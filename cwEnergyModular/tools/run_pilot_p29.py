# -*- coding: utf-8 -*-
"""tools/run_pilot_p29.py — il pilota P2.9 eseguito sul runner v4.

Perche' esiste. P2.9 (protocollo_v4_20261024.md:841-856) prescrive tre prove
(A: semantica di `done_reason`; B: cache, tre richieste identiche contro tre a
nonce iniziale; C: contesto al massimo `N_in` del disegno) e P6.2 (`:2382-2393`)
aggiunge un vincolo di esecuzione: il pilota gira con **lo stesso runner** della
campagna, e ogni blocco esegue la sequenza completa di P1.5, altrimenti le prove
non producono le prime terne reali (`half_range_pre_w`, `u_within,b`). Un
harness diverso lascerebbe P1.7 e P6.4 senza dati, ed e' esattamente cio' che
era successo: il pilota del 06-11-2026 passo' dal runner legacy, che riscrive il
CSV a ogni run (`benchmark_unified.py:1494`, `mode="w"`), e le sue durate non
esistono piu'. P4.4 requisito 5 (`:1481-1486`) fissa `dt_nominal_s` come 3 x la
mediana della durata di richiesta **misurata nel pilota di P2**: senza righe
misurate quel numero non ha una provenienza, e questo strumento la produce.

Cosa fa, in tre passi separati perche' la dichiarazione viene prima dei dati:

  1. ``--plan`` scrive ``plan.json`` nell'archivio tracciato: prompt esatti,
     geometria di ogni braccio, ordine, tolleranze delle verifiche e impronte
     sha256. Se un piano c'e' gia' e differisce, non lo sovrascrive: un disegno
     che cambia dopo i dati non e' un pilota.
  2. ``--execute`` esegue i sei blocchi (A1, A2, A3, B-identico, B-nonce, C)
     attraverso ``benchmark_v4.run_v4_benchmark``, una invocazione per braccio,
     in una cartella di ``results/`` dedicata (il runner appende, ma un secondo
     tentativo nella stessa cartella mescolerebbe due piloti: se trova righe si
     ferma). Raccoglie anche la riga di run metadata di ogni invocazione, che
     porta lo stato macchina di P1.4 e i conteggi dei warm-up.
  3. ``--analyze`` verifica A/B/C, calcola le terne per blocco, copia i CSV
     nell'archivio tracciato con lo sha256 e scrive ``dt_nominal_frozen.json``.

Le tre verifiche di P2.9, come sono lette qui:

  - A: A1 e A2 devono chiudere con ``done_reason=length``, classe
    ``cap_reached`` e ``N_out_actual == num_predict``; A3 con
    ``done_reason=stop`` e classe ``eos`` (non ``eos_at_cap``: una EOS alla
    soglia non distingue la fine naturale dal tetto, che e' proprio cio' che la
    prova deve mostrare). Se A non passa, il pilota NON e' superato e la
    campagna non parte (P2.9: "Se ``done_reason`` manca o non distingue i due
    casi, la campagna non parte").
  - B: descrittiva. Si confrontano mediana e media di ``input_tokens`` e
    ``prompt_eval_duration`` fra i due bracci, e si riporta lo scarto. Nessuna
    soglia: P2.9 dice che il pilota quantifica il riuso, non che decide la
    regola di P2.8.
  - C: ``input_tokens`` presente, ``N_in + N_out <= num_ctx`` e nessun motivo
    ``context_boundary`` (la guardia di P2.7 non scatta); la corrispondenza fra
    contatore e prompt costruito si verifica con due ancore dichiarate prima
    del run: (i) ``input_tokens`` >= numero di parole del testo spedito, che
    ogni tokenizzatore rispetta, quindi un conteggio piu' basso e' troncamento
    o assenza; (ii) il rapporto token/parola del prompt C contro quello dei
    warm-up (512,128) della stessa invocazione, entrambi costruiti dallo stesso
    generatore (``machine_state.warmup_prompt``), entro il 10%. Il rapporto e'
    il confronto giusto perche' i due testi hanno lunghezze diverse.

``dt_nominal_s``: la regola e' quella congelata, senza qualificazioni che il
testo non ha -- 3 x la mediana delle durate di **tutte** le righe valide del
pilota, bracci A, B e C compresi. Le mediane per braccio sono scritte
nell'artefatto come diagnostica dichiarata e **non** usate per il numero: il
pilota non e' omogeneo per geometria (B ha ``num_predict=1``, C ha il massimo
``N_in``) e scegliere il sottoinsieme "che somiglia alla campagna" dopo aver
visto le durate sarebbe una decisione presa sui dati.

Uso (dalla radice del repository):
    py cwEnergyModular/tools/run_pilot_p29.py --plan
    py cwEnergyModular/tools/run_pilot_p29.py --execute
    py cwEnergyModular/tools/run_pilot_p29.py --analyze
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent
sys.path.insert(0, str(MODULE_DIR))

import config  # noqa: E402
import machine_state as ms  # noqa: E402

PILOT_DATE = "20261107"
ARCHIVE_DIR = REPO_ROOT / "experiment_results" / f"p29_pilot_{PILOT_DATE}"
RESULTS_DIR = MODULE_DIR / "results" / f"p29_pilot_{PILOT_DATE}"
ROWS_NAME = "casualwatt_v4_results_p29.csv"
BLOCKS_NAME = "casualwatt_v4_block_summary_p29.csv"
RUNS_NAME = "runs.json"
PLAN_NAME = "plan.json"
ANALYSIS_NAME = "analysis.json"
REPORT_NAME = "p29_pilot_report.md"
FREEZE_NAME = "dt_nominal_frozen.json"

DEFAULT_MODEL = "qwen2.5:0.5b"
NUM_CTX = 8192
K_MAX = 1                 # tetto di Emenda 8 per il pilota: un solo sostituto
ORDER_SEED = "p29:A1,A2,A3,Bi,Bn,C"
TOL_RAPPORTO_TOKEN_WORD = 0.10   # check C (ii), dichiarato nel piano

# Il testo del braccio B non usa WARMUP_SENTENCE: i warm-up di P1.4 spediscono
# 518 parole di quel testo (37 ripetizioni della frase da 14 parole) e un
# prefisso condiviso con il warm-up sarebbe riuso da un'altra richiesta, non fra
# le tre richieste del braccio. Con un testo proprio l'unico prefisso condiviso
# e' quello che il braccio misura.
B_SENTENCE = ("Il blocco misura l'energia della richiesta e sottrae la "
              "baseline calibrata sulle tre finestre che lo precedono. ")
B_QUESTION = "\nRispondi con una sola parola: pronto."


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _b_prompt() -> str:
    words = B_SENTENCE.split()
    repeats = max(1, int(round(130 / len(words))))
    return " ".join([B_SENTENCE.strip()] * repeats) + B_QUESTION


def arms() -> List[Dict]:
    """I sei blocchi del pilota, nell'ordine dichiarato.

    Ogni braccio ha la propria invocazione del runner (``m`` richieste, una
    geometria, un regime di nonce), perche' ``run_block`` accetta un solo
    prompt. B e' l'unico con ``m = 3``: e' l'unico che puo' dare ``u_within,b``
    (semi-range su ``active_energy_raw_j`` delle richieste del blocco, F.9), e
    con ``m = 1`` uno zero sarebbe per costruzione, non misurato.
    """
    return [
        {"label": "A1", "arm": "A", "prompt_id": "p29-a1", "m": 1,
         "num_predict": 32, "use_nonce": True,
         "text": "Elenca trenta capitali europee, una per riga, formato "
                 "'capitale - nazione', senza introduzione ne' commento."},
        {"label": "A2", "arm": "A", "prompt_id": "p29-a2", "m": 1,
         "num_predict": 32, "use_nonce": True,
         "text": "Scrivi in lettere i numeri da uno a cinquanta, uno per "
                 "riga, senza altro testo."},
        {"label": "A3", "arm": "A", "prompt_id": "p29-a3", "m": 1,
         "num_predict": 32, "use_nonce": True,
         "text": "Quanto fa due piu' due? Rispondi solo con la cifra, senza "
                 "spiegazioni."},
        {"label": "Bi", "arm": "B", "prompt_id": "p29-b-id",
         "m": 3, "num_predict": 1, "use_nonce": False,
         "text": _b_prompt()},
        {"label": "Bn", "arm": "B", "prompt_id": "p29-b-nonce",
         "m": 3, "num_predict": 1, "use_nonce": True,
         "text": _b_prompt()},
        {"label": "C", "arm": "C", "prompt_id": "p29-c", "m": 1,
         "num_predict": 32, "use_nonce": True,
         "text": ms.warmup_prompt(ms.WARMUP_N_IN) +
                 "\nRispondi con una sola parola: pronto."},
    ]


def plan_payload(model: str) -> Dict:
    """Il piano, scritto PRIMA del run. Tutto cio' che serve a rifarlo."""
    dichiarati = []
    for a in arms():
        dichiarati.append({
            "label": a["label"], "arm": a["arm"],
            "prompt_id": a["prompt_id"], "m": a["m"],
            "num_predict": a["num_predict"], "num_ctx": NUM_CTX,
            "use_nonce": a["use_nonce"],
            "text": a["text"],
            "text_sha256": _sha256_text(a["text"]),
            "words": len(a["text"].split()),
        })
    return {
        "pilot": "P2.9",
        "declared_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "model": model,
        "temperature": config.DEFAULT_TEMPERATURE,
        "timeout_s": config.DEFAULT_TIMEOUT_S,
        "num_ctx": NUM_CTX,
        "order_seed": ORDER_SEED,
        "emenda8": {"max_invalidated_blocks": K_MAX,
                    "substitution_seed": "p29-<label>"},
        "source_documents": [
            "experiment_results/protocollo_v4_20261024.md:841-856 (P2.9)",
            "experiment_results/protocollo_v4_20261024.md:2382-2393 (P6.2)",
            "experiment_results/protocollo_v4_20261024.md:1481-1486 "
            "(P4.4 requisito 5, dt_nominal_s)",
        ],
        "checks": {
            "A": ("A1 e A2: done_reason=length, termination_class=cap_reached, "
                  "output_tokens == num_predict; A3: done_reason=stop, "
                  "termination_class=eos (non eos_at_cap)"),
            "B": ("descrittiva: mediana e media di input_tokens e "
                  "prefill_duration_s per braccio, scarto relativo; nessuna "
                  "soglia, nessuna decisione su P2.8"),
            "C": ("input_tokens presente; input_tokens+output_tokens <= "
                  f"{NUM_CTX}; nessun context_boundary; input_tokens >= "
                  "parole del testo spedito; rapporto token/parola contro il "
                  "warm-up (512,128) della stessa invocazione entro "
                  f"{TOL_RAPPORTO_TOKEN_WORD:.0%}"),
        },
        "dt_nominal_rule": ("3 x mediana di duration_s su TUTTE le righe "
                            "valide del pilota (A, B, C); le mediane per "
                            "braccio sono diagnostica dichiarata e non sono "
                            "la regola"),
        "blocks": dichiarati,
        "outputs": {
            "results_csv": str(RESULTS_DIR / ROWS_NAME),
            "block_summary_csv": str(RESULTS_DIR / BLOCKS_NAME),
            "archive_dir": str(ARCHIVE_DIR),
        },
        "git_head": _git_head(),
    }


