# -*- coding: utf-8 -*-
"""
tests/test_emenda8_sostituzione.py — Emenda 8 (P1.6): il blocco invalidato si
sostituisce una sola volta; P2.9: la quadratura resta.

Perche' esiste. L'emenda congela una regola che tocca il SOLO punto del
disegno in cui un fallimento parziale puo' trasformarsi in un numero
silenziosamente diverso: un guasto tecnico del contatore in una finestra di
baseline invalida il blocco alla prima occorrenza e chiama UN solo sostituto
completo dello stesso punto, in una posizione estratta dal resto del batch
con seme dichiarato. Se la gestione sbaglia di un'unita' (due sostituti,
nessuno, un retry della finestra, un flag di qualita' scambiato per guasto)
il batch resta plausibile e il difetto lo vede solo l'analisi, dopo. Il tetto
K e il seme senza default, inoltre, sono un gate di partenza: se il runner ne
inventa uno, il disegno del run non e' piu' quello approvato.

Che cosa verifica (prove (a)-(g) del task, + il gate di partenza):
  0. i classificatori: "contatore decrescente" -> delta_negativo; terna con
     NaN -> lettura_non_finita; replica <= 0 -> replica_non_positiva; e
     run_block li usa davvero (solleva V4CounterFault, non V4MeasurementError);
  a. delta negativo nella calibrazione pre -> blocco invalidato, UN solo
     sostituto dello STESSO punto di disegno (replaced_block_id), nonce
     diverso (nonce_seq mai riutilizzato);
  b. secondo guasto sul sostituto -> blocco "mancante", mai una terza chance;
  c. un errore non di contatore (o un flag di qualita') NON produce
     sostituzione: V4MeasurementError ferma il run come prima;
  d. stesso seme -> stessa posizione del sostituto (sorteggio riproducibile);
  e. guasto sull'ultimo blocco del batch -> sostituto in coda;
  f. superamento di K -> il run si FERMA con un messaggio, senza sollevare,
     e lo dichiara nel metadata;
  g. budget_base_w invariato: quadratura delle due semi-ampiezze, la formula
     del test condiviso (0.1^2 + 0.2^2)^0.5 resta il valore atteso;
  h. senza K o senza seme (argomento, config o ambiente) il runner SI
     RIFIUTA di partire, e prima di toccare la sessione;
  i. piano multi-modello: senza guasti l'ordine resta raggruppato per
     modello; il testo approvato ("estratta a sorte dal resto del batch")
     AMMETTE che il sostituto cada nel tratto di un altro modello, e le
     prove congelano il comportamento: identita', punto, tentativo e
     cooldown del proprio punto sono preservati ovunque cada, nessun blocco
     dell'altro modello si perde, la posizione e' deterministica a parita'
     di seme, e il sorteggio puo' anche restare nel tratto proprio;
  l. righe d'invalidazione: guasto POST-calibrazione -> le m righe escono
     dal runner marcate (invalid_reason, block_attempt, replaced_block_id,
     nota di esclusione, nota preesistente preservata) e coerenti col
     riepilogo dello stesso evento; guasto PRE-calibrazione -> nessuna riga
     di richiesta, l'invalidazione vive solo nel riepilogo; le righe dei
     blocchi completati non sono toccate dal runner.

Che cosa NON verifica: hardware reale, frequenza reale dei guasti, costo in
tempo delle sostituzioni; e non verifica le righe di richiesta prodotte da un
blocco invalidato DOPO le m richieste se non tramite fault.rows del fake (la
sorgente reale e' il percorso interno di run_block, che pero' timbra le righe
completate -- prova in test_shared_components_v4.py). Non verifica
soprattutto l'INNOQUITA' dell'interleaving multi-modello: (i) fissa il
comportamento approvato e riproducibile, non che mischiare i tratti di due
modelli non sposti le condizioni di confronto. Decisione A del 26-10: il
sorteggio sul RESTO DEL BATCH resta la regola approvata, nessuna emenda di
restrizione; mantenere la regola NON dichiara innocuo l'interleaving -- la
quantificazione dell'effetto e' un obbligo del pilota, sui dati ordinari e
sostitutivi che queste prove rendono osservabili.
"""
import inspect
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_unified as bu  # noqa: E402
import benchmark_v4 as v4  # noqa: E402


class _RunSession:
    """Sessione finta sufficiente al runner (stessa del test del cooldown)."""

    running = True
    interval_s = 0.001
    source_method = "emi-counter"
    source_notes = []
    calibrated_at = ""
    cpu_time_resolution_s = 0.0156
    _gpu = SimpleNamespace(available=False, name="", index=0)

    def start(self):
        pass

    def stop(self, *a, **k):
        pass


