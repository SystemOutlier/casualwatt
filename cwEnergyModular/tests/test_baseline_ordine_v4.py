# -*- coding: utf-8 -*-
"""
tests/test_baseline_ordine_v4.py — L'ordine delle misure di baseline e la
durata che alimenta `budget_base_j` di blocco.

Perche' esiste. P1.5 (protocollo_v4_20261024.md:191-205) congela una sequenza
con un verso: settling, tre finestre da 30 s SENZA richieste, m richieste,
settling, tre finestre post. Se il post venisse calibrato prima delle richieste
la baseline applicata sarebbe contaminata dal carico, e `dP` misurerebbe il
drift di un prima che non esiste. F.11 (protocollo:1631, :1644, :1651, :2178)
congela anche il numero che alimenta il budget di blocco: `Δt̄_W,b = (1/m)·Σ
Δt_W,i`, la **media aritmetica** di `duration_s`, e lo dice due volte "la media
per blocco della `duration_s` gia' prevista". Il runner la calcolava come
**mediana** delle `dt_W_s` dei bordi: due statistiche diverse su due campi
diversi, e `budget_base_j,c` e` u_base,b` (che ci passa) escono di un fattore
che dipende dalle durate del blocco, non dalla formula.

Che cosa verifica:
  1. l'ordine reale: settle → calibrazione pre → m coppie di bordi → settle →
     calibrazione post, con le repliche pre che alimentano `baseline_pre_w` e
     le post che alimentano `baseline_post_w` (mai scambiate);
  2. `dP = mediana(post) − mediana(pre)` sul blocco, e `budget_base_w` in
     quadratura (formule gia' coperte in test_block_baseline.py: qui si
     verifica che il blocco le usi);
  3. il `budget_base_j` del riepilogo e' `budget_base_w × media aritmetica di
     duration_s`, e non la mediana delle `dt_W_s` (le tre candidate sono
     rese diverse di proposito: durate 1/2/100 con Δt_W = durata + 10);
  4. `budget_base_j` della riga usa la `Δt_W` di QUELLA richiesta (F.4);
  5. quando la media non e' calcolabile (una durata assente o non finita su
     m richieste) il campo di blocco resta VUOTO con il perche' nella nota, e
     una riga senza `Δt_W` non riceve uno zero inventato;
  6. `Δt̄_W,b` e' dichiarato nella nota di riga, perche' non ha colonna
     (P6.5:2178 lo vuole "quantita' derivata" dichiarata da P5).

Che cosa NON verifica: la sostituzione del blocco invalidato per guasto
tecnico del contatore (Emenda 8, P1.6, recepita 2026-10-26: invalidazione
alla PRIMA occorrenza -- nessuna finestra ripetuta ne' nel runner ne' in
`calibrate_idle`, che infatti solleva alla prima anomalia,
energy/energy_session.py:2547-2566 -- e un solo blocco sostitutivo
dello stesso punto in posizione sorteggiata col seme dichiarato). Quella
regola e' verificata in tests/test_emenda8_sostituzione.py; qui sta la
sola sequenza dei blocchi validi. La vecchia "discrepanza dichiarata" fra
testo congelato (retry per finestra, protocollo:221-222) e codice e'
chiusa dall'emenda a favore del codice: non e' piu' una lacuna.
"""
import inspect
import math
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

# terne che rendono le tre statistiche distinte: pre mediana 10,0 range 0,2,
# post mediana 10,4 drift 0,4 -> budget_base_w = hypot(0,1 ; 0,2)
PRE = [9.9, 10.0, 10.1]
POST = [10.3, 10.4, 10.5]
BW = round(math.hypot(0.1, 0.2), 6)


class _Sessione:
    """Sessione sintetica per il solo profiler: i campioni servono alla quota
    di tempo CPU, non alla baseline (che qui e' iniettata)."""

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
            for i in range(300)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None):
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


