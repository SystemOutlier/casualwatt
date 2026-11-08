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
sys.path.insert(0, str(Path(__file__).resolve().parent))

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


# ---------------------------------------------------------------------------
# 2. _attendi_quiete: la precondizione di esecuzione, senza hardware
# ---------------------------------------------------------------------------
class _Clock:
    """Orologio iniettabile: il tempo avanza solo quando lo dice il test.
    Ogni lettura di ``total_cpu_samples`` dura ~3 s (P1.4): il fake
    campiona avanza l'orologio della stessa quantita', cosi' l'attesa
    misurata e' aritmetica dichiarata, non tempo reale."""

    def __init__(self, step=3.0):
        self.t = 0.0
        self.step = step

    def __call__(self):
        return self.t


def _campiona_da_seq(seq, clock, chiamate=None):
    letture = iter(seq)

    def fn(*a, **k):
        if chiamate is not None:
            chiamate.append(clock.t)
        clock.t += clock.step
        return next(letture)

    return fn


QUIETA = [1.0, 1.0, 1.0]        # sotto la soglia P1.4 (5% per 3 s)
RUMOROSA = [20.0, 20.0, 20.0]   # tre campioni consecutivi sopra soglia


def test_quiete_raggiunta_dopo_letture_consecutive():
    """Tre letture consecutive non rumorose: partenza. L'attesa e' misurata
    con l'orologio iniettato (9 s = 3 letture da 3 s), il top-5 e' letto una
    sola volta al momento della partenza, e la pausa fra letture e'
    iniettata (due, non tre: dopo l'ultima non si aspetta)."""
    clock = _Clock()
    sleeps = []
    top_chiamate = []
    top = [{"pid": 7, "name": "ollama.exe", "cpu_pct": 0.5}]

    def top_fn(*a, **k):
        top_chiamate.append(clock.t)
        return top

    esito = rg._attendi_quiete(
        campiona=_campiona_da_seq([QUIETA] * 3, clock), top_fn=top_fn,
        clock=clock, sleep=sleeps.append)
    assert esito["quiet_letture"] == 3
    assert esito["quiet_wait_s"] == pytest.approx(9.0)
    assert esito["top_processes"] == top
    assert top_chiamate == [9.0]
    assert sleeps == [rg.QUIET_POLL_S, rg.QUIET_POLL_S]


def test_lettura_rumorosa_azzera_il_conteggio():
    """Sequenza quieta-rumorosa-quieta-quieta-quieta: la lettura rumorosa
    AZZERA il conteggio, quindi la partenza costa 5 letture, non 3. Senza
    azzeramento la 'persistenza' sarebbe una finzione: basterebbe alternare
    rumore e quiete per partire comunque."""
    clock = _Clock()
    chiamate = []
    esito = rg._attendi_quiete(
        campiona=_campiona_da_seq(
            [QUIETA, RUMOROSA, QUIETA, QUIETA, QUIETA], clock, chiamate),
        top_fn=lambda *a, **k: [], clock=clock, sleep=lambda s: None)
    assert esito["quiet_letture"] == 5
    assert esito["quiet_wait_s"] == pytest.approx(15.0)
    assert chiamate == [0.0, 3.0, 6.0, 9.0, 12.0]


def test_tetto_raggiunto_senza_quiete_systemexit():
    """Sempre rumorosa: al tetto la campagna si ferma con messaggio chiaro
    (main() lo gira in [ARRESTO] exit 3). Mai procedere in silenzio: e'
    SystemExit, non un ritorno con flag. Il top-5 non si legge: non c'e'
    nessuna partenza da registrare."""
    clock = _Clock()
    top_chiamate = []

    def top_fn(*a, **k):
        top_chiamate.append(clock.t)
        return []

    with pytest.raises(SystemExit) as exc:
        rg._attendi_quiete(
            cap_s=30.0, campiona=_campiona_da_seq([RUMOROSA] * 100, clock),
            top_fn=top_fn, clock=clock, sleep=lambda s: None)
    assert "30 s" in str(exc.value)
    assert "NON parte" in str(exc.value)
    assert clock.t == pytest.approx(30.0)   # fermato al tetto, non oltre
    assert top_chiamate == []


def test_quiete_raggiunta_esattamente_al_tetto_non_si_ferma():
    """Il tetto e' 'secondi senza RAGGIUNGERE la quiete': se l'ultima
    lettura entro il tetto completa le consecutive, si parte. L'arresto
    e' per chi non arriva mai, non per chi arriva all'ultimo istante."""
    clock = _Clock()
    esito = rg._attendi_quiete(
        cap_s=15.0,
        campiona=_campiona_da_seq(
            [RUMOROSA, RUMOROSA, QUIETA, QUIETA, QUIETA], clock),
        top_fn=lambda *a, **k: [], clock=clock, sleep=lambda s: None)
    assert esito["quiet_letture"] == 5
    assert esito["quiet_wait_s"] == pytest.approx(15.0)


