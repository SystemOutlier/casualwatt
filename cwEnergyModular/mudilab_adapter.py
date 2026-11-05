"""MUDILAB adapter for the common CasualWatt evaluator.

The adapter evaluates independent pipeline stages and exposes one end-to-end
verdict.  It never treats a correct number as sufficient when the label,
translation, or tool invocation is invalid.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from robust_evaluator import EvaluationResult, evaluate


_NUMBER_RE = re.compile(r"-?\d+(?:[.,]\d+)?(?:[eE][-+]?\d+)?")

# Marcatori letterali della decisione di coerenza, presi dalla frase che il tool
# della relatrice stampa, non derivati dall'ortografia del ground truth:
# `consegna/tools_corretto.py:448` "Evidences are compatible with a single ..." e
# `:453` "Evidences are NOT strongly compatible with a single ...".  Il marcatore
# positivo e' la forma completa `are compatible with` perche' `compatible` compare
# anche dentro la frase negativa.
_POSITIVO_DECISIONE = "are compatible with"
_NEGATIVO_DECISIONE = "not strongly compatible"
_DECISIONI_POSITIVE = ("compatible", "strongly_compatible")
_DECISIONI_NEGATIVE = ("non_compatibile", "not_strongly_compatible")

# Decimali con cui il tool della relatrice stampa il numero, ramo per ramo,
# misurati sul codice consegnato (tools_corretto.py:349 backward_reasoning,
# :380 e :384 intervention, :449 e :454 coherence con la FIX 12 che passa da due
# a quattro, e funtions_corretto.py:302 per i due estremi del controfattuale,
# chiamata da tools_corretto.py:366).  Non e' un'assunzione sulla forma della
# risposta: e' l'ultima cifra che il tool puo' aver scritto.
#
# La tolleranza del contratto deve essere meta' di quell'ordine, perche' il
# ground truth e' a piena precisione (expected_probability ha 10 decimali in
# MUDILAB_run/benchmark/benchmark.csv) e il numero che il modello trascrive e'
# l'arrotondamento del tool: la distanza legittima fra i due non puo' superare
# meta' dell'ultimo passo stampato.  Una tolleranza piu' larga accetta un numero
# con l'ultima cifra sbagliata; una piu' stretta punisce l'arrotondamento.  Il
# valore fisso di prima -- 5e-4, cioe' la meta'-ULP dei rami a 3 decimali -- era
# giusto su cond_prob e inter e dieci volte piu' largo del necessario su
# coherence e counterfactual, che stampano 4 decimali.
_DECIMALI_STAMPATI: Mapping[str, int] = {
    "cond_prob": 3,
    "inter": 3,
    "coherence": 4,
    "counterfactual": 4,
}

# Guardia sulla soglia: 0.5 * 10**-3 non e' rappresentabile esatto in binario,
# quindi un numero legittimamente a meta' del passo di arrotondamento puo'
# risultare di qualche unita' dell'ultimo bit sopra la meta'-ULP e venire
# rifiutato.  1e-12 sta sei ordini sotto la tolleranza piu' stretta che questo
# contratto usa: copre la rappresentazione, non un valore diverso.
_GUARDIA_RAPPRESENTAZIONE = 1e-12


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _tolleranza_assoluta(task_type: str) -> tuple[float, int, str]:
    """Meta'-ULP della stampa del tool per questo ramo, con la sua provenienza.

    Ritorna ``(tolleranza, decimali, provenienza)``.  La provenienza serve perche'
    il numero smette di essere una costante del valutatore e diventa una proprieta'
    misurata del tool: chi legge il contratto deve poter vedere quale stampa l'ha
    prodotto, e quale stampa ha *non* misurata quando il ramo non e' conosciuto.

    Un ramo fuori tavola non riceve una tolleranza inventata ne' una piu' stretta:
    prende la meta'-ULP del ramo piu' rozzo fra quelli osservati -- lo stesso
    valore che il contratto usava prima di questa derivazione -- e la nota lo
    dichiara.  Stringere la misura su un ramo mai letto sarebbe un cambio di
    metodo senza evidenza.
    """
    decimals = _DECIMALI_STAMPATI.get(task_type)
    if decimals is None:
        decimals = min(_DECIMALI_STAMPATI.values())
        provenienza = (
            f"branch {task_type!r} not measured in tools_corretto.py: coarsest "
            f"observed precision ({decimals} decimals) used, tolerance not derived "
            "from this branch's own print"
        )
    else:
        provenienza = (
            f"{decimals} decimals printed by cau_inference for branch {task_type!r}"
        )
    return 0.5 * 10.0 ** -decimals + _GUARDIA_RAPPRESENTAZIONE, decimals, provenienza


@dataclass(frozen=True)
class MudilabCase:
    task_id: str
    task_type: str
    expected_label: str
    expected_probability: Optional[float] = None
    expected_lower: Optional[float] = None
    expected_upper: Optional[float] = None
    expected_decision: Optional[str] = None
    target_variable: str = ""
    target_state: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)
    intervention: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MudilabEvaluation:
    task_id: str
    task_type: str
    label: EvaluationResult
    translation: EvaluationResult
    output: EvaluationResult
    tool_call_valid: bool
    tool_call_status: str
    end_to_end: str
    energy_j: Optional[float] = None
    duration_s: Optional[float] = None
    notes: tuple[str, ...] = ()
    tolerance_provenance: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "label": self.label.to_dict(),
            "translation": self.translation.to_dict(),
            "output": self.output.to_dict(),
            "tool_call_valid": self.tool_call_valid,
            "tool_call_status": self.tool_call_status,
            "end_to_end": self.end_to_end,
            "energy_j": self.energy_j,
            "duration_s": self.duration_s,
            "notes": list(self.notes),
            "tolerance_provenance": self.tolerance_provenance,
        }


def _num(text: str) -> list[float]:
    return [float(item.replace(",", ".")) for item in _NUMBER_RE.findall(text or "")]


def _nome_chiamata(call: Mapping[str, Any]) -> str:
    """The three field names the recorded shapes use for the tool."""
    for key in ("name", "tool", "step"):
        value = str(call.get(key, "")).strip()
        if value:
            return value
    return ""


def _prova_esecuzione(tool_calls: Any) -> tuple[str, list[str]]:
    """Execution status of ``cau_inference`` from the shapes the records use.

    The adapter used to accept one shape only -- a list of mappings carrying
    ``name``/``success`` -- and none of the three shapes the pipeline actually
    writes matches it.  Iterating a dict yields its keys, so ``isinstance(call,
    Mapping)`` was false for every entry, ``matching_calls`` stayed empty and
    every run came back ``missing``: the measurement dropped to zero correct
    not because the tool failed but because the record could not be read.
    The three accepted forms:

    * ``[{"step": "cau_inference", "text": ...}]`` -- the step appended by
      ``run_orchestrato.py:482-500``.  It is appended only after the call
      returned (``:468-480`` routes an exception to ``errore`` with no step),
      so a step with a non-empty text is a successful execution.
    * ``{"cau_inference": {"invocazioni": n, "eccezioni": m}}`` -- the counter
      dict written by ``MUDILAB_run/MUDILAB_correzioni/run_query.py:188-194``,
      where ``tool_ok`` is defined at ``:178`` and written at ``:185`` as exactly
      ``invocazioni >= 1 and eccezioni == 0``.
    * ``[{"name": "cau_inference", "success": true}]`` -- the declared schema,
      still read.

    Returns ``(status, notes)`` with status in
    ``success | failed | unverified | missing``.
    """
    notes: list[str] = []
    if not tool_calls:
        return "missing", ["no tool call recorded in the run"]

    def da_contatore(valore: Any) -> tuple[str, list[str]]:
        if isinstance(valore, Mapping):
            inv = valore.get("invocazioni", valore.get("invocation_count"))
            exc = valore.get("eccezioni", valore.get("invocation_exception_count"))
        else:
            inv, exc = valore, None
        if isinstance(exc, int) and exc > 0:
            return "failed", [f"cau_inference raised {exc} exception(s)"]
        if isinstance(inv, int) and inv <= 0:
            return "missing", ["cau_inference was never invoked"]
        if isinstance(inv, int) and inv >= 1 and exc == 0:
            return "success", []
        return "unverified", [
            f"cau_inference counter read (invocazioni={inv!r}, eccezioni={exc!r}); "
            "not enough to prove a successful call"
        ]

    if isinstance(tool_calls, Mapping):
        if "cau_inference" in tool_calls or "tool_ok" in tool_calls:
            if "cau_inference" in tool_calls:
                return da_contatore(tool_calls["cau_inference"])
            ok = tool_calls.get("tool_ok")
            if ok is True:
                return "success", []
            if ok is False:
                return "missing", ["tool_ok is false"]
        entries: list[Any] = [tool_calls]
    else:
        entries = list(tool_calls)

    chiamate = [call for call in entries
               if isinstance(call, Mapping) and _nome_chiamata(call) == "cau_inference"]
    if not chiamate:
        # A dict of counters keyed by tool name reaches here when the key is
        # not the tool itself; report missing rather than invent a status.
        return "missing", ["no cau_inference entry among the recorded calls"]

    for call in chiamate:
        if call.get("success") is False:
            return "failed", ["the recorded call reports success=False"]
        status = str(call.get("status", "")).strip().lower()
        if status in ("error", "failed", "failure", "exception"):
            return "failed", [f"the recorded call reports status={status}"]
        ecc = call.get("eccezioni", call.get("invocation_exception_count"))
        if isinstance(ecc, int) and ecc > 0:
            return "failed", [f"cau_inference raised {ecc} exception(s)"]
        if call.get("success") is True or status in ("success", "succeeded", "completed", "ok"):
            return "success", []
        # run_orchestrato.py appends the step only on the return path, so a
        # step that carries the tool's own answer text is an execution proof.
        if str(call.get("text", "") or "").strip():
            return "success", []
    return "unverified", [
        "cau_inference appears in the record without an outcome field or answer text"
    ]


_CHIAVI_ARGOMENTI = ("arguments", "args", "input", "inputs", "features", "params")


def _scarta_involucro(payload: Any) -> Any:
    """La query dentro gli argomenti registrati, nella firma che il tool riceve.

    `cau_inference(label, features, path, name, surname)`
    (``MUDILAB_run/consegna/tools_corretto.py:322-323``) prende la traduzione nel
    secondo argomento, come stringa JSON, e l'harness orchestrato registra la
    forma mandata: ``{"label": ..., "features": "{\\"input\\": ...}", "path": ...}``
    (``run_orchestrato.py:491-495``).  Confrontare quell'involucro con la
    traduzione in punteggi avrebbe dato ``mismatch`` fra due dizionari che
    descrivono la stessa query.  La traduzione reale ha la chiave ``input``, quindi
    un payload che ce l'ha gia' non viene scartato un secondo giro.
    """
    while isinstance(payload, Mapping) and "features" in payload and "input" not in payload:
        payload = payload["features"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            pass
    return payload


def _etichetta_del_ramo(value: Any) -> str:
    """L'etichetta del ramo come la intende il tool, non come e' scritta.

    `cau_inference` normalizza il refuso `conterfactual` in `counterfactual`
    (``tools_corretto.py:331-333``, la FIX 2, accettata per non rompere i prompt
    esistenti): confrontare le stringhe crude avrebbe chiamato ``mismatch`` una
    chiamata che il tool esegue sul ramo giusto.
    """
    etichetta = _text(value).lower()
    return "counterfactual" if etichetta == "conterfactual" else etichetta


def _argomenti_verificati(tool_calls: Any, translation: Any,
                          expected_label: str = "") -> tuple[str, str]:
    """Whether the call inputs are readable, and whether they are the scored ones.

    Execution proof alone is not argument proof: the review asked for the call
    arguments to be checked too.  Two of the three recorded shapes can now answer
    that, and one cannot:

    * the orchestrated harness passes the arguments to the tool itself and
      registers them beside the answer (``run_orchestrato.py:469`` and ``:491-495``),
      so its runs are decidable -- ``verified`` when the payload equals the scored
      translation, ``mismatch`` when it does not;
    * a recorded mapping that carries the inputs under another name is read as
      ``unreadable`` rather than guessed;
    * the counter dict of ``MUDILAB_run/MUDILAB_correzioni/run_query.py:188-194``
      reports ``invocazioni``/``eccezioni`` only: ``invocation_count`` is read at
      ``:178`` and ``:190`` and nothing in this repository writes it, so it belongs
      to the agent framework, which does not hand the call inputs back.  For those
      runs -- and for every run recorded before the harness started writing
      ``args`` -- the honest verdict stays ``not recorded``, and it is said in the
      notes instead of being passed off as a verified call.
    """
    raw: list[Mapping[str, Any]] = []
    if isinstance(tool_calls, Mapping):
        entry = tool_calls.get("cau_inference")
        raw = [entry] if isinstance(entry, Mapping) else [tool_calls]
    else:
        raw = [call for call in (tool_calls or []) if isinstance(call, Mapping)]

    registrato: Optional[tuple[Any, Any]] = None
    for call in raw:
        if _nome_chiamata(call) not in ("", "cau_inference"):
            continue
        for key in _CHIAVI_ARGOMENTI:
            if key in call:
                registrato = (call[key], _scarta_involucro(call[key]))
                break
        if registrato is not None:
            break

    if registrato is None:
        return ("not recorded",
                "call inputs are not recorded; execution proof does not cover the arguments")

    involucro, inviati = registrato
    if not isinstance(inviati, Mapping):
        return ("unreadable",
                f"call inputs recorded as {type(inviati).__name__}, not a mapping")

    if not isinstance(translation, Mapping):
        translation = _scarta_involucro(translation)
    if not isinstance(translation, Mapping):
        # Niente traduzione in punteggi = niente termine di confronto.  Dirlo
        # `mismatch` avrebbe attribuito al call un input diverso da una cosa che
        # non era stata registrata; la tappa della traduzione e' gia'
        # `indeterminate` per sua propria ragione.
        return ("unreadable",
                f"no scored translation to compare the recorded inputs with ({type(translation).__name__})")

    if inviati != translation:
        return ("mismatch",
                "call inputs differ from the scored translation: "
                f"{sorted(inviati)} vs {sorted(translation)}")

    # La query coincide.  Se l'involucro porta anche l'etichetta del ramo,
    # un'etichetta diversa da quella del case significa che il tool ha risposto a
    # un'altra domanda con la stessa query: il numero non e' di questa riga.
    if expected_label and isinstance(involucro, Mapping) and "label" in involucro:
        mandata = _etichetta_del_ramo(involucro["label"])
        if mandata and mandata != _etichetta_del_ramo(expected_label):
            return ("mismatch",
                    f"the recorded call asked label {mandata!r}, the case expects "
                    f"{_etichetta_del_ramo(expected_label)!r}: the number comes from "
                    "another branch of the tool")
    return "verified", "call inputs match the scored translation"


def _case_contract(case: MudilabCase) -> dict[str, Any]:
    """Contract of the case, with the tolerance derived from the tool's print.

    ``tolerance_provenance`` is not read by :mod:`robust_evaluator` -- unknown
    keys pass through :func:`robust_evaluator.validate_contract` untouched -- it
    is what makes the number in ``absolute_tolerance`` traceable: the evaluator
    puts that number in the diagnostics of every ``number_tolerance_match`` and
    ``interval_bounds_match`` verdict, so the derived tolerance of the branch is
    visible in the scored output instead of only in this source file.
    """
    tolerance, _, provenance = _tolleranza_assoluta(case.task_type)
    if case.task_type == "counterfactual":
        return {
            "answer_type": "interval", "lower": case.expected_lower,
            "upper": case.expected_upper, "absolute_tolerance": tolerance,
            "relative_tolerance": 0.0,
            "tolerance_provenance": provenance,
        }
    if case.task_type == "coherence":
        return {
            "answer_type": "number", "accepted_answers": [case.expected_probability],
            "absolute_tolerance": tolerance,
            "relative_tolerance": 0.0,
            "tolerance_provenance": provenance,
        }
    return {
        "answer_type": "number", "accepted_answers": [case.expected_probability],
        "absolute_tolerance": tolerance,
        "relative_tolerance": 0.0,
        "tolerance_provenance": provenance,
    }


def load_case(row: Mapping[str, Any]) -> MudilabCase:
    task_type = str(row.get("task_type", row.get("ramo", "")))
    default_labels = {
        "cond_prob": "backward_reasoning",
        "inter": "intervention",
        "coherence": "coherence",
        "counterfactual": "counterfactual",
        "influence": "influence",
    }
    def obj(name: str) -> dict[str, Any]:
        raw = row.get(name, "")
        if isinstance(raw, Mapping):
            return dict(raw)
        try:
            value = json.loads(str(raw or "{}"))
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}

    def opt_float(*names: str) -> Optional[float]:
        for name in names:
            value = row.get(name, "")
            if value not in (None, ""):
                try:
                    parsed = float(value)
                    if math.isfinite(parsed):
                        return parsed
                except (TypeError, ValueError, OverflowError):
                    pass
        return None

    return MudilabCase(
        task_id=str(row.get("task_id", "")),
        task_type=task_type,
        expected_label=str(row.get("etichetta_attesa")
                           or default_labels.get(task_type)
                           or row.get("expected_label", "")),
        expected_probability=opt_float("expected_probability"),
        expected_lower=opt_float("expected_lower_graph", "expected_lower"),
        expected_upper=opt_float("expected_upper_graph", "expected_upper"),
        expected_decision=str(row.get("expected_decision", "") or ""),
        target_variable=str(row.get("target_variable", "")),
        target_state=str(row.get("target_state", "")),
        evidence=obj("evidence_json"),
        intervention=obj("intervention_json"),
    )


def evaluate_translation(case: MudilabCase, translation: Any) -> EvaluationResult:
    expected_input = case.intervention if case.task_type in ("inter", "counterfactual") else case.evidence
    expected = {
        "input": expected_input,
        "output": {case.target_variable: case.target_state},
    }
    return evaluate(translation, {"answer_type": "structured", "expected": expected})


def evaluate_case(case: MudilabCase, *, label: str, translation: Any,
                  output: str, tool_calls: Any = None,
                  energy_j: Optional[float] = None,
                  duration_s: Optional[float] = None) -> MudilabEvaluation:
    """Score one MUDILAB run against the case contract.

    ``tool_calls`` accepts the shapes the pipeline really writes -- a list of
    call mappings, a list of recorded steps, or the counter dict of
    ``run_query.py:188-193`` -- see ``_prova_esecuzione``.
    """
    label_result = evaluate(label, {
        "answer_type": "label", "label": case.expected_label,
    })
    translation_result = evaluate_translation(case, translation)
    contract = _case_contract(case)
    output_result = evaluate(output, contract)
    tool_status, tool_notes = _prova_esecuzione(tool_calls)
    valid_call = tool_status == "success"
    arg_state, arg_note = _argomenti_verificati(
        tool_calls, translation, case.expected_label)
    stages = (label_result.verdict, translation_result.verdict, output_result.verdict)
    if any(item == "incorrect" for item in stages) or tool_status == "failed":
        end_to_end = "incorrect"
    elif any(item == "indeterminate" for item in stages) or tool_status in ("missing", "unverified"):
        end_to_end = "indeterminate"
    else:
        end_to_end = "correct"
    notes = []
    if case.task_type not in _DECIMALI_STAMPATI:
        # Il contratto ha preso la tolleranza del ramo piu' rozzo perche' questo
        # ramo non e' mai stato letto nella stampa del tool.  Va detto nella riga:
        # un numero che sembra derivato da una misura, su un ramo mai misurato, e'
        # un'assunzione travestita.
        notes.append(f"absolute tolerance declared, not derived: {contract['tolerance_provenance']}")
    if tool_status != "success":
        notes.append(f"cau_inference execution status: {tool_status}; "
                     f"{'; '.join(tool_notes) if tool_notes else 'outcome not stated'}")
    if arg_state != "verified":
        notes.append(f"cau_inference arguments: {arg_state} ({arg_note})")
    if case.task_type == "coherence" and case.expected_decision and _text(output):
        # Vocabolario reale del ground truth: benchmark/benchmark.csv contiene
        # `compatible` e `non_compatibile` (20 + 20 task id), non i due nomi enum
        # che questo blocco conosceva. Derivare il marcatore con replace("_", " ")
        # produceva l'italiano "non compatibile", che non puo' comparire
        # nell'inglese stampato dal tool: le 40 righe non_compatibile diventavano
        # tutte incorrect, 19 delle quali pubblicate come giuste.
        expected_decision = case.expected_decision.strip().lower()
        negativo = _NEGATIVO_DECISIONE in _text(output).lower()
        if expected_decision in _DECISIONI_NEGATIVE:
            decision_ok = negativo
        elif expected_decision in _DECISIONI_POSITIVE:
            # "compatible" e' anche dentro "not strongly compatible": il positivo
            # regge solo se il negativo non c'e', altrimenti la classe positiva
            # passa per buona quando la risposta dice l'opposto.
            decision_ok = (_POSITIVO_DECISIONE in _text(output).lower()) and not negativo
        else:
            decision_ok = None
            notes.append(
                f"coherence decision vocabulary not recognised: {expected_decision!r} "
                "(not in the ground truth mapping; marker not derived from spelling)"
            )
        if decision_ok is False:
            end_to_end = "incorrect"
            notes.append(
                "coherence qualitative decision mismatch (literal marker check; "
                "semantic equivalence not assessed)"
            )
        elif decision_ok is None and end_to_end == "correct":
            end_to_end = "indeterminate"
    return MudilabEvaluation(
        task_id=case.task_id, task_type=case.task_type,
        label=label_result, translation=translation_result,
        output=output_result, tool_call_valid=valid_call,
        tool_call_status=tool_status,
        end_to_end=end_to_end, energy_j=energy_j, duration_s=duration_s,
        notes=tuple(notes),
        tolerance_provenance=str(contract.get("tolerance_provenance", "")),
    )
