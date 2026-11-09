# -*- coding: utf-8 -*-
"""
tests/test_gate_p44_end_to_end.py — il flusso del gate P4.4 dalla regia in su.

Perche' esiste. I test di P4.4/P4.5 che hanno accompagnato l'ingresso del
blocco di controllo chiamano ``run_block`` direttamente (test_controllo_p44_v4.py)
o stubbano ``run_block`` stesso (test_terminazione_v4.py): nessuno passa dal
livello che ha generato il difetto del 2026-11-08 — ``run_v4_benchmark`` che
accetta ``block_kind='control'`` e poi spedisce comunque ``m`` richieste perche'
``control`` non arriva mai al blocco. Questo file sostituisce la fiducia in
quella copertura con l'esecuzione reale del percorso: orchestrazione vera,
``run_block`` vero, export veri, ``evaluate_gate`` vero; falsi solo il motore,
la sessione energetica, lo stato macchina e il cooldown.

Che cosa verifica:
  1. neutralita': con i valori di default del 2026-11-08 l'output CSV di un
     blocco di carico e' identico (run id e session id esclusi) con e senza
     gli argomenti ``initial_last_pre_w``/``block_kind`` passati esplicitamente
     — la deroga R1 non deve spostare nulla sul percorso gia' coperto;
  2. coerenza per derivazione: ``block_kind='control'`` arrivato attraverso
     ``run_v4_benchmark`` NON spedisce richieste e produce i campi
     ``control_*``; con ``block_kind='load'`` o ``'campaign'`` il percorso e'
     quello di carico e i campi ``control_*`` non esistono. L'etichetta e il
     percorso non possono divergere per costruzione;
  3. il disegno: dodici righe, sei coppie, carico primo, pair_id corretti,
     parametri inerti non passati sui controlli, e verifica del piano
     dichiarato contro il codice;
  4. end-to-end del tool: ``cmd_plan`` + ``cmd_execute`` con dodici
     invocazioni vere di ``run_v4_benchmark``, propagazione
     ``initial_last_pre_w`` carico -> controllo osservata nel cooldown, e
     ``evaluate_gate`` che dall'output del tool restituisce un VERDETTO
     (``pass``/``fail``), mai ``not-executable``.

Che cosa NON verifica: il criterio F.12 in se' (test_control_gate_p45.py), la
meccanica del cooldown (test_cooldown_v4.py), la struttura del blocco di
controllo (test_controllo_p44_v4.py). Qui si verifica che il livello di regia
li attraversi tutti.
"""
import csv
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import benchmark_unified as bu  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import energy.local_energy as le  # noqa: E402
import machine_state as ms  # noqa: E402
import run_gate_p44 as rg  # noqa: E402
from energy.worker_tree import WorkerProc  # noqa: E402

T0 = 1000.0
WORKER = WorkerProc(7, 1000.0, "ollama.exe")
PRE = [9.9, 10.0, 10.1]
POST = [10.3, 10.4, 10.5]
BW = round(math.hypot(0.1, 0.2), 6)   # 0,223607 W


class _SessioneGate:
    """Sessione unica per carico e controllo: bordi validi con il contatore
    che avanza di 10,1 J ogni secondo di contatore.

    Con P_pre = 10,0 W la finestra passiva sottrae esattamente 10,0 J e
    restituisce ``E_net,control = 0,1 J`` su ``dt_W = 1,0 s``: bias 0,1 W,
    sotto la soglia 0,223607 W. Un numero inventato nel fake sarebbe stato
    peggio: qui il valore atteso e' aritmetica dichiarata.
    """

    running = True
    source_method = "emi-counter"
    source_notes: list = []
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    calibrated_at = ""
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self):
        self.calib = 0
        self.t = T0
        self.j = 1000.0
        self.ts = 1_000_000_000
        # La porta delle finestre idle: e' da qui che il gate misura il fondo
        # pre-esecuzione, e deve essere la STESSA sessione dei bordi perche'
        # nella realta' e' lo stesso contatore di package.
        self._source = _PortaIdle(self)

    def start(self):
        pass

    def stop(self):
        pass

    def settle_idle(self, *a, **k):
        return 1.0

    def calibrate_idle(self, *a, **k):
        self.calib += 1
        return 10.0 if self.calib % 2 == 1 else 10.4

    @property
    def _idle_reps(self):
        return list(PRE if self.calib % 2 == 1 else POST)

    def _edge(self):
        self.t += 1.0
        self.j += 10.1
        self.ts += 10_000_000          # 1,0 s in unita' da 100 ns
        return {
            "tree": [WORKER],
            "worker": {WORKER: self.t},
            "busy": self.t * 10.0,
            "counter": {"pkg_j": self.j, "pkg_pwh": self.j * 100.0,
                        "ts_100ns": self.ts, "pp1_j": None},
            "counter_error": "",
            "t_wall": self.t,
            "t_wall_utc": f"2026-11-08T10:00:{self.t - T0:06.3f}+00:00",
            "t_counter_mono": self.t,
            "t_cpu_mid": self.t,
            "edge_spread_s": 0.02,
        }

    def read_measurement_edge(self, **k):
        return self._edge()

    def read_ttft_edge(self, t_first_token):
        edge = self._edge()
        edge["t_ttft_mono"] = float(t_first_token)
        return edge

    def samples_between(self, a, b):
        return []

    def package_energy_exact_between(self, a, b, excl=None,
                                     exclude_windows=None):
        # sentinella: con bordi validi l'energia arriva dai contatori ai bordi;
        # se questo valore comparisse in una riga, il percorso e' degradato
        return -1.0e6


