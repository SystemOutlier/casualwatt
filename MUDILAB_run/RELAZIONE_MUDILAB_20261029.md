# MUDILAB: cosa non funzionava, cosa ho cambiato, che cosa misuro

Data: 29 ottobre 2026. Ambito: la pipeline causale `MUDILAB` della relatrice
(classificatore, traduttore, esperto causale con tool pyagrum sulla rete
*insurance*). I file originali stanno in `MUDILAB/` e non sono stati toccati;
le correzioni stanno in `MUDILAB_run/consegna/*_corretto.py`.

Riferimenti: `file:riga` si riferisce agli originali della relatrice.

---

## 1. I problemi che aveva MUDILAB

Sono tre gruppi distinti: la pipeline non parte, alcune funzioni danno un
risultato sbagliato anche quando partono, e il numero finale puo' essere
inventato senza che nulla lo segnali. Il terzo e' il piu' grave, perche' non
produce errori.

### 1.1 Bloccanti: con i file cosi' come sono la pipeline non parte

| # | Difetto | Ancoraggio |
|---|---|---|
| 1 | Il traduttore e' istanziato con `tools=[read_graph]`; con `tinyllama:latest`, indicato dalla relatrice, Ollama risponde **HTTP 400** ("does not support tools"): il modello ha la sola capability `completion` | `agents.py:44` (l'agent a `:41-53`) |
| 2 | La sezione `#CLIENTS` e' vuota, quindi `gpt5` e `small` non esistono e i tre agenti non si costruiscono | `agents.py:17` (sezione), usi a `:37`, `:43`, `:67` |
| 3 | `client.py` non e' fornito: `from client import HuggingFaceChatClient` solleva `ModuleNotFoundError` | `agents.py:8` |
| 4 | `prompt_descr` e' una **tupla** di stringhe, non una stringa: passata come istruzioni a un modello non e' testo | `agents.py:72-79` |

Per eseguire qualunque prova ho dovuto aggirare 1-3 **dall'esterno** (uno stub
`client.py` e l'iniezione dei client), senza modificare i suoi file.

### 1.2 Sostanziali: partono, ma il risultato e' sbagliato

- `eval(features)` esegue come codice Python il testo prodotto dal modello
  (`tools.py:45`): funziona finche' il modello scrive solo il dizionario, si
  rompe appena aggiunge un blocco markdown, ed espone all'esecuzione di codice
  arbitrario.
- `read_graph(path: str)` non ha valore predefinito (`tools.py:21`), quindi il
  modello **deve** inventare un percorso; `cau_inference` ce l'ha ma dentro il
  corpo (`tools.py:39-41`) e vale `C:/Users/Samsung/DOTTORATO/...`, cioe' una
  cartella di un altro computer: da qui `gum.loadBN` solleva `IOError`.
- Il ramo controfattuale e' scritto `'conterfactual'` (`tools.py:63`) e il
  classificatore puo' emettere solo `backward_reasoning`, `intervention`,
  `coherence`, `influence` (`agents.py:24`): quel ramo **non viene mai
  raggiunto**.
- `list(input_.keys()) == 2` confronta una lista con un intero, quindi e' sempre
  falso (`tools.py:94`, `:96`): nel ramo coherence viene aggiunta solo la prima
  evidenza. Con piu' di due variabili in input nessuno dei due rami assegna
  `formula` e `if formula is None` solleva `UnboundLocalError`
  (`tools.py:74-80`).
- In `funtions.py` i rami `dim == 2` e `dim == 1` usano nomi (`m`, `col_nox`,
  `n`) definiti solo in altri rami (`:127-147`): `NameError`.
- `pd.read_csv('DATI.csv')` all'import con percorso relativo alla cartella di
  avvio (`funtions.py:6`): da un'altra cartella l'import fallisce.
- Residuo di debug che scrive su stdout a ogni controfattuale
  (`funtions.py:175`).

### 1.3 Il guasto silenzioso: il numero c'e', ma non viene dal calcolo

Il terzo passo e' un agente che **deve chiamare** `cau_inference` come tool. Con
i modelli locali disponibili, quando il tool non viene chiamato la risposta
contiene comunque un numero plausibile: 0.5, 0.8, 0.866 contro un riferimento
di 0.212. Senza contare le invocazioni, un numero inventato e' indistinguibile
da uno calcolato.

