#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cpu_share_check.py — quanto CPU-time ha DAVVERO l'albero Ollama durante il load?

Nasce per correggere un artefatto misurato nel run SRUM x EMI v2
(`experiment_results/srum_emi_cross_20261023_130553.json`): la frazione di
CPU-time dichiarata per Ollama era **0,001** perche' il needle era "ollama" e
il processo che lavora e' `llama-server.exe` (non contiene "ollama" nel nome).
Senza quella correzione il confronto con l'attribuzione SRUM (quota
`CPUEnergyConsumption` di ollama/llama-server nel load = 0,7361) non ha senso.

Metodo: nessuna ipotesi sul nome "di chi e' il lavoro" — elenco i processi che
consumano CPU nella finestra, con delta dei secondi CPU, e li raggruppo per
pattern. Il denominatore lo dichiaro in DUE forme, perche' solo una delle due e'
confrontabile con SRUM:

* `share_su_tempo_totale` = CPU-s albero / somma dei delta di TUTTI i processi
  visibili. Il totale conta i core-secondi reali dell'intervallo (nuclei x
  parete), e l'allocatore di Windows li accredita a `System Idle Process`
  (PID 0) quando i core sono liberi: nel run del 13:32 sono 407,27 s su 1212,73,
  cioe' un terzo del denominatore NON e' lavoro.
* `share_su_tempo_busy` = CPU-s albero / secondi busy di sistema (da
  `psutil.cpu_times()`, totale meno idle). E' il numero confrontabile con la
  frazione di SRUM, che attribuisce energia a chi consuma.

Caveat: i processi invisibili (AccessDenied) restano fuori dal denominatore dei
singoli processi ma NON da `cpu_times()`, che e' di sistema: per questo i due
totali differiscono (misurato: 1212,73 s di processi contro 20 nuclei x 61,6 s
= 1232 s attesi).

Uso: Ollama in esecuzione (`ollama serve` o app di sistema), modello gia'
caricabile; nessuna admin necessaria.

  python cpu_share_check.py
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from four_way_test import ollama_generate  # noqa: E402
from srum_emi_cross import NEEDLES, cpu_seconds_of  # noqa: E402

DURATA_S = 60.0
PATTERNS = ("ollama", "llama-server", "python", "qoder", "brave", "hwinfo",
            "service", "system")
SRUM_CONFRONTO = {
    "SRUM_ollama_share_of_cpu_load": 0.7361,
    "fonte": "experiment_results/srum_emi_cross_20261023_130553.json",
    "nota": "quota CPUEnergyConsumption di ollama.exe + ollama app.exe + "
            "llama-server.exe sul totale di CPU nel load: modello EPI di "
            "Windows, NON misura. Stessa macchina, carico identico (richette "
            "num_predict 32, temperature 0).",
}


def snapshot() -> dict:
    """{(pid, nome): secondi CPU} su tutti i processi visibili."""
    import psutil
    out = {}
    for p in psutil.process_iter(["pid", "name", "cpu_times"]):
        try:
            t = p.info["cpu_times"]
            s = float(getattr(t, "user", 0.0) + getattr(t, "system", 0.0))
        except Exception:
            continue
        out[(p.info["pid"], p.info["name"])] = s
    return out


def busy_seconds() -> tuple[float, float]:
    """(secondi busy, secondi idle) aggregati su tutti i core da cpu_times()."""
    import psutil
    ct = psutil.cpu_times()
    idle = float(getattr(ct, "idle", 0.0))
    total = float(sum(getattr(ct, k, 0.0) for k in ct._fields))
    return total - idle, idle


def main() -> int:
    print("Warm-up (fuori misura)...")
    ollama_generate()

    t0 = time.monotonic()
    a_all, sys_all = cpu_seconds_of(NEEDLES)
    a_oll_only, _ = cpu_seconds_of("ollama")
    busy0, idle0 = busy_seconds()
    snap0 = snapshot()
    print(f"--- finestra di load ({DURATA_S:.0f} s, richette Ollama continue) ---")
    tokens = 0
    while time.monotonic() - t0 < DURATA_S:
        try:
            tokens += ollama_generate()
        except Exception as exc:
            print(f"[WARN] ollama: {exc}")
            time.sleep(1.0)
    dt = time.monotonic() - t0
    b_all, sys_b = cpu_seconds_of(NEEDLES)
    b_oll_only, _ = cpu_seconds_of("ollama")
    busy1, idle1 = busy_seconds()
    snap1 = snapshot()

    d_needles = b_all - a_all
    d_ollama_name = b_oll_only - a_oll_only
    d_system = sys_b - sys_all
    d_busy = busy1 - busy0
    d_idle = idle1 - idle0

    per_proc = {}
    for k, v1 in snap1.items():
        v0 = snap0.get(k)
        if v0 is None:
            continue
        d = v1 - v0
        if d > 0.5:
            per_proc[f"{k[1]} ({k[0]})"] = round(d, 2)
    top = sorted(per_proc.items(), key=lambda x: -x[1])[:12]
    idle_proc = sum(v for k, v in per_proc.items() if k.startswith("System Idle"))

    rag = {}
    for pat in PATTERNS:
        s = sum(v for k, v in per_proc.items() if pat in k.lower())
        if s:
            rag[pat] = round(s, 2)

    res = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "finestra_s": round(dt, 1),
        "token": tokens,
        "needles": list(NEEDLES),
        "cpu_s_albero_ollama": round(d_needles, 2),
        "cpu_s_solo_nome_ollama": round(d_ollama_name, 2),
        "cpu_s_sistema_somma_processi": round(d_system, 2),
        "cpu_s_busy_da_cpu_times": round(d_busy, 2),
        "cpu_s_idle_da_cpu_times": round(d_idle, 2),
        "core_secondi_al_secondo_da_somma_processi": round(d_system / dt, 2),
        "nuclei_logici": os.cpu_count(),
        "completitudine_denominatore": round(d_system / (os.cpu_count() * dt), 4),
        "share_ollama_su_tempo_totale": round(d_needles / d_system, 4) if d_system else None,
        "share_ollama_su_tempo_busy": round(d_needles / d_busy, 4) if d_busy else None,
        "share_col_vecchio_needle": round(d_ollama_name / d_system, 4) if d_system else None,
        "confronto_con_SRUM": {
            **SRUM_CONFRONTO,
            "share_busy_misurato": round(d_needles / d_busy, 4) if d_busy else None,
            "delta_assoluto": (round(abs((d_needles / d_busy) - 0.7361), 4)
                               if d_busy else None),
            "verdetto": "confrontabile solo con la quota busy: il tempo totale "
                        "include l'allocatore (System Idle Process) e dava 0,50",
        },
        "raggruppato_per_pattern_s": rag,
        "top_processi_s": top,
        "system_idle_process_s": round(idle_proc, 2),
    }
    print(json.dumps(res, indent=2, ensure_ascii=False))
    out = (ROOT / "experiment_results" /
           f"cpu_share_check_{datetime.datetime.now():%Y%m%d_%H%M%S}.json")
    out.write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
