# -*- coding: utf-8 -*-
"""Sonda del clamp di latenza in EcoLogits (Punto #119, 26-10-2026).

Perche' esiste. `energy/cloud_energy.py` passa a `llm_impacts` la latenza MISURATA
end-to-end della richiesta (rete + coda del provider incluse) e la Nota B4 asseriva
che "la stima server-side ne risulta lievemente sovrastimata per la porzione
d'attesa". Letto il sorgente installato (ecologits 0.11.1), `request_latency` entra
in un solo punto (`impacts/llm.py:574`) e sempre attraverso `generation_latency`:

    gpu_latency = output_token_count * latency_per_token + ttft
    if request_latency < gpu_latency: return request_latency
    return gpu_latency                            # impacts/llm.py:94-102

quindi la nostra misura non pu' che essere un **upper clamp**: sopra la soglia il
tempo di rete e di coda viene scartato in silenzio. La direzione del bias asserita
nel codice e' sbagliata, e il rischio reale e' l'opposto -- una riga che dichiara
una latenza misurata la quale NON ha influito sul numero.

Cosa stampa, e perche' conta:
  1. la soglia `gpu_latency` **del percorso di produzione**: `llm_impacts` inietta
     `tps` e `ttft` dalla scheda del modello (`tracers/utils.py:121-122`). La
     regressione `alpha*P + beta*B + gamma` (`impacts/llm.py:14-16`) e' il ramo che
     si usa quando quel valore manca.
     TERZA RETTIFICA, 26-10-2026 (`probe_ecologits_gpu_steps_moe_20261026.py`,
     sezione D): le due stesure precedenti di questo punto asserivano che il ramo a
     regressione "qui non compare mai", perche' contavano i `deployment` (344 su 344)
     invece dei `tps` (non nulli su 157). Su 187 schede il ramo vivo e' proprio la
     regressione -- fra cui `meta-llama/Meta-Llama-3.1-70B-Instruct`, usata come
     esempio in `energy/cloud_energy.py`. La soglia di questo run resta
     `n_out/tps + ttft` perche' `gpt-4o-mini` e' una delle 157 con `tps`; i numeri che
     seguono non cambiano, cambia la generalizzazione.
  2. l'energia al crescere della latenza, con il delta rispetto alla latenza di
     riferimento di 0,2 s usata dalle tabelle in `experiment_results/`, per mostrare
     che da un punto in poi e' **bit-identica al plateau**, non "pressappoco";
  3. l'incrocio, che cade esattamente su `n_out / tps + ttft` (1,5697 s a 32 token
     con tps 33 e ttft 0,6): la soglia e' il rendimento dichiarato del provider,
     non una nostra assunzione. Il run copre n_out = 32, 100, 200 perche' le tre
     geometrie sono quelle citate dai documenti del progetto.

Esecuzione:  python probe_ecologits_clamp_20261026.py
Nessun hardware, nessuna richiesta di rete: calcolo offline sul pacchetto installato.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "cwEnergyModular"))

from energy.cloud_energy import _range_of, _value_of                      # noqa: E402
from ecologits.tracers.utils import llm_impacts                           # noqa: E402
import ecologits                                                          # noqa: E402

REGISTRY = os.path.join(os.path.dirname(ecologits.__file__), "data", "models.json")
PROV, MDL = "openai", "gpt-4o-mini"
REF_LAT = 0.2                       # la latenza di riferimento delle tabelle in `experiment_results/`
LATENZE = [0.05, 0.2, 0.5, 1.0, 1.4, 1.5, 1.55, 1.5697, 1.57, 1.6, 2.0, 3.6, 3.7,
           5.0, 6.6606, 10.0, 30.0, 120.0]


def deployment(provider: str, name: str):
    """tps e ttft dichiarati nel registro per (provider, modello)."""
    for m in json.load(open(REGISTRY, encoding="utf-8"))["models"]:
        if m["provider"] == provider and m["name"] == name:
            return m.get("deployment") or {}
    return {}


def threshold(tps: float, ttft: float, n_out: int) -> float:
    """gpu_latency del percorso di produzione: n_out/tps + ttft."""
    return n_out / tps + ttft


def energy(n_out: int, lat: float):
    """(energia media, min, max) in kWh da una chiamata di produzione."""
    res = llm_impacts(provider=PROV, model_name=MDL,
                      output_token_count=n_out, request_latency=lat)
    return _value_of(getattr(res, "energy", None)), _range_of(getattr(res, "energy", None))


def run(n_out: int, tps: float, ttft: float) -> None:
    thr = threshold(tps, ttft, n_out)
    plateau = energy(n_out, thr)[0]
    print(f"\n=== {PROV}/{MDL}  output_token_count={n_out}  "
          f"tps={tps} ttft={ttft}  soglia interna n_out/tps+ttft = {thr:.10f} s ===")
    print(f"  plateau (energia alla soglia, cioe' con clamp attivo) = {plateau:.12e} kWh")
    ref = energy(n_out, REF_LAT)[0]
    for lat in LATENZE:
        e, (lo, hi, _mid) = energy(n_out, lat)
        binding = "misurata" if lat < thr else "STIMA INTERNA (clamp)"
        ident = "   <-- IDENTICA al plateau" if (
            lat >= thr and abs(e - plateau) < 1e-18) else ""
        print(f"  request_latency={lat:8.4f} s  E={e:.12e} kWh  "
              f"banda[{lo:.6e}, {hi:.6e}]  delta vs {REF_LAT} s="
              f"{(e / ref - 1) * 100:+8.3f}%  vincola={binding}{ident}")


def main() -> None:
    print(f"ecologits installato: {getattr(ecologits, '__version__', 'unknown')}")
    dep = deployment(PROV, MDL)
    tot = json.load(open(REGISTRY, encoding="utf-8"))["models"]
    con_dep = sum(1 for m in tot if m.get("deployment"))
    con_tps = sum(1 for m in tot if (m.get("deployment") or {}).get("tps") is not None)
    print(f"registro: {len(tot)} modelli, {con_dep} con deployment, "
          f"{con_tps} con `tps` non nullo (tps/ttft iniettati da "
          f"tracers/utils.py:121-122; senza `tps` la soglia e' la regressione "
          f"`impacts/llm.py:95`, non n_out/tps+ttft)")
    print(f"deployment di {PROV}/{MDL}: {dep}")
    for n_out in (32, 100, 200):
        run(n_out, dep["tps"], dep["ttft"])
    print("\nLettura: finche' la misura e' sotto n_out/tps + ttft il tempo di rete")
    print("entra nel termine server; sopra, la riga dichiara una latenza che NON ha")
    print("influito sul numero e l'energia resta IDENTICA al plateau. Servono")
    print("cloud_latency_used_s e cloud_latency_binding (misurata | stima-interna).")


if __name__ == "__main__":
    main()
