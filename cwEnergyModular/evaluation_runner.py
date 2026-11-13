"""Generic result and energy association utilities for CasualWatt."""
from __future__ import annotations

import csv
import json
import math
import random
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Union

# Import evaluation schema for structured export
from evaluation_schema import (
    EVALUATION_RESULT_COLUMNS,
    EVALUATION_SUMMARY_COLUMNS,
    export_evaluation_results,
    export_evaluation_summary,
    compute_pass_at_k_unbiased,
    wilson_ci,
)

# Bootstrap a cluster: il seme e' fissato perche' l'intervallo deve essere
# rigenerabile dalla stessa riga, non un numero diverso a ogni esecuzione.
BOOTSTRAP_SEED = 20261104
BOOTSTRAP_RESAMPLES = 2000


_TASK_NOTE_PREFIX = "CW_TASK_ID_V1="


def _finite_energy(value: Any) -> Optional[float]:
    """Parse and validate a finite energy value from a CSV cell."""
    if value in (None, "", "N/A"):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


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


# Vocabolario chiuso dei motivi di N/A (piano.DOCX Parte 2, §3.1): quattro
# stati, non testo libero. Gli alias legacy sono ricondotti a questi.
CANONICAL_NONE_REASONS = ("judge_abstained", "judge_uncalibrated",
                          "evaluation_failed", "human_review_required")

_NONE_REASON_ALIASES = {
    "extraction_failed": "evaluation_failed",
    "human_gate_blocked": "human_review_required",
    "judge_abstained": "judge_abstained",
    "judge_uncalibrated": "judge_uncalibrated",
    "evaluation_failed": "evaluation_failed",
    "human_review_required": "human_review_required",
}

_SCORING_NOTE_PREFIX = "CW_SCORING_V1="


def canonical_none_reason(reason: Any) -> str:
    """Riconduce un motivo di N/A al vocabolario canonico; stringa vuota resta vuota.

    Un motivo assente non e' un motivo dichiarato: restituire "" invece di
    inventare "evaluation_failed" conserva la differenza fra "non registrato"
    e "fallito". Gli alias legacy (extraction_failed, human_gate_blocked) sono
    mappati; un token gia' canonico o sconosciuto passa invariato.
    """
    text = str(reason or "").strip()
    if not text:
        return ""
    return _NONE_REASON_ALIASES.get(text, text)


def _is_correct_bool(record: Mapping[str, Any]) -> Optional[bool]:
    """Forma booleana a tre stati del verdetto: true/false/null (mai unscored)."""
    verdict = record_verdict(record)
    return True if verdict == "correct" else (
        False if verdict == "incorrect" else None)


def final_verdict(record: Mapping[str, Any]) -> str:
    """Verdetto dichiarato a quattro stati, separato da is_correct (tre stati).

    correct/incorrect/indeterminate vengono dal verdetto registrato. Un ramo
    bloccato dal gate di calibrazione (judge_uncalibrated) resta ``unscored``:
    il giudice non e' stato chiamato perche' il ramo non e' validato, quindi
    non e' un fallimento dello scoring ma una non-valutazione (§7.1 del piano).
    Confondere i due stati attribuirebbe al modello un errore che non ha
    commesso.
    """
    verdict = record_verdict(record)
    if verdict == "indeterminate":
        if canonical_none_reason(record.get("verdict_none_reason")) == "judge_uncalibrated":
            return "unscored"
    return verdict


def notes_with_scoring_block(record: Mapping[str, Any]) -> str:
    """Serializza il blocco di scoring CW_SCORING_V1 nella colonna notes (P5).

    Come CW_TASK_ID_V1, si sostituisce solo il proprio metadato e il testo
    delle note originali resta intatto: lo schema CSV congelato non si allarga.
    Il blocco e' JSON machine-recoverable, non prosa.
    """
    notes = record.get("notes", "")
    text = "; ".join(str(n) for n in notes) if isinstance(notes, (list, tuple)) else str(notes or "")
    block = {
        "final_verdict": final_verdict(record),
        "is_correct": _is_correct_bool(record),
        "scoring_method": str(record.get("scoring_method", "")).strip(),
        "none_reason": canonical_none_reason(record.get("verdict_none_reason")),
    }
    lines = [line for line in text.splitlines() if not line.startswith(_SCORING_NOTE_PREFIX)]
    lines.append(_SCORING_NOTE_PREFIX + json.dumps(block, ensure_ascii=True, sort_keys=True))
    return "\n".join(lines)


