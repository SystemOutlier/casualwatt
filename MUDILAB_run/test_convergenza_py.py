"""Il test che misura quanto la Py empirica converge alla marginale del grafo.

Perche' esiste. La Py di `cobound` e' P(y = yval). Se viene stimata da una
tabella, la sua accuratezza e' solo quella della tabella: con sei righe la
frequenza empirica puo' assumere solo i valori k/6, quindi una marginale come
0,1852 o 0,1134 non e' rappresentabile e l'errore minimo possibile e' il
sesto piu' vicino (fino a 1/12). Con un campione grande l'errore scende come
1/sqrt(n): e' la ragione per cui una tabella di prova non e' una fonte di
probabilita', e per cui la Py del controfattuale va presa dal grafo (FIX 11)
invece che da DATI.csv.

Tre cose si verificano qui:

1. la tabella sintetica (`genera_dati_sintetici.py`) e' completa e valida, e
   lo stesso seme produce la stessa tabella;
2. l'errore della frequenza empirica contro la marginale del grafo scende al
   crescere di N, e a N = 6 e' quantizzato in sesti;
3. gli stati che DATI.csv usa e che il grafo non ammette producono Py = 0, e
   con Py = 0 gli estremi di `cobound` collassano su un punto: e' l'artefatto
   che produceva il "[0.126, 0.126] convergente" sulle sei righe.

Non e' un test di validita' dei numeri: il campione viene dallo stesso grafo
da cui si legge la marginale, quindi l'accordo e' per costruzione. Il test
misura l'errore di campionamento, non la correttezza del modello.

Uso:
    pytest MUDILAB_run/test_convergenza_py.py
"""

import importlib.util
import sys
from pathlib import Path

import pandas as pd
import pyagrum as gum
import pytest

HERE = Path(__file__).resolve().parent
CONSEGNA = HERE / "consegna"

# (variabile, stato) su cui si misura la convergenza: la prima con marginale
# 0,1852 (stato raro ma non rarissimo), la seconda con 0,1134 e uno stato che
# DATI.csv scrive con un'etichetta che il grafo non ammette
CASI = (("DrivQuality", "Excellent"), ("DrivingSkill", "Expert"))

# bande di accuratezza: con N righe l'errore tipico della frequenza e' circa
# sqrt(p(1-p)/N), cioe' 0,0124 a N = 1000 e 0,0012 a N = 100000 per p = 0,185.
# Le bande qui sotto sono larghe rispetto a quella scala perche' fissano un
# ordine di grandezza e non il valore di un singolo campione; la relazione
# err(100000) < err(1000) e' invece verificata in modo stretto, sullo stesso seme.
BANDA_1000 = 0.05
BANDA_100000 = 0.01


def _carica(nome, percorso):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


gen = _carica("genera_dati_sintetici", HERE / "genera_dati_sintetici.py")
# funtions_corretto legge DATI.csv accanto a se': e' in consegna, non qui
fu = _carica("funtions_corretto", CONSEGNA / "funtions_corretto.py")

GRAFO = gen.carica_grafo()


def _marginale(grafo, variabile, stato):
    ie = gum.LazyPropagation(grafo)
    ie.makeInference()
    return float(ie.posterior(variabile)[{variabile: stato}])


def _empirica(frame, variabile, stato):
    return float((frame[variabile] == stato).mean())


def _estremi(risposta):
    """I due numeri di "The answer is between low and upper"."""
    parti = risposta.split()
    return float(parti[4]), float(parti[6])


# ---------------------------------------------------------------------------
# 1. la tabella sintetica
# ---------------------------------------------------------------------------
def test_tabella_sintetica_completa_e_valida():
    """2000 righe, una colonna per ogni variabile del grafo, nessuna cella fuori vocabolario.

    E' la proprieta' che DATI.csv non ha: 10 colonne del grafo mancano e otto
    celle stanno fuori vocabolario. Se il campione contenesse una cella non
    ammessa, il campionamento o la tabella sarebbero sbagliati e ogni test
    successivo misurerebbe un'altra cosa.
    """
    frame = gen.campiona(GRAFO, 2000, seed=7)
    assert len(frame) == 2000
    assert len(frame.columns) == len(GRAFO.nodes()) + 1  # + la colonna id
    assert frame["id"].tolist() == list(range(2000))
    assert gen.valida_celle(frame, GRAFO) == []


def test_stesso_seme_stessa_tabella():
    """Due campioni con lo stesso seme sono identici, anche nell'ordine delle colonne.

    `grafo.names()` restituisce un set: senza `nomi_ordinati` l'ordine delle
    colonne cambia fra processi e la stessa tabella avrebbe due impronte
    diverse, quindi il test sarebbe irriproducibile.
    """
    a = gen.campiona(GRAFO, 200, seed=7)
    b = gen.campiona(GRAFO, 200, seed=7)
    assert a.equals(b)


