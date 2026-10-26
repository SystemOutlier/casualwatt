# -*- coding: utf-8 -*-
"""
tests/test_edge_window.py — La finestra energetica e' quella dei bordi.

Perche' esiste. Prima della v4 l'energia era integrata sulla finestra Python
(``t0``/``t1`` del client HTTP), mentre il contatore e i ``cpu_times`` erano
letti attorno a quella finestra. Con i bordi di misura la finestra energetica
e' la differenza dei timestamp del contatore, quella CPU e' il tratto in cui
sono stati letti i ``cpu_times``, e lo spread delle due letture e' un numero,
non una speranza. Questo test costruisce i bordi a mano: verifica la
dichiarazione, non il registro.

Che cosa verifica:
  1. con due ``ts_100ns`` noti ``dt_W_s`` e' la loro differenza e
     ``edge_time_source = "emi-counter-ts"`` (la base dell'energia);
  2. senza contatore ``dt_W_s`` viene dalla coppia monotona e la sorgente e'
     ``python-monotonic``: la base e' dichiarata, non presunta;
  3. ``cpu_share_window_s`` e' il tratto CPU (``t_cpu_mid``), NON ``dt_W_s``:
     le due finestre possono differire e il CSV lo dice;
  4. ``edge_spread_s`` e' il massimo dei due bordi e i timestamp EMI agli
     estremi finiscono nei campi dedicati;
  5. l'energia con contatore e' la differenza diretta (``direct-ioctl``) e la
     baseline usa ``dt_W_s``, non la finestra Python.

Che cosa NON verifica: la precisione dei timestamp del driver (dipende
dall'hardware) ne' la copertura del buffer EMI (ha i suoi test).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0
UTC0 = "2026-10-25T10:00:00.000+00:00"
UTC1 = "2026-10-25T10:00:00.450+00:00"


class _Sessione:
    """Sessione sintetica: il buffer restituisce 100 J sulla finestra."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self, n=4):
        self.samples = [
            SimpleNamespace(
                t=T0 + i * 0.5, wall=0.0, package_energy_j=10.0 * i,
                cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                ollama_pids=(7,), ollama_cpu_seconds=0.5 * i,
                gpu_power_w=None, gpu_util_pct=None,
            )
            for i in range(n)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        return 100.0


def _edge(t_counter_mono, t_cpu_mid, spread, utc, counter=None):
    return {
        "counter": counter,
        "counter_error": "" if counter else "non richiesto",
        "t_wall": t_counter_mono,
        "t_wall_utc": utc,
        "t_counter_mono": t_counter_mono,
        "t_cpu_mid": t_cpu_mid,
        "edge_spread_s": spread,
    }


def _counter(j, ts, pwh):
    return {"pkg_j": j, "pkg_pwh": pwh, "ts_100ns": ts, "pp1_j": None}


def _profile(e0, e1):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Sessione()
    return prof.profile_window(
        e0["t_counter_mono"], e1["t_counter_mono"],
        ollama_pids=[7], direct_cpu_delta=6.0, direct_busy_delta=8.0,
        baseline_pre_w=10.0, edge_start=e0, edge_end=e1,
    )


# ------------------------------------------------------------------ 1, 3, 4, 5
def test_dt_w_dai_timestamp_del_contatore_e_finestra_cpu_distinta():
    """ts 0,5 s, tratto CPU 0,65 s: le due finestre sono diverse e dichiarate."""
    e0 = _edge(50.00, 50.30, 0.02, UTC0, _counter(100.0, 10_000_000, 1000.0))
    e1 = _edge(50.45, 50.95, 0.05, UTC1, _counter(112.0, 15_000_000, 1120.0))

    res = _profile(e0, e1)

    # 1) la base dell'energia e' il timestamp del record (5 000 000 x 100 ns
    #    = 0,5 s), non la finestra monotona (0,45 s)
    assert res.dt_W_s == pytest.approx(0.5)
    assert res.duration_s == pytest.approx(0.5)
    assert res.edge_time_source == "emi-counter-ts"
    # 3) la finestra CPU e' il tratto dei cpu_times, non dt_W
    assert res.cpu_share_window_s == pytest.approx(0.65)
    assert res.cpu_share_window_s != pytest.approx(res.dt_W_s)
    # 4) spread = massimo dei due bordi; timestamp grezzi agli estremi
    assert res.edge_spread_s == pytest.approx(0.05)
    assert res.emi_ts_start_100ns == 10_000_000
    assert res.emi_ts_end_100ns == 15_000_000
    assert res.edge_start_utc == UTC0
    assert res.edge_end_utc == UTC1
    # 5) energia diretta dal contatore, baseline su dt_W
    assert res.emi_edge_source == "direct-ioctl"
    assert res.package_window_source == "exact-counter"
    assert res.package_energy_j == pytest.approx(12.0)
    assert res.raw_start == pytest.approx(1000.0)
    assert res.raw_end == pytest.approx(1120.0)
    assert res.raw_unit == "pWh"
    assert res.baseline_pre_w == pytest.approx(10.0)
    assert res.baseline_energy_j == pytest.approx(5.0)   # 10 W x 0,5 s
    assert res.active_energy_j == pytest.approx(7.0)


# ------------------------------------------------------------------ 2
def test_senza_contatore_dt_w_dalla_coppia_monotona():
    """Bordi senza contatore: dt_W dalla coppia monotona, sorgente dichiarata."""
    e0 = _edge(50.00, 50.10, 0.01, UTC0, None)
    e1 = _edge(50.50, 50.70, 0.04, UTC1, None)

    res = _profile(e0, e1)

    assert res.dt_W_s == pytest.approx(0.5)
    assert res.edge_time_source == "python-monotonic"
    assert res.cpu_share_window_s == pytest.approx(0.6)
    assert res.edge_spread_s == pytest.approx(0.04)
    assert res.emi_ts_start_100ns is None
    assert res.emi_ts_end_100ns is None
    # il contatore manca: l'energia viene dal buffer e lo dichiara
    assert res.emi_edge_source == "buffer-interp"
    assert res.package_energy_j == pytest.approx(100.0)
    assert any("differenza diretta del contatore non disponibile" in n
               for n in res.notes)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
