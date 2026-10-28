# P6.6 e P6.2 — preparazione al pilota: stato verificato al 2026-10-28

Data: 2026-10-28. Ambito: audit documentale e di codice. **Nessun run eseguito,
nessuna soglia fissata, nessuna formula cambiata, nessuna riga di codice di
produzione modificata, nessuna riga del protocollo toccata.** Questo file
classifica cio' che e' gia' definito, cio' che va deciso prima del pilota e
cio' che il pilota deve misurare. Dove una decisione manca, la nomina; non la
prende.

Fonti: protocollo P1-P5 congelato (`P6.2` `:2364-2383`, `P6.3` `:2384-2408`,
`P6.6` `:2547-2656`, `P2.9` `:830-873`), codice di `cwEnergyModular/`, e i tre
artefatti P6.6 del 25-10 (`p6_6_banda_20261025.md`,
`p6_6_congelamento_20261025.md`, `p6_6_prepilota_20261025.md`).

---

## 1. Gia' definito

Verificato oggi nel codice, non solo nel testo.

| requisito | fonte | stato in codice (2026-10-28) |
|---|---|---|
| il pilota gira con lo stesso runner della campagna | P6.2 `:2376-2379` | `benchmark_v4.py` e' l'unico runner v4; P2.9 non ha un harness proprio |
| ogni blocco esegue la sequenza di P1.5: settling, 3 pre, `m` richieste, 3 post | P6.2 `:2376-2382` | `calibrate_idle` fa 3 ripetizioni con mediana (`energy_session.py:1362-1370`); il blocco pretende esattamente 3 repliche pre e 3 post e altrimenti solleva (`benchmark_v4.py:1439-1443`, `:1616-1618`) |
| `m = 3` richieste per blocco | P3.13 | `M_REQUESTS = 3` (`benchmark_v4.py:81`) |
| `half_range_pre_w` e `budget_base_w` per blocco | P1.5-P1.7 | `block_baseline` (`benchmark_v4.py:685-759`); scritti nel riepilogo a `:1673`, `:1675-1677` |
| `budget_base_j`, `settle_pre_s`, `settle_post_s`, `negative_increment` | P1.6, F.4 | riepilogo a `:1681-1682`, `:1667-1668`, `:1689` |
| `E_act` firmata, mai troncata | F.2 `:904-908` | la riga porta sia `active_energy_j` (troncato) sia `active_energy_raw_j` (firmato) con `active_valid` (`local_energy.py:555-558`, `:563-567`); il CSV ha le tre colonne |
| `s = d_ollama / d_busy` con i campi dichiarati | P6.6 `:2575-2584` | `d_ollama_cpu_s` / `d_busy_s` (`local_energy.py:748-749`), `cpu_share_window_s` / `cpu_busy_capacity_cores` (`:637-638`), quota limitata a [0,1] (`:661`) |
| `engine_tree_changed` con le identita' `(pid, create_time)` e i suoi ingressi | P6.6 `:2624-2636`; P5 | `worker_cpu_delta` (`worker_tree.py:178-213`); flag a `benchmark_v4.py:1490`, `:1518`; `tree_identity_start/end`, `tree_born`, `tree_lost` nel CSV (`casualwatt_csv_export.py:134-135`) |
| `num_ctx = 8192` (prova C) | P2.9 `:843-845`; P2.7 | `NUM_CTX = 8192` (`benchmark_v4.py:82`) |
| `done_reason` registrato e classificato | P2.4; prova A di P2.9 `:835-838` | `termination_fields` (`benchmark_v4.py:563-641`), grezzo nel payload a `:525`, nota di riga a `:649-663` |

Due note su quest'ultima riga, perche' cambiano il significato della prova A:
`done_reason` **non e' piu' assente dal codice** — l'ancora di P2.11 che lo
dichiara tale e' superata (30 occorrenze in `cwEnergyModular/`). La prova A
resta un cancello, ma non e' piu' una verifica di esistenza del campo: e' la
verifica che **questa** versione di Ollama su **questo** host distingua i due
casi, e che `N_out_actual` saturi il tetto.

