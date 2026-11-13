# -*- coding: utf-8 -*-
"""P6.9 — Protocollo di Robustezza a Perturbazioni.

Modulo di SOLA ANALISI: non e' chiamato dal runner di misura (benchmark_v4.py),
non tocca lo schema CSV P5 (174 colonne congelate), i suoi test girano offline
su dati sintetici e campioni di calibrazione.

Applica perturbazioni controllate a un sottoinsieme di task (es. 20% per categoria)
SENZA cambiare seed/temperatura del modello, e misura la stabilità del verdetto
e il delta energetico.

Riferimenti:
- zheng2024llmajsurvey: survey su LLM-as-a-judge, raccomanda test di invarianza
- liu2023geval: G-Eval, rubriche esplicite e campionamento multiplo
- saadfalcon2025ipw: pesi inversi per correggere bias di selezione
"""

from __future__ import annotations

import json
import random
import zlib
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

# Tipi di perturbazione supportati
PERTURBATION_TYPES = (
    "syntactic_rephrase",      # Parafrasi automatica (back-translation)
    "instruction_reorder",     # Shuffle frasi prompt
    "synonym_substitution",    # Sostituzione lessicale controllata
    "minor_formatting",        # Markdown <-> plain, spazi, maiuscole
    "temperature_sweep",       # Campionamento a temperature diverse (0.1, 0.5, 1.0)
)

# Direzioni di flip del verdetto (§6.2): una perdita di accuratezza
# (correct->incorrect) non e' un degrado della capacita' di scoring
# (correct/incorrect->indeterminate) ne' un recupero (indeterminate->...).
FLIP_CATEGORIES = (
    "correct->incorrect",
    "incorrect->correct",
    "correct->indeterminate",
    "incorrect->indeterminate",
    "indeterminate->correct",
    "indeterminate->incorrect",
)

# Dichiarazione di preservazione della ground truth per trasformazione (§6.1).
# 'identity_placeholder': l'implementazione attuale restituisce il testo
#   invariato, quindi la GT e' banalmente preservata ma NON e' una parafrasi reale.
# 'requires_verification': la trasformazione cambia il prompt e la validita' della
#   risposta attesa va verificata (umano o automatico), non assunta.
# 'not_applicable': non perturba il prompt (campionamento a temperature diverse).
GT_PRESERVATION = {
    "syntactic_rephrase": "identity_placeholder",
    "instruction_reorder": "requires_verification",
    "synonym_substitution": "identity_placeholder",
    "minor_formatting": "requires_verification",
    "temperature_sweep": "not_applicable",
}


def verdict_transition(original: str, perturbed: str) -> str:
    """Transizione canonica del verdetto: 'stable' o la coppia direzionale."""
    if original == perturbed:
        return "stable"
    return f"{original}->{perturbed}"


@dataclass(frozen=True)
class PerturbationResult:
    """Risultato di una singola perturbazione su un task (confronto appaiato)."""
    task_id: str
    category: str
    perturbation_type: str
    original_verdict: str          # "correct" | "incorrect" | "indeterminate"
    perturbed_verdict: str         # "correct" | "incorrect" | "indeterminate"
    original_energy_j: float
    perturbed_energy_j: float
    verdict_stable: bool           # original_verdict == perturbed_verdict
    energy_delta_j: float          # perturbed - original
    metadata: Optional[dict[str, Any]] = None
    # transizione direzionale del verdetto (§6.2): 'stable' o 'orig->pert'
    verdict_transition: str = "stable"
    # latenza baseline/perturbata e loro delta (§6.2); None se non registrata
    original_latency_s: Optional[float] = None
    perturbed_latency_s: Optional[float] = None
    latency_delta_s: Optional[float] = None
    # verifica della ground truth (§6.1): risposta attesa originale, esito della
    # verifica che sia ancora valida sul quesito perturbato, e metodo dichiarato.
    ground_truth: Optional[str] = None
    gt_still_valid: Optional[bool] = None
    gt_verification: str = ""


