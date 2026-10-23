# -*- coding: utf-8 -*-
"""Cadenza reale del canale EMI: distribuzione completa, non solo min/max.

Domanda posta dalla revisione esterna (rev_metodo.DOCX, 23/10): la cadenza
OSSERVATA coincide con quella DICHIARATA, e il registro EMI cambia valore a
ogni lettura o e' quantizzato? Per il percorso LHM power-integration la
risposta era nota e sfavorevole (dichiarato 0,05 s, reale 0,28-0,34 s).
Per il canale principale `emi-counter` va misurata la distribuzione completa
degli intervalli fra valori distinti e fra timestamp di registro, perche'
la correttezza della finestra differenziale dipende dal fatto che il
contatore sia aggiornato a ogni lettura (nessuna integrazione: il totale
su finestra e' il delta del cumulativo, non una somma di istantanee).

Il delta del cumulativo in joule NON e' convertito qui: le unita' del campo
v0 sono quelle osservate dal probe (pWh secondo la letteratura del canale,
ma la conversione assoluta non e' arbitrata). Questo script risponde solo
alla domanda di CADENZA.

Uso:
    python tools/emi_cadenza_analysis.py                     # analizza i CSV committati
    python tools/emi_cadenza_analysis.py --probe 15          # misura ora (15 s idle + 15 s spin)
"""
from __future__ import annotations

import argparse
import glob
import os
import statistics
import sys
import threading
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS = os.path.join(BASE, os.pardir, "experiment_results")


def _percentiles(vals, ps=(10, 50, 90, 99)):
    if not vals:
        return {}
    s = sorted(vals)
    out = {"min": s[0], "max": s[-1], "n": len(s)}
    for p in ps:
        out[f"p{p}"] = s[min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1))))]
    return out


def analyze_csv(path):
    rows = []
    with open(path, encoding="utf-8-sig") as fh:
        header = fh.readline().rstrip("\n").split(";")
        for line in fh:
            parts = line.rstrip("\n").split(";")
            if len(parts) == len(header):
                rows.append(dict(zip(header, parts)))
    if not rows:
        return None
    required = {"t_mono_s", "fase", "emi_v0", "emi_ts8"}
    if not required.issubset(rows[0].keys()):
        # schema del probe diverso (solo console/10 ms): non interpretabile qui
        return {"file": os.path.basename(path) + " [SCHEMA DIVERSO: "
                + ",".join(sorted(rows[0].keys())[:6]) + "]", "fasi": {}}
    phases = {}
    for phase in sorted({r["fase"] for r in rows}):
        sub = [r for r in rows if r["fase"] == phase]
        t = [float(r["t_mono_s"]) for r in sub]
        v0 = [int(r["emi_v0"]) for r in sub]
        ts = [int(r["emi_ts8"]) for r in sub]
        tick = [b - a for a, b in zip(t, t[1:])]
        # intervalli fra letture che hanno PRODOTTO un valore nuovo del cumulativo
        new_vals = [t[i + 1] - t[i] for i in range(len(t) - 1) if v0[i + 1] != v0[i]]
        # intervalli fra timestamp di registro consecutivi (100 ns -> s)
        ts_delta = [(b - a) / 1e7 for a, b in zip(ts, ts[1:]) if b > a]
        dup_v0 = sum(1 for i in range(len(v0) - 1) if v0[i + 1] == v0[i])
        ts_stall = sum(1 for a, b in zip(ts, ts[1:]) if b <= a)
        phases[phase] = {
            "letture": len(sub),
            "durata_s": t[-1] - t[0],
            "intervallo_letture_s": _percentiles(tick),
            "v0_ripetuti": dup_v0,
            "intervallo_valori_distinti_s": _percentiles(new_vals),
            "ts_ripetuti": ts_stall,
            "intervallo_ts_registro_s": _percentiles(ts_delta),
        }
    return {"file": os.path.basename(path), "fasi": phases}


