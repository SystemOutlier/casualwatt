from evaluation_runner import summarize_records


def test_summary_rejects_non_finite_energy_and_reports_wilson_interval():
    rows = [
        {"end_to_end": "correct", "energy_j": 12.0, "duration_s": 2.0},
        {"end_to_end": "incorrect", "energy_j": float("nan"), "duration_s": float("inf")},
        {"end_to_end": "indeterminate", "energy_j": None, "duration_s": 1.0},
    ]
    summary = summarize_records(rows)
    assert summary["n_total"] == 3
    assert summary["n_determinate"] == 2
    assert summary["accuracy_on_determinate"] == 0.5
    assert summary["accuracy_wilson_95"] is not None
    assert summary["n_invalid_or_missing_energy"] == 2
    assert summary["n_invalid_or_missing_duration"] == 1
    assert summary["median_energy_correct_j"] == 12.0


def test_summary_keeps_negative_energy_observable():
    rows = [
        {"end_to_end": "correct", "energy_j": -0.2, "duration_s": 1.0},
    ]
    summary = summarize_records(rows)
    assert summary["median_energy_j"] == -0.2
