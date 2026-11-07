# -*- coding: utf-8 -*-
"""tools/run_gate_p44.py — il gate load-versus-control di P4.4 sulla v4.

Perche' esiste. P4.4 campagna di validazione precede quella principale: sei
coppie di blocchi (emendamento del 2026-10-24) con due blocchi per coppia
— uno di carico (``block_kind='load'``, m richieste, num_predict=32) e uno di
controllo (``block_kind='control'``, m=3 con ``control=True``): il blocco di
controllo non invia richieste ma una finestra passativa lunga
``dt_nominal_s`` (congelato P4.4 requisito 5 = pilot P2.9, 2.930748 s). L'esito
viene al criterio di F.12 di ``control_gate.evaluate_gate`` restituisce
``status=pass``/``fail``/``not-executable``, ``chain_status`` e il bias aggregato.

Il disegno è dichiarato PRIMA dei dati e lo strumento riflette solo P1.5 base
del runner, la struttura P4.3/P4.4/P4.5 richieste e l'ordine randomizzato
con ``order_seed='gate-seed-20261107'`` (confermato dal test
``tests/test_controllo_p44_v4.py``). ``K=1`` / ``substitution_seed='p44-<label>'``
per Emenda 8: a causa del contatore guasto il runner si invalida col primo errore.

Un singolo ``run_v4_benchmark`` per coppia (``blocks_per_point=2``) produce i
due blocchi della coppia: il controllo ha la calibrazione pre del blocco
carico come riferimento di cooldown (P4.4 requisito 7). In totale 6 run × 2 blocci =
12 blocchi = sei coppie.
"""
from __future__ import annotations
import argparse
import csv
import datetime as _dt
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent
sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(REPO_ROOT))

from config import DEFAULT_TIMEOUT_S, DEFAULT_TEMPERATURE  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import control_gate as cg  # noqa: E402

P44_DATE = "20261107"
ARCHIVE_DIR = REPO_ROOT / f"experiment_results/p44_gate_{P44_DATE}"
RESULTS_DIR = MODULE_DIR / f"results/p44_gate_{P44_DATE}"
ROWS_NAME = "casualwatt_v4_results_p44.csv"
BLOCKS_NAME = "casualwatt_v4_block_summary_p44.csv"
RUNS_NAME = "runs.json"
PLAN_NAME = "plan.json"
ANALYSIS_NAME = "analysis.json"
REPORT_NAME = "p44_gate_report.md"
FREEZE_NAME = "gate_result_frozen.json"
DEFAULT_MODEL = "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest"
K_MAX = 1                       # Emenda 8: sostituzione di un blocco
SEED = "gate-seed-20261107"     # ordine congelato
DT_NOM_FROZEN = 2.930748       # pilot P2.9, congelato
GEOMETRY = "12,32"             # conferma operativa di P3.5
NUM_CTX = 8192
LOAD_PROMPT = "Spiega in una frase cos'e' un watt."   # n input ~51 token
BLOCKS_PER_POINT = 2            # 2 blocchi per coppia = 6 run × 2 = 12 blocchi
PAIRS = list(range(6))           # coppia i (carico) j (controllo): 0..2..5


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


