# -*- coding: utf-8 -*-
"""
tests/test_ttft_split.py — I rami TTFT/generazione devono stare in piedi da soli.

Perche' esiste. v4-TTFT e' il nome con cui questo repo nomina la separazione
TTFT/generazione: un requisito di implementazione della v4, non una clausola del
protocollo, dove il numero P6.4 e' occupato dalla simulazione Monte Carlo. Il
ramo spezza la finestra [t_start, t_end] in due sottofinestre
quando il runner ha registrato il bordo del primo token. Le tre grandezze della
riga -- ``package_energy_j``, ``baseline_energy_j``, ``active_energy_j`` -- e
i loro ``*_raw_j`` firmati devono restare legati da un'identita' anche quando
il ramo a due parti gira. Due difetti si sono stratificati qui. Il primo,
chiuso il 05-11: la riga pubblicava la somma firmata delle due sub mentre
``active_energy_j`` veniva sottratto dall'``e_package`` pre-TTFT, e le due
sub-baseline sommate non coincidevano con la baseline di riga quando
``dt_W_s`` (tempo dei timestamp del contatore) differiva da ``t_end - t_start``
(tempo monotono Python). Il secondo, chiuso dalla revisione statica del 06-11
(punto B): la somma delle due sub *sostituiva* comunque il ``package_energy_j``
di riga, che pero' continuava a dichiararsi ``emi_edge_source =
"direct-ioctl"`` e una attribuzione CPU che dice "differenza del contatore fra
i due bordi" -- un numero che non veniva piu' da li', e la derivazione era
nascosta sotto la soglia di 1e-3 J. Ora le sub *ripartiscono* il valore del
percorso primario e non lo rimpiazzano mai: ``package_energy_ttft_j =
e_package * e_ttft / (e_ttft + e_gen)`` e il secondo termine e' il complemento,
perche' la somma delle due quote sia il valore di riga per costruzione.

Che cosa verifica -- ciascuna regola e' indipendente dai valori prodotti dal
codice sotto test: la sessione finta serve un numero che il test stesso ha
scelto, e il test scrive l'atteso a mano.
  1. sub positive: le due quote ripartiscono il valore di riga (``package_ttft
     + package_generation == package_energy_j``), ``active = package -
     baseline``, somma delle due sub-active = active di riga, somma delle due
     sub-baseline = baseline di riga;
  2. sub con una delle due negativa (reset fra i campioni): la separazione NON
     e' calcolabile, i sei campi sub restano ``None`` con una nota che riporta
     i valori grezzi, e la riga e' intatta (package e active firmati del
     percorso primario, ``active_valid`` False, nessun ``max``);
  3. entrambe le sub negative (finestra interamente incoerente): idem -- nessuna
     compensazione silenziosa e nessun campo sub inventato;
  4. sub a somma zero: la ripartizione non e' definita (denominatore zero), i
     campi sub sono ``None``; package = 0, active = -baseline, gate spento;
  5. ``dt_W_s`` (contatore) != ``t_end - t_start`` (monotono): la baseline
     di riga e' ``P_idle * dt_W_s``, le sub sono la FRAZIONE monotona di
     quella, e la loro somma e' esattamente il valore di riga;
  6. ``package_energy_exact_between`` ritorna ``None`` su una sub: la
     separazione non e' calcolabile, ``package_energy_j`` resta quello del
     bordo pre-TTFT, ``ttft_available`` True con i campi sub ``None``;
  7. bordo TTFT fuori finestra (``t_ttft <= t_start`` o ``>= t_end``):
     la riga non calcola la separazione, nota dichiarata;
  8. deriva oltre 1e-3 J fra il delta dei bordi e la somma grezza delle sub:
     la nota di deriva c'e', ma il valore pubblicato RESTA il delta dei bordi:
     dopo il punto B la deriva e' un'informazione, non una sostituzione;
  8b. senza bordi di misura (percorso a buffer) il comportamento osservabile
     non cambia: il valore di riga e' la lettura esatta della finestra e le due
     quote ne ripartiscono la stessa somma;
  9. nessuna delle altre componenti energetiche (``cpu_time_share``,
     ``ollama_active_energy_j``, ``idle_power_w``) cambia tra i rami con e
     senza TTFT: lo scorporo non tocca l'attribuzione;
  10. la nota pubblicata in ``notes`` nomina la ripartizione come STIMA con il
      suo rapporto, e nega che le due fasi siano misurate: il token che
      l'analista legge nel CSV deve dire la natura del numero, non solo il
      meccanismo.

Che cosa NON verifica: la validita' fisica del reset fra i campioni (ha i
suoi test in ``test_cpu_attribution.py``), ne' la precisione di
``t_first_token`` nel runner reale (ha i suoi test in
``test_shared_components_v4.py::test_infer_v4_stream_registra_ttft``).
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0
UTC0 = "2026-11-05T10:00:00.000+00:00"
# 4 s nella base del contatore = 400_000_000 unita' da 100 ns
TS_START = 400_000_000
TS_END = 440_000_000      # delta = 40_000_000 -> dt_W_s = 4.0 s


class _Sessione:
    """Sessione finta che serve i numeri scelti dal test.

    ``pkg_by_window`` mappa ``(a, b)`` -> ``float | None``. Se la coppia
    non e' registrata, ``package_energy_exact_between`` ritorna ``None``:
    e' il modo per testare la sub non calcolabile.
    """

    source_method = "emi-counter"
    interval_s = 0.5
    idle_power_w = 10.0
    idle_provenance = "calibrated"
    idle_gpu_power_w = None
    calibrated_at = ""
    _gpu = SimpleNamespace(available=False, index=0, name="")
    source_notes: list = []

    def __init__(self, pkg_by_window):
        self.pkg_by_window = pkg_by_window
        self.samples = []

    def samples_between(self, a, b):
        return []

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


def _profile(sess, e0, e1, t_ttft_mono=None):
    edge_ttft = None
    if t_ttft_mono is not None:
        edge_ttft = dict(_edge(t_ttft_mono, 0.0, 0))
        edge_ttft["t_ttft_mono"] = float(t_ttft_mono)
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    return prof.profile_window(
        e0["t_counter_mono"], e1["t_counter_mono"],
        ollama_pids=[7], direct_cpu_delta=6.0, direct_busy_delta=8.0,
        baseline_pre_w=sess.idle_power_w,
        edge_start=e0, edge_end=e1, edge_ttft=edge_ttft,
    )


def _notes(res):
    return list(res.notes) if isinstance(res.notes, list) else [str(res.notes)]


# --------------------------------------------------------------------------
# 1) sub positive: identita' fra riga e parti
# --------------------------------------------------------------------------
def test_sub_positive_identita_fra_riga_e_parti():
    """Con due sub positive la riga e le parti rispettano le tre identita'.

    Verifica ``package_ttft + package_generation = package_di_riga``,
    ``baseline_ttft + baseline_gen = baseline_di_riga`` e
    ``active_ttft + active_gen = active_di_riga`` con valori scritti a mano
    dal test, non riletti dal codice sotto prova. Qui il package di riga (60 J
    dai bordi) coincide con la somma grezza delle sub (40 + 20), quindi la
    ripartizione restituisce esattamente le due sottofinestre lette: e' il caso
    in cui il valore di riga e la somma delle parti NON permettono di
    distinguere le due regole, e per questo serve il test sulla deriva.
    """
    # Finestra: ts 400M -> 440M 100ns = 4.0 s (dt_W_s) e
    # t_counter_mono 1000 -> 1004 = 4.0 s (base coincidente qui).
    # package di riga = 60 J (delta dei bordi), sub = 40 + 20,
    # baseline = 10 W * 4 s = 40 J, active di riga = 60 - 40 = 20 J.
    # s = 40/60 => package_ttft = 60 * 2/3 = 40 J, package_gen = 20 J.
    # frac_ttft = 0.15/4 = 0.0375 => baseline_ttft = 40 * 0.0375 = 1.5 J
    # baseline_gen = 40 - 1.5 = 38.5 J
    # active_ttft = 40 - 1.5 = 38.5 J
    # active_gen = 20 - 38.5 = -18.5 J   (complemento, non seconda sottrazione)
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.package_energy_j == pytest.approx(60.0)
    assert res.package_energy_raw_j == pytest.approx(60.0)
    assert res.package_energy_ttft_j == pytest.approx(40.0)
    assert res.package_energy_generation_j == pytest.approx(20.0)
    assert (res.package_energy_ttft_j + res.package_energy_generation_j
            == pytest.approx(res.package_energy_j))

    assert res.baseline_energy_j == pytest.approx(40.0)
    assert res.baseline_energy_ttft_j == pytest.approx(1.5)
    assert res.baseline_energy_generation_j == pytest.approx(38.5)
    assert (res.baseline_energy_ttft_j + res.baseline_energy_generation_j
            == pytest.approx(res.baseline_energy_j))

    assert res.active_energy_j == pytest.approx(20.0)
    assert res.active_energy_raw_j == pytest.approx(20.0)
    assert res.active_energy_ttft_j == pytest.approx(38.5)
    assert res.active_energy_generation_j == pytest.approx(-18.5)
    assert (res.active_energy_ttft_j + res.active_energy_generation_j
            == pytest.approx(res.active_energy_j))

    assert res.ttft_available is True
    assert res.ttft_s == pytest.approx(0.15)
    assert res.active_valid is True
    # Il package di bordo e la somma sub coincidono (60 == 60) => nessuna
    # nota di deriva.
    assert not any("deriva fra il delta dei bordi" in n for n in _notes(res))


# --------------------------------------------------------------------------
# 2) una sub negativa: separazione non calcolabile, riga intatta
# --------------------------------------------------------------------------
def test_una_sub_negativa_separazione_assente_e_riga_intatta():
    """Una sub negativa non produce quote: la riga resta quella del bordo.

    Verifica due cose insieme. La prima e' il segno: un reset fra i campioni
    della sub di generazione (``e_gen = -3 J``) resta firmato in
    ``package_energy_raw_j`` e in ``active_energy_raw_j``, ``active_valid`` si
    spegne e la nota ``E_attiva grezza < 0`` arriva nella riga. La seconda e'
    la separazione: con una sub negativa il rapporto di ripartizione non ha
    significato fisico (una fase che ha "restituito" energia), quindi i sei
    campi ``*_ttft_*``/``*_generation_*`` restano ``None`` e la nota riporta i
    valori grezzi invece di clamparli o di sommarli al valore di riga.
    """
    # Bordo: delta = 2 J (pkg_j 100 -> 102). Sub: 5 + (-3) = 2.
    # baseline di riga: 10 W * 4 s = 40 J.
    # active = 2 - 40 = -38 J (firmato, non clampato).
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 102.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 5.0,
        (1000.15, 1004.0): -3.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.package_energy_j == pytest.approx(2.0)
    assert res.package_energy_raw_j == pytest.approx(2.0)
    assert res.active_energy_j == pytest.approx(-38.0)
    assert res.active_energy_raw_j == pytest.approx(-38.0)
    assert res.active_valid is False
    assert any("E_attiva grezza" in n for n in _notes(res))

    assert res.ttft_available is True
    assert res.ttft_s == pytest.approx(0.15)
    assert res.package_energy_ttft_j is None
    assert res.package_energy_generation_j is None
    assert res.baseline_energy_ttft_j is None
    assert res.baseline_energy_generation_j is None
    assert res.active_energy_ttft_j is None
    assert res.active_energy_generation_j is None
    notes = _notes(res)
    assert any("separazione non calcolabile" in n for n in notes)
    # la nota riporta i valori grezzi: senza di quelli il "perche'" sarebbe
    # invisibile e la riga sembrerebbe un bug del calcolatore
    assert any("e_gen=-3.000000" in n for n in notes)


# --------------------------------------------------------------------------
# 3) entrambe le sub negative: riga firmata, gate spento, nessuna quota
# --------------------------------------------------------------------------
def test_entrambe_sub_negative_gate_spento_e_nessuna_quota():
    """Entrambe le sub negative: la finestra intera resta firmata e invalida.

    Verifica che la finestra uscita dal reset dei bordi (``pkg_j`` 100 -> 90,
    delta ``-10`` J) non venga riparata dalla separazione: il package di riga
    resta ``-10`` J, l'active ``-10 - 40 = -50`` J, ``active_valid`` e' False,
    e nessuna delle due sub negative -- che singolarmente la produzione somma
    in ``e_ttft=-4``, ``e_gen=-6`` -- finisce nei campi sub. Un rapporto fra
    due numeri negativi sarebbe positivo e plausibile: e' esattamente il modo
    in cui un'incoerenza diventerebbe un numero credibile.
    """
    # Bordo: pkg_j 100 -> 90 (delta = -10), che la produzione marcera'
    # counter-invalid. Sub lette: -4 e -6, nessuna ripartizione.
    # baseline = 40 J; active_raw = -10 - 40 = -50 J (fermo).
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 90.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): -4.0,
        (1000.15, 1004.0): -6.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.package_energy_j == pytest.approx(-10.0)
    assert res.package_energy_raw_j == pytest.approx(-10.0)
    assert res.active_energy_j == pytest.approx(-50.0)
    assert res.active_energy_raw_j == pytest.approx(-50.0)
    assert res.active_valid is False
    assert res.package_energy_ttft_j is None
    assert res.package_energy_generation_j is None
    assert res.active_energy_ttft_j is None
    assert res.active_energy_generation_j is None


# --------------------------------------------------------------------------
# 4) sub a somma zero: package 0, active = -baseline, gate spento
# --------------------------------------------------------------------------
def test_somma_sub_a_zero_active_uguale_a_meno_baseline():
    """Sub con somma 0 J: package 0, active = -baseline, nessuna quota.

    Verifica che una finestra il cui package netto e' zero non venga
    mascherata in nessun modo: la riga esce con ``package_energy_j = 0``,
    ``active_energy_j = -baseline``, gate spento, e senza la nota di deriva
    perche' ``abs(0 - 0)`` sta sotto la soglia ``1e-3`` J. La ripartizione
    qui ha il denominatore zero oltre che una sub negativa: nessuna delle due
    quote si calcola, e il fatto che il package di riga valga 0 non autorizza
    una separazione a 0/0.
    """
    # Bordo: pkg_j 100 -> 100 (delta 0). Sub: 3 + (-3) = 0.
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 100.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 3.0,
        (1000.15, 1004.0): -3.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)
    assert res.package_energy_j == pytest.approx(0.0)
    assert res.active_energy_j == pytest.approx(-40.0)
    assert res.active_valid is False
    assert res.package_energy_ttft_j is None
    assert res.package_energy_generation_j is None
    assert res.active_energy_ttft_j is None
    assert res.active_energy_generation_j is None
    # somma sub = package di bordo (0 = 0) => nessuna nota di deriva
    assert not any("deriva fra il delta dei bordi" in n for n in _notes(res))


# --------------------------------------------------------------------------
# 5) dt_W_s != t_end - t_start: sub-baseline-somma = baseline di riga
# --------------------------------------------------------------------------
def test_dt_W_diversa_da_monotono_sub_baseline_sommano_a_riga():
    """``dt_W_s`` (contatore) != ``t_end - t_start`` (monotono): le sub-baseline sommano alla riga.

    Verifica la proprieta' persa dal ramo precedente: la baseline di riga
    e' ``P_idle * dt_W_s`` (4 s), mentre la finestra monotona e' 1 s. Le due
    sub-baseline sono la FRAZIONE monotona di quella baseline (6 J + 34 J),
    non due prodotti ``P_idle * dt_ttft`` e ``P_idle * dt_gen`` che, sulla
    base vecchia, davano 10 J invece di 40 J.
    """
    # ts del contatore: 400M -> 440M = 4.0 s (dt_W_s)
    # t_counter_mono: 1000.0 -> 1001.0 = 1.0 s (finestra Python)
    # => le due basi differiscono per un fattore 4.
    # baseline di riga = 10 * 4 = 40 J (dai timestamp del contatore).
    # frac_ttft sul monotono = (1000.15 - 1000) / (1001 - 1000) = 0.15
    # baseline_ttft = 40 * 0.15 = 6 J; baseline_gen = 40 - 6 = 34 J
    # somma = 40, esattamente baseline di riga. Il ramo vecchio moltiplicava
    # P_idle * dt_ttft (= 1.5 J) e P_idle * dt_gen (= 8.5 J) e sommando
    # otteneva 10 J, non 40 J: identificazione rotta.
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1001.0, 160.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1001.0): 20.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.dt_W_s == pytest.approx(4.0)
    assert res.baseline_energy_j == pytest.approx(40.0)
    assert res.baseline_energy_ttft_j == pytest.approx(6.0)
    assert res.baseline_energy_generation_j == pytest.approx(34.0)
    assert (res.baseline_energy_ttft_j + res.baseline_energy_generation_j
            == pytest.approx(res.baseline_energy_j))
    # Active di riga: package (60) - baseline (40) = 20
    assert res.active_energy_j == pytest.approx(20.0)


# --------------------------------------------------------------------------
# 6) e_ttft=None: nessuna separazione, package di bordo resta
# --------------------------------------------------------------------------
def test_contatore_assente_su_una_sub_separazione_non_calcolabile():
    """Una sub non leggibile: i sei campi TTFT restano ``None``, package di bordo non viene toccato.

    Verifica che ``package_energy_exact_between`` che ritorna ``None`` su
    ``[t_start, t_ttft]`` non venga mai sostituito con uno zero o con l'altra
    sub: ``ttft_available=True`` resta perche' il bordo esiste, ma
    ``package_energy_j`` conserva il delta dei due bordi pre-TTFT e la nota
    dichiara la ragione.
    """
    # (1000.0, 1000.15) non registrato => e_ttft=None.
    # package di bordo resta 60 J (dal direct-ioctl dei due pkg_j).
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    sess = _Sessione({(1000.15, 1004.0): 20.0})
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.package_energy_j == pytest.approx(60.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert res.ttft_available is True
    assert res.ttft_s == pytest.approx(0.15)
    assert res.package_energy_ttft_j is None
    assert res.package_energy_generation_j is None
    assert res.baseline_energy_ttft_j is None
    assert res.baseline_energy_generation_j is None
    assert res.active_energy_ttft_j is None
    assert res.active_energy_generation_j is None
    assert any("contatore non disponibile su" in n for n in _notes(res))


# --------------------------------------------------------------------------
# 7) t_ttft fuori finestra: nessuna separazione, nota dichiarata
# --------------------------------------------------------------------------
def test_bordo_ttft_fuori_della_finestra_notifica_e_non_calcola():
    """``t_ttft > t_end``: nessuna separazione, package e active restano quelli di riga.

    Verifica la guardia ``t_start < t_ttft < t_end`` sul lato destro della
    finestra: il runner potrebbe registrare il bordo del primo token piu'
    tardi della IOCTL finale, e la riga non inventa una sub che la finestra
    fisica non contiene.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    # t_ttft = 1004.5 > t_end: la condizione t_start < t_ttft < t_end e' falsa
    sess = _Sessione({})
    res = _profile(sess, e0, e1, t_ttft_mono=1004.5)
    assert res.package_energy_ttft_j is None
    assert res.package_energy_generation_j is None
    assert res.active_energy_ttft_j is None
    assert res.active_energy_generation_j is None
    assert res.package_energy_j == pytest.approx(60.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert any("bordo TTFT fuori della finestra" in n for n in _notes(res))


def test_bordo_ttft_uguale_a_start_non_calcola():
    """``t_ttft == t_start``: la disuguaglianza e' stretta e la separazione non parte.

    Verifica il bordo sinistro della guardia. Un ``t_ttft`` che coincide con
    ``t_start`` darebbe una prima sub di durata zero: ``P_idle * 0`` e un
    package su ``[t_start, t_start]``. La produzione non calcola nulla, e il
    test lo verifica senza leggere i valori che il codice produce.
    """
    # La disuguaglianza e' stretta: t_ttft == t_start NON calcola.
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    sess = _Sessione({})
    res = _profile(sess, e0, e1, t_ttft_mono=1000.0)
    assert res.package_energy_ttft_j is None
    assert any("bordo TTFT fuori della finestra" in n for n in _notes(res))


# --------------------------------------------------------------------------
# 8) deriva oltre 1e-3 J: nota, e il valore di riga RESTA il delta dei bordi
# --------------------------------------------------------------------------
def test_deriva_sopra_soglia_notificata():
    """Somma sub != delta di bordo oltre ``1e-3`` J: nota, nessuna sostituzione.

    Verifica la regola del punto B: le due sottofinestre sono lette sullo
    stesso contatore del bordo, quindi quando la loro somma grezza differisce
    dal delta dei due bordi la differenza e' una deriva da *dichiarare*, non un
    numero da adottare. La riga continua a pubblicare il delta dei bordi (58 J)
    e le due quote sono la ripartizione di QUELLO con il rapporto delle sub:
    ``package_ttft = 58 * 40/60``. La somma delle parti vale 58, non 60: e'
    l'identita' che tiene, perche' e' quella che un lettore della riga usa.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 158.0, TS_END)     # delta di bordo = 58 J
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,          # somma sub = 60 J, deriva 2 J
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    # Il valore di riga non e' la somma delle sub (60): e' il delta dei bordi.
    assert res.package_energy_j == pytest.approx(58.0)
    assert res.package_energy_raw_j == pytest.approx(58.0)
    assert res.active_energy_j == pytest.approx(18.0)

    # Le quote ripartiscono 58 con il rapporto 40:20 letto sulle sub.
    assert res.package_energy_ttft_j == pytest.approx(58.0 * 40.0 / 60.0, abs=1e-6)
    assert res.package_energy_generation_j == pytest.approx(
        58.0 - 58.0 * 40.0 / 60.0, abs=1e-6)
    assert (res.package_energy_ttft_j + res.package_energy_generation_j
            == pytest.approx(res.package_energy_j))
    assert (res.active_energy_ttft_j + res.active_energy_generation_j
            == pytest.approx(res.active_energy_j))

    notes = _notes(res)
    assert any("deriva fra il delta dei bordi" in n for n in notes)


def test_bordi_e_attribuzione_non_cambiano_con_la_separazione():
    """Con i bordi di misura la separazione non riscrive l'unita' di conto.

    Verifica che ``emi_edge_source``, ``package_window_source``,
    ``cpu_attribution_method`` e i grezzi ``raw_start``/``raw_end`` restino
    quelli del percorso direct-ioctl anche quando la riga porta le sei colonne
    TTFT. Era proprio questo il difetto del punto B: il numero cambiava
    provenienza (dal buffer a 0,05 s) mentre la riga continuava a dichiarare
    "differenza del contatore fra i due bordi", e un lettore del CSV avrebbe
    attribuito alla IOCTL un valore che la IOCTL non aveva prodotto.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 158.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    assert res.emi_edge_source == "direct-ioctl"
    assert res.package_window_source == "exact-counter"
    assert "difference of the counter at the two measurement edges" in \
        res.cpu_attribution_method
    assert res.raw_start == pytest.approx(100_000.0)
    assert res.raw_end == pytest.approx(158_000.0)
    assert res.package_energy_j == pytest.approx(58.0)


def test_deriva_sotto_soglia_non_notificata():
    """Deriva di 0.5 mJ (sotto 1e-3 J) non produce nessuna nota.

    Verifica che la soglia esca davvero: sotto di essa la riga non allarma per
    arrotondamenti di virgola mobile fra due letture dello stesso contatore.
    Il valore pubblicato, sopra come sotto la soglia, e' il delta dei bordi.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0005,   # deriva 0.5 mJ, sotto la soglia 1e-3 J
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)
    assert not any("deriva fra il delta dei bordi" in n for n in _notes(res))
    assert res.package_energy_j == pytest.approx(60.0)


# --------------------------------------------------------------------------
# 8b) percorso senza bordi: il comportamento osservabile non cambia
# --------------------------------------------------------------------------
def test_percorso_buffer_valore_di_riga_e_quote_invariati():
    """Senza bordi di misura la riga vale ancora la lettura esatta della finestra.

    Verifica che il punto B non sposti nulla sul percorso secondario: qui
    ``e_package`` viene da ``package_energy_exact_between`` sulla finestra
    intera (60 J) e le due sub sommano allo stesso numero perche' e' lo stesso
    contatore sulla stessa base temporale. La separazione ripartisce 60 con il
    rapporto 40:20, cio' che gia' faceva, e ``emi_edge_source`` resta
    ``buffer-interp``: la nota di provenienza dice il buffer, non i bordi.
    """
    sess = _Sessione({
        (1000.0, 1004.0): 60.0,
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,
    })
    edge_ttft = dict(_edge(1000.15, 0.0, 0))
    edge_ttft["t_ttft_mono"] = 1000.15
    prof = CasualWattLocalEnergyProfiler()
    prof.session = sess
    res = prof.profile_window(
        1000.0, 1004.0,
        ollama_pids=[7], direct_cpu_delta=6.0, direct_busy_delta=8.0,
        baseline_pre_w=sess.idle_power_w, edge_ttft=edge_ttft,
    )

    assert res.emi_edge_source == "buffer-interp"
    assert res.package_energy_j == pytest.approx(60.0)
    assert res.active_energy_j == pytest.approx(20.0)
    assert res.package_energy_ttft_j == pytest.approx(40.0)
    assert res.package_energy_generation_j == pytest.approx(20.0)
    assert (res.package_energy_ttft_j + res.package_energy_generation_j
            == pytest.approx(res.package_energy_j))
    assert not any("deriva fra il delta dei bordi" in n for n in _notes(res))


# --------------------------------------------------------------------------
# 9) scorrere TTFT non tocca attribuzione CPU, share, potenza idle
# --------------------------------------------------------------------------
def test_scorrere_ttft_non_cambia_share_ne_attribuzione_cpu():
    """Ramo TTFT attivo vs assento: le altre componenti energetiche sono identiche.

    Verifica che ``cpu_time_share``, ``ollama_active_energy_j`` e
    ``idle_power_w`` non cambino fra la stessa riga con e senza separazione
    TTFT: lo scorporo in due sottofinestre e' un'operazione sulle tre grandezze
    ``package``, ``baseline``, ``active`` e non tocca ne' la quota ne' la
    attribuzione CPU.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    with_ttft_sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,
    })
    without_sess = _Sessione({})
    with_ttft = _profile(with_ttft_sess, e0, e1, t_ttft_mono=1000.15)
    without = _profile(without_sess, e0, e1, t_ttft_mono=None)

    # package e active identici (bordo = 60 J, somma sub = 60 J)
    assert with_ttft.package_energy_j == pytest.approx(without.package_energy_j)
    assert with_ttft.active_energy_j == pytest.approx(without.active_energy_j)
    assert with_ttft.cpu_time_share == pytest.approx(without.cpu_time_share)
    assert with_ttft.ollama_active_energy_j == pytest.approx(
        without.ollama_active_energy_j)
    assert with_ttft.idle_power_w == pytest.approx(without.idle_power_w)


