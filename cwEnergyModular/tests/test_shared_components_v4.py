# -*- coding: utf-8 -*-
"""
tests/test_shared_components_v4.py — D6: i due runner non divergono.

Perche' esiste. La campagna v4 vive in ``benchmark_v4.py`` e non tocca il
percorso di produzione ``benchmark_unified.py`` (vincolo esplicito). Il
rischio di due runner paralleli e' che il secondo cloni una funzione e la
faccia evolvere per conto suo: a quel punto i numeri dei due percorsi non
sono piu' confrontabili, e nessun test cade. Qui si verifica che i componenti
condivisi siano gli STESSI oggetti, che i campi scritti esistano nello schema,
e che la sequenza di un blocco passi davvero da quei componenti.

Che cosa verifica:
  1. identita' dei componenti condivisi: sessione, profiler, valutatore,
     costruttore di riga, finalizzazione, export, costruttore del payload;
  2. tutti i campi che la v4 scrive esistono in ``CSV_COLUMNS`` (un campo
     fuori schema verrebbe scartato in silenzio da ``extrasaction="ignore"``);
  3. il payload v4 e' quello di produzione PIU' ``num_ctx`` e ``keep_alive``:
     nessuna chiave storica cambiata;
  4. ``infer_v4`` non stima i token (P2.6): contatori assenti -> campi vuoti e
     ``tokens_valid=False``;
  5. un blocco completo offline passa da ``_basic_record`` e
     ``_finalize_energy_fields`` di produzione, e il riepilogo ha esattamente
     lo schema congelato del lotto 2;
  6. le chiavi di collegamento (``batch_id``, ``point_id``, ``block_id``)
     sono le stesse nella riga e nel riepilogo (D3).

Che cosa NON verifica: che i due runner producano numeri uguali (le sequenze
sono diverse per disegno: la v4 aggiunge settling e baseline di blocco).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_unified as bu  # noqa: E402
import casualwatt_csv_export as cx  # noqa: E402
import energy.energy_session as es  # noqa: E402
import energy.local_energy as le  # noqa: E402
import evaluator  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
from energy.worker_tree import WorkerProc  # noqa: E402

T0 = 50.0
WORKER = WorkerProc(7, 1000.0, "ollama.exe")


class _Sessione:
    """Sessione sintetica sui tempi dei bordi finti (50-52 s)."""

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
            for i in range(5)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
        return 50.0


def _edge(t, cpu_mid, j, ts, worker_cpu, busy):
    return {
        "tree": [WORKER],
        "worker": {WORKER: worker_cpu},
        "busy": busy,
        "counter": {"pkg_j": j, "pkg_pwh": j * 100.0, "ts_100ns": ts,
                    "pp1_j": None},
        "counter_error": "",
        "t_wall": t,
        "t_wall_utc": f"2026-10-25T10:00:{t - T0:06.3f}+00:00",
        "t_counter_mono": t,
        "t_cpu_mid": cpu_mid,
        "edge_spread_s": 0.02,
    }


def _evalres():
    """Placeholder di produzione: la stessa forma che usa il runner reale."""
    return bu.evalres_placeholder()


# ------------------------------------------------------------------ 1
def test_componenti_condivisi_sono_gli_stessi_oggetti():
    """Se un runner clona una funzione, questo test cade."""
    assert v4.bu is bu
    assert v4.evaluate_response is evaluator.evaluate_response
    assert v4.export_results_csv is cx.export_results_csv
    assert v4.export_summary_csv is cx.export_summary_csv
    assert v4.write_run_metadata is cx.write_run_metadata
    assert v4.SESSION is es.SESSION
    assert v4.CasualWattLocalEnergyProfiler is le.CasualWattLocalEnergyProfiler
    assert v4.MEASURED_METHODS is es.MEASURED_METHODS


# ------------------------------------------------------------------ 2
def test_ogni_campo_scritto_dalla_v4_esiste_nello_schema():
    """Un campo fuori da CSV_COLUMNS sarebbe perso senza errore."""
    for col in v4.ENERGY_ROW_FIELDS:
        assert col in cx.CSV_COLUMNS, f"campo energetico fuori schema: {col}"

    local = le.LocalEnergyResult()
    for col in v4.energy_fields(local, ""):
        assert col in cx.CSV_COLUMNS, f"campo di energy_fields fuori schema: {col}"

    for col in v4.judge_fields(None, [], 10.0):
        if col.startswith("_"):
            continue  # chiavi private, tolte prima dell'export
        assert col in cx.CSV_COLUMNS, f"campo del giudice fuori schema: {col}"

    extra = (
        "input_tokens", "output_tokens", "total_tokens", "tokens_per_second",
        "prefill_duration_s", "decoding_duration_s",
        "decoding_tokens_per_second", "model_response", "timestamp_start",
        "timestamp_end", "duration_s", "tool_calls", "eval_mode",
        "is_correct", "causal_accuracy", "explanation_quality",
        "cosine_similarity", "n_correct_links", "acc_comp", "answer_type",
        "extracted_answer", "notes", "keep_alive_sent",
        "engine_tree_changed", "tree_identity_start", "tree_identity_end",
        "tree_born", "tree_lost", "batch_id", "point_id", "block_id",
        "tokens_level", "n_inferenze",
        "judge_energy_j", "judge_window_s",
    )
    for col in extra:
        assert col in cx.CSV_COLUMNS, f"campo della riga fuori schema: {col}"


# ------------------------------------------------------------------ 3
def test_payload_v4_e_produzione_piu_due_parametri(monkeypatch):
    """Nessuna chiave storica cambiata: la v4 aggiunge solo num_ctx e keep_alive."""
    called = []
    real = bu._ollama_payload

    def _spy(*a, **k):
        called.append((a, k))
        return real(*a, **k)

    monkeypatch.setattr(bu, "_ollama_payload", _spy)

    prod = real("llama", "testo", 0.2, 16)
    made = v4.payload_v4("llama", "testo", 0.2, 16)

    assert called, "il payload v4 deve partire dal costruttore di produzione"
    assert made["keep_alive"] == "-1"
    assert made["options"]["num_ctx"] == 8192
    strip = {k: val for k, val in made.items() if k != "keep_alive"}
    strip["options"] = {k: val for k, val in strip["options"].items()
                        if k != "num_ctx"}
    assert strip == prod


# ------------------------------------------------------------------ 4
def test_infer_v4_non_stima_i_token(monkeypatch):
    """P2.6: senza prompt_eval_count/eval_count i campi restano vuoti."""
    sent = {}

    def _post(url, json=None, timeout=None):
        sent.update(json or {})
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"response": "ok", "done_reason": "stop"},
        )

    monkeypatch.setattr(v4.requests, "post", _post)

    out = v4.infer_v4("llama", "testo", 0.2, 5.0)
    assert out["prompt_tokens"] == ""
    assert out["completion_tokens"] == ""
    assert out["tokens_valid"] is False
    assert sent["keep_alive"] == "-1"
    assert sent["options"]["num_ctx"] == 8192

    def _post_con_conteggi(url, json=None, timeout=None):
        return SimpleNamespace(
            status_code=200,
            raise_for_status=lambda: None,
            json=lambda: {"response": "ok", "prompt_eval_count": 12,
                          "eval_count": 5, "done_reason": "stop"},
        )

    monkeypatch.setattr(v4.requests, "post", _post_con_conteggi)
    out = v4.infer_v4("llama", "testo", 0.2, 5.0)
    assert out["prompt_tokens"] == 12
    assert out["completion_tokens"] == 5
    assert out["tokens_valid"] is True


# ------------------------------------------------------------------ 5, 6
def test_un_blocco_offline_passa_dai_componenti_di_produzione(monkeypatch):
    """La sequenza P1.5 usa _basic_record/_finalize di produzione e lo schema lotto 2."""
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table",
            timestamp=0.0))

    calls = {"basic": 0, "finalize": 0}
    real_basic = bu._basic_record
    real_fin = bu._finalize_energy_fields

    def _basic(*a, **k):
        calls["basic"] += 1
        return real_basic(*a, **k)

    def _fin(*a, **k):
        calls["finalize"] += 1
        return real_fin(*a, **k)

    monkeypatch.setattr(bu, "_basic_record", _basic)
    monkeypatch.setattr(bu, "_finalize_energy_fields", _fin)

    # calibrazione pre 10,0 W e post 10,4 W, con le tre repliche
    pre = [9.9, 10.0, 10.1]
    post = [10.3, 10.4, 10.5]
    values = iter([10.0, 10.4])

    def _calibrate(*a, **k):
        v = next(values)
        reps = list(pre if v == 10.0 else post)
        # monkeypatch, non setattr diretto: la sessione e' un singleton e le
        # repliche non devono sopravvivere al test
        monkeypatch.setattr(es.SESSION, "_idle_reps", reps, raising=False)
        return v

    monkeypatch.setattr(es.SESSION, "settle_idle", lambda *a, **k: 0.0)
    monkeypatch.setattr(es.SESSION, "calibrate_idle", _calibrate)

    # due bordi per la sola richiesta del blocco (m=1): counter 100 -> 150 J,
    # ts 2,0 s, worker 10,0 -> 12,0 s, busy 100 -> 108 s
    edges = iter([
        _edge(50.0, 50.1, 100.0, 10_000_000, 10.0, 100.0),
        _edge(52.0, 52.3, 150.0, 30_000_000, 12.0, 108.0),
    ])
    monkeypatch.setattr(es.SESSION, "read_measurement_edge", lambda **k: next(edges))

    resp = {
        "text": "risposta", "prompt_tokens": 100, "completion_tokens": 20,
        "tokens_valid": True, "duration_s": 1.6,
        "prefill_duration_s": 0.2, "decoding_duration_s": 1.4,
        "done_reason": "stop", "raw_created_at": "", "tool_calls": 0,
        "keep_alive_sent": "-1", "num_ctx": 8192, "num_predict": 160,
        "_t0": 50.2, "_t1": 51.8, "_wall_start": 1.0,
    }
    monkeypatch.setattr(v4, "infer_v4", lambda *a, **k: dict(resp))

    seen = {}

    def _evaluate(*a, **k):
        seen["judge_fn"] = k.get("judge_fn")
        return _evalres()

    monkeypatch.setattr(v4, "evaluate_response", _evaluate)

    prof = le.CasualWattLocalEnergyProfiler()
    prof.session = _Sessione()
    prompt = {"id": "p1", "text": "domanda", "ground_truth": "21",
              "source": "manual"}

    rows, block = v4.run_block(
        "llama", prompt,
        run_id="R1", session_id="S1", batch_id="batchA",
        point_id="llama__p1", block_id="llama__p1__b01",
        nonce_seq=0, profiler=prof, m=1,
    )

    # 5) i componenti di produzione sono stati chiamati davvero
    assert calls == {"basic": 1, "finalize": 1}
    assert seen["judge_fn"] is not None

    assert len(rows) == 1
    row = rows[0]

    # 2) nessun campo AGGIUNTO dalla v4 resta fuori schema. I campi che
    # _basic_record di produzione scrive gia' e che l'export scarta
    # (extrasaction="ignore", es. triples_*) sono ereditati: non sono una
    # divergenza introdotta dal runner v4 e il test non glieli attribuisce.
    prod_keys = set(real_basic(
        "R1", "S1", "llama", "llama", "ollama", "local", None,
        prompt, _evalres()))
    added = set(row) - prod_keys
    dropped = sorted(k for k in added if k not in cx.CSV_COLUMNS)
    assert dropped == [], f"campi aggiunti dalla v4 e fuori schema: {dropped}"

    # 6) chiavi stabili uguali in riga e riepilogo
    for key in ("batch_id", "point_id", "block_id"):
        assert row[key] == block[key] == {
            "batch_id": "batchA", "point_id": "llama__p1",
            "block_id": "llama__p1__b01"}[key]
    assert row["tokens_level"] == "per-request"
    assert row["n_inferenze"] == 1

    # energia e attribuzione dalla riga (bordi finti)
    assert row["package_energy_j"] == pytest.approx(50.0)
    assert row["baseline_pre_w"] == pytest.approx(10.0)
    assert row["baseline_energy_j"] == pytest.approx(20.0)  # 10 W x 2 s
    assert row["active_energy_j"] == pytest.approx(30.0)
    assert row["d_ollama_cpu_s"] == pytest.approx(2.0)
    assert row["d_busy_s"] == pytest.approx(8.0)
    assert row["cpu_time_share"] == pytest.approx(0.25)
    assert row["ollama_active_energy_j"] == pytest.approx(7.5)
    assert row["cpu_time_share_valid"] is True
    assert row["emi_edge_source"] == "direct-ioctl"
    assert row["engine_tree_changed"] is False
    assert row["tree_identity_start"] == "7:1000.000000"

    # baseline post: diagnostica, non applicata
    assert row["baseline_post_w"] == pytest.approx(10.4)
    assert row["dP"] == pytest.approx(0.4)
    assert row["half_range_pre_w"] == pytest.approx(0.1)
    assert row["half_drift_w"] == pytest.approx(0.2)
    assert row["budget_base_w"] == pytest.approx((0.1 ** 2 + 0.2 ** 2) ** 0.5)
    assert row["budget_base_j"] == pytest.approx(
        2.0 * (0.1 ** 2 + 0.2 ** 2) ** 0.5)

    # Emenda 8 (P1.6): la timbratura delle tre colonne nuove SU OGNI riga di
    # un blocco completato e' responsabilita' di run_block, non del runner
    # (il runner marca solo fault.rows). invalid_reason vuoto qui e'
    # "costruzione": il blocco reale che arriva in fondo non e' invalidato.
    assert row["block_attempt"] == 1
    assert row["invalid_reason"] == ""
    assert row["replaced_block_id"] == ""

    # riepilogo: schema congelato, campi di analisi vuoti, cooldown non inventato
    assert list(block) == cx.BLOCK_SUMMARY_COLUMNS
    assert block["block_kind"] == "campaign"
    assert block["negative_increment"] == "false"
    assert block["block_attempt"] == 1
    assert block["invalid_reason"] == ""
    assert block["replaced_block_id"] == ""
    for key in ("u_edge_j", "r_A", "r_B", "cooldown_timeout",
                "design_deviation"):
        assert block[key] == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
