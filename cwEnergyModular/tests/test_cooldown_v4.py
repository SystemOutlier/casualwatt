# -*- coding: utf-8 -*-
"""
tests/test_cooldown_v4.py — Il cooldown fra i punti di P1.5.

Perche' esiste. Il protocollo congelato (protocollo_v4_20261024.md:210-212)
impone un criterio DISTINTO da quello del settling: "la media a 10 s rientra
entro 0,5 W da P_pre per 10 s, con tetto 120 s; se il tetto viene raggiunto, si
procede e si marca cooldown_timeout". Il settling guarda la stazionarieta'
(due finestre consecutive che differiscono); il cooldown guarda la vicinanza a
un riferimento. Le due cose non sono interscambiabili e il runner le
implementa separatamente. Senza test, la differenza si perde e il gate
temporale resta un if dentro un loop che nessuno ha guardato: qui sotto c'e'
il caso in cui il tratto di permanenza si azzera a meta', che e' esattamente
il punto dove "per 10 s" smette di essere un commento.

Che cosa verifica:
  1. i quattro parametri del criterio sono quelli del testo, non parametri
     inventati dal codice;
  2. raggiungimento: "per 10 s" e' permanenza continua, non somma di campioni;
  3. tolleranza stretta (< 0,5 W) come in energy_session.py:2400 — a 0,5 W
     esatti la condizione NON e' soddisfatta;
  4. timeout: al tetto si ritorna con timed_out=True e waited_s = tetto, e si
     procede perche' il tetto non invalida il blocco;
  5. dati mancanti: None non e' 0,0 W e si conta; un riferimento P_pre assente
     o non positivo rende il cooldown non eseguibile (cella vuota, non "false");
  6. limiti temporali: interruzione del tratto, completamento esattamente al
     tetto, un campione oltre e' timeout, passo che non supera mai il residuo,
     cancellazione fra due campioni;
  7. cablaggio del runner: il cooldown corre solo sul primo blocco di ogni
     punto, col riferimento dell'ultima baseline_pre_w completata, e il primo
     punto del run non ce l'ha.

Che cosa NON verifica: se la macchina reale rientri entro 0,5 W entro 120 s.
Quello e' un fatto di campagna (P6.1/P6.2), non una proprieta' verificabile
offline; qui si verifica la meccanica del criterio e come viene dichiarata.
"""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402


# ---------------------------------------------------------------------------
# Driver deterministico: il tempo passa solo quando il cooldown chiede di
# dormire, cosi' le attese sono contabili senza orologi reali.
# ---------------------------------------------------------------------------
class FakeClock:
    def __init__(self, t0: float = 1000.0):
        self.t = float(t0)
        self.slept = []

    def clock(self) -> float:
        return self.t

    def sleep(self, dt: float) -> None:
        assert dt >= 0.0, "un sleep negativo e' tempo che torna indietro"
        self.slept.append(float(dt))
        self.t += float(dt)


def power_sequence(values):
    """Lettura che consuma ``values`` e ripete l'ultimo quando finiscono."""
    state = {"i": 0, "calls": 0}

    def fn():
        value = values[min(state["i"], len(values) - 1)]
        state["i"] += 1
        state["calls"] += 1
        return value

    fn.state = state
    return fn


def run(target=10.0, values=(10.2,), **kw):
    """Cooldown con clock e sleep finti, parametri di protocollo default."""
    clk = FakeClock()
    read = power_sequence(list(values))
    out = v4.cooldown_to_baseline(target, power_fn=read,
                                  clock=clk.clock, sleep=clk.sleep, **kw)
    return out, clk, read


# ---------------------------------------------------------------------------
# 1. Parametri congelati
# ---------------------------------------------------------------------------
def test_parametri_congelati_del_criterio():
    """P1.5:210-212 dice 10 s, 0,5 W, 10 s di permanenza, tetto 120 s."""
    assert v4.COOLDOWN_WINDOW_S == 10.0
    assert v4.COOLDOWN_TOLERANCE_W == 0.5
    assert v4.COOLDOWN_SUSTAIN_S == 10.0
    assert v4.COOLDOWN_CAP_S == 120.0
    # Il passo di osservazione NON e' una soglia di protocollo: resta
    # dichiarato come cadenza, e coincide col default di settle_idle.
    assert v4.COOLDOWN_STEP_S == 1.0


