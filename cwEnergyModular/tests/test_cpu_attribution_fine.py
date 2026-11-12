# -*- coding: utf-8 -*-
"""
tests/test_cpu_attribution_fine.py — Attribuzione fine-grained CPU per thread,
con I/O e memoria come diagnostica (senza attribuzione energetica).

Perche' esiste. La Priorita' 6 chiede di scendere sotto il livello di processo
dell'attribuzione esistente (`worker_tree.py`, `local_energy.py` con
`E_worker = E_attiva * d_ollama/d_busy`). L'unica grandezza con una relazione
fisica dichiarabile col consumo del package e' il tempo CPU: ogni thread del
motore consuma quote di tempo CPU, e quelle quote sono un proxy dell'energia
attiva. I/O e memoria invece descrivono occupazione/attivita' indiretta: non
hanno una relazione fisica diretta e dichiarabile tra byte/RSS e joule, quindi
vanno trattati come diagnostica, non come quote di attribuzione.

Il modulo e' di sola analisi: non tocca il percorso di misura, non aggiunge
colonne CSV, non modifica `benchmark_v4.py`, `local_energy.py` o
`worker_tree.py`.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.cpu_attribution_fine import (  # noqa: E402
    IODiagnostics,
    MemoryDiagnostics,
    ThreadAttribution,
    attribute_threads,
    io_diagnostics,
    memory_diagnostics,
)


class _Thread:
    """Simula un thread psutil con id e cpu_times."""

    def __init__(self, tid, user, system):
        self.id = tid
        self.cpu_times = SimpleNamespace(user=user, system=system)


class _Process:
    """Simula psutil.Process con threads(), io_counters() e memory_info()."""

    def __init__(self, threads=None, io=None, memory=None, raise_threads=False,
                 raise_io=False, raise_memory=False):
        self._threads = threads or []
        self._io = io
        self._memory = memory
        self._raise_threads = raise_threads
        self._raise_io = raise_io
        self._raise_memory = raise_memory

    def threads(self):
        if self._raise_threads:
            raise PermissionError("access denied")
        return list(self._threads)

    def io_counters(self):
        if self._raise_io:
            raise OSError("io counters unavailable")
        return self._io

    def memory_info(self):
        if self._raise_memory:
            raise OSError("memory info unavailable")
        return self._memory


# ------------------------------------------------------------------ attributione thread


def test_attribuzione_thread_corretta():
    """E_attiva = 90 J, due thread con quote 0,6 s e 0,4 s -> 54 J e 36 J."""
    threads = [
        _Thread(1, 0.6, 0.0),
        _Thread(2, 0.4, 0.0),
    ]
    proc = _Process(threads=threads)

    attrs = attribute_threads(proc, active_energy_j=90.0, d_busy=1.0)

    assert len(attrs) == 2
    t1, t2 = attrs[0], attrs[1]
    assert t1.method == "thread-cpu-time-share"
    assert t1.valid is True
    assert t1.reason == ""
    assert t1.share == pytest.approx(0.6)
    assert t1.attributed_energy_j == pytest.approx(54.0)
    assert t2.share == pytest.approx(0.4)
    assert t2.attributed_energy_j == pytest.approx(36.0)
    # energia totale distribuita: 54 + 36 = 90
    assert t1.attributed_energy_j + t2.attributed_energy_j == pytest.approx(90.0)


def test_somma_quote_thread_uguale_a_uno():
    """Le share di tutti i thread sommano a 1,0 e le energie a E_attiva."""
    threads = [_Thread(i, 1.0 * (i + 1), 0.0) for i in range(4)]
    proc = _Process(threads=threads)

    attrs = attribute_threads(proc, active_energy_j=100.0, d_busy=1.0)

    assert len(attrs) == 4
    total_share = sum(a.share for a in attrs)
    total_energy = sum(a.attributed_energy_j for a in attrs)
    assert total_share == pytest.approx(1.0)
    assert total_energy == pytest.approx(100.0)
    assert all(a.valid is True for a in attrs)
    assert all(a.reason == "" for a in attrs)


def test_denominatore_nullo_invalido():
    """d_busy <= 0 -> ogni thread invalido, energia attribuita 0."""
    threads = [_Thread(1, 0.5, 0.0)]
    proc = _Process(threads=threads)

    attrs = attribute_threads(proc, active_energy_j=90.0, d_busy=0.0)

    assert len(attrs) == 1
    assert attrs[0].valid is False
    assert attrs[0].attributed_energy_j == 0.0
    assert "d_busy" in attrs[0].reason


def test_energia_attiva_negativa_invalida():
    """E_attiva <= 0 -> ogni thread invalido, niente attribuzione."""
    threads = [_Thread(1, 0.5, 0.0)]
    proc = _Process(threads=threads)

    attrs = attribute_threads(proc, active_energy_j=-5.0, d_busy=1.0)

    assert len(attrs) == 1
    assert attrs[0].valid is False
    assert attrs[0].attributed_energy_j == 0.0
    assert "attiva" in attrs[0].reason


def test_dati_psutil_mancanti_invalido():
    """threads() solleva eccezione -> un solo elemento invalido con ragione."""
    proc = _Process(raise_threads=True)

    attrs = attribute_threads(proc, active_energy_j=90.0, d_busy=1.0)

    assert len(attrs) == 1
    assert attrs[0].valid is False
    assert attrs[0].attributed_energy_j == 0.0
    assert "thread" in attrs[0].reason.lower()


def test_niente_thread_invalido():
    """Lista vuota di thread -> un elemento invalido, ragione dichiarata."""
    proc = _Process(threads=[])

    attrs = attribute_threads(proc, active_energy_j=90.0, d_busy=1.0)

    assert len(attrs) == 1
    assert attrs[0].valid is False
    assert attrs[0].attributed_energy_j == 0.0
    assert "thread" in attrs[0].reason.lower()


# ------------------------------------------------------------------ diagnostica I/O


def test_io_diagnostics_valida():
    """io_counters leggibile -> diagnostica valida con i campi grezzi."""
    io = SimpleNamespace(read_bytes=1024, write_bytes=2048,
                         read_count=10, write_count=5)
    proc = _Process(io=io)

    diag = io_diagnostics(proc)

    assert diag.method == "io-counters"
    assert diag.valid is True
    assert diag.read_bytes == 1024
    assert diag.write_bytes == 2048
    assert diag.read_count == 10
    assert diag.write_count == 5
    assert diag.reason == ""


def test_io_non_leggibile_non_invalizza_thread():
    """I/O illeggibile -> diagnostica invalida, ma l'attribuzione thread resta valida."""
    threads = [_Thread(1, 0.5, 0.0)]

    class _NoIO:
        def threads(self):
            return threads

    proc = _NoIO()

    attr = attribute_threads(proc, active_energy_j=90.0, d_busy=1.0)
    diag = io_diagnostics(proc)

    assert attr[0].valid is True
    assert diag.valid is False
    assert diag.read_bytes is None
    assert diag.write_bytes is None