def _prepara_blocco(monkeypatch, durate):
    """run_block offline: finge la sessione, ritorna l'ordine delle chiamate.

    Ogni richiesta ha `duration_s` = `durate[i]` e una finestra dei bordi di
    `durate[i] + 10` secondi: le due grandezze sono diverse per disegno, cosi'
    una media sull'una invece che sull'altra si vede.
    """
    ordine = []
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table",
            timestamp=0.0))

    bordi = []
    for i, d in enumerate(durate):
        a = T0 + 4.0 * i
        bordi.append(_edge(a, 100.0 + 10.0 * i, 1_000_000 + int(a * 10_000_000)))
        # la finestra del bordo e' durata + 10 s: +10 in avanti
        dt_bordo = float(d) + 10.0 if isinstance(d, (int, float)) and \
            math.isfinite(d) else 11.0
        bordi.append(_edge(a + dt_bordo, 150.0 + 10.0 * i,
                           1_000_000 + int((a + dt_bordo) * 10_000_000)))

    class _SessioneRunner:
        """Sessione che registra l'ordine e serve le terne pre/post al momento
        giusto: `_idle_reps` dipende da quante calibrazioni sono avvenute."""

        running = True
        source_method = "emi-counter"
        source_notes: list = []
        interval_s = 0.5
        idle_power_w = 10.0
        idle_provenance = "calibrated"
        calibrated_at = ""
        _gpu = SimpleNamespace(available=False, name="", index=0)

        def __init__(self):
            self.calib = 0
            self._it = iter(bordi)

        def start(self):
            pass

        def stop(self):
            pass

        def settle_idle(self, *a, **k):
            ordine.append("settle")
            return 1.0

        def calibrate_idle(self, *a, **k):
            self.calib += 1
            ordine.append("calib")
            return 10.0 if self.calib == 1 else 10.4

        @property
        def _idle_reps(self):
            return list(PRE if self.calib == 1 else POST)

        def read_measurement_edge(self, **k):
            ordine.append("bordo")
            return next(self._it)

    fake = _SessioneRunner()
    monkeypatch.setattr(v4, "SESSION", fake)

    risposte = iter([
        {
            "text": "risposta", "prompt_tokens": 100, "completion_tokens": 20,
            "tokens_valid": True, "duration_s": d,
            "prefill_duration_s": 0.2, "decoding_duration_s": 1.0,
            "done_reason": "stop", "raw_created_at": "", "tool_calls": 0,
            "keep_alive_sent": "-1", "num_ctx": 8192, "num_predict": 160,
            "_t0": T0 + 4.0 * i + 0.2, "_t1": T0 + 4.0 * i + 1.2,
            "_wall_start": 1.0,
        }
        for i, d in enumerate(durate)
    ])
    monkeypatch.setattr(v4, "infer_v4", lambda *a, **k: dict(next(risposte)))
    monkeypatch.setattr(v4, "evaluate_response",
                        lambda *a, **k: bu.evalres_placeholder())

    prof = le.CasualWattLocalEnergyProfiler()
    prof.session = _Sessione()
    return prof, ordine


def _blocco(monkeypatch, durate, m=None):
    prof, ordine = _prepara_blocco(monkeypatch, durate)
    rows, summary = v4.run_block(
        "llama", {"id": "p1", "text": "domanda", "ground_truth": "21",
                  "source": "manual"},
        run_id="R1", session_id="S1", batch_id="batchA",
        point_id="llama__p1", block_id="llama__p1__b01",
        nonce_seq=0, profiler=prof, m=m or len(durate))
    return rows, summary, ordine


# ---------------------------------------------------------------------------
# 1. ordine P1.5
# ---------------------------------------------------------------------------
def test_l_ordine_del_blocco_e_quello_di_p15(monkeypatch):
    """settle, calibrazione pre, m coppie di bordi, settle, calibrazione post:
    due sole calibrazioni, e nessuna lettura di bordo prima della pre."""
    _rows, _summary, ordine = _blocco(monkeypatch, [1.0, 2.0, 3.0])

    assert ordine == ["settle", "calib"] + ["bordo", "bordo"] * 3 \
        + ["settle", "calib"]
    assert ordine.count("calib") == 2


