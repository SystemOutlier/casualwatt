# -*- coding: utf-8 -*-
"""Frontiera di Pareto a tre dimensioni (accuratezza/piano.DOCX, Parte 2, §4).

La critica (§4, "il problema e' l'uso esclusivo di accuracy_covered"): un
modello che si astiene su molti quesiti difficili puo' avere un'accuracy
condizionata alta e un ECPC basso, ma una coverage bassa. Confrontare solo
(ECPC, accuracy_covered) lo premia ingiustamente. La soluzione raccomandata:

- tre dimensioni: minimizzare ECPC, massimizzare accuracy_covered, massimizzare
  coverage (§9: "Inserire coverage come terza dimensione della Pareto frontier
  o come vincolo minimo");
- in alternativa un grafico 2D leggibile con la coverage come dimensione del
  punto, piu' una soglia minima di coverage PREREGISTRATA per includere una
  configurazione nella frontiera principale (la soglia si fissa prima dei dati);
- l'analisi resta descrittiva: nessun punto e' promosso a 'validated'.

L'esempio numerico e' quello del piano: A (95%, 40%, 2 J), B (90%, 95%, 3 J),
C (85%, 100%, 3,5 J). In 2D A domina B e C; in 3D nessuno domina nessuno,
perche' A ha risposto solo al 40% dei quesiti.

Cosa non verificano: la misura fisica dell'energia (i valori sono sintetici).
"""

import pytest

from pareto_frontier import (
    ConfigPoint,
    dominates,
    dominates_2d,
    filter_min_coverage,
    knee_detection,
    pareto_frontier,
    pareto_frontier_2d,
    points_from_evaluation_summary,
    points_from_taxonomy_result,
)


def _pt(name, energy, acc, coverage=None):
    return ConfigPoint(model_name=name, category="c", energy_j=energy,
                       accuracy_covered=acc, coverage=coverage)


# --- il campo coverage -------------------------------------------------------


def test_configpoint_ha_coverage_con_default_none():
    """coverage e' un campo dichiarato, None di default: i punti legacy senza
    coverage restano costruibili e la frontiera 2D continua a funzionare. Il
    campo esiste perche' la terza dimensione deve viaggiare con il punto, non
    essere ricostruita a posteriori."""
    p = ConfigPoint(model_name="m", category="c", energy_j=2.0,
                    accuracy_covered=0.9)
    assert p.coverage is None


# --- dominanza 2D vs 3D ------------------------------------------------------


def test_dominates_2d_ignora_la_coverage():
    """La dominanza 2D confronta solo (ECPC, accuracy_covered): A (2 J, 0.95)
    domina B (3 J, 0.90) anche se A ha coverage bassa. E' il comportamento che
    la critica chiede di NON usare da solo per la frontiera principale."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    assert dominates_2d(a, b) is True
    assert dominates_2d(b, a) is False


def test_dominates_3d_non_premia_chi_si_astiene():
    """In 3D A NON domina B: A ha energia minore e accuratezza maggiore, ma
    coverage minore (0.40 < 0.95). La terza dimensione blocca il dominio che
    premierebbe un modello che si astiene sul 60% dei quesiti (§4)."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    assert dominates(a, b) is False
    assert dominates(b, a) is False


def test_dominates_3d_con_coverage_maggiore_su_tutto():
    """Un punto domina in 3D solo se non e' peggiore su NESSUNA delle tre
    dimensioni e strettamente migliore su almeno una: D (2 J, 0.95, 0.95)
    domina A (2 J, 0.95, 0.40) per la sola coverage."""
    d = _pt("D", 2.0, 0.95, 0.95)
    a = _pt("A", 2.0, 0.95, 0.40)
    assert dominates(d, a) is True
    assert dominates(a, d) is False


def test_dominates_senza_coverage_riusa_la_2d():
    """Quando la coverage non e' registrata (None) la dominanza ricade sulla
    2D: non si inventa una coverage per decidere un dominio. La retro-
    compatibilita' dei punti legacy e' preservata."""
    a = _pt("A", 2.0, 0.95)
    b = _pt("B", 3.0, 0.90)
    assert dominates(a, b) is True


# --- frontiera 2D vs 3D sull'esempio del piano -------------------------------


def test_frontiera_2d_sull_esempio_del_piano_solo_A():
    """Sull'esempio del piano la frontiera 2D e' {A}: A domina B e C su
    (ECPC, accuracy_covered). E' il risultato che la critica considera
    fuorviante, ed e' quello che il grafico 2D della tesi mostra ancora."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    c = _pt("C", 3.5, 0.85, 1.00)
    front = pareto_frontier_2d([a, b, c])
    assert [p.model_name for p in front] == ["A"]


def test_frontiera_3d_sull_esempio_del_piano_tutti_e_tre():
    """Sull'esempio del piano la frontiera 3D e' {A, B, C}: nessuno domina
    nessuno, perche' chi ha accuratezza alta ha coverage bassa e viceversa.
    La frontiera principale non scarta B e C solo perche' A si astiene."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    c = _pt("C", 3.5, 0.85, 1.00)
    front = pareto_frontier([a, b, c])
    assert {p.model_name for p in front} == {"A", "B", "C"}
    # ordinati per energia crescente
    assert [p.energy_j for p in front] == [2.0, 3.0, 3.5]


