"""Il passo di traduzione reso verificabile, senza toccare `consegna/`.

Perche' esiste. Lo screening del 01-11 sul dev (81 righe, llama3.2:3b) perde 75
righe su 81 e nessuna di esse e' un errore di calcolo: `cau_inference` risponde
esatto su ogni riga in cui riceve una mappatura valida. I guasti sono tutti nel
dizionario che il traduttore passa al tool. Contati su
`harness/risultati/b_base/20261101_150815`:

  - 40 su 40 fra coherence e counterfactual: la mappatura non e' quella della
    query. In counterfactual due variabili in `input` dove il tool ne vuole una
    sola, osservato `trovate ['Airbag', 'Cushioning']`;
  - 15 su 20 in intervention: la variabile di output finisce anche in `input` e
    pyAgrum risponde `The 3 parts of the query (on, doing, knowing) must be
    pairwise disjoint`;
  - nomi inventati: `variabile 'RepairCost' assente dal grafo`;
  - stati inventati o giustapposti: `CarValue='TwentyThou, FiftyThou, Million'`,
    e `'Not necessary'` messo come stato dell'output.

Cosa fa. Due meccanismi, uno nel prompt e uno nel codice, perche' da soli non
bastano:

  1. il prompt aggiunge al testo della relatrice (che resta identico e viene
     solo seguito) il vocabolario **letto dal grafo** che il tool sta per usare,
     e chiede che ogni variabile estratta sia accompagnata dalla frase della
     query da cui e' stata presa;
  2. il codice verifica e scarta. Cio' che viene scartato e' scritto nel JSON,
     voce per voce, con la regola che l'ha colpito.

Le regole di scarto, in ordine:

  `vocabolario`  la variabile deve essere un nodo del grafo e il valore una delle
                 sue etichette. Chiude dall'esterno `RepairCost` e gli stati
                 inventati: l'elenco non viene da `node_descr` (che ha voci
                 malformate) ma da `gum.loadBN` sullo stesso file che legge il
                 tool.
  `nessuna-evidenza` un input con valore 'Not necessary' non e' evidenza: il tool
                 lo filtra gia' (`tools_corretto.py:192`), qui si dichiara invece
                 di lasciarlo passare come se contasse qualcosa.
  `citazione`    la citazione deve essere un sottostringa della query e deve
                 nominare la variabile o lo stato. E' il controllo che impedisce
                 di tenere una variabile che la query non menziona: senza di
                 questo, un `input` con una variabile vera ma non citata
                 ('AntiTheft': 'True') supererebbe il vocabolario e cambierebbe
                 la risposta.
  `disgiunzione` una variabile non puo' essere insieme evidenza e target. E' la
                 regola che pyAgrum applica a `doing`/`on`/`knowing`, applicata
                 qui prima: toglie l'ingresso in `input`, non quello in `output`,
                 perche' l'output e' la domanda.

Nessun fallback silenzioso, e nessuna scelta al posto del modello. Se restano due
evidenze dove il ramo ne vuole una sola (`tools_corretto.py:327`) la riga viene
rifiutata con il motivo, non risolta tenendone una a caso: una scelta inventata
al posto del modello invalida il numero che vorrebbe correggere. Nello stesso spirito, se l'output non passa il
vocabolario o la citazione la riga si ferma: senza target non c'e' domanda da
rispondere. I vincoli di cardinalita' per etichetta vengono dai rami del tool:
counterfactual esattamente una evidenza (`:327`), intervention/coherence/
backward_reasoning almeno una (`:344`, `:366`, `:316`), influence nessuna pretesa
perche' quel ramo non fa inferenza (`:392`).

Costo dichiarato. Il prompt del traduttore cresce del vocabolario (27 nodi, ~250
token) e la risposta cresce delle citazioni. Non e' gratis e non va presentato
come tale: il confronto con b_base si fa su `j_per_corretta`, dove il costo sta
nel numeratore e le risposte corrette in piu' nel denominatore.

Uso:  MUDILAB_COPIE=1 python traduzione_controllata.py --autoverifica
      (--rete per una BIF diversa dal default; senza MUDILAB_COPIE la verifica
      si farebbe sugli originali, cioe' su file che il run non usa)
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True

# Cache del vocabolario: keyed on (percorso, mtime_ns). Un BIF riscritto cambia
# chiave, quindi una rete perturbata non eredita mai il vocabolario della base.
_VOCABOLARIO = {}

# 'Not necessary' e' una parola del prompt della relatrice, non uno stato del
# grafo: in input significa "questa variabile non c'entra".
NESSUNA_EVIDENZA = "not necessary"

LE_REGOLE = ("vocabolario", "nessuna-evidenza", "citazione", "disgiunzione")

# Cardinalita' dell'evidenza per etichetta, perche' il ramo del tool la impone.
# `influence` e' assente: quel ramo non fa inferenza e non legge l'evidenza.
EVIDENZE_RICHIESTE = {
    "counterfactual": (1, 1),
    "intervention": (1, None),
    "coherence": (1, None),
    "backward_reasoning": (1, None),
}


def _norm(testo) -> str:
    """Lessicalizza: minuscolo, ogni carattere non alfanumerico diventa spazio."""
    return re.sub(r"[^a-z0-9]+", " ", str(testo).lower()).strip()


def _parole(nome: str) -> list:
    """Le parole di un nome CamelCase, con il nome intero.

    `ThisCarCost` -> ['ThisCarCost', 'This', 'Car', 'Cost'] (sopra le due lettere),
    perche' una query dice "the repair cost for this car", non "thiscarcost".
    """
    spezzato = re.findall(r"[A-Z]{2,}(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", str(nome))
    return [w.lower() for w in [str(nome), *spezzato] if len(w) > 2]


def percorso_reto(path_rete: str | None) -> Path:
    """Lo stesso file che leggera' il tool.

    Con `path_rete` assente il tool usa il suo default (`GRAPH_PATH` delle copie),
    non un percorso indovinato qui: il vocabolario della verifica e la rete del
    calcolo devono essere lo stesso file.
    """
    if path_rete:
        return Path(path_rete)
    import tools  # caricato da run_query con le copie corrette
    return Path(tools.GRAPH_PATH)


def vocabolario(path_rete: str | None = None) -> dict:
    """{nome_nodo: [etichette]} letto dal grafo, in ordine del grafo."""
    p = percorso_reto(path_rete)
    chiave = (str(p), p.stat().st_mtime_ns)
    if chiave not in _VOCABOLARIO:
        import pyagrum as gum
        bn = gum.loadBN(str(p))
        _VOCABOLARIO[chiave] = {
            bn.variable(i).name(): list(bn.variable(i).labels()) for i in bn.nodes()
        }
    return _VOCABOLARIO[chiave]


def elenco_vocabolario(voc: dict) -> str:
    """Il vocabolario come testo da mettere nel prompt: `Nome: a|b|c; ...`."""
    return "; ".join(f"{nome}: {'|'.join(stati)}" for nome, stati in voc.items())


# Due pezzi concatenati, non un template con .format(): l'esempio di JSON in fondo
# ha graffe letterali e una formattazione le leggerebbe come campi da sostituire.
_VOCABOLARIO_PROMPT = (
    "\n"
    "VARIABLES AND STATES OF THIS GRAPH (authoritative). The list above comes from\n"
    "descriptions and may be malformed; where the two disagree, follow this one.\n"
)

_CITAZIONI_PROMPT = (
    "\n"
    "Write only variable names and state names copied exactly as they appear above.\n"
    "\n"
    "ADDITIONAL KEY 'citazioni'. Alongside 'input' and 'output', return a third\n"
    "JSON object 'citazioni' with one entry per variable you used, key = variable\n"
    "name, value = the exact words copied from the user's query that made you pick\n"
    "that variable. Copy them, do not paraphrase. Where the rules above say\n"
    "'exactly two sub-dictionaries', the two are input and output: 'citazioni' is\n"
    "the third key the same object must carry. A variable whose words are not in\n"
    "the query must not appear in input or output.\n"
    "Each input variable must be a variable the query states something about; do not\n"
    "repeat the output variable inside input.\n"
    "Example: {\"input\": {\"DrivQuality\": \"Normal\"},\n"
    "\"output\": {\"Age\": \"Senior\"},\n"
    "\"citazioni\": {\"DrivQuality\": \"the driving quality is normal\",\n"
    "\"Age\": \"the age of the driver is senior\"}}\n"
)


def istruzioni_traduttore(voc: dict) -> str:
    """Il prompt della relatrice, invariato, seguito dal vocabolario e dalla richiesta di citazione."""
    import agents  # le copie corrette, caricate da run_query
    return (agents.translator_prompt + _VOCABOLARIO_PROMPT
            + elenco_vocabolario(voc) + "\n" + _CITAZIONI_PROMPT)


def _nome_regola(citazione_output) -> str:
    """Il nome della regola sulla citazione del target, da scrivere nell'esito."""
    if citazione_output is True:
        return "obbligatoria"
    if citazione_output == "se-citata":
        return "se-citata"
    return "non richiesta"


