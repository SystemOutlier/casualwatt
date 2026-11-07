# -*- coding: utf-8 -*-
"""
tests/test_nonce_opzionale_v4.py — Il nonce di P2.8 e il suo unico spegnimento
dichiarato.

Perche' esiste. P2.8 (protocollo_v4_20261024.md:827-839) rende obbligatorio un
nonce a larghezza fissa in testa a ogni prompt, e il runner lo iniettava senza
modo di spegnerlo. Il test B di P2.9 (protocollo:841-856) chiede pero' DUE
bracci sulla stessa richiesta: tre richieste identiche contro tre richieste con
nonce iniziale, per vedere se un prefisso condiviso cambia
``prompt_eval_count``. Senza un braccio senza nonce il confronto non esiste:
il primo braccio misurerebbe sempre un prefisso non riusato, e la domanda del
test resterebbe senza controllo.

Che cosa verifica:
  1. il default resta il nonce: ``build_prompt_v4`` lo inietta e lo
     restituisce con lo sha256 del testo spedito (P2.8 non cambia);
  2. con ``use_nonce=False`` il testo parte **byte-identico** all'originale e
     due sequenze diverse producono lo stesso testo: e' la proprieta' che il
     braccio di controllo deve avere;
  3. un blocco vero eseguito con il nonce spento scrive nella riga
     ``prompt_nonce=off`` con la ragione, e manda al motore il testo grezzo;
     con il nonce acceso scrive il nonce e uno sha256 per richiesta;
  4. ``run_v4_benchmark`` dichiara nel metadata del run quale dei due regimi
     ha usato, perche' la nota di riga non basta a distinguere un braccio di
     diagnostica da una forma di campagna.

Che cosa NON verifica: che il motore riusi davvero il prefisso KV. Quello e'
un esito del test B eseguito contro Ollama reale, non una proprieta' del
runner; qui si verifica solo che i due bracci partano come devono partire.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_unified as bu  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import energy.local_energy as le  # noqa: E402
from energy.worker_tree import WorkerProc  # noqa: E402

T0 = 50.0
WORKER = WorkerProc(7, 1000.0, "ollama.exe")
PRE = [9.9, 10.0, 10.1]
POST = [10.3, 10.4, 10.5]


class _SessioneProfiler:
    """Sessione sintetica per il solo profiler: campioni di package a 10 J/s
    e due bordi qualunque, quanto basta a ``profile_window``."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    _gpu = SimpleNamespace(available=False, index=0, name="")

    def __init__(self):
        self.samples = [
            SimpleNamespace(
                t=T0 + i * 0.5, wall=0.0, package_energy_j=10.0 * i,
                cpu_busy_seconds=2.0 * i, cpu_percent=0.0,
                ollama_pids=(7,), ollama_cpu_seconds=0.5 * i,
                gpu_power_w=None, gpu_util_pct=None,
            )
            for i in range(400)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None,
                                     exclude_windows=None):
        return 50.0


def _edge(t, j, ts):
    return {
        "tree": [WORKER],
        "worker": {WORKER: t},
        "busy": t * 10.0,
        "counter": {"pkg_j": j, "pkg_pwh": j * 100.0, "ts_100ns": ts,
                    "pp1_j": None},
        "counter_error": "",
        "t_wall": t,
        "t_wall_utc": f"2026-10-25T10:00:{t - T0:06.3f}+00:00",
        "t_counter_mono": t,
        "t_cpu_mid": t,
        "edge_spread_s": 0.02,
    }


class _SessioneRunner:
    """Sessione che serve le terne pre/post e bordi sempre crescenti.

    I timestamp del contatore avanzano con i bordi: un registro fermo
    renderebbe la finestra ``counter-invalid`` e la riga non arriverebbe al
    punto che questi test guardano (la nota e il testo spedito).
    """

    running = True
    source_method = "emi-counter"
    source_notes = []
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    calibrated_at = ""
    _gpu = SimpleNamespace(available=False, name="", index=0)

    def __init__(self):
        self.calib = 0
        self.t = T0

    def start(self):
        pass

    def stop(self):
        pass

    def settle_idle(self, *a, **k):
        return 1.0

    def calibrate_idle(self, *a, **k):
        self.calib += 1
        return 10.0 if self.calib == 1 else 10.4

    @property
    def _idle_reps(self):
        return list(PRE if self.calib == 1 else POST)

    def read_measurement_edge(self, **k):
        edge = _edge(self.t, 100.0 + self.t,
                     1_000_000 + int(self.t * 10_000_000))
        self.t += 2.0
        return edge

    def read_ttft_edge(self, t_first_token):
        edge = _edge(self.t, 100.0 + self.t,
                     1_000_000 + int(self.t * 10_000_000))
        edge["t_ttft_mono"] = float(t_first_token)
        return edge


