# -*- coding: utf-8 -*-
"""Gate del giudice nel valutatore (accuratezza/piano.DOCX, Parte 2, §6-§7).

§6: "Se alpha < 0.8 su ramo: imposta flag judge_gated_{ramo}=true;
evaluator.py forza is_correct=None per quel ramo con motivo judge_uncalibrated".
§7 ancora il punto a evaluator.py:676, il ramo senza ground truth (REGIME B)
dove is_correct e' derivato dal punteggio del giudice.

Questi test fissano tre fatti:

- un ramo REGIME B gated NON chiama il giudice e resta non valutato
  (is_correct=None, none_reason="judge_uncalibrated", eval_method="judge_gated"):
  il gate di calibrazione umana blocca lo scoring, non produce un verdetto;
- un ramo REGIME B non gated continua a comportarsi come prima (il giudice e'
  chiamato, is_correct deriva dal punteggio): il gate non cambia il percorso
  validato;
- il gate NON tocca i rami deterministici del REGIME A (number/short_text):
  la loro is_correct viene dalla ground truth, non dal giudice, quindi un
  giudice non calibrato non puo' annullare un verdetto deterministico.

Cosa non verificano: la misura fisica dell'energia ne' l'esecuzione reale del
giudice (judge_fn e' una spia iniettabile).
"""

from evaluator import EvaluationResult, evaluate_response
from evaluation_runner import final_verdict
from benchmark_unified import _basic_record


def _spy_judge(calls):
    """Giudice finto che registra le chiamate: (score, info) con score=5."""
    def judge(question, answer, model=None):
        calls.append((question, answer))
        return 5, {"ok": True, "judge_model": "spy-judge"}
    return judge


def test_regime_b_gated_non_chiama_il_giudice_e_resta_non_valutato():
    """§6: con judge_gated=True il ramo senza GT forza is_correct=None e motivo
    judge_uncalibrated, e NON chiama il giudice. Un ramo bloccato dal gate di
    calibrazione non e' 'indeterminato per fallimento': non e' stato valutato
    affatto, perche' il giudice non e' validato su quel ramo."""
    calls = []
    res = evaluate_response("una risposta causale qualsiasi",
                            ground_truth=None,
                            judge_fn=_spy_judge(calls),
                            judge_gated=True)
    assert res.is_correct is None
    assert res.none_reason == "judge_uncalibrated"
    assert res.eval_method == "judge_gated"
    assert res.eval_mode == "causal_agent_eval"
    assert res.judge_score is None
    assert res.acc_comp is None
    assert calls == []  # il giudice non deve essere invocato


def test_regime_b_non_gated_chiama_il_giudice_come_prima():
    """Il gate non cambia il percorso validato: senza judge_gated il giudice e'
    chiamato e is_correct deriva dal punteggio (5 >= 4 -> 1). none_reason resta
    vuoto: nessun blocco di calibrazione su questo ramo."""
    calls = []
    res = evaluate_response("una risposta causale qualsiasi",
                            ground_truth=None,
                            judge_fn=_spy_judge(calls),
                            judge_gated=False)
    assert len(calls) == 1
    assert res.is_correct == 1
    assert res.none_reason == ""
    assert res.judge_score == 5


def test_gate_non_tocca_il_rammo_deterministico_number():
    """number e' deterministico: is_correct viene dal confronto con la GT, non
    dal giudice. Anche con judge_gated=True un numero corretto resta corretto
    (is_correct=1) e none_reason vuoto: il gate del giudice non puo' annullare
    un verdetto che non dipende dal giudice."""
    calls = []
    res = evaluate_response("la risposta e' 2",
                            ground_truth="2",
                            answer_type="number",
                            judge_fn=_spy_judge(calls),
                            judge_gated=True)
    assert res.is_correct == 1
    assert res.none_reason == ""
    assert res.eval_mode == "ground_truth"


def test_ramo_gated_produce_final_verdict_unscored():
    """Il motivo judge_uncalibrated scritto dal gate, riportato nella riga come
    verdict_none_reason, e' letto da final_verdict come 'unscored' (non
    'indeterminate'): il blocco di calibrazione e' uno stato distinto dal
    fallimento dello scoring (§2.1/§7.1). I due moduli devono agree sul
    vocabolario, altrimenti il riepilogo conta il ramo gated come un errore."""
    res = evaluate_response("risposta", ground_truth=None,
                            judge_fn=_spy_judge([]), judge_gated=True)
    record = {"end_to_end": "indeterminate",
              "verdict_none_reason": res.none_reason}
    assert final_verdict(record) == "unscored"


def test_none_reason_e_un_campo_del_risultato_con_default_vuoto():
    """none_reason e' un campo dichiarato di EvaluationResult, vuoto di default:
    una riga valutata normalmente non porta un motivo di N/A. Il campo esiste
    perche' il motivo del blocco deve viaggiare con il risultato, non essere
    ricostruito a posteriori dal testo delle note."""
    res = EvaluationResult()
    assert res.none_reason == ""


def _record(evalres):
    prompt = {"id": "p1", "text": "q", "ground_truth": None}
    return _basic_record("r", "s", "m", "m", "local", "local",
                         None, prompt, evalres)


def test_record_builder_propaga_il_motivo_del_gate():
    """Il motivo scritto dal gate deve viaggiare nella riga come
    verdict_none_reason, altrimenti il riepilogo non puo' distinguere un ramo
    gated da un fallimento dello scoring: final_verdict leggerebbe
    'indeterminate' invece di 'unscored'. Il campo non e' una colonna CSV (lo
    schema P5 e' congelato): vive nel record e nel blocco CW_SCORING_V1."""
    res = evaluate_response("risposta", ground_truth=None,
                            judge_fn=_spy_judge([]), judge_gated=True)
    rec = _record(res)
    assert rec["verdict_none_reason"] == "judge_uncalibrated"
    assert final_verdict(rec) == "unscored"


def test_record_builder_motivo_vuoto_per_riga_valutata():
    """Una riga valutata normalmente non porta un motivo di N/A: il campo e'
    vuoto, non 'unknown' ne' un token inventato. La differenza fra 'non
    registrato' e 'fallito' deve sopravvivere fino al record."""
    res = evaluate_response("la risposta e' 2", ground_truth="2",
                            answer_type="number")
    rec = _record(res)
    assert rec["verdict_none_reason"] == ""
    assert final_verdict(rec) == "correct"