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
    # P5 / spec C5 §4 (26-10-2026): come il numero e' stato prodotto, non solo
    # quanto vale. Senza questi campi la riga porta una latenza misurata che
    # potrebbe non aver influito sul risultato, e un PUE che nessuno ha scritto.
    pue_applied: Optional[float] = None
    pue_source: str = ""          # "provider_catalog_ecologits" | ""
    latency_used_s: Optional[float] = None
    latency_threshold_s: Optional[float] = None
    latency_binding: str = ""     # "request_latency" | "gpu_latency" | ""
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


def _provider_pue(eco_provider: str):
    """PUE che il motore applica, e come e' stato riassunto in un numero solo.

    EcoLogits lo prende dal catalogo del provider (``PROVIDER_CONFIG_MAP``):
    valore puntuale per OpenAI/Google/Mistral/Cohere, banda per Anthropic e
    Hugging Face. Il campo scalare della riga porta il punto medio; la banda non
    si perde, perche' e' la stessa che separa ``energy_min_j`` da
    ``energy_max_j``. Ritorna (valore, descrizione) o (None, "") se non
    determinabile -- meglio un campo vuoto che un PUE inventato.
    """
    try:
        from ecologits.tracers.utils import PROVIDER_CONFIG_MAP

        pue = PROVIDER_CONFIG_MAP[eco_provider].datacenter_pue
    except Exception:
        return None, ""
    lo = getattr(pue, "min", None)
    hi = getattr(pue, "max", None)
    if lo is not None and hi is not None:
        try:
            return (float(lo) + float(hi)) / 2.0, (
                f"punto medio della banda [{float(lo)}, {float(hi)}]")
        except Exception:
            return None, ""
    try:
        return float(pue), "valore puntuale"
    except Exception:
        return None, ""


