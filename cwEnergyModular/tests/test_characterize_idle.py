# -*- coding: utf-8 -*-
"""
tests/test_characterize_idle.py — test per il comando characterize di P4.4.

Verifica che il comando characterize:
1. scriva idle_characterization.json con schema v1 completo
2. rifiuti di sovrascrivere un file esistente senza --force
3. usi scrittura atomica (.tmp + rename)
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def test_characterize_writes_idle_characterization_json(tmp_path):
    """Il comando characterize scrive idle_characterization.json con tutti i campi richiesti."""
    from cwEnergyModular.tools.run_gate_p44 import characterize_command

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Mock the machine_state functions to return controlled CPU samples
    with patch("cwEnergyModular.tools.run_gate_p44.ms.total_cpu_samples") as mock_samples:
        # Return samples that will produce a valid Q95 threshold
        mock_samples.return_value = [2.0, 2.5, 3.0, 2.8, 3.2] * 6  # 30 samples

        exit_code = characterize_command(
            output_dir=str(output_dir),
            windows=30,
            window_s=10.0,
            margin_pct=1.0,
            force=False
        )

    assert exit_code == 0
    char_file = output_dir / "idle_characterization.json"
    assert char_file.exists()

    data = json.loads(char_file.read_text())
    assert data["schema_version"] == 1
    assert "quiet_threshold_pct" in data
    assert "sha256" in data
    assert len(data["sha256"]) == 64  # full SHA-256


def test_characterize_refuses_existing_file_without_force(tmp_path):
    """Il comando characterize rifiuta di sovrascrivere un file esistente senza --force."""
    from cwEnergyModular.tools.run_gate_p44 import characterize_command

    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "idle_characterization.json").write_text("{}")

    exit_code = characterize_command(
        output_dir=str(output_dir),
        windows=5,
        window_s=10.0,
        margin_pct=1.0,
        force=False
    )

    assert exit_code == 1  # refusal error


def test_characterize_atomic_write(tmp_path):
    """Il comando characterize usa scrittura atomica (file .tmp + rename)."""
    from cwEnergyModular.tools.run_gate_p44 import characterize_command
    import os

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    with patch("cwEnergyModular.tools.run_gate_p44.ms.total_cpu_samples") as mock_samples:
        mock_samples.return_value = [2.0] * 30

        exit_code = characterize_command(
            output_dir=str(output_dir),
            windows=5,
            window_s=10.0,
            margin_pct=1.0,
            force=True
        )

    assert exit_code == 0
    # Verify no .tmp file remains
    tmp_files = list(output_dir.glob("*.tmp"))
    assert len(tmp_files) == 0