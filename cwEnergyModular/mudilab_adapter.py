"""MUDILAB adapter for the common CasualWatt evaluator.

The adapter evaluates independent pipeline stages and exposes one end-to-end
verdict.  It never treats a correct number as sufficient when the label,
translation, or tool invocation is invalid.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from robust_evaluator import EvaluationResult, evaluate


_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")


@dataclass(frozen=True)
class MudilabCase:
    task_id: str
    task_type: str
    expected_label: str
    expected_probability: Optional[float] = None
    expected_lower: Optional[float] = None
    expected_upper: Optional[float] = None
    expected_decision: Optional[str] = None
    target_variable: str = ""
    target_state: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)
    intervention: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MudilabEvaluation:
    task_id: str
    task_type: str
    label: EvaluationResult
    translation: EvaluationResult
    output: EvaluationResult
    tool_call_valid: bool
    tool_call_status: str
    end_to_end: str
    energy_j: Optional[float] = None
    duration_s: Optional[float] = None
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "label": self.label.to_dict(),
            "translation": self.translation.to_dict(),
            "output": self.output.to_dict(),
            "tool_call_valid": self.tool_call_valid,
            "tool_call_status": self.tool_call_status,
            "end_to_end": self.end_to_end,
            "energy_j": self.energy_j,
            "duration_s": self.duration_s,
            "notes": list(self.notes),
        }


def _num(text: str) -> list[float]:
    return [float(item.replace(",", ".")) for item in _NUMBER_RE.findall(text or "")]


def _case_contract(case: MudilabCase) -> dict[str, Any]:
    if case.task_type == "counterfactual":
        return {
            "answer_type": "interval", "lower": case.expected_lower,
            "upper": case.expected_upper, "absolute_tolerance": 5e-4,
        }
    if case.task_type == "coherence":
        return {
            "answer_type": "number", "accepted_answers": [case.expected_probability],
            "absolute_tolerance": 5e-4,
        }
    return {
        "answer_type": "number", "accepted_answers": [case.expected_probability],
        "absolute_tolerance": 5e-4,
    }


def load_case(row: Mapping[str, Any]) -> MudilabCase:
    task_type = str(row.get("task_type", row.get("ramo", "")))
    default_labels = {
        "cond_prob": "backward_reasoning",
        "inter": "intervention",
        "coherence": "coherence",
        "counterfactual": "counterfactual",
        "influence": "influence",
    }
    def obj(name: str) -> dict[str, Any]:
        raw = row.get(name, "")
        if isinstance(raw, Mapping):
            return dict(raw)
        try:
            value = json.loads(str(raw or "{}"))
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    def opt_float(*names: str) -> Optional[float]:
        for name in names:
            value = row.get(name, "")
            if value not in (None, ""):
                try:
                    parsed = float(value)
                    if math.isfinite(parsed):
                        return parsed
                except (TypeError, ValueError, OverflowError):
                    pass
        return None

    return MudilabCase(
        task_id=str(row.get("task_id", "")),
        task_type=task_type,
        expected_label=str(row.get("etichetta_attesa")
                           or default_labels.get(task_type)
                           or row.get("expected_label", "")),
        expected_probability=opt_float("expected_probability"),
        expected_lower=opt_float("expected_lower_graph", "expected_lower"),
        expected_upper=opt_float("expected_upper_graph", "expected_upper"),
        expected_decision=str(row.get("expected_decision", "") or ""),
        target_variable=str(row.get("target_variable", "")),
        target_state=str(row.get("target_state", "")),
        evidence=obj("evidence_json"),
        intervention=obj("intervention_json"),
    )


def evaluate_translation(case: MudilabCase, translation: Any) -> EvaluationResult:
    expected_input = case.intervention if case.task_type in ("inter", "counterfactual") else case.evidence
    expected = {
        "input": expected_input,
        "output": {case.target_variable: case.target_state},
    }
    return evaluate(translation, {"answer_type": "structured", "expected": expected})


def evaluate_case(case: MudilabCase, *, label: str, translation: Any,
                  output: str, tool_calls: Optional[list[Mapping[str, Any]]] = None,
                  energy_j: Optional[float] = None,
                  duration_s: Optional[float] = None) -> MudilabEvaluation:
    label_result = evaluate(label, {
        "answer_type": "label", "label": case.expected_label,
    })
    translation_result = evaluate_translation(case, translation)
    output_result = evaluate(output, _case_contract(case))
    calls = tool_calls or []
    matching_calls = [call for call in calls
                      if isinstance(call, Mapping)
                      and str(call.get("name", call.get("tool", ""))).strip()
                      == "cau_inference"]
    if not matching_calls:
        tool_status = "missing"
    elif any(call.get("success") is False or
             str(call.get("status", "")).lower() in ("error", "failed", "failure")
             for call in matching_calls):
        tool_status = "failed"
    elif any(call.get("success") is True or
             str(call.get("status", "")).lower() in ("success", "succeeded", "completed")
             for call in matching_calls):
        tool_status = "success"
    else:
        tool_status = "unverified"
    valid_call = tool_status == "success"
    stages = (label_result.verdict, translation_result.verdict, output_result.verdict)
    if any(item == "incorrect" for item in stages) or tool_status == "failed":
        end_to_end = "incorrect"
    elif any(item == "indeterminate" for item in stages) or tool_status in ("missing", "unverified"):
        end_to_end = "indeterminate"
    else:
        end_to_end = "correct"
    notes = []
    if tool_status != "success":
        notes.append(f"cau_inference execution status: {tool_status}; successful execution is not verified")
    if case.task_type == "coherence" and case.expected_decision:
        expected_decision = case.expected_decision.strip().lower()
        if expected_decision == "not_strongly_compatible":
            decision_markers = ("not strongly compatible",)
        elif expected_decision == "strongly_compatible":
            decision_markers = ("strongly compatible",)
        else:
            decision_markers = (expected_decision.replace("_", " "),)
        observed = [marker in output.lower() for marker in decision_markers]
        contains_negative = "not strongly compatible" in output.lower()
        decision_ok = any(observed) and (
            (expected_decision == "not_strongly_compatible" and contains_negative)
            or (expected_decision == "strongly_compatible" and not contains_negative)
            or expected_decision not in ("not_strongly_compatible", "strongly_compatible")
        )
        if not decision_ok:
            end_to_end = "incorrect"
            notes.append("coherence qualitative decision mismatch (literal marker check; semantic equivalence not assessed)")
    return MudilabEvaluation(
        task_id=case.task_id, task_type=case.task_type,
        label=label_result, translation=translation_result,
        output=output_result, tool_call_valid=valid_call,
        tool_call_status=tool_status,
        end_to_end=end_to_end, energy_j=energy_j, duration_s=duration_s,
        notes=tuple(notes),
    )
