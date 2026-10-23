# SRUM x EMI — run v2, 2026-10-23 (11:05:57 → 11:22:35 UTC)

Documento di evidenza. Macchina MINI_IT13, i9-13900HK, Windows 11, alimentato a
muro (nessuna batteria). Script: `srum_emi_cross.py` (raccolta) e
`srum_emi_perminute.py` (confronto a finestra identica, calcolato DOPO sui file
gia' scritti). Artefatti: `srum_emi_cross_20261023_130553.{json,csv}`,
`srum_emi_cross_20261023_130553_buckets.csv`, `srum_cross_v2_console.txt`,
`srum_emi_perminute_20261023_130553.{json,csv}`.

## 1. Perche' SRUM, e cosa NON e'

`powercfg /srumutil` (System Resource Usage Monitor) dumpa l'archivio con cui
Windows stesso registra il consumo: e' scritto dal SO, non da un assembly
terzo, e — punto decisivo — i suoi domini CPU li popola leggendo i **contatori
EMI**, gli stessi del mio lettore ctypes. Lo verificato riga per riga sul dump
`srum_dump_20261023_121718_start.csv` (34156 righe): i 596 valori non-zero di
`EmiEnergyConsumption` sono TUTTI gli pseudo-AppId `EMI_RAPL_Package0_PKG` /
`_PP0` / `_PP1`, con `CPUEnergyConsumption = 0` e `Emi == Total`.

Quindi SRUM **non e' un arbitro indipendente della scala**: e' un secondo
consumatore dello stesso dominio. Serve pero' a un altro scopo, ed e' lo scopo
di questo esperimento:

* valida la MIA decodifica (layout dei record, fattore `pWh`, natura cumulativa)
  contro la decodifica di Microsoft degli stessi contatori, su un canale che non
  passa dal mio ctypes;
* e' il quarto testimone che la potenza di package del 13900HK a lavoro reale e'
  ~11-29 W, non 70-99 W: l'assoluto LHM resta impossibile (PL1 35 / PL2 55 W
  OEM, `experiment_results/hwinfo_idle_20261023_011237.csv` colonne 228-231).

Il campo **per-processo** di SRUM (`CPUEnergyConsumption` rigato per appId) e'
invece il modello EPI di Windows: attribuzione, non misura. Lo uso solo come
confronto fra due attribuzioni (§6), mai come evidenza hardware.

## 2. Protocollo e correzioni rispetto alla v1

Fasi: idle 120 s → load 600 s (Ollama, `num_predict` 32, 7456 token) → idle2
120 s; `SETTLE_S = 75` per far scaricare il modello dal buffer di scrittura;
poller EMI laterale a 5 s (tick reale ~6,6 s, costo del poll). Tre difetti
della v1 (`srum_emi_cross_20261023_121718.*`, INVALIDATA) corretti:

1. **`TimeStamp` = UTC naive**, non orario locale: interpretandolo locale la
   finestra risultava vuota per 2 ore (offset macchina 2:00:00, misurato).
2. **compattazione oraria**: i bucket da minuto vengono fusi in un record ORARIO
   a ogni boundary di epoch, misurato alle :32. Il dump del confine di fase
   successivo al boundary non contiene piu' i minuti inglobati — la v1 ha perso
   l'intera fase di load (`bucket_nella_finestra = 0`). V2: dump **a ogni confine
   di fase** e conteggio solo delle righe mai viste (dedup per firma esatta
   `appId+timestamp+ms+cpu+emi+total`).
3. **righe complementari**: lo stesso minuto puo' essere scritto come due righe
   (misurato 10:02 → `TimeInMSec` 26593 + 33399 = 59992). V1 filtrava "corte";
   V2 tiene `0 < ms <= 70000` e verifica la completezza per minuto.

Due bug del harness, entrambi con prova:

* `cpu_seconds_of()` faceva `.get` sul `pcputimes` namedtuple di psutil →
  AttributeError; e' un namedtuple, si indicizza.
* il needle `"ollama"` non intercettava il worker reale `llama-server.exe`: da
  qui il `cpu_time_share_ollama_misurata = 0,001` ancora stampato nel JSON v2
  (riga `confronto`, NON corretta a posteriori per non riscrivere un dato
  grezzo). Misura diretta in `cpu_share_check.py` (§6).