def record_scoring_block(record: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """Rilegge il blocco di scoring dalle notes; None se assente o illeggibile.

    None e non un dict vuoto: un dizionario vuoto sembrerebbe uno scoring
    registrato quando non lo e'.
    """
    for line in str(record.get("notes", "")).splitlines():
        if line.startswith(_SCORING_NOTE_PREFIX):
            try:
                return json.loads(line[len(_SCORING_NOTE_PREFIX):])
            except (ValueError, TypeError):
                return None
    return None


def _eligible_energy_value(row: Mapping[str, Any], energy_key: str) -> Optional[float]:
    """Energia consumata eleggibile per il numeratore di ECPC, oppure None.

    Stessa regola del ciclo principale di ``summarize_records``: valore finito
    non negativo, senza flag invalidante, con finestra di contatore valida. Un
    ``energy_j`` generico senza flag e' accettato per compatibilita' (la
    validita' metrologica non e' provata, ma la riga non e' esclusa); una riga
    unificata senza ``active_valid`` e' esclusa perche' non verificabile. La
    regola vive in un solo posto perche' il totale complessivo e quello per
    categoria non possono divergere sulla stessa riga.
    """
    raw = row.get(energy_key)
    if raw in (None, "", "N/A"):
        return None
    value = _finite_energy(raw)
    if value is None or value < 0:
        return None
    flags = {key: str(row[key]).strip().lower()
             for key in ("energy_valid", "active_valid") if key in row}
    rejected = any(flag in ("false", "0", "0.0") for flag in flags.values())
    unknown = any(flag not in ("true", "1", "1.0", "false", "0", "0.0")
                  for flag in flags.values())
    unified = energy_key == "end_to_end_energy_j"
    unverified = unknown or (unified and "active_valid" not in flags) or not flags
    if rejected:
        return None
    if str(row.get("package_window_source", "")).strip().lower() in (
            "counter-invalid", "unavailable"):
        return None
    if unknown or (unified and unverified):
        return None
    return value


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
      - chi2_correction: il flag *chiesto* dal chiamante, anche quando non c'e'
        un chi2 su cui applicarlo
      - correction_applied: cosa e' entrato davvero nella formula --
        "yes" con chi2 corretto, "no" con chi2 non corretto, "not_applicable"
        quando b+c < 10 e si usa il binomiale esatto (nessun chi2 da correggere)
      - delta_acc = (b-c)/n su determinate (n = determinate)
      - delta_ci: intervallo di Newcombe (metodo 10) con phi corretto,
        None se non calcolabile
      - note

    L'intervallo combina i due intervalli di Wilson marginali con il phi
    corretto del 2x2. Non e' la somma in quadratura degli errori standard
    marginali, che ignora l'appaiamento fra le due misure sullo stesso task.
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
            correction_applied = "yes"
        else:
            chi2 = (b - c) ** 2 / discordant
            correction_applied = "no"
        z = _normal_ppf(1 - alpha / 2)
        p_chi2 = _chi2_survival_1df(chi2)
    else:
        chi2 = None
        p_chi2 = None
        # Con b+c < 10 il test e' quello binomiale esatto: non c'e' un chi2 da
        # correggere. "no" direbbe che la correzione e' stata disattivata.
        correction_applied = "not_applicable"
    delta = (b - c) / n_determinate if n_determinate else None
    # Intervallo di Newcombe (metodo 10): i due intervalli di Wilson marginali
    # si combinano con il phi corretto del 2x2, non in quadratura fra loro.
    if n_determinate and delta is not None:
        p_a = (a + b) / n_determinate
        p_bv = (a + c) / n_determinate
        z = _normal_ppf(1 - alpha / 2)
        denom = 1 + z * z / n_determinate
        centre_a = (p_a + z * z / (2 * n_determinate)) / denom
        centre_b = (p_bv + z * z / (2 * n_determinate)) / denom
        half_a = z * math.sqrt(
            p_a * (1 - p_a) / n_determinate
            + z * z / (4 * n_determinate * n_determinate)
        ) / denom
        half_b = z * math.sqrt(
            p_bv * (1 - p_bv) / n_determinate
            + z * z / (4 * n_determinate * n_determinate)
        ) / denom
        lo_a = centre_a - half_a
        hi_a = centre_a + half_a
        lo_b = centre_b - half_b
        hi_b = centre_b + half_b
        # phi corretto di Newcombe: la covarianza positiva si riduce di n/2;
        # con un marginale vuoto il coefficiente non e' definito e vale zero.
        marg_prod = (a + b) * (c + d) * (a + c) * (b + d)
        if marg_prod == 0:
            phi = 0.0
        else:
            cov = a * d - b * c
            if cov > 0:
                cov = max(cov - n_determinate / 2.0, 0.0)
            phi = cov / math.sqrt(marg_prod)
        span_low = p_a - lo_a
        span_high_b = hi_b - p_bv
        lower = delta - math.sqrt(max(
            0.0,
            span_low * span_low
            - 2.0 * phi * span_low * span_high_b
            + span_high_b * span_high_b,
        ))
        span_high_a = hi_a - p_a
        span_low_b = p_bv - lo_b
        upper = delta + math.sqrt(max(
            0.0,
            span_high_a * span_high_a
            - 2.0 * phi * span_high_a * span_low_b
            + span_low_b * span_low_b,
        ))
        delta_ci = [round(lower, 6), round(upper, 6)]
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
        "correction_applied": correction_applied,
        "note": (
            "indecis: nessuna coppia discordante" if indecis else ""
        ),
    }