# ---------------------------------------------------------------------------
# 2. Raggiungimento
# ---------------------------------------------------------------------------
def test_raggiungimento_richiede_la_permanenza_continua():
    """Media sempre dentro: il criterio si chiude a 10 s, non al primo
    campione entro tolleranza."""
    out, clk, _read = run(target=10.0, values=[10.2])

    assert out["ran"] is True
    assert out["reached"] is True
    assert out["timed_out"] is False
    assert out["waited_s"] == pytest.approx(10.0)
    assert out["samples"] == 11                  # t = 0..10 a passo 1
    assert out["missing_reads"] == 0
    assert sum(clk.slept) == pytest.approx(10.0)
    assert v4.cooldown_timeout_flag(out) == "false"
    assert "consecutivi" in out["reason"]


def test_tratto_interrotto_riparte_da_capo():
    """Un campione fuori tolleranza azzera il tratto: i 10 s ripartono da li',
    perche' "per 10 s" e' un continuo, non una somma."""
    out, _clk, _read = run(target=10.0, values=[10.2] * 5 + [10.9] + [10.2])
    assert out["reached"] is True
    # fuori a t=5, ripartenza a t=6, permanenza 10 s -> chiusura a t=16
    assert out["waited_s"] == pytest.approx(16.0)


# ---------------------------------------------------------------------------
# 3. Tolleranza stretta
# ---------------------------------------------------------------------------
def test_soglia_esatta_non_soddisfa():
    """0,5 W tondi NON sono "entro 0,5 W": disuguaglianza stretta, la stessa
    convenzione del settling (energy_session.py:2400)."""
    out_timeout, _clk, _r = run(target=10.0, values=[10.5])
    assert out_timeout["reached"] is False
    assert out_timeout["timed_out"] is True

    out_ok, _clk2, _r2 = run(target=10.0, values=[10.4999])
    assert out_ok["reached"] is True

    # e vale in entrambe le direzioni: anche 9,5 W e' fuori
    out_low, _clk3, _r3 = run(target=10.0, values=[9.5])
    assert out_low["timed_out"] is True


# ---------------------------------------------------------------------------
# 4. Timeout
# ---------------------------------------------------------------------------
def test_tetto_raggiunto_si_procede_e_si_marca():
    """Sempre fuori tolleranza: timed_out, waited_s = 120 s, flag "true". Il
    protocollo dice "si procede", quindi il tetto non e' un errore."""
    out, clk, read = run(target=10.0, values=[20.0])

    assert out["ran"] is True
    assert out["reached"] is False
    assert out["timed_out"] is True
    assert out["waited_s"] == pytest.approx(120.0)
    assert read.state["calls"] == 121            # t = 0..120 a passo 1
    assert sum(clk.slept) == pytest.approx(120.0)
    assert v4.cooldown_timeout_flag(out) == "true"
    assert "tetto" in out["reason"]
    assert "cooldown_timeout=true" in out["reason"]


# ---------------------------------------------------------------------------
# 5. Dati mancanti
# ---------------------------------------------------------------------------
def test_letture_mancanti_non_sono_zero_watt():
    """Contatore che non esprime una lettura: None, non 0,0 W. Le letture si
    contano e il cooldown va al tetto senza dirsi mai soddisfatto."""
    out, _clk, _read = run(target=10.0, values=[None])
    assert out["ran"] is True
    assert out["reached"] is False
    assert out["timed_out"] is True
    assert out["missing_reads"] == out["samples"] == 121
    assert "letture mancanti=121" in out["reason"]

    # un NaN e' una lettura mancante esattamente come un None
    out_nan, _c2, _r2 = run(target=10.0, values=[float("nan")])
    assert out_nan["missing_reads"] == out_nan["samples"] == 121

    # e una lettura mancante azzera il tratto, come un campione fuori soglia
    out_mix, _c3, _r3 = run(target=10.0, values=[10.2] * 5 + [None] + [10.2])
    assert out_mix["reached"] is True
    assert out_mix["waited_s"] == pytest.approx(16.0)
    assert out_mix["missing_reads"] == 1


