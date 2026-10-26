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

La seconda sezione del file (dopo `main()`) non e' eseguita dallo script: sono
test pytest che congelano l'alfabeto del campo `is_correct`. Vedi la loro
intestazione.
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
        res = evaluator.evaluate_response(answer, ground_truth=GT, mode="auto", use_semantic=True)
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


# ===========================================================================
# GARANZIA FORMALE SULL'ALFABETO DI `is_correct` (26-10-2026)
# ===========================================================================
# Perche' questi test esistono, separati dai tre casi obbligatori di main().
#
# `is_correct` e' l'accuratezza binaria PRIMARIA della riga: 1 = risposta
# corretta, 0 = errata, None = "N/A" perche' non esiste una ground truth
# confrontabile (`evaluator.py:192-194`). Un quarto stato non esiste, e lo
# stato conta a valle: `benchmark_unified.py:564-566` calcola
# `energy_per_correct_answer_j` usando la richiesta solo se `is_correct` e'
# vero. Uno `0` che scivola su `None` toglie dal denominatore una risposta
# realmente sbagliata; un `bool`, un `2` o una stringa al posto di `None`
# rendono la colonna non interpretabile da chi apre il CSV.
#
# L'`or 0.0` che cancellava i `None` in campo energetico -- e che oggi
# `tests/test_cloud_energy_none_preservato.py` impedisce -- e' lo stesso errore
# di tipo in un campo diverso. Qui la forma pericolosa e' `if not v` (vero per
# `0`, per `0.0` e per `""`), che confunderebbe "risposta errata" con "non
# misurabile". `_na_or` (`benchmark_unified.py:362-364`) confronta con
# `is None`: i test sotto congelano quel confronto.
#
# `evaluator.py` NON viene modificato: la standardizzazione richiesta era gia'
# nel codice. Questi test servono a rendere la proprieta' verificabile,
# percorrendo tutti i siti che assegnano il campo (`:368`, `:474`, `:482`,
# `:501`, `:545`, `:554`, `:562`, `:629`), i due percorsi che non lo assegnano
# e lo lasciano a `NA` (`mode="skip"` in `:432-435`, `evaluate_skipped` in
# `:663-669`) e il default della dataclass (`:194`).
#
# Esecuzione:  python -m pytest test_validazione_valutazione.py -v
# Offline: nessun caricamento di embedding e nessuna chiamata a Ollama -- il
# giudice e' iniettato (`judge_fn`), il modulo semantico e' sostituito.
import ast
import csv
from pathlib import Path
from types import SimpleNamespace

import pytest

IS_CORRECT_ALPHABET = (1, 0, None)


def _in_alfabeto(value, dove):
    """Assegna il vincolo formale: `is_correct` e' 1, 0 o None e nient'altro.

    `bool` e' escluso perche' in Python e' un sottotipo di `int`: `True == 1`
    passerebbe un controllo ingenuo `in (0, 1)`, ma il CSV scriverebbe "True".
    Il controllo di tipo esplicito chiude quella porta.
    """
    ok = value is None or (
        isinstance(value, int) and not isinstance(value, bool) and value in (0, 1)
    )
    assert ok, (f"{where}: is_correct={value!r} "
                f"({type(value).__name__}) fuori dall'alfabeto {IS_CORRECT_ALPHABET}")


class _SemStub:
    """Doppio di `semantic_evaluator`: fissa il coseno senza caricare modelli."""

    def __init__(self, value, label="embedding:stub-di-test", error=""):
        self._value = value
        self._label = label
        self._error = error

    def semantic_similarity(self, text_a, text_b):
        return self._value

    def method_label(self):
        return self._label

    def init_error(self):
        return self._error

    def embedding_available(self):
        return self._value is not None


def _judge(score):
    """Doppio del LLM Judge con la firma usata da `_run_judge` (`evaluator.py:646`)."""
    def fn(question, answer, model=None):
        info = {"ok": score is not None, "judge_model": "stub-di-test",
                "reason": "" if score is not None else "giudice disabilitato dal test"}
        return score, info
    return fn


GT_LONGA = ("La capitale d'Italia e' Roma. Roma si trova nel Lazio, lungo il "
            "fiume Tevere, ed e' il centro politico e amministrativo del Paese.")
RISPOSTA_DIVERSA = "Il quadrato ha lato 7, quindi il perimetro e' 28 centimetri."

