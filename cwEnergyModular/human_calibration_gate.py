# -*- coding: utf-8 -*-
"""P6.7 — Gate 2: validazione dello scoring, indipendente dalla catena energetica.

Modulo di SOLA ANALISI: non e' chiamato dal runner di misura (benchmark_v4.py),
non tocca lo schema CSV P5 (174 colonne congelate), i suoi test girano offline
su dati sintetici e campioni di calibrazione.

La correzione P0 del piano (accuratezza/piano.DOCX, Parte 2, §1.1 e §7) e' che
Krippendorff's alpha misura l'accordo fra annotatori UMANI, non la validita' del
giudice LLM: un accordo umano del 95% puo' coesistere con un giudice che sbaglia
sistematicamente il 20% dei casi. Il gate si articola quindi in due verifiche
distinte, piu' un combinatore:

- Verifica A (accordo umano): alpha NOMINALE per ramo (le etichette
  correct/incorrect non sono una scala ordinata), accordo percentuale,
  distribuzione dei disaccordi, numerosita' per strato, intervallo bootstrap
  riproducibile e adjudication dei disaccordi in un riferimento consolidato.
  La soglia alpha >= 0.8 si applica QUI, all'accordo fra annotatori: e' il
  criterio di affidabilita' del RIFERIMENTO umano -- condizione necessaria per
  usarlo come gold standard della Verifica B, non sufficiente per abilitare il
  giudice, che dipende dalla sola Verifica B (specifica, correzione 1).
- Verifica B (validita' del giudice): contro il riferimento umano adjudicato,
  su un campione INDIPENDENTE, matrice di confusione, accuratezza sui decisi,
  precisione/recall delle due classi, tasso di falsi positivi, astensione e
  copertura, con criteri di accettazione preregistrati (fail-closed: senza
  criteri registrati il gate non promuove).
- Gate 3 (integrate_experiment_status): combina energy_chain_status (P4.9,
  Gate 1, non toccato da questo modulo) e scoring_status (Gate 2) senza
  cancellare l'informazione originaria.

Il gate produce ``scoring_status`` per ramo e complessivo, NON un
``chain_status`` energetico. Un ramo bloccato resta non valutato
(``judge_uncalibrated``), non diventa ``incorrect``.

Riferimenti:
- park2024offsetbias: bias di posizione nei giudici LLM
- ye2024justice: pregiudizio nei giudizi LLM
- tan2024judgebench: benchmark per giudici LLM
- zheng2024llmajsurvey: survey LLM-as-a-judge
"""

from __future__ import annotations

import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from evaluation_runner import BOOTSTRAP_SEED, BOOTSTRAP_RESAMPLES, _percentile

CALIBRATION_THRESHOLD = 0.8
REQUIRED_STRATA = ("number", "short_text", "free_text")
_LABELS = ("correct", "incorrect")
# Vocabolario delle annotazioni umane (Verifica A): tre etichette nominali.
# "indeterminate" e' classe nominale legittima per alpha/kappa, ma NON produce
# riferimento (solo correct/incorrect lo fanno), coerente con la rubrica.
HUMAN_LABELS = ("correct", "incorrect", "indeterminate")
# Verdetto del giudice esplicitamente astensivo: conta come astensione, non
# come classe e non come invalid_label (docstring di verifica_b).
JUDGE_ABSTENTION_LABELS = ("indeterminate",)
# Codici diagnostici: perche' il gate non puo' produrre un numero. Chiuso:
# una causa non elencata qui va dichiarata, non accorpata in silenzio.
DIAGNOSTIC_CODES = ("ok", "insufficient_data", "invalid_schema",
                    "invalid_label", "missing_annotation", "unscored")
# Pavimento di numerosita' per strato, preregistrato e non spostato dai dati:
# sotto questa numerosita' il ramo e' insufficient_data, non validated. Tre
# osservazioni sono il minimo che il protocollo richiede per riportare un
# aggregato (P4.12: la terna di osservazioni ne vuole tre); sotto, un alpha
# 1,0 su due item perfetti e un'accuratezza 1,0 su un solo verdetto deciso
# sarebbero un verdetto su un residuo, non su un campione — e i record
# malformati esclusi non devono poter restringere il campione valido fino a
# quel residuo senza che il gate lo dica.
MIN_PAIRABLE_ITEMS = 3
MIN_DECIDED_ITEMS = 3
# Pavimento sulla frazione ammissibile, preregistrato e non spostato dai dati.
# I denominatori del gate sono sempre il sottoinsieme ammissibile -- un record
# incoerente non si converte -- ma il verdetto deve descrivere il campione, non
# il residuo che le esclusioni lasciano: sotto questa frazione di record
# ammissibili lo strato e' insufficient_data, non validated. Fail-closed, puo'
# solo abbassare uno stato, mai alzarlo. Vale per entrambe le verifiche (quota
# di coppie pairable sulle annotazioni dello strato, quota di item con
# riferimento utilizzabile sui record dello strato) e per la sequenza (quota di
# record che appartengono agli strati misurati).
MIN_ADMISSIBLE_FRACTION = 0.5


# --------------------------------------------------------------------------- #
# Verifica A — accordo fra annotatori umani
# --------------------------------------------------------------------------- #

def krippendorff_alpha(data: Sequence[Sequence[Any]], level: str = "nominal",
                       missing: Any = None) -> float:
    """Krippendorff's alpha NOMINALE per accordo inter-annotatore.

    ``data[i][j]`` e' l'etichetta dell'unita' i secondo l'annotatore j. Le
    etichette correct/incorrect/N/A sono categoriali: non esiste una scala di
    intensita' dichiarata, quindi ``level`` diverso da "nominal" solleva
    ``ValueError`` invece di inventare una metrica di distanza.

    Il valore NON e' clampato: un alpha negativo (disaccordo sistematico,
    peggiore del caso) e' informazione che il clamp a zero cancellerebbe.
    Restituisce NaN se non ci sono unita' con almeno due annotazioni.
    """
    if level != "nominal":
        raise ValueError(
            f"level={level!r} non supportato: le etichette categoriali "
            "correct/incorrect richiedono una metrica nominale; una scala "
            "ordinale/intervallo/ratio va dichiarata esplicitamente prima "
            "di poterla usare."
        )

    units = []
    for row in data:
        unit = [v for v in row if v != missing]
        if len(unit) >= 2:
            units.append(unit)
    if not units:
        return float("nan")

    all_values = set()
    for unit in units:
        all_values.update(unit)
    value_to_idx = {v: i for i, v in enumerate(sorted(all_values, key=repr))}
    n_values = len(value_to_idx)

    coincidence = [[0.0] * n_values for _ in range(n_values)]
    n_pairable = 0
    for unit in units:
        m = len(unit)
        for i in range(m):
            for j in range(m):
                if i != j:
                    vi = value_to_idx[unit[i]]
                    vj = value_to_idx[unit[j]]
                    coincidence[vi][vj] += 1.0 / (m - 1)
        n_pairable += m
    if n_pairable == 0:
        return float("nan")

    do = sum(coincidence[i][i] for i in range(n_values)) / n_pairable
    marginals = [sum(row) for row in coincidence]
    total = sum(marginals)
    if total == 0:
        return float("nan")
    de = sum((m / total) ** 2 for m in marginals)
    if de == 1.0:
        return 1.0 if do == 1.0 else 0.0
    return (do - de) / (1.0 - de)


