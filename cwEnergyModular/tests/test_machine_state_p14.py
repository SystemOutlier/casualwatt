# -*- coding: utf-8 -*-
"""
tests/test_machine_state_p14.py — gli obblighi di stato macchina di P1.4.

Perche' esiste. Il protocollo congelato (``protocollo_v4_20261024.md:218-228``)
elenca sette obblighi che precedono ogni misura: modello caricato con
``keep_alive=-1`` e verificato residente su ``/api/ps``; due warm-up a
``(512,128)`` scartati; GUI di LibreHardwareMonitor chiusa; alimentatore
collegato con piano energetico e batteria registrati; sampler alla cadenza
della misura; top-5 processi e CPU totale prima e dopo, con
``background_load`` se la CPU totale resta sopra il 5% per 3 s; nessuna
sottrazione del costo dell'osservatore. P4.4 requisito 6 li richiede identici
anche sul blocco di controllo. Fino a questo file il runner v4 implementava
P1.5 e non P1.4: la sequenza di blocco era fedele, lo stato della macchina no,
e nessun artefatto lo avrebbe detto.

Che cosa verifica:
  1. la residenza si **verifica** su ``/api/ps`` e non si deduce dal fatto che
     il modello sia stato nominato; un modello gia' residente non si ricarica;
  2. il caricamento usa la forma numerica ``keep_alive=-1`` (la stringa
     produce ``400 time: missing unit in duration``) e dopo il 200 la
     residenza si rilegge: un caricamento che non lascia il modello in
     memoria solleva;
  3. il tag implicito ``:latest`` non fa fallire il confronto;
  4. i due warm-up sono due, a ``num_predict=128`` e ``num_ctx=8192``, con
     ``keep_alive=-1``, e restituiscono i conteggi del motore invece di una
     stima: i token del warm-up non si deducono dalla lunghezza del testo;
  5. ``background_load`` richiede TRE campioni consecutivi sopra soglia, non
     un picco: e' la permanenza che contamina la baseline;
  6. host a batteria e GUI aperta FERMANO il run (``MachineStateError``);
     un desktop senza batteria non e' un "collegato" dedotto;
  7. nel runner i tre punti di ingresso sono attraversati davvero e le
     dichiarazioni finiscono in ``notes`` — la sola sede che lo schema P5
     congelato lascia a una quantita' senza colonna;
  8. la preparazione del modello e' per modello e avviene prima dei suoi
     blocchi: il caricamento di un secondo modello puo' scacciare il primo,
     quindi uno stato letto a inizio run non direbbe nulla sui blocchi dopo;
  9. un errore nello stato FINALE non butta via il run: le righe sono gia'
     scritte e l'errore resta dichiarato.

Che cosa NON verifica: il motore Ollama reale e il contatore energetico
(qui sono finti: il canale hardware e' provato da ``diagnostics.py`` e
``tests/test_calibrazione.py``), la cadenza effettiva del sampler (verificata
in ``energy_session``), e il costo dell'osservatore della GUI, che P1.4
dichiara non sottratto proprio perche' la GUI si chiude.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
import machine_state as ms  # noqa: E402


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = {} if payload is None else payload

    def json(self):
        return self._payload


def _ps(*names):
    return {"models": [{"name": n, "size_vram": 100,
                        "expires_at": "2318-01-01T00:00:00Z"} for n in names]}


# ---------------------------------------------------------------------------
# 1. residenza verificata su /api/ps
# ---------------------------------------------------------------------------
def test_modello_gia_residente_non_viene_ricaricato(monkeypatch):
    """P1.4: la residenza si VERIFICA. Se ``/api/ps`` lo elenca, il POST di
    caricamento non deve partire: ricaricarlo sarebbe una scrittura inutile
    sullo stato che si sta dichiarando."""
    calls = []
    monkeypatch.setattr(ms.requests, "get",
                        lambda url, timeout=0: _Resp(200, _ps("m:1b")))
    monkeypatch.setattr(
        ms.requests, "post",
        lambda url, json=None, timeout=0: calls.append(json) or _Resp(200, {}))

    out = ms.ensure_resident("m:1b", api_url="http://f", num_ctx=8192)

    assert out["action"] == "already-resident"
    assert out["expires_at"].startswith("2318")
    assert calls == []


def test_modello_non_residente_viene_caricato_con_keep_alive_numerico(monkeypatch):
    """P1.4 e la forma che il motore accetta: ``keep_alive=-1`` INTERO, non la
    stringa ``"-1"`` (Ollama 0.33.1 risponde 400 alla stringa). Dopo il POST
    la residenza si rilegge: il 200 non e' la prova."""
    posts = []
    reads = iter([_ps(), _ps("m:1b")])
    monkeypatch.setattr(ms.requests, "get",
                        lambda url, timeout=0: _Resp(200, next(reads)))
    monkeypatch.setattr(
        ms.requests, "post",
        lambda url, json=None, timeout=0: posts.append(json) or _Resp(200, {}))

    out = ms.ensure_resident("m:1b", api_url="http://f", num_ctx=8192)

    assert out["action"] == "loaded"
    assert len(posts) == 1
    assert posts[0]["keep_alive"] == -1
    assert not isinstance(posts[0]["keep_alive"], str)
    assert posts[0]["options"]["num_ctx"] == 8192


