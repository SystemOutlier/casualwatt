# -*- coding: utf-8 -*-
"""
tests/test_compare_codecarbon_gate_p44.py — confronto diagnostico scritto.

Perche' esiste. tools/compare_codecarbon_gate.py trasforma il registro del
probe nel report `codecarbon_confronto.md`. Le pretese del mandato C/D da
verificare qui sono quattro, e tutte con aritmetica a mano su fixture
sintetiche (i dati di una campagna vera non esistono finche' la campagna
non e' eseguita — e il report reale NON si committa: sarebbe un numero
inventato):
(1) allineamento: la finestra del controllo deriva dai bordi monotoni
    proiettati sui campioni wall della serie, e la sovrapposizione con la
    run CC puo' essere piena, parziale o assente — tre comportamenti
    diversi, non un numero solo;
(2) l'energia CC "nella stessa finestra" e' una STIMA a potenza costante
    (cpu_energy/duration x overlap): il test fissa i valori e verifica
    che la stima e lo scarto contro E_pkg_gross siano quell'aritmetica;
(3) campionamento piu' rado della finestra (15 s contro dt_W 2,85 s) deve
    degradare il confronto a QUALITATIVO, dichiarato nel report;
(4) assenza di artefatti CC -> exit 2 senza scrivere nulla; status
    unavailable -> il motivo ENTRA nel report, exit 0, nessuna riga
    quantitativa inventata.

Il report non deve contenere un secondo verdetto: le asserzioni (1) e (4)
verificano anche le due frasi-obbligo (nessun verdetto, non e' una replica
metrologica) e il caveat same-counter 0x611 quando presente.

Falsi: qui E' tutto finto per costruzione — i fixture sono i file che il
probe e il runner scriverebbero. La forma dei campi e' presa dagli
artefatti reali del 2026-11-08 (blocks_controllo.json,
control_power_series.json con wall/t, manifest del probe).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import compare_codecarbon_gate as cmp  # noqa: E402

BID = "m__ctrl-1__b01"
LABEL = "controllo-1"
# finestra wall dai bordi t0=100,0 / t1=102,85 proiettati sui campioni
# (t,wall) = (100,1000) (101,1001) (102,1002) (103,1003): (1000,0, 1003,0)
W0, W1 = 1000.0, 1003.0
CPU_KWH = 2.4e-5                 # = 86,4 J
DURATA_RUN = 11.0                # p_media = 86,4/11 = 7,854545... W
E_GROSS = 30.0                   # J, package gate sulla finestra
P_MEDIA = CPU_KWH * cmp.KWH_TO_J / DURATA_RUN


def _status(intervallo=1.0, stato="ok", reason=None):
    return {
        "codecarbon_status": stato,
        "reason": reason,
        "codecarbon_version": "3.3.2-fake",
        "measure_power_secs_requested": 1.0,
        "measure_power_secs_used": intervallo,
        "measure_power_secs_fallback": False,
        "pue": 1.0,
        "tracking_mode": "machine",
        "backend": {"hardware": ["RAM()", "CPU(Windows Emi)"],
                    "cpu_mode": "windows_emi",
                    "cpu_kind": "contatore hardware",
                    "gpu_tracciata": False,
                    "ram": "modello di stima (euristica DIMM), non contatore"},
        "same_counter_caveat": ("windows_emi legge MSR_PKG_ENERGY_STATUS "
                                "(0x611), lo stesso registro della catena "
                                "emi-counter di CasualWatt"),
    }


def _manifest(cc_status="ok", run_window=(999.0, 1010.0), block_status=None):
    block_status = block_status or ("ok" if run_window else "skipped")
    run = None
    if block_status == "ok":
        run = {"run_id": "r-1", "timestamp": "2026-11-08T21:00:10",
               "duration": DURATA_RUN, "cpu_energy": CPU_KWH,
               "gpu_energy": 0.0, "ram_energy": 1.2e-5,
               "energy_consumed": 3.6e-5, "emissions": 1.0e-6,
               "pue": 1.0}
    return {"blocchi": [{
        "block_id": LABEL, "arm": "control", "pair_id": "pair-0",
        "wall_start_s": run_window[0] if run_window else 999.0,
        "wall_end_s": run_window[1] if run_window else 1000.0,
        "block_status": block_status,
        "reason": None if block_status == "ok" else "probe non attivo",
        "run": run}]}


def _scrivi(archivio: Path, *, status=None, manifest=None, serie=None,
            blocks=None, cc=True):
    """cc=False riproduce la campagna eseguita senza --codecarbon: i tre
    file del gate c'esistono, la directory codecarbon/ non esiste proprio
    (il probe non l'ha mai creata) — non una directory vuota."""
    cc_dir = archivio / "codecarbon"
    if cc:
        cc_dir.mkdir(parents=True, exist_ok=True)
    analysis = {
        "status": "pass", "bias_w": 0.1, "bias_threshold_w": 0.223607,
        "quorum": 1, "n_pairs": 1, "chain_status": "gate",
        "controls": [{"block_id": BID, "pair_id": "pair-0", "usable": True,
                      "e_net_j": 0.1, "dt_w_s": 2.85,
                      "budget_base_w": 0.223607,
                      "window_source": "exact-counter"}],
        "runs": [{"block_id": BID, "label": LABEL, "arm": "control",
                  "pair_id": "pair-0"}]}
    if serie is None:
        serie = [{"block_id": BID, "t0_mono": 100.0, "t1_mono": 102.85,
                  "samples": [{"t": 100.0, "wall": 1000.0},
                              {"t": 101.0, "wall": 1001.0},
                              {"t": 102.0, "wall": 1002.0},
                              {"t": 103.0, "wall": 1003.0}]}]
    if blocks is None:
        blocks = [{"block_id": BID, "control_e_pkg_gross_j": E_GROSS,
                   "baseline_pre_w": 10.0}]
    (archivio / "analysis.json").write_text(
        json.dumps(analysis), encoding="utf-8")
    (archivio / "blocks_controllo.json").write_text(
        json.dumps(blocks), encoding="utf-8")
    (archivio / "control_power_series.json").write_text(
        json.dumps(serie), encoding="utf-8")
    if cc:
        (cc_dir / cmp.STATUS_NAME).write_text(
            json.dumps(status or _status()), encoding="utf-8")
        if manifest is not False:
            (cc_dir / cmp.MANIFEST_NAME).write_text(
                json.dumps(manifest or _manifest()), encoding="utf-8")
    return archivio


# ---------------------------------------------------------------------------
# 1. Allineamento pieno: la stima CC nella finestra E' l'aritmetica dichiarata
# ---------------------------------------------------------------------------
def test_allineamento_pieno_stima_e_scarto_sono_laritmetica_dichiarata(
        tmp_path):
    """Run CC [999,1010] copre la finestra [1000,1003]: sovrapposizione
    piena 3 s. Stima = (86,4 J / 11 s) x 3 s = 23,563636 J; scarto contro
    E_pkg_gross 30 J = +6,436364 J. Il report deve portare questi numeri
    (non "circa"), il caveat 0x611 e le due frasi-obbligo: nessun secondo
    verdetto, non e' una replica metrologica."""
    archivio = _scrivi(tmp_path / "a")
    data = cmp._carica(archivio)
    righe = cmp._confronta(data)
    a = righe[0]["allineamento"]
    assert a["tipo"] == "piena"
    assert a["overlap_s"] == pytest.approx(3.0)
    assert a["e_cc_stimata_j"] == pytest.approx(P_MEDIA * 3.0)
    assert a["scarto_j"] == pytest.approx(E_GROSS - P_MEDIA * 3.0)
    assert righe[0]["cc"]["cpu_energy_j"] == pytest.approx(86.4)
    assert righe[0]["cc"]["ram_energy_j"] == pytest.approx(43.2)
    assert righe[0]["cc"]["gpu_energy_j"] == 0.0
    assert cmp.main(["--archive", str(archivio)]) == 0
    testo = (archivio / cmp.REPORT_NAME).read_text(encoding="utf-8")
    assert "0x611" in testo
    assert "non contiene un secondo verdetto" in testo
    assert "STIMA a potenza costante" in testo
    assert "tipo `piena`" in testo
    assert f"{P_MEDIA * 3.0:.3f}" in testo
    assert f"{E_GROSS - P_MEDIA * 3.0:+.3f}" in testo
    assert "bias_w = 0.100000" in testo  # citato, non ricalcolato


def test_bordi_wall_da_nearest_sample_con_campioni_disallineati(tmp_path):
    """La proiezione t0/t1 sui campioni piu' vicini non e' una lettura:
    con campioni a 1 s e bordi a 100,4/102,4 la finestra dichiarata deve
    essere (1000,5+? no) — qui: nearest di 100,4 e' t=100,5->wall 1000,5,
    nearest di 102,4 e' 102,5->wall 1002,5. Il test fissa la regola del
    nearest, perche' un bordo inventato per linearita' sarebbe un
    allineamento migliore di quello che i dati sostengono."""
    serie = [{"block_id": BID, "t0_mono": 100.4, "t1_mono": 102.4,
              "samples": [{"t": 100.5, "wall": 1000.5},
                          {"t": 101.5, "wall": 1001.5},
                          {"t": 102.5, "wall": 1002.5}]}]
    archivio = _scrivi(tmp_path / "b", serie=serie)
    data = cmp._carica(archivio)
    fin = cmp._finestra_controllo(data["serie"][0])
    assert fin == (1000.5, 1002.5)


# ---------------------------------------------------------------------------
# 2. Assenza e indisponibilita': i due percorsi dichiarati dal mandato D
# ---------------------------------------------------------------------------
def test_senza_artefatti_cc_exit_2_e_nessun_file_scritto(tmp_path):
    """Campagna eseguita senza --codecarbon: i tre file del gate ci sono,
    la directory codecarbon/ no. Il confronto deve fermarsi con exit 2,
    dire PERCHE' (possibile omissione del flag o data sbagliata) e non
    creare alcun report — un file che dice "niente da confrontare"
    sporchebbe l'archivio di una campagna che non ha il registro."""
    archivio = tmp_path / "c"
    archivio.mkdir()
    _scrivi(archivio, cc=False)
    assert cmp.main(["--archive", str(archivio)]) == 2
    assert not (archivio / cmp.REPORT_NAME).exists()


def test_status_unavailable_porta_il_motivo_nel_report(tmp_path):
    """codecarbon_status = unavailable: il report si scrive (exit 0), il
    motivo comparire, e nessuna riga quantitativa viene inventata per i
    blocchi senza run — la riga dice "senza dati" con la ragione del
    blocco. E' il caso 'CodeCarbon non riesce a leggere i contatori'."""
    status = _status(intervallo=None, stato="unavailable",
                     reason="codecarbon non importabile (ImportError)")
    manifest = _manifest(block_status="skipped")
    archivio = _scrivi(tmp_path / "d", status=status, manifest=manifest)
    assert cmp.main(["--archive", str(archivio)]) == 0
    testo = (archivio / cmp.REPORT_NAME).read_text(encoding="utf-8")
    assert "unavailable" in testo
    assert "codecarbon non importabile" in testo
    assert "senza dati" in testo
    assert "STIMA a potenza costante" not in testo.split(
        "## Blocchi di controllo")[1]  # nessuna stima per blocco


# ---------------------------------------------------------------------------
# 3. Sovrapposizione parziale e assente: due trattamenti distinti
# ---------------------------------------------------------------------------
def test_sovrapposizione_parziale_scala_la_stima_e_dichiara(tmp_path):
    """Run CC [1001,1010]: overlap con la finestra = 2 s su 3. Tipo
    parziale, stima p_media x 2 s, scarto ricalcolato sull'overlap — non
    sulla finestra intera: presentare la stima come se coprisse 3 s
    sarebbe un numero piu' grande del dato."""
    archivio = _scrivi(tmp_path / "e",
                       manifest=_manifest(run_window=(1001.0, 1010.0)))
    data = cmp._carica(archivio)
    a = cmp._confronta(data)[0]["allineamento"]
    assert a["tipo"] == "parziale"
    assert a["overlap_s"] == pytest.approx(2.0)
    assert a["e_cc_stimata_j"] == pytest.approx(P_MEDIA * 2.0)
    assert a["scarto_j"] == pytest.approx(E_GROSS - P_MEDIA * 2.0)


def test_finestra_fuori_dalla_run_confronto_non_fatto(tmp_path):
    """Run CC [1004,1010] e finestra [1000,1003]: sovrapposizione zero.
    Tipo assente, NESSUNA stima e NESSUN scarto nel record e nel report:
    un numero a sovrapposizione zero sarebbe un incrocio di finestre
    diverse spacciato per confronto."""
    archivio = _scrivi(tmp_path / "f",
                       manifest=_manifest(run_window=(1004.0, 1010.0)))
    data = cmp._carica(archivio)
    riga = cmp._confronta(data)[0]
    a = riga["allineamento"]
    assert a["tipo"] == "assente"
    assert "e_cc_stimata_j" not in a
    assert "scarto_j" not in a
    assert cmp.main(["--archive", str(archivio)]) == 0
    testo = (archivio / cmp.REPORT_NAME).read_text(encoding="utf-8")
    assert "`assente`" in testo


def test_serie_senza_campioni_non_allineabile(tmp_path):
    """La serie di potenza puo' mancare i campioni (blocco con lettura
    degradata): senza bordi wall la finestra NON e' decidibile — tipo
    non-allineabile, non finestra zero. Dedurla dalla durata del run
    sarebbe esattamente l'invenzione che il tool dichiara di non fare."""
    serie = [{"block_id": BID, "t0_mono": 100.0, "t1_mono": 102.85,
              "samples": []}]
    archivio = _scrivi(tmp_path / "g", serie=serie)
    data = cmp._carica(archivio)
    a = cmp._confronta(data)[0]["allineamento"]
    assert a["tipo"] == "non-allineabile"
    assert a["finestra_wall_s"] is None


# ---------------------------------------------------------------------------
# 4. Campionamento piu' rado della finestra: degrado a qualitativo
# ---------------------------------------------------------------------------
def test_campionamento_oltre_la_finestra_degrada_a_qualitativo(tmp_path):
    """Con measure_power_secs 15 s e dt_W 2,85 s la media CC non puo'
    guardare DENTRO la finestra: il confronto resta una quantita' del
    blocco, non della finestra, e il report deve usare la parola
    QUALITATIVO. Con 1 s la nota non compare: il degrado e' legato ai
    dati, non alla presenza del flag."""
    archivio = _scrivi(tmp_path / "h", status=_status(intervallo=15.0))
    data = cmp._carica(archivio)
    a = cmp._confronta(data)[0]["allineamento"]
    assert "QUALITATIVO" in a["campionamento"]
    assert cmp.main(["--archive", str(archivio)]) == 0
    testo = (archivio / cmp.REPORT_NAME).read_text(encoding="utf-8")
    assert "QUALITATIVO" in testo

    archivio2 = _scrivi(tmp_path / "h2")
    assert cmp.main(["--archive", str(archivio2)]) == 0
    testo2 = (archivio2 / cmp.REPORT_NAME).read_text(encoding="utf-8")
    assert "QUALITATIVO" not in testo2
