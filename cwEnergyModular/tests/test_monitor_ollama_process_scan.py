# -*- coding: utf-8 -*-
"""Punto #67 -- la scansione dei processi e' una condizione dichiarata.

La condizione C dell'esperimento A-B-C deve essere *harness senza
enumerazione*: se `--process-scan off` lasciasse una `process_iter` nel
percorso di campionamento, B - C non misurerebbe piu' la scansione. Questi
test congelano:

  1. il parsing del flag (default `full`, valore `off` ammesso, altro no);
  2. l'assenza della chiamata a `collect` nel ramo off, che e' la proprieta'
     sperimentale, non un dettaglio implementativo;
  3. la forma dei campi di riga nei due modi, cosi' il CSV resta leggibile
     anche quando la scansione e' spenta (conteggi a zero, non chiavi mancanti).

Esecuzione:  python -m pytest cwEnergyModular/tests/test_monitor_ollama_process_scan.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import monitor_ollama                                              # noqa: E402


def test_parser_default_full_e_off_ammesso():
    """Il default deve restare `full`: un run senza flag non cambia schema."""
    parser = monitor_ollama.build_parser()
    assert parser.parse_args([]).process_scan == "full"
    assert parser.parse_args(["--process-scan", "off"]).process_scan == "off"


def test_parser_rifiuta_un_modo_sconosciuto():
    """Un terzo modo non esiste: argparse deve fermarsi, non indovinare."""
    parser = monitor_ollama.build_parser()
    try:
        parser.parse_args(["--process-scan", "partial"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("--process-scan partial non ha sollevato SystemExit")


def test_scan_processes_off_non_chiama_collect(monkeypatch):
    """Il ramo off non deve enumerare: collect non viene mai invocata.

    `collect` e' l'unico punto che chiama `psutil.process_iter`; se il test
    monkeypatch la sostituisce con un errore, un percorso alternativo nascosto
    fa fallire il test invece di passare inosservato.
    """
    called = []

    def _boom(*args, **kwargs):
        called.append((args, kwargs))
        raise AssertionError("collect chiamata con --process-scan off")

    monkeypatch.setattr(monitor_ollama, "collect", _boom)
    sweep = monitor_ollama.scan_processes("off", cache=None, excluded=set())
    assert called == []
    assert sweep == {"server": [], "clients": [], "read_errors": 0}


def test_scan_processes_full_delega_a_collect(monkeypatch):
    """Il ramo full deve passare cache ed esclusioni cosi' come sono."""
    sentinel = {"server": [], "clients": [], "read_errors": 0}
    seen = {}

    def _collect(cache, excluded):
        seen["cache"] = cache
        seen["excluded"] = excluded
        return sentinel

    monkeypatch.setattr(monitor_ollama, "collect", _collect)
    cache = object()
    sweep = monitor_ollama.scan_processes("full", cache, {1, 2})
    assert sweep is sentinel
    assert seen == {"cache": cache, "excluded": {1, 2}}


def test_sweep_fields_off_ha_tutte_le_chiavi_a_zero():
    """Con la scansione spenta la riga esiste e dichiara zero, non assenza."""
    fields = monitor_ollama.sweep_fields(
        {"server": [], "clients": [], "read_errors": 0}, ncpu=20
    )
    assert fields["ollama_server_count"] == 0
    assert fields["ollama_runner_count"] == 0
    assert fields["ollama_server_pids"] == ""
    assert fields["ollama_client_count"] == 0
    assert fields["proc_read_errors"] == 0
    assert fields["ollama_cpu_pct_sum_per_core"] == 0
    assert fields["ollama_cpu_pct_host_capacity"] == 0.0
    assert fields["ollama_rss_sum_mb"] == 0.0


def test_sweep_fields_full_aggrega_solo_i_server():
    """CPU e RSS si sommano sui server, i client restano conteggiati a parte."""
    server = [
        {"pid": 10, "ppid": 1, "name": "ollama.exe", "role": "server",
         "match": "allowlist", "cpu": 50.0, "rss": 2 * 1048576,
         "vms": 3 * 1048576, "cpu_unknown": False},
        {"pid": 11, "ppid": 10, "name": "ollama runner", "role": "runner",
         "match": "runner_of:10", "cpu": 30.0, "rss": 4 * 1048576,
         "vms": 5 * 1048576, "cpu_unknown": False},
    ]
    clients = [
        {"pid": 12, "ppid": 1, "name": "python.exe", "role": "client",
         "match": "allowlist", "cpu": 1.0, "rss": 1048576,
         "vms": 1048576, "cpu_unknown": False},
    ]
    fields = monitor_ollama.sweep_fields(
        {"server": server, "clients": clients, "read_errors": 2}, ncpu=20
    )
    assert fields["ollama_server_count"] == 2
    assert fields["ollama_runner_count"] == 1
    assert fields["ollama_runner_rss_mb"] == 4.0
    assert fields["ollama_client_count"] == 1
    assert fields["ollama_cpu_pct_sum_per_core"] == 80.0
    assert fields["ollama_cpu_pct_host_capacity"] == 4.0
    assert fields["ollama_rss_sum_mb"] == 6.0
    assert fields["ollama_vms_sum_mb"] == 8.0
    assert fields["proc_read_errors"] == 2
