# metodiLoc.DOCX — valutazione e metodologia di scelta dei canali, 2026-10-25

Materiale valutato: `metodiLoc.DOCX` (radice del repository, non tracciato),
396 paragrafi. E' una risposta di assistente con citazioni segnaposto
(`[ppl-ai-file-upload.s3.amazonaws]`): vale come **spunto, non come evidenza**.
Ogni affermazione di questo file e' verificata il 25/10/2026 contro il codice,
un artefatto tracciato o il protocollo congelato.

Seguito operativo: `metodi_per_dominio_20261025_spec.md` traduce questa
valutazione nella specifica dei metodi e delle catene di fallback per dominio,
inclusi cloud e rete.

## 1. Verdetto

L'impianto del documento e' corretto e coincide in gran parte con cio' che
CasualWatt fa gia': tassonomia contatore / integrazione / modello / non
disponibile, fallback **per dominio** e non per macchina, etichetta del metodo
sempre registrata, divieto di sommare domini sovrapposti, segmentazione al
cambio di backend, nessuna percentuale di accuratezza senza riferimento
indipendente.

Non e' adottabile come specifica, per cinque motivi:

1. propone un canale `estimated` (TDP) come fallback, che le regole del progetto
   escludono e che il codice non ha (`energy/energy_session.py:49-50`);
2. tratta SRUM/E3 come misura per-processo e come fallback della CPU: e' il
   modello EPI, non un contatore, e non e' per-richiesta;
3. descrive il contatore energetico NVML come primario gia' esistente: nel
   codice c'e' solo `nvmlDeviceGetPowerUsage` e l'integrazione
   (`energy/energy_session.py:2445`, `energy/local_energy.py:377-447`);
4. sbaglia due fatti: l'EMI non esiste su Windows AMD (e' il canale energia
   Intel, `energy/emi_backend.py:7-9`) e PP1 non e' una misura completa della
   GPU;
5. cita numeri stantii (77 superati / 3 saltati; 12,62 e 20,93 W).

La parte davvero utile e' la **forma della decisione**; la sostanza va riscritta
sullo stato reale.

## 2. Cosa e' gia' nostro e va solo documentato

| Proposta del documento | Stato in CasualWatt (25/10) |
|---|---|
| Quattro classi di risultato | Implementate come token di metodo; `MEASURED_METHODS` ammette solo canali di misura (`energy/energy_session.py:49-50`) |
| Fallback per dominio, CPU e GPU indipendenti | CPU e GPU hanno percorsi separati (`energy/local_energy.py:374-493`) |
| Etichetta e provenienza per riga | `energy_calculation_method`, `package_window_source`, `idle_provenance`, `domain`, `raw_start/raw_end`, `backend_version` (`energy/local_energy.py:90-115`) |
| Rollover, reset, monotonia | RAPL ha unwrap esplicito (`energy/rapl_backend.py:120-134`); EMI espone il timestamp **per dominio**, unico modo per accorgersi che un canale non si aggiorna (`energy/emi_backend.py:31-39`) |
| Divieto di sommare domini sovrapposti | Enunciato con la fonte (`energy/emi_backend.py:28-30`); PP1 resta informativo (`energy/local_energy.py:463-476`) |
| Segmentazione al cambio backend | Regola gia' nel protocollo; il metodo e' per riga, non per sessione (`casualwatt_csv_export.py:90-92`) |
| Nessuna percentuale di accuratezza | P4.9/P4.10 (`experiment_results/protocollo_v4_20261024.md:2112-2128`) |

Il documento chiede cose che qui sono piu' avanti di quanto lui sappia (valori
grezzi, dominio, versione del backend); su un punto e' pero' piu' avanti lui: la
**struttura di decisione** e' scritta in modo piu' ordinato, e conviene
adottarla come documento, non come refactor.

## 3. Cosa non adottiamo, e perche'

### 3.1 Il canale "stima TDP" / `EstimatedProvider`

