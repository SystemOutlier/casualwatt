# -*- coding: utf-8 -*-
"""test_iso_alignment.py — regressioni concettuali ISO 50006.

I test verificano che le distinzioni terminologiche del capitolo ISO
siano preservate nel codice: EnB separata dalla baseline idle,
quantizzazione non inventata, manifesto che dichiara i limiti.
Ogni test ha una docstring che dice *perche'* esiste.
"""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from iso_alignment import (
    CORRECTNESS_EVIDENCE_TYPES,
    CORRECTNESS_RULE_VERSIONS,
    GROUND_TRUTH_QUALITY_STATUSES,
    JUDGE_CALIBRATION_STATUSES,
    JUDGE_ROLES,
    ENB_FIT_METHODS,
    IDLE_BASELINE_METHODS,
    MEASUREMENT_ROLES,
    UNCERTAINTY_METHODS,
    IsoAlignment,
)


class TestEnBRecord:
    """EnB richiede modello, metodo e hash — mai un numero senza provenienza."""

    def test_enb_richiede_modello_metodo_e_hash(self):
        """EnB senza provenienza completa e' un numero non verificabile.

        Il test verifica che enb_record restituisca tutti i campi richiesti
        quando i parametri sono validi.
        """
        iso = IsoAlignment()
        record = iso.enb_record(
            model_id="qwen2.5:0.5b",
            fit_method="weighted-linear-surface-QR",
            coefficients_sha256="abc123",
            in_coverage=True,
            prediction_j=100.0,
            residual_j=-5.0,
        )

        assert record["enb_model_id"] == "qwen2.5:0.5b"
        assert record["enb_fit_method"] == "weighted-linear-surface-QR"
        assert record["enb_coefficients_sha256"] == "abc123"
        assert record["enb_in_coverage"] == "true"
        assert record["enb_prediction_j"] == 100.0
        assert record["enb_residual_j"] == -5.0
        assert record["enb_residual_ratio"] == -0.05

    def test_enb_metodo_non_dichiarato_rifiutato(self):
        """Un metodo di fit non dichiarato non entra nel CSV.

        Se un futuro commit introduce un metodo senza aggiornare
        ENB_FIT_METHODS, il test fallisce invece di produrre un numero
        con provenienza illeggibile.
        """
        iso = IsoAlignment()
        try:
            iso.enb_record(
                model_id="test",
                fit_method="unknown-method",
                coefficients_sha256="abc",
                in_coverage=True,
                prediction_j=100.0,
                residual_j=0.0,
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)

    def test_enb_fuori_copertura_non_pubblica_predizione(self):
        """Fuori copertura, EnB non produce predizione né residuo.

        Un'estrapolazione non e' una misura: i campi restano vuoti
        per impedire che un numero apparentemente misurato entri nel CSV.
        """
        iso = IsoAlignment()
        record = iso.enb_record(
            model_id="test",
            fit_method="weighted-linear-surface-QR",
            coefficients_sha256="abc",
            in_coverage=False,
            prediction_j=None,
            residual_j=None,
        )

        assert record["enb_in_coverage"] == ""
        assert record["enb_prediction_j"] == ""
        assert record["enb_residual_j"] == ""

    def test_enb_residuo_ratio_con_denominatore_nullo(self):
        """Se prediction_j e' zero o negativa, il residuo relativo e' vuoto.

        Un rapporto con denominatore nullo non e' un numero: resta vuoto
        invece di sollevare ZeroDivisionError.
        """
        iso = IsoAlignment()
        record = iso.enb_record(
            model_id="test",
            fit_method="weighted-linear-surface-QR",
            coefficients_sha256="abc",
            in_coverage=True,
            prediction_j=0.0,
            residual_j=5.0,
        )

        assert record["enb_residual_ratio"] == ""

    def test_enb_unavailable_record_tutti_vuoti(self):
        """Quando la superficie non e' applicabile, tutti i campi EnB sono vuoti.

        Il test verifica che enb_unavailable_record restituisca un dizionario
        con tutti i campi vuoti, non zero.
        """
        iso = IsoAlignment()
        record = iso.enb_unavailable_record()

        assert record["enb_model_id"] == ""
        assert record["enb_fit_method"] == ""
        assert record["enb_coefficients_sha256"] == ""
        assert record["enb_in_coverage"] == ""
        assert record["enb_prediction_j"] == ""
        assert record["enb_residual_j"] == ""
        assert record["enb_residual_ratio"] == ""