def _scrittura_atomica(path: Path, payload) -> None:
    text = (payload if isinstance(payload, str)
            else json.dumps(payload, indent=2, ensure_ascii=False))
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def cmd_plan(model: str) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = ARCHIVE_DIR / PLAN_NAME
    nuovo = plan_payload(model)
    if path.exists():
        vecchio = json.loads(path.read_text(encoding="utf-8"))
        if vecchio.get("blocks") != nuovo.get("blocks") or \
                vecchio.get("model") != nuovo.get("model"):
            print("[ERRORE] plan.json esiste e differisce: un piano che "
                  "cambia dopo i dati non e' un pilota. Spostare l'archivio "
                  "e dichiarare un pilota nuovo.", file=sys.stderr)
            return 2
        print(f"[OK] piano gia' congelato: {path}")
        return 0
    _scrittura_atomica(path, nuovo)
    print(f"[OK] piano scritto: {path}")
    for b in nuovo["blocks"]:
        print(f"  {b['label']:>2}: m={b['m']} num_predict={b['num_predict']} "
              f"nonce={'on' if b['use_nonce'] else 'off'} "
              f"parole={b['words']} sha={b['text_sha256'][:12]}")
    return 0


def _load_plan() -> Dict:
    path = ARCHIVE_DIR / PLAN_NAME
    if not path.exists():
        raise SystemExit(
            f"piano assente ({path}): il pilota si dichiara con --plan prima "
            "di misurare")
    return json.loads(path.read_text(encoding="utf-8"))


