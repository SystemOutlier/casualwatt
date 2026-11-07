# -*- coding: utf-8 -*-
"""Guardia sull'harness P6.6 (`s_epi_phase.py`) e sulla sua fonte di verita'.

L'harness produce `s_EPI`, `d = s - s_EPI` e `r` per fase, cioe' i numeri con
cui si dichiara se due procedure di attribuzione concordano. Due cose non
possono essere lasciate alla rilettura del codice:

  1. **la finestra**. Il confronto vale solo se `s` e `s_EPI` coprono la stessa
     porzione di tempo: qui la finestra si ricava dalle righe del runner
     (`timestamp_start`/`timestamp_end`), non dalla forma dei bucket SRUM, e i
     due tempi di assestamento vengono dalle colonne `settle_pre_s` /
     `settle_post_s` del runner v4 (o dal piano, dichiarandolo). Un valore
     assente resta vuoto con la sua provenienza -- non si deduce dai bucket;
  2. **il vocabolario delle quote**. `s` e' `d_ollama/d_busy` limitata a [0,1],
     `s_EPI` e' il rapporto fra l'energia CPU dell'albero e quella di tutte le
     voci della fase, e `r` e' la differenza relativa simmetrica. I test
     fissano i valori su bucket costruiti a mano, dove il risultato e'
     calcolabile senza hardware, senza run e senza `powercfg`.
"""

from __future__ import annotations

import datetime as _dt

import pytest

from s_epi_phase import (
    BLOCKING_FLAGS,
    Bucket,
    choose_phase_buckets,
    dedup,
    evaluate_phase,
    is_blocking,
    is_tree_app,
    minute_coverage,
    phase_share,
    relative_symmetric,
    rows_for_phase,
    s_epi_of,
    settle_of,
    window_from_rows,
)

BASE = _dt.datetime(2026, 10, 25, 10, 0, 0)
TD = _dt.timedelta


def bucket(app_id, minutes, ms=60_000, cpu_mj=600.0, offset_minutes=0):
    return Bucket(app_id=app_id, ts_utc=BASE + TD(minutes=minutes + offset_minutes),
                  ms=float(ms), cpu_mj=cpu_mj, emi_mj=0.0, tot_mj=0.0)


def fase(base=BASE, **extra):
    """Una fase valida di 5 minuti, con i due settling dichiarati nel piano."""
    ph = {
        "phase_id": "p1", "config_id": "c1", "replica": 1,
        "t_start_utc": base.isoformat(),
        "t_end_utc": (base + TD(minutes=5)).isoformat(),
        "settle_pre_s": 42.146, "settle_post_s": 25.071,
        "d_ollama_s": 73.39, "d_busy_s": 100.0, "s_source": "csv",
        "engine_tree_changed": False, "exclusion": "",
    }
    ph.update(extra)
    return ph


def cinque_minuti():
    """Albero 600 mJ/min contro altro processo 400 mJ/min: `s_EPI` fa 0,6."""
    out = [bucket("ollama.exe", i) for i in range(5)]
    out += [bucket("chrome.exe", i, cpu_mj=400.0) for i in range(5)]
    return out


# --- famiglia 1: identificazione dell'albero e bucket -----------------------

def test_albero_per_nome_esatto():
    """L'albero e' quello dichiarato da P6.6, confrontato sul basename esatto.

    Il needle `"ollama"` vede 0,0011 invece di 0,7361
    (`srum_emi_cross_20261023_analisi.md:158-162`): un processo che contiene la
    parola non e' l'albero, e un worker `llama-server.exe` lo e' anche se la
    parola non compare.
    """
    assert is_tree_app("C:\\Program Files\\Ollama\\ollama.exe")
    assert is_tree_app("llama-server.exe")
    assert is_tree_app("Ollama App.EXE")
    assert not is_tree_app("chrome.exe")
    assert not is_tree_app("ollama-helper.exe")