def _prepara(monkeypatch, m):
    """run_block offline: registra i testi spediti e serve m risposte."""
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table",
            timestamp=0.0))
    monkeypatch.setattr(v4, "SESSION", _SessioneRunner())
    spediti = []
    risposte = iter([
        {
            "text": "ok", "prompt_tokens": 100, "completion_tokens": 20,
            "tokens_valid": True, "duration_s": 1.0,
            "prefill_duration_s": 0.2, "decoding_duration_s": 0.5,
            "done_reason": "stop", "raw_created_at": "", "tool_calls": 0,
            "keep_alive_sent": -1, "num_ctx": 8192, "num_predict": 32,
            "_t0": 60.0 + 3.0 * i, "_t1": 61.0 + 3.0 * i,
            "_wall_start": 1.0, "_t_ttft": 60.2 + 3.0 * i,
            "ttft_s": 0.2, "ttft_available": True,
        }
        for i in range(m)
    ])

    def fake_stream(model, text, *a, **k):
        spediti.append(text)
        return dict(next(risposte))

    monkeypatch.setattr(v4, "infer_v4_stream", fake_stream)
    monkeypatch.setattr(v4, "evaluate_response",
                        lambda *a, **k: bu.evalres_placeholder())
    prof = le.CasualWattLocalEnergyProfiler()
    prof.session = _SessioneProfiler()
    return prof, spediti


def _blocco(monkeypatch, m, use_nonce):
    prof, spediti = _prepara(monkeypatch, m)
    rows, summary = v4.run_block(
        "llama", {"id": "p1", "text": "domanda identica",
                  "ground_truth": "21", "source": "manual"},
        run_id="R1", session_id="S1", batch_id="batchA",
        point_id="llama__p1", block_id="llama__p1__b01",
        nonce_seq=0, profiler=prof, m=m, num_predict=32,
        use_nonce=use_nonce)
    return rows, summary, spediti


# ---------------------------------------------------------------------------
# 1-2. build_prompt_v4: default acceso, spegnimento esplicito
# ---------------------------------------------------------------------------
def test_il_default_inietta_il_nonce_e_ne_registra_lo_sha():
    """P2.8: senza argomento il prompt spedito e' ``nonce + testo`` e lo
    sha256 e' quello del testo spedito, non dell'originale. Se lo fosse,
    due richieste diverse solo per il nonce avrebbero lo stesso sha e la
    deduplicazione mentirebbe."""
    prompt = {"id": "p1", "text": "domanda"}
    sent, nonce, sha = v4.build_prompt_v4(prompt, 7)

    assert nonce == "[cw4-00000007]"
    assert sent["text"] == "[cw4-00000007]\ndomanda"
    assert sha == v4.prompt_sha256("[cw4-00000007]\ndomanda")
    assert sha != v4.prompt_sha256("domanda")
    # l'originale non viene mutato: il chiamante puo' riusarlo
    assert prompt["text"] == "domanda"


def test_senza_nonce_il_testo_parte_identico_per_sequenze_diverse():
    """Il braccio di controllo del test B di P2.9 esiste solo se due richieste
    a sequenze diverse spediscono gli stessi byte: e' la proprieta' che
    distingue "prefisso condiviso" da "nonce ignorato"."""
    prompt = {"id": "p1", "text": "domanda"}
    primo, nonce_a, sha_a = v4.build_prompt_v4(prompt, 0, use_nonce=False)
    secondo, nonce_b, sha_b = v4.build_prompt_v4(prompt, 1, use_nonce=False)

    assert primo["text"] == "domanda"
    assert primo["text"] == secondo["text"]
    assert nonce_a == "" and nonce_b == ""
    assert sha_a == sha_b == v4.prompt_sha256("domanda")


