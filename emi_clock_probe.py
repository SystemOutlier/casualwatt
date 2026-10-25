#!/usr/bin/env python3
"""Read-only EMI clock and request-window probe.

Purpose: pair the PKG cumulative counter and its per-domain ts_100ns timestamp
with time.monotonic_ns, then apply the association rule of monitor_ollama.py
to an existing request table. This is a probe, not a channel: it does not
interpolate counters, does not subtract a baseline, and nothing it prints is a
protocol result or belongs in MEASURED_METHODS.

The counter clock and time.monotonic_ns do not share an origin. The offset is
measured here for every trace and reported with its drift; it is never
hard-coded, because it is not stable across sessions (compare the association
artifact of 25/10 with experiment_results/four_way_20261023_145041.csv).

Record:
  python emi_clock_probe.py --seconds 30 --interval 0.05 --output trace.csv

Analyze an existing trace against request windows:
  python emi_clock_probe.py --analyze trace.csv --requests requests.csv

Rule: with t_i the midpoint of (mono_before_ns, mono_after_ns), an increment
[t_i, t_{i+1}) belongs to the request window [t_send, t_end) iff
t_send <= t_i and t_{i+1} <= t_end. Increments that straddle a boundary are
excluded and counted. Negative increments are kept and counted: the counter is
never clamped here.
"""
import argparse
import csv
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from cwEnergyModular.energy.emi_backend import EMICounterBackend
except ImportError:
    EMICounterBackend = None

PWH_TO_J = 3.6e-9
PROBE_COLUMNS = ["mono_before_ns", "mono_after_ns", "utc", "ts_100ns", "pkg_pwh"]
REQUIRED_REQUEST_COLUMNS = ("window_id", "t_send_mono_ns", "t_end_mono_ns")


def record(output, seconds, interval):
    if EMICounterBackend is None:
        print("EMI backend non importabile", flush=True)
        return 2
    backend = EMICounterBackend()
    if not backend.available:
        print("EMI non disponibile", flush=True)
        return 2
    output.parent.mkdir(parents=True, exist_ok=True)
    next_at = time.monotonic()
    rows = 0
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(PROBE_COLUMNS)
        handle.flush()
        start = time.monotonic()
        while time.monotonic() - start < seconds:
            before = time.monotonic_ns()
            fields = backend.read_domains()
            after = time.monotonic_ns()
            utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            if fields:
                _, ts_100ns, pkg_pwh = fields["pkg"]
                writer.writerow([before, after, utc, ts_100ns, pkg_pwh])
                rows += 1
                handle.flush()
            next_at += interval
            delay = next_at - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_at = time.monotonic()
    backend.close()
    print(f"rows={rows} file={output.resolve()}", flush=True)
    return 0


def load_probe(path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            before = int(row["mono_before_ns"])
            after = int(row["mono_after_ns"])
            rows.append({
                "mid": (before + after) / 2.0,
                "ts": int(row["ts_100ns"]),
                "pwh": int(row["pkg_pwh"]),
            })
    rows.sort(key=lambda item: item["mid"])
    return rows


def load_requests(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [col for col in REQUIRED_REQUEST_COLUMNS
                   if col not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"colonne mancanti nel CSV richieste: {missing}")
        return list(reader)


def summarize(probe, requests):
    if len(probe) < 2:
        raise ValueError("la sonda ha meno di due righe: nessun incremento")
    span = (probe[-1]["mid"] - probe[0]["mid"]) / 1e9
    gaps = [(b["mid"] - a["mid"]) / 1e9 for a, b in zip(probe, probe[1:])]
    offsets = [row["mid"] / 1e9 - row["ts"] / 1e7 for row in probe]
    print(
        f"probe: {len(probe)} righe su {span:.3f} s | intervallo mediano "
        f"{statistics.median(gaps):.4f} s (min {min(gaps):.4f}, "
        f"max {max(gaps):.4f})"
    )
    print(
        "offset mono - ts/1e7: mediana "
        f"{statistics.median(offsets):.6f} s, drift "
        f"{(max(offsets) - min(offsets)) * 1000:.3f} ms "
        "(misurato su questa traccia, non assunto)"
    )
    for request in requests:
        start = int(request["t_send_mono_ns"])
        end = int(request["t_end_mono_ns"])
        contained = []
        straddle = []
        for a, b in zip(probe, probe[1:]):
            if start <= a["mid"] and b["mid"] <= end:
                contained.append((a, b))
            elif (a["mid"] < start < b["mid"]) or (a["mid"] < end < b["mid"]):
                straddle.append((a, b))
        deltas = [b["pwh"] - a["pwh"] for a, b in contained]
        energy = sum(deltas) * PWH_TO_J
        covered = sum((b["mid"] - a["mid"]) for a, b in contained) / 1e9
        window = (end - start) / 1e9
        straddle_j = sum(
            (b["pwh"] - a["pwh"]) for a, b in straddle
        ) * PWH_TO_J
        negative = sum(1 for delta in deltas if delta < 0)
        mean_w = energy / covered if covered else float("nan")
        print(
            f"\n{request.get('window_id', '?')} [{request.get('status', '?')}]: "
            f"finestra {window:.3f} s | contenuti {len(contained)} | "
            f"span {covered:.3f} s | energia sonda {energy:.3f} J | "
            f"potenza media {mean_w:.2f} W"
        )
        print(
            f"  straddling esclusi: {len(straddle)} incrementi "
            f"(energia intera {straddle_j:.3f} J, non tutta nel bordo) "
            f"| tempo scoperto ai bordi "
            f"{(window - covered) * 1000:.1f} ms | incrementi negativi "
            f"conservati: {negative}"
        )
    return 0


def analyze(probe_path, requests_path):
    probe = load_probe(probe_path)
    requests = load_requests(requests_path)
    if not requests:
        print("CSV richieste vuoto", flush=True)
        return 1
    return summarize(probe, requests)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--interval", type=float, default=0.05)
    parser.add_argument("--output", default="")
    parser.add_argument("--analyze", default="",
                        help="CSV della sonda da analizzare invece di registrare")
    parser.add_argument("--requests", default="",
                        help="CSV delle richieste, richiesto con --analyze")
    args = parser.parse_args()
    if args.analyze:
        if not args.requests:
            parser.error("--requests richiesto con --analyze")
        try:
            return analyze(Path(args.analyze), Path(args.requests))
        except (OSError, ValueError, KeyError) as exc:
            print(f"Analisi non riuscita: {type(exc).__name__}: {exc}",
                  file=sys.stderr)
            return 1
    if args.seconds <= 0:
        parser.error("--seconds must be > 0")
    if args.interval <= 0:
        parser.error("--interval must be > 0")
    output = Path(
        args.output or f"emi_clock_probe_{datetime.now():%Y%m%d_%H%M%S}.csv"
    )
    return record(output, args.seconds, args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
