# -*- coding: utf-8 -*-
"""
energy/cloud_energy.py — Stima energia inferenza cloud via EcoLogits.

Strategia (sezione 9 della specifica):
1. usa il motore di stima nativo di ``ecologits``
   (``ecologits.tracers.utils.llm_impacts``) quando il modello e' registrato;
2. se il modello del provider non e' nel registro EcoLogits, ripiega su un
   proxy di pari-classe dichiarato (es. llama-3.1-8b-instant ->
   meta-llama/llama-3.1-8b-instruct su OpenRouter) mantenendo la latenza
   MISURATA reale della richiesta;
3. se anche il proxy fallisce, ritorna ``energy_j=None`` con metodo
   esplicitamente "unavailable": nessuna formula inventata fuori EcoLogits.

L'energia risultante (kWh -> J) ha confine: server-side datacenter
(usage GPU + PUE + embodied), esclude rete e client.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import List, Optional

warnings.filterwarnings("ignore", category=DeprecationWarning)

# Proxy dichiarati: sottostringa nome richiesto -> (provider_ecologits, modello)
_MODEL_PROXY_RULES = [
    ("llama-3.1-8b-instant", ("openrouter", "meta-llama/llama-3.1-8b-instruct")),
    ("llama-3.3-70b-versatile", ("openrouter", "meta-llama/llama-3.3-70b-instruct")),
    ("gemma2-9b-it", ("openrouter", "google/gemma-2-9b-it")),
    ("mixtral-8x7b", ("openrouter", "mistralai/mixtral-8x7b-instruct-v0.1")),
]


@dataclass
class CloudEnergyResult:
    energy_j: Optional[float] = None
    method: str = "ecologits"
    hw_profile: str = ""
    carbon_gco2eq: Optional[float] = None
    country_code: str = ""
    notes: List[str] = field(default_factory=list)


def _value_of(node) -> Optional[float]:
    """Estrae un float da campi EcoLogits che possono essere Value o RangeValue."""
    if node is None:
        return None
    val = getattr(node, "value", node)
    lo = getattr(val, "min", None)
    hi = getattr(val, "max", None)
    if lo is not None and hi is not None:
        try:
            return (float(lo) + float(hi)) / 2.0
        except Exception:
            return None
    try:
        return float(val)
    except Exception:
        return None


def _candidate_models(provider: str, model_name: str):
    m = (model_name or "").lower()
    yield provider, model_name
    for key, repl in _MODEL_PROXY_RULES:
        if key in m:
            yield repl
            break
    # fallback generico per famiglia
    if "llama" in m:
        yield ("openrouter", "meta-llama/llama-3.1-8b-instruct")
    elif "gemma" in m:
        yield ("openrouter", "google/gemma-2-9b-it")
    elif "mistral" in m or "mixtral" in m:
        yield ("openrouter", "mistralai/mistral-7b-instruct-v0.1")


def estimate_cloud_energy(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_s: float,
    provider: str = "groq",
    electricity_mix_zone: Optional[str] = None,
) -> CloudEnergyResult:
    """Stima EcoLogits [J] per una chiamata cloud. Non produce mai valori finti."""
    try:
        from ecologits.tracers.utils import llm_impacts
        import ecologits
    except Exception as exc:  # noqa: BLE001
        return CloudEnergyResult(
            energy_j=None,
            method="unavailable (ecologits not installed)",
            notes=[f"import ecologits fallito: {type(exc).__name__}"],
        )

    last_errors: List[str] = []
    for prov, mdl in _candidate_models(provider, model_name):
        if not mdl:
            continue
        try:
            res = llm_impacts(
                provider=prov,
                model_name=mdl,
                output_token_count=max(int(completion_tokens), 1),
                request_latency=max(float(duration_s), 0.05),
                electricity_mix_zone=electricity_mix_zone,
            )
        except Exception as exc:  # provider sconosciuto in eco, ecc.
            last_errors.append(f"{prov}/{mdl}: {type(exc).__name__}")
            continue
        kwh = _value_of(getattr(res, "energy", None)) if res is not None else None
        if kwh and kwh > 0:
            gwp_kg = _value_of(getattr(res, "gwp", None))
            notes = []
            if (prov, mdl) != (provider, model_name):
                notes.append(
                    f"proxy dichiarato: '{model_name}' non registrato in EcoLogits; "
                    f"usato modello di pari classe '{mdl}' ({prov}) con latenza "
                    "misurata reale"
                )
            notes.append(
                "confine: inference server-side datacenter (usage+PUE+embodied), "
                "esclude rete e client"
            )
            energy_j = round(kwh * 3_600_000.0, 6)
            carbon_g = round(gwp_kg * 1000.0, 6) if gwp_kg is not None else None
            zone = electricity_mix_zone or "WOR/provider-default"
            return CloudEnergyResult(
                energy_j=energy_j,
                method=(
                    f"ecologits llm_impacts v{getattr(ecologits, '__version__', 'unknown')}"
                ),
                hw_profile=f"{prov}/{mdl}",
                carbon_gco2eq=carbon_g,
                country_code=zone,
                notes=notes,
            )
        errs = getattr(res, "errors", None) or []
        last_errors.extend(f"{prov}/{mdl}: {getattr(e, 'message', e)}" for e in errs)

    return CloudEnergyResult(
        energy_j=None,
        method="unavailable (model not registered in ecologits)",
        notes=last_errors[:4] or ["nessuna stima possibile"],
    )
