#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s_epi_phase.py -- estrazione di s_EPI per fase e associazione a s (P6.6).

Cosa fa, e cosa non fa.  Legge i bucket da minuto di SRUM (gia' esportati con
``powercfg /srumutil``), somma ``CPUEnergyConsumption`` dell'albero del motore
e di tutte le voci della stessa fase, e produce per ogni fase:

    s_EPI = sum(CPUEnergyConsumption degli AppId dell'albero) /
            sum(CPUEnergyConsumption di tutte le voci della fase)

Poi associa a ogni fase la quota ``s`` prodotta dal run (``d_ollama`` e
``d_busy`` della riga, oppure ``s`` dichiarata), calcola

    d = s - s_EPI
    r = 2 * (s - s_EPI) / (s + s_EPI)      differenza relativa simmetrica

e, SOLO se il piano porta una banda gia' congelata, dice se la fase e' dentro.
Se la banda manca, ``in_band`` resta nullo: l'harness non inventa soglie.

Non avvia esperimenti e non tocca il percorso energetico di produzione.  Il
solo comando che scrive sul sistema e' ``--capture-to`` (chiama
``powercfg /srumutil``, richiede amministratore); e' separato dall'analisi e
non viene eseguito dai test.

Albero: nomi esatti ``ollama.exe``, ``llama-server.exe``, ``ollama app.exe``,
confrontati sul basename dell'AppId.  Il needle ``"ollama"`` non va usato:
vede 0,0011 invece di 0,7361 (``srum_emi_cross_20261023_analisi.md:158-162``).

Unita' e tempo: SRUM esporta millijoule e ``TimeStamp`` in UTC naive
(``srum.py:26-41``).  Le fasi nel piano sono UTC naive.  I bucket da minuto
possono arrivare in due righe complementari e vengono compattati in record
orari ai boundary: le righe con ``TimeInMSec`` oltre 70 s sono scartate come
roll-up, la deduplica e' per firma esatta.

Bucket di bordo (P6.6).  Un bucket che attraversa un bordo non viene ne'
ripartito ne' sommato — ripartirlo assumerebbe una distribuzione uniforme del
tempo dentro il bucket — viene escluso e dichiarato con ``bucket_di_bordo:N``;
``window_strict`` dice se la finestra e' esattamente integrale.  Un bordo non
blocca il verdetto da solo: gli estremi della fase vengono dalle letture ai
bordi, non dai confini dei minuti SRUM, quindi un bucket di bordo c'e' quasi
sempre e bloccare su quello vorrebbe dire non valutare nessuna fase reale.  La
conseguenza — ``s`` sulla finestra intera, ``s_EPI`` sulla sola porzione
coperta da bucket interi — sta nel campo e nella tabella di copertura, e la
quantificano le fasi di sensibilita' al bordo del pre-pilota.  Il verdetto manca
invece per le condizioni sostanziali elencate in ``BLOCKING_FLAGS``.  Il
``TimeInMSec`` e' per processo, quindi un bucket corto non e' una finestra
incompleta; la completezza si controlla invece sulla *presenza* dell'albero in
ogni minuto della fase.  Sotto i 5 minuti la fase non si valuta.

Uso:
  py s_epi_phase.py --plan fasi.json --dump dump_fase1.csv --dump dump_fase2.csv
  py s_epi_phase.py --plan fasi.json --buckets bucket_normalizzati.csv
  py s_epi_phase.py --plan fasi.json --dump d1.csv --archive-dir sr_emi_2026/
  py s_epi_phase.py --selftest
  py s_epi_phase.py --capture-to dump.csv          # powercfg, admin, non test

Formato del piano (JSON):
{
  "campaign_id": "...", "ollama_version": "...", "model_digest": "sha256:...",
  "band": null,                       # oppure {"abs": 0.0, "rel": 0.0}
  "done_reason_expected": "length",   # facoltativo: se manca, non si confronta
  "phases": [
    {"phase_id": "c1-r1", "config_id": "c1", "replica": 1,
     "t_start_utc": "2026-10-25T10:00:00", "t_end_utc": "2026-10-25T10:06:00",
     "d_ollama_s": 99.28, "d_busy_s": 119.28, "s_source": "csv:direct",
     "done_reason": "length",
     "engine_tree_changed": false, "exclusion": ""}
  ]
}

``engine_tree_changed`` e' un ingresso del piano, non un valore che questo
harness sa calcolare: lo produce il runner con le identita' ``(pid,
create_time)`` lette ai due bordi (P5, P6.5).  Finche' P5 non lo emette, il
piano lo dichiara a mano e la riga lo riporta.

La banda e' una decisione del protocollo (P6.6), non dell'harness: passarla
qui significa che e' gia' stata congelata e committata prima del run.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import shutil
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import srum  # noqa: E402  (load offline; flush solo in --capture-to)