# (etichetta, argomenti per evaluate_response, esito atteso su is_correct).
# `sem_value` prepara il doppio degli embedding, `judge_score` il doppio del
# giudice: non sono argomenti di `evaluate_response` e vengono estratti.
RAMI_IS_CORRECT = [
    # answer_type=number: confronto numerico riuscito ed errato (`:474`)
    ("number_corretto",
     dict(text="La risposta e' 42.", ground_truth="42", mode="auto",
          answer_type="number"), 1),
    ("number_errato",
     dict(text="La risposta e' 41.", ground_truth="42", mode="auto",
          answer_type="number"), 0),
    # number: nessun numero estraibile -> 0, NON "N/A" (`:482`)
    ("number_senza_numero_estraibile",
     dict(text="non so rispondere", ground_truth="42", mode="auto",
          answer_type="number"), 0),
    # answer_type=short_text: contenimento con alternative (`:501`)
    ("short_text_contenuto",
     dict(text="La capitale e' Roma, citta' eterna.",
          ground_truth="Roma | Roma Capitale", mode="auto",
          answer_type="short_text"), 1),
    ("short_text_non_contenuto",
     dict(text="La capitale e' Firenze.", ground_truth="Roma | Roma Capitale",
          mode="auto", answer_type="short_text"), 0),
    # regime B (senza GT): giudice sopra e sotto la soglia 4.0 (`:629`)
    ("regime_B_giudice_4.5",
     dict(text="Perche' il contatore e' cumulativo e non differenziale.",
          ground_truth=None, mode="auto", judge_score=4.5), 1),
    ("regime_B_giudice_2.0",
     dict(text="Perche' il contatore e' cumulativo e non differenziale.",
          ground_truth=None, mode="auto", judge_score=2.0), 0),
    # regime B: giudice assente -> None, non 0 (`:629`, ramo `else NA`)
    ("regime_B_giudice_non_disponibile",
     dict(text="Perche' il contatore e' cumulativo e non differenziale.",
          ground_truth=None, mode="auto", judge_score=None), None),
    # free_text con embedding richiesto: soglia semantica (`:562`)
    ("free_text_semantica_sopra_soglia",
     dict(text=RISPOSTA_DIVERSA, ground_truth=GT_LONGA, mode="auto",
          answer_type="free_text", use_semantic=True, sem_value=0.99,
          judge_score=4.5), 1),
    ("free_text_semantica_sotto_soglia",
     dict(text=RISPOSTA_DIVERSA, ground_truth=GT_LONGA, mode="auto",
          answer_type="free_text", use_semantic=True, sem_value=0.01,
          judge_score=4.5), 0),
    # free_text: embedding chiesti ma indisponibili -> None (`:545`)
    ("free_text_embeddings_non_disponibili",
     dict(text=RISPOSTA_DIVERSA, ground_truth=GT_LONGA, mode="auto",
          answer_type="free_text", use_semantic=True, sem_value=None,
          judge_score=4.5), None),
    # free_text senza embedding: fallback lessicale dichiarato (`:554`)
    ("free_text_fallback_lessicale_sopra_0.85",
     dict(text=GT_LONGA, ground_truth=GT_LONGA, mode="auto",
          answer_type="free_text", use_semantic=False, judge_score=4.5), 1),
    ("free_text_fallback_lessicale_sotto_0.85",
     dict(text=RISPOSTA_DIVERSA, ground_truth=GT_LONGA, mode="auto",
          answer_type="free_text", use_semantic=False, judge_score=4.5), 0),
    # regime legacy keyword (`:368`)
    ("keyword_cause+effect",
     dict(text="The cause produced an effect on the system",
          ground_truth=None, mode="causal"), 1),
    ("keyword_assente",
     dict(text="Nessun termine causale dentro questa frase", ground_truth=None,
          mode="causal"), 0),
    # nessun ramo assegna: il campo resta il default `NA` (`:432-435`)
    ("mode_skip",
     dict(text="una risposta qualsiasi", ground_truth=GT_LONGA, mode="skip"),
     None),
]


