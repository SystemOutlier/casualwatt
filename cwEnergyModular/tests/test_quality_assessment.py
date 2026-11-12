# -*- coding: utf-8 -*-
"""P6.8 — Test della valutazione della qualita non binaria (scala 0-5).

Verifica:
- krippendorff_alpha_ordinal su scale ordinali 0-5 (accordo perfetto = 1,
  disaccordo sistematico < 0, degenere = None);
- krippendorff_alpha_interval su scale a intervalli (distanza quadratica);
- weighted_cohen_kappa con pesi lineari e quadratici;
- QualityAssessmentGate: soglie, pavimento di numerosita', frazione ammissibile,
  stato per strata e stato complessivo, indipendenza da scoring_status;
- template di preregistrazione con campi None prima della registrazione;
- integrazione con extract_quality_records_from_schema.
"""

from __future__ import annotations

import pytest

from quality_assessment import (
    QUALITY_SCALE,
    MIN_QUALITY_PAIRABLE,
    MIN_QUALITY_ADMISSIBLE_FRACTION,
    QualityAssessmentCriteria,
    QualityAssessmentGate,
    extract_quality_records_from_schema,
    krippendorff_alpha_interval,
    krippendorff_alpha_ordinal,
    quality_protocol_template,
    weighted_cohen_kappa,
)


# ---------------------------------------------------------------------------
# Krippendorff alpha ordinale
# ---------------------------------------------------------------------------


def test_alpha_ordinale_accordo_perfetto_vale_uno():
    """Due valutatori sempre concordi su scala 0-5 producono alpha = 1.0."""
    units = [[3, 3], [0, 0], [5, 5], [2, 2], [4, 4]]
    assert krippendorff_alpha_ordinal(units, level="ordinal") == pytest.approx(1.0)


def test_alpha_ordinale_disaccordo_sistematico_resta_negativo():
    """Un disaccordo sistematico (valutatore 2 assegna sempre il complementare)
    produce alpha < 0. Il valore negativo NON va clampato a zero."""
    units = [[0, 5], [1, 4], [2, 3], [3, 2], [4, 1], [5, 0]]
    alpha = krippendorff_alpha_ordinal(units, level="ordinal")
    assert alpha is not None and alpha < 0.0


def test_alpha_ordinale_item_con_un_solo_valutatore_viene_ignorato():
    """Item con un solo punteggio valido non contribuisce a coppie e non e'
    conteggiato tra le coppie pairable."""
    units = [[3, 3], [0, None], [5, 5], [None, None]]
    assert krippendorff_alpha_ordinal(units, level="ordinal") == pytest.approx(1.0)


def test_alpha_ordinale_meno_di_due_item_non_definito():
    """Con meno di due item da confrontare alpha non e' calcolabile: None."""
    assert krippendorff_alpha_ordinal([[3, 3]], level="ordinal") is None
    assert krippendorff_alpha_ordinal([], level="ordinal") is None


def test_alpha_ordinale_tutti_uguali_varianza_nula():
    """Se tutti i punteggi sono uguali non c'è varianza: alpha None."""
    units = [[3, 3], [3, 3], [3, 3]]
    assert krippendorff_alpha_ordinal(units, level="ordinal") is None


# ---------------------------------------------------------------------------
# Krippendorff alpha a intervalli
# ---------------------------------------------------------------------------


def test_alpha_interval_accordo_perfetto_vale_uno():
    """Due valutatori sempre concordi producono alpha = 1.0 anche a intervalli."""
    units = [[3, 3], [0, 0], [5, 5], [2, 2], [4, 4]]
    assert krippendorff_alpha_interval(units, level="interval") == pytest.approx(1.0)


def test_alpha_interval_penalizza_distanze_grandi():
    """A intervalli, un errore di 4 gradi pesa di piu' di un errore di 1 grado:
    disaccordi su valori distanti producono alpha piu' basso."""
    close = [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5]]
    far = [[0, 5], [1, 4], [2, 3], [3, 2], [4, 1], [5, 0]]
    alpha_close = krippendorff_alpha_interval(close, level="interval")
    alpha_far = krippendorff_alpha_interval(far, level="interval")
    assert alpha_close is not None and alpha_far is not None
    assert alpha_close > alpha_far


