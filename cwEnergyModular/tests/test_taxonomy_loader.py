# -*- coding: utf-8 -*-
"""Test per taxonomy_loader.py (Priorita' 9).

Questi test verificano:
- caricamento JSON da lista di oggetti e da dizionario
- caricamento CSV con intestazione task_id,category
- task_id mancante o non presente nella tassonomia -> categoria "unknown"
- file inesistente solleva FileNotFoundError
- JSON malformed solleva ValueError dichiarato
- CSV senza colonne richieste solleva ValueError dichiarato
- map_categories restituisce nuove dict senza modificare le righe di input
- ogni record ottiene esattamente una categoria (nessun fallback silenzioso)
- il modulo importa solo stdlib (isolamento dal percorso di misura)
"""

import ast
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from taxonomy_loader import (  # noqa: E402
    CATEGORIA_SCONOSCIUTA,
    load_taxonomy_from_csv,
    load_taxonomy_from_json,
    map_categories,
)


def _scrivi_json(tmp_path, nome, oggetto):
    p = tmp_path / nome
    p.write_text(json.dumps(oggetto, ensure_ascii=False), encoding="utf-8")
    return p


def _scrivi_csv(tmp_path, nome, righe):
    import csv

    p = tmp_path / nome
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        for riga in righe:
            writer.writerow(riga)
    return p


def test_load_taxonomy_json_lista_oggetti(tmp_path):
    """JSON lista di oggetti: mappatura task_id -> categoria."""
    p = _scrivi_json(tmp_path, "t.json", [
        {"task_id": "t1", "category": "factual"},
        {"task_id": "t2", "category": "reasoning"},
    ])
    mappa = load_taxonomy_from_json(p)
    assert mappa == {"t1": "factual", "t2": "reasoning"}


def test_load_taxonomy_json_dizionario(tmp_path):
    """JSON dizionario: chiave = task_id, valore = categoria."""
    p = _scrivi_json(tmp_path, "t.json", {"t1": "factual", "t2": "reasoning"})
    mappa = load_taxonomy_from_json(p)
    assert mappa == {"t1": "factual", "t2": "reasoning"}


def test_load_taxonomy_json_task_id_vuoto_errore(tmp_path):
    """Elemento senza task_id solleva ValueError dichiarato."""
    p = _scrivi_json(tmp_path, "t.json", [{"category": "factual"}])
    with pytest.raises(ValueError, match="privo di task_id"):
        load_taxonomy_from_json(p)


def test_load_taxonomy_json_formato_sconosciuto_errore(tmp_path):
    """JSON che non e' lista né dizionario solleva ValueError dichiarato."""
    p = tmp_path / "t.json"
    p.write_text("42", encoding="utf-8")
    with pytest.raises(ValueError, match="formato non riconosciuto"):
        load_taxonomy_from_json(p)


def test_load_taxonomy_json_file_inesistente_errore(tmp_path):
    """File assente solleva FileNotFoundError dichiarato."""
    with pytest.raises(FileNotFoundError):
        load_taxonomy_from_json(tmp_path / "inesistente.json")


def test_load_taxonomy_csv_intestazione(tmp_path):
    """CSV con intestazione task_id,category viene caricato correttamente."""
    p = _scrivi_csv(tmp_path, "t.csv", [
        ["task_id", "category"],
        ["t1", "factual"],
        ["t2", "reasoning"],
    ])
    mappa = load_taxonomy_from_csv(p)
    assert mappa == {"t1": "factual", "t2": "reasoning"}


def test_load_taxonomy_csv_colonne_aggiuntive_ignorate(tmp_path):
    """Colonne oltre task_id e category vengono ignorate."""
    p = _scrivi_csv(tmp_path, "t.csv", [
        ["task_id", "category", "metadata"],
        ["t1", "factual", "x"],
        ["t2", "reasoning", "y"],
    ])
    mappa = load_taxonomy_from_csv(p)
    assert mappa == {"t1": "factual", "t2": "reasoning"}


def test_load_taxonomy_csv_task_id_vuoto_errore(tmp_path):
    """Riga senza task_id solleva ValueError dichiarato."""
    p = _scrivi_csv(tmp_path, "t.csv", [
        ["task_id", "category"],
        ["", "factual"],
    ])
    with pytest.raises(ValueError, match="priva di task_id"):
        load_taxonomy_from_csv(p)


