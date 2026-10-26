# Valutazione della revisione esterna di quinto turno (2026-10-26)

**Provenienza del materiale.** Il documento valutato è `revisione tecnica di
P4.docx`, alla radice del repository e **non tracciato** (materiale dell'utente,
come gli altri `.DOCX`). Si presenta come "revisione tecnica dettagliata e
rigorosa della Sezione P4" e dichiara in testa di non aver modificato file, di
non aver alterato i pesi WLS di P3.8 e di aver verificato la coerenza fra
protocollo, codice e `references.bib`. Per AGENTS.md è **spunto, non evidenza**:
ognuna delle sue affermazioni è stata verificata contro
`protocollo_v4_20261024.md` nella revisione corrente e, dove era numerica,
**per esecuzione** con l'harness tracciato
`inviluppo_e_budget_pred_probe.py` (output
`experiment_results/inviluppo_budget_pred_console_20261026.txt`, 5/5 verifiche,
exit 0).

**Esito in una riga.** I tre difetti dichiarati (D1, D2, D3) e la
raccomandazione (R1) **non sono riprodotti dal testo congelato**: ciascuno cita
come "evidenza verificabile" un contenuto che nel protocollo non c'è. Nessuna
delle quattro correzioni proposte è applicabile, e due di esse — se applicate —
introdurrebbero un difetto dove oggi non ce n'è. Del documento si adottano due
cose, entrambe diverse da ciò che propone: l'**idea** di una suite di test sulla
geometria che non dipenda dall'hardware (realizzata in forma corretta:
`cwEnergyModular/tests/test_protocollo_p4_geometry.py`, 17 test) e la
formulazione GUM dell'ipotesi di ortogonalità, che è materiale utile per la
decisione ancora aperta di P1.7.

| id | sezione citata | cosa afferma | verifica | esito |
|---|---|---|---|---|
| D1 | "P4.2" | l'inviluppo è dichiarato con 5 vertici `(8,4) (32,32) (512,32) (512,256) (32,256)` e omette `(32,4)` | la sezione non esiste con quel contenuto: l'inviluppo sta in **P4.7** `:1827` e dichiara **quattro** vertici `(8,4) (512,32) (512,256) (32,256)`; `:1830-1833` dice esplicitamente che `(32,32)` **non** è un vertice e corregge una lista a cinque già circolata | **respinto**: l'insieme di punti usato dalla revisione non è quello di P3.5 |
| D2 | "P4.3 – P4.4" | `budget_pred² = budget_fit² + u_edge² + u_model²` sommerebbe un `u_model` adimensionale | la formula non esiste: `grep u_model` su 3455 righe dà **0 occorrenze**. La formula congelata è `budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²` (P4.6 `:1624`, P4.3 `:1392`, F.11 `:2934`), tre termini tutti in joule | **respinto**: la correzione proposta introdurrebbe il difetto che denuncia |
| D3 | "P4.5" | P4 conterrebbe notazione del modello cloud C5 (`γ_prefill`, `N_in²/N_out`) nei vincoli di T2 | `grep` su tutto il protocollo: nessuna occorrenza di `γ_prefill`, `γ_decode` o `N_in²/N_out`; `sweetspot` compare **una volta sola**, a `:1966`, come citazione del limite di copertura | **respinto**: il testo citato non esiste |
| R1 | "P4.5" | il testo userebbe `p > 0.05` di un test di omoschedasticità come prova dell'assenza di eteroschedasticità | nessun test di Breusch-Pagan o di White in tutto il protocollo; il criterio `p ≥ 0,05` è quello del **lack-of-fit** permutazionale (P3.9 `:1101`, anello 5 di P4.9 `:2095`), e la fallacia che R1 denuncia è già scritta come motivazione: `:1058` "un test poco potente può 'passare' con uno scarto grande", `:1076-1078` "un `p` troppo grande premia la bassa potenza" | **respinto nell'evidenza**, principio già in vigore; la soglia nuova `|ρ| ≤ 0,35` è **non adottata** |

---

## 1. D1 — l'inviluppo convesso di progetto

**Cosa afferma la revisione.** Che i 10 punti nominali di griglia congelati in P3
siano

