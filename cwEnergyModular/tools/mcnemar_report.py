# -*- coding: utf-8 -*-
"""tools/mcnemar_report.py — confronto appaiato fra due criteri, da un report.

Perche' esiste. `evaluation_runner.paired_mcnemar` calcola la McNemar appaiata
e il suo intervallo di Newcombe, ma per un anno nessun report la chiamava: la
funzione era provata solo dai test, e un campo sbagliato non avrebbe toccato
nessun numero pubblicato finche' qualcuno non l'avesse usata. Questo script e'
il consumatore: legge il report che contiene **due verdetti sulle stesse righe**
(il confronto fra criterio pubblicato e ramo hardened su MUDILAB) e scrive la
matrice, il test e l'intervallo accanto alla fonte, senza ricalcolare i verdetti.

**Cosa legge.** Un JSON con una lista di righe (`--rows-key`, default `righe`);
per ogni riga due valori risolti da percorsi puntati (`--verdict-a`, default
`pubblicato.corretta`; `--verdict-b`, default `rampo.passi.end_to_end`) e
l'identita' del task (`--task-key`, default `task_id`). I verdetti grezzi
arrivano a `paired_mcnemar`, che applica la propria coercizione: `correct` e
`incorrect` sono determinati, `indeterminate`, `missing` ed errore tecnico
restano fuori dalla matrice e finiscono in `n_excluded` con la ragione.

**La riduzione e' dichiarata.** Le repliche della stessa richiesta non sono
prove indipendenti: la matrice si costruisce su **una coppia per task**. La
regola `first` tiene la prima riga incontrata per ogni task, nell'ordine del
file, e non dipende dall'esito. `n_tasks_with_replicates` dice quante coppie la
riduzione ha scartato e `n_without_task` quante righe non erano appaiabili:
entrambe sono nel report invece di essere assorbite in silenzio.

**Cosa non fa.** Nessun modello, nessuna finestra energetica, nessuna
riscrittura dei verdetti: sola lettura dell'input, un JSON e un `.txt` in uscita.
Non sostituisce il report che legge, lo accompagna.

Uso (dalla radice del repository):
    py cwEnergyModular/tools/mcnemar_report.py --input <report.json> --out <uscita.json>
    py cwEnergyModular/tools/mcnemar_report.py --input <estratto.json> \\
        --source "MUDILAB_run/harness/risultati/confronto_valutatori_20261103.json (HEAD 303051dd9)"
`--source` esiste per un caso preciso: quando le righe vengono estratte da un
blob git (`git show <rev>:<file> > estratto.json`) l'input letto e' una copia
temporanea, ma la provenienza da scrivere nel report e' il percorso tracciato
piu' la revisione. Senza `--source` il report registra il percorso letto.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
sys.path.insert(0, str(MODULE_DIR))

from evaluation_runner import paired_summary  # noqa: E402  (dopo sys.path)

DEFAULT_VERDICT_A = "pubblicato.corretta"
DEFAULT_VERDICT_B = "rampo.passi.end_to_end"


def _valore(riga: dict, percorso: str) -> Any:
    """Risolve un percorso puntato; un campo assente e' un errore, non un None."""
    valore: Any = riga
    for pezzo in percorso.split("."):
        if not isinstance(valore, dict) or pezzo not in valore:
            raise KeyError(f"campo {percorso!r} assente nella riga")
        valore = valore[pezzo]
    return valore


