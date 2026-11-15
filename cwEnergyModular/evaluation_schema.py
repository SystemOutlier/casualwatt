# -*- coding: utf-8 -*-
"""
evaluation_schema.py — Schema per i risultati di VALUTAZIONE (correttezza, factual, qualità).

Separato da casualwatt_csv_export.py (misura energetica, P5 congelato) perché:
- piano misura = energia, contatori, baseline, budget, derivati (CSV_COLUMNS 174 nomi)
- piano valutazione = pass/fail, factual accuracy, human score, LLM judge, rubrica, pass@k

I due piani si collegano per run_id / task_id / batch_id / point_id, non per colonne sovrapposte.
"""

from __future__ import annotations
from typing import List, Dict, Any
from pathlib import Path
import csv
import math
from datetime import datetime


# ---------------------------------------------------------------------------
# Schema colonne: risultati di valutazione per task (una riga per task/run)
# ---------------------------------------------------------------------------

EVALUATION_RESULT_COLUMNS: List[str] = [
    # Identità e collegamento con la misura energetica
    "run_id",                 # UUID del run (benchmark_v4.py)
    "session_id",             # sessione energetica (energy_session.py)
    "batch_id",               # batch di punti (P4)
    "point_id",               # punto nel disegno sperimentale (P4)
    "task_id",                # id stabile del task (da tasks.json)
    "task_type",              # "coding" | "factual" | "quality" | "reasoning"
    "prompt_id",              # id del prompt nel dataset (es. "c-001")
    "model_name",             # nome modello (es. "qwen2.5:0.5b")
    "model_label",            # etichetta usata nel run (es. "A", "B")
    "provider",               # "ollama" | "openai" | "hf" | "vllm" | ...

    # Input / Output
    "prompt",                 # prompt completo
    "ground_truth",           # verità di riferimento (per factual/coding)
    "model_response",         # risposta completa del modello
    "extracted_answer",       # risposta estratta per confronto (già in CSV_COLUMNS)

    # Correttezza funzionale (coding)
    "tests_total",            # numero test definiti per il task
    "tests_passed",           # test superati
    "pass_rate",              # tests_passed / tests_total
    "pass_at_1",              # 1 se passato al primo tentativo, 0 altrimenti
    "pass_at_k",              # 1 se passato entro k tentativi, 0 altrimenti
    "k_value",                # k usato per pass@k
    "pass_at_k_unbiased",     # formula unbiased: 1 - C(N-c, k)/C(N, k)
    "compile_rate",           # frazione compilazioni riuscite (se multi-tentativo)
    "runtime_success_rate",   # frazione esecuzioni senza errori

    # Correttezza fattuale (testuale)
    "factual_claims",         # numero affermazioni estratte
    "factual_correct",        # affermazioni verificate vere
    "factual_incorrect",      # affermazioni verificate false
    "factual_unverifiable",   # affermazioni non verificabili
    "factual_accuracy",       # factual_correct / factual_claims (se > 0)
    "factual_precision",      # TP / (TP + FP) su claim verificati
    "factual_recall",         # TP / (TP + FN) su claim totali
    "factual_f1",             # F1 fattuale

    # Qualità (rubrica umana / LLM judge)
    "human_score",            # score medio revisori umani (es. 1-5)
    "human_score_raw",        # JSON con score individuali per revisore
    "llm_judge_score",        # score LLM-as-judge (es. 1-5 o 0-1)
    "llm_judge_model",        # modello usato come giudice
    "rubric_scores",          # JSON: {"relevance": 4, "coherence": 5, ...}
    "rubric_schema",          # nome schema rubrica usato

    # Metriche derivate aggregazione (bootstrap, Wilson, McNemar)
    "wilson_ci_lower",        # IC Wilson 95% lower (per is_correct binario)
    "wilson_ci_upper",        # IC Wilson 95% upper
    "bootstrap_ci_lower",     # IC bootstrap cluster 2.5%
    "bootstrap_ci_upper",     # IC bootstrap cluster 97.5%
    "n_effective_tasks",      # task distinti nel cluster bootstrap
    "mcnemar_p_exact",        # p-value esatto McNemar (paired)
    "mcnemar_ci_lower",       # IC Newcombe lower per delta accuracy
    "mcnemar_ci_upper",       # IC Newcombe upper per delta accuracy
    "mcnemar_verdict",        # "significant" | "not_significant" | "indecisive"

    # Energia (collegamento a CSV_COLUMNS, non duplicazione)
    "energy_scope",           # "client" | "server_inference" | "attributed" | "cloud_estimate"
    "energy_per_task_j",      # joule per questo task (se aggregabile)
    "energy_per_token_j",     # joule per token (se token noti)
    "latency_ms",             # latenza end-to-end per questo task

    # Metadati run
    "timestamp",              # ISO 8601 UTC
    "run_mode",               # "single" | "pass_at_k" | "paired" | "bootstrap"
    "seed",                   # seed per riproducibilità
    "notes",                  # note libere (es. "sandbox: epicbox", "judge: gpt-4o")

    # Provenienza valutazione
    "eval_method",            # "auto_test" | "human_factcheck" | "llm_judge" | "robust_criterion" | "mudilab" | "paired_mcnemar"
    "eval_version",           # versione del criterio (es. "robust_v1", "mudilab_v20261102")
    "ground_truth_source",    # "dataset" | "human" | "oracle" | "synthetic"

    # ISO/IEC 5259: qualità del dataset e ground truth
    "dataset_id",
    "dataset_version",
    "dataset_sha256",
    "ground_truth_provenance",
    "label_quality_status",
    "label_reviewer",
    "label_review_date",

    # ISO/IEC 25059 / TS 25058: judge e valutazione IA
    "judge_model_version",
    "judge_prompt_version",
    "judge_temperature",
    "judge_calibration_status",
    "judge_agreement_metric",
    "judge_agreement_value",
    "judge_limitations",

    # Prova della correttezza (ISO/IEC 25059 + TS 25058)
    # Non duplica eval_method (come e' stata valutata) ne' is_correct (il verdetto).
    # Dichiara: quale prova concreta ha prodotto il verdetto, con quale regola,
    # e se il verdetto e' determinabile o indeterminato.
    "correctness_evidence_type",  # "ground-truth-match" | "semantic-threshold" | "lexical-threshold" | "deterministic-contract" | "none"
    "correctness_evidence_id",    # task_id o ID del contratto/ground truth
    "correctness_rule_version",   # "evaluator_v1" | "robust_v1"
    "correctness_threshold",      # soglia applicata (es. 0.85, absolute=1e-6)
    "correctness_determinate",    # true/false: is_correct e' 0/1 o N/A?

    # Versione e qualita' del ground truth (ISO/IEC 5259-4)
    "ground_truth_version",       # versione del ground truth usato
    "ground_truth_sha256",        # hash del ground truth per riproducibilita'
    "ground_truth_quality_status",# "unreviewed" | "reviewed" | "disputed" | "excluded"

    # Ruolo del judge (non sostituisce il verdetto primario)
    "judge_role",                 # "secondary-quality" | "not-used"
    "judge_override_allowed",     # false: il judge non sostituisce is_correct
    "judge_agrees_with_primary",  # true/false/na: il judge concorda?
    "judge_disagreement_reason",  # perche' il judge discorda (se applicabile)
    "judge_calibration_status",   # "not-calibrated" | "calibrated" | "failed"
]