def test_load_taxonomy_csv_colonne_mancanti_errore(tmp_path):
    """Intestazione senza task_id o category solleva ValueError dichiarato."""
    p = _scrivi_csv(tmp_path, "t.csv", [
        ["id", "nome"],
        ["t1", "factual"],
    ])
    with pytest.raises(ValueError, match="intestazione deve contenere"):
        load_taxonomy_from_csv(p)


def test_load_taxonomy_csv_file_inesistente_errore(tmp_path):
    """File assente solleva FileNotFoundError dichiarato."""
    with pytest.raises(FileNotFoundError):
        load_taxonomy_from_csv(tmp_path / "inesistente.csv")


def test_map_categories_assegna_categoria_mappata():
    """Record con task_id presente nella tassonomia ottiene la categoria esterna."""
    taxonomy = {"t1": "factual", "t2": "reasoning"}
    records = [
        {"task_id": "t1", "energy": 1.0},
        {"task_id": "t2", "energy": 2.0},
    ]
    out = map_categories(records, taxonomy)
    assert out[0]["external_category"] == "factual"
    assert out[1]["external_category"] == "reasoning"


def test_map_categories_task_id_assente_diventa_unknown():
    """Task_id non in tassonomia -> categoria "unknown" (nessun fallback silenzioso)."""
    taxonomy = {"t1": "factual"}
    records = [{"task_id": "t99", "energy": 1.0}]
    out = map_categories(records, taxonomy)
    assert out[0]["external_category"] == CATEGORIA_SCONOSCIUTA


def test_map_categories_task_id_mancante_diventa_unknown():
    """Record senza task_id -> categoria "unknown"."""
    taxonomy = {"t1": "factual"}
    records = [{"energy": 1.0}]
    out = map_categories(records, taxonomy)
    assert out[0]["external_category"] == CATEGORIA_SCONOSCIUTA


def test_map_categories_non_modifica_righe_input():
    """map_categories restituisce nuove dict; le righe di input restano intatte."""
    taxonomy = {"t1": "factual"}
    record = {"task_id": "t1", "energy": 1.0}
    originale = dict(record)
    out = map_categories([record], taxonomy)
    assert record == originale
    assert out[0]["task_id"] == "t1"
    assert out[0]["external_category"] == "factual"
    assert out[0]["energy"] == 1.0


def test_map_categories_categoria_vuota_diventa_unknown():
    """Categoria vuota nella tassonomia -> "unknown", non stringa vuota."""
    taxonomy = {"t1": ""}
    records = [{"task_id": "t1"}]
    out = map_categories(records, taxonomy)
    assert out[0]["external_category"] == CATEGORIA_SCONOSCIUTA


def test_map_categories_task_id_key_personalizzata():
    """task_id_key permette di usare una chiave diversa da 'task_id'."""
    taxonomy = {"abc-1": "coding"}
    records = [{"id_esterno": "abc-1"}]
    out = map_categories(records, taxonomy, task_id_key="id_esterno")
    assert out[0]["external_category"] == "coding"


def test_map_categories_category_key_personalizzata():
    """category_key permette di scegliere il nome del campo di output."""
    taxonomy = {"t1": "factual"}
    records = [{"task_id": "t1"}]
    out = map_categories(records, taxonomy, category_key="cat_esterna")
    assert out[0]["cat_esterna"] == "factual"
    assert "external_category" not in out[0]


def test_nessuna_colonna_csv_nuova():
    """Importare taxonomy_loader non tocca lo schema P5 (CSV_COLUMNS invariato)."""
    from casualwatt_csv_export import CSV_COLUMNS  # noqa: E402

    n_before = len(CSV_COLUMNS)
    importlib.import_module("taxonomy_loader")
    n_after = len(CSV_COLUMNS)
    assert n_before == n_after


def test_modulo_importa_solo_stdlib():
    """taxonomy_loader importa solo moduli della libreria standard."""
    percorso = Path(__file__).resolve().parents[1] / "taxonomy_loader.py"
    albero = ast.parse(percorso.read_text(encoding="utf-8"))
    moduli_importati = set()
    for nodo in ast.walk(albero):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                moduli_importati.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                moduli_importati.add(nodo.module.split(".")[0])
    stdlib_atteso = {
        "csv", "json", "pathlib", "typing", "__future__",
    }
    esterni = moduli_importati - stdlib_atteso
    assert not esterni, f"Import non stdlib trovati: {esterni}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
