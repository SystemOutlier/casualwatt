# Fase B — proposta metodologica motivata per R1–R6

Data: 2026-10-29. **Stato: proposta. Nessuna riga di codice, protocollo,
soglia, schema CSV o harness modificata; nessun run; nessun `powercfg`; nessun
accesso all'hardware; nessun push.** Oggetto: le sei voci R1–R6 del registro
`fase_b_registro_decisioni_20261028.md` (commit `a8a8d28`). R7–R13 restano
fuori da questa consegna: l'autorizzazione copre R1–R6.

Questo documento non decide: propone, con la formulazione pronta da approvare.
L'implementazione (Fase 3) non comincia finche' le formulazioni di §8 non sono
approvate.

---

## 0. Come leggere la proposta

**Tre grandezze che non si scambiano.** Sono il punto 1 della tua attenzione su
R1–R2, e valgono come regola di lettura di tutto il documento:

| grandezza | domanda a cui risponde | dove sta nel protocollo |
|---|---|---|
| tolleranza di **previsione** | l'energia predetta dal modello sta entro il 10% di quella osservata? | P3.10, `err_rel <= 10%`; P4.6/P4.7 |
| **concordanza fra metodi** | `s` e `s_EPI` allocano la stessa frazione? | P6.6 `:2608-2615`; `d`, `r` |
| **riproducibilita'** della procedura | due repliche nelle stesse condizioni danno lo stesso numero? | nessun punto congelato; e' cio' che il pre-pilota misura |

Nessuna delle tre si importa dalle altre. In particolare `err_rel <= 10%` e'
una tolleranza di previsione e **non** puo' diventare la banda di concordanza:
e' l'alternativa B di `p6_6_banda_20261025.md` §6, ed e' quella che questo
documento esclude per prima (R1 §2). Le soglie 10%/20% di P1.6 riguardano la
stabilita' della baseline e il quorum della catena (`P3.7 :1035-1052`), non la
concordanza: importarle sarebbe lo stesso trasferimento arbitrario.

**Tre regole di forma.** Ogni formulazione di §8:

1. non cambia nessun numero gia' congelato: aggiunge numeri nuovi, dichiarati
   **prima** del run che li usa;
2. non introduce un valore implicito: se un parametro manca, il piano si
   rifiuta o il campo resta nullo, non si assume un default (`s_epi_phase.py`
   gia' fa cosi' per la banda: `_load_plan :506-522`, `in_band = null`);
3. distingue cio' che e' **decisione** (un numero scelto) da cio' che e'
   **vincolo di fattibilita'** (un numero misurato che puo' solo vietare, mai
   allargare o restringere una decisione). La distinzione e' quella del
   documento del 25/10 (`p6_6_prepilota_20261025.md:339-354`) e questo
   documento la rende operativa.

**Notazione.** `[I]` implementato, `[V]` verificato su hardware, `[P]`
progettato non implementato, `[A]` da approvare.

---

## 1. Tabella decisionale

| id | oggetto | stato nel protocollo | proposta | blocca (audit §1.2) | dipende da |
|---|---|---|---|---|---|
| R1 | banda assoluta `B_abs` | aperto per testo esplicito (`:2657-2658`) | `B_abs = q·budget_pred/E_active` per configurazione, `q = 1/3`; `B_rel = 0,05` dichiarato a parte; `B_min` come veto di fattibilita' | run P6.6, campagna | P6.2 (`budget_pred`), R2, R4 |
| R2 | forma relativa | forma **non** fissata da P6.6 | `r = 2d/(s+s_EPI)`, solo con `s+s_EPI>0`; le due forme si riportano entrambe e il verdetto le richiede entrambe | run P6.6, campagna | R1 (il valore di `B_rel`) |
| R3 | aggregazione | P6.6 si ferma alla distribuzione per configurazione (`:2604-2606`); la regola a tre livelli e' proposta nel documento del 25/10 (`:62-94`) | tre livelli + nessun verdetto di studio + aggregati descrittivi esclusi dal verdetto | analisi P6.6, campagna | R1, R2, R4, R5 |
| R4 | `C`, `R`, `T`, minimo valido | aperto (`:2600-2606`); numeri proposti in `p6_6_prepilota_20261025.md:96-127` | `C = 3`, `R = 5`, `T = 420 s`, minimo 4 valide = `⌈2/3·5⌉`, nessuna sostituzione | run P6.6 (piano rifiutato se incoerente) | R1 (se D, il quorum cambia significato) |
| R5 | `engine_tree_changed` | due alternative testuali (`:2632-2633`) | si ratifica l'**esclusione**; concorre al minimo di 4 valide; causa riportata a parte | analisi P6.6 | R3, R4 |
| R6 | worker nati | semantica implementata (`worker_tree.py:184-189`), nessuna regola di lettura | braccio primario = produzione; braccio di sensibilita' solo se il tempo CPU dei nati esiste; regola di lettura pre-dichiarata | analisi P6.6 | R5, schema (una colonna in coda se si vuole il braccio numerico) |

Le voci che **bloccano il run** del pilota P2.9 restano quelle dell'audit (R7,
R10, R11). R1–R6 bloccano il run P6.6 e l'analisi: nessuna e' rinviabile
"perche' non blocca il pilota".

---

## 2. R1 — banda assoluta `B_abs`

### 2.1 Testo attuale

P6.6 `:2608-2615`:

> **Statistica e banda.** Per ogni fase valida si calcola `d = s − s_EPI` e si
> riportano distribuzione, media, mediana, dispersione e intervallo. La banda di
> concordanza si fissa **prima del primo run**, in forma assoluta e relativa, e non
> si sceglie dopo aver visto `d`. È l'unico valore che questo punto lascia aperto:
> l'unica osservazione esistente è una fase sola (0,7339 contro 0,7361,
> `srum_emi_cross_20261023_analisi.md:147-148`) e non basta a calibrarla; la banda
> va ancorata alla precisione alla quale l'attribuzione cambia una conclusione, e
> va committata prima dell'esecuzione.

e `:2657-2658`:

> **Cosa resta aperto.** La banda numerica. Tutto il resto è fissato qui e non si
> sposta dopo i dati.

Il documento del 25/10 fissa l'ancora come problema (`p6_6_prepilota_20261025.md`
§7 `:301-354`: tre candidate A1/A2/A3, regola di fattibilita', divieto di
restringere la banda) e la scelta fra A–D (`p6_6_banda_20261025.md` §6
`:119-152`). Nessuno dei due fissa un numero.

### 2.2 Alternative