Misurato: su 12 modelli fino a 8B, 5 chiamano davvero `cau_inference`, ma
**nessuno** restituisce 0.2117; tre ripetizioni su quei 5 danno **0 run validi
su 15**. Il guasto piu' frequente non e' "non chiama", e' "chiama con argomenti
inventati" (14 su 15): `read_graph` ha ricevuto come percorso la query stessa,
`"dict"`, `"data\graph.json"`, un URL di Wikipedia.

La causa e' su tre livelli indipendenti:

1. **trasporto** - Ollama espone `/api/chat` (nativa) e `/v1/chat/completions`
   (compatibile OpenAI, l'unica che il client del framework sa usare). Stessa
   richiesta, temperatura 0: `llama3.1:8b` su `/api/chat` restituisce
   `tool_calls` con `label=backward_reasoning` e il dizionario giusto; su `/v1`
   restituisce `tool_calls: null` e il JSON **dentro il testo**. Il modello sa
   chiamare: e' quell'interfaccia a non restituire la chiamata.
2. **contratto degli argomenti** - `path` passato come stringa `"None"` (vera per
   Python, quindi il valore predefinito non scatta e si cerca un file chiamato
   `None`), virgolette tipografiche `\u201C \u201D` al posto di quelle dritte,
   tool inventati (`trinomial_cdf`), etichette inventate.
3. **scelta dell'etichetta** - sotto gli 8 miliardi il classificatore sbaglia:
   `llama3.2:1b` scrive `influence`, `llama3.2:3b` scrive `coherence`, nessuno
   dei due `backward_reasoning`. Il numero che esce e' di un altro ramo.

---

## 2. La strategia seguita

Regola di fondo: **non si modifica l'originale e non si crede al modello su un
numero**. Ogni correzione e' una copia con il codice originale commentato sopra
e la correzione sotto, con una riga che dice perche'. `agents.py`, `tools.py`,
`funtions.py`, `DATI.csv` e `insurance_grafo.bif` sono intatti.

### 2.1 Correggere il contratto, non il modello

Il testo del modello non si esegue piu': si tolgono le recinzioni markdown, si
normalizzano le virgolette tipografiche, si prova `json.loads` e poi
`ast.literal_eval`; `input` e `output` devono essere due dizionari con `output`
di una sola chiave. `"None"` e `"null"` scritti come parola valgono come
percorso assente. Ogni nome di variabile e ogni valore vengono verificati contro
gli stati che il grafo ammette, e `"Not necessary"` viene scartato dall'evidenza
invece di essere passato a pyagrum come dato osservato; una cella vuota di
`DATI.csv` (che arriva come `nan`) produce un errore che dice **quale** voce
della query non va bene. L'etichetta viene normalizzata, il refuso
`conterfactual` e' accettato come alias e un'etichetta sconosciuta produce un
errore leggibile.

### 2.2 Un riferimento esterno, che nessun modello puo' inventare

`verifica_copie.py` non chiama nessun modello: carica le copie e prova ogni ramo
di `cau_inference` piu' i casi che devono fallire. La prima riga utile:

    backward_reasoning: The probability of Age is Senior given the provided
    conditions is 0.212

Il riferimento indipendente, calcolato con pyagrum sul `.bif` della relatrice,
e' **0.2117**: 0.2117 arrotondato a tre decimali e' 0.212. La formula era
corretta; non funzionavano i collegamenti. Questo e' il criterio con cui si
decide se un run vale.

### 2.3 Togliere il numero dalle mani del modello (via B)

Il numero lo calcola il codice: `run_orchestrato.py` legge etichetta e
dizionario dai due agenti, li valida, chiama `tools.cau_inference.func(...)` e
lascia all'esperto causale **solo** la spiegazione. Non sostituisce
`run_query.py`, che resta la pipeline originale: e' la variante da mettere
accanto per il confronto, ed e' una modifica al disegno della relatrice, quindi
una sua decisione. Il JSON scrive sempre etichetta e dizionario accanto al
numero, perche' a temperatura predefinita il traduttore varia (un run su tre:
`Age=Adult` -> 0.651, giusto per l'altra domanda) e due risposte diverse sono
altrimenti indistinguibili.

### 2.4 Ibrida: il modello grande decide, il piccolo spiega

Se il passo che sceglie la domanda non si puo' sbagliare, e la spiegazione costa
la maggior parte dell'energia, si possono separare: `MUDILAB_MODEL_SPIEGAZIONE`
manda solo la spiegazione su un secondo modello. Misurata, questa e' la
configurazione che tiene: stesso 0.212 a circa meta' dell'energia (sezione 4).

### 2.5 Misurare invece di dedurre: il protocollo

Tre accorgimenti, ognuno nato da un run sbagliato:

- **modelli scaricati** prima di una configurazione, e primo run **scartato**
  (`--scarta-primo-run`): il caricamento dell'8B costa ~2150 J (77,5 s a freddo
  contro 494 J a caldo) e non e' inferenza;
