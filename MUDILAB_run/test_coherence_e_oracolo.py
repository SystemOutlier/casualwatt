"""Test del contratto `coherence` e delle condizioni del giunto ricostruito.

Perche' esistono. Due difetti della consegna sono stati corretti il 01-11 senza
un run sul modello, e senza test sarebbero claim come gli altri:

1. il ramo `coherence` catturava `gum.InvalidEvidence`, classe che in pyAgrum 3.2.1
   non esiste. Come era quel codice e' letto dallo zip del 31-10 e non ricostruito
   (`verifica_fix_coherence.py`, braccio C): `addEvidence` stava fuori dal `try`,
   quindi lo stato sbagliato usciva come `OutOfBounds` nudo e la clausola non veniva
   mai invocata. Restava una clausola che non puo' funzionare -- se il corpo avesse
   sollevato, l'`except` stesso darebbe `AttributeError` e il messaggio di pyAgrum
   si perderebbe. I tipi veri, misurati con `diagnostica_coherence.py`, sono
   `NotFound`, `OutOfBounds`, `InvalidArgument`.
2. con il target anche fra le evidenze (COH09: `input={ThisCarCost: HundredThou}`,
   `output={ThisCarCost: Million}`) pyAgrum non si lamenta: P(False|True)=0 e' una
   condizionale legittima e il ramo stampava "probability of 0.0". Un numero
   apparentemente valido uscia da una domanda contraddittoria.

La terza cosa che questi test fissano e' la ricostruzione `P(x,y) = P(y|x)P(x)` di
`benchmark/genera.py:306` (`Oracolo.congiunto`), che l'oracolo usa perche'
`jointPosterior` di LazyPropagation non e' indirizzabile su una coppia qualunque.
Il prodotto e' un'identita', quindi non va verificata la formula: vanno verificate
le condizioni sotto cui i fattori sono la distribuzione vera -- prior senza
evidenza, condizionamento e non intervento, identita' di marginalizzazione, e il
confronto con `VariableElimination`, motore esatto indipendente. L'ultima e' la
che regge davvero: la rete NON e' una polytree (27 nodi, 52 archi, misurato),
quindi l'esattezza non si puo' dedurre dalla forma del grafo e va confrontata.

Non chiamano il modello e non toccano i sorgenti della relatrice: girano sul layer
deterministico, con le copie in `consegna/`.

Uso:  MUDILAB_COPIE=1 python -m pytest MUDILAB_run/test_coherence_e_oracolo.py -v

`python` qui e' l'interprete del venv di produzione
(`MUDILabV/mudilab_env/Scripts/python.exe`), quello con pyAgrum 3.2.1: i test
affermano comportamenti di quella versione, non di un'altra. Il venv non ha
pytest e non va installato li' -- si eseguirebbe la misura dell'energia con un
ambiente diverso da quello dichiarato. pytest gira da una directory a parte
fuori dal repo, raggiunta con PYTHONPATH (verificato il 01-11: con quel
PYTHONPATH `pyagrum.__version__` resta 3.2.1).
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
import pyagrum as gum                     # noqa: E402
import tools                              # noqa: E402
from benchmark.genera import Oracolo      # noqa: E402


def cau(etichetta, traduzione):
    return tools.cau_inference.func(etichetta, json.dumps(traduzione), RETE)


# -- 1. la superficie di eccezione che il fix assume, misurata non dedotta --------

def test_invalid_evidence_non_esiste_in_pyagrum():
    """La premessa del fix: la classe catturata prima non esiste in 3.2.1."""
    assert not hasattr(gum, "InvalidEvidence")


def test_le_classi_realmente_sollevate_esistono():
    for nome in ("NotFound", "OutOfBounds", "InvalidArgument"):
        assert hasattr(gum, nome), nome


@pytest.mark.parametrize("var,stato,classe", [
    ("NonCes variable", "True", gum.NotFound),
    ("Antilock", "Falso", gum.OutOfBounds),
])
def test_add_evidence_solleva_il_tipo_nominato(var, stato, classe):
    """Lo stesso percorso del ramo: `addEvidence` alza il tipo, non un altro."""
    ie = gum.LazyPropagation(gum.loadBN(RETE))
    with pytest.raises(classe):
        ie.addEvidence(var, stato)


def test_evidenze_in_conflitto_sulla_stessa_variabile_sollevano_invalid_argument():
    ie = gum.LazyPropagation(gum.loadBN(RETE))
    ie.addEvidence("Antilock", "True")
    with pytest.raises(gum.InvalidArgument):
        ie.addEvidence("Antilock", "False")


def test_la_forma_vecchia_lasciava_uscire_l_errore_nudo():
    """La forma pre-fix, copiata dallo zip del 31-10: `addEvidence` era fuori.

    Misurato in `verifica_fix_coherence.py` (braccio C): su uno stato inesistente
    il codice vecchio sollevava `OutOfBounds` e basta, perche' l'unica riga che
    poteva fallire non era coperta dal `try`. Il fix la mette dentro, e la riga
    esce come `RuntimeError` che nomina il tipo e conserva il messaggio.
    """
    def vecchia_forma():
        ie = gum.LazyPropagation(gum.loadBN(RETE))
        for chiave, valore in {"Antilock": "Falso"}.items():
            ie.addEvidence(chiave, valore)          # fuori dal try, come nello zip
        try:
            ie.makeInference()
        except gum.InvalidEvidence as e:             # classe inesistente
            return f"Evidences invalid: {e}"

    with pytest.raises(gum.OutOfBounds):
        vecchia_forma()


def test_quel_catch_non_poteva_funzionare_in_nessun_caso():
    """La clausola `except gum.InvalidEvidence` e' inservibile, non solo lontana.

    Se il corpo solleva qualcosa, l'espressione stessa dell'`except` valuta un
    attributo che non esiste e dà `AttributeError`: il messaggio originale di
    pyAgrum si perde. E' il motivo per cui il catch adesso nomina le tre classi
    misurate, e non un nome inventato.
    """
    ie = gum.LazyPropagation(gum.loadBN(RETE))

    def corpo_che_solleva():
        try:
            ie.addEvidence("Antilock", "Falso")   # OutOfBounds
            ie.makeInference()
        except gum.InvalidEvidence:               # classe inesistente
            return "Evidences invalid"

    with pytest.raises(AttributeError):
        corpo_che_solleva()


def test_il_braccio_nuovo_avvolge_e_conserva_il_messaggio(monkeypatch):
    """Il contratto del ramo dopo il FIX 19, provato sul percorso reale del tool.

    Da fuori, con la pipeline primaria, questo ramo non lo si vede mai fallire:
    `_valida_stati` ferma lo stato inesistente prima di pyAgrum (misurato: tutti e
    tre i bracci danno `ValueError` del validatore). La guardia si disattiva solo
    dentro questo test, per arrivare alla riga che il fix ha cambiato; il resto
    della pipeline non e' toccato, e `monkeypatch` la rimette com'era.
    """
    monkeypatch.setattr(tools, "_valida_stati", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="OutOfBounds") as info:
        cau("coherence", {"input": {"Antilock": "Falso"},
                           "output": {"ThisCarCost": "Thousand"}})
    assert "label 'Falso'" in str(info.value), (
        "il messaggio originale di pyAgrum deve restare leggibile dentro la falla")


# -- 2. nessun numero da un'inferenza che non aveva una domanda sensata ----------

@pytest.mark.parametrize("traduzione", [
    {"input": {"Antilock": "True"}, "output": {"Antilock": "False"}},
    {"input": {"Antilock": "True"}, "output": {"Antilock": "True"}},
    {"input": {"ThisCarCost": "HundredThou"}, "output": {"ThisCarCost": "Million"}},
])
def test_il_target_non_puo_essere_anche_evidenza(traduzione):
    """Prima rispondeva "probability of 0.0"; ora la riga e' dichiarata."""
    with pytest.raises(ValueError, match="contraddittoria"):
        cau("coherence", traduzione)


