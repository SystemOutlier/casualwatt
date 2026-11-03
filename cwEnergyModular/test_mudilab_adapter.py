from mudilab_adapter import evaluate_case, load_case


def _case(task_type="cond_prob"):
    return load_case({
        "task_id": "CP1",
        "task_type": task_type,
        "expected_label": {
            "cond_prob": "backward_reasoning",
            "counterfactual": "counterfactual",
            "coherence": "coherence",
        }.get(task_type, "backward_reasoning"),
        "expected_probability": "0.2117494190",
        "expected_lower_graph": "0.0827",
        "expected_upper_graph": "0.2396",
        "target_variable": "Age",
        "target_state": "Senior",
        "evidence_json": '{"DrivQuality": "Normal"}',
        "intervention_json": '{"RiskAversion": "Cautious"}',
    })


def test_conditional_probability_requires_all_stages():
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
        tool_calls=[{"name": "cau_inference"}],
    )
    assert result.end_to_end == "correct"


def test_missing_tool_call_invalidates_end_to_end():
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
    )
    assert result.end_to_end == "incorrect"


def test_counterfactual_compares_both_bounds():
    result = evaluate_case(
        _case("counterfactual"), label="counterfactual",
        translation={"input": {"RiskAversion": "Cautious"},
                     "output": {"Age": "Senior"}},
        output="The answer is between 0.0827 and 0.2396",
        tool_calls=[{"name": "cau_inference"}],
    )
    assert result.output.verdict == "correct"
