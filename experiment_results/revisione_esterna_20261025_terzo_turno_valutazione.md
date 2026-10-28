# Valutazione della revisione esterna di terzo turno (2026-10-25)

**Provenienza del materiale.** Le sette osservazioni valutate qui sono state
prodotte da un altro modello linguistico e fornite dall'utente come testo
incollato in chat, non come file del repository. Per AGENTS.md questo materiale è
**spunto, non evidenza**: ogni affermazione è stata verificata contro
`protocollo_v4_20261024.md` nella revisione corrente, contro il codice in
`cwEnergyModular/` e, dove l'affermazione era numerica, **per esecuzione**. Il
revisore stesso ha scritto di non aver modificato alcun file, e infatti nessuna
delle sette osservazioni è stata accolta perché scritta: quattro hanno prodotto
una correzione, tre no, e in nessun caso la ragione è l'autorità di chi scrive.

**Esito in una riga.** Tutte e sette le osservazioni descrivono difetti **già
chiusi** nel protocollo il 2026-10-24, con le stesse motivazioni che il revisore
porta; verificandole — non leggendole — sono emersi **cinque difetti reali
residui**, tutti di dichiarazione o di provenienza, nessuno di formula. Il solo
punto che il revisore indicava come bisognoso di verifica tecnica ulteriore,
`u_edge`, è l'unico dei cinque che ha richiesto un'esecuzione: il suo difetto non
era la giustificazione, già rettificata, ma la **provenienza** dei numeri.

| § | osservazione del revisore | stato nel protocollo | esito della verifica |
|---|---|---|---|
| 2.1 | `u_edge`: separare interpolazione, disallineamento e copertura; non giustificare il termine congelato con la sola interpolazione | **chiuso 2026-10-24**, P4.6 `:1694-1735`, F.11 `:2820-2853` | separazione già in vigore e **più forte** di quella chiesta: la via (b) `:1737-1753` elimina i termini 2 e 3 invece di maggiorarli. Difetto reale trovato: i numeri venivano da un calcolo **non tracciato**. Corretto con harness |
| 2.2 | `E_pred ≤ 0` come fallimento della previsione, conservato nel conteggio | **chiuso 2026-10-24**, P3.10 `:1146-1165`, F.10 `:2772` | il protocollo dice già `err_rel = None`, `pred_nonpositive = true`, il punto non passa. Difetto reale trovato: non era scritto che il punto **resta nel conteggio dei casi valutati**. Corretto |
| 2.3 | "intervallo bootstrap al 95%" → "intervallo operativo costruito dal protocollo" | **chiuso 2026-10-24**, P3.10 `:1167-1173`, P4.8 `:2007-2016`, F.14 `:3030-3034` | il nome esatto è già *intervallo operativo di conferma costruito dal protocollo*; la copertura è *nominale non arbitrata* finché P6.4 non la simula. Nessuna correzione necessaria |
| 2.4 | specificare a quale coordinata si riferiscono `a` e `b` | **chiuso 2026-10-24**, P3.3 `:877-890`, P3.4 `:928-929` | le derivate erano già etichettate nei due punti normativi. Difetto reale trovato: **tre elenchi derivati** le riportavano senza coordinata. Corretti, e il controllo incrociato ne ha trovato un quarto |
| 2.5 | registrare le sostituzioni per cella sperimentale | **chiuso 2026-10-24**, P3.12 `:1200-1214` | il conteggio esiste già, con la motivazione del revisore (selezione dei prompt). Difetto reale trovato: l'**unità** non era dichiarata e F.17 ometteva il campo. Corretti |
| 2.6 | il pre-pilota deve verificare la fattibilità dei livelli bassi `(8,4)` e `(12,32)` | **chiuso 2026-10-24**, P3.15 `:1266-1299` | già esteso a entrambe le estremità, con `(8,4)` come vertice di `hull_design` e `(12,32)` come punto di conferma. Nessuna correzione necessaria |
| 2.7 | dichiarare che `c` assorbe parte di un effetto quadratico in `N_out` | **chiuso 2026-10-24**, P3.3 `:892-909`, F.8 `:2717-2724` | l'identità `Σ(N_in+j) = N_in·N_out + N_out·(N_out+1)/2` è scritta, `c` dichiarato assorbitore parziale e il modello primario **approssimazione dichiarata**. Nessuna correzione necessaria |

---

## 1. §2.1 — `u_edge` e i tre errori di bordo

**Cosa dice il revisore.** Che non basta correggere la motivazione: se `u_edge` è
un budget d'incertezza, non si può mantenere la formula esistente limitandosi a
spiegarla diversamente quando quella formula non copre tutti gli errori che si
intendono includere. La correzione deve separare ciò che è dimostrato da ciò che
resta da quantificare, **senza introdurre un nuovo valore numerico non
verificato**. Aggiunge che i calcoli riportati nel testo sono risultati della
verifica descritta dall'autore e che, senza accesso al codice e alla procedura di
calcolo, non li presenterebbe come una verifica indipendente.

