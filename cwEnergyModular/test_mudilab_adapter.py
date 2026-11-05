from mudilab_adapter import evaluate_case, load_case


def _case(task_type="cond_prob", expected_decision="",
          expected_probability="0.2117494190"):
    # L'etichetta attesa non e' passata qui: la deriva `load_case` dalla sua
    # tavola interna (cond_prob -> backward_reasoning, inter -> intervention,
    # ...).  Duplicarla nel fixture significava avere due vocabolari, e il secondo
    # era gia' incompleto: `inter` usciva "backward_reasoning" e la tappa
    # dell'etichetta falliva per colpa del fixture, non del valutatore.
    return load_case({
        "task_id": "CP1",
        "task_type": task_type,
        "expected_probability": expected_probability,
        "expected_lower_graph": "0.0827",
        "expected_upper_graph": "0.2396",
        "expected_decision": expected_decision,
        "target_variable": "Age",
        "target_state": "Senior",
        "evidence_json": '{"DrivQuality": "Normal"}',
        "intervention_json": '{"RiskAversion": "Cautious"}',
    })


def test_conditional_probability_requires_all_stages():
    """La trace legacy prova l'esecuzione, non args e adozione: manca una tappa.

    B5 rende questa riga indeterminata senza cambiare il giudizio sul numero;
    test_tool_provenance copre il caso positivo con forwarding registrato.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
        tool_calls=[{"name": "cau_inference", "success": True, "result": {"ok": True}}],
    )
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"


def test_missing_tool_call_invalidates_end_to_end():
    """Senza trace del tool non c'e' prova che il numero venga dal motore causale.

    Un numero corretto scritto senza invocare `cau_inference` puo' essere
    un'ipotesi del modello: la risposta e' giusta ma il percorso non e' quello
    misurato, quindi l'esito e' `indeterminate` e non `correct`.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning",
        translation={"input": {"DrivQuality": "Normal"},
                     "output": {"Age": "Senior"}},
        output="The probability is 0.2117",
    )
    assert result.end_to_end == "indeterminate"


def test_counterfactual_compares_both_bounds():
    """Il controfattuale ha un contratto a intervallo: vanno letti entrambi gli estremi.

    Con `expected_lower_graph = 0.0827` e `expected_upper_graph = 0.2396` una
    risposta che riporta un solo estremo non e' verificabile; il test fissa che la
    risposta con i due valori produce `correct` contro quel contratto.
    """
    result = evaluate_case(
        _case("counterfactual"), label="counterfactual",
        translation={"input": {"RiskAversion": "Cautious"},
                     "output": {"Age": "Senior"}},
        output="The answer is between 0.0827 and 0.2396",
        tool_calls=[{"name": "cau_inference"}],
    )
    assert result.output.verdict == "correct"


def test_unverified_tool_call_is_indeterminate():
    """Un call registrato senza `success` ne' contatori non dice se ha funzionato.

    Trattarlo come riuscito attribuirebbe al tool un numero che nessuno ha visto
    tornare; trattarlo come fallito punirebbe il modello per un dato assente.
    `unverified` -> `indeterminate` e' la terza via, esplicita nello stato.
    """
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
    """Un call dichiarato fallito e' un esito del percorso, non un buco nei dati.

    `success = False` dice che il motore e' stato invocato e non ha prodotto il
    numero: la riga e' determinabile e sbagliata, quindi `incorrect` -- al
    contrario di `unverified`, dove l'informazione manca e non si puo' concludere.
    """
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
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"


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
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"


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
    assert result.tool_call_valid is False  # esecuzione != argomenti verificati
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"


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
    """`run_orchestrato.py:468-500` aggiunge il passo solo dopo il ritorno.

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
    tacere avrebbe presentato come verificato un argomento mai letto.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.2117", tool_calls=_CONTATORE_OK,
    )
    assert any("arguments: not recorded" in note for note in result.notes)


def test_empty_output_is_indeterminate_not_incorrect():
    """Il gate ferma il run prima del passo causale: una risposta vuota non e'
    un numero sbagliato.

    `number_no_answer` a 0.99 fondeva i fallimenti di acquisizione con gli errori
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


# --- tolleranza derivata dalla precisione stampata dal tool -----------------
#
# I decimali non sono un parametro del valutatore: sono l'ultima cifra che
# `cau_inference` scrive, e si misurano sul codice consegnato -- 3 in
# backward_reasoning (`tools_corretto.py:349`) e intervention (`:380`, `:384`), 4
# in coherence (`:449`, `:454`, dopo la FIX 12 che passa da due a quattro) e nei
# due estremi del controfattuale (`funtions_corretto.py:302`, chiamato da
# `tools_corretto.py:366`).  Il ground truth sta a piena precisione: le 121
# `expected_probability` di `MUDILAB_run/benchmark/benchmark.csv` hanno tutte 10
# decimali (misurato il 04-11), e i 40 estremi controfattuali ne hanno 4.  La
# distanza legittima fra la verita' e il numero trascritto dall'output del tool
# non puo' superare meta' del passo stampato: piu' larga accetta un'ultima cifra
# sbagliata, piu' stretta punisce l'arrotondamento.
_DECIMALI_PER_RAMO = {"cond_prob": 3, "inter": 3, "coherence": 4, "counterfactual": 4}
_TRADUZIONE_INTER = {"input": {"RiskAversion": "Cautious"}, "output": {"Age": "Senior"}}


