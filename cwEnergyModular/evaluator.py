# -*- coding: utf-8 -*-
"""
evaluator.py — Valutazione causale delle risposte (sezione 10).

Regole ESATTE della specifica, senza metriche inventate:
* acc_links: 1.0 se 'cause' ed 'effect' presenti; 0.5 se solo uno; 0.0 nessuno
* judge_score: tool+full -> 4.5 ; non-tool+full -> 4.0 ; half -> 3.0 ; none -> 1.5
* cosine_sim: 0.88 se is_tool else 0.75
Espone inoltre i derivati richiesti dal CSV: causal_accuracy, explanation_quality,
n_correct_links, acc_comp, is_correct.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class EvaluationResult:
    acc_links: float = 0.0
    judge_score: float = 0.0
    cosine_sim: float = 0.0
    is_tool: bool = False
    n_correct_links: int = 0
    causal_accuracy: float = 0.0
    explanation_quality: float = 0.0
    acc_comp: float = 0.0
    is_correct: bool = False
    has_cause: bool = False
    has_effect: bool = False
    notes: List[str] = field(default_factory=list)


_CAUSE_RE = re.compile(r"\bcaus(?:e|es|ed|ing|al|ality)\b", re.IGNORECASE)
_EFFECT_RE = re.compile(r"\beffect(?:s|ed|ing|ive|ually)?\b", re.IGNORECASE)


def detect_causal_terms(text: str):
    """True/False per presenza di 'cause' ed 'effect' nel testo."""
    t = text or ""
    return bool(_CAUSE_RE.search(t)), bool(_EFFECT_RE.search(t))


def evaluate_response(text: str, is_tool: bool = False) -> EvaluationResult:
    """Applica le regole della sezione 10. ``is_tool`` indica che il modello
    ha usato un tool/call strutturato durante la generazione."""
    has_cause, has_effect = detect_causal_terms(text)

    if has_cause and has_effect:
        acc_links = 1.0
    elif has_cause or has_effect:
        acc_links = 0.5
    else:
        acc_links = 0.0

    if acc_links == 1.0:
        judge_score = 4.5 if is_tool else 4.0
    elif acc_links == 0.5:
        judge_score = 3.0
    else:
        judge_score = 1.5

    cosine_sim = 0.88 if is_tool else 0.75

    n_correct_links = 2 if acc_links == 1.0 else (1 if acc_links == 0.5 else 0)

    res = EvaluationResult(
        acc_links=acc_links,
        judge_score=judge_score,
        cosine_sim=cosine_sim,
        is_tool=bool(is_tool),
        n_correct_links=n_correct_links,
        causal_accuracy=acc_links,          # accuratezza causale richiesta
        explanation_quality=judge_score / 5.0,  # scala normalizzata [0..1]
        acc_comp=round((acc_links + cosine_sim) / 2.0, 6),  # composito dichiarato
        is_correct=acc_links == 1.0,
        has_cause=has_cause,
        has_effect=has_effect,
    )
    if is_tool:
        res.notes.append("risposta con evidenze di tool-call")
    return res
