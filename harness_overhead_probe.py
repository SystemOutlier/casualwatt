#!/usr/bin/env python3
"""A-B-A del costo dell'harness di telemetria Ollama.

Domanda: `monitor_ollama.py`, che ogni 0,5 s enumera i processi con psutil e
interroga `/api/ps`, sposta la potenza del package misurata dal contatore EMI
durante le stesse richieste?

Disegno, dichiarato prima dei dati:

- riferimento: la sonda EMI di questo script, attiva a 100 ms in **tutte** le
  fasi. Il suo costo e' costante e resta dentro ogni condizione, quindi i delta
  A-B-A misurano il costo **incrementale** dell'harness, non il costo
  zero-osservatore (che richiederebbe un wattmetro esterno);
- baseline: 3 finestre idle da 30 s prima e 3 dopo, con settling P1.5
  (media mobile a 10 s stabile entro 0,5 W, tetto 120 s);
- stato: due warm-up scartati con lo stesso prompt e `keep_alive = -1`, poi
  `/api/ps` verificato prima e dopo; il modello resta residente per tutto il
  run. La geometria dei warm-up non e' quella di P1.4 (512,128): qui serve solo
  caricare pesi e cache, non misurare token;
- carico: 4 richieste per fase, stesso modello, prompt, opzioni e `keep_alive`,
  invii a 6 s, coda di 2 s;
- tre cicli A-B-A. In A e A2 le richieste sono guidate da questo script, senza
  campionamento psutil; in B le guida `monitor_ollama.py` con lo stesso carico.
  Il riferimento EMI e la regola degli incrementi contenuti sono identici;
- nessuna sottrazione del costo dell'osservatore (P1.4): si misura e si
  dichiara;
- criterio: "non distinguibile dal drift" solo se, per ogni ciclo,
  |B - media(A1,A2)| non supera |A2 - A1| **e** resta sotto 1,0 W, la scala
  assoluta gia' congelata in P4.5. Altrimenti si riporta l'intervallo osservato.

Cio' che questo script non fa: non e' un canale di misura, non entra in
`MEASURED_METHODS`, non calcola energia di protocollo, non modifica la
produzione. Le energie per finestra sono diagnostiche.

Uso:
  python harness_overhead_probe.py --tag harness_overhead_20261025

I file finiscono in `experiment_results/`: sonda EMI, finestre delle richieste
guidate dallo script, telemetria e richieste dell'harness per ogni fase B,
riepilogo JSON e tabella delle finestre.
"""
import argparse
import csv
import hashlib
import json
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from cwEnergyModular.energy.emi_backend import EMICounterBackend
except ImportError:
    EMICounterBackend = None

from monitor_ollama import parse_keep_alive

PWH_TO_J = 3.6e-9
STABLE_TOL_W = 0.5
STABLE_WINDOW_S = 10.0
SCALE_W = 1.0
REQUEST_COLUMNS = [
    "phase", "cycle", "request_index", "status", "http_status", "error",
    "t_send_mono_ns", "t_first_token_mono_ns", "t_end_mono_ns",
    "window_s", "ttft_s", "prompt_eval_count", "eval_count", "done_reason",
    "response_chars", "response_sha256", "response_text",
]
PROBE_COLUMNS = [
    "phase", "cycle", "mono_before_ns", "mono_after_ns", "mono_mid_ns",
    "utc", "ts_100ns", "pkg_pwh",
]


