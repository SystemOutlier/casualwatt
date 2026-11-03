"""Generic result and energy association utilities for CasualWatt."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional


def attach_energy(record: Mapping[str, Any], energy_j: Optional[float],
                  duration_s: Optional[float] = None) -> dict[str, Any]:
    """Attach energy to one response without turning missing data into zero."""
    output = dict(record)
    output["energy_j"] = energy_j if energy_j is not None else None
    output["duration_s"] = duration_s if duration_s is not None else None
    verdict = output.get("end_to_end", output.get("verdict"))
    output["energy_per_correct_j"] = (
        energy_j if verdict == "correct" and energy_j is not None else None
    )
    return output


def summarize_records(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = list(records)
    verdicts = Counter(str(row.get("end_to_end", row.get("verdict", ""))) for row in rows)
    determinate = [row for row in rows if row.get("end_to_end", row.get("verdict"))
                   in ("correct", "incorrect")]
    correct = sum(row.get("end_to_end", row.get("verdict")) == "correct"
                  for row in determinate)
    def finite_measurement(row: Mapping[str, Any], key: str) -> Optional[float]:
        value = row.get(key)
        if value in (None, "", "N/A"):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if math.isfinite(parsed) else None

    energy_values = [(row, finite_measurement(row, "energy_j")) for row in rows]
    energies = [value for _, value in energy_values if value is not None]
    correct_energies = [value for row, value in energy_values
                        if value is not None
                        and row.get("end_to_end", row.get("verdict")) == "correct"]
    durations = [value for row in rows
                 if (value := finite_measurement(row, "duration_s")) is not None]
    return {
        "n_total": len(rows),
        "n_correct": correct,
        "n_incorrect": sum(row.get("end_to_end", row.get("verdict")) == "incorrect"
                           for row in rows),
        "n_indeterminate": sum(row.get("end_to_end", row.get("verdict"))
                               == "indeterminate" for row in rows),
        "accuracy_on_determinate": correct / len(determinate) if determinate else None,
        "coverage": len(determinate) / len(rows) if rows else None,
        "verdict_counts": dict(verdicts),
        "median_energy_j": _median(energies),
        "median_energy_correct_j": _median(correct_energies),
        "median_duration_s": _median(durations),
        "n_invalid_or_missing_energy": len(rows) - len(energies),
        "missing_energy_rate": 1 - len(energies) / len(rows) if rows else None,
        "n_invalid_or_missing_duration": len(rows) - len(durations),
        "missing_duration_rate": 1 - len(durations) / len(rows) if rows else None,
    }


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return round(values[middle], 6)
    return round((values[middle - 1] + values[middle]) / 2, 6)


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
