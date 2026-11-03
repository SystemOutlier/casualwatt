"""Test delle due regole opzionali del ramo `coherence`, spente di default.

Perche' esistono. Sui 240 run misurati il 02-11
(`risultati_misura/b_composta/20261102_191401`) il ramo `coherence` ferma 42 righe
su 60, ma **27 di quelle 42 passano il gate**, ricevono un numero dal tool e quel
numero non e' quello dell'oracolo. `diagnosi_coherence.py` le classifica confrontando
l'insieme di evidenza **e il target** con `evidence_json`/`target_variable` di
`benchmark.csv`: 24 run (otto task) hanno il **target scambiato** -- il modello mette
la variabile dell'oracolo fra le evidenze e fa la domanda su un'altra -- e 3 (COH35)
hanno un'evidenza **manca**. Nessuna delle due classi e' intercettabile dalle quattro
regole in vigore: i nomi sono nodi veri, gli stati veri, le citazioni copie fedeli
della query -- e la query le contiene tutte e due le evidenze, quindi una citazione
omessa non e' una citazione inventata.

Cosa fissano, in ordine:

1. `clausola_domanda` con l'etichetta `coherence` prende lo span fra `is it coherent
   that` e `given that`, e non prende niente dal frammento dopo `given that` perche'
   li' stanno le evidenze, non il target;
2. `clausole_evidenza` conta le clausole di evidenza dal testo della domanda, non da
   una costante: 2 sul template reale, 3 su una domanda con una clausola in piu';
3. `coerenza="target"` ferma lo scambio di target e lascia passare la riga buona;
4. `coerenza="clausole"` ferma la riga tradotta a meta';
5. il default `""` non muove niente: le 27 righe che oggi arrivano al tool ci
   arrivano anche con il modulo aggiornato, perche' il protocollo con cui sono
   presi i joule del 02-11 e' quello, e una regola nuova si misura prima di
   accenderla (`replay_traduzione.py`, regimi `coh-target`/`coh-clausole`/
   `coh-entrambe`);
6. un nome di regola scritto male **solleva**: un regime con un refuso darebbe il
   numero della regola che si credeva di misurare.

Cosa **non** fanno: non misurano l'effetto sul conto delle righe corrette -- quello
e' il lavoro di `replay_traduzione.py` e il suo output va in
`harness/risultati/replay_regole_coherence_<data>.txt`. Qui si fissa il comportamento
delle funzioni, non il loro guadagno.

Uso:  MUDILAB_COPIE=1 python -m pytest MUDILAB_run/test_regole_coherence.py -v

`python` e' l'interprete del venv di misura
(`MUDILabV/mudilab_env/Scripts/python.exe`): il modulo importa la rete e le copie di
`consegna/`. pytest non sta in quel venv e non va installato li' -- si raggiunge con
`PYTHONPATH` dalla directory fuori repo, come in `test_coherence_e_oracolo.py`.
"""
import json
import sys
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

# Le due query sono righe reali di `benchmark/benchmark.csv` (COH01 e COH02), non
# frasi inventate: la forma e' quella del template `genera.py:465`, e una parafrasi
# di chi scrive i test produrrebbe una regola tarata sul proprio testo.
Q_COH01 = ("Is it coherent that the medical cost is one thousand dollars given that "
           "the car is an older model and that the repair cost for this car is one "
           "thousand dollars?")
Q_COH02 = ("Is it coherent that the car has an antilock braking system given that "
           "the driver is senior and that the customer is not a good student?")

# L'ultima tripletta e' il target, le precedenti le evidenze.
def _diz(voci):
    """Il JSON del traduttore dalle triplette (variabile, stato, citazione)."""
    return json.dumps({"input": {v: s for v, s, _ in voci[:-1]},
                       "output": {voci[-1][0]: voci[-1][1]},
                       "citazioni": {v: c for v, _, c in voci}})


RIGA_BUONA = _diz([
    ("VehicleYear", "Older", "the car is an older model"),
    ("ThisCarCost", "Thousand", "the repair cost for this car is one thousand dollars"),
    ("MedCost", "Thousand", "the medical cost is one thousand dollars")])

