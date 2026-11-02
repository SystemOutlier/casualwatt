"""Test della tavola reale della relatrice e del suo adattatore.

Perche' esiste. Il 02-11-2026 la relatrice ha mandato `dataset.xls`: duemila
righe osservate, tutte e ventisette le variabili del grafo. E' il primo dato
*esterno* che entra nel laboratorio -- la tavola sintetica e' campionato dal
grafo e non puo' né validarlo né fornire una marginale indipendente, e
`consegna/DATI.csv` ha sei righe, venti colonne su ventisette e celle fuori
vocabolario. Un file che entra nel percorso di calcolo va ancorato: forma,
conformita' ai domini, e il fatto che la copia normalizzata sia la stessa
tabella e non una sua reinterpretazione.

I test sono scritti intorno ai due difetti misurati il 02-11 leggendo questo
file, perche' entrambi sono silenziosi -- non sollevano eccezione, spostano un
numero:

1. `pandas` tratta "None" come mancante. La lista NA di default contiene la
   stringa "None", e `None` e' uno stato legittimo di `ThisCarDam` e `Accident`
   (letto dal `.bif`, non assunto). Con il lettore di default spariscono 2894
   celle, cioe' 1459 righe su 2000 perdono almeno un valore.
2. `pandas` tratta "True"/"False" come booleani. Sette variabili del grafo
   hanno dominio `{True, False}`, e le chiavi booleane non matchano le etichette
   stringa lette dal `.bif`: la frequenza empirica di `Theft` usciva 0 con
   scarto 0,9988 contro il grafo, cioe' la variabile sembrava vuota quando aveva
   2000 valori su 2000. Lo stesso difetto, dentro la consegna, rendeva la `Py`
   di `cobound` uguale a zero su ogni variabile booleana letta da `DATI.csv`.

Cosa NON pretendono. L'accordo fra le marginali della tavola e quelle del grafo
non e' una validazione del grafo: non sappiamo se il grafo sia stato imparato da
queste stesse righe, e in quel caso l'accordo e' atteso per costruzione. Il test
verifica che la differenza resti alla scala dell'errore di campionamento su
duemila righe, non che il modello sia giusto.

Uso, e dove gira. Due interpreti, due risultati diversi per ragione dichiarata:

    MUDILAB_COPIE=1 <MUDILabV>/Scripts/python.exe -m pytest MUDILAB_run/test_dati_modello.py
    python -m pytest MUDILAB_run/test_dati_modello.py

Con l'interprete della consegna (python 3.12.9, pyAgrum 3.2.1) `agent_framework`
e `tavily` ci sono e i moduli `tools`/`funtions` di consegna si caricano veri:
era 18 passati il 02-11, e nella stessa esecuzione anche i ventisette test di
`test_coherence_e_oracolo.py` e `test_convergenza_py.py` (45 passati). Nota:
l'ambiente della consegna non deve contenere pytest -- `test_coherence_e_oracolo.py`
lo dichiara nel suo docstring e la regola vale anche qui; l'esecuzione di cui
sopra e' stata fatta installando pytest nel venv e disinstallandolo subito dopo
(`pip uninstall -y pytest iniconfig pluggy`), perche' era l'unico modo di provare
i moduli con pyAgrum 3.2.1. Va ripetuta con la stessa procedura, o con il
PYTHONPATH esterno gia' usato l'01-11.

Con l'interprete di sistema (python 3.14, pyAgrum 3.3.2, `agent_framework`
assente) girano gli stessi 18 test perche' le due dipendenze mancanti si
stubpano all'import, non si simulano nei risultati: era 18 passati anche li'.
I due file vecchi invece non raccolgono nemmeno -- quello di `coherence` importa
`run_query`, che vuole il modulo reale.
"""

import hashlib
import importlib.util
import os
import sys
import types
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pyagrum as gum
import pytest