# ---------------------------------------------------------------------------
# Cohen kappa ponderato
# ---------------------------------------------------------------------------


def test_weighted_kappa_lineare_accordo_perfetto_vale_uno():
    """Due valutatori sempre concordi producono kappa = 1.0 (lineare)."""
    a = [0, 1, 2, 3, 4, 5]
    b = [0, 1, 2, 3, 4, 5]
    assert weighted_cohen_kappa(a, b, weight="linear") == pytest.approx(1.0)


def test_weighted_kappa_quadratico_accordo_perfetto_vale_uno():
    """Due valutatori sempre concordi producono kappa = 1.0 (quadratico)."""
    a = [0, 1, 2, 3, 4, 5]
    b = [0, 1, 2, 3, 4, 5]
    assert weighted_cohen_kappa(a, b, weight="quadratic") == pytest.approx(1.0)


def test_weighted_kappa_disaccordo_sistematico_negativo():
    """Disaccordo sistematico produce kappa negativo, non clampato."""
    a = [0, 1, 2, 3, 4, 5]
    b = [5, 4, 3, 2, 1, 0]
    kappa = weighted_cohen_kappa(a, b, weight="linear")
    assert kappa is not None and kappa < 0.0


def test_weighted_kappa_poco_di_due_coppie_none():
    """Con meno di due coppie sovrapposte kappa e' None."""
    assert weighted_cohen_kappa([3], [3], weight="linear") is None
    assert weighted_cohen_kappa([], [], weight="linear") is None


def test_weighted_kappa_lunghezze_diverse_errore():
    """Vettori di lunghezza diversa sollevano ValueError."""
    with pytest.raises(ValueError, match="stessa lunghezza"):
        weighted_cohen_kappa([0, 1], [0], weight="linear")


def test_weighted_kappa_peso_invalido_errore():
    """Un peso diverso da lineare/quadratico solleva ValueError."""
    with pytest.raises(ValueError, match="weight must be"):
        weighted_cohen_kappa([0, 1], [0, 1], weight="esponenziale")


# ---------------------------------------------------------------------------
# QualityAssessmentGate
# ---------------------------------------------------------------------------


def _make_record(task_id, answer_type, human_score=None, llm_judge_score=None,
                 human_score_a=None, human_score_b=None):
    if human_score is None and human_score_a is not None:
        human_score = human_score_a
    record = {
        "task_id": task_id,
        "answer_type": answer_type,
        "human_score": human_score,
        "llm_judge_score": llm_judge_score,
    }
    if human_score_a is not None:
        record["human_score_a"] = human_score_a
    if human_score_b is not None:
        record["human_score_b"] = human_score_b
    return record


def test_gate_strato_validato_con_tutti_i_criteri_soddisfatti():
    """Uno strata con accordo perfetto e punteggi validi passa il gate."""
    # Coppie di valutatori umani concordi su ogni item (6 item, alpha = 1.0)
    # I punteggi variano fra item ma i due valutatori concordano su ciascuno.
    records = [
        _make_record(f"t{i}", "number", human_score=3 + (i % 3),
                     human_score_a=3 + (i % 3), human_score_b=3 + (i % 3),
                     llm_judge_score=3.0 + (i % 3) * 0.2) for i in range(6)
    ]
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_alpha_ordinal=0.8,
                                  min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.quality_status == "validated"
    assert result.quality_status_per_stratum["number"] == "validated"
    assert result.n_strata_validated == 1
    assert result.strata["number"].alpha_ordinal == pytest.approx(1.0)


