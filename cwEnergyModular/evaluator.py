# -*- coding: utf-8 -*-
"""
evaluator.py — Valutazione UNIVERSALE delle risposte.

Tre regimi, scelti automaticamente in base ai dati RICEVUTI (i test arrivano
da sorgenti esterne: CSV MUDILab-like o prompt manuali — mai hardcodati):

1) CON ground truth -> eval_mode = "ground_truth"
   Metrica PRINCIPALE: semantic_similarity = coseno(embedding(risposta),
   embedding(ground_truth)) con modello multilingua approvato
   paraphrase-multilingual-MiniLM-L12-v2 (semantic_evaluator.py).
   ETICHETTA METODOLOGICA: "semantic similarity between model response and
   ground truth" — PROXY di correttezza, NON "causal accuracy pura".
   Metrica SECONDARIA: lexical_similarity = SequenceMatcher (dichiarata come
   tale, non più usata come giudizio principale).
   is_correct = semantic_similarity >= CW_SEMANTIC_THRESHOLD (default 0.75,
   configurabile). In regime GT acc_comp = semantic_similarity (dichiarato).
   Fallback trasparente: se gli embeddings non sono disponibili il risultato
   resta valido ma eval_method = "lexical_only(fallback)" e la nota lo dice.

2) REGIME euristico keyword cause/effect (storico sez. 10 specifica),
   attivato SOLO esplicitamente -> eval_mode = "heuristic_keyword_fallback"
   (NON è una ground-truth accuracy e non viene mai chiamata tale).
   Regole ESATTE:
   * acc_links: 1.0 se 'cause' ed 'effect'; 0.5 se solo uno; 0.0 nessuno
   * judge_score: tool+full -> 4.5 ; non-tool+full -> 4.0 ; half -> 3.0 ; none -> 1.5
   * cosine_sim: 0.88 se is_tool else 0.75 (valore hardcoded della specifica)
   Formula approvata per il composito:
       acc_comp = 0.6*acc_links + 0.3*(judge_score/5) + 0.1*cosine_sim

3) SENZA ground truth e senza richiesta causale -> eval_mode = "skipped":
   nessun errore, campi accuratezza N/A, salvate solo metriche
   energetiche/di latenza/token.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional

import semantic_evaluator as _sem

try:  # soglia configurabile via env (.env/CW_SEMANTIC_THRESHOLD)
    from config import env_float
    _DEFAULT_THRESHOLD = env_float("CW_SEMANTIC_THRESHOLD", 0.75)
except Exception:
    _DEFAULT_THRESHOLD = 0.75

NA = None  # rappresentazione N/A nei record (il writer CSV la rende "")


@dataclass
class EvaluationResult:
    acc_links: Optional[float] = NA
    judge_score: Optional[float] = NA
    cosine_sim: Optional[float] = NA          # hardcoded solo nel regime keyword
    semantic_similarity: Optional[float] = NA # metrica principale regime GT
    lexical_similarity: Optional[float] = NA  # metrica secondaria regime GT
    semantic_threshold: float = _DEFAULT_THRESHOLD
    eval_method: str = ""                     # embedding:... | lexical_only(fallback) | heuristic keywords
    is_tool: bool = False
    n_correct_links: Optional[int] = NA
    causal_accuracy: Optional[float] = NA
    explanation_quality: Optional[float] = NA
    acc_comp: Optional[float] = NA
    is_correct: Optional[bool] = NA
    has_cause: Optional[bool] = NA
    has_effect: Optional[bool] = NA
    eval_mode: str = "skipped"  # "ground_truth" | "heuristic_keyword_fallback" | "skipped"
    notes: List[str] = field(default_factory=list)


_CAUSE_RE = re.compile(r"\bcaus(?:e|es|ed|ing|al|ality)\b", re.IGNORECASE)
_EFFECT_RE = re.compile(r"\beffect(?:s|ed|ing|ive|ually)?\b", re.IGNORECASE)

# compatibilità storica: soglia lessicale non più metrica principale
GT_MATCH_THRESHOLD = 0.85
SEMANTIC_THRESHOLD = _DEFAULT_THRESHOLD

GT_LABEL = ("semantic similarity between model response and ground truth "
            "(proxy of correctness, not pure causal accuracy)")


def detect_causal_terms(text: str):
    """True/False per presenza di 'cause' ed 'effect' nel testo."""
    t = text or ""
    return bool(_CAUSE_RE.search(t)), bool(_EFFECT_RE.search(t))


def _normalize_answer(s: str) -> str:
    """Normalizzazione robusta: minuscole, punteggiatura rimossa, spazi
    compressi, articoli EN/IT comuni ignorati."""
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàèéìòù]", " ", s)
    s = re.sub(r"\b(a|an|the|il|lo|la|i|gli|le|un|uno|una)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def lexical_similarity(response_text: str, ground_truth: str) -> float:
    """Metrica SECONDARIA: similarità lessicale [0..1] (SequenceMatcher).
    Match esatto o GT contenuta nella risposta (normalizzati) -> 1.0."""
    gt_n = _normalize_answer(ground_truth)
    ans_n = _normalize_answer(response_text)
    if not gt_n:
        return 0.0
    if ans_n == gt_n or gt_n in ans_n:
        return 1.0
    return round(difflib.SequenceMatcher(None, ans_n, gt_n).ratio(), 6)


# retro-compatibilità (vecchi import): ora è chiaramente LESSICALE
def score_against_ground_truth(response_text: str, ground_truth: str) -> float:
    return lexical_similarity(response_text, ground_truth)


def evaluate_response(text: str, is_tool: bool = False,
                      ground_truth: Optional[str] = None,
                      mode: str = "auto") -> EvaluationResult:
    """Valutazione UNIVERSALE — firma retro-compatibile.

    mode:
      * "auto" (default): se ``ground_truth`` e' presente -> regime
        ground-truth SEMANTICO; altrimenti -> salto accuratezza (N/A), solo energia.
      * "causal": forza l'euristica keyword cause/effect
        (eval_mode = "heuristic_keyword_fallback").
      * "skip": forza N/A anche con GT presente.
    Non solleva MAI eccezioni: qualunque input produce un EvaluationResult.
    """
    mode = (mode or "auto").strip().lower()

    # ------------------------- regime ground truth --------------------------
    if mode == "auto" and ground_truth not in (None, "", NA):
        lex = lexical_similarity(text or "", str(ground_truth))
        sem = _sem.semantic_similarity(text or "", str(ground_truth))
        thr = _DEFAULT_THRESHOLD

        if sem is None:
            # fallback trasparente: niente embeddings -> solo lessicale dichiarata
            method = "lexical_only(fallback)"
            score = lex
            res = EvaluationResult(
                eval_mode="ground_truth",
                eval_method=method,
                is_tool=bool(is_tool),
                semantic_similarity=NA,
                lexical_similarity=lex,
                semantic_threshold=thr,
                causal_accuracy=score,
                acc_comp=score,
                is_correct=score >= GT_MATCH_THRESHOLD,  # soglia storica solo nel fallback
                explanation_quality=NA,
                n_correct_links=(1 if score >= GT_MATCH_THRESHOLD else NA),
            )
            res.notes.append(
                f"fallback lessicale: valutazione semantica non disponibile "
                f"({_sem.init_error() or 'motivo non specificato'}); score derivato "
                f"da lexical_similarity, NON presentare il risultato come "
                f"valutazione semantica"
            )
            res.notes.append(GT_LABEL)
            return res

        method = _sem.method_label()
        res = EvaluationResult(
            eval_mode="ground_truth",
            eval_method=method,
            is_tool=bool(is_tool),
            semantic_similarity=sem,
            lexical_similarity=lex,
            semantic_threshold=thr,
            # NB: in regime GT questa colonna riporta la similarita' SEMANTICA
            # (proxy di correttezza), non una causal accuracy formale.
            causal_accuracy=sem,
            acc_comp=sem,  # dichiarato: acc_comp = semantic_similarity nel regime GT
            is_correct=sem >= thr,
            explanation_quality=NA,   # non definito senza judge causale
            n_correct_links=(1 if sem >= thr else NA),
        )
        res.notes.append(
            f"{GT_LABEL}; sim_sem={sem:.3f} vs soglia {thr:.2f}; "
            f"sim_less(secondaria)={lex:.3f}"
        )
        return res

    # ---------- regime euristico keyword (NON ground-truth accuracy) --------
    if mode in ("causal", "heuristic_keyword_fallback"):
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

        # formula approvata (NON (acc_links+cosine)/2):
        acc_comp = round(
            0.6 * acc_links + 0.3 * (judge_score / 5.0) + 0.1 * cosine_sim, 6
        )

        res = EvaluationResult(
            eval_mode="heuristic_keyword_fallback",
            eval_method="heuristic keywords cause/effect (NOT ground-truth accuracy)",
            acc_links=acc_links,
            judge_score=judge_score,
            cosine_sim=cosine_sim,
            is_tool=bool(is_tool),
            n_correct_links=n_correct_links,
            causal_accuracy=acc_links,          # proxy keyword, dichiarato euristico
            explanation_quality=judge_score / 5.0,  # scala normalizzata [0..1]
            acc_comp=acc_comp,
            is_correct=acc_links == 1.0,
            has_cause=has_cause,
            has_effect=has_effect,
        )
        res.notes.append(
            "heuristic_keyword_fallback: presenza parole cause/effect, "
            "confrontabile solo con altri run CasualWatt, NON con ground_truth"
        )
        if is_tool:
            res.notes.append("risposta con evidenze di tool-call")
        return res

    # --------------------- salto valutazione (N/A) --------------------------
    res = EvaluationResult(eval_mode="skipped", is_tool=bool(is_tool))
    res.eval_method = "none"
    res.notes.append(
        "valutazione accuratezza saltata: nessuna ground_truth ne' modalita' "
        "causale richiesta; salvate solo metriche energetiche/di latenza/token"
    )
    return res


def evaluate_skipped(reason: str = "") -> EvaluationResult:
    """Risultato esplicito N/A (usato nei percorsi d'errore del runner)."""
    res = EvaluationResult(eval_mode="skipped")
    res.eval_method = "none"
    if reason:
        res.notes.append(f"valutazione non eseguita: {reason}")
    return res
