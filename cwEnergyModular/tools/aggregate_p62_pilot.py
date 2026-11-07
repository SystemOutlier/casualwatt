# -*- coding: utf-8 -*-
"""tools/aggregate_p62_pilot.py — terne di baseline del pilota, aggregate per blocco.

P6.2 chiede al pilota le prime terne reali: `half_range_pre_w`, che decide la
forma di `budget_base_w` in P1.7, e `u_within,b` dei blocchi di carico, che e' il
denominatore del primo `rho` di P6.4
(`experiment_results/protocollo_v4_20261024.md:2376-2382`, `:3538-3540`).
Questo script le estrae dai CSV del runner e scrive il riassunto numerico.

**Dove stanno davvero i dati.** Il file indicato nel mandato,
`experiment_results/prep_after6.csv`, e' un dump SRUM grezzo del pre-pilota P6.6
(26 colonne `AppId / TimeStamp / TimeInMSec / CPUEnergyConsumption / ...`) e non
ha nessuna colonna `baseline_pre_w`: lo consuma `cwEnergyModular/s_epi_phase.py`,
non questo script. Le terne stanno nel riepilogo di blocco di `benchmark_v4`
(`pre_windows_w`), perche' la colonna omonima della riga di richiesta e' scritta
vuota dal runner. Lo script legge il file del mandato **solo** per verificare e
dichiarare questa cosa: se un giorno contenesse davvero le terne, il verdetto
cambierebbe e il campo `requested_source` lo direbbe.

**Cosa calcola.** Per ogni esecuzione di blocco: mediana, range e semi-range
dalle tre finestre pre, ricalcolati dalla terna e confrontati con le colonne del
runner (`baseline_pre_w`, `pre_range_w`, `half_range_pre_w` e il
`budget_base_w = hypot(half_range_pre_w, half_drift_w)` di F.4). Una discrepanza
e' un errore, non un arrotondamento da assorbire.

**Cosa non calcola, e perche'.** `u_within,b` e' `semi-range(E_act,i)` sulle `m`
richieste del blocco (F.9, `:2966`) e si misura su `active_energy_raw_j`, che
conserva il segno. Con `m = 1` il semi-range e' zero per costruzione e uno zero
per costruzione non e' evidenza: il campo esce `null` con la ragione, mai `0.0`.
La dispersione di `d = s - s_EPI` entro configurazione, che e' la grandezza su
cui si fissa `R` in P6.6, **non** si stima da questi file: le esecuzioni presenti
differiscono per `num_predict` e vengono da invocazioni separate del runner,
quindi non sono repliche di una configurazione dichiarata. Il campo
`within_config_dispersion` lo dichiara invece di dedurlo.

Sola lettura: nessun run, nessun contatore, nessun `powercfg`.

Uso (dalla radice del repository):
    py cwEnergyModular/tools/aggregate_p62_pilot.py
    py cwEnergyModular/tools/aggregate_p62_pilot.py --out prova.json \
        --block-summary cwEnergyModular/results/casualwatt_v4_block_summary.csv
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent

DEFAULT_BLOCK_SUMMARY = MODULE_DIR / "results" / "casualwatt_v4_block_summary.csv"
DEFAULT_RESULTS = MODULE_DIR / "results" / "casualwatt_v4_results.csv"
DEFAULT_REQUESTED_SOURCE = REPO_ROOT / "experiment_results" / "prep_after6.csv"
DEFAULT_OUT = REPO_ROOT / "experiment_results" / "p62_pilot_aggregated.json"

#: le tre finestre pre di P1.5: una terna, ne' due ne' quattro
N_PRE_WINDOWS = 3
#: tolleranza del confronto fra la terna ricalcolata e le colonne del runner;
#: il CSV stampa 6 decimali su grandezze di ~10^0 W, quindi un quanto di stampa
#: vale 1e-6 e una discrepanza vera sarebbe un multiplo di quello
TOL = 2e-6
#: `u_within,b` esiste da due richieste in su (semi-range definito)
MIN_M_FOR_U_WITHIN = 2

_NUM_PREDICT = re.compile(r"num_predict=(\d+)")


# ---------------------------------------------------------------------------
# lettura
# ---------------------------------------------------------------------------
def _read_csv(path: Path) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader.fieldnames or []), list(reader)


def _float(text: Optional[str]) -> Optional[float]:
    s = (text or "").strip()
    if not s:
        return None
    try:
        value = float(s)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def parse_triple(text: str) -> List[float]:
    """Le tre finestre pre da `pre_windows_w` (`a;b;c`).

    Il conteggio esatto conta: due valori sono repliche incomplete e quattro
    sono un'altra sequenza, non una terna con una ripetizione.
    """
    parts = [p.strip() for p in (text or "").split(";") if p.strip()]
    if len(parts) != N_PRE_WINDOWS:
        raise ValueError(f"attese {N_PRE_WINDOWS} finestre, trovate {len(parts)}")
    values = [float(p) for p in parts]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("finestra non finita")
    return values


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scheda(path: Path, n_rows: int, columns: Sequence[str]) -> Dict[str, object]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "n_rows": n_rows,
        "n_columns": len(columns),
    }


# ---------------------------------------------------------------------------
# le terne
# ---------------------------------------------------------------------------
def triple_stats(windows: Sequence[float]) -> Dict[str, Optional[float]]:
    """Mediana, range e semi-range di F.4 sulle tre finestre pre."""
    if len(windows) != N_PRE_WINDOWS:
        raise ValueError("una terna ha esattamente tre finestre")
    hi, lo = max(windows), min(windows)
    return {
        "median_w": statistics.median(windows),
        "range_w": hi - lo,
        "half_range_w": (hi - lo) / 2.0,
    }


def _check(calculated: Optional[float], declared: Optional[float],
           column: str) -> Dict[str, object]:
    """Confronto ricalcolato/runner, con la discrepanza in chiaro.

    Un valore assente nel runner non e' una discrepanza: e' un campo vuoto, e
    il record lo dice invece di trattarlo come zero.
    """
    if calculated is None or declared is None:
        return {"column": column, "calculated": calculated,
                "runner": declared, "delta": None,
                "ok": declared is not None}
    delta = calculated - declared
    return {"column": column, "calculated": calculated, "runner": declared,
            "delta": delta, "ok": abs(delta) <= TOL}


def _num_predict(notes: str) -> Optional[int]:
    match = _NUM_PREDICT.search(notes or "")
    return int(match.group(1)) if match else None


def analyse_execution(block_row: Dict[str, str],
                      result_rows: Sequence[Dict[str, str]]) -> Dict[str, object]:
    """Una esecuzione di blocco: terna, ricalcolo, confronti, `m`, `u_within`."""
    record: Dict[str, object] = {
        "block_id": (block_row.get("block_id") or "").strip(),
        "batch_id": (block_row.get("batch_id") or "").strip(),
        "num_predict": None,
        "pre_windows_w": [],
        "half_range_pre_w": None,
        "u_within_b": None,
        "u_within_reason": None,
        "m": len(result_rows),
        "n_result_rows_matched": len(result_rows),
        "excluded": "",
    }
    try:
        windows = parse_triple(block_row.get("pre_windows_w") or "")
    except ValueError as exc:
        record["excluded"] = f"terna_non_valida: {exc}"
        return record
    stats = triple_stats(windows)
    half_drift = _float(block_row.get("half_drift_w"))
    budget_calc = (math.hypot(stats["half_range_w"], half_drift)
                   if half_drift is not None else None)
    checks = [
        _check(stats["median_w"], _float(block_row.get("baseline_pre_w")),
               "baseline_pre_w"),
        _check(stats["range_w"], _float(block_row.get("pre_range_w")),
               "pre_range_w"),
        _check(stats["half_range_w"], _float(block_row.get("half_range_pre_w")),
               "half_range_pre_w"),
        _check(budget_calc, _float(block_row.get("budget_base_w")),
               "budget_base_w"),
    ]
    models = sorted({_num_predict(r.get("notes") or "") for r in result_rows}
                    - {None})
    raw = [_float(r.get("active_energy_raw_j")) for r in result_rows]
    raw = [v for v in raw if v is not None]
    record.update({
        "num_predict": models[0] if len(models) == 1 else None,
        "pre_windows_w": windows,
        "half_range_pre_w": stats["half_range_w"],
        "pre_range_w": stats["range_w"],
        "baseline_pre_w": stats["median_w"],
        "half_drift_w": half_drift,
        "budget_base_w": budget_calc,
        "checks": checks,
        "checks_ok": all(c["ok"] for c in checks),
        "active_energy_raw_j": raw,
    })
    if len(models) > 1:
        record["excluded"] = f"num_predict_diversi_nel_blocco: {models}"
    if len(raw) < MIN_M_FOR_U_WITHIN:
        record["u_within_reason"] = (
            f"m={len(raw)}: il semi-range di una sola richiesta e' zero per "
            "costruzione, non e' evidenza (F.9 richiede m repliche nel blocco)")
    else:
        record["u_within_b"] = (max(raw) - min(raw)) / 2.0
        record["u_within_reason"] = "semi-range di active_energy_raw_j (F.9)"
    return record


def distribuzione(values: Sequence[float]) -> Optional[Dict[str, object]]:
    """Min, mediana, max, range e media: nessuna deviazione standard.

    A `n = 3` una deviazione standard non e' una stima di varianza (P4.12), e
    qui vale la stessa regola anche quando le osservazioni sono piu' di tre.
    """
    vals = [float(v) for v in values if v is not None and math.isfinite(v)]
    if not vals:
        return None
    return {
        "n": len(vals),
        "min": min(vals),
        "median": statistics.median(vals),
        "max": max(vals),
        "range": max(vals) - min(vals),
        "mean": statistics.fmean(vals),
    }


def _requested_source(path: Path) -> Dict[str, object]:
    """Verdetto sul file nominato dal mandato, verificato invece che assunto."""
    if not path.exists():
        return {"path": str(path), "exists": False,
                "has_baseline_pre_w": None,
                "verdict": "file assente: nessuna terna puo' venirne"}
    columns, rows = _read_csv(path)
    has = "baseline_pre_w" in [c.strip() for c in columns]
    return {
        "path": str(path),
        "exists": True,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "n_rows": len(rows),
        "n_columns": len(columns),
        "has_baseline_pre_w": has,
        "verdict": ("contiene le terne" if has else
                    "dump SRUM grezzo: nessuna colonna di baseline, le terne "
                    "non ci sono"),
        "header": [c.strip() for c in columns],
    }


# ---------------------------------------------------------------------------
# aggregazione
# ---------------------------------------------------------------------------
def aggregate(block_path: Path, results_path: Path) -> Dict[str, object]:
    block_columns, block_rows = _read_csv(block_path)
    result_columns, result_rows = _read_csv(results_path)

    by_batch: Dict[str, List[Dict[str, str]]] = {}
    for row in result_rows:
        by_batch.setdefault((row.get("batch_id") or "").strip(), []).append(row)

    executions = []
    matched_batches = set()
    for row in block_rows:
        batch = (row.get("batch_id") or "").strip()
        matched_batches.add(batch)
        executions.append(analyse_execution(row, by_batch.get(batch, [])))
    unmatched = [b for b in by_batch if b and b not in matched_batches]

    blocks: List[Dict[str, object]] = []
    by_block: Dict[str, List[Dict[str, object]]] = {}
    for ex in executions:
        by_block.setdefault(str(ex["block_id"]), []).append(ex)
    for block_id in sorted(by_block):
        runs = by_block[block_id]
        valid = [r for r in runs if not r["excluded"]]
        blocks.append({
            "block_id": block_id,
            "n_executions": len(runs),
            "n_valid": len(valid),
            "num_predict_observed": sorted(
                {r["num_predict"] for r in valid if r["num_predict"] is not None}),
            "half_range_pre_w": [r["half_range_pre_w"] for r in valid],
            "distribution_half_range_pre_w": distribuzione(
                [r["half_range_pre_w"] for r in valid]),
            "u_within_b": None,
            "u_within_reason": (
                "nessuna esecuzione con m >= 2: il semi-range entro blocco non "
                "e' calcolabile dai dati presenti"),
            "executions": runs,
        })

    half_ranges = [r["half_range_pre_w"] for r in executions
                   if not r["excluded"] and r["half_range_pre_w"] is not None]
    half_drifts = [r["half_drift_w"] for r in executions
                   if not r["excluded"] and r["half_drift_w"] is not None]
    budgets = [r["budget_base_w"] for r in executions
               if not r["excluded"] and r["budget_base_w"] is not None]
    u_within = [r["u_within_b"] for r in executions if r["u_within_b"] is not None]

    return {
        "schema": "cw.p62_pilot_aggregated/1",
        "generated_at_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "generator": "cwEnergyModular/tools/aggregate_p62_pilot.py",
        "purpose": (
            "prime terne reali di baseline_pre_w del pilota: half_range_pre_w "
            "(P1.7) e u_within,b (denominatore del primo rho, P6.4)"),
        "sources": {
            "block_summary": _scheda(block_path, len(block_rows), block_columns),
            "results": _scheda(results_path, len(result_rows), result_columns),
        },
        "requested_source": _requested_source(DEFAULT_REQUESTED_SOURCE),
        "blocks": blocks,
        "n_blocks": len(blocks),
        "n_executions": len(executions),
        "n_excluded": sum(1 for r in executions if r["excluded"]),
        "n_result_rows_senza_blocco": len(unmatched),
        "result_batch_ids_senza_blocco": unmatched,
        "distribution_half_range_pre_w": distribuzione(half_ranges),
        "distribution_half_drift_w": distribuzione(half_drifts),
        "distribution_budget_base_w": distribuzione(budgets),
        "u_within_b": {
            "values": u_within,
            "distribution": distribuzione(u_within),
            "computed": bool(u_within),
            "reason_if_empty": (
                None if u_within else
                "nessun blocco con m >= 2 richieste: u_within,b = "
                "semi-range(E_act,i) richiede almeno due richieste nella stessa "
                "esecuzione di blocco, e il pilota ha n_inferenze = 1"),
        },
        "within_config_dispersion": {
            "available": False,
            "reason": (
                "le esecuzioni presenti vengono da invocazioni separate del "
                "runner e differiscono per num_predict (32/128/256): non sono "
                "repliche di una configurazione dichiarata, quindi non stimano "
                "la dispersione entro configurazione richiesta da P6.6"),
        },
        "limitations": [
            "half_range_pre_w descrive il pilota (una configurazione, un prompt, "
            "otto esecuzioni): e' una descrizione, non una decisione sulla forma "
            "di budget_base_w (P2.9: il pilota descrive, non decide)",
            "u_within,b e' nullo per costruzione: si misura su m >= 2 richieste "
            "nello stesso blocco, e il pilota ha m = 1",
            "la colonna di riga pre_windows_w e' vuota nel CSV del runner: la "
            "terna esiste solo nel riepilogo di blocco",
            "i dump SRUM del pre-pilota P6.6 (prep_after*.csv) non contengono "
            "terne di baseline e non vengono usati qui",
            "nessuna deviazione standard: a n = 3 non si stima una varianza "
            "(P4.12), e la stessa regola si applica alle distribuzioni sopra",
        ],
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Aggrega le terne di baseline del pilota P6.2 (sola lettura)")
    ap.add_argument("--block-summary", type=Path, default=DEFAULT_BLOCK_SUMMARY)
    ap.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    for path in (args.block_summary, args.results):
        if not path.exists():
            print(f"errore: file assente: {path}", file=sys.stderr)
            return 2
    columns, _ = _read_csv(args.block_summary)
    for needed in ("pre_windows_w", "baseline_pre_w", "half_range_pre_w",
                   "half_drift_w", "budget_base_w", "batch_id", "block_id"):
        if needed not in [c.strip() for c in columns]:
            print(f"errore: colonna {needed!r} assente in {args.block_summary}",
                  file=sys.stderr)
            return 2

    report = aggregate(args.block_summary, args.results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    dist = report["distribution_half_range_pre_w"]
    print(f"blocchi: {report['n_blocks']}, esecuzioni: {report['n_executions']}, "
          f"escluse: {report['n_excluded']}")
    if dist:
        print(f"half_range_pre_w: n={dist['n']} min={dist['min']:.6f} "
              f"mediana={dist['median']:.6f} max={dist['max']:.6f} "
              f"range={dist['range']:.6f}")
    print(f"u_within_b: {'calcolato' if report['u_within_b']['computed'] else 'non calcolabile'}"
          f" ({report['u_within_b']['reason_if_empty'] or 'presente'})")
    print(f"scritto: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
