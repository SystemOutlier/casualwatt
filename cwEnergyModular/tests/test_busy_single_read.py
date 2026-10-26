# -*- coding: utf-8 -*-
"""
tests/test_busy_single_read.py — Il busy di sistema e' UNA lettura.

Perche' esiste. ``_system_busy_seconds`` e' il denominatore della quota di
attribuzione. La versione precedente faceva due letture: ``cpu_times()`` per
l'idle e ``cpu_times(percpu=True)`` per il totale. Fra le due il sistema
poteva accumulare tempo, e il busy risultava sottostimato di quella
quantita'. Ora totale e idle vengono dalla stessa chiamata per-core:
``busy = somma(tutti i campi) - idle``. Qui si verifica che la chiamata sia
una sola e che la sottrazione sia quella, senza toccare l'hardware.

Che cosa verifica:
  1. ``psutil.cpu_times`` viene chiamata UNA volta, con ``percpu=True``;
  2. il risultato e' ``totale - idle`` sui campi di quella stessa lettura
     (iowait/irq/softirq contano come busy: non sono idle);
  3. se la lettura solleva, la funzione ritorna 0.0 senza propagare
     l'eccezione (un denominatore assente e' dichiarato dal chiamante, non
     un crash del sampler);
  4. il risultato non e' mai negativo.

Che cosa NON verifica: che il busy di sistema corrisponda all'energia (e'
l'ipotesi di attribuzione) ne' la cadenza del sampler.
"""
import sys
from collections import namedtuple
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import energy.energy_session as es  # noqa: E402
from energy.energy_session import EnergySession  # noqa: E402

_CpuTimes = namedtuple(
    "scputimes",
    ["user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal"])


def test_una_sola_lettura_e_sottrazione_totale_meno_idle(monkeypatch):
    """Due core: totale 130 s, idle 40 s -> busy 90 s, con una sola chiamata."""
    calls = []

    def _fake_cpu_times(percpu=False):
        calls.append(percpu)
        return [
            _CpuTimes(30.0, 0.0, 10.0, 20.0, 0.0, 0.0, 0.0, 0.0),
            _CpuTimes(20.0, 0.0, 20.0, 20.0, 5.0, 3.0, 2.0, 0.0),
        ]

    monkeypatch.setattr(es.psutil, "cpu_times", _fake_cpu_times)

    busy = EnergySession._system_busy_seconds()

    assert calls == [True], "una sola lettura per-core: due letture sfasano il delta"
    # totale = (30+10+20) + (20+20+20+5+3+2) = 60 + 70 = 130; idle = 40
    assert busy == pytest.approx(90.0)


def test_lettura_che_solleva_degrada_a_zero_senza_crash(monkeypatch):
    """Un errore psutil non interrompe il campionamento: busy 0.0 dichiarato."""
    def _boom(percpu=False):
        raise OSError("psutil non disponibile")

    monkeypatch.setattr(es.psutil, "cpu_times", _boom)
    assert EnergySession._system_busy_seconds() == 0.0


def test_il_risultato_non_e_mai_negativo(monkeypatch):
    """Campo cumulato negativo (lettura malformata): 0.0, non un numero negativo.

    Con campi non negativi l'idle non puo' superare il totale, perche' il
    totale li include tutti: il ramo del clamp si esercita solo su una lettura
    malformata, ed e' quello che questo test copre.
    """
    monkeypatch.setattr(
        es.psutil, "cpu_times",
        lambda percpu=False: [_CpuTimes(-10.0, 0.0, 1.0, 5.0, 0.0, 0.0, 0.0, 0.0)])
    assert EnergySession._system_busy_seconds() == 0.0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
