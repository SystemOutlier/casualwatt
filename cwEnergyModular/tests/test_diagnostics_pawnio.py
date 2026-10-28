# -*- coding: utf-8 -*-
"""
tests/test_diagnostics_pawnio.py — Il fallback MSR nella diagnostica Windows.

Perche' esiste: quando il device EMI non c'e', la diagnostica dichiara che cosa
aspettarsi dalla catena, e quella dichiarazione deve coincidere con cio' che la
sessione fara'. Due esiti diversi e non intercambiabili: ``pawnio-counter`` se
il contatore MSR risponde, ``unavailable`` con la ragione se non risponde (per
esempio ``access_denied``, misurato il 28-10-2026 su token non elevato,
``tests/test_pawnio_backend.py``). Un terzo caso ha la precedenza su entrambi:
``CW_ENERGY_FILE``, che e' un contatore esterno e non un fallback.

I test sostituiscono i due backend, quindi verificano la CLASSIFICAZIONE e la
precedenza, non l'hardware: che il driver apra o neghi e' la misura, non il
test.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diagnostics  # noqa: E402
from energy import emi_backend as eb  # noqa: E402
from energy import pawnio_backend as pb  # noqa: E402


def _fake_emi(available):
    class FakeEMI:
        def __init__(self, *_args, **_kwargs):
            self.available = available
            self.device_path = None
            self.last_error = "nessun device corrispondente"
            self.notes = []
            self.metadata = None
            self.channels = []
            self.pkg_channel = None

        def read_domains(self):
            return None

        def close(self):
            pass

    return FakeEMI


def _fake_pawnio(available, reason="", cum_j=None):
    class FakeMSR:
        def __init__(self, *_args, **_kwargs):
            self.available = available
            self.reason = reason
            self.notes = [f"prova: {reason}"] if reason else []
            self.vendor = "intel"
            self.unit_msr = 0x606
            self.energy_msr = 0x611
            self.quantum_j = 6.103515625e-05
            self.hvci = "enabled"
            self.driver_signature = {"status": "Valid"}
            self.lib_version = "2.0.0"
            self.cumulative_counts = 204800

        def read_cumulative_energy_j(self):
            return cum_j

        def close(self):
            pass

    return FakeMSR


def _diagnose(monkeypatch, emi_cls, msr_cls):
    monkeypatch.setattr(eb, "EMICounterBackend", emi_cls)
    monkeypatch.setattr(pb, "PawnIOMSRBackend", msr_cls)
    monkeypatch.setattr(diagnostics, "_probe_pmi_power_meter",
                        lambda: {"probed": True, "meters": [], "error": None})
    monkeypatch.delenv("CW_ENERGY_FILE", raising=False)
    summary = {"errors": []}
    diagnostics._diagnose_windows([], None, summary)
    return summary


def test_fallback_che_risponde_diventa_il_metodo_atteso(monkeypatch):
    """EMI assente e MSR leggibile: la riga portera' `pawnio-counter`, non
    `unavailable`, e la ragione assente di EMI resta scritta."""
    summary = _diagnose(monkeypatch, _fake_emi(False),
                        _fake_pawnio(True, cum_j=12.5))
    assert summary["method_expected"] == "pawnio-counter"
    assert summary["pawnio_read"] is True
    assert summary["pawnio_reason"] == ""
    assert summary["pawnio_cum_j"] == 12.5
    assert summary["errors"] == ["emi_device_absent"]


def test_fallback_negato_lascia_unavailable_con_la_sua_ragione(monkeypatch):
    """Senza elevazione il contatore c'e' ma non si apre: `unavailable` con
    `access_denied`, non un numero e non una ragione generica."""
    summary = _diagnose(monkeypatch, _fake_emi(False),
                        _fake_pawnio(False, reason="access_denied"))
    assert summary["method_expected"] == "unavailable"
    assert summary["pawnio_read"] is False
    assert "emi_device_absent" in summary["errors"]
    assert "pawnio:access_denied" in summary["errors"]


def test_contatore_aperto_ma_illeggibile_non_e_un_metodo(monkeypatch):
    """Disponibile e illeggibile sono due stati distinti: senza lettura il
    metodo resta `unavailable` e la ragione e' `counter_unreadable`."""
    summary = _diagnose(monkeypatch, _fake_emi(False),
                        _fake_pawnio(True, cum_j=None))
    assert summary["method_expected"] == "unavailable"
    assert summary["pawnio_read"] is False
    assert "pawnio:counter_unreadable" in summary["errors"]


def test_energy_file_ha_precedenza_sul_fallback(monkeypatch):
    """`CW_ENERGY_FILE` e' un contatore esterno, non un anello della cascata:
    la diagnostica lo dichiara anche quando PawnIO risponderebbe."""
    msr = _fake_pawnio(True, cum_j=12.5)
    monkeypatch.setattr(eb, "EMICounterBackend", _fake_emi(False))
    monkeypatch.setattr(pb, "PawnIOMSRBackend", msr)
    monkeypatch.setattr(diagnostics, "_probe_pmi_power_meter",
                        lambda: {"probed": True, "meters": [], "error": None})
    monkeypatch.setenv("CW_ENERGY_FILE", "counter.json")
    summary = {"errors": []}
    diagnostics._diagnose_windows([], None, summary)
    assert summary["method_expected"] == "energy-file(dev/test)"