def test_il_percorso_che_pranda_in_evidences_invalid_non_e_piu_numerico():
    """Nessuna stringa di risposta per le righe contraddittorie, nemmeno 'invalid'."""
    for t in ({"input": {"Antilock": "True"}, "output": {"Antilock": "False"}}):
        with pytest.raises(Exception) as info:  # noqa: BLE001
            cau("coherence", t)
        assert "probability" not in str(info.value).lower()


def test_riga_ben_formata_gira_com_prima():
    """Non regressione: il fix non tocca le righe sane, e il numero e' esatto.

    Il valore lo prende dall'oracolo dello stesso motore, non da un numero
    copiato: se la rete o la catena cambiano, questo test si muove con loro.
    """
    traduzione = {"input": {"Age": "Senior", "GoodStudent": "False"},
                  "output": {"Antilock": "True"}}
    risposta = str(cau("coherence", traduzione))
    ie = gum.LazyPropagation(gum.loadBN(RETE))
    ie.setEvidence({"Age": "Senior", "GoodStudent": "False"})
    ie.makeInference()
    atteso = round(float(ie.posterior("Antilock")[{"Antilock": "True"}]), 4)
    assert f"probability of {atteso}" in risposta


# -- 3. condizioni della ricostruzione del giunto --------------------------------