def _not_ran(target, **kw):
    return {"ran": False, "reached": False, "timed_out": False,
            "waited_s": None, "target_pre_w": "", "samples": 0,
            "missing_reads": 0, "reason": "cooldown non eseguibile: test"}


def _stub_runner(monkeypatch, run_block_impl, *, k="2", seed="seme-di-prova",
                 sink=None):
    """Prepara run_v4_benchmark senza hardware. Ritorna (chiamate, riepiloghi).

    ``run_block_impl(kw)`` deve restituire (rows, block_rec) o sollevare: il
    fake registra i kwargs ricevuti, che e' tutto cio' che queste prove
    devono osservare (identita' del blocco, tentativo, nonce, riferimento del
    sostituto). Il MODELLO registrato accanto ai kwargs serve alle prove
    multi-modello: l'interleaving si osserva solo da li'. K e seme passano
    qui come ARGOMENTI, non come ambiente: la priorita' ambiente/config e'
    coperta dalla prova (h).

    ``sink``, se fornito, riceve ``"rows"`` (una lista per ogni esportazione
    di righe, con le righe gia' copiate: cio' che il runner ha scritto, non
    cio' che il fake ha restituito) e ``"cooldowns"`` (i riferimenti passati
    a cooldown_to_baseline, uno per ogni k==0 eseguito).
    """
    monkeypatch.delenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", raising=False)
    monkeypatch.delenv("CW_V4_SUBSTITUTION_SEED", raising=False)
    calls = []
    summaries = []
    meta = {}
    rows_out = []
    cooldowns = []

    def fake_cooldown(target, **kw):
        cooldowns.append(target)
        return _not_ran(target)

    monkeypatch.setattr(v4, "cooldown_to_baseline", fake_cooldown)
    monkeypatch.setattr(v4, "SESSION", _RunSession())
    monkeypatch.setattr(v4, "_ollama_runtime_info", lambda model: ("v", "d"))
    monkeypatch.setattr(bu, "_ecologits_version", lambda: "")
    monkeypatch.setattr(
        v4.CasualWattLocalEnergyProfiler, "probe_cpu_time_resolution",
        staticmethod(lambda *a, **k: 0.0156))

    def fake_run_block(model, prompt, **kw):
        calls.append(dict(kw, model=model))
        return run_block_impl(kw)

    def fake_export_rows(rows, path, mode="a"):
        rows_out.append([dict(r) for r in rows])
        return len(rows)

    def fake_export_summary(recs, path, cols, mode="a"):
        for r in recs:
            summaries.append(dict(r))
        return len(recs)

    monkeypatch.setattr(v4, "run_block", fake_run_block)
    monkeypatch.setattr(v4, "export_results_csv", fake_export_rows)
    monkeypatch.setattr(v4, "export_summary_csv", fake_export_summary)
    monkeypatch.setattr(v4, "write_run_metadata",
                        lambda payload, path: meta.update(payload) or path)
    if sink is not None:
        sink["rows"] = rows_out
        sink["cooldowns"] = cooldowns
    return calls, summaries, meta, {"k": k, "seed": seed}


def _ok(kw):
    """Blocco completo: nessuna riga, riepilogo con una baseline leggibile."""
    return [], {"batch_id": kw["batch_id"], "point_id": kw["point_id"],
                "block_id": kw["block_id"], "baseline_pre_w": 11.0,
                "block_attempt": kw.get("block_attempt", 1),
                "invalid_reason": "",
                "replaced_block_id": kw.get("replaced_block_id", "")}


def _fault(kw, reason="delta_negativo", rows=None):
    raise v4.V4CounterFault(
        f"baseline pre invalidata ({reason}) per test", reason, rows=rows)


def _call_args(extra=None):
    kw = {"m": 1, "results_path": Path("results/_e8_rows.csv"),
          "block_summary_path": Path("results/_e8_blocks.csv")}
    if extra:
        kw.update(extra)
    return kw


def _run(monkeypatch, impl, points, blocks, stub_args, sink=None,
         **call_extra):
    calls, summaries, meta, params = _stub_runner(
        monkeypatch, impl, k=stub_args["k"], seed=stub_args["seed"],
        sink=sink)
    out = v4.run_v4_benchmark(
        ["m"], points, blocks_per_point=blocks,
        max_invalidated_blocks=int(stub_args["k"]),
        substitution_seed=stub_args["seed"],
        **_call_args(call_extra))
    return calls, summaries, meta, out


