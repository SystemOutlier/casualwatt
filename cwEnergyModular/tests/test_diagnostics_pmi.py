# -*- coding: utf-8 -*-
"""
tests/test_diagnostics_pmi.py — Sonda PMI/WMI della diagnostica.

Perche' esiste: quando il device EMI non c'e', la diagnostica dice
``unavailable``; ma ``unavailable`` ha due cause diverse, e distinguerle cambia
che cosa si puo' fare. Un meter PMI esposto da Windows (``Win32_PowerMeter``,
namespace ``root\\CIMV2\\power``) significa "esiste un'interfaccia, non e' un
canale implementato"; nessun meter significa "il driver non ne espone".

I test verificano il PARSING e la CLASSIFICAZIONE della sonda, non il sistema
reale: il processo PowerShell e' sostituito. Che cosa NON verificano: che su
questo host esista un meter PMI. La sonda vera gira solo dove EMI manca.
"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diagnostics  # noqa: E402


def _fake_run(returncode=0, stdout="", stderr=""):
    def run(*_args, **_kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout,
                               stderr=stderr)
    return run


def test_meter_multipli(monkeypatch):
    """Due istanze WMI in JSON sono due meter, non un errore di parsing."""
    out = '[{"DeviceID":"a","MeterType":0},{"DeviceID":"b","MeterType":1}]'
    monkeypatch.setattr(diagnostics.subprocess, "run", _fake_run(stdout=out))
    res = diagnostics._probe_pmi_power_meter()
    assert res["probed"] is True and res["error"] is None
    assert [m["DeviceID"] for m in res["meters"]] == ["a", "b"]


def test_istanza_singola_normalizzata_a_lista(monkeypatch):
    """ConvertTo-Json restituisce un oggetto quando l'istanza e' una sola."""
    monkeypatch.setattr(diagnostics.subprocess, "run",
                        _fake_run(stdout='{"DeviceID":"a"}'))
    res = diagnostics._probe_pmi_power_meter()
    assert res["probed"] is True and len(res["meters"]) == 1


def test_nessun_meter_e_una_risposta_conclusa(monkeypatch):
    """Output vuoto = interrogazione riuscita, zero meter (non 'sonda fallita')."""
    monkeypatch.setattr(diagnostics.subprocess, "run", _fake_run(stdout=""))
    res = diagnostics._probe_pmi_power_meter()
    assert res == {"probed": True, "meters": [], "error": None}


def test_classe_assente_non_conclusiva(monkeypatch):
    """Un errore del provider lascia la sonda 'non conclusa', non 'zero meter'."""
    monkeypatch.setattr(diagnostics.subprocess, "run",
                        _fake_run(returncode=1,
                                  stderr="Get-CimInstance : Invalid class\nriga 1"))
    res = diagnostics._probe_pmi_power_meter()
    assert res["probed"] is False
    assert "Invalid class" in res["error"]


def test_timeout_non_conclusivo(monkeypatch):
    """PowerShell che non risponde non deve bloccare la diagnostica."""
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="powershell", timeout=5.0)
    monkeypatch.setattr(diagnostics.subprocess, "run", boom)
    res = diagnostics._probe_pmi_power_meter()
    assert res["probed"] is False and res["error"] == "TimeoutExpired"


def test_json_non_valido_non_conclusivo(monkeypatch):
    monkeypatch.setattr(diagnostics.subprocess, "run",
                        _fake_run(stdout="non-json"))
    res = diagnostics._probe_pmi_power_meter()
    assert res["probed"] is False and res["error"] == "json_non_valido"


def test_comando_usa_il_namespace_documentato(monkeypatch):
    """Il namespace non si indovina: e' quello della pagina Microsoft."""
    visti = {}

    def run(cmd, **_kwargs):
        visti["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(diagnostics.subprocess, "run", run)
    diagnostics._probe_pmi_power_meter()
    script = visti["cmd"][-1]
    assert "root\\CIMV2\\power" in script
    assert "Win32_PowerMeter" in script
    assert "Get-CimInstance" in script
