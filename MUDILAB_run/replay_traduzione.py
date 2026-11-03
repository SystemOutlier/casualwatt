"""Replay offline della verifica di traduzione: cosa cambierebbe una regola, senza modelli.

Perche' esiste. `b_verificata` sull'dev (81 righe, 01-11) raddoppia le risposte
corrette di b_base -- 15 contro 6 -- e pero' fallisce 46 righe su 81 contro le 36
di b_base: la verifica rifiuta piu' righe di quante ne recuperi. Contate su
`harness/risultati/b_verificata/20261101_174518`, 40 refusi su 45 righe con output
leggibile colpiscono la **citazione dell'output**, e fra quelle 20 hanno il target
giusto e 20 ce l'hanno sbagliato: come filtro e' una moneta. Prima di toccare una
regola serve pero' il numero completo, non questa frazione: le 20 righe con il
target giusto non sono 20 risposte corrette in piu', perche' una riga si gioca
anche sull'etichetta e sul numero che il tool stamperebbe.

Cosa fa. Riprende i JSON gia' scritti dallo screening -- testo del traduttore,
etichetta del classificatore, rete -- e riesegue da li' in poi la parte che non
ha bisogno del modello: `traduzione_controllata.valida` con le regole scelte,
`tools.cau_inference` sul dizionario verificato, `_confronta` di genera.py contro
l'oracolo. Niente Ollama, niente calore, niente energia: risponde a "con questa
regola quante righe diventano corrette", non a "quanto costano".

Perche' e' tracciato. Le sue righe di output sono l'evidenza sotto la correzione
della regola `citazione` sull'output: senza questo file quella correzione e'
un'opinione. `confronta` e' la stessa funzione che valuta i run reali, quindi il
replay e il run reale usano lo stesso metro e la stessa tolleranza.

Cosa non fa. Non riclassifica: l'etichetta e' quella che il modello ha scritto nel
run reale, perche' la classificazione e' un passo di modello. Una variante che
cambia il classificatore (`b_esempi`) va schermata davvero, non riproducibile qui.

Uso:  MUDILAB_COPIE=1 python replay_traduzione.py harness/risultati/b_verificata/20261101_174518
      --regole output=obbligatorio|output=se-citata|output=libero|libero+parola-stato|senza-verbatim|cf-target-domanda|cf-target-stretto|stati-alias|coh-target|coh-clausole|coh-entrambe|alias+coh-entrambe|alias+unita
      (default: tutti e tredici, a confronto; --riferimento output=libero conta i delta
      contro il protocollo con cui sono presi i joule del 02-11, e contro un qualsiasi
      altro regime se ne serve un altro -- `alias+unita` si legge contro `stati-alias`)

Gli ultimi tre regimi sono le due regole chieste il 02-11 dopo l'analisi dei rami
deboli (`harness/risultati/analisi_rami_deboli_20261102.txt`): `cf-target-domanda`
accende l'ancoraggio del target controfattuale alla clausola interrogativa,
`cf-target-stretto` e' la stessa regola pero' senza il terzo ramo sulla citazione,
e serve a misurare cosa vale quel ramo; `stati-alias` normalizza il confronto fra
lo stato scritto in prosa e l'etichetta del `.bif`. Il conto, fatto il 02-11 sui 240
run di `risultati_misura/b_composta/20261102_191401`
(`harness/risultati/replay_regole_nuove_20261102.txt`): `cf-target-domanda` 77
corrette come il riferimento, 21 run fermati prima del tool e nessuna riga buona
persa; `cf-target-stretto` 74, tre buone uccise su CF19; `stati-alias` 91, +14 e zero
perse, con 74 normalizzazioni e 12 righe che dal rifiuto passano a `numero` perche'
l'alias smette di fermare un errore di variabile.

Il tredicesimo regime, `alias+unita`, e' il candidato uscito il 03-11 dall'elenco dei
26 valori che `stati-alias` non risolve (`replay_prosa_non_risolta_20261103.txt`, dove
ogni valore e' stampato con gli stati disponibili accanto). Le 26 prose sono tre
famiglie, e una sola e' normalizzabile: 14 hanno l'elenco degli stati copiato dal prompt
nel campo del valore (`Age: "Adolescent|Adult|Senior"`), 6 sono booleani scritti come
frase (`AntiTheft: "no antilock braking system"`, `SeniorTrain: "not completed"`), 3
sono `Mileage: "fifty thousand miles"` -- la forma-canone di `FiftyThou` e' `fifty
thousand`, di mezzo c'e' una parola di unita', la stessa distanza che `dollars` ha per
i costi e che la pulizia gia' scioglie. Le altre 3 sono `SocioEcon` scritto come la
descrizione di `consegna/funtions_corretto.py:54`, copiata dal prompt. Il candidato
copre la terza famiglia e niente altro. Misurato contro `stati-alias`, non contro
`output=libero`, perche' l'asse in piu' e' uno solo
(`harness/risultati/replay_regola_unita_20261103.txt`): **92 corrette contro 91, zero
perse**, 77 normalizzazioni contro 74. Il +1 e' INT24 nella sola ripetizione r1: la
riga scrive `Mileage` in prosa e rimappa `OtherCarCost` dall'`input` all'`output`,
quindi la `disgiunzione` toglie l'evidenza doppia e quel che resta e' `Mileage` -- se
non si risolve, il ramo muore a zero evidenze. Le ripetizioni r2 e r3 parafrasano la
citazione di `Mileage` ("the mileage of the other car is fifty thousand miles", non
nella query) e cadono alla regola `citazione`, che la normalizzazione non tocca: per
questo 3 normalizzazioni in piu' fanno 1 riga in piu', non 3.

I regimi `coh-*` sono la richiesta n. 16, quella di una "regola di forma per il
coherence", e stanno qui perche' la prima cosa da sapere era se quella regola avesse
un soggetto: `diagnosi_coherence.py` ha contato che 27 righe su 42 del ramo passano
il gate e ricevono un numero che non e' quello dell'oracolo, quindi la regola non
poteva essere sulla *forma del dizionario*. Le due che stanno in `valida` sono
sulla forma della **domanda**: `coh-target` ancora il target alla clausola `is it
coherent that ... given that ...`, `coh-clausole` pretende tante evidenze quante
clausole la domanda enuncia, `coh-entrambe` le accende insieme e
`alias+coh-entrambe` le misura sopra il regime che aggiunge corrette, per vedere se
si tolgono a vicenda righe buone. Il conto, fatto il 03-11 sugli stessi 240 run
(`harness/risultati/replay_regole_coherence_20261103.txt`): `coh-target` ferma 21 run
e `coh-clausole` 18, `coh-entrambe` 27 -- cioe' tutti quelli che arrivavano al tool
-- e in tutti e tre le corrette restano **77 come il riferimento, zero perse**; nel
ramo, a regole accese, non resta nessun `numero` (18 corrette su 60, 42 rifiuti
dichiarati). `alias+coh-entrambe` sta a 91 come `stati-alias`: le 14 recuperate sono
in `cond_prob` e `inter`, e i 3 run di COH24 che l'alias portava da `rifiutata` a
`numero` tornano `rifiutata` per la regola sulle clausole.

Nessuna delle regole e' in vigore in produzione: i due regimi controfattuali e i tre
di coerenza non muovono il punteggio, e il regime degli stati lo muove ma con un
effetto collaterale dichiarato. Il metodo in produzione resta quello misurato il
02-11, perche' 'confrontare non significa adottare'.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

REGIMI = ("output=obbligatorio", "output=se-citata", "output=libero",
          "libero+parola-stato", "senza-verbatim",
          "cf-target-domanda", "cf-target-stretto", "stati-alias",
          "coh-target", "coh-clausole", "coh-entrambe", "alias+coh-entrambe",
          "alias+unita")

# Nell'ordine delle colonne di `benchmark.csv`: serve per stampare il "per ramo",
# che e' l'unico modo di vedere che una regola su un ramo ne sposta un altro.
RAMI = ("cond_prob", "inter", "coherence", "counterfactual")

# Le due regole alternative, misurate qui e non nel modulo: `valida` chiama
# `_citazione_valida` per nome globale, quindi sostituirla su `TC` per la durata
# del replay basta, e il protocollo in produzione resta quello scritto nei JSON.
# Perche' vale la pena misurarle: sull'dev di `b_composta` (01-11, 18:31) nove
# righe corrette in `b_esempi` vengono rifiutate qui, e il motivo e' sempre
# "citazione non presente nella query". Leggendole una per una si vede che il
# modello riscrive la frase con un soggetto diverso (`the vehicle is an older
# model` contro `the car is an older model`), tenendo pero' la parola dello stato.
# La pretesa che l'intera frase sia un sottostringa della query punisce la
# parafrasi, non l'invenzione; e su CND02 l'invenzione c'e' davvero
# (`Normal` contro `cautious`), quindi la regola nuova va provata su entrambi i
# casi, non solo su quelli che recupera.
#
# `libero+parola-stato`, misurata (01-11, 19:31, cartella 20261101_183106): 16
# corrette contro le 32 di `output=libero` sulle stesse identiche risposte dei
# modelli, e 50 righe rifiutate contro 20. Non e' una rilassatura: sostituisce
# l'intera verifica invece di togliere una clausola, e con lei sparisce il
# fallback sulla variabile -- che e' la via per cui passa quasi ogni citazione,
# perche' un valore come `Total` o `Ransom` nella query non c'e' mai alla lettera.
# Fra le righe che questa regola lascia arrivare al tool una (`INT26`) porta
# `bad allocation`: e' l'incidente dei 26 GB, e la regola in produzione lo stava
# impedendo.
#
# `senza-verbatim`, misurata (01-11, stessa cartella e stessi testi): **40 corrette
# contro le 32** di `output=libero`, con l'ottava in piu' che si chiama
# CND14 CND21 CND26 CND33 CND38 COH01 INT21 INT33 e **nessuna riga buona persa** --
# le otto si aggiungono, non si scambiano, e i rifiuti scendono da 20 a 10. Il
# costo non e' nel conteggio ma nel tipo di errore: su CND02, l'invenzione
# dichiarata (`Normal` contro `cautious`), la regola A rifiuta la riga e la regola
# C la porta al tool, che stampa 0,704 contro lo 0,221 atteso. Con A un'invenzione
# diventa una riga fallita dichiarata; con C diventa una risposta sbagliata
# confidente. INT26 torna a `bad allocation` anche con C. Sono i due numeri che
# decidono la regola, e la regola e' una scelta di protocollo: non viene cambiata
# qui dentro.
#
# Ordine di grandezza per chi legge: 40/81 sarebbe il nuovo massimo su dev, sopra
# `b_composta` (32) e sotto il tetto dell'unione delle cinque varianti (43).
def _regola_parola_stato(TC):
    """La citazione regge se la parola che porta il valore compare nella query."""
    def versione(cit, variabile, valore, query_norm):
        if not isinstance(cit, str) or not cit.strip():
            return "citazione assente o vuota"
        c = TC._norm(cit)
        if not c:
            return "citazione senza parole"
        v = TC._norm(valore)
        if v and v in query_norm:
            return ""
        return "la parola dello stato non compare nella query"
    return versione


def _regola_senza_verbatim(TC):
    """La regola di produzione senza il solo gate sulla frase: vale la parola dello
    stato o quella della variabile, anche se la citazione e' una parafrasi.

    E' la rilassatura che i commenti sopra descrivono come ipotesi, riscritta da
    `_citazione_valida` clausola per clausola: cambia un gate, non l'intera
    verifica. Misurarla era il modo di sapere se le nove righe perse da
    `b_composta` contro `b_esempi` si recuperano senza perdere CND02.
    """
    def versione(cit, variabile, valore, query_norm):
        if not isinstance(cit, str) or not cit.strip():
            return "citazione assente o vuota"
        c = TC._norm(cit)
        if not c:
            return "citazione senza parole"
        if TC._norm(valore) and TC._norm(valore) in c:
            return ""
        if any(w in c for w in TC._parole(variabile)):
            return ""
        return "la citazione non nomina ne' la variabile ne' lo stato"
    return versione


# -- il regime `stati-alias`: la prosa del modello come sinonimo dell'etichetta -------
#
# Perche' si misura qui e non in produzione. `valida` confronta la stringa scritta
# dal traduttore con le etichette del `.bif` a uguaglianza esatta, e sull'held-out
# del 02-11 quel confronto ferma il target di 26 run `inter` su 60: nove task per tre
# ripetizioni, meno la prima ripetizione di INT35 che si era gia' fermata sulla
# cardinalita' (`analisi_rami_deboli_20261102.txt`, sezioni 2 e 3). Cosa fa l'alias su
# quei nove, riga per riga: INT04, INT07, INT32, INT35 diventano corrette; INT16,
# INT19, INT27 arrivano al tool con il numero sbagliato perche' la prosa e' legittima
# ma la variabile no (`PropCost` dove l'oracolo chiede un altro costo); INT39 resta
# ferma perche' lo stato booleano e' scritto come frase; INT24 resta ferma su un altro
# gate, e questo va detto perche' e' un cambio di motivo: normalizzato l'output, cadono
# in `input` la ripetizione del target (disgiunzione) e `Mileage='fifty thousand
# miles'` (vocabolario), e la riga si ferma sulla cardinalita'.
#
# La normalizzazione che si vorrebbe provare e' una tabella di sinonimi generata
# **dalle etichette stesse**, non scritta a mano: `HundredThou` ->
# "hundred thousand", perche' il CamelCase spezza e `Thou` e' l'abbreviazione di
# `Thousand` nel `.bif` della relatrice. Generarla dal grafo e' quello che rende il
# controllo verificabile: la tabella e' la stessa per tutte le righe e si puo'
# dichiarare iniettiva variabile per variabile, che e' il prerequisito per non
# inventarsi uno stato.
#
# Cio' che NON copre, e va detto prima del numero: gli stati booleani scritti come
# frase, cioe' il caso di INT39 qui sopra. `AntiTheft='no antilock braking system'`
# contro le etichette `True|False` non ha alcuna forma in prosa derivabile
# dall'etichetta, e nessuna delle regole sotto lo recupera. La normalizzazione degli
# stati non e' la risposta a quel caso, e il numero del regime va letto con questa
# riga esclusa.
#
# Misurata (02-11, 240 run di `risultati_misura/b_composta/20261102_191401`, output
# in `harness/risultati/replay_regole_nuove_20261102.txt`): **91 corrette contro le
# 77** di `output=libero`, +14 e **zero perse** -- CND08, INT04, INT07, INT32 e INT35,
# quattro task per tre ripetizioni e INT35 per due. 74 normalizzazioni, 26 prose non
# risolte (INT39 con le sue tre ripetizioni sta qui), 0 collisioni di tabella sulle
# 27 variabili. Il prezzo non e' nel saldo: 12
# righe passano da `rifiutata` a `numero` (COH24, INT16, INT19, INT27) perche' sono
# errori veri di **variabile** -- l'oracolo chiede `ThisCarCost`, il modello scrive
# `PropCost` -- e il confronto letterale le fermava per un motivo che non c'entrava.
# La regola non e' adottata: questo numero dice cosa vale, non cambia il metodo in
# produzione, che e' una decisione separata e vuole un run misurato.
PAROLE_VALUTA = ("dollars", "dollar", "usd")
ESPANSIONI = {"thou": "thousand"}

# La lista chiusa per la variante con le unita' (`alias+unita`, candidato del 03-11).
# Non e' "togli l'ultima parola", e non e' un vocabolario di unita' generico: sono le
# **due** parole che compaiono davvero nei 26 valori non risolti, e sono le unita' che
# il grafo puo' scrivere -- `Mileage` in miglia, i costi in dollari. Il resto dei 26 non
# lo tocca: 14 sono l'elenco degli stati copiato dal prompt (`adolescent adult senior`),
# 6 sono booleani scritti come frase, 3 sono la descrizione di `cau_reference`
# copiata nell'output (vedi `harness/risultati/replay_prosa_non_risolta_20261103.txt`).
PAROLE_UNITA = PAROLE_VALUTA + ("miles", "mile")


def _forma_prosa(etichetta: str) -> str:
    """La prosa che un'etichetta del grafo scrive di se' stessa, in forma-canone."""
    spezzato = re.findall(r"[A-Z]{2,}(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", str(etichetta))
    return " ".join(ESPANSIONI.get(w.lower(), w.lower()) for w in spezzato)


def _pulisci_prosa(TC, valore: str) -> str:
    """Il valore scritto senza la moneta e senza la punteggiatura."""
    return " ".join(w for w in TC._norm(valore).split() if w not in PAROLE_VALUTA)


def _pulisci_prosa_con_unita(TC, valore: str) -> str:
    """La stessa pulizia, con le unita' del grafo al posto della sola moneta.

    E' il candidato misurato il 03-11, non una regola in vigore: `Mileage` scrive
    `fifty thousand miles` e la forma-canone di `FiftyThou` e' `fifty thousand`, quindi
    la distanza fra le due e' una parola di unita' -- la stessa distanza che `dollars`
    ha per i costi, gia' risolta. Perche' stia in una variante e non in
    `_pulisci_prosa`: il regime `stati-alias` ha un numero pubblicato (91), e montare
    una seconda normalizzazione dentro la prima cambierebbe quel numero senza che
    nessuno l'abbia contato.
    """
    return " ".join(w for w in TC._norm(valore).split() if w not in PAROLE_UNITA)


def alias_di(stati: list) -> tuple:
    """({prosa: etichetta}, [(prosa, [etichette collisionanti])]) per una variabile.

    Il secondo valore e' l'iniettivita' verificata, non assunta: se due etichette
    della stessa variabile producono la stessa prosa, la voce viene **tolta** dalla
    tabella. Una normalizzazione ambigua non e' una normalizzazione: scegliere una
    delle due significa inventarsi lo stato, che e' esattamente cio' che il gate
    esiste per impedire.
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