@dataclass(frozen=True)
class PerturbationSummary:
    """Risultati aggregati per tipo di perturbazione e categoria."""
    perturbation_type: str
    category: str
    n_tasks: int
    stability_rate: float          # Frazione verdetti stabili
    mean_energy_delta_j: float     # Delta energetico medio
    max_energy_delta_j: float      # Delta energetico massimo
    verdict_flips: int             # Numero flip correct <-> incorrect (accuratezza)
    flip_rate: float               # Frazione flip
    by_task: list[PerturbationResult]
    # breakdown direzionale dei flip (§6.2): tutte le sei direzioni, zero se assenti
    flip_breakdown: dict[str, int] = field(default_factory=dict)
    # DeltaECPC sul campione appaiato (§6.2): ECPC = somma energia / corrette
    baseline_ecpc_j: Optional[float] = None
    perturbed_ecpc_j: Optional[float] = None
    delta_ecpc_j: Optional[float] = None
    # DeltaLatency medio sulle coppie con entrambe le latenze (§6.2)
    mean_latency_delta_s: Optional[float] = None


def apply_syntactic_rephrase(text: str, seed: int = 42) -> str:
    """Parafrasi sintattica via back-translation (IDENTITY PLACEHOLDER).

    In produzione, usa un modello di traduzione (es. Helsinki-NLP/opus-mt)
    per tradurre in una lingua intermedia e indietro. Finche' quel modello non
    e' implementato la funzione restituisce il testo INVARIATO: non e' una
    parafrasi e non va presentata come tale. GT_PRESERVATION lo dichiara
    'identity_placeholder' (§6.1: il back-translation non e' comunque una
    garanzia di preservazione semantica).

    Args:
        text: Testo da parafrasare
        seed: Seed per riproducibilità (usato solo dall'implementazione reale)

    Returns:
        Testo invariato (placeholder dichiarato).
    """
    return text


def apply_instruction_reorder(text: str, seed: int = 42) -> str:
    """Riordino frasi del prompt mantenendo la semantica.

    Args:
        text: Prompt originale
        seed: Seed per riproducibilità

    Returns:
        Prompt con frasi riordinate
    """
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    if len(sentences) < 2:
        return text
    rng = random.Random(seed)
    rng.shuffle(sentences)
    return '. '.join(sentences) + '.'


def apply_synonym_substitution(text: str, seed: int = 42, rate: float = 0.1) -> str:
    """Sostituzione lessicale controllata con sinonimi (placeholder implementato).

    Usa un dizionario minimo di sinonimi comuni in italiano. In produzione
    usare WordNet o embedding per copertura completa. GT_PRESERVATION lo
    dichiara 'identity_placeholder' perche' la sostituzione lessicale senza
    disambiguazione contestuale non garantisce preservazione semantica.

    Args:
        text: Testo originale
        seed: Seed per riproducibilità
        rate: Frazione parole da sostituire (approssimativa)

    Returns:
        Testo con alcuni sinonimi sostituiti
    """
    # Dizionario minimo di sinonimi per placeholder
    SYNONYMS = {
        "rispondi": "replica",
        "spiega": "illustra",
        "descrivi": "delinea",
        "analizza": "esamina",
        "valuta": "giudica",
        "confronta": "paragona",
        "elenca": "enumera",
        "esempio": "esemplificazione",
        "motivo": "ragione",
        "causa": "origine",
        "risultato": "esito",
        "conseguenza": "effetto",
        "importante": "rilevante",
        "necessario": "indispensabile",
        "possibile": "eventuale",
        "diverso": "differente",
        "simile": "analogo",
        "generale": "comune",
        "specifico": "particolare",
        "principale": "fondamentale",
    }
    
    import re
    words = re.findall(r'\b\w+\b', text.lower())
    n_sub = max(1, int(len(words) * rate))
    rng = random.Random(seed)
    indices = rng.sample(range(len(words)), min(n_sub, len(words)))
    
    # Applica sostituzioni mantenendo case originale approssimativamente
    result = text
    for idx in indices:
        original = words[idx]
        if original in SYNONYMS:
            synonym = SYNONYMS[original]
            # Sostituisce solo la prima occorrenza per evitare catene
            result = re.sub(r'\b' + re.escape(original) + r'\b', synonym, result, count=1, flags=re.IGNORECASE)
    
    return result if result != text else text + " [synonym_substitution]"


