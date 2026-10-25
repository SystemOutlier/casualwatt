#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experiment_additivity.py - La quota di tempo CPU e' additiva sull'energia?

Perche' esiste. ``E_worker = E_attiva * d_ollama/d_busy`` e' la STIMA di
attribuzione usata in produzione: ripartisce l'energia incrementale del
dominio PKG con la quota di tempo CPU BUSY di sistema consumata dall'albero
del motore. L'ipotesi non e' un teorema: vale se il tempo CPU e' un proxy
proporzionale dell'energia. Questo harness la confronta con la somma reale dei
carichi, senza inventare soglie.

Disegno (protocollo v4 per la baseline, non per i criteri):

  * baseline PRE: 3 finestre da 30 s a riposo, P_pre = mediana (P1.3), applicata;
  * baseline POST: altre 3 finestre da 30 s alla fine, diagnostica, MAI applicata;
  * blocchi: ogni blocco contiene le tre condizioni in ordine casuale
    (``--seed`` fisso, l'ordine e' stampato e salvato), cosi' la deriva lenta
    della macchina non favorisce una condizione;
  * (A) richieste Ollama sequenziali per ``--trial-s`` secondi, nessun altro carico;
  * (B) solo ``--n-procs`` processi busy-loop Python (multiprocessing), stessa durata;
  * (C) entrambi insieme, stessa durata;
  * per ogni prova la finestra energetica e' [t0, t1] sul contatore EMI esatto
    e la quota e' letta agli stessi estremi (``SESSION.read_cpu_edge``).

Che cosa produce, per prova: E_attiva grezza CON SEGNO, d_ollama, d_busy,
share grezzo e limitato, anomalia, E_worker, identita' dei worker, flag di
uscita e ritardo residuo delle letture di bordo. Alla fine: media e intervallo
[min, max] con semi-range per condizione (mai una deviazione standard: con
pochi blocchi non e' una stima di varianza, P4.12) e il confronto
E_worker(C) contro E_active(A), piu' E_active(C) contro E_active(A)+E_active(B).

NON stampa giudizi di accettazione: non c'e' una banda preregistrata per
questo esperimento, quindi i numeri si riportano e basta.

Vincoli operativi:
  * serve SOLO il canale EMI (``emi-counter``), nessun amministratore: lo
    script si ferma se il canale attivo e' un altro;
  * il server Ollama deve essere gia' in esecuzione (una richiesta fallita
    ferma il run, non produce una riga a zero);
  * prima della calibrazione PRE vanno chiusi browser, Qoder e HWiNFO (sono
    carico e sporcano la baseline), e non vanno aperti fino alla POST;
  * i processi busy-loop sono figli di questo processo, non dell'albero
    Ollama: restano fuori dal numeratore e dentro il denominatore, che e'
    esattamente il punto del test;
  * il sampler della sessione e questo harness costano CPU in tutte le
    condizioni: e' un carico comune, dichiarato, non una correzione.

Uso:
  py experiment_additivity.py
  py experiment_additivity.py --blocks 7 --trial-s 45 --n-procs 8

Output:
  experiment_results/additivity_<ts>.csv    una riga per prova
  experiment_results/additivity_<ts>.json   argomenti, baseline, righe, riepilogo
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import random
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

import psutil  # noqa: E402
import requests  # noqa: E402

import config  # noqa: E402
from energy.energy_session import SESSION  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402
from energy.worker_tree import worker_cpu_delta  # noqa: E402

CONDITIONS = ("A", "B", "C")
LABEL = {
    "A": "A: Ollama da solo",
    "B": "B: solo carico CPU noto",
    "C": "C: Ollama + carico CPU",
}
PROMPT = ("Rispondi in italiano in modo breve: spiega perche' e' importante "
          "verificare le informazioni.")

