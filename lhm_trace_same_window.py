#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lhm_trace_same_window.py — analisi offline di una trace `lhm_emi_trace_*.csv`
a FINESTRA UGUALE, cioe' con lo stesso metodo dichiarato in
`experiment_results/four_way_finestra_uguale_20261023_analisi.md`.

Perche' esiste: la trace produce due serie che NON hanno la stessa risoluzione
(LHM arriva dal thread power-integration, ~0,30 s misurato; il tick della
trace e' 0,25 s) e non ha bordi di fase allineati ai campioni LHM. Confrontare
il campione ISTANTANEO LHM con la media EMI sull'intervallo intero lascia
l'artefatto che il 23/10 ha fatto sembrare i differenziali LHM divergenti.
Qui le due sorgenti vengono portate sulla STESSA finestra di fase.

Metodo, per fase:
  - La finestra e' fissata da DUE RIGHE della trace (prima e ultima della
    fase): la stessa riga da il tempo del sensore LHM e il valore del
    contatore EMI, quindi non serve allineare orologi diversi.
  - LHM: integrale trapezoidale dei campioni (t, W) della fase, con i bordi
    interpolati sull'asse LHM (regola identica a `four_way_test.integrate_j`).
  - EMI: delta del contatore cumulativo PKG (record a offset 0, pWh) fra le
    due righe, diviso per il delta del SUO timestamp (unita' 100 ns).
  - Il rapporto e' per watt sulla stessa finestra: la durata si cancella, e
    il residuo di freschezza del campione LHM (thread ~0,30 s) e' simmetrico
    sui due bordi.

Uso:
  C:\\...\\pythoncore-3.14-64\\python.exe lhm_trace_same_window.py \
      experiment_results/lhm_emi_trace_20261023_154628.csv

ATTENZIONE SUI CANALI LETTI (pkg, pp0): il record EMI espone piu' domini, ma
PP0 (core) e PP1 (iGPU) stanno DENTRO PKG, non accanto (Beyer & Wendler 2020,
LNCS 12079; e rapporto PP0/PKG misurato 0,51 a riposo contro 0,84 sotto carico
nel probe emi_50ms_probe.py del 23/10). Le serie di questo file vanno lette
UNA ALLA VOLTA contro la propria controparte LHM: mai somare PP0 e PP1 per
ricostruire il package, e mai trattare DRAM come additivo (su questo host vale
0). Il confine dichiarato dal metodo e' il package.
"""
from __future__ import annotations

import bisect
import csv
import statistics
import sys
from pathlib import Path

PWH_TO_J = 3.6e-9          # picoWatt-ora -> joule
TS100NS_TO_S = 1e-7


def read(path: Path):
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                lw = float(r["lhm_w"]) if r["lhm_w"] not in ("", None) else None
                lt = float(r["lhm_t"]) if r["lhm_t"] not in ("", None) else None
                rows.append({"t_trace": float(r["t_mono_s"]), "fase": r["fase"],
                             "lhm_t": lt, "lhm_w": lw,
                             "pkg": int(r["emi_v0"]), "pkg_ts": int(r["emi_ts8"]),
                             "pp0": int(r["emi_v32"]), "pp0_ts": int(r["emi_ts40"])})
            except (KeyError, ValueError):
                continue
    return rows


def interp(pairs, t):
    """Valore piecewise-lineare di [(x, y)] in t, o None fuori dall'asse."""
    pts = [(x, y) for (x, y) in pairs if x is not None and y is not None]
    if not pts:
        return None
    lo, hi = pts[0][0], pts[-1][0]
    t = min(max(t, lo), hi)
    xs = [p[0] for p in pts]
    i = bisect.bisect_left(xs, t)
    if i == 0:
        return pts[0][1]
    if i >= len(pts):
        return pts[-1][1]
    (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * (t - x0) / (x1 - x0)


def trapezoid_j(pts):
    """Joule trapezoidali su [(t_s, W)]; richiede asse coperto."""
    e = 0.0
    for (t0, w0), (t1, w1) in zip(pts, pts[1:]):
        e += (w0 + w1) / 2.0 * (t1 - t0)
    return e, pts[-1][0] - pts[0][0]


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else
                "experiment_results/lhm_emi_trace_20261023_154628.csv")
    rows = read(path)
    if not rows:
        print("trace vuota o formato non riconosciuto")
        return 1
    print(f"{path.name}: {len(rows)} righe, "
          f"tick mediano {statistics.median([b['t_trace'] - a['t_trace'] for a, b in zip(rows, rows[1:])]):.3f} s")
    fasi = []
    for r in rows:
        if not fasi or fasi[-1][0] != r["fase"]:
            fasi.append((r["fase"], []))
        fasi[-1][1].append(r)

    print(f"\n{'fase':7s}{'n':>5}{'LHM_W':>9}{'EMI_W':>9}{'ratio':>8}"
          f"{'LHM_J':>10}{'EMI_J':>10}{'dt_LHM':>8}{'dt_EMI':>8}")
    out = []
    for fase, fr in fasi:
        if len(fr) < 3:
            continue
        # La finestra e' definita da DUE RIGHE della trace (prima e ultima
        # della fase), non da orologi diversi: la stessa riga fornisce il
        # timestamp del sensore LHM E il contatore EMI. L'unico disallineamento
        # residuo e' la freschezza del campione LHM (thread ~0,30 s) ed e' la
        # stessa entita' su entrambi i bordi, quindi su 40 s di fase pesa
        # frazioni di punto percentuale.
        a, b = fr[0], fr[-1]
        if a["lhm_t"] is None or b["lhm_t"] is None:
            continue
        t0, t1 = a["lhm_t"], b["lhm_t"]
        lpts = sorted({(round(r["lhm_t"], 4), r["lhm_w"]) for r in fr
                       if r["lhm_w"] is not None and r["lhm_t"] is not None
                       and t0 <= r["lhm_t"] <= t1})
        if len(lpts) < 2 or t1 <= t0:
            continue
        # ai bordi della finestra il sensore puo' non avere il campione ESATTO:
        # si interpola sull'asse LHM (stesso metodo del four-way)
        w0 = interp(lpts, t0)
        w1 = interp(lpts, t1)
        if w0 is None or w1 is None:
            continue
        inner = [(t, w) for (t, w) in lpts if t0 < t < t1]
        ej_lhm, s_lhm = trapezoid_j([(t0, w0)] + inner + [(t1, w1)])
        s_emi = (b["pkg_ts"] - a["pkg_ts"]) * TS100NS_TO_S
        e_emi = (b["pkg"] - a["pkg"]) * PWH_TO_J
        if s_emi <= 0 or s_lhm <= 0 or e_emi <= 0:
            print(f"{fase:7s} contatore/tempo EMI non monotono in fase")
            continue
        wl, we = ej_lhm / s_lhm, e_emi / s_emi
        out.append({"fase": fase, "n_lhm": len(lpts), "n_emi": len(fr),
                    "lhm_J": round(ej_lhm, 2), "lhm_s": round(s_lhm, 3),
                    "lhm_W": round(wl, 3),
                    "emi_J": round(e_emi, 2), "emi_s": round(s_emi, 3),
                    "emi_W": round(we, 3),
                    "rapporto_LHM_div_EMI": round(wl / we, 4) if we else None})
        print(f"{fase:7s}{len(lpts):>5}{wl:>9.2f}{we:>9.2f}{wl/we:>8.4f}"
              f"{ej_lhm:>10.1f}{e_emi:>10.1f}{s_lhm:>8.2f}{s_emi:>8.2f}")

    # differenziale della fase load, base = media delle due idle
    if len(out) >= 3:
        a, b = out[0], out[1]
        c = out[3] if len(out) >= 4 else out[2]
        base_W = (a["emi_W"] + c["emi_W"]) / 2
        d_emi = b["emi_J"] - base_W * b["emi_s"]
        base_l = (a["lhm_W"] + c["lhm_W"]) / 2
        d_lhm = b["lhm_J"] - base_l * b["lhm_s"]
        print(f"\ndifferenziale della fase load (base = media delle due idle, "
              f"a finestra uguale):")
        print(f"  EMI  {d_emi:8.1f} J   LHM {d_lhm:8.1f} J   "
              f"rapporto LHM/EMI = {d_lhm/d_emi:.4f}")
        print(f"  offset sugli assoluti (base): LHM - EMI = "
              f"{base_l - base_W:+.2f} W")

    dst = path.with_name(path.stem + "_stessa_finestra.json")
    dst.write_text(__import__("json").dumps(out, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print(f"\n[OK] {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
