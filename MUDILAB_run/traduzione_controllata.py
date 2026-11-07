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

  `target-ancorato` **spento di default**, perche' non fa parte del protocollo con
                 cui sono presi i joule del 02-11. Acceso da
                 `valida(..., target_nella_domanda=True)`, vale solo per
                 l'etichetta `counterfactual`: il target deve comparire nella
                 clausola interrogativa della domanda, non nella clausola
                 ipotetica. Motivo misurato: 27 run su 42 controfattuali arrivati
                 al tool hanno come target l'antecedente manipolato. Contato su
                 replay il 02-11 (`replay_traduzione.py`, 240 run,
                 `harness/risultati/replay_regole_nuove_20261102.txt`): ferma 21
                 run che sarebbero arrivati al tool con la domanda sbagliata, non
                 ne recupera e non ne uccide nessuno -- le corrette restano 77,
                 identiche al riferimento. Resta spento: non cambia il punteggio,
                 cambia solo il calcolo speso, e quello si misura con un run, non
                 qui dentro.

  `coerenza-target` **spento di default**, acceso da `valida(..., coerenza="target")`
                 e valido solo per l'etichetta `coherence`: il target deve stare
                 nella clausola fra `is it coherent that` e `given that`. E' la
                 gemella del `target-ancorato` sull'altra forma di domanda, e
                 chiude un foro che le quattro regole in vigore non vedono: il
                 modello prende la variabile che l'oracolo chiede come *evidenza* e
                 fa la domanda su un'altra, con citazioni copie fedeli della query --
                 quindi vere, e non scartabili. Contato il 03-11 su replay
                 (`harness/risultati/replay_regole_coherence_20261103.txt`, 240 run):
                 ferma **21 run** -- COH03, COH07, COH11, COH12, COH15, COH28, COH36
                 per le tre ripetizioni -- e le corrette restano 77, zero perse.

  `coerenza-clausole` **spento di default**, `valida(..., coerenza="clausole")`:
                 tante evidenze quante clausole la domanda enuncia, contate dal
                 testo (`clausole_evidenza`), non da una costante. E' la regola che
                 manca perche' `EVIDENZE_RICHIESTE` dice "almeno una" perche' e'
                 cio' che il *tool* pretende, mentre la domanda di coerenza ne
                 enuncia due: con una sola l'inferenza e' condizionata a meta' e il
                 numero che ne esce passa per una risposta. Contato lo 03-11: ferma
                 **18 run** (COH11, COH12, COH15, COH27, COH35, COH36), corrette 77
                 come il riferimento.

  Le due insieme (`coerenza="target,clausole"`) fermano **tutti e 27** i run del ramo
  che arrivavano al tool con un numero non dell'oracolo, e le corrette di `coherence`
  restano 18/60 in tutti e tre i regimi: il totale su 240 e' 77, identico al
  riferimento, con zero righe buone perse. Non e' un peggioramento e non e' un
  miglioramento: e' lo stesso punteggio con 27 numeri in meno che non andavano
  prodotti. Il regime che le corrette le aggiunge, `stati-alias` (91), con le due
  regole accese resta a 91 -- nessuna delle 14 righe recuperate sta nel ramo, e i 3
  run di COH24 che l'alias riportava da `rifiutata` a `numero` tornano `rifiutata`
  per la regola sulle clausole. Restano tutte e tre spente: chiudono il calcolo
  speso su una domanda gia' sbagliata, non correggono la traduzione, e correggerla
  vuol dire cambiare il prompt, che e' un run sul modello e non si conta da qui.

  Da dove vengono le due regole. `diagnosi_coherence.py` classifica i 27 run che
  passano il gate e stampano un numero non dell'oracolo confrontando il dizionario
  con `evidence_json` di `benchmark.csv` **e** con il target della riga: 24 hanno il
  `target sbagliato` (otto task per tre ripetizioni) e solo 3 un'evidenza `manca`
  (COH35). Quindi il difetto del ramo non e' la traduzione monca, che era l'ipotesi
  con cui la regola fini' in lista: e' lo scambio di target. Le due regole non sono
  l'una un sottoinsieme dell'altra -- 12 run li fermano entrambe, e i 6 propri di
  `clausole` sono COH27 e COH35, cioe' lo scambio che l'ancoraggio non vede e l'unica
  riga con l'evidenza davvero mancante. Output:
  `harness/risultati/diagnosi_coherence_20261103.txt`.

  `stato-alias` **spento di default**, acceso da `valida(..., stati_alias="prosa")`
                 o `stati_alias="prosa+unita"`: il confronto fra lo stato scritto in
                 prosa e l'etichetta del `.bif` passa per una tabella di sinonimi
                 generata **dalle etichette stesse**, non scritta a mano, con le
                 collisioni scartate per-voce. E' l'unica regola che fra quelle contate
                 aggiunge righe corrette: `harness/risultati/replay_regole_nuove_20261102.txt`
                 porta le corrette da 77 a **91 su 240** (+14, zero perse, 74
                 normalizzazioni, 0 collisioni sulle 27 variabili della rete reale), e
                 `harness/risultati/replay_regola_unita_20261103.txt` porta il conto a
                 **92** con la variante che toglie anche `miles` (+1: INT24 in una sola
                 ripetizione, 77 normalizzazioni). Resta spento perche' il prezzo non
                 e' nel saldo ma nella classe di esito: dodici righe passano da
                 `rifiutata` a `numero` (COH24, INT16, INT19, INT27) -- errori veri di
                 **variabile** che il confronto letterale fermava per un motivo che non
                 c'entrava. Con la regola spenta quei dodici restano rifiuti dichiarati;
                 accesa, diventano risposte sbagliate che passano per risposte. Il
                 confine della regola e' misurato e non e' un buco dell'implementazione:
                 i 26 valori che la tabella non scioglie sono tre famiglie, e due
                 (l'elenco degli stati copiato nel campo del valore, e i booleani scritti
                 come frase) **non** hanno una normalizzazione onesta -- scegliere quale
                 stato tenere significherebbe inventarselo.
                 Registro di riga: `esito["stato_alias"]` porta il nome,
                 `esito["normalizzazioni"]` le chiamate risolte dalla tabella e
                 `esito["non_risolti"]` quelle che non l'hanno trovata.

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


def _regole_cerenza(valore) -> tuple:
    """Le regole opzionali del ramo `coherence` da applicare, come insieme ordinato.

    `valore` e' una stringa con i nomi separati da virgola (o un iterable di nomi),
    perche' le due regole si misurano separate e poi insieme: un booleano non
    direbbe quale delle due ha fermato una riga. Il default vuoto le spegne tutte,
    che e' il protocollo con cui sono presi i joule del 02-11.

    Un nome sconosciuto **solleva**, non viene ignorato: un regime scritto male nel
    replay darebbe il numero della regola che si credeva di misurare, e un errore di
    battitura non puo' diventare un protocollo.
    """
    if valore is None or valore is False or valore == "":
        return ()
    if valore is True:
        return REGOLE_COERENZA
    nomi = valore.split(",") if isinstance(valore, str) else list(valore)
    out = tuple(str(n).strip().lower() for n in nomi if str(n).strip())
    ignote = [n for n in out if n not in REGOLE_COERENZA]
    if ignote:
        raise ValueError(f"regola di coerenza sconosciuta: {ignote}; "
                         f"valide: {list(REGOLE_COERENZA)}")
    return out


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


