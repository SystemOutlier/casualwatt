# -*- coding: utf-8 -*-
"""P6.8 — Valutazione della qualita' non binaria su scala 0-5.

Estende `human_calibration_gate` con:

- ``krippendorff_alpha_ordinal`` e ``krippendorff_alpha_interval`` per
  accordo fra valutatori umani su scala ordinale 0-5 (qualita' percepita)
  e su scala a intervalli (punteggi numerici con distanza);
- ``weighted_cohen_kappa`` con pesi lineari e quadratici, per due
  valutatori su scala 0-5;
- ``QualityAssessmentGate`` che combina i punteggi umani (0-5) con i
  verdetti del giudice LLM, producendo ``quality_status`` per strata e
  complessivo, indipendente da ``scoring_status`` e da ``energy_chain_status``.

Tutte le metriche sono descrittive: nessun numero viene inventato, le
frazioni insufficienti restituiscono ``None`` con ragione dichiarata, e
il gate e' fail-closed (puo' solo abbassare uno stato, mai alzarlo).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from human_calibration_gate import CALIBRATION_THRESHOLD

# ---------------------------------------------------------------------------
# Costanti del pavimento di numerosita' per la qualita' (0-5)
# ---------------------------------------------------------------------------

MIN_QUALITY_PAIRABLE = 4  # minimo di coppie valutabili per alpha/kappa
MIN_QUALITY_ADMISSIBLE_FRACTION = 0.5  # frazione minima di record valutabili
QUALITY_SCALE = (0, 1, 2, 3, 4, 5)  # vocabolario chiuso della scala 0-5

# ---------------------------------------------------------------------------
# Helpers di base
# ---------------------------------------------------------------------------


def _is_valid_quality(value) -> bool:
    """True se il valore e' un punteggio intero nella scala 0-5."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and float(value).is_integer() and 0 <= value <= 5


def _quality_value(value) -> int | None:
    """Restituisce il punteggio intero 0-5, oppure None se non valido."""
    if _is_valid_quality(value):
        return int(value)
    return None


def _count_valid(values: Sequence) -> int:
    """Numero di valori validi nella scala 0-5."""
    return sum(1 for v in values if _is_valid_quality(v))


# ---------------------------------------------------------------------------
# Distanze per scala ordinale e a intervalli
# ---------------------------------------------------------------------------


def _ordinal_distance(a: int, b: int) -> int:
    """Distanza ordinale assoluta su scala 0-5 (distanza per gradini)."""
    return abs(a - b)


def _interval_distance(a: int, b: int) -> int:
    """Distanza a intervalli su scala 0-5: quadrato della distanza ordinale.

    Per Krippendorff a livello di intervalli la differenza di distanza e'
    quadratica: due punteggi distanti di 2 gradi pesano 4 volte di piu'
    di due distanti di 1 grado.
    """
    d = abs(a - b)
    return d * d


# ---------------------------------------------------------------------------
# Krippendorff's alpha (ordinale e a intervalli)
# ---------------------------------------------------------------------------


def krippendorff_alpha_ordinal(units: Sequence[Sequence[int | None]],
                               level: str = "ordinal") -> float | None:
    """Krippendorff's alpha per dati ordinali su scala 0-5.

    ``units`` e' una lista di valutazioni: ogni elemento e' la sequenza dei
    punteggi (o None per mancante) assegnati da diversi valutatori allo
    stesso item. Il livello e' ``ordinal``: la distanza e' la distanza
    per gradini (|a - b|).

    Restituisce None se non ci sono abbastanza coppie pairable per calcolare
    l'accordo atteso dal caso, o se la varianza osservata e' nulla (tutti i
    punteggi uguali -> alpha degenere, non definito come numero significativo).

    L'implementazione segue la definizione canonica:

        alpha = 1 - Do / De

    dove Do e' la discordanza osservata e De la discordanza attesa per
    indipendenza fra valutatori.
    """
    return _krippendorff_alpha_generic(
        units, distance=_ordinal_distance, level=level,
    )