**Verifica.** La separazione richiesta è nel testo congelato dal 2026-10-24.
P4.6 `:1694` si intitola *Quale errore maggiora, davvero* e dichiara che la
rettifica corregge la giustificazione e **non** la formula né il valore
congelato; `:1700`, `:1721` e `:1727` numerano i tre errori — interpolazione,
disallineamento, copertura — e `:1733` scrive che il valore congelato **non** li
maggiora tutti e tre. Il protocollo va oltre ciò che il revisore chiede: non si
limita a quantificare il residuo, lo elimina. La via (b) di `:1737-1753` impone
come **requisito vincolante di P5** la lettura sincrona del contatore ai bordi di
finestra, con `Δt_W` preso dalla stessa coppia di letture (`:1765-1775`), e con
due letture sincrone il bordo della finestra *è* un campione del contatore: niente
interpolazione, niente sfasamento, niente clamp a 1 s. La via (a) — aggiungere un
termine stimato sul `ΔP_tick` misurato — è scartata con tre ragioni scritte, e la
prima è esattamente l'avvertenza del revisore: chiede un termine **non
calcolabile**, perché `ΔP_tick` oggi non è misurato da nessuna parte del codice.

Il punto del revisore che invece **non** era coperto è il secondo: la
provenienza. I quattro numeri citati (`3,0e-11 J`, `1,4062 J`, `1,8750 J`,
`0,9375 J`) erano prodotti da un calcolo eseguito mentre si scriveva la
valutazione di primo turno e non salvato da nessuna parte. Per AGENTS.md
un'analisi non tracciata è un numero che nessuno può rigenerare, quindi non è
evidenza — e il revisore lo stava dicendo senza sapere di aver ragione anche sul
nostro lato del testo.

**Difetto reale trovato (D1, provenienza).** Creato
`u_edge_interpolazione_probe.py` alla radice del repository, dove sta la
convenzione degli harness citati dalla tesi o dal protocollo. Non tocca hardware,
non legge il registro EMI, non dipende da Ollama: è aritmetica su forme d'onda
sintetiche, quindi eseguibile ovunque e riproducibile bit per bit. Cinque
verifiche, 5/5 superate, exit 0. P4.6 `:1703` e F.11 `:2827` lo citano ora come
costruttore dei numeri. §7 riporta cosa verifica ciascuna delle cinque e cosa è
emerso eseguendole.

**Difetto reale trovato (D2, ritiro incompleto).** La correzione di D1 ritirava
il residuo `3,0e-11 J` in P4.6 e lasciava in F.11 la stessa cifra, presentata
come "verificato numericamente il 2026-10-24". Il controllo incrociato chiesto
dal revisore in chiusura l'ha trovato: F.11 `:2826-2834` cita ora l'harness e
dichiara il ritiro anche in quella occorrenza. Un numero ritirato nel punto
congelato e ancora vivo nel formulario è peggio di un numero sbagliato in un
punto solo, perché il formulario è ciò che un implementatore copia.

**Cosa non è cambiato.** La formula `u_edge,b = 2 · P_peak,b · δt_edge,b`
(F.11 `:2798`) e il suo valore con i numeri di produzione, 10,5 J. Nessun nuovo
valore numerico è stato introdotto nel budget: il termine di interpolazione resta
**fuori** dal valore congelato, dichiarato tale, e la copertura resta fuori con
esso — è la via (b) a rimuoverli, non una stima.

---

## 2. §2.2 — `E_pred ≤ 0`

**Cosa dice il revisore.** Calcolare `err_rel` soltanto se `E_pred > 0`;
altrimenti registrare il caso come fallimento della previsione, conservandolo nel
conteggio dei casi valutati. Non va escluso silenziosamente dal denominatore
statistico.

**Verifica.** Le prime due clausole sono nel testo congelato dal 2026-10-24.
P3.10 `:1146-1155` si intitola *Denominatore non positivo*, dichiara che
l'aggiunta chiude una lacuna e non cambia il criterio, e prescrive:

```
E_pred ≤ 0  →  err_rel non definito (None, non 0, non +inf aritmetico)
               flag pred_nonpositive = true
               il punto NON passa la validazione
```

F.10 `:2772` ripete la stessa regola nel formulario, e `:2789-2792` ne dà la
ragione: `E0` non è vincolato positivo (P3.3, flag `intercept_nonphysical`),
quindi una divisione implicita produrrebbe un `err_rel` senza significato. La
terza clausola — la conservazione nel conteggio — era invece scritta solo in
negativo, "non escluso dal criterio", che non è la stessa cosa: un lettore può
non escluderlo dal criterio e comunque non contarlo.

**Difetto reale trovato (D3).** P3.10 `:1157-1161` dice ora che il punto **resta
nel conteggio dei casi valutati**, e ne dà la ragione strutturale invece di
un divieto: i punti di conferma sono due e l'anello 6 di P4.9 (`:2088`) li
richiede entrambi, quindi un `pred_nonpositive` non può essere né diluito in una
media né tolto dal denominatore. Il difetto non è cosmetico: con due soli casi,
toglierne uno in silenzio cambia il denominatore del gate da 2 a 1 e rende
l'anello 6 soddisfatto da un unico punto.

**Cosa non è cambiato.** Il criterio `err_rel ≤ 10%` **e** `E_meas ∈
intervallo_conf`, la soglia del 10% e la sua dichiarazione come scala della
sensibilità della baseline (1 W ≈ 6–11% di J/token), non come soglia scientifica
(P3.10 `:1138-1144`, F.10 `:2779-2781`).

