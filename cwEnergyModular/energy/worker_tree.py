# -*- coding: utf-8 -*-
"""energy/worker_tree.py — identita' dei processi del motore locale.

Perche' esiste. La produzione enumerava i processi per NOME (`ollama.exe`,
`ollama_llama_server.exe`) e sommava i `cpu_times` per PID letto una volta per
richiesta. Tre casi restavano invisibili:

* un PID riusato dopo la morte di un worker veniva contato come lo stesso
  processo, e il delta poteva risultare negativo (poi troncato a zero);
* un worker nato dentro la finestra era letto solo a `t_end`, e sommato come
  se fosse stato presente da `t_start`;
* un worker morto prima di `t_end` perdeva il suo tempo CPU senza che nessuno
  lo dichiarasse.

Qui l'identita' e' la coppia ``(pid, create_time)``, l'albero si ricostruisce
a ogni richiesta (radici per nome + discendenti ricorsivi) e il confronto fra
i due bordi produce un flag.

Limite dichiarato: due sole letture ai bordi non vedono un processo che nasce
E muore dentro la finestra. Quel tempo CPU resta fuori dal numeratore e non e'
ricostruibile da questo modulo; il flag copre solo cio' che cambia fra i due
istanti osservati.

La costruzione dell'albero e il confronto sono funzioni pure (la tabella dei
processi e' un input): solo ``read_process_table`` e
``read_worker_cpu_times`` toccano psutil, cosi' i test girano senza hardware.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import psutil


@dataclass(frozen=True)
class ProcInfo:
    """Riga della tabella dei processi: il padre serve a costruire l'albero."""

    pid: int
    ppid: int
    name: str
    create_time: float


@dataclass(frozen=True)
class WorkerProc:
    """Identita' di un processo del motore: il PID da solo non basta."""

    pid: int
    create_time: float
    name: str = ""


@dataclass(frozen=True)
class WorkerDelta:
    """Esito del confronto fra i due bordi della finestra."""

    d_ollama: float
    worker_exit_in_window: bool
    born: Tuple[WorkerProc, ...] = ()
    lost: Tuple[WorkerProc, ...] = ()
    reused_pids: Tuple[int, ...] = ()


def _norm(name: str) -> str:
    """Nome confrontabile: minuscolo e senza l'estensione .exe."""
    n = (name or "").strip().lower()
    return n[:-4] if n.endswith(".exe") else n


def build_worker_tree(
    procs: Iterable[ProcInfo],
    root_names: Sequence[str],
    runner_names: Sequence[str] = (),
) -> List[WorkerProc]:
    """Radici per nome + TUTTI i discendenti ricorsivi, qualunque sia il nome.

    ``runner_names`` non decide l'appartenenza: un runner entra nell'albero
    perche' e' figlio (diretto o no) di una radice, non perche' si chiama
    ``llama-server``. Il parametro resta per simmetria con
    :func:`stray_runners`, che usa quei nomi per segnalare un runner FUORI
    dall'albero.
    """
    rows = list(procs)
    roots_norm = {_norm(n) for n in root_names}
    children: Dict[int, List[ProcInfo]] = {}
    roots: List[ProcInfo] = []
    for p in rows:
        children.setdefault(p.ppid, []).append(p)
        if _norm(p.name) in roots_norm:
            roots.append(p)
    tree: Dict[int, WorkerProc] = {}
    stack = list(roots)
    while stack:
        p = stack.pop()
        if p.pid in tree:
            continue
        tree[p.pid] = WorkerProc(p.pid, p.create_time, p.name)
        stack.extend(children.get(p.pid, ()))
    return sorted(tree.values(), key=lambda w: w.pid)