class _PortaIdle:
    """Le finestre idle lette dal budget pre-esecuzione.

    Perche' queste potenze. Il gate misura tre unita' pre e tre post della
    stessa durata di un controllo e le aggrega con ``block_baseline``: con
    le terne PRE = (9.9, 10.0, 10.1) e POST = (10.3, 10.4, 10.5) il numero
    che ne esce e' ``hypot(0.1, 0.2) = 0,223607 W``, esattamente ``BW`` e
    esattamente la soglia mediana che F.12 calcola sui blocchi. Non e' un
    valore di comodo: e' aritmetica dichiarata, e se il tool applicasse un
    fattore di scala o aggregasse in modo diverso il numero divergerebbe.

    ``durata`` richiesta e durata osservata coincidono perche' qui si prova
    la regola di aggregazione, non il pavimento del primitivo reale
    (``energy_session.py:672`` porta la finestra a 0,5 s: ``_installa``
    dichiara il pavimento 0 perche' il fake non ce l'ha).
    """

    method = "emi-counter"
    last_read_error = ""

    def __init__(self, sessione):
        self.sessione = sessione
        self.letture = 0
        self.potenze = list(PRE) + list(POST)

    def read_idle_window_j(self, durata_s):
        durata_s = float(durata_s)
        if self.letture >= len(self.potenze):
            self.letture = 0
        p = self.potenze[self.letture]
        self.letture += 1
        return (p * durata_s, durata_s, self.method)


def _resp(i):
    return {
        "text": "ok", "prompt_tokens": 100, "completion_tokens": 20,
        "tokens_valid": True, "duration_s": 1.0,
        "prefill_duration_s": 0.2, "decoding_duration_s": 0.5,
        "done_reason": "stop", "raw_created_at": "", "tool_calls": 0,
        "keep_alive_sent": -1, "num_ctx": 8192, "num_predict": 2,
        "_t0": 60.0 + 3.0 * i, "_t1": 61.0 + 3.0 * i,
        "_wall_start": 1.0, "_t_ttft": 60.2 + 3.0 * i,
        "ttft_s": 0.2, "ttft_available": True,
    }


