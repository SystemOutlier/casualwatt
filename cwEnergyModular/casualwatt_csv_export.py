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
    # P5: integrita' del numeratore e quantizzazione. worker_exit_in_window
    # dice che un processo presente a t_start non era piu' leggibile a t_end
    # (tempo CPU perso); cpu_time_resolution_s e' il tick OSSERVATO dei
    # cpu_times, contro cui la finestra va confrontata.
    "worker_exit_in_window", "cpu_time_resolution_s",
    # ---- P5 (#42): lotto 1, scritto dal runner v4 ------------------------
    # engine_tree_changed e' il flag del protocollo che invalida la quota;
    # worker_exit_in_window resta il nome storico dello STESSO insieme (D4:
    # non sono due prove indipendenti). Le identita' rendono l'insieme
    # confrontabile a posteriori, non solo il booleano.
    "engine_tree_changed", "tree_identity_start", "tree_identity_end",
    "tree_born", "tree_lost",
    # Provenienza della quota e validita' dichiarata. cpu_time_share=0 con
    # valid=0 e' "non calcolata", non "nessuna CPU usata"; source dice perche'.
    "cpu_share_source", "cpu_time_share_valid",
    # Bordo di misura: istanti UTC, base di dt_W, spread delle letture e
    # timestamps 100 ns del driver EMI ai due estremi. Con emi_edge_source
    # l'energia della riga e' revisionabile senza il file di run.
    "edge_start_utc", "edge_end_utc", "edge_time_source", "edge_spread_s",
    "dt_W_s", "emi_ts_start_100ns", "emi_ts_end_100ns", "emi_edge_source",
    # P1.5/P1.14: baseline pre (applicata) e post (diagnostica, mai
    # sottratta), le tre repliche di ciascuna e i derivati del budget base.
    "baseline_pre_w", "baseline_post_w", "pre_windows_w", "post_windows_w",
    "pre_range_w", "dP", "half_range_pre_w", "half_drift_w",
    "budget_base_w", "budget_base_j", "settle_pre_s", "settle_post_s",
    # Chiavi stabili di collegamento fra righe grezze e riepiloghi derivati
    # (block_summary.csv / point_summary.csv): il join non usa l'ordine.
    "block_id", "point_id", "batch_id",
    # Livello dei token dichiarato per riga: 'per-request' in v4; vuoto =
    # non dichiarato (righe storiche), non "per richiesta" per default.
    "tokens_level", "n_inferenze",
    # D2: provenienza dei bordi del segmento del LLM Judge. judge_energy_j e
    # judge_window_s esistono gia'; qui si aggiunge COME e' stata letta la
    # sua energia e l'interpolazione resta un numero verificabile accanto
    # alla lettura diretta, non un valore implicito.
    "judge_energy_edge_source", "judge_energy_interp_j",
    "judge_edge_start_utc", "judge_edge_end_utc", "judge_edge_spread_s",
    "judge_emi_ts_start_100ns", "judge_emi_ts_end_100ns",
    # Emenda 8 (P1.6): tracciabilita' della sostituzione di un blocco invalidato
    # per guasto TECNICO del contatore. block_attempt = "1" piano, "2" sostituto;
    # invalid_reason = token del guasto ("delta_negativo" | "lettura_non_finita"
    # | "replica_non_positiva"), VUOTA se il blocco e' valido; replaced_block_id
    # = id del blocco invalidato che questo sostituto rimpiazza, vuota altrove.
    # Attenzione al nome: invalid_reason (di blocco) non e' invalid_reasons
    # (di richiesta, P2.5, oggi nelle note). Accodate in coda: niente rinomine,
    # niente riordini (D4), migrazione per nome via ensure_header.
    "block_attempt", "invalid_reason", "replaced_block_id",
    # P5 / spec C5 §4 (26-10-2026): i sei campi che dicono COME e' stato prodotto
    # il numero cloud, non solo quanto vale. `cloud_input_tokens_included`:
    # False per EcoLogits (llm_impacts accetta solo i token di output), True per
    # l'analitico C5. `cloud_pue_applied` / `cloud_pue_source`: PUE del catalogo
    # provider EcoLogits, oppure assunzione hyperscale dichiarata.
    # `cloud_latency_used_s` / `_threshold_s`: la latenza entrata nel calcolo e la
    # soglia del termine server min(request, n_out/tps+ttft); soglia vuota = non
    # determinabile dalla scheda. `cloud_latency_binding`: True = ha vincolato la
    # soglia del server (latenza misurata troncata, rete e coda fuori), False =
    # ha vincolato la latenza misurata. Accodate in coda: niente riordini.
    "cloud_input_tokens_included", "cloud_pue_applied", "cloud_pue_source",
    "cloud_latency_used_s", "cloud_latency_threshold_s", "cloud_latency_binding",
]


