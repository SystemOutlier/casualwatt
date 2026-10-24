# Valutazione della revisione esterna di secondo turno (2026-10-25)

**Provenienza del materiale.** I quattro rilievi valutati qui sono stati prodotti
da un altro modello linguistico e forniti dall'utente come testo incollato in
chat, non come file del repository. Per AGENTS.md questo materiale è **spunto,
non evidenza**: ogni affermazione è stata verificata contro
`protocollo_v4_20261024.md`, contro il codice in `cwEnergyModular/` e, dove il
rilievo era numerico, **per esecuzione**. Nessun rilievo è stato accolto perché
scritto da un revisore; nessuno è stato respinto perché scritto da un revisore.

**Esito in una riga.** Tre dei quattro rilievi descrivono difetti **già chiusi**
nel protocollo il 2026-10-24, e le formule che il revisore propone sono già state
valutate e scartate con motivazione scritta; il quarto rilievo contiene
un'avvertenza **fondata e nuova** che ha prodotto l'unica correzione sostanziale
di questo turno. La verifica ha inoltre fatto emergere **quattro difetti reali**, tre dei quali non
segnalati dal revisore: tutti di dichiarazione, nessuno di formula.

| # | rilievo del revisore | stato nel protocollo | esito |
|---|---|---|---|
| 1 | `r_A` non è calcolabile sui blocchi di controllo | **chiuso 2026-10-24**, P4.5 `:1429-1573` | proposta del revisore già valutata e scartata (`:1457-1462`); resta un difetto di schema, corretto |
| 2 | `u_bias`: unità, durata e formula del budget predittivo | **chiuso 2026-10-24**, P4.6 `:1575-1769` | formula proposta identica a quella in vigore tranne il simbolo di durata; la variante del revisore è respinta, la scala è ora dichiarata |
| 3 | eliminare `E_trunc` e rendere esplicita la validità del denominatore | **chiuso 2026-10-24**, P1.6 `:210-245` | la forma proposta è il candidato 1 già scartato a `:219-221`; avrebbe reintrodotto il troncamento |
| 4 | copertura sulle coordinate effettive e metrica di `hull_margin_tok` | **chiuso 2026-10-24** per la copertura (P4.7 `:1831-1892`), **aperto** per la metrica | avvertenza sulla metrica **accolta**: è la quinta emenda, di sola dichiarazione |

---

## 1. Rilievo 1 — `r_A` sui controlli

**Cosa dice il revisore.** Il protocollo usa `r_A` come criterio di stabilità su
blocchi che non inviano richieste, dove il denominatore è vuoto; propone un
indicatore distinto (`control_drift_w`) e un flag dedicato
(`control_stability_pass`).

**Verifica.** Il difetto è reale ed era già stato trovato, chiuso e registrato
nella tabella dei difetti dichiarati in testa al protocollo (`:29`). La diagnosi
nel testo congelato è la stessa del revisore, con la ragione strutturale:
`r_A` è una grandezza **relativa**, confronta il drift con l'energia misurata, e
un blocco di controllo non ha energia misurata (P4.4 requisito 5, P4.5 `:1437-1445`).

**Cosa è già in vigore** (P4.5 `:1447-1452`):

```
controllo utilizzabile se   pre_range_w,c ≤ 1,0 W   e   |dP_c| ≤ 1,0 W
```

con flag `control_unstable` (`:1464-1466`) e quorum `⌈2/3 · n_coppie⌉ = 4` su sei
coppie (`:1466-1472`). Il numero di controlli utilizzabili va in
`controls_usable_n`.

**Perché le due proposte del revisore non sono adottate.**

- *Un nome nuovo per l'indicatore.* `control_drift_w` non aggiunge informazione:
  la grandezza esiste già ed è definita in F.1 (`dP`, `:2502`) insieme a
  `pre_range_w` (F.3, `:2545`), e il suo valore assoluto è già uno dei due
  ingressi del filtro. Aggiungere un secondo nome per la stessa
  quantità è il difetto che AGENTS.md vieta esplicitamente ("Terminologia unica").
  Il protocollo ha già un nome per l'**esito** (`control_unstable`), ed è quello
  che serve come campo.
