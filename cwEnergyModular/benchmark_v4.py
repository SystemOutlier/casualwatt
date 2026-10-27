# -*- coding: utf-8 -*-
"""benchmark_v4.py — runner della campagna v4 (P5, #42).

Perche' esiste. Il percorso di produzione (``benchmark_unified.py``) resta
intatto: la campagna v4 ha bisogno di una sequenza che la produzione non ha
(settling, cooldown fra i punti, tre finestre pre, ``m`` richieste con bordi
di misura, tre finestre post) e di una riga che dichiari la provenienza di
energia, quota CPU e baseline. Questo file implementa quella sequenza SENZA
modificare ``benchmark_unified.py``.

Componenti condivisi con la produzione (D6): ``EnergySession`` e il suo bordo
di misura, ``CasualWattLocalEnergyProfiler``, ``_basic_record`` e
``_finalize_energy_fields``, ``_ollama_payload``, ``evaluate_response``, gli
export CSV. La coerenza e' verificata da
``tests/test_shared_components_v4.py``: se un costruttore di riga o una
colonna divergono, il test cade.

Cosa questo runner NON fa (dichiarato, non aggirato):

* non stima i token (P2.6): se ``prompt_eval_count``/``eval_count`` mancano la
  riga resta con i campi vuoti e una nota, e non entra in nessuna analisi
  (il contatore di token e' un contatore, non una stima da euristica);
* non calcola i campi di analisi (``r_A``, ``r_B``, ``u_edge_j``,
  ``budget_fit_j``, ...): restano celle vuote nei riepiloghi finche'
  l'analisi non li produce;
* non cambia ``benchmark_unified.py`` ne' il payload storico: la v4 forza
  ``keep_alive=-1`` e ``num_ctx=8192`` nel proprio payload e lo dichiara in
  riga (``keep_alive_sent``) e nelle note di run.

Un errore di misura (richiesta HTTP fallita, contatore non disponibile,
calibrazione fallita per causa non tecnica) ferma il run: un blocco con meno
di ``m`` richieste non e' un blocco. I blocchi gia' completati restano scritti
(append-only) e il run metadata dichiara l'interruzione.

Eccezione Emenda 8 (P1.6, protocollo: sezione "Emenda 8 (2026-10-26)"): un
GUASTO TECNICO del contatore in una finestra di baseline (delta negativo,
lettura non finita, replica non positiva) INVALIDA il blocco alla prima
occorrenza e lo fa sostituire UNA sola volta da un blocco completo dello stesso
punto di disegno, con nonce nuovi, in una posizione estratta a sorte dal resto
del batch col seme registrato; un secondo guasto sul sostituto dichiara il
blocco "mancante". Il tetto K di blocchi invalidati per batch e il seme si
leggono DA CONFIG (o argomenti espliciti): se mancano, il runner SI RIFIUTA di
partire. I flag di qualita' (pre_unstable, drift, ...) non sostituiscono
nulla: restano flag.
"""
from __future__ import annotations

import argparse
import hashlib
import math
import os
import platform
import random
import statistics
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import requests

import benchmark_unified as bu
import config
import llm_judge as _lj
from casualwatt_csv_export import (
    BLOCK_SUMMARY_COLUMNS,
    export_results_csv,
    export_summary_csv,
    write_run_metadata,
)
from energy.energy_session import MEASURED_METHODS, SESSION
from energy.local_energy import CasualWattLocalEnergyProfiler
from energy.worker_tree import worker_cpu_delta
from evaluator import evaluate_response

APP_VERSION = bu.APP_VERSION

M_REQUESTS = 3          # P3.13: m = 3 richieste per blocco
NUM_CTX = 8192          # P2.7
KEEP_ALIVE = "-1"       # P1.4
TOKENS_LEVEL = "per-request"

# Cooldown fra i punti (P1.5). Tre parametri su quattro sono lettera del
# protocollo congelato (protocollo_v4_20261024.md:210-212): "la media a 10 s
# rientra entro 0,5 W da P_pre per 10 s, con tetto 120 s". Il quarto,
# ``COOLDOWN_STEP_S``, NON e' una soglia: e' la cadenza con cui si osserva la
# media mobile, e coincide con il ``step_s`` di default di
# ``EnergySession.settle_idle`` (``energy/energy_session.py:2373-2374``) perche'
# il cooldown e' lo stesso tipo di attesa.
COOLDOWN_WINDOW_S = 10.0     # larghezza della media mobile
COOLDOWN_TOLERANCE_W = 0.5   # scarto ammesso da P_pre
COOLDOWN_SUSTAIN_S = 10.0    # durata della permanenza ("per 10 s")
COOLDOWN_CAP_S = 120.0       # tetto: al tetto si procede e si marca
COOLDOWN_STEP_S = 1.0        # cadenza di osservazione, non una soglia

DEFAULT_RESULTS_PATH = config.RESULTS_DIR / "casualwatt_v4_results.csv"
DEFAULT_BLOCK_SUMMARY_PATH = config.RESULTS_DIR / "casualwatt_v4_block_summary.csv"


class V4MeasurementError(RuntimeError):
    """Errore che invalida il blocco/run: si ferma, non si aggira."""


class V4CounterFault(V4MeasurementError):
    """Guasto TECNICO del contatore durante una calibrazione di baseline.

    Emenda 8 (P1.6): SOLO questa classe innesca la sostituzione del blocco.
    ``invalid_reason`` e' uno dei tre token congelati nella sezione "Emenda 8"
    del protocollo (``delta_negativo``, ``lettura_non_finita``,
    ``replica_non_positiva``); ``rows`` porta le righe gia' prodotte dal blocco
    (vuote se il guasto e' nella calibrazione pre): restano append-only nel CSV
    con una nota dichiarata che le esclude da ogni analisi, perche' buttarle
    sarebbe perdere l'evidenza del guasto.

    Non e' un guasto sostituibile l'assenza del contatore ("nessun contatore di
    energia/potenza package disponibile", energy/energy_session.py:2548-2553):
    quella e' un errore del backend, ed e' un ``V4MeasurementError`` semplice
    che ferma il run come prima.
    """

    def __init__(self, message: str, invalid_reason: str,
                 rows: Optional[List[Dict]] = None):
        super().__init__(message)
        self.invalid_reason = invalid_reason
        self.rows = list(rows or [])


# ---- Emenda 8 (P1.6): parametri letti da config, nessun default inventato --
# K = tetto di blocchi invalidati per batch; oltre il tetto il runner si
# ferma con un messaggio. Il seme e' la base del sorteggio della posizione del
# sostituto, registrato nel run metadata. Entrambi arrivano, in ordine di
# priorita', da: argomento esplicito di run_v4_benchmark -> attributo di
# config -> variabile d'ambiente. Manca tutto? Il runner si rifiuta di
# partire: un parametro di disegno assente non si riempie con un valore
# scelto da chi esegue, perche' la posizione dei sostituti e il numero di
# blocchi tollerati sono decisioni prese PRIMA dei dati (come le soglie).
ENV_MAX_INVALIDATED_BLOCKS = "CW_V4_MAX_INVALIDATED_BLOCKS_K"
ENV_SUBSTITUTION_SEED = "CW_V4_SUBSTITUTION_SEED"

INVALID_REASON_TOKENS = (
    "delta_negativo", "lettura_non_finita", "replica_non_positiva")


def resolve_emenda8_params(max_invalidated_blocks: Optional[int],
                           substitution_seed: Optional[str]
                           ) -> Tuple[int, str, str]:
    """(K, seme, nota sulle provenienze) o ValueError: mai un default.

    Ritorna anche la stringa che dichiara DOVE sono stati letti i due valori:
    la provenienza di un parametro di disegno finisce nel run metadata, per
    lo stesso motivo per cui ``energy_calculation_method`` finisce nella riga.
    """
    parts = []
    k_raw = max_invalidated_blocks
    if k_raw is None and hasattr(config, "V4_MAX_INVALIDATED_BLOCKS_K"):
        k_raw = config.V4_MAX_INVALIDATED_BLOCKS_K
        parts.append(f"K={k_raw!r} (config.V4_MAX_INVALIDATED_BLOCKS_K)")
    if k_raw is None:
        k_raw = os.getenv(ENV_MAX_INVALIDATED_BLOCKS)
        if k_raw not in (None, ""):
            parts.append(f"K={k_raw!r} (env {ENV_MAX_INVALIDATED_BLOCKS})")
    if k_raw is None:
        raise ValueError(
            "il runner v4 non parte: manca il tetto K di blocchi invalidati "
            f"per batch (argomento max_invalidated_blocks, "
            f"config.V4_MAX_INVALIDATED_BLOCKS_K o env "
            f"{ENV_MAX_INVALIDATED_BLOCKS}). Nessun default inventato "
            "(Emenda 8, P1.6).")
    try:
        k = int(str(k_raw).strip())
    except (TypeError, ValueError):
        raise ValueError(
            f"K di Emenda 8 non interpretabile come intero: {k_raw!r}") from None
    if k < 0:
        raise ValueError(f"K di Emenda 8 deve essere >= 0, letto {k}")

    s_raw = substitution_seed
    if (s_raw is None or str(s_raw) == "") and \
            hasattr(config, "V4_SUBSTITUTION_SEED"):
        s_raw = config.V4_SUBSTITUTION_SEED
        parts.append(f"seme={s_raw!r} (config.V4_SUBSTITUTION_SEED)")
    if s_raw is None or str(s_raw) == "":
        s_raw = os.getenv(ENV_SUBSTITUTION_SEED)
        if s_raw not in (None, ""):
            parts.append(f"seme={s_raw!r} (env {ENV_SUBSTITUTION_SEED})")
    if s_raw is None or str(s_raw) == "":
        raise ValueError(
            "il runner v4 non parte: manca il seme di sostituzione (argomento "
            f"substitution_seed, config.V4_SUBSTITUTION_SEED o env "
            f"{ENV_SUBSTITUTION_SEED}). Il punto del sostituto sorteggiato e' "
            "riproducibile solo con il seme dichiarato (Emenda 8, P1.6).")
    seed = str(s_raw)
    if not parts:
        parts.append(
            f"K={k} (argomento), seme={seed!r} (argomento)")
    return k, seed, "; ".join(parts)


def classify_calibration_exception(exc: BaseException) -> Optional[str]:
    """Token Emenda 8 per un'eccezione di ``calibrate_idle``, o None.

    ``None`` significa: NON e' un guasto tecnico sostituibile. L'assenza del
    contatore (``energy_session.py:2548`` -> raise ``:2553``) ricade qui: e'
    un errore del backend, e la sostituzione dello stesso punto non lo
    aggiusta. La decrescenza del contatore (raise ``:2561-2563``) e' invece
    il segnale del ``delta_negativo``; il reset del contatore si manifesta
    come decrescenza (``energy_session.py:1079-1083``), quindi ricade nello
    stesso token: non esiste un quarto token per un evento che l'unico
    osservabile classifica gia' cosi'.
    """
    text = str(exc)
    if "contatore decrescente" in text:
        return "delta_negativo"
    return None


def classify_reps(raw: Optional[Sequence[float]],
                  clean: Sequence[float]) -> Optional[str]:
    """Token Emenda 8 per la terna letta dopo una calibrazione riuscita.

    * ``lettura_non_finita``: la terna grezza ha 3 valori ma ``_clean_reps``
      ne ha scartato almeno uno (NaN/inf/non convertibili): il percorso di
      produzione lascia passare un delta non finito (il guard `delta_j < 0`
      e' falso per NaN), quindi e' qui, nel runner, che il blocco viene
      invalidato;
    * ``replica_non_positiva``: una replica di potenza <= 0 (contatore che
      non ha contato, o delta azzerato);
    * ``None`` per il resto; una terna grezza gia' corta di suo NON e' un
      guasto classificabile: e' un'incongruenza dell'interfaccia, e resta
      un errore semplice che ferma il run.
    """
    if len(raw or ()) == 3 and len(clean) != 3:
        return "lettura_non_finita"
    if len(clean) == 3 and any(r <= 0.0 for r in clean):
        return "replica_non_positiva"
    return None


def _attempt_of(rec: Dict, where: str) -> int:
    """`block_attempt` di una riga o di un riepilogo: assente/vuoto -> 1.

    Il tentativo di piano e' `1` anche dove la colonna non e' stata timbrata
    (CSV prodotti prima dell'Emenda 8); qualunque altro valore non interpretabile
    e' un rifiuto, non un 1 di conforto.
    """
    raw = rec.get("block_attempt", "")
    if raw in (None, ""):
        return 1
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{where}: block_attempt={raw!r} non e' un intero: il tentativo "
            "di un blocco non si interpreta per approssimazione") from exc


