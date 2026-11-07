# -*- coding: utf-8 -*-
"""P5 — geometria della copertura: `hull_margin_tok`, `coverage_tier`, i flag.

Il protocollo F.13 (`experiment_results/protocollo_v4_20261024.md:1939-1965`)
fissa la metrica e la regola con cui ogni punto pubblicato dichiara **dove**
si trova rispetto al disegno:

    d(P, inviluppo) = minimo, sulle rette degli spigoli, della distanza
                      PERPENDICOLARE euclidea di P dalla retta, in coordinate
                      grezze (token, token); negativa se P e' fuori

Non e' la distanza dal vertice piu' vicino: su `(12,32)` quella da' 28,28 invece
di 1,33, fattore 21,3, e rovescia `thin_support` (P4.7:1944-1945). La metrica
non e' cosmetica perche' `thin_support` scatta sotto i 2 token ed e' una colonna
obbligatoria della riga.

Due inviluppi, ciascuno con il punto della **stessa base** (F.13:1947-1960):

    lato di progetto  hull_design = inviluppo dei 10 punti di P3.5, coordinate
                      target; box_design = 8 <= N_in <= 512, 4 <= N_out <= 256
    lato di fit       hull_fit    = inviluppo delle coppie (x1_b, x2_b) dei
                      blocchi di fit, coordinate reali; box_fit = min/max

L'esito pubblicato (F.13:1962-1964) e' `coverage_tier` = il piu' conservativo
dei due (`A < B < C`) e `thin_support` = vero se **uno** dei due margini e' sotto
la soglia; `sparse_support` e `out_of_coverage` sono le etichette di fascia B e
C. Il lato di fit esiste solo dopo la campagna, quindi `valuta_copertura`
accetta un inviluppo di fit assente e in quel caso pubblica il solo lato di
progetto -- che e' cio' che si puo' dichiarare prima dei dati, e i quattro
margini pubblicati (1,33 / 64,0 / 21,24 / 107,7) sono esattamente di quel lato.

Limite dichiarato dal protocollo e non aggirato qui: la classificazione e' la
proiezione su `(x1_b, x2_b)` mentre il fit vive in `(x1_b, x2_b, x12_b)`, con
`x12_b` media dei prodotti e non prodotto delle medie (F.7). La fascia A e'
condizione **necessaria non sufficiente** per l'interpolazione (F.13:1986-1992).

L'inviluppo si calcola con la catena monotona di Andrew senza dipendenze: decide
una fascia obbligatoria e deve poter essere ricontrollato a mano. La sonda
`inviluppo_e_budget_pred_probe.py` e la guardia
`tests/test_protocollo_p4_geometry.py` mantengono di proposito una
reimplementazione indipendente: servono a verificare questo modulo, non a
ereditarne il codice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence

#: P3.5 (protocollo:954-963): griglia 3x3 piu' il minimo. I punti di fit.
GRIGLIA_N_IN = (32.0, 128.0, 512.0)
GRIGLIA_N_OUT = (32.0, 128.0, 256.0)
PUNTO_MINIMO = (8.0, 4.0)

#: P4.7:1827, P4.14:2225: i quattro vertici dichiarati di `hull_design`.
VERTICI_DICHIARATI = ((8.0, 4.0), (512.0, 32.0), (512.0, 256.0), (32.0, 256.0))

#: P4.7:1837: il box di progetto.
BOX_DESIGN_N_IN = (8.0, 512.0)
BOX_DESIGN_N_OUT = (4.0, 256.0)

#: P4.7:1852, :1907: sotto questa soglia il supporto e' sottile.
SOGLIA_THIN_SUPPORT_TOK = 2.0

#: P4.7:1916, P4.14:2226: i margini di progetto pre-registrati, a 0,01 token.
MARGINI_PUBBLICATI = {
    (12.0, 32.0): 1.33,
    (256.0, 192.0): 64.0,
    (32.0, 32.0): 21.24,
    (128.0, 128.0): 107.7,
}

Punto = tuple[float, float]


def punti_di_disegno() -> list[Punto]:
    """I 10 punti di fit di P3.5, costruiti dalla griglia e non elencati a mano."""
    punti = [(a, b) for a in GRIGLIA_N_IN for b in GRIGLIA_N_OUT]
    punti.append(PUNTO_MINIMO)
    return punti


def inviluppo_convesso(punti: Sequence[Punto]) -> list[Punto]:
    """Catena monotona di Andrew: inviluppo convesso 2D in senso antiorario."""
    unici = sorted(set((float(x), float(y)) for x, y in punti))
    if len(unici) < 3:
        return unici

    def semipiano(o: Punto, a: Punto, b: Punto) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    inferiore: list[Punto] = []
    for p in unici:
        while len(inferiore) >= 2 and semipiano(inferiore[-2], inferiore[-1], p) <= 0:
            inferiore.pop()
        inferiore.append(p)
    superiore: list[Punto] = []
    for p in reversed(unici):
        while len(superiore) >= 2 and semipiano(superiore[-2], superiore[-1], p) <= 0:
            superiore.pop()
        superiore.append(p)
    return inferiore[:-1] + superiore[:-1]


def spigoli(vertici: Sequence[Punto]) -> list[tuple[Punto, Punto]]:
    """Coppie consecutive di vertici, chiusa sull'ultima."""
    v = list(vertici)
    return [(v[i], v[(i + 1) % len(v)]) for i in range(len(v))]