```
P = {(8,4),(8,32),(8,128),(8,256),(32,4),(32,32),(32,128),(32,256),(512,32),(512,256)}
```

e che quindi l'inviluppo abbia i vertici `(8,4) (32,4) (512,32) (512,256)
(8,256)`. Aggiunge che il protocollo dichiara una cinquina contenente `(32,32)`,
che `(32,4)` è stato "erroneamente omesso", e che l'omissione "mutila
l'inviluppo" escludendo illegittimamente dal Livello A la regione
`N_in ∈ [8,32], N_out ∈ [4,32]`.

**Verifica, per esecuzione.** Il disegno congelato è P3.5 `:954-963`:

| punto | `N_in` target | `N_out` target | blocchi | nel fit |
|---|---|---|---|---|
| griglia 3×3 | 32, 128, 512 | 32, 128, 256 | 3 per cella (27) | sì |
| centro | 128 | 128 | 6 totali | sì |
| minimo | 8 | 4 | 3 | sì |
| conferma operativa | 12 | 32 | 3 | no |
| conferma alta | 256 | 192 | 3 | no |

I 10 punti di fit sono dunque `{32,128,512} × {32,128,256}` **più** `(8,4)`.
L'insieme della revisione contiene **quattro punti che non sono di disegno** —
`(8,32)`, `(8,128)`, `(8,256)`, `(32,4)` — e ne **omette quattro** che lo sono —
`(128,32)`, `(128,128)`, `(128,256)`, `(512,128)`. Conta 10 elementi perché
scambia quattro punti reali con quattro inventati. Dall'insieme sbagliato segue
l'inviluppo sbagliato, e infatti due dei cinque vertici proposti — `(32,4)` e
`(8,256)` — non appartengono al disegno.

Con l'insieme reale, la catena monotona di Andrew (implementata nell'harness
senza dipendenze, perché l'inviluppo decide un campo obbligatorio e va
ricontrollabile a mano) restituisce esattamente i quattro vertici dichiarati:

```
calcolati   : (8,4) (512,32) (512,256) (32,256)
P4.7:1827   : (8,4) (512,32) (512,256) (32,256)
P4.14:2225  : (8,4) (512,32) (512,256) (32,256)
```

`(32,32)` sta dentro con margine **21,2372** token, e il protocollo lo scrive a
`:1830` ("`(32,32)` **non** è un vertice: sta dentro l'inviluppo con un margine
di 21,2 token"). A `:1831-1833` c'è anche la correzione esplicita di una
"lista a cinque vertici circolata in chat", con la ragione geometrica: il
poligono con `(32,32)` fra `(8,4)` e `(512,32)` **non è convesso**. La revisione
ripropone una lista a cinque, con due vertici diversi.

I quattro margini pubblicati si rigenerano tutti a 0,01 token, con la metrica
congelata dalla quinta emenda (distanza perpendicolare euclidea dalla retta dello
spigolo, coordinate grezze):

| punto | perpendicolare | pubblicato | dal vertice più vicino |
|---|---|---|---|
| `(12,32)` | 1,3273 | 1,33 | 28,2843 |
| `(256,192)` | 64,0000 | 64,00 | 232,9635 |
| `(32,32)` | 21,2372 | 21,24 | 36,8782 |
| `(128,128)` | 107,7031 | 107,70 | 160,0000 |

Il rapporto delle due metriche su `(12,32)` è **21,3**, il valore che P4.7 `:1888`
usa per giustificare la scelta.

**Il punto sostanziale non è la geometria, è il flag.** La revisione (§1.2)
conclude che il punto di produzione `(12, 31,8)` "cade **pienamente**
all'interno del Livello A", calcolando la soglia sul bordo inferiore del *suo*
inviluppo (`N_out ≥ 4 + (28/504)·(N_in − 8) = 4,22` per `N_in = 12`). Con
l'inviluppo reale il margine è **1,327 token**, sotto la soglia di 2: il punto è
in fascia A **con `thin_support = true`** (P4.7 `:1851-1855` e `:1907`).
L'avverbio "pienamente" cancella un flag obbligatorio, cioè dichiara un supporto
di progetto pieno dove il protocollo dice che è sottile e che a sostenerlo è il
punto di conferma empirico di P3.10, non la geometria. Se la correzione D1 fosse
applicata, il flag sparirebbe dal punto più importante della campagna: quello su
cui si pubblica il `J/token` di produzione.

**Esito: respinto.** Nessun cambiamento al protocollo. La regione che la
revisione vorrebbe recuperare in fascia A — `N_in` basso con `N_out` fra 4 e 32 —
contiene un solo punto misurato, `(8,4)`, e dichiararla coperta significherebbe
spacciare per interpolazione un'estrapolazione, che è l'errore per cui P4.7
esiste (`:1816-1819`).

---

## 2. D2 — la dimensionalità di `budget_pred`

**Cosa afferma la revisione.** Che il protocollo definisca `z_b = r_b /
budget_fit_b` (adimensionale) e poi tratti il percentile dei residui bootstrap
come un termine in joule dentro `budget_pred,b² = budget_fit,b² + u_edge,b² +
u_model,b²`, producendo una "somma algebrica/quadratica non omogenea tra
grandezze dimensionali `[J²]` e adimensionali `[1]`". Propone
`u_model(x) = budget_fit(x) · z_0.975*` e, nel test di accettazione (§7), fissa
`z_975 = 1.96`.

**Verifica.** La premessa è falsa su due punti, entrambi controllabili:

1. **`u_model` non esiste.** `grep -n "u_model"` sul protocollo (3455 righe) dà
   zero occorrenze. La formula congelata è scritta tre volte nello stesso modo —
   P4.6 `:1624`, P4.3 `:1392`, F.11 `:2934`:

   ```
   budget_fit_b²  = u_base,b² + u_within,b²                 # ≡ budget_b di P3.8
   budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²   # per ogni numero pubblicato
   ```

   I tre termini sono `budget_fit_b` (joule, sulla scala di `Ē_b`, dichiarata
   dalla quinta emenda a `:1641-1647`), `u_edge,b = 2 · P_peak,b · δt_edge,b`
   (`[W]·[s] = [J]`, P4.3 `:1388`) e `u_bias,b = |bias_w| · Δt̄_W,b`
   (`[W]·[s] = [J]`, P4.3 `:1391`). L'omogeneità è verificata per esecuzione
   nell'harness: scalare i tre ingressi di `k` scala il risultato di `k` a
   `1e-12`.

2. **Il residuo standardizzato non entra mai da solo in una grandezza
   energetica.** L'incertezza di modello si propaga dal bootstrap di P4.8, che
   costruisce dati sintetici

   ```
   Ȳ*_b = f(x_b ; θ̂) + budget_fit_b · z*_b        (P4.8:1983)
   ```

   cioè moltiplica `z*_b` per il budget del blocco **prima** di usarlo: il
   prodotto è in joule per costruzione. Si rifitta poi WLS sugli sintetici e si
   prendono i quantili di `f(x; θ*)`, che sono in joule, allargati con il
   `budget_pred` del blocco nuovo (`:2000-2001`). Non c'è nessun percentile di
   `z` da riscalare, perché nessun percentile di `z` entra in `budget_pred`.

**Cosa produrrebbe la correzione proposta, misurato.** Sostituire il bootstrap
con `u_model = 1,96 · budget_fit` dà, a `u_edge` nullo:

| `budget_fit` [J] | congelato [J] | proposto [J] | rapporto |
|---|---|---|---|
| 0,001 | 0,001000 | 0,002200 | 2,200364 |
| 0,010 | 0,010000 | 0,022004 | 2,200364 |
| 0,050 | 0,050000 | 0,110018 | 2,200364 |
| 1,000 | 1,000000 | 2,200364 | 2,200364 |
| 100,0 | 100,000000 | 220,036400 | 2,200364 |

Il fattore è `sqrt(1 + 1,96²) = 2,200364` **identico per ogni blocco**: non
contiene informazione dai dati, perché `u_model` è proporzionale a `budget_fit`
per costruzione. Con `u_edge > 0` il fattore scende (2,1990 a `u_edge = 0,002` su
`budget_fit = 0,050`; 2,0182 a `u_edge = 0,5` su `budget_fit = 1`), quindi la
sostituzione non è nemmeno conservativa in modo uniforme: allarga di più i
blocchi con il termine di bordo piccolo, che non sono i blocchi più incerti. E
soprattutto perde ciò che il bootstrap propaga davvero — lo spread dei
coefficienti `θ*` sui 2000 rifit — sostituendolo con una costante.

C'è anche un conflitto di ipotesi, non solo di algebra. P4.8 `:1987-1989`
scrive: "Standardizzare per `budget_fit_b` invece che per una σ stimata è la
scelta coerente con P1.7 e P3.8: **non assume gaussianità dei residui fisici su
33 punti**, non introduce un fattore `√m` fittizio e conserva la natura
conservativa dei budget". `z_0.975* = 1,96` **è** il quantile della normale
standard: adottarlo reintroduce esattamente l'ipotesi che il testo esclude, e la
reintroduce in un punto congelato.

**Esito: respinto.** La verifica dimensionale che la revisione chiede è giusta
come principio ed è stata eseguita: il risultato è che la formula congelata la
soddisfa. Resta nel repository come test
(`test_budget_pred_omogeneo_grado_uno`,
`test_budget_pred_solo_fit_unchanged`, `test_bootstrap_sintetico_in_joule`,
`test_u_model_proposto_fattore_costante`), così la prossima proposta dello stesso
tipo trova un'esecuzione invece di un parere.

---

## 3. D3 — la notazione C5 dentro il modello locale T2

**Cosa afferma la revisione.** Che "nel testo della bozza P4 si fa riferimento a
vincoli di positività su coefficienti analitici quali `γ_prefill`, `γ_decode` o
forme quadrate `N_in²/N_out` tipiche del modello Cloud C5 (SweetSpot)", e propone
di restringere il gate G4 su `a0 > 0, a1 > 0, a2 > 0, c ≥ 0`.

**Verifica.** Il testo citato non esiste. Sul protocollo completo: nessuna
occorrenza di `γ_prefill`, `γ_decode`, `N_in²/N_out`; `sweetspot` compare una
volta sola, a `:1966`, ed è la citazione del **limite di copertura** ("la v4 non
pubblica un `J/token` per prompt lunghi (`N_in > 512`), che è esattamente ciò che
la letteratura analitica chiede (`cavagna2026sweetspot`)"). Il modello locale è
scritto in P3.3 `:877-890` con i coefficienti `(E0, a, b, c)` — non
`(a0, a1, a2, c)` — e P3.4 `:928-929` li qualifica già per coordinata.

**Nel merito, la proposta non è comunque adottabile, per tre ragioni.**

1. **Non è un gate nuovo, è un settimo anello.** La catena di validazione è
   congelata a **sei** anelli (P4.9 `:2090-2096`) e AGENTS.md scrive: "'Validata'
   è una parola sola. Si scrive solo se tutti e sei gli anelli di P4.9 passano".
   Aggiungere un gate di positività cambia il significato di `chain_status =
   validated` su un protocollo congelato, e la revisione lo chiama "G4", che nel
   progetto è già il nome di un'altra cosa: i gate `G0-G4` della specifica per
   dominio (`metodi_per_dominio_20261025_spec.md`), dove G4 è proprio la catena
   dei sei anelli. Sarebbe la terza tassonomia con lo stesso nome.
2. **Le positività richieste sono già coperte, con strumenti più adatti.**
   `c ≥ 0` è un'**attesa** dichiarata con la sua ragione fisica (P3.4 `:891`: "la
   KV cache cresce con `N_in`"); il segno di `E0` ha il flag
   `intercept_nonphysical` (P3.9 `:1065`); e la previsione non positiva è già un
   **fallimento** con il flag `pred_nonpositive` (P3.10 `:1154-1168`, anello 6).
   Un vincolo `a1 > 0` stretto sui coefficienti non è giustificato: un costo
   marginale può essere legittimamente piccolo, e imporlo a priori trasformerebbe
   un esito dei dati in un presupposto del fit.
3. **La revisione stessa contraddice il proprio assunto.** Al §4.1 scrive
   `c ≥ 0` per l'interazione e poi al §4.1/D3 chiede `a0 > 0, a1 > 0, a2 > 0`
   stretti: tre disuguaglianze strette e una larga, senza dire perché il
   trattamento dell'interazione debba essere diverso da quello dei termini
   lineari.

**Esito: respinto.** Nessuna notazione cloud entra in P4 — e la separazione è
già netta: il modello cloud C5 sta in
`experiment_results/metodo_analitico_cloud_20261026.md`, con i coefficienti
`k_over/k_pre/k_dec/k_attn/k_ratio`, e la sua §2.2 rifiuta la notazione `α/β/γ`
proprio per collisione con `GPU_ENERGY_ALPHA/BETA/GAMMA` di ML.ENERGY
(`impacts/llm.py:10-12`).

---

## 4. R1 — il `p`-value come prova di assenza

**Cosa afferma la revisione.** Che il testo citi "p-value del test di
omoschedasticità `p > 0.05` come prova dell'assenza di eteroschedasticità", che
su 33 misurazioni i test di Breusch-Pagan o White abbiano potenza bassissima, e
che il Gate G3 vada integrato con "correlazione di Rank di Spearman tra `|z_b|`
ed `E_att` non superiore a 0.35".

**Verifica sull'evidenza.** Nessun test di Breusch-Pagan o di White compare nel
protocollo (`grep`: zero occorrenze), e non esiste un "Gate G3" nella catena di
P4.9 — l'anello 3 è la baseline con `r_A ≤ 10%`, l'anello 5 è il lack-of-fit. Il
criterio `p ≥ 0,05` citato è quello del **lack-of-fit permutazionale**
(P3.9 `:1101`, P4.9 `:2095`).

**Verifica sul principio.** Il principio è corretto — ed è la regola di lavoro
del repository: un `p` non significativo non è un'assenza di effetto. Il
protocollo lo applica già, in due punti e con due strumenti:

- P3.9 `:1056-1059` introduce `lof_max_rel`, "grandezza dell'effetto di
  lack-of-fit… **descrittivo, non ha soglia e non è un criterio**: serve perché
  un test poco potente può 'passare' con uno scarto grande, e il lettore deve
  poterlo vedere";
- P3.9 `:1067-1078` spiega che con pesi conservativi — `w_b = 1/budget_fit_b²`
  non è l'inverso della varianza — "la statistica non segue la F con `(6, 23)`
  gradi di libertà… L'effetto è asimmetrico e va nella direzione sbagliata: un
  `p` troppo grande premia la bassa potenza, e `p ≥ 0,05` è il criterio di
  **accettazione** dell'anello 5". La cura adottata è cambiare il **riferimento**
  del `p` (distribuzione nulla per ricampionamento del puro errore), non
  aggiungere una soglia accanto.

**Perché la soglia proposta non è adottata.** `|ρ_Spearman| ≤ 0,35` è un numero
nuovo senza ancora: non c'è una fonte, non c'è un calcolo, non c'è una
giustificazione del valore 0,35 contro 0,30 o 0,40. P4.8 `:2075` chiude una
discussione analoga con una frase esplicita — "Nessun'altra soglia si aggiunge" —
e AGENTS.md richiede che le soglie siano congelate **prima** dei dati con la loro
ragione. Siamo prima dei dati, quindi la soglia sarebbe formalmente ammissibile,
ma andrebbe motivata come ogni altra: non è il compito di una raccomandazione non
ancorata. Resta registrata come possibilità, con il suo difetto: aggiunge un
criterio di accettazione a una catena monolitica di sei anelli, dove ogni anello
in più rende `validated` più difficile da raggiungere senza rendere più affidabile
il numero.

**Esito: respinto nell'evidenza, principio già in vigore, soglia non adottata.**

---

## 5. Ciò che del documento si adotta

**5.1 L'idea di una suite di test senza hardware (§7), in forma corretta.** È il
contributo reale del documento: la geometria di copertura è decidibile a tavolino,
dai soli punti di disegno, quindi può essere congelata in test prima della
campagna. La revisione propone `test_protocollo_p4_geometry.py`; il file è stato
scritto con quel nome, ma **non** con quel contenuto, perché i suoi due test
usano l'inviluppo sbagliato (`HULL_VERTICES` a cinque vertici) e la costante
`z_975 = 1.96` discussa in §2. Il file realizzato ha 17 test in tre famiglie —
vertici, metrica e margini, scala di `budget_pred` — e fissa anche il fatto che
`(32,4)` non è un punto di disegno, così la correzione D1 non può rientrare in
silenzio. Esito:

```
pytest cwEnergyModular/tests/test_protocollo_p4_geometry.py -q
17 passed in 0.07s

