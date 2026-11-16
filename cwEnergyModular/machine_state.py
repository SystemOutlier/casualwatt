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
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import psutil
import requests

KEEP_ALIVE_RESIDENT = -1       # P1.4: intero, non la stringa "-1"
API_TIMEOUT_S = 5.0            # letture json di /api/ps e /api/version
LOAD_TIMEOUT_S = 900.0         # tetto HTTP del caricamento, non una soglia
WARMUP_TIMEOUT_S = 900.0       # tetto HTTP del warm-up, non una soglia
WARMUP_N_IN = 512              # P1.4: geometria del warm-up (N_in, N_out)
WARMUP_N_OUT = 128
WARMUP_REPEATS = 2             # P1.4: "due warm-up ... scartati"
BACKGROUND_THRESHOLD_PCT = 5.0  # P1.4: "sopra il 5%" (default legacy, override via parameter)
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


def background_signature(char_sha256: Optional[str] = None,
                         cpu_samples: Optional[Sequence[float]] = None) -> Dict:
    """Firma del background per declared_background (Fase 3 emenda, estesa).

    La firma include grandezze identitarie dello stato E grandezze di
    intensità del background: la CPU% media e massima durante la finestra
    di osservazione, insieme ai PID, nomi e CPU% dei processi rilevanti.
    La firma serve a verificare che il background resti stabile per almeno
    tre finestre consecutive prima di misurare.

    Restituisce un dizionario con:
    - ``processes``: top-5 processi per CPU% (pid, name, cpu_pct)
    - ``power_plan``: piano energetico da powercfg (stringa)
    - ``battery``: stato batteria ("absent", "present")
    - ``power_plugged``: True/False/None (None se batteria assente)
    - ``char_sha256``: hash della caratterizzazione idle (se fornito)
    - ``timestamp``: marca temporale della firma
    - ``cpu_total_mean_pct``: CPU totale media durante la finestra (opzionale)
    - ``cpu_total_max_pct``: CPU totale massima durante la finestra (opzionale)
    - ``process_cpu_mean_pct``: CPU media dei processi top-5 (opzionale)
    - ``process_cpu_max_pct``: CPU massima dei processi top-5 (opzionale)
    - ``timestamp_start``: timestamp monotono inizio finestra
    - ``timestamp_end``: timestamp monotono fine finestra

    Se ``cpu_samples`` è fornito, la firma include le statistiche di intensità
    CPU derivate da quei campioni. Se ``cpu_samples`` è assente, i campi di
    intensità restano ``None`` e la firma resta valida per il confronto
    identitario (comportamento legacy).
    """
    import time as _time
    ps = power_state()
    t_start = _time.monotonic()
    top5 = sample_top_processes(n=TOP_PROCESSES, window_s=TOP_WINDOW_S)
    t_end = _time.monotonic()

    sig: Dict = {
        "processes": top5,
        "power_plan": ps.get("plan", ""),
        "battery": ps.get("battery", "absent"),
        "power_plugged": ps.get("power_plugged"),
        "char_sha256": char_sha256 if char_sha256 else "",
        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "cpu_total_mean_pct": None,
        "cpu_total_max_pct": None,
        "process_cpu_mean_pct": None,
        "process_cpu_max_pct": None,
        "timestamp_start": t_start,
        "timestamp_end": t_end,
    }

    # Se sono forniti campioni CPU totali, calcola le statistiche di intensità.
    if cpu_samples:
        try:
            cpu_vals = [float(x) for x in cpu_samples]
        except (TypeError, ValueError):
            cpu_vals = []
        if cpu_vals:
            sig["cpu_total_mean_pct"] = round(sum(cpu_vals) / len(cpu_vals), 2)
            sig["cpu_total_max_pct"] = round(max(cpu_vals), 2)

    # Statistiche di intensità dai processi top-5 (se presenti).
    proc_cpus = []
    for p in top5:
        try:
            proc_cpus.append(float(p.get("cpu_pct", 0)))
        except (TypeError, ValueError):
            pass
    if proc_cpus:
        sig["process_cpu_mean_pct"] = round(sum(proc_cpus) / len(proc_cpus), 2)
        sig["process_cpu_max_pct"] = round(max(proc_cpus), 2)

    return sig


