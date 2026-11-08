# -*- coding: utf-8 -*-
"""
tests/test_preflight_gate_p44.py — guardie pre-flight del piano (punto A).

Perche' esiste. Il piano della terza campagna (p44_gate_20261109, 12 coppie)
e' congelato prima dei dati: l'execute deve partire solo contro QUEL piano,
con QUEL runner e QUEL percorso di misura. Le guardie del disegno (coppie,
blocchi, seme, quiete) esistevano gia'; mancavano quelle su data della
campagna, SHA-256 del runner e git_head.

Forma della guardia git_head, scelta dall'utente il 2026-11-08 perche'
l'uguaglianza stretta ``git_head == HEAD`` e' in conflitto con due fatti:
il commit del piano stesso muove HEAD (il piano registra il commit
dell'emenda), e il vincolo di non rigenerare il piano congelato vieta di
riallinearlo dopo ogni commit. La guardia adottata: ``git_head`` del piano
deve essere un antenato di HEAD e il PERCORSO DI MISURA
(``benchmark_v4.py``, ``energy/``) deve essere invariato fra i due commit;
lo SHA-256 del runner e' una seconda guardia, indipendente. Il tool del
gate puo' evolvere con estensioni neutre dichiarate (il probe CodeCarbon);
il percorso di misura no. Una guardia non verificabile (git muto) non
passa in silenzio: blocca.

Che cosa NON verifica: il criterio F.12, le soglie, i risultati congelati
delle campagne precedenti — nulla di cio' e' toccato da queste guardie.
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

REPO = Path(__file__).resolve().parent.parent.parent


def _directories(monkeypatch, tmp_path):
    """Archivio/results su tmp, git e SHA fake coerenti col piano fake:
    le guardie pre-flight sono iniettate, quindi ogni test le piega UNA
    alla volta e verifica che sia proprio quella a fermare il run."""
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
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)


def _piano(tmp_path):
    return json.loads(
        (rg.ARCHIVE_DIR / rg.PLAN_NAME).read_text(encoding="utf-8"))


def _riscrivi(piano):
    (rg.ARCHIVE_DIR / rg.PLAN_NAME).write_text(
        json.dumps(piano), encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. baseline: con tutto coerente la verifica passa
# ---------------------------------------------------------------------------
def test_piano_coerente_passa_la_verifica(monkeypatch, tmp_path):
    """Il caso di riferimento: data, SHA, antenato e percorso invariato
    sono coerenti col piano. Se questo fallisce, le guardie sotto stanno
    bloccando qualcosa che non dovrebbero."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = rg._verifica_piano()
    assert piano["campaign_date"] == "20261109"


# ---------------------------------------------------------------------------
# 2. guardia sulla data della campagna
# ---------------------------------------------------------------------------
def test_data_del_piano_diversa_da_execute_blocca(monkeypatch, tmp_path):
    """Un piano della campagna X nell'archivio della campagna Y non e' il
    piano di Y: il run si ferma prima di misurare, anche se il disegno e'
    identico."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    piano["campaign_date"] = "20261110"
    _riscrivi(piano)
    with pytest.raises(SystemExit, match="campagna"):
        rg._verifica_piano()


def test_execute_su_piano_di_altra_data_ritorna_3(monkeypatch, tmp_path):
    """Il percorso di main(): il rifiuto diventa [ARRESTO] e codice 3,
    senza che una sola misura parta."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    piano["campaign_date"] = "20261110"
    _riscrivi(piano)
    assert rg.main(["execute", "--date", "20261109"]) == 3


# ---------------------------------------------------------------------------
# 3. guardia sullo SHA-256 del runner
# ---------------------------------------------------------------------------
def test_sha_del_runner_diverso_blocca(monkeypatch, tmp_path):
    """benchmark_v4.py e' il percorso di misura: se il suo SHA-256 non e'
    quello registrato nel piano, il numero prodotto non sarebbe quello
    dichiarato. Il vincolo e' bloccante, non un avviso."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_sha256", lambda path: "sha-diverso")
    with pytest.raises(SystemExit, match="SHA-256 diverso"):
        rg._verifica_piano()


def test_sha_registrato_assente_blocca(monkeypatch, tmp_path):
    """Un piano senza runner_sha256 non ancora il runner: assente e
    diverso sono la stessa cosa per la guardia (None != sha)."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    del piano["runner_sha256"]
    _riscrivi(piano)
    with pytest.raises(SystemExit, match="SHA-256 diverso"):
        rg._verifica_piano()


