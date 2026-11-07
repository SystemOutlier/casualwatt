# -*- coding: utf-8 -*-
"""P6.5 — il risolutore della superficie predittiva (F.8, F.9).

Il protocollo prescrive QR o SVD sui predittori centrati e scalati, mai le
equazioni normali, e coefficienti riportati nelle unita' di P3.3 con la
trasformazione inversa della standardizzazione
(`experiment_results/protocollo_v4_20261024.md`, P6.5 `:2514-2524`). La riga di
P5 nella tabella di testa dello stesso documento lascia esplicitamente
all'analisi "il risolutore QR/SVD che P6.5 prescrive": questo modulo e' quella
parte, e non tocca ne' lo schema CSV ne' il percorso di misura.

Cosa fa: costruisce il disegno di F.7 (una riga per blocco, `x12` media dei
prodotti), standardizza le sole colonne non costanti lasciando intatta
l'intercetta, risolve i minimi quadrati pesati di F.9 con QR sul disegno pesato,
e riporta `beta` in joule e J/token. Cosa **non** fa: non stima gli errori HC3,
non esegue il bootstrap di F.14, non assegna fasce di copertura. Sono punti di
P3.8/P4.7/P4.8, non di P6.5.

Due convenzioni sono dichiarate perche' senza di esse il numero non e'
riproducibile (P6.5, seconda meta' del punto): il condizionamento e' la 2-norma
`sigma_max/sigma_min`; "standardizzato" e' lo z-score con deviazione popolazione
(`ddof = 0`, la stessa usata da `condizionamento_disegno_probe.py`) sulle colonne
a varianza non nulla, con la colonna dell'intercetta non toccata.

Nessun degrado silenzioso: un budget di fit non finito o negativo e' un errore,
un disegno di rango inferiore a quattro e' un errore che nomina i valori
singolari invece di essere regolarizzato con una pseudoinversa, e un budget
nullo usa peso 1 lasciando il blocco marcato in `equal_weight_blocks`
(P3.8: "si usa peso uguale e si marca il blocco").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

#: P3.3: ordine congelato dei parametri, e nessun termine quadratico.
PARAMETER_NAMES = ("E0", "a", "b", "c")
N_PARAMETERS = len(PARAMETER_NAMES)


@dataclass(frozen=True)
class BlockMeans:
    """Le quattro medie di blocco di F.7, una riga per blocco."""

    x1: np.ndarray
    x2: np.ndarray
    x12: np.ndarray
    y: np.ndarray
    m: np.ndarray


@dataclass(frozen=True)
class StandardizedDesign:
    """Disegno standardizzato con la trasformazione inversa dichiarata."""

    matrix: np.ndarray
    center: np.ndarray
    scale: np.ndarray
    scaled: np.ndarray


@dataclass(frozen=True)
class SurfaceFit:
    """Coefficienti in unita' di P3.3 e cio' che serve a ricontrollare il solve."""

    beta: np.ndarray
    beta_standardized: np.ndarray
    weights: np.ndarray
    equal_weight_blocks: tuple[int, ...]
    rank: int
    condition: float


@dataclass(frozen=True)
class DerivedQuantities:
    """Le quantita' di F.8 a un punto di riferimento."""

    n_in_ref: float
    n_out_ref: float
    e_model_j: float
    j_per_token: float
    de_dn_in: float
    de_dn_out: float
    share_e0: float | None


def _finite_1d(name: str, values) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    if arr.ndim != 1:
        raise ValueError("%s deve essere un vettore, non una matrice %s"
                         % (name, arr.shape))
    if not np.all(np.isfinite(arr)):
        raise ValueError("%s contiene valori non finiti" % name)
    return arr


def block_means(blocks: Sequence[Sequence[Sequence[float]]]) -> BlockMeans:
    """F.7: le medie di blocco, con `x12` media dei prodotti.

    `blocks` e' una sequenza di blocchi, ciascuno una sequenza di richieste
    `(n_in, n_out, e_act)`. `x12_b = (1/m) sum_i N_in,i * N_out,i`, non il
    prodotto delle medie: e' la forma che rende esatta la linearizzazione anche
    con nonce di lunghezza diversa (P3.7, F.7). Un blocco senza richieste non e'
    un blocco e solleva `ValueError`.
    """
    x1, x2, x12, y, m = [], [], [], [], []
    for indice, richieste in enumerate(blocks):
        try:
            arr = np.asarray(list(richieste), dtype=float)
        except (TypeError, ValueError) as errore:
            raise ValueError("blocco %d: richieste non numeriche (%s)"
                             % (indice, errore)) from errore
        if arr.ndim != 2 or arr.shape[1] != 3:
            raise ValueError(
                "blocco %d: attese righe (n_in, n_out, e_act), ricevute %s"
                % (indice, arr.shape))
        if not np.all(np.isfinite(arr)):
            raise ValueError("blocco %d: valori non finiti" % indice)
        n_in, n_out, e_act = arr[:, 0], arr[:, 1], arr[:, 2]
        x1.append(float(n_in.mean()))
        x2.append(float(n_out.mean()))
        x12.append(float((n_in * n_out).mean()))
        y.append(float(e_act.mean()))
        m.append(arr.shape[0])
    if not x1:
        raise ValueError("nessun blocco da aggregare")
    return BlockMeans(x1=np.array(x1), x2=np.array(x2), x12=np.array(x12),
                      y=np.array(y), m=np.array(m, dtype=int))


