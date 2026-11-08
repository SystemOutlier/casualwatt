# Revisione del metodo di misurazione dell'accuratezza: CasualWatt e MUDILAB

Audit interno, 08-11-2026, ramo `emenda-8`. Perimetro: il valutatore generale
(`evaluator.py`, `robust_evaluator.py`, `evaluation_runner.py`) e il ramo
MUDILAB (`mudilab_adapter.py`, `MUDILAB_run/benchmark/valuta.py`,
`MUDILAB_run/benchmark/genera.py`). L'audit è stato in sola lettura: nessuna
modifica al codice durante la ricognizione, nessun commit, nessuna esecuzione
di pytest. La correzione del punto 3.6 è stata applicata dopo, l'08-11-2026.

I numeri MUDILAB sono stati ricalcolati il 08-11-2026 sul file
`MUDILAB_run/harness/risultati/confronto_valutatori_post_fix_20261103.json`
con il codice del repository (`cluster_bootstrap_interval`, 2000 ricampioni,
seed 20261104) e la stessa formula di Wilson di
`cwEnergyModular/evaluation_runner.py:528-538`. La verifica ha corretto un
valore della prima stesura: la copertura 0,575 era attribuita ai 321 run,
mentre appartiene al solo held-out; sui 321 run la copertura è 0,6137.

## 1. Due definizioni di "accuratezza" che convivono

Nel repository "accuratezza" nomina due oggetti diversi, e la tesi li usa
entrambi.

Il **valutatore generale** (`evaluator.py`) produce `is_correct` come variabile
binaria primaria, determinata prima di `acc_comp` in ogni ramo (`:400/406`,
`:507/508`, `:535/537`, `:580-597/610`, `:665/667`), e `acc_comp` come indice
descrittivo a pesi eterogenei (`RUOLO_COMPOSITO`/`RUOLO_BINARIA`, `:230-237`).
Il **valutatore robusto** (`robust_evaluator.py`) e l'adattatore MUDILAB
(`mudilab_adapter.py`) producono invece un verdetto a tre stati — `correct`,
`incorrect`, `indeterminate` — con confidenza e metodo, e per MUDILAB
aggiungono un contratto end-to-end in cinque stati sul percorso del tool. Sono
oggetti con proprietà statistiche diverse: il primo è una soglia su un
punteggio, il secondo una congiunzione di condizioni verificabili. Chiamarli
entrambi "accuratezza" è ammissibile solo se il documento dice quale sta
pubblicando. Oggi non lo dice sempre.

La distinzione non è formale. Nel ramo `free_text` del valutatore generale
`is_correct` è una soglia sul coseno (`:608`, default 0,75) o, nel percorso di
default del benchmark, una soglia sulla similarità lessicale (`:600`). Nel
valutatore robusto `short_text` è contenimento normalizzato, `number` è un
confronto entro tolleranza, e il resto è `indeterminate` invece di zero. Le due
grandezze non sono sulla stessa scala e non misurano lo stesso costrutto.

## 2. Cosa è solido

Quattro scelte reggerebbero la revisione di un revisore esterno, e vanno tenute.

**L'indeterminato non è zero.** `summarize_records` calcola l'accuratezza sui
soli determinati (`evaluation_runner.py:572`) e pubblica `coverage` accanto
(`:573`), con i conteggi per verdetto (`:567-574`). È la pratica che HELM ha
reso esplicita: un numero di accuratezza senza copertura non è interpretabile.
Il codice la esporta come campo, non come nota a piè di pagina.

**Due intervalli, dichiarati come diversi.** Wilson a livello di riga e
bootstrap a cluster a livello di task convivono (`:541-566`), e il secondo resta
`None` con la ragione scritta quando l'identità del task manca o quando c'è un
solo cluster (`:545-558`; `docs/ROBUST_EVALUATOR.md:20-31`). Rifiutare un
intervallo non calcolabile invece di stamparne uno lusinghiero è la scelta
giusta. La differenza fra i due non è teorica: sul pilota held-out l'intervallo
a cluster è 1,74 volte più largo di quello di riga, e l'ICC misurato è 0,981
(sezione 4.2). La stessa disciplina è nel valutatore robusto
(`robust_evaluator.py:458-523`).

**Il conto dell'energia è dichiarato alla lettera.** `energy_numerator` e
`energy_denominator` sono stringhe nel payload (`evaluation_runner.py:593-594`),
`partial` non viene presentato come totale (`:595-602`), le energie negative si
conservano nelle mediane diagnostiche e si escludono — non si clampano — dal
consumo (`:595-598`). È coerente con la regola del repository e con la
distinzione fra energia misurata e attribuita.

**Il percorso del tool è un contratto, non un'euristica.** `mudilab_adapter.py`
distingue `tool_called`, `tool_arguments_status`, `tool_call_status`,
`tool_output_status`, `tool_adoption_status`
(`docs/ROBUST_EVALUATOR.md:316-324`), e l'adozione richiede una ricevuta di
inoltro (`mudilab_adapter.py:479-504`). Il digest SHA-256 è dichiarato per ciò
che prova — integrità interna, non autenticità del produttore — e questa
distinzione molti benchmark di tool use non la fanno.

