# -*- coding: utf-8 -*-
from __future__ import annotations
import time
from typing import Dict, Any, Optional

# Assumiamo l'import del tuo singleton di sessione di CasualWatt
from .energy_session import SESSION

class ProfileMetricsEngine:
    """Motore metrologico ottimizzato per l'elaborazione dei Joule per Token."""

    @staticmethod
    def compute_exact_joules_per_token(metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Ottimizza, valida e calcola l'efficienza energetica della generazione (Decode).
        
        Applica il principio di granularità metrologica: se il numero di token generati
        è troppo basso o la finestra temporale è inferiore al limite di campionamento
        psutil, applica strategie di protezione per evitare divisioni per zero o
        valori di efficienza distorti.
        """
        # Estrazione atomica dei dati per evitare overhead di lookup nei cicli intensivi
        tokens = metrics.get("tokens_generated", 0)
        cpu_j = metrics.get("cpu_energy_generation_j")
        gpu_j = metrics.get("gpu_energy_dynamic_generation_j", 0.0)
        duration = metrics.get("duration_generation_s", 0.0)

        # Inizializzazione dei campi di output
        metrics["joules_per_token"] = None
        metrics["tokens_per_second"] = None
        metrics["generation_efficiency_status"] = "invalid"

        # 1. Validazione della finestra temporale e dei token
        if tokens <= 0:
            metrics["generation_efficiency_status"] = "insufficient_tokens"
            return metrics
            
        if duration <= 1e-4:  # Finestra temporale infinitesima (modello istantaneo)
            metrics["generation_efficiency_status"] = "duration_too_short_for_telemetry"
            return metrics

        # Calcolo del throughput nominale
        metrics["tokens_per_second"] = round(tokens / duration, 2)

        # 2. Controllo dell'integrità del contatore CPU (EMI / RAPL)
        if cpu_j is None:
            metrics["generation_efficiency_status"] = "cpu_hardware_counter_unavailable"
            return metrics

        if cpu_j < 0 or gpu_j < 0:
            metrics["generation_efficiency_status"] = "negative_energy_delta_counter_reset"
            return metrics

        # 3. Calcolo dell'energia totale dinamica a regime di generazione
        # (La CPU è già proporzionale e la GPU è già depurata dall'idle tramite settle_idle)
        total_dynamic_energy_j = cpu_j + gpu_j
        
        # 4. Calcolo finale ottimizzato della metrica cardine (J/Token)
        metrics["joules_per_token"] = round(total_dynamic_energy_j / tokens, 6)
        metrics["generation_efficiency_status"] = "success"

        return metrics

    @classmethod
    def process_window(cls, t_start: float, t_end: float, tokens: int, 
                       gpu_idle_w: float = 0.0) -> Dict[str, Any]:
        """Elabora una qualsiasi finestra di inferenza passata calcolando l'impatto atomico.
        
        Questo metodo ottimizza le performance estraendo i delta dei campioni
        direttamente dalla memoria del buffer circolare senza allocazioni ridondanti.
        """
        dt = max(t_end - t_start, 1e-6)
        
        # Sfrutta il metodo esatto B1 a bordi esatti di CasualWatt
        cpu_j = SESSION.package_energy_exact_between(t_start, t_end)
        
        # Estrazione ad accesso diretto della telemetria GPU dai campioni in memoria
        samples = SESSION.samples_between(t_start, t_end)
        gpu_j_raw = 0.0
        
        if len(samples) >= 2:
            s_first, s_last = samples[0], samples[-1]
            if s_first.gpu_energy_mj is not None and s_last.gpu_energy_mj is not None:
                gpu_j_raw = max((s_last.gpu_energy_mj - s_first.gpu_energy_mj) / 1000.0, 0.0)
            else:
                # Fallback rapido basato sull'integrale discreto se il contatore cumulativo fallisce
                valid_powers = [s.gpu_power_w for s in samples if s.gpu_power_w is not None]
                if valid_powers:
                    gpu_j_raw = (sum(valid_powers) / len(valid_powers)) * dt

        # Scorporo immediato della baseline idle GPU calcolata scientificamente
        gpu_j_dynamic = max(gpu_j_raw - (gpu_idle_w * dt), 0.0)

        raw_metrics = {
            "tokens_generated": tokens,
            "duration_generation_s": dt,
            "cpu_energy_generation_j": cpu_j,
            "gpu_energy_dynamic_generation_j": gpu_j_dynamic
        }

        return cls.compute_exact_joules_per_token(raw_metrics)
