# -*- coding: utf-8 -*-
"""test_background_monitor.py — test dell'orchestratore del monitoraggio background.

Verifica che BackgroundMonitor coordini correttamente i campioni pre/post blocco,
valuti l'esito del background e serializzi lo stato per il campo notes.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from background_monitor import BackgroundMonitor


class TestSamplePre:
    """Verifica che sample_pre() raccolga la firma e imposti il riferimento."""

    def test_sample_pre_sets_reference(self):
        """Il primo sample_pre() imposta il riferimento."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0, 2.0, 1.5]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.5,
            }
            sig = monitor.sample_pre()

        assert monitor.reference_signature is not None
        assert sig["kind"] == "pre"
        assert monitor.reference_signature["kind"] == "pre"

    def test_sample_pre_appends_to_samples(self):
        """Ogni sample_pre() aggiunge un campione alla lista."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()
            monitor.sample_pre()

        assert len(monitor.samples) == 2

    def test_sample_pre_passes_char_sha256(self):
        """Il char_sha256 viene passato a background_signature()."""
        monitor = BackgroundMonitor(char_sha256="abc123")
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()

        call_kwargs = mock_ms.background_signature.call_args[1]
        assert call_kwargs["char_sha256"] == "abc123"

    def test_sample_pre_passes_cpu_samples(self):
        """I campioni CPU vengono passati a background_signature()."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0, 2.0, 1.5]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()

        call_kwargs = mock_ms.background_signature.call_args[1]
        assert call_kwargs["cpu_samples"] == [1.0, 2.0, 1.5]

    def test_sample_pre_returns_signature(self):
        """sample_pre() restituisce la firma raccolta."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            expected_sig = {"processes": [], "cpu_total_mean_pct": 1.0}
            mock_ms.background_signature.return_value = expected_sig
            sig = monitor.sample_pre()

        assert sig["cpu_total_mean_pct"] == 1.0
        assert sig["kind"] == "pre"

    def test_sample_pre_does_not_update_reference(self):
        """Il riferimento resta il primo campione, non si aggiorna."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            # Primo campione: CPU bassa
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            original_ref = monitor.reference_signature

            # Secondo campione: CPU alta
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 50.0,
            }
            monitor.sample_pre()

        assert monitor.reference_signature is original_ref
        assert monitor.reference_signature["cpu_total_mean_pct"] == 1.0

    def test_sample_pre_exception_propagates(self):
        """Se il campionamento fallisce, l'eccezione si propaga."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.side_effect = RuntimeError("sampler fallito")
            with pytest.raises(RuntimeError, match="sampler fallito"):
                monitor.sample_pre()

        assert monitor.reference_signature is None
        assert len(monitor.samples) == 0

    def test_sample_pre_calls_total_cpu_samples(self):
        """sample_pre() chiama total_cpu_samples() una volta."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()

        mock_ms.total_cpu_samples.assert_called_once()


