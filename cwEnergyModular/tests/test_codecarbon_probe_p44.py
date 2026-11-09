# -*- coding: utf-8 -*-
"""
tests/test_codecarbon_probe_p44.py — probe diagnostico CodeCarbon del gate.

Perche' esiste. Il mandato del 2026-11-08 aggiunge al gate P4.4 un registro
parallelo CodeCarbon SENZA alterare il gate primario. La pretesa da
verificare non e' "CodeCarbon funziona" (e' libreria di terzi, provata dal
suo stack) ma la NEUTRALITA' verso il gate, in quattro forme: (1) senza il
flag --codecarbon il tracker non viene nemmeno costruito e l'analysis non
contiene la chiave; (2) con il flag i numeri del criterio F.12 — status,
bias_w, soglia, quorum, E_net, dt_W, budget_base_w per controllo — sono
identici a quelli della stessa campagna senza flag; (3) se la libreria
manca o il tracker non parte, il gate PROSEGUE e l'artefatto dichiara
unavailable con il motivo; (4) il backend dichiarato distingue contatore
(modello) e porta il caveat same-counter quando la modalita' e'
windows_emi.

Falsi: qui il codice REALE e' il probe e l'orchestrazione del gate; la
libreria codecarbon e' sostituita da un modulo iniettato in sys.modules —
nei test non si usa mai la libreria vera (geolocalizzazione IP, contatori
reali, costi di rete). Il fake replica i tre punti d'osservazione del
tracker che il probe legge: `_start_time`, `_hardware` con `_mode` sul CPU,
`final_emissions_data`. La libreria vera e' stata verificata a parte
sondando l'host l'08-11-2026: costruttore con measure_power_secs=1 accettato,
descrizioni hardware RAM() + CPU(Windows Emi), modalita' windows_emi.

Cosa NON verifica: l'esattezza dei joule CodeCarbon (non e' criterio di
nessuno) e il confronto vero e proprio, che e' di
tools/compare_codecarbon_gate.py e dei suoi test.
"""
import json
import math
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import codecarbon_probe as ccp  # noqa: E402
import run_gate_p44 as rg  # noqa: E402
from test_gate_p44_end_to_end import _installa  # noqa: E402


# ---------------------------------------------------------------------------
# Il doppio di codecarbon: solo i tre punti che il probe osserva.
# ---------------------------------------------------------------------------
def _emissions(i):
    val = {
        "timestamp": f"2026-11-08T12:0{i}:00", "project_name": "fake",
        "run_id": f"run-{i}", "duration": 2.93 + 0.01 * i,
        "emissions": 1.0e-6 * i, "cpu_power": 11.0, "gpu_power": 0.0,
        "ram_power": 20.0, "cpu_energy": 1.0e-5, "gpu_energy": 0.0,
        "ram_energy": 2.0e-5, "energy_consumed": 3.0e-5, "pue": 1.0,
        "codecarbon_version": "3.3.2-fake", "tracking_mode": "machine",
        "cpu_model": "fake-cpu", "ram_total_size": 16.0,
    }
    return SimpleNamespace(**{nome: val.get(nome) for nome in ccp.CAMPI_RUN})


class _CpuFalso:
    def __init__(self, mode):
        self._mode = mode

    def description(self):
        if self._mode != "constant":
            return f"CPU({' '.join(map(str.capitalize, self._mode.split('_')))})"
        return "CPU(fake-cpu > 85W [generic])"


class _RamFalso:
    def description(self):
        return "RAM()"


class GPU:
    """Il nome conta: il probe riconosce la GPU da `type(item).__name__`
    per non importare classi codecarbon nel ramo di dichiarazione."""
    _mode = None

    def description(self):
        return "GPU((none))"


