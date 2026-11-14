# -*- coding: utf-8 -*-
"""
tests/test_plan_v2.py — test per il piano v2 di P4.4 con validazione hash.

Verifica che il comando plan:
1. richieda idle_characterization.json esistente
2. validi lo SHA-256 del characterization
3. produca plan.json v2 con schema casualwatt.p44_gate_plan.v2
4. rifiuti piani v1
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))


def test_plan_v2_requires_idle_characterization(tmp_path, monkeypatch):
    """Il comando plan rifiuta se idle_characterization.json non esiste."""
    from cwEnergyModular.tools.run_gate_p44 import cmd_plan
    import cwEnergyModular.tools.run_gate_p44 as rg

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Mock git functions
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))

    # No idle_characterization.json present
    # Need to temporarily change ARCHIVE_DIR
    original_archive = rg.ARCHIVE_DIR
    original_results = rg.RESULTS_DIR
    rg.ARCHIVE_DIR = output_dir
    rg.RESULTS_DIR = output_dir

    try:
        exit_code = cmd_plan(model="test-model")
    finally:
        rg.ARCHIVE_DIR = original_archive
        rg.RESULTS_DIR = original_results

    assert exit_code == 2  # reject: characterization missing


def test_plan_v2_validates_hash(tmp_path, monkeypatch):
    """Il comando plan valida lo SHA-256 di idle_characterization.json."""
    from cwEnergyModular.tools.run_gate_p44 import cmd_plan
    import cwEnergyModular.tools.run_gate_p44 as rg

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Mock git functions
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))

    # Write characterization with known (wrong) hash
    char = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "sha256": "a" * 64,  # wrong hash
    }
    (output_dir / "idle_characterization.json").write_text(json.dumps(char))

    original_archive = rg.ARCHIVE_DIR
    original_results = rg.RESULTS_DIR
    rg.ARCHIVE_DIR = output_dir
    rg.RESULTS_DIR = output_dir

    try:
        exit_code = cmd_plan(model="test-model")
    finally:
        rg.ARCHIVE_DIR = original_archive
        rg.RESULTS_DIR = original_results

    assert exit_code == 2  # reject: hash mismatch


def test_plan_v2_produces_v2_schema(tmp_path, monkeypatch):
    """Il comando plan produce plan.json v2 con tutti i campi richiesti."""
    from cwEnergyModular.tools.run_gate_p44 import cmd_plan
    import cwEnergyModular.tools.run_gate_p44 as rg
    import hashlib

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Mock git functions
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))

    # Write valid characterization with correct hash
    # We need to compute the correct hash
    from cwEnergyModular.tools.idle_characterization import IdleCharacterization

    char_data = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "quiet_consecutive": 3,
        "quiet_window_s": 3.0,
        "quiet_cap_s": 600.0,
        "timestamp": "2026-11-14T00:00:00Z",
        "machine_id": "test-machine",
        "windows": 30,
        "window_s": 10.0,
        "cpu_samples": [2.0] * 30,
        "q95_cpu_pct": 2.0,
        "margin_pct": 1.0,
        "sha256": "",  # placeholder
    }
    # Compute hash
    hash_dict = {k: v for k, v in char_data.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char_data["sha256"] = hashlib.sha256(hash_text).hexdigest()

    (output_dir / "idle_characterization.json").write_text(json.dumps(char_data))

    original_archive = rg.ARCHIVE_DIR
    original_results = rg.RESULTS_DIR
    rg.ARCHIVE_DIR = output_dir
    rg.RESULTS_DIR = output_dir

    try:
        exit_code = cmd_plan(model="test-model")
    finally:
        rg.ARCHIVE_DIR = original_archive
        rg.RESULTS_DIR = original_results

    assert exit_code == 0

    plan_file = output_dir / "plan.json"
    assert plan_file.exists()
    plan = json.loads(plan_file.read_text())

    # Check v2 schema
    assert plan["schema"] == "casualwatt.p44_gate_plan.v2"
    assert plan["requires_idle_characterization"] is True
    assert plan["idle_characterization_sha256"] == char_data["sha256"]
    assert "background_load_policy" in plan
    assert "quiet_params" in plan
    assert "baseline_params" in plan
    assert "budget" in plan
    assert "blocks" in plan
    assert "git_head" in plan
    assert "seed" in plan
    assert "model" in plan
    assert "dt_nominal_s" in plan
    assert "pairs" in plan


def test_plan_v2_rejects_v1_plan(tmp_path, monkeypatch):
    """Il comando plan produce solo piani v2, non v1."""
    from cwEnergyModular.tools.run_gate_p44 import cmd_plan
    import cwEnergyModular.tools.run_gate_p44 as rg
    import hashlib

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    # Mock git functions
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))

    # Write valid characterization
    from cwEnergyModular.tools.idle_characterization import IdleCharacterization

    char_data = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "quiet_consecutive": 3,
        "quiet_window_s": 3.0,
        "quiet_cap_s": 600.0,
        "timestamp": "2026-11-14T00:00:00Z",
        "machine_id": "test-machine",
        "windows": 30,
        "window_s": 10.0,
        "cpu_samples": [2.0] * 30,
        "q95_cpu_pct": 2.0,
        "margin_pct": 1.0,
        "sha256": "",
    }
    hash_dict = {k: v for k, v in char_data.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char_data["sha256"] = hashlib.sha256(hash_text).hexdigest()

    (output_dir / "idle_characterization.json").write_text(json.dumps(char_data))

    original_archive = rg.ARCHIVE_DIR
    original_results = rg.RESULTS_DIR
    rg.ARCHIVE_DIR = output_dir
    rg.RESULTS_DIR = output_dir

    try:
        exit_code = cmd_plan(model="test-model")
    finally:
        rg.ARCHIVE_DIR = original_archive
        rg.RESULTS_DIR = original_results

    assert exit_code == 0

    plan_file = output_dir / "plan.json"
    plan = json.loads(plan_file.read_text())

    # Ensure it's v2, not v1
    assert plan["schema"] == "casualwatt.p44_gate_plan.v2"
    # v1 fields should NOT be present
    assert "pilot" not in plan
    # v2 fields that v1 didn't have (or were renamed)
    assert "requires_idle_characterization" in plan
    assert "idle_characterization_sha256" in plan
    assert "background_load_policy" in plan
    assert "campaign_date" in plan  # v2 field (was in v1, kept in v2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])