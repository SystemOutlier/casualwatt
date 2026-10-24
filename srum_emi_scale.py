#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srum_emi_scale.py — SRUM contiene il NOSTRO stesso contatore: test di scala.

Scoperta (misurata 23/10/2026 su `experiment_results/srum_dump_20261023_121718_start.csv`,
29054-34156 righe, un solo header): fra le ~240 righe per minuto il dump SRUM
contiene anche tre "AppId" che AppId non sono:

    EMI_RAPL_Package0_PKG   EMI_RAPL_Package0_PP0   EMI_RAPL_Package0_PP1

con `CPUEnergyConsumption = 0` e `EmiEnergyConsumption == TotalEnergyConsumption`.
Sono i domini EMI (Energy Meter Interface) cosi' come Windows/SRUM li registra
per se': STESSO dominio del record PKG che noi leggiamo con l'IOCTL 0x22400C, ma
da un consumatore diverso e scritto su un archivio diverso. E' la quarta prova
indipendente (dopo HWiNFO e i limiti PL1/PL2) per la scala del package, e arriva
gratis dal SO.

Cosa fa questo script, senza bisogno di nuovi run:
  1. estrae dai dump SRUM le righe dei tre domini con `TimeInMSec` fra 30 e 70 s
     (= bucket da minuto; le altre sono rollup orari o frazioni, escluse e contate);
  2. le converte in watt sotto l'ipotesi di unita' (default: millijoule, perche'
     15.000 mJ / 60 s = 0,25 W per PP1, in linea con gli 0,35 W di EMI);
  3. costruisce la serie PER MINUTO del PKG dal CSV di un four-way (contatore
     cumulativo pWh, finestra allineata ai minuti UTC usando la colonna `wall`);
  4. stampa le due serie affiancate sui minuti in comune e calcola rapporto,
     deviazione e correlazione ai lag -1/0/+1 minuto (la colonna TimeStamp di
     SRUM non dichiara se il bucket e' etichettato a inizio o a fine minuto:
     il confronto ai lag risponde con dati, non con assunzioni).

Uso:
    python srum_emi_scale.py [dump.csv] [four_way.csv]
default: il dump dell'esperimento SRUM x EMI + il four-way 20261023_120830.
"""
from __future__ import annotations

import csv
import datetime
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "experiment_results"
DOMAINS = ("EMI_RAPL_Package0_PKG", "EMI_RAPL_Package0_PP0", "EMI_RAPL_Package0_PP1")
#: un bucket "da minuto" ha TimeInMSec ~ 60 000; fuori da questa finestra i rollup
MINUTE_MS_LO, MINUTE_MS_HI = 30_000, 70_000
MS_PER_J_HYPOTHESIS = {"mJ": 1e-3, "J": 1.0, "uJ": 1e-6}
PWH_TO_J = 3.6e-9


def local_to_utc_naive(iso_local: str) -> datetime.datetime:
    """`wall` del four-way e' ora locale naive -> UTC naive (base di TimeStamp SRUM)."""
    d = datetime.datetime.fromisoformat(iso_local)
    return d.astimezone().astimezone(datetime.timezone.utc).replace(tzinfo=None)


def srum_minutes(dump_path: Path, unit: str = "mJ") -> dict:
    """{dominio: {minuto_inizio_bucket: W}}, + conteggio righe scartate."""
    sys.path.insert(0, str(ROOT))
    from srum import load
    d = load(dump_path)
    k = MS_PER_J_HYPOTHESIS[unit]
    out = {dom: {} for dom in DOMAINS}
    dropped = {"rollup": 0, "frazione": 0, "altro": 0}
    for r in d.rows:
        app = r.get("AppId") or ""
        if app not in DOMAINS:
            continue
        t = d._ts(r)
        ms = d._f(r, "TimeInMSec")
        v = d._f(r, "EmiEnergyConsumption")
        if t is None:
            dropped["altro"] += 1
            continue
        if ms > MINUTE_MS_HI:
            dropped["rollup"] += 1
            continue
        if ms < MINUTE_MS_LO:
            # frazione dello stesso minuto (stacco di stato): accumulala
            out[app][t] = out[app].get(t, 0.0) + (v * k) / (ms / 1000.0)
            continue
        out[app][t] = out[app].get(t, 0.0) + (v * k) / (ms / 1000.0)
    return {"data": out, "dropped": dropped, "righe": sum(len(v) for v in out.values())}


