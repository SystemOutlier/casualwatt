# -*- coding: utf-8 -*-
"""
test_source.py — Sorgente dei test universale (Modalità di Input Universale).

CasualWatt NON genera e NON hardcoda test causali: i benchmark (es. MUDILab)
sono prodotti da tool esterni. Questo modulo si limita a "ricevere" i test da
eseguire da due sorgenti:

  A) Dataset esterno CSV  -> load_prompts_from_csv(path)
     * cerca una colonna prompt tra: prompt / text / question / input / query
       (case-insensitive, prime colonne candidate in ordine);
     * legge opzionalmente la ground truth tra: ground_truth / expected_result
       / expected / answer / target / label;
     * se il file ha un'unica colonna senza header riconosciuto, tratta ogni
       riga non vuota come un prompt (CSV mono-colonna "raw");
     * ritorna lista di dict: {"id", "text", "ground_truth"(None se assente),
       "source": "csv"}.

  B) Prompt manuale       -> parse_manual_prompts(text)
     * suddivide l'input dell'utente per riga (supporta \r\n, \n, \r);
     * scarta le righe vuote; ritorna gli stessi dict con source="manual".

  load_test_source(mode, csv_path=None, manual_text=None, fallback_config=True)
     è il punto d'ingresso usato dal motore di benchmark: seleziona la
     sorgente in base alla GUI e, solo in modalità CLI (--no-gui) senza input
     esplicito, degrada ai prompt di default nel config (documentato).

Nessuna eccezione esce dalle funzioni di parsing: errori del file (codifica,
delimiter, colonne mancanti) vengono restituiti come messaggio d'errore nella
seconda posizione della tupla, così la GUI può mostrarlo senza crash.
"""
from __future__ import annotations

import csv as _csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Candidati per la colonna dei prompt (in ordine di priorità)
PROMPT_COLUMN_CANDIDATES = ["prompt", "text", "question", "input", "query"]
# Candidati per la colonna del risultato atteso (opzionale)
GT_COLUMN_CANDIDATES = [
    "ground_truth", "expected_result", "expected", "answer", "target", "label",
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


def make_prompt_items(texts_with_gt: List[Tuple[str, Optional[str]]],
                      source: str, id_prefix: str) -> List[Dict]:
    """Normalizza (testo, ground_truth) in item standard del benchmark."""
    items: List[Dict] = []
    for i, (txt, gt) in enumerate(texts_with_gt, start=1):
        txt = (txt or "").strip()
        if not txt:
            continue
        gt_clean = (gt or "").strip() if isinstance(gt, str) else gt
        items.append(
            {
                "id": f"{id_prefix}-{i:03d}",
                "text": txt,
                "ground_truth": gt_clean if gt_clean not in ("", None) else None,
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

        has_real_header = prompt_idx is not None
        if has_real_header:
            data_rows = rows[1:]
        elif len(header) == 1:
            # mono-colonna senza header riconosciuto: ogni riga è un prompt
            prompt_idx, gt_idx = 0, None
            data_rows = rows
        else:
            # nessuna colonna nota: usa la prima colonna come prompt
            prompt_idx, gt_idx = 0, None
            data_rows = rows[1:] if _looks_like_header(rows[0]) else rows

        for r in data_rows:
            txt = r[prompt_idx] if prompt_idx < len(r) else ""
            gt = r[gt_idx] if (gt_idx is not None and gt_idx < len(r)) else None
            items.append((txt, gt))

        out = make_prompt_items(items, source="csv", id_prefix="csv")
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


# ---------------------------------------------------------------------------
# B) Prompt manuale (textarea della GUI, uno per riga)
# ---------------------------------------------------------------------------
# Separatore opzionale prompt / risposta attesa nel box manuale, es.:
#   Qual è la capitale d'Italia? / Roma
_MANUAL_GT_SEP = " / "


def _split_manual_line(line: str) -> Tuple[str, Optional[str]]:
    """Separa 'prompt / ground_truth' una sola volta (il primo separatore).

    Se il separatore non c'è, la riga intera è il prompt e la GT resta None
    (accuratezza -> N/A). La parte dopo il separatore NON può essa stessa
    contenere altri ' / ': viene presa tutta, spazi allowiti.
    """
    if _MANUAL_GT_SEP in line:
        prompt, gt = line.split(_MANUAL_GT_SEP, 1)
        return prompt.strip(), (gt.strip() or None)
    return line.strip(), None


def parse_manual_prompts(text: str) -> List[Dict]:
    """Uno o più prompt separati da newline; righe vuote ignorate.

    Ogni riga può avere la forma 'prompt / risposta_attesa': se presente il
    separatore ' / ', la seconda metà viene usata come ground truth per il
    calcolo dell'accuratezza; altrimenti l'accuratezza resterà N/A (solo
    metriche energetiche/di latenza/token).
    """
    if not text or not text.strip():
        return []
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    pairs = [_split_manual_line(ln) for ln in lines if ln]
    return make_prompt_items(pairs, source="manual", id_prefix="man")


# ---------------------------------------------------------------------------
# Selettore usato dal motore di benchmark
# ---------------------------------------------------------------------------
def load_test_source(
    mode: str,
    csv_path: Optional[str] = None,
    manual_text: Optional[str] = None,
    fallback_config: bool = True,
) -> Tuple[List[Dict], str]:
    """mode: 'csv' | 'manual' | 'default'.

    Ritorna (items, errore). Con ``fallback_config`` True (uso CLI --no-gui)
    'manual' vuoto o 'csv' fallito degradano ai prompt di config.load_prompts()
    con nota esplicita; con False (uso GUI) l'errore risale alla GUI senza
    sorprese.
    """
    mode = (mode or "default").strip().lower()

    if mode == "csv":
        items, err = load_prompts_from_csv(csv_path)
        if items:
            return items, ""
        if fallback_config:
            return _config_default_items(note=f"CSV non valido ({err}); uso dataset config")
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
