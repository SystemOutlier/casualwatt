# -*- coding: utf-8 -*-
"""
tests/test_terminazione_v4.py — P2.4/P2.5 sulla riga v4 e recuperabilita' dei
campi che non hanno colonna.

Perche' esiste. Il protocollo (protocollo_v4_20261024.md:727-741) dice che
``done_reason`` "si registra grezzo, insieme a una classe", e da' una tabella di
cinque righe con una condizione numerica per quattro di esse. La versione
precedente del runner scriveva la nota solo ``if resp_data.get("done_reason")``:
l'assenza del campo -- che E' una delle cinque classi, ``termination_missing`` --
lasciava la riga muta. ``early_stop``, che la stessa sezione formula, non era
calcolato da nessuna parte. Lo schema di P5 non ha colonne per questi campi,
quindi la nota e' l'unica collocazione che non aggiunge nessuna colonna: se non
sono neppure recuperabili da li', la richiesta invalida non si puo' escludere
dall'analisi (P2.5) e il denominatore ``N_out_actual`` di P2.3 non si puo'
giustificare.

Che cosa verifica:
  1. le cinque righe della tabella P2.4, ciascuna con la propria condizione;
  2. ``early_stop`` e' la formula congelata, e vale ``""`` (non ``"false"``)
     quando i contatori mancano e la congiunzione non e' calcolabile;
  3. nessuna sesta classe inventata: il valore e' sempre una delle cinque
     congelate, o vuoto con il perche' dichiarato;
  4. i motivi di invalidita' di P2.5: ``tokens_missing``, ``counter_inconsistent``
     e ``context_boundary`` (che la tabella P2.4 non copre);
  5. la nota e' analizzabile: le chiavi ``done_reason=``, ``termination_class=``,
     ``early_stop=`` c'erano sempre e la stessa riga resta agganciata al blocco
     dalle chiavi ``run_id``/``batch_id``/``point_id``/``block_id``;
  6. il cablaggio: il ramo condizionale non torna, e il percorso del riepilogo di
     blocco e l'identita' del giudice -- che ``_basic_record`` calcola e
     ``export_results_csv`` butta via -- sono recuperabili dal run metadata.

Che cosa NON verifica: la semantica reale di ``done_reason`` per versione di
Ollama (e' il pilota A di P2.9, non si valuta qui) e l'esistenza di una colonna
dedicata, che e' una decisione di congelamento P5.
"""
import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
import casualwatt_csv_export as csvx  # noqa: E402


# ------------------------------------------------------------------ 1
@pytest.mark.parametrize("reason,n_in,n_out,cap,ctx,klass", [
    ("length", 100, 160, 160, 8192, "cap_reached"),
    ("length", 100, 159, 160, 8192, "termination_inconsistent"),
    ("stop", 100, 31, 160, 8192, "eos"),
    ("stop", 100, 160, 160, 8192, "eos_at_cap"),
    ("error", 100, 31, 160, 8192, "termination_missing"),
    ("", 100, 31, 160, 8192, "termination_missing"),
    (None, 100, 31, 160, 8192, "termination_missing"),
])
def test_le_cinque_righe_della_tabella_p24(reason, n_in, n_out, cap, ctx,
                                          klass):
    """Ogni riga della tabella congelata con la sua condizione numerica."""
    f = v4.termination_fields(reason, n_in, n_out, cap, num_ctx=ctx)
    assert f["termination_class"] == klass
    assert klass in v4.TERMINATION_CLASSES


def test_il_grezzoresta_leggibile_anche_quando_assente():
    """done_reason vuoto si marca <assente>: non e' una stringa vuota, e'
    l'assenza del campo, e la classe non si puo' confondere con un valore."""
    assert v4.termination_fields("", 10, 3, 160)["done_reason"] == "<assente>"
    assert v4.termination_fields(None, 10, 3, 160)["done_reason"] == "<assente>"
    # il grezzo di un valore reale non si alterna mai con il marcatore
    assert v4.termination_fields("stop", 10, 3, 160)["done_reason"] == "stop"


# ------------------------------------------------------------------ 2
@pytest.mark.parametrize("reason,n_in,n_out,cap,early", [
    ("stop", 100, 31, 160, "true"),      # sola combinazione vera
    ("stop", 100, 160, 160, "false"),    # eos_at_cap: non e' early stop
    ("length", 100, 160, 160, "false"),  # la congiunzione si legge col solo 1o
    ("", 100, 31, 160, "false"),
    ("stop", 100, "", 160, ""),          # N_out assente: non calcolabile
    ("stop", 100, 31, "", ""),
])
def test_early_stop_e_la_formula_congelata(reason, n_in, n_out, cap, early):
    """early_stop = (done_reason == "stop" and N_out_actual < num_predict)."""
    f = v4.termination_fields(reason, n_in, n_out, cap)
    assert f["early_stop"] == early


