# -*- coding: utf-8 -*-
"""
test_answer_type_evaluation.py — Test per valutazione basata su answer_type.

Le 26 docstring dei test di questo file sono state aggiunte il 23/10/2026
leggendo i corpi, non dall'autore originale delle funzioni. I 5 test della
classe TestRuoloDiAccComp sono entrati il 04-11-2026 con il declassamento di
acc_comp e hanno la docstring scritta insieme al test.

Casi reali:
- number: verità "21", risposta con passaggi -> corretto; risposta "25" -> sbagliato
- short_text: verità "Atene|Athens", risposte con alternative -> corretto; "Roma" -> sbagliato
- number con decimali: verità "21", risposta "21,0" -> corretto
"""
import pytest
from evaluator import (
    RUOLO_BINARIA,
    RUOLO_COMPOSITO,
    detect_answer_type,
    extract_final_number,
    compare_numbers,
    normalize_text_for_comparison,
    check_short_text_containment,
    evaluate_response,
)


class TestDetectAnswerType:
    def test_number_integer(self):
        """Interi, anche negativi ('21', '42', '-5'): la verita' e' classificata 'number'."""
        assert detect_answer_type("21") == "number"
        assert detect_answer_type("42") == "number"
        assert detect_answer_type("-5") == "number"
    
    def test_number_decimal(self):
        """Decimali con punto o con virgola ('3.14', '21,0', '-2.5') restano 'number'."""
        assert detect_answer_type("3.14") == "number"
        assert detect_answer_type("21,0") == "number"
        assert detect_answer_type("-2.5") == "number"
    
    def test_number_with_alternatives(self):
        """Alternative numeriche separate da '|' ('21|22', '3.14|3,14') sono ancora 'number'."""
        assert detect_answer_type("21|22") == "number"
        assert detect_answer_type("3.14|3,14") == "number"
    
    def test_short_text(self):
        """Testo non numerico di poche parole ('Atene', 'Roma capitale') e' 'short_text'."""
        assert detect_answer_type("Atene") == "short_text"
        assert detect_answer_type("La risposta è Atene") == "short_text"
        assert detect_answer_type("Roma capitale") == "short_text"
    
    def test_short_text_with_alternatives(self):
        """Alternative di testo ('Atene|Athens', 'Si|Yes') restano 'short_text'."""
        assert detect_answer_type("Atene|Athens") == "short_text"
        assert detect_answer_type("Sì|Yes") == "short_text"
    
    def test_free_text(self):
        """Oltre le sei parole della regola (evaluator.py:79) la classificazione diventa 'free_text'."""
        assert detect_answer_type("La capitale della Grecia è Atene, una città storica") == "free_text"
        assert detect_answer_type("Questo è un testo molto lungo con più di sei parole") == "free_text"


class TestExtractFinalNumber:
    def test_simple_number(self):
        """Una risposta che e' solo un numero restituisce quel numero."""
        assert extract_final_number("21") == "21"
        assert extract_final_number("42") == "42"
    
    def test_number_after_equals(self):
        """'=' non e' un marker finale: i passaggi ambigui richiedono astensione."""
        assert extract_final_number("5*5=25, 25-4=21") is None
        assert extract_final_number("5*5=25,25-4=21") is None
        assert extract_final_number("Il risultato è 42") == "42"
    
    def test_number_after_keywords(self):
        """Le formule 'La risposta e X', 'Answer: X', 'result = X' estraggono X."""
        assert extract_final_number("La risposta è 21") == "21"
        assert extract_final_number("Answer: 42") == "42"
        assert extract_final_number("result = 100") == "100"
    
    def test_decimal_number(self):
        """La virgola decimale e' normalizzata a punto: '21,0' diventa '21.0'."""
        assert extract_final_number("21,0") == "21.0"
        assert extract_final_number("3.14") == "3.14"
    
    def test_last_number_in_text(self):
        """La posizione finale non identifica la risposta fra piu' valori plausibili."""
        assert extract_final_number("Ho calcolato 5*5=25, poi 25-4=21") is None
        assert extract_final_number("Primo: 10, secondo: 20, terzo: 30") is None
        assert extract_final_number("Primo10 secondo20 terzo30") is None
    
    def test_no_number(self):
        """Nessun numero, o stringa vuota: None, non '0'."""
        assert extract_final_number("Nessun numero qui") is None
        assert extract_final_number("") is None