def test_gate_soglia_alpha_non_soddisfatta_blocca():
    """Sotto la soglia di alpha preregistrata lo strata non passa."""
    # Disaccordo sistematico: alpha negativo, sotto qualsiasi soglia positiva
    records = [
        _make_record(f"t{i}", "number",
                     human_score_a=i % 2, human_score_b=1 - (i % 2),
                     llm_judge_score=float(i % 2)) for i in range(6)
    ]
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_alpha_ordinal=0.8,
                                  min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.quality_status_per_stratum["number"] != "validated"
    assert "min_alpha_ordinal" in result.strata["number"].failed_criteria


def test_gate_pavimento_numerosita_blocca():
    """Sotto il pavimento di coppie valutabili lo strata e' insufficient_data."""
    # Punteggi variati ma concordi fra i due valutatori; solo 2 coppie < 4 minimo.
    records = [
        _make_record(f"t{i}", "number", human_score=2 + i,
                     human_score_a=2 + i, human_score_b=2 + i) for i in range(2)
    ]
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.quality_status == "insufficient_data"
    assert result.strata["number"].reason.startswith("insufficient_data")


def test_gate_frazione_ammissibile_blocca():
    """Sotto la frazione ammissibile preregistrata lo strata non passa."""
    # 4 coppie valutabili (sopra il pavimento) ma solo 4/11 record valutabili.
    records = [
        _make_record(f"t{i}", "number",
                     human_score_a=2 + i, human_score_b=2 + i) for i in range(4)
    ]
    records += [_make_record(f"x{i}", "number", human_score_a=None,
                             human_score_b=None) for i in range(7)]
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.quality_status_per_stratum["number"] == "not_validated"
    assert "insufficient_admissible_fraction" in result.strata["number"].failed_criteria


def test_gate_partialmente_validato():
    """Se solo uno dei due strata passa, lo stato complessivo e' partially_validato."""
    records = []
    for i in range(6):
        records.append(_make_record(f"n{i}", "number",
                                    human_score_a=1 + (i % 5), human_score_b=1 + (i % 5),
                                    llm_judge_score=3.0))
        records.append(_make_record(f"f{i}", "free_text",
                                    human_score_a=i % 2, human_score_b=1 - (i % 2),
                                    llm_judge_score=float(i % 2)))
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_alpha_ordinal=0.8,
                                  min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number", "free_text"])
    assert result.quality_status == "partially_validated"
    assert result.quality_status_per_stratum["number"] == "validated"
    assert result.quality_status_per_stratum["free_text"] != "validated"


def test_gate_required_strata_vuoto_errore():
    """Una configurazione senza strati obbligatori solleva ValueError."""
    gate = QualityAssessmentGate()
    with pytest.raises(ValueError, match="required_strata"):
        gate.evaluate([], required_strata=())
    with pytest.raises(ValueError, match="required_strata"):
        gate.evaluate([], required_strata=None)


def test_gate_record_fuori_degli_strati_contato_ma_non_valutato():
    """Record con answer_type fuori dagli strata richiesti sono contati
    in diagnostics ma non influenzano lo stato degli strata."""
    records = [_make_record(f"t{i}", "number",
                            human_score_a=1 + (i % 5), human_score_b=1 + (i % 5)) for i in range(6)]
    records.append(_make_record("x", "code", human_score_a=3, human_score_b=3))
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.diagnostics["n_out_of_stratum"] == 1
    assert result.quality_status_per_stratum["number"] == "validated"


def test_gate_indipendente_da_scoring_status():
    """Il gate di qualita non produce chain_status né scoring_status: e'
    indipendente dalla catena di misura energetica e dallo scoring."""
    records = [_make_record(f"t{i}", "number",
                            human_score_a=3, human_score_b=3) for i in range(6)]
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert not hasattr(result, "chain_status")
    assert not hasattr(result, "scoring_status")
    d = result.as_dict()
    assert "chain_status" not in d
    assert "scoring_status" not in d


def test_gate_punteggi_medi():
    """Le medie dei punteggi umani e del giudice LLM sono calcolate correttamente."""
    records = [
        _make_record(f"t{i}", "number", human_score=2 + i,
                     llm_judge_score=2.0 + i * 0.5) for i in range(4)
    ]
    gate = QualityAssessmentGate(QualityAssessmentCriteria())
    result = gate.evaluate(records, required_strata=["number"])
    assert result.overall_mean_human_score == pytest.approx(3.5)
    assert result.overall_mean_llm_judge_score == pytest.approx(2.75)