## 3. Difetti del valutatore generale

### 3.1 Il giudice misura la coerenza, ma il verdetto si chiama correttezza (P0)

In regime B `is_correct` è `1` se il punteggio del giudice è ≥ 4
(`evaluator.py:676`). La rubrica del giudice, però, chiede di valutare la
"logical and causal coherence" della risposta rispetto alla domanda, con ancore
da "fully coherent, correct causal structure" a "incoherent"
(`llm_judge.py:56-71`). Coerenza causale e correttezza fattuale non sono la
stessa proprietà: una risposta può essere internamente coerente e falsa. Il
modello di default è `llama3.2:1b` (`llm_judge.py:73-74`), quindi il verdetto
di un modello da 1B su un compito di coerenza diventa l'accuratezza primaria di
un altro modello.

È il difetto di validità di costrutto più grave del ramo generale, e la
letteratura lo sostiene: Zheng et al. (2023) documentano i bias sistematici dei
giudici LLM (posizione, verbosità, auto-preferenza), e Panickssery et al.
(2024) mostrano che i modelli riconoscono e favoriscono le proprie generazioni.
Qui il rischio non è teorico: il giudice di default è della stessa famiglia di
uno dei modelli valutati. Nel dataset a nove righe il giudice non è stato
invocato (`eval_method = none`, documentato in cap. 5), quindi il numero
pubblicato non è affetto; il percorso di produzione però sì, e la tesi lo
descrive come disponibile.

O si rinomina la grandezza (tasso di superamento della soglia di coerenza), o si
aggiunge una rubrica fattuale distinta e si valida il giudice contro etichette
umane con un accordo misurato — Cohen's kappa (1960) è lo strumento minimo —
prima di chiamarla accuratezza.

### 3.2 Il fallback lessicale contraddice la nota che lo accompagna (P0)

Con `use_semantic=True` e embeddings non disponibili, il codice mette
`is_correct = NA` e scrive: "NON usare similarità lessicale come accuratezza"
(`evaluator.py:591-596`). Con `use_semantic=False` — il default durante il
benchmark, per non caricare il modello — mette
`is_correct = 1 if lexical_similarity >= 0.85 else 0` (`:598-605`). La nota e
il comportamento si contraddicono nello stesso blocco, a dieci righe di
distanza.

La scelta coerente con la nota è che il fallback lessicale produca `NA` e resti
diagnostico, come già fa il percorso con embeddings assenti. Se lo si vuole come
verdetto, allora la nota va riscritta e va dichiarato che l'accuratezza
`free_text` di default è una soglia di somiglianza lessicale: un'altra metrica,
con un'altra validità.

### 3.3 La soglia 0,75 sul coseno è già stata falsificata dalla tesi (P0/P1)

Il capitolo 5 documenta il risultato negativo meglio di quanto faccia il
codice: su nove righe `is_correct` coincide con "coseno ≥ 0,75" in 9/9; il
verdetto approva 3 risposte su 7 realmente corrette (precisione 1,00, richiamo
0,43, accordo 6/9); la distanza fra una risposta giusta e una sbagliata nello
stesso item è 0,0235, mentre lo spostamento dello stesso modello fra due item è
0,4279 — l'item pesa circa 18 volte la correttezza. `llama3.2` scrive
"25 − 4 = 21 ... la risposta è: 21" e prende 0,3544 e `False`; `tinyllama`
scrive "5*5−4 = 10*10 = 100 ... = 1" e prende 0,3308.

La conseguenza è netta: finché il denominatore di `J/risposta corretta` è quella
soglia, la metrica di frontiera non misura l'efficienza, misura la distanza
dell'item dalla ground truth. La tesi lo dice già; il valutatore generale
continua a offrire quella soglia come default. La raccomandazione è di non
pubblicare accuratezza `free_text` con quel default: usare i rami deterministici
(`number`, `short_text`) per i risultati principali e trattare `free_text` come
descrittivo finché non esiste una validazione.

### 3.4 Tre tolleranze per la stessa parola (P1)

Lo stesso confronto numerico usa tre contratti: `tol=1e-6` nel valutatore
generale (`evaluator.py:515`), la metà dell'ultimo decimale stampato con guardia
`1e-12` nell'adattatore MUDILAB (`mudilab_adapter.py:67-93`), e `TOLL = 5e-4`
assoluto nel criterio ufficiale MUDILAB
(`MUDILAB_run/benchmark/__init__.py:20-79`). Ognuno è difendibile nel proprio
perimetro, ma non sono confrontabili e il documento non lo dice.

Il caso del valutatore generale è il più fragile: `1e-6` è una tolleranza di
uguaglianza matematica, non di formato. Su numeri stampati, una risposta
corretta arrotondata a due decimali viene rifiutata. La tolleranza derivata
dell'adattatore esiste proprio per questo, ed è la scelta migliore delle tre; il
ramo generale dovrebbe adottarla o dichiarare che `1e-6` presuppone decimali
esatti.

### 3.5 `short_text` non vede la negazione (P1)

