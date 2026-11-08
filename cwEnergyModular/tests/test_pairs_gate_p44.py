# -*- coding: utf-8 -*-
"""
tests/test_pairs_gate_p44.py — il numero di coppie e' un parametro (--pairs).

Perche' esiste. La seconda campagna P4.4 (2026-11-08, artefatti in
experiment_results/p44_gate_20261108/) e' fallita in ambiente quieto
verificato: bias 0,125171 W contro soglia 0,117995 W, 6/6 controlli
utilizzabili. La condizione della decisione 6 della Tredicesima emenda e'
quindi verificata, e la Quattordicesima la adotta nella forma minima scelta
dall'utente: 12 coppie, STESSA dt_nominal_s congelata (2,930748 s), quorum
ceil(2/3 * 12) = 8. Il criterio F.12, le soglie, il seme, la geometria e il
modello non cambiano.

Che cosa verifica:
  1. neutralita' del default: senza --pairs il disegno resta quello delle
     prime due campagne (6 coppie / 12 blocchi);
  2. --pairs 12 congela 24 blocchi nel piano, con la stessa dt_nominal_s su
     ogni controllo e le costanti di quiete;
  3. ``_verifica_piano`` rifiuta un execute il cui --pairs diverge dal piano
     dichiarato, in entrambe le direzioni, PRIMA di misurare;
  4. ``_imposta_coppie`` accetta solo interi positivi (bool escluso: in
     Python True e' un int, ma non e' un conteggio);
  5. il quorum di 12 coppie e' 8 (aritmetica esatta di ``quorum_for``);
  6. l'intestazione del report deriva dai dati, non da una costante;
  7. end-to-end a 12 coppie: 24 invocazioni reali fuorche' motore/sessione/
     stato macchina, verdetto F.12 con quorum 8.

Che cosa NON verifica: il criterio F.12 (test_control_gate_p45.py), la
precondizione di quiete (test_quiet_gate_p44.py) e il flusso a sei coppie
(test_gate_p44_end_to_end.py), che devono passare invariati.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import control_gate as cg  # noqa: E402
import run_gate_p44 as rg  # noqa: E402
from test_gate_p44_end_to_end import _installa, _righe  # noqa: E402


def _directories(monkeypatch, tmp_path):
    """Archivio/results su tmp e registrazione dei globali che ``main``
    muta (data, seme, numero di coppie): senza, un test sposterebbe la
    campagna reale o lascerebbe il disegno a 12 coppie ai test successivi."""
    monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rg, "MODULE_DIR", tmp_path)
    monkeypatch.setattr(rg, "P44_DATE", rg.P44_DATE)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", rg.ARCHIVE_DIR)
    monkeypatch.setattr(rg, "RESULTS_DIR", rg.RESULTS_DIR)
    monkeypatch.setattr(rg, "SEED", rg.SEED)
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    # guardie pre-flight sul git_head: il piano fake porta "test-head",
    # che il git reale non conoscerebbe; la verifica deve arrivare al
    # disegno, non fermarsi sulla guardia del percorso di misura
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)


def _piano(tmp_path, data="20261109"):
    archive = tmp_path / "experiment_results" / f"p44_gate_{data}"
    return json.loads((archive / rg.PLAN_NAME).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1. neutralita' del default
# ---------------------------------------------------------------------------
def test_pairs_default_lascia_il_disegno_quello_dichiarato(monkeypatch,
                                                           tmp_path):
    """Senza --pairs il piano porta il disegno delle campagne 2026-11-07 e
    2026-11-08: 6 coppie, 12 blocchi. La parametrizzazione non deve cambiare
    nulla per chi non la usa."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    assert piano["n_coppie"] == rg.DEFAULT_PAIRS == 6
    assert piano["n_blocchi"] == 12
    assert len(piano["blocks"]) == 12
    assert rg.N_COPPIE == rg.DEFAULT_PAIRS


