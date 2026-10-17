# -*- coding: utf-8 -*-
"""
semantic_evaluator.py — Similarità SEMANTICA risposta vs ground truth.

Modello approvato: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
(multilingua IT/EN, leggero, adatto a CPU). La similarità coseno tra gli
embedding di risposta e ground truth è un PROXY di correttezza semantica:
NON è una "causal accuracy pura" e va etichettata come
"semantic similarity between model response and ground truth".

Cache offline: il modello viene scaricato una volta in config.EMBED_MODEL_DIR
(override via CW_EMBED_MODEL_DIR) e riusato offline nei run successivi.

Fallback trasparente: se sentence-transformers/torch non sono disponibili o
il download fallisce, semantic_similarity = None e l'evaluator usa SOLO la
similarità lessicale secondaria, dichiarandolo esplicitamente in eval_method
("lexical_only(fallback)") e nelle note. Nessun crash, mai.
"""
from __future__ import annotations

import threading
from typing import Optional

EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_MODEL_SHORT = "paraphrase-multilingual-MiniLM-L12-v2"

_lock = threading.Lock()
_model = None                # SentenceTransformer istanziato (o sentinel False)
_init_error: str = ""        # motivo del fallback, dichiarato nel CSV/GUI


def _resolve_local_dir():
    """Directory cache locale del modello (config.EMBED_MODEL_DIR)."""
    try:
        from config import EMBED_MODEL_DIR
        return EMBED_MODEL_DIR
    except Exception:
        from pathlib import Path
        return Path(__file__).resolve().parent / "models" / EMBED_MODEL_SHORT


def _get_model():
    """Carica pigro + thread-safe del modello embeddings.

    Ritorna l'istanza SentenceTransformer oppure None se non disponibile
    (sentinel False memorizzato per non ritentare il download a ogni riga).
    """
    global _model, _init_error
    if _model is not None and _model is not False:
        return _model
    if _model is False:
        return None
    with _lock:
        if _model is not None and _model is not False:
            return _model
        if _model is False:
            return None
        try:
            from sentence_transformers import SentenceTransformer
            local_dir = _resolve_local_dir()
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            # 1° tentativo: cache locale; 2°: download HF (che popola la cache).
            try:
                _model = SentenceTransformer(str(local_dir), local_files_only=True)
            except Exception:
                _model = SentenceTransformer(
                    EMBED_MODEL_NAME, cache_folder=str(local_dir.parent)
                )
        except Exception as exc:  # ImportError, download fallito, torch assente…
            _model = False
            _init_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None
        return _model


def embedding_available() -> bool:
    """True se il backend embeddings è caricabile (senza generare eccezioni)."""
    return _get_model() is not None


def init_error() -> str:
    return _init_error


def semantic_similarity(text_a: str, text_b: str) -> Optional[float]:
    """Coseno(v(a), v(b)) con il modello multilingua; None se non disponibile.

    NB: similarità semantica normalizzata in [~0..1] (coseno su frasi); valori
    negativi vengono troncati a 0.0 per mantenerli nella scala delle metriche.
    """
    model = _get_model()
    if model is None:
        return None
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b:
        return 0.0
    try:
        va, vb = model.encode([a, b], normalize_embeddings=True)
        sim = float(sum(x * y for x, y in zip(va, vb)))  # dot = cos con vettori unitari
        return round(max(0.0, min(1.0, sim)), 6)
    except Exception as exc:
        global _init_error
        _init_error = f"encode fallito: {type(exc).__name__}: {str(exc)[:120]}"
        return None


def method_label() -> str:
    """Valore della colonna eval_method quando la via semantica è attiva."""
    return f"embedding:{EMBED_MODEL_SHORT}"