def distanza_perpendicolare(punto: Punto, vert_a: Punto, vert_b: Punto) -> float:
    """Distanza con segno dalla retta per `vert_a`-`vert_b`, positiva a sinistra."""
    dx, dy = vert_b[0] - vert_a[0], vert_b[1] - vert_a[1]
    norma = math.hypot(dx, dy)
    if norma == 0.0:
        raise ValueError(f"spigolo degenere fra {vert_a} e {vert_b}")
    return (dx * (punto[1] - vert_a[1]) - dy * (punto[0] - vert_a[0])) / norma


def hull_margin_tok(punto: Sequence[float], vertici: Sequence[Punto]) -> float:
    """`d(P, inviluppo)` di F.13:1941-1945, negativa se `punto` e' fuori.

    Minimo delle distanze perpendicolari con segno dagli spigoli. L'orientazione
    dei vertici non conta: il verso si fissa sul baricentro, che per un poligono
    convesso sta dentro, cosi' il risultato non dipende dall'ordine in cui i
    vertici sono stati prodotti.
    """
    x, y = float(punto[0]), float(punto[1])
    if not (math.isfinite(x) and math.isfinite(y)):
        raise ValueError(f"punto non finito: {punto!r}")
    v = list(vertici)
    if len(v) < 3:
        raise ValueError(f"l'inviluppo ha {len(v)} vertici: il margine non e' definito")
    lati = spigoli(v)
    baricentro = (sum(p[0] for p in v) / len(v), sum(p[1] for p in v) / len(v))
    if min(distanza_perpendicolare(baricentro, a, b) for a, b in lati) < 0:
        verso = -1.0
    else:
        verso = 1.0
    # il verso si applica a OGNI distanza prima del minimo: applicarlo al minimo
    # gia' fatto darebbe il massimo delle distanze quando i vertici arrivano in
    # senso orario, cioe' 500 token invece di 1,33 su (12,32)
    return min(verso * distanza_perpendicolare((x, y), a, b) for a, b in lati)


def distanza_dal_vertice(punto: Sequence[float], vertici: Sequence[Punto]) -> float:
    """La metrica scartata dalla quinta emenda (P4.7:1887-1888). Solo confronto."""
    return min(math.hypot(punto[0] - v[0], punto[1] - v[1]) for v in vertici)


def dentro_box(punto: Sequence[float],
               n_in: tuple[float, float] = BOX_DESIGN_N_IN,
               n_out: tuple[float, float] = BOX_DESIGN_N_OUT) -> bool:
    """Appartenenza al box chiuso, estremi compresi (P4.7:1837)."""
    return n_in[0] <= punto[0] <= n_in[1] and n_out[0] <= punto[1] <= n_out[1]