def design_matrix(x1, x2, x12) -> np.ndarray:
    """Il disegno di P3.3/F.7: `(1, x1, x2, x12)`, nessun termine quadratico."""
    x1 = _finite_1d("x1", x1)
    x2 = _finite_1d("x2", x2)
    x12 = _finite_1d("x12", x12)
    if not (x1.shape == x2.shape == x12.shape):
        raise ValueError("x1, x2 e x12 devono avere la stessa lunghezza")
    return np.column_stack([np.ones_like(x1), x1, x2, x12])


def standardize(matrix) -> StandardizedDesign:
    """z-score delle colonne non costanti, intercetta intatta (P6.5).

    La deviazione e' quella di popolazione (`ddof = 0`): e' la convenzione con
    cui `condizionamento_disegno_probe.py` ha rigenerato il valore pubblicato
    `3,761`, e senza dichiararla il numero non e' riproducibile. Una colonna a
    varianza nulla non viene scalata: per l'intercetta significa restare
    esattamente 1, per una colonna vuota significa che il rango la rifiutera'.
    """
    X = np.asarray(matrix, dtype=float)
    if X.ndim != 2 or X.shape[1] != N_PARAMETERS:
        raise ValueError("disegno atteso con %d colonne, ricevute %s"
                         % (N_PARAMETERS, X.shape))
    if not np.all(np.isfinite(X)):
        raise ValueError("il disegno contiene valori non finiti")
    center = X.mean(axis=0)
    scale = X.std(axis=0)
    scaled = scale > 0.0
    Z = X.copy()
    Z[:, scaled] = (X[:, scaled] - center[scaled]) / scale[scaled]
    return StandardizedDesign(matrix=Z, center=center, scale=scale,
                              scaled=scaled)


def _to_p33_units(beta_standardized: np.ndarray,
                  design: StandardizedDesign) -> np.ndarray:
    """Trasformazione inversa: `beta_grezzo_j = beta_z_j / sigma_j` e
    `beta_0 = beta_z_0 - sum_j beta_grezzo_j * mu_j` (P6.5, P3.3).

    Restituire i coefficienti senza questo passaggio significa pubblicarli in
    unita' che non sono quelle del modello: le predizioni coinciderebbero, i
    coefficienti no.
    """
    beta = np.array(beta_standardized, dtype=float)
    scaled = design.scaled
    beta[scaled] = beta_standardized[scaled] / design.scale[scaled]
    beta[0] = beta_standardized[0] - float(
        (beta[scaled] * design.center[scaled]).sum())
    return beta


def fit_surface(means: BlockMeans, budget_fit) -> SurfaceFit:
    """Minimi quadrati pesati di F.9 con QR sul disegno standardizzato.

    Il problema risolto e' `min sum_b w_b (y_b - X_b beta)^2` con
    `w_b = 1/budget_fit_b^2`; le righe si scalano con `sqrt(w)` e si risolve
    `A = sqrt(w) * Z` per QR, mai formando `X'WX`. Il rango e' controllato con
    l'SVD di `A` prima del solve: una pseudoinversa silenziosa cambierebbe il
    modello senza dirlo, quindi un disegno di rango inferiore a 4 solleva
    `ValueError` con i valori singolari.
    """
    X = design_matrix(means.x1, means.x2, means.x12)
    y = _finite_1d("y", means.y)
    budget = _finite_1d("budget_fit", budget_fit)
    if not (X.shape[0] == y.shape[0] == budget.shape[0]):
        raise ValueError("disegno, y e budget_fit devono avere lo stesso numero "
                         "di blocchi")
    if np.any(budget < 0.0):
        raise ValueError("budget_fit negativo: un budget e' una semi-ampiezza, "
                         "non un valore con segno")
    if y.shape[0] < N_PARAMETERS:
        raise ValueError("servono almeno %d blocchi, ricevuti %d"
                         % (N_PARAMETERS, y.shape[0]))

    equal_weight = np.flatnonzero(budget == 0.0)
    positive = budget > 0.0
    weights = np.empty_like(budget)
    weights[positive] = 1.0 / np.square(budget[positive])
    weights[~positive] = 1.0

    design = standardize(X)
    root_w = np.sqrt(weights)
    weighted = design.matrix * root_w[:, None]
    rhs = y * root_w

    singular = np.linalg.svd(weighted, compute_uv=False)
    tolleranza = (float(singular[0]) * max(weighted.shape)
                  * np.finfo(float).eps) if singular[0] > 0.0 else 0.0
    rank = int(np.sum(singular > tolleranza))
    if rank < N_PARAMETERS:
        raise ValueError(
            "disegno di rango %d su %d parametri: il modello non e' stimabile "
            "su questi blocchi (valori singolari: %s)"
            % (rank, N_PARAMETERS,
               ", ".join("%.3e" % v for v in singular)))

    q, r = np.linalg.qr(weighted, mode="reduced")
    beta_standardized = np.linalg.solve(r, q.T @ rhs)
    beta = _to_p33_units(beta_standardized, design)

    return SurfaceFit(
        beta=beta,
        beta_standardized=beta_standardized,
        weights=weights,
        equal_weight_blocks=tuple(int(i) for i in equal_weight),
        rank=rank,
        condition=float(singular[0] / singular[-1]),
    )