# ---------------------------------------------------------------------------
# Schema: definizione task (per tasks.json versionabile)
# ---------------------------------------------------------------------------

TASK_SCHEMA_VERSION = "1.0"

TASK_DEFINITION_COLUMNS: List[str] = [
    "task_id",
    "task_type",              # "coding" | "factual" | "quality" | "reasoning"
    "description",            # descrizione human-readable
    "prompt",                 # prompt da inviare al modello
    "ground_truth",           # verità di riferimento (stringa o JSON)
    "tests",                  # JSON: lista di {"input": ..., "expected": ...} per coding
    "claims",                 # lista affermazioni da verificare (per factual)
    "rubric",                 # JSON schema rubrica (per quality)
    "metadata",               # JSON libero (difficulty, tags, source, ...)
]


# ---------------------------------------------------------------------------
# Schema: riepilogo aggregato per modello/run (una riga per modello)
# ---------------------------------------------------------------------------

EVALUATION_SUMMARY_COLUMNS: List[str] = [
    "run_id",
    "model_name",
    "model_label",
    "task_type",
    "n_tasks",
    "n_tasks_evaluated",

    # Aggregate coding
    "pass_at_1_mean",
    "pass_at_k_mean",
    "pass_at_k_unbiased_mean",
    "compile_rate_mean",
    "runtime_success_rate_mean",

    # Aggregate factual
    "factual_accuracy_mean",
    "factual_precision_mean",
    "factual_recall_mean",
    "factual_f1_mean",

    # Aggregate quality
    "human_score_mean",
    "human_score_ci_lower",
    "human_score_ci_upper",
    "llm_judge_score_mean",
    "llm_judge_agreement",    # Cohen's kappa o % accordo giudici

    # Aggregate correctness (binario is_correct)
    "accuracy_mean",
    "wilson_ci_lower",
    "wilson_ci_upper",
    "bootstrap_ci_lower",
    "bootstrap_ci_upper",
    "n_effective_tasks",

    # Energy aggregate (se disponibile)
    "energy_per_task_j_mean",
    "energy_per_task_j_median",
    "energy_per_token_j_mean",
    "latency_ms_mean",
    "latency_ms_median",

    # Paired comparison (se run paired)
    "paired_with_model",
    "mcnemar_p_exact",
    "mcnemar_ci_lower",
    "mcnemar_ci_upper",
    "mcnemar_verdict",
    "delta_accuracy",

    "timestamp",
    "notes",
]


