# AGENTS.md — regole vincolanti per chi lavora in questo repository

CasualWatt misura l'energia di una singola inferenza LLM locale su Windows,
leggendo il contatore energetico del package CPU. Il repository contiene insieme
il codice di produzione, i dati sperimentali e una tesi di laurea; le regole qui
sotto esistono perche' ognuna di esse corrisponde a un errore gia' commesso o a
una decisione gia' presa e documentata.

I numeri e gli ancoraggi di questo file sono verificati al **24-10-2026**; i tre
conteggi (suite di test, script `.py` di radice, file di `experiment_results/`) sono
riverificati al **26-10-2026** perche' erano stantii, e il conteggio della suite
e gli ancoraggi di `local_energy.py`/`energy_session.py` sono riverificati al
**27-10-2026** dopo l'uscita di LHM dall'implementazione (D18, 8 test rimossi) e
di nuovo al **28-10-2026** dopo NVML, AMD SMI, le tre colonne per token, il
controllo di timestamp del contatore AMD, il fallback `pawnio-counter` e il flag
`external_counter` (D14). Il conteggio della suite, le righe dei tre schemi CSV
e le coordinate dei campi di `local_energy.py` sono riverificati al
**02-11-2026** dopo `cd881e6b` (provenienza dei token ed energia firmata) e
`9fa9a44c` (finestre con contatore incoerente non valide): la suite e' a **528**
e `CSV_COLUMNS` a **174** nomi. Il conteggio della suite e le coordinate dei
nuovi helper GPU di `energy_session.py` sono riverificati al **03-11-2026** dopo
la selezione del dispositivo GPU (13 test nuovi, `482 + 59 = 541`): `CSV_COLUMNS`
resta a **174** nomi perche' la selezione passa per `notes`, non per una colonna.
Il **04-11-2026** e' riverificato il pacchetto di ancoraggi che la tesi cita dallo
`schema CSV` in poi (nomi e righe di `casualwatt_csv_export.py`, durate di fase,
scorporo del giudice, enumerazione per richiesta, salto del ramo cloud, template
di record) e la suite produce gli stessi **541** node id (`538 + 3`); con l'ingresso
del criterio robusto del valutatore (`cf6aca71`, `6b1dccb8`), lo stesso giorno, la
raccolta e' a **577** node id (`574 + 3`), 482 in `tests/` e 95 alla radice; sulla
selezione GPU la docstring di `_open_gpu_monitor` ora dice cosa arriva davvero nella
riga --
`gpu_device_index` e la nota in `notes` -- perche' `device_selection` e' un
attributo del monitor, letto dai test, e non finisce nel CSV. Nello stesso giorno
il conteggio dei file tracciati sotto `experiment_results/` e' riverificato a
**219** ($218$ in radice, $1$ in `codecarbon_four_way/`): il $210$ del 26-10 era
stantio di nove file entrati fra il 28 e il 29-10.
Il conteggio della suite e' riverificato la **sera del 04-11-2026**, dopo i tre
interventi di codice che l'audit tecnico dello stesso giorno ha chiesto e che sono
stati applicati come commit separati (`b3b12ffe` registro PKG fermo, `86bba6a8`
delta de-clampato sul percorso a campioni, `4b922db6` ragione dell'N/A per
`gpu_process_energy_j`): la raccolta e' a **587** node id (`584 + 3`), **492** in
`tests/` e 95 alla radice. `CSV_COLUMNS` resta a **174** nomi, perche' nessuno dei
tre tocca lo schema: il primo scrive `counter-invalid` in una colonna che esiste
gia', il secondo cambia il segno di un valore che la colonna gia' accetta, il terzo
passa per `notes`.
La raccolta e' riverificata nella **notte del 04-11-2026** (commit delle 22:04,
22:11, 22:20 e 22:28), dopo i quattro fix minimi chiesti dalla revisione del
valutatore (`98ec5972` tolleranza derivata, `8a91e16c` registrazione degli
argomenti inviati al tool, `40f6c619` declassamento di `acc_comp`, `5f23853d`
incertezza a livello di task): **608** node id (`605 + 3`), **493** in `tests/` e
**115** alla radice. `CSV_COLUMNS` resta a **174** nomi anche qui, per la stessa
ragione: la tolleranza e' un campo del contratto gia' accettato da
`robust_evaluator.validate_contract`, gli argomenti passano per `args` nel passo
gia' presente in `notes`, `acc_comp` si declassa attraverso le note di riga e il
bootstrap aggiunge chiavi al riepilogo JSON, non al CSV. I tre salti **non**
stanno in `test_rapl_zone.py`, come questo file ha affermato fino ad ora: stanno
in `tests/test_rapl.py` (`test_rapl_basic`, `test_rapl_readings`,
`test_rapl_idle_window`, la cui docstring chiede un host Linux; il quarto,
`test_rapl_diagnostics`, passa anche qui). Correzione di un ancoraggio stantio,
rilevata rigenerando l'Appendice D, non cambio di comportamento.
Gli altri due conteggi di quella riga sono riverificati dopo `244d1c2f` (23:05 dello
stesso 04-11, la sonda Monte Carlo di P6.4): gli script `.py` tracciati alla radice
sono **36** (erano 35, e il nuovo e' `montecarlo_protocollo_p64_probe.py`), e i file
tracciati sotto `experiment_results/` sono **220** ($219$ in radice, $1$ in
`codecarbon_four_way/`), perche' lo stesso commit porta la sua analisi accanto alla
sonda. La suite resta a **608**: quel commit non aggiunge test.
Se un ancoraggio non torna, il file e' stantio: va corretto, non ignorato.

Fonti primarie, in ordine di autorita':

1. `experiment_results/protocollo_v4_20261024.md` — decisioni congelate P1-P4,
   formulario consolidato F.0-F.17 e sezione preparatoria P6 (derivata, senza
   decisioni);
2. il codice in `cwEnergyModular/`;
3. gli artefatti tracciati in `experiment_results/`;
4. questo file.

---

## Regole dure

- **Mai `git push`** se non richiesto esplicitamente. Il lavoro e' locale.
- **Mai toccare `.casualwatt_keys.json`**: non crearlo, non leggerlo, non
  scriverlo, non forzarne l'aggiunta, non rimuovere la sua riga da `.gitignore`.
  Al 04-11-2026 **esiste sul disco** in `cwEnergyModular/`, non e' tracciato e la
  sua riga sta in `.gitignore:18`: la regola non cambia, cambia il fatto che la
  frase precedente descriveva.
- **Un commit per punto.** Ogni punto del protocollo congelato, e ogni modifica
  concettualmente unitaria, ha il suo commit con messaggio che dice cosa e'
  cambiato e perche'.
- **Se c'e' un problema, fermarsi.** Riportare il problema invece di aggirarlo.
  Nessun workaround silenzioso, nessun test disattivato, nessuna soglia spostata.
- **Mai `git add -A` ne' `git add .`**: aggiungere i percorsi esplicitamente. Alla
  radice ci sono materiali dell'utente (`.DOCX`, `.txt`), archivi e directory
  sottoposte ad audit che non devono entrare nel repo.
- **Un claim e' valido solo se ancorato**: `file:riga`, artefatto tracciato, o
  fonte esterna verificata alla fonte primaria con la data della verifica. Il
  materiale fornito dall'utente e le descrizioni prodotte da altri LLM sono
  **spunti, non evidenza**: vanno verificati prima di entrare in un documento.
- **Non sostituire il metodo in produzione senza evidenza sperimentale.**
  Tenere l'attuale finche' un esperimento non dimostra che l'alternativa e'
  migliore. Confrontare non significa adottare.

## Stato corrente del lavoro

P1 (baseline), P2 (token e terminazione), P3 (geometria e modello), P4
(incertezza e validazione) e P5 (schema CSV e runner, 2026-10-26) sono
**congelati**. P6 (esecuzione e analisi) e' **aperto**. P6 contiene P6.1
(pavimento di tempo a muro) e P6.2 (obblighi del pilota), derivati, e tre
requisiti adottati come
vincolanti: P6.3 (audit idle), P6.4 (simulazione Monte Carlo) e P6.6 (prova di
attribuzione ripetibile, 2026-10-25, con la banda di concordanza ancora da
congelare prima del primo run).

C'e' una sola eccezione dichiarata al congelamento: la **forma di combinazione**
di `budget_base_w` (quadratura o somma aritmetica) e' una decisione operativa
provvisoria, rinviata ai dati del pilota P2.9 e da chiudere **prima** della
campagna principale (protocollo P1.7, P1.13). La formula non si tocca nel
frattempo.

**Il codice sorgente di produzione e' sbloccato dal congelamento di P5**
(2026-10-26): la v4 si implementa contro il protocollo congelato, non contro la
descrizione che ne dava questo file. Lo stato aggiornato e' nella tabella in
testa al protocollo, non qui.

---

## Metodologia congelata

Le formule sono tutte in `protocollo_v4_20261024.md`, sezione *Formulario
consolidato* (F.0-F.17), con applicazione e giustificazione per ciascuna. Qui
stanno solo le regole che un agente puo' violare senza accorgersene.

- **Nessun fallback silenzioso.** La catena locale e' corta e va dichiarata: su
  Windows il contatore EMI (`emi-counter`), poi il contatore MSR del package
  letto via PawnIO (`pawnio-counter`, fallback dichiarato dal 28-10-2026), poi
  `unavailable`. LibreHardwareMonitor e' fuori dall'implementazione dal
  2026-10-27 (D18, metodo provato e superato) e non torna; su Linux i contatori
  RAPL. `CW_ENERGY_FILE` (DEV/TEST) ha precedenza su tutto. Non esiste piu'
  `CW_PRIMARY_CHANNEL`. **Il fallback non e' un secondo canale da sommare ne' una
  validazione di EMI**: `0x611` e `0xC001029B` sono lo stesso registro che legge
  EMI, quindi un accordo a finestra uguale e' coerenza di implementazione. La
  lettura via PawnIO **richiede un processo elevato**: da token UAC filtrato o
  SAFER `pawnio_open` risponde `0x80070005` e la ragione e' `access_denied`
  (misurato il 28-10-2026). EMI non ha questo requisito. Il canale va scritto per
  riga in `energy_calculation_method` (`energy/local_energy.py:151`), la finestra
  in `package_window_source` (`exact-counter | samples-fallback | counter-invalid
  | unavailable`, `:140-141`; `counter-invalid` dal 02-11-2026, `9fa9a44c`, e con un
  **secondo** trigger dal 04-11-2026 -- `b3b12ffe`, vedi la regola del registro fermo),
  l'origine della baseline in `idle_provenance` (`:142`) e, dalla v4, in
  `baseline_backend` — campo del protocollo P1.3, non ancora presente nel codice.
  Il flag `external_counter` (`:156`, D14) dice se quel numero viene da un canale
  **esterno** alla catena: vero solo per `energy-file` (`CW_ENERGY_FILE`), falso
  per EMI, PawnIO, RAPL e per le catene GPU. Serve a escludere le righe
  dell'override con un filtro booleano, non confrontando l'etichetta.
  Mai presentare un fallback come un contatore, ne' un integrale come un
  contatore.
- **Sulla GPU il token dice quale percorso ha prodotto il numero.**
  `gpu_attribution_method` comincia sempre con `nvml-energy` (delta del
  contatore cumulativo NVML, mJ) o `nvml-power-integral`, oppure con
  `amdsmi-energy` / `amdsmi-power-integral` sulla catena AMD. Il contatore si usa
  solo con delta non negativo e senza sottofinestre escluse, che un delta non
  sa sottrarre; un integrale non si presenta come contatore. Su AMD SMI la
  risoluzione si legge dall'API (`accumulator * resolution` in microjoule) e se
  manca o e' zero il contatore non si usa: non si assume. Il `timestamp` del
  device (1 ns, solo AMD SMI) e' un controllo di avanzamento, non una durata:
  timestamp fermo = lettura non valida, timestamp che avanza con contatore
  immobile = zero legittimo. Un delta negativo e' un reset o un avvolgimento e
  si copre con l'integrale, **mai clampato a zero**. La potenza dichiara
  `power=<campo> [W]` (su AMD `socket_power` prima, poi
  `current_socket_power`, poi `average_socket_power`) e il contesto
  `platform=gpu_bm_linux` quando vale. Il monitor GPU si seleziona **per
  vendor**: NVML per NVIDIA, AMD SMI per AMD; non esiste una catena
  NVML -> AMD SMI per la stessa scheda, e i due non girano mai in parallelo.
  **La scheda dentro un backend si seleziona per indice, e l'indice 0 non e'
  una scelta implicita** (dal 03-11-2026): `_gpu_indice_richiesto`
  (`energy/energy_session.py:1471`) legge argomento esplicito, poi
  `CW_GPU_INDEX`, poi "non dichiarato"; `_selezione_device` (`:1496`) apre
  l'indice richiesto e, se e' fuori intervallo, **non apre la scheda 0** —
  misurare una scheda e scrivere la riga come se fosse quella richiesta e' un
  numero attribuito male, non un degrado. Con un solo device l'indice 0 non e'
  un'assunzione e non produce nota; con piu' device e nessuna selezione la riga
  lo dice per via sua (`device_note`, appendice in `notes`,
  `energy/local_energy.py:851-853`, lo schema P5 resta 174 nomi). Un
  `CW_GPU_INDEX` non numerico e' un errore dichiarato, non un "non dichiarato".
  L'indice e' una **posizione nell'elenco del backend che ha risposto**
  (`nvmlDeviceGetHandleByIndex`, `amdsmi_get_processor_handles`), non un ID del
  produttore: lo stesso numero su vendor diversi non e' lo stesso silicon. Il
  runner non ha un flag per l'indice — la via di produzione oggi e'
  `CW_GPU_INDEX`, perche' la sessione chiama `_open_gpu_monitor()` senza
  argomento (`energy_session.py:765`).
  **Il ramo per processo non ha una durata da usare, e deve dirlo.**
  `gpu_process_energy_j` vale N/A nella quasi totalita' dei casi, perche' il
  binding NVML installato espone i campioni di `nvmlDeviceGetProcessUtilization`
  come `(pid, timeStamp, smUtil, memUtil, encUtil)` -- **nessun intervallo per
  processo** (`pynvml.py:1755-1761`, letto il 04-11-2026). Senza durata non
  esiste frazione del tempo di finestra da scalare all'energia board: **non si
  inventa un intervallo** e non si sposta il ramo su un'altra unita' di misura.
  Ogni `None` di `process_energy_j` (`energy_session.py:1648`) scrive la **propria**
  ragione in `process_energy_reason` (inizializzata a `:1569, :1683`) e
  `local_energy.py:989` porta quella stringa nella riga: una formula fissa per
  tutti i rami era falsa, perche' il ramo piu' frequente non e' un problema di
  NVML bensi' `_last_window_board_active_j`, letto via `getattr` e mai assegnato
  da nessun percorso. Il campo resta **informativo**: non entra in
  `gpu_energy_attributed_j` e non sostituisce l'attribuzione whole-device. Limite
  dichiarato del ramo che funziona: i campioni vengono dagli **ultimi 10 s** di
  storia NVML, non da `[t_start, t_end]`, quindi la frazione non e' sulla finestra
  della riga quando la finestra non dura 10 s.
  Le due catene sono **[I]** (implementate, provate con `pynvml` e `amdsmi` finti,
  28-10-2026) con **[V] da fare**: su questa macchina non c'e' ne' una NVIDIA
  ne' una AMD, quindi l'esecuzione su GPU reale e' ancora da registrare. Qui
  `[P]` non significa "implementato ma non provato su hardware": significa
  "progettato e non implementato". `pawnio-counter` invece e' **[I] con [V] su
  questo host** (Intel, 28-10-2026: rapporto 1,000578 e 1,000576 contro EMI a
  finestra uguale); restano **[V] da fare** il ramo AMD e riporto/reset reali.
- **Solo i token di canale reali.**
  `MEASURED_METHODS = ("emi-counter", "pawnio-counter", "power-integration",
  "librehardwaremonitor-energy", "energy-file", "rapl")`
  (`energy/energy_session.py:73-74`). La lista dice **quali righe portano un
  numero**, non cosa sa fare il codice oggi: `power-integration` e
  `librehardwaremonitor-energy` restano per i CSV archiviati in
  `experiment_results/` (v1-v3, four-way, A-B-A) misurati con quei canali, e
  nessun percorso di produzione li produce piu'. **CasualWatt non ha un percorso
  di stima TDP**: quello e' il percorso di CodeCarbon, usato nella tesi come
  contrasto. Non inventare un canale `estimated`.
- **PawnIO non si somma a EMI e non si carica da un blob qualunque.** La catena
  e' una cascata: se EMI risponde, PawnIO non viene aperto. Il modulo deve essere
  la release 0.2.11 con SHA-256 pinnato; un hash diverso non si carica. Con HVCI
  attivo **o non determinabile** il firmatario del driver deve essere Microsoft
  (`fail closed`); con HVCI disattivo un terzo valido e' ammesso ma la riga lo
  dichiara. Nessuna scrittura di MSR: l'IOCTL di scrittura esiste e non si usa.
- **Nessun doppio conteggio.** PP0 e PP1 sono sottoinsiemi di PKG: non sommare
  `PKG+PP0+PP1` e non sommare `PKG+DRAM` (`energy/emi_backend.py:32-34`, `:580`;
  `DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")` a `:116`). PP1 alimenta
  `igpu_energy_j`, informativo.
- **Baseline = mediana, non media.**
  `baseline_pre_w = mediana(P_rep,1..3)` su tre finestre da 30 s (P1.3). Con
  `n = 3` una finestra contaminata sposta la media ma non la mediana (P1.14).
  Si applica `P_pre`; `P_post` e' diagnostica (`dP`), mai applicata. La ragione e'
  causale: la richiesta e' l'intervento, quindi il post e' una grandezza
  post-trattamento e condizionarvi l'estimatore renderebbe la correzione
  dipendente dall'esito che deve correggere (P1.14, motivazione causale).
- **Un registro fermo ai bordi non e' una finestra da 0 J.** Il record EMI porta
  il timestamp del contatore in unita' da 100 ns (`energy/emi_backend.py:31`,
  esposto come `ts_100ns` a `:588`; solo EMI lo ha -- PawnIO risponde `None`,
  `energy/energy_session.py:888` e `:903`). Se i due bordi leggono **lo stesso
  record** (`ts_edge1 <= ts_edge0`, `energy/local_energy.py:461-471`, da
  `b3b12ffe` del 04-11-2026) l'incremento nullo non e' una misura: e' una lettura
  non avanzata, e la finestra va `counter-invalid` con `active_valid = False`, non
  `exact-counter` con `package_energy_raw_j = 0.0`. Nello stesso colpo la riga non
  degrada al buffer a 0,05 s. Con il timestamp **assente** (PawnIO, o un canale
  che non lo espone) la domanda non e' decidibile e il bordo vale: `None` non e'
  un "fermo". Su questo host la guardia non invalida righe reali, perche' il
  registro non e' mai rimasto fermo nelle letture campionante: 0 timestamp
  identici su 11.192 transizioni consecutive
  (`experiment_results/emi_cadenza_distribuzione_20261023.md:74`, `:79-81`,
  misurato il 23-10-2026); rimuove un numero che non deve esistere, non un numero
  che esiste.