# ------------------------------------------------------------------ diagnostica memoria


def test_memory_diagnostics_valida():
    """memory_info leggibile -> diagnostica valida con rss e uss."""
    mem = SimpleNamespace(rss=100_000_000, uss=60_000_000,
                          shared=10_000_000)
    proc = _Process(memory=mem)

    diag = memory_diagnostics(proc)

    assert diag.method == "memory-info"
    assert diag.valid is True
    assert diag.rss_bytes == 100_000_000
    assert diag.uss_bytes == 60_000_000
    assert diag.reason == ""


def test_memory_non_leggibile_non_invalizza_thread():
    """Memoria illeggibile -> diagnostica invalida, attributione thread valida."""
    threads = [_Thread(1, 0.5, 0.0)]

    class _NoMem:
        def threads(self):
            return threads

    proc = _NoMem()

    attr = attribute_threads(proc, active_energy_j=90.0, d_busy=1.0)
    diag = memory_diagnostics(proc)

    assert attr[0].valid is True
    assert diag.valid is False
    assert diag.rss_bytes is None
    assert diag.uss_bytes is None


# ------------------------------------------------------------------ determinismo


def test_determinismo_stessi_input_stesso_output():
    """Stessi input producono lo stesso risultato su chiamate ripetute."""
    threads = [_Thread(1, 0.3, 0.1), _Thread(2, 0.5, 0.1)]
    proc = _Process(threads=threads)

    a1 = attribute_threads(proc, active_energy_j=100.0, d_busy=1.0)
    a2 = attribute_threads(proc, active_energy_j=100.0, d_busy=1.0)

    assert a1 == a2


# ------------------------------------------------------------------ nessun impatto su CSV / percorso di misura


def test_niente_modifica_al_percorso_di_misura():
    """Il modulo non importa benchmark_v4, local_energy o casualwatt_csv_export."""
    import inspect
    import energy.cpu_attribution_fine as mod

    src = inspect.getsource(mod)
    import_lines = [
        line for line in src.splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    import_text = "\n".join(import_lines)
    assert "benchmark_v4" not in import_text
    assert "local_energy" not in import_text
    assert "casualwatt_csv_export" not in import_text
    assert "CSV_COLUMNS" not in import_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