# ---------------------------------------------------------------------------
# Helper: pass@k unbiased
# ---------------------------------------------------------------------------

def compute_pass_at_k_unbiased(n_samples: int, n_correct: int, k: int) -> float:
    """
    Formula unbiased per pass@k (Chen et al., HumanEval):
        pass@k = 1 - C(n_samples - n_correct, k) / C(n_samples, k)

    Restituisce 0.0 se n_samples < k o n_correct == 0.
    Restituisce 1.0 se n_correct >= k.
    """
    if n_samples < k or n_correct == 0:
        return 0.0
    if n_correct >= k:
        return 1.0
    # log-combinazioni per evitare overflow
    def log_comb(n: int, r: int) -> float:
        if r < 0 or r > n:
            return float('-inf')
        return math.lgamma(n + 1) - math.lgamma(r + 1) - math.lgamma(n - r + 1)

    log_num = log_comb(n_samples - n_correct, k)
    log_den = log_comb(n_samples, k)
    if log_num == float('-inf'):
        return 1.0
    return 1.0 - math.exp(log_num - log_den)


def compute_pass_at_k_from_results(results: List[Dict], k: int) -> float:
    """
    Calcola pass@k unbiased da una lista di risultati per UN task.
    Ogni result deve avere 'passed' (bool).
    """
    n_samples = len(results)
    n_correct = sum(1 for r in results if r.get("passed"))
    return compute_pass_at_k_unbiased(n_samples, n_correct, k)


# ---------------------------------------------------------------------------
# Helper: Wilson score interval per proporzione binaria
# ---------------------------------------------------------------------------

def wilson_ci(n: int, k: int, confidence: float = 0.95) -> tuple[float, float]:
    """
    Intervallo di Wilson per proporzione k/n.
    Restituisce (lower, upper).
    """
    if n == 0:
        return (0.0, 1.0)
    from scipy import stats
    z = stats.norm.ppf((1 + confidence) / 2)
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2))
    return (max(0.0, centre - half), min(1.0, centre + half))


# ---------------------------------------------------------------------------
# I/O CSV (stesso pattern di casualwatt_csv_export.py)
# ---------------------------------------------------------------------------

