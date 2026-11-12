# -*- coding: utf-8 -*-
"""Test per statistical_uncertainty.py (Priorita' 7).

Questi test verificano:
- std campionario corretto su campione noto, None se n < 2 (mai zero inventato)
- media campionaria coerente
- CI per la media con t-distribution contiene la media su sintetico
- n = 3 -> invalido per protocollo energetico (P4.12: non si stima varianza)
- bootstrap percentile con seme fisso -> deterministico e rigenerabile
- bootstrap con semi diversi -> intervalli diversi
- Wilson CI per proporzioni attorno alla proporzione osservata
- nessuna colonna CSV nuova aggiunta allo schema P5
- il modulo importa solo stdlib (isolamento dal percorso di misura)
"""

import ast
import importlib
import inspect
import math
import sys
from pathlib import Path

import pytest

# Assicura che cwEnergyModular sia importabile anche da radice del repo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.statistical_uncertainty import (  # noqa: E402
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    SampleStatistics,
    bootstrap_percentile_ci,
    mean_ci_t,
    sample_mean,
    sample_std,
    wilson_ci_proportion,
)


def test_sample_std_campione_noto():
    """Deviazione standard campionaria (ddof=1) su [1,2,3,4,5] = sqrt(2.5)."""
    std = sample_std([1.0, 2.0, 3.0, 4.0, 5.0])
    assert std is not None
    assert abs(std - math.sqrt(2.5)) < 1e-9


def test_sample_std_n_minore_di_2_non_inventa_zero():
    """Con n < 2 la std e' None: non si inventa mai uno zero al suo posto."""
    assert sample_std([]) is None
    assert sample_std([42.0]) is None
    assert sample_std([None, None]) is None
    assert sample_std([1.0, None]) is None


def test_sample_mean_corretta_su_campione_noto():
    """Media di [1,2,3,4,5] e' 3.0; lista vuota restituisce None."""
    assert sample_mean([1.0, 2.0, 3.0, 4.0, 5.0]) == 3.0
    assert sample_mean([]) is None
    assert sample_mean([None]) is None


def test_mean_ci_t_contiene_media_su_sintetico():
    """Su [1..10] la CI t al 95% contiene la media campionaria 5.5 (calcolabile a mano)."""
    campione = [float(i) for i in range(1, 11)]
    ris = mean_ci_t(campione, confidence=0.95)
    assert ris.valid is True
    assert ris.value is not None
    assert abs(ris.value - 5.5) < 1e-9
    assert ris.ci_lower is not None and ris.ci_upper is not None
    assert ris.ci_lower <= 5.5 <= ris.ci_upper


def test_mean_ci_t_n_tre_invalido_per_protocollo_energetico():
    """P4.12: con n = 3 non si stima una varianza, quindi la CI t e' invalida."""
    ris = mean_ci_t([10.0, 12.0, 11.0], confidence=0.95)
    assert ris.valid is False
    assert ris.value is None
    assert ris.ci_lower is None and ris.ci_upper is None
    assert "n = 3" in ris.reason and "P4.12" in ris.reason


def test_sample_std_n_tre_valido_ma_ci_invalida():
    """La std campionaria su 3 valori e' calcolabile (ddof=1), ma la CI t su n=3 no."""
    std = sample_std([10.0, 12.0, 11.0])
    assert std is not None
    assert abs(std - 1.0) < 1e-9  # varianza = (1+0+1)/2 = 1
    ci = mean_ci_t([10.0, 12.0, 11.0], confidence=0.95)
    assert ci.valid is False


def test_bootstrap_seme_fisso_deterministico():
    """Stesso seme e stesso campione producono lo stesso intervallo a ogni run."""
    campione = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    r1 = bootstrap_percentile_ci(campione, seed=BOOTSTRAP_SEED, n_resamples=BOOTSTRAP_RESAMPLES)
    r2 = bootstrap_percentile_ci(campione, seed=BOOTSTRAP_SEED, n_resamples=BOOTSTRAP_RESAMPLES)
    assert r1.valid is True
    assert r1.value is not None and abs(r1.value - 5.5) < 1e-9
    assert r1.ci_lower == r2.ci_lower and r1.ci_upper == r2.ci_upper


def test_bootstrap_seme_diverso_intervallo_diverso():
    """Semi diversi producono intervalli (praticamente sempre) diversi su campione ampio."""
    import random

    random.seed(7)
    campione = [random.gauss(50.0, 5.0) for _ in range(50)]
    r1 = bootstrap_percentile_ci(campione, seed=111, n_resamples=2000)
    r2 = bootstrap_percentile_ci(campione, seed=222, n_resamples=2000)
    assert r1.valid is True and r2.valid is True
    assert r1.ci_lower != r2.ci_lower or r1.ci_upper != r2.ci_upper


def test_bootstrap_n_minore_di_2_invalido():
    """Bootstrap richiede almeno 2 valori finiti."""
    assert bootstrap_percentile_ci([]).valid is False
    assert bootstrap_percentile_ci([3.0]).valid is False


def test_wilson_ci_proporzione_intorno_a_osservato():
    """Wilson su 7 successi su 10 centra l'intervallo attorno a 0.7."""
    ris = wilson_ci_proportion(7, 10, confidence=0.95)
    assert ris.valid is True
    assert ris.value is not None and abs(ris.value - 0.7) < 1e-12
    assert ris.ci_lower is not None and ris.ci_upper is not None
    assert 0.0 <= ris.ci_lower <= 0.7 <= ris.ci_upper <= 1.0


def test_wilson_ci_proporzione_tutti_successi():
    """10/10 dà proporzione 1.0 con intervallo che tocca 1.0 in alto."""
    ris = wilson_ci_proportion(10, 10, confidence=0.95)
    assert ris.valid is True
    assert abs(ris.value - 1.0) < 1e-12
    assert ris.ci_upper is not None and abs(ris.ci_upper - 1.0) < 1e-9


def test_wilson_ci_trials_zero_invalido():
    """trials < 1 e' invalido."""
    ris = wilson_ci_proportion(0, 0, confidence=0.95)
    assert ris.valid is False


def test_wilson_ci_successes_fuori_range_invalido():
    """successes > trials e' invalido."""
    ris = wilson_ci_proportion(11, 10, confidence=0.95)
    assert ris.valid is False


def test_nessuna_colonna_csv_nuova():
    """Importare statistical_uncertainty non allarga CSV_COLUMNS (schema P5 congelato)."""
    from casualwatt_csv_export import CSV_COLUMNS  # noqa: E402

    n_before = len(CSV_COLUMNS)
    importlib.import_module("energy.statistical_uncertainty")
    n_after = len(CSV_COLUMNS)
    assert n_before == n_after


def test_modulo_importa_solo_stdlib():
    """statistical_uncertainty importa solo moduli della libreria standard."""
    percorso = Path(__file__).resolve().parents[1] / "energy" / "statistical_uncertainty.py"
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    moduli_importati = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                moduli_importati.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                moduli_importati.add(nodo.module.split(".")[0])
    stdlib_atteso = {
        "math", "random", "statistics", "typing", "dataclasses",
        "__future__", "evaluation_runner",  # modulo dello stesso pacchetto, non una dipendenza esterna
    }
    # __future__ e typing sono stdlib; nessun import esterno (numpy, scipy, ecc.).
    esterni = moduli_importati - stdlib_atteso
    assert not esterni, f"Import non stdlib trovati: {esterni}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
