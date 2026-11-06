"""Test del McNemar appaiato."""


from evaluation_runner import paired_mcnemar, record_verdict


def test_basic_table_counts():
    r = paired_mcnemar([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert r["a"] == 2
    assert r["b"] == 1
    assert r["c"] == 1
    assert r["d"] == 1
    assert r["discordant"] == 2
    assert r["n_determinate"] == 5


def test_indecis_when_no_discordant():
    r = paired_mcnemar([1, 1, 0, 0], [1, 1, 0, 0])
    assert r["indecis"] is True
    assert r["discordant"] == 0
    assert r["p_value_exact"] == 1.0


def test_small_discordant_uses_exact():
    # discordant < 10 → chi2 non calcolato
    r = paired_mcnemar([1, 1, 0, 0, 1], [1, 0, 1, 0, 1] * 1)
    assert r["chi2"] is None
    assert r["p_value_chi2"] is None


def test_large_discordant_computes_chi2():
    xs = [1] * 15 + [0] * 15
    ys = [0] * 15 + [1] * 15
    r = paired_mcnemar(xs, ys)
    assert r["discordant"] == 30
    assert r["chi2"] is not None
    assert r["p_value_chi2"] is not None
    assert r["p_value_exact"] is not None


def test_indeterminate_excluded_and_counted():
    # "correct"/"incorrect" vs None-like
    r = paired_mcnemar([1, 1, "indeterminate", "missing", None], [1, 1, 1, 1, 1])
    assert r["n_determinate"] == 2
    assert r["n_excluded"] == 3
    assert r["n_total"] == 5
    assert r["excluded_by_reason"]  # popolato


def test_length_mismatch_raises():
    try:
        paired_mcnemar([1, 0], [1])
    except ValueError:
        return
    raise AssertionError("deve sollevare ValueError")


def test_no_chance_correction():
    xs = [1] * 12 + [0] * 12
    ys = [0] * 12 + [1] * 12
    r = paired_mcnemar(xs, ys, correction=False)
    assert r["chi2"] is not None


def test_record_verdict_coercion():
    from evaluation_runner import _coerce_to_determined
    va = [_coerce_to_determined(v) for v in (1, 0, None)]
    vb = [_coerce_to_determined(v) for v in (1, 1, 0)]
    assert va == [1, 0, None]
    assert vb == [1, 1, 0]