def apply_minor_formatting(text: str, seed: int = 42) -> str:
    """Variazioni di formattazione minore: Markdown <-> plain, spazi, maiuscole.

    GT_PRESERVATION lo dichiara 'requires_verification' perche' la
    trasformazione di formattazione puo' cambiare l'interpretazione della
    risposta attesa (es. elenco puntato vs paragrafo).

    Args:
        text: Testo originale
        seed: Seed per riproducibilità

    Returns:
        Testo con formattazione variata
    """
    variations = [
        lambda t: t.replace('**', '').replace('*', ''),  # Rimuovi markdown
        lambda t: t.upper(),                               # Maiuscole
        lambda t: t.lower(),                               # Minuscole
        lambda t: ' '.join(t.split()),                     # Normalizza spazi
        lambda t: t.replace('\n', ' '),                    # Una riga
    ]
    rng = random.Random(seed)
    fn = rng.choice(variations)
    return fn(text)


def apply_temperature_sweep(
    generate_fn: Callable[[float], tuple[str, float]],
    temperatures: Sequence[float] = (0.1, 0.5, 1.0),
    seed: int = 42
) -> list[tuple[float, str, float]]:
    """Campionamento a temperature diverse (non perturbazione del prompt).

    Args:
        generate_fn: Funzione che dato temperature ritorna (response, energy_j)
        temperatures: Temperature da testare
        seed: Seed per riproducibilità

    Returns:
        Lista di (temperature, response, energy_j)
    """
    results = []
    for temp in temperatures:
        rng = random.Random(seed + int(temp * 1000))
        response, energy = generate_fn(temp)
        results.append((temp, response, energy))
    return results


PERTURBATION_FNS = {
    "syntactic_rephrase": apply_syntactic_rephrase,
    "instruction_reorder": apply_instruction_reorder,
    "synonym_substitution": apply_synonym_substitution,
    "minor_formatting": apply_minor_formatting,
}


def _unpack_eval(result: tuple) -> tuple[str, float, Optional[float]]:
    """Normalizza il ritorno di evaluate_fn a (verdetto, energia, latenza).

    La firma storica a due valori (verdetto, energia) resta accettata: la
    latenza assente e' None, non zero (§6.2: assenza di misura != variazione
    nulla).
    """
    if len(result) == 3:
        verdict, energy, latency = result
        return verdict, energy, latency
    verdict, energy = result
    return verdict, energy, None


