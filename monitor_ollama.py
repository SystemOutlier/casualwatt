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

Install: python -m pip install psutil
Run: python monitor_ollama.py --interval 1
"""
import argparse
import csv
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

SCHEMA_VERSION = "telemetry/1"
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


def r(value, ndigits=3):
    return round(value, ndigits) if value is not None else ""


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--interval", type=float, default=1.0,
                        help="requested sampling interval in seconds")
    parser.add_argument("--output", default="")
    parser.add_argument("--api", default="http://127.0.0.1:11434")
    parser.add_argument("--api-interval", type=float, default=1.0,
                        help="seconds between /api/ps polls")
    parser.add_argument("--api-timeout", type=float, default=0.3)
    args = parser.parse_args()
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    if args.api_interval <= 0:
        parser.error("--api-interval must be > 0")
    if args.api_timeout <= 0:
        parser.error("--api-timeout must be > 0")

    out = Path(args.output or f"ollama_telemetry_{datetime.now():%Y%m%d_%H%M%S}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
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
    # run); no sampled row must absorb that cost.
    print("Warm-up della cache dei processi...", flush=True)
    collect(cache, excluded)
    psutil.cpu_percent(None)
    self_proc.cpu_percent(None)
    time.sleep(args.interval)

    poller = ApiPoller(args.api, args.api_interval, args.api_timeout)
    poller.poll_once()
    poller.start()

    columns = [
        "timestamp_local", "timestamp_utc", "monotonic_ns",
        "schema_version", "platform", "python_version", "psutil_version",
        "logical_cpus",
        "interval_requested_s", "interval_effective_s", "sweep_duration_s",
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
    print(f"CSV: {out.resolve()} | Ctrl+C per terminare")
    rows = 0
    intervals = []
    missed = 0
    prev_start = None
    next_deadline = time.monotonic()
    try:
        with out.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            while True:
                start_mono = time.monotonic()
                start_ns = time.monotonic_ns()
                local = datetime.now().astimezone()
                utc = datetime.now(timezone.utc)
                vm = psutil.virtual_memory()
                sys_cpu = psutil.cpu_percent(None)
                sweep = collect(cache, excluded)
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
                vms_sum = sum(item["vms"] for item in server
                              if item["vms"] is not None)
                unknown = sum(1 for item in server if item["cpu_unknown"])
                runner_count = sum(1 for item in server
                                   if item["role"] == "runner")
                runner_rss = sum(item["rss"] for item in server
                                 if item["role"] == "runner"
                                 and item["rss"] is not None)
                server_ppids = ";".join(
                    "" if item["ppid"] is None else str(item["ppid"])
                    for item in server
                )
                client_ppids = ";".join(
                    "" if item["ppid"] is None else str(item["ppid"])
                    for item in clients
                )

                row = {
                    "timestamp_local": local.isoformat(timespec="milliseconds"),
                    "timestamp_utc": utc.isoformat(timespec="milliseconds"),
                    "monotonic_ns": start_ns,
                    "schema_version": SCHEMA_VERSION,
                    "platform": platform_name,
                    "python_version": python_version,
                    "psutil_version": psutil_version,
                    "logical_cpus": ncpu,
                    "interval_requested_s": args.interval,
                    "interval_effective_s": r(effective),
                    "sweep_duration_s": r(duration),
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
                    "ollama_server_count": len(server),
                    "ollama_runner_count": runner_count,
                    "ollama_runner_rss_mb": r(runner_rss / 1048576, 2),
                    "ollama_server_pids": ";".join(str(item["pid"]) for item in server),
                    "ollama_server_ppids": server_ppids,
                    "ollama_server_names": ";".join(item["name"] for item in server),
                    "ollama_server_roles": ";".join(item["role"] for item in server),
                    "ollama_server_match_reasons": ";".join(
                        item["match"] for item in server
                    ),
                    "ollama_client_count": len(clients),
                    "ollama_client_pids": ";".join(str(item["pid"]) for item in clients),
                    "ollama_client_ppids": client_ppids,
                    "ollama_client_names": ";".join(item["name"] for item in clients),
                    "ollama_cpu_pct_sum_per_core": r(cpu_sum),
                    "ollama_cpu_pct_host_capacity": r(cpu_sum / ncpu),
                    "ollama_cpu_unknown_count": unknown,
                    "proc_read_errors": sweep["read_errors"],
                    "ollama_rss_sum_mb": r(rss_sum / 1048576, 2),
                    "ollama_vms_sum_mb": r(vms_sum / 1048576, 2),
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
                    time.sleep(next_deadline - now)
                else:
                    missed += 1
                    next_deadline = now
    except KeyboardInterrupt:
        final = poller.snapshot()
        spread = ""
        if intervals:
            spread = (
                f" | intervallo mediano {statistics.median(intervals):.3f} s "
                f"(min {min(intervals):.3f}, max {max(intervals):.3f})"
            )
        print(
            f"Terminato. Righe: {rows}{spread} | deadline perse: {missed} "
            f"| API fallite: {final['failures']}/{final['attempts']} "
            f"| file: {out.resolve()}"
        )
    finally:
        poller.stop()


if __name__ == "__main__":
    main()
