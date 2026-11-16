# -*- coding: utf-8 -*-
"""test_background_stability.py — Stabilità temporale reale del background.

Verifica che _verifica_stabilita_background usi window_s per raccogliere
le firme a distanza temporale, non back-to-back. Usa clock iniettabili
per rendere i test deterministici e veloci.

I test coprono:
- firme raccolte a distanza window_s;
- tempo totale misurato correttamente;
- stabilità con firme identiche;
- instabilità con firme diverse;
- sleep_func chiamato il numero corretto di volte.
"""
from __future__ import annotations
from typing import Dict, List

import pytest
from unittest import mock

# Importa la funzione da testare
import sys
from pathlib import Path
tools_dir = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_dir))
from run_gate_p44 import _verifica_stabilita_background


class FakeMachineState:
    """Mock di machine_state per test deterministici."""
    
    def __init__(self, signatures: List[Dict]):
        """Inizializza con una lista di firme da restituire sequenzialmente."""
        self.signatures = signatures
        self.call_count = 0
    
    def background_signature(self, char_sha256: str = "",
                             cpu_samples=None) -> Dict:
        """Restituisce la prossima firma nella sequenza."""
        if self.call_count < len(self.signatures):
            sig = self.signatures[self.call_count]
            self.call_count += 1
            return sig
        return self.signatures[-1]

    def signatures_match(self, sig1: Dict, sig2: Dict) -> tuple:
        """Confronta due firme semplicemente."""
        if sig1 == sig2:
            return (True, [])
        else:
            return (False, ["firme diverse"])

    def signatures_match_with_intensity(self, sig1: Dict, sig2: Dict,
                                        cpu_tolerance_pct=5.0,
                                        power_tolerance_w=None) -> tuple:
        """Confronto con intensità delegato a signatures_match per i test vecchi."""
        match, diff = self.signatures_match(sig1, sig2)
        if match:
            return ("stable", [])
        return ("identity_changed", diff)

    def total_cpu_samples(self, duration_s=3.0, interval_s=1.0) -> List[float]:
        """Restituisce campioni CPU vuoti per default."""
        return []


def test_firme_raccolte_a_distanza_window_s():
    """Le firme sono raccolte a distanza window_s, non back-to-back."""
    # Firme identiche per test di stabilità
    sig_stabile = {"processes": [], "power_plan": "balanced", "battery": "absent"}
    fake_ms = FakeMachineState([sig_stabile, sig_stabile, sig_stabile])
    
    sleep_times: List[float] = []
    def fake_sleep(s: float) -> None:
        sleep_times.append(s)
    
    def fake_time() -> float:
        return 0.0
    
    with mock.patch('run_gate_p44.ms') as mock_ms:
        mock_ms.background_signature.side_effect = fake_ms.background_signature
        mock_ms.signatures_match.side_effect = fake_ms.signatures_match
        mock_ms.signatures_match_with_intensity.side_effect = fake_ms.signatures_match_with_intensity
        mock_ms.total_cpu_samples.side_effect = fake_ms.total_cpu_samples
        
        result = _verifica_stabilita_background(
            char_sha256="test_hash",
            min_finestre=3,
            window_s=10.0,
            sleep_func=fake_sleep,
            time_func=fake_time,
        )
    
    # sleep_func dovrebbe essere chiamato 2 volte (tra firma 1-2 e 2-3)
    assert len(sleep_times) == 2
    assert sleep_times[0] == 10.0
    assert sleep_times[1] == 10.0
    
    # 3 firme raccolte
    assert result["finestre_raccolte"] == 3
    assert result["window_s"] == 10.0


def test_tempo_totale_misurato():
    """Il tempo totale è misurato dalla prima all'ultima firma."""
    # Firme identiche per test di stabilità
    sig_stabile = {"processes": [], "power_plan": "balanced", "battery": "absent"}
    fake_ms = FakeMachineState([sig_stabile, sig_stabile, sig_stabile])
    
    # Tempo che avanza di 10s dopo ogni sleep
    current_time = [0.0]
    def fake_sleep_with_time(s: float) -> None:
        current_time[0] += s
    
    def fake_time_advancing() -> float:
        return current_time[0]
    
    with mock.patch('run_gate_p44.ms') as mock_ms:
        mock_ms.background_signature.side_effect = fake_ms.background_signature
        mock_ms.signatures_match.side_effect = fake_ms.signatures_match
        mock_ms.signatures_match_with_intensity.side_effect = fake_ms.signatures_match_with_intensity
        mock_ms.total_cpu_samples.side_effect = fake_ms.total_cpu_samples
        
        result = _verifica_stabilita_background(
            char_sha256="test_hash",
            min_finestre=3,
            window_s=10.0,
            sleep_func=fake_sleep_with_time,
            time_func=fake_time_advancing,
        )
    
    # Tempo totale dovrebbe essere ~20s (2 sleep da 10s)
    assert result["tempo_totale_s"] >= 20.0


