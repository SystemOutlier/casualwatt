# -*- coding: utf-8 -*-
"""
casualwatt_csv_export.py — Export CSV dei record di benchmark (sezione 11).

Colonne ESATTAMENTE nell'ordine della specifica. Scrittura append-safe: se il
file esiste gia' con header valido, le nuove righe vengono accodate senza
duplicare l'intestazione; in caso di header assente/corrotto viene ricreato.
Usa pandas per la validazione dello schema.
"""
from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Dict, List

CSV_COLUMNS: List[str] = [
    # identita'
    "run_id", "session_id", "timestamp_start", "timestamp_end",
    "model_name", "model_label", "provider", "mode", "ollama_pid",
    "prompt_id", "prompt",
    # performance
    "duration_s", "input_tokens", "output_tokens", "total_tokens",
    "tokens_per_second", "prefill_duration_s", "decoding_duration_s",
    "decoding_tokens_per_second",
    # energia locale CPU
    "package_energy_j", "idle_power_w", "baseline_energy_j",
    "active_energy_j", "ollama_active_energy_j", "cpu_time_share",
    # energia GPU
    "gpu_available", "gpu_device_index", "gpu_board_energy_j",
    "gpu_energy_attributed_j", "gpu_utilization_share",
    # aggregati energetici
    "local_energy_j", "network_energy_j", "cloud_energy_j",
    "end_to_end_energy_j",
    "energy_per_output_token_j", "energy_per_correct_answer_j",
    "ece_per_joule", "epcl_j_per_link",
    # rete
    "network_upload_bytes", "network_download_bytes", "network_total_bytes",
    "network_energy_coefficient_j_per_bit", "network_measurement_boundary",
    # cloud
    "cloud_energy_method", "cloud_provider", "cloud_model",
    "cloud_input_tokens", "cloud_output_tokens", "cloud_estimation_boundary",
    # qualita'
    "is_correct", "causal_accuracy", "explanation_quality",
    "cosine_similarity", "n_correct_links", "acc_comp", "tool_calls",
    "pyagrum_calls", "llm_calls", "retry_count",
    # carbonio locale
    "local_energy_kwh", "local_carbon_intensity_gco2eq_kwh",
    "local_carbon_intensity_zone", "local_carbon_intensity_source",
    "local_carbon_intensity_timestamp", "local_emissions_gco2eq",
    "local_emissions_method",
    # carbonio cloud
    "cloud_energy_kwh", "cloud_carbon_intensity_gco2eq_kwh",
    "cloud_carbon_intensity_zone", "cloud_carbon_intensity_source",
    "cloud_carbon_intensity_timestamp", "cloud_emissions_gco2eq",
    "cloud_emissions_method",
    # metadodi metodologici
    "cpu_attribution_method", "gpu_attribution_method", "measurement_boundary",
    "energibridge_csv", "notes",
]


def ensure_header(path: Path) -> None:
    """Crea il file con header se assente o con header non valido."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as fh:
                first = next(csv.reader(fh), None)
            if first == CSV_COLUMNS:
                return
        except Exception:
            pass
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerow(CSV_COLUMNS)


def export_results_csv(records: List[Dict], path: Path) -> int:
    """Accoda i record al CSV. Ritorna il numero di righe scritte."""
    path = Path(path)
    ensure_header(path)
    written = 0
    with open(path, "a", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        for rec in records:
            row = {k: rec.get(k, "") for k in CSV_COLUMNS}
            writer.writerow(row)
            written += 1
    return written


def validate_csv(path: Path) -> bool:
    """Valida lo schema con pandas; ritorna True se il file e' leggibile/completo."""
    try:
        import pandas as pd

        df = pd.read_csv(path, encoding="utf-8-sig")
        missing = [c for c in CSV_COLUMNS if c not in df.columns]
        return not missing
    except Exception:
        return False


RUN_METADATA_COLUMNS = [
    "run_id", "started_at", "finished_at", "app_version", "python", "platform",
    "cpu_model", "cpu_logical_cores", "gpu_nvml_name", "gpu_nvml_available",
    "cpu_energy_source_method", "cpu_energy_source_notes",
    "ollama_endpoint", "ollama_models_selected", "cloud_models_selected",
    "num_prompts", "temperature", "timeout_s",
    "idle_power_w", "idle_calibrated_at",
    "ecologits_version", "electricity_maps_used",
    "records_written", "results_csv", "notes",
]


def write_run_metadata(meta: Dict, path: Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    new_row = not exists
    if new_row:
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            csv.writer(fh).writerow(RUN_METADATA_COLUMNS)
    with open(path, "a", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerow([meta.get(c, "") for c in RUN_METADATA_COLUMNS])