def bootstrap_alpha_ci(units: Sequence[Sequence[Any]],
                       resamples: int = BOOTSTRAP_RESAMPLES,
                       seed: int = BOOTSTRAP_SEED) -> Optional[tuple[float, float]]:
    """Intervallo percentile 2.5-97.5 di alpha ricampionando gli ITEM.

    I due annotatori viaggiano insieme (l'unita' di ricampiono e' la coppia di
    etichette, non la singola etichetta). Seed fissato: il numero pubblicato
    deve essere rigenerabile. Con meno di due item ogni ricampiono riproduce lo
    stesso alpha e un intervallo di ampiezza zero sarebbe certezza fabbricata:
    restituisce None.
    """
    units = [list(u) for u in units]
    if len(units) < 2 or resamples < 1:
        return None
    rng = random.Random(seed)
    n = len(units)
    stime: list[float] = []
    for _ in range(resamples):
        sample = [units[rng.randrange(n)] for _ in range(n)]
        a = krippendorff_alpha(sample, level="nominal")
        if not math.isnan(a):
            stime.append(a)
    if len(stime) < 2:
        return None
    stime.sort()
    return (round(_percentile(stime, 0.025), 6),
            round(_percentile(stime, 0.975), 6))


def cohen_kappa_nominal(data: Sequence[Sequence[Any]],
                        missing: Any = None) -> Optional[float]:
    """Cohen's kappa NOMINALE per due annotatori (metrica complementare).

    kappa = (p_o - p_e) / (1 - p_e), con p_o = accordo osservato e
    p_e = somma_c (n1_c/N)(n2_c/N) sulle classi nominali effettivamente
    presenti nelle coppie (correct, incorrect, indeterminate quando
    osservato): nessuna gerarchia ordinale, coerentemente con alpha.

    Restituisce None se le coppie utilizzabili sono meno di due, oppure se
    p_e = 1 (una sola classe su tutti gli item: l'accordo atteso dal caso e'
    totale e il coefficiente non e' definito). Il valore NON e' clampato:
    un kappa negativo (disaccordo sistematico) e' informazione che il clamp
    cancellerebbe.
    """
    pairs = []
    for row in data:
        vals = [v for v in row if v != missing]
        if len(vals) == 2:
            pairs.append((vals[0], vals[1]))
    n = len(pairs)
    if n < 2:
        return None
    p_o = sum(1 for a, b in pairs if a == b) / n
    c1: Counter = Counter(a for a, _ in pairs)
    c2: Counter = Counter(b for _, b in pairs)
    p_e = sum((c1[c] / n) * (c2[c] / n) for c in set(c1) | set(c2))
    if p_e == 1.0:
        return None
    return (p_o - p_e) / (1.0 - p_e)


@dataclass(frozen=True)
class StratumAgreement:
    """Accordo umano su un ramo (Verifica A)."""
    stratum: str
    n_items: int
    n_pairable: int
    alpha_nominal: Optional[float]
    alpha_ci_95: Optional[tuple[float, float]]
    kappa_nominal: Optional[float]
    kappa_reason: str
    percent_agreement: Optional[float]
    disagreements: dict[str, int]
    class_distribution: Counter
    passed: bool
    threshold: float
    reason: str
    diagnostics: dict[str, int]


def verifica_a(annotations: Sequence[dict[str, Any]],
               threshold: float = CALIBRATION_THRESHOLD,
               required_strata: Sequence[str] = REQUIRED_STRATA,
               seed: int = BOOTSTRAP_SEED,
               resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, StratumAgreement]:
    """Accordo fra annotatori per ramo, con numerosita' e disaccordi.

    Accanto al coefficiente riporta l'accordo percentuale, la distribuzione dei
    disaccordi (``"a1->a2": conteggio``) e la distribuzione delle classi
    (etichette dell'annotatore 1): un alpha su pochi item non e' la stessa
    evidenza di un alpha su centinaia di annotazioni. La soglia si applica
    all'accordo umano, non alla validita' del giudice.

    ``kappa_nominal`` (Cohen's kappa nominale) e' una metrica complementare
    riportata, NON un criterio: non modifica ``passed``, che resta determinato
    dalla soglia su alpha. E' None quando non calcolabile (meno di due item
    pairable, o p_e = 1 per una classe sola), con la ragione in ``kappa_reason``.

    Le etichette fuori dal vocabolario ammesso (``HUMAN_LABELS``) -- incluse le
    maiuscole -- NON vengono convertite in minuscolo: una normalizzazione non
    dichiarata inventerebbe un dato. Sono invalid_label, escluse da alpha, kappa
    e dalla distribuzione delle classi, e contate in ``diagnostics``; lo stesso
    vale per un annotatore assente (``missing_annotation``) e per un record non
    conforme (``invalid_schema``). Nessun numero e' calcolato su record
    incoerenti: sono esclusi e contati.

    Un record il cui ``answer_type`` e' assente o fuori da ``required_strata``
    non appartiene a nessuno strato: senza un conto proprio sarebbe l'unica via
    per cui un record scompare in silenzio. E' ``invalid_schema`` (lo schema
    canonico dichiara gli strati) e il calcolo prosegue sui soli record dello
    strato. Il pavimento di numerosita' ``MIN_PAIRABLE_ITEMS`` e' preregistrato:
    sotto, il ramo non passa con ragione ``insufficient_data`` e le metriche
    restano riportate (un alpha 1,0 su due item e' un dato vero, non un
    verdetto).
    """
    by_stratum: dict[str, list[dict[str, Any]]] = {}
    n_invalid_schema = 0
    for ann in annotations:
        if not isinstance(ann, dict):
            n_invalid_schema += 1
            continue
        s = str(ann.get("answer_type", "unknown"))
        if s not in required_strata:
            n_invalid_schema += 1
            continue
        by_stratum.setdefault(s, []).append(ann)

    results: dict[str, StratumAgreement] = {}
    for s in required_strata:
        anns = by_stratum.get(s, [])
        n_items = len(anns)
        units: list[list[Any]] = []
        n_agree = 0
        disagreements: Counter = Counter()
        class_dist: Counter = Counter()
        n_missing = 0
        n_invalid_label = 0
        for ann in anns:
            a1 = ann.get("annotator_1")
            a2 = ann.get("annotator_2")
            if a1 is None or a2 is None:
                n_missing += 1
                continue
            if a1 not in HUMAN_LABELS or a2 not in HUMAN_LABELS:
                n_invalid_label += 1
                continue
            class_dist[a1] += 1
            units.append([a1, a2])
            if a1 == a2:
                n_agree += 1
            else:
                disagreements[f"{a1}->{a2}"] += 1
        n_pairable = len(units)
        percent = n_agree / n_pairable if n_pairable else None
        diagnostics = {
            "ok": n_pairable,
            "insufficient_data": 1 if n_pairable < MIN_PAIRABLE_ITEMS else 0,
            "invalid_schema": n_invalid_schema,
            "invalid_label": n_invalid_label,
            "missing_annotation": n_missing,
            "unscored": 0,
        }
        if n_pairable >= 2:
            alpha = krippendorff_alpha(units, level="nominal")
            alpha_val = None if math.isnan(alpha) else round(alpha, 6)
            ci = bootstrap_alpha_ci(units, resamples=resamples, seed=seed)
            kappa_raw = cohen_kappa_nominal(units)
            kappa_val = None if kappa_raw is None else round(kappa_raw, 6)
            kappa_reason = ("" if kappa_val is not None else
                            "kappa not computable: p_e = 1 (single nominal "
                            "class, no chance variability)")
        else:
            alpha_val = None
            ci = None
            kappa_val = None
            kappa_reason = ("insufficient_data: kappa not computable "
                            "(fewer than 2 pairable items)")
        if n_items == 0:
            passed, reason = False, ("insufficient_data: no annotations for "
                                     "this stratum")
        elif alpha_val is None:
            passed, reason = False, ("insufficient_data: alpha not computable "
                                     "(fewer than 2 pairable items)")
        elif alpha_val < threshold:
            passed, reason = False, f"alpha {alpha_val} < threshold {threshold}"
        elif n_pairable < MIN_PAIRABLE_ITEMS:
            passed, reason = False, (
                f"insufficient_data: {n_pairable} pairable items < floor "
                f"{MIN_PAIRABLE_ITEMS} (preregistered minimum numerosity)")
        elif n_pairable < MIN_ADMISSIBLE_FRACTION * n_items:
            passed, reason = False, (
                f"insufficient_data: {n_pairable}/{n_items} pairable items "
                f"below floor {MIN_ADMISSIBLE_FRACTION} (preregistered "
                "admissible fraction: the verdict describes the sample, "
                "not the residue left by exclusions)")
        else:
            passed, reason = True, ""
        results[s] = StratumAgreement(
            stratum=s, n_items=n_items, n_pairable=n_pairable,
            alpha_nominal=alpha_val, alpha_ci_95=ci,
            kappa_nominal=kappa_val, kappa_reason=kappa_reason,
            percent_agreement=percent,
            disagreements=dict(disagreements), class_distribution=class_dist,
            passed=passed, threshold=threshold, reason=reason,
            diagnostics=diagnostics,
        )
    return results


