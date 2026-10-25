#!/usr/bin/env python3
"""Telemetry harness for local Ollama on Windows, Linux and macOS.

This is an observability instrument, not an energy channel: it records CPU
time, RSS and Ollama's own /api/ps view, which explain a load but never
replace a counter. Nothing here belongs in MEASURED_METHODS.

Identity is an explicit allowlist of Ollama executables, resolved from the
executable basename (the command line is used only to classify the role).
The inference runner is a special case: on Ollama 0.33.1 for Windows it is
`llama-server.exe`, whose name says nothing about Ollama, so it is accepted
only when its ancestor chain reaches an Ollama server root. Parentage is
recorded for audit; arbitrary children are never included, because the tray
app hosts a WebView2 UI and the server spawns console hosts, and those are
not inference. The observer and its ancestors are excluded; the observer's
own cost is recorded in every row.

The CSV carries what is needed to audit a row after the fact: match reason
and role of every selected process, sweep duration, requested and effective
sampling interval, a monotonic timestamp, and the state of the /api/ps
poller (ok, timeout, http_error, ...). An empty model list is "ok" with
api_models_count = 0, never an API failure.

Totals cover the server tree only (tray app, server, runner). CLI clients
such as `ollama run` are listed separately and are not summed: they are
Ollama, but they are not the inference workload.

With --requests N the harness also drives N inference requests and writes a
request table: run_id, model, prompt hash, options, keep_alive actually sent,
monotonic send/first-chunk/end timestamps, server-reported token counts and
durations, and the telemetry samples inside each window. Requests run in a
thread so they never delay a sweep; the run stops on its own after the last
request plus --tail seconds. Streaming is required for the first-chunk
timestamp, so every request uses stream=true; production uses stream=false
(benchmark_unified.py:135), which makes the end-to-end window comparable but
leaves the first-token split available only here.

Association rule, recorded in the run metadata and not inferred:
- a telemetry sample belongs to a window iff
  t_send_mono_ns <= monotonic_ns < t_end_mono_ns;
- an EMI increment [t_i, t_{i+1}) belongs to a window iff both endpoints lie
  inside it; increments that straddle a boundary are excluded and counted;
- monotonic timestamps are comparable across processes only within the same
  boot session; if the energy side uses the EMI ts_100ns clock, its offset to
  time.monotonic_ns must be measured on paired reads and declared, never
  assumed;
- utc_minus_mono_ms is recorded per row to detect wall-clock steps, not as
  the key; the production timestamp_start has one-second resolution
  (benchmark_unified.py:810) and cannot define a window of a few seconds.
No counter is interpolated and no energy is computed here.

Install: python -m pip install psutil
Run: python monitor_ollama.py --interval 1
     python monitor_ollama.py --interval 0.5 --requests 3 --model llama3.2:1b \
         --prompt "Scrivi una frase breve." --options-json '{"num_predict": 32}'
"""
import argparse
import csv
import hashlib
import json
import os
import platform
import statistics
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import psutil

SCHEMA_VERSION = "telemetry/3"
ROOT_ALLOWLIST = frozenset({
    "ollama.exe",
    "ollama app.exe",
    "ollama_llama_server.exe",
    "ollama",
    "ollama_llama_server",
})
RUNNER_ALLOWLIST = frozenset({
    "llama-server.exe",
    "llama-server",
    "ollama_llama_server.exe",
    "ollama_llama_server",
})
READ_ERRORS = (
    psutil.NoSuchProcess,
    psutil.AccessDenied,
    psutil.ZombieProcess,
    OSError,
)


def match_allowlist(basename, allowlist):
    low = (basename or "").lower()
    if low in allowlist:
        return low
    if len(low) == 15:
        for entry in allowlist:
            if entry.startswith(low):
                return entry
    return None


def resolve_identity(proc, name_hint, allowlist):
    try:
        exe = proc.exe()
    except READ_ERRORS:
        exe = ""
    if exe:
        hit = match_allowlist(os.path.basename(exe), allowlist)
        if hit:
            return hit, "exe"
    hit = match_allowlist(name_hint, allowlist)
    if hit:
        return hit, "name"
    return None, ""


def classify(base, argv):
    if base == "ollama app.exe":
        return "server_app"
    if base in RUNNER_ALLOWLIST:
        return "runner"
    sub = argv[1].lower() if len(argv) > 1 else ""
    return "server" if sub == "serve" else "client"


def ancestor_root(pid, procs, roots, limit=12):
    seen = set()
    current = procs[pid][0]
    for _ in range(limit):
        if current is None or current in seen:
            return None
        if current in roots:
            return current
        seen.add(current)
        parent = procs.get(current)
        current = parent[0] if parent else None
    return None


