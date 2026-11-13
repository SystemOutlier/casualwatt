"""Per-category ECPC with cluster-bootstrap confidence intervals.

This module computes Energy Per Correct answer (ECPC) stratified by query
category/taxonomy, with cluster-bootstrap confidence intervals at the task level
to account for non-independence of repeated measurements on the same task.
"""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from evaluation_runner import (
    BOOTSTRAP_SEED,
    BOOTSTRAP_RESAMPLES,
    record_verdict,
    record_task_id,
    _percentile,
    _finite_energy,
    _task_id,
    _eligible_energy_value,
)


def _eligible_energy(row: Mapping[str, Any], energy_key: str) -> Optional[float]:
    """Energia eleggibile per il numeratore di ECPC, con la regola condivisa.

    Delega a ``evaluation_runner._eligible_energy_value`` cosi' il totale per
    categoria, il totale complessivo e il bootstrap usano la stessa regola
    (inclusa l'esclusione delle finestre counter-invalid/unavailable, che la
    nota di questo modulo dichiarava ma il codice precedente non applicava).
    """
    return _eligible_energy_value(row, energy_key)


def _ecpc_bootstrap(
    pairs: list[tuple[int, float, str]],  # (verdict 1/0, energy, task_id)
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Bootstrap di ECPC = ΣE/Σ1[correct] ricampionando i TASK.

    `pairs` sono TUTTE le righe eleggibili (non le sole corrette): il numeratore
    di ogni ricampiono e' l'energia di tutte le righe estratte, il denominatore
    la somma degli indicatori di correttezza, cosi' il rapporto ricampionato e'
    lo stesso estimando del punto stimato. I ricampioni a denominatore nullo
    (nessuna corretta estratta) sono CONTEGGIATI in ``n_zero_denominator``, non
    scartati in silenzio: il conteggio dice quanto e' fragile il denominatore.
    Un'identita' di task parziale e' rifiutata, come per il bootstrap di
    accuratezza: togliere le righe senza id cambierebbe la popolazione.
    """
    clusters: dict[str, list[tuple[int, float]]] = defaultdict(list)
    senza_id = 0
    for verdict, energy, task_id in pairs:
        tid = _task_id(task_id)
        if tid is None:
            senza_id += 1
            continue
        clusters[tid].append((verdict, energy))

    base = {"n_effective_tasks": len(clusters), "n_rows": len(pairs),
            "n_rows_without_task": senza_id, "resamples": resamples, "seed": seed}

    if not clusters:
        return {**base, "interval": None, "n_zero_denominator": 0,
                "reason": "no task identity recorded"}
    if senza_id:
        return {**base, "interval": None, "n_zero_denominator": 0,
                "reason": f"task identity missing for {senza_id} row(s): "
                          "partial cluster bootstrap would change the estimand"}
    if len(clusters) < 2:
        return {**base, "interval": None, "n_zero_denominator": 0,
                "reason": "one distinct task: zero-width interval would be manufactured certainty"}

    task_ids = sorted(clusters, key=repr)
    cluster_data = [clusters[tid] for tid in task_ids]

    rng = random.Random(seed)
    ratios: list[float] = []
    n_zero = 0

    for _ in range(resamples):
        resample = [cluster_data[rng.randrange(len(cluster_data))] for _ in cluster_data]
        total_energy = sum(e for c in resample for _, e in c)
        total_correct = sum(v for c in resample for v, _ in c)
        if total_correct > 0:
            ratios.append(total_energy / total_correct)
        else:
            n_zero += 1

    if len(ratios) < 2:
        return {**base, "interval": None, "n_zero_denominator": n_zero,
                "reason": "bootstrap degenerate: insufficient valid resamples"}

    ratios.sort()
    lo = _percentile(ratios, 0.025)
    hi = _percentile(ratios, 0.975)
    return {
        **base,
        "interval": [round(lo, 6), round(hi, 6)],
        "reason": "",
        "n_zero_denominator": n_zero,
    }


def compute_taxonomy_ecpc(
    records: Iterable[Mapping[str, Any]],
    category_key: str = "category",
    energy_key: str = "end_to_end_energy_j",
) -> dict[str, Any]:
    """Compute ECPC stratified by category with cluster-bootstrap CIs.

    Returns a dict with:
    - "overall": aggregate across all categories
    - "by_category": dict mapping category -> {ecpc, ci, n_tasks, n_rows, ...}
    - "notes": methodological declarations
    """
    rows = list(records)
    cat_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        cat = str(row.get(category_key, "unknown")).strip()
        cat_rows[cat].append(row)

    results = {}
    all_pairs = []  # for overall bootstrap

    for cat, cat_rows_list in cat_rows.items():
        # Determinate rows
        determinate = [r for r in cat_rows_list if record_verdict(r) in ("correct", "incorrect")]
        correct_rows = [r for r in determinate if record_verdict(r) == "correct"]
        n_correct = len(correct_rows)
        
        # ECPC formal definition: sum of energy of ALL rows (including failures, indeterminate) / correct count
        # Energy eligibility: finite, non-negative, valid flags, verified
        cat_total_energy = 0.0
        cat_eligible_count = 0
        for row in cat_rows_list:
            energy = _eligible_energy(row, energy_key)
            if energy is not None:
                cat_total_energy += energy
                cat_eligible_count += 1
        
        cat_total_energy = cat_total_energy if cat_eligible_count > 0 else None
        ecpc = cat_total_energy / n_correct if n_correct and cat_total_energy is not None else None
        
        # Pairs per il bootstrap: TUTTE le righe eleggibili con indicatore 1/0,
        # non le sole corrette, per ricampionare lo stesso estimando del punto
        # stimato. Il conteggio delle corrette con energia resta separato.
        pairs = []
        n_correct_with_eligible = 0
        for row in cat_rows_list:
            energy = _eligible_energy(row, energy_key)
            if energy is None:
                continue
            is_correct_row = record_verdict(row) == "correct"
            n_correct_with_eligible += int(is_correct_row)
            pairs.append((1 if is_correct_row else 0, energy, record_task_id(row)))

        # Cluster bootstrap for this category
        bootstrap = _ecpc_bootstrap(pairs)

        # Accuracy on determinate
        n_determinate = len(determinate)
        accuracy = n_correct / n_determinate if n_determinate else None

        results[cat] = {
            "n_total": len(cat_rows_list),
            "n_determinate": n_determinate,
            "n_correct": n_correct,
            "n_correct_with_eligible_energy": n_correct_with_eligible,
            "total_energy_j": round(cat_total_energy, 6) if cat_total_energy is not None else None,
            "eligible_energy_rows": cat_eligible_count,
            "ecpc_j": round(ecpc, 6) if ecpc is not None else None,
            "ecpc_cluster_bootstrap_95": bootstrap["interval"],
            "ecpc_bootstrap_note": (f"cluster bootstrap: n_effective_tasks={bootstrap['n_effective_tasks']}, "
                                     f"n_rows={bootstrap['n_rows']}, resamples={bootstrap['resamples']}, "
                                     f"seed={bootstrap['seed']}, "
                                     f"n_zero_denominator={bootstrap['n_zero_denominator']}"
                                     if bootstrap["interval"] is not None
                                     else f"not computable: {bootstrap['reason']}"),
            "accuracy_on_determinate": round(accuracy, 6) if accuracy is not None else None,
        }

        # Accumulate for overall
        all_pairs.extend(pairs)

    # Overall bootstrap
    overall_bootstrap = _ecpc_bootstrap(all_pairs)
    # Il denominatore dell'overall e' TUTTE le corrette (definizione formale di
    # ECPC), come per categoria: una corretta senza energia eleggibile resta
    # un'unita' al denominatore. Il conteggio con energia e' pubblicato a parte.
    overall_correct = sum(r["n_correct"] for r in results.values())
    overall_correct_with_energy = sum(r["n_correct_with_eligible_energy"] for r in results.values())
    overall_energy = sum(r["total_energy_j"] for r in results.values() if r["total_energy_j"] is not None)
    overall_ecpc = overall_energy / overall_correct if overall_correct and overall_energy is not None else None

    return {
        "overall": {
            "n_categories": len(results),
            "n_total": len(rows),
            "n_correct": overall_correct,
            "n_correct_with_eligible_energy": overall_correct_with_energy,
            "total_energy_j": round(overall_energy, 6) if overall_energy is not None else None,
            "ecpc_j": round(overall_ecpc, 6) if overall_ecpc is not None else None,
            "ecpc_cluster_bootstrap_95": overall_bootstrap["interval"],
            "ecpc_bootstrap_note": (f"cluster bootstrap: n_effective_tasks={overall_bootstrap['n_effective_tasks']}, "
                                     f"n_rows={overall_bootstrap['n_rows']}, resamples={overall_bootstrap['resamples']}, "
                                     f"seed={overall_bootstrap['seed']}, "
                                     f"n_zero_denominator={overall_bootstrap['n_zero_denominator']}"
                                     if overall_bootstrap["interval"] is not None
                                     else f"not computable: {overall_bootstrap['reason']}"),
        },
        "by_category": results,
        "notes": (
            "ECPC = sum of eligible energy over ALL rows (including failures and indeterminate) "
            "/ count of ALL correct answers, including those without eligible energy. "
            "Energy eligibility requires: finite, non-negative, no invalidating flag, "
            "active_valid=true for unified rows (generic energy_j without flags is accepted "
            "for compatibility only), and package_window_source not in {counter-invalid, unavailable}. "
            "Cluster bootstrap resamples TASKS (not rows) with replacement, computes the FULL ratio "
            "sum(energy)/sum(correct indicator) per resample over all eligible rows, counts "
            "zero-denominator resamples (n_zero_denominator), refuses partial task identity, "
            "and reports the 2.5-97.5 percentile interval. Wilson interval is for the accuracy "
            "proportion, not for the ECPC ratio. A wider cluster interval indicates task-level "
            "dependence. Seed is fixed (20261104) for reproducibility."
        ),
    }


def export_taxonomy_ecpc_csv(
    taxonomy_result: dict[str, Any],
    path: str | Path,
) -> None:
    """Export category-level ECPC results to CSV."""
    path = Path(path)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "category", "n_total", "n_determinate", "n_correct",
            "n_correct_with_eligible_energy", "total_energy_j", "eligible_energy_rows", "ecpc_j",
            "ecpc_ci_lower", "ecpc_ci_upper", "accuracy_on_determinate",
            "bootstrap_note"
        ])
        for cat, data in taxonomy_result["by_category"].items():
            ci = data["ecpc_cluster_bootstrap_95"]
            writer.writerow([
                cat,
                data["n_total"],
                data["n_determinate"],
                data["n_correct"],
                data["n_correct_with_eligible_energy"],
                data["total_energy_j"] if data["total_energy_j"] is not None else "",
                data["eligible_energy_rows"] if data["eligible_energy_rows"] is not None else "",
                data["ecpc_j"] if data["ecpc_j"] is not None else "",
                ci[0] if ci else "",
                ci[1] if ci else "",
                data["accuracy_on_determinate"] if data["accuracy_on_determinate"] is not None else "",
                data["ecpc_bootstrap_note"],
            ])
        # Overall row
        overall = taxonomy_result["overall"]
        ci = overall["ecpc_cluster_bootstrap_95"]
        writer.writerow([
            "OVERALL",
            overall["n_total"],
            "",  # n_determinate N/A for overall
            "",  # n_correct N/A
            overall["n_correct_with_eligible_energy"],
            overall["total_energy_j"] if overall["total_energy_j"] is not None else "",
            "",  # eligible_energy_rows N/A for overall
            overall["ecpc_j"] if overall["ecpc_j"] is not None else "",
            ci[0] if ci else "",
            ci[1] if ci else "",
            "",
            overall["ecpc_bootstrap_note"],
        ])


def export_taxonomy_ecpc_json(
    taxonomy_result: dict[str, Any],
    path: str | Path,
) -> None:
    """Export full taxonomy ECPC result to JSON."""
    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(taxonomy_result, f, ensure_ascii=False, indent=2, sort_keys=True)