- *Una soglia nuova.* La richiesta del revisore di "motivare e dichiarare la
  soglia separatamente" è già soddisfatta, e la soglia **non è nuova**: è la
  stessa di 1,0 W congelata in P1.6 con motivazione misurata — 1 W di errore
  sulla baseline sposta `J/token` del 6–11%
  (`idle_floor_sensitivity_20261023_analisi.md` §2, citato a `:1454-1456`).
  Introdurre `control_stability_pass` con una soglia propria sarebbe scegliere
  una soglia **dopo** aver visto il disegno della campagna; le soglie sono
  congelate prima dei dati (AGENTS.md).
- La via che il revisore non propone — una metrica nuova
  `r_ctrl = |dP_c| · Δt_W,c / E_rif,c` — è stata valutata e scartata il
  2026-10-24 per circolarità di accoppiamento fra i due blocchi della coppia
  (`:1457-1462`, diagnosi in `revisione_esterna_formule_20261024_valutazione.md` §4.2).

**Difetto reale trovato verificando.** Il filtro di P4.5 è calcolabile in virtù
del requisito 7 di P4.4, che elenca `pre_range_w,c` e `dP_c` fra i contenuti del
blocco di controllo; ma l'elenco dei **campi obbligatori** di P4.12 non li
conteneva, e lo schema di F.17 li elencava come grandezze "che nessun punto ha
ancora messo in elenco". Un flag obbligatorio i cui due ingressi non sono salvati
è un'affermazione, non un dato: nessun terzo potrebbe verificare
`control_unstable` dai CSV. **Corretto**: `pre_range_w` e `dP` entrano
nell'elenco di P4.12 (`:2133`), con la regola generale scritta a `:2137-2145`;
F.17 è aggiornato di conseguenza (`:3140-3151`); P6.5 registra il requisito per
P5 `:2427-2433`, perché nessuna delle due è una colonna esistente
(`casualwatt_csv_export.py:17-108`, verificato per esecuzione il 2026-10-25:
0 occorrenze di `pre_range_w`, `dP`, `budget_base*`, `baseline_pre_w`).

---

## 2. Rilievo 2 — `u_bias`: formula, unità, significato

**Cosa dice il revisore.** Chiede (a) di dichiarare se `bias_w` è una correzione
sistematica sottratta o un limite operativo aggiunto al budget, (b) di specificare
quale durata moltiplica `bias_w`, e propone
`budget_pred_b² = budget_fit_b² + u_edge_b² + u_bias_b²` con
`u_bias,b = |bias_w| · Δt_W,b`.

**Verifica.** Il difetto era reale ed è chiuso dal 2026-10-24 (tabella `:30`,
P4.6 `:1611-1620`): nella versione congelata `u_bias` **compariva nel testo e
non nella formula**, e la durata non era specificata. Entrambe le risposte che il
revisore chiede sono già scritte:

- **(a) È un contributo di incertezza, non una correzione.** P4.3 Definizioni
  `:1348` e P4.6 `:1633`: "contributo di incertezza, **non** correzione sottratta dai dati".
  Il valore assoluto sta dentro `u_bias,b` proprio perché un contributo di
  incertezza è non negativo, mentre il segno del bias è informazione che resta
  nel campo `bias_w` firmato. Nessun dato viene corretto: P1 non cambia (`:2050`).
- **(b) La durata è `Δt̄_W,b`, media per blocco.** La formula in vigore è
  `u_bias,b = |bias_w| · Δt̄_W,b` con
  `Δt̄_W,b = (1/m) · Σ_{i∈blocco b} Δt_W,i` (`:1586-1588`, F.11 `:2762-2763`).
  È **la stessa grandezza già usata da `u_base,b`** in P3.8 (`:1594-1595`, `:992`), quindi
  non introduce un simbolo nuovo.

