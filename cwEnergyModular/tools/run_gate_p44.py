# -*- coding: utf-8 -*-
"""tools/run_gate_p44.py — il gate load-versus-control di P4.4 sulla v4.

Perche' esiste. P4.4 (emendamento del 2026-10-24, terza emenda sostanziale)
vuole sei coppie di blocchi: per ogni coppia un blocco di carico
(``block_kind='load'``, m=32 richieste, num_predict=32) e un blocco di
controllo (``block_kind='control'``, finestra passiva di ``dt_nominal_s``
SENZA inviare richieste — requisito 5). Il disegno e' dichiarato
PRIMA dei dati in ``plan.json``; l'esito passa dal criterio F.12 di
``control_gate.evaluate_gate``, che restituisce ``status``
pass/fail/not-executable, ``chain_status`` e il bias aggregato.

Struttura del run (emendata dopo la verifica pre-esecuzione del 2026-11-08):
DODICI invocazioni di ``run_v4_benchmark``, una per blocco, con
``blocks_per_point=1`` e ``pair_id='pair-<coppia>'`` — non piu' sei invocazioni
da due blocchi, perche' in quel disegno il ``pair_id`` era uno solo per la
coppia e il blocco di controllo non era mai attivato (il runner derivava
``control`` da ``block_kind``, ma l'etichetta di una singola invocazione non
puo' coprire due bracci diversi). L'ordine e' carico-primo per coppia,
dichiarato, non randomizzato; ``order_seed`` e' il seme del disegno
(requisito 3), parametrizzato con ``--seed``: il default e'
``'gate-seed-20261107'``, la campagna dichiarata, quindi nulla cambia per chi
non lo passa.

Il cooldown intra-coppia (P1.5) e' una SCELTA OPERATIVA, non un requisito di
P4.4: il requisito 7 vincola la struttura di baseline (3 pre + 3 post su
entrambi i bracci), non il cooldown. Il blocco di controllo riceve il
``P_pre`` del carico della stessa coppia tramite ``initial_last_pre_w``, letto
dall'ultima riga di riepilogo scritta; se la propagazione manca, il tool si
ferma prima di proseguire — un controllo senza cooldown verso il carico e' un
disegno diverso da quello dichiarato, scoperto dopo i dati.

Parametri inerti: su un blocco di controllo ``m``, ``num_predict`` e
``use_nonce`` NON vengono passati — le richieste sono ``range(0)`` per
costruzione (requisito 5), quindi qualunque valore sarebbe una finzione. Il
percorso di controllo e' derivato nel runner da ``block_kind == "control"``.

Come il gate legge i controlli. ``control_e_net_j``, ``control_dt_w_s`` e
``control_package_window_source`` NON hanno colonna nello schema P5 congelato
(``export_summary_csv`` le scarta con ``extrasaction='ignore'``): un tool che
rileggesse i controlli dal CSV consegnerebbe a ``evaluate_gate`` campi per
costruzione vuoti, e il gate si dichiarerebbe non eseguibile DOPO la campagna.
La forma di consumo prevista e' il riepilogo completo del runner (e' quella
che :meth:`control_gate.main` legge da ``--blocks``): il tool cattura i
riepiloghi nell'attimo in cui il runner li passa a ``export_summary_csv`` e
consegna anche ``blocks_controllo.json``, artefatto con la stessa forma. Il
CSV resta la fonte della propagazione (``baseline_pre_w`` e' una colonna) e
dei controlli d'identita'.

Emenda 8: ``K=1`` per invocazione (il runner si invalida al primo guasto) e
``substitution_seed='p44-<label>'`` per blocco. ``dt_nominal_s`` e' congelato
dal pilota P2.9 (requisito 5): 2,930748 s.

La data di campagna e' un parametro (``--date YYYYMMDD``, default la campagna
del 2026-11-07): sposta ``ARCHIVE_DIR`` e ``RESULTS_DIR`` senza toccare
``plan_blocks()`` o la durata congelata, quindi la verifica del piano resta
valida e un secondo run non richiede di editare il codice. Anche il seme e'
un parametro (``--seed``): ``_verifica_piano`` confronta il piano contro il
seme passato, non contro una costante — un execute con un seme diverso da
quello del plan si ferma prima di misurare. Il risultato congelato di una
campagna non si sovrascrive: ``execute`` rifiuta output gia' presenti.

Serie di potenza grezza. Il runner non salva i campioni della finestra
passiva (il riepilogo porta solo gli aggregati ``control_*``): senza la serie
non si puo' dire se il bias di un controllo sia una deriva o un picco. Il tool
la cattura lato proprio — wrapper di ``_run_control_window`` che trattiene i
due bordi e chiede ``samples_between(t0, t1)`` alla sessione, senza letture
aggiuntive sul contatore — e la scrive in ``control_power_series.json``.
E' diagnostica: non entra nel criterio F.12. Per la campagna del 2026-11-07
la serie non esiste e non e' recuperabile a posteriori: la cattura vale per
quelle successive.

Precondizione di quiete. Il gate del 2026-11-07 e' fallito con
``background_load=True`` su 5 controlli su 6: P1.4 registra il flag ma il
runner parte comunque. Prima di OGNI blocco (load e control) il tool
attende che ``ms.background_load_from_samples`` sia False per
``QUIET_CONSECUTIVE`` letture consecutive; una lettura rumorosa azzera il
conteggio; al tetto ``QUIET_CAP_S`` senza quiete, ``SystemExit``
([ARRESTO], exit 3), mai procedere in silenzio. Le costanti sono congelate
in ``plan.json`` prima delle misure (check E) e la verifica del piano le
confronta: il plan del 2026-11-07, che precede la precondizione, non e'
eseguibile e va ripianificato. Attesa e top-5 alla partenza sono registrati
per blocco in ``runs``, nel report e in ``gate_result_frozen.json``. E' una
precondizione di ESECUZIONE: il criterio F.12 non cambia.

Grandezze riportate, non criterio. Per tutti i controlli, anche non
utilizzabili, il tool riporta E_net/dt_W e le statistiche descrittive fra
blocchi (media, sd campionaria ddof=1, SE, CI95 con t di Student: scipy se
installato, altrimenti tabella dichiarata; df>30 senza scipy -> 1.960,
approssimazione normale dichiarata). Nel report una tabella per controllo
con ``background_load`` prima/dopo dal riepilogo del runner. Queste
grandezze NON decidono l'esito (che resta F.12) e non entrano nello schema
CSV: la sd e' fra blocchi, non sulla terna di baseline di P4.12, dove a
n=3 il divieto di stimare una varianza resta.
"""
from __future__ import annotations
import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent
sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import control_gate as cg  # noqa: E402
import machine_state as ms  # noqa: E402