oracolo = Oracolo(Path(RETE))


def test_la_rete_non_e_una_polytree_e_l_esattezza_vene_da_altro():
    """Il fatto strutturale, misurato: `insurance_grafo.bif` NON e' una polytree.

    Il test era nato per asserire l'opposto, col criterio del grafo non diretto:
    una componente connessa e' un albero se e solo se ha tanti archi quanti i
    nodi meno uno. Misurato il 01-11 su questa rete: 27 nodi, 52 archi,
    un'unica componente -- 26 archi piu' di un albero, quindi il grafo sottostante
    ha cicli. E' la forma classica della Insurance di bnlearn, non un difetto
    della copia.

    Questo conta perche' toglie di mezzo un'inferenza: l'esattezza dei numeri
    dell'oracolo non viene dal fatto che la rete sia un albero (non lo e'), e
    viene nemmeno dalla fiducia nel motore. Viene dal confronto fra due motori
    esatti indipendenti, che e' il test successivo. Se un giorno la rete venisse
    sostituita, questa asserzione si muove e obbliga a riaprire la domanda.
    """
    bn = oracolo.bn
    nodi = list(bn.nodes())
    archi = list(bn.arcs())
    adiacenza = {nodo: set() for nodo in nodi}
    for padre, figlio in archi:
        adiacenza[padre].add(figlio)
        adiacenza[figlio].add(padre)

    componenti, viste = 0, set()
    for seme in nodi:
        if seme in viste:
            continue
        componenti += 1
        pila, ora = [seme], set()
        while pila:
            n = pila.pop()
            if n in ora:
                continue
            ora.add(n)
            pila.extend(adiacenza[n] - ora)
        viste |= ora

    assert len(nodi) == 27 and len(archi) == 52 and componenti == 1
    assert len(archi) > len(nodi) - componenti, (
        "il grafo non diretto e' diventato un albero: la premessa di esattezza "
        "del ground truth va riletta, non data per scontata")


def test_marginale_del_oracolo_e_senza_evidenza():
    """P(x) deve essere il prior: una sola evidenza falsa la sposterebbe."""
    bn = gum.loadBN(RETE)
    ie = gum.LazyPropagation(bn)
    ie.makeInference()
    for xv in bn.variable("Antilock").labels():
        assert oracolo.marginale("Antilock", xv) == pytest.approx(
            float(ie.posterior("Antilock")[{"Antilock": xv}]), abs=1e-12)


def test_prodotto_uguale_al_giunto_del_motore_esatto_indipendente():
    """`congiunto` contro VariableElimination, motore esatto non-Lazy.

    La condizione verificata e' che i due fattori vengano dalla stessa
    distribuzione vera: P_ve(y=yv|x=s)*P_ve(x=s) deve coincidere con il prodotto
    del ramo. Una discrepanza direbbe che `posterior` sta facendo un intervento
    al posto di un condizionamento, o che l'evidenza non e' dura.

    La tolleranza non e' scelta a caso: le CPT di `insurance_grafo.bif` sono
    lette in float32 (`bn.cpt("Antilock").as_nparray()` rende 0.8999999761581421,
    non 0.9), quindi i due motori esatti divergono di ~4e-9 per arrotondamento.
    Misurato il 01-11 su questa rete. Un 1e-6 che qui sembra lasco e' il doppio
    del fondo numerico; un 1e-9 farebbe fallire il test perche' la rete e'
    salvata in single, non per un motivo semantico.
    """
    x, y, yv = "Antilock", "ThisCarCost", "Thousand"
    bn = gum.loadBN(RETE)
    ve = gum.VariableElimination(bn)
    ve.makeInference()
    p_x = {s: float(ve.posterior(x)[{x: s}]) for s in bn.variable(x).labels()}
    congiunto = oracolo.congiunto(x, y, yv)
    for s in bn.variable(x).labels():
        ve2 = gum.VariableElimination(gum.loadBN(RETE))
        ve2.setEvidence({x: s})
        ve2.makeInference()
        p_y_dato_x = float(ve2.posterior(y)[{y: yv}])
        assert congiunto[(s, True)] == pytest.approx(p_y_dato_x * p_x[s], abs=1e-6)
        assert congiunto[(s, False)] == pytest.approx((1.0 - p_y_dato_x) * p_x[s], abs=1e-6)


