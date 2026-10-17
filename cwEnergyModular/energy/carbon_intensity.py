# -*- coding: utf-8 -*-
"""
energy/carbon_intensity.py — Intensita' di carbonio della rete elettrica.

Ordine di risoluzione (per riga CSV, con zona e fonte dichiarate):
1. Electricity Maps API se ELECTRICITY_MAPS_API_TOKEN presente;
2. fallback offline: tabella valori medi nazionali/continentali (fonte
   dichiarata "offline-default-table", anno 2024, gCO2eq/kWh Scope-2);
3. worst-caseWOR = 480 gCO2eq/kWh se tutto fallisce.

NB: l'intensita' cloud fornita da EcoLogits (gwp del risultato) viene usata
a monte in benchmark_unified per la componente cloud; qui si copre la
componente LOCALE (energia prelevata dalla presa di casa dell'utente).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

import requests

try:
    from config import ELECTRICITYMAPS_API_URL, ELECTRICITY_MAPS_API_TOKEN, ECO_CARBON_ZONE
except Exception:  # pragma: no cover
    ELECTRICITYMAPS_API_URL = "https://api.electricitymap.org/v3/carbon-intensity/latest"
    ELECTRICITY_MAPS_API_TOKEN = ""
    ECO_CARBON_ZONE = "IT"

# Valori medi annuali Scope-2 gCO2eq/kWh (fonti: Ember 2024 / IEU dati pubblici)
OFFLINE_TABLE = {
    "IT": 267.0, "FR": 55.0, "DE": 396.0, "ES": 191.0, "GB": 207.0,
    "US": 379.0, "CA": 120.0, "NO": 30.0, "SE": 41.0, "PL": 615.0,
    "NL": 311.0, "BE": 214.0, "CH": 88.0, "AT": 165.0, "PT": 172.0,
    "WOR": 480.0,
}

_CACHE: dict = {"zone": None, "value": None, "source": None, "ts": 0.0}
_CACHE_TTL_S = 3600.0


@dataclass
class CarbonIntensity:
    gco2eq_per_kwh: float
    zone: str
    source: str
    timestamp: float


def get_carbon_intensity(zone: Optional[str] = None) -> CarbonIntensity:
    """Ritorna intensita' corrente con fonte e timestamp; mai solleva eccezioni."""
    zone = (zone or ECO_CARBON_ZONE or "IT").upper()
    now = time.time()
    if _CACHE["zone"] == zone and _CACHE["value"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL_S:
        return CarbonIntensity(_CACHE["value"], zone, _CACHE["source"], _CACHE["ts"])

    value: Optional[float] = None
    source = ""

    # 1) Electricity Maps
    if ELECTRICITY_MAPS_API_TOKEN:
        try:
            headers = {"X-RapidAPI-Key": ELECTRICITY_MAPS_API_TOKEN} \
                if "rapidapi" in ELECTRICITYMAPS_API_URL else {"auth-token": ELECTRICITY_MAPS_API_TOKEN}
            r = requests.get(
                ELECTRICITYMAPS_API_URL,
                params={"distance": 100, "zone": zone},
                headers=headers,
                timeout=6,
            )
            if r.status_code == 200:
                data = r.json()
                v = data.get("carbonIntensity")
                if isinstance(v, (int, float)) and v > 0:
                    value = float(v)
                    source = "electricity-maps-api"
        except Exception:
            value = None

    # 2) tabella offline
    if value is None:
        value = OFFLINE_TABLE.get(zone)
        source = "offline-default-table-2024"

    # 3) worst case
    if value is None:
        value = OFFLINE_TABLE["WOR"]
        zone = "WOR"
        source = "worst-case-default"

    _CACHE.update(zone=zone, value=value, source=source, ts=now)
    return CarbonIntensity(round(value, 2), zone, source, now)
