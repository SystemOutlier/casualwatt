# -*- coding: utf-8 -*-
"""
tests/test_budget_p44_preesecuzione.py — il budget del gate e' una MISURA
alla scala del controllo, non una riscalatura.

Perche' esiste. La revisione del gate del 2026-11-09 ha rimosso da
``tools/run_gate_p44.py`` la forma provvisoria

    B_short = B_long * (Tc / 30)

perche' non e' una stima del fondo sulla scala breve: e' un coefficiente
applicato a una grandezza misurata su un'altra scala, e nessuna misura
giustifica quel coefficiente. Questo file prova le due procedure ammesse al
posto di quel coefficiente, e le prova alla scala della formula — non
all'orchestrazione, che sta in ``test_gate_p44_end_to_end.py``.

Che cosa verifica:
  1. ``budget_short``: tre finestre idle di durata nominale Tc pre e tre
     post, lette dal primitivo ``read_idle_window_j`` (contatore di
     package), aggregate da ``benchmark_v4.block_baseline`` verbatim — cioe'
     le STESSE regole di aggregazione del budget lungo applicate a finestre
     brevi — con il numero che esce dall'aritmetica dichiarata e nessun
     fattore Tc/30 applicato;
  2. ``budget_matched``: N = ceil(30 s / Tc) finestre Tc CONSECUTIVE per
     aggregato, potenza dell'aggregato = somma(delta_j)/somma(dt_s) (non la
     media delle potenze), tre aggregati pre e tre post, e il numero di
     finestre realmente usate documentato; un campione singolo non e' mai
     un'unita';
  3. le guardie: lettura assente, delta negativo, dt non positivo, canali
     misti, Tc sotto il pavimento del primitivo, procedura non dichiarata,
     terna degenerata — ognuna ferma la misura con la propria ragione prima
     di produrre qualunque numero, e nessuna degrada a un derivato;
  4. la pre-registrazione: il piano porta i parametri della procedura e la
     verifica del piano rifiuta l'esecuzione se divergono, PRIMA di
     qualunque misura;
  5. le componenti di u_c pre-esecuzione, ciascuna riproducibile a mano
     dalla formula che la dichiara, con le durate osservate realmente lette;
  6. il warm-up post-carico come criterio misurato su DUE segnali nella
     stessa finestra (potenza del contatore entro ``tolerance_w`` dalla
     baseline e media di finestra di ``cpu_percent`` sotto ``cpu_max_pct``):
     permanenza continua, azzeramento del tratto su campione fuori soglia di
     UN qualunque dei due o su lettura assente, disuguaglianza stretta su
     entrambi, tetto che ferma la campagna registrando prima il record,
     temperatura registrata all'ingresso e all'uscita senza decidere niente,
     e target preso dalla baseline del blocco di carico;
  7. la provenienza delle due soglie: le finestre del criterio sono
     ricalcolate sugli artefatti tracciati della seconda campagna
     (``control_power_series.json`` + ``blocks_controllo.json``) e le
     disuguaglianze documentate nel modulo devono essere quelle che escono
     dal ricalcolo — comprese le due finestre opposte del transitorio, che
     è ciò che rende necessario il secondo segnale.

Che cosa NON verifica: il criterio F.12 in se'
(``test_control_gate_p45.py``), l'orchestrazione del tool
(``test_gate_p44_end_to_end.py``), la meccanica del primitivo
``read_idle_window_j`` (``test_energy_corrections.py`` e i test EMI).
"""
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
import run_gate_p44 as rg  # noqa: E402

# Tc congelata dal pilota P2.9 (requisito 5): la scala del controllo e'
# questa, e i test la usano senza accorciarla perche' qui si prova la
# procedura, non la velocita' della suite. Il fake non dorme: la durata e'
# un numero dichiarato nella lettura, non un tempo reale.
TC = 2.930748
PRE = [9.9, 10.0, 10.1]
POST = [10.3, 10.4, 10.5]
BW = round(math.hypot(0.1, 0.2), 6)      # 0,223607 W


class _Porta:
    """Il primitivo ``read_idle_window_j`` con letture decise dal test.

    Ogni lettura e' ``(delta_j, dt_s, canale)`` o ``None``. La porta conta
    le chiamate e le durate richieste: e' cosi' che si verifica che il tool
    legga alla scala Tc e non a 30 s, e che le guardie scattino PRIMA di
    leggere qualunque cosa.
    """

    def __init__(self, letture, method="emi-counter", errore=""):
        self.letture = list(letture)
        self.chiamate: list = []
        self.method = method
        self.last_read_error = errore

    def read_idle_window_j(self, durata_s):
        self.chiamate.append(float(durata_s))
        if not self.letture:
            raise AssertionError(
                "il fake ha esaurito le letture: il tool ha chiesto piu' "
                "finestre di quante il test ne abbia registrate")
        lettura = self.letture.pop(0)
        if lettura is None:
            return None
        delta_j, dt_s, canale = lettura
        return (delta_j, dt_s, canale)


def _sessione(*letture, method="emi-counter", errore=""):
    return SimpleNamespace(_source=_Porta(list(letture), method, errore))


def _letta(potenza, dt=None, canale="emi-counter"):
    """Una finestra idle alla potenza ``potenza`` su durata ``dt``."""
    dt = TC if dt is None else dt
    return (potenza * dt, dt, canale)


def _corpo(pre, post, **kw):
    """Sessione con le terne ``pre``/``post`` a scala Tc."""
    return _sessione(*[_letta(p) for p in pre],
                     *[_letta(p) for p in post], **kw)


# ---------------------------------------------------------------------------
# 1. budget_short: misura a scala Tc, stesse regole del budget lungo
# ---------------------------------------------------------------------------
def test_short_legge_finestre_alla_scala_del_controllo():
    """Il fondo deve essere letto su finestre della durata nominale del
    controllo: se il tool leggesse a 30 s e riscalasse, la durata richiesta
    al primitivo sarebbe 30,0 — e questa asserzione lo vedrebbe."""
    s = _corpo(PRE, POST)
    budget, det = rg._calcola_budget_pre_esecuzione("short", s)
    assert s._source.chiamate == [TC] * 6
    assert det["budget_mode"] == "short"
    assert det["tc_duration_s"] == pytest.approx(TC)
    assert det["n_terne"] == 3
    assert det["n_per_aggregato"] == 1
    assert det["n_finestre_usate"] == 6
    assert det["durata_totale_misura_s"] == pytest.approx(6 * TC)
    assert budget > 0.0


def test_short_budget_e_aritmetica_dichiarata_senza_fattore_di_scala():
    """Il numero E' ``hypot((max-min)/2, |mediana(post)-mediana(pre)|/2)``
    sulle potenze lette a scala Tc: 0,223607 W con le terne di sopra.
    La prova contro la riscalatura e' la terza asserzione: il valore che
    ``B_long * (Tc/30)`` avrebbe dato non e' il valore prodotto."""
    s = _corpo(PRE, POST)
    budget, det = rg._calcola_budget_pre_esecuzione("short", s)
    assert budget == pytest.approx(BW, abs=1e-6)
    assert det["scala_30_s_applicata"] is False
    assert det["codecarbon_usato"] is False
    # cosa avrebbe dato il coefficiente rimosso, sulla stessa dispersione
    riscalato = BW * (TC / 30.0)
    assert budget != pytest.approx(riscalato)
    assert det["budget_base_w"] == pytest.approx(budget)


def test_short_usa_le_stesse_regole_di_aggregazione_del_budget_lungo():
    """"Stesse regole di aggregazione" deve essere verificabile, non
    dichiarata: qui la regola e' ``block_baseline`` chiamata verbatim sulle
    potenze che il tool ha letto, e il budget del tool coincide con il suo
    output. Se il tool implementsse una regola propria divergerebbe."""
    s = _corpo(PRE, POST)
    budget, det = rg._calcola_budget_pre_esecuzione("short", s)
    atteso = v4.block_baseline(PRE, POST)
    assert float(det["budget_base_w"]) == pytest.approx(
        float(atteso["budget_base_w"]))
    assert det["unita_pre_w"] == [pytest.approx(p) for p in PRE]
    assert det["unita_post_w"] == [pytest.approx(p) for p in POST]
    assert det["regola_aggregazione"].find("block_baseline") >= 0
    for chiave in ("baseline_pre_w", "half_range_pre_w", "half_drift_w"):
        assert det["baseline"][chiave] == atteso[chiave]


