"""CLI for evaluating MUDILAB outputs against its frozen ground truth.

Input JSONL records contain at least:
  task_id, label, translation, output

Optional:
  tool_calls (list), energy_j, duration_s
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation_runner import summarize_records, write_jsonl
from mudilab_adapter import evaluate_case, load_case


def _read_ground_truth(path: Path) -> dict[str, object]:
    import csv
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["task_id"]: load_case(row) for row in csv.DictReader(handle)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate MUDILAB with the common evaluator")
    parser.add_argument("--ground-truth", required=True, type=Path)
    parser.add_argument("--input", required=True, type=Path,
                        help="JSONL model outputs")
    parser.add_argument("--output", required=True, type=Path,
                        help="JSONL evaluated records")
    parser.add_argument("--summary", required=True, type=Path,
                        help="JSON summary")
    args = parser.parse_args()

    cases = _read_ground_truth(args.ground_truth)
    results = []
    with args.input.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            record = json.loads(line)
            task_id = str(record.get("task_id", ""))
            case = cases.get(task_id)
            if case is None:
                raise ValueError(f"line {line_number}: unknown task_id {task_id!r}")
            result = evaluate_case(
                case,
                label=str(record.get("label", "")),
                translation=record.get("translation"),
                output=str(record.get("output", "")),
                tool_calls=record.get("tool_calls"),
                energy_j=record.get("energy_j"),
                duration_s=record.get("duration_s"),
            )
            results.append(result.to_dict())

    write_jsonl(results, args.output)
    summary = summarize_records(results)
    summary["ground_truth"] = str(args.ground_truth)
    summary["input"] = str(args.input)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