def _verifica_piano(plan: Dict, model: str) -> None:
    if plan.get("model") != model:
        raise SystemExit(f"modello del piano ({plan.get('model')}) diverso da "
                         f"quello richiesto ({model})")
    correnti = {a["label"]: _sha256_text(a["text"]) for a in arms()}
    for b in plan["blocks"]:
        if correnti.get(b["label"]) != b["text_sha256"]:
            raise SystemExit(
                f"il prompt di {b['label']} non e' quello dichiarato nel "
                "piano: il codice e' cambiato dopo la dichiarazione")


def _ultimo_metadata(run_id: str) -> Optional[Dict]:
    path = config.CSV_RUN_METADATA_PATH
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as fh:
        righe = [r for r in csv.DictReader(fh) if r.get("run_id") == run_id]
    return righe[-1] if righe else None


def cmd_execute(model: str) -> int:
    plan = _load_plan()
    _verifica_piano(plan, model)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    for p in (rows_path, blocks_path):
        if p.exists() and p.stat().st_size > 0:
            raise SystemExit(
                f"{p} esiste gia': un secondo tentativo nella stessa cartella "
                "mescolerebbe due piloti. Spostare la cartella e ripetere "
                "la dichiarazione del piano.")

    import benchmark_v4 as v4

    runs: List[Dict] = []
    for b in plan["blocks"]:
        label = b["label"]
        print(f"\n=== {label} (m={b['m']}, num_predict={b['num_predict']}, "
              f"nonce={'on' if b['use_nonce'] else 'off'}) ===", flush=True)
        summary = v4.run_v4_benchmark(
            [model],
            [{"id": b["prompt_id"], "text": b["text"],
              "answer_type": "auto", "source": "pilot_p29"}],
            m=b["m"], blocks_per_point=1,
            num_predict=b["num_predict"], num_ctx=NUM_CTX,
            use_nonce=b["use_nonce"],
            batch_id=f"p29-{label}", block_kind="pilot",
            order_seed=ORDER_SEED,
            max_invalidated_blocks=K_MAX,
            substitution_seed=f"p29-{label}",
            results_path=rows_path, block_summary_path=blocks_path,
            on_log=lambda m_: print(m_, flush=True),
        )
        meta = _ultimo_metadata(summary["run_id"]) or {}
        runs.append({
            "label": label, "arm": b["arm"], "m": b["m"],
            "num_predict": b["num_predict"], "use_nonce": b["use_nonce"],
            "run_id": summary["run_id"], "batch_id": summary["batch_id"],
            "records": summary.get("records"),
            "blocks": summary.get("blocks"),
            "errors": summary.get("errors"),
            "invalidated_blocks": summary.get("invalidated_blocks"),
            "started_at": meta.get("started_at", ""),
            "finished_at": meta.get("finished_at", ""),
            "notes": meta.get("notes", ""),
        })
        _scrittura_atomica(RESULTS_DIR / RUNS_NAME, {"runs": runs})
        if summary.get("errors"):
            print(f"[ERRORE] {label}: il run ha registrato errori; "
                  "mi fermo qui", file=sys.stderr)
            return 1
    return cmd_analyze(model)