def test_le_repliche_pre_e_post_non_si_scambiano(monkeypatch):
    """`pre_windows_w` porta le terne lette PRIMA delle richieste e
    `post_windows_w` quelle dopo; `baseline_pre_w` e' la mediana delle prime."""
    _rows, summary, _ordine = _blocco(monkeypatch, [1.0, 2.0, 3.0])

    assert summary["pre_windows_w"] == "9.900000;10.000000;10.100000"
    assert summary["post_windows_w"] == "10.300000;10.400000;10.500000"
    assert summary["baseline_pre_w"] == pytest.approx(10.0)
    assert summary["baseline_post_w"] == pytest.approx(10.4)
    assert summary["dP"] == pytest.approx(0.4)
    assert summary["pre_range_w"] == pytest.approx(0.2)
    assert summary["half_range_pre_w"] == pytest.approx(0.1)
    assert summary["half_drift_w"] == pytest.approx(0.2)
    assert summary["budget_base_w"] == pytest.approx(BW)


def test_il_post_e_diagnostico_e_non_sposta_la_baseline_applicata(monkeypatch):
    """P1.14: la riga porta `baseline_pre_w` come potenza applicata; il post
    arriva dopo, e `budget_base_w` e' l'unica combinazione che lo contiene."""
    rows, summary, _ordine = _blocco(monkeypatch, [1.0, 2.0, 3.0])

    assert rows[0]["baseline_pre_w"] == pytest.approx(10.0)
    assert rows[0]["idle_power_w"] == pytest.approx(10.0)
    assert rows[0]["dP"] == pytest.approx(0.4)
    assert summary["budget_base_w"] == pytest.approx(
        math.hypot(summary["half_range_pre_w"], summary["half_drift_w"]))


# ---------------------------------------------------------------------------
# 2-3. Δt̄_W,b: media aritmetica di duration_s
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("durate,atteso", [
    ([1.0, 2.0, 4.0], round(7.0 / 3.0, 6)),
    ([2.0], 2.0),
    ([0.0, 0.0], 0.0),          # zero letto: valore, non assenza
    ([1.5, 1.5, 1.5, 1.5], 1.5),
])
def test_block_mean_e_la_media_aritmetica(durate, atteso):
    """`(1/m)·Σ` su `duration_s` (F.11), non una mediana e non una somma."""
    righe = [{"duration_s": d} for d in durate]
    val, motivo = v4.block_mean_duration_s(righe, len(durate))
    assert motivo == ""
    assert val == pytest.approx(atteso)


@pytest.mark.parametrize("righe,m,motivo_parte", [
    ([{"duration_s": 1.0}, {"duration_s": ""}, {"duration_s": 3.0}], 3,
     "2 durate su 3"),
    ([{"duration_s": 1.0}, {"duration_s": 2.0}], 3, "2 durate su 3"),
    ([{"duration_s": float("nan")}, {"duration_s": 2.0}], 2, "1 durate su 2"),
    ([{"duration_s": 1.0}], 0, "m=0"),
    ([{"duration_s": 1.0}], "tre", "non numerico"),
])
def test_block_mean_lascia_vuoto_quando_non_e_calcolabile(righe, m,
                                                          motivo_parte):
    """Denominatore diverso da m o durata mancante: cella vuota e motivo, mai
    una media su cio' che resta spacciata per `(1/m)·Σ`."""
    val, motivo = v4.block_mean_duration_s(righe, m)
    assert val == ""
    assert motivo_parte in motivo


def test_budget_di_blocco_usa_la_media_non_la_mediana(monkeypatch):
    """Durate 1/2/100: media aritmetica 34,333333, mediana 2, mediana delle
    Δt_W 12. Il riepilogo deve riportare il prodotto con la prima."""
    _rows, summary, _ordine = _blocco(monkeypatch, [1.0, 2.0, 100.0])

    assert summary["budget_base_j"] == pytest.approx(
        round(34.333333 * BW, 6))
    assert summary["budget_base_j"] != pytest.approx(round(2.0 * BW, 6))
    assert summary["budget_base_j"] != pytest.approx(round(12.0 * BW, 6))
    assert v4.block_mean_duration_s(
        [{"duration_s": d} for d in (1.0, 2.0, 100.0)], 3)[0] == pytest.approx(
        34.333333)