def adjudicated_reference(
        annotations: Sequence[dict[str, Any]]) -> tuple[dict[str, str], dict[str, int]]:
    """Consolida il riferimento umano: etichetta concorde o adjudication.

    Dove i due annotatori concordano su un'etichetta usabile (correct/incorrect)
    il riferimento e' quell'etichetta; dove discordano serve un'adjudication
    esplicita. Un disaccordo senza adjudication NON produce un riferimento e
    viene contato: il giudice non puo' essere validato contro un riferimento
    che non esiste.
    """
    reference: dict[str, str] = {}
    n_items = n_agreed = n_disagreements = n_adjudicated = n_without_reference = 0
    n_missing = n_invalid_label = n_invalid_schema = 0
    for ann in annotations:
        n_items += 1
        if not isinstance(ann, dict):
            n_invalid_schema += 1
            continue
        a1 = ann.get("annotator_1")
        a2 = ann.get("annotator_2")
        tid = ann.get("task_id")
        if a1 is None or a2 is None:
            n_missing += 1
        elif a1 not in HUMAN_LABELS or a2 not in HUMAN_LABELS:
            n_invalid_label += 1
        if a1 == a2 and a1 in _LABELS:
            reference[tid] = a1
            n_agreed += 1
        elif a1 == a2:
            n_without_reference += 1
        else:
            n_disagreements += 1
            adj = ann.get("adjudicated")
            if adj in _LABELS:
                reference[tid] = adj
                n_adjudicated += 1
            else:
                n_without_reference += 1
    stats = {
        "n_items": n_items,
        "n_agreed": n_agreed,
        "n_disagreements": n_disagreements,
        "n_adjudicated": n_adjudicated,
        "n_without_reference": n_without_reference,
        "n_missing_annotation": n_missing,
        "n_invalid_label": n_invalid_label,
        "n_invalid_schema": n_invalid_schema,
    }
    return reference, stats


# --------------------------------------------------------------------------- #
# Verifica B — validita' del giudice contro il riferimento umano
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class JudgeAcceptanceCriteria:
    """Criteri di accettazione del giudice, da preregistrare PRIMA dei dati.

    Tutti None finche' non registrati: senza criteri il gate si dichiara non
    eseguibile (fail-closed), non promuove il giudice con soglie inventate al
    momento. I numeri definitivi dipendono dalla distribuzione dei task e non
    si fissano a priori senza conoscerla (§1.4 del piano).
    """
    min_precision_correct: Optional[float] = None
    min_recall_correct: Optional[float] = None
    max_fp_rate: Optional[float] = None
    min_accuracy: Optional[float] = None
    min_coverage: Optional[float] = None

    def __post_init__(self) -> None:
        """E2: una soglia di coverage nulla, negativa o non definita non e' un
        criterio. Non esclude nulla -- un giudice che si astiene su tutti gli
        item la soddisfa -- quindi preregistrarla permette un ramo
        ``validated`` su una copertura arbitraria, con tutti gli altri criteri
        calcolati sui pochi item decisi. ``None`` resta ammesso (criterio non
        registrato, gate fail-closed): qui non si inventa una soglia, si
        rifiuta quella che non discrimina.
        """
        copertura = self.min_coverage
        if copertura is not None and not copertura > 0:
            raise ValueError(
                "min_coverage deve essere positivo o None (non registrato): "
                f"una soglia di {copertura} non esclude alcuna astensione e "
                "non e' un criterio scientificamente significativo"
            )

    def registered(self) -> bool:
        return all(v is not None for v in (
            self.min_precision_correct, self.min_recall_correct,
            self.max_fp_rate, self.min_accuracy, self.min_coverage))


def _ratio(num: float, den: float) -> Optional[float]:
    return num / den if den else None


def _wilson(k: int, n: int) -> Optional[list[float]]:
    """Intervallo di Wilson a livello di riga (z = 1.959963984540054)."""
    if n <= 0:
        return None
    z = 1.959963984540054
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, centre - margin), 6),
            round(min(1.0, centre + margin), 6)]


