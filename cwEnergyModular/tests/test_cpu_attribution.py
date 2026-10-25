# -*- coding: utf-8 -*-
"""
tests/test_cpu_attribution.py — L'attribuzione CPU per processo, senza hardware.

Perche' esiste. Il contatore sa quanto ha consumato il dominio PKG, non quale
processo lo ha consumato: ``E_worker = E_attiva * d_ollama/d_busy`` e' una
STIMA che ripartisce l'energia con la quota di tempo CPU BUSY del sistema. I
tre modi in cui quella stima mentiva senza dirlo erano tutti nel codice:

* l'energia attiva negativa veniva troncata a 0 senza lasciare traccia;
* uno share fuori da [0,1] veniva limitato in silenzio, rendendo
  indistinguibile un ``d_ollama > d_busy`` da uno share di 1 legittimo;
* i processi erano enumerati per nome e sommati per PID, quindi un PID
  riusato, un worker nato o morto dentro la finestra restavano invisibili.

Che cosa verifica (i punti richiesti a-g):

  a. lo share e' ``d_ollama / d_busy`` (tempo BUSY), non ``d_ollama /
     (core x finestra)``: con 6 s di CPU worker, 8 s di busy e 20 core logici
     su 1 s di finestra lo share e' 0,75, non 0,30;
  b. un package sotto la baseline lascia ``active_energy_raw_j`` negativo e
     ``active_valid=False``, con ``active_energy_j`` troncato solo per
     compatibilita' e la nota che lo dichiara;
  c. ``d_ollama > d_busy`` produce ``cpu_time_share_raw > 1``,
     ``share_anomaly = "d_ollama>d_busy"`` e share limitato a 1; lo stesso
     vale per ``d_busy = 0`` e per un denominatore oltre la capacita' fisica;
  d. un processo nato a meta' finestra conta dal suo inizio; uno perso prima
     di t_end alza ``worker_exit_in_window`` (fino alla riga CSV);
  e. stesso PID con ``create_time`` diverso non e' lo stesso processo: il
     riuso si dichiara e i due contributi non si sommano;
  f. l'albero include il runner per discendenza (``llama-server`` anche sotto
     un padre non chiamato ollama) ed esclude un processo estraneo; un runner
     fuori dall'albero viene segnalato come stray;
  g. i campi storici non cambiano significato (share limitato, energia
     attiva troncata) perche' la compatibilita' del CSV non si paga con la
     correttezza dei campi nuovi.

Che cosa NON verifica: che la quota di tempo CPU sia la quota di energia
reale (e' l'ipotesi di attribuzione, non un teorema: la prova e'
``experiment_additivity.py``, che vuole l'hardware), ne' la granularita'
vera del tick su questa macchina (``probe_cpu_time_resolution`` la misura a
runtime; qui si verifica solo che l'avviso scatti sulla soglia).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from config import OLLAMA_ROOT_NAMES, OLLAMA_RUNNER_NAMES  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402
from energy.worker_tree import (  # noqa: E402
    ProcInfo,
    WorkerProc,
    build_worker_tree,
    read_worker_cpu_times,
    stray_runners,
    worker_cpu_delta,
)

T0 = 1000.0
STEP = 0.5


class _FakeSession:
    """Sessione sintetica: contatore costante e campioni regolari.

    ``package_energy_exact_between`` restituisce il valore fornito: la finestra
    dei test e' di 1 s e il valore e' scelto per costruire l'energia attiva
    voluta, senza dipendere da un contatore reale.
    """

    source_method = "emi-counter"
    interval_s = STEP
    idle_gpu_power_w = None
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self, package_j=100.0, idle_w=10.0,
                 idle_provenance="calibrated", n_samples=3,
                 cpu_time_resolution_s=None):
        self.idle_power_w = idle_w
        self.idle_provenance = idle_provenance
        self._package_j = package_j
        self.cpu_time_resolution_s = cpu_time_resolution_s
        self.samples = [
            SimpleNamespace(
                t=T0 + i * STEP, wall=0.0, package_energy_j=package_j * i,
                cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                ollama_pids=(7,), ollama_cpu_seconds=0.5 * i,
                gpu_power_w=None, gpu_util_pct=None,
            )
            for i in range(n_samples)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        return self._package_j


def _profile(session, t_a=T0, t_b=T0 + 1.0, **kwargs):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = session
    kwargs.setdefault("ollama_pids", [7])
    return prof.profile_window(t_a, t_b, **kwargs)


def _twenty_cores(monkeypatch):
    """Fissa la capacita' a 20 core logici: il test non deve dipendere dall'host."""
    monkeypatch.setattr("energy.local_energy.psutil.cpu_count",
                        lambda logical=True: 20)


# ------------------------------------------------------------------ a
def test_a_quota_sul_tempo_busy_non_sulla_capacita(monkeypatch):
    """6 s worker, 8 s busy, 20 core, 1 s: share 0,75 (busy-time), non 0,30 (capacita')."""
    _twenty_cores(monkeypatch)
    res = _profile(_FakeSession(package_j=100.0, idle_w=10.0),
                   direct_cpu_delta=6.0, direct_busy_delta=8.0)

    assert res.cpu_busy_capacity_cores == 20
    assert res.cpu_share_window_s == pytest.approx(1.0)
    assert res.d_ollama_cpu_s == pytest.approx(6.0)
    assert res.d_busy_s == pytest.approx(8.0)
    assert res.cpu_time_share == pytest.approx(0.75)
    assert res.cpu_time_share != pytest.approx(6.0 / (20 * 1.0)), (
        "lo share e' sul tempo BUSY: una quota sulla capacita' toglierebbe "
        "l'idle una seconda volta")
    assert res.share_anomaly == ""
    # E_attiva = 100 - 10*1 = 90 J; E_worker = 90 * 0,75 = 67,5 J
    assert res.active_energy_j == pytest.approx(90.0)
    assert res.ollama_active_energy_j == pytest.approx(67.5)


# ------------------------------------------------------------------ b
def test_b_energia_attiva_negativa_conservata_e_non_valida():
    """5 J di package contro 10 J di baseline: il grezzo e' -5 J, il troncato 0, validita' falsa."""
    res = _profile(_FakeSession(package_j=5.0, idle_w=10.0),
                   direct_cpu_delta=1.0, direct_busy_delta=2.0)

    assert res.package_energy_raw_j == pytest.approx(5.0)
    assert res.baseline_energy_j == pytest.approx(10.0)
    assert res.active_energy_raw_j == pytest.approx(-5.0)
    assert res.active_energy_j == 0.0, "il campo storico resta troncato"
    assert res.active_valid is False
    assert res.ollama_active_energy_j == 0.0
    assert any("E_attiva grezza -5.000 J < 0" in n for n in res.notes)


# ------------------------------------------------------------------ c
def test_c_numeratore_oltre_il_denominatore_si_dichiara(monkeypatch):
    """9 s worker su 8 s busy: grezzo 1,125, anomalia dichiarata, share limitato a 1."""
    _twenty_cores(monkeypatch)
    res = _profile(_FakeSession(), direct_cpu_delta=9.0, direct_busy_delta=8.0)

    assert res.cpu_time_share_raw == pytest.approx(1.125)
    assert res.cpu_time_share == 1.0
    assert res.share_anomaly == "d_ollama>d_busy"
    assert any("anomalia dello share (d_ollama>d_busy)" in n
               for n in res.notes)


def test_c_denominatore_nullo_o_oltre_la_capacita_si_dichiara(monkeypatch):
    """d_busy=0 non divide per zero (share 0, anomalia); d_busy oltre i core e' anomalia."""
    _twenty_cores(monkeypatch)

    zero = _profile(_FakeSession(), direct_cpu_delta=0.5, direct_busy_delta=0.0)
    assert zero.cpu_time_share_raw is None
    assert zero.cpu_time_share == 0.0
    assert zero.share_anomaly == "d_busy=0"

    # 1 s x 20 core = 20 s di capacita'; 21 s di busy sono fisicamente impossibili.
    over = _profile(_FakeSession(), direct_cpu_delta=1.0, direct_busy_delta=21.0)
    assert over.cpu_time_share_raw == pytest.approx(1.0 / 21.0)
    assert over.share_anomaly == "d_busy>capacita'"


# ------------------------------------------------------------------ d
def test_d_nato_dentro_la_finestra_conta_dal_suo_inizio():
    """Un worker visto solo a t_end ha tutto il suo cpu_times dentro la finestra (da 0)."""
    a = WorkerProc(pid=100, create_time=1000.0)
    b = WorkerProc(pid=200, create_time=1005.0)   # nato a meta' finestra

    delta = worker_cpu_delta({a: 1.0}, {a: 2.5, b: 0.75})

    assert delta.d_ollama == pytest.approx(2.25)   # (2,5-1,0) + 0,75
    assert delta.born == (b,)
    assert delta.lost == ()
    assert delta.worker_exit_in_window is False


def test_d_processo_perso_invalida_la_finestra():
    """Un worker presente a t_start e non piu' leggibile a t_end alza il flag."""
    a = WorkerProc(pid=100, create_time=1000.0)
    b = WorkerProc(pid=200, create_time=1005.0)

    delta = worker_cpu_delta({a: 1.0, b: 0.25}, {a: 2.0})

    assert delta.d_ollama == pytest.approx(1.0)
    assert delta.lost == (b,)
    assert delta.worker_exit_in_window is True

    res = _profile(_FakeSession(), direct_cpu_delta=1.0,
                   direct_busy_delta=2.0, worker_exit_in_window=True)
    assert res.worker_exit_in_window is True
    assert any("worker_exit_in_window=True" in n for n in res.notes)


# ------------------------------------------------------------------ e
def test_e_pid_riusato_non_e_lo_stesso_processo():
    """Stesso PID, create_time diverso: il vecchio risulta perso, il nuovo conta da zero."""
    old = WorkerProc(pid=100, create_time=1000.0)
    new = WorkerProc(pid=100, create_time=2000.0)   # PID riciclato

    delta = worker_cpu_delta({old: 50.0}, {new: 3.0})

    assert delta.d_ollama == pytest.approx(3.0), (
        "sommare per PID darebbe 3,0-50,0 = -47,0, poi troncato a 0")
    assert delta.lost == (old,)
    assert delta.born == (new,)
    assert delta.reused_pids == (100,)
    assert delta.worker_exit_in_window is True


def test_e_la_lettura_ricontrolla_create_time():
    """Se il PID e' stato riusato fra istantanea e lettura, il valore non entra nel dizionario."""

    class _Proc:
        def __init__(self, created):
            self._created = created

        def create_time(self):
            return self._created

        def cpu_times(self):
            return SimpleNamespace(user=1.0, system=0.5)

    ident = WorkerProc(pid=10, create_time=1000.0)
    same = read_worker_cpu_times([ident], process_factory=lambda pid: _Proc(1000.0))
    reused = read_worker_cpu_times([ident], process_factory=lambda pid: _Proc(2000.0))

    assert same == {ident: 1.5}
    assert reused == {}, "create_time diverso = altro processo, non un delta"


# ------------------------------------------------------------------ f
def test_f_albero_per_discendenza_e_estranei_esclusi():
    """llama-server entra perche' figlio; un python estraneo resta fuori; il runner orfano si segnala."""
    table = [
        ProcInfo(pid=1, ppid=0, name="ollama.exe", create_time=10.0),
        ProcInfo(pid=2, ppid=1, name="llama-server.exe", create_time=11.0),
        ProcInfo(pid=3, ppid=2, name="conhost.exe", create_time=12.0),
        ProcInfo(pid=4, ppid=0, name="python.exe", create_time=13.0),
        ProcInfo(pid=5, ppid=4, name="ollama_llama_server.exe", create_time=14.0),
    ]

    tree = build_worker_tree(table, OLLAMA_ROOT_NAMES, OLLAMA_RUNNER_NAMES)
    pids = [w.pid for w in tree]

    assert pids == [1, 2, 3], "radice + runner + nipote, per discendenza"
    assert 4 not in pids, "un processo estraneo non entra solo perche' esiste"
    assert 5 not in pids, "sotto python non discende da una radice"

    orbits = stray_runners(table, tree, OLLAMA_RUNNER_NAMES)
    assert [w.pid for w in orbits] == [5], (
        "un runner fuori dall'albero e' un motore che stiamo misurando senza saperlo")


# ------------------------------------------------------------------ g
def test_g_i_campi_storici_restano_invariati(monkeypatch):
    """Una finestra normale lascia active_energy_j e cpu_time_share come prima: la compatibilita' non cambia i numeri."""
    _twenty_cores(monkeypatch)
    res = _profile(_FakeSession(package_j=100.0, idle_w=10.0),
                   direct_cpu_delta=6.0, direct_busy_delta=8.0)

    assert res.active_energy_j == res.active_energy_raw_j == pytest.approx(90.0)
    assert res.cpu_time_share == pytest.approx(0.75)
    assert res.active_valid is True
    assert res.share_anomaly == ""
    assert res.worker_exit_in_window is False


# ------------------------------------------------------------------ punto 5
def test_avviso_finestra_sotto_trenta_passi():
    """Con risoluzione 15,6 ms una finestra da 0,4 s (< 0,468 s) avvisa; una da 1 s no."""
    short = _profile(_FakeSession(cpu_time_resolution_s=0.0156),
                     t_b=T0 + 0.4,
                     direct_cpu_delta=0.2, direct_busy_delta=0.3)
    assert short.cpu_time_resolution_s == pytest.approx(0.0156)
    assert any("30 x risoluzione" in n for n in short.notes)

    long = _profile(_FakeSession(cpu_time_resolution_s=0.0156),
                    direct_cpu_delta=0.6, direct_busy_delta=0.8)
    assert not any("30 x risoluzione" in n for n in long.notes)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
