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

# Cache locale modello embeddings (valutazione semantica ground-truth):
# il modello viene scaricato una volta qui e riutilizzato offline.
EMBED_MODEL_DIR = BASE_DIR / "models" / os.getenv(
    "CW_EMBED_MODEL_DIR", "paraphrase-multilingual-MiniLM-L12-v2"
).strip().strip('"')

for _d in (RESULTS_DIR, LOGS_DIR, DATASET_DIR, EMBED_MODEL_DIR.parent):
    _d.mkdir(parents=True, exist_ok=True)


def env_float(name: str, default: float) -> float:
    """Legge una variabile d'ambiente come float con fallback sicuro."""
    try:
        return float(os.getenv(name, "").strip().strip('"') or default)
    except (TypeError, ValueError):
        return float(default)


def env_str(name: str, default: str) -> str:
    """Legge una variabile d'ambiente come stringa con fallback sicuro."""
    v = os.getenv(name)
    if v is None or not v.strip():
        return default
    return v.strip().strip('"').strip("'")


def _parse_env_file(path: Path) -> dict:
    """Parser minimale e robusto di un file .env (senza dipendenze esterne).

    Gestisce: commenti (#), righe vuote, virgolette, BOM UTF-8, CRLF.
    Ritorna una dict chiave->valore (vuota se il file non esiste/legibile).
    """
    parsed: dict = {}
    try:
        if not path.exists():
            return parsed
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.split("#", 1)[0].strip().strip('"').strip("'")
            if k:
                parsed[k] = v
    except Exception:
        pass
    return parsed


def _load_dotenv() -> None:
    """Carica un eventuale file .env nella root del progetto (best effort).

    Priorita': per OLLAMA_HOST il valore del .env LOCALE vince sempre
    sull'ambiente di sistema. Motivo: su Windows il servizio Ollama spesso
    imposta OLLAMA_HOST="0.0.0.0:11434" a livello globale (e' un indirizzo di
    ASCOLTO, non di connessione) e bloccherebbe la correzione via .env.
    Per le altre chiavi vale la precedenza standard (var esistente non
    sovrascritta).
    """
    env_file = BASE_DIR / ".env"
    local_vars = _parse_env_file(env_file)
    try:
        from dotenv import load_dotenv  # opzionale

        if env_file.exists():
            load_dotenv(env_file, override=False)
    except Exception:
        pass
    for k, v in local_vars.items():
        if k == "OLLAMA_HOST" or k not in os.environ:
            os.environ[k] = v


_load_dotenv()

# ---------------------------------------------------------------------------
# Ollama (sezione 5 e 8)
# ---------------------------------------------------------------------------
# Host Ollama per le RICHIESTE CLIENT. Default locale.
# NOTE:
#  * 0.0.0.0 / :: sono indirizzi di BINDING (ascolto del server), NON host a cui
#    connettersi -> vengono convertiti in 127.0.0.1.
#  * Se l'host non ha una porta esplicita, viene aggiunta la porta di default
#    di Ollama (:11434). Senza questo fix, "http://localhost" punterebbe alla
#    porta 80 e la connessione verrebbe rifiutata.
OLLAMA_DEFAULT_PORT = 11434
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip().strip('"').rstrip("/")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
_host_no_scheme = OLLAMA_HOST.split("://", 1)[-1]
if _host_no_scheme.startswith("0.0.0.0") or _host_no_scheme.startswith("[::]") or _host_no_scheme.startswith("::"):
    OLLAMA_HOST = OLLAMA_HOST.replace(_host_no_scheme, "127.0.0.1:11434" if ":" in _host_no_scheme else "127.0.0.1", 1)
    _host_no_scheme = OLLAMA_HOST.split("://", 1)[-1]
# Aggiunta automatica della porta di default se assente (es. http://localhost -> http://localhost:11434)
try:
    from urllib.parse import urlsplit, urlunsplit

    _parts = urlsplit(OLLAMA_HOST)
    if _parts.port is None and _parts.netloc:
        _netloc = f"{_parts.netloc}:{OLLAMA_DEFAULT_PORT}"
        OLLAMA_HOST = urlunsplit((_parts.scheme, _netloc, _parts.path.rstrip("/"), "", ""))
except Exception:
    pass
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
# Chiavi d'ambiente richieste dalla specifica (sezione 14).
# NOTA: i valori qui sotto sono SNAPSHOT dell'ambiente al momento del import.
# La fonte canonica a runtime e' sempre os.environ: la GUI puo' aggiornare le
# chiavi a caldo con apply_api_keys() (pulsante "Salva Chiavi"), e i moduli
# che effettuano richieste (cloud_estimator, carbon_intensity) leggono da li'.
API_KEY_ENV_VARS = (
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GOOGLE_API_KEY",
    "ELECTRICITY_MAPS_API_TOKEN",
)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
ELECTRICITY_MAPS_API_TOKEN = os.getenv("ELECTRICITY_MAPS_API_TOKEN", "")


