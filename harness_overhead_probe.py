#!/usr/bin/env python3
"""A-B-C del costo dell'harness di telemetria Ollama.

Domanda: l'enumerazione dei processi con psutil che `monitor_ollama.py` esegue
ogni 0,5 s sposta l'energia per richiesta o la durata della richiesta misurate
dal contatore EMI?

Condizioni, a parita' di modello, prompt, opzioni, `keep_alive`, carico e
macchina:

- A: richieste guidate da questo script, nessuna scansione dei processi;
- B: richieste guidate da `monitor_ollama.py --process-scan full`;
- C: richieste guidate da `monitor_ollama.py --process-scan off`.

B-C isola la scansione a driver costante; B-A e' la differenza totale
harness+driver; C-A il residuo del driver e delle componenti fisse comuni a B e
C (compresa l'interrogazione periodica di `/api/ps`).

Disegno, dichiarato prima dei dati:

- riferimento: la sonda EMI di questo script, attiva a 100 ms in **tutte** le
  fasi. Il suo costo e' dentro ogni condizione, quindi i contrasti sono
  incrementali e non misurano il costo zero-osservatore (che richiederebbe un
  wattmetro esterno);
- baseline: 3 finestre idle da 30 s prima e 3 dopo, con settling P1.5
  (media mobile a 10 s stabile entro 0,5 W, tetto 120 s);
- ordine: un blocco di sei cicli con l'insieme completo delle sequenze di
  Williams per tre trattamenti (ABC, BCA, CAB, CBA, ACB, BAC). Ogni condizione
  occupa ogni posizione due volte e segue ogni altra condizione due volte:
  l'ordine e' bilanciato per posizione e carryover e non richiede
  randomizzazione. Oltre sei cicli si ripete il blocco, sfalsato di una
  sequenza per blocco;
- stato: due warm-up scartati con lo stesso prompt e `keep_alive = -1`, poi
  `/api/ps` verificato prima e dopo; il modello resta residente per tutto il
  run. La geometria dei warm-up non e' quella di P1.4 (512,128): qui serve solo
  caricare pesi e cache, non misurare token;
- carico: 4 richieste per condizione per ciclo, invii a 6 s, coda di 2 s;
- nessuna sottrazione del costo dell'osservatore (P1.4): si misura e si
  dichiara.

Criteri preregistrati, nessuno dei quali si sposta dopo aver visto i risultati:

- metriche primarie: energia per richiesta (J) e durata della finestra (s);
- contrasto primario: B-C. Secondari: B-A e C-A;
- soglie di rilevanza pratica: 1,0 J per richiesta (circa 1,2% degli ~82 J del
  run A-B-A, sotto il CV fra run del J/token riportato per v3) e 0,10 s di
  durata (circa 3,3% di una finestra da ~3 s, sotto la cadenza di 0,5 s della
  telemetria dell'harness);
- finestra valida: `status == "ok"`, `eval_count` uguale al `num_predict`
  dichiarato (quando presente) e positivo. Una cella condizione-ciclo entra
  nell'analisi con almeno 3 finestre valide su 4; un contrasto entra se
  entrambe le celle sono incluse, con eliminazione listwise del ciclo. I cicli
  esclusi si contano e si riportano;
- stima: differenze pairate a livello di ciclo, intervallo t al 95% con n-1
  gradi di liberta'. Sotto 4 cicli pairati l'intervallo non si riporta, solo i
  valori osservati. La dispersione fra cicli e' la scala dell'intervallo, non
  l'incertezza di una singola misura;
- verdetto per metrica e contrasto: "effetto rilevante" se l'intero intervallo
  sta oltre +soglia o oltre -soglia; "equivalenza entro soglia" se l'intero
  intervallo sta dentro (-soglia, +soglia); "non conclusivo" se attraversa un
  bordo. Il mancato superamento di una soglia non e' prova di assenza: conta
  solo la posizione dell'intervallo;
- numerosita': il pilota e' a 6 cicli. Se la semi-ampiezza dell'intervallo per
  B-C supera meta' della soglia, su energia o durata, il run definitivo si
  esegue da capo a 12 cicli (due blocchi completi), poi 18; non si accodano
  sessioni diverse. La regola usa solo l'ampiezza, non il segno.

Cio' che questo script non fa: non e' un canale di misura, non entra in
`MEASURED_METHODS`, non calcola energia di protocollo, non modifica la
produzione. Le energie per finestra sono diagnostiche. La versione A-B-A ha
prodotto l'artefatto `harness_overhead_20261025`; questa implementa il disegno
A-B-C del punto #67.

Uso:
  python harness_overhead_probe.py --tag harness_overhead_abc_20261025

I file finiscono in `experiment_results/`: sonda EMI, richieste guidate dallo
script, telemetria e richieste dell'harness per ogni fase B e C, riepilogo JSON
e tabella delle finestre.
"""
import argparse
import csv
import hashlib
import json
import math
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
T_ENERGY_J = 1.0
T_DURATION_S = 0.10
MIN_PAIRED_CYCLES = 4
MAX_CYCLES = 18
SEQUENCES = (
    ("a", "b", "c"),
    ("b", "c", "a"),
    ("c", "a", "b"),
    ("c", "b", "a"),
    ("a", "c", "b"),
    ("b", "a", "c"),
)
T975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447,
    7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179,
    13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101,
    19: 2.093, 20: 2.086, 21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064,
    25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}
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


