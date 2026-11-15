#!/usr/bin/env python3
"""
calibration_gate_summary.py — riepilogo dei tre stati (Opzione A, 2026-11-12).

Perche' esiste. La decisione del 2026-11-12 (Opzione A, architettura separata
sul modello P4.4) chiede UNICO artefatto che riepiloghi tre stati tenuti
distinti, invece di fonderli in un solo token:

- Gate 1 ``energy_chain_status`` (P4.9): la catena energetica. Si calcola sui
  dati della campagna con ``validation_chain.chain_status`` e qui viene solo
  LETTA da un artefatto della campagna, con il suo digest. NON e' un output
  della calibrazione dello scoring e non dipende da essa: questo tool non la
  deriva, non la stima e non la promuove;
- Gate 2 ``scoring_status`` (P6.7): la validazione dello scoring, prodotta da
  ``human_calibration_gate.run_scoring_validation_gate`` sui campioni dichiarati;
- Gate 3 ``integrated_status``: ``integrate_experiment_status`` applicata ai
  due stati, senza cancellare l'informazione originaria.

L'artefatto serve alla verifica PRE-CAMPAGNA: dice quali stati esistono, quali
mancano e perche', quali flag arrivano al valutatore, e cosa blocca una
campagna difendibile. Pre-campagna nessuno stato viene inventato: i gate che
non hanno ancora prodotto un token restano ``null`` con la ragione, e
l'integrato resta ``null`` -- non ``energy_not_validated``, che e' il verdetto
di una catena valutata e trovata non valida, non di una catena non ancora
calcolata.

Che cosa fa:

- delega il calcolo: Gate 2 a ``run_scoring_validation_gate`` (unico produttore
  delle metriche, seme e soglia fissati), la configurazione preregistrata a
  ``compute_annotator_agreement`` (unico lettore del protocollo). Nessuna
  metrica viene ricalcolata qui: alpha, kappa, matrici di confusione e
  intervalli restano nei due report del tool dedicato;
- legge il token energetico da un artefatto JSON con ``chain_status``,
  verificandolo contro il vocabolario chiuso ``validation_chain.STATUS_LABELS``:
  un token fuori vocabolario verrebbe letto da ``integrate_experiment_status``
  come «non validato», e un refuso diventerebbe una catena fallita;
- produce i flag ``judge_gated_*`` con ``judge_gated_flags`` quando il gate ha
  girato; senza gate restano ``null`` con la ragione, e il valutatore
  (``evaluator.py``, parametro ``judge_gated``) tiene il suo default;
- elenca la verifica pre-campagna (campioni, criteri preregistrati,
  indipendenza, dato energetico) con tre soli esiti -- ``present``,
  ``missing``, ``not_applicable`` -- e la ragione di ciascuno;
- allega digest SHA-256 degli input, testa di git (o la ragione per cui non e`
  leggibile) e la provenienza del campione dichiarata dall'operatore, sul
  modello P4.4: l'artefatto e' ricostruibile senza riaprire i dati;
- rifiuta -- senza scrivere nulla -- una configurazione a meta' (un campione
  solo), una sovrapposizione fra campioni (delega al loader del gate), una
  preregistrazione malformata e un token energetico fuori vocabolario.

Che cosa NON fa: non calcola la catena energetica (nessun dato di campagna
entra in Gate 1 da qui), non promuove alcun stato, non scrive un artefatto a
meta' di un rifiuto (scrittura atomica in coda), non certifica la validita'
scientifica del campione ne' della misura.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
for _p in (str(ROOT), str(TOOLS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import compute_annotator_agreement as caa  # noqa: E402
from human_calibration_gate import (  # noqa: E402
    integrate_experiment_status,
    judge_gated_flags,
    run_scoring_validation_gate,
)
from validation_chain import STATUS_LABELS  # noqa: E402

ARTEFATTO = "calibration_gate_summary.json"

ENERGIA_ASSENTE = (
    "la catena energetica P4.9 (Gate 1) si calcola sui dati della campagna "
    "con validation_chain.chain_status: nessun artefatto e' stato dichiarato, "
    "quindi lo stato non e' calcolato in questo riepilogo -- assente, non "
    "'non valido'."
)

SCORING_ASSENTE = (
    "il gate di scoring P6.7 (Gate 2) non e' stato eseguito: nessun campione "
    "di calibrazione/validazione e' stato dichiarato."
)

FLAGS_ASSENTE = (
    "i flag judge_gated_* sono prodotti da human_calibration_gate."
    "judge_gated_flags quando il gate ha girato; senza gate non sono "
    "determinabili e non vengono inventati ne' in un verso ne' nell'altro -- "
    "il valutatore (evaluator.py, parametro judge_gated) tiene il suo default."
)

VALIDITY_NOTE = (
    "Il tool riepiloga gli stati prodotti da altri moduli "
    "(human_calibration_gate per Gate 2, validation_chain per Gate 1) e non "
    "calcola una metrica propria: non certifica la validita' scientifica del "
    "campione ne' della misura. sample_status e' la dichiarazione "
    "dell'operatore sulla provenienza dei record, non una determinazione del "
    "tool. Un token 'validated' qui certifica la sola coerenza fra "
    "preregistrazione e dati."
)


def _digest(path: Path) -> str:
    """SHA-256 esadecimale del file, per rendere il riepilogo ricostruibile."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_testa() -> tuple[str, str]:
    """(sha di HEAD, ragione): la testa del repository nel momento del riepilogo.

    ``git`` non eseguibile dal processo di pytest e' una guardia non
    decidibile, non un fallimento: la ragione vera viene dichiarata accanto al
    campo, che non passa in silenzio.
    """
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(ROOT),
                             capture_output=True, text=True, timeout=20)
    except Exception as exc:  # noqa: BLE001 - non decidibile, non "falso"
        return "", f"git non eseguibile: {type(exc).__name__}: {exc}"
    if out.returncode != 0:
        stderr = (out.stderr or "").strip()
        return "", stderr or f"git esce con codice {out.returncode}"
    return out.stdout.strip(), ""