class TestCompareNumbers:
    def test_exact_match(self):
        """Due stringhe numeriche identiche coincidono."""
        assert compare_numbers("21", "21") is True
        assert compare_numbers("42", "42") is True
    
    def test_decimal_match(self):
        """'21.0' e '21' sono lo stesso numero in entrambi i versi."""
        assert compare_numbers("21.0", "21") is True
        assert compare_numbers("21", "21.0") is True
        assert compare_numbers("3.14", "3.14") is True
    
    def test_within_tolerance(self):
        """Uno scarto di 1e-7 e' dentro la tolleranza del confronto."""
        assert compare_numbers("21.0000001", "21") is True
        assert compare_numbers("20.9999999", "21") is True
    
    def test_outside_tolerance(self):
        """Uno scarto di 1-4 unita' e' fuori tolleranza: falso."""
        assert compare_numbers("22", "21") is False
        assert compare_numbers("20", "21") is False
        assert compare_numbers("25", "21") is False
    
    def test_zero_handling(self):
        """Lo zero non e' un caso speciale: '0', '0.0' e 1e-7 contro 0 coincidono."""
        assert compare_numbers("0", "0") is True
        assert compare_numbers("0.0", "0") is True
        assert compare_numbers("0.0000001", "0") is True


class TestNormalizeTextForComparison:
    def test_lowercase(self):
        """'Atene' e 'ATHENS' si riducono a 'athens'."""
        assert normalize_text_for_comparison("Atene") == "atene"
        assert normalize_text_for_comparison("ATHENS") == "athens"
    
    def test_remove_accents(self):
        """Gli accenti cadono: 'citta' e 'perche' restano senza segno grafico."""
        assert normalize_text_for_comparison("città") == "citta"
        assert normalize_text_for_comparison("perché") == "perche"
    
    def test_remove_punctuation(self):
        """La punteggiatura cade ('Atene!' -> 'atene'), lo spazio di 'Roma, capitale' resta."""
        assert normalize_text_for_comparison("Atene!") == "atene"
        assert normalize_text_for_comparison("Roma, capitale") == "roma capitale"
    
    def test_remove_articles(self):
        """Gli articoli italiani e inglesi ('La', 'Il', 'The') vengono tolti."""
        assert normalize_text_for_comparison("La capitale") == "capitale"
        assert normalize_text_for_comparison("The capital") == "capital"
        assert normalize_text_for_comparison("Il risultato") == "risultato"


class TestCheckShortTextContainment:
    def test_exact_match(self):
        """Verita' e risposta identiche: corretto, e 'matched' riporta la verita'."""
        is_correct, matched = check_short_text_containment("Atene", "Atene")
        assert is_correct is True
        assert matched == "Atene"
    
    def test_contained_in_sentence(self):
        """Una frase che contiene la verita' come sottostringa e' corretta."""
        is_correct, matched = check_short_text_containment(
            "La capitale della Grecia è Atene.", "Atene"
        )
        assert is_correct is True
        assert matched == "Atene"
    
    def test_alternatives(self):
        """Basta una delle alternative: 'Athens' e 'Atene' sono entrambe corrette, e 'matched' dice quale."""
        is_correct, matched = check_short_text_containment(
            "The capital is Athens.", "Atene|Athens"
        )
        assert is_correct is True
        assert matched == "Athens"
        
        is_correct, matched = check_short_text_containment(
            "La capitale è Atene.", "Atene|Athens"
        )
        assert is_correct is True
        assert matched == "Atene"
    
    def test_no_match(self):
        """'Roma' contro 'Atene|Athens': falso e 'matched' a None."""
        is_correct, matched = check_short_text_containment("Roma", "Atene|Athens")
        assert is_correct is False
        assert matched is None
    
    def test_case_insensitive(self):
        """'ATENE' contro 'Atene' e' corretto: il confronto non distingue il maiuscolo."""
        is_correct, matched = check_short_text_containment("ATENE", "Atene")
        assert is_correct is True


