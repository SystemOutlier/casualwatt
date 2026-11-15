"""
semantic_judge.py - Giudice Semantico Locale per CasualWatt
============================================================
Calcola la similarità semantica tra risposte usando modelli di embedding
eseguiti LOCALMENTE sulla CPU (nessuna chiamata cloud, energia misurabile).

Fallback automatico al giudice lessicale (SequenceMatcher) se:
- sentence-transformers non è installato
- il modello non è scaricabile
- si verifica un errore runtime

Autore: Massimo Danilo Giuliana - Tesi CasualWatt
nota: pip install sentence-transformers torch
"""
from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import Optional

logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURAZIONE MODELLI
# ==============================================================================
# Modello piccolo (~80 MB) - ottimo per CPU, veloce, buona qualità
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Modelli alternativi (più grandi, più accurati, più lenti)
# "paraphrase-multilingual-MiniLM-L12-v2"  (~460 MB, multilingua)
# "BAAI/bge-small-en-v1.5"                 (~130 MB, alta qualità)

_model_instance = None
_model_load_error: Optional[str] = None


def get_semantic_model(model_name: str = DEFAULT_MODEL_NAME):
    """
    Carica il modello di embedding in modo lazy (solo al primo utilizzo).
    Restituisce (modello, errore). Se errore è None, il modello è pronto.
    """
    global _model_instance, _model_load_error
    
    if _model_instance is not None:
        return _model_instance, None
    
    if _model_load_error is not None:
        return None, _model_load_error
    
    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"Caricamento modello semantico: {model_name}")
        _model_instance = SentenceTransformer(model_name)
        logger.info(f"✅ Modello semantico caricato: {model_name}")
        return _model_instance, None
    except ImportError:
        _model_load_error = (
            "sentence-transformers non installato. "
            "Installa con: pip install sentence-transformers"
        )
        logger.warning(_model_load_error)
        return None, _model_load_error
    except Exception as e:
        _model_load_error = f"Errore caricamento modello: {e}"
        logger.error(_model_load_error)
        return None, _model_load_error


# ==============================================================================
# CALCOLO SIMILARITÀ
# ==============================================================================
def semantic_similarity(text1: str, text2: str, 
                        model_name: str = DEFAULT_MODEL_NAME) -> float:
    """
    Calcola la similarità coseno tra due testi usando embedding semantici.
    Restituisce un valore tra 0.0 (completamente diversi) e 1.0 (identici).
    """
    if not text1 or not text2:
        return 0.0
    
    model, error = get_semantic_model(model_name)
    if model is None:
        logger.debug(f"Fallback al lessicale: {error}")
        return lexical_similarity(text1, text2)
    
    try:
        embeddings = model.encode([text1, text2], convert_to_numpy=True)
        # Similarità coseno manuale (evita dipendenza da sklearn)
        dot_product = (embeddings[0] * embeddings[1]).sum()
        norm1 = (embeddings[0] ** 2).sum() ** 0.5
        norm2 = (embeddings[1] ** 2).sum() ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    except Exception as e:
        logger.warning(f"Errore calcolo embedding: {e} → fallback lessicale")
        return lexical_similarity(text1, text2)


def lexical_similarity(text1: str, text2: str) -> float:
    """
    Fallback lessicale: SequenceMatcher (già usato nel tuo evaluator.py).
    Confronta i caratteri, non il significato.
    """
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def compute_similarity(text1: str, text2: str, 
                       method: str = "auto") -> dict:
    """
    Funzione unificata che restituisce similarità + metadati.
    
    Args:
        text1, text2: testi da confrontare
        method: "semantic", "lexical", o "auto" (prova semantico, fallback lessicale)
    
    Returns:
        dict con:
        - similarity: float [0, 1]
        - method_used: "semantic" o "lexical"
        - semantic_available: bool
    """
    # Normalizzazione base
    text1 = (text1 or "").strip()
    text2 = (text2 or "").strip()
    
    if not text1 or not text2:
        return {
            "similarity": 0.0,
            "method_used": "lexical",
            "semantic_available": False,
            "reason": "testo_vuoto"
        }
    
    # Controllo disponibilità semantico
    _, error = get_semantic_model()
    semantic_available = error is None
    
    # Scelta metodo
    if method == "lexical" or not semantic_available:
        sim = lexical_similarity(text1, text2)
        return {
            "similarity": sim,
            "method_used": "lexical",
            "semantic_available": semantic_available,
            "reason": "fallback" if not semantic_available else "scelta_utente"
        }
    
    # Metodo semantico (con fallback automatico in caso di errore)
    sim = semantic_similarity(text1, text2)
    return {
        "similarity": sim,
        "method_used": "semantic",
        "semantic_available": True,
        "reason": "embedding_ok"
    }


# ==============================================================================
# TEST RAPIDO
# ==============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("TEST GIUDICE SEMANTICO/LESSICALE")
    print("=" * 60)
    
    test_pairs = [
        ("DrivingSkill influenza DrivQuality positivamente",
         "DrivingSkill ha un impatto positivo su DrivQuality"),
        ("Il cielo è blu", "La neve è bianca"),
        ("", "testo non vuoto"),
        ("Accident causa danni all'auto", "L'incidente danneggia il veicolo"),
    ]
    
    for t1, t2 in test_pairs:
        result = compute_similarity(t1, t2, method="auto")
        print(f"\nTesto 1: {t1[:50]}")
        print(f"Testo 2: {t2[:50]}")
        print(f"Similarità: {result['similarity']:.4f}")
        print(f"Metodo: {result['method_used']}")
        print(f"Semantico disponibile: {result['semantic_available']}")
        print("-" * 60)