def _run_models(monkeypatch, impl, models, points, blocks, *, k, seed,
                sink=None):
    """Come ``_run`` ma con la lista dei modelli esplicita: le prove
    multi-modello osservano l'ordine di esecuzione, non un blocco solo."""
    calls, summaries, meta, params = _stub_runner(
        monkeypatch, impl, k=str(k), seed=seed, sink=sink)
    out = v4.run_v4_benchmark(
        list(models), points, blocks_per_point=blocks,
        max_invalidated_blocks=int(k), substitution_seed=seed,
        **_call_args())
    return calls, summaries, meta, out


# ----------------------------------------------------------- 0: classificatori
def test_classificazione_del_guasto_tecnico():
    """I tre token dell'emenda sono l'UNICA porta verso la sostituzione: se
    un'etichetta sfugge, un guasto diventa un errore del run (run fermo) o un
    errore del run diventa un guasto (blocco sostituito senza titolo)."""
    assert v4.classify_calibration_exception(
        RuntimeError("calibrazione idle fallita: contatore decrescente "
                     "(delta=-3.0 J)")) == "delta_negativo"
    # assenza del backend: NON e' sostituibile (energy_session.py:2548->:2553)
    assert v4.classify_calibration_exception(
        RuntimeError("calibrazione idle fallita: nessun contatore di "
                     "energia/potenza package disponibile")) is None
    nan = float("nan")
    assert v4.classify_reps([10.0, nan, 10.2], [10.0, 10.2]) == \
        "lettura_non_finita"
    assert v4.classify_reps([10.0, -0.5, 10.1], [10.0, -0.5, 10.1]) == \
        "replica_non_positiva"
    assert v4.classify_reps([10.0, 10.1, 10.2], [10.0, 10.1, 10.2]) is None
    assert v4.classify_reps([10.0, 10.1], [10.0, 10.1]) is None


def test_run_block_solleva_v4counterfault_sul_guasto_tecnico(monkeypatch):
    """Il ponte fra il sollevare di ``calibrate_idle`` (produzione) e il token
    dell'emenda sta in run_block: qui si verifica che la catena reale
    ``RuntimeError('contatore decrescente') -> V4CounterFault('delta_negativo')``
    passi, non che il classificatore esista."""
    class _SessioneGuasta:
        running = True
        interval_s = 0.001
        source_method = "emi-counter"
        source_notes = []
        _gpu = SimpleNamespace(available=False, name="", index=0)

        def settle_idle(self, *a, **k):
            return 1.0

        def calibrate_idle(self, *a, **k):
            raise RuntimeError("calibrazione idle fallita: contatore "
                               "decrescente (delta=-1.0 J)")

    monkeypatch.setattr(v4, "SESSION", _SessioneGuasta())
    prof = SimpleNamespace()
    with pytest.raises(v4.V4CounterFault) as ei:
        v4.run_block("m", {"id": "p1", "text": "t"},
                     run_id="R", session_id="S", batch_id="B",
                     point_id="m__p1", block_id="m__p1__b01",
                     nonce_seq=0, profiler=prof, m=1)
    assert ei.value.invalid_reason == "delta_negativo"


def test_run_block_classifica_la_terna_con_lettura_non_finita(monkeypatch):
    """La terna grezza di 3 con un NaN dentro (il guard `delta_j < 0` della
    produzione e' falso per NaN, energy_session.py:2561) deve diventare
    lettura_non_finita NEL RUNNER: e' li' che il blocco si invalida."""
    class _SessioneNan:
        running = True
        interval_s = 0.001
        source_method = "emi-counter"
        source_notes = []
        _gpu = SimpleNamespace(available=False, name="", index=0)
        _idle_reps = [10.0, float("nan"), 10.2]

        def settle_idle(self, *a, **k):
            return 1.0

        def calibrate_idle(self, *a, **k):
            return 10.0

    monkeypatch.setattr(v4, "SESSION", _SessioneNan())
    with pytest.raises(v4.V4CounterFault) as ei:
        v4.run_block("m", {"id": "p1", "text": "t"},
                     run_id="R", session_id="S", batch_id="B",
                     point_id="m__p1", block_id="m__p1__b01",
                     nonce_seq=0, profiler=SimpleNamespace(), m=1)
    assert ei.value.invalid_reason == "lettura_non_finita"


