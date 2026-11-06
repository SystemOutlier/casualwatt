# -*- coding: utf-8 -*-
"""
tests/test_stream_timeout.py — P1: il deadline dello streaming e' globale.

Perche' esiste. ``infer_v4_stream`` usava ``requests`` + ``iter_lines()``:
``timeout_s`` li' era un timeout di socket PER SINGOLO chunk, quindi uno stream
che produce byte ogni frazione del limite non veniva mai interrotto e la
finestra energetica che il chiamante costruisce attorno alla funzione poteva
crescere oltre il limite dichiarato. L'antesistema non e' committato -- la
funzione di streaming nasce nel worktree sporco, non in ``HEAD`` -- quindi
questa descrizione e' l'unica traccia del percorso sostituito: nessun numero di
riga la ancora. Il percorso nuovo gira su
``aiohttp.ClientTimeout(total=...)`` e su ``asyncio.run``: il limite e' un
wall-clock dell'intera richiesta e, alla scadenza, la richiesta viene chiusa
DAVVERO prima che la funzione ritorni.

Che cosa verifica:
  1. il testo e' l'accumulo dei chunk ricevuti, senza duplicazione quando il
     chunk ``done=True`` riporta la risposta completa (regola dichiarata in
     ``infer_v4_stream``);
  2. un risultato incompleto resta incompleto: flag, ragione, testo parziale,
     e nessuna statistica inventata (token e durate del motore stanno solo nel
     chunk finale);
  3. il deadline e' effettivo nei tre stadi in cui puo' scattare: connessione
     mai conclusa, connessione aperta senza header, header ricevuti e corpo
     fermo, corpo che produce chunk all'infinito; un errore di stato HTTP
     invece si propaga e non aspetta il deadline;
  4. al ritorno non esiste nessuna operazione asincrona viva: niente thread di
     CasualWatt, nessun loop aperto, nessuna sessione ``ClientSession`` aperta,
     e la connessione lato server risulta chiusa dal client;
  5. i bordi tornati sono monotoni e ``_t1`` e' l'istante dopo la pulizia,
     perche' e' li' che ``run_block`` legge il bordo di fine ``e1``
     (``benchmark_v4.py:1785-1792``);
  6. una richiesta successiva non eredita nulla da una precedente fallita.

Che cosa NON verifica: che il numero di energia di una riga sia corretto (le
formule stanno in ``energy/local_energy.py`` e non sono toccate dalla P1); che
il blocco completo si apra e chiuda come in campagna (sequenza P1.5 coperta da
``tests/test_baseline_ordine_v4.py`` con un finto ``infer_v4_stream``). Qui il
server e' sempre un socket locale: nessun test chiede Ollama installato e
nessuno apre connessioni esterne.
"""
import asyncio
import copy
import json
import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
import config  # noqa: E402

# Tolleranza di pulizia dopo il deadline. NON e' una soglia di protocollo: e'
# il margine che ammettiamo fra la scadenza del ``total`` e il ritorno della
# funzione, cioe' chiusura risposta + sessione + cancellazione task + chiusura
# loop. Misurata su questa macchina il 05-11-2026: dodici run (tre per
# modalita' fra endless, silent, headers_only, no_accept) con deadline 0,3 s
# danno un eccesso fra 0,009 s e 0,028 s, con zero thread residui. Verifica
# ripetuta la stessa notte con dodici richieste ``endless`` a deadline 0,40 s:
# eccesso fra 0,001 s e 0,0264 s, ``stream_incomplete`` True con ragione
# ``timeout_deadline`` su tutte e dodici e nessun thread di CasualWatt
# superstite. Riverificata il 06-11-2026 con lo stesso disegno del 05-11 (tre
# run per modalita' fra endless, silent, headers_only, no_accept, deadline
# 0,3 s): eccesso fra 0,0132 s e 0,0297 s, ragione ``timeout_deadline`` o
# ``timeout_senza_header`` su tutte e dodici, zero thread residui a ogni
# chiamata. Il massimo letto e' sopra i 0,028 s del 05-11, quindi il Bound
# storico non era un tetto: 1,0 s resta ~34 volte il peggior valore fra le due
# misurazioni. 1,0 s e' dichiarato per il carico della macchina, non una misura
# pubblicata.
TOLLERANZA_PULIZIA_S = 1.0