## 2. Da chiarire prima del pilota

Sono decisioni, non misure. Nessuna si puo' chiudere guardando i dati del
pilota senza cadere nell'adattamento della soglia al risultato.

**2.1 — I due valori della banda di P6.6 (`B_abs`, `B_rel`).** P6.6 `:2608-2615`
li dichiara l'unico valore aperto e impone di fissarli prima del primo run.
`p6_6_banda_20261025.md` conclude che **le evidenze non li giustificano
numericamente**: manca una misura di ripetibilita' di `s_EPI`, manca una
quantificazione dell'errore di bordo dei bucket da 60 s, e manca la frase del
protocollo su quale conclusione cambi. Le alternative documentate sono quattro:
banda metrologica dal solo pavimento di quantizzazione (A), trasferimento di
`err_rel <= 10%` (B, sconsigliata), pre-pilota di ripetibilita' (C), nessuna
banda con `d` e `r` solo descrittivi (D, richiede emendamento).
`p6_6_prepilota_20261025.md` §7 propone tre ancore concrete per C — A1
(`B_abs = q·budget_pred/E_active`, con `q` da dichiarare), A2 (`B_rel = 5%` per
la seconda cifra del J/token), A3 come solo tetto di sanita' — e §11 elenca le
decisioni A-H da ratificare. **Nessuna e' ratificata**, `#70` resta aperto: la
scelta e' dell'utente, e finche' non c'e' il pilota non parte con una banda
scelta a tavolino.

**2.2 — Regola di aggregazione della banda.** `|d_i| <= B_abs` e' una regola
per fase; il protocollo non dice come si aggrega ("10 fasi su 10 dentro banda"
e "8 su 10" sono affermazioni diverse, `p6_6_banda_20261025.md` §2). Va scritta
nel congelamento insieme ai valori.

**2.3 — Denominatore della forma relativa.** Il protocollo chiede "forma
assoluta e relativa" senza fissare il denominatore (`:2609-2611`). La
differenza relativa simmetrica `r = 2d/(s + s_EPI)` e' motivata in
`p6_6_banda_20261025.md` §2 ma non e' ratificata; `d/s_EPI` privilegerebbe EPI
come riferimento, che P4.10 e P6.6 escludono.

**2.4 — `engine_tree_changed`: esclusione o fallback.** P6.6 `:2631-2634`
lascia l'alternativa aperta: "la riga e' esclusa dal confronto **oppure** il suo
`s` viene dal fallback dichiarato". Il codice ha gia' scelto la prima:
con il flag vero la quota non si calcola, `cpu_time_share = 0.0`,
`cpu_time_share_valid = False` e la provenienza e'
`not-computed-tree-changed` (`local_energy.py:662-678`); il "fallback
dichiarato" e' un ramo distinto, `samples-fallback`, che vale quando il bordo
diretto non e' disponibile (`:685-688`). La scelta va **ratificata** — non e'
una modifica di codice, e' la registrazione di cosa il codice fa — e va estesa
dal livello riga al livello fase, perche' P6.6 confronta fasi.

**2.5 — Una tensione dentro P6.6, che il codice non crea ma eredita.**
`worker_cpu_delta` conta **tutto** il tempo CPU di un processo nato dentro la
finestra (`worker_tree.py:194-198`), e questa e' la contaminazione che P6.6
`:2626-2628` descrive. Il flag pero' e' definito a `:2630-2631` come "l'insieme
a `t_end` non e' un sovrainsieme di quello a `t_start`": un worker **nato**
lascia `t_end ⊇ t_start`, quindi la condizione e' falsa e il flag **non scatta**.
Il codice implementa la definizione alla lettera (`benchmark_v4.py:1490`,
`:1518`); il punto non e' che il codice sia sbagliato, e' che la prosa descrive
un rischio che la definizione esclude. Non si corregge il codice: si decide se
`tree_born` non vuoto e' anch'esso una ragione di esclusione dichiarata. La
decisione va presa prima, non dopo aver visto `s`.

