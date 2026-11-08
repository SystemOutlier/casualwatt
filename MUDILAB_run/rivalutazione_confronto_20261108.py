"""Ri-valutazione del confronto MUDILAB del 03-11 con il criterio dell'08-11-2026.

Perche' esiste. `harness/risultati/confronto_valutatori_20261103.{json,txt}`
registra il confronto del 03-11-2026 (commit `303051dd9`): gli stessi 321 run
letti dal criterio pubblicato e dal ramo hardened nella forma che il ramo aveva
allora. Fra il 04 e il 05-11 il ramo ha cambiato il trattamento della chiamata
al tool (`98ec5972`, `6fc13d013`): senza una prova di adozione la riga diventa
indeterminata invece di corretta. Riapplicare il criterio corrente alle stesse
righe risponde a una domanda diversa -- quanto dei 90 corretti del ramo
sopravvive alla regola piu' stretta -- e non va scritto sopra il file che
registra la misura di allora: quello resta la fotografia contro cui si e'
deciso.

Cosa fa, in ordine:
  1. legge `MUDILAB_RAMPO` (obbligatoria): la cartella che contiene
     `mudilab_adapter.py`, `robust_evaluator.py` ed `evaluation_runner.py` del
     codice con cui ri-valutare. Su `emenda-8` la provenienza e' un commit, non
     un albero sporco, quindi si estrae prima in una cartella fuori dal
     repository:
         git archive HEAD cwEnergyModular/mudilab_adapter.py \
             cwEnergyModular/robust_evaluator.py \
             cwEnergyModular/evaluation_runner.py | tar -x -C <cartella>
     e si passa `<cartella>/cwEnergyModular`;
  2. importa `confronto_valutatori_20261103.py` come modulo, con
     `sys.dont_write_bytecode` attivo per non lasciare `__pycache__` accanto
     all'harness;
  3. reindirizza `OUT_BASE` su `harness/risultati/
     confronto_valutatori_20261103_rivalutato_20261108` e invoca il suo
     `main()`.

Nessun modello viene invocato e nessuna finestra energetica viene riletta: i
verdetti del ramo sono ricalcolati sui JSON registrati il 02-11, e il lato
pubblicato passa dallo stesso `benchmark/valuta.py`. Il file prodotto non e' una
nuova misura e non sostituisce `confronto_valutatori_20261103`.

Uso (da una shell qualunque, il resto lo deduce il file):
    set MUDILAB_RAMPO=C:\\percorso\\cwEnergyModular
    python MUDILAB_run\\rivalutazione_confronto_20261108.py
Output atteso: le righe di riepilogo dell'harness e i due file in
`MUDILAB_run/harness/risultati/
confronto_valutatori_20261103_rivalutato_20261108.{txt,json}`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # MUDILAB_run/
HARNESS = HERE / "confronto_valutatori_20261103.py"
OUT_STEM = (HERE / "harness" / "risultati"
            / "confronto_valutatori_20261103_rivalutato_20261108")

RAMPO = os.environ.get("MUDILAB_RAMPO", "").strip().strip('"')
if not RAMPO:
    raise SystemExit(
        "manca MUDILAB_RAMPO: indicare la cartella che contiene "
        "mudilab_adapter.py, robust_evaluator.py ed evaluation_runner.py del "
        "codice con cui ri-valutare. Questo script non indovina il codice.")
if not Path(RAMPO).is_dir():
    raise SystemExit(f"cartella del codice non trovata: {RAMPO}")
if not HARNESS.is_file():
    raise SystemExit(f"harness non trovato: {HARNESS}")

sys.dont_write_bytecode = True
os.environ["MUDILAB_RAMPO"] = str(Path(RAMPO).resolve())

spec = importlib.util.spec_from_file_location("confronto_valutatori", str(HARNESS))
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)

# Verifica prima di eseguire, non dopo: se il codice non e' quello chiesto
# l'artefatto registrerebbe una provenienza falsa.
assert Path(cv.RAMPO).resolve() == Path(RAMPO).resolve(), (
    f"Il harness ha letto un'altra cartella: {cv.RAMPO}")
cv.OUT_BASE = OUT_STEM
sys.argv = [HARNESS.name]
raise SystemExit(cv.main())