class TestEvaluateResponseIntegration:
    def test_number_correct_with_steps(self):
        """Verità '21', risposta con passaggi '5*5=25, 25-4=21. La risposta è 21' -> corretto"""
        res = evaluate_response(
            "5*5=25, 25-4=21. La risposta è 21",
            ground_truth="21",
            answer_type="auto",
        )
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.answer_type == "number"
        assert res.extracted_answer == "21"
    
    def test_number_wrong(self):
        """Verità '21', risposta '25' -> sbagliato"""
        res = evaluate_response(
            "25",
            ground_truth="21",
            answer_type="auto",
        )
        assert res.is_correct == 0
        assert res.acc_comp == 0.0
        assert res.answer_type == "number"
        assert res.extracted_answer == "25"
    
    def test_number_decimal_with_distractor_abstains(self):
        """Il 3 dei passi e il 21,0 sono distinti: senza marker non si sceglie il secondo."""
        for text in ("dopo 3 passi ottengo 21,0", "dopo3 passi ottengo21,0"):
            res = evaluate_response(text, ground_truth="21", answer_type="auto")
            assert res.is_correct is None
            assert res.acc_comp is None
            assert res.answer_type == "number"
            assert res.extracted_answer is None

    def test_number_decimal_correct_without_distractors(self):
        """Senza distrattori il decimale italiano 21,0 coincide con l'intero 21."""
        res = evaluate_response("Ottengo 21,0", ground_truth="21", answer_type="auto")
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.extracted_answer == "21.0"
    
    def test_short_text_alternatives_correct_1(self):
        """Verità 'Atene|Athens', risposta 'La capitale della Grecia è Atene.' -> corretto"""
        res = evaluate_response(
            "La capitale della Grecia è Atene.",
            ground_truth="Atene|Athens",
            answer_type="auto",
        )
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.answer_type == "short_text"
        assert res.extracted_answer == "Atene"
    
    def test_short_text_alternatives_correct_2(self):
        """Verità 'Atene|Athens', risposta 'The capital of Greece is Athens.' -> corretto"""
        res = evaluate_response(
            "The capital of Greece is Athens.",
            ground_truth="Atene|Athens",
            answer_type="auto",
        )
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.answer_type == "short_text"
        assert res.extracted_answer == "Athens"
    
    def test_short_text_alternatives_correct_3(self):
        """Verità 'Atene|Athens', risposta 'Atene (in greco: Αθήνα)' -> corretto"""
        res = evaluate_response(
            "Atene (in greco: Αθήνα)",
            ground_truth="Atene|Athens",
            answer_type="auto",
        )
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.answer_type == "short_text"
        assert res.extracted_answer == "Atene"
    
    def test_short_text_wrong(self):
        """Verità 'Atene|Athens', risposta 'Roma' -> sbagliato"""
        res = evaluate_response(
            "Roma",
            ground_truth="Atene|Athens",
            answer_type="auto",
        )
        assert res.is_correct == 0
        assert res.acc_comp == 0.0
        assert res.answer_type == "short_text"
    
    def test_explicit_answer_type_number(self):
        """Forza answer_type='number' anche se GT non è puramente numerica"""
        res = evaluate_response(
            "42",
            ground_truth="42",
            answer_type="number",
        )
        assert res.is_correct == 1
        assert res.answer_type == "number"
    
    def test_explicit_answer_type_short_text(self):
        """Forza answer_type='short_text' anche se GT è lunga"""
        res = evaluate_response(
            "La risposta è Atene",
            ground_truth="Atene",
            answer_type="short_text",
        )
        assert res.is_correct == 1
        assert res.answer_type == "short_text"