def plan_payload() -> Dict:
    """Disegno dichiarato. Tutto dipende da P2.9: DT_NOM e' il pilota."""
    points = []
    labels = []
    for k in range(6):
        pid = f"pair{k}__p{k}"
        prom = {"id": pid, "text": LOAD_PROMPT, "answer_type": "auto",
                "source": "p44_gate"}
        points.append({"model": DEFAULT_MODEL, "prompt": prom,
                        "point_id": pid, "k": 0, "attempt": 1, "replaced": ""})
        if k % 2 == 0:
            labels.append((f"carico-{k}", "load"))
        else:
            labels.append((f"controllo-{k//2}", "control"))
    # Ogni run gestira' le due finestre della stessa coppia.
    dichiarati = []
    for k in range(6):
        core = (labels[k][0], labels[k][1])
        pairs = [(f"p{i}", f"pair{i}") for i in range(6)]
        if core[1] == "load":
            b = dict(label=f"{core[0]}(load)", arm="load",
                     prompt_id=f"load-{k}", m=32, num_predict=32,
                     use_nonce=True)
            prom = {"id": f"load-{k}", "text": LOAD_PROMPT,
                    "answer_type": "auto", "source": "p44_gate"}
        else:
            b = dict(label=f"{core[0]}(ctrl)", arm="control",
                     prompt_id=f"ctrl-{k}", m=3, num_predict=1,
                     use_nonce=True)
            prom = {"id": f"ctrl-{k}", "text": "", "answer_type": "auto",
                    "source": "gate_control"}
        b["points"] = [{"model": DEFAULT_MODEL, "prompt": prom,
                        "point_id": f"pair{k}__p{k}", "k": 0,
                        "attempt": 1, "replaced": ""}]
        dichiarati.append(dict(b))
    return {
        "pilot": "P4.4 gate",
        "declared_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "model": DEFAULT_MODEL, "temperature": DEFAULT_TEMPERATURE,
        "timeout_s": DEFAULT_TIMEOUT_S, "num_ctx": NUM_CTX,
        "order_seed": SEED,
        "emenda8": {"max_invalidated_blocks": K_MAX,
                    "substitution_seed": f"p44-{labels[0][0]}"},
        "geometry": GEOMETRY,
        "checks": {
            "A": ("sei coppie di blocchi; ogni coppia ha un blocco load m=32 "
                  "e un blocco control m=3 con control=True"),
            "B": (f"geometria operativa confermata sul report; DT_NOM uscita "
                  "congelata P4.4 requisito 5"),
            "C": ("ordine seed = gate-seed-20261107 (riconosciuto da "
                  "test_controllo_p44_v4.py)"),
        },
        "dt_nominal_rule": ("3 x mediana(duration_s) su TUTTE righe valide del "
                            "pilot P2.9; DT_NOM = 2.930748 s, congelato e "
                            "anch'esso citato percorso/sha256/run id/HEAD"),
        "blocks": dichiarati,
        "outputs": {"results_csv": str(RESULTS_DIR / ROWS_NAME),
                    "block_summary_csv": str(RESULTS_DIR / BLOCKS_NAME)},
        "git_head": _git_head(),
    }


def cmd_plan(model: str) -> int:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _scrittura_atomica(ARCHIVE_DIR / PLAN_NAME, plan_payload())
    plan = plan_payload()
    print("[OK] piano scritto:", ARCHIVE_DIR / PLAN_NAME)
    for b in plan["blocks"]:
        side = "load" if b["arm"] == "load" else "control"
        txt = (LOAD_PROMPT if b["arm"] == "load" else "")
        words = len(txt.split()) if txt else 0
        print(f"  {b['label']:>2}: {side} m={b['m']} num_predict={b['num_predict']} "
              f"nonce={'on' if b['use_nonce'] else 'off'} parole={words}", flush=True)
    return 0


def _meta_metadata_path() -> Path:
    import config
    return config.CSV_RUN_METADATA_PATH


def _ultimo_metadata(run_id: str) -> Optional[Dict]:
    path = _meta_metadata_path()
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as fh:
        righe = [r for r in csv.DictReader(fh) if r.get("run_id") == run_id]
    return righe[-1] if righe else None


def _extract_control_blocks(path: Path) -> List[Mapping]:
    """Legge i riepiloghi dei blocchi di controllo da ``block_summary.csv``."""
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise SystemExit(f"ripresa riepiloghi blocco assente o vuota: {path}")
    out = []
    for r in rows:
        if str(r.get("block_kind", "") or "") == "control":
            c = dict(r)
            c.pop("notes", None)  # cancelliamo notes raggruppate
            out.append(c)
    if not out:
        raise SystemExit(
            f"nessun blocco di controllo scritto in {path}: gate non eseguito"
            " (quorum da scartare)")
    return out