def ensure_eval_header(path: Path, columns: List[str] = None) -> None:
    """Crea file con header se assente o non valido."""
    cols = columns or EVALUATION_RESULT_COLUMNS
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.reader(fh))
            first = rows[0] if rows else None
            if first == cols:
                return
            if first and len(first) >= len(cols) and all(first[i] == c for i, c in enumerate(cols)):
                return
            if first and any(c in cols for c in first):
                merged = list(cols) + [c for c in first if c not in cols]
                migrated = [merged]
                for r in rows[1:]:
                    lookup = dict(zip(first, r))
                    migrated.append([lookup.get(c, "") for c in merged])
                with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                    csv.writer(fh).writerows(migrated)
                return
        except Exception:
            pass
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        csv.writer(fh).writerow(cols)


def export_evaluation_results(records: List[Dict], path: Path, mode: str = "a") -> int:
    """Accoda/sovrascrive risultati valutazione."""
    path = Path(path)
    ensure_eval_header(path)
    written = 0
    open_mode = "a" if mode == "a" else "w"
    with open(path, open_mode, newline="", encoding="utf-8-sig") as fh:
        if open_mode == "w":
            csv.writer(fh).writerow(EVALUATION_RESULT_COLUMNS)
        writer = csv.DictWriter(fh, fieldnames=EVALUATION_RESULT_COLUMNS, extrasaction="ignore")
        for rec in records:
            row = {k: rec.get(k, "") for k in EVALUATION_RESULT_COLUMNS}
            writer.writerow(row)
            written += 1
    return written


def export_evaluation_summary(records: List[Dict], path: Path, mode: str = "a") -> int:
    """Accoda/sovrascrive riepilogo aggregato."""
    path = Path(path)
    ensure_eval_header(path, EVALUATION_SUMMARY_COLUMNS)
    written = 0
    open_mode = "a" if mode == "a" else "w"
    with open(path, open_mode, newline="", encoding="utf-8-sig") as fh:
        if open_mode == "w":
            csv.writer(fh).writerow(EVALUATION_SUMMARY_COLUMNS)
        writer = csv.DictWriter(fh, fieldnames=EVALUATION_SUMMARY_COLUMNS, extrasaction="ignore")
        for rec in records:
            writer.writerow({k: rec.get(k, "") for k in EVALUATION_SUMMARY_COLUMNS})
            written += 1
    return written


def export_task_definitions(tasks: List[Dict], path: Path) -> int:
    """Scrive tasks.json (schema versionato)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({
            "schema_version": TASK_SCHEMA_VERSION,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "tasks": tasks
        }, fh, ensure_ascii=False, indent=2)
    return len(tasks)


def load_task_definitions(path: Path) -> List[Dict]:
    """Legge tasks.json."""
    import json
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("tasks", [])


# ---------------------------------------------------------------------------
# Validazione
# ---------------------------------------------------------------------------

def validate_evaluation_csv(path: Path, summary: bool = False) -> bool:
    """Valida schema con pandas."""
    try:
        import pandas as pd
        df = pd.read_csv(path, encoding="utf-8-sig")
        cols = EVALUATION_SUMMARY_COLUMNS if summary else EVALUATION_RESULT_COLUMNS
        missing = [c for c in cols if c not in df.columns]
        return not missing
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Esempio di uso (per test rapido)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Demo pass@k unbiased
    print("pass@k unbiased demo:")
    for n, c, k in [(10, 3, 1), (10, 3, 5), (10, 8, 5), (5, 0, 3), (5, 5, 3)]:
        print(f"  N={n}, c={c}, k={k} -> {compute_pass_at_k_unbiased(n, c, k):.4f}")

    # Demo Wilson
    print("\nWilson CI demo:")
    for n, k in [(100, 85), (10, 8), (5, 5), (5, 0)]:
        lo, hi = wilson_ci(n, k)
        print(f"  n={n}, k={k} -> [{lo:.4f}, {hi:.4f}]")