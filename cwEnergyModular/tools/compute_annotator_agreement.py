#!/usr/bin/env python3
"""
compute_annotator_agreement.py — produttore dei due artefatti preregistrati
della calibrazione del giudice, delegando il calcolo al gate.

Perche' esiste. La preregistrazione (``human_calibration_protocol.json``,
sezione ``output_artifacts``) dichiara due report --
``human_calibration_agreement_report.json`` (Verifica A: affidabilita' umana) e
``human_calibration_judge_comparison.json`` (Verifica B: validita' del giudice)
-- e un unico produttore delle metriche: ``human_calibration_gate.py``. Questo
tool non implementa una seconda metrica: legge i due JSONL in schema canonico,
invoca ``run_scoring_validation_gate`` e ne serializza l'esito. La versione
precedente di questo file calcolava invece Krippendorff alpha su una scala
ordinale che la rubrica non dichiara, usava Cohen kappa come soglia di gate,
mappava in silenzio uno schema diverso (``item_id``/``stratum``/``verdict``
maiuscolo), sovrascriveva gli item duplicati perche' li accumulava in un dict,
perdeva senza contare gli item annotati da un solo annotatore e lasciava il
confronto con il giudice come stub. Con ``krippendorff`` non installato la sua
metrica primaria era comunque sempre ``None``.

Che cosa fa:

- legge la preregistrazione (strati, soglia di alpha, criteri di accettazione,
  seed e numero di ricampioni del bootstrap) e passa al gate ESATTAMENTE quel
  che il file dichiara: nessuna soglia viene inventata qui, e una voce non
  prevista o non numerica e' un errore nominato, non un valore taciuto;
- senza preregistrazione i criteri non sono registrati e il gate e' fail-closed
  (``criteria_not_registered``): il tool non promuove e non sostituisce soglie
  proprie;
- rifiuta -- per delega al loader del gate -- un record senza ``task_id``, un
  ``task_id`` duplicato (anche per soli spazi iniziali/finali) e una
  sovrapposizione fra i due campioni: l'errore nomina il colpevole e nessun
  report viene scritto;
- distingue il campione tecnico dalle annotazioni scientifiche con una
  dichiarazione dell'operatore (``--sample-status``), riportata verbatim nei
  due report: il tool non certifica mai la validita' scientifica del campione
  e non trasforma un fixture in un campione umano;
- allega a entrambi i report il digest SHA-256 dei due file in ingresso, la
  configurazione effettivamente usata (strati, soglia, seed, ricampioni,
  criteri, pavimenti preregistrati) e lo stato del gate per ramo: il report e'
  ricostruibile senza riaprire i dati;
- il codice d'uscita segue lo stato complessivo del gate: 0 solo se
  ``scoring_status == "validated"`` (tutti gli strati obbligatori promossi),
  1 altrimenti -- ``partially_validated`` non e' 0, perche' il gate nel
  complesso non e' passato.

Che cosa NON fa: non valida il metodo (la revisione della specifica distingue
conformita' dell'implementazione, validita' operativa e validita' scientifica
su dati reali: l'ultima richiede annotazioni umane vere), non converte lo
schema del campione precedente e non scrive nulla fuori da ``--out-dir``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from human_calibration_gate import (  # noqa: E402
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CALIBRATION_THRESHOLD,
    MIN_ADMISSIBLE_FRACTION,
    MIN_DECIDED_ITEMS,
    MIN_PAIRABLE_ITEMS,
    REQUIRED_STRATA,
    JudgeAcceptanceCriteria,
    run_scoring_validation_gate,
)

PROTOCOL_NAME = "human_calibration_protocol.json"
AGREEMENT_REPORT = "human_calibration_agreement_report.json"
JUDGE_REPORT = "human_calibration_judge_comparison.json"

CRITERIA_FIELDS = ("min_precision_correct", "min_recall_correct",
                   "max_fp_rate", "min_accuracy", "min_coverage")

VALIDITY_NOTE = (
    "Il tool esegue il gate di validazione dello scoring "
    "(human_calibration_gate.py::run_scoring_validation_gate) e ne riporta "
    "l'esito: non calcola una metrica propria e non certifica la validita' "
    "scientifica del campione. sample_status e' la dichiarazione "
    "dell'operatore sulla provenienza dei record -- campione tecnico o "
    "fixture vs annotazioni umane indipendenti e cieche -- non una "
    "determinazione del tool. Il token 'validated' certifica la sola "
    "coerenza fra preregistrazione e dati; la validita' scientifica del "
    "metodo resta una proprieta' distinta, da dimostrare su annotazioni "
    "reali."
)


def _digest(path: Path) -> str:
    """SHA-256 esadecimale del file, per rendere il report ricostruibile."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _numero(valore: Any, nome: str, minimo: Optional[float] = None) -> float:
    """Voce numerica della preregistrazione: tipizzata e nominata se errata.

    Il bool e' escluso perche' in Python e' un sottotipo di int: una soglia
    preregistrata a ``True`` sarebbe 1 letto come numero, non una
    dichiarazione.
    """
    if isinstance(valore, bool) or not isinstance(valore, (int, float)):
        raise ValueError(
            f"preregistrazione: '{nome}' deve essere un numero, trovato "
            f"{valore!r}")
    if minimo is not None and valore < minimo:
        raise ValueError(
            f"preregistrazione: '{nome}' deve essere >= {minimo}, trovato "
            f"{valore}")
    return valore