# ---------------------------------------------------------------------------
# 4. guardia sul git_head: antenato + percorso di misura invariato
# ---------------------------------------------------------------------------
def test_git_head_non_antenato_blocca(monkeypatch, tmp_path):
    """Storia riscritta o piano di altro repository: il git_head dichiarato
    non e' raggiungibile da HEAD. Il run non parte."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: False)
    with pytest.raises(SystemExit, match="antenato"):
        rg._verifica_piano()


def test_git_head_assente_blocca(monkeypatch, tmp_path):
    """Un piano senza git_head non dichiara da quale commit viene: la
    guardia non puo' passare su un'assenza."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    piano["git_head"] = ""
    _riscrivi(piano)
    with pytest.raises(SystemExit, match="antenato"):
        rg._verifica_piano()


def test_percorso_di_misura_mutato_blocca(monkeypatch, tmp_path):
    """Fra il git_head del piano e HEAD il percorso di misura e' cambiato:
    il piano dichiara un altro runner/catena. Le estensioni neutre al tool
    del gate non entrano in questo diff, quindi non lo fanno scattare."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: True)
    with pytest.raises(SystemExit, match="percorso di misura"):
        rg._verifica_piano()


def test_git_muto_sulla_verifica_del_percorso_blocca(monkeypatch, tmp_path):
    """None = non decidibile: una guardia che non puo' verificare non
    lascia partire il run in silenzio (fail closed)."""
    _directories(monkeypatch, tmp_path)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: None)
    with pytest.raises(SystemExit, match="decidibile"):
        rg._verifica_piano()


def test_helper_git_fail_closed_senza_git(monkeypatch, tmp_path):
    """I due helper contro un REPO_ROOT che non e' un repository: git
    risponde non-zero (o non risponde affatto) e il risultato e' il
    rifiuto, mai un True/False di comodo."""
    monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
    assert rg._git_antenato("0" * 40) is False
    assert rg._git_percorso_misura_mutato("0" * 40) is None


def test_percorso_misura_copre_runner_e_catena():
    """Il perimetro della guardia e' dichiarato: il runner v4 e la catena
    dei contatori. Il tool del gate (tools/) ne sta fuori, ed e' la scelta
    che permette le estensioni neutre senza rigenerare il piano."""
    assert rg.PERCORSO_MISURA == (
        "cwEnergyModular/benchmark_v4.py", "cwEnergyModular/energy")


# ---------------------------------------------------------------------------
# 5. pre-flight REALE del piano congelato della terza campagna
# ---------------------------------------------------------------------------
def test_preflight_reale_piano_terza_campagna(monkeypatch):
    """Ancoraggio all'artefatto tracciato: il piano congelato
    ``experiment_results/p44_gate_20261109/plan.json`` (commit f9bcb5916)
    passa le guardie reali sull'albero corrente — data 20261109, 24
    blocchi / 12 coppie, quorum derivato 8, quiete 3/600, SHA del runner
    uguale a quello registrato, git_head dell'emenda antenato di HEAD con
    percorso di misura invariato. Nessuna misura: sola lettura."""
    path = REPO / "experiment_results" / "p44_gate_20261109" / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    assert piano["campaign_date"] == "20261109"
    assert piano["n_coppie"] == 12 and piano["n_blocchi"] == 24
    assert len(piano["blocks"]) == 24
    assert cg.quorum_for(piano["n_coppie"]) == 8
    assert piano["quiet_consecutive"] == 3
    assert piano["quiet_cap_s"] == 600.0
    assert piano["git_head"] == \
        "498021d601ae5a54ddace0b0fa72a145ace3ae06"
    assert piano["runner_sha256"] == \
        "99846365de073fa112a1594b5659d73d393a86ddf6cca3e196467a25f7881ee0"
    # le guardie reali, senza fake: SHA del runner sul file vero e git vero
    assert rg._sha256(REPO / "cwEnergyModular" / "benchmark_v4.py") == \
        piano["runner_sha256"]
    assert rg._git_antenato(piano["git_head"]) is True
    assert rg._git_percorso_misura_mutato(piano["git_head"]) is False
    # e la verifica completa, spostando i globali sul piano vero
    monkeypatch.setattr(rg, "P44_DATE", "20261109")
    monkeypatch.setattr(rg, "ARCHIVE_DIR", path.parent)
    monkeypatch.setattr(rg, "N_COPPIE", 12)
    monkeypatch.setattr(rg, "N_BLOCCHI", 24)
    monkeypatch.setattr(rg, "SEED", piano["order_seed"])
    verificato = rg._verifica_piano()
    assert verificato["n_coppie"] == 12