| | contenuto | conseguenza |
|---|---|---|
| **A1** | `B_abs = q·budget_pred/E_active`, `q` dichiarato (proposta 1/3) | decisione ancorata a "quale parte del budget pubblicato puo' essere speso dalla differenza fra le procedure"; dipende da `budget_pred`, che esiste solo dopo P6.2 |
| **A2** | `B_rel = 5%`, `B_abs = B_rel·s_med` | convenzione dichiarata ("la seconda cifra del J/token non cambia"); disponibile subito; piu' debole per ammissione dello stesso documento (`:330-331`) |
| **A3** | `B_abs = 1 − s_med` | tetto di sanita', non banda: oltre quel valore il bracket `[E_worker, E_active]` non e' piu' interpretabile |
| **D** | nessuna banda | `in_band` resta nullo; P6.6 produce solo `d`, `r` descrittivi; richiede un'emenda a `:2608-2615`, non un silenzio |
| **B (esclusa)** | `err_rel <= 10%` | e' la tolleranza di **previsione** (P3.10). Usarla come concordanza confonde due domande e un modello che predice bene non renderebbe concordi due metodi |

**L'alternativa che il documento del 25/10 non contiene, e che serve.** A1 e A2
sono presentate come mutuamente esclusive; A1 ricava `B_rel` da `B_abs` passando
per `s_med`. La proposta qui sotto le **separa sulle due forme**: `B_abs` da A1,
`B_rel` dichiarato (5%). Motivi:

1. le due forme rispondono a due domande diverse. `B_abs` chiede "quanta energia
   puo' essere attribuita male senza cambiare la conclusione"; `B_rel` chiede
   "quanto errore relativo accetto su una frazione". Non sono la stessa cosa
   riscritta in due unita';
2. `B_rel = B_abs/s_med` importa nel criterio una grandezza **del campione
   valutato** (`s_med` delle fasi valide). Con un'ancora indipendente per la
   forma assoluta, quell'importazione non serve e il criterio smette di
   dipendere dal dataset che giudica;
3. `s_med` e' indeterminato nel testo (di quale run, di quali fasi, per
   configurazione o in pool: §9, I-2). Separare le due forme elimina
   l'indeterminatezza invece di scegliere una lettura non dichiarata.

### 2.3 Raccomandazione

**R1 = A1 per la forma assoluta, 5% dichiarato per la relativa; `B_min` come
veto.** In concreto, e in quest'ordine:

- **`B_abs,cfg = q · budget_pred / E_active,cfg`**, con `q = 1/3` e
  `budget_pred`, `E_active` dal pilota P6.2, mediana per configurazione. La
  banda e' **per configurazione**, non unica: `E_active` dipende da
  `num_predict` (32 contro 256), quindi la stessa differenza di quota vale
  energie diverse. E' il punto in cui la proposta si discosta dal singolare
  "la banda" di `:2610` e va approvato come tale (§9, I-3).
- **`B_rel = 0,05`**, dichiarato, comune alle configurazioni, con la
  motivazione di A2 (seconda cifra del J/token). Non si ricava da `B_abs`.
- **Verifica dimensionale**, che e' la ragione per cui A1 e' ancorata: `d` e'
  adimensionale, `|d|·E_active` e' l'energia attribuita male. La condizione
  `|d| <= q·budget_pred/E_active` dice esattamente "l'attribuzione sbagliata
  consuma al massimo `q` del budget predittivo pubblicato". E' la precisione
  "alla quale l'attribuzione cambia una conclusione" che `:2614` chiede.
- **`B_min` = veto**, non banda. Definizione proposta (il documento la usa a
  `:339-344` senza definirla: §9, I-1):

  ```
  B_min = max_cfg [ semi_range_i(s_i) + semi_range_i(s_EPI,i) ]   i = fasi valide
  ```

  Somma aritmetica dei due semi-range, non quadratura: e' il lato
  conservativo dichiarato in `AGENTS.md` (la quadratura sta fra `1/√2` e `1`
  della somma), e non e' una deviazione standard (P4.12). Si calcola sulle
  **distribuzioni marginali** di `s` e di `s_EPI`, **mai su `d`**: una banda
  calcolata da `d` sarebbe circolare per costruzione, una calcolata da due
  semi-range marginali no, perche' misura quanto ciascuna procedura si muove
  fra repliche, non quanto le due differiscono.
  `B_min > B_abs` (o `B_min/s_med > B_rel`) ⇒ il confronto si dichiara **non
  risolvibile a quella precisione**: la banda non si tocca, i dati non si
  toccano, la decisione passa a te. Il veto puo' solo impedire, mai rendere
  piu' facile un verdetto.
- **Come si evita di valutare gli stessi dati usati per scegliere la banda** —
  il punto che hai chiesto. Con questa architettura la banda non esce da
  nessuna fase del run che la valuta:

  | grandezza | fonte | puo' essere influenzata da `d`? |
  |---|---|---|
  | `B_abs` | `budget_pred`, `E_active` di **P6.2** | no: run diverso, grandezze diverse |
  | `B_rel` | dichiarato (5%) | no |
  | `B_min` | semi-range di `s` e `s_EPI` del run | no: non contiene `d`, e vale solo come veto |

  La garanzia strutturale e' nel codice: l'harness **non calcola** la banda, la
  legge dal piano (`_load_plan :506-522`) e senza piano lascia `in_band` nullo.
  Un'unica cosa resta fuori dal codice e va nell'audit trail: come sono nati i
  numeri del piano. Per questo la formulazione chiede che il piano sia
  committato con la derivazione dichiarata **e** che sia rifiutato se una delle
  tre grandezze manca.
- **Cosa succede se P6.2 non viene eseguito** (riserva, e' la scelta che ti
  spetta, §10): `B_abs` non ha ancora un'ancora indipendente. Le due uscite
  oneste sono (i) eseguire P6.2 prima, che il protocollo gia' prevede
  (`:2336`, `:2364-2382`), e stare nel caso qui sopra; (ii) adottare la sola
  convenzione A2 (`B_abs = 0,05·s_med`), ma allora `s_med` viene dal pre-pilota
  e il pre-pilota **non puo' essere** il run che valuta la banda: servono due
  run separati (≈6 h invece di ≈3 h). Non esiste una terza uscita che tenga
  insieme banda da `s_med` e un solo run.

### 2.4 Effetti su dati, criteri, interpretazione

- `in_band` esiste solo con banda nel piano; per le fasi bloccanti resta
  `null`, non `false` (`s_epi_phase.py:458-461`). La conseguenza per R3/R5: una
  fase senza verdetto **non e' una fase fuori banda**, e non entra nel
  numeratore di `k/n` come fallimento.
- Con D il criterio non esiste: `k/n` non esiste, e P6.6 resterebbe una
  descrizione. Va dichiarato come emenda, non come esito.
- Interpretazione, invariata da `:2617-2622`: dentro banda = concordanza nelle
  condizioni testate; non accuratezza assoluta, non "validata", non "una delle
  due e' piu' vicina all'energia fisica".
- La banda per configurazione cambia la lettura di `cfg_breve`: se `B_abs` e'
  grande rispetto al suo `s`, il test assoluto non morde e decide quello
  relativo. E' atteso, non un difetto: e' la ragione per cui le due forme sono
  in congiunzione (R2 §4).

### 2.5 Test e criteri di accettazione

Nel `--selftest` dell'harness (66 controlli oggi), da aggiungere:

1. piano senza `band` ⇒ `in_band` nullo per tutte le fasi (esiste gia':
   `:673`, `:679`);
