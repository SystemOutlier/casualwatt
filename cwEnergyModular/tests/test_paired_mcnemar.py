"""Test del McNemar appaiato: costruzione della tabella di concordanza,
selezione tra binomiale esatto e chi² con correzione di continuità,
gestione degli esclusi, riduzione a una coppia per task e intervallo
di Newcombe per la differenza di accuratezze."""


from evaluation_runner import paired_mcnemar, record_verdict


def test_basic_table_counts():
    """Verifica il conteggio corretto delle quattro celle (a, b, c, d)
    e del totale discordanti per una tabella 2x2 nota."""
    r = paired_mcnemar([1, 1, 0, 0, 1], [1, 0, 1, 0, 1])
    assert r["a"] == 2
    assert r["b"] == 1
    assert r["c"] == 1
    assert r["d"] == 1
    assert r["discordant"] == 2
    assert r["n_determinate"] == 5


def test_indecis_when_no_discordant():
    """Se b+c=0 la tabella è priva di discordanti: il test deve dichiarare
    'indecis' con p_value_exact=1.0 e chi² non calcolato."""
    r = paired_mcnemar([1, 1, 0, 0], [1, 1, 0, 0])
    assert r["indecis"] is True
    assert r["discordant"] == 0
    assert r["p_value_exact"] == 1.0


def test_small_discordant_uses_exact():
    """Per discordanti < 10 il test esatto binomiale è l'unico valido:
    chi² e p_value_chi2 devono essere None."""
    r = paired_mcnemar([1, 1, 0, 0, 1], [1, 0, 1, 0, 1] * 1)
    assert r["chi2"] is None
    assert r["p_value_chi2"] is None


def test_large_discordant_computes_chi2():
    """Per discordanti >= 10 il chi² con correzione di continuità deve
    essere calcolato insieme al p-value esatto."""
    xs = [1] * 15 + [0] * 15
    ys = [0] * 15 + [1] * 15
    r = paired_mcnemar(xs, ys)
    assert r["discordant"] == 30
    assert r["chi2"] is not None
    assert r["p_value_chi2"] is not None
    assert r["p_value_exact"] is not None


def test_indeterminate_excluded_and_counted():
    """I verdetti 'indeterminate', 'missing' e None devono essere esclusi
    dal conteggio determinato, conteggiati in n_excluded e dettagliati per
    ragione in excluded_by_reason."""
    r = paired_mcnemar([1, 1, "indeterminate", "missing", None], [1, 1, 1, 1, 1])
    assert r["n_determinate"] == 2
    assert r["n_excluded"] == 3
    assert r["n_total"] == 5
    assert r["excluded_by_reason"]  # popolato


def test_length_mismatch_raises():
    """Lunghezze diverse tra le due liste di verdetti devono sollevare
    ValueError: la McNemar richiede coppie perfettamente appaiate."""
    try:
        paired_mcnemar([1, 0], [1])
    except ValueError:
        return
    raise AssertionError("deve sollevare ValueError")


def test_no_chance_correction():
    """Disattivando la correzione (correction=False) il chi² deve essere
    calcolato senza continuità, distinguendo il caso 'no' da 'yes'."""
    xs = [1] * 12 + [0] * 12
    ys = [0] * 12 + [1] * 12
    r = paired_mcnemar(xs, ys, correction=False)
    assert r["chi2"] is not None


def test_correction_applied_distinguishes_the_three_states():
    """`correction_applied` dice cosa e' entrato nella formula, non il flag.

    Con b+c >= 10 la correzione di continuita' entra nel chi2 quando e' chiesta
    ("yes") e non entra quando e' disattivata ("no"): la stessa tabella deve
    dichiarare due cose diverse. Con b+c < 10 il chi2 non esiste e il test e'
    il binomiale esatto, quindi non c'e' nulla da correggere
    ("not_applicable") -- "no" direbbe che l'utente l'ha spenta. Un valore
    costante non distingue i tre casi.
    """
    xs = [1] * 12 + [0] * 12
    ys = [0] * 12 + [1] * 12
    corrected = paired_mcnemar(xs, ys)
    uncorrected = paired_mcnemar(xs, ys, correction=False)
    assert corrected["chi2"] is not None
    assert uncorrected["chi2"] is not None
    assert corrected["chi2"] != uncorrected["chi2"]
    assert corrected["correction_applied"] == "yes"
    assert uncorrected["correction_applied"] == "no"
    small = paired_mcnemar([1, 1, 0], [1, 0, 1])
    assert small["chi2"] is None
    assert small["correction_applied"] == "not_applicable"


