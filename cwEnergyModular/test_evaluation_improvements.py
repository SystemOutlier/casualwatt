# -*- coding: utf-8 -*-
"""
test_evaluation_improvements.py — Test dei due miglioramenti della misurazione
della correttezza (15-11-2026).

Miglioramento 1: semantic_provenance (EvaluationResult)
Dichiara se is_correct su free_text è provvisorio (lessicale durante il
benchmark) o definitivo (semantico post-hoc). Riferimento: Reimers & Gurevych
(2019) Sentence-BERT; Wang et al. (2025) Practical Guide (arXiv:2506.13023).

Miglioramento 2: judge_uncertainty (EvaluationResult)
Margine dello score del giudice LLM dalla soglia 4.0 per quantificare
l'incertezza nel REGIME B. Riferimento: Sheng et al. (EMNLP 2025)
(arXiv:2509.18658); Wagner et al. (2024) (arXiv:2410.11594).
"""
import pytest


@pytest.fixture
def evaluator():
    """Importa evaluator in un contesto dove causal_extractor e semantic_evaluator
    sono disponibili (test eseguiti dalla radice di cwEnergyModular/)."""
    import evaluator as ev
    return ev


class TestSemanticProvenance:
    """Miglioramento 1: semantic_provenance su free_text."""

    def test_free_text_senza_semantica_dichiara_lexical_only(self, evaluator):
        """Durante il benchmark (use_semantic=False), free_text dichiara
        semantic_provenance='lexical_only' e is_correct è provvisorio."""
        res = evaluator.evaluate_response(
            text="Roma è la capitale d'Italia",
            ground_truth="La capitale italiana è Roma",
            mode="auto",
            answer_type="free_text",
            use_semantic=False,
        )
        assert res.semantic_provenance == "lexical_only"
        assert res.answer_type == "free_text"
        # is_correct è determinato lessicalmente, non semanticamente
        assert res.is_correct in (0, 1)
        assert any("lexical_only" in note for note in res.notes)

    def test_free_text_con_semantica_dichiara_semantic_similarity(self, evaluator):
        """Post-hoc (use_semantic=True), free_text dichiara
        semantic_provenance='semantic_similarity' se gli embedding sono attivi."""
        res = evaluator.evaluate_response(
            text="Roma è la capitale d'Italia",
            ground_truth="La capitale italiana è Roma",
            mode="auto",
            answer_type="free_text",
            use_semantic=True,
        )
        # Se gli embedding sono disponibili, la provenienza è semantica
        if res.semantic_similarity is not None:
            assert res.semantic_provenance == "semantic_similarity"
        else:
            # Se gli embedding non sono disponibili, resta lexical_only
            # anche se use_semantic=True (fallback dichiarato)
            assert res.semantic_provenance == "lexical_only"

    def test_number_non_applica_semantic_provenance(self, evaluator):
        """I rami number e short_text non sono free_text: semantic_provenance
        resta vuoto (non applicabile)."""
        res = evaluator.evaluate_response(
            text="42",
            ground_truth="42",
            mode="auto",
            answer_type="number",
        )
        assert res.semantic_provenance == ""
        assert res.answer_type == "number"

    def test_short_text_non_applica_semantic_provenance(self, evaluator):
        """short_text non è free_text: semantic_provenance resta vuoto."""
        res = evaluator.evaluate_response(
            text="Roma",
            ground_truth="Roma",
            mode="auto",
            answer_type="short_text",
        )
        assert res.semantic_provenance == ""
        assert res.answer_type == "short_text"

    def test_lexical_only_note_includes_reference(self, evaluator):
        """La nota di semantic_provenance=lexical_only cita i riferimenti
        scientifici (Reimers & Gurevych 2019, Wang et al. 2025)."""
        res = evaluator.evaluate_response(
            text="Risposta lunga e complessa",
            ground_truth="Risposta completamente diversa",
            mode="auto",
            answer_type="free_text",
            use_semantic=False,
        )
        notes_text = " ".join(res.notes)
        assert "lexical_only" in notes_text
        # La nota deve menzionare che è una stima provvisoria
        assert "PROVVISORIA" in notes_text or "provvisoria" in notes_text