# Prefissi dei thread che il MODULO di test crea: vanno esclusi dal conteggio
# dei worker residui perche' il vincolo P1 riguarda CasualWatt, non il server
# finto (il server usa thread daemon e non possiede nessuna richiesta).
_SERVER_THREAD_PREFIXES = ("cw-test-server",)




def _chunk_line(text, done=False, **extra):
    """Una riga NDJSON in fondo al file, come la manda /api/generate."""
    obj = {"model": "cw-test", "response": text, "done": bool(done)}
    obj.update(extra)
    return (json.dumps(obj) + "\n").encode("utf-8")


def _done_line(full_text, **extra):
    """Chunk finale: Ollama riporta qui la risposta completa e i contatori."""
    stats = {"prompt_eval_count": 10, "eval_count": 5,
             "prompt_eval_duration": 20000000,
             "eval_duration": 500000000,
             "done_reason": "stop",
             "created_at": "2026-11-05T00:00:00.000Z"}
    stats.update(extra)
    return _chunk_line(full_text, done=True, **stats)


class _FakeOllama:
    """Server HTTP/1.1 a un solo socket: comanda header, corpo e cadenza.

    Modalita': ``no_accept`` (listen senza accept, la fase HTTP non si
    conclude), ``silent`` (accept e nessun byte scritto), ``headers_only``
    (header scritti e corpo fermo), ``lines`` (le righe date a un intervallo,
    poi ``hold_after_lines`` o chiusura), ``endless`` (righe a intervallo
    fisso fino allo stop).

    Registra tre cose che i test usano come evidenza: gli istanti in cui ha
    accettato e in cui il client ha chiuso la connessione, e l'errore di
    scrittura che dimostra che dopo la chiusura dal client non puo' piu'
    arrivare nessun chunk. La richiesta HTTP viene letta SINCRONAMENTE prima di
    rispondere, con ``request_ready`` che segnala il momento in cui il payload
    e' intero: le asserzioni su "cosa e' arrivato al server" non dipendono
    quindi dallo scheduler. I thread del server sono daemon: sono il banco di
    prova, non un worker di CasualWatt, e vengono uniti allo shutdown.
    """

    def __init__(self, mode="lines", lines=(), interval_s=0.0,
                 hold_after_lines=True, pre_headers_delay_s=0.0,
                 end_text="z", status_code=200):
        self.mode = mode
        self.lines = list(lines)
        self.interval_s = interval_s
        self.hold_after_lines = hold_after_lines
        self.pre_headers_delay_s = pre_headers_delay_s
        self.end_text = end_text
        self.status_code = status_code
        self._listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listen.bind(("127.0.0.1", 0))
        # Backlog sempre attivo, anche in ``no_accept``: serve perche' il
        # kernel concluda l'handshake TCP e la richiesta resti in attesa della
        # risposta HTTP, invece di essere rifiutata.
        self._listen.listen(5)
        self.port = self._listen.getsockname()[1]
        self.url = f"http://127.0.0.1:{self.port}/api/generate"
        self.accepted = threading.Event()
        self.request_ready = threading.Event()
        self.payload = None
        self.client_closed_at = None
        self.write_error = None
        self.request_bytes = b""
        self.n_requests = 0
        self._stop = threading.Event()
        self._conn = None
        self._threads = []

    # -- ciclo del server -------------------------------------------------
    def start(self):
        t = threading.Thread(target=self._run, name="cw-test-server",
                             daemon=True)
        self._threads.append(t)
        t.start()
        return self

    def _run(self):
        if self.mode == "no_accept":
            # Il backlog del kernel conclude l'handshake TCP; nessuna risposta
            # HTTP arriva mai, perche' la connessione non viene accettata.
            self._wait_or_stop()
            return
        try:
            conn, _ = self._listen.accept()
        except OSError:
            return
        self._conn = conn
        self.accepted.set()
        self.n_requests = 1
        conn.settimeout(10.0)
        if not self._leggi_richiesta(conn):
            return
        osservatore = threading.Thread(target=self._osserva_chiusura,
                                       args=(conn,),
                                       name="cw-test-server-read", daemon=True)
        self._threads.append(osservatore)
        osservatore.start()
        if self.mode == "silent":
            self._wait_or_stop()
            return
        if self.pre_headers_delay_s:
            if self._stop.wait(self.pre_headers_delay_s):
                return
        try:
            conn.sendall(self._response_headers())
        except OSError as exc:
            self.write_error = type(exc).__name__
            return
        if self.status_code != 200:
            # Nessuna risposta da leggere: il client deve accorgersi dello
            # stato e chiudere, non mettere insieme un risultato incompleto.
            self._chiudi_connessione()
            return
        if self.mode == "headers_only":
            self._wait_or_stop()
            return
        if self.mode == "endless":
            i = 0
            while not self._stop.is_set():
                if self._stop.wait(self.interval_s):
                    break
                i += 1
                if not self._scrivi(_chunk_line(f"{self.end_text}{i}")):
                    break
            return
        # modalita' "lines"
        if self.lines:
            for line in self.lines:
                if not self._scrivi(line):
                    return
                if self.interval_s and self._stop.wait(self.interval_s):
                    return
        if self.hold_after_lines:
            self._wait_or_stop()
        else:
            # EOF: il corpo finisce senza done=True, come un server che chiude.
            self._chiudi_connessione()

    def _response_headers(self):
        motivo = b"OK" if self.status_code == 200 else b"Internal Server Error"
        return (b"HTTP/1.1 " + str(self.status_code).encode() + b" " + motivo +
                b"\r\nContent-Type: application/x-ndjson\r\n\r\n")

    def _scrivi(self, data):
        try:
            self._conn.sendall(data)
            return True
        except OSError as exc:
            self.write_error = type(exc).__name__
            return False

    def _leggi_richiesta(self, conn) -> bool:
        """Intestazione + corpo fino a ``Content-Length``, poi ``request_ready``.

        Ritorna False se il client non completa la richiesta: in quel caso il
        server non risponde e il test si accorge che ``request_ready`` non e'
        mai stato messo, invece di leggere un payload a meta'.
        """
        testa = b""
        while b"\r\n\r\n" not in testa:
            try:
                dato = conn.recv(4096)
            except OSError:
                return False
            if not dato:
                return False
            testa += dato
        pre, _, corpo = testa.partition(b"\r\n\r\n")
        lunghezza = 0
        for riga in pre.split(b"\r\n"):
            nome, _, valore = riga.partition(b":")
            if nome.strip().lower() == b"content-length":
                try:
                    lunghezza = int(valore.strip() or 0)
                except ValueError:
                    lunghezza = 0
        while len(corpo) < lunghezza:
            try:
                dato = conn.recv(4096)
            except OSError:
                break
            if not dato:
                break
            corpo += dato
        self.request_bytes = pre + b"\r\n\r\n" + corpo
        try:
            self.payload = json.loads(corpo.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.payload = {}
        self.request_ready.set()
        return True

    def _osserva_chiusura(self, conn):
        """Resta in ascolto del FIN: l'unico segnale lato server della fine.

        L'istante registrato e' quando NOI leggiamo la chiusura, quindi arriva
        DOPO la chiusura reale del client: i test lo usano come limite
        superiore, mai come ordine causale.
        """
        while True:
            try:
                dato = conn.recv(4096)
            except OSError:
                break
            if not dato:
                break
        self.client_closed_at = time.monotonic()

    def _wait_or_stop(self):
        self._stop.wait(30.0)

    # -- teardown ---------------------------------------------------------
    def _chiudi_connessione(self):
        try:
            if self._conn is not None:
                self._conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        finally:
            try:
                if self._conn is not None:
                    self._conn.close()
            except OSError:
                pass

    def shutdown(self):
        self._stop.set()
        try:
            self._listen.close()
        except OSError:
            pass
        self._chiudi_connessione()
        for t in self._threads:
            t.join(timeout=5.0)


@pytest.fixture
def fake_ollama(monkeypatch):
    """Crea i server locali e punta l'endpoint della v4 su di loro."""
    made = []

    def _make(**kwargs):
        srv = _FakeOllama(**kwargs).start()
        made.append(srv)
        monkeypatch.setattr(config, "OLLAMA_GENERATE_ENDPOINT", srv.url)
        return srv

    yield _make
    for srv in made:
        srv.shutdown()


def _threads_cwatt():
    """Thread vivi che NON sono del banco di prova."""
    return [t for t in threading.enumerate()
            if not any(t.name.startswith(p) for p in _SERVER_THREAD_PREFIXES)]


def _loop_attivo():
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


# ------------------------------------------------------------------ 1, 2, 13
def test_accumulo_tutti_i_chunk(fake_ollama):
    """P1.4: il testo e' l'accumulo dei chunk, non la riga JSON contata.

    Tre chunk "abc", "def", "ghi" e il finale con la risposta completa: il
    testo restituito deve essere "abcdefghi" una volta sola. Se il conteggio
    dei token derivasse dai chunk, o se il finale venisse accumulato sopra i
    parziali, qui il testo si allungherebbe o si duplicherebbe.
    """
    srv = fake_ollama(mode="lines", lines=[
        _chunk_line("abc"), _chunk_line("def"), _chunk_line("ghi"),
        _done_line("abcdefghi"),
    ], hold_after_lines=False)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert out["text"] == "abcdefghi"
    assert out["stream_incomplete"] is False
    assert "ghi" in out["text"] and out["text"].count("abc") == 1


def test_normale_completamento(fake_ollama):
    """P1.4: con done=True entro il deadline i valori nativi restano nativi."""
    srv = fake_ollama(mode="lines", lines=[
        _chunk_line("C"), _chunk_line("iao"), _done_line("Ciao"),
    ], hold_after_lines=False)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert out["stream_incomplete"] is False
    assert out["stream_incomplete_reason"] == ""
    assert out["text"] == "Ciao"
    assert out["prompt_tokens"] == 10
    assert out["completion_tokens"] == 5
    assert out["tokens_valid"] is True
    assert out["token_provenance"] == "native"
    assert out["done_reason"] == "stop"


def test_timeout_non_attivato_se_stream_conclude_normale(fake_ollama):
    """P1.4: una richiesta regolare prima del deadline non e' incompleta.

    Il deadline non deve diventare un flag di fallimento: qui scatta a 5 s e
    la risposta arriva in frazioni di secondo, perche' un timeout che marca
    tutto falsamente invaliderebbe ogni riga buona della campagna.
    """
    srv = fake_ollama(mode="lines", lines=[_done_line("ok")],
                      hold_after_lines=False)
    t0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)
    elapsed = time.monotonic() - t0

    assert out["stream_incomplete"] is False
    assert elapsed < 5.0
    assert out["duration_s"] < 5.0


