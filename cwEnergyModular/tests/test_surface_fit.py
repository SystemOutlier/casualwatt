# -*- coding: utf-8 -*-
"""Guardia sul risolutore QR della superficie predittiva (P6.5).

Il file esiste perche' P6.5 prescrive come si stima la superficie di P3.3 --
matrice di disegno centrata e scalata, QR o SVD, mai equazioni normali, e
coefficienti riportati nelle unita' del modello con la trasformazione inversa
(`experiment_results/protocollo_v4_20261024.md`, `:2514-2524`) -- e la riga di
P5 nella tabella di testa lascia quella parte all'analisi. `surface_fit.py` e'
l'implementazione; qui se ne fissano le relazioni, non i numeri di una campagna
che non e' stata eseguita.

Le proprieta' verificate sono quattro famiglie.

  1. **Convenzione del disegno.** Sui 33 blocchi di P3.5, con la 2-norma e lo
     z-score a deviazione popolazione, il condizionamento e' `1,0227e5` grezzo e
     `3,761` standardizzato, il rango e' 4 e l'intercetta non viene scalata.
     Senza queste due convenzioni il numero pubblicato non e' riproducibile
     (P6.5, e `condizionamento_disegno_probe.py`).
  2. **Inversa della standardizzazione.** Un `beta` intero noto deve tornare
     indietro nelle unita' di P3.3: le predizioni coincidono, e i coefficienti
     non sono quelli del disegno scalato. Il test misura la trasformazione, non
     un numero di cifre: la misura delle cifre perse sta nel probe citato.
  3. **Pesi.** `w_b = 1/budget_fit_b^2` (F.9); con pesi uguali la stima coincide
     con i minimi quadrati non pesati; un budget nullo usa peso 1 e marca il
     blocco (P3.8), un budget negativo o non finito e' un errore dichiarato.
  4. **Rifiuto del degrado silenzioso.** Un disegno di rango inferiore a quattro
     solleva `ValueError` invece di essere regolarizzato, e il condizionamento
     riportato e' quello della matrice risolta (standardizzata), non il quadrato
     che si otterrebbe formando `X'WX`.

Non si verifica qui ne' la copertura degli intervalli (P4.8/P6.4) ne' HC3: non
appartengono a P6.5, e un test che li fingesse darebbe l'impressione che quella
parte sia stata arbitrata.
"""

from __future__ import annotations

import numpy as np
import pytest

from surface_fit import (
    BlockMeans,
    block_means,
    derived_quantities,
    design_matrix,
    fit_surface,
    predict,
    predict_block,
    standardize,
)

# P3.5: griglia 3x3 con il centro a 6 blocchi e il minimo (8,4) a 3; i due punti
# di conferma non entrano nel fit.
GRIGLIA = [(n_in, n_out) for n_in in (32, 128, 512) for n_out in (32, 128, 256)]
CENTRO = (128, 128)
MINIMO = (8, 4)


def punti_di_fit():
    """I 33 blocchi di P3.5, come coppie `(N_in, N_out)` target."""
    punti = []
    for punto in GRIGLIA:
        punti += [punto] * (6 if punto == CENTRO else 3)
    return punti + [MINIMO] * 3


def colonne_di_fit():
    punti = punti_di_fit()
    x1 = np.array([p[0] for p in punti], dtype=float)
    x2 = np.array([p[1] for p in punti], dtype=float)
    return x1, x2, x1 * x2


def cond2(matrix):
    """2-norma dichiarata da P6.5: sigma_max / sigma_min."""
    valori = np.linalg.svd(np.asarray(matrix, dtype=float), compute_uv=False)
    return float(valori[0] / valori[-1])


