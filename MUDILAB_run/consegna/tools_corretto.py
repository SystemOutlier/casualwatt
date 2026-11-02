# =============================================================================
# il codice non corretto resta commentato, la correzione sta sotto e ogni
# blocco dice perche'.
# =============================================================================
import ast
import json
import os

import pyagrum as gum
from tavily import TavilyClient
import pandas as pd
import pyagrum.causal as csl
from agent_framework._tools import tool
from funtions import node_descr
from typing import Optional
# --- originale: import pesanti mai usati (zero occorrenze di dice_ml, helpers,
#     torch e delle classi sklearn nel resto del file). Servivano a un esperimento
#     DiCE che non e' in questo modulo, e costringevano a installare dice_ml,
#     torch e scikit-learn solo per importare il file. Misurato il 31-10-2026 con
#     python 3.14: senza dice_ml l'import si ferma prima di definire cau_inference.
# import dice_ml
# from dice_ml.utils import helpers  # helper functions
# import torch
# from sklearn.compose import ColumnTransformer
# from sklearn.model_selection import train_test_split
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import StandardScaler, OrdinalEncoder
# from sklearn.ensemble import RandomForestClassifier
from funtions import cobound
from pathlib import Path  # aggiunto per fare percorso generico

# FIX: percorsi assoluti rispetto a questo file. Con i percorsi relativi
#      ('DATI.csv') il comportamento dipende dalla CWD da cui parte lo script.
BASE_DIR = Path(__file__).resolve().parent
GRAPH_PATH = BASE_DIR / "insurance_grafo.bif"
DATA_PATH = BASE_DIR / "DATI.csv"


# --- originale: nessun default e nessun controllo di esistenza ---
# @tool
# def read_graph(path: str):
#     grafo = gum.loadBN(path)
#     archi = grafo.arcs()
#     lista = ''
#     for i in grafo.nodes():
#         lista = lista + f', {i} {grafo.variable(i).name()}'
#     arc = ''
#     for a in archi:
#         arc = arc + f'{a}'
#     res = f'Nodi: {lista} \n Archi:{arc}'
#     return res
# FIX 1: `path` con default None. Senza default l'agente deve inventare un
#        percorso, e con None gum.loadBN alza un I/O error sul percorso (C:/Users/Samsung/...)
# FIX 2: se il file non c'e', un FileNotFoundError che dice quale percorso.
# FIX 9: il modello scrive spesso path="None" (la parola, come stringa): e'
#        truthy, quindi saltava il default e cercava un file chiamato None.
#        Misurato il 29-10-2026: read_graph("None") -> FileNotFoundError,
#        read_graph(None) -> grafo. La parola non e' un percorso: si legge
#        come assenza e vale il default.
def _path_or_default(path: Optional[str]) -> Optional[str]:
    """Tratta 'None'/'null' (stringhe) come assenza di percorso."""
    if path is None:
        return None
    text = str(path).strip()
    if text.lower() in ("", "none", "null", "nonetype", "nan"):
        return None
    return text


@tool
def read_graph(path: Optional[str] = None) -> str:
    """Restituisce nodi e archi del grafo di assicurazione."""
    resolved = Path(_path_or_default(path)) if _path_or_default(path) else GRAPH_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"read_graph: grafo non trovato in {resolved}")

    grafo = gum.loadBN(str(resolved))
    archi = grafo.arcs()
    lista = ''
    for i in grafo.nodes():
        lista = lista + f', {i} {grafo.variable(i).name()}'
    arc = ''
    for a in archi:
        arc = arc + f'{a}'
    res = f'Nodi: {lista} \n Archi:{arc}'
    return res


# --- originale: metodo chiamato sulla classe, domini come URL ---
# @tool
# def web_search(query:str) -> str:
#     """Web search Agent"""
#     return TavilyClient.search(query, topic = 'general', include_domains=['https://europa.eu/...'], language= 'en' )
# FIX 1: TavilyClient.search e' un metodo di istanza: prima si costruisce il
#        client, poi si chiama .search(). Chiamato sulla classe solleva
#        TypeError (argomento self mancante).
# FIX 2: include_domains vuole nomi di host ('europa.eu'), non URL completi:
#        con gli URL il filtro non seleziona nulla.
# FIX 3: senza TAVILY_API_KEY il client fallisce in modo opaco: messaggio esplicito.
# FIX 4: la risposta e' un dict e la funzione e' dichiarata -> str: si serializza.
@tool
def web_search(query: str) -> str:
    """Web search Agent"""
    api_key = os.getenv("TAVILY_API_KEY")    #legge una variabile d'ambiente: la chiave si mette nell'ambiente del processo
    if not api_key:
        raise RuntimeError("web_search: TAVILY_API_KEY non impostata nell'ambiente")
    client = TavilyClient(api_key=api_key)
    res = client.search(
        query,
        topic='general',
        include_domains=[
            'europa.eu',
            'moneygeek.com',
            'naic.org',
            'geico.com',
        ],
        language='en',
    )
    return json.dumps(res, ensure_ascii=False)


