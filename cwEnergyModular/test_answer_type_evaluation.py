# -*- coding: utf-8 -*-
"""
test_answer_type_evaluation.py — Test per valutazione basata su answer_type.

Le 26 docstring dei test di questo file sono state aggiunte il 23/10/2026
leggendo i corpi, non dall'autore originale delle funzioni.

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
        """Dopo una catena di uguaglianze ('5*5=25, 25-4=21') si prende l'ultimo valore, non il primo."""
        assert extract_final_number("5*5=25, 25-4=21") == "21"
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
        """Senza parole chiave, il fallback prende comunque l'ultimo numero del testo."""
        assert extract_final_number("Ho calcolato 5*5=25, poi 25-4=21") == "21"
        assert extract_final_number("Primo: 10, secondo: 20, terzo: 30") == "30"
    
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