class ProcCache:
    """Reuse Process objects so psutil keeps its cpu_percent baseline.

    Identity (basename, role, match reason) is resolved once per process and
    cached: exe() and cmdline() are syscalls that need not run every sweep.
    """

    def __init__(self):
        self._entries = {}
        self._primed = set()

    def get(self, pid):
        entry = self._entries.get(pid)
        if entry is not None:
            proc, created, meta = entry
            try:
                if proc.is_running() and proc.create_time() == created:
                    return proc, meta
            except READ_ERRORS:
                pass
            self._entries.pop(pid, None)
            self._primed.discard(pid)
        proc = psutil.Process(pid)
        created = proc.create_time()
        self._entries[pid] = (proc, created, None)
        return proc, None

    def set_meta(self, pid, meta):
        proc, created, _ = self._entries[pid]
        self._entries[pid] = (proc, created, meta)

    def is_primed(self, pid):
        return pid in self._primed

    def mark_primed(self, pid):
        self._primed.add(pid)

    def keep_only(self, pids):
        for pid in list(self._entries):
            if pid not in pids:
                del self._entries[pid]
                self._primed.discard(pid)


def collect(cache, excluded):
    procs = {}
    for proc in psutil.process_iter(attrs=["pid", "ppid", "name"]):
        info = proc.info
        pid = info.get("pid")
        if pid is None:
            continue
        procs[pid] = (info.get("ppid"), info.get("name") or "")
    cache.keep_only(procs)

    selected = {}
    for pid, (ppid, name) in procs.items():
        if pid in excluded or "ollama" not in name.lower():
            continue
        try:
            proc, meta = cache.get(pid)
        except READ_ERRORS:
            continue
        if meta is None:
            base, source = resolve_identity(proc, name, ROOT_ALLOWLIST)
            if base is None:
                continue
            try:
                argv = proc.cmdline()
            except READ_ERRORS:
                argv = []
            meta = {
                "base": base,
                "role": classify(base, argv),
                "match": f"allowlist:{base} ({source})",
            }
            cache.set_meta(pid, meta)
        elif meta["base"] not in ROOT_ALLOWLIST:
            continue
        selected[pid] = {
            "proc": proc,
            "name": name,
            "ppid": ppid if ppid in procs else None,
            "role": meta["role"],
            "match": meta["match"],
        }

    roots = {pid for pid, meta in selected.items()
             if meta["role"] in ("server_app", "server")}
    if roots:
        for pid, (ppid, name) in procs.items():
            if pid in selected or pid in excluded:
                continue
            if match_allowlist(name, RUNNER_ALLOWLIST) is None:
                continue
            root = ancestor_root(pid, procs, roots)
            if root is None:
                continue
            try:
                proc, meta = cache.get(pid)
            except READ_ERRORS:
                continue
            if meta is None:
                base, source = resolve_identity(proc, name, RUNNER_ALLOWLIST)
                if base is None:
                    continue
                meta = {
                    "base": base,
                    "role": "runner",
                    "match": f"runner_of:{root} ({source})",
                }
                cache.set_meta(pid, meta)
            elif meta["base"] not in RUNNER_ALLOWLIST:
                continue
            selected[pid] = {
                "proc": proc,
                "name": name,
                "ppid": ppid if ppid in procs else None,
                "role": "runner",
                "match": meta["match"],
            }

    server = []
    clients = []
    read_errors = 0
    for pid, meta in selected.items():
        proc = meta["proc"]
        cpu_unknown = False
        try:
            with proc.oneshot():
                mem = proc.memory_info()
                cpu = proc.cpu_percent(None)
        except READ_ERRORS:
            read_errors += 1
            mem = None
            cpu = None
        if cpu is not None and not cache.is_primed(pid):
            cache.mark_primed(pid)
            cpu_unknown = True
            cpu = None
        entry = {
            "pid": pid,
            "ppid": meta["ppid"],
            "name": meta["name"],
            "role": meta["role"],
            "match": meta["match"],
            "cpu": cpu,
            "rss": mem.rss if mem is not None else None,
            "vms": mem.vms if mem is not None else None,
            "cpu_unknown": cpu_unknown,
        }
        if meta["role"] == "client":
            clients.append(entry)
        else:
            server.append(entry)

    server.sort(key=lambda item: item["pid"])
    clients.sort(key=lambda item: item["pid"])
    return {"server": server, "clients": clients, "read_errors": read_errors}


def fetch_models(api_url, timeout):
    url = api_url.rstrip("/") + "/api/ps"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url), timeout=timeout
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        return f"http_error:{exc.code}", [], None, None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            return "timeout", [], None, None
        return f"connection_error:{type(exc.reason).__name__}", [], None, None
    except TimeoutError:
        return "timeout", [], None, None
    except OSError as exc:
        return f"os_error:{type(exc).__name__}", [], None, None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "parse_error", [], None, None
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return "parse_error:models", [], None, None
    entries = [model for model in models if isinstance(model, dict)]
    names = [str(model.get("name", "")) for model in entries]
    try:
        size = sum(int(model.get("size") or 0) for model in entries)
        vram = sum(int(model.get("size_vram") or 0) for model in entries)
    except (TypeError, ValueError):
        return "parse_error:size", names, None, None
    return "ok", names, size, vram