2. piano con banda e `|d| <= B_abs`, `|r| > B_rel` ⇒ `in_band = false`;
3. piano con banda e `|d| > B_abs`, `|r| <= B_rel` ⇒ `in_band = false`
   (il caso 2 e 3 provano la congiunzione in **entrambe** le direzioni:
   oggi il selftest prova il vero e un falso, non le due direzioni);
4. `|d|` esattamente uguale a `B_abs` ⇒ `in_band = true` (il testo scrive
   `<=`, non `<`);
5. piano con `band.abs` negativo o senza `rel` ⇒ rifiuto (esiste: `:511-521`);
6. piano con `band` per configurazione e configurazione senza banda ⇒ rifiuto
   (nuovo, conseguenza di §2.3);
7. `B_min` (funzione di analisi): con due fasi identiche vale 0; con fasi
   costruite a semi-range noti vale la somma aritmetica; **non** cambia se si
   alterano solo i `d` a parita' di `s` e `s_EPI` (prova di non-circolarita').

Accettazione: `python s_epi_phase.py --selftest` stampa il nuovo conteggio e
zero fallimenti; nessun test di produzione toccato; la suite
`pytest cwEnergyModular` rieseguita in Fase 3 per provare che il conteggio 526
non cambia.

### 2.6 Dipendenze

Da **R2** (il valore di `B_rel`), **R4** (quante fasi producono i semi-range di
`B_min` e se 4 valide bastano), **R3** (cosa fa il verdetto). Da **P6.2** per
`budget_pred` ed `E_active`: e' la dipendenza che decide se il pre-pilota puo'
essere anche il run che valuta la banda (§2.3, riserva). Da **decisione E** del
documento del 25/10 (`:413`: "prima del primo run **confermativo**") senza la
quale "prima del primo run" di `:2610` non ammette nessun pre-pilota.

---

## 3. R2 — forma relativa

### 3.1 Testo attuale

P6.6 `:2608-2611` chiede la banda "in forma assoluta e relativa" e **non fissa
la formula**. La forma `r = 2d/(s+s_EPI)` e' proposta dal documento del 25/10
(`:43-60`), con la motivazione che `s_EPI` non e' una verita' ma un'altra
attribuzione (`:57-59`, che cita P4.10 `:2517-2523`). L'harness la implementa
(`:350-354`) con la guardia sulla somma. Il registro R2 la tratta come aperta:
corretto sul **valore** di `B_rel` e sul caso `s+s_EPI = 0`, non sulla forma,
che il documento del 25/10 ha gia' scelto.

### 3.2 Alternative

| forma | proprieta' | esito |
|---|---|---|
| `d/s` | mette `s` a riferimento | un errore di `s` diventa "errore di EPI" per costruzione |
| `d/s_EPI` | mette EPI a riferimento | speculare, e privilegia `s_EPI` come verita' che non e' |
| `ln(s/s_EPI)` | simmetrica, moltiplicativa | esplode vicino a zero e non ha un'interpretazione in quota di energia |
| **`2d/(s+s_EPI)`** | simmetrica, limitata: `|r| <= 2` per `s, s_EPI >= 0` | adottata |

Il limite `|r| <= 2` e' la proprieta' che conta: `r` non diverge quando una
delle due quote va a zero, quindi non produce un "fuori banda" solo perche' il
denominatore e' piccolo. Il prezzo e' che `r` **non** e' piccolo quando `d` e'
piccolo in assoluto: con `s = 0,001`, `s_EPI = 0`, `d = 0,001` si ha `r = 2`.
E' esattamente il caso in cui la forma assoluta deve mordere, ed e' la ragione
della congiunzione.

### 3.3 Raccomandazione

Adottare `r = 2·d/(s+s_EPI)` come forma relativa, con queste clausole:

- definita **solo** se `s + s_EPI > 0`; se entrambe sono zero la fase non ha
  `r`, non ha `in_band`, ed e' gia' bloccata da `albero_a_zero` o `s_assente`
  (`BLOCKING_FLAGS :284-288`), quindi il caso non produce un verdetto mancante
  per distrazione;
- `d` e `r` si riportano **entrambi** per ogni fase valida, e il verdetto
  richiede **entrambi** dentro soglia (`p6_6_prepilota_20261025.md:51-55`);
- il **segno** si riporta e non si interpreta come "chi ha ragione": `d > 0`
  dice che la quota di tempo CPU supera la quota di energia EPI, non che `s` e'
  corretta.

### 3.4 Effetti

Nessun campo nuovo: `d` e `r` sono gia' nella riga dell'harness (`:402`,
`:568`). Il verdetto resta congiuntivo. Il caso di somma nulla e' coperto dal
blocco, quindi non serve un ramo nuovo. L'interpretazione resta quella di R1
§2.4.

### 3.5 Test

1. `r(s, e) = -r(e, s)` (simmetria);
2. `r = 0` se `d = 0`;
3. `|r| <= 2` su una griglia di coppie `(s, s_EPI)` in `[0,1]²`, inclusi i
   bordi `0` e `1`;
4. `s = s_EPI = 0` ⇒ `r` nullo e nessuna eccezione;
5. formula esatta: `r = 2(s-e)/(s+e)` su una coppia nota, con confronto a
   `1e-12`;
6. il caso `s = 0,001, s_EPI = 0, d = 0,001` da' `r = 2` e la fase e' fuori
   banda **anche** se `|d|` e' minimo: e' il test che lega R1 e R2.

Accettazione: i controlli 1–6 passano; i controlli 1–4 e 6 sono nuovi.

### 3.6 Dipendenze

Da **R1** per il valore di `B_rel`: la forma non cambia, cambia la soglia. Da
**R3** per cosa significa il segno nell'aggregato. Nessuna dipendenza da R4–R6.

---

## 4. R3 — aggregazione

### 4.1 Testo attuale

P6.6 `:2600-2606` fissa `C` e `R` e chiede "la distribuzione di `d = s − s_EPI`
per configurazione e la dispersione fra configurazioni, non solo la media
complessiva". `:2608-2610` chiede "distribuzione, media, mediana, dispersione e
intervallo". **Il protocollo non dice come si passa dalla fase alla
configurazione e dalla configurazione a un esito**: la regola a tre livelli e'
una proposta del documento del 25/10 (`:62-94`), non testo congelato. L'harness
ne implementa una parte: `summarize` (`:464-500`) riporta `n_phases`,
`n_with_s_epi`, `n_with_flags`, `n_blocking`, `n_with_verdict`,
`n_window_strict`, media/mediana/min/max/range e `in_band: (k, n)`. Non
calcola `d_agg`, non emette un verdetto, non distingue le fasi di bordo.

### 4.2 Alternative

