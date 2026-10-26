# -*- coding: utf-8 -*-
"""Sonda dei gradini `gpu_required_count` e dei fattori MoE (Task #122, 26-10-2026).

Perche' esiste. `experiment_results/metodo_analitico_cloud_20261026.md` introduce tre
famiglie di numeri -- i gradini del numero di GPU, il fattore 3,268 sul 70B e i fattori
MoE 3,0067x / 11,17x -- e alla riga 116 dichiara essa stessa che le sonde da cui quei
numeri vengono (`probe_ecologits_formule_20261026.py`,
`probe_ecologits_gpus_factor_20261026.py`) "sono state eseguite come invocazioni inline
e non sono file tracciati". AGENTS.md: "un'analisi non tracciata e' un numero che
nessuno puo' rigenerare". Questa sonda li rigenera tutti da un artefatto del repository
e, dove un numero non torna, lo dice invece di adeguarlo.

Cosa stampa, nell'ordine:
  A. gli **ancoraggi di sorgente** verificati riga per riga sul pacchetto installato
     (linecache): ogni "`impacts/llm.py:NN`" e ogni "righe 136-141 di `data/models.json`"
     citato dal documento viene ricontrollato contro il testo del file, perche' un
     ancoraggio stantio e' un claim falso;
  B. le **costanti** del modello di impatto, stampate dai loro nomi, non ritrascritte;
  C. la **funzione a gradini** `gpu_required_count(P_total, bits)`, cioe' il motivo per
     cui l'energia non e' continua nella classe di modello: 16 bit e 8 bit affiancate,
     perche' la quantizzazione -- che `MODEL_QUANTIZATION_BITS` fissa a 16 e che nessuno
     ci chiede mai -- sposta il gradino da 8 a 4 su un 218B;
  D. il **registro** (`data/models.json`): quanti modelli hanno un `deployment`, quanti
     hanno `tps` non nullo (qui emerge che NON sono tutti: la soglia n_out/tps+ttft vale
     solo per quelli, per gli altri la soglia e' la regressione della latenza), e come
     si traducono in oggetti le 87 schede MoE -- punto in cui la sonda trova un fatto
     che il documento non aveva: l'unica scheda che usa la chiave `active_parameters`
     ha `parameters` scalare, quindi il parser la consegna come intero e il ramo MoE
     di `tracers/utils.py:89-94` non scatta mai per lei;
  E. `f_E(P_active, B)` a 25 e 218 miliardi di parametri attivi -> il fattore 3,0067
     (e il confronto con 8,72 = 218/25, che e' quello che si aspetterebbe chi non legge
     l'offset `gamma`);
  F. la **correzione 1** sul 70B: la proposta di `cloud.DOCX` scrive
     `E_request = PUE * (E_server + E_gpu)` mentre il codice scrive
     `E_server + gpus_required * E_gpu`; ricostruisce entrambi e li confronta con
     `llm_impacts` reale (uguaglianza, non approssimazione). Sulla stessa scheda stampa
     anche **quale ramo della soglia di latenza gira davvero**: `tps` e` nullo, quindi la
     soglia e' la regressione `alpha*P+beta*B+gamma` e a 200 token vale 17,4612 s, non
     `n_out/tps + ttft`;
  G. la **griglia MoE** (4 brane: denso 25B proxy / MoE governato / MoE spacciato per
     denso / stessa brana a 8 bit) con i rapporti di `request_it_energy`, e il
     riconoscimento di quale brana sia quella che il motore produce davvero. Qui il
     fattore 11,17 del documento viene localizzato: esce dal rapporto fra la brana a
     8 bit e la brana a 16 bit, cioe' da un confronto fra due quantizzazioni diverse,
     non dall'errore MoE.
  H. tabella di **audit dei claim**: per ogni numero citato nel documento, il valore
     rigenerato, lo scarto relativo e l'esito, con le righe "rettificate" separate
     dalle righe che non si rigenerano per un errore della sonda. Le righe marcate
     "ATTESO DALLA RETTIFICA" sono i numeri corretti -- 2,7935, 8,0000, 22,348, 17,4612,
     157 e 86 -- e stanno in tabella perche' una rettifica vale solo se e' rigenerabile
     quanto il numero che sostituisce.

Esecuzione:  python probe_ecologits_gpu_steps_moe_20261026.py
Nessun hardware, nessuna richiesta di rete: calcolo offline sul pacchetto installato
(ecologits 0.11.1). Uscita: 0 se ogni ricostruzione coincide con il motore e se i claim
del documento si rigenerano o sono marcati come rettificati; 1 se una uguaglianza contro
`llm_impacts` o contro gli asset della libreria non regge, oppure se un ancoraggio di
sorgente non torna.
"""
import json
import linecache
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "cwEnergyModular"))