- **Nessun troncamento.** Gli incrementi negativi si conservano: sul ramo CPU il
  flag di riga e' `active_valid` con i valori grezzi `package_energy_raw_j` e
  `active_energy_raw_j` (`energy/local_energy.py:603-604`, `:622-633`; colonne
  nel schema a `casualwatt_csv_export.py:118`), e a livello di blocco resta il
  flag `negative_increment` (`benchmark_v4.py:1694`, colonna di riepilogo). **Il
  debito di metodo dichiarato il 24-10 e' chiuso al 02-11-2026 da `cd881e6b`**:
  i tre clamp a zero che la produzione applicava (`:512`, `:530`, `:548`
  nell'antesistema) non esistono piu' — l'integrale di fallback somma `cur -
  prev` senza `max` (`local_energy.py:578-581`), `package_energy_j` e' il valore
  firmato (`:603`) e `active = active_raw` (`:621`), con la nota che nomina il
  negativo quando c'e' (`:634-639`). **Anche il quarto clamp, quello del percorso
  a campioni, cade il 04-11-2026 con `86bba6a8`**:
  `package_energy_exact_between` (`energy/energy_session.py:1188`) restituiva
  `max(base, 0.0)` -- e lo applicava anche dopo la sottrazione delle
  sottofinestre escluse, quindi un reset fra i campioni diventava una finestra da
  `+X` J invece che da `-X` J -- e ora restituisce il delta firmato in entrambi i
  rami. **Le coordinate di questo elenco sono del 04-11 (sera), dopo i ~40 righe
  di guardie aggiunte da `b3b12ffe` e `86bba6a8`**: i valori citati a `:539`,
  `:561`, `:579`, `:592-597`, `:620`, `:637`, `:672`, `:683-684` dell'ancoraggio
  del 02-11 sono gli stessi codici piu' su di quelle righe, e chi corregge di
  nuovo le guardie deve re-indirizzarli. Resta clampato cio' che **non e' energia**:
  i delta di tempo CPU (`:662`, `:665`, `:679`) perche' un contatore di secondi che
  torna indietro e' un reset, e la quota dove viene usata (`:726`) perche' il
  rapporto grezzo `share_raw` e' conservato a `:746-747` con le anomalie dichiarate
  (`:712-718`, `:725`). La regola non nasce con la v4: era gia' DP-A nella
  specifica `METODI_E_FORMULE.md` del 21-10
  (`Ê_att = E_pkg^raw − E_base`, "firmata, mai clampata"), documento che sta in
  `Tesi-latex/` e quindi **fuori da git**: la
  citazione e' di provenienza, non e' un riferimento consultabile nel repo. Su
  questo punto il codice non e' piu' in ritardo di una generazione rispetto alla
  specifica; la frase che lo affermava era stantia ed e' stata sostituita da
  questa dichiarazione. Uno zero legittimo e' dichiarato, non inventato: baseline non
  calibrata -> `baseline_energy_j = 0` con `idle_provenance = "uncalibrated"`
  (`energy/local_energy.py:380-390`).
- **Linguaggio dell'incertezza.** "Semi-range conservativi", mai "deviazione
  standard": con `n = 3` non si stima una varianza. Nessun `sqrt(...)` del
  protocollo e' una propagazione di varianza: sono combinazioni in quadratura di
  budget conservativi. Ogni numero pubblicato esce con il suo `budget_pred` e con
  la sua fascia di copertura; la copertura e' un campo (`coverage_tier`,
  `hull_margin_tok`), non un aggettivo nel testo.
- **La quadratura non e' un limite conservativo garantito.** Per due termini non
  negativi, `sqrt(a^2+b^2)/(a+b)` sta fra `1/sqrt(2)` e `1`: la somma aritmetica
  e' fra 1,00 e 1,41 volte la quadratura, qualunque siano i valori. La forma scelta e'
  provvisoria (P1.7): si scrive "budget", non "limite superiore garantito", e non
  si presenta la quadratura come se fosse la scelta scientificamente obbligata. La
  scelta dipende da cosa rappresenta il budget — incertezze standard combinabili
  sotto un'ipotesi probabilistica, oppure limiti assoluti senza compensazione — e
  non da quanto e' grande il numero.
- **Nessuna colonna di deviazione standard a `n = 3`** (P4.12). Non e' una stima
  utilizzabile di varianza ed e' ridondante: la terna `(min, med, max)` **e'** la
  terna delle osservazioni riordinata, quindi `sd` ne e' una funzione
  deterministica. Si registrano i tre valori, la mediana, il minimo, il massimo e
  il range. Un indicatore ridondante suggerisce che esista una sigma stimata.
- **`acc_comp` non e' un'accuratezza.** E' un indice descrittivo a pesi su tre
  componenti di natura eterogenea (`acc_links`, `judge/5`, coseno nel regime A) e
  la sua scala non e' omogenea: il numeratore di `ece_per_joule` mischia un
  punteggio 0-1 con una media su scala 0-5. L'accuratezza primaria resta
  `is_correct` (1/0/N/A) e in ogni ramo si determina **prima** di `acc_comp`
  (`evaluator.py:400` e `:406`, `:507` e `:508`, `:535` e `:537`, `:580-597` e
  `:610`, `:665` e `:667`). Il nome storico "accuracy composita" era ambiguo e la
  rinomina **non** ha toccato lo schema P5: il ruolo della riga sta in `notes`
  (`RUOLO_COMPOSITO` / `RUOLO_BINARIA`, `evaluator.py:238-245`, appese a `:414`,
  `:524`, `:548`, `:617`, `:673`) e nelle etichette dei grafici
  (`genera_grafici_tesi.py`), non in una colonna nuova. Sui rami `number` e
  `short_text` `acc_comp` **coincide** con `float(is_correct)`: non e' un'eccezione
  da annotare, e' la definizione del ramo.
- **L'unita' statistica di un benchmark ripetuto e' il task, non la riga.**
  Ripetere la stessa richiesta a temperatura zero non aggiunge un grado di
  liberta'; la variabilita' da coprire e' fra task diversi. Accanto all'intervallo
  di Wilson a livello di riga si pubblica un **bootstrap a livello di task**
  (percentile 2,5-97,5, 2000 ricampioni, seed `20261104`:
  `evaluation_runner.py:14-20`, chiave `accuracy_cluster_bootstrap_95` a `:169`, e
  `robust_evaluator.py:490-510`, dove `task_ids` arriva come argomento perche'
  `EvaluationResult` non porta l'identita' del task). Nei tre casi in cui non e'
  calcolabile l'intervallo resta **`None` con la ragione dichiarata**: identita'
  del task non registrata, un solo task distinto (varianza zero per costruzione non
  e' evidenza), righe senza id escluse dal ricampiono ma conteggiate nella nota. Se
  il bootstrap a cluster risulta piu' largo di Wilson, le righe non erano prove
  indipendenti. Il confronto fra due sistemi sullo stesso task **non** si fa per
  sovrapposizione di intervalli: resta una McNemar appaiata.
- **Un accordo fra due letture dello stesso registro NON e' una validazione
  indipendente.** EMI, LibreHardwareMonitor (oggi fuori dall'implementazione) e
  SRUM leggono tutti
  `MSR_PKG_ENERGY_STATUS` (0x611): concordano per costruzione anche se la scala
  fosse sbagliata. La scala assoluta resta **non arbitrata** senza un wattmetro
  AC/DC esterno. Questo caveat va scritto prima dei numeri, non in nota.
- **"Validata" e' una parola sola.** Si scrive solo se tutti e sei gli anelli di
  P4.9 passano (`chain_status = validated`). Altrimenti si scrive quale anello ha
  ceduto. Dal 28-10-2026 il token ha un produttore (`validation_chain.py`), che
  applica le soglie congelate e restituisce l'etichetta del **primo** anello che
  cede; non promuove nulla e nessuna riga e' `validated` finche' una campagna non
  passa tutti e sei.
- **Le soglie sono congelate prima dei dati.** 1,0 W, 10%, 20%, `err_rel <= 10%`,
  2 token, fattore 2: nessuna si sposta dopo aver visto il risultato.

---

## Comandi di verifica

```
pytest cwEnergyModular          # 608 raccolti: 605 passati, 3 saltati (04-11, notte)
```

**Mai `pytest` nudo dalla radice**: la raccolta viene interrotta da 6 errori in
`cpuepower/` e `cpuepower2/` (`ModuleNotFoundError: No module named
'cpuepower.attribution'`).

Ogni modifica al codice va accompagnata dall'output di pytest incollato per
intero, non riassunto.

La tesi si compila con MiKTeX in `Tesi-latex/qoder-bozza/`:

```
pdflatex main && biber main && pdflatex main && pdflatex main
```

**`biber`, non `bibtex`**: il documento usa biblatex e `bibtex main` fallisce con
"I found no \citation commands", azzera `main.bbl` e produce un PDF senza
bibliografia. Requisiti di compilazione: 0 overfull hbox, 0 riferimenti
indefiniti.

---

## Struttura dei file

- `cwEnergyModular/` — codice di produzione. `energy/emi_backend.py` (contatore
  EMI via ctypes/SetupAPI, con selezione del device CPU e del canale PKG dal
  metadato), `energy/pawnio_backend.py` (contatore MSR del package via driver
  PawnIO: sonda del driver e del modulo, unita' derivata, fallback dichiarato di
  EMI), `energy/energy_session.py` (canali, integrazione di
  finestra, interpolazione ai bordi), `energy/local_energy.py` (campi per riga),
  `casualwatt_csv_export.py` (`CSV_COLUMNS`, righe 17-204 — 174 nomi;
  `BLOCK_SUMMARY_COLUMNS`, 212-227; `POINT_SUMMARY_COLUMNS`, 229-237), e il
  runner v4 `benchmark_v4.py` (sequenza di blocco di P1.5).
- **Il valutatore della risposta sta nello stesso modulo**: `evaluation_runner.py`
  (aggregati con intervallo di Wilson a livello di riga, bootstrap a cluster a
  livello di task, rifiuto dei valori non finiti),
  `mudilab_adapter.py` (ponte MUDILAB: un tool call non verificabile rende la
  riga `indeterminate`), `robust_evaluator.py` (secondo criterio: numero univoco
  o marcatore finale, probabilita' condizionate a tutti gli stadi, controfattuale
  su entrambi i limiti) e `mudilab_eval.py`; i tre `test_*.py` alla radice li
  coprono con **51** test (36 fino alla mattina del 04-11, +15 dai quattro fix
  della notte). Il criterio robusto e' **secondario**:
  `MUDILAB_run/benchmark/valuta.py` e `_confronta` di
  `MUDILAB_run/benchmark/genera.py` restano il riferimento ufficiale delle misure
  pubblicate il 02-11-2026, e il criterio non tocca ne' il valore misurato ne' la
  scala del contatore. Le tre note di metodo stanno in `cwEnergyModular/docs/`
  (`EVALUATION_FRAMEWORK.md`, `ROBUST_EVALUATOR.md`,
  `RELAZIONE_VALUTATORE_ROBUSTO.md`).
- **I test stanno in due posti**: `cwEnergyModular/tests/` (493 raccolti la notte
  del 04-11; 482 al 03-11, +4 di `b3b12ffe` e +1 di `86bba6a8` e +5 di `4b922db6`
  e +1 del declassamento di `acc_comp`)
  e direttamente in `cwEnergyModular/` (`test_answer_type_evaluation.py`, 40;
  `test_synthetic_window.py`, 2; `test_validazione_valutazione.py`, 22;
  `test_robust_evaluator.py`, 19; `test_mudilab_adapter.py`, 26;
  `test_evaluation_runner.py`, 6); 493 + 115 = 608. Gli ultimi tre sono il criterio
  robusto del valutatore, entrato il 04-11 con `cf6aca71` e `6b1dccb8`: e' il
  secondo criterio di quella valutazione, non un dominio nuovo della misura, e non
  tocca ne' il valore misurato ne' la scala del contatore. Diciotto delle loro
  trentasei docstring sono state scritte il 04-11 mattina leggendo i corpi (11 in
  `test_robust_evaluator.py`, 5 in `test_mudilab_adapter.py`, 2 in
  `test_evaluation_runner.py`), le altre diciotto accompagnavano il test; le
  quindici entrate la notte (8 in `test_mudilab_adapter.py` dai due fix sul ramo
  MUDILAB, 3 in `test_robust_evaluator.py` e 4 in `test_evaluation_runner.py` dal
  bootstrap) accompagnano il test loro. La provenienza e' dichiarata, non
  mascherata. Ogni test ha una docstring che
  dice *perche'* esiste e quale relazione matematica o fisica verifica, non solo
  cosa fa. Al 28-10-2026 la norma non era rispettata da nove funzioni (13 node
  id, tutte scritte il 27-28/10): otto in `tests/test_pawnio_backend.py`, una in
  `tests/test_diagnostics_pmi.py`. **Debito chiuso il 03-11-2026 con `9d4ce024`**:
  le nove docstring sono scritte alla fonte, nessuna parafrasi del generatore, e
  l'AST ora conta zero funzioni `test_` senza docstring su tutto il tree. Il
  generatore continua a stampare "nessuna docstring" invece di mascherare, e su
  questa suite oggi non stampa quella riga per nessuna delle 608 righe.
  Dal 27-10-2026 la cartella contiene anche `tests/test_rapl_zone.py`
  (8, logica RAPL su un finto sysfs), `tests/test_diagnostics_pmi.py` (7,
  sonda PMI/WMI) e `tests/test_emi_selezione.py` (16, metadati EMI sintetici:
  metadato V2, scelta del device CPU, canale PKG per nome, V1 scartato): girano
  su Windows, senza host Linux. Dal 28-10-2026 ci sono
  `tests/test_gpu_nvml_energy.py` (8 il 28-10, 16 dal 03-11 con la selezione del
  device, 21 dal 04-11 (sera) con le cinque ragioni dell'N/A per processo; catena `nvml-energy` ->
  `nvml-power-integral` con `pynvml` finto), `tests/test_gpu_amdsmi.py` (19 il
  28-10, 24 dal 03-11;
  catena `amdsmi-energy` -> `amdsmi-power-integral`, conversione da microjoule,
  timestamp come controllo di avanzamento, delta negativo, provenienza di
  potenza e piattaforma, precedenza di NVML, con `amdsmi` finto) e
  `tests/test_metriche_per_token.py`
  (4, le tre colonne per token accodate al CSV) e
  `tests/test_external_counter.py` (6, D14: `external_counter` vero solo per
  `energy-file`, falso per `emi-counter`, `pawnio-counter`, `rapl` e per una
  riga con GPU `nvml-energy`) e `tests/test_chain_status.py` (17, il produttore
  di `chain_status` di P4.9: ordine degli anelli, confini delle soglie, quorum
  del test load-versus-control, vocabolario chiuso). Dal 28-10-2026 ci sono anche
  `tests/test_pawnio_backend.py` (25, catena `pawnio-counter`: sonda HVCI e
  firma con i due firmatari, hash del modulo, ramo Intel e ramo AMD mai su
  `0x611`, unita' derivata, riporto, reset, `access_denied`) e
  `tests/test_pawnio_selezione.py` (9, precedenza EMI -> PawnIO nella sessione,
  nessuna somma dei due canali) e `tests/test_diagnostics_pawnio.py` (4, la
  diagnostica dichiara `pawnio-counter` solo quando il contatore risponde,
  `unavailable` con la ragione altrimenti, e `CW_ENERGY_FILE` ha la precedenza).
  Nello stesso giorno `tests/test_cw_energy_file_override.py` (3) fissa il
  significato di quella precedenza: con un file valido la catena si ferma e
  EMI/PawnIO non vengono tentati, mentre file assente o valore non numerico
  lasciano proseguire la selezione di piattaforma.
  L'Appendice D della tesi e' stata rigenerata il 2026-10-28 con
  `cwEnergyModular/tools/dump_tests_latex.py`: 526 node id, 523 passati, 3
  saltati, docstring 513/526 (le nove funzioni senza docstring elencate sopra).
  **Rigenerata di nuovo il 2026-11-03, dopo `cd881e6b` e `9fa9a44c`: 528 node id,
  525 passati, 3 saltati, docstring 515/528.** Il diff e' di due sole righe nuove
  (`test_cpu_attribution.py::test_c_reset_contatore_ai_bordi_non_degrada_al_fallback`
  e `test_metriche_per_token.py::test_token_stimati_non_entrano_nelle_metriche_scientifiche`)
  piu' una docstring riscritta: nessun fallimento, nessuna riga sparita.
  **Rigenerata una terza volta il 03-11-2026 (sera)**: 541 node id, 538 passati,
  3 saltati, docstring 541/541 -- le nove funzioni elencate sopra le hanno tutte
  (`9d4ce024`). Il diff dalle 528 del mattino e' di 13 righe, tutte e 13 dentro i
  due file GPU della selezione del device: nessun fallimento, nessuna riga sparita.
  **Rigenerata una quarta volta il 04-11-2026, sull'albero che porta il criterio
  robusto del valutatore**: 577 node id, 574 passati, 3 saltati, docstring 577/577;
  le intestazioni di modulo in corsivo sono 45 su 48, perche' i tre file nuovi non
  ne hanno una. Il diff dalle 541 e' di 36 righe, tutte dentro
  `test_robust_evaluator.py` (16), `test_mudilab_adapter.py` (18) e
  `test_evaluation_runner.py` (2): nessun fallimento, nessuna riga sparita.
  Diciotto delle loro trentasei docstring sono state scritte il 04-11 leggendo i
  corpi, le altre diciotto accompagnavano il test. I conteggi della prosa sono
  rifatti col parser dello stesso generatore (`raccogli` e `nome_e_parametri`),
  non per aritmetica: 483 funzioni per `(percorso, classe, nome)`, 482 ignorando
  la classe, 459 monoriga + 118 righe da 24 famiglie parametrizzate in 12 file,
  48 file; delta $294 \to 577 = +288 - 8 + 3$. Il testo dei capitoli e
  dell'Appendice D che dichiarava 541 node id, 447 funzioni, 423 monoriga e 45
  file e' riscritto con questi numeri.
  **Rigenerata una quinta volta la sera del 04-11-2026, sull'albero dei tre
  interventi dell'audit** (`b3b12ffe`, `86bba6a8`, `4b922db6`): **587** node id,
  584 passati, 3 saltati, docstring 587/587, nessuna riga `\textbf{fallito}`,
  `\textbf{errore}` o `n/eseguito` -- ogni node id raccolto ha un esito eseguito.
  I tre salti, qui attribuiti a `test_rapl_zone.py`, stanno in realta' in
  `tests/test_rapl.py:43` (lo dichiara il generatore stesso nella sezione
  "Motivi dei salti"): l'attribuzione di questa riga era stantia, il conteggio
  no. Il diff
  dalle 577 e' di 10 righe: 4 in `test_cpu_attribution.py` (bordi sullo stesso
  record, timestamp che regrada, assenza di timestamp non decidibile, delta
  negativo del percorso a campioni), 1 in `test_emi_backend.py` (il segno del
  reset attraversa `package_energy_exact_between`) e 5 in
  `test_gpu_nvml_energy.py` (le ragioni dell'N/A per processo). Nessun fallimento,
  nessuna riga sparita. I conteggi della prosa, di nuovo col parser del generatore
  e non per aritmetica: **493** funzioni per `(percorso, classe, nome)`, 492
  ignorando la classe, **469** monoriga + 118 righe da 24 famiglie parametrizzate
  in 12 file, 48 file; delta $577 \to 587 = +10$.
  Una nota sul metodo, perche' il 27-28 ottobre ha gia' visto un conteggio a
  memoria: le dieci righe nuove sono tutte monoriga e le famiglie restano 24,
  quindi il parser del generatore -- che tratta l'istanza parametrizzata con
  ``id`` stringa vuota come ``param`` falso -- stampa 471 ``monoriga`` e 116 righe
  parametrizzate. Le due righe ``[]`` (``test_riferimento_non_valido...`` e
  ``test_stato_non_di_misura_produce_none``) appartengono a famiglie da 7 e da 3
  istanze: contate per appartenenza si ottengono i 469 + 118 di questo file, che
  e' la stessa regola usata per i 459 + 118 del 04-11 mattina e per i 423 + 118
  del 03-11. La somma dei due tagli e' 577 e 587 in entrambi i casi; cambia solo
  dove si mettono due righe, e va detto quale regola si sta usando.
  **Rigenerata una sesta volta la notte del 04-11-2026, sull'albero dei quattro
  fix del valutatore** (`98ec5972`, `8a91e16c`, `40f6c619`, `5f23853d`): **608**
  node id, 605 passati, 3 saltati, docstring 608/608, intestazioni di modulo in
  corsivo 45 su 48 (i tre file senza restano `test_robust_evaluator.py`,
  `test_mudilab_adapter.py`, `test_evaluation_runner.py`), nessuna riga
  `\textbf{fallito}`, `\textbf{errore}` o `n/eseguito` -- contato sul file
  generato, non dichiarato. Il diff dalle 587 e' di **+21** righe: 8 in
  `test_mudilab_adapter.py` (4 sulla tolleranza derivata dai decimali stampati, 4
  sulla registrazione degli argomenti), 5 in `test_answer_type_evaluation.py` (il
  ruolo di `acc_comp` nei due regimi a pesi e nei due rami binari), 1 in
  `tests/test_cloud_energy_none_preservato.py` (il numeratore di
  `ece_per_joule` nominato nella nota), 4 in `test_evaluation_runner.py` e 3 in
  `test_robust_evaluator.py` (bootstrap a cluster). Il confronto e' fatto per
  **conteggio per file** contro i numeri registrati in questo file (35, 18, 16, 2,
  492), non per diff testuale: `Tesi-latex/` sta fuori da git e la versione
  precedente del generato e' stata sovrascritta, quindi la scomparsa di una riga
  sarebbe visibile solo come ammanco nell'aritmetica -- che qui chiude a
  $8+5+1+4+3=21$. I tre salti sono gli stessi tre di `tests/test_rapl.py`.
  I conteggi della prosa, di nuovo col parser del generatore e non per
  aritmetica: **514** funzioni per `(percorso, classe, nome)`, **513** ignorando
  la classe, **492** monoriga + **116** righe parametrizzate come le stampa il
  parser, che sono **490 + 118** con la regola delle appartenenze usata in questo
  file (le due righe ``[]`` tornano nelle famiglie da 7 e da 3); famiglie 24 in
  12 file, 48 file; delta $587 \to 608 = +21$.
  **Il 03-11 anche il testo della tesi e' stato allineato a quel conteggio**: i
  paragrafi che dichiaravano $294$ node id, $291$ verdi, $237$ funzioni,
  ``ventisei file``, la decomposizione per file e l'ancoraggio di
  `test_energy_corrections.py` a 19 test (oggi 14, con gli otto rami LHM tolti da
  D18) sono riscritti con i numeri verificati il 03-11 col parser dello stesso
  generatore, non a memoria -- $541$ node id, $447$ funzioni per
  `(percorso, classe, nome)`, $423$ monoriga + $118$ da $24$ famiglie parametrizzate
  in $12$ file, $45$ file tutti tracciati, delta $294 \to 541 = +252 - 8 + 3$.
  Le riesecuzioni del 03-11 sulla raccolta da 541: dalla radice $538$ passati e
  $3$ saltati senza avvisi in $7{,}06$ s, $7{,}53$ s e $7{,}39$ s; il generatore
  dalla cartella del modulo gli stessi $538$ e $3$ in $6{,}94$ s. Due invocazioni
  della stessa giornata avevano la stessa raccolta e lo stesso esito in $10{,}9$ s:
  la durata non e' un ancoraggio citabile, il conteggio si'.
  Il documento compila: **195 pagine, 0 riferimenti indefiniti, 0 `Overfull \hbox`**
  (notte del 04-11-2026: `pdflatex`, `biber`, `pdflatex` x2, poi due `pdflatex`
  ancora dopo la correzione di un accento nel glossario; il `.bbl` porta **65**
  voci prima e dopo, nessuna citazione aggiunta o rimossa). I sei pagine sopra il
  PDF da 189 sono localizzate confrontando i due `main.toc`: $+2$ dentro
  `sec:valutatore` (la prosa dei quattro fix, che prima era una sezione di solo
  titolo), $+1$ nella prosa dei conteggi di `sec:validazione-software`, $+1$ nel
  paragrafo di `sec:statistica` sull'unita' statistica, $+1$ fra l'Appendice C e
  la prosa dell'Appendice D, $+1$ nella tabella generata (le $31$ righe nuove fra
  la quinta e la sesta rigenerazione). Le conteggi precedenti restano storia
  datata: 186 prima della riconciliazione dell'Appendice D con l'albero di
  integrazione, 183 prima della prosa sulla selezione del device GPU, 184 prima
  del riallineamento dello schema CSV, 189 prima di questa.
  **Il passo che queste righe dichiaravano non fatto e' fatto**: la tesi e'
  riallineata all'albero da 608 node id nei capitoli 3-6, nell'Appendice C,
  nell'Appendice D e nel glossario. Il testo che dichiarava $577$ node id e'
  riscritto con i conteggi verificati col parser del generatore, non per
  aritmetica; la declassazione di `acc_comp`, la tolleranza derivata, la
  registrazione degli argomenti e l'incertezza a livello di task hanno ora prosa
  ancorata (cap.\,4 `sec:valutatore`, cap.\,3 `sec:metriche-derivate`, cap.\,5
  `sec:statistica`, cap.\,6 sviluppo 6), e il glossario non spiega piu' `ECE`
  come ``Executive Capacity Evaluation'': lo sviluppo non compare nel codice, che
  usa la sigla e basta (`benchmark_unified.py:15`, `:562`, `:666`). I tre PNG
  citati dalla tesi sono rigenerati la stessa notte
  (`genera_grafici_tesi.py --input results/semantic_evaluation_results.csv`, 2
  righe su 9 sopravvivono al filtro) con le etichette entrate con `40f6c619`, e
  copiati in `Tesi-latex/qoder-bozza/figure/`; restano non tracciati perche'
  `cwEnergyModular/results/` non tiene i PNG.
  Lo stesso 04-11 l'Appendice A e' rigenerata con
  `cwEnergyModular/tools/dump_schema_latex.py` e porta i numeri dello schema vivo:
  $174$ colonne di riga + $30$ di metadato, $77$ di riga + $1$ di metadato ancora
  `nuova` rispetto al CSV di riferimento, $27$ campi `vuota`, header del dataset
  $99$ nomi e header dei metadati $29$. Il testo dei capitoli che parlava di $113$
  colonne \`e allineato a $174$ (cap.\,5, sezione costo in euro), e con lui gli
  ancoraggi di `benchmark_unified.py` spostati dalla crescita del runner: durate di
  fase `:189-190, 238-239`, conversione e scorporo del giudice `:430-456, 941-970`,
  enumerazione per richiesta `:914-915` (con `energy_session.py:814-824`), metriche
  derivate `:605-684` e gate `f1_triples` `:674-682`, template cloud `:515, 549`
  (nota `:541-548`, etichetta scritta dal branch `:1267-1269, 1279`), salto del
  ramo cloud `:1113-1115`. La correzione del template cloud ha ora anche
  l'ancoraggio storico del commit `1f55ca90` (23-10-2026) accanto a quello di
  riga.
  I cinque boxes che stavano nel log del 03-11 (4 in
  `capitoli/cap04_architettura_implementazione.tex` righe 125-141, i token
  `librehardwaremonitor-energy`, `nvml-power-integral`, `amdsmi-power-integral`,
  `igpu-included-in-package` dentro le celle di `tab:backend-fallback`; 1 in
  `capitoli/cap06_conclusioni_sviluppi.tex` riga 122) sono corretti con lo stesso
  meccanismo del generatore -- `-\allowbreak{}` nei token -- piu' l'allargamento
  della terza colonna e il ribilanciamento delle altre a
  `p{0.15} p{0.19} p{0.23} p{0.16} p{0.20}`: il solo punto di capo non bastava,
  perche' `librehardwaremonitor-` e' un frammento di 21 caratteri e nessuna
  sillabazione lo spezza. Quei cinque non erano dell'appendice: erano dei capitoli
  scritti a mano fra il 28-10 e il 02-11. **La lacuna di sostanza che era aperta e'
  chiusa il 04-11**: la regola di selezione del device GPU ora sta in prosa nei
  capitoli, non solo nel codice, nei 13 test e nell'appendice generata -- due
  paragrafi in `cap03_metodologia_misura.tex` (sezione 3.8, dopo `eq:gpu`: i due
  livelli della scelta, per vendor e poi per posizione, e le due condizioni che ne
  discendono), un `\paragraph` in `cap04_architettura_implementazione.tex` (dopo
  `tab:backend-fallback`: dove arriva la richiesta, cosa finisce nella riga, perche'
  `CSV_COLUMNS` resta a 174 nomi, perche' la via di produzione e' `CW_GPU_INDEX`) e
  una frase in `cap06_conclusioni_sviluppi.tex` (riga 162: il ramo multi-device e'
  [I] con [V] da fare, provato solo contro `pynvml` e `amdsmi` finti). Le tre
  aggiunte non introducono claim nuovi: ripetono in prosa ancoraggi gia' nel codice
  (`energy_session.py:1471-1493`, `:1496-1515`, `:1559`, `:1783-1787`, `:1804`,
  `:765`, `local_energy.py:851-853`, `casualwatt_csv_export.py:35`) -- e sono
  quelle del 04-11 (sera), perche' i ~70 righe aggiunte da `4b922db6` dentro
  `_GPUMonitor` hanno spostato in basso tutto il ramo AMD: le coordinate del 04-11
  mattina (`1465-1487`, `1490-1509`, `1553`, `1716-1720`, `1737`, `809-811`)
  indicano lo stesso codice.
  I conteggi non si aggiornano a mano: si rigenera dopo ogni test aggiunto, rimosso
  o rinominato. La verifica del conteggio al 28-10 e' in
  `experiment_results/appD_conteggio_20261028.md`.
  Il file generato (`Tesi-latex/qoder-bozza/generated/test_suite_appD.tex`) sta
  fuori da git, come tutto `Tesi-latex/`.
  I 17 test di `tests/test_protocollo_p4_geometry.py` (2026-10-26, quinto turno
  di revisione esterna) congelano la geometria di copertura di P4.7 e la scala
  di `budget_pred`
  di P4.6 senza hardware né dati: sono i test da eseguire quando qualcuno propone
  di cambiare i vertici dell'inviluppo o la formula del budget.
- **Alla radice del repo stanno 36 script `.py` tracciati** (35 fino a `244d1c2f`,
  che ha portato `montecarlo_protocollo_p64_probe.py`): sono gli harness
  degli esperimenti (`emi_50ms_probe.py`, `emi_resolution_check.py`,
  `four_way_test.py`, `srum.py`, `srum_emi_cross.py`, `observer_cost_probe.py`,
  `idle_floor_sensitivity.py`, `four_way_pi_audit.py`, ...). Questa e' la
  convenzione reale: **un harness il cui output e' citato dalla tesi o dal
  protocollo va tracciato**, perche' un'analisi non tracciata e' un numero che
  nessuno puo' rigenerare. Le sonde usa-e-getta non citate da nulla sono in
  `.gitignore`.
- `cwEnergyModular/tools/` — 9 file tracciati: i generatori del materiale LaTeX
  (Appendici A, D, E), l'analisi di cadenza EMI, la validazione HWiNFO e le tre
  sonde PawnIO (`fetch_pawnio_modules.py` scarica e verifica i moduli della
  release con hash pinnato, `pawnio_probe.py` confronta il contatore con EMI e
  misura il costo di osservazione A-B-A, `pawnio_priv_probe.py` misura i
  privilegi invece di dedurli).
- `experiment_results/` — dati sperimentali e analisi, tracciati (220 file: 219 in
  radice, 1 in `codecarbon_four_way/`; riverificati il 04-11-2026, dopo `244d1c2f`,
  che porta l'analisi Monte Carlo di P6.4). I
  protocolli congelati stanno qui. Un artefatto nuovo entra con il proprio commit
  e con la propria analisi. Il gruppo `pawnio_probe_20261028*` (due run di
  confronto, due A-B-A, tre token di privilegio, l'analisi) e' l'evidenza sotto
  `pawnio-counter`: senza quei file il token non si cita.
- `cpuepower/`, `cpuepower2/` — toolkit sottoposto ad audit: i suoi numeri erano
  mock, la CLI crasha, la mappa MSR era sbagliata. **Banca di esperimenti, non un
  backend di misura.** Non importarlo, non citarlo come risultato.
- **Archivi fuori dal repo** — `../casualwattMetUni/` (verificata il 27/10/2026)
  e le cartelle sorelle con la stessa struttura contengono prototipi storici su
  pythonnet + `LibreHardwareMonitorLib` (`energy_tracker*.py`,
  `consumi_ollama*.py`, `test_ollama_energy.py`). Non sono il backend di
  produzione, non si importano e i loro numeri non sono confrontabili con una
  riga `emi-counter`: misurano una potenza gia' derivata dallo stesso registro
  0x611. La dichiarazione sta nel loro `README.md`, non qui. Resta in questo repo
  solo `consumi_ollama.py` alla radice, strumento legacy a stima TDP/WMI, anch'esso
  fuori dal percorso di misura.
- `Tesi-latex/` — **fuori da git**, ora anche in `.gitignore`. Compilazione
  locale, mai push. `\include` per i capitoli, `\input` per le appendici; nei
  capitoli gli accenti italiani sono ASCII-escapati (`\`e` per "e'", `\'e` per
  "é"), non Unicode.
