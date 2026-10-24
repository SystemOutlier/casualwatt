# Valutazione di `alt_lhm.DOCX` (2026-10-24)

Documento valutato: `alt_lhm.DOCX` (root, 23.596 byte, scritto 23/10 22:28),
167 paragrafi estratti con la ricetta zipfile/UTF-8 e letti integralmente.
Titolo: *"CasualWatt — piano per eliminare LibreHardwareMonitor (LHM)"*.

Regola di lettura (memoria `feedback-thesis-stop-and-reason`): il testo è
spunto, non autorità. Ogni sua richiesta qui sotto è **confermata**, **confutata**
o **accettata come lacuna** contro `file:riga` o contro misure eseguite oggi.

## 0. Che cosa è, e cosa non è, questo documento

Il documento stesso lo dichiara (par. 166): l'autore **non ha letto il codice**.
Riceve «EMI è stato implementato e la suite ha superato 77 test con 3 esclusioni»
e scrive esplicitamente di non considerarla «una verifica indipendente» perché il
connettore GitHub non ha risolto il riferimento. È la stessa diffidenza che la
tesi applica agli strumenti che stampano un numero senza confine, quindi è
metodologicamente legittima — e infatti §7 chiede come primo passo un **audit in
sola lettura**, che è esattamente ciò che è stato fatto il 24/10.

Nota di fatto: il numero «77 test» era corretto il 23/10 ed è **superato**. Oggi
la suite è a **98 passati + 3 saltati** (10 test introdotti il 24/10 da
`tests/test_metodo_ammissibile.py`, commit `30ae6ec`, 11 da
`tests/test_metodo_per_riga.py`, commit `b6539e1`). Appendice D della tesi genera
il verbale da raccolta + AST + esecuzione, quindi la cifra non è più una
testimonianza: è riproducibile.

## 1. Richieste già soddisfatte dall'implementazione (confini, non opinioni)

| Richiesta (par. nel DOCX) | Stato verificato |
|---|---|
| «Nessun import obbligatorio di LHM. Il core e l'avvio devono funzionare senza DLL, processi o installazioni LHM» (24) | **Confermato, ora anche a livello di dipendenze.** `import clr` è dentro `try` in `energy/energy_session.py:500` (guardia a :494) e in `diagnostics.py:149,183`; `pythonnet` è uscito da `requirements.txt` ed è ora in `cwEnergyModular/requirements-lhm.txt:19` (commit `6467219`). Probe eseguito oggi, §4 di questo file. |
| «Nessun cambio silenzioso di metodo… il risultato registra quale metodo è stato usato» (26) | **Confermato.** La selezione è ordinata e dichiarata nelle note del backend; dal 24/10 il metodo finisce **nella riga CSV** (`energy_calculation_method`, commit `b6539e1`), non solo nel file di run metadata. |
| «Misure e stime separate… non mescolate con misure dirette in un unico campo ambiguo» (27, §6) | **Confermato per costruzione.** `MEASURED_METHODS` (`energy/energy_session.py:49-50`) ammette a produrre un numero solo i canali che misurano; tutto il resto → `None` → `N/A` nel CSV. Le stime hanno colonne proprie (`network_*`, `cloud_*`) e non entrano in `local_energy_j` (commento «regola 12.1» in `benchmark_unified.py`). |
| «Compatibilità con i dati storici: etichetta originale conservata, niente ricalcoli retroattivi» (28, riga 147 della matrice) | **Confermato dai file.** `results/semantic_evaluation_results.csv` ha 9 righe ferme allo schema di 99 colonne: 4 con `cpu_attribution_method` che inizia per `power-integration`, 5 con `unavailable`; `ensure_header` le migra aggiungendo le 8 colonne mancanti e **conservando pure le 2 non più nello schema** (`semantic_similarity_posthoc`, `semantic_method_posthoc`). Verificato su una copia in `tmp`, non sul file di produzione. |
| «Unità documentate, conversione in joule verificata» (A, 94) | **Confermato.** pWh → J (`3,6e-9`) in `energy/emi_backend.py:25-26`, conversione bloccata da `tests/test_emi_backend.py::test_pwh_to_j_conversion` e corroborata dal cross-check SRUM in `experiment_results/srum_emi_cross_20261023_analisi.md`. |
| «PKG, DRAM, PP0 e PP1 non vengano sommati in modo improprio» (97, e C/76) | **Confermato.** `energy/emi_backend.py:28-31` enuncia la non additività (Beyer & Wendler, LNCS 12079) e i campi si riportano per confronto mai sommati; `energy/local_energy.py:89` marca `igpu_energy_j` come «informativo, MAI sommato». |
| «Verificare il comportamento quando il dispositivo non è presente» (96, matrice riga 135) | **Confermato.** Il device path non è hardcodato ma enumerato via SetupAPI (`energy/emi_backend.py:37-40`); senza driver `available` resta `False` e la misura si dichiara indisponibile (`tests/test_emi_backend.py::test_unavailable_backend_reads_none`). |
| «Valori non monotoni, reset, wraparound gestiti» (A, 72) | **Confermato, con una precisione che il documento non fa.** `emi_window_energy_j` **rifiuta** la finestra su lettura non monotona (`energy/energy_session.py:1065`: `if cb < ca: return None`), invece di correggerla. Il wraparound del contatore non è un caso reale: il registro è uint64 in pWh, quindi un giro completo vale 2^64 · 3,6e-9 = **6,64·10¹⁰ J**, cioè ~70 anni a 30 W costanti. Il rifiuto è la gestione corretta; un "fix" aritmetico del wrap sarebbe una stima inventata. |
| «Confronto fra backend → metodi e domini distinguibili nei risultati» (riga 151 della matrice) | **Non soddisfatto fino a oggi; soddisfatto dal commit `b6539e1`.** Era la lacuna vera, e il documento l'ha individuata. |

