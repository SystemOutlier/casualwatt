# -*- coding: utf-8 -*-
"""
test_source.py — Sorgente dei test universale (Modalità di Input Universale).

CasualWatt NON genera e NON hardcoda test causali: i benchmark (es. MUDILab)
sono prodotti da tool esterni. Questo modulo si limita a "ricevere" i test da
eseguire da sorgenti multiple:

  A) Dataset esterno CSV  -> load_prompts_from_csv(path)
  B) JSON / JSONL         -> load_prompts_from_json(path)
  C) Excel (.xlsx)        -> load_prompts_from_excel(path)
  D) Parquet              -> load_prompts_from_parquet(path)
  E) Hugging Face Datasets-> load_prompts_from_hf(dataset_name, split, ...)
  F) YAML                 -> load_prompts_from_yaml(path)
  G) Prompt manuale       -> parse_manual_prompts(text)

  load_test_source(mode, ...) è il punto d'ingresso usato dal motore di benchmark:
  seleziona la sorgente in base alla GUI/CLI e, solo in modalità CLI (--no-gui)
  senza input esplicito, degrada ai prompt di default nel config.

Nessuna eccezione esce dalle funzioni di parsing: errori del file (codifica,
delimiter, colonne mancanti, dipendenze mancanti) vengono restituiti come
messaggio d'errore nella seconda posizione della tupla, così la GUI può
mostrarlo senza crash.
"""
from __future__ import annotations

import csv as _csv
import json as _json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Candidati per la colonna dei prompt (in ordine di priorità)
PROMPT_COLUMN_CANDIDATES = ["prompt", "text", "question", "input", "query"]
# Candidati per la colonna del risultato atteso (opzionale)
GT_COLUMN_CANDIDATES = [
    "ground_truth", "expected_result", "expected", "answer", "target", "label",
]
# Candidati per la colonna del tipo di risposta (opzionale)
ANSWER_TYPE_COLUMN_CANDIDATES = [
    "answer_type", "type", "response_type",
]


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "_").replace("-", "_")


def _pick_column(fieldnames: List[str], candidates: List[str]) -> Optional[str]:
    """Ritorna il nome reale della prima colonna che matcha un candidato."""
    lowered = {_norm(f): f for f in fieldnames if f is not None}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def make_prompt_items(texts_with_gt: List[Tuple[str, Optional[str], Optional[str]]],
                      source: str, id_prefix: str) -> List[Dict]:
    """Normalizza (testo, ground_truth, answer_type) in item standard del benchmark.
    
    answer_type: "number" | "short_text" | "free_text" | "auto" (default "auto").
    """
    items: List[Dict] = []
    for i, (txt, gt, ans_type) in enumerate(texts_with_gt, start=1):
        txt = (txt or "").strip()
        if not txt:
            continue
        gt_clean = (gt or "").strip() if isinstance(gt, str) else gt
        ans_type_clean = (ans_type or "auto").strip().lower() if isinstance(ans_type, str) else "auto"
        if ans_type_clean not in ("number", "short_text", "free_text", "auto"):
            ans_type_clean = "auto"
        items.append(
            {
                "id": f"{id_prefix}-{i:03d}",
                # L'indice identifica la riga, non il task statistico.
                "task_id": None,
                "text": txt,
                "ground_truth": gt_clean if gt_clean not in ("", None) else None,
                "answer_type": ans_type_clean,
                "source": source,
            }
        )
    return items


