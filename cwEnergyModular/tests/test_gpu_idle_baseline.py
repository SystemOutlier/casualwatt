# -*- coding: utf-8 -*-
"""Baseline idle della GPU: ``EnergySession.calibrate_gpu_idle``.

Perche' questa cartella di test esiste. La riga legge
``session.idle_gpu_power_w`` (``energy/local_energy.py:931``) per sottrarre
la potenza a riposo della scheda (:943) e ne ricava
``gpu_idle_provenance`` (:936). Fino a questa modifica nessun percorso di
produzione assegnava quel campo: i soli assegnamenti erano nei test, quindi
su una macchina con GPU ogni riga usciva ``missing`` e attribuiva al modello
la potenza TOTALE della scheda. Lo stesso difetto di classe che ``AGENTS.md``
registra per ``_last_window_board_active_j``.

La relazione fisica sotto prova e' quella di P1.3 applicata al contatore della
GPU: ``P_rep = delta E_contatore / delta t`` su tre finestre da 30 s, e
``P_idle = mediana(P_rep)``. Nulla qui stima una potenza: il valore esce dal
delta di un contatore cumulativo diviso per l'intervallo di ``monotonic`` che
lo contiene.

Quello che questi test rifiutano, e che una implementazione "ragionevole"
avrebbe fatto:

* usare la potenza istantanea come media di una finestra da 30 s (sono due
  grandezze diverse, ed e' l'errore che produsse il +16% residuo dei four-way
  col canale LHM);
* clampare a zero un delta negativo, che e' un reset e non una misura;
* trattare un timestamp fermo come una finestra da zero joule;
* lasciare ``idle_gpu_power_w`` a un valore plausibile quando il contatore
  tace.

Nessun test richiede una GPU: il monitor e' un finto oggetto e i 90 s di
attesa sono iniettati. L'esecuzione su hardware reale resta [V] da fare.
"""
from __future__ import annotations

import pytest

from energy.energy_session import EnergySession


class _FakeGpuMonitor:
    """Monitor GPU minimo: la stessa superficie che ``local_energy`` usa.

    ``read_energy`` restituisce i valori in sequenza, due letture per
    ripetizione (bordo iniziale e finale). ``read`` conta le chiamate: la
    potenza istantanea non deve entrare nella baseline, e un test la misura
    contando.
    """

    backend = "nvml"

    def __init__(self, values, *, timestamps=None, available=True,
                 counter=True, reason="", error=None, index=0,
                 name="FakeGPU", selection="indice esplicito: 0"):
        self._values = list(values)
        self._timestamps = timestamps
        self.available = available
        self.energy_counter = counter
        self.energy_counter_reason = reason
        self.error = error
        self.index = index
        self.name = name
        self.device_selection = selection
        self.device_note = ""
        self.energy_reads = 0
        self.power_reads = 0

    def read_energy(self):
        i = self.energy_reads
        self.energy_reads += 1
        value = self._values[min(i, len(self._values) - 1)]
        ts = None
        if self._timestamps is not None:
            ts = self._timestamps[min(i, len(self._timestamps) - 1)]
        return value, ts

    def read(self):
        self.power_reads += 1
        return 999.0, 50.0

    def get_uuid(self):
        return "fake-uuid-nvml"


def _clock_over(values):
    """Clock iniettato: restituisce i valori in ordine (due letture per rep)."""
    seq = iter(values)
    return lambda: next(seq)


def _session(monkeypatch, monitor):
    """Sessione con il monitor sostituito e il floor a 30 s non ereditato."""
    monkeypatch.delenv("CW_GPU_IDLE_WINDOW_S", raising=False)
    s = EnergySession()
    s._gpu = monitor
    return s


def _sleeper():
    slept = []
    return slept, (lambda sec: slept.append(sec))


