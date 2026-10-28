# Additivita' della quota di tempo CPU - run del 25-10-2026

Due run di `experiment_additivity.py` sulla stessa macchina (i9-13900HK, 14 core
fisici / 20 logici, `llama3.2:3b`, canale `emi-counter`, 5 blocchi da A-B-C in
ordine casuale con seme 20261025). I CSV e i JSON citati sono nella stessa
directory.

Questo file dice cosa i due run provano e cosa no. Non c'e' una banda
preregistrata per questo esperimento: i numeri si riportano, non si giudicano.

## Run 1 (18:49, `additivity_20261025_185707`, temperatura 0,2): pilota

Il run serviva a provare il cablaggio e ha mostrato due difetti del disegno.

1. **Una richiesta non e' lo stesso lavoro.** Con temperatura 0,2 il modello si
   ferma a lunghezze diverse: A ha generato 128, 105, 66, 153, 63 token, C 136,
   160, 160, 151, 160. Il confronto diretto E_worker(C) contro E_active(A)
   (160,801 J contro 148,483 J, rapporto 1,083) misurava quindi anche una
   differenza di lavoro. Normalizzato per token: E_worker 1,044 J/token in A e
   1,049 J/token in C.
2. **La baseline si e' mossa dentro il run.** P_pre = 8,799 W
   [8,799; 8,643; 9,860] e P_post = 17,470 W [17,470; 19,241; 14,156]. Il run e'
   partito subito dopo la chiusura del browser, con la macchina ancora in
   assestamento; il POST e' stato letto a caldo, subito dopo l'ultima prova.
   Con una baseline che varia di quasi 9 W, l'energia attiva delle prove non e'
   confrontabile e il run non si usa.

Il difetto 1 e' stato corretto nell'harness (avviso su temperatura > 0, token
per prova, confronto per token); il difetto 2 e' ambientale e si e' risolto da
solo nel run 2, a macchina ferma.

## Run 2 (19:03, `additivity_20261025_191048`, temperatura 0): il run di riferimento

A e C hanno generato 160 token in tutte e cinque le prove (il tetto
`num_predict`), quindi fanno lo stesso lavoro del modello.

Baseline stabile: P_pre = 5,198 W [5,571; 5,198; 5,131], P_post = 5,803 W
[5,736; 6,197; 5,803]. Si applica P_pre (P1.3), il POST resta diagnostico.

| condizione | dt [s] | E_attiva [J] | d_ollama [s] | d_busy [s] | share | E_worker [J] |
|---|---|---|---|---|---|---|
| A, Ollama da solo | 10,059 (min 9,974 max 10,153) | 232,62 (229,07-236,82) | 99,76 (98,48-101,08) | 108,81 (106,77-110,86) | 0,917 (0,898-0,930) | 213,30 (207,51-218,48) |
| B, solo carico CPU | 20,000 | 307,45 (298,41-319,25) | 0,03 | 30,23 (28,41-32,56) | 0,001 | 0,32 |
| C, Ollama + carico | 9,983 (9,831-10,097) | 236,11 (231,00-242,85) | 99,28 (97,66-100,36) | 119,28 (116,97-121,11) | 0,832 (0,829-0,839) | 196,54 (192,37-201,76) |

Intervalli = [min, max] osservati su 5 blocchi; fra parentesi il semi-range non
si usa come sigma (P4.12).

Confronti stampati dall'harness:

* E_worker(C) contro E_active(A): 196,539 J contro 232,623 J, differenza
  -36,084 J, rapporto 0,845; differenze appaiate per blocco -36,084 J
  (min -41,086, max -32,897).
* E_active(C) contro E_active(A) + E_active(B) riportata alla durata della C
  (fattore dt_C/dt_B = 0,499): 236,114 J contro 386,091 J, differenza
  -149,977 J, rapporto 0,612; appaiate -150,014 J (min -154,386, max -144,753).
* Per token: E_attiva 1,454 J/token in A e 1,476 J/token in C; E_worker
  1,333 J/token in A e 1,228 J/token in C.
* Righe dichiarate: 0 con `active_valid=False`, 0 con
  `worker_exit_in_window`, 0 con anomalia di share. 15 righe su 15 hanno
  `package_window_source = exact-counter`.

Cosa mostrano i numeri, senza aggiungere un criterio:

* A lavoro identico (160 token), il carico estraneo **non cambia il lavoro del
  modello**: d_ollama passa da 99,76 a 99,28 s e la durata da 10,059 a 9,983 s.
* Lo stesso carico estraneo, da solo (B), costa 307,45 J in 20 s = 15,4 W sopra
  la baseline; dentro C aggiunge 236,11 - 232,62 = **+3,5 J in circa 10 s**,
  cioe' 0,35 W. La somma delle parti sovrastima l'insieme di un fattore 1/0,612.
* La quota scende da 0,917 a 0,832 perche' il denominatore cresce (+1,05 core
  medi) mentre il numeratore resta fermo: e' il comportamento del modello a
  quota, che ripartisce e non somma. E_worker(C) risulta quindi il 15,5% sotto
  E_active(A) pur a lavoro e energia attiva complessiva uguali.