class ApiPoller(threading.Thread):
    def __init__(self, api_url, interval, timeout):
        super().__init__(daemon=True)
        self.api_url = api_url
        self.interval = interval
        self.timeout = timeout
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._state = {
            "status": "starting",
            "models": [],
            "count": None,
            "size": None,
            "vram": None,
            "ok_mono": None,
            "attempts": 0,
            "failures": 0,
        }

    def poll_once(self):
        status, models, size, vram = fetch_models(self.api_url, self.timeout)
        with self._lock:
            self._state["status"] = status
            self._state["models"] = models
            self._state["count"] = len(models) if status == "ok" else None
            self._state["size"] = size
            self._state["vram"] = vram
            self._state["attempts"] += 1
            if status == "ok":
                self._state["ok_mono"] = time.monotonic()
            else:
                self._state["failures"] += 1

    def run(self):
        while not self._stop_event.wait(self.interval):
            self.poll_once()

    def stop(self):
        self._stop_event.set()

    def snapshot(self):
        with self._lock:
            state = dict(self._state)
        state["age"] = (
            time.monotonic() - state["ok_mono"] if state["ok_mono"] else None
        )
        return state


REQUEST_COLUMNS = [
    "run_id", "request_index", "window_id",
    "status", "http_status", "error",
    "model_requested", "model_returned",
    "prompt_sha256", "prompt_chars",
    "options_json", "keep_alive_sent", "stream",
    "t_send_mono_ns", "t_send_utc", "t_send_utc_minus_mono_ms",
    "t_first_token_mono_ns", "t_first_token_utc", "ttft_s",
    "t_end_mono_ns", "t_end_utc", "t_end_utc_minus_mono_ms",
    "window_s",
    "prompt_eval_count", "eval_count", "done_reason",
    "load_duration_s", "prompt_eval_duration_s", "eval_duration_s",
    "total_duration_s",
    "response_chars", "response_sha256", "response_text",
    "telemetry_samples_in_window", "first_sample_s",
    "last_sample_before_end_s", "max_gap_s",
]


def utc_minus_mono_ms(utc, mono_ns):
    return utc.timestamp() * 1000.0 - mono_ns / 1e6


def parse_generate_line(raw):
    """One NDJSON line from /api/generate; None for a blank keep-alive line."""
    text = raw.strip()
    if not text:
        return None
    payload = json.loads(text.decode("utf-8") if isinstance(raw, bytes) else text)
    if not isinstance(payload, dict):
        raise ValueError("NDJSON line is not an object")
    return payload


def window_coverage(samples_ns, start_ns, end_ns):
    """Samples in the half-open window and the largest gap including edges.

    The gap is measured from t_send to the first sample, between consecutive
    samples, and from the last sample to t_end: a window with no sample shows
    its whole duration, never a zero.
    """
    inside = [ns for ns in samples_ns if start_ns <= ns < end_ns]
    coverage = {
        "telemetry_samples_in_window": len(inside),
        "first_sample_s": None,
        "last_sample_before_end_s": None,
        "max_gap_s": None,
    }
    if end_ns > start_ns:
        marks = [start_ns] + inside + [end_ns]
        coverage["max_gap_s"] = (
            max(b - a for a, b in zip(marks, marks[1:])) / 1e9
        )
    if inside:
        coverage["first_sample_s"] = (inside[0] - start_ns) / 1e9
        coverage["last_sample_before_end_s"] = (end_ns - inside[-1]) / 1e9
    return coverage


def parse_keep_alive(text):
    """`-1` e `0` sono secondi numerici per Ollama, non durate.

    Inviare "-1" come stringa produce HTTP 400 ("missing unit in duration"):
    il valore numerico e' l'unico modo di chiedere la residenza illimitata.
    """
    value = text.strip()
    if value and (value.isdigit()
                  or (value.startswith("-") and value[1:].isdigit())):
        return int(value)
    return text


def ns_to_s(value):
    return round(value / 1e9, 6) if isinstance(value, (int, float)) else ""


class SampleLog:
    """Sampler timestamps shared with the request thread under one lock."""

    def __init__(self):
        self._lock = threading.Lock()
        self._samples = []

    def append(self, mono_ns):
        with self._lock:
            self._samples.append(mono_ns)

    def coverage(self, start_ns, end_ns):
        with self._lock:
            samples = list(self._samples)
        return window_coverage(samples, start_ns, end_ns)