def _f1(precision: Optional[float], recall: Optional[float]) -> Optional[float]:
    """F1 = 2*P*R/(P+R) dalle precision/recall gia' calcolate.

    None se precision o recall non sono definite (denominatore nullo) oppure
    se P+R = 0: la classe non ha veri positivi e l'F1 non e' calcolabile, non
    vale zero. I denominatori di precision/recall non vengono toccati.
    """
    if precision is None or recall is None:
        return None
    denom = precision + recall
    if denom == 0:
        return None
    return 2 * precision * recall / denom


@dataclass(frozen=True)
class JudgeValidity:
    """Validita' del giudice su un ramo contro il riferimento adjudicato."""
    stratum: str
    n_items: int
    n_records_in_stratum: int
    n_reference: int
    n_decided: int
    n_abstained: int
    confusion: dict[str, dict[str, int]]
    accuracy: Optional[float]
    precision_correct: Optional[float]
    recall_correct: Optional[float]
    precision_incorrect: Optional[float]
    recall_incorrect: Optional[float]
    f1_correct: Optional[float]
    f1_incorrect: Optional[float]
    f1_reason: str
    fp_rate: Optional[float]
    abstention_rate: Optional[float]
    coverage: Optional[float]
    accuracy_ci_95: Optional[list[float]]
    precision_correct_ci_95: Optional[list[float]]
    recall_correct_ci_95: Optional[list[float]]
    fp_rate_ci_95: Optional[list[float]]
    passed: bool
    failed_criteria: tuple[str, ...]
    diagnostics: dict[str, int]


def verifica_b(items: Sequence[dict[str, Any]],
               criteria: JudgeAcceptanceCriteria,
               required_strata: Sequence[str] = REQUIRED_STRATA) -> dict[str, JudgeValidity]:
    """Matrice di confusione e metriche del giudice contro il riferimento umano.

    Ogni item porta ``reference`` (etichetta umana adjudicata) e
    ``judge_verdict``. La matrice e' ``confusion[reference][colonna]`` con
    colonne correct/incorrect/abstained: un verdetto non in {correct, incorrect}
    e' un'astensione. L'accuratezza e' calcolata sui soli decisi; il tasso di
    falsi positivi ``IC/(IC+II)`` e' il danno che il piano (§1.1) segnala come
    invisibile alla sola accuratezza: un giudice che promuove risposte errate
    gonfia il numeratore di ECPC.

    ``fp_rate`` e' None quando non esistono riferimenti incorrect (IC+II=0):
    in quel caso il criterio ``max_fp_rate`` e' soddisfatto vacuamente, perche'
    senza casi errati non puo' esserci un falso positivo. La classe incorrect
    resta non testata e la matrice lo mostra.

    ``f1_correct`` e ``f1_incorrect`` (F1 = 2*P*R/(P+R)) sono metriche riportate
    per classe, derivate dalle precision/recall gia' calcolate senza toccarne i
    denominatori. Sono None quando P+R = 0 o precision/recall non sono definite,
    con la ragione in ``f1_reason``. NON sono criteri di accettazione: non
    modificano ``passed`` ne' ``failed_criteria``. Le classi sono solo
    {correct, incorrect}: un riferimento indeterminate e' escluso e un verdetto
    indeterminate del giudice e' un'astensione, non una classe.

    La diagnostica distingue perche' un item non ha prodotto un confronto.
    ``unscored`` per strato conta due cause attribuibili allo strato: un
    verdetto del giudice assente (il giudizio non e' disponibile) e un
    riferimento che il record stesso dichiara inutilizzabile (chiave
    ``reference`` presente con valore fuori vocabolario, ``None`` compreso) --
    in entrambi i casi e' il record a dirlo, e il record appartiene a uno
    strato. Un riferimento NON allegato (chiave ``reference`` assente) non lo
    dichiara il record: lo costruisce il gate, quindi una costruzione mancata
    e' un fatto di sequenza. Contarlo nel dict di ogni strato fuorvierebbe --
    con tre strati un solo record sembrerebbe tre difetti -- percio' lo conta
    il gate, una volta sola, nel proprio ``diagnostics``. Un record fuori da
    ``required_strata`` (o non-dict) e' ``invalid_schema``, non ``unscored``:
    lo schema canonico dichiara gli strati e un record fuori perimetro non
    appartiene ad alcuno. Il pavimento ``MIN_DECIDED_ITEMS`` blocca il giudizio
    delle metriche sotto la numerosita' preregistrata: sotto, il solo criterio
    fallito e' ``insufficient_numerosity`` -- un ``fp_rate`` None su un item
    solo non e' assenza di falsi positivi, e' assenza di casi. Il pavimento
    ``MIN_ADMISSIBLE_FRACTION`` blocca il giudizio quando i record con
    riferimento utilizzabile sono una minoranza di quelli attribuiti allo
    strato (``n_records_in_stratum``, esposto per ricostruire la frazione): le
    metriche sui superstiti sono calcolabili e spesso brillanti, ma descrivono
    il residuo delle esclusioni, non il campione.
    """
    by_stratum: dict[str, list[dict[str, Any]]] = {}
    n_riferimento_dichiarato: dict[str, int] = {}
    n_record_stratum: dict[str, int] = {}
    n_invalid_schema = 0
    for item in items:
        if not isinstance(item, dict):
            n_invalid_schema += 1
            continue
        s = str(item.get("answer_type", "unknown"))
        if s not in required_strata:
            n_invalid_schema += 1
            continue
        n_record_stratum[s] = n_record_stratum.get(s, 0) + 1
        if item.get("reference") not in _LABELS:
            if "reference" in item:
                n_riferimento_dichiarato[s] = n_riferimento_dichiarato.get(s, 0) + 1
            continue
        by_stratum.setdefault(s, []).append(item)

    results: dict[str, JudgeValidity] = {}
    for s in required_strata:
        its = by_stratum.get(s, [])
        n_items = len(its)
        n_records_in_stratum = n_record_stratum.get(s, 0)
        confusion = {r: {"correct": 0, "incorrect": 0, "abstained": 0}
                     for r in _LABELS}
        n_invalid_label = 0
        n_unscored_verdict = 0
        for item in its:
            ref = item["reference"]
            jv = item.get("judge_verdict")
            if jv is None:
                n_unscored_verdict += 1
            elif jv not in _LABELS and jv not in JUDGE_ABSTENTION_LABELS:
                n_invalid_label += 1
            col = jv if jv in _LABELS else "abstained"
            confusion[ref][col] += 1
        cc = confusion["correct"]["correct"]
        ci = confusion["correct"]["incorrect"]
        ic = confusion["incorrect"]["correct"]
        ii = confusion["incorrect"]["incorrect"]
        n_abstained = (confusion["correct"]["abstained"]
                       + confusion["incorrect"]["abstained"])
        n_decided = cc + ci + ic + ii
        accuracy = _ratio(cc + ii, n_decided)
        precision_correct = _ratio(cc, cc + ic)
        recall_correct = _ratio(cc, cc + ci)
        precision_incorrect = _ratio(ii, ii + ci)
        recall_incorrect = _ratio(ii, ii + ic)
        fp_rate = _ratio(ic, ic + ii)
        abstention_rate = _ratio(n_abstained, n_items)
        coverage = _ratio(n_decided, n_items)
        f1_correct = _f1(precision_correct, recall_correct)
        f1_incorrect = _f1(precision_incorrect, recall_incorrect)
        f1_missing = [name for name, val in (("correct", f1_correct),
                                             ("incorrect", f1_incorrect))
                      if val is None]
        f1_reason = ("F1 not computable for class(es) " + ", ".join(f1_missing)
                     + ": precision + recall = 0 or undefined") if f1_missing else ""

        diagnostics = {
            "ok": n_decided,
            "insufficient_data": 1 if n_decided < MIN_DECIDED_ITEMS else 0,
            "invalid_schema": n_invalid_schema,
            "invalid_label": n_invalid_label,
            "missing_annotation": 0,
            "unscored": n_unscored_verdict + n_riferimento_dichiarato.get(s, 0),
        }

        failed: list[str] = []
        floors: list[str] = []
        if n_decided < MIN_DECIDED_ITEMS:
            floors.append("insufficient_numerosity")
        if n_items < MIN_ADMISSIBLE_FRACTION * n_records_in_stratum:
            floors.append("insufficient_admissible_fraction")
        if not criteria.registered():
            failed.append("criteria_not_registered")
        elif n_decided == 0:
            failed.append("no_decided_verdicts")
        elif floors:
            # I pavimenti bloccano il giudizio delle metriche: sotto, un
            # min_accuracy non fallito non e' un giudice valido, e' un giudice
            # giudicato su un residuo. Le due cause restano distinte e
            # compaiono entrambe quando entrambe aprono.
            failed.extend(floors)
        else:
            if not (precision_correct is not None
                    and precision_correct >= criteria.min_precision_correct):
                failed.append("min_precision_correct")
            if not (recall_correct is not None
                    and recall_correct >= criteria.min_recall_correct):
                failed.append("min_recall_correct")
            if not (fp_rate is None or fp_rate <= criteria.max_fp_rate):
                failed.append("max_fp_rate")
            if not (accuracy is not None and accuracy >= criteria.min_accuracy):
                failed.append("min_accuracy")
            if not (coverage is not None and coverage >= criteria.min_coverage):
                failed.append("min_coverage")

        results[s] = JudgeValidity(
            stratum=s, n_items=n_items,
            n_records_in_stratum=n_records_in_stratum, n_reference=n_items,
            n_decided=n_decided, n_abstained=n_abstained, confusion=confusion,
            accuracy=accuracy, precision_correct=precision_correct,
            recall_correct=recall_correct, precision_incorrect=precision_incorrect,
            recall_incorrect=recall_incorrect,
            f1_correct=f1_correct, f1_incorrect=f1_incorrect, f1_reason=f1_reason,
            fp_rate=fp_rate,
            abstention_rate=abstention_rate, coverage=coverage,
            accuracy_ci_95=_wilson(cc + ii, n_decided),
            precision_correct_ci_95=_wilson(cc, cc + ic),
            recall_correct_ci_95=_wilson(cc, cc + ci),
            fp_rate_ci_95=_wilson(ic, ic + ii),
            passed=not failed, failed_criteria=tuple(failed),
            diagnostics=diagnostics,
        )
    return results