@pytest.mark.parametrize("etichetta,kwargs,atteso", RAMI_IS_CORRECT)
def test_is_correct_appartiene_all_alfabeto_binario(monkeypatch, etichetta,
                                                    kwargs, atteso):
    """Ogni ramo di `evaluate_response` produce 1, 0 o None: nessun altro stato.

    Verifica due relazioni per ogni riga della tabella: `valore ∈ {1, 0, None}`
    (alfabeto) e `valore == atteso` (semantica del ramo). Un ramo che producesse
    `True`, `2`, `0.0` o la stringa "N/A" fallisce qui, non a valle nel CSV.
    """
    kw = dict(kwargs)
    sem_value = kw.pop("sem_value", ...)
    judge_score = kw.pop("judge_score", "non specificato")
    if sem_value is not ...:
        monkeypatch.setattr(evaluator, "_sem", _SemStub(
            sem_value, error="" if sem_value is not None else "stub"))
    if judge_score != "non specificato":
        kw["judge_fn"] = _judge(judge_score)
    res = evaluator.evaluate_response(**kw)
    _in_alfabeto(res.is_correct, etichetta)
    assert res.is_correct == atteso, (
        f"{etichetta}: atteso is_correct={atteso!r}, ottenuto "
        f"{res.is_correct!r} (eval_mode={res.eval_mode!r}, "
        f"eval_method={res.eval_method!r})")


def test_default_dataclass_e_evaluate_skipped_restano_na():
    """Il default della dataclass e `evaluate_skipped()` sono None, non 0.

    `evaluate_skipped` costruisce il risultato dei percorsi d'errore del runner
    (`evaluator.py:663-669`) senza attraversare `evaluate_response`: se il
    default fosse `0`, una richiesta fallita risulterebbe "risposta errata" e
    la sua energia entrerebbe nelle medie con il segno opposto.
    """
    _in_alfabeto(evaluator.EvaluationResult().is_correct, "default dataclass :194")
    _in_alfabeto(evaluator.evaluate_skipped("errore di rete").is_correct,
                 "evaluate_skipped :663")
    assert evaluator.EvaluationResult().is_correct is None
    assert evaluator.evaluate_skipped("errore di rete").is_correct is None


def test_NA_e_il_riferimento_none_non_cambiano():
    """`NA` e' `None` (`evaluator.py:53`): se diventasse "" o "N/A" la riga mentirebbe.

    Tutta la rappresentazione dell'assenza poggia su un solo riferimento; la
    casa lo rende "" nel CSV e "N/A" nei campi testuali, mai un valore numerico.
    """
    assert evaluator.NA is None


# --------------------------------------------------- guardia strutturale
def _espressione_solo_0_1_o_na(node):
    """Vero se il nodo AST puo' valutare SOLO a 1, 0 o NA, per forma sintattica."""
    if isinstance(node, ast.Constant):
        return node.value in (0, 1, None)
    if isinstance(node, ast.Name):
        return node.id in ("NA", "None")
    if isinstance(node, ast.IfExp):
        return (_espressione_solo_0_1_o_na(node.body)
                and _espressione_solo_0_1_o_na(node.orelse))
    return False