# ---- P5 (#42), lotto 2: riepiloghi derivati, non righe di richiesta ------
# Congelati per nome e collocazione nella proposta P5 (p5_proposta:360-368).
# I campi di misura del blocco sono scritti dal runner v4; quelli di analisi
# (r_A, r_B, u_edge_j, ...) restano celle vuote finche' l'analisi non li
# calcola: vuoto = non ancora calcolato, mai zero inventato.
BLOCK_SUMMARY_COLUMNS: List[str] = [
    "batch_id", "point_id", "block_id", "block_kind", "pair_id",
    "order_seed", "dt_nominal_s", "dt_tick_s", "p_peak_w",
    "settle_pre_s", "settle_post_s",
    "baseline_pre_w", "baseline_post_w", "pre_windows_w", "post_windows_w",
    "pre_range_w", "dP", "half_range_pre_w", "half_drift_w",
    "budget_base_w", "budget_base_j",
    "u_edge_j", "budget_fit_j", "budget_pred_j", "u_bias_j", "bias_w",
    "z_resid", "cooldown_timeout", "negative_increment",
    "design_deviation", "design_deviation_count", "r_A", "r_B",
    # Emenda 8 (P1.6): le tre colonne in coda, stesso ordine delle righe grezze.
    # Il riepilogo di un blocco invalidato esiste: porta le chiavi d'identita',
    # block_attempt, invalid_reason e replaced_block_id, e le celle di misura
    # Vuote ("non calcolata"), non zero.
    "block_attempt", "invalid_reason", "replaced_block_id",
]

POINT_SUMMARY_COLUMNS: List[str] = [
    "batch_id", "point_id",
    "err_rel", "intervallo_conf", "pred_nonpositive",
    "coverage_tier", "coverage_tier_design", "coverage_tier_fit",
    "hull_margin_tok", "hull_margin_design_tok", "sparse_support",
    "thin_support", "out_of_coverage", "bootstrap_seed",
    "validation_bias_pass", "control_unstable", "chain_status",
    "share_E0", "delta_sens",
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
    _ensure_header_columns(Path(path), CSV_COLUMNS)


def _ensure_header_columns(path: Path, columns: List[str]) -> None:
    """``ensure_header`` per uno schema esplicito (righe o riepilogo)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
            first = rows[0] if rows else None
            if first == columns:
                return
            # header esistente che contiene TUTTE le colonne richieste in
            # ordine? allora è valido: nessuna riscrittura necessaria
            if first and len(first) >= len(columns) and \
                    all(first[i] == col for i, col in enumerate(columns)):
                return
            # migrazione: riaccoda le colonne nuove nello schema canonico
            if first and any(c in columns for c in first):
                merged_cols = list(columns) + [c for c in first if c not in columns]
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
        csv.writer(fh).writerow(columns)


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


def export_summary_csv(records: List[Dict], path: Path, columns: List[str],
                       mode: str = "a") -> int:
    """Accoda uno dei riepiloghi derivati (block/point) con schema esplicito.

    I riepiloghi stanno in file separati dalle righe grezze (D3): le righe
    grezze restano append-only nel CSV dei risultati, i riepiloghi si
    collegano per ``batch_id``/``point_id``/``block_id``. Le colonne vuote
    dichiarano "non calcolato", non zero.
    """
    path = Path(path)
    _ensure_header_columns(path, columns)
    written = 0
    open_mode = "a" if mode == "a" else "w"
    with open(path, open_mode, newline="", encoding="utf-8-sig") as fh:
        if open_mode == "w":
            csv.writer(fh).writerow(columns)
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in columns})
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