def _stato_alias(TC, conto: Counter, pulisci=None):
    """Sostituzione di `TC.stato_del_grafo`: uguaglianza esatta, poi la tabella.

    La tabella si costruisce dall'elenco di stati che `valida` ha gia' in mano, non
    da un vocabolario globale: le righe perturbate girano su reti diverse e una
    tabella unica sarebbe una tabella della rete sbagliata. Per lo stesso motivo la
    cache e' chiave (variabile, tuple(stati)), non la sola variabile.

    `pulisci` e' l'unico asse che il candidato `alias+unita` muove rispetto a
    `stati-alias`, e il default e' la pulizia pubblicata il 02-11: una firma che
    cambiava il comportamento di default avrebbe spostato il numero di un regime gia'
    misurato, che e' esattamente cio' che le varianti esistono per evitare.

    Il `mancato` si stampa con la coppia **e** gli stati disponibili (03-11), perche'
    il conteggio da solo non risponde alla domanda che lo ha fatto nascere: dei 26
    valori in prosa non risolti dal regime, quali sono a non avere una forma-canone
    derivabile e quali no. Senza gli stati accanto, la riga `AntiTheft:no antilock
    braking system` e' un numero e non un verdetto.
    """
    cache = {}
    pulisci = pulisci or _pulisci_prosa

    def versione(valore: str, variabile: str, stati: list):
        if valore in stati:
            return valore
        chiave = (variabile, tuple(stati))
        tabella = cache.get(chiave)
        if tabella is None:
            tabella, collisioni = alias_di(stati)
            cache[chiave] = tabella
            for prosa, etichette in collisioni:
                conto[f"collisione:{variabile}:{prosa}"] += len(etichette)
        etichetta = tabella.get(pulisci(TC, valore))
        if etichetta is None:
            conto["mancato"] += 1
            conto[f"mancato:{variabile}:{valore} [{','.join(stati)}]"] += 1
            return None
        conto["normalizzato"] += 1
        conto[f"coppia:{variabile}:{valore} -> {etichetta}"] += 1
        return etichetta
    return versione