def partition_block_rows(rows: Sequence[Dict],
                         block_summaries: Sequence[Dict]) -> Dict:
    """Filtro P6 eseguibile dell'Emenda 8: nessuna riga invalidata entra
    nelle stime primarie per dimenticanza.

    Perche' esiste. `invalid_reason` sulla riga e' soltanto informazione finche'
    il codice che aggrega non lo interpreta; la nota "NON entrano in nessuna
    analisi" nel CSV non e' un filtro. Questa funzione E' il gate: partiziona
    le righe di richiesta in `valid_rows` (unica fonte delle stime primarie)
    ed `excluded_rows` (evidenza append-only, usabile solo da analisi
    secondarie che LO DICHIARANO). Fonte autoritativa dell'invalidazione e il
    riepilogo di blocco, non la riga: una riga di blocco invalidato che non
    ha timbrato il token (timbratura saltata per bug o per CSV meta-riscritto
    a mano) resta esclusa perche' E' IL RIEPILOGO A DIRE che il blocco e'
    caduto.

    Le cinque regole dell'ordine di servizio (26-10), nell'ordine in cui
    sono applicate:
      1. esclusione: righe il cui riepilogo ha `invalid_reason` non vuota
         vanno in `excluded_rows`, qualunque sia il valore sulla riga;
      2. identita': il sostituto (tentativo 2) non e' mai confuso con
         l'originale -- `block_id` diverso per costruzione, e qui si esige
         anche che il tentativo 2 dichiari `replaced_block_id` esistente e
         invalidato, e che il tentativo 1 NON lo dichiari;
      3. conservazione: gli input NON sono mai mutati, cancellati o
         sovrascritti; le due liste restituite sono copie; il registro
         append-only resta integro e due riepiloghi con la stessa chiave
         (batch_id, block_id) sono un rifiuto immediato, non una vincita;
      4. concordia riga/riepilogo su motivo, tentativo, identificativi:
         qualunque disaccordo SOLLEVA, perche' scegliere quale dei due
         credere sarebbe il fallback silenzioso che il protocollo vieta;
      5. conteggi verificabili di blocchi validi, invalidati, sostitutivi
         e mancanti (questi ultimi = invalidati al tentativo 2), calcolati
         SOLO dai riepiloghi, cosi' che un terzo possa ricavarli dagli
         artefatti senza toccare le righe.

    I campi assenti su una riga (`block_attempt`, `replaced_block_id`,
    `point_id`) sono trattati come il valore di piano -- vuoto/1 -- perche'
    le colonne nuove sono in coda allo schema (F.17) e un CSV vecchio non le
    ha; un valore PRESENTE e in disaccordo con il riepilogo e' un errore.
    Un token fuori dai tre congelati, una riga orfana (nessun riepilogo per
    la sua chiave) o un riepilogo senza `block_id` sono tutti rifiutati: il
    gate non include per default nulla.
    """
    summary_by_key: Dict[Tuple[str, str], Dict] = {}
    for i, s in enumerate(block_summaries):
        block = str(s.get("block_id", "") or "")
        batch = str(s.get("batch_id", "") or "")
        if not block:
            raise ValueError(
                f"riepilogo #{i} senza block_id: un riepilogo non "
                "identificabile non puo' autorizzare ne' escludere nulla")
        key = (batch, block)
        if key in summary_by_key:
            raise ValueError(
                f"chiave (batch_id, block_id) duplicata {batch}/{block}: la "
                "regola 3 dell'Emenda 8 vieta sovrascritture, e due "
                "riepiloghi dello stesso blocco non sono entrambi veri")
        summary_by_key[key] = s

    counts: Dict[str, int] = {
        "valid_blocks": 0, "invalidated_blocks": 0,
        "substitute_blocks": 0, "missing_blocks": 0,
        "valid_rows": 0, "excluded_rows": 0}

    for (batch, block), s in summary_by_key.items():
        reason = str(s.get("invalid_reason", "") or "")
        replaced = str(s.get("replaced_block_id", "") or "")
        attempt = _attempt_of(s, f"riepilogo {batch}/{block}")
        if reason and reason not in INVALID_REASON_TOKENS:
            raise ValueError(
                f"riepilogo {batch}/{block}: invalid_reason={reason!r} non e'"
                " uno dei tre token congelati: un marcatore non interpretabile"
                " non puo' essere usato per escludere o includere")
        if attempt not in (1, 2):
            raise ValueError(
                f"riepilogo {batch}/{block}: block_attempt={attempt} fuori "
                "da {{1, 2}}: l'Emenda 8 non ammette un terzo tentativo")
        if reason:
            counts["invalidated_blocks"] += 1
        else:
            counts["valid_blocks"] += 1
        if attempt == 2:
            counts["substitute_blocks"] += 1
            if not replaced:
                raise ValueError(
                    f"riepilogo {batch}/{block}: tentativo 2 senza "
                    "replaced_block_id: il sostituto sarebbe indistinguibile "
                    "dal blocco di piano (regola 2)")
            orig = summary_by_key.get((batch, replaced))
            if orig is None:
                raise ValueError(
                    f"riepilogo {batch}/{block}: sostituisce {replaced!r} che "
                    "non ha nessun riepilogo in questo batch: l'identita' del "
                    "sostituto non e' verificabile (regola 4)")
            if not str(orig.get("invalid_reason", "") or ""):
                raise ValueError(
                    f"riepilogo {batch}/{block}: sostituisce {replaced!r} che "
                    "risulta VALIDO: solo un blocco invalidato si sostituisce")
            if reason:
                counts["missing_blocks"] += 1
        elif replaced:
            raise ValueError(
                f"riepilogo {batch}/{block}: tentativo 1 con "
                f"replaced_block_id={replaced!r}: confusione di identita'"
                " fra piano e sostituto (regola 2)")

    valid_rows: List[Dict] = []
    excluded_rows: List[Dict] = []
    for i, r in enumerate(rows):
        block = str(r.get("block_id", "") or "")
        batch = str(r.get("batch_id", "") or "")
        s = summary_by_key.get((batch, block))
        if s is None:
            raise ValueError(
                f"riga #{i} orfana: nessun riepilogo per {batch}/{block}: "
                "non si puo' stabilire se la riga e' di un blocco valido, e "
                "il gate non include per default")
        reason_s = str(s.get("invalid_reason", "") or "")
        reason_r = str(r.get("invalid_reason", "") or "")
        if reason_r:
            if reason_r not in INVALID_REASON_TOKENS:
                raise ValueError(
                    f"riga #{i} ({batch}/{block}): invalid_reason="
                    f"{reason_r!r} non e' un token congelato")
            if not reason_s:
                raise ValueError(
                    f"riga #{i} ({batch}/{block}): la riga dichiara "
                    f"invalid_reason={reason_r!r} ma il suo riepilogo e'"
                    " valido: motivo in disaccordo fra riga e riepilogo "
                    "(regola 4), non una preferenza del filtro")
            if reason_r != reason_s:
                raise ValueError(
                    f"riga #{i} ({batch}/{block}): motivo {reason_r!r} sulla "
                    f"riga contro {reason_s!r} nel riepilogo (regola 4)")
        attempt_r = _attempt_of(r, f"riga #{i} ({batch}/{block})")
        attempt_s = _attempt_of(s, f"riepilogo {batch}/{block}")
        if attempt_r != attempt_s:
            raise ValueError(
                f"riga #{i} ({batch}/{block}): tentativo {attempt_r} sulla "
                f"riga contro {attempt_s} nel riepilogo (regola 4)")
        replaced_r = str(r.get("replaced_block_id", "") or "")
        replaced_s = str(s.get("replaced_block_id", "") or "")
        if replaced_r != replaced_s:
            raise ValueError(
                f"riga #{i} ({batch}/{block}): replaced_block_id="
                f"{replaced_r!r} sulla riga contro {replaced_s!r} nel "
                "riepilogo: identificativo del blocco in disaccordo (reg. 2)")
        point_r = str(r.get("point_id", "") or "")
        point_s = str(s.get("point_id", "") or "")
        if point_r and point_s and point_r != point_s:
            raise ValueError(
                f"riga #{i} ({batch}/{block}): point_id {point_r!r} sulla "
                f"riga contro {point_s!r} nel riepilogo (regola 4)")
        # copia: il gate non restituisce oggetti che un'analisi potrebbe
        # mutare rimettendo in discussione il registro append-only
        (excluded_rows if reason_s else valid_rows).append(dict(r))

    counts["valid_rows"] = len(valid_rows)
    counts["excluded_rows"] = len(excluded_rows)
    return {"valid_rows": valid_rows, "excluded_rows": excluded_rows,
            "counts": counts}


class _Cancelled(Exception):
    """Cancellazione richiesta dal chiamante (non e' un errore di misura)."""


# ---------------------------------------------------------------------------
# Identita' e prompt (P2.8)
# ---------------------------------------------------------------------------
def _utc_iso(t_wall: float) -> str:
    return datetime.fromtimestamp(
        float(t_wall), tz=timezone.utc).isoformat(timespec="milliseconds")


def _identity_list(procs: Iterable[object]) -> str:
    """`pid:create_time;...` — l'identita', non solo il PID (P4)."""
    return ";".join(
        f"{int(getattr(w, 'pid'))}:{float(getattr(w, 'create_time')):.6f}"
        for w in (procs or ())
    )


def prompt_nonce(seq: int) -> str:
    """Nonce a larghezza fissa, univoco nel run (P2.8).

    La larghezza fissa non e' estetica: il protocollo dichiara che il
    modello geometrico resta esatto con nonce di lunghezza costante (F.6).
    """
    n = int(seq)
    if n < 0:
        raise ValueError("seq del nonce non puo' essere negativo")
    return f"[cw4-{n:08d}]"


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_prompt_v4(prompt: Dict, seq: int) -> Tuple[Dict, str, str]:
    """Prompt effettivamente inviato = nonce + testo originale.

    Ritorna ``(prompt_inviato, nonce, sha256)``. Il nonce sta nel testo, quindi
    e' ricostruibile dal solo CSV: ``prompt`` contiene cio' che e' stato
    spedito, non cio' che si intendeva spedire.
    """
    nonce = prompt_nonce(seq)
    sent_text = f"{nonce}\n{prompt['text']}"
    sent = dict(prompt, text=sent_text)
    return sent, nonce, prompt_sha256(sent_text)


# ---------------------------------------------------------------------------
# Inferenza v4: nessuna stima (P2.6), contesto e keep_alive dichiarati
# ---------------------------------------------------------------------------
def payload_v4(model: str, prompt: str, temperature: float,
               num_predict: int, num_ctx: int = NUM_CTX,
               keep_alive: str = KEEP_ALIVE) -> Dict:
    """Payload = costruttore condiviso + i due parametri che la v4 fissa.

    ``bu._ollama_payload`` resta l'unica fonte delle chiavi storiche; qui si
    aggiungono SOLO ``options.num_ctx`` (P2.7) e ``keep_alive`` (P1.4). Il
    valore realmente inviato finisce in ``keep_alive_sent``.
    """
    payload = bu._ollama_payload(model, prompt, temperature, num_predict)
    options = dict(payload.get("options") or {})
    options["num_ctx"] = int(num_ctx)
    payload["options"] = options
    payload["keep_alive"] = str(keep_alive)
    return payload


