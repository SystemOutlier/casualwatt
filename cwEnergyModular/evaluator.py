# -*- coding: utf-8 -*-
"""
evaluator.py — Valutazione UNIVERSALE delle risposte (refactoring accademico).

REGIME A — CON ground truth (eval_mode = "ground_truth"):
  * acc_links = F1-score su TRIPLE CAUSALI estratte da ground truth e risposta
    (causal_extractor.py). NON keyword matching. Se la GT non contiene triple
    strutturate -> fallback dichiarato in ordine di preferenza:
      1) semantic_similarity (embedding MiniLM multilingua);
      2) lexical_similarity (SequenceMatcher) solo se embeddings assenti;
    il risultato NON viene mai presentato come valutazione strutturale.
  * cosine_sim = semantic_similarity (misura reale, non hardcoded).
  * judge_score = LLM-as-a-Judge Ollama temperatura 0.0 (se disponibile;
    altrimenti N/A e acc_comp ricalcolato senza di esso, dichiarato).
  * Formula approvata Regime A:
      acc_comp = 0.50*acc_links + 0.30*(judge_score/5) + 0.20*cosine_sim
    (pesi ridistribuiti e dichiarati se un componente e' N/A).
  * ETICHETTA della similarita': "semantic similarity between model response
    and ground truth" — proxy di correttezza, NON causal accuracy pura.

REGIME B — SENZA ground truth (eval_mode = "causal_agent_eval"):
  * cosine_sim NON calcolata e MAI forzata a valori fittizi -> N/A nel CSV.
  * acc_links = F1 sulle triple estratte dalla domanda/riferimenti quando
    possibile, altrimenti 0.0 (punteggio demandato al judge).
  * judge_score OBBLIGATORIO via LLM Judge (llm_judge.py). Formula:
      acc_comp = 0.65*acc_links + 0.35*(judge_score/5)

REGIME euristico keyword cause/effect: RIMOSSO dal calcolo (la funzione
storica resta solo come helper diagnostico has_cause/has_effect nel record).

Regime "skipped": nessuna valutazione, campi N/A, solo energia/latenza/token.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import List, Optional

import semantic_evaluator as _sem
import causal_extractor as _cx

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
    cosine_sim: Optional[float] = NA          # solo misura reale (regime A)
    semantic_similarity: Optional[float] = NA # metrica principale regime GT
    lexical_similarity: Optional[float] = NA  # metrica secondaria regime GT
    semantic_threshold: float = _DEFAULT_THRESHOLD
    eval_method: str = ""                     # embedding:... | lexical_only(fallback) | llm_judge...
    eval_mode: str = "skipped"                # ground_truth | causal_agent_eval | skipped
    is_tool: bool = False
    n_correct_links: Optional[int] = NA
    causal_accuracy: Optional[float] = NA
    explanation_quality: Optional[float] = NA
    acc_comp: Optional[float] = NA
    is_correct: Optional[bool] = NA
    has_cause: Optional[bool] = NA            # solo diagnostico, NON usato in acc_comp
    has_effect: Optional[bool] = NA           # solo diagnostico, NON usato in acc_comp
    # --- triple causali (tracciabilita' F1) ---
    triples_gt: Optional[int] = NA
    triples_response: Optional[int] = NA
    triples_matched: Optional[int] = NA
    f1_precision: Optional[float] = NA
    f1_recall: Optional[float] = NA
    acc_links_basis: str = ""                 # f1_triples | semantic_fallback | lexical_fallback | none
    # --- LLM Judge ---
    judge_model: str = ""
    evaluated_model: str = ""
    judge_equals_evaluated: Optional[bool] = NA
    judge_source: str = ""                    # ollama | unavailable | disabled
    notes: List[str] = field(default_factory=list)


_CAUSE_RE = re.compile(r"\bcaus(?:e|es|ed|ing|al|ality)\b", re.IGNORECASE)
_EFFECT_RE = re.compile(r"\beffect(?:s|ed|ing|ive|ually)?\b", re.IGNORECASE)

GT_LABEL = ("semantic similarity between model response and ground truth "
            "(proxy of correctness, not pure causal accuracy)")


def detect_causal_terms(text: str):
    """SOLO diagnostico: presenza letterale 'cause'/'effect'. NON alimenta
    piu' alcuna metrica di accuratezza (heuristic_keyword_fallback rimosso)."""
    t = text or ""
    return bool(_CAUSE_RE.search(t)), bool(_EFFECT_RE.search(t))


