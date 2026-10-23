# Costo dell'osservatore: GUI LibreHardwareMonitor aperta durante una misura

**Data**: 2026-10-23, finestre alle 16:48:32, 16:51:21, 16:53:53
**Script**: `observer_cost_probe.py` (nuovo, committato qui insieme ai dati)
**Dati**: `observer_cost_gui_open_20261023_164832.{csv,json}`,
`observer_cost_gui_closed_20261023_165121.{csv,json}`,
`observer_cost_gui_open2_20261023_165353.{csv,json}`

## Domanda

I rilanci post-fix di oggi (v3 15:36, trace 15:46, v2 16:04) sono stati eseguiti
**con la GUI di LibreHardwareMonitor aperta** (PID 14828, avviato 14:06:05),
mentre `smoke_test_readpath.py:17` mette fra i requisiti "LHM chiuso altrove
(un solo `Computer()` aperto alla volta)". Serve sapere di quanto quel
vincolo violato sposta il livello assoluto, e se spiega anche l'intervallo dei
campioni che cambia fra i run (0,3025 s contro 0,3272 s).

## Metodo

Idle puro: nessun Ollama invocato, nessun burner, niente da toccare. Tre
finestre da 90 s in disegno **A-B-A** (aperta / chiusa / riaperta), ciascuna
con:

- **EMI** sul campo PKG: `Δcontatore × 3,6e-9 / Δtimestamp_100ns` sulla
  finestra intera. EMI e' esterno alla GUI, legge il package intero e quindi
  include il consumo della GUI: la differenza fra condizioni e' il costo
  cercato;
- **il nostro thread power-integration**: media dei campioni e **mediana
  dell'intervallo reale** fra campioni consecutive;
- il **tempo di CPU del processo GUI** (`GetProcessTimes`, user+kernel) entro
  la finestra, come prova di meccanismo.

Chiusura/riapertura della GUI fatte dall'operatore (il secondo avviamento e'
PID 31464, 16:51:45); lo script **non** tocca la GUI, la misura soltanto.

## Numeri

| condizione | EMI PKG [W] | LHM PI media [W] | LHM−EMI [W] | intervallo PI mediano [s] | CPU GUI nella finestra |
|---|---|---|---|---|---|
| A `gui_open` (PID 14828) | **11,9197** | 12,0742 | +0,1253 | 0,2803 | 3,125 s / 89,84 s = 3,48% di un core |
| B `gui_closed` | **11,0694** | 11,1947 | +0,1140 | 0,2803 | — |
| C `gui_open2` (PID 31464) | **11,2914** | 11,4054 | +0,1545 | 0,2800 | 2,766 s / 89,84 s = 3,08% di un core |

Differenziali:

```
A - B = +0,850 W (EMI)   +0,880 W (LHM)
C - B = +0,222 W (EMI)   +0,211 W (LHM)
A - C = +0,628 W (EMI)   <-- stessa condizione, due istanze diverse
```

Campione per finestra: 357 / 358 / 357 righe, zero campioni Power vuoti. Il
livello all'interno dei 90 s non e' piatto (min ~7,1-7,8 W, mediana
10,74 / 10,99 / 11,64 W, max ~26 W): il PC ha housekeeping di Windows attivo, e
l'ordine delle mediane riproduce quello delle medie.

## Cosa si puo' dire

1. **L'intervallo di campionamento non e' colpa dell'osservatore.** 0,2803 /
   0,2803 / 0,2800 s nelle tre condizioni: identico. La risoluzione intrinseca
   del thread power-integration a riposo vale quindi **~0,28 s** (dichiarati
   0,05 s), e i valori 0,3025 / 0,3272 s dei protocolli sono lo stesso thread
   **sotto carico Ollama**, non l'effetto di una seconda istanza LHM. Questa e'
   una risposta netta alla domanda posta.
2. **Il costo dell'osservatore esiste, ma questo disegno non lo arbitra.**
   La riapertura nella stessa condizione (A contro C) differisce di 0,63 W, piu'
   del segnale C−B (0,22 W): il drift della baseline e' dello stesso ordine del
   disturbo che cerchiamo. Cio' che si puo' dichiarare e' un **intervallo**:
   la GUI apre un contributo fra ~0,2 e ~0,9 W su un idle di ~11 W (2–8%), e la
   stima puntuale onesta e' "inferiore a 1 W, non distinguibile dal drift".
   E' lo stesso confondente che gia' limita i J/token (r = −0,982 con la
   baseline), quindi la leva corretta resta il protocollo v4, non la caccia
   all'osservatore.
3. **Le due sorgenti coincidono anche su incrementi di un decimo di watt.**
   I differenziali calcolati da EMI e dal nostro thread (0,850 contro 0,880;
   0,222 contro 0,211) concordano entro 0,03 W, e l'offset LHM−EMI resta
   +0,114/+0,125/+0,155 W su tre condizioni diverse. E' la conferma piu' fine
   ottenuta finora dell'accordo a finestra identica: prima si erano confrontate
   fasi da 16-38 W, qui si confronta un incremento di 0,2 W.
4. **Meccanismo non stabilito.** Il tempo di CPU della GUI nella finestra vale
   3,1-3,5% di un core: e' una prova che la GUI lavora, ma non basta a
   distinguere fra (a) il costo del suo calcolo e (b) la perdita di profondita'
   di idle (ogni aggiornamento legge 5 MSR via Ring0, `IntelCpu.cs:685-698`).
   Con i dati di qui le due vie non sono separabili: nessuna attribuzione.

## Conseguenze operative

- Gli esperimenti si lanciano **con la GUI chiusa**; la condizione va scritta
  nel protocollo e riportata nel `"stato della macchina"` del verbale, come
  gia' fatto per HWiNFO (chiuso prima del run v3).
- Non serve ripetere i rilanci di oggi per questo: i **rapporti a finestra
  identica** non cambiano (entrambe le sorgenti vedono lo stesso livello,
  osservatore incluso — punto 3), e sui livelli assoluti il contributo e'
  sotto 1 W, dentro l'incertezza gia' dichiarata.
- Se si vuole un numero, il disegno giusto e' n=3 finestre da 90 s per
  condizione con la baseline media sulle 3, non una A-B-A singola.

## Riprodurre

```
# processo ELEVATO (i sensori Power LHM sono invisibili senza Admin)
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe -u \
    observer_cost_probe.py gui_open
# chiudere la GUI, attendere ~20 s
C:\...\python.exe -u observer_cost_probe.py gui_closed
# riaprire la GUI (LibreHardwareMonitor.NET.10\LibreHardwareMonitor.exe)
C:\...\python.exe -u observer_cost_probe.py gui_open2
```

Ogni esecuzione scrive CSV+JSON e stampa il riepilogo prima del teardown;
l'eccezione CLR di pythonnet in chiusura si e' ripresentata anche qui (dopo la
stampa, dati integri) — terzo osservatorio sul fatto che il lancio non e'
deterministico e non conta nei risultati.
