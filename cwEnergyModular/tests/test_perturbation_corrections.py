# -*- coding: utf-8 -*-
"""Protocollo di robustezza a perturbazioni (accuratezza/piano.DOCX, Parte 2, §6).

La critica chiede di non misurare soltanto DeltaAccuracy:

- §6.1: ogni trasformazione deve portare con se' il quesito originale, quello
  perturbato, la risposta attesa originale e la verifica che la risposta attesa
  sia ancora valida. Il back-translation non e' una garanzia di preservazione
  semantica: le trasformazioni identity-placeholder lo dichiarano, quelle reali
  restano 'not_verified' finche' un verificatore (umano o automatico) non interviene.
- §6.2: aggiungere DeltaECPC e DeltaLatency, e distinguere i flip per direzione
  (correct->incorrect, incorrect->correct, correct->indeterminate,
  incorrect->indeterminate, indeterminate->correct/incorrect): una perdita di
  accuratezza vera e propria non e' un peggioramento della capacita' di assegnare
  un verdetto.
- §6.3: il 20% e' un pilota, non la numerosita' definitiva; il confronto e'
  appaiato (stessi task baseline/perturbato) e il seed deve essere riproducibile.

Cosa non verificano: la misura fisica dell'energia ne' l'esecuzione reale del
modello (evaluate_fn e' iniettabile, i valori sono sintetici).
"""

import json

import pytest

import perturbation_protocol as pp
from perturbation_protocol import (
    FLIP_CATEGORIES,
    GT_PRESERVATION,
    PerturbationResult,
    _summarize_results,
    apply_syntactic_rephrase,
    export_perturbation_results,
    run_perturbation_protocol,
    verdict_transition,
)


def _res(orig, pert, e_orig, e_pert, lo=None, lp=None, task="T"):
    transition = verdict_transition(orig, pert)
    return PerturbationResult(
        task_id=task, category="c", perturbation_type="syntactic_rephrase",
        original_verdict=orig, perturbed_verdict=pert,
        original_energy_j=e_orig, perturbed_energy_j=e_pert,
        verdict_stable=(orig == pert),
        energy_delta_j=e_pert - e_orig,
        verdict_transition=transition,
        original_latency_s=lo, perturbed_latency_s=lp,
        latency_delta_s=(lp - lo) if (lo is not None and lp is not None) else None,
    )


# --- classificatore di transizione -------------------------------------------


def test_verdict_transition_stabile_e_direzionale():
    """La transizione e' 'stable' se il verdetto non cambia, altrimenti la
    coppia direzionale orig->pert. Il direction matters: correct->incorrect e'
    una perdita di accuratezza, indeterminate->correct e' un recupero di
    capacita' di scoring, e i due non vanno sommati in un unico 'flip'."""
    assert verdict_transition("correct", "correct") == "stable"
    assert verdict_transition("correct", "incorrect") == "correct->incorrect"
    assert verdict_transition("indeterminate", "correct") == "indeterminate->correct"


# --- aggregazione: flip breakdown, DeltaECPC, DeltaLatency -------------------


def test_flip_breakdown_distingue_tutte_le_direzioni():
    """Il breakdown conta separatamente le sei direzioni di flip (piu' stable
    non contato): correct->incorrect e incorrect->correct sono flip di
    accuratezza, correct/incorrect->indeterminate sono degrado dello scoring,
    indeterminate->correct/incorrect sono recuperi. Sommarli in un solo numero
    nasconderebbe la differenza che §6.2 chiede di rendere visibile."""
    results = [
        _res("correct", "incorrect", 1, 1),
        _res("incorrect", "correct", 1, 1),
        _res("correct", "indeterminate", 1, 1),
        _res("incorrect", "indeterminate", 1, 1),
        _res("indeterminate", "correct", 1, 1),
        _res("indeterminate", "incorrect", 1, 1),
        _res("correct", "correct", 1, 1),
    ]
    s = _summarize_results("syntactic_rephrase", "c", results)
    assert s.flip_breakdown == {
        "correct->incorrect": 1, "incorrect->correct": 1,
        "correct->indeterminate": 1, "incorrect->indeterminate": 1,
        "indeterminate->correct": 1, "indeterminate->incorrect": 1,
    }
    # verdict_flips resta la sola accuratezza (correct <-> incorrect)
    assert s.verdict_flips == 2
    assert s.n_tasks == 7
    assert s.stability_rate == pytest.approx(1 / 7)


