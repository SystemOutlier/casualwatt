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
    estimate_emissions_kg,
    joule_to_kwh,
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