- **cache dei prompt**: lo stesso prompt del traduttore (1346 token) a cache
  calda ne riusa 1320 e ne elabora 26 in 1,3 s, a cache fredda ne riusa 5 e ne
  elabora 1341 in 39 s (34,5 token/s). Ricaricare un modello la svuota: senza
  scartare il primo run si misura la cache, non il modello (8B+1B: 1800,9 J
  invece di 236-259);
- **bordo di riscaldamento** fuori dalla finestra: il primo bordo costa 4-5 s
  (cache di psutil fredda) e, se sta dentro, quei secondi diventano 70-74 J
  attribuiti al run e a nessun passo.

Cosa **non** ho fatto, perche' e' una scelta sua: modificare il client perche'
parli `/api/chat`; toccare `run_query.py` (li' la temperatura resta quella del
suo ambiente).

---

## 3. Il test che stiamo facendo

E' un **caso di riferimento**, non un benchmark: serve a dire se la catena
funziona prima di misurare energia su piu' query. Passa solo se passano tutti i
passi, nello stesso run.

### 3.1 Query

    Given that the driving quality is normal, how likely is it that the age of
    the driver is senior?

### 3.2 Risposta attesa

- valore: **0.2117** calcolato con pyagrum sul `.bif`, stampato **0.212** da
  `cau_inference` (tre decimali, come lo restituisce il tool);
- testo atteso del tool: `The probability of Age is Senior given the provided
  conditions is 0.212`;
- etichetta attesa: `backward_reasoning`;
- dizionario atteso: `{"input": {"DrivQuality": "Normal"}, "output": {"Age":
  "Senior"}}`.

### 3.3 I passi, con l'input esatto e il criterio di accettazione

| passo | input esatto al modello / al codice | output atteso | criterio |
|---|---|---|---|
| 1. traduttore | `Create a dictionary following your instruction of the query:<query>` (`MUDILAB_run/run_query.py`, script mio: `:197-199`) | il dizionario qui sopra | dopo il parsing, `input` e `output` sono dizionari, `output` ha una sola chiave, i nomi esistono nel grafo e `Age=Senior` e' uno stato ammesso |
| 2. classificatore | `classify the following query using your instructions:<query>` (`MUDILAB_run/run_query.py`, script mio: `:206-208`) | `backward_reasoning` | uguaglianza esatta dopo normalizzazione; `influence`, `coherence` o un paragrafo sono **fallimento** |
| 3. `cau_inference` | `label="backward_reasoning"`, `features='{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}'`, `path=None` | `The probability of Age is Senior given the provided conditions is 0.212` | il numero estratto dal testo e' esattamente 0.212; un'eccezione e' fallimento |
| 4. spiegazione | il numero del passo 3, con etichetta e dizionario, e la regola "riporta quel numero e aggiungi la spiegazione" | prosa che cita 0.212 e nessun altro numero | se compaiono altre probabilita' o coefficienti, il run e' **non valido** anche se il numero giusto c'e' (e' successo: quattro numeri inventati accanto a un risultato corretto) |

Nella pipeline originale i passi 1 e 2 sono indipendenti (leggono entrambi la
sola query) e girano nell'ordine traduttore -> classificatore
(`FINAL.ipynb` cella 12; `MUDILAB_run/run_query.py`, script mio: `:197` e
`:206`); in via B l'ordine e' lo stesso. Il passo 3 e' quello che nella
pipeline originale e' dentro `causal_A` come invocazione di tool: li'
l'accettazione richiede **una** chiamata a `cau_inference` contata dal codice
**e** il valore 0.212, non l'una o l'altro.

### 3.4 Come si lancia

    set MUDILAB_COPIE=1
    set MUDILAB_MODEL=llama3.1:8b
    python run_orchestrato.py "Given that the driving quality is normal, how likely is it that the age of the driver is senior?" --scarta-primo-run

Per la versione ibrida si aggiunge

    set MUDILAB_MODEL_SPIEGAZIONE=llama3.2:1b

Il JSON di uscita deve avere `etichetta: backward_reasoning`, il dizionario qui
sopra e `0.212` nel campo `numero`. Con i modelli scaricati il primo run serve
solo a scaldare e non si usa.

### 3.5 Cosa questo test non dice

Non dice che la pipeline funziona sulle altre 9 query: il riferimento per quelle
sta in `ground_truth.csv`, ma su 6 delle 9 la mappatura fra la formulazione
della query e le variabili del grafo e' interpretativa (per esempio "damage to a
car" letto come `ThisCarDam` e non `Accident`) e va confermata dalla relatrice.
Non dice nemmeno che il numero e' corretto per costruzione: dice che questa
domanda, su questo grafo, da 0.212 come pyagrum.

---

## 4. Tre passaggi, energia per passaggio

### 4.1 La struttura

MUDILAB ha **tre passi**, ognuno un agente:

1. **classificatore** - decide che tipo di domanda e' (`backward_reasoning`,
   `intervention`, `coherence`, `influence`);
