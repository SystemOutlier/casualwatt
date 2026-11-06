"""Generic result and energy association utilities for CasualWatt."""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

# Bootstrap a cluster: il seme e' fissato perche' l'intervallo deve essere
# rigenerabile dalla stessa riga, non un numero diverso a ogni esecuzione.
BOOTSTRAP_SEED = 20261104
BOOTSTRAP_RESAMPLES = 2000


_TASK_NOTE_PREFIX = "CW_TASK_ID_V1="


def _task_id(value: Any) -> Optional[str]:
    """Solo identita' esplicite non vuote; nessun indice o hash sostitutivo."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def notes_with_task_id(record: Mapping[str, Any]) -> str:
    """Serializza l'identita' dichiarata nella colonna notes gia' esistente."""
    notes = record.get("notes", "")
    text = "; ".join(str(n) for n in notes) if isinstance(notes, (list, tuple)) else str(notes or "")
    identity = _task_id(record.get("task_id"))
    if identity is None:
        return text
    # Si sostituisce solo il nostro metadato, non il testo delle note originali.
    lines = [line for line in text.splitlines() if not line.startswith(_TASK_NOTE_PREFIX)]
    lines.append(_TASK_NOTE_PREFIX + json.dumps(identity, ensure_ascii=True))
    return "\n".join(lines)


def record_task_id(record: Mapping[str, Any]) -> Optional[str]:
    """Legge il task dichiarato in memoria o nel CSV, senza usare prompt_id."""
    direct = _task_id(record.get("task_id"))
    recorded = []
    for line in str(record.get("notes", "")).splitlines():
        if line.startswith(_TASK_NOTE_PREFIX):
            try:
                value = _task_id(json.loads(line[len(_TASK_NOTE_PREFIX):]))
            except (ValueError, TypeError):
                return None
            if value is None:
                return None
            recorded.append(value)
    values = set(recorded + ([direct] if direct is not None else []))
    return values.pop() if len(values) == 1 else None


def record_verdict(record: Mapping[str, Any]) -> str:
    """Compatibilita' con verdict/end_to_end e con is_correct del CSV unificato."""
    for key in ("end_to_end", "verdict"):
        if key in record:
            value = str(record[key])
            return value if value in ("correct", "incorrect") else "indeterminate"
    value = str(record.get("is_correct", "")).strip().lower()
    return "correct" if value in ("1", "1.0", "true") else (
        "incorrect" if value in ("0", "0.0", "false") else "indeterminate")


