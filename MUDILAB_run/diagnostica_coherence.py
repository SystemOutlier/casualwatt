"""Riferimento del ramo `coherence` prima del fix, e superficie di eccezioni reale.

Perche' esiste. La decisione 2 autorizza lo screening dev senza run sul modello,
quindi prima di toccare il tool serve (a) un fermo del comportamento attuale,
rigenerabile, e (b) la lista di cio' che pyAgrum 3.2.1 solleva davvero: il branch
in `tools_corretto.py` catturava `gum.InvalidEvidence`, classe che in questa
versione non esiste (verificato: `hasattr(gum, 'InvalidEvidence')` falso, `dir(gum)`
ha `InvalidArgument`, `NotFound`, `UndefinedElement`). Nel codice pre-fix pero'
`addEvidence` stava fuori dal `try`, quindi su stato sbagliato usciva l'errore nudo
e la clausola non veniva invocata: la forma vecchia e' misurata, non immaginata, in
`verifica_fix_coherence.py`. Cio' che produceva numeri apparentemente validi senza
domanda era un'altra cosa, ed e' il secondo punto: il target dentro le evidenze.

Cosa scrive. `harness/riferimenti/coherence_prima_del_fix.json`: per ogni riga
coherence del dev, la traduzione registrata nella corsa reale, la mappatura
dell'oracolo, l'esito del tool e il motivo. E' il "prima" della tabella
prima/dopo, e non richiede il modello perche' legge i testi gia' registrati.

Uso:  MUDILAB_COPIE=1 python diagnostica_coherence.py [cartella]
"""
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

CART = HERE / "harness" / "risultati" / "b_composta" / "20261101_183106"
OUT = HERE / "harness" / "riferimenti" / "coherence_prima_del_fix.json"

# (nome, variabile, stato) per le prove di eccezione: cosa alza davvero pyAgrum.
PROVE = [
    ("variabile inesistente", "NonCes variable", "True"),
    ("stato inesistente", "Antilock", "Falso"),
    ("evidenza incoerente sulla stessa variabile", "Antilock", "True"),
    ("inferenza su rete carica ma senza evidenze", "Antilock", "True"),
]


def exception_surface():
    """Le classi realmente sollevate, con il messaggio originale accanto.

    Non si deduce dai nomi: si prova. Ogni prova passa per lo stesso percorso del
    ramo `coherence` (`addEvidence` poi `makeInference`), perche' e' li' che il
    contratto va rispettato.
    """
    import pyagrum as gum
    rete = str(HERE / "consegna" / "insurance_grafo.bif")
    esiti = []
    for nome, var, stato in PROVE:
        bn = gum.loadBN(rete)
        ie = gum.LazyPropagation(bn)
        try:
            if nome.startswith("evidenza incoerente"):
                ie.addEvidence(var, "True")
                ie.addEvidence(var, "False")
            elif nome.startswith("inferenza su rete carica"):
                pass
            else:
                ie.addEvidence(var, stato)
            ie.makeInference()
            esiti.append({"prova": nome, "solleva": None})
        except BaseException as e:  # noqa: BLE001 -- lo scopo e' vedere il tipo
            esiti.append({"prova": nome,
                          "solleva": f"{type(e).__module__}.{type(e).__name__}",
                          "in_gum": hasattr(gum, type(e).__name__),
                          "messaggio": str(e)[:180]})
    return esiti


