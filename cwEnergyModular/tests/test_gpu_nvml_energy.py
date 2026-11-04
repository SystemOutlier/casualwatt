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
               with_counter=True, count=1):
    """Installa un ``pynvml`` finto in ``sys.modules``.

    ``count`` e' il numero di device che NVML vede: la selezione del device si
    prova solo con piu' di un device, perche' con uno solo l'indice 0 non e'
    un'assunzione.
    """
    mod = types.ModuleType("pynvml")

    def nvmlInit():
        if init_error is not None:
            raise init_error

    mod.nvmlInit = nvmlInit
    mod.nvmlShutdown = lambda: None
    mod.nvmlDeviceGetCount = lambda: count
    mod.nvmlDeviceGetHandleByIndex = lambda i: f"handle-{i}"
    mod.nvmlDeviceGetName = lambda h: f"FakeGPU-{h}"
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
    assert m.read_energy() == (pytest.approx(4321.0), None)


def test_wrapper_senza_la_funzione_dichiara_il_motivo(monkeypatch):
    """``pynvml`` vecchio non ha il simbolo: nessun contatore, e il motivo lo dice."""
    _fake_nvml(monkeypatch, with_counter=False)
    m = _GPUMonitor()
    assert m.energy_counter is False
    assert "nvmlDeviceGetTotalEnergyConsumption" in m.energy_counter_reason
    assert m.read_energy() == (None, None)


def test_device_che_non_supporta_il_contatore_non_solleva(monkeypatch):
    """Un NVML_ERROR_NOT_SUPPORTED e' un esito dichiarato, non un'eccezione che risale."""

    def boom(h):
        raise RuntimeError("NVML_ERROR_NOT_SUPPORTED")

    _fake_nvml(monkeypatch, energy_fn=boom)
    m = _GPUMonitor()
    assert m.available is True
    assert m.energy_counter is False
    assert "RuntimeError" in m.energy_counter_reason
    assert m.read_energy() == (None, None)


def test_senza_gpu_la_sonda_non_inventa_un_motivo_tecnico(monkeypatch):
    """Se NVML non si inizializza, il motivo e' l'assenza della GPU, non l'assenza del contatore."""
    _fake_nvml(monkeypatch, init_error=RuntimeError("NVML_ERROR_LIBRARY_NOT_FOUND"))
    m = _GPUMonitor()
    assert m.available is False
    assert m.energy_counter is False
    assert "GPU non disponibile" in m.energy_counter_reason


# ------------------------------------------------------------- selezione device
# ``_GPUMonitor`` apriva l'indice 0 senza alcuna selezione e senza dirlo: su una
# macchina con due GPU il numero nella riga era l'energia della scheda in
# posizione 0, presentata come "la GPU". Questi test fissano la regola: l'indice
# si puo' richiedere, una richiesta che il backend non puo' soddisfare NON
# degrada alla scheda 0, e quando la scelta resta implicita fra piu' device la
# riga lo dichiara.
def test_indice_esplicito_apre_quel_device(monkeypatch):
    """L'argomento ``index`` apre l'handle di quell'indice, non il primo."""
    _fake_nvml(monkeypatch, count=2)
    m = _GPUMonitor(index=1)
    assert m.available is True
    assert m.index == 1
    assert m.handle == "handle-1"
    assert m.device_count == 2
    assert m.device_selection == "argomento"
    assert m.device_note == ""


def test_indice_fuori_intervallo_non_apre_la_scheda_zero(monkeypatch):
    """Richiesta impossibile: nessun device aperto, errore con quello che NVML vede."""
    _fake_nvml(monkeypatch, count=2)
    m = _GPUMonitor(index=5)
    assert m.available is False
    assert m.index is None
    assert m.handle is None
    assert "fuori intervallo" in m.error and "2 device" in m.error


