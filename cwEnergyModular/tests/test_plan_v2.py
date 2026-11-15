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


def _piano_con(tmp_path, monkeypatch, policy):
    """Costruisce un piano v2 con la politica richiesta e lo restituisce.

    La caratterizzazione e' sintetica con hash calcolato dal contenuto, come
    negli altri test di questo file; la politica e' l'unica variabile, perche'
    e' l'unica cosa che questi test devono cambiare.
    """
    import hashlib

    from cwEnergyModular.tools.run_gate_p44 import cmd_plan
    import cwEnergyModular.tools.run_gate_p44 as rg

    output_dir = tmp_path / f"out-{policy}"
    output_dir.mkdir()

    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))

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
        exit_code = cmd_plan(model="test-model", background_policy=policy)
    finally:
        rg.ARCHIVE_DIR = original_archive
        rg.RESULTS_DIR = original_results

    assert exit_code == 0
    return json.loads((output_dir / "plan.json").read_text())


def test_check_e_dichiara_il_salto_quiete_in_background_controlled(tmp_path, monkeypatch):
    """Il piano e' la pre-registrazione: se il tool SALTA la precondizione di
    quiete in politica background_controlled, il testo del check E deve dirlo
    — altrimenti il piano promette una verifica che l'esecuzione non fa, e la
    difformita' fra promessa e misura sarebbe scoperta solo dai dati."""
    plan = _piano_con(tmp_path, monkeypatch, "background_controlled")
    testo_e = plan["checks"]["E"]
    assert "background_controlled" in testo_e
    assert "salto" in testo_e.lower()


def test_check_e_in_block_mantiene_la_quiete_come_precondizione(tmp_path, monkeypatch):
    """Lato di accettazione: in politica block il salto non esiste e il check E
    continua a dichiarare la quiete come precondizione attiva prima di ogni
    blocco. La stessa frase non puo' valere per tutte e due le politiche, ed e'
    per questo che il testo dipende dalla politica scritta nel piano."""
    plan = _piano_con(tmp_path, monkeypatch, "block")
    testo_e = plan["checks"]["E"]
    assert "precondizione di quiete PRIMA di ogni blocco" in testo_e
    assert "salto" not in testo_e.lower()


def test_check_f_descrive_stabilization_senza_parentesi_non_interpolate(tmp_path, monkeypatch):
    """In background_controlled il criterio che gira e' la stabilizzazione
    (media mobile), non il rientro assoluto, e la cpu non decide: il testo del
    check F deve dirlo — e deve dirlo con i NUMERI, non con le graffe di una
    f-string dimenticata, perche' una grafa non interpolata nel piano e' un
    parametro che nessuno ha scelto e che nessun codice leggera'."""
    plan = _piano_con(tmp_path, monkeypatch, "background_controlled")
    testo_f = plan["checks"]["F"]
    assert "media mobile" in testo_f
    assert "NON decide" in testo_f
    assert "{rg." not in testo_f
    assert plan["warmup_mode"] == "stabilization"
    assert f"{plan['warmup_sustain_s']:g} s" in testo_f


def test_check_f_in_block_descrive_il_rientro_assoluto(tmp_path, monkeypatch):
    """Lato di accettazione: in politica block il criterio resta il rientro
    assoluto su due segnali, con la cpu soglia davvero decisiva, e il testo lo
    dice con la soglia derivata dalla caratterizzazione."""
    plan = _piano_con(tmp_path, monkeypatch, "block")
    testo_f = plan["checks"]["F"]
    assert "cpu_percent sta sotto" in testo_f
    assert plan["warmup_mode"] == "absolute"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])