def test_delta_ecpc_baseline_e_perturbato_sul_campione_appaiato():
    """DeltaECPC = ECPC_perturbed - ECPC_baseline sul campione appaiato, con
    ECPC = somma energia di TUTTE le righe / numero di corrette. Due task:
    baseline (correct 10 J, incorrect 6 J) -> 16/1 = 16 J; perturbato
    (incorrect 12 J, correct 8 J) -> 20/1 = 20 J; delta = +4 J."""
    results = [
        _res("correct", "incorrect", 10.0, 12.0, task="T1"),
        _res("incorrect", "correct", 6.0, 8.0, task="T2"),
    ]
    s = _summarize_results("syntactic_rephrase", "c", results)
    assert s.baseline_ecpc_j == pytest.approx(16.0)
    assert s.perturbed_ecpc_j == pytest.approx(20.0)
    assert s.delta_ecpc_j == pytest.approx(4.0)


def test_delta_ecpc_none_se_denominatore_nullo():
    """Se nella condizione perturbata nessuna risposta e' corretta, l'ECPC
    perturbato non esiste (denominatore nullo) e il delta resta None: non si
    divide per zero ne' si assume un costo infinito o nullo."""
    results = [_res("correct", "incorrect", 10.0, 12.0)]
    s = _summarize_results("syntactic_rephrase", "c", results)
    assert s.baseline_ecpc_j == pytest.approx(10.0)
    assert s.perturbed_ecpc_j is None
    assert s.delta_ecpc_j is None


def test_mean_latency_delta_e_none_senza_latenze():
    """DeltaLatency medio sulle coppie che hanno entrambe le latenze; se nessuna
    coppia le registra, il delta e' None (non zero): l'assenza di una misura non
    e' una variazione nulla."""
    with_lat = [_res("correct", "correct", 1, 1, lo=1.0, lp=1.5),
                _res("correct", "correct", 1, 1, lo=2.0, lp=2.5)]
    s = _summarize_results("syntactic_rephrase", "c", with_lat)
    assert s.mean_latency_delta_s == pytest.approx(0.5)
    no_lat = [_res("correct", "correct", 1, 1)]
    s2 = _summarize_results("syntactic_rephrase", "c", no_lat)
    assert s2.mean_latency_delta_s is None


# --- wiring del protocollo: evaluate_fn, latenza, GT -------------------------


def _one_task(gt="42", prompt="hello world"):
    return [{"task_id": "T1", "category": "c", "prompt": prompt,
             "ground_truth": gt}]


def test_evaluate_fn_a_tre_valori_porta_la_latenza():
    """evaluate_fn puo' ritornare (verdetto, energia, latenza): la latenza
    originale e perturbata viaggiano nel risultato e il loro delta e' calcolato.
    Il confronto e' appaiato sullo stesso task (§6.3)."""
    calls = iter([("correct", 10.0, 1.0), ("incorrect", 12.0, 1.5)])
    summaries = run_perturbation_protocol(
        _one_task(), lambda p: next(calls),
        perturbation_types=["syntactic_rephrase"], sample_fraction=1.0)
    r = summaries[0].by_task[0]
    assert r.original_latency_s == 1.0
    assert r.perturbed_latency_s == 1.5
    assert r.latency_delta_s == pytest.approx(0.5)
    assert r.verdict_transition == "correct->incorrect"
    assert summaries[0].mean_latency_delta_s == pytest.approx(0.5)


def test_evaluate_fn_a_due_valori_latenza_none():
    """La firma storica (verdetto, energia) resta accettata: senza latenza il
    campo e' None, non zero. Retro-compatibilita' del chiamante."""
    calls = iter([("correct", 10.0), ("correct", 11.0)])
    summaries = run_perturbation_protocol(
        _one_task(), lambda p: next(calls),
        perturbation_types=["syntactic_rephrase"], sample_fraction=1.0)
    r = summaries[0].by_task[0]
    assert r.original_latency_s is None
    assert r.latency_delta_s is None
    assert summaries[0].mean_latency_delta_s is None


