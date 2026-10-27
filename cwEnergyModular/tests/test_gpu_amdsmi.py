# -*- coding: utf-8 -*-
"""GPU AMD via AMD SMI: fallback dichiarato dopo NVML.

Documentazione verificata alla fonte il 28-10-2026. Python API (AMD SMI
27.1.0): ``amdsmi_get_energy_count`` restituisce ``energy_accumulator``,
``counter_resolution`` e ``timestamp`` con la regola scritta
"energy_accumulator * counter_resolution = total_energy_consumption in
micro-Joules", accumulata "since last restart/gpu reset", e la funzione "is
not supported on virtual machine guest". ``amdsmi_get_power_info`` espone
``socket_power`` ("matches current or average"), ``current_socket_power``
("Mi300+ Series Cards") e ``average_socket_power`` ("Navi + Mi 200 and earlier
Series cards"), tutti e tre in W. ``amdsmi_get_gpu_activity`` da'
``gfx_activity`` in percentuale. La reference C dichiara per il timestamp
"Resolution: 1 ns" e tagga la chiamata ``Platform: gpu_bm_linux``.

Quattro cose che questi test fissano, e che un ``hasattr`` non direbbe:

  * l'unita' e' composta (accumulator x risoluzione, in microjoule) e la
    risoluzione si SONDA su una lettura reale; con risoluzione nulla il
    contatore non e' utilizzabile;
  * il timestamp del device distingue una lettura ferma (non valida) da uno
    zero legittimo (timestamp che avanza, contatore immobile);
  * un delta negativo e' un reset o un avvolgimento: non si clampa a zero, si
    copre la finestra con l'integrale e lo si dichiara;
  * NVML e AMD SMI non convivono: se NVML risponde si usa NVML, l'AMD SMI e'
    il ripiego, mai un secondo lettore della stessa scheda.

``amdsmi`` e' un modulo finto in ``sys.modules``: nessun hardware richiesto.
L'esecuzione su GPU AMD reale resta [P].
"""
import sys
import types

import pytest

from energy.energy_session import (
    SystemSample, _AMDGPUMonitor, _open_gpu_monitor,
)
from energy.local_energy import CasualWattLocalEnergyProfiler

T0 = 1000.0
STEP = 0.5
TS0 = 1_000_000_000          # ns: il timestamp non parte da zero per costruzione


def _fake_amdsmi(monkeypatch, *, accumulator=1_000_000, resolution=1.0,
                 energy_error=None, power=None, init_error=None,
                 handles=("gpu-0",), remove=None, timestamp=1):
    mod = types.ModuleType("amdsmi")

    def amdsmi_init():
        if init_error is not None:
            raise init_error

    mod.amdsmi_init = amdsmi_init
    mod.amdsmi_shut_down = lambda: None
    mod.amdsmi_get_processor_handles = lambda: list(handles)
    mod.amdsmi_get_gpu_asic_info = lambda h: {"market_name": "Fake AMD GPU"}
    mod.amdsmi_get_power_info = lambda h: power if power is not None else {
        "socket_power": 100.0, "current_socket_power": 0.0,
        "average_socket_power": 90.0}
    mod.amdsmi_get_gpu_activity = lambda h: {"gfx_activity": 40}

    def energy_count(h):
        if energy_error is not None:
            raise energy_error
        return {"energy_accumulator": accumulator,
                "counter_resolution": resolution, "timestamp": timestamp}

    mod.amdsmi_get_energy_count = energy_count
    for name in (remove or ()):
        delattr(mod, name)
    monkeypatch.setitem(sys.modules, "amdsmi", mod)
    return mod


def _fake_nvml_absent(monkeypatch):
    mod = types.ModuleType("pynvml")

    def nvmlInit():
        raise RuntimeError("NVMLError_LibraryNotFound")

    mod.nvmlInit = nvmlInit
    mod.nvmlShutdown = lambda: None
    monkeypatch.setitem(sys.modules, "pynvml", mod)


# ------------------------------------------------------------- sonda
def test_contatore_amd_si_converte_da_microjoule(monkeypatch):
    """accumulator x counter_resolution = microjoule: 12.345.000 uJ sono 12.345 mJ."""
    _fake_amdsmi(monkeypatch, accumulator=12_345_000, resolution=1.0,
                 timestamp=777)
    m = _AMDGPUMonitor()
    assert m.available is True
    assert m.energy_counter is True
    assert m.read_energy() == (pytest.approx(12_345.0), 777)


def test_risoluzione_dichiarata_diversa_da_uno(monkeypatch):
    """La risoluzione non si presume 1: 1000 conteggi da 15,3 uJ sono 15.300 uJ."""
    _fake_amdsmi(monkeypatch, accumulator=1000, resolution=15.3)
    m = _AMDGPUMonitor()
    assert m.read_energy()[0] == pytest.approx(15.3)


