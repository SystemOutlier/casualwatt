# -*- coding: utf-8 -*-
"""N/A, non 0.0: una componente energetica non stimata resta assente (difetto F2).

Il test esiste perche' `benchmark_unified.py:1101` (prima di questa correzione)
scriveva `cloud_j = est.energy_j or 0.0`. Quando la catena di stima cloud
falliva -- modello non registrato, proxy non dichiarato, eccezione del motore --
`energy_j` era `None` e l'`or` lo convertiva in `0.0` Joule. Nella riga CSV
quella conversione e' indistinguibile da un costo cloud realmente nullo, e il
consumatore non ha modo di saperlo: `genera_grafici_tesi.py:79` filtra
`end_to_end_energy_j > 0`, quindi la riga non viene scartata come "senza dato"
bensi' aggregata con un end-to-end sottostimato di tutta la componente cloud.
Le medie di `energy_per_output_token_j`, di `ece_per_joule` e di
`epcl_j_per_link` -- che sono gli indicatori di efficienza della tesi --
si abbassano in favore del metodo che non ha prodotto stima.

La regola violata e' quella del repository: **uno zero legittimo e' dichiarato,
non inventato** (AGENTS.md, "Nessun troncamento"; stessa logica di
`idle_provenance = "uncalibrated"` in `energy/local_energy.py:196-203`). Da qui
le due proprieta' che questo file congela, nell'ordine:

  1. `None` in ingresso -> `"N/A"` in uscita, con nota che dice quale componente
     manca, e `end_to_end_energy_j` **non** pubblicato come somma parziale;
  2. `0.0` in ingresso -> `0.0` in uscita, perche' il confine di misura della
     regola 12.1 (rete e cloud zero in modalita' locale) e' un'assenza
     **dichiarata dal chiamante**, non una stima fallita.

La (2) e' la guardia contro la correzione sbagliata: un `if not cloud_j` al
posto di `if cloud_j is None` cancellerebbe il confine 12.1, e un `or 0.0` di
nuovo cancellerebbe il `None`.

La (3) chiude il difetto F9: lo zero di confine della riga locale deve portare
`cloud_energy_method = "not-applicable"` e il suo `cloud_estimation_boundary`,
altrimenti resta indistinguibile da una stima cloud fallita. Vale la stessa
regola della (2): uno zero e' legittimo solo se la riga lo dichiara.

Esecuzione:  python -m pytest tests/test_cloud_energy_none_preservato.py -v
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import benchmark_unified as bu                                      # noqa: E402


def _ev(**kw):
    """Valutazione minima: i soli campi che _finalize_energy_fields legge."""
    base = dict(n_correct_links=None, acc_comp=None, is_correct=None,
                acc_links_basis="", acc_links=None, judge_score=None,
                cosine_sim=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _rec(**kw):
    """Record nel punto in cui il chiamante ha gia' scritto token e griglia."""
    base = {"output_tokens": 10, "notes": "",
            "local_carbon_intensity_gco2eq_kwh": 0}
    base.update(kw)
    return base


# ------------------------------------------------------------------ (1)
def test_cloud_none_diventa_na_e_non_zero():
    """stima cloud assente -> cloud_energy_j='N/A'; round(None) levanterebbe TypeError."""
    rec = _rec()
    bu._finalize_energy_fields(rec, 5.0, 0.25, None, _ev())
    assert rec["cloud_energy_j"] == "N/A"
    assert rec["cloud_energy_kwh"] == "N/A"


def test_end_to_end_non_e_una_somma_parziale():
    """Con una componente assente l'end-to-end e' N/A: local+rete senza cloud non E' un costo totale."""
    rec = _rec()
    bu._finalize_energy_fields(rec, 5.0, 0.25, None, _ev())
    assert rec["end_to_end_energy_j"] == "N/A"
    # e le componenti disponibili restano pubblicate: N/A e' solo l'insieme.
    assert rec["local_energy_j"] == pytest.approx(5.0)
    assert rec["network_energy_j"] == pytest.approx(0.25)


def test_nota_dichiara_quale_componente_manca():
    """L'assenza deve essere leggibile nella riga, non solo inferita dal valore."""
    rec = _rec(notes="richiesta ok")
    bu._finalize_energy_fields(rec, 5.0, 0.25, None, _ev())
    assert "cloud_energy_j" in rec["notes"]
    assert "end_to_end_energy_j=N/A" in rec["notes"]
    assert rec["notes"].startswith("richiesta ok; ")


def test_derivati_di_efficienza_non_usano_un_denominatore_fittizio():
    """J/token, ECE ed EPCL restano N/A: calcolarli su una somma parziale li gonfierebbe verso il basso."""
    rec = _rec()
    ev = _ev(acc_comp=0.8, is_correct=1, n_correct_links=2,
             acc_links_basis="f1_triples")
    bu._finalize_energy_fields(rec, 5.0, 0.25, None, ev)
    assert rec["energy_per_output_token_j"] == "N/A"
    assert rec["ece_per_joule"] == "N/A"
    assert rec["epcl_j_per_link"] == "N/A"
    assert rec["energy_per_correct_answer_j"] == "N/A"


