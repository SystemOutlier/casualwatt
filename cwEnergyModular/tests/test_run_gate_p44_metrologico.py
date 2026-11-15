# -*- coding: utf-8 -*-
"""
tests/test_run_gate_p44_metrologico.py — grandezze metrologiche del gate P4.4.

Perche' esiste. La produzione di run_gate_p44.py e' gia' corretta per le
correzioni della verifica del 2026-11-09 (criterio primario a scala Tc,
incertezza senza doppio conteggio, u_c = RSS solo incluse, u_A = s/sqrt(n),
quorum a 12 coppie, dt_nominal_s congelato). Mancavano i test di:

1. integrita' di dt_nominal_frozen.json: SHA-256 del CSV pilota, mediana
   della durata e valore congelato coerenti fra loro;
2. gestione di bias_w NaN/inf/None nel verdetto primario (deve essere
   not-executable, mai un fail silenzioso su un numero inesistente);
3. gestione di u_A NaN/inf/None nel post-controlli (u_c deve restare None
   se l'unica componente inclusa e' assente; mai zero);
4. riproducibilita' del seme: stesso order_seed genera lo stesso ordine di
   blocchi e di pair_id, a partire da una coppia in poi.

Che cosa NON verifica: il criterio F.12 (test_control_gate_p45.py),
l'orchestrazione end-to-end (test_gate_p44_end_to_end.py), la combinazione
dell'incertezza (test_gate_uncertainty_p44.py), il budget pre-esecuzione
(test_budget_p44_preesecuzione.py).
"""
import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pytest  # noqa: E402

import run_gate_p44 as rg  # noqa: E402
from test_gate_p44_end_to_end import _create_idle_characterization  # noqa: E402

TC = rg.DT_NOM_FROZEN


def _letta(potenza, dt=None, canale="emi-counter"):
    dt = TC if dt is None else dt
    return (potenza * dt, dt, canale)


def _sessione_fondo(*letture):
    class _Porta:
        def __init__(self, letture):
            self.letture = list(letture)

        def read_idle_window_j(self, durata_s):
            lettura = self.letture.pop(0)
            if lettura is None:
                return None
            return lettura

    return SimpleNamespace(_source=_Porta(list(letture)))


def _fondo_quioto():
    """Terne pre/post silenziose: pre 9.9/10.0/10.1, post 10.3/10.4/10.5."""
    return _sessione_fondo(*[_letta(p) for p in (9.9, 10.0, 10.1)],
                           *[_letta(p) for p in (10.3, 10.4, 10.5)])


def _piano_minimo():
    """Piano minimo per _calcola_budget_pre_esecuzione.
    La funzione legge plan.get('baseline_params', {}) con valori di default,
    quindi un dizionario vuoto e' sufficiente."""
    return {}

PILOTA = (Path(__file__).resolve().parents[2]
          / "experiment_results" / "p29_pilot_20261107")
FROZEN = PILOTA / "dt_nominal_frozen.json"
CSV_PILOTA = PILOTA / "casualwatt_v4_results_p29.csv"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _durate_valide_csv(path: Path):
    """Durata delle righe valide: same rule as the pilot (median on all
    valid rows). Usata solo per ricalcolare la mediana ancorata al CSV."""
    durate = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for riga in csv.DictReader(fh):
            try:
                valore = float(riga.get("duration_s", ""))
            except (TypeError, ValueError):
                continue
            if valore > 0.0 and math.isfinite(valore):
                durate.append(valore)
    return durate


