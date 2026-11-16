# -*- coding: utf-8 -*-
"""Test deterministici della firma del background (Fase 3 emenda).

La firma del background include solo grandezze identitarie dello stato:
processi rilevanti (per PID), piano energetico, stato alimentazione,
hash caratterizzazione. Non include CPU%, potenza o temperatura istantanee.

I test usano mock di psutil e subprocess per essere indipendenti dall'host.
"""
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import machine_state as ms


def test_firma_includes_processes():
    """La firma include i top-5 processi per CPU%."""
    with patch.object(ms, "power_state") as mock_ps, \
         patch.object(ms, "sample_top_processes") as mock_top:
        mock_ps.return_value = {
            "plan": "Bilanciato",
            "battery": "absent",
            "power_plugged": None,
        }
        mock_top.return_value = [
            {"pid": 100, "name": "chrome.exe", "cpu_pct": 5.0},
            {"pid": 200, "name": "python.exe", "cpu_pct": 3.0},
        ]
        sig = ms.background_signature(char_sha256="abc123")
        assert "processes" in sig
        assert len(sig["processes"]) == 2
        assert sig["processes"][0]["pid"] == 100


def test_firma_includes_power_plan():
    """La firma include il piano energetico."""
    with patch.object(ms, "power_state") as mock_ps, \
         patch.object(ms, "sample_top_processes") as mock_top:
        mock_ps.return_value = {
            "plan": "Alta prestazione",
            "battery": "absent",
            "power_plugged": None,
        }
        mock_top.return_value = []
        sig = ms.background_signature()
        assert sig["power_plan"] == "Alta prestazione"


def test_firma_includes_battery_state():
    """La firma include lo stato della batteria."""
    with patch.object(ms, "power_state") as mock_ps, \
         patch.object(ms, "sample_top_processes") as mock_top:
        mock_ps.return_value = {
            "plan": "",
            "battery": "present",
            "power_plugged": True,
        }
        mock_top.return_value = []
        sig = ms.background_signature()
        assert sig["battery"] == "present"
        assert sig["power_plugged"] is True


def test_firma_includes_char_hash():
    """La firma include l'hash della caratterizzazione se fornito."""
    with patch.object(ms, "power_state") as mock_ps, \
         patch.object(ms, "sample_top_processes") as mock_top:
        mock_ps.return_value = {"plan": "", "battery": "absent", "power_plugged": None}
        mock_top.return_value = []
        sig = ms.background_signature(char_sha256="deadbeef")
        assert sig["char_sha256"] == "deadbeef"


def test_firma_empty_char_hash_if_not_provided():
    """Se non è fornito l'hash, la firma lo lascia vuoto."""
    with patch.object(ms, "power_state") as mock_ps, \
         patch.object(ms, "sample_top_processes") as mock_top:
        mock_ps.return_value = {"plan": "", "battery": "absent", "power_plugged": None}
        mock_top.return_value = []
        sig = ms.background_signature()
        assert sig["char_sha256"] == ""


def test_signatures_match_identical():
    """Due firme identiche coincidono."""
    sig = {
        "processes": [{"pid": 100, "name": "a.exe", "cpu_pct": 1.0}],
        "power_plan": "Bilanciato",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "abc",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    match, diff = ms.signatures_match(sig, sig)
    assert match is True
    assert diff == []


def test_signatures_match_different_processes():
    """Processi diversi (per PID) rendono le firme non coincidenti."""
    sig1 = {
        "processes": [{"pid": 100, "name": "a.exe", "cpu_pct": 1.0}],
        "power_plan": "Bilanciato",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [{"pid": 200, "name": "b.exe", "cpu_pct": 1.0}],
        "power_plan": "Bilanciato",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:01Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is False
    assert any("processi" in d for d in diff)


def test_signatures_match_different_power_plan():
    """Piano energetico diverso rende le firme non coincidenti."""
    sig1 = {
        "processes": [],
        "power_plan": "Bilanciato",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [],
        "power_plan": "Alta prestazione",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:01Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is False
    assert any("piano energetico" in d for d in diff)


def test_signatures_match_different_battery():
    """Stato batteria diverso rende le firme non coincidenti."""
    sig1 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [],
        "power_plan": "",
        "battery": "present",
        "power_plugged": True,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:01Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is False
    assert any("batteria" in d for d in diff)


def test_signatures_match_different_char_hash():
    """Hash caratterizzazione diverso rende le firme non coincidenti."""
    sig1 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "aaa",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "bbb",
        "timestamp": "2026-11-15T00:00:01Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is False
    assert any("caratterizzazione" in d for d in diff)


def test_signatures_match_empty_char_hash_ignored():
    """Hash vuoto non viene confrontato (non è una differenza)."""
    sig1 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:01Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is True


def test_signatures_match_timestamp_ignored():
    """I timestamp non vengono confrontati (non sono identità)."""
    sig1 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T00:00:00Z",
    }
    sig2 = {
        "processes": [],
        "power_plan": "",
        "battery": "absent",
        "power_plugged": None,
        "char_sha256": "",
        "timestamp": "2026-11-15T23:59:59Z",
    }
    match, diff = ms.signatures_match(sig1, sig2)
    assert match is True
