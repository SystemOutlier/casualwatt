# -*- coding: utf-8 -*-
"""I loader di sorgente test per i formati strutturati (JSON/JSONL, Excel,
Parquet, YAML, Hugging Face) normalizzano gli stessi item del CSV.

Perche' esiste. La "Modalita' di Input Universale" riceve i benchmark da tool
esterni: finche' l'unico formato era il CSV, un dataset esportato in JSON o
Parquet non era caricabile e l'utente doveva riconvertirlo a mano. Questi test
bloccano il contratto condiviso dai nuovi loader:

  1. **stessa semantica del CSV**: i candidati di colonna (prompt/text/...,
     ground_truth/..., answer_type, task_id) valgono identici in ogni formato,
     cosi' un dataset non cambia significato cambiando contenitore;
  2. **nessuna eccezione verso la GUI**: file assente, parse rotto o dipendenza
     mancante producono ``(items=[], errore)`` con un messaggio azionabile
     (es. ``pip install ...``), mai un traceback;
  3. **coerenza di task_id**: come nel CSV, lo stesso task_id non puo'
     identificare due contratti (testo/ground_truth/answer_type) diversi,
     perche' il bootstrap a cluster di P4.12 lo usa come unita' statistica.

I percorsi felici Excel/Parquet/YAML sono guardati da ``importorskip``: girano
solo dove la dipendenza e' installata. Il ramo "dipendenza assente" e' invece
esercitato sempre, simulando l'ImportError, perche' e' il comportamento che la
GUI deve mostrare su una macchina senza le librerie opzionali.
"""

import json
import sys

import pytest

import test_source as ts


# ---------------------------------------------------------------------------
# JSON / JSONL (stdlib: sempre eseguiti)
# ---------------------------------------------------------------------------
def test_json_array_di_dict_mappa_come_csv(tmp_path):
    """Un array JSON di dict produce gli stessi item del CSV: prompt, GT,
    answer_type e task_id letti dai candidati standard, source='json'."""
    data = [
        {"prompt": "Q1", "ground_truth": "A1", "answer_type": "short_text", "task_id": "t1"},
        {"text": "Q2"},
    ]
    p = tmp_path / "d.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert err == ""
    assert len(items) == 2
    assert items[0]["text"] == "Q1"
    assert items[0]["ground_truth"] == "A1"
    assert items[0]["answer_type"] == "short_text"
    assert items[0]["task_id"] == "t1"
    assert items[0]["source"] == "json"
    assert items[1]["ground_truth"] is None


def test_json_lista_di_stringhe(tmp_path):
    """Una lista JSON di sole stringhe e' un dataset mono-colonna: ogni
    stringa diventa un prompt senza ground truth (accuratezza -> N/A)."""
    p = tmp_path / "s.json"
    p.write_text(json.dumps(["Q1", "Q2", "  "]), encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert err == ""
    assert [i["text"] for i in items] == ["Q1", "Q2"]


def test_json_oggetto_contenitore(tmp_path):
    """Un oggetto JSON con chiave 'prompts' (o data/items) viene scartato come
    contenitore e si legge la lista interna, non l'oggetto come singolo prompt."""
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"prompts": [{"question": "Q1", "answer": "A1"}]}), encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert err == ""
    assert len(items) == 1
    assert items[0]["text"] == "Q1"
    assert items[0]["ground_truth"] == "A1"