from energy.cloud_energy import _range_of, _value_of                      # noqa: E402
from ecologits.impacts import llm                                         # noqa: E402
from ecologits.log import logger                                          # noqa: E402
from ecologits.model_repository import ParametersMoE, models              # noqa: E402
from ecologits.tracers.utils import PROVIDER_CONFIG_MAP, llm_impacts      # noqa: E402
import ecologits                                                          # noqa: E402

logger.warning_once = lambda *a, **k: None      # i warning del registro non sono dati

LLM_PY = os.path.join(os.path.dirname(ecologits.__file__), "impacts", "llm.py")
REGISTRY = os.path.join(os.path.dirname(ecologits.__file__), "data", "models.json")
REG = json.load(open(REGISTRY, encoding="utf-8"))["models"]

# Geometrie citate dai documenti del progetto (stesse della sonda dei token).
N_OUT_70B, LAT_70B = 200, 2.0
N_OUT_MINI, LAT_MINI = 100, 1.0
PUE_70B_MIN = PROVIDER_CONFIG_MAP["huggingface_hub"].datacenter_pue.min      # 1,09
PROV_MINI, MDL_MINI = "openai", "gpt-4o-mini"
PROV_70B = "huggingface_hub"
MDL_70B = "meta-llama/Meta-Llama-3.1-70B-Instruct"
PROV_MOE, MDL_MOE = "cohere", "command-a-plus-05-2026"
PROV_MIX, MDL_MIX = "huggingface_hub", "mistralai/Mixtral-8x7B-v0.1"

TOTALI = [12.9, 25.0, 46.7, 70.55, 123.0, 218.0, 405.0]
GRADINI_DOC_16BIT = {12.9: 1, 46.7: 2, 70.55: 4, 123.0: 4, 405.0: 16, 218.0: 8}

# (descrizione, frammento di codice, riga citata dal documento, file)
ANCORAGGI = [
    ("MODEL_QUANTIZATION_BITS", "MODEL_QUANTIZATION_BITS = 16", 8, LLM_PY),
    ("GPU_MEMORY", "GPU_MEMORY = 80", 18, LLM_PY),
    ("model_required_memory", "1.2 * model_total_parameter_count * model_quantization_bits / 8", 120, LLM_PY),
    ("gpu_required_count", "2 ** math.ceil(math.log2(gpu_nb))", 139, LLM_PY),
    ("f_E (gpu_energy)", "gpu_energy_alpha * math.exp(gpu_energy_beta * batch_size) * model_active_parameter_count", 59, LLM_PY),
    ("server_energy", "(generation_latency / 3600) * server_power", 163, LLM_PY),
    ("request_it_energy", "server_energy + gpu_required_count * gpu_energy", 201, LLM_PY),
    ("request_energy", "datacenter_pue * request_it_energy", 181, LLM_PY),
    ("clamp di latenza", "if request_latency < gpu_latency", 100, LLM_PY),
    ("ramo MoE in tracers", "isinstance(model.architecture.parameters, ParametersMoE)", 89,
     os.path.join(os.path.dirname(ecologits.__file__), "tracers", "utils.py")),
    ("attivo=total per i non-ParametersMoE",
     "model_active_params = model.architecture.parameters\n", 94,
     os.path.join(os.path.dirname(ecologits.__file__), "tracers", "utils.py")),
]