def stray_runners(
    procs: Iterable[ProcInfo],
    tree: Iterable[WorkerProc],
    runner_names: Sequence[str],
) -> List[WorkerProc]:
    """Runner del modello che esistono ma non discendono da una radice.

    Un ``llama-server`` fuori dall'albero e' un motore che stiamo misurando
    senza saperlo: la riga non lo attribuisce, e il run deve dirlo.
    """
    runner_norm = {_norm(n) for n in runner_names}
    in_tree = {w.pid for w in tree}
    return [
        WorkerProc(p.pid, p.create_time, p.name)
        for p in procs
        if _norm(p.name) in runner_norm and p.pid not in in_tree
    ]


def read_process_table(process_iter: Optional[object] = None) -> List[ProcInfo]:
    """Istantanea (pid, ppid, nome, create_time) di tutti i processi.

    Con ``process_iter`` iniettabile i test costruiscono la tabella a mano.
    Un processo che sparisce durante l'enumerazione viene saltato: l'albero
    e' un'istantanea, non una garanzia di completezza.
    """
    iterator = process_iter or psutil.process_iter
    out: List[ProcInfo] = []
    try:
        for p in iterator(["pid", "ppid", "name", "create_time"]):
            info = getattr(p, "info", None) or {}
            try:
                out.append(ProcInfo(
                    pid=int(info["pid"]),
                    ppid=int(info.get("ppid") or 0),
                    name=str(info.get("name") or ""),
                    create_time=float(info.get("create_time") or 0.0),
                ))
            except (KeyError, TypeError, ValueError):
                continue
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return out
    return out


def read_worker_cpu_times(
    procs: Iterable[WorkerProc],
    process_factory: Optional[object] = None,
) -> Dict[WorkerProc, float]:
    """cpu_times (user+system) per identita', non per PID.

    ``create_time`` e' ricontrollato alla lettura: se non coincide con quello
    dell'identita', il PID e' stato riusato e il valore appartiene a un altro
    processo. In quel caso la voce NON entra nel dizionario e il processo
    risulta perso al confronto fra i bordi.
    """
    factory = process_factory or psutil.Process
    out: Dict[WorkerProc, float] = {}
    for wp in procs:
        try:
            pr = factory(wp.pid)
            create_time = float(pr.create_time())
            # Tolleranza solo per il rumore di rappresentazione: qualunque
            # riuso reale di PID ha un create_time distante molto piu' di cosi'.
            if wp.create_time and abs(create_time - wp.create_time) > 0.05:
                continue
            t = pr.cpu_times()
            out[wp] = float(t.user + t.system)
        except (psutil.NoSuchProcess, psutil.ZombieProcess,
                psutil.AccessDenied, ValueError, OSError):
            continue
    return out


def worker_cpu_delta(
    start: Dict[WorkerProc, float],
    end: Dict[WorkerProc, float],
) -> WorkerDelta:
    """Delta CPU dell'albero fra i due bordi, con le perdite dichiarate.

    * processo presente a entrambi i bordi: ``end - start``;
    * processo presente solo a ``t_end`` (nato dentro la finestra): il suo
      cpu_times e' gia' tutto dentro la finestra, quindi conta da zero;
    * processo presente solo a ``t_start`` (morto o illeggibile): il suo tempo
      resta fuori dal delta e ``worker_exit_in_window`` diventa True. La
      finestra non e' integra: chi la usa deve escluderla o dichiararlo.
    """
    delta = 0.0
    born: List[WorkerProc] = []
    for wp, end_s in end.items():
        start_s = start.get(wp)
        if start_s is None:
            born.append(wp)
            delta += max(float(end_s), 0.0)
        else:
            delta += max(float(end_s) - float(start_s), 0.0)
    lost = [wp for wp in start if wp not in end]
    reused = tuple(sorted(
        {wp.pid for wp in lost} & {wp.pid for wp in born}
    ))
    return WorkerDelta(
        d_ollama=delta,
        worker_exit_in_window=bool(lost),
        born=tuple(sorted(born, key=lambda w: w.pid)),
        lost=tuple(sorted(lost, key=lambda w: w.pid)),
        reused_pids=reused,
    )
