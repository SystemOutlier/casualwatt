# -*- coding: utf-8 -*-
"""
tests/test_controllo_p44_v4.py — il blocco di controllo di P4.4 e il suo
`E_net,control`.

Perche' esiste. P4.4 (protocollo_v4_20261024.md:1452-1516) chiede una campagna
di controllo che precede la principale: sei coppie di blocchi, e il blocco di
controllo e' "identico per struttura, stato macchina e durata, **senza alcuna
richiesta**" (P4.3, :1430). Il requisito 5 fissa la durata prima
(`dt_nominal_s`) e il requisito 8 fissa il numero: `E_net,control =
E_pkg_gross − P_pre · Δt_W`, "con lo stesso codice di produzione e senza
troncamento". Il requisito 7 impone la stessa struttura di baseline 3 pre +
3 post dei blocchi di carico, perche' e' cio' che rende calcolabili
`pre_range_w,c`, `dP_c`, `budget_base_w,c` e `budget_base_j,c` — gli ingressi
del criterio di P4.5 (:1536-1541) e di F.12 (:3089-3112).

Prima di questo file il runner non sapeva produrre un blocco di controllo:
`run_block` inviava sempre `m` richieste e `block_kind` era solo una stringa
registrata. Un `block_kind='control'` scritto da un chiamante esterno avrebbe
prodotto un blocco di carico etichettato "controllo", cioe' un gate che misura
il carico e dichiara di non averlo inviato.

Che cosa verifica:
  1. il blocco di controllo non invia richieste (`infer_v4_stream` non viene
     chiamato) e non produce righe di richiesta;
  2. l'ordine resta quello di P1.5 — settle, calibrazione pre, due bordi,
     settle, calibrazione post — e le terne pre/post alimentano le due
     baseline come nel blocco di carico;
  3. `E_net,control = E_pkg_gross − P_pre · Δt_W` con il `Δt_W` MISURATO (non
     il nominale) e la sottrazione firmata, senza troncamento: un E_net
     negativo resta negativo e dichiarato, non diventa zero;
  4. `budget_base_j` del controllo e' `budget_base_w × Δt_W,control`, cioe' il
     `budget_base_j,c` che P4.5 confronta con `|E_net,control,c|`;
  5. `r_A`/`r_B` restano vuote: non esiste un denominatore su un blocco senza
     richieste (P4.4 requisito 7, emendamento del 2026-10-24);
  6. una finestra con il contatore non avanzato fra i bordi e' dichiarata
     `counter-invalid` nel riepilogo, non presentata come misura;
  7. senza `dt_nominal_s` il blocco non parte, e non parte PRIMA di toccare la
     sessione: una durata inventata dopo i dati non sarebbe piu' il disegno
     congelato (P4.4 requisito 5).

Che cosa NON verifica: il criterio aggregato di F.12 (`bias_w`, quorum,
`mediana_c(budget_base_w,c)`) e l'ordine randomizzato delle coppie. Sono del
gate, non del blocco: qui si verifica che il blocco produca tutti gli ingressi
che quel criterio legge.
"""
import csv
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_unified as bu  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import energy.local_energy as le  # noqa: E402
from casualwatt_csv_export import (  # noqa: E402
    BLOCK_SUMMARY_COLUMNS, export_summary_csv)
from energy.worker_tree import WorkerProc  # noqa: E402

T0 = 100.0
WORKER = WorkerProc(7, 1000.0, "ollama.exe")

# stesse terne del blocco di carico: pre mediana 10,0 range 0,2, post mediana
# 10,4 drift 0,4 -> budget_base_w = hypot(0,1 ; 0,2) = 0,223607
PRE = [9.9, 10.0, 10.1]
POST = [10.3, 10.4, 10.5]
BW = round(math.hypot(0.1, 0.2), 6)