## 2. Il nucleo metodologico: le righe 80-82 coincidono con una nostra conclusione

Il passaggio più prezioso del documento non è il piano, è il §«Il punto delicato:
cosa significa accuratezza» (par. 80-82):

1. «Il confronto tra EMI e LHM, se entrambi leggono sostanzialmente lo stesso
   segnale RAPL sottostante, è utile per verificare l'implementazione… ma non
   costituisce una validazione indipendente dell'accuratezza fisica.»
   — **già nostro, e ora dimostrato in modo più forte di quanto il documento
   sappia**: `energy/emi_backend.py:9-11` documenta che entrambi leggono
   `MSR_PKG_ENERGY_STATUS` (0x611), e che LHM lo espone già derivato
   (`IntelCpu.cs:696` = Δ(0x611)/Δt). Il nostro confronto a finestra uguale
   (rapporti 0,9947-1,0082) quindi valida **il parser ctypes**, non la scala.
   La memoria di progetto lo diceva; il documento lo dice dall'esterno.
2. «Un wattmetro alla presa misura un confine energetico diverso dal package.»
   — **confermato**, ed è il motivo per cui il wattometro è in backlog come
   *confine diverso*, non come riferimento di accuratezza.
3. «Non fisserei arbitrariamente una soglia del tipo "errore inferiore al 5%".»
   — **confermato**; la nostra regola è derivare la tolleranza dalla ripetibilità
   misurata (CV 8,99 % sul protocollo v3, §4 dei report `lhm_validation_v3_*`).

Queste tre frasi sono citabili nella tesi come **corroborazione esterna indipendente
del confine di validazione**, non come prova: l'autore non ha visto il codice.

## 3. Lacune vere, non ancora colmate (accettate in backlog)

Contro il contratto comune di §2 (par. 31-52), CasualWatt oggi **non** espone:

- `raw_start` / `raw_end`: i valori grezzi del contatore agli estremi di finestra
  non sono persistiti da nessuna parte (`grep raw_start|raw_end` → nessun
  risultato nel codice). Sono il dato che rende una misura revisionabile: senza,
  `package_energy_j` è un numero che richiede di fidarsi del buffer del contatore
  (cadenza dichiarata 0,05 s in `energy/energy_session.py:97-98`).
- `domain` come campo: il dominio (PKG) vive dentro la prosa di
  `measurement_boundary`. Misurato: la stringa `power-integration` **non compare
  in nessuna delle 9 righe storiche** di `measurement_boundary` (0/9), che contiene
  la descrizione lunga del sensore; il token c'era solo in `cpu_attribution_method`.