| | contenuto | esito |
|---|---|---|
| (i) | solo livello fase, nessun verdetto | non risponde alla domanda di P6.6 per configurazione |
| (ii) | verdetto a maggioranza (`k/n >= soglia`) | introduce una soglia nuova e diluisce la fase fuori banda: **esclusa** |
| (iii) | **congiuntivo** su tutte le fasi valide | una fase fuori banda e' un fatto riportabile: adottata |
| (iv) | banda sulla media di `d` | la media di rapporti e' dominata dai denominatori piccoli e nasconde la fase fuori banda: esclusa |
| (v) | `d_agg` (rapporto delle somme) come verdetto | pesa per il lavoro svolto ma non e' un verdetto: descrittiva |

### 4.3 Raccomandazione

Tre livelli, con il terzo **esplicitamente non un verdetto**:

1. **Fase** — unita' di osservazione. `in_band ∈ {true, false, null}`;
   `null` = nessun verdetto (fase bloccante), **mai** contato come `false`.
2. **Configurazione** — verdetto **congiuntivo** sulle sole fasi valide; si
   riporta `k/n`; con meno di 4 fasi valide il verdetto e' **"non
   valutabile"**, non negativo. `d_agg` e `r_agg` (rapporto delle somme,
   `:74-88`) si riportano come descrittive e **non** entrano nel verdetto ne'
   possono correggere una fase fuori banda. Le fasi di sensibilita' al bordo
   restano fuori dal verdetto e da `d_agg` (`:93-94`).
3. **Studio** — **nessun verdetto aggregato.** Si dichiara "concordanza in
   `k_cfg/C` configurazioni" e si riporta il verdetto di ciascuna per esteso.
   La ragione e' la tua: un esito favorevole aggregato non deve nascondere una
   configurazione che non soddisfa il criterio, e con `C = 3` un unico numero
   di sintesi non e' nemmeno una stima di una popolazione di condizioni.

Nessuna percentuale presentata come stima: con `R = 5` un `k/n` in percentuale
suggerirebbe una precisione che non c'e' (`:71-73`).

**Proprieta' che il verdetto deve avere, e che si testa**: se una sola fase
valida e' fuori banda, la configurazione e' fuori concordanza **qualunque**
valore assumano `d_agg` e `r_agg`. E' la traduzione operativa di "un aggregato
favorevole non nasconde una fase che non soddisfa il criterio", e non dipende
dai numeri: e' una proprieta' del codice.

### 4.4 Effetti

- Il verdetto di configurazione ha per denominatore le **fasi valide**, non le
  fasi eseguite: la differenza e' R5 (cosa consuma la tolleranza) e R4 (quante
  ne servono).
- Un esito "non valutabile" e' un esito e si riporta come tale; non si
  sostituisce con "fuori banda".
- Il livello 3 non introduce una soglia: e' una rinuncia dichiarata a
  sintetizzare, coerente con P4.12 (nessuna `sd` a `n = 3`) e con l'assenza di
  una popolazione di condizioni.

### 4.5 Test

Con righe sintetiche, gia' nel formato dell'harness:

1. tutte le fasi valide in banda ⇒ configurazione in concordanza, `k/n = n/n`;
2. una fase fuori banda ⇒ configurazione fuori concordanza, `k/n = (n-1)/n`;
3. **proprieta' di non-mascheramento**: la stessa configurazione del test 2 con
   `d_agg` e `r_agg` dentro banda resta fuori concordanza;
4. una fase `null` (bloccante) + 4 valide tutte dentro ⇒ concordanza con
   `n_with_verdict = 4`, `n_blocking = 1`;
5. 3 valide + 2 bloccanti ⇒ "non valutabile";
6. fase di sensibilita' al bordo fuori banda ⇒ non cambia il verdetto;
7. `k_cfg = 2` su `C = 3` ⇒ lo studio **non** dichiara concordanza, e il testo
   dell'esito nomina la configurazione che non la soddisfa.

Accettazione: tutti e sette passano; 3, 4, 5, 6, 7 sono nuovi.

### 4.6 Dipendenze

Da **R1** (banda), **R2** (`r`), **R4** (minimo valido), **R5** (cosa consuma la
tolleranza e cosa non produce verdetto). La proprieta' 3 dipende da come si
calcola `d_agg`: se in futuro qualcuno lo promuovesse a verdetto, il test 3
fallisce ed e' il suo scopo.

---

## 5. R4 — `C`, `R`, `T` e coerenza con il minimo valido

### 5.1 Testo attuale

P6.6 `:2600-2606`:

> **Configurazioni e repliche sono due numeri.** `C` configurazioni (modello,
> `num_predict`, concorrenza) e `R` repliche per configurazione si dichiarano prima
> del primo run. `C = 10` con `R = 1` produce dieci numeri e nessuna stima della
> variabilità entro configurazione: è una copertura di condizioni, non una
> garanzia di precisione. Il piano dichiara `R` e la sua ragione; il rapporto dà la
> distribuzione di `d = s − s_EPI` per configurazione e la dispersione fra
> configurazioni, non solo la media complessiva.

I numeri sono proposti in `p6_6_prepilota_20261025.md:96-127` (tabella e costo) e
`:405-427` (decisioni C, D, G, H). Nessuno e' congelato.

### 5.2 Alternative

| | contenuto | esito |
|---|---|---|
| `R = 3` | 9 fasi; minimo 2 valide | il range e' deciso da una sola fase anomala: ammesso dal testo, sconsigliato dal documento |
| `R = 5` | 15 fasi; minimo 4 = `⌈2/3·5⌉` | tollera una fase invalida senza introdurre una varianza |
| `R = 6` | 18 fasi; minimo 4 | +1 h di macchina, nessun guadagno sul tipo di conclusione |
| `C = 1` | una condizione | non distingue la variabilita' della procedura da quella del carico |
| `C = 3` | tre livelli di `num_predict`/concorrenza | mostra se la ripetibilita' dipende dal livello |
| `T = 360 s` | 6 minuti, 5 interni al meglio | il minimo di 5 bucket diventa un limite senza margine |
| `T = 420 s` | 7 minuti, 6 interni misurati | un minuto di margine sul minimo |
| `T = 480 s` | 8 minuti, 7 interni | +1/7 di costo per fase, nessun cambio di conclusione |
| **D** (nessuna banda) | `k/n` non esiste | il minimo valido perde la funzione di quorum e resta solo garanzia delle descrittive |

### 5.3 Raccomandazione, e la coerenza che hai chiesto di verificare

Adottare `C = 3`, `R = 5`, `T = 420 s`, minimo **4** fasi valide per
configurazione, **nessuna sostituzione** di una fase invalida. La coerenza fra i
quattro parametri e la scelta sulla banda:

- **4 = `⌈2/3·5⌉`** e' la frazione del quorum che il protocollo usa gia' per
  l'ammissibilita' dei blocchi (P4.5 `:1507-1576`: quorum `⌈2/3·n⌉ = 4` su
  `n = 6`). Non e' una soglia nuova: e' la stessa regola applicata a `R = 5`.
  Con `R = 4` il minimo sarebbe 3 e una configurazione passerebbe con tre fasi.
