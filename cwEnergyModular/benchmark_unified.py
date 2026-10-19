# -*- coding: utf-8 -*-
"""
benchmark_unified.py — Motore di benchmark CasualWatt (sezione 7).

``run_unified_benchmark`` orchestra, nell'ordine della specifica:
1. sessione CasualWatt (SESSION.start);
2. PID Ollama;
3. calibrazione idle;
4. CasualWattLocalEnergyProfiler;
5. NetworkEnergyTracker;
6. CloudEnergyEstimator;
7. CarbonIntensityProvider;
8. esecuzione SOLO modelli locali selezionati;
9. esecuzione SOLO modelli cloud selezionati;
10. valutazione accuratezza/ECE/EPCL (evaluator);
11. export CSV un record per richiesta + run metadata.

Thread-safe rispetto alla GUI: callback ``on_log/on_progress/on_record``,
cancellazione via ``stop_event``. Nessuna eccezione esce verso l'alto: gli
errori finiscono in log e nel campo ``notes`` dei record.
"""
from __future__ import annotations

import os
import platform
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import requests

import config
from casualwatt_csv_export import export_results_csv, write_run_metadata
import llm_judge as _lj  # LAST_WINDOWS: finestre reali del sotto-processo giudice
from cloud_estimator import CloudEnergyEstimator, get_cloud_models
from energy.carbon_intensity import get_carbon_intensity
from energy.energy_session import SESSION
from energy.local_energy import CasualWattLocalEnergyProfiler, LocalEnergyResult
from energy.network_energy import NetworkEnergyTracker
from evaluator import evaluate_response

APP_VERSION = "1.0.0"


def _judge_via_energy_session(question: str, answer: str, model: Optional[str]):
    """Wrapper del LLM judge che traccia le finestre temporali per lo scorporo energetico.

    Delega a ``llm_judge.call_llm_judge``; le finestre temporali del giudice
    vengono registrate in ``_lj.LAST_WINDOWS`` dal modulo llm_judge stesso,
    permettendo al profiler di scorporare l'energia del giudice dal modello
    valutato (B2: integrazione sulla sottofinestra giudice, niente floor).
    """
    return _lj.call_llm_judge(question, answer, model)


# ---------------------------------------------------------------------------
# Lettura modelli Ollama (sezione 5)
# ---------------------------------------------------------------------------
def get_ollama_models(timeout_s: float = 8.0):
    """GET /api/tags -> (lista_modelli, errore). Mai solleva eccezioni.

    Se il connection-test fallisce su 127.0.0.1 ma OLLAMA_HOST puntava a
    0.0.0.0/::, riprova anche su localhost (equivalente locale).
    Ritorna ([], "") se Ollama risponde ma non ha modelli; ([], msg) in caso
    di errore di rete/endpoint (il messaggio viene mostrato nella GUI).
    """
    candidates = [config.OLLAMA_TAGS_ENDPOINT]
    if "127.0.0.1" in config.OLLAMA_TAGS_ENDPOINT:
        candidates.append(config.OLLAMA_TAGS_ENDPOINT.replace("127.0.0.1", "localhost"))
    last_err = ""
    for url in candidates:
        try:
            r = requests.get(url, timeout=timeout_s)
            if r.status_code != 200:
                last_err = f"HTTP {r.status_code} su {url}"
                continue
            data = r.json()
            out = []
            for m in data.get("models", []) or []:
                out.append(
                    {
                        "name": m.get("name", ""),
                        "size": int(m.get("size", 0) or 0),
                        "modified_at": m.get("modified_at", ""),
                    }
                )
            out.sort(key=lambda d: d["name"])
            return out, ""
        except requests.exceptions.ConnectionError:
            last_err = f"connessione rifiutata su {url} (Ollama e' in esecuzione?)"
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc} su {url}"
    return [], last_err


