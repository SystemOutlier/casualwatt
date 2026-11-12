# -*- coding: utf-8 -*-
"""cwEnergyModular/energy/statistical_uncertainty.py — Priorita' 7.

Incertezza statistica su campioni di misura energetica (potenza in W, energia in J).

Perche' esiste. `tools/gate_uncertainty.py` combina componenti di incertezza già
stimate (GUM RSS) ma non stima nulla da campioni. `evaluation_runner.wilson_ci`
e `cluster_bootstrap_interval` operano su esiti binari di valutazione, non su
campioni di misura energetica. Questo modulo colma il vuoto per le grandezze
continue (W, J) e riusa Wilson per le proporzioni.

Il modulo e' di **sola analisi**: non tocca il percorso di misura, non aggiunge
colonne CSV, non modifica `local_energy.py`, `energy_session.py` o `benchmark_v4.py`.
Nessuna dipendenza esterna: solo stdlib (`math`, `statistics`, `random`).

Contratto:
- `sample_mean(values)` -> Optional[float]
- `sample_std(values)` -> Optional[float]  (ddof=1, None se n < 2, mai zero inventato)
- `mean_ci_t(values, confidence=0.95)` -> SampleStatistics  (t-distribution; n=3 -> invalido per P4.12)
- `bootstrap_percentile_ci(values, statistic=mean, n_resamples=2000, seed=20261104, confidence=0.95)` -> SampleStatistics
- `wilson_ci_proportion(successes, trials, confidence=0.95)` -> SampleStatistics  (riuso da evaluation_runner)

Regole di validita':
- lista vuota / tutti None o non finiti -> valid=False, value=None
- n < 2 per std e bootstrap -> valid=False
- n = 3 per mean_ci_t nel protocollo energetico -> valid=False (non si stima varianza, CI su budget/semi-range non su sigma)
- successes > trials o trials < 1 per Wilson -> valid=False
"""

from __future__ import annotations

from dataclasses import dataclass
from math import erf, exp, log, sqrt
from random import Random
from statistics import fmean
from typing import Callable, Optional, Sequence, Union

#: Seme fisso per il bootstrap percentile: l'intervallo deve essere rigenerabile
#: dalla stessa riga, non un numero diverso a ogni esecuzione.
BOOTSTRAP_SEED = 20261104
#: Numero di ricampionamenti predefinito per il bootstrap percentile.
BOOTSTRAP_RESAMPLES = 2000

#: Gradi di libertà oltre i quali il critico di Student e' approssimato dalla
#: quantile normale (l'errore e' trascurabile per il nostro scopo descrittivo).
_T_DF_NORMAL_CUTOFF = 30

# Critici della t-distribution (due code) per gradi di liberta' 1..30, alpha = 0.05 (95%).
# Valori da tavole standard di Student (t_{0.975, df}).
_T_CRIT_95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}

# Critico normale per il 95% (due code).
_Z_95 = 1.959963984540054


@dataclass(frozen=True)
class SampleStatistics:
    """Esito di un calcolo di incertezza su un campione di misura."""

    method: str
    n: int
    valid: bool
    reason: str
    value: Optional[float]
    ci_lower: Optional[float]
    ci_upper: Optional[float]


def _finite_values(values: Sequence[Optional[Union[int, float]]]) -> list[float]:
    """Filtra i valori finiti, scartando None, NaN e infiniti."""
    out: list[float] = []
    for v in values:
        if v is None or isinstance(v, bool):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError, OverflowError):
            continue
        if not (fv != fv or fv in (float("inf"), float("-inf"))):
            out.append(fv)
    return out


def sample_mean(values: Sequence[Optional[Union[int, float]]]) -> Optional[float]:
    """Media campionaria; None se nessun valore finito."""
    finiti = _finite_values(values)
    if not finiti:
        return None
    return fmean(finiti)


def sample_std(values: Sequence[Optional[Union[int, float]]]) -> Optional[float]:
    """Deviazione standard campionaria (ddof = 1).

    Restituisce None se n < 2: non si inventa mai uno zero al posto di una
    varianza non stimabile (regola P4.12).
    """
    finiti = _finite_values(values)
    n = len(finiti)
    if n < 2:
        return None
    media = fmean(finiti)
    varianza = sum((x - media) ** 2 for x in finiti) / (n - 1)
    return sqrt(varianza)


def _t_crit(df: int, confidence: float) -> float:
    """Critico della t-distribution per due code.

    Usa tavole hardcoded per df 1..30 al 95%; oltre approssima con la normale.
    Per confidence diverso da 0.95 e df <= 30 si usa un'interpolazione
    lineare tra i critici 95% (semplificazione dichiarata, accettabile per
    descrittività). Oltre df=30 la normale e' entro l'1% del critico esatto.
    """
    if confidence <= 0.0 or confidence >= 1.0:
        return float("nan")
    if df <= 0:
        return float("nan")
    if df > _T_DF_NORMAL_CUTOFF:
        return _normal_ppf((1.0 + confidence) / 2.0)
    crit95 = _T_CRIT_95.get(df)
    if crit95 is None:
        return _normal_ppf((1.0 + confidence) / 2.0)
    if abs(confidence - 0.95) < 1e-12:
        return crit95
    # Approssimazione dichiarata: scalano lineare intorno al critico 95%.
    # Non e' esatto per confidence arbitrari, ma il modulo opera a 95% per default.
    z = _normal_ppf((1.0 + confidence) / 2.0)
    z95 = _normal_ppf(0.975)
    return crit95 * (z / z95) if z95 != 0 else crit95


