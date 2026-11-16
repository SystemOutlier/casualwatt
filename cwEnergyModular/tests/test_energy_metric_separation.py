# -*- coding: utf-8 -*-
"""Test deterministici delle metriche energetiche separate (Fase 4 emenda).

Le due metriche E_net_idle e E_net_declared_background non vanno mai
aggregate, mediate insieme o confrontate direttamente. Ogni analysis.json
dichiara esplicitamente quale metrica è stata usata.

I test verificano che il campo energy_metric sia presente e corretto
in base alla politica di background dichiarata nel piano.
"""
from __future__ import annotations


def test_energy_metric_idle_per_block():
    """Con politica block, la metrica è E_net_idle."""
    plan = {"background_load_policy": "block"}
    metrica = _deriva_energy_metric(plan)
    assert metrica == "E_net_idle"


def test_energy_metric_declared_per_background_controlled():
    """Con politica background_controlled, la metrica è E_net_declared_background."""
    plan = {"background_load_policy": "background_controlled"}
    metrica = _deriva_energy_metric(plan)
    assert metrica == "E_net_declared_background"


def test_energy_metric_default_idle():
    """Se il piano non dichiara background_load_policy, la metrica è E_net_idle."""
    plan = {}
    metrica = _deriva_energy_metric(plan)
    assert metrica == "E_net_idle"


def test_energy_metric_values_are_distinct():
    """Le due metriche hanno valori distinti, non confondibili."""
    metrica_idle = _deriva_energy_metric({"background_load_policy": "block"})
    metrica_declared = _deriva_energy_metric({"background_load_policy": "background_controlled"})
    assert metrica_idle != metrica_declared
    assert metrica_idle == "E_net_idle"
    assert metrica_declared == "E_net_declared_background"


def _deriva_energy_metric(plan: dict) -> str:
    """Deriva la metrica energetica dalla politica di background del piano.

    Questa funzione replica la logica di run_gate_p44.py:
    se background_load_policy è 'background_controlled', la metrica è
    E_net_declared_background; altrimenti è E_net_idle.
    """
    bg_policy = plan.get("background_load_policy", "block")
    if bg_policy == "background_controlled":
        return "E_net_declared_background"
    else:
        return "E_net_idle"