# ------------------------------------------------------- 3, 7, 16 (parziale)
def test_stream_interrotto_prima_di_done(fake_ollama):
    """P1.4: EOF senza done=True conserva il parziale e non inventa nulla."""
    srv = fake_ollama(mode="lines",
                      lines=[_chunk_line("ab"), _chunk_line("cd")],
                      hold_after_lines=False)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert out["stream_incomplete"] is True
    assert out["text"] == "abcd"
    assert out["prompt_tokens"] == ""
    assert out["completion_tokens"] == ""
    assert out["tokens_valid"] is False
    assert out["token_provenance"] == "missing"


def test_testo_parziale_contiene_tutti_i_chunk(fake_ollama):
    """P1.4: dopo il timeout il testo ha ogni chunk ricevuto, non il primo.

    Con l'implementazione vecchia (``data = final_data or first_data``) qui
    sarebbe rimasto solo "ab": la perdita dei chunk successivi e' il difetto
    che il vincolo "conserva tutto il testo parziale" chiude.
    """
    srv = fake_ollama(mode="lines",
                      lines=[_chunk_line("ab"), _chunk_line("cd"),
                             _chunk_line("ef")],
                      interval_s=0.05, hold_after_lines=True)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 0.3)

    assert out["stream_incomplete"] is True
    assert out["text"] == "abcdef"