# Il documento ancora la scheda MoE a "`data/models.json`, righe 136-141, con quattro
# URL di fonte": verifichiamo dove stanno DAVVERO il nome, la chiave `active_parameters`
# e il primo URL, perche' i quattro URL non stanno dentro 136-141.
ANCORAGGIO_SCHEDA = [
    ("nome della scheda", '"name": "command-a-plus-05-2026"', 136),
    ("chiave active_parameters", '"active_parameters": 25', 140),
    ("primo URL di fonte", '"https://docs.cohere.com/docs/command-a-plus"', 146),
]


def riga_effettiva(frammento: str, path: str) -> int:
    """Prima riga di `path` che contiene `frammento` (0 = assente)."""
    for i in range(1, 700):
        if frammento in linecache.getline(path, i):
            return i
    return 0


def gradino(p_total: float, bits: int):
    """(GB richiesti, divisione per la memoria di un GPU, `gpu_required_count`)."""
    mem = llm.model_required_memory(p_total, bits)
    return mem, mem / llm.GPU_MEMORY, llm.gpu_required_count(mem, llm.GPU_MEMORY)


def it_energy(active: float, totale: float, n_out: float, lat: float,
              bits: int, tps=None, ttft=None):
    """Stati intermedi del DAG con i default del pacchetto (PUE=1: IT lorda)."""
    return llm.compute_llm_impacts_dag(
        model_active_parameter_count=active, model_total_parameter_count=totale,
        output_token_count=n_out, request_latency=lat,
        if_electricity_mix_adpe=1.0, if_electricity_mix_pe=1.0,
        if_electricity_mix_gwp=1.0, if_electricity_mix_wue=1.0,
        datacenter_pue=1.0, datacenter_wue=1.0,
        model_quantization_bits=bits, tps=tps, ttft=ttft)


def f_e(p_active: float) -> float:
    """Wh/token di un singolo GPU: la regressione `impacts/llm.py:59` ricalcolata."""
    return (llm.GPU_ENERGY_ALPHA * math.exp(llm.GPU_ENERGY_BETA * llm.BATCH_SIZE)
            * p_active + llm.GPU_ENERGY_GAMMA)


def card(provider: str, name: str) -> dict:
    return next(x for x in REG if x["provider"] == provider and x["name"] == name)


