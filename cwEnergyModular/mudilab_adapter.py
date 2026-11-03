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


def _nome_chiamata(call: Mapping[str, Any]) -> str:
    """The three field names the recorded shapes use for the tool."""
    for key in ("name", "tool", "step"):
        value = str(call.get(key, "")).strip()
        if value:
            return value
    return ""


def _prova_esecuzione(tool_calls: Any) -> tuple[str, list[str]]:
    """Execution status of ``cau_inference`` from the shapes the records use.

    The adapter used to accept one shape only -- a list of mappings carrying
    ``name``/``success`` -- and none of the three shapes the pipeline actually
    writes matches it.  Iterating a dict yields its keys, so ``isinstance(call,
    Mapping)`` was false for every entry, ``matching_calls`` stayed empty and
    every run came back ``missing``: the measurement dropped to zero correct
    not because the tool failed but because the record could not be read.
    The three accepted forms:

    * ``[{"step": "cau_inference", "text": ...}]`` -- the step appended by
      ``run_orchestrato.py:482-488``.  It is appended only after the call
      returned (``:468-480`` routes an exception to ``errore`` with no step),
      so a step with a non-empty text is a successful execution.
    * ``{"cau_inference": {"invocazioni": n, "eccezioni": m}}`` -- the counter
      dict written by ``MUDILAB_correzioni/run_query.py:188-193``, where
      ``tool_ok`` at ``:185`` is exactly ``invocazioni >= 1 and eccezioni == 0``.
    * ``[{"name": "cau_inference", "success": true}]`` -- the declared schema,
      still read.

    Returns ``(status, notes)`` with status in
    ``success | failed | unverified | missing``.
    """
    notes: list[str] = []
    if not tool_calls:
        return "missing", ["no tool call recorded in the run"]

    def da_contatore(valore: Any) -> tuple[str, list[str]]:
        if isinstance(valore, Mapping):
            inv = valore.get("invocazioni", valore.get("invocation_count"))
            exc = valore.get("eccezioni", valore.get("invocation_exception_count"))
        else:
            inv, exc = valore, None
        if isinstance(exc, int) and exc > 0:
            return "failed", [f"cau_inference raised {exc} exception(s)"]
        if isinstance(inv, int) and inv <= 0:
            return "missing", ["cau_inference was never invoked"]
        if isinstance(inv, int) and inv >= 1 and exc == 0:
            return "success", []
        return "unverified", [
            f"cau_inference counter read (invocazioni={inv!r}, eccezioni={exc!r}); "
            "not enough to prove a successful call"
        ]

    if isinstance(tool_calls, Mapping):
        if "cau_inference" in tool_calls or "tool_ok" in tool_calls:
            if "cau_inference" in tool_calls:
                return da_contatore(tool_calls["cau_inference"])
            ok = tool_calls.get("tool_ok")
            if ok is True:
                return "success", []
            if ok is False:
                return "missing", ["tool_ok is false"]
        entries: list[Any] = [tool_calls]
    else:
        entries = list(tool_calls)

    chiamate = [call for call in entries
               if isinstance(call, Mapping) and _nome_chiamata(call) == "cau_inference"]
    if not chiamate:
        # A dict of counters keyed by tool name reaches here when the key is
        # not the tool itself; report missing rather than invent a status.
        return "missing", ["no cau_inference entry among the recorded calls"]

    for call in chiamate:
        if call.get("success") is False:
            return "failed", ["the recorded call reports success=False"]
        status = str(call.get("status", "")).strip().lower()
        if status in ("error", "failed", "failure", "exception"):
            return "failed", [f"the recorded call reports status={status}"]
        ecc = call.get("eccezioni", call.get("invocation_exception_count"))
        if isinstance(ecc, int) and ecc > 0:
            return "failed", [f"cau_inference raised {ecc} exception(s)"]
        if call.get("success") is True or status in ("success", "succeeded", "completed", "ok"):
            return "success", []
        # run_orchestrato.py appends the step only on the return path, so a
        # step that carries the tool's own answer text is an execution proof.
        if str(call.get("text", "") or "").strip():
            return "success", []
    return "unverified", [
        "cau_inference appears in the record without an outcome field or answer text"
    ]


def _argomenti_verificati(tool_calls: Any, translation: Any) -> tuple[str, str]:
    """Whether the call inputs are readable, and whether they are the scored ones.

    Execution proof alone is not argument proof: the review asked for the call
    arguments to be checked too.  The pipeline records the tool's answer text
    but not its inputs, so the honest verdict on the runs produced so far is
    ``not recorded``, which is stated in the notes rather than passed off as a
    verified call.
    """
    raw: list[Mapping[str, Any]] = []
    if isinstance(tool_calls, Mapping):
        entry = tool_calls.get("cau_inference")
        raw = [entry] if isinstance(entry, Mapping) else [tool_calls]
    else:
        raw = [call for call in (tool_calls or []) if isinstance(call, Mapping)]
    for call in raw:
        if _nome_chiamata(call) not in ("", "cau_inference"):
            continue
        for key in ("arguments", "args", "input", "inputs", "features", "params"):
            if key not in call:
                continue
            inviati = call[key]
            if isinstance(inviati, str):
                try:
                    inviati = json.loads(inviati)
                except (TypeError, ValueError):
                    inviati = inviati.strip()
            if isinstance(inviati, Mapping) and inviati == translation:
                return "verified", "call inputs match the scored translation"
            if isinstance(inviati, Mapping):
                return "mismatch", (
                    "call inputs differ from the scored translation: "
                    f"{sorted(inviati)} vs {sorted(translation) if isinstance(translation, Mapping) else translation!r}"
                )
            return "unreadable", f"call inputs recorded as {type(inviati).__name__}, not a mapping"
    return "not recorded", "call inputs are not recorded; execution proof does not cover the arguments"


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
                  output: str, tool_calls: Any = None,
                  energy_j: Optional[float] = None,
                  duration_s: Optional[float] = None) -> MudilabEvaluation:
    """Score one MUDILAB run against the case contract.

    ``tool_calls`` accepts the shapes the pipeline really writes -- a list of
    call mappings, a list of recorded steps, or the counter dict of
    ``run_query.py:188-193`` -- see ``_prova_esecuzione``.
    """
    label_result = evaluate(label, {
        "answer_type": "label", "label": case.expected_label,
    })
    translation_result = evaluate_translation(case, translation)
    output_result = evaluate(output, _case_contract(case))
    tool_status, tool_notes = _prova_esecuzione(tool_calls)
    valid_call = tool_status == "success"
    arg_state, arg_note = _argomenti_verificati(tool_calls, translation)
    stages = (label_result.verdict, translation_result.verdict, output_result.verdict)
    if any(item == "incorrect" for item in stages) or tool_status == "failed":
        end_to_end = "incorrect"
    elif any(item == "indeterminate" for item in stages) or tool_status in ("missing", "unverified"):
        end_to_end = "indeterminate"
    else:
        end_to_end = "correct"
    notes = []
    if tool_status != "success":
        notes.append(f"cau_inference execution status: {tool_status}; "
                     f"{'; '.join(tool_notes) if tool_notes else 'outcome not stated'}")
    if arg_state != "verified":
        notes.append(f"cau_inference arguments: {arg_state} ({arg_note})")
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