def test_stream_incompleto_senza_statistiche_finali(fake_ollama):
    """P1.4: senza il chunk finale le durate del motore restano assenti.

    ``prompt_eval_duration`` e ``eval_duration`` stanno SOLO nel done=True:
    ``0.0`` qui sarebbe un tempo zero pubblicato al posto di un dato mai
    arrivato, e i token nativi idem.
    """
    srv = fake_ollama(mode="lines",
                      lines=[_chunk_line("x"), _chunk_line("y")],
                      hold_after_lines=False)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert out["stream_incomplete"] is True
    assert out["prefill_duration_s"] is None
    assert out["decoding_duration_s"] is None
    assert out["prompt_tokens"] == ""
    assert out["completion_tokens"] == ""
    assert out["done_reason"] == ""


# ------------------------------------------------- 4, 5, 6, 14 (timeout veri)
def test_chunk_continui_piu_frequenti_del_timeout(fake_ollama):
    """P1.2: chunk continui NON rinnozano il limite: total e' wall-clock.

    Questo e' il caso che ``requests``+``iter_lines`` non chiudevano mai: un
    chunk ogni 20 ms aggiorna un timeout di socket, ma ``ClientTimeout(total``
    scade comunque. Si misura il ritorno entro deadline + tolleranza di
    pulizia documentata, e si verifica che non resti nessun task o worker.
    """
    srv = fake_ollama(mode="endless", interval_s=0.02)
    deadline = 0.4
    prima = {t.name for t in _threads_cwatt()}
    t0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    elapsed = time.monotonic() - t0

    assert deadline <= elapsed <= deadline + TOLLERANZA_PULIZIA_S
    assert out["stream_incomplete"] is True
    assert out["stream_incomplete_reason"] == "timeout_deadline"
    assert out["deadline_s"] == deadline
    assert out["duration_s"] <= deadline + TOLLERANZA_PULIZIA_S
    assert {t.name for t in _threads_cwatt()} == prima
    assert _loop_attivo() is None


