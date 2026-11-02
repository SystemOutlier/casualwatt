"""Verifica del ramo controfattuale di `cau_inference`, senza chiamare un modello.

Tre domande, in ordine di importanza:

1. il ramo si raggiunge dalla pipeline? Il classificatore di `MUDILAB/agents.py`
   istruisce il modello su quattro etichette (`backward_reasoning`,
   `intervention`, `coherence`, `influence`) e `tools.py:63` confronta la stringa
   `'conterfactual'`. Qui si prova la funzione con ogni etichetta che il
   classificatore puo' produrre, piu' le due grafie del controfattuale.
2. se si raggiunge, funziona? Si chiama `cau_inference` e, separatamente,
   `cobound` con gli argomenti corretti, per distinguere un errore del punto di
   chiamata da un errore dentro `cobound`/`g_bin`.
3. con le copie corrette, i tre controfattuali danno gli estremi attesi?

Le due famiglie di moduli stanno in processi diversi (`--gruppo originale` /
`--gruppo corretto`) perche' entrambe fanno `from funtions import cobound` e il
nome del modulo collide. Non tocca Ollama e non scrive niente su disco.

Ogni caso ha l'esito atteso: il codice di uscita e' 1 se anche uno solo non
torna, cosi' la verifica e' un controllo e non una stampa.

Uso:
    python verifica_conterfactual.py --gruppo originale
    python verifica_conterfactual.py --gruppo corretto
"""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# i suoi file originali: accanto a questo script nella cartella di lavoro, o
# dove indica --orig quando lo script gira dalla cartella scompattata
ORIG = HERE.parent / "MUDILAB"
# le copie corrette: nella stessa cartella se e' stata scompattata, altrimenti
# nella sottocartella `consegna` della cartella di lavoro
COPIE = HERE if (HERE / "tools_corretto.py").exists() else HERE / "consegna"

# i tre controfattuali della cella 10 del notebook, con la mappatura di
# ground_truth.csv (task_id CF1..CF3)
CF = (
    ("CF1", "DrivQuality", "Excellent", "RiskAversion", "Cautious"),
    ("CF2", "Accident", "Severe", "Age", "Senior"),
    ("CF3", "Theft", "True", "SocioEcon", "Wealthy"),
)

ETICHETTE = ("backward_reasoning", "intervention", "coherence", "influence",
             "counterfactual", "conterfactual")

# estremi attesi, colonne expected_*_graph di ground_truth.csv (Py = marginale
# del grafo). Il limite inferiore si stampa "0" e non "0.0" perche' `cobound`
# fa max(0, ...) partendo dall'intero: e' un dettaglio del testo, non del valore.
ATTESI_GRAFO = {
    "CF1": "between 0.0827 and 0.2396",
    "CF2": "between 0 and 0.074",
    "CF3": "between 0 and 0.0",
}

esiti = []


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _chiama(funzione, *args, **kwargs):
    """(ok, testo) invece di un'eccezione che ferma la verifica.

    Il testo dell'errore porta l'ultimo frame del modulo chiamato, in forma
    `file.py:riga`: un errore senza il punto in cui nasce non e' un ancoraggio.
    """
    try:
        return True, str(funzione(*args, **kwargs))
    except Exception as e:
        import traceback

        frame = None
        for livello in traceback.extract_tb(e.__traceback__):
            if Path(livello.filename).name != Path(__file__).name:
                frame = livello
        dove = f" [{Path(frame.filename).name}:{frame.lineno}]" if frame else ""
        return False, f"{type(e).__name__}: {e}{dove}"


def _registra(caso: str, ok: bool, testo: str, atteso_ok: bool,
              atteso_testo: str = ""):
    """Verifica l'esito contro l'atteso e prepara la riga di riepilogo."""
    torna = (ok == atteso_ok) and (atteso_testo in testo if atteso_testo else True)
    esiti.append((caso, torna))
    print(f"[{'OK   ' if torna else 'DIVERGE'}] {caso}")
    print(f"          esito: {'risposta' if ok else 'errore'}")
    print(f"          {testo[:400]}")
    if not torna:
        atteso = ("una risposta" if atteso_ok else "un errore")
        if atteso_testo:
            atteso += f" contenente {atteso_testo!r}"
        print(f"          atteso: {atteso}")


