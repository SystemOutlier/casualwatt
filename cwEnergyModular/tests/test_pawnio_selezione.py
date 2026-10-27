# -*- coding: utf-8 -*-
"""Innesto di ``pawnio-counter`` nella catena: dopo EMI, mai al suo posto.

Sul codice la catena Windows e' ``CW_ENERGY_FILE`` > ``emi-counter`` >
``pawnio-counter`` > ``unavailable``: PawnIO legge lo **stesso** registro del
device EMI (``MSR_PKG_ENERGY_STATUS``), quindi e' un ripiego per quando il
device non c'e', non un secondo canale da sommare. Questi test fissano:

  * la precedenza: con EMI disponibile PawnIO non viene nemmeno aperto;
  * il fallimento dichiarato: se la sonda lo esclude, la ragione resta scritta
    e la catena finisce in ``unavailable``, non in un secondo tentativo muto;
  * il riuso del meccanismo di finestra: stesso buffer a 0,05 s, bordi
    interpolati, sottofinestre escluse — cambia la sorgente, non la misura;
  * cio' che PawnIO **non** ha: il dominio PP1 (l'iGPU resta ``None`` con la
    ragione dichiarata) e il timestamp del record, che il contatore MSR non
    porta.

Nessun driver e nessun MSR reale: il backend e il device sono finti.
"""
import threading

import pytest

from energy import emi_backend as eb
from energy import energy_session as es
from energy import pawnio_backend as pb
from test_emi_backend import FakeEMI

QUANTUM = 1.0 / (1 << 14)


class FakePawnio:
    """Sostituto del backend PawnIO: contatore cumulato e conteggi grezzi."""

    def __init__(self, *, available=True, reason="", values=(0.0,),
                 counts=(0,), quantum=QUANTUM, lib_version="2.0.0"):
        self.available = available
        self.reason = reason
        self.notes = ["nota del backend PawnIO"] if available else []
        self.quantum_j = quantum
        self.lib_version = lib_version
        self._values = list(values)
        self._counts = list(counts)
        self.closed = False
        self._i = 0

    def read_cumulative_energy_j(self):
        v = self._values[min(self._i, len(self._values) - 1)]
        self._i += 1
        return v

    @property
    def cumulative_counts(self):
        return self._counts[min(self._i, len(self._counts) - 1)]

    def close(self):
        self.closed = True


def _source(monkeypatch, *, emi=False, pawnio=None):
    """_CPUJouleSource su Windows simulato, con i backend scelti dal test."""
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")
    monkeypatch.setattr(es._CPUJouleSource, "_try_power_counter",
                        lambda self: False)
    monkeypatch.setattr(eb, "EMICounterBackend",
                        lambda *a, **k: FakeEMI(available=emi))
    if pawnio is None:
        monkeypatch.setattr(es._CPUJouleSource, "_try_pawnio",
                            lambda self: False)
    else:
        monkeypatch.setattr(pb, "PawnIOMSRBackend", lambda *a, **k: pawnio)
    monkeypatch.delenv("CW_ENERGY_FILE", raising=False)
    return es._CPUJouleSource()


def _fake_session(src):
    sess = es.EnergySession.__new__(es.EnergySession)   # niente __post_init__
    sess._source = src
    sess._lock = threading.RLock()
    sess._samples = []
    sess._igpu_none_reason = None
    sess._running = False
    sess._thread = None
    return sess


def _seed(src, pts):
    """Buffer del contatore: (t, cumulata_J, grezzo)."""
    with src._emi_lock:
        src._emi_samples = list(pts)


# ------------------------------------------------------------------ catena
def test_emi_ha_la_precedenza_e_pawnio_non_si_apre(monkeypatch):
    """Con EMI disponibile il metodo e' emi-counter e il fallback resta chiuso."""
    pawnio = FakePawnio()
    src = _source(monkeypatch, emi=True, pawnio=pawnio)
    assert src.method == "emi-counter"
    assert src._pawnio is None
    assert src._emi is not None


def test_pawnio_entra_solo_quando_emi_manca(monkeypatch):
    """Senza device EMI la catena passa a PawnIO, con il proprio token."""
    pawnio = FakePawnio()
    src = _source(monkeypatch, emi=False, pawnio=pawnio)
    assert src.method == "pawnio-counter"
    assert src._pawnio is pawnio
    assert src._emi is None
    assert any("fallback 'pawnio-counter'" in n for n in src.notes)
    assert any("si prova il contatore MSR" in n for n in src.notes)


