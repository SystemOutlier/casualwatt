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
(usage GPU + PUE). La quota EMBODIED di EcoLogits NON entra in energy_j: e' un
impatto GWP separato, come dichiarato nelle note di ogni stima. Esclude rete e
client. NOTE B4: llm_impacts (0.11.3) usa solo output_token_count e
request_latency -> i token di input NON sono inclusi nella stima; la latenza
passata include la rete end-to-end (sovrastima d'attesa dichiarata); il valore
principale e' la MEDIA del range EcoLogits, con min/max nei campi
energy_min_j / energy_max_j.
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
    # B4: range EcoLogits (Value/RangeValue) salvati separatamente; il valore
    # principale resta la MEDIA del range, dichiarata come tale nelle note.
    energy_min_j: Optional[float] = None
    energy_max_j: Optional[float] = None
    notes: List[str] = field(default_factory=list)


def _range_of(node):
    """Ritorna (min, max, medio) da campi EcoLogits Value o RangeValue."""
    if node is None:
        return None, None, None
    val = getattr(node, "value", node)
    lo = getattr(val, "min", None)
    hi = getattr(val, "max", None)
    if lo is not None and hi is not None:
        try:
            lo_f, hi_f = float(lo), float(hi)
            return lo_f, hi_f, (lo_f + hi_f) / 2.0
        except Exception:
            return None, None, None
    try:
        f = float(val)
        return f, f, f
    except Exception:
        return None, None, None


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
        kwh_lo, kwh_hi, kwh = _range_of(getattr(res, "energy", None))
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
                "confine: inference server-side datacenter (usage+PUE), esclude "
                "rete e client; NOTA: la quota EMBODIED (fabbricazione hardware) "
                "NON fa parte dell'energia stimata in cloud_energy_j (e' un "
                "impatto GWP separato)"
            )
            # B4: llm_impacts (verificato su ecologits 0.11.3) accetta solo
            # output_token_count e request_latency -> i TOKEN DI INPUT NON
            # sono inclusi nella stima; il conteggio resta nel campo CSV
            # cloud_input_tokens a scopo dichiarativo.
            notes.append(
                f"token di input ({int(prompt_tokens)}) NON inclusi nella stima: "
                "llm_impacts usa solo output_token_count + request_latency"
            )
            # B4: la latenza MISURATA passata a EcoLogits include il tempo di
            # rete client->server: la stima server-side ne risulta lievemente
            # sovrastimata per la porzione d'attesa (dichiarato, non corretto).
            notes.append(
                f"request_latency={float(duration_s):.3f}s MISURATA end-to-end: "
                "include la latenza di rete, non solo il tempo server-side"
            )
            if kwh_lo is not None and kwh_hi is not None and kwh_hi > kwh_lo:
                notes.append(
                    "valore principale = MEDIA del range EcoLogits "
                    f"[{kwh_lo:.6g}, {kwh_hi:.6g}] kWh; min/max salvati in "
                    "cloud_energy_min_j / cloud_energy_max_j"
                )
            energy_j = round(kwh * 3_600_000.0, 6)
            e_min_j = round(kwh_lo * 3_600_000.0, 6) if kwh_lo is not None else None
            e_max_j = round(kwh_hi * 3_600_000.0, 6) if kwh_hi is not None else None
            carbon_g = round(gwp_kg * 1000.0, 6) if gwp_kg is not None else None
            zone = electricity_mix_zone or "WOR/provider-default"
            return CloudEnergyResult(
                energy_j=energy_j,
                energy_min_j=e_min_j,
                energy_max_j=e_max_j,
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
