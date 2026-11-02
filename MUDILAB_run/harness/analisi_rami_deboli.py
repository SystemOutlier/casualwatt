"""Perche' counterfactual e inter sono i rami peggiori dell'held-out misurato.

Analisi offline sui 240 JSON registrati in `risultati_misura/b_composta/
20261102_191401/`, su `risultati_misura/valutazione.json` e su `benchmark.csv`.
Nessun modello, nessuna misura, nessuna riscrittura delle regole: si contano le
decisioni che `traduzione_controllata.valida` ha gia' scritto in
`controllo_traduzione` durante il run. Una reimplementazione del gate qui
approssimerebbe `_citazione_valida` -- che accetta la citazione se nomina *una
parola* CamelCase della variabile, non il nome intero -- e produrrebbe bucket
falsi; e' gia' successo, e i bucket falsi sono il motivo per cui questo file
esiste.

`corrette / n` mette insieme due filtri diversi, e i due rami peggiori cadono su
filtri opposti: la sezione 1 li separa, le sezioni 2-5 guardano il meccanismo, la
sezione 6 retifica la lettura di `etichetta_ok`.
"""

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RUN = ROOT / "risultati_misura" / "b_composta" / "20261102_191401"
BENCH = ROOT / "benchmark" / "benchmark.csv"
VAL = ROOT / "risultati_misura" / "valutazione.json"

RAMI = ("cond_prob", "inter", "coherence", "counterfactual")
ETICHETTA_DEL_RAMO = {"cond_prob": "backward_reasoning", "inter": "intervention",
                      "coherence": "coherence", "counterfactual": "counterfactual"}
STATI_DENARO = {"Thousand", "TenThou", "FiftyThou", "HundredThou", "Million",
                "TwentyThou"}


def carica():
    righe = {r["task_id"]: r for r in csv.DictReader(BENCH.open(encoding="utf-8"))}
    corsi = {}
    for f in sorted(RUN.glob("*.json")):
        if f.name == "riepilogo.json":
            continue
        d = json.load(f.open(encoding="utf-8"))
        if d["task_id"] not in righe:
            continue
        corsi[(d["task_id"], d["ripetizione"])] = d["risultato"]
    evolve = json.load(VAL.open(encoding="utf-8"))["varianti"]["b_composta"]["righe"]
    return righe, corsi, evolve


