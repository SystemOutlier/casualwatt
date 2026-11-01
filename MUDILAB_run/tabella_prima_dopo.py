"""Tabella prima/dopo sulle 81 righe dev, senza run sul modello.

Perche' esiste. La consegna chiede una tabella prima/dopo sull'effetto dei due fix
del 01-11 sul ramo `coherence` (`consegna/tools_corretto.py`, FIX 19 e FIX 20).
`MUDILAB_run/` non e' in git, quindi il "prima" non si puo' riprendere dalla
storia: si prende dagli artefatti della corsa reale 18:31, che sono stati prodotti
dal codice vecchio e contengono la stringa di risposta gia' stampata
(`risultato.numero`). Il "dopo" e' lo stesso testo registrato, ricalcolato col
codice corrente per via di `replay_traduzione.riproduci`, che chiama il tool sulle
traduzioni uscite dagli stessi input del traduttore.

Metro unico per i due lati: la stessa `_confronta` del benchmark e la stessa regola
di citazione primaria congelata (`output=libero`, gate sulla frase attivo), con
`corretta = etichetta_ok AND numero_ok` come d'abitudine. Non e' un metro nuovo
inventato per far tornare il confronto.

Cosa NON fa. Nessun richiamo al modello: i testi del traduttore sono quelli gia'
sul disco. Nessun numero copiato: l'atteso viene da `benchmark.csv`, che e'
rigenerato dalla rete.

Uso:  MUDILAB_COPIE=1 python tabella_prima_dopo.py [cartella]
"""
import csv
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

CART = HERE / "harness" / "risultati" / "b_composta" / "20261101_183106"
OUT_MD = HERE / "harness" / "riferimenti" / "tabella_prima_dopo_20261101.md"
OUT_JSON = HERE / "harness" / "riferimenti" / "tabella_prima_dopo_20261101.json"

REGIME_PRIMARIO = "output=libero"   # la regola congelata: gate sulla frase attivo


def _atteso_da_gt(riga_gt: dict) -> dict:
    """La tupla che vuole `_confronta`, dalle colonne della riga del benchmark."""
    if riga_gt["ramo"] == "counterfactual":
        return {"lower": float(riga_gt["expected_lower"]),
                "upper": float(riga_gt["expected_upper"]), "decisione": ""}
    return {"prob": float(riga_gt["expected_probability"]),
            "decisione": riga_gt["expected_decision"]}


def _classifica_prima(d: dict, r: dict, riga_gt: dict, _confronta, atteso):
    """L'esito COME E' STATO REGISTRATO dal codice vecchio, sulla stessa riga.

    Non una simulazione: `numero` e `errore_variante` sono cio' che quella corsa ha
    gia' scritto su disco. Le categorie sono quelle del replay, cosi' i due lati
    della tabella sono confrontabili senza tradurre un nome nell'altro.
    """
    ev = str(d.get("errore_variante") or "")
    if ev.startswith("ValueError: controllo_traduzione"):
        return "rifiutata", ev[:70]
    if r.get("errore"):
        return "errore", str(r["errore"])[:70]
    etichetta = str(r.get("etichetta") or "").strip().lower()
    if etichetta != riga_gt["etichetta_attesa"]:
        return "etichetta", f"{etichetta} invece di {riga_gt['etichetta_attesa']}"
    if r.get("numero") is None:
        return "senza risposta", ""
    motivo = _confronta(riga_gt["ramo"], str(r["numero"]), atteso)
    return ("corretta" if motivo is None else "numero"), (motivo or "")[:70]


def construi(cartella: Path):
    argv = sys.argv
    sys.argv = [argv[0]]
    import run_query  # noqa: F401  monta `tools`/`agents` sulle copie, fa chdir
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools
    import traduzione_controllata as TC
    import replay_traduzione as R
    from benchmark.genera import _confronta

    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    elaborabili, escluse = R._righe(cartella)

    righe = []
    for d, r, passi, _p in sorted(elaborabili, key=lambda t: t[0]["task_id"]):
        riga_gt = gt[d["task_id"]]
        if riga_gt["split"] != "dev":
            continue
        atteso = _atteso_da_gt(riga_gt)
        prima, motivo_prima = _classifica_prima(d, r, riga_gt, _confronta, atteso)
        dopo, motivo_dopo = R.riproduci(d, r, passi, REGIME_PRIMARIO, gt,
                                       TC, tools, _confronta)
        righe.append({"task_id": d["task_id"], "ramo": riga_gt["ramo"],
                      "prima": prima, "motivo_prima": motivo_prima,
                      "dopo": dopo, "motivo_dopo": motivo_dopo,
                      "cambia": prima != dopo,
                      "traduzione": r.get("traduzione"),
                      "numero_registrato": (str(r["numero"])[:120]
                                            if r.get("numero") is not None else None)})
    return righe, sorted(escluse)


