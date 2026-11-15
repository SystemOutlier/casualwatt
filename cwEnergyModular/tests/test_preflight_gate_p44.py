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
    monkeypatch.setattr(rg, "SEED", rg.SEED)
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    monkeypatch.setattr(rg, "_git_provenienza", lambda: ("test-head", ""))
    # ARCHIVE_DIR and RESULTS_DIR are set by _imposta_data called in main()
    # Create required idle_characterization.json in the real ARCHIVE_DIR location
    # (this will be done by individual tests after _imposta_data runs)


def _create_idle_characterization(archive_dir):
    """Create a valid idle_characterization.json for testing."""
    import hashlib
    char_data = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "quiet_consecutive": 3,
        "quiet_window_s": 3.0,
        "quiet_cap_s": 600.0,
        "timestamp": "2026-11-14T00:00:00Z",
        "machine_id": "test-machine",
        "windows": 30,
        "window_s": 10.0,
        "cpu_samples": [2.0] * 30,
        "q95_cpu_pct": 2.0,
        "margin_pct": 1.0,
        "sha256": "",
    }
    hash_dict = {k: v for k, v in char_data.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char_data["sha256"] = hashlib.sha256(hash_text).hexdigest()
    (archive_dir / "idle_characterization.json").write_text(json.dumps(char_data))


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
    # Create idle_characterization in the ARCHIVE_DIR that _imposta_data will set
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
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
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
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
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
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
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_sha256", lambda path: "sha-diverso")
    with pytest.raises(SystemExit, match="SHA-256 diverso"):
        rg._verifica_piano()


def test_sha_registrato_assente_blocca(monkeypatch, tmp_path):
    """Un piano senza runner_sha256 non ancora il runner: assente e
    diverso sono la stessa cosa per la guardia (None != sha)."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
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
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: False)
    with pytest.raises(SystemExit, match="antenato"):
        rg._verifica_piano()


def test_git_head_assente_blocca(monkeypatch, tmp_path):
    """Un piano senza git_head non dichiara da quale commit viene: la
    guardia non puo' passare su un'assenza. Il messaggio distingue
    l'assenza dal diniego: il primo e' un piano scritto male (o scritto
    senza git), il secondo e' una storia che non contiene quel commit."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    piano = _piano(tmp_path)
    piano["git_head"] = ""
    _riscrivi(piano)
    with pytest.raises(SystemExit, match="git_head del piano assente"):
        rg._verifica_piano()


def test_git_non_eseguibile_nomina_la_causa(monkeypatch, tmp_path):
    """Il caso osservato su questo host il 2026-11-09: dentro la cattura di
    pytest la CreateProcess di Windows risponde OSError(22, winerror=50) e
    git non parte affatto. Prima della separazione dei due stati la guardia
    accusava 'la storia e' stata riscritta', che e' un'altra ipotesi e
    manda chi legge a cercare nel posto sbagliato. Il blocco e' identico;
    cambia solo l'accusa, che ora e' quella vera."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: False)
    monkeypatch.setattr(rg, "_git_antenato_con_ragione", lambda sha: (
        False, "git non eseguibile: OSError: [WinError 50] Richiesta non "
               "supportata"))
    with pytest.raises(SystemExit, match="git non eseguibile"):
        rg._verifica_piano()


def test_git_risponde_non_antenato_accusa_la_storia(monkeypatch, tmp_path):
    """L'altro stato: git parte e risponde che quel commit non e' nella
    storia. Qui l'accusa storica ('riscritta o altro repository') e' quella
    giusta e deve restare; il messaggio tecnico di git non la sostituisce."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: False)
    monkeypatch.setattr(rg, "_git_antenato_con_ragione",
                        lambda sha: (False, "git esce con codice 1"))
    with pytest.raises(SystemExit, match="storia e' stata riscritta"):
        rg._verifica_piano()


def test_plan_non_scritto_senza_provenienza(monkeypatch, tmp_path):
    """cmd_plan con git muto non produce un plan.json con git_head vuoto:
    sarebbe un documento pre-registrato senza collocazione nella storia, e
    il suo difetto comparirebbe solo all'execute. L'archivio resta vuoto."""
    _directories(monkeypatch, tmp_path)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "archivio")
    (tmp_path / "archivio").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(rg, "_git_head", lambda: "")
    monkeypatch.setattr(rg, "_git_provenienza", lambda: (
        "", "git non eseguibile: OSError: [WinError 50]"))
    with pytest.raises(SystemExit, match="non ha provenienza"):
        rg.cmd_plan(rg.DEFAULT_MODEL)
    assert not (rg.ARCHIVE_DIR / rg.PLAN_NAME).exists()