# --------------------------------------------------------------- (a)
def test_a_delta_negativo_un_solo_sostituto_stessa_cella_nonce_diverso(monkeypatch):
    """b01 invalidato alla prima occorrenza: esattamente UN sostituto dello
    stesso punto (replaced_block_id = blocco caduto), con nonce_seq diverso
    (i nonce del blocco fallito sono consumati, mai riusati), e le altre cella
    del punto eseguite come in piano."""
    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            return _fault(kw)
        return _ok(kw)

    calls, summaries, meta, _p = _run(
        monkeypatch, impl, [{"id": "p1", "text": "t1"}], blocks=2,
        stub_args={"k": "2", "seed": "seme-a"})

    ids = [c["block_id"] for c in calls]
    assert "m__p1__b01" in ids
    assert ids.count("m__p1__b01__s2") == 1, "non esattamente un sostituto"
    assert len(ids) == 3, f"eseguito {ids}, attesi b01, b02, sostituto"
    sub = next(c for c in calls if c["block_id"] == "m__p1__b01__s2")
    assert sub["block_attempt"] == 2
    assert sub["replaced_block_id"] == "m__p1__b01"
    assert sub["point_id"] == "m__p1__b01".rsplit("__", 1)[0]
    nonces = {c["nonce_seq"] for c in calls}
    assert len(nonces) == 3, "nonce riutilizzato: i nonce devono essere diversi"
    # il blocco caduto lascia UNA riga di riepilogo con il token
    inv = [s for s in summaries if s.get("invalid_reason")]
    assert len(inv) == 1 and inv[0]["block_id"] == "m__p1__b01"
    assert inv[0]["block_attempt"] == 1
    assert "sostituzioni" in meta["notes"] and "seme='seme-a'" in meta["notes"]


# --------------------------------------------------------------- (b)
def test_b_secondo_guasto_sul_sostituto_blocco_mancante(monkeypatch):
    """Un guasto tecnico anche sul tentativo 2 chiude il punto come
    "mancante": nessuna terza chance, nessun retry ulteriore, e il run
    prosegue il resto del batch."""
    def impl(kw):
        if kw["point_id"] == "m__p1":
            return _fault(kw)
        return _ok(kw)

    calls, summaries, meta, out = _run(
        monkeypatch, impl,
        [{"id": "p1", "text": "t1"}, {"id": "p2", "text": "t2"}],
        blocks=1, stub_args={"k": "2", "seed": "seme-b"})

    ids = [c["block_id"] for c in calls]
    assert ids.count("m__p1__b01") == 1
    assert ids.count("m__p1__b01__s2") == 1, "non c'e' una terza chance"
    assert "m__p2__b01" in ids, "il resto del batch non si ferma"
    assert out["missing_blocks"] == 1
    assert "blocchi mancanti" in meta["notes"]
    inv = [s for s in summaries if s.get("invalid_reason")]
    assert len(inv) == 2  # tentativo 1 e tentativo 2, entrambi marcati
    assert {s["block_attempt"] for s in inv} == {1, 2}


# --------------------------------------------------------------- (c)
def test_c_flag_di_qualita_e_errori_non_tecnici_non_sostituiscono(monkeypatch):
    """La sostituzione e' SOLO per V4CounterFault. Un V4MeasurementError
    (errore del run non tecnico) ferma il run come prima, senza invalidare e
    senza sostituire; un blocco completo con pre_range_w alto resta un blocco
    valido con il suo flag: nessuna riga d'invalidazione."""
    def impl_quality(kw):
        rows, rec = _ok(kw)
        rec = dict(rec)
        rec["pre_range_w"] = 2.0  # > 1,0 W: pre_unstable, un FLAG
        return [{}], rec

    calls, summaries, _meta, out = _run(
        monkeypatch, impl_quality, [{"id": "p1", "text": "t1"}],
        blocks=2, stub_args={"k": "2", "seed": "seme-c1"})
    assert [c["block_id"] for c in calls] == ["m__p1__b01", "m__p1__b02"]
    assert not any(s.get("invalid_reason") for s in summaries)
    assert out["invalidated_blocks"] == 0

    def impl_plain(kw):
        raise v4.V4MeasurementError("errore non tecnico di test")

    with pytest.raises(v4.V4MeasurementError):
        _run(monkeypatch, impl_plain, [{"id": "p1", "text": "t1"}],
             blocks=2, stub_args={"k": "2", "seed": "seme-c2"})
    # e il run non ha prodotto nessun sostituto: lo verifica il fatto che
    # l'eccezione e' risalita fino al chiamante, senza gestione Emenda 8.