HERE = Path(__file__).resolve().parent
CONSEGNA = HERE / "consegna"
BIF = CONSEGNA / "insurance_grafo.bif"
SORGENTE = HERE / "dataset.xls"
COPIA = HERE / "dataset_car_2000.csv"

# L'impronta del file della relatrice, letta da disco il 02-11-2026. E' pinata
# perche' e' l'unico ancoraggio fra i numeri del laboratorio e il file arrivato:
# se il contenuto cambia, la consegna va riarbitrata, e questo test deve
# fallire invece di adeguarsi.
SHA_SORGENTE = "7613b58d95d7c58be0e032235c42bda40256a862d071a609c1d3dda94fdb44f2"

VARIABILI_BOOLEANE = ("Airbag", "AntiTheft", "Antilock", "GoodStudent",
                      "OtherCar", "SeniorTrain", "Theft")
# Il conteggio dello stato `None`, misurato il 02-11-2026 su questa tavola.
CONTEGGI_NONE = {"ThisCarDam": 1459, "Accident": 1435}


def _carica(nome, percorso):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _stub_dipendenze_consegna():
    """Registra i due moduli che `tools_corretto.py` importa e che qui non servono.

    Perche': `agent_framework` e `tavily` stanno nell'ambiente della consegna
    (MUDILabV, python 3.12.9), non nell'interprete di sistema con cui girano
    questi test -- e l'import di `tools_corretto` si ferma li' prima di arrivare
    alla tavola. Sono due dipendenze che queste asserzioni non esercitano:
    `tool` e' un decoratore e `TavilyClient` viene costruito solo dentro il ramo
    `influence`, che nessun test di qui chiama. Si finge l'import per provare il
    lettore, non per simulare il tool di ricerca. Un fake dichiarato, non un
    ramo disattivato.

    Il fake sostituisce solo l'assenza: dove il modulo reale c'e', quello resta,
    perche' shadoware una dipendenza installata vorrebbe dire che il test nella
    consegna vera non e' mai stato eseguito.
    """
    try:
        import agent_framework._tools  # noqa: F401  -- reale, non si tocca
    except ImportError:
        modulo_agent = types.ModuleType("agent_framework")
        modulo_tools = types.ModuleType("agent_framework._tools")
        modulo_tools.tool = lambda funzione=None, **kw: (funzione if callable(funzione)
                                                         else (lambda f: f))
        modulo_agent._tools = modulo_tools
        sys.modules["agent_framework"] = modulo_agent
        sys.modules["agent_framework._tools"] = modulo_tools
    try:
        import tavily  # noqa: F401
    except ImportError:
        modulo_tavily = types.ModuleType("tavily")

        class TavilyClient:
            def __init__(self, *a, **k):
                raise AssertionError("stub: la ricerca non deve essere chiamata")

        modulo_tavily.TavilyClient = TavilyClient
        sys.modules["tavily"] = modulo_tavily


@contextmanager
def _variabile_dambiente(nome, valore):
    """Imposta `nome = valore` per il tempo di un blocco, poi lo toglie.

    Perche': `MUDILAB_DATI` si legge all'import del modulo, quindi l'unico modo
    di provarla e' importare con la variabile attiva. Il ripristino e'
    esplicito: un test che lascia l'ambiente sporco sposta il default dei test
    dopo, ed e' esattamente la classe di difetto silenzioso che questa tavola ha
    gia' mostrato due volte. Si tocca solo questa chiave, non si svuota
    l'ambiente: importare pandas a `SYSTEMROOT` assente e' un altro errore.
    """
    prima = os.environ.get(nome)
    os.environ[nome] = str(valore)
    try:
        yield
    finally:
        if prima is None:
            os.environ.pop(nome, None)
        else:
            os.environ[nome] = prima


dm = _carica("dati_modello", HERE / "dati_modello.py")


@pytest.fixture(scope="module")
def tabella():
    return dm.leggi_tabella(COPIA)


@pytest.fixture(scope="module")
def domini():
    return dm.domini_rete(BIF)


