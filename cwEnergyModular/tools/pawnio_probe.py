# -*- coding: utf-8 -*-
"""Sonda reale del contatore MSR via PawnIO, con confronto a finestra uguale.

Risponde a tre domande, e le risponde con numeri invece che con l'intenzione:

1. **La sonda del backend passa?** Servizio, HVCI, firma del driver, hash dei
   moduli, unita' del package: ogni controllo con il suo esito e la sua
   ragione (``energy/pawnio_backend.py``).
2. **Il contatore si muove, e quanto costa leggerlo?** Latenza mediana e
   massima della lettura ``ioctl_read_msr``, campionata a 50 ms.
3. **Coincide con EMI nella stessa finestra?** EMI e PawnIO leggono lo stesso
   registro ``MSR_PKG_ENERGY_STATUS``: se il rapporto fra i due delta e' 1
   entro la quantizzazione, l'implementazione e' coerente. **Non** e' una
   validazione della scala assoluta — stesso registro, stessa sorgente — e lo
   strumento non la presenta come tale.

Nessuna stima: se EMI non c'e', la terza sezione si dichiara non eseguibile e
lo strumento esce con il solo verdetto del backend.

Uso:
    python cwEnergyModular/tools/pawnio_probe.py --seconds 60 --out out.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.pawnio_backend import METHOD_LABEL, PawnIOMSRBackend  # noqa: E402

TICK_S = 0.05


def _percentiles(values, pcts=(50, 95, 100)) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    out = {}
    for p in pcts:
        if p >= 100:
            out[f"p{p}"] = ordered[-1]
        else:
            idx = min(len(ordered) - 1,
                      max(0, int(round(p / 100.0 * (len(ordered) - 1)))))
            out[f"p{p}"] = ordered[idx]
    return {k: round(v * 1e6, 1) for k, v in out.items()}   # microsecondi


def _open_emi():
    try:
        from energy.emi_backend import EMICounterBackend
        backend = EMICounterBackend()
        return backend if backend.available else None
    except Exception:
        return None


def run(seconds: float) -> dict:
    out = {
        "method": METHOD_LABEL,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds_requested": seconds,
    }
    t0 = time.monotonic()
    msr = PawnIOMSRBackend()
    out["probe"] = msr.probe()
    out["open_s"] = round(time.monotonic() - t0, 3)
    if not msr.available:
        msr.close()
        out["verdict"] = "pawnio non disponibile: " + (msr.reason or "?")
        return out

    emi = _open_emi()
    out["emi"] = {"available": emi is not None,
                  "notes": list(getattr(emi, "notes", [])) if emi else []}

    lat_msr, lat_emi = [], []
    pairs = []      # (t_emi_before, pkg_j_emi, t_msr_before, cum_j_msr)
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        t_emi = None
        pkg_j = None
        if emi is not None:
            a = time.monotonic()
            try:
                domains = emi.read_domains() or {}
                pkg = domains.get("pkg")
                pkg_j = float(pkg[0]) if pkg is not None else None
            except Exception:
                pkg_j = None
            t_emi = a
            lat_emi.append(time.monotonic() - a)
        b = time.monotonic()
        cum = msr.read_cumulative_energy_j()
        lat_msr.append(time.monotonic() - b)
        if cum is not None:
            pairs.append((t_emi, pkg_j, b, cum))
        time.sleep(TICK_S)

    if len(pairs) < 2:
        out["verdict"] = "buffer insufficiente: meno di due letture"
        msr.close()
        if emi is not None:
            emi.close()
        return out

    first, last = pairs[0], pairs[-1]
    e_msr = last[3] - first[3]
    dt_msr_s = last[2] - first[2]
    out["pawnio"] = {
        "reads": len(pairs),
        "cum_j_first": round(first[3], 6),
        "cum_j_last": round(last[3], 6),
        "delta_j": round(e_msr, 6),
        "window_s": round(dt_msr_s, 6),
        "power_w": round(e_msr / dt_msr_s, 4) if dt_msr_s > 0 else None,
        "counts_first": msr.cumulative_counts,
        "quantum_j": msr.quantum_j,
        "wraps": msr.wraps,
        "resets": msr.resets,
        "latency_us": _percentiles(lat_msr),
    }
    # il contatore EMI e il cumulato PawnIO hanno basi diverse: si confrontano
    # i DELTA sulla stessa coppia di tick, ciascuno sulla propria finestra.
    if emi is not None and first[1] is not None and last[1] is not None:
        e_emi = last[1] - first[1]
        dt_emi_s = (last[0] - first[0]) if (last[0] and first[0]) else 0.0
        out["emi_window"] = {
            "cum_j_first": round(first[1], 6),
            "cum_j_last": round(last[1], 6),
            "delta_j": round(e_emi, 6),
            "window_s": round(dt_emi_s, 6),
            "power_w": (round(e_emi / dt_emi_s, 4)
                        if dt_emi_s > 0 else None),
            "latency_us": _percentiles(lat_emi),
        }
        out["comparison"] = {
            "ratio_msr_over_emi": (round(e_msr / e_emi, 6)
                                   if e_emi else None),
            "rel_diff_pct": (round((e_msr - e_emi) / e_emi * 100.0, 4)
                             if e_emi else None),
            "note": ("stesso registro (MSR_PKG_ENERGY_STATUS 0x611): un "
                     "accordo qui e' coerenza di implementazione, non "
                     "validazione indipendente della scala assoluta"),
        }
    else:
        out["comparison"] = {"available": False,
                            "note": "EMI non disponibile: confronto non eseguibile"}

    msr.close()
    if emi is not None:
        emi.close()
    out["verdict"] = "ok"
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    data = run(max(args.seconds, 2.0))
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nscritto {args.out}")
    return 0 if data.get("verdict") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