# ---------------------------------------------------------------------------
# 3. il blocco vero: cosa parte e cosa resta scritto
# ---------------------------------------------------------------------------
def test_il_blocco_senza_nonce_spedisce_il_grezzo_e_scrive_off(monkeypatch):
    """Con ``use_nonce=False`` le m richieste partono byte-identiche e la nota
    di riga dice ``prompt_nonce=off`` con la ragione: una riga muta sarebbe
    indistinguibile da un nonce che il motore ha perso."""
    rows, _summary, spediti = _blocco(monkeypatch, m=3, use_nonce=False)

    assert spediti == ["domanda identica"] * 3
    for r in rows:
        assert "prompt_nonce=off" in r["notes"]
        assert "prompt_sha256=" + v4.prompt_sha256("domanda identica") \
            in r["notes"]
        assert "num_ctx=8192" in r["notes"]
        assert "num_predict=32" in r["notes"]


def test_il_blocco_con_nonce_spedisce_un_nonce_per_richiesta(monkeypatch):
    """Con il default ogni richiesta ha il proprio nonce, anche con lo stesso
    prompt: il prefisso non e' condiviso per costruzione (P2.8)."""
    rows, _summary, spediti = _blocco(monkeypatch, m=3, use_nonce=True)

    assert spediti == [
        "[cw4-00000000]\ndomanda identica",
        "[cw4-00000001]\ndomanda identica",
        "[cw4-00000002]\ndomanda identica",
    ]
    for i, r in enumerate(rows):
        assert f"prompt_nonce=[cw4-{i:08d}]" in r["notes"]
        assert "prompt_nonce=off" not in r["notes"]


# ---------------------------------------------------------------------------
# 4. il regime usato si legge nel metadata del run
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("use_nonce,atteso,vietato", [
    (False, "nonce=off", "nonce=on"),
    (True, "nonce=on", "nonce=off"),
])
def test_il_metadata_dichiara_il_regime_del_nonce(monkeypatch, use_nonce,
                                                  atteso, vietato):
    """La nota di riga dice cosa e' partito, il metadata dice in che regime
    e' stato fatto il run. Senza il secondo, un braccio di diagnostica
    potrebbe essere scambiato per una campagna, che P2.8 vuole sempre con il
    nonce."""
    monkeypatch.setenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", "1")
    monkeypatch.setenv("CW_V4_SUBSTITUTION_SEED", "nonce-opzionale")
    meta = {}
    visti = []

    def fake_run_block(model, prompt, **kw):
        visti.append(kw["use_nonce"])
        return [], {"batch_id": kw["batch_id"], "point_id": kw["point_id"],
                    "block_id": kw["block_id"], "baseline_pre_w": 11.0,
                    "cooldown_timeout": ""}

    monkeypatch.setattr(v4, "run_block", fake_run_block)
    monkeypatch.setattr(v4, "SESSION", SimpleNamespace(
        running=True, start=lambda: None, stop=lambda: None,
        source_method="emi-counter", source_notes=[], calibrated_at="",
        _gpu=SimpleNamespace(available=False, name="", index=0)))
    monkeypatch.setattr(v4, "export_results_csv",
                        lambda rows, path, mode="a": len(rows))
    monkeypatch.setattr(v4, "export_summary_csv",
                        lambda recs, path, cols, mode="a": len(recs))
    monkeypatch.setattr(v4, "_ollama_runtime_info", lambda model: ("v", "d"))
    monkeypatch.setattr(
        v4, "prepare_machine_state",
        lambda **kw: {"power": {}, "top_processes": [],
                      "cpu_samples_pct": [], "background_load": False,
                      "sampler_interval_s": 0.5})
    monkeypatch.setattr(
        v4, "prepare_model_state",
        lambda model, **kw: {"residency": {"action": "already-resident",
                                           "expires_at": ""},
                             "warmups": []})
    monkeypatch.setattr(
        v4, "probe_machine_state_after",
        lambda **kw: {"top_processes": [], "cpu_samples_pct": [],
                      "background_load": False})
    monkeypatch.setattr(v4.bu, "_ecologits_version", lambda: "")
    monkeypatch.setattr(
        v4.CasualWattLocalEnergyProfiler, "probe_cpu_time_resolution",
        staticmethod(lambda *a, **k: 0.0156))
    monkeypatch.setattr(v4, "write_run_metadata",
                        lambda payload, path: meta.update(payload) or path)

    v4.run_v4_benchmark(
        ["m"], [{"id": "p1", "text": "t1"}],
        blocks_per_point=1, m=1, use_nonce=use_nonce,
        results_path=Path("results/_t_rows_nonce.csv"),
        block_summary_path=Path("results/_t_blocks_nonce.csv"))

    assert visti == [use_nonce]
    assert atteso in meta["notes"]
    assert vietato not in meta["notes"]
