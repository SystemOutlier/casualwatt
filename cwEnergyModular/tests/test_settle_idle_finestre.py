# -*- coding: utf-8 -*-
"""Le due finestre di ``EnergySession.settle_idle`` devono essere consecutive.

Perche' esiste. P1.5 chiede la stazionarieta' della macchina *prima* e *dopo*
il blocco, espressa da due medie consecutive su finestre di ``window_s`` che
differiscono meno di ``tolerance_w``. La produzione confrontava la media della
finestra ``[now-window_s, now]`` con quella del ciclo precedente, cioe' con
``[now-window_s-1, now-1]``: due finestre condivise per 9 decimi. Su un drift
costante la differenza fra due finestre cosi' fatte vale ``k * 1 s`` qualunque
sia ``window_s``, quindi una rampa da 0,4 W/s passava il criterio con
``tolerance_w = 0,5`` dopo un solo ciclo -- e il settling dichiarava "a
riposo" una macchina che stava salendo. Il confronto giusto e' fra le finestre
``[now-2*window_s, now-window_s]`` e ``[now-window_s, now]``, che si toccano e
non si sovrappongono: li' la stessa rampa vale ``k * window_s``, dieci volte
di piu'.

Che cosa verifica -- ogni valore atteso e' derivato a mano dalla schedule di
potenza scelta dal test, non letto dal codice sotto prova:
  1. potenza costante: la prima coppia completa esiste a ``2 * window_s`` e li'
     il criterio si chiude; prima di quel punto la finestra precedente non ha
     ancora una base leggibile, e nessuna lettura del package viene fatta;
  2. rampa che non si esaurisce: il criterio non si soddisfa mai e il ritorno
     e' ``None`` al tetto, con la ragione dichiarata;
  2b. rampa lenta (0,4 W/s) sotto la tolleranza *per ciclo*: e' il caso che
     la regola vecchia accettava dopo 1 s; qui arriva al tetto;
  3. rampa che si esaurisce: passa solo quando entrambe le finestre stanno
     fuori dal transiente, perche' e' allora che le due medie concordano;
  4. termine GPU: la stessa coppia non sovrapposta vale anche per la scheda.
     Quando e' la GPU a vincolare e' lei a decidere il tempo, e una deriva
     permanente della scheda non chiude il settling anche se il package e'
     stabile.

Che cosa NON verifica: la catena di lettura del dominio GPU (contatore NVML,
integrale di potenza, timestamp fermo, delta negativo), che sta in
``test_settle_idle_gpu.py`` e nei file dei backend; qui ``_gpu_power_window``
e' sostituito da una media analitica sulla finestra richiesta, per isolare la
regola di *accoppiamento* delle due finestre. L'hardware reale resta [V] da
fare: orologio e sleep sono iniettati, nessuna attesa reale.
"""
from __future__ import annotations

import pytest

from energy.energy_session import EnergySession


