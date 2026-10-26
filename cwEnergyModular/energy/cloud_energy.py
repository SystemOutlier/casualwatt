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
client. NOTE B4: llm_impacts usa solo output_token_count e request_latency ->
i token di input NON sono inclusi nella stima.

RETTIFICA 26-10-2026 (Punto #119, ecologits 0.11.1; sonda tracciata
`probe_ecologits_clamp_20261026.py`, output
`experiment_results/ecologits_clamp_console_20261026.txt`): la latenza
end-to-end che passiamo NON produce una "sovrastima d'attesa" sistematica --
EcoLogits la consuma soltanto attraverso il termine server, via
`generation_latency = min(request_latency, gpu_latency)`
(`impacts/llm.py:100-102`, unico punto d'uso `:574`): il termine e' un **clamp**,
non una deriva. Oltre l'incrocio la porzione di rete e di coda viene SCARTATA e
l'energia resta bit-identica.
CONSEGUENZA PER LA RIGA: sopra la soglia essa dichiara una latenza MISURATA che
NON ha influito sul numero, e la stima diventa **insensibile** alla lentezza del
provider -- il rischio reale e' la sottostima, non la sovrastima. Va corretto il
metodo, non il numero: la riga deve poter dire quale dei due termini vincola.

RETTIFICA DELLA RETTIFICA, stessa data: la soglia NON e' la regressione
`alpha*P_active + beta*BATCH_SIZE + gamma` (`:14-16`), che e' il ramo usato solo
quando `tps is None` (`:94-95`). `llm_impacts` inietta `tps` e `ttft` dalla
scheda del modello (`tracers/utils.py:121-122`) e TUTTI i 344 modelli del
registro hanno un `deployment`; il ramo di produzione e' quindi
`latency_per_token = 1/tps` (`:97`) e la soglia e'
`gpu_latency = n_out/tps + ttft` (`:99`). Verificato eseguendo, su
openai/gpt-4o-mini (tps 33,0, ttft 0,6): soglia 1,5697 s a 32 token con energia
identica da 1,57 s a 120 s (3,176229044667e-06 kWh); soglia 3,6303 s a 100 token
identica da 3,70 s a 120 s (8,929622014584e-06 kWh, +42,881% sul valore a
0,20 s); soglia 6,6606 s a 200 token identica da 10 s a 120 s
(1,739049402917e-05 kWh, +40,892%).

Il valore principale e' la MEDIA del range EcoLogits, con min/max nei campi
energy_min_j / energy_max_j -- e quel range e'
`parameter_pue_ignorance_range` (propagazione dei parametri registrati e delle
bande PUE/WUE del provider), non incertezza statistica del modello.
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
            # B4: llm_impacts (verificato su ecologits 0.11.1) accetta solo
            # output_token_count e request_latency -> i TOKEN DI INPUT NON
            # sono inclusi nella stima; il conteggio resta nel campo CSV
            # cloud_input_tokens a scopo dichiarativo.
            notes.append(
                f"token di input ({int(prompt_tokens)}) NON inclusi nella stima: "
                "llm_impacts usa solo output_token_count + request_latency"
            )
            # B4 + Rettifica #119 (26-10-2026): la latenza MISURATA arriva al
            # motore ma viene usata SOLO come min(request_latency, gpu_latency)
            # nel termine server (impacts/llm.py:100-102, :574). Quindi la porzione
            # di rete e di coda non e' una sovrastima sistematica: sopra
            # l'incrocio il motore usa la propria soglia interna e il tempo
            # extra viene scartato in silenzio. La soglia di produzione NON e' la
            # regressione alpha*P+beta*B+gamma, perche' llm_impacts inietta tps e
            # ttft dalla scheda del modello (tracers/utils.py:121-122; tutti i 344
            # modelli registrati hanno un deployment) -> gpu_latency = n_out/tps +
            # ttft (impacts/llm.py:97-99). Verificato eseguendo
            # probe_ecologits_clamp_20261026.py: identica all'ultima cifra da
            # 1,57 s a 120 s a 32 token, da 3,70 s a 120 s a 100 token, da 10 s a
            # 120 s a 200 token su openai/gpt-4o-mini. Il testo della nota e'
            # stato corretto perche' asseriva una deriva unidirezionale.
            notes.append(
                f"request_latency={float(duration_s):.3f}s MISURATA end-to-end "
                "(include rete e coda): EcoLogits la usa solo come "
                "min(request_latency, n_out/tps + ttft) nel termine server "
                "(tps/ttft della scheda del modello), quindi oltre la soglia "
                "il tempo di rete NON entra nella stima: l'energia resta un "
                "plateau -- clamp, non sovrastima; soglia e termine vincolante non "
                "registrati in riga -- campi cloud_latency_used_s e "
                "cloud_latency_binding, vedi spec C5)"
            )
            if kwh_lo is not None and kwh_hi is not None and kwh_hi > kwh_lo:
                notes.append(
                    "valore principale = MEDIA del range EcoLogits "
                    f"[{kwh_lo:.6g}, {kwh_hi:.6g}] kWh; min/max salvati in "
                    "cloud_energy_min_j / cloud_energy_max_j; "
                    "cloud_energy_band_semantics=parameter_pue_ignorance_range "
                    "(propagazione dei parametri registrati e delle bande PUE/WUE "
                    "del provider, NON deviazione standard ne' confidenza del "
                    "modello)"
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
