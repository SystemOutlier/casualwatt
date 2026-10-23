"""Sensibilita' di E_inc e J/token al fondo di idle (esperimento 23/10, offline).

Nessun rilancio: prende i due protocolli A-B-A gia' committati e applica la
forma chiusa dell'eq. (3.4) di tesi, cioe'

    E_inc(P_fondo)   = max( E_load - P_fondo * dt_load , 0 )
    J/token(P_fondo) = E_inc(P_fondo) / tok_out

e quindi, finche' il clamp non e' attivo,

    d(J/token)/dP_fondo = - dt_load / tok_out   [J/token per watt]

che e' il reciproco del throughput: sbagliare il fondo di 1 W costa quanto
(dt_load/tok_out) secondi di generazione in piu'. Risponde a RQ2 senza hardware
nuovo, per ogni fondo che il progetto ha davvero calibrato, imposto o misurato.

Terza domanda a cui risponde, che i CSV dei protocolli permettono gia' di
porre: quanta della varianza osservata su J/token e' rumore DEL fondo e quanta
e' rumore della STIMA del fondo (finestra da 30 s x 2 contro un unico numero
dichiarato).

Uso:  python idle_floor_sensitivity.py [--out experiment_results]
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RUNS = {
    "v3-15inferenze": Path("experiment_results/lhm_validation_v3_20261023_153604.csv"),
    "v3-5inferenze": Path("experiment_results/lhm_validation_v3_20261023_160430.csv"),
}

# Fondi che il progetto ha davvero usato o misurato, ciascuno con provenienza:
# - il fondo medio del protocollo stesso (eq. 3.4);
# - 65,0 W: idle_power_w delle 9 righe pubblicate in results/ (manual_override);
# - 66,095 W: fondo "calibrato" del run R20261019-164316-74070d (era °C, pre-fix);
# - 17,087 W: fondo medio dei quattro test EMI v2 (30 richieste x 32 token,
#   summary in Tesi-latex/test-emi/emi-ollama-summary-*.txt);
# - 13,4 W: EMI del four-way del 23/10 alle 12:08.
FONDI = [
    ("fondo_del_protocollo", None),
    ("65.0_manuale_produzione", 65.0),
    ("66.095_pre_fix_come_was_C", 66.095),
    ("17.087_fondo_medio_EMI_4_test", 17.087),
    ("13.4_fondo_EMI_four_way", 13.4),
]


def leggi(csv_path: Path) -> tuple[list[dict], dict]:
    """Ricostruisce i run (E_load, dt, tok_out) e il meta del protocollo."""
    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    run: list[dict] = []
    for r in rows:
        if r["phase"] != "load":
            continue
        base = {
            r2["phase"]: float(r2["power_w"])
            for r2 in rows
            if r2["run_id"] == r["run_id"] and r2["phase"].startswith("base")
        }
        run.append({
            "run_id": r["run_id"],
            "e_load_j": float(r["energy_j"]),
            "dt_load_s": float(r["dt_s"]),
            "tok_out": int(float(r["tokens_out"])),
            "p_load_w": float(r["power_w"]),
            "base_a_w": base.get("base_a"),
            "base_b_w": base.get("base_b"),
            "p_base_w": statistics.mean(v for v in base.values() if v is not None),
        })
    meta = {
        "p_base_media_w": round(statistics.mean(x["p_base_w"] for x in run), 3),
        "p_load_media_w": round(statistics.mean(x["p_load_w"] for x in run), 3),
        "sd_p_base_w": round(statistics.stdev(x["p_base_w"] for x in run), 3),
        "n_run": len(run),
    }
    return run, meta


def con_fondo(r: dict, p_fondo: float) -> dict:
    """La forma chiusa su un run, clamp di eq. (3.4) compreso."""
    lorda = r["e_load_j"] - p_fondo * r["dt_load_s"]
    return {
        "e_inc_j": round(max(lorda, 0.0), 2),
        "lorda_j": round(lorda, 2),
        "clamp_attivo": lorda <= 0.0,
        "j_per_token": (max(lorda, 0.0) / r["tok_out"]) if r["tok_out"] else None,
    }


def aggrega(valori: list[float]) -> dict:
    return {
        "j_token_mean": round(statistics.mean(valori), 4),
        "cv_pct": round(statistics.stdev(valori) / statistics.mean(valori) * 100, 2),
        "n": len(valori),
    }


def analisi(nome: str, run: list[dict], meta: dict) -> dict:
    # (1) sensibilita' al VALORE del fondo, con un'unica costante per tutti i run
    per_fondo = {}
    for etichetta, valore in FONDI:
        p = meta["p_base_media_w"] if valore is None else valore
        celle = [con_fondo(r, p) for r in run]
        azzerati = sum(1 for c in celle if c["clamp_attivo"])
        validi = [c["j_per_token"] for c in celle if not c["clamp_attivo"]]
        per_fondo[etichetta] = {
            "p_fondo_w": round(p, 3),
            "j_token_mean": round(statistics.mean(validi), 4) if validi else None,
            "cv_pct": round(aggrega(validi)["cv_pct"], 2) if len(validi) > 1 else None,
            "run_azzerati_dal_clamp": azzerati,
            "n": len(celle),
        }

    # (2) sensibilita' alla CONVENZIONE sul fondo, run per run
    conv = {}
    for chiave, etichetta in (
        ("p_base_w", "media_A_B_eq34"),
        ("base_a_w", "solo_A"),
        ("base_b_w", "solo_B"),
    ):
        celle = [con_fondo(r, r[chiave]) for r in run]
        validi = [c["j_per_token"] for c in celle if not c["clamp_attivo"]]
        if len(validi) > 1:
            conv[etichetta] = aggrega(validi)
    # (3) il "fondo unico dichiarato": la media del protocollo applicata a tutti
    celle = [con_fondo(r, meta["p_base_media_w"]) for r in run]
    conv["fondo_unico_dichiarato"] = aggrega(
        [c["j_per_token"] for c in celle if not c["clamp_attivo"]]
    )

    pendenze = [r["dt_load_s"] / r["tok_out"] for r in run]
    med = statistics.mean(v["j_token_mean"] for v in conv.values())
    return {
        "protocollo": nome,
        **meta,
        "pendenza_j_tok_per_w": {
            "media": round(-statistics.mean(pendenze), 5),
            "min_max": [round(-max(pendenze), 5), round(-min(pendenze), 5)],
        },
        "cv_predetta_da_rumore_fondo_pct": round(
            meta["sd_p_base_w"] * statistics.mean(pendenze)
            / conv["media_A_B_eq34"]["j_token_mean"] * 100, 2
        ),
        "sensibilita_al_valore_del_fondo": per_fondo,
        "sensibilita_alla_convenzione": conv,
        "scarto_max_convenzioni_pct": round(
            max(abs(v["j_token_mean"] - med) / med * 100 for v in conv.values()), 1
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="experiment_results")
    args = ap.parse_args()
    esiti = {}
    for nome, path in RUNS.items():
        run, meta = leggi(path)
        esiti[nome] = analisi(nome, run, meta)
        print(json.dumps(esiti[nome], indent=2, ensure_ascii=False))
        print()
    out = Path(args.out) / "idle_floor_sensitivity_20261023.json"
    out.write_text(json.dumps(esiti, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[scritto] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
