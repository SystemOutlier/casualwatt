"""CLI for evaluating MUDILAB outputs against its frozen ground truth.

Input JSONL records contain at least:
  task_id, label, translation, output

Optional:
  tool_calls, energy_j, duration_s

``tool_calls`` is passed through unchanged and may be any of the shapes the
pipeline really writes: a list of call mappings, a list of recorded steps, or
the counter dict ``{"cau_inference": {"invocazioni": n, "eccezioni": m}}``; see
``mudilab_adapter._prova_esecuzione``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from evaluation_runner import summarize_records, write_jsonl
from mudilab_adapter import evaluate_case, load_case


def _read_ground_truth(path: Path) -> dict[str, object]:
    import csv
    cases = {}
    allowed_types = {"cond_prob", "inter", "coherence", "counterfactual", "influence"}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), 2):
            case = load_case(row)
            if not case.task_id.strip():
                raise ValueError(f"ground truth line {line_number}: empty task_id")
            if case.task_id in cases:
                raise ValueError(f"ground truth line {line_number}: duplicate task_id {case.task_id!r}")
            if case.task_type not in allowed_types:
                raise ValueError(f"ground truth line {line_number}: unsupported task_type {case.task_type!r}")
            if not case.expected_label.strip():
                raise ValueError(f"ground truth line {line_number}: missing expected label")
            if case.task_type == "counterfactual":
                if (case.expected_lower is None or case.expected_upper is None
                        or case.expected_lower > case.expected_upper):
                    raise ValueError(f"ground truth line {line_number}: invalid counterfactual bounds")
            elif case.expected_probability is None:
                raise ValueError(f"ground truth line {line_number}: missing expected_probability")
            cases[case.task_id] = case
    if not cases:
        raise ValueError("ground truth contains no cases")
    return cases


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