class TestRuoloDiAccComp:
    """Il nome 'accuracy composita' era ambiguo: ogni ramo scrive in `notes` cosa
    il suo valore di acc_comp effettivamente e' (04-11-2026, declassamento)."""

    def test_numero_dichiara_che_non_e_una_media(self):
        """Ramo number: acc_comp == is_correct (0/1) e la riga lo dichiara con RUOLO_BINARIA."""
        res = evaluate_response("21", ground_truth="21", answer_type="auto")
        assert res.acc_comp == float(res.is_correct)
        assert RUOLO_BINARIA in res.notes
        assert RUOLO_COMPOSITO not in res.notes

    def test_short_text_dichiara_che_non_e_una_media(self):
        """Ramo short_text: un solo confronto binario, nessuna componente pesata da mediare."""
        res = evaluate_response("Roma", ground_truth="Atene|Athens", answer_type="auto")
        assert res.acc_comp == float(res.is_correct) == 0.0
        assert RUOLO_BINARIA in res.notes

    def test_regime_a_dichiara_l_indice_pesato(self):
        """free_text con giudice: acc_comp e' la media rinormalizzata 0.5/0.3 (cosine N/A),
        e per questo puo' divergere da is_correct — la nota lo dice."""
        res = evaluate_response(
            "Il riscaldamento globale causa un aumento delle temperature, "
            "che e un effetto sul livello dei mari",
            ground_truth="Il riscaldamento globale causa un aumento delle temperature",
            judge_fn=lambda q, a, m: (4.0, {"ok": True, "judge_model": "finto"}),
        )
        assert res.eval_mode == "ground_truth"
        assert RUOLO_COMPOSITO in res.notes
        # 0.5*acc_links + 0.3*(judge/5) rinormalizzato su 0.8 (cosine_sim assente)
        assert res.acc_comp == pytest.approx((0.5 * res.acc_links + 0.3 * 0.8) / 0.8)
        assert res.acc_comp != float(res.is_correct)

    def test_regime_b_dichiara_l_indice_pesato(self):
        """Senza GT il giudice decide is_correct e acc_comp resta un indice a pesi:
        qui vale 0.315 su una risposta giudicata corretta, precisamente perche'
        non misura quante risposte sono corrette."""
        res = evaluate_response(
            "La causa produsse un effetto sul sistema",
            ground_truth=None,
            judge_fn=lambda q, a, m: (4.5, {"ok": True, "judge_model": "finto"}),
        )
        assert res.eval_mode == "causal_agent_eval"
        assert RUOLO_COMPOSITO in res.notes
        assert res.is_correct == 1 and res.acc_comp < 1.0

    def test_keyword_diagnostico_dichiara_l_indice_pesato(self):
        """Il fallback keyword ha costanti fisse al posto del giudice e del coseno:
        la sua nota di ruolo deve esserci come sui rami a pesi veri."""
        res = evaluate_response(
            "The cause produced an effect on the system", mode="causal")
        assert res.eval_mode == "heuristic_keyword_fallback"
        assert RUOLO_COMPOSITO in res.notes
        assert res.acc_comp != float(res.is_correct)