def signatures_match(sig1: Dict, sig2: Dict) -> Tuple[bool, List[str]]:
    """Verifica se due firme di background coincidono.

    Confronta solo i campi identitari: processi rilevanti (per pid e nome),
    piano energetico, stato batteria. Non confronta timestamp o CPU%.

    Restituisce (match: bool, differenze: List[str]).
    Se match è True, differenze è vuoto.
    """
    differenze: List[str] = []

    # Confronto processi per PID (l'ordine può cambiare, i PID no)
    pids1 = {p["pid"] for p in sig1.get("processes", [])}
    pids2 = {p["pid"] for p in sig2.get("processes", [])}
    if pids1 != pids2:
        solo1 = pids1 - pids2
        solo2 = pids2 - pids1
        if solo1:
            differenze.append(f"processi presenti in sig1 ma non in sig2 (PID: {sorted(solo1)})")
        if solo2:
            differenze.append(f"processi presenti in sig2 ma non in sig1 (PID: {sorted(solo2)})")

    # Confronto nome del processo per PID: stesso PID con nome diverso indica
    # che il processo è stato sostituito (es. terminato e rilanciato con altro eseguibile).
    # La firma include già "name" (sample_top_processes:244-246), quindi il confronto
    # non aggiunge costo di采集, solo discriminazione.
    procs1 = {p["pid"]: p.get("name", "") for p in sig1.get("processes", [])}
    procs2 = {p["pid"]: p.get("name", "") for p in sig2.get("processes", [])}
    common_pids = pids1 & pids2
    for pid in sorted(common_pids):
        name1 = procs1.get(pid, "")
        name2 = procs2.get(pid, "")
        if name1 and name2 and name1 != name2:
            differenze.append(
                f"PID {pid}: nome cambiato da {name1!r} a {name2!r} "
                f"(processo sostituito)"
            )

    # Confronto piano energetico
    plan1 = sig1.get("power_plan", "")
    plan2 = sig2.get("power_plan", "")
    if plan1 != plan2:
        differenze.append(
            f"piano energetico cambiato: {plan1!r} -> {plan2!r}"
        )

    # Confronto stato batteria
    batt1 = sig1.get("battery", "absent")
    batt2 = sig2.get("battery", "absent")
    if batt1 != batt2:
        differenze.append(f"stato batteria cambiato: {batt1!r} -> {batt2!r}")

    # Confronto power_plugged (solo se batteria presente)
    if batt1 == "present" and batt2 == "present":
        plug1 = sig1.get("power_plugged")
        plug2 = sig2.get("power_plugged")
        if plug1 != plug2:
            differenze.append(f"alimentazione cambiata: {plug1!r} -> {plug2!r}")

    # Confronto hash caratterizzazione
    char1 = sig1.get("char_sha256", "")
    char2 = sig2.get("char_sha256", "")
    if char1 and char2 and char1 != char2:
        differenze.append("hash caratterizzazione mutato")

    return (len(differenze) == 0, differenze)