@pytest.fixture(scope="module")
def tools_consegna():
    """Carica la consegna come la caricano `verifica_copie.py` e gli harness.

    Perche' in quest'ordine: `tools_corretto.py` fa `from funtions import ...`,
    e il modulo si chiama `funtions` solo perche' qualcuno lo registra con
    quel nome -- la consegna porta `funtions_corretto.py`. Caricando `tools` per
    primo si otterrebbe un `ModuleNotFoundError` che non dice niente sul dato.
    Le due dipendenze esterne si stubpano per lo stesso motivo: stanno
    nell'ambiente della consegna, non nell'interprete con cui gira questo file,
    e nessuna asserzione di qui le chiama.
    """
    _carica("funtions", CONSEGNA / "funtions_corretto.py")
    _stub_dipendenze_consegna()
    return _carica("tools", CONSEGNA / "tools_corretto.py")


# ---------------------------------------------------------------------------
# 1. il file, prima di tutto
# ---------------------------------------------------------------------------
def test_sorgente_non_e_un_excel():
    """`dataset.xls` non e' un Excel: i suoi primi byte sono l'intestazione CSV.

    Perche': il nome mente, e un `pd.read_excel` su quel file fallisce. Se un
    domani il file diventi un vero Excel -- formato OLE `D0CF11E0` o zip `PK` --
    questo test lo vede, e la normalizzazione va rifatta invece di riusare la
    copia vecchia.
    """
    primi = SORGENTE.read_bytes()[:8]
    assert primi.startswith(b"ILiCost,"), "atteso CSV, trovato altro"
    assert not primi.startswith((b"\xd0\xcf\x11\xe0", b"PK\x03\x04")), "vero Excel"


def test_impronta_del_sorgente():
    """Il file della relatrice e' ancora byte-identico a quello del 02-11-2026.

    Perche': ogni claim sulla tavola e' ancorato a questo file. Un edit
    successivo cambierebbe i numeri senza cambiare nessun nome, e l'unica
    difesa e' l'impronta.
    """
    assert hashlib.sha256(SORGENTE.read_bytes()).hexdigest() == SHA_SORGENTE


def test_copia_ha_le_stesse_celle_del_sorgente(tabella):
    """La copia normalizzata e' la stessa tabella: stesse chiavi, stesse righe.

    Perche': `dataset_car_2000.csv` e' una riscrittura di encoding e a capo, non
    un'elaborazione. Confrontare il `DataFrame` deja' letto dai due file prova
    che la normalizzazione non ha reinterpretato niente -- che e' precisamente
    il rischio corso con lo stato `None`.
    """
    dal_sorgente = dm.leggi_tabella(SORGENTE)
    assert dal_sorgente.equals(tabella)


# ---------------------------------------------------------------------------
# 2. forma della tavola
# ---------------------------------------------------------------------------
def test_forma_della_tavola(tabella):
    """Duemila righe per ventisette colonne, nessuna cella vuota.

    Perche': la forma dichiarata e' quella che rende la tavola utilizzabile --
    `DATI.csv` ne aveva sei e con venti colonne su ventisette.
    """
    assert tabella.shape == (2000, 27)
    assert int(tabella.isna().sum().sum()) == 0
    assert not tabella.columns.duplicated().any()
    vuote = sum((tabella[c].astype(str).str.strip() == "").sum() for c in tabella.columns)
    assert vuote == 0


def test_none_resta_un_stato_e_non_diventa_nan(tabella):
    """Lo stato `None` di `ThisCarDam` e `Accident` resta scritto, non e' NaN.

    Perche': e' il difetto silenzioso numero uno. Con il lettore di default le
    due colonne perdono 1459 e 1435 valori (2894 celle complessive) e le
    frequenze si calcolano su un sottoinsieme che nessuno dichiara. Qui si
    verifica il conto, non solo l'assenza di NaN: un test che guardasse solo
    `isna()` passerebbe anche con i valori spostati.
    """
    # Il grafo va tenuto nominato: `variable()` restituisce una vista, e sulla
    # temporanea di un `loadBN` non riferito pyAgrum 3.3.2 dà access violation
    # (misurato il 02-11 su questa stessa riga, scritta come una sola espressione).
    grafo = gum.loadBN(str(BIF))
    ammessi = set(grafo.variable("Accident").labels())
    assert "None" in ammessi
    for nome, k in CONTEGGI_NONE.items():
        assert int((tabella[nome] == "None").sum()) == k, nome
    assert int(tabella.isna().sum().sum()) == 0
    del grafo