def _load_data():
    """Legge DATI.csv solo quando serve (prima si leggeva a ogni chiamata).

    Non e' piu' chiamata da nessun ramo: dopo FIX 11 la Py degli estremi viene
    dal grafo. Resta per confronto con la variante a file, che
    verifica_conterfactual.py usa per mostrare la differenza.
    """
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"cau_inference: DATI.csv non trovato in {DATA_PATH}")
    return pd.read_csv(DATA_PATH)


# --- originale: eval() sul testo del modello e nessuna validazione ---
# def _parse(features):
#     dict = eval(features)
# FIX 1: eval() esegue codice arbitrario: il testo arriva da un LLM, quindi e'
#        input non fidato. Si prova json.loads e poi ast.literal_eval, che
#        accettano solo letterali.
# FIX 2: se il testo non e' un dizionario si alza un errore che riporta il testo,
#        invece di un TypeError a valle su 'str' object has no attribute 'keys'.
def _parse_features(features):
    """Trasforma la risposta del traduttore in un dizionario, senza eval()."""
    if isinstance(features, dict):
        return features
    if not isinstance(features, str):
        raise TypeError(f"features deve essere un dizionario o il suo testo, non {type(features).__name__}")

    text = features.strip()
    # i modelli piccoli incorniciano il JSON con ```json ... ``` : si toglie
    # l'involucro prima di provare a leggerlo.
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text[:4].lower() == "json":
            text = text[4:].strip()
    # FIX 10: llama3.2:3b ha scritto il dizionario con virgolette tipografiche
    #         (\u201C \u201D), che ne' json.loads ne' literal_eval accettano.
    #         La struttura era quella giusta: si normalizzano prima di leggere.
    #         Misurato il 29-10-2026: features = '{\u201Cinput\u201D: ...}' ->
    #         ValueError, mentre la stessa stringa con " si legge.
    text = (text.replace("\u201c", '"').replace("\u201d", '"')
                .replace("\u2018", "'").replace("\u2019", "'"))
    for parser in (json.loads, ast.literal_eval):
        try:
            data = parser(text)
        except (ValueError, SyntaxError):
            continue
        if isinstance(data, dict):
            return data
    raise ValueError(f"features non e' un dizionario leggibile: {text[:200]!r}")


def _split_query(dic, grafo):
    """Estrae (evidenza, variabile di output, valore atteso) e valida la forma.

    FIX: il traduttore puo' restituire un output scalare (osservato: "output":
    "Not necessary") o una variabile che non esiste nel grafo. Qui l'errore e'
    esplicito, e le voci con valore 'Not necessary' non diventano evidenza
    (prima finivano in setEvidence e pyAgrum alzava InvalidEvidence).
    """
    if not isinstance(dic.get("input"), dict) or not isinstance(dic.get("output"), dict):
        raise ValueError(
            "la risposta del traduttore deve avere 'input' e 'output' come dizionari: "
            f"{dic!r}"
        )

    output = dic["output"]
    if len(output) != 1:
        raise ValueError(f"'output' deve avere esattamente una chiave, trovate {len(output)}: {output!r}")
    out, out_v = next(iter(output.items()))

    evidence = {
        k: v for k, v in dic["input"].items()
        if str(v).strip().lower() != "not necessary"
    }

    for name in [out, *evidence]:
        if name not in grafo.names():
            raise KeyError(f"variabile {name!r} assente dal grafo")

    return evidence, out, out_v


