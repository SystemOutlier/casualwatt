# -*- coding: utf-8 -*-
"""
cloud_estimator.py — Facade di stima cloud richiesto dalla specifica.

Ri-esporta ``estimate_cloud_energy`` dal sottosistema ``energy/`` e aggiunge:
* ``get_cloud_models()``  : lettura modelli dai provider configurati (sez. 6);
* ``CloudEnergyEstimator``: wrapper con cache delle stime, una istanza per run.
Nessuna formula propria: tutta la stima passa da EcoLogits (energy/cloud_energy),
compresa la traduzione CasualWatt -> EcoLogits del nome del provider, che sta
la' perche' il badge e la stima devono usare la stessa mappa.
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
from energy.cloud_energy import (  # noqa: F401
    ECOLOGITS_PROVIDER_MAP,
    CloudEnergyResult,
    estimate_cloud_energy,
)

# Mappatura provider CasualWatt -> provider EcoLogits. Un solo esemplare, in
# energy/cloud_energy.py: la usano il badge della GUI e la stima, e finche'
# erano due copie il badge diceva "registrato" mentre la riga diceva
# "unavailable" (google e huggingface, verificato 26-10-2026).
_ECLOGITS_PROVIDER_MAP = ECOLOGITS_PROVIDER_MAP


def _check_ecologits_registration(provider_id: str, model_name: str) -> bool:
    """Verifica se (provider, model) e' nel registro EcoLogits.

    Ritorna True se il modello e' registrato e puo' essere stimato nativamente;
    False altrimenti (stima analitica di fallback o energia=None).
    """
    eco_provider = _ECLOGITS_PROVIDER_MAP.get(provider_id)
    if not eco_provider:
        return False
    try:
        from ecologits.tracers.utils import models

        return models.find_model(eco_provider, model_name) is not None
    except Exception:
        return False


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

    Ritorna [{provider, model, label, free, has_ecologits}] ordinati. Provider
    senza API key o irraggiungibili vengono saltati (nota nel campo 'errors').
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
        # verifica registrazione EcoLogits (per badge visivo in GUI)
        d["has_ecologits"] = _check_ecologits_registration(d["provider"], d["model"])
    out.sort(key=lambda d: (d["provider"], d["model"]))
    return out


class CloudEnergyEstimator:
    """Wrapper con caching delle stime per (provider, model, tok_out, latenza, zona).

    La cache vive quanto l'istanza: finche' ``query_cloud`` ne creava una nuova a
    ogni richiesta, ogni chiamata entrava con la cache vuota e il dizionario non
    veniva mai riletto. Un colpo si ha solo quando provider, modello, token di
    output, latenza arrotondata al centesimo e zona di mix coincidono: con
    latenze misurate e' raro, e la cache non e' un risparmio di calcolo
    garantito, ma un'istanza per run evita di ricostruire lo stesso risultato
    quando la stessa richiesta si ripete.

    La chiave NON contiene ``prompt_tokens``: ``llm_impacts`` accetta solo
    ``output_token_count`` e ``request_latency``, quindi i token di input non
    entrano nella stima (restano nel CSV come dichiarazione). La zona invece
    entra, perche' cambia il mix elettrico e con esso il carbonio: senza di essa
    un colpo fra due zone diverse restituirebbe il carbonio della prima.
    """

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
        key = (provider, model_name, int(completion_tokens),
               round(float(duration_s), 2), electricity_mix_zone)
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