CSV_FIELDS = [
    "block", "order_in_block", "condition",
    "timestamp_start", "timestamp_end", "dt_s",
    "package_energy_j", "package_energy_raw_j", "baseline_energy_j",
    "active_energy_raw_j", "active_energy_j", "active_valid",
    "d_ollama_cpu_s", "d_busy_cpu_s", "cpu_time_share_raw", "cpu_time_share",
    "share_anomaly", "ollama_active_energy_j", "worker_exit_in_window",
    "cpu_busy_capacity_cores", "cpu_share_window_s", "cpu_time_resolution_s",
    "package_window_source", "energy_calculation_method",
    "n_requests", "n_busy_procs", "n_worker_procs",
    "edge_start_offset_s", "edge_end_offset_s", "keep_alive_sent",
]


# ---------------------------------------------------------------------------
# carico CPU noto
# ---------------------------------------------------------------------------
def _busy_loop(stop_event) -> None:
    """Un core al 100% finche' l'evento non viene impostato (nessun I/O)."""
    x = 1
    while not stop_event.is_set():
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF


def _cpu_seconds_of(pid: int) -> float:
    try:
        t = psutil.Process(pid).cpu_times()
        return float(t.user + t.system)
    except psutil.Error:
        return -1.0


def _start_busy(ctx, n_procs: int, settle_s: float):
    """Avvia N busy-loop e verifica che stiano davvero consumando CPU."""
    stop = ctx.Event()
    procs = [ctx.Process(target=_busy_loop, args=(stop,), daemon=True)
             for _ in range(n_procs)]
    for p in procs:
        p.start()
    deadline = time.monotonic() + max(float(settle_s), 0.0)
    while time.monotonic() < deadline:
        time.sleep(0.05)
    for p in procs:
        if not p.is_alive():
            _stop_busy(procs, stop)
            raise RuntimeError(f"processo busy-loop {p.pid} morto all'avvio")
    if sum(max(_cpu_seconds_of(p.pid), 0.0) for p in procs) <= 0.0:
        _stop_busy(procs, stop)
        raise RuntimeError("i busy-loop non hanno consumato CPU: carico non "
                           "verificato, la condizione B non misurerebbe nulla")
    return procs, stop


def _stop_busy(procs, stop) -> None:
    stop.set()
    for p in procs:
        p.join(timeout=5.0)
        if p.is_alive():
            p.terminate()
            p.join(timeout=5.0)


# ---------------------------------------------------------------------------
# richieste Ollama
# ---------------------------------------------------------------------------
def _payload(args) -> dict:
    """Payload identico a ``benchmark_unified._ollama_payload``.

    Duplicato di proposito: importare benchmark_unified tira dentro la GUI e i
    provider cloud, che questo esperimento non usa.
    """
    payload = {
        "model": args.model,
        "prompt": PROMPT,
        "stream": False,
        "options": {"temperature": args.temperature,
                    "num_predict": args.num_predict},
    }
    if config.OLLAMA_KEEP_ALIVE:
        payload["keep_alive"] = config.OLLAMA_KEEP_ALIVE
    return payload


def _request_loop(stop_event: threading.Event, payload: dict,
                  timeout_s: float, stats: dict) -> None:
    """Richieste sequenziali finche' la finestra non si chiude.

    Una richiesta in volo al confine viene lasciata finire (il suo tempo CPU
    oltre t_end resta fuori dalla finestra), poi il thread esce.
    """
    while not stop_event.is_set():
        try:
            r = requests.post(config.OLLAMA_GENERATE_ENDPOINT, json=payload,
                              timeout=timeout_s)
            r.raise_for_status()
            data = r.json()
            stats["n"] += 1
            stats["tokens_out"] += int(data.get("eval_count") or 0)
        except Exception as exc:  # noqa: BLE001 - il run si ferma, non si maschera
            stats["errors"].append(f"{type(exc).__name__}: {exc}")
            stop_event.set()
            return


def _installed_models() -> list:
    r = requests.get(config.OLLAMA_TAGS_ENDPOINT, timeout=10)
    r.raise_for_status()
    return sorted(m.get("name", "") for m in r.json().get("models", []))