`MEASURED_METHODS` contiene cinque canali e nessun `estimated`
(`energy/energy_session.py:49-50`). La stima TDP e' il percorso di CodeCarbon,
usato nella tesi come contrasto, non come fallback di CasualWatt. Un numero
senza un metodo che lo produce e' peggio di un `N/A`: la catena finisce in
`unavailable`, non in una stima. Se un giorno servira' una stima dichiarata,
avra' un campo proprio e un confine proprio, mai il token di
`energy_calculation_method`.

### 3.2 SRUM/E3 non sono una misura per-processo ne' un fallback CPU

SRUM produce un modello EPI di ripartizione, non una lettura hardware: le 596
righe con `EmiEnergyConsumption` non nulla sono pseudo-AppId
`EMI_RAPL_Package0_PKG/_PP0/_PP1`, e i bucket sono compattati a orari
(`experiment_results/srum_emi_cross_20261023_analisi.md:16-18`, `:42-52`).
Inoltre richiede `powercfg /srumutil` elevato (`srum.py:75`) e non e'
per-richiesta. Il
confronto quota di tempo CPU contro EPI arbitra la **procedura di
attribuzione**, non l'equivalenza tempo-energia
(`experiment_results/protocollo_v4_20261024.md:2116`). Quindi senza LHM la
catena Windows resta `EMI -> unavailable`, non `EMI -> SRUM -> TDP`.

### 3.3 LHM non e' una validazione di EMI

Entrambi leggono `MSR_PKG_ENERGY_STATUS` (0x611): concordano per costruzione
anche se la scala fosse sbagliata (`energy/emi_backend.py:9-11`;
`experiment_results/alt_lhm_20261024_valutazione.md:47-55`). Un A-B-A fra due
letture dello stesso registro nasconde un canale sbagliato invece di
correggerlo, ed e' successo (`experiment_results/protocollo_v4_20261024.md:2122-2128`).
LHM e' un **secondo percorso**, non un riferimento.

### 3.4 Il contatore energetico NVML non e' implementato

Nel codice esiste solo la potenza: `nvmlDeviceGetPowerUsage`
(`energy/energy_session.py:2445`), integrata trapezoidalmente e meno la
baseline (`energy/local_energy.py:380-407`). `nvmlDeviceGetTotalEnergyConsumption`
non compare da nessuna parte. La descrizione del documento e' un obiettivo, non
lo stato.

### 3.5 EMI su Windows AMD non esiste

Il canale EMI e' il device del processore **Intel**
(`energy/emi_backend.py:7-9`, GUID `45bd8344-...`). Su AMD il percorso e'
LHM, se espone un sensore di potenza package, altrimenti `unavailable`; su
hardware AMD non e' verificato.

### 3.6 PP1 non e' la GPU

PP1 e' il dominio grafico del package, sottoinsieme di PKG, letto ai bordi di
finestra come campo informativo (`energy/emi_backend.py:22-23`, `:38-39`;
`energy/local_energy.py:463-476`). Non e' una misura completa della GPU e non
si somma. Per una GPU Intel dedicata non esiste backend.

### 3.7 I numeri citati sono stantii

Il documento riporta 77 superati / 3 saltati; la suite attuale e' 157 raccolti =
154 passati + 3 saltati (25/10). Riporta 12,62 W idle e 20,93 W sotto carico:
sono le misure del primo giorno EMI, non lo stato corrente. In generale i numeri
di un documento esterno non si citano se non sono riprodotti qui.

## 4. Metodologia di scelta dei canali

Questa e' la parte che adottiamo, riscritta come regola operativa.

### 4.1 L'unita' di decisione e' il dominio fisico, non la macchina

La configurazione non e' "Windows 11" ne' "i9-13900HK": e' la tupla

    (sistema operativo, produttore, dominio, interfaccia disponibile)

