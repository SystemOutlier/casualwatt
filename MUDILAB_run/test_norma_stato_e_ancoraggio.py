"""Test delle due regole misurate su replay il 02-11: normalizzazione di stato, ancoraggio del target.

Perche' esistono. Dopo l'analisi dei rami deboli
(`harness/risultati/analisi_rami_deboli_20261102.txt`) due correzioni sono state
proposte e nessuna delle due e' in vigore in produzione:

1. **normalizzazione del confronto di stato** (`inter`, 26 run su 60 fermati sul
   target): il modello scrive lo stato in prosa -- `PropCost='ten thousand dollars'`
   contro l'etichetta del `.bif` `TenThou` -- e il confronto letterale lo legge come
   stato inventato. Sulla riga INT39 lo stato booleano e' scritto come frase
   (`'no antilock braking system'` contro `True|False`) e nessuna normalizzazione
   derivabile dall'etichetta lo recupera: la regola ha un confine, e il confine va
   testato perche' e' la parte che impedisce alla normalizzazione di inventarsi uno
   stato.
2. **ancoraggio del target controfattuale alla clausola interrogativa**
   (27 run su 42 arrivati al tool con il target = l'antecedente manipolato). La
   regola ha tre rami, e il terzo -- vale la **citazione** del target se sta dentro
   la clausola -- esiste per un motivo misurato: CF19 ha `Theft=True` e la domanda
   dice "the car has been stolen", dove non compare ne' `true` ne' `theft`. Senza
   terzo ramo una riga buona si ferma; con il terzo ramo l'antecedente continua a
   fermarsi perche' la sua citazione sta **fuori** dalla clausola.

Cosa fissano, in ordine. Il default di `stato_del_grafo` e' l'uguaglianza esatta,
cioe' il protocollo con cui sono presi i joule del 02-11: se qualcuno montasse la
tabella degli alias li' dentro, la produzione cambierebbe senza il numero del replay
(`test_stato_del_grafo_di_produzione_confronta_letterale`). La tabella degli alias e'
iniettiva sulle 27 variabili della rete reale, e una collisione si scarta, non si
risolve a scelta (`test_alias_di_non_scegle_fra_due_etichette_uguale`). Il dizionario
che va al tool porta l'**etichetta**, non la prosa: e' il bug trovato il 02-11, che
faceva stampare al ramo `intervention` l'intera distribuzione invece della singola
probabilita' (`consegna/tools_corretto.py:368-388`) e faceva fallire `_confronta` su
tutte e 14 le righe che la regola avrebbe dovuto recuperare.

Cosa **non** fanno: non misurano l'effetto di una regola sul numero di righe corrette
-- quello e' il lavoro di `replay_traduzione.py`, il cui output del 02-11 sta in
`harness/risultati/replay_regole_nuove_20261102.txt`. Qui si fissa il comportamento
delle funzioni, non il loro guadagno.

Uso:  MUDILAB_COPIE=1 python -m pytest MUDILAB_run/test_norma_stato_e_ancoraggio.py -v

`python` e' l'interprete del venv di misura
(`MUDILabV/mudilab_env/Scripts/python.exe`), perche' il modulo importa la rete e le
copie di `consegna/`; pytest non sta in quel venv e non va installato li' -- si
raggiunge con `PYTHONPATH` dalla directory fuori repo, come in
`test_coherence_e_oracolo.py`.
"""
import sys
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

RETE = str(HERE / "consegna" / "insurance_grafo.bif")

_argv = sys.argv
sys.argv = [_argv[0]]                      # run_query legge argv all'import
import run_query  # noqa: F401,E402  monta `tools`/`agents` sulle copie e fa chdir
sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
import traduzione_controllata as TC        # noqa: E402
import replay_traduzione as RT            # noqa: E402

VOC = TC.vocabolario(RETE)

# Le due query sono le forme del benchmark (`benchmark/genera.py:471`), non frasi
# inventate: la prima e' la forma controfattuale di CF19, la seconda quella di
# INT39-`PropCost`. Un testo inventato non nominerebbe ne' variabili ne' stati e la
# regola passerebbe per motivi sbagliati.
Q_CF19 = ("We observed that the car has been stolen and that the car has no "
          "anti-theft device. What would the probability that the car has been "
          "stolen be if the world had been such that the car has no anti-theft "
          "device?")
