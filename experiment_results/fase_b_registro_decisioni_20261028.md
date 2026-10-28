# Fase B — registro delle decisioni da approvare prima del pilota

Data: 2026-10-28. **Stato: registro, nessuna decisione presa, nessuna soglia
fissata, nessuna formula cambiata, nessuna riga di codice o di protocollo
modificata, nessun run eseguito.** Ogni voce propone una decisione e ne dichiara
le alternative; la scelta resta dell'utente.

Le ancore sono state rilette il 2026-10-28 sui file in disco. I commit e gli
artefatti citati come provenienza (per esempio `p6_6_banda_20261025.md`) non
sono stati rieseguiti in questo turno: valgono come documenti tracciati, non
come misure ripetute oggi.

---

## 0. Come si legge il registro

Ogni voce `R*` ha sei campi, nell'ordine chiesto:

1. **riferimento** preciso alla specifica (file:riga) e agli artefatti;
2. **alternative ammesse** dalla documentazione, non inventate qui;
3. **conseguenze** su formule, dati e criteri di validazione;
4. **decisione da approvare** — una proposta, con la ragione;
5. **test richiesti** per verificarne l'implementazione;
6. **stato**: `aperto` (nessuna decisione ratificata), `deciso` (ratificato nel
   protocollo o in un'emenda, non in codice), `implementato` (in codice, senza
   un test che ne fissi la proprieta'), `verificato` (in codice con test).

Due stati intermedi sono usati dove la realta' non e' a un solo strato:
`implementato (riga) / aperto (fase)` e `deciso, non allineato` (la decisione
c'e', ma un altro punto del protocollo dice ancora il contrario).

Le proposte non sono decisioni. Il protocollo resta l'unica fonte: se una
proposta lo contraddice, si emenda il protocollo, non si applica la proposta.

Base di partenza per i test: `pytest cwEnergyModular` → 526 raccolti,
523 passati, 3 saltati (`AGENTS.md`, verificato 2026-10-28). Ogni campo o test
nuovo si aggiunge a quella suite e l'output va incollato per intero.

---

## 1. Indice

| id | oggetto | spec | stato | blocca |
|---|---|---|---|---|
| R1 | P6.6: banda assoluta `B_abs` | P6.6 `:2608-2615`, `:2657-2658` | aperto | il run confermativo P6.6, non il pilota P2.9 |
| R2 | P6.6: forma relativa e denominatore | P6.6 `:2609-2611` | aperto | come R1 |
| R3 | P6.6: regola di aggregazione | P6.6 `:2600-2615` | aperto | come R1 |
| R4 | P6.6: `C`, `R`, `T` | P6.6 `:2600-2606` | aperto | il pre-pilota P6.6 |
| R5 | `engine_tree_changed`: esclusione o fallback, a livello fase | P6.6 `:2596-2598`, `:2624-2635` | implementato (riga) / aperto (fase) | il pre-pilota P6.6 |
| R6 | worker nati: `tree_born` | P6.6 `:2624-2630` | aperto | il pre-pilota P6.6 |
| R7 | `u_within`: produttore, campo, blocchi invalidi | P3.8 `:1063-1068`; P6.2 `:2376-2382` | aperto | il pilota P2.9 (P6.2 lo richiede) |
| R8 | ammissibilita' dei blocchi per il fit | P1.6 `:251-278`; P3.8 `:1048-1052` | deciso; implementato solo il guasto tecnico | il pilota, per l'analisi |
| R9 | regola di chiusura di P1.7 | P1.7 `:359-371`; P1.13 `:516-523` | deciso (Emenda 8), non allineato | si', prima della campagna |
| R10 | ambiente dichiarato (`CW_IDLE_WINDOW_S`) | P1.3 `:193-205` | aperto | si', il pilota |
| R11 | emendamento P5: `baseline_backend` | P1.3 `:203-205` | aperto | il pilota, per P1.3 |
| R12 | emendamento P5: token D11 | spec metodi `:1186-1199` | aperto | no (il pilota non usa G0) |
| R13 | guardia `CW_ENERGY_FILE` in `calibrate_idle` | P1.3; P5 | aperto, non bloccante | no |

L'ordine segue quello richiesto: P6.6 (R1-R6), poi `u_within` e ammissibilita'
(R7-R8), poi P1.7 (R9), poi gli emendamenti P5 (R10-R12). R13 e' un residuo
della Fase A registrato qui perche' e' una decisione, non un difetto.

---

## 2. P6.6 — la prova di attribuzione

Il testo e' esplicito su cosa non e' in discussione: le tre grandezze
(`:2559-2566`), la definizione di `s` e `s_EPI` (`:2573-2595`), la fase valida
(`:2596-2598`), il ruolo di `E_worker` come limite inferiore, l'esclusione da
`chain_status` (`:2646-2655`). **L'unico valore aperto e' la banda numerica**
(`:2657-2658`): "Tutto il resto e' fissato qui e non si sposta dopo i dati."

### R1 — `B_abs`, la banda assoluta

**Riferimento.** P6.6 `:2608-2615` (banda fissata prima del primo run, in forma
assoluta e relativa, non scelta dopo aver visto `d`); `:2657-2658`;
`p6_6_banda_20261025.md` §3-§6; `p6_6_prepilota_20261025.md` §7, §11 (A, B);
`p6_preparazione_pilota_20261028.md` §2.1. Issue `#70` aperta.

**Alternative ammesse.** Quattro, tutte scritte in `p6_6_banda_20261025.md` §6:

- **A — pavimento metrologico**: `B_abs ~ 5e-4`, dai 0,0156 s del tick dei
  `cpu_times`. E' l'unico numero derivabile da un dato documentato, ma misura
  solo il lato `s` e ignora il bucket SRUM da 60 s: una differenza osservata
  di 0,0022 sarebbe fuori banda per costruzione. Coerente solo se il confronto
  fosse fra due letture dello stesso orologio, che non e' il caso.
- **B — trasferire `err_rel <= 10%`** dell'anello 6. Riguarda l'errore di
  predizione, non l'attribuzione; richiede di dichiarare equivalenti due
  grandezze con decisioni diverse. Sconsigliata dallo stesso documento.
- **C — pre-pilota di ripetibilita'** (raccomandata se autorizzato), con tre
  ancore proposte in `p6_6_prepilota_20261025.md` §7: **A1**
  `B_abs = q · budget_pred / E_active` con `q = 1/3`; **A2** `B_rel = 5%` per la
  seconda cifra del J/token; **A3** `B_abs = 1 − s_med` solo come tetto di
  sanita'. Richiede un emendamento: la banda nascerebbe dopo un run di
  calibrazione, non "prima del primo run" in senso assoluto.
- **D — nessuna banda numerica**: `d` e `r` solo descrittivi. Coerente con i
  dati esistenti, ma contraddice `:2610-2611` e richiede un emendamento
  esplicito.

**Conseguenze.** A e B classificano fasi con un numero che non e' ancorato a
nulla: e' il caso che `p6_6_banda_20261025.md` §5 dichiara inaccettabile. C
sostituisce l'assenza con una misura, ma costa un run e un emendamento; con A1
la banda dipende da `budget_pred`, che esce dal pilota P6.2, quindi l'ordine
diventa pilota → ancora → run confermativo, non "tutto prima del pilota". Con A2
la banda e' disponibile subito, ma e' una convenzione dichiarata. D rende P6.6
descrittivo: la terza riga di P4.10 resta una prova, ma non classifica. In
nessuno dei quattro casi la banda entra in `chain_status` (`:2652-2653`) o
arbitra la scala assoluta.

**Decisione da approvare.** Una sola, per iscritto, con formula e numero:
(i) C+A1, con autorizzazione del pre-pilota e l'emendamento di §1 di
`p6_6_prepilota_20261025.md`; (ii) C+A2, se si autorizza il pre-pilota ma non si
vuole dipendere da `budget_pred`; (iii) D, se non si autorizza alcun run.
La proposta e' **(iii) D adesso, con C+A1 come percorso se e solo se un
pre-pilota viene autorizzato**: D e' l'unica affermazione vera oggi, e' reversibile
con un emendamento, e non richiede di scegliere un numero prima di avere una
misura di ripetibilita'. A e B restano scritte come alternative scartate, con la
ragione.

**Test richiesti.** Nessun codice di produzione. L'harness P6.6 deve:
leggere `B_abs`/`B_rel` solo da un piano committato, senza valore di default, e
rifiutarsi se manca; calcolare `in_band` come `|d| <= B_abs` **e**
`|r| <= B_rel`, riportando sempre `d` e `r`; se si adotta D, non emettere
`in_band` e non avere alcun percorso che scriva `concordanza` o `validated`; un
test che i campi P6.6 non cambiano `chain_status` (`validation_chain.py` non li
legge: oggi vero, va fissato).

**Stato.** `aperto`.

### R2 — `B_rel` e il denominatore della forma relativa

**Riferimento.** P6.6 `:2609-2611` chiede "forma assoluta e relativa" senza
fissare il denominatore; `p6_6_banda_20261025.md` §2; `p6_preparazione_pilota_20261028.md`
§2.3.

**Alternative ammesse.** Tre letture sono possibili, e due sono documentate:
`r = 2d/(s + s_EPI)` (differenza relativa simmetrica, proposta in
`p6_6_banda_20261025.md` §2); `d/s_EPI` (EPI come riferimento); `d/s`
(specchio della precedente, non discussa nei documenti ma ammessa dalla forma
"relativa"). La quarta opzione e' non avere forma relativa, che coincide con D
di R1.

**Conseguenze.** `d/s_EPI` privilegia EPI come riferimento, mentre P4.10
(`:2570-2571`) e P6.6 (`:2566-2571`) dicono che EPI e' un'altra attribuzione,
non una verita': con quella forma ogni errore di EPI diventerebbe "errore di
`s`" per costruzione. La forma simmetrica e' limitata (`|r| <= 2` per valori non
negativi), antisimmetrica e definita quando `s + s_EPI > 0`, che in una fase
valida e' sempre vero; il denominatore nullo diventa un criterio di invalidita'
dichiarato, non un infinito. Con valori vicini (l'unica osservazione esistente:
0,7339 contro 0,7361) le tre forme danno numeri quasi identici; divergono quando
le due procedure divergono, ed e' esattamente il caso che la banda deve
classificare.