try:  # scipy e' opzionale: senza, la tabella t dichiarata sotto
    from scipy.stats import t as _scipy_t  # noqa: E402
except ImportError:
    _scipy_t = None

DEFAULT_DATE = "20261107"       # campagna dichiarata; --date per le successive
P44_DATE = DEFAULT_DATE         # etichetta di campagna, non del disegno
ARCHIVE_DIR = REPO_ROOT / "experiment_results" / f"p44_gate_{P44_DATE}"
RESULTS_DIR = MODULE_DIR / "results" / f"p44_gate_{P44_DATE}"
ROWS_NAME = "casualwatt_v4_results_p44.csv"
BLOCKS_NAME = "casualwatt_v4_block_summary_p44.csv"
PLAN_NAME = "plan.json"
ANALYSIS_NAME = "analysis.json"
FREEZE_NAME = "gate_result_frozen.json"
REPORT_NAME = "p44_gate_report.md"
BLOCKS_JSON_NAME = "blocks_controllo.json"
SERIES_NAME = "control_power_series.json"
DEFAULT_MODEL = "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest"
K_MAX = 1                       # Emenda 8: sostituzione di un blocco
DEFAULT_SEED = "gate-seed-20261107"  # campagna dichiarata; --seed per le altre
SEED = DEFAULT_SEED             # requisito 3: seme del disegno, dichiarato
DT_NOM_FROZEN = 2.930748        # pilota P2.9, requisito 5: congelato
GEOMETRY = "12,32"              # requisito 4: punto operativo di P3.5
NUM_CTX = 8192
LOAD_PROMPT = "Spiega in una frase cos'e' un watt."   # n_in ~51 token
LOAD_M = 32
LOAD_NUM_PREDICT = 32
N_COPPIE = 6
N_BLOCCHI = 12
BLOCKS_PER_POINT = 1            # un blocco per invocazione: due bracci non
                                # possono stare sotto lo stesso block_kind