# -- il confronto fra lo stato scritto e le etichette del grafo -----------------------------
#
# Perche' e' una funzione e non un `in`. Il gate scrive `out_v not in voc[out]`, cioe'
# un'uguaglianza esatta fra la stringa del modello e l'etichetta del `.bif`. E' il
# protocollo con cui sono presi i joule del 02-11 e resta il default. Ma sull'held-out
# quel confronto ferma 26 run `inter` su 60 per una ragione sola: il traduttore scrive
# lo stato **in prosa** -- `PropCost='hundred thousand dollars'` contro l'etichetta
# `HundredThou`, `OtherCarCost='ten thousand dollars'` contro `TenThou` -- e la rete
# non vede nessuna delle due parole. Contato riga per riga sui JSON di
# `risultati_misura/b_composta/20261102_191401`: nove task per tre ripetizioni
# (INT04, INT07, INT16, INT19, INT24, INT27, INT32, INT35 e INT39), di cui INT39 scrive
# `AntiTheft='no antilock braking system'` contro gli stati `True|False`, che nessun
# alias di etichetta puo' toccare. Il numero completo c'e', e non autorizza ancora la
# regola: il replay del 02-11
# (`harness/risultati/replay_regole_nuove_20261102.txt`, regime `stati-alias`) porta
# le corrette da 77 a 91 su 240 con 74 normalizzazioni, 0 collisioni di tabella e 26
# prose che restano non risolte, e sposta anche 12 righe da `rifiutata` a `numero` --
# errori veri di variabile che il confronto letterale fermava per motivo diverso.
# Per questo la ricerca dell'etichetta si puo' sostituire dall'esterno, come
# `_citazione_valida`: la variante si misura, non si adotta. La sostituzione e'
# rimasta l'unico modo di accenderla fino al 03-11, e aveva un difetto di
# provenienza: il regime del replay montava la tabella per name-shadowing, quindi il
# numero di 91 era contato su una funzione che nel modulo non esisteva. Ora la
# normalizzazione sta qui, dietro il kwarg `stati_alias` di `valida`, e il replay
# accende quella: la riga e il suo numero vengono dalla stessa implementazione.
#
# Ritorna l'etichetta e non un booleano, perche' il tool riceve la stringa: accettare
# `HundredThou` passando al grafo `hundred thousand dollars` vorrebbe dire spostare il
# rifiuto dal gate a pyAgrum, cio' e' un errore in piu' dichiarato da un'altra parte.
def stato_del_grafo(valore: str, variabile: str, stati: list):
    """L'etichetta del grafo che il valore scritto indica, o None.

    Default: uguaglianza esatta, il protocollo del 02-11. La normalizzazione in
    prosa e' un'alternativa **dichiarata** da chi chiama (kwarg `stati_alias` di
    `valida`), non un comportamento di questa funzione; la sostituzione dall'esterno
    resta ammessa come cucitura di test, non come via di adozione.
    """
    return valore if valore in stati else None


# -- la normalizzazione in prosa, dietro il kwarg `stati_alias ---------------------------
#
# Le due pulizie sono due regimi diversi e hanno due numeri diversi, e per questo
# restano separate: `prosa` e' quella pubblicata il 02-11 (74 normalizzazioni, 91
# corrette su 240), `prosa+unita` e' il candidato del 03-11 nato dall'elenco dei 26
# valori non risolti (77 normalizzazioni, 92 corrette, +1 e zero perse -- e l'+1 e'
# una riga sola, INT24 nella sola ripetizione r1). Il confine di entrambe e' una
# **lista chiusa** di parole: `dollars|dollar|usd` per la prima, piu' `miles|mile`
# per la seconda perche' `Mileage` e' l'unica variabile del grafo la cui unita' non
# sia una moneta. Non e' "togli l'ultima parola" e non e' un vocabolario di unita'
# generico: le parole sono quelle che compaiono davvero nei 26 valori non risolti.
PAROLE_VALUTA = ("dollars", "dollar", "usd")
PAROLE_UNITA = PAROLE_VALUTA + ("miles", "mile")
ESPANSIONI = {"thou": "thousand"}


def _forma_prosa(etichetta: str) -> str:
    """La prosa che un'etichetta del grafo scrive di se' stessa, in forma-canone.

    `HundredThou` -> `hundred thousand`: il CamelCase spezza e `Thou` e'
    l'abbreviazione che il `.bif` della relatrice usa per `Thousand`. L'espansione e'
    una tabella di una sola righe perche' quella e' l'unica abbreviazione che
    compare nelle etichette della rete reale -- contato, non assunto: le altre si
    spezzano in parole intere (`True`, `Current`, `Older`, `SubStandard`).
    """
    spezzato = re.findall(r"[A-Z]{2,}(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", str(etichetta))
    return " ".join(ESPANSIONI.get(w.lower(), w.lower()) for w in spezzato)


def _togli_parenime(valore: str, parenime: tuple) -> str:
    """La lessicalizzazione del valore scritto, senza le parole di unita'."""
    return " ".join(w for w in _norm(valore).split() if w not in parenime)


def _pulisci_prosa(valore: str) -> str:
    """La pulizia pubblicata il 02-11: via la sola moneta."""
    return _togli_parenime(valore, PAROLE_VALUTA)


def _pulisci_prosa_con_unita(valore: str) -> str:
    """La pulizia del candidato del 03-11: la moneta e l'unita' di `Mileage`."""
    return _togli_parenime(valore, PAROLE_UNITA)


NORMALIZZAZIONI_STATO = {
    "prosa": _pulisci_prosa,
    "prosa+unita": _pulisci_prosa_con_unita,
}


def _scelta_normalizzazione(valore) -> str:
    """Il nome della normalizzazione da applicare, validato; '' per nessuna.

    Come `_regole_cerenza`: un nome scritto male **solleva**, non degrada al default.
    Un regime con un refuso darebbe il numero della normalizzazione che si credeva di
    misurare, e qui quel numero e' la ragione per cui la regola e' ancora spenta.
    """
    if valore is None or valore is False or valore == "":
        return ""
    if valore is True:
        return "prosa"
    nome = str(valore).strip().lower()
    if nome not in NORMALIZZAZIONI_STATO:
        raise ValueError(f"normalizzazione di stato sconosciuta: {nome!r}; "
                         f"valide: {sorted(NORMALIZZAZIONI_STATO)}")
    return nome


def alias_di(stati: list) -> tuple:
    """({prosa: etichetta}, [(prosa, [etichette collisionanti])]) per una variabile.

    Il secondo valore e' l'iniettivita' **verificata**, non assunta: se due etichette
    della stessa variabile scrivono la stessa prosa, la voce viene tolta dalla
    tabella. Una normalizzazione ambigua non e' una normalizzazione -- scegliere una
    delle due significa inventarsi lo stato, che e' esattamente cio' che il gate
    esiste per impedire. Lo scarto e' per-voce e non per-tabella: una collisione sui
    `Thou` non toglie la voce `Million`, che buona lo e'.
    """
    righe = {}
    for s in stati:
        righe.setdefault(_forma_prosa(s), []).append(s)
    tabella, collisioni = {}, []
    for prosa, etichette in righe.items():
        if len(etichette) > 1:
            collisioni.append((prosa, etichette))
        else:
            tabella[prosa] = etichette[0]
    return tabella, collisioni


# Cache delle tabelle: chiave (variabile, tuple(stati), normalizzazione). La sola
# variabile non basta -- le righe perturbate del benchmark girano su reti diverse e
# una tabella unica sarebbe la tabella della rete sbagliata -- e non basta nemmeno
# (variabile, stati) perche' le due pulizie producono tabelle diverse.
_ALIAS = {}


