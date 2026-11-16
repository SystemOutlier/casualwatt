"""Regression tests for idempotent BackgroundMonitor artifact persistence."""
import json

import pytest

from background_monitor_json import write_background_monitor_json


def _record(batch_id, block_id, verdict="stable"):
    return {
        "batch_id": batch_id,
        "block_id": block_id,
        "local_verdict": verdict,
        "global_verdict": verdict,
        "local_diff": [],
        "global_diff": [],
        "overhead_s": 0.25,
        "timestamp": 123.0,
    }


def test_four_blocks_are_persisted_exactly_once(tmp_path):
    path = tmp_path / "background_monitor.json"
    for index in range(1, 5):
        write_background_monitor_json(
            [_record("batch-A", f"block-{index}")], path
        )

    records = json.loads(path.read_text(encoding="utf-8"))
    assert len(records) == 4
    assert [(r["batch_id"], r["block_id"]) for r in records] == [
        ("batch-A", "block-1"),
        ("batch-A", "block-2"),
        ("batch-A", "block-3"),
        ("batch-A", "block-4"),
    ]


def test_retry_is_idempotent_and_updates_existing_record(tmp_path):
    path = tmp_path / "background_monitor.json"
    write_background_monitor_json([_record("batch-A", "block-1")], path)
    write_background_monitor_json(
        [_record("batch-A", "block-1", verdict="unstable")], path
    )

    records = json.loads(path.read_text(encoding="utf-8"))
    assert len(records) == 1
    assert records[0]["local_verdict"] == "unstable"


def test_same_block_id_in_different_batches_is_not_collapsed(tmp_path):
    path = tmp_path / "background_monitor.json"
    write_background_monitor_json(
        [_record("batch-A", "block-1"), _record("batch-B", "block-1")],
        path,
    )

    records = json.loads(path.read_text(encoding="utf-8"))
    assert len(records) == 2
    assert {r["batch_id"] for r in records} == {"batch-A", "batch-B"}


def test_missing_identity_is_rejected_without_creating_artifact(tmp_path):
    path = tmp_path / "background_monitor.json"
    with pytest.raises(ValueError, match="batch_id and block_id"):
        write_background_monitor_json([{"block_id": "block-1"}], path)
    assert not path.exists()


def test_duplicate_keys_in_same_input_are_rejected(tmp_path):
    path = tmp_path / "background_monitor.json"
    with pytest.raises(ValueError, match="duplicate input"):
        write_background_monitor_json(
            [_record("batch-A", "block-1"), _record("batch-A", "block-1")],
            path,
        )
    assert not path.exists()


def test_corrupt_existing_artifact_is_not_silently_overwritten(tmp_path):
    path = tmp_path / "background_monitor.json"
    path.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match="unreadable"):
        write_background_monitor_json([_record("batch-A", "block-1")], path)

    assert path.read_text(encoding="utf-8") == "{broken"
