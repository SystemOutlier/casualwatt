# -*- coding: utf-8 -*-
"""
tests/test_csv_schema_p5.py — Lo schema P5: colonne in coda, migrazione, riepiloghi.

Perche' esiste. Le righe v4 portano campi che prima non esistevano (bordo di
misura, validita' della quota, baseline di blocco, provenienza del giudice).
Se una colonna manca dallo schema, ``export_results_csv`` la scarta in
silenzio (``extrasaction="ignore"``): il run sembrerebbe riuscito e il campo
sarebbe perso. Se l'ordine cambia, i CSV storici si disallineano. Questo test
blocca entrambe le cose e verifica che la migrazione dell'header non inventi
un livello dei token per le righe vecchie.

Che cosa verifica:
  1. le 39 colonne P5 -- piu' le 3 di Emenda 8 e le 6 del delta cloud C5 in
     coda, per 48 -- sono in coda, una sola volta, nell'ordine dichiarato,
     subito dopo ``cpu_time_resolution_s``;
  2. un CSV vecchio con tre sole colonne viene migrato all'header corrente
     senza perdere i valori (il join e' per nome, non per posizione);
  3. le righe migrate hanno ``tokens_level`` VUOTO: "livello non dichiarato",
     non "per richiesta" per default;
  4. ``block_summary.csv`` ha lo schema congelato e le celle non calcolate
     restano vuote; ``point_summary.csv`` espone i campi congelati del punto;
  5. una riga v4 esportata porta i valori nuovi nelle colonne giuste.

Che cosa NON verifica: che i valori siano corretti (li verificano i test dei
bordi e della baseline) ne' la validazione pandas (``validate_csv``).
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from casualwatt_csv_export import (  # noqa: E402
    BLOCK_SUMMARY_COLUMNS,
    CSV_COLUMNS,
    POINT_SUMMARY_COLUMNS,
    ensure_header,
    export_results_csv,
    export_summary_csv,
)

TAIL = [
    "engine_tree_changed", "tree_identity_start", "tree_identity_end",
    "tree_born", "tree_lost",
    "cpu_share_source", "cpu_time_share_valid",
    "edge_start_utc", "edge_end_utc", "edge_time_source", "edge_spread_s",
    "dt_W_s", "emi_ts_start_100ns", "emi_ts_end_100ns", "emi_edge_source",
    "baseline_pre_w", "baseline_post_w", "pre_windows_w", "post_windows_w",
    "pre_range_w", "dP", "half_range_pre_w", "half_drift_w",
    "budget_base_w", "budget_base_j", "settle_pre_s", "settle_post_s",
    "block_id", "point_id", "batch_id",
    "tokens_level", "n_inferenze",
    "judge_energy_edge_source", "judge_energy_interp_j",
    "judge_edge_start_utc", "judge_edge_end_utc", "judge_edge_spread_s",
    "judge_emi_ts_start_100ns", "judge_emi_ts_end_100ns",
    # Emenda 8 (P1.6): tracciabilita' della sostituzione, accodate in coda.
    "block_attempt", "invalid_reason", "replaced_block_id",
    # Delta cloud (spec C5 §4, 26-10-2026): banda della stima e i termini che
    # l'hanno prodotta. In coda, dopo le colonne di Emenda 8.
    "cloud_input_tokens_included", "cloud_pue_applied", "cloud_pue_source",
    "cloud_latency_used_s", "cloud_latency_threshold_s", "cloud_latency_binding",
    # Metriche per token (emendazione a P5, 28-10-2026): in coda, dopo il
    # blocco cloud, cosi' nessuna colonna storica cambia posizione.
    "energy_per_total_token_j", "tokens_per_joule", "kwh_per_million_tokens",
]


# ------------------------------------------------------------------ 1
def test_colonne_p5_in_coda_nell_ordine_dichiarato():
    """Nessun riordino: le nuove colonne stanno dopo quelle storiche, in coda."""
    assert CSV_COLUMNS[-len(TAIL):] == TAIL
    assert CSV_COLUMNS[-(len(TAIL) + 1)] == "cpu_time_resolution_s"
    for col in TAIL:
        assert CSV_COLUMNS.count(col) == 1, f"colonna duplicata: {col}"


# ------------------------------------------------------------------ 2, 3
def test_migrazione_di_un_csv_vecchio_senza_disallineare_le_righe(tmp_path):
    """Un CSV di tre colonne diventa lo schema corrente; i valori restano per nome."""
    p = tmp_path / "vecchio.csv"
    p.write_text(
        "run_id,package_energy_j,cpu_time_share\nr1,12.5,0.75\n",
        encoding="utf-8-sig")

    ensure_header(p)

    with open(p, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 2
    row = dict(zip(rows[0], rows[1]))
    assert row["run_id"] == "r1"
    assert row["package_energy_j"] == "12.5"
    assert row["cpu_time_share"] == "0.75"
    # 3) livello non dichiarato, non "per richiesta"
    assert row["tokens_level"] == ""
    assert row["n_inferenze"] == ""
    assert row["baseline_pre_w"] == ""


# ------------------------------------------------------------------ 4
def test_riepiloghi_con_schema_congelato_e_celle_vuote(tmp_path):
    """block/point summary: nomi congelati e "non calcolato" = cella vuota."""
    for col in ("pre_range_w", "dP", "budget_base_j", "r_A", "r_B",
                "cooldown_timeout", "negative_increment"):
        assert col in BLOCK_SUMMARY_COLUMNS
    for col in ("err_rel", "intervallo_conf", "coverage_tier",
                "hull_margin_tok", "chain_status"):
        assert col in POINT_SUMMARY_COLUMNS

    p = tmp_path / "block_summary.csv"
    rec = {"batch_id": "b1", "point_id": "p1", "block_id": "b1__p1__b01",
           "block_kind": "campaign", "baseline_pre_w": 10.0,
           "budget_base_w": 0.3, "negative_increment": "false"}
    assert export_summary_csv([rec], p, BLOCK_SUMMARY_COLUMNS, mode="a") == 1
    with open(p, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == BLOCK_SUMMARY_COLUMNS
    assert rows[0]["budget_base_w"] == "0.3"
    # i campi che l'analisi non ha ancora calcolato sono vuoti, non zero
    assert rows[0]["u_edge_j"] == ""
    assert rows[0]["r_A"] == ""


# ------------------------------------------------------------------ 5
def test_una_riga_v4_porta_i_valori_nuovi_nelle_colonne_giuste(tmp_path):
    """Export di una riga v4: i campi P5 arrivano nel CSV, non vengono scartati."""
    p = tmp_path / "righe.csv"
    export_results_csv([{
        "run_id": "r1", "tokens_level": "per-request", "n_inferenze": 1,
        "engine_tree_changed": False, "cpu_time_share_valid": True,
        "cpu_share_source": "direct-edge", "dt_W_s": 3.5,
        "emi_edge_source": "direct-ioctl", "baseline_pre_w": 11.2,
        "budget_base_j": 0.42, "block_id": "b__p__b01",
        "point_id": "b__p", "batch_id": "b",
        "judge_energy_edge_source": "direct-ioctl",
        "judge_energy_interp_j": 0.8,
    }], p, mode="w")

    with open(p, newline="", encoding="utf-8-sig") as fh:
        row = next(csv.DictReader(fh))
    assert row["tokens_level"] == "per-request"
    assert row["n_inferenze"] == "1"
    assert row["cpu_share_source"] == "direct-edge"
    assert row["dt_W_s"] == "3.5"
    assert row["baseline_pre_w"] == "11.2"
    assert row["block_id"] == "b__p__b01"
    assert row["judge_energy_interp_j"] == "0.8"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
