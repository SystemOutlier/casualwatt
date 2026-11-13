# -*- coding: utf-8 -*-
"""P6.7 / P4.9 — il riepilogo dei tre stati (Opzione A, architettura separata).

L'Opzione A decisa il 2026-11-12 costruisce un unico artefatto,
``calibration_gate_summary.json``, che riepiloga tre stati distinti senza
sovrapporli:

- Gate 1: ``energy_chain_status`` (P4.9, catena energetica), che NON dipende
  dalla calibrazione dello scoring: si calcola sui dati della campagna
  (``validation_chain.chain_status``) e qui viene solo LETTO da un artefatto,
  con il suo digest;
- Gate 2: ``scoring_status`` (P6.7, validazione dello scoring), prodotto da
  ``human_calibration_gate.run_scoring_validation_gate``;
- Gate 3: ``integrated_status`` (``integrate_experiment_status``), che combina
  i due senza cancellare l'informazione originaria.

Questi test fissano il contratto che rende l'opzione A difendibile:

1. pre-campagna nessuno stato viene inventato: i due gate che non hanno ancora
   prodotto un token restano ``null`` con la ragione, e l'integrato resta
   ``null`` -- non ``energy_not_validated``, che sarebbe un verdetto su un
   gate non ancora eseguito;
2. uno scoring ``validated`` NON promuove la catena energetica: senza lo stato
   energetico l'integrato non compare, Con esso l'integrato segue
   ``integrate_experiment_status`` e i due stati originari restano leggibili
   accanto al combinato;
3. i flag ``judge_gated_*`` per evaluator.py escono dal gate quando il gate ha
   girato, e restano ``null`` (con ragione) quando non ha girato: il valutatore
   non cambia comportamento per un dato che non esiste;
4. il tool rifiuta -- senza scrivere nulla -- una configurazione a meta'
   (un campione solo), una sovrapposizione fra campioni e un token energetico
   fuori dal vocabolario chiuso di P4.9;
5. l'artefatto dichiara digest degli input, testa di git e provenienza del
   campione: e' ricostruibile senza riaprire i dati.

Cosa non verificano: il gate (suo test dedicato), la catena energetica (suo
test dedicato) e la campagna reale.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import calibration_gate_summary as tool  # noqa: E402
from human_calibration_gate import (  # noqa: E402
    JudgeAcceptanceCriteria,
    integrate_experiment_status,
    judge_gated_flags,
    run_scoring_validation_gate,
)

CRITERI = JudgeAcceptanceCriteria(
    min_precision_correct=0.90,
    min_recall_correct=0.80,
    max_fp_rate=0.10,
    min_accuracy=0.85,
    min_coverage=0.80,
)

ARTEFATTO = "calibration_gate_summary.json"


def _cal(n=12, etichetta="correct"):
    return [{"task_id": f"cal_number_{i}", "answer_type": "number",
             "annotations": {"annotator_1": etichetta,
                             "annotator_2": etichetta}}
            for i in range(n)]


def _val(n=10, verdetto="correct"):
    return [{"task_id": f"val_number_{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct",
             "judge_verdict": verdetto}
            for i in range(n)]


def _preregistrazione(tmp_path, criteri=CRITERI):
    p = tmp_path / "protocol.json"
    p.write_text(json.dumps({
        "strata": ["number"],
        "verifica_a": {"threshold_alpha": 0.8},
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": criteri.min_precision_correct,
            "min_recall_correct": criteri.min_recall_correct,
            "max_fp_rate": criteri.max_fp_rate,
            "min_accuracy": criteri.min_accuracy,
            "min_coverage": criteri.min_coverage,
        }},
    }, ensure_ascii=False), encoding="utf-8")
    return p


def _scrivi(tmp_path, cal, val):
    cal_file = tmp_path / "cal.jsonl"
    val_file = tmp_path / "val.jsonl"
    cal_file.write_text("\n".join(json.dumps(r) for r in cal), encoding="utf-8")
    val_file.write_text("\n".join(json.dumps(r) for r in val), encoding="utf-8")
    return cal_file, val_file


def _energia(tmp_path, token):
    p = tmp_path / "energy_chain.json"
    p.write_text(json.dumps({"chain_status": token}, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _lancia(tmp_path, cal=None, val=None, prereg=None, energia=None,
            sample_status=None):
    argv = ["--out-dir", str(tmp_path / "out")]
    if cal is not None and val is not None:
        cal_file, val_file = _scrivi(tmp_path, cal, val)
        argv += ["--calibration", str(cal_file), "--validation", str(val_file)]
    elif cal is not None or val is not None:
        solo = cal if cal is not None else val
        file = tmp_path / "solo.jsonl"
        file.write_text("\n".join(json.dumps(r) for r in solo),
                        encoding="utf-8")
        argv += ["--calibration" if cal is not None else "--validation",
                 str(file)]
    if prereg is not None:
        argv += ["--preregistration", str(prereg)]
    if energia is not None:
        argv += ["--energy-chain", str(energia)]
    if sample_status is not None:
        argv += ["--sample-status", sample_status]
    return tool.main(argv), (tmp_path / "out" / ARTEFATTO)


def _leggi(percorso):
    return json.loads(Path(percorso).read_text(encoding="utf-8"))


def _verifica(artefatto, nome):
    for voce in artefatto["campaign_precheck"]:
        if voce["check"] == nome:
            return voce
    raise AssertionError(f"verifica '{nome}' assente dal riepilogo")


# --- 1. Pre-campagna: nessuno stato inventato --------------------------------


def test_precampagna_senza_campioni_dichiara_gli_stati_non_calcolati(tmp_path):
    """Senza campioni ne' catena energetica il riepilogo dice «non calcolato»,
    non «non valido»: un verdetto su un gate che non ha girato sarebbe
    inventato. L'artefatto si scrive ugualmente (codice 0) perche' il suo
    ruolo e' dichiarare lo stato, non emetterlo."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, prereg=prereg)
    assert codice == 0
    assert percorso.exists()
    art = _leggi(percorso)
    assert art["energy_chain_status"] is None
    assert "campagna" in art["energy_chain_status_reason"]
    assert art["scoring_status"] is None
    assert "calibrazione" in art["scoring_status_reason"]
    assert art["integrated_status"] is None
    assert art["judge_gated_flags"] is None
    assert "judge_gated_flags_reason" in art
    assert _verifica(art, "calibration_sample")["status"] == "missing"
    assert _verifica(art, "validation_sample")["status"] == "missing"