Q_CF_AIRBAG = ("We observed that the car has an airbag and that the car is as rugged "
               "as a football. What would the probability that the car is as rugged as "
               "a football be if the world had been such that the car has no airbag?")


# -- 1. la forma-canone: dall'etichetta alla prosa --------------------------------

@pytest.mark.parametrize("etichetta,prosa", [
    ("TenThou", "ten thousand"),
    ("TwentyThou", "twenty thousand"),
    ("FiftyThou", "fifty thousand"),
    ("HundredThou", "hundred thousand"),
    ("FiveThou", "five thousand"),
    ("Million", "million"),
    ("Thousand", "thousand"),
    ("True", "true"),
    ("Current", "current"),
])
def test_forma_prosa_dall_etichetta(etichetta, prosa):
    """`Thou` e' l'unica abbreviazione che il grafo scrive e la prosa scioglie."""
    assert RT._forma_prosa(etichetta) == prosa


def test_pulisci_prosa_toglie_la_parola_di_moneta():
    """`dollars` non e' nell'etichetta: toglierla e' l'unica differenza reale.

    Misurata: `harness/risultati/analisi_rami_deboli_20261102.txt`, sezione 3. Su
    Inter le prose del target sono cinque di valuta ("ten thousand dollars",
    "hundred thousand", "hundred thousand dollars" su PropCost, OtherCarCost,
    ILiCost) e una no, la frase booleana di AntiTheft che nessuna forma-canone
    derivabile dall'etichetta recupera. Le scritture di valuta, "X dollars" e "X"
    liscio, devono convergere sulla stessa voce di tabella.
    """
    assert RT._pulisci_prosa(TC, "ten thousand dollars") == "ten thousand"
    assert RT._pulisci_prosa(TC, "hundred thousand") == "hundred thousand"
    assert RT._pulisci_prosa(TC, "USD 100000") == "100000"


# -- 2. l'iniettivita' della tabella, verificata e non assunta -------------------

def test_alias_di_e_iniettiva_su_tutte_le_variabili_della_rete():
    """Nessuna delle 27 variabili ha due etichette che scrivono la stessa prosa.

    E' il prerequisito della regola: con una collisione la tabella non e' piu' una
    traduzione, e' una scelta. Il replay la conta per regime
    (`etichette in collisione:`); qui la si fissa sul grafo reale.
    """
    collisioni = {nome: alias_di[1]
                  for nome, alias_di in ((n, RT.alias_di(stati))
                                         for n, stati in VOC.items()) if alias_di[1]}
    assert collisioni == {}, collisioni


def test_alias_di_non_scegle_fra_due_etichette_uguali():
    """Una collisione si scarta tutta, non si risolve tenendone una.

    Caso sintetico perche' la rete reale non ne produce (test precedente): `Yes` e
    `YES` sono due etichette che nella forma-canone sono la stessa parola. Una
    normalizzazione ambigua non e' una normalizzazione -- scegliere una delle due
    significa inventarsi lo stato, che e' cio' che il gate esiste per impedire.
    """
    tabella, collisioni = RT.alias_di(["Yes", "YES"])
    assert tabella == {}
    assert collisioni == [("yes", ["Yes", "YES"])]


def test_alias_di_deve_poter_scrivere_il_nome_scribacchiato():
    """Un'etichetta che collide non entra in tabella, ma le altre si'.

    Fissa che lo scarto e' per-voce e non per-tabella: una collisione sui `Thou`
    non toglie la voce `Million`, che buona lo e'. La collisione e' fra `TenThou`
    e `Ten Thousand`, che nella forma-canone sono la stessa prosa.
    """
    tabella, collisioni = RT.alias_di(["TenThou", "Ten Thousand", "Million"])
    assert collisioni == [("ten thousand", ["TenThou", "Ten Thousand"])]
    assert tabella == {"million": "Million"}


# -- 3. il default di produzione NON normalizza ----------------------------------

def test_stato_del_grafo_di_produzione_confronta_letterale():
    """La cucitura esiste per misurare un'alternativa, non per sostituirla.

    Il default e' l'uguaglianza esatta del protocollo del 02-11: se un domani
    qualcuno montasse la tabella qui dentro, la produzione cambierebbe metodo senza
    il numero del replay, che e' la regola dura del repository.
    """
    assert TC.stato_del_grafo("TenThou", "PropCost", VOC["PropCost"]) == "TenThou"
    assert TC.stato_del_grafo("ten thousand dollars", "PropCost",
                              VOC["PropCost"]) is None
    assert TC.stato_del_grafo("No antilock braking system", "AntiTheft",
                              VOC["AntiTheft"]) is None