def infer_v4(model: str, prompt: str, temperature: float, timeout_s: float,
             num_predict: int = 160, num_ctx: int = NUM_CTX,
             keep_alive: str = KEEP_ALIVE) -> Dict:
    """POST /api/generate con i marcatori di finestra per il profilo.

    Differenza deliberata da ``bu._ollama_infer_only``: qui i token NON si
    stimano. Se il motore non riporta ``prompt_eval_count`` o ``eval_count``,
    il campo resta vuoto e ``tokens_valid`` e' False; il chiamante aggiunge la
    nota e la riga non entra nelle analisi sui token (P2.6).
    """
    payload = payload_v4(model, prompt, temperature, num_predict,
                         num_ctx=num_ctx, keep_alive=keep_alive)
    t0 = time.monotonic()
    wall_start = time.time()
    resp = requests.post(config.OLLAMA_GENERATE_ENDPOINT, json=payload,
                         timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    t1 = time.monotonic()

    text = data.get("response", "") or ""
    p_tok = int(data.get("prompt_eval_count") or 0)
    c_tok = int(data.get("eval_count") or 0)
    tokens_valid = p_tok > 0 and c_tok > 0
    return {
        "text": text,
        "prompt_tokens": p_tok if p_tok > 0 else "",
        "completion_tokens": c_tok if c_tok > 0 else "",
        "tokens_valid": tokens_valid,
        "duration_s": round(t1 - t0, 6),
        "prefill_duration_s": float(data.get("prompt_eval_duration") or 0) / 1e9,
        "decoding_duration_s": float(data.get("eval_duration") or 0) / 1e9,
        "done_reason": data.get("done_reason", "") or "",
        "raw_created_at": data.get("created_at", "") or "",
        "tool_calls": 0,
        "keep_alive_sent": bu._keep_alive_sent(payload),
        "num_ctx": int(num_ctx),
        "num_predict": int(num_predict),
        "_t0": t0,
        "_t1": t1,
        "_wall_start": wall_start,
    }


# ---------------------------------------------------------------------------
# Terminazione e validita' della richiesta (P2.4, P2.5)
# ---------------------------------------------------------------------------
# Le cinque classi sono quelle della tabella di P2.4 (protocollo:727-741):
# non se ne aggiungono. Una richiesta che non cade in nessuna riga resta senza
# classe, con il perche' dichiarato, e con il motivo di invalidita' di P2.5.
TERMINATION_CLASSES = ("cap_reached", "termination_inconsistent", "eos",
                       "eos_at_cap", "termination_missing")

# Motivi di invalidita' di P2.5 (protocollo:760-764). early_stop, cap_reached e
# eos_at_cap NON sono in questa lista: sono flag che non invalidano.
INVALIDITY_REASONS = ("tokens_missing", "termination_missing",
                      "termination_inconsistent", "counter_inconsistent",
                      "context_boundary")


def _to_int(value: object) -> Optional[int]:
    """Intero netto, o ``None`` se il valore non c'e'. Lo zero non e' assenza."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def termination_fields(done_reason: object, n_in_actual: object,
                       n_out_actual: object, num_predict: object,
                       num_ctx: object = None) -> Dict[str, object]:
    """Classifica la terminazione di una richiesta secondo P2.4.

    Ritorna ``done_reason`` grezzo (marcato ``<assente>`` quando il campo non
    c'e', perche' l'assenza va letta e non confusa con una stringa vuota), la
    classe, ``early_stop`` e i motivi di invalidita' di P2.5.

    I due contatori sono parametri obbligatori e non hanno default: ``None``
    significa "il motore non l'ha riportato", che e' il motivo
    ``tokens_missing`` di P2.5, e non puo' significare anche "il chiamante non
    me l'ha chiesto". Solo ``num_ctx`` e' opzionale, perche' la guardia
    ``N_in + N_out <= num_ctx`` senza il contesto dichiarato non si puo' proprio
    valutare.

    ``early_stop`` e' la formula congelata di P2.4,
    ``done_reason == "stop" and N_out_actual < num_predict``: quando
    ``done_reason`` non e' ``"stop"`` la congiunzione e' falsa gia' letta e il
    valore e' ``"false"`` senza bisogno dei token. Quando e' ``"stop"`` ma i
    token mancano, il valore non e' calcolabile e resta ``""``: non e' "false".

    Righe della tabella non coperte (``stop`` con ``N_out > num_predict``) non
    vengono assegnate a forza a una classe vicina: la classe resta vuota, il
    perche' si dichiara e il motivo di P2.5 (``counter_inconsistent``) viene
    registrato, perche' quello la tabella di P2.5 lo nomina davvero.
    """
    raw = str(done_reason or "").strip()
    n_in = _to_int(n_in_actual)
    n_out = _to_int(n_out_actual)
    cap = _to_int(num_predict)
    ctx = _to_int(num_ctx)
    klass = ""
    early = ""
    notes: List[str] = []
    reasons: List[str] = []

    if raw == "length":
        if n_out is None or cap is None:
            notes.append("classe P2.4 non determinabile: N_out_actual o "
                         "num_predict assente")
        elif n_out == cap:
            klass = "cap_reached"
        else:
            klass = "termination_inconsistent"
    elif raw == "stop":
        if n_out is None or cap is None:
            notes.append("classe P2.4 non determinabile: N_out_actual o "
                         "num_predict assente")
        elif n_out < cap:
            klass = "eos"
            early = "true"
        elif n_out == cap:
            klass = "eos_at_cap"
            early = "false"
        else:
            notes.append("nessuna riga della tabella P2.4 per done_reason=stop "
                         "con N_out_actual > num_predict")
    else:
        klass = "termination_missing"

    if early == "" and raw != "stop":
        # la congiunzione di P2.4 si legge anche senza contatori
        early = "false"

    if n_out is None or n_in is None or n_out <= 0 or n_in <= 0:
        reasons.append("tokens_missing")
    if klass == "termination_missing":
        reasons.append("termination_missing")
    if klass == "termination_inconsistent":
        reasons.append("termination_inconsistent")
    if n_out is not None and cap is not None and n_out > cap:
        reasons.append("counter_inconsistent")
    if n_in is not None and n_out is not None and ctx is not None \
            and (n_in + n_out) > ctx:
        reasons.append("context_boundary")

    return {
        "done_reason": raw if raw else "<assente>",
        "termination_class": klass,
        "early_stop": early,
        "invalid_reasons": reasons,
        "undetermined": notes,
    }


def termination_note(fields: Dict[str, object]) -> str:
    """Riga di nota analizzabile per la terminazione (chiavi ``k=v``).

    Non esiste una colonna per questi campi: lo schema di P5 le ha congelate nel
    lotto 1 e le aggiunte vanno ratificate con il congelamento. La nota e' la
    collocazione che non aggiunge nessuna colonna e resta agganciata alla riga
    dalla chiave ``run_id`` / ``block_id`` / ``point_id``.
    """
    parts = [
        f"done_reason={fields.get('done_reason', '')}",
        f"termination_class={fields.get('termination_class', '') or '<non determinata>'}",
        f"early_stop={fields.get('early_stop', '') or '<non determinabile>'}",
    ]
    reasons = list(fields.get("invalid_reasons") or [])
    if reasons:
        parts.append("richiesta invalida per: " + ",".join(reasons))
    for d in list(fields.get("undetermined") or []):
        parts.append(str(d))
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Baseline di blocco (P1.5, P1.6, P1.7)
# ---------------------------------------------------------------------------
def _clean_reps(reps: Optional[Sequence[float]]) -> List[float]:
    out: List[float] = []
    for r in reps or ():
        try:
            v = float(r)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            out.append(v)
    return out


def block_baseline(reps_pre: Sequence[float],
                   reps_post: Optional[Sequence[float]] = None) -> Dict[str, object]:
    """Mediane, range, drift e budget base di un blocco.

    Formule congelate (P1.5-P1.7, F.1/F.4)::

        baseline_pre_w  = mediana(P_rep,1..3)
        pre_range_w     = max(P_rep) - min(P_rep)
        half_range_pre_w= pre_range_w / 2
        dP              = mediana(P_post) - baseline_pre_w
        half_drift_w    = |dP| / 2
        budget_base_w   = sqrt(half_range_pre_w^2 + half_drift_w^2)

    ``P_post`` non entra mai in ``baseline_pre_w`` (P1.14): e' diagnostica.
    Le celle che non si possono calcolare restano vuote, non zero.

    P2.9, confermato dall'Emenda 8 (2026-10-26): ``budget_base_w`` RESTA la
    combinazione in quadratura delle DUE SEMI-AMPIEZZE ``half_range_pre_w`` e
    ``half_drift_w``. Non e' una propagazione di varianza e non va chiamata
    "deviazione standard": con n = 3 non si stima una varianza (P4.12), e per
    due termini non negativi ``sqrt(a^2+b^2)`` sta fra ``1/sqrt(2)`` e ``1``
    volte la somma aritmetica, quindi non e' nemmeno un limite massimo
    garantito. E' un PROXY CONSERVATIVO di incertezza standard: usato cosi'
    com'e' nei pesi ``w_b = 1/budget_fit_b^2`` (F.9), dove conta la forma
    relativa fra blocchi, non il livello assoluto del singolo numero. La forma di
    combinazione (quadratura o somma) resta la sola eccezione dichiarata al
    congelamento, rinviata ai dati del pilota P2.9/P6.2: qui il pilota la
    descrive (distribuzione di ``half_range_pre_w`` e ``u_within,b``), non la
    sceglie; per le soglie del gate che chiedono una garanzia piu' forte si
    applichera' un fattore di copertura separato, non una formula diversa.
    """
    pre = _clean_reps(reps_pre)
    post = _clean_reps(reps_post)
    out: Dict[str, object] = {
        "baseline_pre_w": "",
        "baseline_post_w": "",
        "pre_windows_w": "",
        "post_windows_w": "",
        "pre_range_w": "",
        "dP": "",
        "half_range_pre_w": "",
        "half_drift_w": "",
        "budget_base_w": "",
    }
    if not pre:
        return out
    out["pre_windows_w"] = ";".join(f"{v:.6f}" for v in pre)
    pre_med = statistics.median(pre)
    out["baseline_pre_w"] = round(float(pre_med), 6)
    if len(pre) >= 2:
        pre_range = max(pre) - min(pre)
        out["pre_range_w"] = round(pre_range, 6)
        out["half_range_pre_w"] = round(pre_range / 2.0, 6)
    if post:
        out["post_windows_w"] = ";".join(f"{v:.6f}" for v in post)
        post_med = statistics.median(post)
        out["baseline_post_w"] = round(float(post_med), 6)
        if len(pre) >= 2:
            dp = float(post_med) - float(pre_med)
            out["dP"] = round(dp, 6)
            out["half_drift_w"] = round(abs(dp) / 2.0, 6)
    if out["half_range_pre_w"] != "" and out["half_drift_w"] != "":
        # P2.9 / Emenda 8: quadratura di DUE SEMI-AMPIEZZE, proxy conservativo
        # per i pesi F.9. Non e' una propagazione di varianza (con n = 3 non
        # si stima una varianza) e non e' un limite massimo garantito: il
        # rapporto sqrt(a^2+b^2)/(a+b) sta fra 1/sqrt(2) e 1. La forma di
        # combinazione (questa o la somma aritmetica) e' l'unica eccezione
        # dichiarata al congelamento, da chiudere sui dati del pilota PRIMA
        # della campagna: finche' non e' chiusa il numero si chiama "budget",
        # non "incertezza" e non "tolleranza".
        out["budget_base_w"] = round(
            math.hypot(float(out["half_range_pre_w"]),
                       float(out["half_drift_w"])), 6)
    return out


def budget_base_j(dt_w_s: float, budget_base_w: float) -> float:
    """`budget_base_j = Δt_W · budget_base_w` (F.4), per richiesta."""
    return round(float(dt_w_s) * float(budget_base_w), 6)


def block_mean_duration_s(rows: Sequence[Dict], m: int) -> Tuple[str, str]:
    """`Δt̄_W,b = (1/m) · Σ_{i∈blocco} Δt_W,i` (F.11) sul blocco appena chiuso.

    Due dettagli congelati, entrambi verificabili nel testo: la statistica e'
    la **media aritmetica** (protocollo:1631 e :1389 la scrivono `(1/m)·Σ`, e
    :1644 la chiama "durata **media** delle finestre"), e il campo che la
    alimenta e' `duration_s` di riga -- il quinto emendamento lo dice due
    volte: "il campo durata che alimenta `u_base,b` e `u_bias,b` e' la media
    per blocco di `duration_s`, la stessa grandezza di `Δt̄_W,b`"
    (protocollo:1651) e "`Δt̄_W,b` **non** e' una colonna nuova: e' la media per
    blocco della `duration_s` gia' prevista" (protocollo:2178).

    La somma e' su `m` richieste perche' `m` e' il numero congelato del blocco:
    se una riga non ha durata la media su cio' che resta non e' piu' `(1/m)·Σ`,
    e il riepilogo resta vuoto con il perche'. Una `budget_base_j` di blocco
    calcolata su un denominatore diverso da `m` sarebbe un numero diverso con
    lo stesso nome.

    Ritorna ``(valore, motivo)``: valore ``""`` quando non si puo' calcolare,
    mai un `0.0` inventato.
    """
    try:
        n_richieste = int(m)
    except (TypeError, ValueError):
        return "", "m non numerico: media di blocco non calcolabile"
    if n_richieste < 1:
        return "", f"m={n_richieste} < 1: nessun blocco da mediare"
    durate: List[float] = []
    for r in rows:
        d = r.get("duration_s")
        if d is None or (isinstance(d, str) and not d.strip()):
            continue
        try:
            v = float(d)
        except (TypeError, ValueError):
            continue
        if math.isfinite(v):
            durate.append(v)
    if len(durate) != n_richieste:
        return "", (f"{len(durate)} durate su {n_richieste} richieste: "
                    "(1/m)·Σ non e' calcolabile")
    return round(sum(durate) / n_richieste, 6), ""


# ---------------------------------------------------------------------------
# Cooldown fra i punti (P1.5)
# ---------------------------------------------------------------------------
def cooldown_power_w(window_s: float) -> Optional[float]:
    """Potenza media package sulle ultime ``window_s`` dal contatore di sessione.

    Stessa grandezza e stessa fonte di ``settle_idle`` e della calibrazione:
    ``package_energy_exact_between`` diviso la durata della finestra, non una
    media dei campioni. ``None`` quando il backend non esprime una lettura
    esatta: una finestra senza lettura NON e' una potenza pari a zero, e il
    chiamante la conta come lettura mancante.
    """
    now = time.monotonic()
    try:
        e_window = SESSION.package_energy_exact_between(now - window_s, now)
    except Exception:  # noqa: BLE001 - la lettura degrada, non crasha il run
        return None
    if e_window is None:
        return None
    try:
        v = float(e_window)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v / float(window_s)


def cooldown_to_baseline(
    target_pre_w: Optional[float],
    *,
    window_s: float = COOLDOWN_WINDOW_S,
    tolerance_w: float = COOLDOWN_TOLERANCE_W,
    sustain_s: float = COOLDOWN_SUSTAIN_S,
    cap_s: float = COOLDOWN_CAP_S,
    step_s: float = COOLDOWN_STEP_S,
    power_fn: Optional[Callable[[], Optional[float]]] = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    stop_event: Optional[threading.Event] = None,
) -> Dict[str, object]:
    """Attende il criterio di cooldown di P1.5 e dichiara come e' finita.

    Criterio (protocollo:210-212, distinto da quello del settling): la media
    a ``window_s`` rientra entro ``tolerance_w`` da ``target_pre_w`` **per**
    ``sustain_s``. "per 10 s" e' permanenza, non media singola: la condizione
    va osservata soddisfatta per un tratto continuo di ``sustain_s``, e un
    campione fuori tolleranza azzera il tratto (come fa ``settle_idle`` con la
    coppia di finestre). La disuguaglianza e' stretta, come in
    ``energy/energy_session.py:2400``.

    Al tetto ``cap_s`` si ritorna comunque: il protocollo dice "se il tetto
    viene raggiunto, si procede e si marca ``cooldown_timeout`", quindi il
    tetto NON invalida il blocco. ``timed_out`` e' il fatto osservato,
    ``waited_s`` il tempo realmente atteso.

    ``target_pre_w`` mancante o non finito rende il cooldown **non eseguibile**:
    ``ran=False`` e ``timed_out=False``, perche' "non calcolato" non e'
    "cooldown riuscito" e la cella ``cooldown_timeout`` resta vuota.

    ``power_fn``, ``clock`` e ``sleep`` sono iniettabili per lo stesso motivo
    per cui ``settle_idle`` non ha bisogno di dati fittizi in test: la
    meccanica dei limiti temporali si verifica deterministicamente, mentre il
    valore assoluto della potenza resta una questione di campagna.
    """
    read = power_fn or (lambda: cooldown_power_w(window_s))
    out: Dict[str, object] = {
        "ran": False,
        "reached": False,
        "timed_out": False,
        "waited_s": None,
        "target_pre_w": "",
        "samples": 0,
        "missing_reads": 0,
        "reason": "",
    }
    try:
        target = float(target_pre_w)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        target = float("nan")
    if not math.isfinite(target) or target <= 0.0:
        out["reason"] = (
            "cooldown non eseguibile: nessun P_pre di riferimento valido "
            f"(ricevuto {target_pre_w!r})")
        return out
    out["target_pre_w"] = round(target, 6)

    t_first = clock()
    satisfied_since: Optional[float] = None
    while True:
        if stop_event is not None and stop_event.is_set():
            raise _Cancelled("stop richiesto durante il cooldown")
        now = clock()
        out["samples"] = int(out["samples"]) + 1
        power = read()
        try:
            value = None if power is None else float(power)
        except (TypeError, ValueError):
            value = float("nan")
        if value is None or not math.isfinite(value):
            out["missing_reads"] = int(out["missing_reads"]) + 1
            satisfied_since = None
        elif abs(value - target) < tolerance_w:
            if satisfied_since is None:
                satisfied_since = now
            if now - satisfied_since >= sustain_s:
                out.update({"ran": True, "reached": True, "timed_out": False,
                            "waited_s": round(now - t_first, 3)})
                out["reason"] = (
                    f"cooldown soddisfatto: media a {window_s:.0f} s entro "
                    f"{tolerance_w} W da P_pre={target:.3f} W per "
                    f"{sustain_s:.0f} s consecutivi")
                return out
        else:
            satisfied_since = None

        elapsed = now - t_first
        if elapsed >= cap_s:
            out.update({"ran": True, "reached": False, "timed_out": True,
                        "waited_s": round(elapsed, 3)})
            out["reason"] = (
                f"tetto di {cap_s:.0f} s raggiunto senza {sustain_s:.0f} s "
                f"continui entro {tolerance_w} W da P_pre={target:.3f} W "
                f"(campioni={out['samples']}, letture mancanti="
                f"{out['missing_reads']}); si procede e si marca "
                "cooldown_timeout=true")
            return out
        sleep(max(min(step_s, cap_s - elapsed), 0.0))


def cooldown_timeout_flag(cooldown: Optional[Dict[str, object]]) -> str:
    """Valore di ``cooldown_timeout`` per il riepilogo di blocco.

    "true"/"false" solo quando il cooldown e' stato eseguito; vuoto quando non
    lo si poteva eseguire (primo punto del run, o baseline di riferimento
    mancante). Una cella vuota dice "non calcolato"; "false" sarebbe
    l'affermazione che il cooldown e' riuscito.
    """
    if not cooldown or not cooldown.get("ran"):
        return ""
    return "true" if cooldown.get("timed_out") else "false"


# ---------------------------------------------------------------------------
# Giudice: bordi di contatore propri (D2)
# ---------------------------------------------------------------------------
def normalize_counter_edge(edge: Dict[str, object]) -> Dict[str, object]:
    """Dà a ``read_counter_edge()`` anche il nome di chiave che il consumatore
    condiviso cerca (``t_counter_mono``).

    ``read_measurement_edge()`` espone l'istante della lettura del contatore
    come ``t_counter_mono``; ``read_counter_edge()`` lo espone come ``t_mono``.
    E' lo stesso instante, preso prima della stessa IOCTL, con due nomi:
    ``_edge_dt_w`` (in ``energy/local_energy.py``) legge il primo, quindi i
    bordi del giudice arriverebbero sempre al terzo ramo (``python-window``)
    e il fallback monotono non sarebbe mai raggiungibile. Normalizzare qui, e
    non in produzione, perche' la produzione non ha questo consumatore in
    comune: ``local_energy`` resta invariata per i suoi percorsi storici.
    """
    if isinstance(edge, dict) and "t_counter_mono" not in edge \
            and "t_mono" in edge:
        edge["t_counter_mono"] = edge["t_mono"]
    return edge


class JudgeEdgeCapture:
    """Wrapper del giudice che legge una coppia di contatore per chiamata.

    D2: il segmento del giudice non e' interpolato dal buffer quando il
    contatore e' leggibile; l'eventuale ritorno all'interpolazione e' un
    token nella riga (``judge_energy_edge_source``), non un dettaglio.
    La lettura e' una sola IOCTL per bordo: nessuna enumerazione dell'albero
    attorno al giudice, che aggiungerebbe carico al segmento che si misura.

    I bordi passano da :func:`normalize_counter_edge` per la ragione dei due
    nomi descritta li': senza, un contatore leggibile ma senza timestamp del
    record degrada all'interpolazione invece di restare lettura diretta.
    """

    def __init__(self) -> None:
        self.calls: List[Dict[str, object]] = []

    @staticmethod
    def _edge() -> Tuple[Dict[str, object], float]:
        t = time.monotonic()
        edge = normalize_counter_edge(SESSION.read_counter_edge())
        return edge, time.monotonic() - t

    def __call__(self, question: str, answer: str, model: Optional[str]):
        start, read0 = self._edge()
        try:
            return bu._judge_via_energy_session(question, answer, model)
        finally:
            end, read1 = self._edge()
            self.calls.append({
                "start": start,
                "end": end,
                # ``read_s`` e' il massimo delle DUE letture di questa chiamata:
                # quanto e' costata una IOCTL al bordo, non quanto e' durato il
                # segmento. La durata del segmento e' ``judge_window_s``.
                "read_s": max(read0, read1),
                "read_start_s": read0,
                "read_end_s": read1,
            })


def judge_direct_readiness(call: Dict[str, object],
                           baseline_pre_w: float) -> Tuple[Optional[float], str]:
    """Energia diretta di una chiamata del giudice, o perche' non c'e'.

    Ritorna ``(valore_con_segno, motivazione)``. Il valore e'
    ``ΔE_contatore − P_pre · Δt_W`` sulla COPPIA DI LETTURE di quella chiamata
    (stessa finestra per energia e durata: requisito P6.5, "Δt_W dalla stessa
    coppia di letture"), senza interpolazione.

    Casi in cui il valore non esiste, ciascuno dichiarato con la propria
    ragione perche' il fallback sia verificabile e non un mistero:

    * ``stesso record``: i due bordi riportano il medesimo timestamp del
      record PKG. La differenza del contatore sarebbe 0,0 J, ma 0,0 J qui non
      e' "il package non ha consumato": e' la stessa riga letta due volte.
      Meglio l'interpolazione dichiarata che un incrementale falso di ``−P·Δt``;
    * ``contatore assente`` o ``valore non crescente``: ``_edge_energy_j``
      ritorna None (manca un bordo, o il contatore e' resettato fra i bordi);
    * ``nessun Δt``: ``_edge_dt_w`` non ha ne' timestamp crescente ne' base
      monotona;
    * ``Δt non positivo``: finestra degenere, dividere o moltiplicare per zero
      non produce una misura.
    """
    start = call.get("start") or {}
    end = call.get("end") or {}
    ts0 = CasualWattLocalEnergyProfiler._edge_counter_ts(start)
    ts1 = CasualWattLocalEnergyProfiler._edge_counter_ts(end)
    if ts0 is not None and ts1 is not None and ts0 == ts1:
        return None, f"stesso record ai bordi (ts={ts0}): ΔE=0 non e' una misura"
    dt_w, dt_src = CasualWattLocalEnergyProfiler._edge_dt_w(start, end)
    e_raw = CasualWattLocalEnergyProfiler._edge_energy_j(start, end)
    if e_raw is None:
        return None, ("contatore assente in un bordo o valore non crescente "
                      "(reset fra i bordi)")
    if dt_w is None:
        return None, f"nessun Δt dai bordi (base={dt_src})"
    if dt_w <= 0.0:
        return None, f"Δt non positivo ({dt_w})"
    return float(e_raw) - float(baseline_pre_w) * float(dt_w), f"ok ({dt_src})"


def _direct_judge_energy(call: Dict[str, object],
                         baseline_pre_w: float) -> Optional[float]:
    """Valore diretto della chiamata, o None: versione senza motivazione.

    Resta per i chiamanti che contano le letture utilizzabili; la motivazione
    del rifiuto la da' :func:`judge_direct_readiness`.
    """
    return judge_direct_readiness(call, baseline_pre_w)[0]


def _interp_judge_energy(t_start: float, t_end: float,
                         baseline_pre_w: float) -> Optional[float]:
    """Energia GREZZA (con segno) della sottofinestra del giudice dal buffer.

    Stessa grandezza di ``bu._estimate_judge_energy`` — energia del canale
    meno ``P · dt`` sulla stessa finestra — ma con due differenze dichiarate:
    la ``P`` e' la ``P_pre`` del blocco (F.1: la baseline applicata e' quella
    pre, non uno stato mutabile della sessione) e non c'e' il clamp a zero.
    Un valore negativo e' un dato e resta nel campo; il valore convenzionale
    zero, quando serve, lo mette il chiamante e lo dichiara.

    Ritorna None se il canale non e' un misuratore o il buffer non copre la
    finestra: in quel caso non si inventa un numero.
    """
    try:
        dur = max(float(t_end) - float(t_start), 0.0)
        if dur <= 0.0:
            return 0.0
        if SESSION.source_method not in MEASURED_METHODS:
            return None
        e_raw = SESSION.package_energy_exact_between(t_start, t_end)
        if e_raw is None:
            return None
        return float(e_raw) - float(baseline_pre_w) * dur
    except Exception:
        return None


def judge_trace_note(capture: Optional[JudgeEdgeCapture],
                     reasons: Sequence[str], source: str,
                     judge_window_s: object) -> str:
    """Nota D2 sui bordi del segmento del giudice.

    Perche' una nota e non una colonna: lo schema approvato non ha campi per
    le ragioni di scarto bordo-per-bordo, e aggiungerli senza una motivazione
    di protocollo sarebbe una colonna in piu' che nessuno consume. Qui finisce
    cio' che serve a un terzo per RICOSTRUIRE la scelta: quante chiamate avevano
    un bordo diretto, perche' le altre non l'avevano, l'estensione reale dei
    bordi e i valori grezzi del contatore ai due estremi (cosi' il ΔE diretto
    si ricalcola a mano, senza fidarsi del runner).

    Ritorna "" quando di chiamate non ce n'e': la riga allora dichiara solo il
    fonte-energia, e inventare una nota vuota non aggiunge nulla.
    """
    calls = list(getattr(capture, "calls", []) or [])
    if not calls:
        return ""
    direct = sum(1 for r in reasons if str(r).startswith("ok"))
    parts = [
        f"giudice: {direct}/{len(calls)} chiamate con bordo diretto; "
        f"fonte energia={source}",
        "esiti bordi: [" + "; ".join(str(r) for r in reasons) + "]",
    ]
    first = calls[0].get("start") or {}
    last = calls[-1].get("end") or {}
    t0 = first.get("t_counter_mono")
    if t0 is None:
        t0 = first.get("t_mono")
    t1 = last.get("t_counter_mono")
    if t1 is None:
        t1 = last.get("t_mono")
    if t0 is not None and t1 is not None:
        parts.append(
            f"estensione bordi={float(t1) - float(t0):.6f} s contro "
            f"judge_window_s={judge_window_s} s (il Δt dell'energia diretta e' "
            "la coppia di letture di ciascuna chiamata, non la somma delle "
            "finestre HTTP)")
    pwh0 = CasualWattLocalEnergyProfiler._edge_raw_value(first)
    pwh1 = CasualWattLocalEnergyProfiler._edge_raw_value(last)
    raw_unit = (CasualWattLocalEnergyProfiler._edge_raw_unit(first)
                or CasualWattLocalEnergyProfiler._edge_raw_unit(last) or "pWh")
    if pwh0 is not None or pwh1 is not None:
        # Un bordo senza grezzo si dichiara con "-", non si omette: la riga
        # deve dire quale dei due estremi non e' ricostruibile.
        parts.append(
            f"contatore grezzo {raw_unit}: "
            f"{pwh0 if pwh0 is not None else '-'} -> "
            f"{pwh1 if pwh1 is not None else '-'}")
    return "; ".join(parts)


def judge_fields(capture: Optional[JudgeEdgeCapture],
                 windows: Optional[Sequence[Tuple[float, float]]],
                 baseline_pre_w: float,
                 reasons_out: Optional[List[str]] = None) -> Dict[str, object]:
    """Campi del giudice: valore scelto, provenienza, interpolazione esplicita.

    Regola: se TUTTE le coppie di bordi sono leggibili si usa la differenza
    diretta; se una sola manca si usa la somma interpolata per l'intero
    segmento (``buffer-interp``), cosi' ``judge_energy_j`` non mescola due
    metodi in un numero solo. L'interpolazione resta comunque in
    ``judge_energy_interp_j``, verificabile accanto al valore scelto, e in
    entrambi i percorsi il valore grezzo con segno resta a disposizione del
    chiamante (``_judge_energy_raw_j``) per la nota D1.

    Cosa dice ciascuno dei campi di tempo, perche' sono tre grandezze diverse
    e scambiarle e' il modo piu' facile di mentire senza numeri:

    * ``judge_window_s`` — durata del SEGMENTO: somma delle finestre della
      chiamata HTTP registrate da ``llm_judge.LAST_WINDOWS``;
    * ``judge_edge_spread_s`` — costo della LETTURA: il massimo, fra tutte le
      IOCTL dei bordi del segmento, del tempo che una singola lettura del
      contatore e' durata. NON e' la durata del segmento e non e' lo
      ``edge_spread_s`` del blocco, che misura un tratto diverso (contatore +
      albero + cpu_times) e nasce da un altro bordo;
    * ``judge_emi_ts_{start,end}_100ns`` — gli istanti del RECORD del contatore
      ai due estremi del segmento, che sono la base con cui l'energia diretta e'
      stata sottratta.

    ``reasons_out``, quando il chiamante la passa, riceve per ogni chiamata
    l'esito del bordo diretto ("ok (base)" o la ragione del rifiuto): serve
    alla nota perche' un ``buffer-interp`` senza motivo non e' verificabile.
    """
    out: Dict[str, object] = {
        "judge_energy_j": "",
        "judge_window_s": "",
        "judge_energy_edge_source": "",
        "judge_energy_interp_j": "",
        "judge_edge_start_utc": "",
        "judge_edge_end_utc": "",
        "judge_edge_spread_s": "",
        "judge_emi_ts_start_100ns": "",
        "judge_emi_ts_end_100ns": "",
        "_judge_energy_raw_j": "",
    }
    wins = list(windows or ())
    calls = list(capture.calls) if capture is not None else []
    if not wins and not calls:
        return out

    if wins:
        out["judge_window_s"] = round(sum(b - a for a, b in wins), 6)
        interp_raw: List[float] = []
        for a, b in wins:
            v = _interp_judge_energy(a, b, baseline_pre_w)
            if v is None:
                interp_raw = []
                break
            interp_raw.append(float(v))
        if interp_raw:
            out["judge_energy_interp_j"] = round(sum(interp_raw), 6)

    direct: List[float] = []
    # Le finestre di LAST_WINDOWS e le chiamate del wrapper nascono insieme;
    # se le liste non coincidono si preferisce comunque la lettura diretta
    # delle chiamate effettivamente avvenute, dichiarando il numero usato in
    # nota. Il numero di finestre non e' una prova della copertura dei bordi.
    # Tutte le chiamate vengono valutate, non ci si ferma al primo rifiuto:
    # la nota deve dire quante bordo diretto c'era, non solo la prima che
    # mancava.
    for call in calls:
        value, reason = judge_direct_readiness(call, baseline_pre_w)
        if reasons_out is not None:
            reasons_out.append(reason)
        if value is not None:
            direct.append(float(value))
    direct_ok = bool(calls) and len(direct) == len(calls)

    if direct_ok:
        raw_sum = sum(direct)
        out["_judge_energy_raw_j"] = round(raw_sum, 6)
        out["judge_energy_j"] = round(max(raw_sum, 0.0), 6)
        out["judge_energy_edge_source"] = "direct-ioctl"
    elif out["judge_energy_interp_j"] != "":
        raw_sum = float(out["judge_energy_interp_j"])
        out["_judge_energy_raw_j"] = raw_sum
        out["judge_energy_j"] = round(max(raw_sum, 0.0), 6)
        out["judge_energy_edge_source"] = "buffer-interp"
    else:
        out["judge_energy_j"] = "N/A"
        out["judge_energy_edge_source"] = "unavailable"

    if calls:
        first = calls[0].get("start") or {}
        last = calls[-1].get("end") or {}
        out["judge_edge_start_utc"] = str(first.get("t_wall_utc", "") or "")
        out["judge_edge_end_utc"] = str(last.get("t_wall_utc", "") or "")
        # Costo della LETTURA, non durata del segmento: il massimo, fra tutte
        # le IOCTL del segmento, del tempo che una singola lettura del
        # contatore ha impiegato. La durata e' judge_window_s.
        out["judge_edge_spread_s"] = round(
            max(float(c.get("read_s") or 0.0) for c in calls), 6)
        c0 = first.get("counter") or {}
        c1 = last.get("counter") or {}
        ts0 = c0.get("ts_100ns") if isinstance(c0, dict) else None
        ts1 = c1.get("ts_100ns") if isinstance(c1, dict) else None
        out["judge_emi_ts_start_100ns"] = int(ts0) if ts0 is not None else ""
        out["judge_emi_ts_end_100ns"] = int(ts1) if ts1 is not None else ""
    return out


# ---------------------------------------------------------------------------
# Righe: mappatura condivisa del risultato energetico
# ---------------------------------------------------------------------------
ENERGY_ROW_FIELDS: Tuple[str, ...] = (
    # stesse grandezze che scrive il percorso locale di benchmark_unified
    "package_energy_j", "idle_power_w", "baseline_energy_j",
    "active_energy_j", "ollama_active_energy_j", "cpu_time_share",
    "package_energy_raw_j", "active_energy_raw_j", "active_valid",
    "cpu_time_share_raw", "share_anomaly",
    "gpu_available", "gpu_device_index", "gpu_board_energy_j",
    "gpu_energy_attributed_j", "gpu_utilization_share",
    "cpu_attribution_method", "gpu_attribution_method",
    "energy_calculation_method", "raw_start", "raw_end", "raw_unit",
    "domain", "sampling_interval_observed_s", "backend_version",
    "measurement_boundary", "idle_provenance", "package_window_source",
    "gpu_process_energy_j", "igpu_energy_j", "gpu_idle_provenance",
    "ollama_pids_used", "d_ollama_cpu_s", "d_busy_s", "n_samples_in_window",
    "cpu_share_window_s", "cpu_busy_capacity_cores",
    "worker_exit_in_window", "cpu_time_resolution_s",
    # P5 (#42): bordo, validita' e baseline di blocco
    "engine_tree_changed", "cpu_share_source", "cpu_time_share_valid",
    "edge_start_utc", "edge_end_utc", "edge_time_source", "edge_spread_s",
    "dt_W_s", "emi_ts_start_100ns", "emi_ts_end_100ns", "emi_edge_source",
    "baseline_pre_w",
)


def energy_fields(local, keep_alive_sent: str) -> Dict[str, object]:
    """Riga energetica da ``LocalEnergyResult`` (stessi nomi della produzione)."""
    return {
        "package_energy_j": local.package_energy_j,
        "idle_power_w": local.idle_power_w,
        "baseline_energy_j": local.baseline_energy_j,
        "active_energy_j": local.active_energy_j,
        "ollama_active_energy_j": local.ollama_active_energy_j,
        "cpu_time_share": local.cpu_time_share,
        "package_energy_raw_j": bu._na_or(local.package_energy_raw_j),
        "active_energy_raw_j": local.active_energy_raw_j,
        "active_valid": bool(local.active_valid),
        "cpu_time_share_raw": bu._na_or(local.cpu_time_share_raw),
        "share_anomaly": local.share_anomaly or "",
        "gpu_available": local.gpu_available,
        "gpu_device_index": (
            "" if local.gpu_device_index is None else local.gpu_device_index),
        "gpu_board_energy_j": local.gpu_board_energy_j,
        "gpu_energy_attributed_j": local.gpu_energy_attributed_j,
        "gpu_utilization_share": local.gpu_utilization_share,
        "cpu_attribution_method": local.cpu_attribution_method,
        "gpu_attribution_method": local.gpu_attribution_method,
        "energy_calculation_method": local.energy_calculation_method or "",
        "raw_start": bu._na_or(local.raw_start),
        "raw_end": bu._na_or(local.raw_end),
        "raw_unit": local.raw_unit or "",
        "domain": local.domain or "",
        "sampling_interval_observed_s": bu._na_or(
            local.sampling_interval_observed_s),
        "backend_version": local.backend_version or "",
        "measurement_boundary": local.measurement_boundary,
        "idle_provenance": local.idle_provenance or "",
        "package_window_source": local.package_window_source or "",
        "keep_alive_sent": keep_alive_sent or "",
        "gpu_process_energy_j": bu._na_or(local.gpu_process_energy_j),
        "igpu_energy_j": bu._na_or(local.igpu_energy_j),
        "gpu_idle_provenance": local.gpu_idle_provenance or "",
        "ollama_pids_used": local.ollama_pids_used or "",
        "d_ollama_cpu_s": local.d_ollama_cpu_s,
        "d_busy_s": local.d_busy_s,
        "n_samples_in_window": local.n_samples_in_window,
        "cpu_share_window_s": local.cpu_share_window_s,
        "cpu_busy_capacity_cores": local.cpu_busy_capacity_cores,
        "worker_exit_in_window": bool(local.worker_exit_in_window),
        "cpu_time_resolution_s": bu._na_or(local.cpu_time_resolution_s),
        "engine_tree_changed": bool(local.engine_tree_changed),
        "cpu_share_source": local.cpu_share_source or "",
        "cpu_time_share_valid": bool(local.cpu_time_share_valid),
        "edge_start_utc": local.edge_start_utc or "",
        "edge_end_utc": local.edge_end_utc or "",
        "edge_time_source": local.edge_time_source or "",
        "edge_spread_s": bu._na_or(local.edge_spread_s),
        "dt_W_s": local.dt_W_s,
        "emi_ts_start_100ns": bu._na_or(local.emi_ts_start_100ns),
        "emi_ts_end_100ns": bu._na_or(local.emi_ts_end_100ns),
        "emi_edge_source": local.emi_edge_source or "",
        "baseline_pre_w": bu._na_or(local.baseline_pre_w),
    }


def _tokens_total(p_tok, c_tok):
    if isinstance(p_tok, int) and isinstance(c_tok, int):
        return p_tok + c_tok
    return ""


def _tokens_rate(value, duration):
    if isinstance(value, int) and duration and float(duration) > 0:
        return round(value / float(duration), 3)
    return ""


# ---------------------------------------------------------------------------
# Un blocco: settling, P_pre, m richieste, settling, P_post
# ---------------------------------------------------------------------------
def run_block(model: str, prompt: Dict, *, run_id: str, session_id: str,
              batch_id: str, point_id: str, block_id: str,
              nonce_seq: int, profiler: CasualWattLocalEnergyProfiler,
              m: int = M_REQUESTS, num_predict: int = 160,
              num_ctx: int = NUM_CTX, temperature: float = config.DEFAULT_TEMPERATURE,
              timeout_s: float = config.DEFAULT_TIMEOUT_S,
              eval_mode_override: Optional[str] = None,
              block_kind: str = "campaign", pair_id: str = "",
              order_seed: str = "", dt_nominal_s: str = "",
              dt_tick_s: str = "", p_peak_w: str = "",
              stop_event: Optional[threading.Event] = None,
              cooldown: Optional[Dict[str, object]] = None,
              block_attempt: int = 1, replaced_block_id: str = "",
              on_log: Optional[Callable[[str], None]] = None
              ) -> Tuple[List[Dict], Dict[str, object]]:
    """Esegue un blocco P1.5 e ritorna (righe, riepilogo di blocco).

    Ordine: settling -> calibrazione pre (applicata) -> m richieste
    back-to-back con bordo prima/dopo -> settling -> calibrazione post
    (diagnostica). Le righe ricevono P_pre e i derivati del blocco solo dopo
    la calibrazione post, quindi ``baseline_post_w``/``dP`` sono presenti in
    ogni riga e ``P_post`` non viene mai sottratto.

    ``cooldown`` e' il dizionario prodotto da :func:`cooldown_to_baseline`
    prima del blocco, quando il blocco apre un punto nuovo (P1.5: il cooldown
    sta "fra i punti"). Il runner lo riceve gia' eseguito perche' il criterio
    guarda la baseline del punto precedente, che il blocco non conosce: chi
    organizza i punti decide il riferimento, il blocco lo dichiara. Da qui il
    flag ``cooldown_timeout`` e le note di riga.

    Emenda 8 (P1.6): ``block_attempt`` vale ``1`` per il blocco in piano e
    ``2`` per il sostituto, e ``replaced_block_id`` e' l'id del blocco
    invalidato che il sostituto rimpiazza (vuota per il blocco in piano). Le
    tre colonne ``block_attempt``/``invalid_reason``/``replaced_block_id``
    sono scritte SU OGNI riga e nel riepilogo: su un blocco completato
    ``invalid_reason`` resta vuota per costruzione, perche' la causa di
    invalidazione vive nel ``V4CounterFault`` che il chiamante intercetta e
    nel riepilogo d'invalidazione che il chiamante scrive. Un guasto tecnico
    del contatore solleva ``V4CounterFault`` (con le righe gia' prodotte
    attaccate, se il guasto e' post-richieste); qualunque altro errore
    solleva ``V4MeasurementError`` e ferma il run come prima.
    """
    if m < 1:
        raise ValueError("m deve essere >= 1")
    log = on_log or (lambda _m: None)
    cd_flag = cooldown_timeout_flag(cooldown)
    if cooldown and cooldown.get("ran"):
        log(f"[BLOCK {block_id}] cooldown: {cooldown.get('reason')}")

    settle_pre = SESSION.settle_idle()
    try:
        p_pre = float(SESSION.calibrate_idle())
    except Exception as exc:
        token = classify_calibration_exception(exc)
        msg = (f"calibrazione pre fallita per {point_id}/{block_id}: "
               f"{type(exc).__name__}: {exc}")
        if token:
            raise V4CounterFault(msg, token) from exc
        raise V4MeasurementError(msg) from exc
    # EMENDA 8 (P1.6), recepita 2026-10-26: qui stava la "discrepanza
    # dichiarata" fra il testo congelato (retry per singola finestra anomala,
    # protocollo:221-222) e il codice (invalidazione alla prima occorrenza).
    # L'emenda chiude la questione a favore del codice: il blocco si invalida
    # alla PRIMA occorrenza del guasto tecnico -- nessun retry dentro
    # `calibrate_idle` (che infatti non ce l'ha, energy/energy_session.py
    # :2547-2566) -- e la sostituzione e' di un BLOCCO COMPLETO, non della
    # singola finestra: tre finestre nuove con nonce nuovi, in una posizione
    # estratta dal resto del batch col seme registrato. Il retry per finestra
    # resta non implementato, e ora la scelta e' una decisione di protocollo,
    # non una lacuna del runner.
    raw_pre = list(getattr(SESSION, "_idle_reps", []) or ())
    reps_pre = _clean_reps(raw_pre)
    token = classify_reps(raw_pre, reps_pre)
    if token:
        raise V4CounterFault(
            f"baseline pre invalidata ({token}) per {point_id}/{block_id}: "
            f"grezza={raw_pre} pulita={reps_pre}", token)
    if len(reps_pre) != 3:
        raise V4MeasurementError(
            f"calibrazione pre con {len(reps_pre)} repliche, attese 3 "
            f"({point_id}/{block_id})")
    if any(r <= 0.0 for r in reps_pre):
        raise V4CounterFault(
            f"replica di baseline pre non positiva ({reps_pre}): contatore "
            f"non valido ({point_id}/{block_id})", "replica_non_positiva")
    log(f"[BLOCK {block_id}] P_pre={p_pre:.3f} W "
        f"reps={[round(r, 3) for r in reps_pre]} settle={settle_pre}")

    rows: List[Dict] = []
    for i in range(m):
        if stop_event is not None and stop_event.is_set():
            raise _Cancelled(f"stop richiesto durante {block_id}")
        sent, nonce, sha = build_prompt_v4(prompt, nonce_seq + i)
        capture = JudgeEdgeCapture()
        _lj.LAST_WINDOWS = []

        e0 = SESSION.read_measurement_edge()
        pids = [w.pid for w in e0["tree"]]
        resp_data = infer_v4(
            model, sent["text"], temperature, timeout_s,
            num_predict=num_predict, num_ctx=num_ctx)
        # Bordo di fine PRIMA della valutazione: la finestra energetica e'
        # quella della sola inferenza. Il giudice ha i propri bordi (D2).
        e1 = SESSION.read_measurement_edge()
        wd = worker_cpu_delta(e0["worker"], e1["worker"])
        # Il delta busy e' cumulativo e non dovrebbe mai decrescere: se lo fa,
        # il profiler vede 0 (anomalia dichiarata "d_busy=0") e il valore
        # grezzo resta nella nota, invece di sparire dentro il max().
        busy_raw = float(e1["busy"]) - float(e0["busy"])
        direct_busy = max(busy_raw, 0.0)

        evalres = evaluate_response(
            resp_data["text"], is_tool=False,
            ground_truth=prompt.get("ground_truth"),
            mode=bu._resolve_eval_mode(prompt, eval_mode_override),
            question=prompt["text"], evaluated_model=model,
            judge_fn=capture,
            answer_type=prompt.get("answer_type", "auto"),
        )
        local = profiler.profile_window(
            resp_data["_t0"], resp_data["_t1"],
            ollama_pids=pids,
            direct_cpu_delta=wd.d_ollama,
            direct_busy_delta=direct_busy,
            worker_exit_in_window=wd.worker_exit_in_window,
            edge_start=e0,
            edge_end=e1,
            baseline_pre_w=p_pre,
            engine_tree_changed=bool(wd.lost),
            tree_born=_identity_list(wd.born),
            tree_lost=_identity_list(wd.lost),
        )

        rec = bu._basic_record(
            run_id, session_id, model, model, "ollama", "local",
            pids[0] if pids else None, sent, bu.evalres_placeholder())
        p_tok = resp_data["prompt_tokens"]
        c_tok = resp_data["completion_tokens"]
        rec.update(
            model_response=resp_data["text"],
            timestamp_start=_utc_iso(resp_data["_wall_start"]),
            timestamp_end=datetime.now(timezone.utc).isoformat(
                timespec="seconds"),
            duration_s=resp_data["duration_s"],
            input_tokens=p_tok,
            output_tokens=c_tok,
            total_tokens=_tokens_total(p_tok, c_tok),
            tokens_per_second=_tokens_rate(c_tok, resp_data["duration_s"]),
            prefill_duration_s=round(resp_data.get("prefill_duration_s", 0.0), 6),
            decoding_duration_s=round(resp_data.get("decoding_duration_s", 0.0), 6),
            decoding_tokens_per_second=_tokens_rate(
                c_tok, resp_data.get("decoding_duration_s", 0.0)),
            tool_calls=0,
        )
        rec.update(energy_fields(local, resp_data["keep_alive_sent"]))
        rec.update(
            engine_tree_changed=bool(wd.lost),
            tree_identity_start=_identity_list(e0["tree"]),
            tree_identity_end=_identity_list(e1["tree"]),
            tree_born=_identity_list(wd.born),
            tree_lost=_identity_list(wd.lost),
            # Chiavi stabili (D3): il join non usa l'ordine delle righe.
            batch_id=batch_id,
            point_id=point_id,
            block_id=block_id,
            tokens_level=TOKENS_LEVEL,
            n_inferenze=1,
        )
        judge_reasons: List[str] = []
        rec.update(judge_fields(
            capture, getattr(_lj, "LAST_WINDOWS", []) or [], p_pre,
            reasons_out=judge_reasons))
        raw_judge = rec.pop("_judge_energy_raw_j", "")
        rec.update(
            eval_mode=evalres.eval_mode,
            is_correct=bu._na_or(evalres.is_correct),
            causal_accuracy=bu._na_or(evalres.causal_accuracy),
            explanation_quality=bu._na_or(evalres.explanation_quality),
            cosine_similarity=bu._na_or(evalres.cosine_sim),
            n_correct_links=bu._na_or(evalres.n_correct_links),
            acc_comp=bu._na_or(evalres.acc_comp),
            answer_type=getattr(evalres, "answer_type", "auto"),
            extracted_answer=bu._na_or(getattr(evalres, "extracted_answer", None)),
        )

        local_j = (local.ollama_active_energy_j
                   + local.gpu_energy_attributed_j)
        bu._finalize_energy_fields(rec, local_j, 0.0, 0.0, evalres)

        notes = list(local.notes) + list(evalres.notes)
        # La nota di _finalize_energy_fields dichiara quali metriche derivate
        # sono N/A: non va persa sovrascrivendo il campo.
        existing_note = rec.get("notes")
        if isinstance(existing_note, str) and existing_note:
            notes.append(existing_note)
        if isinstance(raw_judge, (int, float)) and float(raw_judge) < 0.0:
            notes.append(
                f"energia del giudice grezza {raw_judge} J < 0: "
                "judge_energy_j=0 convenzionale (stessa regola del percorso "
                "di produzione), il grezzo resta in questa nota")
        if busy_raw < 0.0:
            notes.append(
                f"d_busy grezzo {busy_raw:.6f} s < 0 fra i bordi (contatore "
                "cumulativo non monotono): al profiler e' passato 0.0, la "
                "quota e' dichiarata non valida con anomalia d_busy=0")
        notes.append(
            f"prompt_nonce={nonce}; prompt_sha256={sha}; "
            f"num_ctx={int(num_ctx)}; num_predict={int(num_predict)}")
        # P2.4: done_reason si registra SEMPRE, anche quando il motore non lo
        # riporta. Il ramo condizionale precedente lasciava la riga muta
        # sull'assenza, e l'assenza e' esattamente la classe
        # `termination_missing` che la richiesta la rende invalida.
        term = termination_fields(
            resp_data.get("done_reason"), p_tok, c_tok, num_predict,
            num_ctx=num_ctx)
        notes.append(termination_note(term))
        if not resp_data["tokens_valid"]:
            notes.append(
                "contatore token assente (prompt_eval_count/eval_count): "
                "nessuna stima (P2.6); i campi token restano vuoti e la riga "
                "non e' utilizzabile per le analisi sui token")
        judge_note = judge_trace_note(
            capture, judge_reasons,
            str(rec.get("judge_energy_edge_source", "")),
            rec.get("judge_window_s", ""))
        if judge_note:
            notes.append(judge_note)
        rec["notes"] = "; ".join(n for n in notes if n)
        rows.append(rec)
        log(f"[OK {block_id} #{i + 1}/{m}] {resp_data['duration_s']:.2f}s | "
            f"E_ollama={local.ollama_active_energy_j:.2f} J "
            f"valid={local.cpu_time_share_valid} "
            f"source={local.cpu_share_source}")

    settle_post = SESSION.settle_idle()
    try:
        p_post = float(SESSION.calibrate_idle())
    except Exception as exc:
        token = classify_calibration_exception(exc)
        msg = (f"calibrazione post fallita per {point_id}/{block_id}: "
               f"{type(exc).__name__}: {exc}")
        if token:
            # Le m richieste SONO gia' avvenute: le righe restano evidenze
            # (append-only, D3) e il chiamante le esporta con la nota di
            # invalidazione; il blocco in quanto misurazione e' invalidato.
            raise V4CounterFault(msg, token, rows=rows) from exc
        raise V4MeasurementError(msg) from exc
    raw_post = list(getattr(SESSION, "_idle_reps", []) or ())
    reps_post = _clean_reps(raw_post)
    token = classify_reps(raw_post, reps_post)
    if token:
        raise V4CounterFault(
            f"baseline post invalidata ({token}) per {point_id}/{block_id}: "
            f"grezza={raw_post} pulita={reps_post}", token, rows=rows)
    if len(reps_post) != 3:
        raise V4MeasurementError(
            f"calibrazione post con {len(reps_post)} repliche, attese 3 "
            f"({point_id}/{block_id})")
    base = block_baseline(reps_pre, reps_post)

    # Δt̄_W,b: MEDIA aritmetica delle durate del blocco (F.11), sul campo
    # duration_s dichiarato dal quinto emendamento. Non e' la mediana delle
    # Δt_W: le due letture danno numeri diversi e il protocollo ne scrive una
    # sola.
    mean_dt, mean_dt_motivo = block_mean_duration_s(rows, m)
    bw = base.get("budget_base_w", "")
    for r in rows:
        r["baseline_post_w"] = base["baseline_post_w"]
        r["post_windows_w"] = base["post_windows_w"]
        r["dP"] = base["dP"]
        r["half_range_pre_w"] = base["half_range_pre_w"]
        r["half_drift_w"] = base["half_drift_w"]
        r["budget_base_w"] = bw
        # Emenda 8 (P1.6): le tre colonne nuove su ogni riga del blocco.
        # invalid_reason qui e' VUOTA per costruzione: un blocco che arriva
        # fin qui non e' stato invalidato; la riga d'invalidazione (il
        # riepilogo scritto dal runner sul guasto) porta il token.
        r["block_attempt"] = int(block_attempt)
        r["invalid_reason"] = ""
        r["replaced_block_id"] = replaced_block_id
        # F.4 per richiesta: senza la Δt_W della richiesta il budget non si
        # puo' calcolare, e lo zero sarebbe un "non consuma" inventato.
        dt_row = r.get("dt_W_s")
        r["budget_base_j"] = (
            budget_base_j(dt_row, bw)
            if (bw != "" and dt_row not in (None, "")) else "")
        r["settle_pre_s"] = "" if settle_pre is None else settle_pre
        r["settle_post_s"] = "" if settle_post is None else settle_post

    negatives = sum(
        1 for r in rows
        if (isinstance(r.get("active_energy_raw_j"), (int, float))
            and float(r["active_energy_raw_j"]) < 0.0)
        or (isinstance(r.get("package_energy_raw_j"), (int, float))
            and float(r["package_energy_raw_j"]) < 0.0))
    summary: Dict[str, object] = {
        "batch_id": batch_id,
        "point_id": point_id,
        "block_id": block_id,
        "block_kind": block_kind,
        "pair_id": pair_id,
        "order_seed": order_seed,
        "dt_nominal_s": dt_nominal_s,
        "dt_tick_s": dt_tick_s,
        "p_peak_w": p_peak_w,
        "settle_pre_s": "" if settle_pre is None else settle_pre,
        "settle_post_s": "" if settle_post is None else settle_post,
        "baseline_pre_w": base["baseline_pre_w"],
        "baseline_post_w": base["baseline_post_w"],
        "pre_windows_w": base["pre_windows_w"],
        "post_windows_w": base["post_windows_w"],
        "pre_range_w": base["pre_range_w"],
        "dP": base["dP"],
        "half_range_pre_w": base["half_range_pre_w"],
        "half_drift_w": base["half_drift_w"],
        "budget_base_w": base["budget_base_w"],
        # F.4 per richiesta; nel riepilogo la stessa grandezza su `Δt̄_W,b`,
        # la MEDIA aritmetica delle durate del blocco (F.11, protocollo:1631),
        # dichiarata come derivata e non come misura indipendente.
        "budget_base_j": (
            budget_base_j(mean_dt, bw) if (mean_dt != "" and bw != "") else ""),
        # Campi di analisi: non li calcola il runner.
        "u_edge_j": "", "budget_fit_j": "", "budget_pred_j": "",
        "u_bias_j": "", "bias_w": "", "z_resid": "",
        # Cooldown P1.5: "true"/"false" solo se eseguito; vuoto al primo punto
        # del run (nessun P_pre di riferimento) o con riferimento non valido.
        "cooldown_timeout": cd_flag,
        "negative_increment": "true" if negatives else "false",
        # Sostituzioni di P3.12: non gestite qui.
        "design_deviation": "", "design_deviation_count": "",
        "r_A": "", "r_B": "",
        # Emenda 8 (P1.6): in coda, stesso ordine delle righe grezze. Un
        # riepilogo che arriva fin qui e' di un blocco completo: tentativo e
        # ids del piano, invalid_reason vuota.
        "block_attempt": int(block_attempt),
        "invalid_reason": "",
        "replaced_block_id": replaced_block_id,
    }
    if settle_pre is None:
        for r in rows:
            r["notes"] = (r.get("notes", "") + "; " if r.get("notes") else "") + (
                "settling pre al tetto (settle_pre_s vuoto): stabilita' non "
                "osservata, non un tempo inventato")
    if settle_post is None:
        for r in rows:
            r["notes"] = (r.get("notes", "") + "; " if r.get("notes") else "") + (
                "settling post al tetto (settle_post_s vuoto): stabilita' non "
                "osservata")
    # `Δt̄_W,b` non e' una colonna (P6.5:2178 la chiama "quantita' derivata: la
    # media per blocco della duration_s gia' prevista"), ma il budget di blocco
    # si ricava solo da li': senza il valore nella nota, un terzo non puo'
    # rifare il prodotto `budget_base_w x Δt̄_W,b` che legge in block_summary.
    if mean_dt == "":
        dt_note = f"budget_base_j di blocco non calcolabile: {mean_dt_motivo}"
    else:
        dt_note = (
            "budget_base_j di blocco = budget_base_w x Δt̄_W,b (F.11); "
            f"Δt̄_W,b={mean_dt} s, media aritmetica di {m} duration_s di "
            "richiesta (non la mediana)")
    for r in rows:
        r["notes"] = ((r.get("notes", "") + "; ") if r.get("notes")
                      else "") + dt_note
    if cooldown and cooldown.get("ran"):
        cd_note = (
            "cooldown P1.5: " + str(cooldown.get("reason")) +
            f" [target_pre_w={cooldown.get('target_pre_w')} W, "
            f"waited_s={cooldown.get('waited_s')}, "
            f"campioni={cooldown.get('samples')}, "
            f"letture mancanti={cooldown.get('missing_reads')}]")
        for r in rows:
            r["notes"] = ((r.get("notes", "") + "; ") if r.get("notes")
                          else "") + cd_note
    if base["pre_range_w"] != "" and float(base["pre_range_w"]) > 1.0:
        for r in rows:
            r["notes"] = (r.get("notes", "") + "; " if r.get("notes") else "") + (
                f"pre_range_w={base['pre_range_w']} W > 1,0 W: pre_unstable "
                "true (P1.6); il flag non invalida da solo il blocco, entra in "
                "half_range_pre_w")
    log(f"[BLOCK {block_id}] P_post={p_post:.3f} W dP={base['dP']} "
        f"pre_range={base['pre_range_w']} budget={base['budget_base_w']} W")
    return rows, summary


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def _slug(text: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "-"
                   for c in str(text)).strip("-")


def _ollama_runtime_info(model: str) -> Tuple[str, str]:
    """(versione, digest) del motore e del modello; "" se non leggibili."""
    version = ""
    digest = ""
    try:
        r = requests.get(f"{config.OLLAMA_API_URL}/api/version", timeout=5)
        if r.status_code == 200:
            version = str((r.json() or {}).get("version", "") or "")
    except Exception:
        version = ""
    try:
        r = requests.post(f"{config.OLLAMA_API_URL}/api/show",
                          json={"model": model}, timeout=10)
        if r.status_code == 200:
            digest = str((r.json() or {}).get("digest", "") or "")
    except Exception:
        digest = ""
    return version, digest


def run_v4_benchmark(
    local_models: Sequence[str],
    prompts: Sequence[Dict],
    *,
    m: int = M_REQUESTS,
    blocks_per_point: int = 3,
    num_predict: int = 160,
    num_ctx: int = NUM_CTX,
    temperature: float = config.DEFAULT_TEMPERATURE,
    timeout_s: float = config.DEFAULT_TIMEOUT_S,
    eval_mode_override: Optional[str] = None,
    batch_id: Optional[str] = None,
    block_kind: str = "campaign",
    pair_id: str = "",
    order_seed: str = "",
    dt_nominal_s: str = "",
    dt_tick_s: str = "",
    p_peak_w: str = "",
    on_log: Optional[Callable[[str], None]] = None,
    stop_event: Optional[threading.Event] = None,
    results_path: Optional[Path] = None,
    block_summary_path: Optional[Path] = None,
    max_invalidated_blocks: Optional[int] = None,
    substitution_seed: Optional[str] = None,
) -> Dict:
    """Esegue la campagna v4 (blocchi P1.5) e scrive righe + riepiloghi.

    ``blocks_per_point`` default 3 e' la struttura di D10 (tre batch
    temporali). Il valore usato e' un parametro del run e non del singolo
    blocco: non ha una colonna in ``block_summary.csv``, quindi viene
    registrato nel run metadata (``notes``) insieme a ``m``, ``num_ctx`` e
    ``num_predict``. Il chiamante puo' ridurlo per collaudi, ma il numero
    effettivo resta scritto li'.

    ``stop_event`` interrompe fra un blocco e l'altro: il blocco gia'
    iniziato viene completato, e il riepilogo esce con ``cancelled=True``
    invece che come errore. Le righe gia' scritte restano (append-only, D3).

    Cooldown (P1.5, protocollo_v4_20261024.md:210-212): corre SOLO sul blocco
    ``k == 0`` di ogni punto, perche'
    il protocollo lo colloca "fra i punti", non fra i blocchi. Il testo
    congelato non dice **quale** ``P_pre`` sia il riferimento, e al confine fra
    due punti ne esiste uno solo misurabile: quello del blocco appena chiuso
    (il ``P_pre`` del punto che sta aprendo non e' ancora stato calibrato --
    viene dopo il cooldown). Qui si usa quindi l'ultima ``baseline_pre_w``
    completata. Il primo punto del run non ha cooldown perche' non ha
    riferimento: la cella ``cooldown_timeout`` resta vuota, non "false".

    Emenda 8 (P1.6) -- sostituzione del blocco invalidato. I piani dei blocchi
    (modello x punto x k) diventano una LISTA PIATTA eseguita con un cursore,
    perche' la posizione del sostituto deve poter cadere fra i blocchi che
    vengono DOPO quello fallito: un ciclo annidato non puo' accodare in mezzo.
    Regola vigente, implementata qui e NON nel blocco:

    1. ``V4CounterFault`` (guasto tecnico del contatore in una finestra di
       baseline) invalida il blocco alla prima occorrenza; ``nonce_seq`` avanza
       comunque di ``m`` (i nonce del blocco fallito sono consumati e
       dichiarati, il sostituto non li riusa);
    2. il tentativo ``1`` produce UN SOLO sostituto dello stesso punto di
       disegno (``block_id`` con suffisso ``__s2``, ``block_attempt=2``),
       inserito in ``rng.randrange(idx + 1, len(piano) + 1)`` con
       ``rng = random.Random(seme)``: posizione fra i blocchi RESTANTI, coda
       se il fallito era l'ultimo. Seme e posizione finiscono nel log e nel
       run metadata, perche' un ordine non riproducibile e' come un esito
       scelto a posteriori;
    3. un secondo guasto sul tentativo ``2`` dichiara il blocco "mancante"
       (contatore ``missing_blocks``) e si prosegue: non c'e' una terza
       chance;
    4. il blocco invalidato lascia una RIGA in ``block_summary.csv`` (chiavi
       d'identita', tentativo, ``invalid_reason``, posizione relativa) con le
       celle di misura vuote: un'invalidazione visibile solo nel log non e'
       recuperabile da un terzo;
    5. oltre il tetto ``max_invalidated_blocks`` (K) il run si FERMA con un
       messaggio, senza sollevare: i dati scritti restano e l'interruzione e'
       dichiarata nel metadata;
    6. K e il seme non hanno default: senza entrambi il runner SI RIFIUTA di
       partire (``ValueError`` prima di toccare hardware o sessione).

    Nessun altro errore attiva la sostituzione: un errore di qualita'
    (pre_unstable, ``pre_range_w`` alto, drift) resta un FLAG sul blocco
    completo, e un errore non-tecnico (backend assente, HTTP, incongruenza
    dell'interfaccia) ferma il run come prima.
    """
    log = on_log or (lambda _m: None)
    models = list(local_models or [])
    points = list(prompts or [])
    if not models:
        raise ValueError("nessun modello locale selezionato")
    if not points:
        raise ValueError("nessuna richiesta selezionata")
    if blocks_per_point < 1:
        raise ValueError("blocks_per_point deve essere >= 1")
    # Emenda 8 (P1.6): K e seme si risolvono PRIMA di qualsiasi altra cosa.
    # Se mancano il runner non parte, e non parte soprattutto prima di toccare
    # la sessione: un run avviato con un tetto inventato sarebbe un disegno
    # diverso da quello deciso, scoperto solo dopo i dati.
    k_max, seed, seed_prov = resolve_emenda8_params(
        max_invalidated_blocks, substitution_seed)

    results_path = Path(results_path or DEFAULT_RESULTS_PATH)
    block_summary_path = Path(block_summary_path or DEFAULT_BLOCK_SUMMARY_PATH)
    batch = batch_id or uuid.uuid4().hex[:12]
    run_id = uuid.uuid4().hex
    session_id = uuid.uuid4().hex
    started_wall = datetime.now(timezone.utc)

    profiler = CasualWattLocalEnergyProfiler()
    was_running = SESSION.running
    rows_written = 0
    blocks_written = 0
    errors = 0
    nonce_seq = 0
    # Riferimento del cooldown (P1.5): l'ultima baseline_pre_w completata.
    last_pre_w: Optional[float] = None
    cooldown_log: List[str] = []
    runtime: Dict[str, Tuple[str, str]] = {
        model: ("", "") for model in models}
    summary = {
        "run_id": run_id, "session_id": session_id, "batch_id": batch,
        "records": 0, "blocks": 0, "errors": 0, "cancelled": False,
        # Emenda 8 (P1.6): contatori di invalidazione, tutti dichiarati.
        "invalidated_blocks": 0, "missing_blocks": 0, "substitutions": 0,
        "stopped_by_k": "",
        "results_csv": str(results_path),
        "block_summary_csv": str(block_summary_path),
    }
    # Piano dei blocchi: lista PIATTA (modello x punto x k), perche' il
    # sostituto va potersi inserire fra i blocchi che vengono dopo, e un
    # ciclo annidato non ha un "dopo" fra un punto e l'altro. L'identita'
    # del punto (point_id) e calcolata qui una volta sola, come faceva il
    # ciclo annidato.
    plan: List[Dict[str, object]] = []
    for model in models:
        for prompt in points:
            point_id = f"{_slug(model)}__{_slug(prompt['id'])}"
            for k in range(blocks_per_point):
                plan.append({"model": model, "prompt": prompt,
                             "point_id": point_id, "k": k,
                             "attempt": 1, "replaced": ""})
    rng = random.Random(seed)
    runtime_done: set = set()
    invalidated = 0
    missing_ids: List[str] = []
    substitution_log: List[str] = []
    stopped_by_k = ""
    failure: Optional[BaseException] = None
    try:
        if not was_running:
            SESSION.start()
            time.sleep(SESSION.interval_s * 2)
        cpu_res = CasualWattLocalEnergyProfiler.probe_cpu_time_resolution()
        SESSION.cpu_time_resolution_s = cpu_res
        log(f"Sorgente energia package CPU: {SESSION.source_method}")
        log("Risoluzione osservata dei cpu_times: "
            + (f"{cpu_res:.4f} s" if cpu_res else "non misurabile"))

        idx = 0
        while idx < len(plan):
            entry = plan[idx]
            if stop_event is not None and stop_event.is_set():
                raise _Cancelled("stop richiesto fra due blocchi")
            model = str(entry["model"])
            if model not in runtime_done:
                version, digest = _ollama_runtime_info(model)
                runtime[model] = (version, digest)
                runtime_done.add(model)
            point_id = str(entry["point_id"])
            k = int(entry["k"])
            attempt = int(entry["attempt"])
            block_id = (f"{point_id}__b{k + 1:02d}" if attempt == 1 else
                        f"{point_id}__b{k + 1:02d}__s2")
            cooldown = None
            if k == 0:
                cooldown = cooldown_to_baseline(
                    last_pre_w, stop_event=stop_event)
                if cooldown.get("ran"):
                    cooldown_log.append(
                        f"{point_id}: target_pre_w="
                        f"{cooldown['target_pre_w']} W, "
                        f"waited_s={cooldown['waited_s']}, "
                        f"cooldown_timeout="
                        f"{cooldown_timeout_flag(cooldown)}")
                log(f"[COOLDOWN -> {point_id}] {cooldown['reason']}")
            try:
                rows, block_rec = run_block(
                    model, entry["prompt"],
                    run_id=run_id, session_id=session_id, batch_id=batch,
                    point_id=point_id, block_id=block_id,
                    nonce_seq=nonce_seq, profiler=profiler,
                    m=m, num_predict=num_predict, num_ctx=num_ctx,
                    temperature=temperature, timeout_s=timeout_s,
                    eval_mode_override=eval_mode_override,
                    block_kind=block_kind, pair_id=pair_id,
                    order_seed=order_seed, dt_nominal_s=dt_nominal_s,
                    dt_tick_s=dt_tick_s, p_peak_w=p_peak_w,
                    stop_event=stop_event, cooldown=cooldown, on_log=log,
                    block_attempt=attempt,
                    replaced_block_id=str(entry["replaced"]),
                )
            except V4CounterFault as fault:
                # Emenda 8 (P1.6): prima occorrenza -> invalidazione senza
                # retry; il nonce e' consumato comunque (il sostituto non
                # riusa nonce ambigui), e il blocco lascia una riga di
                # riepilogo con il token del guasto.
                nonce_seq += m
                invalidated += 1
                summary["invalidated_blocks"] = invalidated
                for r in fault.rows:
                    r["block_attempt"] = attempt
                    r["invalid_reason"] = fault.invalid_reason
                    r["replaced_block_id"] = str(entry["replaced"])
                    r["notes"] = ((r.get("notes", "") + "; ")
                                  if r.get("notes") else "") + (
                        f"blocco invalidato P1.6/Emenda 8 "
                        f"(invalid_reason={fault.invalid_reason}): righe "
                        "conservate append-only come evidenza, NON entrano "
                        "in nessuna analisi")
                if fault.rows:
                    rows_written += export_results_csv(
                        fault.rows, results_path, mode="a")
                    summary["records"] = rows_written
                invalid_rec = {
                    "batch_id": batch, "point_id": point_id,
                    "block_id": block_id, "block_kind": block_kind,
                    "pair_id": pair_id, "order_seed": order_seed,
                    "dt_nominal_s": dt_nominal_s, "dt_tick_s": dt_tick_s,
                    "p_peak_w": p_peak_w,
                    # Il cooldown, se eseguito, e' un fatto del run: resta.
                    "cooldown_timeout": cooldown_timeout_flag(cooldown),
                    "block_attempt": attempt,
                    "invalid_reason": fault.invalid_reason,
                    "replaced_block_id": str(entry["replaced"]),
                }
                blocks_written += export_summary_csv(
                    [invalid_rec], block_summary_path,
                    BLOCK_SUMMARY_COLUMNS, mode="a")
                summary["blocks"] = blocks_written
                log(f"[BLOCCO INVALIDATO {block_id}] "
                    f"invalid_reason={fault.invalid_reason}: {fault}")
                if invalidated > k_max:
                    stopped_by_k = (
                        f"tetto K={k_max} di blocchi invalidati per batch "
                        f"superato ({invalidated}): il run si ferma qui, i "
                        "dati scritti restano")
                    summary["stopped_by_k"] = stopped_by_k
                    log(f"[ARRESTO] {stopped_by_k}")
                    break
                if attempt == 2:
                    # Secondo guasto tecnico sullo STESSO punto di disegno:
                    # il blocco e' "mancante", non c'e' una terza chance.
                    missing_ids.append(block_id)
                    summary["missing_blocks"] = len(missing_ids)
                    log(f"[MANCANTE] {block_id}: secondo guasto tecnico sul "
                        "sostituto, il punto resta scoperto")
                    idx += 1
                    continue
                sub_bid = f"{point_id}__b{k + 1:02d}__s2"
                sub_entry = {"model": model, "prompt": entry["prompt"],
                             "point_id": point_id, "k": k, "attempt": 2,
                             "replaced": block_id}
                pos = rng.randrange(idx + 1, len(plan) + 1)
                plan.insert(pos, sub_entry)
                substitution_log.append(
                    f"{block_id} -> sostituto {sub_bid} "
                    f"in posizione {pos} di {len(plan) - 1} "
                    f"(seme={seed!r}, invalid_reason={fault.invalid_reason})")
                summary["substitutions"] = len(substitution_log)
                log(f"[SOSTITUZIONE] seme={seed!r} posizione={pos} "
                    f"({block_id} -> {sub_bid})")
                idx += 1
                continue
            nonce_seq += m
            b_pre = block_rec.get("baseline_pre_w")
            if isinstance(b_pre, (int, float)) and math.isfinite(float(b_pre)):
                last_pre_w = float(b_pre)
            rows_written += export_results_csv(
                rows, results_path, mode="a")
            blocks_written += export_summary_csv(
                [block_rec], block_summary_path,
                BLOCK_SUMMARY_COLUMNS, mode="a")
            summary["records"] = rows_written
            summary["blocks"] = blocks_written
            idx += 1
    except _Cancelled as exc:
        summary["cancelled"] = True
        log(f"[ANNULLATO] {exc}")
    except BaseException as exc:  # noqa: BLE001 - si registra e si rilancia
        errors += 1
        failure = exc
        summary["errors"] = errors
        log(f"[ERRORE] {type(exc).__name__}: {exc}")
    finally:
        if not was_running:
            SESSION.stop()

    finished_wall = datetime.now(timezone.utc)
    notes = [
        "runner=benchmark_v4",
        f"m={m}",
        f"blocks_per_point={blocks_per_point}",
        f"num_ctx={int(num_ctx)}",
        f"num_predict={int(num_predict)}",
        f"keep_alive={KEEP_ALIVE}",
        # Il ghiaccio dello schema di P5 non ha una colonna per il percorso dei
        # riepiloghi di blocco ne' per l'identita' del giudice: ``results_csv``
        # ce l'ha, gli altri no. Si registrano qui, perche' un riepilogo di cui
        # non si conosce il percorso e' un artefatto non rigenerabile, e perche'
        # le colonne ``judge_*`` della riga senza ``judge_model`` non dicono
        # quale modello ha prodotto il punteggio.
        f"block_summary_csv={block_summary_path}",
        f"judge_model={_lj.judge_model_name()}",
        "baseline: per blocco (baseline_pre_w/post e repliche nelle righe e "
        "in block_summary.csv)",
        # Criterio e riferimenti del cooldown, perche' la sola colonna
        # cooldown_timeout non dice contro quale P_pre si era controllato.
        f"cooldown P1.5: media {COOLDOWN_WINDOW_S:.0f} s entro "
        f"{COOLDOWN_TOLERANCE_W} W da P_pre per {COOLDOWN_SUSTAIN_S:.0f} s, "
        f"tetto {COOLDOWN_CAP_S:.0f} s, passo {COOLDOWN_STEP_S:.0f} s; "
        "riferimento = baseline_pre_w dell'ultimo blocco completato; "
        "primo punto del run senza cooldown",
    ]
    if cooldown_log:
        notes.append("cooldown: " + " | ".join(cooldown_log))
    else:
        notes.append("cooldown: nessun confine fra punti con riferimento "
                     "disponibile (nessun cooldown eseguito)")
    # Emenda 8 (P1.6): il tetto, il seme e le posizioni estratte dal sorteggio
    # stanno nel metadata perche' non hanno colonne, e un ordine dei blocchi
    # non riproducibile e' come una scelta fatta dopo i dati.
    notes.append(
        f"emenda 8 P1.6: K={k_max}, seme={seed!r} (provenienza: {seed_prov})")
    if substitution_log:
        notes.append("sostituzioni: " + " | ".join(substitution_log))
    if missing_ids:
        notes.append("blocchi mancanti (secondo guasto tecnico sul "
                     "sostituto): " + ", ".join(missing_ids))
    if runtime:
        notes.append("modelli: " + "; ".join(
            f"{mdl} digest={dg or '-'} ollama={vr or '-'}"
            for mdl, (vr, dg) in runtime.items()))
    if failure is not None:
        notes.append(f"interrotto: {type(failure).__name__}: {failure}")
    elif summary["cancelled"]:
        notes.append("cancelled")
    elif stopped_by_k:
        # Il tetto K e' un arresto voluto dal disegno, non un errore: i dati
        # restano e il motivo e' dichiarato, non camuffato da "completed".
        notes.append(stopped_by_k)
    else:
        notes.append("completed")
    meta = {
        "run_id": run_id,
        "started_at": started_wall.isoformat(timespec="seconds"),
        "finished_at": finished_wall.isoformat(timespec="seconds"),
        "app_version": APP_VERSION,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}",
        "cpu_model": platform.processor() or platform.machine(),
        "cpu_logical_cores": platform.os.cpu_count(),
        "gpu_nvml_name": SESSION._gpu.name or "",
        "gpu_nvml_available": SESSION._gpu.available,
        "cpu_energy_source_method": SESSION.source_method,
        "cpu_energy_source_notes": "; ".join(SESSION.source_notes),
        "ollama_endpoint": config.OLLAMA_API_URL,
        "ollama_models_selected": ";".join(models),
        "cloud_models_selected": "",
        "num_prompts": len(points),
        "test_source_mode": "external",
        "test_source_csv": "",
        "test_source_items_total": len(points),
        "test_ground_truth_count": sum(
            1 for p in points if p.get("ground_truth")),
        "temperature": temperature,
        "timeout_s": timeout_s,
        # Non esiste una sola baseline per run: la P_pre e' per blocco.
        "idle_power_w": "",
        "idle_calibrated_at": getattr(SESSION, "calibrated_at", "") or "",
        "ecologits_version": bu._ecologits_version(),
        "electricity_maps_used": False,
        "records_written": rows_written,
        "results_csv": str(results_path),
        "notes": "; ".join(notes),
        "ollama_keep_alive": KEEP_ALIVE,
    }
    try:
        write_run_metadata(meta, config.CSV_RUN_METADATA_PATH)
    except Exception as exc:  # noqa: BLE001 - il run e' gia' avvenuto
        # Le righe sono scritte e il run e' avvenuto: perdere il solo file di
        # metadati non giustifica buttare via i dati, ma non si finge che sia
        # andata: l'errore resta nel riepilogo e nel log.
        summary["metadata_error"] = f"{type(exc).__name__}: {exc}"
        log(f"[AVVISO] run metadata non scritti: {summary['metadata_error']}")
    summary["runtime"] = runtime
    if failure is not None:
        raise failure
    return summary


# ---------------------------------------------------------------------------
# CLI (la campagna passa dal chiamante; qui c'e' un ingresso minimo)
# ---------------------------------------------------------------------------
def _parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Runner v4 CasualWatt: blocchi P1.5 (settle, m richieste, "
                    "settle) con bordi di misura e schema P5.")
    p.add_argument("--model", action="append", required=True,
                   help="modello Ollama (ripetibile)")
    p.add_argument("--csv", default=None,
                   help="CSV delle richieste (id,text[,ground_truth])")
    p.add_argument("--num-prompts", type=int, default=None)
    p.add_argument("--m", type=int, default=M_REQUESTS)
    p.add_argument("--blocks", type=int, default=3)
    p.add_argument("--num-predict", type=int, default=160)
    p.add_argument("--num-ctx", type=int, default=NUM_CTX)
    p.add_argument("--temperature", type=float, default=config.DEFAULT_TEMPERATURE)
    p.add_argument("--timeout", type=float, default=config.DEFAULT_TIMEOUT_S)
    # Emenda 8 (P1.6): nessun default qui. Lasciare il default a None vuol
    # dire far cadere il ValueError di "rifiuto di partire" con il messaggio
    # in chiaro; mettere un numero avrebbe inventato un tetto di disegno.
    p.add_argument("--max-invalidated-k", type=int, default=None,
                   help=f"tetto K di blocchi invalidati per batch "
                        f"(Emenda 8; obbligatorio, o env "
                        f"{ENV_MAX_INVALIDATED_BLOCKS})")
    p.add_argument("--substitution-seed", default=None,
                   help=f"seme per la posizione dei sostituti (Emenda 8; "
                        f"obbligatorio, o env {ENV_SUBSTITUTION_SEED})")
    return p.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    from test_source import load_test_source

    prompts_all, src_err = load_test_source(
        mode="csv" if args.csv else "default",
        csv_path=args.csv,
        fallback_config=True,
    )
    if not prompts_all:
        print(f"Sorgente test vuota ({src_err})", file=sys.stderr)
        return 2
    prompts = list(prompts_all)
    if args.num_prompts:
        prompts = prompts[:max(int(args.num_prompts), 1)]
    try:
        out = run_v4_benchmark(
            args.model, prompts,
            m=args.m, blocks_per_point=args.blocks,
            num_predict=args.num_predict, num_ctx=args.num_ctx,
            temperature=args.temperature, timeout_s=args.timeout,
            max_invalidated_blocks=args.max_invalidated_k,
            substitution_seed=args.substitution_seed,
            on_log=print,
        )
    except Exception as exc:
        print(f"Run interrotto: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    print(f"Righe: {out['records']} | blocchi: {out['blocks']} | "
          f"errori: {out['errors']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
