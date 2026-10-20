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


# ---------------------------------------------------------------------------
# Fetch dinamico dei modelli cloud (nessuna lista hardcodata): gli ID vengono
# sempre letti dagli endpoint ufficiali dei provider, cosi' la GUI non puo'
# proporre modelli obsoleti (errori 400/404).
#
# Endpoint di riferimento:
#   Groq          GET https://api.groq.com/openai/v1/models      (Bearer)
#   OpenRouter    GET https://openrouter.ai/api/v1/models        (Bearer;
#                 gratuito se id termina con ':free' o costi == 0)
#   Google Gemini GET https://generativelanguage.googleapis.com/v1beta/
#                      models?key=<KEY>  (solo modelli con 'generateContent')
# ---------------------------------------------------------------------------


def _is_free_model(it: Dict, mid: str) -> bool:
    """Rileva i modelli gratuiti (OpenRouter e simili).

    Criteri: suffisso ':free' nell'id, oppure metadati 'pricing' con
    prompt/completion azzerati ('0' o 0.0). Nessun criterio inventato.
    """
    if str(mid).endswith(":free"):
        return True
    pricing = it.get("pricing") or {}
    try:
        vals = [pricing.get("prompt"), pricing.get("completion")]
        if all(v is not None and float(v) == 0.0 for v in vals):
            return True
    except (TypeError, ValueError):
        pass
    return False


def _fetch_provider_models(prov_id: str, cfg: Dict, api_key: str,
                           timeout_s: float) -> List[Dict]:
    """Fetch singolo provider con adattamento per provider. Non solleva."""
    out: List[Dict] = []
    headers = {"Authorization": f"Bearer {api_key}"}

    if prov_id == "google":
        # v1beta nativo: filtra solo supportedGenerationMethods ~ generateContent
        url = ("https://generativelanguage.googleapis.com/v1beta/models"
               f"?key={api_key}")
        r = requests.get(url, timeout=timeout_s)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        for it in r.json().get("models", []):
            methods = it.get("supportedGenerationMethods") or []
            if not any("generateContent" in str(m) for m in methods):
                continue
            mid = str(it.get("name", "")).replace("models/", "")
            if not mid:
                continue
            free = bool(it.get("flags")) and "FREE" in str(it.get("flags")).upper()
            out.append({"provider": prov_id, "model": mid,
                        "free": free, "label": f"{prov_id} | {mid}"})
        return out

    if cfg.get("style") == "anthropic_native" or prov_id == "anthropic":
        # Anthropic Messages API nativa: x-api-key + anthropic-version.
        # GET /v1/models -> {"data": [{"id","display_name",...}]}
        r = requests.get(
            cfg.get("models_endpoint",
                    "https://api.anthropic.com/v1/models"),
            headers={"x-api-key": api_key,
                     "anthropic-version": "2023-06-01"},
            timeout=timeout_s)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        data = r.json()
        items = data.get("data") or data.get("models") or []
        for it in items:
            mid = it.get("id") or it.get("name")
            if not mid:
                continue
            mid = str(mid)
            # Anthropic non espone tier gratuiti nel /models: free=False
            label = f"{prov_id} | {mid}"
            out.append({"provider": prov_id, "model": mid,
                        "free": False, "label": label})
        return out

    # percorso OpenAI-compatible (groq, openrouter, openai, huggingface,
    # eventuali aggiunti)
    r = requests.get(cfg["models_endpoint"], headers=headers, timeout=timeout_s)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}")
    data = r.json()
    items = data.get("data") or data.get("models") or []
    for it in items:
        mid = it.get("id") or it.get("name")
        if not mid:
            continue
        mid = str(mid)
        free = _is_free_model(it, mid)
        # ID inviato al provider: per OpenRouter/Groq serve l'ID COMPLETO
        # ('meta-llama/llama-3.2-3b-instruct:free'); lo stripping del prefisso
        # 'models/' vale solo per Google (gestita sopra). Mostriamo l'ID intero
        # e tagghiamo [Gratuito] a parte -> niente 404 su modelli annidati.
        label = f"{prov_id} | {mid}" + (" [Gratuito]" if free else "")
        out.append({"provider": prov_id, "model": mid,
                    "free": free, "label": label})
    return out


def get_cloud_models(timeout_s: float = 15.0) -> List[Dict]:
    """Elenca i modelli disponibili dai provider configurati (fetch live).

    Ritorna [{provider, model, label, free}] ordinati. Provider senza API
    key o irraggiungibili vengono saltati (nota nel campo 'errors').
    Mai liste statiche: gli ID obsoleti spariscono quando il provider li
    ritira, evitando errori 400/404 a runtime.
    """
    out: List[Dict] = []
    for prov_id, cfg in (CLOUD_PROVIDERS or {}).items():
        api_key = os.getenv(cfg.get("api_key_env", ""), "") or cfg.get("api_key", "")
        if not api_key:
            continue
        try:
            out.extend(_fetch_provider_models(prov_id, cfg, api_key, timeout_s))
        except Exception:
            continue  # provider offline / chiave invalida: skip silenzioso
    # etichetta '[Gratuito]' anche per i provider che non la espongono
    for d in out:
        if d.get("free") and "[Gratuito]" not in d["label"]:
            d["label"] += " [Gratuito]"
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