# ---------------------------------------------------------------------------
# una prova
# ---------------------------------------------------------------------------
def _run_trial(condition: str, args, ctx) -> dict:
    n_procs = args.n_procs if condition in ("B", "C") else 0
    procs, busy_stop = ([], None)
    if n_procs:
        procs, busy_stop = _start_busy(ctx, n_procs, args.settle_s)

    req_stop = threading.Event()
    req_stats = {"n": 0, "tokens_out": 0, "errors": []}
    thread = None

    t0 = time.monotonic()
    wall0 = time.time()

    # Qualunque cosa succeda nella finestra, richieste e busy-loop vanno spenti:
    # un carico che sopravvive alla prova sporcherebbe la calibrazione POST.
    try:
        edge0 = SESSION.read_cpu_edge()
        offset0 = time.monotonic() - t0

        if condition in ("A", "C"):
            thread = threading.Thread(
                target=_request_loop,
                args=(req_stop, _payload(args), args.request_timeout_s, req_stats),
                daemon=True,
            )
            thread.start()

        # Attesa del confine; se la richiesta e' gia' fallita si chiude subito
        # la finestra (il run si fermera', ma il tempo non si butta).
        deadline = t0 + args.trial_s
        while time.monotonic() < deadline and not req_stop.is_set():
            time.sleep(min(0.2, max(deadline - time.monotonic(), 0.0)))
        t1 = time.monotonic()
        wall1 = time.time()
        edge1 = SESSION.read_cpu_edge()
        offset1 = time.monotonic() - t1
    finally:
        req_stop.set()
        if thread is not None:
            thread.join(timeout=args.request_timeout_s + 5.0)
        if busy_stop is not None:
            _stop_busy(procs, busy_stop)

    if thread is not None and thread.is_alive():
        raise RuntimeError(
            "la richiesta Ollama non e' terminata entro il timeout: "
            "finestra non chiusa, run fermato")
    if req_stats["errors"]:
        raise RuntimeError("richiesta Ollama fallita: " + req_stats["errors"][0])

    delta = worker_cpu_delta(edge0["worker"], edge1["worker"])
    direct_busy = max(float(edge1["busy"]) - float(edge0["busy"]), 0.0)
    pids = sorted({w.pid for w in edge0["tree"]} | {w.pid for w in edge1["tree"]})

    profiler = CasualWattLocalEnergyProfiler()
    profiler.session = SESSION
    res = profiler.profile_window(
        t0, t1,
        ollama_pids=pids,
        direct_cpu_delta=delta.d_ollama,
        direct_busy_delta=direct_busy,
        worker_exit_in_window=delta.worker_exit_in_window,
    )

    return {
        "condition": condition,
        "timestamp_start": datetime.fromtimestamp(wall0).isoformat(timespec="seconds"),
        "timestamp_end": datetime.fromtimestamp(wall1).isoformat(timespec="seconds"),
        "dt_s": round(t1 - t0, 6),
        "package_energy_j": res.package_energy_j,
        "package_energy_raw_j": res.package_energy_raw_j,
        "baseline_energy_j": res.baseline_energy_j,
        "active_energy_raw_j": res.active_energy_raw_j,
        "active_energy_j": res.active_energy_j,
        "active_valid": res.active_valid,
        "d_ollama_cpu_s": res.d_ollama_cpu_s,
        "d_busy_cpu_s": res.d_busy_s,
        "cpu_time_share_raw": res.cpu_time_share_raw,
        "cpu_time_share": res.cpu_time_share,
        "share_anomaly": res.share_anomaly,
        "ollama_active_energy_j": res.ollama_active_energy_j,
        "worker_exit_in_window": res.worker_exit_in_window,
        "cpu_busy_capacity_cores": res.cpu_busy_capacity_cores,
        "cpu_share_window_s": res.cpu_share_window_s,
        "cpu_time_resolution_s": res.cpu_time_resolution_s,
        "package_window_source": res.package_window_source,
        "energy_calculation_method": res.energy_calculation_method,
        "n_requests": req_stats["n"],
        "tokens_out": req_stats["tokens_out"],
        "n_busy_procs": n_procs,
        "n_worker_procs": len(pids),
        "edge_start_offset_s": round(offset0, 6),
        "edge_end_offset_s": round(offset1, 6),
        "keep_alive_sent": (config.OLLAMA_KEEP_ALIVE
                            or "non inviato (default Ollama)"),
        "born": [f"{w.pid}:{w.name}".strip(":") for w in delta.born],
        "lost": [f"{w.pid}:{w.name}".strip(":") for w in delta.lost],
        "reused_pids": list(delta.reused_pids),
        "notes": list(res.notes),
    }