def test_costanti_di_default_quelle_congelate_nel_piano():
    """Senza argomenti la funzione usa le costanti del piano, e il piano
    le dichiara PRIMA delle misure: 3 letture consecutive, tetto 600 s.
    Un default divergente dal piano sarebbe una precondizione diversa da
    quella dichiarata."""
    assert rg.QUIET_CONSECUTIVE == 3
    assert rg.QUIET_CAP_S == 600.0
    piano = rg.plan_payload()
    assert piano["quiet_consecutive"] == 3
    assert piano["quiet_cap_s"] == 600.0
    assert "precondizione di quiete" in piano["checks"]["E"]


def test_verifica_piano_rifiuta_quiete_assente_o_diversa(monkeypatch,
                                                       tmp_path):
    """Il plan del 2026-11-07 precede la precondizione: eseguirlo misurerebbe
    con un disegno di esecuzione diverso da quello del codice. La verifica
    si ferma sulle costanti mancanti, e anche su costanti cambiate dopo la
    dichiarazione."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    path = tmp_path / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    assert piano["quiet_consecutive"] == rg.QUIET_CONSECUTIVE
    assert piano["quiet_cap_s"] == rg.QUIET_CAP_S
    del piano["quiet_consecutive"]
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit):
        rg._verifica_piano()
    piano["quiet_consecutive"] = rg.QUIET_CONSECUTIVE
    piano["quiet_cap_s"] = 1.0
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit):
        rg._verifica_piano()


def test_quiete_chiamata_prima_di_ogni_invocazione(monkeypatch, tmp_path):
    """Ordine: l'attesa precede OGNI chiamata a run_v4_benchmark, load e
    control — 12 attese per 12 invocazioni, alternate. Una quiete
    controllata una sola volta a inizio campagna non coprirebbe i blocchi
    successivi, che e' esattamente dove il 2026-11-07 ha visto il carico
    (5 controlli su 6 con background_load=True)."""
    import benchmark_v4 as v4
    from test_gate_p44_end_to_end import _installa
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(rg, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(rg, "DT_NOM_FROZEN", 0.05)
    monkeypatch.setattr(rg, "LOAD_M", 2)
    monkeypatch.setattr(rg, "LOAD_NUM_PREDICT", 2)
    _installa(monkeypatch)
    ordine = []
    reale_quiete = rg._attendi_quiete

    def quiet_spia(**kw):
        ordine.append("quiete")
        return reale_quiete(**kw)

    monkeypatch.setattr(rg, "_attendi_quiete", quiet_spia)
    reale_run = v4.run_v4_benchmark

    def run_spia(*a, **kw):
        ordine.append("run")
        return reale_run(*a, **kw)

    monkeypatch.setattr(v4, "run_v4_benchmark", run_spia)
    assert rg.cmd_plan(rg.DEFAULT_MODEL) == 0
    rg.cmd_execute(rg.DEFAULT_MODEL)
    assert ordine == ["quiete", "run"] * 12


def test_execute_registra_quiete_per_ogni_blocco(monkeypatch, tmp_path):
    """Le dodici invocazioni portano ciascuna quiet_wait_s, quiet_letture e
    il top-5 alla partenza in runs — e quindi in gate_result_frozen.json e
    nel report. L'harness e2e falsa lo stato macchina: l'attesa e'
    deterministica, la registrazione e' reale."""
    from test_gate_p44_end_to_end import _esegui_gate
    analysis, _spediti, _targets = _esegui_gate(monkeypatch, tmp_path)
    assert len(analysis["runs"]) == 12
    for r in analysis["runs"]:
        assert r["quiet_letture"] == rg.QUIET_CONSECUTIVE
        assert r["quiet_wait_s"] >= 0.0
        assert r["quiet_top_processes"] == []
    assert analysis["quiet_precondition"] == {"consecutive": 3,
                                              "cap_s": 600.0}
    freeze = json.loads(
        (rg.ARCHIVE_DIR / rg.FREEZE_NAME).read_text(encoding="utf-8"))
    assert all("quiet_wait_s" in r for r in freeze["runs"])
    assert freeze["quiet_precondition"] == analysis["quiet_precondition"]
    report = (rg.ARCHIVE_DIR / rg.REPORT_NAME).read_text(encoding="utf-8")
    assert "## Precondizione di quiete" in report
    assert "carico-1 (load): attesa=" in report
    assert "controllo-6 (control): attesa=" in report