I domini che CasualWatt puo' trattare sono: `cpu_package`, `gpu` dedicata,
`npu` (quando esistera' un'interfaccia verificata), `cloud`, `network`. La iGPU
non e' un dominio separato: e' **dentro** il package. La DRAM e' esposta da EMI
ma spesso vale zero e non e' additiva; non si usa.

Conseguenza: non esiste "la misura del computer". Ogni riga dichiara il confine
(`measurement_boundary`) e il dominio; una misura CPU valida resta valida anche
se la GPU non ha telemetria, e viceversa.

### 4.2 Gerarchia epistemica: tre livelli di misura piu' l'assenza

| livello | che cos'e' | esempi | cosa dichiara |
|---|---|---|---|
| M1 | contatore cumulativo di dominio | EMI PKG, RAPL `energy_uj`, NVML total energy (non implementato) | energia del dominio tra due letture |
| M2 | integrazione di potenza dello stesso dominio | LHM `CPU Package`, NVML `PowerUsage` | energia = integrale, dipende da cadenza e copertura |
| M3 | modello o attribuzione | quota di tempo CPU, quota di utilizzo GPU, EPI | una **quota**, non una lettura |
| M4 | non disponibile | nessun canale utilizzabile | assenza dichiarata, con ragione |

Le stime cloud (EcoLogits) e rete (coefficiente `3.4e-8 J/bit`,
`cwEnergyModular/config.py:333-334`) stanno **fuori** da questa scala: non sono
misure di un dominio locale e hanno campi propri. La scala M1-M4 e' una lente
documentale; l'arbitro per riga resta il token di metodo del CSV. Non si
introduce una seconda tassonomia nel CSV.

### 4.3 Cinque controlli, e cosa abilita ciascuno

| controllo | domanda | se fallisce |
|---|---|---|
| G0 disponibilita' | l'interfaccia esiste ed e' leggibile? | si passa al livello successivo |
| G1 semantica | unita', dominio e conversione sono documentati e verificati (non assunti)? | il canale non e' utilizzabile |
| G2 integrita' di finestra | monotonia, reset, rollover, timestamp per dominio, copertura, campioni mancanti | la finestra si segmenta o si dichiara `unavailable`; mai sottrazione cieca |
| G3 confine | cosa include il dominio, cosa si sovrappone, misura di dominio o attribuzione? | il canale non e' utilizzabile per quel dominio |
| G4 validazione | esiste un riferimento indipendente e lo stesso intervallo? | si puo' usare, ma **non** si scrive "validato" |

G0-G3 decidono **se** un canale e' utilizzabile. G4 non cambia il canale: cambia
solo la parola che si puo' usare. Un canale piu' forte per semantica ma non
validato non viene sostituito silenziosamente da uno piu' debole "validato"; si
sceglie il piu' forte che passa G0-G3 e si dichiara lo stato di validazione.

### 4.4 Regola di selezione

```
per ogni dominio richiesto:
    per ogni canale nella catena pre-registrata (OS, produttore, dominio):
        se G0..G3 passano:
            seleziona canale
            stato = "validato" se G4 passa, altrimenti "funzionamento verificato"
            interrompi
    se nessun canale passa:
        seleziona "unavailable" con la ragione
```

L'ordine della catena e' fissato **prima** di eseguire, non deciso a runtime in
base a cosa risponde. Un rollover o una copertura incompleta sono un fallimento
di G2 di **quella finestra**: si segmenta o si dichiara l'assenza; non si
"sistema" il numero.

### 4.5 Quanti fallback

Tanti quanti sono i percorsi **meccanicamente distinti**, non di piu'. Due
letture dello stesso registro non sono due fallback: sono due implementazioni
dello stesso canale, e la seconda non copre il guasto della prima (driver,
permessi, formato). Oggi:

- Windows Intel CPU: **2** (EMI, poi LHM);
- Windows AMD CPU: **1** (LHM), e solo se il sensore esiste;
- Linux Intel CPU: **1** (RAPL);
- GPU NVIDIA: **1** (NVML potenza), con il contatore NVML come futuro M1;
- GPU AMD, GPU Intel dedicata, NPU, macOS: **0**, quindi `unavailable`;
- iGPU Intel: **0** termini separati, perche' e' dentro PKG.

### 4.6 Cambio di canale a meta' finestra

Non si concatenano dati di backend diversi. Se il canale cambia, la finestra si
interrompe o si separa in segmenti, e il cambio resta scritto nella riga. La
regola e' gia' nel protocollo e il CSV ha il metodo per riga
(`casualwatt_csv_export.py:90-92`).

## 5. Matrice di capacita' reale al 25/10/2026

| piattaforma / dominio | M1 contatore | M2 integrazione | stato verificato | etichetta pubblicabile |
|---|---|---|---|---|
| Windows Intel `cpu_package` | EMI PKG | LHM `CPU Package` | M1 funzionante su i9-13900HK; M2 fallback | `emi-counter` / `power-integration` |
| Windows AMD `cpu_package` | nessuno | LHM se espone il package | non verificato | `power-integration` oppure `unavailable` |
| Linux Intel `cpu_package` | RAPL `energy_uj` | nessuno | codice implementato, 3 test saltati (nessun host Linux) | `rapl` |
| Linux AMD `cpu_package` | percorso `intel-rapl:0` | nessuno | non verificato | `rapl` solo se il percorso esiste, altrimenti `unavailable` |
| Windows NVIDIA `gpu` | nessuno (NVML energy assente) | NVML `PowerUsage` whole-device, idle **mai calibrato** | implementato, non validato | `power-integration` con `gpu_idle_provenance=missing` |
| AMD / Intel dGPU `gpu` | nessuno | nessuno | assente | `unavailable` |
| Intel iGPU | PP1 (informativo) | LHM `CPU Graphics` (informativo) | dentro PKG, mai sommato | campo `igpu_energy_j` |
| NPU (qualsiasi OS) | nessuno | nessuno | assente | `unavailable` |
| macOS | nessuno | nessuno | percorso `unavailable` (`energy/energy_session.py:192-197`) | `unavailable` |
| cloud | nessuno | EcoLogits (stima) | stimato, non misurato | `ecologits` + range |
| rete | nessuno | coefficiente J/bit | stima non validata | campo `network_*` |

Due precisazioni che la matrice rende visibili:

1. **La GPU NVIDIA oggi non e' incrementale.** `idle_gpu_power_w` viene letto
   ma non assegnato da nessun percorso di produzione (grep: solo i test lo
   impostano), quindi `gpu_idle_provenance` e' `missing` per costruzione e
   `gpu_energy_attributed_j` e' l'energia **dell'intera scheda** nella finestra
   (`energy/local_energy.py:397-407`). Va dichiarato; non e' la stessa
   grandezza di `ollama_active_energy_j`.
2. **L'attribuzione GPU per processo e' M3.** `process_energy_j` moltiplica
   l'energia board attiva per la frazione di utilizzo dei PID
   (`energy/energy_session.py:2465-2504`): e' un modello, etichettato
   informativo, non una lettura.

## 6. Catene di fallback, esplicite

| dominio | catena | etichette |
|---|---|---|
| Windows Intel CPU | EMI PKG -> LHM potenza -> `unavailable` | `emi-counter`, `power-integration`, `unavailable` |
| Windows AMD CPU | LHM potenza (se presente) -> `unavailable` | `power-integration`, `unavailable` |
| Linux Intel CPU | RAPL -> `unavailable` | `rapl`, `unavailable` |
| Linux AMD CPU | RAPL se il percorso esiste -> `unavailable` | `rapl`, `unavailable` |
| NVIDIA GPU | NVML potenza whole-device -> `unavailable` | `power-integration`, `unavailable` |
| AMD/Intel dGPU | `unavailable` | `unavailable` |
| NPU | `unavailable` | `unavailable` |
| macOS | `unavailable` | `unavailable` |
| cloud | EcoLogits (stima, non fallback di misura) | `ecologits` |
| rete | coefficiente (stima, non fallback di misura) | campo dedicato |