class Sampler(threading.Thread):
    """Letture EMI continue con etichetta di fase, condivise con l'analisi."""

    def __init__(self, backend, interval):
        super().__init__(daemon=True)
        self.backend = backend
        self.interval = interval
        self.stop_event = threading.Event()
        self._lock = threading.Lock()
        self._rows = []
        self._phase = "init"
        self._cycle = 0
        self.start_error = ""

    def set_phase(self, phase, cycle):
        with self._lock:
            self._phase = phase
            self._cycle = cycle

    def run(self):
        next_at = time.monotonic()
        try:
            while not self.stop_event.is_set():
                before = time.monotonic_ns()
                domains = self.backend.read_domains()
                after = time.monotonic_ns()
                if domains:
                    _, ts_100ns, pkg_pwh = domains["pkg"]
                    with self._lock:
                        phase = self._phase
                        cycle = self._cycle
                    row = {
                        "phase": phase,
                        "cycle": cycle,
                        "mono_before_ns": before,
                        "mono_after_ns": after,
                        "mono_mid_ns": (before + after) // 2,
                        "utc": datetime.now(timezone.utc).isoformat(
                            timespec="milliseconds"
                        ),
                        "ts_100ns": ts_100ns,
                        "pkg_pwh": pkg_pwh,
                    }
                    with self._lock:
                        self._rows.append(row)
                next_at += self.interval
                delay = next_at - time.monotonic()
                if delay > 0:
                    self.stop_event.wait(delay)
                else:
                    next_at = time.monotonic()
        except BaseException as exc:                    # noqa: BLE001
            self.start_error = f"{type(exc).__name__}: {exc}"

    def snapshot(self):
        with self._lock:
            return list(self._rows)


def contained_metrics(rows, start_ns, end_ns):
    """Incrementi EMI interamente nella finestra, piu' i bordi contati."""
    energy_pwh = 0
    covered_ns = 0
    contained = 0
    straddle = 0
    negatives = 0
    for a, b in zip(rows, rows[1:]):
        if start_ns <= a["mono_mid_ns"] and b["mono_mid_ns"] <= end_ns:
            delta = b["pkg_pwh"] - a["pkg_pwh"]
            energy_pwh += delta
            covered_ns += b["mono_mid_ns"] - a["mono_mid_ns"]
            contained += 1
            if delta < 0:
                negatives += 1
        elif (a["mono_mid_ns"] < start_ns < b["mono_mid_ns"]
              or a["mono_mid_ns"] < end_ns < b["mono_mid_ns"]):
            straddle += 1
    window_ns = max(0, end_ns - start_ns)
    energy_j = energy_pwh * PWH_TO_J
    covered_s = covered_ns / 1e9
    return {
        "contained": contained,
        "straddle": straddle,
        "negatives": negatives,
        "energy_j": energy_j,
        "covered_s": covered_s,
        "uncovered_ms": (window_ns - covered_ns) / 1e6,
        "power_w": energy_j / covered_s if covered_s > 0 else None,
    }


def power_between(rows, start_ns, end_ns):
    return contained_metrics(rows, start_ns, end_ns)


def settle(sampler, max_s):
    """Settling P1.5: confronta due blocchi da 10 s, non l'uguaglianza a P_pre."""
    t0 = time.monotonic()
    time.sleep(STABLE_WINDOW_S)
    last = None
    while time.monotonic() - t0 < max_s:
        now = time.monotonic_ns()
        rows = sampler.snapshot()
        cur = power_between(
            rows, now - int(2 * STABLE_WINDOW_S * 1e9),
            now - int(STABLE_WINDOW_S * 1e9),
        )
        prev = power_between(
            rows, now - int(3 * STABLE_WINDOW_S * 1e9),
            now - int(2 * STABLE_WINDOW_S * 1e9),
        )
        if cur["power_w"] is not None and prev["power_w"] is not None:
            last = (cur["power_w"], prev["power_w"])
            if abs(cur["power_w"] - prev["power_w"]) < STABLE_TOL_W:
                return {
                    "elapsed_s": round(time.monotonic() - t0, 3),
                    "p_now_w": round(cur["power_w"], 4),
                    "p_prev_w": round(prev["power_w"], 4),
                    "stable": True,
                }
        time.sleep(5.0)
    return {
        "elapsed_s": round(time.monotonic() - t0, 3),
        "p_now_w": None if last is None else round(last[0], 4),
        "p_prev_w": None if last is None else round(last[1], 4),
        "stable": False,
    }