# --------------------------------------------------------------- (d)
def test_d_stesso_seme_stessa_posizione(monkeypatch):
    """Il punto del sostituto e' sorteggiato con random.Random(seme): due run
    con lo stesso seme e lo stesso schema di guasti producono LO STESSO ordine
    di esecuzione; e l'ordine non e' banalmente la coda (il seme dichiara il
    sorteggio, la coda e' solo il caso bordo (e))."""
    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            return _fault(kw)
        return _ok(kw)

    seqs = []
    for _ in range(2):
        calls, _summaries, _meta, _out = _run(
            monkeypatch, impl, [{"id": "p1", "text": "t1"}],
            blocks=3, stub_args={"k": "2", "seed": "seme-42"})
        seqs.append([c["block_id"] for c in calls])
    assert seqs[0] == seqs[1]
    # identita' del sorteggio verificabile a posteriori: con il fallimento del
    # primo blocco di un piano da 3, la posizione estratta al primo lancio e'
    # randrange(1, 4); la coda (3) e il mezzo (1) sono entrambi legittimi, ma
    # DEVONO essere gli stessi fra i due run per lo stesso motivo.
    pos = random.Random("seme-42").randrange(1, 4)
    expected = ["m__p1__b01"]
    rest = ["m__p1__b02", "m__p1__b03"]
    rest.insert(pos - 1, "m__p1__b01__s2")
    assert seqs[0] == expected + rest


# --------------------------------------------------------------- (e)
def test_e_guasto_sull_ultimo_blocco_sostituto_in_coda(monkeypatch):
    """Se il blocco caduto e' l'ultimo del batch non resta posto: il randrange
    degenera sulla coda e il sostituto e' l'ultima cosa eseguita."""
    def impl(kw):
        if kw["block_id"] == "m__p1__b03":
            return _fault(kw)
        return _ok(kw)

    calls, _summaries, _meta, _out = _run(
        monkeypatch, impl, [{"id": "p1", "text": "t1"}],
        blocks=3, stub_args={"k": "2", "seed": "seme-e"})
    ids = [c["block_id"] for c in calls]
    assert ids == ["m__p1__b01", "m__p1__b02", "m__p1__b03",
                   "m__p1__b03__s2"]


# --------------------------------------------------------------- (f)
def test_f_superamento_di_k_arresta_con_messaggio(monkeypatch):
    """K=1: il primo guasto consuma il tetto e chiama il sostituto; il secondo
    lo SUPERA e il run si ferma con un messaggio, senza sollevare. I dati
    scritti restano e l'arresto e' dichiarato nel metadata come tale, non
    come "completed"."""
    log_lines = []

    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            return _fault(kw)
        if kw["block_id"] == "m__p1__b01__s2":
            return _fault(kw, reason="lettura_non_finita")
        return _ok(kw)

    calls, summaries, meta, out = _run(
        monkeypatch, impl,
        [{"id": "p1", "text": "t1"}, {"id": "p2", "text": "t2"}],
        blocks=1, stub_args={"k": "1", "seed": "seme-f"})

    assert out["invalidated_blocks"] == 2
    assert "tetto K=1" in out["stopped_by_k"]
    assert "tetto K=1" in meta["notes"]
    assert "completed" not in meta["notes"].split("emenda 8")[-1]
    inv = [s for s in summaries if s.get("invalid_reason")]
    assert [s["block_attempt"] for s in inv] == [1, 2]
    assert inv[1]["invalid_reason"] == "lettura_non_finita"
    assert inv[1]["replaced_block_id"] == "m__p1__b01"
    # l'arresto ha fermato il piano: p2 (se non gia' eseguito prima del
    # sostituto) non puo' comparire DOPO l'arresto: l'ultimo blocco eseguito
    # e' sempre il sostituto fallito
    assert calls[-1]["block_id"] == "m__p1__b01__s2"


def test_k_ambiente_risolve_senza_argomenti(monkeypatch):
    """La via ambiente e' quella della produzione (config senza default): K e
    seme letti da CW_V4_* fanno partire il runner come gli argomenti."""
    monkeypatch.delenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", raising=False)
    monkeypatch.delenv("CW_V4_SUBSTITUTION_SEED", raising=False)
    monkeypatch.setenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", "3")
    monkeypatch.setenv("CW_V4_SUBSTITUTION_SEED", "da-ambiente")
    k, seed, prov = v4.resolve_emenda8_params(None, None)
    assert (k, seed) == (3, "da-ambiente")
    assert "CW_V4_MAX_INVALIDATED_BLOCKS_K" in prov