def krippendorff_alpha_interval(units: Sequence[Sequence[int | None]],
                                level: str = "interval") -> float | None:
    """Krippendorff's alpha per dati a intervalli su scala 0-5.

    Come ``krippendorff_alpha_ordinal`` ma con distanza quadratica
    (distanza a intervalli): due punteggi distanti di 2 gradi pesano 4
    volte di piu' di due distanti di 1 grado. Adatto a punteggi di
    qualita' dove la distanza numerica ha significato (es. 0 vs 5 e'
    peggiore di 0 vs 1).
    """
    return _krippendorff_alpha_generic(
        units, distance=_interval_distance, level=level,
    )


def _krippendorff_alpha_generic(units: Sequence[Sequence[int | None]],
                                distance,
                                level: str) -> float | None:
    """Calcolo generico di Krippendorff's alpha con distanza customizzata.

    Algoritmo (Krippendorff 2004, capitolo su alpha):
    1. Costruire la tabella di coincidenza O: quante volte ogni coppia di
       valori appare su due valutatori diversi per lo stesso item.
    2. Do = somma su tutte le coppie (valore, valore') di O[v][v'] *
       distanza(valore, valore') / N_paia
    3. De = somma su tutte le coppie di e[v] * e[v'] * distanza(valore,
       valore') / N^2, dove e[v] e' la frequenza marginale del valore v.
    4. alpha = 1 - Do / De; se De == 0, alpha e' None (nessuna varianza).
    """
    # Raccogli tutti i valori validi e le loro frequenze
    valid_values = []
    for unit in units:
        for v in unit:
            if _is_valid_quality(v):
                valid_values.append(int(v))

    if len(valid_values) < 2:
        return None

    # Valori distinti ordinati (scala 0-5)
    distinct = sorted(set(valid_values))

    # Tabella di coincidenza O: conteggio di coppie ordinate (v1, v2) su
    # valutatori diversi dello stesso item.
    coincidence = {v: {w: 0 for w in distinct} for v in distinct}
    n_pairs = 0  # numero totale di coppie (v1, v2) su valutatori diversi

    for unit in units:
        vals = [int(v) for v in unit if _is_valid_quality(v)]
        m = len(vals)
        if m < 2:
            continue
        for i in range(m):
            for j in range(m):
                if i == j:
                    continue
                coincidence[vals[i]][vals[j]] += 1
                n_pairs += 1

    if n_pairs == 0:
        return None

    # Do: discordanza osservata (media delle distanze sulle coppie)
    do = 0.0
    for v1 in distinct:
        for v2 in distinct:
            do += coincidence[v1][v2] * distance(v1, v2)
    do = do / n_pairs

    # Frequenze marginali e
    n_values = len(valid_values)
    marginal = {v: valid_values.count(v) for v in distinct}

    # De: discordanza attesa per indipendenza
    de = 0.0
    for v1 in distinct:
        for v2 in distinct:
            de += (marginal[v1] / n_values) * (marginal[v2] / n_values) * distance(v1, v2)

    if de == 0.0:
        # Tutti i punteggi sono uguali: nessuna varianza, alpha non definito.
        return None

    alpha = 1.0 - do / de
    # Clamp numerico: piccoli errori di floating point possono portare
    # alpha leggermente fuori da [-1, 1].
    if alpha > 1.0:
        alpha = 1.0
    if alpha < -1.0:
        alpha = -1.0
    return alpha


# ---------------------------------------------------------------------------
# Cohen's kappa ponderato (lineare e quadratico)
# ---------------------------------------------------------------------------