def _intero(valore: Any, nome: str, minimo: int) -> int:
    if isinstance(valore, bool) or not isinstance(valore, int):
        raise ValueError(
            f"preregistrazione: '{nome}' deve essere un intero, trovato "
            f"{valore!r}")
    if valore < minimo:
        raise ValueError(
            f"preregistrazione: '{nome}' deve essere >= {minimo}, trovato "
            f"{valore}")
    return valore


def _criteri(protocollo: dict[str, Any]) -> JudgeAcceptanceCriteria:
    """Criteri di accettazione dalla preregistrazione, senza inventarli.

    Assenti o parzialmente nulli restano non registrati: il gate e'
    fail-closed e il tool non riempie i buchi con soglie proprie. Una voce
    non numerica o una chiave non prevista sono errori nominati -- una
    soglia silenziosamente ignorata sarebbe una configurazione diversa da
    quella preregistrata, scoperta dopo i dati.
    """
    verifica_b = protocollo.get("verifica_b")
    criteri = verifica_b.get("acceptance_criteria") if isinstance(
        verifica_b, dict) else None
    if criteri is None:
        return JudgeAcceptanceCriteria()
    if not isinstance(criteri, dict):
        raise ValueError(
            "preregistrazione: 'verifica_b.acceptance_criteria' deve essere "
            f"un oggetto, trovato {type(criteri).__name__}")
    sconosciute = sorted(set(criteri) - set(CRITERIA_FIELDS))
    if sconosciute:
        raise ValueError(
            "preregistrazione: 'verifica_b.acceptance_criteria' contiene "
            f"chiavi non previste {sconosciute}: i criteri ammessi sono "
            f"{list(CRITERIA_FIELDS)}")
    valori: dict[str, float] = {}
    for nome in CRITERIA_FIELDS:
        if criteri.get(nome) is not None:
            valori[nome] = _numero(
                criteri[nome], f"verifica_b.acceptance_criteria.{nome}")
    return JudgeAcceptanceCriteria(**valori)


def _strati(protocollo: dict[str, Any]) -> tuple[str, ...]:
    """Strati obbligatori dalla preregistrazione.

    Il protocollo tracciato li dichiara come oggetti con ``name`` (con
    descrizione e numerosita' target); un elenco di stringhe e' altrettanto
    accettato. Un elenco assente o vuoto e' rifiutato qui, come dal gate:
    senza strati obbligatori il verdetto complessivo sarebbe ``validated``
    per costruzione, contando zero evidenze come successo.
    """
    strata = protocollo.get("strata")
    if strata is None:
        return tuple(REQUIRED_STRATA)
    if not isinstance(strata, list) or not strata:
        raise ValueError(
            "preregistrazione: 'strata' deve essere un elenco non vuoto di "
            "nomi (o di oggetti con 'name')")
    nomi: list[str] = []
    for voce in strata:
        if isinstance(voce, str) and voce.strip():
            nomi.append(voce)
        elif (isinstance(voce, dict) and isinstance(voce.get("name"), str)
                and voce["name"].strip()):
            nomi.append(voce["name"])
        else:
            raise ValueError(
                f"preregistrazione: voce di 'strata' non utilizzabile come "
                f"strato: {voce!r}")
    return tuple(nomi)