def paired_summary(
    verdicts_a: Iterable[Any],
    verdicts_b: Iterable[Any],
    task_ids: Iterable[Any],
    reduction: str = "first",
    **mcnemar_kwargs: Any,
) -> dict[str, Any]:
    """Riduce una coppia per task e applica `paired_mcnemar`.

    E' il ponte fra righe di un report e il test: le repliche della stessa
    richiesta non sono prove indipendenti, quindi la matrice si costruisce su
    una coppia per task, con una regola dichiarata prima di guardare l'esito.
    L'unica regola ammessa oggi e' `first`: la prima riga incontrata per ogni
    task, nell'ordine dell'input (che nei report e' l'ordine dei file).

    Le righe senza identita' del task non sono appaiabili: sono contate in
    `n_without_task` e non scartate in silenzio. `n_tasks_with_replicates` dice
    quante coppie la riduzione ha scartato, cioe' quanto la scelta della regola
    pesa su questo insieme di dati. Il resto del dict e' quello di
    `paired_mcnemar`, che riceve i verdi grezzi e applica la propria coerenza.
    """
    a = list(verdicts_a)
    b = list(verdicts_b)
    ids = list(task_ids)
    if not (len(a) == len(b) == len(ids)):
        raise ValueError(
            "paired_summary: verdetti e identita' del task devono avere la "
            "stessa lunghezza"
        )
    if reduction != "first":
        raise ValueError(
            f"paired_summary: riduzione non supportata {reduction!r} (ammessa: 'first')"
        )
    prima_coppia: dict[str, tuple[Any, Any]] = {}
    repliche: Counter[str] = Counter()
    n_without_task = 0
    for va, vb, ident in zip(a, b, ids):
        task = _task_id(ident)
        if task is None:
            n_without_task += 1
            continue
        repliche[task] += 1
        if task not in prima_coppia:
            prima_coppia[task] = (va, vb)
    esito = paired_mcnemar(
        [coppia[0] for coppia in prima_coppia.values()],
        [coppia[1] for coppia in prima_coppia.values()],
        **mcnemar_kwargs,
    )
    esito["reduction"] = reduction
    esito["n_tasks"] = len(prima_coppia)
    esito["n_without_task"] = n_without_task
    esito["n_tasks_with_replicates"] = sum(1 for c in repliche.values() if c > 1)
    return esito


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
                      energy_key: str = "energy_j",
                      category_key: str = "category") -> dict[str, Any]:
    """Aggrega verdetti ed energia disponibile di TUTTI i tentativi.

    Il costo per corretta e' somma energia / tutte le corrette, non la media
    dell'energia delle sole corrette. Le mediane restano diagnostiche firmate.
    `cluster_key` identifica il task: B7 non ammette identita' parziali nel CI.
    
    Nuovo: calcola ECPC e campi di validazione per categoria (stratificati per
    `category_key`). Per ogni categoria restituisce:
    - ecpc_j / ecpc_model_j: energia del modello su TUTTE le righe / corrette
    - ecpc_system_j: (E_model + E_judge)/corrette, solo se il giudice e' misurato
      su ogni riga; ecpc_status dice complete | partial | unavailable
    - ECPC_verified: somma energia / corrette dove lo scoring e' deterministico
    - ECPC_conditional: somma energia / corrette dove lo scoring e' LLM Judge
    - scoring_coverage: frazione di righe determinate (is_correct != null)
    - judge_validation_status: validated | unvalidated | gated | failed
    """
    rows = list(records)
    verdicts = Counter(str(record_verdict(row)) for row in rows)
    determinate = [row for row in rows if record_verdict(row)
                   in ("correct", "incorrect")]
    correct = sum(record_verdict(row) == "correct"
                  for row in determinate)

    energy_values = [(row, _finite_energy(row.get(energy_key))) for row in rows]
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
                 if (value := _finite_energy(row.get("duration_s"))) is not None]
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
        "misurano direttamente l'intra-correlazione. Questo riepilogo vale per "
        "una sola serie di verdetti: il confronto fra due sistemi sullo stesso "
        "task e' paired_mcnemar"
        if cluster["interval"] is not None else
        f"intervallo a livello di task non calcolabile: {cluster['reason']}"
    )
    # --- Category-stratified ECPC with validation fields ---
    # Group rows by category
    from collections import defaultdict
    cat_rows = defaultdict(list)
    for row in rows:
        cat = str(row.get(category_key, "unknown"))
        cat_rows[cat].append(row)
    
    category_results = {}
    for cat, cat_rows_list in cat_rows.items():
        # Determinate rows in this category
        cat_determinate = [r for r in cat_rows_list if record_verdict(r) in ("correct", "incorrect")]
        cat_correct = sum(1 for r in cat_determinate if record_verdict(r) == "correct")
        cat_n_determinate = len(cat_determinate)
        
        # ECPC = somma dell'energia di TUTTE le righe eleggibili (errori e
        # indeterminati inclusi) / numero di corrette. L'eleggibilita' usa lo
        # stesso helper del totale complessivo: una riga non puo' essere
        # eleggibile di la' e non eleggibile qui.
        cat_total_energy = 0.0
        cat_eligible_count = 0
        cat_eligible_rows = []
        for row in cat_rows_list:
            value = _eligible_energy_value(row, energy_key)
            if value is not None:
                cat_total_energy += value
                cat_eligible_count += 1
                cat_eligible_rows.append((row, value))

        cat_total_energy = cat_total_energy if cat_eligible_count > 0 else None
        cat_correct_with_energy = sum(1 for r in cat_rows_list
                                       if record_verdict(r) == "correct"
                                       and _eligible_energy_value(r, energy_key) is not None)

        # ECPC primario (solo modello): energia del modello per corretta.
        cat_ecpc = cat_total_energy / cat_correct if cat_correct and cat_total_energy is not None else None

        # Il bootstrap ricampiona lo STESSO estimando del punto stimato: pairs
        # su TUTTE le righe eleggibili, con indicatore 1/0, non sulle sole
        # corrette (che darebbero un rapporto diverso e un cluster in meno).
        ecpc_pairs = [(1 if record_verdict(row) == "correct" else 0,
                       value, record_task_id(row))
                      for row, value in cat_eligible_rows]
        
        # Use taxonomy_ecpc's bootstrap function
        ecpc_bootstrap = None
        if ecpc_pairs:
            try:
                from taxonomy_ecpc import _ecpc_bootstrap
                ecpc_bootstrap = _ecpc_bootstrap(ecpc_pairs)
            except ImportError:
                ecpc_bootstrap = {"interval": None, "reason": "taxonomy_ecpc module not available", 
                                 "n_effective_tasks": 0, "n_rows": len(ecpc_pairs)}
        
        # Stratify by scoring_method for validation regimes
        cat_verified_energy = []
        cat_conditional_energy = []
        cat_unvalidated_energy = []
        cat_failed_energy = []
        cat_scoring_methods = Counter()
        cat_judge_statuses = Counter()
        cat_human_ref_available = 0
        
        for row, value in [(r, _finite_energy(r.get(energy_key))) for r in cat_rows_list]:
            if value is None or value < 0:
                continue
            scoring_method = str(row.get("scoring_method", "none")).strip().lower()
            judge_status = str(row.get("judge_validation_status", "unvalidated")).strip().lower()
            human_ref = row.get("human_reference_available", False)
            if human_ref:
                cat_human_ref_available += 1
            cat_scoring_methods[scoring_method] += 1
            cat_judge_statuses[judge_status] += 1
            
            if scoring_method == "deterministic" and record_verdict(row) == "correct":
                cat_verified_energy.append(value)
            elif scoring_method == "llm_judge" and record_verdict(row) == "correct":
                cat_conditional_energy.append(value)
            elif judge_status == "validated" and record_verdict(row) == "correct":
                cat_conditional_energy.append(value)
            elif judge_status in ("gated", "failed") and record_verdict(row) == "correct":
                cat_failed_energy.append(value)
            elif record_verdict(row) == "correct":
                cat_unvalidated_energy.append(value)
        
        cat_correct_verified = sum(1 for r in cat_rows_list 
                                   if record_verdict(r) == "correct" 
                                   and str(r.get("scoring_method", "")).strip().lower() == "deterministic")
        cat_correct_conditional = sum(1 for r in cat_rows_list 
                                      if record_verdict(r) == "correct" 
                                      and str(r.get("scoring_method", "")).strip().lower() in ("llm_judge", "human_calibrated"))
        
        ecpc_verified = (sum(cat_verified_energy) / cat_correct_verified 
                        if cat_correct_verified and cat_verified_energy else None)
        ecpc_conditional = (sum(cat_conditional_energy) / cat_correct_conditional
                           if cat_correct_conditional and cat_conditional_energy else None)
        
        # Coverage = #{is_correct != null}/N: frazione di righe determinate,
        # non frazione di righe con un'energia o un metodo dichiarato (§9 P0 #4).
        scoring_coverage = cat_n_determinate / len(cat_rows_list) if cat_rows_list else 0

        # ECPC_status distingue un totale definitivo da un subtotale (§9 P0 #5).
        if cat_ecpc is None:
            ecpc_status = "unavailable"
        elif cat_eligible_count == len(cat_rows_list):
            ecpc_status = "complete"
        else:
            ecpc_status = "partial"

        # ECPC_system = (E_model + E_judge)/N_correct, secondario: si calcola
        # solo se OGNI riga ha un'energia del giudice finita. Assumere zero per
        # l'energia mancante sottostimerebbe il costo di sistema (§9 P1 #8).
        judge_values = [_finite_energy(r.get("judge_energy_j")) for r in cat_rows_list]
        judge_present = [v for v in judge_values if v is not None]
        judge_energy_total = sum(judge_present) if judge_present else None
        n_judge_missing = sum(1 for v in judge_values if v is None)
        if cat_ecpc is not None and n_judge_missing == 0 and judge_energy_total is not None:
            ecpc_system = (cat_total_energy + judge_energy_total) / cat_correct
            ecpc_system_reason = ""
        elif cat_ecpc is None:
            ecpc_system = None
            ecpc_system_reason = "no correct answers or no eligible model energy"
        else:
            ecpc_system = None
            ecpc_system_reason = (f"judge energy missing for {n_judge_missing} row(s): "
                                  "ECPC_system would assume zero for the missing judge energy")
        
        # Overall judge validation status for category
        if cat_judge_statuses.get("failed", 0) > 0:
            judge_validation_status = "failed"
        elif cat_judge_statuses.get("gated", 0) > 0:
            judge_validation_status = "gated"
        elif cat_judge_statuses.get("validated", 0) > 0:
            judge_validation_status = "validated"
        else:
            judge_validation_status = "unvalidated"
        
        category_results[cat] = {
            "n_total": len(cat_rows_list),
            "n_determinate": cat_n_determinate,
            "n_correct": cat_correct,
            "n_correct_with_eligible_energy": cat_correct_with_energy,
            "accuracy_on_determinate": cat_correct / cat_n_determinate if cat_n_determinate else None,
            "total_energy_j": round(cat_total_energy, 6) if cat_total_energy is not None else None,
            "eligible_energy_rows": cat_eligible_count,
            "ecpc_j": round(cat_ecpc, 6) if cat_ecpc is not None else None,
            "ecpc_status": ecpc_status,
            "ecpc_model_j": round(cat_ecpc, 6) if cat_ecpc is not None else None,
            "ecpc_system_j": round(ecpc_system, 6) if ecpc_system is not None else None,
            "ecpc_system_reason": ecpc_system_reason,
            "judge_energy_total_j": round(judge_energy_total, 6) if judge_energy_total is not None else None,
            "ecpc_cluster_bootstrap_95": ecpc_bootstrap["interval"] if ecpc_bootstrap else None,
            "ecpc_bootstrap_note": ecpc_bootstrap["reason"] if ecpc_bootstrap and ecpc_bootstrap["interval"] is None else 
                                    (f"cluster bootstrap: n_effective_tasks={ecpc_bootstrap['n_effective_tasks']}, "
                                     f"n_rows={ecpc_bootstrap['n_rows']}, resamples={ecpc_bootstrap['resamples']}, "
                                     f"seed={ecpc_bootstrap['seed']}" if ecpc_bootstrap and ecpc_bootstrap["interval"] is not None else ""),
            "ecpc_verified": round(ecpc_verified, 6) if ecpc_verified is not None else None,
            "ecpc_conditional": round(ecpc_conditional, 6) if ecpc_conditional is not None else None,
            "scoring_coverage": round(scoring_coverage, 6),
            "scoring_methods": dict(cat_scoring_methods),
            "judge_validation_status": judge_validation_status,
            "judge_statuses": dict(cat_judge_statuses),
            "human_reference_available": cat_human_ref_available,
            "n_correct_verified": cat_correct_verified,
            "n_correct_conditional": cat_correct_conditional,
        }
    
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
        # New category-stratified fields
        "categories": category_results,
        # Selective prediction / coverage reporting
        "verdict_coverage": len(determinate) / len(rows) if rows else None,
        "verdict_accuracy_covered": correct / len(determinate) if determinate else None,
        "verdict_none_count": sum(record_verdict(row) == "indeterminate" for row in rows),
        "verdict_none_reason": dict(Counter(
            canonical_none_reason(row.get("verdict_none_reason")) or "unknown"
            for row in rows
            if record_verdict(row) == "indeterminate"
        )),
        "verdict_none_reason_note": "Counts of 'indeterminate' verdicts by canonical reason (judge_abstained, judge_uncalibrated, evaluation_failed, human_review_required); legacy aliases are mapped, an absent reason is 'unknown'.",
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