def _citazione_valida(cit: str, variabile: str, valore: str, query_norm: str) -> str:
    """'' se la citazione regge, altrimenti il motivo. Un motivo per volta, il primo.

    Il gate `c not in query_norm` e' in discussione con un numero sopra, non con
    un'opinione: togliendolo (replay `senza-verbatim`, 01-11, stessi testi
    registrati di `b_composta`) le righe corrette salgono da 32 a 40 su 81, perche'
    punisce la parafrasi, non solo l'invenzione. Lo stesso gate e' pero' cio' che
    su CND02 ferma un valore inventato -- la riga, rieseguita sul layer deterministico
    con l'evidenza `RiskAversion=Normal` che la query non contiene, stamperebbe 0.704
    contro l'atteso 0.2214 -- e senza quel gate arriva al tool una risposta sbagliata
    al posto di un rifiuto dichiarato.

    Quella di 40/81 e' un'analisi alternativa, non un secondo protocollo, e i due
    numeri non si confrontano come se fossero lo stesso metro: la decisione dell'01-11
    congela la regola con il gate attivo (32/81) e chiede che l'altra resti marcata
    come esplorativa. Le quattro quantita' che li separano -- correttezze, copertura,
    rifiuti, citazioni accettate ma non supportate -- sono in
    `harness/riferimenti/registro_non_valutabili.md`, sezione 5, rigenerate da
    `registro_non_valutabili.py`; la coppia 32/40 rieseguita sugli stessi testi e il
    suo prezzo stanno in `harness/riferimenti/replay_regimi_b_composta_20261101.md`,
    dove la riga INT26 passa dal rifiuto dichiarato a `Exception: bad allocation`
    dentro il tool. Chi volesse cambiare la regola primaria lo la' sopra, non su
    32 contro 40.
    """
    if not isinstance(cit, str) or not cit.strip():
        return "citazione assente o vuota"
    c = _norm(cit)
    if not c:
        return "citazione senza parole"
    if c not in query_norm:
        return "citazione non presente nella query"
    if _norm(valore) and _norm(valore) in c:
        return ""
    if any(w in c for w in _parole(variabile)):
        return ""
    return "la citazione non nomina ne' la variabile ne' lo stato"


