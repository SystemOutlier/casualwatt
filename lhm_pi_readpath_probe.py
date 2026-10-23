#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lhm_pi_readpath_probe.py — prova DIRETTA del meccanismo trovato nel codice.

Ipotesi da testare (non assunzione): `energy_session._read_power_w_direct()`
(:799-831) ritorna al PRIMO sensore che soddisfa
`:819  if sensor is sel or str(sensor.Name) == self._pi_sensor_name`.
Il selettore (:731-797) sceglie correttamente un sensore di tipo Power, ma in
`LibreHardwareMonitor-0.9.6/.../IntelCpu.cs:401` viene creato un sensore
**Temperature con la STESSA etichetta "CPU Package"**, e in `:480` i Power sono
creati DOPO: quindi nella lista `hw.Sensors` il primo match per nome e' la
TEMPERATURA. Se l'ipotesi e' vera, il thread di integrazione accumula °C·s.

Cosa stampa, stesso istante, stesso oggetto `src` della `SESSION` reale:

  1. `src._read_power_w_direct()`  -> il valore che FINISCE NELL'INTEGRALE;
  2. `src._pi_selected.Value`      -> il valore del sensore Power (quello "giusto");
  3. l'elenco di TUTTI i sensori della CPU con nome == `_pi_sensor_name`,
     con `SensorType` e posizione in lista (il colpevole deve precedere);
  4. `SESSION` accumulatore `/_pi_energy_j` e EMI PKG [W] come arbitro.

Fasi: idle -> burn8 -> cool (40 s ciascuna). La firma attesa dell'ipotesi:
`_read_power_w_direct` sale lentamente nel burn e **resta alto nella fase cool**
(inerzia termica), mentre `Value` del Power e EMI tornano subito a ~14 W.

