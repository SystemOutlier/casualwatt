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
di nuovo al **28-10-2026** dopo NVML, AMD SMI, le tre colonne per token e il
controllo di timestamp del contatore AMD.
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
  Oggi non esiste sul disco ed e' ignorato.
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
  Windows il contatore EMI (`emi-counter`) oppure `unavailable` — nessun secondo
  canale, perche' LibreHardwareMonitor e' uscito dall'implementazione il
  2026-10-27 (D18, metodo provato e superato, sostituto MSR [P]); su Linux i
  contatori RAPL. `CW_ENERGY_FILE` (DEV/TEST) ha precedenza su entrambi. Non
  esiste piu' `CW_PRIMARY_CHANNEL`. Il canale va scritto per riga in
  `energy_calculation_method` (`energy/local_energy.py:134`), la finestra in
  `package_window_source` (`exact-counter | samples-fallback | unavailable`,
  `:124`), l'origine della baseline in `idle_provenance` (`:125`) e, dalla v4, in
  `baseline_backend` — campo del protocollo P1.3, non ancora presente nel codice.
  Mai presentare un fallback come un contatore.
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
  `platform=gpu_bm_linux` quando vale. NVML e AMD SMI non girano mai in
  parallelo — AMD SMI e' il fallback, non un secondo canale. Le due
  catene sono **[I]** (implementate, provate con `pynvml` e `amdsmi` finti,
  28-10-2026) con **[V] da fare**: su questa macchina non c'e' ne' una NVIDIA
  ne' una AMD, quindi l'esecuzione su GPU reale e' ancora da registrare. Qui
  `[P]` non significa "implementato ma non provato su hardware": significa
  "progettato e non implementato", come per PawnIO.