def test_precampagna_non_scrive_energy_not_validated(tmp_path):
    """`energy_not_validated` e' il verdetto di Gate 3 su una catena valutata e
    trovata non valida. Pre-campagna la catena non e' stata valutata: scrivere
    quel token sarebbe un verdetto fabbricato su un gate non eseguito."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    assert art["integrated_status"] is None
    assert art["integrated_status"] != "energy_not_validated"
    assert "validation_chain" in art["integrated_status_reason"]


# --- 2. Gate 2 non promuove Gate 1 -------------------------------------------


def test_scoring_validato_non_promuove_la_catena_energetica(tmp_path):
    """Cuore del vincolo dell'Opzione A: uno scoring `validated` con la catena
    energetica assente NON produce `integrated_status`. La catena resta un
    gate autonomo, calcolato altrove sui dati della campagna."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    assert art["scoring_status"] == "validated"
    assert art["energy_chain_status"] is None
    assert art["integrated_status"] is None
    assert art["integrated_status"] != "validated"


def test_con_entrambi_gli_stati_integra_senza_cancellare(tmp_path):
    """Con lo stato energetico `validated` letto dall'artefatto della campagna,
    Gate 3 combina: `integrated_status == "validated"` e i due stati originari
    restano leggibili accanto al combinato (nessuna cancellazione)."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "validated")
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg,
                               energia=energia)
    assert codice == 0
    art = _leggi(percorso)
    assert art["energy_chain_status"] == "validated"
    assert art["scoring_status"] == "validated"
    assert art["integrated_status"] == "validated"
    assert art["input_digests"]["energy_chain"] == _digest(energia)


def test_catena_energetica_non_valida_blocca_lintegrato(tmp_path):
    """Una catena `bias_declared` (il verdetto del gate P4.4 eseguito l'08-11)
    con scoring validato da' `energy_not_validated`: lo scoring non la promuove
    e i due stati originari restano dichiarati."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "bias_declared")
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg,
                               energia=energia)
    assert codice == 0
    art = _leggi(percorso)
    assert art["energy_chain_status"] == "bias_declared"
    assert art["scoring_status"] == "validated"
    assert art["integrated_status"] == "energy_not_validated"


