"""Audit idle di P6.3: la macchina a riposo e' stazionaria?

`protocollo_v4_20261024.md:2407-2416` chiede, **prima** del pilota e della
campagna, "un audit idle di 30 minuti sulla macchina nella configurazione esatta
di misura", con "l'elenco dei processi e le sei finestre da 30 s lette con la
sequenza di P1.5". Se l'audit mostra `pre_range_w > 1,0 W` la campagna non parte
e si dichiara perche': la soglia e' quella congelata di P1.6, non una nuova.

Cosa misura davvero. Le sei finestre sono due gruppi da tre separati da un
settling, cioe' la sequenza pre/post di P1.5 applicata a un blocco che non invia
richieste. I 30 minuti di P6.3 sono l'attesa di quiete che precede la misura, non
una durata delle finestre: senza di essa si misura l'assestamento della macchina
dopo il lavoro di chi l'ha appena usata, che e' esattamente il difetto che
l'audit deve intercettare invece di subire.

Il canale e' quello di produzione (`SESSION._source.read_idle_window_j(30.0)`,
cioe' P1.3), non `calibrate_idle`, che gestirebbe start/stop della sessione.
La baseline vale `mediana(P_rep,1..3)` e il `dP` e' la differenza fra la mediana
del secondo gruppo e quella del primo: il post e' diagnostica, mai applicato
(P1.14).

Le soglie non si spostano: `pre_range_w <= 1,0 W` e' il gate di P6.3/P1.6,
`|dP| <= 1,0 W` e' il filtro dei blocchi di controllo di P4.5
(`protocollo_v4_20261024.md:1540`). L'esito e' un fatto registrato nell'artefatto,
non una dichiarazione: chi legge vede le sei potenze e rifa' il conto.

Uso:
    python tools/audit_idle_p63.py                    # 30 min di quiete + 6 finestre
    python tools/audit_idle_p63.py --quiescenza-min 0 # solo le finestre (collaudo)
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import psutil
except ImportError:  # pragma: no cover - psutil e' una dipendenza di produzione
    psutil = None

MODULE_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = MODULE_DIR.parent
# Eseguito come `py tools/audit_idle_p63.py` Python mette in sys.path la
# cartella dello script, non il modulo: `energy` sarebbe irraggiungibile.
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))
DEFAULT_OUT = REPO_ROOT / "experiment_results" / "p6_3_audit_idle_20261107.json"

WINDOW_S = 30.0
N_WINDOWS_PER_GROUP = 3
SETTLE_WINDOW_S = 10.0
SETTLE_TOLERANCE_W = 0.5
SETTLE_TIMEOUT_S = 120.0
P_REP_MIN_S = 30.0

# Soglie congelate. Nessuna si sposta dopo aver visto il risultato.
GATE_PRE_RANGE_W = 1.0
GATE_DP_W = 1.0
BACKGROUND_CPU_PCT = 5.0

# Procsi di monitoraggio che P6.3 chiede chiusi: se ci sono, la regola e'
# "GUI di monitoraggio chiuse" e il costo dell'osservatore e' 0,2-0,9 W,
# confondibile con il drift (observer_cost_20261023_analisi.md, §2).
MONITORING_HINTS = (
    "librehardwaremonitor", "hwinfo", "gpu-z", "gpuz", "hwmonitor",
    "openhardwaremonitor", "throttlestop", "aida64",
)
OLLAMA_HINTS = ("ollama", "llama-server")


def _proc_name(proc: "psutil.Process") -> str:
    try:
        return (proc.name() or "").lower()
    except Exception:
        return ""


def _snapshot() -> dict:
    """Configurazione della macchina al momento dell'audit (P1.4, P6.3)."""
    out: dict = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        out["elevated"] = bool(
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "([Security.Principal.WindowsPrincipal]"
                 "[Security.Principal.WindowsIdentity]::GetCurrent())"
                 ".IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)"],
                capture_output=True, text=True, timeout=30,
            ).stdout.strip().lower().startswith("true")
        )
    except Exception as exc:
        out["elevated"] = None
        out["elevated_error"] = f"{type(exc).__name__}: {exc}"
    try:
        out["power_plan"] = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True, text=True, timeout=30,
        ).stdout.strip()
    except Exception as exc:
        out["power_plan"] = f"non letto ({type(exc).__name__}: {exc})"

    if psutil is None:
        return out

    try:
        batt = psutil.sensors_battery()
        out["battery"] = None if batt is None else {
            "percent": round(float(batt.percent), 1),
            "plugged": bool(batt.power_plugged),
        }
    except Exception:
        out["battery"] = "non letto"

    procs = []
    monitors = []
    ollama = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        name = _proc_name(p)
        if not name:
            continue
        if any(h in name for h in MONITORING_HINTS):
            monitors.append({"pid": p.info["pid"], "name": p.info["name"]})
        if any(h in name for h in OLLAMA_HINTS):
            ollama.append({"pid": p.info["pid"], "name": p.info["name"]})
        mem = p.info.get("memory_info")
        rss = getattr(mem, "rss", 0) if mem is not None else 0
        procs.append((rss, p.info["pid"], p.info["name"]))
    procs.sort(reverse=True)
    out["monitoring_processes"] = monitors
    out["ollama_processes"] = ollama
    out["top_by_rss"] = [
        {"pid": pid, "name": nm, "rss_mb": round(rss / 1e6, 1)}
        for rss, pid, nm in procs[:10]
    ]
    return out


