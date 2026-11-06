# -*- coding: utf-8 -*-
"""Termine GPU condizionale di ``EnergySession.settle_idle``.

Perche' questo file esiste. P1.5 chiede la stazionarieta' della **macchina**
prima e dopo il blocco, ma ``settle_idle`` guardava solo il package CPU. Dopo
un'inferenza una dGPU tiene il P-state alto per secondi: un settling solo-CPU
dichiara "a riposo" una macchina che non lo e'. Il termine GPU proposto dalla
bozza, pero', componeva un AND rigido con un canale che su molti host non
esiste: ``current_gpu`` restava ``None`` per sempre, il criterio non si
soddisfaceva mai e ogni blocco pagava i 120 s del tetto per perdere
``settle_pre_s``. Qui la regola e' condizionale:

* canale GPU assente -> criterio CPU, esito ``"channel-absent"`` dichiarato
  (osservazione non possibile, non un fallimento);
* canale presente -> servono due finestre stabili **anche** sulla scheda,
  con la catena dichiarata (contatore cumulativo, altrimenti integrale della
  potenza);
* canale presente ma finestre illeggibili fino al tetto -> ``None`` con
  ``"not-observed"`` e la ragione: la stabilita' non e' osservata, non e'
  inventata.

Le relazioni sotto prova sono fisiche, non di forma: due finestre sono
"stabili" quando le loro potenze medie differiscono meno della tolleranza, la
potenza media e' energia della finestra divisa per la sua durata, e un delta
negativo del contatore non e' una finestra a zero watt. L'hardware reale resta
[V] da fare: qui il monitor e' finto e l'orologio e' iniettato.
"""
from __future__ import annotations

import pytest

import benchmark_v4 as v4
from energy.energy_session import EnergySession, SystemSample


class _FakeGpuMonitor:
    """Superficie minima del monitor GPU usata dal settling."""

    backend = "nvml"

    def __init__(self, *, available=True, counter=True, index=0,
                 name="FakeGPU"):
        self.available = available
        self.energy_counter = counter
        self.energy_counter_reason = "" if counter else "contatore assente"
        self.error = "" if available else "LibraryNotFound"
        self.index = index
        self.name = name
        self.device_selection = "indice esplicito: 0"
        self.device_note = ""


