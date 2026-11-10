# -*- coding: utf-8 -*-
"""carbon_report — report carbonio di sola analisi sopra energia misurata.

Modulo di analisi (registro di surface_fit.py / geometry.py / control_gate.py):
non e' chiamato dal runner, non tocca lo schema P5 (CSV_COLUMNS resta 174),
non dipende da SESSION. Converte l'energia misurata in kWh e applica fattori
dichiarati con fonte; ogni emissione e' una STIMA, distinta dalla misura.
"""
import math
from dataclasses import dataclass

JOULE_PER_KWH = 3_600_000.0


@dataclass(frozen=True)
class CarbonFactors:
    """Fattori dichiarati del report. Nessuno e' inventato: la fonte della
    intensita' di rete e' obbligatoria; il PUE di default e' 1.0 (host locale,
    nessun overhead da datacenter)."""
    grid_intensity_kg_per_kwh: float
    grid_source: str
    pue: float = 1.0
    pue_source: str = "host locale: nessun overhead datacenter"

    def __post_init__(self):
        g = self.grid_intensity_kg_per_kwh
        if g is None or not isinstance(g, (int, float)) or not math.isfinite(g) or g <= 0:
            raise ValueError("intensita' di rete obbligatoria, finita e > 0")
        if not self.grid_source or not str(self.grid_source).strip():
            raise ValueError("fonte dell'intensita' di rete obbligatoria")
        if not isinstance(self.pue, (int, float)) or not math.isfinite(self.pue) or self.pue <= 0:
            raise ValueError("PUE finito e > 0")


def joule_to_kwh(energy_j: float) -> float:
    """Converte J in kWh (1 kWh = 3.6e6 J). Il segno si conserva."""
    return energy_j / JOULE_PER_KWH


def estimate_emissions_kg(energy_kwh: float, *, grid_intensity_kg_per_kwh: float,
                          pue: float = 1.0) -> float:
    """Emissioni stimate: E_kWh * PUE * intensita' di rete (kg CO2eq/kWh)."""
    return energy_kwh * pue * grid_intensity_kg_per_kwh