def emi_minutes(csv_path: Path, min_span_s: float = 45.0) -> dict:
    """W per minuto di calendario (UTC) dal contatore cumulativo di un four-way.

    Un minuto e' misurato come `primo campione del minuto m+1 - primo campione
    del minuto m` sul CONTATORE EMI (energia e tempo del meter), cosi' la
    finestra e' ~60 s e coincide con la durata di un bucket SRUM. Minuti con
    span inferiore a `min_span_s` (bordi del run) sono scartati e dichiarati.
    """
    rows = []
    with open(csv_path, encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter=";")
        for r in rd:
            if not r.get("emi_pkg_pwh") or not r.get("wall"):
                continue
            rows.append((local_to_utc_naive(r["wall"]), float(r["emi_pkg_pwh"]),
                         float(r["emi_pkg_ts100ns"]), r.get("fase", "?")))
    rows.sort(key=lambda x: x[0])
    first = {}
    for (t, pwh, ts100, fase) in rows:
        key = t.replace(second=0, microsecond=0)
        if key not in first:
            first[key] = (pwh, ts100, fase, t)
    keys = sorted(first)
    out = {}
    for a, b in zip(keys, keys[1:]):
        pa, pb = first[a], first[b]
        dj = (pb[0] - pa[0]) * PWH_TO_J
        dt = (pb[1] - pa[1]) * 1e-7
        if dt >= min_span_s:
            out[a] = (dj / dt, pa[2])
    return out


def compare(srum: dict, emi: dict, lag_min: int) -> dict:
    """SRUM etichetta il bucket `t`: confrontalo con il minuto EMI `t + lag`."""
    xs, ys = [], []
    _matched = []
    for t, w in srum.items():
        u = t + datetime.timedelta(minutes=lag_min)
        if u in emi:
            xs.append(emi[u][0])
            ys.append(w)
            _matched.append(t)
    if len(xs) < 2:
        return {"n": len(xs)}
    ratio = [y / x for x, y in zip(xs, ys) if x > 0]
    n = len(xs)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sx = statistics.pstdev(xs) or 0.0
    sy = statistics.pstdev(ys) or 0.0
    cov = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / n
    return {
        "n": n,
        "EMI_media_W": round(mx, 2), "SRUM_media_W": round(my, 2),
        "rapporto_media_SRUM_div_EMI": round(statistics.mean(ratio), 4),
        "sd_rapporto": round(statistics.pstdev(ratio), 4),
        "pearson_r": round(cov / (sx * sy), 4) if sx and sy else None,
        "coppie": [(a.strftime("%H:%M"), b.strftime("%H:%M"), round(y, 2), round(x, 2),
                    round(y / x, 3)) for (a, b, x, y) in zip(
                        [t + datetime.timedelta(minutes=lag_min) for t in _matched],
                        _matched, xs, ys)],
    }


def main() -> int:
    dump = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "srum_dump_20261023_121718_start.csv"
    fway = Path(sys.argv[2]) if len(sys.argv) > 2 else OUT / "four_way_20261023_120830.csv"
    for p in (dump, fway):
        if not p.exists():
            print(f"[ERRORE] manca {p}")
            return 2
    print(f"dump SRUM : {dump}\nfour-way  : {fway}")
    for unit in ("mJ", "J", "uJ"):
        s = srum_minutes(dump, unit)
        emi = emi_minutes(fway)
        pkg = s["data"]["EMI_RAPL_Package0_PKG"]
        print(f"\n=== unita' ipotesi: {unit} (righe bucket: {s['righe']}, "
              f"scartate {s['dropped']}) ===")
        print(f"   EMI (four-way) minuti disponibili: {len(emi)}")
        for lag in (-1, 0, 1):
            print(f"    lag {lag:+d}: {compare(pkg, emi, lag)}")
        if unit == "mJ":
            print("\n    minuti in comune (SRUM-PKG vs EMI-PKG, lag migliore) :")
            for lag in (-1, 0, 1):
                res = compare(pkg, emi, lag)
                if not res.get("n"):
                    continue
                print(f"      lag {lag:+d}: n={res['n']} "
                      f"SRUM_media={res.get('SRUM_media_W')} EMI_media={res.get('EMI_media_W')} "
                      f"rapporto={res.get('rapporto_media_SRUM_div_EMI')} "
                      f"(sd {res.get('sd_rapporto')}) r={res.get('pearson_r')}")
                for (sl, el, sw, ew, rr) in res.get("coppie", []):
                    print(f"         SRUM {sl} = {sw:6.2f} W   EMI {el} = {ew:6.2f} W"
                          f"   rapporto={rr}")
        for dom in ("EMI_RAPL_Package0_PP0", "EMI_RAPL_Package0_PP1"):
            print(f"    {dom.split('_')[-1]}: {round(statistics.mean(list(s['data'][dom].values())), 3)} W medio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