# ---------------------------------------------------------------------------
# 2. --pairs 12: il disegno della terza campagna
# ---------------------------------------------------------------------------
def test_pairs_12_congela_24_blocchi_stessa_dt_e_quiete(monkeypatch, tmp_path):
    """La forma minima della decisione 6: cambiano SOLO i conteggi. Ogni
    controllo porta la stessa dt_nominal_s congelata dal pilota P2.9, le
    costanti di quiete restano nel piano, e i testi dichiarati (check A,
    invocazioni, deviazioni) derivano dai conteggi invece di mentire."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109", "--pairs", "12"]) == 0
    piano = _piano(tmp_path)
    assert piano["n_coppie"] == 12 and piano["n_blocchi"] == 24
    assert len(piano["blocks"]) == 24
    assert piano["blocks"][-2]["label"] == "carico-12"
    assert piano["blocks"][-1]["label"] == "controllo-12"
    assert piano["blocks"][-1]["pair_id"] == "pair-11"
    controlli = [b for b in piano["blocks"] if b["arm"] == "control"]
    assert len(controlli) == 12
    assert all(b["dt_nominal_s"] == rg.DT_NOM_FROZEN == 2.930748
               for b in controlli)
    assert all(b["richieste"] == 0 for b in controlli)
    assert "24 blocchi in 12 coppie" in piano["checks"]["A"]
    assert "(24)" in piano["invocazioni"]
    assert piano["quiet_consecutive"] == rg.QUIET_CONSECUTIVE
    assert piano["quiet_cap_s"] == rg.QUIET_CAP_S
    assert piano["order_seed"] == rg.DEFAULT_SEED
    assert rg.N_COPPIE == 12 and rg.N_BLOCCHI == 24


# ---------------------------------------------------------------------------
# 3. la verifica del piano rifiuta un disegno diverso, in entrambe le direzioni
# ---------------------------------------------------------------------------
def test_verifica_piano_rifiuta_pairs_diverso_dal_piano(monkeypatch, tmp_path):
    """Un execute con piu' (o meno) coppie del plan e' un disegno diverso da
    quello dichiarato: il rifiuto arriva prima di qualunque misura, e vale
    in entrambe le direzioni (piano 12 / tool 6 e piano 6 / tool 12)."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109", "--pairs", "12"]) == 0
    rg._imposta_coppie(6)
    with pytest.raises(SystemExit, match="--pairs diverso dal disegno"):
        rg._verifica_piano()
    # direzione opposta: piano a 6, tool a 12
    rg._imposta_coppie(6)
    assert rg.cmd_plan(rg.DEFAULT_MODEL) == 0
    rg._imposta_coppie(12)
    with pytest.raises(SystemExit, match="--pairs diverso dal disegno"):
        rg._verifica_piano()


def test_execute_con_pairs_diverso_dal_piano_ritorna_3(monkeypatch, tmp_path):
    """Il percorso di main(): --pairs discorde -> [ARRESTO] e codice 3,
    senza che una sola misura parta. La verifica del piano e' il primo atto
    di cmd_execute, quindi il rifiuto non costa nessun blocco."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109", "--pairs", "12"]) == 0
    assert rg.main(["execute", "--date", "20261109", "--pairs", "6"]) == 3


# ---------------------------------------------------------------------------
# 4. _imposta_coppie: solo interi positivi
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("n", [0, -1, 2.5, "12", True, None])
def test_imposta_coppie_rifiuta_non_conteggi(monkeypatch, n):
    """Zero o negativo non sono un disegno, un non intero non e' un
    conteggio, e True e' un int in Python ma non e' un numero di coppie:
    il rifiuto e' dichiarato, non una coercizione silenziosa."""
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    with pytest.raises(SystemExit):
        rg._imposta_coppie(n)
    assert rg.N_COPPIE == rg.DEFAULT_PAIRS


def test_imposta_coppie_aggiorna_i_due_globali_insieme(monkeypatch):
    """N_BLOCCHI e' derivato (2 per coppia): i due globali si muovono
    insieme, cosi' piano, verifica e conteggio dei controlli catturati
    leggono lo stesso disegno."""
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    rg._imposta_coppie(12)
    assert rg.N_COPPIE == 12 and rg.N_BLOCCHI == 24
    rg._imposta_coppie(1)
    assert rg.N_COPPIE == 1 and rg.N_BLOCCHI == 2


