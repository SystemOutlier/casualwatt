# -*- coding: utf-8 -*-
"""Guardia sulla geometria di copertura di F.13, promossa in `geometry.py`.

La geometria decide due colonne obbligatorie della riga (`coverage_tier` e
`hull_margin_tok`) e un flag (`thin_support`) che non e' un aggettivo nel testo:
se la metrica o l'inviluppo cambiano, il punto operativo `(12,32)` passa da
"fascia A con supporto sottile" a "fascia A con supporto pieno" e il documento
dichiara un'interpolazione che non ha. Questi test fissano la metrica
**perpendicolare** di P4.7:1941-1945 e la regola a due lati di F.13, e
riproducono i quattro margini pre-registrati `1,33 / 64,0 / 21,24 / 107,7`.

La guardia storica `tests/test_protocollo_p4_geometry.py` resta in piedi con la
sua reimplementazione indipendente: e' il controllo incrociato di questo modulo,
non una copia da tenere allineata a mano.
"""

from __future__ import annotations

import math

import pytest

import geometry as g

# --- famiglia 1: il lato di progetto ----------------------------------------

def test_vertice_dichiarati_e_box_derivati():
    """`HULL_DESIGN` rigenera i quattro vertici e il box di P4.7:1827,1837.

    I vertici non si elencano: escono dalla catena monotona sui 10 punti di
    P3.5, e devono coincidere con quelli dichiarati. Il box e' dichiarato a
    parte dal protocollo ed e' lo stesso che gli estremi dei punti darebbero --
    due strade per lo stesso numero, ed entrambe devono portare li'.
    """
    assert set(g.HULL_DESIGN.vertici) == set(g.VERTICI_DICHIARATI)
    assert len(g.HULL_DESIGN.vertici) == 4
    assert g.HULL_DESIGN.n_in == g.BOX_DESIGN_N_IN
    assert g.HULL_DESIGN.n_out == g.BOX_DESIGN_N_OUT
    estremi = g.Hull.da_punti(g.punti_di_disegno())
    assert (estremi.n_in, estremi.n_out) == (g.BOX_DESIGN_N_IN, g.BOX_DESIGN_N_OUT)


def test_margini_pubblicati_rigenerati():
    """I quattro margini di P4.7:1916 e P4.14:2226 tornano a 0,01 token.

    Sono numeri pre-registrati: si confrontano con la campagna dopo, quindi se
    la metrica cambia devono cambiare anche loro, non il contrario.
    """
    for punto, pubblicato in g.MARGINI_PUBBLICATI.items():
        assert g.hull_margin_tok(punto, g.HULL_DESIGN.vertici) == pytest.approx(
            pubblicato, abs=0.01), punto


def test_metrica_perpendicolare_non_vertice():
    """Su `(12,32)` perpendicolare e distanza dal vertice danno 1,33 e 28,28.

    Fattore 21,3 fra due metriche sullo stesso punto e sullo stesso inviluppo,
    con esiti opposti sul flag: e' la ragione della quinta emenda di P4.7
    (righe 1883-1888). La distanza dal vertice resta nel modulo solo per
    documentare il confronto, mai per classificare.
    """
    punto = (12.0, 32.0)
    perpendicolare = g.hull_margin_tok(punto, g.HULL_DESIGN.vertici)
    dal_vertice = g.distanza_dal_vertice(punto, g.HULL_DESIGN.vertici)
    assert perpendicolare == pytest.approx(1.327, abs=0.01)
    assert dal_vertice == pytest.approx(28.284, abs=0.01)
    assert dal_vertice / perpendicolare == pytest.approx(21.3, abs=0.1)


def test_fuori_inviluppo_margine_negativo():
    """`(256,8)` e' sotto lo spigolo inferiore di 9,76 token: margine negativo.

    E' la convenzione di segno di F.13:1943, e non e' decorativa -- e' il
    numero che distingue la fascia B dalla A quando il punto resta nel box.
    """
    margine = g.hull_margin_tok((256.0, 8.0), g.HULL_DESIGN.vertici)
    assert margine == pytest.approx(-9.7629, abs=0.01)
    assert g.dentro_box((256.0, 8.0))


def test_ordine_dei_vertici_non_cambia_il_margine():
    """Il margine non dipende dall'ordine con cui arrivano i vertici.

    Il verso si fissa sul baricentro, che per un poligono convesso sta dentro:
    senza quella normalizzazione un inviluppo prodotto in senso orario
    cambierebbe il segno di tutti i margini e classificherebbe l'interno come
    esterno.
    """
    vertici = g.HULL_DESIGN.vertici
    for punto in ((12.0, 32.0), (256.0, 8.0), (400.0, 40.0)):
        assert g.hull_margin_tok(punto, tuple(reversed(vertici))) == pytest.approx(
            g.hull_margin_tok(punto, vertici), abs=1e-12)


# --- famiglia 2: fascia e flag sul lato di progetto -------------------------