# ---------------------------------------------------------------------------
# riepilogo
# ---------------------------------------------------------------------------
def _stats(values) -> dict:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"n": 0}
    return {
        "n": len(vals),
        "mean": sum(vals) / len(vals),
        "min": min(vals),
        "max": max(vals),
        "median": statistics.median(vals),
        "semi_range": (max(vals) - min(vals)) / 2.0,
    }


def _fmt_stats(s: dict, unit: str = "") -> str:
    if not s.get("n"):
        return "n=0"
    return (f"media {s['mean']:.3f}{unit}  "
            f"[min {s['min']:.3f}, max {s['max']:.3f}]{unit}  "
            f"semi-range {s['semi_range']:.3f}{unit}  mediana {s['median']:.3f}{unit}")


METRICS = [
    ("package_energy_raw_j", "E_package grezza [J]"),
    ("active_energy_raw_j", "E_attiva grezza (con segno) [J]"),
    ("d_ollama_cpu_s", "d_ollama [s]"),
    ("d_busy_cpu_s", "d_busy [s]"),
    ("cpu_time_share_raw", "share grezzo d_ollama/d_busy"),
    ("ollama_active_energy_j", "E_worker = E_attiva x share [J]"),
]


def _summarize(rows: list) -> dict:
    out = {}
    for cond in CONDITIONS:
        subset = [r for r in rows if r["condition"] == cond]
        out[cond] = {key: _stats([r.get(key) for r in subset])
                     for key, _ in METRICS}
    return out