def cycle_order(cycle):
    """Sequenza del ciclo: blocco Williams completo, sfalsato ogni sei."""
    block, index = divmod(cycle - 1, len(SEQUENCES))
    return SEQUENCES[(index + block) % len(SEQUENCES)]


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


def run_harness(args, out_dir, tag, cycle, condition):
    process_scan = "full" if condition == "b" else "off"
    sampler_phase = f"c{cycle}_{condition}"
    run_id = f"{tag}_{condition}{cycle}"
    telemetry = out_dir / f"{tag}_telemetry_{condition}{cycle}.csv"
    requests = out_dir / f"{tag}_requests_{condition}{cycle}.csv"
    meta = out_dir / f"{tag}_meta_{condition}{cycle}.json"
    log = out_dir / f"{tag}_harness_{condition}{cycle}.log"
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
        "--process-scan", process_scan,
        "--run-id", run_id,
        "--output", str(telemetry),
        "--requests-output", str(requests),
        "--meta-output", str(meta),
    ]
    print(f"  {sampler_phase}: {args.harness.name} "
          f"(process-scan={process_scan}, run_id={run_id})", flush=True)
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
        "condition": condition,
        "process_scan": process_scan,
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
    scans = [float(row["process_scan_s"]) for row in rows
             if row.get("process_scan_s") not in (None, "")]
    cpu = [float(row["observer_cpu_pct"]) for row in rows
           if row["observer_cpu_pct"]]
    cpu_seconds = 0.0
    for row in rows[1:]:
        try:
            cpu_seconds += (float(row["observer_cpu_pct"]) / 100.0
                            * float(row["interval_effective_s"]))
        except (TypeError, ValueError):
            pass
    interval_median = statistics.median(intervals) if intervals else None
    scan_median = statistics.median(scans) if scans else None
    return {
        "rows": len(rows),
        "interval_median_s": (round(interval_median, 4)
                              if interval_median is not None else None),
        "sweep_median_s": (round(statistics.median(sweeps), 4)
                           if sweeps else None),
        "sweep_max_s": round(max(sweeps), 4) if sweeps else None,
        "sweep_duty": (round(statistics.median(sweeps) / interval_median, 6)
                       if sweeps and interval_median else None),
        "process_scan_median_s": (round(scan_median, 6)
                                  if scan_median is not None else None),
        "process_scan_max_s": round(max(scans), 6) if scans else None,
        "process_scan_duty": (round(scan_median / interval_median, 6)
                              if scan_median is not None and interval_median
                              else None),
        "observer_cpu_pct_mean": (round(statistics.mean(cpu), 4)
                                  if cpu else None),
        "observer_cpu_pct_max": round(max(cpu), 4) if cpu else None,
        "observer_cpu_seconds": round(cpu_seconds, 4),
    }