def test_true_false_restano_stringhe(tabella, domini):
    """Le sette variabili booleane hanno chiavi stringa che matchano i label del grafo.

    Perche': e' il difetto silenzioso numero due. pandas converte "True"/"False"
    in colonne booleanhe, la frequenza viene contata su chiavi `bool` e il
    dominio del `.bif` e' fatto di `str`: la `Py` di `Theft = True` risulta zero
    mentre `Theft` ha duemila valori. Qui si esige che ogni stato di ogni
    variabile booleana compaia nella tavola con la sua etichetta.
    """
    for nome in VARIABILI_BOOLEANE:
        assert set(domini[nome]) == {"True", "False"}
        assert not pd.api.types.is_bool_dtype(tabella[nome]), nome
        assert pd.api.types.is_string_dtype(tabella[nome]), nome
        presenti = set(tabella[nome])
        assert presenti == {"True", "False"}, (nome, presenti)
        assert all(isinstance(v, str) for v in presenti), nome
        # la proprieta' sostanziale: la frequenza si legge con l'etichetta che
        # viene dal .bif, non con un equivalente booleano
        assert 0 < int(tabella[nome].value_counts().get("True", 0)) < 2000, nome


# ---------------------------------------------------------------------------
# 3. conformita' col grafo
# ---------------------------------------------------------------------------
def test_tavola_conforme_ai_domini_del_grafo(tabella, domini):
    """Tutte e ventisette le variabili del grafo sono colonne con stati ammessi.

    Perche': uno stato fuori dominio non e' un dato, e' l'errore che pyAgrum
    solleva come `OutOfBounds` dentro `cau_inference`. Su `DATI.csv` e' gia'
    accaduto (`DrivingSkill = "Excellent"`); qui la tavola deve essere pulita,
    altrimenti le query generate dalle sue righe misurano il validatore.
    """
    assert set(tabella.columns) == set(domini), "colonne e nodi non sono lo stesso insieme"
    assert dm.difetti_vs_rete(tabella, domini) == []


def test_marginali_empiriche_sono_proporzioni(tabella):
    """Le marginali sommano a uno per variabile e stanno fra zero e uno.

    Perche': `value_counts` conta, non proporziona. Confondere le due cose da'
    scarti nell'ordine di 1230 contro una soglia di 0,05 -- l'errore commesso il
    02-11 su questa tavola e visibile solo confrontandola con il grafo, quindi
    va fissato qui il vincolo aritmetico.
    """
    emp = dm.marginali_empiriche(tabella)
    for nome, valori in emp.items():
        assert abs(sum(valori.values()) - 1.0) < 1e-6, nome
        assert all(0.0 <= v <= 1.0 for v in valori.values()), nome
        assert sum(tabella[nome].value_counts()) == 2000, nome


def test_p_empirica_coincide_con_la_marginale(tabella):
    """La `Py` frequentistica di `cobound` e' lo stesso numero della marginale.

    Perche': due funzioni separate sulla stessa quantita' devono dare lo stesso
    valore, o il ramo empirico e il confronto con il grafo parlano di due cose
    diverse. E' la proprieta' che rende la funzione utilizzabile come `py`
    esplicito senza cambiare la definizione di `P(y)`.
    """
    emp = dm.marginali_empiriche(tabella)
    for nome in ("Theft", "Accident", "Age"):
        for stato in emp[nome]:
            assert dm.p_empirica(tabella, nome, stato) == pytest.approx(emp[nome][stato])