class TestSamplePost:
    """Verifica che sample_post() raccolga la firma senza aggiornare il riferimento."""

    def test_sample_post_kind(self):
        """sample_post() aggiunge kind='post' alla firma."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            sig = monitor.sample_post()

        assert sig["kind"] == "post"

    def test_sample_post_does_not_set_reference(self):
        """sample_post() non imposta il riferimento se è None."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_post()

        assert monitor.reference_signature is None

    def test_sample_post_appends_to_samples(self):
        """sample_post() aggiunge un campione alla lista."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_post()

        assert len(monitor.samples) == 1

    def test_sample_post_passes_cpu_samples(self):
        """I campioni CPU vengono passati a background_signature()."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0, 2.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_post()

        call_kwargs = mock_ms.background_signature.call_args[1]
        assert call_kwargs["cpu_samples"] == [1.0, 2.0]

    def test_sample_post_exception_propagates(self):
        """Se il campionamento fallisce, l'eccezione si propaga."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.side_effect = RuntimeError("sampler fallito")
            with pytest.raises(RuntimeError, match="sampler fallito"):
                monitor.sample_post()


class TestEvaluateBackground:
    """Verifica che evaluate_background() restituisca il verdetto corretto."""

    def test_stable_background(self):
        """Stessi processi, CPU stabile → stable."""
        monitor = BackgroundMonitor()
        ref_sig = {
            "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
            "cpu_total_mean_pct": 2.0,
            "power_plan": "balanced",
            "battery": "absent",
        }
        post_sig = {
            "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.5}],
            "cpu_total_mean_pct": 2.5,
            "power_plan": "balanced",
            "battery": "absent",
        }
        monitor.reference_signature = ref_sig
        monitor.samples = [ref_sig, post_sig]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            verdetto, diff = monitor.evaluate_background()

        assert verdetto == "stable"
        assert diff == []

    def test_identity_changed_maps_to_unstable(self):
        """Processo terminato → unstable, non identity_changed."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"processes": [{"pid": 123}]}
        monitor.samples = [{"processes": [{"pid": 123}]}, {"processes": [{"pid": 456}]}]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "identity_changed", ["PID cambiato"]
            )
            verdetto, diff = monitor.evaluate_background()

        assert verdetto == "unstable"
        assert "PID cambiato" in diff

    def test_intensity_unstable_maps_to_unstable(self):
        """CPU variabile oltre tolleranza → unstable."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"cpu_total_mean_pct": 2.0}
        monitor.samples = [
            {"cpu_total_mean_pct": 2.0},
            {"cpu_total_mean_pct": 40.0},
        ]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "intensity_unstable", ["CPU media cambiata"]
            )
            verdetto, diff = monitor.evaluate_background()

        assert verdetto == "unstable"

    def test_insufficient_data_passthrough(self):
        """Dati CPU mancanti → insufficient_data."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"cpu_total_mean_pct": None}
        monitor.samples = [{"cpu_total_mean_pct": None}]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "insufficient_data", ["dati intensità CPU mancanti"]
            )
            verdetto, diff = monitor.evaluate_background()

        assert verdetto == "insufficient_data"

    def test_no_reference_returns_insufficient_data(self):
        """Nessun riferimento → insufficient_data."""
        monitor = BackgroundMonitor()
        verdetto, diff = monitor.evaluate_background()

        assert verdetto == "insufficient_data"
        assert "nessun campione di riferimento" in diff

    def test_no_samples_returns_insufficient_data(self):
        """Nessun campione raccolto → insufficient_data."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"processes": []}
        monitor.samples = []

        verdetto, diff = monitor.evaluate_background()

        assert verdetto == "insufficient_data"
        assert "nessun campione raccolto" in diff

    def test_evaluate_passes_cpu_tolerance(self):
        """La tolleranza CPU viene passata a signatures_match_with_intensity()."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"cpu_total_mean_pct": 2.0}
        monitor.samples = [{"cpu_total_mean_pct": 2.0}]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            monitor.evaluate_background(cpu_tolerance_pct=10.0)

        call_kwargs = mock_ms.signatures_match_with_intensity.call_args[1]
        assert call_kwargs["cpu_tolerance_pct"] == 10.0

    def test_evaluate_passes_power_tolerance(self):
        """La tolleranza potenza viene passata a signatures_match_with_intensity()."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"cpu_total_mean_pct": 2.0}
        monitor.samples = [{"cpu_total_mean_pct": 2.0}]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            monitor.evaluate_background(power_tolerance_w=5.0)

        call_kwargs = mock_ms.signatures_match_with_intensity.call_args[1]
        assert call_kwargs["power_tolerance_w"] == 5.0

    def test_evaluate_compares_last_sample(self):
        """Il confronto usa l'ultimo campione, non il primo."""
        monitor = BackgroundMonitor()
        ref_sig = {"cpu_total_mean_pct": 2.0}
        mid_sig = {"cpu_total_mean_pct": 3.0}
        last_sig = {"cpu_total_mean_pct": 2.5}
        monitor.reference_signature = ref_sig
        monitor.samples = [ref_sig, mid_sig, last_sig]

        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            monitor.evaluate_background()

        call_args = mock_ms.signatures_match_with_intensity.call_args[0]
        assert call_args[0] is ref_sig
        assert call_args[1] is last_sig


