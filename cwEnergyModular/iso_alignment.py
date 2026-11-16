# -*- coding: utf-8 -*-
"""iso_alignment.py — ruoli metodologici ISO 50006, senza calcolo energetico.

Questo modulo non misura energia, non calcola baseline e non scrive righe.
Dichiara e valida i ruoli metodologici che il capitolo ISO della tesi
afferma: EnB separata dalla baseline idle, metodo di fit, ruolo epistemico
della riga. Ogni funzione restituisce un dizionario pronto per essere
unito al record CSV; se un campo non e' disponibile, resta vuoto, mai zero
inventato.

L'EnB (Energy Baseline metodologica) e' la superficie pesata
E = f(N_in, N_out) stimata da `surface_fit.py`. La baseline idle
(`baseline_pre_w`) e' una grandezza di correzione del fondo, non una EnB.
I due concetti non vanno confusi: questo modulo impedisce la confusione
convalidando i token ammessi e richiedendo i campi obbligatori.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


#: Metodi di fit della superficie EnB dichiarati nel capitolo ISO.
ENB_FIT_METHODS: frozenset = frozenset({
    "weighted-linear-surface-QR",
    "weighted-linear-surface-SVD",
})

#: Metodi di baseline idle dichiarati nel capitolo ISO.
IDLE_BASELINE_METHODS: frozenset = frozenset({
    "median-of-3-idle-windows",
})

#: Ruoli epistemici della riga: misura diretta, attribuzione o stima.
MEASUREMENT_ROLES: frozenset = frozenset({
    "direct-counter",
    "attributed",
    "estimated",
    "unavailable",
})

#: Metodi di dichiarazione dell'incertezza (ISO/IEC Guide 98-3, GUM).
UNCERTAINTY_METHODS: frozenset = frozenset({
    "quadrature-conservative-semiranges",
})

#: Tipi di prova della correttezza (ISO/IEC 25059 + TS 25058).
# Non duplica eval_method: dichiara quale prova concreta ha prodotto il verdetto.
CORRECTNESS_EVIDENCE_TYPES: frozenset = frozenset({
    "ground-truth-match",
    "semantic-threshold",
    "lexical-threshold",
    "deterministic-contract",
    "none",
})

#: Versioni delle regole di valutazione.
CORRECTNESS_RULE_VERSIONS: frozenset = frozenset({
    "evaluator_v1",
    "robust_v1",
})

#: Status di qualita' del ground truth (ISO/IEC 5259-4).
GROUND_TRUTH_QUALITY_STATUSES: frozenset = frozenset({
    "unreviewed",
    "reviewed",
    "disputed",
    "excluded",
    "not-applicable",
})

#: Ruoli del judge LLM.
JUDGE_ROLES: frozenset = frozenset({
    "secondary-quality",
    "not-used",
})

#: Status di calibrazione del judge.
JUDGE_CALIBRATION_STATUSES: frozenset = frozenset({
    "not-calibrated",
    "calibrated",
    "failed",
})



@dataclass(frozen=True)
class IsoAlignment:
    """Dichiara e valida i ruoli metodologici ISO 50006.

    Attributi:
        primary_standard: standard primario (ISO 50006:2023).
        alignment_scope: ambito dell'allineamento (methodological, non certification).
    """

    primary_standard: str = "ISO 50006:2023"
    alignment_scope: str = "methodological"

    # ------------------------------------------------------------------
    # EnB — baseline normalizzata della performance
    # ------------------------------------------------------------------

    def enb_record(
        self,
        *,
        model_id: str,
        fit_method: str,
        coefficients_sha256: str,
        in_coverage: bool,
        prediction_j: Optional[float],
        residual_j: Optional[float],
    ) -> Dict:
        """Restituisce i campi EnB per una riga CSV.

        Args:
            model_id: identificatore del modello (es. nome del modello).
            fit_method: metodo di fit (deve essere in ENB_FIT_METHODS).
            coefficients_sha256: hash SHA-256 dei coefficienti della superficie.
            in_coverage: True se la geometria e' dentro il dominio di supporto.
            prediction_j: energia attesa dalla EnB per quella geometria.
            residual_j: e_net_j - prediction_j, con segno conservato.

        Returns:
            Dizionario con i campi enb_* pronti per il record CSV.

        Raises:
            ValueError: se fit_method non e' dichiarato.
        """
        if fit_method not in ENB_FIT_METHODS:
            raise ValueError(
                f"metodo EnB non dichiarato: {fit_method!r}. "
                f"Valori ammessi: {sorted(ENB_FIT_METHODS)}"
            )

        residual_ratio = (
            residual_j / prediction_j
            if residual_j is not None and prediction_j is not None and prediction_j > 0
            else ""
        )

        return {
            "enb_model_id": model_id,
            "enb_fit_method": fit_method,
            "enb_coefficients_sha256": coefficients_sha256,
            "enb_in_coverage": str(in_coverage).lower() if in_coverage else "",
            "enb_prediction_j": prediction_j if prediction_j is not None else "",
            "enb_residual_j": residual_j if residual_j is not None else "",
            "enb_residual_ratio": residual_ratio,
        }

    def enb_unavailable_record(self, reason: str = "") -> Dict:
        """Restituisce i campi EnB vuoti quando la superficie non e' applicabile.

        Args:
            reason: motivo opzionale (es. "fuori copertura", "fit non disponibile").

        Returns:
            Dizionario con tutti i campi EnB vuoti.
        """
        return {
            "enb_model_id": "",
            "enb_model_version": "",
            "enb_fit_method": "",
            "enb_coefficients_sha256": "",
            "enb_in_coverage": "",
            "enb_prediction_j": "",
            "enb_residual_j": "",
            "enb_residual_ratio": "",
        }

    # ------------------------------------------------------------------
    # Baseline idle — correzione del fondo, non EnB
    # ------------------------------------------------------------------

    def idle_baseline_record(
        self,
        *,
        method: str,
        value_w: float,
        windows_n: int,
    ) -> Dict:
        """Restituisce i campi della baseline idle per una riga CSV.

        La baseline idle e' una grandezza di correzione del fondo, non una
        EnB metodologica. Il ruolo e' sempre "background-subtraction".

        Args:
            method: metodo di calcolo (deve essere in IDLE_BASELINE_METHODS).
            value_w: potenza idle in watt (baseline_pre_w).
            windows_n: numero di finestre usate per la mediana.

        Returns:
            Dizionario con i campi idle_baseline_* pronti per il record CSV.

        Raises:
            ValueError: se method non e' dichiarato.
        """
        if method not in IDLE_BASELINE_METHODS:
            raise ValueError(
                f"metodo baseline idle non dichiarato: {method!r}. "
                f"Valori ammessi: {sorted(IDLE_BASELINE_METHODS)}"
            )

        return {
            "idle_baseline_method": method,
            "idle_baseline_role": "background-subtraction",
            "idle_baseline_value_w": value_w,
            "idle_baseline_windows_n": windows_n,
        }

    # ------------------------------------------------------------------
    # Ruolo epistemico della riga
    # ------------------------------------------------------------------

    def measurement_role_record(
        self,
        *,
        role: str,
    ) -> Dict:
        """Restituisce il ruolo epistemico della riga.

        Args:
            role: ruolo (deve essere in MEASUREMENT_ROLES).

        Returns:
            Dizionario con il campo measurement_role.

        Raises:
            ValueError: se role non e' dichiarato.
        """
        if role not in MEASUREMENT_ROLES:
            raise ValueError(
                f"ruolo di misura non dichiarato: {role!r}. "
                f"Valori ammessi: {sorted(MEASUREMENT_ROLES)}"
            )

        return {
            "measurement_role": role,
        }

    # ------------------------------------------------------------------
    # Incertezza GUM-like (ISO/IEC Guide 98-3)
    # ------------------------------------------------------------------

    def uncertainty_record(
        self,
        *,
        method: str,
        budget_j: Optional[float],
        components: Optional[Dict] = None,
    ) -> Dict:
        """Restituisce i campi di incertezza dichiarati per riga.

        L'incertezza e' espressa come budget conservativo di semi-ampiezze
        combinato in quadratura, coerente con i principi del GUM ma non
        presentato come deviazione standard campionaria.

        Args:
            method: metodo di dichiarazione (deve essere in UNCERTAINTY_METHODS).
            budget_j: budget di incertezza in Joule, o None se non calcolabile.
            components: dizionario delle componenti separate (opzionale).

        Returns:
            Dizionario con i campi uncertainty_* pronti per il record CSV.

        Raises:
            ValueError: se method non e' dichiarato.
        """
        if method not in UNCERTAINTY_METHODS:
            raise ValueError(
                f"metodo di incertezza non dichiarato: {method!r}. "
                f"Valori ammessi: {sorted(UNCERTAINTY_METHODS)}"
            )

        return {
            "uncertainty_method": method,
            "uncertainty_budget_j": budget_j if budget_j is not None else "",
            "uncertainty_components": (
                str(components) if components is not None else ""
            ),
        }

    # ------------------------------------------------------------------
    # Manifesto ISO per run
    # ------------------------------------------------------------------

    def manifest(
        self,
        *,
        run_id: str,
        enb_model_id: str = "",
        enb_fit_method: str = "",
        enb_coefficients_sha256: str = "",
        idle_baseline_method: str = "median-of-3-idle-windows",
        idle_baseline_role: str = "background-subtraction",
        local_emissions_gco2eq: Optional[float] = None,
        cloud_emissions_gco2eq: Optional[float] = None,
    ) -> Dict:
        """Genera il manifesto ISO per un run.

        Il manifesto dichiara esplicitamente cosa CasualWatt misura,
        attribuisce e stima, e cosa NON rivendica.

        Args:
            run_id: identificatore del run.
            enb_model_id: identificatore del modello EnB.
            enb_fit_method: metodo di fit della superficie.
            enb_coefficients_sha256: hash dei coefficienti.
            idle_baseline_method: metodo della baseline idle.
            idle_baseline_role: ruolo della baseline idle.
            local_emissions_gco2eq: emissioni locali se calcolate.
            cloud_emissions_gco2eq: emissioni cloud se calcolate.

        Returns:
            Dizionario pronto per essere scritto come JSON.
        """
        has_emissions = (
            local_emissions_gco2eq is not None
            or cloud_emissions_gco2eq is not None
        )

        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "primary_standard": self.primary_standard,
            "alignment_scope": self.alignment_scope,
            "m_and_v_reference": "ISO 50015:2014",
            "uncertainty_reference": "ISO/IEC Guide 98-3:2008",
            "ai_quality_reference": "ISO/IEC 25059:2023",
            "ai_evaluation_reference": "ISO/IEC TS 25058:2024",
            "data_quality_reference": "ISO/IEC 5259 series",
            "enpi": [
                "energy_per_total_token_j",
                "energy_per_output_token_j",
                "energy_per_correct_answer_j",
                "e_net_j",
            ],
            "enb": {
                "model_id": enb_model_id,
                "fit_method": enb_fit_method,
                "variables": [
                    "input_tokens",
                    "output_tokens",
                    "input_output_interaction",
                ],
                "coefficients_sha256": enb_coefficients_sha256,
            },
            "idle_baseline": {
                "method": idle_baseline_method,
                "role": idle_baseline_role,
            },
            "boundaries": {
                "cpu": "package",
                "gpu": "separate",
                "network": "estimated",
                "cloud": "estimated",
            },
            "quality_framework": "ISO/IEC 25010:2023",
            "ai_governance_reference": "ISO/IEC 42001:2023",
            "ghg_reporting_reference": {
                "standard": "ISO 14064-1:2018",
                "applicable": has_emissions,
            },
            "not_claimed": [
                "ISO 50001 certification",
                "ISO 14064 verification",
                "ISO/IEC 42001 certification",
            ],
        }

    # ------------------------------------------------------------------
    # Prova della correttezza (ISO/IEC 25059 + TS 25058)
    # Non duplica eval_method ne' is_correct: dichiara la prova concreta.
    # ------------------------------------------------------------------

    def evidence_record(
        self,
        *,
        evidence_type: str,
        evidence_id: str = "",
        rule_version: str = "",
        threshold: str = "",
        determinate: bool,
        gt_version: str = "",
        gt_sha256: str = "",
        gt_quality: str = "",
    ) -> Dict:
        """Restituisce i campi della prova della correttezza per una riga.

        Non duplica eval_method (come e' stata valutata) ne' is_correct
        (il verdetto binario). Dichiara: quale prova concreta ha prodotto
        il verdetto, con quale regola, e se il verdetto e' determinabile.

        Args:
            evidence_type: tipo di prova (ground-truth-match, semantic-threshold,
                lexical-threshold, deterministic-contract, none).
            evidence_id: task_id o ID del contratto/ground truth.
            rule_version: versione della regola (evaluator_v1, robust_v1).
            threshold: soglia applicata (es. 0.85, absolute=1e-6).
            determinate: True se is_correct e' 0/1; False se N/A.
            gt_version: versione del ground truth.
            gt_sha256: hash del ground truth per riproducibilita'.
            gt_quality: qualita' del ground truth (opzionale).

        Returns:
            Dizionario con i campi correctness_* e ground_truth_* pronti
            per il record CSV.

        Raises:
            ValueError: se evidence_type, rule_version o gt_quality non sono dichiarati.
        """
        if evidence_type not in CORRECTNESS_EVIDENCE_TYPES:
            raise ValueError(
                f"tipo di evidenza non dichiarato: {evidence_type!r}. "
                f"Valori ammessi: {sorted(CORRECTNESS_EVIDENCE_TYPES)}"
            )
        if rule_version and rule_version not in CORRECTNESS_RULE_VERSIONS:
            raise ValueError(
                f"versione regola non dichiarata: {rule_version!r}. "
                f"Valori ammessi: {sorted(CORRECTNESS_RULE_VERSIONS)}"
            )
        if gt_quality and gt_quality not in GROUND_TRUTH_QUALITY_STATUSES:
            raise ValueError(
                f"qualita' ground truth non dichiarata: {gt_quality!r}. "
                f"Valori ammessi: {sorted(GROUND_TRUTH_QUALITY_STATUSES)}"
            )
        # Se l'evidence type implica ground truth, versione e hash sono obbligatori.
        # Una risposta "corretta" senza hash del ground truth non e' riproducibile.
        _gt_required_types = frozenset({
            "ground-truth-match",
            "deterministic-contract",
        })
        if evidence_type in _gt_required_types:
            if not gt_version or not gt_sha256:
                raise ValueError(
                    f"evidence_type = {evidence_type!r} richiede "
                    f"ground_truth_version e ground_truth_sha256 non vuoti: "
                    f"una risposta 'corretta' senza hash del ground truth "
                    f"non e' riproducibile."
                )

        return {
            "correctness_evidence_type": evidence_type,
            "correctness_evidence_id": evidence_id,
            "correctness_rule_version": rule_version,
            "correctness_threshold": threshold,
            "correctness_determinate": str(determinate).lower(),
            "ground_truth_version": gt_version,
            "ground_truth_sha256": gt_sha256,
            "ground_truth_quality_status": gt_quality,
        }

    # ------------------------------------------------------------------
    # Ruolo del judge (non sostituisce il verdetto primario)
    # ------------------------------------------------------------------

    def judge_role_record(
        self,
        *,
        judge_role: str = "not-used",
        judge_override_allowed: bool = False,
        judge_agrees_with_primary: Optional[bool] = None,
        judge_disagreement_reason: str = "",
        judge_calibration_status: str = "not-calibrated",
    ) -> Dict:
        """Restituisce i campi del judge come criterio secondario.

        Il judge LLM non sostituisce il verdetto primario is_correct.
        Puo' auditare o descrivere la qualita', ma non decidere la correttezza.

        Args:
            judge_role: ruolo del judge (secondary-quality o not-used).
            judge_override_allowed: False per default — il judge non
                sostituisce silenziosamente is_correct.
            judge_agrees_with_primary: il judge concorda con is_correct?
            judge_disagreement_reason: perche' il judge discorda.
            judge_calibration_status: stato di calibrazione del judge.

        Returns:
            Dizionario con i campi judge_* pronti per il record CSV.

        Raises:
            ValueError: se judge_role o judge_calibration_status non sono dichiarati.
        """
        if judge_role not in JUDGE_ROLES:
            raise ValueError(
                f"ruolo judge non dichiarato: {judge_role!r}. "
                f"Valori ammessi: {sorted(JUDGE_ROLES)}"
            )
        if judge_calibration_status not in JUDGE_CALIBRATION_STATUSES:
            raise ValueError(
                f"calibrazione judge non dichiarata: {judge_calibration_status!r}. "
                f"Valori ammessi: {sorted(JUDGE_CALIBRATION_STATUSES)}"
            )
        return {
            "judge_role": judge_role,
            "judge_override_allowed": str(judge_override_allowed).lower(),
            "judge_agrees_with_primary": (
                str(judge_agrees_with_primary).lower()
                if judge_agrees_with_primary is not None
                else ""
            ),
            "judge_disagreement_reason": judge_disagreement_reason,
            "judge_calibration_status": judge_calibration_status,
        }