# --------------------------------------------------------------------------- #
# Gate 2 complessivo + Gate 3 combinatore
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ScoringValidationGateResult:
    """Esito del gate di validazione dello scoring (Gate 2).

    Non contiene alcun ``chain_status``: la validita' della misura energetica
    (P4.9, Gate 1) e' una proprieta' distinta e resta indipendente.
    """
    agreement: tuple[StratumAgreement, ...]
    validity: tuple[JudgeValidity, ...]
    scoring_status_per_stratum: dict[str, str]
    scoring_status: str
    n_calibration_items: int
    n_validation_items: int
    reference_stats: dict[str, int]
    diagnostics: dict[str, int]
    admissible_fractions: dict[str, Optional[float]]
    notes: str


def _load_annotations(path: str | Path) -> tuple[list[dict[str, Any]], int]:
    """Legge un JSONL; appiattisce il formato compatto con ``annotations``.

    Restituisce gli record e il conteggio di quelli non conformi allo schema
    canonico (riga JSON non-oggetto, campo ``annotations`` non-oggetto): sono
    esclusi dal calcolo e contati, perche' un numero letto su un record
    illeggibile sarebbe un dato senza record.

    L'identita' invece e' un PREREQUISITO, non un difetto di contenuto. Il
    controllo di indipendenza fra calibrazione e validazione opera per
    ``task_id``: un record senza task_id (assente, vuoto, di soli spazi o non
    stringa) quel controllo non lo vede, quindi la stessa osservazione
    potrebbe comparire due volte, una volta anonima. Un task_id duplicato
    dentro la stessa sequenza e' la stessa osservazione contata due volte, che
    nessuna sovrascrittura (tacita sostituzione del primo record con il
    secondo) risolve. In entrambi i casi il loader rifiuta il file con
    ``ValueError``, che nomina il record e la riga: l'errore e' ricostruibile
    senza riaprire i dati.

    Il confronto d'identita' -- duplicato dentro la sequenza, sovrapposizione
    fra le due sequenze -- opera sulla forma normalizzata (spazi iniziali e
    finali rimossi): due id che differiscono soltanto per quelli sono la
    stessa identita', e un confronto per stringa esatta non li vedrebbe
    coincidere. Il record conserva il proprio task_id originale: la
    normalizzazione riguarda il confronto, non una riscrittura del dato.
    """
    path = Path(path)
    out: list[dict[str, Any]] = []
    n_invalid_schema = 0
    visti: dict[str, int] = {}
    with path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not isinstance(rec, dict):
                n_invalid_schema += 1
                continue
            ann = dict(rec)
            nested = rec.get("annotations")
            if isinstance(nested, dict):
                ann.update(nested)
            elif "annotations" in rec:
                n_invalid_schema += 1
                continue
            task_id = ann.get("task_id")
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError(
                    f"{path}: riga {line_num}: record senza task_id "
                    "utilizzabile come identita'. L'identita' e' obbligatoria: "
                    "senza di essa l'indipendenza del campione e l'unicita' "
                    "dell'osservazione non sono verificabili, quindi il gate "
                    "non parte."
                )
            identita = task_id.strip()
            if identita in visti:
                raise ValueError(
                    f"{path}: task_id '{task_id}' duplicato (righe "
                    f"{visti[identita]} e {line_num}): la stessa osservazione "
                    "non entra due volte nel gate e nessuna sovrascrittura "
                    "sostituisce il primo record con il secondo. Due id che "
                    "differiscono soltanto per spazi iniziali o finali sono "
                    "la stessa identita'."
                )
            visti[identita] = line_num
            out.append(ann)
    return out, n_invalid_schema


