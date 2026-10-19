# -*- coding: utf-8 -*-
"""
test_validazione_valutazione.py — I TRE CASI OBBLIGATORI di validazione
della valutazione semantica ground-truth (proposta approvata).

Casi richiesti:
  A) parafrasi corretta      -> attesa: semantic_similarity >= soglia, is_correct=True
  B) risposta errata         -> attesa: semantic_similarity < soglia,  is_correct=False
  C) risposta quasi identica -> attesa: semantic_similarity >= 0.90,   is_correct=True
Requisito extra: differenza A-B >= 0.20.

Esegui con la GUI spenta:  py test_validazione_valutazione.py
Uscita: 0 = tutti i criteri soddisfatti; 1 = criteri non soddisfatti;
        2 = backend embeddings non disponibile (fallback lessicale dichiarato).
"""
from __future__ import annotations

import sys

import evaluator
import semantic_evaluator as sem


def _fmt(v):
    return "N/A" if v is None else f"{v:.6f}" if isinstance(v, float) else str(v)


def main() -> int:
    thr = evaluator.SEMANTIC_THRESHOLD
    print("=== VALIDAZIONE VALUTAZIONE SEMANTICA (3 casi obbligatori) ===")
    print(f"Soglia CW_SEMANTIC_THRESHOLD = {thr}")
    print(f"Modello approvato            = {sem.EMBED_MODEL_NAME}")

    available = sem.embedding_available()
    if not available:
        print(f"[WARN] Backend embeddings NON disponibile: {sem.init_error()}")
        print("[WARN] L'evaluator userà il fallback trasparente "
              "'lexical_only(fallback)' — la valutazione semantica non è "
              "validabile in questo ambiente.")
        print("[HINT] pip install sentence-transformers  (poi ritentare)")

    GT = ("La capitale d'Italia è Roma. Roma si trova nel Lazio, lungo il "
          "fiume Tevere, ed è il centro politico e amministrativo del Paese.")

    cases = [
        # (etichetta, risposta, esito atteso)
        ("A) parafrasi corretta",
         "Roma, situata nel Lazio sulle rive del Tevere, è la città capoluogo "
         "e sede del governo italiano.",
         "correct"),
        ("B) risposta errata",
         "La capitale d'Italia è Firenze, famosa per il Duomo e il Ponte Vecchio.",
         "wrong"),
        ("C) risposta quasi identica",
         "La capitale d'Italia è Roma. Roma si trova nel Lazio, lungo il fiume "
         "Tevere, ed è il centro politico e amministrativo del Paese.",
         "correct"),
    ]

    results = []
    for label, answer, expect in cases:
        res = evaluator.evaluate_response(answer, ground_truth=GT, mode="auto")
        ok_sem = res.semantic_similarity
        ok_lex = res.lexical_similarity
        verdict = "PASS"
        reasons = []
        if available and ok_sem is not None:
            if expect == "correct":
                if label.startswith("C"):
                    if not (ok_sem >= 0.90 and res.is_correct):
                        verdict, _ = "FAIL", None
                        reasons.append("atteso sim>=0.90 e is_correct=True")
                else:
                    if not (ok_sem >= thr and res.is_correct):
                        verdict = "FAIL"
                        reasons.append(f"atteso sim>={thr} e is_correct=True")
            else:  # wrong
                if not (ok_sem < thr and res.is_correct == 0):
                    verdict = "FAIL"
                    reasons.append(f"atteso sim<{thr} e is_correct=False")
        elif not available:
            verdict = "SKIP(no-embeddings)"
        results.append((label, res, verdict, reasons))

        print(f"\n--- {label} ---")
        print(f"Risposta           : {answer[:70]}…")
        print(f"semantic_similarity: {_fmt(ok_sem)}")
        print(f"lexical_similarity : {_fmt(ok_lex)}")
        print(f"is_correct         : {res.is_correct}")
        print(f"eval_mode          : {res.eval_mode}")
        print(f"eval_method        : {res.eval_method}")
        print(f"acc_comp           : {_fmt(res.acc_comp)}")
        print(f"esito caso         : {verdict}"
              + ((" — " + "; ".join(reasons)) if reasons else ""))

    # criterio trasversale: separazione A/B >= 0.20
    if available:
        sa = results[0][1].semantic_similarity
        sb = results[1][1].semantic_similarity
        if sa is not None and sb is not None:
            diff = sa - sb
            print(f"\nSeparazione semantica A-B = {diff:.4f} "
                  f"(richiesto >= 0.20)")
            if diff < 0.20:
                print("[FAIL] La similarità semantica non distingue "
                      "parafrasi-corretta da risposta_errata a sufficienza.")
                return 1

    # coerenze dichiarate nella proposta
    gt_res = results[2][1]  # caso C, sempre regime GT
    assert gt_res.eval_mode == "ground_truth", "eval_mode deve essere ground_truth"
    if available and gt_res.semantic_similarity is not None:
        assert gt_res.eval_method == sem.method_label(), \
            "eval_method deve dichiarare il modello embedding"
        assert gt_res.acc_comp == gt_res.semantic_similarity, \
            "in regime GT acc_comp deve essere la semantic_similarity"

    kw = evaluator.evaluate_response(
        "The cause produced an effect on the system", mode="causal")
    assert kw.eval_mode == "heuristic_keyword_fallback", \
        "il fallback keyword deve etichettarsi heuristic_keyword_fallback"
    expected_acc_comp = round(
        0.6 * kw.acc_links + 0.3 * (kw.judge_score / 5.0) + 0.1 * kw.cosine_sim, 6)
    assert abs(kw.acc_comp - expected_acc_comp) < 1e-9, \
        "acc_comp causale deve usare la formula 0.6/0.3/0.1"
    print("\n[OK] eval_mode regime GT = 'ground_truth'")
    print(f"[OK] eval_method regime GT = '{gt_res.eval_method}'")
    print("[OK] regime keyword etichettato 'heuristic_keyword_fallback'")
    print(f"[OK] acc_comp causale = 0.6*acc_links+0.3*(judge/5)+0.1*cosine "
          f"-> {kw.acc_comp}")

    if not available:
        print("\n[RESULT] Fallback lessicale attivo e dichiarato; i valori "
              "semantici non sono validabili qui. Su Windows con "
              "sentence-transformers installato rilanciare lo script.")
        return 2

    fails = [r for r in results if r[2] == "FAIL"]
    if fails:
        print("\n[RESULT] FALLITI:", [f[0] for f in fails])
        return 1
    print("\n[RESULT] TUTTI E TRE I CASI SUPERATI")
    return 0


if __name__ == "__main__":
    sys.exit(main())