#: nomi esatti dei processi dell'albero del motore (P6.6)
TREE_EXE = ("ollama.exe", "llama-server.exe", "ollama app.exe")
#: pseudo-AppId con cui Windows espone i domini RAPL: CPUEnergyConsumption = 0
SRUM_EMI_PREFIX = "emi_rapl_"
#: oltre questa soglia una riga e' un roll-up orario, non un bucket da minuto
MAX_BUCKET_MS = 70_000
#: regola documentata: almeno 5 bucket da ~1 min per fase
MIN_BUCKETS_PER_PHASE = 5


# ---------------------------------------------------------------------------
# bucket
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Bucket:
    app_id: str
    ts_utc: _dt.datetime
    ms: float
    cpu_mj: float
    emi_mj: float
    tot_mj: float

    @property
    def signature(self) -> Tuple:
        return (self.app_id, self.ts_utc.isoformat(), round(self.ms),
                round(self.cpu_mj, 3), round(self.emi_mj, 3),
                round(self.tot_mj, 3))


def _parse_utc(text: str) -> Optional[_dt.datetime]:
    """ISO naive o con suffisso Z: la base di SRUM e' UTC senza fuso."""
    s = (text or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1]
    try:
        t = _dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is not None:
        t = t.astimezone(_dt.timezone.utc).replace(tzinfo=None)
    return t


def _basename(app_id: str) -> str:
    name = (app_id or "").strip().replace("/", "\\").rsplit("\\", 1)[-1]
    return name.casefold()


def is_tree_app(app_id: str, tree: Sequence[str] = TREE_EXE) -> bool:
    """L'AppId appartiene all'albero del motore, per nome esatto."""
    return _basename(app_id) in {t.casefold() for t in tree}


def buckets_from_dump(path: Path) -> List[Bucket]:
    """Bucket da minuto di un dump SRUM, senza deduplica (fa ``dedup``).

    Scarta i roll-up orari (``TimeInMSec`` > 70 s) e le righe senza timestamp.
    Tiene le righe complementari dello stesso minuto: filtrarle perderebbe
    energia (``srum.py:35-38``).  La deduplica sta in un posto solo, cosi' il
    conteggio delle righe scartate e' quello reale e non zero per costruzione.
    """
    snap = srum.load(path)
    out: List[Bucket] = []
    for r in snap.rows:
        ms = snap._f(r, "TimeInMSec")
        if not (0 < ms <= MAX_BUCKET_MS):
            continue
        ts = snap._ts(r)
        if ts is None:
            continue
        out.append(Bucket(
            app_id=(r.get("AppId") or "?").strip(),
            ts_utc=ts,
            ms=float(ms),
            cpu_mj=snap._f(r, "CPUEnergyConsumption"),
            emi_mj=snap._f(r, "EmiEnergyConsumption"),
            tot_mj=snap._f(r, "TotalEnergyConsumption"),
        ))
    out.sort(key=lambda b: (b.ts_utc, b.app_id))
    return out


def buckets_from_csv(path: Path) -> List[Bucket]:
    """Bucket gia' normalizzati: app_id, timestamp_utc, ms, cpu_mj, emi_mj, tot_mj."""
    out: List[Bucket] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ts = _parse_utc(row.get("timestamp_utc") or "")
            if ts is None:
                continue
            out.append(Bucket(
                app_id=(row.get("app_id") or "?").strip(),
                ts_utc=ts,
                ms=float(row.get("ms") or 0.0),
                cpu_mj=float(row.get("cpu_mj") or 0.0),
                emi_mj=float(row.get("emi_mj") or 0.0),
                tot_mj=float(row.get("tot_mj") or 0.0),
            ))
    out.sort(key=lambda b: (b.ts_utc, b.app_id))
    return out


def dedup(buckets: Iterable[Bucket]) -> List[Bucket]:
    seen, out = set(), []
    for b in buckets:
        if b.signature in seen:
            continue
        seen.add(b.signature)
        out.append(b)
    return out


def choose_phase_buckets(
    buckets: Sequence[Bucket], t0: _dt.datetime, t1: _dt.datetime,
) -> Tuple[List[Bucket], List[Bucket]]:
    """Bucket interamente contenuti nella fase, e bucket che la attraversano.

    Un bucket e' *dentro* se il suo intervallo ``[ts, ts + ms)`` sta in
    ``[t0, t1]``: contribuisce per intero, senza riparto.  Un bucket che
    attraversa un bordo non viene ne' ripartito ne' sommato alla fase — il
    tempo dentro il bucket non e' distribuito uniformemente e ripartirlo
    sarebbe un'assunzione — viene restituito a parte: la fase non ha una
    finestra integra e il chiamante lo dichiara (P6.6, "finestra integra").
    """
    inside, boundary = [], []
    for b in buckets:
        end = b.ts_utc + _dt.timedelta(milliseconds=b.ms)
        if t0 <= b.ts_utc and end <= t1:
            inside.append(b)
        elif b.ts_utc < t1 and end > t0:
            boundary.append(b)
    return inside, boundary


