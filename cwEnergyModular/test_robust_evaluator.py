import json

import pytest

from robust_evaluator import evaluate, summarize


def test_number_requires_unambiguous_or_marked_final_answer():
    """Un numero in mezzo al ragionamento non e' la risposta: serve un'unica
    occorrenza, oppure un marcatore finale dichiarato.

    `5 * 5 = 25, poi 25 - 4 = 21` contiene due numeri e nessun marcatore, quindi non
    esiste un criterio per dire quale sia la risposta -> `indeterminate`; con `La
    risposta: 21` il marcatore toglie l'ambiguita' e l'esito e' `correct`, mentre
    `La risposta: 25` e' `incorrect`. Senza questa regola l'ultimo numero trovato
    diventerebbe la risposta e un passaggio intermedio verrebbe contato come errore
    (o come successo).
    """
    reference = {"answer_type": "number", "accepted_answers": ["21"]}
    assert evaluate("La risposta: 21", reference).verdict == "correct"
    assert evaluate("5 * 5 = 25, poi 25 - 4 = 21", reference).verdict == "indeterminate"
    assert evaluate("5 * 5 = 25. La risposta: 25", reference).verdict == "incorrect"


def test_number_tolerance_is_explicit():
    """Il contratto puo' sostituire il default abs=1e-9, rel=1e-6 esplicitamente.

    Con absolute_tolerance=0.001 lo scarto 0.0004 passa e 0.008 no: il
    confronto usa il massimo fra budget assoluto e relativo, non la somma.
    """
    reference = {
        "answer_type": "number",
        "accepted_answers": ["0.212"],
        "absolute_tolerance": 0.001,
    }
    assert evaluate("answer: 0,2124", reference).verdict == "correct"
    assert evaluate("answer: 0,22", reference).verdict == "incorrect"


def test_short_text_uses_token_boundaries_and_aliases():
    """`short_text` confronta token interi contro gli alias dichiarati, non sottostringhe.

    `Athens` e' un alias di `Atene`, quindi `La capitale è Athens.` e' corretta;
    `Ateneo` contiene la sottostringa `Atene` ma e' un'altra parola, e un match
    ingenuo la conterebbe come giusta. Il test blocca entrambe le direzioni: alias
    si', prefisso no.
    """
    reference = {"answer_type": "short_text", "accepted_answers": ["Atene", "Athens"]}
    assert evaluate("La capitale è Athens.", reference).verdict == "correct"
    assert evaluate("La capitale è Ateneo.", reference).verdict == "incorrect"


def test_free_text_requires_declared_facts():
    """`free_text` si valuta contro i fatti dichiarati, non contro una somiglianza.

    Servono tutti e due i fatti richiesti e nessuno dei vietati: `Roma si trova nel
    Lazio` passa, `Roma è in Toscana` manca `Lazio`, `Roma è importante` ne
    contiene uno solo. Il minimo e' un campo del contratto
    (`minimum_required_facts`), non una costante del valutatore, perche' la soglia
    appartiene a chi ha scritto il riferimento.
    """
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
    """Un riferimento non strutturato non e' un contratto: il tipo non si inventa.

    La stringa `"Roma"` non dice se e' un numero, un `short_text` o un `free_text`,
    e indovinare sarebbe la stessa cosa che assumere la risposta giusta; lo stesso
    contenuto in JSON con `answer_type` dichiarato produce `correct`. Il test separa
    la mancanza di contratto (`indeterminate`) dalla risposta sbagliata.
    """
    assert evaluate("Roma", "Roma").verdict == "indeterminate"
    result = evaluate("Roma", json.dumps({
        "answer_type": "short_text", "accepted_answers": ["Roma"]
    }))
    assert result.verdict == "correct"


