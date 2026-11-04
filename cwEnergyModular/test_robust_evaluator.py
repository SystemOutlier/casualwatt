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

def test_scalar_reference_and_explicit_answer_type_are_supported():
    assert evaluate("21", {"accepted_answers": 21}).verdict == "correct"
    assert evaluate("Athens", {"accepted_answers": ["Athens"]},
                    answer_type="short_text").verdict == "correct"


def test_zero_scalare_e_un_riferimento_pieno_non_un_contratto_manco():
    """Lo zero di un contatore e' un valore atteso, non un'assenza.

    `values is None` e `if not values` non sono la stessa condizione, e qui fa la
    differenza: `{"accepted_answers": 0}` deve restare un contratto `number`
    valido e produrre `incorrect` su una risposta diversa, non degradare a
    `number_contract_missing`/`indeterminate` perche' il falso di `0` cancellerebbe
    la misura di un run che una verita' ce l'ha.
    """
    risultato = evaluate("21", {"accepted_answers": 0})
    assert risultato.verdict == "incorrect"
    assert risultato.answer_type == "number"
    assert risultato.method == "number_tolerance_match"


def test_stringa_scalsa_non_diventa_short_text_per_comodita():
    """Un `accepted_answers` a stringa resta un contratto free_text da dichiarare.

    La normalizzazione del caso `auto` accetta scalari numerici perche' il tipo si
    deduce dal valore; una stringa no, perche' `short_text` e `free_text` chiedono
    due cose diverse (una corrispondenza di token contro fatti dichiarati con
    `fact_match_mode='literal'`) e la scelta non compete al valutatore: senza
    fatti dichiarati l'esito e' `invalid_reference_contract`, dichiarato.
    """
    risultato = evaluate("Athens", {"accepted_answers": "Athens"})
    assert risultato.verdict == "indeterminate"
    assert risultato.method == "invalid_reference_contract"


def test_booleano_scalare_non_e_un_numero():
    """`True` e `False` sono `int` in Python, ma non sono un joule atteso.

    Il ramo `auto` normalizza `isinstance(values, (str, int, float))`, e il bool
    ci cade dentro: va bene solo perche' `_to_float("True")` non e' un numero,
    quindi il contratto scende a `free_text` e viene fermato come non dichiarabile
    invece di diventare un confronto numerico contro 1.
    """
    risultato = evaluate("1", {"accepted_answers": True})
    assert risultato.verdict == "indeterminate"
    assert risultato.method == "invalid_reference_contract"


def test_absent_answer_is_indeterminate_for_number_and_interval():
    """Una risposta vuota non e' un numero sbagliato: e' un run che non ha prodotto
    nulla da valutare.

    `incorrect` a confidenza 0.99 funde il fallimento di acquisizione con l'errore
    del modello e sposta il denominatore delle metriche per corretto; un run
    fermato prima del passo causale non puo' essere contato fra gli sbagliati.
    """
    numero = evaluate("", {"answer_type": "number", "accepted_answers": ["0.2"]})
    intervallo = evaluate("", {"answer_type": "interval", "lower": 0.1, "upper": 0.3})
    assert numero.verdict == "indeterminate"
    assert numero.method == "number_answer_absent"
    assert intervallo.verdict == "indeterminate"
    assert intervallo.method == "interval_answer_absent"


def test_non_empty_answer_without_a_number_stays_incorrect():
    """Il floor resta `incorrect` per una risposta che c'e' ma non risponde: la
    regola nuova copre l'assenza, non l'incoerenza."""
    assert evaluate("non so", {"answer_type": "number",
                               "accepted_answers": ["0.2"]}).verdict == "incorrect"