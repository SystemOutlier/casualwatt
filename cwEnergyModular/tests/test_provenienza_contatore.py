# -*- coding: utf-8 -*-
"""
tests/test_provenienza_contatore.py — I grezzi della finestra vivono nella riga.

Perche' esiste. ``alt_lhm.DOCX`` (24/10, contratto §2 par. 31-52 e §3) chiede
che una misura porti con se' ``raw_start``/``raw_end``, il dominio, la
cadenza REALE dei campioni e la versione del backend. CasualWatt salvava il
canale (``energy_calculation_method``) ma non i valori grezzi: senza quelli,
``package_energy_j`` e' un numero che richiede di fidarsi del buffer del
contatore. Il report interno ``idee_implementative_20261024.md`` (P0-1) mette
questa colonna come primo punto offline.

Che cosa verifica:
  1. EMI: i grezzi sono pWh interpolati ai bordi dal buffer a 0,05 s, il
     dominio e' PKG, la cadenza e' la MEDIANA dei delta (non la media, che
     sotto spin passa da 0,0506 a 0,0770 s);
  2. RAPL: microjoule cumulati (unwrapped), versione = kernel;
  3. il profiler copia la provenienza nella riga e un errore del canale
     degrada a campi vuoti con una nota, non a un crash;
  4. la migrazione dell'header accoda le sei colonne senza perdere le celle
     storiche, e l'export le scrive.

Che cosa NON verifica: che il valore grezzo sia corretto rispetto al
registro hardware. Quello e' il dominio dei protocolli A-B-A con EMI vero;
qui si controlla che il dato arrivi, con la sua unita', dove deve arrivare.
"""
import csv
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from casualwatt_csv_export import (  # noqa: E402
    CSV_COLUMNS, ensure_header, export_results_csv,
)
from energy.energy_session import EnergySession, SystemSample  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


def _session(src, samples=None):
    """Sessione minima: solo cio' che serve a provenienza e profilo."""
    sess = EnergySession.__new__(EnergySession)   # niente __post_init__
    sess._source = src
    sess._lock = threading.RLock()
    sess._samples = list(samples or [])
    sess._igpu_none_reason = None
    return sess


class _SoloSorgente:
    """Sorgente finta che espone solo metodo e versione (per il wiring)."""

    def __init__(self, method="emi-counter", version="emi-reader/1"):
        self.method = method
        self._version = version

    def version_label(self):
        return self._version


def _with_provenance(prov):
    """Sessione finta: profiler reale, provenienza iniettata."""
    class _S:
        source_method = "emi-counter"
        interval_s = 0.5
        idle_power_w = 10.0
        idle_provenance = "calibrated"
        idle_gpu_power_w = None
        _gpu = SimpleNamespace(available=False, index=0, name="")

        def __init__(self):
            self.samples = [
                SystemSample(t=T0 + i * 0.5, wall=0.0,
                             package_energy_j=10.0 * i,
                             cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                             ollama_pids=(7,), ollama_cpu_seconds=0.5 * i)
                for i in range(3)
            ]

        def samples_between(self, a, b):
            return [s for s in self.samples if a <= s.t <= b]

        def window_counter_provenance(self, a, b, domain="pkg"):
            return dict(prov)

    prof = CasualWattLocalEnergyProfiler()
    prof.session = _S()
    return prof.profile_window(T0, T0 + 1.0, ollama_pids=[7])


# ------------------------------------------------------------------ EMI
def test_emi_grezzi_in_pwh_e_cadenza_mediana(monkeypatch):
    """Buffer PKG (t, J, pWh): raw ai bordi interpolato in pWh, cadenza = mediana dei delta."""
    from test_emi_backend import _make_source

    src, _ = _make_source(monkeypatch)
    with src._emi_lock:
        src._emi_samples = [
            (1000.0, 0.0, 0),
            (1002.0, 3.6, 1_000_000),
            (1004.0, 7.2, 2_000_000),
        ]
    prov = _session(src).window_counter_provenance(1001.0, 1004.0)
    assert prov["domain"] == "PKG"
    assert prov["raw_unit"] == "pWh"
    assert prov["raw_start"] == pytest.approx(500_000)
    assert prov["raw_end"] == pytest.approx(2_000_000)
    assert prov["sampling_interval_observed_s"] == pytest.approx(2.0)
    # emi-reader/2 (27/10/2026): la lettura passa dal metadato e il canale PKG
    # si sceglie per nome, non per posizione nel record (F11/F13).
    assert prov["backend_version"].startswith("emi-reader/2")
    assert "metadato" in prov["backend_version"]