def test_assenza_dei_token_non_diventa_false():
    """Con ``N_out_actual`` mancante ``early_stop`` resta vuoto: "false"
    sarebbe un'informazione che la macchina non ha prodotto."""
    f = v4.termination_fields("stop", 100, "", 160)
    assert f["early_stop"] == ""
    assert f["termination_class"] == ""
    assert "tokens_missing" in f["invalid_reasons"]


def test_lo_zero_letto_e_un_valore_non_una_mancanza():
    """``eval_count = 0`` e' un conteggio: la classe di P2.4 si applica al
    valore letto (``eos``), e l'invalidita' arriva da P2.5, che chiede
    ``eval_count >= 1``. Le due cose non si confondono fra loro."""
    f = v4.termination_fields("stop", 0, 0, 160)
    assert f["termination_class"] == "eos"
    assert f["early_stop"] == "true"
    assert "tokens_missing" in f["invalid_reasons"]


# ------------------------------------------------------------------ 3
def test_nessuna_sesta_classe():
    """Le classi possibili sono le cinque di P2.4, o il vuoto dichiarato."""
    for reason in ("", "stop", "length", "eos", "max", "noise", None, 0, "STOP"):
        for n_out in (0, "", None, 5, 160, 999):
            klass = v4.termination_fields(reason, 10, n_out, 160,
                                          num_ctx=8192)["termination_class"]
            assert klass == "" or klass in v4.TERMINATION_CLASSES


def test_stop_oltre_il_tetto_non_cade_in_una_riga_vicina():
    """stop con N_out > num_predict non ha una riga nella tabella: la classe
    resta vuota con il perche', e il motivo di P2.5 (counter_inconsistent)
    viene registrato perche' quello P2.5 lo nomina."""
    f = v4.termination_fields("stop", 100, 200, 160)
    assert f["termination_class"] == ""
    assert "counter_inconsistent" in f["invalid_reasons"]
    assert any("nessuna riga" in d for d in f["undetermined"])


# ------------------------------------------------------------------ 4
def test_context_boundary_sul_denominatore_dichiarato():
    """N_in + N_out > num_ctx invalida (P2.5); l'uguaglianza no, e senza
    num_ctx dichiarato la guardia non si puo' proprio valutare."""
    assert "context_boundary" in v4.termination_fields(
        "stop", 8000, 200, 160, num_ctx=8192)["invalid_reasons"]
    assert "context_boundary" not in v4.termination_fields(
        "stop", 8000, 192, 160, num_ctx=8192)["invalid_reasons"]
    assert "context_boundary" not in v4.termination_fields(
        "stop", 8000, 200, 160)["invalid_reasons"]


def test_counter_inconsistent_anche_con_length():
    """``length`` con N_out sopra il tetto e' incoerenza del contatore, e la
    riga della tabella la chiama gia' termination_inconsistent."""
    f = v4.termination_fields("length", 100, 200, 160)
    assert f["termination_class"] == "termination_inconsistent"
    assert "counter_inconsistent" in f["invalid_reasons"]
    assert "termination_inconsistent" in f["invalid_reasons"]


def test_i_motivi_di_invalidita_nominati_da_p25():
    """P2.5 (protocollo:760-764) elenca cinque motivi di invalidita'. Qui si
    verifica che siano tutti producibili e che nessun altro token esca dalla
    funzione: una sesta etichetta inventata non deve poter entrare
    nell'esclusione del dataset primario."""
    casi = [
        dict(reason="", n_in=100, n_out=31, cap=160),
        dict(reason="length", n_in=100, n_out=150, cap=160),
        dict(reason="stop", n_in=100, n_out=200, cap=160),
        dict(reason="stop", n_in=8100, n_out=100, cap=160, ctx=8192),
        dict(reason="stop", n_in="", n_out=31, cap=160),
    ]
    prodotte = set()
    for c in casi:
        f = v4.termination_fields(c["reason"], c["n_in"], c["n_out"], c["cap"],
                                  num_ctx=c.get("ctx", 8192))
        prodotte.update(f["invalid_reasons"])
    assert prodotte == set(v4.INVALIDITY_REASONS), prodotte
    for no in ("early_stop", "cap_reached", "eos_at_cap"):
        assert no not in v4.INVALIDITY_REASONS


# ------------------------------------------------------------------ 5
def test_la_nota_ha_sempre_le_tre_chiavi():
    """Le chiavi parseabili ci sono anche nei casi degeneri: un analizzatore
    non deve inferire l'assenza di una chiave dall'assenza del dato."""
    for reason, n_in, n_out in [("stop", 100, 31), ("", 100, 31),
                                ("stop", "", ""), ("length", 100, 160)]:
        note = v4.termination_note(
            v4.termination_fields(reason, n_in, n_out, 160))
        for key in ("done_reason=", "termination_class=", "early_stop="):
            assert key in note, (key, note)
        assert all(("=" in p) for p in note.split("; ") if not p.startswith(
            ("richiesta invalida", "classe P2.4", "nessuna riga"))), note