def _provider_base_url(cfg: dict) -> str:
    """Ricostruisce un endpoint OpenAI-style dal solo base_url."""
    base = str(cfg.get("base_url", "")).rstrip("/")
    return {
        "models_endpoint": f"{base}/models",
        "chat_endpoint": f"{base}/chat/completions",
    }


def refresh_provider_keys() -> None:
    """Risincronizza CLOUD_PROVIDERS (e i globali XXX_API_KEY) con os.environ.

    Chiamata dopo apply_api_keys()/load_saved_api_keys() perche' i campi
    'api_key'/'enabled' dei provider non restino congelati all'import.
    """
    global GROQ_API_KEY, OPENROUTER_API_KEY, GOOGLE_API_KEY
    global ELECTRICITY_MAPS_API_TOKEN
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    ELECTRICITY_MAPS_API_TOKEN = os.getenv("ELECTRICITY_MAPS_API_TOKEN", "")
    live = {
        "GROQ_API_KEY": GROQ_API_KEY,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "GOOGLE_API_KEY": GOOGLE_API_KEY,
    }
    for name, cfg in CLOUD_PROVIDERS.items():
        key = live.get(cfg.get("api_key_env", ""), "")
        cfg["api_key"] = key
        cfg["enabled"] = bool(key)
        # self-healing: se gli endpoint mancano o puntano ancora alla porta 80
        # (es. base_url senza schema/porta), rigenerarli dal base_url corrente
        need = False
        for ep in ("models_endpoint", "chat_endpoint"):
            u = str(cfg.get(ep, ""))
            if not u or u.startswith(("http://localhost/", "http://127.0.0.1/")):
                need = True
        if need and cfg.get("base_url"):
            cfg.update(_provider_base_url(cfg))


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
IDLE_CALIBRATION_SECONDS = float(os.getenv("CW_IDLE_CALIBRATION_SECONDS", "10"))
# Calibrazione idle puramente empirica: finestra di riposo consigliata 10 s
# (delta Joule reali del contatore package / durata). Configurabile via env.
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


# ---------------------------------------------------------------------------
# Persistenza delle API key (pannello "Impostazioni / Chiavi API" della GUI)
# ---------------------------------------------------------------------------
# File nascosto nella root del progetto. Le chiavi sono secreti: NON finisce
# nel repository (.gitignore), perms 0600 su POSIX, e il file non contiene
# path/endpoint — solo le variabili d'ambiente della sezione 14.
API_KEYS_FILE = BASE_DIR / ".casualwatt_keys.json"


def load_saved_api_keys() -> dict:
    """Legge il file chiavi salvato (best effort). Ritorna {} se assente/corrotto."""
    try:
        if not API_KEYS_FILE.exists():
            return {}
        import json

        data = json.loads(API_KEYS_FILE.read_text(encoding="utf-8-sig"))
        if isinstance(data, dict):
            return {
                k: str(v).strip()
                for k, v in data.items()
                if k in API_KEY_ENV_VARS and str(v or "").strip()
            }
    except Exception:
        pass
    return {}


def save_api_keys(keys: dict) -> bool:
    """Salva le chiavi nel file nascosto con permessi restrittivi. True se OK."""
    try:
        import json

        payload = {k: str(v).strip() for k, v in (keys or {}).items() if k in API_KEY_ENV_VARS}
        API_KEYS_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        try:
            os.chmod(API_KEYS_FILE, 0o600)
        except Exception:
            pass  # su Windows il chmod può essere inerte: non è un errore
        return True
    except Exception:
        return False


def apply_api_keys(keys: dict, persist: bool = True) -> bool:
    """Applica le chiavi alla sessione corrente.

    * aggiorna os.environ (fonte canonica a runtime);
    * risincronizza CLOUD_PROVIDERS via refresh_provider_keys();
    * persiste nel file nascosto .casualwatt_keys.json (se persist=True).

    Le stringhe vuote rimuovono la variabile dall'ambiente (il provider
    corrispondente torna 'disabled'). Ritorna True se il salvataggio è riuscito.
    """
    for var in API_KEY_ENV_VARS:
        val = str((keys or {}).get(var, "") or "").strip()
        if val:
            os.environ[var] = val
        else:
            os.environ.pop(var, None)
    refresh_provider_keys()
    if persist:
        merged = load_saved_api_keys()
        for var in API_KEY_ENV_VARS:
            nv = str((keys or {}).get(var, "") or "").strip()
            if nv:
                merged[var] = nv
            else:
                merged.pop(var, None)
        return save_api_keys(merged)
    return True


def init_secrets_from_disk() -> None:
    """Auto-caricamento all'avvio: file chiavi -> os.environ -> provider.

    Precedenza: variabile d'ambiente già esistente > file .casualwatt_keys.json
    (le env reali dell'utente non vengono mai sovrascritte dal file).
    """
    saved = load_saved_api_keys()
    changed = False
    for var, val in saved.items():
        if not os.environ.get(var) and val:
            os.environ[var] = val
            changed = True
    if changed:
        refresh_provider_keys()


init_secrets_from_disk()
