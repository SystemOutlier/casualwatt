# -*- coding: utf-8 -*-
"""Guardie della CLI report_carbon.

La CLI esiste perche' la tesi deve poter RIGENERARE il numero del report
(regola: un'analisi non tracciata e' un numero che nessuno puo' rigenerare).
Qui si verifica il percorso end-to-end su un CSV minimo e il rifiuto
dichiarato quando i fattori non sono validi.
"""
import importlib.util
import json
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "report_carbon.py"
_spec = importlib.util.spec_from_file_location("report_carbon", TOOL)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def _csv(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text("ollama_active_energy_j\n360000\n", encoding="utf-8")
    return p


def test_cli_end_to_end(tmp_path):
    """360000 J = 0.1 kWh; con PUE 1.2 e rete 0.5 -> 0.06 kg. Scrive JSON+LaTeX
    con provenance (sha256) ed etichetta 'stima'."""
    out_dir = tmp_path / "out"
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "0.5",
                   "--grid-source", "ISPRA", "--pue", "1.2",
                   "--output-dir", str(out_dir)])
    assert rc == 0
    data = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert data["label"] == "stima"
    assert data["estimate"]["emissions_kg"] == pytest.approx(0.06)
    assert data["provenance"]["input_csv_sha256"]
    assert (out_dir / "report.tex").exists()


def test_cli_rifiuta_intensita_non_finita(tmp_path):
    """Intensita' non finita: rifiuto dichiarato, codice 2, nessun output."""
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "nan",
                   "--grid-source", "ISPRA", "--output-dir", str(tmp_path / "o")])
    assert rc == 2


def test_cli_rifiuta_fonte_vuota(tmp_path):
    """Fonte vuota: il fattore non ha provenienza, rifiuto con codice 2."""
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "0.5",
                   "--grid-source", "", "--output-dir", str(tmp_path / "o")])
    assert rc == 2


def test_cli_input_inesistente(tmp_path):
    """Input inesistente: errore dichiarato, codice 2."""
    rc = cli.main(["--input", str(tmp_path / "no.csv"), "--grid-intensity", "0.5",
                   "--grid-source", "ISPRA", "--output-dir", str(tmp_path / "o")])
    assert rc == 2