def test_caricamento_che_non_lascia_il_modello_residente_solleva(monkeypatch):
    """Un POST che risponde 200 e non lascia il modello in memoria non e' lo
    stato di P1.4: il run non parte invece di misurare un modello freddo."""
    monkeypatch.setattr(ms.requests, "get",
                        lambda url, timeout=0: _Resp(200, _ps()))
    monkeypatch.setattr(ms.requests, "post",
                        lambda url, json=None, timeout=0: _Resp(200, {}))

    with pytest.raises(ms.MachineStateError, match="non risulta residente"):
        ms.ensure_resident("m:1b", api_url="http://f", num_ctx=8192)


def test_tag_latest_implicito_non_confonde_la_residenza(monkeypatch):
    """Ollama omette ``:latest``: ``qwen2.5`` e ``qwen2.5:latest`` sono lo
    stesso modello, e un confronto testuale farebbe ricaricare (o rifiutare)
    un modello che e' gia' in memoria."""
    monkeypatch.setattr(ms.requests, "get",
                        lambda url, timeout=0: _Resp(200, _ps("qwen2.5:latest")))
    monkeypatch.setattr(
        ms.requests, "post",
        lambda *a, **k: pytest.fail("non deve caricare"))

    out = ms.ensure_resident("qwen2.5", api_url="http://f", num_ctx=8192)
    assert out["action"] == "already-resident"
    assert ms.same_model("qwen2.5", "qwen2.5:latest")
    assert not ms.same_model("qwen2.5:0.5b", "qwen2.5:latest")


# ---------------------------------------------------------------------------
# 2. due warm-up a (512,128), scartati, con i conteggi del motore
# ---------------------------------------------------------------------------
def test_due_warmup_a_512_128_scartati(monkeypatch):
    """P1.4: "due warm-up a (512,128), scartati". Scartati vuol dire fuori
    dai dati, non fuori dall'artefatto: i conteggi del motore tornano al
    chiamante, che li scrive nella nota del run."""
    posts = []
    monkeypatch.setattr(
        ms.requests, "post",
        lambda url, json=None, timeout=0: posts.append(json) or _Resp(
            200, {"done": True, "prompt_eval_count": 512,
                  "eval_count": 128, "total_duration": 10 ** 9}))

    out = ms.warmup("m:1b", api_url="http://f", num_ctx=8192)

    assert len(posts) == 2
    for payload in posts:
        assert payload["keep_alive"] == -1
        assert payload["options"]["num_predict"] == 128
        assert payload["options"]["num_ctx"] == 8192
        assert payload["stream"] is False
        assert len(payload["prompt"].split()) >= ms.WARMUP_N_IN
    assert [w["prompt_eval_count"] for w in out] == [512, 512]
    assert [w["eval_count"] for w in out] == [128, 128]


# ---------------------------------------------------------------------------
# 3. top-5 processi
# ---------------------------------------------------------------------------
class _Proc:
    def __init__(self, pid, name, value):
        self.info = {"pid": pid, "name": name}
        self._value = value

    def cpu_percent(self, _interval=None):
        return self._value