# ---------------------------------------------------------------------------
# A) Dataset esterno CSV (output di tool come MUDILab)
# ---------------------------------------------------------------------------
def load_prompts_from_csv(path) -> Tuple[List[Dict], str]:
    """Carica i prompt (ed eventuale ground truth) da un CSV esterno.

    Ritorna (items, errore). ``items`` è vuoto con messaggio esplicativo se
    il file non esiste/non è leggibile/non contiene prompt.
    """
    p = Path(str(path or "").strip().strip('"'))
    if not str(p):
        return [], "nessun file CSV selezionato"
    if not p.exists() or not p.is_file():
        return [], f"file non trovato: {p}"

    raw_text = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            raw_text = p.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
        except Exception as exc:
            return [], f"lettura fallita ({type(exc).__name__}: {exc})"
    if raw_text is None:
        return [], "impossibile decodificare il file (codifiche tentate: utf-8, cp1252)"
    if not raw_text.strip():
        return [], "file CSV vuoto"

    # delimiter: sniffing sulla prima riga (output europei/Excel usano ';')
    first_line = raw_text.splitlines()[0]
    delimiter = _guess_delim(first_line)

    items: List[Dict] = []
    try:
        reader = _csv.reader(raw_text.splitlines(), delimiter=delimiter)
        rows = [r for r in reader if r and any((c or "").strip() for c in r)]
        if not rows:
            return [], "nessuna riga dati nel CSV"

        header = [_norm(c) for c in rows[0]]
        prompt_idx = _idx_of(header, PROMPT_COLUMN_CANDIDATES)
        gt_idx = _idx_of(header, GT_COLUMN_CANDIDATES)
        ans_type_idx = _idx_of(header, ANSWER_TYPE_COLUMN_CANDIDATES)
        task_idx = _idx_of(header, ["task_id"]) if prompt_idx is not None else None

        has_real_header = prompt_idx is not None
        if has_real_header:
            data_rows = rows[1:]
        elif len(header) == 1:
            # mono-colonna senza header riconosciuto: ogni riga è un prompt
            prompt_idx, gt_idx, ans_type_idx = 0, None, None
            data_rows = rows
        else:
            # nessuna colonna nota: usa la prima colonna come prompt
            prompt_idx, gt_idx, ans_type_idx = 0, None, None
            data_rows = rows[1:] if _looks_like_header(rows[0]) else rows

        for r in data_rows:
            txt = r[prompt_idx] if prompt_idx < len(r) else ""
            gt = r[gt_idx] if (gt_idx is not None and gt_idx < len(r)) else None
            ans_type = r[ans_type_idx] if (ans_type_idx is not None and ans_type_idx < len(r)) else None
            items.append((txt, gt, ans_type))

        out = make_prompt_items(items, source="csv", id_prefix="csv")
        task_ids = [
            (r[task_idx].strip() or None)
            if task_idx is not None and task_idx < len(r) else None
            for r in data_rows if prompt_idx < len(r) and r[prompt_idx].strip()
        ]
        identities = {}
        for item, task_id in zip(out, task_ids):
            item["task_id"] = task_id
            if task_id is not None:
                spec = (item["text"], item["ground_truth"], item["answer_type"])
                if task_id in identities and identities[task_id] != spec:
                    return [], f"task_id {task_id!r} identifica contratti diversi"
                identities[task_id] = spec
        if not out:
            return [], "colonna prompt trovata ma tutte le celle sono vuote"
        return out, ""
    except Exception as exc:
        return [], f"parse CSV fallito ({type(exc).__name__}: {exc})"