def _summarize_results(
    perturbation_type: str,
    category: str,
    results: Sequence[PerturbationResult],
) -> PerturbationSummary:
    """Aggrega i risultati appaiati di un (tipo, categoria).

    Il breakdown dei flip distingue le sei direzioni (§6.2); verdict_flips
    resta la sola accuratezza (correct <-> incorrect). DeltaECPC e' calcolato
    sul campione appaiato come somma energia / corrette, separatamente per
    baseline e perturbato, e resta None se un denominatore e' nullo.
    """
    n = len(results)
    stability_rate = sum(r.verdict_stable for r in results) / n if n else 0.0
    energy_deltas = [r.energy_delta_j for r in results]

    flip_breakdown = {k: 0 for k in FLIP_CATEGORIES}
    for r in results:
        if r.verdict_transition in flip_breakdown:
            flip_breakdown[r.verdict_transition] += 1
    verdict_flips = (flip_breakdown["correct->incorrect"]
                     + flip_breakdown["incorrect->correct"])

    baseline_energy = sum(r.original_energy_j for r in results)
    baseline_correct = sum(1 for r in results if r.original_verdict == "correct")
    perturbed_energy = sum(r.perturbed_energy_j for r in results)
    perturbed_correct = sum(1 for r in results if r.perturbed_verdict == "correct")
    baseline_ecpc = baseline_energy / baseline_correct if baseline_correct else None
    perturbed_ecpc = perturbed_energy / perturbed_correct if perturbed_correct else None
    delta_ecpc = (perturbed_ecpc - baseline_ecpc
                  if baseline_ecpc is not None and perturbed_ecpc is not None
                  else None)

    latency_deltas = [r.latency_delta_s for r in results if r.latency_delta_s is not None]
    mean_latency_delta = sum(latency_deltas) / len(latency_deltas) if latency_deltas else None

    return PerturbationSummary(
        perturbation_type=perturbation_type,
        category=category,
        n_tasks=n,
        stability_rate=stability_rate,
        mean_energy_delta_j=sum(energy_deltas) / n if n else 0.0,
        max_energy_delta_j=max(energy_deltas) if n else 0.0,
        verdict_flips=verdict_flips,
        flip_rate=verdict_flips / n if n else 0.0,
        by_task=list(results),
        flip_breakdown=flip_breakdown,
        baseline_ecpc_j=baseline_ecpc,
        perturbed_ecpc_j=perturbed_ecpc,
        delta_ecpc_j=delta_ecpc,
        mean_latency_delta_s=mean_latency_delta,
    )


def run_perturbation_protocol(
    tasks: Sequence[dict[str, Any]],
    evaluate_fn: Callable[[str], tuple],  # (prompt) -> (verdict, energy[, latency])
    perturbation_types: Sequence[str] = PERTURBATION_TYPES[:-1],  # Exclude temperature_sweep
    sample_fraction: float = 0.2,
    seed: int = 20261104,
    verify_gt_fn: Optional[Callable[[dict, str, str], bool]] = None,
) -> list[PerturbationSummary]:
    """Esegue il protocollo di perturbazione su un sottoinsieme di task.

    Confronto appaiato (§6.3): lo stesso task e' valutato in condizione baseline
    e perturbata. Il campione (default 20% per categoria) e' un PILOTA, non la
    numerosita' definitiva. Il seed per-task usa zlib.crc32 (stabile fra
    processi, a differenza di hash() salato).

    Args:
        tasks: Lista di task con chiavi task_id, category, prompt, ground_truth
        evaluate_fn: (prompt) -> (verdict, energy_j) o (verdict, energy_j, latency_s)
        perturbation_types: Tipi di perturbazione da applicare
        sample_fraction: Frazione di task per categoria da perturbare (pilota)
        seed: Seed per riproducibilita'
        verify_gt_fn: Verificatore (task, prompt_orig, prompt_pert) -> bool della
            validita' della ground truth sul quesito perturbato (§6.1). Se assente,
            le trasformazioni identity-placeholder dichiarano GT preservata, le
            altre restano 'not_verified'.

    Returns:
        Lista di PerturbationSummary per (tipo, categoria).
    """
    rng = random.Random(seed)

    # Raggruppa per categoria
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        cat = task.get("category", "unknown")
        by_cat.setdefault(cat, []).append(task)

    all_summaries = []

    for cat, cat_tasks in by_cat.items():
        # Campiona sottoinsieme per categoria (pilota)
        n_sample = max(1, int(len(cat_tasks) * sample_fraction))
        sampled = rng.sample(cat_tasks, min(n_sample, len(cat_tasks)))

        for ptype in perturbation_types:
            if ptype not in PERTURBATION_FNS:
                continue

            perturb_fn = PERTURBATION_FNS[ptype]
            results = []

            for task in sampled:
                original_prompt = task.get("prompt", "")
                original_verdict, original_energy, original_latency = _unpack_eval(
                    evaluate_fn(original_prompt))

                # Applica perturbazione con seed stabile fra processi
                task_seed = seed + zlib.crc32(task["task_id"].encode("utf-8"))
                perturbed_prompt = perturb_fn(original_prompt, seed=task_seed)
                perturbed_verdict, perturbed_energy, perturbed_latency = _unpack_eval(
                    evaluate_fn(perturbed_prompt))

                # Verifica della ground truth (§6.1): non si assume preservazione
                ground_truth = task.get("ground_truth")
                if verify_gt_fn is not None:
                    gt_still_valid = verify_gt_fn(task, original_prompt, perturbed_prompt)
                    gt_verification = "provided_fn"
                elif GT_PRESERVATION.get(ptype) == "identity_placeholder":
                    gt_still_valid = True
                    gt_verification = "identity_placeholder"
                else:
                    gt_still_valid = None
                    gt_verification = "not_verified"

                latency_delta = (perturbed_latency - original_latency
                                 if original_latency is not None and perturbed_latency is not None
                                 else None)

                results.append(PerturbationResult(
                    task_id=task["task_id"],
                    category=cat,
                    perturbation_type=ptype,
                    original_verdict=original_verdict,
                    perturbed_verdict=perturbed_verdict,
                    original_energy_j=original_energy,
                    perturbed_energy_j=perturbed_energy,
                    verdict_stable=(original_verdict == perturbed_verdict),
                    energy_delta_j=perturbed_energy - original_energy,
                    metadata={"original_prompt": original_prompt, "perturbed_prompt": perturbed_prompt},
                    verdict_transition=verdict_transition(original_verdict, perturbed_verdict),
                    original_latency_s=original_latency,
                    perturbed_latency_s=perturbed_latency,
                    latency_delta_s=latency_delta,
                    ground_truth=ground_truth,
                    gt_still_valid=gt_still_valid,
                    gt_verification=gt_verification,
                ))

            all_summaries.append(_summarize_results(ptype, cat, results))

    return all_summaries