class _TrackerFake:
    """Costruttore, start() e stop() come in 3.3.2: il tracker e' unico,
    le run sono una per start/stop. start() sopprime gli errori e non
    imposta _start_time; stop() produce final_emissions_data solo se la
    misura c'e'. I controlli del test: rifiuta_secs, start_fails,
    start_fails_al_secondo, stop_fails_data, cpu_mode, gpu, istanza."""

    def __init__(self, controllo, **kwargs):
        self.controllo = controllo
        self.kwargs = kwargs
        self._start_time = None
        self._pue = kwargs.get("pue", 1.0)
        hw = [_RamFalso(), _CpuFalso(controllo.get("cpu_mode", "windows_emi"))]
        if controllo.get("gpu"):
            hw.append(GPU())
        self._hardware = hw
        self.n_start = 0
        self.n_stop = 0
        self.final_emissions_data = None
        if kwargs.get("measure_power_secs") in controllo.get("rifiuta_secs", ()):
            raise ValueError(
                f"measure_power_secs={kwargs['measure_power_secs']} non "
                "accettato da questo sistema")

    def start(self):
        self.n_start += 1
        if self.controllo.get("start_fails"):
            return
        if (self.controllo.get("start_fails_al_secondo")
                and self.n_start == 2):
            return
        self._start_time = 1000.0 + self.n_start

    def stop(self):
        self.n_stop += 1
        self._start_time = None
        if self.controllo.get("stop_fails_data"):
            self.final_emissions_data = None
            return None
        self.final_emissions_data = _emissions(self.n_stop)
        return 1.0e-6


def _modulo_falso(monkeypatch, **controllo):
    """Inietta un modulo `codecarbon` completo: `__version__` e
    EmissionsTracker factory. `istanza` raccoglie il tracker costruito,
    cosi' i test asseriscono sul numero di start/stop realmente
    eseguiti."""
    controllo = dict(controllo)
    controllo["istanza"] = {}
    mod = ModuleType("codecarbon")
    mod.__version__ = "3.3.2-fake"

    def factory(**kwargs):
        tr = _TrackerFake(controllo, **kwargs)
        controllo["istanza"]["t"] = tr
        return tr

    mod.EmissionsTracker = factory
    monkeypatch.setitem(sys.modules, "codecarbon", mod)
    return controllo


def _senza_libreria(monkeypatch):
    """`None` in sys.modules: l'import fallisce con ImportError, esattamente
    come su un host dove codecarbon non e' installato."""
    monkeypatch.setitem(sys.modules, "codecarbon", None)


def _due_blocchi(probe):
    probe.apri_blocco("b00", arm="load", pair_id="pair-0")
    probe.chiudi_blocco()
    probe.apri_blocco("b01", arm="control", pair_id="pair-0")
    probe.chiudi_blocco()


# ---------------------------------------------------------------------------
# 1. Unit: ciclo di vita del probe contro il tracker finto
# ---------------------------------------------------------------------------
def test_avvia_costruisce_tracker_con_intervallo_richiesto_e_pue_dichiarato(
        monkeypatch, tmp_path):
    """Il costruttore riceve cio' che il mandato impone: measure_power_secs
    1 s di default, pue 1,0 esplicito, save_to_file con CSV nella directory
    separata, allow_multiple_runs perche' le run sono una per blocco,
    tracking_mode machine. Sono i valori che il confronto andra' a citare:
    se non passano qui, non esistono da nessuna parte."""
    controllo = _modulo_falso(monkeypatch)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    assert probe.stato["codecarbon_status"] == "ready"
    kwargs = controllo["istanza"]["t"].kwargs
    assert kwargs["measure_power_secs"] == ccp.DEFAULT_MEASURE_POWER_S == 1.0
    assert kwargs["pue"] == 1.0
    assert kwargs["tracking_mode"] == "machine"
    assert kwargs["allow_multiple_runs"] is True
    assert kwargs["output_file"] == ccp.CSV_NAME
    assert kwargs["save_to_api"] is False and kwargs["save_to_logger"] is False
    assert Path(kwargs["output_dir"]) == tmp_path / "cc"