@pytest.mark.parametrize("bad", [None, "", 0.0, -5.0, float("nan"),
                                 float("inf"), "ciao"])
def test_riferimento_non_valido_rende_il_cooldown_non_eseguibile(bad):
    """Senza P_pre non c'e' criterio: il loop non parte nemmeno, e la cella
    resta vuota perche' "false" affermerebbe un cooldown riuscito."""
    clk = FakeClock()
    calls = {"n": 0}

    def read():
        calls["n"] += 1
        return 10.2

    out = v4.cooldown_to_baseline(bad, power_fn=read,
                                  clock=clk.clock, sleep=clk.sleep)
    assert out["ran"] is False
    assert out["reached"] is False
    assert out["timed_out"] is False
    assert out["waited_s"] is None
    assert calls["n"] == 0
    assert clk.slept == []
    assert v4.cooldown_timeout_flag(out) == ""
    assert "non eseguibile" in out["reason"]


def test_flag_vuoto_senza_dizionario():
    """Nessun cooldown invocato (primo punto del run) e' cella vuota: non
    "false", non "true"."""
    assert v4.cooldown_timeout_flag(None) == ""
    assert v4.cooldown_timeout_flag({}) == ""
    assert v4.cooldown_timeout_flag({"ran": False, "timed_out": True}) == ""
    assert v4.cooldown_timeout_flag({"ran": True, "timed_out": False}) == "false"
    assert v4.cooldown_timeout_flag({"ran": True, "timed_out": True}) == "true"


# ---------------------------------------------------------------------------
# 6. Limiti temporali
# ---------------------------------------------------------------------------
def test_completamento_esattamente_al_tetto_conta_come_raggiunto():
    """Il criterio si chiude a 120 s tondi: la verifica della condizione viene
    prima di quella del tetto, quindi "compiuto al tetto" e' raggiunto."""
    out, _clk, _read = run(target=10.0, values=[20.0] * 110 + [10.0])
    assert out["reached"] is True
    assert out["timed_out"] is False
    assert out["waited_s"] == pytest.approx(120.0)


def test_un_campione_di_attesa_oltre_il_tetto_e_timeout():
    """Stessa forma con ripartenza a t=111: servirebbero 121 s, il tetto e'
    120 e il tratto non si chiude. Il confine e' il tetto, non il loop."""
    out, _clk, _read = run(target=10.0, values=[20.0] * 111 + [10.0])
    assert out["reached"] is False
    assert out["timed_out"] is True
    assert out["waited_s"] == pytest.approx(120.0)


def test_passo_non_overshoota_il_tetto():
    """L'ultimo sonno si accorcia al residuo: mai dormire oltre il tetto."""
    out, clk, _read = run(target=10.0, values=[20.0], window_s=1.0,
                          sustain_s=1.0, cap_s=15.0, step_s=10.0)
    assert out["timed_out"] is True
    assert out["waited_s"] == pytest.approx(15.0)
    assert clk.slept == [10.0, 5.0]
    assert out["samples"] == 3


def test_stop_event_interrompe_il_cooldown():
    """La cancellazione dell'operatore non e' un timeout: esce con
    _Cancelled e non marca cooldown_timeout."""
    ev = threading.Event()
    ev.set()
    clk = FakeClock()
    with pytest.raises(v4._Cancelled):
        v4.cooldown_to_baseline(10.0, power_fn=power_sequence([10.2]),
                                clock=clk.clock, sleep=clk.sleep,
                                stop_event=ev)
    assert clk.slept == []


class _ContatoreCheLegge:
    """Backend che espone solo il metodo usato dal cooldown di default."""

    def __init__(self, energy=100.0, raises=False):
        self.energy = energy
        self.raises = raises
        self.seen = []

    def package_energy_exact_between(self, a, b, excl=None):
        self.seen.append((a, b))
        if self.raises:
            raise RuntimeError("backend chiuso")
        return self.energy