def test_marginali_sotto_la_soglia_dichiarata(tabella, domini):
    """Lo scarto massimo fra tavola e grafo resta sotto 0,05 su tutte e 27.

    Perche' esiste, e cosa NON dice. Su duemila righe l'errore standard di una
    frequenza e' circa `sqrt(p(1-p)/2000)`, cioe' al massimo 0,0112 per
    `p = 0,5`; misurato il 02-11 lo scarto massimo e' 0,0190 (`Mileage`). Se un
    aggiornamento della tavola portasse una variabile fuori da quella scala, la
    coincidenza con il giunto non sarebbe piu' spiegabile dal campionamento.
    Non e' una validazione del grafo: non sappiamo se il grafo sia stato
    imparato da queste righe, e in tal caso l'accordo e' atteso per costruzione.
    """
    righe = dm.confronto(tabella, soglia=0.05, bif_path=BIF)
    assert len(righe) == 27
    assert [r["variabile"] for r in righe if r["giudizio"] == "discordante"] == []
    assert max(r["scarto_max"] for r in righe) <= 0.05


def test_stato_del_grafo_mai_osservato(tabella):
    """`OtherCarCost = Million` non compare in nessuna delle duemila righe.

    Perche': non e' un difetto della tavola, e' un vincolo d'uso registrato. Su
    quello stato la `Py` frequentistica vale zero per assenza di evidenza, e
    una query che lo chiede non ha riscontro nel dato: si vede solo qui, perche'
    il grafo gli assegna una probabilita' non nulla.
    """
    assert "Million" in set(tabella["ThisCarCost"])
    assert int((tabella["OtherCarCost"] == "Million").sum()) == 0
    assert dm.p_empirica(tabella, "OtherCarCost", "Million") == 0.0


# ---------------------------------------------------------------------------
# 4. evidenze campionate: l'uso nuovo
# ---------------------------------------------------------------------------
def test_evidenze_deterministiche_per_seme(tabella):
    """Stesso seme e stesso `n` danno le stesse righe, nell'ordine.

    Perche': le query del `coherence` e del controfattuale possono nascere da
    configurazioni osservate. Se il campione non fosse ricostruibile, una query
    non si potrebbe riprodurre dopo un riavvio, e una query non riproducibile
    non e' un caso di test.
    """
    a = dm.evidenze_da_righe(tabella, n=12, seed=7)
    b = dm.evidenze_da_righe(tabella, n=12, seed=7)
    assert a == b
    assert len({tuple(sorted(e["evidenza"].items())) for e in a}) > 1
    c = dm.evidenze_da_righe(tabella, n=12, seed=11)
    assert [e["riga"] for e in c] != [e["riga"] for e in a]


def test_evidenza_completa_e_ammissibile(tabella, domini):
    """Ogni evidenza campionate ha ventisette variabili e stati tutti nel dominio.

    Perche': l'evidenza passa a `_valida_stati`; un campione che producesse uno
    stato fuori dominio farebbe fallire la query per colpa della tavola, non del
    modello, e sarebbe un errore di misura invece che un risultato.
    """
    for e in dm.evidenze_da_righe(tabella, n=20, seed=7):
        ev = e["evidenza"]
        assert set(ev) == set(domini)
        for nome, stato in ev.items():
            assert stato in domini[nome], (e["riga"], nome, stato)


@pytest.mark.parametrize("n", [0, 2001])
def test_numero_di_evidenze_fuori_intervallo_fallisce_dichiarando(n, tabella):
    """`n` fuori da 1..2000 solleva `ValueError`, non restituisce un campione monco.

    Perche': `df.sample` con n troppo grande e' un errore opaco di pandas e con
    n = 0 e' una lista vuota che passa come "nessuna evidenza". La condizione del
    giunto va detta nel punto in cui si verifica.
    """
    with pytest.raises(ValueError):
        dm.evidenze_da_righe(tabella, n=n, seed=7)


