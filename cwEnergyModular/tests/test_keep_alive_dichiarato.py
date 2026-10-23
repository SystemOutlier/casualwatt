# -*- coding: utf-8 -*-
"""D1 -- lo stato del motore locale e' un parametro dichiarato, non un incidente.

Il framework non ha mai inviato `keep_alive` a Ollama: decideva il default del
servitore se i pesi restassero caricati fra una richiesta e la successiva.
Quello stato non e' neutro -- e' la causa piu' plausibile dei residui di
durata fuori da prefill e decoding osservati nel CSV di produzione (due righe
su nove a 6,0-6,6 s contro 0,03-1,87 s delle altre) e, come mostra l'
esperimento A-B-A, la baseline e' il principale predittore del J/token.

Questi test congelano le due proprieta' che contano, nell'ordine:

  1. senza configurazione il payload RESTA quello storico, perche' i run gia'
     pubblicati devono restare riproducibili (regola "attuale finche' provato");
  2. con configurazione il valore arriva al motore, e cio' che e' arrivato
     finisce nella risposta riga per riga e nel verbale di run, perche' due run
     con keep_alive diverso non misurano la stessa cosa.

Esecuzione:  python -m pytest tests/test_keep_alive_dichiarato.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_unified as bu                                    # noqa: E402
import config                                                      # noqa: E402
from casualwatt_csv_export import CSV_COLUMNS, RUN_METADATA_COLUMNS  # noqa: E402

STORICO = {"model": "m", "prompt": "p", "stream": False,
           "options": {"temperature": 0.2, "num_predict": 160}}


class _Resp:
    """Risposta Ollama minima: i campi che il client legge davvero."""

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": "testo", "prompt_eval_count": 10, "eval_count": 5,
                "prompt_eval_duration": 20_000_000, "eval_duration": 500_000_000,
                "created_at": "2026-10-23T00:00:00Z"}


class _Post:
    """Sostituisce requests.post e registra il payload effettivamente spedito."""

    def __init__(self):
        self.sent = None

    def __call__(self, url, json=None, timeout=None):
        self.sent = json
        return _Resp(json)


def test_senza_configurazione_il_payload_e_quello_storico(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_KEEP_ALIVE", "", raising=False)
    assert bu._ollama_payload("m", "p", 0.2, 160) == STORICO


def test_con_configurazione_la_chiave_e_nel_payload(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_KEEP_ALIVE", "5m", raising=False)
    payload = bu._ollama_payload("m", "p", 0.2, 160)
    assert payload["keep_alive"] == "5m"
    assert {k: v for k, v in payload.items() if k != "keep_alive"} == STORICO


def test_default_non_inviato_dichiarato_in_risposta(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_KEEP_ALIVE", "", raising=False)
    post = _Post()
    monkeypatch.setattr(bu.requests, "post", post)
    resp, _ = bu._ollama_infer_only("m", "p", 0.2, 30.0, num_predict=160)
    assert "keep_alive" not in post.sent
    assert resp["keep_alive_sent"] == "non inviato (default Ollama)"


def test_valore_inviato_compare_nella_risposta(monkeypatch):
    monkeypatch.setattr(config, "OLLAMA_KEEP_ALIVE", "0", raising=False)
    post = _Post()
    monkeypatch.setattr(bu.requests, "post", post)
    resp, _ = bu._ollama_infer_only("m", "p", 0.2, 30.0, num_predict=160)
    assert post.sent["keep_alive"] == "0"
    assert resp["keep_alive_sent"] == "0"


def test_query_ollama_usa_lo_stesso_payload(monkeypatch):
    """Le due chiamate Ollama non possono divergere su questo parametro."""
    monkeypatch.setattr(config, "OLLAMA_KEEP_ALIVE", "30s", raising=False)
    post = _Post()
    monkeypatch.setattr(bu.requests, "post", post)
    resp, _ = bu.query_ollama("m", "p", 0.2, 30.0, num_predict=160)
    assert post.sent["keep_alive"] == "30s"
    assert resp["keep_alive_sent"] == "30s"


def test_schema_esporta_cio_che_e_stato_inviato():
    assert "keep_alive_sent" in CSV_COLUMNS
    assert len(CSV_COLUMNS) == len(set(CSV_COLUMNS)), "colonne duplicate"
    assert "ollama_keep_alive" in RUN_METADATA_COLUMNS
    # accodata: i file di run metadata gia' scritti non hanno migrazione
    assert RUN_METADATA_COLUMNS[-1] == "ollama_keep_alive"