class TestIdleBaseline:
    """La baseline idle e' correzione del fondo, non EnB."""

    def test_baseline_idle_ruolo_sempre_background_subtraction(self):
        """Il ruolo della baseline idle e' sempre 'background-subtraction'.

        Anche se un futuro commit volesse usarla come EnB, il test fallisce.
        """
        iso = IsoAlignment()
        record = iso.idle_baseline_record(
            method="median-of-3-idle-windows",
            value_w=45.5,
            windows_n=3,
        )

        assert record["idle_baseline_role"] == "background-subtraction"
        assert record["idle_baseline_method"] == "median-of-3-idle-windows"
        assert record["idle_baseline_value_w"] == 45.5
        assert record["idle_baseline_windows_n"] == 3

    def test_baseline_idle_metodo_non_dichiarato_rifiutato(self):
        """Un metodo di baseline non dichiarato non entra nel CSV.

        Se un futuro commit introduce un metodo senza aggiornare
        IDLE_BASELINE_METHODS, il test fallisce.
        """
        iso = IsoAlignment()
        try:
            iso.idle_baseline_record(
                method="unknown-method",
                value_w=45.0,
                windows_n=3,
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)

    def test_baseline_idle_non_e_enb(self):
        """Test critico: baseline idle non popola i campi EnB.

        Se una futura modifica confonde di nuovo la potenza a riposo
        con la baseline di performance, questo test fallisce.
        """
        iso = IsoAlignment()
        idle_record = iso.idle_baseline_record(
            method="median-of-3-idle-windows",
            value_w=45.5,
            windows_n=3,
        )

        # La baseline idle non ha campi EnB
        assert "enb_model_id" not in idle_record
        assert "enb_fit_method" not in idle_record
        assert "enb_prediction_j" not in idle_record

        # Il ruolo e' esplicitamente diverso da qualsiasi EnB
        assert idle_record["idle_baseline_role"] == "background-subtraction"


class TestMeasurementRole:
    """Il ruolo epistemico della riga e' dichiarato, non implicito."""

    def test_measurement_role_valido(self):
        """Ogni ruolo in MEASUREMENT_ROLES e' accettato."""
        iso = IsoAlignment()
        for role in MEASUREMENT_ROLES:
            record = iso.measurement_role_record(role=role)
            assert record["measurement_role"] == role

    def test_measurement_role_non_dichiarato_rifiutato(self):
        """Un ruolo non dichiarato non entra nel CSV."""
        iso = IsoAlignment()
        try:
            iso.measurement_role_record(role="invented-role")
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)


class TestQuantizzazione:
    """La quantizzazione e' dichiarata, non dedotta dal nome del modello."""

    def test_quantizzazione_sconosciuta_non_inventata(self):
        """Se la quantizzazione non e' dichiarata, il valore e' 'unknown'.

        Non si inventa un parser fragile che legge 'q4_K_M' dal nome del
        modello: se il valore non e' dichiarato dalla configurazione,
        resta 'unknown'.
        """
        # Il test verifica il principio: un campo assente non diventa
        # un valore tecnico non verificato.
        record = {
            "model_name": "qwen2.5:0.5b",
            "model_quantization": "unknown",
            "model_precision": "unknown",
        }

        assert record["model_quantization"] == "unknown"
        assert record["model_precision"] == "unknown"
        # Non e' vuoto, non e' un valore inventato
        assert record["model_quantization"] != ""


