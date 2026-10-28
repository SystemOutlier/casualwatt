"""Confronto SRUM x EMI a intervalli IDENTICI (per-minuto accoppiato).

Perche': `srum_emi_cross.py` calcola i rapporti per FASE, ma le due sorgenti non
coprono la stessa finestra (load: meter EMI 601,17 s, bucket SRUM 660 s; idle2:
120 s contro 180 s). Un rapporto di fase quindi confronta potenze medie su
intervalli diversi. Questo script ristabilisce il pairing: prende i bucket SRUM
gia' deduppati dal dump v2 e calcola il delta del contatore EMI sulla STESSA
finestra di 60 s (o quella effettiva del bucket).

Input (artefatti del run, NON rigenera e NON rilegge nulla di nuovo):
  experiment_results/srum_emi_cross_<ts>.json   -> utc_start/utc_end per fase
  experiment_results/srum_emi_cross_<ts>.csv    -> righe fase;t_s;emi_pkg_pwh;...
  experiment_results/srum_emi_cross_<ts>_buckets.csv -> righe per minuto

Unita':
  SRUM : EmiEnergyConsumption in millijoule (confermato in srum.py), TimeInMSec
         in millisecondi -> J = raw/1000, W = J / (ms/1000)
  EMI  : energia pWh -> J = raw * 3.6e-9

Limite del run v2: la traccia del meter ha salvato SOLO il dominio PKG
(intestazione `fase;t_s;emi_pkg_pwh;emi_pkg_ts100ns`), quindi il pairing
accoppia PKG; PP0/PP1 restano nel CSV con `emi_J` vuoto.

I campioni EMI arrivano ogni ~6,6 s (non 5,0 s dichiarati: il costo del poll
estende il tick). Il valore del contatore al confine di minuto e' interpolato
linearmente tra i due campioni che lo circondano, per non spostare la finestra
di mezzo tick.

Regola di esclusione dichiarata: il PRIMO e l'ULTIMO minuto accoppiato di ogni
fase sono "di confine" (contengono un cambio di regime) e vengono tenuti separati
dai minuti interni. Motivo: il bucket SRUM e i 60 s di EMI guardano la stessa
finestra ma non la stessa storia, e su un solo minuto la differenza si vede
tutta (misurato: 11:10 = 0,8206 contro 0,9946 medio degli interni).

Uso (da shell normale: legge solo file gia' scritti, non serve Admin):
  python srum_emi_perminute.py [timestamp-run]   # default 20261023_130553
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
RESULTS = BASE / "experiment_results"
PWH_TO_J = 3.6e-9
MJ_TO_J = 1e-3
# dominio accoppiabile: presente sia nei bucket sia nella traccia del meter
PAIR = ("package", "EMI_RAPL_Package0_PKG")
# domnei SRUM senza contatore EMI nel run v2 (nessun confronto per-minuto)
NO_METER = ("EMI_RAPL_Package0_PP0", "EMI_RAPL_Package0_PP1")
DEFAULT_RUN = "20261023_130553"


def load_run(ts: str) -> tuple[dict, list[dict], list[dict]]:
    j = json.loads((RESULTS / f"srum_emi_cross_{ts}.json").read_text(encoding="utf-8"))
    with (RESULTS / f"srum_emi_cross_{ts}.csv").open(encoding="utf-8") as fh:
        emi_rows = list(csv.DictReader(fh, delimiter=";"))
    with (RESULTS / f"srum_emi_cross_{ts}_buckets.csv").open(encoding="utf-8") as fh:
        buck = list(csv.DictReader(fh, delimiter=";"))
    return j, emi_rows, buck


def minute_key(iso: str) -> str:
    """'2026-10-23T11:11:00.4' -> '2026-10-23T11:11:00' (etichetta del bucket)."""
    return iso[:16] + ":00"


def srum_per_minute(buck: list[dict]) -> dict[tuple[str, str], tuple[float, float]]:
    """{(appId, minuto): (joule, millisecondi coperti)} per i domini EMI di SRUM.

    Un minuto puo' essere scritto come righe COMPLEMENTARI (misurato 10:02 ->
    TimeInMSec 26593 + 33399 = 59992): qui le si somma perche' sono lo STESSO
    intervallo, non due minuti.
    """
    agg: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
    for r in buck:
        app = r["appId"]
        if app not in (PAIR[1], *NO_METER):
            continue
        k = (app, minute_key(r["time_stamp_utc"]))
        agg[k][0] += float(r["emi_energy_raw"]) * MJ_TO_J
        agg[k][1] += float(r["time_in_msec"])
    return {k: (v[0], v[1]) for k, v in agg.items()}


def emi_axis(em: list[dict], fase: str, utc_start: str) -> list[tuple[datetime, float]]:
    """Asse dei campioni EMI di una fase in UTC naive (istante, J cumulati).

    t_s e' l'offset di wall-clock dal via fase, `utc_start` il datetime rilevato
    all'inizio: li sommo perche' nei 5 test dell'utente il tempo del contatore
    EMI coincide col wall-clock client al 0,01 s.
    """
    t0 = datetime.fromisoformat(utc_start)
    axis = [(t0 + timedelta(seconds=float(r["t_s"])), float(r["emi_pkg_pwh"]) * PWH_TO_J)
            for r in em if r["fase"] == fase]
    axis.sort()
    return axis


def counter_at(axis: list[tuple[datetime, float]], instant: datetime):
    """Valore cumulato interpolato all'istante, o None se fuori dall'asse."""
    if not axis or instant < axis[0][0] or instant > axis[-1][0]:
        return None
    for (t1, v1), (t2, v2) in zip(axis, axis[1:]):
        if t1 <= instant <= t2:
            span = (t2 - t1).total_seconds()
            if span <= 0:
                return v1
            return v1 + (v2 - v1) * ((instant - t1).total_seconds() / span)
    return axis[-1][1] if instant == axis[-1][0] else None


def analyze_phase(fase: str, j: dict, em: list[dict], sm: dict) -> dict:
    axis = emi_axis(em, fase, j["emi_per_fase"][fase]["utc_start"])
    minuti = sorted({m for (app, m) in sm if app == PAIR[1]})
    # tiene solo i minuti la cui etichetta cade nell'intervallo UTC della fase
    u0 = datetime.fromisoformat(j["emi_per_fase"][fase]["utc_start"])
    u1 = datetime.fromisoformat(j["emi_per_fase"][fase]["utc_end"])
    minuti = [m for m in minuti if u0 <= datetime.fromisoformat(m) <= u1 + timedelta(minutes=1)]
    rows = []
    for m in minuti:
        s_j, s_ms = sm[(PAIR[1], m)]
        e0 = datetime.fromisoformat(m)
        c0, c1 = counter_at(axis, e0), counter_at(axis, e0 + timedelta(minutes=1))
        row = {"fase": fase, "dominio_srum": PAIR[1], "emi_dom": PAIR[0],
               "minuto_utc": m, "srum_J": round(s_j, 4), "srum_ms": s_ms,
               "srum_W": round(s_j / (s_ms / 1000.0), 4),
               "emi_J": None, "emi_s": None, "emi_W": None, "rapporto": None}
        if c0 is not None and c1 is not None and c1 > c0:
            e_j = c1 - c0
            row["emi_J"] = round(e_j, 4)
            row["emi_s"] = 60.0
            row["emi_W"] = round(e_j / 60.0, 4)
            row["rapporto"] = round(row["srum_W"] / row["emi_W"], 4)
        rows.append(row)
    coppie = [r for r in rows if r["emi_J"] is not None]
    val = sorted(r["rapporto"] for r in coppie)
    stat = {}
    if val:
        med = sum(val) / len(val)
        sd = (sum((x - med) ** 2 for x in val) / (len(val) - 1)) ** 0.5 if len(val) > 1 else 0.0
        stat = {"n": len(val), "media": round(med, 4), "sd": round(sd, 4),
                "min": val[0], "max": val[-1],
                "deviazione_massima_da_1": round(max(abs(x - 1.0) for x in val), 4)}
    return {"asse_emi_campioni": len(axis),
            "asse_emi_da": axis[0][0].isoformat() if axis else None,
            "asse_emi_a": axis[-1][0].isoformat() if axis else None,
            "minuti_in_fase": minuti, "righe": rows,
            "coppie_complete": len(coppie), "statistiche": stat}


def main(argv: list[str]) -> int:
    ts = argv[1] if len(argv) > 1 else DEFAULT_RUN
    j, em, buck = load_run(ts)
    sm = srum_per_minute(buck)
    out = {"run": ts,
           "metodo": "delta contatore EMI (interpolato ai confini) sulla stessa "
                     "finestra del bucket SRUM da minuto; potenze = J / secondi propri",
           "unita": {"srum": "mJ -> J (/1000)", "emi": "pWh -> J (x3.6e-9)"},
           "dominio_accoppiato": PAIR[0], "skip": list(NO_METER), "fasi": {}}
    for fase in ("idle", "load", "idle2"):
        blob = analyze_phase(fase, j, em, sm)
        out["fasi"][fase] = blob
        s = blob["statistiche"]
        print(f"[{fase:5s}] minuti={len(blob['minuti_in_fase'])} "
              f"coppie={blob['coppie_complete']} "
              + (f"media={s['media']:.4f} sd={s['sd']:.4f} "
                 f"min={s['min']:.4f} max={s['max']:.4f} maxdev={s['deviazione_massima_da_1']:.4f}"
                 if s else "nessuna coppia"))
        for r in blob["righe"]:
            print("   ", r["minuto_utc"], "srum_W", r["srum_W"],
                  "emi_W", r["emi_W"], "rapporto", r["rapporto"])

    allc = [r for b in out["fasi"].values() for r in b["righe"] if r["emi_J"] is not None]
    load_only = [r for r in allc if r["fase"] == "load"]

    def med(rs):
        return round(sum(r["rapporto"] for r in rs) / len(rs), 4) if rs else None

    # "interni" = non il primo e non l'ultimo minuto accoppiato della fase: sono
    # gli unici due che contengono un cambio di regime (load che parte, carico che
    # finisce), e li' il minuto SRUM e la finestra EMI di 60 s non vedono la STESSA
    # storia termica. Li elenco, non li nascondo.
    interni = []
    for b in out["fasi"].values():
        p = [r for r in b["righe"] if r["emi_J"] is not None]
        b["minuti_di_confine"] = [r["minuto_utc"] for r in (p[:1] + p[-1:])]
        interni += p[1:-1]
    out["riepilogo"] = {
        "coppie_totali": len(allc),
        "rapporto_medio_load": med(load_only),
        "n_load": len(load_only),
        "rapporto_medio_minuti_interni": med(interni),
        "n_minuti_interni": len(interni),
        "deviazione_massima_minuti_interni":
            round(max(abs(r["rapporto"] - 1.0) for r in interni), 4) if interni else None,
        "deviazione_massima_load": round(max(abs(r["rapporto"] - 1.0)
                                             for r in load_only), 4) if load_only else None,
        "rapporti_minuti_interni": sorted(r["rapporto"] for r in interni),
        "esclusi_come_confine": {f: out["fasi"][f]["minuti_di_confine"] for f in out["fasi"]},
    }

    print("riepilogo:", json.dumps(out["riepilogo"], ensure_ascii=False))

    # Differenziale A-B-A e J/token calcolati DALLE DUE sorgenti con le STESSE
    # convenzioni (stesso token count, stesso meter_s), per vedere se il
    # differenziale sopravvive al cambio di sensore.
    e = j["emi_per_fase"]
    s = j["srum_per_fase"]
    meter = e["load"]["emi_meter_s"]["package"]
    tok = j["tokens_load"]
    W_e = {f: e[f]["emi_W"]["package"] for f in ("idle", "load", "idle2")}
    W_s = {f: s[f]["SRUM_W_per_dominio_EMI"]["EMI_RAPL_Package0_PKG"]
           for f in ("idle", "load", "idle2")}
    diff = {}
    for etich, base_fn in (("base_media_A_B", lambda W: (W["idle"] + W["idle2"]) / 2),
                           ("base_solo_B", lambda W: W["idle2"])):
        row = {}
        for nome, W in (("EMI", W_e), ("SRUM", W_s)):
            b = base_fn(W)
            inc = (W["load"] - b) * meter
            row[nome] = {"base_W": round(b, 3), "dP_W": round(W["load"] - b, 3),
                         "incrementale_J": round(inc, 1), "J_per_token": round(inc / tok, 4)}
        row["rapporto_SRUM_div_EMI_J_token"] = round(
            row["SRUM"]["J_per_token"] / row["EMI"]["J_per_token"], 4)
        diff[etich] = row
    out["differenziale_due_sorgenti"] = {"meter_s": meter, "token": tok, **diff}
    print("differenziale:", json.dumps(out["differenziale_due_sorgenti"], ensure_ascii=False))

    (RESULTS / f"srum_emi_perminute_{ts}.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    with (RESULTS / f"srum_emi_perminute_{ts}.csv").open("w", newline="",
                                                          encoding="utf-8") as fh:
        cols = ["fase", "dominio_srum", "emi_dom", "minuto_utc", "srum_J", "srum_ms",
                "srum_W", "emi_J", "emi_s", "emi_W", "rapporto"]
        w = csv.DictWriter(fh, fieldnames=cols, delimiter=";")
        w.writeheader()
        for b in out["fasi"].values():
            for r in b["righe"]:
                w.writerow({k: r[k] for k in cols})
    print(f"scritto srum_emi_perminute_{ts}.json / .csv "
          f"(coppie con EMI interpolato: {len(allc)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