def test_summary_reports_indeterminate_cases_and_wilson_interval():
    """L'accuratezza si calcola sui determinati, ma gli indeterminati restano contati.

    Con una risposta giusta, una sbagliata e una ambigua l'accuratezza e' 0.5 su
    `n_determinate = 2`, e `n_indeterminate = 1` resta nel riepilogo: escluderli dal
    denominatore senza esporli permetterebbe di alzare l'accuratezza fermando righe
    senza che il numero lo dica. L'intervallo di Wilson accompagna la proporzione
    invece di lasciarla nuda.
    """
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


def test_task_ids_pongono_l_incertezza_a_livello_di_task():
    """Quattro righe da due task: la Wilson le legge come quattro tentativi
    indipendenti, il bootstrap a cluster no.

    Task A = (correct, incorrect), task B = (correct, correct): accuratezza 0,75 su
    `n_determinate = 4`, Wilson `[0,301; 0,954]`. Ricampionando i task ogni
    ricampiono vale 0,5 (due A), 0,75 (A+B) o 1,0 (due B), quindi il 2,5 e il 97,5
    per cento cadono su `[0,5; 1,0]`: il bordo inferiore SALE perche' la
    variabilita' entro il task non e' variabilita' fra task. `n_effective_tasks`
    dice quanti sono davvero gli esperimenti.
    """
    reference = {"answer_type": "number", "accepted_answers": ["21"]}
    rows = [
        evaluate("La risposta: 21", reference),
        evaluate("La risposta: 20", reference),
        evaluate("La risposta: 21", reference),
        evaluate("La risposta: 21", reference),
    ]
    summary = summarize(rows, task_ids=["A", "A", "B", "B"])
    assert summary["n_determinate"] == 4
    assert summary["accuracy"] == 0.75
    assert summary["n_effective_tasks"] == 2
    assert summary["accuracy_cluster_bootstrap_95"] == [0.5, 1.0]
    assert summary["accuracy_cluster_bootstrap_95"][0] > summary["accuracy_wilson_95"][0]


def test_senza_task_ids_l_intervallo_di_cluster_e_dichiarato_assente():
    """`EvaluationResult` non porta l'identita' del task: senza `task_ids` il
    cluster non esiste e l'assenza va scritta, non sostituita da un bootstrap per riga."""
    reference = {"answer_type": "number", "accepted_answers": ["21"]}
    rows = [evaluate("La risposta: 21", reference),
            evaluate("La risposta: 20", reference)]
    summary = summarize(rows)
    assert summary["n_effective_tasks"] is None
    assert summary["accuracy_cluster_bootstrap_95"] is None
    assert "task identity not recorded" in summary["cluster_bootstrap_note"]
    assert summary["accuracy_wilson_95"] is not None


def test_task_ids_disallineati_sono_un_errore_non_un_silenzio():
    """Un accoppiamento storto fra esiti e task attribuirebbe verdetti al task
    sbagliato: fallisce in faccia, non raggruppa a caso."""
    reference = {"answer_type": "number", "accepted_answers": ["21"]}
    rows = [evaluate("La risposta: 21", reference),
            evaluate("La risposta: 20", reference)]
    with pytest.raises(ValueError, match="misaligned pairing"):
        summarize(rows, task_ids=["A"])


def test_free_text_negation_is_indeterminate_not_correct():
    """I fatti presenti in una frase negata non soddisfano il contratto.

    `Roma non si trova nel Lazio` contiene sia `Roma` sia `Lazio`, quindi un
    controllo di sola presenza la dichiarerebbe corretta mentre dice l'opposto;
    senza un verificatore di implicazione semantica l'esito onesto e'
    `indeterminate`, e il diagnostico `semantic_entailment_verified = False` lo
    rende esplicito invece di lasciarlo dedurre.
    """
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
    """Un riferimento `NaN` e' un contratto non valido, non un valore da confrontare.

    `NaN` non e' un numero e ogni confronto con esso e' falso: senza il controllo il
    contratto produrrebbe `incorrect` per costruzione, cioe' una riga punita per un
    errore del dataset. Il test fissa `invalid_reference_contract`, che dice da che
    parte sta il difetto.
    """
    result = evaluate("answer: 1", {
        "answer_type": "number", "accepted_answers": ["NaN"]
    })
    assert result.verdict == "indeterminate"
    assert result.method == "invalid_reference_contract"