**Perché la forma proposta dal revisore non è adottata.** `Δt_W,b` senza barra è
ambiguo fra la durata media e la durata **aggregata** del blocco, e le due danno
joule diversi di un fattore `m = 3`: è esattamente il difetto che l'emendamento
del 2026-10-24 ha chiuso (`:1615-1618`). La lettura aggregata è stata valutata e
**non adottata** — con `Σ_i Δt_W,i` i tre termini `u_base`, `u_edge`, `u_bias`
crescerebbero di un fattore 3 e `budget_pred_b` fino a tre volte, su un budget che
deve accompagnare `Ē_b`, media per richiesta (F.7 `:963`, F.9 `:984`). La formula
del revisore per `budget_pred_b²` è invece **identica** a quella in vigore
(`:1581`, `:1349`, `:2764`): nessuna divergenza.

**Difetto reale trovato verificando.** La scala dei due budget
(`budget_fit_b`, `budget_pred_b`) non era dichiarata in nessun punto: entrambi
sono in joule **sulla scala di `Ē_b`**, media per richiesta del blocco, non sul
totale di blocco. È la ragione per cui la durata che li collega ai watt è
`Δt̄_W,b` e non `Σ_i Δt_W,i`, ma finché non è scritta la coerenza è
un'inferenza del lettore. **Corretto**: dichiarazione esplicita in P4.6
(`:1597-1608`) e in F.11 *Applicazione* (`:2779-2781`).

---

## 3. Rilievo 3 — `E_trunc` e la validità del denominatore

**Cosa dice il revisore.** Propone di eliminare il simbolo ereditato dalla
produzione e di scrivere `r_A = |dP| · Σ Δt_W,i / Σ E_net_incremental,i` con la
condizione di validità `Σ > 0`.

**Verifica.** La prima metà è **già fatta**: `E_trunc` è eliminato dal
2026-10-24 (P1.6 `:241-245`, F.3), sostituito da `E_net_abs,b` (`:225`); le sei
occorrenze residue nel protocollo sono tutte frasi di **ritiro** del simbolo, non
usi vivi (verificato per grep multiline il 2026-10-25). Il difetto era reale:
quattro occorrenze d'uso e nessuna di definizione, nessuna voce in Terminologia,
nome ereditato da una produzione che tronca due volte
(`local_energy.py:300` e `:309-310`) mentre la v4 non tronca (P1.3, P3.2, F.2).

**Perché la forma proposta è respinta.** È il **candidato 1** della tabella già
valutata a `:219-221` e scartato:

| candidato | denominatore | conseguenza se `Σ E_net < 0` |
|---|---|---|
| `Σ E_net_incremental,i` firmato | può essere ≤ 0 | `r_A ≤ 0` passa sempre: il filtro è cieco |

Il revisore aggiunge la condizione `Σ > 0`, che non risolve il difetto e ne
aggiunge uno: con `Σ < 0` il blocco non sarebbe "invalido per denominatore cieco"
ma "non valutabile", cioè un esito che dipende dal **segno** dell'energia netta e
non dalla sua grandezza. Soprattutto, un denominatore firmato spinge verso
l'uso di `Σ |E_net,i|` per garantirne la positività, che è il candidato 3,
scartato perché confronta il drift con una grandezza che **non entra nel fit**
(F.7 stima su `Ē_b`). La scelta in vigore è la seconda:
`E_net_abs,b = |Σ_i E_net_incremental,i| = m · |Ē_b|` (`:225-226`), l'unica
coerente con "nessun troncamento" perché il valore assoluto sta **fuori** dalla
somma, quindi le singole `E_net_incremental,i` restano firmate e nessuna è
clampata. È il vincolo esplicito dell'utente per questo turno: il troncamento
dell'energia incrementale **non** si reintroduce per accomodare una formula
ereditata dalla produzione.

**Sulla condizione di validità.** Esiste già, ed è congelata: "se il denominatore
di `r_A` o `r_B` è zero, il blocco o il punto è invalido per costruzione"
(`:207-208`), con il senso precisato a `:237-239`. Aggiungere `Σ > 0` come
criterio **nuovo** significherebbe introdurre una condizione di validità dopo
aver visto il disegno; con `E_net_abs` la condizione è `≠ 0`, che è più debole e
non seleziona sul segno. L'informazione di segno non va persa: è portata dal flag
`negative_increment` (`:204-206`) e dal campo grezzo firmato, ed è una colonna
obbligatoria (P4.12).

