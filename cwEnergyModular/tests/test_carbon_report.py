# -*- coding: utf-8 -*-
"""Guardie del reporter carbonio di sola analisi.

Il modulo esiste per produrre un report emissioni SOPRA l'energia misurata,
con la formula kWh corretta e fattori dichiarati. Il bug del modulo mock
(energy/carbon_emissions.py, non tracciato) era un fattore 1000x: usava i Wh
come kWh. Qui si fissano la conversione, la formula e il rifiuto dei fattori
non dichiarati.
"""
import math

import pytest

from carbon_report import (
    JOULE_PER_KWH,
    CarbonFactors,
    CarbonRowResult,
    estimate_emissions_kg,
    illustrative_equivalences,
    joule_to_kwh,
    render_latex,
    report_carbon,
)


def test_joule_to_kwh_un_kwh():
    """3.6e6 J sono esattamente 1 kWh: e' la conversione che il mock sbagliava."""
    assert JOULE_PER_KWH == 3_600_000.0
    assert joule_to_kwh(3_600_000.0) == pytest.approx(1.0)
    assert joule_to_kwh(0.0) == 0.0


def test_joule_to_kwh_negativo_conservato():
    """Il segno si conserva: un delta negativo non si clampa (regola del progetto)."""
    assert joule_to_kwh(-3_600_000.0) == pytest.approx(-1.0)


def test_regressione_fattore_mille():
    """0.1 kWh con PUE 1.2 e rete 0.5 kg/kWh danno 0.06 kg, NON 60 kg.

    E' il bug del mock (Wh usati come kWh), fissato da un test: 360000 J =
    0.1 kWh, e 0.1 * 1.2 * 0.5 = 0.06.
    """
    energy_kwh = joule_to_kwh(360_000.0)
    assert energy_kwh == pytest.approx(0.1)
    assert estimate_emissions_kg(
        energy_kwh, grid_intensity_kg_per_kwh=0.5, pue=1.2
    ) == pytest.approx(0.06)


def test_pue_default_locale():
    """Il default PUE e' 1.0 (host locale), non 1.2 da datacenter."""
    f = CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="ISPRA 2025")
    assert f.pue == 1.0


@pytest.mark.parametrize("grid", [None, float("nan"), float("inf"), 0.0, -0.1])
def test_intensita_rete_non_valida_rifiutata(grid):
    """Intensita' assente/non finita/<=0: rifiuto dichiarato, nessun default."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=grid, grid_source="ISPRA 2025")


def test_fonte_rete_vuota_rifiutata():
    """La fonte e' obbligatoria: un fattore senza provenienza non entra."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="")


def test_pue_non_valido_rifiutato():
    """PUE non finito o <=0 e' un errore dichiarato."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="ISPRA", pue=0.0)


def _provenance():
    return {"input_csv": "in.csv", "input_csv_sha256": "abc",
            "energy_column": "ollama_active_energy_j", "generated_utc": "2026-11-10T00:00:00+00:00"}


def test_report_aggrega_sole_righe_valide():
    """Il totale somma le sole righe ok; le escluse sono conteggiate con ragione."""
    factors = CarbonFactors(0.5, "ISPRA", pue=1.2)
    rows = [{"ollama_active_energy_j": "360000"},
            {"ollama_active_energy_j": ""},
            {"ollama_active_energy_j": "nan"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["label"] == "stima"
    assert s["measured"]["n_rows"] == 3
    assert s["measured"]["n_ok"] == 1
    assert s["measured"]["n_excluded"] == 2
    assert s["measured"]["energy_j_total"] == pytest.approx(360000.0)
    assert s["estimate"]["emissions_kg"] == pytest.approx(0.06)
    assert sum(s["measured"]["excluded_reasons"].values()) == 2


def test_report_energia_negativa_conservata():
    """Un delta negativo resta firmato, non clampato: l'emissione puo' essere negativa."""
    factors = CarbonFactors(0.5, "ISPRA", pue=1.0)
    rows = [{"ollama_active_energy_j": "-360000"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["measured"]["n_ok"] == 1
    assert s["measured"]["energy_j_total"] == pytest.approx(-360000.0)
    assert s["estimate"]["emissions_kg"] == pytest.approx(-0.05)


def test_report_riga_esclusa_ha_ragione():
    """Ogni esclusione dichiara la sua ragione, non sparisce in silenzio."""
    factors = CarbonFactors(0.5, "ISPRA")
    rows = [{"ollama_active_energy_j": "abc"}, {"ollama_active_energy_j": "inf"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["measured"]["n_ok"] == 0
    statuses = [r["status"] for r in s["rows"]]
    assert statuses == ["excluded", "excluded"]
    assert all(r["reason"] for r in s["rows"])


def test_report_provenance_e_label():
    """La provenance porta sha256, fattori con fonte e etichetta 'stima'."""
    factors = CarbonFactors(0.3, "ISPRA 2025")
    s = report_carbon([{"ollama_active_energy_j": "3600000"}], factors,
                      energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["label"] == "stima"
    assert s["provenance"]["input_csv_sha256"] == "abc"
    assert s["provenance"]["module"] == "carbon_report"
    assert s["factors"]["grid_source"] == "ISPRA 2025"
    assert s["factors"]["pue"] == 1.0


def test_latex_contiene_formula_parametri_e_stima():
    """Il template LaTeX dichiara formula, fattori con fonte e l'etichetta
    'stima': e' il pezzo pronto per la tesi, distinto dalla misura."""
    factors = CarbonFactors(0.3, "ISPRA 2025", pue=1.0)
    s = report_carbon([{"ollama_active_energy_j": "3600000"}], factors,
                      energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    tex = render_latex(s, factors)
    assert "stima" in tex
    assert "Energia misurata" in tex
    assert "ISPRA 2025" in tex
    assert "PUE" in tex
    assert "3.6" in tex  # la conversione J -> kWh nella formula


def test_equivalenze_solo_con_fattori_dichiarati():
    """Le equivalenze sono illustrative e solo con fattori dichiarati."""
    eq = {"auto": {"kg_per_unit": 0.12, "unit": "km"}}
    out = illustrative_equivalences(0.06, eq)
    assert len(out) == 1
    assert "illustrativo" in out[0]
    assert "km" in out[0]
    assert illustrative_equivalences(0.06, {}) == []


def test_equivalenze_fattore_non_valido_saltato():
    """Un fattore illustrativo nullo/non finito non produce una riga."""
    eq = {"x": {"kg_per_unit": 0.0, "unit": "u"},
          "y": {"kg_per_unit": float("nan"), "unit": "v"}}
    assert illustrative_equivalences(0.06, eq) == []