# Precondizione di quiete (lato tool, P1.4): il gate del 2026-11-07 e'
# fallito con background_load=True su 5 controlli su 6 — il runner registra
# il flag nel verbale ma parte comunque. Queste due costanti finiscono in
# plan.json PRIMA delle misure: sono parametri di esecuzione, non criterio
# F.12 (che non si muove).
QUIET_CONSECUTIVE = 3           # letture consecutive non rumorose per partire
QUIET_CAP_S = 600.0             # tetto: oltre, SystemExit, mai in silenzio
QUIET_POLL_S = 0.0              # ogni lettura e' gia' ~3 s di osservazione
                                # (total_cpu_samples): nessuna pausa in piu'


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scrittura_atomica(path: Path, payload) -> None:
    text = payload if isinstance(payload, str) else \
        json.dumps(payload, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:
        return ""


def _imposta_data(data: str) -> None:
    """Sposta archivio e results su un'altra campagna dichiarata (``--date``).

    La data e' un'etichetta di campagna, non un parametro del disegno:
    ``plan_blocks()``, il seed e ``DT_NOM_FROZEN`` non dipendono da essa,
    quindi la verifica del piano resta quella congelata. Un secondo run
    non richiede di editare il codice; il risultato della prima campagna
    non si tocca. Formato accettato: YYYYMMDD (otto cifre, data reale).
    """
    global P44_DATE, ARCHIVE_DIR, RESULTS_DIR
    try:
        _dt.datetime.strptime(data, "%Y%m%d")
    except (TypeError, ValueError):
        raise SystemExit(
            f"--date '{data}' non valida: atteso YYYYMMDD (es. 20261107)")
    if len(data) != 8 or not data.isdigit():
        raise SystemExit(
            f"--date '{data}' non valida: atteso YYYYMMDD (es. 20261107)")
    P44_DATE = data
    ARCHIVE_DIR = REPO_ROOT / "experiment_results" / f"p44_gate_{data}"
    RESULTS_DIR = MODULE_DIR / "results" / f"p44_gate_{data}"


def _imposta_seme(seme: str) -> None:
    """Il seme del disegno e' un parametro (``--seed``), non una costante.

    Default = il seme della campagna dichiarata del 2026-11-07: nulla cambia
    per chi non lo passa. ``_verifica_piano`` confronta il piano contro
    QUESTO valore: un execute con un seme diverso da quello del plan si
    ferma prima di misurare, perche' un ordine dei blocchi estratto con un
    seme diverso e' un disegno diverso da quello dichiarato. Il valore e'
    conservato esattamente come passato (nessuno strip silencioso): un seme
    vuoto o di soli spazi non e' un seme e si rifiuta.
    """
    global SEED
    if not isinstance(seme, str) or not seme.strip():
        raise SystemExit(
            f"--seed '{seme}' non valido: atteso un seme non vuoto "
            f"(default {DEFAULT_SEED!r})")
    SEED = seme


def plan_blocks() -> List[Dict]:
    """Le dodici righe dichiarate: per ogni coppia, carico poi controllo."""
    blocchi = []
    for i in range(N_BLOCCHI):
        coppia = i // 2
        if i % 2 == 0:
            blocchi.append({
                "index": i, "label": f"carico-{coppia + 1}", "arm": "load",
                "pair_id": f"pair-{coppia}",
                "prompt_id": f"load-{coppia + 1}", "text": LOAD_PROMPT,
                "source": "p44_gate",
                "m": LOAD_M, "num_predict": LOAD_NUM_PREDICT,
                "use_nonce": True,
            })
        else:
            # m/num_predict/use_nonce NON si passano: su una finestra passiva
            # sono inerti (requisito 5) e passarli fingerebbe che operino.
            blocchi.append({
                "index": i, "label": f"controllo-{coppia + 1}",
                "arm": "control", "pair_id": f"pair-{coppia}",
                "prompt_id": f"ctrl-{coppia + 1}", "text": "",
                "source": "gate_control",
                "richieste": 0, "dt_nominal_s": DT_NOM_FROZEN,
            })
    return blocchi


def plan_payload() -> Dict:
    """Disegno dichiarato. Tutto dipende da P2.9: DT_NOM e' il pilota."""
    return {
        "pilot": "P4.4 gate",
        "campaign_date": P44_DATE,
        "declared_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "model": DEFAULT_MODEL,
        "temperature": config.DEFAULT_TEMPERATURE,
        "timeout_s": config.DEFAULT_TIMEOUT_S, "num_ctx": NUM_CTX,
        "order_seed": SEED,
        "n_coppie": N_COPPIE, "n_blocchi": N_BLOCCHI,
        "blocks_per_point": BLOCKS_PER_POINT,
        "invocazioni": "una run_v4_benchmark per blocco (12), non 6 da 2",
        "emenda8": {"max_invalidated_blocks": K_MAX,
                    "substitution_seed": "p44-<label> per blocco"},
        # Congelate PRIMA delle misure: un'esecuzione con una precondizione
        # diversa e' un disegno di esecuzione diverso, e la verifica sotto
        # lo rifiuta invece di scoprirlo sui dati.
        "quiet_consecutive": QUIET_CONSECUTIVE,
        "quiet_cap_s": QUIET_CAP_S,
        "geometry": GEOMETRY,
        "checks": {
            "A": ("dodici blocchi in sei coppie; ogni coppia: blocco load "
                  "m=32/np=32/nonce, poi blocco control con finestra passiva "
                  "di dt_nominal_s e ZERO richieste (requisiti 1 e 5)"),
            "B": (f"geometria operativa (12,32) confermata (requisito 4); "
                  f"DT_NOM = {DT_NOM_FROZEN} s congelata dal pilota P2.9 "
                  "(requisito 5)"),
            "C": ("ordine carico-primo per coppia, dichiarato nel piano; "
                  f"order_seed = {SEED} registrato su ogni blocco "
                  "(requisito 3)"),
            "D": ("baseline 3 pre + 3 post su ENTRAMBI i bracci (requisito 7); "
                  "cooldown intra-coppia carico->controllo via "
                  "initial_last_pre_w: scelta operativa, non requisito P4.4"),
            "E": ("precondizione di quiete PRIMA di ogni blocco (load e "
                  f"control): {QUIET_CONSECUTIVE} letture consecutive con "
                  "background_load=False, una rumorosa azzera il conteggio; "
                  f"tetto {QUIET_CAP_S:g} s poi SystemExit. Parametro di "
                  "esecuzione lato tool: il criterio F.12 non cambia"),
        },
        "deviazioni_dichiarate": [
            "12 invocazioni = 12 preparazioni di stato macchina (P1.4) e fino "
            "a 24 warm-up (2 per invocazione): costo non pagato dal disegno a "
            "6 invocazioni",
            "le finestre idle pre/post del blocco control non sono contigue a "
            "quelle del carico: la coppia e' congiunta dal pair_id e dal "
            "cooldown propagato, non dalla contiguita' temporale",
            "prepare_model_state (i due warm-up) precede il cooldown: il "
            "warm-up scalda il motore prima di attendere il rientro a P_pre",
            "i parametri inerti del controllo (m, num_predict, use_nonce) non "
            "sono passati: valore_effectivo = default del runner, inerte per "
            "costruzione su range(0)",
        ],
        "dt_nominal_rule": ("3 x mediana(duration_s) su TUTTE righe valide del "
                            "pilot P2.9; DT_NOM = 2.930748 s, congelato prima "
                            "della campagna (requisito 5)"),
        "blocks": plan_blocks(),
        "outputs": {"results_csv": str(RESULTS_DIR / ROWS_NAME),
                    "block_summary_csv": str(RESULTS_DIR / BLOCKS_NAME)},
        "git_head": _git_head(),
        "runner_sha256": _sha256(MODULE_DIR / "benchmark_v4.py"),
    }


def cmd_plan(model: str) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plan = plan_payload()
    _scrittura_atomica(ARCHIVE_DIR / PLAN_NAME, plan)
    print("[OK] piano scritto:", ARCHIVE_DIR / PLAN_NAME)
    for b in plan["blocks"]:
        if b["arm"] == "load":
            dettagli = (f"m={b['m']} num_predict={b['num_predict']} "
                        f"nonce=on")
        else:
            dettagli = f"richieste=0 finestra={b['dt_nominal_s']} s"
        print(f"  [{b['index']:>2}] {b['label']:<12} {b['arm']:<7} "
              f"{b['pair_id']:<8} {dettagli}", flush=True)
    return 0


def _verifica_piano() -> Dict:
    """Il piano eseguito deve essere quello dichiarato, non una sua riedizione."""
    path = ARCHIVE_DIR / PLAN_NAME
    if not path.exists():
        raise SystemExit("nessun plan.json: lanciare prima `plan`")
    with path.open(encoding="utf-8") as fh:
        plan = json.load(fh)
    dichiarati = plan_blocks()
    if plan.get("blocks") != dichiarati:
        raise SystemExit(
            "il piano dichiarato non coincide con plan_blocks() del codice: "
            "il tool e' cambiato DOPO la dichiarazione. Ritirare plan.json e "
            "ripianificare PRIMA di misurare.")
    # SEED e' il valore passato (--seed), non una costante: il piano deve
    # coincidere con il seme dichiarato al plan, qualunque esso sia.
    if plan.get("order_seed") != SEED or plan.get("model") != DEFAULT_MODEL:
        raise SystemExit("seed o modello discostati dal piano dichiarato")
    if (plan.get("quiet_consecutive") != QUIET_CONSECUTIVE
            or plan.get("quiet_cap_s") != QUIET_CAP_S):
        raise SystemExit(
            "precondizione di quiete assente o diversa dal piano dichiarato: "
            "il plan precede l'introduzione della precondizione (o e' stato "
            "cambiato dopo). Ritirare plan.json e ripianificare PRIMA di "
            "misurare.")
    return plan


def _ultima_baseline_pre(path: Path) -> Optional[float]:
    """L'ultima baseline_pre_w scritta, o None se non c'e'/non e' finita."""
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as fh:
        righe = list(csv.DictReader(fh))
    if not righe:
        return None
    try:
        valore = float(righe[-1].get("baseline_pre_w", ""))
    except (TypeError, ValueError):
        return None
    return valore if valore == valore and valore > 0.0 else None


def _filtra_controlli(catturati: List[Dict]) -> List[Mapping]:
    """I riepiloghi completi dei soli blocchi di controllo, notes escluse.

    Sono i dizionari che il runner passa a ``export_summary_csv`` PRIMA che
    lo schema P5 congeli le colonne: contengono i campi ``control_*`` che
    ``evaluate_gate`` legge e che il CSV consegnato non porta.
    """
    out = []
    for rec in catturati:
        if str(rec.get("block_kind", "") or "") == "control":
            c = dict(rec)
            c.pop("notes", None)
            out.append(c)
    if not out:
        raise SystemExit(
            "nessun riepilogo di blocco di controllo catturato: gate non "
            "eseguito")
    return out


def _call_kwargs(b: Dict, initial_pre: Optional[float],
                 rows_path: Path, blocks_path: Path) -> Tuple[Dict, Dict]:
    kw = dict(
        blocks_per_point=BLOCKS_PER_POINT,
        num_ctx=NUM_CTX, temperature=config.DEFAULT_TEMPERATURE,
        timeout_s=config.DEFAULT_TIMEOUT_S,
        batch_id=f"p44-{b['label']}",
        block_kind=b["arm"], pair_id=b["pair_id"], order_seed=SEED,
        dt_nominal_s=str(DT_NOM_FROZEN),
        max_invalidated_blocks=K_MAX,
        substitution_seed=f"p44-{b['label']}",
        initial_last_pre_w=initial_pre,
        results_path=rows_path, block_summary_path=blocks_path,
        on_log=lambda m: print(m, flush=True))
    if b["arm"] == "load":
        kw.update(m=b["m"], num_predict=b["num_predict"],
                  use_nonce=b["use_nonce"])
    prompt = {"id": b["prompt_id"], "text": b["text"],
              "answer_type": "auto", "source": b["source"]}
    return kw, prompt


def _cattura_riepiloghi():
    """Mod (non monkeypatch permanente) di ``export_summary_csv``: passa al
    writer reale e trattiene una copia del riepilogo COMPLETO — con i campi
    ``control_*`` che lo schema P5 scarterebbe. E' l'unico momento in cui il
    chiamante di ``run_v4_benchmark`` li vede interi."""
    reale = v4.export_summary_csv
    catturati: List[Dict] = []

    def wrapper(records, path, columns, mode="a"):
        n = reale(records, path, columns, mode=mode)
        for rec in records:
            catturati.append(dict(rec))
        return n

    return reale, wrapper, catturati


_MANCANTE = object()


def _campione_dict(s) -> Dict:
    """``SystemSample`` -> dict JSON-safe. I pid sono interi, nessun oggetto
    vivo entra nell'artefatto; un campione senza ``package_energy_j`` resta
    None (cella non misurata, non zero)."""
    try:
        d = asdict(s)
    except TypeError:
        d = dict(vars(s))
    d["ollama_pids"] = [int(p) if isinstance(p, (int, float)) else str(p)
                        for p in d.get("ollama_pids", ()) or ()]
    return d


def _serie_potenza(campioni: List[Dict]) -> List[Dict]:
    """Potenza media fra campioni consecutivi: ``ΔE_pkg/Δt`` del contatore
    cumulativo. E' la grandezza che dice se il bias di un controllo e' una
    deriva lenta o un picco; i bordi interpolati da ``samples_between``
    coprono l'intera finestra. Un intervallo con contatore assente o dt<=0
    non produce un numero."""
    out: List[Dict] = []
    for a, b in zip(campioni, campioni[1:]):
        ea, eb = a.get("package_energy_j"), b.get("package_energy_j")
        try:
            dt = float(b["t"]) - float(a["t"])
        except (TypeError, ValueError, KeyError):
            continue
        if ea is None or eb is None or dt <= 0.0:
            continue
        de = float(eb) - float(ea)
        out.append({"t_start": a["t"], "t_end": b["t"], "dt_s": dt,
                    "de_j": de, "power_w": de / dt})
    return out


def _cattura_serie_controllo():
    """Wrapper di ``_run_control_window``: passa al runner reale e salva la
    serie di potenza grezza della finestra passiva, che il runner non
    scrive da nessuna parte (il riepilogo porta solo gli aggregati).

    Metodo: durante la sola finestra passiva la sessione e' quella di
    produzione e ``_run_control_window`` legge esattamente due bordi. Il
    wrapper trattiene quei due bordi (con l'istante monotono subito dopo
    la lettura), ricostruisce ``[t0, t1]`` con la stessa espressione del
    runner (``t_counter_mono`` del primo bordo, monotono dopo il secondo)
    e chiede ``samples_between(t0, t1)`` — gli stessi campioni che il
    sampler ha gia' raccolto, nessuna lettura in piu' sul contatore.
    L'unico overhead e' un ``time.monotonic()`` per bordo.

    La serie e' DIAGNOSTICA: non entra nel criterio F.12 e non cambia
    nessuna quantita' misurata. Se i campioni mancano, l'artefatto lo
    dichiara con la ragione, non inventa una serie.
    """
    reale = v4._run_control_window
    catturate: List[Dict] = []

    def wrapper(*, block_id, durata_s, profiler, p_pre,
                stop_event=None, log=None):
        sessione = v4.SESSION
        bordi: List[Tuple[Dict, float]] = []
        proprio = sessione.__dict__.get("read_measurement_edge", _MANCANTE)
        reale_edge = sessione.read_measurement_edge

        def edge_wrapper(**kw):
            e = reale_edge(**kw)
            bordi.append((e, time.monotonic()))
            return e

        sessione.read_measurement_edge = edge_wrapper
        try:
            rec = reale(block_id=block_id, durata_s=durata_s,
                        profiler=profiler, p_pre=p_pre,
                        stop_event=stop_event, log=log)
        finally:
            if proprio is _MANCANTE:
                sessione.__dict__.pop("read_measurement_edge", None)
            else:
                sessione.read_measurement_edge = proprio
        entry: Dict = {"block_id": block_id, "t0_mono": None,
                       "t1_mono": None, "n_samples": 0,
                       "samples": [], "power_w": [], "reason": ""}
        if len(bordi) != 2:
            entry["reason"] = (f"bordi catturati {len(bordi)} (attesi 2): "
                               "serie non ricostruibile")
            catturate.append(entry)
            return rec
        e0, mono0 = bordi[0]
        _e1, mono1 = bordi[1]
        try:
            t0 = float(e0.get("t_counter_mono"))
        except (TypeError, ValueError):
            t0 = mono0
        entry["t0_mono"], entry["t1_mono"] = t0, mono1
        try:
            campioni = sessione.samples_between(t0, mono1)
        except Exception as exc:
            entry["reason"] = f"samples_between non disponibile: {exc}"
            catturate.append(entry)
            return rec
        dicts = [_campione_dict(s) for s in campioni]
        entry["samples"] = dicts
        entry["n_samples"] = len(dicts)
        entry["power_w"] = _serie_potenza(dicts)
        if not dicts:
            entry["reason"] = "nessun campione nella finestra passiva"
        catturate.append(entry)
        return rec

    return reale, wrapper, catturate


def _attendi_quiete(*, consecutive: Optional[int] = None,
                    cap_s: Optional[float] = None,
                    poll_s: float = QUIET_POLL_S,
                    campiona=None, top_fn=None,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep,
                    on_log=None) -> Dict:
    """Precondizione di quiete: il blocco non parte se la macchina e' carica.

    Perche' esiste. Il gate del 2026-11-07 e' fallito con
    ``background_load=True`` su 5 controlli su 6 (CompatTelRunner,
    SearchIndexer, Defender, Chrome, Qoder): P1.4 registra il flag nel
    verbale ma non impedisce la partenza. Questa e' una precondizione di
    ESECUZIONE, lato tool: il criterio F.12, le soglie e il disegno non si
    muovono, e il runner non cambia comportamento.

    Meccanica. Ogni lettura e' ``ms.total_cpu_samples()`` (~3 s di
    osservazione, P1.4); ``ms.background_load_from_samples`` dice se e'
    rumorosa (persistenza sopra la soglia congelata di P1.4, non un picco
    singolo). Quiete = ``consecutive`` letture consecutive non rumorose;
    una lettura rumorosa AZZERA il conteggio. Al tetto ``cap_s`` senza
    quiete: ``SystemExit`` — main() lo gira in [ARRESTO] exit 3, la
    campagna non parte e non prosegue in silenzio. Diverso dal cooldown
    (che al tetto RITORNA con timed_out, perche' il blocco si puo' comunque
    misurare e flaggare): qui partire senza quiete sarebbe un disegno
    diverso da quello dichiarato, scoperto solo dopo i dati.

    Iniezione. ``clock``/``sleep`` sono legati alla def come in
    ``cooldown_to_baseline``; ``campiona``/``top_fn`` si risolvono alla
    CHIAMATA (sentinella None) cosi' i test li sostituiscono sul modulo
    senza hardware. I default delle costanti sono quelli congelati nel
    piano (``plan_payload``), e ``_verifica_piano`` li confronta.

    Restituisce ``quiet_wait_s`` (attesa misurata), ``quiet_letture``
    (letture eseguite) e ``top_processes`` (top-5 al momento della
    partenza, ``ms.sample_top_processes``): finiscono in ``runs`` per
    blocco, nel report e in ``gate_result_frozen.json``.
    """
    if consecutive is None:
        consecutive = QUIET_CONSECUTIVE
    if cap_s is None:
        cap_s = QUIET_CAP_S
    if campiona is None:
        campiona = ms.total_cpu_samples
    if top_fn is None:
        top_fn = ms.sample_top_processes
    if consecutive < 1:
        raise ValueError(
            f"consecutive={consecutive}: serve almeno una lettura")
    log = on_log or (lambda m: None)
    t0 = clock()
    consec = 0
    letture = 0
    while True:
        campioni = campiona()
        rumorosa = ms.background_load_from_samples(campioni)
        letture += 1
        if rumorosa:
            consec = 0
            log(f"[QUIETE] lettura {letture}: background_load=True "
                f"(campioni={campioni}), conteggio azzerato")
        else:
            consec += 1
        if consec >= consecutive:
            break
        if clock() - t0 >= cap_s:
            raise SystemExit(
                f"precondizione di quiete non raggiunta entro {cap_s:g} s "
                f"({letture} letture, ne servono {consecutive} consecutive "
                "non rumorose): background_load resta True. Il blocco NON "
                "parte e la campagna si ferma — procedere in silenzio "
                "sarebbe un disegno diverso da quello dichiarato.")
        sleep(poll_s)
    attesa = clock() - t0
    top = top_fn()
    log(f"[QUIETE] raggiunta dopo {attesa:.1f} s ({letture} letture); "
        f"top-5 alla partenza: {top}")
    return {"quiet_wait_s": attesa, "quiet_letture": letture,
            "top_processes": top}


def cmd_execute(model: str) -> Dict:
    plan = _verifica_piano()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    for p in (rows_path, blocks_path):
        if p.exists() and p.stat().st_size > 0:
            raise SystemExit(
                f"output gia' presente: {p}. Il gate misura una campagna "
                "dichiarata: rimuovi l'archivio o cambia data (--date), non "
                "accodare.")

    reale, wrapper, catturati = _cattura_riepiloghi()
    reale_cw, wrapper_cw, serie = _cattura_serie_controllo()
    runs: List[Dict] = []
    v4.export_summary_csv = wrapper
    v4._run_control_window = wrapper_cw
    try:
        for b in plan["blocks"]:
            initial_pre: Optional[float] = None
            if b["arm"] == "control":
                initial_pre = _ultima_baseline_pre(blocks_path)
                if initial_pre is None:
                    raise SystemExit(
                        f"propagazione interrotta prima di {b['label']}: "
                        "nessuna baseline_pre_w valida dall'ultimo blocco. Il "
                        "controllo partirebbe senza cooldown verso il carico: "
                        "disegno diverso da quello dichiarato, mi fermo.")
            kw, prompt = _call_kwargs(b, initial_pre, rows_path, blocks_path)
            print(f"[BLOCCO {b['index']:>2}] {b['label']} ({b['arm']}, "
                  f"{b['pair_id']})"
                  + (f" P_pre_ref={initial_pre:.6f} W" if initial_pre else ""),
                  flush=True)
            # Precondizione PRIMA di ogni invocazione, load E control:
            # una macchina carica non parte (check E del piano).
            quiet = _attendi_quiete(on_log=lambda m: print(m, flush=True))
            summary = v4.run_v4_benchmark([model], [prompt], **kw)
            rec = dict(catturati[-1]) if catturati else {}
            run_rec = {
                "index": b["index"], "label": b["label"], "arm": b["arm"],
                "pair_id": b["pair_id"], "run_id": summary["run_id"],
                "batch_id": summary["batch_id"],
                "block_id": rec.get("block_id", ""),
                "records": summary.get("records"),
                "blocks": summary.get("blocks"),
                "errors": summary.get("errors"),
                "invalidated_blocks": summary.get("invalidated_blocks"),
                "initial_last_pre_w": initial_pre,
                "block_baseline_pre_w": rec.get("baseline_pre_w", ""),
                "block_cooldown_timeout": rec.get("cooldown_timeout", ""),
                "quiet_wait_s": quiet["quiet_wait_s"],
                "quiet_letture": quiet["quiet_letture"],
                "quiet_top_processes": quiet["top_processes"],
                "background_load_before": summary.get("background_load_before"),
                "background_load_after": summary.get("background_load_after"),
            }
            runs.append(run_rec)
            if summary.get("errors"):
                raise SystemExit(
                    f"[ERRORE] {b['label']}: {summary['errors']} — K=1, mi "
                    "fermo prima del blocco successivo (Emenda 8)")
            if summary.get("invalidated_blocks"):
                raise SystemExit(
                    f"[ERRORE] {b['label']}: blocco invalidato per guasto "
                    f"(K={K_MAX}): {summary.get('stopped_by_k', '')} — mi "
                    "fermo")
            if b["arm"] == "control":
                cd = run_rec["block_cooldown_timeout"]
                if cd == "":
                    raise SystemExit(
                        f"[ERRORE] {b['label']}: cooldown non eseguito "
                        f"nonostante P_pre propagato ({initial_pre} W) — "
                        "cella cooldown_timeout vuota. La propagazione non ha "
                        "raggiunto il runner: mi fermo prima di dichiarare "
                        "il gate.")
    finally:
        v4.export_summary_csv = reale
        v4._run_control_window = reale_cw

    controls = _filtra_controlli(catturati)
    if len(controls) != N_COPPIE:
        raise SystemExit(
            f"controlli catturati {len(controls)} su {N_COPPIE}: il gate "
            "sarebbe valutato su un disegno diverso da quello dichiarato")
    _scrittura_atomica(ARCHIVE_DIR / BLOCKS_JSON_NAME, controls)
    if len(serie) != N_COPPIE:
        print(f"[AVVISO] serie di potenza catturate {len(serie)} su "
              f"{N_COPPIE}: diagnostica incompleta, il gate non cambia",
              flush=True)
    _scrittura_atomica(ARCHIVE_DIR / SERIES_NAME, serie)
    q = cg.evaluate_gate(controls, n_pairs=N_COPPIE)
    analysis = q.to_dict()
    analysis.update({
        "pilot": "P4.4 gate",
        "model": model,
        "dt_nominal_s": DT_NOM_FROZEN,
        "order_seed": SEED,
        "geometry": GEOMETRY,
        "quiet_precondition": {"consecutive": QUIET_CONSECUTIVE,
                               "cap_s": QUIET_CAP_S},
        "runs": runs,
        "results_csv": str(rows_path),
        "block_summary_csv": str(blocks_path),
        "blocks_controllo_json": str(ARCHIVE_DIR / BLOCKS_JSON_NAME),
        "control_power_series_json": str(ARCHIVE_DIR / SERIES_NAME),
        "series_counts": {s["block_id"]: s["n_samples"] for s in serie},
        "run_ids": [r["run_id"] for r in runs],
        "git_head": _git_head(),
        "runner_sha256": _sha256(MODULE_DIR / "benchmark_v4.py"),
        "metadata_path": str(config.CSV_RUN_METADATA_PATH),
    })
    # Grandezze riportate, non criterio: viaggiano nell'analysis e quindi
    # nel freeze, accanto al verdetto F.12 che non toccano.
    analysis["grandezze_riportate"] = _grandezze_riportate(
        analysis["controls"], runs)
    _scrittura_atomica(ARCHIVE_DIR / ANALYSIS_NAME, analysis)
    _scrittura_atomica(ARCHIVE_DIR / FREEZE_NAME, analysis)
    _write_report(analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False), flush=True)
    return analysis