# ---------------------------------------------------------------------------
# 5. il quorum della terza campagna
# ---------------------------------------------------------------------------
def test_quorum_for_dodici_coppie_e_otto():
    """ceil(2/3 * 12) = 8 esatto: con 12 coppie il quorum sale da 4 a 8.
    L'aritmetica e' quella congelata di ``quorum_for`` (Fraction), non una
    costante scritta a mano nel tool."""
    assert cg.quorum_for(12) == 8
    assert cg.quorum_for(6) == 4  # il disegno precedente resta coperto


# ---------------------------------------------------------------------------
# 6. l'intestazione del report deriva dai dati
# ---------------------------------------------------------------------------
def test_report_intestazione_deriva_da_n_pairs(monkeypatch, tmp_path):
    """La riga 'N blocchi / M coppie' del report si calcola da n_pairs dei
    dati: un report a 12 coppie non deve dichiarare il disegno a 6."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    data = {
        "status": "not-executable", "controls_usable_n": 0, "n_pairs": 12,
        "quorum": 8, "chain_status": "bias_declared",
        "model": "m-test", "dt_nominal_s": 2.930748, "order_seed": rg.SEED,
        "bias_w": None, "bias_threshold_w": None,
        "controls": [], "runs": [],
        "results_csv": "r.csv", "block_summary_csv": "b.csv",
        "blocks_controllo_json": "c.json", "run_ids": [],
        "git_head": "h", "runner_sha256": "s",
    }
    rg._write_report(data)
    report = (tmp_path / rg.REPORT_NAME).read_text(encoding="utf-8")
    assert "- 24 blocchi / 12 coppie, un blocco per invocazione" in report
    assert "quorum = 8" in report


# ---------------------------------------------------------------------------
# 7. end-to-end a 12 coppie: 24 invocazioni e verdetto F.12 con quorum 8
# ---------------------------------------------------------------------------
def test_execute_end_to_end_ventiquattro_invocazioni_quorum_otto(monkeypatch,
                                                                 tmp_path):
    """Stesso impianto del test a sei coppie (tutto reale fuorche' motore,
    sessione e stato macchina), disegno a 12 coppie: 24 invocazioni
    alternate, propagazione P_pre su ogni controllo, zero testi spediti
    nelle finestre passive, e il verdetto F.12 esiste con quorum 8 invece
    di 4. I numeri sono del fake, l'aritmetica del gate e' vera."""
    _directories(monkeypatch, tmp_path)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(rg, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(rg, "DT_NOM_FROZEN", 0.05)
    monkeypatch.setattr(rg, "LOAD_M", 2)
    monkeypatch.setattr(rg, "LOAD_NUM_PREDICT", 2)
    rg._imposta_coppie(12)
    _fake, spediti, _meta, targets = _installa(monkeypatch)
    assert rg.cmd_plan(rg.DEFAULT_MODEL) == 0
    analysis = rg.cmd_execute(rg.DEFAULT_MODEL)

    assert len(analysis["runs"]) == 24
    for i, r in enumerate(analysis["runs"]):
        assert r["arm"] == ("load" if i % 2 == 0 else "control")
        assert r["pair_id"] == f"pair-{i // 2}"
    # propagazione: ogni carico None, ogni controllo la baseline del carico
    assert targets == [None, 10.0] * 12
    # richieste: solo i dodici blocchi di carico, m=2 ciascuno
    assert len(spediti) == 24

    blocks_csv = _righe(rg.RESULTS_DIR / rg.BLOCKS_NAME)
    assert len(blocks_csv) == 24
    assert [r["block_kind"] for r in blocks_csv] == ["load", "control"] * 12
    assert len(_righe(rg.RESULTS_DIR / rg.ROWS_NAME)) == 24

    assert analysis["n_pairs"] == 12
    assert analysis["quorum"] == 8
    assert len(analysis["controls"]) == 12
    assert analysis["status"] == "pass"
    freeze = json.loads(
        (rg.ARCHIVE_DIR / rg.FREEZE_NAME).read_text(encoding="utf-8"))
    assert freeze["quorum"] == 8
    report = (rg.ARCHIVE_DIR / rg.REPORT_NAME).read_text(encoding="utf-8")
    assert "- 24 blocchi / 12 coppie, un blocco per invocazione" in report