def cerca_stato_alias(valore: str, variabile: str, stati: list, normalizzazione: str):
    """L'etichetta che la tabella degli alias associa alla prosa, o None."""
    chiave = (variabile, tuple(stati), normalizzazione)
    entrata = _ALIAS.get(chiave)
    if entrata is None:
        entrata = alias_di(stati)
        _ALIAS[chiave] = entrata
    return entrata[0].get(NORMALIZZAZIONI_STATO[normalizzazione](valore))


def collisioni_alias() -> list:
    """Le collisioni di tabella su tutte le chiavi costruite finora.

    Non un dettaglio di stampa: l'iniettivita' e' il prerequisito perche' la
    normalizzazione non sia una scelta, e il conto del replay la stampa perche' una
    collisione ignorata sarebbe un rifiuto trasformato in un'invenzione.
    """
    return [collisioni for (_chiave, (_tabella, collisioni)) in _ALIAS.items()
            if collisioni]


def stato_con_alias(valore: str, variabile: str, stati: list, normalizzazione: str):
    """L'etichetta del grafo: uguaglianza esatta prima, tabella degli alias poi.

    L'ordine non e' una pigrizia: una prosa che collide con un'etichetta reale non
    deve mai avere precedenza sull'etichetta scritta alla lettera. Con
    `normalizzazione` vuota e' `stato_del_grafo`, cioe' il protocollo del 02-11.
    """
    etichetta = stato_del_grafo(valore, variabile, stati)
    if etichetta is not None or not normalizzazione:
        return etichetta
    return cerca_stato_alias(valore, variabile, stati, normalizzazione)


# -- l'ancoraggio del target alla domanda -------------------------------------------------
#
# Perche' esiste. Sull'held-out misurato del 02-11 il ramo counterfactual e' il
# peggiore (15/60) e la ragione non e' il calcolo: delle 42 righe che il gate
# lascia arrivare al tool, 27 -- nove task per le tre ripetizioni -- hanno nel
# dizionario un target **diverso** da quello della domanda, e `corretta` e' vera
# solo quando il target e' giusto (0 divergenze su 42). Sette di quei nove task
# mettono come target l'**antecedente** manipolato -- `VehicleYear=Older` (CF11,
# CF20, CF27, CF32, CF35, CF39) e `SeniorTrain` (CF24), ventuno run -- perche' la
# forma della domanda controfattuale nomina due stati della stessa variabile:
# l'osservato nella clausola interrogativa e l'ipotetico nella clausola
# `if the world had been`, e il traduttore piccolo sceglie la seconda. Gli altri due
# sono CF07 (`Accident=None` invece di `Moderate`) e CF28 (`PropCost=Million` invece
# di `ThisCarCost=Thousand`): target un'altra variabile, non l'antecedente.
# Evidenza: `harness/risultati/analisi_rami_deboli_20261102.txt` sezione 4 e i
# JSON di `risultati_misura/b_composta/20261102_191401`.
#
# Perche' non la citazione. La regola gemella sulla citazione del target non puo'
# fare questo lavoro: in `b_composta` vale `citazione_output = non richiesta`
# perche' sull'dev la pretesa rifiutava 40 righe, meta' con il target giusto, e
# INT03 mostra che il modello omette la citazione dell'output anche quando il
# target e' quello vero. Qui non si chiede al modello di citare niente: si legge
# la **domanda**, che e' testo noto al gate, e si verifica che il target che il
# modello ha scelto stia nella clausola che fa la domanda.
#
# Debolezza misurata, non promessa. Il secondo ramo accetta se una parola del nome
# della variabile compare nella clausola, e per le variabili di costo le parole si
# sovrappongono: `ThisCarCost` e `PropCost` condividono `cost`, quindi una riga
# che confonde i due costi **non** viene colta (CF28, `PropCost=Million` al posto
# di `ThisCarCost=Thousand`). Contato: il replay del 02-11
# (`harness/risultati/replay_regole_nuove_20261102.txt`) su 240 run con la regola a
# tre rami ferma 21 run che sarebbero arrivati al tool con il target dell'antecedente
# (CF11, CF20, CF24, CF27, CF32, CF35, CF39), non ne recupera nessuno e non ne uccide
# nessuno: le corrette restano 77, identiche al riferimento `output=libero`. CF28
# passa, come previsto qui sopra. Il guadagno non e' il punteggio -- quelle 21 righe
# erano gia' `numero` sbagliato -- e' che non consumano il calcolo.
APERTURA_DOMANDA = "what would the probability that"
CLAUSOLA_ILOTETICO = "if the world had been"

# Le due ancore per etichetta, entrambe lette dai template di `genera.py`
# (`_q_cf:469`, `_q_coh:464`) e non inventate: la clausola della domanda e' il
# testo fra l'apertura e la prima ancora che la chiude. `intervention`
# ("What is the probability that ... if we intervene to make it so that ...") e
# `backward_reasoning` ("Given that ..., how likely is it that ...") restano
# fuori perche' la prima ha il target gia' all'inizio e la seconda lo ha dopo
# l'unica clausola: li l'ancoraggio non separerebbe nulla, e una regola che non
# discrimina e' un rischio di falsi positivi senza guadagno.
FORME_DOMANDA = {
    "counterfactual": (APERTURA_DOMANDA, CLAUSOLA_ILOTETICO),
    "coherence": ("is it coherent that", "given that"),
}

# Le regole opzionali del ramo `coherence`, accese dalla stringa `coerenza` di
# `valida`. Sono due e restano separabili perche' i due guasti sono diversi, e sono
# due conti diversi -- la classe di `diagnosi_coherence.py` dice di cosa si tratta,
# il replay dice quanta strada ferma ciascuna. Sui 27 run che il 02-11 passano il
# gate e ricevono un numero che non e' quello dell'oracolo
# (`harness/risultati/diagnosi_coherence_20261103.txt`, misura del 03-11):
#   classe `target sbagliato`  24 -- il modello domanda un'altra variabile e mette
#                              quella dell'oracolo fra le evidenze (otto task per tre
#                              ripetizioni: COH03, COH07, COH11, COH12, COH15, COH27,
#                              COH28, COH36);
#   classe `manca`              3 -- l'insieme di evidenza e' piu' corto, perche' una
#                              delle due clausole non e' tradotta (solo COH35,
#                              `RuggedAuto`).
# Le due classi sono esaustive e non si sovrappongono. Quanta strada ferma ciascuna
# regola e' un altro numero, e i due conti non vanno letti come la stessa cosa: la
# classe dice **cosa non torna** nel dizionario che arriva al tool, il regime dice
# **cosa il gate ferma**, e la regola `target` confronta il dizionario con la clausola
# della domanda -- non con l'oracolo -- quindi la sua copertura della classe non e'
# per intero:
#   `target`    21 run nuovi fermati (nel ramo le sue motivazioni sono 27: sei erano
#               gia' rifiutate da una regola in vigore, cambia solo la ragione)
#   `clausole`  18 run nuovi fermati
#   entrambe    27 -- non e' la somma dei due (21+18=39): l'intersezione e' 12 run.
# L'ottavo task della classe che `target` non ferma e' COH27: la clausola dice `the
# car is a current-year model` e il modello ha scelto `MakeModel`, quindi il secondo
# ramo accetta per la parola del nome che coincide -- la stessa sovrapposizione gia'
# dichiarata per CF28 (`ThisCarCost` / `PropCost`). Lo prende `clausole`, perche'
# quell'evidenza l'ha spostata lui nell'output e sotto `given that` ne resta una su
# due (`COH27_r{1,2,3}.json`: input `DrivQuality`, output `MakeModel`).
# Replay: `harness/risultati/replay_regole_coherence_20261103.txt`.
REGOLE_COERENZA = ("target", "clausole")
GIUNZIONE_EVIDENZE = " and that "