def test_frontiera_3d_rimuove_un_punto_dominato_su_tutte_le_dimensioni():
    """Un punto peggiore su tutte e tre le dimensioni esce dalla frontiera 3D:
    E (4 J, 0.80, 0.50) e' dominato da B (3 J, 0.90, 0.95). La frontiera non
    e' 'tutti i punti': scarta chi e' dominato davvero."""
    b = _pt("B", 3.0, 0.90, 0.95)
    e = _pt("E", 4.0, 0.80, 0.50)
    front = pareto_frontier([b, e])
    assert [p.model_name for p in front] == ["B"]


# --- soglia minima di coverage preregistrata ---------------------------------


def test_filter_min_coverage_esclude_chi_non_raggiunge_la_soglia():
    """Una soglia preregistrata di coverage (0.80) esclude A (0.40) dalla
    frontiera principale e tiene B (0.95) e C (1.00). La soglia e' un parametro
    passato dal chiamante, non un numero scelto dopo aver visto i dati (§4)."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    c = _pt("C", 3.5, 0.85, 1.00)
    kept, excluded = filter_min_coverage([a, b, c], 0.80)
    assert {p.model_name for p in kept} == {"B", "C"}
    assert {p.model_name for p in excluded} == {"A"}


def test_filter_min_coverage_none_coverage_e_escluso_fail_closed():
    """Con una soglia attiva, un punto senza coverage registrata non puo'
    dimostrare di raggiungerla: e' escluso (fail-closed), non ammesso per
    default. Ammetterlo significherebbe assumere una coverage non misurata."""
    a = _pt("A", 2.0, 0.95, None)
    b = _pt("B", 3.0, 0.90, 0.95)
    kept, excluded = filter_min_coverage([a, b], 0.80)
    assert [p.model_name for p in kept] == ["B"]
    assert [p.model_name for p in excluded] == ["A"]


def test_filter_min_coverage_soglia_none_non_filtra():
    """Senza soglia preregistrata (None) nessun punto e' escluso: il filtro e'
    disattivato e la frontiera resta quella 3D completa. La scelta di non
    preregistrare una soglia va dichiarata, non nascosta."""
    a = _pt("A", 2.0, 0.95, 0.40)
    b = _pt("B", 3.0, 0.90, 0.95)
    kept, excluded = filter_min_coverage([a, b], None)
    assert {p.model_name for p in kept} == {"A", "B"}
    assert excluded == []


# --- knee: proiezione 2D dichiarata ------------------------------------------


def test_knee_detection_resta_proiezione_2d():
    """Il knee e' una distanza geometrica sull'inviluppo (ECPC, accuratezza):
    resta una proiezione 2D della frontiera, la coverage non entra nella
    distanza. Con meno di tre punti non c'e' knee. Il comportamento 2D e'
    preservato e dichiarato."""
    pts = [_pt("A", 1.0, 0.50, 0.9), _pt("B", 2.0, 0.80, 0.9),
           _pt("C", 4.0, 0.90, 0.9), _pt("D", 8.0, 0.95, 0.9)]
    knee = knee_detection(pts)
    assert knee is not None
    assert knee.model_name in {"A", "B", "C", "D"}
    assert knee_detection(pts[:2]) is None


# --- costruttori: chiavi reali e bug fix -------------------------------------


def test_points_from_evaluation_summary_usa_le_chiavi_per_categoria():
    """Il costruttore legge accuracy_on_determinate e scoring_coverage, le
    chiavi che summarize_records scrive DENTRO ogni categoria. La chiave
    verdict_accuracy_covered esiste solo al livello complessivo: leggerla per
    categoria restituiva sempre None e nessun punto veniva costruito (bug)."""
    summary = {"categories": {"c": {
        "ecpc_j": 2.0, "accuracy_on_determinate": 0.95,
        "scoring_coverage": 0.40, "n_correct": 19, "n_total": 50,
        "ecpc_cluster_bootstrap_95": [1.5, 2.5],
        "verdict_accuracy_covered": 0.99,  # livello complessivo, da NON usare
    }}}
    pts = points_from_evaluation_summary(summary, "m")
    assert len(pts) == 1
    assert pts[0].accuracy_covered == pytest.approx(0.95)
    assert pts[0].coverage == pytest.approx(0.40)
    assert pts[0].energy_j == pytest.approx(2.0)


def test_points_from_taxonomy_result_calcola_la_coverage():
    """Il costruttore da taxonomy calcola la coverage come n_determinate/n_total
    (le chiavi che compute_taxonomy_ecpc scrive per categoria) e la porta nel
    punto: senza, la frontiera 3D non avrebbe la terza dimensione."""
    taxonomy = {"by_category": {"c": {
        "ecpc_j": 3.0, "accuracy_on_determinate": 0.90,
        "n_determinate": 19, "n_total": 20, "n_correct": 17,
        "ecpc_cluster_bootstrap_95": [2.0, 4.0],
    }}}
    pts = points_from_taxonomy_result(taxonomy, "m")
    assert len(pts) == 1
    assert pts[0].coverage == pytest.approx(19 / 20)
    assert pts[0].accuracy_covered == pytest.approx(0.90)