def baseline_windows(sampler, label, count, seconds):
    windows = []
    for index in range(1, count + 1):
        phase = f"{label}{index}"
        sampler.set_phase(phase, 0)
        time.sleep(0.5)
        start = time.monotonic_ns()
        time.sleep(seconds)
        end = time.monotonic_ns()
        metrics = contained_metrics(sampler.snapshot(), start, end)
        metrics.update({
            "phase": phase,
            "start_mono_ns": start,
            "end_mono_ns": end,
            "window_s": (end - start) / 1e9,
        })
        windows.append(metrics)
        print(f"  {phase}: {metrics['power_w']:.3f} W "
              f"({metrics['contained']} incrementi, "
              f"{metrics['uncovered_ms']:.1f} ms scoperti)", flush=True)
    powers = [w["power_w"] for w in windows if w["power_w"] is not None]
    summary = {
        "windows": windows,
        "median_w": round(statistics.median(powers), 4) if powers else None,
        "range_w": (round(max(powers) - min(powers), 4)
                    if len(powers) > 1 else None),
        "min_w": round(min(powers), 4) if powers else None,
        "max_w": round(max(powers), 4) if powers else None,
    }
    return summary


def parse_generate_line(raw):
    text = raw.strip()
    if not text:
        return None
    payload = json.loads(text.decode("utf-8") if isinstance(raw, bytes) else text)
    if not isinstance(payload, dict):
        raise ValueError("NDJSON line is not an object")
    return payload