def test_la_versione_alias_recupera_e_dichiara():
    """L'alias montato dal replay risolve la prosa e conta la coppia.

    Il conteggio non e' un dettaglio di stampa: `conto["normalizzato"]` e' il numero
    che dice quante righe il regime ha toccato, e una riga toccata non e' una riga
    buona.
    """
    conto = Counter()
    alias = RT._stato_alias(TC, conto)
    assert alias("ten thousand dollars", "PropCost", VOC["PropCost"]) == "TenThou"
    assert alias("hundred thousand", "PropCost", VOC["PropCost"]) == "HundredThou"
    assert alias("TenThou", "PropCost", VOC["PropCost"]) == "TenThou"
    assert conto["normalizzato"] == 2, conto
    assert conto["mancato"] == 0, conto


def test_la_versione_alias_lascia_stare_la_frase_che_non_c_entra():
    """Il confine della regola: lo stato booleano scritto come frase non si recupera.

    INT39: `'no antilock braking system'` contro gli stati `True|False` di
    `AntiTheft`. Non e' un buco dell'implementazione, e' il suo limite: la prosa non
    derivabile da un'etichetta non ha una traduzione, e il rifiuto resta onesto.
    """
    conto = Counter()
    alias = RT._stato_alias(TC, conto)
    assert alias("no antilock braking system", "AntiTheft",
                 VOC["AntiTheft"]) is None
    assert conto["mancato"] == 1, conto
    assert conto["normalizzato"] == 0, conto


# -- 4. l'ancoraggio del target controfattuale ------------------------------------

def test_clausola_domanda_prende_la_sola_clausola_interrogativa():
    """Lo span e' fra l'apertura e la clausola ipotetica, niente antecedente.

    E' tutta la regola: l'antecedente manipolato vive nella frase `if the world had
    been ...`, e un target che compare solo li' non e' il target della domanda.
    """
    span = TC.clausola_domanda(TC._norm(Q_CF_AIRBAG))
    assert span == "the car is as rugged as a football be", span
    assert "no airbag" not in span


def test_clausola_domanda_senza_apertura_restituisce_stringa_vuota():
    """Forma non riconosciuta != target sbagliato: la regola non decide il rifiuto.

    Un `intervention` o un `coherence` non portano l'apertura controfattuale; se
    questa stringa venisse letta come un motivo, la regola accesa fermerebbe meta'
    benchmark per la forma della frase.
    """
    assert TC.clausola_domanda(TC._norm("Given that X, how likely is Y?")) == ""
    assert TC.ancoraggio_target("Theft", "True",
                               TC._norm("how likely is it that the car is stolen"))\
        == "forma della domanda non riconosciuta"


def test_ancoraggio_terzo_ramo_salva_il_booleano_in_prosa():
    """CF19: ne' `true` ne' `theft` stanno nella clausola; la citazione si'.

    Il terzo ramo chiede la citazione **del target** dentro lo span, perche' nella
    forma controfattuale il valore del target e' enunciato come fatto osservato e
    ripreso nella domanda con la stessa perifrasi.
    """
    q = TC._norm(Q_CF19)
    assert TC.ancoraggio_target("Theft", "True", q, "the car has been stolen") == ""


def test_ancoraggio_ferma_l_antecedente_anche_col_terzo_ramo():
    """La citazione buona non e' un salvacondotto: dev'essere quella del target.

    Airbag=`False` e la sua citazione "the car has no airbag" sono l'antecedente
    ipotetico di Q_CF_AIRBAG: stanno nella query, non nella clausola interrogativa.
    Il ramo nuovo non deve recuperare questo foro -- e' il foro da cui passavano i
    27 run su 42 dell'held-out.
    """
    q = TC._norm(Q_CF_AIRBAG)
    assert TC.ancoraggio_target("Airbag", "False", q, "the car has no airbag") \
        == "il target non compare nella clausola della domanda"