def test_percorso_di_misura_mutato_blocca(monkeypatch, tmp_path):
    """Fra il git_head del piano e HEAD il percorso di misura e' cambiato:
    il piano dichiara un altro runner/catena. Le estensioni neutre al tool
    del gate non entrano in questo diff, quindi non lo fanno scattare."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
    assert rg.main(["plan", "--date", "20261109"]) == 0
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: True)
    with pytest.raises(SystemExit, match="percorso di misura"):
        rg._verifica_piano()


def test_git_muto_sulla_verifica_del_percorso_blocca(monkeypatch, tmp_path):
    """None = non decidibile: una guardia che non puo' verificare non
    lascia partire il run in silenzio (fail closed)."""
    _directories(monkeypatch, tmp_path)
    archive_dir = tmp_path / "experiment_results" / "p44_gate_20261109"
    archive_dir.mkdir(parents=True, exist_ok=True)
    _create_idle_characterization(archive_dir)
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
def test_preflight_reale_piano_terza_campagna(monkeypatch, tmp_path):
    """Ancoraggio all'artefatto tracciato: il piano congelato
    ``experiment_results/p44_gate_20261109/plan.json`` (commit f9bcb5916)
    passa le QUATTRO guardie reali sull'albero corrente — data 20261109, 24
    blocchi / 12 coppie, quorum derivato 8, quiete 3/600, SHA del runner
    uguale a quello registrato, git_head dell'emenda antenato di HEAD con
    percorso di misura invariato — e la verifica completa LO BLOCCA: il
    piano precede i parametri di warm-up e della procedura di budget, che
    il tool vuole dichiarati prima di misurare. Nessuna misura: sola
    lettura. Il rifiuto e' l'esito atteso, non un difetto della guardia."""
    # I globali vanno impostati PRIMA delle guardie git reali, perche'
    # _git_percorso_misura_mutato esegue git con cwd=REPO_ROOT e
    # _sha256 legge benchmark_v4.py da MODULE_DIR. Un test precedente
    # puo' averli spostati su tmp_path.
    monkeypatch.setattr(rg, "REPO_ROOT", REPO)
    monkeypatch.setattr(rg, "MODULE_DIR", REPO / "cwEnergyModular")
    path = REPO / "experiment_results" / "p44_gate_20261109" / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    assert piano["campaign_date"] == "20261109"
    assert piano["n_coppie"] == 12 and piano["n_blocchi"] == 24
    assert len(piano["blocks"]) == 24
    assert cg.quorum_for(piano["n_coppie"]) == 8
    assert piano["quiet_consecutive"] == 3
    assert piano["quiet_cap_s"] == 600.0
    # il piano registra il git_head dell'albero su cui e' stato creato;
    # la guardia reale verifica che sia antenato di HEAD (vedi sotto)
    assert piano["runner_sha256"] == \
        "6f3bad16859c92ec9f9401605b1a367368978ed3d2fc3cb5885f3384e3d0288c"
    # le guardie reali, senza fake: SHA del runner sul file vero e git vero
    assert rg._sha256(REPO / "cwEnergyModular" / "benchmark_v4.py") == \
        piano["runner_sha256"]
    # Le due asserzioni sotto aprono un processo git. Su questo host, dentro
    # la cattura di pytest, la CreateProcess di Windows a volte non fa
    # partire affatto il figlio (OSError errno 22 winerror 50, oppure errno 6
    # winerror 6) e il fenomeno e' di SESSIONE, non di chiamata: misurato
    # l'09-11-2026 in 10 tentativi consecutivi, o falliscono tutti o non ne
    # fallisce nessuno, quindi un ritentare non c'entra niente. Nel frattempo
    # git, invocato da terminale, risponde rc=0 che 498021d6 e' antenato di
    # HEAD: il fatto ancorato e' vero, e' l'esecuzione dal processo figlio di
    # pytest a non essere disponibile. Quando non lo e' si dichiara il salto
    # con la sua ragione (stessa convenzione dei tre salti che chiedono un
    # host Linux in tests/test_rapl.py); quando lo e', l'asserzione corre e
    # coglie una storia riscritta o un piano di un altro repository.
    antenato, ragione = rg._git_antenato_con_ragione(piano["git_head"])
    if ragione.startswith("git non eseguibile"):
        pytest.skip(f"git non eseguibile dal processo di test: {ragione}")
    assert antenato is True
    assert rg._git_percorso_misura_mutato(piano["git_head"]) is False
    # la verifica completa, sull'albero VERO: i globali sono gia' impostati
    # sopra, prima delle guardie git.
    monkeypatch.setattr(rg, "P44_DATE", "20261109")
    monkeypatch.setattr(rg, "N_COPPIE", 12)
    monkeypatch.setattr(rg, "N_BLOCCHI", 24)
    monkeypatch.setattr(rg, "SEED", piano["order_seed"])

    # Il piano congelato del 20261109 contiene gia' i parametri di warm-up e
    # budget: sulla copia sul disco la guardia passa. Qui si verifica invece
    # che la guardia BLOCCA quando quei parametri mancano, costruendo un
    # piano incompleto in tmp_path (il congelato non si tocca).
    # Serve anche copiare idle_characterization.json perche' _verifica_piano
    # ora verifica la catena di provenienza piano -> caratterizzazione idle.
    incompleto = {k: v for k, v in piano.items()
                  if k not in ("warmup_tolerance_w", "warmup_cpu_max_pct",
                               "warmup_sustain_s", "warmup_cap_s",
                               "warmup_step_s", "warmup_window_s",
                               "budget_mode", "budget_n_terne",
                               "budget_matched_target_s", "criterio_primario")}
    piano_tmp = tmp_path / rg.PLAN_NAME
    piano_tmp.write_text(json.dumps(incompleto), encoding="utf-8")
    # Copia idle_characterization.json dalla campagna 20261109 (il piano
    # non ha idle_characterization_sha256 perche' e' un piano v1, ma la
    # guardia ora lo richiede. Per il test creiamo uno minimale con la soglia
    # cpu che il piano dichiara (2.0) e calcoliamo l'hash da inserire nel
    # piano incompleto, cosi' la guardia passa oltre e blocca su warm-up.)
    import hashlib as _hl
    char_minimale = {
        "schema_version": 1,
        "warmup_cpu_max_pct": piano["warmup_cpu_max_pct"],
        "sha256": "",
    }
    hash_dict = {k: v for k, v in char_minimale.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char_minimale["sha256"] = _hl.sha256(hash_text).hexdigest()
    (tmp_path / "idle_characterization.json").write_text(
        json.dumps(char_minimale), encoding="utf-8")
    # Il piano incompleto deve dichiarare idle_characterization_sha256
    # per superare la guardia della catena di provenienza.
    incompleto["idle_characterization_sha256"] = char_minimale["sha256"]
    piano_tmp = tmp_path / rg.PLAN_NAME
    piano_tmp.write_text(json.dumps(incompleto), encoding="utf-8")
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    with pytest.raises(SystemExit, match="warm-up"):
        rg._verifica_piano()
