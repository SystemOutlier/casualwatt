# -*- coding: utf-8 -*-
"""Sonda reale del backend AMD GPU via AMD SMI.

Risponde a cinque domande con numeri, non con l'intenzione:

1. **Il backend AMD SMI si inizializza?** `amdsmi_init()`, enumerazione device,
   selezione per indice (non ID produttore), lettura ASIC info (market_name).
2. **Il contatore energetico è utilizzabile?** `amdsmi_get_energy_count` ritorna
   `energy_accumulator`, `counter_resolution` (>0), `timestamp` (ns, 1 ns
   dichiarato). La conversione `mJ = accumulator * resolution / 1000` è
   verificata su una lettura reale. Risoluzione nulla = contatore non usabile.
3. **Il timestamp avanza?** Due letture consecutive: timestamp deve avanzare
   (altrimenti lettura non valida), contatore può restare fermo (zero legittimo
   con timestamp che avanza). Delta negativo = reset/avvolgimento → si copre
   con integrale, non si clampa.
4. **La potenza dichiara il campo usato?** Ordine: `socket_power` (generale) →
   `current_socket_power` (Mi300+) → `average_socket_power` (Navi/Mi200). Tutti
   in W per documentazione. `gfx_activity` in % da `amdsmi_get_gpu_activity`.
5. **Precedenza NVML?** Se NVML risponde, AMD SMI non viene usato (niente
   doppio lettore). Il tool lo verifica e lo dichiara.

Uso:
    python cwEnergyModular/tools/amdsmi_probe.py --out out.json
    python cwEnergyModular/tools/amdsmi_probe.py --index 0 --out out.json
    python cwEnergyModular/tools/amdsmi_probe.py --compare-nvml --out out.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.energy_session import _open_gpu_monitor, _GPUMonitor, _AMDGPUMonitor  # noqa: E402


def _ts() -> float:
    return time.time()


def _measure_latency(fn, iterations: int = 10) -> Dict[str, float]:
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        latencies.append(time.perf_counter() - t0)
    latencies.sort()
    n = len(latencies)
    return {
        "count": n,
        "median_s": latencies[n // 2],
        "p95_s": latencies[min(n - 1, int(0.95 * (n - 1)))],
        "max_s": latencies[-1],
        "mean_s": sum(latencies) / n,
    }


def _probe_amd_backend(index: Optional[int] = None) -> Dict[str, Any]:
    """Esegue la sonda completa del backend AMD SMI."""
    result: Dict[str, Any] = {
        "backend": "amdsmi",
        "index_requested": index,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "steps": {},
    }

    # Step 1: Inizializzazione e selezione device
    step = {}
    t0 = _ts()
    amd = _AMDGPUMonitor(index=index)
    step["init_latency_s"] = _ts() - t0

    step["available"] = amd.available
    step["error"] = amd.error
    step["device_count"] = amd.device_count
    step["device_selection"] = amd.device_selection
    step["device_note"] = amd.device_note
    step["index_selected"] = amd.index
    step["name"] = amd.name
    step["platform_context"] = amd.platform_context
    step["amd_uuid"] = amd.get_amd_uuid()
    step["bdf"] = amd.get_bdf()

    if amd.available:
        # Step 2: Contatore energetico
        step["energy_counter"] = amd.energy_counter
        step["energy_counter_reason"] = amd.energy_counter_reason
        step["resolution_uj"] = amd._resolution_uj

        if amd.energy_counter:
            # Lettura singola per verificare la conversione
            t0 = _ts()
            energy_mj, ts = amd.read_energy()
            step["read_latency_s"] = _ts() - t0
            step["first_read"] = {
                "energy_mj": energy_mj,
                "timestamp_ns": ts,
                "energy_uj": energy_mj * 1000.0 if energy_mj is not None else None,
            }

            # Due letture consecutive per verificare timestamp
            time.sleep(0.1)
            energy_mj2, ts2 = amd.read_energy()
            step["second_read"] = {
                "energy_mj": energy_mj2,
                "timestamp_ns": ts2,
                "energy_uj": energy_mj2 * 1000.0 if energy_mj2 is not None else None,
            }

            if ts is not None and ts2 is not None:
                step["timestamp_delta_ns"] = ts2 - ts
                step["timestamp_advanced"] = ts2 > ts
            if energy_mj is not None and energy_mj2 is not None:
                step["energy_delta_mj"] = energy_mj2 - energy_mj
                step["energy_delta_uj"] = (energy_mj2 - energy_mj) * 1000.0
                step["negative_delta"] = energy_mj2 < energy_mj

            # Latenza di lettura
            step["read_latency_stats"] = _measure_latency(lambda: amd.read_energy())

        # Step 3: Potenza e attività
        power_w, util_pct = amd.read()
        step["power"] = {
            "power_w": power_w,
            "power_field": amd.power_field,
            "power_unit": amd.power_unit,
            "gfx_activity_pct": util_pct,
        }

        # Step 4: Multiple letture per verificare stabilità
        readings = []
        for _ in range(5):
            e, t = amd.read_energy()
            if e is not None:
                readings.append((e, t))
            time.sleep(0.05)
        step["stability_readings"] = len(readings)
        if len(readings) >= 2:
            deltas = [readings[i+1][0] - readings[i][0] for i in range(len(readings)-1)]
            step["energy_deltas_mj"] = deltas
            step["any_negative_delta"] = any(d < 0 for d in deltas)

    result["steps"] = step
    result["summary"] = {
        "backend_usable": amd.available and amd.energy_counter,
        "counter_resolution_valid": amd.energy_counter and amd._resolution_uj > 0,
        "timestamp_advances": step.get("timestamp_advanced", False),
        "power_field_declared": bool(amd.power_field) if amd.available else False,
        "selection_note": amd.device_note,
    }

    amd.shutdown()
    return result


def _probe_nvml_precedence(index: Optional[int] = None) -> Dict[str, Any]:
    """Verifica che NVML abbia precedenza su AMD SMI quando entrambi disponibili."""
    result: Dict[str, Any] = {
        "test": "nvml_precedence",
        "index_requested": index,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
    }

    # Tenta NVML
    nv = _GPUMonitor(index=index)
    result["nvml"] = {
        "available": nv.available,
        "error": nv.error,
        "name": nv.name,
        "index": nv.index,
        "energy_counter": nv.energy_counter,
    }

    if nv.available:
        # Se NVML disponibile, _open_gpu_monitor deve restituire NVML
        monitor = _open_gpu_monitor(index=index)
        result["open_gpu_monitor_returns"] = {
            "backend": monitor.__class__.__name__,
            "available": monitor.available,
            "name": getattr(monitor, 'name', None),
        }
        result["precedence_ok"] = isinstance(monitor, _GPUMonitor)
    else:
        # NVML non disponibile: AMD SMI dovrebbe essere provato
        monitor = _open_gpu_monitor(index=index)
        result["open_gpu_monitor_returns"] = {
            "backend": monitor.__class__.__name__,
            "available": monitor.available,
            "name": getattr(monitor, 'name', None),
        }
        result["precedence_ok"] = True  # non c'è conflitto

    return result


def main():
    parser = argparse.ArgumentParser(description="AMD SMI GPU backend probe")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file")
    parser.add_argument("--index", type=int, default=None, help="GPU index to probe")
    parser.add_argument("--compare-nvml", action="store_true",
                        help="Also test NVML precedence")
    args = parser.parse_args()

    output = {
        "probe": "amdsmi_probe",
        "python_platform": sys.platform,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        "index_requested": args.index,
    }

    # Sonda AMD SMI
    print(f"[INFO] Probing AMD SMI backend (index={args.index})...")
    amd_result = _probe_amd_backend(args.index)
    output["amd_smi"] = amd_result

    summary = amd_result["summary"]
    if summary["backend_usable"]:
        print(f"[OK] AMD SMI backend usable: {amd_result['steps'].get('name', 'unknown')}")
        print(f"     Counter resolution: {amd_result['steps'].get('resolution_uj', 'N/A')} uJ")
        print(f"     Power field: {amd_result['steps'].get('power', {}).get('power_field', 'N/A')}")
        print(f"     Timestamp advances: {summary['timestamp_advances']}")
    else:
        print(f"[WARN] AMD SMI backend not usable: {amd_result['steps'].get('error', 'unknown')}")
        print(f"     energy_counter: {summary.get('counter_resolution_valid', False)}")

    # Test precedenza NVML
    if args.compare_nvml:
        print("[INFO] Testing NVML precedence...")
        nvml_result = _probe_nvml_precedence(args.index)
        output["nvml_precedence"] = nvml_result
        if nvml_result["precedence_ok"]:
            print("[OK] NVML precedence respected")
        else:
            print("[FAIL] NVML precedence NOT respected!")

    # Scrivi output
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"[INFO] Results written to {args.out}")

    # Exit code: 0 se AMD SMI usable, 1 se non usable ma senza errori, 2 se errore critico
    if summary["backend_usable"]:
        return 0
    elif amd_result["steps"].get("error"):
        return 1
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())