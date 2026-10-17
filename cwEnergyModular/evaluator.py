# -*- coding: utf-8 -*-
"""
evaluator.py — Valutazione UNIVERSALE delle risposte.

Due regimi, scelti automaticamente in base ai dati ricevuti (i test arrivano
da sorgenti esterne: CSV MUDILab-like o prompt manuali — mai hardcodati):

1) CON ground truth (colonna ground_truth/expected_result nel CSV caricato):
   l'accuratezza è il confronto risposta-vs-risultato-atteso
   (normalizzazione + match esatto, altrimenti similarità lessicale):
     is_correct        = match (>= soglia 0.85)
     causal_accuracy   = similarita' normalizzata [0..1]
     acc_comp          = same score composito
   I campi specifici dei test causali (judge_score, cosine_sim, n_correct_links)
   restano N/A quando non applicabili al regime: vengono lasciati vuoti così
   che ECE/EPCL/energy_per_correct_answer non mescolino regimi diversi.

2) SENZA ground truth (prompt manuale o CSV privo di etichette):
   NON va in errore: salta il calcolo accuratezza (campi -> N/A) e concentra
   il salvataggio sulle sole metriche energetiche/di latenza/token.

3) REGIME CAUSALE STORICO (sezione 10 della specifica CasualWatt), attivato
   SOLO esplicitamente con mode="causal" (dataset che richiede cause/effect):
   regole ESATTE:
   * acc_links: 1.0 se 'cause' ed 'effect' presenti; 0.5 se solo uno; 0.0 nessuno
   * judge_score: tool+full -> 4.5 ; non-tool+full -> 4.0 ; half -> 3.0 ; none -> 1.5
   * cosine_sim: 0.88 se is_tool else 0.75
   Espone i derivati richiesti dal CSV: causal_accuracy, explanation_quality,
   n_correct_links, acc_comp, is_correct.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional

NA = None  # rappresentazione N/A nei record (il writer CSV la rende "")


@dataclass
class EvaluationResult:
    acc_links: Optional[float] = NA
    judge_score: Optional[float] = NA
    cosine_sim: Optional[float] = NA
    is_tool: bool = False
    n_correct_links: Optional[int] = NA
    causal_accuracy: Optional[float] = NA
    explanation_quality: Optional[float] = NA
    acc_comp: Optional[float] = NA
    is_correct: Optional[bool] = NA
    has_cause: Optional[bool] = NA
    has_effect: Optional[bool] = NA
    eval_mode: str = "skipped"  # "ground_truth" | "causal" | "skipped"
    notes: List[str] = field(default_factory=list)


_CAUSE_RE = re.compile(r"\bcaus(?:e|es|ed|ing|al|ality)\b", re.IGNORECASE)
_EFFECT_RE = re.compile(r"\beffect(?:s|ed|ing|ive|ually)?\b", re.IGNORECASE)

# soglia di similarita' per considerare "corretta" una risposta con GT libera
GT_MATCH_THRESHOLD = 0.85


def detect_causal_terms(text: str):
    """True/False per presenza di 'cause' ed 'effect' nel testo."""
    t = text or ""
    return bool(_CAUSE_RE.search(t)), bool(_EFFECT_RE.search(t))


def _normalize_answer(s: str) -> str:
    """Normalizzazione robusta per il confronto con ground_truth: minuscole,
    punteggiatura rimossa, spazi compressi, articoli EN/IT comuni ignorati."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàèéìòù]", " ", s)
    s = re.sub(r"\b(a|an|the|il|lo|la|i|gli|le|un|uno|una)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def score_against_ground_truth(response_text: str, ground_truth: str) -> float:
    """Score [0..1] della risposta rispetto al risultato atteso.

    Euristica dichiarata, nessuna metrica inventata oltre al confronto:
    1. match esatto (normalizzato)                      -> 1.0
    2. GT contenuto nella risposta (formato libero)     -> 1.0
    3. altrimenti similarita' lessicale SequenceMatcher -> [0..1]
    """
    gt_n = _normalize_answer(ground_truth)
    ans_n = _normalize_answer(response_text)
    if not gt_n:
        return 0.0
    if ans_n == gt_n:
        return 1.0
    if gt_n in ans_n:
        return 1.0
    return round(difflib.SequenceMatcher(None, ans_n, gt_n).ratio(), 6)


def evaluate_response(text: str, is_tool: bool = False,
                      ground_truth: Optional[str] = None,
                      mode: str = "auto") -> EvaluationResult:
    """Valutazione UNIVERSALE — firma retro-compatibile.

    mode:
      * "auto" (default): se ``ground_truth`` e' presente -> regime
        ground-truth; altrimenti -> salto accuratzza (N/A), solo energia.
      * "causal": forza le regole causali della sezione 10 (cause/effect).
      * "skip": forza N/A anche con GT presente.
    Non solleva MAI eccezioni: qualunque input produce un EvaluationResult.
    """
    mode = (mode or "auto").strip().lower()

    # ------------------------- regime ground truth --------------------------
    if mode == "auto" and ground_truth not in (None, "", NA):
        score = score_against_ground_truth(text or "", str(ground_truth))
        res = EvaluationResult(
            eval_mode="ground_truth",
            is_tool=bool(is_tool),
            causal_accuracy=score,
            acc_comp=score,
            is_correct=score >= GT_MATCH_THRESHOLD,
            explanation_quality=NA,   # non definito senza judge causale
            n_correct_links=(1 if score >= GT_MATCH_THRESHOLD else NA),
        )
        res.notes.append(
            f"accuracy=confronto vs ground_truth (score {score:.2f}, "
            f"soglia {GT_MATCH_THRESHOLD})"
        )
        return res

    # ----------------------------- regime causale ---------------------------
    if mode == "causal":
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
            eval_mode="causal",
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

    # --------------------- salto valutazione (N/A) --------------------------
    res = EvaluationResult(eval_mode="skipped", is_tool=bool(is_tool))
    res.notes.append(
        "valutazione accuratezza saltata: nessuna ground_truth ne' modalita' "
        "causale richiesta; salvate solo metriche energetiche/di latenza/token"
    )
    return res


def evaluate_skipped(reason: str = "") -> EvaluationResult:
    """Risultato esplicito N/A (usato nei percorsi d'errore del runner)."""
    res = EvaluationResult(eval_mode="skipped")
    if reason:
        res.notes.append(f"valutazione non eseguita: {reason}")
    return res