def _risposta_veritiera(case, decimali: int) -> tuple[str, dict, str]:
    """Etichetta, traduzione e risposta che il ramo produce davvero su questo case.

    La risposta e' il ground truth arrotondato ai decimali di quello che il tool
    stampa, perche' e' esattamente quella la stringa che il modello trascrive: un
    contratto superato su questa risposta dice che la soglia copre l'arrotondamento
    del tool, non che il test e' scritto largo.
    """
    if case.task_type == "counterfactual":
        return (case.expected_label, _TRADUZIONE_INTER,
                f"The answer is between {round(case.expected_lower, decimali)} "
                f"and {round(case.expected_upper, decimali)}")
    traduzione = _TRADUZIONE_INTER if case.task_type == "inter" else _TRADUZIONE
    if case.task_type == "coherence":
        risposta = ("Evidences are compatible with a single Age of Senior "
                    f"with a probability of {round(case.expected_probability, decimali)}")
    else:
        risposta = f"The probability is {round(case.expected_probability, decimali)}"
    return case.expected_label, traduzione, risposta


def test_each_branch_tolerance_is_half_the_printed_step():
    """Ogni ramo ha come soglia meta' dell'ultimo ordine che il tool stampa.

    Fissa la relazione fra la stampa del tool e la tolleranza del contratto: se
    un ramo cambia i decimali stampati, questo test chiede di muovere la soglia
    insieme a lui.  Il valore sta nei diagnostics di ogni verdetto, quindi la
    riga valutata porta con se' il numero che l'ha giudicata.
    """
    for ramo, decimali in _DECIMALI_PER_RAMO.items():
        case = _case(ramo)
        label, traduzione, output = _risposta_veritiera(case, decimali)
        result = evaluate_case(case, label=label, translation=traduzione,
                               output=output, tool_calls=_CONTATORE_OK)
        assert result.output.verdict == "correct", (ramo, result.output.method)
        assert result.output.diagnostics["absolute_tolerance"] == (
            0.5 * 10.0 ** -decimali + 1e-12
        ), ramo
        assert f"{decimali} decimals" in result.tolerance_provenance, ramo


def test_coherence_rejects_a_probability_with_the_last_printed_digit_wrong():
    """0.2118 non e' la stampa di 0.2117494190 a quattro decimali: e' 0.2117.

    Con la soglia fissa a 5e-4 questa risposta passava, perche' lo scarto reale
    (5,06e-5) stava dentro un passo dieci volte piu' grosso di quello che il ramo
    stampa.  E' il falso positivo che la derivazione chiude: un numero la cui
    ultima cifra stampata e' sbagliata non e' un arrotondamento legittimo.
    """
    result = evaluate_case(
        _case("coherence", expected_decision="compatible"), label="coherence",
        translation=_TRADUZIONE,
        output=("Evidences are compatible with a single Age of Senior "
                "with a probability of 0.2118"),
        tool_calls=_CONTATORE_OK,
    )
    assert result.output.diagnostics["absolute_tolerance"] == 0.5 * 10.0 ** -4 + 1e-12
    assert result.output.verdict == "incorrect"
    assert result.end_to_end == "incorrect"


def test_transcrizione_esattamente_a_meta_del_passo_non_e_rifiutata():
    """La meta' del passo stampato e' una trascrizione corretta, non un errore.

    0.0625 a tre decimali esce 0.062 (arrotondamento al pari), e in binario
    0.0625 - 0.062 fa 0.0005000000000000004: una soglia nuda a 0.0005 leggerebbe
    il numero come sbagliato per colpa della sua rappresentazione.  La guardia di
    1e-12 sta sei ordini sotto la soglia -- copre il bordo, non accetta nessun
    valore diverso -- e questo test e' cio' che la rende necessaria.
    """
    assert abs(0.0625 - 0.062) > 0.5 * 10.0 ** -3
    result = evaluate_case(
        _case("cond_prob", expected_probability="0.0625000000"),
        label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.062", tool_calls=_CONTATORE_OK,
    )
    assert result.output.verdict == "correct"


