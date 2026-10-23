# Probe EMI a 50 ms e 10 ms — il limite di risoluzione non è del contatore

Data: 23/10/2026, host MINI_IT13 (i9-13900HK, Windows 11), terminale elevato.
Script: `emi_50ms_probe.py`.
Dati: `emi_50ms_probe_20261023_184046.csv` (50 ms),
`emi_50ms_probe_20261023_184129.csv` (10 ms),
console `emi_probe_50ms_console.txt`, `emi_probe_10ms_console.txt`.

## Domanda

Il lavoro ha misurato una cadenza reale di 0,28–0,34 s contro i 0,05 s
dichiarati da `energy_session.py:45`, e per ora ha imputato il gap al carico del
thread di integrazione LHM. La domanda che il lavoro NON aveva ancora arbitrato
è precedente e più forte: se il campionamento fosse veloce, il registro
reggerebbe? Se no, la risoluzione è una proprietà del silicio e nessun refactor
del thread cambierebbe nulla. Se sì, il collo di bottiglia è nostro.

Il probe legge l'IOCTL EMI `IOCTL_EMI_GET_MEASUREMENT` (0x0022400C) direttamente
con ctypes, senza LibreHardwareMonitor, con scadenza assoluta a 50 ms e poi a
10 ms, su due fasi: riposo, e carico generato da 4 processi di spin.

## Risultato

| cadenza | fase | letture | Δ PKG nulli | Δ PP0 nulli | Δ PP1 nulli | Δ DRAM nulli |
|---|---|---|---|---|---|---|
| 50 ms | riposo | 800 | 0/799 (0,00%) | 0/799 | 0/799 | 799/799 (100%) |
| 50 ms | load 4 proc | 800 | 0/799 (0,00%) | 0/799 | 0/799 | 799/799 |
| 10 ms | riposo | 2000 | 0/1999 (0,00%) | 3/1999 (0,15%) | 43/1999 (2,15%) | 1999/1999 |
| 10 ms | load 4 proc | 2000 | 2/1999 (0,10%) | 6/1999 (0,30%) | 56/1999 (2,80%) | 1999/1999 |

Il timestamp del dominio avanza nel 100% dei casi con mediana pari
all'intervallo dichiarato (50,01 / 49,99 / 10,02 / 9,99 ms): non stiamo
ricopiando lo stesso record.

Ogni cadenza è stata corsa due volte (quattro CSV in archivio: `183652` e
`184046` a 50 ms, `183819` e `184129` a 10 ms; le prime due senza il controllo
sul timestamp in output, che però si ricalcola dal CSV). Le ripetizioni
concordano: Δ PKG nulli 0/799 in entrambe le corse a 50 ms; potenza di package
a riposo 11,99 e 11,94 W (50 ms), 12,19 e 12,02 W (10 ms); PP0/PKG a riposo
0,5011 e 0,5049 (50 ms), 0,5120 e 0,5068 (10 ms), sotto carico 0,8402 e 0,8395,
0,8429 e 0,8423. La conclusione non dipende da una singola corsa.

**La finestra minima osservabile del package è 1 campione.** A 50 ms: 92,6 J
(riposo) e 194,0 J (carico) di increments medi per campione, 0 delta nulli.
A 10 ms: 4,09 J e 1,16 J. Non esiste un pavimento di finestra a 50 ms — e non
esiste praticamente nemmeno a 10 ms.

## Cosa risponde

**Il limite di risoluzione non è del contatore: è del nostro percorso di
lettura.** Il contatore del package eroga energia aggiornata a 10 ms su questa
macchina. La cadenza di 0,28–0,34 s è una proprietà del thread LHM
`power-integration`, e la scelta di leggere LHM (libreria generalista) invece
del canale nativo (driver di Intel) ha un costo metrologico preciso e misurato:
un fattore ~6× sulla cadenza.

È la misura che mancava per passare dal "forse" al "dimostrato" in cap. 3.3,
cap. 5.5 e cap. 6.2 — e il limite dei 4 casi su 634 delta nulli della trace a
250 ms (cap. 5.5) ora si legge diversamente: era già il percorso di lettura,
non il silicio.

## Due risultati collaterali, più pregiate della risposta

**1. Confine misurato, non dichiarato.** Il package ha un residuo
non attribuito a core né a iGPU di **5,51–5,59 W**, stabile fra riposo e
carico al 99,9% (223,35 J a riposo contro 223,22 J sotto carico su 40 s; e
111,74 J contro 110,09 J su 20 s). È la prima volta che un pezzo del confine di
misura viene **quantificato**, non solo elencato. È anche la ragione per cui
la riga `pkg CPU` della tabella dei confini (tab. 3.13) non può essere
attribuita a un processo senza un peso.

**2. La proposta ΔPP0/ΔPKG è sostenuta dai dati.** Su un carico che è puro CPU
(4 processi di spin, nessuna GPU), l'incremento di PP0 copre l'incremento del
package con rapporto **0,99972 a 50 ms e 1,00389 a 10 ms**: due cadenze
indipendenti, scarto dallo 0,03% allo 0,39%. PP1 (iGPU) si muove di 0,41 J e
−0,29 J, cioè rumore. DRAM è inesposto qui (0/799 e 0/1999 delta non nulli) ma
**non è una proprietà del chip**: la riga `package` non include i joule di
memoria che il dominio DRAM conterrebbe.

## Limiti di questa prova

- Il carico è di spin in Python, non un'inferenza: serve a interrogare il
  registro, non a produrre una J/token.
- Il contatore è lo stesso `MSR_PKG_ENERGY_STATUS` letto da LHM: il probe
  dimostra la **cadenza del canale**, non la correttezza della scala assoluta
  (che resta non arbitrata — valgono le note del 23/10 su same-counter).
- La cadenza dichiarata NON è quella ottenuta: a 50 ms il dt reale è
  46,4–54,4 ms (±8%); a 10 ms il `time.sleep` di Windows degrada il campionamento
  (2,2–17,8 ms, mediana 10,0 ms) e la varianza del delta si mangia la
  risoluzione temporale. 50 ms è il limite inferiore utile con questo
  strumentazione software; per scendere serve un timer periodico.
- Un solo host, come per tutto il lavoro.

## Conseguenze operative, in ordine

1. **Il percorso di campionamento diretto EMI a 50 ms è ora un'opzione
   documentata**, non un'ipotesi: è la voce 3 degli sviluppi (cap. 6.3) e ha
   la sua evidenza. Va costruito come **secondo percorso da confrontare**
   (`--metodo` esplicito), non come sostituto silenzioso di LHM — la regola
   "attuale finché provato" vale più qui che altrove, perché LHM è il canale
   su cui sono stati tarati i protocolli v1–v3.
2. **I limiti scritti in tesi che imputavano la finestra al contatore vanno
   corretti** (cap. 3.3, 5.5, 6.2, abstract).
3. **La metrica ΔPP0/ΔPKG per fase è proposta con numeri**, non più come idea.