def clausola_domanda(query_norm: str, etichetta: str = "counterfactual") -> str:
    """Il testo della domanda fra le due ancore dell'etichetta, o ''.

    La forma e' quella dei template del benchmark (`genera.py:471` il
    controfattuale, `genera.py:465` la coerenza). Un testo che non la porta
    restituisce stringa vuota e **non** e' un rifiuto: la regola dice "non
    riconosco la forma", non "il target e' sbagliato".

    Il default e' l'etichetta controfattuale per non cambiare la firma che i
    chiamanti esterni usano (`replay_traduzione.py`,
    `test_norma_stato_e_ancoraggio.py`).
    """
    apertura, chiusura = FORME_DOMANDA.get(str(etichetta).strip().lower(), ("", ""))
    if not apertura:
        return ""
    i = query_norm.find(apertura)
    if i < 0:
        return ""
    resto = query_norm[i + len(apertura):]
    j = resto.find(chiusura)
    return (resto[:j] if j >= 0 else resto).strip()


def clausole_evidenza(query_norm: str, etichetta: str = "coherence") -> int | None:
    """Quante evidenze la domanda enuncia, o None se non si riconosce la forma.

    Per la coerenza il template e' fisso (`genera.py:465`):
    `Is it coherent that <target> given that <e1> and that <e2>?`, quindi il
    numero di clausole dopo `given that` e' 1 + quante ` and that ` compaiono.
    Non si scrive "2" perche' il numero deve venire dal testo della riga: se un
    template cambiera', la regola segue il testo, e una riga con una clausola in
    meno -- o con una clausola duplicata -- lo si vede nel conto.

    Il conteggio e' sul testo **dopo** l'ancora, perche' la frase del target sta
    prima e non e' un'evidenza. Una `FRASI` che contenesse " and that " al suo
    interno gonfierebbe il conto: misurato sulle righe di `benchmark.csv`, il
    conteggio esce 2 su **tutte** le righe di coerenza, e questo e' il controllo
    che scioglie quel rischio -- se una frase lo contenesse, il conto salirebbe e
    la riga buona si fermerebbe.
    """
    apertura, chiusura = FORME_DOMANDA.get(str(etichetta).strip().lower(), ("", ""))
    if not apertura:
        return None
    i = query_norm.find(apertura)
    if i < 0:
        return None
    resto = query_norm[i + len(apertura):]
    j = resto.find(chiusura)
    if j < 0:
        return None
    coda = resto[j + len(chiusura):]
    return 1 + coda.count(GIUNZIONE_EVIDENZE)


def ancoraggio_target(variabile: str, valore: str, query_norm: str, cit=None,
                      etichetta: str = "counterfactual") -> str:
    """'' se il target e' nella clausola della domanda, altrimenti il motivo.

    Tre rami, come in `_citazione_valida` se ne fanno due: la parola dello stato, o
    una parola del nome della variabile, o la citazione che il modello stesso ha
    scritto per il target. Il terzo ramo non e' una cortesia: e' l'unico che copre
    gli stati **booleani scritti come frase**, dove l'etichetta del grafo non ha
    alcuna forma in prosa. CF19 chiede `Theft=True` e la domanda scrive "the car has
    been stolen": li non compare ne' `true` ne' `theft`, e la riga buona muore.
    Contato su replay (02-11, 240 run,
    `harness/risultati/replay_regole_nuove_20261102.txt`): con i soli due rami la
    regola ferma 24 run e **tre di questi sono righe buone**, tutte CF19, e muoiono
    esattamente su quel foro -- 74 corrette contro le 77 del riferimento. Con il terzo
    ramo i fermati restano 21 e le buone perse zero.

    Non chiede che la clausola contenga il **valore** alla lettera, perche' nella
    forma controfattuale il valore del target e' enunciato come fatto osservato nella
    prima frase e ripreso nella domanda con la stessa perifrasi:
    `VehicleYear=Current` si scrive "the car is a current-year model".

    `etichetta` sceglie la forma della domanda da riconoscere: la funzione e' la
    stessa perche' il controllo e' lo stesso -- il target deve stare nella clausola
    che fa la domanda -- e cambia solo il testo che delimita quella clausola.
    """
    span = clausola_domanda(query_norm, etichetta)
    if not span:
        return "forma della domanda non riconosciuta"
    if _norm(valore) and _norm(valore) in span:
        return ""
    if any(w in span for w in _parole(variabile)):
        return ""
    if isinstance(cit, str) and cit.strip() and _norm(cit) in span:
        # la citazione vale solo se sta DENTRO la clausola interrogativa: una frase
        # copiata dalla clausola degli osservati non porta niente, e' l'antecedente
        # con un vestito diverso
        return ""
    return "il target non compare nella clausola della domanda"


