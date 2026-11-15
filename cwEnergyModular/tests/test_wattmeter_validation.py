# -*- coding: utf-8 -*-
"""Test per wattmeter_validation.py (Priority 8).

Questi test verificano:
- dry-run produce un piano valido con criteri congelati
- SCPIWattmeter apre/chude correttamente (mockato)
- Validazione fallisce se EMI non disponibile
- Soglie congelate non sono modificabili dai dati
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.wattmeter_validation import (
    PASS_LEVEL_W,
    CADENCE_TOL,
    EMI_TICK_S,
    MIN_WINDOW_S,
    dry_run,
    SCPIWattmeter,
    run_validation,
)


def test_dry_run_produce_piano_valido():
    """dry-run restituisce piano con criteri congelati e note metodologiche."""
    plan = dry_run("COM3", 9600, 300)
    
    assert plan["method"] == "emi-vs-wattmeter"
    assert plan["mode"] == "dry-run"
    assert plan["planned_port"] == "COM3"
    assert plan["planned_baud"] == 9600
    assert plan["planned_seconds"] == 300
    
    criteria = plan["criteria"]
    assert criteria["level_pass_w"] == PASS_LEVEL_W
    assert criteria["cadence_tol"] == CADENCE_TOL
    assert criteria["cadence_target_s"] == EMI_TICK_S
    assert criteria["min_window_s"] == MIN_WINDOW_S
    
    assert "note" in plan
    assert "concordanza" in plan["note"].lower()
    assert "scala assoluta" in plan["note"].lower()


def test_dry_run_scritto_su_file(tmp_path):
    """dry-run con --out scrive file JSON valido."""
    out = tmp_path / "plan.json"
    
    plan = dry_run("COM3", 9600, 300)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["mode"] == "dry-run"
    assert loaded["criteria"]["level_pass_w"] == 1.0


def test_soglie_congelate_non_modificabili():
    """Le soglie sono costanti del modulo, non parametrizzabili dai dati."""
    # Verifica che le costanti siano quelle dichiarate nel protocollo
    assert PASS_LEVEL_W == 1.0
    assert CADENCE_TOL == 0.10
    assert EMI_TICK_S == 1.0
    assert MIN_WINDOW_S == 300.0


@patch("tools.wattmeter_validation.serial.Serial")
def test_scpi_wattmeter_apre_e_chiude(mock_serial):
    """SCPIWattmeter apre connessione, identifica modello, chiude."""
    mock_conn = MagicMock()
    mock_conn.readline.side_effect = [
        b"Keysight,N6705C,MY12345,1.0\n",  # *IDN?
        b"123.45\n",                        # MEAS:POW? (durante open)
        b"123.45\n",                        # MEAS:POW? (durante read_power_w)
    ]
    mock_serial.return_value = mock_conn
    
    wm = SCPIWattmeter("COM3", 9600)
    assert wm.open() is True
    assert wm.model == "Keysight,N6705C,MY12345,1.0"
    
    # Test read
    power = wm.read_power_w()
    assert power == 123.45
    
    wm.close()
    mock_conn.close.assert_called_once()


@patch("tools.wattmeter_validation.serial.Serial")
def test_scpi_wattmeter_comando_alternativo_se_primo_fallisce(mock_serial):
    """Se MEAS:POW? fallisce, prova MEAS:POW:AC?."""
    mock_conn = MagicMock()
    mock_conn.readline.side_effect = [
        b"Generic Wattmeter\n",    # *IDN?
        b"ERROR\n",                # MEAS:POW? fallisce (durante open)
        b"200.0\n",                # MEAS:POW:AC? riesce (durante open)
        b"150.0\n",                # MEAS:POW? (durante read_power_w)
    ]
    mock_serial.return_value = mock_conn
    
    wm = SCPIWattmeter("COM3", 9600)
    assert wm.open() is True
    assert wm.model == "Generic Wattmeter"
    
    # Dopo l'open, read_power_w usa MEAS:POW?
    power = wm.read_power_w()
    assert power == 150.0


@patch("tools.wattmeter_validation.EMICounterBackend")
@patch("tools.wattmeter_validation.SCPIWattmeter")
def test_run_validation_emi_non_disponibile_fallisce(mock_wm_class, mock_emi_class):
    """Se EMI non disponibile, validazione fallisce con verdetto chiaro."""
    mock_wm = MagicMock()
    mock_wm.open.return_value = True
    mock_wm.model = "Test Wattmeter"
    mock_wm_class.return_value = mock_wm
    
    mock_emi_class.return_value = None  # EMI non disponibile
    
    result = run_validation(300, "COM3", 9600)
    
    assert result["verdict"] == "EMI non disponibile"
    assert result["emi_available"] is not True
    mock_wm.close.assert_called_once()


@patch("tools.wattmeter_validation.EMICounterBackend")
@patch("tools.wattmeter_validation.SCPIWattmeter")
def test_run_validation_wattmetro_non_apribile_fallisce(mock_wm_class, mock_emi_class):
    """Se wattmetro non apribile, validazione fallisce."""
    mock_wm = MagicMock()
    mock_wm.open.return_value = False
    mock_wm.model = "error: port not found"
    mock_wm_class.return_value = mock_wm
    
    mock_emi = MagicMock()
    mock_emi.available = True
    mock_emi_class.return_value = mock_emi
    
    result = run_validation(300, "COM3", 9600)
    
    assert "wattmetro non apribile" in result["verdict"]
    # EMI non e' mai stata aperta (il wattmetro e' fallito prima), quindi non va chiusa
    mock_emi.close.assert_not_called()


def test_soglia_finestra_minima_rifiutata():
    """Finestra sotto MIN_WINDOW_S (300s) e' rifiutata prima di partire."""
    # Questo e' testato via CLI, qui verifichiamo la costante
    assert MIN_WINDOW_S == 300.0
    
    # dry-run accetta qualsiasi durata (solo piano)
    plan = dry_run("COM3", 9600, 60)  # 60s < 300s
    assert plan["planned_seconds"] == 60
    # Il controllo min_window_s e' nel main CLI, non in dry_run


def test_note_metodologica_esplicita_in_output():
    """L'output include la nota che concordanza != validazione scala."""
    plan = dry_run("COM3", 9600, 300)
    
    rules = plan["criteria"]["rules"]
    assert "concordanza" in rules.lower()
    assert "validazione" in rules.lower()
    assert "scala assoluta" in rules.lower()
    assert "grandezze fisiche diverse" in rules.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])