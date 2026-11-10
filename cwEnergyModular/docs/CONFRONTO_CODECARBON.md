# Confronto con CodeCarbon: assi verificati, limiti e prova a richiesta uguale

Questo documento sostituisce il confronto che sta in `EMInote/`. Quel confronto
partiva da una premessa falsa -- che CodeCarbon stimi il consumo da TDP su
Windows moderno e che CasualWatt "misuri gli elettroni" -- e ne traeva una
superiorita' che il codice non sostiene. Qui il confronto e' rifatto su tre assi
verificati alla fonte, con la dichiarazione esplicita di cosa resta difendibile e
di cosa no.

La conclusione non e' che uno strumento sia migliore: i due stimandi sono
diversi. CodeCarbon risponde a "quanta energia ha assorbito la macchina mentre il
tracker era attivo"; CasualWatt risponde a "quanta energia e' attribuibile a
questa richiesta al netto della baseline". E, su Windows, leggono **lo stesso
contatore**.

## 1. Perimetro e versione verificata

- Pacchetto installato su questo host: **CodeCarbon 3.3.2**, in
  `%LOCALAPPDATA%\Python\pythoncore-3.14-64\Lib\site-packages\codecarbon\`
  (verificato il 05-11-2026 con `codecarbon.__version__`; la stessa 3.3.2 e'
  presente anche in `pythoncore-3.15-64`, l'interprete che la suite risolve oggi,
  riverificato il 10-11-2026). La release 3.3.0, che
  introduce il backend EMI di Windows, e' del **2025-08-04** (PR #1263 di
  `benoit-cty`, mergiata il 2025-08-03). La 3.3.2 e' del 2025-10-23.
  Entrambe le date sono verificate alla fonte su
  [github.com/mlco2/codecarbon/releases](https://github.com/mlco2/codecarbon/releases).
- Gli ancoraggi `file:riga` sotto sono su **3.3.2**, la versione che gira su
  questa macchina. Dove il testo della tesi cita la 3.3.0 le coordinate possono
  differire di qualche riga: il contenuto e' lo stesso, la numerazione no.
- I numeri misurati di CasualWatt citati qui vengono da artefatti tracciati in
  `experiment_results/`; le date sono quelle degli artefatti, non una
  riverifica di oggi.

## 2. Cosa risponde CodeCarbon (lo stimando, prima del merito)

Sul percorso Windows con EMI disponibile, CodeCarbon:

1. apre il device EMI e legge i canali il cui nome contiene `pkg`
   (`core/windows_emi.py:250-252`), con unita' **picowattora** e timestamp in
   unita' da **100 ns** (`core/windows_emi.py:36-44`);
2. somma i soli delta "Processor Energy Delta" dei canali selezionati
   (`external/hardware.py:421-433`), dopo aver deduplicato i contatori speculari
   confrontando i **valori** (`core/rapl.py:31-53`, agganciato a
   `core/windows_emi.py:307-321`);
3. restituisce quell'energia **senza scalarla** alla modalita' di tracciamento:
   `measure_power_and_energy` sul ramo `windows_emi` chiama
   `_get_energy_from_cpus` e torna (`external/hardware.py:465-472`). Il
   `tracking_mode` entra in gioco solo nel percorso `cpu_load`
   (`external/hardware.py:319-368`);
4. aggiunge due termini che non vengono dal contatore: la **RAM**, modellata per
   numero di DIMM a 5 W ciascuna con minimo 2 DIMM su x86
   (`external/ram.py:15-16`, `:164-171`; la "3 W ogni 8 GB" e' l'euristica
   pre-v3, citata solo nella docstring `:21-23`), e la **GPU**, a livello di
   device;
5. espone le componenti separate -- `cpu_energy`, `ram_energy`, `gpu_energy` --
   in `EmissionsData` (`output_methods/emissions_data.py:22-24`), popolate in
   `emissions_tracker.py:1159-1161`.

Default: `tracking_mode="machine"` (`emissions_tracker.py:601`) e
`measure_power_secs=15` (`:585`). Entrambi sono parametri, non costanti: "15 s
rigidi" e' falso, "15 s di default" e' vero.

Il punto che conta per il confronto: **il canale CPU di CodeCarbon e' lo stesso
registro che legge CasualWatt**, `MSR_PKG_ENERGY_STATUS` (0x611; nel nostro
sorgente `energy/emi_backend.py:9-11`, nel loro `core/windows_emi.py:36-44`).
Un accordo fra i due numeri e' quindi **coerenza di implementazione**, non una
validazione indipendente. La scala assoluta resta non arbitrata senza un
wattmetro AC/DC esterno.

## 3. I tre assi verificati

### 3.1 Baseline: assente

Nel pacchetto 3.3.2 le parole `idle` e `baseline` compaiono **5 volte** in tutto
il codice Python: 4 `baseline`, 1 `idle` (contato con
`grep -riw --include=*.py` il 10-11-2026, uguale sui due interpreti installati).
Nessuna e' una sottrazione della potenza di riposo:

| occorrenza | cos'e' |
|---|---|
| `external/hardware.py:71` | `times.idle` di psutil: tempo CPU inattivo, usato per il tempo *busy* nel ramo `process`/`cpu_load` |
| `external/hardware.py:37`, `:39` | la baseline interna di `psutil.cpu_percent(interval=None)`, cioe' il punto di partenza di una misura di carico |
| `core/rapl.py:134` | "no baseline to compute a delta from": il valore precedente del contatore, non una potenza idle |
| `core/gpu_device.py:181` | "no baseline yet": il contatore GPU comparso dopo l'avvio |

Il modello `cpu_load`, quando il contatore non e' accessibile, ha un pavimento
fisso al 10% del TDP (`load_factor = 0.1 + 0.9 * load**3`,
`external/hardware.py:319-327`): quello e' l'unico termine che assomiglia a un
idle, ed e' un'assunzione sul TDP, non una misura. Sul percorso EMI non entra.

**Conseguenza, quantificata sui nostri dati.** Sul protocollo v3 post-fix (8 run
x 15 inferenze; valori medi **per run**,
`experiment_results/lhm_validation_v3_postfix_20261023_analisi.md:20-24`):
`E_inc = 1778,7 J`, `P_base = 11,55 W`, `P_load = 28,33 W`, quindi
`dt_W = E_inc / (P_load - P_base) = 106,0 s`, `E_gross = 3003 J`,
`E_idle = 1224 J`. La baseline e' il **40,8% dell'energia lorda**. CodeCarbon,
sullo stesso intervallo e sullo stesso canale, riporterebbe il lordo: il 41% del
suo numero non e' del carico. A questo va aggiunto il termine RAM modellato
(>= 10 W su x86 con 2 DIMM), che non e' un contatore.

Non e' un errore di CodeCarbon: e' lo stimando che ha scelto. Diventa un errore
solo se il suo numero viene presentato come "energia della richiesta".

### 3.2 Segno: i delta negativi si scartano

CodeCarbon accetta solo delta non negativi su EMI e, quando il delta e' negativo,
**salta il campione** dichiarandolo nel log:
`if delta_pwh >= 0 and delta_time_s > 0` ... `else: "Skipping negative delta"`
(`core/windows_emi.py:544-555`). Sul percorso RAPL prova prima a correggere un
avvolgimento con `max_energy_reading` e, se il contatore e' ancora indietro,
salta anche quello (`core/rapl.py:136-152`). Sulla GPU, contatore che torna
indietro -- ricarica del driver o reset -- fa scattare il fallback a potenza
integrata e riconcilia dopo (`core/gpu_device.py:189-198`).

CasualWatt conserva l'incremento **firmato** e lo dichiara: `package_energy_j` e
`package_energy_raw_j` prendono lo stesso valore firmato
(`energy/local_energy.py:629-630`), `active_energy_j = active_energy_raw_j`
(`:646-648`), e un delta negativo arriva alla riga con `active_valid = False`
(`:766-771`) e la nota che lo nomina (`:772-777`). Una finestra con i due bordi
sullo stesso record diventa `counter-invalid` (`:489-501`, dove
`ts_edge1 <= ts_edge0`), non zero; il ramo gemello per il delta negativo ai
bordi sta a `:464-471`. Regola: nessun troncamento.

**Conseguenza.** Dopo un reset del contatore i due strumenti danno numeri diversi
per costruzione: CodeCarbon sottostima in silenzio (quel tratto vale 0), noi
riportiamo un negativo con un flag. La differenza e' visibile solo in presenza di
un reset o di un avvolgimento. **Non e' dimostrabile con una prova a richiesta
uguale**: servirebbe indurre un reset, che non facciamo.

### 3.3 Risoluzione: il 15 s non e' un quanto

Il punto su cui il confronto precedente sbagliava di piu'. `measure_power_secs =
15` e' l'intervallo con cui il thread di monitoraggio legge il contatore, non la
granularita' dell'energia: l'energia e' la differenza di un contatore
**cumulativo** fra due letture, quindi i delta intermedi si sommano e il totale
su una finestra chiusa e' la differenza ai bordi. Un intervallo di 15 s non
"perde" energia; perde la capacita' di **attribuirla dentro** l'intervallo.

Sull'altro lato, i 0,05 s di CasualWatt non sono una risoluzione migliore del
contatore:

- il registro EMI non e' quantizzato sopra i 10 ms: su 11.192 transizioni
  consecutive, **0 timestamp identici** e 4 valori duplicati (0,036%), e nelle
  sonde a 50 ms 0 duplicati su 1.600 letture
  (`experiment_results/emi_cadenza_distribuzione_20261023.md:9-19`, `:22-33`,
  `:74-81`);
- `EMI_SAMPLE_INTERVAL_S = 0.05` (`energy/energy_session.py:107`) e' la cadenza
  del **buffer di bordo**: serve a leggere il contatore vicino ai bordi della
  finestra, non a campionare piu' finemente di CodeCarbon;
- il buffer ha un costo: in spin a 20 Hz l'intervallo misurato passa da 0,0506 a
  0,0770 s, +52% (`emi_cadenza_distribuzione_20261023.md:85-99`). Il documento
  stesso precisa che l'effetto sul **numero** di finestra e' nullo -- la finestra
  e' il delta del cumulativo ai bordi, non la somma dei campioni -- ma il costo
  di osservazione esiste e va dichiarato. CodeCarbon a 15 s o a 1 s costa meno.

**Conseguenza.** Sull'energia totale di una richiesta delimitata i due metodi
possono dare lo stesso numero, e devono: stesso contatore, stessa finestra. La
differenza reale e' (a) dove cadono i bordi, (b) cosa si sottrae dentro la
finestra, (c) se si puo' spezzare la finestra in fasi. Il punto (c) -- TTFT
contro generazione -- **non e' implementato** oggi: e' il punto 4 del backlog ed
e' successivo a P6.

## 4. Cosa resta difendibile, e cosa no

Difendibile, con ancoraggio:

- **Attribuzione alla richiesta**: finestra delimitata dalla richiesta, non dal
  ciclo del tracker; baseline `P_pre` misurata su tre finestre da 30 s, mediana
  (`energy/energy_session.py:1561`), con provenienza in `idle_provenance`
  (`energy/local_energy.py:166` la dichiarazione, `:395-418` la scelta del
  valore) e sottrazione firmata (`:643-648`).
- **Segno conservato e dichiarato** (sezione 3.2).
- **Catena di fallback corta e scritta per riga**: `emi-counter`, poi
  `pawnio-counter`, poi `unavailable`; `package_window_source` dice quale
  percorso ha prodotto il numero (`exact-counter | samples-fallback |
  counter-invalid | unavailable`, `:163-165`). PawnIO e' un fallback sullo
  **stesso** registro, non un secondo canale e non una validazione.
- **Bordi letti senza interpolazione quando il buffer copre**: differenza del
  contatore ai bordi (`energy/energy_session.py:1237` e seguenti).
- **Criterio di stabilizzazione esplicito** (`settle_idle`, `:1442`) e baseline
  calibrata (`calibrate_idle`, `:1561`; GPU, `calibrate_gpu_idle`, `:1660`),
  separati: stabilizzare non e' calibrare.

Non difendibile, e da togliere dai documenti:

- **"Misura gli elettroni" / validazione indipendente**: stesso registro 0x611.
  Un accordo e' coerenza, non arbitraggio della scala.
- **"Risoluzione 0,05 s" come superiorita'**: e' cadenza di bordo, e costa
  (sezione 3.3).
- **"Separazione TTFT"**: non implementata.
- **"CodeCarbon non vede `llama-server`"**: in `machine` mode lo vede, perche'
  misura la macchina intera. Quello che non fa e' attribuire alla richiesta e
  sottrarre la baseline. In `process` mode su EMI, come verificato nella
  sezione 2 (punto 3), il numero e' comunque quello della macchina: e' il
  documento di CodeCarbon a
  promettere l'isolamento, non il codice a realizzarlo su questo percorso.
- **"CodeCarbon stima da TDP"**: vero solo quando nessun contatore e'
  accessibile. Su questo host, con EMI disponibile, usa il contatore.
- **"Il nostro dedup e' migliore del loro"**: non e' vero in un caso. Noi
  leggiamo una volta i canali PKG **omonimi** e rifiutiamo come
  `ambiguous_domain` piu' canali PKG con nomi distinti
  (`energy/emi_backend.py:233-235`, `:252-260`); CodeCarbon riconosce i
  contatori speculari confrontando i **valori** (`core/rapl.py:31-53`), quindi
  copre anche nomi diversi per lo stesso contatore di socket. Su un multi-die
  con nomi per-die il loro criterio e' piu' generale del nostro; il nostro, se
  non riconosce, si ferma invece di sommare. Sono due scelte diverse, non un
  punto a favore.

Confine dichiarato: **la RAM non la misuriamo**. Leggiamo il dominio DRAM dove
il driver lo espone (spesso 0 su host client) e non modelliamo le DIMM. CodeCarbon
la modella. Chi confronta i totali deve confrontare `cpu_energy`, non
`energy_consumed`.

## 5. Cosa buttare dei documenti `EMInote/`

| affermazione nei documenti vecchi | verdetto | correzione |
|---|---|---|
| "CodeCarbon stima la CPU dal TDP" | falso su questo percorso | contatore EMI quando disponibile; TDP solo se nessun contatore |
| "Intervalli rigidi da 15 s" | impreciso | default configurabile; l'energia e' un delta di contatore cumulativo |
| "Campionamento a 0,05 s = risoluzione superiore" | falso come formulato | cadenza dei bordi; il registro non quantizza sopra 10 ms; l'energia totale non migliora |
| "Separazione TTFT dalla generazione" | non implementato | punto 4, dopo P6 |
| "Attribuzione proporzionale che sottrae i picchi" | invenzione | in CodeCarbon non esiste alcuna sottrazione di idle |
| "`settle_idle` = mediana su 3 x 30 s" | confusione | `settle_idle` e' il criterio di stabilita'; la baseline e' `calibrate_idle` |
| "Non vede il demone Ollama ne' i runner figli" | falso in `machine` mode | li vede nella macchina; manca l'attribuzione alla richiesta |
| "3 W ogni 8 GB di RAM" | euristica pre-v3 | v3: 5 W per DIMM, minimo 2 DIMM su x86, modello |
| "PawnIO aggiunge un secondo canale / valida EMI" | falso | fallback sullo stesso registro; nessuna somma, nessuna validazione |

## 6. La prova a richiesta uguale: decisione e disegno

**Decisione: si propone, con il criterio di utilita' scritto prima.**
Raccomandazione: farlo, perche' costa poco e chiude la sezione con un numero;
ma non e' necessario agli assi. I tre assi della sezione 3 sono letti nel
sorgente e ancorati, e il run non dimostra una superiorita' ne' scopre nulla che
il codice non dica gia'. Serve a due cose piu' modeste:

1. verificare sullo strumento vero che il 15 s non e' un quanto (telescoping) e
   che su EMI `machine` e `process` danno lo stesso numero -- cioe' a esporre
   il nostro stesso codice a una confutazione;
2. misurare, invece di calcolare, la decomposizione `E_CC - E_CW ≈ P_pre*dt_W`,
   che oggi e' un'identita' algebrica sui dati v3.

Se il numero misurato non serve al testo, il run si puo' non fare: il documento
resta valido con la sola lettura del sorgente. Non puo' mostrare l'asse del segno
(serve un reset) ne' la scala assoluta (serve un wattmetro).

### Disegno

Stessa richiesta, stesso modello, stessa temperatura (0), stesso `keep_alive`
numerico e dichiarato, modello gia' caldo. Quattro bracci, tre ripetizioni,
**interleaved** (C1 C2 C3 C4, tre giri) per distribuire la deriva:

| braccio | strumento | configurazione |
|---|---|---|
| C1 | CasualWatt | EMI, `E_net` con `P_pre` da 3 x 30 s prima; bordi ai marcatori della richiesta |
| C2 | CodeCarbon | `tracking_mode="machine"`, `measure_power_secs=15` (default), `offline=True`, `country_iso_code="ITA"` |
| C3 | CodeCarbon | come C2 ma `measure_power_secs=1` (non-default, dichiarato) |
| C4 | CodeCarbon | `tracking_mode="process"`, `measure_power_secs=15` |

Per ogni braccio si legge `final_emissions_data.cpu_energy` (kWh), `duration`,
`tracking_mode` e, separatamente, `ram_energy`; il confronto e' su `cpu_energy`.
I bracci sono sequenziali: due letture simultanee dello stesso contatore si
disturbano.

### Predizioni, dichiarate prima del run

1. **Telescoping**: `|E_C2 - E_C3|` piccolo rispetto ai due valori. Soglia
   dichiarata ora: **2% della mediana**, che a ~28 W corrisponde a circa 0,15 s
   di disallineamento dei bordi -- l'ordine di grandezza dello start/stop, non
   una differenza di metodo. Se la supera, il problema e' nell'arnese: ci si
   ferma e si riporta, senza spostare la soglia.
2. **Decomposizione**: `E_C2 - E_C1 ≈ P_pre * dt_W`, entro il budget combinato.
   E' l'unica affermazione di sostanza.
3. **Modalita'**: `E_C4 ≈ E_C2` su EMI. Uno scarto sistematico
   contraddirebbe la lettura del codice e andrebbe spiegato, non assorbito.
4. **Coerenza, non validazione**: `E_C2` e il lordo di CasualWatt sulla stessa
   finestra devono coincidere entro il rumore. Se coincidono, il numero e'
   coerente fra due implementazioni dello stesso registro; non e' validato.

### Criteri e dichiarazioni

- Se `windows_emi.is_emi_available()` e' falso, il braccio CodeCarbon e'
  **non disponibile e si dichiara tale**: **non** si ripiega sul modello
  `cpu_load`, che produrrebbe un numero di natura diversa.
- Ogni riga porta il canale e la modalita'; il file di analisi dichiara che il
  contatore e' lo stesso e che la scala assoluta non e' arbitrata.
- Il run **non** cambia il metodo di produzione: confrontare non e' adottare.
- Durata: 12 richieste misurate (9 se C4 resta fuori), piu' 3 di warm-up e 90 s
  di baseline; stimata **8-12 minuti** a seconda della lunghezza della risposta.
  Si esegue solo su via esplicita dell'utente, dichiarando i passi prima.
- Se il run si fa, l'harness e il file di analisi vanno tracciati in
  `experiment_results/` accanto ai dati: un'analisi non tracciata e' un numero
  che nessuno puo' rigenerare.

## 7. Stato

| elemento | stato |
|---|---|
| lettura del sorgente CodeCarbon 3.3.2 sui tre assi | verificata il 05-11-2026, ancoraggi in questo file |
| confronto baseline con i dati v3 (40,8% del lordo) | calcolato su artefatto tracciato, aritmetica dichiarata |
| prova a richiesta uguale (sezione 6) | progettata, non eseguita; richiede via esplicita |
| asse del segno su reset reale | da fare, solo con un reset indotto o osservato |
| scala assoluta del contatore | non arbitrata: serve un wattmetro AC/DC esterno |
| isolamento per processo su EMI | letto nel codice: non viene applicato; il documento di CodeCarbon lo promette |
| RAM | fuori perimetro per CasualWatt; termine modellato in CodeCarbon |

## 8. Dove sta la stessa materia nella tesi

Il capitolo 3 (`Tesi-latex/qoder-bozza/capitoli/cap03_metodologia_misura.tex`,
sezione `sec:codecarbon`) contiene gia' il confronto corretto sull'asse della
baseline, con la tabella `tab:codecarbon-confronto` e il caveat dello stesso
contatore. Restano tre punti da riallineare, e sono **segnalati qui, non
corretti**, perche' `Tesi-latex/` e' fuori da git:

1. la frase "zero occorrenze di `idle` e `baseline`" e' vera per la 3.3.0 ma non
   per la 3.3.2, dove le occorrenze sono 5 (4 `baseline`, 1 `idle`) e nessuna e'
   una sottrazione di idle:
   va riformulata come "nessuna sottrazione della potenza di riposo", che e' il
   claim che regge;
2. gli ancoraggi di riga sono sulla 3.3.0 e vanno etichettati come tali, oppure
   riportati alla 3.3.2;
3. l'equazione `eq:attiva` riporta ancora `E_active = max(E_pkg - P_idle*dt, 0)`,
   che contraddice la regola del segno conservato: va tolta la `max`.
