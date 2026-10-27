# -*- coding: utf-8 -*-
"""Catena GPU NVIDIA: nvml-energy -> nvml-power-integral -> unavailable.

Il contatore cumulativo ``nvmlDeviceGetTotalEnergyConsumption`` e' documentato
dalla fonte primaria (NVML API Guide, R535, letto il 28-10-2026) come "the
total energy consumed in mJ", accumulato "since the last reset", supportato da
Kepler in poi e "does not overflow". Due conseguenze che questi test fissano:

  * il valore assoluto non e' l'energia della finestra: serve il DELTA fra i
    bordi, perche' il punto zero e' un reset del driver e non l'inizio della
    misura (stessa semantica M1 dei delta EMI);
  * il supporto si SONDA su una lettura reale, non si presume da ``hasattr``:
    un device pre-Kepler risponde ``NVML_ERROR_NOT_SUPPORTED`` e la catena
    scende all'integrale della potenza, dichiarandolo.

I test non richiedono NVIDIA: ``pynvml`` e' un modulo finto in ``sys.modules``
e il profilo gira su una sessione sintetica, come in ``test_energy_corrections``.
L'esecuzione su hardware reale resta [P]: su questa macchina NVML non c'e'
(``NVMLError_LibraryNotFound``), quindi la prova sul campo e' ancora da fare.
"""
import sys
import types
from types import SimpleNamespace

import pytest

from energy.energy_session import SystemSample, _GPUMonitor
from energy.local_energy import CasualWattLocalEnergyProfiler

T0 = 1000.0
STEP = 0.5


def _fake_nvml(monkeypatch, *, energy_fn=None, init_error=None,
               with_counter=True):
    """Installa un ``pynvml`` finto in ``sys.modules``."""
    mod = types.ModuleType("pynvml")

    def nvmlInit():
        if init_error is not None:
            raise init_error

    mod.nvmlInit = nvmlInit
    mod.nvmlShutdown = lambda: None
    mod.nvmlDeviceGetCount = lambda: 1
    mod.nvmlDeviceGetHandleByIndex = lambda i: "handle-0"
    mod.nvmlDeviceGetName = lambda h: "FakeGPU"
    mod.nvmlDeviceGetPowerUsage = lambda h: 100_000.0     # mW -> 100 W
    mod.nvmlDeviceGetUtilizationRates = lambda h: SimpleNamespace(gpu=50)
    mod.nvmlDeviceGetProcessUtilization = lambda h, t: []
    if with_counter:
        mod.nvmlDeviceGetTotalEnergyConsumption = (
            energy_fn if energy_fn is not None else (lambda h: 1234.0))
    monkeypatch.setitem(sys.modules, "pynvml", mod)
    return mod


# ------------------------------------------------------------- sonda
def test_contatore_presente_si_usa(monkeypatch):
    """La sonda fa una lettura reale: se risponde, il percorso nvml-energy e' disponibile."""
    _fake_nvml(monkeypatch, energy_fn=lambda h: 4321.0)
    m = _GPUMonitor()
    assert m.available is True
    assert m.energy_counter is True
    assert m.energy_counter_reason == ""
    assert m.read_energy_mj() == pytest.approx(4321.0)


def test_wrapper_senza_la_funzione_dichiara_il_motivo(monkeypatch):
    """``pynvml`` vecchio non ha il simbolo: nessun contatore, e il motivo lo dice."""
    _fake_nvml(monkeypatch, with_counter=False)
    m = _GPUMonitor()
    assert m.energy_counter is False
    assert "nvmlDeviceGetTotalEnergyConsumption" in m.energy_counter_reason
    assert m.read_energy_mj() is None


def test_device_che_non_supporta_il_contatore_non_solleva(monkeypatch):
    """Un NVML_ERROR_NOT_SUPPORTED e' un esito dichiarato, non un'eccezione che risale."""

    def boom(h):
        raise RuntimeError("NVML_ERROR_NOT_SUPPORTED")

    _fake_nvml(monkeypatch, energy_fn=boom)
    m = _GPUMonitor()
    assert m.available is True
    assert m.energy_counter is False
    assert "RuntimeError" in m.energy_counter_reason
    assert m.read_energy_mj() is None


