# -*- coding: utf-8 -*-
"""
tests/test_cpu_share_window.py — Il denominatore dello share CPU e' dichiarato.

Perche' esiste. ``rev_metodo.DOCX`` §2(b): "la quota va definita rispetto allo
stesso intervallo temporale della misura energetica, normalizzata alla
capacita' realmente disponibile". Il calcolo era gia' coerente (i delta sono
sulla stessa finestra, le sottofinestre del judge vengono escluse), ma il CSV
non diceva ne' su quale intervallo ne' con quanti core il rapporto era stato
costruito: un lettore non poteva verificare che ``d_busy_s`` non superasse la
capacita' fisica.

Che cosa verifica:
  1. ``cpu_share_window_s`` e' la finestra dell'energia (duration_s), non
     l'intervallo richiesto in config;
  2. ``cpu_busy_capacity_cores`` e' il numero di core logici su cui e'
     aggregato ``cpu_busy_seconds`` (psutil percpu);
  3. la disuguaglianza verificabile: d_busy_s <= core x finestra;
  4. lo share resta d_ollama/d_busy (i due campi nuovi sono dichiarativi,
     non cambiano il numero);
  5. con una sottofinestra esclusa la finestra dichiarata si riduce, la
     capacita' no;
  6. le due colonne esistono in coda e l'export le scrive.

Che cosa NON verifica: che la capacita' dichiarata coincida con quella
"realmente disponibile" al netto di turbo/throttling. Quella e' una proprieta'
della macchina, non del CSV: qui si controlla che il denominatore sia
dichiarato e coerente con i delta.
"""
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil  # noqa: E402
import pytest  # noqa: E402

from casualwatt_csv_export import CSV_COLUMNS, export_results_csv  # noqa: E402
from energy.energy_session import SystemSample  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


class _Sessione:
    """Sessione minima con campioni a passo 0.5 s e nessun contatore esatto."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self, n=3):
        self.samples = [
            SystemSample(t=T0 + i * 0.5, wall=0.0,
                         package_energy_j=10.0 * i,
                         cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                         ollama_pids=(7,), ollama_cpu_seconds=0.5 * i)
            for i in range(n)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]


def _profile(n=3, exclude=None):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Sessione(n=n)
    return prof.profile_window(T0, T0 + (n - 1) * 0.5,
                               ollama_pids=[7], exclude_windows=exclude)


# ------------------------------------------------------------------ 1-3
def test_finestra_e_capacita_dichiarate_e_coerenti():
    """Finestra = duration_s, capacita' = core logici; d_busy non supera il tetto fisico."""
    res = _profile(n=5)   # 2,0 s di finestra
    assert res.cpu_share_window_s == pytest.approx(2.0)
    assert res.cpu_busy_capacity_cores == int(psutil.cpu_count(logical=True) or 0)
    assert res.cpu_busy_capacity_cores >= 1
    assert res.d_busy_s <= res.cpu_busy_capacity_cores * res.cpu_share_window_s + 1e-9


# ------------------------------------------------------------------ 4
def test_i_campi_nuovi_non_cambiano_lo_share():
    """d_ollama = 2,0 s, d_busy = 4,0 s: share 0,5 come prima, con il denominatore dichiarato."""
    res = _profile(n=5)   # ollama: 0,5*4 = 2,0 s; busy: 1,0*4 = 4,0 s
    assert res.d_ollama_cpu_s == pytest.approx(2.0)
    assert res.d_busy_s == pytest.approx(4.0)
    assert res.cpu_time_share == pytest.approx(0.5)


# ------------------------------------------------------------------ 5
def test_esclusione_riduce_la_finestra_ma_non_la_capacita():
    """Una sottofinestra di 0,5 s esclusa riduce duration_s/window_s, non i core."""
    base = _profile(n=5)
    res = _profile(n=5, exclude=[(T0 + 1.0, T0 + 1.5)])
    assert res.cpu_share_window_s == pytest.approx(1.5)
    assert res.cpu_share_window_s < base.cpu_share_window_s
    assert res.cpu_busy_capacity_cores == base.cpu_busy_capacity_cores
    assert res.d_busy_s < base.d_busy_s, "il delta busy esclude il segmento"


# ------------------------------------------------------------------ 6
def test_colonne_e_export(tmp_path):
    """Le due colonne sono in coda, una sola volta, e i valori arrivano nel CSV."""
    assert CSV_COLUMNS.count("cpu_share_window_s") == 1
    assert CSV_COLUMNS.count("cpu_busy_capacity_cores") == 1
    # I due campi del denominatore restano adiacenti; dopo di loro la sola
    # coda aggiunta dalla correzione dell'attribuzione (P2), accodata per non
    # spostare nessuna colonna esistente.
    i = CSV_COLUMNS.index("cpu_share_window_s")
    assert CSV_COLUMNS[i:i + 2] == [
        "cpu_share_window_s", "cpu_busy_capacity_cores"]
    assert CSV_COLUMNS[i + 2:] == [
        "package_energy_raw_j", "active_energy_raw_j", "active_valid",
        "cpu_time_share_raw", "share_anomaly"]

    p = tmp_path / "out.csv"
    export_results_csv([{"run_id": "r1", "cpu_share_window_s": 1.5,
                         "cpu_busy_capacity_cores": 20}], p, mode="w")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        row = next(csv.DictReader(fh))
    assert row["cpu_share_window_s"] == "1.5"
    assert row["cpu_busy_capacity_cores"] == "20"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
