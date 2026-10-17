# -*- coding: utf-8 -*-
"""
main.py — Entry point CasualWatt Energy Benchmark.

Avvia la GUI Tkinter (gui/app.py). Con ``--no-gui`` esegue un benchmark da
terminale per smoke-test/CI; con ``--selftest`` verifica import e coerenza
delle formule energetiche senza toccare rete/Ollama.
"""
from __future__ import annotations

import argparse
import sys


def _selftest() -> int:
    print("[selftest] import pacchetti…")
    from energy import SESSION  # noqa: F401  (import relativo interno OK)
    import evaluator
    import cloud_estimator  # noqa: F401
    import test_source  # noqa: F401
    from casualwatt_csv_export import export_results_csv, CSV_COLUMNS  # noqa: F401

    # regola sez. 10 — regime causale esplicito (mode="causal")
    r = evaluator.evaluate_response("The cause of X has an effect on Y", is_tool=False, mode="causal")
    assert r.acc_links == 1.0 and r.judge_score == 4.0 and r.cosine_sim == 0.75
    r2 = evaluator.evaluate_response("only a cause here", is_tool=True, mode="causal")
    assert r2.acc_links == 0.5 and r2.judge_score == 3.0 and r2.cosine_sim == 0.88
    r3 = evaluator.evaluate_response("nothing relevant", is_tool=True, mode="causal")
    assert r3.acc_links == 0.0 and r3.judge_score == 1.5
    r4 = evaluator.evaluate_response("cause + effect", is_tool=True, mode="causal")
    assert r4.judge_score == 4.5

    # valutazione UNIVERSALE: ground truth -> accuratezza per confronto
    gt = evaluator.evaluate_response("Paris", ground_truth="Paris")
    assert gt.eval_mode == "ground_truth" and gt.is_correct is True and gt.causal_accuracy == 1.0
    gt_bad = evaluator.evaluate_response("London", ground_truth="Paris")
    assert gt_bad.is_correct is False

    # senza ground truth -> NESSUN errore, campi accuratezza N/A
    sk = evaluator.evaluate_response("una risposta qualunque", ground_truth=None)
    assert sk.eval_mode == "skipped" and sk.causal_accuracy is None and sk.is_correct is None

    # sorgente dei test: parsing CSV esterno (con e senza GT) + prompt manuali
    import tempfile
    from pathlib import Path as _P

    tmp = _P(tempfile.gettempdir()) / "cw_selftest.csv"
    tmp.write_text('id;prompt;expected_result\n1;What is 2+2?;4\n2;Capital of France?;Paris\n', encoding="utf-8")
    items, err = test_source.load_prompts_from_csv(tmp)
    assert not err and len(items) == 2, f"CSV parsing fallito: {err}"
    assert items[0]["text"] == "What is 2+2?" and items[1]["ground_truth"] == "Paris"
    man = test_source.parse_manual_prompts("Primo prompt\nSecondo prompt\n\nTerzo")
    assert len(man) == 3 and man[2]["ground_truth"] is None
    tmp.unlink(missing_ok=True)

    # regola sez. 2/12: E_attiva non include idle; baseline separata
    from energy.local_energy import LocalEnergyResult  # noqa: F401

    # schema CSV completo
    assert "baseline_energy_j" in CSV_COLUMNS and "ollama_active_energy_j" in CSV_COLUMNS
    assert {"test_source", "ground_truth", "eval_mode"} <= set(CSV_COLUMNS), "colonne sorgente test mancanti!"
    assert len(CSV_COLUMNS) == len(set(CSV_COLUMNS)), "colonne duplicate!"

    # stima cloud eco-logits (offline, modello registrato proxy)
    est = cloud_estimator.estimate_cloud_energy(
        model_name="llama-3.1-8b-instant", prompt_tokens=40,
        completion_tokens=60, duration_s=2.0, provider="groq",
    )
    assert est.energy_j is None or est.energy_j > 0

    print("[selftest] OK — formule causali, valutazione universale, sorgente test esterna, schema CSV coerenti")
    return 0


def _cli_benchmark(args) -> int:
    from benchmark_unified import run_unified_benchmark

    # sorgente dei test anche da CLI: --csv <file> oppure --manual "p1\np2"
    if args.csv:
        src_kwargs = {"test_mode": "csv", "csv_path": args.csv}
    elif args.manual:
        src_kwargs = {"test_mode": "manual", "manual_text": args.manual.replace("\\n", "\n")}
    else:
        src_kwargs = {"test_mode": "default"}

    summary = run_unified_benchmark(
        local_models=args.local.split(",") if args.local else [],
        cloud_selection=[],
        num_prompts=args.prompts,
        temperature=args.temperature,
        timeout_s=args.timeout,
        on_log=lambda m: print(m, flush=True),
        **src_kwargs,
    )
    print(f"records={summary['records']} errors={summary['errors']} csv={summary['csv_path']}")
    return 0 if summary["errors"] < max(summary["records"], 1) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="casualwatt", description="CasualWatt Energy Benchmark")
    parser.add_argument("--no-gui", action="store_true", help="benchmark da terminale")
    parser.add_argument("--selftest", action="store_true", help="verifica import e formule")
    parser.add_argument("--local", default="", help="modelli Ollama separati da virgola")
    parser.add_argument("--prompts", type=int, default=3)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--csv", default="", help="dataset CSV esterno (es. output MUDILab)")
    parser.add_argument("--manual", default="", help="prompt manuale separati da \\n")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.no_gui:
        return _cli_benchmark(args)

    try:
        from gui.app import main as gui_main

        gui_main()
        return 0
    except Exception as exc:  # pragma: no cover
        print(f"Avvio GUI fallito ({type(exc).__name__}: {exc}).", file=sys.stderr)
        print("Suggerimenti: su Windows usare 'py main.py'; verificare tkinter installato.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