def test_scoring_insufficiente_blocca_lintegrato(tmp_path):
    """Con la catena validata ma il campione sotto il pavimento preregistrato,
    lo scoring e' `not_validated` (per ramo `insufficient_data`) e l'integrato
    e' `scoring_not_validated`: un residuo di campione non e' un verdetto."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "validated")
    codice, percorso = _lancia(tmp_path, cal=_cal(n=2), val=_val(n=2),
                               prereg=prereg, energia=energia)
    assert codice == 0
    art = _leggi(percorso)
    assert art["scoring_status"] == "not_validated"
    assert art["scoring_status_per_stratum"]["number"] == "insufficient_data"
    assert art["integrated_status"] == "scoring_not_validated"


def test_integrato_coincide_col_combinatore_del_gate(tmp_path):
    """L'integrato non e' una regola propria del tool: e' esattamente
    `integrate_experiment_status` applicata ai due stati letti. Se il tool
    implementasse una combinatoria diversa, i due numeri divergerebbero."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "counter_invalid")
    cal, val = _cal(), _val()
    codice, percorso = _lancia(tmp_path, cal=cal, val=val, prereg=prereg,
                               energia=energia)
    assert codice == 0
    art = _leggi(percorso)
    atteso = integrate_experiment_status(art["energy_chain_status"],
                                        art["scoring_status"])
    assert art["integrated_status"] == atteso


# --- 3. I flag judge_gated per evaluator.py ----------------------------------


def test_flags_giudice_dal_gate_quando_il_gate_ha_girato(tmp_path):
    """Con il gate eseguito e il ramo promosso, i flag `judge_gated_*` sono
    quelli del produttore unico (`judge_gated_flags`): False, il valutatore
    usa il giudice come prima. Il tool non li riscrive per conto suo."""
    prereg = _preregistrazione(tmp_path)
    cal, val = _cal(), _val()
    codice, percorso = _lancia(tmp_path, cal=cal, val=val, prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    attesi = judge_gated_flags(run_scoring_validation_gate(
        *(tmp_path / n for n in ("cal.jsonl", "val.jsonl")),
        criteria=CRITERI, required_strata=("number",), threshold=0.8))
    assert art["judge_gated_flags"] == attesi
    assert art["judge_gated_flags"] == {"judge_gated_number": False}


def test_flag_true_su_ramo_giudice_non_validato(tmp_path):
    """Un ramo il cui giudice sbaglia sistematicamente (riferimento corretto,
    verdetto `incorrect`) resta `judge_uncalibrated`: il flag e' True per quel
    ramo. Un ramo bloccato resta non valutato, non `incorrect`."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, cal=_cal(),
                               val=_val(verdetto="incorrect"), prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    assert art["scoring_status_per_stratum"]["number"] == "judge_uncalibrated"
    assert art["judge_gated_flags"] == {"judge_gated_number": True}


def test_flags_nulli_precampagna_non_cambiano_il_valutatore(tmp_path):
    """Senza campioni i flag sono `null` con la ragione: il valutatore tiene il
    suo default (giudice abilitato) e il tool non inventa un blocco ne' uno
    sblocco. La ragione nomina il consumatore (evaluator.py)."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    assert art["judge_gated_flags"] is None
    assert "evaluator" in art["judge_gated_flags_reason"]


# --- 4. Rifiuti fail-closed --------------------------------------------------


def test_sovrapposizione_fra_campioni_rifiutata_senza_scrivere(tmp_path):
    """Gli stessi task_id in calibrazione e validazione violano
    l'indipendenza del campione: il loader del gate rifiuta e il riepilogo non
    scrive nulla (nessun artefatto a meta' di un rifiuto)."""
    prereg = _preregistrazione(tmp_path)
    cal = _cal()
    val = _val()
    val[0] = dict(val[0], task_id=cal[0]["task_id"])
    codice, percorso = _lancia(tmp_path, cal=cal, val=val, prereg=prereg)
    assert codice == 1
    assert not percorso.exists()


def test_un_solo_campione_rifiutato(tmp_path):
    """Configurazione a meta': con un campione solo il gate non e' eseguibile e
    un riepilogo «valutato su mezzo disegno» sarebbe peggio di un rifiuto."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, cal=_cal(), prereg=prereg)
    assert codice == 1
    assert not percorso.exists()


def test_token_energetico_fuori_vocabolario_rifiutato(tmp_path):
    """Il token energetico deve appartvenire al vocabolario chiuso di P4.9
    (`validation_chain.STATUS_LABELS`): un token arbitrario verrebbe letto da
    `integrate_experiment_status` come «non validato» e il riepilogo
    riporterebbe una catena fallita per un refuso."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "pass")
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg,
                               energia=energia)
    assert codice == 1
    assert not percorso.exists()