def _ancoraggio_senza_citazione(TC):
    """L'ancoraggio del target con i soli due rami sulla parola dello stato e del nome.

    E' la variante stretta, e serve a misurare cosa vale il terzo ramo: senza di
    questo numero non si sa se la citazione salva tre righe buone o ne lascia
    passare anche lei ventiquattro sbagliate. `valida` chiama `ancoraggio_target` per
    nome globale, quindi la sostituzione dura quanto il regime.

    Misurata (02-11, gli stessi 240 run): **74 corrette contro le 77** -- ferma 24
    run e tre di questi sono righe buone, tutte CF19 (`Theft=True` scritto "the car
    has been stolen"), che e' esattamente il foro che il terzo ramo copre. Con il
    terzo ramo, regime `cf-target-domanda`: 77 corrette, identiche al riferimento, e
    21 run fermati prima del tool.
    """
    def versione(variabile, valore, query_norm, cit=None, etichetta="counterfactual"):
        span = TC.clausola_domanda(query_norm, etichetta)
        if not span:
            return "forma della domanda non riconosciuta"
        if TC._norm(valore) and TC._norm(valore) in span:
            return ""
        if any(w in span for w in TC._parole(variabile)):
            return ""
        return "il target non compare nella clausola della domanda"
    return versione


def _pacchetto(TC, regime, conto: Counter):
    """({attributo di TC: funzione}, `citazione_output`, kwarg di `valida`).

    Un pacchetto per regime, su quattro assi ortogonali: la citazione del target, il
    confronto di stato, l'ancoraggio del target controfattuale, le due regole di
    coerenza. Le `sostituzioni` montano una versione alternativa di una funzione che
    `valida` chiama per nome globale -- `_citazione_valida` (come si valuta una
    citazione scritta), `stato_del_grafo` (come si confronta uno stato con le
    etichette del `.bif`), `ancoraggio_target` (quanti rami ha l'ancoraggio del
    controfattuale). I regimi di `citazione_output` non sostituiscono niente e
    cambiano solo il flag; i due regimi `cf-target-*` e i quattro `coh-*`/`alias+coh-*`
    accendono kwarg che il modulo gia' espone spenti -- e `alias+coh-entrambe` e'
    l'unico che monta un asse e accende l'altro, per misurare l'interazione. Cio' che
    un regime non tocca resta il default di produzione, scritto nei JSON del 02-11.

    Il `conto` serve alle sostituzioni di stato: una normalizzazione e' un dato, non
    una riga buona, e va elencata coppia per coppia.
    """
    if regime == "libero+parola-stato":
        return {"_citazione_valida": _regola_parola_stato(TC)}, False, {}
    if regime == "senza-verbatim":
        return {"_citazione_valida": _regola_senza_verbatim(TC)}, False, {}
    if regime == "cf-target-domanda":
        return {}, False, {"target_nella_domanda": True}
    if regime == "cf-target-stretto":
        return ({"ancoraggio_target": _ancoraggio_senza_citazione(TC)}, False,
                {"target_nella_domanda": True})
    if regime == "stati-alias":
        return {"stato_del_grafo": _stato_alias(TC, conto)}, False, {}
    if regime == "alias+unita":
        # Il candidato del 03-11 sui 26 valori non risolti: la stessa tabella di
        # `stati-alias`, con la pulizia che conosce anche `miles`. Un asse solo, per
        # poter leggere il delta come **quello** della parola di unita' -- e il
        # riferimento giusto e' `stati-alias`, non `output=libero`.
        return ({"stato_del_grafo": _stato_alias(
            TC, conto, pulisci=_pulisci_prosa_con_unita)}, False, {})
    # I tre regimi di coerenza accendono le due regole che il modulo espone spente,
    # separate perche' colpiscono due guasti diversi -- `diagnosi_coherence.py`: 24 run
    # su 27 con il target scambiato, 3 con un'evidenza in meno, e le due regole si
    # sovrappongono su 12 -- e `coh-entrambe` esiste per misurare se la combinazione
    # apre interferenze che i due soli no. Contato il 03-11: 21, 18 e 27 run fermati,
    # 77 corrette in tutti e tre i regimi
    # (`harness/risultati/replay_regole_coherence_20261103.txt`).
    # Come per i due regimi controfattuali, `citazione_output` sta a `False`: e' il
    # regime dei joule del 02-11, e una regola nuova va contata contro quello.
    if regime == "coh-target":
        return {}, False, {"coerenza": "target"}
    if regime == "coh-clausole":
        return {}, False, {"coerenza": "clausole"}
    if regime == "coh-entrambe":
        return {}, False, {"coerenza": "target,clausole"}
    if regime == "alias+coh-entrambe":
        # L'interazione fra i due interventi che valgono di piu': `stati-alias`
        # (+14 corrette) e' l'unico regime che ne aggiunge, e le due regole di
        # coerenza sono le uniche che possono togliergliele -- perche' normalizzare
        # la prosa rende l'insieme di evidenza piu' completo, e il controllo sulle
        # clausole guarda proprio la completezza. Se qui le corrette scendono sotto
        # le 91 di `stati-alias`, la scelta non e' ovvia e va riportata cosi'.
        return ({"stato_del_grafo": _stato_alias(TC, conto)}, False,
                {"coerenza": "target,clausole"})
    return ({}, {"output=obbligatorio": True, "output=se-citata": "se-citata",
                 "output=libero": False}[regime], {})