**Decisione da approvare.** Adottare `r = 2d/(s + s_EPI)`, chiamarla "differenza
relativa simmetrica" (non "errore relativo"), richiedere `s + s_EPI > 0` come
condizione di fase valida, e registrare `s` e `s_EPI` in modo che `r` sia
ricalcolabile. Se si preferisce EPI come riferimento, va dichiarato che EPI e'
il riferimento — il che contraddice P4.10 e P6.6 — e quindi non e' la proposta.

**Test richiesti.** `r(a,b) = -r(b,a)`; `|r| <= 2` su coppie non negative;
denominatore nullo → token di esclusione, non eccezione numerica; `d` e `r`
arrotondati a 6 decimali come gli altri campi derivati; test che la riga di fase
porta entrambi i valori, cosi' `r` non e' ricostruibile solo dal rapporto.

**Stato.** `aperto`.

### R3 — regola di aggregazione

**Riferimento.** P6.6 `:2600-2606` (distribuzione per configurazione, non solo
media complessiva); `:2608` (per ogni fase valida si calcola `d`);
`p6_6_banda_20261025.md` §2; `p6_preparazione_pilota_20261028.md` §2.2;
`p6_6_prepilota_20261025.md` §3.

**Alternative ammesse.** (i) solo per fase, nessun verdetto; (ii) verdetto di
configurazione **congiuntivo** (tutte le fasi valide dentro banda); (iii)
frazione `k/n` come verdetto; (iv) aggregato descrittivo a rapporto delle somme
`d_agg`; (v) media o mediana di `d_i`. Il protocollo non dice quale; il
documento del 25-10 dimostra che "10 fasi su 10" e "8 su 10" sono affermazioni
diverse e nessuna e' implicita in `|d_i| <= B_abs`.

**Conseguenze.** Con `R = 5` il verdetto congiuntivo fa cadere una
configurazione per una sola fase fuori banda: e' severo, e con `R = 5` e'
l'unico che non richiede una soglia nuova. `k/n` e' un conteggio, non una
percentuale stimabile a 5 repliche. La media dei rapporti e' dominata dalle fasi
con denominatore piccolo; la mediana scarta la magnitudine. `d_agg` a rapporto
delle somme e' l'unico aggregato che pesa le fasi per il lavoro svolto e
risponde a "sull'intera configurazione le due procedure allocano la stessa
frazione?", ma puo' stare in banda mentre una fase singola ne e' fuori: se
sostituisse il verdetto, diluirebbe il caso che si vuole vedere.

**Decisione da approvare.** Tre livelli, come in
`p6_6_prepilota_20261025.md` §3: la fase valida e' l'unita' di osservazione;
il verdetto di configurazione e' congiuntivo; si riporta `k/n` (conteggio);
`d_agg` e `r_agg` sono descrittivi e **non** possono raddrizzare una fase fuori
banda; le fasi di sensibilita' al bordo si riportano a parte e non entrano ne'
nel verdetto ne' in `d_agg`.

**Test richiesti.** Configurazione 4/5 dentro banda → non in concordanza e
`k/n = 4/5`; `d_agg = Σ d_ollama / Σ d_busy` su un fixture numerico in cui
differisce dalla media di `d_i`; test che `d_agg` non puo' impostare `in_band`
per una fase esterna; test che le fasi di sensibilita' non alterano ne'
verdetto ne' `d_agg`.