def test_alfabeto_di_is_correct_chiuso_sulla_struttura_di_evaluator():
    """Ogni assegnazione di `is_correct` in `evaluator.py` e' binaria per forma.

    E' il complemento statico del test parametrizzato: la tabella sopra
    percorre i rami conosciuti, questo impedisce che un ramo nuovo -- o la
    riscrittura di uno esistente -- introduca un valore fuori dall'alfabeto
    senza che nessuno aggiunga un caso. Sono ammesse solo costanti 1/0/None,
    il nome `NA` e i `IfExp` annidati di queste: niente `bool(...)`, niente
    `int(...)`, niente `or` di default.

    Allarga la scansione anche all'annotazione della dataclass (`:194`,
    `is_correct: Optional[int] = NA`: bersaglio `Name`, non `Attribute`), perche'
    il default e' il nono stato possibile della colonna ed e' quello usato dai
    percorsi che non assegnano.
    """
    src = Path(evaluator.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    siti = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                nome = (tgt.attr if isinstance(tgt, ast.Attribute) else
                        tgt.id if isinstance(tgt, ast.Name) else "")
                if nome == "is_correct":
                    siti.append((node.lineno, node.value))
    assert siti, "nessuna assegnazione di is_correct trovata: il test e' stale"
    fuori = [ln for ln, v in siti if not _espressione_solo_0_1_o_na(v)]
    assert not fuori, (
        "assegnazioni di is_correct non riconducibili a 1/0/None in "
        + ", ".join(f"evaluator.py:{ln}" for ln in fuori))
    # i nove siti noti: default :194 e le assegnazioni :368 :474 :482 :501
    # :545 :554 :562 :629
    assert len(siti) >= 9, (
        f"attesi almeno i 9 siti noti, trovati {len(siti)}: "
        "riesaminare la tabella RAMI_IS_CORRECT")


# ------------------------------------------------------- percorso di export
def test_na_or_non_tratta_lo_zero_come_assenza():
    """`_na_or` confronta `is None`: `0` resta `0`, solo `None` diventa "N/A".

    E' la regressione che l'utente chiede di impedire: un futuro
    `return v or "N/A"` o `if not v:` riscriverebbe la risposta sbagliata (0)
    come risposta non misurabile ("N/A"), e le due cose hanno segno opposto
    nelle statistiche di efficienza.
    """
    import benchmark_unified as bu

    assert bu._na_or(0) == 0 and not isinstance(bu._na_or(0), str)
    assert bu._na_or(1) == 1
    assert bu._na_or(None) == "N/A"
    assert str(bu._na_or(0)) == "0"
    assert bu._na_or(0.0) == 0.0          # anche lo zero di confine 12.1
    assert bu._na_or(0.75) == 0.75


def test_basic_record_preserva_il_zero_di_is_correct():
    """La riga costruita da `_basic_record` porta `is_correct=0`, non "N/A".

    Copre il punto d'uso `benchmark_unified.py:445`. Il fornitore di intensita'
    di carbonio e' sostituito per non dipendere da rete o cache: cio' che si
    test qui e' la rappresentazione del campo, non il fattore di rete elettrica.
    """
    import benchmark_unified as bu

    ci_finto = SimpleNamespace(gco2eq_per_kwh=245.7, zone="IT",
                               source="stub-di-test", timestamp=0.0)
    monkeypatch = bu.get_carbon_intensity
    bu.get_carbon_intensity = lambda *a, **k: ci_finto
    prompt = {"id": "p1", "text": "quanto fa 6 per 7?"}
    try:
        ev_errata = evaluator.evaluate_response("La risposta e' 41.",
                                                ground_truth="42", mode="auto",
                                                answer_type="number")
        assert ev_errata.is_correct == 0
        rec = bu._basic_record("r1", "s1", "m", "M", "local", "local", None,
                               prompt, ev_errata)
        rec_na = bu._basic_record("r1", "s1", "m", "M", "local", "local", None,
                                 prompt, evaluator.evaluate_skipped("x"))
    finally:
        bu.get_carbon_intensity = monkeypatch
    _in_alfabeto(rec["is_correct"], "_basic_record :445 (risposta errata)")
    assert rec["is_correct"] == 0, (
        f'lo zero e\' diventato {rec["is_correct"]!r}: una risposta errata non '
        'e\' "N/A"')
    assert rec_na["is_correct"] == "N/A"


def test_csv_round_trip_la_colonna_is_correct_non_e_ambigua(tmp_path):
    """Scritto e riletto il CSV, la cella legge "0" per l'errata e "N/A" per l'assente.

    Verifica la colonna fino in fondo: `CSV_COLUMNS` la espone
    (`casualwatt_csv_export.py:49`) e `export_results_csv` usa un `DictWriter`,
    che renderizzerebbe `None` come stringa vuota. Per questo l'export passa da
    `_na_or`: la cella deve leggere esattamente "N/A", non "".
    """
    import benchmark_unified as bu
    import casualwatt_csv_export as cxexport

    ci_finto = SimpleNamespace(gco2eq_per_kwh=245.7, zone="IT",
                               source="stub-di-test", timestamp=0.0)
    monkeypatch = bu.get_carbon_intensity
    bu.get_carbon_intensity = lambda *a, **k: ci_finto
    prompt = {"id": "p1", "text": "quanto fa 6 per 7?"}
    try:
        rec_errata = bu._basic_record(
            "r1", "s1", "m", "M", "local", "local", None, prompt,
            evaluator.evaluate_response("La risposta e' 41.", ground_truth="42",
                                        mode="auto", answer_type="number"))
        rec_na = bu._basic_record(
            "r1", "s1", "m", "M", "local", "local", None, prompt,
            evaluator.evaluate_skipped("x"))
    finally:
        bu.get_carbon_intensity = monkeypatch

    path = tmp_path / "risultati.csv"
    cxexport.export_results_csv([rec_errata, rec_na], path, mode="w")
    with open(path, newline="", encoding="utf-8") as fh:
        righe = list(csv.DictReader(fh))
    assert len(righe) == 2
    assert righe[0]["is_correct"] == "0", (
        f'cella letta come {righe[0]["is_correct"]!r}: una risposta errata non '
        'deve essere indistinguibile da una non valutata')
    assert righe[1]["is_correct"] == "N/A"


if __name__ == "__main__":
    sys.exit(main())
