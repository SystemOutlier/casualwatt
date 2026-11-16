# -*- coding: utf-8 -*-
"""background_monitor_json.py — persistenza dell'artefatto diagnostico.

Perché esiste. Il monitor del background (`background_monitor.py`) produce
due verdetti per blocco (locale e globale) con differenze, timestamp e
overhead. Questi dati sono troppo dettagliati per il campo `notes` del CSV P5
(174 nomi congelati), ma non possono essere persi.

Questo modulo scrive `background_monitor.json` accanto ai CSV di risultati,
collegando ogni record al blocco corrispondente tramite `batch_id` e
`block_id`. La scrittura è atomica: prima in un file temporaneo, poi rename
per evitare file parziali in caso di arresto improvviso.

L'artefatto JSON non è un requisito per la validità delle misure energetiche:
se la scrittura fallisce, le righe CSV restano valide. Il fallimento viene
registrato come problema diagnostico, non come invalidazione.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List


def write_background_monitor_json(
    verdicts: List[Dict],
    path: Path,
) -> None:
    """Scrive l'artefatto diagnostico del monitor in JSON.

    Ogni record contiene: batch_id, block_id, local_verdict, global_verdict,
    local_diff, global_diff, overhead_s, timestamp, errors.

    La scrittura è atomica: scrive in un file temporaneo nella stessa
    directory, poi rename per evitare file parziali.

    Args:
        verdicts: lista di dizionari, uno per blocco.
        path: percorso del file JSON da scrivere.

    Raises:
        OSError: se la scrittura o il rename falliscono. Il chiamante deve
            catturare l'eccezione e registrare l'errore come insufficient_data,
            senza invalidare le misure energetiche già salvate.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Legge il file esistente (se presente) per accumulare i verdetti
    existing: List[Dict] = []
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # File corrotto: parte da zero, non crash
            existing = []

    # Accoda i nuovi verdetti
    existing.extend(verdicts)

    # Scrittura atomica: file temporaneo + rename
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json.tmp",
        prefix="background_monitor_",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(path))
    except Exception:
        # Pulisce il file temporaneo se il rename fallisce
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