RIGA_SCAMBIO = _diz([
    ("MedCost", "Thousand", "the medical cost is one thousand dollars"),
    ("ThisCarCost", "Thousand", "the repair cost for this car is one thousand dollars"),
    ("VehicleYear", "Older", "the car is an older model")])
# `VehicleYear` e' un'evidenza della domanda, non il suo target: il modello lo mette
# in `output` e sposta `MedCost` fra le evidenze. Con le regole spente passa, ed e'
# esattamente il foro contato il 03-11.

RIGA_META = _diz([
    ("VehicleYear", "Older", "the car is an older model"),
    ("MedCost", "Thousand", "the medical cost is one thousand dollars")])
# Manca `ThisCarCost`, la cui frase e' nella query e il cui nome e' un nodo vero: le
# quattro regole in vigore non la vedono, perche' non c'e' niente da scartare -- il
# difetto e' una mancata estrazione, non un'estrazione falsa.


# -- 1. la clausola della domanda di coerenza -------------------------------------

def test_clausola_domanda_di_coerenza_prende_il_solo_target():
    """Lo span e' fra `is it coherent that` e `given that`: li' c'e' il target.

    Le due evidenze stanno dopo `given that`, quindi non entrano: se entrassero, la
    regola non distinguerebbe lo scambio di target -- che e' la classe dominante della
    diagnosi (`diagnosi_coherence.py`, 24 run su 27), e la distinzione e' tutta li'.
    """
    span = TC.clausola_domanda(TC._norm(Q_COH01), "coherence")
    assert span == "the medical cost is one thousand dollars", span
    assert "older model" not in span
    assert "repair cost" not in span


def test_clausola_domanda_senza_etichetta_resta_controfattuale():
    """Il default non e' cambiato: la firma che il replay gia' chiama e' la stessa.

    `replay_traduzione.py` e `test_norma_stato_e_ancoraggio.py` passano solo il
    testo. Se il default scivolasse su `coherence`, quelle chiamate leggerebbero una
    clausola diversa da quella che i numeri del 02-11 descrivono.
    """
    assert TC.clausola_domanda(TC._norm(Q_COH01)) == ""
    assert TC.clausola_domanda(TC._norm(Q_COH01), "coherence") != ""


def test_clausola_domanda_di_un_etichetta_senza_forma_restituisce_vuoto():
    """Forma non riconosciuta != riga sbagliata, e vale anche per l'intervento.

    `intervention` e `backward_reasoning` non stanno in `FORME_DOMANDA`: un default
    che cadesse su una delle due forme fermerebbe meta' benchmark per il testo della
    frase invece che per il contenuto.
    """
    assert TC.clausola_domanda(TC._norm(Q_COH01), "intervention") == ""
    assert TC.clausola_domanda("una domanda qualunque", "coherence") == ""


# -- 2. il conto delle clausole viene dal testo -----------------------------------

def test_clausole_evidenza_conta_le_clausole_del_template_reale():
    """Due sulle righe reali di coerenza: `genera.py:465` enuncia `e1 and that e2`.

    Misurato su tutte le righe di `benchmark.csv` con `ramo == coherence` (03-11): il
    conto esce 2 su 40 su 40. E' anche il controllo sul rischio della regola -- una
    `FRASI` che contenesse " and that " al suo interno gonfierebbe il conto e la riga
    buona si fermerebbe; su questo corpus non succede, e i due testi qui sono due del
    corpus, non due scritti per far tornare il numero.
    """
    assert TC.clausole_evidenza(TC._norm(Q_COH01), "coherence") == 2
    assert TC.clausole_evidenza(TC._norm(Q_COH02), "coherence") == 2


def test_clausole_evidenza_segue_il_testo_non_una_costante():
    """Tre clausole nel testo, tre nel conto: la regola legge, non assume.

    Se il numero fosse scritto a mano (`2`), una domanda con una clausola in meno o
    in piu' sarebbe gia' giudicata sul template sbagliato, e il rifiuto non direbbe
    niente di quello che la riga contiene.
    """
    tre = TC._norm("Is it coherent that the medical cost is a million dollars given "
                   "that the car is an older model and that the cushioning is "
                   "excellent and that the driver is cautious?")
    assert TC.clausole_evidenza(tre, "coherence") == 3
    assert TC.clausole_evidenza(TC._norm(Q_COH01), "counterfactual") is None
    assert TC.clausole_evidenza("nessuna forma riconosciuta", "coherence") is None


