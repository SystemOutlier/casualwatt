# -*- coding: utf-8 -*-
"""
cloud_estimator.py — Facade di stima cloud richiesto dalla specifica.

Ri-esporta ``estimate_cloud_energy`` dal sottosistema ``energy/`` e aggiunge:
* ``get_cloud_models()``  : lettura modelli dai provider configurati (sez. 6);
* ``CloudEnergyEstimator``: wrapper stateless usato da benchmark_unified.
Nessuna formula propria: tutta la stima passa da EcoLogits (energy/cloud_energy).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import requests

try:
    from config import CLOUD_PROVIDERS
except Exception:  # pragma: no cover
    CLOUD_PROVIDERS = {}

# riusa il motore eco-logits del pacchetto energy (import relativo NON serve
# qui: questo modulo sta nella root, quindi import assoluto del subpackage)
from energy.cloud_energy import CloudEnergyResult, estimate_cloud_energy

__all__ = [
    "CloudEnergyResult",
    "CloudEnergyEstimator",
    "estimate_cloud_energy",
    "get_cloud_models",
]


def get_cloud_models(timeout_s: float = 10.0) -> List[Dict]:
    """Elenca i modelli dei provider abilitati (GET <models_endpoint>).

    Ritorna [{provider, model, label}]. Provider senza API key o offline
    vengono saltati con nota silenziosa (mai eccezioni verso la GUI).
    """
    out: List[Dict] = []
    for prov_id, cfg in (CLOUD_PROVIDERS or {}).items():
        api_key = os.getenv(cfg.get("api_key_env", ""), "") or cfg.get("api_key", "")
        if not api_key:
            continue
        try:
            r = requests.get(
                cfg["models_endpoint"],
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=timeout_s,
            )
            if r.status_code != 200:
                continue
            data = r.json()
            items = data.get("data") or data.get("models") or []
            for it in items:
                mid = it.get("id") or it.get("name")
                if not mid:
                    continue
                # google restituisce nomi tipo 'models/gemini-2.0-flash'
                clean = str(mid).split("/")[-1]
                out.append(
                    {
                        "provider": prov_id,
                        "model": clean,
                        "label": f"{prov_id} | {clean}",
                    }
                )
        except Exception:
            continue
    out.sort(key=lambda d: (d["provider"], d["model"]))
    return out


class CloudEnergyEstimator:
    """Wrapper con caching delle stime per (provider, model, tok_out, latenza)."""

    def __init__(self) -> None:
        self._cache: Dict[tuple, CloudEnergyResult] = {}

    def estimate(
        self,
        provider: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_s: float,
        electricity_mix_zone: Optional[str] = None,
    ) -> CloudEnergyResult:
        key = (provider, model_name, int(completion_tokens), round(float(duration_s), 2))
        if key in self._cache:
            return self._cache[key]
        res = estimate_cloud_energy(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_s=duration_s,
            provider=provider,
            electricity_mix_zone=electricity_mix_zone,
        )
        self._cache[key] = res
        return res