**Nessun difetto nuovo** emerso da questo rilievo.

---

## 4. Rilievo 4 — copertura sulle coordinate effettive, e metrica del margine

**Cosa dice il revisore.** Cinque passi: (1) `hull_fit` sulle coordinate reali dei
33 blocchi di fit, (2) `box_fit` come rettangolo dei reali, (3) classificazione
per blocco sulla coppia reale, (4) fascia pubblicata = la più conservativa dei due
lati, (5) avvertenza che un `hull_margin_tok` euclideo grezzo dipende dalla scala
degli assi e che coordinate normalizzate sarebbero una decisione metodologica
separata.

**Verifica sui passi 1–4: tutti già in vigore** (P4.7 `:1839-1865`), e il
protocollo va **un passo oltre** la raccomandazione: non sposta solo il punto sui
reali tenendo l'inviluppo sui target, ma costruisce **due inviluppi nella stessa
base del punto classificato** (`:1831-1837`, `:1867-1869`), perché con reali
sistematicamente spostati un punto può cadere dentro l'inviluppo di progetto ed
essere fuori da quello dei dati su cui il modello è stimato — un'estrapolazione
pubblicata in fascia A. Il passo 4 è la regola
`coverage_tier = il più conservativo dei due` (`:1863`). I quattro margini
pubblicati sono etichettati come **margini di progetto** (`:1873-1877`), e la
possibilità che la fascia cambi dopo la misura è dichiarata come conseguenza, non
come eccezione (`:1878-1882`).

**Il passo 5 è accolto, ed è l'unica correzione sostanziale di questo turno.**
"Distanza dal bordo" non specificava **quale** distanza, e la scelta non è
cosmetica perché `thin_support` scatta sotto i 2 token (soglia congelata).
Verificato **per esecuzione** il 2026-10-25 sui 10 punti di disegno di P3.5
(9 celle 32/128/512 × 32/128/256 più il minimo (8,4)), con `hull_design`
ricalcolato e non copiato:

```
vertici hull_design = (8,4) (512,32) (512,256) (32,256)     [confermati]

punto      perpendicolare   dal vertice più vicino   rapporto   thin_support
(12,32)         1,33                 28,28            21,3     True  / False
(256,192)      64,00                232,96             3,6     False / False
(32,32)        21,24                 36,88             1,7     False / False
(128,128)     107,70                160,00             1,5     False / False
```

Le due metriche danno **esiti opposti** del flag obbligatorio `thin_support` sul
punto operativo reale (12,32): con la perpendicolare è marcato, con la distanza
dal vertice non lo è. Fattore 21,3 sullo stesso punto e sullo stesso inviluppo.
La metrica adottata è la **perpendicolare euclidea dalla retta dello spigolo più
vicino**, in coordinate grezze, negativa fuori dall'inviluppo — ed è quella con
cui i quattro margini già pubblicati tornano: 1,33 / 64,0 / 21,24 / 107,7 (il
terzo è il 21,2 scritto, arrotondato). Se fosse stata adottata l'altra, tutti e
quattro i numeri pubblicati sarebbero stati sbagliati dello stesso fattore, e un
flag congelato avrebbe cambiato segno in silenzio.

È il quinto difetto dichiarato in testa al protocollo, ed è quello in cui le due
letture della stessa frase danno due esiti opposti di un flag già congelato.
Chiuso il 2026-10-25 in **cinque** punti, perché una dichiarazione sola in un
documento di 3155 righe non vincola l'implementazione: P4.3 Definizioni
(`:1354`), blocco di calcolo di P4.7 (`:1840-1845` e `:1853`, `:1860`),
paragrafo di verifica di P4.7 (`:1894-1903`), blocco di F.13 (`:2899-2901`), e il
requisito per P5 in P6.5 (`:2434-2439`), che vincola l'implementazione e non solo
l'interpretazione.

