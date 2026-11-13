# -*- coding: utf-8 -*-
"""Correzioni P0/P1 del piano (accuratezza/piano.DOCX, Parte 2, §9) su ECPC.

Questi test fissano le correzioni metrologiche al riepilogo per categoria e al
bootstrap di ECPC:

- §9 P0 #4: la copertura di scoring e' la frazione di righe determinate
  (is_correct != null), non la frazione di righe con un'energia o un metodo;
- §9 P0 #5: ECPC_status distingue complete/partial/unavailable, per non
  presentare un subtotale come un costo definitivo;
- §9 P1 #8: ECPC_model (primario, energia del solo modello) separato da
  ECPC_system = (E_model + E_judge)/N_correct (secondario), con E_judge_total;
  ECPC_system non si calcola assumendo zero per l'energia del giudice mancante;
- §9 P1 #9: il bootstrap ricampiona i task e calcola il rapporto COMPLETO
  ΣE/Σ1[correct] a ogni ricampiono (numeratore = energia di TUTTE le righe
  eleggibili, non delle sole corrette), conta i ricampioni a denominatore nullo
  e rifiuta un'identita' di task parziale;
- §2.1/§3.1: final_verdict separato da is_correct (unscored per un ramo gated),
  motivi di N/A canonici e blocco di scoring strutturato nelle notes.

Cosa non verificano: la misura fisica dell'energia (i valori sono sintetici) e
l'esecuzione reale del giudice.
"""

import math

import pytest

from evaluation_runner import (
    CANONICAL_NONE_REASONS,
    canonical_none_reason,
    final_verdict,
    notes_with_scoring_block,
    record_scoring_block,
    summarize_records,
)
from taxonomy_ecpc import _ecpc_bootstrap, compute_taxonomy_ecpc


def _row(verdict, energy, task, category="c", **extra):
    row = {"category": category, "end_to_end": verdict,
           "energy_j": energy, "task_id": task}
    row.update(extra)
    return row


# --- P1 #9: il numeratore del bootstrap e' l'energia di TUTTE le righe ---------


def test_category_ecpc_usa_energia_di_tutte_le_righe_non_solo_corrette():
    """ECPC = ΣE su tutte le righe eleggibili / N_correct: 10+8+5 = 23 J per UNA
    corretta. L'energia spesa negli errori e negli indeterminati e' un costo
    sostenuto; escluderla dal numeratore sottostima il costo per corretta."""
    rows = [_row("correct", 10.0, "T1"),
            _row("incorrect", 8.0, "T2"),
            _row("indeterminate", 5.0, "T3")]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["n_correct"] == 1
    assert cat["eligible_energy_rows"] == 3
    assert cat["ecpc_j"] == pytest.approx(23.0)
    # con tre task distinti e pairs su tutte le righe, il CI e' calcolabile
    assert cat["ecpc_cluster_bootstrap_95"] is not None


def test_category_ecpc_elegibile_come_il_riepilogo_complessivo():
    """La stessa riga non puo' essere eleggibile nel totale complessivo e non
    eleggibile nella sua categoria: l'energia generica senza flag e' accettata
    per compatibilita' in entrambi i lati, con la stessa regola."""
    rows = [_row("correct", 10.0, "T1"), _row("incorrect", 8.0, "T2")]
    summary = summarize_records(rows)
    assert summary["total_energy_j"] == pytest.approx(18.0)
    assert summary["categories"]["c"]["total_energy_j"] == pytest.approx(18.0)


def test_ecpc_bootstrap_conta_ricampioni_a_denominatore_nullo():
    """Un ricampiono che estrae solo task sbagliati ha Σ1[correct]=0: il rapporto
    non esiste e va CONTEGGIATO, non scartato in silenzio. Il conteggio dice
    quanto e' fragile il denominatore."""
    pairs = [(1, 10.0, "T1"), (0, 100.0, "T2")]
    res = _ecpc_bootstrap(pairs, resamples=2000, seed=20261104)
    assert res["interval"] is not None
    assert res["n_zero_denominator"] > 0
    assert res["n_zero_denominator"] + len(res.get("ratios_used", [])) <= 2000 or \
        res["n_zero_denominator"] > 0