# --------------------------------------------------------------- (g)
def test_g_budget_base_w_invariato_quadratura_due_semiampiezze():
    """P2.9 / Emenda 8: nessuna formula nuova. budget_base_w resta la
    quadratura delle due semi-ampiezze, e il valore atteso e' lo stesso del
    test condiviso dei componenti (ipotenusa di 0,1 e 0,2)."""
    base = v4.block_baseline([9.9, 10.0, 10.1], [10.3, 10.4, 10.5])
    assert base["half_range_pre_w"] == pytest.approx(0.1)
    assert base["half_drift_w"] == pytest.approx(0.2)
    assert base["budget_base_w"] == pytest.approx(
        (0.1 ** 2 + 0.2 ** 2) ** 0.5)
    src = inspect.getsource(v4.block_baseline)
    assert "math.hypot" in src
    # la dichiarazione richiesta dall'emenda vive nel commento/docstring:
    # proxy conservativo, non incertezza standard, non limite massimo.
    doc = v4.block_baseline.__doc__.lower()
    for token in ("quadratura", "semi-ampiezze", "proxy", "non e'",
                  "limite massimo"):
        assert token in doc


# --------------------------------------------------------------- (h) gate
def test_senza_k_o_senza_seme_il_runner_non_parte(monkeypatch):
    """Nessun valore di default inventato: senza K il runner solleva PRIMA di
    toccare la sessione; senza seme lo stesso. La prova tocca anche l'ordine:
    SESSION.start non deve mai essere reached."""
    monkeypatch.delenv("CW_V4_MAX_INVALIDATED_BLOCKS_K", raising=False)
    monkeypatch.delenv("CW_V4_SUBSTITUTION_SEED", raising=False)

    started = []

    class _SessioneCheNonDevePartire(_RunSession):
        def start(self):
            started.append(True)

    monkeypatch.setattr(v4, "SESSION", _SessioneCheNonDevePartire())

    with pytest.raises(ValueError, match="non parte"):
        v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"}],
                            m=1, results_path=Path("results/_x.csv"),
                            block_summary_path=Path("results/_y.csv"),
                            substitution_seed="solo-seme")
    with pytest.raises(ValueError, match="non parte"):
        v4.run_v4_benchmark(["m"], [{"id": "p1", "text": "t1"}],
                            m=1, results_path=Path("results/_x.csv"),
                            block_summary_path=Path("results/_y.csv"),
                            max_invalidated_blocks=2)
    assert started == [], "il gate deve precedere l'avvio della sessione"


# ------------------------------------------------- (i) piano multi-modello
_ORIGINE_PUNTI = [{"id": "p1", "text": "t1"}, {"id": "p2", "text": "t2"}]


def _piano_atteso():
    """Gli otto blocchi di due modelli x due punti x due blocchi, nell'ordine
    in cui il piano li costruisce: tutto alfa, poi tutto beta."""
    return [f"{mdl}__{p}__b{k:02d}"
            for mdl in ("alfa", "beta") for p in ("p1", "p2") for k in (1, 2)]


def test_i1_piano_senza_guasti_raggruppa_per_modello(monkeypatch):
    """Senza guasti il runner NON tocca l'ordine: i blocchi restano
    raggruppati per modello e per punto. E' il controesempio che rende
    significativa la prova di interleaving (i2): se l'ordine di base fosse
    gia' mescolato, "il sostituto cade in mezzo a beta" non direbbe nulla."""
    sink = {}
    calls, _summaries, meta, out = _run_models(
        monkeypatch, _ok, ["alfa", "beta"], _ORIGINE_PUNTI, 2,
        k=3, seed="seme-i1", sink=sink)
    assert [c["block_id"] for c in calls] == _piano_atteso()
    assert [c["model"] for c in calls] == ["alfa"] * 4 + ["beta"] * 4
    assert out["invalidated_blocks"] == 0
    assert "completed" in meta["notes"]
    # cooldown SOLO sui k==0: quattro confini di punto, niente sostituti
    assert len(sink["cooldowns"]) == 4


