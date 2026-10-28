# -*- coding: utf-8 -*-
"""Guardia sulla geometria di copertura di P4.7 e sulla scala di `budget_pred`.

Il file esiste perche' il quinto turno di revisione esterna
(`revisione tecnica di P4.docx`, 2026-10-26, valutato in
`experiment_results/revisione_esterna_20261026_quinto_turno_valutazione.md`)
propone di scrivere nel protocollo congelato una cinquina di vertici
dell'inviluppo di progetto e una formula di `budget_pred` con un termine
`u_model` adimensionale. Nessuna delle due e' applicabile: la prima viene da un
insieme di disegno che non e' quello di P3.5, la seconda corregge una formula
che nel protocollo non esiste. Una proposta respinta puo' tornare -- e' gia'
successo con la "lista a cinque vertici circolata in chat" che P4.7 corregge a
riga 1831 -- quindi qui si congela in test cio' che il protocollo dichiara, con
le righe accanto.

Le proprieta' fissate sono tre famiglie.

  1. **L'inviluppo di progetto ha quattro vertici, non cinque.** I 10 punti di
     fit di P3.5 (righe 954-963) sono la griglia `{32,128,512} x {32,128,256}`
     piu' il minimo `(8,4)`. Il loro inviluppo convesso e'
     `(8,4) (512,32) (512,256) (32,256)` (P4.7:1827, P4.14:2225). `(32,4)` non
     e' un punto di disegno e `(32,32)` sta dentro con margine 21,24.
  2. **La metrica del margine e' la perpendicolare, non la distanza dal
     vertice.** Quinta emenda di P4.7 (righe 1883-1888): su `(12,32)` le due
     metriche danno 1,33 e 28,28, fattore 21,3, e il flag `thin_support`
     (soglia 2 token) si rovescia. I quattro margini pubblicati
     `1,33 / 64,0 / 21,24 / 107,7` devono rigenerarsi.
  3. **`budget_pred_b` e' omogeneo di grado 1 in joule.** La formula congelata
     `budget_pred_b^2 = budget_fit_b^2 + u_edge,b^2 + u_bias,b^2` (P4.6:1624,
     P4.3:1392, F.11:2934) ha tre termini, tutti in joule: nessun percentile di
     residuo standardizzato vi compare. L'incertezza di modello passa dal
     bootstrap di P4.8, che costruisce `Y*_b = f(x_b;theta^) + budget_fit_b * z*_b`
     (riga 1983) e resta in joule perche' `z*_b` e' moltiplicato per un budget.

L'ultimo test documenta perche' la sostituzione proposta non va adottata: con
`u_model = 1,96 * budget_fit` il budget predittivo cresce di un fattore
`sqrt(1 + 1,96^2) = 2,2004` identico per ogni blocco a `u_edge` nullo, cioe'
senza contenuto dai dati, e con un quantile normale che P4.8 (righe 1987-1989)
esclude esplicitamente.
"""

from __future__ import annotations

import math

import pytest

# --- testo congelato, con la riga del protocollo accanto ---------------------

# P3.5, righe 954-963.
GRIGLIA_N_IN = (32.0, 128.0, 512.0)
GRIGLIA_N_OUT = (32.0, 128.0, 256.0)
PUNTO_MINIMO = (8.0, 4.0)

# P4.7, riga 1827; P4.14, righe 2224-2227.
VERTICI_DICHIARATI = ((8.0, 4.0), (512.0, 32.0), (512.0, 256.0), (32.0, 256.0))

# P4.7, riga 1837.
BOX_N_IN = (8.0, 512.0)
BOX_N_OUT = (4.0, 256.0)

# P4.7, righe 1852 e 1907.
SOGLIA_THIN_SUPPORT_TOK = 2.0

# P4.7, righe 1916 e 1945; P4.14, righe 2226-2227.
MARGINI_PUBBLICATI = {
    (12.0, 32.0): 1.33,
    (256.0, 192.0): 64.0,
    (32.0, 32.0): 21.24,
    (128.0, 128.0): 107.7,
}

# revisione tecnica di P4.docx, sez. 1.1: la cinquina proposta.
VERTICI_PROPOSTI = ((8.0, 4.0), (32.0, 4.0), (512.0, 32.0), (512.0, 256.0),
                    (8.0, 256.0))

# revisione tecnica di P4.docx, sez. 2.2 e sez. 7.
Z_0975_PROPOSTO = 1.96


def punti_di_disegno():
    """I 10 punti di fit di P3.5, costruiti dalla griglia."""
    punti = [(a, b) for a in GRIGLIA_N_IN for b in GRIGLIA_N_OUT]
    punti.append(PUNTO_MINIMO)
    return punti