def _installa(monkeypatch):
    """Falsi solo fuori dal percorso verificato: motore, sessione, stato
    macchina, metadati e cooldown. ``run_block``, gli export e il gate sono
    reali. Il cooldown finto REGISTRA i target ricevuti: e' li' che si vede
    la propagazione."""
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table",
            timestamp=0.0))
    fake = _SessioneGate()
    monkeypatch.setattr(v4, "SESSION", fake)

    prof = le.CasualWattLocalEnergyProfiler()
    prof.session = fake

    def factory(*a, **k):
        return prof

    factory.probe_cpu_time_resolution = staticmethod(lambda *a, **k: 0.0156)
    monkeypatch.setattr(v4, "CasualWattLocalEnergyProfiler", factory)

    spediti: list = []

    def fake_stream(model, text, *a, **k):
        spediti.append(text)
        return dict(_resp(len(spediti)))

    monkeypatch.setattr(v4, "infer_v4_stream", fake_stream)
    monkeypatch.setattr(v4, "evaluate_response",
                        lambda *a, **k: bu.evalres_placeholder())

    monkeypatch.setattr(
        v4, "prepare_machine_state",
        lambda **kw: {"power": {}, "top_processes": [],
                      "cpu_samples_pct": [1.0], "background_load": False,
                      "sampler_interval_s": 0.5})
    monkeypatch.setattr(
        v4, "prepare_model_state",
        lambda model, **kw: {"residency": {"action": "already-resident",
                                           "expires_at": ""},
                             "warmups": []})
    monkeypatch.setattr(
        v4, "probe_machine_state_after",
        lambda **kw: {"top_processes": [], "cpu_samples_pct": [1.0],
                      "background_load": False})
    # Precondizione di quiete (lato tool): senza questi due fake
    # cmd_execute campionerebbe la macchina REALE (~3 s per lettura, 12
    # blocchi) e il test dipenderebbe dal carico dell'host. I fake rendono
    # l'attesa deterministica; le asserzioni di questo file non cambiano.
    monkeypatch.setattr(ms, "total_cpu_samples",
                        lambda *a, **k: [1.0, 1.0, 1.0])
    monkeypatch.setattr(ms, "sample_top_processes", lambda *a, **k: [])
    monkeypatch.setattr(v4, "_ollama_runtime_info", lambda model: ("v", "d"))
    meta: dict = {}
    monkeypatch.setattr(v4, "write_run_metadata",
                        lambda payload, path: meta.update(payload) or path)

    targets: list = []

    def fake_cd(target, **kw):
        targets.append(target)
        ran = (isinstance(target, (int, float)) and math.isfinite(float(target))
               and float(target) > 0.0)
        return {"ran": ran, "reached": ran, "timed_out": False,
                "waited_s": 0.0,
                "target_pre_w": float(target) if ran else "",
                "samples": 1, "missing_reads": 0,
                "reason": "cooldown fake"}

    monkeypatch.setattr(v4, "cooldown_to_baseline", fake_cd)

    # Lato tool, Revisione del Gate 2026-11-09. (1) Il fake non ha il
    # pavimento di ``read_idle_window_j`` (energy_session.py:672 porta la
    # finestra a 0,5 s) e questi test accorciano Tc a 0,05 s: senza deroga
    # il tool fermerebbe GIUSTAMENTE la misura del fondo, e qui si vuole
    # provare l'orchestrazione, non il pavimento (che e' nei test dedicati).
    # (2) La stabilizzazione post-carico legge DUE segnali sulla finestra:
    #     ``v4.cooldown_power_w`` (che su questa sessione restituirebbe la
    #     sentinella -1e6 J della finestra degradata) e
    #     ``ms.total_cpu_samples``, gia' fake sopra a 1,0 % di media. Qui si
    #     dichiara una macchina rientrata a 10,0 W e ferma all'1,0 % con
    #     permanenza nulla, perche' la MECCANICA del criterio multisegnale e'
    #     provata nei test dedicati, non qui.
    monkeypatch.setattr(rg, "BUDGET_FLOOR_FINESTRA_S", 0.0)
    monkeypatch.setattr(rg, "WARMUP_SUSTAIN_S", 0.0)
    monkeypatch.setattr(rg, "WARMUP_STEP_S", 0.0)
    monkeypatch.setattr(rg, "WARMUP_WINDOW_S", 0.05)
    monkeypatch.setattr(v4, "cooldown_power_w", lambda window_s: 10.0)
    # (3) La temperatura del warm-up e' registrazione, non criterio: il ramo
    # reale apre un subprocess (powershell + CIM) e sotto la cattura dei fd
    # di pytest risponde l'OSError(22) noto dell'ambiente, non un numero.
    # Qui si inietta una lettura valida perche' il record registri la fonte
    # provata del ramo, non l'errore del runner dei test.
    monkeypatch.setattr(rg, "_temperatura_cpu_c",
                        lambda: (27.85, "fake:MSAcpi_ThermalZoneTemperature"))
    return fake, spediti, meta, targets


