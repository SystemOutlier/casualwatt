# -*- coding: utf-8 -*-
"""
energy/normalization.py — Normalizzazione cross-platform per metriche energetiche.

Questo modulo fornisce funzioni per normalizzare i consumi energetici in modo
comparabile tra piattaforme eterogenee (Windows/Linux, CPU/GPU diverse),
seguendo il framework proposto dalla letteratura (energy_efficiency_2026,
Watt Counts, Energy Considerations).

Le metriche normalizzate principali sono:
- E_token = E / N_token (energia per token generato)
- ECPC = E_tot / N_corrette (energia per risposta corretta)
- Separazione per componente: CPU (PKG), GPU, DRAM

La normalizzazione NON sostituisce i valori misurati: produce colonne derivate
che affiancano i dati grezzi nello schema CSV o di analisi.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Metadati hardware normalizzati per confronto cross-platform
@dataclass(frozen=True)
class HardwareSpec:
    """Specifiche hardware normalizzate per confronto cross-platform.
    
    Attributes:
        os: Sistema operativo (windows, linux, macos)
        cpu_model: Modello CPU (es. "Intel Core i9-13900HK")
        cpu_logical_cores: Core logici
        cpu_arch: Architettura (x86_64, arm64, ...)
        gpu_vendor: Vendor GPU (nvidia, amd, intel, none)
        gpu_model: Modello GPU (es. "RTX 4080", "RX 7900 XTX")
        gpu_memory_gb: Memoria GPU in GB
        ram_gb: RAM di sistema in GB
        kernel_version: Versione kernel (Linux) o build (Windows)
        driver_version: Versione driver GPU
        backend_cpu: Backend misura CPU (emi-counter, pawnio-counter, rapl, energy-file)
        backend_gpu: Backend misura GPU (nvml-energy, amdsmi-energy, nvml-power-integral, ...)
    """
    os: str
    cpu_model: str
    cpu_logical_cores: int
    cpu_arch: str
    gpu_vendor: str
    gpu_model: str
    gpu_memory_gb: Optional[float]
    ram_gb: Optional[float]
    kernel_version: str
    driver_version: str
    backend_cpu: str
    backend_gpu: str


@dataclass(frozen=True)
class NormalizedEnergy:
    """Risultato normalizzazione energetica per una singola misura.
    
    Tutte le energie sono in Joule. I campi None indicano che la metrica
    non e' calcolabile (es. token=0, corretti=0, componente non misurata).
    """
    # Energia grezza (misurata)
    total_energy_j: Optional[float]
    cpu_energy_j: Optional[float]        # PKG (package CPU)
    gpu_energy_j: Optional[float]        # GPU board
    dram_energy_j: Optional[float]       # DRAM (se disponibile)
    network_energy_j: Optional[float]    # Rete (stimata)
    cloud_energy_j: Optional[float]      # Cloud (stimata)
    
    # Conteggi
    output_tokens: int
    input_tokens: int
    total_tokens: int
    correct_answers: int
    total_answers: int
    
    # Metriche normalizzate per token
    energy_per_output_token_j: Optional[float]
    energy_per_total_token_j: Optional[float]
    cpu_energy_per_output_token_j: Optional[float]
    gpu_energy_per_output_token_j: Optional[float]
    
    # Metriche normalizzate per risposta corretta (ECPC)
    ecpc_total_j: Optional[float]
    ecpc_cpu_j: Optional[float]
    ecpc_gpu_j: Optional[float]
    
    # Metadata
    hardware_spec: Optional[HardwareSpec] = None
    notes: str = ""


def normalize_energy_per_token(
    energy_j: Optional[float],
    tokens: int
) -> Optional[float]:
    """Normalizza energia per token.
    
    Args:
        energy_j: Energia in Joule (None se non disponibile)
        tokens: Numero token (> 0)
    
    Returns:
        J/token o None se energia None o token <= 0
    """
    if energy_j is None or not math.isfinite(energy_j) or tokens <= 0:
        return None
    return energy_j / tokens


def normalize_energy_per_correct(
    energy_j: Optional[float],
    correct_count: int
) -> Optional[float]:
    """Normalizza energia per risposta corretta (ECPC).
    
    Args:
        energy_j: Energia in Joule (None se non disponibile)
        correct_count: Numero risposte corrette (> 0)
    
    Returns:
        J/corretta o None se energia None o correct_count <= 0
    """
    if energy_j is None or not math.isfinite(energy_j) or correct_count <= 0:
        return None
    return energy_j / correct_count


def compute_normalized_energy(
    record: Mapping[str, Any],
    hardware_spec: Optional[HardwareSpec] = None
) -> NormalizedEnergy:
    """Calcola tutte le metriche normalizzate da un record CSV.
    
    Args:
        record: Riga del CSV (casualwatt_csv_export.CSV_COLUMNS)
        hardware_spec: Specifiche hardware opzionali per confronto cross-platform
    
    Returns:
        NormalizedEnergy con tutte le metriche derivate
    """
    # Estrazione energia grezza
    total_energy = _finite(record.get("end_to_end_energy_j"))
    cpu_energy = _finite(record.get("active_energy_j")) or _finite(record.get("package_energy_j"))
    gpu_energy = _finite(record.get("gpu_energy_attributed_j"))
    dram_energy = _finite(record.get("baseline_energy_j"))  # DRAM non separato in PKG
    network_energy = _finite(record.get("network_energy_j"))
    cloud_energy = _finite(record.get("cloud_energy_j"))
    
    # Conteggi token
    output_tokens = _int(record.get("output_tokens"))
    input_tokens = _int(record.get("input_tokens"))
    total_tokens = output_tokens + input_tokens
    
    # Conteggi correttezza
    is_correct = record.get("is_correct")
    correct = 1 if str(is_correct).strip().lower() in ("1", "1.0", "true") else 0
    total_answers = 1  # una riga = una risposta
    
    # Per-token
    e_per_out_tok = normalize_energy_per_token(total_energy, output_tokens)
    e_per_tot_tok = normalize_energy_per_token(total_energy, total_tokens)
    cpu_per_out_tok = normalize_energy_per_token(cpu_energy, output_tokens)
    gpu_per_out_tok = normalize_energy_per_token(gpu_energy, output_tokens)
    
    # Per corretta (ECPC)
    ecpc_total = normalize_energy_per_correct(total_energy, correct)
    ecpc_cpu = normalize_energy_per_correct(cpu_energy, correct)
    ecpc_gpu = normalize_energy_per_correct(gpu_energy, correct)
    
    notes_parts = []
    if total_energy is None:
        notes_parts.append("total_energy_missing")
    if correct == 0:
        notes_parts.append("no_correct_answer")
    if output_tokens == 0:
        notes_parts.append("no_output_tokens")
    
    return NormalizedEnergy(
        total_energy_j=total_energy,
        cpu_energy_j=cpu_energy,
        gpu_energy_j=gpu_energy,
        dram_energy_j=dram_energy,
        network_energy_j=network_energy,
        cloud_energy_j=cloud_energy,
        output_tokens=output_tokens,
        input_tokens=input_tokens,
        total_tokens=total_tokens,
        correct_answers=correct,
        total_answers=total_answers,
        energy_per_output_token_j=e_per_out_tok,
        energy_per_total_token_j=e_per_tot_tok,
        cpu_energy_per_output_token_j=cpu_per_out_tok,
        gpu_energy_per_output_token_j=gpu_per_out_tok,
        ecpc_total_j=ecpc_total,
        ecpc_cpu_j=ecpc_cpu,
        ecpc_gpu_j=ecpc_gpu,
        hardware_spec=hardware_spec,
        notes="; ".join(notes_parts) if notes_parts else ""
    )


def _finite(value: Any) -> Optional[float]:
    """Converte a float finito, None altrimenti."""
    if value in (None, "", "N/A"):
        return None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _int(value: Any) -> int:
    """Converte a int, 0 altrimenti."""
    if value in (None, "", "N/A"):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def aggregate_normalized(
    records: Sequence[Mapping[str, Any]],
    hardware_spec: Optional[HardwareSpec] = None
) -> Dict[str, Any]:
    """Aggrega metriche normalizzate su un insieme di record.
    
    Calcola medie, mediane e intervalli per le metriche normalizzate.
    Usa solo record con energia finita e token > 0.
    
    Returns:
        Dizionario con statistiche aggregate
    """
    normalized = [compute_normalized_energy(r, hardware_spec) for r in records]
    
    # Filtra record validi per metriche per-token
    valid_token = [n for n in normalized if n.output_tokens > 0 and n.total_energy_j is not None]
    valid_correct = [n for n in normalized if n.correct_answers > 0 and n.total_energy_j is not None]
    
    def stats(values: List[float]) -> Dict[str, float]:
        if not values:
            return {}
        v = sorted(values)
        n = len(v)
        return {
            "mean": sum(v) / n,
            "median": v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2,
            "min": v[0],
            "max": v[-1],
            "count": n,
        }
    
    return {
        "n_records": len(records),
        "n_valid_token": len(valid_token),
        "n_valid_correct": len(valid_correct),
        "per_output_token": stats([n.energy_per_output_token_j for n in valid_token if n.energy_per_output_token_j is not None]),
        "per_total_token": stats([n.energy_per_total_token_j for n in valid_token if n.energy_per_total_token_j is not None]),
        "cpu_per_output_token": stats([n.cpu_energy_per_output_token_j for n in valid_token if n.cpu_energy_per_output_token_j is not None]),
        "gpu_per_output_token": stats([n.gpu_energy_per_output_token_j for n in valid_token if n.gpu_energy_per_output_token_j is not None]),
        "ecpc_total": stats([n.ecpc_total_j for n in valid_correct if n.ecpc_total_j is not None]),
        "ecpc_cpu": stats([n.ecpc_cpu_j for n in valid_correct if n.ecpc_cpu_j is not None]),
        "ecpc_gpu": stats([n.ecpc_gpu_j for n in valid_correct if n.ecpc_gpu_j is not None]),
        "hardware_spec": asdict(hardware_spec) if hardware_spec else None,
    }


def export_normalized_csv(
    records: Sequence[Mapping[str, Any]],
    path: str | Path,
    hardware_spec: Optional[HardwareSpec] = None,
    mode: str = "w"
) -> int:
    """Esporta metriche normalizzate in CSV.
    
    Colonne:
    - run_id, session_id, task_id (identificatori)
    - Tutte le energie grezze per componente
    - Token counts
    - Correct counts
    - Metriche per-token
    - Metriche per-corretta (ECPC)
    - Hardware spec (se fornito)
    - Notes
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    columns = [
        "run_id", "session_id", "batch_id", "point_id", "task_id",
        "total_energy_j", "cpu_energy_j", "gpu_energy_j", "dram_energy_j",
        "network_energy_j", "cloud_energy_j",
        "output_tokens", "input_tokens", "total_tokens",
        "correct_answers", "total_answers",
        "energy_per_output_token_j", "energy_per_total_token_j",
        "cpu_energy_per_output_token_j", "gpu_energy_per_output_token_j",
        "ecpc_total_j", "ecpc_cpu_j", "ecpc_gpu_j",
        "hardware_os", "hardware_cpu_model", "hardware_gpu_vendor",
        "hardware_gpu_model", "hardware_backend_cpu", "hardware_backend_gpu",
        "notes",
    ]
    
    import csv
    open_mode = "a" if mode == "a" and path.exists() and path.stat().st_size > 0 else "w"
    written = 0
    
    with open(path, open_mode, newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        if open_mode == "w":
            writer.writeheader()
        
        for record in records:
            norm = compute_normalized_energy(record, hardware_spec)
            row = {
                "run_id": record.get("run_id", ""),
                "session_id": record.get("session_id", ""),
                "batch_id": record.get("batch_id", ""),
                "point_id": record.get("point_id", ""),
                "task_id": record.get("task_id", ""),
                "total_energy_j": norm.total_energy_j,
                "cpu_energy_j": norm.cpu_energy_j,
                "gpu_energy_j": norm.gpu_energy_j,
                "dram_energy_j": norm.dram_energy_j,
                "network_energy_j": norm.network_energy_j,
                "cloud_energy_j": norm.cloud_energy_j,
                "output_tokens": norm.output_tokens,
                "input_tokens": norm.input_tokens,
                "total_tokens": norm.total_tokens,
                "correct_answers": norm.correct_answers,
                "total_answers": norm.total_answers,
                "energy_per_output_token_j": norm.energy_per_output_token_j,
                "energy_per_total_token_j": norm.energy_per_total_token_j,
                "cpu_energy_per_output_token_j": norm.cpu_energy_per_output_token_j,
                "gpu_energy_per_output_token_j": norm.gpu_energy_per_output_token_j,
                "ecpc_total_j": norm.ecpc_total_j,
                "ecpc_cpu_j": norm.ecpc_cpu_j,
                "ecpc_gpu_j": norm.ecpc_gpu_j,
                "hardware_os": norm.hardware_spec.os if norm.hardware_spec else "",
                "hardware_cpu_model": norm.hardware_spec.cpu_model if norm.hardware_spec else "",
                "hardware_gpu_vendor": norm.hardware_spec.gpu_vendor if norm.hardware_spec else "",
                "hardware_gpu_model": norm.hardware_spec.gpu_model if norm.hardware_spec else "",
                "hardware_backend_cpu": norm.hardware_spec.backend_cpu if norm.hardware_spec else "",
                "hardware_backend_gpu": norm.hardware_spec.backend_gpu if norm.hardware_spec else "",
                "notes": norm.notes,
            }
            writer.writerow(row)
            written += 1
    
    return written


def export_normalized_json(
    records: Sequence[Mapping[str, Any]],
    path: str | Path,
    hardware_spec: Optional[HardwareSpec] = None,
    include_aggregate: bool = True
) -> None:
    """Esporta metriche normalizzate in JSON con struttura completa."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    normalized = [compute_normalized_energy(r, hardware_spec) for r in records]
    
    data = {
        "records": [asdict(n) for n in normalized],
        "hardware_spec": asdict(hardware_spec) if hardware_spec else None,
    }
    
    if include_aggregate:
        data["aggregate"] = aggregate_normalized(records, hardware_spec)
    
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def hardware_spec_from_run_metadata(
    run_meta: Mapping[str, Any],
    gpu_name: str = "",
    gpu_vendor: str = "",
    driver_version: str = "",
    backend_cpu: str = "",
    backend_gpu: str = ""
) -> HardwareSpec:
    """Costruisce HardwareSpec dai metadati di run (RUN_METADATA_COLUMNS)."""
    import platform
    
    os_name = platform.system().lower()
    if os_name == "darwin":
        os_name = "macos"
    
    return HardwareSpec(
        os=os_name,
        cpu_model=run_meta.get("cpu_model", ""),
        cpu_logical_cores=int(run_meta.get("cpu_logical_cores", 0) or 0),
        cpu_arch=platform.machine().lower(),
        gpu_vendor=gpu_vendor or run_meta.get("gpu_nvml_name", "").split()[0].lower() if run_meta.get("gpu_nvml_name") else "none",
        gpu_model=gpu_name or run_meta.get("gpu_nvml_name", ""),
        gpu_memory_gb=_finite(run_meta.get("gpu_memory_gb")) if "gpu_memory_gb" in run_meta else None,
        ram_gb=_finite(run_meta.get("ram_gb")) if "ram_gb" in run_meta else None,
        kernel_version=platform.release(),
        driver_version=driver_version,
        backend_cpu=backend_cpu or run_meta.get("cpu_energy_source_method", ""),
        backend_gpu=backend_gpu,
    )


# Convenzioni per dichiarazione metodologica (da includere in report/tesi)
NORMALIZATION_METHODOLOGY = """
Normalizzazione cross-platform (metodologia dichiarata):

1. ENERGIA PER TOKEN (E_token)
   E_token = E_totale / N_token_output
   - E_totale: end_to_end_energy_j (somma CPU + GPU + rete + cloud)
   - N_token_output: token generati dal modello (output_tokens)
   - Separazione componenti: CPU_token = active_energy_j / N_token, GPU_token = gpu_energy_attributed_j / N_token

2. ENERGIA PER RISPOSTA CORRETTA (ECPC)
   ECPC = Σ E_eleggibile / N_risposte_corrette
   - E_eleggibile: energia con flag validi, baseline sottratta, finestra verificata
   - N_risposte_corrette: conteggio is_correct == 1 (verdetto binario validato)
   - Separazione componenti: ECPC_cpu, ECPC_gpu

3. SPECIFICHE HARDWARE (per confronto cross-platform)
   Dichiarate per ogni campagna: OS, CPU model/core/arch, GPU vendor/model/memory,
   kernel/driver version, backend misura CPU e GPU.
   Il confronto tra piattaforme diverse USA SOLO metriche normalizzate,
   MAI joule assoluti.

4. LIMITI DICHIARATI
   - La scala assoluta del contatore NON e' arbitrata (stesso MSR 0x611 su Windows)
   - GPU per-processo NON disponibile (limite NVML binding)
   - DRAM spesso 0 su host client (non sommata a PKG)
   - Rete/cloud: stime con coefficienti dichiarati, non misure
"""


if __name__ == "__main__":
    # Demo veloce
    print(NORMALIZATION_METHODOLOGY)
    
    # Test funzioni base
    print("\n--- Test funzioni base ---")
    print(f"normalize_energy_per_token(100.0, 50) = {normalize_energy_per_token(100.0, 50)}")
    print(f"normalize_energy_per_token(None, 50) = {normalize_energy_per_token(None, 50)}")
    print(f"normalize_energy_per_token(100.0, 0) = {normalize_energy_per_token(100.0, 0)}")
    print(f"normalize_energy_per_correct(500.0, 10) = {normalize_energy_per_correct(500.0, 10)}")
    print(f"normalize_energy_per_correct(500.0, 0) = {normalize_energy_per_correct(500.0, 0)}")