def _stato_energetico(
        path: Optional[Path]) -> tuple[Optional[str], str, Optional[Path]]:
    """Token P4.9 letto da un artefatto della campagna: (token, ragione, file).

    Il token deve appartenere al vocabolario chiuso ``STATUS_LABELS``: una
    stringa arbitraria verrebbe letta da ``integrate_experiment_status`` come
    «non validato», e un refuso diventerebbe una catena fallita. Senza
    artefatto il token e' ``None``: la catena non e' ancora calcolata.
    """
    if path is None:
        return None, ENERGIA_ASSENTE, None
    try:
        dati = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(
            f"catena energetica: file non leggibile come JSON ({path}): {e}")
    if not isinstance(dati, dict) or "chain_status" not in dati:
        raise ValueError(
            f"catena energetica: {path} non dichiara 'chain_status'. "
            "L'artefatto atteso e' quello della campagna, dove "
            "validation_chain.chain_status scrive il token.")
    token = dati["chain_status"]
    if not isinstance(token, str) or not token.strip():
        raise ValueError(
            "catena energetica: 'chain_status' deve essere un token non vuoto, "
            f"trovato {token!r}")
    token = token.strip()
    if token not in STATUS_LABELS:
        raise ValueError(
            f"catena energetica: token {token!r} fuori dal vocabolario chiuso "
            f"di P4.9 {list(STATUS_LABELS)}. Un token fuori vocabolario non "
            "distinguerebbe una catena fallita da un refuso.")
    return (token,
            f"letto dall'artefatto {Path(path).name} (digest in input_digests)",
            path)


def _verifiche(*, entrambi_campioni: bool, criteri,
               energia: Optional[Path]) -> list[dict[str, Any]]:
    """Verifica pre-campagna: tre esiti, mai un giudizio inventato.

    ``missing`` dice cosa blocca una campagna difendibile; ``not_applicable``
    dice cosa non e' decidibile qui -- e in particolare che il dato energetico
    NON e' un input di questo gate, quindi la sua assenza non e' un difetto
    dello scoring.
    """
    campioni = "present" if entrambi_campioni else "missing"
    motivo_campioni = (
        "entrambi i campioni dichiarati: il gate di scoring e' eseguibile"
        if entrambi_campioni else
        "campioni non dichiarati: il gate di scoring (Gate 2) non e' "
        "eseguibile -- servono calibrazione e validazione indipendente")
    return [
        {"check": "calibration_sample", "status": campioni,
         "reason": motivo_campioni},
        {"check": "validation_sample", "status": campioni,
         "reason": motivo_campioni},
        {"check": "judge_criteria_registered",
         "status": "present" if criteri.registered() else "missing",
         "reason": (
             "criteri di accettazione preregistrati: il gate puo' giudicare "
             "il giudice"
             if criteri.registered() else
             "criteri di accettazione non preregistrati: il gate e' "
             "fail-closed (criteria_not_registered) e nessun ramo viene "
             "promosso -- i cinque criteri vanno fissati prima dei dati")},
        {"check": "sample_independence",
         "status": "present" if entrambi_campioni else "not_applicable",
         "reason": (
             "il loader del gate ha verificato l'indipendenza per task_id: "
             "una sovrapposizione fra i campioni sarebbe un rifiuto, non "
             "un'avvertenza"
             if entrambi_campioni else
             "l'indipendenza si verifica sui dati: senza entrambi i campioni "
             "non e' decidibile")},
        {"check": "energy_chain_data",
         "status": "present" if energia is not None else "not_applicable",
         "reason": (
             "artefatto della campagna dichiarato (digest in input_digests): "
             "il token P4.9 entra nel riepilogo come input, non come output"
             if energia is not None else
             "la catena energetica P4.9 si calcola sui dati della campagna "
             "(validation_chain.chain_status): non e' un input di questo "
             "gate e la sua assenza qui non e' un difetto dello scoring")},
    ]


