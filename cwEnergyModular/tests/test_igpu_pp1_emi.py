# -*- coding: utf-8 -*-
"""PP1 del record EMI collegato al campo informativo ``igpu_energy_j``.

Decisione del 24/10: quando ``emi-counter`` e' il canale primario, il dominio
grafico non deve restare N/A "per costruzione" mentre lo stesso record che
gia' si legge espone PP1. Dal 27/10/2026 (D18) e' anche l'UNICO percorso
iGPU: uscendo LHM non esiste piu' un sensore di potenza iGPU da integrare.
Le docstring di questo file sono scritte dalle funzioni stesse.

Come in tutto il modulo: nessun IOCTL reale. ``FakeEMI`` falsa SOLO il record
(a ``test_emi_backend``), mentre la conversione pWh -> J e la mappa
offset -> dominio sono il codice di produzione. Cio' che si prova qui e' la
catena di decisioni — quali campi si mettono in buffer, come si leggono i
bordi, quando si risponde None e perche'. Il fatto che PP1 sia il valore
giusto su QUESTA macchina e' un'altro fatto, verificato il 24/10 sui nomi
esposti dal metadato del driver (RAPL_Package0_PKG/_DRAM/_PP0/_PP1).
"""
import threading

import pytest

from energy import emi_backend as eb
from energy import energy_session as es
from test_emi_backend import _make_source, FakeEMI

PWH = eb.PWH_TO_J


def _seed_pp1(src, pts):
    """Buffer PP1: (t_monotono, cumulata_J, timestamp_del_dominio)."""
    with src._emi_lock:
        src._emi_pp1_samples = list(pts)


# ------------------------------------------------------------------ backend
def test_read_domains_espone_quattro_domini_col_loro_timestamp(monkeypatch):
    """Un record da 8 uint64 esce come dominio -> (J, ts): i timestamp sono per dominio."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    b.read_raw = lambda: (1_000_000, 42, 0, 43, 500_000, 44, 250_000, 45)
    d = b.read_domains()
    assert set(d) == {"pkg", "dram", "pp0", "pp1"}
    assert d["pkg"][0] == pytest.approx(1_000_000 * PWH)
    assert d["pkg"][2] == 1_000_000, "il terzo campo e' il grezzo in pWh, non J"
    assert d["dram"][:2] == (0.0, 43)
    assert d["pp0"][0] == pytest.approx(500_000 * PWH)
    assert d["pp1"][0] == pytest.approx(250_000 * PWH)
    assert d["pp1"][1] == 45, "il timestamp di PP1 e' il settimo campo, non quello del PKG"


def test_read_fields_j_resta_la_stessa_superficie_di_prima():
    """Il refactoring non cambia il contratto storico: quattro valori [J] + ts_100ns del PKG."""
    b = eb.EMICounterBackend(auto_open=False)
    b.available = True
    b.read_raw = lambda: (1_000_000, 42, 0, 43, 500_000, 44, 250_000, 45)
    f = b.read_fields_j()
    assert f["pkg"] == pytest.approx(3.6e-3)
    assert f["pp1"] == pytest.approx(9e-4)
    assert f["ts_100ns"] == 42
    assert "pp1_ts" not in f


# ------------------------------------------------------- bordo esatto di PP1
def test_pp1_finestra_letta_ai_bordi_esatti(monkeypatch):
    """PP1: 40 J sulla finestra intera, 20 J coi bordi interni, 20 J scorporando la finestra del giudice."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 0.0, 10), (1002.0, 20.0, 20), (1004.0, 40.0, 30)])
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") == pytest.approx(40.0)
    assert src.emi_window_energy_j(1001.0, 1003.0, domain="pp1") == pytest.approx(20.0)
    assert src.emi_window_energy_j(
        1000.0, 1004.0, [(1001.0, 1003.0)], domain="pp1") == pytest.approx(20.0)


def test_pp1_fermo_nel_tempo_non_e_zero_j(monkeypatch):
    """Timestamp PP1 costanti nella finestra: None con la ragione dichiarata, non un 0,000 J falso."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 7.0, 11), (1002.0, 7.0, 11), (1004.0, 7.0, 11)])
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") is None
    assert "fermo" in src.pp1_read_reason


def test_pp1_che_si_muove_a_valore_invariato_e_una_misura(monkeypatch):
    """Timestamp che avanzano e valore fermo = il dominio ha consumato zero: 0.0 J E' il numero giusto."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 7.0, 11), (1002.0, 7.0, 12), (1004.0, 7.0, 13)])
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") == pytest.approx(0.0)