def _soglia_e_bootstrap(
        protocollo: dict[str, Any]) -> tuple[float, int, int]:
    """Soglia di alpha, seed e numero di ricampioni, come preregistrati.

    Dove la preregistrazione non li dichiara valgono le costanti del gate --
    che sono esse stesse preregistrate -- e il report dice quali valori sono
    stati usati, perche' un bootstrap con seed diverso non e' riproducibile.
    """
    verifica_a = protocollo.get("verifica_a")
    verifica_a = verifica_a if isinstance(verifica_a, dict) else {}
    soglia = verifica_a.get("threshold_alpha")
    if soglia is None:
        soglia = CALIBRATION_THRESHOLD
    else:
        soglia = _numero(soglia, "verifica_a.threshold_alpha")
    seed = verifica_a.get("bootstrap_seed")
    if seed is None:
        seed = BOOTSTRAP_SEED
    else:
        seed = _intero(seed, "verifica_a.bootstrap_seed", minimo=0)
    resamples = verifica_a.get("bootstrap_resamples")
    if resamples is None:
        resamples = BOOTSTRAP_RESAMPLES
    else:
        resamples = _intero(resamples, "verifica_a.bootstrap_resamples",
                            minimo=1)
    return float(soglia), int(seed), int(resamples)


def _carica_preregistrazione(
        path: Optional[Path]) -> dict[str, Any]:
    """Legge la preregistrazione; assente significa criteri non registrati.

    Un file illeggibile o non conforme e' un errore nominato, non un
    silenzioso fail-closed: la configurazione va corretta, non indovinata.
    """
    if path is None:
        return {
            "source": None,
            "criteria": JudgeAcceptanceCriteria(),
            "required_strata": tuple(REQUIRED_STRATA),
            "threshold_alpha": CALIBRATION_THRESHOLD,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        }
    path = Path(path)
    try:
        protocollo = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(
            f"preregistrazione: file non leggibile come JSON ({path}): {e}")
    if not isinstance(protocollo, dict):
        raise ValueError(
            f"preregistrazione: {path} non e' un oggetto JSON")
    soglia, seed, resamples = _soglia_e_bootstrap(protocollo)
    return {
        "source": str(path),
        "criteria": _criteri(protocollo),
        "required_strata": _strati(protocollo),
        "threshold_alpha": soglia,
        "bootstrap_seed": seed,
        "bootstrap_resamples": resamples,
    }


def _configurazione_usata(prereg: dict[str, Any]) -> dict[str, Any]:
    """Dichiarazione della configurazione con cui il gate e' stato eseguito.

    I pavimenti non sono parametri del tool: sono le costanti del gate,
    riportate perche' il report dica quali pavimenti preregistrati
    vigevano -- un verdetto cambia significato se il pavimento si sposta.
    """
    criteri = prereg["criteria"]
    return {
        "source": prereg["source"],
        "criteria_registered": criteri.registered(),
        "criteria": {nome: getattr(criteri, nome) for nome in CRITERIA_FIELDS},
        "required_strata": list(prereg["required_strata"]),
        "threshold_alpha": prereg["threshold_alpha"],
        "bootstrap_seed": prereg["bootstrap_seed"],
        "bootstrap_resamples": prereg["bootstrap_resamples"],
        "preregistered_floors": {
            "min_pairable_items": MIN_PAIRABLE_ITEMS,
            "min_decided_items": MIN_DECIDED_ITEMS,
            "min_admissible_fraction": MIN_ADMISSIBLE_FRACTION,
        },
    }