def test_i2_sostituto_cade_nel_tratto_di_un_altro_modello(monkeypatch):
    """Il testo approvato dell'emenda dice "estratta a sorte dal RESTO DEL
    BATCH", e il batch copre tutti i modelli: con due modelli il sostituto
    PUO' atterrare dentro il tratto dell'altro. Il rischio dichiarato nella
    revisione del 26-10 (interleaving) esiste nel disegno approvato; questa
    prova lo congela come COMPORTAMENTO OSSERVATO e verifica che, comunque
    cada, il sostituto resta il blocco dello STESSO punto di disegno:
    modello, point_id, k, tentativo e cooldown sono quelli di alfa, e il
    tratto di beta non perde nessun blocco. La decisione A del 26-10 mantiene
    questa regola SENZA emenda di restrizione: qui non si testa che l'effetto
    sia innocuo, ma che il comportamento sia deterministico e osservabile --
    l'ordine reale finisce nel substitution_log del metadata, e il pilota deve
    quantificarne l'impatto confrontando sostituti e blocchi di piano."""
    seed = "e8-beta"
    pos = random.Random(seed).randrange(1, 9)
    assert pos == 7, "il seme di prova deve estrarre una posizione in beta"
    piano = _piano_atteso()
    sostituto = "alfa__p1__b01__s2"
    atteso = piano[:pos] + [sostituto] + piano[pos:]

    def impl(kw):
        if kw["block_id"] == "alfa__p1__b01":
            return _fault(kw)
        return _ok(kw)

    sink = {}
    calls, _summaries, meta, out = _run_models(
        monkeypatch, impl, ["alfa", "beta"], _ORIGINE_PUNTI, 2,
        k=3, seed=seed, sink=sink)

    assert [c["block_id"] for c in calls] == atteso
    sub = next(c for c in calls if c["block_id"] == sostituto)
    assert sub["model"] == "alfa", "il sostituto eredita il modello del punto"
    assert sub["point_id"] == "alfa__p1"
    assert sub["block_attempt"] == 2
    assert sub["replaced_block_id"] == "alfa__p1__b01"
    # il tratto beta e' intatto: quattro blocchi, ordine relativo preservato
    beta = [c["block_id"] for c in calls if c["model"] == "beta"]
    assert beta == [b for b in piano if b.startswith("beta__")]
    # il k del punto e' conservato: il sostituto apre il punto come k==0 e
    # riceve il suo cooldown, anche se esegue in mezzo a beta
    assert len(sink["cooldowns"]) == 5, "cooldown anche per il k==0 sostituito"
    assert out["substitutions"] == 1
    assert f"in posizione {pos} di 8" in meta["notes"]


def test_i3_interleaving_riproducibile_a_parita_di_seme(monkeypatch):
    """L'estensione multi-modello del requisito (d): lo stesso seme e lo
    stesso schema di guasti producono la STESSA sequenza (modello, block_id).
    Se l'interleaving deve restare nel disegno, deve almeno essere
    rigenerabile: due run che divergono nella posizione del sostituto non
    sono confrontabili fra loro."""
    def impl(kw):
        if kw["block_id"] == "alfa__p1__b01":
            return _fault(kw)
        return _ok(kw)

    seqs = []
    for _ in range(2):
        calls, _summaries, _meta, _out = _run_models(
            monkeypatch, impl, ["alfa", "beta"], _ORIGINE_PUNTI, 2,
            k=3, seed="e8-beta")
        seqs.append([(c["model"], c["block_id"]) for c in calls])
    assert seqs[0] == seqs[1]


def test_i4_sostituto_nel_tratto_del_proprio_modello(monkeypatch):
    """L'altro braccio del sorteggio: con il seme che estrae posizione 1 il
    sostituto esegue subito dopo il blocco caduto, il tratto di alfa resta
    contiguo e quello di beta NON viene toccato. Insieme a (i2) fissa che la
    posizione e' davvero una variabile del seme, non una coda fissa."""
    seed = "e8-dentro"
    pos = random.Random(seed).randrange(1, 9)
    assert pos == 1
    piano = _piano_atteso()
    sostituto = "alfa__p1__b01__s2"
    atteso = piano[:pos] + [sostituto] + piano[pos:]

    def impl(kw):
        if kw["block_id"] == "alfa__p1__b01":
            return _fault(kw)
        return _ok(kw)

    calls, _summaries, _meta, _out = _run_models(
        monkeypatch, impl, ["alfa", "beta"], _ORIGINE_PUNTI, 2,
        k=3, seed=seed)
    assert [c["block_id"] for c in calls] == atteso
    beta = [c for c in calls if c["model"] == "beta"]
    assert [c["block_id"] for c in beta] == [b for b in atteso
                                             if b.startswith("beta__")]


