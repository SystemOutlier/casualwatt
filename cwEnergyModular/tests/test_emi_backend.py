# -*- coding: utf-8 -*-
"""Test offline del canale EMI come metodo principale su Windows (23/10).

Le docstring dei test di questo file sono state aggiunte il 23/10/2026
leggendo i corpi, non dall'autore originale delle funzioni; quelle dei test
toccati il 27/10/2026 (uscita di LHM dall'implementazione, D18) sono state
riscritte con i corpi.

Nessun IOCTL reale: il backend e' sostituito da un fake; cio' che si prova
qui e' la CATENA di decisioni (precedenze, etichette di metodo, lettura dei
bordi di finestra dal buffer del cumulativo) — non il registro hardware,
che e' validato a parte dai protocolli A-B-A con EMI vero.
"""
import threading

import pytest

from energy import emi_backend as eb
from energy import energy_session as es


class FakeEMI:
    """Stessa superficie di EMICounterBackend usata dal sorgente.

    ``read_domains`` NON e' riscritto qui: e' il metodo VERO del backend,
    applicato al record finto. Falsa resta solo la IOCTL, che e' il confine
    con l'hardware; la conversione pWh->J e la mappa offset->dominio sono
    le stesse che passano in produzione.
    """

    read_domains = eb.EMICounterBackend.read_domains

    #: Metadato che il device finto dichiara: dal 27/10/2026 ``read_domains``
    #: mappa per NOME, quindi senza canali non c'e' nessun dominio.
    NAMES = ("RAPL_Package0_PKG", "RAPL_Package0_DRAM",
             "RAPL_Package0_PP0", "RAPL_Package0_PP1")

    def __init__(self, auto_open=True, available=True):
        self.notes = []
        self.available = available
        self.device_path = "\\\\?\\fake#device" if available else None
        self.metadata = None
        self.channels = eb.channels_from_names(self.NAMES) if available else []
        self.last_error = None if available else "no device (fake)"
        self.closed = False
        self.raw_calls = 0

    def read_raw(self):
        # PKG=1_000_000 pWh, ts, DRAM=0, ts, PP0=500_000, ts, PP1=250_000, ts
        self.raw_calls += 1
        return (1_000_000, 42, 0, 0, 500_000, 43, 250_000, 44)

    def read_cumulative_energy_j(self):
        return 1_000_000 * eb.PWH_TO_J

    def close(self):
        self.closed = True