- `.casualwatt_keys.json` — vedi Regole dure.
- CSV: `cwEnergyModular/results/*.csv` e' ignorato. I CSV di benchmark sotto
  `Tesi-latex/test-emi/` seguono la regola della tesi e restano fuori. Cio' che la
  tesi cita va in `experiment_results/` e viene committato.
- **Non esiste una directory `Temp/`** e non esiste questa convenzione: non
  inventarla.

---

## Scrittura accademica

- Usare le chiavi esistenti di `references.bib`; **mai inventare una citazione**.
  Le voci marcate `IN VERIFICA` (`dalerci2026move`) non vanno
  citate finche' non sono verificate alla fonte primaria. Ogni voce ha una `note`
  con gli ancoraggi e la data della verifica. `mlenergy2025` **non e' piu' IN
  VERIFICA**: verificata 26-10-2026 alla fonte primaria (Chung et al.,
  arXiv:2505.06371, NeurIPS 2025 D&B Spotlight). Attenzione alla confusione
  gia' commessa: `mlenergy2025` e' il *ML.ENERGY Benchmark* (J/token in steady
  state, misura con Zeus), `tschand2025mlperfpower` e' *MLPerf Power*
  (arXiv:2410.12032, J/campione, strumentazione certificata) e non fornisce
  J/token.
- Mantenere distinta in ogni tabella l'energia **misurata** da quella
  **attribuita**: l'attribuzione e' una procedura con una sua assunzione
  dichiarata (quota di tempo CPU come proxy della quota di energia), non una
  lettura del contatore.
- Terminologia unica: **baseline** per la stima della potenza idle del package.
  "Idle floor" compare una sola volta come sinonimo dichiarato; "fondo" non si usa
  come sostantivo tecnico.
- Le fonti non peer-reviewed (preprint, white paper, blog, repository) sono
  etichettate come tali nel testo, mai presentate come letteratura.
- Italiano formale nella tesi; identificatori di codice e token in inglese cosi'
  come compaiono nel sorgente.
