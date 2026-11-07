# Pilota P2.9 sul runner v4 — 2026-11-07

Modello: `qwen2.5:0.5b` — runner `benchmark_v4.run_v4_benchmark` — ordine dichiarato `p29:A1,A2,A3,Bi,Bn,C`.
CSV: `casualwatt_v4_results_p29.csv` (10 righe), `casualwatt_v4_block_summary_p29.csv` (6 blocchi), `runs.json`.

## Verifiche

- A (semantica di `done_reason`): **superata**
  - A1 [ok]: done_reason=length, classe=cap_reached, N_out=32.0, tetto=32.0
  - A2 [ok]: done_reason=length, classe=cap_reached, N_out=32.0, tetto=32.0
  - A3 [ok]: done_reason=stop, classe=eos, N_out=2.0, tetto=32.0
  - conseguenza: la campagna puo' partire
- B (cache, descrittiva): identico {'n': 3, 'input_tokens': [297.0, 297.0, 297.0], 'input_tokens_median': 297.0, 'input_tokens_mean': 297.0, 'prefill_s': [1.208799, 0.016102, 0.014839], 'prefill_s_median': 0.016102, 'prefill_s_mean': 0.413247}; nonce {'n': 3, 'input_tokens': [310.0, 310.0, 310.0], 'input_tokens_median': 310.0, 'input_tokens_mean': 310.0, 'prefill_s': [1.135049, 1.145196, 1.128363], 'prefill_s_median': 1.135049, 'prefill_s_mean': 1.136203}; scarto {'input_tokens_median': 0.043771, 'prefill_s_median': 69.491181, 'input_tokens_mean': 0.043771, 'prefill_s_mean': 1.749453}
- C (contesto): **superata** — controlli {"guardia_p27": {"n_in_plus_n_out": 984.0, "num_ctx": 8192, "rispettata": true}, "context_boundary": "assente", "parole_testo_spedito": 525, "n_in_almeno_parole": true, "rapporto_token_parola": {"prompt_c": 1.866667, "warmup": 1.843629, "rapporto": 1.012496, "tolleranza": 0.1, "entro_tolleranza": true}}

## Terne per blocco (P6.2)

| blocco | richieste | P_pre W | pre_range W | half_range W | dP W | budget_base W | u_within,b J |
|---|---|---|---|---|---|---|---|
| qwen2.5-0.5b__p29-a1__b01 | 1 | 8.70434 | 4.538748 | 2.269374 | 0.757743 | 2.300783 | n/d |
| qwen2.5-0.5b__p29-a2__b01 | 1 | 6.004142 | 0.159513 | 0.079757 | -0.031947 | 0.081341 | n/d |
| qwen2.5-0.5b__p29-a3__b01 | 1 | 6.297229 | 0.310427 | 0.155213 | -0.111763 | 0.164966 | n/d |
| qwen2.5-0.5b__p29-b-id__b01 | 3 | 6.041866 | 0.630198 | 0.315099 | 1.518442 | 0.822012 | 13.353762 |
| qwen2.5-0.5b__p29-b-nonce__b01 | 3 | 7.459288 | 1.633163 | 0.816582 | -1.65201 | 1.161504 | 1.557569 |
| qwen2.5-0.5b__p29-c__b01 | 1 | 5.663985 | 0.302018 | 0.151009 | -1.091009 | 0.56602 | n/d |

`u_within,b` e' `n/d` dove il blocco ha una richiesta sola: con `m = 1` il semi-range e' zero per costruzione (P3.8/F.9).

## `dt_nominal_s` congelato

- valore: **2.930748 s**
- regola: P4.4 requisito 5, protocollo_v4_20261024.md:1481-1486: fissato PRIMA della campagna come 3 x la mediana della durata di richiesta misurata nel pilota di P2
- mediana delle durate: 0.976916 s su 10 righe valide
- durate: [0.043409, 0.043732, 0.218623, 0.619917, 0.796816, 1.157016, 1.172488, 1.178841, 1.252318, 3.947675]
- mediane per braccio (diagnostica, non usate): {'A1': 0.796816, 'A2': 0.619917, 'A3': 0.218623, 'Bi': 0.043732, 'Bn': 1.172488, 'C': 3.947675}

Il numero non e' stato scelto: esce dalla mediana delle righe misurate, e l'artefatto ne cita percorso, sha256, run id e HEAD.