def test_server_senza_header(fake_ollama):
    """P1.2: connessione accettata e nessun byte scritto = timeout, non blocco.

    Il client deve terminare da solo: un server muto non puo' tenere aperta
    una finestra energetica. ``t_headers_received`` assente e ``ttft_s`` vuoto
    dicono che nessun contenuto e' stato ricevuto, quindi la riga non avra'
    alcuna statistica da interpretare.
    """
    srv = fake_ollama(mode="silent")
    deadline = 0.4
    t0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    elapsed = time.monotonic() - t0

    assert srv.accepted.is_set()
    assert deadline <= elapsed <= deadline + TOLLERANZA_PULIZIA_S
    assert out["stream_incomplete"] is True
    assert out["stream_incomplete_reason"] == "timeout_senza_header"
    assert out["_t_headers_received"] is None
    assert out["ttft_s"] is None
    assert out["text"] == ""


def test_server_blocca_dopo_header(fake_ollama):
    """P1.2: header arrivati e corpo fermo = timeout con gli header letti.

    La ragione diversa da ``test_server_senza_header`` e' il punto: la
    distinzione fra "nessuna risposta" e "risposta senza contenuti" finisce
    nella riga, perche' il TTFT non e' la stessa cosa in due casi.
    """
    srv = fake_ollama(mode="headers_only")
    deadline = 0.4
    t0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    elapsed = time.monotonic() - t0

    assert deadline <= elapsed <= deadline + TOLLERANZA_PULIZIA_S
    assert out["stream_incomplete"] is True
    assert out["stream_incomplete_reason"] == "timeout_deadline"
    assert out["_t_headers_received"] is not None
    assert out["_t_last_chunk"] is None
    assert out["ttft_available"] is False