def test_disegno_congelato_ha_rango_pieno_e_condizionamento_dichiarato():
    """Sui 33 blocchi di P3.5 il disegno ha rango 4 e i due condizionamenti di P6.5.

    `1,0227e5` e' il valore della 2-norma sul disegno grezzo, `3,761` quello sul
    disegno con i predittori in z-score e l'intercetta intatta: sono le due
    convenzioni che P6.5 dichiara, e cambiarne una cambia il numero senza
    cambiare il disegno.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    Z = standardize(X).matrix

    assert X.shape == (33, 4)
    assert np.linalg.matrix_rank(X) == 4
    assert cond2(X) == pytest.approx(1.0227e5, rel=1e-4)
    assert cond2(Z) == pytest.approx(3.761, abs=1e-3)


def test_la_standardizzazione_lascia_l_intercetta_intatta():
    """L'intercetta resta esattamente 1 e le altre colonne in z-score a `ddof=0`.

    Se anche la colonna costante fosse centrata e scalata, il disegno perderebbe
    l'intercetta e il modello di P3.3 non avrebbe piu' `E0`; il test fissa la
    convenzione `ddof=0` perche' e' quella che rigenera il `3,761` pubblicato.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    design = standardize(X)

    assert np.array_equal(design.matrix[:, 0], np.ones(33))
    assert not design.scaled[0]
    assert design.scale[0] == 0.0
    assert np.array_equal(design.scale, X.std(axis=0))
    for colonna in (1, 2, 3):
        assert design.matrix[:, colonna].mean() == pytest.approx(0.0, abs=1e-12)
        assert design.matrix[:, colonna].std() == pytest.approx(1.0, abs=1e-12)


def test_recupera_i_coefficienti_di_p3_3_sui_dati_esatti():
    """Con `y = X beta` e `beta` noto, la stima torna nelle unita' di P3.3.

    E' il test dell'inversa della standardizzazione: se `beta` restasse quello
    del disegno scalato, `E0` sarebbe sbagliato di ordini di grandezza mentre le
    predizioni coinciderebbero. La soglia e' larga di proposito: la misura delle
    cifre perse sui 24 casi sta in `condizionamento_disegno_probe.py`, non qui.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    beta_vero = np.array([5.0, 7.0, 11.0, 3.0])
    fit = fit_surface(
        BlockMeans(x1=x1, x2=x2, x12=x12, y=X @ beta_vero,
                   m=np.full(33, 3)), np.ones(33))

    errore = np.max(np.abs(fit.beta - beta_vero) / np.abs(beta_vero))
    assert errore < 1e-9
    assert fit.beta.shape == (4,)
    assert fit.beta[0] == pytest.approx(5.0, rel=1e-9)
    assert np.allclose(predict_block(fit.beta, x1, x2, x12), X @ beta_vero,
                       rtol=1e-12, atol=1e-9)


def test_pesi_uguali_riproducono_i_minimi_quadrati_non_pesati():
    """Con `w_b` tutti uguali la WLS coincide con la OLS di riferimento.

    E' la relazione che lega F.9 al caso non pesato: se il peso entrasse due
    volte, o solo su una delle due parti (`A` e `y`), la stima si sposterebbe.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    rng = np.random.default_rng(20261107)
    y = X @ np.array([5.0, 7.0, 11.0, 3.0]) + 0.01 * rng.standard_normal(33)
    fit = fit_surface(
        BlockMeans(x1=x1, x2=x2, x12=x12, y=y, m=np.full(33, 3)), np.ones(33))
    riferimento = np.linalg.lstsq(X, y, rcond=None)[0]

    assert fit.beta == pytest.approx(riferimento, rel=1e-8)