def test_short_delta_negativo_ferma_senza_clampare():
    """Su una finestra idle un decremento del contatore e' un reset, non un
    fondo. La regola "nessun troncamento" qui si legge al contrario: il
    valore non si clampa a zero e non entra nel budget — la misura si
    ferma. Un clamp avrebbe prodotto un budget piu' piccolo, cioe' una
    soglia piu' severa inventata."""
    letture = [_letta(9.9), (-5.0, TC, "emi-counter"), _letta(10.1),
               _letta(10.3), _letta(10.4), _letta(10.5)]
    s = _sessione(*letture)
    with pytest.raises(SystemExit) as exc:
        rg._calcola_budget_pre_esecuzione("short", s)
    assert "decrescente" in str(exc.value)
    # la terza finestra pre non viene letta: la guardia ferma li'
    assert len(s._source.chiamate) == 2


def test_short_lettura_assente_ferma_con_la_ragione():
    """Nessun fallback silenzioso: senza contatore il budget non esiste e
    la campagna non parte. La ragione del primitivo (``last_read_error``)
    deve arrivare nel messaggio, perche' 'accesso negato' e 'nessun
    backend' sono due cose diverse da riparare."""
    porta = _Porta([None] * 6, method="unavailable",
                   errore="access_denied")
    with pytest.raises(SystemExit) as exc:
        rg._calcola_budget_pre_esecuzione("short",
                                          SimpleNamespace(_source=porta))
    msg = str(exc.value)
    assert "nessun contatore" in msg
    assert "access_denied" in msg


def test_short_dt_non_positivo_ferma():
    """Una finestra senza durata non ha potenza: la divisione delta/dt non
    e' definibile e un dt <= 0 dal primitivo e' una lettura rotta, non
    fondo zero."""
    porta = _Porta([(10.0 * TC, 0.0, "emi-counter")])
    with pytest.raises(SystemExit) as exc:
        rg._calcola_budget_pre_esecuzione("short",
                                          SimpleNamespace(_source=porta))
    assert "non positivo" in str(exc.value)


def test_short_canali_misti_fermano_la_misura():
    """Un budget composto da letture di origine diversa non e' una misura:
    le due catene hanno scale e privilegi diversi, e la soglia nascerebbe
    da una composizione non dichiarata."""
    letture = [_letta(p, canale="emi-counter") for p in PRE]
    letture += [_letta(p, canale="pawnio-counter") for p in POST]
    s = _sessione(*letture)
    with pytest.raises(SystemExit) as exc:
        rg._calcola_budget_pre_esecuzione("short", s)
    assert "canali misti" in str(exc.value)


def test_guardie_sulla_procedura_prima_di_leggere(monkeypatch):
    """Tre precondizioni sulla procedura, ciascuna anteriore a qualunque
    lettura: il pavimento del primitivo (energy_session.py:672 porta la
    finestra a 0,5 s, quindi un Tc piu' piccolo di cosi' non esiste e non
    si spaccia per Tc), la procedura non dichiarata, la terna degenerata
    (una semi-ampiezza su un campione solo non e' dispersione)."""
    s = _corpo(PRE, POST)
    monkeypatch.setattr(rg, "DT_NOM_FROZEN", 0.05)
    with pytest.raises(SystemExit) as exc:
        rg._calcola_budget_pre_esecuzione("short", s)
    assert "pavimento" in str(exc.value)
    assert s._source.chiamate == []          # nessun numero prodotto
    monkeypatch.undo()

    s2 = _corpo(PRE, POST)
    with pytest.raises(SystemExit) as exc2:
        rg._calcola_budget_pre_esecuzione("rescaled-30s", s2)
    assert "non ammesso" in str(exc2.value)
    assert s2._source.chiamate == []

    monkeypatch.setattr(rg, "BUDGET_N_TERNE", 1)
    s3 = _corpo(PRE, POST)
    with pytest.raises(SystemExit) as exc3:
        rg._calcola_budget_pre_esecuzione("short", s3)
    assert "non e' una misura di dispersione" in str(exc3.value)
    assert s3._source.chiamate == []


# ---------------------------------------------------------------------------
# 2. budget_matched: aggregato consecutivo a durata equivalente, mai un
#    campione singolo
# ---------------------------------------------------------------------------
def test_matched_documenta_le_finestre_usate():
    """N = ceil(30 s / Tc) = 11 finestre consecutive per aggregato, tre
    aggregati pre e tre post: 66 finestre da 2,930748 s. Il numero reale
    usato deve essere leggibile nell'artefatto, non dedotto."""
    unita = [_letta(p) for p in PRE for _ in range(11)]
    unita += [_letta(p) for p in POST for _ in range(11)]
    s = _sessione(*unita)
    budget, det = rg._calcola_budget_pre_esecuzione("matched", s)
    n_atteso = math.ceil(rg.BUDGET_MATCHED_TARGET_S / TC)
    assert n_atteso == 11
    assert det["n_per_aggregato"] == 11
    assert det["durata_aggregato_s"] == pytest.approx(11 * TC)
    assert det["n_finestre_usate"] == 66
    assert len(det["aggregati_pre"]) == 3
    assert all(a["n_finestre"] == 11 for a in det["aggregati_pre"]
               + det["aggregati_post"])
    assert det["scala_30_s_applicata"] is False


def test_matched_aggregato_e_somma_energia_per_somma_tempo():
    """L'aggregato conta per la sua energia: somma(delta_j)/somma(dt_s).
    Con 30 J su 10 s e 10 J su 2 s la potenza dell'aggregato e' 40/12 =
    3,3333 W, mentre la media delle due potenze sarebbe 4,0 W e darebbe
    peso uguale a campioni di durata diversa."""
    w1 = rg._finestra_idle(_sessione((30.0, 10.0, "emi-counter")), 10.0,
                           "a")
    w2 = rg._finestra_idle(_sessione((10.0, 2.0, "emi-counter")), 2.0, "b")
    agg = rg._aggregato_consecutivo([w1, w2], "agg")
    assert agg["power_w"] == pytest.approx(40.0 / 12.0)
    assert agg["power_w"] != pytest.approx(4.0)
    assert agg["delta_j"] == pytest.approx(40.0)
    assert agg["dt_s"] == pytest.approx(12.0)
    assert agg["n_finestre"] == 2
    assert agg["durata_nominale_s"] == pytest.approx(12.0)


def test_matched_budget_dalla_dispersione_degli_aggregati():
    """Le tre unita' che entrano in ``block_baseline`` sono gli aggregati,
    non le finestre: con potenze degli aggregati 9,9/10,0/10,1 pre e
    10,3/10,4/10,5 post il budget e' di nuovo 0,223607 W, e questo prova
    che l'aggregazione non cambia il numero — cambia la durata su cui ogni
    unita' e' misurata."""
    unita = [_letta(p) for p in PRE for _ in range(11)]
    unita += [_letta(p) for p in POST for _ in range(11)]
    s = _sessione(*unita)
    budget, det = rg._calcola_budget_pre_esecuzione("matched", s)
    assert det["unita_pre_w"] == [pytest.approx(p) for p in PRE]
    assert budget == pytest.approx(BW, abs=1e-6)
    assert float(det["baseline"]["baseline_pre_w"]) == pytest.approx(10.0)