def test_la_nota_dichiara_la_classe_non_determinata():
    """Classe e early_stop non calcolabili si leggono come marcatori espliciti,
    non come stringhe vuote dentro un ``k=v`` muto."""
    note = v4.termination_note(v4.termination_fields("stop", "", "", 160))
    assert "termination_class=<non determinata>" in note
    assert "early_stop=<non determinabile>" in note
    assert "classe P2.4 non determinabile" in note


def test_la_nota_porta_i_motivi_di_invalidita():
    """P2.5: i motivi di invalidita' si leggono nella nota di riga, perche'
    non hanno colonna. Un ``done_reason`` non fra i cinque della tabella (qui
    ``error``) deve produrre ``richiesta invalida per:`` con il motivo, e una
    richiesta sana non deve produrre la frase: la assenza di invalidita' non e'
    la stessa stringa di un'invalidita' non calcolata."""
    note = v4.termination_note(v4.termination_fields("error", 10, 3, 160))
    assert "richiesta invalida per:" in note
    assert "termination_missing" in note
    # una richiesta sana non ha la frase
    sano = v4.termination_note(v4.termination_fields("stop", 100, 31, 160,
                                                     num_ctx=8192))
    assert "richiesta invalida per:" not in sano


def test_le_chiavi_di_aggancio_restano_nello_schema():
    """La nota e' recuperabile solo se la riga e' identificabile: run_id,
    batch_id, point_id e block_id sono colonne di CSV_COLUMNS (D3)."""
    for key in ("run_id", "session_id", "batch_id", "point_id", "block_id",
                "prompt", "notes"):
        assert key in csvx.CSV_COLUMNS


# ------------------------------------------------------------------ 6
def test_il_ramo_condizionale_su_done_reason_non_c_e_piu():
    """Regressione: ``if resp_data.get("done_reason")`` rendeva muta
    l'assenza. La nota di terminazione e' ora incondizionata."""
    src = inspect.getsource(v4.run_block)
    assert 'if resp_data.get("done_reason")' not in src
    assert "termination_note(term)" in src
    assert "prompt_nonce={nonce}; prompt_sha256={sha}" in src
    assert "num_ctx={int(num_ctx)}; num_predict={int(num_predict)}" in src


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


def _stub_run(monkeypatch):
    """run_v4_benchmark senza hardware ne' rete: ritorna il payload dei
    metadati del run, cioe' il posto dove i campi senza colonna devono potersi
    leggere. K e seme di Emenda 8 dall'ambiente: senza il runner non parte."""
    monkeypatch.setenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", "1")
    monkeypatch.setenv("CW_V4_SUBSTITUTION_SEED", "terminazione-test")
    meta = {}
    blocks = []

    def fake_run_block(model, prompt, **kw):
        blocks.append(kw)
        return [], {"batch_id": kw["batch_id"], "point_id": kw["point_id"],
                    "block_id": kw["block_id"], "baseline_pre_w": 11.0,
                    "cooldown_timeout": ""}

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
    return meta, blocks


def test_i_campi_senza_colonna_si_leggono_nei_metadata(monkeypatch):
    """``block_summary_csv`` non ha colonna in RUN_METADATA_COLUMNS e
    ``judge_model`` lo ha nella riga ma viene scartato da
    ``extrasaction="ignore"``: finiscono entrambi nella nota del run, dove
    ``run_id`` li aggancia alle righe."""
    monkeypatch.setenv("CW_JUDGE_MODEL", "giudice-di-prova:1b")
    meta, _blocks = _stub_run(monkeypatch)
    blocchi = Path("results/_t_blocks.csv")
    v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"}],
                        blocks_per_point=1, m=2,
                        results_path=Path("results/_t_rows.csv"),
                        block_summary_path=blocchi)

    assert "block_summary_csv=" in meta["notes"]
    # il percorso e' quello normalizzato dal sistema: e' la stringa che un
    # terzo deve poter incollare, non una sua riformattazione
    assert str(blocchi) in meta["notes"]
    assert "judge_model=giudice-di-prova:1b" in meta["notes"]
    # le impostazioni sperimentali restano recuperabili dal run
    for token in ("runner=benchmark_v4", "m=2", "blocks_per_point=1",
                  "num_ctx=", "num_predict=", "keep_alive="):
        assert token in meta["notes"], token
    assert meta["temperature"] == v4.config.DEFAULT_TEMPERATURE


def test_judge_model_esiste_ma_non_e_una_colonna(monkeypatch):
    """Prova del presupposto: ``_basic_record`` calcola ``judge_model`` e lo
    scrive in una riga che poi il writer butta via. Se qualcuno aggiunge la
    colonna, questo test va aggiornato insieme alla nota (che resta, e'
    ridondanza dichiarata, non un doppio conteggio)."""
    keys = set(v4.bu._basic_record(
        "r", "s", "m", "m", "ollama", "local", None,
        {"id": "p", "text": "t"}, v4.bu.evalres_placeholder()).keys())
    assert "judge_model" in keys
    assert "judge_model" not in csvx.CSV_COLUMNS
    assert "done_reason" not in csvx.CSV_COLUMNS
    assert "early_stop" not in csvx.CSV_COLUMNS


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
