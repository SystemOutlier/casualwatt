# Pilota P2.9 sul runner v4 — 2026-11-07

Modello: `qwen2.5:0.5b` — runner `benchmark_v4.run_v4_benchmark` — ordine dichiarato `p29:A1,A2,A3,Bi,Bn,C`.
CSV: `casualwatt_v4_results_p29.csv` (10 righe), `casualwatt_v4_block_summary_p29.csv` (6 blocchi), `runs.json`.

## Verifiche

- A (semantica di `done_reason`): **NON superata**
  - A1 [NO]: done_reason=stop, classe=eos, N_out=15.0, tetto=32.0 — done_reason='stop', atteso 'length'; termination_class='eos', attesa 'cap_reached'; N_out_actual=15.0 != num_predict=32.0
  - A2 [ok]: done_reason=length, classe=cap_reached, N_out=32.0, tetto=32.0
  - A3 [ok]: done_reason=stop, classe=eos, N_out=2.0, tetto=32.0
  - conseguenza: P2.9 non superato: la campagna NON parte (protocollo:841-856)
- B (cache, descrittiva): identico {'n': 3, 'input_tokens': [297.0, 297.0, 297.0], 'input_tokens_median': 297.0, 'input_tokens_mean': 297.0, 'prefill_s': [1.160942, 0.017198, 0.015236], 'prefill_s_median': 0.017198, 'prefill_s_mean': 0.397792}; nonce {'n': 3, 'input_tokens': [310.0, 310.0, 310.0], 'input_tokens_median': 310.0, 'input_tokens_mean': 310.0, 'prefill_s': [1.192783, 1.178324, 1.164203], 'prefill_s_median': 1.178324, 'prefill_s_mean': 1.178437}; scarto {'input_tokens_median': 0.043771, 'prefill_s_median': 67.515176, 'input_tokens_mean': 0.043771, 'prefill_s_mean': 1.962445}
- C (contesto): **superata** — controlli {"guardia_p27": {"n_in_plus_n_out": 984.0, "num_ctx": 8192, "rispettata": true}, "context_boundary": "assente", "parole_testo_spedito": 525, "n_in_almeno_parole": true, "rapporto_token_parola": {"prompt_c": 1.866667, "warmup": 1.843629, "rapporto": 1.012496, "tolleranza": 0.1, "entro_tolleranza": true}}

## Terne per blocco (P6.2)

| blocco | richieste | P_pre W | pre_range W | half_range W | dP W | budget_base W | u_within,b J |
|---|---|---|---|---|---|---|---|
| qwen2.5-0.5b__p29-a1__b01 | 1 | 6.116852 | 1.093608 | 0.546804 | -0.129404 | 0.550619 | n/d |
| qwen2.5-0.5b__p29-a2__b01 | 1 | 6.020601 | 0.528946 | 0.264473 | 7.55142 | 3.784961 | n/d |
| qwen2.5-0.5b__p29-a3__b01 | 1 | 8.320663 | 0.789207 | 0.394603 | -2.257677 | 1.195821 | n/d |
| qwen2.5-0.5b__p29-b-id__b01 | 3 | 6.040237 | 0.074071 | 0.037036 | 0.251063 | 0.13088 | 13.169478 |
| qwen2.5-0.5b__p29-b-nonce__b01 | 3 | 7.882317 | 1.690638 | 0.845319 | -1.811411 | 1.238897 | 1.458864 |
| qwen2.5-0.5b__p29-c__b01 | 1 | 6.235182 | 0.368676 | 0.184338 | -0.15089 | 0.199179 | n/d |

`u_within,b` e' `n/d` dove il blocco ha una richiesta sola: con `m = 1` il semi-range e' zero per costruzione (P3.8/F.9).

## `dt_nominal_s` congelato

- valore: **2.751297 s**
- regola: P4.4 requisito 5, protocollo_v4_20261024.md:1481-1486: fissato PRIMA della campagna come 3 x la mediana della durata di richiesta misurata nel pilota di P2
- mediana delle durate: 0.917099 s su 10 righe valide
- durate: [0.047065, 0.060772, 0.195735, 0.453485, 0.63556, 1.198638, 1.207016, 1.215095, 1.236959, 4.048023]
- mediane per braccio (diagnostica, non usate): {'A1': 0.453485, 'A2': 0.63556, 'A3': 0.195735, 'Bi': 0.060772, 'Bn': 1.207016, 'C': 4.048023}

Il numero non e' stato scelto: esce dalla mediana delle righe misurate, e l'artefatto ne cita percorso, sha256, run id e HEAD.
