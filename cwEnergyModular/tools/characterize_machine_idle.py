#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Caratterizzazione macchina: misura idle power e CPU% su finestre 2s.

Obiettivo: determinare threshold quiet/warmup raggiungibili OGGI su questa macchina,
per aggiornare i parametri pre-registrati prima della campagna P4.4 #3.

Misura:
- Finestre non sovrapposte da 2s (WARMUP_WINDOW_S)
- Potenza: delta contatore EMI / delta tempo (stesso canale di produzione)
- CPU%: media campioni psutil sulla finestra
- Durata target: 600s (10 min) = 300 finestre
- Output: JSONL con ogni finestra + statistiche aggregate
"""

from __future__ import annotations
import json
import time
import statistics
import psutil
from pathlib import Path
from datetime import datetime, timezone

# Importa il percorso di misura di produzione
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from energy.energy_session import SESSION, EnergySession
import energy.energy_session as es_mod

# Costanti del criterio warm-up (attuali, da aggiornare)
WARMUP_WINDOW_S = 2.0
TARGET_DURATION_S = 600.0  # 10 minuti
OUTPUT_PATH = Path(__file__).parent.parent.parent / "experiment_results" / "machine_characterization_20261113.jsonl"


def main():
    print(f"[CHAR] Avvio caratterizzazione macchina — {TARGET_DURATION_S:.0f}s target")
    print(f"[CHAR] Finestra: {WARMUP_WINDOW_S}s, Canale: EMI package counter")
    print(f"[CHAR] Output: {OUTPUT_PATH}")
    
    # Apri sessione energetica (stessa catena di produzione - usa il singleton SESSION)
    sessione = SESSION
    sessione.start()  # avvia il sampler (include EMI sampling thread)
    
    src = sessione._source
    print(f"[CHAR] Canale attivo: {getattr(src, 'method', 'sconosciuto')}")
    
    # Warm-up lettura contatore (primo campione)
    print("[CHAR] Lettura iniziale contatore...")
    first = sessione.read_measurement_edge()
    if first is None or first.get("counter") is None:
        print("[CHAR] ERRORE: contatore non leggibile")
        return 1
    counter_data = first.get("counter", {})
    t0_counter = float(first.get("t_counter_mono", 0))
    e0_counter = float(counter_data.get("pkg_j", 0))
    t0_mono = time.monotonic()
    
    risultati = []
    finestra_idx = 0
    start_time = time.monotonic()
    
    try:
        while (time.monotonic() - start_time) < TARGET_DURATION_S:
            finestra_start = time.monotonic()
            
            # Attendi durata finestra
            time.sleep(WARMUP_WINDOW_S)
            
            # Leggi contatore (bordo fine finestra)
            edge = sessione.read_measurement_edge()
            if edge is None or edge.get("counter") is None:
                print(f"[CHAR] Finestra {finestra_idx}: contatore non leggibile")
                risultati.append({
                    "finestra": finestra_idx,
                    "t_mono_start": finestra_start,
                    "t_mono_end": time.monotonic(),
                    "power_w": None,
                    "cpu_pct": None,
                    "error": "counter_unreadable"
                })
                finestra_idx += 1
                continue
            
            t1_counter = float(edge.get("t_counter_mono", 0))
            e1_counter = float(edge.get("counter", {}).get("pkg_j", 0))
            dt_counter = t1_counter - t0_counter
            de_j = e1_counter - e0_counter
            
            # CPU% sulla finestra (psutil con intervallo = durata finestra)
            cpu_samples = psutil.cpu_percent(interval=WARMUP_WINDOW_S, percpu=False)
            cpu_pct = float(cpu_samples) if cpu_samples is not None else None
            
            # Potenza
            if dt_counter > 0 and de_j >= 0:
                power_w = de_j / dt_counter
            else:
                power_w = None
            
            record = {
                "finestra": finestra_idx,
                "t_mono_start": finestra_start,
                "t_mono_end": time.monotonic(),
                "dt_counter_s": dt_counter,
                "de_j": de_j,
                "power_w": power_w,
                "cpu_pct": cpu_pct,
                "counter_t0": t0_counter,
                "counter_t1": t1_counter,
            }
            risultati.append(record)
            
            # Avanzamento
            if finestra_idx % 30 == 0:
                pw = f"{power_w:.3f}" if power_w is not None else "N/A"
                cp = f"{cpu_pct:.1f}" if cpu_pct is not None else "N/A"
                print(f"  [{finestra_idx:>3}] power={pw}W  cpu={cp}%")
            
            # Prepara prossima finestra
            t0_counter = t1_counter
            e0_counter = e1_counter
            finestra_idx += 1
            
    except KeyboardInterrupt:
        print(f"\n[CHAR] Interrotto dall'utente a finestra {finestra_idx}")
    finally:
        sessione.close()
    
    # Statistiche aggregate
    valid_power = [r["power_w"] for r in risultati if r["power_w"] is not None]
    valid_cpu = [r["cpu_pct"] for r in risultati if r["cpu_pct"] is not None]
    
    stats = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "target_duration_s": TARGET_DURATION_S,
            "window_s": WARMUP_WINDOW_S,
            "finestre_totali": len(risultati),
            "finestre_valide_power": len(valid_power),
            "finestre_valide_cpu": len(valid_cpu),
            "canale": getattr(src, 'method', 'sconosciuto'),
        },
        "power_w": {
            "count": len(valid_power),
            "mean": statistics.mean(valid_power) if valid_power else None,
            "median": statistics.median(valid_power) if valid_power else None,
            "stdev": statistics.stdev(valid_power) if len(valid_power) > 1 else None,
            "min": min(valid_power) if valid_power else None,
            "max": max(valid_power) if valid_power else None,
            "range": max(valid_power) - min(valid_power) if valid_power else None,
            "p95": sorted(valid_power)[int(0.95 * len(valid_power))] if valid_power else None,
            "p99": sorted(valid_power)[int(0.99 * len(valid_power))] if valid_power else None,
        },
        "cpu_pct": {
            "count": len(valid_cpu),
            "mean": statistics.mean(valid_cpu) if valid_cpu else None,
            "median": statistics.median(valid_cpu) if valid_cpu else None,
            "stdev": statistics.stdev(valid_cpu) if len(valid_cpu) > 1 else None,
            "min": min(valid_cpu) if valid_cpu else None,
            "max": max(valid_cpu) if valid_cpu else None,
            "range": max(valid_cpu) - min(valid_cpu) if valid_cpu else None,
            "p95": sorted(valid_cpu)[int(0.95 * len(valid_cpu))] if valid_cpu else None,
            "p99": sorted(valid_cpu)[int(0.99 * len(valid_cpu))] if valid_cpu else None,
        },
        "finestre": risultati
    }
    
    # Scrivi JSONL (una riga per finestra) + summary finale
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for r in risultati:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.write(json.dumps({"_summary": stats}, ensure_ascii=False) + "\n")
    
    print(f"\n[CHAR] Completato: {len(risultati)} finestre, {len(valid_power)} power valide, {len(valid_cpu)} cpu valide")
    print(f"[CHAR] Power: mean={stats['power_w']['mean']:.3f}W median={stats['power_w']['median']:.3f}W range={stats['power_w']['range']:.3f}W p95={stats['power_w']['p95']:.3f}W")
    print(f"[CHAR] CPU%:  mean={stats['cpu_pct']['mean']:.1f}% median={stats['cpu_pct']['median']:.1f}% range={stats['cpu_pct']['range']:.1f}% p95={stats['cpu_pct']['p95']:.1f}%")
    print(f"[CHAR] Salvato in: {OUTPUT_PATH}")
    
    # Suggerimento threshold
    if valid_power and valid_cpu:
        p95_power = stats['power_w']['p95']
        p95_cpu = stats['cpu_pct']['p95']
        median_power = stats['power_w']['median']
        median_cpu = stats['cpu_pct']['median']
        
        print(f"\n[CHAR] SUGGERIMENTO THRESHOLD (basato su p95):")
        print(f"  WARMUP_TOLERANCE_W  >= {p95_power - median_power:.3f}W  (p95 - median)")
        print(f"  WARMUP_CPU_MAX_PCT  >= {p95_cpu:.1f}%     (p95)")
        print(f"  WARMUP_SUSTAIN_S    <= 10s  (da verificare: quante finestre consecutive entro banda)")
        print(f"  QUIET_CONSECUTIVE   = 3  (invariato, serve baseline_pre_w stabile)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())