class RequestDriver(threading.Thread):
    """Drive /api/generate requests on the sampler's monotonic clock.

    Each row is flushed before the next request, so an interrupted run leaves
    an auditable prefix. The driver never writes telemetry and never touches
    the energy path.
    """

    def __init__(self, api_url, model, prompt, options, keep_alive, count,
                 interval, timeout_s, tail_s, path, run_id, sample_log,
                 stop_event):
        super().__init__(daemon=True)
        self.api_url = api_url
        self.model = model
        self.prompt = prompt
        self.options = options
        self.keep_alive = keep_alive
        self.count = count
        self.interval = interval
        self.timeout_s = timeout_s
        self.tail_s = tail_s
        self.path = path
        self.run_id = run_id
        self.sample_log = sample_log
        self.stop_event = stop_event
        self.prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        self.prompt_chars = len(prompt)
        self._lock = threading.Lock()
        self._rows = []
        self._errors = 0
        self.driver_error = ""

    def payload(self):
        payload = {
            "model": self.model,
            "prompt": self.prompt,
            "stream": True,
            "options": self.options,
        }
        if self.keep_alive:
            payload["keep_alive"] = self.keep_alive_value()
        return payload

    def keep_alive_value(self):
        return parse_keep_alive(self.keep_alive)

    def keep_alive_sent(self):
        return self.keep_alive or "non inviato (default Ollama)"

    def _request_row(self, index):
        window_id = f"{self.run_id}-r{index:03d}"
        t_send_ns = time.monotonic_ns()
        t_send_utc = datetime.now(timezone.utc)
        status = "ok"
        http_status = None
        error = ""
        model_returned = ""
        first_ns = None
        first_utc = None
        final = {}
        response_hash = hashlib.sha256()
        response_chars = 0
        response_parts = []
        try:
            body = json.dumps(self.payload()).encode("utf-8")
            request = urllib.request.Request(
                self.api_url.rstrip("/") + "/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                http_status = response.status
                while True:
                    raw = response.readline()
                    if not raw:
                        break
                    try:
                        chunk = parse_generate_line(raw)
                    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                        status = "parse_error"
                        error = f"{type(exc).__name__}: {exc}"
                        break
                    if chunk is None:
                        continue
                    if not model_returned and isinstance(chunk.get("model"), str):
                        model_returned = chunk["model"]
                    if chunk.get("error"):
                        status = "api_error"
                        error = str(chunk["error"])
                        break
                    text = chunk.get("response")
                    if isinstance(text, str):
                        if text and first_ns is None:
                            first_ns = time.monotonic_ns()
                            first_utc = datetime.now(timezone.utc)
                        response_hash.update(text.encode("utf-8"))
                        response_chars += len(text)
                        response_parts.append(text)
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
            if isinstance(exc.reason, TimeoutError):
                status = "timeout"
            else:
                status = f"connection_error:{type(exc.reason).__name__}"
            error = str(exc)
        except TimeoutError as exc:
            status = "timeout"
            error = f"{type(exc).__name__}: {exc}"
        except OSError as exc:
            status = f"os_error:{type(exc).__name__}"
            error = str(exc)
        except Exception as exc:
            status = f"unexpected:{type(exc).__name__}"
            error = str(exc)
        t_end_ns = time.monotonic_ns()
        t_end_utc = datetime.now(timezone.utc)
        coverage = self.sample_log.coverage(t_send_ns, t_end_ns)
        return {
            "run_id": self.run_id,
            "request_index": index,
            "window_id": window_id,
            "status": status,
            "http_status": "" if http_status is None else http_status,
            "error": error,
            "model_requested": self.model,
            "model_returned": model_returned,
            "prompt_sha256": self.prompt_sha256,
            "prompt_chars": self.prompt_chars,
            "options_json": json.dumps(
                self.options, sort_keys=True, separators=(",", ":")
            ),
            "keep_alive_sent": self.keep_alive_sent(),
            "stream": True,
            "t_send_mono_ns": t_send_ns,
            "t_send_utc": t_send_utc.isoformat(timespec="milliseconds"),
            "t_send_utc_minus_mono_ms": r(
                utc_minus_mono_ms(t_send_utc, t_send_ns), 3
            ),
            "t_first_token_mono_ns": "" if first_ns is None else first_ns,
            "t_first_token_utc": (
                "" if first_utc is None
                else first_utc.isoformat(timespec="milliseconds")
            ),
            "ttft_s": "" if first_ns is None else r((first_ns - t_send_ns) / 1e9, 6),
            "t_end_mono_ns": t_end_ns,
            "t_end_utc": t_end_utc.isoformat(timespec="milliseconds"),
            "t_end_utc_minus_mono_ms": r(
                utc_minus_mono_ms(t_end_utc, t_end_ns), 3
            ),
            "window_s": r((t_end_ns - t_send_ns) / 1e9, 6),
            "prompt_eval_count": final.get("prompt_eval_count", ""),
            "eval_count": final.get("eval_count", ""),
            "done_reason": final.get("done_reason", ""),
            "load_duration_s": ns_to_s(final.get("load_duration")),
            "prompt_eval_duration_s": ns_to_s(final.get("prompt_eval_duration")),
            "eval_duration_s": ns_to_s(final.get("eval_duration")),
            "total_duration_s": ns_to_s(final.get("total_duration")),
            "response_chars": response_chars,
            "response_sha256": (
                response_hash.hexdigest() if response_chars else ""
            ),
            "response_text": "".join(response_parts),
            **coverage,
        }

    def run(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.DictWriter(handle, fieldnames=REQUEST_COLUMNS)
                writer.writeheader()
                handle.flush()
                for index in range(1, self.count + 1):
                    if self.stop_event.is_set():
                        break
                    row = self._request_row(index)
                    writer.writerow(row)
                    handle.flush()
                    with self._lock:
                        self._rows.append({
                            "window_id": row["window_id"],
                            "status": row["status"],
                        })
                        if row["status"] != "ok":
                            self._errors += 1
                    if index < self.count and self.stop_event.wait(self.interval):
                        break
            if not self.stop_event.is_set():
                self.stop_event.wait(self.tail_s)
        except Exception as exc:
            self.driver_error = f"{type(exc).__name__}: {exc}"
            print(f"Driver delle richieste fermato: {self.driver_error}",
                  flush=True)
        finally:
            self.stop_event.set()

    def snapshot(self):
        with self._lock:
            return list(self._rows), self._errors


def association_rule():
    return {
        "primary_clock": "time.monotonic_ns",
        "request_window": (
            "half-open [t_send_mono_ns, t_end_mono_ns); t_send is taken "
            "immediately before the HTTP request, t_end after the last NDJSON line"
        ),
        "telemetry_sample_membership": (
            "a telemetry sample belongs to a window iff "
            "t_send_mono_ns <= monotonic_ns < t_end_mono_ns"
        ),
        "telemetry_cpu_semantics": (
            "CPU percentages cover the interval ending at the sample's "
            "monotonic_ns; RSS is instantaneous. Both are diagnostics, not energy."
        ),
        "emi_increment_membership": (
            "an EMI increment [t_i, t_{i+1}) belongs to a window iff "
            "t_send <= t_i and t_{i+1} <= t_end; increments that straddle a "
            "boundary are excluded and counted"
        ),
        "emi_timestamp_offset": (
            "if the energy side uses the EMI ts_100ns clock, its offset to "
            "time.monotonic_ns must be measured on paired reads and declared; "
            "it is never assumed constant or zero"
        ),
        "wall_clock_role": (
            "utc_minus_mono_ms detects wall-clock steps; the production "
            "timestamp_start/end have one-second resolution "
            "(benchmark_unified.py:810) and cannot define a window of a few "
            "seconds by themselves"
        ),
        "same_boot_session": (
            "monotonic timestamps are comparable across processes only within "
            "the same boot session"
        ),
        "no_interpolation_here": (
            "this harness records windows and coverage; it does not interpolate "
            "counters or compute energy"
        ),
    }


def write_run_meta(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def r(value, ndigits=3):
    return round(value, ndigits) if value is not None else ""


def scan_processes(mode, cache, excluded):
    """Enumerazione dei processi, o struttura vuota con `mode == "off"`.

    Il ramo off non chiama `psutil.process_iter`: la condizione C del punto
    #67 misura l'assenza di quella chiamata, quindi non deve esistere un
    percorso alternativo che la reintroduca.
    """
    if mode == "off":
        return {"server": [], "clients": [], "read_errors": 0}
    return collect(cache, excluded)


def sweep_fields(sweep, ncpu):
    """Campi della riga derivati dalla scansione, uguali nei due modi."""
    server = sweep["server"]
    clients = sweep["clients"]
    cpu_sum = sum(item["cpu"] for item in server if item["cpu"] is not None)
    rss_sum = sum(item["rss"] for item in server if item["rss"] is not None)
    vms_sum = sum(item["vms"] for item in server if item["vms"] is not None)
    unknown = sum(1 for item in server if item["cpu_unknown"])
    runner_count = sum(1 for item in server if item["role"] == "runner")
    runner_rss = sum(item["rss"] for item in server
                     if item["role"] == "runner" and item["rss"] is not None)
    return {
        "ollama_server_count": len(server),
        "ollama_runner_count": runner_count,
        "ollama_runner_rss_mb": r(runner_rss / 1048576, 2),
        "ollama_server_pids": ";".join(str(item["pid"]) for item in server),
        "ollama_server_ppids": ";".join(
            "" if item["ppid"] is None else str(item["ppid"]) for item in server
        ),
        "ollama_server_names": ";".join(item["name"] for item in server),
        "ollama_server_roles": ";".join(item["role"] for item in server),
        "ollama_server_match_reasons": ";".join(
            item["match"] for item in server
        ),
        "ollama_client_count": len(clients),
        "ollama_client_pids": ";".join(str(item["pid"]) for item in clients),
        "ollama_client_ppids": ";".join(
            "" if item["ppid"] is None else str(item["ppid"]) for item in clients
        ),
        "ollama_client_names": ";".join(item["name"] for item in clients),
        "ollama_cpu_pct_sum_per_core": r(cpu_sum),
        "ollama_cpu_pct_host_capacity": r(cpu_sum / ncpu),
        "ollama_cpu_unknown_count": unknown,
        "proc_read_errors": sweep["read_errors"],
        "ollama_rss_sum_mb": r(rss_sum / 1048576, 2),
        "ollama_vms_sum_mb": r(vms_sum / 1048576, 2),
    }


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interval", type=float, default=1.0,
                        help="requested sampling interval in seconds")
    parser.add_argument("--output", default="")
    parser.add_argument("--api", default="http://127.0.0.1:11434")
    parser.add_argument("--api-interval", type=float, default=1.0,
                        help="seconds between /api/ps polls")
    parser.add_argument("--api-timeout", type=float, default=0.3)
    parser.add_argument("--run-id", default="",
                        help="shared by the telemetry, request and meta files")
    parser.add_argument("--requests", type=int, default=0,
                        help="number of /api/generate requests (0 = telemetry only)")
    parser.add_argument("--model", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--options-json", default="{}",
                        help="JSON object sent as Ollama options")
    parser.add_argument("--keep-alive", default="",
                        help="keep_alive sent verbatim; empty = not sent")
    parser.add_argument("--request-interval", type=float, default=5.0)
    parser.add_argument("--request-timeout", type=float, default=120.0)
    parser.add_argument("--tail", type=float, default=2.0,
                        help="seconds sampled after the last request")
    parser.add_argument("--requests-output", default="")
    parser.add_argument("--meta-output", default="")
    parser.add_argument(
        "--process-scan", choices=("full", "off"), default="full",
        help="per-process enumeration: full (default) or off (no process_iter)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.api_interval <= 0:
        parser.error("--api-interval must be > 0")
    if args.api_timeout <= 0:
        parser.error("--api-timeout must be > 0")
    if args.requests < 0:
        parser.error("--requests must be >= 0")
    if args.request_interval <= 0:
        parser.error("--request-interval must be > 0")
    if args.request_timeout <= 0:
        parser.error("--request-timeout must be > 0")
    if args.tail < 0:
        parser.error("--tail must be >= 0")
    try:
        options = json.loads(args.options_json)
    except json.JSONDecodeError as exc:
        parser.error(f"--options-json non valido: {exc}")
    if not isinstance(options, dict):
        parser.error("--options-json deve essere un oggetto JSON")
    if args.prompt and args.prompt_file:
        parser.error("--prompt e --prompt-file sono alternativi")
    prompt = args.prompt
    prompt_source = "inline" if args.prompt else ""
    if args.prompt_file:
        try:
            prompt = Path(args.prompt_file).read_text(encoding="utf-8")
        except OSError as exc:
            parser.error(f"--prompt-file non leggibile: {exc}")
        prompt_source = args.prompt_file
    if args.requests > 0:
        if not args.model:
            parser.error("--model richiesto con --requests > 0")
        if not prompt:
            parser.error("--prompt o --prompt-file richiesto con --requests > 0")
    elif args.model or prompt or args.prompt_file:
        parser.error("--model/--prompt/--prompt-file richiedono --requests > 0")

    run_id = args.run_id or f"{datetime.now():%Y%m%d_%H%M%S}_{os.getpid()}"
    out = Path(args.output or f"ollama_telemetry_{run_id}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    requests_out = Path(
        args.requests_output or out.with_name(out.stem + "_requests.csv")
    )
    meta_out = Path(args.meta_output or out.with_name(out.stem + "_meta.json"))
    ncpu = psutil.cpu_count(logical=True) or 1
    ram_total = psutil.virtual_memory().total
    platform_name = platform.platform()
    python_version = platform.python_version()
    psutil_version = psutil.__version__

    self_proc = psutil.Process()
    excluded = {self_proc.pid}
    try:
        excluded.update(parent.pid for parent in self_proc.parents())
    except READ_ERRORS:
        pass
    ancestors = sorted(pid for pid in excluded if pid != self_proc.pid)

    cache = ProcCache()
    psutil.cpu_percent(None)
    self_proc.cpu_percent(None)

    # The first enumeration warms psutil's process cache (seconds, once per
    # run); no sampled row must absorb that cost. Con --process-scan off non
    # c'e' cache da scaldare e nessuna enumerazione da nascondere.
    if args.process_scan == "full":
        print("Warm-up della cache dei processi...", flush=True)
        collect(cache, excluded)
    else:
        print("Scansione dei processi disattivata (--process-scan off).",
              flush=True)
    psutil.cpu_percent(None)
    self_proc.cpu_percent(None)
    time.sleep(args.interval)

    poller = ApiPoller(args.api, args.api_interval, args.api_timeout)
    poller.poll_once()
    poller.start()

    mono_clock = time.get_clock_info("monotonic")
    wall_clock = time.get_clock_info("time")
    columns = [
        "run_id",
        "timestamp_local", "timestamp_utc", "monotonic_ns",
        "utc_minus_mono_ms",
        "schema_version", "platform", "python_version", "psutil_version",
        "logical_cpus",
        "interval_requested_s", "interval_effective_s", "sweep_duration_s",
        "process_scan", "process_scan_s",
        "sweep_overrun_s", "schedule_missed_total",
        "system_cpu_pct", "system_ram_total_mb", "system_ram_available_mb",
        "system_ram_used_pct",
        "observer_pid", "observer_ancestor_pids", "observer_cpu_pct",
        "observer_rss_mb",
        "ollama_server_count", "ollama_runner_count", "ollama_runner_rss_mb",
        "ollama_server_pids", "ollama_server_ppids", "ollama_server_names",
        "ollama_server_roles", "ollama_server_match_reasons",
        "ollama_client_count", "ollama_client_pids", "ollama_client_ppids",
        "ollama_client_names",
        "ollama_cpu_pct_sum_per_core", "ollama_cpu_pct_host_capacity",
        "ollama_cpu_unknown_count", "proc_read_errors",
        "ollama_rss_sum_mb", "ollama_vms_sum_mb",
        "api_status", "api_models_count", "api_models",
        "api_size_sum_bytes", "api_vram_sum_bytes", "api_age_s",
        "api_attempts", "api_failures",
    ]
    sample_log = SampleLog()
    stop_event = threading.Event()
    meta = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "started_utc": datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        ),
        "started_mono_ns": time.monotonic_ns(),
        "platform": platform_name,
        "python_version": python_version,
        "psutil_version": psutil_version,
        "logical_cpus": ncpu,
        "observer_pid": self_proc.pid,
        "observer_ancestor_pids": ancestors,
        "clocks": {
            "monotonic": {
                "implementation": mono_clock.implementation,
                "resolution_s": mono_clock.resolution,
                "adjustable": mono_clock.adjustable,
            },
            "time": {
                "implementation": wall_clock.implementation,
                "resolution_s": wall_clock.resolution,
                "adjustable": wall_clock.adjustable,
            },
        },
        "sampling": {
            "interval_requested_s": args.interval,
            "process_scan": args.process_scan,
            "columns": columns,
        },
        "ollama": {
            "api_url": args.api,
            "requests_planned": args.requests,
            "request_interval_s": args.request_interval,
            "request_timeout_s": args.request_timeout,
            "tail_s": args.tail,
            "model_requested": args.model,
            "prompt": prompt,
            "prompt_source": prompt_source,
            "prompt_sha256": (
                hashlib.sha256(prompt.encode("utf-8")).hexdigest()
                if prompt else ""
            ),
            "prompt_chars": len(prompt),
            "options": options,
            "keep_alive_sent": (
                parse_keep_alive(args.keep_alive) if args.keep_alive
                else "non inviato (default Ollama)"
            ),
            "stream": True,
            "request_csv": (
                str(requests_out.resolve()) if args.requests > 0 else ""
            ),
        },
        "association": association_rule(),
        "status": "running",
        "counts": {},
    }
    write_run_meta(meta_out, meta)
    print(
        f"CSV: {out.resolve()} | meta: {meta_out.resolve()} "
        f"| Ctrl+C per terminare",
        flush=True,
    )
    rows = 0
    intervals = []
    offsets_ms = []
    requests_driver = None
    interrupted = False
    missed = 0
    prev_start = None
    next_deadline = time.monotonic()
    try:
        with out.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            if args.requests > 0:
                requests_driver = RequestDriver(
                    args.api, args.model, prompt, options, args.keep_alive,
                    args.requests, args.request_interval, args.request_timeout,
                    args.tail, requests_out, run_id, sample_log, stop_event,
                )
                requests_driver.start()
            while not stop_event.is_set():
                start_mono = time.monotonic()
                start_ns = time.monotonic_ns()
                local = datetime.now().astimezone()
                utc = datetime.now(timezone.utc)
                offset_ms = utc_minus_mono_ms(utc, start_ns)
                sample_log.append(start_ns)
                offsets_ms.append(offset_ms)
                vm = psutil.virtual_memory()
                sys_cpu = psutil.cpu_percent(None)
                scan_start = time.monotonic()
                sweep = scan_processes(args.process_scan, cache, excluded)
                scan_s = time.monotonic() - scan_start
                duration = time.monotonic() - start_mono
                effective = start_mono - prev_start if prev_start is not None else None
                api = poller.snapshot()
                try:
                    observer_mem = self_proc.memory_info()
                    observer_cpu = self_proc.cpu_percent(None)
                except READ_ERRORS:
                    observer_mem = None
                    observer_cpu = None

                server = sweep["server"]
                clients = sweep["clients"]
                cpu_sum = sum(item["cpu"] for item in server
                              if item["cpu"] is not None)
                rss_sum = sum(item["rss"] for item in server
                              if item["rss"] is not None)
                runner_count = sum(1 for item in server
                                   if item["role"] == "runner")

                row = {
                    "run_id": run_id,
                    "timestamp_local": local.isoformat(timespec="milliseconds"),
                    "timestamp_utc": utc.isoformat(timespec="milliseconds"),
                    "monotonic_ns": start_ns,
                    "utc_minus_mono_ms": r(offset_ms, 3),
                    "schema_version": SCHEMA_VERSION,
                    "platform": platform_name,
                    "python_version": python_version,
                    "psutil_version": psutil_version,
                    "logical_cpus": ncpu,
                    "interval_requested_s": args.interval,
                    "interval_effective_s": r(effective),
                    "sweep_duration_s": r(duration),
                    "process_scan": args.process_scan,
                    "process_scan_s": r(scan_s),
                    "sweep_overrun_s": r(max(0.0, duration - args.interval)),
                    "schedule_missed_total": missed,
                    "system_cpu_pct": r(sys_cpu),
                    "system_ram_total_mb": r(ram_total / 1048576, 2),
                    "system_ram_available_mb": r(vm.available / 1048576, 2),
                    "system_ram_used_pct": r(vm.percent),
                    "observer_pid": self_proc.pid,
                    "observer_ancestor_pids": ";".join(str(pid) for pid in ancestors),
                    "observer_cpu_pct": r(observer_cpu),
                    "observer_rss_mb": r(
                        observer_mem.rss / 1048576 if observer_mem else None, 2
                    ),
                    **sweep_fields(sweep, ncpu),
                    "api_status": api["status"],
                    "api_models_count": "" if api["count"] is None else api["count"],
                    "api_models": ";".join(api["models"]),
                    "api_size_sum_bytes": "" if api["size"] is None else api["size"],
                    "api_vram_sum_bytes": "" if api["vram"] is None else api["vram"],
                    "api_age_s": r(api["age"]),
                    "api_attempts": api["attempts"],
                    "api_failures": api["failures"],
                }
                writer.writerow(row)
                handle.flush()

                effective_txt = f"{effective:.2f}" if effective is not None else "--"
                count_txt = "-" if api["count"] is None else api["count"]
                print(
                    f"{local:%H:%M:%S} | dt {effective_txt} s "
                    f"| sweep {duration:.2f} s | CPU sistema {sys_cpu:5.1f}% "
                    f"| server {len(server)} runner {runner_count} "
                    f"({cpu_sum / ncpu:5.1f}% host) "
                    f"| RSS {rss_sum / 1048576:7.1f} MB | client {len(clients)} "
                    f"| api {api['status']} ({count_txt} modelli)"
                )
                rows += 1
                if effective is not None:
                    intervals.append(effective)

                prev_start = start_mono
                next_deadline += args.interval
                now = time.monotonic()
                if now < next_deadline:
                    if stop_event.wait(next_deadline - now):
                        break
                else:
                    missed += 1
                    next_deadline = now
    except KeyboardInterrupt:
        interrupted = True
        stop_event.set()
    finally:
        poller.stop()
        if requests_driver is not None:
            requests_driver.join(timeout=2.0)
        final = poller.snapshot()
        request_rows, request_errors = (
            requests_driver.snapshot() if requests_driver is not None else ([], 0)
        )
        driver_error = (
            requests_driver.driver_error if requests_driver is not None else ""
        )
        meta["finished_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        )
        meta["finished_mono_ns"] = time.monotonic_ns()
        meta["status"] = "interrupted" if interrupted else "completed"
        meta["counts"] = {
            "telemetry_rows": rows,
            "requests_recorded": len(request_rows),
            "requests_ok": sum(1 for row in request_rows if row["status"] == "ok"),
            "requests_failed": request_errors,
            "request_driver_error": driver_error,
            "api_attempts": final["attempts"],
            "api_failures": final["failures"],
        }
        if offsets_ms:
            meta["clock_offset"] = {
                "utc_minus_mono_ms_median": round(
                    statistics.median(offsets_ms), 3
                ),
                "drift_ms": round(max(offsets_ms) - min(offsets_ms), 3),
                "samples": len(offsets_ms),
            }
        write_run_meta(meta_out, meta)
        spread = ""
        if intervals:
            spread = (
                f" | intervallo mediano {statistics.median(intervals):.3f} s "
                f"(min {min(intervals):.3f}, max {max(intervals):.3f})"
            )
        request_txt = ""
        if requests_driver is not None:
            request_txt = (
                f" | richieste {len(request_rows)} "
                f"(ok {meta['counts']['requests_ok']}, "
                f"fallite {request_errors})"
            )
        if driver_error:
            request_txt += f" | driver: {driver_error}"
        print(
            f"Terminato. Righe: {rows}{spread}{request_txt} "
            f"| deadline perse: {missed} "
            f"| API fallite: {final['failures']}/{final['attempts']} "
            f"| file: {out.resolve()} | meta: {meta_out.resolve()}"
        )
    return 1 if request_errors or driver_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