def test_timeout_durante_connessione(fake_ollama):
    """P1.2: se la fase HTTP non si conclude, il limite vale lo stesso.

    Il server resta in ``listen`` senza accettare: il kernel conclude l'handshake
    e il client scrive, ma gli header non arrivano mai. Il timeout scatta
    sull'attesa della risposta e la pulizia avviene comunque, con una sessione
    creata e chiusa e nessun thread residuo.
    """
    srv = fake_ollama(mode="no_accept")
    deadline = 0.4
    prima = {t.name for t in _threads_cwatt()}
    t0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    elapsed = time.monotonic() - t0

    assert not srv.accepted.is_set()
    assert deadline <= elapsed <= deadline + TOLLERANZA_PULIZIA_S
    assert out["stream_incomplete"] is True
    assert out["stream_incomplete_reason"] == "timeout_senza_header"
    assert {t.name for t in _threads_cwatt()} == prima
    assert _loop_attivo() is None


# ------------------------------ 8, 9, 10, 11, 15 + errore HTTP (residui)
def test_errore_http_non_diventa_risultato_incompleto(fake_ollama):
    """P1.5: un 5xx e' una richiesta fallita, non una misura parziale.

    Il vincolo sulla chiusura della finestra riguarda anche l'errore HTTP: la
    risposta arriva con stato 500 e nessun corpo. La produzione vecchia usava
    ``resp.raise_for_status()`` di ``requests`` e propagava ``HTTPError``; il
    percorso nuovo propaga ``ClientResponseError`` di ``aiohttp`` -- e' l'unico
    cambio di tipo del pacchetto P1, dichiarato qui perche' il comportamento
    che conta e' identico: nessuna riga pubblicata, nessun risultato, nessuna
    attesa del deadline, e nessuna sessione lasciata aperta.
    """
    srv = fake_ollama(mode="lines", lines=[], status_code=500)
    t0 = time.monotonic()

    with pytest.raises(v4.aiohttp.ClientResponseError):
        v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert time.monotonic() - t0 < 5.0
    assert srv.accepted.is_set()
    assert _loop_attivo() is None
    assert not any(t.name.startswith(v4._STREAM_THREAD_PREFIX)
                   for t in _threads_cwatt())


def test_nessun_worker_dopo_la_restituzione(fake_ollama):
    """P1.2: al ritorno non esiste nessun worker o task di CasualWatt.

    Si confrontano i thread vivi prima e dopo, ESCLUSI quelli del banco di
    prova (prefisso ``cw-test-server``): il vincolo riguarda i thread che il
    programma crea, non il server finto. Si verifica anche che il thread
    chiamante non abbia un loop in esecuzione, perche' un loop aperto dopo il
    ritorno significherebbe operazioni asincrone ancora vive.
    """
    srv = fake_ollama(mode="endless", interval_s=0.05)
    prima = sorted(t.name for t in _threads_cwatt())

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 0.3)
    dopo = sorted(t.name for t in _threads_cwatt())

    assert out["stream_incomplete"] is True
    assert dopo == prima
    assert not any(n.startswith(v4._STREAM_THREAD_PREFIX) for n in dopo)
    assert _loop_attivo() is None


def test_nessuna_modifica_dopo_la_restituzione(fake_ollama):
    """P1.2: il risultato restituito non e' piu' modificabile da nessuno.

    Dopo il ritorno si aspetta oltre il deadline e si riconfronta con una
    copia: se esistesse un task vivo, il timeout avrebbe potuto cambiare il
    testo o il flag dopo la consegna. L'errore di scrittura del server e'
    l'evidenza indipendente che la richiesta HTTP era gia' morta.
    """
    srv = fake_ollama(mode="endless", interval_s=0.05)
    deadline = 0.3
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    snapshot = copy.deepcopy(out)
    time.sleep(2.0 * deadline + 0.2)

    assert out == snapshot
    assert out["stream_incomplete"] is True
    assert srv.write_error is not None