def test_ancoraggio_passa_per_la_parola_dello_stato_o_del_nome():
    """I primi due rami restano, e sono quelli che non hanno bisogno della citazione.

    `VehicleYear=Current` si scrive "the car is a current-year model": la parola
    dello stato c'e' (`current`). `RuggedAuto=Football` nella domanda dice "as rugged
    as a football": la parola dello stato no, quella del nome (`rugged`) si'.
    """
    q = TC._norm(Q_CF_AIRBAG)
    assert TC.ancoraggio_target("RuggedAuto", "Football", q) == ""
    assert TC.ancoraggio_target("RuggedAuto", "Football", q, None) == ""
    assert TC.ancoraggio_target(
        "VehicleYear", "Current",
        TC._norm("What would the probability that the car is a current-year model "
                 "be if the world had been such that the car has no airbag?")) == ""


def test_l_ancoraggio_stretto_del_replay_ferma_cf19():
    """La variante a due rami, cioe' il prezzo del terzo ramo misurato a parte.

    `cf-target-stretto` contro `cf-target-domanda` esiste per rispondere a questo:
    il terzo ramo rescuede tre righe buone (CF19) o lascia passare anche le
    sbagliate? Se la variante e il modulo divergono su questa riga, il regime del
    replay non sta misurando la regola che crede di misurare.
    """
    stretto = RT._ancoraggio_senza_citazione(TC)
    q = TC._norm(Q_CF19)
    assert TC.ancoraggio_target("Theft", "True", q, "the car has been stolen") == ""
    assert stretto("Theft", "True", q, "the car has been stolen") \
        == "il target non compare nella clausola della domanda"
    # e sull'antecedente le due varianti coincidono: il terzo ramo non allarga quel foro
    qa = TC._norm(Q_CF_AIRBAG)
    assert stretto("Airbag", "False", qa, "the car has no airbag") \
        == TC.ancoraggio_target("Airbag", "False", qa, "the car has no airbag")


# -- 5. i regimi del replay: quali assi toccano -----------------------------------

def test_un_regime_accende_un_asse_solo():
    """`cf-target-domanda` non tocca la citazione ne' gli stati; `stati-alias` idem.

    I tre assi (citazione del target, confronto di stato, ancoraggio) sono ortogonali
    e i regimi li accendono uno per volta: se un regime montasse una sostituzione che
    non dichiara, il delta del replay non sarebbe attribuibile a una regola.
    """
    conto = Counter()
    sost, regola, kw = RT._pacchetto(TC, "cf-target-domanda", conto)
    assert sost == {} and regola is False and kw == {"target_nella_domanda": True}
    sost, regola, kw = RT._pacchetto(TC, "cf-target-stretto", conto)
    assert set(sost) == {"ancoraggio_target"}
    assert kw == {"target_nella_domanda": True}
    sost, regola, kw = RT._pacchetto(TC, "stati-alias", conto)
    assert set(sost) == {"stato_del_grafo"} and kw == {}
    assert regola is False, "il riferimento del confronto e' `output=libero`"
    sost, regola, kw = RT._pacchetto(TC, "output=libero", conto)
    assert sost == {} and regola is False and kw == {}


def test_il_conto_degli_alias_vive_quanto_il_regime_non_quanto_la_riga():
    """La cache di `stato_del_grafo` e' per (variabile, stati), non globale.

    Le righe perturbate girano su reti diverse: una tabella unica per tutta la
    esecuzione sarebbe la tabella della rete sbagliata, e il numero sarebbe perso
    senza essere visibile.
    """
    conto = Counter()
    alias = RT._stato_alias(TC, conto)
    assert alias("ten thousand dollars", "PropCost", VOC["PropCost"]) == "TenThou"
    # stessa variabile, stati diversi (rete perturbata): la voce non puo' arrivare
    # dalla cache della variabile, e `Thousand` qui non e' piu' ammessa
    stati_perturbati = ["Thousand", "Million"]
    assert alias("TenThou", "PropCost", stati_perturbati) is None
    assert alias("ten thousand dollars", "PropCost", stati_perturbati) is None


# -- 6. il giunto fra normalizzazione e dizionario per il tool --------------------