- `sampling_interval` **reale**: si registra `interval_s` richiesto
  (`config.py:322` = 0,5 s, e nel boundary «@ 0.5s») e `n_samples_in_window`, non
  la cadenza osservata. Il nostro stesso esperimento ha misurato il thread
  `power-integration` a **0,2803 s contro 0,05 s dichiarati**
  (`POWER_SAMPLE_INTERVAL_S`, `energy/energy_session.py:60`) —
  `experiment_results/observer_cost_20261023_analisi.md:59-61`. È esattamente il
  rischio che il criterio B del documento descrive («registra la cadenza reale dei
  campioni, non soltanto quella richiesta»), e noi l'abbiamo toccato con mano
  senza averlo messo in una colonna.
- `backend_version`: nessuna versione del canale salvata (né la build di
  `LibreHardwareMonitorLib.dll` né il numero del canale EMI/driver).
  `RUN_METADATA_COLUMNS` ha `ecologits_version`, non la versione
  del backend energetico. Il problema è reale e documentato: le righe di
  `IntelCpu.cs` citate vengono dalla sorgente 0.9.6, il runtime distribuito è 0.9.4.
- `quality_flags` strutturato: oggi è la lista `notes`, libera e in italiano.

Nessuna di queste è una correzione da fare a caso: ognuna è una colonna, e una
colonna nuova sposta l'header di un CSV che ha già file storici. Vanno aggiunte
in coda, con la stessa disciplina usata per `energy_calculation_method`, e con i
test di migrazione.

## 4. L'esperimento che il documento chiede e che noi non avevamo ancora fatto

Fase 4 della matrice (riga 145): «Dipendenze LHM rimosse → avvio e test senza LHM
installato». `pythonnet` è installato nella macchina di sviluppo, quindi il
requisito non era mai stato **verificato**, solo dichiarato. Eseguito oggi con un
`sys.meta_path` blocker che fa fallire `import clr`/`pythonnet` come in un ambiente
pulito (da `cwEnergyModular/`, interprete reale):

```python
BLOCCATI = {"clr", "pythonnet", "LibreHardwareMonitorLib"}
class BloccaLHM:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCCATI:
            raise ModuleNotFoundError(f"No module named {name!r}")
        return None
sys.meta_path.insert(0, BloccaLHM())
```

Output reale, non simulato (il contatore è quello del processore; la terza riga è
una finestra idle ripetuta tre volte di seguito nella stessa sessione):

    import del core (benchmark_unified): OK, senza clr ne' pythonnet
    source_method     : emi-counter
    clr in sys.modules: False
    nota backend      : metodo principale 'emi-counter': contatore package cumulativo (pWh) letto via
    finestra 1       : 54.0342 J / 4.0002 s = 13.51 W | emi-counter | exact-counter | 7 campioni
    finestra 2       : 52.3149 J / 4.0100 s = 13.05 W | emi-counter | exact-counter | 8 campioni
    finestra 3       : 49.6556 J / 4.0008 s = 12.41 W | emi-counter | exact-counter | 7 campioni
    P_idle            : None | idle_provenance: None
    diagnostics.py    : importabile senza clr

`P_idle` è `None` (il profiler la dichiara `0.0` con provenienza `uncalibrated`)
perché il probe non esegue la calibrazione: la baseline non è stata inventata, che
è il comportamento richiesto da §6 del documento. La nota registrata dal backend
dice «LHM non interrogata (fallback automatico solo se il canale EMI manca)».

Le tre finestre idle dicono due cose diverse, e tutte e due favorevoli al
documento. (1) **Funziona senza la libreria**: canale attivo, lettura ai bordi
esatti del contatore, energia di ordine corretto. (2) **Una finestra da 4 s su una
macchina non quietata non è ripetibile**: 13,51 / 13,05 / 12,41 W, scarto 1,10 W
(8,4 % sulla media), in discesa come ci si aspetta se il processo che ha importato
`benchmark_unified` sta scaricando; nelle esecuzioni precedenti dello stesso probe
nella stessa ora i valori singoli sono stati 11,98, 12,27 e 14,35 W. Il confronto
con i fondi di idle del 23/10 (11,92 / 11,07 / 11,29 W su finestre da **89,84 s**,
`experiment_results/observer_cost_20261023_analisi.md:40-42`) non è un confronto di
accuratezza: 4 s a lavoro in corso e 90 s a riposo non sono la stessa quantità.
Proprio per questo il criterio B e la fase 5 del documento sono **giusti e non
ancora soddisfatti**: serve registrate la finestra reale, e serve fissare le
condizioni (numero di richieste, keep_alive, baseline pre/post) prima di chiamare
un J/token un risultato.