def test_il_condizionamento_riportato_e_quello_della_matrice_risolta():
    """Il condizionamento e' quello di `sqrt(w) Z`, non il suo quadrato.

    Formare `X'WX` porterebbe il condizionamento a `cond(X)^2` (misurato dal
    probe: `1,0e10` sul grezzo, verifica 5); qui il valore riportato e' quello
    della matrice che il solve attraversa davvero, e il test lo confronta con il
    quadrato per mostrare che i due non coincidono.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    fit = fit_surface(
        BlockMeans(x1=x1, x2=x2, x12=x12, y=X @ np.array([5.0, 7.0, 11.0, 3.0]),
                   m=np.full(33, 3)), np.ones(33))

    assert fit.rank == 4
    assert fit.condition == pytest.approx(cond2(standardize(X).matrix),
                                          rel=1e-12)
    assert fit.condition < 10.0
    assert cond2(X.T @ X) > 1e9


def test_budget_nullo_usa_peso_uguale_e_marca_il_blocco():
    """`budget_fit = 0` non produce un peso infinito: peso 1 e blocco marcato.

    P3.8 lo dice per il singolo blocco ("si usa peso uguale e si marca il
    blocco"); senza il marcatore l'analisi non saprebbe che quella riga non ha
    un budget, e un `1/0` silenzioso la escluderebbe di fatto dal fit.
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    budget = np.full(33, 0.5)
    budget[7] = 0.0
    fit = fit_surface(
        BlockMeans(x1=x1, x2=x2, x12=x12,
                   y=X @ np.array([5.0, 7.0, 11.0, 3.0]), m=np.full(33, 3)),
        budget)

    assert fit.equal_weight_blocks == (7,)
    assert fit.weights[7] == 1.0
    assert np.allclose(np.delete(fit.weights, 7), 1.0 / 0.5 ** 2)


@pytest.mark.parametrize("budget_non_valido", [-0.1, float("nan"), float("inf")])
def test_budget_non_valido_e_un_errore_dichiarato(budget_non_valido):
    """Un budget negativo o non finito e' un errore, non un peso da inventare.

    Un budget e' una semi-ampiezza conservativa: se ha segno o non e' finito, il
    peso che ne deriva non e' interpretabile, e nessun clamp e' ammesso (la
    regola dei clamp a zero vale per le grandezze energetiche, non per i pesi).
    """
    x1, x2, x12 = colonne_di_fit()
    X = design_matrix(x1, x2, x12)
    budget = np.full(33, 0.5)
    budget[3] = budget_non_valido

    with pytest.raises(ValueError):
        fit_surface(BlockMeans(x1=x1, x2=x2, x12=x12, y=X @ np.ones(4),
                               m=np.full(33, 3)), budget)


def test_disegno_di_rango_inferiore_e_un_errore_dichiarato():
    """Rango < 4 non si risolve con una pseudoinversa: si rifiuta.

    P6.5 dichiara il rango pieno come condizione del disegno; un solve al minimo
    delle norme sceglierebbe in silenzio una soluzione diversa da quella di
    F.9, quindi il modulo deve fermarsi e nominare i valori singolari.
    """
    x1, x2, _ = colonne_di_fit()
    y = np.zeros(33)
    with pytest.raises(ValueError, match="almeno"):
        fit_surface(BlockMeans(x1=x1[:3], x2=x2[:3], x12=(x1 * x2)[:3],
                               y=y[:3], m=np.full(3, 3)), np.ones(3))

    x12_collineare = np.array([2.0, 4.0, 6.0, 8.0, 10.0, 12.0])
    with pytest.raises(ValueError, match="rango"):
        fit_surface(BlockMeans(x1=np.arange(1.0, 7.0),
                               x2=np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
                               x12=x12_collineare, y=np.arange(6.0),
                               m=np.full(6, 3)), np.ones(6))


def test_media_di_blocco_usa_la_media_dei_prodotti():
    """F.7: `x12_b` e' la media dei prodotti, non il prodotto delle medie.

    Se le richieste di un blocco hanno token diversi, le due grandezze non
    coincidono e il modello lineare smetterebbe di essere esatto sul blocco.
    Il test costruisce `e_act` dal modello richiesta per richiesta e chiede alla
    stima di tornare: con il prodotto delle medie non tornerebbe.
    """
    richieste = [
        [(10.0, 5.0), (12.0, 6.0), (11.0, 7.0)],
        [(20.0, 10.0), (21.0, 9.0), (19.0, 11.0)],
        [(30.0, 40.0), (31.0, 39.0), (29.0, 41.0)],
        [(50.0, 80.0), (51.0, 79.0), (49.0, 81.0)],
    ]
    beta_vero = np.array([5.0, 7.0, 11.0, 3.0])

    def energia(n_in, n_out):
        return beta_vero[0] + beta_vero[1] * n_in + beta_vero[2] * n_out \
            + beta_vero[3] * n_in * n_out

    blocchi = [[(n_in, n_out, energia(n_in, n_out)) for n_in, n_out in blocco]
               for blocco in richieste]
    means = block_means(blocchi)
    fit = fit_surface(means, np.ones(4))

    assert means.m.tolist() == [3, 3, 3, 3]
    assert means.x12[0] != pytest.approx(means.x1[0] * means.x2[0])
    assert fit.beta == pytest.approx(beta_vero, rel=1e-12)
    assert predict_block(fit.beta, means.x1, means.x2,
                         means.x12) == pytest.approx(means.y, rel=1e-12)


def test_previsione_di_richiesta_e_di_blocco_coincidono_solo_senza_dispersione():
    """`predict` e `predict_block` coincidono se e solo se `x12 = x1 * x2`.

    Sulle richieste di un blocco con token diversi le due grandezze divergono:
    `predict` ricostruisce il prodotto, `predict_block` riceve la media dei
    prodotti. E' la distinzione di F.7, e un chiamante che usasse `predict` su un
    blocco otterrebbe una previsione sistematicamente piu' bassa quando `c > 0`.
    """
    beta = np.array([5.0, 7.0, 11.0, 3.0])
    assert predict(beta, 32.0, 32.0) == pytest.approx(
        predict_block(beta, 32.0, 32.0, 32.0 * 32.0))

    means = block_means([[(10.0, 5.0, 0.0), (12.0, 6.0, 0.0), (11.0, 7.0, 0.0)]])
    assert means.x12[0] > means.x1[0] * means.x2[0]
    assert predict(beta, means.x1[0], means.x2[0]) < predict_block(
        beta, means.x1[0], means.x2[0], means.x12[0])


def test_quantita_derivate_di_f8_ai_punti_di_riferimento():
    """`J/token`, le due derivate parziali e `share_E0` seguono F.8 alla lettera.

    A `(32,32)` con `beta = (5,7,11,3)`: `E_model = 3653 J`, `J/token =
    114,15625`, `dE/dN_in = a + c*N_out = 103`, `dE/dN_out = b + c*N_in = 107`.
    Le derivate portano la coordinata giusta: scambiarle e' il difetto che il
    protocollo ha chiuso il 2026-10-25.
    """
    beta = np.array([5.0, 7.0, 11.0, 3.0])
    corto = derived_quantities(beta, 32.0, 32.0)
    centro = derived_quantities(beta, 128.0, 128.0)

    assert corto.e_model_j == pytest.approx(3653.0)
    assert corto.j_per_token == pytest.approx(3653.0 / 32.0)
    assert corto.de_dn_in == pytest.approx(103.0)
    assert corto.de_dn_out == pytest.approx(107.0)
    assert corto.share_e0 == pytest.approx(5.0 / 3653.0)

    assert centro.e_model_j == pytest.approx(51461.0)
    assert centro.j_per_token == pytest.approx(51461.0 / 128.0)
    assert centro.de_dn_in == pytest.approx(7.0 + 3.0 * 128.0)
    assert centro.de_dn_out == pytest.approx(11.0 + 3.0 * 128.0)


def test_j_per_token_rifiuta_un_denominatore_non_positivo():
    """`J/token` a `N_out,ref <= 0` non e' definito e non si inventa.

    F.8 divide per `N_out,ref`; zero o negativo non sono geometrie del disegno,
    e un rapporto calcolato lo stesso sarebbe un numero senza significato.
    """
    beta = np.array([5.0, 7.0, 11.0, 3.0])
    for n_out in (0.0, -4.0):
        with pytest.raises(ValueError, match="N_out"):
            derived_quantities(beta, 32.0, n_out)
