# Due punti aperti, chiusi con una misura

31 ottobre 2026. Misure fatte su questa macchina, con pyagrum 3.2.1 e Ollama
locale. Ogni numero qui sotto si rigenera con lo script indicato accanto, senza
modificare nessuno dei suoi file.

## Cosa e' stato deciso

1. **Py = P(Y=y) negli estremi controfattuali viene dalla marginale del grafo**,
   non da DATI.csv. Non e' una preferenza: su 500 modelli con accoppiamento noto
   la formula contiene la probabilita' vera 500 volte su 500 con la Py del
   giunto, e sbaglia 129 volte su 500 con una Py stimata su sei righe.
2. **La quinta etichetta (`counterfactual`) si adotta**, perche' senza di essa
   nessuna delle tre query controfattuali puo' essere instradata: il ramo esiste
   nel codice ma il vocabolario del classificatore non lo nomina.

Il punto che resta aperto non e' piu' nel codice: **con tinyllama:latest il
classificatore non emette alcuna etichetta**, quindi la pipeline non parte con
il modello che mi ha indicato. Le misure sono al punto 3.

Resta la scelta del percorso: modello che chiama i tool (a) oppure codice che
chiama `cau_inference` (b). Le due varianti sono state misurate sullo stesso
run, con lo stesso processo e la stessa finestra energetica: i numeri sono al
punto 4.

---

## 1. Da dove viene Py

`cobound` (`MUDILAB/funtions.py:156-195`) calcola gli estremi di Tian e Pearl.
Quattro termini escono dal grafo; l'unico che la funzione prende da fuori e' Py
(`:178-179`, `ny/data.shape[0]`). Con i suoi file quel numero viene da DATI.csv:
6 righe, 20 colonne.

### 1.1 Le due fonti non sono la stessa popolazione (`verifica_py.py`, parte A)

| | |
|---|---|
| nodi del grafo / colonne del file | 27 / 20 |
| variabili comuni | 17 |
| variabili del grafo assenti dal file | 10 |
| distanza massima (variazione totale) | **0,804** su `Accident` |

Le dieci assenti: ThisCarDam, MakeModel, DrivQuality, Theft, CarValue, AntiTheft,
PropCost, OtherCarCost, MedCost, Cushioning. Due dei tre bersagli
controfattuali, **DrivQuality** e **Theft**, sono fra queste: con Py dal file
quelle due query non si calcolano affatto.

Sulle 17 comuni la distanza non e' rumore da campionamento: `Accident=None` vale
0,7159 nel grafo e 0,0000 nel file, uno stato che nelle sei righe non compare mai
(0 su 6). Non e' lo stesso campione.

### 1.2 Su modelli con accoppiamento noto la formula regge solo con la Py esatta (`verifica_py.py`, parte B)

500 modelli causali artificiali, 40 blocchi dell'esogena uniforme, seed
20261031. Per ognuno la probabilita' vera di necessita' e sufficienza
(PNS = P(Y(1)=1, Y(0)=0)) si calcola per enumerazione; l'intervallo deve
contenerla.

| Py usata negli estremi | PNS fuori dall'intervallo | intervalli rovesciati (low > upper) |
|---|---|---|
| marginale del giunto (esatta) | **0/500** | 0/500 |
| stimata su 6 righe campionate dallo stesso modello | **129/500 (25,8%)** | **23/500 (4,6%)** |
| × 1,446 (il fattore reale di CF2) | **47/500 (9,4%)** | 0/500 |

L'ampiezza mediana dell'intervallo esatto e' 0,300, quindi i fallimenti non
vengono da intervalli stretti: cadono fuori anche quando c'e' spazio.

La terza riga e' l'errore che si commetterebbe davvero su CF2, dove la frequenza
nel file e' 1/6 = 0,1667 contro 0,1153 del grafo.

### 1.3 Conseguenza applicata (FIX 11 in `tools_corretto.py`)

`cau_inference` calcola Py dalla marginale del grafo e la passa a `cobound`. Da
li' i tre riferimenti si calcolano tutti e coincidono con `ground_truth.csv`:

| | risposta di `cau_inference` |
|---|---|
| CF1 `RiskAversion=Cautious -> DrivQuality=Excellent` | `between 0.0827 and 0.2396` |
| CF2 `Age=Senior -> Accident=Severe` | `between 0 and 0.074` |
| CF3 `SocioEcon=Wealthy -> Theft=True` | `between 0 and 0.0` |

Il limite inferiore si stampa `0` e non `0.0` perche' `cobound` fa `max(0, ...)`
partendo dall'intero: e' il testo, non il valore.

Due note di lettura:

- **CF1**: l'estremo inferiore e' retto dal termine `PYx - PYnox = 0,0827`, che
  non contiene Py. Quel valore non dipende da come si stima Py.
- **CF3**: `P(Theft=True | do(SocioEcon=Wealthy))` vale 4,87e-05. L'estremo
  superiore e' corretto, ma e' piu' piccolo dell'ultimo decimale che `cobound`
  stampa (round a 4 decimali), quindi `between 0 and 0.0` si legge come "nessun
  effetto" e non lo e'. **Il formato resta il suo**: se preferisce piu'
  decimali, o un formato che dichiari la risoluzione, e' una riga da cambiare e
  la cambio.

Il parametro `py` resta in `cobound`, quindi la variante a file si puo' ancora
calcolare e serve da confronto: per CF2 da' `between 0.0404 and 0.074`; per CF1
e CF3 solleva `KeyError` perche' la colonna manca. Le colonne
`expected_lower_file`/`expected_upper_file` in `ground_truth.csv` restano come
traccia.

### 1.4 Accettazione (`verifica_ground_truth.py`)

Le 12 righe di `ground_truth.csv` eseguite con l'etichetta che il classificatore
dovrebbe emettere: **12/12 tornano** (tolleranza 5e-4; 5e-3 solo sul ramo
coherence, che stampa 2 decimali per costruzione). Il file e' verde anche sulle
tre controfattuali, che prima non partivano.

Nota (stesso giorno). Il ramo coherence e' stato portato a quattro decimali
(FIX 12 in `tools_corretto.py`): la tolleranza e' ora 5e-4 su tutte le righe e
le tre righe coherence riportano 0.0670, 0.0397, 0.1614 invece di due decimali.
La misura 12/12 resta.

---

## 2. La quinta etichetta

`tools.py:63` confronta l'etichetta con `'conterfactual'`; `agents.py:24`
ammette solo `backward_reasoning`, `intervention`, `coherence`, `influence`.
Quel ramo non e' raggiungibile, e le tre query controfattuali del notebook non
trovano risposta. In `agents_corretto.py` l'etichetta c'e' gia', con un criterio
e la richiesta di una sola parola minuscola.

La domanda non era "si puo' aggiungere" ma "sposta le altre nove". Misura:
`verifica_classificatore.py`, temperatura 0, tre ripetizioni, stessi 12 testi di
prompt sullo stesso modello, prima con 4 e poi con 5 etichette. Conta come
etichetta solo una risposta composta dalla sola parola ammessa (a meno di spazi,
virgolette e punti), perche' `cau_inference` confronta per uguaglianza
(`tools.py:51`): una parola citata dentro una frase non instrada nulla.

| modello | endpoint | CF come `counterfactual` | altre che cambiano | altre senza etichetta |
|---|---|---|---|---|
| tinyllama:latest | /v1 | 0/3 | 0 | 9/9 |
| tinyllama:latest | /api/chat | 0/3 | 0 | 9/9 |
| llama3.2:3b-instruct-q4_K_M | /v1 | **2/3** (CF1, CF3) | 1 (CP1) | 0 |
| qwen2.5:1.5b | /v1 | 0/3 | 1 (IN1) | 0 |

Lettura onesta di questa tabella:

- **llama3.2:3b**: con 4 etichette CF1 e CF3 andavano su `intervention`, con 5 su
  `counterfactual`. CF2 resta su `influence` anche con la quinta: il criterio
  scritto non copre quella formulazione, e va rivisto. Il "cambio" su CP1 non e'
  causato dalla quinta etichetta: con 4 etichette quella query era gia' instabile
  (`influence` x2, `coherence` x1), con 5 e' `coherence` x3.
- **qwen2.5:1.5b**: nessuna delle tre arriva a `counterfactual`; CF1 e CF3
  passano da `backward_reasoning` a `intervention`, CF2 resta `intervention`, e
  IN1 passa da `backward_reasoning` a `coherence`. La quinta etichetta non basta
  su un modello di questa taglia, e non e' neutra sulle altre.
- **tinyllama**: nessuna risposta e' un'etichetta (punto 3), quindi le nove
  non controfattuali non sono confrontabili. Non e' "zero spostamenti": e' un
  confronto che non si puo' fare.

Conclusione: la quinta etichetta serve, e non rompe in modo sistematico le altre
nove: cambia una query su nove sui due modelli che classificano, e su llama3.2
quella query era gia' instabile prima. Non basta pero' da sola: CF2 resta fuori
su entrambi, e su 1,5 miliardi di parametri non cambia nulla. Le query colpite
sono nominate qui sopra, non lasciate implicite.

---

## 3. Il blocco che resta: tinyllama non classifica