def probe_live(seconds: float) -> dict:
    sys.path.insert(0, BASE)
    from energy.emi_backend import EMICounterBackend  # noqa: E402

    b = EMICounterBackend()
    b._open()
    if not b.available:
        raise RuntimeError(f"EMI non disponibile: {b.last_error}")
    out = {}
    try:
        for phase in ("idle", "spin_1t"):
            stop = [False]
            th = None
            if phase == "spin_1t":
                def spin():
                    x = 0.0
                    while not stop[0]:
                        x += 1.0
                th = threading.Thread(target=spin, daemon=True)
                th.start()
            samples = []
            t0 = time.monotonic()
            while time.monotonic() - t0 < seconds:
                v = b.read_raw() if hasattr(b, "read_raw") else None
                samples.append((time.monotonic(), v[0] if v else 0, v[1] if v else 0))
                time.sleep(0.05)
            stop[0] = True
            if th:
                th.join(timeout=2)
            t = [s[0] - t0 for s in samples]
            v0 = [s[1] for s in samples]
            ts = [s[2] for s in samples]
            new_vals = [t[i + 1] - t[i] for i in range(len(t) - 1) if v0[i + 1] != v0[i]]
            ts_delta = [(b2 - a2) / 1e7 for a2, b2 in zip(ts, ts[1:]) if b2 > a2]
            out[phase] = {
                "letture": len(t),
                "durata_s": t[-1] - t[0],
                "intervallo_letture_s": _percentiles([b - a for a, b in zip(t, t[1:])]),
                "v0_ripetuti": sum(1 for i in range(len(v0) - 1) if v0[i + 1] == v0[i]),
                "intervallo_valori_distinti_s": _percentiles(new_vals),
                "ts_ripetuti": sum(1 for a2, b2 in zip(ts, ts[1:]) if b2 <= a2),
                "intervallo_ts_registro_s": _percentiles(ts_delta),
            }
    finally:
        b.close()
    return {"file": f"probe_live_{time.strftime('%Y%m%d_%H%M%S')}", "fasi": out}


def fmt(d):
    if not d:
        return "n/d"
    keys = ("min", "p10", "p50", "p90", "p99", "max")
    return " ".join(f"{k}={d[k]:.4f}" for k in keys if k in d) + f" n={d.get('n', 0)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", type=float, default=0.0,
                    help="secondi per fase di una misura live (0 = solo CSV committati)")
    ap.add_argument("--out", default="", help="percorso markdown di destinazione")
    args = ap.parse_args()

    reports = []
    for p in sorted(glob.glob(os.path.join(RESULTS, "emi_50ms_probe_*.csv"))):
        r = analyze_csv(p)
        if r:
            reports.append(r)
    if args.probe > 0:
        reports.append(probe_live(args.probe))

    lines = ["# Cadenza del canale EMI: distribuzione completa", "",
             "Domanda della revisione esterna (rev_metodo.DOCX 23/10): la lettura",
             "cambia valore a ogni campionamento o esistono duplicazioni/quantizzazioni?",
             "Unita' del cumulativo NON convertite (qui interessa il tempo, non i joule).", ""]
    for r in reports:
        lines.append(f"## {r['file']}")
        for phase, d in r["fasi"].items():
            lines.append(f"- **{phase}** letture={d['letture']} durata={d['durata_s']:.1f}s")
            lines.append(f"  - intervallo letture: {fmt(d['intervallo_letture_s'])}")
            lines.append(f"  - v0 identici consecutivi: {d['v0_ripetuti']}")
            lines.append(f"  - intervallo tra valori DISTINTI: {fmt(d['intervallo_valori_distinti_s'])}")
            lines.append(f"  - timestamp registro identici: {d['ts_ripetuti']}")
            lines.append(f"  - intervallo timestamp registro: {fmt(d['intervallo_ts_registro_s'])}")
        lines.append("")
    text = "\n".join(lines)
    out = args.out or os.path.join(RESULTS, "emi_cadenza_distribuzione_20261023.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text.encode("ascii", "replace").decode())
    print("scritto:", out)


if __name__ == "__main__":
    main()