# Quantili t di Student, coda superiore 0.025 (CI95 bilaterale), df 1-30:
# tavola standard della distribuzione t (NIST/SEMATECH e-Handbook, tabella
# dei quantili t; valori arrotondati alla terza cifra). Usata SOLO se scipy
# non e' installato: la provenienza e' dichiarata per ogni calcolo.
_T_TABLE_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}
_T_INF_975 = 1.960  # df>30 senza scipy: approssimazione normale, dichiarata


def _quantile_t_975(df: int) -> Tuple[float, str]:
    """Quantile t(0.975, df) con la sua provenienza: scipy se c'e',
    altrimenti tabella 1-30; oltre 30, 1.960 (approssimazione normale).
    La provenienza viaggia col numero: un quantile senza fonte non e'
    verificabile da un terzo."""
    if df < 1:
        raise ValueError(f"df={df}: i gradi di liberta' sono n-1, n>=2")
    if _scipy_t is not None:
        return float(_scipy_t.ppf(0.975, df)), "scipy"
    if df <= 30:
        return _T_TABLE_975[df], "tabella"
    return _T_INF_975, "tabella (df>30: 1.960, approssimazione normale)"


def _statistiche_descrittive(valori: Sequence[float]) -> Dict:
    """Media, sd campionaria (ddof=1), SE e CI95 t di Student.

    Descrittiva FRA blocchi di controllo: non e' la terna di baseline di
    P4.12 (lì a n=3 non si stima una varianza, e quel divieto resta), non
    entra nello schema CSV e non decide l'esito del gate. Con n<2 la sd
    non e' calcolabile: None dichiarata, non zero. CI95 = media +/-
    t(0.975, n-1) * SE, con la provenienza del quantile registrata.
    """
    n = len(valori)
    out: Dict = {"n": n, "media": None, "sd": None, "se": None,
                 "ci95": None, "t_quantile": None, "t_provenienza": ""}
    if n == 0:
        out["t_provenienza"] = "nessun valore"
        return out
    media = sum(valori) / n
    out["media"] = media
    if n < 2:
        out["t_provenienza"] = "n<2: sd non calcolabile"
        return out
    sd = math.sqrt(sum((x - media) ** 2 for x in valori) / (n - 1))
    se = sd / math.sqrt(n)
    q, prov = _quantile_t_975(n - 1)
    out.update(sd=sd, se=se, ci95=[media - q * se, media + q * se],
               t_quantile=q, t_provenienza=prov)
    return out