def test_pawnio_rifiutato_dichiara_la_ragione_e_chiude_la_catena(monkeypatch):
    """Una sonda che esclude PawnIO non e' un silenzio: ragione e catena chiusa."""
    src = _source(monkeypatch, emi=False,
                  pawnio=FakePawnio(available=False, reason="module_missing"))
    assert src.method == "unavailable"
    assert any("PawnIO non disponibile: module_missing" in n
               for n in src.notes)
    assert any("catena Windows esaurita" in n for n in src.notes)


# --------------------------------------------------- finestra esatta e bordi
def test_finestra_esatta_dallo_stesso_buffer(monkeypatch):
    """Bordi interpolati dal buffer a 0,05 s: 20 s lineari a 10 J/s, meta' finestra esclusa."""
    src = _source(monkeypatch, emi=False, pawnio=FakePawnio())
    _seed(src, [(1000.0, 0.0, 0.0), (1002.0, 20.0, 327680.0),
                (1004.0, 40.0, 655360.0)])
    assert src.emi_window_energy_j(1000.0, 1004.0) == pytest.approx(40.0)
    assert src.emi_window_energy_j(1001.0, 1003.0) == pytest.approx(20.0)
    assert src.emi_window_energy_j(
        1000.0, 1004.0, [(1001.0, 1003.0)]) == pytest.approx(20.0)

    sess = _fake_session(src)
    assert sess.package_energy_exact_between(1000.0, 1004.0) == pytest.approx(
        40.0)


def test_pp1_non_esiste_su_pawnio_e_la_ragione_e_scritta(monkeypatch):
    """Il contatore MSR del package non porta PP1: None con la ragione, non 0 J."""
    src = _source(monkeypatch, emi=False, pawnio=FakePawnio())
    _seed(src, [(1000.0, 0.0, 0.0), (1002.0, 20.0, 100.0)])
    assert src.emi_window_energy_j(1000.0, 1002.0, domain="pp1") is None
    assert "PP1" in src.pp1_read_reason and "pawnio-counter" in src.pp1_read_reason

    sess = _fake_session(src)
    assert sess.read_igpu_energy_j(1000.0, 1002.0) is None
    assert "PP1" in sess.igpu_unavailable_reason


def test_provenienza_riporta_conteggi_e_quantum(monkeypatch):
    """I grezzi della riga sono conteggi del contatore MSR, con il quantum letto."""
    src = _source(monkeypatch, emi=False, pawnio=FakePawnio())
    _seed(src, [(1000.0, 0.0, 1000.0), (1002.0, 0.2, 1000 + 3276.8),
                (1004.0, 0.4, 1000 + 6553.6)])
    prov = _fake_session(src).window_counter_provenance(1000.0, 1004.0)
    assert prov["domain"] == "PKG"
    assert prov["raw_unit"].startswith("counts")
    assert f"{QUANTUM:.9g}" in prov["raw_unit"]
    assert prov["raw_start"] == pytest.approx(1000.0)
    assert prov["raw_end"] == pytest.approx(1000 + 6553.6)
    assert "pawnio" in prov["backend_version"]
    assert "2.0.0" in prov["backend_version"]


def test_bordo_del_contatore_porta_i_conteggi_non_i_pwh(monkeypatch):
    """read_counter_edge su PawnIO: pkg_j e pkg_counts, nessun timestamp 100 ns."""
    src = _source(monkeypatch, emi=False,
                  pawnio=FakePawnio(values=(12.5,), counts=(204800,)))
    edge = _fake_session(src).read_counter_edge()
    assert edge["counter_error"] == ""
    assert edge["counter"]["pkg_j"] == pytest.approx(12.5)
    assert edge["counter"]["pkg_counts"] == 204800
    assert edge["counter"]["ts_100ns"] is None
    assert edge["counter"]["pp1_j"] is None


def test_finestra_idle_dichiara_la_modalita_pawnio(monkeypatch):
    """La finestra passiva usa il contatore PawnIO e lo nomina nella modalita'."""
    src = _source(monkeypatch, emi=False,
                  pawnio=FakePawnio(values=(10.0, 11.5)))
    monkeypatch.setattr(es.time, "sleep", lambda s: None)
    delta, dt, mode = src.read_idle_window_j(0.5)
    assert mode == "pawnio-counter"
    assert delta == pytest.approx(1.5)
    assert dt > 0.0


def test_close_chiude_la_libreria_una_sola_volta(monkeypatch):
    """close() chiude il backend PawnIO e azzera il riferimento (idempotente)."""
    pawnio = FakePawnio()
    src = _source(monkeypatch, emi=False, pawnio=pawnio)
    sess = _fake_session(src)

    class _Gpu:
        def shutdown(self):
            pass

    sess._gpu = _Gpu()
    sess.close()
    assert pawnio.closed is True
    assert src._pawnio is None
    sess.close()   # idempotente
    assert src._pawnio is None