---

## 3. §2.3 — il nome dell'intervallo

**Cosa dice il revisore.** Sostituire "intervallo bootstrap al 95%" con
"intervallo operativo costruito dal protocollo", perché il fatto che i quantili
bootstrap siano al 95% non implica che l'intervallo finale abbia copertura
nominale del 95%.

**Verifica.** Già in vigore, con lo stesso argomento e la stessa conclusione.
P3.10 `:1167-1173`, *Nome dell'intervallo*: `intervallo_conf` **non è** un
intervallo al 95%, i quantili bootstrap lo sono e poi vengono allargati di due
semi-range `u_conf`, quindi la copertura nominale non è il 95% e non è
quantificata; si chiama *intervallo operativo di conferma costruito dal
protocollo*. F.10 `:2788-2790` ripete la dichiarazione nel formulario. Il punto
generale è trattato separatamente in P4.8 `:2007-2016` — *Il bootstrap produce un
intervallo al 95% **nominale**. Nominale non è sinonimo di verificato* — e la
conseguenza è un vincolo sulla tesi: finché P6.4 non simula la copertura, si
scrive *bootstrap, livello nominale 95%, copertura non arbitrata* (F.14
`:3030-3034`) e la tesi non può scrivere "95%". P4.3 `:1396` definisce
"copertura nominale" come voce a sé.

Nessuna correzione necessaria. La forma è congelata e non cambia; il revisore
chiedeva esattamente ciò che il protocollo già fa: cambiare come la si nomina,
non cosa calcola.

---

## 4. §2.4 — la coordinata di `a` e di `b`

**Cosa dice il revisore.** Specificare a quale coordinata si riferisce ciascun
costo marginale: `∂E/∂N_in = a + c·N_out,ref` e `∂E/∂N_out = b + c·N_in,ref`.

**Verifica.** Le due formule sono nel testo congelato, etichettate, nei due
punti normativi: P3.3 `:887` e P3.4 `:928-929`, con F.8 `:2705-2706` che le
riporta nel formulario. P3.3 `:886-890`
aggiunge la qualifica che rende impossibile lo scambio: `a` è J/token di prefill
marginale **a `N_out = 0`**, `b` è J/token di decode marginale **a `N_in = 0`**,
e la qualifica non è una formula nuova ma ciò che la derivata già dice, scritta
dove la parola "marginale" compare da sola.