def t_critical(df):
    return T975.get(df, 1.96)


def request_is_valid(row, expected_tokens):
    """Finestra valida secondo il criterio preregistrato di #67."""
    if row.get("status") != "ok":
        return False
    try:
        tokens = int(row.get("eval_count"))
    except (TypeError, ValueError):
        return False
    if tokens <= 0:
        return False
    return expected_tokens is None or tokens == expected_tokens


def condition_windows(driven_rows, harness_runs, probe_rows):
    windows = {"a": [], "b": [], "c": []}
    for row in driven_rows:
        metrics = request_metrics(probe_rows, row)
        metrics["condition"] = "a"
        windows["a"].append(metrics)
    for run in harness_runs:
        condition = run["condition"]
        for row in load_csv(Path(run["requests_csv"])):
            row["phase"] = run["phase"]
            row["cycle"] = str(run["cycle"])
            metrics = request_metrics(probe_rows, row)
            metrics["condition"] = condition
            windows[condition].append(metrics)
    return windows


def aggregate_cells(windows, expected_tokens, min_valid):
    cells = {condition: {} for condition in ("a", "b", "c")}
    for condition, rows in windows.items():
        for cycle in sorted({row["cycle"] for row in rows}):
            selected = [row for row in rows if row["cycle"] == cycle]
            valid = [row for row in selected
                     if request_is_valid(row, expected_tokens)]
            cell = {
                "requests": len(selected),
                "valid": len(valid),
                "included": len(valid) >= min_valid,
                "energy_j_per_request": None,
                "duration_s": None,
                "power_w": None,
                "j_per_token": None,
                "ttft_s": None,
            }
            if valid:
                energy_j = sum(row["energy_j"] for row in valid)
                covered_s = sum(row["covered_s"] for row in valid)
                tokens = sum(int(row["eval_count"]) for row in valid)
                ttfts = [row["ttft_s"] for row in valid
                         if row["ttft_s"] is not None]
                cell["energy_j_per_request"] = round(
                    energy_j / len(valid), 6)
                cell["duration_s"] = round(
                    statistics.mean(row["window_s"] for row in valid), 6)
                cell["power_w"] = (round(energy_j / covered_s, 4)
                                   if covered_s else None)
                cell["j_per_token"] = (round(energy_j / tokens, 6)
                                       if tokens else None)
                cell["ttft_s"] = (round(statistics.mean(ttfts), 6)
                                  if ttfts else None)
            cells[condition][cycle] = cell
    return cells


def paired_differences(cells, minuend, subtrahend, key):
    values = []
    per_cycle = {}
    for cycle in sorted(set(cells[minuend]) & set(cells[subtrahend])):
        left = cells[minuend][cycle]
        right = cells[subtrahend][cycle]
        if not (left["included"] and right["included"]):
            continue
        if left[key] is None or right[key] is None:
            continue
        difference = left[key] - right[key]
        per_cycle[str(cycle)] = round(difference, 6)
        values.append(difference)
    return values, per_cycle


def summarize_differences(values):
    n = len(values)
    summary = {
        "n": n,
        "mean": None,
        "cycle_sd": None,
        "half_width": None,
        "lo": None,
        "hi": None,
        "t_crit": None,
        "positive": 0,
        "negative": 0,
        "zero": 0,
        "interval_available": False,
    }
    if n == 0:
        return summary
    mean = statistics.mean(values)
    summary["mean"] = round(mean, 6)
    summary["positive"] = sum(1 for value in values if value > 0)
    summary["negative"] = sum(1 for value in values if value < 0)
    summary["zero"] = n - summary["positive"] - summary["negative"]
    if n >= MIN_PAIRED_CYCLES:
        sd = statistics.stdev(values)
        crit = t_critical(n - 1)
        half = crit * sd / math.sqrt(n)
        summary.update({
            "cycle_sd": round(sd, 6),
            "half_width": round(half, 6),
            "lo": round(mean - half, 6),
            "hi": round(mean + half, 6),
            "t_crit": crit,
            "interval_available": True,
        })
    return summary


