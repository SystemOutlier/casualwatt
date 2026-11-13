# -*- coding: utf-8 -*-
"""P6.7 — il gate di validazione dello scoring separa due verifiche distinte.

La correzione P0 del piano (accuratezza/piano.DOCX, Parte 2, §1.1 e §7) e'
che Krippendorff's alpha misura l'accordo fra annotatori umani, NON la
validita' del giudice LLM: un accordo umano del 95% puo' coesistere con un
giudice che sbaglia sistematicamente il 20% dei casi. Questi test fissano
quindi:

- Verifica A: alpha NOMINALE (le etichette correct/incorrect/N/A non sono
  una scala ordinata), accordo percentuale, distribuzione dei disaccordi,
  numerosita' per strato e intervallo bootstrap riproducibile;
- Verifica B: accuratezza, precisione/recall delle due classi, tasso di
  falsi positivi, astensione e matrice di confusione del giudice contro il
  riferimento umano adjudicato, con criteri di accettazione preregistrati;
- il gate produce ``scoring_status`` per ramo e NON tocca la catena di
  validazione energetica P4.9 (``energy_chain_status`` resta indipendente);
- il campione di validazione e' indipendente da quello di calibrazione;
- un ramo bloccato resta non valutato, non diventa ``incorrect``.

Cosa non verificano: l'esecuzione reale del giudice (i verdetti qui sono
dati sintetici) e la campagna di misura.
"""

import json
import math
import tempfile
from pathlib import Path

import pytest

from human_calibration_gate import (
    CALIBRATION_THRESHOLD,
    MIN_ADMISSIBLE_FRACTION,
    MIN_DECIDED_ITEMS,
    MIN_PAIRABLE_ITEMS,
    JudgeAcceptanceCriteria,
    adjudicated_reference,
    bootstrap_alpha_ci,
    calibration_protocol_template,
    calibration_sample_template,
    cohen_kappa_nominal,
    integrate_experiment_status,
    judge_gated_flags,
    krippendorff_alpha,
    run_scoring_validation_gate,
    verifica_a,
    verifica_b,
)


def _annotations(stratum, n, agree=True):
    """n item con due annotatori concordi (o discordanti sugli item dispari)."""
    items = []
    for i in range(n):
        label = "correct" if i % 2 == 0 else "incorrect"
        other = label if agree or i % 2 == 0 else (
            "incorrect" if label == "correct" else "correct")
        items.append({
            "task_id": f"{stratum}_{i}",
            "answer_type": stratum,
            "annotator_1": label,
            "annotator_2": other,
        })
    return items


def _criteria():
    return JudgeAcceptanceCriteria(
        min_precision_correct=0.90,
        min_recall_correct=0.80,
        max_fp_rate=0.10,
        min_accuracy=0.85,
        min_coverage=0.80,
    )


# --- Verifica A: accordo umano ------------------------------------------------


def test_alpha_nominale_accordo_perfetto_vale_uno():
    """Due annotatori sempre concordi producono alpha = 1: e' il limite
    superiore del coefficiente e il caso in cui il riferimento e' banalmente
    consolidato."""
    data = [["correct", "correct"], ["incorrect", "incorrect"]] * 5
    assert krippendorff_alpha(data, level="nominal") == pytest.approx(1.0)


def test_alpha_nominale_disaccordo_sistematico_resta_negativo():
    """Un disaccordo sistematico (annotatore 2 inverta sempre l'etichetta)
    produce alpha < 0. Il valore negativo NON va clampato a zero: dice che
    l'accordo e' peggiore del caso, informazione che il clamp cancellerebbe."""
    data = [["correct", "incorrect"], ["incorrect", "correct"]] * 5
    assert krippendorff_alpha(data, level="nominal") < 0.0


def test_alpha_ordinale_rifiutato_per_etichette_categoriali():
    """correct/incorrect/N/A non sono livelli di una scala di intensita':
    chiedere un alpha ordinale senza una scala ordinata dichiarata deve
    sollevare, non calcolare un numero con una metrica di distanza inventata."""
    with pytest.raises(ValueError):
        krippendorff_alpha([["correct", "incorrect"]], level="ordinal")


def test_verifica_a_riporta_numerosita_accordo_e_disaccordi():
    """Il piano (§1.2-1.3) chiede, accanto al coefficiente, l'accordo
    percentuale, la distribuzione dei disaccordi e il numero effettivo di
    item per strato: un alpha su pochi item non e' la stessa evidenza di un
    alpha su centinaia di annotazioni."""
    ann = _annotations("number", 10, agree=False)
    result = verifica_a(ann, required_strata=("number",))
    s = result["number"]
    assert s.n_items == 10
    assert s.percent_agreement == pytest.approx(0.5)
    assert sum(s.disagreements.values()) == 5
    assert s.class_distribution["correct"] == 5
    assert s.alpha_nominal is not None


def test_verifica_a_soglia_si_applica_all_accordo_umano():
    """La soglia 0.8 e' un criterio operativo sull'accordo fra annotatori
    (§1.4): con meta' degli item discordanti il ramo non la supera."""
    ann = _annotations("number", 12, agree=False)
    result = verifica_a(ann, required_strata=("number",))
    assert result["number"].passed is False
    assert result["number"].alpha_nominal < CALIBRATION_THRESHOLD


def test_intervallo_bootstrap_di_alpha_e_riproducibile():
    """L'intervallo per alpha ricampiona gli ITEM (i due annotatori viaggiano
    insieme), con seed fissato: due esecuzioni con lo stesso seed devono
    coincidere, perche' il numero pubblicato deve essere rigenerabile."""
    units = [["correct", "correct"], ["incorrect", "incorrect"],
             ["correct", "incorrect"], ["incorrect", "incorrect"]] * 4
    ci1 = bootstrap_alpha_ci(units, resamples=200, seed=20261104)
    ci2 = bootstrap_alpha_ci(units, resamples=200, seed=20261104)
    assert ci1 == ci2
    assert ci1 is not None and ci1[0] <= ci1[1]


def test_intervallo_bootstrap_non_calcolabile_su_un_solo_item():
    """Con un solo item ogni ricampiono riproduce lo stesso alpha: un
    intervallo di ampiezza zero sarebbe certezza fabbricata, quindi None."""
    assert bootstrap_alpha_ci([["correct", "correct"]], resamples=50) is None


def test_riferimento_adjudicato_consolida_i_disaccordi():
    """Il riferimento consolidato (§1.1, Verifica A) usa l'etichetta concorde
    dove c'e' accordo e l'adjudication dove c'e' disaccordo; un disaccordo
    senza adjudication NON produce un riferimento e viene contato."""
    ann = [
        {"task_id": "a", "annotator_1": "correct", "annotator_2": "correct"},
        {"task_id": "b", "annotator_1": "correct", "annotator_2": "incorrect",
         "adjudicated": "incorrect"},
        {"task_id": "c", "annotator_1": "correct", "annotator_2": "incorrect"},
    ]
    reference, stats = adjudicated_reference(ann)
    assert reference == {"a": "correct", "b": "incorrect"}
    assert stats["n_disagreements"] == 2
    assert stats["n_adjudicated"] == 1
    assert stats["n_without_reference"] == 1


# --- Verifica A: Cohen's kappa nominale (metrica complementare) ---------------


def test_kappa_nominale_accordo_perfetto_vale_uno():
    """Due annotatori sempre concordi su due classi producono kappa = 1:
    p_o = 1, p_e = 0.5, (1 - 0.5)/(1 - 0.5) = 1. E' il limite superiore del
    coefficiente, distinto dal caso degenere di una classe sola."""
    data = [["correct", "correct"], ["incorrect", "incorrect"]] * 5
    assert cohen_kappa_nominal(data) == pytest.approx(1.0)


def test_kappa_nominale_accordo_da_caso_vale_zero():
    """Quando l'accordo osservato eguaglia quello atteso dal caso (p_o = p_e)
    kappa = 0: le etichette non portano informazione oltre la distribuzione
    marginale. Qui p_o = 2/4 = 0.5 e p_e = 0.5."""
    data = [["correct", "correct"], ["correct", "incorrect"],
            ["incorrect", "correct"], ["incorrect", "incorrect"]]
    assert cohen_kappa_nominal(data) == pytest.approx(0.0)


def test_kappa_nominale_valore_misto_noto():
    """Valore calcolato a mano: 6 coppie (correct,correct), 2 (correct,
    incorrect), 2 (incorrect,incorrect). p_o = 8/10; marginali annotatore 1
    {correct:8, incorrect:2}, annotatore 2 {correct:6, incorrect:4};
    p_e = 0.8*0.6 + 0.2*0.4 = 0.56; kappa = 0.24/0.44 = 6/11."""
    data = ([["correct", "correct"]] * 6 + [["correct", "incorrect"]] * 2
            + [["incorrect", "incorrect"]] * 2)
    assert cohen_kappa_nominal(data) == pytest.approx(6 / 11)