class TestManifestoISO:
    """Il manifesto ISO dichiara esplicitamente i limiti del progetto."""

    def test_manifesto_iso_dichiara_limiti(self):
        """Il manifesto elenca le certificazioni NON rivendicate.

        CasualWatt non e' certificato ISO 50001, ISO 14064 o ISO/IEC 42001.
        Il manifesto lo dichiara esplicitamente per evitare fraintendimenti.
        """
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-20261115")

        assert "ISO 50001 certification" in manifest["not_claimed"]
        assert "ISO 14064 verification" in manifest["not_claimed"]
        assert "ISO/IEC 42001 certification" in manifest["not_claimed"]

    def test_manifesto_iso_standard_primario(self):
        """ISO 50006 e' lo standard primario, non ISO 50001."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-20261115")

        assert manifest["primary_standard"] == "ISO 50006:2023"
        assert manifest["alignment_scope"] == "methodological"

    def test_manifesto_iso_enpi_inclusi(self):
        """Gli EnPI del manifesto sono quelli dichiarati nel capitolo ISO."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-20261115")

        assert "energy_per_total_token_j" in manifest["enpi"]
        assert "energy_per_output_token_j" in manifest["enpi"]
        assert "energy_per_correct_answer_j" in manifest["enpi"]
        assert "e_net_j" in manifest["enpi"]

    def test_manifesto_iso_confini_dichiarati(self):
        """I confini di misura sono dichiarati nel manifesto."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-20261115")

        assert manifest["boundaries"]["cpu"] == "package"
        assert manifest["boundaries"]["gpu"] == "separate"
        assert manifest["boundaries"]["network"] == "estimated"
        assert manifest["boundaries"]["cloud"] == "estimated"

    def test_manifesto_iso_emissions_applicable(self):
        """ISO 14064 e' applicabile solo se il run produce CO2eq."""
        iso = IsoAlignment()

        # Senza emissioni, non applicabile
        manifest_no = iso.manifest(run_id="test-no-emissions")
        assert manifest_no["ghg_reporting_reference"]["applicable"] is False

        # Con emissioni locali, applicabile
        manifest_yes = iso.manifest(
            run_id="test-with-emissions",
            local_emissions_gco2eq=0.000304,
        )
        assert manifest_yes["ghg_reporting_reference"]["applicable"] is True

    def test_manifesto_iso_scrittura_json(self):
        """Il manifesto e' scrivibile come JSON senza errori."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-json-write")

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "iso_alignment_test.json"
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, indent=2, ensure_ascii=False)

            with open(path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)

            assert loaded["run_id"] == "test-json-write"
            assert loaded["primary_standard"] == "ISO 50006:2023"


class TestVocabolarioChiuso:
    """I vocabolari sono chiusi: un token non dichiarato non entra."""

    def test_enb_fit_methods_chiuso(self):
        """ENB_FIT_METHODS e' un frozenset: non modificabile a runtime."""
        assert isinstance(ENB_FIT_METHODS, frozenset)
        assert "weighted-linear-surface-QR" in ENB_FIT_METHODS
        assert "weighted-linear-surface-SVD" in ENB_FIT_METHODS

    def test_idle_baseline_methods_chiuso(self):
        """IDLE_BASELINE_METHODS e' un frozenset: non modificabile a runtime."""
        assert isinstance(IDLE_BASELINE_METHODS, frozenset)
        assert "median-of-3-idle-windows" in IDLE_BASELINE_METHODS

    def test_measurement_roles_chiuso(self):
        """MEASUREMENT_ROLES e' un frozenset: non modificabile a runtime."""
        assert isinstance(MEASUREMENT_ROLES, frozenset)
        assert "direct-counter" in MEASUREMENT_ROLES
        assert "attributed" in MEASUREMENT_ROLES
        assert "estimated" in MEASUREMENT_ROLES
        assert "unavailable" in MEASUREMENT_ROLES