def classify(interval, threshold):
    """Verdetto sulla posizione dell'intervallo, non sulla significativita'."""
    if not interval["interval_available"]:
        return "non conclusivo: meno di 4 cicli pairati validi"
    lo = interval["lo"]
    hi = interval["hi"]
    if lo > threshold or hi < -threshold:
        return "effetto rilevante: l'intero intervallo supera la soglia"
    if -threshold < lo and hi < threshold:
        return "equivalenza entro soglia: l'intero intervallo sta nella banda"
    return "non conclusivo: l'intervallo attraversa un bordo della soglia"


def cycles_needed(interval, threshold):
    """Cicli per una semi-ampiezza <= soglia/2; usa l'ampiezza, non il segno."""
    if not interval["interval_available"] or interval["cycle_sd"] is None:
        return None
    target = threshold / 2.0
    sd = interval["cycle_sd"]
    if sd == 0:
        return interval["n"]
    n = max(interval["n"], MIN_PAIRED_CYCLES)
    for _ in range(100):
        needed = max(n, math.ceil((t_critical(n - 1) * sd / target) ** 2))
        if needed <= n:
            return n
        n = needed
    return n


def pooled_telemetry(runs):
    if not runs:
        return None

    def median_field(name):
        values = [run[name] for run in runs if run.get(name) is not None]
        return round(statistics.median(values), 6) if values else None

    cpu_seconds = [run["observer_cpu_seconds"] for run in runs
                   if run.get("observer_cpu_seconds") is not None]
    return {
        "runs": len(runs),
        "interval_median_s": median_field("interval_median_s"),
        "sweep_duty": median_field("sweep_duty"),
        "process_scan_median_s": median_field("process_scan_median_s"),
        "process_scan_duty": median_field("process_scan_duty"),
        "observer_cpu_pct_mean": median_field("observer_cpu_pct_mean"),
        "observer_cpu_seconds_sum": (round(sum(cpu_seconds), 4)
                                     if cpu_seconds else None),
    }