def test_percorso_di_default_usa_la_finestra_di_10_s_del_contatore(monkeypatch):
    """100 J sulla finestra di 10 s fanno 10,0 W: la media mobile del cooldown
    e' energia esatta divisa la durata, non una media di campioni."""
    src = _ContatoreCheLegge(energy=100.0)
    monkeypatch.setattr(v4, "SESSION", src)
    clk = FakeClock()
    out = v4.cooldown_to_baseline(10.0, clock=clk.clock, sleep=clk.sleep)

    assert out["reached"] is True
    assert len(src.seen) == 11
    for a, b in src.seen:
        assert b - a == pytest.approx(v4.COOLDOWN_WINDOW_S)


def test_percorso_di_default_degrada_dichiarando(monkeypatch):
    """Lettura assente o eccezione del backend: nessuna potenza, quindi tutte
    le letture mancanti e tetto raggiunto. Una lettura che fallisce non diventa
    mai 0,0 W (che contro un P_pre basso sarebbe "rientrato")."""
    for src in (_ContatoreCheLegge(energy=None),
               _ContatoreCheLegge(raises=True)):
        monkeypatch.setattr(v4, "SESSION", src)
        clk = FakeClock()
        out = v4.cooldown_to_baseline(10.0, clock=clk.clock, sleep=clk.sleep)
        assert out["reached"] is False
        assert out["timed_out"] is True
        assert out["missing_reads"] == 121


# ---------------------------------------------------------------------------
# 7. Cablaggio nel runner: il cooldown sta fra i punti
# ---------------------------------------------------------------------------
class _RunSession:
    """Sessione minima per far girare il solo ciclo dei punti: niente start,
    niente contatore, niente GPU."""

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


def _stub_run(monkeypatch, cooldown_fn):
    """Prepara run_v4_benchmark senza hardware: ritorna i record di chiamata.

    Emenda 8 (P1.6): K e seme non hanno default e il runner senza di essi si
    rifiuta di partire -- qui arrivano dall'ambiente, la stessa via che la
    produzione usera', cosi' ogni chiamata di questo file passa il gate senza
    inventarsi un tetto."""
    monkeypatch.setenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", "1")
    monkeypatch.setenv("CW_V4_SUBSTITUTION_SEED", "cooldown-test")
    calls = []
    blocks = []

    def fake_cooldown(target, **kw):
        calls.append(target)
        return cooldown_fn(target)

    def fake_run_block(model, prompt, **kw):
        blocks.append(kw)
        return [], {
            "batch_id": kw["batch_id"], "point_id": kw["point_id"],
            "block_id": kw["block_id"], "baseline_pre_w": 11.0,
            "cooldown_timeout": v4.cooldown_timeout_flag(kw.get("cooldown")),
        }

    meta = {}

    monkeypatch.setattr(v4, "cooldown_to_baseline", fake_cooldown)
    monkeypatch.setattr(v4, "run_block", fake_run_block)
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
    return calls, blocks, meta


def _not_executed(target):
    return {"ran": False, "reached": False, "timed_out": False,
            "waited_s": None, "target_pre_w": "", "samples": 0,
            "missing_reads": 0,
            "reason": "cooldown non eseguibile: nessun P_pre di riferimento"}


def _timed_out(target):
    return {"ran": target is not None, "reached": False,
            "timed_out": target is not None, "waited_s": 120.0,
            "target_pre_w": target if target is not None else "",
            "samples": 121, "missing_reads": 0,
            "reason": "tetto di 120 s raggiunto; si procede e si marca "
                      "cooldown_timeout=true"}