def weighted_cohen_kappa(ratings_a: Sequence[int | None],
                         ratings_b: Sequence[int | None],
                         weight: str = "linear") -> float | None:
    """Cohen's kappa ponderato per due valutatori su scala 0-5.

    ``weight`` puo' essere ``"linear"`` (peso = |a - b| / 5) o
    ``"quadratic"`` (peso = ((a - b) / 5)^2). Il kappa ponderato e'

        kappa_w = 1 - (Do_w / De_w)

    dove Do_w e' la discordanza ponderata osservata e De_w quella attesa
    per indipendenza.

    Restituisce None se non ci sono abbastanza item sovrapposti (meno di 2)
    o se non c'è varianza (De_w == 0).
    """
    if weight not in ("linear", "quadratic"):
        raise ValueError(f"weight must be 'linear' or 'quadratic', got {weight!r}")

    if len(ratings_a) != len(ratings_b):
        raise ValueError("ratings_a e ratings_b devono avere la stessa lunghezza")

    # Filtra le coppie dove entrambi i valutatori hanno un punteggio valido
    pairs = [(int(a), int(b)) for a, b in zip(ratings_a, ratings_b)
             if _is_valid_quality(a) and _is_valid_quality(b)]

    n = len(pairs)
    if n < 2:
        return None

    distinct = sorted(set(v for p in pairs for v in p))

    # Matrice di confusione normalizzata: p[i][j] = P(valutatore A = i, B = j)
    confusion = {(i, j): 0 for i in distinct for j in distinct}
    for a, b in pairs:
        confusion[(a, b)] += 1

    # Pesi: w[i][j] = distanza ponderata fra i e j
    max_dist = 5.0  # scala 0-5
    if weight == "linear":
        weight_fn = lambda i, j: abs(i - j) / max_dist
    else:
        weight_fn = lambda i, j: ((i - j) / max_dist) ** 2

    # Do_w: discordanza ponderata osservata
    do_w = 0.0
    for i in distinct:
        for j in distinct:
            do_w += (confusion[(i, j)] / n) * weight_fn(i, j)

    # Frequenze marginali
    marginal_a = {i: sum(1 for a, _ in pairs if a == i) / n for i in distinct}
    marginal_b = {j: sum(1 for _, b in pairs if b == j) / n for j in distinct}

    # De_w: discordanza ponderata attesa per indipendenza
    de_w = 0.0
    for i in distinct:
        for j in distinct:
            de_w += marginal_a[i] * marginal_b[j] * weight_fn(i, j)

    if de_w == 0.0:
        return None

    kappa_w = 1.0 - do_w / de_w
    if kappa_w > 1.0:
        kappa_w = 1.0
    if kappa_w < -1.0:
        kappa_w = -1.0
    return kappa_w


# ---------------------------------------------------------------------------
# Risultati della verifica di qualita'
# ---------------------------------------------------------------------------


@dataclass
class QualityStratumResult:
    """Esito della verifica di qualita' per uno singolo strata di risposta."""

    stratum: str
    n_records: int = 0
    n_evaluable: int = 0  # record con punteggio umano valido 0-5
    n_human_pairable: int = 0  # coppie usabili per alpha/kappa
    alpha_ordinal: float | None = None
    alpha_interval: float | None = None
    kappa_linear: float | None = None
    kappa_quadratic: float | None = None
    mean_human_score: float | None = None
    mean_llm_judge_score: float | None = None
    passed: bool = False
    reason: str = ""
    failed_criteria: tuple[str, ...] = ()
    diagnostics: dict = field(default_factory=dict)

    @property
    def admissible_fraction(self) -> float | None:
        if self.n_records == 0:
            return None
        return self.n_evaluable / self.n_records


