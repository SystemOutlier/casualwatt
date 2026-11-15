# -*- coding: utf-8 -*-
"""
Test per energy/normalization.py
"""
from __future__ import annotations

import pytest
from energy.normalization import (
    normalize_energy_per_token,
    normalize_energy_per_correct,
    compute_normalized_energy,
    aggregate_normalized,
    HardwareSpec,
    _finite,
    _int,
)


def test_normalize_energy_per_token():
    """Test normalizzazione energia per token."""
    assert normalize_energy_per_token(100.0, 50) == 2.0
    assert normalize_energy_per_token(0.0, 10) == 0.0
    assert normalize_energy_per_token(None, 50) is None
    assert normalize_energy_per_token(100.0, 0) is None
    assert normalize_energy_per_token(100.0, -1) is None
    assert normalize_energy_per_token(float('inf'), 10) is None
    assert normalize_energy_per_token(float('nan'), 10) is None


def test_normalize_energy_per_correct():
    """Test normalizzazione energia per risposta corretta (ECPC)."""
    assert normalize_energy_per_correct(500.0, 10) == 50.0
    assert normalize_energy_per_correct(0.0, 5) == 0.0
    assert normalize_energy_per_correct(None, 10) is None
    assert normalize_energy_per_correct(100.0, 0) is None
    assert normalize_energy_per_correct(100.0, -1) is None


def test_finite():
    """Test helper _finite."""
    assert _finite(1.5) == 1.5
    assert _finite(0) == 0.0
    assert _finite("3.14") == 3.14
    assert _finite(None) is None
    assert _finite("") is None
    assert _finite("N/A") is None
    assert _finite(float('inf')) is None
    assert _finite(float('nan')) is None
    assert _finite("abc") is None


def test_int():
    """Test helper _int."""
    assert _int(5) == 5
    assert _int(3.7) == 3
    assert _int("10") == 10
    assert _int("2.5") == 2
    assert _int(None) == 0
    assert _int("") == 0
    assert _int("N/A") == 0
    assert _int("abc") == 0


def test_compute_normalized_energy():
    """Test calcolo metriche normalizzate da record CSV."""
    record = {
        "end_to_end_energy_j": "150.5",
        "active_energy_j": "120.0",
        "gpu_energy_attributed_j": "30.5",
        "network_energy_j": "0.0",
        "cloud_energy_j": "",
        "output_tokens": "25",
        "input_tokens": "10",
        "is_correct": "1",
    }
    
    result = compute_normalized_energy(record)
    
    assert result.total_energy_j == 150.5
    assert result.cpu_energy_j == 120.0
    assert result.gpu_energy_j == 30.5
    assert result.output_tokens == 25
    assert result.input_tokens == 10
    assert result.total_tokens == 35
    assert result.correct_answers == 1
    assert result.energy_per_output_token_j == pytest.approx(6.02)
    assert result.energy_per_total_token_j == pytest.approx(4.3)
    assert result.cpu_energy_per_output_token_j == pytest.approx(4.8)
    assert result.gpu_energy_per_output_token_j == pytest.approx(1.22)
    assert result.ecpc_total_j == pytest.approx(150.5)
    assert result.ecpc_cpu_j == pytest.approx(120.0)
    assert result.ecpc_gpu_j == pytest.approx(30.5)


def test_compute_normalized_energy_incorrect():
    """Test con risposta non corretta."""
    record = {
        "end_to_end_energy_j": "100.0",
        "active_energy_j": "80.0",
        "gpu_energy_attributed_j": "20.0",
        "output_tokens": "20",
        "input_tokens": "5",
        "is_correct": "0",
    }
    
    result = compute_normalized_energy(record)
    
    assert result.correct_answers == 0
    assert result.ecpc_total_j is None
    assert result.ecpc_cpu_j is None
    assert result.ecpc_gpu_j is None
    assert "no_correct_answer" in result.notes