Il ramo `short_text` normalizza e verifica il contenimento
(`evaluator.py:543-565`, `check_short_text_containment`). "Non è 21" contiene
"21" e passa. Il valutatore robusto ha `_locally_negated`
(`robust_evaluator.py:185-197`), ma lo applica solo a `free_text`; i rami
`short_text` — entrambi — non lo usano. È un buco ristretto ma reale, e riguarda
una classe di risposte frequenti nei question-answering brevi.

### 3.6 La McNemar è implementata, documentata come assente, e con l'intervallo sbagliato (P0; intervallo e `correction_applied` corretti l'08-11-2026)

È il difetto più concreto, perché è verificabile in tre punti del repository che
si contraddicono fra loro.

Il test c'è: `paired_mcnemar` in `evaluation_runner.py:177-331`, con exact
binomial e chi-quadro corretto quando le coppie discordanti sono ≥ 10
(`:246-260`). La documentazione diceva il contrario: "richiede una McNemar
appaiata: **non è implementata**" (`docs/ROBUST_EVALUATOR.md:29`). E il codice
stesso stampava quella frase nella nota di ogni riepilogo: "McNemar non
implementato" (`evaluation_runner.py:453` al commit `b11c8fc38`, prima della
rimozione dell'08-11-2026). La tesi la
ripeteva in tre capitoli (cap. 4, cap. 5, cap. 6). Quindi: funzionalità presente,
documentazione e output runtime falsi, tesi stantia.

