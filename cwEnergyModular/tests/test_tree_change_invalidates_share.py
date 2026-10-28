# -*- coding: utf-8 -*-
"""
tests/test_tree_change_invalidates_share.py — Albero cambiato: la quota non si calcola.

Perche' esiste. ``E_worker = E_attiva · d_ollama/d_busy`` e' una stima: se un
worker presente a t_start non e' piu' leggibile a t_end, il suo tempo CPU non
e' nel numeratore e la quota e' sottostimata in una direzione sola. In quel
caso la v4 NON calcola la quota e NON la sostituisce con un fallback che
eredita la stessa perdita (D1 approvata): conserva la riga, gli ingressi
grezzi e i flag, e mette zero solo come valore convenzionale dichiarato.

Che cosa verifica:
  1. con ``engine_tree_changed=True``: ``cpu_time_share_raw is None``,
     ``cpu_time_share == 0``, ``ollama_active_energy_j == 0``,
     ``cpu_time_share_valid is False``, sorgente
     ``not-computed-tree-changed``, nota presente; ``d_ollama_cpu_s`` e
     ``d_busy_s`` restano gli ingressi grezzi;
  2. senza il flag il comportamento e' quello di sempre (share 0,75 e
     E_worker = 90 · 0,75), quindi il flag non cambia il percorso valido;
  3. D4: il percorso storico che passa solo ``worker_exit_in_window`` non
     viene riscritto, ma la quota e' dichiarata NON valida con una nota: i
     due nomi descrivono lo stesso insieme, non sono due prove indipendenti.

Che cosa NON verifica: che il costo CPU perso sia recuperabile (non lo e':
la finestra non e' integra) ne' che il flag scatti su un albero reale
(``worker_tree`` ha i suoi test).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


class _Sessione:
    """Sessione sintetica: 100 J di package, 10 W di idle, finestra di 1 s."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 10.0
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


def _profile(**kwargs):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Sessione()
    kwargs.setdefault("ollama_pids", [7])
    kwargs.setdefault("direct_cpu_delta", 6.0)   # 6 s di CPU worker
    kwargs.setdefault("direct_busy_delta", 8.0)  # 8 s di busy di sistema
    return prof.profile_window(T0, T0 + 1.0, **kwargs)


# ------------------------------------------------------------------ 1
def test_albero_cambiato_quota_non_calcolata_ma_riga_conservata():
    """Flag vero: zero convenzionale + flag + sorgente; gli ingressi grezzi restano."""
    res = _profile(engine_tree_changed=True,
                   worker_exit_in_window=True,
                   tree_born="99:1234.500000",
                   tree_lost="42:1000.000000")

    assert res.engine_tree_changed is True
    assert res.cpu_time_share_raw is None
    assert res.cpu_time_share == 0.0
    assert res.ollama_active_energy_j == 0.0
    assert res.cpu_time_share_valid is False
    assert res.cpu_share_source == "not-computed-tree-changed"
    # gli ingressi grezzi NON vengono azzerati: sono la prova del perche'
    assert res.d_ollama_cpu_s == pytest.approx(6.0)
    assert res.d_busy_s == pytest.approx(8.0)
    assert res.tree_born == "99:1234.500000"
    assert res.tree_lost == "42:1000.000000"
    # l'energia attiva resta quella misurata: non si azzera il dato, si
    # rifiuta l'attribuzione
    assert res.active_energy_j == pytest.approx(90.0)
    assert any("engine_tree_changed" in n for n in res.notes)


# ------------------------------------------------------------------ 2
def test_senza_flag_la_quota_e_quella_di_sempre():
    """Flag falso: share 6/8 = 0,75, E_worker = 90 · 0,75, sorgente direct-edge."""
    res = _profile(engine_tree_changed=False)

    assert res.engine_tree_changed is False
    assert res.cpu_time_share_raw == pytest.approx(0.75)
    assert res.cpu_time_share == pytest.approx(0.75)
    assert res.cpu_time_share_valid is True
    assert res.cpu_share_source == "direct-edge"
    assert res.ollama_active_energy_j == pytest.approx(67.5)


# ------------------------------------------------------------------ 3
def test_D4_percorso_storico_dichiara_la_quota_non_valida():
    """Solo ``worker_exit_in_window``: numero storico, ma validita' falsa e nota D4."""
    res = _profile(engine_tree_changed=False, worker_exit_in_window=True)

    # il numero non cambia (compatibilita' del percorso di produzione) ...
    assert res.cpu_time_share == pytest.approx(0.75)
    assert res.ollama_active_energy_j == pytest.approx(67.5)
    # ... ma non e' dichiarato integro, e il perche' e' scritto
    assert res.cpu_time_share_valid is False
    assert any("non ha passato il flag v4" in n for n in res.notes)
    assert any("non due prove indipendenti" in n for n in res.notes)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
