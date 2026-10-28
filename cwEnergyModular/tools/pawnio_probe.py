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

Modo ``--aba``: costo di osservazione del campionatore PawnIO. La catena
ammette ``pawnio-counter`` solo se il costo dell'osservatore e' misurato, non
dedotto (specifica §3.1.2). Il disegno e' A-B-A su idle puro, con EMI come
strumento in tutte e tre le fasi (una lettura al secondo, identica in ogni
fase, quindi si elide nella differenza):

- **A1** 60 s: nessun campionatore PawnIO.
- **B** 60 s: campionatore PawnIO a 50 ms.
- **A2** 60 s: come A1.

Criteri dichiarati **prima** della misura, e nessuno spostato dopo:

1. livello: passa se |P_B - P_A1| < 1,0 W e |P_B - P_A2| < 1,0 W (la soglia
   di 1,0 W gia' congelata);
2. cadenza: passa se l'intervallo medio del campionatore sta entro il 10% del
   bersaglio di 50 ms (la soglia del 10% gia' congelata);
3. attribuzione: se la deriva |P_A1 - P_A2| non e' minore della differenza
   B-A, l'effetto non e' attribuibile e la prova e' inconclusiva, non
   "costo nullo".

La fase B e' un **limite superiore**: in produzione gira un solo backend, qui
girano insieme il campionatore EMI (1 Hz, strumento) e quello PawnIO (20 Hz,
osservatore). Un costo nullo in questa configurazione implica un costo nullo
anche quando il campionatore PawnIO e' solo.

Uso:
    python cwEnergyModular/tools/pawnio_probe.py --seconds 60 --out out.json
    python cwEnergyModular/tools/pawnio_probe.py --aba 60 --out aba.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.pawnio_backend import METHOD_LABEL, PawnIOMSRBackend  # noqa: E402

TICK_S = 0.05
EMI_TICK_S = 1.0
WARMUP_S = 30.0
PASS_LEVEL_W = 1.0      # soglia congelata
CADENCE_TOL = 0.10      # soglia congelata


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


def _read_emi_pkg(emi):
    t = time.monotonic()
    try:
        domains = emi.read_domains() or {}
        pkg = domains.get("pkg")
        return t, (float(pkg[0]) if pkg is not None else None)
    except Exception:
        return t, None


class _Sampler(threading.Thread):
    """Campionatore PawnIO a cadenza fissa: e' l'osservatore della fase B."""

    def __init__(self, backend, tick=TICK_S):
        super().__init__(daemon=True)
        self.backend = backend
        self.tick = tick
        self.samples = []       # (t_lettura, latenza_s, cum_j)
        self._stop = threading.Event()

    def run(self):
        while not self._stop.is_set():
            t = time.monotonic()
            value = self.backend.read_cumulative_energy_j()
            self.samples.append((t, time.monotonic() - t, value))
            time.sleep(self.tick)

    def stop(self):
        self._stop.set()
        self.join()


def _phase_power(edge0, edge1):
    (t0, j0), (t1, j1) = edge0, edge1
    if None in (t0, j0, t1, j1) or t1 <= t0:
        return None, None, None
    return j1 - j0, t1 - t0, (j1 - j0) / (t1 - t0)


def run_aba(seconds: float) -> dict:
    """Costo di osservazione del campionatore PawnIO, disegno e criteri sopra."""
    out = {
        "method": METHOD_LABEL,
        "mode": "aba",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase_s": seconds,
        "warmup_s": WARMUP_S,
        "criteria": {
            "level_pass_w": PASS_LEVEL_W,
            "cadence_tol": CADENCE_TOL,
            "cadence_target_s": TICK_S,
            "rules": ("livello: |P_B-P_A1|<1.0 W e |P_B-P_A2|<1.0 W; "
                      "cadenza: intervallo medio entro il 10% di 50 ms; "
                      "B limite superiore (in produzione un solo backend)"),
        },
    }
    msr = PawnIOMSRBackend()
    out["probe"] = msr.probe()
    if not msr.available:
        msr.close()
        out["verdict"] = "pawnio non disponibile: " + (msr.reason or "?")
        return out
    emi = _open_emi()
    if emi is None:
        msr.close()
        out["verdict"] = "EMI non disponibile: A-B-A non eseguibile"
        return out

    # assestamento: nessuna delle fasi misurate deve contenere il transitorio
    deadline = time.monotonic() + WARMUP_S
    while time.monotonic() < deadline:
        time.sleep(EMI_TICK_S)

    phases = []
    sampler = None
    for name in ("A1", "B", "A2"):
        edge0 = _read_emi_pkg(emi)
        cpu0 = time.process_time()
        t_start = time.monotonic()
        if name == "B":
            sampler = _Sampler(msr)
            sampler.start()
        ticks = []
        while time.monotonic() < t_start + seconds:
            time.sleep(EMI_TICK_S)
            ticks.append(_read_emi_pkg(emi))
        if sampler is not None:
            sampler.stop()
        cpu1 = time.process_time()
        edge1 = _read_emi_pkg(emi)
        delta_j, window_s, power_w = _phase_power(edge0, edge1)
        phases.append({
            "name": name,
            "emi_j": None if delta_j is None else round(delta_j, 6),
            "window_s": None if window_s is None else round(window_s, 6),
            "power_w": None if power_w is None else round(power_w, 4),
            "emi_ticks": len(ticks),
            "cpu_s": round(cpu1 - cpu0, 4),
        })
        sampler_phase = sampler
        sampler = None
        if sampler_phase is not None:
            values = [s for s in sampler_phase.samples if s[2] is not None]
            gaps = [b[0] - a[0] for a, b in zip(values, values[1:])]
            out["pawnio_sampler"] = {
                "reads": len(sampler_phase.samples),
                "valid": len(values),
                "interval_mean_s": round(statistics.fmean(gaps), 6) if gaps else None,
                "interval_p95_s": (round(sorted(gaps)[int(0.95 * (len(gaps) - 1))], 6)
                                   if gaps else None),
                "latency_p50_us": _percentiles([s[1] for s in sampler_phase.samples]).get("p50"),
                "counter_advanced_j": (round(values[-1][2] - values[0][2], 6)
                                       if len(values) > 1 else None),
            }

    out["phases"] = phases
    by_name = {p["name"]: p for p in phases}
    a1 = by_name["A1"]["power_w"]
    b = by_name["B"]["power_w"]
    a2 = by_name["A2"]["power_w"]
    if None in (a1, b, a2):
        out["level"] = {"available": False,
                        "note": "una fase non ha bordi EMI leggibili"}
        out["verdict"] = "misura incompleta"
    else:
        d1 = b - a1
        d2 = b - a2
        drift = abs(a1 - a2)
        attributable = drift < max(abs(d1), abs(d2))
        level_pass = max(abs(d1), abs(d2)) < PASS_LEVEL_W
        out["level"] = {
            "delta_b_minus_a1_w": round(d1, 4),
            "delta_b_minus_a2_w": round(d2, 4),
            "drift_a1_a2_w": round(drift, 4),
            "attributable": attributable,
            "level_pass": level_pass if attributable else False,
            "note": ("B e' un limite superiore: in produzione gira un solo "
                     "backend, qui EMI (1 Hz, strumento) e PawnIO (20 Hz, "
                     "osservatore) insieme"),
        }
        smp = out.get("pawnio_sampler") or {}
        mean = smp.get("interval_mean_s")
        cadence_pass = (mean is not None
                        and abs(mean - TICK_S) / TICK_S <= CADENCE_TOL)
        out["cadence"] = {
            "target_s": TICK_S,
            "mean_s": mean,
            "pass": cadence_pass,
        }
        if not attributable:
            out["verdict"] = "inconclusivo: la deriva A1-A2 domina la differenza B-A"
        elif level_pass and cadence_pass:
            out["verdict"] = "ok"
        else:
            out["verdict"] = "costo di osservazione sopra la soglia"

    msr.close()
    emi.close()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--aba", type=float, default=None, metavar="SEC",
                    help="A-B-A del costo di osservazione, durata di ogni fase")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.aba is not None:
        data = run_aba(max(args.aba, 10.0))
    else:
        data = run(max(args.seconds, 2.0))
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nscritto {args.out}")
    return 0 if data.get("verdict") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