def test_top_processi_ordinati_e_troncati(monkeypatch):
    """P1.4 chiede i primi cinque: l'elenco e' ordinato per CPU decrescente,
    troncato a cinque e senza il pid 0, che su Windows e' il tempo inattivo
    ("System Idle Process") e non un processo concorrente: lasciarlo in cima
    renderebbe illeggibile proprio la dichiarazione che P1.4 chiede."""
    procs = [_Proc(0, "System Idle Process", 900.0)] + [
        _Proc(i, f"p{i}", v) for i, v in
        enumerate([1.0, 40.0, 7.5, 90.0, 0.0, 12.0, 3.0], start=1)]
    monkeypatch.setattr(ms.psutil, "process_iter",
                        lambda attrs=None: iter(procs))

    rows = ms.sample_top_processes(window_s=0.0)

    assert [r["cpu_pct"] for r in rows] == [90.0, 40.0, 12.0, 7.5, 3.0]
    assert all(r["pid"] != 0 for r in rows)
    assert len(rows) == 5


def test_cpu_totale_campionata_a_intervalli(monkeypatch):
    """La CPU totale si legge come media fra due campioni (P1.4: "prima e
    dopo"), quindi i campioni sono almeno due e sono numeri, non booleani."""
    values = iter([10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0])
    monkeypatch.setattr(ms.psutil, "cpu_percent",
                        lambda _interval=None: next(values, 80.0))

    samples = ms.total_cpu_samples(duration_s=0.03, interval_s=0.005)

    assert len(samples) >= 2
    assert all(isinstance(s, float) for s in samples)


# ---------------------------------------------------------------------------
# 4. background_load: tre campioni consecutivi sopra soglia
# ---------------------------------------------------------------------------
def test_background_load_richiede_tre_campioni_consecutivi():
    """P1.4: "se la CPU totale resta sopra il 5% per 3 s". Tre campioni a 1 s
    consecutivi sopra soglia sono tre secondi; due no, e una media alta con
    un buco no: il criterio e' la permanenza, non il livello medio."""
    assert ms.background_load_from_samples([1.0, 6.0, 7.0, 8.0, 2.0]) is True
    assert ms.background_load_from_samples([6.0, 7.0, 2.0, 6.0, 7.0]) is False
    assert ms.background_load_from_samples([1.0, 2.0, 3.0]) is False
    assert ms.background_load_from_samples([]) is False
    # il confine: esattamente 5% non e' "sopra il 5%"
    assert ms.background_load_from_samples([5.0, 5.0, 5.0]) is False


# ---------------------------------------------------------------------------
# 5. alimentazione, piano energetico, GUI LHM
# ---------------------------------------------------------------------------
def test_piano_energetico_e_batteria_registrati(monkeypatch):
    """P1.4: alimentatore collegato, piano energetico invariato e registrato,
    stato batteria registrato. Le tre voci tornano come le da' il sistema."""
    monkeypatch.setattr(ms.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        ms.subprocess, "run",
        lambda *a, **k: SimpleNamespace(
            stdout="Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  "
                   "(Bilanciato)\n"))
    monkeypatch.setattr(
        ms.psutil, "sensors_battery",
        lambda: SimpleNamespace(power_plugged=True, percent=97.5))

    state = ms.power_state()

    assert "Bilanciato" in state["plan"]
    assert state["battery"] == "present"
    assert state["power_plugged"] is True
    assert state["battery_percent"] == 97.5


def test_host_a_batteria_non_parte(monkeypatch):
    """P1.4 chiede l'alimentatore collegato: una misura presa a batteria non
    e' quella congelata, e il run si ferma con la causa invece di proseguire
    e dichiararlo dopo."""
    monkeypatch.setattr(
        ms.psutil, "sensors_battery",
        lambda: SimpleNamespace(power_plugged=False, percent=42.0))

    with pytest.raises(ms.MachineStateError, match="batteria"):
        ms.require_ac_power()