def test_stabilita_con_firme_identiche():
    """Firme identiche restituiscono stabile=True quando i dati CPU sono presenti."""
    # Firme identiche per test di stabilità
    sig_stabile = {
        "processes": [{"pid": 123, "name": "idle"}],
        "power_plan": "balanced",
        "cpu_total_mean_pct": 2.0,
    }
    fake_ms = FakeMachineState([sig_stabile, sig_stabile, sig_stabile])

    def fake_sleep(s: float) -> None:
        pass

    def fake_time() -> float:
        return 0.0

    def fake_cpu():
        return [2.0]

    with mock.patch('run_gate_p44.ms') as mock_ms:
        mock_ms.background_signature.side_effect = fake_ms.background_signature
        mock_ms.signatures_match.side_effect = fake_ms.signatures_match
        mock_ms.signatures_match_with_intensity.side_effect = fake_ms.signatures_match_with_intensity
        mock_ms.total_cpu_samples.side_effect = fake_ms.total_cpu_samples

        result = _verifica_stabilita_background(
            char_sha256="test_hash",
            min_finestre=3,
            window_s=10.0,
            sleep_func=fake_sleep,
            time_func=fake_time,
            campiona_cpu=fake_cpu,
        )

    assert result["stabile"] is True
    assert result["stability_status"] == "stable"


def test_instabilita_con_firme_diverse():
    """Firme diverse azzerano la sequenza; se il tempo massimo è superato, SystemExit."""
    fake_ms = FakeMachineState([
        {"processes": [{"pid": 123, "name": "idle"}], "power_plan": "balanced"},
        {"processes": [{"pid": 456, "name": "new_process"}], "power_plan": "balanced"},
        {"processes": [{"pid": 456, "name": "new_process"}], "power_plan": "balanced"},
    ])

    def fake_sleep(s: float) -> None:
        pass

    current_time = [0.0]
    def fake_time() -> float:
        return current_time[0]

    with mock.patch('run_gate_p44.ms') as mock_ms:
        mock_ms.background_signature.side_effect = fake_ms.background_signature
        mock_ms.signatures_match.side_effect = fake_ms.signatures_match
        mock_ms.signatures_match_with_intensity.side_effect = fake_ms.signatures_match_with_intensity
        mock_ms.total_cpu_samples.side_effect = fake_ms.total_cpu_samples

        with pytest.raises(SystemExit) as exc_info:
            _verifica_stabilita_background(
                char_sha256="test_hash",
                min_finestre=3,
                window_s=0.0,
                max_wait_s=0.0,
                sleep_func=fake_sleep,
                time_func=fake_time,
            )

        assert "tempo massimo" in str(exc_info.value)


def test_sleep_chiamato_n_meno_1_volte():
    """sleep_func è chiamato n-1 volte per n finestre."""
    # Firme identiche per test di stabilità
    sig_stabile = {"processes": [], "power_plan": "balanced", "battery": "absent"}
    fake_ms = FakeMachineState([sig_stabile] * 5)
    
    sleep_count = [0]
    def fake_sleep(s: float) -> None:
        sleep_count[0] += 1
    
    def fake_time() -> float:
        return 0.0
    
    with mock.patch('run_gate_p44.ms') as mock_ms:
        mock_ms.background_signature.side_effect = fake_ms.background_signature
        mock_ms.signatures_match.side_effect = fake_ms.signatures_match
        mock_ms.signatures_match_with_intensity.side_effect = fake_ms.signatures_match_with_intensity
        mock_ms.total_cpu_samples.side_effect = fake_ms.total_cpu_samples
        
        result = _verifica_stabilita_background(
            char_sha256="test_hash",
            min_finestre=5,
            window_s=10.0,
            sleep_func=fake_sleep,
            time_func=fake_time,
        )
    
    # 5 finestre = 4 sleep
    assert sleep_count[0] == 4
    assert result["finestre_raccolte"] == 5
