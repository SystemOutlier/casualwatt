# -*- coding: utf-8 -*-
"""P6.8 — Frontiera di Pareto Energia-Accuratezza.

Modulo di SOLA ANALISI: non e' chiamato dal runner di misura (benchmark_v4.py),
non tocca lo schema CSV P5 (174 colonne congelate), i suoi test girano offline
su dati sintetici e campioni di calibrazione.

Definisce la frontiera di Pareto per il compromesso Energia-Accuratezza-Copertura
stratificato per categoria e aggregato, con knee detection (punto di massimo
guadagno di accuratezza per joule aggiuntivo). La frontiera principale e' a tre
dimensioni (minimizzare ECPC, massimizzare accuracy_covered, massimizzare
coverage, §4 del piano); la proiezione 2D resta per il grafico della tesi e il
knee e' un descrittore 2D dichiarato. Una soglia minima di coverage preregistrata
puo' escludere configurazioni dalla frontiera principale (fail-closed).

Riferimenti:
- cavagna2026sweetspot: modello analitico per efficienza energetica LLM
- niu2025tokenpowerbench: benchmark potenza inferenza LLM
- wang2024mmlupro: tassonomia MMLU-Pro per categorizzazione
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class ConfigPoint:
    """Un punto nello spazio (Energia, Accuratezza) per una configurazione.

    Attributes:
        model_name: Nome del modello (es. "qwen2.5:0.5b", "gemma2:9b")
        category: Categoria di task (factual, reasoning, coding, creative, ...)
        energy_j: ECPC aggregato in Joule (somma energia / corrette)
        accuracy_covered: Accuratezza condizionata (binaria validata, NON acc_comp)
        energy_ci: Intervallo di confidenza 95% per energia [lo, hi] (bootstrap)
        accuracy_ci: Intervallo di confidenza 95% per accuratezza [lo, hi] (Wilson)
        n_correct: Numero di risposte corrette
        n_total: Numero totale di item
        metadata: Dati aggiuntivi (temperatura, max_tokens, prompt_template, ...)
        coverage: frazione di item con verdetto determinato (is_correct != null),
            terza dimensione della frontiera (§4). None se non registrata: la
            dominanza ricade allora sulla 2D e un'eventuale soglia minima di
            coverage esclude il punto (fail-closed).
    """
    model_name: str
    category: str
    energy_j: float
    accuracy_covered: float
    energy_ci: Optional[tuple[float, float]] = None
    accuracy_ci: Optional[tuple[float, float]] = None
    n_correct: int = 0
    n_total: int = 0
    metadata: Optional[dict[str, Any]] = None
    coverage: Optional[float] = None


def dominates_2d(a: ConfigPoint, b: ConfigPoint) -> bool:
    """Dominanza di Pareto su DUE obiettivi: (ECPC, accuracy_covered).

    a domina b se energia_a <= energia_b E accuratezza_a >= accuratezza_b,
    con almeno una disuguaglianza stretta. La coverage NON entra: e' la
    proiezione 2D che il grafico della tesi usa ancora, ma da sola premia chi
    si astiene sui quesiti difficili (§4), quindi non e' la frontiera principale.
    """
    return (a.energy_j <= b.energy_j and a.accuracy_covered >= b.accuracy_covered and
            (a.energy_j < b.energy_j or a.accuracy_covered > b.accuracy_covered))


def dominates(a: ConfigPoint, b: ConfigPoint) -> bool:
    """Dominanza di Pareto su TRE obiettivi: ECPC, accuracy_covered, coverage.

    a domina b se non e' peggiore su nessuna delle tre dimensioni (energia
    minimizzata, accuratezza e coverage massimizzate) e strettamente migliore
    su almeno una. La coverage e' la terza dimensione raccomandata da §4: un
    modello con accuratezza condizionata alta ma coverage bassa NON domina un
    modello che risponde a piu' quesiti.

    Se la coverage non e' registrata su almeno uno dei due punti (None), la
    dimensione non e' confrontabile e la dominanza ricade sulla 2D: non si
    inventa una coverage per decidere un dominio.
    """
    if a.coverage is None or b.coverage is None:
        return dominates_2d(a, b)
    no_worse = (a.energy_j <= b.energy_j and
                a.accuracy_covered >= b.accuracy_covered and
                a.coverage >= b.coverage)
    strictly_better = (a.energy_j < b.energy_j or
                       a.accuracy_covered > b.accuracy_covered or
                       a.coverage > b.coverage)
    return no_worse and strictly_better


def pareto_frontier_2d(points: Sequence[ConfigPoint]) -> list[ConfigPoint]:
    """Frontiera di Pareto sulla proiezione 2D (ECPC, accuracy_covered).

    Sweep efficiente: ordina per energia crescente e tiene i punti che
    migliorano l'accuratezza. E' il grafico bidimensionale leggibile per la
    tesi (§4), con la coverage eventualmente come dimensione del punto. NON
    e' la frontiera principale: da sola premia chi si astiene (§4).

    Returns:
        Lista di punti non dominati in 2D, ordinati per energia crescente.
    """
    pts = list(points)
    if not pts:
        return []

    # Ordina per energia crescente, per accuratezza decrescente come tie-breaker
    pts.sort(key=lambda p: (p.energy_j, -p.accuracy_covered))

    frontier = []
    best_accuracy = -1.0
    for p in pts:
        if p.accuracy_covered > best_accuracy:
            frontier.append(p)
            best_accuracy = p.accuracy_covered

    return frontier


def pareto_frontier(points: Sequence[ConfigPoint]) -> list[ConfigPoint]:
    """Frontiera di Pareto principale: configurazioni non dominate in 3D.

    Usa ``dominates`` (ECPC, accuracy_covered, coverage): un punto entra se
    nessun altro lo domina su tutte e tre le dimensioni. Con coverage assente
    la dominanza ricade sulla 2D, quindi i punti legacy danno la frontiera 2D.

    Il confronto ha significato solo fra configurazioni valutate sullo stesso
    insieme di task, stesse categorie, stesse condizioni di generazione e
    stesso protocollo di scoring (§4.1): il modulo non lo verifica, lo dichiara.

    Args:
        points: Sequenza di ConfigPoint

    Returns:
        Lista di punti non dominati, ordinati per energia crescente.
    """
    pts = list(points)
    frontier = [p for p in pts
                if not any(dominates(q, p) for q in pts if q is not p)]
    frontier.sort(key=lambda p: (p.energy_j, -p.accuracy_covered))
    return frontier


def filter_min_coverage(points: Sequence[ConfigPoint],
                        min_coverage: Optional[float]
                        ) -> tuple[list[ConfigPoint], list[ConfigPoint]]:
    """Applica una soglia minima di coverage PREREGISTRATA (§4).

    La soglia si fissa prima dei risultati e si motiva rispetto al caso d'uso;
    qui e' un parametro, non un numero scelto dopo aver visto i dati. Una
    configurazione entra nella frontiera principale solo se la sua coverage
    registrata raggiunge la soglia.

    Fail-closed: con soglia attiva, un punto senza coverage (None) non puo'
    dimostrare di raggiungerla ed e' escluso. Con ``min_coverage=None`` il
    filtro e' disattivato (nessuna soglia preregistrata, da dichiarare).

    Returns:
        (kept, excluded): punti ammessi e punti esclusi, cosi' l'esclusione
        resta tracciabile invece di sparire in silenzio.
    """
    pts = list(points)
    if min_coverage is None:
        return pts, []
    kept, excluded = [], []
    for p in pts:
        if p.coverage is not None and p.coverage >= min_coverage:
            kept.append(p)
        else:
            excluded.append(p)
    return kept, excluded


def knee_detection(frontier: Sequence[ConfigPoint]) -> Optional[ConfigPoint]:
    """Identifica il 'knee' della frontiera: punto di massimo guadagno per joule.

    PROIEZIONE 2D dichiarata: la distanza geometrica e' calcolata sul piano
    (ECPC, accuracy_covered); la coverage NON entra nella distanza del knee.
    Il knee e' un descrittore della forma 2D della frontiera, non un punto
    ottimo sulle tre dimensioni.

    Metodo: massima distanza perpendicolare dall'inviluppo convesso dei punti
    della frontiera. L'inviluppo e' costruito SOLO dai punti della frontiera
    (Andrew's monotone chain), NON include il punto ideale (0,1) ne' il punto
    peggiore (max_energia, 0) come descritto in una stesura precedente: la
    differenza e' rilevante per frontiere corte. Il knee e' il punto della
    frontiera con distanza massima dall'inviluppo convesso dei punti della
    frontiera stessa.

    Args:
        frontier: Punti sulla frontiera di Pareto (già ordinati per energia)

    Returns:
        ConfigPoint del knee, o None se frontier ha < 3 punti.
    """
    if len(frontier) < 3:
        return None

    pts = list(frontier)
    # Coordinate per calcolo geometrico: (energia, -accuratezza) per convesso verso l'alto
    coords = np.array([(p.energy_j, -p.accuracy_covered) for p in pts])

    # Inviluppo convesso (Andrew's monotone chain)
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    # Lower hull
    lower = []
    for p in coords:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(tuple(p))

    # Upper hull
    upper = []
    for p in reversed(coords):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(tuple(p))

    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None

    # Per ogni punto sulla frontiera, calcola distanza perpendicolare al segmento
    # dell'inviluppo che lo contiene (o al più vicino)
    max_dist = -1.0
    knee_idx = 0

    for i, p in enumerate(coords):
        # Trova il segmento dell'hull più vicino
        min_dist = float('inf')
        for j in range(len(hull)):
            a = np.array(hull[j])
            b = np.array(hull[(j + 1) % len(hull)])
            # Distanza punto-segmento
            ap = p - a
            ab = b - a
            t = np.dot(ap, ab) / np.dot(ab, ab)
            if t < 0:
                dist = np.linalg.norm(p - a)
            elif t > 1:
                dist = np.linalg.norm(p - b)
            else:
                proj = a + t * ab
                dist = np.linalg.norm(p - proj)
            if dist < min_dist:
                min_dist = dist

        if min_dist > max_dist:
            max_dist = min_dist
            knee_idx = i

    return pts[knee_idx]


def pareto_by_category(points: Sequence[ConfigPoint]) -> dict[str, list[ConfigPoint]]:
    """Calcola frontiera di Pareto per ogni categoria.

    Args:
        points: Tutti i punti

    Returns:
        Dizionario categoria -> lista punti frontiera (ordinati per energia)
    """
    by_cat: dict[str, list[ConfigPoint]] = {}
    for p in points:
        by_cat.setdefault(p.category, []).append(p)

    return {cat: pareto_frontier(pts) for cat, pts in by_cat.items()}


def export_pareto_json(frontier: Sequence[ConfigPoint],
                       path: str | Path,
                       by_category: Optional[dict[str, list[ConfigPoint]]] = None,
                       knee: Optional[ConfigPoint] = None,
                       min_coverage: Optional[float] = None,
                       excluded: Optional[Sequence[ConfigPoint]] = None) -> None:
    """Esporta frontiera di Pareto in JSON, con le dichiarazioni del metodo."""
    path = Path(path)
    data = {
        "frontier": [asdict(p) for p in frontier],
        "by_category": {cat: [asdict(p) for p in pts] for cat, pts in (by_category or {}).items()},
        "knee": asdict(knee) if knee else None,
        "min_coverage_preregistered": min_coverage,
        "excluded_by_min_coverage": [asdict(p) for p in (excluded or [])],
        "notes": (
            "Pareto frontier (primary): configurations not dominated on THREE objectives "
            "(minimize ECPC, maximize accuracy_covered, maximize coverage). Coverage = "
            "fraction of items with a determinate verdict (is_correct != null); without it "
            "dominance falls back to 2D. Energy = ECPC (sum eligible energy / ALL correct "
            "answers). Accuracy = accuracy_covered (binary validated, NOT acc_comp). "
            "min_coverage_preregistered is the pre-registered coverage threshold for the "
            "primary frontier (fixed before data; None = no threshold, declared); points "
            "below it or without recorded coverage are excluded (fail-closed) and listed in "
            "excluded_by_min_coverage. The 2D projection (ECPC, accuracy_covered) remains "
            "available for the thesis plot, with coverage as point size. Knee = maximum "
            "perpendicular distance from the convex hull, a 2D projection descriptor "
            "(coverage does not enter the distance). Comparability requires the same task "
            "set, categories, generation conditions and scoring protocol across configurations. "
            "Descriptive analysis only: no point is promoted to 'validated'."
        ),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def import_pareto_json(path: str | Path) -> dict[str, Any]:
    """Importa frontiera di Pareto da JSON."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ---- Costruzione punti da risultati summarizzati ----

def points_from_taxonomy_result(taxonomy_result: dict[str, Any],
                                model_name: str,
                                metadata: Optional[dict[str, Any]] = None
                                ) -> list[ConfigPoint]:
    """Costruisce ConfigPoint dai risultati di taxonomy_ecpc.compute_taxonomy_ecpc.

    Args:
        taxonomy_result: Output di taxonomy_ecpc.compute_taxonomy_ecpc
        model_name: Nome del modello
        metadata: Dati aggiuntivi (temperatura, max_tokens, ...)

    Returns:
        Lista di ConfigPoint, uno per categoria.
    """
    points = []
    for cat, data in taxonomy_result.get("by_category", {}).items():
        ecpc = data.get("ecpc_j")
        acc = data.get("accuracy_on_determinate")
        if ecpc is None or acc is None:
            continue
        n_total = data.get("n_total", 0)
        n_determinate = data.get("n_determinate")
        coverage = (n_determinate / n_total
                    if n_determinate is not None and n_total else None)
        points.append(ConfigPoint(
            model_name=model_name,
            category=cat,
            energy_j=ecpc,
            accuracy_covered=acc,
            energy_ci=data.get("ecpc_cluster_bootstrap_95"),
            accuracy_ci=None,  # Wilson CI not directly available here
            n_correct=data.get("n_correct", 0),
            n_total=n_total,
            metadata=metadata,
            coverage=coverage,
        ))
    return points


def points_from_evaluation_summary(summary: dict[str, Any],
                                   model_name: str,
                                   category_key: str = "category",
                                   metadata: Optional[dict[str, Any]] = None
                                   ) -> list[ConfigPoint]:
    """Costruisce ConfigPoint dai risultati di evaluation_runner.summarize_records.

    Args:
        summary: Output di evaluation_runner.summarize_records
        model_name: Nome del modello
        category_key: Chiave categoria (default "category")
        metadata: Dati aggiuntivi

    Returns:
        Lista di ConfigPoint, uno per categoria.
    """
    points = []
    for cat, data in summary.get("categories", {}).items():
        ecpc = data.get("ecpc_j")
        # accuracy_on_determinate e scoring_coverage sono le chiavi che
        # summarize_records scrive DENTRO ogni categoria. verdict_accuracy_covered
        # esiste solo al livello complessivo: leggerla qui dava sempre None.
        acc = data.get("accuracy_on_determinate")
        if ecpc is None or acc is None:
            continue
        points.append(ConfigPoint(
            model_name=model_name,
            category=cat,
            energy_j=ecpc,
            accuracy_covered=acc,
            energy_ci=data.get("ecpc_cluster_bootstrap_95"),
            accuracy_ci=None,
            n_correct=data.get("n_correct", 0),
            n_total=data.get("n_total", 0),
            metadata=metadata,
            coverage=data.get("scoring_coverage"),
        ))
    return points