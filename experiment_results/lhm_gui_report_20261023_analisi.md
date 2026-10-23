# Report della GUI LibreHardwareMonitor — cosa prova e cosa cambia

**Data analisi**: 2026-10-23, dopo le 16:05
**File archiviati qui**: `lhm_gui_report_20261023.txt` (137.005 B, mtime 23/10 16:05:40)
e `lhm_gui_report_20261015.txt` (90.849 B, mtime 15/10 14:02:12).
Entrambi generati da `LibreHardwareMonitor.exe` **v 0.9.6.0** (header dei due file;
oggi su CLR 10.0.13, il 15/10 su CLR 4.0.30319.42000), copia in
`C:\Users\Massimo\Documents\CasualWatt\LHM\LibreHardwareMonitor.NET.10\`.
Sono report "testuali" della GUI: fotografano la lista sensori in un istante,
con valore / minimo / massimo per riga.

## 1. L'omonimia "CPU Package" e' provata dall'esterno, non dal nostro codice

Le due righe che si leggono fianco a fianco nello stesso report del 23/10:

```
|  +- CPU Package    :  13.9577  6.83624  44.0328 (/intelcpu/0/power/0)
|  +- CPU Package    :       68       59      100 (/intelcpu/0/temperature/16)
```

Stesso nome, due sensori distinti, identificadori diversi (`power/0` contro
`temperature/16`), ordini di grandezza diversi. E' la conferma visiva e
firmata da un software terzo del difetto arbitrato oggi: selezionare il sensore
**per nome** (`energy_session.py:819` prima del fix `1422d1b`) poteva prendere
uno dei due, e prendeva il secondo. La nostra prova interna era il probe
`lhm_readpath_probe_20261023_132621.json` (posizione 38 = `Temperature` 65,0,
posizione 67 = `Power` 8,691 W); il report aggiunge una prova che non dipende
dal nostro codice.

## 2. La confutazione era disponibile otto giorni prima

Nel report del **15/10** lo stesso sensore valeva gia':

```
|  +- CPU Package    :  8.90718  8.40652  14.9184 (/intelcpu/0/power/0)
```

8,91 W (min 8,41 / max 14,92) contro i ~70 "W" che la produzione asseriva nelle
stesse settimane. Il confronto era dunque gia' stato fatto, e archiviato:
mancava solo la decisione di credere al disaccordo invece che alla propria
catena di calcolo. E' un risultato metodologico, non solo un numero: va messo
fra i vincoli di lavoro ("un disaccordo fra due strumenti sullo stesso
oggetto apre un lavoro di arbitrato, non si risolve con la fiducia
all'osservato").

## 3. La lista dei sensori: perche' 4 + 1 righe `/power/` e zero `/energy/`

Verificato nei due report: 5 righe `/power/`, **0** righe `/energy/`,
0 `/current/`, 51 `/temperature/` (23/10). Le 5 `/power/` non sono le 5 etichette
del sorgente: sono 4 del package CPU + 1 della GPU integrata.

```
/intelcpu/0/power/0  CPU Package   13,96 W  [6,84 .. 44,03]
/intelcpu/0/power/1  CPU Cores      7,29 W  [2,01 .. 38,71]
/intelcpu/0/power/3  CPU Memory     0,00 W  (MSR_DRAM_ENERGY_STATUS spento qui)
/intelcpu/0/power/4  CPU Platform   0,33 W
/gpu-intel-integrated/.../power/0  GPU Power 0,61 W
```

Il buco sull'indice 2 ("CPU Graphics") e' voluto dal sorgente:
`IntelCpu.cs:688-690` salta `i == 2` su Windows perche' la iGPU la espone il
modulo GPU. Il massimo di `CPU Package`, **44,03 W**, sta dentro l'involucro
OEM misurato (PL1 35 W, PL2 55 W, `hwinfo_idle_20261023_011237.csv`): plausibile.
I 99 "W" pre-fix stavano fuori da PL2 e sono un altro motivo, indipendente, per
cui la lettura vecchia era falsa.

## 4. Gap di versione: produzione 0.9.4.0, GUI 0.9.6.0

```
cwEnergyModular/config.py:27  ->  LHM_DLL_PATH = BASE_DIR / "LibreHardwareMonitorLib" /
                                  "LibreHardwareMonitor" / "LibreHardwareMonitorLib.dll"
                                  = 712.192 B, FileVersion 0.9.4.0  (produzione)
LHM/LibreHardwareMonitor.NET.10/LibreHardwareMonitorLib.dll
                                  = 1.214.976 B, FileVersion 0.9.6.0 (la GUI)