# -- 3. la regola `target`: ferma lo scambio, non la riga buona --------------------

def test_coerenza_target_ferma_lo_scambio():
    """La riga con il target preso fra le evidenze si ferma, con il motivo giusto."""
    traduzione, esito = TC.valida(RIGA_SCAMBIO, "coherence", Q_COH01, RETE,
                                  citazione_output=False, coerenza="target")
    assert traduzione is None
    assert esito["motivo"] == ("output VehicleYear='Older': il target non compare "
                               "nella clausola della domanda"), esito["motivo"]


def test_coerenza_target_lascia_passare_la_riga_buona():
    """La stessa domanda con il target giusto: `MedCost=Thousand` sta nella clausola.

    Senza questo test la regola sarebbe solo un modo di rifiutare: deve stare contro
    una riga che oggi e' corretta, e la discrimina la stessa cosa che ferma lo
    scambio -- la clausola, non la lista degli stati.
    """
    traduzione, esito = TC.valida(RIGA_BUONA, "coherence", Q_COH01, RETE,
                                  citazione_output=False, coerenza="target")
    assert traduzione == {"input": {"VehicleYear": "Older",
                                   "ThisCarCost": "Thousand"},
                          "output": {"MedCost": "Thousand"}}, traduzione
    assert "coerenza-target" in esito["regole"], esito["regole"]
    assert esito["motivo"] == ""


def test_coerenza_target_non_uccide_lo_stato_booleano_in_prosa():
    """COH02: `Antilock=True` si scrive "the car has an antilock braking system".

    Il secondo ramo -- una parola del nome nella clausola -- e' quello che lavora:
    l'etichetta `True` non compare nella frase, `antilock` (parte del nome) si'. E'
    l'analogo coerenziale di CF19, e il motivo per cui l'ancoraggio ha tre rami e non
    uno. Il secondo membro fissa che l'evidenza scambiata per target continua a
    cadere: la stessa citazione fedele, un'altra clausola.
    """
    assert TC.ancoraggio_target("Antilock", "True", TC._norm(Q_COH02),
                                etichetta="coherence") == ""
    assert TC.ancoraggio_target("GoodStudent", "False", TC._norm(Q_COH02),
                                etichetta="coherence") \
        == "il target non compare nella clausola della domanda"


# -- 4. la regola `clausole`: ferma la meta' traduzione ---------------------------

def test_coerenza_clausole_ferma_la_riga_a_meta():
    traduzione, esito = TC.valida(RIGA_META, "coherence", Q_COH01, RETE,
                                  citazione_output=False, coerenza="clausole")
    assert traduzione is None
    assert "la domanda enuncia 2 clausole" in esito["motivo"], esito["motivo"]
    assert esito["clausole_domanda"] == 2
    assert "coerenza-clausole" in esito["regole"]


def test_coerenza_clausole_non_ferma_chi_le_copre_tutte():
    traduzione, esito = TC.valida(RIGA_BUONA, "coherence", Q_COH01, RETE,
                                  citazione_output=False, coerenza="clausole")
    assert traduzione is not None, esito["motivo"]
    assert esito["clausole_domanda"] == 2


def test_coerenza_clausole_ordinata_dopo_la_cardinalita():
    """Con zero evidenze vince il controllo di cardinalita', che e' in vigore.

    Il motivo del protocollo di riferimento deve restare lo stesso a regola accesa:
    se la regola nuova parlasse per prima, il delta del replay su quelle righe
    sarebbe attribuito a chi ha cambiato il messaggio invece che a chi ha cambiato il
    giudizio.
    """
    zero = ('{"input": {}, "output": {"MedCost": "Thousand"}, '
            '"citazioni": {"MedCost": "the medical cost is one thousand dollars"}}')
    for kw in ({}, {"coerenza": "clausole"}):
        traduzione, esito = TC.valida(zero, "coherence", Q_COH01, RETE,
                                      citazione_output=False, **kw)
        assert traduzione is None
        assert "servono almeno 1 evidenza" in esito["motivo"], (kw, esito["motivo"])