def test_bucket_di_bordo_esclusi_e_restituiti():
    """Un bucket che attraversa un bordo non si ripartisce: si esclude.

    Ripartirlo assumerebbe una distribuzione uniforme del tempo dentro il
    bucket, che il protocollo non assume; il bucket esce dal calcolo e il
    chiamante lo dichiara con `bucket_di_bordo:N`.
    """
    inside, boundary = choose_phase_buckets(
        [bucket("ollama.exe", -1, ms=90_000),
         bucket("ollama.exe", 4, ms=90_000)],
        BASE, BASE + TD(minutes=5))
    assert inside == []
    assert len(boundary) == 2


def test_righe_complementari_restano_entrambe():
    """Due righe dello stesso minuto sono due pezzi reali, non duplicati.

    Filtrarle perderebbe energia (`srum.py:35-38`); la deduplica e' per firma
    esatta, quindi solo una riga identica viene scartata.
    """
    due = [bucket("ollama.exe", 0, ms=26_593, cpu_mj=10.0),
           bucket("ollama.exe", 0, ms=33_399, cpu_mj=10.0)]
    assert len(dedup(due)) == 2
    assert s_epi_of(due)["total_cpu_j"] == pytest.approx(0.02)
    assert len(dedup(due + [due[0]])) == 2


def test_pseudo_appid_rapl_fuori_dal_denominatore():
    """Gli pseudo-AppId `emi_rapl_*` hanno CPU = 0 e non entrano nel rapporto.

    Sommarli gonfierebbe il denominatore di un'entita' che non e' lavoro della
    CPU: il modello EPI per processo non li conta.
    """
    pseudo = Bucket("EMI_RAPL_Package0_PKG", BASE, 60_000, 0.0, 50.0, 50.0)
    assert s_epi_of([pseudo])["total_cpu_j"] == 0.0
    assert s_epi_of([pseudo])["s_epi"] is None


def test_s_epi_sui_bucket_costruiti():
    """`s_EPI` e' il rapporto fra energia dell'albero e totale della fase.

    3 J dell'albero su 5 J totali: 0,6. Il numeratore si legge per nome esatto,
    il denominatore somma ogni voce tranne gli pseudo-AppId RAPL.
    """
    agg = s_epi_of(cinque_minuti())
    assert agg["tree_cpu_j"] == pytest.approx(3.0)
    assert agg["total_cpu_j"] == pytest.approx(5.0)
    assert agg["s_epi"] == pytest.approx(0.6)
    assert agg["n_apps"] == 2


def test_minuti_e_presenza_albero():
    """La completezza si giudica dalla presenza dell'albero, non dai millisecondi.

    `TimeInMSec` e' per processo: un bucket corto e' il tempo reale di quella
    app, non una finestra incompleta. Se pero' un minuto non ha nessuna riga
    dell'albero, il numeratore non copre la stessa finestra di `s`.
    """
    buckets = [bucket("ollama.exe", i) for i in range(1, 5)]
    buckets += [bucket("chrome.exe", i, cpu_mj=400.0) for i in range(5)]
    minuti, con_albero = minute_coverage(buckets)
    assert len(minuti) == 5
    assert len(con_albero) == 4


# --- famiglia 2: le quote e la differenza simmetrica ------------------------

def test_differenza_relativa_simmetrica():
    """`r = 2d/(s+s_EPI)` e' simmetrica e non definita a somma nulla."""
    assert relative_symmetric(0.7339, 0.7361) == pytest.approx(
        -0.002993197278911565, rel=0, abs=1e-15)
    assert relative_symmetric(0.7, 0.7) == 0.0
    assert relative_symmetric(0.0, 0.0) is None


def test_quota_dai_componenti_o_dal_campo():
    """`s` viene da `d_ollama/d_busy`; il campo dichiarato e' il ripiego.

    I componenti sono la definizione (P6.6), il campo `s` esiste per le righe
    che non li portano, e la provenienza segue il valore.
    """
    s_val, fonte = phase_share({"d_ollama_s": 73.39, "d_busy_s": 100.0})
    assert (s_val, fonte) == (pytest.approx(0.7339), "d_ollama/d_busy")
    s_val, fonte = phase_share({"s": 0.71, "s_source": "campo csv"})
    assert (s_val, fonte) == (0.71, "campo csv")
    assert phase_share({})[0] is None


# --- famiglia 3: la valutazione di fase -------------------------------------