pytest cwEnergyModular -q
382 passed, 3 skipped in 8.95s
```

La suite passa da 368 raccolti (365 + 3) a **385 raccolti (382 + 3)**. Le
Appendici D della tesi e il conteggio in AGENTS.md vanno rigenerati con
`cwEnergyModular/tools/dump_tests_latex.py`: non è stato fatto qui, perché
AGENTS.md e le appendici si allineano al freeze P5 insieme alle altre 848 righe
non committate.

**5.2 La formulazione GUM dell'ipotesi di ortogonalità (§2.3).** La revisione
scrive che la quadratura "non assume la normalità delle sorgenti di errore, ma
risponde all'ipotesi di ortogonalità/indipendenza delle componenti (Guida GUM /
ISO/IEC Guide 98-3)", e che i semi-range rettangolari non vanno divisi né per
`√3` né per `m`. La seconda metà è già congelata (P3.8: `u_within,b` "non diviso
per radice di m"). La prima metà è la formulazione che manca alla decisione
**ancora aperta** di P1.7 — la forma di combinazione di `budget_base_w`,
quadratura o somma aritmetica, rinviata ai dati del pilota P2.9 — e al punto
accettato-non-fatto registrato come task #43: dichiarare l'ipotesi che giustifica
`w_b = 1/budget_fit_b²`. Dire "ortogonalità, non normalità" non chiude la
scelta, perché la quadratura resta provvisoria finché non si decide **cosa**
rappresenti il budget — incertezze standard combinabili sotto un'ipotesi
probabilistica, oppure limiti assoluti senza compensazione (AGENTS.md, "La
quadratura non è un limite conservativo garantito") — ma è la formulazione giusta
da portare al pilota. Registrata, non adottata: nessuna formula cambia.

**5.3 LOPO come sensibilità, non come gate (§3.1).** Il protocollo non ha una
cross-validazione: ha due punti di conferma fuori dal fit, `(12,32)` e `(256,192)`
(P3.5 `:959-960`, P3.10, anello 6). L'idea di una leave-one-point-out a 10 pieghe
per valutare la capacità di interpolazione della superficie è ragionevole come
**analisi post-hoc di P6** (sezione derivata, aperta), dove non tocca nessuna
decisione congelata. Non è adottata come gate e non sostituisce l'anello 6: P4.9
`:2112-2114` scrive che "nessun test di sottrazione può rimpiazzare la conferma
su geometrie mai entrate nel fit".

La lista di punti holdout della revisione va invece respinta nel contenuto, perché
due su tre contraddicono il disegno:

| proposto | stato reale |
|---|---|
| `O1 = (12,32)` | è la conferma operativa di P3.5, fuori dal fit: **corretto** |
| `O2 = (128,128)` | è il **centro del disegno**, dentro il fit con 6 blocchi (P3.5 `:957`): non può essere holdout |
| `O3 = (256,64)` | **non è un punto di disegno**; la conferma alta è `(256,192)` (P3.5 `:960`) |

Anche qui vale la stessa dinamica di D1: l'elenco è scritto senza leggere la
tabella del disegno.

---

## 6. Ciò che del documento non si adotta: lo schema dati (§5)

La revisione propone cinque campi — `coverage_tier`, `nearest_point_id`,
`dist_box_ratios`, `budget_pred_j`, `validation_status` — con valori e formule
propri. Tre conflitti con il testo congelato:

1. **`nearest_point_id` e `dist_box_ratios` usano coordinate normalizzate**
   (`/512`, `/256`, `/504`, `/252`). Le coordinate normalizzate sono state
   **valutate e non adottate** dalla quinta emenda, con la ragione scritta
   (P4.7 `:1948-1957`): cambierebbero il valore di tutti i margini pubblicati e
   il significato della soglia di 2 token di `thin_support`, che sta nel testo
   congelato. Reintrodotte di passata in un elenco di campi, senza dichiarare la
   decisione.
2. **`validation_status` con valori `failed_G1 … failed_G4`** è una seconda
   tassonomia accanto a `chain_status` (P4.3 `:1398`, P4.9 `:2107-2109`), che ha
   le sue etichette congelate: `counter_invalid`, `baseline_unstable`,
   `bias_declared`, `model_inadequate`, `validation_failed`, più
   `pred_nonpositive` e `reduced_design`. Il repository ha già un caso di doppia
   tassonomia da riconciliare (regola 9 della specifica contro regola 12.1 del
   codice) e non ne aggiunge una seconda per lo stesso oggetto.
3. **I valori di `coverage_tier`** proposti (`A_full`, `B_partial`,
   `C_out_of_bounds`) non sono quelli congelati: le fasce sono `A / B / C`
   (P4.3 `:1395`) con i flag separati `sparse_support` (B) e `out_of_coverage`
   (C), più `coverage_tier_design` e `coverage_tier_fit` che la revisione non
   contempla — e sono i due campi che la prima emenda sostanziale di P4.7 ha
   introdotto per chiudere il difetto target/reali.

Manca inoltre, nell'elenco proposto, ciò che P4.12 rende obbligatorio:
`hull_margin_tok` e `hull_margin_design_tok`, `thin_support`, `h_leverage`,
`boot_leva_rel_diff`, `boot_leva_adopted`, `u_bias_j`, `dt_tick_s`, `p_peak_w`.

---

## 7. Regola di metodo che questo turno conferma

È il quinto turno e il quarto con lo stesso esito: le osservazioni descrivono
difetti già chiusi o non riprodotti, e il lavoro utile emerge **verificandole**,
non leggendole. Qui la verifica ha un costo bassissimo — un `grep` e un calcolo
di geometria piana — e ha prodotto un guadagno reale: la geometria di copertura e
la scala di `budget_pred` ora sono congelate anche in 17 test eseguibili senza
hardware, quindi una proposta futura dello stesso tipo trova un'esecuzione invece
di un parere. Il terzo turno lo scriveva come regola ("verificare ancoraggi e
provenienza batte leggere le proposte", protocollo `:73`); questo turno ne è la
quarta conferma, e aggiunge una variante: **quando la revisione cita una sezione,
controllare che la sezione esista e dica quello**. Tre dei quattro punti citano
"P4.2", "P4.3-P4.4" e "P4.5" per contenuti che stanno altrove o da nessuna parte.

Nessun file di produzione è stato modificato. Nessun valore congelato è stato
spostato. Nessuna soglia è stata aggiunta.

---

## 8. Ancoraggi

**Protocollo** (`experiment_results/protocollo_v4_20261024.md`, 3455 righe):
disegno P3.5 `:954-963`; modello P3.3 `:877-890`, P3.4 `:891` e `:928-929`;
diagnostica e `lof_max_rel` P3.9 `:1044-1078`; `pred_nonpositive` P3.10
`:1154-1168`; definizioni P4.3 `:1379-1404`; formula di `budget_pred` P4.6
`:1624`, scala dichiarata `:1641-1647`; inviluppo e fasce P4.7 `:1814-1967`,
vertici `:1827`, `(32,32)` non vertice `:1830-1833`, `thin_support`
`:1851-1855`, due inviluppi `:1882-1908`, margini `:1916` e `:1945`, metrica
`:1883-1888`, coordinate normalizzate non adottate `:1948-1957`, "nessun'altra
soglia si aggiunge" `:2075`; bootstrap P4.8 `:1969-2082`, sintetici `:1983`,
non-gaussianità `:1987-1989`; catena a sei anelli P4.9 `:2084-2114`; campi
obbligatori P4.12 `:2166-2180`; ancore P4.14 `:2224-2227`; formulario F.11
`:2934`, F.13 `:3108`, F.14 `:3185-3186`.

**Eseguito in questo turno**: `inviluppo_e_budget_pred_probe.py` (5/5 verifiche,
exit 0), output `experiment_results/inviluppo_budget_pred_console_20261026.txt`;
`cwEnergyModular/tests/test_protocollo_p4_geometry.py` (17 test);
`pytest cwEnergyModular` → 382 passati, 3 saltati, 8,95 s.

**Materiale valutato**: `revisione tecnica di P4.docx` (radice, non tracciato,
22 958 byte, 2026-10-26 20:55).