def _edge(t, pkg_j, ts_100ns):
    """Bordo di misura con il contatore EMI: `pkg_j` in joule e `ts_100ns` sono
    le due grandezze che `_edge_energy_j` e `_edge_dt_w` leggono."""
    return {
        "tree": [WORKER],
        "worker": {WORKER: t},
        "busy": t * 10.0,
        "counter": {"pkg_j": pkg_j, "pkg_pwh": pkg_j * 100.0,
                    "ts_100ns": ts_100ns, "pp1_j": None},
        "counter_error": "",
        "t_wall": t,
        "t_wall_utc": f"2026-11-07T10:00:{t - T0:06.3f}+00:00",
        "t_counter_mono": t,
        "t_cpu_mid": t,
        "edge_spread_s": 0.02,
    }


def _bordi(dt_w_s, e_pkg_j, *, ts_avanza=True):
    """Coppia di bordi a distanza `dt_w_s` con delta package `e_pkg_j`.

    `ts_100ns` e' in unita' da 100 ns: per `dt_w_s` secondi serve un salto di
    `dt_w_s * 1e7`. Con `ts_avanza=False` i due bordi leggono lo stesso record
    e la finestra e' `counter-invalid` (la regola del registro fermo).
    """
    ts0 = 1_000_000_000
    ts1 = ts0 + int(round(dt_w_s * 1e7)) if ts_avanza else ts0
    return [_edge(T0, 1000.0, ts0), _edge(T0 + dt_w_s, 1000.0 + e_pkg_j, ts1)]


def _prepara(monkeypatch, bordi, *, durata_nominale="0.02"):
    """Sessione sintetica per il solo blocco di controllo: nessun campione,
    nessuna richiesta, due bordi serviti in ordine."""
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table",
            timestamp=0.0))

    class _SessioneControllo:
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
            self.ordine = []
            self._it = iter(bordi)

        def start(self):
            pass

        def stop(self):
            pass

        def settle_idle(self, *a, **k):
            self.ordine.append("settle")
            return 1.0

        def calibrate_idle(self, *a, **k):
            self.calib += 1
            self.ordine.append("calib")
            return 10.0 if self.calib == 1 else 10.4

        @property
        def _idle_reps(self):
            return list(PRE if self.calib == 1 else POST)

        def read_measurement_edge(self, **k):
            self.ordine.append("bordo")
            edge = next(self._it)
            self._last_edge = edge
            return edge

        def samples_between(self, a, b):
            return []

        def package_energy_exact_between(self, a, b, excl=None,
                                         exclude_windows=None):
            # sentinella: con i bordi validi il percorso esatto sul buffer non
            # deve essere usato (l'energia e' la differenza diretta ai bordi)
            return -1.0e6

    fake = _SessioneControllo()
    monkeypatch.setattr(v4, "SESSION", fake)

    def _vietato(*a, **k):
        raise AssertionError("il blocco di controllo non invia richieste")

    monkeypatch.setattr(v4, "infer_v4_stream", _vietato)
    monkeypatch.setattr(v4, "evaluate_response", _vietato)

    prof = le.CasualWattLocalEnergyProfiler()
    prof.session = fake
    return prof, fake


def _blocco(monkeypatch, bordi, **kwargs):
    prof, fake = _prepara(monkeypatch, bordi)
    dt_nom = kwargs.pop("dt_nominal_s", "0.02")
    rows, summary = v4.run_block(
        "qwen2.5:0.5b",
        {"id": "g1", "text": "domanda", "ground_truth": "21",
         "source": "manual"},
        run_id="R1", session_id="S1", batch_id="batchGate",
        point_id="gate__p1", block_id="gate__p1__c1",
        nonce_seq=0, profiler=prof, m=3,
        block_kind="control", pair_id="pair-1",
        order_seed="gate-seed-20261107", dt_nominal_s=dt_nom,
        control=True, **kwargs)
    return rows, summary, fake


# ---------------------------------------------------------------------------
# 1. nessuna richiesta, nessuna riga
# ---------------------------------------------------------------------------
def test_controllo_non_invia_richieste_e_non_produce_righe(monkeypatch):
    """P4.3: il blocco di controllo e' "senza alcuna richiesta". Se il runner
    ne inviasse anche una, il blocco misurerebbe un carico che dichiara di non
    aver prodotto, e `E_net,control` non sarebbe piu' l'incremento a
    richiesta nulla che il gate usa come riferimento."""
    rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 101.0))

    assert rows == []
    assert summary["block_kind"] == "control"
    assert summary["pair_id"] == "pair-1"
    assert summary["order_seed"] == "gate-seed-20261107"


