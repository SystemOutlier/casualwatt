# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import os
import threading
from datetime import datetime, timezone
from typing import Dict, Any

class CasualWattCSVLogger:
    """Logger thread-safe per la memorizzazione scientifica delle metriche di CasualWatt.
    
    Gestisce la scrittura incrementale, l'inizializzazione automatica degli header 
    e l'esportazione atomica per prevenire corruzioni di dati durante benchmark intensivi.
    """

    def __init__(self, output_dir: str = "./experiment_results", filename: str = "ollama_perf_v4.csv"):
        self.output_dir = output_dir
        self.filepath = os.path.join(output_dir, filename)
        self._lock = threading.Lock()
        
        # Definizione rigorosa dei canali e delle metriche (in linea con la Spec v4)
        self.headers = [
            "timestamp_utc",
            "model_name",
            "tokens_generated",
            "tokens_per_second",
            "generation_status",
            # Canali Temporali (s)
            "duration_ttft_s",
            "duration_generation_s",
            "duration_total_s",
            # Canali Energetici CPU (Joule - Bordo Esatto ed Attribuzione)
            "cpu_energy_exact_ttft_j",
            "cpu_energy_exact_generation_j",
            "cpu_energy_attributed_ttft_j",
            "cpu_energy_attributed_generation_j",
            # Canali Energetici GPU (Joule - Dinamica depurata dall'idle)
            "gpu_energy_dynamic_ttft_j",
            "gpu_energy_dynamic_generation_j",
            # Metrica Cardine di Efficienza (J/Token)
            "joules_per_token",
            # Metadati Hardware e Baseline (W)
            "cpu_idle_baseline_w",
            "gpu_idle_baseline_w",
            "energy_calculation_method"
        ]
        
        self._ensure_file_initialized()

    def _ensure_file_initialized(self) -> None:
        """Crea la directory e scrive gli header del CSV se il file non esiste."""
        with self._lock:
            if not os.path.exists(self.output_dir):
                os.makedirs(self.output_dir, exist_ok=True)
            
            if not os.path.exists(self.filepath):
                with open(self.filepath, mode="w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.headers)

    def log_metrics(self, raw_metrics: Dict[str, Any], session_info: Any) -> str:
        """Mappa, pulisce e scrive una riga nel CSV in modo atomico.
        
        Tratta i valori mancanti inserendo 'N/A' in conformità con il principio
        di trasparenza metrologica del framework (MEASURED_METHODS), evitando zeri falsi.
        """
        # Creazione del timestamp di parete ISO UTC sincronizzato al millisecondo
        now_utc = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        
        # Recupero delle baseline e dei metodi dal singleton SESSION passato
        cpu_idle = getattr(session_info, "idle_power_w", None)
        gpu_idle = getattr(session_info, "gpu_idle_power_w", None)
        method = getattr(session_info, "source_method", "unavailable")

        # Mappatura sicura del dizionario per garantire l'allineamento con le colonne
        row_dict = {
            "timestamp_utc": now_utc,
            "model_name": raw_metrics.get("model", "unknown"),
            "tokens_generated": raw_metrics.get("tokens_generated", 0),
            "tokens_per_second": raw_metrics.get("tokens_per_second"),
            "generation_status": raw_metrics.get("generation_efficiency_status", "invalid"),
            
            "duration_ttft_s": raw_metrics.get("duration_ttft_s"),
            "duration_generation_s": raw_metrics.get("duration_generation_s"),
            "duration_total_s": raw_metrics.get("total_duration_s"),
            
            "cpu_energy_exact_ttft_j": raw_metrics.get("cpu_energy_ttft_j"),
            "cpu_energy_exact_generation_j": raw_metrics.get("cpu_energy_generation_j"),
            "cpu_energy_attributed_ttft_j": raw_metrics.get("cpu_energy_attributed_ttft_j"),
            "cpu_energy_attributed_generation_j": raw_metrics.get("cpu_energy_attributed_generation_j"),
            
            "gpu_energy_dynamic_ttft_j": raw_metrics.get("gpu_energy_dynamic_ttft_j"),
            "gpu_energy_dynamic_generation_j": raw_metrics.get("gpu_energy_dynamic_generation_j"),
            
            "joules_per_token": raw_metrics.get("joules_per_token"),
            
            "cpu_idle_baseline_w": cpu_idle if cpu_idle is not None else "N/A",
            "gpu_idle_baseline_w": gpu_idle if gpu_idle is not None else "N/A",
            "energy_calculation_method": method
        }

        # Conversione dei valori None in 'N/A' per l'analisi statistica in R/Pandas
        row_to_write = [
            "N/A" if row_dict[h] is None else row_dict[h] 
            for h in self.headers
        ]

        # Scrittura Thread-Safe sul file di report
        with self._lock:
            with open(self.filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row_to_write)
                
        return self.filepath