**Coordinate normalizzate: dichiarate, non adottate.** L'avvertenza del revisore
sulla dipendenza dalla scala è corretta e va presa sul serio: `N_in` sta in 8–512
e `N_out` in 4–256, quindi una distanza euclidea grezza pesa i due assi in modo
diseguale. Normalizzare renderebbe il margine adimensionale. È però una decisione
metodologica **distinta**, non una correzione da introdurre di passata: cambia il
valore di tutti i margini pubblicati e il **significato** della soglia di 2 token
di `thin_support`, che sta nel testo congelato. Per AGENTS.md le soglie si
congelano prima dei dati e non si spostano dopo; applicarla in silenzio sarebbe
esattamente lo spostamento vietato. Registrata come sviluppo possibile, da
prendere **prima** dei dati se la si vuole prendere (`:1905-1914`). Finché non è
presa, la metrica è quella grezza dichiarata e i margini sono in token — e chi
legge un margine pubblicato deve leggere anche quella riga.

---

## 5. Le quattro correzioni applicate in questo turno

Nessuna tocca una formula congelata o sposta una soglia. Tutte sono di
**dichiarazione**: rendono esplicito ciò che il testo implicava, o aggiungono un
campo obbligatorio che un flag già congelato presuppone.

| # | difetto | dove | correzione |
|---|---|---|---|
| 1 | metrica di `hull_margin_tok` non specificata: "distanza dal bordo" senza dire quale distanza | P4.3, P4.7, F.13, P6.5 | dichiarata la perpendicolare euclidea, verificata per esecuzione, con il controesempio 1,33 contro 28,28 scritto nel testo |
| 2 | `pre_range_w` e `dP` obbligatori per P4.5 ma assenti dall'elenco dei campi di P4.12 e dallo schema di F.17 | P4.12, F.17, P3.13, P6.5 | aggiunti all'elenco, con la regola generale "un flag obbligatorio porta con sé i valori da cui è stato calcolato"; requisito per P5 registrato |
| 3 | passo 5 di F.0 chiedeva `r_A` e `r_B` su blocchi dove l'emendamento di P4.5 li ha dichiarati non calcolabili | F.0 | disambiguato: `r_A`/`r_B` sui blocchi di carico, filtro assoluto e `control_unstable` sui blocchi di controllo |
| 4 | scala di `budget_fit_b` e `budget_pred_b` non dichiarata: joule su `Ē_b` o sul totale di blocco | P4.6, F.11 | dichiarata la scala di `Ē_b`, con la lettura aggregata valutata e non adottata (fattore `m = 3`) |

I difetti 2, 3 e 4 sono emersi **verificando** i rilievi, non dai rilievi: il
revisore segnalava la metrica del margine (difetto 1, dal suo passo 5) e non lo
schema dei dati, né l'ordine di calcolo, né la scala dei budget. È la conferma del
metodo — la verifica degli ancoraggi trova più difetti della lettura delle
proposte, e infatti tre dei quattro non erano segnalati da nessuno.

---

## 6. Controllo incrociato delle occorrenze dei simboli modificati

Richiesto esplicitamente dall'utente prima di ridichiarare il protocollo
congelato. Metodo: per ogni simbolo modificato, ricerca su **tutto** il documento
con `multiline` attivo (la lezione del primo turno: gli ancoraggi ripetuti si
cercano per numero o per nome di simbolo, mai per frase, perché il testo va a
capo fra le parole — è così che al primo giro era sfuggita la quinta occorrenza di
"126 token"). Per ciascuno: definizione, formula, criterio di validità, schema
dei dati, richiami nelle sezioni successive.