def _testo(esito: dict, fonte: str, etichetta_a: str, etichetta_b: str) -> str:
    ci = esito["delta_ci_newcombe"]
    chi2 = "n/d (b+c < 10: binomiale esatto)" if esito["chi2"] is None else (
        f"{esito['chi2']} (p={esito['p_value_chi2']}, correzione="
        f"{esito['correction_applied']})")
    esclusi = ", ".join(f"{k}={v}" for k, v in sorted(esito["excluded_by_reason"].items()))
    coppie = esito["n_determinate"] + esito["n_excluded"]
    quota_escluse = esito["n_excluded"] / coppie if coppie else 0.0
    linee = [
        f"McNemar appaiato: {etichetta_a} vs {etichetta_b}",
        f"fonte: {fonte}",
        f"riduzione: {esito['reduction']} (prima riga per task) -- "
        f"{esito['n_tasks']} task, {esito['n_tasks_with_replicates']} con repliche, "
        f"{esito['n_without_task']} righe senza identita'",
        f"matrice: a={esito['a']} b={esito['b']} c={esito['c']} d={esito['d']} "
        f"(discordanti {esito['discordant']}, determinate {esito['n_determinate']}, "
        f"escluse {esito['n_excluded']})",
        f"p esatto (binomiale): {esito['p_value_exact']}",
        f"chi2: {chi2}",
        f"delta_acc = (b-c)/n: {esito['delta_acc']}  "
        f"CI 95% Newcombe: {ci}",
        f"esclusi per ragione: {esclusi or 'nessuno'}",
    ]
    # Un test senza coppie discordanti non dice "nessuna differenza": dice che
    # non e' decidibile, e la specifica chiede di riportarlo cosi'.
    if esito["indecis"]:
        linee.append("verdetto: INDECISO -- nessuna coppia discordante, non una "
                     "parita' dimostrata")
    if quota_escluse > 0.10:
        linee.append(f"cautela: {quota_escluse * 100:.1f}% delle coppie escluse "
                     "(>10%): il confronto parla di poche righe")
    return "\n".join(linee) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="McNemar appaiato fra due verdetti sulle stesse righe")
    parser.add_argument("--input", type=Path, required=True,
                        help="JSON con le righe del report")
    parser.add_argument("--source", default=None,
                        help="provenienza da registrare nel report (default: --input)")
    parser.add_argument("--rows-key", default="righe",
                        help="chiave della lista di righe (default: righe)")
    parser.add_argument("--task-key", default="task_id",
                        help="campo con l'identita' del task (default: task_id)")
    parser.add_argument("--verdict-a", default=DEFAULT_VERDICT_A,
                        help=f"percorso del verdetto A (default: {DEFAULT_VERDICT_A})")
    parser.add_argument("--verdict-b", default=DEFAULT_VERDICT_B,
                        help=f"percorso del verdetto B (default: {DEFAULT_VERDICT_B})")
    parser.add_argument("--label-a", default="pubblicato",
                        help="nome del sistema A nel testo (default: pubblicato)")
    parser.add_argument("--label-b", default="ramo:passi",
                        help="nome del sistema B nel testo (default: ramo:passi)")
    parser.add_argument("--out", type=Path, default=None,
                        help="JSON di uscita (default: mcnemar_<nome input>.json "
                             "accanto all'input)")
    args = parser.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"input non trovato: {args.input}")
    documento = json.loads(args.input.read_text(encoding="utf-8"))
    righe = documento.get(args.rows_key) if isinstance(documento, dict) else None
    if not isinstance(righe, list) or not righe:
        raise SystemExit(f"{args.input}: nessuna lista {args.rows_key!r} da leggere")

    verdi_a, verdi_b, identita = [], [], []
    for riga in righe:
        verdi_a.append(_valore(riga, args.verdict_a))
        verdi_b.append(_valore(riga, args.verdict_b))
        identita.append(_valore(riga, args.task_key))

    esito = paired_summary(verdi_a, verdi_b, identita)
    uscita = args.out or args.input.with_name(f"mcnemar_{args.input.stem}.json")
    fonte = args.source or str(args.input)
    documento_uscita = {
        "input": fonte,
        "colonne": {"task": args.task_key, "verdetto_a": args.verdict_a,
                    "verdetto_b": args.verdict_b,
                    "etichetta_a": args.label_a, "etichetta_b": args.label_b},
        "righe_lette": len(righe),
        **esito,
    }
    uscita.write_text(json.dumps(documento_uscita, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    testo = _testo(esito, fonte, args.label_a, args.label_b)
    uscita.with_suffix(".txt").write_text(testo, encoding="utf-8")
    print(testo, end="")
    print(f"scritto: {uscita} e {uscita.with_suffix('.txt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
