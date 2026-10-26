# -*- coding: utf-8 -*-
"""Sonda del clamp di latenza in EcoLogits (Punto #119, 26-10-2026).

Perche' esiste. `energy/cloud_energy.py` passa a `llm_impacts` la latenza MISURATA
end-to-end della richiesta (rete + coda del provider incluse) e la Nota B4 asseriva
che "la stima server-side ne risulta lievemente sovrastimata per la porzione
d'attesa". Lettode il sorgente installato, `request_latency` entra in un solo punto
(`impacts/llm.py:574`) e sempre attraverso `generation_latency`:

    gpu_latency = output_token_count * latency_per_token + ttft
    if request_latency < gpu_latency: return request_latency
    return gpu_latency                       # impacts/llm.py:95-102

quindi la misura non puo' che essere un **upper clamp**: oltre la soglia interna il
motore usa la propria regressione e il tempo di rete viene scartato in silenzio.
La direzione del bias asserita nel codice e' sbagliata, e il rischio reale e'
l'opposto: una riga dichiara una latenza misurata che non ha influito sul numero.

Cosa stampa, e perche' conta:
  1. la soglia calcolata dalla regressione pubblicata (`LATENCY_ALPHA/BETA/GAMMA`,
     `impacts/llm.py:14-16`, `BATCH_SIZE = 64` a `:31`) per la nostra geometria;
  2. il valore d'energia al crescere della latenza, per mostrare che da un punto in
     poi e' **identico all'ultima cifra**: non "pressapoche', bit-identico;
  3. l'incrocio fra la latenza in kWh (termine server) e la parte indipendente da
     `request_latency`, che fissa il margine di manovra reale della nostra misura.

Esecuzione:  python probe_ecologits_clamp_20261026.py
Nessun hardware, nessuna richiesta di rete: calcolo offline sul pacchetto installato.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "cwEnergyModular"))

from energy.cloud_energy import _range_of, _value_of                      # noqa: E402
from ecologits.tracers.utils import llm_impacts                           # noqa: E402
import ecologits                                                          # noqa: E402

A = 0.0006785088094353663     # LATENCY_ALPHA, impacts/llm.py:14  [s/parametro-attivo]
B = 0.0003119310311688259     # LATENCY_BETA,  impacts/llm.py:15  [s/token-in-batch]
C = 0.019473717579473387      # LATENCY_GAMMA, impacts/llm.py:16  [s, offset]
BATCH = 64                    # BATCH_SIZE,    impacts/llm.py:31

PROV, MDL = "openai", "gpt-4o-mini"
LATENZE = [0.05, 0.5, 1.0, 1.4, 1.5, 1.6, 2.0, 3.6, 5.0, 10.0, 30.0, 120.0]


def gpu_latency(params_b: float, n_out: int) -> float:
    """Latenza di generazione stimata dal motore (ttft 0, tps non fornito)."""
    return n_out * (A * params_b + B * BATCH + C)


def run(n_out: int) -> None:
    print(f"\n=== {PROV}/{MDL}  output_token_count={n_out} ===")
    print("  soglia interna gpu_latency: "
          + ", ".join(f"P={p}B -> {gpu_latency(p, n_out):.4f} s" for p in (8, 18, 28)))
    ref = None
    first_flat_at = None
    for lat in LATENZE:
        res = llm_impacts(provider=PROV, model_name=MDL,
                          output_token_count=n_out, request_latency=lat)
        e = _value_of(getattr(res, "energy", None))
        lo, hi, _ = _range_of(getattr(res, "energy", None))
        flat = ""
        if ref is not None and e is not None and abs(e - ref) < 1e-18:
            flat = "   <-- IDENTICA alla precedente (clamp: tempo extra scartato)"
            if first_flat_at is None:
                first_flat_at = lat
        ref = e
        print(f"  request_latency={lat:7.3f} s  E={e:.9e} kWh  "
              f"banda[{lo:.6e}, {hi:.6e}]{flat}")
    if first_flat_at is not None:
        prev = LATENZE[LATENZE.index(first_flat_at) - 1]
        print(f"  -> il valore published smette di rispondere alla misura fra "
              f"{prev} s e {first_flat_at} s.")


def main() -> None:
    print(f"ecologits installato: {getattr(ecologits, '__version__', 'unknown')}")
    print("request_latency entra solo da generation_latency = "
          "min(request_latency, gpu_latency)  [impacts/llm.py:100-102, uso a :574]")
    run(32)      # geometria media del progetto: N_out 31,8 (idee_implementative:69)
    run(200)     # coda lunga: la soglia interna scala con n_out
    print("\nLettura: finche' la misura e' sotto la soglia interna il tempo di rete")
    print("entra nel termine server; sopra, la riga dichiara una latenza che NON ha")
    print("influito sul numero. Serve cloud_latency_used_s / cloud_latency_binding.")


if __name__ == "__main__":
    main()