def test_matched_non_usa_mai_un_campione_singolo(monkeypatch):
    """Anche con un obiettivo di durata che il quoziente renderebbe 1,
    l'unita' resta almeno due finestre: un campione breve da solo non e'
    mai un budget, perche' la sua semi-ampiezza di dispersione sarebbe
    zero per costruzione."""
    monkeypatch.setattr(rg, "BUDGET_MATCHED_TARGET_S", TC)
    n_min = max(2, math.ceil(TC / TC))
    unita = [_letta(p) for p in PRE for _ in range(n_min)]
    unita += [_letta(p) for p in POST for _ in range(n_min)]
    s = _sessione(*unita)
    _budget, det = rg._calcola_budget_pre_esecuzione("matched", s)
    assert det["n_per_aggregato"] == 2
    assert det["durata_aggregato_s"] == pytest.approx(2 * TC)
    assert det["n_finestre_usate"] == 12
    assert len(s._source.chiamate) == 12


def test_matched_aggregato_con_dt_totale_non_positivo_ferma():
    """Un aggregato la cui somma dei tempi non e' positiva non ha potenza:
    si ferma, non si scrive 0 W come se fosse un fondo perfetto."""
    w1 = rg._finestra_idle(_sessione((5.0, 2.0, "emi-counter")), 2.0, "a")
    w2 = dict(w1, label="b", dt_s=-2.0)
    with pytest.raises(SystemExit) as exc:
        rg._aggregato_consecutivo([w1, w2], "agg-rotto")
    assert "dt totale" in str(exc.value)


# ---------------------------------------------------------------------------
# 3. pre-registrazione: la procedura sta nel piano e il piano la verifica
# ---------------------------------------------------------------------------
def test_piano_porta_la_procedura_di_budget_e_il_warmup():
    """Il requisito dice "pre-registrata nel piano": i parametri devono
    essere nel payload numerico, non solo nella prosa, perche' la verifica
    confronta i numeri. E la check G deve nominare la procedura esclusa,
    cioe' che CodeCarbon non corregge il budget."""
    piano = rg.plan_payload()
    assert piano["budget_mode"] == rg.BUDGET_MODE
    assert piano["budget_n_terne"] == rg.BUDGET_N_TERNE
    assert piano["budget_matched_target_s"] == rg.BUDGET_MATCHED_TARGET_S
    assert piano["budget_floor_finestra_s"] == rg.BUDGET_FLOOR_FINESTRA_S
    assert piano["warmup_tolerance_w"] == rg.WARMUP_TOLERANCE_W
    assert piano["warmup_cpu_max_pct"] == rg.WARMUP_CPU_MAX_PCT
    assert piano["warmup_sustain_s"] == rg.WARMUP_SUSTAIN_S
    assert piano["warmup_cap_s"] == rg.WARMUP_CAP_S
    assert piano["warmup_step_s"] == rg.WARMUP_STEP_S
    assert piano["warmup_window_s"] == rg.WARMUP_WINDOW_S
    assert rg.BUDGET_MODE in ("short", "matched")
    # ogni check deve essere UNA stringa: una virgola di troppo nella
    # composizione letterale la rende una tupla, e il plan.json consegnato
    # stamperebbe "('...', '...')" invece della frase di protocollo
    assert all(isinstance(testo, str) for testo in piano["checks"].values())
    assert "CodeCarbon" in piano["checks"]["G"]
    assert piano["checks"]["G"].find(rg.BUDGET_MODE.upper()) >= 0
    # nessuna forma riscalata ammessa nella prosa della procedura
    assert "Tc / 30" not in piano["checks"]["G"]
    assert "sleep(10" in piano["checks"]["F"]     # dice cosa e' stato tolto


def test_verifica_piano_rifiuta_la_procedura_diversa_da_quella_dichiarata(
        tmp_path, monkeypatch):
    """Esecuzione ammessa solo contro la procedura dichiarata: se
    ``budget_mode`` diverge, il tool si ferma PRIMA di misurare. Un piano
    ritirato a posteriori per cambiare procedura sarebbe lo stesso difetto
    di una soglia spostata dopo i dati."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    # Create idle_characterization.json first (required by plan v2)
    _create_idle_characterization(tmp_path)
    # cmd_plan non scrive un piano senza provenienza: qui il soggetto e' la
    # procedura di budget, quindi git_head e' iniettato (la guardia sulla
    # provenienza sta in tests/test_preflight_gate_p44.py).
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    rg.cmd_plan(rg.DEFAULT_MODEL)
    path = tmp_path / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    piano["budget_mode"] = ("matched" if piano["budget_mode"] == "short"
                            else "short")
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    assert "procedura di budget" in str(exc.value)

    piano2 = json.loads(path.read_text(encoding="utf-8"))
    piano2["budget_mode"] = rg.BUDGET_MODE
    piano2["budget_n_terne"] = 99
    path.write_text(json.dumps(piano2), encoding="utf-8")
    with pytest.raises(SystemExit):
        rg._verifica_piano()


def _create_idle_characterization(output_dir):
    """Create a valid idle_characterization.json for testing."""
    import hashlib
    char_data = {
        "schema_version": 1,
        "quiet_threshold_pct": 8.0,
        "warmup_cpu_max_pct": 8.0,
        "quiet_consecutive": 3,
        "quiet_window_s": 3.0,
        "quiet_cap_s": 600.0,
        "timestamp": "2026-11-14T00:00:00Z",
        "machine_id": "test-machine",
        "windows": 30,
        "window_s": 10.0,
        "cpu_samples": [2.0] * 30,
        "q95_cpu_pct": 2.0,
        "margin_pct": 1.0,
        "sha256": "",
    }
    hash_dict = {k: v for k, v in char_data.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    char_data["sha256"] = hashlib.sha256(hash_text).hexdigest()
    (output_dir / "idle_characterization.json").write_text(json.dumps(char_data))


def test_verifica_piano_rifiuta_warmup_cpu_max_diverso(monkeypatch,
                                                       tmp_path):
    """La soglia di ``cpu_percent`` e' un numero del disegno quanto la
    tolleranza di potenza: se il piano ne dichiara una e il codice ne applica
    un'altra, la campagna gira con un criterio diverso da quello
    pre-registrato, e la cosa si vede solo dopo i dati. Qui la guardia deve
    fermarla PRIMA, sulla chiave specifica, e deve farlo anche quando la
    chiave manca del tutto (un piano vecchio non conosce il secondo
    segnale)."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    _create_idle_characterization(tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    path = tmp_path / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    piano["warmup_cpu_max_pct"] = 99.0
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    assert "warmup_cpu_max_pct" in str(exc.value)
    assert "warm-up" in str(exc.value)

    piano2 = json.loads(path.read_text(encoding="utf-8"))
    del piano2["warmup_cpu_max_pct"]
    path.write_text(json.dumps(piano2), encoding="utf-8")
    with pytest.raises(SystemExit) as exc2:
        rg._verifica_piano()
    assert "warmup_cpu_max_pct" in str(exc2.value)