def analyze(args, probe_rows, driven_rows, harness_runs, baselines,
            probe_cpu_s, wall_s, executed_order):
    offset_values = [
        row["mono_mid_ns"] / 1e9 - row["ts_100ns"] / 1e7
        for row in probe_rows
    ]
    offset = {
        "pairs": len(offset_values),
        "median_s": round(statistics.median(offset_values), 6),
        "drift_ms": round((max(offset_values) - min(offset_values)) * 1000, 3),
    }

    try:
        expected_tokens = int(args.options.get("num_predict"))
    except (TypeError, ValueError):
        expected_tokens = None
    min_valid = math.ceil(0.75 * args.requests)

    windows = condition_windows(driven_rows, harness_runs, probe_rows)
    cells = aggregate_cells(windows, expected_tokens, min_valid)

    all_windows = []
    for cycle in range(1, args.cycles + 1):
        for condition in ("a", "b", "c"):
            all_windows.extend(sorted(
                (row for row in windows[condition] if row["cycle"] == cycle),
                key=lambda row: row["request_index"],
            ))
    windows_csv = Path(args.out_dir) / f"{args.tag}_windows.csv"
    columns = [
        "condition", "phase", "cycle", "request_index", "status", "window_s",
        "ttft_s", "prompt_eval_count", "eval_count", "done_reason",
        "contained", "straddle", "negatives", "energy_j", "covered_s",
        "uncovered_ms", "power_w", "j_per_token",
    ]
    with windows_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in all_windows:
            writer.writerow({key: row.get(key, "") for key in columns})

    telemetry = {"b": [], "c": []}
    for run in harness_runs:
        telemetry[run["condition"]].append({
            "cycle": run["cycle"],
            "process_scan": run["process_scan"],
            "exit": run["returncode"],
            "elapsed_s": run["elapsed_s"],
            **harness_telemetry_summary(Path(run["telemetry_csv"])),
        })

    conditions = {}
    for condition in ("a", "b", "c"):
        rows = windows[condition]
        valid = [row for row in rows
                 if request_is_valid(row, expected_tokens)]
        energy_j = sum(row["energy_j"] for row in valid)
        covered_s = sum(row["covered_s"] for row in valid)
        tokens = sum(int(row["eval_count"]) for row in valid)
        ttfts = [row["ttft_s"] for row in valid if row["ttft_s"] is not None]
        conditions[condition] = {
            "windows": len(rows),
            "valid_windows": len(valid),
            "included_cells": sum(1 for cell in cells[condition].values()
                                  if cell["included"]),
            "energy_j_per_request": (round(energy_j / len(valid), 4)
                                     if valid else None),
            "duration_s": (round(statistics.mean(
                row["window_s"] for row in valid), 4) if valid else None),
            "power_w": (round(energy_j / covered_s, 4)
                        if covered_s else None),
            "j_per_token": (round(energy_j / tokens, 6) if tokens else None),
            "ttft_s": (round(statistics.mean(ttfts), 6) if ttfts else None),
            "harness_telemetry": pooled_telemetry(
                telemetry.get(condition, [])),
        }

    contrast_specs = (
        ("b_minus_c", "b", "c"),
        ("b_minus_a", "b", "a"),
        ("c_minus_a", "c", "a"),
    )
    metric_specs = (
        ("energy_j_per_request", T_ENERGY_J, "primary"),
        ("duration_s", T_DURATION_S, "primary"),
        ("j_per_token", None, "secondary"),
        ("power_w", None, "secondary"),
        ("ttft_s", None, "secondary"),
    )
    contrasts = {}
    for name, minuend, subtrahend in contrast_specs:
        entry = {}
        for key, threshold, role in metric_specs:
            values, per_cycle = paired_differences(
                cells, minuend, subtrahend, key)
            interval = summarize_differences(values)
            item = {
                "role": role,
                "threshold": threshold,
                "per_cycle": per_cycle,
                **interval,
            }
            if threshold is not None:
                item["verdict"] = classify(interval, threshold)
                item["recommended_cycles"] = cycles_needed(
                    interval, threshold)
            entry[key] = item
        contrasts[name] = entry

    cycles = {}
    for cycle in range(1, args.cycles + 1):
        cycles[str(cycle)] = {
            "order": "".join(cycle_order(cycle)).upper(),
            "cells": {condition: cells[condition].get(cycle)
                      for condition in ("a", "b", "c")},
        }

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

    n_rule = {}
    for key in ("energy_j_per_request", "duration_s"):
        item = contrasts["b_minus_c"][key]
        needed = item["recommended_cycles"]
        n_rule[key] = {
            "threshold": item["threshold"],
            "target_half_width": item["threshold"] / 2.0,
            "achieved_half_width": item["half_width"],
            "met": (item["half_width"] is not None
                    and item["half_width"] <= item["threshold"] / 2.0),
            "recommended_cycles": (min(needed, MAX_CYCLES)
                                   if needed is not None else None),
            "beyond_cap": (needed is not None and needed > MAX_CYCLES),
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
            "requests_per_condition": args.requests,
            "request_interval_s": args.request_interval,
            "tail_s": args.tail,
            "cycles": args.cycles,
            "order_sequences": ["".join(seq).upper() for seq in SEQUENCES],
            "order_executed": executed_order,
            "process_scan": {"b": "full", "c": "off"},
            "probe_interval_s": args.probe_interval,
            "baseline_windows": args.baseline_windows,
            "baseline_seconds": args.baseline_seconds,
            "harness": str(args.harness),
            "expected_eval_count": expected_tokens,
            "min_valid_per_cell": min_valid,
        },
        "preregistration": {
            "primary_metrics": ["energy_j_per_request", "duration_s"],
            "primary_contrast": "b_minus_c",
            "secondary_contrasts": ["b_minus_a", "c_minus_a"],
            "thresholds": {
                "energy_j_per_request": T_ENERGY_J,
                "duration_s": T_DURATION_S,
            },
            "valid_window": ("status == ok, eval_count == num_predict "
                             "quando dichiarato, eval_count > 0"),
            "cell_inclusion": (f"almeno {min_valid} finestre valide "
                               f"su {args.requests}"),
            "cycle_inclusion": "listwise: entrambe le celle incluse",
            "interval": "t al 95%, df = n-1, minimo 4 cicli pairati",
            "verdict_rule": ("rilevante se l'intervallo e' tutto oltre "
                             "+soglia o tutto oltre -soglia; equivalente se "
                             "tutto dentro la banda; altrimenti non "
                             "conclusivo"),
            "n_rule": ("pilota 6 cicli; se la semi-ampiezza B-C supera "
                       "soglia/2, run definitivo da capo a 12, poi 18"),
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
        "conditions": conditions,
        "contrasts": contrasts,
        "n_rule": n_rule,
        "cycles": cycles,
        "harness_telemetry": telemetry,
        "harness_runs": harness_runs,
        "files": {
            "probe_csv": str(Path(args.out_dir) / f"{args.tag}_probe.csv"),
            "driven_requests_glob": str(
                Path(args.out_dir) / f"{args.tag}_requests_probe_c*_a.csv"
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
    parser.add_argument("--cycles", type=int, default=6)
    parser.add_argument("--probe-interval", type=float, default=0.1)
    parser.add_argument("--baseline-windows", type=int, default=3)
    parser.add_argument("--baseline-seconds", type=float, default=30.0)
    parser.add_argument("--settle-max-s", type=float, default=120.0)
    args = parser.parse_args()

    if args.requests < 1:
        parser.error("--requests must be >= 1")
    if args.cycles < 1:
        parser.error("--cycles must be >= 1")
    if args.cycles > MAX_CYCLES:
        parser.error(f"--cycles must be <= {MAX_CYCLES}")
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
    executed_order = []
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
            order = cycle_order(cycle)
            print(f"\nCiclo {cycle}/{args.cycles}: ordine "
                  f"{'-'.join(order).upper()}", flush=True)
            for condition in order:
                if condition == "a":
                    driven_rows.extend(drive_requests(
                        args, sampler, f"c{cycle}_a", cycle,
                        out_dir / f"{args.tag}_requests_probe_c{cycle}_a.csv",
                    ))
                    continue
                sampler.set_phase(f"c{cycle}_{condition}", cycle)
                run = run_harness(
                    args, out_dir, args.tag, cycle, condition)
                harness_runs.append(run)
                if run["returncode"] != 0:
                    errors.append(
                        f"harness ciclo {cycle} {condition}: "
                        f"exit {run['returncode']}"
                    )
            executed_order.append("".join(order).upper())
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
    for run in harness_runs:
        requests_csv = Path(run["requests_csv"])
        if not requests_csv.is_file():
            errors.append(f"{run['phase']}: CSV delle richieste assente")
            continue
        for row in load_csv(requests_csv):
            if row["status"] != "ok":
                errors.append(
                    f"{run['phase']} r{row['request_index']}: "
                    f"{row['status']}"
                )
    if sampler.start_error:
        errors.append(f"sonda: {sampler.start_error}")

    summary, _ = analyze(
        args, probe_rows, driven_rows, harness_runs, baselines,
        cpu_s, wall_s, executed_order,
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
    for condition in ("a", "b", "c"):
        item = summary["conditions"][condition]
        print(f"{condition.upper()}: {item['valid_windows']}/"
              f"{item['windows']} finestre valide, "
              f"{item['energy_j_per_request']} J/richiesta, "
              f"{item['duration_s']} s")
    for name, entry in summary["contrasts"].items():
        for key in ("energy_j_per_request", "duration_s"):
            item = entry[key]
            span = (f"[{item['lo']}, {item['hi']}]"
                    if item["interval_available"] else "intervallo assente")
            print(f"{name} {key}: media {item['mean']} {span} "
                  f"n={item['n']} -> {item['verdict']}")
    for key, item in summary["n_rule"].items():
        print(f"n rule {key}: semi-ampiezza {item['achieved_half_width']} "
              f"(target {item['target_half_width']}), "
              f"cicli consigliati {item['recommended_cycles']}"
              f"{' (oltre il tetto)' if item['beyond_cap'] else ''}")
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