@dataclass
class QualityGateResult:
    """Esito complessivo del gate di valutazione della qualita."""

    quality_status: str = "not_validated"  # validated | partially_validated | not_validated | insufficient_data
    quality_status_per_stratum: dict[str, str] = field(default_factory=dict)
    strata: dict[str, QualityStratumResult] = field(default_factory=dict)
    overall_mean_human_score: float | None = None
    overall_mean_llm_judge_score: float | None = None
    n_strata_validated: int = 0
    n_strata_total: int = 0
    diagnostics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "quality_status": self.quality_status,
            "quality_status_per_stratum": dict(self.quality_status_per_stratum),
            "n_strata_validated": self.n_strata_validated,
            "n_strata_total": self.n_strata_total,
            "overall_mean_human_score": self.overall_mean_human_score,
            "overall_mean_llm_judge_score": self.overall_mean_llm_judge_score,
            "diagnostics": dict(self.diagnostics),
        }


# ---------------------------------------------------------------------------
# QualityAssessmentGate
# ---------------------------------------------------------------------------


class QualityAssessmentCriteria:
    """Criteri di accettazione per il gate di qualita non binaria.

    Attributi:
        min_alpha_ordinal: soglia minima per alpha ordinale (0-1), None se non registrato.
        min_alpha_interval: soglia minima per alpha a intervalli (0-1), None se non registrato.
        min_kappa_linear: soglia minima per kappa ponderato lineare (0-1), None se non registrato.
        min_kappa_quadratic: soglia minima per kappa ponderato quadratico (0-1), None se non registrato.
        min_mean_human_score: soglia minima per il punteggio umano medio (0-5), None se non registrato.
        min_admissible_fraction: frazione minima di record valutabili (0-1), None se non registrato.
    """

    def __init__(self,
                 min_alpha_ordinal: float | None = None,
                 min_alpha_interval: float | None = None,
                 min_kappa_linear: float | None = None,
                 min_kappa_quadratic: float | None = None,
                 min_mean_human_score: float | None = None,
                 min_admissible_fraction: float | None = None):
        # Validazione: se una soglia e' dichiarata, deve essere nel range valido
        for name, value in (
            ("min_alpha_ordinal", min_alpha_ordinal),
            ("min_alpha_interval", min_alpha_interval),
            ("min_kappa_linear", min_kappa_linear),
            ("min_kappa_quadratic", min_kappa_quadratic),
            ("min_mean_human_score", min_mean_human_score),
        ):
            if value is not None and not (0.0 <= value <= (5.0 if name == "min_mean_human_score" else 1.0)):
                raise ValueError(f"{name} deve essere compreso nell'intervallo valido, ricevuto {value!r}")
        if min_admissible_fraction is not None and not (0.0 < min_admissible_fraction <= 1.0):
            raise ValueError("min_admissible_fraction deve essere compreso fra 0 (escluso) e 1")
        self.min_alpha_ordinal = min_alpha_ordinal
        self.min_alpha_interval = min_alpha_interval
        self.min_kappa_linear = min_kappa_linear
        self.min_kappa_quadratic = min_kappa_quadratic
        self.min_mean_human_score = min_mean_human_score
        self.min_admissible_fraction = min_admissible_fraction