# ---------------------------------------------------------------------------
# Analisi: verifiche A/B/C, terne per blocco, congelamento di dt_nominal_s
# ---------------------------------------------------------------------------
def _kv(notes: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for parte in str(notes or "").split(";"):
        if "=" in parte:
            k, v = parte.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _num(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def _carica_csv(path: Path) -> List[Dict]:
    with path.open(newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def _riga_valida(riga: Dict) -> bool:
    """Valida per P2.5: nessun motivo di invalidita', token e durata letti."""
    if "richiesta invalida per:" in str(riga.get("notes", "")):
        return False
    if _num(riga.get("duration_s")) is None:
        return False
    for campo in ("input_tokens", "output_tokens"):
        v = _num(riga.get(campo))
        if v is None or v <= 0:
            return False
    return True


def _terne_blocchi(rows: Sequence[Dict]) -> List[Dict]:
    """Una riga per blocco: baseline, terna pre, `u_within,b` delle richieste.

    ``u_within,b`` = semi-range di ``active_energy_raw_j`` (F.9, :2966), non
    diviso per sqrt(m). Con meno di due valori la cella resta ``None`` con la
    ragione: a ``m = 1`` uno zero e' per costruzione.
    """
    per_blocco: Dict[str, List[Dict]] = {}
    for r in rows:
        per_blocco.setdefault(str(r.get("block_id", "")), []).append(r)
    out = []
    for block_id, righe in per_blocco.items():
        energia = [_num(r.get("active_energy_raw_j")) for r in righe]
        energia = [e for e in energia if e is not None]
        if len(energia) >= 2:
            u_within = (max(energia) - min(energia)) / 2.0
            u_motivo = ""
        else:
            u_within = None
            u_motivo = ("meno di due richieste valide nel blocco: il "
                        "semi-range sarebbe zero per costruzione")
        out.append({
            "block_id": block_id,
            "batch_id": str(righe[0].get("batch_id", "")),
            "requests": len(righe),
            "active_energy_raw_j": [round(e, 6) for e in energia],
            "u_within_b_j": (None if u_within is None
                             else round(u_within, 6)),
            "u_within_b_reason": u_motivo,
        })
    return out


def _verifica_a(per_braccio: Dict[str, List[Dict]]) -> Dict:
    attesi = {"A1": ("length", "cap_reached"),
              "A2": ("length", "cap_reached"),
              "A3": ("stop", "eos")}
    prova: Dict[str, Dict] = {}
    ok = True
    for label, (done_atteso, classe_attesa) in attesi.items():
        righe = per_braccio.get(label) or []
        if len(righe) != 1:
            prova[label] = {"ok": False,
                            "motivo": f"{len(righe)} righe, attesa 1"}
            ok = False
            continue
        r = righe[0]
        kv = _kv(r.get("notes", ""))
        n_out = _num(r.get("output_tokens"))
        cap = _num(kv.get("num_predict"))
        done = kv.get("done_reason", "")
        classe = kv.get("termination_class", "")
        sotto = []
        if done != done_atteso:
            sotto.append(f"done_reason={done!r}, atteso {done_atteso!r}")
        if classe != classe_attesa:
            sotto.append(f"termination_class={classe!r}, "
                         f"attesa {classe_attesa!r}")
        if label in ("A1", "A2"):
            if n_out is None or cap is None or n_out != cap:
                sotto.append(f"N_out_actual={n_out!r} != num_predict={cap!r}")
        else:
            if n_out is None or cap is None or not (0 < n_out < cap):
                sotto.append(f"N_out_actual={n_out!r} non sotto il tetto "
                             f"num_predict={cap!r}: una EOS al tetto non e' "
                             "distinguibile da un cap")
        prova[label] = {"ok": not sotto,
                        "done_reason": done, "termination_class": classe,
                        "output_tokens": n_out, "num_predict": cap,
                        "motivi": sotto}
        ok = ok and not sotto
    return {"ok": ok, "per_label": prova,
            "conseguenza": ("la campagna puo' partire" if ok else
                            "P2.9 non superato: la campagna NON parte "
                            "(protocollo:841-856)")}


def _riassunto_braccio(righe: Sequence[Dict]) -> Dict:
    conteggi = [_num(r.get("input_tokens")) for r in righe]
    prefills = [_num(r.get("prefill_duration_s")) for r in righe]
    conteggi = [c for c in conteggi if c is not None]
    prefills = [p for p in prefills if p is not None]
    return {
        "n": len(righe),
        "input_tokens": conteggi,
        "input_tokens_median": (statistics.median(conteggi)
                                if conteggi else None),
        "input_tokens_mean": (round(statistics.fmean(conteggi), 3)
                              if conteggi else None),
        "prefill_s": [round(p, 6) for p in prefills],
        "prefill_s_median": (round(statistics.median(prefills), 6)
                             if prefills else None),
        "prefill_s_mean": (round(statistics.fmean(prefills), 6)
                           if prefills else None),
    }


def _verifica_b(per_braccio: Dict[str, List[Dict]]) -> Dict:
    ident = _riassunto_braccio(per_braccio.get("Bi") or [])
    nonce = _riassunto_braccio(per_braccio.get("Bn") or [])
    scarto = {}
    for chiave in ("input_tokens_median", "prefill_s_median",
                   "input_tokens_mean", "prefill_s_mean"):
        a, b = ident.get(chiave), nonce.get(chiave)
        if a not in (None, 0) and b is not None:
            scarto[chiave] = round((b - a) / a, 6)
        else:
            scarto[chiave] = None
    return {"descrittiva": True,
            "identico": ident, "nonce": nonce, "scarto_relativo": scarto,
            "lettura": ("lo scarto misura quanto il prefisso condiviso pesa; "
                        "non decide nulla su P2.8, che resta obbligatorio "
                        "anche se lo scarto fosse nullo")}


def _warmup_counts(notes: str) -> List[int]:
    return [int(v) for v in re.findall(r"prompt_eval=(\d+)", str(notes))]


def _verifica_c(righe: Sequence[Dict], run: Dict, num_ctx: int) -> Dict:
    if len(righe) != 1:
        return {"ok": False, "motivo": f"{len(righe)} righe, attesa 1"}
    r = righe[0]
    kv = _kv(r.get("notes", ""))
    n_in = _num(r.get("input_tokens"))
    n_out = _num(r.get("output_tokens"))
    parole = len(str(r.get("prompt", "")).split())
    controlli: Dict[str, object] = {}
    ok = True
    if n_in is None or n_in <= 0:
        controlli["input_tokens"] = "assente"
        ok = False
    if n_in is not None and n_out is not None:
        controlli["guardia_p27"] = {
            "n_in_plus_n_out": n_in + n_out, "num_ctx": num_ctx,
            "rispettata": (n_in + n_out) <= num_ctx}
        ok = ok and (n_in + n_out) <= num_ctx
    if "context_boundary" in str(r.get("notes", "")):
        controlli["context_boundary"] = "presente: la guardia di P2.7 scatta"
        ok = False
    else:
        controlli["context_boundary"] = "assente"
    controlli["parole_testo_spedito"] = parole
    if n_in is not None:
        controlli["n_in_almeno_parole"] = n_in >= parole
        ok = ok and n_in >= parole
    conteggi_warmup = _warmup_counts(run.get("notes", ""))
    ratio = None
    if conteggi_warmup and n_in is not None and parole > 0:
        tok_per_word_c = n_in / float(parole)
        tok_per_word_w = conteggi_warmup[-1] / float(
            len(ms.warmup_prompt(ms.WARMUP_N_IN).split()))
        ratio = tok_per_word_c / tok_per_word_w
        controlli["rapporto_token_parola"] = {
            "prompt_c": round(tok_per_word_c, 6),
            "warmup": round(tok_per_word_w, 6),
            "rapporto": round(ratio, 6),
            "tolleranza": TOL_RAPPORTO_TOKEN_WORD,
            "entro_tolleranza": abs(ratio - 1.0) <= TOL_RAPPORTO_TOKEN_WORD,
        }
        ok = ok and abs(ratio - 1.0) <= TOL_RAPPORTO_TOKEN_WORD
    else:
        controlli["rapporto_token_parola"] = (
            "non calcolabile: warm-up o contatore assenti")
        ok = False
    return {"ok": ok, "input_tokens": n_in, "output_tokens": n_out,
            "done_reason": kv.get("done_reason", ""),
            "termination_class": kv.get("termination_class", ""),
            "controlli": controlli}


def _freeze_dt(righe: Sequence[Dict], runs: Sequence[Dict]) -> Dict:
    """Il numero, e solo il numero: 3 x mediana delle durate valide.

    Separato dalla provenienza perche' la regola si puo' verificare su righe
    sintetiche senza un archivio sul disco; il campo ``source`` lo aggiunge
    :func:`_freeze_provenienza` dopo la copia dei CSV.
    """
    valide = [r for r in righe if _riga_valida(r)]
    escluse = [{"block_id": r.get("block_id", ""),
                "notes": str(r.get("notes", ""))[:200]}
               for r in righe if not _riga_valida(r)]
    durate = sorted(float(r["duration_s"]) for r in valide)
    if not durate:
        raise SystemExit("nessuna riga valida: dt_nominal_s non ha una "
                         "provenienza e non si inventa")
    mediana = statistics.median(durate)
    per_braccio: Dict[str, Optional[float]] = {}
    for run in runs:
        b = [float(r["duration_s"]) for r in valide
             if r.get("batch_id") == run["batch_id"]]
        per_braccio[run["label"]] = (round(statistics.median(b), 6)
                                     if b else None)
    return {
        "dt_nominal_s": round(3.0 * mediana, 6),
        "formula": "3 x mediana(duration_s delle righe valide del pilota)",
        "rule": ("P4.4 requisito 5, protocollo_v4_20261024.md:1481-1486: "
                 "fissato PRIMA della campagna come 3 x la mediana della "
                 "durata di richiesta misurata nel pilota di P2"),
        "median_duration_s": round(float(mediana), 6),
        "durations_s": [round(d, 6) for d in durate],
        "rows_used": len(valide),
        "rows_excluded": escluse,
        "per_arm_median_s": per_braccio,
        "per_arm_note": ("diagnostica dichiarata, NON usata per il numero: la "
                         "regola e' la mediana su tutte le righe valide, e il "
                         "pilota non e' omogeneo per geometria"),
    }


def _freeze_provenienza(freeze: Dict, runs: Sequence[Dict],
                        num_ctx: int, model: str) -> Dict:
    """Percorsi, sha256, run id e HEAD: senza questi il numero e' anonimo."""
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    out = dict(freeze)
    out["source"] = {
        "results_csv": str(ARCHIVE_DIR / ROWS_NAME),
        "results_csv_sha256": (_sha256(ARCHIVE_DIR / ROWS_NAME)
                               if (ARCHIVE_DIR / ROWS_NAME).exists()
                               else _sha256(rows_path)),
        "block_summary_csv": str(ARCHIVE_DIR / BLOCKS_NAME),
        "block_summary_csv_sha256": (
            _sha256(ARCHIVE_DIR / BLOCKS_NAME)
            if (ARCHIVE_DIR / BLOCKS_NAME).exists()
            else _sha256(blocks_path)),
        "live_results_csv": str(rows_path),
        "live_block_summary_csv": str(blocks_path),
        "run_ids": [r["run_id"] for r in runs],
        "model": model,
        "num_ctx": num_ctx,
        "pilot_date": PILOT_DATE,
        "git_head": _git_head(),
        "runner": "benchmark_v4.run_v4_benchmark",
    }
    return out


def cmd_analyze(model: str) -> int:
    plan = _load_plan()
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    runs_path = RESULTS_DIR / RUNS_NAME
    for p in (rows_path, blocks_path, runs_path):
        if not p.exists():
            raise SystemExit(f"serve {p}: eseguire prima --execute")
    rows = _carica_csv(rows_path)
    blocchi = _carica_csv(blocks_path)
    runs = json.loads(runs_path.read_text(encoding="utf-8"))["runs"]
    num_ctx = int(plan["num_ctx"])

    per_braccio: Dict[str, List[Dict]] = {}
    for run in runs:
        per_braccio[run["label"]] = [
            r for r in rows if r.get("batch_id") == run["batch_id"]]

    a = _verifica_a(per_braccio)
    b = _verifica_b(per_braccio)
    run_c = next((r for r in runs if r["label"] == "C"), {})
    c = _verifica_c(per_braccio.get("C") or [], run_c, num_ctx)
    terne = _terne_blocchi(rows)

    # I CSV entrano nell'archivio tracciato PRIMA del freeze, perche' il freeze
    # ne cita lo sha256: un'impronta di un file che poi cambia non aggancia
    # nulla.
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for src, name in ((rows_path, ROWS_NAME), (blocks_path, BLOCKS_NAME),
                      (runs_path, RUNS_NAME)):
        shutil.copyfile(src, ARCHIVE_DIR / name)
    freeze = _freeze_dt(rows, runs)
    freeze = _freeze_provenienza(freeze, runs, num_ctx, plan["model"])

    analysis = {
        "pilot": "P2.9",
        "declared_at": plan.get("declared_at", ""),
        "executed_from": (runs[0].get("started_at", "") if runs else ""),
        "executed_to": (runs[-1].get("finished_at", "") if runs else ""),
        "model": plan["model"],
        "runs": runs,
        "checks": {"A": a, "B": b, "C": c},
        "blocks": blocchi,
        "terne": terne,
        "dt_nominal": freeze,
        "git_head": _git_head(),
    }
    _scrittura_atomica(ARCHIVE_DIR / ANALYSIS_NAME, analysis)
    _scrittura_atomica(ARCHIVE_DIR / FREEZE_NAME, freeze)

    righe_report = [
        "# Pilota P2.9 sul runner v4 — 2026-11-07",
        "",
        f"Modello: `{plan['model']}` — runner `benchmark_v4.run_v4_benchmark` "
        f"— ordine dichiarato `{plan['order_seed']}`.",
        f"CSV: `{ROWS_NAME}` ({len(rows)} righe), `{BLOCKS_NAME}` "
        f"({len(blocchi)} blocchi), `{RUNS_NAME}`.",
        "",
        "## Verifiche",
        "",
        f"- A (semantica di `done_reason`): **{'superata' if a['ok'] else 'NON superata'}**",
    ]
    for label, p in a["per_label"].items():
        esito = "ok" if p.get("ok") else "NO"
        righe_report.append(
            f"  - {label} [{esito}]: done_reason={p.get('done_reason')}, "
            f"classe={p.get('termination_class')}, "
            f"N_out={p.get('output_tokens')}, tetto={p.get('num_predict')}"
            + ("" if p.get("ok") else
               " — " + "; ".join(p.get("motivi") or [])))
    righe_report += [
        f"  - conseguenza: {a['conseguenza']}",
        f"- B (cache, descrittiva): identico {b['identico']}; "
        f"nonce {b['nonce']}; scarto {b['scarto_relativo']}",
        f"- C (contesto): **{'superata' if c['ok'] else 'NON superata'}** — "
        f"controlli {json.dumps(c.get('controlli', {}), ensure_ascii=False)}",
        "",
        "## Terne per blocco (P6.2)",
        "",
        "| blocco | richieste | P_pre W | pre_range W | half_range W | dP W | "
        "budget_base W | u_within,b J |",
        "|---|---|---|---|---|---|---|---|",
    ]
    terna_per_blocco = {t["block_id"]: t for t in terne}
    for bl in blocchi:
        t = terna_per_blocco.get(bl.get("block_id", ""), {})
        u = t.get("u_within_b_j")
        righe_report.append(
            f"| {bl.get('block_id','')} | {t.get('requests','')} | "
            f"{bl.get('baseline_pre_w','')} | {bl.get('pre_range_w','')} | "
            f"{bl.get('half_range_pre_w','')} | {bl.get('dP','')} | "
            f"{bl.get('budget_base_w','')} | "
            f"{'n/d' if u is None else u} |")
    righe_report += [
        "",
        f"`u_within,b` e' `n/d` dove il blocco ha una richiesta sola: con "
        f"`m = 1` il semi-range e' zero per costruzione (P3.8/F.9).",
        "",
        "## `dt_nominal_s` congelato",
        "",
        f"- valore: **{freeze['dt_nominal_s']} s**",
        f"- regola: {freeze['rule']}",
        f"- mediana delle durate: {freeze['median_duration_s']} s su "
        f"{freeze['rows_used']} righe valide",
        f"- durate: {freeze['durations_s']}",
        f"- mediane per braccio (diagnostica, non usate): "
        f"{freeze['per_arm_median_s']}",
        "",
        "Il numero non e' stato scelto: esce dalla mediana delle righe "
        "misurate, e l'artefatto ne cita percorso, sha256, run id e HEAD.",
        "",
    ]
    _scrittura_atomica(ARCHIVE_DIR / REPORT_NAME, "\n".join(righe_report))

    stato = "OK" if (a["ok"] and c["ok"]) else "NON SUPERATO"
    print(f"\n[PILOTA {stato}] A={'ok' if a['ok'] else 'NO'} "
          f"B=descrittiva C={'ok' if c['ok'] else 'NO'}")
    print(f"dt_nominal_s = {freeze['dt_nominal_s']} s "
          f"(3 x {freeze['median_duration_s']} s, "
          f"{freeze['rows_used']} righe valide)")
    print(f"artefatti: {ARCHIVE_DIR}")
    return 0 if (a["ok"] and c["ok"]) else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Pilota P2.9 sul runner v4 (dichiarazione, esecuzione, "
                    "analisi).")
    ap.add_argument("--plan", action="store_true",
                    help="scrive plan.json prima di misurare")
    ap.add_argument("--execute", action="store_true",
                    help="esegue i sei blocchi del piano e analizza")
    ap.add_argument("--analyze", action="store_true",
                    help="verifica A/B/C e congela dt_nominal_s dai CSV")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    args = ap.parse_args(argv)
    if sum(bool(x) for x in (args.plan, args.execute, args.analyze)) != 1:
        ap.error("scegliere esattamente uno fra --plan, --execute, --analyze")
    if args.plan:
        return cmd_plan(args.model)
    if args.execute:
        return cmd_execute(args.model)
    return cmd_analyze(args.model)


if __name__ == "__main__":
    sys.exit(main())