class TestNumericB1:
    @pytest.mark.parametrize("answer,reference", [
        ("+3", "3"), ("-.5", "-0,5"), ("+,5", "0.5"),
        ("1e3", "1000"), ("-2.5E-3", "-0.0025"), ("+2,5e+2", "250"),
        ("50%", "0.5"), ("0.5", "50 %"), ("-5e1%", "-0.5"),
        ("3000 mJ", "3 J"), (".003 kJ", "3 J"), ("3J", "3000mJ"),
        ("3 W", "3W"), ("500 ms", ".5 s"), ("-.5 s", "-500ms"),
        ("Ottengo 21,0", "21"), ("21 21", "21"), ("21 e 21", "21"),
        ("3 J; 3000 mJ", "3J"), ("+3; +3", "3"),
    ])
    def test_shared_finite_quantities(self, answer, reference):
        """Entrambi i valutatori riconoscono lo stesso scalare e conversioni SI esatte."""
        from robust_evaluator import evaluate
        standard = evaluate_response(answer, ground_truth=reference, answer_type="auto")
        robust = evaluate(answer, {"accepted_answers": [reference]})
        assert standard.answer_type == robust.answer_type == "number"
        assert standard.is_correct == 1 and standard.acc_comp == 1.0
        assert robust.verdict == "correct"
        assert standard.extracted_answer == robust.extracted_answer

    @pytest.mark.parametrize("marker", [
        "final answer", "risposta finale", "answer", "result", "risposta", "risultato",
    ])
    @pytest.mark.parametrize("separator", [" ", ": ", " = ", " is ", " è "])
    def test_marker_grammar(self, marker, separator):
        """Il marker, non '=' isolato, separa il risultato dai numeri intermedi."""
        from robust_evaluator import evaluate
        text = "5*5=25. " + marker + separator + "-2.1e1"
        standard = evaluate_response(text, ground_truth="-21", answer_type="number")
        robust = evaluate(text, {"answer_type": "number", "accepted_answers": ["-21"]})
        assert standard.is_correct == 1 and robust.verdict == "correct"
        assert standard.extracted_answer == robust.extracted_answer == "-2.1e1"

    @pytest.mark.parametrize("text", [
        "answer: 20; final answer: 21", "final answer: 21; answer: 20",
        "risultato=20; risposta finale è 21", "answer: 21; risultato: 21",
        "Final answer: 21; risposta finale: 21.0",
    ])
    def test_marker_priority_and_agreement(self, text):
        """Il livello finale prevale in entrambi gli ordini; ripetizioni concordi non sono ambigue."""
        from robust_evaluator import evaluate
        assert evaluate_response(text, ground_truth="21", answer_type="number").is_correct == 1
        assert evaluate(text, {"answer_type": "number", "accepted_answers": [21]}).verdict == "correct"

    @pytest.mark.parametrize("text", [
        "", "   ", "answer:", "risposta finale è", "21; final answer:",
        "answer: 21; final answer:", "answer:; result: 21",
        "answer: 20; result: 21", "final answer: 20; risposta finale: 21",
        "final answer: 21 or 20", "21 20", "5*5=25,25-4=21",
        "Primo10 secondo20 terzo30", "dopo3 passi ottengo21,0", "21=21",
        "21*21", "21+21", "21 +21", "--21", "−21",
        "NaN", "+inf", "-Infinity", "∞", "1e309", "1e-9999", "1e+",
        "answer: NaN", "21 blarg", "21 kg", "21 J/kg", "21 (W)",
        "21 W^2", "21% J", "21 J foo", "$21", "21e", "1,234.5",
        "21 21.0000000000001",
    ])
    def test_shared_abstention(self, text):
        """Ambiguita', non-finiti e grammatica non supportata non inventano una risposta estraibile."""
        from robust_evaluator import evaluate
        standard = evaluate_response(text, ground_truth="21", answer_type="number")
        robust = evaluate(text, {"answer_type": "number", "accepted_answers": [21]})
        assert standard.is_correct is None and standard.acc_comp is None
        assert robust.verdict == "indeterminate" and robust.score is None
        assert standard.extracted_answer is robust.extracted_answer is None
        assert extract_final_number(text) is None

    @pytest.mark.parametrize("text", ["non so", "nessun numero qui", "answer: non so"])
    def test_nonempty_without_number_is_incorrect(self, text):
        """Testo presente senza numeri e' errore, distinto dall'assenza di una risposta."""
        from robust_evaluator import evaluate
        standard = evaluate_response(text, ground_truth="21", answer_type="number")
        robust = evaluate(text, {"answer_type": "number", "accepted_answers": [21]})
        assert standard.is_correct == 0 and standard.acc_comp == 0.0
        assert robust.verdict == "incorrect"

    @pytest.mark.parametrize("answer,reference", [
        ("3 W", "3 J"), ("3 W", "3"), ("3", "3 J"),
        ("3 s", "3 J"), ("3 mJ", "3 J"), ("3%", "3"), ("-3", "3"),
    ])
    def test_dimensions_scales_and_signs_are_not_erased(self, answer, reference):
        """Stessa cifra non significa stessa quantita': dimensione, scala e segno restano vincolanti."""
        from robust_evaluator import evaluate
        standard = evaluate_response(answer, ground_truth=reference, answer_type="number")
        robust = evaluate(answer, {"answer_type": "number", "accepted_answers": [reference]})
        assert standard.is_correct == 0 and robust.verdict == "incorrect"
        assert compare_numbers(answer, reference) is False

    @pytest.mark.parametrize("reference", ["NaN", "inf", "1e309", "3 blarg", "3 J/kg", "3|"])
    def test_standard_invalid_numeric_reference_abstains(self, reference):
        """Una GT numerica non valida non puo' diventare un errore imputato al modello."""
        result = evaluate_response("3", ground_truth=reference, answer_type="number")
        assert result.is_correct is None and result.acc_comp is None

    def test_standard_tolerance_remains_strict(self):
        """La soglia relativa storica e quella assoluta per GT=0 escludono il bordo."""
        assert compare_numbers("1e-6", "0") is False
        assert compare_numbers("9.999e-7", "0") is True
        assert compare_numbers("1.0000005", "1") is True
        assert compare_numbers("1.000002", "1") is False
        # Bordo relativo binario esatto: 0.25 / 2 = 0.125.
        assert compare_numbers("2.25", "2", tolerance=0.125) is False
        for invalid in ("nan", "inf", "-inf", "1e309"):
            assert compare_numbers(invalid, invalid) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