class _Clock:
    """Orologio monotono finto: ``sleep`` avanza lo stesso tempo che legge."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def _samples(schedule, *, t_from=-40.0, t_to=200.0, step=0.5,
             counter=True, timestamps=True):
    """Campioni GPU coerenti: potenza da ``schedule(t)`` e contatore integrato.

    Il contatore cumulativo e' costruito con la stessa regola trapezoidale che
    usa ``_gpu_power_window`` quando integra la potenza: cosi' le due catene,
    sullo stesso segnale, devono dare la stessa finestra. Non e' una comodita'
    del test: e' la proprieta' che il test verifica.
    """
    out = []
    energy_mj = 0.0
    n = int(round((t_to - t_from) / step))
    t_prev = t_from
    p_prev = schedule(t_from)
    for i in range(n + 1):
        t = round(t_from + i * step, 6)
        p = schedule(t)
        if counter:
            energy_mj += (p_prev + p) / 2.0 * (t - t_prev) * 1000.0
        out.append(SystemSample(
            t=t,
            wall=0.0,
            package_energy_j=0.0,
            cpu_busy_seconds=0.0,
            cpu_percent=0.0,
            gpu_power_w=p,
            gpu_energy_mj=(energy_mj if counter else None),
            gpu_energy_ts_ns=(int(t * 1e9) if timestamps else None),
        ))
        t_prev, p_prev = t, p
    return out


def _session(monkeypatch, monitor, samples):
    """Sessione con monitor e campioni sostituiti; CPU costante a 10 W.

    Il package non c'entra con i test GPU: si sostituisce solo la lettura
    esatta della finestra, cosi' il criterio CPU e' costante e il tempo
    restituito e' deciso dal termine GPU.
    """
    s = EnergySession()
    s._gpu = monitor
    s._samples = list(samples)
    monkeypatch.setattr(
        s, "package_energy_exact_between", lambda a, b: 10.0 * (b - a))
    return s


def _warm_up(t: float) -> float:
    """20 W fino a t = 0 (coda della richiesta), poi 5 W a riposo."""
    return 20.0 if t < 0.0 else 5.0


# ------------------------------------------------- canale assente: solo CPU
def test_senza_canale_gpu_il_criterio_resta_cpu(monkeypatch):
    """Nessuna GPU: due finestre CPU consecutive bastano, e l'esito lo dichiara.

    L'AND rigido con un canale assente non si soddisfa mai: ogni blocco
    pagherebbe il tetto per perdere il tempo di settling. Con la regola
    condizionale il settling si chiude alla prima coppia di finestre stabili e
    ``channel-absent`` dice che l'osservazione GPU non era possibile, non che
    e' fallita.

    La prima coppia completa esiste solo a ``2 * window_s`` = 20 s: la corrente
    su ``[now-10, now]`` e la precedente su ``[now-20, now-10]`` non si
    sovrappongono, e sotto i 20 s la seconda cadrebbe fuori dalla finestra di
    osservazione. Prima di questo vincolo il criterio confrontava la finestra
    corrente con quella del ciclo di prima -- cioe' la stessa finestra spostata
    di 1 s, condivisa per 9 decimi -- e si chiudeva a 1 s.
    """
    mon = _FakeGpuMonitor(available=False, counter=False)
    samples = _samples(lambda t: 5.0, counter=False, timestamps=False)
    for s in samples:
        s.gpu_power_w = None
    sess = _session(monkeypatch, mon, samples)
    clock = _Clock()

    t = sess.settle_idle(clock=clock, sleep=clock.sleep)

    assert t == pytest.approx(20.0)
    assert sess.last_settle_gpu_status == "channel-absent"
    assert "canale GPU assente" in sess.last_settle_gpu_reason
    assert sess.last_settle_gpu_chain is None


# ------------------------------------------- canale presente: AND richiesto
def test_gpu_presente_ritarda_il_settle_fino_alla_sua_stabilita(monkeypatch):
    """CPU stabile a 1 s, GPU in coda a 20 W: si aspetta anche la scheda.

    Il tempo restituito non e' quello del package: e' il primo istante in cui
    due finestre consecutive sono stabili su entrambi i domini. Il margine di
    10 s e' la finestra che deve uscire per intero dal transiente (qui 0 s),
    non una costante scelta a mano.
    """
    mon = _FakeGpuMonitor()
    sess = _session(monkeypatch, mon, _samples(_warm_up))
    clock = _Clock()

    t = sess.settle_idle(clock=clock, sleep=clock.sleep)

    assert t is not None
    assert t > 1.0                      # il solo CPU si chiuderebbe a 1 s
    assert t >= 10.0                    # finestra da 10 s fuori dal transiente
    assert sess.last_settle_gpu_status == "stable"
    assert sess.last_settle_gpu_chain == "nvml-energy"


def test_integrale_e_contatore_danno_lo_stesso_settle(monkeypatch):
    """Contatore assente ma potenza leggibile: stessa finestra, altra catena.

    L'integrale trapezoidale e il delta del contatore misurano la stessa
    energia quando i campioni sono gli stessi: il settling deve chiudersi
    nello stesso istante, e la catena dichiarata cambia (e' un'evidenza
    diversa, non un numero diverso).
    """
    mon_ctr = _FakeGpuMonitor(counter=True)
    s_ctr = _session(monkeypatch, mon_ctr, _samples(_warm_up, counter=True))
    c_ctr = _Clock()
    t_ctr = s_ctr.settle_idle(clock=c_ctr, sleep=c_ctr.sleep)

    mon_int = _FakeGpuMonitor(counter=False)
    s_int = _session(monkeypatch, mon_int, _samples(_warm_up, counter=False))
    c_int = _Clock()
    t_int = s_int.settle_idle(clock=c_int, sleep=c_int.sleep)

    assert t_int == t_ctr
    assert s_ctr.last_settle_gpu_chain == "nvml-energy"
    assert s_int.last_settle_gpu_chain == "nvml-power-integral"


# ------------------------------------------ canale presente ma illeggibile
def test_canale_presente_ma_illeggibile_va_al_tetto(monkeypatch):
    """GPU presente e nessun campione leggibile: ``None``, non un falso idle.

    Se la scheda c'e' ma non sappiamo leggerla, dichiarare la macchina a
    riposo sulla sola CPU e' una stabilita' mai osservata. Al tetto il
    ritorno e' ``None`` con la ragione, e il runner la scrive in ``notes``.
    """
    mon = _FakeGpuMonitor()
    samples = _samples(lambda t: 5.0, counter=False)
    for s in samples:
        s.gpu_power_w = None
        s.gpu_energy_mj = None
    sess = _session(monkeypatch, mon, samples)
    clock = _Clock()

    t = sess.settle_idle(timeout_s=5.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert sess.last_settle_gpu_status == "not-observed"
    assert "nessun campione GPU leggibile" in sess.last_settle_gpu_reason


def test_delta_negativo_non_diventa_una_finestra_a_zero(monkeypatch):
    """Contatore che torna indietro: finestra illeggibile, mai clampata a 0 W.

    Un delta negativo e' un reset o un avvolgimento. Trattarlo come una
    finestra a potenza zero la farebbe sembrare "stabilissima" e chiuderebbe
    il settling su un riposo inventato; qui la finestra non esiste e il
    settling va al tetto dichiarando la causa.
    """
    mon = _FakeGpuMonitor()
    samples = _samples(lambda t: 5.0)
    for i, s in enumerate(samples):
        s.gpu_energy_mj = -1000.0 * i      # contatore sempre decrescente
    sess = _session(monkeypatch, mon, samples)
    clock = _Clock()

    t = sess.settle_idle(timeout_s=5.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert sess.last_settle_gpu_status == "not-observed"
    assert "decrescente" in sess.last_settle_gpu_reason
    assert "non si clampa" in sess.last_settle_gpu_reason


def test_finestre_gpu_leggibili_ma_non_stabili_vanno_al_tetto(monkeypatch):
    """GPU in crescita lenta: leggibile ma mai stabile, ``None`` con la ragione.

    Una scheda che sale di 1 W per finestra non e' a riposo anche se il
    package lo e'. La ragione dichiara il caso "leggibile ma non stabile",
    diverso da "non leggibile", perche' le due cose hanno rimedi diversi.
    """
    mon = _FakeGpuMonitor()
    # salita di 5 W/s (mai negativa): la media sulla finestra da 10 s cresce
    # di 5 W a ogni passo di 1 s, oltre la tolleranza di 0,5 W
    sess = _session(monkeypatch, mon,
                    _samples(lambda t: max(0.0, 5.0 + 5.0 * t)))
    clock = _Clock()

    t = sess.settle_idle(timeout_s=5.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert sess.last_settle_gpu_status == "not-observed"
    assert "non stabili fino al tetto" in sess.last_settle_gpu_reason


def test_timestamp_fermo_non_e_un_intervallo(monkeypatch):
    """AMD SMI con timestamp identico: lettura non avanzata, finestra non valida.

    Il timestamp del device e' un controllo di avanzamento, non una durata:
    se non avanza il contatore non ha riletto e l'incremento non e' energia.
    """
    mon = _FakeGpuMonitor()
    samples = _samples(lambda t: 5.0, timestamps=False)
    for s in samples:
        s.gpu_energy_ts_ns = 100
    sess = _session(monkeypatch, mon, samples)
    clock = _Clock()

    t = sess.settle_idle(timeout_s=5.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert "timestamp" in sess.last_settle_gpu_reason


# --------------------------------------------------- finestra GPU unitaria
def test_zero_con_timestamp_che_avanza_e_una_finestra_valida(monkeypatch):
    """Contatore fermo e timestamp che avanza: 0 W misurato, non ``None``.

    E' la stessa distinzione dei bordi del package (``local_energy.py``): una
    scheda che in una finestra non accumula joule ha misurato zero. La media
    vale 0 W e non la potenza del package, che qui e' 10 W: le due grandezze
    non si confondono.
    """
    mon = _FakeGpuMonitor()
    sess = _session(monkeypatch, mon, _samples(lambda t: 0.0))
    for s in sess._samples:
        s.gpu_energy_mj = 500.0            # contatore costante
        s.gpu_energy_ts_ns = int(s.t * 1e9)

    w, chain, reason = sess._gpu_power_window(0.0, 10.0)

    assert w == pytest.approx(0.0)
    assert chain == "nvml-energy"
    assert reason == ""


def test_la_finestra_gpu_e_energia_divisa_per_durata(monkeypatch):
    """10 W costanti su 10 s: il contatore sale di 100 000 mJ, la media e' 10 W."""
    mon = _FakeGpuMonitor()
    sess = _session(monkeypatch, mon, _samples(lambda t: 10.0))

    w, chain, reason = sess._gpu_power_window(0.0, 10.0)

    assert w == pytest.approx(10.0)
    assert chain == "nvml-energy"
    assert reason == ""


