#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lhm_pi_path_test.py — l'offset di +55 W e' nel SENSORE o nel NOSTRO percorso?

Contexto (misurato, 23/10/2026, sequenza di due esperimenti):

  A) `lhm_sensor_dump.py` (run 20261023_124448, esperimento PULITO: UN SOLO thread,
     UN SOLO `hw.Update()` per tick a 1 Hz, stessa DLL di produzione 0.9.4.0):
        LHM "CPU Package"   idle 14,33 W   burn2 29,56 W   burn8 38,02 W
        EMI PKG             idle 14,29 W   burn2 30,18 W   burn8 38,92 W
     -> offset a idle = +0,04 W, rapporti delta EMI/delta sensore = 1,043 e 1,040.
     Il sensore, letto cosi', E' il contatore RAPL di package (come dice il
     sorgente 0.9.6 in IntelCpu.cs:696: delta(MSR 0x611)/dt) e coincide con EMI.

  B) il percorso DI PRODUZIONE (CasualWatt SESSION, power-integration) da'
     69-73 W nelle stesse identiche condizioni (four_way run 1 e 2, offset
     +55,9 W e pendenza ~0,5 sull'inferenza).

Quindi la divergenza che abbiamo attribuito a "LHM invalidato" NON e' del
sensore: e' introdotta da come LO LEGGIAMO NOI. Differenze candidate fra A e B:
  1. frequenza: il thread di integrazione chiama `hw.Update()` ogni
     POWER_SAMPLE_INTERVAL_S = 0,05 s (energy_session.py:45, :840-854), mentre
     il costo reale di un Update sull'assembly e' ~0,32 s (misurato in
     pi_diagnostics): `IntelCpu.Update()` ricalcola `deltaTime` fra chiamate
     concorrenti e `sensor.Value` viene sovrascritto da piu' caller;
  2. concorrenza: oltre al thread PI, il sampler di produzione chiama altri
     punti che fanno `hw.Update()` (`_lhm_value` riga 649, `_read_power_w_direct`
     riga 812, `_select_power_sensor` riga 750, `_gpu.read`): piu' thread sullo
     STESSO oggetto sensore senza lock, mentre A ha un solo thread;
  3. selezione del sensore (esclusa da A: "CPU Package" e' unico, idx 0, e gli
     altri 4 sensori hanno i valori attesi: CPU Cores = PP0 8,13 W, CPU Memory =
     DRAM 0,0 W, CPU Platform 0,33 W, GPU Power 0,36 W).

Questo test distingue 1+2 (percorso) dal sensore, con lo stesso protocollo a
fasi di A (idle / burn2 / burn8 / cool) ecampione Contemporaneamente:
  * EMI PKG [W] dal contatore cumulativo (riferimento hardware);
  * W "come lo riporta CasualWatt": integrazione del thread PI sulla fase
    (delta di `src._pi_energy_j` / durata reale);
  * i VALORI grezzi del sensore che il thread PI scrive in `sensor.Value`
    (letti dal nostro thread SENZA chiamare Update, cosi' non aggiungiamo
    concorrenza), con media/mediana/max e il numero di campioni per secondo
    réellement osservato.

Lettura: se EMI ~14 W a idle e il percorso di produzione ~70 W con gli STESSI
oggetti LHM, il difetto e' nel percorso (frequenza/concorrenza) e i numeri
Windows di CasualWatt (v1, v2, v3, four-way) vanno ritrattati. Se invece anche
qui il grezzo valesse ~70 W, la causa sarebbe lo stato dell'assembly dopo
SESSION.start() e va cercata li'.

NON modifica `energy_session.py` (vincolo di progetto): lo usa e basta.
Serve AMMINISTRATORE. Output: experiment_results/lhm_pi_path_<ts>.{csv,json}
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
OUT_DIR = ROOT / "experiment_results"
FASI = [("idle", 30.0), ("burn2", 30.0), ("burn8", 30.0), ("cool", 25.0)]
BURN_N = {"idle": 0, "burn2": 2, "burn8": 8, "cool": 0}


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
    print(f"[OK] SESSION avviata: method={src.method} "
          f"sensor='{getattr(src, '_pi_sensor_name', '?')}' "
          f"periodo_dichiarato={src.POWER_SAMPLE_INTERVAL_S} s")
    print(f"[OK] sensori Power visti da produzione: "
          f"{getattr(src, '_pi_sensors_seen', [])}")
    sel = getattr(src, "_pi_selected", None)
    if sel is None:
        print("[ERRORE] nessun sensore Power selezionato: il test non ha senso.")
        SESSION.stop()
        return 3

    h = open_emi()
    rows = []
    prev = None          # (t, pi_energy_j, n_samples, emi)
    for fase, dur in FASI:
        t0 = time.monotonic()
        procs = [mp.Process(target=burn, args=(t0 + dur,)) for _ in range(BURN_N[fase])]
        for p in procs:
            p.start()
        print(f"--- fase {fase} ({dur:.0f} s, {BURN_N[fase]} processi burn) ---")
        with src._pi_lock:
            e_start = src._pi_energy_j
            n_start = len(src._pi_samples)
        emi_start = emi_all(h)
        phase_vals = []
        while time.monotonic() - t0 < dur:
            time.sleep(1.0)
            try:
                raw = float(sel.Value)
            except Exception:
                raw = None
            with src._pi_lock:
                ej = src._pi_energy_j
                ns = len(src._pi_samples)
            e = emi_all(h)
            now = time.monotonic()
            rows.append({"fase": fase, "t": round(now - t0, 2),
                         "raw_value_W": raw, "pi_energy_j": round(ej, 3),
                         "pi_samples": ns,
                         "emi_pkg_pwh": e["package"][0],
                         "emi_pkg_t100ns": e["package"][1]})
            if raw is not None and raw == raw:
                phase_vals.append(raw)
            prev = (now, ej, ns, e)
        t_end = time.monotonic()
        with src._pi_lock:
            e_end = src._pi_energy_j
            n_end = len(src._pi_samples)
        emi_end = emi_all(h)
        dt = t_end - t0
        dJ = (emi_end["package"][0] - emi_start["package"][0]) * 3.6e-9
        dPP0 = (emi_end["pp0"][0] - emi_start["pp0"][0]) * 3.6e-9
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()
        rows.append({"fase": fase, "t": round(dt, 2), "raw_value_W": None,
                     "pi_energy_j": round(e_end, 3), "pi_samples": n_end,
                     "emi_pkg_pwh": emi_end["package"][0],
                     "emi_pkg_t100ns": emi_end["package"][1],
                     "RIASSUNTO": {
                         "EMI_pkg_W": round(dJ / dt, 2),
                         "EMI_pp0_W": round(dPP0 / dt, 2),
                         "produzione_W": round((e_end - e_start) / dt, 2),
                         "campioni_PI_al_s": round((n_end - n_start) / dt, 2),
                         "raw_value_media_W": (round(statistics.mean(phase_vals), 2)
                                               if phase_vals else None),
                         "raw_value_mediana_W": (round(statistics.median(phase_vals), 2)
                                                 if phase_vals else None),
                         "raw_value_max_W": (round(max(phase_vals), 2)
                                             if phase_vals else None),
                         "raw_value_min_W": (round(min(phase_vals), 2)
                                             if phase_vals else None),
                     }})

    riassunti = [r["RIASSUNTO"] for r in rows if "RIASSUNTO" in r]
    idle = riassunti[0]
    out = {
        "timestamp": ts,
        "protocollo": "identico a lhm_sensor_dump_20261023_124448 (idle 30 / burn2 30 / burn8 30 / cool 25)",
        "periodo_dichiarato_s": src.POWER_SAMPLE_INTERVAL_S,
        "sensor": getattr(src, "_pi_sensor_name", "?"),
        "metodo": src.method,
        "fasi": riassunti,
        "confronto": {
            "idle_EMI_W": idle["EMI_pkg_W"],
            "idle_produzione_W": idle["produzione_W"],
            "offset_W": round(idle["produzione_W"] - idle["EMI_pkg_W"], 2),
            "rapporto_burn8": (round(riassunti[2]["produzione_W"] / riassunti[2]["EMI_pkg_W"], 3)
                               if riassunti[2]["EMI_pkg_W"] else None),
            "delta_burn8_EMI_W": round(riassunti[2]["EMI_pkg_W"] - idle["EMI_pkg_W"], 2),
            "delta_burn8_produzione_W": round(riassunti[2]["produzione_W"] - idle["produzione_W"], 2),
            "delta_burn2_EMI_W": round(riassunti[1]["EMI_pkg_W"] - idle["EMI_pkg_W"], 2),
            "delta_burn2_produzione_W": round(riassunti[1]["produzione_W"] - idle["produzione_W"], 2),
            "campioni_PI_al_s_obs": [r["campioni_PI_al_s"] for r in riassunti],
        },
        "run_pulito_di_riferimento": {
            "file": "lhm_sensor_dump_20261023_124448.json",
            "idle_LHM_W": 14.33, "idle_EMI_W": 14.29,
            "burn8_LHM_W": 38.02, "burn8_EMI_W": 38.92,
            "rapporti_delta": [1.043, 1.04],
        },
    }

    OUT_DIR.mkdir(exist_ok=True)
    oj = OUT_DIR / f"lhm_pi_path_{ts}.json"
    oj.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    oc = OUT_DIR / f"lhm_pi_path_{ts}.csv"
    with open(oc, "w", encoding="utf-8") as f:
        f.write("fase;t;raw_value_W;pi_energy_j;pi_samples;emi_pkg_pwh;emi_pkg_t100ns\n")
        for r in rows:
            f.write(f"{r['fase']};{r['t']};{r['raw_value_W']};{r['pi_energy_j']};"
                    f"{r['pi_samples']};{r['emi_pkg_pwh']};{r['emi_pkg_t100ns']}\n")

    print("\n=== fasi ===")
    for r in riassunti:
        print("  " + json.dumps(r, ensure_ascii=False))
    print("\n=== confronto ===")
    print(json.dumps(out["confronto"], indent=2, ensure_ascii=False))
    print(f"\n[OK] {oj}\n[OK] {oc}")
    SESSION.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