## Limite che invalida il test a piu' core: il carico B non e' quello richiesto

Il run 2 e' stato lanciato con `--n-procs 6`, ma i sei busy-loop hanno
consegnato **circa un core**, non sei: `d_busy` in B e' 30,23 s su 20 s di
finestra = 1,51 core medi, di cui circa 0,5 sono il fondo della macchina. La
misura diretta dei `cpu_times` dei sei processi conferma:

* 1 processo: 7,94 s di CPU in 8 s (0,99 core);
* 2 processi: 3,61 + 4,00 = 7,61 s (0,95 core);
* 6 processi: somma 7,76-7,86 s (0,97-0,98 core).

### I carichi sono processi veri, non thread

Verificato nel codice e a runtime: `_start_busy` crea `ctx.Process` con
contesto `spawn` (una `multiprocessing` spawn per loop, argomenti
`(stop,)`), e ogni processo legge il proprio `cpu_times`. A runtime, per
N = 1, 2, 3, 6, 10, i PID distinti sono sempre N e ogni PID ha il suo
contributo. Una variante a thread avrebbe mostrato N nel conteggio dello
script e **un solo** core di CPU reale: e' l'altra spiegazione, ed e' esclusa
dai PID distinti con `cpu_times` separati.

### Curva dei core consegnati, N = 1..10

Sonda dedicata (stessa struttura di `_start_busy`: N processi, lettura di
`cpu_times` di tutti, finestra di 3 s), due esecuzioni: dentro questa sessione
e **fuori dall'albero** di questa sessione (processo lanciato via WMI
`Win32_Process.Create`, quindi figlio di `WmiPrvSE`, non nostro discendente):

| N | PID distinti | core, in sessione | core, fuori albero (WMI) |
|---|---|---|---|
| 1 | 1 | 0,98 | 0,96 |
| 2 | 2 | 0,88 | 0,93 |
| 3 | 3 | 0,97 | 0,92 |
| 6 | 6 | 1,03 | 1,02 |
| 10 | 10 | 1,18 | 1,25 |

Il totale resta **circa un core a ogni N**, anche fuori dal nostro albero.
Una finestra di 2 s puo' mostrare un burst sopra il core (1,9 core con 6
processi): a 3 s il valore si assesta. L'affinita' e' piena (0-19), la
priorita' normale (32), `IsProcessInJob` = False e la query del rate di CPU
sul job corrente fallisce con accesso negato.

Lettura corretta dei tre fatti insieme:

* il tetto **non e' dell'harness** (processi veri, PID distinti, nessun
  thread, nessuna somma di tempi sbagliata);
* il tetto **non e' confinato al gruppo di processi di questa sessione**
  (la sonda via WMI, fuori dall'albero, consegna gli stessi ~1 core);
* il tetto **non e' della macchina**: Ollama, che non e' figlio di questa
  sessione, usa ~9,9 core (`d_ollama` 99,3 s su 10 s).

Resta un limite dell'ambiente in cui questa sessione esegue i processi che
avvia; il meccanismo non e' identificato. L'ipotesi precedente ("limite del
gruppo di processi della sessione") e' quindi **smentita** dalla prova fuori
albero, e il test a sei core **non e' stato eseguito**.

### Cosa dichiara ora l'harness

Ogni prova B/C porta quattro campi nuovi nel CSV e nel JSON:
`busy_probe_cores` (core totali misurati dalla sonda prima della finestra),
`busy_probe_pids` (PID distinti fra i loop), `busy_pids_cores` (contributo
per PID) e `busy_cores_window` (`d_busy/dt` **dentro** la finestra, che
include il fondo della macchina e quindi non coincide con la sonda).
Il run rifiuta il carico se i loop consumano meno della meta' dell'atteso:
in questo ambiente `--n-procs 6` e `--n-procs 10` vengono rifiutati, e con
`--n-procs-list 3,6,10` il run si ferma al primo livello rifiutato.

Conseguenza: l'additivita' qui sopra e' misurata **a un core di carico estraneo
(7% della macchina)**, non a sei. La tabella per livello introdotta con
`--n-procs-list` esiste ed e' provata su righe sintetiche, ma i livelli 3, 6 e
10 **non sono stati misurati qui**: il test va lanciato da un terminale
normale, fuori da questo ambiente.

## Cosa questo esperimento non dimostra

* Non arbitra la scala assoluta dell'energia: e' lo stesso contatore EMI
  (`MSR_PKG_ENERGY_STATUS`), nessun wattmetro AC/DC.
* Non misura l'energia per processo: `E_worker` resta una **stima di
  attribuzione** (quota del tempo CPU busy), non una lettura per processo.
* Non stabilisce come si comporta la quota a carichi alti: il carico B qui e'
  un core. La sub-additivita' osservata vale a quel livello.
* Qoder non e' stato chiuso (ospita questa sessione): contribuisce al fondo e al
  denominatore in tutte le condizioni. Browser (Brave) e HWiNFO erano chiusi.