def _markdown(righe, escluse, cartella):
    prima_ok = sum(1 for x in righe if x["prima"] == "corretta")
    dopo_ok = sum(1 for x in righe if x["dopo"] == "corretta")
    L = [
        "# Tabella prima/dopo — dev 81 righe, nessun run sul modello",
        "",
        f"Corsa di riferimento: `{cartella.name}` (variant `{cartella.parent.name}`, "
        "18:31 dell'01-11).",
        f"Regola di citazione: primaria congelata (`{REGIME_PRIMARIO}`: gate che "
        "vuole la frase verbatim nella query).",
        "Metro: `_confronta` di `benchmark/genera.py` con la tolleranza `TOLL`; "
        "`corretta = etichetta_ok AND numero_ok`.",
        "**Prima** = stringa gia' registrata nel JSON della corsa, prodotta dal "
        "codice vecchio. **Dopo** = lo stesso testo del traduttore, ricalcolato "
        "con `consegna/tools_corretto.py` corrente.",
        "",
        f"Totali: corrette **{prima_ok}/{len(righe)}** prima → **{dopo_ok}/{len(righe)}** "
        "dopo.",
        "",
        "## Per ramo",
        "",
        "| ramo | righe | corrette prima | corrette dopo | esiti cambiati |",
        "|---|---|---|---|---|",
    ]
    for ramo in sorted({x["ramo"] for x in righe}):
        g = [x for x in righe if x["ramo"] == ramo]
        L.append(f"| {ramo} | {len(g)} | {sum(1 for x in g if x['prima']=='corretta')} "
                 f"| {sum(1 for x in g if x['dopo']=='corretta')} "
                 f"| {sum(1 for x in g if x['cambia'])} |")
    L += ["", "## Categoria dell'esito, per lato", "",
          f"- prima: {dict(sorted(Counter(x['prima'] for x in righe).items()))}",
          f"- dopo:  {dict(sorted(Counter(x['dopo'] for x in righe).items()))}",
          "", "## Righe che cambiano esito", "",
          "| task | ramo | prima | dopo | motivo (dopo) | traduzione registrata |",
          "|---|---|---|---|---|---|"]
    cambiate = [x for x in righe if x["cambia"]]
    if not cambiate:
        L.append("| _nessuna riga cambia esito_ | | | | | |")
    for x in cambiate:
        L.append(f"| {x['task_id']} | {x['ramo']} | {x['prima']} | {x['dopo']} "
                 f"| {x['motivo_dopo'] or '-'} | `{json.dumps(x['traduzione'], ensure_ascii=False)}` |")
    if not cambiate:
        coerenza = [x for x in righe if x["ramo"] == "coherence"]
        L += ["", "## Perche' non cambia niente, detto con i numeri", "",
              "I due fix stanno dentro il ramo `coherence` del tool. Su questo dev "
              f"le `{len(coerenza)}` righe coherence si dividono cosi':", ""]
        for x in coerenza:
            L.append(f"- {x['task_id']}: {x['prima']} → {x['dopo']}"
                     + (f" ({x['motivo_dopo']})" if x['motivo_dopo'] else ""))
        L += ["",
              "Una riga rifiutata dal validatore non arriva mai al tool, e una riga "
              "che al tool arriva con il target fuori dalle evidenze esegue lo stesso "
              "calcolo di prima: per questo il punteggio non si muove. Che i due fix "
              "non siano codice decorato lo misura `verifica_fix_coherence.py`, che "
              "mette lo stesso input sui tre bracci (file attuale, attuale senza il "
              "controllo sul target, file dello zip del 31-10) e registra: sul "
              "target-dentro-le-evidenze i bracci senza FIX 20 stampano "
              "`probability of 1.0` e `probability of 0.0`, quello attuale esce "
              "dichiarato; sull'evidenza con stato inesistente il codice vecchio "
              "lasciava uscire `OutOfBounds` nudo perche' `addEvidence` era fuori "
              "dal `try`.", ""]
    L += ["", f"Righe senza passo traduttore registrato (non riproducibili, contate a "
          f"parte): {len(escluse)} {' '.join(escluse) or '-'}", ""]
    return "\n".join(L)


if __name__ == "__main__":
    cartella = Path(sys.argv[1]) if len(sys.argv) > 1 else CART
    righe, escluse = construi(cartella)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({"cartella": str(cartella),
                                    "regola": REGIME_PRIMARIO,
                                    "righe": righe,
                                    "escluse": escluse},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    OUT_MD.write_text(_markdown(righe, escluse, cartella), encoding="utf-8")
    print(f"righe={len(righe)} corrette_prima="
          f"{sum(1 for x in righe if x['prima']=='corretta')}"
          f" corrette_dopo={sum(1 for x in righe if x['dopo']=='corretta')}"
          f" cambiano={sum(1 for x in righe if x['cambia'])}"
          f" escluse={escluse}")
    for x in righe:
        if x["cambia"]:
            print(f"  {x['task_id']} [{x['ramo']}] {x['prima']} -> {x['dopo']}"
                  f" | {x['motivo_dopo']}")
    print(f"scritto: {OUT_JSON}\nscritto: {OUT_MD}")
