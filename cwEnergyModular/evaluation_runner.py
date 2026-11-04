"""Generic result and energy association utilities for CasualWatt."""
from __future__ import annotations

import csv
import json
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

# Bootstrap a cluster: il seme e' fissato perche' l'intervallo deve essere
# rigenerabile dalla stessa riga, non un numero diverso a ogni esecuzione.
BOOTSTRAP_SEED = 20261104
BOOTSTRAP_RESAMPLES = 2000


def cluster_bootstrap_interval(pairs: Iterable[tuple[int, Any]],
                               resamples: int = BOOTSTRAP_RESAMPLES,
                               seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Intervallo percentile al 95% della precisione, ricampionando i TASK.

    `pairs` sono le sole righe determinate come (esito 1/0, identita' del task).
    L'unita' di ricampionamento e' il cluster, non la riga: se la stessa
    domanda compare in piu' richieste, le sue righe non sono prove indipendenti
    e l'intervallo di Wilson su n righe finge un n_effective che non c'e'.
    Con un solo membro per cluster questo coincide col bootstrap sulle righe.

    Non sostituisce Wilson: lo accompagna, e la differenza fra le due ampiezze
    e' la misura dell'intra-correlazione. Per CONFRONTARE due sistemi sullo
    stesso task resta la via dichiarata (McNemar appaiato), non questo intervallo.

    Ritorna un dict con `interval` (None e `reason` quando l'unita' di cluster
    non e' registrata o non c'e' nulla da ricampionare), `n_effective_tasks`,
    `n_rows`, `n_rows_without_task`, `resamples`, `seed`.
    """
    rows = [(int(esito), cluster) for esito, cluster in pairs]
    senza_id = sum(1 for _, cluster in rows if cluster in (None, ""))
    gruppi: dict[Any, list[int]] = {}
    for esito, cluster in rows:
        if cluster in (None, ""):
            continue
        gruppi.setdefault(cluster, []).append(esito)
    base = {
        "n_effective_tasks": len(gruppi),
        "n_rows": len(rows),
        "n_rows_without_task": senza_id,
        "resamples": resamples,
        "seed": seed,
    }
    if not gruppi:
        return {**base, "interval": None,
                "reason": "task identity not recorded: a row-level bootstrap "
                          "would narrow the interval by assuming the independence "
                          "the cluster is meant to correct"}
    if len(gruppi) < 2:
        return {**base, "interval": None,
                "reason": "one distinct task: every resample reproduces the same "
                          "accuracy, so a zero-width interval here would report "
                          "certainty manufactured from a single cluster, not evidence"}
    if resamples < 1:
        return {**base, "interval": None, "reason": "resamples < 1"}
    chiavi = sorted(gruppi, key=repr)          # ordine deterministico
    membri = [gruppi[k] for k in chiavi]
    rng = random.Random(seed)
    stime: list[float] = []
    for _ in range(resamples):
        camp = [membri[rng.randrange(len(membri))] for _ in membri]
        totale = sum(len(c) for c in camp)
        if not totale:
            continue
        stime.append(sum(sum(c) for c in camp) / totale)
    if len(stime) < 2:
        return {**base, "interval": None,
                "reason": "bootstrap degenerate: nessun ricampiono con denominatore"}
    stime.sort()
    lo, hi = (_percentile(stime, 0.025), _percentile(stime, 0.975))
    return {**base, "interval": [round(lo, 6), round(hi, 6)], "reason": ""}


def _percentile(valori: list[float], q: float) -> float:
    """Percentile con interpolazione lineare sui ranghi (come numpy default)."""
    if not valori:
        return float("nan")
    posizione = (len(valori) - 1) * q
    basso = math.floor(posizione)
    alto = math.ceil(posizione)
    if basso == alto:
        return valori[basso]
    return valori[basso] + (valori[alto] - valori[basso]) * (posizione - basso)


def attach_energy(record: Mapping[str, Any], energy_j: Optional[float],
                  duration_s: Optional[float] = None) -> dict[str, Any]:
    """Attach energy to one response without turning missing data into zero."""
    output = dict(record)
    output["energy_j"] = energy_j if energy_j is not None else None
    output["duration_s"] = duration_s if duration_s is not None else None
    verdict = output.get("end_to_end", output.get("verdict"))
    output["energy_per_correct_j"] = (
        energy_j if verdict == "correct" and energy_j is not None else None
    )
    return output


def summarize_records(records: Iterable[Mapping[str, Any]],
                      cluster_key: str = "task_id") -> dict[str, Any]:
    """Aggrega i verdetti. `cluster_key` e' il campo che identifica il task:
    con lo stesso task ripetuto piu' volte l'unita' statistica non e' la riga,
    e l'intervallo a livello di task lo dice."""
    rows = list(records)
    verdicts = Counter(str(row.get("end_to_end", row.get("verdict", ""))) for row in rows)
    determinate = [row for row in rows if row.get("end_to_end", row.get("verdict"))
                   in ("correct", "incorrect")]
    correct = sum(row.get("end_to_end", row.get("verdict")) == "correct"
                  for row in determinate)
    def finite_measurement(row: Mapping[str, Any], key: str) -> Optional[float]:
        value = row.get(key)
        if value in (None, "", "N/A"):
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if math.isfinite(parsed) else None

    energy_values = [(row, finite_measurement(row, "energy_j")) for row in rows]
    energies = [value for _, value in energy_values if value is not None]
    correct_energies = [value for row, value in energy_values
                        if value is not None
                        and row.get("end_to_end", row.get("verdict")) == "correct"]
    durations = [value for row in rows
                 if (value := finite_measurement(row, "duration_s")) is not None]
    n_determinate = len(determinate)
    accuracy = correct / n_determinate if n_determinate else None
    if n_determinate:
        z = 1.959963984540054
        denominator = 1 + z * z / n_determinate
        centre = (accuracy + z * z / (2 * n_determinate)) / denominator
        margin = math.sqrt(
            accuracy * (1 - accuracy) / n_determinate
            + z * z / (4 * n_determinate * n_determinate)
        ) * z / denominator
        wilson = [round(max(0.0, centre - margin), 6),
                  round(min(1.0, centre + margin), 6)]
    else:
        wilson = None
    cluster = cluster_bootstrap_interval(
        [(1 if row.get("end_to_end", row.get("verdict")) == "correct" else 0,
          row.get(cluster_key)) for row in determinate])
    cluster_note = (
        f"intervallo a livello di task (unita' = {cluster_key}): "
        f"n_effective_tasks={cluster['n_effective_tasks']}, "
        f"righe determinate={cluster['n_rows']}, "
        f"righe senza id escluse dal ricampiono={cluster['n_rows_without_task']}, "
        f"ricampioni={cluster['resamples']}, seed={cluster['seed']}; "
        "Wilson e' a livello di riga e assume indipendenza, il bootstrap a "
        "cluster no: si leggono insieme, e se il secondo e' piu' largo le righe "
        "non erano prove indipendenti. Il confronto fra due sistemi sullo "
        "stesso task resta una McNemar appaiata, non questo intervallo"
        if cluster["interval"] is not None else
        f"intervallo a livello di task non calcolabile: {cluster['reason']}"
    )
    return {
        "n_total": len(rows),
        "n_determinate": n_determinate,
        "accuracy_wilson_95": wilson,
        "n_effective_tasks": cluster["n_effective_tasks"],
        "accuracy_cluster_bootstrap_95": cluster["interval"],
        "cluster_bootstrap_note": cluster_note,
        "n_correct": correct,
        "n_incorrect": sum(row.get("end_to_end", row.get("verdict")) == "incorrect"
                           for row in rows),
        "n_indeterminate": sum(row.get("end_to_end", row.get("verdict"))
                               == "indeterminate" for row in rows),
        "accuracy_on_determinate": correct / len(determinate) if determinate else None,
        "coverage": len(determinate) / len(rows) if rows else None,
        "verdict_counts": dict(verdicts),
        "median_energy_j": _median(energies),
        "median_energy_correct_j": _median(correct_energies),
        "median_duration_s": _median(durations),
        "n_invalid_or_missing_energy": len(rows) - len(energies),
        "missing_energy_rate": 1 - len(energies) / len(rows) if rows else None,
        "n_invalid_or_missing_duration": len(rows) - len(durations),
        "missing_duration_rate": 1 - len(durations) / len(rows) if rows else None,
    }


def _median(values: list[float]) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    middle = len(values) // 2
    if len(values) % 2:
        return round(values[middle], 6)
    return round((values[middle - 1] + values[middle]) / 2, 6)


def write_jsonl(records: Iterable[Mapping[str, Any]], path: str | Path) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(dict(record), ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