def _grandezze_riportate(controls: Sequence[Mapping],
                         runs: Sequence[Mapping]) -> Dict:
    """E_net/dt_W per TUTTI i controlli, anche non utilizzabili, e le
    statistiche descrittive su tutti e sui soli utilizzabili.

    Non decide l'esito: il gate resta F.12. Un controllo non utilizzabile
    non sparisce dal report — il suo rapporto e' riportato, il criterio lo
    esclude. I flag ``background_load`` prima/dopo arrivano dai runs (il
    runner li espone nel riepilogo), matched per ``block_id``; un run
    assente lascia None, non inventa uno stato. dt_W=0 o assente, E_net
    non numerico: nessun numero (None), non una divisione forzata.
    """
    run_per_blocco = {r.get("block_id", ""): r for r in runs}
    per_controllo: List[Dict] = []
    tutti: List[float] = []
    utilizzabili: List[float] = []
    for c in controls:
        bid = str(c.get("block_id", "") or "")
        r = run_per_blocco.get(bid, {})
        e_net, dt = c.get("e_net_j"), c.get("dt_w_s")
        p_net: Optional[float] = None
        try:
            if e_net is not None and dt is not None and float(dt) != 0.0:
                p_net = float(e_net) / float(dt)
        except (TypeError, ValueError):
            p_net = None
        if p_net is not None and not math.isfinite(p_net):
            p_net = None
        per_controllo.append({
            "block_id": bid,
            "usable": bool(c.get("usable")),
            "e_net_j": e_net, "dt_w_s": dt, "p_net_w": p_net,
            "background_load_before": r.get("background_load_before"),
            "background_load_after": r.get("background_load_after"),
        })
        if p_net is not None:
            tutti.append(p_net)
            if c.get("usable"):
                utilizzabili.append(p_net)
    return {
        "per_controllo": per_controllo,
        "tutti": _statistiche_descrittive(tutti),
        "utilizzabili": _statistiche_descrittive(utilizzabili),
        "nota": ("grandezze descrittive fra blocchi di controllo: non "
                 "decidono l'esito del gate (F.12 invariato), non entrano "
                 "nello schema CSV. sd campionaria (ddof=1) su n blocchi, "
                 "non sulla terna di baseline di P4.12; CI95 = media +/- "
                 "t(0.975, n-1) * SE; n<2 -> sd None dichiarata."),
    }


