import json

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
    """La tolleranza numerica esiste solo se il contratto la dichiara.

    Con `absolute_tolerance = 0.001` l'errore `0.2124 - 0.212 = 0.0004` passa e
    l'errore `0.22 - 0.212 = 0.008` no; senza tolleranza un confronto approssimato
    sarebbe una soglia arbitraria del valutatore, non una regola del dataset. Il
    test fissa i due lati del confronto sullo stesso riferimento, cosi' che la
    soglia si veda applicata e non solo nominata.
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