2. **traduttore** - scrive la domanda come dizionario `input`/`output` sulle
   variabili del grafo;
3. **esperto causale** - chiama `cau_inference` (e `read_graph`) e scrive la
   risposta con la spiegazione.

Nella pipeline originale l'ordine di esecuzione e' traduttore, classificatore,
esperto causale (`FINAL.ipynb` cella 12): i primi due leggono la sola query e
non si scambiano nulla, quindi l'ordine fra loro non cambia il risultato, ma e'
quello che la via B riproduce.

In via B il terzo passo e' diviso in due **finestre**, perche' sono due cose
diverse: la chiamata a `cau_inference` la fa il codice (millisecondi, nessun
token) e la spiegazione la scrive un modello. Quindi le finestre misurate sono
quattro - traduttore, classificatore, `cau_inference`, spiegazione - ma i passi
del disegno della relatrice restano tre. Tenerle separate e' cio' che permette
di dire **dove** va l'energia, ed e' la ragione per cui l'ibrida si puo'
progettare: il costo non e' distribuito sui tre passi, e' concentrato nel
quarto.

### 4.2 Come si misura

Contatore EMI del package CPU (`emi-counter`, finestra `exact-counter`), un
campionatore a 20 Hz acceso per tutta la durata, due bordi del contatore
attorno a ogni passo e `profile_window` fra i due; i token vengono da
`usage_details` del client. La baseline non e' calibrata (`--calibra-idle` la
calibrerebbe con tre finestre da 30 s): le cifre sono **energia del package**,
non energia attiva, e il JSON lo dichiara (`idle_provenance = uncalibrated`).
Il residuo fuori dai passi (bordi, scrittura del JSON) e' 2,7-6,2 J.

### 4.3 Energia per passo, misurata

Query della sezione 3, temperatura 0, modelli scaricati prima di ogni
configurazione, primo run scartato. Joule; fra parentesi i secondi.

| config. | traduttore | classificatore | `cau_inference` | spiegazione | totale |
|---|---|---|---|---|---|
| 8B + 8B (run 1) | 110,3 (3,81) | 22,8 (0,83) | 1,4 (0,05) | 349,6 (12,38) | **486,8** (17,3) |
| 8B + 8B (run 2) | 121,0 (4,28) | 30,8 (1,05) | 4,8 (0,10) | 376,1 (13,13) | **538,8** (19,0) |
| 8B + 1B (run 1) | 108,6 (4,11) | 21,4 (0,72) | 2,3 (0,05) | 100,7 (3,61) | **236,2** (8,7) |
| 8B + 1B (run 2) | 119,5 (4,13) | 27,1 (0,98) | 2,9 (0,05) | 103,9 (3,63) | **258,8** (9,1) |
| 8B + 3B 		  | 110,4 (4,13) | 22,3 (0,72) | 2,2 (0,05) | 149,8 (5,34) | **288,7** (10,6) |

