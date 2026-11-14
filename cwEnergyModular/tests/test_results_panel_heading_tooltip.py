# -*- coding: utf-8 -*-
"""
tests/test_results_panel_heading_tooltip.py — Pannello 3: i tooltip sulle
testate di colonna mostrano l'attributo che identifica la colonna.

La testa di colonna e' l'unico posto in cui una colonna viene identificata
visivamente nel pannello Risultati: l'etichetta italiana (es. "E2E J") non
e' il nome con cui la colonna si trova nel CSV e nel dizionario delle righe
(es. `end_to_end_energy_j`). Questo test fissa il contratto:

  - `_heading_attr(event)` ritorna `(cid, label, width)` quando il mouse e'
    sulla testa di colonna (`identify_row` vuoto), None quando e' su una
    riga dati (`identify_row` restituisce un iid);
  - `_on_tree_motion` su una testa di colonna mostra un tooltip che
    contiene "Attributo colonna: <cid>";
  - `_on_tree_motion` su una riga dati non mostra il tooltip dell'attributo
    (rimane il tooltip della risposta del modello, se applicabile).

Nessun display reale richiesto: il test costruisce il pannello in un Tk
root reale (l'ambiente di test lo permette) e finge i movimenti del mouse
sostituendo `identify_row` / `identify_column` con i valori di ritorno che
la geometria reale produrrebbe, cosi' il test non dipende dalla larghezza
del monitor o dal layout.
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

import tkinter as tk

from gui.results_panel import ResultsPanel, CSV_VIEW_COLUMNS


def _write_csv(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_VIEW_COLUMNS)
        for r in rows:
            w.writerow([r.get(c, "") for c in CSV_VIEW_COLUMNS])


class _FakeEvent:
    """Event minimale: solo le coordinate che i metodi del Treeview usano."""

    def __init__(self, x=0, y=0, x_root=0, y_root=0):
        self.x = x
        self.y = y
        self.x_root = x_root
        self.y_root = y_root


@pytest.fixture
def panel(tmp_path):
    csv_path = tmp_path / "results.csv"
    _write_csv(csv_path, [{"model_label": "qwen", "prompt_id": "p001"}])
    import config

    old = config.CSV_RESULTS_PATH
    config.CSV_RESULTS_PATH = csv_path
    root = tk.Tk()
    root.withdraw()
    p = ResultsPanel(root)
    p.refresh()
    yield p
    root.destroy()
    config.CSV_RESULTS_PATH = old


def _idx(cid: str) -> int:
    """Indice 1-based di una colonna in CSV_VIEW_COLUMNS (come #N di identify_column)."""
    for i, (c, _, _) in enumerate(CSV_VIEW_COLUMNS, start=1):
        if c == cid:
            return i
    raise KeyError(cid)


def test_heading_attr_su_testa_di_colonna(panel):
    """Sulla testa di colonna `_heading_attr` ritorna la terna (cid, label, width)."""
    panel.tree.identify_row = lambda y: ""
    panel.tree.identify_column = lambda x: f"#{_idx('model_response')}"
    h = panel._heading_attr(_FakeEvent())
    assert h is not None
    assert h == ("model_response", "Risposta Modello", 320)


def test_heading_attr_su_riga_dati_restituisce_none(panel):
    """Su una riga dati `_heading_attr` ritorna None (e' la risposta, non l'attributo)."""
    panel.tree.identify_row = lambda y: "I001"
    panel.tree.identify_column = lambda x: f"#{_idx('model_response')}"
    assert panel._heading_attr(_FakeEvent()) is None


def test_heading_attr_su_colonna_non_riconosciuta(panel):
    """Una colonna fuori range non e' un'attributo: None, non un IndexError."""
    panel.tree.identify_row = lambda y: ""
    panel.tree.identify_column = lambda x: "#999"
    assert panel._heading_attr(_FakeEvent()) is None


def test_on_tree_motion_mostra_attributo_sulla_testa_di_colonna(panel):
    """`_on_tree_motion` sulla testa di colonna mostra il tooltip dell'attributo."""
    panel.tree.identify_row = lambda y: ""
    panel.tree.identify_column = lambda x: f"#{_idx('end_to_end_energy_j')}"
    panel._on_tree_motion(_FakeEvent(x_root=10, y_root=10))
    assert panel._tip is not None and panel._tip.winfo_exists()
    text = panel._tip._lbl.cget("text")
    assert "Attributo colonna: end_to_end_energy_j" in text
    assert "E2E J" in text


def test_on_tree_motion_nasconde_attributo_sulla_riga_dati(panel):
    """Su una riga dati il tooltip dell'attributo non esce."""
    panel.tree.identify_row = lambda y: "I001"
    panel.tree.identify_column = lambda x: f"#{_idx('model_response')}"
    panel._on_tree_motion(_FakeEvent(x_root=10, y_root=10))
    assert panel._tip is None or not panel._tip.winfo_exists()


def test_heading_attr_tutte_le_colonne(panel):
    """Ogni colonna del CSV_VIEW_COLUMNS e' identificabile via tooltip."""
    for idx, (cid, label, _w) in enumerate(CSV_VIEW_COLUMNS, start=1):
        panel.tree.identify_row = lambda y: ""
        panel.tree.identify_column = lambda x, _i=idx: f"#{_i}"
        h = panel._heading_attr(_FakeEvent())
        assert h is not None, cid
        assert h[0] == cid
        assert h[1] == label