# -*- coding: utf-8 -*-
"""
tests/test_quiet_gate_p44.py — precondizione di quiete e grandezze riportate.

Perche' esiste. Il gate P4.4 del 2026-11-07 e' fallito (bias 0,4796 W >
soglia 0,2623 W) e nei metadati 5 controlli su 6 avevano
``background_load=True``: il runner registrava il flag ma partiva comunque.
La risposta e' una precondizione di quiete PRIMA di ogni blocco, lato tool,
senza toccare il criterio F.12 (``control_gate.evaluate_gate``, le soglie
``PRE_RANGE_MAX_W``/``DP_MAX_W``, il quorum, ``plan_blocks()``,
``DT_NOM_FROZEN``, K=1, il calcolo di E_net e ``block_baseline()`` restano
quelli congelati).

Che cosa verifica:
  1. ``--seed``: il seme e' un parametro come ``--date``; il piano lo
     congela, ``_verifica_piano`` confronta il valore passato (non una
     costante) e un execute con seme diverso si ferma prima di misurare;
  2. ``_attendi_quiete``: quiete raggiunta dopo N letture consecutive,
     azzeramento del conteggio su una lettura rumorosa, tetto raggiunto ->
     ``SystemExit`` (mai procedere in silenzio); clock, sleep, campionamento
     e top-5 iniettabili, quindi nessun hardware e nessun tempo reale;
  3. le costanti di quiete sono nel piano PRIMA delle misure e la verifica
     del piano le confronta;
  4. il riepilogo del runner espone ``background_load_before``/``after``
     (modifica minima autorizzata), e il tool li registra per blocco;
  5. le grandezze riportate (E_net/dt_W, media, sd, SE, CI95 t di Student)
     sono descrittive: non decidono l'esito del gate.

Che cosa NON verifica: il criterio F.12 (test_control_gate_p45.py) e il
flusso end-to-end delle dodici invocazioni (test_gate_p44_end_to_end.py),
che devono passare invariati.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import run_gate_p44 as rg  # noqa: E402


def _directories(monkeypatch, tmp_path):
    """Archivio/results su tmp e registrazione dei globali che ``main``
     muta (data e seme): senza, un test sposterebbe la campagna reale."""
    monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rg, "MODULE_DIR", tmp_path)
    monkeypatch.setattr(rg, "P44_DATE", rg.P44_DATE)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", rg.ARCHIVE_DIR)
    monkeypatch.setattr(rg, "RESULTS_DIR", rg.RESULTS_DIR)
    monkeypatch.setattr(rg, "SEED", rg.SEED)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")


# ---------------------------------------------------------------------------
# 1. --seed: il seme del disegno e' un parametro, non una costante
# ---------------------------------------------------------------------------
def test_seed_default_lascia_il_disegno_quello_dichiarato(monkeypatch,
                                                          tmp_path):
    """Senza --seed il piano porta il seme della campagna dichiarata:
    la parametrizzazione non deve cambiare nulla per chi non la usa."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    archive = tmp_path / "experiment_results" / "p44_gate_20261109"
    piano = json.loads((archive / rg.PLAN_NAME).read_text(encoding="utf-8"))
    assert piano["order_seed"] == rg.DEFAULT_SEED == "gate-seed-20261107"
    assert rg.SEED == rg.DEFAULT_SEED


def test_seed_custom_congelato_nel_piano_e_propagato_ai_blocchi(monkeypatch,
                                                                tmp_path):
    """Il seme passato finisce nel piano, nella verifica e negli argomenti
    del runner: un execute con lo stesso seme e' lo stesso disegno, con un
    seme diverso e' un altro disegno e si ferma PRIMA di misurare."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109",
                    "--seed", "seme-nuovo"]) == 0
    archive = tmp_path / "experiment_results" / "p44_gate_20261109"
    piano = json.loads((archive / rg.PLAN_NAME).read_text(encoding="utf-8"))
    assert piano["order_seed"] == "seme-nuovo"
    assert rg.SEED == "seme-nuovo"
    assert rg._verifica_piano()["order_seed"] == "seme-nuovo"
    kw, _prompt = rg._call_kwargs(piano["blocks"][0], None,
                                  tmp_path / "rows.csv", tmp_path / "b.csv")
    assert kw["order_seed"] == "seme-nuovo"
    monkeypatch.setattr(rg, "SEED", "seme-diverso")
    with pytest.raises(SystemExit):
        rg._verifica_piano()


def test_execute_con_seed_diverso_dal_piano_ritorna_3(monkeypatch, tmp_path):
    """Il percorso di main(): seed discorde -> [ARRESTO] e codice 3, senza
    che una sola misura parta. La verifica del piano e' il primo atto di
    cmd_execute, quindi il rifiuto non costa nessun blocco."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109",
                    "--seed", "seme-nuovo"]) == 0
    assert rg.main(["execute", "--date", "20261109",
                    "--seed", "altro-seme"]) == 3


@pytest.mark.parametrize("seme", ["", "   "])
def test_seed_vuoto_o_di_soli_spazi_rifiutato(seme):
    """Un seme vuoto non e' un seme: l'ordine dei blocchi non sarebbe
    riproducibile. Il rifiuto e' dichiarato, non uno strip silenzioso."""
    with pytest.raises(SystemExit):
        rg._imposta_seme(seme)


def test_seed_conservato_esattamente_come_passato(monkeypatch):
    """Nessuno strip silenzioso: due semi che differiscono per spazi sono
    due semi diversi, e il piano deve dire quale dei due e' stato usato."""
    monkeypatch.setattr(rg, "SEED", rg.SEED)
    rg._imposta_seme(" seme-esatto ")
    assert rg.SEED == " seme-esatto "