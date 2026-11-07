# -*- coding: utf-8 -*-
"""machine_state.py — lo stato della macchina di P1.4 sul percorso di misura.

Perche' esiste. P1.4 (``protocollo_v4_20261024.md:218-228``) impone che una
campagna parta con: modello caricato con ``keep_alive=-1`` e **verificato
residente** su ``/api/ps``; due warm-up a ``(512,128)`` scartati; GUI di
LibreHardwareMonitor chiusa; alimentatore collegato e piano energetico
registrato; sampler alla stessa cadenza della misura; top-5 processi e CPU
totale prima e dopo, con ``background_load`` se la CPU totale resta sopra il
5% per 3 s. Il runner v4 implementava la sequenza di blocco (P1.5) e non
questi obblighi: un run poteva partire con il modello freddo, con la GUI
aperta o su batteria, e nessun artefatto lo avrebbe detto. P4.4 requisito 6
(``:1487-1488``) li richiede identici anche sul blocco di controllo.

Cosa NON fa questo modulo: non misura energia, non scrive righe, non decide
soglie. Raccoglie fatti e li restituisce; l'unica decisione che prende e'
quella scritta nel protocollo — batteria scollegata, GUI aperta e modello non
residente dopo il caricamento **fermano il run** con ``MachineStateError``,
perche' una misura presa in quello stato non e' quella congelata. Un
``background_load`` invece **non** ferma il run: e' un flag da dichiarare
(la forma che P1.4 gli da'), e il suo esito va nel run metadata.

Lo schema P5 e' congelato a 174 colonne di riga, 34 di riepilogo di blocco e
30 di metadato: nessuna delle quantita' raccolte qui ha una colonna, quindi
finiscono tutte nella nota del run metadata (``notes``), come i contatori di
Emenda 8. Un obbligo di protocollo dichiarato in una nota e' verificabile;
una colonna nuova lo sarebbe a costo di allargare lo schema congelato.
"""
from __future__ import annotations

import math
import platform
import subprocess
import time
from typing import Callable, Dict, List, Optional, Sequence

import psutil
import requests

KEEP_ALIVE_RESIDENT = -1       # P1.4: intero, non la stringa "-1"
API_TIMEOUT_S = 5.0            # letture json di /api/ps e /api/version
LOAD_TIMEOUT_S = 900.0         # tetto HTTP del caricamento, non una soglia
WARMUP_TIMEOUT_S = 900.0       # tetto HTTP del warm-up, non una soglia
WARMUP_N_IN = 512              # P1.4: geometria del warm-up (N_in, N_out)
WARMUP_N_OUT = 128
WARMUP_REPEATS = 2             # P1.4: "due warm-up ... scartati"
BACKGROUND_THRESHOLD_PCT = 5.0  # P1.4: "sopra il 5%"
BACKGROUND_SUSTAIN_S = 3.0     # P1.4: "per 3 s"
CPU_SAMPLE_INTERVAL_S = 1.0    # cadenza dei campioni di CPU totale
TOP_PROCESSES = 5              # P1.4: "top-5 processi"
TOP_WINDOW_S = 1.0             # finestra di osservazione dei processi

#: Il pid 0 su Windows e' "System Idle Process": la sua CPU e' il tempo in cui
#: nessuno lavora, cioe' il complemento del carico. In cima a un top-5 non e'
#: un processo concorrente e renderebbe la dichiarazione illeggibile.
EXCLUDED_PIDS = (0,)

#: Un warm-up a (512,128) serve a portare pesi e cache di allocazione in
#: regime. Il testo non deve essere intelligente: deve avere circa 512 token,
#: e i conteggi reali del motore vengono restituiti e dichiarati, perche' e'
#: il motore a dire quanti token ha visto (P2.1: il contatore non si stima).
WARMUP_SENTENCE = (
    "CasualWatt misura l'energia di una inferenza locale leggendo il "
    "contatore del package della CPU. ")


class MachineStateError(RuntimeError):
    """Stato macchina non conforme a P1.4: il run non parte o non prosegue."""


