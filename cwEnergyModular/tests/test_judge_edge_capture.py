# -*- coding: utf-8 -*-
"""
tests/test_judge_edge_capture.py — I bordi del segmento del giudice (D2).

Perche' esiste. D2 impegna il runner a una cosa sola: l'energia del segmento
del giudice viene dalla DIFFERENZA DEL CONTATORE letta ai due bordi della
chiamata, e quando questo non e' possibile si torna all'interpolazione del
buffer LO DICHIARO in un campo (`judge_energy_edge_source`). Il "non e'
possibile" ha quattro facce diverse — contatore assente, timestamp non
crescente, Δt indisponibile, stesso record letto due volte — e tutte e quattro
finiscono dentro lo stesso `buffer-interp` se nessuno le distingue. Un revisore
che vede `buffer-interp` deve poter capire perche'.

C'e' anche un difetto di forma, verificato qui: `read_counter_edge()` espone
l'istante della lettura come `t_mono`, mentre il helper condiviso `_edge_dt_w`
legge `t_counter_mono` (il nome che gli da' `read_measurement_edge()`). Due
produttori, due nomi, un consumatore: senza normalizzazione il secondo ramo di
`_edge_dt_w` non e' mai raggiungibile dai bordi del giudice.

Che cosa verifica:
  1. la forma del bordo: `t_counter_mono` esposto, Δt sulla base corretta;
  2. priorita' `emi-counter-ts` e valore = ΔE − P_pre·Δt sulla STESSA coppia;
  3. record duplicato (stesso timestamp ai bordi) NON diventa 0,0 J;
  4. contatore assente, valore non crescente (reset), Δt assente: ciascuno
     con la propria ragione, e il segmento degrada intero, non a meta';
  5. timestamp non monotono ma base monotona disponibile: si usa la monotona;
  6. `judge_edge_spread_s` e' il costo di UNA lettura, `judge_window_s` la
     durata del segmento: numeri diversi, e un test che non li lasci confondere;
  7. la nota di tracciabilita' riporta grezzo del contatore ed estensione dei
     bordi, perche' il valore diretto sia ricalcolabile da un terzo.

Che cosa NON verifica: che il contatore EMI si muova davvero entro i 250 ms
di una chiamata del giudice (fatto di campagna), ne' la correttezza assoluta
della scala del registro (non arbitrata, stesso MSR 0x611).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler as Profiler  # noqa: E402


# ---------------------------------------------------------------------------
# Costruttori di bordi nella forma reale di read_counter_edge()
# ---------------------------------------------------------------------------
def edge(pkg_j=None, ts=None, pwh=None, t_mono=None, utc="t-utc",
         via_capture=True):
    """Bordo nell'esatta forma di ``EnergySession.read_counter_edge``.

    ``t_mono`` e' l'istante preso PRIMA dell'IOCTL, come fa la sessione; il
    record del contatore porta ``ts_100ns`` e il valore grezzo ``pkg_pwh``.
    Con ``via_capture=True`` (default) il bordo passa dalla normalizzazione
    che il wrapper applica a tutti i bordi letti dalla sessione: costruire i
    bordi a mano senza di essa significherebbe testare una forma che il runner
    non produce mai.
    """
    cnt = None
    if pkg_j is not None:
        cnt = {"pkg_j": float(pkg_j), "pkg_pwh": pwh,
               "ts_100ns": ts, "pp1_j": None}
    e = {"counter": cnt, "counter_error": "" if cnt else "lettura fallita",
         "t_wall": 1000.0, "t_wall_utc": utc}
    if t_mono is not None:
        e["t_mono"] = float(t_mono)
    return v4.normalize_counter_edge(e) if via_capture else e


class FakeJudgeSession:
    """Sessione che serve bordi in sequenza e un'energia di buffer finta."""

    def __init__(self, edges, buffer_energy=None, method="emi-counter"):
        self._edges = list(edges)
        self.i = 0
        self.source_method = method
        self.buffer_energy = buffer_energy
        self.seen = []

    def read_counter_edge(self):
        e = self._edges[min(self.i, len(self._edges) - 1)]
        self.i += 1
        return dict(e)                    # copia: la cattura la normalizza

    def package_energy_exact_between(self, a, b, excl=None):
        self.seen.append((a, b))
        return self.buffer_energy