def test_invalid_free_text_contract_requires_explicit_literal_mode():
    """Il modo di confronto si dichiara: senza `fact_match_mode` il contratto e' invalido.

    Un `free_text` i cui fatti potrebbero essere confrontati in modi diversi
    (letterale, lemma, implicazione) non e' riproducibile finche' il modo non e'
    scritto; il messaggio di validazione nomina la chiave mancante, cosi' chi scrive
    il riferimento sa cosa aggiungere invece di vedere un fallimento senza causa.
    """
    result = evaluate("Roma è nel Lazio", {
        "answer_type": "free_text", "required_facts": ["Roma", "Lazio"]
    })
    assert result.verdict == "indeterminate"
    assert "fact_match_mode='literal'" in result.diagnostics["validation_errors"][0]


def test_auto_contract_inference_remains_supported():
    """Un contratto minimo `{accepted_answers: [...]}` continua a valere: il tipo si
    inferisce, l'inferenza non e' deprecata.

    Il dataset storico non dichiara `answer_type` su tutte le righe; togliere
    l'inferenza farebbe degradare a `indeterminate` righe con un riferimento
    numerico inequivocabile. Il test difende la compatibilita' all'indietro: la
    regola nuova chiede un contratto valido, non un formato nuovo.
    """
    assert evaluate("42", {"accepted_answers": ["42"]}).verdict == "correct"

def test_scalar_reference_and_explicit_answer_type_are_supported():
    """Lo scalare `21` e il tipo dichiarato sono due forme dello stesso contratto.

    Un `accepted_answers` scalare non e' una lista ma e' comunque un riferimento
    univoco, quindi vale; `answer_type = "short_text"` scritto a mano deve vincere
    sull'inferenza, altrimenti il campo esplicito non servirebbe a nulla. Il test
    copre entrambe le normalizzazioni sullo stesso percorso di `evaluate`.
    """
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


@pytest.mark.parametrize("reference", [
    "3 blarg", "3 J/kg", "NaN", "+inf", "1e309", "1e-9999", "1e+", True,
])
def test_b1_numeric_contract_rejects_unsupported_values(reference):
    """La validazione usa lo stesso scalare dell'estrazione: nessun prefisso o unita' cancellata."""
    result = evaluate("3", {"answer_type": "number", "accepted_answers": [reference]})
    assert result.verdict == "indeterminate"
    assert result.method == "invalid_reference_contract"


@pytest.mark.parametrize("key", ["absolute_tolerance", "relative_tolerance"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, "1 J", "1e+"])
def test_b1_numeric_tolerances_are_finite_unitless_nonnegative(key, value):
    """Un budget malformato non deve rendere ogni risposta corretta ne' provocare eccezioni."""
    result = evaluate("3", {"answer_type": "number", "accepted_answers": [3], key: value})
    assert result.method == "invalid_reference_contract"


def test_b1_robust_default_budget_is_unchanged():
    """Per |GT|<1 resta scala=1 e max(abs,rel*scala); il bordo robusto e' inclusivo."""
    from robust_evaluator import _numeric_match
    reference = {"answer_type": "number", "accepted_answers": [0]}
    at_edge = evaluate("1e-6", reference)
    assert at_edge.verdict == "correct"
    assert at_edge.diagnostics["absolute_tolerance"] == 1e-9
    assert at_edge.diagnostics["relative_tolerance"] == 1e-6
    assert evaluate("1.001e-6", reference).verdict == "incorrect"
    assert _numeric_match(2.25, 2, 0, 0.125) is True
    assert _numeric_match(0.00015, 0, 0.0001, 0.0001) is False
    assert _numeric_match(float("inf"), 3, 1e-9, 1e-6) is False