def test_identity_placeholder_dichiara_gt_preservata():
    """syntactic_rephrase e' un identity-placeholder (non una parafrasi reale):
    il prompt non cambia, quindi la risposta attesa e' banalmente ancora valida,
    ma la verifica e' dichiarata come 'identity_placeholder', non come una
    validazione semantica. La ground truth originale viaggia nel risultato."""
    calls = iter([("correct", 1.0), ("correct", 1.0)])
    summaries = run_perturbation_protocol(
        _one_task(gt="42"), lambda p: next(calls),
        perturbation_types=["syntactic_rephrase"], sample_fraction=1.0)
    r = summaries[0].by_task[0]
    assert r.ground_truth == "42"
    assert r.gt_still_valid is True
    assert r.gt_verification == "identity_placeholder"
    assert r.metadata["original_prompt"] == r.metadata["perturbed_prompt"]


def test_trasformazione_reale_senza_verificatore_non_verifica_gt():
    """instruction_reorder cambia il prompt: senza un verificatore la validita'
    della risposta attesa NON e' dimostrata. gt_still_valid resta None e la
    verifica e' 'not_verified': il back-translation/reorder non e' una garanzia
    di preservazione semantica (§6.1)."""
    calls = iter([("correct", 1.0), ("correct", 1.0)])
    summaries = run_perturbation_protocol(
        _one_task(prompt="One. Two."), lambda p: next(calls),
        perturbation_types=["instruction_reorder"], sample_fraction=1.0)
    r = summaries[0].by_task[0]
    assert r.gt_still_valid is None
    assert r.gt_verification == "not_verified"


def test_verify_gt_fn_fornito_viene_usato():
    """Un verificatore esplicito (umano o automatico) decide la validita' della
    GT sul quesito perturbato: il protocollo ne registra l'esito, invece di
    assumere la preservazione. Qui il verificatore boccia la trasformazione."""
    calls = iter([("correct", 1.0), ("correct", 1.0)])
    summaries = run_perturbation_protocol(
        _one_task(prompt="One. Two."), lambda p: next(calls),
        perturbation_types=["instruction_reorder"], sample_fraction=1.0,
        verify_gt_fn=lambda task, orig, pert: False)
    r = summaries[0].by_task[0]
    assert r.gt_still_valid is False
    assert r.gt_verification == "provided_fn"


# --- dichiarazioni: placeholder, pilota, funzione morta rimossa --------------


def test_identity_placeholder_e_dichiarato_nella_tassonomia():
    """La parafrasi sintattica restituisce il testo invariato (placeholder) e la
    tassonomia GT_PRESERVATION lo dichiara: nessun claim di parafrasi reale finche'
    il modello di traduzione non e' implementato."""
    assert apply_syntactic_rephrase("testo di prova") == "testo di prova"
    assert GT_PRESERVATION["syntactic_rephrase"] == "identity_placeholder"
    assert GT_PRESERVATION["instruction_reorder"] == "requires_verification"


def test_funzione_morta_perturbation_results_from_summary_rimossa():
    """Il placeholder che ritornava [] senza costruire task e' rimosso: una
    funzione che non fa nulla e' un'implementazione a meta', non un'integrazione.
    I task reali li passa il chiamante a run_perturbation_protocol."""
    assert not hasattr(pp, "perturbation_results_from_summary")


def test_export_dichiara_pilota_metriche_e_confronto_appaiato(tmp_path):
    """L'export dichiara che il campione e' un pilota (numerosita' definitiva da
    decidere sulla precisione di DeltaAccuracy), che il confronto e' appaiato, e
    porta flip_breakdown, DeltaECPC e DeltaLatency per ogni riepilogo."""
    calls = iter([("correct", 10.0, 1.0), ("incorrect", 12.0, 1.5)])
    summaries = run_perturbation_protocol(
        _one_task(), lambda p: next(calls),
        perturbation_types=["syntactic_rephrase"], sample_fraction=1.0)
    out = tmp_path / "pert.json"
    export_perturbation_results(summaries, out)
    data = json.loads(out.read_text(encoding="utf-8"))
    notes = data["notes"].lower()
    assert "pilot" in notes
    assert "paired" in notes
    s0 = data["summaries"][0]
    assert "flip_breakdown" in s0
    assert "delta_ecpc_j" in s0
    assert "mean_latency_delta_s" in s0