| simbolo | occorrenze | esito |
|---|---|---|
| `hull_margin_tok`, `hull_margin_design_tok` | P4.3 `:1350-1354`, P4.7 `:1839-1865`, P4.8 `:2180`, F.0 passo 13 `:2487-2489`, F.13 `:2896-2919`, P4.12 `:2129`, F.17 `:3133`, P6.5 `:2434-2439` | coerenti; metrica dichiarata in tutti e cinque i punti normativi |
| `thin_support` | P4.7 `:1864`, P4.3 `:1354`, P4.12 `:2131`, F.13 `:2918` | soglia 2 token invariata; il flag ora ha una metrica sola |
| `pre_range_w`, `dP` | P1.6 `:181-182`, F.1 `:2502`, F.3 `:2545`, `:2556`, P4.5 `:1403-1494`, P4.12 `:2133-2145`, F.0 `:2470-2474`, F.12 `:2827`, F.17 `:3140-3151`, P3.13 `:1214-1217` | coerenti dopo la correzione; F.17 non li elenca più come "nessun punto li ha messi in elenco" |
| `control_unstable` | tabella difetti `:29`, P4.5 `:1464`, P4.12 `:2132-2140`, F.0 `:2456`, `:2474`, F.12 `:2829`, F.17 `:3135` | coerenti; i due ingressi sono ora entrambi campi obbligatori |
| `Δt̄_W,b` | P3.8 `:992`, P4.3 `:1346`, P4.6 `:1583-1608`, F.11 `:2762-2781`, F.0 `:2478`, P4.12 `:2134`, F.17 `:3148-3151` | definizione unica `(1/m)·Σ Δt_W,i`, usata da `u_base,b` e `u_bias,b`; nessuna occorrenza con durata aggregata |
| `u_bias,b`, `u_bias_j` | P4.3 `:1348`, `:1349`, P4.5 `:1496-1499`, P4.6 `:1581-1637`, P4.9 `:2050`, P4.12 `:2126`, F.0 `:2457-2460`, F.10 `:2749`, F.11 `:2763-2774`, F.12 `:2845-2867` | compare nella formula di `budget_pred_b²` in tutti e tre i punti in cui la formula è scritta |
| `bias_jtok_pct_lo` / `_hi` | P4.3 `:1343`, P4.5 `:1517`, `:1526`, F.0 `:2456`, F.12 `:2839`, intestazione P4 `:14` | armonizzati al primo turno (commit `0e53a67`); nessuna occorrenza residua del nome singolo |
| `E_trunc` | 6 occorrenze, tutte frasi di ritiro | simbolo ritirato; nessuna formula lo usa |
| `E_net_abs` | Terminologia `:68-69` e ritiro di `E_trunc` `:74-77`, P1.6 `:191-195`, `:225-226`, P4.4 `:1416`, P4.5 `:1439`, F.0 `:2472`, F.3 `:2547-2551`, `:2564`, F.12 `:2858` | unico denominatore di `r_A`/`r_B`; nessuna occorrenza residua di `E_trunc` come simbolo vivo |

Due incoerenze residue trovate dal controllo incrociato e corrette nello stesso
turno: F.17 `:3140-3151` (che elencava `pre_range_w` e `dP` come grandezze non
ancora elencate da nessun punto, falso dopo la correzione di P4.12) e l'elenco
P4.12 riportato in F.17 `:3130-3136` (che non includeva i due campi nuovi).

---

## 7. Eseguibilità del gate P4.9 dopo le modifiche

Verifica richiesta perché un emendamento che rende un anello non calcolabile è
peggio del difetto che corregge. Letti i sei anelli (`:2047-2054`) e per ciascuno
gli ingressi, cercandoli nello schema dei dati.

| anello | criterio | ingressi | presenti come campi obbligatori |
|---|---|---|---|
| 1 | pilota P2.9 A/B/C superato | esito del pilota | sì, artefatto di P2.9, non colonna |
| 2 | nessun blocco con delta negativo, reset o lettura non finita | `raw_start`, `raw_end`, `negative_increment` | sì (`CSV_COLUMNS` esistenti + P4.12) |
| 3 | `r_A ≤ 10%` in almeno 2 blocchi su 3 per punto | `dP`, `E_net_abs,b` (da `active_energy_j`), `Σ Δt_W,i` (da `duration_s`) | sì: `dP` **dal 2026-10-25**; `budget_base_j` resta da aggiungere in P5 |
| 4 | test load-versus-control dentro il budget | `pre_range_w,c`, `|dP_c|`, `budget_base_j,c`, `budget_base_w,c`, quorum 4 su 6, `controls_usable_n` | sì: i primi due **dal 2026-10-25**; `budget_base_j,c` è il requisito P6.5 aperto `:2427-2433` |
| 5 | lack-of-fit non significativo, `p_lof_perm ≥ 0,05` | `F_lof`, `p_lof_perm`, `p_lof_asint`, `lof_max_rel` (per campagna), `z_pe_b` (per blocco) | sì, emendamento P3.9; collocazione decisa da P5 |
| 6 | entrambi i punti di conferma con `err_rel ≤ 10%` e dentro `intervallo_conf` | `err_rel`, `intervallo_conf`, `pred_nonpositive`, `budget_pred_b` (con `u_bias_j`, `u_edge_j`, `hull_margin_tok`, `coverage_tier`) | sì; `budget_pred_b` calcolabile perché `Δt̄_W,b` è derivato da `duration_s` (P4.12 `:2134`) |

