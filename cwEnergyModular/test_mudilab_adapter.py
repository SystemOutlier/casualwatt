from mudilab_adapter import evaluate_case, load_case


def _case(task_type="cond_prob", expected_decision=""):
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
        "expected_decision": expected_decision,
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
        tool_calls=[{"name": "cau_inference", "success": True, "result": {"ok": True}}],
    )
    assert result.end_to_end == "correct"


def test_missing_tool_call_invalidates_end_to_end():
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
    )
    assert result.end_to_end == "indeterminate"


def test_counterfactual_compares_both_bounds():
    result = evaluate_case(
        _case("counterfactual"), label="counterfactual",
        translation={"input": {"RiskAversion": "Cautious"},
                     "output": {"Age": "Senior"}},
        output="The answer is between 0.0827 and 0.2396",
        tool_calls=[{"name": "cau_inference"}],
    )
    assert result.output.verdict == "correct"


def test_unverified_tool_call_is_indeterminate():
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
        tool_calls=[{"name": "cau_inference"}],
    )
    assert result.tool_call_status == "unverified"
    assert result.end_to_end == "indeterminate"


def test_failed_tool_call_is_incorrect():
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
        tool_calls=[{"name": "cau_inference", "success": False}],
    )
    assert result.tool_call_status == "failed"
    assert result.end_to_end == "incorrect"


# Le frasi sono quelle che stampa il tool della relatrice
# (`MUDILAB_run/consegna/tools_corretto.py:448` e `:453`), prese di peso perche'
# il controllo qualitativo e' una ricerca di sottostringa su quel testo: se il
# test ne scrive una paraphrasi, verifica il test e non il controllo.
_FRASE_POSITIVA = ("Evidences are compatible with a single Age of Senior "
                   "with a probability of 0.2117")
_FRASE_NEGATIVA = ("Evidences are NOT strongly compatible with a single Age of Senior "
                   "with a probability of 0.2117")
_TRADUZIONE = {"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}
_CONTATORE_OK = {"read_graph": {"invocazioni": 0, "eccezioni": 0},
                 "cau_inference": {"invocazioni": 1, "eccezioni": 0}}


def test_vocabulary_non_compatibile_reads_the_english_negative():
    """Il ground truth usa `non_compatibile`, il marcatore non si deriva piu'
    dall'ortografia: la riga negata in inglese e' corretta, non `incorrect`.

    Prima del fix il valore veniva mappato con `replace("_", " ")` -> "non
    compatibile", che non puo' comparire in una frase inglese: tutte le 40 righe
    `non_compatibile` del dataset uscivano `incorrect`, 19 delle quali pubblicate
    come giuste.
    """
    result = evaluate_case(
        _case("coherence", expected_decision="non_compatibile"),
        label="coherence", translation=_TRADUZIONE, output=_FRASE_NEGATIVA,
        tool_calls=_CONTATORE_OK,
    )
    assert result.output.verdict == "correct"
    assert result.end_to_end == "correct"


def test_vocabulary_compatible_reads_the_english_positive():
    """Il marcatore positivo `are compatible with` regge la classe `compatible`.

    Il vocabolario reale del dataset e' {`compatible`, `non_compatibile`}
    (20 + 20 task id in `MUDILAB_run/benchmark/benchmark.csv`): il ramo conosceva
    solo i due nomi enum inglesi e per l'altra meta' delle righe di coerenza non
    diceva nulla.
    """
    result = evaluate_case(
        _case("coherence", expected_decision="compatible"),
        label="coherence", translation=_TRADUZIONE, output=_FRASE_POSITIVA,
        tool_calls=_CONTATORE_OK,
    )
    assert result.end_to_end == "correct"


def test_compatible_row_saying_the_negative_is_flagged():
    """`compatible` e' anche dentro `not strongly compatible`: da solo non basta.

    Senza la guardia sul negativo una riga attesa positiva la cui risposta dice
    l'opposto passa per buona: sulle righe registrate il controllo taceva su 24
    righe (12 task id x 3 ripetizioni) per questa identica ragione.
    """
    result = evaluate_case(
        _case("coherence", expected_decision="compatible"),
        label="coherence", translation=_TRADUZIONE, output=_FRASE_NEGATIVA,
        tool_calls=_CONTATORE_OK,
    )
    assert result.end_to_end == "incorrect"
    assert any("decision mismatch" in note for note in result.notes)


def test_non_compatibile_row_saying_the_positive_is_flagged():
    """Simmetrico: una riga attesa negativa che risponde positiva e' incorrect."""
    result = evaluate_case(
        _case("coherence", expected_decision="non_compatibile"),
        label="coherence", translation=_TRADUZIONE, output=_FRASE_POSITIVA,
        tool_calls=_CONTATORE_OK,
    )
    assert result.end_to_end == "incorrect"


def test_unknown_decision_value_is_indeterminate_not_a_fabricated_marker():
    """Un valore fuori vocabolario non si traduce piu' in un marcatore inventato.

    Il `replace("_", " ")` produceva un marcatore che nessuna risposta puo'
    contenere: la riga diventava `incorrect` per colpa del valutatore.  Ora e'
    `indeterminate` e la nota lo dice.
    """
    result = evaluate_case(
        _case("coherence", expected_decision="forse_compatibile"),
        label="coherence", translation=_TRADUZIONE, output=_FRASE_POSITIVA,
        tool_calls=_CONTATORE_OK,
    )
    assert result.end_to_end == "indeterminate"
    assert any("vocabulary not recognised" in note for note in result.notes)


def test_coherence_row_without_output_skips_the_decision_check():
    """Nessuna risposta = niente marcatore da cercare: la riga resta `indeterminate`
    per il gate, non viene punita due volte dal controllo qualitativo."""
    result = evaluate_case(
        _case("coherence", expected_decision="compatible"),
        label="coherence", translation=_TRADUZIONE, output="",
        tool_calls=_CONTATORE_OK,
    )
    assert result.output.verdict == "indeterminate"
    assert result.end_to_end == "indeterminate"
    assert not any("decision mismatch" in note for note in result.notes)


def test_counter_dict_tool_calls_is_read_as_execution_proof():
    """`run_query.py:188-193` scrive un dict con chiavi italiane, non una lista.

    L'adapter iterava il dict e otteneva le chiavi (stringhe), quindi
    `isinstance(call, Mapping)` era falso per ogni voce: `matching_calls` vuoto,
    stato `missing`, e 321 run su 321 fuori misura perche' il record non era
    leggibile -- non perche' il tool fosse fallito.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117", tool_calls=_CONTATORE_OK,
    )
    assert result.tool_call_status == "success"
    assert result.tool_call_valid is True
    assert result.end_to_end == "correct"


def test_counter_dict_with_exceptions_is_failed():
    """`eccezioni > 0` e' la condizione negata di `tool_ok` (`run_query.py:178`)."""
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117",
        tool_calls={"cau_inference": {"invocazioni": 2, "eccezioni": 1}},
    )
    assert result.tool_call_status == "failed"
    assert result.end_to_end == "incorrect"