def test_valida_passa_al_tool_l_etichetta_e_non_la_prosa():
    """Il bug del 02-11, fissato: `{out: out_v}` invece di `{out: etichetta_out}`.

    Con la prosa nel dizionario, il ramo `intervention` di
    `consegna/tools_corretto.py:368-388` non trova `out_v` fra le etichette e stampa
    l'intera distribuzione: `_confronta` (`benchmark/genera.py:528-551`) vede quattro
    numeri invece di uno e la riga fallisce. Il regime `stati-alias` recuperava 74
    normalizzazioni e 0 righe, perche' il dizionario restava illeggibile.
    """
    grezzo = ('{"input": {"Age": "Senior"}, "output": {"PropCost": "ten thousand '
              'dollars"}, "citazioni": {"Age": "the driver is senior", '
              '"PropCost": "the property damage cost is ten thousand dollars"}}')
    query = ("What is the probability that the property damage cost is ten thousand "
             "dollars if we intervene to make it so that the driver is senior?")
    conto = Counter()
    originale = TC.stato_del_grafo
    TC.stato_del_grafo = RT._stato_alias(TC, conto)
    try:
        traduzione, esito = TC.valida(grezzo, "intervention", query, RETE,
                                      citazione_output=False)
    finally:
        TC.stato_del_grafo = originale
    assert traduzione["output"] == {"PropCost": "TenThou"}, traduzione
    assert traduzione["input"] == {"Age": "Senior"}, traduzione
    # la normalizzazione si dichiara, perche' il dizionario che va al tool non e'
    # piu' quello che il modello ha scritto
    assert esito["stati_normalizzati"]["PropCost"] == {
        "scritto": "ten thousand dollars", "etichetta": "TenThou"}
    assert esito["target"] == {"PropCost": "TenThou"}
    assert conto["normalizzato"] == 1, conto


def test_la_citazione_del_target_si_valuta_sulla_prosa_scritta():
    """Una normalizzazione non puo' irrigidire un altro gate.

    Il caso e' costruito per discriminare: `SocioEcon` scritto `upper middle`,
    citazione `the class is upper middle`. Con il valore **scritto** il gate passa
    (`upper middle` e' nella citazione); con l'**etichetta** del grafo la stessa
    citazione cadrebbe, perche' `_norm('UpperMiddle')` e' `uppermiddle`, tutto
    attaccato, e nessuna delle parole del nome (`socio`, `econ`) compare nella
    frase. Una regola che normalizza lo stato e poi pretende che la citazione sia
    riscritta con l'etichetta punisce la normalizzazione, non il modello.
    """
    grezzo = ('{"input": {"HomeBase": "Rural"}, "output": {"SocioEcon": "upper '
              'middle"}, "citazioni": {"HomeBase": "kept in a rural area", '
              '"SocioEcon": "the class is upper middle"}}')
    query = ("Given that the car is kept in a rural area, how likely is it that "
             "the class is upper middle?")
    conto = Counter()
    originale = TC.stato_del_grafo
    TC.stato_del_grafo = RT._stato_alias(TC, conto)
    try:
        traduzione, esito = TC.valida(grezzo, "backward_reasoning", query, RETE)
    finally:
        TC.stato_del_grafo = originale
    assert traduzione is not None, esito["motivo"]
    assert traduzione["output"] == {"SocioEcon": "UpperMiddle"}, traduzione
    assert "avviso_output" not in esito, esito


def test_senza_alias_la_stessa_riga_si_ferma_con_il_motivo():
    """Il prima: con il default di produzione la riga e' un rifiuto dichiarato.

    E' la coppia del test sopra, e serve a non leggere il numero del replay come se
    l'alias aggiungesse righe buone dal niente: toglie righe che il protocollo
    fermava per una ragione sua, e la ragione va vista prima di cambiarla.
    """
    grezzo = ('{"input": {"Age": "Senior"}, "output": {"PropCost": "ten thousand '
              'dollars"}, "citazioni": {"Age": "the driver is senior", '
              '"PropCost": "the property damage cost is ten thousand dollars"}}')
    query = ("What is the probability that the property damage cost is ten thousand "
             "dollars if we intervene to make it so that the driver is senior?")
    traduzione, esito = TC.valida(grezzo, "intervention", query, RETE,
                                  citazione_output=False)
    assert traduzione is None
    assert "non e' uno stato di PropCost" in esito["motivo"], esito["motivo"]
    assert esito["stati_normalizzati"] == {}