def one_request(api_url, model, prompt, options, keep_alive, timeout_s):
    t_send_ns = time.monotonic_ns()
    status = "ok"
    http_status = None
    error = ""
    first_ns = None
    final = {}
    parts = []
    hash_obj = hashlib.sha256()
    body = {
        "model": model,
        "prompt": prompt,
        "stream": True,
        "options": options,
    }
    if keep_alive:
        body["keep_alive"] = parse_keep_alive(keep_alive)
    try:
        request = urllib.request.Request(
            api_url.rstrip("/") + "/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            http_status = response.status
            while True:
                raw = response.readline()
                if not raw:
                    break
                chunk = parse_generate_line(raw)
                if chunk is None:
                    continue
                if chunk.get("error"):
                    status = "api_error"
                    error = str(chunk["error"])
                    break
                text = chunk.get("response")
                if isinstance(text, str):
                    if text and first_ns is None:
                        first_ns = time.monotonic_ns()
                    hash_obj.update(text.encode("utf-8"))
                    parts.append(text)
                if chunk.get("done"):
                    final = chunk
                    break
            if status == "ok" and not final:
                status = "incomplete_stream"
    except urllib.error.HTTPError as exc:
        status = "http_error"
        http_status = exc.code
        try:
            error = exc.read().decode("utf-8", "replace")
        except OSError:
            error = ""
    except urllib.error.URLError as exc:
        status = ("timeout" if isinstance(exc.reason, TimeoutError)
                  else f"connection_error:{type(exc.reason).__name__}")
        error = str(exc)
    except TimeoutError as exc:
        status = "timeout"
        error = f"{type(exc).__name__}: {exc}"
    except OSError as exc:
        status = f"os_error:{type(exc).__name__}"
        error = str(exc)
    except Exception as exc:                            # noqa: BLE001
        status = f"unexpected:{type(exc).__name__}"
        error = str(exc)
    t_end_ns = time.monotonic_ns()
    text = "".join(parts)
    return {
        "status": status,
        "http_status": "" if http_status is None else http_status,
        "error": error,
        "t_send_mono_ns": t_send_ns,
        "t_first_token_mono_ns": "" if first_ns is None else first_ns,
        "t_end_mono_ns": t_end_ns,
        "window_s": round((t_end_ns - t_send_ns) / 1e9, 6),
        "ttft_s": ("" if first_ns is None
                   else round((first_ns - t_send_ns) / 1e9, 6)),
        "prompt_eval_count": final.get("prompt_eval_count", ""),
        "eval_count": final.get("eval_count", ""),
        "done_reason": final.get("done_reason", ""),
        "response_chars": len(text),
        "response_sha256": hash_obj.hexdigest() if text else "",
        "response_text": text,
    }


def api_ps(api_url, timeout_s=2.0):
    """Stato dei modelli residenti, per dichiarare che il modello e' caricato."""
    try:
        with urllib.request.urlopen(
            api_url.rstrip("/") + "/api/ps", timeout=timeout_s
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
        models = [
            {
                "name": item.get("name"),
                "size_bytes": item.get("size"),
                "size_vram_bytes": item.get("size_vram"),
                "expires_at": item.get("expires_at"),
            }
            for item in data.get("models", [])
        ]
        return {"ok": True, "models": models}
    except Exception as exc:                            # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def drive_requests(args, sampler, phase, cycle, path):
    """Guida le richieste delle fasi A senza campionamento psutil."""
    rows = []
    path.parent.mkdir(parents=True, exist_ok=True)
    sampler.set_phase(phase, cycle)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUEST_COLUMNS)
        writer.writeheader()
        handle.flush()
        t0 = time.monotonic()
        for index in range(1, args.requests + 1):
            target = t0 + (index - 1) * args.request_interval
            delay = target - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            row = {"phase": phase, "cycle": cycle, "request_index": index}
            row.update(one_request(
                args.api, args.model, args.prompt, args.options,
                args.keep_alive, args.request_timeout,
            ))
            writer.writerow(row)
            handle.flush()
            rows.append(row)
            print(f"  {phase} r{index}: {row['status']} "
                  f"{row['window_s']} s, {row['eval_count']} token", flush=True)
        time.sleep(args.tail)
    return rows


def run_harness(args, out_dir, tag, cycle):
    sampler_phase = f"c{cycle}_b"
    run_id = f"{tag}_b{cycle}"
    telemetry = out_dir / f"{tag}_telemetry_b{cycle}.csv"
    requests = out_dir / f"{tag}_requests_b{cycle}.csv"
    meta = out_dir / f"{tag}_meta_b{cycle}.json"
    log = out_dir / f"{tag}_harness_b{cycle}.log"
    command = [
        sys.executable, str(args.harness),
        "--interval", "0.5",
        "--requests", str(args.requests),
        "--request-interval", str(args.request_interval),
        "--request-timeout", str(args.request_timeout),
        "--tail", str(args.tail),
        "--model", args.model,
        "--prompt", args.prompt,
        "--options-json", json.dumps(args.options),
        "--keep-alive", args.keep_alive,
        "--run-id", run_id,
        "--output", str(telemetry),
        "--requests-output", str(requests),
        "--meta-output", str(meta),
    ]
    print(f"  {sampler_phase}: {args.harness.name} (run_id={run_id})",
          flush=True)
    started = time.monotonic()
    result = subprocess.run(
        command, capture_output=True, text=True,
        timeout=abs(args.requests * args.request_interval) + 300,
    )
    elapsed = time.monotonic() - started
    log.write_text(
        f"command: {' '.join(command)}\n"
        f"exit: {result.returncode}\n"
        f"elapsed_s: {elapsed:.3f}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}\n",
        encoding="utf-8",
    )
    print(f"  {sampler_phase}: exit {result.returncode} in {elapsed:.1f} s",
          flush=True)
    return {
        "cycle": cycle,
        "phase": sampler_phase,
        "command": command,
        "returncode": result.returncode,
        "elapsed_s": round(elapsed, 3),
        "telemetry_csv": str(telemetry),
        "requests_csv": str(requests),
        "meta_json": str(meta),
        "log": str(log),
        "stdout": result.stdout[-2000:],
        "stderr": result.stderr[-2000:],
    }


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def request_metrics(rows, request):
    start = int(request["t_send_mono_ns"])
    end = int(request["t_end_mono_ns"])
    metrics = contained_metrics(rows, start, end)
    metrics.update({
        "phase": request["phase"],
        "cycle": int(request["cycle"]),
        "request_index": int(request["request_index"]),
        "status": request["status"],
        "window_s": float(request["window_s"]),
        "ttft_s": (float(request["ttft_s"])
                   if request["ttft_s"] not in ("", None) else None),
        "prompt_eval_count": request["prompt_eval_count"],
        "eval_count": request["eval_count"],
        "done_reason": request["done_reason"],
    })
    eval_count = request["eval_count"]
    try:
        tokens = int(eval_count)
    except (TypeError, ValueError):
        tokens = 0
    metrics["j_per_token"] = (
        metrics["energy_j"] / tokens if tokens > 0 else None
    )
    return metrics


def harness_telemetry_summary(path):
    rows = load_csv(path)
    if not rows:
        return {"rows": 0}
    intervals = [float(row["interval_effective_s"]) for row in rows
                 if row["interval_effective_s"]]
    sweeps = [float(row["sweep_duration_s"]) for row in rows
              if row["sweep_duration_s"]]
    cpu = [float(row["observer_cpu_pct"]) for row in rows
           if row["observer_cpu_pct"]]
    cpu_seconds = 0.0
    for row in rows[1:]:
        try:
            cpu_seconds += (float(row["observer_cpu_pct"]) / 100.0
                            * float(row["interval_effective_s"]))
        except (TypeError, ValueError):
            pass
    return {
        "rows": len(rows),
        "interval_median_s": (round(statistics.median(intervals), 4)
                              if intervals else None),
        "sweep_median_s": (round(statistics.median(sweeps), 4)
                           if sweeps else None),
        "sweep_max_s": round(max(sweeps), 4) if sweeps else None,
        "sweep_duty": (round(statistics.median(sweeps)
                             / statistics.median(intervals), 6)
                       if sweeps and intervals else None),
        "observer_cpu_pct_mean": (round(statistics.mean(cpu), 4)
                                  if cpu else None),
        "observer_cpu_pct_max": round(max(cpu), 4) if cpu else None,
        "observer_cpu_seconds": round(cpu_seconds, 4),
    }


def mean_of(values):
    clean = [value for value in values if value is not None]
    return round(statistics.mean(clean), 4) if clean else None


def median_of(values):
    clean = [value for value in values if value is not None]
    return round(statistics.median(clean), 4) if clean else None


def analyze(args, sampler, probe_rows, driven_rows, harness_runs,
            baselines, probe_cpu_s, wall_s):
    offset_values = [
        row["mono_mid_ns"] / 1e9 - row["ts_100ns"] / 1e7
        for row in probe_rows
    ]
    offset = {
        "pairs": len(offset_values),
        "median_s": round(statistics.median(offset_values), 6),
        "drift_ms": round((max(offset_values) - min(offset_values)) * 1000, 3),
    }

    condition_a = [request_metrics(probe_rows, row) for row in driven_rows]
    condition_b = []
    telemetry_summary = []
    for run in harness_runs:
        rows = load_csv(Path(run["requests_csv"]))
        for row in rows:
            row["phase"] = run["phase"]
            row["cycle"] = str(run["cycle"])
            condition_b.append(request_metrics(probe_rows, row))
        telemetry_summary.append({
            "cycle": run["cycle"],
            "exit": run["returncode"],
            "elapsed_s": run["elapsed_s"],
            **harness_telemetry_summary(Path(run["telemetry_csv"])),
        })

    all_windows = condition_a + condition_b
    windows_csv = Path(args.out_dir) / f"{args.tag}_windows.csv"
    columns = [
        "phase", "cycle", "request_index", "status", "window_s", "ttft_s",
        "prompt_eval_count", "eval_count", "done_reason",
        "contained", "straddle", "negatives", "energy_j", "covered_s",
        "uncovered_ms", "power_w", "j_per_token",
    ]
    with windows_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in all_windows:
            writer.writerow({key: row.get(key, "") for key in columns})

    cycles = {}
    for cycle in sorted({row["cycle"] for row in all_windows}):
        a1 = [row for row in condition_a
              if row["cycle"] == cycle and row["phase"].endswith("_a1")]
        b = [row for row in condition_b if row["cycle"] == cycle]
        a2 = [row for row in condition_a
              if row["cycle"] == cycle and row["phase"].endswith("_a2")]
        entry = {
            "a1_power_w": mean_of([row["power_w"] for row in a1]),
            "b_power_w": mean_of([row["power_w"] for row in b]),
            "a2_power_w": mean_of([row["power_w"] for row in a2]),
            "a1_jtok": mean_of([row["j_per_token"] for row in a1]),
            "b_jtok": mean_of([row["j_per_token"] for row in b]),
            "a2_jtok": mean_of([row["j_per_token"] for row in a2]),
            "a1_n": len(a1), "b_n": len(b), "a2_n": len(a2),
        }
        if None not in (entry["a1_power_w"], entry["b_power_w"],
                        entry["a2_power_w"]):
            reference = (entry["a1_power_w"] + entry["a2_power_w"]) / 2.0
            entry["delta_b_minus_a_w"] = round(
                entry["b_power_w"] - reference, 4
            )
            entry["drift_a2_minus_a1_w"] = round(
                entry["a2_power_w"] - entry["a1_power_w"], 4
            )
        if None not in (entry["a1_jtok"], entry["b_jtok"], entry["a2_jtok"]):
            reference = (entry["a1_jtok"] + entry["a2_jtok"]) / 2.0
            entry["delta_b_minus_a_jtok"] = round(
                entry["b_jtok"] - reference, 6
            )
            entry["drift_a2_minus_a1_jtok"] = round(
                entry["a2_jtok"] - entry["a1_jtok"], 6
            )
        cycles[str(cycle)] = entry

    deltas = [entry.get("delta_b_minus_a_w") for entry in cycles.values()
              if entry.get("delta_b_minus_a_w") is not None]
    drifts = [entry.get("drift_a2_minus_a1_w") for entry in cycles.values()
              if entry.get("drift_a2_minus_a1_w") is not None]
    signal = max((abs(value) for value in deltas), default=None)
    drift = max((abs(value) for value in drifts), default=None)
    paired = [entry for entry in cycles.values()
              if entry.get("delta_b_minus_a_w") is not None
              and entry.get("drift_a2_minus_a1_w") is not None]
    if signal is None or drift is None:
        verdict = "non calcolabile: finestre mancanti"
    elif (signal < SCALE_W
          and all(abs(entry["delta_b_minus_a_w"])
                  <= abs(entry["drift_a2_minus_a1_w"]) for entry in paired)):
        verdict = ("non distinguibile dal drift: |delta| < 1,0 W in ogni "
                   "ciclo e non supera |A2 - A1| dello stesso ciclo")
    else:
        verdict = ("il delta supera il drift o la scala di 1,0 W: "
                   "riportare l'intervallo, non una stima puntuale")

    pre = baselines["pre"]
    post = baselines["post"]
    baseline = {
        "pre_w": pre["median_w"],
        "pre_range_w": pre["range_w"],
        "pre_min_w": pre["min_w"],
        "pre_max_w": pre["max_w"],
        "post_w": post["median_w"],
        "post_range_w": post["range_w"],
        "drift_w": (round(post["median_w"] - pre["median_w"], 4)
                    if None not in (pre["median_w"], post["median_w"])
                    else None),
        "settle_pre": baselines["settle_pre"],
        "settle_post": baselines["settle_post"],
    }

    a_power = mean_of([row["power_w"] for row in condition_a])
    b_power = mean_of([row["power_w"] for row in condition_b])
    a_jtok = mean_of([row["j_per_token"] for row in condition_a])
    b_jtok = mean_of([row["j_per_token"] for row in condition_b])
    pooled = {
        "a_windows": len(condition_a),
        "b_windows": len(condition_b),
        "a_power_w": a_power,
        "b_power_w": b_power,
        "a_power_median_w": median_of([row["power_w"] for row in condition_a]),
        "b_power_median_w": median_of([row["power_w"] for row in condition_b]),
        "a_jtok": a_jtok,
        "b_jtok": b_jtok,
        "delta_power_w": (round(b_power - a_power, 4)
                          if None not in (a_power, b_power) else None),
        "delta_jtok": (round(b_jtok - a_jtok, 6)
                       if None not in (a_jtok, b_jtok) else None),
    }

    summary = {
        "tag": args.tag,
        "created_utc": datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ),
        "config": {
            "model": args.model,
            "prompt": args.prompt,
            "options": args.options,
            "keep_alive": args.keep_alive,
            "keep_alive_sent": parse_keep_alive(args.keep_alive),
            "requests_per_phase": args.requests,
            "request_interval_s": args.request_interval,
            "tail_s": args.tail,
            "cycles": args.cycles,
            "probe_interval_s": args.probe_interval,
            "baseline_windows": args.baseline_windows,
            "baseline_seconds": args.baseline_seconds,
            "harness": str(args.harness),
        },
        "probe": {
            "rows": len(probe_rows),
            "wall_s": round(wall_s, 3),
            "cpu_s": round(probe_cpu_s, 3),
            "cpu_pct_one_core": (round(probe_cpu_s / wall_s * 100, 3)
                                 if wall_s > 0 else None),
            "offset": offset,
        },
        "baseline": baseline,
        "pooled": pooled,
        "cycles": cycles,
        "criterion": {
            "scale_w": SCALE_W,
            "max_abs_delta_w": signal,
            "max_abs_drift_w": drift,
            "verdict": verdict,
        },
        "harness": telemetry_summary,
        "harness_runs": harness_runs,
        "files": {
            "probe_csv": str(Path(args.out_dir) / f"{args.tag}_probe.csv"),
            "driven_requests_glob": str(
                Path(args.out_dir) / f"{args.tag}_requests_probe_c*.csv"
            ),
            "windows_csv": str(windows_csv),
            "summary_json": str(Path(args.out_dir) / f"{args.tag}_summary.json"),
        },
    }
    return summary, all_windows