def test_finestra_energetica_chiusa(fake_ollama):
    """P1.5: il bordo di fine si puo' leggere solo a stream chiuso.

    ``run_block`` legge ``e0`` prima e ``e1`` dopo la chiamata
    (``benchmark_v4.py:1785-1792``) e passa ``_t0``/``_t1`` al profilo: se la
    funzione ritornasse con lo stream vivo, ``e1`` sarebbe precoce. Qui si
    reproduce la sequenza del chiamante con i tempi a muro e si pretende che
    il server abbia visto la chiusura del client PRIMA di ``e1`` (piu' la
    tolleranza di osservazione), che i bordi siano monotoni, e che ``_t1`` sia
    l'istante della pulizia e non della ricezione.
    """
    srv = fake_ollama(mode="endless", interval_s=0.05)
    deadline = 0.3

    t_e0 = time.monotonic()
    out = v4.infer_v4_stream("cw-test", "p", 0.0, deadline)
    t_e1 = time.monotonic()

    assert out["_t_request_start"] <= out["_t_headers_received"]
    assert out["_t_headers_received"] <= out["_t_last_chunk"]
    assert out["_t_last_chunk"] <= out["_t_measurement_end"] == out["_t1"]
    # La finestra del chiamante CONTIENE la richiesta: ``e0`` e' letto prima di
    # entrare nel coroutine e ``e1`` dopo che il wrapper ha finito, perche'
    # ``run_block`` sta fuori dalla funzione (``benchmark_v4.py:1785-1792``).
    assert t_e0 <= out["_t_request_start"]
    assert out["_t_measurement_end"] <= t_e1
    assert srv.client_closed_at is not None
    assert srv.client_closed_at <= t_e1 + TOLLERANZA_PULIZIA_S
    assert out["stream_incomplete"] is True


def test_richiesta_successiva_senza_interferenze(fake_ollama):
    """P1: un timeout non avvelena la chiamata dopo.

    La seconda richiesta usa un server NUOVO con done=True: se il wrapper
    lasciasse un loop o una sessione in corso, la seconda chiamata erediterebbe
    lo stato della prima e il risultato non sarebbe piu' riproducibile.
    """
    srv1 = fake_ollama(mode="endless", interval_s=0.05)
    out1 = v4.infer_v4_stream("cw-test", "primo", 0.0, 0.3)
    assert out1["stream_incomplete"] is True

    srv2 = fake_ollama(mode="lines", lines=[_chunk_line("ki"),
                                           _done_line("kiwi")],
                       hold_after_lines=False)
    out2 = v4.infer_v4_stream("cw-test", "secondo", 0.0, 5.0)

    assert out2["stream_incomplete"] is False
    assert out2["text"] == "kiwi"
    assert out2["completion_tokens"] == 5
    assert srv2.accepted.is_set()


def test_timeout_non_contamina_richiesta_successiva(fake_ollama, monkeypatch):
    """P1.2: niente dati, sessioni o stato riutilizzati fra le chiamate.

    Le due chiamate usano prompt diversi e server diversi: si pretende che
    ogni ``ClientSession`` creata sia un oggetto distinto e gia' chiuso al
    ritorno, che il secondo server legga il proprio payload e non quello
    precedente, e che il secondo risultato non contenga nessuna parte del testo
    parziale della prima. Il conteggio delle sessioni e' l'unica prova che non
    esiste una sessione di modulo riusata fra le richieste.
    """
    created = []
    real_session = v4.aiohttp.ClientSession

    def _traccia(**kwargs):
        sess = real_session(**kwargs)
        created.append(sess)
        return sess

    monkeypatch.setattr(v4.aiohttp, "ClientSession", _traccia)

    srv1 = fake_ollama(mode="endless", interval_s=0.05)
    out1 = v4.infer_v4_stream("cw-test", "PARZIALE1", 0.0, 0.3)
    srv2 = fake_ollama(mode="lines", lines=[_done_line("PULITO2")],
                       hold_after_lines=False)
    out2 = v4.infer_v4_stream("cw-test", "PULITO2", 0.0, 5.0)

    assert out1["stream_incomplete"] is True
    assert out2["stream_incomplete"] is False
    assert "PARZIALE1" not in out2["text"]
    assert len(created) == 2
    assert created[0] is not created[1]
    assert all(sess.closed for sess in created)
    # Il payload intero e' un evento, non una speranza sullo scheduler.
    assert srv2.request_ready.wait(5.0)
    assert srv1.request_ready.wait(5.0)
    assert srv2.payload["prompt"] == "PULITO2"
    assert srv1.payload["prompt"] == "PARZIALE1"
    assert srv2.payload["stream"] is True
    assert "PARZIALE1" not in srv2.request_bytes.decode("utf-8", "replace")


