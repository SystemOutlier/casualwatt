# P6.6 — Pre-pilota di ripetibilità (Option C)

Data: 2026-11-06. **Stato: decisione adottata, pre-pilota da eseguire.**

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
- [ ] Piano JSON del pre-pilota preparato
- [ ] Runner eseguito sulla configurazione fissa
- [ ] Dump SRUM catturati
- [ ] `s_EPI` estratto per fase
- [ ] Dispersione stimata
- [ ] `B_abs` e `B_rel` congelati
- [ ] Banda scritta nel piano della prova vera
- [ ] Banda committata

## File esaminati

- `experiment_results/p6_6_banda_20261025.md` — analisi della banda
- `experiment_results/p6_6_congelamento_20261025.md` — stato del congelamento
- `experiment_results/protocollo_v4_20261024.md:2499-2609` — P6.6
- `s_epi_phase.py` — harness di estrazione
- `AGENTS.md` — regole vincolanti