Limite di questo probe: blocca l'import, non disinstalla il pacchetto, e gira
sulla stessa macchina con lo stesso driver. Un ambiente davvero pulito (venv
senza `requirements-lhm.txt`) resta da fare; e **non** dimostra l'accuratezza
assoluta, che rimane il buco aperto (§2, punto 1).

## 5. Cosa NON abbiamo accettato: eliminare LHM

La raccomandazione finale del documento (par. 167) è «eliminare LHM dal percorso
di produzione, non sostituirlo con un fallback energetico non validato». La prima
metà è stata **rifiutata per decisione esplicita dell'utente** il 24/10, la seconda
è adottata. Motivi, tutti ancorati a codice:

1. `CW_PRIMARY_CHANNEL=lhm` non è un residuo: è **lo strumento con cui EMI è
   stato validato** (confronto a finestra uguale, `test_emi_backend.py::test_cw_primary_channel_lhm_skips_emi`
   e i report del 23/10). Rimuovere il percorso rende non ripetibile l'esperimento
   che ha prodotto l'evidenza usata per promoverlo, contro la regola
   «attuale finché provato».
2. Il canale iGPU è già spento in produzione quando EMI è attivo:
   `energy/energy_session.py:1637-1638` campiona `CPU Graphics` **solo** se
   `method == "power-integration"` e la libreria è aperta. Eliminare LHM oggi non
   toglie un percorso usado: toglie l'unico campo informativo iGPU esistente.
3. Il costo del tenere LHM era reale ed era **l'ambiguità del suo sensore**, non la
   sua presenza: la selezione per nome (`_select_power_sensor`) matchava l'omonimo
   `Temperature` e integrava gradi come joule, producendo 68/81/96 «W» contro
   14/30/38 di EMI; oggi il tipo del sensore è un filtro esplicito
   (`energy_session.py:841-842`, `!= "power" → continue`, fix `1422d1b`). Con EMI
   principale, inoltre, il probe LHM non parte nemmeno pigramente
   (`energy_session.py:140-148`, `pass` esplicito con il commento «il probe LHM NON
   viene eseguito nemmeno pigramente») e `clr` non è in `sys.modules` (§4). Il
   rischio è quindi già neutralizzato alla radice, e da oggi anche il costo
   percepito (dipendenza resa extra, §1 riga 1).
4. Il documento chiede «backend candidati con test distinti»: EMI e LHM ce l'hanno
   già (`test_emi_backend.py` 12 test sul canale, `test_rapl.py` con skip dichiarato
   su Linux, `test_energy_corrections.py` sul percorso campioni).

## 6. Il piano in 6 fasi (§4 del documento), com'è messo davvero