@pytest.fixture
def no_real_judge(monkeypatch):
    """Il giudice reale non si chiama: la HTTP e' fuori scope qui."""
    monkeypatch.setattr(v4.bu, "_judge_via_energy_session",
                        lambda q, a, m: "risposta")


def capture_two(edges, monkeypatch, buffer_energy=None):
    """Esegue una chiamata del wrapper su due bordi dati."""
    monkeypatch.setattr(v4, "SESSION", FakeJudgeSession(edges, buffer_energy))
    cap = v4.JudgeEdgeCapture()
    cap("q", "a", "m")
    return cap


# ---------------------------------------------------------------------------
# 1. Forma del bordo
# ---------------------------------------------------------------------------
def test_il_bordo_del_giudice_espone_anche_t_counter_mono(monkeypatch,
                                                          no_real_judge):
    """Normalizzazione del nome: senza di essa il fallback monotono di
    _edge_dt_w e' irraggiungibile per i bordi del giudice."""
    cap = capture_two([edge(pkg_j=100.0, ts=None, t_mono=1000.0),
                       edge(pkg_j=200.5, ts=None, t_mono=1002.0)], monkeypatch)
    call = cap.calls[0]
    assert call["start"]["t_counter_mono"] == pytest.approx(
        call["start"]["t_mono"])
    assert call["end"]["t_counter_mono"] == pytest.approx(1002.0)
    dt, src = Profiler._edge_dt_w(call["start"], call["end"])
    assert src == "python-monotonic"
    assert dt == pytest.approx(2.0)

    # e la normalizzazione e' portante, non decorativa: gli stessi bordi
    # nella forma grezza di read_counter_edge() non danno nessun Δt, quindi
    # un contatore leggibile degraderebbe all'interpolazione in silenzio.
    raw = {"start": edge(pkg_j=100.0, t_mono=1000.0, via_capture=False),
           "end": edge(pkg_j=200.5, t_mono=1002.0, via_capture=False)}
    raw_dt, raw_src = Profiler._edge_dt_w(raw["start"], raw["end"])
    assert raw_dt is None and raw_src == "python-window"
    assert v4.judge_direct_readiness(raw, 10.0)[0] is None


def test_letture_di_entrambi_i_bordi_restano_separate(monkeypatch,
                                                     no_real_judge):
    """read_s e' il max dei due bordi, ma i due valori restano in tabella:
    se un solo bordo e' lento deve potersi distinguere da un segmento lento."""
    cap = capture_two([edge(pkg_j=100.0, ts=0, t_mono=1000.0),
                       edge(pkg_j=101.0, ts=1_000_000, t_mono=1001.0)],
                      monkeypatch)
    call = cap.calls[0]
    assert call["read_s"] == pytest.approx(
        max(call["read_start_s"], call["read_end_s"]), abs=1e-3)
    assert call["read_start_s"] >= 0.0 and call["read_end_s"] >= 0.0


# ---------------------------------------------------------------------------
# 2. Δt dal record del contatore e stessa coppia per energia e durata
# ---------------------------------------------------------------------------
def test_energia_diretta_usa_il_timestamp_del_record():
    """ts 100,0 s -> 105,0 s e contatore 100,0 -> 150,5 J:
    E = 50,5 − 10,0·5,0 = 0,5 J, con base dichiarata emi-counter-ts."""
    call = {"start": edge(pkg_j=100.0, ts=1_000_000_000, pwh=10**14),
            "end": edge(pkg_j=150.5, ts=1_050_000_000, pwh=10**14 + 5 * 10**12)}
    value, reason = v4.judge_direct_readiness(call, 10.0)
    assert value == pytest.approx(0.5)
    assert reason.startswith("ok") and "emi-counter-ts" in reason