def export_perturbation_results(
    summaries: Sequence[PerturbationSummary],
    path: str | Path,
) -> None:
    """Esporta risultati perturbazione in JSON."""
    path = Path(path)
    data = {
        "summaries": [asdict(s) for s in summaries],
        "overall": {
            "total_tasks": sum(s.n_tasks for s in summaries),
            "mean_stability_rate": sum(s.stability_rate * s.n_tasks for s in summaries) / sum(s.n_tasks for s in summaries) if summaries else 0.0,
            "total_verdict_flips": sum(s.verdict_flips for s in summaries),
            "overall_flip_rate": sum(s.verdict_flips for s in summaries) / sum(s.n_tasks for s in summaries) if summaries else 0.0,
        },
        "notes": (
            "Perturbation protocol (PILOT sample, default 20% per category; the definitive "
            "sample size depends on the desired precision of DeltaAccuracy and the fraction "
            "of verdict changes). PAIRED comparison: the same task is evaluated in baseline "
            "and perturbed condition. Measures verdict stability, energy delta, DeltaECPC "
            "(sum energy / correct, baseline vs perturbed on the paired sample) and "
            "DeltaLatency. The flip breakdown distinguishes accuracy loss (correct->incorrect), "
            "recovery (incorrect->correct, indeterminate->correct/incorrect) and scoring-capacity "
            "degradation (correct/incorrect->indeterminate); verdict_flips counts only accuracy "
            "(correct <-> incorrect). Ground-truth preservation is declared per transformation "
            "(identity_placeholder vs not_verified vs provided_fn): back-translation/reorder is "
            "NOT a guarantee of semantic preservation. A perturbation that does not change verdict "
            "but doubles energy signals an efficiency problem, not an accuracy problem. Constant "
            "seed/temperature only if the model supports a reproducible seed; otherwise record the "
            "limitation and use replicates. Per-task seed uses zlib.crc32 (stable across processes). "
            "References: zheng2024llmajsurvey (invariance tests), liu2023geval (rubrics), "
            "saadfalcon2025ipw (inverse propensity weighting)."
        ),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def import_perturbation_results(path: str | Path) -> dict[str, Any]:
    """Importa risultati perturbazione da JSON."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)