# ---------------------------------------------------------------------------
# 1. integrita' di dt_nominal_frozen.json
# ---------------------------------------------------------------------------
def test_dt_nominal_frozen_coerente_con_csv_pilota():
    """Il numero congelato (2,930748 s) e' 3 x mediana di tutte le durate
    valide del CSV pilota, e lo SHA-256 del CSV registrato nel JSON e'
    quello del file sul disco. Se uno dei due numeri fosse cambiato dopo la
    dichiarazione, la terza campagna userebbe una scala Tc diversa da quella
    pre-registrata."""
    congelato = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert congelato["dt_nominal_s"] == pytest.approx(2.930748)
    assert congelato["formula"].startswith("3 x mediana")

    sha_csv = congelato["source"]["results_csv_sha256"]
    sha_disco = _sha256_file(CSV_PILOTA)
    assert sha_csv == sha_disco

    durate = _durate_valide_csv(CSV_PILOTA)
    assert sorted(durate) == sorted(congelato["durations_s"])
    n = len(durate)
    medio = sorted(durate)[n // 2] if n % 2 else (
        (sorted(durate)[n // 2 - 1] + sorted(durate)[n // 2]) / 2.0)
    assert congelato["median_duration_s"] == pytest.approx(medio)
    assert congelato["dt_nominal_s"] == pytest.approx(3.0 * medio)


def test_dt_nominal_frozen_valore_non_inventato():
    """La formula del JSON e' dichiarata e il numero risulta da essa, non
    da una costante scritta a mano nel tool: DT_NOM_FROZEN e' lo stesso
    valore del JSON, letto dal pilot P2.9 prima della campagna."""
    congelato = json.loads(FROZEN.read_text(encoding="utf-8"))
    assert rg.DT_NOM_FROZEN == pytest.approx(congelato["dt_nominal_s"])
    assert rg.DT_NOM_FROZEN == pytest.approx(
        3.0 * congelato["median_duration_s"])


# ---------------------------------------------------------------------------
# 2. bias_w NaN / inf / None nel verdetto primario
# ---------------------------------------------------------------------------
def test_verdetto_primario_bias_none_e_not_executable():
    """bias_w mancante (controlli non usabili o gate non eseguibile) non
    produce un fail: il verdetto e' not-executable e margine None."""
    base = {"status": "fail", "bias_w": None, "quorum": 8,
            "controls_usable_n": 0}
    out = rg._verdetto_primario(base, budget_w=0.20)
    assert out["status"] == "not-executable"
    assert out["margine_w"] is None
    assert out["criterio"] == rg.CRITERIO_PRIMARIO


@pytest.mark.parametrize("bias", [float("nan"), float("inf"), -float("inf")])
def test_verdetto_primario_bias_non_finito_not_executable(bias):
    """Un bias non finito non e' un numero misurato: il verdetto non puo'
    confrontarlo col budget e si ferma con not-executable, mai pass/fail
    su NaN o inf."""
    base = {"status": "fail", "bias_w": bias, "quorum": 8,
            "controls_usable_n": 6}
    out = rg._verdetto_primario(base, budget_w=0.20)
    assert out["status"] == "not-executable"
    assert out["margine_w"] is None


def test_verdetto_primario_bias_finito_normale():
    """Bias finito si confronta col budget: |bias| <= budget e' pass."""
    base = {"status": "fail", "bias_w": 0.125171, "quorum": 8,
            "controls_usable_n": 6}
    out = rg._verdetto_primario(base, budget_w=0.20)
    assert out["status"] == "pass"
    assert out["margine_w"] == pytest.approx(0.20 - 0.125171)


# ---------------------------------------------------------------------------
# 3. u_A NaN / inf / None nel post-controlli
# ---------------------------------------------------------------------------
def test_u_a_con_potenza_netta_none_resta_none_non_zero():
    """Un controllo con e_net_j = None non entra nelle potenze nette; se
    resta un solo controllo usabile, u_A = None (non zero) e u_c = None."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _fondo_quioto(), _piano_minimo())[1]
    pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    post = rg._incertezza_con_au_controlli(
        pre, [{"usable": True, "e_net_j": None, "dt_w_s": 3.0}])
    assert post["u_A"] is None
    assert post["u_c"] is None
    assert post["potenze_nette_w"] == []
    assert post["soglia_w"] == pytest.approx(pre["budget_base_w"])


def test_u_a_con_dt_w_s_inf_resta_none():
    """dt_w_s = +inf non e' una durata: il controllo e' escluso dalla
    dispersione e u_A resta None con la sua ragione."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _fondo_quioto(), _piano_minimo())[1]
    pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    post = rg._incertezza_con_au_controlli(
        pre, [{"usable": True, "e_net_j": 0.3, "dt_w_s": float("inf")}])
    assert post["u_A"] is None
    assert post["potenze_nette_w"] == []
    assert "almeno una coppia" in post["componenti"]["u_A"]["fonte"]


def test_u_a_con_e_net_j_non_finito_escluso():
    """e_net_j = NaN o +inf non produce una potenza netta: il controllo
    sparisce dalla dispersione senza inquinare s / sqrt(n)."""
    det = rg._calcola_budget_pre_esecuzione(
        "short", _fondo_quioto(), _piano_minimo())[1]
    pre = rg._incertezza_pre_esecuzione(det, 0.0156)
    post = rg._incertezza_con_au_controlli(
        pre, [{"usable": True, "e_net_j": float("nan"), "dt_w_s": 3.0},
              {"usable": True, "e_net_j": 0.12, "dt_w_s": 3.0}])
    assert post["potenze_nette_w"] == [pytest.approx(0.04)]
    assert post["u_A"] is None  # un solo valore: nessuna dispersione fra blocchi


# ---------------------------------------------------------------------------
# 4. riproducibilita' del seme
# ---------------------------------------------------------------------------
def test_stesso_seed_stesso_ordine_blocchi(monkeypatch):
    """Stesso order_seed -> stesso piano, stesso ordine di bracci e di
    pair_id. Un seme diverso invece cambia il disegno dichiarato e quindi
    _verifica_piano lo rifiuta (piano 6 / tool 6 e' il disegno dichiarato)."""
    monkeypatch.setattr(rg, "N_COPPIE", rg.N_COPPIE)
    monkeypatch.setattr(rg, "N_BLOCCHI", rg.N_BLOCCHI)
    rg._imposta_coppie(6)

    blocchi_a = rg.plan_blocks()
    rg._imposta_coppie(6)
    blocchi_b = rg.plan_blocks()

    assert [b["pair_id"] for b in blocchi_a] == [b["pair_id"] for b in blocchi_b]
    assert [b["arm"] for b in blocchi_a] == [b["arm"] for b in blocchi_b]
    assert [b["index"] for b in blocchi_a] == [b["index"] for b in blocchi_b]
    assert [b["pair_id"] for b in blocchi_a] == [
        f"pair-{i // 2}" for i in range(12)]


def test_seed_diverso_cambia_il_piano_dichiarato(tmp_path, monkeypatch):
    """Il seme e' parte del disegno dichiarato: cambiarlo senza ripianificare
    fa fallire la verifica del piano, come ogni altra manomissione post-dati."""
    monkeypatch.setattr(rg, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(rg, "_git_head", lambda: "test-head")
    _create_idle_characterization(tmp_path)
    rg.cmd_plan(rg.DEFAULT_MODEL)
    piano = json.loads(
        (rg.ARCHIVE_DIR / rg.PLAN_NAME).read_text(encoding="utf-8"))
    piano["order_seed"] = "seed-altro"
    (tmp_path / rg.PLAN_NAME).write_text(
        json.dumps(piano), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        rg._verifica_piano()
    msg = str(exc.value)
    assert "seed" in msg