def cmd_execute(model: str) -> Dict:
    plan = plan_payload()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    # Verifica esplicita dei valori congelati P4.4 su ogni blocco del piano.
    # Il confronto "expected != b" di prima era una forma di auto-verifica
    # perche' expected era costruito estraendo le stesse chiavi da b, quindi
    # il fallimento era strutturale: qui si confronta contro i valori
    # prescritti dal protocollo, non contro il payload stesso.
    for b in plan["blocks"]:
        if b["arm"] == "load":
            ok = (b["m"] == 32 and b["num_predict"] == 32
                  and b["use_nonce"] is True)
        elif b["arm"] == "control":
            ok = (b["m"] == 3 and b["num_predict"] == 1
                  and b["use_nonce"] is True)
        else:
            raise SystemExit(
                f"blocco {b['label']}: arm={b['arm']!r} non ammesso "
                "(atteso load|control)")
        if not ok:
            raise SystemExit(
                f"blocco {b['label']} ({b['arm']}): m={b['m']} "
                f"num_predict={b['num_predict']} use_nonce={b['use_nonce']} "
                "- P4.4 vuole load m=32/np=32, control m=3/np=1")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    runs: List[Dict] = []
    errors: List[str] = []
    for k in range(PAIRS):
        mid = labels = None
        # label corrente della run: carico o controllo della coppia k
        current = ("carico-" if k % 2 == 0 else "controllo-") + str(k // 2 + 1)
        prom = ({"id": f"load-{k}", "text": LOAD_PROMPT,
                  "answer_type": "auto", "source": "p44_gate"}
                if current.startswith("carico-")
                else {"id": f"ctrl-{k}", "text": "",
                      "answer_type": "auto", "source": "gate_control"})
        summary = v4.run_v4_benchmark(
            [DEFAULT_MODEL], [prom],
            m=32 if current.startswith("carico-") else 3,
            blocks_per_point=BLOCKS_PER_POINT,
            num_predict=32 if current.startswith("carico-") else 1,
            num_ctx=NUM_CTX, temperature=DEFAULT_TEMPERATURE,
            timeout_s=DEFAULT_TIMEOUT_S, batch_id=f"p44-{current}",
            block_kind=current.startswith("carico-") and "load"
                      or "control",
            pair_id=f"pair-{k}", order_seed=SEED,
            dt_nominal_s=str(DT_NOM_FROZEN),
            max_invalidated_blocks=K_MAX,
            substitution_seed=f"p44-{current}",
            results_path=rows_path, block_summary_path=blocks_path,
            on_log=lambda m: print(m, flush=True))
        meta = _ultimo_metadata(summary["run_id"]) or {}
        runs.append({"label": current, "arm": current.startswith("carico-")
                     and "load" or "control", "m": 32 if current.startswith("carico-")
                     else 3, "num_predict": 32 if current.startswith("carico-")
                     else 1, "use_nonce": True, "run_id": summary["run_id"],
                     "batch_id": summary["batch_id"], "records": summary.get(
                        "records"), "blocks": summary.get("blocks"),
                     "errors": summary.get("errors"),
                     "invalidated_blocks": summary.get("invalidated_blocks"),
                     "started_at": meta.get("started_at", ""),
                     "finished_at": meta.get("finished_at", ""),
                     "notes": meta.get("notes", "")})
        if summary.get("errors"):
            errors.append(f"{current}: {summary['errors']}")
            print(f"[ERRORE] {current}: {summary['errors']}", file=sys.stderr)

    if errors:
        raise SystemExit(3)
    controls = _extract_control_blocks(blocks_path)
    q = cg.evaluate_gate(controls, n_pairs=len(PAIRS))
    analysis = {
        "pilot": "P4.4 gate",
        "model": DEFAULT_MODEL,
        "dt_nominal_s": DT_NOM_FROZEN,
        "order_seed": SEED,
        "geometry": GEOMETRY,
        "controls_usable_n": q.controls_usable_n,
        "n_pairs": len(PAIRS),
        "quorum": q.quorum,
        "controls": [dict(c) for c in q.controls],
        "bias_w": q.bias_w,
        "bias_threshold_w": q.bias_threshold_w,
        "bias_jtok_pct": list(q.bias_jtok_pct),
        "chain_status": q.chain_status,
        "status": q.status,
        "reasons": list(q.reasons),
        "runs": runs,
        "fake_results_csv": str(rows_path),
        "fake_block_summary_csv": str(blocks_path),
        "fake_run_ids": [r["run_id"] for r in runs],
        "fake_block_ids": [r["run_id"] for r in runs],
        "fake_git_head": _git_head(),
        "fake_metadata_path": str(_meta_metadata_path()),
    }
    _scrittura_atomica(ARCHIVE_DIR / ANALYSIS_NAME, analysis)
    _scrittura_atomica(ARCHIVE_DIR / FREEZE_NAME, analysis)
    _write_report(analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False), flush=True)
    return analysis


