# P6.6 — Stato del congelamento al 25-10-2026

**Stato: non congelabile oggi.** Nessun run eseguito, nessun commit, nessuna
modifica al percorso energetico di produzione. Questo file elenca cosa il
protocollo ha gia' fissato, cosa manca e perche', con l'ancoraggio di ogni
affermazione. Non introduce decisioni: le tre che restano aperte sono #70
(banda), P5/#42 (schema e runner) e la scelta C/R, che dipende dalle prime due.

## 1. Gia' fissato da P6.6 (non si riapre)

Ancore: `protocollo_v4_20261024.md:2499-2609`.

* l'ancoraggio: la prova EPI e' la terza riga di P4.10, non l'anello 4 di P4.9
  (`:2501-2509`);
* `s = d_ollama / d_busy`, denominatore = tempo BUSY del sistema, non tempo
  totale dei core (`:2527-2535`);
* `s_EPI = sum(CPUEnergyConsumption(albero)) / sum(CPUEnergyConsumption(tutte
  le voci))`, albero per nome esatto (`:2537-2542`);
* stessa finestra per `s` e `s_EPI`, timestamp dei bordi registrati
  (`:2543-2547`);
* fase valida = finestra integra, `done_reason` atteso, nessun
  `engine_tree_changed`, nessuna esclusione non dichiarata (`:2548-2550`);
* `C` configurazioni e `R` repliche dichiarate prima del primo run (`:2552-2558`);
* banda in forma assoluta e relativa, fissata prima del primo run (`:2560-2567`);
* dentro banda = concordanza fra procedure, **non** "validata" (`:2569-2574`);
* `engine_tree_changed`: identita' `(pid, create_time)` ai due bordi; quando e'
  vero `direct_cpu_delta` non alimenta `s` (`:2576-2587`);
* l'harness e' analisi, non produzione, e si puo' scrivere prima che P5 chiuda
  (`:2589-2596`);
* niente PDH/WMI, niente promozione a `chain_status` (`:2598-2606`).

## 2. #70 — banda: bloccante A

Analisi completa in `p6_6_banda_20261025.md`. In sintesi: mancano (a) una
misura di ripetibilita' di `s_EPI`, (b) una quantificazione dell'errore di
bordo dei bucket da 60 s, (c) una frase che dica quale conclusione cambia se
`s` e `s_EPI` differiscono di `x`. Con queste tre assenze ogni soglia sarebbe
una convenzione. Alternative motivate: A metrologica, B prestito del 10%,
C pre-pilota di ripetibilita', D nessuna banda con emendamento.

**#70 resta aperto.** Nessuna soglia e' stata scritta qui o nell'harness.

## 3. P5 (#42) — bloccante B: cosa manca, verificato oggi nel codice