def _quiescenza(durata_s: float, step_s: float = 5.0) -> dict:
    """Attende ``durata_s`` campionando la CPU: la macchina e' ferma?

    Registra ogni campione: un massimo alto in mezzo all'attesa non si cancella
    con la media, ed e' quello che conta per la soglia del 5% di P1.4.
    """
    if psutil is None or durata_s <= 0:
        return {"skipped": True, "reason": "psutil assente o durata zero"}
    campioni = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < durata_s:
        campioni.append(round(float(psutil.cpu_percent(interval=min(step_s, 1.0))), 2))
        resto = durata_s - (time.monotonic() - t0)
        if resto > 0:
            time.sleep(min(step_s, 1.0) if resto < 1.0 else 0.0)
    consec = massimo_consec = 0
    for c in campioni:
        if c > BACKGROUND_CPU_PCT:
            consec += 1
            massimo_consec = max(massimo_consec, consec)
        else:
            consec = 0
    return {
        "duration_s": round(time.monotonic() - t0, 1),
        "n_samples": len(campioni),
        "cpu_pct_min": min(campioni) if campioni else None,
        "cpu_pct_median": round(statistics.median(campioni), 2) if campioni else None,
        "cpu_pct_max": max(campioni) if campioni else None,
        "samples_over_threshold": sum(1 for c in campioni if c > BACKGROUND_CPU_PCT),
        "max_consecutive_over_threshold": massimo_consec,
        "background_load": massimo_consec >= 3,
        "threshold_pct": BACKGROUND_CPU_PCT,
    }


def _gruppo(src, etichetta: str) -> dict:
    """Settling di P1.5 e tre finestre di 30 s consecutive."""
    t0 = time.monotonic()
    settle = src_settle(etichetta)
    t_settle = time.monotonic() - t0
    finestre = []
    for _ in range(N_WINDOWS_PER_GROUP):
        r = src.read_idle_window_j(WINDOW_S)
        if r is None:
            finestre.append({"error": "contatore assente"})
            continue
        de, dt, modo = r
        finestre.append({
            "delta_j": round(float(de), 6),
            "dt_s": round(float(dt), 6),
            "power_w": round(float(de) / float(dt), 6),
            "method": modo,
        })
    potenze = [f["power_w"] for f in finestre if "power_w" in f]
    return {
        "group": etichetta,
        "settle_s": round(t_settle, 1),
        "settle_converged": settle is not None,
        "windows": finestre,
        "n_valid": len(potenze),
        "median_w": round(statistics.median(potenze), 6) if potenze else None,
        "range_w": round(max(potenze) - min(potenze), 6) if potenze else None,
    }