def test_desktop_senza_batteria_non_e_un_collegamento_dedotto(monkeypatch):
    """Su un host senza batteria la condizione non e' decidibile: lo stato e'
    ``absent`` e non un ``collegato`` inventato."""
    monkeypatch.setattr(ms.psutil, "sensors_battery", lambda: None)

    state = ms.require_ac_power()

    assert state["battery"] == "absent"
    assert state["power_plugged"] is None


def test_gui_lhm_aperta_ferma_il_run(monkeypatch):
    """P1.4: la GUI si chiude, e il suo costo (0,2-0,9 W) non si sottrae.
    Con la GUI aperta il run non parte: sottrarre sarebbe arbitrario e
    ignorarla renderebbe il costo un pezzo non dichiarato della misura."""
    procs = [_Proc(1, "chrome.exe", 0.0),
             _Proc(2, "LibreHardwareMonitor.exe", 0.0)]
    monkeypatch.setattr(ms.psutil, "process_iter",
                        lambda attrs=None: iter(procs))

    found = ms.lhm_processes()
    assert [p["pid"] for p in found] == [2]
    with pytest.raises(ms.MachineStateError, match="LibreHardwareMonitor"):
        ms.require_lhm_closed()


# ---------------------------------------------------------------------------
# 6. cablaggio nel runner
# ---------------------------------------------------------------------------
class _RunSession:
    running = True
    interval_s = 0.001
    source_method = "emi-counter"
    source_notes = []
    calibrated_at = ""
    _gpu = SimpleNamespace(available=False, name="", index=0)

    def start(self):
        pass

    def stop(self):
        pass


def _stub_run(monkeypatch, *, after_raises=False):
    """run_v4_benchmark senza hardware ne' motore: i tre punti d'ingresso di
    P1.4 sono finti e registrano l'ordine. K e seme dall'ambiente perche'
    Emenda 8 li rende obbligatori."""
    monkeypatch.setenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", "1")
    monkeypatch.setenv("CW_V4_SUBSTITUTION_SEED", "p14-test")
    order = []
    meta = {}

    def fake_before(**kw):
        order.append(("before",))
        return {"power": {"plan": "Bilanciato", "battery": "absent",
                          "power_plugged": None, "battery_percent": None},
                "top_processes": [{"pid": 9, "name": "python.exe",
                                   "cpu_pct": 3.0}],
                "cpu_samples_pct": [1.0, 2.0, 1.5],
                "background_load": False,
                "sampler_interval_s": 0.001}

    def fake_model(model, **kw):
        order.append(("model", model))
        return {"residency": {"action": "already-resident",
                              "expires_at": "2318-01-01T00:00:00Z"},
                "warmups": [{"repeat": 1, "prompt_eval_count": 512,
                             "eval_count": 128},
                            {"repeat": 2, "prompt_eval_count": 512,
                             "eval_count": 128}]}

    def fake_after(**kw):
        order.append(("after",))
        if after_raises:
            raise RuntimeError("psutil non risponde")
        return {"top_processes": [], "cpu_samples_pct": [2.0, 2.5, 3.0],
                "background_load": False}

    def fake_run_block(model, prompt, **kw):
        order.append(("block", model, kw["block_id"]))
        return [], {"batch_id": kw["batch_id"], "point_id": kw["point_id"],
                    "block_id": kw["block_id"], "baseline_pre_w": 11.0}

    monkeypatch.setattr(v4, "prepare_machine_state", fake_before)
    monkeypatch.setattr(v4, "prepare_model_state", fake_model)
    monkeypatch.setattr(v4, "probe_machine_state_after", fake_after)
    monkeypatch.setattr(v4, "run_block", fake_run_block)
    # Il cooldown e' della sequenza P1.5, non dello stato macchina: qui non
    # corre, altrimenti il secondo punto aspetterebbe fino al tetto di 120 s.
    monkeypatch.setattr(
        v4, "cooldown_to_baseline",
        lambda target, **kw: {"ran": False, "reached": False,
                              "timed_out": False, "waited_s": None,
                              "target_pre_w": "", "samples": 0,
                              "missing_reads": 0, "reason": "test"})
    monkeypatch.setattr(v4, "SESSION", _RunSession())
    monkeypatch.setattr(v4, "export_results_csv",
                        lambda rows, path, mode="a": len(rows))
    monkeypatch.setattr(v4, "export_summary_csv",
                        lambda recs, path, cols, mode="a": len(recs))
    monkeypatch.setattr(v4, "_ollama_runtime_info", lambda model: ("v", "d"))
    monkeypatch.setattr(v4.bu, "_ecologits_version", lambda: "")
    monkeypatch.setattr(
        v4.CasualWattLocalEnergyProfiler, "probe_cpu_time_resolution",
        staticmethod(lambda *a, **k: 0.0156))
    monkeypatch.setattr(v4, "write_run_metadata",
                        lambda payload, path: meta.update(payload) or path)
    return order, meta