# -- 7. il candidato del 03-11: la parola di unita' (MIGLIA) ----------------------
#
# Nasce dai 26 valori in prosa che `stati-alias` non risolve, elencati con gli stati
# disponibili in `harness/risultati/replay_prosa_non_risolta_20261103.txt`. Sono tre
# famiglie, e una sola e' normalizzabile:
#   - 14 run hanno l'**elenco degli stati copiato dal prompt** nel campo del valore
#     (`Age: "Adolescent|Adult|Senior"`, `VehicleYear: "Current|Older"`, e altre sei
#     variabili): tre stati in un campo che ne vuole uno. Non e' un problema di forma,
#     e nessuna normalizzazione deve risolverlo -- scegliere quale dei tre tenere
#     significa inventarsi lo stato;
#   - 6 sono i booleani scritti come frase (`AntiTheft: "no antilock braking system"`,
#     `SeniorTrain: "not completed"`): la prosa non e' derivabile da `True|False`;
#   - **3** sono `Mileage: "fifty thousand miles"`, dove la forma-canone di `FiftyThou`
#     e' `fifty thousand` e di mezzo c'e' una parola di unita' -- la stessa distanza che
#     `dollars` ha per i costi, gia' risolta da `_pulisci_prosa`.
# Il candidato copre solo la terza, e la misura (`--riferimento stati-alias`,
# `harness/risultati/replay_regola_unita_20261103.txt`) dice **+1 corretta (INT24 r1),
# 0 perse, 77 normalizzazioni contro 74**. Non e' adottato.

Q_INT24 = ("What is the probability that the repair cost for the other car is ten "
           "thousand dollars if we intervene to make it so that the mileage is fifty "
           "thousand miles?")


def test_pulisci_prosa_con_unita_scoglie_l_unita_e_il_default_no():
    """L'unica differenza fra le due pulizie e' la lista chiusa delle parole.

    Fissa che il regime pubblicato il 02-11 non si muove: `miles` resta nel valore per
    `_pulisci_prosa`, e il numero di `stati-alias` (91) resta quello contato.
    """
    assert RT._pulisci_prosa(TC, "fifty thousand miles") == "fifty thousand miles"
    assert RT._pulisci_prosa_con_unita(TC, "fifty thousand miles") == "fifty thousand"
    # le monete gia' risolte lo restano, e una parola che non e' un'unita' non si tocca
    assert RT._pulisci_prosa_con_unita(TC, "ten thousand dollars") == "ten thousand"
    assert RT._pulisci_prosa_con_unita(TC, "not completed") == "not completed"


def test_il_candidato_recupera_mileage_e_si_dichiara():
    """La coppia che esiste per il regime: normalizzare e' un dato, non una riga buona."""
    conto = Counter()
    alias = RT._stato_alias(TC, conto, pulisci=RT._pulisci_prosa_con_unita)
    assert alias("fifty thousand miles", "Mileage", VOC["Mileage"]) == "FiftyThou"
    assert conto["normalizzato"] == 1, conto
    assert conto["mancato"] == 0, conto


def test_il_candidato_non_inventa_lo_stato_davanti_all_elenco_copiato():
    """Il confine, misurato prima di scrivere la regola: 14 dei 26 restano tali.

    Sono le famiglie che la normalizzazione **non** deve toccare. `Adolescent|Adult|
    Senior` lessicalizzato e' `adolescent adult senior`, e nessuna delle tre etichette
    emerge dalla pulizia: se emergesse, la regola avrebbe scelto un stato al posto del
    modello. `no antilock braking system` e' il caso di INT39 gia' dichiarato nel
    test in cima al file, e resta il limite della regola, non un buco.
    """
    conto = Counter()
    alias = RT._stato_alias(TC, conto, pulisci=RT._pulisci_prosa_con_unita)
    assert alias("Adolescent|Adult|Senior", "Age", VOC["Age"]) is None
    assert alias("Current|Older", "VehicleYear", VOC["VehicleYear"]) is None
    assert alias("no antilock braking system", "AntiTheft", VOC["AntiTheft"]) is None
    assert alias("socio-economic status. Values: Prole, Middle, UpperMiddle, Wealthy",
                 "SocioEcon", VOC["SocioEcon"]) is None
    assert conto["mancato"] == 4, conto
    assert conto["normalizzato"] == 0, conto