def test_risoluzione_nulla_non_e_un_contatore(monkeypatch):
    """Senza risoluzione il valore non ha unita': contatore non utilizzabile, motivo scritto."""
    _fake_amdsmi(monkeypatch, resolution=0.0)
    m = _AMDGPUMonitor()
    assert m.energy_counter is False
    assert "risoluzione" in m.energy_counter_reason
    assert m.read_energy() == (None, None)


def test_contatore_che_solleva_non_ferma_il_monitor(monkeypatch):
    """Un errore AMD SMI sul contatore lascia la potenza disponibile e non risale."""
    _fake_amdsmi(monkeypatch, energy_error=RuntimeError("AMDSMI_STATUS_NOT_SUPPORTED"))
    m = _AMDGPUMonitor()
    assert m.available is True
    assert m.energy_counter is False
    assert "RuntimeError" in m.energy_counter_reason


def test_potenza_amd_usa_il_campo_generale(monkeypatch):
    """Il campo generale ``socket_power`` vale su ogni generazione: si legge quello."""
    _fake_amdsmi(monkeypatch)
    m = _AMDGPUMonitor()
    w, util = m.read()
    assert w == pytest.approx(100.0)
    assert util == pytest.approx(40.0)
    assert m.power_field == "socket_power"


def test_senza_campo_generale_si_usa_quello_della_generazione(monkeypatch):
    """``socket_power`` assente su una Mi300+: si scende a ``current_socket_power``."""
    _fake_amdsmi(monkeypatch, power={"socket_power": None,
                                     "current_socket_power": 55.0,
                                     "average_socket_power": 90.0})
    m = _AMDGPUMonitor()
    assert m.read()[0] == pytest.approx(55.0)
    assert m.power_field == "current_socket_power"


def test_senza_i_due_campi_nuovi_resta_la_media(monkeypatch):
    """Navi e MI 200 o precedenti: resta ``average_socket_power``, non si inventa zero."""
    _fake_amdsmi(monkeypatch, power={"socket_power": None,
                                     "current_socket_power": None,
                                     "average_socket_power": 90.0})
    m = _AMDGPUMonitor()
    assert m.read()[0] == pytest.approx(90.0)
    assert m.power_field == "average_socket_power"


def test_unita_della_potenza_dichiarata_solo_dopo_la_lettura(monkeypatch):
    """L'unita' e' W per documentazione, ma finche' non si legge un valore resta "unknown"."""
    _fake_amdsmi(monkeypatch)
    m = _AMDGPUMonitor()
    assert m.power_unit == "unknown"
    m.read()
    assert m.power_unit == "W"


def test_contesto_di_piattaforma_linux_e_quello_documentato(monkeypatch):
    """La reference C tagga il contatore ``gpu_bm_linux``: su Linux il contesto lo dice."""
    monkeypatch.setattr(sys, "platform", "linux")
    _fake_amdsmi(monkeypatch)
    assert _AMDGPUMonitor().platform_context == "gpu_bm_linux"


def test_contesto_di_piattaforma_fuori_dal_documentato(monkeypatch):
    """Se risponde su un OS non documentato, il contesto non si presenta come quello provato."""
    monkeypatch.setattr(sys, "platform", "win32")
    _fake_amdsmi(monkeypatch)
    assert _AMDGPUMonitor().platform_context == "non-linux"


def test_senza_gpu_amd_il_contesto_resta_ignoto(monkeypatch):
    """Senza GPU non c'e' un contesto da dichiarare: ``unknown``, non un'ipotesi."""
    _fake_amdsmi(monkeypatch, handles=())
    m = _AMDGPUMonitor()
    assert m.available is False
    assert "nessuna GPU AMD SMI" in m.error
    assert m.platform_context == "unknown"


# ------------------------------------------------------------- selezione
def test_senza_nvml_si_scende_ad_amd_smi(monkeypatch):
    """NVML assente e AMD SMI presente: il monitor e' AMD, e NVML non resta in parallelo."""
    _fake_nvml_absent(monkeypatch)
    _fake_amdsmi(monkeypatch)
    m = _open_gpu_monitor()
    assert m.available is True
    assert m.backend == "amdsmi"
    assert m.name == "Fake AMD GPU"


def test_senza_nessuno_dei_due_il_motivo_nomina_entrambi(monkeypatch):
    """Nessun backend: non disponibile, e il motivo non nasconde quale dei due manca."""
    _fake_nvml_absent(monkeypatch)
    _fake_amdsmi(monkeypatch, init_error=RuntimeError("AMDSMI_STATUS_INIT_ERROR"))
    m = _open_gpu_monitor()
    assert m.available is False
    assert "NVML" in m.error and "AMD SMI" in m.error


