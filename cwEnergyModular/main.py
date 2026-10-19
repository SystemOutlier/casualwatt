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

    # euristica keyword cause/effect (NON ground-truth accuracy):
    # eval_mode rinominato esplicitamente in "heuristic_keyword_fallback"
    r = evaluator.evaluate_response("The cause of X has an effect on Y", is_tool=False, mode="causal")
    assert r.eval_mode == "heuristic_keyword_fallback"
    assert r.acc_links == 1.0 and r.judge_score == 4.0 and r.cosine_sim == 0.75
    # formula approvata: acc_comp = 0.6*acc_links + 0.3*(judge/5) + 0.1*cosine
    assert abs(r.acc_comp - (0.6 * 1.0 + 0.3 * (4.0 / 5.0) + 0.1 * 0.75)) < 1e-9
    r2 = evaluator.evaluate_response("only a cause here", is_tool=True, mode="causal")
    assert r2.acc_links == 0.5 and r2.judge_score == 3.0 and r2.cosine_sim == 0.88
    r3 = evaluator.evaluate_response("nothing relevant", is_tool=True, mode="causal")
    assert r3.acc_links == 0.0 and r3.judge_score == 1.5
    r4 = evaluator.evaluate_response("cause + effect", is_tool=True, mode="causal")
    assert r4.judge_score == 4.5

    # valutazione UNIVERSALE regime GT: answer_type "short_text" -> matching
    # esatto/contenimento; is_correct e' l'accuracy binaria primaria (1/0)
    # calcolata PRIMA di acc_comp.
    gt = evaluator.evaluate_response("Paris", ground_truth="Paris")
    assert gt.eval_mode == "ground_truth" and gt.is_correct == 1
    assert gt.answer_type == "short_text" and gt.acc_comp == 1.0
    gt_bad = evaluator.evaluate_response("London", ground_truth="Paris")
    assert gt_bad.is_correct == 0 and gt_bad.acc_comp == 0.0
    # via "free_text" (embedding semantico): solo se gli embeddings sono
    # disponibili offline; altrimenti il campo resta N/A e il check e' saltato.
    gt_free = evaluator.evaluate_response(
        "Rain falls, so the ground becomes wet and the soil moisture rises.",
        ground_truth="Because rain falls the ground gets wet and soil moisture "
                     "increases over time.",
    )
    assert gt_free.answer_type == "free_text" and gt_free.is_correct in (0, 1, None)
    if gt_free.semantic_similarity is not None:
        thr = gt_free.semantic_threshold
        assert gt_free.is_correct == (1 if gt_free.semantic_similarity >= thr else 0)

    # senza ground truth -> regime B (causal_agent_eval): NESSUN errore, campi
    # accuratezza N/A perche' il giudice e' dichiarato assente. Judge iniettato
    # offline: il selftest non deve mai toccare la rete.
    sk = evaluator.evaluate_response(
        "una risposta qualunque", ground_truth=None,
        judge_fn=lambda q, a, m: (None, {"reason": "selftest offline", "ok": False}),
    )
    assert sk.eval_mode == "causal_agent_eval"
    assert sk.causal_accuracy is None and sk.is_correct is None

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
    # nuove colonne valutazione semantica (proposta approvata)
    assert {"eval_method", "semantic_similarity", "lexical_similarity",
            "semantic_threshold"} <= set(CSV_COLUMNS), "colonne semantiche mancanti!"
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