def test_il_runner_chiama_il_cooldown_solo_ai_confini_dei_punti(monkeypatch):
    """Due punti x due blocchi: quattro blocchi, due invocazioni (una per
    punto), riferimento = ultima baseline_pre_w completata, e il riferimento
    arriva a run_block insieme al flag nel riepilogo."""
    calls, blocks, meta = _stub_run(monkeypatch, _timed_out)
    out = v4.run_v4_benchmark(
        ["m"], [{"id": "p1", "text": "t1"}, {"id": "p2", "text": "t2"}],
        blocks_per_point=2, m=1,
        results_path=Path("results/_cooldown_rows.csv"),
        block_summary_path=Path("results/_cooldown_blocks.csv"))

    assert out["blocks"] == 4
    # due punti, quindi due invocazioni: la prima senza riferimento
    assert calls == [None, 11.0]
    first_of_point = [kw for kw in blocks
                      if kw["block_id"].endswith("b01")]
    assert len(first_of_point) == 2
    assert all(kw.get("cooldown") is not None for kw in first_of_point)
    assert all(kw.get("cooldown") is None for kw in blocks
               if not kw["block_id"].endswith("b01"))
    # il riferimento del secondo punto e' la baseline del blocco precedente
    assert first_of_point[1]["cooldown"]["target_pre_w"] == 11.0


def test_cooldown_timeout_arriva_nel_riepilogo_di_blocco(monkeypatch):
    """Il flag marcato dal protocollo sta nella colonna del riepilogo: "true"
    dal secondo punto, vuoto al primo perche' non c'era riferimento."""
    _calls, _blocks, meta = _stub_run(monkeypatch, _timed_out)
    blocks = []

    def spy_run(model, prompt, **kw):
        blocks.append(kw)
        return [], {"point_id": kw["point_id"], "block_id": kw["block_id"],
                    "baseline_pre_w": 11.0,
                    "cooldown_timeout": v4.cooldown_timeout_flag(
                        kw.get("cooldown"))}

    monkeypatch.setattr(v4, "run_block", spy_run)
    v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"},
                                {"id": "p2", "text": "t2"}],
                        blocks_per_point=1, m=1,
                        results_path=Path("results/_a.csv"),
                        block_summary_path=Path("results/_b.csv"))
    flags = [kw["cooldown"]["ran"] for kw in blocks]
    assert flags == [False, True]


def test_il_primo_punto_del_run_dichiara_il_senso_cooldown(monkeypatch):
    """Un punto solo: nessun confine con riferimento, quindi nessuna voce di
    cooldown nel metadata e la nota che lo dichiara."""
    _calls, _blocks, meta = _stub_run(monkeypatch, _not_executed)
    v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"}],
                        blocks_per_point=1, m=1,
                        results_path=Path("results/_c.csv"),
                        block_summary_path=Path("results/_d.csv"))

    assert "cooldown: nessun confine" in meta["notes"]
    assert "media 10 s entro 0.5 W" in meta["notes"]
    assert "passo 1 s" in meta["notes"]


def test_i_singoli_cooldown_finiscono_nei_metadata(monkeypatch):
    """Il riferimento e il tempo atteso non stanno nel CSV di blocco (nessuna
    colonna), quindi devono essere recuperabili dal run metadata: senza di
    essi cooldown_timeout="true" non e' verificabile da un terzo."""
    _calls, _blocks, meta = _stub_run(monkeypatch, _timed_out)
    v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"},
                                {"id": "p2", "text": "t2"}],
                        blocks_per_point=1, m=1,
                        results_path=Path("results/_e.csv"),
                        block_summary_path=Path("results/_f.csv"))

    assert "target_pre_w=11.0 W" in meta["notes"]
    assert "waited_s=120.0" in meta["notes"]
    assert "cooldown_timeout=true" in meta["notes"]
    # il primo punto non produce una voce: nessun cooldown eseguito
    assert meta["notes"].count("target_pre_w=") == 1


def test_il_blocco_espone_il_parametro_cooldown():
    """Il ciclo dei punti e `run_block` sono testati separatamente perche' il
    blocco richiede hardware e rete; se il nome del parametro diverge, il
    cooldown smette di arrivare nel riepilogo senza che cada nulla. Questa e'
    l'unica verifica economica del contratto fra i due."""
    import inspect

    params = inspect.signature(v4.run_block).parameters
    assert "cooldown" in params
    assert params["cooldown"].kind is inspect.Parameter.KEYWORD_ONLY
    assert params["cooldown"].default is None
    assert '"cooldown_timeout": cd_flag' in inspect.getsource(v4.run_block)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