class QualityAssessmentGate:
    """Gate di valutazione della qualita non binaria (scala 0-5).

    Combina i punteggi umani (0-5) con i verdetti del giudice LLM per
    produrre ``quality_status`` per strata, indipendente da
    ``scoring_status`` e da ``energy_chain_status``.

    Il gate opera su record della forma::

        {
            "task_id": str,
            "answer_type": str,  # uno degli strati richiesti
            "human_score": int | None,  # punteggio umano 0-5 (opzionale)
            "llm_judge_score": float | None,  # punteggio del giudice LLM (opzionale)
            "rubric_scores": dict[str, int] | None,  # punteggi per sottocriterio
        }
    """

    def __init__(self, criteria: QualityAssessmentCriteria | None = None):
        self.criteria = criteria or QualityAssessmentCriteria()

    def evaluate_stratum(self,
                         records: list[dict],
                         stratum: str) -> QualityStratumResult:
        """Valuta la qualita per un singolo strata di risposta.

        Parametri:
            records: lista di record dello stesso strata.
            stratum: nome dello strata (es. "number", "short_text", "free_text").

        Restituisce un ``QualityStratumResult`` con alpha ordinale, alpha a
        intervalli, kappa ponderato lineare/quadratic, medie dei punteggi
        umani e del giudice LLM, e il verdetto di passed.
        """
        result = QualityStratumResult(stratum=stratum)
        result.n_records = len(records)

        # Punteggi umani validi (0-5)
        human_scores = []
        llm_scores = []
        human_pairs = []  # coppie (valutatore1, valutatore2) per items con due valutatori

        for record in records:
            hs = _quality_value(record.get("human_score"))
            if hs is None:
                hs = _quality_value(record.get("human_score_a"))
            if hs is not None:
                human_scores.append(hs)
            ls = record.get("llm_judge_score")
            if isinstance(ls, (int, float)) and not isinstance(ls, bool) and math.isfinite(ls):
                llm_scores.append(float(ls))

            # Se ci sono due valutatori umani (human_score_a, human_score_b)
            hsa = _quality_value(record.get("human_score_a"))
            hsb = _quality_value(record.get("human_score_b"))
            if hsa is not None and hsb is not None:
                human_pairs.append((hsa, hsb))

        result.n_evaluable = len(human_scores)
        result.n_human_pairable = len(human_pairs)

        # Medie
        if human_scores:
            result.mean_human_score = sum(human_scores) / len(human_scores)
        if llm_scores:
            result.mean_llm_judge_score = sum(llm_scores) / len(llm_scores)

        # Diagnostica di base
        result.diagnostics["n_human_scores_valid"] = len(human_scores)
        result.diagnostics["n_llm_scores_valid"] = len(llm_scores)
        result.diagnostics["n_invalid_human_scores"] = result.n_records - len(human_scores) - sum(
            1 for r in records if r.get("human_score") is None
        )

        # Krippendorff alpha: serve almeno 2 item con >=2 valutatori ciascuno
        # Costruisci units per krippendorff: ogni item con due valutatori umani
        units_for_alpha = [[a, b] for a, b in human_pairs] if human_pairs else []

        if len(units_for_alpha) >= 2:
            result.alpha_ordinal = krippendorff_alpha_ordinal(units_for_alpha, level="ordinal")
            result.alpha_interval = krippendorff_alpha_interval(units_for_alpha, level="interval")
        else:
            result.alpha_ordinal = None
            result.alpha_interval = None

        # Cohen kappa ponderato: serve almeno 2 coppie sovrapposte
        if len(human_pairs) >= 2:
            a_vals = [p[0] for p in human_pairs]
            b_vals = [p[1] for p in human_pairs]
            result.kappa_linear = weighted_cohen_kappa(a_vals, b_vals, weight="linear")
            result.kappa_quadratic = weighted_cohen_kappa(a_vals, b_vals, weight="quadratic")
        else:
            result.kappa_linear = None
            result.kappa_quadratic = None

        # Verdetto: fail-closed. Il ramo passa solo se tutte le soglie
        # dichiarate sono soddisfatte e il pavimento di numerosita' e' rispettato.
        failed = []

        # Pavimento di numerosita'
        if result.n_human_pairable < MIN_QUALITY_PAIRABLE:
            failed.append("insufficient_quality_numerosity")
            result.reason = (f"insufficient_data: n_human_pairable={result.n_human_pairable} "
                             f"< {MIN_QUALITY_PAIRABLE}")
        elif result.n_records > 0:
            frac = result.admissible_fraction
            if (self.criteria.min_admissible_fraction is not None
                    and (frac is None or frac < self.criteria.min_admissible_fraction)):
                failed.append("insufficient_admissible_fraction")
                result.reason = (f"insufficient_data: admissible_fraction={frac} "
                                 f"< {self.criteria.min_admissible_fraction}")

        # Soglie di accordo (solo se registrate)
        if (self.criteria.min_alpha_ordinal is not None
                and (result.alpha_ordinal is None or result.alpha_ordinal < self.criteria.min_alpha_ordinal)):
            failed.append("min_alpha_ordinal")
        if (self.criteria.min_alpha_interval is not None
                and (result.alpha_interval is None or result.alpha_interval < self.criteria.min_alpha_interval)):
            failed.append("min_alpha_interval")
        if (self.criteria.min_kappa_linear is not None
                and (result.kappa_linear is None or result.kappa_linear < self.criteria.min_kappa_linear)):
            failed.append("min_kappa_linear")
        if (self.criteria.min_kappa_quadratic is not None
                and (result.kappa_quadratic is None
                     or result.kappa_quadratic < self.criteria.min_kappa_quadratic)):
            failed.append("min_kappa_quadratic")
        if (self.criteria.min_mean_human_score is not None
                and (result.mean_human_score is None
                     or result.mean_human_score < self.criteria.min_mean_human_score)):
            failed.append("min_mean_human_score")

        result.failed_criteria = tuple(failed)
        result.passed = len(failed) == 0 and result.n_human_pairable >= MIN_QUALITY_PAIRABLE
        return result

    def evaluate(self,
                 records: list[dict],
                 required_strata: Sequence[str]) -> QualityGateResult:
        """Valuta la qualita su tutti gli strata richiesti.

        Parametri:
            records: lista di record (ognuno con ``answer_type``).
            required_strata: sequenza di nomi di strata obbligatori.

        Restituisce un ``QualityGateResult`` con lo stato per strata e
        complessivo. Se required_strata e' vuoto o None solleva ValueError
        (configurazione degenere, fail-closed).
        """
        if required_strata is None or len(required_strata) == 0:
            raise ValueError("required_strata non puo' essere vuoto o None: "
                             "una configurazione senza strati obbligatori non e' una configurazione")

        result = QualityGateResult()
        result.n_strata_total = len(required_strata)

        # Raggruppa i record per strata
        by_stratum: dict[str, list[dict]] = {s: [] for s in required_strata}
        out_of_stratum = 0
        for record in records:
            st = record.get("answer_type")
            if st in by_stratum:
                by_stratum[st].append(record)
            else:
                out_of_stratum += 1
        result.diagnostics["n_out_of_stratum"] = out_of_stratum

        for stratum in required_strata:
            stratum_result = self.evaluate_stratum(by_stratum[stratum], stratum)
            result.strata[stratum] = stratum_result
            result.quality_status_per_stratum[stratum] = (
                "validated" if stratum_result.passed else "not_validated"
            )
            if stratum_result.passed:
                result.n_strata_validated += 1

        # Punteggi medi complessivi
        all_human = [s.mean_human_score for s in result.strata.values()
                     if s.mean_human_score is not None]
        all_llm = [s.mean_llm_judge_score for s in result.strata.values()
                   if s.mean_llm_judge_score is not None]
        if all_human:
            result.overall_mean_human_score = sum(all_human) / len(all_human)
        if all_llm:
            result.overall_mean_llm_judge_score = sum(all_llm) / len(all_llm)

        # Verdetto complessivo
        if result.n_strata_validated == result.n_strata_total:
            result.quality_status = "validated"
        elif result.n_strata_validated > 0:
            result.quality_status = "partially_validated"
        else:
            # Nessuno strata validato: controlla se e' per dati insufficienti
            # o per criteri non soddisfatti.
            any_insufficient = any(
                s.reason.startswith("insufficient_data") for s in result.strata.values()
            )
            result.quality_status = "insufficient_data" if any_insufficient else "not_validated"

        result.diagnostics["n_records_total"] = len(records)
        result.diagnostics["n_strata_validated"] = result.n_strata_validated
        result.diagnostics["n_strata_total"] = result.n_strata_total
        return result


