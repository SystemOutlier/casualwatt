# -*- coding: utf-8 -*-
"""Controllo pre-campagna: la forma di ``keep_alive`` che il motore accetta.

Non misura energia e non scrive CSV. Chiede al motore reale cio' che il
percorso di produzione spedisce oggi (``payload_v4`` -> ``infer_v4`` e
``infer_v4_stream``) e verifica le tre cose che un aggiornamento di Ollama
puo' rompere in silenzio, senza toccare una riga di ``benchmark_v4.py``:

1. la forma **numerica** di ``keep_alive`` e' accettata: Ollama 0.33.1
   risponde ``400`` con ``time: missing unit in duration "-1"`` alla forma
   stringa (misurato il 05-11-2026 su ``127.0.0.1:11434``);
2. ``keep_alive_sent`` riporta **il numero**, non l'etichetta "non inviato":
   il test e' ``is None``, perche' con ``keep_alive=0`` la verita' del valore
   e' l'unico modo di sapere che la richiesta ha scaricato i pesi;
3. il ramo in streaming risponde con la finestra chiusa.

Uso (dalla cartella ``cwEnergyModular/``; il motore deve gia' essere in
ascolto e il modello gia' scaricato -- questo script non scarica nulla)::

    python tools/smoke_keep_alive.py
    python tools/smoke_keep_alive.py --model qwen2.5:0.5b --keep-alive 0
    python tools/smoke_keep_alive.py --host http://127.0.0.1:11435

Esce ``0`` se tutte e tre passano, ``1`` se una verifica fallisce, ``2`` se il
motore non risponde o il modello non c'e': un controllo che non puo' girare
non e' un controllo superato.

Attenzione a ``--keep-alive 0``: scarica i pesi dalla memoria del motore al
termine della richiesta, quindi il run successivo riparte da un caricamento.
``-1`` (il default, come in produzione) li lascia in memoria.
"""
import argparse
import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RADICE not in sys.path:
    sys.path.insert(0, RADICE)

import benchmark_v4 as v4  # noqa: E402

PROMPT = "Rispondi con una sola parola: ok"


def get_json(url, timeout):
    """GET JSON puro, senza passare dal codice di produzione."""
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def verifica(esiti, nome, condizione, dettaglio):
    print("[{}] {}\n        {}".format("OK " if condizione else "NO ", nome, dettaglio))
    esiti.append(bool(condizione))
    return condizione


