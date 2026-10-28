# -*- coding: utf-8 -*-
"""
test_metodo_ammissibile.py — solo i metodi che misurano possono produrre un numero.

Perche' questo file esiste. Il campo ``judge_energy_j`` viene da
``benchmark_unified._estimate_judge_energy``, che fino al 24/10 aveva una COPIA
locale dell'elenco dei metodi ammessi ("power-integration",
"librehardwaremonitor-energy", "emi-counter", "energy-file"). La copia era ferma
al 22/10: il backend RAPL (``energy/rapl_backend.py``, aggiunto il 21/10 e
impostato come ``method = "rapl"`` in ``energy_session._activate_rapl_backend``)
non c'era, quindi su Linux con contatore funzionante la finestra del giudice
sarebbe risultata N/A. Un elenco duplicato che diverge dal suo significato e'
invisibile finche' non lo si guarda: qui l'elenco unico e'
``energy_session.MEASURED_METHODS``, e questi test ne fissano il comportamento.

Cosa NON verifica: che il numero prodotto sia giusto. Verifica solo quali stati
del backend possono esprimere un numero e quali devono esprimere N/A -- la
regola "nessuna stima inventata" del cap. 3, non l'accuratezza del contatore
(quella e' negli harness di Appendice C e nei verbali di experiment_results/).

Le docstring dei test sono scritte insieme ai corpi il 24/10/2026.
"""
from types import SimpleNamespace

import pytest

import benchmark_unified as bu
from energy.energy_session import MEASURED_METHODS


def _fake_session(metodo: str, raw_j: float = 5.0, idle_w: float = 1.0):
    """SESSION sintetica: contatore che dice raw_j sulla finestra, idle noto."""
    return SimpleNamespace(
        source_method=metodo,
        idle_power_w=idle_w,
        package_energy_exact_between=lambda a, b, excl=None: raw_j,
    )


@pytest.mark.parametrize("metodo", sorted(MEASURED_METHODS))
def test_ogni_metodo_di_misura_produce_un_numero(monkeypatch, metodo):
    """Ogni metodo in MEASURED_METHODS deve esprimere l'energia della finestra."""
    monkeypatch.setattr(bu, "SESSION", _fake_session(metodo))
    # 5,0 J letti meno baseline 1,0 W per 1,0 s di finestra
    assert bu._estimate_judge_energy(100.0, 101.0) == pytest.approx(4.0)


@pytest.mark.parametrize("metodo", ["unavailable", "librehardwaremonitor", ""])
def test_stato_non_di_misura_produce_none(monkeypatch, metodo):
    """Senza contatore leggibile il risultato e' None (N/A nel CSV), mai uno zero."""
    assert metodo not in MEASURED_METHODS
    monkeypatch.setattr(bu, "SESSION", _fake_session(metodo))
    assert bu._estimate_judge_energy(100.0, 101.0) is None


def test_la_lista_ammessi_non_e_piu_duplicata():
    """benchmark_unified usa la costante condivisa: niente seconda copia da far divergere."""
    assert bu.MEASURED_METHODS is MEASURED_METHODS
    # 'rapl' e' il caso storico che la copia locale perdeva
    assert "rapl" in MEASURED_METHODS


def test_contatore_che_non_legge_resta_none(monkeypatch):
    """Metodo ammesso ma lettura None (bordo fuori buffer): N/A, non zero."""
    sess = _fake_session("emi-counter")
    sess.package_energy_exact_between = lambda a, b, excl=None: None
    monkeypatch.setattr(bu, "SESSION", sess)
    assert bu._estimate_judge_energy(100.0, 101.0) is None