def _json_safe(valore: Any) -> Any:
    """Conversione ricorsiva per la serializzazione JSON.

    ``Counter`` non passa da ``dataclasses.asdict``: asdict lo ricostruisce
    con ``type(obj)((k, v) ...)``, e il costruttore di Counter tratta
    l'argomento come un iterabile di elementi -- una coppia ``('correct', 12)``
    diventa una chiave tupla invece di una voce. Qui il Counter ridiventa il
    dict che e', con le stesse chiavi; un contatore lasciato corrotto
    sarebbe un report illeggibile, non un errore rumoroso.
    """
    if isinstance(valore, Counter):
        return {k: _json_safe(v) for k, v in valore.items()}
    if isinstance(valore, dict):
        return {k: _json_safe(v) for k, v in valore.items()}
    if isinstance(valore, (list, tuple)):
        return [_json_safe(v) for v in valore]
    return valore


def _riga(obj: Any) -> dict[str, Any]:
    """Dataclass del gate in dict JSON-safe, campo per campo."""
    return {f.name: _json_safe(getattr(obj, f.name)) for f in fields(obj)}


def _report_comune(risultato, digests: dict[str, str],
                   sample_status: str, prereg: dict[str, Any]) -> dict:
    return {
        "protocol": PROTOCOL_NAME,
        "sample_status": sample_status,
        "input_digests": digests,
        "validity_note": VALIDITY_NOTE,
        "n_calibration_items": risultato.n_calibration_items,
        "n_validation_items": risultato.n_validation_items,
        "preregistration_used": _configurazione_usata(prereg),
        "scoring_status": risultato.scoring_status,
        "scoring_status_per_stratum": dict(risultato.scoring_status_per_stratum),
        "diagnostics": dict(risultato.diagnostics),
        "admissible_fractions": dict(risultato.admissible_fractions),
    }


def _scrivi(report: dict, directory: Path, nome: str) -> Path:
    percorso = directory / nome
    percorso.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return percorso


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Report preregistrati di calibrazione del giudice "
                    "(Verifica A e Verifica B), delega a human_calibration_gate")
    parser.add_argument("--calibration", required=True, type=Path,
                        help="JSONL del campione di calibrazione (schema canonico)")
    parser.add_argument("--validation", required=True, type=Path,
                        help="JSONL del campione di validazione, indipendente")
    parser.add_argument("--preregistration", type=Path, default=None,
                        help="protocollo preregistrato JSON (strati, soglia, criteri)")
    parser.add_argument("--sample-status", default="not_declared",
                        help="dichiarazione dell'operatore sulla provenienza del campione")
    parser.add_argument("--out-dir", type=Path, default=Path("."),
                        help="directory dei due report (default: corrente)")
    args = parser.parse_args(argv)

    prereg = _carica_preregistrazione(args.preregistration)

    # Il loader del gate rifiuta -- con ValueError che nomina record e riga --
    # un task_id assente, un task_id duplicato (anche per soli spazi) e una
    # sovrapposizione fra i campioni. L'errore risale prima di qualsiasi
    # scrittura: nessun report esiste a meta' di un rifiuto.
    risultato = run_scoring_validation_gate(
        args.calibration, args.validation, prereg["criteria"],
        threshold=prereg["threshold_alpha"],
        required_strata=prereg["required_strata"],
        seed=prereg["bootstrap_seed"], resamples=prereg["bootstrap_resamples"])

    digests = {"calibration": _digest(args.calibration),
               "validation": _digest(args.validation)}
    comune = _report_comune(risultato, digests, args.sample_status, prereg)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scritto_a = _scrivi({**comune, "verifica_a": {
        a.stratum: _riga(a) for a in risultato.agreement}}, out_dir,
        AGREEMENT_REPORT)
    scritto_b = _scrivi({**comune, "verifica_b": {
        v.stratum: _riga(v) for v in risultato.validity},
        "reference_stats": dict(risultato.reference_stats),
        "notes": risultato.notes}, out_dir, JUDGE_REPORT)
    print(f"Report scritti: {scritto_a}")
    print(f"Report scritti: {scritto_b}")
    print(f"scoring_status: {risultato.scoring_status} "
          f"({json.dumps(risultato.scoring_status_per_stratum, ensure_ascii=False)})")
    return 0 if risultato.scoring_status == "validated" else 1


if __name__ == "__main__":
    sys.exit(main())