def forma_inviata(payload):
    """La stringa che il motore legge: il tipo conta piu' del valore."""
    corpo = json.dumps(payload)
    grezzo = payload.get("keep_alive")
    numero = isinstance(grezzo, int) and not isinstance(grezzo, bool)
    return corpo, numero, grezzo


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--model", default="qwen2.5:0.5b",
                   help="modello gia' presente nel motore (default: %(default)s)")
    p.add_argument("--host", default=None,
                   help="base url del motore; default: quello di config.OLLAMA_API_URL")
    p.add_argument("--keep-alive", type=int, default=v4.KEEP_ALIVE,
                   help="secondi di keep_alive da spedire (default: %(default)s, "
                        "-1 = non scadere mai, 0 = scarica i pesi)")
    p.add_argument("--num-predict", type=int, default=16)
    p.add_argument("--deadline", type=float, default=120.0,
                   help="wall-clock massimo per ciascuna delle due chiamate")
    a = p.parse_args()

    host = (a.host or v4.config.OLLAMA_API_URL).rstrip("/")
    if a.host:
        # Il codice di produzione legge l'endpoint al momento della chiamata,
        # quindi questo basta a portare payload e POST sullo stesso server
        # richiesto, senza modificare config.py ne' benchmark_v4.py.
        v4.config.OLLAMA_API_URL = host
        v4.config.OLLAMA_GENERATE_ENDPOINT = f"{host}/api/generate"

    print("motore   :", host)
    print("modello  :", a.model)
    print("KEEP_ALIVE di modulo = %r (%s) | valore di questa prova = %r"
          % (v4.KEEP_ALIVE, type(v4.KEEP_ALIVE).__name__, a.keep_alive))

    # --- 0) il motore risponde? -------------------------------------------------
    try:
        versione = get_json(f"{host}/api/version", 10.0).get("version", "?")
        print("versione :", versione, "(e' il metadato `ollama_version` del verbale)")
    except (URLError, OSError, ValueError) as e:
        print("\nMOTORE NON RAGGIUNGIBUTO su %s/api/version: %s: %s"
              % (host, type(e).__name__, e))
        print("Il controllo non e' stato superato: e' proprio mancato.")
        return 2

    esiti = []

    # --- 1) la forma spedita ----------------------------------------------------
    payload = v4.payload_v4(a.model, PROMPT, v4.config.DEFAULT_TEMPERATURE,
                            a.num_predict, keep_alive=a.keep_alive)
    corpo, numero, grezzo = forma_inviata(payload)
    verifica(esiti, "forma numerica nel JSON",
             numero and '"keep_alive": "' not in corpo,
             "keep_alive = %r (%s) -- corpo: %s"
             % (grezzo, type(grezzo).__name__,
                corpo if len(corpo) < 400 else corpo[:400] + " [...]"))

    # --- 2) infer_v4, stream:false ---------------------------------------------
    print("\n--- 2) infer_v4 (stream:false) ---")
    t0 = time.monotonic()
    try:
        piatto = v4.infer_v4(a.model, PROMPT, v4.config.DEFAULT_TEMPERATURE,
                             a.deadline, num_predict=a.num_predict,
                             keep_alive=a.keep_alive)
    except Exception as e:
        messaggio = "%s: %s" % (type(e).__name__, e)
        verifica(esiti, "il motore accetta la chiamata", False, messaggio)
        print("\nLa 400 e' la firma di una forma non accettata; sul corpo sopra "
              "guarda com'e' stampato keep_alive prima di correggere il codice.")
        return 1
    print("wall = %.3f s" % (time.monotonic() - t0))
    for chiave in ("text", "prompt_tokens", "completion_tokens", "tokens_valid",
                   "done_reason", "duration_s", "keep_alive_sent"):
        print("  %-18s %r" % (chiave, piatto.get(chiave)))
    verifica(esiti, "keep_alive_sent riporta il numero inviato",
             piatto.get("keep_alive_sent") == a.keep_alive,
             "keep_alive_sent = %r, atteso %r"
             % (piatto.get("keep_alive_sent"), a.keep_alive))
    verifica(esiti, "il motore ha chiuso la richiesta",
             piatto.get("done_reason") in ("stop", "length"),
             "done_reason = %r" % piatto.get("done_reason", ""))

    # --- 3) infer_v4_stream, stream:true ---------------------------------------
    print("\n--- 3) infer_v4_stream (stream:true) ---")
    t0 = time.monotonic()
    try:
        stream = v4.infer_v4_stream(a.model, PROMPT, v4.config.DEFAULT_TEMPERATURE,
                                    a.deadline, num_predict=a.num_predict,
                                    keep_alive=a.keep_alive)
    except Exception as e:
        messaggio = "%s: %s" % (type(e).__name__, e)
        verifica(esiti, "il ramo streaming risponde", False, messaggio)
        return 1
    print("wall = %.3f s" % (time.monotonic() - t0))
    for chiave in ("text", "tokens_valid", "done_reason", "keep_alive_sent",
                   "stream_incomplete", "stream_incomplete_reason",
                   "ttft_available", "ttft_s", "prefill_duration_s",
                   "decoding_duration_s", "deadline_s"):
        print("  %-26s %r" % (chiave, stream.get(chiave)))
    verifica(esiti, "il ramo streaming risponde e dichiara lo stesso numero",
             stream.get("keep_alive_sent") == a.keep_alive
             and not stream.get("stream_incomplete"),
             "keep_alive_sent = %r, stream_incomplete = %r (%r)"
             % (stream.get("keep_alive_sent"), stream.get("stream_incomplete"),
                stream.get("stream_incomplete_reason", "")))

    # --- 4) cosa resta in memoria (informativo, non un criterio) ---------------
    print("\n--- 4) /api/ps (informativo: un altro processo puo' tenere lo "
          "stesso modello in carica) ---")
    try:
        for m in get_json(f"{host}/api/ps", 10.0).get("models", []):
            print("  %-24s exp=%r ctx=%s"
                  % (m.get("name", "?"), m.get("expires"),
                     m.get("context_length", "?")))
    except (URLError, OSError, ValueError) as e:
        print("  /api/ps non risponde: %s: %s" % (type(e).__name__, e))

    if all(esiti):
        print("\nSMOKE OK: %d/%d verifiche passate (Ollama %s, modello %s, "
              "keep_alive=%r)" % (len(esiti), len(esiti), versione, a.model,
                                  a.keep_alive))
        return 0
    print("\nSMOKE FALLITO: %d/%d verifiche passate (Ollama %s). "
          "Non lanciare la campagna su questo stato."
          % (sum(esiti), len(esiti), versione))
    return 1


if __name__ == "__main__":
    sys.exit(main())