def minute_coverage(
    buckets: Sequence[Bucket],
) -> Tuple[List[_dt.datetime], List[_dt.datetime]]:
    """Minuti distinti nella fase, e quali di essi hanno una riga dell'albero.

    ``TimeInMSec`` e' per processo: un bucket corto di un'app che ha girato
    pochi secondi e' il suo tempo reale, non una finestra incompleta.  Per
    questo la completezza non si giudica dai millisecondi; si giudica dalla
    presenza: l'albero deve avere una riga in ogni minuto della fase, altrimenti
    il numeratore di ``s_EPI`` non copre la stessa finestra di ``s``.
    """
    minutes = sorted({b.ts_utc for b in buckets})
    tree = {b.ts_utc for b in buckets if is_tree_app(b.app_id)}
    return minutes, [t for t in minutes if t in tree]


# ---------------------------------------------------------------------------
# s_EPI
# ---------------------------------------------------------------------------
def s_epi_of(buckets: Sequence[Bucket]) -> Dict[str, object]:
    """Numeratore, denominatore e quota.  Nessun clamp, nessun riempimento."""
    tree: List[Bucket] = []
    den = 0.0
    for b in buckets:
        if _basename(b.app_id).startswith(SRUM_EMI_PREFIX):
            continue                      # pseudo-AppId RAPL: CPU = 0
        den += b.cpu_mj
        if is_tree_app(b.app_id):
            tree.append(b)
    num = sum(b.cpu_mj for b in tree)
    return {
        "tree_cpu_j": round(num / 1000.0, 6),
        "total_cpu_j": round(den / 1000.0, 6),
        "s_epi": (num / den) if den > 0 else None,
        "tree_app_ids": sorted({b.app_id for b in tree}),
        "n_apps": len({b.app_id for b in buckets}),
    }


#: condizioni sostanziali che tolgono il verdetto: la fase non e' la condizione
#: dichiarata o non misura un rapporto fra due quote sulla stessa porzione di
#: finestra.  ``bucket_di_bordo`` NON e' fra queste: il bucket che attraversa un
#: bordo viene escluso dal calcolo (``choose_phase_buckets``), il suo conteggio
#: resta nel campo ``boundary_buckets`` e ``window_strict`` dice se la finestra
#: e' esattamente integrale.  Gli estremi della fase vengono dalle letture ai
#: bordi e non dai confini dei minuti SRUM: quasi ogni fase reale ha almeno un
#: bucket di bordo, e trattarlo come bloccante vorrebbe dire non valutare nessuna
#: fase.  Il costo della finestra non identica (``s`` intera, ``s_EPI`` sui soli
#: bucket interi) si dichiara e si quantifica con la sensibilita' al bordo.
BLOCKING_FLAGS = (
    "finestra_non_valida", "nessun_bucket", "meno_di_5_bucket",
    "engine_tree_changed", "denominatore_nullo", "albero_a_zero",
    "s_fuori_da_0_1", "s_assente",
)
BLOCKING_PREFIXES = (
    "esclusione_dichiarata:", "minuto_senza_albero:", "done_reason:",
)


def is_blocking(flags: Sequence[str]) -> bool:
    """Vero se almeno un flag e' una condizione sostanziale, non un conteggio."""
    return any(f in BLOCKING_FLAGS or f.startswith(BLOCKING_PREFIXES)
               for f in flags)


def quality_flags(
    phase: Dict[str, object], inside: Sequence[Bucket], boundary: Sequence[Bucket],
    s_val: Optional[float] = None,
    expected_done_reason: Optional[str] = None,
) -> List[str]:
    """Motivi per cui la fase va dichiarata, con il proprio ingresso se conteggio.

    Ogni flag porta il proprio ingresso quando e' un conteggio.  Nessuna
    soglia nuova: ``MIN_BUCKETS_PER_PHASE`` viene dalla convenzione gia'
    documentata in ``srum_emi_cross.py``, ``s`` e' limitata a [0,1] da P6.6,
    ``done_reason`` si confronta con quello dichiarato nel piano (se il piano
    non lo dichiara, non si confronta).  Non tutti i flag tolgono il verdetto:
    vedi ``BLOCKING_FLAGS``.  Un bucket che attraversa un bordo e' escluso dal
    calcolo e dichiarato qui, ma da solo non invalida la fase.
    """
    flags: List[str] = []
    t0 = _parse_utc(str(phase.get("t_start_utc") or ""))
    t1 = _parse_utc(str(phase.get("t_end_utc") or ""))
    duration = (t1 - t0).total_seconds() if (t0 and t1 and t1 > t0) else 0.0
    minutes, tree_minutes = minute_coverage(inside)
    missing_tree = len(minutes) - len(tree_minutes)
    if duration <= 0:
        flags.append("finestra_non_valida")
    if not inside:
        flags.append("nessun_bucket")
    if len(minutes) < MIN_BUCKETS_PER_PHASE:
        flags.append("meno_di_5_bucket")
    if boundary:
        flags.append(f"bucket_di_bordo:{len(boundary)}")
    if minutes and missing_tree:
        flags.append(f"minuto_senza_albero:{missing_tree}")
    if phase.get("engine_tree_changed") is True:
        flags.append("engine_tree_changed")
    if str(phase.get("exclusion") or "").strip():
        flags.append("esclusione_dichiarata:" + str(phase["exclusion"]).strip())
    if phase.get("s_epi") is None:
        flags.append("denominatore_nullo")
    if phase.get("tree_cpu_j") in (0.0, 0):
        flags.append("albero_a_zero")
    if s_val is None:
        flags.append("s_assente")
    elif not (0.0 <= s_val <= 1.0):
        flags.append("s_fuori_da_0_1")
    done = phase.get("done_reason")
    if (expected_done_reason and done is not None
            and str(done) != str(expected_done_reason)):
        flags.append(f"done_reason:{done}")
    return flags


