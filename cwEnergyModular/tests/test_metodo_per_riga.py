# -*- coding: utf-8 -*-
"""
tests/test_metodo_per_riga.py — Il canale di misura del package vive nella RIGA.

Esecuzione (dalla cartella cwEnergyModular/):
    python -m pytest tests/test_metodo_per_riga.py -v
    python tests/test_metodo_per_riga.py

Perche' esiste. alt_lhm.DOCX (24/10) chiede che ogni misura sia
auto-descrittiva: "energia_joules, measurement_type, domain, start/end,
raw_start/end, sampling_interval, quality_flags, backend_version". CasualWatt
scaricava il nome del canale SOLO dentro stringhe composite
(cpu_attribution_method, measurement_boundary) e nel file di run metadata
(``cpu_energy_source_method``). Il CSV dei risultati pero' ACCUMULA righe di
run diversi: una riga letta tre mesi dopo non dice se i suoi joule vengono da
``emi-counter``, da ``power-integration``, da ``rapl`` o da nessun contatore, e
un valore energetico senza canale e' esattamente il difetto che la tesi
rimprovera agli altri strumenti.

Che cosa verifica:
  1. la colonna ``energy_calculation_method`` esiste, una volta sola, in coda
     (l'ordine delle colonne precedenti e' bloccato da
     test_energy_corrections.py: test_P2_colonna_csv_accodata_senza_cambiare_ordine);
  2. il profiler scrive il canale ATTIVO per ogni canale misurato, incluso
     ``rapl``;
  3. il canale e' orthogonal alla qualita' della lettura: ``package_window_source``
     puo' essere "samples-fallback" o "unavailable" mentre il canale resta
     quello reale -- due domande diverse, due campi diversi;
  4. ``ensure_header`` migra un CSV storico scritto con lo schema precedente,
     senza perdere le celle esistenti e senza disallineare le righe;
  5. due righe scritte con canali diversi restano distinguibili dopo la
     rilettura del file.

Che cosa NON verifica: che il numero nel canale sia corretto. Quella e' una
domanda di validazione fisica (EMI contro SRUM, contro LHM a finestra uguale)
che questi test non toccano: qui si controlla SOLO che l'etichetta arrivi dove
deve arrivare.
"""
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from casualwatt_csv_export import (  # noqa: E402
    CSV_COLUMNS, ensure_header, export_results_csv,
)
from energy.energy_session import MEASURED_METHODS, SystemSample  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


class _SoloCanale:
    """Sessione minima: conta solo quale canale e' attivo e se ci sono campioni.

    Nessun ``package_energy_exact_between``: il profiler passa dal percorso sui
    campioni, che e' il ramo piu' corto e non richiede un'integrazione finta.
    ``con_energia=False`` modella il canale dichiarato ma senza contatore: i
    campioni esistono (CPU-time, busy) e ``package_energy_j`` resta None.
    """

    def __init__(self, method, n_samples=3, con_energia=True):
        self.source_method = method
        self.interval_s = 0.5
        self.idle_power_w = 10.0
        self.idle_provenance = "calibrated"
        self.idle_gpu_power_w = None
        self._gpu = SimpleNamespace(available=False, index=0, name="")
        self.samples = [
            SystemSample(t=T0 + i * 0.5, wall=0.0,
                         package_energy_j=(10.0 * i if con_energia else None),
                         cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                         ollama_pids=(7,), ollama_cpu_seconds=0.5 * i,
                         gpu_power_w=None, gpu_util_pct=None)
            for i in range(n_samples)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]


def _profile(method, n_samples=3, con_energia=True):
    sess = _SoloCanale(method, n_samples=n_samples, con_energia=con_energia)
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(T0, T0 + 1.0, ollama_pids=[7])


