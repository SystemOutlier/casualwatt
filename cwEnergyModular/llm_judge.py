# -*- coding: utf-8 -*-
"""
llm_judge.py — LLM-as-a-Judge via Ollama locale (Regime B, senza ground truth).

Valuta la coerenza logica/causale di una risposta con temperatura 0.0 e
restituisce un punteggio 1..5. NON inventa mai punteggi: se il giudice non e'
disponibile (Ollama giu', modello assente, timeout, parsing fallito) ritorna
None e l'evaluator marca esplicitamente il limite nel record.

Configurazione (env / .env):
  CW_JUDGE_MODEL        modello supervisore (default llama3.2:1b)
  CW_JUDGE_TIMEOUT_S    timeout chiamata (default 60)
  CW_JUDGE_ENABLED      "0" per disattivare il judge (default attivo)
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

try:
    from config import env_str, env_float, OLLAMA_API_URL
except Exception:  # pragma: no cover - fallback standalone
    import os
    OLLAMA_API_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/generate"

    def env_str(k, d): return os.getenv(k, d)
    def env_float(k, d):
        try: return float(os.getenv(k, d))
        except Exception: return d


JUDGE_SYSTEM = (
    "You are a strict impartial evaluator of causal reasoning. "
    "Do NOT reveal which model produced the answer. Judge only the logical "
    "and causal coherence of the ANSWER with respect to the QUESTION."
)

JUDGE_TEMPLATE = """Rate the logical and causal coherence of the ANSWER to the QUESTION.

Scoring rubric (integer 1..5):
5 = fully coherent, correct causal structure, no contradictions
4 = mostly coherent, minor gaps or imprecision
3 = partially coherent, some unsupported or weak links
2 = weakly coherent, major gaps or contradictions
1 = incoherent, irrelevant, or self-contradictory

QUESTION:
{question}

ANSWER:
{answer}

Respond with ONLY a single integer from 1 to 5. No words, no punctuation."""


def judge_model_name() -> str:
    return env_str("CW_JUDGE_MODEL", "llama3.2:1b")


def judge_enabled() -> bool:
    return env_str("CW_JUDGE_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def build_judge_prompt(question: str, answer: str) -> str:
    return JUDGE_TEMPLATE.format(
        question=(question or "").strip()[:4000],
        answer=(answer or "").strip()[:4000],
    )


_SCORE_RE = re.compile(r"\b([1-5])\b")


def extract_score(text: str) -> Optional[int]:
    """Estrae il punteggio 1..5 dalla risposta del giudice.

    Prende il PRIMO intero valido isolato; rigetta risposte senza match
    (None), mai valori di default fittizi.
    """
    if not text:
        return None
    m = _SCORE_RE.search(text.strip())
    if not m:
        return None
    v = int(m.group(1))
    return v if 1 <= v <= 5 else None


def call_llm_judge(question: str, answer: str,
                   model: Optional[str] = None) -> Tuple[Optional[float], dict]:
    """Chiama il giudice su Ollama. Ritorna (judge_score|None, info).

    info contiene: judge_model, ok(bool), reason, raw_response(troncata),
    duration_s. Nessuna eccezione viene propagata.
    """
    info = {"judge_model": model or judge_model_name(), "ok": False,
            "reason": "", "raw_response": "", "duration_s": None}
    if not judge_enabled():
        info["reason"] = "CW_JUDGE_ENABLED=0 (judge disattivato dall'utente)"
        return None, info
    try:
        import requests
        import time as _t
        payload = {
            "model": info["judge_model"],
            "prompt": build_judge_prompt(question, answer),
            "system": JUDGE_SYSTEM,
            "stream": False,
            "options": {"temperature": 0.0},
        }
        t0 = _t.monotonic()
        r = requests.post(OLLAMA_API_URL, json=payload,
                          timeout=env_float("CW_JUDGE_TIMEOUT_S", 60.0))
        info["duration_s"] = round(_t.monotonic() - t0, 3)
        if r.status_code != 200:
            info["reason"] = f"HTTP {r.status_code}: {r.text[:160]}"
            return None, info
        data = r.json()
        raw = str(data.get("response", ""))
        info["raw_response"] = raw[:120]
        score = extract_score(raw)
        if score is None:
            info["reason"] = "punteggio non estraibile dalla risposta del giudice"
            return None, info
        info["ok"] = True
        return float(score), info
    except Exception as exc:
        info["reason"] = f"{type(exc).__name__}: {exc}"[:200]
        return None, info
