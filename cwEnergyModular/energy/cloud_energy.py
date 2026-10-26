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

RETTIFICA 26-10-2026 (proxy irraggiungibile, verificata eseguendo su ecologits
0.11.1). La catena dichiarata C1 -> C2 -> C3 (proxy) -> "unavailable" non
arrivava mai a C3: tutte le regole di proxy puntavano al provider "openrouter",
che nel registro non esiste -- i provider di EcoLogits 0.11.1 sono ``anthropic,
cohere, google_genai, huggingface_hub, mistralai, openai``. Ogni richiesta Groq o
OpenRouter usciva quindi "unavailable" con il messaggio del provider
sconosciuto, e la nota "proxy dichiarato" non veniva mai scritta. Il proxy vive
ora nel registro Hugging Face, con l'id esatto della scheda: il motore usa la
scheda di quel modello (acceleratore di riferimento), non l'hardware del
provider, e la riga lo dichiara.
Nello stesso punto si chiude la seconda falla: la mappa CasualWatt -> EcoLogits
("google" -> "google_genai", "huggingface" -> "huggingface_hub") era applicata
al solo badge della GUI, non alla stima, per cui una richiesta Google valida
usciva "unavailable" mentre la GUI mostrava il modello come registrato. La mappa
ora vive in un solo posto (``ECOLOGITS_PROVIDER_MAP``) ed e' applicata
all'ingresso di ``estimate_cloud_energy``, prima di interrogare il registro.

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