def test_record_verdict_coercion():
    from evaluation_runner import _coerce_to_determined
    va = [_coerce_to_determined(v) for v in (1, 0, None)]
    vb = [_coerce_to_determined(v) for v in (1, 1, 0)]
    assert va == [1, 0, None]
    assert vb == [1, 1, 0]


def test_paired_summary_reduces_to_one_pair_per_task():
    """La riduzione a una coppia per task e' dichiarata e conteggiata.

    Tre righe appartengono al task T1: tenerle tutte fingerebbe tre prove
    indipendenti, e la McNemar conterebbe la stessa richiesta piu' volte. Con la
    regola `first` resta la prima coppia; `n_tasks_with_replicates` dice quante
    ne sono state scartate e `n_without_task` conta le righe senza identita'
    invece di perderle in silenzio.
    """
    from evaluation_runner import paired_summary
    a = [1, 0, 1, 0, 1]
    b = [0, 0, 1, 1, 0]
    ids = ["T1", "T1", "T1", "T2", None]
    result = paired_summary(a, b, ids)
    assert result["n_tasks"] == 2
    assert result["n_without_task"] == 1
    assert result["n_tasks_with_replicates"] == 1
    assert result["n_determinate"] == 2
    # coppie tenute: T1 (1 vs 0), T2 (0 vs 1) -> b = c = 1, a = d = 0
    assert (result["a"], result["b"], result["c"], result["d"]) == (0, 1, 1, 0)


def test_paired_summary_rejects_undeclared_reduction():
    """Una regola non dichiarata non si applica di nascosto.

    La riduzione decide la matrice: un nome sconosciuto deve fallire, non
    ricadere su `first` con l'aria di essere stato rispettato.
    """
    from evaluation_runner import paired_summary
    try:
        paired_summary([1], [1], ["T1"], reduction="last")
    except ValueError:
        return
    raise AssertionError("deve sollevare ValueError")


def test_delta_ci_newcombe_reference_example():
    """Riproduce l'esempio del metodo 10 con il phi corretto.

    La tabella [[10, 5], [2, 20]] (a=10, b=5, c=2, d=20) ha limiti attesi
    -0.0643926050711 e 0.2211160178958: fissarli impedisce di tornare alla
    somma in quadratura dei marginali, che ignora l'appaiamento e con il phi
    non corretto darebbe un intervallo diverso.
    """
    xs = [1] * 10 + [1] * 5 + [0] * 2 + [0] * 20
    ys = [1] * 10 + [0] * 5 + [1] * 2 + [0] * 20
    result = paired_mcnemar(xs, ys)
    assert result["delta_ci_newcombe"] == [-0.064393, 0.221116]


def test_delta_ci_depends_on_pairing_not_only_marginals():
    """Stessi marginali e phi diverso devono dare intervalli diversi.

    (60, 10, 2, 28) e (55, 15, 7, 23) hanno a+b=70 e a+c=62 su n=100: le due
    proporzioni marginali coincidono, cambia solo l'appaiamento. Un intervallo
    valido dipende da b e c; la quadratura dei marginali dava lo stesso
    risultato a entrambe le tabelle.
    """
    xs1 = [1] * 60 + [1] * 10 + [0] * 2 + [0] * 28
    ys1 = [1] * 60 + [0] * 10 + [1] * 2 + [0] * 28
    xs2 = [1] * 55 + [1] * 15 + [0] * 7 + [0] * 23
    ys2 = [1] * 55 + [0] * 15 + [1] * 7 + [0] * 23
    first = paired_mcnemar(xs1, ys1)
    second = paired_mcnemar(xs2, ys2)
    assert first["delta_acc"] == second["delta_acc"] == 0.08
    assert first["delta_ci_newcombe"] == [0.011009, 0.148316]
    assert second["delta_ci_newcombe"] == [-0.012714, 0.170744]
    assert first["delta_ci_newcombe"] != second["delta_ci_newcombe"]