# ---------------------------------------------------------------------------
# 2. struttura di baseline identica a P1.5
# ---------------------------------------------------------------------------
def test_controllo_mantiene_la_sequenza_pre_bordi_post(monkeypatch):
    """P4.4 requisito 7: tre finestre pre, la finestra passiva, tre post. Due
    sole calibrazioni e due soli bordi: una terza calibrazione sarebbe una
    baseline inventata, un terzo bordo una finestra che il blocco non ha."""
    _rows, summary, fake = _blocco(monkeypatch, _bordi(10.0, 101.0))

    assert fake.ordine == ["settle", "calib", "bordo", "bordo",
                           "settle", "calib"]
    assert summary["pre_windows_w"] == "9.900000;10.000000;10.100000"
    assert summary["post_windows_w"] == "10.300000;10.400000;10.500000"
    assert summary["baseline_pre_w"] == pytest.approx(10.0)
    assert summary["baseline_post_w"] == pytest.approx(10.4)
    assert summary["dP"] == pytest.approx(0.4)
    assert summary["pre_range_w"] == pytest.approx(0.2)
    assert summary["budget_base_w"] == pytest.approx(BW)


# ---------------------------------------------------------------------------
# 3-4. E_net,control e budget_base_j,c
# ---------------------------------------------------------------------------
def test_e_net_control_e_il_prodotto_con_la_dt_w_misurata(monkeypatch):
    """F.12: `E_net,control = E_pkg_gross − P_pre · Δt_W`. L'energia e' la
    differenza diretta del contatore ai bordi (101 − 1000), `P_pre` e' la
    mediana delle tre repliche pre e `Δt_W` e' il tempo del contatore (10 s,
    dai timestamp 100 ns), non il nominale di 0,02 s."""
    _rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 101.0))

    assert summary["control_wait_nominal_s"] == pytest.approx(0.02)
    assert summary["control_dt_w_s"] == pytest.approx(10.0)
    assert summary["control_e_pkg_gross_j"] == pytest.approx(101.0)
    assert summary["control_e_baseline_j"] == pytest.approx(100.0)
    assert summary["control_e_net_j"] == pytest.approx(1.0)
    assert summary["control_package_window_source"] == "exact-counter"


def test_budget_base_j_del_controllo_usa_la_finestra_unica(monkeypatch):
    """P4.5 confronta `|E_net,control,c|` con `budget_base_j,c`: sul controllo
    non ci sono richieste, quindi `budget_base_j` e' `budget_base_w` per la sola
    finestra passiva e non una media su `duration_s` inesistenti."""
    _rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 101.0))

    assert summary["budget_base_j"] == pytest.approx(round(10.0 * BW, 6))


def test_e_net_negativo_non_viene_troncato(monkeypatch):
    """Il protocollo conserva il segno: un controllo che consuma meno della
    baseline ha E_net negativo, ed e' il caso informativo. Troncarlo a zero
    cancellerebbe proprio l'incremento che il gate misura."""
    _rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 95.0))

    assert summary["control_e_net_j"] == pytest.approx(-5.0)
    assert "E_attiva grezza" in summary["control_notes"]
    assert "active_valid=False" in summary["control_notes"]
    # il grezzo del package e' positivo (95.0 J): nessun reset, nessun flag
    assert summary["negative_increment"] == "false"


def test_r_a_e_r_b_restano_vuote_su_un_controllo(monkeypatch):
    """P4.4 requisito 7 (emendamento 2026-10-24): `r_A`/`r_B` hanno al
    denominatore l'energia delle richieste valide; su un blocco senza richieste
    non esiste un denominatore, quindi le celle restano vuote e non zero. Una
    cella a 0,0 direbbe "errore relativo nullo", cioe' il contrario."""
    _rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 101.0))

    assert summary["r_A"] == ""
    assert summary["r_B"] == ""