def _get_json(url: str, timeout_s: float = API_TIMEOUT_S) -> Dict:
    try:
        r = requests.get(url, timeout=timeout_s)
    except Exception as exc:
        raise MachineStateError(
            f"lettura {url} fallita: {type(exc).__name__}: {exc}") from exc
    if r.status_code != 200:
        raise MachineStateError(
            f"lettura {url}: HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception as exc:
        raise MachineStateError(
            f"lettura {url}: risposta non json: {type(exc).__name__}") from exc
    return data if isinstance(data, dict) else {}


def _post_json(url: str, payload: Dict,
               timeout_s: float) -> Dict:
    try:
        r = requests.post(url, json=payload, timeout=timeout_s)
    except Exception as exc:
        raise MachineStateError(
            f"POST {url} fallito: {type(exc).__name__}: {exc}") from exc
    if r.status_code != 200:
        raise MachineStateError(
            f"POST {url}: HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception as exc:
        raise MachineStateError(
            f"POST {url}: risposta non json: {type(exc).__name__}") from exc
    return data if isinstance(data, dict) else {}


def _normalized_name(name: str) -> str:
    """Ollama omette ``:latest``: ``qwen2.5`` e ``qwen2.5:latest`` sono lo
    stesso modello e il confronto fra residente e richiesto non puo' fallire
    per il tag implicito."""
    text = str(name or "").strip()
    return text if ":" in text else text + ":latest"


def same_model(a: str, b: str) -> bool:
    """Stesso modello a meno del tag implicito ``:latest``."""
    return _normalized_name(a) == _normalized_name(b)


def resident_models(api_url: str,
                    timeout_s: float = API_TIMEOUT_S) -> List[Dict]:
    """Modelli in memoria secondo ``/api/ps``.

    Restituisce una voce per modello con ``name``, ``size_vram`` ed
    ``expires_at``; ``expires_at`` e' la prova che ``keep_alive`` ha preso:
    con ``keep_alive=-1`` Ollama risponde con una scadenza molto lontana
    (``2318-...``) e non con un orario vicino.
    """
    data = _get_json(f"{api_url}/api/ps", timeout_s)
    out: List[Dict] = []
    for item in data.get("models") or []:
        if not isinstance(item, dict):
            continue
        out.append({
            "name": str(item.get("name") or item.get("model") or ""),
            "size_vram": item.get("size_vram"),
            "expires_at": str(item.get("expires_at") or ""),
        })
    return out


def ensure_resident(model: str, *, api_url: str,
                    num_ctx: int, timeout_s: float = API_TIMEOUT_S,
                    load_timeout_s: float = LOAD_TIMEOUT_S) -> Dict:
    """Verifica che ``model`` sia in memoria e, se non lo e', lo carica.

    Il caricamento e' un ``POST /api/generate`` con prompt vuoto e
    ``keep_alive=-1`` numerico: e' la forma che Ollama accetta (la stringa
    ``"-1"`` produce ``400 time: missing unit in duration``) e carica i pesi
    senza generare token. Dopo il POST la residenza si **riverifica** su
    ``/api/ps``: un caricamento che risponde 200 senza lasciare il modello in
    memoria non e' uno stato conforme, e la dichiarazione non si deduce dalla
    risposta.
    """
    before = resident_models(api_url, timeout_s)
    hit = next((r for r in before if same_model(r["name"], model)), None)
    if hit is not None:
        return {"model": model, "action": "already-resident",
                "expires_at": hit["expires_at"],
                "size_vram": hit["size_vram"]}
    _post_json(f"{api_url}/api/generate",
               {"model": model, "prompt": "", "stream": False,
                "keep_alive": int(KEEP_ALIVE_RESIDENT),
                "options": {"num_ctx": int(num_ctx)}},
               load_timeout_s)
    after = resident_models(api_url, timeout_s)
    hit = next((r for r in after if same_model(r["name"], model)), None)
    if hit is None:
        raise MachineStateError(
            f"P1.4: il modello {model!r} non risulta residente su /api/ps "
            f"dopo il caricamento (residenti: "
            f"{[r['name'] for r in after] or 'nessuno'})")
    return {"model": model, "action": "loaded",
            "expires_at": hit["expires_at"],
            "size_vram": hit["size_vram"]}


def warmup_prompt(n_words: int = WARMUP_N_IN) -> str:
    """Testo deterministico di circa ``n_words`` parole, per il warm-up.

    Il conteggio vero dei token lo da' il motore (``prompt_eval_count``) e
    viene restituito: la geometria del warm-up e' dichiarata, non dedotta da
    una lunghezza in caratteri.
    """
    words = WARMUP_SENTENCE.split()
    repeats = max(1, int(math.ceil(n_words / len(words))))
    return " ".join([WARMUP_SENTENCE.strip()] * repeats)


def warmup(model: str, *, api_url: str, num_ctx: int,
           repeats: int = WARMUP_REPEATS,
           n_in: int = WARMUP_N_IN, n_out: int = WARMUP_N_OUT,
           temperature: float = 0.0,
           timeout_s: float = WARMUP_TIMEOUT_S) -> List[Dict]:
    """Esegue i warm-up di P1.4 e **li scarta**: nessuna riga, nessun
    campione, nessuna energia attribuita. Restituisce solo i conteggi del
    motore, perche' "scartato" deve voler dire non usato nei dati e non
    "non registrato": l'artefatto deve poter dire che cosa e' stato scartato.
    """
    text = warmup_prompt(n_in)
    out: List[Dict] = []
    for k in range(int(repeats)):
        data = _post_json(
            f"{api_url}/api/generate",
            {"model": model, "prompt": text, "stream": False,
             "keep_alive": int(KEEP_ALIVE_RESIDENT),
             "options": {"num_ctx": int(num_ctx),
                         "num_predict": int(n_out),
                         "temperature": float(temperature)}},
            timeout_s)
        out.append({
            "repeat": k + 1,
            "done": data.get("done"),
            "prompt_eval_count": data.get("prompt_eval_count"),
            "eval_count": data.get("eval_count"),
            "total_duration_ns": data.get("total_duration"),
        })
    return out


def sample_top_processes(n: int = TOP_PROCESSES,
                         window_s: float = TOP_WINDOW_S) -> List[Dict]:
    """I primi ``n`` processi per CPU su una finestra di ``window_s``.

    ``psutil`` misura la CPU per processo fra due letture:
    la prima chiamata arma il contatore, la seconda lo legge dopo la finestra.
    Il valore puo' superare 100 su host multi-core, perche' e' la somma dei
    core usati: si dichiara cosi' come lo da' il sistema, non normalizzato.
    """
    primed = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc.cpu_percent(None)
            primed.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(window_s)
    rows: List[Dict] = []
    for proc in primed:
        try:
            info = proc.info
            pid = int(info.get("pid", 0))
            if pid in EXCLUDED_PIDS:
                continue
            rows.append({"pid": pid,
                         "name": str(info.get("name") or ""),
                         "cpu_pct": round(float(proc.cpu_percent(None)), 1)})
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda r: r["cpu_pct"], reverse=True)
    return rows[:int(n)]


def total_cpu_samples(duration_s: float = BACKGROUND_SUSTAIN_S,
                      interval_s: float = CPU_SAMPLE_INTERVAL_S) -> List[float]:
    """CPU totale del sistema campionata ogni ``interval_s`` per
    ``duration_s``. Ogni campione e' la media dall'ultimo campione, quindi
    tre campioni a 1 s sono i tre secondi di P1.4."""
    psutil.cpu_percent(None)
    samples: List[float] = []
    deadline = time.monotonic() + float(duration_s)
    while time.monotonic() < deadline:
        time.sleep(float(interval_s))
        samples.append(round(float(psutil.cpu_percent(None)), 1))
    return samples


def background_load_from_samples(
        samples: Sequence[float],
        threshold_pct: float = BACKGROUND_THRESHOLD_PCT,
        sustain_s: int = int(BACKGROUND_SUSTAIN_S)) -> bool:
    """``background_load`` di P1.4: la CPU totale resta sopra la soglia per
    ``sustain_s`` campioni consecutivi (1 s ciascuno). Non e' "un picco
    sopra soglia": serve la permanenza, perche' e' quella che contamina la
    baseline e non un processo breve che finisce prima della misura."""
    run = 0
    for value in samples:
        run = run + 1 if float(value) > float(threshold_pct) else 0
        if run >= int(sustain_s):
            return True
    return False


def power_state() -> Dict:
    """Alimentazione e piano energetico, come li vede il sistema.

    La batteria si legge da ``psutil``: se non esiste (desktop) lo stato e'
    ``absent`` e non un "collegato" dedotto. Il piano energetico e' Windows
    (``powercfg /getactivescheme``); su altri sistemi la voce e' dichiarata
    non applicabile, non inventata. Un errore di lettura finisce in
    ``notes`` e non ferma il run: uno stato non leggibile e' dichiarato, non
    assunto.
    """
    out: Dict = {"plan": "", "power_plugged": None,
                 "battery_percent": None, "battery": "absent",
                 "notes": []}
    if platform.system() == "Windows":
        try:
            r = subprocess.run(["powercfg", "/getactivescheme"],
                               capture_output=True, text=True, timeout=10)
            out["plan"] = (r.stdout or "").strip()
        except Exception as exc:
            out["notes"].append(
                f"powercfg non leggibile: {type(exc).__name__}: {exc}")
    else:
        out["notes"].append(
            f"piano energetico non applicabile su {platform.system()}")
    try:
        battery = psutil.sensors_battery()
    except Exception as exc:
        out["notes"].append(
            f"batteria non leggibile: {type(exc).__name__}: {exc}")
        battery = None
    if battery is not None:
        out["battery"] = "present"
        out["power_plugged"] = bool(battery.power_plugged)
        out["battery_percent"] = round(float(battery.percent), 1)
    return out


def require_ac_power(state: Optional[Dict] = None) -> Dict:
    """P1.4: "alimentatore collegato". Su un host con batteria, una misura
    a batteria non e' quella congelata: si ferma con la causa. Su un host
    senza batteria la condizione non e' decidibile e non si assume."""
    state = power_state() if state is None else state
    if state.get("battery") == "present" and state.get("power_plugged") is False:
        raise MachineStateError(
            "P1.4: host alimentato a batteria "
            f"({state.get('battery_percent')}%): collegare l'alimentatore")
    return state


LHM_PROCESS_MARKERS = ("librehardwaremonitor",)


def lhm_processes() -> List[Dict]:
    """Processi la cui immagine e' la GUI di LibreHardwareMonitor."""
    found: List[Dict] = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = str(proc.info.get("name") or "")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        lowered = name.lower()
        if any(marker in lowered for marker in LHM_PROCESS_MARKERS):
            found.append({"pid": int(proc.info.get("pid", 0)),
                          "name": name})
    return found


def require_lhm_closed() -> List[Dict]:
    """P1.4: "GUI di LibreHardwareMonitor chiusa". Il costo dell'osservatore
    misurato e' 0,2-0,9 W e non si sottrae (P1.4,
    ``observer_cost_20261023_analisi.md`` §2): l'unica via congelata e'
    chiuderla, quindi se e' aperta il run non parte."""
    found = lhm_processes()
    if found:
        raise MachineStateError(
            "P1.4: GUI di LibreHardwareMonitor aperta "
            f"({found}): chiuderla prima di misurare")
    return found


def sampler_cadence(session: object) -> Optional[float]:
    """Cadenza del sampler che la sessione userebbe davvero (P1.4: "sampler
    attivo con la stessa cadenza della misura"). ``None`` se la sessione non
    la dichiara: non si assume un valore."""
    value = getattr(session, "interval_s", None)
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