**Documentazione allineata l'08-11-2026, cinque punti** (nessuna riga del
percorso di misura): la nota del riepilogo rinvia a `paired_mcnemar`
(`evaluation_runner.py:545-558`); `docs/ROBUST_EVALUATOR.md:28-54` descrive la
funzione al posto della dichiarazione di assenza; i capitoli 4, 5 e 6 della tesi
la citano come implementata con gli stessi ancoraggi; la spec di fase 3
(`fase3_mcnemar_spec_20261107.md`, §1 e §9) passa al passato la lacuna, elenca i
campi reali e corregge il refuso `pairedd_mcnemar`; `AGENTS.md` (regola
sull'unità statistica) e `docs/RELAZIONE_VALUTATORE_ROBUSTO.md` (terzo limite)
puntano alla funzione. Alla data di quella nota restava l'assenza di un percorso
di report che la chiamasse: vedi in fondo alla sezione.

Peggio, l'intervallo non era appaiato. Le righe `:247-265` del codice di allora
calcolavano i due intervalli Wilson marginali (`lo_a`, `hi_a`, `lo_b`, `hi_b`,
`:259-262`) e poi non li usavano; combinavano i due errori standard in
quadratura (`se_paired = sqrt(se_a² + se_b²)`, `:264`) e producevano
`delta_ci` (`:265`).
Questa è la formula non appaiata: ignora la covarianza fra le due proporzioni
sullo stesso campione. La specifica scritta nel repository la vieta
esplicitamente (`experiment_results/fase3_mcnemar_spec_20261107.md`, §3, righe
45-48) e chiede l'intervallo di Newcombe (§8). L'effetto è un intervallo troppo
largo quando la correlazione è positiva — conservativo, ma incoerente con il
test, che l'appaiamento lo usa attraverso `b` e `c`. Un intervallo che non
esclude lo zero mentre il test esatto è significativo (o viceversa) è un
risultato che si contraddice.

**Verifica numerica (08-11-2026, codice precedente alla correzione).**
L'implementazione di riferimento del metodo
10 è stata validata sull'esempio riportato nella documentazione di statsmodels
per `confint_proportions_paired` (tabella `[[10, 5], [2, 20]]`): il calcolo
indipendente dà (-0,0643926050712, 0,2211160178958) contro
(-0,0643926050711, 0,2211160178958) atteso, con phi corretto 0,545063. Sul
codice *precedente* alla correzione (colonna «CI precedente»), con
`paired_mcnemar` importato dal modulo:

| Caso (a, b, c, d) | p esatto | CI precedente | CI Newcombe | phi |
|---|---:|---|---|---:|
| (60, 10, 2, 28) | 0,038574 | −0,053624 – 0,213624 | 0,011009 – 0,148316 | 0,724 |
| (55, 15, 7, 23) | 0,133801 | −0,053624 – 0,213624 | −0,012714 – 0,170744 | 0,499 |
| (10, 10, 10, 10) | 1,0 | −0,229412 – 0,229412 | −0,209310 – 0,209310 | 0 |
| (2, 1, 1, 1) | 1,0 | −0,814811 – 0,814811 | −0,464868 – 0,464868 | 0 |
| (0, 12, 12, 0) | 1,0 | −0,304697 – 0,304697 | −0,371451 – 0,371451 | −1 |

Le prime due righe hanno gli stessi marginali (`a+b = 70`, `a+c = 62`, `n =
100`) e ricevono lo stesso intervallo: quello del repository è funzione dei soli
marginali e non può essere appaiato. Sulla prima riga il test esatto è
significativo (0,0386) mentre il suo intervallo contiene lo zero; Newcombe lo
esclude. L'ampiezza è 1,95 volte quella di Newcombe con phi = 0,724, 1,46 con
phi = 0,499, 1,10 con phi = 0 e 0,82 con phi = −1: troppo larga per
correlazione positiva, leggermente larga anche a correlazione nulla, troppo
stretta per correlazione fortemente negativa. A correlazione nulla il residuo
viene dal termine `z²/(4n²)`, che entra due volte: 0,267248 contro 0,261668
della Wald non appaiata, quindi non è nemmeno quella. `correction=False` su
`b = c = 12` dava chi² 0,0 contro 0,041667 con correzione, ma
`correction_applied` (`:283` allora) restava "yes" in entrambi i casi: il
campo era una costante, e `test_no_chance_correction` non lo intercettava
perché asseriva solo che chi² non fosse `None`. Corretto anch'esso l'08-11-2026,
come il secondo punto della nota che segue.

Nessuno degli otto test preesistenti in `tests/test_paired_mcnemar.py`
asseriva `delta_ci_newcombe`: il campo poteva essere sbagliato senza che la
suite se ne accorgesse. Nessun percorso di report chiamava `paired_mcnemar` — il
`grep` trovava solo i test — quindi il difetto non aveva ancora toccato un numero
pubblicato, ma andava corretto prima che lo facesse. La correzione richiedeva
tre cose insieme — formula di Newcombe con il phi corretto del 2×2 (covarianza
positiva ridotta di `n/2`, o intervallo condizionale esatto), un test che fissi
il campo, e la rimozione delle cinque affermazioni stantie — e non andava fatta
a metà.

**Corretto l'08-11-2026.** `paired_mcnemar` ora calcola l'intervallo di
Newcombe (metodo 10) con il phi corretto (`evaluation_runner.py:262-311`); due
test in `tests/test_paired_mcnemar.py` fissano l'esempio di riferimento e la
dipendenza da phi. La suite eseguita quel giorno dà 1046 test passati e 4
saltati, 0 falliti, in 20,08 s.

**Secondo punto, stesso giorno.** `correction_applied` non è più una costante
(`evaluation_runner.py:246-260`, restituito a `:327`): vale `"yes"` quando il
chi² usa la correzione di continuità, `"no"` quando `correction=False` la
disattiva, e `"not_applicable"` quando `b+c < 10` — lì il test è il binomiale
esatto e non esiste un chi² da correggere, quindi `"no"` direbbe che la
correzione è stata spenta. `chi2_correction` (`:323`) resta il flag *chiesto*
dal chiamante, e la docstring distingue i due campi. Un test nuovo
(`test_correction_applied_distinguishes_the_three_states`) fissa i tre stati e
il file passa a 11 test; la suite sale a 1047 passati e 4 saltati, 0 falliti,
in 21,64 s. Nello stesso giorno, con due passaggi successivi, sono cadute anche
le cinque affermazioni di non implementazione (vedi sopra, "Documentazione
allineata") e l'assenza di un percorso di report che chiami la funzione (vedi
§7): alla fine della giornata il difetto è chiuso su codice, test, documentazione
e report.

**Percorso di report, stessa sera.** `paired_summary` (stesso modulo, subito
dopo `paired_mcnemar`) riduce le due serie a **una coppia per task** con la
regola `first`, che tiene la prima riga incontrata nell'ordine del file e non
dipende dall'esito; restituisce `n_tasks`, `n_tasks_with_replicas` e
`n_without_task`, così che le righe scartate dalla riduzione non restino
implicite. Due test nuovi (`test_paired_summary_reduces_to_one_pair_per_task`,
`test_paired_summary_rejects_undeclared_reduction`) portano il file a 13 test.
`tools/mcnemar_report.py` è il consumatore: `--input` obbligatorio, `--source`
per registrare la provenienza quando le righe vengono estratte da un blob git,
uscita JSON più `.txt` con matrice, p esatto, chi², delta, intervallo di Newcombe,
esclusi per ragione, verdetto **INDECISO** quando `b+c=0` e cautela sopra il 10%
di coppie escluse. Prima esecuzione sul confronto MUDILAB del 03-11-2026 —
`confronto_valutatori_20261103.json` al commit `303051dd9`, 321 run, ridotti a
161 task (80 con repliche): matrice `a=50 b=7 c=0 d=104`, nessuna coppia
esclusa, p esatto 0,015625, `delta_acc = 0,043478`, intervallo di Newcombe
`[0,009472; 0,078023]`. Il ramo `passi` perde sette task e nessuno ne vince;
l'intervallo esclude lo zero e concorda con il test. La copia dell'albero di
lavoro, rigenerata il 07-11-2026, non era una misura di quel giorno ma una
ri-valutazione delle righe del 03-11 con i campi nuovi del valutatore
(`tolerance_provenance` dal `98ec5972` del 04-11; adozione, argomenti e output
del tool dal `6fc13d013` del 05-11). L'08-11-2026 il file tracciato è stato
ripristinato al blob di `303051dd9` (hash verificato: `44f6f98d…` per il JSON,
`250fefa5…` per il `.txt`), conservandone una copia fuori dal repository, e la
ri-valutazione è stata rifatta come artefatto separato con provenienza
dichiarata e la sua nota
(`experiment_results/rivalutazione_confronto_mudilab_20261108.md`): `passi` dà
0/321 con 88 determinati (27,41%) e 233 indeterminati, e il confronto appaiato
su quello è indeciso (48 coppie determinate tutte concordanti, 113 escluse,
70,2%). Il report di questa sezione continua a leggere l'artefatto del 03-11,
l'unico dei due in cui i due criteri producono coppie discordanti. Con i due test della
riduzione la suite passa a 1049 passati e 4 saltati, 0 falliti, in 21,22 s.

### 3.7 Il bootstrap a cluster: non è un dettaglio, è un fattore 1,74 (P1)

La scelta di pubblicare `n_effective_tasks` e di restituire `None` con un solo
cluster è corretta. Sul pilota MUDILAB l'effetto del clustering è però
misurabile e grande: 240 righe valgono 81 osservazioni indipendenti (ICC 0,981,
design effect 2,96), e l'intervallo a cluster è 1,74 volte quello di riga. Non è
un caso limite: è la situazione normale quando tre repliche a temperatura zero
ripetono lo stesso task.

Resta il fatto che il bootstrap percentile, fra 2 e circa 30 cluster, sottostima
la copertura: Cameron, Gelbach e Miller (2008) mostrano che l'inferenza con
pochi cluster è sistematicamente troppo ottimista e propongono correzioni (wild
cluster bootstrap, distribuzione t con G−1 gradi di libertà). Con 80 task il
problema è trascurabile; con i nove record del dataset generale il cluster non è
calcolabile e l'intervallo resta `None`, il che è onesto ma significa che quel
dataset non porta incertezza a livello di task. Va scritto, non corretto con un
numero.

### 3.8 `J/risposta corretta` sotto copertura parziale (P2)

La definizione è dichiarata: numeratore = somma dell'energia disponibile su
tutte le righe eleggibili, comprese le fallite; denominatore = tutte le
corrette, comprese quelle senza energia (`evaluation_runner.py:593-594`). Presa
alla lettera, sotto copertura parziale la direzione del bias non è unica: le
righe indeterminate aggiungono energia al numeratore ma non possono mai entrare
nel denominatore (spingono il rapporto in alto), mentre le righe corrette senza
energia entrano nel denominatore senza contribuire al numeratore (lo spingono in
basso). Il payload dice `partial`, non dice il segno. La raccomandazione è
pubblicare due rapporti — energia sulle sole righe determinate e energia su
tutte le righe eleggibili — oppure dichiarare esplicitamente che sotto copertura
parziale il rapporto è un limite inferiore o superiore. Oggi non è né l'uno né
l'altro.

### 3.9 Il residuo di `acc_comp` (P2)

La declassazione a indice descrittivo è fatta bene: il ruolo sta in `notes`, non
in una colonna nuova, e lo schema P5 resta a 174 nomi. Il residuo è che
`ece_per_joule` continua a usare quel numeratore eterogeneo
(`benchmark_unified.py:690`), quindi una metrica derivata mescola ancora una
scala 0-1 con una media 0-5. La tesi lo dichiara; la conseguenza pratica è che
`ece_per_joule` va pubblicata come descrittiva, non come efficienza.

## 4. Il ramo MUDILAB

### 4.1 Cosa misura il criterio ufficiale

Il criterio è `corretta = etichetta_ok and numero_ok`
(`MUDILAB_run/benchmark/valuta.py:18-21`, `:268`), con confronto numerico a
`TOLL = 5e-4` sui valori stampati (`genera.py:528-551`). È deterministico,
riproducibile e non dipende da un giudice: per un benchmark di tool use è la
scelta giusta. Ha però due limiti strutturali.

Il primo è che la congiunzione non distingue due fallimenti diversi: un'etichetta
non riconosciuta e un numero sbagliato valgono entrambi "incorrect". Il percorso
end-to-end li separa. Sul confronto del 03/11, 321 run danno 109 corrette
(33,956%; il riepilogo JSON arrotonda a 0,3396) e 915,749 J/corretta. Il
percorso stretto `passi`/`dizionario` dà lo stesso 109/321, con copertura 0,6137
(197 determinati su 321): 124 righe fermate dal gate diventano `indeterminate` e
88 mismatch di traduzione restano `incorrect`
(`MUDILAB_run/harness/risultati/confronto_valutatori_post_fix_20261103.txt:40`,
`:14`, `:30`). Sul solo held-out la copertura scende a 0,575 (138/240), con 102
indeterminate e 61 incorrect, e il costo sale a 964,929 J/corretta (`:42`). Lo
stesso numero, due significati: nel primo caso "il modello ha sbagliato", nel
secondo "in 124 casi sui 321 non sappiamo se il modello ha sbagliato o se ha
ceduto la pipeline". Per un benchmark che vuole attribuire l'errore al modello,
la seconda lettura è obbligatoria.

Il secondo limite è che `5e-4` è assoluto sul valore stampato. Per una
probabilità va bene; per un numero con due decimali è più stretto della
precisione dichiarata: 0,21 è l'arrotondamento corretto di 0,212 a due decimali,
ma la distanza 0,002 supera `5e-4` e la risposta viene dichiarata errata.
L'adattatore MUDILAB ha già la tolleranza derivata che risolverebbe il caso
(`mudilab_adapter.py:67-93`); il criterio ufficiale non la usa. Se la scelta
assoluta è voluta, va dichiarata con la sua conseguenza — penalizza il formato
grosso — non presentata come confronto di valori stampati.

### 4.2 L'unità statistica: 240 righe sono 80 task, e il conto è esplicito

Il pilota held-out ha 240 righe, ma sono 80 task × 3 repliche a temperatura zero.
Le tre repliche non sono tentativi indipendenti: 25 task sono corretti in tutte e
tre, 54 in nessuna, 1 in due su tre; nessun task ha una sola corretta. Il
ricalcolo con il codice del repository (`cluster_bootstrap_interval`, 2000
ricampioni, seed 20261104; Wilson con `z = 1.959963984540054`, come
`evaluation_runner.py:528-538`) sul file
`confronto_valutatori_post_fix_20261103.json`, filtrato a
`split == "held-out"`, dà:

| Stima | Valore | Intervallo 95% | Larghezza |
|---|---:|---|---:|
| Riga, n = 240 | 77/240 = 32,083% | 26,500–38,231% | 11,73 pp |
| Cluster bootstrap, 80 task | 32,083% | 22,083–42,500% | 20,42 pp |
| Task tutte corrette, 25/80 | 31,250% | 22,150–42,068% | 19,92 pp |
| Task con almeno una corretta, 26/80 | 32,500% | 23,244–43,360% | 20,12 pp |

La stima puntuale di riga e quella a livello di task coincidono quasi (32,08%
contro 31,25%), perché i cluster sono bilanciati a tre righe; ciò che cambia è
l'incertezza. L'intervallo a livello di task è **1,74 volte** più largo di
quello di riga, e il rapporto fra le ampiezze non è un estimatore
dell'intra-correlazione — ma l'ANOVA sui 240 record la stima direttamente:
ICC = 0,981, design effect = 2,96, quindi n efficace ≈ 81, esattamente il numero
di task. I bordi del bootstrap sono valori discreti (53/240 e 102/240), perché
ogni ricampiono ha 240 righe: l'intervallo non è centrato esattamente sulla
stima puntuale (centro 32,29%) e questo è normale con una distribuzione a due
masse.

La stima a livello di task dipende dalla definizione: "task risolto = tutte e
tre le repliche corrette" dà 25/80 = 31,25%, "almeno una corretta" dà
26/80 = 32,50%. Qui la differenza è di un solo task, ma è la definizione da
dichiarare, non da lasciare implicita. Questa è la correzione statistica
principale del ramo MUDILAB, ed è ottenibile senza nuovi dati: pubblicare
l'intervallo a livello di task come primario, con `n_effective_tasks = 80`, e il
Wilson di riga come secondario. `valuta.py` oggi aggrega senza intervallo
(`_aggregato`, `:301-325`): il numero 33,96% esce nudo.

Per completezza, lo stesso ricalcolo sui 321 run del file (81 dev + 240
held-out, 109 corrette) dà 33,956% con Wilson di riga 28,993–39,299% e cluster
su 161 task 26,101–42,250%, rapporto 1,57. È un intervallo valido ma su un
disegno misto: i task dev hanno una sola replica, quelli held-out tre, quindi il
bootstrap pesa le righe held-out tre volte tanto. L'unità pulita per l'inferenza
resta la tabella sopra, sui 240.

### 4.3 Il confronto con un altro sistema non è decidibile su questi dati

Con un solo task discordante — l'unico che alterna, 2/3 — una McNemar appaiata
dà p esatto = 1,0: nessun confronto può raggiungere la significatività,
qualunque sia la differenza osservata. La conclusione operativa è che il claim
"SLM contro proprietari" non si può chiudere con 80 task e un solo discordante;
serve o un numero di task maggiore, o un disegno appaiato con una potenza
calcolata prima. È la regola di casa — un intervallo che contiene lo zero non è
un'assenza di effetto, ma un test che non può rifiutare non è un'evidenza di
equivalenza.

### 4.4 Oracoli e coerenza

La dichiarazione di indipendenza è corretta e va mantenuta: `cond_prob` e `inter`
hanno oracoli indipendenti, il controfattuale no, perché misura il routing
(`MUDILAB_run/benchmark/__init__.py:20-79`). La coerenza usa un marcatore
letterale ("NOT strongly compatible") con soglia 0,60 (`genera.py:547-550`): è
deterministico, ma è un auto-report del tool, quindi misura il formato e il
routing, non la verità. Va bene come criterio di instradamento; non va chiamato
correttezza.

### 4.5 La decisione aperta sul mismatch

Un `tool_arguments_status = mismatch` oggi cambia la nota, non il verdetto
(`mudilab_adapter.py:460`, `:476-482`). Per un benchmark che misura l'uso del
tool, una riga "corretta" con argomenti diversi da quelli inviati è un buco di
validità: il numero può venire da un'altra chiamata. La decisione è dichiarata
aperta nel codice, il che è meglio di una scelta silenziosa, ma va chiusa prima
della prossima campagna. La proposta coerente con la semantica degli stati è
`mismatch → indeterminate`, non `incorrect`: è un fallimento di pipeline, non
del modello.

## 5. Valutazione dei riferimenti scientifici

La struttura intellettuale del metodo è già quella giusta: la documentazione
cita SQuAD per la normalizzazione, HELM per la copertura, Lanham per la
distinzione fra sequenza e causalità, Newcombe per l'intervallo appaiato, Zheng
per i bias del giudice. Il problema è che la bibliografia della tesi non
contiene le voci statistiche: Wilson, McNemar, Newcombe, Efron,
Cameron-Gelbach-Miller, Cohen, SQuAD, HELM e Lanham non hanno una chiave in
`references.bib`. La tesi usa il metodo e non può citarne le fonti. È una
lacuna di conformità, non di sostanza, e si chiude con nove voci verificate.

Sul merito, tre osservazioni. Wilson (1927) è appropriato per una proporzione
binomiale, ma assume righe indipendenti: per questo il bootstrap a cluster non è
un'alternativa ma un secondo intervallo, e la documentazione lo dice
correttamente (`ROBUST_EVALUATOR.md:23-24`). McNemar (1947) richiede esiti
binari appaiati sugli stessi task; con meno di dieci discordanti il test esatto
è preferibile al chi-quadro, e il codice lo fa. Newcombe (1998b) è il
riferimento giusto per l'intervallo appaiato, ma la formula implementata non è
la sua: la somma in quadratura degli errori standard marginali è la formula non
appaiata. Efron (1979) e Cameron-Gelbach-Miller (2008) sono i due riferimenti
che mancano alla sezione sul bootstrap a cluster — che oggi dichiara
esplicitamente di non avere una fonte associata
(`RELAZIONE_VALUTATORE_ROBUSTO.md:309-311`): il primo per il metodo, il secondo
per il caso dei pochi cluster. Cohen (1960) serve se si vuole validare il
giudice contro etichette umane, che è la strada per rendere il regime B
un'accuratezza e non un tasso di coerenza.

SQuAD (2016) e HELM (2022) sono citati nei documenti interni e assenti dalla
biblio; il primo sostiene la normalizzazione del testo, il secondo la
pubblicazione della copertura. Lanham et al. (2023) è usato per la distinzione
fra relazione sequenziale e causale, che è esattamente il punto del contratto di
adozione: un numero uguale a quello del tool non prova che venga dal tool. Zheng
et al. (2023) è già in biblio e sostiene la cautela sul giudice; Panickssery et
al. (2024) è in biblio ma marcata preprint, e lo stato editoriale va riconfermato
alla fonte prima di citarla come peer-reviewed. BFCL è una risorsa di
leaderboard, non letteratura peer-reviewed: va etichettata come tale, come
chiede la regola del repository.

## 6. Priorità

**P0 — prima di pubblicare un numero di confronto.** L'intervallo McNemar e il
campo `correction_applied` sono stati corretti l'08-11-2026 (formula appaiata
con il phi, non la quadratura dei marginali; tre stati espliciti per la
correzione, con test che fissano il caso noto, la dipendenza da phi e i tre
stati). Le cinque affermazioni di non implementazione sono state rimosse lo
stesso giorno (nota del riepilogo, `ROBUST_EVALUATOR.md`, cap. 4, cap. 5,
cap. 6), e il confronto appaiato ha un percorso di report
(`tools/mcnemar_report.py`), il cui primo uso sul confronto MUDILAB del 03-11 dà
sette task persi contro zero vinti (p esatto 0,0156, intervallo `[0,0095;
0,0780]`). Restano due punti di
criterio, non di implementazione: allineare il fallback lessicale alla propria
nota (`NA`, non verdetto) e decidere
se il regime B si chiama accuratezza o tasso di coerenza, e nel secondo caso
rinominarlo ovunque.