**Stato.** `aperto`.

### R4 — `C`, `R` e durata di fase

**Riferimento.** P6.6 `:2600-2606`: `C` configurazioni e `R` repliche si
dichiarano **prima del primo run**; "`C = 10` con `R = 1` produce dieci numeri
e nessuna stima della variabilita' entro configurazione". Proposta
`C = 3`, `R = 5`, `T = 420 s` in `p6_6_prepilota_20261025.md` §4 e §11 (C);
`p6_preparazione_pilota_20261028.md` §2.6.

**Alternative ammesse.** Qualunque coppia dichiarata prima del run; il testo
esclude solo `R = 1` come copertura di condizioni senza stima di variabilita'.
`R = 3` e' ammesso ma il range sarebbe deciso da una sola fase anomala;
`C = 3` distingue la variabilita' della procedura da quella del carico. `T` non
e' una soglia: e' la durata che garantisce almeno 5 bucket SRUM interni
(`p6_6_prepilota_20261025.md` §5.5: con `T = 420 s` restano 6 minuti su 7,
misurato).

**Conseguenze.** `C` e `R` fissano `n` e se esiste una dispersione; `T` fissa la
risoluzione di `s_EPI`; insieme fissano il costo (≈ 2 h 30 min di carico, ≈ 3 h
con il margine H). Cambiarli dopo aver visto `d` sarebbe la stessa cosa che
spostare una soglia. **P6.6 non e' il pilota P2.9**: una fase di P2.9 e' una
singola richiesta e non ha risoluzione SRUM (`p6_preparazione_pilota_20261028.md`
§2.10), quindi `C`, `R`, `T` valgono per il pre-pilota dedicato.

**Decisione da approvare.** `C = 3`, `R = 5`, `T = 420 s`, una fase invalida
tollerata per configurazione (minimo 4 valide), le tre configurazioni di §4
(`cfg_breve` 32 token, `cfg_lungo` 256, `cfg_conc` 2 richieste in volo), modello
residente dichiarato con `model_digest` e `ollama_version`; piu' le due scelte di
disegno che non sono soglie: G (bucket di bordo escluso e dichiarato, non
bloccante) e H (60 s di carico oltre i due bordi, +30 min). I valori si scrivono
nel piano del pre-pilota e si committano prima dell'esecuzione.

**Test richiesti.** Nessun test di produzione. Validazione del piano: rifiuto se
`C`, `R`, `T` o la banda mancano; numero di fasi per configurazione uguale a `R`;
fasi di sensibilita' escluse dal verdetto; `study: "p6_6_prepilot"` presente in
ogni artefatto, cosi' i dati non si uniscono a quelli della campagna.

**Stato.** `aperto`.

### R5 — `engine_tree_changed`: esclusione o fallback, a livello fase

**Riferimento.** P6.6 `:2596-2598` (una fase valida non ha
`engine_tree_changed`); `:2624-2635` (quando il flag e' vero, "la riga e'
esclusa dal confronto **oppure** il suo `s` viene dal fallback dichiarato");
P6.5 `:2528-2538`; codice `local_energy.py:662-678` (esclusione),
`:685-688` (`samples-fallback`, ramo distinto); `benchmark_v4.py:1490`,
`:1518`; CSV `:134-135`. Contesto in `p6_preparazione_pilota_20261028.md` §2.4.

**Alternative ammesse.** (a) escludere la riga/la fase dal confronto;
(b) usare il fallback dichiarato per `s`, con la provenienza nella riga;
(c) entrambe, a seconda della disponibilita' del bordo diretto. Il protocollo
lascia aperto (a) contro (b); il codice ha gia' scelto (a) **a livello riga** e
tiene (b) per una condizione diversa (bordo diretto non disponibile).

**Conseguenze.** (a) riduce `n` e non mescola procedure: un `d` calcolato su
fonti diverse non e' piu' il confronto fra le stesse due grandezze. (b) conserva
`n` ma cambia la definizione di `s`; se usata, ogni `d` deve portare la fonte e
`d` non si aggrega fra fonti diverse. Poiche' P6.6 confronta **fasi**, la regola
va alzata di livello: una sola riga con il flag rende la fase non valida,
altrimenti la quota della fase mescolerebbe un valore escluso e uno no.

**Decisione da approvare.** Ratificare (a) — e' cio' che il codice gia' fa — ed
estenderla alla fase: `engine_tree_changed = true` su almeno una riga →
fase esclusa dal confronto, con motivo registrato; `samples-fallback` resta cio'
che e' (bordo diretto assente) e **non** e' il fallback di P6.6; se i due casi
coincidono, vince l'esclusione. La provenienza della quota
(`direct-edge | samples-fallback | not-observable | not-computed-tree-changed`,
`local_energy.py:666`, `:684-688`) resta nella riga.

**Test richiesti.** A livello riga esistono gia' (quota non calcolata, fonte
`not-computed-tree-changed`, `cpu_time_share_valid = False`). Da aggiungere:
fase con una riga marcata → esclusa con motivo; fase interamente da
`samples-fallback` → etichettata e riportata a parte, non aggregata con
`direct-edge`; nessuna fase esclusa senza motivo scritto.

**Stato.** `implementato (riga) / aperto (fase)`.

### R6 — worker nati: `tree_born`