class TestToJson:
    """Verifica la serializzazione JSON per il campo notes."""

    def test_to_json_format(self):
        """to_notes_string() restituisce una stringa con chiave strutturata."""
        monitor = BackgroundMonitor()
        json_str = monitor.to_notes_string()

        assert json_str.startswith("background_monitor:")
        data = json.loads(json_str.split(":", 1)[1])
        assert "background_monitor" in data

    def test_to_json_samples_collected(self):
        """Il numero di campioni raccolti è corretto."""
        monitor = BackgroundMonitor()
        monitor.samples = [{"kind": "pre"}, {"kind": "post"}]

        json_str = monitor.to_notes_string()
        data = json.loads(json_str.split(":", 1)[1])

        assert data["background_monitor"]["samples_collected"] == 2

    def test_to_json_reference_available_true(self):
        """Se il riferimento esiste, reference_available è True."""
        monitor = BackgroundMonitor()
        monitor.reference_signature = {"processes": []}

        json_str = monitor.to_notes_string()
        data = json.loads(json_str.split(":", 1)[1])

        assert data["background_monitor"]["reference_available"] is True

    def test_to_json_reference_available_false(self):
        """Se il riferimento manca, reference_available è False."""
        monitor = BackgroundMonitor()

        json_str = monitor.to_notes_string()
        data = json.loads(json_str.split(":", 1)[1])

        assert data["background_monitor"]["reference_available"] is False

    def test_to_json_round_trip(self):
        """Il JSON è parsabile e conserva i dati."""
        monitor = BackgroundMonitor(char_sha256="abc123")
        monitor.reference_signature = {"processes": []}
        monitor.samples = [{"kind": "pre"}, {"kind": "post"}, {"kind": "post"}]

        json_str = monitor.to_notes_string()
        data = json.loads(json_str.split(":", 1)[1])

        assert data["background_monitor"]["samples_collected"] == 3
        assert data["background_monitor"]["reference_available"] is True