def inviluppo_convesso(punti):
    """Catena monotona di Andrew, antioraria.

    Implementata qui invece che importata da `scipy.spatial`: l'inviluppo decide
    una fascia di copertura obbligatoria e un implementatore deve poterlo
    ricontrollare senza una libreria fra i piedi.
    """
    unici = sorted(set(punti))

    def semipiano(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inferiore = []
    for p in unici:
        while len(inferiore) >= 2 and semipiano(inferiore[-2], inferiore[-1], p) <= 0:
            inferiore.pop()
        inferiore.append(p)
    superiore = []
    for p in reversed(unici):
        while len(superiore) >= 2 and semipiano(superiore[-2], superiore[-1], p) <= 0:
            superiore.pop()
        superiore.append(p)
    return inferiore[:-1] + superiore[:-1]


def _spigoli(vertici):
    v = list(vertici)
    return [(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]


def distanza_perpendicolare(punto, vert_a, vert_b):
    """Distanza con segno dalla retta dello spigolo: la metrica di P4.7:1883."""
    dx, dy = vert_b[0] - vert_a[0], vert_b[1] - vert_a[1]
    return (dx * (punto[1] - vert_a[1]) - dy * (punto[0] - vert_a[0])) / math.hypot(dx, dy)


def _verso_interno(vertici):
    baricentro = (sum(v[0] for v in vertici) / len(vertici),
                  sum(v[1] for v in vertici) / len(vertici))
    interno = min(distanza_perpendicolare(baricentro, a, b) for a, b in _spigoli(vertici))
    return 1.0 if interno >= 0 else -1.0


def margine(punto, vertici):
    """Distanza perpendicolare dallo spigolo piu' vicino, negativa se fuori."""
    verso = _verso_interno(vertici)
    return min(verso * distanza_perpendicolare(punto, a, b) for a, b in _spigoli(vertici))


def distanza_dal_vertice(punto, vertici):
    """La metrica scartata dalla quinta emenda (P4.7:1887-1888)."""
    return min(math.hypot(punto[0] - v[0], punto[1] - v[1]) for v in vertici)


def dentro_box(punto):
    return (BOX_N_IN[0] <= punto[0] <= BOX_N_IN[1]
            and BOX_N_OUT[0] <= punto[1] <= BOX_N_OUT[1])


def fascia(punto, vertici):
    """A / B / C di P4.7:1835-1841."""
    if not dentro_box(punto):
        return "C"
    return "A" if margine(punto, vertici) >= 0 else "B"


def budget_pred_congelato(budget_fit, u_edge, u_bias):
    """P4.6:1624, P4.3:1392, F.11:2934. Tre termini, tutti in joule."""
    return math.sqrt(budget_fit ** 2 + u_edge ** 2 + u_bias ** 2)


def budget_pred_con_u_model(budget_fit, u_edge, z0975=Z_0975_PROPOSTO):
    """La sostituzione proposta dalla revisione: u_model = budget_fit * z_0.975*."""
    return math.sqrt(budget_fit ** 2 + (budget_fit * z0975) ** 2 + u_edge ** 2)


# --- famiglia 1: i vertici ---------------------------------------------------

def test_vertici_inviluppo_progetto():
    """L'inviluppo dei 10 punti di P3.5 e' la quaterna dichiarata da P4.7:1827.

    Non e' una verifica di stile: `coverage_tier` e `hull_margin_tok` sono campi
    obbligatori della riga CSV, e se l'inviluppo e' sbagliato un punto in fascia
    A viene pubblicato come interpolazione quando e' estrapolazione -- l'errore
    per cui P4.7 esiste (righe 1816-1819).
    """
    hull = inviluppo_convesso(punti_di_disegno())
    assert set(hull) == set(VERTICI_DICHIARATI)
    assert len(hull) == 4, "l'inviluppo di progetto ha quattro vertici, non cinque"


def test_ogni_punto_disegno_dentro():
    """Nessun punto di disegno resta fuori dal proprio inviluppo.

    E' il controllo di autoconsistenza della catena monotona: se l'algoritmo o
    l'orientazione fossero sbagliati, almeno uno dei 10 punti uscirebbe.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    for punto in punti_di_disegno():
        assert margine(punto, hull) >= -1e-9, punto


def test_punto_32_4_assente_disegno():
    """`(32,4)` non e' un punto di disegno: la correzione D1 non e' applicabile.

    D1 chiede di aggiungere `(32,4)` ai vertici sostenendo che il protocollo lo
    abbia omesso. Il punto non esiste in P3.5 (righe 954-963): la griglia parte
    da `N_in = 32` con `N_out >= 32`, e l'unico punto sotto e' il minimo `(8,4)`.
    Scrivere `(32,4)` come vertice dichiarerebbe coperta una regione che il
    disegno non misura -- esattamente l'estrapolazione mascherata da
    interpolazione che P4.7 vieta.
    """
    assert (32.0, 4.0) not in set(punti_di_disegno())
    assert (8.0, 32.0) not in set(punti_di_disegno())
    assert (8.0, 256.0) not in set(punti_di_disegno())


def test_cinquina_proposta_non_e_inviluppo():
    """La cinquina della revisione usa due vertici che non sono punti di disegno.

    `(32,4)` e `(8,256)` non appartengono all'insieme di P3.5, quindi non
    possono essere vertici dell'inviluppo di progetto. Il test fissa il fatto,
    non il giudizio: se un domani il pre-pilota di P3.15 cambiasse i punti di
    disegno, cambierebbero entrambi gli inviluppi (P4.7:1926-1928) e questo
    test andrebbe aggiornato insieme al protocollo, non prima.
    """
    disegno = set(punti_di_disegno())
    estranei = [v for v in VERTICI_PROPOSTI if v not in disegno]
    assert estranei == [(32.0, 4.0), (8.0, 256.0)]


def test_32_32_interno_non_vertice():
    """`(32,32)` sta dentro con margine 21,24, come P4.7:1830 scrive.

    La revisione sostiene che il protocollo lo dichiari vertice. Il testo dice
    il contrario: "`(32,32)` **non** e' un vertice: sta dentro l'inviluppo con un
    margine di 21,2 token".
    """
    hull = inviluppo_convesso(punti_di_disegno())
    assert (32.0, 32.0) not in hull
    assert margine((32.0, 32.0), hull) == pytest.approx(21.24, abs=0.01)


# --- famiglia 2: metrica e margini ------------------------------------------

def test_margini_pubblicati_rigenerati():
    """I quattro margini di P4.7:1916 e P4.14:2226 si rigenerano a 0,01 token.

    Sono numeri pre-registrati: servono da confronto prima dei dati, quindi se
    la metrica cambia devono cambiare anche loro, non il contrario.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    for punto, pubblicato in MARGINI_PUBBLICATI.items():
        assert margine(punto, hull) == pytest.approx(pubblicato, abs=0.01), punto


def test_metrica_perpendicolare_non_vertice():
    """Su `(12,32)` le due metriche danno 1,33 e 28,28: fattore 21,3.

    Quinta emenda di P4.7 (righe 1883-1888). Il test esiste perche' la scelta
    non e' cosmetica: con la distanza dal vertice il punto operativo supera la
    soglia di 2 token e `thin_support` resta falso, cioe' la riga dichiarerebbe
    un supporto di progetto pieno dove il protocollo dice che e' sottile.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    punto = (12.0, 32.0)
    perpendicolare = margine(punto, hull)
    dal_vertice = distanza_dal_vertice(punto, hull)
    assert perpendicolare == pytest.approx(1.327, abs=0.01)
    assert dal_vertice == pytest.approx(28.284, abs=0.01)
    assert dal_vertice / perpendicolare == pytest.approx(21.3, abs=0.1)


def test_punto_operativo_thin_support():
    """`(12,32)` e `(12,31,8)` sono in fascia A con `thin_support = true`.

    La revisione (sez. 1.2) scrive che il punto "cade pienamente all'interno del
    Livello A": l'avverbio cancella il flag obbligatorio. Il test congela la
    coppia (fascia, flag), perche' pubblicare la fascia senza il flag e' cio' che
    P4.7:1851-1855 vieta.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    for punto in ((12.0, 32.0), (12.0, 31.8)):
        assert fascia(punto, hull) == "A"
        assert margine(punto, hull) < SOGLIA_THIN_SUPPORT_TOK, punto


def test_conferma_alta_supporto_pieno():
    """`(256,192)` ha margine 64 token: fascia A senza `thin_support`.

    E' il caso di controllo del flag: se `thin_support` scattasse anche qui la
    soglia sarebbe inutile, e se non scattasse su `(12,32)` sarebbe disattivata.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    punto = (256.0, 192.0)
    assert fascia(punto, hull) == "A"
    assert margine(punto, hull) == pytest.approx(64.0, abs=0.01)
    assert margine(punto, hull) >= SOGLIA_THIN_SUPPORT_TOK


def test_fascia_b_dentro_box_fuori_inviluppo():
    """`(256,8)`: dentro il box, fuori dall'inviluppo, quindi fascia B.

    P4.7:1837-1839. La regione ad alto prefill e bassissimo decode e' coperta
    dal box e non dal disegno: la previsione e' descrittiva e marcata
    `sparse_support`, non entra nei claim primari.
    """
    hull = inviluppo_convesso(punti_di_disegno())
    punto = (256.0, 8.0)
    assert dentro_box(punto)
    assert margine(punto, hull) < 0
    assert fascia(punto, hull) == "B"


@pytest.mark.parametrize("punto", [(600.0, 32.0), (128.0, 300.0), (4.0, 32.0)])
def test_fascia_c_fuori_box(punto):
    """Fuori dal box non si pubblica nessuna stima (P4.7:1840-1841)."""
    hull = inviluppo_convesso(punti_di_disegno())
    assert not dentro_box(punto)
    assert fascia(punto, hull) == "C"


# --- famiglia 3: scala di budget_pred ---------------------------------------

def test_budget_pred_omogeneo_grado_uno():
    """`budget_pred_b` e' omogeneo di grado 1: tre termini, tutti in joule.

    Se un termine adimensionale entrasse nella quadratura, scalare gli ingressi
    di un fattore k non scalerebbe il risultato di k. Il test e' la verifica
    dimensionale che la revisione chiede, applicata alla formula che esiste
    davvero (P4.6:1624) invece che a quella che cita.
    """
    base = budget_pred_congelato(0.050, 0.002, 0.001)
    for k in (1e-3, 7.5, 1000.0):
        scalato = budget_pred_congelato(0.050 * k, 0.002 * k, 0.001 * k)
        assert scalato == pytest.approx(base * k, rel=1e-12)


def test_budget_pred_solo_fit_unchanged():
    """Con `u_edge = u_bias = 0` il budget predittivo coincide con quello di fit.

    E' la proprieta' che la sostituzione proposta rompe: aggiungendo
    `u_model = 1,96 * budget_fit` il risultato diventa `2,2004 * budget_fit`
    anche quando gli altri due termini sono nulli, cioe' il budget si allarga
    senza che sia entrato nessun dato nuovo.
    """
    for budget_fit in (1e-3, 0.05, 1.0, 100.0):
        assert budget_pred_congelato(budget_fit, 0.0, 0.0) == pytest.approx(budget_fit)


def test_bootstrap_sintetico_in_joule():
    """`Y*_b = f + budget_fit_b * z*_b` e' in joule (P4.8:1983).

    Il residuo standardizzato non entra mai da solo in una grandezza energetica:
    e' sempre moltiplicato per il budget del blocco, che porta l'unita'. E' la
    ragione per cui nel protocollo non esiste un termine `u_model` da
    riscalare -- l'incertezza di modello si propaga rifittando sui sintetici e
    prendendo i quantili di `f(x; theta*)`, non con un percentile di `z`.
    """
    f_fit, z_star = 1.250, -1.37
    for budget_fit in (0.010, 0.050, 0.200):
        y_star = f_fit + budget_fit * z_star
        assert y_star == pytest.approx(f_fit - 1.37 * budget_fit)
        # raddoppiare il budget raddoppia lo scarto, non il livello
        scarto = abs(y_star - f_fit)
        y_doppio = f_fit + (2 * budget_fit) * z_star
        assert abs(y_doppio - f_fit) == pytest.approx(2 * scarto)


def test_u_model_proposto_fattore_costante():
    """La sostituzione proposta allarga di `sqrt(1 + 1,96^2) = 2,2004`.

    Il fattore non dipende dal blocco quando `u_edge` e' nullo, perche'
    `u_model` e' proporzionale a `budget_fit`: e' una costante moltiplicativa,
    non una misura. Con `u_edge > 0` il fattore scende, quindi la sostituzione
    non e' nemmeno conservativa in modo uniforme -- allarga di piu' i blocchi
    con il bordo piccolo, che non sono i piu' incerti.
    """
    atteso = math.sqrt(1 + Z_0975_PROPOSTO ** 2)
    for budget_fit in (1e-3, 0.05, 1.0):
        rapporto = (budget_pred_con_u_model(budget_fit, 0.0)
                    / budget_pred_congelato(budget_fit, 0.0, 0.0))
        assert rapporto == pytest.approx(atteso, rel=1e-12)
    assert atteso == pytest.approx(2.2004, abs=1e-4)
    con_bordo = (budget_pred_con_u_model(0.050, 0.002)
                 / budget_pred_congelato(0.050, 0.002, 0.0))
    assert con_bordo < atteso
