# P6.6 — Pre-pilota di ripetibilità (Option C)

Data: 2026-11-06. **Stato: pre-pilota completato, banda congelata (B_abs=0.6, B_rel=1.1).**

## Decisione

Adottata **Option C** (pre-pilota di ripetibilità) per congelare la banda di
concordanza `B_abs` / `B_rel` di P6.6. La decisione è stata presa il
2026-11-06 dopo l'analisi documentata in `p6_6_banda_20261025.md`, che ha
concluso che nessuna soglia numerica è giustificabile con le evidenze disponibili
(mancano: misura di ripetibilità di `s_EPI`, quantificazione dell'errore di
bordo dei bucket da 60 s, decisione documentata su quale conclusione la banda
dovrebbe proteggere).

## Cosa fa il pre-pilota

Misurare `s_EPI` **senza produrre energia** (il modello gira ma non si misura
l'attribuzione energetica), su una configurazione fissa, con `R` repliche e fasi
da almeno 5 bucket SRUM (~300 s ciascuna). Stimare:

1. **Dispersione entro configurazione** (`u_within,b`): la variabilità di
   `s_EPI` fra repliche della stessa configurazione.
2. **Sensibilità al bordo**: quanto `s_EPI` si muove variando la durata della
   fase o lo shift del confine (bucket di bordo).
3. **Dispersione fra configurazioni**: quanto `d` dipende dalla condizione.

Congelare `B_abs` e `B_rel` da quella misura, **prima** della prova vera e
propria.

## Parametri da dichiarare prima del primo run

| parametro | valore | fonte |
|---|---|---|
| Configurazione fissa | modello, `num_predict`, concorrenza da scegliere | P6.6 `:2552-2558` |
| `R` repliche | da decidere in base alla dispersione attesa | P6.6 `:2552-2558` |
| Durata fase | ≥ 5 bucket SRUM (~300 s) | `srum_emi_cross.py:66-68` |
| `C` configurazioni (prova vera) | 10 | P6.6 Ottava emenda |
| `R` repliche (prova vera) | da congelare dopo il pre-pilota | P6.6 `:2552-2558` |

## Procedura

1. **Preparare il piano JSON** per il pre-pilota: una sola configurazione,
   `R` repliche, fasi da ≥ 5 bucket, `band: null` (il pre-pilota non ha ancora
   una banda).
2. **Eseguire il runner** (`benchmark_unified.py`) sulla configurazione fissa,
   raccogliendo `d_ollama_s` e `d_busy_s` per ogni fase.
3. **Catturare i dump SRUM** ai confini di fase (`powercfg /srumutil`,
   amministratore) con `s_epi_phase.py --capture-to`.
4. **Estrarre `s_EPI`** per fase con `s_epi_phase.py --plan ... --dump ...`.
5. **Calcolare** `d_i = s_i - s_EPI,i` e `r_i = 2*d_i/(s_i + s_EPI,i)` per
   ogni fase.
6. **Stimare** la dispersione entro configurazione (min, mediana, max, range di
   `d` e `r` fra repliche) e la sensibilità al bordo (fasi a durate diverse).
7. **Congelare** `B_abs` e `B_rel` come soglie che coprono la dispersione
   osservata più un margine dichiarato.
8. **Scrivere** la banda congelata nel piano JSON della prova vera
   (`"band": {"abs": ..., "rel": ...}`).
9. **Committare** la banda prima dell'esecuzione della prova vera.

## Cosa il pre-pilota NON fa

- Non produce energia (il modello gira ma non si misura l'attribuzione).
- Non tocca il percorso energetico di produzione.
- Non promuove l'attribuzione a "validata".
- Non arbitra la scala assoluta (serve wattmetro esterno).

## Emendamento al protocollo

Il protocollo P6.6 dice "la banda si fissa prima del primo run". Il pre-pilota
è un run di calibrazione, non la prova vera: la banda nasce dopo un run di
calibrazione, non "prima del primo run" in senso assoluto. Questo è un
emendamento esplicito al protocollo, dichiarato qui.

## Stato

- [x] Decisione adottata (Option C)
- [x] Piano JSON del pre-pilota preparato (prep_plan3.json, prep_plan5.json)
- [x] Runner eseguito sulla configurazione fissa (gemma2:9b, 3 prompt, 6 run totali)
- [x] Dump SRUM catturati (prep_before5.csv, prep_after5.csv, elevazione admin)
- [x] `s_EPI` estratto per fase (prep_output3.json, prep_output5.json)
- [x] Dispersione stimata (3 fasi valide: prep-r3, prep-r5, prep-r6)
- [x] `B_abs` e `B_rel` congelati (B_abs=0.6, B_rel=1.1, margine 20%)
- [x] Banda scritta nel piano della prova vera (prep_plan_frozen.json)
- [x] Banda committata (prep_plan_frozen.json, 2026-11-06)

## Risultati pre-pilota (2026-11-06)

| fase | durata (s) | n_min | s | s_EPI | d | r | bloccata |
|---|---|---|---|---|---|---|---|
| prep-r3 | 455 | 8 | 0.7678 | 0.2941 | 0.4737 | 0.8922 | no |
| prep-r5 | 446 | 6 | 0.7824 | 0.5300 | 0.2524 | 0.3847 | no |
| prep-r6 | 463 | 7 | 0.8346 | 0.4443 | 0.3903 | 0.6104 | no |

Tentativo scartato: prep-r4 (319 s, 4 minuti SRUM, `blocking=True`,
flag `meno_di_5_bucket,bucket_di_bordo:314` in `prep_output4.json`):
fase sotto i 5 bucket, esclusa dalla stima.

Dispersione osservata (3 repliche valide): d in [0.252, 0.474], r in [0.385, 0.892].
La variabilita e alta: conferma la necessita del pre-pilota prima di congelare la banda.

## Banda congelata (2026-11-06)

**B_abs = 0.6** (soglia assoluta su |d| = |s - s_EPI|)
**B_rel = 1.1** (soglia relativa su |r| = 2*|d|/(s + s_EPI))

Margine: 20% sopra il massimo osservato (max d=0.4737, max r=0.8922).
Basi: 3 repliche valide su configurazione fissa (gemma2:9b, 3 prompt, ~7 min/fase).

| statistica | d | r |
|---|---|---|
| min | 0.2524 | 0.3847 |
| mediana | 0.3903 | 0.6104 |
| max | 0.4737 | 0.8922 |
| range | 0.2213 | 0.5075 |

Piano con banda: experiment_results/prep_plan_frozen.json

## File esaminati

- `experiment_results/p6_6_banda_20261025.md` — analisi della banda
- `experiment_results/p6_6_congelamento_20261025.md` — stato del congelamento
- `experiment_results/protocollo_v4_20261024.md:2499-2609` — P6.6
- `s_epi_phase.py` — harness di estrazione
- `AGENTS.md` — regole vincolanti
