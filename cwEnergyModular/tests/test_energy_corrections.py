# -*- coding: utf-8 -*-
"""Test sintetici (senza hardware) delle correzioni A1-A3, B2, C1.

Le 8 docstring dei test di questo file sono state aggiunte il 23/10/2026
leggendo i corpi, non dall'autore originale delle funzioni.
"""
import threading
from types import SimpleNamespace

import pytest

from energy.energy_session import EnergySession, SystemSample
from energy.local_energy import CasualWattLocalEnergyProfiler

T0 = 1000.0
STEP = 0.5


class FakeGpu:
    def __init__(self, available=False):
        self.available = available
        self.index = 0
        self.name = "FakeGPU"


class FakeSession:
    """Sessione sintetica: potenza CPU/GPU e CPU-time definiti da funzioni."""

    def __init__(self, p_cpu, p_gpu=None, util=None, ollama_rate=1.0, busy_rate=1.0,
                 idle_w=10.0, idle_gpu_w=20.0, gpu_available=False, t_end=10.0):
        self.interval_s = STEP
        self.idle_power_w = idle_w
        self.idle_provenance = "calibrated"
        self.idle_gpu_power_w = idle_gpu_w
        self.source_method = "power-integration"
        self._gpu = FakeGpu(gpu_available)
        self.p_cpu = p_cpu                  # f(t_rel) -> W
        self.ollama_rate = ollama_rate      # f(t_rel) -> cpu-s/s dell'albero Ollama
        self.busy_rate = busy_rate          # f(t_rel) -> cpu-s/s del sistema
        self.samples = []
        e = o = b = 0.0
        n = int(round(t_end / STEP))
        for i in range(n + 1):
            tr = i * STEP
            if i:
                e += p_cpu(tr - STEP / 2) * STEP
                o += self._rate(ollama_rate, tr - STEP / 2) * STEP
                b += self._rate(busy_rate, tr - STEP / 2) * STEP
            self.samples.append(SystemSample(
                t=T0 + tr, wall=0.0, package_energy_j=e, cpu_busy_seconds=b,
                cpu_percent=0.0, ollama_pids=(123,), ollama_cpu_seconds=o,
                gpu_power_w=(p_gpu(tr) if p_gpu else None),
                gpu_util_pct=(util(tr) if util else None)))

    @staticmethod
    def _rate(r, t):
        return r(t) if callable(r) else r

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        """Integrale esatto di p_cpu su [a,b] meno le finestre escluse."""
        def integ(x, y):
            n = 2000
            h = (y - x) / n
            return sum(self.p_cpu((x - T0) + (k + .5) * h) * h for k in range(n))
        total = integ(a, b)
        for xa, xb in (excl or []):
            total -= integ(xa, xb)
        return total

    def read_igpu_energy_j(self, a, b, excl=None):
        return None


def profile(sess, t_a=0.0, t_b=10.0, excl=None):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(T0 + t_a, T0 + t_b, ollama_pids=[123],
                               exclude_windows=excl)


# ---------------------------------------------------------------- A1
@pytest.mark.parametrize("tail", [1.0, 5.0])
def test_A1_coda_inattiva_non_gonfia_energia_attiva(tail):
    """30 W per 2 s poi idle (10 W): E_attiva = (30-10)*2 = 40 J qualunque coda."""
    t_active = 2.0
    p = lambda t: 30.0 if t < t_active else 10.0
    o = lambda t: 1.0 if t < t_active else 0.0
    s = FakeSession(p, ollama_rate=o, busy_rate=o, t_end=t_active + tail)
    res = profile(s, 0.0, t_active + tail)
    assert res.active_energy_j == pytest.approx(40.0, abs=1.0)
    assert res.ollama_active_energy_j == pytest.approx(40.0, abs=1.0)


# ---------------------------------------------------------------- A2
@pytest.mark.parametrize("util", [0.3, 0.9])
def test_A2_gpu_energia_indipendente_dall_utilizzo(util):
    """100 W costanti, idle 20 W, 10 s -> 800 J a prescindere dall'utilizzo."""
    s = FakeSession(lambda t: 10.0, p_gpu=lambda t: 100.0,
                    util=lambda t: util * 100.0, gpu_available=True)
    res = profile(s)
    assert res.gpu_energy_attributed_j == pytest.approx(800.0, rel=0.02)


# ---------------------------------------------------------------- A3
def test_A3_senza_nvml_nessun_termine_igpu_sommato():
    """Senza GPU il termine attribuito vale 0: la somma locale resta solo la CPU."""
    s = FakeSession(lambda t: 30.0, gpu_available=False)
    res = profile(s)
    local_j = res.ollama_active_energy_j + res.gpu_energy_attributed_j
    assert res.gpu_energy_attributed_j == 0.0
    assert local_j == pytest.approx(res.ollama_active_energy_j)


