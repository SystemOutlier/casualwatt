#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_demo_tests_energy.py — Protocollo dimostrativo CasualWatt con misura energetica corretta.

Esegue 3 query x 3 ripetizioni per 3 modelli SLM locali tramite Ollama /api/chat.
Usa il bordo di misura di CasualWatt (read_measurement_edge) e package_energy_exact_between
per ottenere l'energia esatta di ogni richiesta, come nel benchmark v4.

Uso:
  py -3 run_demo_tests_energy.py

Prerequisiti:
  - Ollama attivo su http://127.0.0.1:11434
  - Modelli già scaricati:
      hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest
      llama3.2:1b
      qwen2.5:0.5b
  - Eseguire lo script dalla cartella cwEnergyModular, così l'import di energy funziona.

Output:
  output_demo/demo_results_energy.csv
  output_demo/demo_results_energy.json
"""

import csv
import json
import os
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
CHAT_API = f"{OLLAMA_URL}/api/chat"
TAGS_API = f"{OLLAMA_URL}/api/tags"

MODELS = [
    "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest",
    "llama3.2:1b",
    "qwen2.5:0.5b",
]

QUERIES = [
    {"id": "q1", "type": "number", "prompt": "What is 2 + 2? Answer only with the numeric result.", "expected": "4"},
    {"id": "q2", "type": "short_text", "prompt": "What is the capital of France? Answer only with the city name.", "expected": "Paris"},
    {"id": "q3", "type": "free_text", "prompt": "Explain in one sentence the cause-effect relation between deforestation and CO2 concentration.", "expected": ""},
]

REPEATS = 3
NUM_PREDICT = 128
TEMPERATURE = 0.0
KEEP_ALIVE = -1
OUT_DIR = Path("output_demo")
OUT_DIR.mkdir(exist_ok=True)
CSV_PATH = OUT_DIR / "demo_results_energy.csv"
JSON_PATH = OUT_DIR / "demo_results_energy.json"

try:
    from energy import SESSION  # type: ignore
    HAS_CASUALWATT = True
except Exception as exc:
    HAS_CASUALWATT = False
    SESSION = None
    CASUALWATT_IMPORT_ERROR = str(exc)


def http_json(url: str, payload: dict | None = None, timeout: float = 120.0) -> dict:
    if payload is None:
        req = Request(url, method="GET")
    else:
        data = json.dumps(payload).encode("utf-8")
        req = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_ok() -> bool:
    try:
        http_json(TAGS_API, timeout=5)
        return True
    except Exception:
        return False


def available_models() -> list[str]:
    try:
        data = http_json(TAGS_API, timeout=5)
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    except Exception:
        return []


def warmup(model: str) -> list[dict]:
    rows = []
    for i in range(2):
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "Warm-up request for CasualWatt demonstration."}],
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": TEMPERATURE, "num_predict": 32},
        }
        response = http_json(CHAT_API, payload)
        rows.append({
            "model": model,
            "warmup": i + 1,
            "prompt_tokens": response.get("prompt_eval_count"),
            "output_tokens": response.get("eval_count"),
            "total_duration_s": (response.get("total_duration") or 0) / 1e9,
        })
    return rows


def edge_t(edge: dict) -> float:
    """Estrae il timestamp monotonic dal bordo di misura, in modo robusto."""
    if "t_mono" in edge:
        return edge["t_mono"]
    for key in ("counter_edge", "cpu_edge", "counter", "cpu"):
        sub = edge.get(key)
        if isinstance(sub, dict) and "t_mono" in sub:
            return sub["t_mono"]
    raise KeyError(f"t_mono non trovato nel bordo: {list(edge.keys())}")


def measure_with_session(payload: dict):
    """Esegue la richiesta dentro la sessione energetica CasualWatt, usando i bordi di misura."""
    if not HAS_CASUALWATT or SESSION is None:
        response = http_json(CHAT_API, payload)
        return response, None, None, "no_casualwatt"

    if not (hasattr(SESSION, "start") and hasattr(SESSION, "stop")
            and hasattr(SESSION, "read_measurement_edge")
            and hasattr(SESSION, "package_energy_exact_between")):
        response = http_json(CHAT_API, payload)
        return response, None, None, "casualwatt_api_mancante"

    edge_start = SESSION.read_measurement_edge()
    t0 = edge_t(edge_start)
    response = http_json(CHAT_API, payload)
    edge_end = SESSION.read_measurement_edge()
    t1 = edge_t(edge_end)

    energy_j = SESSION.package_energy_exact_between(t0, t1)
    power_w = energy_j / (t1 - t0) if energy_j is not None and t1 > t0 else None
    return response, energy_j, power_w, "casualwatt_edge"


def run_one(model: str, query: dict, repeat: int) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": query["prompt"]}],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": TEMPERATURE, "num_predict": NUM_PREDICT},
    }
    t0 = time.perf_counter()
    response, energy_j, power_w, energy_method = measure_with_session(payload)
    t1 = time.perf_counter()
    duration = t1 - t0

    message = (response.get("message") or {})
    answer = (message.get("content") or "").strip()
    prompt_tokens = response.get("prompt_eval_count") or 0
    output_tokens = response.get("eval_count") or 0
    energy_per_token = energy_j / output_tokens if energy_j and output_tokens else None
    return {
        "query_id": query["id"],
        "query_type": query["type"],
        "repeat": repeat,
        "model": model,
        "prompt": query["prompt"],
        "expected": query["expected"],
        "answer": answer,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "duration_s": round(duration, 6),
        "energy_j": energy_j,
        "energy_per_token_j": energy_per_token,
        "power_w": power_w,
        "tokens_per_second": output_tokens / duration if duration else None,
        "ttft_ms": None,
        "itl_ms": None,
        "is_correct": None,
        "eval_method": "manual_review_or_casualwatt",
        "energy_method": energy_method,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def simple_correctness(row: dict):
    qtype = row["query_type"]
    answer = (row["answer"] or "").strip().lower()
    expected = (row["expected"] or "").strip().lower()
    if qtype == "number":
        return int(expected in answer) if answer else 0
    if qtype == "short_text":
        return int(expected in answer) if answer else 0
    return None


def main():
    if not ollama_ok():
        raise SystemExit(f"Ollama non raggiungibile su {OLLAMA_URL}")

    available = available_models()
    print("Modelli disponibili:")
    for m in available:
        print(" -", m)

    if not HAS_CASUALWATT:
        print("[warn] CasualWatt non disponibile:", CASUALWATT_IMPORT_ERROR)

    rows = []
    warmups = []

    if HAS_CASUALWATT and SESSION is not None:
        print("[casualwatt] avvio sessione energetica")
        SESSION.start()

    for model in MODELS:
        if model not in available:
            print(f"[skip] modello non disponibile: {model}")
            continue
        print(f"[warm-up] {model}")
        warmups.extend(warmup(model))

    queries = QUERIES[:]
    random.shuffle(queries)

    for query in queries:
        for model in MODELS:
            if model not in available:
                continue
            for repeat in range(1, REPEATS + 1):
                print(f"[run] {query['id']} | {model} | repeat {repeat}")
                row = run_one(model, query, repeat)
                row["is_correct"] = simple_correctness(row)
                rows.append(row)
                if row["energy_j"] is None:
                    print("  [warn] energia non disponibile per questa sessione")
                time.sleep(1.0)

    if HAS_CASUALWATT and SESSION is not None:
        print("[casualwatt] stop sessione energetica")
        SESSION.stop()

    fields = list(rows[0].keys()) if rows else []
    with CSV_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    summary = {}
    for model in MODELS:
        model_rows = [r for r in rows if r["model"] == model]
        energies = [r["energy_j"] for r in model_rows if r["energy_j"] is not None]
        summary[model] = {
            "n_runs": len(model_rows),
            "energy_j_mean": statistics.fmean(energies) if energies else None,
            "energy_j_median": statistics.median(energies) if energies else None,
            "energy_j_min": min(energies) if energies else None,
            "energy_j_max": max(energies) if energies else None,
        }

    JSON_PATH.write_text(
        json.dumps({"rows": rows, "summary": summary, "warmups": warmups}, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"CSV: {CSV_PATH}")
    print(f"JSON: {JSON_PATH}")


if __name__ == "__main__":
    main()
