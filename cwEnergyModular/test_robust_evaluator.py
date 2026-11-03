import json

from robust_evaluator import evaluate, summarize


def test_number_requires_unambiguous_or_marked_final_answer():
    reference = {"answer_type": "number", "accepted_answers": ["21"]}
    assert evaluate("La risposta: 21", reference).verdict == "correct"
    assert evaluate("5 * 5 = 25, poi 25 - 4 = 21", reference).verdict == "indeterminate"
    assert evaluate("5 * 5 = 25. La risposta: 25", reference).verdict == "incorrect"


def test_number_tolerance_is_explicit():
    reference = {
        "answer_type": "number",
        "accepted_answers": ["0.212"],
        "absolute_tolerance": 0.001,
    }
    assert evaluate("answer: 0,2124", reference).verdict == "correct"
    assert evaluate("answer: 0,22", reference).verdict == "incorrect"


def test_short_text_uses_token_boundaries_and_aliases():
    reference = {"answer_type": "short_text", "accepted_answers": ["Atene", "Athens"]}
    assert evaluate("La capitale è Athens.", reference).verdict == "correct"
    assert evaluate("La capitale è Ateneo.", reference).verdict == "incorrect"


def test_free_text_requires_declared_facts():
    reference = {
        "answer_type": "free_text",
        "required_facts": ["Roma", "Lazio"],
        "forbidden_facts": ["Firenze"],
        "minimum_required_facts": 2,
        "fact_match_mode": "literal",
    }
    assert evaluate("Roma si trova nel Lazio.", reference).verdict == "correct"
    assert evaluate("Roma è in Toscana.", reference).verdict == "incorrect"
    assert evaluate("Roma è importante.", reference).verdict == "incorrect"


def test_unstructured_legacy_reference_is_indeterminate():
    assert evaluate("Roma", "Roma").verdict == "indeterminate"
    result = evaluate("Roma", json.dumps({
        "answer_type": "short_text", "accepted_answers": ["Roma"]
    }))
    assert result.verdict == "correct"


def test_summary_reports_indeterminate_cases_and_wilson_interval():
    rows = [
        evaluate("21", {"answer_type": "number", "accepted_answers": ["21"]}),
        evaluate("20", {"answer_type": "number", "accepted_answers": ["21"]}),
        evaluate("21 20", {"answer_type": "number", "accepted_answers": ["21"]}),
    ]
    summary = summarize(rows)
    assert summary["n_total"] == 3
    assert summary["n_determinate"] == 2
    assert summary["n_indeterminate"] == 1
    assert summary["accuracy"] == 0.5
    assert summary["accuracy_wilson_95"][0] >= 0


def test_free_text_negation_is_indeterminate_not_correct():
    reference = {
        "answer_type": "free_text",
        "required_facts": ["Roma", "Lazio"],
        "minimum_required_facts": 2,
        "fact_match_mode": "literal",
    }
    result = evaluate("Roma non si trova nel Lazio.", reference)
    assert result.verdict == "indeterminate"
    assert result.diagnostics["semantic_entailment_verified"] is False


def test_non_finite_numeric_reference_is_indeterminate():
    result = evaluate("answer: 1", {
        "answer_type": "number", "accepted_answers": ["NaN"]
    })
    assert result.verdict == "indeterminate"
    assert result.method == "invalid_reference_contract"


def test_invalid_free_text_contract_requires_explicit_literal_mode():
    result = evaluate("Roma è nel Lazio", {
        "answer_type": "free_text", "required_facts": ["Roma", "Lazio"]
    })
    assert result.verdict == "indeterminate"
    assert "fact_match_mode='literal'" in result.diagnostics["validation_errors"][0]


def test_auto_contract_inference_remains_supported():
    assert evaluate("42", {"accepted_answers": ["42"]}).verdict == "correct"