# ------------------------------------------- (l) righe invalide ed esclusione
def test_l1_guasto_post_calibrazione_esporta_righe_marcate_escluse(monkeypatch):
    """Il protocollo (Emenda 8, rifinitura c547cd8) dice: se il guasto e'
    post-calibrazione le m richieste SONO avvenute e le righe restano nel CSV
    append-only con una nota dichiarata, ma NON entrano in nessuna analisi.
    Il marcatore di esclusione e' il trio invalid_reason / block_attempt /
    replaced_block_id timbrato dal runner SU OGNI riga del blocco caduto,
    oltre alla nota. Qui si verifica che (1) le righe escono marcate, con la
    nota preesistente preservata e il token giusto, (2) le righe dei blocchi
    completati NON vengono toccate dal runner (la timbratura di quelle e'
    responsabilita' di run_block, provata in test_shared_components_v4.py),
    (3) il riepilogo d'invalidazione e le righe raccontano lo stesso evento:
    stesso block_id, stesso tentativo, stesso motivo."""
    sink = {}

    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            return _fault(kw, rows=[
                {"block_id": kw["block_id"], "notes": "nota tecnica"},
                {"block_id": kw["block_id"], "notes": ""},
            ])
        # blocco completato: run_block lo ha gia' timbrato, il runner passa
        return ([{"block_id": kw["block_id"], "block_attempt": 1,
                  "invalid_reason": "", "replaced_block_id": "",
                  "notes": ""}], _ok(kw)[1])

    calls, summaries, _meta, out = _run(
        monkeypatch, impl,
        [{"id": "p1", "text": "t1"}, {"id": "p2", "text": "t2"}],
        blocks=1, stub_args={"k": "2", "seed": "seme-l1"}, sink=sink)

    righe_cadute = sink["rows"][0]
    assert len(righe_cadute) == 2
    for r in righe_cadute:
        assert r["invalid_reason"] == "delta_negativo"
        assert r["block_attempt"] == 1
        assert r["replaced_block_id"] == ""
        assert "NON entrano in nessuna analisi" in r["notes"]
    assert righe_cadute[0]["notes"].startswith("nota tecnica; ")
    # le esportazioni successive (sostituto e p2) sono righe completate:
    # invalid_reason vuota e nessun tocco del runner
    for batch in sink["rows"][1:]:
        for r in batch:
            assert r["invalid_reason"] == ""
            assert "invalidato" not in r["notes"]
    # coerenza riga/riepilogo dello STESSO evento
    inv = [s for s in summaries if s.get("invalid_reason")]
    assert len(inv) == 1
    assert inv[0]["block_id"] == righe_cadute[0]["block_id"] == "m__p1__b01"
    assert inv[0]["block_attempt"] == righe_cadute[0]["block_attempt"] == 1
    assert inv[0]["invalid_reason"] == righe_cadute[0]["invalid_reason"]
    assert out["records"] == 4  # 2 cadute + 1 sostituto + 1 p2
    assert len(calls) == 3


def test_l2_guasto_pre_calibrazione_non_produce_righe_di_richiesta(monkeypatch):
    """L'altro ramo del protocollo: guasto nella calibrazione pre e il
    blocco non ha prodotto nessuna richiesta. Nessuna riga deve entrare nel
    CSV; l'invalidazione vive SOLO nel riepilogo di blocco, che pero' c'e'
    ed e' completo dei tre campi. Se il runner esportasse le fault.rows
    anche quando il guasto e' pre, il fake dovrebbe averle fornite: qui non
    ce ne sono e il conteggio dei record resta quello dei soli blocchi
    completati."""
    sink = {}

    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            return _fault(kw)  # rows=None: pre-calibrazione
        return _ok(kw)

    calls, summaries, _meta, out = _run(
        monkeypatch, impl,
        [{"id": "p1", "text": "t1"}], blocks=2,
        stub_args={"k": "2", "seed": "seme-l2"}, sink=sink)

    assert all(len(batch) == 0 for batch in sink["rows"]), \
        "il blocco caduto pre-calibrazione non ha righe da esportare"
    assert out["records"] == 0
    inv = [s for s in summaries if s.get("invalid_reason")]
    assert len(inv) == 1
    assert inv[0]["block_attempt"] == 1
    assert inv[0]["invalid_reason"] == "delta_negativo"
    assert inv[0]["replaced_block_id"] == ""
    # il sostituto, quando fallito a sua volta, porterebbe replaced_block_id
    # del caduto: qui riesce, e la sua chiamata lo dichiara
    sub = next(c for c in calls if c["block_id"].endswith("__s2"))
    assert sub["replaced_block_id"] == "m__p1__b01"
    assert sub["block_attempt"] == 2


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