- **`T = 420 s` e' il minimo che sopravvive alle due perdite misurate.** 420 s
  danno 7 minuti; il contenimento stretto ne conserva **6** (misura del 25/10:
  2.582 bucket su 15.658 con `TimeInMSec > 60.000`, `p6_6_prepilota_20261025.md`
  §5.5); restano quindi 6 − 5 = **1 minuto di margine** sul minimo di 5. Con
  `T = 360 s` il margine e' zero e la fase e' persa dalla sola quantizzazione.
  Questo e' il senso in cui `T` **non e' una soglia**: e' l'aritmetica
  `T/60 − 1 (quantizzazione) >= 5 + 1 (margine)`.
- **`T` e' la finestra fra le due letture ai bordi**, non la durata del carico:
  con H il carico dura `T + 120 s` e la finestra resta `T`. Va scritto
  esplicitamente, perche' la tabella di `:102` dice "durata fase `T`" e il
  §5.2 punto 4 dice "carico per `T` (con H `T + 120`)".
- **`C = 3` e il quorum insieme hanno un costo che va dichiarato**: servono
  almeno 12 fasi valide su 15 perche' lo studio possa dire qualcosa su tutte e
  tre le configurazioni. Se una configurazione scende sotto 4, il livello 3 di
  R3 non dichiara concordanza: e' il comportamento voluto, ma significa che
  tre configurazioni moltiplicano per tre il rischio di "non valutabile". La
  mitigazione e' l'ordine: prima la fase di copertura (§5.3 del documento del
  25/10), poi le misure.
- **Se si scegliesse D (nessuna banda), R4 non cambia i numeri ma cambia
  significato**: `k/n` non esiste, il minimo di 4 protegge solo la
  riproducibilita' del range, `T` resta vincolato dal minimo di 5 bucket perche'
  `s_EPI` deve esistere. La coerenza si mantiene, ma il quorum non e' piu' un
  criterio di verdetto: va dichiarato, altrimenti 4 sembra una soglia senza
  oggetto.

### 5.4 Effetti

- Il piano dichiara `C`, `R`, `T`, il minimo valido, il numero di fasi di
  sensibilita' al bordo (**escluse da `R`**) e la fase di copertura. Un piano
  incoerente si rifiuta; non si corregge a run iniziato.
- Costo: ≈2 h 30 di macchina senza H, ≈3 h con H; piu' ≈15 min di copertura e
  ≈16 min di sensibilita' al bordo.
- Nessun campo CSV nuovo e' indispensabile: il marcatore `study` puo' stare nel
  piano (§9, I-9).

### 5.5 Test

1. piano con `C`, `R` o `T` assenti ⇒ rifiuto;
2. numero di fasi di misura per configurazione diverso da `R` ⇒ rifiuto;
3. fasi di sensibilita' conteggiate in `R` ⇒ rifiuto;
4. `T` tale che `T/60 − 1 < 5` ⇒ rifiuto, con il messaggio che nomina il
   minimo di 5 bucket;
5. `R < 2` ⇒ rifiuto (nessuna dispersione possibile);
6. configurazione con una fase invalida e 4 valide ⇒ valutabile; con 2 invalide
   ⇒ "non valutabile", e il messaggio distingue il caso da "fuori banda";
7. nessuna fase sostituita: 5 fasi eseguite restano 5 anche se una e' invalida.

Accettazione: 1–7 passano; 1, 2, 3, 4, 6 sono nuovi (5 dipende dal validatore
del piano, che oggi non esiste: `s_epi_phase.py` non legge `C`, `R`, `T`).

### 5.6 Dipendenze

Da **R1**: con D il quorum cambia significato (§5.3, ultimo punto). Da **R5**:
cosa consuma la tolleranza. Da **P6.2** solo nel ramo A1 (per `B_abs`); non per
i numeri di R4. Il costo e' una tua decisione, non un test.

---

## 6. R5 — `engine_tree_changed`: esclusione o fallback, e il conto delle fasi invalide

### 6.1 Testo attuale

P6.6 `:2596-2598` (fase valida):

> Fase valida: finestra integra, `done_reason` atteso, nessun
> `engine_tree_changed`, nessuna esclusione non dichiarata. Ogni esclusione si
> registra con la motivazione.

e `:2624-2635`:

> Quando è vero, `direct_cpu_delta` non alimenta `s`: la riga è esclusa dal
> confronto oppure il suo `s` viene dal fallback dichiarato, con la provenienza.

Lo stato del codice: il runner pone `engine_tree_changed = bool(wd.lost)`
(`benchmark_v4.py:1490`, `:1518`), `local_energy.py:662-678` non calcola la
quota e scrive `not-computed-tree-changed` con `cpu_time_share_valid = False`,
e l'harness tratta il flag come bloccante di fase (`BLOCKING_FLAGS :284-288`).

### 6.2 Alternative

| | contenuto | esito |
|---|---|---|
| (a) | **esclusione**, e la fase esclusa concorre al minimo di 4 | adottata |
| (b) | esclusione **senza** consumare la tolleranza (la fase "non conta") | allarga di fatto `R`: il numero di fasi utili dipende dalla causa, e la tolleranza non e' piu' un numero |
| (c) | esclusione oltre un tetto dichiarato di esclusioni | soglia nuova, e con `R = 5` un tetto ha senso solo se e' 1: ridondante con (a) |
| (d) | `s` dal fallback dichiarato | **non implementabile oggi**: nessun percorso produce un `s` alternativo quando l'albero cambia. Il campo `s_source` esiste nell'harness (`:402`, `phase_share :357`) ma nessuno lo popola con un fallback |

### 6.3 Raccomandazione

**R5 = (a), con la causa riportata a parte.** In dettaglio:

- La fase non produce verdetto (`in_band = null`) e **non** si sostituisce.
- **Concorre al minimo di 4 fasi valide**, come qualunque altra fase invalida.
  Motivazione: la tolleranza di `R4` esiste per assorbire una fase persa, non
  per assorbire una causa specifica; renderla gratuita per una causa
  significherebbe che il numero di fasi utili dipende dal motivo della perdita,
  e il denominatore del verdetto non sarebbe piu' un numero dichiarato nel
  piano. E' anche l'unica scelta che non introduce un tetto nuovo.
- Il conteggio distingue le cause: `n_blocking_tree_changed` separato dagli
  altri bloccanti. Serve a leggere il risultato (un'albero instabile e' un
  fatto sulla macchina, non sulla procedura), non a cambiare il verdetto.
- **La disgiunzione di `:2632-2633` si chiude sul lato "esclusione"**, perche'
  il lato "fallback" non ha produttore. Va ratificato, non lasciato aperto: un
  testo che ammette due strade e ne ha una sola implementabile e' un testo che
  produce due letture diverse dello stesso run.
- **Regola di aggregazione riga → fase, oggi non scritta** (§9, I-6):
  `engine_tree_changed(fase) = true` se **almeno una** richiesta della fase ha
  il flag a vero. E' il lato conservativo coerente con "la finestra non e'
  integra" (`worker_tree.py:187-189`): se una richiesta perde un worker, il
  `s` della fase non e' confrontabile anche se le altre tre sono pulite.

### 6.4 Effetti