def relative_symmetric(s: float, s_epi: float) -> Optional[float]:
    """Differenza relativa simmetrica; definita se la somma e' positiva."""
    if s + s_epi <= 0:
        return None
    return 2.0 * (s - s_epi) / (s + s_epi)


def phase_share(phase: Dict[str, object]) -> Tuple[Optional[float], str]:
    """``s`` dai componenti grezzi se ci sono, altrimenti dal campo dichiarato.

    Se il piano porta sia ``s`` sia i componenti, il controllo di coerenza e'
    esplicito: una discrepanza oltre 1e-6 diventa un flag, non un silenzio.
    """
    d_ollama = phase.get("d_ollama_s")
    d_busy = phase.get("d_busy_s")
    s_field = phase.get("s")
    s_calc = None
    if d_ollama is not None and d_busy is not None:
        try:
            db = float(d_busy)
            if db > 0:
                s_calc = float(d_ollama) / db
        except (TypeError, ValueError):
            s_calc = None
    if s_calc is not None:
        return s_calc, "d_ollama/d_busy"
    if s_field is not None:
        try:
            return float(s_field), str(phase.get("s_source") or "campo s")
        except (TypeError, ValueError):
            return None, "s non numerica"
    return None, "assente"


# ---------------------------------------------------------------------------
# valutazione di una fase
# ---------------------------------------------------------------------------
def evaluate_phase(
    phase: Dict[str, object], buckets: Sequence[Bucket],
    band: Optional[Dict[str, float]],
    expected_done_reason: Optional[str] = None,
) -> Dict[str, object]:
    t0 = _parse_utc(str(phase.get("t_start_utc") or ""))
    t1 = _parse_utc(str(phase.get("t_end_utc") or ""))
    row: Dict[str, object] = {
        "phase_id": phase.get("phase_id"),
        "config_id": phase.get("config_id"),
        "replica": phase.get("replica"),
        "t_start_utc": phase.get("t_start_utc"),
        "t_end_utc": phase.get("t_end_utc"),
        "duration_s": None,
        "s": None, "s_source": None,
        "s_epi": None, "d": None, "r": None, "in_band": None,
        "blocking": False,
        "n_minutes": 0, "n_minutes_with_tree": 0, "boundary_buckets": 0,
        "boundary_minutes": 0, "window_strict": None,
        "tree_cpu_j": None, "total_cpu_j": None,
        "tree_app_ids": "", "engine_tree_changed": bool(
            phase.get("engine_tree_changed")),
        "exclusion": str(phase.get("exclusion") or ""),
        "flags": "",
    }
    if not (t0 and t1 and t1 > t0):
        row["flags"] = "finestra_non_valida"
        row["blocking"] = True
        return row
    inside, boundary = choose_phase_buckets(buckets, t0, t1)
    agg = s_epi_of(inside)
    minutes, tree_minutes = minute_coverage(inside)
    # la quota pubblicata e quella con cui si calcolano d e r sono lo stesso
    # numero: chi rilegge il CSV deve ritrovare d = s - s_epi, non una
    # differenza di 1e-6 dovuta a due arrotondamenti diversi
    s_epi_out = (round(float(agg["s_epi"]), 9)
                 if agg["s_epi"] is not None else None)
    row.update({
        "duration_s": round((t1 - t0).total_seconds(), 3),
        "s_epi": s_epi_out,
        "tree_cpu_j": agg["tree_cpu_j"],
        "total_cpu_j": agg["total_cpu_j"],
        "tree_app_ids": "|".join(agg["tree_app_ids"]),
        "n_minutes": len(minutes),
        "n_minutes_with_tree": len(tree_minutes),
        "boundary_buckets": len(boundary),
        # i due conteggi non coincidono: un solo minuto di bordo porta una riga
        # per ogni AppId attiva (misurato 106 righe su un minuto, dump 23/10)
        "boundary_minutes": len({b.ts_utc for b in boundary}),
        "window_strict": not boundary,
    })
    s_val, s_src = phase_share(phase)
    row["s"], row["s_source"] = s_val, s_src
    if s_val is not None and s_epi_out is not None:
        d = s_val - s_epi_out
        row["d"] = round(d, 9)
        r = relative_symmetric(s_val, s_epi_out)
        row["r"] = round(r, 9) if r is not None else None
    flags = quality_flags({**phase, **row}, inside, boundary, s_val,
                          expected_done_reason)
    if (phase.get("s") is not None and phase.get("d_ollama_s") is not None
            and phase.get("d_busy_s") is not None and s_val is not None):
        try:
            if abs(float(phase["s"]) - s_val) > 1e-6:
                flags.append("s_dichiarata_diversa_dai_componenti")
        except (TypeError, ValueError):
            pass
    row["flags"] = ",".join(flags)
    row["blocking"] = is_blocking(flags)
    blocked = row["blocking"]
    if band and row["d"] is not None and row["r"] is not None and not blocked:
        row["in_band"] = bool(
            abs(float(row["d"])) <= float(band["abs"])
            and abs(float(row["r"])) <= float(band["rel"]))
    return row