# --------------------------------------------------------------- mediana
def test_mediana_di_tre_finestre_da_30s(monkeypatch):
    """300, 600, 450 J su 30 s sono 10, 20, 15 W: la baseline e' la mediana, 15 W.

    Con n = 3 la mediana non e' la media: se una finestra fosse contaminata da
    un transiente, la media la inseguirebbe e la mediana no. E' la ragione per
    cui P1.3 prescrive la mediana e non la media.
    """
    mon = _FakeGpuMonitor([1000.0, 301_000.0, 301_000.0, 901_000.0,
                           901_000.0, 1_351_000.0])
    s = _session(monkeypatch, mon)
    slept, slp = _sleeper()

    w = s.calibrate_gpu_idle(
        clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert w == pytest.approx(15.0)
    assert s.idle_gpu_power_w == pytest.approx(15.0)
    assert s._gpu_idle_reps == pytest.approx([10.0, 20.0, 15.0])
    assert slept == [30.0, 30.0, 30.0]
    assert s._gpu_idle_window_s == 30.0


def test_il_campo_letto_dalla_riga_viene_assegnato(monkeypatch):
    """Il nome del campo e' quello che ``local_energy`` legge, e vale > 0.

    La regressione da impedire non e' aritmetica: e' un contratto fra due
    moduli. ``local_energy.py:931`` legge ``session.idle_gpu_power_w`` e
    ``:936`` promuove a "calibrated" solo un valore maggiore di zero. Una
    calibrazione che scrivesse in un altro attributo calcolerebbe il numero
    giusto e la riga continuerebbe a dichiarare ``missing``.
    """
    s = _session(monkeypatch, _FakeGpuMonitor(
        [0.0, 300_000.0, 300_000.0, 600_000.0, 600_000.0, 900_000.0]))
    _, slp = _sleeper()

    assert s.idle_gpu_power_w is None          # contratto: assente, non zero
    s.calibrate_gpu_idle(
        clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert s.idle_gpu_power_w > 0.0
    assert s.gpu_idle_calibrated_at is not None


def test_device_calibrato_e_dichiarato(monkeypatch):
    """La baseline appartiene alla scheda aperta per la misura, e lo dice.

    L'indice GPU e' una posizione nell'elenco del backend che ha risposto, non
    un ID del produttore: due schede diverse possono avere lo stesso indice su
    vendor diversi. Una baseline senza device e' un numero attribuito male.
    """
    mon = _FakeGpuMonitor([0.0, 300_000.0, 300_000.0, 600_000.0, 600_000.0,
                           900_000.0], index=1, name="FakeGPU-1",
                          selection="CW_GPU_INDEX=1")
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    s.calibrate_gpu_idle(
        clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert s._gpu_idle_device == "nvml:1"
    assert s._gpu_idle_selection == "CW_GPU_INDEX=1"


# ------------------------------------------------------------------ floor
def test_la_finestra_non_scende_sotto_30s(monkeypatch):
    """``seconds=5`` non accorcia la finestra: il floor e' 30 s e resta.

    Una finestra breve campiona il transiente di ritorno dal P-state di
    carico, non il riposo, e la baseline che ne esce e' troppo alta. Il floor
    non e' una preferenza: e' la condizione perche' il numero descriva il
    riposo.
    """
    mon = _FakeGpuMonitor([0.0, 300_000.0, 300_000.0, 600_000.0, 600_000.0,
                           900_000.0])
    s = _session(monkeypatch, mon)
    slept, slp = _sleeper()

    s.calibrate_gpu_idle(
        seconds=5,
        clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert slept == [30.0, 30.0, 30.0]


# ------------------------------------------------------- fallimenti dichiarati
def test_senza_gpu_solleva_senza_inventare_baseline(monkeypatch):
    """Nessun monitor: RuntimeError con la causa, e il campo resta ``None``.

    Una macchina senza GPU non ha una baseline GPU da misurare. Il fallimento
    e' dichiarato perche' il chiamante deve poterlo registrare senza
    distinguere "assente" da "non misurato".
    """
    mon = _FakeGpuMonitor([], available=False, counter=False,
                          error="LibraryNotFound")
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    with pytest.raises(RuntimeError) as exc:
        s.calibrate_gpu_idle(sleep=slp)

    assert "LibraryNotFound" in str(exc.value)
    assert s.idle_gpu_power_w is None


def test_contatore_assente_non_ricade_sulla_potenza_istantanea(monkeypatch):
    """Contatore cumulativo muto: errore, e ``read()`` non viene mai chiamata.

    La potenza istantanea e la media di una finestra da 30 s sono grandezze
    diverse: usarle come sinonimi e' l'errore che produsse il +16% residuo dei
    four-way col canale LHM. Il test lo impedisce contando le chiamate, non
    leggendo il messaggio d'errore.
    """
    mon = _FakeGpuMonitor([], counter=False,
                          reason="nvmlDeviceGetTotalEnergyConsumption assente")
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    with pytest.raises(RuntimeError) as exc:
        s.calibrate_gpu_idle(sleep=slp)

    assert "nvmlDeviceGetTotalEnergyConsumption" in str(exc.value)
    assert mon.power_reads == 0
    assert s.idle_gpu_power_w is None


def test_delta_negativo_e_un_reset_e_non_si_clampa(monkeypatch):
    """Contatore che torna indietro: errore, non una finestra da zero joule.

    Il punto zero di un contatore cumulativo e' un reset del driver, non
    l'inizio della misura. Un delta negativo dice che fra i due bordi e'
    avvenuto un reset o un avvolgimento: la finestra non esiste, e zero
    sarebbe un valore inventato con l'aria di un dato.
    """
    mon = _FakeGpuMonitor([1000.0, 900.0, 900.0, 1200.0, 1200.0, 1500.0])
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    with pytest.raises(RuntimeError) as exc:
        s.calibrate_gpu_idle(
            clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert "decrescente" in str(exc.value)
    assert s.idle_gpu_power_w is None
    assert mon.energy_reads == 2       # la prima ripetizione si ferma subito


def test_timestamp_fermo_invalida_la_lettura(monkeypatch):
    """AMD SMI con timestamp identico ai bordi: lettura non avanzata, errore.

    Il timestamp del device e' un controllo di avanzamento, non una durata.
    Se non avanza, il contatore non ha riletto: l'incremento nullo non e' una
    misura, come per i bordi EMI di ``local_energy.py:461-471``.
    """
    mon = _FakeGpuMonitor([1000.0, 1000.0, 1000.0, 1000.0, 1000.0, 1000.0],
                          timestamps=[100, 100, 100, 100, 100, 100])
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    with pytest.raises(RuntimeError) as exc:
        s.calibrate_gpu_idle(
            clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert "timestamp" in str(exc.value)
    assert s.idle_gpu_power_w is None


def test_zero_con_timestamp_che_avanza_e_legittimo(monkeypatch):
    """Timestamp che avanza e contatore fermo: zero misurato, non lettura persa.

    La distinzione e' la stessa dei bordi del package: una scheda che in 30 s
    non accumula joule ha misurato zero. Il valore si registra, non si
    trasforma in ``None``: la riga dira' che la baseline non e' utilizzabile,
    ed e' un'informazione diversa da "non misurata".
    """
    mon = _FakeGpuMonitor([1000.0] * 6,
                          timestamps=[10, 20, 20, 30, 30, 40])
    s = _session(monkeypatch, mon)
    _, slp = _sleeper()

    w = s.calibrate_gpu_idle(
        clock=_clock_over([0.0, 30.0, 30.0, 60.0, 60.0, 90.0]), sleep=slp)

    assert w == 0.0
    assert s.idle_gpu_power_w == 0.0
    assert s._gpu_idle_reps == [0.0, 0.0, 0.0]