def main():
    righe, corsi, evolve = carica()
    chiavi_ho = {k for k in corsi if righe[k[0]]["split"] == "held-out"}
    corsi = {k: v for k, v in corsi.items() if k in chiavi_ho}
    evolve_ho = {(r["task_id"], r["ripetizione"]): r for r in evolve
                 if r["split"] == "held-out"}

    # --- 1. i due filtri, separati --------------------------------------------
    print("=" * 74)
    print("1. due filtri, non uno")
    print(f"{'ramo':<14}{'run':>5}{'al tool':>9}{'corrette':>10}{'su 60':>9}"
          f"{'fra chi arriva':>16}")
    for ramo in RAMI:
        ids = {k for k in corsi if righe[k[0]]["ramo"] == ramo}
        al_tool = sum(1 for k in ids if "errore" not in corsi[k])
        corrette = sum(1 for k in ids if evolve_ho[k]["corretta"])
        print(f"{ramo:<14}{len(ids):>5}{al_tool:>9}{corrette:>10}"
              f"{corrette / len(ids):>9.1%}{corrette / al_tool:>16.1%}")

    # --- 2. dove si ferma chi non arriva al tool -------------------------------
    print()
    print("=" * 74)
    print("2. dove si ferma una riga (contate per run; le 3 ripetizioni non sono")
    print("   indipendenti: a temperatura 0 coincidevano su 235 run su 240)")
    for ramo in RAMI:
        morti = {k: v for k, v in corsi.items()
                 if righe[k[0]]["ramo"] == ramo and "errore" in v}
        col_targ = [v for v in morti.values()
                    if (v.get("controllo_traduzione") or {}).get("target") is None]
        col_card = [v for v in morti.values()
                    if (v.get("controllo_traduzione") or {}).get("target") is not None
                    and (v.get("controllo_traduzione") or {}).get("evidenze") is None]
        altri = len(morti) - len(col_targ) - len(col_card)
        print(f"  {ramo}: {len(morti)} run fermati -- {len(col_targ)} sul target, "
              f"{len(col_card)} sulla cardinalita', {altri} altri")
        dettagli = Counter()
        for v in morti.values():
            for s in (v.get("controllo_traduzione") or {}).get("scartate", []):
                dettagli[(s["regola"], s["dettaglio"][:56])] += 1
        for k, n in dettagli.most_common(6):
            print(f"        {n:>3} voci -- {k[0]}: {k[1]}")

    # --- 3. inter: lo stato del grafo e' un'abbreviazione, la query e' prosa ----
    print()
    print("=" * 74)
    print("3. inter")
    for ramo in RAMI:
        denaro = sum(1 for tid in {k[0] for k in corsi if righe[k[0]]["ramo"] == ramo}
                     if righe[tid]["target_state"] in STATI_DENARO)
        n = len({k[0] for k in corsi if righe[k[0]]["ramo"] == ramo})
        print(f"   target con stato-dinaro ({sorted(STATI_DENARO)}): "
              f"{ramo} {denaro}/{n}")
    prose = Counter()
    parafrasi = []
    for (tid, rep), v in corsi.items():
        if righe[tid]["ramo"] != "inter" or "errore" not in v:
            continue
        e = v.get("controllo_traduzione") or {}
        if e.get("target") is None and " non e' uno stato di " in e.get("motivo", ""):
            prose[(e["motivo"].split("output: ")[1].split(" non e' uno stato")[0],
                    e["motivo"].split("stato di ")[1].split(";")[0])] += 1
        for s in e.get("scartate", []):
            if s["regola"] == "citazione" and "non presente" in s["dettaglio"]:
                parafrasi.append((tid, s["variabile"], s["valore"]))
    print("   stati del target scritti in prosa (run):", dict(prose))
    print("   voci d'input con citazione parafrasata (run):",
          dict(Counter(x[1] for x in parafrasi)))
    assenti = Counter()
    for (tid, rep), v in corsi.items():
        e = v.get("controllo_traduzione") or {}
        n = sum(1 for s in e.get("scartate", []) if "assente" in s["dettaglio"])
        if n:
            assenti[(tid, n)] += 1
    print("   voci senza citazione, riga per riga (il bucket da 46 della sezione 2"
          " e' una riga sola x 2 run):", dict(assenti))

    print()
    print("   esito riga per riga (T = fermata sul target, C = fermata sulla")
    print("   cardinalita', . = arrivata al tool; fra parentesi il numero di")
    print("   ripetizioni non concordi con la prima):")
    for ramo in ("inter", "counterfactual"):
        for tid in sorted({k[0] for k in corsi if righe[k[0]]["ramo"] == ramo}):
            esiti = []
            for rep in (1, 2, 3):
                v = corsi.get((tid, rep))
                if v is None:
                    esiti.append("-")
                    continue
                e = v.get("controllo_traduzione") or {}
                if "errore" not in v:
                    esiti.append(".")
                elif e.get("target") is None:
                    esiti.append("T")
                else:
                    esiti.append("C")
            discordanti = sum(1 for x in esiti[1:] if x != esiti[0])
            print(f"      {tid:<6}{''.join(esiti)}"
                  + (f"  ({discordanti} disc.)" if discordanti else ""))

    # --- 4. controfattuale: la domanda giusta o la premessa? -------------------
    print()
    print("=" * 74)
    print("4. counterfactual: cosa calcola chi supera il gate")
    superstiti = {k: v for k, v in corsi.items()
                  if righe[k[0]]["ramo"] == "counterfactual" and "errore" not in v}
    classificazione = Counter()
    for (tid, rep), v in superstiti.items():
        e = v.get("controllo_traduzione") or {}
        (var, stato), = e["target"].items()
        atteso = (righe[tid]["target_variable"], righe[tid]["target_state"])
        premessa_var = righe[tid]["intervention_json"] and json.loads(
            righe[tid]["intervention_json"])
        if (var, stato) == atteso:
            classificazione["target = la domanda"] += 1
        elif premessa_var and var == next(iter(premessa_var)):
            classificazione[f"target = la variabile manipolata "
                            f"({var})"] += 1
        else:
            classificazione[f"target = un altra variabile ({var})"] += 1
    for k, n in classificazione.most_common():
        print(f"   {n:>3} run: {k}")
    divergenze = []
    for k, v in superstiti.items():
        preso = (v.get("controllo_traduzione") or {}).get("target") == {
            righe[k[0]]["target_variable"]: righe[k[0]]["target_state"]}
        if preso != evolve_ho[k]["corretta"]:
            divergenze.append(k)
    print(f"   fra i superstiti, `corretta` e 'target = la domanda della riga' "
          f"coincidono: {not divergenze} (diversi: {divergenze})")
    print("   Joule per categoria di run (il numero che esce da `valutazione.json`):")
    for ramo in ("counterfactual", "inter", "cond_prob", "coherence"):
        chiavi = [k for k in corsi if righe[k[0]]["ramo"] == ramo]
        bucket = defaultdict(list)
        for k in chiavi:
            e = corsi[k].get("controllo_traduzione") or {}
            if "errore" in corsi[k]:
                cat = "fermata al gate"
            elif e.get("target") == {righe[k[0]]["target_variable"]:
                                      righe[k[0]]["target_state"]}:
                cat = "domanda giusta"
            else:
                cat = "domanda sbagliata"
            bucket[cat].append(evolve_ho[k]["energia_j"])
        riga = "  ".join(f"{c}: {sum(v) / len(v):7.1f} J/run x{len(v):>2}"
                         for c, v in sorted(bucket.items()))
        print(f"      {ramo:<15}{riga}")

    # --- 5. forma della query --------------------------------------------------
    print()
    print("=" * 74)
    print("5. forma della query e cosa chiede il gate")
    for ramo in RAMI:
        tid = sorted({k[0] for k in corsi if righe[k[0]]["ramo"] == ramo})[0]
        r = righe[tid]
        print(f"   {ramo} ({tid}): {r['query'][:118]}...")
        print(f"        evidence={r['evidence_json'] or '{}'} "
              f"intervention={r['intervention_json'] or '{}'} "
              f"target={r['target_variable']}={r['target_state']}")

    # --- 6. `etichetta_ok` non misura il classificatore -------------------------
    print()
    print("=" * 74)
    print("6. etichetta_ok")
    grezzo_ok = 0
    for (tid, rep), v in corsi.items():
        passo = [s for s in v.get("steps", []) if s.get("step") == "classificator"]
        if passo and ETICHETTA_DEL_RAMO[righe[tid]["ramo"]] in passo[0].get("text", ""):
            grezzo_ok += 1
    print(f"   passi `classificator` con l'etichetta attesa nel testo: "
          f"{grezzo_ok}/{len(corsi)}")
    print(f"   JSON senza la chiave `etichetta` (percorso d'errore di "
          f"run_orchestrato.py): {sum(1 for v in corsi.values() if 'etichetta' not in v)}")
    per_ramo_ok = defaultdict(int)
    for r in evolve:
        if r["split"] == "held-out" and r["etichetta_ok"]:
            per_ramo_ok[r["ramo"]] += 1
    print(f"   `etichetta_ok` aggregata per ramo: {dict(per_ramo_ok)}")


if __name__ == "__main__":
    main()