# --------------------------------------------------------------------------
# 10) la nota pubblicata dichiara la ripartizione come STIMA
# --------------------------------------------------------------------------
def test_nota_dichiara_ripartizione_proporzionale_non_misura():
    """La nota in ``notes`` dice che le due quote sono una ripartizione, non due misure.

    Perche' esiste. I sei campi di fase sono la ripartizione proporzionale del
    valore di riga: ``package_energy_ttft_j`` non e' la lettura del contatore
    nella sottofinestra TTFT, bensi' ``e_package * s``. Chi legge il CSV vede
    pero' solo ``notes``, e la nota che accompagna la separazione descriveva il
    *meccanismo* («due sottofinestre, baseline scalata su ciascuna») senza dire
    che il numero e' una stima. E' la stessa obbligazione gia' soddisfatta per
    l'attribuzione CPU, dove ``cpu_attribution_method`` scrive "ESTIMATE", e la
    stessa obbligazione che il punto B ha chiuso nei commenti dei campi: qui si
    fissa il token **pubblicato**, perche' un'annotazione di codice non arriva
    all'analista che apre il dataset.

    Verifica che la nota contenga la parola che nomina la natura del numero
    (``STIMA``), la parola che nomina l'operazione (``ripartizione
    proporzionale``) e il rapporto che la produce; e che non affermi che le due
    fasi sono state misurate. Il testo esatto non e' un requisito di schema --
    ``notes`` e' una colonna libera -- quindi il test asserisce sui token, non
    sulla stringa intera, e regge a un ribilanciamento di parole.
    """
    e0 = _edge(1000.0, 100.0, TS_START)
    e1 = _edge(1004.0, 160.0, TS_END)
    sess = _Sessione({
        (1000.0, 1000.15): 40.0,
        (1000.15, 1004.0): 20.0,
    })
    res = _profile(sess, e0, e1, t_ttft_mono=1000.15)

    note_sep = [n for n in _notes(res) if "separazione TTFT/generazione" in n]
    assert len(note_sep) == 1, \
        f"una sola nota di separazione, trovate {len(note_sep)}: {note_sep}"
    nota = note_sep[0]

    assert "STIMA" in nota, f"la nota non nomina la natura del numero: {nota}"
    assert "ripartizione proporzionale" in nota, \
        f"la nota non nomina l'operazione: {nota}"
    assert "s=e_ttft/(e_ttft+e_gen)" in nota, \
        f"la nota non nomina il rapporto: {nota}"
    assert "non misura delle due fasi" in nota, \
        f"la nota non esclude la lettura come misura di fase: {nota}"
    # Il valore di riga citato nella nota e' P_idle, non una sub: la nota non
    # deve introdurre un numero che il lettore scambierebbe per una misura.
    assert f"P_idle={res.idle_power_w:.3f} W" in nota