def predict(beta, n_in, n_out):
    """`E_model` di F.8 a una geometria di richiesta: `x12 = N_in * N_out`.

    Vale per i punti di riferimento di F.8, dove le due coordinate sono quelle
    di una singola richiesta. Su un blocco non si usa: li' il terzo predittore
    e' la media dei prodotti (`predict_block`), e il prodotto delle medie e'
    un'altra grandezza (F.7).
    """
    beta = _finite_1d("beta", beta)
    if beta.shape != (N_PARAMETERS,):
        raise ValueError("beta deve avere %d coefficienti, ricevuti %d"
                         % (N_PARAMETERS, beta.shape[0]))
    n_in = np.asarray(n_in, dtype=float)
    n_out = np.asarray(n_out, dtype=float)
    return beta[0] + beta[1] * n_in + beta[2] * n_out + beta[3] * n_in * n_out


def predict_block(beta, x1, x2, x12):
    """`E_model` su una riga di disegno F.7: il terzo predittore arriva esplicito.

    `x12_b` e' la media dei prodotti, quindi non e' ricostruibile da `x1_b` e
    `x2_b`; chiederlo come argomento impedisce di sostituirvi il prodotto delle
    medie, che darebbe un numero diverso sullo stesso blocco.
    """
    beta = _finite_1d("beta", beta)
    if beta.shape != (N_PARAMETERS,):
        raise ValueError("beta deve avere %d coefficienti, ricevuti %d"
                         % (N_PARAMETERS, beta.shape[0]))
    x1 = np.asarray(x1, dtype=float)
    x2 = np.asarray(x2, dtype=float)
    x12 = np.asarray(x12, dtype=float)
    return beta[0] + beta[1] * x1 + beta[2] * x2 + beta[3] * x12


def derived_quantities(beta, n_in_ref: float, n_out_ref: float) -> DerivedQuantities:
    """Le cinque quantita' di F.8 al punto di riferimento (P3.4).

    I segni si conservano e non si applica nessun clamp: `J/token` e
    `share_E0` sono rapporti, e i flag `intercept_nonphysical` e
    `pred_nonpositive` appartengono all'analisi di P3.10/P3.13, non qui. Per
    `N_out,ref <= 0` la quantita' non e' definita e l'input e' rifiutato.
    """
    beta = _finite_1d("beta", beta)
    if beta.shape != (N_PARAMETERS,):
        raise ValueError("beta deve avere %d coefficienti, ricevuti %d"
                         % (N_PARAMETERS, beta.shape[0]))
    n_in_ref = float(n_in_ref)
    n_out_ref = float(n_out_ref)
    if not (np.isfinite(n_in_ref) and np.isfinite(n_out_ref)):
        raise ValueError("punto di riferimento non finito")
    if n_out_ref <= 0.0:
        raise ValueError("J/token e' definito per N_out,ref > 0 (F.8)")

    e_model = float(predict(beta, n_in_ref, n_out_ref))
    return DerivedQuantities(
        n_in_ref=n_in_ref,
        n_out_ref=n_out_ref,
        e_model_j=e_model,
        j_per_token=e_model / n_out_ref,
        de_dn_in=float(beta[1] + beta[3] * n_out_ref),
        de_dn_out=float(beta[2] + beta[3] * n_in_ref),
        share_e0=(float(beta[0] / e_model) if e_model != 0.0 else None),
    )