def test_ecpc_bootstrap_rifiuta_identita_parziale():
    """Togliere le righe senza task_id cambierebbe il denominatore rispetto al
    punto stimato: come per il bootstrap di accuratezza, un'identita' parziale
    non produce un intervallo su una popolazione diversa."""
    pairs = [(1, 10.0, "T1"), (0, 5.0, "T2"), (1, 3.0, None)]
    res = _ecpc_bootstrap(pairs)
    assert res["interval"] is None
    assert "partial" in res["reason"] or "missing" in res["reason"]


def test_taxonomy_bootstrap_e_punto_stimato_sullo_stesso_estimando():
    """Il punto stimato usa l'energia di tutte le righe (10+100=110 J per una
    corretta); il bootstrap deve ricampionare lo STESSO rapporto. Coi soli
    correct-row il bootstrap avrebbe un solo cluster e nessun intervallo: la
    correzione allinea i due lati."""
    rows = [
        {"category": "c", "end_to_end": "correct",
         "end_to_end_energy_j": 10.0, "active_valid": "True", "task_id": "T1"},
        {"category": "c", "end_to_end": "incorrect",
         "end_to_end_energy_j": 100.0, "active_valid": "True", "task_id": "T2"},
    ]
    cat = compute_taxonomy_ecpc(rows)["by_category"]["c"]
    assert cat["ecpc_j"] == pytest.approx(110.0)
    assert cat["ecpc_cluster_bootstrap_95"] is not None


def test_taxonomy_overall_denominatore_tutte_le_corrette_come_la_categoria():
    """Il denominatore dell'overall e' TUTTE le corrette, non le sole corrette
    con energia: una corretta senza energia eleggibile resta un costo sostenuto
    al numeratore (l'energia delle altre) e un'unita' al denominatore. Con 15 J
    eleggibili e DUE corrette (una senza energia) l'ECPC e' 7,5 sia per categoria
    sia complessivo; dividere per la sola corretta con energia darebbe 15."""
    rows = [
        {"category": "c", "end_to_end": "correct",
         "end_to_end_energy_j": 10.0, "active_valid": "True", "task_id": "T1"},
        {"category": "c", "end_to_end": "correct",
         "end_to_end_energy_j": None, "active_valid": "True", "task_id": "T2"},
        {"category": "c", "end_to_end": "incorrect",
         "end_to_end_energy_j": 5.0, "active_valid": "True", "task_id": "T3"},
    ]
    result = compute_taxonomy_ecpc(rows)
    assert result["by_category"]["c"]["ecpc_j"] == pytest.approx(7.5)
    assert result["overall"]["ecpc_j"] == pytest.approx(7.5)


# --- P0 #4: copertura di scoring = frazione di determinate ---------------------


def test_category_scoring_coverage_e_frazione_di_determinate():
    """Coverage = #{is_correct != null}/N. Due determinate su tre righe (una
    indeterminata) danno 2/3, non 1.0: la vecchia formula contava le righe con
    un'energia o un metodo dichiarato, che non e' la copertura di scoring."""
    rows = [_row("correct", 10.0, "T1"),
            _row("incorrect", 8.0, "T2"),
            _row("indeterminate", 5.0, "T3")]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["scoring_coverage"] == pytest.approx(2 / 3)


# --- P0 #5: ECPC_status complete/partial/unavailable ---------------------------


def test_category_ecpc_status_complete_con_energia_su_tutte_le_righe():
    """Tutte le righe hanno energia eleggibile e c'e' almeno una corretta: il
    costo per corretta e' un totale definitivo, non un subtotale."""
    rows = [_row("correct", 10.0, "T1"), _row("incorrect", 8.0, "T2")]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["ecpc_status"] == "complete"


def test_category_ecpc_status_partial_con_energia_mancante():
    """Una riga senza energia rende il numeratore un subtotale: lo status lo
    dichiara partial, per non presentare 18 J come il costo completo."""
    rows = [_row("correct", 10.0, "T1"),
            _row("incorrect", 8.0, "T2"),
            _row("incorrect", None, "T3")]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["ecpc_status"] == "partial"


def test_category_ecpc_status_unavailable_senza_corrette():
    """Senza corrette il rapporto non esiste: unavailable, non un numero."""
    rows = [_row("incorrect", 8.0, "T1"), _row("indeterminate", 5.0, "T2")]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["ecpc_status"] == "unavailable"
    assert cat["ecpc_j"] is None


# --- P1 #8: ECPC_model / ECPC_system / E_judge_total ---------------------------