def test_unmeasured_branch_declares_its_tolerance_instead_of_borrowing_one():
    """Un ramo mai letto nella stampa del tool non riceve una soglia derivata.

    `influence` non stampa una probabilita' e non ha una precisione osservata:
    stringere la misura su di esso sarebbe un cambio di metodo senza evidenza,
    quindi il contratto prende la soglia del ramo piu' rozzo fra quelli osservati
    -- lo stesso valore che usava prima -- e la nota lo dichiara nella riga.
    """
    result = evaluate_case(
        _case("influence"), label="influence", translation=_TRADUZIONE,
        output="The probability is 0.212", tool_calls=_CONTATORE_OK,
    )
    assert result.output.diagnostics["absolute_tolerance"] == 0.5 * 10.0 ** -3 + 1e-12
    assert any("absolute tolerance declared, not derived" in note
               for note in result.notes)


# --- argomenti del call registrati e letti ----------------------------------
#
# La forma e' quella che l'harness orchestrato scrive adesso nel passo:
# `run_orchestrato.py:469` passa etichetta, query e path a `cau_inference.func`
# e `:491-495` li registra insieme alla risposta.  La query e' il secondo
# argomento della firma del tool (`consegna/tools_corretto.py:322-323`), cioe' una
# stringa JSON dentro un involucro con tre chiavi: confrontare l'involucro con la
# traduzione in punteggi avrebbe dato `mismatch` fra due dizionari che descrivono
# la stessa query, e il confronto sarebbe fallito per la forma, non per il
# contenuto.
_QUERY_JSON = '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}'


def _passo(args_label="backward_reasoning", args_features=_QUERY_JSON,
           text="The probability is 0.212"):
    return {"step": "cau_inference",
            "args": {"label": args_label, "features": args_features,
                     "path": "insurance_grafo.bif"},
            "text": text}


def test_recorded_arguments_are_read_through_the_tools_signature():
    """Un passo che registra gli argomenti mandati e' decidibile: niente piu' `not recorded`.

    Prima di questa registrazione il record conteneva solo il testo della risposta,
    quindi la prova di esecuzione copriva il fatto che il tool fosse girato ma non
    che avesse ricevuto la traduzione messa in punteggi.  Qui la coincidenza e'
    reale: lo stato `verified` si vede dall'assenza della nota.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.212", tool_calls=[_passo()],
    )
    assert result.tool_call_status == "success"
    assert not any("cau_inference arguments" in note for note in result.notes)
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"


def test_arguments_that_differ_from_the_scored_translation_are_declared():
    """B5: args Bad contro traduzione Normal invalidano il percorso end-to-end.

    Il nuovo contratto autorizzato richiede argomenti verificati: la nota da sola
    non deve piu' far passare un numero ottenuto interrogando un'altra query.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.212",
        tool_calls=[_passo(args_features=(
            '{"input": {"DrivQuality": "Bad"}, "output": {"Age": "Senior"}}'))],
    )
    assert any("cau_inference arguments: mismatch" in note for note in result.notes)
    assert result.end_to_end == "incorrect"


def test_arguments_sent_to_another_branch_of_the_tool_are_declared():
    """Stessa query ma etichetta `intervention`: il tool ha risposto ad altra domanda.

    Il contratto numerico del ramo `cond_prob` e quello dell'intervento non sono lo
    stesso numero, quindi una riga con gli argomenti dell'altro ramo non e'
    verificata dalla traduzione: e' un ramo diverso eseguito sulla stessa query.
    L'etichetta si confronta dopo la normalizzazione del tool, non alla lettera.
    """
    result = evaluate_case(
        _case(), label="backward_reasoning", translation=_TRADUZIONE,
        output="The probability is 0.212", tool_calls=[_passo(args_label="intervention")],
    )
    assert any("another branch of the tool" in note for note in result.notes)


def test_refuso_nei_args_registrati_non_e_un_ramo_sbagliato():
    """`conterfactual` nei argomenti e' il refuso che il tool accetta, non un ramo altro.

    `tools_corretto.py:331-333` normalizza il refuso in `counterfactual` (FIX 2,
    accettato per non rompere i prompt esistenti): un confronto letterale avrebbe
    dichiarato `mismatch` una chiamata che il tool esegue sul ramo giusto, e la
    nota avrebbe accusato il run per colpa dell'ortografia.
    """
    result = evaluate_case(
        _case("counterfactual"), label="counterfactual", translation=_TRADUZIONE_INTER,
        output="The answer is between 0.0827 and 0.2396",
        tool_calls=[_passo(args_label="conterfactual",
                           args_features='{"input": {"RiskAversion": "Cautious"}, '
                                         '"output": {"Age": "Senior"}}',
                           text="The answer is between 0.0827 and 0.2396")],
    )
    assert not any("cau_inference arguments" in note for note in result.notes)
    # Trace legacy senza ricevuta di adozione: numero corretto != percorso provato.
    assert result.end_to_end == "indeterminate"