**Riferimento.** P6.6 `:2624-2630`: la prosa descrive la contaminazione ("un
worker che nasce durante la finestra e' catturato a `t_end` con tutto il suo
tempo CPU"), ma la definizione del flag e' "l'insieme a `t_end` non e' un
sovrainsieme di quello a `t_start`", che un worker nato **non** soddisfa;
`worker_tree.py:194-198` conta il tempo del nato da zero; `benchmark_v4.py:1491`,
`:1521`; CSV `tree_born` `:135`. Analisi in
`p6_preparazione_pilota_20261028.md` §2.5.

**Alternative ammesse.** (i) definizione alla lettera: il nato non alza il flag,
si riporta `tree_born` a parte; (ii) `tree_born` non vuoto e' ragione di
esclusione; (iii) esclusione solo sopra una soglia di tempo CPU del nato — ma e'
una soglia nuova, e le soglie si congelano prima dei dati, quindi e' esclusa
come via praticabile in questo turno.

**Conseguenze.** (ii) cambia il significato di "fase valida" e riduce `n`; ha
pero' un costo reale: con `keep_alive = -1` l'albero e' residente, quindi una
nascita e' di solito un riavvio, cioe' il rischio che la prosa descrive. (i)
lascia la contaminazione visibile ma non corretta, e la sua grandezza non e'
misurata: il tempo del nato entra intero in `d_ollama` e non in `d_busy` della
stessa porzione. Nessuna delle due e' "sbagliata": la prima rispetta la
definizione congelata, la seconda rispetta l'intenzione della prosa.

**Decisione da approvare.** (i), con due obblighi dichiarati: riportare
`tree_born` per fase e, dove calcolabile, la quota di tempo CPU dei nati come
**diagnostica, non soglia**; e ripetere il confronto **senza** le fasi con nati
come sensibilita' dichiarata, preregistrata insieme a `C`/`R`. Se il pre-pilota
mostra nati in una frazione non banale delle fasi, il numero si riporta e la
lettura cambia — ma non si sposta la definizione del flag dopo aver visto `s`.

**Test richiesti.** Fase con soli nati → valida, etichettata, e presente
nell'arm di sensibilita'; fase con persi → esclusa; fase con entrambi → esclusa;
test che il flag resta falso quando `t_end ⊇ t_start` (definizione letterale,
gia' implicita nel codice).

**Stato.** `aperto`.

---

## 3. `u_within` e ammissibilita' dei blocchi

### R7 — `u_within`: produttore, campo, unita', blocchi invalidi

**Riferimento.** P3.8 `:1063-1068` (`u_within,b = semi-range(E_act,i)`, "non
diviso per `√m`"); P4.6 `:1658-1662` (`budget_fit_b² = u_base,b² + u_within,b²`),
scala in joule **sulla scala di `Ē_b`** `:1675-1686`; F.9/F.11 `:2925-2935`;
P6.2 `:2376-2382` (il pilota deve produrlo: "e' il denominatore del primo `ρ`
misurato"); P6.4 `:2434-2439`; P3.8 `:1070-1071` (`budget_b = 0` → peso uguale e
blocco marcato). Schema: `BLOCK_SUMMARY_COLUMNS`
(`casualwatt_csv_export.py:208-223`) **non ha il campo**; ha
`budget_fit_j` (`:215`), che il runner lascia vuoto (`benchmark_v4.py:1684`).
Righe: `active_energy_raw_j` (`:119`), `active_valid`, `block_id` (`:151`).
Analisi in `p6_preparazione_pilota_20261028.md` §2.8.

**Cosa e' deciso e cosa no.** La formula e' congelata; il **produttore** no.
Verificato oggi con grep su `cwEnergyModular/` e sulla radice: `u_within` compare
solo nella docstring di `block_baseline` (`benchmark_v4.py:712`) e nella sonda
**simulata** `semi_range_concentrazione_pesi_probe.py` (`:61`: "non una misura,
perche' `u_within` non e' mai stato misurato su un blocco v4"). Nessun percorso
lo calcola.

**Definizione da fissare** (formula, unita', livello, campo):

```
u_within,b = ( max_i E_act,i − min_i E_act,i ) / 2     i sulle richieste VALIDE del blocco
E_act,i    = active_energy_raw_j                       # firmata, F.2: mai troncata
unita'     = joule, sulla scala di E_bar_b             # non sul totale di blocco
livello    = blocco; NON diviso per sqrt(m), NON per punto
campo      = assente oggi in BLOCK_SUMMARY_COLUMNS
```

Il campo troncato `active_energy_j` non e' utilizzabile: con `m = 3` una sola
richiesta negativa cambia un estremo e quindi il semi-range (e' il difetto che
`p6_preparazione_pilota_20261028.md` §2.8 registra). Si usa il grezzo firmato.

**Alternative per il produttore.**

- **(a) runner**: calcola e scrive `u_within_j` nel riepilogo di blocco. Richiede
  emendamento P5 (36 → 37 colonne) e codice nel runner. Difetto: il riepilogo di
  un blocco invalidato deve avere le celle di misura **vuote** (Emenda 8
  `:3451-3461`), quindi il runner dovrebbe decidere, prima dell'analisi, se
  `u_within` e' "misura" o "derivato": due regole per lo stesso file.
- **(b) analisi**: deriva dalle righe con join su `block_id`, dopo
  `partition_block_rows`. Nessun cambiamento di schema ne' di runner; si
  ricostruisce dagli artefatti gia' registrati; il numero pero' non e' nel
  riepilogo, e chi legge il solo `block_summary.csv` non lo vede.
- **(c) entrambi**: il runner lo scrive e l'analisi lo ricalcola, con un test di
  uguaglianza. Massima tracciabilita', costo di un campo e di un test;
  richiede comunque l'emendamento.

**Conseguenze.** (a) mette nel runner una grandezza di analisi il cui valore
dipende dalla selezione delle righe valide, che oggi e' un gate separato
(`partition_block_rows`, `benchmark_v4.py:260-417`, test in
`tests/test_filtro_p6_invalidati.py`): due punti che devono restare d'accordo.
(b) lascia un solo punto di calcolo, ma va scritto e committato, e deve chiamare
il gate o includera' righe escluse. (c) rende la divergenza un test invece di un
sospetto.

**Decisione da approvare.** (b) come primo passo — nessuno schema, nessun
runner, funzione di analisi committata e testata — e poi, **nello stesso
emendamento P5 che aggiunge `baseline_backend` (R11)**, accodare `u_within_j` e
aggiungere il test di uguaglianza, cioe' passare a (c). Se si preferisce un solo
passo, (c) subito, accettando che il runner si tocchi solo dopo l'emendamento.

**Livello e blocchi invalidi.** Livello: blocco. `ρ = u_base/u_within` si
calcola per blocco e si riporta come distribuzione (P6.4), mai come tabella a
una cifra. Regole:

1. blocco con `invalid_reason` non vuota → escluso, `u_within` vuoto, righe non
   usate (il gate lo fa gia': `benchmark_v4.py:367-417`);
2. `m_valide = 3` per il fit primario; `m_valide = 2` → `u_within` calcolabile ma
   il blocco va in sensibilita' con il conteggio dichiarato; `m_valide < 2` →
   vuoto (un semi-range su un punto non esiste);
3. `budget_fit_b = 0` (entrambi i termini nulli) → peso uguale e blocco marcato
   (P3.8 `:1070-1071`); il marcatore e' leggibile da `budget_fit_j == 0`, senza
   un campo nuovo;
4. se scritto nel riepilogo, 6 decimali come gli altri campi; in analisi, piena
   precisione fino al confronto.

**Test richiesti.** Tre righe sintetiche con valori noti (es. 10,0 / 12,0 / 9,0 J
→ 1,5 J); un caso con una richiesta negativa (es. −2 / 1 / 3 J): semi-range sul
grezzo 2,5 J, sul troncato 1,5 J, e il test deve esigere il grezzo; tutte uguali
→ `0`, non vuoto; due valide → token di sensibilita'; blocco invalido → vuoto;
join per `block_id` con righe in ordine sparso; nessuna divisione per `√m`
(confronto numerico con il valore diviso, che deve differire); uguaglianza con
`hypot(u_base, u_within)`; test che il campo **non** e' nello schema finche'
l'emendamento non c'e', cosi' l'aggiunta e' deliberata e non silenziosa.

**Stato.** `aperto` (formula decisa, produttore assente).

### R8 — ammissibilita' dei blocchi: guasti tecnici contro flag di qualita'

**Riferimento.** P1.6 `:251-278` (soglie 1,0 W, 10%, 5/20%); Emenda 8
`:3415-3461` (sostituzione del blocco, `invalid_reason`,
`block_attempt`, `K` senza default); P4.5 `:1509-1572` (filtro dei controlli
`pre_range_w,c <= 1,0 W` e `|dP_c| <= 1,0 W`, quorum `⌈2/3·n⌉ = 4`); P3.8
`:1048-1052` (r_B 10-20% nel fit con peso ridotto, oltre 20% in sensibilita').
Codice: `partition_block_rows` (`benchmark_v4.py:260-417`) con i suoi test
(`tests/test_filtro_p6_invalidati.py`); `validation_chain.py:121`, `:128`,
`:242`; il runner lascia **vuoti** `r_A` e `r_B` (`benchmark_v4.py:1692`).

**Cosa e' deciso.** Guasto tecnico del contatore → blocco invalidato alla prima
occorrenza, sostituito una volta, `K` letto da config senza default, righe
conservate con nota. Flag di qualita' (`pre_unstable`, `pre_range_w`, drift):
**non** generano sostituzione (Emenda 8 punto 5). `r_A > 10%` → `baseline_unstable`,
due blocchi su tre → campagna invalida; `r_B` 10-20% → mantenuto, marcato, peso
ridotto, oltre 20% → escluso dal fit primario e in sensibilita'; oltre il 5% di
richieste negative in un punto → punto marcato; denominatore nullo → invalido
per costruzione. Sui blocchi di controllo `r_A` e `r_B` **non** si usano (non
hanno denominatore, P4.5 `:1512-1519`).

**Cosa e' implementato.** Solo il guasto tecnico e le sue cinque regole
(`partition_block_rows`, con test). `chain_status` legge
`negative_increment` e `baseline_unstable`, ma `r_A` arriva vuoto dal runner:
oggi l'anello 1 di P4.9 non e' calcolabile dai soli artefatti del run. Nessun
codice applica al fit `r_B`, il peso ridotto o l'esclusione del punto.

**Alternative.** (a) un solo modulo di analisi che calcola `r_A`, `r_B`,
`negative_increment` dalle righe, chiama `partition_block_rows` e restituisce
tre liste — primaria, sensibilita', esclusa — con i motivi; (b) calcolare i flag
dentro il codice del fit (soglie sparse in piu' punti); (c) farli calcolare al
runner (impraticabile per `r_B`, che richiede il punto completo, e contrario a
P5, che li dichiara campi di analisi).

**Conseguenze.** (a) da' un punto unico da cui passano `u_within`, i pesi e il
fit; rende i flag verificabili da un terzo; non introduce soglie. (b) e'
esattamente il modo in cui un flag diventa un'affermazione non verificabile.
(c) sposta nel runner una decisione che dipende dal punto e non dal blocco.

**Decisione da approvare.** (a): un modulo di analisi, soglie lette da costanti
gia' congelate (non da config), che sia l'unica fonte di `valid_rows` per
`u_within`, per i pesi e per il fit; `partition_block_rows` resta il gate
sull'invalidazione tecnica e non si duplica.

**Test richiesti.** Confini esatti: `r_A = 10%` passa e `10% + 1e-6` no (gia'
in `tests/test_chain_status.py:134-135`); `r_B` a 10%, 20%, 20% + 1e-6; 5%
esatto di richieste negative; `|dP_c| = 1,0 W` incluso; due blocchi su tre
`baseline_unstable` → campagna invalida; un controllo con `r_A` assente non
fallisce; quorum 4 su 6 coppie; blocco invalidato nella post-calibrazione →
righe presenti, escluse, con motivo; nessuna lista di esclusi senza motivo.

**Stato.** `deciso` nel protocollo; `implementato` solo il guasto tecnico; il
gate di qualita' per il fit e' `aperto` come codice.

---

## 4. P1.7 e il contratto dei dati

### R9 — regola di chiusura di P1.7

**Riferimento.** P1.7 `:335-375`, in particolare la "Decisione rinviata,
motivata" `:359-371` ("Dopo il pilota di P2.9 ... si decide se mantenerla o
introdurne una diversa"); P1.13 `:518-523` ("e' aperta la sua interpretazione, e
va chiusa prima della campagna principale"); riga P1 della tabella di stato
(`:11`), che ripete il rinvio; Emenda 8 `:3478-3504`; F.11 `:1719-1723` (la
forma esterna di `budget_pred` "resta provvisoria insieme a quella di
`budget_base_w` ... le due decisioni vanno chiuse insieme"); P6.4 `:2447-2449`.
Artefatto: `p1_7_forma_budget_base_20261028.md` §5 (D1, D2, D3).

**Il fatto testuale.** L'Emenda 8 ha **deciso**: "La decisione operativa
provvisoria di P1.7 e' chiusa in questa direzione", la quadratura resta, la
somma aritmetica "non e' adottata", e il pilota "descrive ... non decide la forma
di combinazione" (`:3480-3499`). Ma non ha registrato **cosa cessa di valere**,
come aveva fatto per P1.6 (`:3395-3413`): P1.13, la riga P1 della tabella e
`AGENTS.md` continuano a dire che la forma si decide sui dati del pilota. Il
protocollo, quindi, dice due cose; l'emenda datata piu' recente vince, ma chi
legge la tabella di stato non lo sa. Questa e' l'unica contraddizione testuale
aperta su P1.7, e non riguarda la formula: riguarda la regola di chiusura.

**Alternative.** D1 — tenere la quadratura, dichiararla *proxy di incertezza
standard* e riportare `f_b = sqrt(1+q_b²)/(1+q_b)` (con
`q_b = half_drift_w,b / half_range_pre_w,b`) come sensibilita' per blocco. D2 —
passare alla somma aritmetica, dichiararla *limite*, e ricalcolare prima della
campagna gate, pesi e `budget_pred`. D3 — decidere sulla rilevanza con una
soglia `f*` preregistrata: sopra `f*` resta la quadratura con la nota di D1,
sotto la scelta passa alla motivazione teorica.

**Conseguenze.** D2 non e' locale: la soglia del gate diventa piu' facile fino a
+41,4% (analitico, non statistico: la somma e' sempre `>=` della quadratura), i
pesi si spostano secondo la curva di `ρ` (incrocio fra 0,20 e 0,25) e
`budget_pred` segue per F.11. D1 non cambia nessun numero e lascia scritto che
l'ipotesi di ortogonalita' non e' verificata. D3 rende la decisione non
post-hoc, ma richiede che `f*` sia scritto prima di vedere `half_range_pre_w`; e
`f*` e' una soglia nuova, quindi va dichiarata come regola di decisione, non
come soglia del protocollo. Il pilota, in tutti e tre i casi, non puo' arbitrare
cio' che non misura (`p1_7_forma_budget_base_20261028.md` §4).

**Decisione da approvare.** D1 — che e' cio' che l'Emenda 8 gia' applica — piu'
una clausola di emendamento che elenchi le frasi che cessano di valere (P1.7
`:359-361`; P1.13 `:518-523`; riga P1 `:11`) e la correzione della riga stantia
di `AGENTS.md`. Il pilota riporta `f_b` per blocco come sensibilita' e non
tocca la forma. Se si preferisce che il pilota decida davvero, la scelta e' D3:
allora `f*` si preregistra e il punto di Emenda 8 "non decide la forma" va
emendato — le due cose non possono stare insieme.

**Test richiesti.** `f_b` con `q = half_drift/half_range`, e verifica che stia in
`[1/√2, 1]`; `budget_base_w = hypot(half_range, half_drift)` gia' fissato da
`tests/test_block_baseline.py:82` e `tests/test_baseline_ordine_v4.py:252-253`;
test che il calcolo di `f_b` non scrive ne' modifica alcun campo del blocco
(sensibilita', non decisione).

**Stato.** `deciso (Emenda 8), non allineato`: tre testi su quattro dicono
ancora il contrario.

### R10 — ambiente dichiarato (`CW_IDLE_WINDOW_S`, `CW_IDLE_CALIBRATION_SECONDS`)

**Riferimento.** P1.3 `:193-205`: "finestra idle = 30,000 s, passati
esplicitamente". Codice: `config.py:331` (`IDLE_CALIBRATION_SECONDS` = 10 s di
default), `energy_session.py:1380-1389` (`duration_s = max(10,
CW_IDLE_WINDOW_S)`, floor default 30 s), `:1440` (`p_rep`). Analisi in
`p6_preparazione_pilota_20261028.md` §2.9.

**Il rischio.** Se `CW_IDLE_WINDOW_S` e' impostata a 10, le tre repliche tornano
da 10 s — le finestre dei run v3, a cui P1.7 `:345-348` e P6.2 `:2371-2373`
attribuiscono l'assenza della terna. Il CSV registra le potenze
(`pre_windows_w`, `:146`) ma **non la durata**, quindi un run a 10 s e' oggi
indistinguibile, dagli artefatti, da un run a 30 s.

**Alternative.** (i) dichiarare entrambe le variabili non impostate nel piano e
nell'artefatto; (ii) guardia fail-closed nel runner: un run v4 si rifiuta di
partire se la finestra effettiva non e' 30 s; (iii) registrare la durata
effettiva (campo nuovo, emendamento P5) oppure nelle note di riga (nessuno
schema nuovo, ma testo libero non verificabile).

**Conseguenze.** (i) dipende dall'operatore e non lascia traccia nei dati. (ii)
cambia il comportamento, non la misura, ed e' l'unica che non dipende
dall'operatore; va limitata ai run v4 per non rompere i collaudi rapidi. (iii)
rende il campo verificabile, ma le note non sono filtrabili.

**Decisione da approvare.** (ii) + (i): il runner rifiuta di partire se la
finestra idle effettiva e' diversa da 30 s, con messaggio che nomina la
variabile; il piano dichiara entrambe le variabili non impostate e
l'artefatto lo registra. Se non si vuole toccare il codice prima
dell'emendamento P5, (i) + durata nelle note di riga, e (iii) entra nello stesso
emendamento di R11/R7.

**Test richiesti.** Risoluzione del floor: non impostata → 30; `= 10` → 10;
`= 45` → 45 (test unitario su `calibrate_idle`, senza misura). Se si adotta la
guardia: `CW_IDLE_WINDOW_S=10` su un run v4 → rifiuto prima del primo blocco, con
il nome della variabile nel messaggio; run normale → 30 s registrati.

**Stato.** `aperto`.

---

## 5. Emendamenti P5

Lo schema e' congelato a 172 colonne di richiesta, 36 di riepilogo di blocco e
19 di punto (`casualwatt_csv_export.py:17-200`, `:208-223`, `:225-233`; decimo
emendamento, 2026-10-28). Ogni aggiunta e' in coda, con migrazione per nome
(`ensure_header`) e senza rinominare o riordinare nulla. R11 e R12 sono due
emendamenti distinti; se si accetta anche `u_within_j` (R7), entra in quello di
R11 perche' e' lo stesso oggetto — il riepilogo di blocco — ma con il suo commit.

### R11 — `baseline_backend`

**Riferimento.** P1.3 `:203-205`: "Backend: lo stesso della misura della
richiesta; su questo host `emi-counter`. Se si usa il fallback, si registra
`baseline_backend` e l'incertezza di bordo del backend." P5 congelato
(`:15`, 36 colonne di blocco); CSV `:208-223`. Disegno completo in
`p1_3_baseline_backend_20261028.md` §2-§7. Codice: `energy_session.py:685-688`
(token di modalita'), `:1434` (unpack di `(delta, dt, mode)`), `:1449`
(`self._idle_mode`), `benchmark_v4.py:1411-1413` (calibrazione pre), `:1432`
(`raw_pre`), `:1596-1610` (post), `:1677` (riepilogo).

**Il fatto.** Il backend si sceglie **una volta per sessione** (assegnazioni
solo alla costruzione, nessun cambio a meta' sessione; `read_idle_window_j` usa
`self.method`, `:674-688`). Quindi, dentro un blocco, la baseline e la richiesta
non possono avere canali diversi, tranne con `CW_ENERGY_FILE`, che
`calibrate_idle` rifiuta (`:1394-1403`). P1.3 ammette il fallback, ma nella
pratica attuale il "fallback" e' una proprieta' della **sessione**: il campo non
scopre una variabile, **rende esplicita un'invarianza**. Questo cambia il
disegno: non serve un campo per misura, serve un campo per dichiarare, e un test
che l'invarianza regga.

**Alternative.** (a) campo nel riepilogo di blocco, token normalizzato
(`rapl-counter → rapl`, `energy-counter → energy-file`, `emi-counter` e
`pawnio-counter` invariati) preso dalla calibrazione **pre**; (b) campo di riga
(172 → 173, duplicato `m` volte); (c) nessun campo, si usa
`energy_calculation_method` (perde la distinzione pre/post e non soddisfa P1.3).

**Conseguenze.** (a) richiede l'emendamento (36 → 37) e la cattura di
`_idle_mode` **prima** della calibrazione post, che lo sovrascrive (`:1449`;
`_idle_reps` e' gia' salvato a `:1432`). Un dettaglio da chiudere: `_idle_mode`
e' la modalita' dell'**ultima** ripetizione (`mode_used = mode` in ciclo,
`:1442`), quindi il campo deve esigere che le tre repliche riportino la stessa
modalita' e rifiutare (o marcare) il caso misto, invece di prendere l'ultima in
silenzio. (b) e' ridondante e allarga la riga senza aggiungere informazione.
(c) e' il difetto che P1.3 esiste per evitare.

**Seconda meta' di P1.3: l'incertezza di bordo del backend.** Oggi non ha un
produttore per le finestre idle: `read_idle_window_j` restituisce solo
`(delta_j, dt_real, mode)` (`:660-692`), e `edge_spread_s` esiste solo per le
richieste (`local_energy.py:345-348`). Tre vie: (a) aggiungere un produttore;
(b) dichiararla **zero per costruzione**, data l'invarianza di sessione, e
scriverlo; (c) rifiutare una baseline in fallback. La proposta e' (b) + il test
dell'invarianza: il termine e' nullo perche' il canale e' lo stesso, non perche'
sia stato misurato nullo — e la frase va scritta cosi'. Se un giorno il canale
diventasse per-blocco, il produttore diventa obbligatorio.

**Decisione da approvare.** (a): una colonna in coda a
`BLOCK_SUMMARY_COLUMNS`, vocabolario chiuso, valore preso dalla pre, tre
repliche concordi, vuota sul blocco invalidato; piu' il test d'invarianza
`baseline_backend == energy_calculation_method` su ogni blocco di carico; piu'
la dichiarazione che l'incertezza di bordo della baseline e' zero per
costruzione finche' il canale e' unico per sessione.

**Test richiesti.** Tabella di mappatura dei quattro token; pre non sovrascritta
dalla post (blocco con pre e post di modalita' diverse → il campo e' la pre);
modalita' mista fra le tre repliche → rifiuto o token dedicato, mai "l'ultima";
campo presente nello schema e vuoto sul blocco invalidato; uguaglianza con
`energy_calculation_method`; migrazione per nome che lascia leggibili i CSV
scritti prima dell'emendamento.

**Stato.** `aperto` (disegno completo; emendamento e codice mancanti).

### R12 — token D11 (ragioni di G0 come campo di riga)

**Riferimento.** Specifica metodi `:1186-1199` ("Serve che il suo esito diventi
un token della riga, non un file a parte (D11)"), `:1931` (il testo del motivo
non nomina il produttore); classificazione in
`d11_d15_classificazione_20261028.md` §1. Schema: 172 colonne
(`casualwatt_csv_export.py:17-200`); `invalid_reason` e' un token di **blocco**
(`:222`), non di riga.

**Alternative.** (a) nuova colonna di riga con vocabolario chiuso
(`vm`, `remote_endpoint`, `permission_denied`, `driver_missing`,
`no_energy_domain`, `counter_stale`, `ambiguous_domain`); (b) allargare
`energy_calculation_method` a un insieme di ragioni; (c) un artefatto separato
(la specifica lo esclude esplicitamente).

**Conseguenze.** (a) emendamento 172 → 173, campo nel dataclass, funzione di
mappatura; la sonda oggi non e' importabile (`probes/` senza `__init__.py`) e usa
un lettore EMI diverso da quello di produzione (`probes/cw_probe.py:63-69`
contro `energy/emi_backend.py`), quindi "l'esito diventa un token" richiede di
importare la logica o di duplicarla dichiarandolo. (b) confonde canale e motivo
e rende non filtrabile per canale una tabella che oggi lo e'. (c) non e' per
riga, che e' il requisito.

**Decisione da approvare.** (a); il token si scrive **solo** quando nessun
contatore ha prodotto il numero, ed e' vuoto altrimenti; il vocabolario e'
chiuso e un valore fuori elenco e' rifiutato; il testo non nomina il produttore;
il token non si confonde con `invalid_reason` (blocco) ne' con `invalid_reasons`
(richiesta, P2.5).

**Test richiesti.** Un test per ciascuno dei sette token; vuoto sulle righe
misurate; rifiuto di un token fuori vocabolario; test che il testo non contiene i
nomi dei produttori; test che D11 non sovrascrive ne' legge `invalid_reason`.

**Stato.** `aperto` (direzione decisa nella specifica, codice e schema mancanti).

### R13 — guardia `CW_ENERGY_FILE` in `calibrate_idle` (residuo Fase A)

**Riferimento.** `energy_session.py:548` (`self.method = "energy-file"`),
`:649-654` (ramo del lettore), `:1394-1403` (guardia: ammette solo `rapl`,
`emi-counter`, `pawnio-counter`); `benchmark_v4.py:202-217` (classificatore),
`:1414-1420` (propagazione a `V4MeasurementError`);
`tests/test_cw_energy_file_override.py` (3). Disegno in
`p1_3_baseline_backend_20261028.md` §6.1.

**Il conflitto.** Il lettore supporta `energy-file`; la guardia lo rifiuta. Sotto
override, un run v4 si ferma al primo blocco con `V4MeasurementError`, che
**non** e' un guasto sostituibile (il classificatore riconosce solo il contatore
decrescente). E' una decisione, non un bug da correggere in silenzio.

**Alternative.** (a) ammettere `energy-file` nella guardia, solo DEV/TEST, con
`external_counter = true` (D14) e `baseline_backend = energy-file`; (b) tenere il
rifiuto e dichiarare che v4 non gira sotto override; (c) un modo DEV separato.

**Conseguenze.** (a) consente di rieseguire la logica v4 su tracce salvate, ma
richiede che l'analisi applichi il filtro `external_counter` — oggi lo farebbe
solo il gate di R8; il rischio di mescolare righe esterne alla catena con la
produzione e' reale ma filtrabile. (b) perde la riesecuzione, non perde nulla
della campagna.

**Decisione da approvare.** (b) adesso; (a) solo con dichiarazione esplicita e
filtro nell'analisi. Non blocca il pilota, che gira su EMI.

**Test richiesti.** Fissare il comportamento attuale con un test (rifiuto), cosi'
un cambiamento futuro e' deliberato; se (a), test che la riga porta
`external_counter = true` e `baseline_backend = energy-file`.

**Stato.** `aperto`, non bloccante.

---

## 6. Ordine di chiusura e dipendenze

| passo | voci | serve un run | serve codice | serve emendamento |
|---|---|---|---|---|
| 1 | R9 ratifica della chiusura P1.7 e allineamento di P1.13/riga P1/AGENTS | no | no | si' (clausola di sostituzione) |
| 2 | R10 ambiente dichiarato (+ eventuale guardia) | no | solo con la guardia | no (o si', se la durata va in un campo) |
| 3 | R11 + R7: `baseline_backend` e `u_within_j` in coda al riepilogo | no | si' | si' (36 → 38) |
| 4 | R8 gate di qualita' per il fit | no (fixture sintetiche) | si' | no |
| 5 | R5/R6 regole di fase per P6.6 | no | si' (harness) | no (registrazione) |
| 6 | R4 `C`/`R`/`T`, poi R2/R3, poi R1 banda | si' per C e per l'ancora A1 | si' (harness) | si' solo se D o C |
| 7 | R12 token D11 | no | si' | si' (172 → 173) |
| 8 | R13 | no | si' | no |

Dipendenze: R7 dipende da R8 (il gate definisce le righe valide); R1 con A1
dipende dal pilota P6.2 che produce `budget_pred`; R3 e R2 dipendono dalla
scelta di R1 (con D non ci sono bande da aggregare); R11 e R7 condividono lo
stesso emendamento di schema ma restano due commit.

**Cosa non chiude il pilota.** Nessuna voce di questo registro e' il pilota.
P6.2 richiede che il pilota produca `half_range_pre_w` e `u_within,b`: la prima
esce gia' dal runner (`block_baseline`, `benchmark_v4.py:685-759`), la seconda
richiede R7 e R8. L'audit idle di P6.3 (30 minuti, `pre_range_w <= 1,0 W`) resta
un prerequisito separato e non e' toccato qui.

---

## 7. Se le decisioni vengono approvate: cosa cambia e dove

| voce | file | tipo di modifica | test |
|---|---|---|---|
| R1-R4 | piano del pre-pilota (nuovo artefatto) e harness P6.6 | parametri dichiarati, nessun default | validazione del piano |
| R5-R6 | harness P6.6 | regola di fase, esclusioni con motivo | casi sintetici |
| R7 | modulo di analisi; poi `casualwatt_csv_export.py` | derivazione; una colonna in coda | semi-range, blocchi invalidi, join |
| R8 | modulo di analisi | gate unico, soglie congelate | confini 1,0 W / 10% / 20% / 5% |
| R9 | protocollo (emenda datata), `AGENTS.md` | clausola di sostituzione; riga stantia | nessuno (documento) |
| R10 | `benchmark_v4.py` (guardia), piano | rifiuto fail-closed; dichiarazione | floor e rifiuto |
| R11 | `casualwatt_csv_export.py`, `benchmark_v4.py`, `energy_session.py` | colonna in coda; cattura della pre | mappatura, invarianza |
| R12 | `casualwatt_csv_export.py`, dataclass, mappatura | colonna in coda; vocabolario chiuso | un test per token |
| R13 | `energy_session.py` (solo se (a)) | guardia DEV/TEST | rifiuto attuale fissato |

Il protocollo non si riscrive: le modifiche sono emende datate in coda, con
l'elenco esatto di cio' che cessa di valere — la forma che l'Emenda 8 ha usato
per P1.6 e non per P1.7.

---

## 8. Ancore verificate il 2026-10-28

| affermazione | ancora |
|---|---|
| la banda e' l'unico valore aperto di P6.6 | `protocollo_v4_20261024.md:2608-2615`, `:2657-2658` |
| fase valida = finestra integra, `done_reason` atteso, nessun `engine_tree_changed` | `:2596-2598` |
| alternativa esclusione/fallback per `engine_tree_changed` | `:2631-2634` |
| `tree_born` non alza il flag (definizione letterale) | `:2630-2631`; `benchmark_v4.py:1490`, `:1518` |
| `u_within` non diviso per `√m`, scala di `Ē_b` | `:1063-1068`, `:1658-1662`, `:1675-1686` |
| il pilota deve produrre `half_range_pre_w` e `u_within` | `:2376-2382`; `:2434-2439` |
| P1.7 rinvia la forma ai dati del pilota | `:359-371`; `:518-523`; riga P1 `:11` |
| l'Emenda 8 la chiude e rende il pilota descrittivo | `:3478-3504` |
| F.11 lega la forma di `budget_pred` a quella di `budget_base_w` | `:1719-1723` |
| soglie di P1.6 e filtro dei controlli | `:251-278`; `:1525-1550` |
| sostituzione del blocco e `invalid_reason` | `:3415-3461` |
| `baseline_backend` richiesto, con incertezza di bordo | P1.3 `:203-205` |
| schema a 172 / 36 / 19 colonne | `casualwatt_csv_export.py:17-200`, `:208-223`, `:225-233` |
| `budget_fit_j` esiste ma il runner lo lascia vuoto | `benchmark_v4.py:1684` |
| `r_A`/`r_B` lasciati all'analisi | `benchmark_v4.py:1692` |
| gate di partizione dei blocchi invalidati, con test | `benchmark_v4.py:260-417`; `tests/test_filtro_p6_invalidati.py` |
| modalita' del lettore idle e sovrascrittura della post | `energy_session.py:685-688`, `:1434`, `:1442`, `:1449` |
| guardia di `calibrate_idle` | `energy_session.py:1394-1403` |
| floor da `CW_IDLE_WINDOW_S`, default 30 s | `energy_session.py:1380-1389`; `config.py:331` |
| `s` escluso se l'albero cambia, con fonte dichiarata | `local_energy.py:662-678`, `:684-688` |
| `edge_spread_s` esiste solo per le richieste | `local_energy.py:345-348` |
| `chain_status` legge `negative_increment` e `baseline_unstable` | `validation_chain.py:121`, `:128`, `:242` |
| `u_within` mai calcolato in produzione | grep 2026-10-28; `benchmark_v4.py:712`; `semi_range_concentrazione_pesi_probe.py:61` |

---

## 9. Cosa non e' stato fatto in questo turno

- nessuna riga di codice di produzione modificata; nessun campo aggiunto;
- nessuna soglia, formula o banda fissata; nessuna riga del protocollo toccata;
- nessun run eseguito, nessun `pytest` rieseguito: non essendoci modifiche al
  codice, l'output di suite resta quello registrato in `AGENTS.md` (526 = 523 + 3);
- R13 e' registrato come decisione, non corretto: il comportamento attuale e'
  quello che il codice ha, e cambiarlo richiede l'approvazione.

## 10. File esaminati

- `experiment_results/protocollo_v4_20261024.md`: `:8-16`, `:191-205`,
  `:249-375`, `:516-523`, `:830-845`, `:1035-1077`, `:1507-1572`,
  `:1653-1686`, `:1714-1723`, `:2212-2253`, `:2350-2408`, `:2410-2458`,
  `:2460-2660`, `:2918-2935`, `:3385-3504`;
- `experiment_results/p6_6_banda_20261025.md`;
- `experiment_results/p6_6_prepilota_20261025.md`;
- `experiment_results/p6_preparazione_pilota_20261028.md`;
- `experiment_results/p1_7_forma_budget_base_20261028.md`;
- `experiment_results/p1_3_baseline_backend_20261028.md`;
- `experiment_results/d11_d15_classificazione_20261028.md`;
- `cwEnergyModular/benchmark_v4.py`;
- `cwEnergyModular/casualwatt_csv_export.py`;
- `cwEnergyModular/energy/energy_session.py`;
- `cwEnergyModular/energy/local_energy.py`;
- `cwEnergyModular/validation_chain.py`;
- `cwEnergyModular/config.py`.