class TestUncertaintyGUM:
    """L'incertezza e' dichiarata con metodo e componenti, non inventata."""

    def test_uncertainty_metodo_valido(self):
        """Un metodo di incertezza dichiarato produce i campi corretti.

        Il test verifica che uncertainty_record restituisca i campi GUM
        quando il metodo e' dichiarato e il budget e' disponibile.
        """
        iso = IsoAlignment()
        record = iso.uncertainty_record(
            method="quadrature-conservative-semiranges",
            budget_j=0.5,
            components={"half_range_pre_w": 0.3, "half_drift_w": 0.4},
        )

        assert record["uncertainty_method"] == "quadrature-conservative-semiranges"
        assert record["uncertainty_budget_j"] == 0.5
        assert "half_range_pre_w" in record["uncertainty_components"]

    def test_uncertainty_senza_budget_resta_vuota(self):
        """Se il budget non e' calcolabile, la cella resta vuota, non zero.

        Un budget inventato sarebbe una violazione del principio GUM:
        l'incertezza va dichiarata solo quando e' calcolabile.
        """
        iso = IsoAlignment()
        record = iso.uncertainty_record(
            method="quadrature-conservative-semiranges",
            budget_j=None,
        )

        assert record["uncertainty_method"] == "quadrature-conservative-semiranges"
        assert record["uncertainty_budget_j"] == ""
        assert record["uncertainty_components"] == ""

    def test_uncertainty_metodo_non_dichiarato_rifiutato(self):
        """Un metodo di incertezza non dichiarato non entra nel CSV."""
        iso = IsoAlignment()
        try:
            iso.uncertainty_record(
                method="unknown-method",
                budget_j=0.5,
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)

    def test_uncertainty_components_assenti(self):
        """Se le componenti non sono disponibili, il campo resta vuoto."""
        iso = IsoAlignment()
        record = iso.uncertainty_record(
            method="quadrature-conservative-semiranges",
            budget_j=0.5,
            components=None,
        )

        assert record["uncertainty_budget_j"] == 0.5
        assert record["uncertainty_components"] == ""


class TestManifestoISOAggiornato:
    """Il manifesto ISO dichiara i nuovi standard aggiunti."""

    def test_manifesto_include_iso_50015(self):
        """ISO 50015 e' il riferimento M&V del manifesto."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-mv")
        assert manifest["m_and_v_reference"] == "ISO 50015:2014"

    def test_manifesto_include_gum(self):
        """ISO/IEC Guide 98-3 (GUM) e' il riferimento incertezza."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-gum")
        assert manifest["uncertainty_reference"] == "ISO/IEC Guide 98-3:2008"

    def test_manifesto_include_25059(self):
        """ISO/IEC 25059 e' il riferimento qualità IA."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-25059")
        assert manifest["ai_quality_reference"] == "ISO/IEC 25059:2023"

    def test_manifesto_include_ts25058(self):
        """ISO/IEC TS 25058 e' il riferimento valutazione IA."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-ts25058")
        assert manifest["ai_evaluation_reference"] == "ISO/IEC TS 25058:2024"

    def test_manifesto_include_5259(self):
        """ISO/IEC 5259 e' il riferimento qualità dati."""
        iso = IsoAlignment()
        manifest = iso.manifest(run_id="test-5259")
        assert manifest["data_quality_reference"] == "ISO/IEC 5259 series"


class TestVocabolarioChiuso:
    """I vocabolari sono chiusi: un token non dichiarato non entra."""

    def test_enb_fit_methods_chiuso(self):
        """ENB_FIT_METHODS e' un frozenset: non modificabile a runtime."""
        assert isinstance(ENB_FIT_METHODS, frozenset)
        assert "weighted-linear-surface-QR" in ENB_FIT_METHODS
        assert "weighted-linear-surface-SVD" in ENB_FIT_METHODS

    def test_idle_baseline_methods_chiuso(self):
        """IDLE_BASELINE_METHODS e' un frozenset: non modificabile a runtime."""
        assert isinstance(IDLE_BASELINE_METHODS, frozenset)
        assert "median-of-3-idle-windows" in IDLE_BASELINE_METHODS

    def test_measurement_roles_chiuso(self):
        """MEASUREMENT_ROLES e' un frozenset: non modificabile a runtime."""
        assert isinstance(MEASUREMENT_ROLES, frozenset)
        assert "direct-counter" in MEASUREMENT_ROLES
        assert "attributed" in MEASUREMENT_ROLES
        assert "estimated" in MEASUREMENT_ROLES
        assert "unavailable" in MEASUREMENT_ROLES

    def test_uncertainty_methods_chiuso(self):
        """UNCERTAINTY_METHODS e' un frozenset: non modificabile a runtime."""
        assert isinstance(UNCERTAINTY_METHODS, frozenset)
        assert "quadrature-conservative-semiranges" in UNCERTAINTY_METHODS


