# -*- coding: utf-8 -*-
"""multi_prompt.py — Estensione del runner v4 per il multi-prompt.

Ispirato a Evalita-LLM: eseguire lo stesso task con N prompt diversi e
aggregare l'energia con la stessa statistica già implementata (Wilson CI,
bootstrap a cluster).

Il multi-prompt è un'estensione del runner v4, non una modifica: il runner
esistente resta intatto, e questo modulo legge il task da YAML e esegue
il loop sulle varianti del prompt.

La sensibilità energetica al prompt è una nuova metrica derivata:
`energy_prompt_sensitivity = std(E_prompt1, E_prompt2, ...)` che quantifica
quanto l'energia dipende dalla formulazione, non dal modello.
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Any

from task_definition import TaskDefinition


def run_multi_prompt(
    task: TaskDefinition,
    results_dir: Path,
    on_log: Optional[callable] = None,
) -> Dict[str, Any]:
    """Esegue un task con multi-prompt e aggrega l'energia.
    
    Args:
        task: TaskDefinition con le varianti del prompt
        results_dir: directory dove salvare i risultati
        on_log: funzione di logging opzionale
        
    Returns:
        Dizionario con i risultati aggregati, incluse le metriche di
        sensibilità energetica al prompt
    """
    log = on_log or (lambda msg: None)
    
    log(f"[MULTI-PROMPT] Task: {task.task_name}")
    log(f"[MULTI-PROMPT] Modello: {task.model}")
    log(f"[MULTI-PROMPT] Varianti del prompt: {len(task.prompt_variants)}")
    
    # Risultati per ogni variante del prompt
    prompt_results: List[Dict[str, Any]] = []
    
    for i, prompt in enumerate(task.prompt_variants):
        log(f"[MULTI-PROMPT] Variante {i+1}/{len(task.prompt_variants)}: {prompt[:50]}...")
        
        # Qui verrebbe chiamata la funzione del runner v4 per eseguire
        # il blocco con questo prompt specifico. Per ora, restituiamo
        # una struttura vuota che verrà popolata dal runner.
        result = {
            'prompt_variant_index': i,
            'prompt': prompt,
            'task_name': task.task_name,
            'model': task.model,
            'energy_j': None,  # Popolato dal runner v4
            'active_energy_j': None,  # Popolato dal runner v4
            'baseline_energy_j': None,  # Popolato dal runner v4
        }
        prompt_results.append(result)
    
    # Aggregazione dell'energia con la statistica già implementata
    aggregated = aggregate_prompt_energy(prompt_results, log)
    
    # Salva i risultati in JSON
    output_file = results_dir / f"{task.task_name}_multi_prompt_results.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(aggregated, f, indent=2, ensure_ascii=False)
    
    log(f"[MULTI-PROMPT] Risultati salvati in {output_file}")
    
    return aggregated


def aggregate_prompt_energy(
    prompt_results: List[Dict[str, Any]],
    log: Optional[callable] = None,
) -> Dict[str, Any]:
    """Aggrega l'energia delle varianti del prompt.
    
    Calcola la sensibilità energetica al prompt:
    `energy_prompt_sensitivity = std(E_prompt1, E_prompt2, ...)`
    
    Args:
        prompt_results: lista dei risultati per ogni variante del prompt
        log: funzione di logging opzionale
        
    Returns:
        Dizionario con le metriche aggregate
    """
    log = log or (lambda msg: None)
    
    # Estrae le energie attive dalle varianti del prompt
    energies = [
        result['active_energy_j']
        for result in prompt_results
        if result.get('active_energy_j') is not None
    ]
    
    if not energies:
        log("[MULTI-PROMPT] Nessuna energia attiva disponibile per l'aggregazione")
        return {
            'task_name': prompt_results[0]['task_name'] if prompt_results else None,
            'model': prompt_results[0]['model'] if prompt_results else None,
            'prompt_variant_count': len(prompt_results),
            'energy_prompt_sensitivity': {
                'std_energy_j': None,
                'cv': None,
                'max_min_ratio': None,
            },
            'mean_active_energy_j': None,
            'std_active_energy_j': None,
            'min_active_energy_j': None,
            'max_active_energy_j': None,
            'prompt_results': prompt_results,
        }
    
    # Calcola le statistiche descrittive
    mean_energy = statistics.mean(energies)
    std_energy = statistics.stdev(energies) if len(energies) > 1 else 0.0
    min_energy = min(energies)
    max_energy = max(energies)
    
    # Calcola la sensibilità con le tre metriche
    sensitivity = calculate_energy_prompt_sensitivity(energies)
    
    log(f"[MULTI-PROMPT] Energia attiva: media={mean_energy:.4f} J, "
        f"std={std_energy:.4f} J, min={min_energy:.4f} J, max={max_energy:.4f} J")
    
    if sensitivity['cv'] is not None:
        log(f"[MULTI-PROMPT] CV={sensitivity['cv']:.4f}, "
            f"Max/Min={sensitivity['max_min_ratio']:.4f}")
    
    return {
        'task_name': prompt_results[0]['task_name'],
        'model': prompt_results[0]['model'],
        'prompt_variant_count': len(prompt_results),
        'energy_prompt_sensitivity': sensitivity,
        'mean_active_energy_j': mean_energy,
        'std_active_energy_j': std_energy,
        'min_active_energy_j': min_energy,
        'max_active_energy_j': max_energy,
        'prompt_results': prompt_results,
    }


def calculate_energy_prompt_sensitivity(
    energies: List[float],
) -> Dict[str, Optional[float]]:
    """Calcola la sensibilità energetica al prompt.
    
    Restituisce tre metriche complementari:
    
    1. `std_energy_j`: deviazione standard assoluta, misura la variabilità
       in Joule. Utile per un singolo modello, ma non confrontabile
       cross-modello perché un LLM da 70B consuma ordini di grandezza
       più di un SLM da 3B.
    
    2. `cv` (Coefficient of Variation): σ/μ, normalizza la deviazione
       standard rispetto alla media. Permette il confronto equo: se un SLM
       ha CV = 0.15 e un LLM ha CV = 0.08, l'SLM è più sensibile alla
       formulazione del prompt rispetto al suo consumo medio, anche se la
       deviazione assoluta è minore.
    
    3. `max_min_ratio`: rapporto massimo/minimo, misura l'ampiezza
       conservativa della variabilità. Un rapporto 2.0 significa che la
       variante più costosa consuma il doppio della più economica.
    
    Args:
        energies: lista delle energie attive per ogni variante del prompt
        
    Returns:
        Dizionario con le tre metriche, o None se meno di 2 campioni.
        CV è None se la media è zero o negativa (caso patologico).
    """
    if len(energies) < 2:
        return {
            'std_energy_j': None,
            'cv': None,
            'max_min_ratio': None,
        }
    
    mean_energy = statistics.mean(energies)
    std_energy = statistics.stdev(energies)
    min_energy = min(energies)
    max_energy = max(energies)
    
    # CV è definito solo se la media è strettamente positiva
    cv = std_energy / mean_energy if mean_energy > 0.0 else None
    
    # Max/min ratio è definito solo se il minimo è strettamente positivo
    max_min_ratio = max_energy / min_energy if min_energy > 0.0 else None
    
    return {
        'std_energy_j': std_energy,
        'cv': cv,
        'max_min_ratio': max_min_ratio,
    }