Esito: la catena resta eseguibile. L'unico ingresso non ancora garantito da un
campo obbligatorio è `budget_base_j`, e per questo è scritto come requisito di
P5 in P6.5 `:2427-2433` e in F.17 `:3146-3150`: senza di esso l'anello 4 confronta un errore
con una soglia non salvata. Non è un difetto introdotto da questo turno — è il
lavoro principale di P5, che è aperto.

Verificata anche la coerenza numerica dei termini di leva dichiarati in P4.8,
per esecuzione il 2026-10-25 sui 33 blocchi di fit del disegno nominale di P3.5:
rango 4, condizionamento grezzo 1,023e5 (valori singolari
2,653e5 / 8,792e2 / 6,062e2 / 2,594e0), centrato e scalato 3,761, leva media
0,121212 = 4/33, leva massima 0,2852 sui tre blocchi (512,256) con fattore
`1/√(1−h)` = 1,1828, sei blocchi sopra `2p/n = 0,2424`. Tutti i numeri di
`:2001-2015` e `:2409-2419` tornano.

---

## 8. Cosa non è cambiato

Nessuna formula congelata è stata modificata al di fuori dei punti con
contraddizione dimostrabile, come richiesto dall'utente. In particolare:

- `E_net_incremental` resta **firmato e mai troncato** (P1.3, F.2); il rilievo 3
  non ha reintrodotto il troncamento, né direttamente né attraverso un
  denominatore firmato;
- nessuna soglia è stata spostata: 1,0 W, 10%, 20%, 5%, `err_rel ≤ 10%`, 2 token,
  fattore 2, quorum `⌈2/3 · n_coppie⌉` restano quelle congelate prima dei dati;
- `budget_base_w` resta in quadratura, con la forma di combinazione ancora
  provvisoria e rinviata ai dati del pilota P2.9 (P1.7, P1.13): questo turno non
  la tocca;
- la copertura resta "nominale non arbitrata" (P4.8) e la scala assoluta resta
  non arbitrata senza wattometro AC/DC esterno;
- P1–P4 restano congelati; la quinta emenda è di sola dichiarazione.

## 9. Verifiche eseguite e loro limiti

Eseguite, non assunte: ricalcolo dell'inviluppo convesso dei 10 punti di disegno
e delle quattro distanze con entrambe le metriche; ricalcolo di rango,
condizionamento e leva sui 33 blocchi di fit; grep multiline su ogni simbolo
modificato; lettura integrale di `CSV_COLUMNS`
(`casualwatt_csv_export.py:17-108`) con conteggio delle occorrenze dei nomi di
campo candidati; suite di test `pytest cwEnergyModular` rieseguita e incollata per
intero nel verbale.

Limiti dichiarati. `hull_fit` **non** è ricalcolabile oggi: richiede le 33 coppie
di token reali `(x1_b, x2_b)`, che esistono solo dopo la campagna. La verifica ha
quindi riguardato `hull_design` e la metrica, non i margini reali. Le distanze
sono calcolate con aritmetica in doppia precisione su coordinate intere, dove il
margine minimo (1,33) è sei ordini di grandezza sopra la risoluzione disponibile:
nessun rischio numerico nella conclusione. Infine, la verifica che la metrica
adottata sia quella con cui i margini pubblicati sono stati originariamente
calcolati è **indiretta**: non esiste nel repository lo script che li ha prodotti,
quindi la prova è che la perpendicolare li riproduce tutti e quattro mentre la
distanza dal vertice ne dà altri. Per questo la metrica è ora dichiarata nel testo
invece di restare implicita in un calcolo non tracciato, e P6.5 chiede a P5 di
vincolare l'implementazione.