# ------------------------------------------------------------------ 12
def test_ttft_e_token_nativi(fake_ollama):
    """P1.3: il TTFT parte dall'invio, non dagli header; i token sono nativi.

    Il server ritarda gli header di 0,20 s prima di scrivere qualsiasi cosa:
    se la latenza partisse dagli header, ``ttft_s`` sarebbe piu' piccolo del
    ritardo e il confine fra "tempo di risposta HTTP" e TTFT si perderebbe. Il
    vincolo chiede che ``t_request_start`` sia preso prima dell'invio, e qui
    lo si misura.
    """
    delay = 0.20
    srv = fake_ollama(mode="lines", lines=[_chunk_line("C"),
                                          _chunk_line("iao"),
                                          _done_line("Ciao")],
                      hold_after_lines=False, pre_headers_delay_s=delay)

    out = v4.infer_v4_stream("cw-test", "p", 0.0, 5.0)

    assert out["ttft_available"] is True
    assert out["ttft_s"] >= delay
    assert out["duration_s"] >= out["ttft_s"]
    assert out["_t_ttft"] is not None and out["_t_ttft"] >= out["_t_headers_received"]
    assert out["prompt_tokens"] == 10
    assert out["completion_tokens"] == 5
    assert out["prefill_duration_s"] == pytest.approx(0.02)
    assert out["decoding_duration_s"] == pytest.approx(0.5)


# ---------------------------------------------------------- extra dichiarati
def test_deadline_non_positivo_e_rifiutato(fake_ollama):
    """P1.2: ``timeout_s`` 0 o assente non e' "nessun limite".

    Con 0 il vecchio percorso avrebbe potuto girare per sempre (o con un
    comportamento dipendente da ``requests``); qui il rifiuto e' un errore
    nominato prima di aprire la connessione, cosi' nessuna finestra energetica
    viene aperta su una richiesta senza limite.
    """
    srv = fake_ollama(mode="endless", interval_s=0.05)

    for cattivo in (0, -1, None, float("inf"), float("nan"), "x"):
        with pytest.raises(v4.V4MeasurementError):
            v4.infer_v4_stream("cw-test", "p", 0.0, cattivo)

    assert not srv.accepted.is_set()


def test_wrapper_in_loop_gia_attivo(fake_ollama):
    """P1.2: il wrapper funziona anche dentro un loop in esecuzione.

    ``asyncio.run`` da un thread con un loop attivo solleva RuntimeError: il
    ramo con il pool temporaneo serve li'. Si esegue il wrapper dentro un
    loop reale e si pretendera' il risultato e l'assenza di thread residui.
    """
    srv = fake_ollama(mode="endless", interval_s=0.05)
    prima = sorted(t.name for t in _threads_cwatt())

    async def _dentro_il_loop():
        # Chiamata sincrona dentro un coroutine: e' esattamente il caso in cui
        # il wrapper deve creare il loop altrove invece di riusare questo.
        return v4._ollama_stream_with_aiohttp_deadline(
            {"model": "cw-test", "prompt": "p", "stream": True}, 0.3)

    res = asyncio.run(_dentro_il_loop())
    dopo = sorted(t.name for t in _threads_cwatt())

    assert srv.accepted.is_set()
    assert res["final_data"] is None
    assert res["stream_incomplete_reason"] == "timeout_deadline"
    assert dopo == prima