def _print_summary(rows: list, summary: dict) -> None:
    print("\n=== Riepilogo per condizione ===")
    print("Semi-range = (max - min) / 2: e' un intervallo osservato, non una "
          "deviazione standard (P4.12).")
    for cond in CONDITIONS:
        n = summary[cond]["active_energy_raw_j"].get("n", 0)
        print(f"\n{LABEL[cond]}  (n={n})")
        if not n:
            continue
        for key, label in METRICS:
            print(f"  {label:<38} {_fmt_stats(summary[cond][key])}")

    print("\n=== Confronti ===")
    by = {cond: [r for r in rows if r["condition"] == cond] for cond in CONDITIONS}

    def paired(a_key, b_key):
        a = {r["block"]: r.get(a_key) for r in by["A"]}
        b = {r["block"]: r.get(b_key) for r in by["C"]}
        return [b[k] - a[k] for k in sorted(set(a) & set(b))
                if a[k] is not None and b[k] is not None]

    ew_c = summary["C"]["ollama_active_energy_j"]
    ea_a = summary["A"]["active_energy_raw_j"]
    ea_b = summary["B"]["active_energy_raw_j"]
    ea_c = summary["C"]["active_energy_raw_j"]

    print("E_worker(C) vs E_active(A) - la stima di attribuzione con il carico "
          "estraneo attivo contro l'energia misurata del modello da solo:")
    print(f"  E_worker(C) media      {ew_c.get('mean', float('nan')):.3f} J")
    print(f"  E_active(A) media      {ea_a.get('mean', float('nan')):.3f} J")
    if ea_a.get("mean") is not None and ew_c.get("mean") is not None:
        print(f"  differenza (C-A)       {ew_c['mean'] - ea_a['mean']:+.3f} J")
        if ea_a["mean"]:
            print(f"  rapporto C/A           {ew_c['mean'] / ea_a['mean']:.3f}")
    d = paired("active_energy_raw_j", "ollama_active_energy_j")
    if d:
        s = _stats(d)
        print(f"  differenze appaiate per blocco (C-A)  "
              f"{_fmt_stats(s, ' J')}")

    print("\nE_active(C) vs E_active(A) + E_active(B) - additivita' in energia "
          "(stesso contatore, stessa baseline):")
    if (ea_a.get("mean") is not None and ea_b.get("mean") is not None
            and ea_c.get("mean") is not None):
        somma = ea_a["mean"] + ea_b["mean"]
        print(f"  A + B (medie)          {somma:.3f} J")
        print(f"  C (media)              {ea_c['mean']:.3f} J")
        if somma:
            print(f"  differenza (C - A - B) {ea_c['mean'] - somma:+.3f} J   "
                  f"rapporto C/(A+B) {ea_c['mean'] / somma:.3f}")
    sum_ac = {r["block"]: r.get("active_energy_raw_j") for r in by["A"]}
    b_c = {r["block"]: r.get("active_energy_raw_j") for r in by["B"]}
    c_c = {r["block"]: r.get("active_energy_raw_j") for r in by["C"]}
    d2 = [c_c[k] - sum_ac[k] - b_c[k] for k in sorted(set(sum_ac) & set(b_c) & set(c_c))
          if None not in (sum_ac[k], b_c[k], c_c[k])]
    if d2:
        print(f"  differenze appaiate per blocco (C-A-B)  "
              f"{_fmt_stats(_stats(d2), ' J')}")

    print("\nControllo: E_worker(B) con il solo carico estraneo:")
    print(f"  {_fmt_stats(summary['B']['ollama_active_energy_j'], ' J')}")

    invalid = [r for r in rows if r.get("active_valid") is False]
    exits = [r for r in rows if r.get("worker_exit_in_window")]
    anomalies = [r for r in rows if r.get("share_anomaly")]
    print("\nRighe dichiarate (riportate, non scartate): "
          f"active_valid=False {len(invalid)}, "
          f"worker_exit_in_window {len(exits)}, "
          f"anomalia share {len(anomalies)}.")
    print("Nessuna soglia di accettazione: questo harness stampa i numeri, non "
          "un verdetto.")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def _parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Additivita' della quota di tempo CPU sull'energia EMI.")
    p.add_argument("--model", default="llama3.2:3b")
    p.add_argument("--blocks", type=int, default=5,
                   help="blocchi (ognuno con A, B, C in ordine casuale)")
    p.add_argument("--trial-s", type=float, default=30.0,
                   help="durata di ogni prova [s]")
    p.add_argument("--n-procs", type=int,
                   default=int(psutil.cpu_count(logical=False) or 1),
                   help="processi busy-loop per la condizione B (default: core fisici)")
    p.add_argument("--num-predict", type=int, default=160)
    p.add_argument("--temperature", type=float, default=config.DEFAULT_TEMPERATURE)
    p.add_argument("--seed", type=int, default=20261025,
                   help="seme dell'ordine casuale dentro i blocchi")
    p.add_argument("--settle-s", type=float, default=2.0,
                   help="attesa fra prove e avvio del carico prima di t0 [s]")
    p.add_argument("--request-timeout-s", type=float, default=120.0)
    p.add_argument("--warmup-requests", type=int, default=1,
                   help="richieste prima della baseline PRE (caricano i pesi)")
    p.add_argument("--countdown-s", type=float, default=5.0,
                   help="preavviso prima della calibrazione PRE [s]")
    args = p.parse_args(argv)
    if args.blocks < 1:
        p.error("--blocks deve essere >= 1")
    if args.trial_s < 1.0:
        p.error("--trial-s deve essere >= 1 s")
    if args.n_procs < 1:
        p.error("--n-procs deve essere >= 1")
    if args.warmup_requests < 0:
        p.error("--warmup-requests deve essere >= 0")
    return args