def righe_reference():
    """(riga, traduzione, mappatura attesa, esito del tool) per il dev coherence."""
    argv = sys.argv
    sys.argv = [argv[0]]
    import run_query  # noqa: F401
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools
    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    fuori = []
    for t, g in sorted(gt.items()):
        if g["ramo"] != "coherence" or g["split"] != "dev":
            continue
        p = CART / f"{t}_r1.json"
        d = json.loads(p.read_text(encoding="utf-8"))
        r = d.get("risultato") or {}
        traduzione = r.get("traduzione")
        riga = {"task_id": t,
                "query": g["query"],
                "etichetta_run": r.get("etichetta"),
                "traduzione": traduzione,
                "atteso": {"input": json.loads(g["evidence_json"]),
                           "output": {g["target_variable"]: g["target_state"]}},
                "prob_oracolo": float(g["expected_probability"]),
                "decisione_oracolo": g["expected_decision"],
                "motivo_controllo": (r.get("controllo_traduzione") or {}).get("motivo")}
        if traduzione is None:
            riga["esito_tool"] = "non arrivato al tool"
        else:
            try:
                risposta = tools.cau_inference.func(
                    g["etichetta_attesa"], json.dumps(traduzione), d.get("rete"))
                riga["esito_tool"] = "calcolato"
                riga["testo_risposta"] = str(risposta)[:200]
            except BaseException as e:  # noqa: BLE001
                riga["esito_tool"] = f"{type(e).__name__}"
                riga["testo_errore"] = str(e)[:200]
        # La diagnosi della mappatura: quali chiavi mancano, quali in piu', chi e
        # stato invertito. E' qui che il ramo perde, non nell'inferenza.
        if traduzione:
            avuti_in = {k.lower(): v.lower() for k, v in (traduzione.get("input") or {}).items()}
            attesi_in = {k.lower(): v.lower() for k, v in riga["atteso"]["input"].items()}
            avuti_out = {k.lower(): v.lower() for k, v in (traduzione.get("output") or {}).items()}
            attesi_out = {k.lower(): v.lower() for k, v in riga["atteso"]["output"].items()}
            riga["mappatura"] = {
                "input_mancanti": sorted(set(attesi_in) - set(avuti_in)),
                "input_in_piu": sorted(set(avuti_in) - set(attesi_in)),
                "output_atteso": attesi_out,
                "output_avuto": avuti_out,
                "target_invertito": bool(avuti_out and avuti_out.items() <= attesi_in.items()),
                "esatta": avuti_in == attesi_in and avuti_out == attesi_out}
        fuori.append(riga)
    return fuori


def main():
    cart = sys.argv[1] if len(sys.argv) > 1 else None
    global CART
    if cart:
        CART = Path(cart) if Path(cart).is_absolute() else HERE / cart
    OUT.parent.mkdir(parents=True, exist_ok=True)
    dati = {"cartella_riferimento": CART.name,
            "regola_citazione": "in produzione (gate sulla frase attivo) -- 32/81",
            "exception_surface": exception_surface(),
            "righe": righe_reference()}
    OUT.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"scritto: {OUT.relative_to(HERE)}  ({len(dati['righe'])} righe coherence dev)\n")
    print("--- superficie di eccezione reale (pyAgrum 3.2.1, stesso percorso del ramo)")
    for e in dati["exception_surface"]:
        print(f"  {e['prova']:45s} -> {e['solleva'] or 'nessuna eccezione'}"
              + (f"  [in gum: {e['in_gum']}]" if e["solleva"] else ""))
    print("\n--- mappatura per riga")
    n_esatta = n_invertite = n_manca = 0
    for r in dati["righe"]:
        m = r.get("mappatura") or {}
        if m.get("esatta"):
            n_esatta += 1
        elif m.get("target_invertito"):
            n_invertite += 1
        elif m:
            n_manca += 1
        print(f"  {r['task_id']}  {r['esito_tool']:18s} esatta={m.get('esatta')} "
              f"mancanti={m.get('input_mancanti')} in_piu={m.get('input_in_piu')} "
              f"atteso_out={m.get('output_atteso')} avuto_out={m.get('output_avuto')}")
    tot = len(dati["righe"])
    print(f"\nmappatura esatta {n_esatta}/{tot} | target invertito {n_invertite}/{tot} | "
          f"altro errore di mappatura {n_manca}/{tot}")
    for r in dati["righe"]:
        if r.get("testo_risposta"):
            print(f"  {r['task_id']}: {r['testo_risposta'][:88]}")


if __name__ == "__main__":
    main()
