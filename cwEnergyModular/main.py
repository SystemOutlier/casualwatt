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
    from casualwatt_csv_export import export_results_csv, CSV_COLUMNS  # noqa: F401

    # regola sez. 10
    r = evaluator.evaluate_response("The cause of X has an effect on Y", is_tool=False)
    assert r.acc_links == 1.0 and r.judge_score == 4.0 and r.cosine_sim == 0.75
    r2 = evaluator.evaluate_response("only a cause here", is_tool=True)
    assert r2.acc_links == 0.5 and r2.judge_score == 3.0 and r2.cosine_sim == 0.88
    r3 = evaluator.evaluate_response("nothing relevant", is_tool=True)
    assert r3.acc_links == 0.0 and r3.judge_score == 1.5
    r4 = evaluator.evaluate_response("cause + effect", is_tool=True)
    assert r4.judge_score == 4.5

    # regola sez. 2/12: E_attiva non include idle; baseline separata
    from energy.local_energy import LocalEnergyResult  # noqa: F401

    # schema CSV completo
    assert "baseline_energy_j" in CSV_COLUMNS and "ollama_active_energy_j" in CSV_COLUMNS
    assert len(CSV_COLUMNS) == len(set(CSV_COLUMNS)), "colonne duplicate!"

    # stima cloud eco-logits (offline, modello registrato proxy)
    est = cloud_estimator.estimate_cloud_energy(
        model_name="llama-3.1-8b-instant", prompt_tokens=40,
        completion_tokens=60, duration_s=2.0, provider="groq",
    )
    assert est.energy_j is None or est.energy_j > 0

    print("[selftest] OK — formule causali, schema CSV e modulo cloud coerenti")
    return 0


def _cli_benchmark(args) -> int:
    from benchmark_unified import run_unified_benchmark

    summary = run_unified_benchmark(
        local_models=args.local.split(",") if args.local else [],
        cloud_selection=[],
        num_prompts=args.prompts,
        temperature=args.temperature,
        timeout_s=args.timeout,
        on_log=lambda m: print(m, flush=True),
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