def test_jsonl_una_riga_un_record(tmp_path):
    """Il JSONL (una riga = un oggetto JSON) e' riconosciuto quando il parse
    dell'intero file fallisce: ogni riga valida diventa un item."""
    p = tmp_path / "d.jsonl"
    p.write_text('{"prompt": "Q1"}\n{"prompt": "Q2", "ground_truth": "A2"}\n', encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert err == ""
    assert len(items) == 2
    assert items[1]["ground_truth"] == "A2"


def test_json_rotto_ritorna_errore_non_eccezione(tmp_path):
    """Un file non parsabile come JSON ne' come JSONL ritorna ([], errore):
    la GUI mostra il messaggio invece di crashare."""
    p = tmp_path / "bad.json"
    p.write_text("{questo non e' json", encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert items == []
    assert err


def test_json_task_id_incoerente_rifiutato(tmp_path):
    """Lo stesso task_id con due contratti diversi e' un errore: il bootstrap
    a cluster (P4.12) userebbe un'unita' statistica ambigua."""
    data = [
        {"prompt": "Q1", "task_id": "t"},
        {"prompt": "Q2-diverso", "task_id": "t"},
    ]
    p = tmp_path / "dup.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    items, err = ts.load_prompts_from_json(p)
    assert items == []
    assert "task_id" in err


# ---------------------------------------------------------------------------
# Dispatcher load_test_source
# ---------------------------------------------------------------------------
def test_dispatcher_json_via_file_path_e_csv_path(tmp_path):
    """Il dispatcher accetta il percorso sia come file_path sia come csv_path
    (riuso del campo percorso della GUI) e instrada al loader JSON."""
    p = tmp_path / "d.json"
    p.write_text(json.dumps([{"prompt": "Q1"}]), encoding="utf-8")
    a, ea = ts.load_test_source("json", file_path=str(p), fallback_config=False)
    b, eb = ts.load_test_source("json", csv_path=str(p), fallback_config=False)
    assert ea == eb == ""
    assert len(a) == len(b) == 1


def test_file_assente_ritorna_errore_per_ogni_formato(tmp_path):
    """Un percorso inesistente produce ([], errore) in tutti i formati file,
    senza sollevare: e' il contratto che la GUI usa per il messaggio a video."""
    missing = str(tmp_path / "non_esiste")
    for mode in ("csv", "json", "excel", "parquet", "yaml"):
        items, err = ts.load_test_source(mode, file_path=missing, fallback_config=False)
        assert items == []
        assert err


def test_hf_nome_vuoto_ritorna_errore():
    """Senza nome dataset il loader HF non tenta il download e ritorna un
    errore esplicito (la GUI non deve lanciare una richiesta a vuoto)."""
    items, err = ts.load_prompts_from_hf("")
    assert items == []
    assert err


# ---------------------------------------------------------------------------
# Dipendenze opzionali assenti: errore azionabile, mai eccezione
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mode,lib,pip", [
    ("excel", "openpyxl", "openpyxl"),
    ("parquet", "pyarrow", "pyarrow"),
    ("yaml", "yaml", "pyyaml"),
    ("hf", "datasets", "datasets"),
])
def test_dipendenza_assente_ritorna_pip_install(tmp_path, monkeypatch, mode, lib, pip):
    """Con la libreria opzionale assente il loader ritorna un messaggio che
    nomina il comando di installazione, senza sollevare ImportError."""
    # sys.modules[lib]=None forza ImportError al prossimo import della libreria
    monkeypatch.setitem(sys.modules, lib, None)
    if mode == "hf":
        items, err = ts.load_prompts_from_hf("mmlu")
    else:
        p = tmp_path / f"d.{mode}"
        p.write_text("x", encoding="utf-8")
        items, err = ts.load_test_source(mode, file_path=str(p), fallback_config=False)
    assert items == []
    assert f"pip install {pip}" in err


# ---------------------------------------------------------------------------
# Percorsi felici dove la dipendenza e' installata
# ---------------------------------------------------------------------------
def test_excel_happy_path(tmp_path):
    """Con openpyxl installato, il primo foglio .xlsx viene letto con gli
    stessi candidati di colonna del CSV."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["prompt", "ground_truth", "task_id"])
    ws.append(["Q1", "A1", "t1"])
    ws.append(["Q2", None, None])
    p = tmp_path / "d.xlsx"
    wb.save(p)
    items, err = ts.load_prompts_from_excel(p)
    assert err == ""
    assert len(items) == 2
    assert items[0]["ground_truth"] == "A1"
    assert items[0]["task_id"] == "t1"


def test_yaml_happy_path(tmp_path):
    """Con PyYAML installato, una lista YAML di dict produce item standard."""
    pytest.importorskip("yaml")
    p = tmp_path / "d.yaml"
    p.write_text("- prompt: Q1\n  ground_truth: A1\n- prompt: Q2\n", encoding="utf-8")
    items, err = ts.load_prompts_from_yaml(p)
    assert err == ""
    assert len(items) == 2
    assert items[0]["ground_truth"] == "A1"


def test_parquet_happy_path(tmp_path):
    """Con pyarrow installato, un Parquet viene letto e normalizzato come CSV."""
    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq
    t = pa.table({"prompt": ["Q1", "Q2"], "ground_truth": ["A1", None]})
    p = tmp_path / "d.parquet"
    pq.write_table(t, p)
    items, err = ts.load_prompts_from_parquet(p)
    assert err == ""
    assert len(items) == 2
    assert items[0]["ground_truth"] == "A1"