# --- 5. Provenienza dell'artefatto -------------------------------------------


def test_digesti_provenienza_e_stato_campione_dichiarati(tmp_path):
    """L'artefatto e' ricostruibile senza riaprire i dati: digest SHA-256 dei
    tre input, testa di git (o la ragione per cui non e' leggibile), stato del
    campione dichiarato dall'operatore e configurazione usata."""
    prereg = _preregistrazione(tmp_path)
    cal, val = _cal(), _val()
    codice, percorso = _lancia(tmp_path, cal=cal, val=val, prereg=prereg,
                               sample_status="technical_fixture")
    assert codice == 0
    art = _leggi(percorso)
    assert art["input_digests"]["calibration"] == _digest(tmp_path / "cal.jsonl")
    assert art["input_digests"]["validation"] == _digest(tmp_path / "val.jsonl")
    assert art["input_digests"]["preregistration"] == _digest(prereg)
    assert art["sample_status"] == "technical_fixture"
    assert art["git_head"] or art["git_head_reason"]
    assert art["preregistration_used"]["criteria_registered"] is True


def test_note_dichiarano_la_separazione_dei_gate_e_il_ruolo_di_alpha(tmp_path):
    """Le note dell'artefatto dicono cio' che i numeri non dicono: i due gate
    sono separati, alpha e' necessaria-non-sufficiente, un ramo bloccato resta
    non valutato. Senza questa prosa un lettore potrebbe leggere
    `energy_not_validated` come un difetto dello scoring."""
    prereg = _preregistrazione(tmp_path)
    energia = _energia(tmp_path, "bias_declared")
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg,
                               energia=energia)
    assert codice == 0
    art = _leggi(percorso)
    note = art["notes"]
    assert "Gate 1" in note and "Gate 2" in note
    assert "necessaria" in note and "sufficiente" in note
    assert "judge_uncalibrated" in note
    assert "P4.9" in note and "P6.7" in note
    assert "validity_note" in art


def test_artefatto_non_contiene_metriche_proprie(tmp_path):
    """Il tool non e' un secondo produttore di metriche: il riepilogo riporta
    gli stati del gate, non numeri ricalcolati. `alpha_nominal` e la matrice
    di confusione stanno nei due report del tool dedicato, non qui."""
    prereg = _preregistrazione(tmp_path)
    codice, percorso = _lancia(tmp_path, cal=_cal(), val=_val(), prereg=prereg)
    assert codice == 0
    art = _leggi(percorso)
    assert "alpha_nominal" not in art
    assert "confusion" not in art
    assert "verifica_a" not in art