# ---------------------------------------------------------------------------
# 5. cosa cambia dentro la consegna
# ---------------------------------------------------------------------------
def test_la_consegna_legge_la_tavola_severa(tools_consegna):
    """`_load_data` con il default da' `Py(Airbag=True) = 4/6`, non zero.

    Perche': fissa il comportamento corretto del lettore, dopo FIX 12. Con il
    lettore vecchio la colonna booleana diventava `bool` e il confronto
    `data[y] == 'True'` non matchava mai: la branca empirica restituiva 0 su
    qualunque variabile booleana. E' un secondo motivo, indipendente dalle sei
    righe, per cui FIX 11 ha portato la `Py` nel giunto -- e ora e' un test, non
    una deduzione.
    """
    to = tools_consegna
    assert to.DATA_PATH == CONSEGNA / "DATI.csv", "il default della consegna non si sposta"
    dati = to._load_data()
    assert dati.shape == (6, 20)
    assert round(float((dati["Airbag"] == "True").mean()), 4) == round(4 / 6, 4)
    assert round(float((dati["GoodStudent"] == "True").mean()), 4) == round(1 / 6, 4)


def test_dati_csv_ha_nan_che_non_e_uno_stato(tools_consegna, domini):
    """Le celle `Accident = "NaN"` di `DATI.csv` sono letterali fuori vocabolario.

    Perche': `NaN` non sta nel dominio `{None, Mild, Moderate, Severe}`. Con la
    tavola reale si vede che `None` e' lo stato maggioritario (`Accident` 1435 su
    2000, 71,75%), mentre in `DATI.csv` -- che e' un `to_csv` di pandas, perche'
    ha la colonna indice `Unnamed: 0` -- quattro righe su sei hanno `NaN` nella
    stessa colonna. L'ipotesi che quelle celle siano lo stato `None` scritto da
    un giro di pandas ha ora due evidenze; resta un'ipotesi, perche' non e'
    stata verificata su una versione precedente del file.
    """
    dati = tools_consegna._load_data()
    assert "NaN" in dati["Accident"].tolist()
    assert "NaN" not in domini["Accident"]
    assert int((dati["Accident"] == "NaN").sum()) == 4
    assert "Unnamed: 0" in dati.columns


def test_la_tavola_reale_enza_il_chiave_di_nome(tools_consegna):
    """`funtions_corretto` si importa anche su una tavola senza `Name`/`Surnames`.

    Perche': i due globali sono morti -- nel modulo non c'e' altra occorrenza
    dopo la riga che li assegna -- pero' facevano fallire l'import con `KeyError`
    su una colonna che il calcolo non usa. La tavola della relatrice ha le
    ventisette variabili del grafo e non i nomi dei clienti, quindi il vincolo
    andava condizionato e non cancellato: qui si prova che l'import gira e che
    con `DATI.csv` i nomi restano leggibili.
    """
    fu = sys.modules["funtions"]
    assert fu.DATA_PATH == CONSEGNA / "DATI.csv"
    assert fu.names == ["Lorenzo", "Carlo", "Caterina", "Davide", "Luca", "Giulia"]
    assert len(fu.surnames) == 6
    with _variabile_dambiente("MUDILAB_DATI", COPIA):
        nuovo_fu = _carica("funtions_reale", CONSEGNA / "funtions_corretto.py")
        nuovo_to = _carica("tools_reale", CONSEGNA / "tools_corretto.py")
    assert nuovo_fu.DATA_PATH == COPIA
    assert nuovo_to.DATA_PATH == COPIA, "le due letture di DATA_PATH devono coincidere"
    assert nuovo_fu.dati.shape == (2000, 27)
    assert nuovo_fu.names == [], "la tavola reale non ha nomi: il globale dev'essere vuoto, non un errore"
    assert nuovo_to._load_data().shape == (2000, 27)
    assert fu.DATA_PATH == CONSEGNA / "DATI.csv", "l'ambiente non deve restare applicato"