# ------------------------------------------------------------------ 1
def test_colonna_esiste_una_sola_volta_ed_e_in_coda():
    """energy_calculation_method compare una volta e apre il blocco di provenienza accodato il 24/10."""
    assert CSV_COLUMNS.count("energy_calculation_method") == 1
    # 24/10: il contratto alt_lhm §3 accoda i grezzi dopo il canale. La coda
    # si verifica come LISTA (stessa lezione del test in test_energy_corrections).
    CODA = ["energy_calculation_method",
            "raw_start", "raw_end", "raw_unit", "domain",
            "sampling_interval_observed_s", "backend_version",
            "cpu_share_window_s", "cpu_busy_capacity_cores"]
    assert CSV_COLUMNS[-len(CODA):] == CODA
    # il blocco storico non si e' mosso: keep_alive_sent era la coda del 23/10
    assert CSV_COLUMNS[-len(CODA) - 1] == "keep_alive_sent"


# ------------------------------------------------------------------ 2
@pytest.mark.parametrize("method", sorted(MEASURED_METHODS))
def test_il_canale_attivo_finisce_nella_riga(method):
    """Qualunque canale misurato scrive il PROPRIO nome nel risultato della finestra."""
    assert _profile(method).energy_calculation_method == method


def test_canale_indisponibile_dichiara_zero_non_una_stima():
    """Canale senza contatore: il nome resta 'unavailable' e l'energia package e' 0, non una stima."""
    res = _profile("unavailable", con_energia=False)
    assert res.energy_calculation_method == "unavailable"
    assert res.package_window_source == "unavailable"
    assert res.package_energy_j == pytest.approx(0.0)
    assert "DISABLED" in res.measurement_boundary


# ------------------------------------------------------------------ 3
def test_canale_e_diverso_da_quanto_bene_ho_letto():
    """'emi-counter' + bordi non leggibili = ancora emi-counter: package_window_source risponde ad altra domanda."""
    res = _profile("emi-counter")
    assert res.energy_calculation_method == "emi-counter"   # QUALE canale
    assert res.package_window_source == "samples-fallback"  # COME l'ho letto
    assert "emi-counter" in res.cpu_attribution_method      # coerenza testuale


def test_nessun_campione_non_cancella_il_canale():
    """Finestra senza campioni: package_window_source='unavailable', ma il canale attivo resta dichiarato."""
    res = _profile("rapl", n_samples=0)
    assert res.energy_calculation_method == "rapl"
    assert res.package_window_source == "unavailable"
    assert res.n_samples_in_window == 0


# ------------------------------------------------------------------ 4
def test_ensure_header_migra_un_csv_storico(tmp_path):
    """Un CSV scritto con lo schema vecchio (senza il blocco nuovo) viene migrato: celle conservate, nuove vuote."""
    path = tmp_path / "risultati_storici.csv"
    vecchio = CSV_COLUMNS[:-8]          # ieri: senza 6 di provenienza e 2 dello share
    riga = {c: f"v:{c}" for c in vecchio}
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=vecchio)
        w.writeheader()
        w.writerow(riga)

    ensure_header(path)

    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 2, "la riga storica non deve sparire ne' raddoppiare"
    assert rows[1][vecchio.index("run_id")] == "v:run_id"
    assert rows[1][vecchio.index("local_energy_j")] == "v:local_energy_j"
    assert rows[1][CSV_COLUMNS.index("raw_start")] == ""
    assert rows[1][CSV_COLUMNS.index("backend_version")] == ""
    assert len(rows[1]) == len(CSV_COLUMNS), "riga disallineata rispetto all'header"


def test_esportazione_righe_con_canali_diversi_resta_distinguibile(tmp_path):
    """Due righe accumulate nello stesso file, emi-counter e power-integration: lette, restano due canali diversi."""
    path = tmp_path / "risultati.csv"
    recs = [{"run_id": "r1", "model_name": "a", "local_energy_j": 1.0,
             "energy_calculation_method": "emi-counter"},
            {"run_id": "r2", "model_name": "b", "local_energy_j": 2.0,
             "energy_calculation_method": "power-integration"}]
    n = export_results_csv(recs, path, mode="w")
    assert n == 2
    with open(path, "r", newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    got = {r["run_id"]: r["energy_calculation_method"] for r in rows}
    assert got == {"r1": "emi-counter", "r2": "power-integration"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