def summarize(rows: Sequence[Dict[str, object]]) -> Dict[str, object]:
    """Distribuzione di d e r per configurazione; nessuna deviazione standard."""
    by_cfg: Dict[str, List[Dict[str, object]]] = {}
    for r in rows:
        by_cfg.setdefault(str(r.get("config_id")), []).append(r)

    def stats(vals: List[float]) -> Optional[Dict[str, float]]:
        if not vals:
            return None
        return {
            "n": len(vals), "mean": statistics.fmean(vals),
            "median": statistics.median(vals),
            "min": min(vals), "max": max(vals),
            "range": max(vals) - min(vals),
        }

    out: Dict[str, object] = {}
    for cfg, rs in by_cfg.items():
        d = [float(r["d"]) for r in rs if r.get("d") is not None]
        rr = [float(r["r"]) for r in rs if r.get("r") is not None]
        inb = [r["in_band"] for r in rs if r.get("in_band") is not None]
        out[cfg] = {
            "n_phases": len(rs),
            "n_with_s_epi": len(d),
            # "con almeno un flag" non e' "senza verdetto": un bucket di bordo
            # produce un flag e lascia il verdetto.  I due conteggi restano
            # separati, altrimenti la copertura sembra peggiore di quella che e'
            "n_with_flags": sum(1 for r in rs if str(r.get("flags") or "")),
            "n_blocking": sum(1 for r in rs if r.get("blocking")),
            "n_with_verdict": len(inb),
            "n_window_strict": sum(1 for r in rs if r.get("window_strict")),
            "d": stats(d), "r_sym": stats(rr),
            "in_band": (sum(1 for x in inb if x), len(inb)) if inb else None,
            "replicas": sorted({r.get("replica") for r in rs
                                if r.get("replica") is not None}),
        }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _load_plan(path: Path) -> Dict[str, object]:
    with open(path, encoding="utf-8") as fh:
        plan = json.load(fh)
    if not isinstance(plan.get("phases"), list) or not plan["phases"]:
        raise SystemExit("piano senza 'phases'")
    band = plan.get("band")
    if band is not None:
        if not isinstance(band, dict) or "abs" not in band or "rel" not in band:
            raise SystemExit("band deve essere null o {'abs': x, 'rel': y}")
        try:
            b_abs, b_rel = float(band["abs"]), float(band["rel"])
        except (TypeError, ValueError):
            raise SystemExit("band.abs e band.rel devono essere numeri")
        if b_abs < 0 or b_rel < 0:
            raise SystemExit("band.abs e band.rel non possono essere negativi")
        plan["band"] = {"abs": b_abs, "rel": b_rel}
    return plan


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _source_record(path: Path, kind: str, n_buckets: int,
                   archived: Optional[Path] = None) -> Dict[str, object]:
    """Traccia il file d'origine: l'analisi si deve poter rigenerare (P6.6)."""
    rec: Dict[str, object] = {
        "kind": kind, "path": str(path), "sha256": _sha256(path),
        "bytes": path.stat().st_size, "n_buckets": n_buckets,
    }
    if archived is not None:
        rec["archived_path"] = str(archived)
    return rec