# ------------------------------------------------------------------ unit: backend
def test_pwh_to_j_conversion():
    """1_000_000 pWh = 3,6e-3 J, e i campi PP0/PP1/DRAM/ts escono convertiti."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    # i canali sono dichiarati, non dedotti dalla posizione: senza metadato
    # ``read_domains`` non produce domini (F13).
    b.channels = eb.channels_from_names(FakeEMI.NAMES)
    b.read_raw = lambda: (1_000_000, 42, 0, 0, 500_000, 43, 250_000, 44)
    assert b.read_cumulative_energy_j() == pytest.approx(1_000_000 * eb.PWH_TO_J)
    f = b.read_fields_j()
    assert f["pkg"] == pytest.approx(3.6e-3)
    assert f["dram"] == pytest.approx(0.0)
    assert f["pp0"] == pytest.approx(1.8e-3)
    assert f["pp1"] == pytest.approx(9e-4)
    assert f["ts_100ns"] == 42


def test_unavailable_backend_reads_none():
    """Backend non aperto: le letture restituiscono None, non 0 J."""
    b = eb.EMICounterBackend(auto_open=False)
    assert b.available is False
    assert b.read_cumulative_energy_j() is None
    assert b.read_fields_j() is None


# ------------------------------------------------------------------ catena: priorità
def _make_source(monkeypatch, available=True):
    """Costruisce un _CPUJouleSource su Windows simulato con EMI fake."""
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")
    monkeypatch.setattr(es._CPUJouleSource, "_try_power_counter", lambda self: False)
    monkeypatch.delenv("CW_ENERGY_FILE", raising=False)

    fake = FakeEMI(available=available)
    monkeypatch.setattr(eb, "EMICounterBackend", lambda *a, **k: fake)
    src = es._CPUJouleSource()
    return src, fake


def test_emi_is_the_measured_method(monkeypatch):
    """Con EMI disponibile il metodo e' 'emi-counter' e nessun thread di misura parte all'import."""
    src, fake = _make_source(monkeypatch, available=True)
    assert src.method == "emi-counter"
    assert src._emi is fake
    # l'import/costruzione NON deve mai avviare thread di misura:
    assert src._emi_thread is None


def test_windows_without_emi_is_unavailable(monkeypatch):
    """Senza EMI il metodo resta 'unavailable' con la nota che dichiara la catena chiusa."""
    src, fake = _make_source(monkeypatch, available=False)
    assert src.method == "unavailable"
    assert src._emi is None
    assert any("EMI non disponibile" in n for n in src.notes)


# ----------------------------------------------------------- bordo esatto di finestra
def _seed_buffer(src, pts):
    with src._emi_lock:
        src._emi_samples = list(pts)


def test_emi_window_energy_exact_edges(monkeypatch):
    """Finestra intera 40 J, bordi interni interpolati 20 J, sottofinestra del giudice esclusa ai bordi esatti."""
    src, _ = _make_source(monkeypatch)
    _seed_buffer(src, [(1000.0, 0.0), (1002.0, 20.0), (1004.0, 40.0)])
    # cumulativa lineare 10 J/s: finestra piena = 40 J
    assert src.emi_window_energy_j(1000.0, 1004.0) == pytest.approx(40.0)
    # bordi interni interpolati: [1001, 1003] = 20 J
    assert src.emi_window_energy_j(1001.0, 1003.0) == pytest.approx(20.0)
    # sottofinestra esclusa (judge) ai bordi esatti: 10 + 10
    assert src.emi_window_energy_j(
        1000.0, 1004.0, [(1001.0, 1003.0)]
    ) == pytest.approx(20.0)


def test_emi_window_energy_guards(monkeypatch):
    """Metodo diverso, buffer vuoto o finestra fuori copertura: None, mai un numero estrapolato."""
    src, _ = _make_source(monkeypatch)
    # metodo diverso: nessun valore (il chiamante dichiara il fallback)
    src.method = "rapl"
    assert src.emi_window_energy_j(1000.0, 1004.0) is None
    src.method = "emi-counter"
    # buffer vuoto: None, non zero
    assert src.emi_window_energy_j(1000.0, 1004.0) is None
    # finestra fuori copertura (> 1 s oltre il bordo): None, mai estrapolare
    _seed_buffer(src, [(1000.0, 0.0), (1002.0, 20.0)])
    assert src.emi_window_energy_j(900.0, 1001.0) is None


def test_session_exact_between_routes_buffer_then_counter(monkeypatch):
    """package_energy_exact_between usa il buffer EMI e degrada a None senza copertura, non a 0."""
    src, _ = _make_source(monkeypatch)
    sess = es.EnergySession.__new__(es.EnergySession)  # niente __post_init__
    sess._source = src
    sess._lock = threading.RLock()
    sess._samples = []
    _seed_buffer(src, [(1000.0, 0.0), (1010.0, 100.0)])
    assert sess.package_energy_exact_between(1002.0, 1007.0) == pytest.approx(50.0)
    # senza copertura il percorso esato degrada dichiaratamente (None),
    # NON restituisce 0:
    _seed_buffer(src, [(1000.0, 0.0)])
    assert sess.package_energy_exact_between(1100.0, 1105.0) is None


# ------------------------------------------------------------------ calibrazione
def test_idle_window_reports_emi_mode(monkeypatch):
    """La finestra di idle dichiara 'emi-counter' e riporta il delta del contatore (30 J) e la sua durata."""
    src, _ = _make_source(monkeypatch)
    seq = iter([100.0, 130.0])
    src._emi.read_cumulative_energy_j = lambda: next(seq)
    w = src.read_idle_window_j(0.5)
    assert w is not None
    delta, dt, mode = w
    assert delta == pytest.approx(30.0)
    assert mode == "emi-counter"
    assert dt >= 0.5 - 1e-6


def test_read_power_j_and_package_j_use_counter(monkeypatch):
    """Letture puntuali del package passano dal contatore cumulativo convertito, non dall'integrazione."""
    src, _ = _make_source(monkeypatch)
    assert src.read_power_j() == pytest.approx(1_000_000 * eb.PWH_TO_J)
    assert src.read_package_j(0.0) == pytest.approx(1_000_000 * eb.PWH_TO_J)


# -------------------------------------------------------------------- chiusura
def test_close_stops_sampler_and_backend(monkeypatch):
    """close() spegne il thread del sampler, azzera i riferimenti e chiude il backend."""
    src, fake = _make_source(monkeypatch)
    sess = es.EnergySession.__new__(es.EnergySession)
    sess._source = src
    sess._lock = threading.RLock()
    sess._samples = []
    sess._running = False
    sess._thread = None
    sess._stop = threading.Event()
    from types import SimpleNamespace
    sess._gpu = SimpleNamespace(shutdown=lambda: None)
    src._emi.read_cumulative_energy_j = lambda: 1.0
    src._start_emi_sampling()
    assert src._emi_thread is not None and src._emi_thread.is_alive()
    es.EnergySession.close(sess)
    assert src._emi_thread is None
    assert src._emi is None
    assert fake.closed is True
