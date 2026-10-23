#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srum_emi_cross.py — la quarta sorgente NATIVA che non conoscevo: SRUM.

Scoperta (23/10/2026, probe in experiment_results/alternative_sources_probe_*.txt):
`powercfg /srumutil` da amministratore esporta il database SRUM di Windows con
colonne per-processo `CPUEnergyConsumption`, `EmiEnergyConsumption`,
`TotalEnergyConsumption`, popolate anche su un mini-PC senza batteria
(31726/31726 righe non zero). E' una ripartizione dell'energia per processo fatta
da Windows, quindi UN TERMINE DI CONFRONTO INDIPENDENTE per il capitolo
"perche' l'attribuzione per-processo non funziona" (e per CPU_TIME_SHARE di
cpuepower2) — non un arbitro: la granularita' e' a bucket e il split e' un modello.

Cosa misura qui, sulla stessa scalinata A-B-A:
  1. SCALA: rapporto SRUM(somma per tutti gli AppId) / delta EMI sulla finestra.
     Se SRUM e' in millijoule il rapporto deve venire ~1; se viene ~1000 o ~3600
     l'unita' dichiarata e' sbagliata. E' il test, non un'assunzione.
  2. ATTRIBUZIONE: SRUM CPUEnergyConsumption dell'AppId di ollama.exe vs
     (delta PP0 EMI) x frazione di CPU-time del processo (psutil, misurata nella
     finestra) vs la nostra formula EMI-style E_pkg x cpu_fraction.
  3. PENDENZA: same run, cosi' i due canali guardano la stessa finestra.

Fasi: warm-up (fuori misura) -> idle 120 s -> load 600 s (richette Ollama
identiche a four_way_test.py: num_predict 32, temperature 0) -> idle2 120 s ->
settle 60 s (per far comparire i bucket dell'ultimo minuto nel dump finale).

OROLOGI: la colonna `TimeStamp` del dump SRUM e' UTC naive (misurato: eta' 1,4
min interpretandola UTC contro 121 min interpretandola locale). Le finestre di
fase sono quindi registrate in UTC; il suffisso dei campi e' `utc_*`.

Output:
  experiment_results/srum_emi_cross_<ts>.json  riepilogo e rapporti
  experiment_results/srum_emi_cross_<ts>.csv   righe EMI per fase
  experiment_results/srum_dump_<ts>*.csv       i due dump (NON committati: 8 MB)