# ---------------------------------------------------------------------------
# 5. finestra del contatore degradata
# ---------------------------------------------------------------------------
def test_finestra_con_registro_fermo_dichiarata_counter_invalid(monkeypatch):
    """Due bordi che leggono lo stesso record EMI: il delta non e' una misura
    (regola del registro fermo, gia' in vigore per le righe). Il riepilogo del
    controllo deve dichiararlo con `package_window_source`, non presentarlo
    come `exact-counter`: il gate deve poter scartare il controllo."""
    _rows, summary, _fake = _blocco(
        monkeypatch, _bordi(10.0, 101.0, ts_avanza=False))

    assert summary["control_package_window_source"] == "counter-invalid"
    assert "non avanzato fra i bordi" in summary["control_notes"]


# ---------------------------------------------------------------------------
# 6. durata fissata prima
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("nominale", ["", "  ", "tre", "0", "-5", None])
def test_senza_dt_nominale_il_controllo_non_parte(monkeypatch, nominale):
    """P4.4 requisito 5: `dt_nominal_s` si fissa PRIMA della campagna. Un
    valore assente, non numerico o non positivo ferma il blocco con
    `ValueError` prima di toccare la sessione: partire con una durata
    inventata sarebbe un disegno diverso da quello congelato, scoperto solo
    dopo i dati."""
    class _Trappola:
        def __getattr__(self, nome):
            raise AssertionError(
                f"sessione toccata prima della validazione ({nome})")

    monkeypatch.setattr(v4, "SESSION", _Trappola())
    with pytest.raises(ValueError):
        v4.run_block(
            "qwen2.5:0.5b", {"id": "g1", "text": "domanda", "source": "manual"},
            run_id="R1", session_id="S1", batch_id="batchGate",
            point_id="gate__p1", block_id="gate__p1__c1",
            nonce_seq=0, profiler=None, m=3,
            block_kind="control", dt_nominal_s=nominale, control=True)


def test_il_nominale_non_entra_nella_sottrazione(monkeypatch):
    """P4.4 requisito 5: lo scarto fra nominale e misurato non crea bias
    perche' ciascun blocco sottrae il PROPRIO `Δt_W`. Due nominali diversi
    sulla stessa finestra di contatore devono dare lo stesso E_net."""
    _r1, base, _f1 = _blocco(monkeypatch, _bordi(10.0, 101.0),
                             dt_nominal_s="0.02")
    _r2, lungo, _f2 = _blocco(monkeypatch, _bordi(10.0, 101.0),
                              dt_nominal_s="0.05")

    assert base["control_e_net_j"] == pytest.approx(lungo["control_e_net_j"])
    assert base["control_dt_w_s"] == pytest.approx(lungo["control_dt_w_s"])


# ---------------------------------------------------------------------------
# 8. il riepilogo entra nello schema P5 senza allargarlo
# ---------------------------------------------------------------------------
def test_il_riepilogo_del_controllo_entra_nello_schema_p5(monkeypatch,
                                                          tmp_path):
    """Lo schema P5 e' congelato (34 colonne di blocco) e le quantita' della
    finestra passiva non hanno una colonna: se l'esportazione le scrivesse,
    allargherebbe lo schema; se perdesse `block_kind`, il controllo non
    sarebbe distinguibile da un blocco di carico nel file consegnato."""
    _rows, summary, _fake = _blocco(monkeypatch, _bordi(10.0, 101.0))
    percorso = tmp_path / "block_summary.csv"

    assert export_summary_csv([summary], percorso, BLOCK_SUMMARY_COLUMNS,
                              mode="a") == 1

    with open(percorso, newline="", encoding="utf-8-sig") as fh:
        righe = list(csv.DictReader(fh))

    assert list(righe[0]) == BLOCK_SUMMARY_COLUMNS
    assert not any(nome.startswith("control_") for nome in righe[0])
    riga = righe[0]
    assert riga["block_kind"] == "control"
    assert riga["pair_id"] == "pair-1"
    assert riga["r_A"] == "" and riga["r_B"] == ""
    assert float(riga["budget_base_j"]) == pytest.approx(
        summary["budget_base_j"])