def test_ecpc_system_somma_energia_del_giudice_quando_presente_su_tutte():
    """ECPC_model = E_model/N_correct (primario); ECPC_system =
    (E_model+E_judge)/N_correct (secondario). Con 18 J di modello, 3 J di
    giudice e una corretta: model 18, system 21, judge_total 3."""
    rows = [_row("correct", 10.0, "T1", judge_energy_j=2.0),
            _row("incorrect", 8.0, "T2", judge_energy_j=1.0)]
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["ecpc_model_j"] == pytest.approx(18.0)
    assert cat["judge_energy_total_j"] == pytest.approx(3.0)
    assert cat["ecpc_system_j"] == pytest.approx(21.0)


def test_ecpc_system_none_se_energia_giudice_manca_non_assume_zero():
    """Se una riga non ha judge_energy_j, ECPC_system non si calcola: sommare
    zero per l'energia mancante sottostimerebbe il costo di sistema. Il modello
    resta calcolabile e il totale del giudice e' dichiarato parziale."""
    rows = [_row("correct", 10.0, "T1", judge_energy_j=2.0),
            _row("incorrect", 8.0, "T2")]  # niente judge_energy_j
    cat = summarize_records(rows)["categories"]["c"]
    assert cat["ecpc_model_j"] == pytest.approx(18.0)
    assert cat["ecpc_system_j"] is None
    assert "judge" in cat["ecpc_system_reason"].lower()
    assert cat["judge_energy_total_j"] == pytest.approx(2.0)


# --- P0 #3 / §2.1: final_verdict separato da is_correct ------------------------


def test_final_verdict_mappa_correct_incorrect_indeterminate():
    """final_verdict espone il verdetto dichiarato; is_correct e' la sua forma
    booleana. I due non vanno confusi: un verdetto ha quattro stati, is_correct
    tre (true/false/null)."""
    assert final_verdict({"end_to_end": "correct"}) == "correct"
    assert final_verdict({"end_to_end": "incorrect"}) == "incorrect"
    assert final_verdict({"end_to_end": "indeterminate"}) == "indeterminate"


def test_final_verdict_unscored_per_ramo_gated():
    """Un ramo bloccato dal gate di calibrazione resta NON VALUTATO (unscored),
    non indeterminato per fallimento dello scoring: il giudice non e' stato
    chiamato perche' il ramo non e' validato. La distinzione e' §7.1 del piano."""
    gated = {"end_to_end": "indeterminate",
             "verdict_none_reason": "judge_uncalibrated"}
    assert final_verdict(gated) == "unscored"
    failed = {"end_to_end": "indeterminate",
              "verdict_none_reason": "evaluation_failed"}
    assert final_verdict(failed) == "indeterminate"


# --- §3.1 / §3.2: motivi canonici e blocco di scoring strutturato --------------


def test_motivi_di_none_canonici():
    """Il vocabolario dei motivi di N/A e' chiuso ai quattro del piano (§3.1):
    judge_abstained, judge_uncalibrated, evaluation_failed, human_review_required.
    Gli alias legacy sono ricondotti, non lasciati come testo libero."""
    assert set(CANONICAL_NONE_REASONS) == {
        "judge_abstained", "judge_uncalibrated",
        "evaluation_failed", "human_review_required"}
    assert canonical_none_reason("extraction_failed") == "evaluation_failed"
    assert canonical_none_reason("human_gate_blocked") == "human_review_required"
    assert canonical_none_reason("judge_abstained") == "judge_abstained"
    assert canonical_none_reason("") == ""


def test_blocco_scoring_strutturato_roundtrip_nelle_notes():
    """Il blocco CW_SCORING_V1 e' JSON machine-recoverable nelle notes (§3.2),
    non testo libero: si scrive e si rilegge senza perdere il verdetto, e le
    note originali della riga restano intatte (come CW_TASK_ID_V1)."""
    rec = {"notes": "nota originale", "end_to_end": "correct",
           "scoring_method": "deterministic"}
    text = notes_with_scoring_block(rec)
    assert "nota originale" in text
    assert "CW_SCORING_V1=" in text
    block = record_scoring_block({"notes": text})
    assert block["final_verdict"] == "correct"
    assert block["is_correct"] is True
    assert block["scoring_method"] == "deterministic"


def test_blocco_scoring_assente_restituisce_none():
    """Senza il blocco il lettore restituisce None, non un dizionario vuoto che
    sembrerebbe uno scoring registrato."""
    assert record_scoring_block({"notes": "nota senza blocco"}) is None