def test_budget_di_riga_usa_la_propria_delta_w(monkeypatch):
    """F.4: la riga moltiplica la propria `Δt_W` (che e' durata + 10 nel
    disegno di questo test), non la media di blocco."""
    rows, _summary, _ordine = _blocco(monkeypatch, [1.0, 2.0, 100.0])

    for i, d in enumerate([1.0, 2.0, 100.0]):
        assert rows[i]["dt_W_s"] == pytest.approx(d + 10.0)
        assert rows[i]["budget_base_j"] == pytest.approx(
            round((d + 10.0) * BW, 6))


def test_dt_bar_dichiarata_nella_nota_perche_non_ha_colonna(monkeypatch):
    """P6.5:2178 vieta una colonna nuova per `Δt̄_W,b` e chiede a P5 di
    dichiararla come quantita' derivata: il valore usato deve essere leggibile
    da chi ricava il budget di blocco."""
    rows, summary, _ordine = _blocco(monkeypatch, [1.0, 2.0, 100.0])

    assert "Δt̄_W,b=34.333333 s" in rows[0]["notes"]
    assert "media aritmetica di 3 duration_s" in rows[0]["notes"]
    assert "non la mediana" in rows[0]["notes"]
    assert summary["budget_base_j"] == pytest.approx(
        v4.budget_base_j(34.333333, summary["budget_base_w"]))


def test_media_non_calcolabile_lascia_la_cella_vuota_e_lo_dice(monkeypatch):
    """Una durata non finita su m=3: `(1/m)·Σ` non esiste, il campo resta ""
    e la nota dice perche'. Zero qui sarebbe un budget dichiarato nullo."""
    rows, summary, _ordine = _blocco(
        monkeypatch, [1.0, 2.0, float("nan")])

    assert summary["budget_base_j"] == ""
    assert "budget_base_j di blocco non calcolabile" in rows[0]["notes"]
    assert "2 durate su 3" in rows[0]["notes"]
    # le righe restano calcolabili con la propria Δt_W: la media di blocco non
    # e' una precondizione del budget per richiesta
    assert rows[0]["budget_base_j"] == pytest.approx(round(11.0 * BW, 6))


def test_una_riga_senza_delta_w_non_riceve_un_budget_zero(monkeypatch):
    """La regola "cella vuota, non zero": se la finestra della richiesta non
    e' espressa, `budget_base_j` di riga resta vuoto invece di diventare
    0,0 J = "baseline consuma nulla"."""
    prof, ordine = _prepara_blocco(monkeypatch, [1.0])
    reale = prof.profile_window

    def che_perde_la_finestra(*a, **k):
        res = reale(*a, **k)
        res.dt_W_s = ""
        return res

    prof.profile_window = che_perde_la_finestra
    rows, _summary = v4.run_block(
        "llama", {"id": "p1", "text": "domanda", "source": "manual"},
        run_id="R1", session_id="S1", batch_id="batchA",
        point_id="llama__p1", block_id="llama__p1__b01",
        nonce_seq=0, profiler=prof, m=1)

    assert rows[0]["dt_W_s"] in ("", None)
    assert rows[0]["budget_base_j"] == ""
    assert ordine.count("calib") == 2


def test_il_runner_non_usa_piu_la_mediana_per_dt_bar():
    """Regressione sull'espressione che sbagliava formula: la mediana delle
    `dt_W_s` era usata come `Δt̄_W,b`. La mediana resta legittima per le
    repliche di baseline, non per la durata di blocco."""
    src = inspect.getsource(v4.run_block)
    assert "statistics.median(iters)" not in src
    assert "block_mean_duration_s(rows, m)" in src


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