def test_il_runner_attraversa_i_tre_punti_e_li_dichiara_nel_metadata(monkeypatch):
    """P1.4 non e' un modulo di analisi: deve stare SUL percorso. Lo stato
    iniziale precede il primo blocco, quello del modello lo precede per
    modello, quello finale segue l'ultimo; le quantita' senza colonna
    arrivano in ``notes``, l'unica sede che lo schema P5 congelato lascia."""
    order, meta = _stub_run(monkeypatch)

    v4.run_v4_benchmark(
        ["m"], [{"id": "p1", "text": "t1"}], blocks_per_point=2, m=1,
        results_path=Path("results/_p14_rows.csv"),
        block_summary_path=Path("results/_p14_blocks.csv"))

    assert order[0] == ("before",)
    assert order[1] == ("model", "m")
    assert order[-1] == ("after",)
    assert sum(1 for step in order if step[0] == "block") == 2
    notes = meta["notes"]
    assert "P1.4 stato iniziale" in notes
    assert "GUI LibreHardwareMonitor assente" in notes
    assert "sampler=0.001 s" in notes
    assert "P1.4 m: residente=already-resident" in notes
    assert "warm-up (512,128) scartati" in notes
    assert "P1.4 top-5 prima" in notes
    assert "P1.4 top-5 dopo" in notes
    assert "background_load=False" in notes
    assert f"tre finestre consecutive da {v4.IDLE_WINDOW_S:.0f} s" in notes


def test_lo_stato_del_modello_e_per_modello_e_una_volta_sola(monkeypatch):
    """Il piano e' ordinato per modello: la preparazione avviene prima del
    PRIMO blocco di ciascun modello e non si ripete. Ripeterla a ogni blocco
    rifarebbe due warm-up da (512,128) dentro la campagna; farla una volta a
    inizio run, con due modelli, dichiarerebbe residente un modello che il
    secondo caricamento puo' aver scacciato."""
    order, _meta = _stub_run(monkeypatch)

    v4.run_v4_benchmark(
        ["m1", "m2"], [{"id": "p1", "text": "t1"}], blocks_per_point=2, m=1,
        results_path=Path("results/_p14_rows.csv"),
        block_summary_path=Path("results/_p14_blocks.csv"))

    model_steps = [step for step in order if step[0] == "model"]
    assert model_steps == [("model", "m1"), ("model", "m2")]
    first_block_m1 = order.index(("block", "m1", "m1__p1__b01"))
    first_block_m2 = order.index(("block", "m2", "m2__p1__b01"))
    assert order.index(("model", "m1")) < first_block_m1
    assert order.index(("model", "m2")) < first_block_m2


def test_un_errore_nello_stato_finale_non_butta_via_il_run(monkeypatch):
    """Le righe sono gia' scritte quando lo stato finale si legge: un errore
    del probe non puo' trasformare una campagna eseguita in un'eccezione. Il
    fatto resta dichiarato in ``notes``."""
    _order, meta = _stub_run(monkeypatch, after_raises=True)

    out = v4.run_v4_benchmark(
        ["m"], [{"id": "p1", "text": "t1"}], blocks_per_point=1, m=1,
        results_path=Path("results/_p14_rows.csv"),
        block_summary_path=Path("results/_p14_blocks.csv"))

    assert out["blocks"] == 1
    assert out["errors"] == 0
    assert "P1.4 stato finale non rilevato: RuntimeError" in meta["notes"]