# ------------------------------------------------------------- finestra
class FakeGpu:
    backend = "amdsmi"

    def __init__(self, energy_counter=True, power_field="socket_power",
                 platform_context="gpu_bm_linux"):
        self.available = True
        self.index = 0
        self.name = "Fake AMD GPU"
        self.energy_counter = energy_counter
        self.power_field = power_field
        self.power_unit = "W" if power_field else "unknown"
        self.platform_context = platform_context


class FakeSession:
    def __init__(self, p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True,
                 t_end=10.0, ts_stalled=False, zero_energy=False,
                 ts_missing=False):
        self.interval_s = STEP
        self.idle_power_w = 10.0
        self.idle_provenance = "calibrated"
        self.idle_gpu_power_w = idle_gpu_w
        self.source_method = "power-integration"
        self._gpu = FakeGpu(energy_counter=energy_counter)
        self.samples = []
        e = 0.0
        uj = 0.0
        n = int(round(t_end / STEP))
        for i in range(n + 1):
            tr = i * STEP
            if i:
                e += 10.0 * STEP
                if not zero_energy:
                    uj += (p_gpu * STEP) * 1e6          # W*s -> uJ
            ts = TS0 if ts_stalled else TS0 + i * 500_000_000
            self.samples.append(SystemSample(
                t=T0 + tr, wall=0.0, package_energy_j=e, cpu_busy_seconds=0.0,
                cpu_percent=0.0, ollama_pids=(123,), ollama_cpu_seconds=0.0,
                gpu_power_w=p_gpu, gpu_util_pct=40.0,
                gpu_energy_mj=(uj / 1000.0 if energy_counter else None),
                gpu_energy_ts_ns=(None if (ts_missing or not energy_counter)
                                  else ts)))

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        return 10.0 * (b - a)

    def read_igpu_energy_j(self, a, b, excl=None):
        return None


def profile(sess):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(T0, T0 + 10.0, ollama_pids=[123])


def test_finestra_amd_usa_il_token_amdsmi_energy():
    """100 W per 10 s dal contatore AMD: 1000 J, meno 20 W x 10 s di idle = 800 J."""
    res = profile(FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True))
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=1e-9)
    assert res.gpu_energy_attributed_j == pytest.approx(800.0, rel=1e-9)
    assert res.gpu_attribution_method.startswith("amdsmi-energy")
    assert "platform=gpu_bm_linux" in res.gpu_attribution_method


def test_finestra_amd_senza_contatore_usa_l_integrale_e_dichiara_la_chiave():
    """Senza contatore il ripiego e' l'integrale, e il campo dice chiave e unita' di potenza."""
    res = profile(FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=False))
    assert res.gpu_attribution_method.startswith("amdsmi-power-integral")
    assert "power=socket_power [W]" in res.gpu_attribution_method
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=0.01)


def test_timestamp_fermo_non_e_un_intervallo_di_energia():
    """Device che non aggiorna il contatore: il delta non si legge come energia, si integra."""
    res = profile(FakeSession(p_gpu=100.0, energy_counter=True, ts_stalled=True))
    assert res.gpu_attribution_method.startswith("amdsmi-power-integral")
    assert any("timestamp" in n and "fermo" in n for n in res.notes)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=0.01)


def test_timestamp_che_avanza_con_contatore_fermo_e_zero_legittimo():
    """Timestamp che avanza e contatore immobile: zero e' un dato, non una lettura mancante."""
    res = profile(FakeSession(p_gpu=100.0, energy_counter=True, zero_energy=True))
    assert res.gpu_attribution_method.startswith("amdsmi-energy")
    assert res.gpu_board_energy_j == pytest.approx(0.0)
    assert any("zero" in n and "timestamp" in n for n in res.notes)


def test_delta_negativo_e_reset_o_avvolgimento_non_clampato():
    """Un contatore che torna indietro non diventa energia: si dichiara e si integra."""
    s = FakeSession(p_gpu=100.0, energy_counter=True)
    for i, sample in enumerate(s.samples):
        sample.gpu_energy_mj = 5000.0 if i < 10 else 500.0
    res = profile(s)
    assert res.gpu_attribution_method.startswith("amdsmi-power-integral")
    assert any("avvolgimento" in n and "reset" in n for n in res.notes)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=0.01)


def test_senza_timestamp_il_controllo_non_si_applica_e_lo_dice():
    """Contatore AMD senza timestamp: il delta si usa, ma l'assenza del controllo e' scritta."""
    res = profile(FakeSession(p_gpu=100.0, energy_counter=True, ts_missing=True))
    assert res.gpu_attribution_method.startswith("amdsmi-energy")
    assert any("senza timestamp" in n for n in res.notes)
    assert res.gpu_board_energy_j == pytest.approx(1000.0, rel=1e-9)
