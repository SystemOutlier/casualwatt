# -*- coding: utf-8 -*-
import time
import requests
import json
from typing import Dict, Any, Optional

# Assumiamo l'import del tuo singleton di sessione
from energy.energy_session import SESSION

def profile_ollama_stream(model_name: str, prompt: str, host: str = "http://localhost:11434") -> Dict[str, Any]:
    """Invia una richiesta in streaming a Ollama e separa nettamente 
    l'energia e i tempi del TTFT da quelli della generazione successiva.
    """
    if not SESSION.running:
        SESSION.start()

    url = f"{host}/api/generate"
    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": True
    }

    # --- FASE 0: Stato Iniziale ---
    # Cattura l'albero dei processi, i contatori EMI/RAPL e i tempi pre-richiesta
    edge_start = SESSION.read_measurement_edge(include_counter=True)
    t_start = edge_start["t_counter_mono"]

    # Invia la richiesta HTTP
    response = requests.post(url, json=payload, stream=True)
    response.raise_for_status()
    
    response_iterator = response.iter_lines()
    
    # --- FASE 1: Intercettazione Primo Token (TTFT) ---
    first_token_data = None
    for line in response_iterator:
        if line:
            first_token_data = json.loads(line.decode('utf-8'))
            break # Abbiamo ricevuto il PRIMO token!

    # Bordo di misura IMMEDIATO al millisecondo sul primo token
    edge_ttft = SESSION.read_measurement_edge(include_counter=True)
    t_ttft = edge_ttft["t_counter_mono"]

    # --- FASE 2: Raccolta Token Successivi (Generazione) ---
    total_tokens = 1
    final_data = first_token_data

    for line in response_iterator:
        if line:
            token_data = json.loads(line.decode('utf-8'))
            if not token_data.get("done", False):
                total_tokens += 1
            else:
                final_data = token_data # Il record finale di Ollama contiene le statistiche native

    # Bordo di misura FINALE al termine dello stream
    edge_end = SESSION.read_measurement_edge(include_counter=True)
    t_end = edge_end["t_counter_mono"]

    # --- FASE 3: Calcolo dell'Energia Esatta tramite il tuo Contatore Hardware ---
    # Sfrutta il tuo metodo esatto B1 che bypassa le stime approssimative
    e_ttft_total_j = SESSION.package_energy_exact_between(t_start, t_ttft)
    e_gen_total_j = SESSION.package_energy_exact_between(t_ttft, t_end)

    # --- FASE 4: Attribuzione Proporzionale (CPU) e Scorporo Idle (GPU) ---
    # Durate reali delle due finestre
    dt_ttft = max(t_ttft - t_start, 1e-6)
    dt_gen = max(t_end - t_ttft, 1e-6)

    # Calcolo dell'energia dinamica della GPU (usando la calibrazione idle sviluppata prima)
    p_gpu_idle = getattr(SESSION, "gpu_idle_power_w", 0.0)
    
    # Recuperiamo i delta mJ dai campioni della sessione per le due finestre
    # Nota: Nel tuo framework, per i calcoli esatissimi sulle finestre brevi trascorse,
    # puoi estendere il calcolo leggendo il delta cumulativo gpu_energy_mj nei campioni.
    samples_ttft = SESSION.samples_between(t_start, t_ttft)
    samples_gen = SESSION.samples_between(t_ttft, t_end)

    def _get_gpu_delta_j(samples) -> float:
        if len(samples) >= 2 and samples[-1].gpu_energy_mj is not None and samples[0].gpu_energy_mj is not None:
            return max((samples[-1].gpu_energy_mj - samples[0].gpu_energy_mj) / 1000.0, 0.0)
        return 0.0

    gpu_j_ttft = _get_gpu_delta_j(samples_ttft)
    gpu_j_gen = _get_gpu_delta_j(samples_gen)

    # Risultati finali strutturati per l'esportazione scientifica
    metrics = {
        "model": model_name,
        "tokens_generated": total_tokens,
        # Tempistiche
        "duration_ttft_s": round(dt_ttft, 4),
        "duration_generation_s": round(dt_gen, 4),
        "total_duration_s": round(t_end - t_start, 4),
        # Metriche Energetiche CPU (Package intero)
        "cpu_energy_ttft_j": round(e_ttft_total_j, 4) if e_ttft_total_j is not None else None,
        "cpu_energy_generation_j": round(e_gen_total_j, 4) if e_gen_total_j is not None else None,
        # Metriche Energetiche GPU (Dinamica, depurata dall'idle)
        "gpu_energy_dynamic_ttft_j": round(max(gpu_j_ttft - (p_gpu_idle * dt_ttft), 0.0), 4),
        "gpu_energy_dynamic_generation_j": round(max(gpu_j_gen - (p_gpu_idle * dt_gen), 0.0), 4),
        # Statistiche native Ollama (per validazione incrociata)
        "ollama_native_eval_count": final_data.get("eval_count"),
        "ollama_native_prompt_eval_duration_ms": final_data.get("prompt_eval_duration", 0) / 1e6,
        "ollama_native_eval_duration_ms": final_data.get("eval_duration", 0) / 1e6,
    }

    # Efficienza di Generazione Pura (Joule/Token) - La metrica che cercavi
    if total_tokens > 1 and metrics["cpu_energy_generation_j"] is not None:
        total_gen_energy = metrics["cpu_energy_generation_j"] + metrics["gpu_energy_dynamic_generation_j"]
        metrics["joules_per_token"] = round(total_gen_energy / total_tokens, 6)
    else:
        metrics["joules_per_token"] = None

    return metrics