class TestJudgeUncertainty:
    """Miglioramento 2: judge_uncertainty nel REGIME B."""

    def test_judge_uncertainty_sopra_soglia(self, evaluator):
        """Quando il giudice dà 5.0 (massimo), judge_uncertainty = +1.0
        (massima confidenza nella correttezza)."""
        def fake_judge_high(question, answer, model):
            return (5.0, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta corretta",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_high,
        )
        assert res.judge_uncertainty == 1.0
        assert res.is_correct == 1  # 5.0 >= 4.0 → corretto
        assert res.eval_mode == "causal_agent_eval"

    def test_judge_uncertainty_sotto_soglia(self, evaluator):
        """Quando il giudice dà 0.0 (minimo), judge_uncertainty = -4.0
        (massima confidenza nell'errore)."""
        def fake_judge_low(question, answer, model):
            return (0.0, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta errata",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_low,
        )
        assert res.judge_uncertainty == -4.0
        assert res.is_correct == 0  # 0.0 < 4.0 → errato

    def test_judge_uncertainty_vicino_soglia(self, evaluator):
        """Quando il giudice dà 4.0 (esattamente sulla soglia),
        judge_uncertainty = 0.0 (massima incertezza)."""
        def fake_judge_threshold(question, answer, model):
            return (4.0, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta al limite",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_threshold,
        )
        assert res.judge_uncertainty == 0.0
        assert res.is_correct == 1  # 4.0 >= 4.0 → corretto (soglia inclusiva)
        # La nota deve segnalare incertezza elevata
        notes_text = " ".join(res.notes)
        assert "incerto" in notes_text.lower() or "incertezza" in notes_text.lower()

    def test_judge_uncertainty_leggermente_sopra(self, evaluator):
        """Judge 4.3 → uncertainty +0.3 (leggermente sopra soglia, incerto)."""
        def fake_judge_close(question, answer, model):
            return (4.3, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta quasi corretta",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_close,
        )
        assert res.judge_uncertainty == 0.3
        assert res.is_correct == 1
        # Margine < 0.5 → nota di incertezza
        notes_text = " ".join(res.notes)
        assert "incerto" in notes_text.lower() or "incertezza" in notes_text.lower()

    def test_judge_uncertainty_leggermente_sotto(self, evaluator):
        """Judge 3.7 → uncertainty -0.3 (leggermente sotto soglia, incerto)."""
        def fake_judge_close_below(question, answer, model):
            return (3.7, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta quasi errata",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_close_below,
        )
        assert res.judge_uncertainty == -0.3
        assert res.is_correct == 0  # 3.7 < 4.0 → errato

    def test_judge_uncertainty_none_se_giudice_assente(self, evaluator):
        """Se il giudice non risponde, judge_uncertainty è None."""
        def fake_judge_unavailable(question, answer, model):
            return (None, {"ok": False, "reason": "unavailable"})

        res = evaluator.evaluate_response(
            text="Risposta senza giudice",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_unavailable,
        )
        assert res.judge_uncertainty is None
        assert res.is_correct is None

    def test_judge_uncertainty_note_cita_riferimento(self, evaluator):
        """La nota di judge_uncertainty cita Sheng et al. (EMNLP 2025)."""
        def fake_judge_confident(question, answer, model):
            return (5.0, {"ok": True, "judge_model": "fake"})

        res = evaluator.evaluate_response(
            text="Risposta corretta",
            ground_truth=None,
            mode="auto",
            judge_fn=fake_judge_confident,
        )
        notes_text = " ".join(res.notes)
        assert "Sheng" in notes_text or "2509.18658" in notes_text

    def test_judge_gated_non_chiama_giudice(self, evaluator):
        """Se judge_gated=True, il giudice non è chiamato e
        judge_uncertainty resta None."""
        res = evaluator.evaluate_response(
            text="Risposta con gate",
            ground_truth=None,
            mode="auto",
            judge_gated=True,
        )
        assert res.judge_uncertainty is None
        assert res.is_correct is None
        assert res.none_reason == "judge_uncalibrated"

    def test_judge_uncertainty_range_valido(self, evaluator):
        """judge_uncertainty è sempre nell'intervallo [-4.0, +1.0]
        dato che judge_score è in [0.0, 5.0]."""
        for score in [0.0, 1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0]:
            def fake_judge(s=score):
                return lambda q, a, m: (s, {"ok": True, "judge_model": "fake"})

            res = evaluator.evaluate_response(
                text="Test",
                ground_truth=None,
                mode="auto",
                judge_fn=fake_judge(),
            )
            assert -4.0 <= res.judge_uncertainty <= 1.0, \
                f"judge_uncertainty {res.judge_uncertainty} fuori range per score {score}"


class TestEvaluationResultFields:
    """Verifica che i nuovi campi esistano in EvaluationResult."""

    def test_semantic_provenance_field_exists(self, evaluator):
        """Il campo semantic_provenance esiste in EvaluationResult."""
        res = evaluator.EvaluationResult()
        assert hasattr(res, 'semantic_provenance')
        assert res.semantic_provenance == ""  # default vuoto

    def test_judge_uncertainty_field_exists(self, evaluator):
        """Il campo judge_uncertainty esiste in EvaluationResult."""
        res = evaluator.EvaluationResult()
        assert hasattr(res, 'judge_uncertainty')
        assert res.judge_uncertainty is None  # default NA