def gruppo_originale() -> None:
    # funtions.py legge 'DATI.csv' con un percorso relativo all'import
    sys.path.insert(0, str(ORIG))
    os.chdir(ORIG)
    fu = _load("funtions", ORIG / "funtions.py")
    tools = _load("tools", ORIG / "tools.py")
    cau = getattr(tools.cau_inference, "func", tools.cau_inference)

    import pyagrum as gum

    grafo = gum.loadBN(str(ORIG / "insurance_grafo.bif"))
    percorso = str(ORIG / "insurance_grafo.bif")

    print("== 1. la funzione chiamata con ogni etichetta (query CF1) ==")
    # CF1 chiede un controfattuale: l'output e' DrivQuality=Excellent,
    # l'ingresso e' RiskAversion=Cautious
    features = json.dumps({"input": {"RiskAversion": "Cautious"},
                           "output": {"DrivQuality": "Excellent"}})
    # atteso: quattro etichette del classificatore rispondono con un numero
    # (o un testo, per influence); le due grafie del controfattuale falliscono
    attesi = {
        "backward_reasoning": (True, "0.289"),
        "intervention": (True, "0.24"),
        "coherence": (True, "0.29"),
        "influence": (True, "Look at the grafo"),
        "counterfactual": (False, "UnboundLocalError"),
        "conterfactual": (False, "TypeError"),
    }
    for etichetta in ETICHETTE:
        ok, testo = _chiama(cau, etichetta, features, percorso)
        _registra(f"cau_inference('{etichetta}', CF1)", ok, testo, *attesi[etichetta])

    print()
    print("== 2. cobound con gli argomenti che il ramo avrebbe dovuto passare ==")
    # atteso: nessuno dei tre si calcola, per due motivi distinti
    attesi = {"CF1": (False, "KeyError"), "CF2": (False, "IndexError"),
              "CF3": (False, "KeyError")}
    for cid, y, yv, x, xval in CF:
        ok, testo = _chiama(fu.cobound, y, yv, x, xval, fu.dati, grafo)
        _registra(f"cobound({cid})", ok, testo, *attesi[cid])

    print()
    print("== 3. casi con piu' di due variabili di input (originale) ==")
    tre = {"Age": "Senior", "Mileage": "FiftyThou", "VehicleYear": "Older"}
    uscita = {"output": {"Accident": "Severe"}}
    ok, testo = _chiama(cau, "intervention", json.dumps({"input": tre, **uscita}),
                        percorso)
    _registra("intervention con tre input", ok, testo, False, "UnboundLocalError")
    # nel ramo coherence solo la prima evidenza entra: con tre variabili la
    # risposta deve coincidere con quella della sola prima
    _, una = _chiama(cau, "coherence",
                     json.dumps({"input": {"Age": "Senior"}, **uscita}), percorso)
    ok, tre_ev = _chiama(cau, "coherence",
                         json.dumps({"input": tre, **uscita}), percorso)
    _registra("coherence con tre evidenze = con una sola", ok and tre_ev == una,
              f"una evidenza: {una} | tre evidenze: {tre_ev}", True)

    _domanda_pipeline()