Uso: da shell ELEVATA (`powercfg /srumutil` senza admin risponde 0x1f / status 5).
"""
from __future__ import annotations

import ctypes
import datetime
import json
import statistics
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# riusa il trasporto EMI e il carico del four-way, senza duplicarli
from four_way_test import (  # noqa: E402
    MODEL, NUM_PREDICT, PROMPT, PWH_TO_J, emi_pkg, ollama_generate, open_emi,
)
from srum import flush, grand_total, load as srum_load, utc_now_naive  # noqa: E402

# finestre lunghe per proposito: i bucket SRUM sono da ~1 min e il bucket di
# confine mescola idle+load, quindi serve >= 5 bucket per fase per non essere
# dominati dall'errore di bordo (misurato in srum_lag_check: eta' 1,4 min).
FASI = [("idle", 120.0), ("load", 600.0), ("idle2", 120.0)]
SETTLE_S = 60.0        # per far comparire i bucket ritardati nell'ultimo dump
EMI_STEP_S = 5.0       #_tick_ di tracciamento EMI dentro la fase
OUT_DIR = ROOT / "experiment_results"


def emi_all(h) -> dict:
    """Tutti e 4 i record EMI: PKG@0, DRAM@16, PP0@32, PP1@48 (energia pWh, tempo 100 ns)."""
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not ctypes.windll.kernel32.DeviceIoControl(h, 0x0022400C, None, 0,
                                                  out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return {"package": (v[0], v[1]), "dram": (v[2], v[3]),
            "pp0": (v[4], v[5]), "pp1": (v[6], v[7])}


def cpu_seconds_of(name_needle: str) -> tuple:
    """(secondi CPU dei processi che matchano, secondi CPU di TUTTO il sistema)."""
    import psutil
    mine = 0.0
    total = 0.0
    for p in psutil.process_iter(["name", "cpu_times"]):
        try:
            t = p.info["cpu_times"] or {}
            s = float(t.get("user", 0.0) + t.get("system", 0.0))
        except Exception:
            continue
        total += s
        if name_needle and name_needle.lower() in (p.info["name"] or "").lower():
            mine += s
    return mine, total


def main() -> int:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] serve Amministratore: powercfg /srumutil risponde "
              "0x1f + 'SruUpdateStats failed, status 5' senza elevazione.")
        return 2

    print("Warm-up del modello (fuori misura)...")
    ollama_generate()

    h = open_emi()
    print("[OK] EMI attivo.")

    ts_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    d0 = flush(OUT_DIR / f"srum_dump_{ts_tag}_start.csv")
    if d0 is None:
        print("[ERRORE] flush SRUM fallito: niente esperimento.")
        return 3
    snap0 = srum_load(d0)
    print(f"[OK] SRUM dump iniziale: {len(snap0.rows)} righe, "
          f"watermark {snap0.max_ts()}")

    marks = {}
    ticks = []
    tokens = 0
    for fase, dur in FASI:
        t0 = time.monotonic()
        w0 = utc_now_naive()          # UTC: stessa base della TimeStamp SRUM
        e0 = emi_all(h)
        c0 = cpu_seconds_of("ollama")
        print(f"--- fase {fase} ({dur:.0f} s) ---")
        last = t0
        while True:
            t = time.monotonic() - t0
            if t >= dur:
                break
            if fase == "load":
                try:
                    tokens += ollama_generate()
                except Exception as exc:
                    print(f"[WARN] ollama: {exc}")
                if time.monotonic() - t0 >= dur:
                    break
            if time.monotonic() - last >= EMI_STEP_S:
                last = time.monotonic()
                pj, pt = emi_pkg(h)
                ticks.append({"fase": fase, "t_s": round(time.monotonic() - t0, 1),
                              "emi_pkg_pwh": pj, "emi_pkg_ts100ns": pt})
        e1 = emi_all(h)
        c1 = cpu_seconds_of("ollama")
        marks[fase] = {
            "utc_start": w0.isoformat(timespec="seconds"),
            "utc_end": utc_now_naive().isoformat(timespec="seconds"),
            "emi_start": e0, "emi_end": e1,
            "cpu_start": c0, "cpu_end": c1,
        }

    print(f"Settle {SETTLE_S:.0f} s per i bucket SRUM ritardati...")
    time.sleep(SETTLE_S)
    d1 = flush(OUT_DIR / f"srum_dump_{ts_tag}_end.csv")
    snap1 = srum_load(d1)

    # ---- 1) delta EMI per fase e totale --------------------------------------
    def emi_delta(fase, dom):
        m = marks[fase]
        pj0, pt0 = m["emi_start"][dom]
        pj1, pt1 = m["emi_end"][dom]
        return (pj1 - pj0) * PWH_TO_J, (pt1 - pt0) * 1e-7

    per_phase = {}
    for fase, _ in FASI:
        d = {dom: emi_delta(fase, dom) for dom in ("package", "dram", "pp0", "pp1")}
        m = marks[fase]
        per_phase[fase] = {
            "emi_J": {k: round(v[0], 2) for k, v in d.items()},
            "emi_meter_s": {k: round(v[1], 2) for k, v in d.items()},
            "emi_W": {k: (round(v[0] / v[1], 2) if v[1] > 0 else None)
                      for k, v in d.items()},
            "cpu_ollama_s": round(m["cpu_end"][0] - m["cpu_start"][0], 2),
            "cpu_system_s": round(m["cpu_end"][1] - m["cpu_start"][1], 2),
            "utc_start": m["utc_start"], "utc_end": m["utc_end"],
        }

    win_start = datetime.datetime.fromisoformat(marks["idle"]["utc_start"])
    win_end = datetime.datetime.fromisoformat(marks["idle2"]["utc_end"])
    load_start = datetime.datetime.fromisoformat(marks["load"]["utc_start"])
    load_end = datetime.datetime.fromisoformat(marks["load"]["utc_end"])

    # ---- 2) SRUM: somma dei bucket dentro la finestra, per AppId -------------
    def srum_window(a, b):
        per = {}
        for r in snap1.rows:
            t = snap1._ts(r)
            if t is None or not (a < t <= b):
                continue
            app = r.get("AppId", "?")
            d = per.setdefault(app, {})
            for f in ("CPUEnergyConsumption", "EmiEnergyConsumption",
                      "TotalEnergyConsumption", "TimeInMSec"):
                d[f] = d.get(f, 0.0) + snap1._f(r, f)
        return per

    whole = srum_window(win_start, win_end)
    loadw = srum_window(load_start, load_end)
    gt_whole = grand_total(whole)
    gt_load = grand_total(loadw)

    # bucket presenti nella finestra e loro granularita'
    b_ts = sorted({snap1._ts(r) for r in snap1.rows
                   if snap1._ts(r) and win_start < snap1._ts(r) <= win_end})
    gaps = [ (b-a).total_seconds() for a, b in zip(b_ts[:-1], b_ts[1:]) ]

    def ollama_apps(per):
        return {k: v for k, v in per.items() if "ollama" in k.lower()}

    emi_pkg_load_J, emi_pkg_load_s = emi_delta("load", "package")
    emi_pp0_load_J, _ = emi_delta("load", "pp0")
    base_idle_W = statistics.mean([per_phase[f]["emi_W"]["package"]
                                   for f in ("idle", "idle2")])
    e_inc_J = emi_pkg_load_J - base_idle_W * emi_pkg_load_s
    srum_cpu_load = gt_load.get("CPUEnergyConsumption", 0.0)
    srum_emi_load = gt_load.get("EmiEnergyConsumption", 0.0)
    srum_tot_load = gt_load.get("TotalEnergyConsumption", 0.0)
    oll_cpu_load = sum(v.get("CPUEnergyConsumption", 0.0) for v in ollama_apps(loadw).values())
    oll_tot_load = sum(v.get("TotalEnergyConsumption", 0.0) for v in ollama_apps(loadw).values())

    frac_ollama = (per_phase["load"]["cpu_ollama_s"] /
                   per_phase["load"]["cpu_system_s"]
                   if per_phase["load"]["cpu_system_s"] > 0 else None)

    summary = {
        "timestamp": ts_tag,
        "finestra": {"start": marks["idle"]["utc_start"], "end": marks["idle2"]["utc_end"],
                     "load": [marks["load"]["utc_start"], marks["load"]["utc_end"]]},
        "fasi": FASI,
        "settle_s": SETTLE_S,
        "tokens_load": tokens,
        "granularita": {"bucket_nella_finestra": len(b_ts),
                        "delta_bucket_s": [round(g) for g in gaps[:12]]},
        "emi_per_fase": per_phase,
        "srum_totale_finestra": {k: round(v, 1) for k, v in gt_whole.items()},
        "srum_totale_load": {k: round(v, 1) for k, v in gt_load.items()},
        "srum_ollama_load": {k: round(v, 1) for k, v in ollama_apps(loadw).items()},
        "confronto": {
            "EMI_pkg_load_J": round(emi_pkg_load_J, 2),
            "EMI_pp0_load_J": round(emi_pp0_load_J, 2),
            "EMI_incrementale_J": round(e_inc_J, 2),
            "EMI_base_idle_W": round(base_idle_W, 2),
            "EMI_J_per_token": round(e_inc_J / tokens, 4) if tokens else None,
            "SRUM_CPU_load_raw": round(srum_cpu_load, 1),
            "SRUM_Emi_load_raw": round(srum_emi_load, 1),
            "SRUM_Totale_load_raw": round(srum_tot_load, 1),
            "rapporto_SRUMcpu_div_EMIpkg": (round(srum_cpu_load / emi_pkg_load_J, 3)
                                            if emi_pkg_load_J else None),
            "rapporto_SRUMcpu_div_EMIinc": (round(srum_cpu_load / e_inc_J, 3)
                                            if e_inc_J else None),
            "rapporto_SRUMemi_div_EMIpkg": (round(srum_emi_load / emi_pkg_load_J, 3)
                                            if emi_pkg_load_J else None),
            "ipotesi_unita": ("mJ -> rapporto atteso ~1; J -> ~1e-3; uJ -> ~1e6"
                              "; il valore MISURATO decide, non la doc"),
            "SRUM_ollama_cpu_raw": round(oll_cpu_load, 1),
            "SRUM_ollama_share_of_cpu_load": (round(oll_cpu_load / srum_cpu_load, 4)
                                              if srum_cpu_load else None),
            "cpu_time_share_ollama_misurata": round(frac_ollama, 4) if frac_ollama else None,
            "EMI_pkg_x_cpu_share_J": (round(e_inc_J * frac_ollama, 2) if frac_ollama else None),
        },
        "caveat": (
            "SRUM scrive a bucket: la finestra di fase puo' essere spostata di un "
            "bucket (errori di confine ~1 granularita', dichiarata in `granularita`), "
            "e il campo per-processo e' prodotto dal modello EPI di Windows: questo "
            "esperimento confronta DUE attribuzioni (la sua e la nostra frazione di "
            "CPU-time), non ne valida una contro la verita' hardware. L'arbitro resta "
            "il delta EMI/PP0, che e' cumulativo e senza modello."),
    }

    out_json = OUT_DIR / f"srum_emi_cross_{ts_tag}.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = OUT_DIR / f"srum_emi_cross_{ts_tag}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("fase;t_s;emi_pkg_pwh;emi_pkg_ts100ns\n")
        for r in ticks:
            f.write(f"{r['fase']};{r['t_s']};{r['emi_pkg_pwh']};{r['emi_pkg_ts100ns']}\n")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[OK] {out_json}\n[OK] {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