def test_punto_operativo_fascia_a_supporto_sottile():
    """`(12,32)` e `(12,31,8)` sono A con `thin_support`, prima della campagna.

    Margine 1,33 token contro una soglia di 2: il flag e' obbligatorio
    (P4.7:1851-1855) e non e' attenuato dalla fascia. Senza inviluppo di fit i
    campi di quel lato restano `None`, cioe' "non ancora calcolabile", non zero.
    """
    for punto in ((12.0, 32.0), (12.0, 31.8)):
        copertura = g.valuta_copertura(*punto)
        assert copertura.coverage_tier_design == "A"
        assert copertura.coverage_tier == "A"
        assert copertura.thin_support
        assert copertura.coverage_tier_fit is None
        assert copertura.hull_margin_tok is None
        assert not copertura.sparse_support
        assert not copertura.out_of_coverage


def test_conferma_alta_supporto_pieno():
    """`(256,192)` ha margine 64 token: fascia A senza `thin_support`.

    E' il caso di controllo del flag: se scattasse anche qui la soglia sarebbe
    inutile, e se non scattasse su `(12,32)` sarebbe disattivata.
    """
    copertura = g.valuta_copertura(256.0, 192.0)
    assert copertura.coverage_tier_design == "A"
    assert copertura.hull_margin_design_tok == pytest.approx(64.0, abs=0.01)
    assert not copertura.thin_support


def test_fascia_b_dentro_box_fuori_inviluppo():
    """`(256,8)`: dentro il box, fuori dall'inviluppo, quindi fascia B.

    P4.7:1894-1896: nel box la previsione si produce ma e' descrittiva,
    marcata `sparse_support`, e non entra nei claim primari.
    """
    copertura = g.valuta_copertura(256.0, 8.0)
    assert copertura.coverage_tier == "B"
    assert copertura.sparse_support
    assert not copertura.out_of_coverage


@pytest.mark.parametrize("punto", [(600.0, 32.0), (128.0, 300.0), (4.0, 32.0)])
def test_fascia_c_fuori_box(punto):
    """Fuori dal box non si pubblica nessuna stima (P4.7:1897-1898)."""
    copertura = g.valuta_copertura(*punto)
    assert copertura.coverage_tier == "C"
    assert copertura.out_of_coverage


# --- famiglia 3: il lato di fit e la regola a due lati ----------------------

def test_lato_di_fit_piu_conservativo_prevale():
    """Un punto A in progetto ma B sui reali si pubblica B.

    F.13:1962-1964. E' il caso per cui il secondo inviluppo esiste: se i token
    reali stanno sistematicamente sotto i target, un punto che in progetto e'
    comodo puo' cadere fuori dai dati su cui il modello e' stato stimato.
    """
    cloud = [(8.0, 4.0), (512.0, 140.0), (512.0, 256.0), (32.0, 256.0)]
    hull_fit = g.Hull.da_punti(cloud)
    punto = (400.0, 40.0)
    solo_progetto = g.valuta_copertura(*punto)
    assert solo_progetto.coverage_tier_design == "A"
    assert not solo_progetto.thin_support

    copertura = g.valuta_copertura(*punto, hull_fit=hull_fit)
    assert copertura.coverage_tier_design == "A"
    assert copertura.coverage_tier_fit == "B"
    assert copertura.coverage_tier == "B"
    assert copertura.sparse_support
    assert copertura.hull_margin_tok < 0.0


def test_lato_di_fit_puo_declassare_a_c():
    """Il lato di fit puo' portare fino a C un punto che in progetto era A.

    F.13:1978-1982: la fascia puo' cambiare in seguito alla misura e i claim si
    declassano; non si sposta l'inviluppo per far rientrare il punto.
    """
    cloud = [(10.0, 30.0), (14.0, 30.0), (14.0, 34.0)]
    hull_fit = g.Hull.da_punti(cloud)
    punto = (12.0, 36.0)
    assert g.valuta_copertura(*punto).coverage_tier_design == "A"
    copertura = g.valuta_copertura(*punto, hull_fit=hull_fit)
    assert copertura.coverage_tier_design == "A"
    assert copertura.coverage_tier_fit == "C"
    assert copertura.coverage_tier == "C"
    assert copertura.out_of_coverage


def test_thin_support_basta_uno_dei_due_margini():
    """`thin_support` scatta se **uno** dei due margini e' sotto 2 token.

    F.13:1964. Con il punto in progetto a 64 token e i reali che lo stringono a
    1,5, il supporto e' sottile: il margine che conta non e' quello piu' largo.
    """
    cloud = [(254.5, 190.5), (257.5, 190.5), (257.5, 193.5), (254.5, 193.5)]
    copertura = g.valuta_copertura(256.0, 192.0, hull_fit=g.Hull.da_punti(cloud))
    assert copertura.hull_margin_design_tok == pytest.approx(64.0, abs=0.01)
    assert copertura.hull_margin_tok == pytest.approx(1.5, abs=1e-9)
    assert copertura.coverage_tier == "A"
    assert copertura.thin_support


# --- famiglia 4: ingressi degeneri dichiarati -------------------------------

def test_inviluppo_degenere_e_un_errore():
    """Un inviluppo con meno di tre vertici o un punto non finito sono errori.

    Un poligono di due punti non ha area e nessuna fascia: rispondere un numero
    li' sarebbe peggio di fermarsi, perche' `coverage_tier` e' una colonna
    pubblicata.
    """
    with pytest.raises(ValueError):
        g.hull_margin_tok((1.0, 1.0), [(0.0, 0.0), (1.0, 1.0)])
    with pytest.raises(ValueError):
        g.hull_margin_tok((math.nan, 1.0), g.HULL_DESIGN.vertici)