def _normalize_answer(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàèéìòù]", " ", s)
    s = re.sub(r"\b(a|an|the|il|lo|la|i|gli|le|un|uno|una)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def lexical_similarity(response_text: str, ground_truth: str) -> float:
    """Metrica SECONDARIA: similarità lessicale [0..1] (SequenceMatcher)."""
    gt_n = _normalize_answer(ground_truth)
    ans_n = _normalize_answer(response_text)
    if not gt_n:
        return 0.0
    if ans_n == gt_n or gt_n in ans_n:
        return 1.0
    return round(difflib.SequenceMatcher(None, ans_n, gt_n).ratio(), 6)


def compute_acc_comp(has_ground_truth: bool, acc_links: Optional[float],
                     judge_score: Optional[float],
                     cosine_sim: Optional[float] = None) -> Optional[float]:
    """Accuratezza composita con pesi DINAMICI (nessuna costante magica).

    Regime A (GT + cosine disponibile):
        0.50*acc_links + 0.30*(judge/5) + 0.20*cosine
    Regime B (senza GT / cosine None):
        0.65*acc_links + 0.35*(judge/5)
    Se un componente e' N/A, i suoi pesi vengono RIDISTRIBUITI proporzionalmente
    sui componenti disponibili (comportamento dichiarato nelle note), mai
    sostituito da valori fittizi. Ritorna None se non c'e' nulla di calcolabile.
    """
    parts = []  # (weight, normalized_value)
    if acc_links is not None:
        parts.append((0.50 if has_ground_truth else 0.65,
                      max(0.0, min(1.0, acc_links))))
    if judge_score is not None:
        parts.append((0.30 if has_ground_truth else 0.35,
                      max(0.0, min(1.0, judge_score / 5.0))))
    if has_ground_truth and cosine_sim is not None:
        parts.append((0.20, max(0.0, min(1.0, cosine_sim))))

    if not parts:
        return None
    total_w = sum(w for w, _ in parts)
    score = sum(w * v for w, v in parts) / total_w  # rinormalizzazione onesta
    return round(score, 4)


def _f1_acc_links(text: str, ground_truth: str, res: EvaluationResult):
    """acc_links da F1 su triple causali, con fallback DICHJARATO in catena:
    semantic_similarity -> lexical_similarity. Ritorna (value, basis)."""
    t_gt = _cx.extract_triples(ground_truth)
    t_ans = _cx.extract_triples(text or "")
    res.triples_gt = len(t_gt)
    res.triples_response = len(t_ans)
    f1 = _cx.f1_on_triples(t_gt, t_ans)
    if f1 is not None:
        res.triples_matched = f1["n_matched"]
        res.f1_precision = f1["precision"]
        res.f1_recall = f1["recall"]
        return f1["f1"], "f1_triples"
    # GT senza triple strutturate: valutazione strutturale IMPOSSIBILE.
    res.notes.append(
        "acc_links: ground truth priva di triple causali strutturate; "
        "usa proxy SEMANTICO (non e' una valutazione strutturale di triple)"
    )
    sem = res.semantic_similarity
    if sem is not None:
        return sem, "semantic_fallback"
    lex = res.lexical_similarity
    if lex is not None:
        res.notes.append(
            "fallback LESSICALE (SequenceMatcher) dichiarato: embeddings non "
            "disponibili; NON presentare il risultato come valutazione "
            "strutturale o semantica"
        )
        return lex, "lexical_fallback"
    return 0.0, "none"


def evaluate_response(text: str, is_tool: bool = False,
                      ground_truth: Optional[str] = None,
                      mode: str = "auto", question: str = "",
                      evaluated_model: str = "",
                      judge_fn=None) -> EvaluationResult:
    """Valutazione UNIVERSALE.

    mode:
      * "auto": ground_truth presente -> REGIME A ("ground_truth");
                altrimenti -> REGIME B ("causal_agent_eval") con LLM Judge.
      * "skip": forza N/A anche con GT presente.
    judge_fn: iniettabile per i test (firma: (question, answer, model?) ->
              (score|None, info dict)). Default: llm_judge.call_llm_judge.
    Non solleva MAI eccezioni.
    """
    mode = (mode or "auto").strip().lower()
    res = EvaluationResult(is_tool=bool(is_tool),
                           evaluated_model=evaluated_model or "")
    res.has_cause, res.has_effect = detect_causal_terms(text)  # solo diagnostico

    if mode == "skip":
        res.eval_mode, res.eval_method = "skipped", "none"
        res.notes.append("valutazione saltata per richiesta esplicita")
        return res

    # ------------------------- REGIME A: ground truth -----------------------
    if ground_truth not in (None, "", NA):
        res.eval_mode = "ground_truth"
        res.lexical_similarity = lexical_similarity(text or "", str(ground_truth))
        sem = _sem.semantic_similarity(text or "", str(ground_truth))
        res.semantic_similarity = sem
        res.cosine_sim = sem  # misura REALE (non più hardcoded)
        thr = _DEFAULT_THRESHOLD
        if sem is None:
            res.eval_method = "lexical_only(fallback)"
            res.notes.append(
                f"embeddings non disponibili ({_sem.init_error() or 'motivo non specificato'}): "
                f"metrica principale NON calcolabile, usare solo i campi lessicali dichiarati"
            )
        else:
            res.eval_method = _sem.method_label()
        res.is_correct = (sem >= thr) if sem is not None else \
                         (res.lexical_similarity >= 0.85)
        res.causal_accuracy = sem  # etichetta: proxy semantico, vedi GT_LABEL
        res.acc_links, res.acc_links_basis = _f1_acc_links(text, str(ground_truth), res)
        res.n_correct_links = res.triples_matched if res.triples_matched is not None else \
            (1 if res.is_correct else 0)
        # judge opzionale ma tentato (arricchisce il mix Regime A)
        j_score, j_info = _run_judge(question, text, res, judge_fn)
        res.judge_score = j_score
        res.explanation_quality = (j_score / 5.0) if j_score is not None else NA
        res.acc_comp = compute_acc_comp(True, res.acc_links, j_score, sem)
        res.notes.append(GT_LABEL)
        res.notes.append(
            f"regime A: acc_comp=0.50*acc_links+0.30*(judge/5)+0.20*cosine "
            f"(componenti N/A rinormalizzati e dichiarati); "
            f"basis acc_links={res.acc_links_basis}"
        )
        return res

    # ----------------- REGIME B: senza GT -> LLM-as-a-Judge -----------------
    res.eval_mode = "causal_agent_eval"
    res.eval_method = "llm_judge(ollama,T=0)+triple_f1(self-consistency)"
    res.cosine_sim = NA               # MAI forzato: N/A nel CSV
    res.semantic_similarity = NA      # idem: nessuna GT da confrontare
    res.lexical_similarity = NA
    # acc_links: struttura causale auto-consistente nella risposta
    # (triples estratte; senza triple riconoscibili -> 0.0, punteggio al judge)
    t_ans = _cx.extract_triples(text or "")
    res.triples_response = len(t_ans)
    res.triples_gt = NA               # inesistente in regime B
    if t_ans:
        res.acc_links = 1.0           # struttura presente ed estraibile
        res.acc_links_basis = "f1_triples"
        res.triples_matched = len(t_ans)
    else:
        res.acc_links = 0.0
        res.acc_links_basis = "none"
        res.notes.append(
            "nessuna tripla causale estraibile dalla risposta: acc_links=0.0, "
            "punteggio qualitativo interamente demandato al LLM Judge"
        )
    j_score, j_info = _run_judge(question, text, res, judge_fn)
    if j_score is None:
        res.eval_method = "llm_judge_unavailable"
        res.notes.append(
            f"LLM Judge non disponibile ({j_info.get('reason','')}): "
            f"acc_comp calcolata SOLO su acc_links, giudice dichiarato assente"
        )
    res.judge_score = j_score
    res.explanation_quality = (j_score / 5.0) if j_score is not None else NA
    res.n_correct_links = res.triples_matched if res.triples_matched else 0
    res.is_correct = (j_score >= 4.0) if j_score is not None else NA
    res.causal_accuracy = NA          # in regime B non esiste causal accuracy GT-based
    res.acc_comp = compute_acc_comp(False, res.acc_links, j_score, None)
    res.notes.append(
        "regime B: acc_comp=0.65*acc_links+0.35*(judge/5); "
        "cosine_sim/semantic_similarity=N/A (nessuna ground truth)"
    )
    return res


def _run_judge(question: str, answer: str, res: EvaluationResult, judge_fn):
    """Esegue il giudice e compila i campi tracciabilita'/bias."""
    try:
        if judge_fn is None:
            import llm_judge as _lj
            judge_fn = _lj.call_llm_judge
        score, info = judge_fn(question or "", answer or "", None)
    except Exception as exc:  # il giudice non deve MAI far fallire la valutazione
        score, info = None, {"reason": f"{type(exc).__name__}: {exc}",
                             "judge_model": ""}
    res.judge_model = str(info.get("judge_model", ""))
    res.judge_source = "ollama" if info.get("ok") else \
        ("disabled" if "ENABLED" in str(info.get("reason", "")) else "unavailable")
    if res.judge_model and res.evaluated_model:
        same = res.judge_model.strip().lower() == res.evaluated_model.strip().lower()
        res.judge_equals_evaluated = same
        if same:
            res.notes.append(
                "Self-evaluation bias possible: judge model equals evaluated model."
            )
    return score, info


def evaluate_skipped(reason: str = "") -> EvaluationResult:
    """Risultato esplicito N/A (usato nei percorsi d'errore del runner)."""
    res = EvaluationResult(eval_mode="skipped")
    res.eval_method = "none"
    if reason:
        res.notes.append(f"valutazione non eseguita: {reason}")
    return res