def export_evaluation_results_from_records(
    records: Iterable[Mapping[str, Any]],
    path: Path,
    run_id: str = "",
    model_name: str = "",
    mode: str = "a"
) -> int:
    """
    Esporta i record di valutazione nel formato EVALUATION_RESULT_COLUMNS.
    Collega per run_id, task_id, batch_id, point_id al CSV energetico.
    """
    from datetime import datetime
    eval_records = []
    for row in records:
        eval_rec = {
            "run_id": run_id or row.get("run_id", ""),
            "session_id": row.get("session_id", ""),
            "batch_id": row.get("batch_id", ""),
            "point_id": row.get("point_id", ""),
            "task_id": row.get("task_id", ""),
            "task_type": "factual",  # default, overridden below
            "prompt_id": row.get("prompt_id", ""),
            "model_name": model_name or row.get("model_name", ""),
            "model_label": row.get("model_label", ""),
            "provider": row.get("provider", ""),
            "prompt": row.get("prompt", row.get("question", "")),
            "ground_truth": row.get("ground_truth", ""),
            "model_response": row.get("model_response", row.get("response", row.get("text", ""))),
            "extracted_answer": row.get("extracted_answer", ""),
            "tests_total": row.get("tests_total", 0),
            "tests_passed": row.get("tests_passed", 0),
            "pass_rate": row.get("pass_rate", 0.0),
            "pass_at_1": 1 if row.get("passed", row.get("is_correct") in (1, 1.0, True, "1", "true")) else 0,
            "pass_at_k": 1 if row.get("passed", row.get("is_correct") in (1, 1.0, True, "1", "true")) else 0,
            "k_value": 1,
            "pass_at_k_unbiased": 1.0 if row.get("passed", row.get("is_correct") in (1, 1.0, True, "1", "true")) else 0.0,
            "compile_rate": row.get("compile_rate", 0.0),
            "runtime_success_rate": row.get("runtime_success_rate", 0.0),
            "factual_claims": row.get("factual_claims", 0),
            "factual_correct": row.get("factual_correct", 0),
            "factual_incorrect": row.get("factual_incorrect", 0),
            "factual_unverifiable": row.get("factual_unverifiable", 0),
            "factual_accuracy": row.get("factual_accuracy", 0.0),
            "factual_precision": row.get("factual_precision", 0.0),
            "factual_recall": row.get("factual_recall", 0.0),
            "factual_f1": row.get("factual_f1", 0.0),
            "human_score": row.get("human_score", ""),
            "human_score_raw": row.get("human_score_raw", ""),
            "llm_judge_score": row.get("llm_judge_score", row.get("acc_comp", "")),
            "llm_judge_model": row.get("llm_judge_model", row.get("judge_model", "")),
            "rubric_scores": row.get("rubric_scores", ""),
            "rubric_schema": row.get("rubric_schema", ""),
            "wilson_ci_lower": row.get("wilson_ci_lower", ""),
            "wilson_ci_upper": row.get("wilson_ci_upper", ""),
            "bootstrap_ci_lower": row.get("bootstrap_ci_lower", ""),
            "bootstrap_ci_upper": row.get("bootstrap_ci_upper", ""),
            "n_effective_tasks": row.get("n_effective_tasks", 1),
            "mcnemar_p_exact": row.get("mcnemar_p_exact", ""),
            "mcnemar_ci_lower": row.get("mcnemar_ci_lower", ""),
            "mcnemar_ci_upper": row.get("mcnemar_ci_upper", ""),
            "mcnemar_verdict": row.get("mcnemar_verdict", ""),
            "energy_scope": row.get("energy_scope", "attributed"),
            "energy_per_task_j": row.get("energy_per_task_j", row.get("end_to_end_energy_j", "")),
            "energy_per_token_j": row.get("energy_per_token_j", row.get("energy_per_total_token_j", "")),
            "latency_ms": row.get("latency_ms", round(row.get("duration_s", 0) * 1000) if row.get("duration_s") else ""),
            "timestamp": row.get("timestamp", datetime.utcnow().isoformat() + "Z"),
            "run_mode": row.get("run_mode", "single"),
            "seed": row.get("seed", ""),
            "notes": row.get("notes", ""),
            "eval_method": row.get("eval_method", row.get("eval_mode", "")),
            "eval_version": row.get("eval_version", ""),
            "ground_truth_source": row.get("ground_truth_source", ""),
        }
        # Infer task_type
        if row.get("tests_total", 0) > 0:
            eval_rec["task_type"] = "coding"
        elif row.get("factual_claims", 0) > 0:
            eval_rec["task_type"] = "factual"
        elif row.get("rubric_scores"):
            eval_rec["task_type"] = "quality"
        else:
            eval_rec["task_type"] = "reasoning"
        eval_records.append(eval_rec)
    
    return export_evaluation_results(eval_records, path, mode=mode)