**P1 — prima della prossima campagna.** Pubblicare l'intervallo MUDILAB a
livello di task come primario e aggiungerlo a `valuta.py`; chiudere
`mismatch → indeterminate`; armonizzare le tre tolleranze o dichiarare perché
differiscono; applicare la negazione locale anche a `short_text`; non usare la
soglia 0,75 come accuratezza `free_text` nei risultati principali.

**P2 — nella revisione della tesi.** Aggiungere le nove voci statistiche
verificate; scrivere la direzione del bias di `J/corretta` sotto copertura
parziale; dichiarare il limite del bootstrap percentile con pochi cluster;
etichettare BFCL come risorsa non peer-reviewed.

## 7. Metodo e limiti di questa revisione

La revisione è stata scritta in sola lettura: nessuna modifica al codice di
produzione durante l'audit, nessun commit, nessuna esecuzione di pytest. La
correzione della sezione 3.6 è stata applicata dopo, l'08-11-2026, con i test
indicati. I valori MUDILAB sono stati
ricalcolati il 08-11-2026 dal file
`confronto_valutatori_post_fix_20261103.json` con il codice del repository
(`cluster_bootstrap_interval`, 2000 ricampioni, seed 20261104) e la stessa
formula di Wilson di `evaluation_runner.py:528-538`; ICC e design effect sono
calcolati con l'ANOVA sui 240 record held-out. La verifica ha confermato tutti i
valori citati tranne uno della prima stesura — la copertura 0,575, che è del
solo held-out (138/240) e non dei 321 run (197/321 = 0,6137) — ed è la
correzione applicata alla sezione 4.1. Non ho rigenerato il pilota: i 240
record e i 321 run sono artefatti del 02-03/11. L'intervallo McNemar è stato
verificato numericamente l'08-11-2026: l'implementazione di riferimento del
metodo 10, confrontata con l'esempio della documentazione di statsmodels,
riproduce
(-0,0643926050711, 0,2211160178958) a 1e-13; sul codice del repository
precedente alla correzione la verifica mostrava l'invarianza ai marginali, la
contraddizione con il test esatto e il campo `correction_applied` costante
(sezione 3.6). Entrambi i difetti sono chiusi nel codice dell'08-11-2026, con i
test che li fissano; l'audit resta in sola lettura sui dati, che non ho
rigenerato. Il primo esempio sui dati di CasualWatt è il confronto MUDILAB del
03-11-2026 (sezione 3.6); non è un campione esterno. L'artefatto rigenerato
nell'albero di lavoro è stato ripristinato il 08-11-2026 al blob tracciato,
dopo che la sua provenienza è risultata una ri-valutazione delle stesse righe;
la ri-valutazione è stata poi rifatta come artefatto separato e documentata
(`experiment_results/rivalutazione_confronto_mudilab_20261108.md`), e su quello
il test è indeciso (113 coppie su 161 escluse, nessuna discordante), quindi il
report si legge dal file ripristinato con uscita identica a quella calcolata
dal blob. I valori del
dataset generale a nove righe (0,3544; 0,3308; 0,0235; 0,4279; precisione 1,00;
richiamo 0,43; accordo 6/9) vengono da
`cwEnergyModular/results/semantic_evaluation_results.csv` e dalla prosa della
tesi, non da questo JSON, e non sono stati ricontrollati qui.