def test_identita_di_marginalizzazione():
    """Somma sul giunto ricostruito: deve ridare P(y=yv) e totale 1.

    E' la condizione minima di sanita': se il prodotto fosse un intervento, la
    somma marginale su x non ridarebbe il posterior di y.
    """
    x, y, yv = "Antilock", "ThisCarCost", "Thousand"
    bn = gum.loadBN(RETE)
    congiunto = oracolo.congiunto(x, y, yv)
    totale = sum(congiunto.values())
    assert totale == pytest.approx(1.0, abs=1e-9)
    margine_y = sum(v for (s, ok), v in congiunto.items() if ok)
    ie = gum.LazyPropagation(bn)
    ie.makeInference()
    assert margine_y == pytest.approx(float(ie.posterior(y)[{y: yv}]), abs=1e-9)


def test_posterior_e_condizionamento_non_intervento():
    """Distingua le due funzioni: `posterior` condiziona, `do` interviene.

    Se `congiunto` chiamasse `do` al posto di `posterior` il prodotto non sarebbe
    un giunto. Il discriminante giusto non e' una coppia qualunque: per una
    variabile senza padri i due operatori coincidono per definizione (tagliare
    gli archi entranti su una radice non taglia niente), quindi la stessa
    asserzione va fatta in entrambe le direzioni -- identica su una radice,
    diversa su una variabile con padri.

    Numeri misurati il 01-11 su questa rete, prima etichetta per parte:
    `Age` (0 padri) -> ThisCarCost delta 0,000e+00;
    `VehicleYear` (2 padri) -> ThisCarCost delta +1,459e-02;
    `GoodStudent` (2 padri) -> ThisCarCost delta -7,065e-02.
    Il test precedente usava `Age` e asseriva una differenza: poteva solo
    fallire, perche' la differenza su una radice non c'e' e non ci sara'.
    """
    y, yv = "ThisCarCost", "Thousand"
    bn = gum.loadBN(RETE)

    radice = "Age"
    assert len(bn.parents(bn.idFromName(radice))) == 0
    lab = bn.variable(radice).labels()[0]
    cond = oracolo.posterior(y, yv, {radice: lab})
    intervent = oracolo.do(y, yv, radice, lab)
    assert cond == pytest.approx(intervent, abs=1e-9)

    con_padri = "VehicleYear"
    assert len(bn.parents(bn.idFromName(con_padri))) > 0
    lab = bn.variable(con_padri).labels()[0]
    cond = oracolo.posterior(y, yv, {con_padri: lab})
    intervent = oracolo.do(y, yv, con_padri, lab)
    assert abs(cond - intervent) > 1e-3, (
        f"condizionamento e intervento coincidono ({cond} vs {intervent}): "
        f"uno dei due percorsi non sta facendo la sua definizione")


def test_do_non_muta_la_rete_dell_oracolo():
    """`do` copia il grafo: se la copia fosse superficiale inquinerebbe tutto.

    Le righe successive del ground truth leggerebbero una rete con gli archi
    cancellati e i CPT a massa puntuale. Il numero di archi e una CPT di
    controllo si confrontano prima e dopo.
    """
    def firma():
        return (len(list(oracolo.bn.arcs())),
                oracolo.bn.cpt("Antilock").as_nparray().tolist())

    prima = firma()
    oracolo.do("ThisCarCost", "Thousand", "Antilock", "True")
    assert firma() == prima