- Il denominatore di `k/n` e' `n_valid = n_eseguite − n_invalide`, e la
  tolleranza e' 1 per configurazione. Due esclusioni nella stessa
  configurazione ⇒ "non valutabile" (R3 livello 2).
- Nessun campo nuovo: `engine_tree_changed`, `tree_identity_start/end`,
  `tree_born`, `tree_lost` sono gia' colonne (`casualwatt_csv_export.py:134-135`).
- Interpretazione: "non valutabile" non e' "fuori banda". Un solo numero nella
  relazione non deve dire "la procedura non concorda" quando la procedura non e'
  stata misurata.

### 6.5 Test

1. fase con `engine_tree_changed` ⇒ bloccante, `in_band` nullo, contata in
   `n_blocking` e non in `n_with_verdict` (esiste in parte: `:689`, `:727`);
2. 4 valide + 1 con albero cambiato ⇒ configurazione valutabile, `k/n` su 4;
3. 3 valide + 2 con albero cambiato ⇒ "non valutabile";
4. aggregazione riga→fase: una richiesta su quattro con flag vero ⇒ fase
   bloccante;
5. `n_blocking_tree_changed` distinto dagli altri bloccanti;
6. il verdetto primario non cambia se si aggiunge una fase bloccante a una
   configurazione che era in concordanza con 4 valide su 5.

Accettazione: tutti e sei passano; 3–6 sono nuovi.

### 6.6 Dipendenze

Da **R4** (il minimo di 4 e' il numero con cui la tolleranza interagisce) e da
**R3** (il denominatore del verdetto). Da **R6** per il caso simmetrico (la
nascita). Il ramo (d) dipende da un produttore di `s` alternativo che non
esiste: se lo si volesse, sarebbe un punto di Fase 3 con la sua emenda.

---

## 7. R6 — worker nati: come si legge la sensibilita', prima del run

### 7.1 Testo attuale

P6.6 `:2624-2635` definisce il flag come "l'insieme a `t_end` **non** e' un
sovrainsieme di quello a `t_start`", e motiva la perdita (un worker che muore
non e' piu' leggibile). La semantica del conteggio e' in
`worker_tree.py:184-189`: un nato ha `cpu_times` tutto dentro la finestra e
conta **da zero** (`:197`); chi e' presente solo a `t_start` resta fuori e alza
il flag (`:200-208`). `tree_born` e' registrato come identita'
(`casualwatt_csv_export.py:135`, `benchmark_v4.py:1491`, `:1521`), **senza il
tempo CPU**.

**Il punto che il protocollo non dice, e che R6 deve fissare.** Un nato rende
`t_end ⊃ t_start`, quindi il flag resta **falso** per costruzione: la nascita
non e' un evento escluso, e la fase e' valida. La domanda di R6 non e' "la
escludiamo" (no: `:2631` la vuole dentro), e' **come si legge una fase con una
nascita**, prima di vedere i risultati.

### 7.2 Un fatto che orienta la scelta