## Riferimenti

- Wilson, E. B. (1927), *Probable Inference, the Law of Succession, and
  Statistical Inference*, JASA 22(158), 209–212.
  <https://doi.org/10.1080/01621459.1927.10502953>
- McNemar, Q. (1947), *Note on the sampling error of the difference between
  correlated proportions or percentages*, Psychometrika 12(3), 153–157.
  <https://doi.org/10.1007/BF02295996>
- Newcombe, R. G. (1998), *Improved confidence intervals for the difference
  between binomial proportions based on paired data*, Statistics in Medicine
  17(22), 2635–2650.
- Efron, B. (1979), *Bootstrap Methods: Another Look at the Jackknife*, Annals
  of Statistics 7(1), 1–26. <https://doi.org/10.1214/aos/1176344552>
- Cameron, A. C., Gelbach, J. B., Miller, D. L. (2008), *Bootstrap-Based
  Improvements for Inference with Clustered Errors*, Review of Economics and
  Statistics 90(3), 414–427. <https://doi.org/10.1162/rest.90.3.414>
- Cohen, J. (1960), *A Coefficient of Agreement for Nominal Scales*,
  Educational and Psychological Measurement 20(1), 37–46.
  <https://doi.org/10.1177/001316446002000104>
- Rajpurkar, P., Zhang, J., Lopyrev, K., Liang, P. (2016), *SQuAD: 100,000+
  Questions for Machine Comprehension of Text*, EMNLP 2016.
  <https://arxiv.org/abs/1606.05250>