def test_costruttore_rifiuta_1_secondo_fallback_dichiarato_a_15(
        monkeypatch, tmp_path):
    """Default 1 s SE il sistema lo consente, altrimenti 15 s: il test
    piega il costruttore sul solo valore chiesto e verifica che il probe
    riprovi a 15, dichiari il fallback nello stato e costruisca il tracker
    con l'intervallo realmente usato. Un fallback silenzioso sarebbe un
    disegno di osservazione diverso da quello dichiarato."""
    controllo = _modulo_falso(monkeypatch, rifiuta_secs=(1.0,))
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    assert probe.stato["measure_power_secs_used"] == ccp.FALLBACK_MEASURE_POWER_S
    assert probe.stato["measure_power_secs_fallback"] is True
    assert "fallback" in probe.stato["reason"]
    assert controllo["istanza"]["t"].kwargs["measure_power_secs"] == 15.0


def test_libreria_assente_unavailable_con_motivo_e_artefatti(
        monkeypatch, tmp_path):
    """Il caso del vincolo: senza codecarbon installato avvia() NON
    solleva, dichiara unavailable con il motivo leggibile, e concludi()
    scrive comunque i due JSON — e' li' che chi legge i dati dopo trova la
    ragione dell'assenza, non in un log volante."""
    _senza_libreria(monkeypatch)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is False
    assert probe.stato["codecarbon_status"] == "unavailable"
    assert "non importabile" in probe.stato["reason"]
    _due_blocchi(probe)
    riepilogo = probe.concludi()
    assert riepilogo["codecarbon_status"] == "unavailable"
    assert riepilogo["n_blocchi_aperti"] == 2
    assert riepilogo["n_blocchi_con_dati"] == 0
    status = json.loads(
        (tmp_path / "cc" / ccp.STATUS_NAME).read_text(encoding="utf-8"))
    assert status["codecarbon_status"] == "unavailable"
    assert "non importabile" in status["reason"]
    manifest = json.loads(
        (tmp_path / "cc" / ccp.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert [b["block_status"] for b in manifest["blocchi"]] == \
        ["skipped", "skipped"]
    assert all(b["reason"] for b in manifest["blocchi"])


def test_ciclo_completo_due_blocchi_manifest_con_dati_e_wall_times(
        monkeypatch, tmp_path):
    """Con tracker attivo ogni blocco chiude una run: il manifest porta
    TUTTI e due i blocchi con wall_start/wall_end (le finestre di
    allineamento del confronto, non dedotte dal CSV), status ok, e i campi
    richiesti dal mandato — timestamp, potenze, energie, energy_consumed,
    emissions — con le unita' dichiarate (W, kWh, kg CO2e)."""
    controllo = _modulo_falso(monkeypatch)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    _due_blocchi(probe)
    riepilogo = probe.concludi()
    assert riepilogo["codecarbon_status"] == "ok"
    assert riepilogo["n_blocchi_con_dati"] == 2
    tracker = controllo["istanza"]["t"]
    assert (tracker.n_start, tracker.n_stop) == (2, 2)
    manifest = json.loads(
        (tmp_path / "cc" / ccp.MANIFEST_NAME).read_text(encoding="utf-8"))
    blocchi = manifest["blocchi"]
    assert [b["block_id"] for b in blocchi] == ["b00", "b01"]
    assert [b["arm"] for b in blocchi] == ["load", "control"]
    for b in blocchi:
        assert b["block_status"] == "ok"
        assert b["wall_start_s"] <= b["wall_end_s"]
        assert b["run"]["run_id"].startswith("run-")
        for nome in ("timestamp", "cpu_power", "gpu_power", "ram_power",
                     "cpu_energy", "gpu_energy", "ram_energy",
                     "energy_consumed", "emissions"):
            assert b["run"][nome] is not None
    assert manifest["units"]["energy"] == "kWh"
    assert manifest["units"]["power"] == "W"


def test_start_non_attiva_blocco_failed_e_stato_unavailable(
        monkeypatch, tmp_path):
    """codecarbon 3.3.2 sopprime le eccezioni dentro start(): il probe non
    si fida del ritorno e guarda `_start_time`. Un tracker che non parte
    NON deve diventare una finestra di durata zero — sarebbe un numero
    inventato: il blocco e' failed col motivo, e senza alcun dato lo stato
    finale e' unavailable, non ok."""
    _modulo_falso(monkeypatch, start_fails=True)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    _due_blocchi(probe)
    riepilogo = probe.concludi()
    assert riepilogo["codecarbon_status"] == "unavailable"
    assert "nessun blocco ha prodotto dati" in riepilogo["reason"]
    assert "_start_time" in riepilogo["reason"]
    assert riepilogo["n_blocchi_con_dati"] == 0


def test_start_fallito_al_secondo_blocco_stato_partial(
        monkeypatch, tmp_path):
    """Meta' campagna osservata e meta' no: lo status e' partial con
    n_blocchi_con_dati < n_blocchi_aperti, non "ok". Un registro
    parziale presentato come completo sarebbe il peggio possibile per chi
    confronta dopo."""
    _modulo_falso(monkeypatch, start_fails_al_secondo=True)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    _due_blocchi(probe)
    riepilogo = probe.concludi()
    assert riepilogo["codecarbon_status"] == "partial"
    assert (riepilogo["n_blocchi_aperti"],
            riepilogo["n_blocchi_con_dati"]) == (2, 1)
    manifest = json.loads(
        (tmp_path / "cc" / ccp.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert [b["block_status"] for b in manifest["blocchi"]] == \
        ["ok", "failed"]


def test_stop_senza_emissions_non_inventa_finestra_zero(
        monkeypatch, tmp_path):
    """stop() che non produce final_emissions_data non deve finire nel
    manifest come run a campi vuoti letti come zero: il blocco e' failed e
    la run resta None."""
    _modulo_falso(monkeypatch, stop_fails_data=True)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    assert probe.avvia() is True
    _due_blocchi(probe)
    assert probe.concludi()["codecarbon_status"] == "unavailable"
    manifest = json.loads(
        (tmp_path / "cc" / ccp.MANIFEST_NAME).read_text(encoding="utf-8"))
    assert [b["run"] for b in manifest["blocchi"]] == [None, None]


# ---------------------------------------------------------------------------
# 2. Backend dichiarato: contatore vs modello, caveat same-counter
# ---------------------------------------------------------------------------
def test_windows_emi_dichiara_contatore_e_caveat_stesso_registro(
        monkeypatch, tmp_path):
    """Il punto metrologico del mandato B: dichiarare il canale che ha
    prodotto il numero. Con cpu_mode windows_emi il backend e' un
    contatore hardware E LO STESSO MSR 0x611 della catena emi-counter di
    CasualWatt: lo stato deve portare il caveat, perche' un accordo fra i
    due non e' validazione indipendente (regola AGENTS)."""
    _modulo_falso(monkeypatch, cpu_mode="windows_emi")
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    probe.avvia()
    probe.apri_blocco("b00", arm="load", pair_id="pair-0")
    backend = probe.stato["backend"]
    assert backend["cpu_mode"] == "windows_emi"
    assert backend["cpu_kind"] == "contatore hardware"
    assert backend["gpu_tracciata"] is False
    assert "RAM()" in backend["hardware"] and "modello" in backend["ram"]
    assert "0x611" in probe.stato["same_counter_caveat"]
    assert "coerenza di implementazione" in probe.stato["same_counter_caveat"]
    probe.chiudi_blocco()
    assert probe.concludi()["same_counter_caveat"]


def test_costante_tdp_dichiara_modello_nessun_caveat_same_counter(
        monkeypatch, tmp_path):
    """Controesempio: su un host senza EMI il fallback di codecarbon e'
    la costante TDP (85 W generici). Lì il numero E' un modello: cpu_kind
    "modello o stima", nessun caveat same-counter — il caveat e' legato
    alla modalita' osservata, non alla libreria in quanto tale. Con GPU
    presente gpu_tracciata diventa True: assente/0 W non e' una misura."""
    _modulo_falso(monkeypatch, cpu_mode="constant", gpu=True)
    probe = ccp.ProbeCodeCarbon(tmp_path / "cc")
    probe.avvia()
    probe.apri_blocco("b00", arm="load", pair_id="pair-0")
    assert probe.stato["backend"]["cpu_kind"] == \
        "modello o stima (nessun contatore)"
    assert probe.stato["same_counter_caveat"] is None
    assert probe.stato["backend"]["gpu_tracciata"] is True
    probe.chiudi_blocco()
    assert probe.concludi()["backend"]["cpu_mode"] == "constant"


# ---------------------------------------------------------------------------
# 3. E2E col gate: neutralita' del flag sui numeri del criterio
# ---------------------------------------------------------------------------
def _fake_engine_gate(monkeypatch, tmp_path, sottocartella,
                      codecarbon=False):
    """Stesso disegno di test_gate_p44_end_to_end con una coppia sola
    (2 blocchi): motore/sessione/stato macchina finti e deterministici,
    plan+execute reali. Ritorna l'analysis."""
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    rg._imposta_coppie(1)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / sottocartella / "archive")
    monkeypatch.setattr(rg, "RESULTS_DIR", tmp_path / sottocartella / "results")
    monkeypatch.setattr(rg, "DT_NOM_FROZEN", 0.05)
    monkeypatch.setattr(rg, "LOAD_M", 2)
    monkeypatch.setattr(rg, "LOAD_NUM_PREDICT", 2)
    _installa(monkeypatch)
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    assert rg.cmd_plan(rg.DEFAULT_MODEL) == 0
    return rg.cmd_execute(rg.DEFAULT_MODEL, codecarbon=codecarbon)


def _grandezze_criterio(analysis):
    """Le sole quantita' che F.12 decide — non una di piu', non una di
    meno: e' la lista su cui il flag deve essere inerte."""
    return {
        "status": analysis["status"],
        "bias_w": analysis["bias_w"],
        "bias_threshold_w": analysis["bias_threshold_w"],
        "quorum": analysis["quorum"],
        "chain_status": analysis["chain_status"],
        "controls_usable_n": analysis["controls_usable_n"],
        "n_pairs": analysis["n_pairs"],
        "per_controllo": [(c["e_net_j"], c["dt_w_s"], c["budget_base_w"],
                          c["usable"], c["block_pass"])
                         for c in analysis["controls"]],
    }


def test_senza_flag_nessun_file_nessun_tracker_nessuna_chiave(
        monkeypatch, tmp_path):
    """Il comportamento senza flag deve restare identico a oggi, e
    "identico" qui e' misurato in tre forme: nessuna directory
    codecarbon/ nell'archivio, nessun tracker realmente costruito (la
    factory finta non e' mai stata chiamata — quindi neppure l'import
    pesante), e nessuna chiave codecarbon nell'analysis."""
    controllo = _modulo_falso(monkeypatch)
    analysis = _fake_engine_gate(monkeypatch, tmp_path, "senza")
    assert "codecarbon" not in analysis
    assert controllo["istanza"] == {}
    assert not (rg.ARCHIVE_DIR / ccp.DIR_NAME).exists()


def test_con_flag_numeri_del_gate_identici_e_chiave_aggiunta(
        monkeypatch, tmp_path):
    """La verifica centrale del mandato B: la STESSA campagna deterministica
    eseguita senza e con --codecarbon produce le stesse identiche
    grandezze del criterio F.12 (status, bias, soglia, quorum,
    chain_status, E_net/dt_W/budget_base_w/usable/block_pass per
    controllo). Il flag aggiunge una chiave accanto, non dentro: i valori
    finti del tracker (11 W, 3e-5 kWh) non compaiono da nessun'altra
    parte dell'analysis."""
    _modulo_falso(monkeypatch)
    a = _fake_engine_gate(monkeypatch, tmp_path / "A", "senza")
    _modulo_falso(monkeypatch)
    b = _fake_engine_gate(monkeypatch, tmp_path / "B", "con",
                          codecarbon=True)
    assert _grandezze_criterio(a) == _grandezze_criterio(b)
    assert b["codecarbon"]["codecarbon_status"] == "ok"
    assert b["codecarbon"]["n_blocchi_aperti"] == 2
    assert "11.0" not in json.dumps(_grandezze_criterio(b))
    # il gate primario del fake resta il noto: bias 0,1 W < 0,223607 W
    assert b["bias_w"] == pytest.approx(0.1)
    assert b["bias_threshold_w"] == pytest.approx(
        math.hypot(0.1, 0.2), abs=1e-6)
    assert b["status"] == "pass"


def test_con_flag_manifest_allinea_i_bloccoli_del_piano(
        monkeypatch, tmp_path):
    """Le finestre del registro parallelo devono corrispondere BLOCCO per
    BLOCCO al piano: 2 run per 2 invocazioni, bracci e pair_id uguali a
    `runs`, e il tracciamento reale e' una coppia start/stop per blocco —
    non un tracker unico a cavallo della campagna (che darebbe una riga
    sola, non confrontabile per blocco)."""
    controllo = _modulo_falso(monkeypatch)
    b = _fake_engine_gate(monkeypatch, tmp_path, "con", codecarbon=True)
    tracker = controllo["istanza"]["t"]
    assert (tracker.n_start, tracker.n_stop) == (2, 2)
    manifest = json.loads(
        (Path(b["codecarbon"]["directory"]) / ccp.MANIFEST_NAME
         ).read_text(encoding="utf-8"))
    assert [x["arm"] for x in manifest["blocchi"]] == \
        [r["arm"] for r in b["runs"]]
    assert [x["pair_id"] for x in manifest["blocchi"]] == \
        [r["pair_id"] for r in b["runs"]]
    assert [x["block_id"] for x in manifest["blocchi"]] == \
        [r["label"] for r in b["runs"]]


def test_libreria_assente_gate_prosegue_unavailable_dichiarato(
        monkeypatch, tmp_path):
    """Il vincolo B per come va su un host senza codecarbon: l'execute NON
    si ferma, il verdetto resta quello del fake (pass, bias 0,1 W), e
    l'artefatto dichiara unavailable con la ragione. Un gate bloccato da
    un osservatore opzionale sarebbe un workaround al contrario."""
    _senza_libreria(monkeypatch)
    analysis = _fake_engine_gate(monkeypatch, tmp_path, "cc-assente",
                                 codecarbon=True)
    assert analysis["status"] == "pass"
    assert analysis["bias_w"] == pytest.approx(0.1)
    cc = analysis["codecarbon"]
    assert cc["codecarbon_status"] == "unavailable"
    assert "non importabile" in cc["reason"]
    status_file = Path(cc["status_file"])
    assert status_file.exists()
    assert json.loads(status_file.read_text(encoding="utf-8"))[
        "codecarbon_status"] == "unavailable"


def test_cli_main_passa_flag_e_intervallo_a_cmd_execute(
        monkeypatch, tmp_path):
    """L'interfaccia promessa deve esistere: `execute --codecarbon` arriva
    a cmd_execute con codecarbon=True, `--codecarbon-interval 5` arriva
    come measure_power_secs; senza flag arrivano i default neutri
    (False/None), perche' la firma del gate non cambia per chi non usa il
    registro. Qui si ferma un passo prima della misura."""
    visti = []

    def finto(model, **kw):
        visti.append((model, kw))
        return {"status": "pass"}

    for nome in ("P44_DATE", "ARCHIVE_DIR", "RESULTS_DIR", "SEED",
                 "N_COPPIE", "N_BLOCCHI"):
        monkeypatch.setattr(rg, nome, getattr(rg, nome))
    monkeypatch.setattr(rg, "cmd_execute", finto)
    assert rg.main(["execute", "--date", "20261109", "--pairs", "12",
                    "--codecarbon"]) == 0
    assert visti[-1][1] == {"codecarbon": True, "codecarbon_interval": None}
    assert rg.main(["execute", "--date", "20261109", "--pairs", "12",
                    "--codecarbon", "--codecarbon-interval", "5"]) == 0
    assert visti[-1][1] == {"codecarbon": True, "codecarbon_interval": 5.0}
    assert rg.main(["execute", "--date", "20261109", "--pairs", "12"]) == 0
    assert visti[-1][1] == {"codecarbon": False, "codecarbon_interval": None}