def valida(grezzo: str, etichetta: str, query: str, path_rete: str | None = None,
           citazione_output=True, target_nella_domanda=False, coerenza="",
           stati_alias=""):
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

    `target_nella_domanda` accende l'ancoraggio del target alla clausola
    interrogativa, **solo** per l'etichetta `counterfactual` (vedi
    `ancoraggio_target`). Default spento perche' il protocollo primario e' quello
    misurato il 02-11 senza questa regola; la regola e' contata su replay
    (`harness/risultati/replay_regole_nuove_20261102.txt`), ma un conto offline non
    e' un metodo adottato. Quando accesa, l'esito lo dichiara: il JSON di ogni riga
    deve dire con quali regole e' stata verificata.

    `coerenza` accende le regole opzionali del ramo `coherence` (vedi
    `REGOLE_COERENZA` e `FORME_DOMANDA`): `"target"` ancora il target alla clausola
    `is it coherent that ...`, `"clausole"` pretende tante evidenze quante clausole
    la domanda enuncia, `"target,clausole"` le accende entrambe, `""` (default) le
    spegne. Vuole una stringa e non un booleano perche' le due regole colpiscono due
    guasti diversi e vanno contate separate prima di essere scelte insieme; il nome
    sta scritto nell'esito come quello della citazione, perche' due run con regole
    diverse non sono lo stesso protocollo.

    `stati_alias` accende la normalizzazione in prosa del confronto di stato (vedi
    `stato_con_alias` e `NORMALIZZAZIONI_STATO`): `""` (default) e' l'uguaglianza
    esatta del protocollo del 02-11, `"prosa"` e' il regime che il replay ha contato
    a 91 corrette su 240 (+14, zero perse), `"prosa+unita"` e' il candidato del 03-11
    a 92. Vuole un **nome** e non un booleano perche' le due pulizie hanno numeri
    diversi e una lista chiusa di parole diversa: un booleano direbbe "normalizza"
    senza dire con quali parole. Un nome che non sta in `NORMALIZZAZIONI_STATO`
    solleva, come un nome di regola di coerenza scritto male. Anche questa e' spenta
    di default: il conto offline non e' un metodo adottato, e qui la differenza non e'
    solo il punteggio -- e' anche la classe di errore, perche' dodici righe passano da
    `rifiutata` a `numero`. L'esito dichiara la scelta con il nome, perche' una riga
    verificata con la tabella degli alias non e' una riga verificata come le altre.
    """
    import tools  # _parse_features delle copie: virgolette tipografiche e via dicendo
    regole_cerenza = _regole_cerenza(coerenza)
    normalizzazione = _scelta_normalizzazione(stati_alias)
    esito = {"regole": list(LE_REGOLE), "scartate": [], "motivo": "",
             "etichetta": etichetta, "evidenze": None, "target": None,
             "stati_normalizzati": {},
             "citazione_output": _nome_regola(citazione_output),
             "coerenza": list(regole_cerenza)}
    if normalizzazione:
        esito["regole"] = esito["regole"] + ["stato-alias"]
        esito["stato_alias"] = normalizzazione
        # Il conto per **chiamata**, non per variabile: `stati_normalizzati` e' keyed
        # on variable e una riga che normalizza `OtherCarCost` due volte (in `input`
        # e in `output`, il caso INT24) la dichiara una volta sola. Il numero delle
        # normalizzazioni pubblicate il 02-11 (74, e 77 con le unita') e' il numero
        # delle chiamate, e senza questa lista non e' rigenerabile dal JSON della riga.
        esito["normalizzazioni"] = []
        esito["non_risolti"] = []

    def cerca_etichetta(valore, variabile, stati):
        """L'etichetta del grafo per il valore scritto, con il conto di contorno.

        Un'unica via per `output` e per ogni `input`, perche' il metro di confronto
        non puo' cambiare fra le due metà della stessa riga: e' la ragione per cui la
        sostituzione stava su `stato_del_grafo` e non su un ramo di `valida`.
        """
        etichetta = stato_con_alias(valore, variabile, stati, normalizzazione)
        if normalizzazione:
            if etichetta is None:
                esito["non_risolti"].append([variabile, str(valore)])
            elif etichetta != valore:
                esito["normalizzazioni"].append([variabile, str(valore), etichetta])
        return etichetta

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
    etichetta_out = cerca_etichetta(out_v, out, voc[out])
    if etichetta_out is None:
        esito["motivo"] = (f"output: {out_v!r} non e' uno stato di {out}"
                           + (f" e non ha alias in tabella (`{normalizzazione}`)"
                              if normalizzazione else "")
                           + f"; stati: {voc[out]}")
        return None, esito
    if etichetta_out != out_v:
        # la normalizzazione c'e' stata: si dichiara, perche' il dizionario che il
        # tool riceve non e' piu' quello che il modello ha scritto
        esito["stati_normalizzati"][out] = {"scritto": out_v,
                                            "etichetta": etichetta_out}
    # la citazione si confronta con la parola **scritta** dal modello, non con
    # l'etichetta del grafo: una normalizzazione non puo' irrigidire un altro gate
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
    esito["target"] = {out: etichetta_out}

    # --- ancoraggio del target alla domanda, solo controfattuale e solo se acceso
    if target_nella_domanda and str(etichetta).strip().lower() == "counterfactual":
        esito["regole"] = esito["regole"] + ["target-ancorato"]
        esito["clausola_domanda"] = clausola_domanda(query_norm)
        motivo = ancoraggio_target(out, out_v, query_norm, citazioni.get(out))
        if motivo:
            # il target non lo decide il codice: la riga si ferma con il motivo, e
            # chi legge vede la clausola su cui la regola ha guardato
            esito["motivo"] = f"output {out}={out_v!r}: {motivo}"
            return None, esito

    # --- coerenza: il target deve stare nella clausola della domanda -------------
    # Stessa regola, forma diversa: qui la clausola e' fra `is it coherent that` e
    # `given that`, e il foro che copre non e' l'antecedente -- nella coerenza non
    # c'e' antecedente -- ma lo scambio di target: il modello prende la variabile
    # che l'oracolo chiede come evidenza e fa la domanda su un'altra. Contato il
    # 03-11 da `diagnosi_coherence.py` sulle 27 righe con un numero che non e'
    # quello dell'oracolo: 24 su 27 sono quello scambio (otto task per tre
    # ripetizioni), e la regola ne ferma 21 run -- l'ottavo, COH27, lo prende il
    # controllo sulle clausole.
    if "target" in regole_cerenza and str(etichetta).strip().lower() == "coherence":
        esito["regole"] = esito["regole"] + ["coerenza-target"]
        esito["clausola_domanda"] = clausola_domanda(query_norm, "coherence")
        motivo = ancoraggio_target(out, out_v, query_norm, citazioni.get(out),
                                   etichetta="coherence")
        if motivo:
            esito["motivo"] = f"output {out}={out_v!r}: {motivo}"
            return None, esito

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
        etichetta_v = cerca_etichetta(valore, nome, voc[nome])
        if etichetta_v is None:
            scarta("vocabolario",
                   f"{valore!r} non e' uno stato di {nome}"
                   + (f" e non ha alias in tabella (`{normalizzazione}`)"
                      if normalizzazione else "")
                   + f"; stati: {voc[nome]}")
            continue
        if etichetta_v != valore:
            esito["stati_normalizzati"][nome] = {"scritto": valore,
                                                 "etichetta": etichetta_v}
        if nome == out:
            scarta("disgiunzione", "la variabile e' gia' il target della domanda")
            continue
        motivo = _citazione_valida(citazioni.get(nome), nome, valore, query_norm)
        if motivo:
            scarta("citazione", motivo)
            continue
        evidenza[nome] = etichetta_v

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

    # --- coerenza: tante evidenze quante clausole la domanda enuncia --------------
    # Dopo il controllo di cardinalita', perche' quello e' in vigore nel protocollo
    # misurato e una riga con zero evidenze deve continuare a dire la stessa cosa.
    # Qui il numero non lo decide il codice ne' il ramo del tool: lo decide la frase
    # della domanda, che il traduttore ha il compito di coprire tutta. `EVIDENZE_RICHIESTE`
    # dice "almeno una" perche' e' cio' che il tool pretende; la domanda di coerenza
    # ne enuncia due, e con una sola l'inferenza e' condizionata a meta' di quanto
    # la riga chiede -- un numero che passa comunque da `_confronta` e viene contato
    # come risposta.
    if "clausole" in regole_cerenza and str(etichetta).strip().lower() == "coherence":
        esito["regole"] = esito["regole"] + ["coerenza-clausole"]
        n_domanda = clausole_evidenza(query_norm, "coherence")
        esito["clausole_domanda"] = n_domanda
        if n_domanda is not None and n_domanda != len(evidenza):
            scarto = (f"; scartate: " + ", ".join(
                f"{s['variabile']}={s['valore']!r} ({s['regola']}: {s['dettaglio']})"
                for s in esito["scartate"])) if esito["scartate"] else ""
            esito["motivo"] = (f"coherence: la domanda enuncia {n_domanda} clausole "
                               f"di evidenza, la traduzione ne porta "
                               f"{list(evidenza)}{scarto}")
            return None, esito

    return {"input": evidenza, "output": {out: etichetta_out}}, esito


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
    Lo stesso vale per `target_nella_domanda`, che accende l'ancoraggio del target
    controfattuale ed e' spento di default. `coerenza` e' la stringa dei nomi delle
    regole opzionali del ramo `coherence` (vedi `valida`), e sta spenta (`""`) quanto
    quella. `stati_alias` e' il nome della normalizzazione in prosa del confronto di
    stato (`""` = uguaglianza esatta, il protocollo del 02-11; `prosa`, `prosa+unita`
    i due regimi contati su replay): e' sull'oggetto e non sulla chiamata perche' la
    normalizzazione cambia cosa arriva al tool, quindi cambia il metodo di una riga
    intera e il JSON deve poterlo dire. Nessuna di queste quattro opzioni fa parte
    del protocollo con cui sono presi i joule del 02-11, e accenderle perche' "non
    possono fare danni" vorrebbe dire chiamare lo stesso run due metodi diversi.
    """

    def __init__(self, cliente, citazione_output=True, target_nella_domanda=False,
                 coerenza="", stati_alias=""):
        self._cliente = cliente
        self._citazione_output = citazione_output
        self._target_nella_domanda = target_nella_domanda
        self._coerenza = coerenza
        self._stati_alias = stati_alias
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
                      citazione_output=self._citazione_output,
                      target_nella_domanda=self._target_nella_domanda,
                      coerenza=self._coerenza,
                      stati_alias=self._stati_alias)