def _frazione_ammissibile_sequenza(
        records: Sequence[dict[str, Any]],
        required_strata: Sequence[str]) -> Optional[float]:
    """Quota di record della sequenza che appartengono agli strati misurati.

    Un record fuori perimetro (o non-oggetto, gia' escluso dal loader) non
    entra in alcuno strato: senza questa frazione, un campione di cui la
    maggioranza non e' misurabile sarebbe invisibile a ogni denominatore. None
    se la sequenza e' vuota (non c'e' campione, non c'e' frazione).
    """
    n = len(records)
    if n == 0:
        return None
    in_strati = sum(1 for a in records
                    if isinstance(a, dict)
                    and str(a.get("answer_type", "unknown")) in required_strata)
    return in_strati / n


def run_scoring_validation_gate(
        calibration_file: str | Path,
        validation_file: str | Path,
        criteria: JudgeAcceptanceCriteria,
        threshold: float = CALIBRATION_THRESHOLD,
        required_strata: Sequence[str] = REQUIRED_STRATA,
        seed: int = BOOTSTRAP_SEED,
        resamples: int = BOOTSTRAP_RESAMPLES) -> ScoringValidationGateResult:
    """Esegue Verifica A (calibrazione) e Verifica B (validazione indipendente).

    Il campione di validazione deve essere indipendente da quello di
    calibrazione: gli stessi item non possono servire sia per modificare la
    rubrica sia per dichiarare il giudice validato. Una sovrapposizione di
    task_id e' un errore dichiarato (``ValueError``), non un'avvertenza.

    Stato per ramo: ``validated`` solo se l'accordo umano supera la soglia E il
    giudice supera i criteri preregistrati; altrimenti ``human_agreement_failed``,
    ``criteria_not_registered``, ``insufficient_data`` o ``judge_uncalibrated``.
    ``insufficient_data`` nomina il pavimento di numerosita' preregistrato
    (``MIN_PAIRABLE_ITEMS`` item pairable in Verifica A, ``MIN_DECIDED_ITEMS``
    verdetti decisi in Verifica B): sotto, il campione non supporta un verdetto.
    ``human_agreement_failed`` dice l'opposto -- il campione c'e' e non concorda.
    Il pavimento e' fail-closed, puo' solo abbassare uno stato, mai alzarlo. Un
    ramo bloccato non blocca gli altri (§7.1).

    ``diagnostics`` riporta il conteggio dei difetti per categoria
    (``DIAGNOSTIC_CODES``). I conteggi di sequenza -- riga non-oggetto, record
    fuori dagli strati, riferimento non producibile -- sono authoritative a
    questo livello e non negli strati: sommarli per strato conterebbe piu' volte
    lo stesso record. Le cause di sequenza sono mutuamente esclusive, con
    precedenza ``invalid_schema`` su ``unscored`` (un record fuori perimetro
    senza riferimento e' invalid_schema una volta sola); le cause di contenuto
    (``invalid_label``, ``missing_annotation``) possono invece toccare lo stesso
    record. La diagnostica non cambia ``passed`` ne' i denominatori: gli stati
    per ramo li muove solo il pavimento, che e' regola di verdetto
    preregistrata, non informazione additiva. Un record difettoso e' escluso
    dal calcolo e contato, mai convertito ne' promosso.

    ``required_strata'' non puo' essere assente ne' vuoto: una configurazione
    senza strati obbligatori misura zero item e il verdetto complessivo
    risulterebbe ``validated`` per costruzione (``n_validated ==
    len(required_strata) == 0``), contando zero evidenze come successo. Il
    rifiuto e' un errore dichiarato (``ValueError``), non un avviso.
    """
    if required_strata is None:
        required_strata = ()
    required_strata = tuple(required_strata)
    if not required_strata:
        raise ValueError(
            "required_strata assente o vuoto: senza strati obbligatori il "
            "gate non misura alcun item, e il verdetto complessivo sarebbe "
            "validated per costruzione (n_validated == len(required_strata) "
            "== 0). La configurazione e' rifiutata prima di leggere i dati."
        )
    cal, n_cal_invalid_schema = _load_annotations(calibration_file)
    val, n_val_invalid_schema = _load_annotations(validation_file)
    # La sovrapposizione si decide sulla forma normalizzata: due id che
    # differiscono soltanto per spazi iniziali/finali sono la stessa identità,
    # e un confronto per stringa esatta non li vedrebbe coincidere -- la stessa
    # osservazione servirebbe alla rubrica e al giudizio, con l'indipendenza
    # verificata per falso.
    cal_ids = {str(a["task_id"]).strip() for a in cal}
    val_ids = {str(a["task_id"]).strip() for a in val}
    overlap = cal_ids & val_ids
    if overlap:
        raise ValueError(
            f"campione di validazione non indipendente: {len(overlap)} task_id "
            f"in comune con la calibrazione (es. {sorted(overlap)[:3]})"
        )

    agreement = verifica_a(cal, threshold=threshold,
                           required_strata=required_strata,
                           seed=seed, resamples=resamples)
    reference, ref_stats = adjudicated_reference(val)
    val_items = []
    for ann in val:
        item = dict(ann)
        # Il riferimento e' un campo derivato: il gate ne e' l'unico
        # produttore, quindi una chiave ``reference'' in ingresso e' scartata
        # (sarebbe un riferimento non adjudicated) e la chiave resta ASSENTE
        # quando il riferimento non e' producibile. Assente, non None: la
        # distinzione dice chi ha la causa -- il record (per strato) o la
        # sequenza (il gate) -- vedi la docstring di verifica_b.
        item.pop("reference", None)
        ref = reference.get(ann.get("task_id"))
        if ref is not None:
            item["reference"] = ref
        val_items.append(item)
    validity = verifica_b(val_items, criteria, required_strata=required_strata)

    # Conteggi di sequenza authoritative. Non sono la somma dei dict per
    # strato: una riga non-oggetto, un record fuori dagli strati e un
    # riferimento non costruito non appartengono ad alcuno strato, quindi
    # sommarli per strato conterebbe lo stesso record tre volte con tre
    # strati. invalid_schema ha la precedenza su unscored: un record fuori
    # perimetro senza riferimento e' contato una volta sola, come
    # invalid_schema.
    n_invalid_schema = (n_cal_invalid_schema + n_val_invalid_schema
                        + sum(1 for a in cal if str(a.get("answer_type",
                                                         "unknown"))
                              not in required_strata)
                        + sum(1 for a in val if str(a.get("answer_type",
                                                        "unknown"))
                              not in required_strata))
    n_unscored = sum(1 for a in val
                     if str(a.get("answer_type", "unknown")) in required_strata
                     and a.get("task_id") not in reference)

    # Frazione ammissibile per sequenza (E1 dell'audit). Il denominatore e' il
    # numero di record letti dal loader: una riga non-oggetto non entra in
    # alcuno strato e non deve potere restringere il campione misurabile senza
    # che il verdetto lo veda.
    admissible_fractions = {
        "calibration": _frazione_ammissibile_sequenza(cal, required_strata),
        "validation": _frazione_ammissibile_sequenza(val, required_strata),
    }

    statuses: dict[str, str] = {}
    for s in required_strata:
        a = agreement[s]
        v = validity[s]
        if v.n_items == 0:
            statuses[s] = "insufficient_data"
        elif not a.passed:
            # Due cause distinte: senza campione (pavimento, alpha non
            # calcolabile) il ramo e' insufficient_data; con campione che non
            # concorda e' human_agreement_failed. Collassarle direbbe "gli
            # annotatori non concordano" a un ramo con due soli item.
            statuses[s] = ("insufficient_data"
                           if a.reason.startswith("insufficient_data")
                           else "human_agreement_failed")
        elif "insufficient_numerosity" in v.failed_criteria:
            statuses[s] = "insufficient_data"
        elif "insufficient_admissible_fraction" in v.failed_criteria:
            statuses[s] = "insufficient_data"
        elif v.n_decided == 0:
            statuses[s] = "insufficient_data"
        elif v.passed:
            statuses[s] = "validated"
        elif "criteria_not_registered" in v.failed_criteria:
            statuses[s] = "criteria_not_registered"
        else:
            statuses[s] = "judge_uncalibrated"

    # Guardia di sequenza (E1 dell'audit): se la maggioranza dei record di una
    # sequenza non appartiene agli strati misurati, il gate non ha misurato il
    # campione che il protocollo dichiara -- i difetti non entrano in alcuno
    # strato, quindi nessun denominatore li vede. Fail-closed: nessun ramo puo'
    # essere promosso, qualunque siano le metriche sui superstiti.
    sequenze_sotto_pavimento = [
        nome for nome, frazione in admissible_fractions.items()
        if frazione is not None and frazione < MIN_ADMISSIBLE_FRACTION
    ]
    if sequenze_sotto_pavimento:
        for s in required_strata:
            statuses[s] = "insufficient_data"

    n_validated = sum(1 for st in statuses.values() if st == "validated")
    if n_validated == len(required_strata):
        overall = "validated"
    elif n_validated > 0:
        overall = "partially_validated"
    else:
        overall = "not_validated"

    notes = (
        "Gate 2 (scoring): Verifica A misura l'accordo fra annotatori umani "
        f"(alpha nominale, soglia {threshold}); Verifica B misura la validita' "
        "del giudice contro il riferimento adjudicato su campione indipendente, "
        "con criteri preregistrati. La soglia alpha e' il criterio di "
        "affidabilita' del riferimento umano: condizione necessaria per usarlo "
        "come gold standard, non sufficiente per abilitare il giudice, che "
        "dipende dalla sola Verifica B (specifica, correzione 1). Questo stato "
        "NON e' la catena energetica P4.9 (Gate 1): integrate_experiment_status "
        "combina i due senza cancellarli. Un ramo judge_uncalibrated resta non "
        "valutato (is_correct=None), non incorrect. Riferimenti: "
        "park2024offsetbias, ye2024justice, tan2024judgebench, "
        "zheng2024llmajsurvey."
    )
    diagnostics = {
        "ok": (sum(a.diagnostics.get("ok", 0) for a in agreement.values())
               + sum(v.diagnostics.get("ok", 0) for v in validity.values())),
        "insufficient_data": (sum(a.diagnostics.get("insufficient_data", 0)
                                  for a in agreement.values())
                              + sum(v.diagnostics.get("insufficient_data", 0)
                                    for v in validity.values())),
        # Conteggi di sequenza authoritative (vedi la docstring): il loader e'
        # l'autorita' sui record non conformi allo schema, i record fuori dagli
        # strati non appartengono ad alcuno e un riferimento non costruito non
        # e' attribuibile a uno strato.
        "invalid_schema": n_invalid_schema,
        "invalid_label": (sum(a.diagnostics.get("invalid_label", 0)
                              for a in agreement.values())
                          + ref_stats.get("n_invalid_label", 0)
                          + sum(v.diagnostics.get("invalid_label", 0)
                                for v in validity.values())),
        "missing_annotation": (sum(a.diagnostics.get("missing_annotation", 0)
                                   for a in agreement.values())
                               + ref_stats.get("n_missing_annotation", 0)),
        "unscored": n_unscored,
    }
    n_defects = sum(diagnostics[k] for k in diagnostics if k != "ok")
    if n_defects:
        notes += (
            " Diagnostica dei difetti (conteggio per causa: le cause di "
            "sequenza sono mutuamente esclusive con precedenza invalid_schema "
            "su unscored, mentre una causa di contenuto -- etichetta umana "
            "fuori vocabolario, annotazione mancante -- puo' toccare lo stesso "
            "record): "
            + ", ".join(f"{k}={v}" for k, v in sorted(diagnostics.items())
                        if k != "ok" and v > 0)
            + ". I record difettosi sono esclusi dal calcolo, non convertiti: "
            "nessun numero di questo gate e' ottenuto da dati incoerenti."
        )
    if sequenze_sotto_pavimento:
        dettaglio = ", ".join(
            f"{nome}={admissible_fractions[nome]:.3f}"
            for nome in sequenze_sotto_pavimento)
        notes += (
            " Frazione ammissibile sotto il pavimento preregistrato "
            f"({dettaglio} < {MIN_ADMISSIBLE_FRACTION}): la maggioranza dei "
            "record non appartiene agli strati misurati, quindi il gate non ha "
            "misurato il campione che il protocollo dichiara e nessun ramo e' "
            "promosso. Fail-closed: il pavimento puo' solo abbassare uno "
            "stato."
        )
    return ScoringValidationGateResult(
        agreement=tuple(agreement[s] for s in required_strata),
        validity=tuple(validity[s] for s in required_strata),
        scoring_status_per_stratum=statuses,
        scoring_status=overall,
        n_calibration_items=len(cal),
        n_validation_items=len(val),
        reference_stats=ref_stats,
        diagnostics=diagnostics,
        admissible_fractions=admissible_fractions,
        notes=notes,
    )


