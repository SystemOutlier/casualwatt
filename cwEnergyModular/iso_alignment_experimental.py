# -*- coding: utf-8 -*-
"""
iso_alignment_experimental.py — Colonne ISO sperimentali (riserva futura).

Questo modulo conserva le colonne ISO 50006/50015 e GUM identificate durante
il lavoro di allineamento metrologico. NON sono scritte da produzione e NON
fanno parte dello schema P5 congelato.

Stato: SPERIMENTALE
Data identificazione: 2026-11
Perimetro: Allineamento ISO 50006 (EnB), ISO 50015 (M&V), GUM (incertezza)

Le colonne qui dichiarate sono state rimosse da CSV_COLUMNS e
RUN_METADATA_COLUMNS di casualwatt_csv_export.py perche':
- non esiste un percorso di produzione che le popoli;
- non entrano nei risultati P5 finche' non esiste un produttore reale;
- non vengono usate per decisioni del gate F.12;
- creerebbero un'aspettativa falsa nello schema congelato.

Quando sara' implementato il percorso di produzione (surface_fit.py per EnB,
machine_state.py per termico, ecc.), queste colonne torneranno in
casualwatt_csv_export.py con il loro commit dedicato.

ISO_CSV_COLUMNS elenca le 31 colonne rimosse da CSV_COLUMNS.
ISO_RUN_METADATA_COLUMNS elenca le 11 colonne rimosse da RUN_METADATA_COLUMNS.
"""
from __future__ import annotations

from typing import List

# 31 colonne rimosse da CSV_COLUMNS (erano accodate a riga 209-250)
# Gruppi: EnB (8), baseline idle ruolo (4), ruolo epistemico (1),
# quantizzazione (5), batch (2), termico (4), GUM (3), M&V (4).
ISO_CSV_COLUMNS: List[str] = [
    # ISO 50006: EnB distinta dalla baseline idle.
    # L'EnB e' la superficie pesata E=f(N_in, N_out) di surface_fit.py;
    # la baseline idle (baseline_pre_w) e' una correzione del fondo.
    "enb_model_id",
    "enb_model_version",
    "enb_fit_method",
    "enb_coefficients_sha256",
    "enb_in_coverage",
    "enb_prediction_j",
    "enb_residual_j",
    "enb_residual_ratio",
    # Ruolo esplicito della baseline idle: correzione del fondo, non EnB.
    "idle_baseline_method",
    "idle_baseline_role",
    "idle_baseline_value_w",
    "idle_baseline_windows_n",
    # Ruolo epistemico della riga: misura diretta, attribuzione o stima.
    "measurement_role",
    # Variabili rilevanti ISO 50006: quantizzazione e configurazione modello.
    "model_quantization",
    "model_precision",
    "model_context_length",
    "model_backend_version",
    "model_parameters_b",
    # Batch size dichiarato (ISO 50006: variabile rilevante).
    "inference_batch_size",
    "concurrent_requests",
    # Stato termico: temperatura e throttling come covariate dichiarate.
    "cpu_temperature_c",
    "gpu_temperature_c",
    "thermal_throttle_detected",
    "thermal_throttle_source",
    # GUM (ISO/IEC Guide 98-3): incertezza dichiarata per riga.
    "uncertainty_method",
    "uncertainty_budget_j",
    "uncertainty_components",
    # ISO 50015: perimetro M&V.
    "m_and_v_boundary",
    "baseline_scenario",
    "intervention_scenario",
    "comparison_validity",
]

# 11 colonne rimosse da RUN_METADATA_COLUMNS (erano accodate a riga 404-416)
# Stessi nomi delle colonne CSV corrispondenti per quantizzazione, batch, termico.
ISO_RUN_METADATA_COLUMNS: List[str] = [
    # ISO 50006: variabili rilevanti strutturate nel run metadata.
    "model_quantization",
    "model_precision",
    "model_context_length",
    "model_backend_version",
    "model_parameters_b",
    "inference_batch_size",
    "concurrent_requests",
    # Stato termico: temperatura e throttling come covariate dichiarate.
    "cpu_temperature_c",
    "gpu_temperature_c",
    "thermal_throttle_detected",
    "thermal_throttle_source",
]