def test_energia_e_durata_dalla_stessa_coppia_di_letture():
    """Il Δt moltiplicato per P_pre e' quello dei due timestamp del bordo, non
    la somma delle finestre HTTP: requisito P6.5, e qui verificato perche' il
    campo esposto (judge_window_s) misura un'altra cosa."""
    call = {"start": edge(pkg_j=100.0, ts=1_000_000_000),
            "end": edge(pkg_j=150.5, ts=1_050_000_000)}
    value, _reason = v4.judge_direct_readiness(call, 10.0)
    dt, _src = Profiler._edge_dt_w(call["start"], call["end"])
    assert dt == pytest.approx(5.0)
    assert value == pytest.approx((150.5 - 100.0) - 10.0 * dt)


# ---------------------------------------------------------------------------
# 3. Record duplicato
# ---------------------------------------------------------------------------
def test_stesso_record_letto_due_volte_non_diventa_zero_joule():
    """ΔE = 0,0 con timestamp identici non e' "il package non ha consumato":
    e' la stessa riga letta due volte. Va a interpolazione dichiarata, non a
    un incrementale finto di −P·Δt."""
    call = {"start": edge(pkg_j=100.0, ts=1_000_000_000, t_mono=1000.0),
            "end": edge(pkg_j=100.0, ts=1_000_000_000, t_mono=1000.5)}
    value, reason = v4.judge_direct_readiness(call, 10.0)
    assert value is None
    assert "stesso record" in reason

    fields = v4.judge_fields(
        SimpleNamespace(calls=[call]), [], 10.0)
    assert fields["judge_energy_edge_source"] == "unavailable"
    assert fields["judge_energy_j"] == "N/A"


def test_contatore_che_non_avanza_ma_record_diverso_e_un_dato():
    """Timestamp diversi e valore invariato: il contatore non ha ticchettato
    nel segmento. E' una misura (0,0 J) che con la baseline diventa negativa e
    resta firmata: il clamp a zero lo decide il chiamante, non qui."""
    call = {"start": edge(pkg_j=100.0, ts=1_000_000_000),
            "end": edge(pkg_j=100.0, ts=1_010_000_000)}
    value, reason = v4.judge_direct_readiness(call, 10.0)
    assert reason.startswith("ok")
    assert value == pytest.approx(0.0 - 10.0 * 1.0)   # −10,0 J: firmato


# ---------------------------------------------------------------------------
# 4. Contatore assente / reset / nessun Δt
# ---------------------------------------------------------------------------
# Id espliciti e ASCII: il valore atteso contiene spazi e un "Δ", e pytest li
# mette tali e quali nel node id ("...[call2-nessun Δt]", che `pytest -v`
# stampa come "...[call2-nessun \u0394t]"). Il generatore dell'Appendice D
# converte quel backslash in \textbackslash{} e la prima colonna della tabella
# si ritrova un frammento inseguibile da 29 caratteri: la soglia di 26,
# congelata il 24/10 dopo sei overfull box, e' una misura della colonna, non una
# cortesia. Il nome del case si legge comunque, e il guard
# tests/test_dump_node_id.py::test_il_frammento_piu_lunguo_del_verbale_sta_in_un_segmento
# resta verde senza spostarlo.
@pytest.mark.parametrize("call,expected", [
    # un bordo senza contatore (backend chiuso, IOCTL fallita)
    pytest.param({"start": edge(pkg_j=None), "end": edge(pkg_j=150.0, ts=10)},
                 "contatore assente", id="senza-contatore"),
    # valore del contatore che decresce fra i bordi: reset
    pytest.param({"start": edge(pkg_j=150.0, ts=1_000_000_000),
                  "end": edge(pkg_j=100.0, ts=1_100_000_000)},
                 "non crescente", id="contatore-non-crescente"),
    # ne' timestamp del record ne' base monotona: nessun Δt
    pytest.param({"start": edge(pkg_j=100.0), "end": edge(pkg_j=150.0)},
                 "nessun Δt", id="nessun-dt"),
])
def test_i_rifiuti_del_bordo_hanno_ciascuno_la_loro_ragione(call, expected):
    """Quattro facce del "non e' possibile" non stanno dentro un None solo:
    la ragione finisce nella nota e rende verificabile il buffer-interp."""
    value, reason = v4.judge_direct_readiness(call, 10.0)
    assert value is None
    assert expected in reason