def test_pp1_senza_campioni_e_dominio_sconosciuto(monkeypatch):
    """Buffer PP1 vuoto o dominio che il sampler non legge: None, e la ragione dice quale."""
    src, _ = _make_source(monkeypatch)
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") is None
    assert "PP1" in src.pp1_read_reason
    # PP0 non e' campionato: la domanda va rifiutata, non interpolata altrove
    _seed_pp1(src, [(1000.0, 1.0, 1), (1002.0, 2.0, 2)])
    assert src.emi_window_energy_j(1000.0, 1002.0, domain="pp0") is None
    assert "pp0" in src.pp1_read_reason


def test_pp1_non_contamina_lettura_del_package(monkeypatch):
    """Riempire solo il buffer PP1 non cambia il package: i due domini restano strade separate."""
    src, _ = _make_source(monkeypatch)
    with src._emi_lock:
        src._emi_samples = [(1000.0, 0.0), (1004.0, 100.0)]
    assert src.emi_window_energy_j(1000.0, 1004.0) == pytest.approx(100.0)
    _seed_pp1(src, [(1000.0, 5.0, 1), (1004.0, 6.0, 2)])
    assert src.emi_window_energy_j(1000.0, 1004.0) == pytest.approx(100.0)
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") == pytest.approx(1.0)


def test_con_metodo_diverso_pp1_non_parla(monkeypatch):
    """Su un altro canale di misura (RAPL) nessun delta PP1 esce dal buffer EMI."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 0.0, 1), (1004.0, 9.0, 2)])
    src.method = "rapl"
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") is None


def test_lettura_del_package_non_cancella_la_ragione(monkeypatch):
    """PKG e PP1 si leggono nella stessa finestra: l'ordine non deve far sparire la motivazione del N/A."""
    src, _ = _make_source(monkeypatch)
    with src._emi_lock:
        src._emi_samples = [(1000.0, 0.0), (1004.0, 100.0)]
    _seed_pp1(src, [(1000.0, 4.0, 7), (1002.0, 4.0, 7), (1004.0, 4.0, 7)])
    assert src.emi_window_energy_j(1000.0, 1004.0, domain="pp1") is None
    assert "fermo" in src.pp1_read_reason
    # il package passa dallo stesso metodo con un altro dominio: non deve
    # riportare lo slot della ragione a vuoto
    assert src.emi_window_energy_j(1000.0, 1004.0) == pytest.approx(100.0)
    assert "fermo" in src.pp1_read_reason


# ------------------------------------------------------------------ sessione
def _fake_session(src):
    sess = es.EnergySession.__new__(es.EnergySession)   # niente __post_init__
    sess._source = src
    sess._lock = threading.RLock()
    sess._samples = []
    sess._igpu_none_reason = None
    return sess


def test_session_igpu_con_emi_uses_the_counter(monkeypatch):
    """read_igpu_energy_j con emi-counter restituisce il delta PP1 e azzera la ragione del None."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 0.0, 1), (1002.0, 3.0, 2), (1004.0, 8.0, 3)])
    sess = _fake_session(src)
    assert sess.read_igpu_energy_j(1000.0, 1004.0) == pytest.approx(8.0)
    assert sess.igpu_unavailable_reason is None


def test_session_igpu_emi_propaga_la_ragione(monkeypatch):
    """Il motivo per cui igpu_energy_j sara' N/A nel CSV arriva dal backend, non da una nota generica."""
    src, _ = _make_source(monkeypatch)
    _seed_pp1(src, [(1000.0, 4.0, 7), (1002.0, 4.0, 7), (1004.0, 4.0, 7)])
    sess = _fake_session(src)
    assert sess.read_igpu_energy_j(1000.0, 1004.0) is None
    assert "fermo" in sess.igpu_unavailable_reason


def test_sampler_riempie_ambii_i_buffer_con_una_sola_ioctl(monkeypatch):
    """Un tick = una IOCTL: PKG e PP1 vengono dallo stesso record, cioe' dallo stesso istante."""
    src, fake = _make_source(monkeypatch)
    src._start_emi_sampling()
    threading.Event().wait(0.35)
    src.stop_emi_sampling()
    assert len(src._emi_samples) >= 2, "il sampler non ha popolato il PKG"
    assert len(src._emi_pp1_samples) >= 2, "il sampler non ha popolato il PP1"
    assert len(src._emi_pp1_samples) == len(src._emi_samples)
    # una lettura per tick, non due: i timestamp dei due domini sono coerenti
    assert fake.raw_calls == len(src._emi_samples)
    assert all(len(p) == 3 for p in src._emi_pp1_samples)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