def _valida_stati(grafo, evidence):
    """Ogni valore dell'evidenza deve essere uno stato ammesso dalla sua variabile.

    FIX 8: senza questo controllo e' pyAgrum ad alzare OutOfBounds dentro
    setEvidence, con un messaggio che nomina l'etichetta ma non la voce della
    query che l'ha prodotta. Osservato sulle righe di DATI.csv con Accident
    vuoto (arriva come 'nan') e con Age='Young': entrambi i lati si fermano con
    lo stesso OutOfBounds, quindi l'errore e' corretto ma muto sull'origine.
    """
    for nome, valore in evidence.items():
        stati = list(grafo.variable(nome).labels())
        if valore not in stati:
            raise ValueError(
                f"{nome}={valore!r} non e' uno stato ammesso da {nome}; stati: {stati}"
            )


# --- originale: rami con variabili non definite, refuso, argomenti invertiti ---
# @tool
# def cau_inference(label: str, features: str, path: Optional[str], name: Optional[str] = None, surname: Optional[str] = None):
#     #if path is None:
#     #    path = "C:/Users/Samsung/Documents/DOTTORATO/GitHub/IPMU/IPMU/Journal/insurance_grafo.bif"
#     BASE_DIR = Path(__file__).resolve().parent
#     if path is None:
#         path = str(BASE_DIR / "insurance_grafo.bif")
#     grafo = gum.loadBN(path)
#     data = pd.read_csv('DATI.csv')
#     ie = gum.LazyPropagation(grafo)
#     dict = eval(features)
#     input_ = dict['input']
#     output = dict['output']
#     out = list(output.keys())[0]
#     out_v = list(output.values())[0]
#     if (label == 'backward_reasoning'):
#         ... per i, state in enumerate(var.labels()): if state == out_v: answer = ...
#     elif(label == 'conterfactual'):
#         answer = cobound(out, out_v, input_, list(input_.values())[0], data, grafo)
#     elif label == 'intervention':
#         ...
#         if len(input_.keys()) == 1:      # valido: un int, si confronta
#         elif len(input_.keys()) == 2:    # valido, ma con 3+ input nessun ramo
#                                          # assegna 'formula'
#         ...
#     elif label == 'coherence':
#         ie.addEvidence(list(input_.keys())[0], list(input_.values())[0])
#         if list(input_.keys()) == 2:     # lista confrontata con un intero
#         elif list(input_.keys()) == 3:
#     ...
#     return answer
#
# FIX 1: `eval` sostituito da _parse_features; la lettura di DATI.csv e' pigra
#        (dopo FIX 11 nessun ramo la usa: il file serve solo all'import di
#        funtions, per gli elenchi dei nomi).
# FIX 2: 'conterfactual' e' un refuso: l'etichetta vera e' 'counterfactual'.
#        Accettata anche la grafia sbagliata, per non rompere i prompt esistenti.
# FIX 3: cobound vuole (y, yval, x, xval, data, graph): il nome della variabile,
#        non il dizionario. Prima il terzo argomento era `input_`.
# FIX 4: con tre o piu' variabili di input ne' `== 1` ne' `== 2` e' vero, quindi
#        `formula` restava non assegnata e `if formula is None` alzava
#        UnboundLocalError (verificato: tools.py:80). Con una o due variabili il
#        ramo funzionava. Ora una sola chiamata, con doing = tutte le variabili
#        di input (una o piu'). Nota: `len(...)` restituisce un intero, quindi il
#        confronto con 1 e 2 e' corretto; era sbagliata la copertura dei casi.
# FIX 5: `list(input_.keys()) == 2` confronta una lista con un intero: sempre
#        falso, quindi solo la prima evidenza entrava. Ora un ciclo su tutte.
# FIX 6: se l'etichetta non e' nessuna di quelle previste si alza ValueError,
#        invece di restituire una `answer` non definita.
# FIX 7: `values` di causalImpact affetta il tensore anche sulla variabile
#        `doing` (verificato su pyagrum 3.2.1), quindi {variabile: valore} da'
#        P(out | do(variabile = valore)). Senza slicing il tensore ha due assi
#        e impact[i] mescolava gli assi.
# FIX 8: i valori dell'evidenza sono controllati contro gli stati ammessi dalla
#        variabile (_valida_stati), non solo i nomi. Prima era pyAgrum a
#        fermarsi con OutOfBounds su un'etichetta sconosciuta: errore corretto
#        ma senza la voce della query che l'aveva prodotta. Il ramo `influence`
#        non fa inferenza e resta com'era.
# FIX 9: come in read_graph, path="None" (stringa) vale come assenza: nel run
#        con smollm2:1.7b il modello ha chiamato il tool con path="None" e
#        l'inferenza si e' fermata su un file inesistente pur essendo il grafo
#        accanto al modulo.
# FIX 10 (dentro _parse_features): virgolette tipografiche normalizzate prima
#        di json.loads/literal_eval; senza, llama3.2:3b produceva ValueError.
# FIX 11: la Py degli estremi controfattuali viene dal giunto del grafo, non da
#        DATI.csv. `cobound` la prendeva dal file, ma le altre quattro
#        quantita' (PYx, PYnox, p_xy/p_noxy e Pxny/Pnxy) vengono dal grafo, e
#        Py e' la marginale di quello stesso giunto: non e' un parametro
#        libero. Il file ha 6 righe e manca di 10 variabili del grafo, fra cui
#        DrivQuality e Theft, cioe' l'output di due delle tre query
#        controfattuali. Stimata su 6 righe la PNS vera cade fuori
#        dall'intervallo nel 25,8% dei modelli e l'intervallo si rovescia nel
#        4,6%; con la marginale del giunto, 0 su 500 (verifica_py.py).
@tool
def cau_inference(label: str, features: str, path: Optional[str] = None,
                  name: Optional[str] = None, surname: Optional[str] = None):
    """Inferenza esatta sul grafo: il ramo dipende dall'etichetta del classificatore."""
    resolved = Path(_path_or_default(path)) if _path_or_default(path) else GRAPH_PATH
    if not resolved.exists():
        raise FileNotFoundError(f"cau_inference: grafo non trovato in {resolved}")

    grafo = gum.loadBN(str(resolved))

    label = str(label).strip().lower()
    if label == "conterfactual":
        label = "counterfactual"

    ie = gum.LazyPropagation(grafo)
    evidence, out, out_v = _split_query(_parse_features(features), grafo)
    out_labels = list(grafo.variable(out).labels())
    if label != "influence":
        _valida_stati(grafo, evidence)

    if label == "backward_reasoning":
        ie.setEvidence(evidence)
        ie.makeInference()
        if out_v not in out_labels:
            raise ValueError(f"backward_reasoning: {out_v!r} non e' uno stato di {out}, stati: {out_labels}")
        prob = float(ie.posterior(out)[{out: out_v}])
        answer = (
            f"The probability of {out} is {out_v} given the provided conditions "
            f"is {round(prob, 3)}"
        )

    elif label == "counterfactual":
        if len(evidence) != 1:
            raise ValueError(
                f"counterfactual: serve esattamente una variabile di input, trovate {list(evidence)}"
            )
        x, xval = next(iter(evidence.items()))
        if out_v not in out_labels:
            raise ValueError(
                f"counterfactual: {out_v!r} non e' uno stato di {out}, stati: {out_labels}"
            )
        # FIX 11: Py = P(Y = y) e' la marginale dello stesso giunto da cui
        #         cobound prende p_xy, Pxny, p_noxy e Pnxy: si legge dal grafo.
        ie.makeInference()
        py = float(ie.posterior(out)[{out: out_v}])
        answer = cobound(out, out_v, x, xval, None, grafo, py=py)

    elif label == "intervention":
        if not evidence:
            raise ValueError("intervention: 'input' e' vuoto, nessuna variabile su cui intervenire")
        model = csl.CausalModel(gum.BayesNet(grafo))
        formula, impact, explanation = csl.causalImpact(
            model, on=out, doing=set(evidence), values=evidence
        )
        if impact is None:
            answer = f"Non identifiable Query!\n Explanation: {explanation}"
        elif out_v in out_labels:
            answer = (
                f"The probability of {out} equal to {out_v} given the current "
                f"intervention is {round(float(impact[{out: out_v}]), 3)}"
            )
        else:
            distribuzione = ", ".join(
                f"{lab}={round(float(impact[i]), 3)}" for i, lab in enumerate(out_labels)
            )
            answer = (
                f"The probability of {out} given the current intervention is "
                f"distributed as: {distribuzione}"
            )

    elif label == "coherence":
        # FIX 19 (01-11): qui si catturava `gum.InvalidEvidence`, che in pyAgrum
        #        3.2.1 NON esiste (verificato: `hasattr(gum, 'InvalidEvidence')`
        #        falso, e in `dir(gum)` ci sono `NotFound`, `OutOfBounds`,
        #        `InvalidArgument`, `UndefinedElement`).
        #        Come era prima, e' misurato in `verifica_fix_coherence.py` sul
        #        file dello zip del 31-10, non ricostruito: `addEvidence` stava
        #        FUORI dal `try`, quindi lo stato sbagliato usciva come
        #        `OutOfBounds` nudo e la clausola `except` non veniva mai
        #        invocata. Restava pero' una clausola che non puo' funzionare:
        #        se `makeInference()` avesse sollevato, l'espressione stessa
        #        dell'`except` avrebbe dato `AttributeError` e il messaggio di
        #        pyAgrum si sarebbe perso. Il percorso e' stato provato (01-11) e
        #        su questa rete con evidenze valide non solleva, quindi quella
        #        branca non e' mai stata vista girare: il valore del fix qui e'
        #        la forma del contratto, non un punteggio diverso.
        #        I tipi veri su questo percorso sono misurati da
        #        `diagnostica_coherence.py`: `NotFound` per la variabile che non
        #        c'e', `OutOfBounds` per lo stato che non c'e', `InvalidArgument`
        #        per due evidenze in conflitto sulla stessa variabile.
        #        Il `try` ora abbraccia anche `addEvidence`, perche' e' li' che
        #        `NotFound`/`OutOfBounds` partono, e la falla si rialza con `from e`
        #        per conservare la catena. Non si costruisce nessuna `answer`:
        #        un'inferenza fallita non ha un numero, e una frase che ne ha la
        #        forma viene letta come verdetto da `benchmark/valuta.py`.
        try:
            if out in evidence:
                # FIX 20 (01-11): il target non puo' essere anche evidenza. Con
                #        `input={ThisCarCost: HundredThou}` e `output={ThisCarCost:
                #        Million}` -- osservato su COH09 -- pyAgrum non solleva
                #        nulla: P(False|True)=0 e' una condizionale legittima, e il
                #        ramo stampa "probability of 0.0". E' un numero
                #        apparentemente valido prodotto da una domanda
                #        contraddittoria, e `benchmark/valuta.py` lo conterebbe come
                #        risposta. Con lo stato identico sarebbe P=1, un verdetto
                #        vuoto. La riga malformata esce dichiarata, non numerata.
                raise ValueError(
                    f"coherence: il target {out} compare anche fra le evidenze "
                    f"({evidence[out]!r}); la domanda e' contraddittoria, non si risponde"
                )
            for chiave, valore in evidence.items():
                ie.addEvidence(chiave, valore)
            ie.makeInference()
        except (gum.NotFound, gum.OutOfBounds, gum.InvalidArgument) as e:
            raise RuntimeError(
                f"coherence: inferenza non possibile ({type(e).__name__}): {e}"
            ) from e
        if out_v not in out_labels:
            raise ValueError(f"coherence: {out_v!r} non e' uno stato di {out}, stati: {out_labels}")
        prob = float(ie.posterior(out)[{out: out_v}])
        THRESHOLD = 0.60  # soglia presente nel codice della relatrice
        # FIX 12: quattro decimali, come gli altri rami. Con due decimali una
        #         probabilita' piccola ma calcolata (osservato: 0.004876) si
        #         stampa "0.0" e diventa indistinguibile da uno zero esatto: chi
        #         legge non sa se il ramo ha calcolato o si e' fermato.
        if prob >= THRESHOLD:
            answer = (
                f"Evidences are compatible with a single {out} of {out_v} "
                f"with a probability of {round(prob, 4)}"
            )
        else:
            answer = (
                f"Evidences are NOT strongly compatible with a single {out} "
                f"of {out_v} with a probability of {round(prob, 4)}"
            )

    elif label == "influence":
        # qui al posto di fare calcoli, forse conviene di più ragionare sugli archi.
        archi = grafo.arcs()
        lista = ''
        for i in grafo.nodes():
            lista = lista + f', {i} {grafo.variable(i).name()}'
        arc = ''
        for a in archi:
            arc = arc + f'{a}'

        prompt = (
            'If a node has a fixed value the causal relation that goes from its parents nodes '
            'to its sons nodes is blocked (no more influence). If there is at least an indirect '
            'or direct path between the node under consideration and the one on which we want to '
            'understand the effects that does not contain the fixed nodes, the influence is still valid.'
        )
        answer = (
            f'Look at the grafo and understand the task following this instruction: {prompt}. '
            f'The nodes are {lista} and the arc {arc}'
        )

    else:
        raise ValueError(
            f"etichetta non riconosciuta: {label!r} (attese: backward_reasoning, "
            "intervention, coherence, influence, counterfactual)"
        )

    return answer


#@tool
#def vector_search():