tinyllama:latest, 12 query su 12, **zero etichette**, su `/v1` e su `/api/chat`,
a 128 e a 400 token, con il prompt a 4 e a 5 etichette. Non e' un troncamento:
la risposta e' letta intera. In 10 casi su 12 il testo non contiene nemmeno una
parola ammessa; negli altri 2 la cita dentro una frase ("the criterion for
assigning the label ... is backward_reasoning"), che per il confronto per
uguaglianza di `tools.py:51` non instrada nulla. Il modello risponde alla
domanda invece di classificarla ("If a person's risk aversion were Cautious
rather than Psy...").
Il prompt di sistema arriva: il template di tinyllama ha il posto per
`{{ .System }}` (`ollama show tinyllama:latest`). Sull'altro lato il traduttore
non e' nemmeno istanziabile, perche' `agents.py:44` gli dichiara un tool e
Ollama risponde 400 "tinyllama:latest does not support tools".

Poiche' `run_orchestrato.py` e `cau_inference` instradano sull'etichetta, con
questo modello **nessuna delle 12 query arriva a un ramo**. Le tre strade sono
quelle del punto 4 di LEGGIMI (modello che segue il protocollo; togliere il
modello dal percorso di instradamento; una soluzione sua) e nessuna e' una
modifica che faccio senza il suo assenso.

---

## 4. (a) o (b): la stessa query, lo stesso processo

`confronto_a_b.py` esegue le due varianti nello stesso processo, sulle stesse
copie corrette, con la stessa misura EMI (`emi-counter`, finestra
`exact-counter`) e con la baseline calibrata su tre finestre da 30 s. I due
percorsi si alternano (A B A B A B) per distribuire la deriva della macchina, e
il primo run di ogni variante e' di riscaldamento e non entra nella tabella:
paga il caricamento del modello e la cache fredda dei prompt. La query e'
quella di riferimento (`DrivQuality=Normal -> Age=Senior`, valore atteso 0,212).

Un run e' valido se la risposta e' quella giusta: per (a) il tool deve essere
stato chiamato senza eccezioni e il testo finale deve contenere 0,212; per (b)
l'etichetta deve essere `backward_reasoning` e il numero deve essere 0,212
(tolleranza 5e-4).

| modello (baseline) | variante | s (mediana) | J package (mediana) | J attiva (mediana) | validi |
|---|---|---|---|---|---|
| llama3.2:3b (13,993 W) | (a) modello chiama i tool | 39,28 | 1178,0 | 644,4 | **0/3** |
| | (b) codice chiama il tool | 11,12 | 294,5 | 138,5 | **0/3** |
| llama3.1:8b (18,036 W) | (a) modello chiama i tool | 73,50 | 2306,6 | 980,5 | **0/3** |
| | (b) codice chiama il tool | 20,51 | 588,9 | 218,3 | **3/3** |

Le terne complete: sul 3B (a) 48,66 / 38,09 / 39,28 s, (b) 15,33 / 9,85 /
11,12 s; sull'8B (a) 73,50 / 74,69 / 68,72 s, (b) 27,70 / 20,51 / 19,62 s.
Rispetto a (b), (a) costa **circa 4 volte** in J package (4,00 sul 3B, 3,92
sull'8B) e **circa 3,5 volte** in tempo (3,53 e 3,58).

### 4.1 Come falliscono le due varianti

- **3B, (a)**: il modello chiama davvero `read_graph`, ma sbaglia l'argomento:
  passa un percorso CSV (`data\driving-quality.csv`) o addirittura il
  dizionario delle evidenze (`{'DrivQuality': 'Normal', 'Age': 'Senior'}`).
  `read_graph` solleva `FileNotFoundError`, il framework ritenta fino a tre
  errori consecutivi, `tool_ok` e' falso e in un run il testo finale contiene
  `1.0` come probabilita'. In un run chiama anche `cau_inference`, con lo stesso
  percorso CSV, e fallisce ugualmente: nessun run arriva a una chiamata valida.
- **3B, (b)**: il percorso funziona, ma il classificatore sceglie `coherence`;
  `cau_inference` risponde sul ramo coherence ("Evidences are NOT strongly
  compatible..."), che e' una risposta legittima a un'altra domanda. Il
  fallimento e' a monte, nell'etichetta, non nei tool.
- **8B, (a)**: il modello non completa nemmeno una chiamata con argomenti
  validi: `read_graph` riceve `data.csv` o il testo della query, `cau_inference`
  riceve `features` come stringa malformata (`'{'`). Tre errori consecutivi e
  nessun numero.
- **8B, (b)**: etichetta `backward_reasoning` e risposta "The probability of Age
  is Senior given the provided conditions is 0.212" in tutti e tre i run.

### 4.2 Cosa dicono e cosa non dicono

Il confronto energetico qui sopra **non e' il costo di due strade per la stessa
risposta**: (a) non produce la risposta. I suoi joule sono il costo di un run
senza risultato, quindi il rapporto ~4x va letto come "quanto costa il
fallimento del percorso pilotato dal modello", non come "quanto e' piu'
efficiente (b) a parita' di risultato". Con i due modelli disponibili non esiste
un run (a) valido da mettere a confronto.

Due asimmetrie restano dichiarate e non corrette:

- **temperatura**: (b) gira a 0 (`run_orchestrato.OPZIONI`), (a) al valore
  predefinito di Ollama, perche' `run_query.py` non passa opzioni alla pipeline
  originale. E' il comportamento della pipeline, non una scelta della misura;
  toglierla richiederebbe di modificare gli agenti, che non tocco.
- **baseline**: le due sessioni hanno baseline diverse (13,993 W e 18,036 W,
  misurate a distanza di dodici minuti). Dentro una sessione A e B condividono
  la stessa baseline, quindi il confronto A/B di una riga e' omogeneo; fra i due
  modelli si confronta il **J package**, non l'energia attiva.

I secondi assoluti di questa tabella sono piu' alti dei run (b) eseguiti uno
dietro l'altro (3B: 7,2 s e 208 J; 8B: 17,3-19,0 s e 487-539 J). L'alternanza
serve a togliere la deriva della macchina, ma a ogni cambio di variante il
prompt cache di Ollama riparte in parte, verosimilmente perche' i prompt delle
due varianti non stanno tutti in cache. Il confronto A/B resta dentro lo stesso
regime, ma il regime non e' neutro: (a) porta anche gli schemi dei tool nei
prompt, quindi la ri-prefill che paga a ogni cambio e' verosimilmente piu'
grande. Il rapporto ~4x e' misurato qui, non e' un limite inferiore per (a), e
per un disegno a blocchi va rimisurato.

Con tinyllama la prova non e' stata fatta: il classificatore non emette
etichette (punto 3) e il traduttore dell'originale non e' istanziabile, quindi
entrambe le varianti si fermerebbero prima dei tool e la misura sarebbe di due
fallimenti diversi, non di due percorsi.

I dati grezzi sono in `confronto_a_b_20261031_1658.json` (3B) e
`confronto_a_b_20261031_1710.json` (8B), con secondi, joule, argomenti dei tool,
testo delle eccezioni e testo finale di ogni run. `--rivaluta` ricalcola il
verdetto dai campi grezzi senza rifare i run.

---

## 5. Cosa cambia nella campagna

- Le 12 query si dividono in **9 non controfattuali + 3 controfattuali**. Il
  blocco delle 9 e' misurabile con qualunque modello che emetta un'etichetta; le
  3 richiedono la quinta etichetta e un criterio che copra anche CF2.
- Il disegno resta 3 configurazioni x 3 ripetizioni: **81 esecuzioni** sulle 9
  query, piu' le 27 sulle tre controfattuali. Caricamento dei modelli e cache
  fredda dei prompt restano fuori dalla finestra (`--riscalda-modelli`,
  `--scarta-primo-run`).
- Nessun numero di energia cambia per effetto di queste due decisioni: cambiano
  **quali** query producono un risultato, non come si misura.

---

## 6. Come si rigenera

Dalla cartella scompattata, con il python dell'ambiente che ha pyagrum:

```
python verifica_py.py
python verifica_ground_truth.py
python verifica_conterfactual.py --gruppo corretto
python verifica_classificatore.py --modello tinyllama:latest --endpoint v1
python verifica_classificatore.py --modello tinyllama:latest --endpoint chat
python verifica_classificatore.py --modello llama3.2:3b-instruct-q4_K_M
python verifica_classificatore.py --modello qwen2.5:1.5b
python confronto_a_b.py --modello llama3.2:3b
python confronto_a_b.py --modello llama3.1:8b
```

Tutti escono 0 se il risultato e' quello atteso, 1 altrimenti. Gli output gia'
prodotti su questa macchina sono in `output_classificatore_*.txt`,
`output_verifica.txt`, `confronto_riepilogo_20261031.txt` e nei due JSON del
confronto. `verifica_classificatore.py` esce 1 anche qui: e' il risultato, non un
guasto dello script — con tinyllama l'attesa non e' soddisfatta. `confronto_a_b.py`
esce 1 solo se una finestra non ha prodotto energia: il confronto non ha un
criterio di superamento. `verifica_classificatore.py` esce 1 anche qui: e' il
risultato, non un guasto dello script — con tinyllama l'attesa non e' soddisfatta.
