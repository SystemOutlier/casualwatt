# -*- coding: utf-8 -*-
"""
tests/test_gpu_skew_and_gui_message.py -- due punti FASE 3 non coperti prima.

Perche' esiste.
  1. La calibrazione GPU e il termine condizionale di ``settle_idle`` usano
     il contatore cumulativo del device (NVML o AMD SMI) e il tempo monotono
     della sessione. Il device espone un proprio timestamp, in nanosecondi,
     che pero' NON e' un fuso orario allineato a ``time.monotonic``: sul
     ramo AMD SMI la specifica lo dichiara come ``controllo di avanzamento``
     e mai come una durata. La finestra deve therefore restare divisa per
     ``span = last.t - first.t`` (monotono) e NON per ``(ts1 - ts0) / 1e9``
     (device): se le due basi fossero scambiate, una deriva di qualche ppm
     fra QPC e clock del device diventerebbe un errore sistematico sulla
     baseline, e la riga lo presenterebbe come misura.
  2. Il ramo "altrimenti" della calibrazione idle nella GUI diceva sempre
     la stessa frase. Sono pero' due fatti distinti -- ``gpu_mon`` assente
     o non disponibile (nessun monitor) e ``gpu_mon.available=True`` con
     ``energy_counter=False`` (monitor si', contatore no) -- e solo il
     secondo lascia la riga in sovrastima dichiarata con
     ``gpu_idle_provenance='missing'``. Un messaggio che dice "nessuna GPU"
     quando la GPU c'e' e' una dichiarazione sbagliata, non una forma.

Che cosa verifica:
  1. ``_gpu_power_window`` con device clock che corre meta' del monotono:
     il denominatore della media e' ``span`` monotono, non il timestamp del
     device; la catena dichiarata resta ``<backend>-energy``.
  2. ``_gpu_idle_missing_message(gpu_mon=None)`` parla di "nessun monitor".
  3. ``_gpu_idle_missing_message`` con ``available=True`` e
     ``energy_counter=False`` nomina la scheda e la provenienza ``missing``,
     e non dice "nessuna GPU".
  4. ``_gpu_idle_missing_message`` con ``available=False`` ricade nel ramo
     "nessun monitor" (non inventa una scheda presente).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.energy_session import EnergySession, SystemSample  # noqa: E402
from gui.benchmark_panel import _gpu_idle_missing_message  # noqa: E402


class _FakeGpuMonitor:
    backend = "amdsmi"

    def __init__(self, *, available=True, counter=False, name="AMD Radeon"):
        self.available = available
        self.energy_counter = counter
        self.energy_counter_reason = "" if counter else "contatore assente"
        self.error = "" if available else "LibraryNotFound"
        self.index = 0
        self.name = name

    def get_amd_uuid(self):
        return "fake-uuid-amd"


def _sample(t, mJ, ts_ns):
    return SystemSample(
        t=t, wall=0.0, package_energy_j=0.0, cpu_busy_seconds=0.0,
        cpu_percent=0.0, gpu_power_w=1.0,
        gpu_energy_mj=mJ, gpu_energy_ts_ns=ts_ns,
    )


def test_denominatore_e_monotono_non_device_clock(monkeypatch):
    """Monotono 10 s, device clock 5 s: ``P = d_E / 10`` (monotono), non /5.

    Se la produzione dividesse per il delta del timestamp del device, la
    potenza raddoppierebbe: 10 000 mJ / 5 s = 2 W. Il denominatore corretto
    e' ``span = last.t - first.t = 10.0 s`` e la media e' 1 W. La catena
    resta ``amdsmi-energy`` perche' il timestamp avanza, quindi non e' una
    lettura ferma.
    """
    s = EnergySession()
    s._gpu = _FakeGpuMonitor(available=True, counter=True)
    # due campioni a monotono t=0.0 e t=10.0; il device clock copre 5 s
    s._samples = [
        _sample(0.0, 20_000.0, 1_000_000_000),   # 1 s dal boot del device
        _sample(10.0, 30_000.0, 6_000_000_000),  # 6 s dal boot del device
    ]

    w, chain, reason = s._gpu_power_window(0.0, 10.0)

    assert chain == "amdsmi-energy"
    assert reason == ""
    # 10 000 mJ = 10 J su 10 s -> 1 W (monotono), NON 2 W (device clock)
    assert w == pytest.approx(1.0)


def test_timestamp_fermo_anche_con_delta_positivo_e_invalido(monkeypatch):
    """stesso ts ai due campioni -> lettura non avanzata, non una finestra 0 W.

    E' il parallelo GPU della regola ``b3b12ffe`` sul package. Il ``d_mj``
    potrebbe essere positivo per una coincidenza; finche' il timestamp del
    device non avanza, la lettura non e' una nuova misura.
    """
    s = EnergySession()
    s._gpu = _FakeGpuMonitor(available=True, counter=True)
    s._samples = [
        _sample(0.0, 20_000.0, 5_000_000_000),
        _sample(10.0, 25_000.0, 5_000_000_000),  # timestamp identico
    ]

    w, chain, reason = s._gpu_power_window(0.0, 10.0)

    assert w is None
    assert chain == ""
    assert "fermo" in reason


# ------------------------------------------------------------------ messaggi
def test_msg_nessun_monitor():
    """``gpu_mon=None`` -> "nessun monitor GPU attivo", non "senza contatore"."""
    msg = _gpu_idle_missing_message(None)
    assert "Nessun monitor GPU attivo" in msg
    assert "senza contatore" not in msg


def test_msg_monitor_presente_ma_senza_contatore_cumulativo():
    """``available=True`` e ``energy_counter=False`` -> nomina la GPU e la
    provenienza ``invalid-baseline``, non dice che la macchina e' senza GPU."""
    mon = _FakeGpuMonitor(available=True, counter=False, name="RTX 4060")
    msg = _gpu_idle_missing_message(mon)
    assert "GPU rilevata" in msg
    assert "RTX 4060" in msg
    assert "senza contatore cumulativo" in msg
    assert "gpu_idle_provenance='invalid-baseline'" in msg
    # Non deve mai affermare che la macchina non ha una GPU
    assert "Nessun monitor GPU attivo" not in msg


def test_msg_monitor_non_disponibile_ricade_su_nessun_monitor():
    """``available=False`` (es. LibraryNotFound) -> stesso ramo "nessun monitor".
    """
    mon = _FakeGpuMonitor(available=False, counter=False)
    msg = _gpu_idle_missing_message(mon)
    assert "Nessun monitor GPU attivo" in msg
