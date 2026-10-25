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
    # tracciabilita' sorgente test (Modalita' di Input Universale)
    "test_source", "ground_truth", "eval_mode", "eval_method",
    "semantic_similarity", "lexical_similarity", "semantic_threshold",
    # risposta generata dal modello (verifica manuale errori/allucinazioni)
    "model_response",
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
    # --- colonne aggiunte (release successive: accodate, header migrato) ---
    # B3: provenienza P_idle salvata per riga; B1: origine lettura finestra
    "idle_provenance", "package_window_source",
    # A2/A3: GPU diagnostica e iGPU informativa (mai sommata)
    "gpu_process_energy_j", "igpu_energy_j",
    # B2: energia REALE della sottofinestra del LLM Judge (scorporata)
    "judge_energy_j", "judge_window_s",
    # B4: range EcoLogits (il valore principale e' la media, dichiarata)
    "cloud_energy_min_j", "cloud_energy_max_j",
    # C1/C2: metriche derivate separate e tracciabilita' pesi acc_comp
    "acc_comp_components", "acc_comp_weights",
    # Punto 2: provenienza dell'idle GPU usato nello scorporo (calibrated|missing)
    "gpu_idle_provenance",
    # Diagnostica cpu-time-share (per riga: perche' share=0?). La quota e'
    # d_ollama/d_busy, cioe' sul tempo BUSY di sistema (non-idle), NON sulla
    # capacita' N_eff*dt: la baseline e' gia' sottratta, e una quota sulla
    # capacita' toglierebbe l'idle due volte. ollama_active_energy_j e' una
    # STIMA di attribuzione, non una misura per processo: il contatore conosce
    # il dominio (PKG), non il processo.
    "ollama_pids_used", "d_ollama_cpu_s", "d_busy_s", "n_samples_in_window",
    # answer_type e extracted_answer (valutazione accuratezza)
    "answer_type", "extracted_answer",
    # D1: lo stato del motore locale e' un parametro del run, non un incidente.
    # keep_alive NON era mai inviato: il default di Ollama decideva se i pesi
    # restavano caricati fra una richiesta e la successiva, e nel CSV di
    # produzione due righe su nove hanno un residuo di 6,0-6,6 s (caricamento)
    # contro 0,03-1,87 s delle altre. Qui finisce il valore REALMENTE inviato.
    "keep_alive_sent",
    # alt_lhm.DOCX (24/10), recepito: il canale che ha prodotto package_energy_j
    # va nella riga, non solo nel file di run metadata. I CSV di risultato
    # accumulano righe di run diversi (emi-counter / power-integration / rapl /
    # unavailable) e il metodo storico era leggibile solo dentro le stringhe
    # composite cpu_attribution_method e measurement_boundary. Qui c'e' il solo
    # token del canale package CPU; per le righe cloud e' il canale del CLIENT
    # locale (il server non e' misurato qui: vedere cloud_energy_method).
    "energy_calculation_method",
    # alt_lhm.DOCX (24/10), contratto §3: la riga porta anche i valori GREZZI
    # del contatore agli estremi di finestra, l'unita' nativa, il dominio, la
    # cadenza REALMENTE osservata (non quella richiesta) e la versione del
    # percorso di lettura. Senza questi campi package_energy_j e' un numero
    # che richiede di fidarsi del buffer; con questi e' revisionabile.
    # Accodate in coda: i CSV storici si migrano con ensure_header.
    "raw_start", "raw_end", "raw_unit", "domain",
    "sampling_interval_observed_s", "backend_version",
    # rev_metodo.DOCX §2(b): il denominatore dello share va dichiarato. La
    # quota e' d_ollama/d_busy, ma va detto su quale intervallo e con quale
    # capacita': d_busy_s <= core x finestra e' verificabile a posteriori.
    "cpu_share_window_s", "cpu_busy_capacity_cores",
    # P2: la riga dichiara la grandezza GREZZA, con segno, e se la sottrazione
    # della baseline ha senso. package_energy_j e active_energy_j restano
    # troncati a zero per compatibilita': senza queste tre colonne un troncamento
    # e' indistinguibile da uno zero misurato.
    "package_energy_raw_j", "active_energy_raw_j", "active_valid",
    # P3: lo share grezzo (senza clamp) e il token dell'anomalia. Con
    # cpu_time_share=1 e questi due campi vuoti la quota e' 1 per misura; con
    # share_anomaly valorizzata il clamp ha nascosto un'incoerenza.
    "cpu_time_share_raw", "share_anomaly",
]


def ensure_header(path: Path) -> None:
    """Crea il file con header se assente o con header non valido.

    Se il file esiste gia' con uno schema *valido* ma privo delle colonne
    aggiunte nelle release successive (es. 'model_response'), le colonne
    mancanti vengono inserite nell'header alla loro posizione canonica e
    tutte le righe esistenti vengono ri-normalizzate allo schema corrente
    (celle vuote per i campi nuovi): niente perdita di dati, niente righe
    disallineate.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
            first = rows[0] if rows else None
            if first == CSV_COLUMNS:
                return
            # header esistente che contiene TUTTE le colonne richieste in
            # ordine? allora è valido: nessuna riscrittura necessaria
            if first and len(first) >= len(CSV_COLUMNS) and \
                    all(first[i] == col for i, col in enumerate(CSV_COLUMNS)):
                return
            # migrazione: riaccoda le colonne nuove nello schema canonico
            if first and any(c in CSV_COLUMNS for c in first):
                merged_cols = list(CSV_COLUMNS) + [c for c in first if c not in CSV_COLUMNS]
                migrated = [merged_cols]
                for r in rows[1:]:
                    lookup = dict(zip(first, r))
                    migrated.append([lookup.get(c, "") for c in merged_cols])
                with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerows(migrated)
                return
        except Exception:
            pass
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerow(CSV_COLUMNS)


def export_results_csv(records: List[Dict], path: Path, mode: str = "a") -> int:
    """Accoda (mode='a') o sovrascrive (mode='w') i record nel CSV.
    Ritorna il numero di righe scritte."""
    path = Path(path)
    ensure_header(path)
    written = 0
    open_mode = "a" if mode == "a" else "w"
    with open(path, open_mode, newline="", encoding="utf-8-sig") as fh:
        if open_mode == "w":
            # riscrive header + record (sovrascrittura completa)
            import csv as _csv
            _csv.writer(fh).writerow(CSV_COLUMNS)
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
    "num_prompts", "test_source_mode", "test_source_csv",
    "test_source_items_total", "test_ground_truth_count",
    "temperature", "timeout_s",
    "idle_power_w", "idle_calibrated_at",
    "ecologits_version", "electricity_maps_used",
    "records_written", "results_csv", "notes",
    # D1: accodata per non disallineare i file di run metadata gia' scritti
    # (nessuna migrazione per questo CSV: l'header e' scritto una volta sola).
    "ollama_keep_alive",
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
