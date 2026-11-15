#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_demo_tests.py — Protocollo dimostrativo CasualWatt
Esegue 3 query x 3 ripetizioni per 3 modelli SLM locali tramite Ollama.
Genera un CSV con energia, token, latenza, throughput e risposta.

Uso:
  python run_demo_tests.py

Prerequisiti:
  - Ollama avviato in locale su http://127.0.0.1:11434
  - Modelli già scaricati:
      hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest
      llama3.2:1b-instruct-q4_K_M
      qwen2.5:0.5b-instruct-q4_K_M
  - CasualWatt disponibile nello stesso ambiente, se si vuole integrare la misura energetica.

Nota:
  Lo script misura energia solo se il modulo CasualWatt/energy è disponibile.
  Altrimenti registra energia come N/A e produce comunque token, latenza e risposta.
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
API = f"{OLLAMA_URL}/api/generate"
MODELS = [
    "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest",
    "llama3.2:1b",
    "llama3.2:3b-instruct-q4_K_M",
]
QUERIES = [
    {"id": "q1", "type": "number", "prompt": "What is 2 + 2?", "expected": "4"},
    {"id": "q2", "type": "short_text", "prompt": "What is the capital of France?", "expected": "Paris"},
    {"id": "q3", "type": "free_text", "prompt": "Explain in one sentence the cause-effect relation between deforestation and CO2 concentration.", "expected": ""},
]
REPEATS = 3
NUM_PREDICT = 128
TEMPERATURE = 0.0
KEEP_ALIVE = -1
OUT_DIR = Path("output_demo")
OUT_DIR.mkdir(exist_ok=True)
CSV_PATH = OUT_DIR / "demo_results.csv"
JSON_PATH = OUT_DIR / "demo_results.json"

try:
    from energy import SESSION  # type: ignore
    HAS_CASUALWATT = True
except Exception:
    HAS_CASUALWATT = False


def post(payload: dict, timeout: float = 120.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(API, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_ok() -> bool:
    try:
        with urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as response:
            return response.status == 200
    except Exception:
        return False


def warmup(model: str) -> list[dict]:
    rows = []
    for i in range(2):
        payload = {
            "model": model,
            "prompt": "Warm-up request for CasualWatt demonstration.",
            "stream": False,
            "keep_alive": KEEP_ALIVE,
            "options": {"temperature": TEMPERATURE, "num_predict": 32},
        }
        response = post(payload)
        rows.append({
            "model": model,
            "warmup": i + 1,
            "prompt_tokens": response.get("prompt_eval_count"),
            "output_tokens": response.get("eval_count"),
            "total_duration_s": (response.get("total_duration") or 0) / 1e9,
        })
    return rows


def measure_energy():
    if HAS_CASUALWATT and hasattr(SESSION, "__enter__"):
        return SESSION
    import contextlib
    return contextlib.nullcontext()

def extract_energy(session):
    if session is None:
        return None, None
    result = getattr(session, "result", None)
    if isinstance(result, dict):
        return result.get("total_energy_j"), result.get("avg_power_w")
    return None, None
    
def run_one(model: str, query: dict, repeat: int) -> dict:
    payload = {
        "model": model,
        "prompt": query["prompt"],
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": TEMPERATURE, "num_predict": NUM_PREDICT},
    }
    t0 = time.perf_counter()
    energy_j = None
    power_w = None
    with measure_energy() as session:
        response = post(payload)
        energy_j, power_w = extract_energy(session)
    t1 = time.perf_counter()
    duration = t1 - t0
    prompt_tokens = response.get("prompt_eval_count") or 0
    output_tokens = response.get("eval_count") or 0
    answer = response.get("response", "").strip()
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
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


def simple_correctness(row: dict) -> int | None:
    qtype = row["query_type"]
    answer = (row["answer"] or "").strip().lower()
    expected = (row["expected"] or "").strip().lower()
    if qtype == "number":
        return int(expected in answer)
    if qtype == "short_text":
        return int(expected in answer)
    return None


def main():
    if not ollama_ok():
        raise SystemExit(f"Ollama non raggiungibile su {OLLAMA_URL}")
    rows = []
    warmups = []
    for model in MODELS:
        print(f"[warm-up] {model}")
        warmups.extend(warmup(model))
    queries = QUERIES[:]
    random.shuffle(queries)
    for query in queries:
        for model in MODELS:
            for repeat in range(1, REPEATS + 1):
                print(f"[run] {query['id']} | {model} | repeat {repeat}")
                row = run_one(model, query, repeat)
                row["is_correct"] = simple_correctness(row)
                rows.append(row)
                time.sleep(1.0)
    fields = list(rows[0].keys())
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
    JSON_PATH.write_text(json.dumps({"rows": rows, "summary": summary, "warmups": warmups}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"CSV: {CSV_PATH}")
    print(f"JSON: {JSON_PATH}")


if __name__ == "__main__":
    main()