def test_timestamp_non_monotono_usa_la_base_monotona():
    """Record con ts che torna indietro (registro riordinato) ma istante Python
    crescente: _edge_dt_w sceglie la monotona e lo dichiara, il bordo non e'
    sprecato."""
    call = {"start": edge(pkg_j=100.0, ts=2_000_000_000, t_mono=1000.0),
            "end": edge(pkg_j=150.0, ts=1_000_000_000, t_mono=1005.0)}
    value, reason = v4.judge_direct_readiness(call, 10.0)
    assert value == pytest.approx(50.0 - 10.0 * 5.0)
    assert "python-monotonic" in reason


def test_degrada_tutto_il_segmento_non_a_meta(monkeypatch):
    """Due chiamate, una sola con il bordo diretto: il numero pubblicato viene
    dall'interpolazione per l'INTERO segmento (un numero non puo' essere meta'
    IOCTL e meta' buffer), e la nota dice 1/2."""
    ok = {"start": edge(pkg_j=100.0, ts=1_000_000_000),
          "end": edge(pkg_j=150.0, ts=1_005_000_000)}
    mancati = {"start": edge(pkg_j=None), "end": edge(pkg_j=200.0, ts=1)}
    # buffer: 40,0 J sulla finestra del giudice
    monkeypatch.setattr(v4, "SESSION",
                        FakeJudgeSession([], buffer_energy=40.0))
    reasons = []
    fields = v4.judge_fields(
        SimpleNamespace(calls=[ok, mancati]), [(1000.0, 1003.0)], 10.0,
        reasons_out=reasons)

    assert len(reasons) == 2, "le chiamate vanno valutate tutte"
    assert fields["judge_energy_edge_source"] == "buffer-interp"
    # buffer: 40,0 J su 3,0 s con P_pre 10,0 W -> 40 − 30 = 10,0 J
    assert fields["judge_energy_interp_j"] == pytest.approx(10.0)
    assert fields["judge_energy_j"] == pytest.approx(10.0)
    assert fields["judge_window_s"] == pytest.approx(3.0)


def test_interpolazione_applica_la_baseline_del_blocco(monkeypatch):
    """Il percorso di fallback sottrae P_pre del blocco, non lo stato di
    sessione (F.1) e non clampa a zero (D1): il segno resta nel grezzo."""
    monkeypatch.setattr(v4, "SESSION", FakeJudgeSession(
        [], buffer_energy=5.0, method="emi-counter"))
    # 5,0 J su 1,0 s con P_pre 10,0 W -> −5,0 J
    fields = v4.judge_fields(SimpleNamespace(calls=[]),
                             [(1000.0, 1001.0)], 10.0)
    assert fields["judge_energy_interp_j"] == pytest.approx(-5.0)
    assert fields["_judge_energy_raw_j"] == pytest.approx(-5.0)
    assert fields["judge_energy_j"] == pytest.approx(0.0)
    assert fields["judge_energy_edge_source"] == "buffer-interp"


def test_canale_non_di_misura_non_si_interpola(monkeypatch):
    """Un canale di stima non produce un'energia interpolata: la cella resta
    non-calcolata e il fonte dice unavailable."""
    monkeypatch.setattr(v4, "SESSION", FakeJudgeSession(
        [], buffer_energy=5.0, method="estimated"))
    fields = v4.judge_fields(SimpleNamespace(calls=[]),
                             [(1000.0, 1001.0)], 10.0)
    assert fields["judge_energy_interp_j"] == ""
    assert fields["judge_energy_j"] == "N/A"
    assert fields["judge_energy_edge_source"] == "unavailable"