def test_due_gpu_senza_selezione_avvisano_la_riga(monkeypatch):
    """Con due device e nessuna richiesta l'indice 0 e' un'assunzione e va scritta."""
    _fake_nvml(monkeypatch, count=2)
    m = _GPUMonitor()
    assert m.available is True
    assert m.index == 0
    assert m.device_note.startswith("2 GPU nvml")
    assert "CW_GPU_INDEX" in m.device_note


def test_un_solo_device_non_produce_note(monkeypatch):
    """Su una macchina con una GPU sola l'indice 0 non e' un'assunzione: nessuna nota."""
    _fake_nvml(monkeypatch, count=1)
    m = _GPUMonitor()
    assert m.available is True
    assert m.device_note == ""


def test_cw_gpu_index_seleziona_il_device(monkeypatch):
    """Il knob d'ambiente sceglie il device a ogni apertura, senza toccare il codice."""
    _fake_nvml(monkeypatch, count=3)
    monkeypatch.setenv("CW_GPU_INDEX", "2")
    m = _GPUMonitor()
    assert m.available is True
    assert m.index == 2
    assert m.device_selection == "CW_GPU_INDEX"
    assert m.device_note == ""


def test_cw_gpu_index_non_numerico_non_apre_niente(monkeypatch):
    """Una richiesta letta male non diventa "non dichiarato": e' un errore dichiarato."""
    _fake_nvml(monkeypatch, count=2)
    monkeypatch.setenv("CW_GPU_INDEX", "prima")
    m = _GPUMonitor()
    assert m.available is False
    assert m.index is None
    assert "non numerico" in m.error


# ------------------------------------------------------------- finestra
class FakeGpu:
    def __init__(self, available=True, energy_counter=True, name="FakeGPU",
                 device_note=""):
        self.available = available
        self.index = 0
        self.name = name
        self.energy_counter = energy_counter
        self.energy_counter_reason = ""
        self.device_note = device_note


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


def test_la_selezione_del_device_arriva_nella_riga():
    """La nota del monitor va in ``notes``: chi legge il CSV deve sapere quale scheda ha prodotto il numero.

    Lo schema di P5 e' congelato e qui non serve una colonna nuova: la selezione
    e' contesto della riga, come le altre note. Il test passa dal profilo, non
    dal monitor, perche' il punto e' che l'informazione attraversi la catena
    fino alla riga.
    """
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    s._gpu = FakeGpu(device_note="2 GPU nvml: aperto l'indice 0 perche' la "
                                "selezione del device non e' dichiarata "
                                "(CW_GPU_INDEX)")
    res = profile(s)
    assert res.gpu_device_index == 0
    assert any("aperto l'indice 0" in n for n in res.notes)


def test_senza_nota_di_selezione_la_riga_non_ne_inventa_una():
    """Nessuna selezione implicita = nessuna nota: lo spazio non si riempie da solo."""
    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    res = profile(s)
    assert not any("indice 0" in n for n in res.notes)


# ------------------------------------------------- attribuzione per processo (N/A dichiarato)
# ``process_energy_j`` rispondeva None e la riga scriveva comunque
# "nvmlDeviceGetProcessUtilization non disponibile per i PID Ollama": una
# ragione sola, falsa nel caso piu' frequente (il bordo board-attivo, letto via
# ``getattr`` e mai assegnato da nessun percorso). Inoltre il binding NVML
# installato su questa macchina espone i campioni come
# ``(pid, timeStamp, smUtil, memUtil, encUtil)`` -- nessuna DURATA per processo
# (pynvml.py:1755-1761, letto il 04-11-2026) -- quindi la "frazione del tempo di
# finestra" che il codice costruiva non ha un campo da cui venire. Questi test
# fissano che l'assenza sia nominata, non mascherata da una sola ragione.
def _campione_legame_reale(pid=7, sm=40):
    """La forma vera del binding: pid + timeStamp + percentuali, senza durata."""
    return SimpleNamespace(pid=pid, timeStamp=1_000_000, smUtil=sm,
                           memUtil=0, encUtil=0)