def _righe(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


# run id e session id sono identita' dell'invocazione; timestamp_end e'
# l'orologio reale a secondi (benchmark_v4.py:1990) e due invocazioni a
# cavallo di un secondo divergerebbero per costruzione. edge_start_utc ed
# edge_end_utc no: derivano dal t_wall_utc dell'edge, quindi restano nel
# confronto.
_ESCLUDE = {"run_id", "session_id", "timestamp_end"}


def _normalizza(righe):
    return [{k: v for k, v in r.items() if k not in _ESCLUDE} for r in righe]


# ---------------------------------------------------------------------------
# 1. neutralita' deroga R1: default espliciti == argomenti assenti
# ---------------------------------------------------------------------------
def test_default_esPLICITI_non_mutano_l_output_di_carico(monkeypatch,
                                                         tmp_path):
    """La deroga approva due modifiche al runner "entrambe neutre a default".
    Questa e' la prova: stesso disegno di carico invocato senza i nuovi
    argomenti e con ``initial_last_pre_w=None``/``block_kind`` espliciti deve
    produrre righe e riepiloghi identici (run id e session id esclusi). Se
    divergesse, la neutralita' sarebbe un'affermazione, non una misura."""
    def _run(nome, extra):
        _installa(monkeypatch)
        rows = tmp_path / f"rows_{nome}.csv"
        blocks = tmp_path / f"blocks_{nome}.csv"
        v4.run_v4_benchmark(["m-test"], [{"id": "p1", "text": "domanda",
                                          "answer_type": "auto",
                                          "source": "test"}],
                            m=2, num_predict=2, blocks_per_point=1,
                            batch_id="neut",
                            max_invalidated_blocks=1,
                            substitution_seed="neut",
                            results_path=rows, block_summary_path=blocks,
                            **extra)
        return _normalizza(_righe(rows)), _normalizza(_righe(blocks))

    righe_a, riep_a = _run("senza", {})
    righe_b, riep_b = _run("con", {"initial_last_pre_w": None,
                                   "block_kind": "campaign"})
    assert righe_b == righe_a
    assert riep_b == riep_a


def test_block_kind_load_non_attiva_il_percorso_di_controllo(monkeypatch,
                                                             tmp_path):
    """Il caso da escludere e' la divaricazione etichetta/percorso. Con
    ``block_kind='load'`` la derivazione deve valere ``control=False``: le
    richieste partono e i campi ``control_*`` non esistono nemmeno nel
    riepilogo in memoria."""
    _fake, spediti, _meta, _t = _installa(monkeypatch)
    blocks = tmp_path / "blocks.csv"
    captured = []
    reale = v4.export_summary_csv
    monkeypatch.setattr(
        v4, "export_summary_csv",
        lambda recs, path, cols, mode="a": (
            [captured.append(dict(r)) for r in recs],
            reale(recs, path, cols, mode=mode))[1])
    v4.run_v4_benchmark(["m-test"], [{"id": "p1", "text": "domanda",
                                      "answer_type": "auto",
                                      "source": "test"}],
                        m=2, num_predict=2, blocks_per_point=1,
                        block_kind="load", batch_id="nb",
                        max_invalidated_blocks=1, substitution_seed="nb",
                        results_path=tmp_path / "rows.csv",
                        block_summary_path=blocks)
    assert len(spediti) == 2
    assert not any(k.startswith("control_") for k in captured[0])


# ---------------------------------------------------------------------------
# 2. coerenza per derivazione, dal livello di orchestrazione
# ---------------------------------------------------------------------------
def test_controllo_da_run_v4_benchmark_non_invia_richieste(monkeypatch,
                                                           tmp_path):
    """Qui e' scoppiato il difetto del 2026-11-08: ``block_kind='control'``
    arrivava al runner ma ``control`` non arrivava mai a ``run_block``, e un
    blocco di carico etichettato controllo avrebbe spedito m richieste. Ora
    la derivazione sta nel punto esatto: zero righe di richiesta, zero testi
    spediti, campi ``control_*`` valorizzati nel riepilogo in memoria."""
    _fake, spediti, _meta, _targets = _installa(monkeypatch)
    blocks = tmp_path / "blocks.csv"
    captured = []
    reale = v4.export_summary_csv
    monkeypatch.setattr(
        v4, "export_summary_csv",
        lambda recs, path, cols, mode="a": (
            [captured.append(dict(r)) for r in recs],
            reale(recs, path, cols, mode=mode))[1])
    summary = v4.run_v4_benchmark(
        ["m-test"], [{"id": "c1", "text": "", "answer_type": "auto",
                      "source": "gate_control"}],
        blocks_per_point=1, block_kind="control", pair_id="pair-0",
        order_seed="gate-seed-20261107", dt_nominal_s="0.05",
        batch_id="ctrl-test", max_invalidated_blocks=1,
        substitution_seed="ctrl-test", initial_last_pre_w=10.0,
        results_path=tmp_path / "rows.csv", block_summary_path=blocks)
    assert spediti == []
    assert summary["records"] == 0
    rec = captured[0]
    assert rec["block_kind"] == "control"
    assert rec["control_e_net_j"] == pytest.approx(0.1)
    assert rec["control_dt_w_s"] == pytest.approx(1.0)
    assert rec["control_package_window_source"] == "exact-counter"
    assert rec["cooldown_timeout"] == "false"   # il cooldown ha ricevuto 10 W
    assert rec["r_A"] == "" and rec["r_B"] == ""
    assert summary["errors"] == 0


# ---------------------------------------------------------------------------
# 3. il disegno dichiarato
# ---------------------------------------------------------------------------
def test_disegno_dodici_righe_sei_coppie_carico_primo():
    """plan.json deve dire dodici righe, non sei invocazioni da due: in
    un'invocazione sola il block_kind e' uno e non puo' coprire due bracci.
    Le righe di controllo NON portano m/num_predict/use_nonce: passarli
    fingerebbe che operino su ``range(0)`` (requisito 5)."""
    blocchi = rg.plan_blocks()
    assert len(blocchi) == 12
    for i, b in enumerate(blocchi):
        assert b["pair_id"] == f"pair-{i // 2}"
        assert b["arm"] == ("load" if i % 2 == 0 else "control")
        assert b["index"] == i
    for b in blocchi:
        if b["arm"] == "load":
            assert (b["m"], b["num_predict"], b["use_nonce"]) == (32, 32, True)
        else:
            assert "m" not in b and "num_predict" not in b
            assert "use_nonce" not in b
            assert b["richieste"] == 0
            assert b["dt_nominal_s"] == 2.930748
    assert rg.BLOCKS_PER_POINT == 1


def test_verifica_piano_blocca_il_codice_cambiato_dopo_la_dichiarazione(
        monkeypatch, tmp_path):
    """Esecuzione ammessa solo contro il piano dichiarato. Se il codice dei
    blocchi cambia dopo il plan (o il seed), il tool si ferma PRIMA di
    misurare: un disegno modificato dopo la dichiarazione sarebbe scoperto
    solo sui dati."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    # cmd_plan non scrive un piano senza provenienza: il soggetto di questo
    # test e' il seed/manomissione, la guardia su git_head ha il suo file.
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    rg.cmd_plan(rg.DEFAULT_MODEL)
    piano = json.loads((tmp_path / rg.PLAN_NAME).read_text(encoding="utf-8"))
    assert piano["n_blocchi"] == 12 and piano["n_coppie"] == 6
    assert piano["order_seed"] == rg.SEED
    assert piano["blocks"][1]["arm"] == "control"
    assert piano["blocks"][0]["arm"] == "load"
    assert "initial_last_pre_w" in str(piano["checks"]["D"])
    piano["order_seed"] = "seed-manomesso"
    (tmp_path / rg.PLAN_NAME).write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit):
        rg._verifica_piano()


def test_date_parametro_sposta_gli_output_senza_toccare_il_disegno(
        monkeypatch, tmp_path):
    """--date e' un'etichetta di campagna, non un parametro del disegno:
    archivio e results si spostano, ``plan_blocks()`` e il seed restano
    quelli dichiarati, quindi la verifica del piano non si invalida e un
    secondo run non richiede di editare il codice."""
    monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rg, "MODULE_DIR", tmp_path)
    monkeypatch.setattr(rg, "P44_DATE", rg.P44_DATE)
    monkeypatch.setattr(rg, "ARCHIVE_DIR", rg.ARCHIVE_DIR)
    monkeypatch.setattr(rg, "RESULTS_DIR", rg.RESULTS_DIR)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    assert rg.main(["plan", "--date", "20261109"]) == 0
    archive = tmp_path / "experiment_results" / "p44_gate_20261109"
    piano = json.loads((archive / rg.PLAN_NAME).read_text(encoding="utf-8"))
    assert piano["blocks"] == rg.plan_blocks()
    assert piano["order_seed"] == rg.SEED
    assert piano["campaign_date"] == "20261109"
    assert rg.ARCHIVE_DIR == archive
    assert rg.RESULTS_DIR == tmp_path / "results" / "p44_gate_20261109"
    # il piano e' per campagna: execute su un archivio senza plan si ferma
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "vuoto")
    with pytest.raises(SystemExit):
        rg.cmd_execute(rg.DEFAULT_MODEL)


@pytest.mark.parametrize("data", ["2026-11-09", "20261399", "202611", ""])
def test_date_non_valida_rifiutata_prima_di_scrivere(monkeypatch, tmp_path,
                                                     data):
    """Una data malformata non deve creare archivi: il rifiuto arriva prima
    di qualunque scrittura (strptime da solo accettrebbe anche '2026117')."""
    monkeypatch.setattr(rg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rg, "MODULE_DIR", tmp_path)
    with pytest.raises(SystemExit):
        rg.main(["plan", "--date", data])
    assert list(tmp_path.iterdir()) == []


def test_report_mostra_pass_false_rapporto_enet_dt_e_baseline(
        monkeypatch, tmp_path):
    """Il report deve rendere leggibili tre grandezze che il JSON gia' porta:
    E_net/dt_W per controllo, quanti utilizzabili falliscono il criterio per
    blocco (block_pass=False, non i None dei non utilizzabili), e la baseline
    propagata contro quella propria del blocco. Un dt_W=0 non produce una
    divisione: 'n/d'. I numeri ricalcano il fail reale del 20261107
    (2,64 J contro budget 0,885 J)."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    data = {
        "status": "fail", "controls_usable_n": 2, "n_pairs": 2,
        "quorum": 2, "chain_status": "",
        "model": "m-test", "dt_nominal_s": 0.05, "order_seed": rg.SEED,
        "bias_w": 0.9, "bias_threshold_w": 0.3,
        "controls": [
            {"block_id": "b-1", "usable": True, "control_unstable": False,
             "pre_range_w": 0.1, "dP": 0.5, "e_net_j": 2.64,
             "dt_w_s": 2.93, "budget_base_j": 0.885,
             "budget_base_w": 0.302, "window_source": "exact-counter",
             "block_pass": False, "reason": ""},
            {"block_id": "b-2", "usable": True, "control_unstable": False,
             "pre_range_w": 0.1, "dP": -0.1, "e_net_j": 0.31,
             "dt_w_s": 0.0, "budget_base_j": 0.511,
             "budget_base_w": 0.173, "window_source": "exact-counter",
             "block_pass": True, "reason": ""},
            {"block_id": "b-3", "usable": False, "control_unstable": True,
             "pre_range_w": 1.2, "dP": 1.1, "e_net_j": -2.56,
             "dt_w_s": 2.93, "budget_base_j": 0.9,
             "budget_base_w": 0.31, "window_source": "exact-counter",
             "block_pass": None, "reason": "|dP| > 1 W"},
        ],
        "runs": [
            {"label": "controllo-1", "arm": "control", "block_id": "b-1",
             "initial_last_pre_w": 6.3, "block_baseline_pre_w": 5.2,
             "block_cooldown_timeout": "false"},
        ],
        "results_csv": "r.csv", "block_summary_csv": "b.csv",
        "blocks_controllo_json": "c.json", "run_ids": ["x"],
        "git_head": "h", "runner_sha256": "s",
    }
    rg._write_report(data)
    report = (tmp_path / rg.REPORT_NAME).read_text(encoding="utf-8")
    # b-3 non e' utilizzabile: il suo block_pass=None non entra nel conteggio
    assert "utilizzabili con block_pass=False: 1/2" in report
    assert "E_net/dt_W=0.901024 W" in report      # 2.64 / 2.93
    assert "E_net/dt_W=n/d" in report             # dt_W = 0
    assert "P_pre_ref propagata dal carico=6.3 W" in report
    assert "propria del blocco=5.2 W" in report
    assert "baseline propria del blocco=5.2" in report