- **Solo i token di canale reali.**
  `MEASURED_METHODS = ("emi-counter", "power-integration",
  "librehardwaremonitor-energy", "energy-file", "rapl")`
  (`energy/energy_session.py:72-73`). La lista dice **quali righe portano un
  numero**, non cosa sa fare il codice oggi: `power-integration` e
  `librehardwaremonitor-energy` restano per i CSV archiviati in
  `experiment_results/` (v1-v3, four-way, A-B-A) misurati con quei canali, e
  nessun percorso di produzione li produce piu'. **CasualWatt non ha un percorso
  di stima TDP**: quello e' il percorso di CodeCarbon, usato nella tesi come
  contrasto. Non inventare un canale `estimated`.
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
- **Nessun troncamento.** Gli incrementi negativi si conservano con il flag
  `negative_increment`. La produzione attuale applica un clamp a zero in
  tre punti (`energy/local_energy.py:496`, `:514`, `:532`); la v4
  non lo fa e la differenza va dichiarata. La regola non nasce con la v4: era
  gia' DP-A nella specifica `METODI_E_FORMULE.md` del 21-10
  (`Ê_att = E_pkg^raw − E_base`, "firmata, mai clampata"), documento che sta in
  `Tesi-latex/` e quindi **fuori da git**: la
  citazione e' di provenienza, non e' un riferimento consultabile nel repo. Il
  codice di produzione e' dunque in ritardo di una generazione di metodo rispetto
  alla specifica. Uno zero legittimo e' dichiarato, non inventato: baseline non
  calibrata -> `baseline_energy_j = 0` con `idle_provenance = "uncalibrated"`
  (`energy/local_energy.py:196-203`).
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
- **Un accordo fra due letture dello stesso registro NON e' una validazione
  indipendente.** EMI, LibreHardwareMonitor (oggi fuori dall'implementazione) e
  SRUM leggono tutti
  `MSR_PKG_ENERGY_STATUS` (0x611): concordano per costruzione anche se la scala
  fosse sbagliata. La scala assoluta resta **non arbitrata** senza un wattmetro
  AC/DC esterno. Questo caveat va scritto prima dei numeri, non in nota.
- **"Validata" e' una parola sola.** Si scrive solo se tutti e sei gli anelli di
  P4.9 passano (`chain_status = validated`). Altrimenti si scrive quale anello ha
  ceduto.
- **Le soglie sono congelate prima dei dati.** 1,0 W, 10%, 20%, `err_rel <= 10%`,
  2 token, fattore 2: nessuna si sposta dopo aver visto il risultato.

---

## Comandi di verifica

```
pytest cwEnergyModular          # 460 raccolti: 457 passati, 3 saltati (10 s)
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
  metadato), `energy/energy_session.py` (canali, integrazione di
  finestra, interpolazione ai bordi), `energy/local_energy.py` (campi per riga),
  `casualwatt_csv_export.py` (`CSV_COLUMNS`, righe 17-193;
  `BLOCK_SUMMARY_COLUMNS`, 201-216; `POINT_SUMMARY_COLUMNS`, 218-226), e il
  runner v4 `benchmark_v4.py` (sequenza di blocco di P1.5).
- **I test stanno in due posti**: `cwEnergyModular/tests/` (401) e direttamente in
  `cwEnergyModular/` (`test_answer_type_evaluation.py`, 35;
  `test_synthetic_window.py`, 2; `test_validazione_valutazione.py`, 22);
  401 + 59 = 460. Ogni test ha una docstring che
  dice *perche'* esiste e quale relazione matematica o fisica verifica, non solo
  cosa fa. Dal 27-10-2026 la cartella contiene anche `tests/test_rapl_zone.py`
  (8, logica RAPL su un finto sysfs), `tests/test_diagnostics_pmi.py` (7,
  sonda PMI/WMI) e `tests/test_emi_selezione.py` (16, metadati EMI sintetici:
  metadato V2, scelta del device CPU, canale PKG per nome, V1 scartato): girano
  su Windows, senza host Linux. Dal 28-10-2026 ci sono
  `tests/test_gpu_nvml_energy.py` (8, catena `nvml-energy` ->
  `nvml-power-integral` con `pynvml` finto), `tests/test_gpu_amdsmi.py` (19,
  catena `amdsmi-energy` -> `amdsmi-power-integral`, conversione da microjoule,
  timestamp come controllo di avanzamento, delta negativo, provenienza di
  potenza e piattaforma, precedenza di NVML, con `amdsmi` finto) e
  `tests/test_metriche_per_token.py`
  (4, le tre colonne per token accodate al CSV).
  L'Appendice D della tesi e' stata rigenerata il 2026-10-26 con
  `cwEnergyModular/tools/dump_tests_latex.py`: 404 node id, 401 passati, 3
  saltati, docstring 404/404. Quel materiale precede l'uscita di LHM
  dall'implementazione (2026-10-27), che ha rimosso 8 test, e precede i 15 test
  della revisione del 27/10: va rigenerato prima
  di citarne i conteggi. Il file generato
  (`Tesi-latex/qoder-bozza/generated/test_suite_appD.tex`) sta fuori da git.
  I 17 test di `tests/test_protocollo_p4_geometry.py` (2026-10-26, quinto turno
  di revisione esterna) congelano la geometria di copertura di P4.7 e la scala
  di `budget_pred`
  di P4.6 senza hardware né dati: sono i test da eseguire quando qualcuno propone
  di cambiare i vertici dell'inviluppo o la formula del budget.
- **Alla radice del repo stanno 35 script `.py` tracciati**: sono gli harness
  degli esperimenti (`emi_50ms_probe.py`, `emi_resolution_check.py`,
  `four_way_test.py`, `srum.py`, `srum_emi_cross.py`, `observer_cost_probe.py`,
  `idle_floor_sensitivity.py`, `four_way_pi_audit.py`, ...). Questa e' la
  convenzione reale: **un harness il cui output e' citato dalla tesi o dal
  protocollo va tracciato**, perche' un'analisi non tracciata e' un numero che
  nessuno puo' rigenerare. Le sonde usa-e-getta non citate da nulla sono in
  `.gitignore`.
- `cwEnergyModular/tools/` — 6 file tracciati: i generatori del materiale LaTeX
  (Appendici A, D, E), l'analisi di cadenza EMI, la validazione HWiNFO.
- `experiment_results/` — dati sperimentali e analisi, tracciati (201 file: 200 in
  radice, 1 in `codecarbon_four_way/`). I
  protocolli congelati stanno qui. Un artefatto nuovo entra con il proprio commit
  e con la propria analisi.
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