# ------------------------------------------------- Punto 1: energia iGPU
class FakeIGpuSession:
    """Sessione sintetica che riusa i metodi REALI di EnergySession per l'iGPU.

    Nessun hardware: i campioni portano solo ``igpu_power_w`` (costante,
    variabile o None = sensore assente).
    """

    samples_between = EnergySession.samples_between
    read_igpu_energy_j = EnergySession.read_igpu_energy_j
    _interpolate = staticmethod(EnergySession._interpolate)

    def __init__(self, igpu_w=5.0, t_end=10.0, lhm_opened=True):
        self.interval_s = STEP
        self._lock = threading.RLock()
        self._source = SimpleNamespace(method="power-integration",
                                       _lhm_opened=lhm_opened)
        n = int(round(t_end / STEP))
        self._samples = [
            SystemSample(
                t=T0 + i * STEP, wall=0.0, package_energy_j=0.0,
                cpu_busy_seconds=0.0, cpu_percent=0.0,
                igpu_power_w=(igpu_w(i * STEP) if callable(igpu_w) else igpu_w))
            for i in range(n + 1)
        ]


def test_P1_igpu_integrale_trapezoidale_sulla_finestra():
    """5 W costanti per 10 s -> 50 J (integrale sulla finestra, non lettura puntuale)."""
    s = FakeIGpuSession(igpu_w=5.0)
    assert s.read_igpu_energy_j(T0, T0 + 10.0) == pytest.approx(50.0, rel=1e-6)


def test_P1_igpu_sottofinestra_esclusa():
    """Judge escluso 4 s su 10 -> restano 6 s a 5 W = 30 J."""
    s = FakeIGpuSession(igpu_w=5.0)
    got = s.read_igpu_energy_j(T0, T0 + 10.0,
                               exclude_windows=[(T0 + 6.0, T0 + 10.0)])
    assert got == pytest.approx(30.0, rel=1e-6)


def test_P1_igpu_sensore_assente_ritorna_none():
    """igpu_power_w assente su tutti i campioni: None, non 0 J."""
    s = FakeIGpuSession(igpu_w=None)
    assert s.read_igpu_energy_j(T0, T0 + 10.0) is None


def test_P1_igpu_potenza_variabile_segue_la_finestra():
    """Rampa 0->10 W su 10 s -> 50 J; il tratto finale escluso non conta."""
    s = FakeIGpuSession(igpu_w=lambda tr: tr)          # W = t_rel
    assert s.read_igpu_energy_j(T0, T0 + 10.0) == pytest.approx(50.0, rel=1e-3)
    assert s.read_igpu_energy_j(T0, T0 + 4.0) == pytest.approx(8.0, rel=1e-2)


def test_P1_igpu_backend_non_attivo_ritorna_none():
    """Backend dei sensori non aperto: None, perche' 0 J sarebbe una misura falsa."""
    s = FakeIGpuSession(igpu_w=5.0, lhm_opened=False)
    assert s.read_igpu_energy_j(T0, T0 + 10.0) is None


# ---------------------------------------------------------------- B1
def test_B1_energia_finestra_da_contatore_esatto():
    """Bordi 1,2-7,7 s non allineati ai campioni: 25 W x 6,5 s e window_source 'exact-counter'."""
    s = FakeSession(lambda t: 25.0)
    res = profile(s, 1.2, 7.7)       # bordi non allineati ai campioni (0,5 s)
    assert res.package_energy_j == pytest.approx(25.0 * 6.5, rel=1e-3)
    assert res.package_window_source == "exact-counter"


# ---------------------------------------------------------------- B2
def test_B2_judge_escluso_coerente_su_energia_baseline_e_cpu():
    """Judge in [6,10]: potenza 30 W. Ollama usa 1 cpu-s/s, sistema 2 cpu-s/s
    -> quota reale 0.5 sugli intervalli tenuti ([0,6])."""
    s = FakeSession(lambda t: 30.0, ollama_rate=1.0, busy_rate=2.0)
    res = profile(s, 0.0, 10.0, excl=[(T0 + 6.0, T0 + 10.0)])
    assert res.duration_s == pytest.approx(6.0, abs=0.05)
    assert res.package_energy_j == pytest.approx(30.0 * 6.0, rel=1e-2)
    assert res.baseline_energy_j == pytest.approx(10.0 * 6.0, rel=1e-2)
    assert res.cpu_time_share == pytest.approx(0.5, abs=0.02)
    assert res.ollama_active_energy_j == pytest.approx(0.5 * 120.0, rel=0.03)


def test_B2_gpu_esclude_la_finestra_del_judge():
    """GPU 100 W costanti, idle 20 W; Judge escluso 4 s su 10 -> (100-20)*6 J."""
    s = FakeSession(lambda t: 10.0, p_gpu=lambda t: 100.0, gpu_available=True)
    res = profile(s, 0.0, 10.0, excl=[(T0 + 6.0, T0 + 10.0)])
    assert res.gpu_energy_attributed_j == pytest.approx(80.0 * 6.0, rel=0.03)