@pytest.mark.parametrize("text", [
    "between +8.27e-2 and 2.396E-1",
    "from .0827 to +,2396", "between 8,27E-2 and .2396",
], ids=["segni-ed-esponenti", "virgola-iniziale", "virgola-decimale"])
def test_b1_interval_scientific_notation_preserves_both_bounds(text):
    """L'esponente appartiene al limite intero: entrambi gli estremi devono coincidere."""
    reference = {"answer_type": "interval", "lower": 0.0827, "upper": 0.2396,
                 "absolute_tolerance": 0.00005 + 1e-12, "relative_tolerance": 0}
    result = evaluate(text, reference)
    assert result.verdict == "correct"
    assert result.diagnostics["lower_match"] is True
    assert result.diagnostics["upper_match"] is True
    wrong_upper = text.replace("2396", "2496").replace("2.396", "2.496")
    assert wrong_upper != text
    assert evaluate(wrong_upper, reference).verdict == "incorrect"


@pytest.mark.parametrize("text", [
    "between 8.27e-2 and 2.396e-1 J", "between 8.27e-2 and 2.396e-",
    "between 8.27e-2 and NaN", "between 8.27e-2 and 1e309",
], ids=["unita", "esponente-incompleto", "nan", "overflow"])
def test_b1_interval_does_not_accept_a_partial_upper_bound(text):
    """Un esponente incompleto, non-finito o dimensionale non e' il limite adimensionale atteso."""
    result = evaluate(text, {"answer_type": "interval", "lower": 0.0827, "upper": 0.2396})
    assert result.verdict != "correct"


@pytest.mark.parametrize("task_type", ["cond_prob", "inter", "coherence", "counterfactual"])
def test_b1_mudilab_has_explicit_zero_relative_tolerance(task_type):
    """Il contratto MUDILAB resta meta' del passo stampato +1e-12, senza budget relativo aggiuntivo."""
    from mudilab_adapter import _case_contract, load_case
    case = load_case({"task_id": "B1", "task_type": task_type,
                      "expected_probability": "0.2117494190",
                      "expected_lower_graph": "0.0827", "expected_upper_graph": "0.2396"})
    contract = _case_contract(case)
    assert contract["relative_tolerance"] == 0.0
    decimals = 3 if task_type in ("cond_prob", "inter") else 4
    assert contract["absolute_tolerance"] == 0.5 * 10 ** -decimals + 1e-12
    if task_type == "counterfactual":
        assert evaluate("between .08275 and .23965", contract).verdict == "correct"
        assert evaluate("between .082751 and .2396", contract).verdict == "incorrect"
    else:
        printed = ".212" if decimals == 3 else ".2117"
        wrong = ".211" if decimals == 3 else ".2116"
        assert evaluate(printed, contract).verdict == "correct"
        assert evaluate(wrong, contract).verdict == "incorrect"


# --------------------------------------------------------------------- B2
# Il match testuale di `short_text` e `free_text` usa confini di parola/frase
# sui due lati del confronto. Prima B2 il ramo `free_text` contava sottostringhe
# (`normalize_text(item) in normalized`) e il ramo `short_text` costruiva
# `\b\b` per un alias che si normalizza a vuoto: nel primo caso `Roma` dentro
# `Romania` soddisfava un fatto dichiarato, nel secondo ogni risposta diventava
# corretta. Le flessioni restano distinte: non c'e' stemming, solo punteggiatura
# e accenti normalizzati allo stesso modo su risposta e riferimento.
@pytest.mark.parametrize("answer,accepted", [
    pytest.param("La Romania e' un paese.", "Roma", id="roma-romania"),
    pytest.param("The catalog is here.", "cat", id="cat-catalog"),
    pytest.param("Ateneo", "Atene", id="atene-ateneo"),
])
def test_b2_short_text_non_premia_la_sottostringa(answer, accepted):
    """`Roma` non e' `Romania`: la parola dentro un'altra parola e' un'altra
    parola, e la riga non deve uscire `correct` senza che il fatto ci sia."""
    result = evaluate(answer, {"answer_type": "short_text",
                               "accepted_answers": [accepted]})
    assert result.verdict == "incorrect"
    assert result.matched_answers == ()


