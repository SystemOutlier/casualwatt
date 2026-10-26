# -*- coding: utf-8 -*-
"""
tests/test_block_baseline.py — La baseline del blocco e i suoi derivati.

Perche' esiste. P1.5/P1.6/P1.7 congelano una sequenza precisa: tre finestre
pre, tre post, mediana (non media), range del pre, deriva, e
``budget_base_w = sqrt(half_range^2 + half_drift^2)``. ``P_post`` e'
diagnostica: non entra MAI nella sottrazione (P1.14). Queste formule vivono
nel runner v4 (``block_baseline``), non in produzione, e un errore qui
sposterebbe ogni numero della campagna senza far cadere nulla.

Che cosa verifica:
  1. mediana, range, ``dP``, semi-range e semi-drift su terne note;
  2. ``budget_base_w`` e' la radice della somma dei quadrati (non la somma) e
     ``budget_base_j`` e' il budget per la durata della richiesta;
  3. ``P_post`` non sposta ``baseline_pre_w``, che resta la mediana del pre;
  4. ``pre_windows_w`` conserva le tre repliche nell'ordine, non solo la
     mediana: la terna (min, med, max) e' la terna delle osservazioni;
  5. con meno di tre repliche le celle che non si possono calcolare restano
     VUOTE, non zero (una baseline inventata e' peggio di una assente);
  6. nel profiler la baseline del blocco sostituisce lo stato di sessione:
     ``baseline_energy_j = P_pre x dt_W`` e non usa ``SESSION.idle_power_w``.

Che cosa NON verifica: che tre finestre da 30 s siano sufficienti a stimare
la deriva (e' una scelta di disegno, P1.5) ne' la stabilita' della macchina.
"""
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


class _Sessione:
    """Sessione con idle di sessione volutamente diverso da P_pre."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 99.0          # non deve essere usato: c'e' baseline_pre_w
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self, n=3):
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


# ------------------------------------------------------------------ 1-4
def test_terne_note_mediana_range_deriva_e_budget():
    """10,0/10,4/10,2 pre e 10,6/10,8/10,7 post: tutti i derivati a mano."""
    b = v4.block_baseline([10.0, 10.4, 10.2], [10.6, 10.8, 10.7])

    assert b["baseline_pre_w"] == pytest.approx(10.2)
    assert b["baseline_post_w"] == pytest.approx(10.7)
    assert b["pre_range_w"] == pytest.approx(0.4)
    assert b["dP"] == pytest.approx(0.5)
    assert b["half_range_pre_w"] == pytest.approx(0.2)
    assert b["half_drift_w"] == pytest.approx(0.25)
    # radice della somma dei quadrati, NON somma aritmetica
    assert b["budget_base_w"] == pytest.approx(math.hypot(0.2, 0.25))
    assert b["budget_base_w"] != pytest.approx(0.2 + 0.25)
    # le tre repliche restano nell'ordine dato
    assert b["pre_windows_w"] == "10.000000;10.400000;10.200000"
    assert b["post_windows_w"] == "10.600000;10.800000;10.700000"
    # budget per richiesta: dt_W x budget_base_w
    assert v4.budget_base_j(2.0, b["budget_base_w"]) == pytest.approx(
        2.0 * math.hypot(0.2, 0.25))


# ------------------------------------------------------------------ 3
def test_il_post_non_sposta_la_baseline_pre():
    """La mediana del pre resta 10,2 anche con un post molto diverso."""
    b = v4.block_baseline([10.0, 10.2, 10.4], [30.0, 30.0, 30.0])
    assert b["baseline_pre_w"] == pytest.approx(10.2)
    assert b["baseline_post_w"] == pytest.approx(30.0)
    assert b["dP"] == pytest.approx(19.8)


# ------------------------------------------------------------------ 5
def test_meno_di_tre_repliche_lascia_vuoto_non_zero():
    """Una sola replica non produce un range: la cella resta vuota."""
    b = v4.block_baseline([10.0], None)
    assert b["baseline_pre_w"] == pytest.approx(10.0)
    assert b["pre_range_w"] == ""
    assert b["half_range_pre_w"] == ""
    assert b["budget_base_w"] == ""
    assert b["baseline_post_w"] == ""

    empty = v4.block_baseline([], [])
    assert empty["baseline_pre_w"] == ""
    assert empty["pre_windows_w"] == ""


def test_repliche_non_finite_scartate_prima_della_mediana():
    """NaN/inf non entrano nella mediana: una replica illeggibile non e' un valore."""
    b = v4.block_baseline([10.0, float("nan"), 10.2, float("inf")], None)
    assert b["baseline_pre_w"] == pytest.approx(10.1)
    assert b["pre_range_w"] == pytest.approx(0.2)


# ------------------------------------------------------------------ 6
def test_baseline_del_blocco_non_usa_lo_stato_di_sessione():
    """P_pre=10,0 contro idle di sessione 99,0: baseline_energy_j = 10 x dt_W."""
    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Sessione()
    res = prof.profile_window(
        T0, T0 + 1.0, ollama_pids=[7], direct_cpu_delta=6.0,
        direct_busy_delta=8.0, baseline_pre_w=10.0)

    assert res.idle_power_w == pytest.approx(10.0)
    assert res.baseline_energy_j == pytest.approx(10.0)
    assert res.baseline_pre_w == pytest.approx(10.0)
    assert res.active_energy_j == pytest.approx(90.0)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