**Difetto reale trovato (D4).** Tre elenchi derivati riportavano le espressioni
**senza** la derivata davanti: P3.11 (elenco delle metriche), P4.8 `:1987-1991`
(elenco delle quantità dell'intervallo parametrico) e la prosa di F.8 `:2714`, che
nel formulario riscriveva a parole ciò che `:2705-2706` aveva appena scritto in
formula. Le prime due, più F.14, anche nell'ordine inverso rispetto ad `a`/`b`;
F.8 nell'ordine giusto, ma senza etichetta vale lo stesso. Sono i
punti che un implementatore legge per sapere **cosa pubblicare**, ed elencare
`b + c·N_in,ref` per primo, senza etichetta, invita a leggerlo come il costo
marginale di `N_in`. Corretti tutti e tre: P3.11 `:1179-1180`, P4.8 `:1988` e
F.8 `:2714` scrivono ora la coordinata.

**Difetto reale trovato (D5, dal controllo incrociato).** La quarta occorrenza è
lo pseudocodice di F.14 `:3007`, che elencava
`q2,5 e q97,5 di b + c·N_in,ref ; a + c·N_out,ref ; ...` — stesso difetto, nel
punto in cui la formula diventa una riga di codice da trascrivere. Etichettata.
Le occorrenze erano quindi **quattro**, non tre: la chiusura era stata dichiarata
sulla base di un elenco incompleto, e l'ha completata il controllo incrociato,
non la lettura. La riga 36 del registro dei difetti (`:36`) lo dice.

**Cosa non è cambiato.** Nessuna formula, nessun coefficiente, nessun riferimento
predeclarato. `(32,32)` e `(128,128)` restano i due riferimenti (F.8 `:2710`).

---

## 5. §2.5 — le sostituzioni

**Cosa dice il revisore.** Registrare il numero di sostituzioni per cella
sperimentale, perché sostituirle espone il disegno alla selezione dei prompt.

**Verifica.** Già in vigore dal 2026-10-24, con la stessa motivazione. P3.12
`:1200-1214`, *conteggio delle sostituzioni*: `design_deviation_count` registra
le sostituzioni eseguite e, per ciascuna, il prompt scartato e quello che lo
sostituisce; la ragione dichiarata è che sostituire le richieste che terminano
presto **seleziona** prompt che generano a lungo, quindi un blocco con molte
sostituzioni non contiene un campione casuale di prompt ma una popolazione
selezionata dal criterio di sostituzione; il conteggio non corregge l'effetto, lo
rende visibile.

**Difetto reale trovato (D6).** L'**unità** non era dichiarata: cella o blocco?
Non è una scelta amministrativa. `m = 3` è il numero di richieste di un blocco e
una cella ne ha tre, quindi il testo congelato diceva "se il conteggio di una
cella arriva a un valore paragonabile a `m`" — cioè confrontava fino a nove
richieste con una soglia tarata su tre. P3.12 `:1201-1214` dichiara ora il campo
**per blocco**, dice che il valore per cella è la somma dei tre blocchi e va
confrontato con `3m`, e riporta la soglia di discussione in entrambe le unità.

**Difetto reale trovato (D7).** F.17 `:3168-3173`, che ripete l'elenco dei
contenuti obbligatori di P3.13, **ometteva** `design_deviation_count`: il campo
era obbligatorio nel punto congelato e assente dall'elenco derivato che P5 usa
come specifica delle colonne. Aggiunto, con la nota che dice quando e perché
(`:3173`).

**Cosa non è cambiato.** La regola di sostituzione (`:1197-1199`: la misura resta
valida per P2, non è assegnabile alla cella, si sostituisce e si registra, non si
cambia il target), la tolleranza ±5% sul `N_in` target, e `m = 3`.

---

## 6. §2.6 e §2.7 — pre-pilota sui livelli bassi, e ruolo di `c`

**§2.6, cosa dice il revisore.** Il pre-pilota deve verificare la fattibilità dei
livelli bassi `(8,4)` e `(12,32)`, perché se non sono raggiungibili nelle
coordinate effettive la geometria dichiarata non può dirsi validata solo perché i
livelli massimi funzionano.

**Verifica.** Già in vigore dal 2026-10-24, con gli stessi due punti e la stessa
conseguenza. P3.15 `:1266-1299`: il pre-pilota verifica la fattibilità dei livelli
**a entrambe le estremità**, in alto e in basso; `(8,4)` è un **vertice
dell'inviluppo convesso** e se 8 token di input o 4 di output non sono
raggiungibili entro la tolleranza ±5% di P3.12 il vertice non esiste nelle
coordinate dichiarate e `hull_design` è costruito su un punto fittizio, con
`hull_margin_design_tok` di tutti gli altri punti calcolato contro un bordo che
non c'è (`:1274-1278`); `(12,32)` è il punto operativo di conferma con
`hull_margin_design_tok = 1,33`, più piccolo della tolleranza del prompt, quindi
la sua fascia dipende dal token reale e non dal target (`:1279-1283`); la
tolleranza ±5% è incompatibile con lo scarto misurato fra target e actual nel run
v3 (`N_in = 64` dichiarato → 126 token reali), e su `N_in = 8` uno scarto di
quella taglia non è riducibile a una tolleranza del 5%: va misurato, non assunto
(`:1284-1295`). La chiusura è `:1297-1299`: se un livello — alto **o basso** —
non è raggiungibile, P3 si riapre e si dichiara; non si cambia il livello in
silenzio. P4.7 `:1919-1920` e P4.14 `:2243-2246` ne propagano l'effetto su
entrambi gli inviluppi. Nessuna correzione necessaria.

**§2.7, cosa dice il revisore.** Dichiarare che il modello primario è
un'approssimazione il cui `c` assorbe parzialmente un effetto quadratico in
`N_out`, senza per questo aggiungere un termine quadratico; e mantenere le
percentuali di errore attribuite alla sua simulazione come affermazioni non
riprodotte.

**Verifica.** Già in vigore dal 2026-10-24. P3.3 `:892-909`, *Cosa assorbe `c`, e
il termine quadratico che il modello non ha*: l'identità
`Σ_{j=1..N_out}(N_in + j) = N_in·N_out + N_out·(N_out+1)/2` è scritta a `:898`;
`:901-905` dichiarano che la stessa giustificazione fisica che fonda `c ≥ 0`
implica quel termine omesso, che **non** è un motivo per aggiungerlo (il disegno
di P3.5 non lo identifica separatamente da `b` senza livelli di `N_out` più
distanziati, e P3.3 congela l'assenza di quadratici), ma che va scritto che `c`
assorbe parte di un effetto con componente quadratica e che il modello primario è
un'**approssimazione dichiarata** della superficie, non la sua forma fisica; se il
lack-of-fit di P3.9 rifiuta il modello, questa è la prima spiegazione strutturale
da citare. F.8 `:2717-2724` ripete tutto nel formulario. Nessuna correzione
necessaria.

**Sulle percentuali della simulazione.** Il revisore chiede che restino
identificate come affermazioni non riprodotte. Verificato: **il protocollo non
contiene nessuna percentuale attribuita a una simulazione del revisore**. Le
uniche percentuali numeriche presenti sono misure del progetto con il proprio
artefatto accanto (CV 8,99% e 2,20% `:355`, ±4,0–4,8% `:358`, CV 22,5% con
`lhm_validation_v3_20261023_153604.md:12-20,24` `:428`, `:506`, `:2335`) oppure
soglie congelate (10%, 20%, 5%). La regola è quindi già rispettata per assenza, e
va dichiarata come valevole per la tesi: un numero di simulazione prodotto da un
revisore esterno entra solo se il revisore fornisce la procedura, o se la si
riscrive come harness tracciato — la stessa regola applicata a D1.

---

## 7. L'harness: cosa verifica, e cosa è emerso eseguendolo

`u_edge_interpolazione_probe.py`, radice del repository. Costanti dichiarate nel
sorgente: `P_PEAK_W = 35.0`, `DT_TICK_S = 0.30` (l'intervallo **misurato** sul
percorso EMI, non i 0,05 s dichiarati da `POWER_SAMPLE_INTERVAL_S`,
`energy_session.py:80`), `D_GRADINO_W = 25.0`, `CLAMP_COPERTURA_S = 1.0`,
`N_GRIGLIA = 2_000_001` (dispari, quindi contiene esattamente il punto medio del
tick). Uso: `python u_edge_interpolazione_probe.py`.

| # | relazione verificata | esito |
|---|---|---|
| 1 | a potenza costante `E(t) = P·t` è lineare, l'interpolazione lineare fra gli estremi è esatta e l'errore è nullo in aritmetica esatta; il residuo misurato è arrotondamento e va dichiarato **relativo** | PASSA: residuo relativo 7,027e-12 a `P = 35 W`, identico a 70 W e 140 W |
| 2 | `max_t |E(t) − interp(t)| = ΔP · f · (1 − f) · Δt_tick`, massimo `ΔP·Δt_tick/4` in `f = 1/2`; il livello di potenza non compare | PASSA a sette valori di `f`: 0,6750 / 1,4062 / 1,8000 / 1,8750 / 1,8000 / 1,4063 / 0,6750 J, scarto massimo dall'analitico 1,69e-06 J = passo di griglia |
| 3 | per una rampa lineare l'errore massimo è `ΔP·Δt_tick/8`, metà del gradino a `f = 1/2` | PASSA: 0,9375 J numerico contro 0,9375 J analitico, scarto 3,00e-15 J |
| 4 | il termine congelato con i numeri di produzione | PASSA: `2 × 35 W × 0,15 s = 10,50 J`, coincide con il valore dichiarato |
| 5 | il clamp di copertura supera il budget congelato | PASSA: `P_peak · 1 s = 35,00 J` = 3,33 volte `u_edge,b`, quindi il valore congelato non maggiora tutti e tre gli errori |

**La verifica 1 è fallita alla prima stesura, e il fallimento è la prova del
ritiro.** Il criterio originale confrontava residui **assoluti** e li voleva
decrescenti al crescere della griglia: l'harness restituiva 4/5 e exit 1, perché
`np.cumsum` accumula arrotondamento e il residuo assoluto **cresce** con la
densità di griglia — 3,553e-13 / 7,189e-12 / 2,271e-11 J per `n` = 10 001 /
100 001 / 1 000 001 — ed è proporzionale a `P`: 1,476e-10 J a 70 W e 2,951e-10 J
a 140 W, contro 7,379e-11 J a 35 W. La stessa versione stampava "il livello di
potenza NON compare" mentre il suo output mostrava il contrario. Corretti
entrambi: il criterio è ora relativo a `P·Δt_tick` con soglia 1e-10, e la riga
stampata dice che l'assoluto è proporzionale a `P` e il relativo no. Ne segue che
il `3,0e-11 J` pubblicato in P4.6 e in F.11 non era sbagliato nel metodo ma
**non pubblicabile**: era l'assoluto di una griglia non dichiarata, e un lettore
che cambi griglia non lo riproduce. Il numero pubblicato è ora il relativo, con
la griglia accanto.

**Cosa l'harness non dimostra.** Non misura `ΔP_tick` nel blocco — nessuna parte
del codice lo fa — quindi i numeri delle verifiche 2 e 3 sono aritmetica di una
forma d'onda ipotizzata, non misure. Non dimostra che 10,5 J coprano il
disallineamento reale della campagna: quello dipende dal `Δt_tick,b` osservato,
che la v4 registra come `sampling_interval_observed_s`. E non è una validazione
della scala assoluta, che resta non arbitrata senza un wattmetro esterno.

---

## 8. Controllo incrociato delle occorrenze dei simboli modificati

Richiesto esplicitamente dal revisore in chiusura ("comprese tabelle, schema dei
dati e riferimenti interni"). Metodo: ricerca sull'**intero** documento per
ciascun simbolo, non per frase — la lezione del primo turno, dove la quinta
occorrenza di "126 token" era invisibile a un `grep` sulla frase perché il testo
andava a capo fra il numero e la parola. Per ogni occorrenza: sezione di
appartenenza, coerenza con la definizione, presenza negli elenchi derivati.

| simbolo | occorrenze nel protocollo (revisione a 3198 righe) | esito |
|---|---|---|
| `3,0e-11 J` ritirato, `7,0e-12`, harness | intestazione P4 `:14`, registro `:35` e `:36` (la riga dei costi marginali cita il ritiro per analogia, ed è così che il controllo l'ha trovata), P4.6 `:1703`, `:1705`, `:1707`, F.11 `:2827`, `:2829`, `:2830` | coerenti dopo D2: le uniche due occorrenze vive del numero ritirato erano P4.6 e F.11, ed entrambe lo dichiarano ritirato citando l'harness |
| `∂E/∂N_in`, `∂E/∂N_out` | registro `:36`, P3.3 `:887`, P3.4 `:928-929`, P3.11 `:1179-1180`, P4.8 `:1988`, F.8 `:2705-2706`, `:2714`, F.14 `:3007` | tutte e otto etichettate con la propria coordinata; nessuna occorrenza residua delle espressioni nude |
| `design_deviation_count` | intestazione P3 `:13`, registro `:37`, narrativa `:63`, P3.12 `:1202`, P3.13 `:1242`, F.17 `:3172` | unità "per blocco" dichiarata in P3.12, ripetuta fra parentesi in P3.13 e in F.17; soglia di discussione in entrambe le unità (`m` e `3m`) |
| `pred_nonpositive`, `err_rel` | intestazione P3 `:13`, registro `:38`, narrativa `:58`, P3.10 `:1133`, `:1138`, `:1147`, `:1152-1153`, `:1160`, P3.13 `:1243`, P4.9 `:2088`, P6.5 `:2458-2459`, F.0 `:2521-2522`, F.10 `:2767`, `:2770`, `:2772`, `:2792`, F.16 `:3136`. Il solo identificatore `pred_nonpositive` compare 10 volte: `:13`, `:38`, `:58`, `:1153`, `:1160`, `:1243`, `:2088`, `:2459`, `:2522`, `:2772`. Il solo `err_rel` compare 13 volte: `:1133`, `:1138`, `:1147`, `:1152`, `:1243`, `:2088`, `:2458`, `:2521`, `:2767`, `:2770`, `:2772`, `:2792`, `:3136`. Gli intervalli a due righe nelle celle precedenti (`:1152-1153`, `:2458-2459`, `:2521-2522`) sono unioni: una riga porta l'uno, l'altra l'altro | `err_rel` definito una sola volta e citato con la condizione `E_pred > 0` in entrambi i punti normativi; `pred_nonpositive` è campo obbligatorio in P3.13, P6.5 e F.0; l'anello 6 di P4.9 lo tratta come fallimento |
| `intervallo_conf` e il suo nome | identificatore, 13 occorrenze: intestazione P3 `:13`, P3.10 `:1135`, `:1139`, `:1162`, `:1167`, P3.13 `:1244`, P4.9 `:2088`, P6.5 `:2458`, F.0 `:2521`, F.10 `:2769`, `:2770`, `:2787`, `:2788`. Nome esteso *intervallo operativo di conferma*, 3 occorrenze: narrativa `:58`, P3.1 `:850` (D7), P3.10 `:1170` (dove è definito). Forma breve *intervallo di conferma di P3.10*: P4.6 `:1802`, P6.4 `:2389` | la forma `[q2.5 − 2·u_conf, q97.5 + 2·u_conf]` è identica nei due punti in cui è scritta; **nessuna** occorrenza lo chiama intervallo al 95%. Le 11 occorrenze di "95%" nel documento (`:1167-1169`, `:1396`, `:2007`, `:2015-2016`, `:2362`, `:2788`, `:3030`, `:3034`) o lo negano esplicitamente o lo qualificano come *nominale, copertura non arbitrata*. Distinto e correttamente nominato a parte l'oggetto "intervallo bootstrap" (`:1177`, `:1396`, `:1797`, `:2858`), che sono i quantili interni dei coefficienti, non l'intervallo di decisione |
| numeri di bordo (`10,5 J`, `1,8750 J`, `0,9375 J`) | P4.6 `:1717-1718`, `:1724`, `:1734`, `:1783`, F.11 `:2834`, `:2837`, `:2843`, `:2850` | tutti coerenti con l'harness; `1,8750 J` scritto con quattro cifre in entrambe le occorrenze; il `3,75 J` del revisore di primo turno non è nel protocollo e non ci entra |

Due occorrenze che il controllo incrociato ha trovato **sbagliate negli
artefatti**, non nel protocollo, e corrette: la tabella di §6 della valutazione di
secondo turno elencava per `thin_support` un riferimento a "P4.3 `:1389`" dove
`thin_support` **non compare** (quella è la riga che definisce la metrica del
margine, da cui il flag dipende senza nominarlo), e per `hull_margin_tok` un
elenco parziale che ometteva P4.1, P3.15, due occorrenze in P4.7 e P6.5. Un
controllo incrociato che elenca un'occorrenza inesistente non è un controllo
incrociato: entrambe le righe sono state riscritte complete.

---

## 9. Riparazione degli ancoraggi

Le correzioni di questo turno cambiano la lunghezza del protocollo, e ogni
`:NNNN` degli artefatti che lo citano va riportato alla revisione corrente o
dichiarato stante. Regola di AGENTS.md: se un ancoraggio non torna, il file è
stantio e va corretto, non ignorato.

| documento | cosa è stato fatto |
|---|---|
| `protocollo_v4_20261024.md` | 3147 → 3154 righe con l'emendamento su `u_edge` (commit `aad8a91`), 3154 → 3198 con le correzioni D3-D7 di questo turno. Tutte le aggiunte sono dichiarate in testa, nel registro dei difetti e nel punto in cui stanno |
| `revisione_esterna_20261025_secondo_turno_valutazione.md` | 127 ancoraggi traslati di +4 (righe 69-2825) e +9 (righe ≥ 2826), con la mappa costruita per `difflib` sulla versione precedente ricostruita per sostituzione inversa; **nessun** ancoraggio cadeva nelle due regioni riscritte, quindi nessuna mappatura ambigua. Quattro righe di §6 sono state riscritte con l'elenco **esaustivo** delle occorrenze, generate dal documento e non a mano: `hull_margin_tok` (18 occorrenze), `pre_range_w`/`dP` (56), `control_unstable` (12), più la qualifica di P4.9 `:2086` nella riga di `u_bias`. Le prime due erano state trovate già una volta in questo turno e la correzione era risultata essa stessa sbagliata; lunghezza citata del protocollo corretta |
| `revisione_esterna_formule_20261024_valutazione.md` | i suoi 23 ancoraggi al protocollo puntano alla revisione del 2026-10-24 e sono **dichiarati stanti** invece che ricalcolati: ricalcolarli produrrebbe numeri validi oggi a fronte di una verifica eseguita su un testo diverso. Aggiunti la nota di provenienza sui numeri di §2.1, la dichiarazione della convenzione di conteggio delle righe e l'aggiornamento dell'auto-riferimento di **quel** documento alla propria riga (era la 126, ora la 145: numeri relativi a `revisione_esterna_formule_20261024_valutazione.md`, non al protocollo — scritti qui in prosa e non come `:NNNN` proprio perché un ancoraggio nudo si leggerebbe contro il protocollo) |

**Fuori-di-uno nella convenzione di conteggio, dichiarato.** I conteggi di
lunghezza scritti nei due artefatti e nel messaggio del commit `aad8a91`
("3148 → 3155") usavano `len(read().split('\n'))`, che conta anche la stringa
vuota dopo l'ultimo `\n` e restituisce una riga in più del numero dell'ultima
riga di contenuto. Gli ancoraggi `:NNNN` usano la numerazione di contenuto,
quella di `wc -l`: i valori corretti sono 3147 → 3154, e oggi 3198. Il messaggio
di commit non si corregge — un commit si rifà, non si riscrive, e riscriverlo
sarebbe un `--amend` su lavoro già consegnato — e resta come traccia con questa
dichiarazione accanto. Nessun ancoraggio dipendeva dalla convenzione, perché
tutti erano stati verificati stampando la riga citata.

---

## 10. Cosa non è cambiato

Nessuna formula congelata, nessuna soglia, nessun valore numerico congelato,
nessun disegno. Nel dettaglio:

- `u_edge,b = 2 · P_peak,b · δt_edge,b` e i suoi 10,5 J con i numeri di
  produzione (F.11 `:2798`, P4.6 `:1782-1786`);
- `budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²` (F.11 `:2801`), e la
  forma di combinazione di `budget_base_w` resta la decisione provvisoria rinviata
  ai dati del pilota P2.9 (P1.7, P1.13);
- `err_rel ≤ 10%`, la soglia di 2 token di `thin_support`, 1,0 W sui controlli, i
  sei coppie e il quorum di quattro del gate, 0,05 sul lack-of-fit: nessuna
  soglia spostata;
- il modello a quattro parametri senza quadratici (P3.3 `:870-874`), i 39 blocchi
  e i 33 di fit, i due punti di conferma `(12,32)` e `(256,192)`, i pesi
  `w_b = 1/budget_fit_b²`;
- **nessun troncamento reintrodotto**: `E_net_incremental` resta firmato e
  conservato con il flag `negative_increment` (P1.6, P3.2 `:866-868`), e nessuna
  delle correzioni di questo turno tocca il denominatore di `r_A`;
- la via (b) resta un requisito di P5, e **il codice sorgente di produzione resta
  bloccato** fino al congelamento di P5. L'unico file scritto in questo turno è
  l'harness, che è un'analisi e non produzione: non importa `cwEnergyModular`, non
  legge il registro EMI, non tocca hardware.

Le cinque correzioni sono di dichiarazione e di provenienza. Quattro aggiungono
una parola o un'unità che mancava; una aggiunge un costruttore a numeri che non
ne avevano. Nessuna toglie un vincolo.

---

## 11. Verifiche eseguite e loro limiti

Eseguite il 2026-10-25 sulla revisione del protocollo a 3198 righe di contenuto.

1. **Harness dei tre errori di bordo**: `python u_edge_interpolazione_probe.py`,
   5/5 verifiche, exit 0. È la sola verifica numerica nuova di questo turno, ed è
   tracciata.
2. **Controllo incrociato dei simboli**: ricerca esauriente sul documento per sei
   gruppi di simboli (§8), con sezione di appartenenza di ogni occorrenza. Ha
   prodotto D2 e D5, cioè due difetti che la lettura dei punti segnalati non
   aveva trovato: entrambi stavano in un elenco derivato, non nel punto
   congelato.
3. **Rimappatura degli ancoraggi**: automatica per traslazione, poi **ogni**
   ancoraggio delle tabelle di §6 e §7 del secondo turno è stato verificato
   stampando le righe citate. Due sono risultati sbagliati e corretti; il resto
   torna.
4. **Non eseguito**: nessuna misura su hardware, nessuna lettura del registro
   EMI, nessun run di Ollama. Nessun numero di questo turno proviene dalla
   campagna, che non è ancora stata eseguita. `ΔP_tick` resta non misurato da
   nessuna parte del codice, ed è la ragione per cui la via (a) è scartata.
5. **Limite di metodo.** I numeri delle verifiche 2, 3 e 5 dell'harness sono
   aritmetica su forme d'onda sintetiche con parametri ipotizzati (`ΔP_tick = 25 W`,
   `P_peak = 35 W`, clamp a 1 s letto dal codice): dimostrano le **relazioni**,
   non la grandezza degli errori nella campagna. La verifica 5 è l'unica il cui
   ingresso è letto dal codice (`energy_session.py:1111-1116`).
6. **Controllo automatico degli ancoraggi, su entrambi i documenti**: due criteri
   meccanici applicati a tutte le coppie `SEZIONE `:A-B`` e a tutte le righe di
   tabella — (i) l'intervallo deve cadere dentro lo span della sezione nominata,
   span ricostruito dalle intestazioni del protocollo; (ii) l'intervallo citato
   deve contenere almeno una riga con il simbolo soggetto della riga. Esito su
   questo documento: 79 coppie, 0 fuori sezione; i 67 ancoraggi nudi stampati uno
   per uno con la riga citata. Esito sulla tabella di §6 del secondo turno: 100
   coppie, 3 fuori sezione e 1 ancoraggio senza soggetto — le tre sono citazioni
   della forma sbagliata precedente dentro la cella dell'esito, e restano
   legittime perché sono dichiarate come tali.
   Difetti trovati e corretti, **sette in tutto**. In questo documento: un'etichetta
   `P4.15` per un ancoraggio che sta in P4.14 (la sezione P4.15 non esiste); gli
   ancoraggi di codice di §12 leggibili come ancoraggi al protocollo; tre elenchi
   di occorrenze incompleti o imprecisi in §8 (mancava il registro `:36` nella
   riga del residuo ritirato; mancavano le tre occorrenze in testa nella riga di
   `pred_nonpositive`; la riga di `intervallo_conf` attribuiva a F.10 il nome
   esteso dell'intervallo, che F.10 non usa — F.10 nega che sia un intervallo al
   95%, `:2788`, che non è la stessa cosa). Nel secondo turno: **quattro** righe di
   §6 sbagliate, elencate in quel documento, di cui una — `hull_margin_tok` — era
   la riga che il terzo turno aveva **già corretto una volta**, sostituendo
   `:2216` con `:2216-2219` e lasciando l'etichetta `P4.8` su righe che stanno in
   P4.13. La lezione è la stessa di D2 e vale per i controlli incrociati quanto
   per i ritiri: correggere un'occorrenza senza verificare a quale sezione
   appartiene produce un riferimento più preciso nella forma e falso nel
   contenuto. Un documento che esegue il controllo incrociato sugli
   altri va sottoposto allo stesso controllo.
7. **Limite di indipendenza.** L'harness è scritto da chi ha scritto il
   protocollo, e verifica relazioni matematiche che sono note: la sua funzione non
   è scoprire se l'interpolazione lineare è esatta su una retta, ma rendere quei
   numeri **rigenerabili** da un terzo. Resta vero ciò che il revisore ha scritto:
   senza accesso alla procedura, un calcolo descritto a parole non è una verifica
   indipendente. Ora la procedura c'è ed è nel repository.

---

## 12. Riferimenti

- `protocollo_v4_20261024.md` — P3.3, P3.4, P3.10, P3.11, P3.12, P3.13, P3.15,
  P4.3, P4.6, P4.7, P4.8, P4.9, P4.12, P4.14, P6.2, P6.4, P6.5, F.0, F.8, F.10,
  F.11, F.13, F.14, F.16, F.17;
- `u_edge_interpolazione_probe.py` — harness dei tre errori di bordo;
- `cwEnergyModular/energy/energy_session.py:80` (`POWER_SAMPLE_INTERVAL_S`),
  `:1103-1124` (`_emi_cum_at`), `:1111-1116` (clamp di copertura),
  `:1245-1250` (bordi interpolati);
- `cwEnergyModular/energy/local_energy.py:156`, `:171`, `:175`, `:309-310`.

- `revisione_esterna_formule_20261024_valutazione.md` — primo turno, §2.1 e §9;
- `revisione_esterna_20261025_secondo_turno_valutazione.md` — secondo turno, §5,
  §6, §7;
- commit `aad8a91` (harness e emendamento P4.6).
Negli ultimi due elenchi i `:NNNN` che seguono il nome del file sono righe **di
quel file**, non del protocollo: la convenzione è la stessa, il referente cambia,
e qui è scritto esplicitamente perché un ancoraggio nudo in un documento che ne
cita due diversi è ambiguo per chi legge. Verificati uno per uno il 2026-10-25:
`POWER_SAMPLE_INTERVAL_S = 0.05` a `energy_session.py:80`, `def _emi_cum_at` a
`:1103` con l'interpolazione `e0 + (e1 - e0) * (t - t0) / (t1 - t0)` a `:1124`,
il clamp entro 1 s a `:1111-1116`, la coppia di bordi `ca, cb` a `:1249`;
`dt = max(t_end - t_start, 1e-6)` a `local_energy.py:156`, la sottrazione delle
finestre escluse a `:171`, `res.duration_s = dt` a `:175`, il troncamento
`max(package_energy_j - baseline_energy_j, 0.0)` a `:309-310` — quest'ultimo è il
difetto dichiarato in P1.6, non una formula del protocollo.
