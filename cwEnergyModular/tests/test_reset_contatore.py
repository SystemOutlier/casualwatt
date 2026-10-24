# -*- coding: utf-8 -*-
"""
tests/test_reset_contatore.py — Il reset del contatore cumulativo non e' un delta.

Perche' esiste. ``alt_lhm.DOCX`` (24/10) §6, fase 2, elenca come unica lacuna
dei test del backend EMI: "manca un test che modelli il reset/non monotonia
del contatore cumulativo (oggi e' solo il rifiuto a :1065)". Il caso non e'
teorico: driver ricaricato, sospensione/ripresa del portatile e riapertura
dell'handle possono riportare il contatore a un valore piu' basso. Se il
buffer non venisse svuotato, l'interpolazione fra pre e post reset
produrrebbe un delta negativo (scartato) o una rampa inventata.

Che cosa verifica:
  1. un valore decrescente svuota il buffer PKG e il campione post-reset
     apre il nuovo buffer;
  2. un valore UGUALE non e' un reset (nessuno svuotamento);
  3. PKG e PP1 hanno buffer indipendenti: il reset di uno non cancella l'altro;
  4. una finestra a cavallo del reset risponde None (copertura insufficiente),
     non un delta falso; una finestra interamente dopo il reset e' corretta;
  5. la provenienza (raw pWh) dopo il reset parte dal nuovo valore.

Che cosa NON verifica: che il driver reale si comporti cosi'. Il test
modella il contratto che il sampler deve rispettare; l'evento fisico e'
documentato nei protocolli A-B-A (suspend/resume) e nel codice di riapertura
dell'handle (``read_raw`` ritenta una volta dopo la chiusura).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from test_emi_backend import _make_source  # noqa: E402


def _pkg(src):
    return [(p[0], p[1]) for p in src._emi_samples]


def _pp1(src):
    return [(p[0], p[1]) for p in src._emi_pp1_samples]


# ------------------------------------------------------------------ 1
def test_pkg_decrescente_svuota_il_buffer(monkeypatch):
    """10 -> 12 -> 0,5 J (driver ricaricato): restano solo i campioni del nuovo buffer."""
    src, _ = _make_source(monkeypatch)
    src._accept_emi_sample(1000.0, 10.0, 10_000_000_000)
    src._accept_emi_sample(1001.0, 12.0, 12_000_000_000)
    src._accept_emi_sample(1002.0, 0.5, 500_000_000)   # reset
    src._accept_emi_sample(1003.0, 1.5, 1_500_000_000)
    assert _pkg(src) == [(1002.0, 0.5), (1003.0, 1.5)]


# ------------------------------------------------------------------ 2
def test_valore_uguale_non_e_un_reset(monkeypatch):
    """Due letture identiche sono due campioni veri (consumo nullo), non un reset."""
    src, _ = _make_source(monkeypatch)
    src._accept_emi_sample(1000.0, 7.0, 7_000_000_000)
    src._accept_emi_sample(1001.0, 7.0, 7_000_000_000)
    assert len(src._emi_samples) == 2


# ------------------------------------------------------------------ 3
def test_reset_di_pkg_non_cancella_pp1_e_viceversa(monkeypatch):
    """I due domini hanno buffer separati: il reset di uno non tocca l'altro."""
    src, _ = _make_source(monkeypatch)
    src._accept_emi_sample(1000.0, 10.0, 10_000_000_000, (5.0, 100))
    src._accept_emi_sample(1001.0, 12.0, 12_000_000_000, (6.0, 101))
    # reset del solo PP1: il PKG continua a crescere
    src._accept_emi_sample(1002.0, 13.0, 13_000_000_000, (0.1, 102))
    assert _pkg(src) == [(1000.0, 10.0), (1001.0, 12.0), (1002.0, 13.0)]
    assert _pp1(src) == [(1002.0, 0.1)]
    # reset del solo PKG: il PP1 resta
    src._accept_emi_sample(1003.0, 0.2, 200_000_000, (0.2, 103))
    assert _pkg(src) == [(1003.0, 0.2)]
    assert _pp1(src) == [(1002.0, 0.1), (1003.0, 0.2)]


# ------------------------------------------------------------------ 4
def test_finestra_a_cavallo_del_reset_non_produce_un_delta(monkeypatch):
    """Nessuna estrapolazione oltre 1 s: la finestra che attraversa il reset risponde None."""
    src, _ = _make_source(monkeypatch)
    src._accept_emi_sample(1000.0, 10.0, 10_000_000_000)
    src._accept_emi_sample(1001.0, 12.0, 12_000_000_000)
    src._accept_emi_sample(1002.0, 0.5, 500_000_000)
    src._accept_emi_sample(1003.0, 1.5, 1_500_000_000)
    assert src.emi_window_energy_j(1000.0, 1003.0) is None
    # interamente dopo il reset: delta reale, non negativo
    assert src.emi_window_energy_j(1002.0, 1003.0) == pytest.approx(1.0)


# ------------------------------------------------------------------ 5
def test_provenienza_riparte_dal_valore_post_reset(monkeypatch):
    """raw_start/raw_end dopo il reset vengono dal nuovo contatore, non dal vecchio."""
    src, _ = _make_source(monkeypatch)
    src._accept_emi_sample(1000.0, 10.0, 10_000_000_000)
    src._accept_emi_sample(1001.0, 12.0, 12_000_000_000)
    src._accept_emi_sample(1002.0, 0.5, 500_000_000)
    src._accept_emi_sample(1003.0, 1.5, 1_500_000_000)
    from test_provenienza_contatore import _session
    prov = _session(src).window_counter_provenance(1002.0, 1003.0)
    assert prov["raw_start"] == pytest.approx(500_000_000)
    assert prov["raw_end"] == pytest.approx(1_500_000_000)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