def test_counter_dict_with_zero_invocations_is_missing():
    """Zero invocazioni significa che il numero non viene dal tool: niente misura."""
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117",
        tool_calls={"cau_inference": {"invocazioni": 0, "eccezioni": 0}},
    )
    assert result.tool_call_status == "missing"
    assert result.end_to_end == "indeterminate"


def test_recorded_step_with_answer_text_proves_execution():
    """`run_orchestrato.py:468-488` aggiunge il passo solo dopo il ritorno.

    La eccezione finisce in `errore` senza passo, quindi un passo
    `cau_inference` con il testo della risposta e' la prova che il call e'
    avvenuto; e' la forma che i run pubblicati contengono davvero.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117",
        tool_calls=[{"step": "translator", "text": "..."},
                    {"step": "cau_inference", "text": _FRASE_POSITIVA}],
    )
    assert result.tool_call_status == "success"


def test_arguments_of_the_call_are_declared_not_recorded():
    """La prova di esecuzione non copre gli argomenti: lo stato va dichiarato.

    Il record contiene il testo del tool, non i suoi input.  Dire `success` e
    tacere avrebbe presented come verificato un argomento mai letto.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117", tool_calls=_CONTATORE_OK,
    )
    assert any("arguments: not recorded" in note for note in result.notes)


def test_empty_output_is_indeterminate_not_incorrect():
    """Il gate ferma il run prima del passo causale: una risposta vuota non e'
    un numero sbagliato.

    `number_no_answer` a 0.99 fundeva i fallimenti di acquisizione con gli errori
    del modello e spostava il denominatore del J/corretta per la ragione sbagliata
    (sui run registrati: 105 righe).
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="", tool_calls=_CONTATORE_OK,
    )
    assert result.output.verdict == "indeterminate"
    assert result.output.method == "number_answer_absent"
    assert result.end_to_end == "indeterminate"


def test_empty_counterfactual_output_is_indeterminate():
    """Stessa regola sul ramo controfattuale, dove il contratto e' un intervallo
    (`interval_not_found` contava le 19 righe gate come `incorrect`)."""
    result = evaluate_case(
        _case("counterfactual"), label="counterfactual",
        translation={"input": {"RiskAversion": "Cautious"}, "output": {"Age": "Senior"}},
        output="", tool_calls=_CONTATORE_OK,
    )
    assert result.output.verdict == "indeterminate"
    assert result.output.method == "interval_answer_absent"
    assert result.end_to_end == "indeterminate"