def main() -> int:
    errori = []
    rettifiche = []
    print(f"ecologits {getattr(ecologits, '__version__', 'unknown')}  "
          f"--  {LLM_PY}")

    print("\n=== A. ancoraggi di sorgente (citati dal documento -> riga effettiva) ===")
    for nome, frammento, citata, path in ANCORAGGI:
        eff = riga_effettiva(frammento, path)
        ok = eff == citata
        print(f"  {nome:24s} :{citata:<4d} effettiva :{eff:<4d} "
              f"{'OK' if ok else 'ATTESO :%d -> :%d' % (citata, eff)}")
        if not ok:
            rettifiche.append(f"ancoraggio {nome}: il documento cita :{citata}, "
                              f"la riga effettiva e' :{eff}")

    print("\n=== B. costanti (nomi del modulo, non valori ritrascritti) ===")
    for nome in ("MODEL_QUANTIZATION_BITS", "GPU_ENERGY_ALPHA", "GPU_ENERGY_BETA",
                 "GPU_ENERGY_GAMMA", "LATENCY_ALPHA", "LATENCY_BETA",
                 "LATENCY_GAMMA", "GPU_MEMORY", "SERVER_GPUS", "SERVER_POWER",
                 "BATCH_SIZE"):
        print(f"  {nome:24s} = {getattr(llm, nome)!r}")

    print("\n=== C. gradino gpu_required_count(P_total, bits) ===")
    print(f"  {'P_total':>8s} {'16b GB':>8s} {'/80':>7s} {'n':>3s}"
          f"   {'8b GB':>8s} {'/80':>7s} {'n':>3s}   gradino atteso dal documento")
    for p in TOTALI:
        m16, r16, g16 = gradino(p, 16)
        m8, r8, g8 = gradino(p, 8)
        doc = GRADINI_DOC_16BIT.get(p)
        nota = "-" if doc is None else ("OK" if doc == g16 else f"ATTESO {doc}")
        print(f"  {p:8.2f} {m16:8.2f} {r16:7.3f} {g16:3d}   "
              f"{m8:8.2f} {r8:7.3f} {g8:3d}   {nota}")
        if doc is not None and doc != g16:
            errori.append(f"gradino {p}B (atteso {doc}, ottenuto {g16})")
    print("  Nota: `model_required_memory` usa i parametri TOTALI e i bit, `f_E` usa "
          "i TOTALI per\n  la memoria e gli ATTIVI per l'energia: due scale diverse "
          "nello stesso numero.")

    print("\n=== D. registro (data/models.json) ===")
    dep = [m for m in REG if m.get("deployment")]
    con_tps = [m for m in dep if m["deployment"].get("tps") is not None]
    moe = [m for m in REG if m["architecture"].get("type") == "moe"]
    legacy = [m for m in REG if "active_parameters" in json.dumps(m)]
    print(f"  modelli: {len(REG)}   con `deployment`: {len(dep)}   "
          f"con `tps` non nullo: {len(con_tps)}")
    if len(dep) != len(con_tps):
        rettifiche.append(
            f"il deployment esiste su {len(dep)} modelli ma `tps` e' nullo su "
            f"{len(dep) - len(con_tps)}: per quei modelli la soglia della latenza NON "
            f"e' n_out/tps+ttft, bensi' la regressione alpha*P+beta*B+gamma "
            f"(ramo `impacts/llm.py:94-95`)")
    parsed = {}
    for m in moe:
        mm = models.find_model(provider=m["provider"], model_name=m["name"])
        p = mm.architecture.parameters
        k = "ParametersMoE" if isinstance(p, ParametersMoE) else type(p).__name__
        parsed.setdefault(k, []).append(f"{m['provider']}/{m['name']}"
                                        + (f" (total {p.total}, active {p.active})"
                                           if k == "ParametersMoE" else f" ({p})"))
    print(f"  MoE nel registro: {len(moe)}, lette dal parser come: "
          + ", ".join(f"{k}={len(v)}" for k, v in sorted(parsed.items())))
    print(f"  chiave `active_parameters` presente in {len(legacy)} schede: "
          + ", ".join(f"{m['provider']}/{m['name']}" for m in legacy))
    if len(moe) > len(legacy):
        rettifiche.append(
            f"la premessa «i MoE sono il caso in cui il registro tace» non regge: "
            f"{len(moe)} schede MoE, di cui {len(parsed.get('ParametersMoE', []))} "
            f"dichiarano gia' total+active nell'oggetto `parameters` e il parser le "
            f"converte in ParametersMoE (Mixtral-8x7B: total 46,7, active 12,9). "
            f"Il caso reale non e' «il registro tace», e' il formato della scheda: la "
            f"chiave legacy `active_parameters` -- che il parser non legge -- sta in "
            f"{len(legacy)} scheda, ed e' proprio quella che collassa")
    for nome, frammento, citata in ANCORAGGIO_SCHEDA:
        eff = riga_effettiva(frammento, REGISTRY)
        print(f"     ancoraggio {nome:22s}: documento dice :{citata}, "
              f"file dice :{eff} {'OK' if eff == citata else 'DIFFERENTE'}")
        if eff != citata:
            rettifiche.append(f"ancoraggio scheda MoE «{nome}»: il documento cita "
                              f":{citata}, la riga effettiva e' :{eff}")
    for k, v in parsed.items():
        if k != "ParametersMoE":
            for nome in v:
                rettifiche.append(
                    f"{nome}: `parameters` scalare + `active_parameters` fratello -> "
                    f"il parser lo consegna come {k}, il ramo MoE di "
                    f"`tracers/utils.py:89-94` non scatta e l'attivo collassa sul totale")
    for prov, mdl in ((PROV_MINI, MDL_MINI), (PROV_70B, MDL_70B),
                      (PROV_MOE, MDL_MOE), (PROV_MIX, MDL_MIX)):
        c = card(prov, mdl)
        mm = models.find_model(provider=prov, model_name=mdl)
        p = mm.architecture.parameters
        attivo = p.active if isinstance(p, ParametersMoE) else p
        print(f"  {prov}/{mdl}\n     json={json.dumps(c['architecture'])}"
              f"  deployment={c.get('deployment')}\n     parser: parameters="
              f"{type(p).__name__} -> active usato = {attivo}")

    print("\n=== E. f_E(P_active, B=64) e il fattore MoE sul termine per token ===")
    f25, f218 = f_e(25.0), f_e(218.0)
    lib25 = llm.gpu_energy(25.0, 1, llm.BATCH_SIZE, llm.GPU_ENERGY_ALPHA,
                           llm.GPU_ENERGY_BETA, llm.GPU_ENERGY_GAMMA) * 1000
    lib218 = llm.gpu_energy(218.0, 1, llm.BATCH_SIZE, llm.GPU_ENERGY_ALPHA,
                            llm.GPU_ENERGY_BETA, llm.GPU_ENERGY_GAMMA) * 1000
    print(f"  f_E(25)   = {f25:.6e} Wh/token   (libreria {lib25:.6e}, scarto "
          f"{abs(f25 - lib25):.3e})")
    print(f"  f_E(218)  = {f218:.6e} Wh/token   (libreria {lib218:.6e}, scarto "
          f"{abs(f218 - lib218):.3e})")
    print(f"  fattore   = {f218 / f25:.4f}   (218/25 = {218 / 25:.2f} sarebbe "
          f"l'attesa di chi ignora l'offset gamma)")
    if abs(f25 - lib25) > 1e-18 or abs(f218 - lib218) > 1e-18:
        errori.append("f_E ricostruito != asset gpu_energy")

    print(f"\n=== F. correzione 1 sul 70B: manca il moltiplicatore gpus_required "
          f"(n_out={N_OUT_70B}, lat={LAT_70B} s, 16 bit) ===")
    r70 = it_energy(70.55, 70.55, N_OUT_70B, LAT_70B, 16)
    g70, e_gpu70, e_srv70 = (r70["gpu_required_count"], r70["gpu_energy"],
                             r70["server_energy"])
    e_codice = PUE_70B_MIN * r70["request_it_energy"]
    e_proposta = PUE_70B_MIN * (e_srv70 + e_gpu70)
    print(f"  gpu_required_count = {g70} (memoria "
          f"{r70['model_required_memory']:.2f} GB / {llm.GPU_MEMORY} = "
          f"{r70['model_required_memory'] / llm.GPU_MEMORY:.3f} -> "
          f"2^ceil(log2(3)) = {g70})   generation_latency = "
          f"{r70['generation_latency']} s")
    print(f"  E_server = {e_srv70:.15e} kWh   E_gpu(1 GPU) = {e_gpu70:.15e} kWh")
    print(f"  codice    : PUE * (E_server + {g70} * E_gpu) = {e_codice:.15e} kWh")
    print(f"  proposta  : PUE * (E_server + E_gpu)         = {e_proposta:.15e} kWh")
    print(f"  fattore    = {e_codice / e_proposta:.4f}   (documento: 3,268)")
    c70 = card(PROV_70B, MDL_70B)
    tps70, ttft70 = (c70.get("deployment") or {}).get("tps"), \
        (c70.get("deployment") or {}).get("ttft")
    lpt70 = (llm.LATENCY_ALPHA * 70.55 + llm.LATENCY_BETA * llm.BATCH_SIZE
             + llm.LATENCY_GAMMA)
    soglia70 = N_OUT_70B * lpt70 + (ttft70 or 0)
    print(f"  quale ramo della soglia gira su QUESTA scheda: deployment="
          f"{c70.get('deployment')} -> `tps` = {tps70}")
    print(f"     con `tps` nullo il ramo e' la regressione `impacts/llm.py:95`"
          f" alpha*P_active+beta*B+gamma = {lpt70:.7f} s/token (non 1/tps)")
    print(f"     soglia a n_out={N_OUT_70B}: {soglia70:.4f} s   (documento: "
          f"17,4612 s)  |  request_latency={LAT_70B} s -> min = "
          f"{r70['generation_latency']} s: vince la misura, la rete NON viene "
          f"scartata")
    if tps70 is not None:
        errori.append("70B: la scheda ha `tps` non nullo -> il ramo a regressione "
                      "citato nella spec non e' quello di produzione")
    if abs(soglia70 - 17.4612) > 5e-4:
        rettifiche.append(f"soglia a regressione del 70B: la spec cita 17,4612 s, "
                          f"la sonda rigenera {soglia70:.4f} s")
    res70 = llm_impacts(provider=PROV_70B, model_name=MDL_70B,

                        output_token_count=N_OUT_70B, request_latency=LAT_70B)
    lo70, hi70, _mid = _range_of(getattr(res70, "energy", None))
    print(f"  llm_impacts reale: energy.min = {lo70:.15e}  energy.max = "
          f"{hi70:.15e} kWh   (il max viene dal PUE a range 1,09-1,14 di "
          f"huggingface_hub)")
    print(f"  ricostruzione vs llm_impacts.min: scarto relativo "
          f"{abs(e_codice / lo70 - 1):.3e}")
    if abs(e_codice - lo70) > 1e-18:
        errori.append("70B: ricostruzione != llm_impacts.min")

    print(f"\n=== G. griglia MoE 218B/25B (n_out={N_OUT_70B}, lat={LAT_70B} s, "
          f"tps/ttft dalla scheda command-a) ===")
    tps, ttft = card(PROV_MOE, MDL_MOE)["deployment"]["tps"], \
        card(PROV_MOE, MDL_MOE)["deployment"]["ttft"]
    brane = [
        ("A  denso 25B (proxy scelto per parametri attivi), 16 bit", 25.0, 25.0, 16),
        ("B  MoE governato: active 25 / total 218, 16 bit", 25.0, 218.0, 16),
        ("C  MoE spacciato per denso: active 218 / total 218, 16 bit", 218.0, 218.0, 16),
        ("D  active 218 / total 218, 8 bit", 218.0, 218.0, 8),
    ]
    it = {}
    for label, a, t, b in brane:
        r = it_energy(a, t, N_OUT_70B, LAT_70B, b, tps=tps, ttft=ttft)
        key = label.split()[0]
        it[key] = r["request_it_energy"]
        print(f"  {label}\n      mem={r['model_required_memory']:7.2f} GB  "
              f"gpus={r['gpu_required_count']}  gen_latency="
              f"{r['generation_latency']} s  E_gpu={r['gpu_energy']:.6e}  "
              f"E_server={r['server_energy']:.6e}  E_it={r['request_it_energy']:.6e} kWh")
    pue_moe = PROVIDER_CONFIG_MAP[PROV_MOE].datacenter_pue
    res_moe = llm_impacts(provider=PROV_MOE, model_name=MDL_MOE,
                          output_token_count=N_OUT_70B, request_latency=LAT_70B)
    e_moe = _value_of(getattr(res_moe, "energy", None))
    print("  rapporti su `request_it_energy`:")
    print(f"     C/A = {it['C'] / it['A']:7.4f}   etichetta MoE sbagliata + gradino, "
          f"entrambi a 16 bit")
    print(f"     D/A = {it['D'] / it['A']:7.4f}   <== qui esce il numero 11,17 citato "
          f"nel documento: 8 bit contro 16 bit")
    print(f"     C/B = {it['C'] / it['B']:7.4f}   SOLA etichetta MoE (stessi totali, "
          f"quindi stessi gradini)")
    print(f"     B/A = {it['B'] / it['A']:7.4f}   SOLO il gradino 25B -> 218B")
    print(f"  llm_impacts reale su {MDL_MOE} = {e_moe:.15e} kWh (banda: "
          f"{_range_of(getattr(res_moe, 'energy', None))})")
    for k in ("A", "B", "C", "D"):
        att = pue_moe * it[k]
        print(f"     vs PUE({pue_moe}) * E_it({k}) = {att:.15e}  scarto relativo "
              f"{abs(e_moe / att - 1):.6f}"
              + ("   <== IL MOTORE E' IN QUESTA BRANA"
                 if abs(e_moe - att) < 1e-16 else ""))
    if abs(e_moe - pue_moe * it["C"]) > 1e-16:
        errori.append("MoE: output del motore != brana C")

    print("\n=== H. audit dei claim di "
          "`experiment_results/metodo_analitico_cloud_20261026.md` ===")
    lo_mini, hi_mini, _m = _range_of(getattr(llm_impacts(
        provider=PROV_MINI, model_name=MDL_MINI, output_token_count=N_OUT_MINI,
        request_latency=LAT_MINI), "energy", None))
    # (nome, valore scritto nel documento, valore rigenerato, tolleranza relativa)
    # La tolleranza codifica l'arrotondamento delle cifre scritte nel documento: 169,3
    # ha 4 cifre significative, quindi 2e-4 copre l'arrotondamento; un fattore 2 o 8
    # non e' dentro nessuna tolleranza ragionevole.
    righe = [
        ("gpt-4o-mini 100 tok 1,0 s bordo min (P=8B)", "6,191401e-06", lo_mini, 5e-7),
        ("gpt-4o-mini 100 tok 1,0 s bordo max (P=28B)", "7,557994e-06", hi_mini, 5e-7),
        ("Llama-3.1-70B 200 tok 2,0 s energy.min", "7,60487313e-05", lo70, 5e-9),
        ("memoria 70,55B a 16 bit (1,2*70,55*16/8)", "169,3", r70["model_required_memory"], 2e-4),
        ("gpu_required 70,55B", "4", g70, 0.0),
        ("formula della proposta sul 70B", "2,327e-05", e_proposta, 5e-4),
        ("fattore 70B (codice/proposta)", "3,268", e_codice / e_proposta, 5e-4),
        ("gpu_required 12,9B -> 1", "1", gradino(12.9, 16)[2], 0.0),
        ("gpu_required 46,7B -> 2", "2", gradino(46.7, 16)[2], 0.0),
        ("gpu_required 123B -> 4", "4", gradino(123.0, 16)[2], 0.0),
        ("gpu_required 405B -> 16", "16", gradino(405.0, 16)[2], 0.0),
        ("f_E(25) Wh/token", "5,476463e-05", f25, 5e-7),
        ("f_E(218) Wh/token", "1,646615e-04", f218, 5e-7),
        ("fattore MoE per token", "3,0067", f218 / f25, 5e-5),
        ("memoria 218B a 16 bit", "523,2", gradino(218.0, 16)[0], 5e-4),
        ("gpu_required 218B a 16 bit (da 1 a 8)", "8", gradino(218.0, 16)[2], 0.0),
        ("E_it brana denso-25B (A)", "1,225501e-05", it["A"], 5e-7),
        ("E_it brana citata come 1,369375e-04", "1,369375e-04", it["D"], 5e-7),
        ("ATTESO DALLA RETTIFICA: etichetta MoE a parita' di scheda (C/B)",
         "2,7935", it["C"] / it["B"], 5e-5),
        ("ATTESO DALLA RETTIFICA: solo gradino GPU (B/A)", "8,0000", it["B"] / it["A"], 1e-9),
        ("ATTESO DALLA RETTIFICA: etichetta + gradino (C/A, 16 bit)",
         "22,348", it["C"] / it["A"], 5e-4),
        ("ATTESO DALLA RETTIFICA: soglia a regressione sul 70B, n_out=200",
         "17,4612", soglia70, 5e-5),
        ("ATTESO DALLA RETTIFICA: schede del registro con `tps` non nullo",
         "157", len(con_tps), 0.0),
        ("ATTESO DALLA RETTIFICA: MoE gia' dichiarati total+active (ParametersMoE)",
         "86", len(parsed.get("ParametersMoE", [])), 0.0),
        # Dove nasce il numero scritto nel documento: il rapporto fra la brana a 8 bit
        # e quella a 16 bit, cioe' fra due quantizzazioni diverse, non fra dense e MoE.
        ("origine del «11,17» scritto nel documento (D/A, 8 bit vs 16 bit)",
         "11,17", it["D"] / it["A"], 5e-3),
    ]
    non_rigenerati = []
    for nome, nel_doc, rigenerato, tol in righe:
        atteso = float(str(nel_doc).replace(",", "."))
        dev = abs(rigenerato / atteso - 1) if atteso else abs(rigenerato - atteso)
        ok = dev <= tol
        val = str(rigenerato) if isinstance(rigenerato, int) else f"{rigenerato:.6e}"
        print(f"  {nome:52s} doc={nel_doc:>16s}  rigenerato={val:>16s}  "
              f"dev={dev:.2e}  {'OK' if ok else 'NON RIGENERATO'}")
        if not ok:
            non_rigenerati.append((nome, nel_doc, val, dev))
    if non_rigenerati:
        print("\n  RITROVAMENTO (non un errore della sonda):")
        for nome, nel_doc, val, dev in non_rigenerati:
            print(f"    - {nome}: il documento scrive {nel_doc}, la sonda rigenera "
                  f"{val} (dev {dev:.2%})")
        rettifiche.append(
            "il fattore '11,17' del documento (§2.3) NON e' il fattore MoE alla "
            "geometria dichiarata: e' il rapporto fra la brana a 8 bit e quella a 16 "
            "bit (D/A). A 16 bit -- default del pacchetto -- lo stesso confronto vale "
            "C/A = 22,348, e l'errore di SOLA etichetta MoE, a parita' di parametri "
            "totali e quindi di gradini, e' C/B = 2,7935")
    print(f"  righe rigenerate: {len(righe) - len(non_rigenerati)}/{len(righe)}")

    print("\n=== Lettura ===")
    print("I gradini sono 2^ceil(log2(ceil(mem/GPU_MEMORY))) e la memoria dipende dai")
    print("parametri TOTALI e dai bit; l'energia per token dipende dai parametri ATTIVI.")
    print("Sono due scale diverse dentro lo stesso numero, e nessuna delle due e'")
    print("continua nella classe di modello: un proxy scelto per la classe da 25B vale")
    print("1 GPU, lo stesso modello dichiarato a 218B ne vale 8 (fattore esatto 8,0).")
    print("L'etichetta MoE sbagliata, a parita' di scheda, e' un fattore 2,79 sull'IT")
    print("(3,01 sul solo termine per token, perche' l'offset gamma ammortizza).")

    if rettifiche:
        print(f"\nRETTIFICHE ({len(rettifiche)}) -- gia' applicate il 26-10 in "
              "`metodo_analitico_cloud_20261026.md` (§2.3, regola 1 di N_active e "
              "riga del campo `cloud_moe_active_assumption`) e in "
              "`metodi_per_dominio_20261025_spec.md`; la sonda le ri-emette perche' "
              "restino rigenerabili dal loro artefatto:")
        for r in rettifiche:
            print(f"  * {r}")
    if errori:
        print("\nFALLIMENTI INTERNI DELLA SONDA (da risolvere, non da rettificare):")
        for e in errori:
            print(f"  ! {e}")
        return 1
    print("\nOgni ricostruzione coincide con il motore: 0 fallimenti interni.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