# ---------------------------------------------------------------------------
# Integrazione con lo schema di valutazione (evaluation_schema.py)
# ---------------------------------------------------------------------------


def extract_quality_records_from_schema(schema_rows: Iterable[dict]) -> list[dict]:
    """Estrae record di qualita da righe dello schema di valutazione.

    Cerca nei campi ``human_score``, ``llm_judge_score`` e ``rubric_scores``
    (definiti in ``evaluation_schema.py``: ``EVALUATION_RESULT_COLUMNS``).

    Ogni record restituito ha la forma::

        {
            "task_id": str,
            "answer_type": str,
            "human_score": int | None,
            "llm_judge_score": float | None,
            "rubric_scores": dict[str, int] | None,
        }

    I record senza ``task_id`` o senza ``answer_type`` vengono esclusi
    (il gate non puo' valutare identita' sconosciute).
    """
    records = []
    for row in schema_rows:
        task_id = row.get("task_id")
        answer_type = row.get("answer_type")
        if task_id is None or answer_type is None:
            continue

        human_score = row.get("human_score")
        if human_score is None:
            human_score = row.get("human_score_a")

        human_score_a = row.get("human_score_a")
        human_score_b = row.get("human_score_b")
        llm_judge_score = row.get("llm_judge_score")

        rubric_scores = None
        rubric_raw = row.get("rubric_scores")
        if isinstance(rubric_raw, dict):
            rubric_scores = {k: v for k, v in rubric_raw.items()
                             if _is_valid_quality(v)}

        records.append({
            "task_id": task_id,
            "answer_type": answer_type,
            "human_score": human_score,
            "human_score_a": human_score_a,
            "human_score_b": human_score_b,
            "llm_judge_score": llm_judge_score,
            "rubric_scores": rubric_scores,
        })
    return records