- Liang, P. et al. (2022), *Holistic Evaluation of Language Models*.
  <https://arxiv.org/abs/2211.09110>
- Lanham, T. et al. (2023), *Measuring Faithfulness in Chain-of-Thought
  Reasoning*. <https://arxiv.org/abs/2307.02726>
- Zheng, L. et al. (2023), *Judging LLM-as-a-Judge with MT-Bench and Chatbot
  Arena*. <https://arxiv.org/abs/2306.05685>
- Panickssery, A. et al. (2024), *LLM Evaluators Recognize and Favor Their Own
  Generations*. <https://arxiv.org/abs/2404.13076>
- Reimers, N., Gurevych, I. (2019), *Sentence-BERT*.
  <https://arxiv.org/abs/1908.10084>
- Berkeley Function Calling Leaderboard (BFCL), Gorilla project — risorsa di
  benchmark, non peer-reviewed. <https://gorilla.cs.berkeley.edu/leaderboard.html>

### Software

- statsmodels, `confint_proportions_paired` (metodo `newcomb`, cioè il metodo
  10 di Newcombe), documentazione di sviluppo (`/dev/`) e sorgente del ramo
  `main` consultati l'08-11-2026:
  <https://www.statsmodels.org/dev/generated/statsmodels.stats.proportion.confint_proportions_paired.html>.
  L'esempio `[[10, 5], [2, 20]]` è il caso di riferimento numerico della sezione
  3.6; il pacchetto dichiara la verifica contro R `ratesci` e `PropCIs`.
  Non è letteratura: è un'implementazione di riferimento, citata come tale.
