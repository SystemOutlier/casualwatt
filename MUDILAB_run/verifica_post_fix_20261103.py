"""Riesecuzione del confronto dopo i quattro fix al ramo valutatore (03-11-2026).

Perche' esiste: `MUDILAB_run/CONFRONTO_VALUTATORI_20261103.md` fissa lo stato del
ramo `patch/scientific-evaluator-hardening` a `f8903ba6`, e i fix stanno su un
branch locale (`fix/valutatore-mudilab`) dentro un worktree. Serviva una via per
rieseguire **lo stesso** harness sui **medesimi** 321 record contro i moduli
corretti senza sovrascrivere gli artefatti committati: quelli sono la fotografia
contro cui si e' deciso, e un'appendice che li riscrive non e' un'appendice.

Cosa fa, in ordine:
  1. legge `MUDILAB_RAMPO` (obbligatoria): la cartella `cwEnergyModular` del ramo
     da valutare -- worktree o estrazione `git archive`. Non c'e' un percorso
     hardcoded di seconda mano, perche' il ramo cambia a ogni commit;
  2. importa `confronto_valutatori_20261103.py` come modulo, con
     `sys.dont_write_bytecode` attivo per non sporcare `__pycache__` accanto al
     harness;
  3. reindirizza `OUT_BASE` su `harness/risultati/
     confronto_valutatori_post_fix_20261103` e invoca il suo `main()`.

Nessun modello invocato, nessun run nuovo: i verdetti del ramo sono ricalcolati
sui JSON registrati il 02-11. L'aritmetica pubblicata non passa di qui --
`benchmark/valuta.py` resta il produttore delle misure in circolazione.

Uso (da una shell qualunque, il resto lo deduce il file):
    set MUDILAB_RAMPO=C:\\percorso\\del\\worktree\\cwEnergyModular
    python MUDILAB_run\\verifica_post_fix_20261103.py
Output atteso: le righe di riepilogo del harness e i due file in
`MUDILAB_run/harness/risultati/confronto_valutatori_post_fix_20261103.{txt,json}`.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # MUDILAB_run/
HARNESS = HERE / "confronto_valutatori_20261103.py"
OUT_STEM = HERE / "harness" / "risultati" / "confronto_valutatori_post_fix_20261103"

RAMPO = os.environ.get("MUDILAB_RAMPO", "").strip().strip('"')
if not RAMPO:
    raise SystemExit(
        "manca MUDILAB_RAMPO: indicare la cartella cwEnergyModular del ramo da "
        "valutare (worktree o estrazione git archive). Questo script non "
        "indovina il ramo.")
if not Path(RAMPO).is_dir():
    raise SystemExit(f"cartella del ramo non trovata: {RAMPO}")
if not HARNESS.is_file():
    raise SystemExit(f"harness non trovato: {HARNESS}")

sys.dont_write_bytecode = True
os.environ["MUDILAB_RAMPO"] = str(Path(RAMPO).resolve())

spec = importlib.util.spec_from_file_location("confronto_valutatori", str(HARNESS))
cv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cv)

# Verifica prima di eseguire, non dopo: se il ramo non e' quello chiesto il
# confronto non ha senso, e il file prodotto sarebbe una fotografia mentita.
assert Path(cv.RAMPO).resolve() == Path(RAMPO).resolve(), (
    f"Il harness ha letto un altro ramo: {cv.RAMPO}")
cv.OUT_BASE = OUT_STEM
sys.argv = [HARNESS.name]
raise SystemExit(cv.main())