def test_kappa_nominale_disaccordo_sistematico_resta_negativo():
    """Annotatore 2 inverta sempre l'etichetta: p_o = 0, p_e = 0.5,
    kappa = -1. Il valore negativo NON va clampato: dice che l'accordo e'
    peggiore del caso, come per alpha."""
    data = [["correct", "incorrect"], ["incorrect", "correct"]] * 5
    assert cohen_kappa_nominal(data) == pytest.approx(-1.0)


def test_kappa_nominale_classe_sola_non_definito():
    """Una sola classe su tutti gli item (tutti correct): p_e = 1, il
    denominatore (1 - p_e) si annulla e kappa NON e' definito. Restituisce
    None, non un valore inventato. Nota: alpha qui vale 1.0 per convenzione
    degenere, kappa None: i due coefficienti divergono proprio su questo caso."""
    data = [["correct", "correct"]] * 5
    assert cohen_kappa_nominal(data) is None
    assert krippendorff_alpha(data, level="nominal") == pytest.approx(1.0)


def test_kappa_nominale_indeterminate_e_terza_classe_nominale():
    """Indeterminate partecipa come terza classe nominale, non come livello
    intermedio ne' come valore scartato: 3 (correct,correct), 3 (incorrect,
    incorrect), 3 (indeterminate,indeterminate), 1 (correct,indeterminate).
    p_o = 9/10; p_e = (4*3 + 3*3 + 3*4)/100 = 0.33; kappa = 0.57/0.67 = 57/67.
    Se indeterminate fosse ignorato o ordinato, il numero sarebbe diverso."""
    data = ([["correct", "correct"]] * 3 + [["incorrect", "incorrect"]] * 3
            + [["indeterminate", "indeterminate"]] * 3
            + [["correct", "indeterminate"]])
    assert cohen_kappa_nominal(data) == pytest.approx(57 / 67)


def test_kappa_nominale_meno_di_due_coppie_non_definito():
    """Con una sola coppia utilizzabile (o item con un annotatore mancante)
    kappa non e' calcolabile: None, coerentemente con alpha che richiede
    almeno due item pairable."""
    assert cohen_kappa_nominal([["correct", "correct"]]) is None
    assert cohen_kappa_nominal([["correct", None],
                                ["correct", "correct"]]) is None


def test_verifica_a_espone_kappa_nominale_e_ragione():
    """verifica_a riporta kappa_nominal accanto ad alpha, con la stessa
    popolazione di item pairable: su due classi concordi kappa = 1.0 e
    kappa_reason vuota. La soglia e il passed restano quelli di alpha."""
    ann = _annotations("number", 10, agree=True)
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.kappa_nominal == pytest.approx(1.0)
    assert s.kappa_reason == ""
    assert s.passed is True