**2.6 — `C` e `R`.** P6.6 `:2600-2607` impone di dichiararli prima del primo
run; oggi non sono dichiarati. Il pre-pilota propone `C = 3`, `R = 5`,
`T = 420 s` (§11, punto C): e' una proposta, non una decisione.

**2.7 — La regola che decide P1.7.** Il rinvio di P1.7 e' chiuso dai dati solo
se **prima** e' scritto quale confronto fra quadratura e somma aritmetica
decidera'. Il codice fa la quadratura (`benchmark_v4.py:746-757`) e la
documenta come provvisoria; P6.4 `:2447-2449` elenca gia' le tre grandezze che
la scelta muove (pesi, bootstrap, gate). Cambiarla dopo aver visto
`half_range_pre_w` sarebbe la stessa cosa che spostare una soglia.

**2.8 — Su quale campo si calcola `u_within,b`.** F.9/F.11 lo definiscono come
`semi-range(E_act,i)`, e `E_act` e' firmata e non troncata (F.2 `:908`). Nel
codice convivono due campi: `active_energy_j`, che la produzione **tronca a
zero** (`local_energy.py:556-558`), e `active_energy_raw_j`, che conserva il
segno. Il semi-range su valori troncati non e' il semi-range di `E_act`: con
`m = 3` basta una richiesta negativa per cambiare entrambi gli estremi. Va
dichiarato che `u_within,b` si calcola su `active_energy_raw_j`, con
`negative_increment` riportato.

**2.9 — Le finestre di baseline sono protette da un default, non da una
costante.** `config.IDLE_CALIBRATION_SECONDS` vale **10 s**
(`config.py:331`) e `calibrate_idle` alza la durata al floor di
`CW_IDLE_WINDOW_S`, default 30 s (`energy_session.py:1380-1389`). Con
`CW_IDLE_WINDOW_S` impostata a 10 le tre repliche tornano da 10 s, che sono le
finestre di v3 a cui il protocollo attribuisce l'assenza della terna
(`P6.2` `:2371-2373`). Il piano deve dichiarare l'ambiente del pilota —
entrambe le variabili non impostate — e registrarlo nell'artefatto; nessuna
riga di codice va cambiata.

**2.10 — `s_EPI` non e' misurabile nel pilota.** P6.6 richiede fasi da almeno
5 bucket SRUM (`srum_emi_cross.py:72-73`, ~300 s) e `powercfg /srumutil` ai
confini di fase (`:256`, `:317`). Una fase di P2.9 e' una singola richiesta:
per costruzione non ha risoluzione SRUM. Il confronto `s` contro `s_EPI` esce
quindi **solo** dal pre-pilota dedicato (fasi da `T = 420 s`,
`p6_6_prepilota_20261025.md` §4), non dal pilota P2.9. Confondere i due
produrrebbe un `d` dominato dal bordo del bucket.

## 3. Da misurare durante il pilota

| grandezza | da dove esce | cosa decide | cosa non decide |
|---|---|---|---|
| `half_range_pre_w`, una per blocco | tre repliche pre da 30 s, `block_baseline` | quale delle due forme di P1.7 regge sui dati (con la regola di 2.7) | non fissa `budget_base_w`: la forma si chiude prima della campagna |
| `u_within,b` per blocco di carico | semi-range di `active_energy_raw_j` sulle `m = 3` richieste | fornisce al primo `rho = u_base/u_within` il suo denominatore (`P6.4` `:2434-2439`) | non stima una varianza: resta un semi-range conservativo a `n = 3` |
| esito delle prove A, B, C di P2.9 | runner, non dataset | se la campagna parte (A) e la quantificazione descrittiva della cache (B) | non entra nel dataset (P2.9 `:832-833`) e non cambia P2.8 |
| quante fasi cadono per `engine_tree_changed`, `tree_born`, `worker_exit_in_window` | righe di richiesta | se il fallback di 2.4 e 2.5 e' utilizzabile in pratica | non e' una soglia: e' un conteggio |
| durata osservata delle finestre e stabilita' di `P_pre` | `settle_pre_s`, `pre_range_w`, `dP` | se l'audit idle di P6.3 ha descritto la macchina giusta | non chiude `#70`: la banda non si misura qui |

