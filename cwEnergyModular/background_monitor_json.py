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
    """Persist an idempotent set of block verdicts using an atomic replace.

    Records are uniquely identified by (batch_id, block_id). Replaying a
    record updates that record rather than appending a duplicate. Existing
    malformed or ambiguous artifacts fail closed: they are never silently
    discarded because that would destroy diagnostic evidence.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    incoming_by_key: Dict[tuple, Dict] = {}
    for index, verdict in enumerate(verdicts):
        if not isinstance(verdict, dict):
            raise TypeError(f"verdict #{index} must be a dict")
        batch_id = str(verdict.get("batch_id") or "").strip()
        block_id = str(verdict.get("block_id") or "").strip()
        if not batch_id or not block_id:
            raise ValueError(
                f"verdict #{index} requires non-empty batch_id and block_id"
            )
        key = (batch_id, block_id)
        if key in incoming_by_key:
            raise ValueError(f"duplicate input verdict key: {key!r}")
        incoming_by_key[key] = dict(verdict)

    existing_by_key: Dict[tuple, Dict] = {}
    if path.exists() and path.stat().st_size > 0:
        try:
            with path.open("r", encoding="utf-8") as fh:
                existing = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(
                f"existing background monitor artifact is unreadable: {path}"
            ) from exc
        if not isinstance(existing, list):
            raise ValueError(
                f"existing background monitor artifact must contain a list: {path}"
            )
        for index, record in enumerate(existing):
            if not isinstance(record, dict):
                raise ValueError(f"existing record #{index} is not an object")
            key = (
                str(record.get("batch_id") or "").strip(),
                str(record.get("block_id") or "").strip(),
            )
            if not all(key):
                raise ValueError(
                    f"existing record #{index} lacks batch_id/block_id"
                )
            if key in existing_by_key:
                raise ValueError(
                    f"existing artifact contains duplicate key {key!r}"
                )
            existing_by_key[key] = record

    # Upsert, preserving the original insertion order for historical records.
    for key, record in incoming_by_key.items():
        existing_by_key[key] = record

    merged = list(existing_by_key.values())
    fd, tmp_path = tempfile.mkstemp(
        suffix=".json.tmp",
        prefix="background_monitor_",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2, allow_nan=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, str(path))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
