"""Independent, conservative evaluator for benchmark answers.

This module deliberately does not replace ``evaluator.py``.  It provides a
second measurement path based on deterministic answer contracts:

* closed numeric and short-text answers are checked exactly;
* free-text answers are scored only from declared required/forbidden facts;
* semantic similarity and LLM judges are optional diagnostics, never the
  primary correctness decision;
* ambiguous or incomplete references return ``indeterminate`` rather than a
  fabricated zero or positive score.

Reference contracts may be dictionaries or JSON strings, for example::

    {
      "answer_type": "number",
      "accepted_answers": ["21"],
      "absolute_tolerance": 0.01,
      "relative_tolerance": 0.001
    }

    {
      "answer_type": "free_text",
      "required_facts": ["Roma", "Lazio"],
      "forbidden_facts": ["Firenze"],
      "minimum_required_facts": 2
    }
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence


VERDICTS = ("correct", "incorrect", "indeterminate")
_NUMBER_RE = re.compile(r"[-+]?(?:\d+(?:[.,]\d+)?|\d+[.,]\d+e[-+]?\d+)", re.I)
_ANSWER_MARKER_RE = re.compile(
    r"(?:final answer|answer|risposta|risultato|result)\s*[:=]\s*"
    r"([-+]?(?:\d+(?:[.,]\d+)?|\d+[.,]\d+e[-+]?\d+))",
    re.I,
)
_INTERVAL_RE = re.compile(
    r"(?:between|from)\s+(-?(?:\d+(?:[.,]\d+)?))\s+"
    r"(?:and|to)\s+(-?(?:\d+(?:[.,]\d+)?))",
    re.I,
)


@dataclass(frozen=True)
class EvaluationResult:
    verdict: str
    score: Optional[float]
    confidence: float
    method: str
    answer_type: str
    extracted_answer: Optional[str] = None
    matched_answers: tuple[str, ...] = ()
    missing_facts: tuple[str, ...] = ()
    forbidden_facts: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _text(value).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _parse_contract(reference: Any) -> Optional[dict[str, Any]]:
    if isinstance(reference, Mapping):
        return dict(reference)
    raw = _text(reference)
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def _numbers(text: str) -> list[str]:
    return _NUMBER_RE.findall(text or "")


def _to_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _numeric_match(actual: float, expected: float, absolute: float,
                   relative: float) -> bool:
    distance = abs(actual - expected)
    scale = max(abs(expected), 1.0)
    return distance <= max(absolute, relative * scale)


def _result(verdict: str, score: Optional[float], confidence: float,
            method: str, answer_type: str, **kwargs: Any) -> EvaluationResult:
    if verdict not in VERDICTS:
        raise ValueError(f"unknown verdict: {verdict}")
    return EvaluationResult(
        verdict=verdict,
        score=score,
        confidence=max(0.0, min(1.0, confidence)),
        method=method,
        answer_type=answer_type,
        **kwargs,
    )


def _evaluate_number(answer: str, contract: Mapping[str, Any]) -> EvaluationResult:
    accepted = contract.get("accepted_answers", contract.get("answers"))
    if accepted is None:
        accepted = [contract.get("answer", contract.get("value"))]
    expected = [_to_float(item) for item in accepted]
    expected = [item for item in expected if item is not None]
    if not expected:
        return _result("indeterminate", None, 0.0, "number_contract_missing",
                       "number", diagnostics={"reason": "no numeric reference"})

    marked = _ANSWER_MARKER_RE.findall(answer or "")
    candidates = marked or _numbers(answer)
    if not candidates:
        return _result("incorrect", 0.0, 0.99, "number_no_answer",
                       "number", diagnostics={"reason": "no numeric answer"})
    parsed = [_to_float(item) for item in candidates]
    parsed = [item for item in parsed if item is not None]
    if not parsed:
        return _result("incorrect", 0.0, 0.99, "number_parse_failed", "number")

    # A marked answer is authoritative.  Without a marker, only an unambiguous
    # final numeric candidate is accepted; this avoids rewarding an intermediate
    # number merely because it happened to be the last token.
    actual = parsed[-1]
    if not marked and len(parsed) > 1:
        unique = {round(item, 12) for item in parsed}
        if len(unique) > 1:
            return _result(
                "indeterminate", None, 0.45, "number_ambiguous",
                "number", extracted_answer=str(candidates[-1]),
                diagnostics={"candidates": candidates},
            )

    absolute = float(contract.get("absolute_tolerance", 1e-9))
    relative = float(contract.get("relative_tolerance", 1e-6))
    matched = tuple(str(item) for item in expected
                    if _numeric_match(actual, item, absolute, relative))
    ok = bool(matched)
    return _result(
        "correct" if ok else "incorrect", 1.0 if ok else 0.0, 0.99,
        "number_tolerance_match", "number", extracted_answer=str(actual),
        matched_answers=matched,
        diagnostics={"absolute_tolerance": absolute,
                      "relative_tolerance": relative},
    )


def _accepted_texts(contract: Mapping[str, Any]) -> list[str]:
    values = contract.get("accepted_answers", contract.get("answers"))
    if values is None:
        values = [contract.get("answer", contract.get("value"))]
    if isinstance(values, str):
        values = [values]
    return [_text(item) for item in values if _text(item)]


def _evaluate_short_text(answer: str, contract: Mapping[str, Any]) -> EvaluationResult:
    accepted = _accepted_texts(contract)
    if not accepted:
        return _result("indeterminate", None, 0.0, "short_text_contract_missing",
                       "short_text", diagnostics={"reason": "no text reference"})
    normalized_answer = normalize_text(answer)
    matched = tuple(item for item in accepted
                    if re.search(rf"\b{re.escape(normalize_text(item))}\b",
                                 normalized_answer))
    ok = bool(matched)
    return _result(
        "correct" if ok else "incorrect", 1.0 if ok else 0.0, 0.98,
        "short_text_token_boundary_match", "short_text",
        matched_answers=matched,
        diagnostics={"accepted_answers": accepted},
    )


def _evaluate_free_text(answer: str, contract: Mapping[str, Any]) -> EvaluationResult:
    required = [_text(item) for item in contract.get("required_facts", []) if _text(item)]
    forbidden = [_text(item) for item in contract.get("forbidden_facts", []) if _text(item)]
    if not required and not forbidden:
        return _result("indeterminate", None, 0.0, "free_text_contract_missing",
                       "free_text",
                       diagnostics={"reason": "no verifiable facts declared"})

    normalized = normalize_text(answer)
    missing = tuple(item for item in required
                    if normalize_text(item) not in normalized)
    found_forbidden = tuple(item for item in forbidden
                            if normalize_text(item) in normalized)
    minimum = int(contract.get("minimum_required_facts", len(required)))
    present = len(required) - len(missing)
    if found_forbidden:
        verdict = "incorrect"
    elif present < minimum:
        verdict = "incorrect"
    else:
        verdict = "correct"
    score = present / len(required) if required else (0.0 if found_forbidden else 1.0)
    return _result(
        verdict, round(score, 6), 0.9 if required else 0.75,
        "free_text_declared_facts", "free_text",
        missing_facts=missing, forbidden_facts=found_forbidden,
        diagnostics={"required_count": len(required), "present_count": present,
                     "minimum_required_facts": minimum},
    )


def _evaluate_interval(answer: str, contract: Mapping[str, Any]) -> EvaluationResult:
    lower = _to_float(contract.get("lower", contract.get("expected_lower")))
    upper = _to_float(contract.get("upper", contract.get("expected_upper")))
    if lower is None or upper is None or lower > upper:
        return _result("indeterminate", None, 0.0, "interval_contract_invalid",
                       "interval", diagnostics={"reason": "invalid bounds"})
    match = _INTERVAL_RE.search(answer or "")
    if not match:
        return _result("incorrect", 0.0, 0.98, "interval_not_found",
                       "interval", diagnostics={"reason": "interval not found"})
    actual_lower, actual_upper = (_to_float(match.group(1)),
                                  _to_float(match.group(2)))
    if actual_lower is None or actual_upper is None or actual_lower > actual_upper:
        return _result("incorrect", 0.0, 0.98, "interval_invalid",
                       "interval", diagnostics={"answer": match.group(0)})
    absolute = float(contract.get("absolute_tolerance", 1e-9))
    relative = float(contract.get("relative_tolerance", 0.0))
    lower_ok = _numeric_match(actual_lower, lower, absolute, relative)
    upper_ok = _numeric_match(actual_upper, upper, absolute, relative)
    return _result(
        "correct" if lower_ok and upper_ok else "incorrect",
        1.0 if lower_ok and upper_ok else 0.0, 0.99,
        "interval_bounds_match", "interval",
        extracted_answer=f"{actual_lower} - {actual_upper}",
        diagnostics={"expected_lower": lower, "expected_upper": upper,
                     "actual_lower": actual_lower, "actual_upper": actual_upper,
                     "lower_match": lower_ok, "upper_match": upper_ok,
                     "absolute_tolerance": absolute},
    )


def _evaluate_label(answer: str, contract: Mapping[str, Any]) -> EvaluationResult:
    expected = normalize_text(contract.get("label", contract.get("expected_label")))
    actual = normalize_text(answer)
    if not expected:
        return _result("indeterminate", None, 0.0, "label_contract_missing",
                       "label")
    # Labels are categorical: surrounding explanation is not accepted unless
    # the contract explicitly allows it.
    allowed = bool(contract.get("allow_explanation", False))
    ok = expected == actual if not allowed else re.search(
        rf"\b{re.escape(expected)}\b", actual) is not None
    return _result("correct" if ok else "incorrect", 1.0 if ok else 0.0,
                   0.99, "label_exact_match", "label",
                   extracted_answer=answer.strip(),
                   diagnostics={"expected_label": expected})


def _evaluate_structured(answer: Any, contract: Mapping[str, Any]) -> EvaluationResult:
    if not isinstance(answer, Mapping):
        try:
            answer = json.loads(_text(answer))
        except (TypeError, ValueError):
            answer = None
    expected = contract.get("expected", contract.get("schema"))
    if not isinstance(answer, Mapping) or not isinstance(expected, Mapping):
        return _result("indeterminate", None, 0.0, "structured_contract_invalid",
                       "structured")
    missing = []
    mismatched = {}
    for key, value in expected.items():
        if key not in answer:
            missing.append(key)
        elif answer[key] != value:
            mismatched[key] = {"expected": value, "actual": answer[key]}
    ok = not missing and not mismatched
    return _result(
        "correct" if ok else "incorrect", 1.0 if ok else 0.0, 0.99,
        "structured_exact_match", "structured",
        diagnostics={"missing": missing, "mismatched": mismatched},
    )


def evaluate(answer: str, reference: Any, *, answer_type: str = "auto") -> EvaluationResult:
    """Evaluate one answer using a deterministic reference contract."""
    contract = _parse_contract(reference)
    if contract is None:
        return _result("indeterminate", None, 0.0, "reference_not_structured",
                       answer_type if answer_type != "auto" else "unknown",
                       diagnostics={"reason": "reference must be a JSON/object contract"})
    detected = _text(contract.get("answer_type", answer_type)).lower()
    if detected == "auto":
        detected = "number" if _accepted_texts(contract) and all(
            _to_float(item) is not None for item in _accepted_texts(contract)
        ) else "free_text"
    if detected == "number":
        return _evaluate_number(_text(answer), contract)
    if detected == "short_text":
        return _evaluate_short_text(_text(answer), contract)
    if detected == "free_text":
        return _evaluate_free_text(_text(answer), contract)
    if detected == "interval":
        return _evaluate_interval(_text(answer), contract)
    if detected == "label":
        return _evaluate_label(_text(answer), contract)
    if detected == "structured":
        return _evaluate_structured(answer, contract)
    return _result("indeterminate", None, 0.0, "unknown_answer_type",
                   detected, diagnostics={"reason": "unsupported answer_type"})


def summarize(results: Iterable[EvaluationResult]) -> dict[str, Any]:
    """Aggregate results without hiding indeterminate cases.

    Accuracy is computed only over determinate cases.  The Wilson interval is
    reported instead of a misleading normal approximation for small samples.
    """
    rows = list(results)
    determinate = [row for row in rows if row.verdict in ("correct", "incorrect")]
    correct = sum(row.verdict == "correct" for row in determinate)
    n = len(determinate)
    accuracy = correct / n if n else None
    if n:
        z = 1.959963984540054
        denominator = 1 + z * z / n
        centre = (accuracy + z * z / (2 * n)) / denominator
        margin = z * math.sqrt((accuracy * (1 - accuracy) / n) +
                               (z * z / (4 * n * n))) / denominator
        interval = [round(max(0.0, centre - margin), 6),
                    round(min(1.0, centre + margin), 6)]
    else:
        interval = None
    return {
        "n_total": len(rows),
        "n_determinate": n,
        "n_indeterminate": len(rows) - n,
        "n_correct": correct,
        "accuracy": round(accuracy, 6) if accuracy is not None else None,
        "accuracy_wilson_95": interval,
        "indeterminate_rate": round(
            (len(rows) - n) / len(rows), 6) if rows else None,
        "mean_confidence": round(
            sum(row.confidence for row in rows) / len(rows), 6) if rows else None,
    }