def fascia(punto: Sequence[float], vertici: Sequence[Punto],
           n_in: tuple[float, float] = BOX_DESIGN_N_IN,
           n_out: tuple[float, float] = BOX_DESIGN_N_OUT) -> str:
    """A dentro l'inviluppo, B dentro il box, C fuori dal box (P4.7:1835-1841)."""
    if not dentro_box(punto, n_in, n_out):
        return "C"
    return "A" if hull_margin_tok(punto, vertici) >= 0.0 else "B"


@dataclass(frozen=True)
class Hull:
    """Un inviluppo con il proprio box: le due facce che servono a una fascia."""

    vertici: tuple[Punto, ...]
    n_in: tuple[float, float]
    n_out: tuple[float, float]

    @classmethod
    def da_punti(cls, punti: Sequence[Punto], *,
                 box: Optional[tuple[tuple[float, float], tuple[float, float]]] = None
                 ) -> "Hull":
        """Inviluppo di un insieme, con box derivato dagli estremi se non dato.

        `box` esiste per il lato di progetto, dove P4.7:1837 dichiara il box
        prima e indipendentemente dall'inviluppo: gli estremi dei 10 punti
        coincidono con quel box, ma il numero deve restare quello dichiarato.
        """
        vertici = tuple(inviluppo_convesso(punti))
        if box is None:
            xs = [p[0] for p in punti]
            ys = [p[1] for p in punti]
            n_in, n_out = (min(xs), max(xs)), (min(ys), max(ys))
        else:
            n_in, n_out = box
        return cls(vertici=vertici, n_in=(float(n_in[0]), float(n_in[1])),
                   n_out=(float(n_out[0]), float(n_out[1])))


#: Il lato di progetto di F.13:1947-1953, calcolato e non scritto a mano.
HULL_DESIGN = Hull.da_punti(
    punti_di_disegno(), box=(BOX_DESIGN_N_IN, BOX_DESIGN_N_OUT))


@dataclass(frozen=True)
class Coverage:
    """L'esito pubblicato di F.13:1962-1964, con le colonne del protocollo."""

    coverage_tier_design: str
    hull_margin_design_tok: float
    coverage_tier_fit: Optional[str]
    hull_margin_tok: Optional[float]
    coverage_tier: str
    thin_support: bool
    sparse_support: bool
    out_of_coverage: bool


def valuta_copertura(n_in_target: float, n_out_target: float, *,
                     hull_design: Hull = HULL_DESIGN,
                     hull_fit: Optional[Hull] = None) -> Coverage:
    """Classifica il punto target su entrambi i lati e pubblica l'esito.

    Senza `hull_fit` (prima della campagna) il lato di fit non esiste e la
    pubblicazione e' quella del solo lato di progetto: i campi di fit restano
    `None` invece di essere riempiti con una geometria che non si e' ancora
    potuta calcolare.
    """
    punto = (float(n_in_target), float(n_out_target))
    tier_design = fascia(punto, hull_design.vertici, hull_design.n_in, hull_design.n_out)
    margin_design = hull_margin_tok(punto, hull_design.vertici)

    tier: str = tier_design
    thin = margin_design < SOGLIA_THIN_SUPPORT_TOK
    tier_fit: Optional[str] = None
    margin_fit: Optional[float] = None
    if hull_fit is not None:
        # il punto classificato sul lato di fit e' (x1_b, x2_b), la stessa base
        # dell'inviluppo: chi chiama passa i reali, non i target (F.13:1967-1969)
        tier_fit = fascia(punto, hull_fit.vertici, hull_fit.n_in, hull_fit.n_out)
        margin_fit = hull_margin_tok(punto, hull_fit.vertici)
        # "A" < "B" < "C" in ordine alfabetico: il massimo e' il piu' conservativo
        tier = max(tier_design, tier_fit)
        thin = thin or margin_fit < SOGLIA_THIN_SUPPORT_TOK

    return Coverage(
        coverage_tier_design=tier_design,
        hull_margin_design_tok=margin_design,
        coverage_tier_fit=tier_fit,
        hull_margin_tok=margin_fit,
        coverage_tier=tier,
        thin_support=thin,
        sparse_support=(tier == "B"),
        out_of_coverage=(tier == "C"),
    )
