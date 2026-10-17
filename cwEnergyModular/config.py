# -*- coding: utf-8 -*-
"""
config.py — Configurazione centrale di CasualWatt Energy Benchmark.

Contiene percorsi, parametri Ollama/cloud, coefficienti energetici e la
lettura delle variabili d'ambiente richieste dalla specifica (sezione 14).

Nota metodologica (sezione 2): nessuna frazione arbitraria tipo
``total_energy_j * 0.1`` e' usata per attribuire energia a Ollama;
l'attribuzione avviene solo tramite CPU-time share documentato in
``energy/local_energy.py``.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Percorsi (tutto relativo alla cartella del progetto)
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

RESULTS_DIR = BASE_DIR / "results"
LOGS_DIR = BASE_DIR / "logs"
DATASET_DIR = BASE_DIR / "dataset"

LHM_DLL_PATH = (
    BASE_DIR
    / "LibreHardwareMonitorLib"
    / "LibreHardwareMonitor"
    / "LibreHardwareMonitorLib.dll"
)

CSV_RESULTS_PATH = RESULTS_DIR / "casualwatt_results.csv"
CSV_RUN_METADATA_PATH = RESULTS_DIR / "casualwatt_run_metadata.csv"

for _d in (RESULTS_DIR, LOGS_DIR, DATASET_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    """Carica un eventuale file .env nella root del progetto (best effort)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv  # opzionale

        load_dotenv(env_file)
        return
    except Exception:
        pass
    # fallback minimale senza dipendenze
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


_load_dotenv()

# ---------------------------------------------------------------------------
# Ollama (sezione 5 e 8)
# ---------------------------------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
OLLAMA_API_URL = OLLAMA_HOST
OLLAMA_TAGS_ENDPOINT = f"{OLLAMA_API_URL}/api/tags"
OLLAMA_GENERATE_ENDPOINT = f"{OLLAMA_API_URL}/api/generate"

# Nomi dei processi Ollama da individuare per il PID (sezione 7, punto 2)
OLLAMA_PROCESS_NAMES = (
    "ollama.exe",
    "ollama_llama_server.exe",
    "ollama",
    "ollama_llama_server",
)

# ---------------------------------------------------------------------------
# Provider cloud compatibili OpenAI (sezione 6 e 9)
# ---------------------------------------------------------------------------
# Chiavi d'ambiente richieste dalla specifica (sezione 14)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ELECTRICITY_MAPS_API_TOKEN = os.getenv("ELECTRICITY_MAPS_API_TOKEN", "")

CLOUD_PROVIDERS: dict = {
    "groq": {
        "label": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "models_endpoint": "https://api.groq.com/openai/v1/models",
        "chat_endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "api_key_env": "GROQ_API_KEY",
        "api_key": GROQ_API_KEY,
        "enabled": bool(GROQ_API_KEY),
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models_endpoint": "https://openrouter.ai/api/v1/models",
        "chat_endpoint": "https://openrouter.ai/api/v1/chat/completions",
        "api_key_env": "OPENROUTER_API_KEY",
        "api_key": OPENROUTER_API_KEY,
        "enabled": bool(OPENROUTER_API_KEY),
    },
    "google": {
        "label": "Google Gemini",
        # endpoint in formato OpenAI-compatible di Google AI Studio
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models_endpoint": (
            "https://generativelanguage.googleapis.com/v1beta/openai/models"
        ),
        "chat_endpoint": (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
            "chat/completions"
        ),
        "api_key_env": "GOOGLE_API_KEY",
        "api_key": GOOGLE_API_KEY,
        "enabled": bool(GOOGLE_API_KEY),
    },
}

# ---------------------------------------------------------------------------
# Parametri di benchmark (pannello GUI sezione 4.2)
# ---------------------------------------------------------------------------
DEFAULT_NUM_PROMPTS = int(os.getenv("CW_NUM_PROMPTS", "3"))
DEFAULT_TEMPERATURE = float(os.getenv("CW_TEMPERATURE", "0.2"))
DEFAULT_TIMEOUT_S = float(os.getenv("CW_TIMEOUT_S", "60"))
IDLE_CALIBRATION_SECONDS = float(os.getenv("CW_IDLE_CALIBRATION_SECONDS", "5"))
MONITOR_INTERVAL_S = 0.5  # frequenza campionamento energy tracker

# ---------------------------------------------------------------------------
# Stima energia di rete (sezione 9/12.2) — coefficienti documentati
# J/bit per trasmissione dati su rete geografica, valori conservativi da
# letteratura sugli access network (FTTx); confine: client-side NIC delta.
# ---------------------------------------------------------------------------
NETWORK_ENERGY_COEFFICIENT_J_PER_BIT = float(
    os.getenv("CW_NET_J_PER_BIT", "3.4e-8")
)

# GPU integrata: quota di potenza attiva package attribuibile all'iGPU
# quando non esiste contatore separato (euristica dichiarata, NON applicata
# come frazione dell'energia totale: opera sulla sola energia ATTIVA).
IGPU_POWER_SHARE = float(os.getenv("CW_IGPU_SHARE", "0.30"))

# EcoLogits: profilo hardware cloud assunto per la stima (sezione 9)
ECOLOGITS_HW_PROFILE = os.getenv("ECOLOGITS_HW_PROFILE", "H100")
ECOLOGITS_USE_FRAC = float(os.getenv("ECOLOGITS_USE_FRAC", "0.3"))
ECOLOGITS_COUNTRY_CODE = os.getenv("ECOLOGITS_COUNTRY_CODE", "IT")

# Electricity Maps (carbon intensity, energy/carbon_intensity.py)
ELECTRICITYMAPS_API_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"

# Power API interface code usato da EcoLogits per la country carbon intensity
ECO_CARBON_ZONE = os.getenv("CW_ECO_CARBON_ZONE", "IT")

# ---------------------------------------------------------------------------
# Prompt causali di default (valutazione sezione 10: cause/effect)
# ---------------------------------------------------------------------------
DEFAULT_CAUSAL_PROMPTS = [
    {
        "id": "causal-001",
        "text": (
            "Explain the link between deforestation and CO2 concentration. "
            "Answer strictly using the words 'cause' and 'effect'."
        ),
    },
    {
        "id": "causal-002",
        "text": (
            "Why does an uncooled CPU throttle its frequency? Answer with one "
            "short sentence that contains the words 'cause' and 'effect'."
        ),
    },
    {
        "id": "causal-003",
        "text": (
            "Describe the causal chain between rising sea temperature and "
            "coral bleaching. Use the words 'cause' and 'effect' explicitly."
        ),
    },
]

PROMPTS_FILE = DATASET_DIR / "causal_prompts.json"


def load_prompts() -> list:
    """Carica i prompt dal dataset se presente, altrimenti usa i default."""
    if PROMPTS_FILE.exists():
        try:
            import json

            data = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
            out = []
            for i, item in enumerate(data):
                if isinstance(item, str):
                    out.append({"id": f"custom-{i+1:03d}", "text": item})
                elif isinstance(item, dict) and "text" in item:
                    out.append(
                        {"id": item.get("id", f"custom-{i+1:03d}"), "text": item["text"]}
                    )
            if out:
                return out
        except Exception:
            pass
    return list(DEFAULT_CAUSAL_PROMPTS)