def _chiavi_ammesse(dati: dict) -> bool:
    return set(dati) == {"input", "output", "citazioni"}


def valida(grezzo: str, etichetta: str, query: str, path_rete: str | None = None,
           citazione_output=True):
    """(traduzione per il tool, esito) oppure (None, esito con `motivo`).

    `esito` esce sempre compilato, anche quando la riga viene rifiutata: la riga
    fallita deve dire quale regola l'ha fermata, non solo che si e' fermata.

    `citazione_output` sceglie la regola sulla citazione del target, e finisce
    scritta nell'esito perche' due run con regole diverse non sono lo stesso
    protocollo: `True` (default, come misurato l'01-11) la pretende; `"se-citata"`
    la verifica solo quando il modello la scrive; `False` non la chiede. La scelta
    non e' un gusto: sull'dev la pretesa rifiutava 40 righe, meta' con il target
    giusto e meta' con il target sbagliato (`replay_traduzione.py`), quindi come
    filtro sull'output non separa nulla.
    """
    import tools  # _parse_features delle copie: virgolette tipografiche e via dicendo
    esito = {"regole": list(LE_REGOLE), "scartate": [], "motivo": "",
             "etichetta": etichetta, "evidenze": None, "target": None,
             "citazione_output": _nome_regola(citazione_output)}

    try:
        dati = tools._parse_features(grezzo)
    except Exception as e:
        esito["motivo"] = f"il testo del traduttore non e' un dizionario: {type(e).__name__}: {e}"
        return None, esito
    if not _chiavi_ammesse(dati):
        esito["motivo"] = (f"chiavi {sorted(dati)} invece di "
                           "['citazioni', 'input', 'output']")
        return None, esito

    voc = vocabolario(path_rete)
    query_norm = _norm(query)
    citazioni = dati["citazioni"]
    if not isinstance(citazioni, dict) or not citazioni:
        esito["motivo"] = "'citazioni' assente o vuoto: nessuna estrazione e' verificabile"
        return None, esito

    # --- output: se non regge, la riga si ferma. Senza target non c'e' domanda.
    output = dati["output"]
    if not isinstance(output, dict) or len(output) != 1:
        esito["motivo"] = f"'output' deve avere esattamente una chiave: {output!r}"
        return None, esito
    (out, out_v), = output.items()
    if out not in voc:
        esito["motivo"] = f"output: variabile {out!r} non e' un nodo del grafo"
        return None, esito
    if str(out_v).strip().lower() == NESSUNA_EVIDENZA:
        esito["motivo"] = "output: lo stato e' 'Not necessary', la domanda non ha target"
        return None, esito
    if out_v not in voc[out]:
        esito["motivo"] = (f"output: {out_v!r} non e' uno stato di {out}; "
                           f"stati: {voc[out]}")
        return None, esito
    motivo = _citazione_valida(citazioni.get(out), out, out_v, query_norm)
    if citazione_output is True or (citazione_output == "se-citata"
                                    and isinstance(citazioni.get(out), str)
                                    and citazioni[out].strip()):
        if motivo:
            esito["motivo"] = f"output {out}: {motivo}"
            return None, esito
    elif motivo:
        # la citazione del target c'e' e non regge: la si dichiara senza fermare
        # la riga, perche' `se-citata` e `libero` rinunciano a quel controllo
        esito["avviso_output"] = motivo
    esito["target"] = {out: out_v}

    # --- input: ogni voce passa le regole, e cio' che cade e' dichiarato
    if not isinstance(dati["input"], dict):
        esito["motivo"] = f"'input' non e' un dizionario: {dati['input']!r}"
        return None, esito
    evidenza = {}
    for nome, valore in dati["input"].items():
        def scarta(regola, dettaglio):
            esito["scartate"].append({"lato": "input", "variabile": nome,
                                      "valore": valore, "regola": regola,
                                      "dettaglio": dettaglio})
        if nome not in voc:
            scarta("vocabolario", f"{nome!r} non e' un nodo del grafo")
            continue
        if str(valore).strip().lower() == NESSUNA_EVIDENZA:
            scarta("nessuna-evidenza", "il valore dichiara che la variabile non c'entra")
            continue
        if valore not in voc[nome]:
            scarta("vocabolario",
                   f"{valore!r} non e' uno stato di {nome}; stati: {voc[nome]}")
            continue
        if nome == out:
            scarta("disgiunzione", "la variabile e' gia' il target della domanda")
            continue
        motivo = _citazione_valida(citazioni.get(nome), nome, valore, query_norm)
        if motivo:
            scarta("citazione", motivo)
            continue
        evidenza[nome] = valore

    limiti = EVIDENZE_RICHIESTE.get(str(etichetta).strip().lower())
    if limiti:
        min_e, max_e = limiti
        # Il motivo da solo direbbe "nessuna evidenza" senza dire perche': le voci
        # sono gia' cadute una per una sotto, e chi legge il JSON deve vedere la
        # catena, non solo l'ultimo anello.
        scarto = (f"; scartate: " + ", ".join(
            f"{s['variabile']}={s['valore']!r} ({s['regola']}: {s['dettaglio']})"
            for s in esito["scartate"])) if esito["scartate"] else ""
        if len(evidenza) < min_e:
            esito["motivo"] = (f"{etichetta}: servono almeno {min_e} evidenza/e, "
                               f"restano {list(evidenza)}{scarto}")
            return None, esito
        if max_e is not None and len(evidenza) > max_e:
            esito["motivo"] = (f"{etichetta}: serve esattamente {max_e} evidenza, "
                               f"restano {list(evidenza)}: quale sia l'intervento "
                               f"non lo decide il codice{scarto}")
            return None, esito

    esito["evidenze"] = evidenza
    return {"input": evidenza, "output": {out: out_v}}, esito