def _flag_txt(v) -> str:
    """Il flag P1.4 nel report: True/False misurati, None = non rilevato.
    Un 'non rilevato' non si stampa come False."""
    if v is True:
        return "True"
    if v is False:
        return "False"
    return "non rilevato"


def _stats_txt(s: Mapping) -> str:
    """Riga di report per le statistiche: n, media, sd, SE, CI95 e la
    provenienza del quantile t. n<2 e n=0 sono dichiarati, non taciuti."""
    if s["n"] == 0:
        return "- n=0: nessun valore calcolabile\n"
    riga = f"- n={s['n']}, media={s['media']:.6f} W"
    if s["sd"] is None:
        return riga + "; sd/SE/CI95 non calcolabili (n<2), dichiarati\n"
    lo, hi = s["ci95"]
    return (riga + f", sd={s['sd']:.6f} W, SE={s['se']:.6f} W, "
            f"CI95=[{lo:.6f}, {hi:.6f}] W "
            f"(t={s['t_quantile']:.4f}, provenienza: {s['t_provenienza']})\n")


def _write_report(data: Dict) -> None:
    summary = (f"gate: {data['status']}; controlli utilizzabili = "
               f"{data['controls_usable_n']}/{data['n_pairs']} coppie, "
               f"quorum = {data['quorum']}; chain_status = "
               f"'{data['chain_status']}'")
    with (ARCHIVE_DIR / REPORT_NAME).open("w", encoding="utf-8") as fh:
        fh.write("# Gate P4.4 load-versus-control\n\n")
        fh.write(f"- modello: `{data['model']}`\n")
        fh.write(f"- DT_NOM congelato = {data['dt_nominal_s']} s "
                 "(pilota P2.9, requisito 5)\n")
        fh.write(f"- order_seed dichiarato = {data['order_seed']} "
                 "(requisito 3)\n")
        fh.write("- geometria (12,32) (requisito 4)\n")
        fh.write("- 12 blocchi / 6 coppie, un blocco per invocazione\n\n")
        fh.write("## Risultato\n\n")
        fh.write(summary + "\n")
        pass_false = sum(1 for c in data["controls"]
                         if c["usable"] and c["block_pass"] is False)
        fh.write(f"- utilizzabili con block_pass=False: {pass_false}/"
                 f"{data['controls_usable_n']} (il criterio per blocco e' "
                 "riportato, non decide lo status del gate)\n\n")
        if data["bias_w"] is not None:
            fh.write(f"- bias_w = {data['bias_w']:.6f} W contro soglia "
                     f"mediana_c(budget_base_w) = "
                     f"{data['bias_threshold_w']:.6f} W\n\n")
        else:
            fh.write("- bias non calcolato: gate non eseguibile\n\n")
        fh.write("## Blocchi di controllo\n\n")
        run_per_blocco = {r.get("block_id", ""): r
                          for r in data.get("runs", [])}
        for c in data["controls"]:
            try:
                p_net_w = float(c["e_net_j"]) / float(c["dt_w_s"])
                p_net_txt = f"{p_net_w:.6f} W"
            except (TypeError, ValueError, ZeroDivisionError):
                p_net_txt = "n/d"
            fh.write(
                f"- {c['block_id']}: usable={c['usable']}, "
                f"unstable={c['control_unstable']}, "
                f"pre_range_w={c['pre_range_w']}, dP={c['dP']}, "
                f"E_net={c['e_net_j']} J, dt_W={c['dt_w_s']} s, "
                f"E_net/dt_W={p_net_txt}, "
                f"budget_base_j={c['budget_base_j']}, "
                f"budget_base_w={c['budget_base_w']} W, "
                f"window={c['window_source']}, block_pass={c['block_pass']}"
                + (f" — {c['reason']}" if c["reason"] else "") + "\n")
            r = run_per_blocco.get(c["block_id"], {})
            if r:
                fh.write(
                    f"  baseline: P_pre_ref propagata dal carico="
                    f"{r.get('initial_last_pre_w')} W, propria del blocco="
                    f"{r.get('block_baseline_pre_w')} W\n")
        g = data.get("grandezze_riportate")
        if g:
            fh.write("\n## Grandezze riportate, non criterio\n\n")
            fh.write("E_net/dt_W per TUTTI i controlli (anche non "
                     "utilizzabili) e statistiche descrittive fra blocchi: "
                     "media, sd campionaria (ddof=1), SE, CI95 t di "
                     "Student. Non decidono l'esito del gate, che resta "
                     "F.12; non entrano nello schema CSV. background_load "
                     "prima/dopo dal riepilogo del runner (P1.4).\n\n")
            fh.write("| blocco | utilizzabile | E_net/dt_W (W) | "
                     "background_load prima | dopo |\n")
            fh.write("|---|---|---|---|---|\n")
            for c in g["per_controllo"]:
                p = c["p_net_w"]
                p_txt = f"{p:.6f}" if p is not None else "n/d"
                fh.write(
                    f"| {c['block_id']} | {c['usable']} | {p_txt} | "
                    f"{_flag_txt(c['background_load_before'])} | "
                    f"{_flag_txt(c['background_load_after'])} |\n")
            for nome, stats in (("tutti i controlli", g["tutti"]),
                                ("soli utilizzabili", g["utilizzabili"])):
                fh.write(f"\n### Statistiche su {nome}\n\n")
                fh.write(_stats_txt(stats))
        fh.write("\n## Propagazione cooldown (scelta operativa)\n\n")
        for r in data["runs"]:
            if r["arm"] == "control":
                fh.write(
                    f"- {r['label']}: P_pre_ref="
                    f"{r['initial_last_pre_w']}, baseline propria del blocco="
                    f"{r.get('block_baseline_pre_w', '')}, cooldown_timeout="
                    f"'{r['block_cooldown_timeout']}'\n")
        fh.write("\n## Precondizione di quiete\n\n")
        q = data.get("quiet_precondition") or {}
        fh.write(f"Prima di OGNI blocco (load e control): "
                 f"{q.get('consecutive', QUIET_CONSECUTIVE)} letture "
                 "consecutive con background_load=False; una lettura "
                 "rumorosa azzera il conteggio; al tetto "
                 f"({q.get('cap_s', QUIET_CAP_S):g} s) il run si ferma. "
                 "Precondizione di esecuzione lato tool (P1.4): non entra "
                 "nel criterio F.12.\n\n")
        for r in data["runs"]:
            attesa = r.get("quiet_wait_s")
            attesa_txt = (f"{attesa:.1f} s"
                          if isinstance(attesa, (int, float)) else "n/d")
            top = r.get("quiet_top_processes") or []
            top_txt = ", ".join(
                f"{p.get('name', '?')} pid={p.get('pid', '?')} "
                f"({p.get('cpu_pct', '?')}%)" for p in top) or "nessuno"
            fh.write(
                f"- {r['label']} ({r['arm']}): attesa={attesa_txt}, "
                f"letture={r.get('quiet_letture', 'n/d')}, top-5 alla "
                f"partenza: {top_txt}\n")
        if data.get("bias_jtok_pct"):
            lo, hi = data["bias_jtok_pct"]
            fh.write("\n## Rapporto J/token (F.12, grandezza riportata)\n\n")
            fh.write(f"- bias = {lo:.3f}–{hi:.3f} % di J/token "
                     "(scala ancorata 1 W ~ 6–11%)\n")
        if data.get("reasons"):
            fh.write("\n## Ragioni\n\n")
            for motivo in data["reasons"]:
                fh.write(f"- {motivo}\n")
        if data.get("series_counts"):
            fh.write("\n## Serie di potenza grezza (diagnostica)\n\n")
            fh.write("Campioni del sampler nella finestra passiva "
                     "[t0, t1] del contatore; potenza = delta del "
                     "contatore cumulativo / delta t fra campioni "
                     "consecutivi. Diagnostica per distinguere deriva e "
                     "picchi: non entra nel criterio F.12.\n\n")
            for bid, n in data["series_counts"].items():
                fh.write(f"- {bid}: {n} campioni\n")
        fh.write("\n## Artefatti\n\n")
        fh.write(f"- results CSV: {data['results_csv']}\n")
        fh.write(f"- block summary CSV: {data['block_summary_csv']}\n")
        fh.write(f"- riepiloghi controllo (JSON, forma --blocks): "
                 f"{data['blocks_controllo_json']}\n")
        fh.write(f"- serie di potenza grezza dei controlli (JSON): "
                 f"{data.get('control_power_series_json', '')}\n")
        fh.write(f"- run ids: {', '.join(data['run_ids'])}\n")
        fh.write(f"- git head: {data['git_head']}\n")
        fh.write(f"- runner sha256: {data['runner_sha256']}\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate load-versus-control di P4.4 sulla v4")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="scrivi il piano PRIMA di misurare")
    p_plan.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_plan.add_argument("--date", default=DEFAULT_DATE,
                        help="etichetta della campagna YYYYMMDD: archivio e "
                             "results dedicati, disegno invariato")
    p_plan.add_argument("--seed", default=DEFAULT_SEED,
                        help="seme del disegno dichiarato nel piano "
                             "(default: la campagna 2026-11-07)")
    p_exec = sub.add_parser("execute",
                            help="esegui le dodici righe e valuta F.12")
    p_exec.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_exec.add_argument("--date", default=DEFAULT_DATE,
                        help="etichetta della campagna YYYYMMDD: deve essere "
                             "quella del plan dichiarato")
    p_exec.add_argument("--seed", default=DEFAULT_SEED,
                        help="seme del disegno: deve essere quello del plan "
                             "dichiarato, altrimenti execute si ferma")
    args = parser.parse_args(argv)
    _imposta_data(args.date)
    _imposta_seme(args.seed)
    if args.cmd == "plan":
        return cmd_plan(args.model)
    if args.cmd == "execute":
        try:
            r = cmd_execute(args.model)
        except SystemExit as e:
            if isinstance(e.code, int):
                raise
            print(f"[ARRESTO] {e.code}", file=sys.stderr, flush=True)
            return 3
        mapping = {"pass": 0, "fail": 1, "not-executable": 2}
        return mapping[r["status"]]
    parser.error("seguono solo plan/execute")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