| Fase | Richiesta | Stato |
|---|---|---|
| 1 | Inventario di import, dipendenze, docs; baseline dei test; verificare che `emi-counter` sia il backend selezionato | **Fatta oggi.** Inventario: grep §1 e §3 (esiti negativi inclusi). Baseline: 98 passati + 3 saltati, commit `6467219`. Backend selezionato: probe §4 su hardware reale, `source_method = emi-counter`. |
| 2 | Test del backend EMI isolato (conversione, bordi, finestre corte, dispositivo assente, domini non sommati) | **Copertura esistente, non scritta come risposta a questo documento.** `tests/test_emi_backend.py` ha 12 test che coprono conversione, priorità/fallback, override, bordi esatti, guards (`None` e non 0 su buffer vuoto o finestra fuori copertura), chiusura. **Manca**: un test che modelli il reset/non monotonia del contatore cumulativo (oggi è solo il rifiuto a :1065). |
| 3 | Rimozione LHM in branch separato | **RIFIUTATA** (§5). Ricevuta in forma diversa: LHM reso **opzionale e dichiarato**, non rimosso (`requirements-lhm.txt`, commenti in `avvia_casualwatt.bat`, `MEASURED_METHODS`). |
| 4 | Regressione multipiattaforma (Windows con/senza/dispositivo non leggibile, Linux con/senza RAPL, ambiente pulito senza DLL) | **Parziale.** I rami Windows e Linux hanno test; `test_rapl.py` fa **skip dichiarato** su Windows (non un verde falso). **Non fatto**: ambiente senza `pythonnet` installato (§4 lo simula, non lo installa) e Windows *senza* driver EMI (macchina con solo LHM). |
| 5 | Validazione su hardware reale con modello/token/keep_alive fissati, baseline pre e post, ripetizioni e intervalli | **Il punto più debole nostro, e il documento lo centra.** `keep_alive` è ora dichiarato (`keep_alive_sent`, `ollama_keep_alive`) ma **mai stato inviato** fino a D1, quindi le righe storiche hanno baseline non controllata; il protocollo v4 a numero di richieste fisso non è girato; la baseline pre/post non è nel verbale. I J/token di v2 e v3 **non sono confrontabili** tra loro (0,9873 vs 1,2862) e vanno dichiarati come tali. |
| 6 | Audit finale, dati storici conservano il metodo, licenze delle dipendenze **effettivamente distribuite**, approvazione esplicita prima del merge | **In corso.** Licenze: `LibreHardwareMonitorLib.dll` = MPL-2.0 verificata sul `LICENSE` upstream (README, commit `5b17e98`); restano da ri-verificare `HidSharp.dll` e `Microsoft.Win32.TaskScheduler.dll` prima di qualsiasi ridistribuzione. Le DLL sono ancora **distribuite nel repo** (1,3 MB, 6 file tracciati) benché non caricate con EMI attivo: il documento chiede coerenza fra dipendenze dichiarate e distribuite, e su questo ha ragione; rimuoverle è una decisione che serve solo se si ridistribuisce. |

## 7. Conseguenze eseguite (tutte committate, nessuna spinta)

| # | Azione | Commit |
|---|---|---|
| 1 | `rapl` mancava dalla whitelist dei metodi ammessi: su Linux `judge_energy_j` sarebbe stato `N/A` con un contatore funzionante. Lista unica `MEASURED_METHODS` accanto a chi produce i valori + 10 test parametrizzati | `30ae6ec` |
| 2 | `pythonnet`/`wmi`/`pywin32` fuori dall'installazione obbligatoria, extra `requirements-lhm.txt` dichiarato, README corretto (incluso un claim falso su `codecarbon` scritto e confutato lo stesso giorno: è importato solo da `four_way_test.py:259`, dentro `try`), commento in `avvia_casualwatt.bat` senza cambiare comportamento | `6467219` |
| 3 | `energy_calculation_method` nella riga CSV (canale del package per riga) + 11 test + migrazione verificata su un CSV storico reale + test di congelamento dell'ordine riscritto come lista (gli indici negativi obbligavano a riscrivere 8 asserzioni a ogni colonna nuova) | `b6539e1` |

Backlog che questo documento ha reso esplicito (in ordine di utilità, non di
facilità): colonne `raw_start`/`raw_end`/`domain`/`cadenza_osservata_s`/
`backend_version` con i relativi test di migrazione; test di reset del contatore;
protocollo v4 a numero di richieste fisso con geometria `a·N_in + b·N_out` e
`keep_alive` dichiarato; baseline pre/post con criterio di instabilità; ambiente
venv senza `pythonnet`; macchina senza driver EMI; dual-boot Linux/RAPL con CEM e
pyJoules come secondo lettore; wattometro come *confine diverso*.

## 8. Che cosa questa valutazione non stabilisce

Non stabilisce che i joule di CasualWatt siano giusti. Stabilirlo richiederebbe un
lettore indipendente dello stesso dominio, che oggi non esiste: SRUM decodifica lo
stesso contatore (`srum_emi_cross_20261023_analisi.md`, accordo 0,9946), LHM legge
lo stesso MSR, Task Manager/PDH/CodeCarbon non arbitrano, HWiNFO ha `err=2` sulla
Shared Memory. Il contributo del documento è esattamente questo: dice con chiarezza
che la coerenza fra due lettori dello stesso segnale è **validazione
dell'implementazione**, e che finché non c'è un confine diverso la scala assoluta
resta un limite dichiarato, non un risultato.