class Traduttore:
    """Il passo di traduzione come oggetto: istruzioni con il vocabolario, e verifica.

    Serve a `run_orchestrato.run(..., traduttore=...)`, che chiama `agente` per il
    passo di modello e `valida` prima di passare il dizionario al tool. Il
    vocabolario dipende dalla rete della riga, quindi l'agente si costruisce una
    volta per rete: una rete perturbata ha le stesse variabili della base, ma la
    chiave e' il file, non l'elenco delle variabili.

    `citazione_output` e' una scelta di protocollo della variante, non un dettaglio
    di chiamata: sta sull'oggetto, cosi' ogni riga del JSON dichiara con quale regola
    e' stata verificata e due run con regole diverse non si spacciano per lo stesso.
    """

    def __init__(self, cliente, citazione_output=True):
        self._cliente = cliente
        self._citazione_output = citazione_output
        self._agenti = {}

    def agente(self, path_rete: str | None):
        from agents import Agent  # le copie corrette, caricate da run_query
        p = percorso_reto(path_rete)
        chiave = (str(p), p.stat().st_mtime_ns)
        if chiave not in self._agenti:
            self._agenti[chiave] = Agent(
                name="To_Math",
                client=self._cliente,
                instructions=istruzioni_traduttore(vocabolario(path_rete)),
            )
        return self._agenti[chiave]

    def valida(self, grezzo: str, etichetta: str, query: str, path_rete: str | None = None):
        return valida(grezzo, etichetta, query, path_rete,
                      citazione_output=self._citazione_output)