def test_verifica_a_kappa_non_definito_su_classe_sola_con_ragione():
    """Un ramo con una sola classe (tutti correct) ha alpha = 1.0 (passed)
    ma kappa non definito: kappa_nominal None e kappa_reason che nomina
    p_e = 1. Il passed di alpha NON cambia: kappa e' una metrica riportata."""
    ann = [{"task_id": f"n{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}
           for i in range(6)]
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.alpha_nominal == pytest.approx(1.0)
    assert s.passed is True
    assert s.kappa_nominal is None
    assert "p_e" in s.kappa_reason


def test_verifica_a_kappa_non_calcolabile_su_pochi_item_con_ragione():
    """Meno di due item pairable: kappa_nominal None con ragione che nomina
    la numerosita' insufficiente, distinta dalla ragione p_e = 1."""
    ann = [{"task_id": "n0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}]
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.kappa_nominal is None
    assert s.kappa_reason != ""
    assert "p_e" not in s.kappa_reason


# --- Verifica B: validita' del giudice ----------------------------------------


def _validation_items():
    """Campione sintetico con matrice di confusione nota.

    Riferimento umano: 6 correct, 4 incorrect.
    Giudice: sui 6 correct -> 5 correct, 1 incorrect;
             sui 4 incorrect -> 1 correct (falso positivo), 2 incorrect,
             1 astenuto.
    Quindi: accuracy sui decisi = 7/9, precision_correct = 5/6,
    recall_correct = 5/6, fp_rate = 1/3, astensione = 1/10.
    """
    items = []
    for i in range(6):
        items.append({"task_id": f"v_c{i}", "answer_type": "free_text",
                      "reference": "correct",
                      "judge_verdict": "correct" if i < 5 else "incorrect"})
    for i in range(4):
        verdict = ("correct" if i == 0 else
                   "incorrect" if i < 3 else "indeterminate")
        items.append({"task_id": f"v_i{i}", "answer_type": "free_text",
                      "reference": "incorrect", "judge_verdict": verdict})
    return items


def test_verifica_b_matrice_di_confusione_e_metriche():
    """La validita' del giudice si misura contro il riferimento adjudicato
    con la matrice di confusione completa: accuratezza sui decisi,
    precisione/recall di entrambe le classi, falsi positivi e astensione.
    I valori attesi sono calcolati a mano sul campione sintetico."""
    result = verifica_b(_validation_items(), _criteria(),
                        required_strata=("free_text",))
    v = result["free_text"]
    assert v.n_items == 10
    assert v.n_decided == 9
    assert v.confusion["correct"]["correct"] == 5
    assert v.confusion["correct"]["incorrect"] == 1
    assert v.confusion["incorrect"]["correct"] == 1
    assert v.confusion["incorrect"]["incorrect"] == 2
    assert v.confusion["incorrect"]["abstained"] == 1
    assert v.accuracy == pytest.approx(7 / 9)
    assert v.precision_correct == pytest.approx(5 / 6)
    assert v.recall_correct == pytest.approx(5 / 6)
    assert v.precision_incorrect == pytest.approx(2 / 3)
    assert v.recall_incorrect == pytest.approx(2 / 3)
    assert v.fp_rate == pytest.approx(1 / 3)
    assert v.abstention_rate == pytest.approx(0.1)
    assert v.coverage == pytest.approx(0.9)
    assert v.accuracy_ci_95 is not None


def test_verifica_b_falso_positivo_blocca_il_ramo():
    """Il caso che la vecchia architettura non vedeva (§1.1): l'accordo
    umano puo' essere perfetto e il giudice sbagliare sistematicamente.
    Con fp_rate 1/3 > max_fp_rate 0.10 il ramo e' bloccato anche se
    l'accuratezza complessiva fosse alta."""
    result = verifica_b(_validation_items(), _criteria(),
                        required_strata=("free_text",))
    v = result["free_text"]
    assert v.passed is False
    assert "max_fp_rate" in v.failed_criteria


def test_verifica_b_criteri_non_registrati_bloccano():
    """Il piano (§1.4) non fissa numeri definitivi senza conoscere la
    distribuzione dei task: senza criteri preregistrati il gate deve
    dichiararsi non eseguibile, non promuovere il giudice con soglie
    inventate al momento."""
    result = verifica_b(_validation_items(), JudgeAcceptanceCriteria(),
                        required_strata=("free_text",))
    assert result["free_text"].passed is False
    assert "criteria_not_registered" in result["free_text"].failed_criteria


def test_verifica_b_giudice_valido_supera_tutti_i_criteri():
    """Un giudice con 9/10 corretti, un solo errore e nessuna astensione
    supera i criteri preregistrati: il gate deve poter promuovere, non
    solo bloccare."""
    items = [{"task_id": f"g{i}", "answer_type": "number",
              "reference": "correct" if i < 5 else "incorrect",
              "judge_verdict": "correct" if i < 5 else "incorrect"}
             for i in range(10)]
    items[9]["judge_verdict"] = "correct"  # un falso positivo su 5 incorrect
    result = verifica_b(items, _criteria(), required_strata=("number",))
    v = result["number"]
    assert v.fp_rate == pytest.approx(0.2)
    assert v.passed is False  # fp 0.2 > 0.10: il criterio morde davvero
    items[9]["judge_verdict"] = "incorrect"
    result = verifica_b(items, _criteria(), required_strata=("number",))
    assert result["number"].passed is True


@pytest.mark.parametrize("valore", [0, 0.0, -0.5, float("nan")])
def test_soglia_di_coverage_degenere_non_e_preregistrabile(valore):
    """E2: una soglia di coverage nulla, negativa o non definita non esclude
    nulla -- un giudice che si astiene su ogni item la soddisfa -- quindi non
    e' un criterio scientificamente significativo. Il rifiuto arriva alla
    costruzione dei criteri, prima dei dati, e NON inventa una soglia al posto
    di quella dichiarata: la soglia resta un campo da preregistrare, e il
    valore ammesso e' positivo."""
    with pytest.raises(ValueError, match="min_coverage"):
        JudgeAcceptanceCriteria(
            min_precision_correct=0.90,
            min_recall_correct=0.80,
            max_fp_rate=0.10,
            min_accuracy=0.85,
            min_coverage=valore,
        )


def test_giudice_con_astenioni_massicce_non_e_validato_da_una_soglia_nullativa(tmp_path):
    """E2 end-to-end con i numeri dell'audit: 30 item di validazione, il
    giudice ne decide 3 e si astiene su 27 (copertura 0,100). Tutti gli altri
    criteri sono calcolati sui 3 decisi e li passano: con la soglia di
    coverage preregistrata a 0,0 il ramo risultava validated -- e la soglia
    nulla non e' piu' costruibile, quindi il falso positivo non e' configurabile.
    Con una soglia che discriminera' davvero (0,80) lo stesso dato non passa: il
    ramo e' judge_uncalibrated con min_coverage fra i criteri falliti."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct" if i < 3 else "indeterminate"}
           for i in range(30)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    v = result.validity[0]
    assert v.n_decided == 3
    assert v.coverage == pytest.approx(0.1)
    assert "min_coverage" in v.failed_criteria
    assert result.scoring_status_per_stratum["number"] == "judge_uncalibrated"


# --- Verifica B: F1 per classe (metrica riportata) ----------------------------


def test_verifica_b_f1_per_classe_valore_noto():
    """Sul campione sintetico F1_correct = 5/6 e F1_incorrect = 2/3, derivati
    dalle precision/recall gia' prodotte (P = R per entrambe le classi, quindi
    F1 = P = R). F1 e' riportata, con ragione vuota quando calcolabile."""
    v = verifica_b(_validation_items(), _criteria(),
                   required_strata=("free_text",))["free_text"]
    assert v.f1_correct == pytest.approx(5 / 6)
    assert v.f1_incorrect == pytest.approx(2 / 3)
    assert v.f1_reason == ""


def test_verifica_b_f1_per_classe_precision_recall_asimmetriche():
    """F1 con precision != recall, calcolata a mano: 5 riferimenti correct
    (4 judge correct, 1 incorrect) e 3 incorrect (2 judge correct, 1 incorrect).
    P_correct = 4/6, R_correct = 4/5 -> F1 = 8/11; P_incorrect = 1/2,
    R_incorrect = 1/3 -> F1 = 2/5. I denominatori di precision/recall non
    cambiano: F1 li riusa senza ricalcolarli."""
    items = []
    for i in range(5):
        items.append({"task_id": f"c{i}", "answer_type": "number",
                      "reference": "correct",
                      "judge_verdict": "correct" if i < 4 else "incorrect"})
    for i in range(3):
        items.append({"task_id": f"i{i}", "answer_type": "number",
                      "reference": "incorrect",
                      "judge_verdict": "correct" if i < 2 else "incorrect"})
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.precision_correct == pytest.approx(4 / 6)
    assert v.recall_correct == pytest.approx(4 / 5)
    assert v.f1_correct == pytest.approx(8 / 11)
    assert v.precision_incorrect == pytest.approx(1 / 2)
    assert v.recall_incorrect == pytest.approx(1 / 3)
    assert v.f1_incorrect == pytest.approx(2 / 5)


def test_verifica_b_f1_non_calcolabile_quando_precision_piu_recall_zero():
    """Giudice che inverte sistematicamente: cc=0, ii=0, ci=2, ic=2.
    P_correct = R_correct = 0 (somma 0) e P_incorrect = R_incorrect = 0:
    F1 non calcolabile per entrambe le classi, None con ragione che nomina
    precision + recall. Nessun valore inventato (es. 0 al posto di None)."""
    items = []
    for i in range(2):
        items.append({"task_id": f"c{i}", "answer_type": "number",
                      "reference": "correct", "judge_verdict": "incorrect"})
    for i in range(2):
        items.append({"task_id": f"i{i}", "answer_type": "number",
                      "reference": "incorrect", "judge_verdict": "correct"})
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.precision_correct == pytest.approx(0.0)
    assert v.recall_correct == pytest.approx(0.0)
    assert v.f1_correct is None
    assert v.f1_incorrect is None
    assert v.f1_reason != ""
    assert "precision" in v.f1_reason


def test_verifica_b_f1_non_calcolabile_se_precision_non_definita():
    """Quando non esistono verdetti correct del giudice (cc+ic=0) la
    precision_correct e' None (0/0): F1_correct non calcolabile, mentre
    F1_incorrect resta definita (3/4). Le due classi sono indipendenti e
    indeterminate non entra come classe di riferimento."""
    items = []
    for i in range(2):
        items.append({"task_id": f"c{i}", "answer_type": "number",
                      "reference": "correct", "judge_verdict": "incorrect"})
    for i in range(3):
        items.append({"task_id": f"i{i}", "answer_type": "number",
                      "reference": "incorrect", "judge_verdict": "incorrect"})
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.precision_correct is None
    assert v.f1_correct is None
    assert v.f1_incorrect == pytest.approx(3 / 4)
    assert v.f1_reason != ""


def test_verifica_b_f1_non_modifica_i_criteri_di_accettazione():
    """F1 e' una metrica riportata (Opzione 1): non aggiunge criteri ne'
    cambia passed/failed_criteria. Sul campione sintetico il ramo resta
    bloccato da min_precision_correct, max_fp_rate e min_accuracy, esattamente
    come prima dell'introduzione di F1."""
    v = verifica_b(_validation_items(), _criteria(),
                   required_strata=("free_text",))["free_text"]
    assert v.passed is False
    assert v.failed_criteria == ("min_precision_correct", "max_fp_rate",
                                 "min_accuracy")
    assert not any("f1" in c for c in v.failed_criteria)


# --- Gate complessivo: due gate indipendenti ----------------------------------


def _write_jsonl(path, items):
    path.write_text("\n".join(json.dumps(i) for i in items), encoding="utf-8")


def test_gate_produce_scoring_status_non_chain_status(tmp_path):
    """La correzione architetturale P0 (§7): la validita' dello scoring e'
    una proprieta' diversa dalla validita' della misura energetica. Il
    risultato espone scoring_status per ramo e complessivo, e non produce
    alcun chain_status energetico."""
    cal = []
    for stratum in ("number", "short_text", "free_text"):
        cal.extend(_annotations(stratum, 12, agree=True))
    val = []
    for stratum in ("number", "short_text", "free_text"):
        for i in range(10):
            val.append({"task_id": f"val_{stratum}_{i}", "answer_type": stratum,
                        "annotator_1": "correct", "annotator_2": "correct",
                        "judge_verdict": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria())
    assert result.scoring_status == "validated"
    assert result.scoring_status_per_stratum["number"] == "validated"
    assert not hasattr(result, "chain_status")
    exported = json.loads(json.dumps(result.__dict__, default=lambda o: o.__dict__))
    assert "chain_status" not in exported


def test_gate_per_ramo_non_blocca_gli_altri_rami(tmp_path):
    """§7.1: se il giudice non e' affidabile su free_text non deve essere
    disabilitato su number. Il giudice del free_text qui sbaglia meta' dei
    correct; number e short_text restano validi."""
    cal = []
    for stratum in ("number", "short_text", "free_text"):
        cal.extend(_annotations(stratum, 12, agree=True))
    val = []
    for stratum in ("number", "short_text", "free_text"):
        for i in range(10):
            reference = "correct" if i < 5 else "incorrect"
            if stratum == "free_text" and i < 5:
                verdict = "correct" if i < 2 else "incorrect"
            else:
                verdict = reference
            val.append({"task_id": f"val_{stratum}_{i}", "answer_type": stratum,
                        "annotator_1": reference, "annotator_2": reference,
                        "judge_verdict": verdict})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria())
    assert result.scoring_status_per_stratum["number"] == "validated"
    assert result.scoring_status_per_stratum["short_text"] == "validated"
    assert result.scoring_status_per_stratum["free_text"] == "judge_uncalibrated"
    assert result.scoring_status == "partially_validated"
    flags = judge_gated_flags(result)
    assert flags["judge_gated_free_text"] is True
    assert flags["judge_gated_number"] is False


def test_campione_di_validazione_deve_essere_indipendente(tmp_path):
    """§1.3: gli stessi item non possono servire sia per modificare la
    rubrica sia per dichiarare il giudice validato. La sovrapposizione di
    task_id fra calibrazione e validazione e' un errore dichiarato."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": "number_0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"}]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError):
        run_scoring_validation_gate(cal_file, val_file, _criteria())


# --- Identita' dei record: un dato anonimo non entra nel gate ------------------
#
# Rilievo 3.4 della revisione correttiva (Fase 1). L'indipendenza fra
# calibrazione e validazione e' un PREREQUISITO del gate: il controllo opera
# per task_id, quindi un record senza identita' verificabile non e' un difetto
# di contenuto da contare in diagnostica -- e' un record che quel controllo non
# puo' vedere, e la stessa osservazione potrebbe comparire due volte, una
# volta anonima. Il gate rifiuta il file invece di escludere in silenzio.


def test_task_id_assente_nella_calibrazione_e_rifiutato(tmp_path):
    """3.4: un record di calibrazione senza task_id non ha identita'
    verificabile. Il gate rifiuta il file: la sua indipendenza dal campione di
    validazione non e' controllabile, quindi nessuno strato puo' essere
    promosso -- e il rifiuto e' un errore, non un record perso in silenzio."""
    cal = _annotations("number", 12, agree=True)
    del cal[4]["task_id"]
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="task_id"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_task_id_assente_nella_validazione_e_rifiutato(tmp_path):
    """3.4: lo stesso vincolo vale sul campione di validazione. Un record
    anonimo potrebbe essere un item di calibrazione rivalutato: la sua
    indipendenza non e' decidibile, quindi il gate non parte."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    del val[6]["task_id"]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="task_id"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


@pytest.mark.parametrize("valore", ["", "   ", 7])
def test_task_id_non_utilizzabile_come_identita_e_rifiutato(tmp_path, valore):
    """3.4: un task_id vuoto, di soli spazi o non stringa non e' un'identita'.
    Il caso non-stringa non e' un dettaglio di tipo: 7 e "7" sono chiavi
    diverse, quindi l'incrocio fra i due campioni non li vedrebbe coincidere e
    l'indipendenza sarebbe verificata per falso."""
    cal = _annotations("number", 12, agree=True)
    cal[3]["task_id"] = valore
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="task_id"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_task_id_duplicato_nella_calibrazione_e_rifiutato(tmp_path):
    """3.5: la stessa osservazione non entra due volte nel gate. Il duplicato
    porta annotazioni DIVERSE dall'originale: se il loader sovrascrivesse (o
    tenesse l'ultimo), nessun errore comparirebbe e alpha sarebbe calcolata su
    un campione che dichiara 12 item contandone 11. Il rifiuto e' senza
    sovrascritture, e l'errore nomina il task_id colpevole."""
    cal = _annotations("number", 12, agree=True)
    cal.append({"task_id": "number_0", "answer_type": "number",
                "annotator_1": "correct", "annotator_2": "incorrect"})
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="number_0"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_task_id_duplicato_nella_validazione_e_rifiutato(tmp_path):
    """3.5: lo stesso vale per la validazione, dove il duplicato naturale e'
    il verdetto del giudice registrato due volte per lo stesso item (una
    riesecuzione appena aggiunta in coda al file): conterebbe doppio nella
    matrice di confusione e nelle coverage."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    val.append(dict(val[0]))
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="val_number_0"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_task_id_duplicato_per_soli_spazi_e_la_stessa_identita(tmp_path):
    """3.5/2.5: ' n0 ' e 'n0' sono la stessa identita'. Il duplicato per soli
    spazi iniziali/finali e' invisibile a occhio e a un confronto per stringa
    esatta: accettandolo, la stessa osservazione entra due volte nel campione
    (13 item dove il protocollo ne dichiara 12) e alpha, kappa e le coverage
    sono calcolate su un campione che nessuno ha annotato due volte. Il
    confronto d'identita' opera sulla forma normalizzata, ma l'errore nomina
    il task_id così come sta nel file, così l'anomalia è ricostruibile senza
    riaprire i dati."""
    cal = _annotations("number", 12, agree=True)
    cal.append({"task_id": " number_0 ", "answer_type": "number",
                "annotator_1": "correct", "annotator_2": "incorrect"})
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="number_0"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_indipendenza_dei_campioni_sulla_identita_normalizzata(tmp_path):
    """3.4/2.5: l'indipendenza fra calibrazione e validazione è decidibile
    solo se l'identità è confrontata per forma normalizzata. Con 'n0' in
    calibrazione e ' n0 ' in validazione il confronto per stringa esatta non
    li vede coincidere, e la stessa osservazione servirebbe sia a modificare
    la rubrica sia a dichiarare il giudice validato -- un'indipendenza
    verificata per falso, lo stesso rischio del task_id non-stringa."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    val[2]["task_id"] = " number_2 "
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="indipendente"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))


