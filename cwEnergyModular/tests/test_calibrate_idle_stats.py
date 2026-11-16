# -*- coding: utf-8 -*-
"""Test di regressione: calibrate_idle() popola baseline_stats senza modificare idle_power_w.

Verifica che l'estensione di EnergySession con BaselineStatistics non cambi
il comportamento di calibrate_idle() riguardo a idle_power_w, e che le nuove
metriche siano popolate correttamente.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestCalibrateIdleStats:
    """Verifica che calibrate_idle() produca baseline_stats senza modificare idle_power_w."""

    def _make_session_with_mocked_source(self):
        """Crea una EnergySession con il source mockato per evitare EMI/RAPL reali."""
        from energy.energy_session import EnergySession

        session = EnergySession()

        # Mock del source per simulare un contatore funzionante
        mock_source = MagicMock()
        mock_source.method = "emi-counter"
        mock_source.last_read_error = None

        # 3 finestre idle: (delta_j, dt, mode)
        # Potenze: 100W, 102W, 98W → mediana = 100W
        mock_source.read_idle_window_j.side_effect = [
            (3000.0, 30.0, "emi-counter"),  # 100W
            (3060.0, 30.0, "emi-counter"),  # 102W
            (2940.0, 30.0, "emi-counter"),  # 98W
        ]

        session._source = mock_source
        return session

    def test_idle_power_w_unchanged(self):
        """idle_power_w resta la mediana delle 3 potenze, invariato."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            idle_power = session.calibrate_idle(seconds=30.0)

        # La mediana di [98, 100, 102] e' 100.0
        assert idle_power == pytest.approx(100.0, abs=0.1)
        assert session.idle_power_w == pytest.approx(100.0, abs=0.1)

    def test_baseline_stats_populated(self):
        """baseline_stats e' popolata dopo calibrate_idle()."""
        from energy.energy_session import BaselineStatistics as BS
        assert BS is not None, "BaselineStatistics non importato in energy_session"

        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        assert session.baseline_stats.window_count == 3

    def test_baseline_stats_mean_matches(self):
        """La media di baseline_stats corrisponde alla media delle 3 potenze."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        # Media di [98, 100, 102] = 100.0
        assert session.baseline_stats.power_mean_w == pytest.approx(100.0, abs=0.1)

    def test_baseline_stats_median_matches_idle_power_w(self):
        """La mediana di baseline_stats corrisponde a idle_power_w."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        assert session.baseline_stats.power_median_w == pytest.approx(
            session.idle_power_w, abs=0.1
        )

    def test_baseline_stats_duration(self):
        """La durata di baseline_stats e' la somma dei 3 dt."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        # 3 finestre da 30s = 90s
        assert session.baseline_stats.duration_s == pytest.approx(90.0, abs=0.1)

    def test_baseline_stats_stability_status(self):
        """Lo status di stabilita' e' valutato correttamente."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        # Con potenze [98, 100, 102], CV e' basso → stable
        assert session.baseline_stats.stability_status == "stable"

    def test_baseline_stats_cv_low(self):
        """Il CV e' basso per potenze simili."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        assert session.baseline_stats.cv_pct < 10.0

    def test_baseline_stats_none_before_calibration(self):
        """baseline_stats e' None prima della calibrazione."""
        session = self._make_session_with_mocked_source()
        assert session.baseline_stats is None

    def test_idle_provenance_unchanged(self):
        """idle_provenance resta 'calibrated' come prima."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.idle_provenance == "calibrated"

    def test_calibrated_at_set(self):
        """calibrated_at e' impostato dopo la calibrazione."""
        session = self._make_session_with_mocked_source()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.calibrated_at is not None


class TestCalibrateIdleUnstable:
    """Verifica che baseline_stats rilevi correttamente l'instabilità."""

    def _make_unstable_session(self):
        """Crea una sessione con potenze instabili."""
        from energy.energy_session import EnergySession

        session = EnergySession()
        mock_source = MagicMock()
        mock_source.method = "emi-counter"
        mock_source.last_read_error = None

        # Potenze instabili: 100W, 150W, 80W → CV alto
        mock_source.read_idle_window_j.side_effect = [
            (3000.0, 30.0, "emi-counter"),  # 100W
            (4500.0, 30.0, "emi-counter"),  # 150W
            (2400.0, 30.0, "emi-counter"),  # 80W
        ]

        session._source = mock_source
        return session

    def test_unstable_baseline_detected(self):
        """Una baseline instabile ha status 'unstable'."""
        session = self._make_unstable_session()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            session.calibrate_idle(seconds=30.0)

        assert session.baseline_stats is not None
        assert session.baseline_stats.stability_status == "unstable"

    def test_idle_power_w_still_median_when_unstable(self):
        """Anche con baseline instabile, idle_power_w resta la mediana."""
        session = self._make_unstable_session()

        with patch.object(session, 'start'), patch.object(session, 'stop'):
            idle_power = session.calibrate_idle(seconds=30.0)

        # Mediana di [80, 100, 150] = 100.0
        assert idle_power == pytest.approx(100.0, abs=0.1)
