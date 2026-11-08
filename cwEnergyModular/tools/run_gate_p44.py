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
dichiarato, non randomizzato; ``order_seed='gate-seed-20261107'`` resta il
seme del disegno (requisito 3).

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
``plan_blocks()``, il seme o la durata congelata, quindi la verifica del piano
resta valida e un secondo run non richiede di editare il codice. Il risultato
congelato di una campagna non si sovrascrive: ``execute`` rifiuta output gia'
presenti.
"""
from __future__ import annotations
import argparse
import csv
import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent
sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import control_gate as cg  # noqa: E402

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
DEFAULT_MODEL = "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest"
K_MAX = 1                       # Emenda 8: sostituzione di un blocco
SEED = "gate-seed-20261107"     # requisito 3: seme del disegno, dichiarato
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
    if plan.get("order_seed") != SEED or plan.get("model") != DEFAULT_MODEL:
        raise SystemExit("seed o modello discostati dal piano dichiarato")
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
    runs: List[Dict] = []
    v4.export_summary_csv = wrapper
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

    controls = _filtra_controlli(catturati)
    if len(controls) != N_COPPIE:
        raise SystemExit(
            f"controlli catturati {len(controls)} su {N_COPPIE}: il gate "
            "sarebbe valutato su un disegno diverso da quello dichiarato")
    _scrittura_atomica(ARCHIVE_DIR / BLOCKS_JSON_NAME, controls)
    q = cg.evaluate_gate(controls, n_pairs=N_COPPIE)
    analysis = q.to_dict()
    analysis.update({
        "pilot": "P4.4 gate",
        "model": model,
        "dt_nominal_s": DT_NOM_FROZEN,
        "order_seed": SEED,
        "geometry": GEOMETRY,
        "runs": runs,
        "results_csv": str(rows_path),
        "block_summary_csv": str(blocks_path),
        "blocks_controllo_json": str(ARCHIVE_DIR / BLOCKS_JSON_NAME),
        "run_ids": [r["run_id"] for r in runs],
        "git_head": _git_head(),
        "runner_sha256": _sha256(MODULE_DIR / "benchmark_v4.py"),
        "metadata_path": str(config.CSV_RUN_METADATA_PATH),
    })
    _scrittura_atomica(ARCHIVE_DIR / ANALYSIS_NAME, analysis)
    _scrittura_atomica(ARCHIVE_DIR / FREEZE_NAME, analysis)
    _write_report(analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False), flush=True)
    return analysis


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
        fh.write(summary + "\n\n")
        if data["bias_w"] is not None:
            fh.write(f"- bias_w = {data['bias_w']:.6f} W contro soglia "
                     f"mediana_c(budget_base_w) = "
                     f"{data['bias_threshold_w']:.6f} W\n\n")
        else:
            fh.write("- bias non calcolato: gate non eseguibile\n\n")
        fh.write("## Blocchi di controllo\n\n")
        for c in data["controls"]:
            fh.write(
                f"- {c['block_id']}: usable={c['usable']}, "
                f"unstable={c['control_unstable']}, "
                f"pre_range_w={c['pre_range_w']}, dP={c['dP']}, "
                f"E_net={c['e_net_j']} J, dt_W={c['dt_w_s']} s, "
                f"budget_base_j={c['budget_base_j']}, "
                f"budget_base_w={c['budget_base_w']} W, "
                f"window={c['window_source']}, block_pass={c['block_pass']}"
                + (f" — {c['reason']}" if c["reason"] else "") + "\n")
        fh.write("\n## Propagazione cooldown (scelta operativa)\n\n")
        for r in data["runs"]:
            if r["arm"] == "control":
                fh.write(
                    f"- {r['label']}: P_pre_ref="
                    f"{r['initial_last_pre_w']}, cooldown_timeout="
                    f"'{r['block_cooldown_timeout']}'\n")
        if data.get("bias_jtok_pct"):
            lo, hi = data["bias_jtok_pct"]
            fh.write("\n## Rapporto J/token (F.12, grandezza riportata)\n\n")
            fh.write(f"- bias = {lo:.3f}–{hi:.3f} % di J/token "
                     "(scala ancorata 1 W ~ 6–11%)\n")
        if data.get("reasons"):
            fh.write("\n## Ragioni\n\n")
            for motivo in data["reasons"]:
                fh.write(f"- {motivo}\n")
        fh.write("\n## Artefatti\n\n")
        fh.write(f"- results CSV: {data['results_csv']}\n")
        fh.write(f"- block summary CSV: {data['block_summary_csv']}\n")
        fh.write(f"- riepiloghi controllo (JSON, forma --blocks): "
                 f"{data['blocks_controllo_json']}\n")
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
    p_exec = sub.add_parser("execute",
                            help="esegui le dodici righe e valuta F.12")
    p_exec.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_exec.add_argument("--date", default=DEFAULT_DATE,
                        help="etichetta della campagna YYYYMMDD: deve essere "
                             "quella del plan dichiarato")
    args = parser.parse_args(argv)
    _imposta_data(args.date)
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