# ---------------------------------------------------------------------------
# Richieste (sezioni 8 e 9)
# ---------------------------------------------------------------------------
def _estimate_tokens(prompt_text: str, response_text: str):
    """Stima token con tiktoken se installato; altrimenti euristica len//4
    (dichiarata nelle note del record)."""
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return (
            max(len(enc.encode(prompt_text)), 1),
            max(len(enc.encode(response_text)), 0),
        )
    except Exception:
        return (
            max(len(prompt_text) // 4, 1),
            max(len(response_text) // 4, 0),
        )


def query_ollama(model: str, prompt: str, temperature: float, timeout_s: float,
                 num_predict: int = 160):
    """POST /api/generate (stream:false) + profilo energetico della finestra.

    response_data: {text, prompt_tokens, completion_tokens, duration_s}
    local_result : LocalEnergyResult profilato causalmente sulla finestra.
    NB: qui NON c'e' scorporo judge — usato dai percorsi senza LLM Judge
    (cloud, legacy). Il percorso locale del benchmark usa _ollama_infer_only
    + profile_window(escludendo la sottofinestra del giudice).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    profiler = CasualWattLocalEnergyProfiler()

    t0 = time.monotonic()
    wall_start = time.time()
    resp = requests.post(config.OLLAMA_GENERATE_ENDPOINT, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    t1 = time.monotonic()

    text = data.get("response", "") or ""
    p_tok = int(data.get("prompt_eval_count") or data.get("prompt_count") or 0)
    c_tok = int(data.get("eval_count") or 0)
    tokens_estimated = False
    if p_tok == 0 or c_tok == 0:
        tokens_estimated = True
        est_p, est_c = _estimate_tokens(prompt, text)
        if p_tok == 0:
            p_tok = est_p
        if c_tok == 0:
            c_tok = est_c
    resp_data = {
        "text": text,
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "duration_s": round(t1 - t0, 6),
    }
    # prefill/decoding se Ollama li espone (campi nativi dell'API, in ns)
    resp_data["prefill_duration_s"] = float(data.get("prompt_eval_duration") or 0) / 1e9
    resp_data["decoding_duration_s"] = float(data.get("eval_duration") or 0) / 1e9
    resp_data["raw_created_at"] = data.get("created_at", "")
    resp_data["tool_calls"] = 0
    if tokens_estimated:
        resp_data["_tokens_note"] = "input/output token stimati (tiktoken/euristica len//4)"

    local = profiler.profile_window(t0, t1)
    resp_data["_t0"] = t0
    resp_data["_t1"] = t1
    resp_data["_wall_start"] = wall_start
    return resp_data, local


def _ollama_infer_only(model: str, prompt: str, temperature: float,
                       timeout_s: float, num_predict: int = 160):
    """Inferenza Ollama SENZA profiling: ritorna (resp_data, None).

    Il profilo viene preso DOPO la valutazione, scorporando la sottofinestra
    del LLM Judge (benchmark_unified, percorso locale).
    """
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    t0 = time.monotonic()
    wall_start = time.time()
    resp = requests.post(config.OLLAMA_GENERATE_ENDPOINT, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    t1 = time.monotonic()

    text = data.get("response", "") or ""
    p_tok = int(data.get("prompt_eval_count") or data.get("prompt_count") or 0)
    c_tok = int(data.get("eval_count") or 0)
    resp_data = {
        "text": text,
        "prompt_tokens": p_tok,
        "completion_tokens": c_tok,
        "duration_s": round(t1 - t0, 6),
    }
    if p_tok == 0 or c_tok == 0:
        est_p, est_c = _estimate_tokens(prompt, text)
        if p_tok == 0:
            resp_data["prompt_tokens"] = est_p
        if c_tok == 0:
            resp_data["completion_tokens"] = est_c
        resp_data["_tokens_note"] = "input/output token stimati (tiktoken/euristica len//4)"
    resp_data["prefill_duration_s"] = float(data.get("prompt_eval_duration") or 0) / 1e9
    resp_data["decoding_duration_s"] = float(data.get("eval_duration") or 0) / 1e9
    resp_data["raw_created_at"] = data.get("created_at", "")
    resp_data["tool_calls"] = 0
    # finestre della SOLA inferenza (judge escluso dal profiling successivo)
    resp_data["_t0"] = t0
    resp_data["_t1"] = t1
    resp_data["_wall_start"] = wall_start
    return resp_data, None


def query_cloud(provider_cfg: Dict, model: str, prompt: str, temperature: float,
                timeout_s: float, max_tokens: int = 160):
    """POST chat/completions OpenAI-compatible.

    Ritorna (response_data, cloud_result, network_result) come da sezione 9.
    """
    net = NetworkEnergyTracker()
    estimator = CloudEnergyEstimator()

    def _do_request():
        import json as _json

        native = (provider_cfg.get("style") == "anthropic_native"
                  or provider_cfg.get("id") == "anthropic")
        if native:
            # Anthropic Messages API nativa: x-api-key + anthropic-version,
            # max_tokens OBBLIGATORIO, risposta con content[0].text e usage.
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        else:
            body = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
        json_body = _json.dumps(body).encode("utf-8")
        t0 = time.monotonic()
        if native:
            headers = {
                "x-api-key": provider_cfg["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            }
        else:
            headers = {
                "Authorization": f"Bearer {provider_cfg['api_key']}",
                "Content-Type": "application/json",
            }
        r = requests.post(
            provider_cfg["chat_endpoint"],
            headers=headers,
            data=json_body,
            timeout=timeout_s,
        )
        r.raise_for_status()
        j = r.json()
        t1 = time.monotonic()
        if native:
            blocks = j.get("content") or []
            text = "".join(str(b.get("text", "")) for b in blocks
                           if isinstance(b, dict))
            usage = j.get("usage") or {}
            ptok = int(usage.get("input_tokens") or 0)
            ctok = int(usage.get("output_tokens") or 0)
            tool_calls = any(isinstance(b, dict) and b.get("type") == "tool_use"
                             for b in blocks)
        else:
            choice = (j.get("choices") or [{}])[0]
            msg = choice.get("message", {}) or {}
            usage = j.get("usage") or {}
            text = (msg.get("content") or "").strip()
            ptok = int(usage.get("prompt_tokens") or 0)
            ctok = int(usage.get("completion_tokens") or 0)
            tool_calls = bool(msg.get("tool_calls"))
        rd = {
            "text": text,
            "prompt_tokens": ptok,
            "completion_tokens": ctok,
            "duration_s": round(t1 - t0, 6),
            "_t0": t0,
            "_t1": t1,
            "_req_bytes": len(json_body),
            "_resp_bytes": len(r.content),
            "tool_calls": tool_calls,
        }
        return rd

    resp_data, network_result = net.measure(_do_request)

    # energia locale del CLIENT durante la chiamata cloud (CPU/GPU host utente)
    profiler = CasualWattLocalEnergyProfiler()
    client_local = profiler.profile_window(resp_data["_t0"], resp_data["_t1"])

    cloud_est = estimator.estimate(
        provider=provider_cfg["id"],
        model_name=model,
        prompt_tokens=resp_data["prompt_tokens"],
        completion_tokens=resp_data["completion_tokens"],
        duration_s=resp_data["duration_s"],
    )

    resp_data["cloud_energy_j"] = cloud_est.energy_j if cloud_est.energy_j else 0.0
    resp_data["network_energy_j"] = network_result.energy_j
    resp_data["network_upload_bytes"] = network_result.upload_bytes
    resp_data["network_download_bytes"] = network_result.download_bytes

    cloud_result = {
        "estimation": cloud_est,
        "client_local": client_local,
        "provider": provider_cfg["id"],
        "model": model,
        "input_tokens": resp_data["prompt_tokens"],
        "output_tokens": resp_data["completion_tokens"],
    }
    return resp_data, cloud_result, network_result


# ---------------------------------------------------------------------------
# Costruzione record (sezione 11 + regole 12)
# ---------------------------------------------------------------------------
def _na_or(v):
    """None -> 'N/A' esplicito nel CSV (valutazione saltata per riga)."""
    return "N/A" if v is None else v


def _resolve_eval_mode(prompt: Dict, explicit: Optional[str] = None) -> str:
    """Sceglie il regime di valutazione in base ai dati RICEVUTI dal test.

    - ground_truth presente nel dataset esterno   -> 'auto' (GT semantica);
    - item marcato causale (flag/id/contenuto)    -> 'heuristic_keyword_fallback'
      (euristica keyword cause/effect, NON una ground-truth accuracy);
    - altrimenti                                  -> 'skip' (solo energia).
    L'override esplicito ('auto'|'causal'|'skip') ha sempre priorita'; il
    valore storico 'causal' e' accettato come alias del fallback euristico.
    """
    if explicit:
        e = explicit.strip().lower()
        return "heuristic_keyword_fallback" if e == "causal" else e
    if prompt.get("ground_truth"):
        return "auto"
    pid = str(prompt.get("id", "")).lower()
    txt = str(prompt.get("text", "")).lower()
    if prompt.get("causal") or "causal" in pid or ("cause" in txt and "effect" in txt):
        return "heuristic_keyword_fallback"
    return "skip"


def _estimate_judge_energy(t_start: float, t_end: float) -> Optional[float]:
    """Energia REALE della finestra del LLM Judge (B2: niente floor arbitrari).

    Integra la potenza CPU (o legge il contatore Energy cumulato, a seconda
    del backend attivo) ESATTAMENTE sulla sottofinestra [t_start, t_end] del
    giudice e ne sottrae la baseline P_idle * dt con lo stesso metodo del
    profiler. Nessuna stima inventata: se la misurazione locale non puo'
    esprimere la lettura, ritorna None (il runner scrive N/A nel CSV).
    """
    try:
        dur = max(float(t_end) - float(t_start), 0.0)
        if dur <= 0:
            return 0.0
        m = SESSION.source_method
        if m not in ("power-integration", "librehardwaremonitor-energy",
                     "energy-file"):
            return None
        e_raw = SESSION.package_energy_exact_between(t_start, t_end)
        if e_raw is None:
            return None
        p_idle = float(SESSION.idle_power_w or 0.0)
        return round(max(e_raw - p_idle * dur, 0.0), 6)
    except Exception:
        return None


def _basic_record(run_id, session_id, model_name, model_label, provider, mode,
                  ollama_pid, prompt, evalres) -> Dict:
    ci = get_carbon_intensity()
    gt = prompt.get("ground_truth") if isinstance(prompt, dict) else None
    rec = {
        "run_id": run_id,
        "session_id": session_id,
        "timestamp_start": "",
        "timestamp_end": "",
        "model_name": model_name,
        "model_label": model_label,
        "provider": provider,
        "mode": mode,
        "ollama_pid": ollama_pid if ollama_pid is not None else "",
        "prompt_id": prompt["id"],
        "prompt": prompt["text"],
        # tracciabilita' sorgente test (Modalita' di Input Universale)
        "test_source": prompt.get("source", "unknown"),
        "ground_truth": gt if gt not in (None, "") else "N/A",
        "eval_mode": getattr(evalres, "eval_mode", "skipped"),
        # provenienza/declinazione metrica: embedding semantico vs fallback lessicale
        "eval_method": getattr(evalres, "eval_method", ""),
        "semantic_similarity": _na_or(getattr(evalres, "semantic_similarity", None)),
        "lexical_similarity": _na_or(getattr(evalres, "lexical_similarity", None)),
        "semantic_threshold": getattr(evalres, "semantic_threshold", ""),
        # testo esatto generato dal modello (verifica manuale errori/allucinazioni)
        "model_response": "",
        "is_correct": _na_or(evalres.is_correct),
        "causal_accuracy": _na_or(evalres.causal_accuracy),
        "explanation_quality": _na_or(evalres.explanation_quality),
        "cosine_similarity": _na_or(evalres.cosine_sim),
        "n_correct_links": _na_or(evalres.n_correct_links),
        "acc_comp": _na_or(evalres.acc_comp),
        # --- tracciabilita' triple causali / F1 (regime A) ---
        "triples_gt": _na_or(getattr(evalres, "triples_gt", None)),
        "triples_response": _na_or(getattr(evalres, "triples_response", None)),
        "triples_matched": _na_or(getattr(evalres, "triples_matched", None)),
        "f1_precision": _na_or(getattr(evalres, "f1_precision", None)),
        "f1_recall": _na_or(getattr(evalres, "f1_recall", None)),
        "acc_links_basis": getattr(evalres, "acc_links_basis", ""),
        # --- LLM Judge (regime B e arricchimento regime A) ---
        "judge_model": getattr(evalres, "judge_model", ""),
        "evaluated_model": getattr(evalres, "evaluated_model", ""),
        "judge_equals_evaluated": _na_or(getattr(evalres, "judge_equals_evaluated", None)),
        "judge_source": getattr(evalres, "judge_source", ""),
        "tool_calls": 1 if evalres.is_tool else 0,
        "pyagrum_calls": 0,
        "llm_calls": 1,
        "retry_count": 0,
        # default rete/cloud a zero (regola 12.1)
        "network_energy_j": 0.0,
        "cloud_energy_j": 0.0,
        "network_upload_bytes": 0,
        "network_download_bytes": 0,
        "network_total_bytes": 0,
        "network_energy_coefficient_j_per_bit": config.NETWORK_ENERGY_COEFFICIENT_J_PER_BIT,
        "network_measurement_boundary": "not-applicable (local mode)" if mode == "local" else "",
        # carbonio: zona/fonte sempre dichiarate
        "local_carbon_intensity_gco2eq_kwh": ci.gco2eq_per_kwh,
        "local_carbon_intensity_zone": ci.zone,
        "local_carbon_intensity_source": ci.source,
        "local_carbon_intensity_timestamp": datetime.fromtimestamp(
            ci.timestamp, tz=timezone.utc
        ).isoformat(timespec="seconds"),
        "local_emissions_method": "local_energy_kwh x grid carbon intensity (scope-2)",
        "cloud_carbon_intensity_gco2eq_kwh": "",
        "cloud_carbon_intensity_zone": "",
        "cloud_carbon_intensity_source": "",
        "cloud_carbon_intensity_timestamp": "",
        "cloud_emissions_method": "ecologits gwp (server-side, scope-2 incl. PUE)",
        "energibridge_csv": "",
        "notes": [],
    }
    return rec


def _finalize_energy_fields(rec: Dict, local_j: float, network_j: float, cloud_j: float,
                            evalres) -> None:
    """Applica le regole 12.1/12.2 e i derivati ECE/EPCL.

    Con valutazione saltata/N/A (regime senza ground truth) i derivati di
    accuratezza restano 'N/A': mai sostituiti con 0 o valori fittizi.
    """
    rec["local_energy_j"] = round(local_j, 9)
    rec["network_energy_j"] = round(network_j, 9)
    rec["cloud_energy_j"] = round(cloud_j, 9)
    rec["end_to_end_energy_j"] = round(local_j + network_j + cloud_j, 9)

    e2e = rec["end_to_end_energy_j"]
    try:
        out_tok = int(rec.get("output_tokens") or 0)
    except (TypeError, ValueError):
        out_tok = 0
    rec["energy_per_output_token_j"] = round(e2e / out_tok, 9) if out_tok > 0 else ""

    n_correct = getattr(evalres, "n_correct_links", None)
    acc_comp = getattr(evalres, "acc_comp", None)
    is_correct = getattr(evalres, "is_correct", None)
    basis = getattr(evalres, "acc_links_basis", "") or ""

    # --- C1: energy_per_correct_answer_j ed epcl_j_per_link SONO DUE METRICHE
    # DIVERSE (prima avevano la stessa formula):
    #   * energy_per_correct_answer_j = e2e / 1 se is_correct, altrimenti N/A
    #     (per riga; non dipende dai link causali);
    #   * epcl_j_per_link = e2e / n_correct_links calcolata SOLO per task con
    #     triple causali realmente strutturate (basis == 'f1_triples');
    #     altrove N/A con nota (un proxy semantico/lessicale o una struttura
    #     auto-consistente regime B NON sono causal link corretti).
    if is_correct is None:
        rec["energy_per_correct_answer_j"] = "N/A"
    elif is_correct:
        rec["energy_per_correct_answer_j"] = round(e2e, 9)
    else:
        rec["energy_per_correct_answer_j"] = ""  # risposta errata: non definita
    # ECE per joule: accuratezza composita / energia end-to-end (J) — dichiarato
    if acc_comp is None:
        rec["ece_per_joule"] = "N/A"
    else:
        rec["ece_per_joule"] = round(acc_comp / e2e, 9) if e2e > 0 else ""
    # EPCL: Joule per causal link corretto (lower is better)
    if n_correct is None:
        rec["epcl_j_per_link"] = "N/A"
    elif basis != "f1_triples":
        rec["epcl_j_per_link"] = "N/A"
        # FIX: notes e' una stringa (non lista), quindi concatena invece di append
        new_note = (
            f"epcl_j_per_link=N/A: n_correct_links basato su '{basis}' "
            "(proxy/auto-consistenza), non su triple causali verificate contro GT"
        )
        existing = rec.get("notes", "")
        rec["notes"] = f"{existing}; {new_note}" if existing else new_note
    else:
        rec["epcl_j_per_link"] = round(e2e / n_correct, 9) if n_correct > 0 else ""
    # C1: nota che dichiara quale delle due metriche derivate e' valida
    new_note = (
        "metriche derivate: energy_per_correct_answer_j=e2e se is_correct "
        "altrimenti N/A; epcl_j_per_link=e2e/n_correct_links solo con triple "
        "causali F1 vs GT valide"
    )
    existing = rec.get("notes", "")
    rec["notes"] = f"{existing}; {new_note}" if existing else new_note

    # --- C2: componenti di acc_comp sempre separate e dichiarate -----------
    comps = []
    if getattr(evalres, "acc_links", None) is not None:
        comps.append("acc_links")
    if getattr(evalres, "judge_score", None) is not None:
        comps.append("judge_score")
    if getattr(evalres, "cosine_sim", None) is not None:
        comps.append("cosine_similarity")
    rec["acc_comp_components"] = "|".join(comps) if comps else "none"
    try:
        import config as _cfg
        rec["acc_comp_weights"] = (
            f"A:{_cfg.ACC_COMP_WEIGHTS_GT}/B:{_cfg.ACC_COMP_WEIGHTS_NOGT}"
        )
    except Exception:
        rec["acc_comp_weights"] = ""

    rec["local_energy_kwh"] = round(rec["local_energy_j"] / 3_600_000.0, 12)
    rec["cloud_energy_kwh"] = round(rec["cloud_energy_j"] / 3_600_000.0, 12)
    try:
        ci_val = float(rec["local_carbon_intensity_gco2eq_kwh"])
    except (TypeError, ValueError):
        ci_val = 0.0
    rec["local_emissions_gco2eq"] = round(rec["local_energy_kwh"] * ci_val, 9)


# ---------------------------------------------------------------------------
# Runner principale
# ---------------------------------------------------------------------------
def run_unified_benchmark(
    local_models: Optional[List[str]] = None,
    cloud_selection: Optional[List[Dict]] = None,  # [{provider, model}]
    num_prompts: int = config.DEFAULT_NUM_PROMPTS,
    temperature: float = config.DEFAULT_TEMPERATURE,
    timeout_s: float = config.DEFAULT_TIMEOUT_S,
    on_log: Optional[Callable[[str], None]] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    stop_event: Optional[threading.Event] = None,
    run_id: Optional[str] = None,
    session_id: Optional[str] = None,
    skip_idle_calibration: bool = False,
    # --- Modalita' di Input Universale (sorgente dei test) -----------------
    test_mode: str = "default",        # 'csv' | 'manual' | 'default'
    csv_path: Optional[str] = None,    # dataset esterno (es. output MUDILab)
    manual_text: Optional[str] = None, # prompt digitati a mano, uno per riga
    eval_mode_override: Optional[str] = None,  # 'auto'|'causal'|'skip' (opz.)
) -> Dict:
    """Esegue il benchmark completo. Ritorna un summary dict. Mai solleva."""
    local_models = list(local_models or [])
    cloud_selection = list(cloud_selection or [])
    log = on_log or (lambda m: None)
    progress = on_progress or (lambda i, n: None)
    stop_event = stop_event or threading.Event()

    run_id = run_id or datetime.now().strftime("R%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    session_id = session_id or uuid.uuid4().hex[:12]
    started_wall = datetime.now(timezone.utc)

    summary = {
        "run_id": run_id,
        "session_id": session_id,
        "records": 0,
        "errors": 0,
        "cancelled": False,
        "csv_path": str(config.CSV_RESULTS_PATH),
    }

    # ---- sorgente dei test: ricevuta dALL'ESTERNO, mai hardcodata ---------
    try:
        from test_source import load_test_source

        prompts_all, src_err = load_test_source(
            mode=test_mode,
            csv_path=csv_path,
            manual_text=manual_text,
            fallback_config=True,
        )
    except Exception as exc:
        prompts_all, src_err = [], f"modulo test_source non disponibile: {exc}"
    if not prompts_all:
        msg = f"Sorgente test vuota o non valida ({src_err}); uso dataset config"
        log(msg)
        try:
            prompts_all = [
                {"id": p.get("id", f"cfg-{i+1:03d}"), "text": p["text"],
                 "ground_truth": p.get("ground_truth"), "source": "config"}
                for i, p in enumerate(config.load_prompts())
            ]
        except Exception:
            prompts_all = []
    prompts = prompts_all[: max(int(num_prompts), 1)]
    src_kinds = sorted({p.get("source", "?") for p in prompts})
    n_gt = sum(1 for p in prompts if p.get("ground_truth"))
    log(
        f"Sorgente test: {test_mode} ({', '.join(src_kinds)}) — "
        f"{len(prompts)} prompt selezionati su {len(prompts_all)} disponibili; "
        f"ground_truth presente per {n_gt} prompt"
        + (" (valutazione accuratezza -> N/A dove assente)" if n_gt < len(prompts) else "")
    )
    total_tasks = len(prompts) * (len(local_models) + len(cloud_selection))
    done = 0
    records: List[Dict] = []

    # ---- 1. sessione -------------------------------------------------------
    was_running = SESSION.running
    if not was_running:
        SESSION.start()
        time.sleep(SESSION.interval_s * 2)

    # ---- 2. PID Ollama -----------------------------------------------------
    ollama_pids = SESSION.find_ollama_procs()
    primary_pid = ollama_pids[0] if ollama_pids else None
    log(f"PID Ollama rilevato: {primary_pid if primary_pid else 'NESSUNO (ollama offline?)'} "
        f"(albero: {ollama_pids})")

    # ---- 3. calibrazione idle ----------------------------------------------
    if not skip_idle_calibration and SESSION.idle_power_w is None:
        try:
            log(
                "Calibrazione idle in corso (>=30 s x 3 ripetizioni, mediana, "
                "non generare carico)…"
            )
            pw = SESSION.calibrate_idle()
            reps = getattr(SESSION, "_idle_reps", []) or []
            n_samp = getattr(SESSION, "_idle_samples_count", None)
            log(
                f"P_idle calibrata: {pw:.2f} W "
                f"(mediana di {[round(r, 2) for r in reps]} W; "
                f"metodo: {getattr(SESSION, '_idle_mode', '?')}"
                + (f"; campioni power-integration: {n_samp}" if n_samp else "")
                + ")"
            )
        except Exception as exc:
            log(f"AVVISO: calibrazione idle fallita ({exc}); uso baseline dichiarata dal profiler")

    # ---- 4/5/6/7. componenti ------------------------------------------------
    profiler = CasualWattLocalEnergyProfiler()
    net_tracker = NetworkEnergyTracker()
    cloud_estimator = CloudEnergyEstimator()
    _ = get_carbon_intensity()  # CarbonIntensityProvider warm-up
    log(
        f"Sorgente energia package CPU: {SESSION.source_method}"
        + (f" | note: {'; '.join(SESSION.source_notes)}" if SESSION.source_notes else "")
    )

    # Snapshot dei provider al momento dell'avvio, con API key letta LIVE da
    # os.environ (la GUI può aver salvato/aggiornato le chiavi a caldo dopo
    # l'import di config: refresh_provider_keys() risincronizza i flag 'enabled').
    try:
        config.refresh_provider_keys()
    except Exception:
        pass
    providers_by_id = {}
    for pid, cfg in config.CLOUD_PROVIDERS.items():
        live_key = os.getenv(cfg.get("api_key_env", ""), "") or cfg.get("api_key", "")
        c2 = dict(cfg, id=pid)
        c2["api_key"] = live_key
        c2["enabled"] = bool(live_key)
        providers_by_id[pid] = c2

    # ---- 8. modelli locali ---------------------------------------------------
    for model in local_models:
        for pr in prompts:
            if stop_event.is_set():
                summary["cancelled"] = True
                break
            rec = _basic_record(
                run_id, session_id, model, model, "ollama", "local",
                primary_pid, pr, evalres_placeholder(),
            )
            t_wall0 = time.time()
            try:
                # Ricalcola albero processi Ollama a OGNI richiesta (non solo all'avvio)
                current_ollama_pids = SESSION.find_ollama_procs()
                # Leggi cpu_times agli estremi esatti della finestra (non dai campioni)
                from energy.local_energy import CasualWattLocalEnergyProfiler
                cpu_t_start = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(current_ollama_pids)
                
                # 1) inferenza del modello valutato (senza profilo ancora)
                resp_data, _local_raw = _ollama_infer_only(
                    model, pr["text"], temperature, timeout_s
                )
                # Leggi cpu_times a t_end (dopo inferenza, prima del judge)
                cpu_t_end = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(current_ollama_pids)
                direct_cpu_delta = max(cpu_t_end - cpu_t_start, 0.0)
                # 2) valutazione + LLM Judge (eventuale): registra le sue
                #    sottofinestre in llm_judge.LAST_WINDOWS
                _lj.LAST_WINDOWS = []
                evalres = evaluate_response(
                    resp_data["text"], is_tool=False,
                    ground_truth=pr.get("ground_truth"),
                    mode=_resolve_eval_mode(pr, eval_mode_override),
                    question=pr["text"], evaluated_model=model,
                    judge_fn=_judge_via_energy_session,
                    answer_type=pr.get("answer_type", "auto"),
                )
                jw = list(getattr(_lj, "LAST_WINDOWS", []) or [])
                # 3) UNICO profiling: finestra [t0, t_end_effettivo] con la
                #    sottofinestra del giudice SCORPORATA esplicitamente.
                #    Il modello valutato contribuisce solo al segmento inferenza;
                #    judge_energy_j e' l'energia REALE misurata del segmento
                #    giudice (B2: integrazione sulla sua finestra, niente floor).
                t_end_profile = jw[-1][1] if jw else resp_data["_t1"]
                local = CasualWattLocalEnergyProfiler().profile_window(
                    resp_data["_t0"], t_end_profile,
                    ollama_pids=current_ollama_pids,
                    direct_cpu_delta=direct_cpu_delta,
                    exclude_windows=jw if jw else None,
                )
                if jw:
                    je_parts = []
                    for (ja, jb) in jw:
                        je = _estimate_judge_energy(ja, jb)
                        if je is None:
                            je_parts.append(None)
                        else:
                            je_parts.append(je)
                    rec["judge_energy_j"] = (
                        "N/A" if any(p is None for p in je_parts)
                        else round(sum(je_parts), 6)
                    )
                else:
                    rec["judge_energy_j"] = ""
                rec["judge_window_s"] = round(sum(b - a for a, b in jw), 6) if jw else ""
                rec.update(
                    model_response=resp_data["text"],
                    timestamp_start=datetime.fromtimestamp(t_wall0, tz=timezone.utc).isoformat(timespec="seconds"),
                    timestamp_end=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    duration_s=resp_data["duration_s"],
                    input_tokens=resp_data["prompt_tokens"],
                    output_tokens=resp_data["completion_tokens"],
                    total_tokens=resp_data["prompt_tokens"] + resp_data["completion_tokens"],
                    tokens_per_second=(
                        round(resp_data["completion_tokens"] / resp_data["duration_s"], 3)
                        if resp_data["duration_s"] > 0 else ""
                    ),
                    prefill_duration_s=round(resp_data.get("prefill_duration_s", 0.0), 6),
                    decoding_duration_s=round(resp_data.get("decoding_duration_s", 0.0), 6),
                    decoding_tokens_per_second=(
                        round(resp_data["completion_tokens"] / resp_data["decoding_duration_s"], 3)
                        if resp_data.get("decoding_duration_s", 0) > 0 else ""
                    ),
                    # campi energetici (regola 12.1/12.3)
                    package_energy_j=local.package_energy_j,
                    idle_power_w=local.idle_power_w,
                    baseline_energy_j=local.baseline_energy_j,
                    active_energy_j=local.active_energy_j,
                    ollama_active_energy_j=local.ollama_active_energy_j,
                    cpu_time_share=local.cpu_time_share,
                    gpu_available=local.gpu_available,
                    gpu_device_index=("" if local.gpu_device_index is None else local.gpu_device_index),
                    gpu_board_energy_j=local.gpu_board_energy_j,
                    gpu_energy_attributed_j=local.gpu_energy_attributed_j,
                    gpu_utilization_share=local.gpu_utilization_share,
                    cpu_attribution_method=local.cpu_attribution_method,
                    gpu_attribution_method=local.gpu_attribution_method,
                    measurement_boundary=local.measurement_boundary,
                    # B3/A1: provenienza P_idle per riga (calibrated|session|uncalibrated)
                    idle_provenance=getattr(local, "idle_provenance", "") or "",
                    # B1: origine lettura finestra package (exact-counter|samples-fallback)
                    package_window_source=getattr(local, "package_window_source", "") or "",
                    # A2/A3: campi diagnostici GPU/iGPU (mai sommati a local_energy_j)
                    gpu_process_energy_j=_na_or(getattr(local, "gpu_process_energy_j", None)),
                    igpu_energy_j=_na_or(getattr(local, "igpu_energy_j", None)),
                    # Punto 2: provenienza idle GPU (calibrated|missing)
                    gpu_idle_provenance=getattr(local, "gpu_idle_provenance", "") or "",
                    # Diagnostica cpu-time-share (per riga)
                    ollama_pids_used=getattr(local, "ollama_pids_used", "") or "",
                    d_ollama_cpu_s=getattr(local, "d_ollama_cpu_s", 0.0),
                    d_busy_s=getattr(local, "d_busy_s", 0.0),
                    n_samples_in_window=getattr(local, "n_samples_in_window", 0),
                )
                # riscrive qualita' con valutazione reale (N/A se saltata)
                rec.update(
                    eval_mode=evalres.eval_mode,
                    is_correct=_na_or(evalres.is_correct),
                    causal_accuracy=_na_or(evalres.causal_accuracy),
                    explanation_quality=_na_or(evalres.explanation_quality),
                    cosine_similarity=_na_or(evalres.cosine_sim),
                    n_correct_links=_na_or(evalres.n_correct_links),
                    acc_comp=_na_or(evalres.acc_comp),
                    answer_type=getattr(evalres, "answer_type", "auto"),
                    extracted_answer=_na_or(getattr(evalres, "extracted_answer", None)),
                )
                # regola 12.1: rete e cloud ZERO; locale = solo Ollama attiva+GPU attribuita
                local_j = local.ollama_active_energy_j + local.gpu_energy_attributed_j
                _finalize_energy_fields(rec, local_j, 0.0, 0.0, evalres)
                note_parts = list(local.notes) + list(evalres.notes)
                if resp_data.get("_tokens_note"):
                    note_parts.append(resp_data["_tokens_note"])
                rec["notes"] = "; ".join(note_parts)
                log(
                    f"[OK local] {model} | {pr['id']} | {resp_data['duration_s']:.2f}s | "
                    f"E_ollama={local.ollama_active_energy_j:.2f} J "
                    f"(share {local.cpu_time_share:.2f}) | acc={_acc_log(evalres)}"
                )
            except Exception as exc:
                summary["errors"] += 1
                # Usa una lista per le note, poi fai join alla fine
                note_parts = [f"ERRORE richiesta locale: {type(exc).__name__}: {exc}"]
                rec.update(
                    timestamp_start=datetime.fromtimestamp(t_wall0, tz=timezone.utc).isoformat(timespec="seconds"),
                    timestamp_end=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                _finalize_energy_fields(rec, 0.0, 0.0, 0.0, evalres_placeholder())
                # Unisci le note alla fine (dopo _finalize_energy_fields)
                existing_notes = rec.get("notes", "")
                if existing_notes:
                    note_parts.insert(0, existing_notes)
                rec["notes"] = "; ".join(note_parts)
                log(f"[ERRORE local] {model} | {pr['id']} | {type(exc).__name__}: {exc}")
            records.append(rec)
            done += 1
            progress(done, total_tasks)
            _flush_incremental(records, log)
        if summary["cancelled"]:
            break

    # ---- 9. modelli cloud ----------------------------------------------------
    if not summary["cancelled"]:
        for sel in cloud_selection:
            prov_id = sel.get("provider")
            model = sel.get("model")
            pcfg = providers_by_id.get(prov_id)
            if not pcfg or not pcfg.get("api_key"):
                log(f"[SKIP cloud] provider '{prov_id}' senza API key configurata")
                continue
            for pr in prompts:
                if stop_event.is_set():
                    summary["cancelled"] = True
                    break
                rec = _basic_record(
                    run_id, session_id, model, f"{prov_id} | {model}", prov_id,
                    "cloud", primary_pid, pr, evalres_placeholder(),
                )
                t_wall0 = time.time()
                try:
                    resp_data, cloud_res, net_res = query_cloud(
                        pcfg, model, pr["text"], temperature, timeout_s
                    )
                    evalres = evaluate_response(
                        resp_data["text"], is_tool=bool(resp_data.get("tool_calls")),
                        ground_truth=pr.get("ground_truth"),
                        mode=_resolve_eval_mode(pr, eval_mode_override),
                        judge_fn=_judge_via_energy_session,
                        answer_type=pr.get("answer_type", "auto"),
                    )
                    client_local = cloud_res["client_local"]
                    est = cloud_res["estimation"]

                    rec.update(
                        model_response=resp_data["text"],
                        timestamp_start=datetime.fromtimestamp(t_wall0, tz=timezone.utc).isoformat(timespec="seconds"),
                        timestamp_end=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        duration_s=resp_data["duration_s"],
                        input_tokens=resp_data["prompt_tokens"],
                        output_tokens=resp_data["completion_tokens"],
                        total_tokens=resp_data["prompt_tokens"] + resp_data["completion_tokens"],
                        tokens_per_second=(
                            round(resp_data["completion_tokens"] / resp_data["duration_s"], 3)
                            if resp_data["duration_s"] > 0 else ""
                        ),
                        tool_calls=1 if resp_data.get("tool_calls") else 0,
                        # client-local (stessa formula causale, applicata al PC utente)
                        package_energy_j=client_local.package_energy_j,
                        idle_power_w=client_local.idle_power_w,
                        baseline_energy_j=client_local.baseline_energy_j,
                        active_energy_j=client_local.active_energy_j,
                        ollama_active_energy_j=client_local.ollama_active_energy_j,
                        cpu_time_share=client_local.cpu_time_share,
                        gpu_available=client_local.gpu_available,
                        gpu_board_energy_j=client_local.gpu_board_energy_j,
                        gpu_energy_attributed_j=client_local.gpu_energy_attributed_j,
                        gpu_utilization_share=client_local.gpu_utilization_share,
                        # Punto 2: provenienza idle GPU (calibrated|missing)
                        gpu_idle_provenance=(
                            getattr(client_local, "gpu_idle_provenance", "") or ""
                        ),
                        cpu_attribution_method=client_local.cpu_attribution_method,
                        gpu_attribution_method=client_local.gpu_attribution_method,
                        measurement_boundary=(
                            client_local.measurement_boundary
                            + " | network: " + net_res.measurement_boundary
                            + " | cloud: server-side ecologits"
                        ),
                        # rete (regola 12.2)
                        network_upload_bytes=net_res.upload_bytes,
                        network_download_bytes=net_res.download_bytes,
                        network_total_bytes=net_res.total_bytes,
                        network_energy_coefficient_j_per_bit=net_res.coefficient_j_per_bit,
                        network_measurement_boundary=net_res.measurement_boundary,
                        # cloud
                        cloud_energy_method=est.method,
                        cloud_provider=prov_id,
                        cloud_model=model,
                        cloud_input_tokens=resp_data["prompt_tokens"],
                        cloud_output_tokens=resp_data["completion_tokens"],
                        cloud_estimation_boundary=(
                            "ecologits server-side estimate; hw-profile: " + est.hw_profile
                            + "; zone: " + est.country_code
                        ),
                        is_correct=_na_or(evalres.is_correct),
                        causal_accuracy=_na_or(evalres.causal_accuracy),
                        explanation_quality=_na_or(evalres.explanation_quality),
                        cosine_similarity=_na_or(evalres.cosine_sim),
                        n_correct_links=_na_or(evalres.n_correct_links),
                        acc_comp=_na_or(evalres.acc_comp),
                        eval_mode=evalres.eval_mode,
                        eval_method=getattr(evalres, "eval_method", ""),
                        semantic_similarity=_na_or(
                            getattr(evalres, "semantic_similarity", None)),
                        lexical_similarity=_na_or(
                            getattr(evalres, "lexical_similarity", None)),
                        semantic_threshold=getattr(evalres, "semantic_threshold", ""),
                    )
                    cloud_j = est.energy_j or 0.0
                    if est.energy_j is None:
                        rec["cloud_energy_method"] = est.method
                        rec["notes"] = "; ".join(est.notes)
                    # carbonio cloud: se EcoLogits ha fornito gwp lo riportiamo
                    if est.carbon_gco2eq is not None:
                        rec["cloud_emissions_gco2eq"] = est.carbon_gco2eq
                        rec["cloud_carbon_intensity_gco2eq_kwh"] = (
                            round(est.carbon_gco2eq / (est.energy_j / 3_600_000.0), 3)
                            if est.energy_j else ""
                        )
                        rec["cloud_carbon_intensity_zone"] = est.country_code
                        rec["cloud_carbon_intensity_source"] = "ecologits-electricity-mix-repository"
                        rec["cloud_carbon_intensity_timestamp"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

                    local_j = (
                        client_local.ollama_active_energy_j
                        + client_local.gpu_energy_attributed_j
                    )
                    _finalize_energy_fields(rec, local_j, net_res.energy_j, cloud_j, evalres)
                    extra = "; ".join(client_local.notes + net_res.notes + est.notes)
                    rec["notes"] = (rec["notes"] + "; " + extra).strip("; ")
                    log(
                        f"[OK cloud] {prov_id}/{model} | {pr['id']} | {resp_data['duration_s']:.2f}s | "
                        f"cloud={cloud_j:.3f} J net={net_res.energy_j:.5f} J "
                        f"client={local_j:.2f} J | acc={_acc_log(evalres)}"
                    )
                except Exception as exc:
                    summary["errors"] += 1
                    rec.update(
                        timestamp_start=datetime.fromtimestamp(t_wall0, tz=timezone.utc).isoformat(timespec="seconds"),
                        timestamp_end=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        notes=f"ERRORE richiesta cloud: {type(exc).__name__}: {exc}",
                    )
                    _finalize_energy_fields(rec, 0.0, 0.0, 0.0, evalres_placeholder())
                    log(f"[ERRORE cloud] {prov_id}/{model} | {pr['id']} | {type(exc).__name__}: {exc}")
                records.append(rec)
                done += 1
                progress(done, total_tasks)
                _flush_incremental(records, log)
            if summary["cancelled"]:
                break

    # ---- 11. export finale ---------------------------------------------------
    finished_wall = datetime.now(timezone.utc)
    written = 0
    try:
        written = export_results_csv(records, config.CSV_RESULTS_PATH, mode="w")
        log(f"CSV aggiornato: {config.CSV_RESULTS_PATH} ({written} righe cumulative)")
    except Exception as exc:
        log(f"ERRORE export CSV: {exc}")
        summary["errors"] += 1

    try:
        meta = {
            "run_id": run_id,
            "started_at": started_wall.isoformat(timespec="seconds"),
            "finished_at": finished_wall.isoformat(timespec="seconds"),
            "app_version": APP_VERSION,
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "cpu_model": platform.processor() or platform.machine(),
            "cpu_logical_cores": platform.os.cpu_count(),
            "gpu_nvml_name": SESSION._gpu.name or "",
            "gpu_nvml_available": SESSION._gpu.available,
            "cpu_energy_source_method": SESSION.source_method,
            "cpu_energy_source_notes": "; ".join(SESSION.source_notes),
            "ollama_endpoint": config.OLLAMA_API_URL,
            "ollama_models_selected": ";".join(local_models),
            "cloud_models_selected": ";".join(f"{s.get('provider')}/{s.get('model')}" for s in cloud_selection),
            "num_prompts": len(prompts),
            "test_source_mode": test_mode,
            "test_source_csv": str(csv_path or ""),
            "test_source_items_total": len(prompts_all),
            "test_ground_truth_count": n_gt,
            "temperature": temperature,
            "timeout_s": timeout_s,
            "idle_power_w": SESSION.idle_power_w,
            "idle_calibrated_at": SESSION.calibrated_at,
            "ecologits_version": _ecologits_version(),
            "electricity_maps_used": bool(os.getenv("ELECTRICITY_MAPS_API_TOKEN", "")),
            "records_written": len(records),
            "results_csv": str(config.CSV_RESULTS_PATH),
            "notes": "cancelled" if summary["cancelled"] else "completed",
        }
        write_run_metadata(meta, config.CSV_RUN_METADATA_PATH)
    except Exception as exc:
        log(f"ERRORE run metadata: {exc}")

    summary["records"] = len(records)
    if not was_running:
        SESSION.stop()
    return summary


def evalres_placeholder():
    """Placeholder N/A per record pre-richiesta / percorsi d'errore."""
    from evaluator import evaluate_skipped

    return evaluate_skipped("richiesta non completata")


def _acc_log(evalres) -> str:
    """Rappresentazione log-friendly dell'accuratezza (N-A-aware)."""
    v = evalres.causal_accuracy
    if v is None:
        return "N/A"
    return f"{v:.2f} ({getattr(evalres, 'eval_mode', '?')})"


def _flush_incremental(records: List[Dict], log) -> None:
    """Ogni tot record, salva un checkpoint incrementale (anti-crash)."""
    n = len(records)
    if n and n % 5 == 0:
        try:
            export_results_csv(records, config.CSV_RESULTS_PATH, mode="w")
        except Exception as exc:
            log(f"checkpoint CSV fallito: {exc}")


def _ecologits_version() -> str:
    try:
        import ecologits

        return getattr(ecologits, "__version__", "unknown")
    except Exception:
        return "not-installed"
