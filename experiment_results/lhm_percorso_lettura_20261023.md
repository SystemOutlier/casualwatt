# Da dove viene "CPU Package" di LibreHardwareMonitor, e perche' CasualWatt lo legge male

MINI_IT13, 2026-10-23, shell elevata. Due esperimenti nuovi + lettura del
sorgente LHM 0.9.6 fornito in `C:\Users\Massimo\Documents\CasualWatt\LHM`.

File di evidenza:

| File | Cosa contiene |
|---|---|
| `lhm_sensor_dump.py` / `lhm_sensor_dump_20261023_124448.{json,csv}` / `lhm_sensor_dump_console.txt` | ogni sensore Power esposto da LHM, confrontato fase per fase con i 4 domini EMI |
| `lhm_pi_path_test.py` / `lhm_pi_path_20261023_124936.{json,csv}` / `lhm_pi_path_console.txt` | lo STESSO sensore letto (a) pulito a 1 Hz con un solo `hw.Update()` e (b) dal percorso di produzione `SESSION` |
| `LibreHardwareMonitor-0.9.6/.../Cpu/IntelCpu.cs` | origine reale del valore |
| `cwEnergyModular/energy/energy_session.py:731-863` | percorso di lettura in produzione (SOLO letto, non modificato) |

## 1. Che cosa e' davvero il sensore (dal sorgente, non dalla doc)

`IntelCpu.cs`:

* `:28` — `_energyStatusMsrs = { MSR_PKG_ENERGY_STATUS, MSR_PP0_ENERGY_STATUS,
  MSR_PP1_ENERGY_STATUS, MSR_DRAM_ENERGY_STATUS, MSR_PLATFORM_ENERGY_STATUS }`,
  con i valori `:760-766`: DRAM `0x619`, PKG `0x611`, PP0 `0x639`, PP1 `0x641`,
  PLATFORM `0x64D` (+ `MSR_RAPL_POWER_UNIT = 0x606` a `:768`);
* `:469-475` — il moltiplicatore di unita' viene DA `0x606`:
  `EnergyUnitsMultiplier = 1.0f / (1 << ((eax >> 8) & 0x1F))` per le architetture
  moderne (identico alla decodifica del kernel Linux RAPL, quindi non e' un
  fattore inventato);
* `:480` — le etichette generate in quell'ordine sono
  `["CPU Package", "CPU Cores", "CPU Graphics", "CPU Memory", "CPU Platform"]`:
  **il sensore n.0 "CPU Package" e' `MSR_PKG_ENERGY_STATUS`**, cioe' lo stesso
  contatore che Windows espone tramite EMI e che noi leggiamo con
  `IOCTL_EMI_GET_MEASUREMENT`;
* `:687-698` — il valore istantaneo e' una derivata:
  `sensor.Value = EnergyUnitsMultiplier * unchecked(energyConsumed -
  _lastEnergyConsumed[idx]) / deltaTime`, con `if (deltaTime < 0.01) continue`.