def _chiave(diagnostico: str) -> str:
    """La classe del motivo, non il motivo. Serve al `--motivi`.

    I testi di `valida` portano il nome della variabile, lo stato scritto e la
    lista degli stati: raggrupparli verbatim vorrebbe dire una riga per riga, che
    non e' un conto. Qui si collassa tutto cio' che e' *istanza* -- gli intervalli
    fra apici o fra parentesi quadre e i numeri -- cosi' il gruppo risponde alla
    domanda giusta: quale regola ferma, non quale riga. E' una perdita dichiarata:
    la riga individuale si legge sempre nel JSON del run, e questa chiave non la
    sostituisce.
    """
    t = re.sub(r"\[[^\]]*\]", "[...]", diagnostico)
    t = re.sub(r"'[^']*'", "'...'", t)
    t = re.sub(r'"[^"]*"', '"..."', t)
    t = re.sub(r"\d+[\.,]?\d*", "#", t.lower())
    return t[:46]


def _righe(cartella: Path):
    """I run con un testo di traduttore registrato: il materiale del replay.

    Reso come (elaborabili, escluse): una riga senza il passo `translator` non e'
    riproducibile e va contata a parte, perche' il numero in fondo al report dice
    quante righe il metro nuovo ha visto, non quante esistevano.
    """
    elaborabili, escluse = [], []
    for p in sorted(cartella.glob("*_r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        r = d.get("risultato") or {}
        passi = {s["step"]: s for s in (r.get("steps") or []) if "step" in s}
        if "translator" not in passi or not passi["translator"].get("text"):
            escluse.append(d.get("task_id"))
            continue
        elaborabili.append((d, r, passi, p))
    return elaborabili, escluse


def riproduci(d: dict, r: dict, passi: dict, pacchetto: tuple, gt: dict, TC, tools,
              _confronta):
    """(esito, dettaglio) per un regime dato, sullo stesso testo della riga reale.

    Il `pacchetto` arriva da `main`, costruito una volta per regime: le sostituzioni
    sono montate prima di chiamare questa funzione e la cache degli alias vive quanto
    il regime, non quanto la riga. Costruirla qui dentro vorrebbe dire richiudere
    `alias_di` per ogni riga e, soprattutto, montare una funzione mentre se ne
    valuta un'altra.
    """
    task_id = d["task_id"]
    riga_gt = gt[task_id]
    etichetta = str(r.get("etichetta") or "").strip().lower()
    if not etichetta:
        # lo stesso parser del run, ma dal modulo puro: `run_orchestrato` all'import
        # monta la pipeline di `run_query` e fa chdir nella consegna
        from etichette import etichetta_dal_testo
        etichetta = etichetta_dal_testo(passi["classificator"]["text"])
    rete = d.get("rete") or None

    regola, kw = pacchetto[1:]
    traduzione, esito = TC.valida(passi["translator"]["text"], etichetta,
                                  riga_gt["query"], rete, citazione_output=regola, **kw)
    if traduzione is None:
        return "rifiutata", esito["motivo"]
    if etichetta != riga_gt["etichetta_attesa"]:
        return "etichetta", f"{etichetta} invece di {riga_gt['etichetta_attesa']}"
    try:
        risposta = tools.cau_inference.func(etichetta, json.dumps(traduzione), rete)
    except Exception as e:
        return "tool", f"{type(e).__name__}: {e}"
    motivo = _confronta(riga_gt["ramo"], str(risposta), _atteso(riga_gt))
    return ("corretta" if motivo is None else "numero"), (motivo or "")


def _atteso(gt: dict):
    """La stessa tupla che costruisce valuta.py: probabilita' o estremi."""
    if gt["ramo"] == "counterfactual":
        return {"lower": float(gt["expected_lower"]), "upper": float(gt["expected_upper"]),
                "decisione": ""}
    return {"prob": float(gt["expected_probability"]), "decisione": gt["expected_decision"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella", help="la marca di uno screening, es. harness/risultati/b_verificata/<ts>")
    ap.add_argument("--regole", default=",".join(REGIMI))
    ap.add_argument("--riferimento", default="output=libero",
                    help="il regime contro cui contare il delta; `''` per non confrontare")
    ap.add_argument("--motivi", nargs="?", const="*", default=None, metavar="RAMI",
                    help="stampare il conto dei motivi per ramo (lista separata da "
                         "virgole, o `*` per tutti): senza di questo il report dice "
                         "quante righe si fermano, non su quale regola")
    a = ap.parse_args()

    argv = sys.argv
    sys.argv = [argv[0]]                      # run_query legge argv all'import
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools
    import traduzione_controllata as TC
    from benchmark.genera import _confronta
    import csv
    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}

    cartella = (HERE / a.cartella) if not Path(a.cartella).is_absolute() else Path(a.cartella)
    regimi = [x.strip() for x in a.regole.split(",") if x.strip()]
    for x in regimi:
        if x not in REGIMI:
            raise SystemExit(f"regime sconosciuto: {x!r}; validi: {', '.join(REGIMI)}")

    memorizzate, escluse = _righe(cartella)
    # La selezione dei motivi, validata subito: un ramo scritto male stamperebbe
    # un vuoto che sembra "nessun motivo" invece di "hai chiesto un ramo che non
    # esiste", e i quattro nomi sono gia' quelli di `RAMI`.
    rami_motivi = None
    if a.motivi is not None:
        rami_motivi = (list(RAMI) if a.motivi == "*"
                       else [x.strip() for x in a.motivi.split(",") if x.strip()])
        sconosciuti = [x for x in rami_motivi if x not in RAMI]
        if sconosciuti:
            raise SystemExit(f"ramo sconosciuto per --motivi: {', '.join(sconosciuti)}; "
                             f"validi: {', '.join(RAMI)}")
    # Il riferimento per primo, o i delta dei regimi che lo precedono non avrebbero
    # niente da confrontare e stamperebbero un vuoto come se fosse un risultato.
    if a.riferimento in regimi:
        regimi.insert(0, regimi.pop(regimi.index(a.riferimento)))
    print(f"cartella: {cartella.name}")
    # Il comando, riscritto nell'output: questo file e' l'evidenza sotto una regola,
    # e un'evoluzione senza la riga che l'ha prodotta e' un numero che nessuno puo'
    # rigenerare (AGENTS.md, sezione struttura dei file). Ricostruito dagli argomenti
    # parsed, non da `sys.argv`: `run_query` lo riscrive all'import, e un header che
    # perde l'interprete non e' piu' una riga di comando.
    print("comando: MUDILAB_COPIE=1 "
          f"{sys.executable} {Path(__file__).name} {a.cartella} "
          f"--regole {a.regole} --riferimento {a.riferimento}")
    print(f"righe con un testo di traduttore: {len(memorizzate)}, "
          f"senza: {len(escluse)}{(' (' + ', '.join(map(str, escluse)) + ')') if escluse else ''}")
    esiti_riferimento = {}
    for regime in regimi:
        conti = Counter()
        esempio = {}
        rami_conti = {}
        esiti_regime = {}
        diag = {}
        originale = {}
        conto = Counter()
        # Il pacchetto e' uno per regime, non una funzione per asse: un regime puo'
        # montare due sostituzioni (una citazione e un ancoraggio) e la riga che le
        # vede entrambe deve vederle insieme, come le vedrebbe una variante reale.
        # Le sostituzioni si montano su `TC` perche' `valida` chiama quelle funzioni
        # per nome globale; si smontano nel `finally`, perche' un `KeyboardInterrupt`
        # a meta' regime lascerebbe il modulo con la regola sbagliata per i regimi
        # che vengono dopo, e il numero stampato dopo sarebbe della regola sbagliata.
        pacchetto = _pacchetto(TC, regime, conto)
        for nome, versione in pacchetto[0].items():
            originale[nome] = getattr(TC, nome)
            setattr(TC, nome, versione)
        try:
            for d, r, passi, _p in memorizzate:
                esito, dettaglio = riproduci(d, r, passi, pacchetto, gt, TC, tools,
                                             _confronta)
                conti[esito] += 1
                esempio.setdefault(esito, f"{d['task_id']}: {dettaglio[:60]}")
                ramo = gt[d["task_id"]]["ramo"]
                rami_conti.setdefault(ramo, Counter())[esito] += 1
                esiti_regime[_p.name] = (ramo, esito)
                if rami_motivi and ramo in rami_motivi and dettaglio:
                    # il dettaglio vuoto e' la riga corretta: qui si contano i
                    # motivi per cui le altre si fermano, non le altre
                    diag.setdefault(ramo, Counter())[_chiave(dettaglio)] += 1
        finally:
            for nome, versione in originale.items():
                setattr(TC, nome, versione)
        n = sum(conti.values())
        print(f"\n--- {regime}: {n} righe riprodotte")
        for esito in ("corretta", "numero", "etichetta", "rifiutata", "tool"):
            if conti[esito]:
                print(f"  {esito:10s} {conti[esito]:3d}   es. {esempio.get(esito, '-')}")
        print("  per ramo (corrette / riprodotte): " + ", ".join(
            f"{ramo} {rami_conti[ramo]['corretta']}/{sum(rami_conti[ramo].values())}"
            for ramo in RAMI if ramo in rami_conti))
        for ramo in (rami_motivi or ()):
            if ramo in diag:
                # ordinato per conta decrescente: la prima riga di questo blocco e'
                # la regola che il ramo perde piu' spesso, che e' il candidato su
                # cui lavorare, non la piu' esotica
                print(f"  motivi di `{ramo}`:")
                for chiave, q in diag[ramo].most_common():
                    print(f"    {q:3d}  {chiave}")
        print(f"  corrette/prodotte = {conti['corretta']}/{n}")
        if conto:
            print(f"  normalizzazioni di stato: {conto['normalizzato']}, "
                  f"valori in prosa non risolti: {conto['mancato']}, "
                  f"etichette in collisione: "
                  f"{sum(v for k, v in conto.items() if k.startswith('collisione:')) or 0}")
            for chiave in sorted(conto):
                if chiave.startswith("coppia:"):
                    print(f"    {chiave[len('coppia:'):]} x{conto[chiave]}")
            for chiave in sorted(conto):
                if chiave.startswith("mancato:"):
                    print(f"    ! {chiave[len('mancato:'):]} x{conto[chiave]}")
        # Il delta contro il riferimento e' il numero che decide, non il totale:
        # una regola che aggiunge tre corrette togliendone due non e' un miglioramento.
        # E il conteggio delle sole corrette non basta nemmeno lui: una riga che
        # passa da `rifiutata` a `numero` non guadagna nulla e perde il rifiuto
        # dichiarato, che e' l'informazione che la regola primaria produce. Quindi
        # qui si stampano TUTTE le transizioni, grouped by (da, a).
        if esiti_riferimento and regime != a.riferimento:
            transizioni = {}
            for file, (ramo, es) in esiti_regime.items():
                prima = esiti_riferimento.get(file, ("", ""))[1]
                if prima and prima != es:
                    transizioni.setdefault((prima, es), []).append(file)
            print(f"  contro {a.riferimento}: "
                  f"{sum(len(v) for k, v in transizioni.items() if k[1] == 'corretta')}"
                  f" corrette in piu', "
                  f"{sum(len(v) for k, v in transizioni.items() if k[0] == 'corretta')}"
                  " corrette in meno")
            for (prima, dopo), file in sorted(transizioni.items()):
                task = ", ".join(sorted({f.split('_r')[0] for f in file}))
                print(f"    {prima} -> {dopo}: {len(file)} run ({task})")
            guadagnate = [f for f, (_r, es) in esiti_regime.items()
                          if es == "corretta"
                          and esiti_riferimento.get(f, ("", ""))[1] != "corretta"]
            perse = [f for f, (_r, es) in esiti_regime.items()
                     if esiti_riferimento.get(f, ("", ""))[1] == "corretta"
                     and es != "corretta"]
            for etichetta, elenchi in (("guadagnate", guadagnate), ("perse", perse)):
                if elenchi:
                    print(f"    {etichetta}: " + ", ".join(sorted(
                        {f.split('_r')[0] for f in elenchi})))
        if regime == a.riferimento:
            esiti_riferimento = esiti_regime


if __name__ == "__main__":
    main()