# ---------------------------------------------------------------------------
# 2. convergenza della frequenza empirica
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("variabile,stato", CASI)
def test_sei_righe_quantizzano_la_py_in_sesti(variabile, stato):
    """Con sei righe la frequenza e' k/6 e non puo' valere la marginale del grafo.

    E' il difetto di fondo di una Py presa da DATI.csv: il denominatore e' sei,
    quindi l'errore minimo raggiungibile e' il sesto piu' vicino, fino a 1/12
    (0,0833). Qui si verifica che la frequenza stia esattamente su un sesto e
    che disti dalla marginale almeno quello che la quantizzazione impone.
    """
    frame = gen.campiona(GRAFO, 6, seed=7)
    emp = _empirica(frame, variabile, stato)
    marginale = _marginale(GRAFO, variabile, stato)
    # la frequenza sta sul reticolo dei sesti: k/6
    assert abs(emp * 6 - round(emp * 6)) < 1e-12
    # quindi lo scarto dalla marginale non scende sotto la distanza dal sesto
    # piu' vicino: non e' rumore, e' il passo del reticolo
    sesto = round(marginale * 6) / 6
    assert abs(emp - marginale) >= abs(sesto - marginale) - 1e-12


@pytest.mark.parametrize("variabile,stato", CASI)
def test_la_frequenza_converge_alla_marginale(variabile, stato):
    """L'errore su N = 100000 sta sotto il 1%, e sotto quello su N = 1000.

    Con sei righe due stati su tre possono valere zero, quindi la Py puo'
    differire dalla marginale di 0,1-0,2: e' il caso di DATI.csv, dove
    DrivingSkill = "Expert" vale 0 mentre nel grafo vale 0,1134. Se l'errore
    non scendesse con N, la tabella non sarebbe un campione del grafo.
    """
    marginale = _marginale(GRAFO, variabile, stato)
    errori = {}
    for n in (6, 1000, 100000):
        frame = gen.campiona(GRAFO, n, seed=7)
        errori[n] = abs(_empirica(frame, variabile, stato) - marginale)

    assert errori[1000] < BANDA_1000, errori
    assert errori[100000] < BANDA_100000, errori
    assert errori[100000] < errori[1000] < errori[6], errori


# ---------------------------------------------------------------------------
# 3. perche' DATI.csv produce una Py degenere
# ---------------------------------------------------------------------------
def test_dati_csv_usa_uno_stato_che_il_grafo_non_ammette():
    """La colonna DrivingSkill di DATI.csv vale "Excellent", che non e' uno stato del grafo.

    Gli stati del grafo sono SubStandard, Normal, Expert. Con "Excellent" nella
    colonna, P(DrivingSkill = Expert) sulla tabella vale 0 per costruzione: non
    e' un campione con una frequenza bassa, e' una cella fuori vocabolario. Lo
    stesso vale per DrivQuality, che nella tabella non c'e' affatto.
    """
    dati = pd.read_csv(CONSEGNA / "DATI.csv")
    ammessi = set(GRAFO.variable("DrivingSkill").labels())
    assert ammessi == {"SubStandard", "Normal", "Expert"}
    assert set(dati["DrivingSkill"]) - ammessi == {"Excellent"}
    assert _empirica(dati, "DrivingSkill", "Expert") == 0.0
    assert "DrivQuality" not in dati.columns


def test_py_zero_collassa_gli_estremi_in_un_punto():
    """Con Py = 0 il limite inferiore diventa PYx e coincide con il superiore.

    `low_B = max(0, PYx - PYnox, Py - PYnox, PYx - Py)` con Py = 0: i termini
    con Py sono negativi o nulli, resta `max(0, PYx - PYnox, PYx) = PYx` perche'
    PYnox >= 0. Se anche il superiore e' PYx, la risposta e' un punto
    "[x, x]" e sembra un'identificazione puntuale: e' l'artefatto dei sei
    controfattuali di DATI.csv. Con Py = marginale del grafo gli estremi si
    separano di nuovo.
    """
    y, yval, x, xval = "DrivQuality", "Excellent", "RiskAversion", "Cautious"
    marginale = _marginale(GRAFO, y, yval)

    basso_con_zero, alto_con_zero = _estremi(fu.cobound(y, yval, x, xval, None, GRAFO, py=0.0))
    basso, alto = _estremi(fu.cobound(y, yval, x, xval, None, GRAFO, py=marginale))

    assert basso_con_zero == alto_con_zero
    assert basso < alto
    assert basso < basso_con_zero <= alto
    # il punto su cui collassa e' il limite superiore di Tian-Pearl: PYx
    assert basso_con_zero == alto