def integrate_experiment_status(energy_chain_status: str,
                                scoring_status: str) -> str:
    """Gate 3: combina i due gate senza cancellare l'informazione originaria.

    Una catena energetica non valida non diventa mai ``validated`` per merito
    dello scoring; una catena valida con scoring parziale resta
    ``partially_validated``.
    """
    if energy_chain_status != "validated":
        return "energy_not_validated"
    if scoring_status == "validated":
        return "validated"
    if scoring_status == "partially_validated":
        return "partially_validated"
    return "scoring_not_validated"


def judge_gated_flags(result: ScoringValidationGateResult) -> dict[str, bool]:
    """Flag ``judge_gated_{ramo}`` per evaluator.py.

    True quando il ramo non e' ``validated``: evaluator.py deve forzare
    ``is_correct=None`` con motivo ``judge_uncalibrated`` per quel ramo, senza
    disabilitare il giudice sugli altri rami.
    """
    return {f"judge_gated_{s}": (status != "validated")
            for s, status in result.scoring_status_per_stratum.items()}


# --------------------------------------------------------------------------- #
# Template di preregistrazione
# --------------------------------------------------------------------------- #

def calibration_protocol_template() -> dict[str, Any]:
    """Template di preregistrazione del protocollo di calibrazione/validazione.

    Da commitare in experiment_results/ PRIMA della campagna. I criteri del
    giudice sono campi da fissare prima dei dati (None finche' non registrati);
    il campione di validazione e' indipendente e le risposte coprono piu'
    tipologie (§10), non solo le due etichette cieche.
    """
    return {
        "protocol_version": "P6.7-20261111",
        "strata": list(REQUIRED_STRATA),
        "alpha_level": "nominal",
        "rubric": {
            "number": "Valore numerico con tolleranza assoluta/relativa dichiarata",
            "short_text": "Testo breve con alternative a confini di parola",
            "free_text": "Fatti richiesti e proibiti (claim-level)",
        },
        "annotators": 2,
        "blind": True,
        "total_items": 40,
        "pilot_declaration": (
            "I 40 item sono un pilota: l'intervallo bootstrap di alpha dice "
            "quanto pesa la numerosita'. Se la precisione dell'intervallo e' "
            "insufficiente per decidere la soglia, si raccoglie un campione "
            "aggiuntivo prima di congelare i criteri; non si sposta la soglia "
            "dopo aver visto i dati. Il pavimento di numerosita' per ramo "
            "(verifica_a.min_pairable_items, verifica_b.min_decided_items) e' "
            "preregistrato con la soglia: sotto, il ramo e' insufficient_data, "
            "non validated -- un verdetto su un residuo di campione non e' un "
            "verdetto. Il pavimento sulla frazione ammissibile "
            "(verifica_a.min_admissible_fraction, "
            "verifica_b.min_admissible_fraction) chiude il residuo: se i record "
            "con riferimento utilizzabile sono una minoranza di quelli attribuiti "
            "al ramo, il ramo e' insufficient_data anche quando le metriche sui "
            "superstiti sono brillanti, perche' descrivono il residuo delle "
            "esclusioni e non il campione."
        ),
        "verifica_a": {
            "what": "Accordo fra annotatori umani (NON validita' del giudice)",
            "alpha_role": (
                "Condizione NECESSARIA per usare il riferimento umano come "
                "gold standard, NON criterio sufficiente per abilitare il "
                "giudice: l'abilitazione viene dalla sola Verifica B "
                "(specifica, correzione 1)."
            ),
            "threshold_alpha": CALIBRATION_THRESHOLD,
            "min_pairable_items": MIN_PAIRABLE_ITEMS,
            "min_admissible_fraction": MIN_ADMISSIBLE_FRACTION,
            "metrics": ["alpha_nominal", "kappa_nominal", "percent_agreement",
                        "disagreements", "class_distribution",
                        "n_items_per_stratum"],
            "ci_method": "item-level bootstrap percentile 2.5-97.5",
            "seed": BOOTSTRAP_SEED,
            "resamples": BOOTSTRAP_RESAMPLES,
            "adjudication": (
                "I disaccordi sono adjudicati da un terzo revisore cieco; "
                "l'etichetta adjudicata entra nel riferimento consolidato. "
                "Un disaccordo senza adjudication non produce riferimento."
            ),
        },
        "verifica_b": {
            "what": "Validita' del giudice contro il riferimento umano adjudicato",
            "independent_sample": True,
            "min_decided_items": MIN_DECIDED_ITEMS,
            "min_admissible_fraction": MIN_ADMISSIBLE_FRACTION,
            "acceptance_criteria": {
                "min_precision_correct": None,
                "min_recall_correct": None,
                "max_fp_rate": None,
                "min_accuracy": None,
                "min_coverage": None,
            },
            "metrics": ["confusion_matrix", "accuracy_on_decided",
                        "precision_correct", "recall_correct",
                        "precision_incorrect", "recall_incorrect",
                        "f1_correct", "f1_incorrect",
                        "fp_rate", "abstention_rate", "coverage"],
            "note": (
                "Il tasso di falsi positivi (IC/(IC+II)) e' il danno principale "
                "a ECPC: un giudice che promuove risposte errate gonfia il "
                "numeratore di corrette. L'accuratezza complessiva da sola non "
                "lo vede. Criteri None = non preregistrati = gate fail-closed."
            ),
        },
        "verdict_model": {
            "alpha_necessaria_non_sufficiente": True,
            "judge_enabling_criterion": "verifica_b",
            "enabling_rule": (
                "Un ramo e' validated solo se Verifica A supera la soglia E "
                "Verifica B supera i criteri preregistrati: un buon accordo "
                "umano non abilita il giudice. La soglia alpha abilita l'uso "
                "del riferimento umano come gold standard, non il giudice "
                "(specifica, correzione 1)."
            ),
        },
        "response_typologies": [
            "corrette",
            "scorrette",
            "errori parziali (risposta incompleta)",
            "informazioni superflue (risposta corretta con contenuto irrilevante)",
            "convincenti-ma-errate (forma persuasiva, contenuto falso)",
            "ambigue",
            "diverse famiglie di modelli (SLM e LLM)",
        ],
        "selection_method": (
            "Stratified random sample from pilot tasks, blind to model identity "
            "and to the other annotator's labels."
        ),
        "gate_output": (
            "scoring_status per ramo e complessivo (Gate 2); NON produce "
            "energy_chain_status, che resta il Gate 1 di P4.9."
        ),
        "seed": BOOTSTRAP_SEED,
    }


def calibration_sample_template() -> list[dict[str, Any]]:
    """Template del campione di calibrazione: 40 item da popolare e commitare.

    Ogni item registra le due annotazioni cieche, l'adjudication del disaccordo
    e la tipologia di risposta, non solo le due etichette.
    """
    items = []
    for i in range(40):
        items.append({
            "task_id": f"CAL_{i + 1:03d}",
            "category": "",
            "answer_type": "",
            "model_response": "",
            "expected": "",
            "response_typology": "",
            "annotations": {
                "annotator_1": "",
                "annotator_2": "",
            },
            "adjudicated": "",
        })
    return items