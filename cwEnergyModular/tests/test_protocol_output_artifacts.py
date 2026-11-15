# -*- coding: utf-8 -*-
"""P3 — la preregistrazione dichiara l'artefatto nuovo e ancoraggi che tornano.

La priorita' 3 della decisione operativa del 2026-11-12 chiede di aggiornare
la preregistrazione (``experiment_results/human_calibration_protocol.json``)
PRIMA di produrre il nuovo artefatto della Opzione A,
``calibration_gate_summary.json``. Il protocollo e' NON congelato
(``pre_registration_commit`` nullo), quindi l'emendamento e' legittimo e
dovuto; questi test fissano tre invarianti, ciascuna ancorata al codice:

1. il nome dell'artefatto nuovo e' dichiarato in ``output_artifacts``, con il
   produttore che lo genera: un artefatto non preregistrato non e' un output
   del protocollo, e un nome senza produttore non e' rigenerabile da chi
   riceve il solo documento;
2. ``gate_separation.integrated_gate.output`` nomina il campo che
   l'artefatto scrive davvero (``integrated_status``): la versione 2.0 del
   protocollo diceva ``experiment_status``, un campo che non esiste nel
   codice e nel riepilogo;
3. ogni ancoraggio della forma ``file.py::fun (A-B)`` torna sui sorgenti
   attuali: ``A`` e' la riga del ``def`` e ``B`` e' l'ultima riga della
   funzione, letti dall'AST. Un ancoraggio stantio descrive un altro albero
   (regola: se un ancoraggio non torna, il file e' stantio).

Cosa non verificano: il comportamento del tool (suo test dedicato), il gate
(suo test dedicato) e gli ancoraggi di prosa che citano singole righe
(``:NNN``), la cui correttezza e' di contenuto e non di span: quelli sono
stati verificati a mano alla fonte nella stessa passata.
"""

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import calibration_gate_summary as tool  # noqa: E402

PROTOCOLLO = ROOT.parent / "experiment_results" / "human_calibration_protocol.json"

CAMPO_GATE3 = "integrated_status"

ANCORA_FUNZIONE = re.compile(
    r"([A-Za-z0-9_./-]+\.py)::([A-Za-z0-9_]+) \((\d+)-(\d+)\)")


def _protocollo():
    return json.loads(PROTOCOLLO.read_text(encoding="utf-8"))


def _stringhe_ricorsive(nodo):
    if isinstance(nodo, str):
        yield nodo
    elif isinstance(nodo, dict):
        for valore in nodo.values():
            yield from _stringhe_ricorsive(valore)
    elif isinstance(nodo, list):
        for valore in nodo:
            yield from _stringhe_ricorsive(valore)


def _risolvi_file(percorso):
    diretto = ROOT / percorso
    if diretto.exists():
        return diretto
    candidati = sorted(ROOT.rglob(Path(percorso).name))
    if len(candidati) == 1:
        return candidati[0]
    return None


def _funzione(sorgente, nome):
    def _cerca(nodo):
        for figlio in ast.iter_child_nodes(nodo):
            if isinstance(figlio, ast.FunctionDef) and figlio.name == nome:
                return figlio
            if isinstance(figlio, ast.ClassDef):
                trovata = _cerca(figlio)
                if trovata is not None:
                    return trovata
        return None

    return _cerca(ast.parse(sorgente))


def _ancore_di_funzione():
    viste = []
    for testo in _stringhe_ricorsive(_protocollo()):
        for percorso, nome, inizio, fine in ANCORA_FUNZIONE.findall(testo):
            ancora = (percorso, nome, int(inizio), int(fine))
            if ancora not in viste:
                viste.append(ancora)
    return viste


def test_artefatto_nuovo_dichiarato_in_output_artifacts():
    voci = _protocollo()["output_artifacts"]
    dichiarate = [voce for voce in voci if tool.ARTEFATTO in voce]
    assert dichiarate, (
        f"{tool.ARTEFATTO} non e' preregistrato in output_artifacts")
    assert any("calibration_gate_summary.py" in voce for voce in dichiarate), (
        "La voce che dichiara l'artefatto non nomina il produttore "
        "(tools/calibration_gate_summary.py): un nome senza produttore non "
        "e' rigenerabile.")

def test_gate3_output_nomina_il_campo_dell_artefatto():
    output = _protocollo()["gate_separation"]["integrated_gate"]["output"]
    assert output == CAMPO_GATE3, (
        f"gate_separation.integrated_gate.output dichiara '{output}', ma "
        f"l'artefatto scrive '{CAMPO_GATE3}': il campo preregistrato non "
        "esiste nel riepilogo.")

def test_esempio_gate3_usa_il_campo_dell_artefatto():
    esempio = _protocollo()["gate_separation"]["example"]
    assert CAMPO_GATE3 in esempio, (
        "L'esempio di gate_separation non contiene la chiave "
        f"{CAMPO_GATE3}.")
    assert "experiment_status" not in esempio, (
        "L'esempio di gate_separation contiene ancora la chiave "
        "'experiment_status', inesistente nel riepilogo prodotto.")

def test_ancoraggi_di_funzione_tornano_sui_sorgenti_attuali():
    stantii = []
    irrisolti = []
    for percorso, nome, inizio, fine in _ancore_di_funzione():
        sorgente_path = _risolvi_file(percorso)
        if sorgente_path is None:
            irrisolti.append(f"{percorso}::{nome} ({inizio}-{fine})")
            continue
        funzione = _funzione(sorgente_path.read_text(encoding="utf-8"), nome)
        if funzione is None:
            irrisolti.append(f"{percorso}::{nome} ({inizio}-{fine})")
            continue
        if funzione.lineno != inizio or funzione.end_lineno != fine:
            stantii.append(
                f"{percorso}::{nome} ({inizio}-{fine}) -- reale "
                f"({funzione.lineno}-{funzione.end_lineno})")
    assert not irrisolti, (
        f"Ancoraggi non risolvibili nei sorgenti: {irrisolti}")
    assert not stantii, (
        f"Ancoraggi di funzione stantii: {stantii}")
