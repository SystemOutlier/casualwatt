#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
experiment_validate_lhm.py — v3
===============================

Esperimento controllato per validare la misura energetica LHM di CasualWatt
su Windows (power-integration sul sensore 'CPU Package').

Design v2 (mantenuto): diagnostica PI, num_predict fisso, cool-down,
A-B-A (BASE_A -> LOAD -> COOLDOWN -> BASE_B, P_base = media delle due),
metrica primaria J/token.

Cambi v3 (dalla run v2 20261022_001626, ONLY two knobs):
  A. CARICO PIU' LUNGO: n_inferences_per_run 5 -> 15. Scomposizione v2:
     E_inc = (P_load - P_base_avg) * dt_load con segnale ~4,4 W e incertezza
     ~1,1 W sulla baseline -> CV(E_inc) ~ 1,1/4,4 = 25%, esattamente quella
     osservata. Allungando il carico il segnale cresce piu' velocemente
     dell'errore medio della baseline (che scala ~1/sqrt(n finestre));
     CV attesa ~10-12%.
  B. PIU' RIPETIZIONI: n_runs 5 -> 8. IC95 si restringe ~1,6x a parita' di CV
     (t critico 2,262 -> 2,365~invariato ma SE /sqrt(8)).
  Invariati perche' NON collo di bottiglia v2: P_load era gia' stabile
  (CV 1,18%), il token counting non e' piu' la causa della varianza
  (run 465 tok -> 169,6 J vs 466 tok -> 204,4 J: il gap e' nella baseline).
  exact-counter: irraggiungibile per costruzione su questa macchina
  (intervallo PI misurato 0,28-0,32 s > tolerance 0,1 s di
  pi_window_energy_j); contatore NON toccato ("keep current until proven").
  Duration stimata: ~25-30 min (carico ~105 s/run + 2x30 s baseline
  + 15 s cooldown, x8) + calibrazione idle se assente.

Requisiti (invariati):
  - processo ELEVATO (UAC Admin): i sensori Power LHM restano invisibili
    senza elevazione (diagnostics.py: Energy=0, Power=0)
  - Ollama attivo su localhost:11434, modello gia' scaricato
  - interprete: C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe
    (launcher `py` rotto: stub WindowsApps)
"""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import psutil
import requests

# ---- Import CasualWatt ------------------------------------------------------
# NB: l'app viene eseguita con cwEnergyModular/ come radice (config.py,
# energy/ sono moduli top-level). Dobbiamo replicare QUELLO sys.path, altrimenti
# energy_session non importa config e il probe LHM fallisce (ModuleNotFoundError).
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))
from energy.energy_session import SESSION  # noqa: E402


# =============================================================================
# CONFIGURAZIONE
# =============================================================================

@dataclass
class ExperimentConfig:
    model: str = "llama3.2:3b"
    prompt: str = "Spiega la fotosintesi in 50 parole."
    num_predict: int = 128                   # token in output BLOCCATI (v2)
    n_inferences_per_run: int = 15           # v3 A: 5 -> 15 (segnale/baseline ~3x)
    n_runs: int = 8                          # v3 B: 5 -> 8 (IC95 ~1,6x piu' stretto)
    warmup_inferences: int = 3
    baseline_window_s: float = 30.0          # durata fissa BASE_A e BASE_B (v2)
    cooldown_s: float = 15.0                 # pausa post-carico prima di BASE_B (v2)
    ollama_host: str = "http://localhost:11434"
    output_dir: Path = Path("experiment_results")


def load_config() -> ExperimentConfig:
    import os
    c = ExperimentConfig()
    if os.getenv("CW_EXP_MODEL"):
        c.model = os.environ["CW_EXP_MODEL"]
    if os.getenv("CW_EXP_PROMPT"):
        c.prompt = os.environ["CW_EXP_PROMPT"]
    if os.getenv("CW_EXP_RUNS"):
        c.n_runs = int(os.environ["CW_EXP_RUNS"])
    if os.getenv("CW_EXP_INF"):
        c.n_inferences_per_run = int(os.environ["CW_EXP_INF"])
    if os.getenv("CW_EXP_NUMPREDICT"):
        c.num_predict = int(os.environ["CW_EXP_NUMPREDICT"])
    if os.getenv("CW_EXP_BASELINE_S"):
        c.baseline_window_s = float(os.environ["CW_EXP_BASELINE_S"])
    if os.getenv("CW_EXP_COOLDOWN_S"):
        c.cooldown_s = float(os.environ["CW_EXP_COOLDOWN_S"])
    return c


# =============================================================================
# OLLAMA + PROCESSO
# =============================================================================

def ollama_generate(config: ExperimentConfig) -> Tuple[dict, float]:
    """Una generazione con num_predict bloccato; ritorna (json, durata_s)."""
    url = f"{config.ollama_host}/api/generate"
    payload = {
        "model": config.model,
        "prompt": config.prompt,
        "stream": False,
        "options": {"num_predict": config.num_predict},
    }
    t0 = time.monotonic()
    resp = requests.post(url, json=payload, timeout=180)
    dt = time.monotonic() - t0
    resp.raise_for_status()
    return resp.json(), dt


def get_ollama_pids() -> List[int]:
    pids = []
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if p.info["name"] and p.info["name"].lower() in (
                    "ollama.exe", "ollama_llama_server.exe"):
                pids.append(p.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return pids


# =============================================================================
# LETTURA ENERGIA + DIAGNOSTICA PI (v2 #1)
# =============================================================================

def read_method() -> str:
    return SESSION.source_method


def pi_diagnostics() -> dict:
    """Intervallo REALE dei campioni del thread power-integration.

    Misurato sull'effettivo buffer (t, W) con lo stesso lock del thread:
    se hw.Update() e' piu' lento del POWER_SAMPLE_INTERVAL_S dichiarato
    (0.05 s), l'ultimo campione e' sempre piu' vecchio della tolerance di
    0.1 s di pi_window_energy_j -> l'exact-counter decade a fallback.
    """
    src = SESSION._source
    out = {"sensor": getattr(src, "_pi_sensor_name", None),
           "declared_interval_s": getattr(src, "POWER_SAMPLE_INTERVAL_S", None),
           "n_samples": 0, "measured_interval_s": None}
    try:
        with src._pi_lock:
            buf = list(src._pi_samples)
        out["n_samples"] = len(buf)
        tail = buf[-21:]
        if len(tail) >= 2:
            span = tail[-1][0] - tail[0][0]
            if span > 0:
                out["measured_interval_s"] = round(span / (len(tail) - 1), 4)
    except Exception:
        pass
    return out


def window_energy_j(t_start: float, t_end: float,
                    counter_before: Optional[float],
                    counter_after: Optional[float]) -> Tuple[Optional[float], str]:
    """Energia package [J] sulla finestra [t_start, t_end].

    Primario: EnergySession.package_energy_exact_between (percorso B1 del
    profiler). Fallback dichiarato: delta del contatore cumulato letto ai
    bordi del blocco.
    """
    e = None
    try:
        e = SESSION.package_energy_exact_between(t_start, t_end)
    except Exception:
        e = None
    if e is not None and e >= 0.0:
        return float(e), "exact-counter"
    if counter_before is not None and counter_after is not None \
            and counter_after >= counter_before:
        return float(counter_after - counter_before), "counter-delta-fallback"
    return None, "unavailable"


def read_counter_j() -> Optional[float]:
    try:
        return SESSION._source.read_power_j()
    except Exception:
        return None


@dataclass
class PhaseResult:
    energy_j: Optional[float]
    dt_s: float
    wsrc: str
    pi: dict


def measure_window(seconds: float, label: str) -> PhaseResult:
    """Misura una finestra di durata `seconds` SENZA generare carico."""
    pi_before = pi_diagnostics()
    c0 = read_counter_j()
    t0 = time.monotonic()
    print(f"[{label}] {seconds:.1f} s a riposo…")
    time.sleep(seconds)
    t1 = time.monotonic()
    c1 = read_counter_j()
    pi_after = pi_diagnostics()
    e, wsrc = window_energy_j(t0, t1, c0, c1)
    dt = t1 - t0
    if e is None:
        raise SystemExit(
            f"[ERRORE] nessuna lettura energetica nella finestra {label} "
            f"(metodo={read_method()}); intervallo campioni PI: "
            f"{pi_after.get('measured_interval_s')}"
        )
    print(f"  {label}: E={e:.2f} J  dt={dt:.2f} s  P={e / dt:.2f} W  ({wsrc})")
    return PhaseResult(max(e, 0.0), dt, wsrc, {**pi_after,
                                               "samples_during": pi_after["n_samples"] - pi_before["n_samples"]})


# =============================================================================
# RECORD
# =============================================================================

@dataclass
class RunRecord:
    run_id: int
    phase: str                    # base_a | load | base_b
    method: str
    energy_j: float
    dt_s: float
    power_w: float
    tokens_in: int = 0
    tokens_out: int = 0
    pids: str = ""
    window_source: str = ""
    pi_measured_interval_s: Optional[float] = None
    e_inc_j: Optional[float] = None       # solo sul rigo load (A-B-A)
    j_per_token: Optional[float] = None   # solo sul rigo load


# =============================================================================
# ESPERIMENTO
# =============================================================================

def calibrate_idle_if_needed(min_duration_s: float = 30.0) -> None:
    if SESSION.idle_power_w is None:
        print(f"[INFO] P_idle non calibrato. Calibrazione idle "
              f"({min_duration_s:.0f} s x 3 finestre, mediana)…")
        SESSION.on_progress = lambda msg: print(f"    .. {msg}")
        p_idle = SESSION.calibrate_idle(seconds=min_duration_s)
        print(f"[OK] P_idle calibrato: {p_idle:.2f} W "
              f"(provenienza: {SESSION.idle_provenance})")


def run_experiment(config: ExperimentConfig) -> List[RunRecord]:
    records: List[RunRecord] = []

    SESSION.start()
    print(f"[INFO] Sessione avviata. Metodo: {read_method()}")
    pi0 = pi_diagnostics()
    print(f"[INFO] PI: sensore='{pi0['sensor']}' "
          f"intervallo dichiarato={pi0['declared_interval_s']} s "
          f"intervallo misurato={pi0['measured_interval_s']} s "
          f"campioni={pi0['n_samples']}")

    if read_method() not in ("power-integration", "librehardwaremonitor-energy",
                             "rapl"):
        raise SystemExit(
            f"[ERRORE] nessun backend energetico reale (metodo="
            f"'{read_method()}'). Windows: riesegui da terminale ELEVATO (i "
            "sensori Power/Energy LHM sono invisibili senza UAC Admin). "
            "Linux: /sys/class/powercap/intel-rapl/ deve essere leggibile "
            "(sudo, oppure udev rule gruppo 'power'); NOTA: una VM NON "
            "espone contatori RAPL fisici -> ambiente non valido."
        )

    calibrate_idle_if_needed()

    print(f"\n[INFO] Warm-up: {config.warmup_inferences} inferenze "
          f"(num_predict={config.num_predict}, non misurate)…")
    for i in range(config.warmup_inferences):
        _, dt = ollama_generate(config)
        print(f"  warm-up {i + 1}/{config.warmup_inferences}: {dt:.2f} s")

    for run in range(1, config.n_runs + 1):
        print(f"\n{'=' * 66}\nRUN {run}/{config.n_runs}  "
              f"[BASE_A {config.baseline_window_s:.0f}s -> LOAD "
              f"{config.n_inferences_per_run}x{config.num_predict}tok -> "
              f"COOLDOWN {config.cooldown_s:.0f}s -> BASE_B "
              f"{config.baseline_window_s:.0f}s]\n{'=' * 66}")
        method = read_method()

        # ---- BASE_A -----------------------------------------------------
        base_a = measure_window(config.baseline_window_s, "BASE_A")
        records.append(RunRecord(run, "base_a", method, round(base_a.energy_j, 6),
                                 round(base_a.dt_s, 3),
                                 round(base_a.energy_j / base_a.dt_s, 4),
                                 window_source=base_a.wsrc,
                                 pi_measured_interval_s=base_a.pi["measured_interval_s"]))

        # ---- LOAD -------------------------------------------------------
        print(f"[LOAD] {config.n_inferences_per_run} inferenze "
              f"(num_predict={config.num_predict})…")
        pids = set(get_ollama_pids())
        tok_in = tok_out = 0
        c0 = read_counter_j()
        t0 = time.monotonic()
        for _ in range(config.n_inferences_per_run):
            data, _ = ollama_generate(config)
            tok_in += data.get("prompt_eval_count", 0)
            tok_out += data.get("eval_count", 0)
            pids |= set(get_ollama_pids())
        t1 = time.monotonic()
        c1 = read_counter_j()
        e_load, wsrc_load = window_energy_j(t0, t1, c0, c1)
        if e_load is None:
            raise SystemExit(
                f"[ERRORE] nessuna lettura energetica nella finestra LOAD "
                f"(metodo={method}); intervallo PI: "
                f"{pi_diagnostics().get('measured_interval_s')}"
            )
        load = PhaseResult(max(e_load, 0.0), t1 - t0, wsrc_load, pi_diagnostics())
        p_load = load.energy_j / load.dt_s
        print(f"  LOAD: E={load.energy_j:.2f} J  dt={load.dt_s:.2f} s  "
              f"P={p_load:.2f} W  tok={tok_in}+{tok_out}  ({load.wsrc})")

        # ---- COOLDOWN + BASE_B ------------------------------------------
        print(f"[COOLDOWN] {config.cooldown_s:.0f} s (spin worker Ollama)…")
        time.sleep(config.cooldown_s)
        base_b = measure_window(config.baseline_window_s, "BASE_B")

        # ---- A-B-A: potenza idle = media delle due baseline -------------
        p_base_avg = ((base_a.energy_j / base_a.dt_s)
                      + (base_b.energy_j / base_b.dt_s)) / 2.0
        e_inc = max(load.energy_j - p_base_avg * load.dt_s, 0.0)
        jpt = (e_inc / tok_out) if tok_out > 0 else None
        print(f"  [A-B-A] P_base_avg={p_base_avg:.2f} W  "
              f"E_inc={e_inc:.2f} J  J/token="
              + (f"{jpt:.4f}" if jpt is not None else "n/d"))

        records.append(RunRecord(run, "load", method, round(load.energy_j, 6),
                                 round(load.dt_s, 3), round(p_load, 4),
                                 tok_in, tok_out,
                                 ",".join(str(p) for p in sorted(pids)),
                                 load.wsrc, load.pi.get("measured_interval_s"),
                                 round(e_inc, 6),
                                 round(jpt, 6) if jpt is not None else None))
        records.append(RunRecord(run, "base_b", method, round(base_b.energy_j, 6),
                                 round(base_b.dt_s, 3),
                                 round(base_b.energy_j / base_b.dt_s, 4),
                                 window_source=base_b.wsrc,
                                 pi_measured_interval_s=base_b.pi["measured_interval_s"]))

    SESSION.stop()
    return records


# =============================================================================
# STATISTICHE
# =============================================================================

@dataclass
class Stats:
    method: str
    n_runs: int
    p_base_mean_w: float
    p_base_cv_pct: float
    p_idle_calibrated_w: Optional[float]
    p_load_mean_w: float
    p_load_cv_pct: float
    e_inc_mean_j: float
    e_inc_cv_pct: float
    e_inc_ci95_j: Tuple[float, float]
    j_token_mean: Optional[float]
    j_token_cv_pct: Optional[float]
    j_token_ci95: Optional[Tuple[float, float]]
    tok_out_mean: Optional[float]
    window_sources: Dict[str, int]
    pi_interval_measured_s: Optional[float]
    pi_interval_declared_s: Optional[float]


def _mean_cv(vals: List[float]) -> Tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    m = statistics.mean(vals)
    cv = (statistics.stdev(vals) / m * 100.0) if len(vals) > 1 and m else 0.0
    return m, cv


def _ci95(vals: List[float]) -> Tuple[float, float]:
    if not vals:
        return (0.0, 0.0)
    if len(vals) < 3:
        m = statistics.mean(vals)
        return (m, m)
    m = statistics.mean(vals)
    se = statistics.stdev(vals) / (len(vals) ** 0.5)
    t = {3: 4.178, 4: 3.182}.get(len(vals), 2.262) if len(vals) < 10 else 1.96
    return (m - t * se, m + t * se)


def compute_stats(records: List[RunRecord], config: ExperimentConfig) -> Optional[Stats]:
    loads = [r for r in records if r.phase == "load"]
    if not loads:
        return None
    by_run: Dict[int, Dict[str, RunRecord]] = {}
    for r in records:
        by_run.setdefault(r.run_id, {})
        key = "base_a" if r.phase == "base_a" else ("base_b" if r.phase == "base_b" else "load")
        by_run[r.run_id][key] = r

    p_loads, e_incs, jpts, toks = [], [], [], []
    wsources: Dict[str, int] = {}
    pi_ivs = []
    for run_id, ph in by_run.items():
        if "load" not in ph:
            continue
        wsources[ph["load"].window_source] = wsources.get(ph["load"].window_source, 0) + 1
        if ph["load"].pi_measured_interval_s:
            pi_ivs.append(ph["load"].pi_measured_interval_s)
        p_loads.append(ph["load"].power_w)
        if ph["load"].e_inc_j is not None:
            e_incs.append(ph["load"].e_inc_j)
        if ph["load"].j_per_token is not None:
            jpts.append(ph["load"].j_per_token)
        toks.append(ph["load"].tokens_out)
        for k in ("base_a", "base_b"):
            if k in ph:
                wsources[ph[k].window_source] = wsources.get(ph[k].window_source, 0) + 1

    p_base_mean, p_base_cv = _mean_cv([r.power_w for r in records
                                       if r.phase in ("base_a", "base_b")])
    p_load_mean, p_load_cv = _mean_cv(p_loads)
    e_inc_mean, e_inc_cv = _mean_cv(e_incs)
    j_mean, j_cv = _mean_cv(jpts)
    src = SESSION._source
    return Stats(
        method=loads[0].method,
        n_runs=len(loads),
        p_base_mean_w=round(p_base_mean, 4),
        p_base_cv_pct=round(p_base_cv, 2),
        p_idle_calibrated_w=SESSION.idle_power_w,
        p_load_mean_w=round(p_load_mean, 4),
        p_load_cv_pct=round(p_load_cv, 2),
        e_inc_mean_j=round(e_inc_mean, 4),
        e_inc_cv_pct=round(e_inc_cv, 2),
        e_inc_ci95_j=tuple(round(x, 4) for x in _ci95(e_incs)),
        j_token_mean=round(j_mean, 6) if jpts else None,
        j_token_cv_pct=round(j_cv, 2) if len(jpts) > 2 else None,
        j_token_ci95=tuple(round(x, 6) for x in _ci95(jpts)) if jpts else None,
        tok_out_mean=round(statistics.mean(toks), 1) if toks else None,
        window_sources=wsources,
        pi_interval_measured_s=round(statistics.mean(pi_ivs), 4) if pi_ivs else None,
        pi_interval_declared_s=getattr(src, "POWER_SAMPLE_INTERVAL_S", None),
    )


# =============================================================================
# OUTPUT
# =============================================================================

CSV_COLS = ["run_id", "phase", "method", "energy_j", "dt_s", "power_w",
            "tokens_in", "tokens_out", "pids", "window_source",
            "pi_measured_interval_s", "e_inc_j", "j_per_token"]


def save_csv(records: List[RunRecord], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CSV_COLS)
        for r in records:
            w.writerow([r.run_id, r.phase, r.method, r.energy_j, r.dt_s,
                        r.power_w, r.tokens_in, r.tokens_out, r.pids,
                        r.window_source, r.pi_measured_interval_s,
                        r.e_inc_j, r.j_per_token])
    print(f"[OK] CSV: {out_path}")


def save_json(stats: Optional[Stats], out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(asdict(stats) if stats else {}, f, indent=2, ensure_ascii=False)
    print(f"[OK] JSON: {out_path}")


def generate_report(config: ExperimentConfig, records: List[RunRecord],
                    stats: Optional[Stats], out_path: Path):
    L: List[str] = []
    L.append("# Validazione LHM — Esperimento v3 (A-B-A, carico lungo 15x128)")
    L.append("")
    L.append(f"**Data**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    L.append(f"**Modello**: `{config.model}` | **Prompt**: `{config.prompt}`  ")
    L.append(f"**num_predict**: {config.num_predict} | **inferenze/run**: "
             f"{config.n_inferences_per_run} | **run**: {config.n_runs}  ")
    L.append(f"**Baseline**: {config.baseline_window_s:.0f} s x2 (A-B-A) | "
             f"**Cool-down**: {config.cooldown_s:.0f} s")
    L.append("")
    L.append("## Per-run")
    L.append("")
    L.append("| run | E_load [J] | P_load [W] | P_baseA [W] | P_baseB [W] | "
             "E_inc [J] | tok_out | J/token | wsrc |")
    L.append("|-----|-----------|-----------|-------------|-------------|"
             "--------|---------|---------|------|")
    by_run: Dict[int, Dict[str, RunRecord]] = {}
    for r in records:
        by_run.setdefault(r.run_id, {})[r.phase] = r
    for run_id in sorted(by_run):
        ph = by_run[run_id]
        ld = ph.get("load")
        if not ld:
            continue
        a = ph.get("base_a")
        b = ph.get("base_b")
        L.append(f"| {run_id} | {ld.energy_j:.1f} | {ld.power_w:.2f} | "
                 + (f"{a.power_w:.2f}" if a else "-") + " | "
                 + (f"{b.power_w:.2f}" if b else "-") + " | "
                 + (f"{ld.e_inc_j:.1f}" if ld.e_inc_j is not None else "-") + " | "
                 + f"{ld.tokens_out} | "
                 + (f"{ld.j_per_token:.4f}" if ld.j_per_token is not None else "-")
                 + f" | {ld.window_source} |")
    L.append("")
    if stats:
        L.append("## Statistiche")
        L.append("")
        L.append(f"- Metodo attivo: `{stats.method}`")
        L.append(f"- P_base (A-B-A, media): **{stats.p_base_mean_w:.2f} W** "
                 f"(CV {stats.p_base_cv_pct:.1f}%) — cross-check P_idle calibrato: "
                 f"{stats.p_idle_calibrated_w} W")
        L.append(f"- P_load media: {stats.p_load_mean_w:.2f} W "
                 f"(CV {stats.p_load_cv_pct:.1f}%)")
        L.append(f"- **E_inc medio (A-B-A)**: {stats.e_inc_mean_j:.2f} J "
                 f"(CV {stats.e_inc_cv_pct:.1f}%), IC95% "
                 f"[{stats.e_inc_ci95_j[0]:.2f}, {stats.e_inc_ci95_j[1]:.2f}] J")
        if stats.j_token_mean is not None:
            L.append(f"- **METRICA PRIMARIA J/token**: {stats.j_token_mean:.4f} "
                     f"(CV {stats.j_token_cv_pct}%), IC95% "
                     f"[{stats.j_token_ci95[0]:.4f}, {stats.j_token_ci95[1]:.4f}] "
                     f"su tok_out medio {stats.tok_out_mean}")
        L.append(f"- Letture finestra: {stats.window_sources}")
        L.append(f"- Intervallo campioni PI: dichiarato "
                 f"{stats.pi_interval_declared_s} s, **misurato "
                 f"{stats.pi_interval_measured_s} s**")
        L.append("")
        L.append("## Limiti dichiarati")
        L.append("")
        L.append("1. La misura copre il **dominio package CPU** (contatore "
                 "firmware via LHM), non il solo processo Ollama: l'attribuzione "
                 "avviene a valle con cpu-time-share nel profiler CasualWatt.")
        L.append("2. Confronto LHM-vs-lettura-nativa dello stesso contatore "
                 "**non e' validazione indipendente** (stesso sensore). "
                 "Riferimento distinto: RAPL/turbostat su Linux (dual-backend).")
        L.append("3. P_base A-B-A cattura il sistema con modello Ollama "
                 "residente: la baseline e' 'warm idle', condizione coerente "
                 "col benchmark ma da dichiarare.")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(L), encoding="utf-8")
    print(f"[OK] Report: {out_path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    config = load_config()
    print("=" * 66)
    print("ESPERIMENTO VALIDAZIONE LHM v3 — CasualWatt (A-B-A, carico lungo)")
    print("=" * 66)
    print(f"Modello: {config.model} | num_predict: {config.num_predict}")
    print(f"Run: {config.n_runs} x ({config.n_inferences_per_run} inferenze)")
    print(f"Baseline: {config.baseline_window_s:.0f}s x2 | cooldown "
          f"{config.cooldown_s:.0f}s | output: {config.output_dir}")
    print("=" * 66)

    try:
        requests.get(f"{config.ollama_host}/api/tags", timeout=5).raise_for_status()
    except Exception as e:
        print(f"[ERRORE] Ollama non raggiungibile su {config.ollama_host}: {e}")
        sys.exit(1)

    try:
        import ctypes
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("[ERRORE] processo NON elevato: LHM non espone sensori "
                  "Power/Energy. Riapri il terminale come Amministratore.")
            sys.exit(2)
    except AttributeError:
        pass

    records: List[RunRecord] = []
    stats: Optional[Stats] = None
    try:
        records = run_experiment(config)
        stats = compute_stats(records, config)
    finally:
        if records:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            # backend nel nome file: lhm_validation_* (Windows) o
            # rapl_validation_* (Linux) — protocollo e colonne identici.
            tag = "rapl" if (stats and stats.method == "rapl") else "lhm"
            base = config.output_dir / f"{tag}_validation_v3_{ts}"
            save_csv(records, base.with_suffix(".csv"))
            save_json(stats, base.with_suffix(".json"))
            generate_report(config, records, stats, base.with_suffix(".md"))

    if stats:
        print("\n" + "=" * 66)
        print("RISULTATI")
        print("=" * 66)
        print(f"PI intervallo misurato: {stats.pi_interval_measured_s} s "
              f"(dichiarato {stats.pi_interval_declared_s} s)")
        print(f"Letture: {stats.window_sources}")
        print(f"P_base(A-B-A): {stats.p_base_mean_w:.2f} W  "
              f"P_idle calibrato: {stats.p_idle_calibrated_w} W")
        print(f"E_inc medio:   {stats.e_inc_mean_j:.2f} J  (CV {stats.e_inc_cv_pct}%)")
        if stats.j_token_mean is not None:
            print(f"J/token:       {stats.j_token_mean:.4f}  "
                  f"(CV {stats.j_token_cv_pct}%, "
                  f"IC95 [{stats.j_token_ci95[0]:.4f}, {stats.j_token_ci95[1]:.4f}])")


if __name__ == "__main__":
    main()