| requisito | fonte | stato al 25-10-2026 |
|---|---|---|
| lettura sincrona del contatore EMI ai bordi | P6.5, `:2419-2430` | **assente come lettura diretta al bordo**: `package_energy_exact_between` (`energy_session.py:2105`) chiama `emi_window_energy_j` (`:1209`), che prende i due bordi dal buffer cumulativo via `_emi_cum_at` (`:1264`, definizione `:1118`). Manca la IOCTL all'istante di bordo col suo timestamp; il buffer e' nominalmente a 0,05 s ma la cadenza misurata sotto carico e' 0,28-0,34 s (P4.6) |
| `Δt_W` dalla stessa coppia di letture | P6.5, `:2431-2438` | **assente**: `duration_s` e' `t_end - t_start` sull'orologio Python (`local_energy.py:225`) mentre l'energia viene dai bordi del buffer; `read_cpu_edge` (`energy_session.py:1808`) legge albero, `cpu_times` e busy in una chiamata, ma non il contatore EMI |
| livello di aggregazione dei token dichiarato | P6.5, `:2439-2454` | **parziale**: `prompt_eval_count` e' letto (`benchmark_unified.py:171`, `:219`) ma il CSV non porta `n_inferenze` ne' il livello nel nome del campo |
| matrice di disegno centrata/scalata, QR o SVD | P6.5, `:2455-2465` | **assente** (e' lato analisi, da scrivere nel runner) |
| nome del campo del settling post | P6.5, `:2466-2467` | **assente** |
| collocazione dei campi per punto | P6.5, `:2468-2472` | **assente** |
| `pre_range_w`, `dP`, `budget_base_j` | P6.5, `:2473-2479` | **assenti** da `CSV_COLUMNS` (`casualwatt_csv_export.py:17-127`) |
| `engine_tree_changed` | P6.5, `:2480-2490` | **calcolabile ma non esportato**: `worker_cpu_delta` restituisce `born`, `lost`, `reused_pids` (`worker_tree.py:178-210`) e il runner legge i due bordi (`benchmark_unified.py:780-795`), ma il CSV non ha la colonna ne' gli ingressi. La regola "quando e' vero `direct_cpu_delta` non alimenta `s`" **non e' applicata**: `local_energy.py:412-413` usa comunque il delta diretto, `:465-470` aggiunge solo una nota |
| `hull_margin_tok` come distanza perpendicolare dallo spigolo | P6.5, `:2491-2497` | **assente** |
| baseline per blocco: 3 x 30 s pre + 3 x 30 s post | P1.5 | **assente**: `benchmark_unified.py:721-727` calibra una volta sola se `idle_power_w is None`; `P_post` non viene raccolto |

Conseguenza: P5 non si chiude per decisione, si chiude per codice. Le voci sopra
richiedono modifiche al percorso di produzione, che in questa sessione non sono
state autorizzate e non sono state fatte.

## 4. #71 — harness: pronto per le parti offline, in attesa del runner

`s_epi_phase.py` (radice, non tracciato) fa tre cose e nient'altro:

* estrae i bucket da minuto da uno o piu' dump `powercfg /srumutil`, scarta i
  roll-up (> 70 s), deduplica per firma esatta e tiene le righe complementari;
* assegna i bucket alle fasi del piano solo se interamente contenuti nella
  finestra, dichiara i bucket di bordo e i minuti in cui l'albero non ha riga,
  e rifiuta il verdetto quando la finestra non e' integra;
* calcola `d = s - s_EPI` e `r = 2(s - s_EPI)/(s + s_EPI)`, e applica la banda
  **solo** se il piano la porta gia'; altrimenti `in_band = null`.

Test eseguiti oggi (nessun run, nessun `powercfg`, nessun accesso all'hardware):
`--selftest` con 56 controlli, piu' una prova end-to-end su un dump sintetico
(48 bucket, 1 duplicato scartato, una fase valida e una bloccata da
`done_reason`). Il file dichiara nel JSON le sorgenti con `sha256` e puo'
archiviare i dump grezzi (`--archive-dir`).

Cosa l'harness **non** puo' fare da solo: `engine_tree_changed` lo riceve dal
piano, non lo calcola; i timestamp di fase e `done_reason` li deve produrre il
runner; `s` la prende dai campi `d_ollama_s`/`d_busy_s` della riga. Per questo
l'esecuzione aspetta P5 (`:2589-2596`).

## 5. Cosa resta da congelare, e perche' non si congela oggi

1. **banda** `B_abs`, `B_rel`, forma relativa, regola per l'aggregato — #70.
2. **`C` e `R`** — dipendono dalla banda: `R` serve a stimare la dispersione
   entro configurazione, ma senza banda non si sa quante repliche siano
   necessarie a una decisione.
3. **durata della fase** — il minimo e' 5 bucket SRUM (~300 s) per la regola
   documentata (`srum_emi_cross.py:66-68`); una fase da 10 s come quelle di
   `experiment_additivity.py` non e' risolvibile da SRUM. La durata esatta non
   e' decidibile senza sapere quante fasi entrano in `R` repliche.
4. **criteri di esclusione** — la forma e' fissata (fase non valida -> esclusa
   con motivazione), l'elenco dei flag e' quello dell'harness; manca la
   decisione su cosa fare delle fasi con `bucket_di_bordo` quando sono molte.
5. **schema CSV e runner** — P5, tabella §3.
6. **analisi statistica** — min/mediana/max/range per configurazione (P4.12),
   niente deviazione standard; la regola di aggregato della banda e' parte di
   #70.

Congelare oggi 2-6 significherebbe congelare un piano che la banda puo'
invalidare, oppure scrivere soglie per riempire un vuoto. Non si fa.

## 6. Dentro la configurazione e fra configurazioni

Sono due numeri diversi e il protocollo lo dice (`:2552-2558`):

* **entro configurazione**: `R` repliche della stessa `(modello, num_predict,
  concorrenza)`. Con `R = 1` non esiste dispersione entro configurazione e non
  si puo' scrivere nulla sulla ripetibilita'; la terna `(min, mediana, max)`
  descrive le repliche, non stima una varianza (P4.12).
* **fra configurazioni**: `C` condizioni. La loro distribuzione dice quanto `d`
  dipende dalla condizione, non quanto e' preciso in una condizione. Una media
  su tutte le fasi mescola le due cose e non va pubblicata come precisione.

L'harness riporta gia' le due cose separate: `summary_by_config` per
configurazione e le righe per fase con `replica`.

## 7. Ordine minimo per arrivare al primo run

1. decidere #70 (pre-pilota C, oppure emendamento per D): richiede
   autorizzazione, perche' C esegue un run e D modifica il protocollo;
2. chiudere P5: modifiche di produzione autorizzate, poi pytest incollato;
3. congelare schema, runner, `C`, `R`, durate, esclusioni, analisi;
4. provare l'harness sui dump veri del runner;
5. eseguire solo il piano congelato, conservando anche gli esiti negativi.