class _Clock:
    """Orologio monotono finto: ``sleep`` avanza lo stesso tempo che legge."""

    def __init__(self, t: float = 0.0):
        self.t = t
        self.reads = 0

    def __call__(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        self.t += dt


def _sessione(monkeypatch, integ):
    """Sessione con il package sostituito dall'integrale ``integ(a, b)``.

    Il monitor GPU e' assente salvo dove il test lo chiede: il termine CPU
    e' l'unico criterio, e le finestre lette sono contate.
    """
    s = EnergySession()
    s._gpu = None
    calls: list = []

    def exact_between(a, b):
        calls.append((round(float(a), 6), round(float(b), 6)))
        return integ(a, b)

    monkeypatch.setattr(s, "package_energy_exact_between", exact_between)
    s._calls = calls
    return s


# ------------------------------------------------------------------ 1) costante
def test_potenza_costante_chiude_alla_prima_coppia_completa(monkeypatch):
    """10 W costanti: il settling vale ``2 * window_s``, e nessuna lettura prima.

    Verifica il punto minimo del nuovo criterio: la finestra precedente su
    ``[now-20, now-10]`` non esiste prima di ``now = 20``, e sotto quella
    soglia la produzione non valuta nulla -- quindi non chiama nemmeno il
    contatore. Con i 10 W costanti le due medie coincidono e il ritorno e'
    l'elapsed di quell'iterazione.
    """
    sess = _sessione(monkeypatch, lambda a, b: 10.0 * (b - a))
    clock = _Clock()

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=120.0,
                         step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t == pytest.approx(20.0)
    # Le prime due letture compaiono solo a now = 20: nessuna finestra
    # parziale e' stata valutata nei diciannove cicli precedenti.
    assert sess._calls == [(10.0, 20.0), (0.0, 10.0)]


def test_finestre_non_sovrapposte_sono_le_due_letture(monkeypatch):
    """Le due finestre lette sono adiacenti, non spostate di un ciclo.

    Verifica la forma geometrica del criterio: corrente ``[now-10, now]`` e
    precedente ``[now-20, now-10]`` condividono il bordo ``now-10`` e nessun
    interno. La regola vecchia leggeva ``[now-10, now]`` e, un ciclo prima,
    ``[now-11, now-1]``: la stessa finestra traslata di 1 s, con 9 s di
    interno comune.
    """
    sess = _sessione(monkeypatch, lambda a, b: 10.0 * (b - a))
    clock = _Clock()

    sess.settle_idle(window_s=10.0, step_s=1.0, clock=clock, sleep=clock.sleep)

    cur, prev = sess._calls
    assert cur[0] == pytest.approx(10.0) and cur[1] == pytest.approx(20.0)
    assert prev[0] == pytest.approx(0.0) and prev[1] == pytest.approx(10.0)
    assert prev[1] == cur[0]                      # adiacenti: un bordo, non un interno
    assert abs((cur[1] - cur[0]) - (prev[1] - prev[0])) < 1e-9


# ------------------------------------------------------- 2) rampa mai stabile
def test_rampa_non_esaurita_arriva_al_tetto_con_none(monkeypatch):
    """5 W/s che non si fermano: ``None`` al tetto, con la ragione dichiarata.

    Verifica che un drift sopra la tolleranza non chiuda mai il criterio. La
    media su una finestra da 10 s di una rampa da 5 W/s vale 50 W piu' della
    media della finestra che la precede: ``abs(diff) = 50`` contro
    ``tolerance_w = 0.5``, e il ciclo finisce al tetto senza inventare un
    tempo di stabilizzazione mai osservato.
    """
    sess = _sessione(monkeypatch, lambda a, b: 2.5 * (b * b - a * a))
    clock = _Clock()

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=40.0,
                        step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert clock.t == pytest.approx(40.0)          # il tetto e' stato pagato
    assert sess.last_settle_gpu_status == "channel-absent"


def test_rampa_lenta_sotto_la_tolleranza_per_ciclo_non_passa(monkeypatch):
    """0,4 W/s: la regola vecchia passava al primo ciclo, questa va al tetto.

    Verifica il difetto specifico, non la sua conseguenza generica. Con le
    finestre spostate di 1 s la differenza fra le due medie vale
    ``0.4 W/s * 1 s = 0.4 W``, che sta sotto ``tolerance_w = 0.5``: il
    settling si chiudeva dopo un ciclo su una macchina che stava salendo. Con
    le finestre non sovrapposte la stessa pendenza vale ``0.4 * 10 = 4.0 W``,
    otto volte la tolleranza, e il criterio non si soddisfa mai.
    """
    sess = _sessione(monkeypatch, lambda a, b: 0.2 * (b * b - a * a))
    clock = _Clock()

    def potenza_ombra(now):
        # 0.4 W/s: la media su [now-10, now] e' 0.4*(now-5)
        return 0.4 * (now - 5.0)

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=30.0,
                         step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t is None
    # Il delta fra due finestre consecutive, alla fine del tetto: 4.0 W contro
    # una tolleranza di 0.5 W. Sotto i 0,5 W ci sarebbe stato con le finestre
    # traslate di un ciclo, ed e' esattamente la firma del difetto.
    assert abs(potenza_ombra(30.0) - potenza_ombra(20.0)) == pytest.approx(4.0)
    assert abs(potenza_ombra(30.0) - potenza_ombra(29.0)) < 0.5


# ------------------------------------------------------ 3) rampa che si esaurisce
def test_rampa_che_si_esaurisce_passa_fuori_dal_transiente(monkeypatch):
    """``min(5t, 75)``: il criterio si chiude a 34 s, non prima.

    Verifica il caso in cui la stazionarieta' arriva davvero, e che il tempo
    restituito e' quello della *seconda* finestra. Con F(t) = 2,5t^2 fino a
    15 s e 75 W dopo, la media della finestra corrente vale 75 W da
    ``now = 25``; la precedente e' interamente fuori dal transiente solo da
    ``now = 35``, ma a ``now = 34`` resta dentro il transiente per 1 s e
    perde 0,25 W -- sotto la tolleranza. Quindi il primo ciclo accettabile
    e' 34: a 33 la differenza e' 1,0 W e il criterio giustamente resiste.
    Con le finestre traslate di 1 s avrebbe chiuso prima, perche' il
    transiente sarebbe uscito dalla finestra corrente mentre era ancora
    dentro la precedente.
    """
    def F(t):
        return 2.5 * t * t if t <= 15.0 else 562.5 + 75.0 * (t - 15.0)

    sess = _sessione(monkeypatch, lambda a, b: F(b) - F(a))
    clock = _Clock()

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=120.0,
                         step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t == pytest.approx(34.0)
    # A now = 34: corrente 75,00 W, precedente 74,75 W (1 s di rampa dentro).
    assert sess._calls[-1] == (14.0, 24.0)


# ------------------------------------------------------------------ 4) GPU
class _MonitorFinto:
    available = True
    backend = "nvml"


def test_il_termine_gpu_usa_la_stessa_coppia_non_sovrapposta(monkeypatch):
    """Package stabile dalla prima coppia, GPU in coda: il tempo e' della GPU.

    Verifica che il termine GPU non sia stato lasciato alla vecchia coppia
    traslata mentre il package passava alla coppia consecutiva. Il package
    vale 10 W costanti ed e' stabile appena la coppia esiste; la GPU sale di
    5 W/s fino a 50 W a ``t = 10`` e poi tiene. A ``now = 20`` la finestra
    corrente e' piatta e quella *del ciclo precedente* (``[9, 19]``) differiva
    per 0,25 W -- sotto la tolleranza: la regola vecchia dichiarava la scheda
    stabile nove secondi prima. Con le finestre non sovrapposte la precedente
    a ``now = 20`` e' ``[0, 10]``, tutta dentro il transiente (25 W contro
    50 W), e la prima coppia in cui entrambe stanno fuori dal rampa vale
    ``[9, 19]`` contro ``[19, 29]``: 49,75 W e 50 W, differenza 0,25 W, il
    primo ciclo accettabile. Il ritorno e' 29, perche' e' la GPU a vincolare.
    """
    def F(t):
        return 2.5 * t * t if t <= 10.0 else 250.0 + 50.0 * (t - 10.0)

    sess = _sessione(monkeypatch, lambda a, b: 10.0 * (b - a))
    sess._gpu = _MonitorFinto()

    lette: list = []

    def gpu_window(a, b):
        # Media esatta della rampa 5 W/s saturata a 50 W: nessuna
        # approssimazione, il valore atteso di 29 s deriva da qui.
        lette.append((round(float(a), 6), round(float(b), 6)))
        return (F(b) - F(a)) / (b - a), "nvml-energy", ""

    monkeypatch.setattr(sess, "_gpu_power_window", gpu_window)
    clock = _Clock()

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=120.0,
                         step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t == pytest.approx(29.0)
    assert sess.last_settle_gpu_status == "stable"
    assert sess.last_settle_gpu_chain == "nvml-energy"
    assert sess.last_settle_gpu_reason == ""
    # La GPU legge le due finestre adiacenti, come il package: [19, 29] e
    # [9, 19], non [19, 29] e [18, 28].
    cur, prev = lette[-2], lette[-1]
    assert (cur, prev) == ((19.0, 29.0), (9.0, 19.0))


def test_gpu_con_deriva_permanente_non_chiude_il_settling(monkeypatch):
    """GPU che sale di 0,2 W/s: con le finestre consecutive non passa mai.

    Verifica il caso che il difetto rendeva accettabile. Una deriva di
    0,2 W/s vale 0,2 W fra due finestre traslate di un ciclo -- sotto
    ``tolerance_w = 0.5``, quindi la scheda sembrava stabile -- e vale 2 W fra
    due finestre consecutive, quattro volte la tolleranza. Il package e'
    stabile dalla prima coppia completa e non basta: il ritorno e' ``None``
    con l'esito ``not-observed``, perche' la stazionarieta' della macchina non
    e' osservata se un dominio continua a muoversi.
    """
    sess = _sessione(monkeypatch, lambda a, b: 10.0 * (b - a))
    sess._gpu = _MonitorFinto()

    def gpu_window(a, b):
        # p(t) = 5 + 0.2t: media su [a, b] = 5 + 0.2*(a+b)/2
        return 5.0 + 0.2 * (a + b) / 2.0, "nvml-energy", ""

    monkeypatch.setattr(sess, "_gpu_power_window", gpu_window)
    clock = _Clock()

    t = sess.settle_idle(window_s=10.0, tolerance_w=0.5, timeout_s=40.0,
                         step_s=1.0, clock=clock, sleep=clock.sleep)

    assert t is None
    assert sess.last_settle_gpu_status == "not-observed"
    assert "non stabili fino al tetto" in sess.last_settle_gpu_reason