def src_settle(etichetta: str):
    from energy.energy_session import SESSION

    return SESSION.settle_idle(
        window_s=SETTLE_WINDOW_S,
        tolerance_w=SETTLE_TOLERANCE_W,
        timeout_s=SETTLE_TIMEOUT_S,
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quiescenza-min", type=float, default=30.0,
                    help="attesa di quiete che precede le finestre (P6.3: 30 min)")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--nota", action="append", default=[],
                    help="dichiarazione da registrare nell'artefatto (ripetibile): "
                         "cosa e' stato chiuso o sospeso prima della misura")
    args = ap.parse_args(argv)

    from energy.energy_session import SESSION

    src = SESSION._source
    report: dict = {
        "audit": "P6.3",
        "source": "protocollo_v4_20261024.md:2407-2416",
        "thresholds": {
            "pre_range_w_max": GATE_PRE_RANGE_W,
            "abs_dp_w_max": GATE_DP_W,
            "settle_tolerance_w": SETTLE_TOLERANCE_W,
            "settle_timeout_s": SETTLE_TIMEOUT_S,
            "window_s": WINDOW_S,
            "windows_per_group": N_WINDOWS_PER_GROUP,
        },
        "channel": getattr(src, "method", "unknown"),
        "note": list(args.nota),
        "snapshot": _snapshot(),
        "quiescence": _quiescenza(args.quiescenza_min * 60.0),
        "groups": [],
    }

    report["groups"].append(_gruppo(src, "pre"))
    report["groups"].append(_gruppo(src, "post"))

    pre, post = report["groups"]
    potenze = [f["power_w"] for g in (pre, post) for f in g["windows"] if "power_w" in f]
    if pre["n_valid"] == N_WINDOWS_PER_GROUP and post["n_valid"] == N_WINDOWS_PER_GROUP:
        baseline_pre = pre["median_w"]
        baseline_post = post["median_w"]
        dp = round(baseline_post - baseline_pre, 6)
        pre_range = pre["range_w"]
        report["baseline_pre_w"] = baseline_pre
        report["baseline_post_w"] = baseline_post
        report["dP_w"] = dp
        report["pre_range_w"] = pre_range
        report["post_range_w"] = post["range_w"]
        report["gate"] = {
            "pre_range_ok": pre_range <= GATE_PRE_RANGE_W,
            "dp_ok": abs(dp) <= GATE_DP_W,
            "campaign_may_start": (pre_range <= GATE_PRE_RANGE_W and abs(dp) <= GATE_DP_W),
        }
    else:
        report["gate"] = {
            "pre_range_ok": False,
            "dp_ok": False,
            "campaign_may_start": False,
            "reason": "una o piu' finestre non hanno prodotto una potenza",
        }
    report["n_power_values"] = len(potenze)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"canale: {report['channel']} | piano: {report['snapshot'].get('power_plan', '')}")
    q = report["quiescence"]
    if not q.get("skipped"):
        print(f"quiete: {q['duration_s']:.0f} s, CPU mediana {q['cpu_pct_median']}% "
              f"max {q['cpu_pct_max']}% | background_load={q['background_load']}")
    for g in report["groups"]:
        pw = ", ".join(f"{f['power_w']:.3f}" for f in g["windows"] if "power_w" in f)
        print(f"  {g['group']:4s}: settle {g['settle_s']:.0f}s "
              f"(convergenza={g['settle_converged']}) | P_rep = [{pw}] W")
    if "pre_range_w" in report:
        print(f"baseline_pre_w  = {report['baseline_pre_w']:.4f} W")
        print(f"baseline_post_w = {report['baseline_post_w']:.4f} W")
        print(f"pre_range_w     = {report['pre_range_w']:.4f} W  (max {GATE_PRE_RANGE_W})")
        print(f"dP_w            = {report['dP_w']:+.4f} W  (|dP| max {GATE_DP_W})")
    print(f"gate campagna   = {report['gate']}")
    print(f"artefatto: {out}")
    return 0 if report["gate"]["campaign_may_start"] else 1


if __name__ == "__main__":
    sys.exit(main())