def signatures_match_with_intensity(
        sig1: Dict, sig2: Dict,
        cpu_tolerance_pct: float = 5.0,
        power_tolerance_w: Optional[float] = None) -> Tuple[str, List[str]]:
    """Confronto firme con intensità: distingue identità da stabilità intensità.

    A differenza di ``signatures_match()`` che restituisce solo un booleano,
    questa funzione distingue quattro casi:

    A. ``"stable"``: identità stabile E intensità entro tolleranza.
    B. ``"intensity_unstable"``: stessa identità, intensità variabile.
    C. ``"identity_changed"``: identità modificata.
    D. ``"insufficient_data"``: dati di intensità mancanti in almeno una firma.

    Parametri:
    - ``sig1``, ``sig2``: due firme da ``background_signature()``.
    - ``cpu_tolerance_pct``: tolleranza sulla CPU totale media (default 5%).
      Se la differenza tra le medie CPU supera questo valore, l'intensità
      è instabile. La tolleranza viene dal piano, non è una costante universale.
    - ``power_tolerance_w``: tolleranza sulla potenza media (opzionale).
      Se fornita, anche la potenza deve stare entro questa banda.

    Restituisce ``(verdetto, differenze)`` dove ``verdetto`` è uno dei quattro
    token sopra e ``differenze`` elenca le ragioni del verdetto.
    """
    # 1. Confronto identità (stessa logica di signatures_match).
    identico, diff_identita = signatures_match(sig1, sig2)
    if not identico:
        return ("identity_changed", diff_identita)

    # 2. Verifica dati di intensità disponibili.
    cpu1 = sig1.get("cpu_total_mean_pct")
    cpu2 = sig2.get("cpu_total_mean_pct")
    if cpu1 is None or cpu2 is None:
        return ("insufficient_data", [
            "dati intensità CPU mancanti in almeno una firma",
        ])

    differenze: List[str] = []

    # 3. Confronto intensità CPU con tolleranza.
    try:
        cpu_diff = abs(float(cpu1) - float(cpu2))
    except (TypeError, ValueError):
        return ("insufficient_data", [
            "valori CPU non numerici",
        ])
    if cpu_diff > float(cpu_tolerance_pct):
        differenze.append(
            f"CPU media cambiata: {cpu1}% → {cpu2}% "
            f"(differenza {cpu_diff:.1f}%, tolleranza {cpu_tolerance_pct}%)")

    # 4. Confronto intensità potenza, se la tolleranza è fornita.
    if power_tolerance_w is not None:
        pow1 = sig1.get("power_mean_w")
        pow2 = sig2.get("power_mean_w")
        if pow1 is None or pow2 is None:
            return ("insufficient_data", [
                "dati intensità potenza mancanti in almeno una firma",
            ])
        try:
            pow_diff = abs(float(pow1) - float(pow2))
        except (TypeError, ValueError):
            return ("insufficient_data", [
                "valori potenza non numerici",
            ])
        if pow_diff > float(power_tolerance_w):
            differenze.append(
                f"Potenza media cambiata: {pow1} W → {pow2} W "
                f"(differenza {pow_diff:.2f} W, tolleranza {power_tolerance_w} W)")

    if differenze:
        return ("intensity_unstable", differenze)
    return ("stable", [])


def thermal_state() -> Dict:
    """Raccoglie temperatura e throttling come fatti dichiarati.

    Non decide se il throttling invalida la misura: quella decisione
    appartiene al protocollo congelato e al runner. La temperatura e'
    una covariata ISO 50006 (variabile rilevante), non un normalizzatore
    finche' non e' dimostrato con i dati che ha un effetto sistematico
    sull'energia.

    Restituisce un dizionario con:
    - ``cpu_temperature_c``: temperatura CPU in gradi Celsius, vuoto se non
      disponibile.
    - ``gpu_temperature_c``: temperatura GPU in gradi Celsius, vuoto se non
      disponibile o GPU assente.
    - ``thermal_throttle_detected``: True/False/vuoto (vuoto se non verificabile).
    - ``thermal_throttle_source``: fonte del rilevamento, vuoto se non rilevato.
    - ``thermal_state_notes``: lista di note esplicative.

    Nessuna temperatura inventata: se il sensore non e' esposto, resta vuoto.
    """
    out: Dict = {
        "cpu_temperature_c": "",
        "gpu_temperature_c": "",
        "thermal_throttle_detected": "",
        "thermal_throttle_source": "",
        "thermal_state_notes": [],
    }

    notes: List[str] = []

    # Temperatura CPU — best-effort su Windows via psutil
    try:
        cpu_temps = psutil.sensors_temperatures()
        if cpu_temps:
            # psutil restituisce un dizionario di dizionari; prendi il primo
            # sensore con temperatura non nulla
            for _, entries in cpu_temps.items():
                for entry in entries:
                    if entry.current is not None and entry.current > 0:
                        out["cpu_temperature_c"] = round(entry.current, 1)
                        notes.append(f"CPU temp da sensore {entry.label!r}")
                        break
                if out["cpu_temperature_c"]:
                    break
            if not out["cpu_temperature_c"]:
                notes.append("sensori CPU presenti, nessuna temperatura letta")
        else:
            notes.append("sensori temperatura CPU non disponibili")
    except Exception as exc:
        notes.append(f"sensors_temperatures fallito: {type(exc).__name__}")

    # Temperatura GPU — non letta qui (richiede NVML/AMD SMI)
    # Il runner la popola se il monitor GPU e' attivo
    notes.append("GPU temp non letta da thermal_state (popolata dal monitor)")

    # Throttling — non verificato automaticamente; il runner o il protocollo
    # possono impostare il flag se una condizione e' rilevata
    notes.append("throttling non verificato automaticamente")

    out["thermal_state_notes"] = notes

    return out