def _normal_ppf(p: float) -> float:
    """Quantile della normale standard via approssimazione di Acklam (singola precisione)."""
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    # Coefficienti di Acklam per la funzione inversa di erf.
    a = [
        -3.969683028665376e+01, 2.209460984245205e+02,
        -2.759285104469687e+02, 1.383577518672690e+02,
        -3.066479806614716e+01, 2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01, 1.615858368580409e+02,
        -1.556989798598866e+02, 6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03, -3.223964580411365e-01,
        -2.400758277161838e+00, -2.549732539343734e+00,
        4.374664141464968e+00, 2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03, 3.224671290700398e-01,
        2.445134137142996e+00, 3.754408661907416e+00,
    ]
    plow = 0.02425
    phigh = 1 - plow
    if p < plow:
        q = sqrt(-2 * log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
               (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)
    q = sqrt(-2 * log(1 - p))
    return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
           ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)


def _percentile(valori: list[float], q: float) -> float:
    """Percentile con interpolazione lineare sui ranghi (come numpy default)."""
    if not valori:
        return float("nan")
    valori_ord = sorted(valori)
    posizione = (len(valori_ord) - 1) * q
    basso = int(__import__("math").floor(posizione))
    alto = int(__import__("math").ceil(posizione))
    if basso == alto:
        return valori_ord[basso]
    return valori_ord[basso] + (valori_ord[alto] - valori_ord[basso]) * (posizione - basso)


def mean_ci_t(
    values: Sequence[Optional[Union[int, float]]],
    confidence: float = 0.95,
) -> SampleStatistics:
    """Intervallo di confidenza per la media con t-distribution di Student.

    Regola P4.12: con n = 3 non si stima una varianza, quindi l'intervallo
    basato su sigma e' invalido per il protocollo energetico. Il campo
    `valid` e' False e `reason` lo dichiara; la CI andrebbe basata su
    budget/semi-range, non su sigma.

    Restituisce SampleStatistics con `value` = media campionaria.
    """
    method = "mean-ci-t"
    finiti = _finite_values(values)
    n = len(finiti)
    if n == 0:
        return SampleStatistics(method, n, False, "campione vuoto o nessun valore finito", None, None, None)
    if n < 2:
        return SampleStatistics(method, n, False, "n < 2: non si stima varianza", None, None, None)
    if n == 3:
        return SampleStatistics(
            method, n, False,
            "n = 3: non si stima una varianza (P4.12); CI su budget/semi-range, non su sigma",
            None, None, None,
        )
    media = fmean(finiti)
    std = sample_std(finiti)
    if std is None:
        return SampleStatistics(method, n, False, "deviazione standard non calcolabile", None, None, None)
    critico = _t_crit(n - 1, confidence)
    errore_std = std / sqrt(n)
    margine = critico * errore_std
    return SampleStatistics(method, n, True, "", media, media - margine, media + margine)


def bootstrap_percentile_ci(
    values: Sequence[Optional[Union[int, float]]],
    statistic: Callable[[Sequence[float]], Optional[float]] = sample_mean,
    n_resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = 0.95,
) -> SampleStatistics:
    """Intervallo percentile di bootstrap per una statistica del campione.

    Semine fisse (`seed`) per riprodurre lo stesso intervallo da uno stesso
    campione. `n_resamples = 2000` per default (coerente con
    `evaluation_runner.cluster_bootstrap_interval`).

    Restituisce SampleStatistics con `value` = statistica sul campione originale.
    """
    method = "bootstrap-percentile"
    finiti = _finite_values(values)
    n = len(finiti)
    if n < 2:
        return SampleStatistics(method, n, False, "n < 2: bootstrap non calcolabile", None, None, None)
    if n_resamples < 1:
        return SampleStatistics(method, n, False, "n_resamples < 1", None, None, None)
    valore_puntuale = statistic(finiti)
    if valore_puntuale is None:
        return SampleStatistics(method, n, False, "statistica sul campione non calcolabile", None, None, None)
    rng = Random(seed)
    stime: list[float] = []
    for _ in range(n_resamples):
        campione = [finiti[rng.randrange(n)] for _ in range(n)]
        st = statistic(campione)
        if st is not None:
            stime.append(st)
    if len(stime) < 2:
        return SampleStatistics(method, n, False, "bootstrap degenerato: nessun ricampiono valido", None, None, None)
    stime.sort()
    alpha_tail = (1.0 - confidence) / 2.0
    lo = _percentile(stime, alpha_tail)
    hi = _percentile(stime, 1.0 - alpha_tail)
    return SampleStatistics(method, n, True, "", valore_puntuale, lo, hi)


def wilson_ci_proportion(
    successes: int,
    trials: int,
    confidence: float = 0.95,
) -> SampleStatistics:
    """Intervallo di Wilson per una proporzione binaria.

    Riesposto da `evaluation_runner.wilson_ci` per i campioni di misura
    energetica (es. frazione di run sotto soglia). Non e' una nuova stima:
    delega alla funzione esistente.
    """
    from evaluation_runner import wilson_ci  # import locale per non creare dipendenza circolare a livello di pacchetto

    method = "wilson-proportion"
    if trials < 1:
        return SampleStatistics(method, trials, False, "trials < 1", None, None, None)
    if successes < 0 or successes > trials:
        return SampleStatistics(method, trials, False, "successes fuori da [0, trials]", None, None, None)
    lo, hi = wilson_ci(trials, successes, confidence)
    proporzione = successes / trials
    return SampleStatistics(method, trials, True, "", proporzione, lo, hi)