# ------------------------------------------------------------------ (2)
def test_zero_di_confine_regola_12_1_resta_numeric():
    """La modalita' locale passa 0.0 espliciti: sono il confine di misura, non un fallimento."""
    rec = _rec()
    bu._finalize_energy_fields(rec, 40.0, 0.0, 0.0, _ev())
    assert rec["cloud_energy_j"] == pytest.approx(0.0)
    assert rec["network_energy_j"] == pytest.approx(0.0)
    assert rec["end_to_end_energy_j"] == pytest.approx(40.0)
    assert rec["energy_per_output_token_j"] == pytest.approx(4.0)
    assert "end_to_end_energy_j=N/A" not in rec["notes"]


def test_cloud_zero_legittimo_non_diventa_na():
    """Guardia contro il `or 0.0` e contro un futuro `if not cloud_j`: 0.0 non e' None."""
    rec = _rec()
    bu._finalize_energy_fields(rec, 1.0, 0.0, 0.0, _ev())
    assert rec["cloud_energy_j"] == 0.0
    assert rec["cloud_energy_kwh"] == 0.0


def test_percorso_completo_invariato():
    """Tre componenti numeriche: gli stessi numeri e gli stessi derivati di prima della correzione."""
    rec = _rec()
    ev = _ev(acc_comp=0.8, is_correct=1, n_correct_links=3,
             acc_links_basis="f1_triples")
    bu._finalize_energy_fields(rec, 60.0, 2.0, 8.0, ev)
    assert rec["end_to_end_energy_j"] == pytest.approx(70.0)
    assert rec["energy_per_output_token_j"] == pytest.approx(7.0)
    assert rec["energy_per_correct_answer_j"] == pytest.approx(70.0)
    assert rec["epcl_j_per_link"] == pytest.approx(70.0 / 3.0)
    assert rec["ece_per_joule"] == pytest.approx(0.8 / 70.0)
    assert rec["cloud_energy_kwh"] == pytest.approx(8.0 / 3_600_000.0)


def test_emissioni_locali_reggono_assenza_locale():
    """Se il locale manca, i kWh e le emissioni locali sono N/A: non 0 gCO2eq."""
    rec = _rec(local_carbon_intensity_gco2eq_kwh=267.0)
    bu._finalize_energy_fields(rec, None, 0.0, 1.0, _ev())
    assert rec["local_energy_kwh"] == "N/A"
    assert rec["local_emissions_gco2eq"] == "N/A"
    assert rec["cloud_energy_j"] == pytest.approx(1.0)


# ------------------------------------------------------------------ (3)
def _riga(mode, monkeypatch):
    """Riga costruita dal template, con l'intensita' di carbonio resa offline."""
    monkeypatch.setattr(
        bu, "get_carbon_intensity",
        lambda zone=None: SimpleNamespace(
            gco2eq_per_kwh=267.0, zone="IT", source="test-table", timestamp=0.0))
    return bu._basic_record(
        "R1", "S1", "llama", "llama", "ollama", mode, None,
        {"id": "p1", "text": "p", "source": "manual", "ground_truth": "21"},
        bu.evalres_placeholder())


def test_riga_locale_dichiara_metodo_e_confine_del_cloud(monkeypatch):
    """Lo zero cloud della riga locale deve dire di essere un confine (difetto F9).

    Senza i due campi quello zero e' indistinguibile da una stima fallita: la
    regola 12.1 lo ammette solo se il confine lo dichiara.
    """
    rec = _riga("local", monkeypatch)
    assert rec["cloud_energy_j"] == 0.0
    assert rec["cloud_energy_method"] == "not-applicable"
    assert rec["cloud_estimation_boundary"] == "not-applicable (local mode)"


def test_riga_cloud_non_pre_etichetta_un_metodo(monkeypatch):
    """Il template non scrive un nome di metodo per un percorso non ancora invocato.

    Il metodo della riga cloud lo scrive il blocco che produce la stima, insieme
    al valore; qui -- prima della stima -- deve restare vuoto.
    """
    rec = _riga("cloud", monkeypatch)
    assert rec["cloud_energy_method"] == ""
    assert rec["cloud_estimation_boundary"] == ""


# ------------------------------------------------------------------ log
def test_j_log_non_maschera_l_assenza():
    """Il log deve dire N/A, non schiantarsi su :.3f ne' stampare 0.000 J."""
    assert bu._j_log(None) == "N/A"
    assert bu._j_log(0.0) == "0.000"
    assert bu._j_log(12.3456) == "12.346"