# ---------------------------------------------------------------------------
# autoverifica: casi sintetici, nessun modello, nessuna query
# ---------------------------------------------------------------------------

def _casi():
    """(nome, grezzo, etichetta, query, esito atteso) e opzionalmente i flag di `valida`.

    Gli esiti attesi sono ('ok', traduzione) o ('no', motivo che deve comparire).
    Le query sono frasi del benchmark reale, per verificare la citazione su testo
    vero e non su un testo inventato che non nomina ne' variabili ne' stati.
    Un sesto elemento, facoltativo, sono i `kwarg` da passare a `valida`: serve
    alle regole non in vigore nel protocollo primario, che vanno provate accese
    E spente -- altrimenti il caso sintetico non dice quale protocollo fissa.
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
    # La forma di CF19 dell'held-out: un booleano scritto come frase. E' la riga che
    # distingue le due varianti della regola, quindi serve un testo suo.
    q_cf3 = ("We observed that the car has been stolen and that the car has no "
             "anti-theft device. What would the probability that the car has been "
             "stolen be if the world had been such that the car has no anti-theft "
             "device?")
    # La COH01 del benchmark reale, copiata da `benchmark/benchmark.csv`: due clausole
    # di evidenza e un target che condivide la parola `cost` con una delle due, che e'
    # il caso piu' difficile per l'ancoraggio e quindi il testo su cui provarlo.
    q_coh = ("Is it coherent that the medical cost is one thousand dollars given "
             "that the car is an older model and that the repair cost for this car "
             "is one thousand dollars?")
    # La domanda di INT24, copiata da `benchmark/benchmark.csv`: e' l'unica riga che il
    # candidato con le unita' sposta, quindi serve un testo suo e non uno inventato.
    q_int24 = ("What is the probability that the repair cost for the other car is ten "
               "thousand dollars if we intervene to make it so that the mileage is "
               "fifty thousand miles?")
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

        # -- ancoraggio del target alla domanda (regola spenta di default) ----------
        #
        # I quattro casi stanno insieme perche' e' la coppia a dire qualcosa: il primo
        # mostra che con la regola spenta -- il protocollo con cui sono presi i
        # joule del 02-11 -- la riga passa, il secondo che accesa si ferma, gli
        # ultimi due che una riga buona non viene uccisa, ciascuno per un ramo
        # diverso della regola.
        ("target = l'antecedente ipotetico, regola spenta: passa (default invariato)",
         '{"input": {"RuggedAuto": "Football"}, "output": {"Airbag": "False"},'
         ' "citazioni": {"RuggedAuto": "the car is as rugged as a football",'
         ' "Airbag": "the car has no airbag"}}',
         # La citazione del target E' una copia fedele della clausola `if the world
         # had been`, e la variabile e' un nodo vero con uno stato vero: nessuna
         # regola oggi in vigore puo' fermare questa riga. E' il foro da cui
         # passano i 27 run controfattuali dell'held-out.
         "counterfactual", q_cf,
         ("ok", {"input": {"RuggedAuto": "Football"}, "output": {"Airbag": "False"}}),
         {}),

        ("target = l'antecedente ipotetico, regola accesa: la riga si ferma",
         '{"input": {"RuggedAuto": "Football"}, "output": {"Airbag": "False"},'
         ' "citazioni": {"RuggedAuto": "the car is as rugged as a football",'
         ' "Airbag": "the car has no airbag"}}',
         "counterfactual", q_cf,
         ("no", "il target non compare nella clausola della domanda"),
         {"target_nella_domanda": True}),

        ("target = la domanda, regola accesa: passa",
         '{"input": {"Airbag": "True"}, "output": {"RuggedAuto": "Football"},'
         ' "citazioni": {"Airbag": "the car has an airbag",'
         ' "RuggedAuto": "the car is as rugged as a football"}}',
         # Il secondo ramo della regola e' quello che lavora, qui: lo stato
         # `Football` non compare nella clausola perche' la frase del benchmark
         # scrive "as rugged as a football", quindi vale la parola del nome.
         "counterfactual", q_cf,
         ("ok", {"input": {"Airbag": "True"}, "output": {"RuggedAuto": "Football"}}),
         {"target_nella_domanda": True}),

        ("booleano scritto come frase: lo salva la citazione del target",
         '{"input": {"AntiTheft": "False"}, "output": {"Theft": "True"},'
         ' "citazioni": {"AntiTheft": "the car has no anti-theft device",'
         ' "Theft": "the car has been stolen"}}',
         # CF19 dell'held-out, e il caso che separa le due varianti della regola.
         # Nella clausola interrogativa non compare ne' la parola dello stato (`true`)
         # ne' il nome della variabile (`theft`): la domanda dice "the car has been
         # stolen". Con i soli primi due rami questa riga buona si ferma -- e' il
         # prezzo che il regime `cf-target-stretto` del replay conta; con il terzo
         # ramo, sulla citazione del target dentro la clausola, passa.
         #
         # `citazione_output` sta a `False` perche' e' il regime su cui la regola va
         # misurata: quello dei joule del 02-11, dove la citazione del target non si
         # pretende. Con la pretesa accesa questa stessa riga si fermerebbe un gate
         # prima, alla regola `citazione` ("la citazione non nomina ne' la variabile
         # ne' lo stato": `theft` non e' nella frase), e il caso proverebbe l'ancoraggio
         # su una riga che non arriva nemmeno a guardarlo.
         "counterfactual", q_cf3,
         ("ok", {"input": {"AntiTheft": "False"}, "output": {"Theft": "True"}}),
         {"target_nella_domanda": True, "citazione_output": False}),

        # -- le due regole del ramo coherence (spente di default) --------------------
        #
        # Coppie dello stesso testo, come per il controfattuale: il primo membro dice
        # cosa fa il protocollo misurato il 02-11, il secondo cosa fa la regola accesa.
        # Righe inventate non servirebbero -- la domanda di coerenza ha una forma, e
        # la forma e' quella di `genera.py:465`.
        ("coherence: target scambiato con un'evidenza, regola spenta: passa",
         '{"input": {"MedCost": "Thousand", "ThisCarCost": "Thousand"},'
         ' "output": {"VehicleYear": "Older"},'
         ' "citazioni": {"MedCost": "the medical cost is one thousand dollars",'
         ' "ThisCarCost": "the repair cost for this car is one thousand dollars",'
         ' "VehicleYear": "the car is an older model"}}',
         # Le tre citazioni sono copie fedeli della query e i sei nomi sono nodi e
         # stati veri: nessuna delle quattro regole in vigore puo' fermare questa
         # riga, e infatti il 02-11 arriva al tool e stampa un numero che non e'
         # quello dell'oracolo. E' la classe dominante della diagnosi
         # (`harness/risultati/diagnosi_coherence_20261103.txt`): 24 run su 27, otto
         # task per tre ripetizioni. La regola ne ferma 21 -- sette task su otto --
         # e l'ottavo, COH27, lo prende la regola sulle clausole.
         "coherence", q_coh,
         ("ok", {"input": {"MedCost": "Thousand", "ThisCarCost": "Thousand"},
                "output": {"VehicleYear": "Older"}}),
         {"citazione_output": False}),

        ("coherence: target scambiato con un'evidenza, regola `target` accesa: si ferma",
         '{"input": {"MedCost": "Thousand", "ThisCarCost": "Thousand"},'
         ' "output": {"VehicleYear": "Older"},'
         ' "citazioni": {"MedCost": "the medical cost is one thousand dollars",'
         ' "ThisCarCost": "the repair cost for this car is one thousand dollars",'
         ' "VehicleYear": "the car is an older model"}}',
         "coherence", q_coh,
         ("no", "il target non compare nella clausola della domanda"),
         {"citazione_output": False, "coerenza": "target"}),

        ("coherence: la riga buona passa con entrambe le regole accese",
         '{"input": {"VehicleYear": "Older", "ThisCarCost": "Thousand"},'
         ' "output": {"MedCost": "Thousand"},'
         ' "citazioni": {"VehicleYear": "the car is an older model",'
         ' "ThisCarCost": "the repair cost for this car is one thousand dollars",'
         ' "MedCost": "the medical cost is one thousand dollars"}}',
         # Il falso positivo da escludere: il target `MedCost=Thousand` passa per la
         # parola dello stato (`thousand` sta nella clausola) e le clausole sono due
         # come le evidenze. Una regola che fermasse anche questa non sarebbe una
         # regola, sarebbe un modo di perdere righe.
         "coherence", q_coh,
         ("ok", {"input": {"VehicleYear": "Older", "ThisCarCost": "Thousand"},
                "output": {"MedCost": "Thousand"}}),
         {"citazione_output": False, "coerenza": "target,clausole"}),

        ("coherence: una clausola non tradotta, regola `clausole` accesa: si ferma",
         '{"input": {"VehicleYear": "Older"}, "output": {"MedCost": "Thousand"},'
         ' "citazioni": {"VehicleYear": "the car is an older model",'
         ' "MedCost": "the medical cost is one thousand dollars"}}',
         # L'altro foro: la regola ferma **18 run su 27** che arrivano al tool con una
         # sola delle due evidenze che la domanda enuncia
         # (`replay_regole_coherence_20261103.txt`). La diagnosi ne chiama `manca`
         # solo 3 (COH35), e non e' una contraddizione: la classe si decide dal
         # target prima che dall'insieme, quindi gli altri 15 stanno gia' nella classe
         # `target sbagliato`. `EVIDENZE_RICHIESTE` non li ferma -- il tool ne pretende
         # una -- e la domanda ne enuncia due: il condizionamento e' a meta' e il numero
         # che ne esce non e' quello chiesto, ma passa per una risposta.
         "coherence", q_coh,
         ("no", "la domanda enuncia 2 clausole"),
         {"citazione_output": False, "coerenza": "clausole"}),

        ("coherence: la stessa riga a meta', con le regole spente, passa",
         '{"input": {"VehicleYear": "Older"}, "output": {"MedCost": "Thousand"},'
         ' "citazioni": {"VehicleYear": "the car is an older model",'
         ' "MedCost": "the medical cost is one thousand dollars"}}',
         # Il gemello del caso sopra, senza kwarg: fissa cio' che il protocollo del
         # 02-11 ha davvero lasciato passare, e rende il paio leggibile -- la
         # differenza fra le due righe e' la regola, non il testo.
         "coherence", q_coh,
         ("ok", {"input": {"VehicleYear": "Older"}, "output": {"MedCost": "Thousand"}}),
         {"citazione_output": False}),

        ("coherence: nome di regola sconosciuto solleva, non si ignora",
         '{"input": {"VehicleYear": "Older"}, "output": {"MedCost": "Thousand"},'
         ' "citazioni": {"VehicleYear": "the car is an older model",'
         ' "MedCost": "the medical cost is one thousand dollars"}}',
         # Un regime scritto male nel replay darebbe il numero della regola che si
         # credeva di misurare: `valida` deve schiantarsi, non comportarsi da default.
         # Il caso e' atteso come `no` sul testo dell'eccezione, che `valida` lascia
         # salire: `autoverifica` lo conta solo se l'eccezione arriva fin qui.
         "coherence", q_coh,
         ("eccezione", "regola di coerenza sconosciuta"),
         {"coerenza": "target,clausole,aggiuntiva"}),

        # -- la normalizzazione in prosa del confronto di stato (spenta di default) -----
        #
        # Tre coppie sullo stesso testo, come per le due regole sopra: il primo membro
        # fissa cosa fa il protocollo con cui sono presi i joule del 02-11 (il rifiuto
        # dichiarato), il secondo cosa fa la regola accesa. I testi non sono inventati:
        # la prima coppia e' la forma di INT32 dell'held-out (`PropCost` scritta in
        # prosa di valuta), la seconda e' INT24 r1 riga per riga (grezzo da
        # `risultati_misura/b_composta/20261102_191401/INT24_r1.json`, query dalla riga
        # INT24 di `benchmark.csv`) ed e' la coppia che separa le due pulizie.
        ("stato in prosa di valuta, regola spenta: la riga si ferma (default invariato)",
         '{"input": {"Age": "Senior"}, "output": {"PropCost": "ten thousand dollars"},'
         ' "citazioni": {"Age": "the driver is senior",'
         ' "PropCost": "the property damage cost is ten thousand dollars"}}',
         "intervention",
         ("What is the probability that the property damage cost is ten thousand "
          "dollars if we intervene to make it so that the driver is senior?"),
         ("no", "non e' uno stato di PropCost"),
         {"citazione_output": False}),

        ("stato in prosa di valuta, `prosa` accesa: passa, e al tool va l'etichetta",
         '{"input": {"Age": "Senior"}, "output": {"PropCost": "ten thousand dollars"},'
         ' "citazioni": {"Age": "the driver is senior",'
         ' "PropCost": "the property damage cost is ten thousand dollars"}}',
         # Il punto che il 02-11 ha dovuto scoprire per la strada lunga: la riga si
         # salva solo se il dizionario che parte per il tool porta `TenThou` e non la
         # prosa, perche' `tools_corretto.py:368-388` sulla prosa non trova l'etichetta
         # e stampa l'intera distribuzione invece della probabilita' chiesta.
         "intervention",
         ("What is the probability that the property damage cost is ten thousand "
          "dollars if we intervene to make it so that the driver is senior?"),
         ("ok", {"input": {"Age": "Senior"}, "output": {"PropCost": "TenThou"}}),
         {"citazione_output": False, "stati_alias": "prosa"}),

        ("la stessa coppia con la parola di unita': `Mileage` in prosa",
         '{"input": {"OtherCarCost": "ten thousand dollars", "Mileage": "fifty '
         'thousand miles"}, "output": {"OtherCarCost": "ten thousand dollars"}, '
         '"citazioni": {"OtherCarCost": "ten thousand dollars", '
         '"Mileage": "fifty thousand miles"}}',
         # INT24 r1. Con `prosa` la riga si ferma lo stesso, ma non sul target: la
         # disgiunzione toglie `OtherCarCost` dall'`input` perche' e' anche l'output,
         # e l'unica evidenza che resta e' `Mileage`, che la pulizia senza unita' non
         # scioglie. Il motivo resta la cardinalita' dell'evidenza.
         "intervention", q_int24,
         ("no", "servono almeno 1 evidenza"),
         {"citazione_output": False, "stati_alias": "prosa"}),

        ("`prosa+unita` accesa: l'unita' di `Mileage` si scioglie e la riga passa",
         '{"input": {"OtherCarCost": "ten thousand dollars", "Mileage": "fifty '
         'thousand miles"}, "output": {"OtherCarCost": "ten thousand dollars"}, '
         '"citazioni": {"OtherCarCost": "ten thousand dollars", '
         '"Mileage": "fifty thousand miles"}}',
         # Il +1 del replay del 03-11, in una riga: il ramo vive o muore su questo
         # stato, perche' l'evidenza superstit della disgiunzione e' proprio `Mileage`.
         # Lo scarto di `OtherCarCost` va atteso, non lasciato passare: la riga passa
         # *perche' la disgiunzione* ha tolto il target dall'`input`, e una rimozione
         # che non si dichiara e' il difetto che questa variante combate.
         "intervention", q_int24,
         ("ok", {"input": {"Mileage": "FiftyThou"},
                 "output": {"OtherCarCost": "TenThou"}},
          [("OtherCarCost", "disgiunzione")]),
         {"citazione_output": False, "stati_alias": "prosa+unita"}),

        ("la lista chiusa delle parole e' il confine: l'elenco copiato non si risolve",
         '{"input": {"HomeBase": "Rural"}, "output": {"Age": "Adolescent|Adult|Senior"},'
         ' "citazioni": {"HomeBase": "kept in a rural area",'
         ' "Age": "the age of the driver"}}',
         # 14 dei 26 valori non risolti sono questa forma: tre stati in un campo che ne
         # vuole uno, copiati dall'elenco del prompt. Se la tabella ne risolvesse uno,
         # la normalizzazione avrebbe scelto lo stato al posto del modello -- ed e'
         # esattamente cio' che `alias_di` rende impossibile scartando le collisioni.
         # La citazione nominano la variabile, quindi non e' lei a fermare la riga:
         # il motivo deve restare il vocabolario, con la tabella dichiarata accanto.
         "backward_reasoning", q_cp,
         ("no", "non e' uno stato di Age"),
         {"citazione_output": False, "stati_alias": "prosa+unita"}),

        ("nome di normalizzazione sconosciuto solleva, non torna al letterale",
         '{"input": {"Age": "Senior"}, "output": {"PropCost": "ten thousand dollars"},'
         ' "citazioni": {"Age": "the driver is senior",'
         ' "PropCost": "the property damage cost is ten thousand dollars"}}',
         # Lo stesso obbligo della `coerenza`: un regime scritto male al replay
         # consegnerebbe il numero della normalizzazione che si credeva di misurare.
         "intervention",
         ("What is the probability that the property damage cost is ten thousand "
          "dollars if we intervene to make it so that the driver is senior?"),
         ("eccezione", "normalizzazione di stato sconosciuta"),
         {"stati_alias": "prosa+solenne"}),
    ]


def autoverifica(path_rete: str | None = None) -> int:
    """Esegue i casi sintetici sulla rete reale. Ritorna il numero di fallimenti.

    Un caso `ok` puo' chiedere anche le voci scartate: scartare in silenzio e'
    esattamente il difetto che la variante combate, quindi il conteggio degli
    scarti e' parte dell'aspettativa, non un dettaglio di stampa.

    I `kwarg` del sesto elemento arrivano a `valida` cosi' come sono: la regola
    `target-ancorato` non e' in vigore nel protocollo primario e il caso sintetico
    deve poterla provare accesa e spenta sulla stessa riga. Se il ciclo la
    ignorasse, i tre casi in fondo a `_casi()` direbbero tutti la stessa cosa e
    l'autoverifica passerebbe senza verificare niente.

    Un atteso puo' essere di tre tipi: `ok`, `no` ed `eccezione`. Il terzo e' per i
    parametri che non possono essere ignorati -- un nome di regola scritto male deve
    fermare chi lo usa, non girare con il default -- e `valida` deve sollevare.
    """
    caduti = 0
    scarti = 0
    for caso in _casi():
        nome, grezzo, etichetta, query, atteso = caso[:5]
        kwarg = caso[5] if len(caso) > 5 else {}
        tipo, dettaglio = atteso[0], atteso[1]
        scartate_attese = atteso[2] if len(atteso) > 2 else []
        traduzione = esito = None
        errore = ""
        try:
            traduzione, esito = valida(grezzo, etichetta, query, path_rete, **kwarg)
        except Exception as e:
            # il terzo tipo di esito atteso: una chiamata che deve **sollevare**, perche'
            # un parametro scritto male non puo' degradare silenziosamente al default.
            # senza questa branca il caso sull'eccezione risulterebbe un rifiuto con
            # `motivo` vuoto e stamperebbe "accettata, ma era da rifiutare", che e'
            # il contrario di quello che e' successo.
            errore = f"{type(e).__name__}: {e}"
        if esito:
            scarti += len(esito["scartate"])
        if tipo == "ok":
            trovate = [(s["variabile"], s["regola"]) for s in esito["scartate"]]
            va = traduzione == dettaglio and trovate == scartate_attese
            perche = "" if va else (f"traduzione {traduzione}, scartate {trovate}")
        elif tipo == "eccezione":
            va = bool(errore) and dettaglio in errore
            perche = errore or "nessuna eccezione, la riga e' passata a `valida`"
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
    # La tabella degli alias si genera dalle **etichette**, quindi e' una sola e non
    # dipende dalla normalizzazione: `prosa` e `prosa+unita` cambiano cio' che si
    # toglie al valore **scritto**, non le voci. Cio' che le tiene insieme e' una
    # proprieta' da controllare su questa rete, non da dare per assunta: la
    # forma-canone di un'etichetta deve riprendere l'etichetta stessa. Serve perche'
    # la lista delle unita' contiene `mile` e lo stato `Thousand` di `Mileage` scrive
    # la prosa `thousand`: se un domani un'etichetta contenesse una parola della
    # lista di pulizia, la sua voce sarebbe irraggiungibile dal regime e il numero
    # pubblicato (74/77 normalizzazioni) non sarebbe piu' rigenerabile.
    # La rete qui e' quella passata con `--rete`, non il default: le righe perturbate
    # del benchmark girano su un altro `.bif`, e una collisione la si deve vedere
    # prima di accendere `stati_alias` li'.
    stati_totali = sum(len(s) for s in voc.values())
    tabelle = {nome: alias_di(stati) for nome, stati in voc.items()}
    collisioni = [(nome, prosa, etichette) for nome, tab in tabelle.items()
                  for prosa, etichette in tab[1]]
    print(f"tabella alias: {sum(len(tab[0]) for tab in tabelle.values())} voci su "
          f"{stati_totali} stati, collisioni scartate: "
          + ("; ".join(f"{n}:{p}<-{','.join(e)}" for n, p, e in collisioni)
             or "nessuna"))
    for nome in sorted(NORMALIZZAZIONI_STATO):
        perse = [(v, s) for v, stati in voc.items() for s in stati
                 if cerca_stato_alias(_forma_prosa(s), v, stati, nome) != s]
        print(f"autoconsistenza (`{nome}`): {stati_totali - len(perse)} stati su "
              f"{stati_totali} si riprendono dalla propria prosa"
              + (f", perduti: {perse}" if perse else ""))
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