Token: traduttore 1367, classificatore 259, spiegazione 361 (8B) / 374 (1B) /
365 (3B).

Come si leggono:

- **i primi tre passi costano uguale** nelle tre configurazioni: la scelta del
  modello della spiegazione non li tocca, ed e' la prova che le finestre sono
  separate come si voleva;
- **la spiegazione e' il 70-72% del totale** con l'8B, e scende a 101-104 J col
  1B (un fattore 3,4-3,6) scrivendo 13 token in piu'; col 3B a 149,8 J;
- **totale**: 487-539 J con l'8B, 236-259 col 1B (circa meta'), 288,7 col 3B
  (-41/-46%);
- la ripetizione della stessa configurazione da' uno scarto del **10%** in joule
  (stesso dizionario, stesso 0.212, stessi token): la ripetibilita' del testo
  non e' ripetibilita' dei joule. Le differenze sopra sono dello stesso ordine
  o piu' grandi solo nel quarto passo, ed e' li' che vanno lette; differenze di
  1-2 J fra i primi passi non sono significative a questa risoluzione.

### 4.4 Che cosa questi numeri non sono

- non sono l'energia del computer: sono il **package CPU**, e non includono GPU
  (qui assente), disco, rete;
- non sono energia **attiva**: manca la sottrazione della baseline, quindi
  contengono la potenza di riposo moltiplicata per la durata (per questo il
  run piu' lungo ha anche piu' joule "spuri");
- un campione per configurazione (due per A e B, uno per C) non basta per una
  stima: serve la campagna con ripetizioni, quella si' con l'analisi di P4.

---

## 5. Dove stanno le prove

| file | cosa dimostra |
|---|---|
| `consegna/verifica_copie.py`, `consegna/output_verifica.txt` | i rami senza modello: 0.212 e i casi che devono fallire |
| `consegna/LEGGIMI.txt` | i difetti a riga, le correzioni, la tabella della sezione 4 qui sopra |
| `consegna/SINTESI_invocazione_tool.txt` | una pagina: le due vie  |
| `MUDILAB_correzioni.zip` | il pacchetto verificabile: 35 file, tre run di esempio |
| `run_orchestrato_ctl_A3/A4_8b_20261029.json` | le due misure 8B+8B |
| `run_orchestrato_ctl_B2/B3_8b_1b_20261029.json` | le due misure 8B+1B |
| `run_orchestrato_ctl_C2_8b_3b_20261029.json` | la misura 8B+3B |
| `run_orchestrato_ctl_{A2,B,C}_*.json` | run precedenti, con i due primi passi in ordine invertito: superati da A3/B2/C2 |
| `run_orchestrato_llama31_freddo_20261029.json` | il run a freddo: 2644,5 J totali, di cui ~2150 J di caricamento (§2.5) |
| `run_orchestrato_ibrido_8b_1b_20261029.json` | il run con la cache fredda (1800,9 J) |

## 6. Punti aperti

1. Le 9 query di `ground_truth.csv` piu' le 3 controfattuali: mappature da
   confermare, poi campagna con ripetizioni e energia.
2. `Py = P(Y=y)` nel ramo controfattuale: da `DATI.csv` vale 0 su una query e
   produce un intervallo puntiforme; da dove prenderla e' una domanda per la
   relatrice.

   Nota del 31-10-2026: punto chiuso. La Py viene dalla marginale dello stesso
   giunto da cui `cobound` prende gli altri quattro termini (FIX 11 in
   `consegna/tools_corretto.py`, con il parametro `py` di `cobound` in
   `consegna/funtions_corretto.py:235`); con la Py del giunto la formula contiene la
   probabilita' vera 500 volte su 500, con quella stimata su sei righe sbaglia
   129 volte su 500 (`verifica_py.py`, parte B;
   `RISULTATI_decisioni_20261031.md` §1). Le colonne `expected_lower_file`/
   `expected_upper_file` restano come traccia del confronto.
3. `DATI.csv`: 8 celle invalide sulle 6 righe.
4. Se il client debba parlare `/api/chat` (l'8B chiamerebbe i tool) e se
   `run_query.py` debba girare a temperatura 0: due scelte sue.
