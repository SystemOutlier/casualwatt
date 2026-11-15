# -*- coding: utf-8 -*-
"""test_baseline_windows_target.py — Finestre baseline per politica di background.

Verifica che _calcola_budget_pre_esecuzione usi 5 finestre target per
background_controlled e 3 per block/controlled_idle.

I test coprono:
- 5 target in background_controlled;
- 3 target in block;
- minimo 3 valide dopo filtro;
- SystemExit se meno di 3 valide.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

import pytest
from unittest import mock

import sys
from pathlib import Path
tools_dir = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(tools_dir))
from run_gate_p44 import _calcola_budget_pre_esecuzione


def _fake_session():
    """Crea una sessione fake con _source.read_idle_window_j."""
    fake_source = mock.MagicMock()
    fake_source.read_idle_window_j.return_value = (1.0, 1.0, "pkg")
    fake_session = mock.MagicMock()
    fake_session._source = fake_source
    return fake_session


def test_5_target_in_background_controlled():
    """background_controlled usa 5 finestre target di default."""
    plan = {
        "background_load_policy": "background_controlled",
        "baseline_params": {
            "baseline_outlier_rule": "none",
            "baseline_windows_min": 3,
        },
    }
    
    fake_session = _fake_session()
    
    with mock.patch('run_gate_p44.v4') as mock_v4:
        mock_v4.block_baseline.return_value = {
            "budget_base_w": 1.0,
            "half_range_pre_w": 0.1,
            "half_drift_w": 0.05,
        }
        
        budget_w, dettagli = _calcola_budget_pre_esecuzione(
            "short", fake_session, plan
        )
    
    # background_controlled dovrebbe usare 5 finestre
    assert dettagli["n_terne"] == 5
    assert dettagli["n_finestre_usate"] == 10  # 5 pre + 5 post


def test_3_target_in_block():
    """block usa 3 finestre target di default."""
    plan = {
        "background_load_policy": "block",
        "baseline_params": {
            "baseline_outlier_rule": "none",
            "baseline_windows_min": 3,
        },
    }
    
    fake_session = _fake_session()
    
    with mock.patch('run_gate_p44.v4') as mock_v4:
        mock_v4.block_baseline.return_value = {
            "budget_base_w": 1.0,
            "half_range_pre_w": 0.1,
            "half_drift_w": 0.05,
        }
        
        budget_w, dettagli = _calcola_budget_pre_esecuzione(
            "short", fake_session, plan
        )
    
    # block dovrebbe usare 3 finestre
    assert dettagli["n_terne"] == 3
    assert dettagli["n_finestre_usate"] == 6  # 3 pre + 3 post


def test_minimo_3_valide_dopo_filtro():
    """Dopo filtro IQR, almeno 3 finestre devono restare valide."""
    plan = {
        "background_load_policy": "block",
        "baseline_params": {
            "baseline_outlier_rule": "iqr_1p5",
            "baseline_windows_min": 3,
        },
    }
    
    fake_session = _fake_session()
    
    with mock.patch('run_gate_p44.v4') as mock_v4:
        mock_v4.block_baseline.return_value = {
            "budget_base_w": 1.0,
            "half_range_pre_w": 0.1,
            "half_drift_w": 0.05,
        }
        
        budget_w, dettagli = _calcola_budget_pre_esecuzione(
            "short", fake_session, plan
        )
    
    # Dopo filtro, almeno 3 valide
    assert dettagli["baseline_filtrato"]["pre_filtrate"] >= 3
    assert dettagli["baseline_filtrato"]["post_filtrate"] >= 3


def test_custom_baseline_windows_target():
    """baseline_windows_target dal piano sovrascrive il default."""
    plan = {
        "background_load_policy": "background_controlled",
        "baseline_windows_target": 7,  # Custom target
        "baseline_params": {
            "baseline_outlier_rule": "none",
            "baseline_windows_min": 3,
        },
    }
    
    fake_session = _fake_session()
    
    with mock.patch('run_gate_p44.v4') as mock_v4:
        mock_v4.block_baseline.return_value = {
            "budget_base_w": 1.0,
            "half_range_pre_w": 0.1,
            "half_drift_w": 0.05,
        }
        
        budget_w, dettagli = _calcola_budget_pre_esecuzione(
            "short", fake_session, plan
        )
    
    # Custom target dovrebbe essere usato
    assert dettagli["n_terne"] == 7
    assert dettagli["n_finestre_usate"] == 14  # 7 pre + 7 post