Il pilota **non** misura `s_EPI` (2.10), **non** arbitra la scala assoluta — che
resta non arbitrata senza il riferimento esterno W1 — e **non** produce nessuna
riga `validated`: l'anello 1 di P4.9 resta una precondizione e non un token.

## 4. Ancore da riallineare (riscontrate, non corrette qui)

Le citazioni di P6.6 e P2.11 puntano a posizioni che il codice ha superato. Non
le ho toccate: il protocollo e' congelato e il riallineamento va in un commit
dedicato, dopo aver verificato tutti i riferimenti alla stessa interfaccia.

| citazione | cosa dichiara | posizione reale al 2026-10-28 |
|---|---|---|
| P6.6 `:2580-2581` → `local_energy.py:342-355`, `casualwatt_csv_export.py:104-107` | campi di `s` (`d_ollama`, `d_busy`, finestra, capacita') | `local_energy.py:172-173`, `:748-749`, `:637-638`; `casualwatt_csv_export.py:84`, `:114` |
| P6.6 `:2625` e P6.5 `:2531` → `benchmark_unified.py:757` | lettura dei PID una volta per richiesta | `find_worker_tree` (`energy_session.py:814-824`); il log delle identita' e' a `benchmark_unified.py:808-822` |
| P6.6 `:2626` e P6.5 `:2530` → `local_energy.py:550-577` | `_read_ollama_cpu_times` ricorsivo | `:1160`; il delta per identita' e' in `worker_tree.py:178-213` |
| P6.6 `:2594-2595` → `srum.py:45-48`, `srum_emi_cross.py:49`, `:244` | flush ai confini di fase, mai nel tick | `srum.py:45-46` (testo); flush reale a `srum_emi_cross.py:256`, `:317`; `:49` e' la nota sull'elevazione, `:244` il controllo admin |
| P2.11 `:861` | "`done_reason` assente dal codice" | falso: 30 occorrenze, `benchmark_v4.py:525`, `:563-641` |
| P6.5 `:2524-2532` | P5 deve aggiungere `engine_tree_changed` come campo nuovo, perche' "non e' calcolabile dal codice attuale" | superato dal congelamento di P5 (2026-10-26): il campo esiste e ha i suoi ingressi (`casualwatt_csv_export.py:134-135`, `worker_tree.py:178-213`) |
| `p6_6_banda_20261025.md:79` | `read_cpu_edge` a `energy_session.py:1808-1823` | `:957`; il file ha 1800 righe, `:1808` non esiste |
| `p6_6_banda_20261025.md:81`, `:159` | regola dei 5 bucket a `srum_emi_cross.py:66-68` | `:72-73` |
| `p6_6_banda_20261025.md:166` | unita' millijoule a `srum.py:39-41` | `:42-44` |
| `p6_6_congelamento_20261025.md:47-48` | P5 assente: bordo sincrono, `Δt_W`, `n_inferenze` | superato dal congelamento di P5: il runner v4 ha `read_counter_edge`, `dt_W_s` dalla stessa coppia e `n_inferenze` |

L'ultima riga e' la piu' importante: `p6_6_congelamento_20261025.md` e' una
fotografia del 25-10 e le sue assenze non valgono piu'. Il documento resta
come provenienza storica e non si riscrive; non va citato come stato corrente.

## 5. Cosa serve perche' il pilota parta

Nell'ordine, senza salti:

1. ratifica delle decisioni 2.1-2.5 (banda, aggregazione, forma relativa,
   alternativa su `engine_tree_changed`, caso dei worker nati) e delle
   proposte `C`/`R` di 2.6;
2. la regola di decisione di 2.7 e la scelta di campo di 2.8, scritte prima;
3. l'ambiente dichiarato di 2.9 e il conteggio delle fasi di 3;
4. audit idle di P6.3 (30 minuti, `pre_range_w <= 1,0 W`) — precede sia il
   pilota sia la campagna;
5. autorizzazione esplicita all'esecuzione.

Nessuno di questi cinque passi e' stato compiuto in questo turno.