def _write_report(data: Dict) -> None:
    controls_usable = data["controls_usable_n"]
    n_pairs = data["n_pairs"]
    q = data["status"]
    summary = (f"gate: {q}; controls_usable={controls_usable}/{n_pairs}, "
               f"quorum={data['quorum']}, chain_status={data['chain_status']}; "
               f"bias_w={data['bias_w']}; threshold={data['bias_threshold_w']}");
    with open(ARCHIVE_DIR / REPORT_NAME, "w", encoding="utf-8") as fh:
        fh.write(
            "# Gate P4.4 load-versus-control — 2026-11-07\n\n")
        fh.write(f"- modello: `{data['model']}`\n")
        fh.write(f"- DT_NOM congelato = {data['dt_nominal_s']} s (pilota P2.9)\n")
        fh.write(f"- ordine = {data['order_seed']}\n")
        fh.write(f"- geometria confermata (12,32)\n\n")
        fh.write("## Risultato\n\n")
        fh.write(summary + "\n\n")
        for c in data["controls"]:
            fh.write(
                f"- blocco {c['block_id']}: usable={c['usable']}, "
                f"unstable={c['control_unstable']}, "
                f"pre_range={c['pre_range_w']}, dP={c['dP']}, "
                f"|E_net,control|={c['e_net_j']}, "
                f"budget_base_j={c['budget_base_j']}, "
                f"budget_base_w={c['budget_base_w']}, "
                f"block_pass={c['block_pass']}\n")
        fh.write("\n## Rapporto J/token (F.12)\n\n")
        if data["bias_jtok_pct"][0] is not None:
            fh.write(
                f"- bias_w={data['bias_w']:.4f} W;\n"
                f"  jtok_pct_lo={data['bias_jtok_pct'][0]:.3f},"
                f" jtok_pct_hi={data['bias_jtok_pct'][1]:.3f}\n\n")
        else:
            fh.write("- gate non eseguibile: bias assente\n\n")
        fh.write("## Artefatti\n\n")
        fh.write(f"- results CSV: {data['fake_results_csv']}\n")
        fh.write(f"- block summary CSV: {data['fake_block_summary_csv']}\n")
        fh.write(f"- runs: {len(data['runs'])}\n")
        fh.write(f"- run ids: {data['fake_run_ids']}\n")
        fh.write(f"- git head: {data['fake_git_head']}\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate load-versus-control di P4.4 sulla v4")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="scrivi il piano PRIMA di misurare")
    p_plan.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_exec = sub.add_parser("execute",
                            help="esegui le sei coppie e valuta F.12")
    p_exec.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    args = parser.parse_args(argv)
    if args.cmd == "plan":
        return cmd_plan(args.model)
    if args.cmd == "execute":
        r = cmd_execute(args.model)
        mapping = {"pass": 0, "fail": 1, "not-executable": 2}
        return mapping[r["status"]]
    parser.error("seguono solo plan/execute")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