# ---------------------------------------------------------------------------
# 6. Spread dei bordi contro durata del segmento
# ---------------------------------------------------------------------------
def test_judge_edge_spread_non_e_la_durata_del_segmento():
    """``judge_edge_spread_s`` e' il massimo del costo di UNA lettura del
    contatore dentro il segmento; ``judge_window_s`` e' la somma delle finestre
    HTTP. Numeri diversi per grandezze diverse: se qualcuno li confonde, il
    test cade."""
    ok = {"start": edge(pkg_j=100.0, ts=1_000_000_000, t_mono=1000.0),
          "end": edge(pkg_j=150.0, ts=1_005_000_000, t_mono=1005.0),
          "read_s": 0.002, "read_start_s": 0.002, "read_end_s": 0.0005}
    ok2 = {"start": edge(pkg_j=150.0, ts=1_005_000_000, t_mono=1005.0),
           "end": edge(pkg_j=200.0, ts=1_012_000_000, t_mono=1012.0),
           "read_s": 0.001, "read_start_s": 0.0004, "read_end_s": 0.001}
    cap = SimpleNamespace(calls=[ok, ok2])
    fields = v4.judge_fields(cap, [(1000.0, 1003.0), (1005.0, 1010.0)], 10.0)

    assert fields["judge_edge_spread_s"] == pytest.approx(0.002)
    assert fields["judge_window_s"] == pytest.approx(8.0)
    assert fields["judge_edge_spread_s"] != fields["judge_window_s"]
    # i bordi UTC sono il primo start e l'ultimo end, non una media
    assert fields["judge_edge_start_utc"] == "t-utc"
    assert fields["judge_edge_end_utc"] == "t-utc"
    assert fields["judge_emi_ts_start_100ns"] == 1_000_000_000
    assert fields["judge_emi_ts_end_100ns"] == 1_012_000_000


# ---------------------------------------------------------------------------
# 7. Nota di tracciabilita'
# ---------------------------------------------------------------------------
def test_la_nota_lascia_ricalcolare_il_valore_diretto():
    """Grezzo del contatore, estensione dei bordi ed esito per chiamata: con
    questi tre un terzo rifà la sottrazione senza fidarsi del runner."""
    ok = {"start": edge(pkg_j=100.0, ts=1_000_000_000, pwh=1_000_000.0,
                        t_mono=1000.0),
          "end": edge(pkg_j=150.0, ts=1_005_000_000, pwh=1_500_000.0,
                      t_mono=1005.0), "read_s": 0.002}
    bad = {"start": edge(pkg_j=None, t_mono=1010.0),
           "end": edge(pkg_j=200.0, ts=1, t_mono=1012.0), "read_s": 0.001}
    reasons = []
    fields = v4.judge_fields(SimpleNamespace(calls=[ok, bad]), [], 10.0,
                             reasons_out=reasons)
    note = v4.judge_trace_note(SimpleNamespace(calls=[ok, bad]), reasons,
                               fields["judge_energy_edge_source"],
                               fields["judge_window_s"])

    assert "giudice: 1/2 chiamate con bordo diretto" in note
    assert "fonte energia=unavailable" in note
    assert "contatore assente" in note
    assert "estensione bordi=12.000000 s" in note
    # il grezzo mancante a un estremo si dichiara, non si omette
    assert "contatore grezzo pWh: 1000000.0 -> -" in note
    assert "judge_window_s" in note


def test_nota_vuota_senza_chiamate():
    """Nessuna chiamata del giudice: nessuna nota inventata."""
    assert v4.judge_trace_note(SimpleNamespace(calls=[]), [], "", "") == ""
    assert v4.judge_trace_note(None, [], "", "") == ""


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
