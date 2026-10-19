# -*- coding: utf-8 -*-
"""
test_answer_type_evaluation.py — Test per valutazione basata su answer_type.

Casi reali:
- number: verità "21", risposta con passaggi -> corretto; risposta "25" -> sbagliato
- short_text: verità "Atene|Athens", risposte con alternative -> corretto; "Roma" -> sbagliato
- number con decimali: verità "21", risposta "21,0" -> corretto
"""
import pytest
from evaluator import (
    detect_answer_type,
    extract_final_number,
    compare_numbers,
    normalize_text_for_comparison,
    check_short_text_containment,
    evaluate_response,
)


class TestDetectAnswerType:
    def test_number_integer(self):
        assert detect_answer_type("21") == "number"
        assert detect_answer_type("42") == "number"
        assert detect_answer_type("-5") == "number"
    
    def test_number_decimal(self):
        assert detect_answer_type("3.14") == "number"
        assert detect_answer_type("21,0") == "number"
        assert detect_answer_type("-2.5") == "number"
    
    def test_number_with_alternatives(self):
        assert detect_answer_type("21|22") == "number"
        assert detect_answer_type("3.14|3,14") == "number"
    
    def test_short_text(self):
        assert detect_answer_type("Atene") == "short_text"
        assert detect_answer_type("La risposta è Atene") == "short_text"
        assert detect_answer_type("Roma capitale") == "short_text"
    
    def test_short_text_with_alternatives(self):
        assert detect_answer_type("Atene|Athens") == "short_text"
        assert detect_answer_type("Sì|Yes") == "short_text"
    
    def test_free_text(self):
        assert detect_answer_type("La capitale della Grecia è Atene, una città storica") == "free_text"
        assert detect_answer_type("Questo è un testo molto lungo con più di sei parole") == "free_text"


class TestExtractFinalNumber:
    def test_simple_number(self):
        assert extract_final_number("21") == "21"
        assert extract_final_number("42") == "42"
    
    def test_number_after_equals(self):
        assert extract_final_number("5*5=25, 25-4=21") == "21"
        assert extract_final_number("Il risultato è 42") == "42"
    
    def test_number_after_keywords(self):
        assert extract_final_number("La risposta è 21") == "21"
        assert extract_final_number("Answer: 42") == "42"
        assert extract_final_number("result = 100") == "100"
    
    def test_decimal_number(self):
        assert extract_final_number("21,0") == "21.0"
        assert extract_final_number("3.14") == "3.14"
    
    def test_last_number_in_text(self):
        assert extract_final_number("Ho calcolato 5*5=25, poi 25-4=21") == "21"
        assert extract_final_number("Primo: 10, secondo: 20, terzo: 30") == "30"
    
    def test_no_number(self):
        assert extract_final_number("Nessun numero qui") is None
        assert extract_final_number("") is None


class TestCompareNumbers:
    def test_exact_match(self):
        assert compare_numbers("21", "21") is True
        assert compare_numbers("42", "42") is True
    
    def test_decimal_match(self):
        assert compare_numbers("21.0", "21") is True
        assert compare_numbers("21", "21.0") is True
        assert compare_numbers("3.14", "3.14") is True
    
    def test_within_tolerance(self):
        assert compare_numbers("21.0000001", "21") is True
        assert compare_numbers("20.9999999", "21") is True
    
    def test_outside_tolerance(self):
        assert compare_numbers("22", "21") is False
        assert compare_numbers("20", "21") is False
        assert compare_numbers("25", "21") is False
    
    def test_zero_handling(self):
        assert compare_numbers("0", "0") is True
        assert compare_numbers("0.0", "0") is True
        assert compare_numbers("0.0000001", "0") is True


class TestNormalizeTextForComparison:
    def test_lowercase(self):
        assert normalize_text_for_comparison("Atene") == "atene"
        assert normalize_text_for_comparison("ATHENS") == "athens"
    
    def test_remove_accents(self):
        assert normalize_text_for_comparison("città") == "citta"
        assert normalize_text_for_comparison("perché") == "perche"
    
    def test_remove_punctuation(self):
        assert normalize_text_for_comparison("Atene!") == "atene"
        assert normalize_text_for_comparison("Roma, capitale") == "roma capitale"
    
    def test_remove_articles(self):
        assert normalize_text_for_comparison("La capitale") == "capitale"
        assert normalize_text_for_comparison("The capital") == "capital"
        assert normalize_text_for_comparison("Il risultato") == "risultato"


class TestCheckShortTextContainment:
    def test_exact_match(self):
        is_correct, matched = check_short_text_containment("Atene", "Atene")
        assert is_correct is True
        assert matched == "Atene"
    
    def test_contained_in_sentence(self):
        is_correct, matched = check_short_text_containment(
            "La capitale della Grecia è Atene.", "Atene"
        )
        assert is_correct is True
        assert matched == "Atene"
    
    def test_alternatives(self):
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
        is_correct, matched = check_short_text_containment("Roma", "Atene|Athens")
        assert is_correct is False
        assert matched is None
    
    def test_case_insensitive(self):
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
    
    def test_number_decimal_correct(self):
        """Verità '21', risposta 'dopo 3 passi ottengo 21,0' -> corretto"""
        res = evaluate_response(
            "dopo 3 passi ottengo 21,0",
            ground_truth="21",
            answer_type="auto",
        )
        assert res.is_correct == 1
        assert res.acc_comp == 1.0
        assert res.answer_type == "number"
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
