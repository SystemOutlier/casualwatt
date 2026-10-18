# -*- coding: utf-8 -*-
"""
semantic_evaluator.py — Similarità SEMANTICA risposta vs ground truth.

Modello approvato: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
(multilingua IT/EN, leggero, adatto a CPU). La similarità coseno tra gli
embedding di risposta e ground truth è un PROXY di correttezza semantica:
NON è una "causal accuracy pura" e va etichettata come
"semantic similarity between model response and ground truth".

Cache offline: comportamento DI DEFAULT di Hugging Face — al primo avvio il
modello (~120-470 MB) viene scaricato nella cache globale di sistema
(su Windows C:\\Users\\<TuoNome>\\.cache\\huggingface\\hub), senza parametri
cache_folder nel codice: niente file binari pesanti dentro la cartella del
progetto/GitHub. Dalla seconda esecuzione in poi il modello è caricato da
disco, offline, senza consumare rete. È possibile deviare la cache globale
solo tramite le variabili d'ambiente standard HF_HOME / HF_HUB_CACHE.

Fallback trasparente: se sentence-transformers/torch non sono disponibili o
il download fallisce, semantic_similarity = None e l'evaluator usa SOLO la
similarità lessicale secondaria, dichiarandolo esplicitamente in eval_method
("lexical_only(fallback)") e nelle note. Nessun crash, mai.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

EMBED_MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBED_MODEL_SHORT = "paraphrase-multilingual-MiniLM-L12-v2"

_lock = threading.Lock()
_model = None                # SentenceTransformer istanziato (o sentinel False)
_init_error: str = ""        # motivo del fallback, dichiarato nel CSV/GUI


def _home_cache_root():
    """Radice della cache HF globale dell'utente (default di Hugging Face).

    Risoluzione standard: HF_HOME/hub, altrimenti ~/.cache/huggingface/hub
    (su Windows: C:\\Users\\<nome>\\.cache\\huggingface\\hub).
    """
    try:
        hf_home = os.getenv("HF_HOME")
        if hf_home:
            hub = Path(hf_home) / "hub"
        else:
            hub = Path.home() / ".cache" / "huggingface" / "hub"
        explicit = os.getenv("HF_HUB_CACHE")
        return Path(explicit) if explicit else hub
    except Exception:
        return None


def _looks_like_model(path) -> bool:
    """True se la cartella contiene davvero un checkpoint SentenceTransformer."""
    try:
        p = str(path)
        return (p.endswith(".safetensors") or p.endswith(".bin")) and path.is_file() \
            if False else (path / "config.json").is_file() and any(
                (path / n).is_file() for n in ("model.safetensors", "pytorch_model.bin"))
    except Exception:
        return False


def _find_snapshot(root):
    """Cerca un checkout HF valido sotto <root>/models--…/snapshots/<rev>/content."""
    try:
        snap_parent = root / f"models--{EMBED_MODEL_NAME.replace('/', '--')}"
        snaps = snap_parent / "snapshots"
        if not snaps.is_dir():
            return None
        candidates = []
        for rev in snaps.iterdir():
            content = rev / "content" if (rev / "content").is_dir() else rev
            if _looks_like_model(content):
                candidates.append(content)
        if candidates:
            # snapshot più recente per data di modifica
            candidates.sort(key=lambda c: c.stat().st_mtime)
            return candidates[-1]
    except Exception:
        return None
    return None


def _try_load(st_cls, path, offline: bool):
    """Carica da percorso locale esplicito; ritorna None se non valido/manca."""
    try:
        if not path or not str(path):
            return None
        m = st_cls(str(path), local_files_only=offline)
        return m
    except Exception:
        return None


def _get_model():
    """Carica pigro + thread-safe del modello embeddings.

    Ordine di risoluzione (nessun crash garantito):
      1. cache HF globale dell'utente (~/.cache/huggingface/hub, default HF)
         — se il modello è già stato scaricato si usa subito, OFFLINE;
      2. download una tantum con il comportamento DI DEFAULT di Hugging Face:
         SentenceTransformer(EMBED_MODEL_NAME) SENZA cache_folder → i pesi
         finiscono nella cache globale di sistema, mai dentro la cartella
         del progetto/GitHub;
      3. fallback lessicale dichiarato (eval_method='lexical_only(fallback)').

    Ritorna l'istanza SentenceTransformer oppure None (sentinel False memorizzato
    per non ritentare a ogni riga).
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
            from sentence_transformers import SentenceTransformer as ST
            # 1) cache globale HF già popolata → carico offline senza rete
            home_cache = _home_cache_root()
            _model = _try_load(ST, _find_snapshot(home_cache) if home_cache else None,
                               offline=True)
            # 2) download una tantum nel default HF (cache globale di sistema)
            if _model is None:
                _model = ST(EMBED_MODEL_NAME)
        except Exception as exc:  # ImportError, download fallito, torch assente…
            _model = False
            _init_error = f"{type(exc).__name__}: {str(exc)[:160]}"
            return None
        if _model is None:
            _model = False
            _init_error = "modello embeddings introvabile/non scaricabile"
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
