# -*- coding: utf-8 -*-
"""cwEnergyModular/energy/cpu_attribution_fine.py — Priorita' 6.

Attribuzione fine-grained del consumo CPU a livello di thread, con I/O e
memoria come diagnostica (NON come quote di attribuzione energetica).

Perche' esiste. L'attribuzione esistente (`worker_tree.py`,
`local_energy.py`) opera a livello di processo:
E_worker = E_attiva * d_ollama / d_busy. La Priorita' 6 chiede di scendere
sotto il livello di processo. L'unica grandezza con una relazione fisica
dichiarabile col consumo del package e' il tempo CPU: ogni thread del motore
consuma quote di tempo CPU, che sono un proxy dell'energia attiva.

I/O (byte letti/scritti) e memoria (RSS/USS) descrivono occupazione e
attivita' indiretta: non esiste una relazione fisica diretta e dichiarabile tra
byte/RSS e joule del package, quindi vanno trattati come diagnostica, non come
quote di attribuzione. Attribuire loro energia sarebbe una stima non dichiarata.

Il modulo e' di **sola analisi**: non tocca il percorso di misura, non aggiunge
colonne CSV, non modifica il runner v4, `local_energy.py` o
`worker_tree.py`.

Contratto:
- `attribute_threads(proc, active_energy_j, d_busy)` -> list[ThreadAttribution]
  (un elemento per thread leggibile, oppure un singolo elemento invalido se i
  dati non sono disponibili).
- `io_diagnostics(proc)` -> IODiagnostics (campi grezzi, mai attribuzione).
- `memory_diagnostics(proc)` -> MemoryDiagnostics (campi grezzi, mai attribuzione).

Regole di validita':
- active_energy_j <= 0 -> ogni thread invalido, attributed_energy_j = 0.
- d_busy <= 0 -> ogni thread invalido, attributed_energy_j = 0.
- zero thread leggibili -> un elemento invalido, ragione dichiarata.
- threads() non leggibile -> un elemento invalido, ragione dichiarata.
- I/O / memoria non leggibili -> diagnostica invalida, NON invalizzano i thread.

share = thread_cpu_time / sum(tutti i thread_cpu_time)
attributed_energy_j = active_energy_j * share
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class ThreadAttribution:
    """Risultato dell'attribuzione fine-grained per un singolo thread."""

    method: str
    share: float
    attributed_energy_j: float
    valid: bool
    reason: str


@dataclass(frozen=True)
class IODiagnostics:
    """Diagnostica I/O di un processo: mai usata per attribuire energia."""

    method: str
    read_bytes: Optional[int]
    write_bytes: Optional[int]
    read_count: Optional[int]
    write_count: Optional[int]
    valid: bool
    reason: str


@dataclass(frozen=True)
class MemoryDiagnostics:
    """Diagnostica memoria di un processo: mai usata per attribuire energia."""

    method: str
    rss_bytes: Optional[int]
    uss_bytes: Optional[int]
    shared_bytes: Optional[int]
    memory_percent: Optional[float]
    valid: bool
    reason: str


def _thread_cpu_seconds(th) -> Optional[float]:
    """Tempo CPU (user + system) di un thread, o None se illeggibile.

    Accetta sia ``th.cpu_times`` come attributo oggetto (SimpleNamespace con
    ``user`` e ``system``) sia ``th.cpu_times()`` come metodo chiamante, per
    compatibilita' con le diverse firme di psutil e con i fake dei test.
    """
    try:
        ct = th.cpu_times
        if callable(ct):
            ct = ct()
        return float(ct.user) + float(ct.system)
    except Exception:
        return None


def attribute_threads(
    proc, active_energy_j: float, d_busy: float
) -> List[ThreadAttribution]:
    """Attribuisce l'energia attiva ai thread per quota di tempo CPU.

    Restituisce una lista con un elemento per thread leggibile. Se i dati
    psutil non sono disponibili, o active_energy_j <= 0, o d_busy <= 0,
    restituisce un singolo elemento invalido con attributed_energy_j = 0.0.

    Il denominatore e' la somma del tempo CPU di tutti i thread leggibili,
    non d_busy: l'attribuzione e' interna all'albero del motore, coerente
    con E_worker = E_attiva * d_ollama / d_busy ma operando dentro di esso.
    """
    method = "thread-cpu-time-share"

    # Guardie di validita' globali.
    if active_energy_j is None or active_energy_j <= 0.0:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="energia attiva <= 0 o non definita",
            )
        ]
    if d_busy is None or d_busy <= 0.0:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="d_busy <= 0 o non definito",
            )
        ]

    # Lettura dei thread.
    try:
        threads = proc.threads()
    except Exception:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="dati thread non leggibili (threads() ha sollevato)",
            )
        ]

    if not threads:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="nessun thread leggibile",
            )
        ]

    # Tempo CPU per thread.
    per_thread: List[tuple[object, float]] = []
    for th in threads:
        cpu_s = _thread_cpu_seconds(th)
        if cpu_s is not None:
            per_thread.append((th, cpu_s))

    if not per_thread:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="nessun thread con cpu_times leggibile",
            )
        ]

    total_cpu = sum(cpu for _, cpu in per_thread)
    if total_cpu <= 0.0:
        return [
            ThreadAttribution(
                method=method,
                share=0.0,
                attributed_energy_j=0.0,
                valid=False,
                reason="tempo CPU totale nullo",
            )
        ]

    results: List[ThreadAttribution] = []
    for th, cpu in per_thread:
        share = cpu / total_cpu
        results.append(
            ThreadAttribution(
                method=method,
                share=round(share, 6),
                attributed_energy_j=round(active_energy_j * share, 6),
                valid=True,
                reason="",
            )
        )
    return results


def io_diagnostics(proc) -> IODiagnostics:
    """Legge i contatori I/O di un processo come diagnostica, mai attribuzione."""
    method = "io-counters"
    try:
        io = proc.io_counters()
        return IODiagnostics(
            method=method,
            read_bytes=int(getattr(io, "read_bytes", 0) or 0),
            write_bytes=int(getattr(io, "write_bytes", 0) or 0),
            read_count=int(getattr(io, "read_count", 0) or 0),
            write_count=int(getattr(io, "write_count", 0) or 0),
            valid=True,
            reason="",
        )
    except Exception:
        return IODiagnostics(
            method=method,
            read_bytes=None,
            write_bytes=None,
            read_count=None,
            write_count=None,
            valid=False,
            reason="contatori I/O non leggibili",
        )


def memory_diagnostics(proc) -> MemoryDiagnostics:
    """Legge le informazioni memoria di un processo come diagnostica."""
    method = "memory-info"
    try:
        mem = proc.memory_info()
        return MemoryDiagnostics(
            method=method,
            rss_bytes=int(getattr(mem, "rss", 0) or 0),
            uss_bytes=int(getattr(mem, "uss", 0) or 0),
            shared_bytes=int(getattr(mem, "shared", 0) or 0),
            memory_percent=(
                float(getattr(mem, "percent", 0.0) or 0.0)
                if getattr(mem, "percent", None) is not None
                else None
            ),
            valid=True,
            reason="",
        )
    except Exception:
        return MemoryDiagnostics(
            method=method,
            rss_bytes=None,
            uss_bytes=None,
            shared_bytes=None,
            memory_percent=None,
            valid=False,
            reason="informazioni memoria non leggibili",
        )