# ---------------------------------------------------------------------------
# autoverifica: casi sintetici, nessun modello, nessuna query
# ---------------------------------------------------------------------------

def _casi():
    """(nome, grezzo, etichetta, query, esito atteso).

    Gli esiti attesi sono ('ok', traduzione) o ('no', motivo che deve comparire).
    Le query sono frasi del benchmark reale, per verificare la citazione su testo
    vero e non su un testo inventato che non nomina ne' variabili ne' stati.
    """
    q_cp = ("Given that the driving quality is normal, how likely is it that "
            "the age of the driver is senior?")
    q_cf = ("We observed that the car has an airbag and that the car is as rugged "
            "as a football. What would the probability that the car is as rugged as "
            "a football be if the world had been such that the car has no airbag?")
    # Due dotazioni, non una: serve a provare il rifiuto senza appoggiarsi a una
    # citazione falsa, perche' in quel caso la riga si salverebbe lo stesso.
    q_cf2 = ("We observed that the car has an airbag and that the car has an "
             "antilock braking system and that the car is as rugged as a football. "
             "What would the probability that the car is as rugged as a football be "
             "if the world had been such that the car has no airbag?")
    return [
        ("forma buona",
         '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal",'
         ' "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         ("ok", {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}})),

        ("variabile inventata nel grafo, input rimosso",
         '{"input": {"DrivQuality": "Normal", "RepairCost": "Thousand"},'
         ' "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal",'
         ' "RepairCost": "the cost is one thousand dollars", "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         ("ok", {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}},
          [("RepairCost", "vocabolario")])),

        ("stato inventato: tre stati giustapposti non sono uno stato",
         '{"input": {"CarValue": "TwentyThou, FiftyThou, Million"},'
         ' "output": {"Age": "Senior"},'
         ' "citazioni": {"CarValue": "the car is worth five thousand dollars",'
         ' "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         ("no", "non e' uno stato di CarValue")),

        ("variabile vera ma non citata: cade lei, la riga resta buona",
         '{"input": {"DrivQuality": "Normal", "AntiTheft": "True"},'
         ' "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal",'
         ' "AntiTheft": "the vehicle is never stolen", "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         # L'evidenza non richiesta sparisce e resta la domanda vera: e' il caso
         # delle 15 su 20 di intervention, dove la variabile in piu' era proprio
         # il motivo per cui pyAgrum si fermava.
         ("ok", {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}},
          [("AntiTheft", "citazione")])),

        ("target ripetuto in input: disgiunzione, e il numero torna lo stesso",
         '{"input": {"DrivQuality": "Normal", "Age": "Senior"},'
         ' "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal",'
         ' "Age": "the age of the driver is senior"}}',
         "intervention", q_cp,
         # La voce che cade e' dichiarata, non tolta in silenzio: senza questo
         # contatore il run non direbbe quante righe sono state salvate dallo
         # scarto invece che da una traduzione giusta al primo colpo.
         ("ok", {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}},
          [("Age", "disgiunzione")])),

        ("'Not necessary' in input: non e' evidenza, si dichiara e si toglie",
         '{"input": {"DrivQuality": "Normal", "Cushioning": "Not necessary"},'
         ' "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal",'
         ' "Cushioning": "the cushioning is poor", "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         ("ok", {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}},
          [("Cushioning", "nessuna-evidenza")])),

        ("'Not necessary' come stato dell'output: la riga si ferma",
         '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Not necessary"},'
         ' "citazioni": {"DrivQuality": "the driving quality is normal", "Age": "age"}}',
         "backward_reasoning", q_cp,
         ("no", "'Not necessary', la domanda non ha target")),

        ("senza citazioni non c'e' nulla da verificare",
         '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}, "citazioni": {}}',
         "backward_reasoning", q_cp,
         ("no", "nessuna estrazione e' verificabile")),

        ("chiavi sbagliate",
         '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}',
         "backward_reasoning", q_cp,
         ("no", "invece di ['citazioni', 'input', 'output']")),

        ("prosa invece del dizionario: niente da verificare",
         "I think the driver is senior because the driving quality is normal.",
         "backward_reasoning", q_cp,
         ("no", "non e' un dizionario")),

        ("counterfactual: il target ripetuto in input cade, resta una evidenza",
         '{"input": {"Airbag": "True", "RuggedAuto": "Football"},'
         ' "output": {"RuggedAuto": "Football"},'
         ' "citazioni": {"Airbag": "the car has an airbag",'
         ' "RuggedAuto": "the car is as rugged as a football"}}',
         "counterfactual", q_cf,
         ("ok", {"input": {"Airbag": "True"}, "output": {"RuggedAuto": "Football"}},
          [("RuggedAuto", "disgiunzione")])),

        ("counterfactual con due evidenze entrambe legittime: la riga si ferma",
         # Nessuna delle due cade: sono nodi veri, stati veri, citazioni verificate,
         # e nessuna e' il target. E' il caso in cui scegliere significherebbe
         # inventarsi la domanda, quindi il rifiuto e' l'unico esito onesto.
         '{"input": {"Airbag": "True", "Antilock": "True"},'
         ' "output": {"RuggedAuto": "Football"},'
         ' "citazioni": {"Airbag": "the car has an airbag",'
         ' "Antilock": "the car has an antilock braking system",'
         ' "RuggedAuto": "the car is as rugged as a football"}}',
         "counterfactual", q_cf2,
         ("no", "serve esattamente 1 evidenza")),

        ("citazione parafrasata: non e' copia, quindi non regge",
         '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"},'
         ' "citazioni": {"DrivQuality": "quality is fine", "Age": "the age of the driver is senior"}}',
         "backward_reasoning", q_cp,
         ("no", "citazione non presente nella query")),
    ]