Quattro regole che valgono per tutte:

- un livello inferiore non si presenta mai con l'etichetta del superiore;
- il fallback non e' una licenza a inventare: se anche l'ultimo livello di
  misura fallisce, il risultato e' `unavailable`;
- il fallback di un dominio non degrada gli altri;
- l'assenza di un dominio (GPU, NPU) non rende invalida la misura CPU.

## 7. LHM come fallback: si', con cinque condizioni

**Decisione: tenerlo.** Non perche' sia un riferimento, ma perche' e' l'unico
secondo percorso su Windows.

1. Copre il guasto che EMI non copre: macchine senza driver del canale energia,
   Intel piu' vecchie, AMD, dove l'IOCTL non esiste
   (`energy/emi_backend.py:41-44`).
2. I suoi modi di guasto sono diversi (assembly .NET, apertura `Computer()`,
   sensori) e quindi un fallback reale, anche se non indipendente come evidenza.
3. Non apre nulla quando EMI funziona: il probe LHM e' saltato
   (`energy/energy_session.py:172-180`), e questo evita il costo .NET e
   l'effetto osservatore.
4. Fornisce sensori che EMI non espone (grafica integrata come campo
   informativo, sensori di contorno).
5. E' l'unico produttore del token `librehardwaremonitor-energy`, ma su questa
   macchina il sensore `Energy` non esiste: e' istanziato solo dalla batteria in
   LHM 0.9.6 (`experiment_results/lhm_gui_report_20261023_analisi.md:46-99`).
   Il fallback **effettivo** e' quindi `power-integration`, non
   `librehardwaremonitor-energy`.

Condizioni d'uso:

- etichetta `power-integration`, mai `emi-counter`;
- cadenza **osservata** dichiarata: 0,2803 s contro 0,05 s richiesti
  (`experiment_results/observer_cost_20261023_analisi.md:59-61`;
  `experiment_results/alt_lhm_20261024_valutazione.md:79-87`);
- nessuna hot-swap a meta' finestra: si segmenta;
- il suo accordo con EMI non e' validazione (stesso registro 0x611);
- se fallisce anche lui: `unavailable`, mai TDP o stima.

Nota di confine: EMI non richiede elevazione (`energy/emi_backend.py:15-16`),
mentre i sensori Energy-CPU di LHM la richiedono: senza UAC la libreria si
aggancia ma legge zero/None (`energy/energy_session.py:542-552`). Una macchina
senza privilegi e senza driver EMI puo' quindi non avere **nessun** canale: e'
un caso da dichiarare, non da aggirare.

## 8. NPU

Non esiste oggi un contatore NPU verificato, ne' nel codice (nessun riferimento
a NPU) ne' nel record EMI, che espone solo PKG, DRAM, PP0 e PP1
(`energy/emi_backend.py:18-23`). Se una NPU integrata consuma dentro il
package, la sua energia e' **dentro** PKG ma non e' separabile: non si puo'
dire "energia della NPU" ne' per differenza ne' per quota inventata.

Supporto possibile solo quando esistono, tutti insieme: interfaccia documentata
dal produttore, contatore cumulativo o di potenza per quel dominio, definizione
del dominio (cosa include), disponibilita' verificabile a runtime, e gli stessi
G0-G4. Fino ad allora: `unavailable`. Non si aggiungono colonne NPU al CSV
prima che esista un backend: sarebbero colonne vuote che suggeriscono un
canale inesistente.

## 9. Cosa serve per dire "validato"