def test_configurazione_senza_strati_obbligatori_e_rifiutata(tmp_path):
    """3.6: required_strata=() misura zero item, e il verdetto complessivo
    rispondeva validated per costruzione -- n_validated == len(required_strata)
    == 0, zero evidenze contate come successo. Una configurazione senza strati
    obbligatori e' degenere: il gate rifiuta di partire invece di promuovere
    un campione che non ha misurato nulla."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="required_strata"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=())


def test_configurazione_con_strati_assenti_e_rifiutata(tmp_path):
    """3.6: lo stesso vincolo per required_strata assente (None). Oggi il
    gate ci arrivava dentro e sollevava un TypeError dal ciclo sugli strati:
    un errore non dichiarato, non un rifiuto motivato. Una configurazione
    senza strati obbligatori non e' una configurazione."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="required_strata"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=None)


def test_accordo_umano_insufficiente_blocca_la_validazione_del_judge(tmp_path):
    """Se il riferimento umano non e' concorde (Verifica A fallita), il
    giudice non puo' essere validato contro di esso: il ramo resta bloccato
    anche con un giudice apparentemente perfetto."""
    cal = _annotations("number", 12, agree=False)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    assert result.scoring_status_per_stratum["number"] != "validated"


def test_note_del_gate_dichiarano_la_catena_di_abilitazione(tmp_path):
    """La nota del gate -- cioe' quello che l'artefatto si porta dietro senza
    il modulo davanti -- dichiara la catena: la soglia alpha abilita l'uso del
    riferimento umano, non il giudice. Senza quella frase il report mostra due
    verifiche senza dire quale delle due abilita il giudice, e la soglia alpha
    resta leggibile come abilitazione (l'ambiguita' che la correzione 1 della
    specifica chiude)."""
    cal = []
    for stratum in ("number", "short_text", "free_text"):
        cal.extend(_annotations(stratum, 12, agree=True))
    val = []
    for stratum in ("number", "short_text", "free_text"):
        for i in range(10):
            val.append({"task_id": f"val_{stratum}_{i}",
                        "answer_type": stratum,
                        "annotator_1": "correct", "annotator_2": "correct",
                        "judge_verdict": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria())
    note = result.notes.lower()
    assert "necessaria" in note and "sufficiente" in note
    assert "verifica b" in note


def test_experiment_status_combina_i_due_gate_senza_cancellarli():
    """Gate 3 (§7): lo stato complessivo combina energy_chain_status e
    scoring_status senza cancellare l'informazione originaria. Una catena
    energetica valida con scoring parziale resta partially_validated; una
    catena energetica fallita non diventa mai validated per merito dello
    scoring."""
    assert integrate_experiment_status("validated", "validated") == "validated"
    assert integrate_experiment_status(
        "validated", "partially_validated") == "partially_validated"
    assert integrate_experiment_status(
        "validated", "not_validated") == "scoring_not_validated"
    assert integrate_experiment_status(
        "bias_declared", "validated") == "energy_not_validated"


def test_template_protocollo_dichiara_le_due_verifiche_e_la_preregistrazione():
    """Il template di preregistrazione deve dichiarare: alpha nominale,
    le due verifiche distinte, i criteri del giudice come campi da fissare
    PRIMA dei dati (None finche' non registrati), il campione indipendente
    e la rappresentativita' delle risposte (§10)."""
    t = calibration_protocol_template()
    assert t["alpha_level"] == "nominal"
    assert "verifica_a" in t and "verifica_b" in t
    criteria = t["verifica_b"]["acceptance_criteria"]
    assert all(v is None for v in criteria.values())
    assert t["verifica_b"]["independent_sample"] is True
    assert len(t["response_typologies"]) >= 5
    assert t["pilot_declaration"]


def test_template_dichiara_che_alpha_non_abilita_il_giudice():
    """Correzione 1 della specifica (riga 21): alpha nominale e' il criterio
    di affidabilita' del RIFERIMENTO umano -- condizione necessaria per usarlo
    come gold standard -- e NON un criterio sufficiente di abilitazione del
    giudice. Il template e' lo schema da cui il protocollo committato in
    experiment_results/ deve essere rispetto (il JSON pronto lo dichiara gia'
    in verifica_a.alpha_role): un template che tace su chi abilita il giudice
    lascia la soglia alpha leggibile come abilitazione, e una registrazione
    rifatta dal template perderebbe la dichiarazione."""
    t = calibration_protocol_template()
    ruolo = t["verifica_a"]["alpha_role"]
    assert "necessaria" in ruolo.lower()
    assert "sufficiente" in ruolo.lower()
    modello = t["verdict_model"]
    assert modello["alpha_necessaria_non_sufficiente"] is True
    assert modello["judge_enabling_criterion"] == "verifica_b"


def test_template_metrics_nominano_kappa_e_f1():
    """Il template di preregistrazione deve nominare fra le metriche riportate
    kappa_nominal (Verifica A) e f1_correct/f1_incorrect (Verifica B): sono
    implementate dal gate (cohen_kappa_nominal, _f1) e la loro disponibilita'
    e' condizione necessaria per il completamento scientifico (Opzione 1).
    Un template che non le elenca dichiara una procedura incompleta."""
    t = calibration_protocol_template()
    assert "kappa_nominal" in t["verifica_a"]["metrics"]
    assert "f1_correct" in t["verifica_b"]["metrics"]
    assert "f1_incorrect" in t["verifica_b"]["metrics"]


def test_template_campione_prevede_adjudication_e_tipologia():
    """Il campione di calibrazione deve poter registrare l'adjudication dei
    disaccordi e la tipologia di risposta (corretta, errata, parziale,
    convincente-ma-errata, ambigua), non solo le due etichette cieche."""
    items = calibration_sample_template()
    assert len(items) == 40
    first = items[0]
    assert "adjudicated" in first
    assert "response_typology" in first
    assert "annotations" in first


# --- Diagnostica: perche' il gate non puo' produrre un numero -------------------
#
# Il gate deve non solo evitare un risultato falso, ma dire PERCHE' non puo'
# produrne uno. Le cinque categorie sono distinte e non intercambiabili:
#   insufficient_data  — dati corretti ma troppo pochi (sotto il pavimento
#                        preregistrato: n_pairable < MIN_PAIRABLE_ITEMS,
#                        n_decided < MIN_DECIDED_ITEMS);
#   invalid_schema     — record non conforme allo schema canonico (non-dict,
#                        riga JSON non-oggetto, answer_type fuori dagli strati
#                        misurati o assente);
#   invalid_label      — etichetta fuori dal vocabolario ammesso, incluse le
#                        maiuscole, che NON vengono convertite in minuscolo;
#   missing_annotation — annotatore richiesto assente (None);
#   unscored           — riferimento umano non producibile (non confrontabile).
# Nessun numero e' calcolato su record incoerenti: sono esclusi e contati.
# validated e i denominatori restano invariati: la diagnostica e' riportata.


def test_verifica_a_distinguue_annotazione_mancante():
    """Un annotatore assente (annotator_2 = None) e' missing_annotation, non
    una coppia da trattare come discordante ne' un item silenziosamente
    perduto: senza due etichette non esiste accordo misurabile, quindi la
    coppia non entra in alpha/kappa e la sua assenza e' contata."""
    ann = [{"task_id": f"n{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": None}
           for i in range(2)]
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.diagnostics["missing_annotation"] == 2
    assert s.n_pairable == 0
    assert s.alpha_nominal is None


def test_verifica_a_distinguue_etichetta_invalida_e_non_converte():
    """Le maiusole (Correct/Incorrect) sono fuori dal vocabolario ammesso e
    NON vengono convertite in minuscolo: convertirle sarebbe inventare una
    normalizzazione non dichiarata. Sono invalid_label, escluse da alpha/kappa
    e dalla distribuzione delle classi; le coppie valide restano le uniche a
    produrre il numero."""
    ann = ([{"task_id": f"v{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct"}
            for i in range(5)]
           + [{"task_id": "u0", "answer_type": "number",
               "annotator_1": "Correct", "annotator_2": "Correct"},
              {"task_id": "u1", "answer_type": "number",
               "annotator_1": "Incorrect", "annotator_2": "Incorrect"}])
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.diagnostics["invalid_label"] == 2
    assert s.n_pairable == 5
    assert "Correct" not in s.class_distribution
    assert s.alpha_nominal == pytest.approx(1.0)


def test_verifica_a_non_calcola_su_record_malformato():
    """Un record che non e' un dict non ha strato ne' annotatori: e'
    invalid_schema. Il gate non deve sollevare (crash) e non deve lasciarlo
    entrare nel calcolo: lo esclude e lo conta, perche' un numero ottenuto su
    un record illeggibile sarebbe un numero senza dato."""
    ann = ([{"task_id": f"n{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct"}
            for i in range(3)]
           + ["record-malformato"])
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.diagnostics["invalid_schema"] >= 1
    assert s.n_pairable == 3


def test_verifica_a_insufficient_data_ha_codice_e_ragione():
    """Con una sola coppia valida alpha/kappa non sono calcolabili
    (insufficient_data, non un numero su un item). La ragione lo nomina col
    codice, distinto da p_e = 1 (classe sola), che e' un'altra causa."""
    ann = [{"task_id": "n0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}]
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.diagnostics["insufficient_data"] == 1
    assert s.reason.startswith("insufficient_data")
    assert s.alpha_nominal is None


def test_adjudicated_reference_conta_anomalie_senza_alterare_il_consolidamento():
    """Il consolidamento del riferimento resta quello di prima (accordo,
    adjudication, senza-riferimento), ma ora le anomalie sono contate con
    codice proprio: annotazione mancante ed etichetta fuori vocabolario non
    producono riferimento e vengono distinte, non accorpate nel generico
    n_without_reference."""
    ann = [
        {"task_id": "a", "annotator_1": "correct", "annotator_2": "correct"},
        {"task_id": "b", "annotator_1": "correct", "annotator_2": None},
        {"task_id": "c", "annotator_1": "Correct", "annotator_2": "Correct"},
    ]
    reference, stats = adjudicated_reference(ann)
    assert reference == {"a": "correct"}
    assert stats["n_missing_annotation"] == 1
    assert stats["n_invalid_label"] == 1


def test_verifica_b_distinguue_non_confrontabile_da_etichetta_invalida():
    """In Verifica B due furie di astensione hanno cause diverse: un
    riferimento assente rende l'item non confrontabile (unscored, escluso
    dalla matrice), mentre un verdetto fuori vocabolario su un riferimento
    valido resta un'astensione nella matrice ma e' invalid_label. Il calcolo
    di confusion/astensione non cambia; la causa viene detta."""
    items = [
        {"task_id": "a", "answer_type": "free_text",
         "reference": "correct", "judge_verdict": "correct"},
        {"task_id": "b", "answer_type": "free_text",
         "reference": "correct", "judge_verdict": "Maybe"},
        {"task_id": "c", "answer_type": "free_text",
         "reference": None, "judge_verdict": "correct"},
    ]
    v = verifica_b(items, _criteria(), required_strata=("free_text",))["free_text"]
    assert v.diagnostics["invalid_label"] == 1
    assert v.diagnostics["unscored"] == 1
    assert v.confusion["correct"]["correct"] == 1
    assert v.confusion["correct"]["abstained"] == 1


def test_gate_espone_diagnostica_e_non_promuove_record_malformati(tmp_path):
    """Una riga non-oggetto nel campione e' invalid_schema a livello di gate:
    viene contata ed esclusa, non fa crashare e non diventa evidenza. I veri
    item validi continuano a determinare scoring_status (fail-closed sui
    criteri invariato): il record malformato e' segnalato, non Promosso."""
    cal = [{"task_id": f"cal_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}
           for i in range(12)]
    val = [{"task_id": f"val_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"}
           for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with val_file.open("a", encoding="utf-8") as f:
        f.write("\n" + json.dumps(42))
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    assert result.diagnostics["invalid_schema"] >= 1
    assert result.scoring_status_per_stratum["number"] == "validated"


# --- Pavimento di numerosita' e conteggio delle cause (D1, D2, D4) -------------
#
# Tre difetti trovati nella revisione mirata, con il test che li dimostra:
#
# D2 — pavimento di numerosita'. Con due item di calibrazione concordi e un
#      solo item di validazione deciso (piu' 500 record malformati) il ramo
#      passava validated: alpha = 1.0 su n = 2, accuratezza 1.0 su n = 1,
#      fp_rate None soddisfatto vacuamente. Un campione valido troppo piccolo
#      non deve potere promuovere: sotto il pavimento preregistrato il ramo e'
#      insufficient_data, non validated. La regola di verdetto cambia in
#      direzione fail-closed (puo' solo abbassare uno stato, mai alzarlo), ed
#      e' una decisione di protocollo: il pavimento sta fra le costanti
#      dichiarate e nel template di preregistrazione.
#
# D1 — somma di unscored. Il conteggio dei riferimenti non producibili e' di
#      sequenza: attribuito a ogni strato e poi sommato sugli strati, un solo
#      record contava tre volte con tre strati. I dict per strato devono
#      riportare solo cause attribuibili a quello strato.
#
# D4 — record fuori dagli strati misurati. Un record con answer_type assente
#      o fuori da REQUIRED_STRATA entrava in nessuno strato e non era contato
#      da nessun codice: l'unica via per cui un record spariva in silenzio.
#      Ora e' invalid_schema (lo schema canonico dichiara gli strati).


def test_verifica_a_pavimento_di_numerosita_blocca_il_passaggio():
    """Due item concordi danno alpha = 1.0 ma non sono un campione: sotto il
    pavimento preregistrato il ramo non passa, con ragione insufficient_data.
    La metrica resta riportata (alpha = 1.0 e' un dato vero), il verdetto no:
    un accordo perfetto su due item non e' evidenza di accordo."""
    ann = [{"task_id": "n0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"},
           {"task_id": "n1", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}]
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.n_pairable == 2
    assert s.alpha_nominal == pytest.approx(1.0)
    assert s.passed is False
    assert s.reason.startswith("insufficient_data")
    assert str(MIN_PAIRABLE_ITEMS) in s.reason


def test_verifica_b_pavimento_di_numerosita_non_giudica_le_metriche():
    """Con due verdetti decisi le metriche sono calcolabili (accuracy 1.0) ma
    non giudicabili: sotto il pavimento preregistrato il ramo non passa e il
    solo criterio fallito e' la numerosita'. Valutare precision/recall su due
    item sarebbe un verdetto su un campione che non li supporta; fp_rate None
    non e' assente di falsi positivi, e' assenza di casi errati."""
    items = [{"task_id": f"v{i}", "answer_type": "number",
              "reference": "correct", "judge_verdict": "correct"}
             for i in range(2)]
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.n_decided == 2
    assert v.accuracy == pytest.approx(1.0)
    assert v.fp_rate is None
    assert v.passed is False
    assert v.failed_criteria == ("insufficient_numerosity",)


def test_gate_distingue_insufficient_data_da_human_agreement_failed():
    """Le due cause di mancato passaggio della Verifica A non hanno lo stesso
    nome: sotto il pavimento il ramo e' insufficient_data (non c'e' campione),
    con alpha sotto soglia e' human_agreement_failed (il campione c'e' e non
    concorda). Collassarle avrebbe detto "gli annotatori non concordano" a un
    ramo con due soli item, e "dati insufficienti" a un ramo con meta' item
    discordanti: in entrambi i versi la causa detta sarebbe sbagliata."""
    cal_pavimento = [{"task_id": "n0", "answer_type": "number",
                      "annotator_1": "correct", "annotator_2": "correct"},
                     {"task_id": "n1", "answer_type": "number",
                      "annotator_1": "correct", "annotator_2": "correct"}]
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"}
           for i in range(MIN_DECIDED_ITEMS)]
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cal_file, val_file = td / "cal.jsonl", td / "val.jsonl"
        _write_jsonl(cal_file, cal_pavimento)
        _write_jsonl(val_file, val)
        r = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                        required_strata=("number",))
        assert r.scoring_status_per_stratum["number"] == "insufficient_data"
        assert r.scoring_status == "not_validated"
        _write_jsonl(cal_file, _annotations("number", 12, agree=False))
        r = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                        required_strata=("number",))
        assert r.scoring_status_per_stratum["number"] == "human_agreement_failed"


def test_gate_non_promuove_su_residuo_valido_troppo_piccolo(tmp_path):
    """Lo scenario della revisione: due item di calibrazione e uno di
    validazione validi, circondati da 500 record malformati. Prima del
    pavimento il ramo passava validated -- un verdetto su un residuo, non su
    un campione. Ora il pavimento blocca E i 500 record sono contati: il
    verdetto negativo ha la sua causa detta, e la causa non e' un giudice
    difettoso (judge_uncalibrated) ne' un disaccordo umano."""
    cal = [{"task_id": "c0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"},
           {"task_id": "c1", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}]
    val = [{"task_id": "v0", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"}]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    with val_file.open("w", encoding="utf-8") as f:
        for item in val:
            f.write(json.dumps(item) + "\n")
        for i in range(500):
            f.write("\n" + json.dumps(42))
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    assert result.scoring_status_per_stratum["number"] == "insufficient_data"
    assert result.scoring_status != "validated"
    assert result.diagnostics["invalid_schema"] == 500
    assert "insufficient_numerosity" in result.validity[0].failed_criteria


def test_gate_conta_unscored_una_sola_volta_per_record(tmp_path):
    """D1: un record il cui riferimento non e' producibile (disaccordo senza
    adjudication) e' non confrontabile UNA volta, non una per strato. Con tre
    strati la somma per strato del conteggio di sequenza dava 3. I dict per
    strato non portano cause di sequenza: riportano solo verdetti assenti."""
    cal = []
    for stratum in ("number", "short_text", "free_text"):
        cal.extend(_annotations(stratum, 12, agree=True))
    val = []
    for stratum in ("number", "short_text", "free_text"):
        val.extend([{"task_id": f"val_{stratum}_{i}", "answer_type": stratum,
                     "annotator_1": "correct", "annotator_2": "correct",
                     "judge_verdict": "correct"}
                    for i in range(10)])
    val.append({"task_id": "val_free_text_disaccordo",
                "answer_type": "free_text",
                "annotator_1": "correct", "annotator_2": "incorrect",
                "judge_verdict": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria())
    assert result.reference_stats["n_without_reference"] == 1
    assert result.diagnostics["unscored"] == 1
    for v in result.validity:
        assert v.diagnostics["unscored"] == 0


def test_record_fuori_degli_strati_contato_come_invalid_schema():
    """D4: un record con answer_type fuori dagli strati misurati (o assente)
    non entra in nessuno strato e non sparisce in silenzio: e' invalid_schema,
    perche' lo schema canonico dichiara gli strati. Il calcolo prosegue sui
    soli record dello strato, senza contarli due volte dentro lo strato."""
    ann = ([{"task_id": f"n{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct"}
            for i in range(3)]
           + [{"task_id": "z", "answer_type": "code",
               "annotator_1": "correct", "annotator_2": "correct"},
              {"task_id": "w",
               "annotator_1": "correct", "annotator_2": "correct"}])
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.n_items == 3
    assert s.n_pairable == 3
    assert s.diagnostics["invalid_schema"] == 2
    items = ([{"task_id": f"v{i}", "answer_type": "number",
               "reference": "correct", "judge_verdict": "correct"}
              for i in range(3)]
             + [{"task_id": "z", "answer_type": "code",
                 "reference": "correct", "judge_verdict": "correct"}])
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.n_items == 3
    assert v.n_decided == 3
    assert v.diagnostics["invalid_schema"] == 1


def test_gate_invalid_schema_include_record_fuori_degli_strati(tmp_path):
    """D4 a livello di gate: il conteggio authoritative di invalid_schema non
    e' la somma degli strati (che non possono attribuirsi un record illeggibile
    o fuori perimetro) ma il conteggio di sequenza del gate: righe non-oggetto
    dal loader PIU' record fuori dagli strati, ciascuno contato una volta."""
    cal = [{"task_id": f"cal_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}
           for i in range(12)]
    val = [{"task_id": f"val_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"}
           for i in range(10)]
    cal.append({"task_id": "cal_fuori", "answer_type": "code",
                "annotator_1": "correct", "annotator_2": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    assert result.diagnostics["invalid_schema"] == 1


def test_template_dichiara_i_pavimenti_di_numerosita():
    t = calibration_protocol_template()
    assert t["verifica_a"]["min_pairable_items"] == MIN_PAIRABLE_ITEMS
    assert t["verifica_b"]["min_decided_items"] == MIN_DECIDED_ITEMS


# --- Opzione 1: validated invariato, completamento scientifico ----------------


def _scientifically_complete(status, agreement, validity):
    """Opzione 1: completamento scientifico = gate superato E κ/F1 disponibili.

    Derivato nel test, NON un token del gate: ``validated`` resta determinato
    solo da Verifica A (alpha) + Verifica B (criteri preregistrati). κ e F1
    sono metriche riportate la cui disponibilita' (non-None) e' condizione
    necessaria aggiuntiva per dichiarare completa la validazione.
    """
    return (status == "validated"
            and agreement.kappa_nominal is not None
            and validity.f1_correct is not None
            and validity.f1_incorrect is not None)


def test_validated_anche_con_kappa_non_disponibile(tmp_path):
    """Opzione 1: il token validated NON dipende da kappa. Una calibrazione
    a classe sola (tutti correct) ha alpha = 1.0 (passed) ma kappa None
    (p_e = 1); con un giudice perfetto il ramo e' validated, scientificamente
    incompleto perche' kappa non e' disponibile."""
    cal = [{"task_id": f"cal_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct"}
           for i in range(12)]
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": r, "annotator_2": r, "judge_verdict": r}
           for i, r in enumerate(["correct"] * 5 + ["incorrect"] * 5)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    a, v = result.agreement[0], result.validity[0]
    assert result.scoring_status_per_stratum["number"] == "validated"
    assert a.kappa_nominal is None
    assert a.passed is True
    assert not _scientifically_complete("validated", a, v)


def test_validated_anche_con_f1_di_una_classe_non_disponibile(tmp_path):
    """Opzione 1: validated NON dipende da F1. Una validazione senza
    riferimenti incorrect ha fp_rate None (criterio soddisfatto vacuamente)
    e F1_incorrect None (classe non testata); il ramo puo' essere validated
    ma scientificamente incompleto finche' la classe incorrect non e' campionata."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct" if i < 9 else "incorrect"}
           for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    a, v = result.agreement[0], result.validity[0]
    assert result.scoring_status_per_stratum["number"] == "validated"
    assert v.f1_incorrect is None
    assert v.f1_correct is not None
    assert a.kappa_nominal is not None
    assert not _scientifically_complete("validated", a, v)


def test_kappa_f1_disponibili_non_promuovono_un_ramo_bloccato(tmp_path):
    """Opzione 1: la disponibilita' di κ/F1 NON promuove un ramo che i
    criteri preregistrati bocciano. Un giudice con fp_rate 0.6 resta
    judge_uncalibrated anche se κ e F1 sono tutti calcolabili."""
    cal = _annotations("number", 12, agree=True)
    val = []
    for i in range(5):
        val.append({"task_id": f"val_c{i}", "answer_type": "number",
                    "annotator_1": "correct", "annotator_2": "correct",
                    "judge_verdict": "correct"})
    for i in range(5):
        val.append({"task_id": f"val_i{i}", "answer_type": "number",
                    "annotator_1": "incorrect", "annotator_2": "incorrect",
                    "judge_verdict": "correct" if i < 3 else "incorrect"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    a, v = result.agreement[0], result.validity[0]
    assert result.scoring_status_per_stratum["number"] != "validated"
    assert a.kappa_nominal is not None
    assert v.f1_correct is not None and v.f1_incorrect is not None
    assert "max_fp_rate" in v.failed_criteria


def test_completamento_scientifico_richiede_gate_e_metriche(tmp_path):
    """Opzione 1: completamento scientifico = validated E κ disponibile E
    F1 di entrambe le classi disponibile. Caso positivo: calibrazione a due
    classi concordi (κ = 1) e giudice perfetto su entrambe le classi (F1 = 1)."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": r, "annotator_2": r, "judge_verdict": r}
           for i, r in enumerate(["correct"] * 5 + ["incorrect"] * 5)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    a, v = result.agreement[0], result.validity[0]
    status = result.scoring_status_per_stratum["number"]
    assert status == "validated"
    assert a.kappa_nominal == pytest.approx(1.0)
    assert v.f1_correct == pytest.approx(1.0)
    assert v.f1_incorrect == pytest.approx(1.0)
    assert _scientifically_complete(status, a, v)


# --- Pavimento sulla frazione ammissibile (audit avversariale) -----------------
#
# L'audit ha misurato un'esposizione che i pavimenti di numerosita' non
# chiudono: i denominatori del gate sono sempre il sottoinsieme ammissibile --
# trattamento metrologicamente corretto, un record incoerente non si converte
# -- ma NESSUN criterio condizionava il verdetto alla frazione ammissibile.
# Tre attacchi, stessa radice, tutti misuravano `validated`:
#
# E1 — fuori perimetro: 9 item validi su 40, i 31 difettosi fuori dagli strati
#      misurati. Non entrano in alcuno strato, quindi ogni strato vede
#      n_items = 3 e copertura 1,0. I 31 comparivano solo in invalid_schema.
# E2 — entro perimetro, Verifica B: 3 verdetti decisi su 30 item (27
#      astensioni) con min_coverage preregistrato a 0,0: copertura 0,100,
#      diagnostica dei difetti tutta a zero.
# E3 — entro perimetro, Verifica A: 3 coppie pairable su 30 record di
#      calibrazione (27 etichette fuori vocabolario): alpha = 1,0, passed.
#
# La guardia e' preregistrata e fail-closed, come D2: sotto la frazione
# ammissibile il ramo e' insufficient_data, non validated. Puo' solo abbassare
# un verdetto. Il verdetto deve descrivere il campione, non il residuo che le
# esclusioni lasciano.


def test_verifica_a_frazione_ammissibile_blocca_l_accordo():
    """E3 lato Verifica A: 30 record attribuiti allo strato, 3 con annotazioni
    valide e 27 con etichette fuori vocabolario. I 27 sono esclusi (mai
    convertiti) e contati, e alpha = 1,0 sui 3 superstiti e' un dato vero: ma
    un accordo perfetto sul residuo non e' accordo del campione. Sotto la
    frazione ammissibile preregistrata lo strato non passa, con ragione
    insufficient_data -- non human_agreement_failed: gli annotatori superstiti
    concordano, il campione non basta."""
    ann = ([{"task_id": f"n{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct"}
            for i in range(3)]
           + [{"task_id": f"j{i}", "answer_type": "number",
               "annotator_1": "CORRECT", "annotator_2": "CORRECT"}
              for i in range(27)])
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.n_items == 30
    assert s.n_pairable == 3
    assert s.alpha_nominal == pytest.approx(1.0)
    assert s.diagnostics["invalid_label"] == 27
    assert s.passed is False
    assert s.reason.startswith("insufficient_data")
    assert "3/30" in s.reason


def test_verifica_a_frazione_al_pavimento_resta_giudicabile():
    """Il pavimento sulla frazione ammissibile e' una soglia, non un divieto:
    esattamente al pavimento (4 pairable su 8 record, frazione 0,5) lo strato
    resta giudicabile e passa. La soglia e' preregistrata, non spostabile dai
    dati, e il test fissa il confine perche' un confine ambiguo renderebbe la
    guardia una soglia mobile."""
    ann = ([{"task_id": f"n{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct"}
            for i in range(4)]
           + [{"task_id": f"j{i}", "answer_type": "number",
               "annotator_1": "CORRECT", "annotator_2": "CORRECT"}
              for i in range(4)])
    s = verifica_a(ann, required_strata=("number",))["number"]
    assert s.n_items == 8
    assert s.n_pairable == 4
    assert s.passed is True


def test_verifica_b_frazione_ammissibile_blocca_il_giudizio():
    """E2/E3 lato Verifica B: 10 item attribuiti allo strato, 4 con riferimento
    utilizzabile e 6 che dichiarano un riferimento fuori vocabolario. Le
    metriche sui 4 sono calcolabili e perfette (accuracy 1,0): senza la guardia
    il ramo passava e il verdetto descriveva il residuo. Ora il solo criterio
    fallito e' la frazione ammissibile -- non i criteri del giudice, che sui 4
    item sono soddisfatti -- e il conteggio dei record dello strato e' esposto,
    per ricostruire la frazione senza rileggere il file."""
    items = ([{"task_id": f"v{i}", "answer_type": "number",
               "reference": "correct", "judge_verdict": "correct"}
              for i in range(4)]
             + [{"task_id": f"u{i}", "answer_type": "number",
                 "reference": "forse", "judge_verdict": "correct"}
                for i in range(6)])
    v = verifica_b(items, _criteria(), required_strata=("number",))["number"]
    assert v.n_records_in_stratum == 10
    assert v.n_items == 4
    assert v.n_decided == 4
    assert v.accuracy == pytest.approx(1.0)
    assert v.diagnostics["unscored"] == 6
    assert v.passed is False
    assert "insufficient_admissible_fraction" in v.failed_criteria
    assert "min_accuracy" not in v.failed_criteria


def test_gate_non_promuove_con_record_fuori_perimetro_in_quota(tmp_path):
    """E1 a livello di gate: 9 item validi (3 per strato) e 31 record fuori
    dagli strati misurati. I 31 non entrano in nessuno strato, quindi ogni
    strato vede n_items = 3 e copertura 1,0: prima della guardia il gate
    rispondeva validated su un campione di cui il 77,5% non era misurabile. La
    frazione ammissibile della sequenza e' preregistrata: sotto, nessun ramo e'
    promosso, perche' il gate non ha misurato il campione che il protocollo
    dichiara. I 31 restano contati come invalid_schema -- esclusi, non
    convertiti -- e la frazione e' esposta per ricostruire la causa."""
    cal = []
    for stratum in ("number", "short_text", "free_text"):
        cal.extend(_annotations(stratum, 4))
    val = []
    for stratum in ("number", "short_text", "free_text"):
        val.extend([{"task_id": f"val_{stratum}_{i}", "answer_type": stratum,
                     "annotator_1": "correct", "annotator_2": "correct",
                     "judge_verdict": "correct"} for i in range(3)])
    for i in range(31):
        val.append({"task_id": f"fuori_{i}", "answer_type": "code",
                    "annotator_1": "correct", "annotator_2": "correct",
                    "judge_verdict": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria())
    assert result.diagnostics["invalid_schema"] == 31
    assert result.admissible_fractions["validation"] == pytest.approx(9 / 40)
    assert result.scoring_status != "validated"
    for stratum in ("number", "short_text", "free_text"):
        assert result.scoring_status_per_stratum[stratum] == "insufficient_data"


def test_frazione_ammissibile_preregistrata_nel_template():
    """Come il pavimento di numerosita', la frazione ammissibile e'
    preregistrata: sta nel template accanto alla soglia, fissata prima dei
    dati. Una guardia non dichiarata nel template sarebbe una soglia comparsa
    dopo aver visto il campione -- e un pavimento preregistrato a posteriori
    non e' preregistrato."""
    t = calibration_protocol_template()
    assert t["verifica_a"]["min_admissible_fraction"] == MIN_ADMISSIBLE_FRACTION
    assert t["verifica_b"]["min_admissible_fraction"] == MIN_ADMISSIBLE_FRACTION


def test_pavimento_della_frazione_dichiarato_nella_preregistrazione():
    """Il pavimento sulla frazione ammissibile compare nella prosa di
    preregistrazione del template, non solo come chiave numerica: chi riceve il
    template legge quali pavimenti vigono e perche'. Una guardia presente solo
    nel codice sarebbe una regola di verdetto che il documento preregistrato non
    nomina -- e la preregistrazione e' il documento, non l'implementazione."""
    t = calibration_protocol_template()
    dichiarazione = t["pilot_declaration"]
    assert "min_admissible_fraction" in dichiarazione
    assert "insufficient_data" in dichiarazione
    assert "residuo" in dichiarazione


# --- Fase 4: prove combinatorie sulle correzioni della revisione -------------
#
# Le correzioni 3.4, 3.5, 3.6, E2, 2.3, 2.4 e 2.5 sono state verifyate una per
# una nei blocchi precedenti. Qui si verificano le COMBINAZIONI: un difetto non
# deve potere eludere la protezione di un altro difetto, ne' una protezione deve
# potere essere bypassata presentando insieme i due difetti che essa copre.


def test_g1_identita_assente_e_duplicato_il_primo_difetto_in_lettura_e_nominato(
        tmp_path):
    """Combinazione 3.4 + 3.5. Un record senza task_id e un duplicato nello
    stesso file: entrambe le protezioni devono rifiutare, e il rifiuto deve
    nominare il primo difetto incontrato in ordine di lettura, non uno qualunque
    dei due. Se il loader controllasse i duplicati prima dell'identita' (o
    accumulasse in un dict), un record anonimo verrebbe semplicemente perso:
    con task_id assente la chiave di raggruppamento non esiste e il duplicato
    successivo lo sovrascriverebbe -- due difetti in uno, conteggio zero."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    # riga 1: duplicato di val_number_0; riga 2: record senza identita'.
    val[1] = dict(val[0])
    del val[5]["task_id"]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="duplicato"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))
    # L'errore nomina il task_id originale (non la forma normalizzata): la
    # ricostruzione dell'anomalia non deve richiedere una riscrittura del dato.
    val_senza_dup = [v for i, v in enumerate(val) if i != 1]
    cal_file2, val_file2 = tmp_path / "cal2.jsonl", tmp_path / "val2.jsonl"
    _write_jsonl(cal_file2, cal)
    _write_jsonl(val_file2, val_senza_dup)
    with pytest.raises(ValueError, match="task_id"):
        run_scoring_validation_gate(cal_file2, val_file2, _criteria(),
                                    required_strata=("number",))


def test_g2_configurazione_degenere_e_criterio_degenere_non_si_eludono(
        tmp_path):
    """Combinazione 3.6 + E2. Le due protezioni sono indipendenti e nessuna
    elude l'altra: una configurazione senza strati obbligatori e' rifiutata
    prima di leggere i dati anche con criteri perfettamente registrati, e un
    criterio di coverage degenere e' rifiutato alla costruzione, prima dei
    dati, anche con una configurazione di strati valida. Il caso avversariale
    e' presentarli INSIEME -- configurazione degenere con criterio degenere --
    dove un'implementazione che controllasse un solo dei due lascerebbe passare
    l'altro: qui il rifiuto arriva comunque, dal criterio, perche' il gate non
    viene chiamato."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="required_strata"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=())
    with pytest.raises(ValueError, match="min_coverage"):
        # Il criterio degenere non e' costruibile, quindi il gate non parte:
        # nessuna configurazione di strati puo' rendere accettabile una soglia
        # che non esclude alcuna astensione.
        criterio = JudgeAcceptanceCriteria(
            min_precision_correct=0.90, min_recall_correct=0.80,
            max_fp_rate=0.10, min_accuracy=0.85, min_coverage=0.0)
        run_scoring_validation_gate(cal_file, val_file, criterio,
                                    required_strata=("number",))


def test_g3_record_con_tre_difetti_contato_una_volta_con_precedenza(tmp_path):
    """Combinazione 2.3 + 2.4 + precedenza invalid_schema su unscored. Un
    record fuori dagli strati misurati, con un'etichetta umana fuori
    vocabolario e senza riferimento producibile, porta tre difetti insieme.
    Deve essere contato UNA volta come invalid_schema (causa di sequenza,
    che ha la precedenza), NON anche come unscored; la causa di contenuto --
    l'etichetta invalida -- resta visibile in invalid_label. Sommare i tre
    difetti darebbe 3 su un solo record, e la frazione ammissibile del
    campione ne sarebbe corrotta due volte."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(12)]
    val.append({"task_id": "val_fuori_code", "answer_type": "code",
                "annotator_1": "correct", "annotator_2": "Corretto",
                "judge_verdict": "correct"})
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    result = run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                         required_strata=("number",))
    assert result.diagnostics["invalid_schema"] == 1
    assert result.diagnostics["unscored"] == 0
    assert result.diagnostics["invalid_label"] == 1
    # reference_stats descrive la produzione del riferimento sull'INTERA
    # sequenza, senza il filtro degli strati: il record fuori perimetro non ha
    # prodotto riferimento e infatti n_without_reference lo conta. Il gate
    # invece non lo conta in ``unscored'', perche' la causa di sequenza ha la
    # precedenza ed e' mutuamente esclusiva: un record fuori perimetro senza
    # riferimento e' invalid_schema una volta sola. I due campi hanno ambiti
    # diversi -- riferimento non prodotto sull'intera sequenza, difetti di
    # sequenza sui soli strati misurati -- e nessuno dei due protegge un
    # verdetto: il ramo resta validated sui 12 item ammissibili.
    assert result.reference_stats["n_without_reference"] == 1
    v = result.validity[0]
    assert v.n_records_in_stratum == 12
    assert v.n_items == 12
    # Il difetto e' escluso dal calcolo e contato: il verdetto resta quello
    # del campione dichiarato (12/13 ammissibili), non di un residuo.
    assert result.admissible_fractions["validation"] == pytest.approx(12 / 13)
    assert result.scoring_status_per_stratum["number"] == "validated"


def test_g4_duplicato_prima_della_sovrapposizione_il_primo_errore_nomina_il_colpevole(
        tmp_path):
    """Combinazione 3.5 + indipendenza dei campioni. Un task_id duplicato
    DENTRO la validazione che coincide anche con un task_id della calibrazione
    presenta due difetti di identita' insieme. Il loader deve rifiutare il
    duplicato per primo, nomeando il task_id colpevole e le due righe: se il
    controllo di indipendenza scattasse prima, l'errore direbbe "non
    indipendente" e il duplicato -- la stessa osservazione contata due volte
    nella matrice di confusione -- resterebbe invisibile nel messaggio."""
    cal = _annotations("number", 12, agree=True)
    val = [{"task_id": f"val_number_{i}", "answer_type": "number",
            "annotator_1": "correct", "annotator_2": "correct",
            "judge_verdict": "correct"} for i in range(10)]
    val[3] = dict(val[0])          # duplicato di val_number_0 (riga 4)
    val[7]["task_id"] = "number_2"  # anche sovrapposizione con la calibrazione
    cal_file, val_file = tmp_path / "cal.jsonl", tmp_path / "val.jsonl"
    _write_jsonl(cal_file, cal)
    _write_jsonl(val_file, val)
    with pytest.raises(ValueError, match="val_number_0"):
        run_scoring_validation_gate(cal_file, val_file, _criteria(),
                                    required_strata=("number",))
    # Rimosso il duplicato, la sovrapposizione residua e' rifiutata a sua
    # volta, con il proprio nome: i due controlli non si sostituiscono.
    val_senza_dup = [v for i, v in enumerate(val) if i != 3]
    cal_file2, val_file2 = tmp_path / "cal2.jsonl", tmp_path / "val2.jsonl"
    _write_jsonl(cal_file2, cal)
    _write_jsonl(val_file2, val_senza_dup)
    with pytest.raises(ValueError, match="indipendente"):
        run_scoring_validation_gate(cal_file2, val_file2, _criteria(),
                                    required_strata=("number",))