def test_senza_gpu_la_sonda_non_inventa_un_motivo_tecnico(monkeypatch):
    """Se NVML non si inizializza, il motivo e' l'assenza della GPU, non l'assenza del contatore."""
    _fake_nvml(monkeypatch, init_error=RuntimeError("NVML_ERROR_LIBRARY_NOT_FOUND"))
    m = _GPUMonitor()
    assert m.available is False
    assert m.energy_counter is False
    assert "GPU non disponibile" in m.energy_counter_reason


# ------------------------------------------------------------- finestra
class FakeGpu:
    def __init__(self, available=True, energy_counter=True, name="FakeGPU"):
        self.available = available
        self.index = 0
        self.name = name
        self.energy_counter = energy_counter
        self.energy_counter_reason = ""


class FakeSession:
    """Sessione sintetica con potenza GPU e contatore cumulativo coerenti."""

    def __init__(self, p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True,
                 t_end=10.0):
        self.interval_s = STEP
        self.idle_power_w = 10.0
        self.idle_provenance = "calibrated"
        self.idle_gpu_power_w = idle_gpu_w
        self.source_method = "power-integration"
        self._gpu = FakeGpu(energy_counter=energy_counter)
        self.p_cpu = lambda t: 10.0
        self.samples = []
        e = 0.0
        mj = 0.0
        n = int(round(t_end / STEP))
        for i in range(n + 1):
            tr = i * STEP
            if i:
                e += 10.0 * STEP
                mj += (p_gpu * STEP) * 1000.0      # W*s -> mJ
            self.samples.append(SystemSample(
                t=T0 + tr, wall=0.0, package_energy_j=e, cpu_busy_seconds=0.0,
                cpu_percent=0.0, ollama_pids=(123,), ollama_cpu_seconds=0.0,
                gpu_power_w=p_gpu, gpu_util_pct=50.0,
                gpu_energy_mj=(mj if energy_counter else None)))

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        return 10.0 * (b - a)

    def read_igpu_energy_j(self, a, b, excl=None):
        return None


def profile(sess, t_a=0.0, t_b=10.0, excl=None):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(T0 + t_a, T0 + t_b, ollama_pids=[123],
                               exclude_windows=excl)


def test_la_finestra_usa_il_delta_del_contatore():
    """100 W per 10 s = 1000 J dal contatore (delta mJ), meno 20 W x 10 s di idle = 800 J."""
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    res = profile(s)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=1e-9)
    assert res.gpu_energy_attributed_j == pytest.approx(800.0, rel=1e-9)
    assert res.gpu_attribution_method.startswith("nvml-energy")


def test_contatore_assente_resta_l_integrale():
    """Senza contatore la catena scende un gradino, non inventa un delta."""
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=False)
    res = profile(s)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=0.01)
    assert res.gpu_energy_attributed_j == pytest.approx(800.0, rel=0.01)
    assert res.gpu_attribution_method.startswith("nvml-power-integral")


def test_contatore_che_torna_indietro_e_un_reset_dichiarato():
    """Un delta negativo (reset del driver a meta' finestra) non si scrive come energia: si integra la potenza."""
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    for i, sample in enumerate(s.samples):
        if i < 10:
            sample.gpu_energy_mj = 5000.0       # prima meta': contatore alto
        else:
            sample.gpu_energy_mj = 500.0        # reset del driver a meta' finestra
    res = profile(s)
    assert res.gpu_attribution_method.startswith("nvml-power-integral")
    assert any("reset" in n for n in res.notes)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=0.01)


def test_sottofinestra_esclusa_usa_l_integrale():
    """Il delta del contatore non sa sottrarre il judge: con una sottofinestra esclusa si integra e si sottrae."""
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    excl = [(T0 + 4.0, T0 + 6.0)]
    res = profile(s, excl=excl)
    assert res.gpu_attribution_method.startswith("nvml-power-integral")
    assert res.gpu_board_energy_j == pytest.approx(800.0, rel=0.02)