def test_le_unita_non_creano_collisioni_sulle_27_variabili():
    """La pulizia nuova non puo' far convergere due etichette della stessa variabile.

    E' l'iniettivita' del test in cima, ma sulla composizione forma-canone x pulizia:
    `TenThou` e `Ten Thousand` collidono gia' da sole e vengono scartate; qui si verifica
    che togliere `miles`/`mile` non aggiunga **nuove** collisioni. Se una ne emergesse,
    la tabella la scarta e il valore resta non risolto -- la perdita si vede, non si
    risolve a scelta.
    """
    nuove = {}
    for nome, stati in VOC.items():
        forme = [RT._pulisci_prosa_con_unita(TC, RT._forma_prosa(s)) for s in stati]
        ripetute = {f for f in forme if forme.count(f) > 1}
        if ripetute:
            nuove[nome] = sorted(ripetute)
    assert nuove == {}, nuove
    tabella, collisioni = RT.alias_di(VOC["Mileage"])
    assert collisioni == [], collisioni
    assert tabella["fifty thousand"] == "FiftyThou", tabella


def test_valida_con_il_candidato_porta_al_tool_l_etichetta_di_mileage():
    """La riga INT24, testo reale: con le unita' il dizionario e' leggibile dal tool.

    Il grezzo e' `risultati_misura/b_composta/20261102_191401/INT24_r1.json` e la query
    e' la riga INT24 di `benchmark.csv`. L'`output` riporta la variabile chiesta anche
    in `input`, e la regola `disgiunzione` la scarta li': l'unica evidenza che resta e'
    `Mileage`, e se quello stato non si risolve il ramo si ferma a zero evidenze. Per
    questo la stessa riga, senza la pulizia con le unita', e' un rifiuto.
    """
    grezzo = ('{"input": {"OtherCarCost": "ten thousand dollars", "Mileage": "fifty '
              'thousand miles"}, "output": {"OtherCarCost": "ten thousand dollars"}, '
              '"citazioni": {"OtherCarCost": "ten thousand dollars", "Mileage": "fifty '
              'thousand miles"}}')
    conto = Counter()
    originale = TC.stato_del_grafo
    TC.stato_del_grafo = RT._stato_alias(TC, conto, pulisci=RT._pulisci_prosa_con_unita)
    try:
        traduzione, esito = TC.valida(grezzo, "intervention", Q_INT24, RETE,
                                      citazione_output=False)
    finally:
        TC.stato_del_grafo = originale
    assert traduzione is not None, esito["motivo"]
    assert traduzione["input"] == {"Mileage": "FiftyThou"}, traduzione
    assert traduzione["output"] == {"OtherCarCost": "TenThou"}, traduzione
    assert esito["stati_normalizzati"]["Mileage"] == {
        "scritto": "fifty thousand miles", "etichetta": "FiftyThou"}
    assert conto["normalizzato"] == 3, conto
    # tre, non due: `OtherCarCost` e' scritta due volte (in `input` e in `output`) e
    # ogni passaggio la normalizza; `Mileage` una volta sola. E' la ragione per cui il
    # conteggio delle normalizzazioni del replay (74, 77) non e' il numero di righe.

    TC.stato_del_grafo = RT._stato_alias(TC, Counter())
    try:
        senza, esito_senza = TC.valida(grezzo, "intervention", Q_INT24, RETE,
                                       citazione_output=False)
    finally:
        TC.stato_del_grafo = originale
    assert senza is None
    assert "servono almeno 1 evidenza" in esito_senza["motivo"], esito_senza["motivo"]


def test_alias_unita_accende_un_asse_solo_contro_stati_alias():
    """Il nuovo regime differisce da `stati-alias` per la sola funzione di pulizia.

    Se montasse anche un kwarg o cambiasse `citazione_output`, il +1 del replay non
    sarebbe attribuibile alla parola di unita'.
    """
    assert "alias+unita" in RT.REGIMI, RT.REGIMI
    conto = Counter()
    base = RT._pacchetto(TC, "stati-alias", conto)
    candidato = RT._pacchetto(TC, "alias+unita", conto)
    assert set(base[0]) == set(candidato[0]) == {"stato_del_grafo"}
    assert base[1] == candidato[1] is False
    assert base[2] == candidato[2] == {}
    assert base[0] is not candidato[0], "le due chiusure non sono la stessa funzione"