def gruppo_corretto() -> None:
    sys.path.insert(0, str(COPIE))
    os.chdir(COPIE)
    fu = _load("funtions", COPIE / "funtions_corretto.py")
    tools = _load("tools", COPIE / "tools_corretto.py")
    cau = getattr(tools.cau_inference, "func", tools.cau_inference)

    import pyagrum as gum

    grafo = gum.loadBN(str(COPIE / "insurance_grafo.bif"))
    ie = gum.LazyPropagation(grafo)
    ie.makeInference()
    percorso = str(COPIE / "insurance_grafo.bif")

    print("== 3. ramo controfattuale con le copie corrette, Py dal grafo ==")
    # FIX 11: cau_inference passa a cobound la marginale del grafo, quindi i tre
    # riferimenti si calcolano tutti e sono quelli di ground_truth.csv
    attesi = {cid: (True, ATTESI_GRAFO[cid]) for cid in ATTESI_GRAFO}
    for cid, y, yv, x, xval in CF:
        features = json.dumps({"input": {x: xval}, "output": {y: yv}})
        ok, testo = _chiama(cau, "counterfactual", features, percorso)
        _registra(f"counterfactual {cid} (Py grafo)", ok, testo, *attesi[cid])

    print()
    print("== 4. stessa chiamata con la grafia sbagliata dell'etichetta ==")
    features = json.dumps({"input": {"Age": "Senior"},
                           "output": {"Accident": "Severe"}})
    ok, testo = _chiama(cau, "conterfactual", features, percorso)
    _registra("conterfactual CF2", ok, testo, True, ATTESI_GRAFO["CF2"])

    print()
    print("== 5. cobound con Py dalla marginale del grafo (via `py=`) ==")
    # atteso: gli stessi tre estremi, chiamando cobound direttamente
    for cid, y, yv, x, xval in CF:
        etichette = list(grafo.variable(y).labels())
        py = float(ie.posterior(y)[etichette.index(yv)])
        ok, testo = _chiama(fu.cobound, y, yv, x, xval, None, grafo, py=py)
        _registra(f"cobound({cid}, py=grafo)", ok, testo, True, ATTESI_GRAFO[cid])

    print()
    print("== 5b. la variante a file resta calcolabile (py=None, data) ==")
    # e' il confronto che giustifica FIX 11: la Py su sei righe cambia CF2 e non
    # lascia partire CF1 e CF3, il cui nodo di output non e' una colonna
    attesi_file = {"CF1": (False, "non e' in DATI.csv"),
                   "CF2": (True, "between 0.0404 and 0.074"),
                   "CF3": (False, "non e' in DATI.csv")}
    for cid, y, yv, x, xval in CF:
        ok, testo = _chiama(fu.cobound, y, yv, x, xval, fu.dati, grafo)
        _registra(f"cobound({cid}, Py file)", ok, testo, *attesi_file[cid])

    print()
    print("== 6. gli altri rami, sulle copie, per confronto ==")
    tre = {"Age": "Senior", "Mileage": "FiftyThou", "VehicleYear": "Older"}
    for titolo, etichetta, dic, atteso in (
        ("backward_reasoning", "backward_reasoning",
         {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}, "0.212"),
        ("intervention un input", "intervention",
         {"input": {"Age": "Senior"}, "output": {"Accident": "Severe"}}, "0.074"),
        ("intervention tre input", "intervention",
         {"input": tre, "output": {"Accident": "Severe"}}, ""),
        ("coherence tre evidenze", "coherence",
         {"input": tre, "output": {"Accident": "Severe"}}, ""),
    ):
        ok, testo = _chiama(cau, etichetta, json.dumps(dic), percorso)
        _registra(titolo, ok, testo, True, atteso)


def _domanda_pipeline() -> None:
    """Il classificatore puo' produrre 'counterfactual'? Si legge il prompt."""
    sorgente = (ORIG / "agents.py").read_text(encoding="utf-8")
    inizio = sorgente.index("label_inst = (")
    fine = sorgente.index(")\n", sorgente.index("backward_reasoning\\n", inizio))
    blocco = sorgente[inizio:fine]
    presenti = [e for e in ETICHETTE if e in blocco]
    mancanti = [e for e in ETICHETTE if e not in blocco]
    print()
    print("== 7. vocabolario del classificatore (MUDILAB/agents.py, label_inst) ==")
    print(f"          etichette ammesse nel prompt: {', '.join(presenti)}")
    print(f"          assenti dal prompt:           {', '.join(mancanti)}")
    _registra("nessuna grafia del controfattuale fra le etichette ammesse",
              True, f"ammesse: {', '.join(presenti)}", True)


def main() -> int:
    global ORIG
    p = argparse.ArgumentParser()
    p.add_argument("--gruppo", choices=("originale", "corretto"), required=True)
    p.add_argument("--orig", default=None,
                   help="cartella con agents.py, tools.py, funtions.py originali "
                        "(serve solo a --gruppo originale)")
    args = p.parse_args()
    if args.orig:
        ORIG = Path(args.orig).resolve()

    if args.gruppo == "originale":
        gruppo_originale()
    else:
        gruppo_corretto()

    divergenti = [caso for caso, torna in esiti if not torna]
    print()
    print(f"casi: {len(esiti)}, divergenti: {len(divergenti)}")
    for caso in divergenti:
        print(f"  - {caso}")
    return 1 if divergenti else 0


if __name__ == "__main__":
    sys.exit(main())