def test_fase_completa_d_e_r_coerenti():
    """`d` e `r` pubblicati si ricavano dai due campi pubblicati, non a parte.

    Se il CSV esponesse `s`, `s_EPI` e `d` con arrotondamenti diversi, chi
    rilegge non ritroverebbe `d = s - s_EPI`: qui la coerenza e' un test.
    """
    row = evaluate_phase(fase(), cinque_minuti(), {"abs": 0.005, "rel": 0.01})
    assert row["s"] == pytest.approx(0.7339)
    assert row["s_epi"] == pytest.approx(0.6)
    assert row["d"] == pytest.approx(0.1339)
    assert row["d"] == pytest.approx(row["s"] - row["s_epi"])
    assert row["r"] == pytest.approx(round(2 * 0.1339 / 1.3339, 9))
    assert row["in_band"] is False
    assert row["blocking"] is False
    assert row["n_minutes"] == 5
    assert row["window_strict"] is True


def test_senza_banda_nessun_verdetto():
    """Senza banda congelata `in_band` resta nullo: l'harness non inventa soglie."""
    row = evaluate_phase(fase(), cinque_minuti(), None)
    assert row["in_band"] is None
    assert row["d"] == pytest.approx(0.1339)


def test_engine_tree_changed_toglie_il_verdetto():
    """Un albero cambiato rende `s` non comparabile (P6.6:2661-2672).

    Il flag e' una condizione sostanziale: la fase resta misurata ma non
    produce verdetto di banda.
    """
    row = evaluate_phase(fase(engine_tree_changed=True), cinque_minuti(),
                         {"abs": 0.5, "rel": 0.9})
    assert "engine_tree_changed" in row["flags"]
    assert row["in_band"] is None
    assert row["blocking"] is True


def test_s_fuori_intervallo_toglie_il_verdetto():
    """`s` e' limitata a [0,1] da P6.6: 1,2 e' un errore di misura, non una quota."""
    row = evaluate_phase(fase(d_ollama_s=120.0, d_busy_s=100.0),
                         cinque_minuti(), {"abs": 0.5, "rel": 0.9})
    assert "s_fuori_da_0_1" in row["flags"]
    assert row["in_band"] is None


def test_minuto_senza_albero_toglie_il_verdetto():
    """Un minuto senza righe dell'albero lascia il numeratore scoperto."""
    parziale = [bucket("ollama.exe", i) for i in range(1, 5)]
    parziale += [bucket("chrome.exe", i, cpu_mj=400.0) for i in range(5)]
    row = evaluate_phase(fase(), parziale, {"abs": 0.5, "rel": 0.9})
    assert "minuto_senza_albero:1" in row["flags"]
    assert row["in_band"] is None


# --- famiglia 4: finestra e settling dalle righe del runner -----------------

def righe_runner(**override):
    riga = {
        "block_id": "qwen2.5-0.5b__c-001__b01", "batch_id": "a807d465870b",
        "timestamp_start": BASE.isoformat() + "+00:00",
        "timestamp_end": (BASE + TD(minutes=5)).isoformat() + "+00:00",
        "settle_pre_s": "42.146", "settle_post_s": "25.071",
    }
    riga.update(override)
    return riga


def test_settle_dalle_colonne_del_runner():
    """I tempi di assestamento sono quelli del runner, non dei bucket SRUM.

    Il runner li misura con `settle_idle()` prima delle due calibrazioni
    (`benchmark_v4.py:1733`, `:1945`) e li scrive su ogni riga del blocco:
    qui si legge il valore e si dichiara la provenienza.
    """
    settle = settle_of({"phase_id": "p"}, [righe_runner()])
    assert settle.source == "runner"
    assert (settle.pre_s, settle.post_s) == (42.146, 25.071)
    assert settle.inconsistent is False


def test_settle_incoerente_non_sceglie_un_valore():
    """Righe dello stesso blocco con settling diversi non producono un numero.

    Vuol dire che i file mescolano blocchi o run: si pubblica il vuoto con la
    provenienza `incoerente`, non il primo valore incontrato.
    """
    righe = [righe_runner(), righe_runner(settle_pre_s="48.151")]
    settle = settle_of({"phase_id": "p"}, righe)
    assert settle.source == "incoerente"
    assert settle.pre_s is None and settle.post_s is None
    assert settle.inconsistent is True


