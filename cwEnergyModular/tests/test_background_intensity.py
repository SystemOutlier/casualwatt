# -*- coding: utf-8 -*-
"""test_background_intensity.py — test BG-01÷BG-08, WU-01÷WU-06.

Verifica che il controllo del background distingua identità dei processi
dalla stabilità dell'intensità CPU e potenza, e che il warm-up post-carico
usi la CPU anche in modalità background_controlled.
"""
import pytest
from unittest.mock import MagicMock, patch

from machine_state import (
    background_signature,
    signatures_match,
    signatures_match_with_intensity,
)


# ─── BG-01 ÷ BG-08: identità e intensità ───


class TestBackgroundIdentityAndIntensity:
    """BG-01÷BG-08: signatures_match_with_intensity distingue i 4 casi."""

    def _firma(self, cpu_mean=None, power_mean=None, processes=None,
               power_plan="Bilanciato", battery="absent"):
        """Costruisce una firma di test con i campi richiesti."""
        if processes is None:
            processes = [
                {"pid": 100, "name": "ollama", "cpu_pct": 1.0},
                {"pid": 200, "name": "chrome", "cpu_pct": 0.5},
            ]
        return background_signature(
            char_sha256="abc123",
            cpu_samples=[cpu_mean] if cpu_mean is not None else None,
        ) | {
            "processes": processes,
            "power_plan": power_plan,
            "battery": battery,
            "cpu_total_mean_pct": cpu_mean,
            "cpu_total_max_pct": cpu_mean,
            "power_mean_w": power_mean,
        }

    def test_bg01_stessi_processi_cpu_stabile(self):
        """BG-01: stessi processi e CPU stabile → stabilità riconosciuta."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=2.5, power_mean=101.0)
        verdetto, diff = signatures_match_with_intensity(sig1, sig2)
        assert verdetto == "stable", f"Atteso 'stable', ottenuto '{verdetto}': {diff}"

    def test_bg02_stessi_processi_cpu_variabile(self):
        """BG-02: stessi processi, CPU da 5% a 40% → background instabile."""
        sig1 = self._firma(cpu_mean=5.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=40.0, power_mean=100.0)
        verdetto, diff = signatures_match_with_intensity(sig1, sig2)
        assert verdetto == "intensity_unstable", (
            f"Atteso 'intensity_unstable', ottenuto '{verdetto}': {diff}"
        )

    def test_bg03_stessi_processi_potenza_variabile(self):
        """BG-03: stessi processi, potenza molto variabile → instabile."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=2.0, power_mean=150.0)
        verdetto, diff = signatures_match_with_intensity(
            sig1, sig2, power_tolerance_w=10.0
        )
        assert verdetto == "intensity_unstable", (
            f"Atteso 'intensity_unstable', ottenuto '{verdetto}': {diff}"
        )

    def test_bg04_processo_terminato(self):
        """BG-04: un processo viene terminato → identità cambiata."""
        sig1 = self._firma(
            cpu_mean=2.0,
            processes=[
                {"pid": 100, "name": "ollama", "cpu_pct": 1.0},
                {"pid": 200, "name": "chrome", "cpu_pct": 0.5},
            ],
        )
        sig2 = self._firma(
            cpu_mean=2.0,
            processes=[
                {"pid": 100, "name": "ollama", "cpu_pct": 1.0},
            ],
        )
        verdetto, diff = signatures_match_with_intensity(sig1, sig2)
        assert verdetto == "identity_changed", (
            f"Atteso 'identity_changed', ottenuto '{verdetto}': {diff}"
        )

    def test_bg05_nuovo_processo_entrato(self):
        """BG-05: un nuovo processo entra nel gruppo rilevante → identità cambiata."""
        sig1 = self._firma(
            cpu_mean=2.0,
            processes=[
                {"pid": 100, "name": "ollama", "cpu_pct": 1.0},
            ],
        )
        sig2 = self._firma(
            cpu_mean=2.0,
            processes=[
                {"pid": 100, "name": "ollama", "cpu_pct": 1.0},
                {"pid": 300, "name": "render", "cpu_pct": 15.0},
            ],
        )
        verdetto, diff = signatures_match_with_intensity(sig1, sig2)
        assert verdetto == "identity_changed", (
            f"Atteso 'identity_changed', ottenuto '{verdetto}': {diff}"
        )

    def test_bg06_campione_cpu_mancante(self):
        """BG-06: campione CPU mancante → stabilità non dichiarata."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=None, power_mean=100.0)
        verdetto, diff = signatures_match_with_intensity(sig1, sig2)
        assert verdetto == "insufficient_data", (
            f"Atteso 'insufficient_data', ottenuto '{verdetto}': {diff}"
        )

    def test_bg07_campione_potenza_mancante(self):
        """BG-07: campione potenza mancante → stabilità non dichiarata."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=2.0, power_mean=None)
        verdetto, diff = signatures_match_with_intensity(
            sig1, sig2, power_tolerance_w=10.0
        )
        assert verdetto == "insufficient_data", (
            f"Atteso 'insufficient_data', ottenuto '{verdetto}': {diff}"
        )

    def test_bg08_oscillazione_entro_limiti(self):
        """BG-08: oscillazione entro i limiti preregistrati → stabilità riconosciuta."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=3.5, power_mean=102.0)
        # Tolleranza CPU 5%, tolleranza potenza 5 W
        verdetto, diff = signatures_match_with_intensity(
            sig1, sig2, cpu_tolerance_pct=5.0, power_tolerance_w=5.0
        )
        assert verdetto == "stable", (
            f"Atteso 'stable', ottenuto '{verdetto}': {diff}"
        )

    def test_bg09_tolleranza_cpu_parametrizzabile(self):
        """La tolleranza CPU è parametrizzabile, non hardcoded."""
        sig1 = self._firma(cpu_mean=2.0, power_mean=100.0)
        sig2 = self._firma(cpu_mean=6.0, power_mean=100.0)
        # Differenza 4.0%: con tolleranza 3% → instabile
        verdetto_stritto, _ = signatures_match_with_intensity(
            sig1, sig2, cpu_tolerance_pct=3.0
        )
        assert verdetto_stritto == "intensity_unstable"
        # Con tolleranza 5% → stabile (4.0% ≤ 5%)
        verdetto_largo, _ = signatures_match_with_intensity(
            sig1, sig2, cpu_tolerance_pct=5.0
        )
        assert verdetto_largo == "stable"

    def test_bg10_signatures_match_retrocompatibile(self):
        """signatures_match() resta funzionante senza campi intensità."""
        sig1 = self._firma(cpu_mean=2.0)
        sig2 = self._firma(cpu_mean=40.0)
        # signatures_match non guarda l'intensità: restituisce True
        match, diff = signatures_match(sig1, sig2)
        assert match is True, (
            "signatures_match() non deve guardare l'intensità"
        )


# ─── WU-01 ÷ WU-06: warm-up post-carico ───


class TestWarmUpBackgroundControlled:
    """WU-01÷WU-06: _stabilizza_post_carico con CPU attiva in background_controlled.

    I test usano sys.modules per evitare l'import di gate_uncertainty
    che non e' installato su tutte le macchine.
    """

    def _import_gate(self):
        """Importa _stabilizza_post_carico con mock di gate_uncertainty."""
        import sys
        from types import ModuleType
        sys.modules["gate_uncertainty"] = ModuleType("gate_uncertainty")
        from tools.run_gate_p44 import _stabilizza_post_carico
        return _stabilizza_post_carico

    def test_wu01_potenza_stabile_cpu_stabile(self):
        """WU-01: potenza stabile e CPU stabile → warm-up completato."""
        _stabilizza_post_carico = self._import_gate()

        def leggi_potenza():
            return 100.0  # stabile, entro tolerance da target

        def leggi_cpu():
            return [2.0]  # stabile, sotto soglia

        esito = _stabilizza_post_carico(
            target_pre_w=100.0,
            tolerance_w=5.0,
            cpu_max_pct=5.0,
            sustain_s=2.0,
            cap_s=60.0,
            step_s=0.1,
            window_s=0.1,
            campiona_potenza=leggi_potenza,
            campiona_cpu=leggi_cpu,
            legge_temperatura=lambda: (None, "test"),
            registra=None,
            mode="absolute",
        )
        assert esito["warmup_completed"] is True
        assert esito["warmup_motivo"] == "criterio_soddisfatto"

    def test_wu02_potenza_stabile_cpu_instabile(self):
        """WU-02: potenza stabile, CPU instabile → warm-up non completato in absolute."""
        _stabilizza_post_carico = self._import_gate()

        def leggi_potenza():
            return 100.0

        def leggi_cpu():
            return [40.0]  # sopra cpu_max_pct

        with pytest.raises(SystemExit, match="tetto"):
            _stabilizza_post_carico(
                target_pre_w=100.0,
                tolerance_w=5.0,
                cpu_max_pct=5.0,
                sustain_s=2.0,
                cap_s=0.5,
                step_s=0.1,
                window_s=0.1,
                campiona_potenza=leggi_potenza,
                campiona_cpu=leggi_cpu,
                legge_temperatura=lambda: (None, "test"),
                registra=None,
                mode="absolute",
            )

    def test_wu03_cpu_stabile_potenza_instabile(self):
        """WU-03: CPU stabile, potenza instabile → warm-up non completato."""
        _stabilizza_post_carico = self._import_gate()

        def leggi_potenza():
            return 150.0  # fuori da tolerance

        def leggi_cpu():
            return [2.0]

        with pytest.raises(SystemExit, match="tetto"):
            _stabilizza_post_carico(
                target_pre_w=100.0,
                tolerance_w=5.0,
                cpu_max_pct=5.0,
                sustain_s=2.0,
                cap_s=0.5,
                step_s=0.1,
                window_s=0.1,
                campiona_potenza=leggi_potenza,
                campiona_cpu=leggi_cpu,
                legge_temperatura=lambda: (None, "test"),
                registra=None,
                mode="absolute",
            )

    def test_wu04_segnale_mancante(self):
        """WU-04: segnale mancante → warm-up non completato."""
        _stabilizza_post_carico = self._import_gate()

        def leggi_potenza():
            return None  # lettura assente

        def leggi_cpu():
            return [2.0]

        with pytest.raises(SystemExit, match="tetto"):
            _stabilizza_post_carico(
                target_pre_w=100.0,
                tolerance_w=5.0,
                cpu_max_pct=5.0,
                sustain_s=2.0,
                cap_s=0.5,
                step_s=0.1,
                window_s=0.1,
                campiona_potenza=leggi_potenza,
                campiona_cpu=leggi_cpu,
                legge_temperatura=lambda: (None, "test"),
                registra=None,
                mode="absolute",
            )

    def test_wu05_stabilita_dopo_piu_finestre(self):
        """WU-05: stabilità raggiunta dopo più finestre → completato."""
        _stabilizza_post_carico = self._import_gate()

        call_count = 0
        def leggi_potenza():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return 150.0  # fuori banda per i primi 2 campioni
            return 100.0  # poi stabile

        def leggi_cpu():
            return [2.0]

        esito = _stabilizza_post_carico(
            target_pre_w=100.0,
            tolerance_w=5.0,
            cpu_max_pct=5.0,
            sustain_s=2.0,
            cap_s=60.0,
            step_s=0.1,
            window_s=0.1,
            campiona_potenza=leggi_potenza,
            campiona_cpu=leggi_cpu,
            legge_temperatura=lambda: (None, "test"),
            registra=None,
            mode="absolute",
        )
        assert esito["warmup_completed"] is True

    def test_wu06_stabilita_non_raggiunta_entro_timeout(self):
        """WU-06: stabilità non raggiunta entro il timeout → arresto."""
        _stabilizza_post_carico = self._import_gate()

        def leggi_potenza():
            return 150.0  # sempre fuori banda

        def leggi_cpu():
            return [2.0]

        with pytest.raises(SystemExit, match="tetto"):
            _stabilizza_post_carico(
                target_pre_w=100.0,
                tolerance_w=5.0,
                cpu_max_pct=5.0,
                sustain_s=2.0,
                cap_s=0.5,
                step_s=0.1,
                window_s=0.1,
                campiona_potenza=leggi_potenza,
                campiona_cpu=leggi_cpu,
                legge_temperatura=lambda: (None, "test"),
                registra=None,
                mode="absolute",
            )