La parola ha una sola definizione: tutti e sei gli anelli di P4.9 passano
(`experiment_results/protocollo_v4_20261024.md:2100-2120`). Oggi l'anello piu'
debole e' l'assenza del wattometro: senza riferimento esterno la **scala
assoluta** resta non arbitrata, anche se il percorso e' coerente.

Metriche da riportare, per macchina, dominio e durata di finestra: bias
percentuale, errore assoluto percentuale, MAE, RMSE, ripetibilita' (CV delle
repliche), copertura operativa (finestre valide / tentate), overhead del
monitoraggio. Con energia di riferimento vicina a zero il rapporto e' instabile:
servono anche gli errori assoluti in joule. Le soglie si fissano prima dei dati.

Un confronto a finestra uguale fra due letture dello stesso registro **non**
entra in questa lista come validazione: e' un controllo di implementazione.

## 10. Conseguenze per P5 e per il codice (oggi congelato)

Questo documento non tocca il codice di produzione: P5 e' aperto e il codice
resta bloccato.

Quando P5 si chiude, le decisioni che discendono da qui sono:

1. **Decisione di schema, ora o mai piu'.** Oggi la GPU ha
   `gpu_attribution_method` (prosa) e `gpu_idle_provenance`, ma non un token di
   metodo stabile come la CPU (`energy_calculation_method`). Se si vuole che la
   GPU sia confrontabile per riga, il token va deciso **in P5**, perche' dopo il
   congelamento lo schema non si cambia. Proposta minima:
   `gpu_energy_method` con valori `nvml-power-integration` / `unavailable`.
2. **Nessun refactor a `EnergyProvider` adesso.** Il contratto (dominio,
   metodo, unita', provenienza, disponibilita') e' gia' implementato per riga;
   una gerarchia di classi prima di P5 aggiungerebbe rischio senza evidenza.
3. **Baseline idle GPU.** Senza, ogni numero GPU e' whole-device: e' la lacuna
   piu' concreta della matrice, e va colmata prima di usare la GPU in una
   campagna.
4. **Contatore NVML.** Se e quando implementato, entra come M1 **sopra** la
   potenza, con gli stessi controlli; non sostituisce la potenza come fallback.
5. **RAPL reale.** Provare su Linux Intel, poi AMD, prima di dichiarare il
   supporto. Il percorso e' cablato su `intel-rapl:0`
   (`energy/rapl_backend.py:45-48`) e non e' stato eseguito su hardware reale.
6. **AMD SMI / NPU.** Solo con documentazione verificata alla fonte e un test
   che dimostri lettura e dominio; fino ad allora `unavailable`.

## 11. Priorita'

1. baseline idle GPU (rende utilizzabile il canale NVIDIA);
2. token GPU in P5 (decide la confrontabilita' futura);
3. RAPL su Linux reale (Intel, poi AMD);
4. contatore NVML come M1;
5. AMD SMI e NPU solo dopo verifica documentale;
6. wattmetro AC/DC esterno, unica via alla validazione della scala assoluta.

## 12. Rifiuti espliciti

| proposta del documento | decisione | motivo |
|---|---|---|
| fallback TDP / `EstimatedProvider` | rifiutata | non e' una misura; `MEASURED_METHODS` non lo ammette |
| SRUM/E3 come provider o fallback CPU | rifiutata | e' il modello EPI, non un contatore; non per-richiesta; richiede elevazione |
| LHM come validazione di EMI | rifiutata | stesso registro 0x611 |
| NVML energy counter come stato attuale | corretta | non implementato; oggi solo potenza |
| EMI su Windows AMD | rifiutata | EMI e' il canale Intel |
| PP1 come energia GPU | rifiutata | dominio informativo, dentro PKG |
| percentuali di accuratezza per configurazione | rifiutata | nessun riferimento indipendente; valgono solo "funzionamento verificato" |
| 77/3 e 12,62/20,93 W | corrette | stantii; la suite e' 154/3 su 157 e le potenze sono del primo giorno |
