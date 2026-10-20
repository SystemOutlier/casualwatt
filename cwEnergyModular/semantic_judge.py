# -*- coding: utf-8 -*-
"""
semantic_judge.py — Valutazione semantica POST-HOC per CasualWatt
=================================================================

Modulo INDIPENDENTE che legge il CSV dei risultati del benchmark e calcola
la similarita' semantica tra risposta del modello e ground truth.

VINCOLO METODOLOGICO:
  Questo modulo NON deve essere importato dal benchmark principale.
  La valutazione semantica avviene POST-HOC sui testi gia' generati,
  per non contaminare la misurazione energetica con il carico di
  sentence-transformers.

Uso:
  py semantic_judge.py [--input results/casualwatt_results.csv]
                       [--output results/semantic_evaluation_results.csv]

Output:
  CSV con colonna 'semantic_similarity_posthoc' aggiunta (e 'method_used'
  per tracciare se e' stato usato embedding o fallback lessicale).

Fallback automatico a SequenceMatcher se:
  - sentence-transformers non e' installato
  - il modello non e' scaricabile
  - si verifica un errore runtime

Autore: Massimo Danilo Giuliana - Tesi CasualWatt
Nota: pip install sentence-transformers torch
"""
from __future__ import annotations

import argparse
import logging
import sys
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ==============================================================================
# CONFIGURAZIONE MODELLI
# ==============================================================================
# Modello piccolo (~80 MB) - ottimo per CPU, veloce, buona qualita'
# DIVERSO dal modello usato in evaluator.py (paraphrase-multilingual-MiniLM-L12-v2)
# per mostrare che il post-hoc puo' usare un modello diverso dal benchmark
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model_instance = None
_model_load_error: Optional[str] = None


def get_semantic_model(model_name: str = DEFAULT_MODEL_NAME):
    """
    Carica il modello di embedding in modo lazy (solo al primo utilizzo).
    Restituisce (modello, errore). Se errore e' None, il modello e' pronto.
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
        logger.info(f"Modello semantico caricato: {model_name}")
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
# CALCOLO SIMILARITA'
# ==============================================================================
def semantic_similarity(text1: str, text2: str,
                        model_name: str = DEFAULT_MODEL_NAME) -> float:
    """
    Calcola la similarita' coseno tra due testi usando embedding semantici.
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
        # Similarita' coseno manuale (evita dipendenza da sklearn)
        dot_product = (embeddings[0] * embeddings[1]).sum()
        norm1 = (embeddings[0] ** 2).sum() ** 0.5
        norm2 = (embeddings[1] ** 2).sum() ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot_product / (norm1 * norm2))
    except Exception as e:
        logger.warning(f"Errore calcolo embedding: {e} -> fallback lessicale")
        return lexical_similarity(text1, text2)


def lexical_similarity(text1: str, text2: str) -> float:
    """
    Fallback lessicale: SequenceMatcher.
    Confronta i caratteri, non il significato.
    """
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def compute_similarity(text1: str, text2: str,
                       method: str = "auto") -> dict:
    """
    Funzione unificata che restituisce similarita' + metadati.

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

    # Controllo disponibilita' semantico
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
# ELABORAZIONE POST-HOC DEL CSV
# ==============================================================================
def process_csv(input_path: str, output_path: str) -> None:
    """
    Legge il CSV dei risultati, calcola similarita' semantica per ogni riga,
    e salva un nuovo CSV con le colonne aggiunte.
    """
    logger.info(f"Input CSV: {input_path}")
    if not Path(input_path).exists():
        logger.error(f"File non trovato: {input_path}")
        sys.exit(1)

    df = pd.read_csv(input_path)
    logger.info(f"Caricate {len(df)} righe")

    # Colonne necessarie
    required_cols = ["model_response", "ground_truth"]
    for col in required_cols:
        if col not in df.columns:
            logger.error(f"Colonna mancante nel CSV: {col}")
            sys.exit(1)

    # Calcola similarita' per ogni riga
    similarities = []
    methods_used = []
    semantic_available_flag = None

    for idx, row in df.iterrows():
        response = str(row.get("model_response", "") or "")
        gt = str(row.get("ground_truth", "") or "")

        # Salta righe senza ground truth o risposta
        if not response.strip() or not gt.strip() or gt.strip().lower() == "n/a":
            similarities.append(None)
            methods_used.append("skipped")
            continue

        result = compute_similarity(response, gt, method="auto")
        similarities.append(result["similarity"])
        methods_used.append(result["method_used"])

        if semantic_available_flag is None:
            semantic_available_flag = result["semantic_available"]

        if (idx + 1) % 10 == 0:
            logger.info(f"Elaborate {idx + 1}/{len(df)} righe...")

    # Aggiungi colonne al DataFrame
    df["semantic_similarity_posthoc"] = similarities
    df["semantic_method_posthoc"] = methods_used

    # Salva output
    df.to_csv(output_path, index=False)
    logger.info(f"Output salvato: {output_path}")

    # Summary
    if semantic_available_flag:
        logger.info("Metodo usato: sentence-transformers (embedding semantico)")
    else:
        logger.warning("Metodo usato: SequenceMatcher (fallback lessicale)")

    valid_sims = [s for s in similarities if s is not None]
    if valid_sims:
        logger.info(f"Similarita' media: {sum(valid_sims)/len(valid_sims):.4f}")
        logger.info(f"Similarita' min/max: {min(valid_sims):.4f} / {max(valid_sims):.4f}")


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Valutazione semantica POST-HOC per CasualWatt"
    )
    parser.add_argument(
        "--input",
        default="results/casualwatt_results.csv",
        help="Path del CSV input (default: results/casualwatt_results.csv)"
    )
    parser.add_argument(
        "--output",
        default="results/semantic_evaluation_results.csv",
        help="Path del CSV output (default: results/semantic_evaluation_results.csv)"
    )
    args = parser.parse_args()

    print("=" * 70)
    print("VALUTAZIONE SEMANTICA POST-HOC - CasualWatt")
    print("=" * 70)

    process_csv(args.input, args.output)

    print("=" * 70)
    print("COMPLETATO")
    print("=" * 70)


if __name__ == "__main__":
    main()