# ----------------------------------------- dichiarazione nella riga (runner)
def test_la_nota_non_sporca_gli_esiti_osservati():
    """``stable`` e ``None`` non aggiungono testo: la riga resta com'era."""
    assert v4._gpu_settle_note("pre", "stable", "") == ""
    assert v4._gpu_settle_note("post", None, "") == ""


def test_la_nota_dichiara_quale_settling_e_solo_cpu():
    """Canale assente o illeggibile: la nota dice pre/post, esito e ragione.

    Senza questa nota ``settle_pre_s`` e ``settle_post_s`` sembrerebbero la
    stabilita' dell'intera macchina, mentre coprono il solo package.
    """
    assente = v4._gpu_settle_note("post", "channel-absent",
                                  "canale GPU assente")
    assert "post" in assente
    assert "channel-absent" in assente
    assert "canale GPU assente" in assente

    illeggibile = v4._gpu_settle_note(
        "pre", "not-observed", "timestamp del contatore nvml fermo (100 ns)")
    assert "pre" in illeggibile
    assert "not-observed" in illeggibile
    assert "timestamp del contatore" in illeggibile


def test_le_note_arrivano_a_ogni_riga_senza_cancellare_le_altre():
    """La nota GPU si accoda alle note esistenti, su tutte le righe del blocco."""
    rows = [{"notes": ""}, {"notes": "nota gia' presente"}]

    v4._append_gpu_settle_notes(rows, "channel-absent", "canale GPU assente",
                                "stable", "")

    assert "canale GPU assente" in rows[0]["notes"]
    assert rows[1]["notes"].startswith("nota gia' presente; ")
    assert "canale GPU assente" in rows[1]["notes"]
    assert "post" not in rows[0]["notes"]      # il post era stabile
