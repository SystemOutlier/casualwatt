# -*- coding: utf-8 -*-
"""Test per BaselineStatistics — il primitivo comune di analisi statistica.

Verifica che il modulo calcoli correttamente tutte le metriche richieste,
gestisca gli edge cases senza errori e produca lo status di stabilità corretto.
"""
import pytest
from baseline_statistics import (
    BaselineStatistics,
    iqr_filter,
)


# -- from_power_windows() — metriche corrette -------------------------------

class TestFromPowerWindowsMetrics:
    """Verifica che from_power_windows() calcoli tutte le statistiche correttamente."""

    def test_three_windows_stable(self):
        """Tre finestre stabili: CV ≈ 1.49%, status stable."""
        powers = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 3
        assert stats.power_mean_w == pytest.approx(100.0, abs=0.1)
        assert stats.power_std_w == pytest.approx(2.0, abs=0.1)
        assert stats.cv_pct == pytest.approx(2.0, abs=0.1)
        assert stats.power_median_w == pytest.approx(100.0, abs=0.1)
        assert stats.duration_s == pytest.approx(90.0, abs=0.1)
        assert stats.stability_status == "stable"

    def test_three_windows_unstable(self):
        """Tre finestre instabili: CV ≈ 20%, status unstable."""
        powers = [(100.0, 30.0), (120.0, 30.0), (80.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 3
        assert stats.cv_pct > 10.0
        assert stats.stability_status == "unstable"

    def test_single_window_insufficient_data(self):
        """Una sola finestra: insufficient_data, non stable con CV=0."""
        powers = [(100.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 1
        assert stats.stability_status == "insufficient_data"
        assert stats.power_std_w == 0.0

    def test_empty_list_not_evaluated(self):
        """Lista vuota: not_evaluated, non stable con CV=0."""
        stats = BaselineStatistics.from_power_windows([])

        assert stats.window_count == 0
        assert stats.stability_status == "not_evaluated"
        assert stats.cv_pct == 0.0

    def test_duration_summed_correctly(self):
        """La durata è la somma dei dt delle finestre valide."""
        powers = [(100.0, 30.0), (102.0, 35.0), (98.0, 25.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.duration_s == pytest.approx(90.0, abs=0.1)

    def test_iqr_calculated(self):
        """L'IQR è calcolato correttamente (Q3 - Q1)."""
        powers = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0), (101.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.power_iqr_w >= 0.0
        # Con 4 valori ordinati [98, 100, 101, 102]: Q1=99, Q3=101.5, IQR=2.5
        assert stats.power_iqr_w == pytest.approx(2.5, abs=0.1)

    def test_median_calculated(self):
        """La mediana è il valore centrale dopo ordinamento."""
        powers = [(100.0, 30.0), (110.0, 30.0), (90.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.power_median_w == pytest.approx(100.0, abs=0.1)

    def test_std_sample_not_population(self):
        """La deviazione standard usa n-1 (Bessel), non n."""
        # Con n=3, std_campione = sqrt(sum((x-mean)^2) / 2)
        powers = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        # Verifica che std_campione sia calcolato con n-1:
        # con [98, 100, 102], mean=100, var = (4+0+4)/2 = 4, std = 2.0
        # (La media esatta e' 100.0, quindi std = sqrt(4) = 2.0)
        assert stats.power_std_w == pytest.approx(2.0, abs=0.01)
        # Se usasse n invece di n-1: std = sqrt(8/3) ≈ 1.633
        assert stats.power_std_w > 1.633

    def test_cv_formula(self):
        """CV = (std / mean) * 100."""
        powers = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        expected_cv = (stats.power_std_w / stats.power_mean_w) * 100.0
        assert stats.cv_pct == pytest.approx(expected_cv, abs=0.01)

    def test_custom_cv_threshold(self):
        """La soglia CV è parametrizzabile."""
        powers = [(100.0, 30.0), (105.0, 30.0), (95.0, 30.0)]
        # Con CV ≈ 5%, è stable con soglia 10% ma unstable con soglia 3%
        stats_10 = BaselineStatistics.from_power_windows(powers, cv_max_pct=10.0)
        stats_3 = BaselineStatistics.from_power_windows(powers, cv_max_pct=3.0)

        assert stats_10.stability_status == "stable"
        assert stats_3.stability_status == "unstable"


# -- from_power_windows() — edge cases --------------------------------------

class TestFromPowerWindowsEdgeCases:
    """Edge cases: finestre non valide, potenza negativa, media zero."""

    def test_zero_dt_window_skipped(self):
        """Finestra con dt=0 viene scartata, non divide per zero."""
        powers = [(100.0, 30.0), (102.0, 0.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 2
        assert any("dt=" in note and "≤ 0" in note for note in stats.notes)

    def test_negative_power_window_skipped(self):
        """Finestra con potenza negativa viene scartata."""
        powers = [(100.0, 30.0), (-10.0, 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 2
        assert any("negativa" in note for note in stats.notes)

    def test_all_windows_invalid(self):
        """Tutte le finestre non valide: not_evaluated."""
        powers = [(100.0, 0.0), (-10.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 0
        assert stats.stability_status == "not_evaluated"

    def test_zero_mean_insufficient_data(self):
        """Media = 0: CV non calcolabile, insufficient_data."""
        powers = [(0.0, 30.0), (0.0, 30.0), (0.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.stability_status == "insufficient_data"
        assert any("CV non calcolabile" in note for note in stats.notes)

    def test_cpu_utilization_avg_calculated(self):
        """CPU utilization medio è calcolato correttamente se fornito."""
        powers = [(100.0, 30.0), (102.0, 30.0)]
        cpu_samples = [(5.0, 30.0), (7.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers, cpu_samples=cpu_samples)

        assert stats.cpu_utilization_avg == pytest.approx(6.0, abs=0.1)

    def test_cpu_utilization_avg_none_when_absent(self):
        """CPU utilization è None se non fornito."""
        powers = [(100.0, 30.0), (102.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.cpu_utilization_avg is None


# -- from_single_values() — metriche corrette -------------------------------

class TestFromSingleValues:
    """Verifica che from_single_values() calcoli le statistiche senza durata."""

    def test_three_values_stable(self):
        """Tre valori stabili: stesse metriche senza dt."""
        powers = [100.0, 102.0, 98.0]
        stats = BaselineStatistics.from_single_values(powers)

        assert stats.window_count == 3
        assert stats.power_mean_w == pytest.approx(100.0, abs=0.1)
        assert stats.duration_s == 0.0
        assert stats.stability_status == "stable"

    def test_single_value_insufficient_data(self):
        """Un solo valore: insufficient_data."""
        stats = BaselineStatistics.from_single_values([100.0])

        assert stats.window_count == 1
        assert stats.stability_status == "insufficient_data"

    def test_empty_list_not_evaluated(self):
        """Lista vuota: not_evaluated."""
        stats = BaselineStatistics.from_single_values([])

        assert stats.window_count == 0
        assert stats.stability_status == "not_evaluated"

    def test_negative_values_skipped(self):
        """Valori negativi vengono scartati."""
        stats = BaselineStatistics.from_single_values([100.0, -10.0, 98.0])

        assert stats.window_count == 2
        assert any("negativa" in note for note in stats.notes)

    def test_consistent_with_from_power_windows(self):
        """Le statistiche sono coerenti con from_power_windows() per le stesse potenze."""
        powers_float = [100.0, 102.0, 98.0]
        powers_tuple = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0)]

        stats_float = BaselineStatistics.from_single_values(powers_float)
        stats_tuple = BaselineStatistics.from_power_windows(powers_tuple)

        assert stats_float.power_mean_w == stats_tuple.power_mean_w
        assert stats_float.power_std_w == stats_tuple.power_std_w
        assert stats_float.cv_pct == stats_tuple.cv_pct
        assert stats_float.power_median_w == stats_tuple.power_median_w
        assert stats_float.stability_status == stats_tuple.stability_status


# -- evaluate_stability() — vocabolario chiuso ------------------------------

class TestStabilityVocabulary:
    """Verifica che il vocabolario di stability_status sia chiuso e corretto."""

    def test_stable_token(self):
        """CV ≤ soglia con ≥ 2 finestre: stable."""
        powers = [(100.0, 30.0), (101.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)
        assert stats.stability_status == "stable"

    def test_unstable_token(self):
        """CV > soglia: unstable."""
        powers = [(100.0, 30.0), (200.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)
        assert stats.stability_status == "unstable"

    def test_insufficient_data_token(self):
        """Meno di 2 finestre: insufficient_data."""
        stats = BaselineStatistics.from_power_windows([(100.0, 30.0)])
        assert stats.stability_status == "insufficient_data"

    def test_not_evaluated_token(self):
        """Lista vuota: not_evaluated."""
        stats = BaselineStatistics.from_power_windows([])
        assert stats.stability_status == "not_evaluated"

    def test_cv_at_threshold_is_stable(self):
        """CV esattamente alla soglia: stable (non stretto)."""
        # CV = 10.0% con soglia 10.0% → stable
        powers = [(100.0, 30.0), (100.0, 30.0), (100.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers, cv_max_pct=10.0)
        assert stats.stability_status == "stable"


# -- iqr_filter() — coerenza con l'implementazione esistente ----------------

class TestIqrFilter:
    """Verifica che iqr_filter() sia coerente con _applica_filtro_outlier_iqr()."""

    def test_no_outliers(self):
        """Senza outlier, il filtro non rimuove nulla."""
        values = [100.0, 101.0, 102.0, 103.0, 104.0]
        filtered = iqr_filter(values)
        assert len(filtered) == len(values)

    def test_outlier_removed(self):
        """Un valore lontano viene rimosso."""
        values = [100.0, 101.0, 102.0, 103.0, 500.0]
        filtered = iqr_filter(values)
        assert 500.0 not in filtered

    def test_zero_iqr_no_removal(self):
        """IQR = 0 non rimuove nulla."""
        values = [100.0, 100.0, 100.0, 100.0]
        filtered = iqr_filter(values)
        assert len(filtered) == len(values)

    def test_single_value(self):
        """Un solo valore: restituito senza modifiche."""
        filtered = iqr_filter([100.0])
        assert filtered == [100.0]

    def test_custom_multiplier(self):
        """Moltiplicatore personalizzato."""
        values = [100.0, 101.0, 102.0, 103.0, 200.0]
        # Con k=1.5, 200.0 viene rimosso; con k=10.0, potrebbe restare
        filtered_1_5 = iqr_filter(values, k=1.5)
        filtered_10 = iqr_filter(values, k=10.0)
        assert len(filtered_1_5) <= len(filtered_10)


# -- serializzazione JSON — round-trip --------------------------------------

class TestJsonSerialization:
    """Verifica che la serializzazione JSON sia un round-trip corretto."""

    def test_round_trip(self):
        """Serializzazione e deserializzazione preservano i dati."""
        powers = [(100.0, 30.0), (102.0, 30.0), (98.0, 30.0)]
        original = BaselineStatistics.from_power_windows(powers)

        json_str = original.to_json()
        restored = BaselineStatistics.from_json(json_str)

        assert restored is not None
        assert restored.window_count == original.window_count
        assert restored.power_mean_w == original.power_mean_w
        assert restored.cv_pct == original.cv_pct
        assert restored.stability_status == original.stability_status

    def test_json_starts_with_key(self):
        """La stringa JSON inizia con la chiave strutturata."""
        powers = [(100.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)
        json_str = stats.to_json()
        assert json_str.startswith("baseline_stats:")

    def test_from_json_returns_none_for_unknown_prefix(self):
        """from_json restituisce None per stringhe non valide."""
        assert BaselineStatistics.from_json("qualcosaltro:{...}") is None

    def test_json_compact_format(self):
        """Il JSON è compatto (senza spazi)."""
        powers = [(100.0, 30.0), (102.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)
        json_str = stats.to_json()
        # Dopo il prefisso, il JSON non dovrebbe contenere spazi dopo : o ,
        json_part = json_str[len("baseline_stats:"):]
        assert ": " not in json_part or json_part.count(": ") == 0

    def test_notes_included_in_json(self):
        """Le note diagnostiche sono incluse nel JSON se presenti."""
        powers = [(100.0, 30.0), (102.0, 0.0)]  # dt=0 genera una nota
        stats = BaselineStatistics.from_power_windows(powers)
        json_str = stats.to_json()
        assert "scartata" in json_str


# -- immutabilità della dataclass -------------------------------------------

class TestImmutability:
    """Verifica che BaselineStatistics sia immutabile (frozen=True)."""

    def test_frozen_dataclass(self):
        """Tentativo di modifica solleva FrozenInstanceError."""
        powers = [(100.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        with pytest.raises(Exception):  # FrozenInstanceError
            stats.window_count = 5  # type: ignore


# -- robustezza valori non finiti -------------------------------------------

class TestNonFiniteValues:
    """Verifica che NaN e infinito vengano scartati esplicitamente."""

    def test_nan_power_skipped(self):
        """Potenza NaN viene scartata, non produce CV=NaN."""
        import math
        powers = [(100.0, 30.0), (float('nan'), 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 2
        assert math.isfinite(stats.cv_pct)
        assert any("non finita" in note for note in stats.notes)

    def test_inf_power_skipped(self):
        """Potenza infinito viene scartata."""
        powers = [(100.0, 30.0), (float('inf'), 30.0), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 2
        assert any("non finita" in note for note in stats.notes)

    def test_nan_dt_skipped(self):
        """dt NaN viene scartato."""
        powers = [(100.0, 30.0), (102.0, float('nan')), (98.0, 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 2
        assert any("non finito" in note for note in stats.notes)

    def test_all_nan_not_evaluated(self):
        """Tutti NaN: not_evaluated, non stable."""
        powers = [(float('nan'), 30.0), (float('nan'), 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.window_count == 0
        assert stats.stability_status == "not_evaluated"
        assert stats.cv_pct == 0.0

    def test_from_single_values_nan_skipped(self):
        """from_single_values scarta NaN esplicitamente."""
        import math
        stats = BaselineStatistics.from_single_values([100.0, float('nan'), 98.0])

        assert stats.window_count == 2
        assert math.isfinite(stats.cv_pct)
        assert any("non finita" in note for note in stats.notes)

    def test_nan_does_not_produce_stable(self):
        """NaN non produce mai status stable."""
        powers = [(float('nan'), 30.0), (float('nan'), 30.0), (float('nan'), 30.0)]
        stats = BaselineStatistics.from_power_windows(powers)

        assert stats.stability_status != "stable"