SECONDA RETTIFICA, 26-10-2026 (sonda tracciata
`probe_ecologits_gpu_steps_moe_20261026.py`, sezioni D e F): la frase "TUTTI i 344
modelli del registro hanno un `deployment`" e' vera, ma non e' il fatto che serviva.
Il `deployment` esiste su 344 schede; il valore `tps` dentro di esso e' non nullo su
**157**. Su 187 schede -- fra cui huggingface_hub/meta-llama/Meta-Llama-3.1-70B-
Instruct, che e' il modello preso come esempio in questo modulo -- `tps` e' nullo, e
il ramo di produzione torna la regressione `:94-95` con soglia 17,4612 s a 200 token
(anch'essa rigenerata dalla sonda). L'errore metodologico che la prima stesura
denunciava -- "la firma dell'API non e' il percorso interno" -- si e' ripresentato
identico nella seconda: scambiare la PRESENZA di una chiave per la PRESENZA del suo
valore. Vanno contati i valori, non i campi.

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

# Mappatura CasualWatt -> provider EcoLogits. Vive qui, non nella facade, perche'
# la usano due percorsi -- il badge della GUI e la stima -- e finche' erano due
# copie divergevano: "google" risultava registrato nella GUI e "unavailable"
# nella riga. Un solo posto, una sola traduzione.
ECOLOGITS_PROVIDER_MAP = {
    "google": "google_genai",
    "openai": "openai",
    "anthropic": "anthropic",
    "huggingface": "huggingface_hub",
    # groq e openrouter non hanno modelli registrati in EcoLogits 0.11.x: si
    # raggiungono solo con un proxy dichiarato (vedi _MODEL_PROXY_RULES).
}

# Proxy dichiarati: sottostringa del nome richiesto -> (provider_ecologits, modello).
# Il provider NON e' "openrouter": quello non esiste nel registro, e finora ha
# reso il ramo proxy irraggiungibile (rettifica 26-10-2026, verificata eseguendo).
# Gli id sono quelli esatti del registro Hugging Face; il motore ne usa la scheda
# hardware, che e' un acceleratore di riferimento e non l'hardware del provider --
# la riga lo dichiara come equivalenza di classe.
_MODEL_PROXY_RULES = [
    ("llama-3.1-8b-instant", ("huggingface_hub", "meta-llama/Meta-Llama-3.1-8B-Instruct")),
    # 3.3-70B non e' nel registro: il piu' vicino per classe di parametri e'
    # 3.1-70B. Non e' lo stesso modello, e la nota lo dice.
    ("llama-3.3-70b-versatile", ("huggingface_hub", "meta-llama/Meta-Llama-3.1-70B-Instruct")),
    ("gemma2-9b-it", ("huggingface_hub", "google/gemma-2-9b-it")),
    ("mixtral-8x7b", ("huggingface_hub", "mistralai/Mixtral-8x7B-Instruct-v0.1")),
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
    """Coppie (provider EcoLogits, modello) da provare, senza ripetizioni.

    La prima e' la richiesta tradotta; poi l'eventuale regola di proxy; poi il
    fallback di famiglia. Il dedup non e' cosmetico: senza, la stessa coppia
    fallita compariva due volte nelle note della riga.
    """
    m = (model_name or "").lower()
    seen = set()

    def _unique(pair):
        if not pair[1] or pair in seen:
            return None
        seen.add(pair)
        return pair

    first = _unique((provider, model_name))
    if first:
        yield first
    for key, repl in _MODEL_PROXY_RULES:
        if key in m:
            pair = _unique(repl)
            if pair:
                yield pair
            break
    # fallback generico per famiglia. Anche qui il provider e' huggingface_hub
    # (openrouter non esiste nel registro) e la taglia conta: mandare un 70B su
    # una scheda da 8B sarebbe un errore di classe di un ordine di grandezza,
    # non un'approssimazione.
    fam = None
    if "llama" in m:
        if "405b" in m:
            fam = ("huggingface_hub", "meta-llama/Meta-Llama-3.1-405B-Instruct")
        elif any(s in m for s in ("70b", "72b")):
            fam = ("huggingface_hub", "meta-llama/Meta-Llama-3.1-70B-Instruct")
        else:
            fam = ("huggingface_hub", "meta-llama/Meta-Llama-3.1-8B-Instruct")
    elif "gemma" in m:
        fam = ("huggingface_hub", "google/gemma-2-9b-it")
    elif "mixtral" in m:
        fam = ("huggingface_hub",
               "mistralai/Mixtral-8x22B-Instruct-v0.1" if "22b" in m
               else "mistralai/Mixtral-8x7B-Instruct-v0.1")
    elif "mistral" in m:
        fam = ("huggingface_hub", "mistralai/Mistral-7B-Instruct-v0.1")
    if fam:
        pair = _unique(fam)
        if pair:
            yield pair


def estimate_cloud_energy(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_s: float,
    provider: str = "groq",
    electricity_mix_zone: Optional[str] = None,
) -> CloudEnergyResult:
    """Stima EcoLogits [J] per una chiamata cloud. Non produce mai valori finti.

    Il provider in ingresso e' l'id CasualWatt ("google", "huggingface", ...):
    viene tradotto in quello di EcoLogits qui, all'ingresso, perche' il registro
    conosce solo i propri nomi. La traduzione e' la stessa che la GUI usa per il
    badge (``ECOLOGITS_PROVIDER_MAP``), cosi' "registrato" e "stimabile" non
    possono piu' divergere.
    """
    try:
        from ecologits.tracers.utils import llm_impacts
        import ecologits
    except Exception as exc:  # noqa: BLE001
        return CloudEnergyResult(
            energy_j=None,
            method="unavailable (ecologits not installed)",
            notes=[f"import ecologits fallito: {type(exc).__name__}"],
        )

    eco_provider = ECOLOGITS_PROVIDER_MAP.get((provider or "").strip().lower(),
                                              provider)
    last_errors: List[str] = []
    for prov, mdl in _candidate_models(eco_provider, model_name):
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
            if (prov, mdl) != (eco_provider, model_name):
                notes.append(
                    f"proxy dichiarato: '{model_name}' non e' registrato in "
                    f"EcoLogits (provider {eco_provider}); usato '{mdl}' di {prov} "
                    "come equivalente di classe (stessa fascia di parametri, NON "
                    "lo stesso modello) con la latenza misurata reale della "
                    "richiesta"
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
            # extra viene scartato in silenzio. La soglia di produzione NON e' in
            # generale la regressione alpha*P+beta*B+gamma, perche' llm_impacts inietta
            # tps e ttft dalla scheda del modello (tracers/utils.py:121-122) ->
            # gpu_latency = n_out/tps + ttft (impacts/llm.py:97-99). ATTENZIONE,
            # seconda rettifica 26-10-2026 (probe_ecologits_gpu_steps_moe_20261026.py,
            # sezione D): il deployment esiste su tutti i 344 modelli ma `tps` e' non
            # nullo solo su 157, quindi su 187 schede (fra cui il 70B) il ramo vivo e'
            # la regressione :94-95. La nota pubblicata qui sotto cita la forma
            # n_out/tps + ttft: e' la forma del ramo usato negli esperimenti condotti
            # su gpt-4o-mini, non una proprieta' di tutte le schede.
            # Verificato eseguendo
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