def export_evaluation_summary_from_results(
    summary: Mapping[str, Any],
    path: Path,
    run_id: str = "",
    model_name: str = "",
    mode: str = "a"
) -> int:
    """
    Esporta il riepilogo aggregato nel formato EVALUATION_SUMMARY_COLUMNS.
    """
    from datetime import datetime
    wilson = summary.get("accuracy_wilson_95")
    cluster = summary.get("accuracy_cluster_bootstrap_95")
    summary_rec = {
        "run_id": run_id or summary.get("run_id", ""),
        "model_name": model_name or summary.get("model_name", ""),
        "model_label": summary.get("model_label", ""),
        "task_type": summary.get("task_type", ""),
        "n_tasks": summary.get("n_tasks", summary.get("n_total", 0)),
        "n_tasks_evaluated": summary.get("n_tasks_evaluated", summary.get("n_determinate", 0)),
        "pass_at_1_mean": summary.get("pass_at_1_mean", ""),
        "pass_at_k_mean": summary.get("pass_at_k_mean", ""),
        "pass_at_k_unbiased_mean": summary.get("pass_at_k_unbiased_mean", ""),
        "compile_rate_mean": summary.get("compile_rate_mean", ""),
        "runtime_success_rate_mean": summary.get("runtime_success_rate_mean", ""),
        "factual_accuracy_mean": summary.get("factual_accuracy_mean", summary.get("accuracy_on_determinate", "")),
        "factual_precision_mean": summary.get("factual_precision_mean", ""),
        "factual_recall_mean": summary.get("factual_recall_mean", ""),
        "factual_f1_mean": summary.get("factual_f1_mean", ""),
        "human_score_mean": summary.get("human_score_mean", ""),
        "human_score_ci_lower": summary.get("human_score_ci_lower", ""),
        "human_score_ci_upper": summary.get("human_score_ci_upper", ""),
        "llm_judge_score_mean": summary.get("llm_judge_score_mean", ""),
        "llm_judge_agreement": summary.get("llm_judge_agreement", ""),
        "accuracy_mean": summary.get("accuracy_mean", summary.get("accuracy_on_determinate", "")),
        "wilson_ci_lower": summary.get("wilson_ci_lower", wilson[0] if wilson else ""),
        "wilson_ci_upper": summary.get("wilson_ci_upper", wilson[1] if wilson else ""),
        "bootstrap_ci_lower": summary.get("bootstrap_ci_lower", cluster[0] if cluster else ""),
        "bootstrap_ci_upper": summary.get("bootstrap_ci_upper", cluster[1] if cluster else ""),
        "n_effective_tasks": summary.get("n_effective_tasks", summary.get("n_effective_tasks", "")),
        "energy_per_task_j_mean": summary.get("energy_per_task_j_mean", summary.get("median_energy_j", "")),
        "energy_per_task_j_median": summary.get("energy_per_task_j_median", summary.get("median_energy_j", "")),
        "energy_per_token_j_mean": summary.get("energy_per_token_j_mean", ""),
        "latency_ms_mean": summary.get("latency_ms_mean", round(summary.get("median_duration_s", 0) * 1000) if summary.get("median_duration_s") else ""),
        "latency_ms_median": summary.get("latency_ms_median", round(summary.get("median_duration_s", 0) * 1000) if summary.get("median_duration_s") else ""),
        "paired_with_model": summary.get("paired_with_model", ""),
        "mcnemar_p_exact": summary.get("mcnemar_p_exact", ""),
        "mcnemar_ci_lower": summary.get("mcnemar_ci_lower", ""),
        "mcnemar_ci_upper": summary.get("mcnemar_ci_upper", ""),
        "mcnemar_verdict": summary.get("mcnemar_verdict", ""),
        "delta_accuracy": summary.get("delta_accuracy", ""),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "notes": summary.get("notes", ""),
    }
    return export_evaluation_summary([summary_rec], path, mode=mode)


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
