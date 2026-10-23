#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
four_way_pi_audit.py — revisione INDIPENDENTE degli integrali del four-way.

Rilegge dai file committati (four_way_<ts>.csv, four_way_<ts>_pi.csv,
four_way_<ts>.json) quello che il log del four-way ha dichiarato, con codice
separato e riscritto da zero: se i numeri non coincidono, l'integrazione di
four_way_test.py e' sbagliata e il JSON non e' affidabile.

Controlli per fase:
  1. integrale trapezoidale del buffer di produzione sulla finestra dichiarata
     (cw_t0_mono .. cw_t1_mono)  -> deve uguagliare cw_J_fase
  2. delta del contatore EMI interpolato linearmente sui tick, sulla STESSA
     finestra -> deve uguagliare emi_J_finestra_uguale
  3. rapporto dei due -> deve uguagliare rapporto_cw_div_EMI_finestra_uguale
  4. "modo_debole": LHM istantaneo al tick / media EMI sull'intervallo tra i
     tick, ricalcolato dal CSV dei tick

Uso:
  python four_way_pi_audit.py              # ultima esecuzione in experiment_results
  python four_way_pi_audit.py 20261023_145041
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RES = ROOT / "experiment_results"
PWH_TO_J = 3.6e-9
TOL_J = 0.01          # 10 mJ: arrotondamenti del JSON (3 decimali) + float


def interp(pairs, t):
    """Valore di una serie monotona interpolato linearmente in t (None fuori range)."""
    if not pairs or t < pairs[0][0] or t > pairs[-1][0]:
        return None
    for i in range(1, len(pairs)):
        if pairs[i][0] >= t:
            (t0, v0), (t1, v1) = pairs[i - 1], pairs[i]
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * (t - t0) / (t1 - t0)
    return pairs[-1][1]


def trapezoid(pairs, t0, t1):
    """Integrale trapezoidale di (t, W) tra t0 e t1, con bordi interpolati."""
    inside = [(t, w) for (t, w) in pairs if t0 <= t <= t1]
    pts = [(t0, interp(pairs, t0))] + inside + [(t1, interp(pairs, t1))]
    if any(p[1] is None for p in pts):
        return None, 0
    e = sum((pts[i][1] + pts[i + 1][1]) / 2.0 * (pts[i + 1][0] - pts[i][0])
            for i in range(len(pts) - 1))
    return e, len(inside)


def latest_run():
    js = sorted(RES.glob("four_way_2*.json"), key=lambda p: p.stat().st_mtime)
    if not js:
        raise SystemExit("[ERRORE] nessun four_way_<ts>.json in experiment_results")
    return js[-1].stem.replace("four_way_", "")


def main():
    ts = sys.argv[1] if len(sys.argv) > 1 else latest_run()
    jf = RES / f"four_way_{ts}.json"
    tf = RES / f"four_way_{ts}.csv"
    pf = RES / f"four_way_{ts}_pi.csv"
    for f in (jf, tf, pf):
        if not f.exists():
            raise SystemExit(f"[ERRORE] manca {f}")

    d = json.loads(jf.read_text(encoding="utf-8"))
    ticks = list(csv.DictReader(open(tf, encoding="utf-8"), delimiter=";"))
    buf = sorted((float(r["mono"]), float(r["w"]))
                 for r in csv.DictReader(open(pf, encoding="utf-8"), delimiter=";"))
    emi = [(float(r["mono"]), float(r["emi_pkg_pwh"])) for r in ticks]

    dt_buf = [b - a for (a, _), (b, _) in zip(buf, buf[1:]) if b - a < 5]
    print(f"run {ts} | buffer {len(buf)} campioni, dt mediano "
          f"{statistics.median(dt_buf):.3f} s (il thread dichiara 0,05 s: "
          f"{statistics.median(dt_buf)/0.05:.1f}x piu' lento)")
    print(f"{'fase':7s} {'J_LHM_audit':>12s} {'J_LHM_json':>11s} {'scarto':>8s} "
          f"{'J_EMI_audit':>12s} {'J_EMI_json':>11s} {'rap_audit':>10s} "
          f"{'rap_json':>9s} {'modo_debole':>12s}")
    ok = True
    for fase in [f for f, _ in d["fasi"]]:
        s = (d["per_fase"] or {}).get(fase) or {}
        t0, t1 = s.get("cw_t0_mono"), s.get("cw_t1_mono")
        if t0 is None:
            print(f"{fase:7s} assente nel JSON: {s.get('cw_win_note')}")
            ok = False
            continue
        j_cw, n = trapezoid(buf, t0, t1)
        # il JSON dichiara i bordi arrotondati a 3 decimali: un bordo puo'
        # risultare ~1 ms fuori dall'asse reale dei tick (o del buffer). Si
        # riporta dentro, perche' e' un artefatto di formattazione, non di misura
        e_lo, e_hi = emi[0][0], emi[-1][0]
        t0e = min(max(t0, e_lo), e_hi)
        t1e = min(max(t1, e_lo), e_hi)
        p0, p1 = interp(emi, t0e), interp(emi, t1e)
        j_emi = None if (p0 is None or p1 is None) else (p1 - p0) * PWH_TO_J
        fr = [r for r in ticks if r["fase"] == fase and r["lhm_w"]]
        coppie = [(float(b["lhm_w"]),
                   (float(b["emi_pkg_pwh"]) - float(a["emi_pkg_pwh"])) * PWH_TO_J /
                   ((float(b["emi_pkg_ts100ns"]) - float(a["emi_pkg_ts100ns"])) * 1e-7))
                  for a, b in zip(fr, fr[1:])
                  if float(b["emi_pkg_ts100ns"]) > float(a["emi_pkg_ts100ns"])]
        debole = (statistics.mean([c[0] for c in coppie]) /
                  statistics.mean([c[1] for c in coppie])) if coppie else None
        rap = None if not j_emi else j_cw / j_emi
        sc = None if j_cw is None else (j_cw - s["cw_J_fase"]) / j_cw
        ok = ok and sc is not None and abs(sc) < 1e-3 and abs(rap - s[
            "rapporto_cw_div_EMI_finestra_uguale"]) < 1e-3
        print(f"{fase:7s} {j_cw:12.2f} {s['cw_J_fase']:11.2f} {100*sc:+7.3f}% "
              f"{j_emi:12.2f} {s['emi_J_finestra_uguale']:11.2f} {rap:10.4f} "
              f"{s['rapporto_cw_div_EMI_finestra_uguale']:9.4f} {debole:12.4f}"
              f"   (n {n} campioni)")

    print("\nVERDETTO:", "coerente: gli integrali del JSON sono ricostruibili "
          "dai CSV committati" if ok else
          "DIVERGENZA: ricontrollare four_way_test.py prima di usare i numeri")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