def test_piano_con_soglia_cpu_derivata_passa(monkeypatch, tmp_path):
    """Il nuovo contratto: la soglia cpu del warm-up non e' la costante
    legacy 2,0 ma il valore che la caratterizzazione idle dichiara
    (ceil(q95 + margine)). Un piano che riporta esattamente quel valore e'
    coerente con la propria fonte e deve passare: la guardia cerca la
    divergenza, non il valore. Questo e' il lato di accettazione della
    coppia con il test sopra: se qualcuno reintroduce il confronto con la
    costante, qui il run si ferma su un piano legittimo."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    _create_idle_characterization(tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    piano = json.loads((tmp_path / rg.PLAN_NAME).read_text(encoding="utf-8"))
    char = json.loads(
        (tmp_path / "idle_characterization.json").read_text(encoding="utf-8"))
    assert piano["warmup_cpu_max_pct"] == char["warmup_cpu_max_pct"]
    piano_verificato = rg._verifica_piano()
    assert piano_verificato["warmup_cpu_max_pct"] == char["warmup_cpu_max_pct"]


def test_caratterizzazione_rigenerata_dopo_il_piano_blocca(monkeypatch,
                                                           tmp_path):
    """Il piano pinna l'hash della caratterizzazione da cui discende. Se il
    file viene rigenerato DOPO il piano (altra q95, altra soglia cpu, altre
    finestre), il piano dichiarato e la caratterizzazione su disco non sono
    piu' la stessa cosa, e la campagna girerebbe con un warm-up diverso da
    quello pre-registrato. La guardia deve fermarla PRIMA, nominando
    l'hash: e' la catena di provenienza piano -> caratterizzazione, che il
    piano scrive ma nulla enforcementava."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    _create_idle_characterization(tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    piano = json.loads((tmp_path / rg.PLAN_NAME).read_text(encoding="utf-8"))
    sha_piano = piano["idle_characterization_sha256"]
    # Rigenerazione post-piano: contenuto diverso, proprio sha256 aggiornato
    import hashlib
    char = json.loads(
        (tmp_path / "idle_characterization.json").read_text(encoding="utf-8"))
    char["quiet_threshold_pct"] = 42.0
    char["warmup_cpu_max_pct"] = 42.0
    hash_dict = {k: v for k, v in char.items() if k != "sha256"}
    char["sha256"] = hashlib.sha256(json.dumps(
        hash_dict, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "idle_characterization.json").write_text(json.dumps(char))
    assert char["sha256"] != sha_piano
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    assert "idle_characterization_sha256" in str(exc.value)


def test_caratterizzazione_manomessa_nel_contenuto_blocca(monkeypatch,
                                                          tmp_path):
    """Il campo sha256 del file viene riscritto per farlo combaciare con il
    piano, ma il CONTENUTO no: l'hash si ricalcola dal contenuto, non ci si
    fida del campo. Una caratterizzazione manipolata deve essere respinta
    anche quando il suo campo sha256 e' allineato al piano."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    _create_idle_characterization(tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    monkeypatch.setattr(rg, "_git_antenato", lambda sha: True)
    monkeypatch.setattr(rg, "_git_percorso_misura_mutato", lambda sha: False)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    piano = json.loads((tmp_path / rg.PLAN_NAME).read_text(encoding="utf-8"))
    sha_piano = piano["idle_characterization_sha256"]
    char = json.loads(
        (tmp_path / "idle_characterization.json").read_text(encoding="utf-8"))
    char["q95_cpu_pct"] = 99.0          # contenuto manomesso
    char["warmup_cpu_max_pct"] = 99.0
    char["sha256"] = sha_piano          # campo allineato a forza
    (tmp_path / "idle_characterization.json").write_text(json.dumps(char))
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    assert "idle_characterization_sha256" in str(exc.value)


def test_artefatto_del_budget_e_completo_di_assunzioni(tmp_path, monkeypatch):
    """L'artefatto nasce prima dei blocchi e porta il numero, la procedura,
    le finestre lette e le assunzioni dichiarate: chi rilegge la campagna
    deve potere riprodurre il numero dai soli campi scritti."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    s = _corpo(PRE, POST)
    budget, det = rg._calcola_budget_pre_esecuzione("short", s)
    path = rg._scrivi_budget_preregistrato(budget, det)
    assert path == tmp_path / rg.BUDGET_PREREG_NAME
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    body = payload["budget_preregistrato"]
    assert body["budget_base_w"] == pytest.approx(BW, abs=1e-6)
    assert body["scala_30_s_applicata"] is False
    assert body["codecarbon_usato"] is False
    assert len(body["finestre_pre"]) == 3
    assert len(body["finestre_post"]) == 3
    assert len(body["assunzioni"]) >= 5
    assert body["calcolato_utc"]


# ---------------------------------------------------------------------------
# 4. u_c pre-esecuzione: ogni componente si riproduce dalla sua formula
# ---------------------------------------------------------------------------
def _budget_per_u_c(dt_offset=0.0):
    """Sessione con durate osservate spostate di ``dt_offset`` dal nominale."""
    potenze = PRE + POST
    letture = []
    for i, p in enumerate(potenze):
        dt = TC + (dt_offset if i % 2 == 0 else 0.0)
        letture.append((p * TC, dt, "emi-counter"))
    return _sessione(*letture)


def test_componenti_u_c_ripetibili_a_mano():
    """Le quattro componenti non sono etichette: ognuna e' ricalcolata nel
    test dai numeri misurati (potenze lette, durate osservate, risoluzione
    del timer) e coincide con la formula che dichiara. Se una componente
    fosse un valore d'esempio, divergerebbe."""
    s = _budget_per_u_c(dt_offset=0.02)
    budget, det = rg._calcola_budget_pre_esecuzione("short", s)
    b = det["baseline"]
    fondo = float(b["baseline_pre_w"])
    dts = [f["dt_s"] for f in det["finestre_pre"] + det["finestre_post"]]
    dt_min = min(dts)
    dev_max = max(abs(dt - TC) for dt in dts)
    risol = 0.0156

    inc = rg._incertezza_pre_esecuzione(det, risol)
    c = inc["componenti"]
    assert c["u_rumore"]["value"] == pytest.approx(
        float(b["half_range_pre_w"]))
    assert c["u_termico"]["value"] == pytest.approx(float(b["half_drift_w"]))
    assert c["u_timer"]["value"] == pytest.approx(
        fondo * (risol / 2.0) / dt_min)
    assert c["u_allineamento"]["value"] == pytest.approx(
        fondo * dev_max / dt_min)
    assert dev_max == pytest.approx(0.02)
    # Nessuna componente indipendente dal budget prima dei controlli: u_c e'
    # None (non zero) e la soglia e' il budget, NON budget + k * u_c.
    # u_rumore e u_termico sono i due termini di budget_base_w: includerli
    # avrebbe dato S >= 3 * budget (doppio conteggio).
    assert inc["u_c"] is None
    assert inc["soglia_w"] == pytest.approx(budget)
    assert inc["k"] is None and inc["U_w"] is None
    assert budget == pytest.approx(math.hypot(
        c["u_rumore"]["value"], c["u_termico"]["value"]), abs=1e-6)
    assert inc["u_A"] is None
    assert "non calcolabile prima dei controlli" in inc["nota_u_A"]
    assert all(c[nome]["fonte"] for nome in c)
    assert inc["codecarbon_usato"] is False


def test_u_timer_non_misurabile_resta_assente_non_zero():
    """None non e' zero: se la risoluzione del timer non e' misurabile la
    componente esce dalla somma in quadratura, e la soglia che ne risulta
    e' quella delle componenti rimaste — ma dichiarata come tale. Mettere
    uno zero vorrebbe dire restringere la soglia senza fondamento; qui la
    differenza e' misurata."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _budget_per_u_c(dt_offset=0.02))[1]
    inc = rg._incertezza_pre_esecuzione(det, None)
    assert inc["componenti"]["u_timer"]["value"] is None
    assert "non misurabile" in inc["componenti"]["u_timer"]["fonte"]
    assert inc["componenti"]["u_timer"]["inclusa"] is False
    # l'assenza non cambia la soglia (nessuna componente indipendente e'
    # inclusa prima dei controlli) e non si trasforma in uno zero
    assert inc["u_c"] is None
    assert inc["soglia_w"] == pytest.approx(det["budget_base_w"])


def test_u_A_arriva_dopo_sui_soli_controlli_utilizzabili():
    """La quinta componente nasce dai controlli di F.12 con lo stesso filtro
    ``usable`` del bias: dispersione su una popolazione diversa darebbe un
    numero non confrontabile. E' semi-ampiezza fra blocchi, non la sigma
    delle terne (P4.12), e non sostituisce il budget."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _budget_per_u_c(dt_offset=0.02))[1]
    inc_pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    controls = [
        {"usable": True, "e_net_j": 0.30, "dt_w_s": 3.0},    # 0,10 W
        {"usable": True, "e_net_j": 0.12, "dt_w_s": 3.0},    # 0,04 W
        {"usable": False, "e_net_j": 9.00, "dt_w_s": 3.0},   # esclusa
        {"usable": True, "e_net_j": 1.00, "dt_w_s": 0.0},    # dt non valido
    ]
    inc_post = rg._incertezza_con_au_controlli(inc_pre, controls)
    # u_A = s / sqrt(n) sulle potenze 0,10 e 0,04 W: s = 0,0424264, n = 2
    assert inc_post["u_A"] == pytest.approx(0.03)
    assert inc_post["potenze_nette_w"] == [pytest.approx(0.10),
                                           pytest.approx(0.04)]
    assert inc_post["budget_base_w"] == inc_pre["budget_base_w"]
    assert inc_post["componenti"]["u_A"]["value"] == inc_post["u_A"]
    assert "s / sqrt(n)" in inc_post["componenti"]["u_A"]["formula"]
    assert inc_post["componenti"]["u_A"]["tipo"] == "A"
    assert inc_post["componenti"]["u_A"]["inclusa"] is True
    # u_c = u_A (unica componente inclusa); U = t(0,975; 1) * u_c
    assert inc_post["u_c"] == pytest.approx(0.03)
    assert inc_post["k"] == pytest.approx(12.706, rel=1e-3)
    assert inc_post["U_w"] == pytest.approx(12.706 * 0.03, rel=1e-3)
    # la soglia del criterio primario non viene maggiorata
    assert inc_post["soglia_w"] == inc_pre["budget_base_w"]
    assert inc_post["codecarbon_usato"] is False


def test_u_A_assente_con_un_solo_controllo_utilizzabile():
    """Un blocco solo non da' dispersione fra blocchi: la componente resta
    None con la sua ragione, e non viene sostituita da una semi-ampiezza
    fittizia o da zero."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _budget_per_u_c(dt_offset=0.02))[1]
    inc_pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    inc_post = rg._incertezza_con_au_controlli(
        inc_pre, [{"usable": True, "e_net_j": 0.3, "dt_w_s": 3.0}])
    assert inc_post["u_A"] is None
    assert "almeno una coppia" in inc_post["componenti"]["u_A"]["fonte"]


# ---------------------------------------------------------------------------
# 5. warm-up post-carico: criterio misurato su DUE segnali nella finestra
# ---------------------------------------------------------------------------
class _Orologio:
    def __init__(self, passo=1.0):
        self.t = 0.0
        self.passo = passo
        self.dormito: list = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.dormito.append(s)
        self.t += s


def _sequenza(valori, nome):
    """Lettore che consuma una lettura per chiamata e grida se ne chiede una
    piu' di quante il test ne abbia dichiarate."""
    seq = list(valori)

    def read():
        if not seq:
            raise AssertionError(
                f"il warm-up ha letto piu' campioni di {nome} del dichiarato")
        return seq.pop(0)

    return read


def _stabilizza(target, potenze, cpu_finestre, *, tolerance_w=0.5,
                cpu_max_pct=2.0, sustain_s=3.0, cap_s=60.0, passo=1.0,
                temperatura=(27.85, "fake:MSAcpi_ThermalZoneTemperature"),
                registri=None, orologio=None, termiche=None) -> dict:
    """Esegue il criterio con TUTTE le sorgenti iniettate.

    Potenza, ``cpu_percent``, temperatura, orologio, sonno e registro sono
    parametri: nessun test di questa sezione tocca la macchina reale, e
    ``legge_temperatura`` e' iniettato proprio perche' il ramo vero apre un
    ``subprocess`` (powershell + CIM), che sotto la cattura dei fd di pytest e'
    un'``OSError(22)`` nota e non un fallimento del criterio.
    """
    orologio = orologio if orologio is not None else _Orologio(passo=passo)
    chiamate_termiche: list = []

    def leggi_temperatura():
        chiamate_termiche.append(orologio.t)
        return temperatura

    finestre_cpu = [[] if c is None else [c] for c in cpu_finestre]
    esito = rg._stabilizza_post_carico(
        target, tolerance_w=tolerance_w, cpu_max_pct=cpu_max_pct,
        sustain_s=sustain_s, cap_s=cap_s, step_s=passo, window_s=2.0,
        campiona_potenza=_sequenza(potenze, "potenza"),
        campiona_cpu=_sequenza(finestre_cpu, "cpu_percent"),
        legge_temperatura=leggi_temperatura,
        registra=(registri.append if registri is not None else None),
        clock=orologio.now, sleep=orologio.sleep)
    if termiche is not None:
        termiche.extend(chiamate_termiche)
    return esito


def test_warmup_si_compone_dopo_la_permanenza_continua_dei_due_segnali():
    """Il criterio chiede ``sustain_s`` CONTINUI con entrambi i segnali entro
    soglia: quattro campioni a passo 1 s chiudono una permanenza di 3 s. La
    durata registrata e' il tempo reale della stabilizzazione, non un
    parametro: la forma fissa ``sleep(10)`` avrebbe dormito 7 s piu' del
    necessario su questa macchina gia' rientrata."""
    esito = _stabilizza(10.0, [10.4, 10.4, 10.4, 10.4], [1.0, 1.0, 1.0, 1.0])
    assert esito["warmup_completed"] is True
    assert esito["warmup_motivo"] == "criterio_soddisfatto"
    assert esito["warmup_duration_s"] == pytest.approx(3.0)
    assert esito["warmup_duration_s"] != rg.WARMUP_SUSTAIN_S
    assert esito["warmup_campioni"] == 4
    assert esito["warmup_target_pre_w"] == 10.0
    assert esito["warmup_soglia_w"] == 0.5
    assert esito["warmup_soglia_cpu_pct"] == 2.0
    assert esito["warmup_finestra_s"] == 2.0
    assert esito["warmup_tetto_s"] == 60.0
    assert esito["warmup_permanenza_richiesta_s"] == 3.0
    assert esito["warmup_valori_w"] == [10.4] * 4
    assert esito["warmup_valori_cpu_pct"] == [1.0] * 4
    assert esito["warmup_letture_mancanti"] == 0


def test_warmup_cpu_fuori_soglia_azzera_il_tratto_con_potenza_in_banda():
    """E' il caso della PRIMA finestra di ctrl-1: potenza rientrata (dev
    0,48 W < 0,5) e cpu al 4,1 % sopra la soglia. Un criterio solo sulla
    potenza avrebbe chiuso qui e avrebbe immesso il controllo in transitorio.
    Il tratto si azzera e l'escursione resta nella serie, perche' la serie
    registra quel che e' stato letto, non solo quel che e' passato."""
    esito = _stabilizza(10.0, [10.4, 10.4, 10.4, 10.4, 10.4],
                        [4.1, 1.0, 1.0, 1.0, 1.0])
    assert esito["warmup_completed"] is True
    assert esito["warmup_campioni"] == 5
    assert esito["warmup_duration_s"] == pytest.approx(4.0)
    assert 4.1 in esito["warmup_valori_cpu_pct"]
    assert esito["warmup_valori_w"] == [10.4] * 5


def test_warmup_potenza_fuori_tolleranza_azzera_il_tratto_con_cpu_in_banda():
    """E' il caso della SECONDA finestra di ctrl-1: cpu all'1,8 % (sotto 2,0)
    e deviazione di 0,80 W sopra la tolleranza. Un criterio solo sulla cpu
    avrebbe chiuso li'. La permanenza e' continua su entrambi, quindi il
    rientro costa 5 s invece dei 3 s minimi e il registro lo dice."""
    esito = _stabilizza(10.0, [10.4, 20.0, 10.4, 10.4, 10.4, 10.4],
                        [1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    assert esito["warmup_campioni"] == 6
    assert esito["warmup_duration_s"] == pytest.approx(5.0)
    assert 20.0 in esito["warmup_valori_w"]


def test_warmup_lettura_assente_azzera_il_tratto_e_si_dichiara():
    """Una lettura di potenza assente non e' "il campione mancava, il tratto
    vale": il tratto si azzera e il conteggio delle letture mancanti resta
    nell'artefatto, perche' e' un segnale diagnostico su quel blocco."""
    esito = _stabilizza(10.0, [10.4, None, 10.4, 10.4, 10.4],
                        [1.0, 1.0, 1.0, 1.0, 1.0], sustain_s=2.0)
    assert esito["warmup_letture_mancanti"] == 1
    assert esito["warmup_duration_s"] == pytest.approx(4.0)
    assert None not in esito["warmup_valori_w"]
    assert len(esito["warmup_valori_w"]) == 4


def test_warmup_finestra_cpu_senza_campioni_non_diventa_uno_zero():
    """``total_cpu_samples`` torna la lista dei campioni della finestra: una
    lista vuota significa "nessun campione", non "macchina ferma allo 0 %".
    Mista per zero su una finestra vuota darebbe 0,0 % e chiuderebbe il tratto
    proprio quando il canale non ha risposto."""
    esito = _stabilizza(10.0, [10.4, 10.4, 10.4, 10.4],
                        [None, 1.0, 1.0, 1.0], sustain_s=2.0)
    assert esito["warmup_letture_mancanti"] == 1
    assert esito["warmup_duration_s"] == pytest.approx(3.0)
    assert 0.0 not in esito["warmup_valori_cpu_pct"]
    assert esito["warmup_valori_cpu_pct"] == [1.0, 1.0, 1.0]


@pytest.mark.parametrize("potenze,cpu_finestre", [
    ([10.5] * 5, [1.0] * 5),
    ([10.4] * 5, [2.0] * 5),
], ids=["potenza-al-bordo", "cpu-al-bordo"])
def test_warmup_disuguaglianza_stretta_su_ogni_segnale(potenze, cpu_finestre):
    """Il campione esattamente AL bordo della sua soglia NON soddisfa il
    criterio: la disuguaglianza e' stretta in ``cooldown_to_baseline`` (P1.5)
    e vale identica per entrambi i segnali qui, perche' "entro" e "a bordo"
    sono due criteri diversi e uno dei due deve essere scritto. Con soli
    valori a bordo la fase non chiude mai e il tetto ferma la campagna."""
    orologio = _Orologio(passo=1.0)
    with pytest.raises(SystemExit) as exc:
        _stabilizza(10.0, potenze, cpu_finestre, sustain_s=0.0, cap_s=3.0,
                    orologio=orologio)
    assert "tetto" in str(exc.value)


def test_warmup_tetto_ferma_la_campagna():
    """Al tetto senza rientro la campagna si ferma: il cooldown puo'
    tornare ``timed_out`` perche' il blocco e' gia' definito e il flag lo
    dichiara, ma qui il blocco successivo non e' ancora partito e
    immetterlo in transitorio rimetterebbe il residuo di carico dentro
    ``E_net`` — il difetto che questa fase esiste per togliere."""
    with pytest.raises(SystemExit) as exc:
        _stabilizza(10.0, [11.0] * 8, [5.0] * 8, sustain_s=5.0, cap_s=4.0)
    assert "tetto" in str(exc.value)
    assert "NON parte" in str(exc.value)


def test_warmup_tetto_registra_prima_di_arrestarsi():
    """L'arresto non avviene in silenzio sul registro. ``registra`` riceve il
    record terminale PRIMA del ``SystemExit``: una campagna fermata non scrive
    ``analysis.json``, e la durata di un warm-up fallito e' il dato che serve
    a capire perche' si e' fermata. Il record e' lo stesso che sarebbe
    scritto in chiusura, con ``warmup_completed`` a ``False``."""
    registri: list = []
    with pytest.raises(SystemExit):
        _stabilizza(10.0, [11.0] * 8, [5.0] * 8, sustain_s=5.0, cap_s=4.0,
                    registri=registri)
    assert len(registri) == 1
    record = registri[0]
    assert record["warmup_completed"] is False
    assert record["warmup_motivo"] == "tetto_raggiunto"
    assert record["warmup_duration_s"] == pytest.approx(4.0)
    assert record["warmup_campioni"] == 5


def test_warmup_si_compone_registra_il_record_di_chiusura():
    """Il registro non e' una cosa del solo percorso di arresto: la fase
    chiusa scrive lo stesso record che finisce nel ``runs`` di
    ``analysis.json``, perche' il JSONL e' la prova append-only della
    durata effettiva, non un derivato del report."""
    registri: list = []
    esito = _stabilizza(10.0, [10.4] * 4, [1.0] * 4, registri=registri)
    assert len(registri) == 1
    assert registri[0]["warmup_motivo"] == "criterio_soddisfatto"
    assert registri[0]["warmup_completed"] is True
    assert registri[0]["warmup_duration_s"] == esito["warmup_duration_s"]


def test_warmup_temperatura_letta_due_volte_e_registrata_con_la_fonte():
    """La temperatura si legge all'ingresso e all'uscita della fase, NON per
    campione: lo spawn del lettore costa 0,26-0,33 s (misurato 2026-11-09) e
    consuma CPU proprio mentre si osserva ``cpu_percent``. Le due letture con
    la loro fonte finiscono nel record, per servire da evidenza a una soglia
    termica di una campagna futura."""
    termiche: list = []
    esito = _stabilizza(10.0, [10.4] * 4, [1.0] * 4, termiche=termiche)
    assert len(termiche) == 2
    assert [r["fase"] for r in esito["warmup_temperatura"]] == ["ingresso",
                                                                "uscita"]
    assert [r["temperatura_c"] for r in esito["warmup_temperatura"]] == [27.85,
                                                                        27.85]
    assert all(r["fonte"] == "fake:MSAcpi_ThermalZoneTemperature"
               for r in esito["warmup_temperatura"])


def test_warmup_temperatura_assente_si_dichiara_e_non_decide():
    """Temperatura illeggibile: ``(None, motivo)`` registrato, nessun
    sostituto (non 0,0 C, non l'ultima lettura valida) e nessun effetto sul
    criterio, che chiude identico. E' la forma operativa di "se disponibile"
    senza fallback silenzioso, e la stessa forma in cui il canale termico
    risponde su questo host."""
    esito = _stabilizza(10.0, [10.4] * 4, [1.0] * 4,
                        temperatura=(None, "psutil: nessuna lettura valida; "
                                           "cim: FileNotFoundError"))
    assert esito["warmup_completed"] is True
    assert esito["warmup_duration_s"] == pytest.approx(3.0)
    assert [r["temperatura_c"] for r in esito["warmup_temperatura"]] == [None,
                                                                        None]
    assert "nessuna lettura valida" in esito["warmup_temperatura"][0]["fonte"]


def test_warmup_senza_baseline_di_carico_non_ha_criterio():
    """Il target e' la ``baseline_pre_w`` del blocco di carico: senza di
    quella non esiste ne' il criterio ne' un sostituto, e il tool si ferma
    invece di dormire un tempo a caso. Tre forme di assenza: None, zero e
    stringa vuota, e il nan."""
    for target in (None, 0.0, "", float("nan")):
        with pytest.raises(SystemExit) as exc:
            _stabilizza(target, [10.0], [1.0])
        assert "nessun target" in str(exc.value)


def test_warmup_default_pre_registrati_coerenti():
    """I default sono parametri di protocollo, e la loro coerenza e'
    aritmetica: la tolleranza deve essere piu' stretta della soglia di
    stabilita' di F.12 (1,0 W) o il warm-up accetterebbe un rientro che il
    gate scarterebbe; la soglia di cpu deve essere un numero positivo e il
    tetto deve superare la permanenza richiesta; il passo e' zero perche'
    l'osservazione della finestra E il passo."""
    assert 0.0 < rg.WARMUP_TOLERANCE_W < 1.0
    assert rg.WARMUP_CPU_MAX_PCT > 0.0
    assert rg.WARMUP_SUSTAIN_S > 0.0
    assert rg.WARMUP_CAP_S > rg.WARMUP_SUSTAIN_S + rg.WARMUP_STEP_S
    assert rg.WARMUP_WINDOW_S > 0.0
    assert rg.WARMUP_STEP_S == 0.0
    # la durata fissa non esiste piu' nel modulo: rimossa, non messa da parte
    assert not hasattr(rg, "WARMUP_DURATION_S")


# ---------------------------------------------------------------------------
# 6. provenienza delle due soglie: ricalcolate, non dichiarate a memoria
# ---------------------------------------------------------------------------
# Gli artefatti della SECONDA campagna, tracciati e non riscritti: la serie
# di potenza per blocco di controllo (campioni di contatore con
# ``cpu_percent``) e i riepiloghi di blocco con la ``baseline_pre_w``. Sono
# la stessa evidenza citata nel commento delle costanti
# (tools/run_gate_p44.py, blocco "Warm-up post-carico") e in ``checks["F"]``
# del piano, e qui si rileggono per ricalcolarle alla scala del criterio.
_ARTEFATTI_P44_20261108 = (Path(__file__).resolve().parents[2]
                           / "experiment_results" / "p44_gate_20261108")


def _finestre_del_criterio(entry: dict, target_pre_w: float,
                           window_s: float) -> list:
    """Riaggrega la serie di un blocco alla scala che il criterio osserva.

    La meccanica e' quella di ``_stabilizza_post_carico``, non una
    scorciatoia: finestre NON sovrapposte da ``window_s`` ancorate a
    ``t0_mono``, potenza = delta del contatore / delta di tempo fra il primo
    e l'ultimo campione dentro la finestra (media del contatore, non
    interpolazione fra finestre), ``cpu_percent`` = MEDIA dei campioni della
    finestra. Una finestra con un solo campione dentro non ha un delta del
    contatore al suo interno, quindi non e' osservabile dalla stessa
    meccanica (il criterio legge il contatore sulla finestra e non lo
    interpola oltre i bordi): viene esclusa, e il conteggio dei campioni di
    ciascuna finestra resta nel risultato.
    """
    t0 = float(entry["t0_mono"])
    campioni = sorted(entry["samples"], key=lambda s: float(s["t"]))
    if not campioni:
        return []
    n_finestre = int((float(campioni[-1]["t"]) - t0) // window_s) + 1
    finestre: list = []
    for i in range(n_finestre):
        inizio = t0 + i * window_s
        dentro = [s for s in campioni if inizio <= float(s["t"])
                  < inizio + window_s]
        if len(dentro) < 2:
            continue
        t_a, t_b = float(dentro[0]["t"]), float(dentro[-1]["t"])
        potenza = ((float(dentro[-1]["package_energy_j"])
                    - float(dentro[0]["package_energy_j"])) / (t_b - t_a))
        cpu = sum(float(s["cpu_percent"]) for s in dentro) / len(dentro)
        finestre.append({"n_campioni": len(dentro),
                         "potenza_w": round(potenza, 6),
                         "deviazione_w": abs(potenza - target_pre_w),
                         "cpu_medio_pct": cpu})
    return finestre


def _due_popolazioni():
    """Serie + baseline dei sei controlli, divisi fra il blocco in
    transitorio (ctrl-1, il primo della campagna) e i cinque stabilizzati."""
    serie = json.loads((_ARTEFATTI_P44_20261108
                        / "control_power_series.json").read_text(
                            encoding="utf-8"))
    blocchi = json.loads((_ARTEFATTI_P44_20261108
                          / "blocks_controllo.json").read_text(
                              encoding="utf-8"))
    pre = {b["block_id"]: float(b["baseline_pre_w"]) for b in blocchi}
    stabilizzati: list = []
    transitorio: list = []
    for entry in serie:
        finestra = _finestre_del_criterio(entry, pre[entry["block_id"]],
                                          rg.WARMUP_WINDOW_S)
        (transitorio if "__ctrl-1__" in entry["block_id"]
         else stabilizzati).extend(finestra)
    assert len(transitorio) == 2 and len(stabilizzati) >= 5
    return stabilizzati, transitorio


def test_provenienza_soglie_la_popolazione_stabilizzata_osserva_le_costanti():
    """Le due soglie non sono convenienze: ricalcolando le finestre del
    criterio sugli artefatti della seconda campagna, NESSUNA finestra dei
    cinque controlli stabilizzati scatta su NESSUNO dei due segnali. Se
    ricadi qui e una finestra scatta, la soglia e' stata scritta a memoria
    e il warm-up fermerebbe un blocco che il gate usera'."""
    stabilizzati, _transitorio = _due_popolazioni()
    dev_max = max(f["deviazione_w"] for f in stabilizzati)
    cpu_max = max(f["cpu_medio_pct"] for f in stabilizzati)
    assert dev_max == pytest.approx(0.3626, abs=5e-4)
    assert cpu_max == pytest.approx(1.000, abs=5e-4)
    assert dev_max < rg.WARMUP_TOLERANCE_W
    assert cpu_max < rg.WARMUP_CPU_MAX_PCT


def test_provenienza_soglie_il_transitorio_occupa_due_finestre_opposte():
    """Il re-lookup dei numeri citati nel commento delle costanti e in
    ``checks["F"]``: ctrl-1 da' 0,48 W con 4,1 % alla prima finestra e 0,80
    W con 1,8 % alla seconda. Ciascuna delle due finestre e' dentro la banda
    di un segnale e fuori da quella dell'altro, e le due soglie stanno
    strette fra le due popolazioni: questo e' il test che le soglie sono
    derivazione, non gusti."""
    _stabilizzati, transitorio = _due_popolazioni()
    dev = [f["deviazione_w"] for f in transitorio]
    cpu = [f["cpu_medio_pct"] for f in transitorio]
    assert dev[0] == pytest.approx(0.4802, abs=5e-4)
    assert cpu[0] == pytest.approx(4.100, abs=5e-4)
    assert dev[1] == pytest.approx(0.7951, abs=5e-4)
    assert cpu[1] == pytest.approx(1.800, abs=5e-4)
    # prima finestra: potenza DENTRO, cpu FUORI
    assert dev[0] < rg.WARMUP_TOLERANCE_W
    assert cpu[0] >= rg.WARMUP_CPU_MAX_PCT
    # seconda finestra: potenza FUORI, cpu DENTRO
    assert dev[1] >= rg.WARMUP_TOLERANCE_W
    assert cpu[1] < rg.WARMUP_CPU_MAX_PCT
    # ciascuna soglia e' stretta fra le due popolazioni
    assert rg.WARMUP_TOLERANCE_W < max(dev)
    assert rg.WARMUP_CPU_MAX_PCT < max(cpu)


def test_provenienza_permanenza_supera_il_tratto_continuo_del_transitorio():
    """``WARMUP_SUSTAIN_S`` e' la terza scelta ancorata agli stessi dati:
    nella sola potenza, la massima sequenza CONTINUA di campioni di
    contatore entro la tolleranza dentro il blocco in transitorio e' ~1,09 s
    (i due campioni centrali su quattro), e il blocco dura 2,94 s. Una
    permanenza di 10 s — circa tre finestre ``Tc`` e non piu' lasca della
    persistenza gia' pretesa dalla quiete P1.4 — non la attraversa. Se la
    permanenza scendesse sotto il tratto, il warm-up chiuderebbe in
    transitorio e il criterio multisegnale sarebbe decorativo."""
    serie = json.loads((_ARTEFATTI_P44_20261108
                        / "control_power_series.json").read_text(
                            encoding="utf-8"))
    blocchi = json.loads((_ARTEFATTI_P44_20261108
                          / "blocks_controllo.json").read_text(
                              encoding="utf-8"))
    entry = [e for e in serie if "__ctrl-1__" in e["block_id"]][0]
    target = {b["block_id"]: float(b["baseline_pre_w"]) for b in blocchi}[
        entry["block_id"]]
    campioni = sorted(entry["samples"], key=lambda s: float(s["t"]))
    deviazioni = []
    for a, b in zip(campioni, campioni[1:]):
        dt = float(b["t"]) - float(a["t"])
        potenza = (float(b["package_energy_j"])
                   - float(a["package_energy_j"])) / dt
        deviazioni.append((abs(potenza - target), dt))
    tratto = 0.0
    migliore = 0.0
    for deviazione, dt in deviazioni:
        if deviazione < rg.WARMUP_TOLERANCE_W:
            tratto += dt
            migliore = max(migliore, tratto)
        else:
            tratto = 0.0
    assert migliore == pytest.approx(1.09, abs=0.02)
    assert migliore < rg.WARMUP_SUSTAIN_S


# ---------------------------------------------------------------------------
# 7. criterio primario e uncertainty budget corretto (revisione 2026-11-09,
#    secondo giro): niente doppio conteggio, tipo A come s / sqrt(n),
#    componenti con tipo/inclusione/motivo, criterio dichiarato nel piano
# ---------------------------------------------------------------------------
def test_la_soglia_non_e_piu_budget_piu_k_u_c_doppio_conteggio():
    """La forma rimossa dava S = budget + 2 * u_c con u_c che sommava
    u_rumore e u_termico, cioe' i due termini di cui e' fatto il budget:
    u_c >= budget e S >= 3 * budget. Qui si dimostra l'aritmetica e che il
    tool NON la produce piu': con i numeri della seconda campagna (budget
    0,117995 W, bias 0,125171 W) la forma rimossa avrebbe dato S >= 0,353985
    W, cioe' un pass; la soglia del tool e' il budget, cioe' un fail."""
    import gate_uncertainty as gu
    budget = 0.117995
    half_range, half_drift = 0.1, math.sqrt(budget ** 2 - 0.1 ** 2)
    assert math.hypot(half_range, half_drift) == pytest.approx(budget)
    u_c_vecchio = gu.calcola_u_c(dispersione_baseline=half_range,
                                 margine_termico=half_drift)[0]
    assert u_c_vecchio == pytest.approx(budget)
    assert budget + 2.0 * u_c_vecchio >= 3.0 * budget - 1e-12
    assert budget + 2.0 * u_c_vecchio > 0.125171          # avrebbe fatto passare
    det = rg._calcola_budget_pre_esecuzione(
        "short", _corpo(PRE, POST))[1]
    inc = rg._incertezza_pre_esecuzione(det, 0.0156)
    assert inc["soglia_w"] == pytest.approx(det["budget_base_w"])
    assert inc["soglia_w"] < 3.0 * det["budget_base_w"]


def test_ogni_componente_dichiara_tipo_inclusione_e_motivo():
    """Per ogni componente, pre e post: valore, tipo A/B, inclusa True/False
    e un motivo non vuoto. Un'esclusione e' una decisione dichiarata, non
    un'assenza dal report."""
    import gate_uncertainty as gu
    det = rg._calcola_budget_pre_esecuzione(
        "short", _budget_per_u_c(dt_offset=0.02))[1]
    pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    post = rg._incertezza_con_au_controlli(pre, [
        {"usable": True, "e_net_j": 0.3, "dt_w_s": 3.0},
        {"usable": True, "e_net_j": 0.12, "dt_w_s": 3.0}])
    for gruppo in (pre, post):
        assert set(gruppo["componenti"]) >= {"u_rumore", "u_termico",
                                             "u_timer", "u_allineamento"}
        for nome, comp in gruppo["componenti"].items():
            assert gu.valida_componente(nome, comp) == [], nome
            assert comp["tipo"] in ("A", "B")
            assert isinstance(comp["inclusa"], bool)
            assert comp["motivo"].strip()
    incluse_pre = [n for n, c in pre["componenti"].items() if c["inclusa"]]
    incluse_post = [n for n, c in post["componenti"].items() if c["inclusa"]]
    assert incluse_pre == []
    assert incluse_post == ["u_A"]
    # le escluse restano nel report con il loro valore informativo
    assert pre["componenti"]["u_rumore"]["value"] is not None
    assert pre["componenti"]["u_allineamento"]["inclusa"] is False


def test_u_A_e_s_su_radice_di_n_e_decresce_con_n():
    """Con la stessa dispersione, 12 controlli danno u_A piu' piccola di 4:
    s / sqrt(n) decresce con n. La semi-ampiezza (max - min) / 2 non
    decresceva, e il range cresce con n: con 12 coppie il gate sarebbe
    stato piu' facile da passare che con 6."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _budget_per_u_c(dt_offset=0.02))[1]
    pre = rg._incertezza_pre_esecuzione(det, 0.0156)

    def ctrl(n):
        return [{"usable": True, "e_net_j": 0.3 if i % 2 == 0 else 0.0,
                 "dt_w_s": 3.0} for i in range(n)]

    u4 = rg._incertezza_con_au_controlli(pre, ctrl(4))["u_A"]
    u12 = rg._incertezza_con_au_controlli(pre, ctrl(12))["u_A"]
    # potenze 0,10 / 0,00 W alternate: media 0,05, scarti +-0,05
    assert u4 == pytest.approx(math.sqrt(4 * 0.05 ** 2 / 3) / math.sqrt(4))
    assert u12 == pytest.approx(
        math.sqrt(12 * 0.05 ** 2 / 11) / math.sqrt(12))
    assert u12 < u4


def test_piano_dichiara_il_criterio_primario_e_la_verifica_lo_confronta(
        monkeypatch, tmp_path):
    """Il criterio che decide e' scritto nel piano PRIMA dei dati (chiave e
    check H) e _verifica_piano si ferma se manca o diverge: scegliere dopo
    i dati fra due soglie sarebbe un grado di liberta' del ricercatore."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    _create_idle_characterization(tmp_path)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    path = rg.ARCHIVE_DIR / rg.PLAN_NAME
    piano = json.loads(path.read_text(encoding="utf-8"))
    assert piano["criterio_primario"] == rg.CRITERIO_PRIMARIO
    assert piano["criterio_storico_riportato"] == rg.CRITERIO_STORICO_F12
    assert "decide" in piano["checks"]["H"].lower()
    assert "Nessuna soglia del tipo budget + k * u_c" in piano["checks"]["H"]
    assert all(isinstance(t, str) for t in piano["checks"].values())
    piano["criterio_primario"] = "f12_mediana_budget_per_blocco_30s"
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    assert "criterio_primario" in str(exc.value)
    del piano["criterio_primario"]
    path.write_text(json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit) as exc2:
        rg._verifica_piano()
    assert "criterio_primario" in str(exc2.value)


def test_verdetto_primario_pass_fail_e_non_eseguibile():
    """Il criterio primario confronta |bias| con il budget a scala Tc e
    ripete il quorum di F.12. Non e' F.12: puo' dare pass dove F.12 storico
    da' fail (mismatch di scala), e il verdetto storico viaggia accanto."""
    base = {"status": "fail", "bias_w": 0.125171, "quorum": 8,
            "controls_usable_n": 12}
    pass_ = rg._verdetto_primario(base, budget_w=0.20)
    assert pass_["status"] == "pass"
    assert pass_["f12_status"] == "fail"           # lo storico non si tocca
    assert pass_["margine_w"] == pytest.approx(0.20 - 0.125171)
    fail = rg._verdetto_primario(base, budget_w=0.10)
    assert fail["status"] == "fail"
    assert fail["margine_w"] < 0.0
    bordo = rg._verdetto_primario({**base, "bias_w": 0.2}, budget_w=0.2)
    assert bordo["status"] == "pass"               # <= come F.12
    neg = rg._verdetto_primario({**base, "bias_w": -0.3}, budget_w=0.2)
    assert neg["status"] == "fail"                 # valore assoluto
    ne = rg._verdetto_primario(
        {"status": "not-executable", "bias_w": None, "quorum": 8,
         "controls_usable_n": 3}, budget_w=0.2)
    assert ne["status"] == "not-executable"
    assert ne["margine_w"] is None
    for v in (pass_, fail, ne):
        assert v["criterio"] == rg.CRITERIO_PRIMARIO
        assert v["criterio_storico_riportato"] == rg.CRITERIO_STORICO_F12


def test_accettazione_guardata_e_solo_riportata():
    """|bias| + U <= budget: grandezza riportata (JCGM 106:2012), None se
    bias o U non sono calcolabili. Non e' il criterio."""
    post = {"U_w": 0.05}
    ok = rg._accettazione_guardata(0.10, post, 0.20)
    assert ok["accettata"] is True
    assert ok["bias_piu_U_w"] == pytest.approx(0.15)
    no = rg._accettazione_guardata(0.18, post, 0.20)
    assert no["accettata"] is False
    assert no["bias_piu_U_w"] == pytest.approx(0.23)
    assert rg._accettazione_guardata(None, post, 0.2)["accettata"] is None
    assert rg._accettazione_guardata(0.1, {"U_w": None},
                                     0.2)["accettata"] is None
    assert "non decide" in ok["nota"]