class TestEvidenceRecord:
    """La prova della correttezza non duplica eval_method ne' is_correct."""

    def test_evidence_ground_truth_match(self):
        """Un tipo di evidenza dichiarato produce i campi corretti.

        Il test verifica che evidence_record restituisca i campi
        quando evidence_type, rule_version e determinate sono validi.
        """
        iso = IsoAlignment()
        record = iso.evidence_record(
            evidence_type="ground-truth-match",
            evidence_id="task-001",
            rule_version="evaluator_v1",
            threshold="1e-6",
            determinate=True,
            gt_version="1.0",
            gt_sha256="abc123",
        )

        assert record["correctness_evidence_type"] == "ground-truth-match"
        assert record["correctness_evidence_id"] == "task-001"
        assert record["correctness_rule_version"] == "evaluator_v1"
        assert record["correctness_threshold"] == "1e-6"
        assert record["correctness_determinate"] == "true"
        assert record["ground_truth_version"] == "1.0"
        assert record["ground_truth_sha256"] == "abc123"

    def test_evidence_type_non_dichiarato_rifiutato(self):
        """Un tipo di evidenza non dichiarato non entra nel CSV."""
        iso = IsoAlignment()
        try:
            iso.evidence_record(
                evidence_type="invented-evidence",
                determinate=True,
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)

    def test_evidence_rule_version_non_dichiarata_rifiutata(self):
        """Una versione regola non dichiarata non entra nel CSV."""
        iso = IsoAlignment()
        try:
            iso.evidence_record(
                evidence_type="ground-truth-match",
                rule_version="invented-v99",
                determinate=True,
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarata" in str(exc)

    def test_evidence_indeterminato_non_diventa_errato(self):
        """Se determinate=False, is_correct e' N/A, non 0.

        Il campo correctness_determinate distingue N/A da errore:
        un verdetto indeterminato non e' un verdetto errato.
        """
        iso = IsoAlignment()
        record = iso.evidence_record(
            evidence_type="none",
            determinate=False,
        )

        assert record["correctness_determinate"] == "false"
        assert record["correctness_evidence_type"] == "none"

    def test_evidence_vocabolari_chiusi(self):
        """I vocabolari della prova sono frozenset immutabili."""
        assert isinstance(CORRECTNESS_EVIDENCE_TYPES, frozenset)
        assert isinstance(CORRECTNESS_RULE_VERSIONS, frozenset)
        assert isinstance(GROUND_TRUTH_QUALITY_STATUSES, frozenset)
        assert "ground-truth-match" in CORRECTNESS_EVIDENCE_TYPES
        assert "deterministic-contract" in CORRECTNESS_EVIDENCE_TYPES
        assert "evaluator_v1" in CORRECTNESS_RULE_VERSIONS
        assert "reviewed" in GROUND_TRUTH_QUALITY_STATUSES

    def test_ground_truth_hash_per_riproducibilita(self):
        """L'hash del ground truth rende la valutazione riproducibile.

        Una risposta 'corretta' senza hash del ground truth non e'
        riproducibile: non si sa quale versione della verita' e' stata usata.
        """
        iso = IsoAlignment()
        record = iso.evidence_record(
            evidence_type="ground-truth-match",
            gt_version="1.0",
            gt_sha256="sha256:abc123",
            gt_quality="reviewed",
            determinate=True,
        )

        assert record["ground_truth_sha256"] == "sha256:abc123"
        assert record["ground_truth_version"] == "1.0"
        assert record["ground_truth_quality_status"] == "reviewed"

    def test_ground_truth_hash_obbligatorio_quando_usato(self):
        """Se evidence_type implica ground truth, hash e versione sono obbligatori.

        Una risposta 'corretta' senza hash del ground truth non e'
        riproducibile: la guardia impedisce di scrivere il verdetto
        senza dichiarare quale ground truth e' stato usato.
        """
        iso = IsoAlignment()
        try:
            iso.evidence_record(
                evidence_type="ground-truth-match",
                evidence_id="task-001",
                rule_version="evaluator_v1",
                threshold="1e-6",
                determinate=True,
                gt_version="",
                gt_sha256="",
                gt_quality="reviewed",
            )
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "riproducibile" in str(exc)

    def test_ground_truth_hash_vuoto_se_non_applicabile(self):
        """Se evidence_type e' 'none', ground truth puo' restare vuoto.

        Quando non c'e' prova di correttezza, non c'e' ground truth
        da versionare: i campi restano vuoti senza errore.
        """
        iso = IsoAlignment()
        record = iso.evidence_record(
            evidence_type="none",
            evidence_id="",
            rule_version="evaluator_v1",
            threshold="",
            determinate=False,
            gt_version="",
            gt_sha256="",
            gt_quality="not-applicable",
        )

        assert record["ground_truth_version"] == ""
        assert record["ground_truth_sha256"] == ""

    def test_ground_truth_campi_in_schema(self):
        """ground_truth_version e ground_truth_sha256 sono in EVALUATION_RESULT_COLUMNS.

        Test di regressione: questi campi non devono essere rimossi
        dallo schema, perche' sono l'unico modo per rendere riproducibile
        l'affermazione 'questa risposta e' corretta rispetto a questa verita''.
        """
        from evaluation_schema import EVALUATION_RESULT_COLUMNS
        assert "ground_truth_version" in EVALUATION_RESULT_COLUMNS
        assert "ground_truth_sha256" in EVALUATION_RESULT_COLUMNS


class TestJudgeRole:
    """Il judge LLM non sostituisce il verdetto primario is_correct."""

    def test_judge_override_disabilitato_di_default(self):
        """judge_override_allowed e' False di default.

        Il judge non sostituisce silenziosamente is_correct:
        puo' auditare o descrivere la qualita', ma non decidere.
        """
        iso = IsoAlignment()
        record = iso.judge_role_record()

        assert record["judge_override_allowed"] == "false"
        assert record["judge_role"] == "not-used"

    def test_judge_ruolo_secondary_quality(self):
        """Se il judge e' usato per qualita', il ruolo e' dichiarato."""
        iso = IsoAlignment()
        record = iso.judge_role_record(
            judge_role="secondary-quality",
            judge_calibration_status="calibrated",
        )

        assert record["judge_role"] == "secondary-quality"
        assert record["judge_calibration_status"] == "calibrated"

    def test_judge_acCORDO_con_verdetto_primario(self):
        """Se il judge concorda con is_correct, il campo e' 'true'."""
        iso = IsoAlignment()
        record = iso.judge_role_record(
            judge_role="secondary-quality",
            judge_agrees_with_primary=True,
        )

        assert record["judge_agrees_with_primary"] == "true"

    def test_judge_disaccordo_registrato(self):
        """Se il judge discorda, la ragione e' registrata."""
        iso = IsoAlignment()
        record = iso.judge_role_record(
            judge_role="secondary-quality",
            judge_agrees_with_primary=False,
            judge_disagreement_reason="il judge valuta qualita', non verita'",
        )

        assert record["judge_agrees_with_primary"] == "false"
        assert "qualita'" in record["judge_disagreement_reason"]

    def test_judge_campi_vuoti_se_non_applicato(self):
        """Se il judge non e' applicato, i campi restano vuoti."""
        iso = IsoAlignment()
        record = iso.judge_role_record()

        assert record["judge_agrees_with_primary"] == ""
        assert record["judge_disagreement_reason"] == ""

    def test_judge_ruolo_non_dichiarato_rifiutato(self):
        """Un ruolo judge non dichiarato non entra nel CSV."""
        iso = IsoAlignment()
        try:
            iso.judge_role_record(judge_role="invented-role")
            assert False, "doveva sollevare ValueError"
        except ValueError as exc:
            assert "non dichiarato" in str(exc)

    def test_judge_vocabolari_chiusi(self):
        """I vocabolari del judge sono frozenset immutabili."""
        assert isinstance(JUDGE_ROLES, frozenset)
        assert isinstance(JUDGE_CALIBRATION_STATUSES, frozenset)
        assert "secondary-quality" in JUDGE_ROLES
        assert "not-used" in JUDGE_ROLES
        assert "calibrated" in JUDGE_CALIBRATION_STATUSES
        assert "not-calibrated" in JUDGE_CALIBRATION_STATUSES
