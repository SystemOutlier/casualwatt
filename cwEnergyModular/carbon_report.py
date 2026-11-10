# -*- coding: utf-8 -*-
"""carbon_report — report carbonio di sola analisi sopra energia misurata.

Modulo di analisi (registro di surface_fit.py / geometry.py / control_gate.py):
non e' chiamato dal runner, non tocca lo schema P5 (CSV_COLUMNS resta 174),
non dipende da SESSION. Converte l'energia misurata in kWh e applica fattori
dichiarati con fonte; ogni emissione e' una STIMA, distinta dalla misura.
"""
import math
from dataclasses import dataclass, asdict
from typing import Iterable, Optional, Tuple

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


@dataclass
class CarbonRowResult:
    """Esito di una riga: energia misurata (firmata) e stima, o esclusione
    dichiarata. status e' 'ok' oppure 'excluded'; reason e' vuota se ok."""
    energy_j_measured: Optional[float]
    energy_kwh: Optional[float]
    emissions_kg_estimate: Optional[float]
    status: str
    reason: str


def _parse_energy(raw) -> Tuple[Optional[float], str]:
    """Estrae l'energia in J da un valore di riga. Ritorna (valore, '') se
    valida, (None, ragione) se assente/non numerica/non finita. Il segno si
    conserva."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "energia assente"
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None, "energia non numerica"
    if not math.isfinite(val):
        return None, "energia non finita"
    return val, ""


def report_carbon(rows: Iterable[dict], factors: CarbonFactors, *,
                  energy_column: str, input_provenance: dict) -> dict:
    """Report di sola analisi: legge righe gia' parsate, non misura. Somma le
    sole righe valide; le escluse sono conteggiate con la loro ragione."""
    results = []
    reasons: dict = {}
    sum_j = 0.0
    n_ok = 0
    n_excluded = 0
    for row in rows:
        val, reason = _parse_energy(row.get(energy_column))
        if val is None:
            n_excluded += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            results.append(CarbonRowResult(None, None, None, "excluded", reason))
            continue
        kwh = joule_to_kwh(val)
        em = estimate_emissions_kg(
            kwh, grid_intensity_kg_per_kwh=factors.grid_intensity_kg_per_kwh,
            pue=factors.pue)
        sum_j += val
        n_ok += 1
        results.append(CarbonRowResult(val, kwh, em, "ok", ""))
    total_kwh = joule_to_kwh(sum_j)
    total_em = estimate_emissions_kg(
        total_kwh, grid_intensity_kg_per_kwh=factors.grid_intensity_kg_per_kwh,
        pue=factors.pue)
    return {
        "label": "stima",
        "measured": {
            "energy_j_total": sum_j,
            "energy_kwh_total": total_kwh,
            "n_rows": n_ok + n_excluded,
            "n_ok": n_ok,
            "n_excluded": n_excluded,
            "excluded_reasons": reasons,
        },
        "factors": {
            "pue": factors.pue,
            "pue_source": factors.pue_source,
            "grid_intensity_kg_per_kwh": factors.grid_intensity_kg_per_kwh,
            "grid_source": factors.grid_source,
        },
        "estimate": {"emissions_kg": total_em},
        "provenance": {**input_provenance, "module": "carbon_report",
                       "formula": "E_J/3.6e6 * PUE * grid"},
        "rows": [asdict(r) for r in results],
    }