Nessuna modifica al backend: qui si SOLO legge lo stato degli oggetti.
Servono privilegi di Amministratore (LHM).
Output: experiment_results/lhm_readpath_probe_<ts>.{json,csv}
"""
from __future__ import annotations

import ctypes
import datetime
import json
import multiprocessing as mp
import statistics
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

from four_way_test import open_emi  # noqa: E402

IOCTL = 0x0022400C
PWH_TO_J = 3.6e-9
OUT_DIR = ROOT / "experiment_results"
FASI = [("idle", 40.0), ("burn8", 40.0), ("cool", 40.0)]
BURN_N = {"idle": 0, "burn8": 8, "cool": 0}


def emi_all(h) -> dict:
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not ctypes.windll.kernel32.DeviceIoControl(h, IOCTL, None, 0, out, 64,
                                                  ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return {"package": (v[0], v[1]), "dram": (v[2], v[3]),
            "pp0": (v[4], v[5]), "pp1": (v[6], v[7])}


def burn(stop_at: float) -> None:
    x = 0.0
    while time.monotonic() < stop_at:
        for _ in range(200_000):
            x += 1.0


def main() -> int:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] serve Amministratore (LHM).")
        return 2

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    from energy.energy_session import SESSION  # noqa: E402
    SESSION.start()
    src = SESSION._source
    sel = getattr(src, "_pi_selected", None)
    name = getattr(src, "_pi_sensor_name", "?")
    print(f"[OK] method={src.method} sensore selezionato='{name}' "
          f"Power visti={getattr(src, '_pi_sensors_seen', [])}")
    if sel is None:
        print("[ERRORE] nessun sensore Power selezionato: il probe non ha senso.")
        SESSION.stop()
        return 3

    # --- (3) tutti i sensori della CPU che si chiamano come quello scelto -------
    omonimi = []
    for hw in src._lhm.Hardware:
        try:
            hw.Update()
        except Exception:
            continue
        if not src._lhm_is_cpu_hw(hw):
            continue
        for pos, sensor in enumerate(list(hw.Sensors) + [
                s for sub in (list(getattr(hw, "SubHardware", []) or [])) for s in sub.Sensors]):
            try:
                if str(sensor.Name).strip() == str(name).strip():
                    omonimi.append({"posizione_in_lista": pos,
                                    "tipo": src._lhm_sensor_type_name(sensor),
                                    "value": (None if sensor.Value is None
                                              else round(float(sensor.Value), 3))})
            except Exception:
                continue
    print("[Sensori con il nome scelto]", json.dumps(omonimi, ensure_ascii=False))
    print(f"[OK] il sensore Power scelto e' in posizione: "
          f"{[o['posizione_in_lista'] for o in omonimi if o['tipo'].lower() == 'power']}")

    h = open_emi()
    rows, riassunti = [], []
    for fase, dur in FASI:
        t0 = time.monotonic()
        procs = [mp.Process(target=burn, args=(t0 + dur,)) for _ in range(BURN_N[fase])]
        for p in procs:
            p.start()
        print(f"--- fase {fase} ({dur:.0f} s, {BURN_N[fase]} processi burn) ---")
        e0 = emi_all(h)
        with src._pi_lock:
            ej0, n0 = src._pi_energy_j, len(src._pi_samples)
        letti = []
        last = t0
        while time.monotonic() - t0 < dur:
            time.sleep(0.2)
            if time.monotonic() - last < 1.0:
                continue
            last = time.monotonic()
            vw = src._read_power_w_direct()          # (1) quello che viene integrato
            vp = None
            try:
                vp = float(sel.Value)                # (2) il Power "giusto"
            except Exception:
                pass
            with src._pi_lock:
                ej = src._pi_energy_j
            elapsed = time.monotonic() - t0
            r = {"fase": fase, "t_s": round(elapsed, 2),
                 "read_power_w_direct": (None if vw is None else round(float(vw), 3)),
                 "pi_selected_Value": (None if vp is None else round(vp, 3)),
                 "pi_energy_j": round(ej, 3),
                 "samples": len(src._pi_samples)}
            rows.append(r)
            letti.append(r)
        e1 = emi_all(h)
        with src._pi_lock:
            ej1 = src._pi_energy_j
            n1 = len(src._pi_samples)
        dt = time.monotonic() - t0
        dt_pkg = (e1["package"][1] - e0["package"][1]) * 1e-7
        e_pkg = (e1["package"][0] - e0["package"][0]) * PWH_TO_J
        rd = [x["read_power_w_direct"] for x in letti if x["read_power_w_direct"] is not None]
        vp = [x["pi_selected_Value"] for x in letti if x["pi_selected_Value"] is not None]
        riassunti.append({
            "fase": fase,
            "EMI_pkg_W": round(e_pkg / dt_pkg, 2) if dt_pkg > 0 else None,
            "read_power_w_direct_mediana": round(statistics.median(rd), 2) if rd else None,
            "pi_selected_Value_mediana": round(statistics.median(vp), 2) if vp else None,
            "produzione_W": round((ej1 - ej0) / dt, 2),
            "campioni_PI_al_s": round((n1 - n0) / dt, 2),
        })
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

    ok = riassunti[0]
    cool = riassunti[2]
    verdetto = {
        "domanda": "_read_power_w_direct() ritorna il sensore Power o un omonimo?",
        "idle_read_vs_Value": [ok["read_power_w_direct_mediana"],
                               ok["pi_selected_Value_mediana"]],
        "idle_EMI_W": ok["EMI_pkg_W"],
        "cool_read_vs_Value": [cool["read_power_w_direct_mediana"],
                               cool["pi_selected_Value_mediana"]],
        "cool_EMI_W": cool["EMI_pkg_W"],
        "firma_attesa_se_temperatura": ("read_power_w_direct >> Value del Power, "
                                        "e in fase cool read resta alto mentre "
                                        "Value ed EMI tornano a ~14 W"),
    }
    SESSION.stop()

    out_json = OUT_DIR / f"lhm_readpath_probe_{ts}.json"
    out_json.write_text(json.dumps({"timestamp": ts, "fasi": FASI,
                                    "sensori_omonimi": omonimi,
                                    "riassunti": riassunti, "verdetto": verdetto},
                                   indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = OUT_DIR / f"lhm_readpath_probe_{ts}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("fase;t_s;read_power_w_direct;pi_selected_Value;pi_energy_j;samples\n")
        for r in rows:
            f.write(f"{r['fase']};{r['t_s']};{r['read_power_w_direct']};"
                    f"{r['pi_selected_Value']};{r['pi_energy_j']};{r['samples']}\n")
    print(json.dumps({"riassunti": riassunti, "verdetto": verdetto},
                     indent=2, ensure_ascii=False))
    print(f"[OK] {out_json}\n[OK] {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