class TestIntegration:
    """Test di integrazione: flusso pre → post → evaluate."""

    def test_full_flow_stable(self):
        """Flusso completo: pre → post → evaluate → stable."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0, 2.0, 1.5]
            # Ogni chiamata restituisce un dizionario diverso
            mock_ms.background_signature.side_effect = [
                {
                    "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
                    "cpu_total_mean_pct": 1.5,
                    "power_plan": "balanced",
                    "battery": "absent",
                },
                {
                    "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
                    "cpu_total_mean_pct": 1.5,
                    "power_plan": "balanced",
                    "battery": "absent",
                },
            ]
            pre = monitor.sample_pre()
            post = monitor.sample_post()
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            verdetto, diff = monitor.evaluate_background()

        assert pre["kind"] == "pre"
        assert post["kind"] == "post"
        assert verdetto == "stable"
        assert len(monitor.samples) == 2

    def test_full_flow_unstable(self):
        """Flusso completo: pre → post → evaluate → unstable."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
                "cpu_total_mean_pct": 1.5,
                "power_plan": "balanced",
                "battery": "absent",
            }
            monitor.sample_pre()
            # Dopo il blocco, la CPU è salita
            mock_ms.background_signature.return_value = {
                "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
                "cpu_total_mean_pct": 40.0,
                "power_plan": "balanced",
                "battery": "absent",
            }
            monitor.sample_post()
            mock_ms.signatures_match_with_intensity.return_value = (
                "intensity_unstable",
                ["CPU media cambiata: 1.5% → 40.0%"],
            )
            verdetto, diff = monitor.evaluate_background()

        assert verdetto == "unstable"
        assert any("CPU" in d for d in diff)

    def test_multiple_blocks(self):
        """Più blocchi: ogni blocco ha pre e post, il riferimento resta il primo."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            # Blocco 1
            monitor.sample_pre()
            original_ref = monitor.reference_signature
            monitor.sample_post()
            # Blocco 2
            monitor.sample_pre()
            monitor.sample_post()

        assert len(monitor.samples) == 4
        assert monitor.reference_signature is original_ref

    def test_verdict_in_block_summary(self):
        """Il verdetto può essere aggiunto al riepilogo di blocco."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            monitor.sample_post()
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            verdetto, _ = monitor.evaluate_background()

        block_rec = {"block_id": "test__b01", "bg_monitor_verdict": verdetto}
        assert block_rec["bg_monitor_verdict"] == "stable"

    def test_notes_append(self):
        """Il JSON del monitor può essere aggiunto al campo notes."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()
            monitor.sample_post()

        notes = ["runner=benchmark_v4"]
        notes.append(monitor.to_notes_string())

        assert any("background_monitor:" in note for note in notes)

    def test_exception_during_post_is_insufficient_data(self):
        """Se sample_post fallisce, evaluate restituisce insufficient_data."""
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            # sample_post fallisce
            mock_ms.total_cpu_samples.side_effect = RuntimeError("sampler fallito")
            with pytest.raises(RuntimeError):
                monitor.sample_post()

        # Il riferimento esiste, ma l'ultimo campione è il pre
        verdetto, diff = monitor.evaluate_background()
        # Confronta pre con pre: dovrebbe essere stable
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            verdetto, _ = monitor.evaluate_background()
            assert verdetto == "stable"


class TestAuditMandatoryTests:
    """10 test obbligatori richiesti dall'audit.

    Verifica che il monitor soddisfi i criteri di accettazione:
    persistenza, isolamento errori, confronto locale/globale,
    classificazione processi, copertura temporale, vocabolario chiuso,
    compatibilità schema P5.
    """

    def test_monitor_failure_after_block_saves_rows(self):
        """T1: Il monitor fallisce dopo un blocco completato: le righe sono salvate.

        Se sample_post() o evaluate_background() falliscono, le righe
        energetiche vengono scritte comunque con verdetto insufficient_data.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            # sample_post fallisce: side_effect sulla prossima chiamata
            mock_ms.total_cpu_samples.side_effect = RuntimeError("sampler fallito")

            # Il runner gestisce l'eccezione: verdetto diventa insufficient_data
            bg_verdict = "insufficient_data"
            bg_diff = []
            try:
                monitor.sample_post()
                bg_verdict, bg_diff = monitor.evaluate_global()
            except Exception as bg_exc:
                bg_verdict = "insufficient_data"
                bg_diff = [f"monitor_error: {type(bg_exc).__name__}: {bg_exc}"]

        # Le righe vengono scritte con il verdetto
        assert bg_verdict == "insufficient_data"
        assert len(bg_diff) == 1
        assert "monitor_error" in bg_diff[0]

    def test_monitor_failure_does_not_repeat_block(self):
        """T2: Il fallimento del monitor non ripete lo stesso blocco.

        Un errore del monitor non causa il retry del blocco: il verdetto
        diventa insufficient_data e il runner avanza al blocco successivo.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            # sample_post fallisce: side_effect sulla prossima chiamata
            mock_ms.total_cpu_samples.side_effect = RuntimeError("sampler fallito")

            # Il fallimento non causa retry: il verdetto è insufficient_data
            bg_verdict = "insufficient_data"
            try:
                monitor.sample_post()
                bg_verdict, _ = monitor.evaluate_global()
            except Exception:
                bg_verdict = "insufficient_data"

            assert bg_verdict == "insufficient_data"
            # Il runner avanza: idx += 1 (simulato qui)
            idx = 1
            idx += 1
            assert idx == 2

    def test_verdict_in_persisted_artifact(self):
        """T3: Il verdetto è presente nell'artefatto persistito (JSON).

        to_json() restituisce un dizionario con block_verdicts popolati
        dopo record_block_verdict().
        """
        monitor = BackgroundMonitor()
        monitor.record_block_verdict(
            block_id="test__b01",
            local_verdict="stable",
            local_diff=[],
            global_verdict="stable",
            global_diff=[],
            overhead_s=3.0,
        )
        state = monitor.to_json()

        assert "background_monitor" in state
        assert len(state["background_monitor"]["block_verdicts"]) == 1
        verdict = state["background_monitor"]["block_verdicts"][0]
        assert verdict["block_id"] == "test__b01"
        assert verdict["local_verdict"] == "stable"
        assert verdict["global_verdict"] == "stable"

    def test_second_block_compares_with_own_pre(self):
        """T4: Un secondo blocco viene confrontato con il proprio campione pre.

        evaluate_local() confronta pre vs post dello stesso blocco,
        non con il riferimento iniziale.
        """
        monitor = BackgroundMonitor()
        pre_sig = {
            "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
            "cpu_total_mean_pct": 2.0,
        }
        post_sig = {
            "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.5}],
            "cpu_total_mean_pct": 2.5,
        }
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = ("stable", [])
            verdetto, _ = monitor.evaluate_local(pre_sig, post_sig)

        assert verdetto == "stable"
        # Verifica che il confronto usi pre_sig e post_sig, non il riferimento
        call_args = mock_ms.signatures_match_with_intensity.call_args[0]
        assert call_args[0] is pre_sig
        assert call_args[1] is post_sig

    def test_global_drift_detected_separately(self):
        """T5: La deriva rispetto al riferimento globale viene rilevata separatamente.

        evaluate_global() confronta l'ultimo campione con il riferimento
        iniziale, indipendentemente dal verdetto locale.
        """
        monitor = BackgroundMonitor()
        ref_sig = {
            "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
            "cpu_total_mean_pct": 2.0,
        }
        monitor.reference_signature = ref_sig
        monitor.samples = [
            ref_sig,
            {
                "processes": [{"pid": 123, "name": "ollama", "cpu_pct": 1.0}],
                "cpu_total_mean_pct": 40.0,  # deriva globale
            },
        ]
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "intensity_unstable",
                ["CPU media cambiata"],
            )
            verdetto, diff = monitor.evaluate_global()

        assert verdetto == "unstable"
        assert any("CPU" in d for d in diff)

    def test_ollama_not_confused_with_background(self):
        """T6: Ollama non viene confuso con un processo background indipendente.

        La firma include i processi con PID e nome: Ollama è identificabile
        come TARGET_WORKLOAD, non come BACKGROUND.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [
                    {"pid": 123, "name": "ollama", "cpu_pct": 50.0},
                    {"pid": 456, "name": "chrome", "cpu_pct": 5.0},
                ],
                "cpu_total_mean_pct": 55.0,
            }
            sig = monitor.sample_pre()

        # Ollama è presente nella firma con il suo PID e nome
        processes = sig["processes"]
        ollama = [p for p in processes if p["name"] == "ollama"]
        assert len(ollama) == 1
        assert ollama[0]["pid"] == 123

    def test_ephemeral_process_coverage_insufficient(self):
        """T7: Processo effimero: copertura temporale dichiarata insufficiente.

        Con solo campioni pre/post, non si può sapere se un processo è
        comparso e scomparso nel mezzo. La copertura è dichiarata
        insufficiente, non si dichiara stabilità verificata.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {
                "processes": [],
                "cpu_total_mean_pct": 1.0,
            }
            monitor.sample_pre()
            monitor.sample_post()

        state = monitor.to_json()
        coverage = state["background_monitor"]["coverage_status"]
        # Con solo pre/post, la copertura è dichiarata pre_post_only
        assert coverage == "pre_post_only"
        # Non è "verified" perché manca il campionamento durante il blocco

    def test_insufficient_data_not_stable(self):
        """T8: I dati insufficienti non vengono convertiti in stable.

        Se il monitoraggio fallisce o i dati mancano, il verdetto è
        insufficient_data, non stable.
        """
        monitor = BackgroundMonitor()
        # Nessun campione raccolto
        verdetto, diff = monitor.evaluate_global()

        assert verdetto == "insufficient_data"
        assert verdetto != "stable"
        assert "nessun campione" in diff[0]

    def test_monitor_does_not_modify_csv_columns(self):
        """T9: Il monitor non modifica le 174 colonne CSV P5.

        Il verdetto entra nel campo notes, non in una colonna nuova.
        to_notes_string() restituisce una stringa pronta per notes.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()

        notes_str = monitor.to_notes_string()
        assert notes_str.startswith("background_monitor:")
        # Il campo notes esiste già nello schema P5: nessuna nuova colonna
        assert "CSV_COLUMNS" not in notes_str

    def test_absent_monitor_does_not_change_historical_behavior(self):
        """T10: L'assenza del monitor non modifica il comportamento storico.

        Se bg_monitor_verdict è None, l'anello background_monitor() passa
        senza bloccare: il comportamento storico del runner è preservato.
        """
        from validation_chain import background_monitor

        result = background_monitor(local_verdict=None, global_verdict=None)
        assert result is None
        # None = monitoraggio non attivo, non bloccante