def test_compute_normalized_energy_no_tokens():
    """Test senza token output."""
    record = {
        "end_to_end_energy_j": "50.0",
        "active_energy_j": "40.0",
        "output_tokens": "0",
        "input_tokens": "10",
        "is_correct": "1",
    }
    
    result = compute_normalized_energy(record)
    
    assert result.output_tokens == 0
    assert result.energy_per_output_token_j is None
    assert result.cpu_energy_per_output_token_j is None
    assert result.ecpc_total_j == pytest.approx(50.0)


def test_aggregate_normalized():
    """Test aggregazione metriche normalizzate."""
    records = [
        {
            "end_to_end_energy_j": "100.0",
            "active_energy_j": "80.0",
            "gpu_energy_attributed_j": "20.0",
            "output_tokens": "10",
            "input_tokens": "5",
            "is_correct": "1",
        },
        {
            "end_to_end_energy_j": "200.0",
            "active_energy_j": "150.0",
            "gpu_energy_attributed_j": "50.0",
            "output_tokens": "20",
            "input_tokens": "10",
            "is_correct": "1",
        },
        {
            "end_to_end_energy_j": "150.0",
            "active_energy_j": "120.0",
            "gpu_energy_attributed_j": "30.0",
            "output_tokens": "15",
            "input_tokens": "8",
            "is_correct": "0",  # non corretta
        },
    ]
    
    agg = aggregate_normalized(records)
    
    assert agg["n_records"] == 3
    assert agg["n_valid_token"] == 3
    assert agg["n_valid_correct"] == 2  # solo 2 corrette
    
    # Medie per token (su 3 record validi)
    # Record 1: 100/10 = 10.0
    # Record 2: 200/20 = 10.0
    # Record 3: 150/15 = 10.0
    assert agg["per_output_token"]["mean"] == pytest.approx(10.0)
    assert agg["per_output_token"]["median"] == pytest.approx(10.0)
    assert agg["per_output_token"]["count"] == 3
    
    # ECPC (su 2 record corretti)
    # Record 1: 100/1 = 100.0
    # Record 2: 200/1 = 200.0
    assert agg["ecpc_total"]["mean"] == pytest.approx(150.0)
    assert agg["ecpc_total"]["median"] == pytest.approx(150.0)
    assert agg["ecpc_total"]["count"] == 2


def test_hardware_spec():
    """Test HardwareSpec dataclass."""
    spec = HardwareSpec(
        os="windows",
        cpu_model="Intel Core i9-13900HK",
        cpu_logical_cores=20,
        cpu_arch="x86_64",
        gpu_vendor="nvidia",
        gpu_model="RTX 4080",
        gpu_memory_gb=16.0,
        ram_gb=32.0,
        kernel_version="10.0.26200",
        driver_version="560.94",
        backend_cpu="emi-counter",
        backend_gpu="nvml-energy",
    )
    
    assert spec.os == "windows"
    assert spec.cpu_logical_cores == 20
    assert spec.gpu_memory_gb == 16.0


def test_compute_normalized_energy_with_hardware():
    """Test con hardware spec."""
    record = {
        "end_to_end_energy_j": "100.0",
        "active_energy_j": "80.0",
        "output_tokens": "10",
        "input_tokens": "5",
        "is_correct": "1",
    }
    
    spec = HardwareSpec(
        os="linux",
        cpu_model="AMD Ryzen 9 7950X",
        cpu_logical_cores=32,
        cpu_arch="x86_64",
        gpu_vendor="amd",
        gpu_model="RX 7900 XTX",
        gpu_memory_gb=24.0,
        ram_gb=64.0,
        kernel_version="6.8.0",
        driver_version="24.10.1",
        backend_cpu="rapl",
        backend_gpu="amdsmi-energy",
    )
    
    result = compute_normalized_energy(record, spec)
    
    assert result.hardware_spec is not None
    assert result.hardware_spec.os == "linux"
    assert result.hardware_spec.backend_cpu == "rapl"
    assert result.hardware_spec.backend_gpu == "amdsmi-energy"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])