Unita' SRUM: `EmiEnergyConsumption` in **millijoule**, confermato due volte —
sul run 12:17 (rapporto SRUM/EMI = 0,9985 sd 0,0076) e qui al §3 (rapporti
0,81-0,98 su intervalli diversi). Se fosse joule il rapporto sarebbe ~1e-3.

## 3. Risultato principale: potenze di fase

PKG = dominio di package. `SRUM_W` calcolata su `TimeInMSec` dei bucket,
`EMI_W` sui secondi del meter (finestre proprie, dichiarate in `granularita'`).

| fase | minuti SRUM | copertura SRUM s | EMI W (PKG) | SRUM W (PKG) | rapporto |
|---|---|---|---|---|---|
| idle | 4 | 240 | 23,25 | 18,865 | 0,8114 |
| load | 11 | 660 | 28,27 | 26,794 | **0,9478** |
| idle2 | 3 | 180 | 11,45 | 11,225 | **0,9803** |

Stesso quadro per gli altri due domini: PP0 0,9371 (load) e 0,9688 (idle2);
PP1 1,0294 e 0,9818. Il DRAM di EMI resta 0,00 W (canale morto, gia' visto).

L'`idle` NON e' unidle reale: la fase copriva il warm-up (modello in caricamento
e browser attivo), e i suoi 4 bucket SRUM coprono 240 s contro 120 s di meter.
E' il motivo dell'0,8114, non un problema di unita'.

## 4. Pairing a finestra identica (`srum_emi_perminute.py`)

Per togliere il difetto delle finestre diverse: per ogni minuto SRUM completo si
prendono i 60 s esatti del contatore EMI, con il valore interpolato linearmente ai
confini. Su PKG, fase di load:

| minuto UTC | SRUM W | EMI W | rapporto |
|---|---|---|---|
| 11:10 | 22,569 | 27,503 | 0,8206 ← confine (load parte 11:09:15) |
| 11:11 | 27,485 | 28,561 | 0,9623 |
| 11:12 | 28,553 | 29,057 | 0,9827 |
| 11:13 | 29,044 | 28,477 | 1,0199 |
| 11:14 | 28,472 | 28,568 | 0,9966 |
| 11:15 | 28,534 | 28,643 | 0,9962 |
| 11:16 | 28,694 | 28,484 | 1,0074 |
| 11:17 | 28,436 | 28,515 | 0,9972 |
| 11:18 | 28,550 | 28,701 | 0,9947 ← confine |

nove coppie: media **0,9753** sd 0,0601. Esclusi i due minuti di confine (quelli
che contengono un cambio di regime), sette minuti interni: media **0,9946**,
deviazione massima da 1 **0,0377** (3,8%). idle2: un minuto accoppiato, 0,9627.
L'idle non da' coppie: l'asse EMI finisce alle 11:07:57, prima del secondo
confine di minuto utile.

**Verdetto sul §3+§4: la decodifica EMI di CasualWatt (layout, pWh,
cumulativita') coincide con quella di Windows a ±4% su finestre di 60 s
identiche.** Non e' una validazione indipendente del numero — e' la stessa
sorgente letta da due parser; pero' esclude che il mio ctypes sbagli unita' o
letture, che era il dubbio aperto dopo i quattro way.

## 5. Differenziale e J/token dalle due sorgenti

Convenzioni identiche (stesso `meter_s` 601,17 e stesso token count 7456), dal
blocco `differenziale_due_sorgenti` del JSON:

| baseline | EMI dP W | EMI J/token | SRUM dP W | SRUM J/token | rapporto |
|---|---|---|---|---|---|
| media A−B | 10,92 | **0,8805** | 11,749 | **0,9473** | 1,076 |
| solo B (idle2) | 16,82 | 1,3562 | 15,569 | 1,2553 | 0,926 |

Due letture oneste: (a) la potenza istantanea coincide al 4%, il **differenziale
no** (±8%), perche' il differenziale dipende dalla baseline e le due baseline
non sono lo stesso intervallo di tempo; (b) lo J/token locale vive in una banda
0,88–1,36 a seconda della finestra di riferimento, coerente con la banda storica
EMI 0,833–1,173 (5 test dell'utente + due four-way). Non esiste "il" J/token:
esiste il J/token di un protocollo, e la scelta della baseline va dichiarata
come parametro, non come dettaglio.

## 6. Attribuzione per-processo: SRUM (EPI) contro CPU-time

`SRUM_ollama_share_of_cpu_load = 0,7361`: la frazione di energia CPU che il
modello EPI di Windows assegna all'albero Ollama (llama-server.exe + ollama.exe
+ ollama app.exe) nel load; prima voce `top_cpu_mJ` = llama-server.exe 9386,89
mJ su 12858,58 totali. `cpu_share_check.py` misura il denominatore reale in tre
finestre da 60 s (Ollama sotto le stesse richette `num_predict` 32):

| run | finestra s | CPU-s albero | busy s | share busy | share su tempo totale |
|---|---|---|---|---|---|
| 13:45:30 | 62,0 | 610,56 | 844,02 | 0,7234 | 0,5021 |
| 13:47:43 | 61,4 | 607,09 | 827,17 | **0,7339** | 0,5021 |
| 13:32:35 | 61,6 | 608,06 | — | — | 0,5014 |

**0,7339 (tempo kernel reale, run migliore) contro 0,7361 (modello EPI):
differenza 0,0022, 0,3%.** Il run 13:32 e' precedente alla correzione del
denominatore e resta su disco senza i campi busy; il numero "0,50" e' la stessa
quota divisa pero' per i core-secondi TOTALI, che includono `System Idle
Process` (PID 0, ~409 s su 20 nuclei in 61 s): non e' lavoro, e infatti non e'
confrontabile con SRUM. `completitudine_denominatore = 0,9847` (19,69 core-s/s
su 20) dichiara che la somma dei processi visibili copre il 98% del tempo di
sistema, quindi il denominatore non e' bucherellato da AccessDenied.

Utile ma con il caveat dichiarato: e' un confronto tra due attribuzioni dello
stesso stimolo, non una validazione di una delle due contro l'hardware. E
conferma cio' che la metodologia gia' esclude: l'energia CPU durante
l'inferenza e' ~ tre quarti dell'albero Ollama, ma la sua quota NON e'
misurabile per-PID — l'hardware conta per package/domain. Il vecchio needle
`"ollama"` dava 0,0011 (run 13:47: 1,36 CPU-s su 607), cioe' attribuiva all'LLM
un millesimo: da qui la correzione `NEEDLES = ("ollama", "llama-server")`.

## 7. Cosa vale e cosa non vale per la tesi

Vale: (1) la decodifica EMI di CasualWatt e' coerente con quella di Windows
(±4% a finestra identica, n=7-9); (2) l'assoluto EMI ~11-29 W e' confermato da
una seconda implementazione indipendente del parser + HWiNFO + limiti PL;
(3) la scelta della baseline e' un parametro dichiarato dello J/token (±8-30%).

Non vale: (1) SRUM come arbitro della scala (same-counter, regola
[[feedback-keep-current-until-proven]]); (2) il campo per-processo SRUM come
misura (modello EPI); (3) alcunche' sul lato LHM: il difetto del percorso di
lettura resta quello misurato in `lhm_percorso_lettura_20261023.md` §4.1 —
`energy_session.py:819` ritorna la temperatura "CPU Package"
(`IntelCpu.cs:401`, posizione 38 contro il Power in posizione 67) e `_pi_loop`
integra °C·s. SRUM semmai rafforza l'accusa: 28 W reali contro i ~67 "W" integrati.

Non toccato: `cwEnergyModular/energy/energy_session.py`. La correzione minima
richiesta e' una riga (usare solo `sensor is sel`, o imporre anche
`SensorType == "power"`); **non la applico senza autorizzazione esplicita**.

## 8. Riprodurre

```
# raccolta (serve Admin per il dump SRUM; EMI non lo richiede)
powershell Start-Process -Verb RunAs python -ArgumentList 'srum_emi_cross.py'
# analisi a finestra identica: legge solo gli artefatti, senza Admin
python srum_emi_perminute.py 20261023_130553
```

La v1 (`srum_emi_cross_20261023_121718.*`) e i dump grezzi
`srum_dump_20261023_*.csv` restano in `experiment_results/` ma NON committati:
la v1 e' invalidata dal bug di compattazione, i dump pesano 7-8 MB l'uno.