```

Conseguenza da dichiarare: **il sorgente che abbiamo letto per l'arbitrato
(`LHM/LibreHardwareMonitor-0.9.6/`) e' la versione 0.9.6, non quella in
produzione.** Le righe citate in tesi (`IntelCpu.cs:28`, `:401`, `:480`,
`:687-698`) valgono come descrizione del 0.9.6. Il comportamento del 0.9.4
in esecuzione e' stabilito **per via di runtime** (probe 132621: l'omonimo
`Temperature` e' nella lista, e il fix sul `SensorType` cambia il numero letto
in 3 fasi su 3), non per lettura del sorgente di quella versione, che non
abbiamo. La tesi va etichettata di conseguenza. Stessa omonimia, stessa
correzione efficace: la conclusione regge, la citazione di riga no.

## 5. Su questa macchina LHM non dara' mai il contatore cumulativo

`SensorType.Energy` esiste (unita' dichiarata **mWh**, `ISensor.cs:34`), ma nel
sorgente 0.9.6 viene istanziato **solo** da `Battery.cs:76`, `:77`, `:81`
(Designed / Fully-Charged / Remaining capacity). Nessun backend EMI: grep su
`LibreHardwareMonitorLib/` di `energyMeterInterface`, `45bd8344` (il GUID del
device EMI), `GetMeasurement` → **zero risultati**. MINI_IT13 non ha batteria.
Quindi:

1. l'assenza di `/energy/` nei report non e' un bug ne' una questione di
   versione: e' strutturale;
2. `power-integration` non e' un workaround provvisorio, e' l'unico modo di
   fare joule con LibreHardwareMonitor su questo hardware;
3. il contatore cumulativo su Windows lo da' solo EMI (e SRUM, che pero' e'
   a granularita' oraria/percentuale e non in tempo reale). La coppia
   (rate LHM, contatore EMI) e' la migliore disponibile e va mantenuta cosi'.

## 6. Il sensore `CPU Package` e' gia' una differenza finita dello stesso MSR

```
IntelCpu.cs:470-475   legge MSR_RAPL_POWER_UNIT (0x606) ed EnergyUnitsMultiplier
                      = 1 / (1 << ((eax >> 8) & 0x1F))   # cioe' 2^-U joule per tick
IntelCpu.cs:693       if (deltaTime < 0.01) continue;
IntelCpu.cs:696       sensor.Value = EnergyUnitsMultiplier * (energyConsumed
                                  - lastEnergyConsumed) / deltaTime;
```

Il valore "W" di LHM non e' una misura di corrente o di un PLL: e' esattamente
`Δ(MSR 0x611) / Δt`, con il moltiplicatore di unita' preso da `0x606`. Questo
spiega il risultato di oggi meglio di quanto facesse la sola coincidenza dei
nomi: integrando a finestra identica una rate cosi' costruita si recupera il
`Δ` del contatore, e il rapporto LHM/EMI doveva venire ~1 per costruzione
software. **Conferma che il confronto same-counter non arbitra la scala** (gia'
detto) e che l'accordo entro l'1% valida le due catene di lettura simultanee.
Nota non usata: il ramo `Silvermont/Airmont` di `:472-473` usa `1.0e-6 * (1<<U)`,
cioe' moltiplica invece di dividere — non ci riguarda (Raptor Lake), ma se mai
CasualWatt venisse eseguito su una macchina Atom e' la prima cosa da verificare.

## 7. La GUI espone anche un web server, oggi spento

Il binario GUI contiene `StartHttpListener` / `StopHttpListener` /
`System.Net.HttpListener` e una pagina che fa `$.getJSON('data.json')`;
`LibreHardwareMonitor/Utilities/HttpServer.cs:586` mappa `SensorType.Energy`
su `("watthour", 0.001)`. Verifica di stasera: `curl --max-time 3
http://localhost:808{4,5,6}/data.json` → `000` su tutte e tre, e `netstat` non
mostra ascolti su 808x. L'opzione remote non e' attiva (e' la stessa casella
"Remote Web Server" che con HWiNFO abbiamo gia' evitato di toccare via GUI
automation). Se attivata darebbe una **terza lettura dello stesso registro**:
utile come ridondanza software, inutile come arbitro della scala.

## 8. Cosa cambia per i protocolli di oggi

La GUI era avviata alle **14:06:05** (PID 14828) ed e' rimasta aperta per
tutta la finestra dei rilanci (14:15 → 16:04). `smoke_test_readpath.py:17`
dichiara fra i requisiti "LHM chiuso altrove (un solo `Computer()` aperto alla
volta)": il vincolo non era soddisfatto, e i run di oggi vanno letti con
questa condizione dichiarata. Effetto quantificato a parte in
`observer_cost_20261023_analisi.md` (risultato: non arbitrato, 0–0,9 W
sull'idle; **non** spiega l'intervallo dei campioni).