def _riepilogo(args: argparse.Namespace) -> dict[str, Any]:
    """Costruisce il riepilogo; solleva (ValueError, OSError) su rifiuto.

    La scrittura avviene da ``main`` solo se questa funzione ritorna: nessun
    artefatto esiste a meta' di un rifiuto.
    """
    prereg = caa._carica_preregistrazione(args.preregistration)
    if (args.calibration is None) != (args.validation is None):
        raise ValueError(
            "configurazione a meta': il gate di scoring (Gate 2) richiede "
            "ENTRAMBI i campioni -- calibrazione e validazione indipendente. "
            "Con un campione solo il gate non e' eseguibile, e un riepilogo "
            "valutato su mezzo disegno sarebbe un verdetto su un residuo. "
            "Senza campioni il riepilogo si scrive in stato pre-campagna "
            "(stati null con la ragione).")

    digests: dict[str, str] = {}
    if args.preregistration is not None:
        digests["preregistration"] = _digest(args.preregistration)
    energia_token, energia_reason, energia_file = _stato_energetico(
        args.energy_chain)
    if energia_file is not None:
        digests["energy_chain"] = _digest(energia_file)

    sha, git_reason = _git_testa()

    if args.calibration is not None and args.validation is not None:
        risultato = run_scoring_validation_gate(
            args.calibration, args.validation, prereg["criteria"],
            threshold=prereg["threshold_alpha"],
            required_strata=prereg["required_strata"],
            seed=prereg["bootstrap_seed"],
            resamples=prereg["bootstrap_resamples"])
        digests["calibration"] = _digest(args.calibration)
        digests["validation"] = _digest(args.validation)
        scoring_status: Optional[str] = risultato.scoring_status
        scoring_per: Optional[dict[str, str]] = dict(
            risultato.scoring_status_per_stratum)
        scoring_reason = ("gate eseguito sui campioni dichiarati (digesti in "
                          "input_digests); le metriche stanno nei due report "
                          "di compute_annotator_agreement")
        flags = judge_gated_flags(risultato)
        flags_reason = ("flag prodotti da human_calibration_gate."
                        "judge_gated_flags sul risultato del gate")
    else:
        scoring_status = None
        scoring_per = None
        scoring_reason = SCORING_ASSENTE
        flags = None
        flags_reason = FLAGS_ASSENTE

    if energia_token is not None and scoring_status is not None:
        integrato: Optional[str] = integrate_experiment_status(
            energia_token, scoring_status)
        integrato_reason = (
            "integrate_experiment_status applicata ai due stati dichiarati: "
            "nessuno dei due e' cancellato")
    else:
        integrato = None
        integrato_reason = (
            "Gate 3 non e' decidibile: manca almeno uno dei due stati "
            f"(energia: {energia_reason}; scoring: {scoring_reason}). "
            "Nessun verdetto integrato viene scritto -- in particolare NON "
            "'energy_not_validated', che e' il verdetto di una catena "
            "valutata e trovata non valida.")

    return {
        "artifact": ARTEFATTO,
        "tool": "tools/calibration_gate_summary.py",
        "protocol": "P4.9 (Gate 1) / P6.7 (Gate 2) / Gate 3 "
                    "(integrate_experiment_status)",
        "sample_status": args.sample_status,
        "input_digests": digests,
        "git_head": sha,
        "git_head_reason": git_reason,
        "preregistration_used": caa._configurazione_usata(prereg),
        "energy_chain_status": energia_token,
        "energy_chain_status_reason": energia_reason,
        "scoring_status": scoring_status,
        "scoring_status_reason": scoring_reason,
        "scoring_status_per_stratum": scoring_per,
        "integrated_status": integrato,
        "integrated_status_reason": integrato_reason,
        "judge_gated_flags": flags,
        "judge_gated_flags_reason": flags_reason,
        "campaign_precheck": _verifiche(
            entrambi_campioni=args.calibration is not None
            and args.validation is not None,
            criteri=prereg["criteria"], energia=energia_file),
        "validity_note": VALIDITY_NOTE,
        "notes": (
            "Riepilogo dei tre stati. Gate 1 (energy_chain_status, P4.9) e' "
            "la catena energetica: si calcola sui dati della campagna con "
            "validation_chain.chain_status e qui viene solo letta da un "
            "artefatto, con il suo digest -- non e' un output della "
            "calibrazione dello scoring e non dipende da essa. Gate 2 "
            "(scoring_status, P6.7) e' la validazione dello scoring: "
            "Verifica A (accordo fra annotatori umani, alpha nominale) e "
            "Verifica B (validita' del giudice contro il riferimento "
            "adjudicato su campione indipendente). La soglia alpha e' il "
            "criterio di affidabilita' del riferimento umano: condizione "
            "necessaria per usarlo come gold standard, non sufficiente per "
            "abilitare il giudice, che dipende dalla sola Verifica B "
            "(specifica, correzione 1). Gate 3 (integrated_status) combina i "
            "due con integrate_experiment_status senza cancellare "
            "l'informazione originaria: 'energy_not_validated' dice che la "
            "catena e' stata valutata e non ha passato, non che lo scoring "
            "ha difetti. Un ramo judge_uncalibrated resta non valutato "
            "(is_correct=None), non incorrect. I flag judge_gated_* sono il "
            "collegamento al valutatore (evaluator.py, parametro "
            "judge_gated) ed escono da human_calibration_gate."
            "judge_gated_flags quando il gate ha girato. Riferimenti: "
            "park2024offsetbias, ye2024justice, tan2024judgebench, "
            "zheng2024llmajsurvey."
        ),
    }