def autoverifica(path_rete: str | None = None) -> int:
    """Esegue i casi sintetici sulla rete reale. Ritorna il numero di fallimenti.

    Un caso `ok` puo' chiedere anche le voci scartate: scartare in silenzio e'
    esattamente il difetto che la variante combate, quindi il conteggio degli
    scarti e' parte dell'aspettativa, non un dettaglio di stampa.
    """
    caduti = 0
    scarti = 0
    for nome, grezzo, etichetta, query, atteso in _casi():
        traduzione, esito = valida(grezzo, etichetta, query, path_rete)
        scarti += len(esito["scartate"])
        tipo, dettaglio = atteso[0], atteso[1]
        scartate_attese = atteso[2] if len(atteso) > 2 else []
        if tipo == "ok":
            trovate = [(s["variabile"], s["regola"]) for s in esito["scartate"]]
            va = traduzione == dettaglio and trovate == scartate_attese
            perche = "" if va else (f"traduzione {traduzione}, scartate {trovate}")
        else:
            va = traduzione is None and dettaglio in esito["motivo"]
            perche = esito["motivo"] or "accettata, ma era da rifiutare"
        if not va:
            caduti += 1
        print(f"[{'ok ' if va else 'KO '}] {nome}: {perche}")
    voc = vocabolario(path_rete)
    print(f"vocabolario: {len(voc)} nodi, "
          f"{sum(len(s) for s in voc.values())} stati, "
          f"{len(elenco_vocabolario(voc))} caratteri di prompt")
    print(f"voci scartate sui casi: {scarti}")
    return caduti


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--autoverifica", action="store_true")
    ap.add_argument("--rete", help="BIF da usare, default: il default delle copie")
    a = ap.parse_args()
    if not a.autoverifica:
        ap.print_help()
        raise SystemExit(2)
    # Absolute adesso, perche' run_query cambia la CWD nella cartella delle copie:
    # un percorso relativo passato qui si leggerebbe da un'altra cartella.
    rete = str(Path(a.rete).resolve()) if a.rete else None
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie di MUDILAB_COPIE
    raise SystemExit(1 if autoverifica(rete) else 0)