def test_il_legame_nvml_reale_non_espone_una_durata_e_lo_dice(monkeypatch):
    """PID presente e API disponibile, ma nessun campo durata: N/A con la ragione giusta."""
    mod = _fake_nvml(monkeypatch)
    mod.nvmlDeviceGetProcessUtilization = lambda h, t: [_campione_legame_reale()]
    m = _GPUMonitor()
    assert m.available is True
    assert m.process_energy_j(T0, T0 + 1.0, [7]) is None
    assert "non espongono una durata" in m.process_energy_reason
    # e non accusa ne' i PID ne' il bordo: la ragione e' una sola
    assert "nessun PID" not in m.process_energy_reason
    assert "_last_window_board_active_j" not in m.process_energy_reason


def test_pid_non_nei_campioni_dichiara_i_pid(monkeypatch):
    """I campioni ci sono ma per altri PID: la ragione sono i PID, non l'API."""
    mod = _fake_nvml(monkeypatch)
    mod.nvmlDeviceGetProcessUtilization = lambda h, t: [
        _campione_legame_reale(pid=99)]
    m = _GPUMonitor()
    assert m.process_energy_j(T0, T0 + 1.0, [7]) is None
    assert m.process_energy_reason == (
        "nessun PID Ollama nei campioni di utilizzo NVML")


def test_bordo_board_attivo_mai_assegnato_non_accusa_l_api(monkeypatch):
    """Con una durata disponibile il None viene dal bordo mancante, e la ragione dice quello."""
    mod = _fake_nvml(monkeypatch)
    mod.nvmlDeviceGetProcessUtilization = lambda h, t: [SimpleNamespace(
        pid=7, utilization={"gpu": 50.0},
        time_range=SimpleNamespace(start=0, end=500_000))]
    m = _GPUMonitor()
    assert m.process_energy_j(T0, T0 + 1.0, [7]) is None
    assert "_last_window_board_active_j" in m.process_energy_reason
    assert "nvmlDeviceGetProcessUtilization ha fallito" not in (
        m.process_energy_reason)


def test_con_bordo_registrato_il_campo_esiste_e_resta_sotto_il_board(monkeypatch):
    """Scala la frazione sul board attivo: il valore esiste solo con entrambi gli ingressi.

    Si verifica la disuguaglianza (0 < attribuito < board), non il numero
    assoluto: il fattore che converte i campioni in frazione di finestra non e'
    ancorato a un binding reale -- quello reale non da durate -- e un test che
    congeli un numero qui congeli un'assunzione.
    """
    mod = _fake_nvml(monkeypatch)
    mod.nvmlDeviceGetProcessUtilization = lambda h, t: [SimpleNamespace(
        pid=7, utilization={"gpu": 50.0},
        time_range=SimpleNamespace(start=0, end=500_000))]
    m = _GPUMonitor()
    m._last_window_board_active_j = 10.0
    v = m.process_energy_j(T0, T0 + 1.0, [7])
    assert v is not None and 0.0 < v < 10.0
    assert m.process_energy_reason is None


def test_la_riga_porta_la_ragione_del_monitor_non_una_formula_fissa():
    """Il motivo dell'N/A attraversa la catena fino alla riga."""

    class _GpuConRagione(FakeGpu):
        def process_energy_j(self, t_start, t_end, pids):
            self.process_energy_reason = (
                "i campioni NVML dei PID dichiarati non espongono una durata")
            return None

    s = FakeSession(p_gpu=100.0, idle_gpu_w=20.0, energy_counter=True)
    s._gpu = _GpuConRagione()
    res = profile(s)
    assert res.gpu_process_energy_j is None
    assert any("non espongono una durata" in n for n in res.notes)
    assert not any("nvmlDeviceGetProcessUtilization non disponibile" in n
                   for n in res.notes)