# ---------------------------------------------------------------------------
# 4. end-to-end del tool: dodici invocazioni reali e verdetto F.12
# ---------------------------------------------------------------------------
def _esegui_gate(monkeypatch, tmp_path, gate_controls: "list|None" = None):
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(rg, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(rg, "DT_NOM_FROZEN", 0.05)
    monkeypatch.setattr(rg, "LOAD_M", 2)
    monkeypatch.setattr(rg, "LOAD_NUM_PREDICT", 2)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    _fake, spediti, _meta, targets = _installa(monkeypatch)
    if gate_controls is not None:
        # spia in sola lettura su cio' che il gate riceve: la lista e' cio'
        # che ``control_gate.evaluate_gate`` vede, per provare che una fase
        # di servizio non entra nel verdetto
        reale = rg.cg.evaluate_gate

        def spione(controls, **kw):
            gate_controls.extend(controls)
            return reale(controls, **kw)

        monkeypatch.setattr(rg.cg, "evaluate_gate", spione)
    assert rg.cmd_plan(rg.DEFAULT_MODEL) == 0
    analysis = rg.cmd_execute(rg.DEFAULT_MODEL)
    return analysis, spediti, targets


def test_execute_end_to_end_dodici_invocazioni_e_verdetto(monkeypatch,
                                                          tmp_path):
    """Il test che sostituisce la fiducia nei test esistenti: dall'orchestrazione
    al gate, tutto reale fuorche' motore/sessione/stato macchina. Aspetti:
    dodici invocazioni alternate carico/controllo con pair_id di coppia;
    la propagazione P_pre arriva al cooldown SOLO sui controlli; zero testi
    spediti durante le finestre passive; i campi che ``evaluate_gate`` legge
    sono valorizzati; e il verdetto esiste (pass), non 'not-executable'."""
    analysis, spediti, targets = _esegui_gate(monkeypatch, tmp_path)

    assert len(analysis["runs"]) == 12
    for i, r in enumerate(analysis["runs"]):
        assert r["arm"] == ("load" if i % 2 == 0 else "control")
        assert r["pair_id"] == f"pair-{i // 2}"

    # propagazione: ogni carico None (primo blocco della sua invocazione),
    # ogni controllo 10.0 = baseline_pre_w del carico della stessa coppia
    assert targets == [None, 10.0] * 6

    # richieste: solo i sei blocchi di carico, m=2 ciascuno
    assert len(spediti) == 12

    # riepiloghi CSV: dodici blocchi, sei di controllo; le righe di richiesta
    # sono solo dei carico (6 x 2)
    blocks_csv = _righe(rg.RESULTS_DIR / rg.BLOCKS_NAME)
    assert len(blocks_csv) == 12
    assert [r["block_kind"] for r in blocks_csv] == \
        ["load", "control"] * 6
    assert [r["pair_id"] for r in blocks_csv] == \
        [f"pair-{i // 2}" for i in range(12)]
    assert len(_righe(rg.RESULTS_DIR / rg.ROWS_NAME)) == 12

    # i controlli consegnati al gate: campi valorizzati, non celle vuote
    assert len(analysis["controls"]) == 6
    for c in analysis["controls"]:
        assert c["e_net_j"] == pytest.approx(0.1)
        assert c["dt_w_s"] == pytest.approx(1.0)
        assert c["window_source"] == "exact-counter"
        assert c["usable"] is True
    assert all(r["block_cooldown_timeout"] == "false"
               for r in analysis["runs"] if r["arm"] == "control")

    # IL VERDETTO: era questo il punto che i run a sei invocazioni non
    # avrebbero mai raggiunto (controlli pieni di richieste e campi vuoti)
    assert analysis["status"] == "pass"
    assert analysis["chain_status"] == ""
    assert analysis["quorum"] == 4 and analysis["controls_usable_n"] == 6
    assert analysis["bias_w"] == pytest.approx(0.1)
    assert analysis["bias_threshold_w"] == pytest.approx(BW)

    # l'artefatto blocks_controllo.json ha la forma letta da
    # ``control_gate.main --blocks``: un terzo puo' rieseguire il gate
    payload = json.loads(
        (rg.ARCHIVE_DIR / rg.BLOCKS_JSON_NAME).read_text(encoding="utf-8"))
    assert len(payload) == 6
    assert all("control_e_net_j" in r for r in payload)

    # il report porta le grandezze derivate, non solo il JSON: E_net/dt_W
    # (0,1 J su 1,0 s nel fake), il conteggio dei pass=False e la baseline
    # propagata contro quella propria del blocco
    report = (rg.ARCHIVE_DIR / rg.REPORT_NAME).read_text(encoding="utf-8")
    assert "E_net/dt_W=0.100000 W" in report
    assert "utilizzabili con block_pass=False: 0/6" in report
    assert "P_pre_ref propagata dal carico=10.0 W" in report
    assert "propria del blocco=10.0 W" in report

    # la serie di potenza grezza: sei finestre dichiarate; il fake non
    # campiona, quindi l'artefatto dice 0 campioni con la ragione, non
    # inventa una serie. La diagnostica non entra nel verdetto.
    serie = json.loads(
        (rg.ARCHIVE_DIR / rg.SERIES_NAME).read_text(encoding="utf-8"))
    assert len(serie) == 6
    for s in serie:
        assert s["n_samples"] == 0 and s["samples"] == []
        assert s["reason"] == "nessun campione nella finestra passiva"
        assert isinstance(s["t0_mono"], float)
        assert isinstance(s["t1_mono"], float)
    assert analysis["series_counts"] == {s["block_id"]: 0 for s in serie}
    assert analysis["control_power_series_json"].endswith(rg.SERIES_NAME)
    assert "serie di potenza grezza dei controlli (JSON)" in report


def test_serie_grezza_salvata_con_potenza_derivata(monkeypatch, tmp_path):
    """Con campioni veri la serie deve portare i cumulati grezzi e la
    potenza derivata ΔE/Δt (5 W su 1 s fra i due campioni del fake), e il
    wrapper deve restituirsi: ``_run_control_window`` del runner torna
    quello di prima e la sessione non resta con un edge method posticcio.
    E' la prova che la cattura e' diagnostica e non tocca il percorso."""
    from energy.energy_session import SystemSample  # noqa: E402

    campioni = [
        SystemSample(t=1001.0, wall=1.0, package_energy_j=1000.0,
                     cpu_busy_seconds=0.0, cpu_percent=1.0),
        SystemSample(t=1002.0, wall=2.0, package_energy_j=1005.0,
                     cpu_busy_seconds=0.0, cpu_percent=1.0),
    ]
    viste: list = []

    def samples(self, a, b):
        viste.append(self)
        return list(campioni)

    monkeypatch.setattr(_SessioneGate, "samples_between", samples)
    reale_cw = v4._run_control_window
    analysis, _spediti, _targets = _esegui_gate(monkeypatch, tmp_path)
    assert v4._run_control_window is reale_cw
    assert viste
    assert all("read_measurement_edge" not in s.__dict__ for s in viste)
    serie = json.loads(
        (rg.ARCHIVE_DIR / rg.SERIES_NAME).read_text(encoding="utf-8"))
    assert len(serie) == 6
    for s in serie:
        assert s["n_samples"] == 2 and s["reason"] == ""
        assert s["samples"][0]["package_energy_j"] == 1000.0
        assert s["samples"][1]["package_energy_j"] == 1005.0
        assert len(s["power_w"]) == 1
        intervallo = s["power_w"][0]
        assert intervallo["dt_s"] == pytest.approx(1.0)
        assert intervallo["de_j"] == pytest.approx(5.0)
        assert intervallo["power_w"] == pytest.approx(5.0)
    assert set(analysis["series_counts"].values()) == {2}


def test_execute_si_ferma_se_il_piano_non_e_pianificato(monkeypatch,
                                                        tmp_path):
    """``execute`` senza ``plan`` deve rifiutarsi: misurare senza disegno
    dichiarato e' esattamente il difetto che P4.4 requisito 5 vuole impedire."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path / "archive")
    monkeypatch.setattr(rg, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_sha256", lambda path: "test-sha")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    _installa(monkeypatch)
    with pytest.raises(SystemExit):
        rg.cmd_execute(rg.DEFAULT_MODEL)


def test_budget_preesecuzione_e_warmup_attraversano_l_orchestrazione(
        monkeypatch, tmp_path):
    """La revisione del gate del 2026-11-09 tocca la regia, non solo i
    moduli: qui si verifica che il fondo venga misurato prima che esista un
    solo blocco di questa campagna, che il warm-up sta' DOPO l'invocazione di
    carico e sul target letto da quel blocco, e che nessuna delle due cose
    sposti il verdetto F.12. I numeri di scala sono nei test dedicati; qui
    sta l'ordine degli eventi, che e' il punto dove il difetto si annida.
    """
    visto_al_gate: list = []
    analysis, _spediti, _targets = _esegui_gate(monkeypatch, tmp_path,
                                                 visto_al_gate)

    # 1. l'artefatto del fondo esiste, e' scritto nell'archivio della
    #    campagna, e dichiara la procedura con le sue chiavi anti-riscalatura
    path = Path(analysis["budget_preregistrato_json"])
    assert path == rg.ARCHIVE_DIR / rg.BUDGET_PREREG_NAME
    assert path.exists()
    fondo = json.loads(path.read_text(encoding="utf-8"))["budget_preregistrato"]
    assert fondo["budget_mode"] == rg.BUDGET_MODE
    assert fondo["tc_duration_s"] == pytest.approx(0.05)
    assert fondo["n_finestre_usate"] == 6
    assert fondo["scala_30_s_applicata"] is False
    assert fondo["codecarbon_usato"] is False
    assert fondo["budget_base_w"] == pytest.approx(BW, abs=1e-6)

    # 2. il fondo precede i blocchi: l'unico ordine in cui una soglia
    #    pre-registrata ha significato
    mtime_fondo = path.stat().st_mtime_ns
    mtime_blocchi = (rg.ARCHIVE_DIR / rg.BLOCKS_JSON_NAME).stat().st_mtime_ns
    assert mtime_fondo <= mtime_blocchi

    # 3. warm-up: presente sui soli carichi, con il target del blocco stesso
    for r in analysis["runs"]:
        if r["arm"] == "load":
            assert r["warmup"] is not None
            assert r["warmup"]["warmup_target_pre_w"] == pytest.approx(
                float(r["block_baseline_pre_w"]))
            assert r["warmup"]["warmup_completed"] is True
            assert r["warmup"]["warmup_motivo"] == "criterio_soddisfatto"
            assert r["warmup"]["warmup_duration_s"] >= 0.0
            assert r["warmup"]["warmup_soglia_cpu_pct"] == pytest.approx(
                rg.WARMUP_CPU_MAX_PCT)
            assert [t["fonte"] for t in
                    r["warmup"]["warmup_temperatura"]] == [
                        "fake:MSAcpi_ThermalZoneTemperature"] * 2
        else:
            assert r["warmup"] is None

    # 3b. il warm-up non diventa mai un blocco e non arriva al gate: le
    #     unita' che ``control_gate.evaluate_gate`` riceve sono esattamente
    #     i sei controlli, e nessuno dei suoi campi compare in quelle tuple.
    #     E' la prova operativa della regola "non e' un controllo, non entra
    #     in bias_w", che altrimenti resterebbe una frase nel docstring.
    assert len(visto_al_gate) == rg.N_COPPIE
    for controllo in visto_al_gate:
        assert not [k for k in controllo if "warmup" in k]
    assert len(analysis["runs"]) == 2 * rg.N_COPPIE
    for r in analysis["runs"]:
        assert not [k for k in r if k.startswith("warmup_")]

    # 4. il verdetto F.12 non si e' spostato: la soglia del criterio resta
    #    la mediana dei budget per blocco, e il numero pre-registrato
    #    viaggia accanto come incertezza dichiarata
    assert analysis["bias_threshold_w"] == pytest.approx(BW)
    assert analysis["budget_pre_esecuzione"]["budget_base_w"] == \
        pytest.approx(analysis["bias_threshold_w"], abs=1e-6)
    inc = analysis["incertezza"]
    assert set(inc) == {"pre_esecuzione", "post_controlli"}
    assert inc["pre_esecuzione"]["u_A"] is None
    assert inc["post_controlli"]["u_A"] == pytest.approx(0.0)
    assert analysis["soglia_preregistrata_w"] == pytest.approx(
        inc["pre_esecuzione"]["soglia_w"])
    assert analysis["status"] == "pass"

    # 5. il report rende leggibile la soglia e le sue componenti: la
    #    tracciabilita' chiesta dalla revisione non deve vivere solo nel
    #    JSON. Le formule sono nel testo, accanto ai valori.
    report = (rg.ARCHIVE_DIR / rg.REPORT_NAME).read_text(encoding="utf-8")
    assert "## Budget pre-registrato e incertezza" in report
    assert "scala 30 s applicata = False" in report
    assert "CodeCarbon usato = False" in report
    assert "### u_c pre-esecuzione" in report
    assert "half_range_pre_w = (max - min) / 2 sulle unita' pre" in report
    assert rg.BUDGET_PREREG_NAME in report