def test_emi_senza_grezzi_nel_buffer_non_inventa(monkeypatch):
    """Buffer storico a due campi (t, J): manca il pWh, quindi raw None -- non zero."""
    from test_emi_backend import _make_source

    src, _ = _make_source(monkeypatch)
    with src._emi_lock:
        src._emi_samples = [(1000.0, 0.0), (1002.0, 3.6), (1004.0, 7.2)]
    prov = _session(src).window_counter_provenance(1000.0, 1004.0)
    assert prov["domain"] == "PKG"
    assert prov["raw_start"] is None and prov["raw_end"] is None
    assert prov["raw_unit"] == "pWh", "l'unita' e' nota anche se il grezzo manca"
    assert prov["sampling_interval_observed_s"] == pytest.approx(2.0)


# ----------------------------------------------------------------- RAPL
def test_rapl_grezzi_in_microjoule_unwrapped():
    """RAPL: cumulati in uJ (unwrapped) dai campioni di sessione, versione = kernel."""
    src = _SoloSorgente("rapl", "linux-rapl (kernel 6.8.0)")
    samples = [
        SystemSample(t=T0 + i, wall=0.0, package_energy_j=1.0 + i,
                     cpu_busy_seconds=1.0 * i, cpu_percent=0.0)
        for i in range(3)
    ]
    prov = _session(src, samples).window_counter_provenance(T0, T0 + 2.0)
    assert prov["raw_unit"] == "uJ (unwrapped)"
    assert prov["raw_start"] == pytest.approx(1_000_000)
    assert prov["raw_end"] == pytest.approx(3_000_000)
    assert prov["sampling_interval_observed_s"] == pytest.approx(1.0)
    assert "6.8.0" in prov["backend_version"]


# ------------------------------------------------------------- wiring
def test_il_profiler_copia_la_provenienza_nella_riga():
    """I sei campi arrivano nel LocalEnergyResult, non solo nel dizionario della sessione."""
    res = _with_provenance({
        "raw_start": 123.0, "raw_end": 456.0, "raw_unit": "pWh",
        "domain": "PKG", "sampling_interval_observed_s": 0.05,
        "backend_version": "emi-reader/1 (IOCTL 0x0022400C)",
    })
    assert res.raw_start == 123.0 and res.raw_end == 456.0
    assert res.raw_unit == "pWh" and res.domain == "PKG"
    assert res.sampling_interval_observed_s == pytest.approx(0.05)
    assert res.backend_version.startswith("emi-reader/1")


def test_provenienza_che_solleva_degrada_a_campi_vuoti_con_nota():
    """Una sessione senza il metodo (storica) o che fallisce non deve rompere la riga."""
    prov_ok = {"raw_start": None, "raw_end": None, "raw_unit": "", "domain": "",
               "sampling_interval_observed_s": None, "backend_version": ""}
    res = _with_provenance(prov_ok)
    assert res.raw_start is None and res.domain == ""

    class _Rotto:
        source_method = "emi-counter"
        interval_s = 0.5
        idle_power_w = 10.0
        idle_provenance = "calibrated"
        idle_gpu_power_w = None
        _gpu = SimpleNamespace(available=False, index=0, name="")

        def samples_between(self, a, b):
            return []

        def window_counter_provenance(self, a, b, domain="pkg"):
            raise RuntimeError("buffer non leggibile")

    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Rotto()
    res2 = prof.profile_window(T0, T0 + 1.0)
    assert res2.raw_start is None and res2.backend_version == ""
    assert any("provenienza contatore non disponibile" in n for n in res2.notes)


# ------------------------------------------------------------------ CSV
def test_migrazione_header_accoda_sei_colonne(tmp_path):
    """CSV storico senza il blocco di provenienza: celle preservate, sei colonne vuote in coda."""
    p = tmp_path / "storico.csv"
    old_cols = CSV_COLUMNS[:-6]
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(old_cols)
        w.writerow(["run-1"] + [""] * (len(old_cols) - 1))
    ensure_header(p)
    with open(p, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert rows[0] == CSV_COLUMNS
    assert rows[1][0] == "run-1", "la cella storica non si perde"
    assert rows[1][-6:] == [""] * 6
    assert len(rows[1]) == len(CSV_COLUMNS)


def test_export_scrive_i_campi_di_provenienza(tmp_path):
    """Una riga con i grezzi esce dal CSV con gli stessi valori e la stessa unita'."""
    p = tmp_path / "out.csv"
    rec = {"run_id": "r1", "raw_start": 100, "raw_end": 200,
           "raw_unit": "pWh", "domain": "PKG",
           "sampling_interval_observed_s": 0.05,
           "backend_version": "emi-reader/1"}
    export_results_csv([rec], p, mode="w")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        row = next(csv.DictReader(fh))
    assert row["raw_start"] == "100" and row["raw_end"] == "200"
    assert row["raw_unit"] == "pWh" and row["domain"] == "PKG"
    assert row["sampling_interval_observed_s"] == "0.05"
    assert row["backend_version"] == "emi-reader/1"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
