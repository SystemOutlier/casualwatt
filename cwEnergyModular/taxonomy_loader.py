# -*- coding: utf-8 -*-
"""cwEnergyModular/taxonomy_loader.py — Priorita' 9.

Caricamento di tassonomie di benchmark esterni (es. MMLU, MMLU-Pro, HELM) da
file JSON/CSV e mappatura ``task_id -> categoria esterna`` sui record di
valutazione.

Perche' esiste. `taxonomy_ecpc.compute_taxonomy_ecpc` e
`evaluation_runner.summarize_records` operano su una colonna ``category`` che
oggi viene letta direttamente dalle righe di input, senza alcuna mappatura a una
tassonomia esterna. Questo modulo colma la filiera di ingresso: carica una
tassonomia esterna da file e assegna a ogni record la categoria corrispondente,
cosi' che ECPC per categoria e frontiera di Pareto possano essere calcolati su
categorie esterne invece che su etichette interne arbitrarie.

Il modulo e' di **sola analisi**: non tocca il percorso di misura, non aggiunge
colonne CSV allo schema P5 congelato (174 nomi), non modifica
`taxonomy_ecpc.py`, `evaluation_runner.py` o `benchmark_v4.py`. Solo stdlib.

Contratto:
- `load_taxonomy_from_json(path) -> dict[str, str]`
- `load_taxonomy_from_csv(path) -> dict[str, str]`
- `map_categories(records, taxonomy, task_id_key="task_id", category_key="external_category") -> list[dict]`

Regole:
- task_id mancante o non presente nella tassonomia -> categoria "unknown"
- nessun fallback silenzioso: un file inesistente o malformed solleva un errore dichiarato
- le righe di input non vengono modificate sul posto: `map_categories` restituisce nuove dict
- JSON atteso: lista di oggetti `{"task_id": ..., "category": ...}` oppure dict `{task_id: category}`
- CSV atteso: intestazione `task_id,category` (prima colonna task_id, seconda categoria)
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

CATEGORIA_SCONOSCIUTA = "unknown"


def load_taxonomy_from_json(path: str | Path) -> dict[str, str]:
    """Carica una tassonomia esterna da file JSON.

    Accetta due forme:
      1. lista di oggetti: ``[{"task_id": "t1", "category": "factual"}, ...]``
      2. dizionario: ``{"t1": "factual", "t2": "reasoning"}``

    Restituisce ``{task_id: categoria}``.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"tassonomia JSON non trovata: {p}")
    with p.open("r", encoding="utf-8") as f:
        dati = json.load(f)

    mappa: dict[str, str] = {}
    if isinstance(dati, dict):
        for task_id, categoria in dati.items():
            tid = str(task_id).strip()
            cat = str(categoria).strip() if categoria is not None else CATEGORIA_SCONOSCIUTA
            if tid:
                mappa[tid] = cat or CATEGORIA_SCONOSCIUTA
    elif isinstance(dati, list):
        for i, oggetto in enumerate(dati):
            if not isinstance(oggetto, Mapping):
                raise ValueError(
                    f"tassonomia JSON: elemento {i} non e' un oggetto (valore: {oggetto!r})"
                )
            tid = str(oggetto.get("task_id", "")).strip()
            cat = str(oggetto.get("category", CATEGORIA_SCONOSCIUTA)).strip()
            if not tid:
                raise ValueError(
                    f"tassonomia JSON: elemento {i} privo di task_id (valore: {oggetto!r})"
                )
            mappa[tid] = cat or CATEGORIA_SCONOSCIUTA
    else:
        raise ValueError(
            f"tassonomia JSON: formato non riconosciuto (atteso lista di oggetti o dizionario, "
            f"trovato {type(dati).__name__})"
        )
    return mappa


def load_taxonomy_from_csv(path: str | Path) -> dict[str, str]:
    """Carica una tassonomia esterna da file CSV.

    Si aspetta un'intestazione con almeno due colonne: la prima e' ``task_id``,
    la seconda e' ``category``. Le colonne aggiuntive vengono ignorate.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"tassonomia CSV non trovata: {p}")
    mappa: dict[str, str] = {}
    with p.open("r", encoding="utf-8", newline="") as f:
        lettore = csv.reader(f)
        intestazione = next(lettore, None)
        if intestazione is None:
            raise ValueError(f"tassonomia CSV vuota: {p}")
        # Normalizza i nomi di colonna per trovare task_id e category.
        indice_task = indice_categoria = None
        for idx, col in enumerate(intestazione):
            c = col.strip().lower()
            if c == "task_id":
                indice_task = idx
            elif c == "category":
                indice_categoria = idx
        if indice_task is None or indice_categoria is None:
            raise ValueError(
                f"tassonomia CSV: intestazione deve contenere 'task_id' e 'category', "
                f"trovato {intestazione}"
            )
        for n_riga, riga in enumerate(lettore, start=2):
            if not riga or all(cella.strip() == "" for cella in riga):
                continue
            if indice_task >= len(riga) or indice_categoria >= len(riga):
                raise ValueError(
                    f"tassonomia CSV: riga {n_riga} ha meno colonne dell'intestazione: {riga}"
                )
            tid = riga[indice_task].strip()
            cat = riga[indice_categoria].strip()
            if not tid:
                raise ValueError(f"tassonomia CSV: riga {n_riga} priva di task_id")
            mappa[tid] = cat or CATEGORIA_SCONOSCIUTA
    return mappa


def map_categories(
    records: Iterable[Mapping[str, Any]],
    taxonomy: Mapping[str, str],
    task_id_key: str = "task_id",
    category_key: str = "external_category",
) -> list[dict[str, Any]]:
    """Assegna a ogni record la categoria esterna dalla tassonomia.

    Restituisce una lista di nuove dict (le righe di input non sono modificate).
    Ogni record di output contiene una copia dei campi originali piu'
    ``category_key`` impostato alla categoria mappata, o a
    ``"unknown"`` se il task_id e' mancante o assente dalla tassonomia.

    Nessun fallback silenzioso: ogni record ottiene esattamente una categoria,
    dichiarata esplicitamente.
    """
    mappati: list[dict[str, Any]] = []
    for row in records:
        nuovo = dict(row)
        tid = row.get(task_id_key)
        categoria = CATEGORIA_SCONOSCIUTA
        if tid is not None:
            tid_str = str(tid).strip()
            if tid_str:
                categoria = taxonomy.get(tid_str, CATEGORIA_SCONOSCIUTA)
                if not categoria:
                    categoria = CATEGORIA_SCONOSCIUTA
        nuovo[category_key] = categoria
        mappati.append(nuovo)
    return mappati
