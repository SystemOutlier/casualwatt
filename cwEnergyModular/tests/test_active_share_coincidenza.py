# -*- coding: utf-8 -*-
"""``ollama_active_energy_j`` deve essere la quota dell'``active_energy_j`` DI RIGA.

Perche' esiste. L'attribuzione CPU e' definita come prodotto: la quota di tempo
busy (``cpu_time_share``) applicata all'energia attiva della riga. Nella
produzione il moltiplicatore veniva pero' preso da una variabile locale
(``active``) diversa da quella pubblicata (``res.active_energy_j``), e il ramo
TTFT ne era la prova: quando il ramo sovrascriveva il package con la somma
delle due sottofinestre ricalcolava ``active_raw`` e ``res.active_energy_j``,
ma non ``active``, e ``ollama_active_energy_j`` restava la quota di un numero
che nella riga non c'era piu'. Il punto C elimina la seconda fonte di verita';
il punto B elimina la causa che la rendeva osservabile, e per questo il caso 7
-- bordi e sub in disaccordo -- e' l'unico che mostra il difetto con un numero
diverso: rieseguito contro il ramo TTFT precedente fallisce, mentre sugli altri
percorsi le due variabili coincidevano e l'identita' reggeva gia'. Il file
fissa comunque l'identita' su TUTTI i percorsi, cosi' che la coincidenza non
dipenda piu' dal fatto che, oggi, le due variabili sono per fortuna lo stesso
numero.

Che cosa verifica -- per ogni percorso il test scrive a mano package, baseline
e active attesi, poi controlla l'identita' aritmetica sulla riga prodotta:
  1. bordi diretti (``direct-ioctl``) senza TTFT: quote e attribuzione sulla
     stessa energia attiva della riga;
  2. bordi diretti CON separazione TTFT: l'attribuzione non usa nessuna delle
     due sub-attive, usa ``active_energy_j`` di riga;
  3. percorso a buffer (bordi assenti) con e senza TTFT;
  4. fallback dichiarato sui campioni interpolati, con quota CPU letta dai
     campioni stessi (non dai bordi);
  5. sottofinestre escluse (scorporo del giudice): l'identita' regge sulla
     finestra ridotta;
  6. gate spenti: con ``active_valid`` False (energia attiva negativa) e con
     ``cpu_time_share_valid`` False (cpu-time Ollama non osservabile, quota
     azzerata perche' l'albero dei processi e' cambiato) il prodotto convenzionale
     e' 0.0, non la quota di un numero non valido;
  7. riproduzione del difetto: bordi 60 J e sub 50 + 30 = 80 J, il caso in cui
     il ramo TTFT pubblicava un ``active_energy_j`` diverso dalla variabile
     locale. Qui l'identita' E' violata sul codice precedente (10 J contro i
     20 J attesi da 40 J * 0,5) e regge su questo.

Che cosa NON verifica: il valore dello share (ha i suoi test in
``test_cpu_share_window.py`` e ``test_cpu_attribution.py``) ne' la correttezza
delle due quote TTFT (``test_ttft_split.py``). Qui si controlla soltanto che
l'attribuzione moltiplichi IL NUMERO DI RIGA e lo zero dove il gate dice di
mettere lo zero.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.energy_session import SystemSample  # noqa: E402
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

UTC0 = "2026-11-06T10:00:00.000+00:00"
TS_START = 400_000_000
TS_END = 440_000_000          # delta 40_000_000 * 100 ns = 4.0 s
T_START, T_END, T_TTFT = 1000.0, 1004.0, 1000.15

# Numeri scelti per stare dentro la capacita' anche su un host da 1 core:
# d_busy = 2,0 s su una finestra di 4,0 s vale share = 0,5 e non richiede
# nemmeno il check "d_busy <= core * durata".
D_OLLAMA_S = 1.0
D_BUSY_S = 2.0
P_IDLE_W = 10.0
PKG_START_J = 100.0
PKG_END_J = 160.0             # package di riga 60 J, baseline 40 J, active 20 J


class _Sessione:
    """Sessione finta: contatore esatto a richiesta e campioni opzionali."""

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = P_IDLE_W
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    calibrated_at = ""
    _gpu = SimpleNamespace(available=False, index=0, name="")
    source_notes: list = []

    def __init__(self, pkg_by_window=None, samples=None):
        self.pkg_by_window = pkg_by_window or {}
        self.samples = samples or []

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]

    def package_energy_exact_between(self, a, b, excl=None, exclude_windows=None):
        return self.pkg_by_window.get((round(float(a), 6), round(float(b), 6)))


def _edge(t_counter_mono, pkg_j, ts_100ns):
    return {
        "counter": {"pkg_j": pkg_j, "pkg_pwh": pkg_j * 1000.0,
                    "ts_100ns": ts_100ns, "pp1_j": None},
        "counter_error": "",
        "t_wall": t_counter_mono,
        "t_wall_utc": UTC0,
        "t_counter_mono": t_counter_mono,
        "t_cpu_mid": t_counter_mono,
        "edge_spread_s": 0.005,
        "tree": [],
        "worker": {},
        "busy": t_counter_mono * 2.0,
    }


def _campioni(pkg_j_list, busy_list, ollama_list):
    """Campioni nella finestra: package cumulato, busy e cpu-time Ollama."""
    out = []
    ts = [T_START, 1001.0, 1002.0, 1003.0, T_END]
    for i, t in enumerate(ts):
        out.append(SystemSample(
            t=t, wall=0.0, package_energy_j=pkg_j_list[i],
            cpu_busy_seconds=busy_list[i], cpu_percent=0.0,
            ollama_pids=(7,), ollama_io_bytes=0,
            ollama_cpu_seconds=ollama_list[i],
        ))
    return out


def _run(sess, *, e0=None, e1=None, t_ttft=None, direct=True, exclude=None):
    edge_ttft = None
    if t_ttft is not None:
        edge_ttft = dict(_edge(t_ttft, 0.0, 0))
        edge_ttft["t_ttft_mono"] = t_ttft
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(
        T_START, T_END,
        ollama_pids=[7],
        direct_cpu_delta=(D_OLLAMA_S if direct else None),
        direct_busy_delta=(D_BUSY_S if direct else None),
        baseline_pre_w=P_IDLE_W,
        edge_start=e0, edge_end=e1, edge_ttft=edge_ttft,
        exclude_windows=exclude,
    )


def _assert_identita(res, share_atteso=None):
    """L'attribuzione e' la quota dell'active DI RIGA, o 0.0 se un gate e' spento."""
    if res.cpu_time_share_valid and res.active_valid:
        assert res.ollama_active_energy_j == pytest.approx(
            round(res.active_energy_j * res.cpu_time_share, 6), abs=1e-9)
        if share_atteso is not None:
            assert res.cpu_time_share == pytest.approx(share_atteso)
    else:
        assert res.ollama_active_energy_j == 0.0


def _notes(res):
    return list(res.notes) if isinstance(res.notes, list) else [str(res.notes)]


# ----------------------------------------------------------------- 1) bordi
def test_bordi_senza_ttft_attribuzione_sull_active_di_riga():
    """Percorso primario ``direct-ioctl``: 20 J * 0,5 = 10 J.

    Verifica il caso di riferimento, quello dove la variabile locale e il
    valore pubblicato coincidono per costruzione: fissa il numero atteso perche'
    le varianti sotto, dove i due non coincidevano, siano confrontabili.
    """
    res = _run(_Sessione(), e0=_edge(T_START, PKG_START_J, TS_START),
               e1=_edge(T_END, PKG_END_J, TS_END))

    assert res.emi_edge_source == "direct-ioctl"
    assert res.package_energy_j == pytest.approx(60.0)
    assert res.baseline_energy_j == pytest.approx(40.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert res.active_valid is True
    assert res.cpu_time_share_valid is True
    _assert_identita(res, share_atteso=0.5)
    assert res.ollama_active_energy_j == pytest.approx(10.0)


# ----------------------------------------------------------------- 2) bordi + TTFT
def test_bordi_con_separazione_ttft_non_usa_le_sub():
    """Con la separazione TTFT l'attribuzione resta quella dell'active di riga.

    Verifica il percorso che il difetto colpiva: le due sub-attive (38,5 J e
    -18,5 J) sono colonne informative, non l'ingresso dell'attribuzione CPU,
    che moltiplica ``active_energy_j`` = 20 J. Se il prodotto usasse una delle
    due, o l'active calcolato prima della sovrascrittura del package, il numero
    sarebbe 19,25 J o -9,25 J invece di 10 J.
    """
    sess = _Sessione({
        (T_START, T_TTFT): 40.0,
        (T_TTFT, T_END): 20.0,
    })
    res = _run(sess, e0=_edge(T_START, PKG_START_J, TS_START),
               e1=_edge(T_END, PKG_END_J, TS_END), t_ttft=T_TTFT)

    assert res.ttft_available is True
    assert res.active_energy_ttft_j is not None
    assert res.active_energy_generation_j is not None
    assert res.active_energy_j == pytest.approx(20.0)
    _assert_identita(res, share_atteso=0.5)
    assert res.ollama_active_energy_j == pytest.approx(10.0)
    # nessuna delle due quote compare nell'attribuzione
    assert res.ollama_active_energy_j != pytest.approx(
        res.active_energy_ttft_j * res.cpu_time_share)


# ----------------------------------------------------------------- 3) buffer
def test_percorso_buffer_con_e_senza_ttft_stessa_identita():
    """Senza bordi di misura il prodotto usa comunque l'active pubblicato.

    Verifica che la coincidenza non dipenda dal percorso primario: qui
    ``e_package`` arriva da ``package_energy_exact_between`` sulla finestra
    intera (60 J) e la riga dichiara ``buffer-interp``; con e senza bordo TTFT
    l'attribuzione vale 10 J in entrambi i casi.
    """
    senza = _run(_Sessione({(T_START, T_END): 60.0}))
    con = _run(_Sessione({(T_START, T_END): 60.0,
                          (T_START, T_TTFT): 40.0,
                          (T_TTFT, T_END): 20.0}), t_ttft=T_TTFT)

    for res in (senza, con):
        assert res.emi_edge_source == "buffer-interp"
        assert res.active_energy_j == pytest.approx(20.0)
        _assert_identita(res, share_atteso=0.5)
    assert senza.ollama_active_energy_j == pytest.approx(10.0)
    assert con.ollama_active_energy_j == pytest.approx(10.0)
    assert con.ttft_available is True


# ----------------------------------------------------------------- 4) campioni
def test_fallback_campioni_quota_da_campioni_identita_tenuta():
    """Fallback dichiarato sui campioni: share dai campioni, prodotto dall'active.

    Verifica il percorso senza letture dirette agli estremi: il package viene
    dalla somma dei delta fra campioni (100 -> 108 -> 122 -> 140 -> 160 = 60 J),
    lo share dal rapporto fra i cpu-time dei campioni (1,0 s / 2,0 s = 0,5), e
    ``cpu_share_source`` vale ``samples-fallback``. L'identita' e' la stessa:
    20 J * 0,5 = 10 J.
    """
    sess = _Sessione(
        {},  # nessuna lettura esatta: la produzione degrada ai campioni
        samples=_campioni([100.0, 108.0, 122.0, 140.0, 160.0],
                          [500.0, 500.4, 500.9, 501.4, 502.0],
                          [10.0, 10.2, 10.5, 10.8, 11.0]),
    )
    res = _run(sess, direct=False)

    assert res.package_window_source == "samples-fallback"
    assert res.package_energy_j == pytest.approx(60.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert res.cpu_share_source == "samples-fallback"
    assert res.cpu_time_share_valid is True
    _assert_identita(res, share_atteso=0.5)
    assert res.ollama_active_energy_j == pytest.approx(10.0)


# ----------------------------------------------------------------- 5) escluse
def test_sottofinestre_escluse_identita_sulla_finestra_ridotta():
    """Con lo scorporo del giudice l'attribuzione segue l'active, non il package.

    Verifica che una sottofinestra esclusa non introduca una terza base di
    calcolo: la finestra energetica e' ridotta, la baseline pure, e il prodotto
    usa il numero ridotto pubblicato nella riga. Qui package 60 J, baseline
    35 J (finestra di 3,5 s), active 25 J, share 0,5: 12,5 J.
    """
    sess = _Sessione({(T_START, T_END): 60.0})
    res = _run(sess, exclude=[(1001.0, 1001.5)])

    assert res.dt_W_s == pytest.approx(3.5)
    assert res.baseline_energy_j == pytest.approx(35.0)
    assert res.active_energy_j == pytest.approx(25.0)
    _assert_identita(res, share_atteso=0.5)
    assert res.ollama_active_energy_j == pytest.approx(12.5)


# ----------------------------------------------------------------- 6) gate spenti
def test_active_negativo_attribuzione_zero_anche_con_share_valido():
    """``active_valid`` False azzera il prodotto: nessuna quota di un non-numero.

    Verifica il gate sul lato energia: 20 J di package con 40 J di baseline
    danno active -20 J, firmato in riga ma inutilizzabile per l'attribuzione;
    ``cpu_time_share_valid`` resta True perche' e' un'altra condizione, e il
    prodotto e' 0.0.
    """
    res = _run(_Sessione(), e0=_edge(T_START, PKG_START_J, TS_START),
               e1=_edge(T_END, 120.0, TS_END))

    assert res.package_energy_j == pytest.approx(20.0)
    assert res.active_energy_j == pytest.approx(-20.0)
    assert res.active_valid is False
    assert res.cpu_time_share_valid is True
    assert res.ollama_active_energy_j == 0.0


def test_share_non_valido_attribuzione_zero_anche_con_active_valido():
    """``cpu_time_share_valid`` False azzera il prodotto: la quota non si inventa.

    Verifica il gate sul lato CPU: senza letture dirette e senza campioni il
    cpu-time di Ollama non e' osservabile, lo share vale 0.0 con la ragione
    dichiarata, e l'attribuzione e' 0.0 anche se l'energia attiva e' valida.
    """
    res = _run(_Sessione({(T_START, T_END): 60.0}), direct=False)

    assert res.active_energy_j == pytest.approx(20.0)
    assert res.active_valid is True
    assert res.cpu_time_share_valid is False
    assert res.ollama_active_energy_j == 0.0


def test_albero_processi_cambiato_attribuzione_zero():
    """``engine_tree_changed`` True: quota azzerata per D1, identita' non applicata.

    Verifica il terzo gate: la riga conserva gli ingressi grezzi e spende la
    quota; l'identita' deve reggere anche qui (0.0 con il gate spento), perche'
    un prodotto calcolato su un albero mutato alimenterebbe il confronto di
    concordanza P6.6 con una stima non integra.
    """
    sess = _Sessione()
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    res = prof.profile_window(
        T_START, T_END,
        ollama_pids=[7], direct_cpu_delta=D_OLLAMA_S,
        direct_busy_delta=D_BUSY_S, baseline_pre_w=P_IDLE_W,
        edge_start=_edge(T_START, PKG_START_J, TS_START),
        edge_end=_edge(T_END, PKG_END_J, TS_END),
        engine_tree_changed=True,
    )

    assert res.cpu_time_share_valid is False
    assert res.cpu_time_share == 0.0
    assert res.ollama_active_energy_j == 0.0
    _assert_identita(res)


# ------------------------------------------------ 9) riproduzione del difetto
def test_deriva_fra_bordi_e_sub_l_attribuzione_segue_l_active_pubblicato():
    """Bordi 60 J e sub 50 + 30 = 80 J: l'attribuzione segue il numero DI RIGA.

    Verifica il difetto di cui questo file esiste, non solo l'invarianza. Con
    il package di riga (60 J) diverso dalla somma delle due sub (80 J), il ramo
    TTFT precedente sovrascriveva ``package_energy_j`` e ``active_energy_j`` con
    80 e 40 J, ma non la variabile locale ``active``, che restava 20 J:
    l'attribuzione usciva ``round(20 * 0,5) = 10 J``, mentre la riga dichiarava
    un'energia attiva di 40 J. L'identita' dell'attribuzione era rotta con i due
    numeri pubblicati entrambi in CSV, e ``active_valid``/``cpu_time_share_valid``
    erano veri entrambi, quindi nessun gate la segnalava. Misurato: rieseguito
    contro l'albero con il ramo TTFT precedente, questo test fallisce con
    ``10.0 != 20.0``. Dopo B la riga non viene piu' sovrascritta (package 60,
    active 20) e dopo C la seconda fonte di verita' non esiste piu': 10 J e'
    davvero meta' di 20 J.
    """
    sess = _Sessione({
        (T_START, T_TTFT): 50.0,
        (T_TTFT, T_END): 30.0,
    })
    res = _run(sess, e0=_edge(T_START, PKG_START_J, TS_START),
               e1=_edge(T_END, PKG_END_J, TS_END), t_ttft=T_TTFT)

    # La riga resta il delta dei bordi: 60 J, non la somma delle sub.
    assert res.emi_edge_source == "direct-ioctl"
    assert res.package_energy_j == pytest.approx(60.0)
    assert res.package_energy_raw_j == pytest.approx(60.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert res.active_valid is True
    assert res.cpu_time_share_valid is True
    # La deriva e' dichiarata, non usata per correggere il valore.
    assert any("deriva fra il delta dei bordi" in n for n in _notes(res))
    # Le due quote ripartiscono 60 J con s = 50/80 = 0,625.
    assert res.package_energy_ttft_j == pytest.approx(37.5)
    assert res.package_energy_generation_j == pytest.approx(22.5)
    # E l'attribuzione e' la quota dell'active pubblicato: 20 * 0,5 = 10.
    _assert_identita(res, share_atteso=0.5)
    assert res.ollama_active_energy_j == pytest.approx(10.0)
    # Il numero che il ramo precedente pubblicava (40 J * 0,5) non compare.
    assert res.ollama_active_energy_j != pytest.approx(20.0)