def _guess_delim(line: str) -> str:
    """Primo delimiter presente tra ; \t , | (virgola come default)."""
    counts = {d: line.count(d) for d in (";", "\t", ",", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _idx_of(normed_header: List[str], candidates: List[str]) -> Optional[int]:
    for cand in candidates:
        if cand in normed_header:
            return normed_header.index(cand)
    return None


def _looks_like_header(cells: List[str]) -> bool:
    joined = " ".join(_norm(c) for c in cells)
    return any(c in joined for c in PROMPT_COLUMN_CANDIDATES + GT_COLUMN_CANDIDATES + ["id"])


def _read_text(path) -> Tuple[Optional[str], str]:
    """Legge un file di testo provando piu' codifiche. Ritorna (testo, errore)."""
    p = Path(str(path or "").strip().strip('"'))
    if not str(p):
        return None, "nessun file selezionato"
    if not p.exists() or not p.is_file():
        return None, f"file non trovato: {p}"
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return p.read_text(encoding=enc), ""
        except (UnicodeDecodeError, LookupError):
            continue
        except Exception as exc:
            return None, f"lettura fallita ({type(exc).__name__}: {exc})"
    return None, "impossibile decodificare il file (codifiche tentate: utf-8, cp1252)"


# ---------------------------------------------------------------------------
# Mapper generico record -> item (condiviso da JSON/Excel/Parquet/YAML/HF)
# ---------------------------------------------------------------------------
def _record_get(rec: Dict, candidates: List[str]) -> Optional[Any]:
    """Primo valore la cui chiave (normalizzata) matcha un candidato."""
    lowered = {_norm(k): v for k, v in rec.items() if k is not None}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def _items_from_records(records: List[Any], source: str,
                        id_prefix: str) -> Tuple[List[Dict], str]:
    """Normalizza una lista di dict (o stringhe) in item standard del benchmark.

    Riusa gli stessi candidati di colonna del CSV, cosi' un dataset esportato
    in uno qualsiasi dei formati strutturati mantiene la stessa semantica.
    Verifica la coerenza di ``task_id`` come nel loader CSV.
    """
    triples: List[Tuple[str, Optional[str], Optional[str]]] = []
    task_ids: List[Optional[str]] = []
    for rec in records:
        if isinstance(rec, str):
            txt, gt, ans, tid = rec, None, None, None
        elif isinstance(rec, dict):
            txt = _record_get(rec, PROMPT_COLUMN_CANDIDATES)
            gt = _record_get(rec, GT_COLUMN_CANDIDATES)
            ans = _record_get(rec, ANSWER_TYPE_COLUMN_CANDIDATES)
            tid = _record_get(rec, ["task_id"])
        else:
            continue
        txt = str(txt).strip() if txt is not None else ""
        if not txt:
            continue
        triples.append((txt, gt, ans))
        task_ids.append(str(tid).strip() or None if tid is not None else None)

    out = make_prompt_items(triples, source=source, id_prefix=id_prefix)
    identities: Dict[str, Tuple] = {}
    for item, tid in zip(out, task_ids):
        item["task_id"] = tid
        if tid is not None:
            spec = (item["text"], item["ground_truth"], item["answer_type"])
            if tid in identities and identities[tid] != spec:
                return [], f"task_id {tid!r} identifica contratti diversi"
            identities[tid] = spec
    if not out:
        return [], "nessun prompt valido nei record (colonna prompt assente o vuota)"
    return out, ""


def _unwrap_container(data: Any) -> Optional[List[Any]]:
    """Estrae una lista di record da un contenitore JSON/YAML.

    Accetta: lista diretta; dict con una lista sotto una chiave nota
    (prompts/data/items/examples/questions/tests); dict che e' esso stesso
    un singolo prompt. Ritorna None se non riconoscibile.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("prompts", "data", "items", "examples", "questions", "tests"):
            if isinstance(data.get(key), list):
                return data[key]
        if _record_get(data, PROMPT_COLUMN_CANDIDATES) is not None:
            return [data]
    return None


# ---------------------------------------------------------------------------
# C) JSON / JSONL
# ---------------------------------------------------------------------------
def load_prompts_from_json(path) -> Tuple[List[Dict], str]:
    """Carica prompt da un file JSON (array/oggetto) o JSONL (una riga = un JSON).

    Ritorna (items, errore). Nessun sollevamento: errori di parse/decodifica
    sono messaggi nella seconda posizione.
    """
    raw, err = _read_text(path)
    if raw is None:
        return [], err
    if not raw.strip():
        return [], "file JSON vuoto"

    records: Optional[List[Any]] = None
    stripped = raw.strip()
    # JSON classico: array o oggetto contenitore
    try:
        data = _json.loads(stripped)
        records = _unwrap_container(data)
    except _json.JSONDecodeError:
        records = None

    # JSONL: una riga = un oggetto JSON (o stringa)
    if records is None:
        recs: List[Any] = []
        for ln in stripped.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                recs.append(_json.loads(ln))
            except _json.JSONDecodeError:
                return [], "parse JSON/JSONL fallito: riga non valida"
        records = recs or None

    if records is None:
        return [], "struttura JSON non riconosciuta (attesa lista di prompt o oggetto con chiave prompts/data/items)"
    return _items_from_records(records, source="json", id_prefix="json")


# ---------------------------------------------------------------------------
# D) Excel (.xlsx) — richiede openpyxl
# ---------------------------------------------------------------------------
def load_prompts_from_excel(path, sheet: Optional[str] = None) -> Tuple[List[Dict], str]:
    """Carica prompt dal primo foglio (o ``sheet``) di un file .xlsx.

    Richiede ``openpyxl``; se assente ritorna un errore con il comando di
    installazione, senza sollevare.
    """
    p = Path(str(path or "").strip().strip('"'))
    if not str(p):
        return [], "nessun file Excel selezionato"
    if not p.exists() or not p.is_file():
        return [], f"file non trovato: {p}"
    try:
        import openpyxl
    except ImportError:
        return [], "Excel richiede openpyxl: pip install openpyxl"
    try:
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
    except Exception as exc:
        return [], f"lettura Excel fallita ({type(exc).__name__}: {exc})"
    if not rows:
        return [], "foglio Excel vuoto"
    header = [str(c) if c is not None else "" for c in rows[0]]
    records = [
        {header[i]: cell for i, cell in enumerate(r) if i < len(header)}
        for r in rows[1:]
    ]
    return _items_from_records(records, source="excel", id_prefix="xls")


# ---------------------------------------------------------------------------
# E) Parquet — richiede pyarrow (o pandas+pyarrow/fastparquet)
# ---------------------------------------------------------------------------
def load_prompts_from_parquet(path) -> Tuple[List[Dict], str]:
    """Carica prompt da un file Parquet. Richiede pyarrow o pandas.

    Se nessuna delle due librerie e' presente ritorna un errore con il
    comando di installazione, senza sollevare.
    """
    p = Path(str(path or "").strip().strip('"'))
    if not str(p):
        return [], "nessun file Parquet selezionato"
    if not p.exists() or not p.is_file():
        return [], f"file non trovato: {p}"
    records: Optional[List[Dict]] = None
    try:
        import pyarrow.parquet as pq
        records = pq.read_table(p).to_pylist()
    except ImportError:
        try:
            import pandas as pd
            records = pd.read_parquet(p).to_dict("records")
        except ImportError:
            return [], "Parquet richiede pyarrow: pip install pyarrow"
        except Exception as exc:
            return [], f"lettura Parquet fallita ({type(exc).__name__}: {exc})"
    except Exception as exc:
        return [], f"lettura Parquet fallita ({type(exc).__name__}: {exc})"
    return _items_from_records(records or [], source="parquet", id_prefix="pq")


# ---------------------------------------------------------------------------
# F) Hugging Face Datasets — richiede datasets
# ---------------------------------------------------------------------------
def load_prompts_from_hf(dataset_name: str, split: str = "test",
                         config_name: Optional[str] = None,
                         column_map: Optional[Dict[str, str]] = None,
                         ) -> Tuple[List[Dict], str]:
    """Carica prompt da un dataset Hugging Face (es. 'mmlu', 'gsm8k').

    ``column_map`` (opz.) mappa nomi canonici -> nomi reali del dataset,
    es. {"prompt": "question", "ground_truth": "answer"}. Senza, si usano i
    candidati standard. Richiede ``datasets``; se assente, errore esplicito.
    """
    name = (dataset_name or "").strip()
    if not name:
        return [], "nessun dataset Hugging Face specificato"
    try:
        import datasets
    except ImportError:
        return [], "Hugging Face richiede datasets: pip install datasets"
    try:
        if config_name:
            ds = datasets.load_dataset(name, config_name, split=split or "test")
        else:
            ds = datasets.load_dataset(name, split=split or "test")
    except Exception as exc:
        return [], f"download dataset HF fallito ({type(exc).__name__}: {exc})"
    records = [dict(r) for r in ds]
    if column_map:
        for rec in records:
            for canon, actual in column_map.items():
                if actual in rec:
                    rec[canon] = rec[actual]
    items, err = _items_from_records(records, source="hf", id_prefix="hf")
    if not items and not err:
        cols = getattr(ds, "column_names", [])
        err = f"nessuna colonna prompt riconosciuta; colonne disponibili: {cols}"
    return items, err


# ---------------------------------------------------------------------------
# G) YAML — richiede PyYAML
# ---------------------------------------------------------------------------
def load_prompts_from_yaml(path) -> Tuple[List[Dict], str]:
    """Carica prompt da un file YAML (lista o oggetto con chiave prompts/data).

    Richiede ``yaml`` (PyYAML); se assente ritorna un errore con il comando
    di installazione, senza sollevare.
    """
    raw, err = _read_text(path)
    if raw is None:
        return [], err
    if not raw.strip():
        return [], "file YAML vuoto"
    try:
        import yaml
    except ImportError:
        return [], "YAML richiede PyYAML: pip install pyyaml"
    try:
        data = yaml.safe_load(raw)
    except Exception as exc:
        return [], f"parse YAML fallito ({type(exc).__name__}: {exc})"
    records = _unwrap_container(data)
    if records is None:
        return [], "struttura YAML non riconosciuta (attesa lista di prompt o oggetto con chiave prompts/data/items)"
    return _items_from_records(records, source="yaml", id_prefix="yml")


# ---------------------------------------------------------------------------
# B) Prompt manuale (textarea della GUI, uno per riga)
# ---------------------------------------------------------------------------
# Separatore opzionale prompt / risposta attesa nel box manuale, es.:
#   Qual è la capitale d'Italia? / Roma
_MANUAL_GT_SEP = " / "


def _split_manual_line(line: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Separa 'prompt / ground_truth / answer_type' (fino a 2 separatori).
    
    Se il separatore non c'è, la riga intera è il prompt e GT/answer_type restano None.
    Supporta fino a 3 parti: prompt, ground_truth, answer_type.
    """
    parts = line.split(_MANUAL_GT_SEP)
    if len(parts) == 1:
        return parts[0].strip(), None, None
    elif len(parts) == 2:
        return parts[0].strip(), (parts[1].strip() or None), None
    else:  # len >= 3
        prompt = parts[0].strip()
        gt = (parts[1].strip() or None)
        ans_type = (parts[2].strip() or None)
        return prompt, gt, ans_type


def parse_manual_prompts(text: str) -> List[Dict]:
    """Uno o più prompt separati da newline; righe vuote ignorate.

    Ogni riga può avere la forma 'prompt / risposta_attesa / tipo_risposta':
    se presente il separatore ' / ', la seconda metà viene usata come ground truth
    e la terza come answer_type; altrimenti l'accuratezza resterà N/A.
    """
    if not text or not text.strip():
        return []
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    triples = [_split_manual_line(ln) for ln in lines if ln]
    return make_prompt_items(triples, source="manual", id_prefix="man")


# ---------------------------------------------------------------------------
# Selettore usato dal motore di benchmark
# ---------------------------------------------------------------------------
def load_test_source(
    mode: str,
    csv_path: Optional[str] = None,
    manual_text: Optional[str] = None,
    fallback_config: bool = True,
    file_path: Optional[str] = None,
    hf_dataset: Optional[str] = None,
    hf_split: str = "test",
    hf_config: Optional[str] = None,
    hf_column_map: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict], str]:
    """mode: 'csv' | 'json' | 'excel' | 'parquet' | 'yaml' | 'hf' | 'manual' | 'default'.

    Ritorna (items, errore). Con ``fallback_config`` True (uso CLI --no-gui)
    una sorgente vuota o fallita degrada ai prompt di config.load_prompts()
    con nota esplicita; con False (uso GUI) l'errore risale alla GUI senza
    sorprese.

    Per i formati file (json/excel/parquet/yaml) il percorso e' ``file_path``
    o, in sua assenza, ``csv_path`` (riuso del campo percorso della GUI).
    Per 'hf' si usano ``hf_dataset``/``hf_split``/``hf_config``/``hf_column_map``.
    """
    mode = (mode or "default").strip().lower()
    path = file_path or csv_path

    _file_loaders = {
        "csv": lambda: load_prompts_from_csv(path),
        "json": lambda: load_prompts_from_json(path),
        "jsonl": lambda: load_prompts_from_json(path),
        "excel": lambda: load_prompts_from_excel(path),
        "xlsx": lambda: load_prompts_from_excel(path),
        "parquet": lambda: load_prompts_from_parquet(path),
        "yaml": lambda: load_prompts_from_yaml(path),
        "yml": lambda: load_prompts_from_yaml(path),
    }
    if mode in _file_loaders:
        items, err = _file_loaders[mode]()
        if items:
            return items, ""
        if fallback_config:
            return _config_default_items(note=f"sorgente {mode} non valida ({err}); uso dataset config")
        return [], err

    if mode in ("hf", "huggingface"):
        items, err = load_prompts_from_hf(
            hf_dataset or "", split=hf_split, config_name=hf_config,
            column_map=hf_column_map)
        if items:
            return items, ""
        if fallback_config:
            return _config_default_items(note=f"dataset HF non valido ({err}); uso dataset config")
        return [], err

    if mode == "manual":
        items = parse_manual_prompts(manual_text or "")
        if items:
            return items, ""
        if fallback_config:
            return _config_default_items(note="nessun prompt manuale inserito; uso dataset config")
        return [], "nessun prompt manuale: digita o incolla almeno un prompt"

    # modalità 'default' (CLI storica) — dataset in config/dataset
    try:
        import config

        cfg_items = config.load_prompts()
        out = []
        for i, it in enumerate(cfg_items, start=1):
            if isinstance(it, str):
                out.append({"id": f"cfg-{i:03d}", "text": it, "ground_truth": None, "source": "config"})
            else:
                out.append({
                    "id": it.get("id", f"cfg-{i:03d}"),
                    "task_id": it.get("task_id"),
                    "text": it.get("text", ""),
                    "ground_truth": it.get("ground_truth"),
                    "source": "config",
                })
        out = [o for o in out if o["text"]]
        if out:
            return out, ""
    except Exception:
        pass
    return [], "dataset di default non disponibile"


def _config_default_items(note: str) -> Tuple[List[Dict], str]:
    items, err = load_test_source("default", fallback_config=False)
    if items:
        for it in items:
            it.setdefault("notes_extra", note)
    return items, err