def _write_outputs(rows: List[Dict[str, object]], plan: Dict[str, object],
                   out_json: Path, out_csv: Path,
                   sources: Optional[Sequence[Dict[str, object]]] = None) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "campaign_id": plan.get("campaign_id"),
        "ollama_version": plan.get("ollama_version"),
        "model_digest": plan.get("model_digest"),
        "band": plan.get("band"),
        # la presenza della banda nel piano non prova *quando* e' stata fissata:
        # il congelamento e' un atto del protocollo, non un campo verificabile qui
        "band_in_plan_at_analysis_time": plan.get("band") is not None,
        "sources": list(sources or []),
        "n_phases": len(rows),
        "rows": rows,
        "summary_by_config": summarize(rows),
        "note": ("d = s - s_EPI; r = 2(s - s_EPI)/(s + s_EPI). Nessuna "
                 "deviazione standard: min, mediana, max e range (P4.12)."),
    }
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    fields = [
        "phase_id", "config_id", "replica", "t_start_utc", "t_end_utc",
        "duration_s", "s", "s_source", "s_epi", "d", "r", "in_band",
        "blocking", "n_minutes", "n_minutes_with_tree", "boundary_buckets",
        "boundary_minutes", "window_strict",
        "tree_cpu_j", "total_cpu_j", "tree_app_ids", "engine_tree_changed",
        "exclusion", "flags",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def _selftest() -> int:
    """Prove offline: niente powercfg, niente run, nessun hardware."""
    ok = 0

    def check(name: str, cond: bool) -> None:
        nonlocal ok
        if not cond:
            raise AssertionError(name)
        ok += 1

    T = _dt.datetime
    td = _dt.timedelta
    # 1. identificazione dell'albero: nomi esatti, basename, case
    check("tree exe", is_tree_app("C:\\Program Files\\Ollama\\ollama.exe"))
    check("tree worker", is_tree_app("llama-server.exe"))
    check("tree app", is_tree_app("Ollama App.EXE"))
    check("not tree", not is_tree_app("chrome.exe"))
    check("not needle", not is_tree_app("ollama-helper.exe"))

    # 2. 5 minuti pieni: albero 600 mJ x 5, altro processo 400 mJ x 5
    base = T(2026, 10, 25, 10, 0, 0)
    buckets = [
        Bucket("ollama.exe", base + td(minutes=i), 60_000, 600.0, 0.0, 0.0)
        for i in range(5)
    ]
    buckets += [
        Bucket("chrome.exe", base + td(minutes=i), 60_000, 400.0, 0.0, 0.0)
        for i in range(5)
    ]
    inside, boundary = choose_phase_buckets(buckets, base, base + td(minutes=5))
    check("10 bucket dentro", len(inside) == 10)
    check("nessun bordo", not boundary)
    agg = s_epi_of(inside)
    check("s_epi 3/5", abs(agg["s_epi"] - 0.6) < 1e-12)
    check("tree 3 J", abs(agg["tree_cpu_j"] - 3.0) < 1e-9)
    check("totale 5 J", abs(agg["total_cpu_j"] - 5.0) < 1e-9)

    # 3. un bucket che attraversa t0 o t1 non entra e viene dichiarato
    edge_in = Bucket("ollama.exe", base - td(seconds=20), 60_000, 999.0, 0.0, 0.0)
    edge_out = Bucket("ollama.exe", base + td(minutes=4, seconds=30), 60_000,
                      999.0, 0.0, 0.0)
    inside3, boundary3 = choose_phase_buckets(
        [edge_in, edge_out], base, base + td(minutes=5))
    check("bordi fuori", len(inside3) == 0 and len(boundary3) == 2)

    # 4. righe complementari: restano entrambe e formano un solo minuto
    two = [Bucket("ollama.exe", base, 26_593, 10.0, 0.0, 0.0),
           Bucket("ollama.exe", base, 33_399, 10.0, 0.0, 0.0)]
    check("complementari", len(dedup(two)) == 2)
    check("complementari somma", abs(s_epi_of(two)["total_cpu_j"] - 0.02) < 1e-12)
    mins, mins_tree = minute_coverage(two)
    check("un minuto", len(mins) == 1)
    check("minuto con albero", len(mins_tree) == 1)

    # 5. roll-up orario scartato e pseudo-AppId escluso dal denominatore
    check("roll-up", not (0 < 7.2e7 <= MAX_BUCKET_MS))
    pseudo = Bucket("EMI_RAPL_Package0_PKG", base, 60_000, 0.0, 50.0, 50.0)
    check("pseudo escluso", s_epi_of([pseudo])["total_cpu_j"] == 0.0)

    # 6. differenza relativa simmetrica
    r = relative_symmetric(0.7339, 0.7361)
    check("r simmetrica", abs(r - (-0.002993197278911565)) < 1e-12)
    check("r segno", r is not None and r < 0)
    check("r formula", abs(r - 2 * (-0.0022) / 1.47) < 1e-12)
    check("r zero", relative_symmetric(0.7, 0.7) == 0.0)
    check("r non definita", relative_symmetric(0.0, 0.0) is None)

    # 7. fase completa con banda: d e r coerenti con i campi pubblicati
    phase = {
        "phase_id": "p1", "config_id": "c1", "replica": 1,
        "t_start_utc": base.isoformat(),
        "t_end_utc": (base + td(minutes=5)).isoformat(),
        "d_ollama_s": 73.39, "d_busy_s": 100.0, "s_source": "csv",
        "engine_tree_changed": False, "exclusion": "",
    }
    row = evaluate_phase(phase, buckets, {"abs": 0.005, "rel": 0.01})
    check("s", abs(float(row["s"]) - 0.7339) < 1e-12)
    check("s_epi fase", abs(float(row["s_epi"]) - 0.6) < 1e-12)
    check("d", abs(float(row["d"]) - 0.1339) < 1e-9)
    check("r fase", abs(float(row["r"]) - round(2 * 0.1339 / 1.3339, 9)) < 1e-12)
    check("d dal CSV", abs(float(row["d"]) - (float(row["s"])
                                              - float(row["s_epi"]))) < 1e-9)
    check("in band false", row["in_band"] is False)
    check("non bloccante", row["blocking"] is False)
    check("finestra stretta", row["window_strict"] is True)
    check("boundary zero", row["boundary_buckets"] == 0)
    check("minuti 5", row["n_minutes"] == 5)
    check("minuti con albero 5", row["n_minutes_with_tree"] == 5)
    check("nessun flag", row["flags"] == "")

    # 8. senza banda: nessun verdetto
    row2 = evaluate_phase(phase, buckets, None)
    check("in_band null", row2["in_band"] is None)

    # 9. engine_tree_changed blocca il verdetto
    ph3 = dict(phase, engine_tree_changed=True)
    row3 = evaluate_phase(ph3, buckets, {"abs": 0.5, "rel": 0.9})
    check("e_t_c flag", "engine_tree_changed" in row3["flags"])
    check("e_t_c no band", row3["in_band"] is None)

    # 10. albero a zero: la quota EPI e' 0, il verdetto e' bloccato
    only_chrome = [
        Bucket("chrome.exe", base + td(minutes=i), 60_000, 400.0, 0.0, 0.0)
        for i in range(5)
    ]
    row4 = evaluate_phase(phase, only_chrome, {"abs": 0.5, "rel": 0.9})
    check("s_epi 0", row4["s_epi"] == 0.0)
    check("albero flag", "albero_a_zero" in row4["flags"])
    check("albero no band", row4["in_band"] is None)

    # 11. nessun bucket: denominatore nullo e quota non calcolabile
    row4b = evaluate_phase(phase, [], {"abs": 0.5, "rel": 0.9})
    check("s_epi none", row4b["s_epi"] is None)
    check("den flag", "denominatore_nullo" in row4b["flags"])

    # 12. meno di 5 minuti
    row5 = evaluate_phase(phase, buckets[:2], {"abs": 0.5, "rel": 0.9})
    check("5 bucket flag", "meno_di_5_bucket" in row5["flags"])

    # 13. un bucket che attraversa t1 e' dichiarato ed escluso, non bloccante:
    #     gli estremi della fase vengono dalle letture ai bordi, non dai
    #     confini dei minuti, quindi quasi ogni fase reale ne ha almeno uno
    with_edge = list(buckets) + [
        Bucket("ollama.exe", base + td(minutes=5), 60_000, 600.0, 0.0, 0.0)]
    ph13 = dict(phase, t_end_utc=(base + td(minutes=5, seconds=30)).isoformat())
    row6 = evaluate_phase(ph13, with_edge, {"abs": 0.5, "rel": 0.9})
    check("bordo flag", "bucket_di_bordo:1" in row6["flags"])
    check("bordo escluso dal calcolo", row6["n_minutes"] == 5)
    check("bordo righe e minuti distinti",
          row6["boundary_buckets"] == 1 and row6["boundary_minutes"] == 1)
    check("bordo non bloccante", row6["blocking"] is False)
    check("bordo finestra non stretta", row6["window_strict"] is False)
    check("bordo con verdetto", row6["in_band"] is True)
    check("bordo non in BLOCKING_FLAGS",
          not is_blocking(["bucket_di_bordo:2"]))

    # 14. un minuto senza riga dell'albero blocca il verdetto
    no_tree_minute = [
        Bucket("ollama.exe", base + td(minutes=i), 60_000, 600.0, 0.0, 0.0)
        for i in range(1, 5)
    ] + [
        Bucket("chrome.exe", base + td(minutes=i), 60_000, 400.0, 0.0, 0.0)
        for i in range(5)
    ]
    row7 = evaluate_phase(phase, no_tree_minute, {"abs": 0.5, "rel": 0.9})
    check("albero mancante flag", "minuto_senza_albero:1" in row7["flags"])
    check("albero mancante no band", row7["in_band"] is None)

    # 15. s fuori da [0,1] (P6.6) blocca il verdetto
    ph15 = dict(phase, d_ollama_s=120.0, d_busy_s=100.0)
    row8 = evaluate_phase(ph15, buckets, {"abs": 0.5, "rel": 0.9})
    check("s 1.2", abs(float(row8["s"]) - 1.2) < 1e-12)
    check("s range flag", "s_fuori_da_0_1" in row8["flags"])
    check("s range no band", row8["in_band"] is None)

    # 15b. senza d_ollama, d_busy ne' s dichiarata: niente quota
    ph15b = {k: v for k, v in phase.items() if k not in ("d_ollama_s", "d_busy_s")}
    row8b = evaluate_phase(ph15b, buckets, {"abs": 0.5, "rel": 0.9})
    check("s assente flag", "s_assente" in row8b["flags"])
    check("s assente no band", row8b["in_band"] is None)

    # 16. done_reason diverso da quello dichiarato nel piano
    ph16 = dict(phase, done_reason="stop")
    row9 = evaluate_phase(ph16, buckets, {"abs": 0.5, "rel": 0.9},
                          expected_done_reason="length")
    check("done_reason flag", "done_reason:stop" in row9["flags"])
    check("done_reason no band", row9["in_band"] is None)

    # 17. riepilogo: mediana e range, nessuna sd, fasi bloccate contate
    summ = summarize([row, dict(row, d=0.2, r=0.1), row9])
    check("summary n", summ["c1"]["n_with_s_epi"] == 3)
    check("summary range", "range" in summ["c1"]["d"])
    check("summary no sd", "sd" not in summ["c1"]["d"])
    check("summary bloccate", summ["c1"]["n_blocking"] == 1)
    check("summary con flag", summ["c1"]["n_with_flags"] == 1)
    check("summary con verdetto", summ["c1"]["n_with_verdict"] == 2)
    check("summary finestre strette", summ["c1"]["n_window_strict"] == 3)

    print(f"[selftest OK] {ok} controlli; nessun run, nessun powercfg, "
          "nessun accesso all'hardware")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="s_EPI per fase da SRUM e associazione a s (P6.6).")
    p.add_argument("--plan", help="piano JSON con le fasi e la banda (o null)")
    p.add_argument("--dump", action="append", default=[],
                   help="dump SRUM da powercfg /srumutil (ripetibile)")
    p.add_argument("--buckets", action="append", default=[],
                   help="bucket gia' normalizzati in CSV (ripetibile)")
    p.add_argument("--out-json", help="output JSON")
    p.add_argument("--out-csv", help="output CSV per fase")
    p.add_argument("--archive-dir", help="copia qui i dump SRUM grezzi "
                                         "(l'analisi si rigenera dai file)")
    p.add_argument("--capture-to", help="esegue powercfg /srumutil su questo "
                                        "file (admin; NON e' un test)")
    p.add_argument("--selftest", action="store_true",
                   help="prove offline delle sole funzioni pure")
    args = p.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.capture_to:
        out = Path(args.capture_to).resolve()
        got = srum.flush(out)
        if got is None:
            print("ERRORE: powercfg /srumutil non ha scritto il dump "
                  "(serve amministratore)", file=sys.stderr)
            return 2
        print(f"dump: {got}")
        return 0
    if not args.plan:
        p.error("serve --plan (oppure --selftest / --capture-to)")
    if not args.dump and not args.buckets:
        p.error("serve almeno un --dump o --buckets")

    plan = _load_plan(Path(args.plan))
    archive = Path(args.archive_dir).resolve() if args.archive_dir else None
    if archive is not None:
        archive.mkdir(parents=True, exist_ok=True)
    buckets: List[Bucket] = []
    sources: List[Dict[str, object]] = []
    for d in args.dump:
        path = Path(d)
        got = buckets_from_dump(path)
        archived = None
        if archive is not None:
            archived = archive / path.name
            if archived.resolve() != path.resolve():
                shutil.copy2(path, archived)
        sources.append(_source_record(path, "srum-dump", len(got), archived))
        buckets += got
    for b in args.buckets:
        path = Path(b)
        got = buckets_from_csv(path)
        sources.append(_source_record(path, "buckets-normalized", len(got)))
        buckets += got
    n_before = len(buckets)
    buckets = dedup(buckets)
    n_dup = n_before - len(buckets)
    if not buckets:
        print("ERRORE: nessun bucket utilizzabile", file=sys.stderr)
        return 2
    band = plan.get("band")
    expected = plan.get("done_reason_expected")
    rows = [evaluate_phase(ph, buckets, band, expected) for ph in plan["phases"]]
    out_json = Path(args.out_json or ROOT / "experiment_results" /
                    "s_epi_phase_out.json")
    out_csv = Path(args.out_csv or ROOT / "experiment_results" /
                   "s_epi_phase_out.csv")
    _write_outputs(rows, plan, out_json, out_csv, sources)
    flagged = sum(1 for r in rows if str(r.get("flags") or ""))
    blocked = sum(1 for r in rows if r.get("blocking"))
    printable = sum(1 for r in rows if r["in_band"] is not None)
    strict = sum(1 for r in rows if r.get("window_strict"))
    print(f"bucket: {len(buckets)} distinti su {n_before} letti; "
          f"duplicati scartati: {n_dup}")
    print(f"fasi: {len(rows)} (con almeno un flag: {flagged}; "
          f"bloccate: {blocked}; finestra stretta: {strict}; "
          f"con verdetto di banda: {printable})")
    print(f"banda: {band if band is not None else 'non congelata (in_band=null)'}")
    print(f"JSON: {out_json}")
    print(f"CSV:  {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