def write_probe_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROBE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", default=f"harness_overhead_{datetime.now():%Y%m%d_%H%M%S}")
    parser.add_argument("--out-dir", default="experiment_results")
    parser.add_argument("--harness", default="monitor_ollama.py")
    parser.add_argument("--api", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="llama3.2:1b")
    parser.add_argument("--prompt", default="Scrivi un testo lungo e dettagliato sul mare, almeno duecento parole.")
    parser.add_argument("--options-json", default='{"num_predict":64,"temperature":0}')
    parser.add_argument("--keep-alive", default="-1")
    parser.add_argument("--requests", type=int, default=4)
    parser.add_argument("--request-interval", type=float, default=6.0)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--tail", type=float, default=2.0)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--probe-interval", type=float, default=0.1)
    parser.add_argument("--baseline-windows", type=int, default=3)
    parser.add_argument("--baseline-seconds", type=float, default=30.0)
    parser.add_argument("--settle-max-s", type=float, default=120.0)
    args = parser.parse_args()

    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.cycles < 1:
        parser.error("--cycles must be >= 1")
    if args.baseline_windows < 1:
        parser.error("--baseline-windows must be >= 1")
    for name in ("request_interval", "request_timeout", "probe_interval",
                 "baseline_seconds", "settle_max_s"):
        if getattr(args, name) <= 0:
            parser.error(f"--{name.replace('_', '-')} must be > 0")
    if args.tail < 0:
        parser.error("--tail must be >= 0")
    try:
        options = json.loads(args.options_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--options-json non valido: {exc}")
    if not isinstance(options, dict):
        parser.error("--options-json deve essere un oggetto JSON")
    args.options = options
    args.harness = Path(args.harness)
    if not args.harness.is_file():
        parser.error(f"harness non trovato: {args.harness}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if EMICounterBackend is None:
        print("EMI backend non importabile", flush=True)
        return 2
    backend = EMICounterBackend()
    if not backend.available:
        print("EMI non disponibile", flush=True)
        return 2

    sampler = Sampler(backend, args.probe_interval)
    sampler.start()
    time.sleep(0.5)
    if sampler.start_error:
        print(f"Sonda EMI fermata: {sampler.start_error}", flush=True)
        return 2

    wall_start = time.monotonic()
    cpu_start = time.process_time()
    baselines = {}
    driven_rows = []
    harness_runs = []
    errors = []
    state = {"api_ps_start": api_ps(args.api)}
    try:
        print("Warm-up: 2 richieste scartate", flush=True)
        sampler.set_phase("warmup", 0)
        warmup = []
        for index in range(1, 3):
            row = one_request(
                args.api, args.model, args.prompt, args.options,
                args.keep_alive, args.request_timeout,
            )
            row["request_index"] = index
            warmup.append({
                "request_index": index,
                "status": row["status"],
                "window_s": row["window_s"],
                "eval_count": row["eval_count"],
                "done_reason": row["done_reason"],
            })
            print(f"  warmup r{index}: {row['status']} {row['window_s']} s, "
                  f"{row['eval_count']} token", flush=True)
            if row["status"] != "ok":
                errors.append(f"warmup r{index}: {row['status']} {row['error']}")
        state["warmup"] = warmup
        time.sleep(5.0)
        state["api_ps_after_warmup"] = api_ps(args.api)
        print("Baseline pre: settling", flush=True)
        baselines["settle_pre"] = settle(sampler, args.settle_max_s)
        print("Baseline pre: 3 finestre", flush=True)
        baselines["pre"] = baseline_windows(
            sampler, "pre", args.baseline_windows, args.baseline_seconds
        )
        for cycle in range(1, args.cycles + 1):
            print(f"\nCiclo {cycle}/{args.cycles}", flush=True)
            driven_rows.extend(drive_requests(
                args, sampler, f"c{cycle}_a1", cycle,
                out_dir / f"{args.tag}_requests_probe_c{cycle}_a1.csv",
            ))
            sampler.set_phase(f"c{cycle}_b", cycle)
            run = run_harness(args, out_dir, args.tag, cycle)
            harness_runs.append(run)
            if run["returncode"] != 0:
                errors.append(f"harness ciclo {cycle}: exit {run['returncode']}")
            driven_rows.extend(drive_requests(
                args, sampler, f"c{cycle}_a2", cycle,
                out_dir / f"{args.tag}_requests_probe_c{cycle}_a2.csv",
            ))
        print("\nBaseline post: settling", flush=True)
        baselines["settle_post"] = settle(sampler, args.settle_max_s)
        print("Baseline post: 3 finestre", flush=True)
        baselines["post"] = baseline_windows(
            sampler, "post", args.baseline_windows, args.baseline_seconds
        )
        state["api_ps_end"] = api_ps(args.api)
    except KeyboardInterrupt:
        errors.append("interrotto da tastiera")
    finally:
        sampler.stop_event.set()
        sampler.join(timeout=5.0)
        backend.close()

    probe_rows = sampler.snapshot()
    wall_s = time.monotonic() - wall_start
    cpu_s = time.process_time() - cpu_start
    write_probe_csv(out_dir / f"{args.tag}_probe.csv", probe_rows)

    bad_requests = [row for row in driven_rows if row["status"] != "ok"]
    for row in bad_requests:
        errors.append(
            f"{row['phase']} r{row['request_index']}: {row['status']}"
        )
    if sampler.start_error:
        errors.append(f"sonda: {sampler.start_error}")

    summary, _ = analyze(
        args, sampler, probe_rows, driven_rows, harness_runs, baselines,
        cpu_s, wall_s,
    )
    summary["errors"] = errors
    summary["state"] = state
    summary_path = out_dir / f"{args.tag}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print("\n===== RIEPILOGO =====")
    print(f"baseline pre  {summary['baseline']['pre_w']} W "
          f"(range {summary['baseline']['pre_range_w']} W)")
    print(f"baseline post {summary['baseline']['post_w']} W "
          f"(drift {summary['baseline']['drift_w']} W)")
    print(f"pooled A {summary['pooled']['a_power_w']} W, "
          f"B {summary['pooled']['b_power_w']} W, "
          f"delta {summary['pooled']['delta_power_w']} W")
    for cycle, entry in summary["cycles"].items():
        print(f"ciclo {cycle}: A1 {entry.get('a1_power_w')} W, "
              f"B {entry.get('b_power_w')} W, A2 {entry.get('a2_power_w')} W, "
              f"delta B-A {entry.get('delta_b_minus_a_w')} W, "
              f"drift A2-A1 {entry.get('drift_a2_minus_a1_w')} W")
    print(f"criterio: {summary['criterion']['verdict']}")
    print(f"sonda: {summary['probe']['rows']} righe, "
          f"CPU {summary['probe']['cpu_pct_one_core']}% di un core")
    print(f"file: {summary_path.resolve()}")
    if errors:
        print("ERRORI:")
        for error in errors:
            print(f"  - {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