@pytest.mark.parametrize("answer,accepted,verdict", [
    pytest.param("Atene.", "Atene", "correct", id="punto-risposta"),
    pytest.param("Atene", "Atene...", "correct", id="punto-riferimento"),
    pytest.param("La capitale e' Atene", "Atene", "correct", id="frase-positiva"),
    pytest.param("cani", "cane", "incorrect", id="cane-cani"),
])
def test_b2_short_text_punteggiatura_simmetrica_flessioni_distinte(answer, accepted, verdict):
    """La punteggiatura ai bordi e' normalizzata sui due lati, quindi non decide
    l'esito; una flessione diversa no, perche' senza stemming `cani` non e'
    `cane` e l'alias esplicito resta l'unico modo per dichiararla equivalente."""
    result = evaluate(answer, {"answer_type": "short_text",
                               "accepted_answers": [accepted]})
    assert result.verdict == verdict


def test_b2_free_text_conta_fatti_come_parole_intere():
    """`Roma` dentro `Romania` non soddisfa il fatto richiesto, `Firenze` dentro
    `Firenzenuova` non viola il fatto vietato: entrambi erano falsi positivi del
    confronto per sottostringa, uno a favore e uno contro il modello. La virgola
    non spezza `Roma` e `Lazio`, che restano due parole intere."""
    reference = {
        "answer_type": "free_text",
        "required_facts": ["Roma", "Lazio"],
        "forbidden_facts": ["Firenze"],
        "minimum_required_facts": 2,
        "fact_match_mode": "literal",
    }
    assert evaluate("La Romania e' nel Lazio.", reference).verdict == "incorrect"
    assert evaluate("Roma, si trova nel Lazio.", reference).verdict == "correct"
    assert evaluate("Roma e' nel Lazio, lontana da Firenzenuova.", reference).verdict == "correct"
    assert evaluate("Roma e' nel Lazio e anche a Firenze.", reference).verdict == "incorrect"


def test_b2_free_text_frase_in_piu_parole_regge_la_punteggiatura():
    """Un fatto in due parole combacia anche quando la risposta lo separa con
    una virgola, perche' la punteggiatura diventa spazio e non unisce ne'
    spezza: `Roma capitale` resta la stessa frase."""
    reference = {"answer_type": "free_text", "required_facts": ["Roma capitale"],
                 "minimum_required_facts": 1, "fact_match_mode": "literal"}
    assert evaluate("Roma, capitale d'Italia.", reference).verdict == "correct"
    assert evaluate("Roma Capitale.", reference).verdict == "correct"


def test_b2_riferimento_normalizzato_vuoto_non_approva_nulla():
    """`...` si normalizza a stringa vuota: `"" in testo` sarebbe vero per ogni
    risposta, quindi non puo' combaciare con nulla. Se nessun alias ha
    contenuto il contratto non e' utilizzabile e l'esito onesto e'
    `indeterminate`, non `correct`; un alias vuoto accanto a uno valido non
    allarga il match.

    Un fatto *richiesto* che si normalizza a vuoto non e' invece soddisfacibile
    per costruzione (nessuna sottostringa da cercare): la riga esce `incorrect`,
    che e' deterministico e non inventa un match. Resta un limite dichiarato del
    contratto scritto male, non un silenzio del valutatore.
    """
    result = evaluate("Qualunque risposta",
                      {"answer_type": "short_text", "accepted_answers": ["..."]})
    assert result.verdict == "indeterminate"
    assert result.method == "short_text_contract_missing"
    reference = {"answer_type": "short_text", "accepted_answers": ["...", "Atene"]}
    assert evaluate("Roma", reference).verdict == "incorrect"
    assert evaluate("Atene.", reference).verdict == "correct"
    degenerate = {"answer_type": "free_text", "required_facts": ["..."],
                  "minimum_required_facts": 1, "fact_match_mode": "literal"}
    assert evaluate("Qualunque risposta", degenerate).verdict == "incorrect"