# ---------------------------------------------------------------------------
# Template di preregistrazione
# ---------------------------------------------------------------------------


def test_template_campi_none_prima_della_registrazione():
    """I criteri di accettazione nel template sono None finche' non registrati."""
    t = quality_protocol_template()
    criteria = t["criteri_di_accettazione"]
    assert all(v is None for v in criteria.values())
    assert t["verifica_umana"]["krippendorff_alpha_ordinal"] is None
    assert t["verifica_umana"]["krippendorff_alpha_interval"] is None
    assert t["campione_indipendente"] is True
    assert len(t["tipologie_di_risposta"]) >= 3


def test_template_nomina_metriche():
    """Il template deve nominare kappa lineare/quadratico e alpha ordinale."""
    t = quality_protocol_template()
    verifica = t["verifica_umana"]
    assert "krippendorff_alpha_ordinal" in verifica
    assert "krippendorff_alpha_interval" in verifica
    assert "cohen_kappa_lineare" in verifica
    assert "cohen_kappa_quadratico" in verifica


def test_template_dichiara_scala_e_pavimento():
    """Il template dichiara la scala 0-5 e il pavimento di coppie valutabili."""
    t = quality_protocol_template()
    assert t["quality_scale"] == [0, 1, 2, 3, 4, 5]
    assert t["verifica_umana"]["min_pairable_items"] == MIN_QUALITY_PAIRABLE
    assert t["verifica_umana"]["min_admissible_fraction"] == MIN_QUALITY_ADMISSIBLE_FRACTION


# ---------------------------------------------------------------------------
# Integrazione con lo schema di valutazione
# ---------------------------------------------------------------------------


def test_extract_quality_records_from_schema():
    """L'estrazione da righe dello schema restituisce record con i campi attesi."""
    rows = [
        {"task_id": "t1", "answer_type": "number", "human_score": 4,
         "llm_judge_score": 3.5, "rubric_scores": {"chiarezza": 5, "completezza": 3}},
        {"task_id": "t2", "answer_type": "short_text", "human_score": None,
         "llm_judge_score": 2.0, "rubric_scores": {}},
        {"task_id": None, "answer_type": "number", "human_score": 3},  # escluso
        {"task_id": "t3", "answer_type": None, "human_score": 3},  # escluso
    ]
    records = extract_quality_records_from_schema(rows)
    assert len(records) == 2
    assert records[0]["task_id"] == "t1"
    assert records[0]["human_score"] == 4
    assert records[0]["llm_judge_score"] == 3.5
    assert records[0]["rubric_scores"] == {"chiarezza": 5, "completezza": 3}
    assert records[1]["task_id"] == "t2"
    assert records[1]["human_score"] is None
    assert records[1]["llm_judge_score"] == 2.0


def test_gate_con_record_estratti_da_schema():
    """Record estratti dallo schema vengono valutati dal gate."""
    rows = [
        {"task_id": f"t{i}", "answer_type": "number",
         "human_score_a": 1 + (i % 5), "human_score_b": 1 + (i % 5),
         "llm_judge_score": 3.0 + (i % 3) * 0.2} for i in range(6)
    ]
    records = extract_quality_records_from_schema(rows)
    gate = QualityAssessmentGate(
        QualityAssessmentCriteria(min_alpha_ordinal=0.8,
                                  min_admissible_fraction=0.5))
    result = gate.evaluate(records, required_strata=["number"])
    assert result.quality_status == "validated"


# ---------------------------------------------------------------------------
# Costanti
# ---------------------------------------------------------------------------


def test_costanti_scala_qualita():
    assert QUALITY_SCALE == (0, 1, 2, 3, 4, 5)
    assert MIN_QUALITY_PAIRABLE == 4
    assert MIN_QUALITY_ADMISSIBLE_FRACTION == 0.5