def quality_protocol_template() -> dict:
    """Template di preregistrazione per il gate di qualita non binaria.

    Restituisce un dizionario che dichiara, prima di vedere i dati:
    - il livello di misura (ordinal / interval),
    - i criteri di accettazione come campi da registrare (None finche'
      non registrati),
    - il campione indipendente di valutazione umana,
    - la rappresentativita' delle tipologie di risposta.
    """
    return {
        "measurement_level": "ordinal",  # 0-5 e' una scala ordinale; interval opzionale
        "quality_scale": list(QUALITY_SCALE),
        "verifica_umana": {
            "krippendorff_alpha_ordinal": None,
            "krippendorff_alpha_interval": None,
            "cohen_kappa_lineare": None,
            "cohen_kappa_quadratico": None,
            "min_pairable_items": MIN_QUALITY_PAIRABLE,
            "min_admissible_fraction": MIN_QUALITY_ADMISSIBLE_FRACTION,
        },
        "giudice_llm": {
            "mean_llm_judge_score": None,
        },
        "criteri_di_accettazione": {
            "min_alpha_ordinal": None,
            "min_alpha_interval": None,
            "min_kappa_lineare": None,
            "min_kappa_quadratico": None,
            "min_mean_human_score": None,
            "min_admissible_fraction": None,
        },
        "campione_indipendente": True,
        "tipologie_di_risposta": ["number", "short_text", "free_text", "interval"],
        "pilot_declaration": (
            "Il gate di qualita non binaria valuta l'accordo fra valutatori "
            "umani su scala 0-5 (Krippendorff alpha ordinale e a intervalli, "
            "Cohen kappa ponderato lineare e quadratico) ed e' indipendente "
            "dallo scoring binario e dalla catena di misura energetica."
        ),
    }


__all__ = [
    "QUALITY_SCALE",
    "MIN_QUALITY_PAIRABLE",
    "MIN_QUALITY_ADMISSIBLE_FRACTION",
    "krippendorff_alpha_ordinal",
    "krippendorff_alpha_interval",
    "weighted_cohen_kappa",
    "QualityStratumResult",
    "QualityGateResult",
    "QualityAssessmentCriteria",
    "QualityAssessmentGate",
    "extract_quality_records_from_schema",
    "quality_protocol_template",
]
