# AGENTS.md — regole vincolanti per chi lavora in questo repository

CasualWatt misura l'energia di una singola inferenza LLM locale su Windows,
leggendo il contatore energetico del package CPU. Il repository contiene insieme
il codice di produzione, i dati sperimentali e una tesi di laurea; le regole qui
sotto esistono perche' ognuna di esse corrisponde a un errore gia' commesso o a
una decisione gia' presa e documentata.

I numeri e gli ancoraggi di questo file sono verificati al **24-10-2026**. Se un
ancoraggio non torna, il file e' stantio: va corretto, non ignorato.

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
(incertezza e validazione) sono **congelati**. P5 (schema CSV e runner) e P6
(esecuzione e analisi) sono **aperti**; di P6 esiste solo una sezione
preparatoria (P6.1 pavimento di tempo a muro, P6.2 obblighi di esecuzione del
pilota) che e' derivata e non contiene decisioni.

C'e' una sola eccezione dichiarata al congelamento: la **forma di combinazione**
di `budget_base_w` (quadratura o somma aritmetica) e' una decisione operativa
provvisoria, rinviata ai dati del pilota P2.9 e da chiudere **prima** della
campagna principale (protocollo P1.7, P1.13). La formula non si tocca nel
frattempo.

**Il codice sorgente di produzione resta bloccato fino al congelamento di P5.**
Si puo' leggere, verificare e analizzare; non si implementa la v4 prima che P5
sia chiuso. Lo stato aggiornato e' nella tabella in testa al protocollo, non qui.

---

## Metodologia congelata

Le formule sono tutte in `protocollo_v4_20261024.md`, sezione *Formulario
consolidato* (F.0-F.17), con applicazione e giustificazione per ciascuna. Qui
stanno solo le regole che un agente puo' violare senza accorgersene.

- **Nessun fallback silenzioso.** Il fallback EMI -> LHM/RAPL fa parte del
  disegno di produzione (`CW_PRIMARY_CHANNEL`, default `"emi"`,
  `energy/energy_session.py:210`), ma va sempre dichiarato: il canale per riga in
  `energy_calculation_method` (`energy/local_energy.py:98`), la finestra in
  `package_window_source` (`exact-counter | samples-fallback | unavailable`,
  `:90`), l'origine della baseline in `idle_provenance` (`:91`) e, dalla v4, in
  `baseline_backend` — campo del protocollo P1.3, non ancora presente nel codice.
  Mai presentare un fallback come un contatore.
- **Solo i token di canale reali.**
  `MEASURED_METHODS = ("emi-counter", "power-integration",
  "librehardwaremonitor-energy", "energy-file", "rapl")`
  (`energy/energy_session.py:49-50`). **CasualWatt non ha un percorso di stima
  TDP**: quello e' il percorso di CodeCarbon, usato nella tesi come contrasto. Non
  inventare un canale `estimated`.
- **Nessun doppio conteggio.** PP0 e PP1 sono sottoinsiemi di PKG: non sommare
  `PKG+PP0+PP1` e non sommare `PKG+DRAM` (`energy/emi_backend.py:29`, `:272`;
  `DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")` a `:73`). PP1 alimenta
  `igpu_energy_j`, informativo.
- **Baseline = mediana, non media.**
  `baseline_pre_w = mediana(P_rep,1..3)` su tre finestre da 30 s (P1.3). Con
  `n = 3` una finestra contaminata sposta la media ma non la mediana (P1.14).
  Si applica `P_pre`; `P_post` e' diagnostica (`dP`), mai applicata. La ragione e'
  causale: la richiesta e' l'intervento, quindi il post e' una grandezza
  post-trattamento e condizionarvi l'estimatore renderebbe la correzione
  dipendente dall'esito che deve correggere (P1.14, motivazione causale).
- **Nessun troncamento.** Gli incrementi negativi si conservano con il flag
  `negative_increment`. La produzione attuale tronca due volte
  (`energy/local_energy.py:300` e `:309-310`); la v4 non lo fa e la differenza
  va dichiarata. La regola non nasce con la v4: era gia' DP-A nella specifica
  `METODI_E_FORMULE.md` del 21-10 (`Ê_att = E_pkg^raw − E_base`, "firmata, mai
  clampata"), documento che sta in `Tesi-latex/` e quindi **fuori da git**: la
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
  indipendente.** EMI, LibreHardwareMonitor e SRUM leggono tutti
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
pytest cwEnergyModular          # 151 raccolti: 148 passati, 3 saltati (4,6 s)
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
  EMI via ctypes/SetupAPI), `energy/energy_session.py` (canali, integrazione di
  finestra, interpolazione ai bordi), `energy/local_energy.py` (campi per riga),
  `casualwatt_csv_export.py` (`CSV_COLUMNS`, righe 17-108).
- **I test stanno in due posti**: `cwEnergyModular/tests/` (114) e direttamente in
  `cwEnergyModular/` (`test_answer_type_evaluation.py`, 35;
  `test_synthetic_window.py`, 2); 114 + 37 = 151. Ogni test ha una docstring che
  dice *perche'* esiste e quale relazione matematica o fisica verifica, non solo
  cosa fa.
  L'Appendice D della tesi li elenca tutti e 151 con provenienza: se cambia la
  suite, va rigenerata con `cwEnergyModular/tools/dump_tests_latex.py`.
- **Alla radice del repo stanno 23 script `.py` tracciati**: sono gli harness
  degli esperimenti (`emi_50ms_probe.py`, `emi_resolution_check.py`,
  `four_way_test.py`, `srum.py`, `srum_emi_cross.py`, `observer_cost_probe.py`,
  `idle_floor_sensitivity.py`, `four_way_pi_audit.py`, ...). Questa e' la
  convenzione reale: **un harness il cui output e' citato dalla tesi o dal
  protocollo va tracciato**, perche' un'analisi non tracciata e' un numero che
  nessuno puo' rigenerare. Le sonde usa-e-getta non citate da nulla sono in
  `.gitignore`.
- `cwEnergyModular/tools/` — 6 file tracciati: i generatori del materiale LaTeX
  (Appendici A, D, E), l'analisi di cadenza EMI, la validazione HWiNFO.
- `experiment_results/` — dati sperimentali e analisi, tracciati (103 file). I
  protocolli congelati stanno qui. Un artefatto nuovo entra con il proprio commit
  e con la propria analisi.
- `cpuepower/`, `cpuepower2/` — toolkit sottoposto ad audit: i suoi numeri erano
  mock, la CLI crasha, la mappa MSR era sbagliata. **Banca di esperimenti, non un
  backend di misura.** Non importarlo, non citarlo come risultato.
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
  Le voci marcate `IN VERIFICA` (`dalerci2026move`, `mlenergy2025`) non vanno
  citate finche' non sono verificate alla fonte primaria. Ogni voce ha una `note`
  con gli ancoraggi e la data della verifica.
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