def main(argv=None) -> int:
    args = _parse_args(argv)

    print("=== experiment_additivity ===")
    print(f"Data: {datetime.now().isoformat(timespec='seconds')}")
    print(f"Host: {psutil.cpu_count(logical=True)} core logici, "
          f"{psutil.cpu_count(logical=False)} fisici; modello {args.model}")
    print(f"Blocchi: {args.blocks} x 3 condizioni; prova {args.trial_s:.0f} s; "
          f"busy-loop {args.n_procs} processi; seme {args.seed}")

    try:
        installed = _installed_models()
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: server Ollama non raggiungibile su "
              f"{config.OLLAMA_GENERATE_ENDPOINT}: {type(exc).__name__}: {exc}")
        return 2
    if args.model not in installed:
        print(f"ERRORE: modello '{args.model}' non installato. Disponibili: "
              f"{', '.join(installed) or 'nessuno'}")
        return 2

    was_running = SESSION.running
    if not was_running:
        SESSION.start()
        time.sleep(SESSION.interval_s * 2)

    if SESSION.source_method != "emi-counter":
        print(f"ERRORE: canale attivo '{SESSION.source_method}', atteso "
              "'emi-counter'. Questo esperimento e' definito sul contatore EMI "
              "(nessun amministratore richiesto); fermarsi e riportare il "
              "problema invece di misurare su un altro canale.")
        if not was_running:
            SESSION.stop()
        return 2

    tree = SESSION.find_worker_tree()
    if not tree:
        print("ERRORE: nessun processo del motore locale (Ollama offline?). "
              "Avviare il server e riprovare.")
        if not was_running:
            SESSION.stop()
        return 2
    print("Albero worker: " + ", ".join(
        f"{w.pid}:{w.name}@{w.create_time:.0f}" for w in tree))
    stray = SESSION.find_stray_runner_procs(tree)
    if stray:
        print("AVVISO: runner del modello FUORI dall'albero misurato (non "
              "attribuito): " + ", ".join(
                  f"{w.pid}:{w.name}@{w.create_time:.0f}" for w in stray))

    res_s = CasualWattLocalEnergyProfiler.probe_cpu_time_resolution()
    SESSION.cpu_time_resolution_s = res_s
    print("Risoluzione osservata dei cpu_times: "
          + (f"{res_s:.4f} s" if res_s else "non misurabile"))

    payload = _payload(args)
    for i in range(args.warmup_requests):
        print(f"Warm-up {i + 1}/{args.warmup_requests}: richiesta Ollama...")
        try:
            r = requests.post(config.OLLAMA_GENERATE_ENDPOINT, json=payload,
                              timeout=args.request_timeout_s)
            r.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"ERRORE: warm-up fallito: {type(exc).__name__}: {exc}")
            if not was_running:
                SESSION.stop()
            return 2
    time.sleep(args.settle_s)

    print(f"\nBaseline PRE: 3 finestre da 30 s a riposo, mediana (P1.3). "
          f"Chiudere browser, Qoder e HWiNFO.")
    for sec in range(int(args.countdown_s), 0, -1):
        print(f"  avvio fra {sec} s... (non generare carico)")
        time.sleep(1.0)
    try:
        p_pre = SESSION.calibrate_idle()
    except Exception as exc:  # noqa: BLE001
        print(f"ERRORE: calibrazione PRE fallita: {type(exc).__name__}: {exc}")
        if not was_running:
            SESSION.stop()
        return 2
    reps_pre = list(getattr(SESSION, "_idle_reps", []) or [])
    print(f"P_pre = {p_pre:.3f} W (mediana di "
          f"{[round(x, 3) for x in reps_pre]})")

    ctx = mp.get_context("spawn")
    rng = random.Random(args.seed)
    rows = []
    orders = {}
    aborted = None
    try:
        for block in range(1, args.blocks + 1):
            order = list(CONDITIONS)
            rng.shuffle(order)
            orders[block] = order
            print(f"\n--- Blocco {block}/{args.blocks}: ordine "
                  f"{' -> '.join(order)} ---")
            for pos, cond in enumerate(order, 1):
                if pos > 1:
                    time.sleep(args.settle_s)
                row = _run_trial(cond, args, ctx)
                row["block"] = block
                row["order_in_block"] = pos
                rows.append(row)
                print(f"  [{pos}/3] {LABEL[cond]:<28} "
                      f"dt={row['dt_s']:.2f}s | "
                      f"E_attiva={row['active_energy_raw_j']:+.2f}J | "
                      f"d_ollama={row['d_ollama_cpu_s']:.3f}s | "
                      f"d_busy={row['d_busy_cpu_s']:.3f}s | "
                      f"share={row['cpu_time_share_raw'] if row['cpu_time_share_raw'] is not None else float('nan'):.4f} | "
                      f"E_worker={row['ollama_active_energy_j']:.2f}J | "
                      f"req={row['n_requests']}"
                      + (f" | anomalia={row['share_anomaly']}"
                         if row["share_anomaly"] else "")
                      + (" | WORKER PERSO" if row["worker_exit_in_window"] else "")
                      + ("" if row["active_valid"] else " | active_valid=False"))
    except KeyboardInterrupt:
        aborted = "interrotto dall'utente"
        print("\nInterrotto dall'utente: i blocchi completati restano nei file.")
    except Exception as exc:  # noqa: BLE001 - fermarsi, ma non perdere le righe
        aborted = f"{type(exc).__name__}: {exc}"
        print(f"\nRUN FERMATO al blocco {len(orders)}: {aborted}. "
              "Le prove completate vengono comunque scritte.")
    finally:
        print("\nBaseline POST: 3 finestre da 30 s a riposo (diagnostica, "
              "NON applicata).")
        try:
            p_post = SESSION.calibrate_idle()
            reps_post = list(getattr(SESSION, "_idle_reps", []) or [])
        except Exception as exc:  # noqa: BLE001
            p_post, reps_post = None, []
            print(f"AVVISO: calibrazione POST fallita: {type(exc).__name__}: {exc}")
        SESSION.idle_power_w = p_pre
        if not was_running:
            SESSION.stop()

    print(f"P_post = {'n/d' if p_post is None else f'{p_post:.3f} W'} "
          f"(mediana di {[round(x, 3) for x in reps_post]}); P_pre resta la "
          f"baseline applicata.")

    summary = _summarize(rows)
    _print_summary(rows, summary)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "experiment_results"
    out_dir.mkdir(exist_ok=True)
    csv_path = out_dir / f"additivity_{ts}.csv"
    json_path = out_dir / f"additivity_{ts}.json"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "args": vars(args),
            "host": {
                "logical_cores": psutil.cpu_count(logical=True),
                "physical_cores": psutil.cpu_count(logical=False),
                "source_method": "emi-counter",
                "cpu_time_resolution_s": res_s,
            },
            "baseline": {
                "p_pre_w": p_pre, "reps_pre_w": reps_pre,
                "p_post_w": p_post, "reps_post_w": reps_post,
                "applied": "pre",
            },
            "orders": orders,
            "aborted": aborted,
            "keep_alive_sent": (config.OLLAMA_KEEP_ALIVE
                                or "non inviato (default Ollama)"),
            "rows": rows,
            "summary": summary,
        }, fh, ensure_ascii=False, indent=2)

    print(f"\nCSV:  {csv_path}")
    print(f"JSON: {json_path}")
    if aborted:
        print(f"Run NON completo: {aborted}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