def _latency_diagnostics(eco_provider: str, model_name: str,
                         output_tokens: float, request_latency: float):
    """Riproduce il clamp del motore sulla latenza: ``min(request, gpu_latency)``.

    ``gpu_latency`` e' la soglia del termine server. Quando la scheda del modello
    ha ``tps`` la soglia e' ``n_out/tps + ttft``; altrimenti e' la regressione
    del motore, e in quel caso la si chiede al motore stesso con una latenza
    richiesta infinita -- cosi' i coefficienti restano quelli del pacchetto
    installato e non una copia nostra che invecchia. Ritorna
    ``(usata, soglia, termine)`` con termine ``"request_latency"`` (nessun
    troncamento) o ``"gpu_latency"`` (tempo di rete e di coda scartati), e
    ``(None, None, "")`` se non e' determinabile.
    """
    try:
        from ecologits.tracers.utils import models
        from ecologits.impacts import llm as _eco_llm

        md = models.find_model(eco_provider, model_name)
        if md is None:
            return None, None, ""
        dep = getattr(md, "deployment", None)
        tps = getattr(dep, "tps", None) if dep else None
        ttft = getattr(dep, "ttft", None) if dep else None
        if tps is not None:
            threshold = float(output_tokens) / float(tps) + (float(ttft) if ttft else 0.0)
        else:
            params = getattr(getattr(md, "architecture", None), "parameters", None)
            active = getattr(params, "active", params)
            threshold = float(_eco_llm.generation_latency(
                model_active_parameter_count=float(active),
                output_token_count=float(output_tokens),
                batch_size=_eco_llm.BATCH_SIZE,
                latency_alpha=_eco_llm.LATENCY_ALPHA,
                latency_beta=_eco_llm.LATENCY_BETA,
                latency_gamma=_eco_llm.LATENCY_GAMMA,
                request_latency=1e9, tps=None, ttft=ttft))
        used = min(float(request_latency), threshold)
        binding = ("request_latency" if float(request_latency) < threshold
                   else "gpu_latency")
        return used, threshold, binding
    except Exception:
        return None, None, ""


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
    # Pavimenti applicati al motore: il token di output minimo (1) e la latenza
    # minima (0,05 s). Stanno in due variabili perche' il valore realmente usato
    # deve comparire anche nella diagnostica della latenza, non solo nella call.
    raw_n_out = int(completion_tokens)
    raw_lat_s = float(duration_s)
    n_out = max(raw_n_out, 1)
    lat_req = max(raw_lat_s, 0.05)
    # Un pavimento e' una scelta di questo codice, non una proprieta' del motore:
    # quando scatta, il numero e' prodotto da un ingresso diverso da quello
    # misurato. Senza la nota la riga lascerebbe credere che 0 token o una
    # latenza di 3 ms siano entrati nel calcolo cosi' come sono stati osservati.
    floor_notes: List[str] = []
    if raw_n_out < 1:
        floor_notes.append(
            "floor applied: output_token_count clamped to 1 "
            f"(conteggio misurato {raw_n_out}); il pavimento e' di questo "
            "codice, non un valore del motore"
        )
    if raw_lat_s < 0.05:
        floor_notes.append(
            "floor applied: request_latency clamped to 0.05 s "
            f"(misurati {raw_lat_s:.3f} s); la stima usa 0,05 s benche' la "
            "richiesta sia stata piu' rapida"
        )
    last_errors: List[str] = []
    for prov, mdl in _candidate_models(eco_provider, model_name):
        if not mdl:
            continue
        try:
            res = llm_impacts(
                provider=prov,
                model_name=mdl,
                output_token_count=n_out,
                request_latency=lat_req,
                electricity_mix_zone=electricity_mix_zone,
            )
        except Exception as exc:  # provider sconosciuto in eco, ecc.
            last_errors.append(f"{prov}/{mdl}: {type(exc).__name__}")
            continue
        kwh_lo, kwh_hi, kwh = _range_of(getattr(res, "energy", None))
        if kwh and kwh > 0:
            gwp_kg = _value_of(getattr(res, "gwp", None))
            notes = list(floor_notes)
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
            # Rettifica #119 (26-10-2026) e seconda rettifica: la latenza MISURATA
            # arriva al motore ma viene usata solo come min(request_latency,
            # gpu_latency) nel termine server (impacts/llm.py:100-102, :574).
            # Sopra l'incrocio il tempo di rete e di coda viene scartato: e' un
            # clamp, non una sovrastima. La soglia e' n_out/tps + ttft quando la
            # scheda ha tps (157 schede su 344: sonda
            # probe_ecologits_gpu_steps_moe_20261026.py, sezione D), altrimenti la
            # regressione :94-95. La stesura precedente citava n_out/tps + ttft
            # come forma universale: era falsa per la maggioranza delle schede.
            pue, pue_kind = _provider_pue(prov)
            lat_used, lat_thr, binding = _latency_diagnostics(
                prov, mdl, n_out, lat_req)
            notes.append(
                f"request_latency={lat_req:.3f}s MISURATA end-to-end (include rete e "
                "coda): EcoLogits la usa solo come min(request_latency, soglia del "
                "termine server) -- clamp, non sovrastima; oltre la soglia il tempo "
                "di rete non entra e l'energia resta un plateau"
            )
            if lat_thr is not None:
                notes.append(
                    f"latenza entrata nel calcolo: {lat_used:.3f}s su una soglia di "
                    f"{lat_thr:.3f}s (n_out/tps + ttft se la scheda ha tps, "
                    "altrimenti la regressione del motore); termine vincolante: "
                    + ("latenza misurata, nessun troncamento"
                       if binding == "request_latency"
                       else "soglia del server -- latenza misurata troncata, rete e "
                            "coda NON entrano nella stima")
                )
            else:
                notes.append(
                    "soglia del termine server non determinabile dalla scheda "
                    "(tps assente e parametri non scalari): termine vincolante non "
                    "registrato per questa riga"
                )
            if pue is not None:
                notes.append(
                    f"PUE applicato: {pue:.3f} ({pue_kind}), catalogo provider "
                    "EcoLogits; la banda del provider, dove esiste, resta visibile "
                    "in cloud_energy_min_j / cloud_energy_max_j"
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
                pue_applied=pue,
                pue_source=("provider_catalog_ecologits" if pue is not None else ""),
                latency_used_s=(
                    round(lat_used, 6) if lat_used is not None else None),
                latency_threshold_s=(
                    round(lat_thr, 6) if lat_thr is not None else None),
                latency_binding=binding,
                notes=notes,
            )
        errs = getattr(res, "errors", None) or []
        last_errors.extend(f"{prov}/{mdl}: {getattr(e, 'message', e)}" for e in errs)

    return CloudEnergyResult(
        energy_j=None,
        method="unavailable (model not registered in ecologits)",
        # I pavimenti restano dichiarati anche quando la stima non riesce: sono
        # stati applicati agli argomenti del tentativo, e il lettore deve poterli
        # vedere senza dedurli dal fatto che il numero manca.
        notes=floor_notes + (last_errors[:4] or ["nessuna stima possibile"]),
    )