`s_EPI` aggrega per **eseguibile**, non per PID: l'albero e' `ollama.exe` +
`llama-server.exe` + `ollama app.exe` (P6.6 `:2589-2590`). Un worker nato ha lo
stesso AppId del padre, quindi la sua energia entra in `s_EPI` **e** il suo
tempo CPU entra in `s`, entrambi dall'istante di nascita. La nascita e'
**simmetrica** fra le due procedure; la perdita **no** (il tempo CPU di un
morto sparisce dal numeratore di `s`, mentre la sua energia resta attribuita
all'AppId in SRUM). Questa asimmetria e' la ragione per cui `:2631` esclude la
perdita e non la nascita, e va scritta: oggi e' solo implicita.

### 7.3 Alternative

| | contenuto | esito |
|---|---|---|
| (i) | nessuna analisi della natalita' | la nascita resta invisibile a ogni conteggio: non accettabile, perche' `tree_born` e' registrato proprio per questo |
| (ii) | **diagnostica**: conteggio delle fasi con almeno un nato, e delle identita' riusate | disponibile subito, nessuna colonna nuova |
| (iii) | (ii) + **braccio di sensibilita' numerico**: `s` ricalcolato sulla sola intersezione dell'albero | richiede il tempo CPU dei nati, che **non** e' registrato: una colonna nuova in coda |
| (iv) | escludere le fasi con nascite | contraddice `:2631` e ridurrebbe le fasi utili senza una ragione misurata |

### 7.4 Raccomandazione, con la regola di lettura pre-dichiarata

Adottare **(ii) ora**, con la regola che rende **(iii)** attivabile senza
cambiare le conclusioni a posteriori:

1. **Braccio primario = comportamento di produzione**: tempo CPU intero dalla
   nascita (`worker_tree.py:184-189`). E' cio' che la campagna usera', quindi e'
   l'unico primario difendibile.
2. **Braccio di sensibilita' = sola intersezione** dell'albero. Si calcola
   **solo se** il tempo CPU dei nati e' registrato; oggi non lo e'
   (`tree_born` porta identita', non tempo), quindi il braccio non e'
   disponibile senza una colonna in coda. Il documento non lo dà per fatto.
3. **Attivazione senza soglie**: il braccio si calcola su **tutte** le fasi con
   almeno un nato, quante che siano. Nessuna soglia sul numero di nascite, sul
   loro tempo o sulla loro frazione: sarebbe un parametro nuovo, e con `R = 5`
   non sarebbe stimabile.
4. **Regola di lettura, identica nei due sensi** (e' il punto che hai chiesto):
   se i due bracci danno lo stesso verdetto, la fase non e' ambigua e si
   riporta il primario con la nota che la natalita' non sposta nulla. Se danno
   verdetti **diversi**, il verdetto **primario resta** — non si sceglie il
   braccio dopo aver visto i risultati — la fase si annota
   `nascita_non_stabile`, e la relazione scrive che quella fase **non
   distingue** le due procedure dalle due trattazioni della natalita'. Nessuna
   fase si scarta perche' il braccio secondario e' sfavorevole.
5. **Se la divergenza riguarda tutte le fasi di una configurazione**, la
   conclusione su quella configurazione si riporta come **condizionata al
   trattamento della natalita'** e non si dichiara ne' concordanza ne'
   discordanza. E' un esito, non un guasto da aggirare.
6. **Se non si osserva nessuna nascita**, si riporta "trattamento della
   natalita' non esercitato" e il punto 4 non si applica: e' un'informazione
   sulla macchina, non sull'assenza dell'effetto.

### 7.5 Effetti

- Nessun campo nuovo per (ii): `tree_born` e' gia' una colonna.
- (iii) richiede **una** colonna in coda (per esempio `worker_born_cpu_s`),
  quindi un'emenda allo schema, compatibile e in coda come le tre colonne per
  token di Emenda 8. Non si fa in Fase 2.
- La lettura non cambia il verdetto primario in nessun caso: cambia cio' che si
  scrive accanto. E' la ragione per cui questa regola puo' essere fissata
  adesso, prima dei dati, senza decidere nulla sul risultato.
- Con (ii) soltanto, il limite va dichiarato: la natalita' e' **osservata**, non
  **quantificata**.

### 7.6 Test

1. fase con `tree_born` non vuoto ⇒ `n_phases_with_birth` cresce e la fase
   resta valida (`engine_tree_changed = false`);
2. due identita' con lo stesso PID in `tree_born` e `tree_lost` ⇒ riuso del PID
   riportato come diagnostica (il delta lo calcola gia': `worker_tree.py:201-203`);
3. matrice di interpretazione sui quattro casi (primario dentro/fuori ×
   sensibilita' dentro/fuori): ognuno produce l'etichetta pre-dichiarata al
   punto 4–5, e in nessun caso il verdetto primario cambia;
4. sensibilita' non disponibile (colonna assente) ⇒ nessun errore, nessun
   braccio inventato, la nota "osservata non quantificata" compare;
5. nessuna nascita ⇒ "non esercitato".

Accettazione: 1, 2, 4, 5 passano con (ii); 3 richiede (iii) e si accetta solo
insieme alla colonna nuova. Il test 3 e' quello che impedisce la scelta del
braccio a posteriori: se qualcuno in futuro rendesse selezionabile il braccio,
il test 3 deve fallire.

### 7.7 Dipendenze

Da **R5** (flag e aggregazione riga→fase) e **R3** (dove finisce l'etichetta
`nascita_non_stabile`). Da una decisione sullo schema per (iii). Da nessuna
soglia.

---

## 8. Formulazioni esatte da approvare

Da incollare, se approvate, in un'emenda datata a P6.6. Ogni blocco e'
autosufficiente; nessuno modifica un numero gia' congelato.

> **F-R1 — banda di concordanza (integra «Cosa resta aperto», P6.6 `:2657-2658`).**
> La banda di concordanza si fissa, prima del run che la valuta e per ogni
> configurazione `cfg`, in due numeri indipendenti:
> `B_abs,cfg = q · budget_pred,cfg / E_active,cfg` con `q = 1/3`, e
> `B_rel = 0,05`. `budget_pred` ed `E_active` sono la mediana delle fasi valide
> del pilota P6.2; `B_rel` non si ricava da `B_abs` e nessuno dei due dipende da
> una grandezza della fase valutata. Una fase e' in concordanza se e solo se
> `|d| <= B_abs,cfg` **e** `|r| <= B_rel`. Se il piano non contiene la banda
> `in_band` resta nullo: nessun valore implicito. `B_min = max_cfg
> [semi_range(s) + semi_range(s_EPI)]`, calcolato sulle distribuzioni marginali
> e mai su `d`, e' un veto di fattibilita': se `B_min > B_abs,cfg` oppure
> `B_min/s_med > B_rel`, il confronto si dichiara non risolvibile a quella
> precisione, la banda non si restringe ne' si allarga, e la decisione torna
> all'utente. Il piano e' rifiutato se una delle tre grandezze manca.

> **F-R2 — forma relativa.** `r = 2·d/(s + s_EPI)`, calcolato solo se
> `s + s_EPI > 0`; con `s = s_EPI = 0` la fase non ha `r` e non ha verdetto.
> `d` e `r` si riportano entrambi per ogni fase valida e il verdetto richiede
> entrambi dentro soglia. `r` non e' una deviazione e non si usa da solo: e' una
> differenza relativa simmetrica, con `|r| <= 2` per costruzione. Il segno si
> riporta e non si interpreta come indicazione di quale procedura sia corretta.

> **F-R3 — tre livelli e verdetto.** (i) Fase: `in_band` vale vero, falso o
> nullo; nullo per le fasi senza verdetto, mai falso. (ii) Configurazione:
> verdetto congiuntivo sulle fasi valide, si riporta `k/n`; con meno di 4 fasi
> valide il verdetto e' "non valutabile". `d_agg` e `r_agg`, rapporto delle
> somme, sono descrittive e non entrano nel verdetto ne' possono correggere una
> fase fuori banda; le fasi di sensibilita' al bordo restano fuori dal verdetto
> e da `d_agg`. (iii) Studio: nessun verdetto aggregato; si dichiara
> "concordanza in `k_cfg/C` configurazioni" con il verdetto di ciascuna
> riportato per esteso. Nessuna percentuale e' presentata come stima.

> **F-R4 — disegno.** `C = 3`, `R = 5`, `T = 420 s`, dove `T` e' la finestra fra
> le due letture ai bordi e con H il carico dura `T + 120 s`. Minimo 4 fasi
> valide per configurazione, cioe' `⌈2/3·5⌉`, la frazione del quorum di P4.5.
> Una fase invalida non si sostituisce. Se in una configurazione restano meno di
> 4 fasi valide, la configurazione e' "non valutabile" e lo studio non dichiara
> concordanza in quella configurazione. `T` non scende sotto 420 s: 7 minuti
> meno i 2 di quantizzazione misurata lasciano 5 interni, senza margine per un
> minuto perso per un'altra ragione. Il piano e' rifiutato se `C`, `R` o `T`
> mancano, se il numero di fasi di misura per configurazione non e' `R`, se le
> fasi di sensibilita' sono conteggiate in `R`, o se `T/60 − 1 < 5`.

> **F-R5 — `engine_tree_changed`.** Si ratifica l'esclusione: la fase non
> produce verdetto e non si sostituisce, e concorre al minimo di 4 fasi valide
> come qualunque altra fase invalida. La causa si riporta a parte
> (`n_blocking_tree_changed` distinto dagli altri bloccanti). Una fase ha
> `engine_tree_changed = true` se almeno una delle sue richieste ha la riga a
> vero. Il ramo "`s` dal fallback dichiarato" non e' disponibile e resta
> chiuso.

> **F-R6 — natalita' dell'albero.** Il braccio primario e' il comportamento di
> produzione: tempo CPU intero dalla nascita. Il braccio di sensibilita' e' `s`
> ricalcolato sulla sola intersezione dell'albero e si calcola solo se il tempo
> CPU dei nati e' registrato; attivazione su tutte le fasi con almeno un nato,
> senza soglie. Se i due bracci danno lo stesso verdetto, si riporta il primario
> con la nota che la natalita' non sposta nulla. Se danno verdetti diversi, il
> verdetto primario resta, la fase si annota `nascita_non_stabile` e la
> relazione dichiara che quella fase non distingue le due procedure dalle due
> trattazioni della natalita'; nessun braccio si sceglie dopo aver visto i
> risultati e nessuna fase si scarta perche' il braccio secondario e'
> sfavorevole. Se la divergenza riguarda tutte le fasi di una configurazione, la
> conclusione su quella configurazione si riporta come condizionata al
> trattamento della natalita'. Se non si osserva nessuna nascita, si riporta che
> il trattamento non e' esercitato. Senza il tempo CPU dei nati la natalita' e'
> osservata, non quantificata.

---

## 9. Punti che il protocollo lascia indeterminati

Non li colmo: o la proposta dice come li tratterebbe (e allora e' dichiarata),
o restano a te.

| id | punto | dove | stato in questa proposta |
|---|---|---|---|
| I-1 | `B_min` e' usato nella regola di fattibilita' e **non e' definito** | `p6_6_prepilota_20261025.md:339-344` | definizione proposta in F-R1, dichiarata come nuova |
| I-2 | `s_med` di A1: di quale run, quali fasi, per configurazione o in pool | `:318-322`, `:343` | evitato: `B_rel` e' dichiarato, non derivato da `s_med` |
| I-3 | la banda e' singolare ("la banda", `:2610`), ma `E_active` dipende da `num_predict` | P6.6 `:2610` | proposta per configurazione, da ratificare |
| I-4 | P6.6 chiede "dispersione" (`:2609`) senza definirla; P4.12 vieta la `sd` a `n = 3` e tace su `R = 5` | `:2609`; P4.12 | proposta: min/mediana/max/range, nessuna `sd` anche a `R = 5`, perche' le fasi non sono campioni indipendenti |
| I-5 | non esiste una regola di esito per lo **studio** (il documento del 25/10 si ferma alla configurazione) | `p6_6_prepilota_20261025.md:62-94` | proposto: nessun verdetto, `k_cfg/C` |
| I-6 | aggregazione riga→fase di `engine_tree_changed` non scritta | P6.6 `:2596-2598` | proposta: "almeno una richiesta" |
| I-7 | la disgiunzione di `:2632-2633` ammette due strade, una sola implementabile | P6.6 `:2632-2633` | chiusa sul lato esclusione in F-R5 |
| I-8 | la nascita e' invisibile al flag **per definizione** (`:2631` chiede il sovrainsieme): la conseguenza non e' scritta | P6.6 `:2631` | dichiarata in R6 §7.1 e nella motivazione di F-R6 |
| I-9 | `study` e' proposto "in ogni artefatto" senza dire dove: campo del piano o colonna CSV | registro `:236-241` | proposta: campo del piano; colonna solo con emenda |
| I-10 | "prima del primo run" (`:2610`) non ammette nessun pre-pilota | P6.6 `:2610` | dipende dalla decisione E (`p6_6_prepilota_20261025.md:413`), fuori da R1–R6 |
| I-11 | il pre-pilota e' uno studio di calibrazione separato o e' il run P6.6? cambia circolarita' e costo | `p6_6_prepilota_20261025.md` §1 `:9-37` contro §7 `:339-354` | **aperto, decisione tua** (§10) |

---

## 10. Cosa aspetta la tua approvazione

Sei formulazioni (F-R1…F-R6) e quattro scelte che non posso fare al tuo posto:

1. **R1, ramo**: P6.2 prima del run che valuta la banda (allora un solo run,
   ≈3 h) **oppure** sola convenzione A2 con due run separati (≈6 h)? La prima
   e' coerente con il protocollo che gia' prevede `budget_pred`; la seconda non
   dipende da P6.2 ma raddoppia il tempo di macchina.
2. **`q = 1/3`** (`p6_6_prepilota_20261025.md:322`, decisione B): confermato?
3. **`study`**: campo del piano e basta, o colonna CSV in coda con emenda?
   La colonna e' l'unica forma che sopravvive a una concatenazione di CSV.
4. **R6, braccio numerico**: si autorizza la colonna in coda per il tempo CPU
   dei nati, o si resta alla diagnostica dichiarata come "osservata non
   quantificata"?

E una precisazione che riguarda tutto: **`B_abs` resta senza numero finche' P6.2
non produce `budget_pred`**. Se vuoi un numero adesso, l'unica strada e' A2 con
due run; non c'e' un terzo modo che tenga insieme banda da `s_med` e un solo
run senza circolarita'.

Nessuna implementazione comincia prima della tua approvazione. Le modifiche di
Fase 3, quando autorizzate, saranno: estensione del `--selftest` dell'harness,
validatore del piano, `d_agg`/`r_agg` e i tre livelli in `summarize`, banda per
configurazione nel piano, eventuale colonna in coda — ognuna con i suoi test e
la suite intera rieseguita.

---

## 11. Ancore verificate oggi

Rilette in questo turno, non ricostruite a memoria:

* `experiment_results/protocollo_v4_20261024.md`: `:2352-2363` (P6.1),
  `:2364-2382` (P6.2), `:2384-2408` (P6.3), `:2547-2557` (P6.6 non e' un
  anello), `:2559-2571` (le tre grandezze), `:2573-2594` (definizioni di `s` e
  `s_EPI`, albero per eseguibile), `:2596-2598` (fase valida), `:2600-2606`
  (`C`, `R`), `:2608-2615` (banda), `:2617-2622` (risultato e interpretazione),
  `:2624-2635` (`engine_tree_changed`), `:2657-2658` (cosa resta aperto);
  `:1035-1052` (P3.7), `:1054-1071` (P3.8), `:1507-1576` (P4.5, quorum);
* `experiment_results/p6_6_prepilota_20261025.md`: `:9-37` (§1), `:39-60` (§2
  definizioni), `:62-94` (§3 aggregazione), `:96-127` (§4 disegno e costo),
  `:301-354` (§7 ancora A1/A2/A3 e regola di fattibilita'), `:405-427` (§11
  decisioni A–H), `:429-437` (file esaminati);
* `experiment_results/p6_6_banda_20261025.md` §6 `:119-152` (alternative A–D);
* `experiment_results/fase_b_registro_decisioni_20261028.md`: R1–R6 `:73-321`,
  tabella delle dipendenze `:709-731`;
* `experiment_results/fase_b_audit_20261029.md` §1–§3 (classificazione e
  riscontri F1–F8);
* `s_epi_phase.py`: `:106` (`MIN_BUCKETS_PER_PHASE`), `:284-291`
  (`BLOCKING_FLAGS`, prefissi), `:350-354` (`relative_symmetric`), `:387-461`
  (`evaluate_phase`), `:458-461` (`in_band` solo senza blocco), `:464-500`
  (`summarize`, `n_with_verdict :493`, `in_band :496`), `:506-522`
  (`_load_plan`: la banda viene dal piano, mai calcolata), `:581` (`--selftest`);
* `cwEnergyModular/energy/worker_tree.py`: `:178-210` (delta, nato da zero
  `:197`, perdita `:200`, riuso di PID `:201-203`);
* `cwEnergyModular/casualwatt_csv_export.py`: `:118-138` (integrita' del
  numeratore, `engine_tree_changed`, `tree_identity_*`, `tree_born`,
  `tree_lost`);
* `cwEnergyModular/benchmark_v4.py`: `:1490-1491`, `:1518-1521` (flag e
  identita' per riga);
* `cwEnergyModular/energy/local_energy.py`: `:662-678` (quota non calcolata con
  l'albero cambiato), `:712-734` (nome storico e nome del protocollo).

Non eseguito in questo turno: nessun `pytest`, nessun `--selftest`, nessun run,
nessun `powercfg`, nessun accesso al contatore EMI o PawnIO. Il conteggio di
riferimento della suite resta 526 = 523 + 3 di `AGENTS.md`, non rigenerato qui.