def _scrivi(riepilogo: dict[str, Any], directory: Path) -> Path:
    """Scrittura atomica in coda: un file a meta' non e' un artefatto."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    percorso = directory / ARTEFATTO
    tmp = percorso.with_suffix(percorso.suffix + ".tmp")
    tmp.write_text(json.dumps(riepilogo, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(percorso)
    return percorso


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Riepilogo dei tre stati (Gate 1 P4.9, Gate 2 P6.7, "
                    "Gate 3), verifica pre-campagna e flag judge_gated per "
                    "evaluator.py; delega il calcolo a human_calibration_gate "
                    "e validation_chain")
    parser.add_argument("--calibration", type=Path, default=None,
                        help="JSONL del campione di calibrazione (Verifica A)")
    parser.add_argument("--validation", type=Path, default=None,
                        help="JSONL del campione di validazione, indipendente")
    parser.add_argument("--preregistration", type=Path, default=None,
                        help="protocollo preregistrato JSON (strati, soglia, "
                             "criteri)")
    parser.add_argument("--energy-chain", type=Path, default=None,
                        dest="energy_chain",
                        help="artefatto JSON della campagna con 'chain_status'"
                             " (token P4.9)")
    parser.add_argument("--sample-status", default="not_declared",
                        help="dichiarazione dell'operatore sulla provenienza "
                             "del campione")
    parser.add_argument("--out-dir", type=Path, default=Path("."),
                        help=f"directory di {ARTEFATTO} (default: corrente)")
    args = parser.parse_args(argv)

    try:
        riepilogo = _riepilogo(args)
    except (ValueError, OSError) as e:
        print(f"[RIFIUTO] {e}", file=sys.stderr)
        return 1

    percorso = _scrivi(riepilogo, Path(args.out_dir))
    per_strato = json.dumps(riepilogo["scoring_status_per_stratum"],
                            ensure_ascii=False)
    flags = json.dumps(riepilogo["judge_gated_flags"], ensure_ascii=False)
    print(f"Riepilogo scritto: {percorso}")
    print(f"energy_chain_status: {riepilogo['energy_chain_status']}")
    print(f"scoring_status: {riepilogo['scoring_status']} ({per_strato})")
    print(f"integrated_status: {riepilogo['integrated_status']}")
    print(f"judge_gated_flags: {flags}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