# -- 5. il default: non muove una riga --------------------------------------------

@pytest.mark.parametrize("riga", [RIGA_SCAMBIO, RIGA_META])
def test_default_spento_lascia_passare_quello_che_passava(riga):
    """`coerenza=""` e' il protocollo dei joule del 02-11, non una quinta regola.

    Le due righe sopra sono i due fori che le regole chiudono: con il default devono
    entrambe arrivare al tool, perche' e' cosi' che 27 righe su 42 hanno prodotto un
    numero non dell'oracolo. Se questo test fallisse, il modulo avrebbe gia' cambiato
    metodo senza il conto del replay.
    """
    traduzione, esito = TC.valida(riga, "coherence", Q_COH01, RETE,
                                  citazione_output=False)
    assert traduzione is not None, esito["motivo"]
    assert esito["coerenza"] == []
    assert esito["regole"] == list(TC.LE_REGOLE), esito["regole"]


def test_le_due_regole_insieme_non_dichiarano_chi_non_gira():
    """`"target,clausole"` sulla riga con lo scambio: si ferma sul target.

    Fissa due cose: l'ordine di valutazione -- il target prima, perche' senza target
    non c'e' domanda da contare -- e che `esito["regole"]` elenca le regole **applicate
    fino a quel punto**, non quelle accese: una regola mai eseguita non si dichiara
    eseguita, e chi legge il JSON non deve dedurlo dallo stdout.
    """
    traduzione, esito = TC.valida(RIGA_SCAMBIO, "coherence", Q_COH01, RETE,
                                  citazione_output=False, coerenza="target,clausole")
    assert traduzione is None
    assert "il target non compare" in esito["motivo"], esito["motivo"]
    assert "coerenza-target" in esito["regole"]
    assert "coerenza-clausole" not in esito["regole"], esito["regole"]
    # le due regole accese restano pero' scritte nell'esito, separate da quelle usate
    assert esito["coerenza"] == ["target", "clausole"], esito["coerenza"]


def test_le_regole_di_coerenza_non_toccano_gli_altri_rami():
    """Una riga `backward_reasoning` con le regole accese si comporta come spente.

    Il selettore d'etichetta e' parte della regola: senza di esso `clausole`
    cercherebbe `given that` nelle domande di `cond_prob` -- che pure lo contengono,
    in un'altra posizione -- e fermerebbe righe per un conto che non le riguarda.
    """
    q = ("Given that the driving quality is normal, how likely is it that "
         "the age of the driver is senior?")
    grezzo = _diz([("DrivQuality", "Normal", "the driving quality is normal"),
                   ("Age", "Senior", "the age of the driver is senior")])
    spenta = TC.valida(grezzo, "backward_reasoning", q, RETE, citazione_output=False)
    accesa = TC.valida(grezzo, "backward_reasoning", q, RETE, citazione_output=False,
                       coerenza="target,clausole")
    assert spenta[0] == accesa[0] is not None
    assert accesa[1]["regole"] == list(TC.LE_REGOLE), accesa[1]["regole"]


# -- 6. un nome sconosciuto solleva, il maiuscolo no ------------------------------

@pytest.mark.parametrize("valore", ["sconosciuta", "target,sconosciuta", "targets"])
def test_nome_di_regola_sconosciuto_solleva(valore):
    """Nessuna degradazione al default: un regime deve dire cosa sta misurando.

    `targets` e' il refuso piu' probabile, perche' il nome esiste al singolare.
    """
    with pytest.raises(ValueError, match="regola di coerenza sconosciuta"):
        TC._regole_cerenza(valore)


def test_regole_cerenza_ammette_il_vuoto_il_true_e_il_maiuscolo():
    assert TC._regole_cerenza("") == ()
    assert TC._regole_cerenza(None) == ()
    assert TC._regole_cerenza(False) == ()
    assert TC._regole_cerenza(True) == TC.REGOLE_COERENZA
    assert TC._regole_cerenza("TARGET") == ("target",)
    assert TC._regole_cerenza(["target", " clausole "]) == ("target", "clausole")