Quindi: **LHM non misura la potenza, la ricava da un contatore cumulativo di
energia RAPL di package**. E' lo stesso terminale hardware del nostro canale EMI
(il trasporto per`o` e' diverso: LHM passa da `MSR read` con modulo `PawnIO`/WinRing0,
che richiede driver e privilegi; EMI e' un IOCTL del driver ACPI di Intel).

## 2. Misura A — il sensore, letto bene, E' il contatore EMI

`lhm_sensor_dump.py` (lettura pulita: un solo `hw.Update()` per tick a 1 Hz, un
solo thread, DLL reale `0.9.4.0`; il sorgente letto e' `0.9.6` — discordanza
dichiarata nel referto perche' le righe citate potrebbero non coincidere 1:1):

| Fase | EMI PKG [W] | LHM "CPU Package" [W] | offset a idle |
|---|---|---|---|
| idle | 14,29 | 14,33 | **+0,04 W** |
| burn2 | 30,18 | 29,56 | — |
| burn8 | 38,92 | 38,02 | — |
| cool | 13,48 | 13,67 | — |

Δ per gradino: burn2 `EMI 15,89 / sensore 15,23` → rapporto **1,043**; burn8
`24,63 / 23,69` → **1,040**. E i sensori fratelli mappano sugli altri domini EMI
come prevede `:480`: "CPU Cores" 8,13 W vs EMI PP0 8,10 W; "CPU Memory" 0,0 W vs
DRAM 0,0 W; "CPU Platform" 0,33 W vs EMI PP1 0,35 W.

**Conseguenza:** l'offset di ~+55 W e la "pendenza divergente" registrati nei run
four-way (22/10 e 23/10) **non sono una proprieta' del sensore**. Il sensore,
letto cosi', coincide con EMI a +0,04 W e ±4% sulla pendenza.

## 3. Misura B — il percorso di produzione gonfia lo stesso valore

`lhm_pi_path_test.py` avvia la `SESSION` reale e confronta, nella stessa fase,
tre cose: EMI, l'accumulatore di produzione (`_pi_energy_j`/dt) e il `Value`
grezzo del sensore selezionato (`src._pi_selected.Value`), letto senza chiamare
`Update()`:

| Fase | EMI PKG [W] | `produzione_W` | `raw_value` mediano [W] |
|---|---|---|---|
| idle | 14,06 | **68,26** | 13,70 |
| burn2 | 30,01 | 81,27 | 30,05 |
| burn8 | 38,49 | **95,97** | 38,28 |
| cool | 14,12 | **71,12** | 13,29 |

Il sensore, campionato a 1 Hz mentre la produzione gira, dice 13,7/30,1/38,3 W:
**giusto**. L'accumulatore di produzione dice 68/81/96 "W": **sbagliato di ~+54 W
a riposo e con rapporto 2,49 sotto carico**. Il difetto e' nel nostro percorso di
lettura, non nel sensore, non nella DLL, non in EMI.

Prova chiave (dai dati gia' scritti nel CSV del test, rielaborati): nella fase
`cool` il carico e' spento e EMI e' tornato a 14,12 W, mentre `produzione_W`
vale 71,12 W e il `raw_value` del sensore Power 13,29 W. Un sensore di potenza
non puo' comportarsi cosi'; **una temperatura si'.**

## 4. Meccanismo individuato nel codice (riga per riga)

* `IntelCpu.cs:401` crea un sensore **`SensorType.Temperature` chiamato esattamente
  "CPU Package"** (package DTS), e `:480` crea i sensori Power la cui prima
  etichetta e' ancora "CPU Package". Nel `hw.Sensors` della CPU i due oggetti
  convivono con lo STESSO nome (il Temperatura e' creato prima, quindi compare
  prima nella lista);
* `energy_session.py:731-797` (`_select_power_sensor`) filtra correttamente per
  `SensorType == "power"` e memorizza **l'oggetto** in `_pi_selected` e
  **il nome** in `_pi_sensor_name` (= "CPU Package");
* `energy_session.py:799-831` (`_read_power_w_direct`) pero' cerca con
  `:819  if sensor is sel or str(sensor.Name) == self._pi_sensor_name:`
  e **ritorna al primo match**. Il match per nome cade sul sensore Temperatura
  "CPU Package", che precede quello Power: la funzione restituisce **gradi °C**,
  e `:852  self._pi_energy_j += ((pw + w) / 2.0) * dt` integra °C·s come se
  fossero joule.

Questo spiega in un colpo solo tutti e tre i sintomi storici: l'offset quasi
costante tra i run (+54,5 W il 22/10 alle 02:00, +55,9 W alle 12:08 — cioe' il
livello di temperatura, che a riposo e' stabile), il rapporto ~2,5 sul gradino
(la temperatura sale molto meno della potenza), e l'inerzia della fase `cool`.
Il tutto mentre il canale EMI — che non passa da li' — resta corretto.

**Stato della prova:** il percorso e' dimostrato per lettura del codice (righe
sopra) e confermato indirettamente dai dati (inerzia termica in `cool`). Manca
la conferma diretta e banale: stampare nello stesso istante
`_read_power_w_direct()` contro `_pi_selected.Value` e l'elenco dei sensori
della CPU con nome "CPU Package" e loro `SensorType`. Probe preparato
(`lhm_pi_readpath_probe.py`), da eseguire senza altro carico sulla macchina.

## 5. Cosa invalida e cosa resta in piedi

Invalidati (ASSOLUTI Windows lato LHM/CasualWatt):

* `produzione_W` e quindi ogni `J/token`, ogni energia e ogni potenza assoluta
  riportati dal percorso `power-integration` su Windows nei run gia' committati
  (validazione LHM v1/v2/v3, colonne LHM dei due four-way, trace LHM+EMI 634
  campioni);
* il claim di tesi currently registrato come *"la pendenza LHM diverge da EMI,
  quindi il J/token LHM non e' valido come proprieta' del sensore"*: va
  **ri-attribuito** al nostro percorso di lettura, perche' la Misura A mostra il
  sensore fedele a ±4%.

Restano validi:

* tutto il canale **EMI** (contatore cumulativo, IOCTL ACPI, non tocca LHM): e'
  l'arbitro che abbiamo gia' usato, con i suoi differenziali A-B-A;
* SRUM come 3o/4o terminale (unita' millijoule confermata: rapporto SRUM/EMI
  0,9985, sd 0,0076);
* la scelta del *metodo* (integrazione trapezoidale del sensore di package), che
  con questa correzione diventa equivalente a EMI con un errore del 4%.

Da decidere appena confermata la prova: la correzione minima in
`energy_session.py:819` (eliminare il confronto per nome, o pretendere anche
`SensorType == "power"`). **Non la applico senza autorizzazione esplicita**: e'
il backend in produzione e la regola del progetto e' tenere l'attuale finche'
non provato — la prova diretta sta nel probe.
