# Report: colli di bottiglia e opportunità di refactoring (MUDILAB)

## Ambito
Analisi statica di `agents.py`, `funtions.py`, `tools.py` (3 file Python, ~400 righe). Focus su inefficienze, I/O, loop costosi e opportunità di riduzione del consumo energetico per inferenza.

## Principali bottleneck

### 1. I/O e import pesanti al caricamento del modulo (`funtions.py`, `tools.py`)
- `dati = pd.read_csv('DATI.csv')` eseguito a import-time in `funtions.py`, anche se `names`/`surnames` non sono usati.
- `agents.py` importa `transformers`, `torch`, `pyro`, `pyagrum` a livello di modulo anche quando non necessari; costo di import elevato e memoria residente.
- `tools.py` importa `dice_ml`, `sklearn`, `torch` non usati nel flusso mostrato.

Suggerimento: import lazy (dentro le funzioni) e rimozione degli import inutili; caricare `DATI.csv` solo quando serve.

### 2. Complessità algoritmica in `g_bin` / `complex_prob` (`funtions.py`)
- `g_bin` ricostruisce la rete e ricalcola CPT con cicli annidati fino a 4 livelli; `complex_prob` viene richiamata dentro i loop, ricalcolando posteriori e filtrando il DataFrame ad ogni iterazione.
- `cobound` chiama `g_bin` due volte e poi `complex_prob` indirettamente; costo O(n^4) su variabili con molti stati.

Suggerimento: pre-calcolare i posteriori una sola volta per combinazione di evidenze; vettorizzare con pandas/numpy; evitare ricalcolo di `ie.posterior(x)` dentro i loop.

### 3. Concatenazione di stringhe in loop (`tools.py`, `funtions.py`)
- `lista = lista + ...`, `arc = arc + ...` in `read_graph` e nel ramo `influence`: complessità O(n²) per la costruzione della stringa.
- `pulisci_output` fa più `replace` sequenziali su stringhe grandi.

Suggerimento: usare `"".join(...)` su generatori/list comprehension.

### 4. `eval(features)` in `cau_inference` (`tools.py`)
- Uso di `eval` su input non fidato: rischio di sicurezza e overhead di parsing. Non è un bottleneck energetico diretto ma blocca ottimizzazioni (no caching, no validazione).

Suggerimento: sostituire con `json.loads` e validazione dello schema.

### 5. Copie inutili e mutazione di DataFrame (`funtions.py`)
- `bind = data[[y,x]]` poi `bind[x] = ...` (SettingWithCopyWarning, copia implicita).
- `copyx`/`copyy` liste copiate e modificate; `g_bin` copia l'intera BayesNet.

Suggerimento: usare `.copy()` esplicito o operare su viste; evitare copie profonde quando non necessarie.

### 6. Duplicazione di `node_descr` (`funtions.py`)
- `node_descr = nodes_descr = {...}`: alias inutile, doppio riferimento allo stesso dict.

### 7. `web_search` (`tools.py`)
- `TavilyClient.search(...)` chiamato come metodo di classe senza istanza; probabilmente errore runtime. Anche se funzionasse, nessun caching delle query.

Suggerimento: istanziare il client una volta e aggiungere cache (functools.lru_cache) per query ripetute.

### 8. Mancanza di caching per inferenza
- `cau_inference` ricarica il grafo (`gum.loadBN`) e i dati ad ogni chiamata; nessun memoization.

Suggerimento: cache del grafo caricato e dei risultati di inferenza per input identici.

## Priorità di intervento (impatto energetico)
1. Rimuovere import non usati e I/O a import-time (impatto immediato su startup).
2. Vettorizzare `complex_prob` e pre-calcolare posteriori (impatto maggiore su runtime).
3. Sostituire concatenazioni stringa con `join`.
4. Aggiungere caching del grafo e dei risultati.
5. Sostituire `eval` con parsing sicuro.

## Note
Nessuna modifica applicata: questo report è solo analisi. I test esistenti (se presenti) vanno eseguiti dopo ogni refactoring.