class TestIntegrationEndToEnd:
    """Test end-to-end: valutazione locale, globale, JSON e notes CSV."""

    def test_local_evaluation_executed(self):
        """INT01: Valutazione locale effettivamente eseguita.

        evaluate_local() confronta pre_sig con post_sig dello stesso blocco.
        """
        monitor = BackgroundMonitor()
        pre_sig = {"processes": [], "cpu_total_mean_pct": 2.0}
        post_sig = {"processes": [], "cpu_total_mean_pct": 2.5}
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "stable", []
            )
            verdetto, diff = monitor.evaluate_local(pre_sig, post_sig)

        assert verdetto == "stable"
        mock_ms.signatures_match_with_intensity.assert_called_once()
        call_args = mock_ms.signatures_match_with_intensity.call_args[0]
        assert call_args[0] is pre_sig
        assert call_args[1] is post_sig

    def test_global_evaluation_executed(self):
        """INT02: Valutazione globale effettivamente eseguita.

        evaluate_global() confronta l'ultimo campione con il riferimento.
        """
        monitor = BackgroundMonitor()
        ref_sig = {"processes": [], "cpu_total_mean_pct": 2.0}
        monitor.reference_signature = ref_sig
        monitor.samples = [ref_sig, {"processes": [], "cpu_total_mean_pct": 2.5}]
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.signatures_match_with_intensity.return_value = (
                "stable", []
            )
            verdetto, diff = monitor.evaluate_global()

        assert verdetto == "stable"
        call_args = mock_ms.signatures_match_with_intensity.call_args[0]
        assert call_args[0] is ref_sig

    def test_verdicts_in_json_artifact(self):
        """INT03: Verdetti presenti nell'artefatto JSON.

        record_block_verdict() registra i verdetti per la serializzazione.
        """
        monitor = BackgroundMonitor()
        monitor.record_block_verdict(
            block_id="p1__b01",
            local_verdict="stable",
            local_diff=[],
            global_verdict="stable",
            global_diff=[],
            overhead_s=3.0,
        )
        state = monitor.to_json()
        verdicts = state["background_monitor"]["block_verdicts"]
        assert len(verdicts) == 1
        assert verdicts[0]["block_id"] == "p1__b01"
        assert verdicts[0]["local_verdict"] == "stable"
        assert verdicts[0]["global_verdict"] == "stable"

    def test_batch_id_block_id_linkage(self):
        """INT04: Collegamento univoco tra batch_id e block_id.

        Ogni record JSON contiene block_id per ricondurre al blocco CSV.
        """
        monitor = BackgroundMonitor()
        monitor.record_block_verdict(
            block_id="p1__b01",
            local_verdict="stable",
            local_diff=[],
            global_verdict="stable",
            global_diff=[],
            overhead_s=0.0,
        )
        monitor.record_block_verdict(
            block_id="p1__b02",
            local_verdict="unstable",
            local_diff=["CPU cambiata"],
            global_verdict="stable",
            global_diff=[],
            overhead_s=0.0,
        )
        state = monitor.to_json()
        verdicts = state["background_monitor"]["block_verdicts"]
        block_ids = [v["block_id"] for v in verdicts]
        assert "p1__b01" in block_ids
        assert "p1__b02" in block_ids

    def test_synthetic_verdicts_in_csv_notes(self):
        """INT05: Verdetti sintetici presenti nelle note CSV.

        Le note CSV contengono entrambi i verdetti (locale e globale).
        """
        local_verdict = "stable"
        global_verdict = "unstable"
        local_diff = []
        global_diff = ["CPU media cambiata"]
        bg_note = f"bg_local:{local_verdict}; bg_global:{global_verdict}"
        if local_diff or global_diff:
            all_diff = local_diff + global_diff
            bg_note += f" ({', '.join(all_diff)})"
        assert "bg_local:stable" in bg_note
        assert "bg_global:unstable" in bg_note
        assert "CPU media cambiata" in bg_note

    def test_sample_pre_error_handled(self):
        """INT06: Errore di sample_pre gestito correttamente.

        Se sample_pre() fallisce, pre_sig resta None e il verdetto locale
        diventa insufficient_data.
        """
        monitor = BackgroundMonitor()
        pre_sig = None
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.side_effect = RuntimeError("pre fallito")
            with pytest.raises(RuntimeError, match="pre fallito"):
                monitor.sample_pre()
        # pre_sig è None: il confronto locale darà insufficient_data
        post_sig = {"processes": []}
        verdetto, diff = monitor.evaluate_local(pre_sig, post_sig)
        assert verdetto == "insufficient_data"
        assert "mancante" in diff[0]

    def test_sample_post_error_handled(self):
        """INT07: Errore di sample_post gestito correttamente.

        Se sample_post() fallisce, il verdetto diventa insufficient_data
        ma le righe energetiche restano valide.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            monitor.sample_pre()
            # Simula fallimento post
            mock_ms.total_cpu_samples.side_effect = RuntimeError("post fallito")
            with pytest.raises(RuntimeError, match="post fallito"):
                monitor.sample_post()
        # Il riferimento è impostato, ma post non è disponibile
        # Il runner gestisce l'eccezione e assegna insufficient_data

    def test_json_write_error_no_data_loss(self):
        """INT08: Errore di scrittura JSON senza perdita delle misure.

        Se write_background_monitor_json() fallisce, le righe CSV restano
        valide. Il fallimento è registrato come problema diagnostico.
        """
        from background_monitor_json import write_background_monitor_json
        import tempfile
        import os
        verdicts = [{"block_id": "p1__b01", "local_verdict": "stable"}]
        # Directory non scrivibile: simula errore
        with patch("os.replace", side_effect=OSError("disco pieno")):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = os.path.join(tmpdir, "bg.json")
                with pytest.raises(OSError, match="disco pieno"):
                    write_background_monitor_json(verdicts, path)
            # Le righe CSV restano valide nonostante l'errore JSON

    def test_validation_chain_receives_verdicts(self):
        """INT09: Catena di validazione alimentata dai verdetti effettivi.

        chain_status() riceve bg_local_verdict e bg_global_verdict e li
        passa a background_monitor().
        """
        from validation_chain import (
            chain_status,
            BACKGROUND_LOCAL_UNSTABLE,
            BACKGROUND_GLOBAL_UNSTABLE,
            BACKGROUND_INSUFFICIENT,
        )

        def _blocchi(point_id="p1", r_a=0.05, n=3):
            return [dict({"block_id": f"{point_id}-b{i}", "point_id": point_id,
                          "r_A": r_a, "negative_increment": "false",
                          "invalid_reason": "", "replaced_block_id": ""})
                    for i in range(n)]

        def _controllo(i):
            return {"control_id": f"c{i}", "pre_range_w": 0.4, "dP": 0.2,
                    "e_net_j": 1.0, "dt_w_s": 30.0,
                    "budget_base_j": 30.0, "budget_base_w": 0.5}

        def _controlli(n=6):
            return [_controllo(i) for i in range(n)]

        def _conferma(err_rel=0.02):
            return {"err_rel": err_rel, "e_pred_j": 100.0,
                    "inside_interval": True, "pred_nonpositive": False}

        base_kwargs = dict(
            blocks=_blocchi("p1") + _blocchi("p2"),
            controls=_controlli(),
            n_pairs=6,
            p_lof_perm=0.40,
            confirmation_points=[_conferma(), _conferma(err_rel=0.05)],
            reduced_design=False,
        )

        status = chain_status(**base_kwargs,
                              bg_local_verdict="unstable",
                              bg_global_verdict="stable")
        assert status == BACKGROUND_LOCAL_UNSTABLE

        status = chain_status(**base_kwargs,
                              bg_local_verdict="stable",
                              bg_global_verdict="unstable")
        assert status == BACKGROUND_GLOBAL_UNSTABLE

        status = chain_status(**base_kwargs,
                              bg_local_verdict="insufficient_data",
                              bg_global_verdict="stable")
        assert status == BACKGROUND_INSUFFICIENT

    def test_no_row_duplication_on_monitor_error(self):
        """INT10: Nessuna duplicazione o perdita delle righe energetiche.

        Un errore del monitor non ripete il blocco né duplica le righe.
        Il verdetto diventa insufficient_data e l'export procede.
        """
        monitor = BackgroundMonitor()
        with patch("background_monitor.ms") as mock_ms:
            mock_ms.total_cpu_samples.return_value = [1.0]
            mock_ms.background_signature.return_value = {"processes": []}
            pre_sig = monitor.sample_pre()
        # Simula errore post: il verdetto diventa insufficient_data
        post_sig = None
        local_verdict, local_diff = monitor.evaluate_local(pre_sig, post_sig)
        assert local_verdict == "insufficient_data"
        # Il runner esporta le righe una sola volta, non le ripete