def test_settle_dal_piano_se_le_righe_non_lo_portano():
    """Senza colonne valorizzate si legge il piano, dichiarandolo."""
    righe = [righe_runner(settle_pre_s="", settle_post_s="")]
    settle = settle_of({"settle_pre_s": 20.0, "settle_post_s": 21.0}, righe)
    assert settle.source == "piano"
    assert (settle.pre_s, settle.post_s) == (20.0, 21.0)


def test_settle_assente_non_blocca_ma_si_dichiara():
    """Un settling assente e' una lacuna di provenienza, non una fase invalida.

    P6.6 elenca finestra integra, `done_reason`, albero cambiato ed esclusioni:
    il settling non c'e', quindi il verdetto si produce e la riga lo dichiara.
    """
    ph = {k: v for k, v in fase().items() if not k.startswith("settle_")}
    row = evaluate_phase(ph, cinque_minuti(), {"abs": 0.5, "rel": 0.9})
    assert row["settle_source"] == "assente"
    assert row["settle_pre_s"] is None
    assert "settle_assente" in row["flags"]
    assert row["blocking"] is False
    assert row["in_band"] is True


def test_finestra_dalla_riga_del_runner():
    """Senza finestra nel piano, la fase si ricava dalle righe del runner.

    La finestra e' quella delle richieste -- `min(timestamp_start)` e
    `max(timestamp_end)` -- e i timestamp con offset diventano UTC naive, la
    base su cui SRUM scrive i bucket.
    """
    ph = {k: v for k, v in fase().items()
          if k not in ("t_start_utc", "t_end_utc")}
    ph["block_id"] = "qwen2.5-0.5b__c-001__b01"
    row = evaluate_phase(ph, cinque_minuti(), {"abs": 0.5, "rel": 0.9},
                         rows=[righe_runner()])
    assert row["window_source"] == "runner:timestamp_start/end"
    assert row["t_start_utc"] == BASE.isoformat()
    assert row["t_end_utc"] == (BASE + TD(minutes=5)).isoformat()
    assert row["duration_s"] == pytest.approx(300.0)
    assert row["n_minutes"] == 5


def test_finestra_dichiarata_nel_piano_vince():
    """Se il piano dichiara la finestra, quella vince e la provenienza lo dice.

    E' la via del pre-pilota: le fasi furono battute a mano su un blocco intero,
    e la riga deve poterlo dichiarare invece di far sembrare tutto derivato.
    """
    row = evaluate_phase(fase(), cinque_minuti(), None,
                         rows=[righe_runner()])
    assert row["window_source"] == "piano"
    assert row["settle_source"] == "runner"


def test_riga_senza_timestamp_non_da_finestra():
    """Una riga senza timestamp lascia la finestra vuota, e la fase invalida.

    Non si salta la riga e non si usa quella delle altre: una finestra
    costruita su un sottoinsieme non e' la finestra della fase.
    """
    assert window_from_rows([righe_runner(timestamp_end="")]) is None
    ph = {k: v for k, v in fase().items()
          if k not in ("t_start_utc", "t_end_utc")}
    ph["block_id"] = "qwen2.5-0.5b__c-001__b01"
    row = evaluate_phase(ph, cinque_minuti(), None,
                         rows=[righe_runner(timestamp_end="")])
    assert row["flags"] == "finestra_non_valida"
    assert row["blocking"] is True


def test_righe_di_fase_per_block_o_batch():
    """Le righe si associano alla fase per `block_id`, con `batch_id` di riserva."""
    righe = [righe_runner()]
    assert rows_for_phase(righe, {"block_id": "qwen2.5-0.5b__c-001__b01"}) == righe
    assert rows_for_phase(righe, {"batch_id": "a807d465870b"}) == righe
    assert rows_for_phase(righe, {"phase_id": "senza-righe"}) == []


def test_flag_settle_non_bloccanti():
    """`settle_assente` e `settle_incoerente` non sono condizioni di validita'."""
    for flag in ("settle_assente", "settle_incoerente"):
        assert flag not in BLOCKING_FLAGS
        assert is_blocking([flag]) is False