def cluster_bootstrap_interval(pairs: Iterable[tuple[int, Any]],
                               resamples: int = BOOTSTRAP_RESAMPLES,
                               seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Intervallo percentile al 95% della precisione, ricampionando i TASK.

    `pairs` sono le sole righe determinate come (esito 1/0, identita' del task).
    L'unita' di ricampionamento e' il cluster, non la riga: se la stessa
    domanda compare in piu' richieste, le sue righe non sono prove indipendenti
    e l'intervallo di Wilson su n righe finge un n_effective che non c'e'.
    Con un solo membro per cluster questo coincide col bootstrap sulle righe.

    Non sostituisce Wilson: lo accompagna. La differenza fra le ampiezze non
    e' uno stimatore dell'intra-correlazione. McNemar appaiato e' una possibile
    analisi successiva, ora implementata in paired_mcnemar.

    Ritorna un dict con `interval` (None e `reason` quando l'unita' di cluster
    non e' registrata o non c'e' nulla da ricampionare), `n_effective_tasks`,
    `n_rows`, `n_rows_without_task`, `resamples`, `seed`.
    """
    rows = [(int(esito), _task_id(cluster)) for esito, cluster in pairs]
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
    if senza_id:
        return {**base, "interval": None,
                "reason": f"task identity missing for {senza_id} determinate row(s): "
                          "partial cluster bootstrap would change the estimand"}
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


# --------------------------------------------------------------------------- #
# McNemar appaiato per il confronto di due sistemi sullo stesso task
# --------------------------------------------------------------------------- #

import statistics as _statistics


def _normal_ppf(p: float) -> float:
    if p <= 0.0:
        return -8.0
    if p >= 1.0:
        return 8.0
    return _statistics.NormalDist().inv_cdf(p)


def _binom_pvalue_exact(n: int, k: int, p: float) -> float:
    """Bilateral del binomiale: 2 * min(P(X<=k), P(X>=k)) con correzione."""
    if n == 0:
        return 1.0
    prob_le = sum(
        math.comb(n, i) * p ** i * (1 - p) ** (n - i)
        for i in range(0, k + 1)
    )
    prob_ge = sum(
        math.comb(n, i) * p ** i * (1 - p) ** (n - i)
        for i in range(k, n + 1)
    )
    return min(1.0, 2 * min(prob_le, prob_ge))


def paired_mcnemar(
    pairs_a: Iterable[Any],
    pairs_b: Iterable[Any],
    correction: bool = True,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """McNemar appaiato fra due sistemi sullo stesso task.

    `pairs_a` e `pairs_b` sono liste *appaiate per posizione* di esiti grezzi.
    L'esito viene derivato da `record_verdict` se non e' gia' 0/1.

    Return un dict con:
      - n_determinate: coppie con esito determinato per ENTRAMBI
      - n_excluded: coppie con almeno un esito indeterminato/missing/tech (e reason)
      - a, b, c, d del 2x2 su determinate
      - discordant = b + c
      - p_value: binomiale esatto (sempre) e chi2 (se b+c >= 10), con correction
      - delta_acc = (b-c)/n su determinate (n = determinate)
      - delta_ci: intervallo Newcombe (None se non calcolabile)
      - note
    """
    list_a = list(pairs_a)
    list_b = list(pairs_b)
    if len(list_a) != len(list_b):
        raise ValueError(
            "paired_mcnemar: le due liste devono avere la stessa lunghezza "
            "(appaiamento per task)"
        )
    verdict_a = []
    verdict_b = []
    excluded_rec: Counter[str] = Counter()
    n_excl = 0
    for va, vb in zip(list_a, list_b):
        ea = _coerce_to_determined(va)
        eb = _coerce_to_determined(vb)
        if ea is None or eb is None:
            n_excl += 1
            if ea is None:
                excluded_rec[str(_classify_exclusion(va))] += 1
            if eb is None:
                excluded_rec[str(_classify_exclusion(vb))] += 1
    # filtra determinate reali
    verdict_a = []
    verdict_b = []
    n_determinate = 0
    for va, vb in zip(list_a, list_b):
        ea = _coerce_to_determined(va)
        eb = _coerce_to_determined(vb)
        if ea is not None and eb is not None:
            verdict_a.append(ea)
            verdict_b.append(eb)
            n_determinate += 1
    a = sum(1 for x, y in zip(verdict_a, verdict_b) if x == 1 and y == 1)
    b = sum(1 for x, y in zip(verdict_a, verdict_b) if x == 1 and y == 0)
    c = sum(1 for x, y in zip(verdict_a, verdict_b) if x == 0 and y == 1)
    d = sum(1 for x, y in zip(verdict_a, verdict_b) if x == 0 and y == 0)
    discordant = b + c
    na = n_determinate if n_determinate else None
    p_exact = _binom_pvalue_exact(discordant, b, 0.5) if discordant > 0 else 1.0
    if discordant >= 10:
        if correction:
            chi2 = (abs(b - c) - 1) ** 2 / discordant
        else:
            chi2 = (b - c) ** 2 / discordant
        z = _normal_ppf(1 - alpha / 2)
        p_chi2 = _chi2_survival_1df(chi2)
    else:
        chi2 = None
        p_chi2 = None
    delta = (b - c) / n_determinate if n_determinate else None
    # Newcombe paired interval
    if n_determinate and delta is not None:
        p_a = (a + b) / n_determinate
        p_bv = (a + c) / n_determinate
        z = _normal_ppf(1 - alpha / 2)
        # Wilson intervals marginali
        se_a = math.sqrt(p_a * (1 - p_a) / n_determinate + z * z / (4 * n_determinate * n_determinate))
        se_b = math.sqrt(p_bv * (1 - p_bv) / n_determinate + z * z / (4 * n_determinate * n_determinate))
        crit_a = z / (1 + z * z / n_determinate)
        centre_a = p_a + z * z / (2 * n_determinate)
        centre_b = p_bv + z * z / (2 * n_determinate)
        denom = 1 + z * z / n_determinate
        lo_a = (centre_a - crit_a * math.sqrt(p_a * (1 - p_a) / n_determinate + z * z / (4 * n_determinate * n_determinate))) / denom
        hi_a = (centre_a + crit_a * math.sqrt(p_a * (1 - p_a) / n_determinate + z * z / (4 * n_determinate * n_determinate))) / denom
        lo_b = (centre_b - crit_a * math.sqrt(p_bv * (1 - p_bv) / n_determinate + z * z / (4 * n_determinate * n_determinate))) / denom
        hi_b = (centre_b + crit_a * math.sqrt(p_bv * (1 - p_bv) / n_determinate + z * z / (4 * n_determinate * n_determinate))) / denom
        # paired: width via sum of marginals
        se_paired = math.sqrt(se_a * se_a + se_b * se_b)
        delta_ci = [round(delta - z * se_paired, 6), round(delta + z * se_paired, 6)]
    else:
        delta_ci = None
    indecis = (discordant == 0)
    return {
        "n_total": len(list_a),
        "n_determinate": n_determinate,
        "n_excluded": n_excl,
        "excluded_by_reason": dict(excluded_rec),
        "a": a, "b": b, "c": c, "d": d,
        "discordant": discordant,
        "p_value_exact": round(p_exact, 6) if p_exact is not None else None,
        "p_value_chi2": round(p_chi2, 6) if p_chi2 is not None else None,
        "chi2": round(chi2, 6) if chi2 is not None else None,
        "chi2_correction": bool(correction),
        "delta_acc": round(delta, 6) if delta is not None else None,
        "delta_ci_newcombe": delta_ci,
        "indecis": indecis,
        "correction_applied": "yes",
        "note": (
            "indecis: nessuna coppia discordante" if indecis else ""
        ),
    }


def _coerce_to_determined(value: Any) -> Optional[int]:
    """0/1 se determinato; None se indeterminate/missing/tech."""
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        v = float(value)
        if math.isnan(v):
            return None
        if v in (0.0, 1.0):
            return int(v)
        return 1 if v >= 0.5 else 0
    # usa record_verdict se applicabile
    text = str(value).strip().lower()
    if text in ("1", "1.0", "true", "correct", "yes"):
        return 1
    if text in ("0", "0.0", "false", "incorrect", "no"):
        return 0
    return None


def _classify_exclusion(value: Any) -> str:
    if value is None:
        return "missing"
    text = str(value).strip().lower()
    if text in ("", "none", "na", "n/a", "nan"):
        return "missing"
    if text in ("indeterminate", "unknown", "undetermined"):
        return "indeterminate"
    if "error" in text or "runtime" in text or "fail" in text:
        return "technical_error"
    if text in ("0", "0.0", "false", "incorrect", "no", "1", "1.0", "true", "correct", "yes"):
        return "determinate"
    return "missing"


def _chi2_survival_1df(x: float) -> float:
    """P(χ²_1df > x) = erfc(sqrt(x)/sqrt(2))."""
    if x < 0:
        return 1.0
    return math.erfc(math.sqrt(x) / math.sqrt(2))


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
                      cluster_key: str = "task_id",
                      energy_key: str = "energy_j") -> dict[str, Any]:
    """Aggrega verdetti ed energia disponibile di TUTTI i tentativi.

    Il costo per corretta e' somma energia / tutte le corrette, non la media
    dell'energia delle sole corrette. Le mediane restano diagnostiche firmate.
    `cluster_key` identifica il task: B7 non ammette identita' parziali nel CI.
    """
    rows = list(records)
    verdicts = Counter(str(record_verdict(row)) for row in rows)
    determinate = [row for row in rows if record_verdict(row)
                   in ("correct", "incorrect")]
    correct = sum(record_verdict(row) == "correct"
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

    energy_values = [(row, finite_measurement(row, energy_key)) for row in rows]
    # Diagnostica: anche negativi e valori con flag invalidante restano visibili.
    energies = [value for _, value in energy_values if value is not None]
    correct_energies = [value for row, value in energy_values
                        if value is not None
                        and record_verdict(row) == "correct"]
    available = []
    exclusions: Counter[str] = Counter()
    n_missing = n_invalid = n_negative = n_unverified = n_compatibility = 0
    for row, value in energy_values:
        flags = {key: str(row[key]).strip().lower()
                 for key in ("energy_valid", "active_valid") if key in row}
        rejected = any(flag in ("false", "0", "0.0") for flag in flags.values())
        unknown = any(flag not in ("true", "1", "1.0", "false", "0", "0.0")
                      for flag in flags.values())
        # Un CSV legacy non ha prova della validita' della sottrazione baseline.
        unified = energy_key == "end_to_end_energy_j"
        unverified = unknown or (unified and "active_valid" not in flags) or not flags
        n_negative += int(value is not None and value < 0)
        if row.get(energy_key) in (None, "", "N/A"):
            n_missing += 1
            exclusions["missing"] += 1
            continue
        n_unverified += int(unverified)
        reasons = []
        if value is None:
            reasons.append("nonfinite_or_nonnumeric")
        elif value < 0:
            reasons.append("negative_not_consumed")
        if rejected:
            reasons.append("validity_flag_false")
        if str(row.get("package_window_source", "")).strip().lower() in (
                "counter-invalid", "unavailable"):
            reasons.append("package_window_invalid_or_unavailable")
        if unknown or (unified and unverified):
            reasons.append("validity_unverifiable")
        if reasons:
            n_invalid += 1
            exclusions.update(reasons)
            continue
        available.append(value)
        n_compatibility += int(unverified)
    total_energy = sum(available) if available else None
    energy_status = ("unavailable" if not available else
                     "complete" if len(available) == len(rows) else "partial")
    energy_reason = ("no available eligible energy" if not available else
                     "available subtotal only; incomplete energy coverage"
                     if energy_status == "partial" else "")
    if total_energy is not None and not math.isfinite(total_energy):
        total_energy = None
        energy_status = "unavailable"
        energy_reason = "energy sum is nonfinite"
    ratio_reason = "; ".join(reason for reason in (
        "zero correct answers" if not correct else "", energy_reason) if reason)
    ratio = total_energy / correct if correct and total_energy is not None else None
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
        [(1 if record_verdict(row) == "correct" else 0,
          record_task_id(row) if cluster_key == "task_id" else row.get(cluster_key))
         for row in determinate])
    cluster_note = (
        f"intervallo a livello di task (unita' = {cluster_key}): "
        f"n_effective_tasks={cluster['n_effective_tasks']}, "
        f"righe determinate={cluster['n_rows']}, "
        f"righe senza id escluse dal ricampiono={cluster['n_rows_without_task']}, "
        f"ricampioni={cluster['resamples']}, seed={cluster['seed']}; "
        "Wilson e' a livello di riga e assume indipendenza, il bootstrap a "
        "cluster conserva le righe di ciascun task insieme. Le ampiezze non "
        "misurano direttamente l'intra-correlazione. McNemar non implementato"
        if cluster["interval"] is not None else
        f"intervallo a livello di task non calcolabile: {cluster['reason']}"
    )
    return {
        "n_total": len(rows),
        "n_determinate": n_determinate,
        "accuracy_wilson_95": wilson,
        "n_effective_tasks": cluster["n_effective_tasks"],
        "n_determinate_without_task_id": cluster["n_rows_without_task"],
        "accuracy_cluster_bootstrap_95": cluster["interval"],
        "cluster_bootstrap_note": cluster_note,
        "n_correct": correct,
        "n_incorrect": sum(record_verdict(row) == "incorrect"
                           for row in rows),
        "n_indeterminate": sum(record_verdict(row)
                               == "indeterminate" for row in rows),
        "accuracy_on_determinate": correct / len(determinate) if determinate else None,
        "coverage": len(determinate) / len(rows) if rows else None,
        "verdict_counts": dict(verdicts),
        "median_energy_j": _median(energies),
        "median_energy_correct_j": _median(correct_energies),
        "median_duration_s": _median(durations),
        "energy_key": energy_key,
        "total_energy_j": total_energy,
        "energy_per_correct_j": ratio,
        "energy_status": energy_status,
        "energy_reason": energy_reason,
        "energy_per_correct_status": energy_status if ratio is not None else "undefined",
        "energy_per_correct_reason": ratio_reason,
        "energy_coverage": len(available) / len(rows) if rows else None,
        "n_available_energy": len(available),
        "n_missing_energy": n_missing,
        "n_invalid_energy": n_invalid,
        "n_negative_energy": n_negative,
        "n_unverified_energy_validity": n_unverified,
        "n_compatibility_energy": n_compatibility,
        "energy_exclusion_counts": dict(exclusions),
        "energy_numerator": "sum of available eligible energy over ALL rows, including failures",
        "energy_denominator": "ALL correct rows, including those without eligible energy",
        "energy_note": (
            "total_energy_j is an available subtotal when status=partial, not a complete total; "
            "negative energies are preserved in diagnostic medians, excluded (not clamped) "
            "from consumed energy. Medians use all finite values, including invalid rows. "
            "Generic energy_j without flags is accepted for compatibility only: a finite "
            "nonnegative number does not prove metrological validity. Unified rows without "
            "active_valid have unverifiable validity and are excluded. Complete denotes "
            "row coverage, not independent validation or completeness of the physical boundary."
        ),
        "n_invalid_or_missing_energy": n_missing + n_invalid,
        "missing_energy_rate": 1 - len(available) / len(rows) if rows else None,
        "n_invalid_or_missing_duration": len(rows) - len(durations),
        "missing_duration_rate": 1 - len(durations) / len(rows) if rows else None,
    }


def summarize_unified_records(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Separa run/sessione/sistema e pubblica la provenienza, senza rivalutare GT.

    I metodi registrati (anche semantici legacy) NON diventano accuratezza
    deterministica per il solo fatto di aggregare is_correct.
    """
    keys = ("run_id", "session_id", "provider", "model_name", "mode")
    groups: dict[tuple, list[Mapping[str, Any]]] = {}
    for record in records:
        identity = tuple(record.get(key) for key in keys)
        groups.setdefault(identity, []).append(record)

    def recorded(rows, fields):
        return {field: dict(Counter(
            str(row.get(field)) if row.get(field) not in (None, "", "N/A")
            else "not-recorded" for row in rows)) for field in fields}

    results = []
    for identity, rows in groups.items():
        result = summarize_records(rows, energy_key="end_to_end_energy_j")
        result.update(zip(keys, identity))
        result["correctness_metadata"] = recorded(rows, (
            "eval_method", "eval_mode", "answer_type", "acc_links_basis",
            "judge_model", "judge_source"))
        result["energy_metadata"] = recorded(rows, (
            "measurement_boundary", "network_measurement_boundary",
            "cloud_estimation_boundary", "energy_calculation_method",
            "cpu_attribution_method", "gpu_attribution_method", "cloud_energy_method",
            "package_window_source"))
        result["provenance_note"] = (
            "Correctness uses recorded verdict/is_correct and the recorded evaluation methods; "
            "legacy semantic verdicts are not new deterministic accuracy. Energy retains the "
            "recorded boundary and attributed CPU-time/GPU shares: it is not whole-machine "
            "consumption or an independent validation. Failed/incomplete attempts contribute "
            "only where energy was available; components outside the boundary are not recovered."
        )
        results.append(result)
    return results


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