# ------------------------------------------- Punto 2: provenienza idle GPU
def test_P2_idle_gpu_assente_provenance_missing_e_nota():
    """100 W costanti senza idle calibrato -> tutta la scheda, dichiarata."""
    s = FakeSession(lambda t: 10.0, p_gpu=lambda t: 100.0, gpu_available=True,
                    idle_gpu_w=0.0)
    res = profile(s)
    assert res.gpu_idle_provenance == "missing"
    assert res.gpu_energy_attributed_j == pytest.approx(1000.0, rel=0.02)
    assert any("idle GPU non calibrato" in n and "sovrastima" in n
               for n in res.notes)


def test_P2_idle_gpu_non_impostato_provenance_missing():
    """Idle GPU mai impostato (None) e' 'missing' come 0,0: la nota di sovrastima c'e' in entrambi i casi."""
    s = FakeSession(lambda t: 10.0, p_gpu=lambda t: 100.0, gpu_available=True,
                    idle_gpu_w=None)
    res = profile(s)
    assert res.gpu_idle_provenance == "missing"
    assert any("idle GPU non calibrato" in n for n in res.notes)


def test_P2_idle_gpu_calibrato_provenance_calibrated():
    """100 W costanti, idle 20 W -> 800 J e nessuna nota di sovrastima."""
    s = FakeSession(lambda t: 10.0, p_gpu=lambda t: 100.0, gpu_available=True,
                    idle_gpu_w=20.0)
    res = profile(s)
    assert res.gpu_idle_provenance == "calibrated"
    assert res.gpu_energy_attributed_j == pytest.approx(800.0, rel=0.02)
    assert not any("idle GPU non calibrato" in n for n in res.notes)


def test_P2_senza_gpu_dedicata_provenance_vuota():
    """Senza GPU dedicata la provenienza e' stringa vuota: dato non applicabile, non dato mancante."""
    s = FakeSession(lambda t: 30.0, gpu_available=False)
    assert profile(s).gpu_idle_provenance == ""


def test_P2_colonna_csv_accodata_senza_cambiare_ordine():
    """gpu_idle_provenance compare una volta sola e l'ordine delle colonne e' bloccato: nuove solo in coda."""
    from casualwatt_csv_export import CSV_COLUMNS
    assert CSV_COLUMNS.count("gpu_idle_provenance") == 1
    # Il blocco storico resta intatto e ogni release accode UNA colonna. La
    # coda e fissata come LISTA ordinata, non come indici negativi: con gli
    # indici ogni colonna nuova obbligava a riscrivere tutte le asserzioni
    # (e spostare un -1 di posto e' esattamente il modo in cui si scopre
    # dopo di aver rotto l'ordine di quelle vecchie).
    CODA = ["gpu_idle_provenance",      # Punto 2: provenienza idle GPU
            "ollama_pids_used", "d_ollama_cpu_s", "d_busy_s",
            "n_samples_in_window",      # diagnostica cpu-time-share
            "answer_type", "extracted_answer",
            "keep_alive_sent",          # D1: stato reale del motore locale
            "energy_calculation_method",  # 24/10: canale del package PER RIGA
            # 24/10: contratto alt_lhm §3 (grezzi, unita', dominio,
            # cadenza osservata, versione del percorso di lettura)
            "raw_start", "raw_end", "raw_unit", "domain",
            "sampling_interval_observed_s", "backend_version",
            # rev_metodo §2(b): denominatore dello share CPU
            "cpu_share_window_s", "cpu_busy_capacity_cores",
            # P2: grandezza grezza con segno e validita' dichiarata
            "package_energy_raw_j", "active_energy_raw_j", "active_valid"]
    assert CSV_COLUMNS[-len(CODA):] == CODA
    assert CSV_COLUMNS[:6] == [
        "run_id", "session_id", "timestamp_start", "timestamp_end",
        "model_name", "model_label",
    ]


# ---------------------------------------------------------------- C1
def test_C1_epcl_ed_energia_per_risposta_corretta_sono_distinte():
    """60 J con 3 collegamenti corretti: EPCL 20 J/link, energia per risposta corretta 60 J. Due denominatori."""
    from benchmark_unified import _finalize_energy_fields
    ev = SimpleNamespace(n_correct_links=3, acc_comp=0.8, is_correct=True,
                         acc_links_basis="f1_triples")
    rec = {"output_tokens": 10, "local_energy_j": 0, "notes": [],
           "local_carbon_intensity_gco2eq_kwh": 0}
    _finalize_energy_fields(rec, 60.0, 0.0, 0.0, ev)
    assert rec["energy_per_correct_answer_j"] == pytest.approx(60.0)
    assert rec["epcl_j_per_link"] == pytest.approx(20.0)
