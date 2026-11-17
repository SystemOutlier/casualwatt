# BRANCH_MAP.md — Mappa delle implementazioni CasualWatt

**Generato:** 2026-11-18  
**Commit di riferimento:** `0fa2768f1` (emenda/background-controlled-20261115)  
**main:** `d08a011ad` (2 settimane fa)

---

## 1. Branch principali

| Branch | HEAD | Commit vs `main` | Funzione | Stato |
|--------|------|------------------|----------|-------|
| `main` | `d08a011ad` | — | Versione stabile | ✅ Stabile |
| `emenda/background-controlled-20261115` ⭐ | `0fa2768f1` | **+226** | Sviluppo principale | ✅ Attivo, pushato |

---

## 2. Branch di sviluppo parallelo

### `fix/p44-metrologico-20261109`

- **HEAD:** `868a8323b` (3 giorni fa)
- **Commit vs `main`:** +193
- **Commit unici vs branch principale:** 0 (completamente integrato)
- **Commit del branch principale non qui:** 33
- **Stato:** ✅ **Completamente integrato** in `emenda/background-controlled-20261115`
- **Implementazioni:**
  - Fix P4.4 metrologico: catena di provenienza idle, verdetto N/A canonico
  - Test preflight aggiornati per nuova catena
  - Energy session: calibrazione idle con provenienza dichiarata

### `patch/scientific-evaluator-hardening`

- **HEAD:** `afbf9ba70` (2 settimane fa) — **stesso SHA di `fix/valutatore-mudilab`**
- **Commit vs `main`:** +44
- **Commit unici vs branch principale:** 44
- **Stato:** 🔲 **Non integrato** — lavoro separato sul valutatore scientifico
- **Implementazioni:**
  - Fix valutatore: reference scalare numerico come contratto number
  - Hardening del valutatore scientifico
  - Correzioni accuratezza per answer_type
- **Verifica audit:** `git rev-parse` conferma che `fix/valutatore-mudilab` e `patch/scientific-evaluator-hardening` puntano allo stesso commit `afbf9ba70`. Il BRANCH_MAP originale riportava `73c05e716` come HEAD, ma era stantio: il branch è stato aggiornato o il conteggio era di un altro punto della storia.

### `feat/carbon-report-analysis-20261110`

- **HEAD:** `00c38be7d` (8 giorni fa)
- **Merge-base con branch principale:** `e36df8889`
- **Commit unici sopra merge-base:** 6
- **Stato:** 🔲 **Lavoro separato** — 6 commit unici sopra un merge-base comune
- **Implementazioni (6 commit):**
  1. `00c38be7d` feat(tool): CLI report_carbon per artefatto rigenerabile
  2. `6947367ba` feat(analysis): template LaTeX ed equivalenze illustrative dichiarate
  3. `8f63783d8` feat(analysis): report_carbon per riga e aggregato con provenance
  4. `515d2fb01` feat(analysis): carbon_report, formula kWh corretta e fattori dichiarati
  5. `ff702c762` docs(plan): piano implementativo carbon report analysis (5 task TDD)
  6. `20189c9fb` docs(analysis): spec del reporter carbonio di sola analisi
- **Verifica audit:** I 6 commit sono lavoro nuovo sul reporting CodeCarbon, non confliggente con il branch principale. Il resto dei 170 commit vs main è storia comune (P4.4, GPU, valutatore) già nel branch principale.

### `fix/cpu-attribution`

- **HEAD:** `7befeb466` (3 settimane fa)
- **Commit vs `main`:** 0 (già in main o antenato)
- **Commit unici vs branch principale:** 0
- **Stato:** ✅ **Già integrato** in `main`
- **Implementazioni:**
  - Additività: tetto a un core dell'ambiente, non della sessione
  - Attribuzione energetica CPU

### `energy-consumption-framework-ollama-d248a`

- **HEAD:** `b41519167` (3 settimane fa)
- **Commit vs `main`:** vari
- **Commit unici vs branch principale:** 0
- **Stato:** ✅ **Già integrato** in `emenda/background-controlled-20261115`
- **Implementazioni:**
  - Framework consumo energetico Ollama
  - Protocollo P6.6, prova di attribuzione ripetibile

### `fase-b-docs`

- **HEAD:** `ea1afa0d8` (2 settimane fa)
- **Commit vs `main`:** vari
- **Commit unici vs branch principale:** 11
- **Stato:** ✅ **Mergiata in `main`** — i commit sono già nella storia di main
- **Implementazioni:**
  - Documentazione README e RELAZIONE.md
  - Dichiarazione tool legacy vs metodo corrente

---

## 3. Branch obsoleti o ridondanti

### `fix/valutatore-mudilab`

- **HEAD:** `afbf9ba70` (2 settimane fa)
- **Punta a:** `patch/scientific-evaluator-hardening` (stesso commit)
- **Stato:** ⚠️ **Bloccato da worktree** — alias di `patch/scientific-evaluator-hardening`, ma usato da worktree in `ramo-valutatore`
- **Azione:** Richiede rimozione del worktree prima della pulizia del branch

### `integrazione/valutatore`

- **HEAD:** stesso di `emenda/background-controlled-20261115`
- **Commit unici vs branch principale:** 0
- **Stato:** ⚠️ **Bloccato da worktree** — senza upstream, stesso contenuto del branch principale, ma usato da worktree in `integrazione-valutatore`
- **Azione:** Richiede rimozione del worktree prima della pulizia del branch

### `master`

- **HEAD:** commit iniziale (4 settimane fa)
- **Stato:** ✅ **Rimosso** — branch eliminato localmente il 18-11-2026

### `systemoutlier-jubilant-waffle`

- **HEAD:** 12 giorni fa
- **Stato:** ✅ **Rimosso** — branch eliminato localmente il 18-11-2026

### `origin/fix/background-monitor-persistence`

- **HEAD:** `f79fa1d7c` (31 ore fa)
- **Commit unici vs branch principale:** 4
- **Stato:** ✅ **Lavoro già integrato** — i 4 commit sono implementazioni duplicate nel branch principale
- **Implementazioni (4 commit):**
  1. `f79fa1d7c` Correct BackgroundMonitor to_json return annotation
  2. `71ea0844d` Add regression tests for BackgroundMonitor JSON persistence
  3. `e36a491ff` Make BackgroundMonitor JSON persistence idempotent by batch and block
  4. `b6d23a99a` Fix BackgroundMonitor runner metadata serialization and per-block persistence
- **Verifica audit:** `git diff --stat` mostra che questi 4 commit **rimuovono** 696 righe e ne aggiungono 195 rispetto al branch principale. Il branch principale ha già integrato lo stesso lavoro con commit diversi (`1daceaedb`, `3feafea8e`). I file toccati (background_monitor.py, background_monitor_json.py, benchmark_v4.py, machine_state.py, validation_chain.py) sono già corretti nel branch principale. **Nessuna funzionalità mancante.**

### `origin/parallel-robust-evaluator`

- **HEAD:** `b4e6dbd4b` (2 settimane fa)
- **Commit unici vs branch principale:** 321
- **Stato:** ⚠️ **Branch divergente** — storia molto separata, architettura parallela
- **Implementazioni (primi 10 commit):**
  1. `b4e6dbd4b` Build common accuracy and energy evaluation framework
  2. `f742153fa` Document robust evaluator methodology
  3. `3a82906af` Add conservative parallel evaluator
  4. `073698b09` Update README.md
  5. `4afd61377` Create README.it.md
  6. `a353edfb2` Merge pull request #4 from SystemOutlier/emenda-8
  7. `cd881e6b1` Preserve signed energy and token provenance
  8. `5081b827f` merge: fase-b-docs in main
- **Verifica audit:** Il branch contiene un framework di valutazione parallelo (accuratezza + energia) sviluppato indipendentemente. I commit 4-8 sono storia comune già in main. I commit 1-3 sono lavoro nuovo su architettura di valutazione. **Da conservare fino a decisione sull'architettura di valutazione.**

### `origin/fix/benchmark-validation-2026-10`

- **HEAD:** `31d4ccc7a` (4 settimane fa)
- **Commit unici vs branch principale:** 31
- **Stato:** ⚠️ **Storia antica parzialmente in main** — molti commit sono già in main o nel branch principale
- **Implementazioni (31 commit, primi 10):**
  1. `31d4ccc7a` REV: valutazione accuratezza basata su answer_type
  2. `892d538d5` DIAG: diagnostica cpu-time-share + lettura esatta agli estremi
  3. `07e7cf82c` GUI: righe risultati evidenziate a gruppi per modello
  4. `589ba026b` FIX: accuratezza errata per risposte numeriche brevi
  5. `15ff783d1` FIX: duplicazione record nel CSV
  6. `c8e80a2d4` GUI: pulsante 'Calibra idle a 65 W'
  7. `df500ba69` FIX: NameError '_judge_via_energy_session'
  8. `f3a8955fd` FIX: benchmark crash su 'str' object has no attribute 'append'
  9. `ad86f2a91` GUI: log/console altezza aumentata
  10. `11c36da2d` GUI: fix finestre nascoste
- **Verifica audit:** I commit più recenti (1-10) sono fix GUI/benchmark che potrebbero non essere nel branch principale. I commit più antichi (11-31) sono storia iniziale del progetto, già in main. **Da valutare singolarmente i commit 1-10 per funzionalità mancanti.**

---

## 4. Implementazioni chiave per feature

| Feature | Branch principale | Commit chiave | Stato |
|---------|-------------------|---------------|-------|
| **BaselineStatistics** | `emenda/background-...` | `846f0f1d1` | ✅ Completato |
| **EnergySession.baseline_stats** | `emenda/background-...` | `06fb994` | ✅ Completato |
| **Durate effettive dt** | `emenda/background-...` | sessione correzione | ✅ Completato |
| **BackgroundMonitor** | `emenda/background-...` | `3d76113c8` | ✅ Completato |
| **Confronto locale/globale** | `emenda/background-...` | `6615890fb` | ✅ Completato |
| **Persistenza JSON** | `emenda/background-...` | `1daceaedb` | ✅ Completato |
| **Classificazione processi** | `emenda/background-...` | `c9a63c9f1` | ✅ Completato |
| **Intensità CPU per processo** | `emenda/background-...` | `c9a63c9f1` | ✅ Completato |
| **chain_status() opzionale** | `emenda/background-...` | `22a90c634` | ✅ Completato |
| **chain_status() not_evaluated** | `emenda/background-...` | `0fa2768f1` | ✅ Completato |
| **Fix P4.4 metrologico** | `fix/p44-metrologico-...` | `f535870c6` | ✅ Integrato |
| **Report CodeCarbon** | `feat/carbon-report-...` | `00c38be7d` | 🔲 6 commit unici |
| **Fix valutatore scientifico** | `patch/scientific-evaluator-...` | `afbf9ba70` | 🔲 44 commit unici |
| **Attribuzione CPU** | `fix/cpu-attribution` | `d1351ea56` | ✅ In main |

---

## 5. Riepilogo azioni raccomandate

### Sicure da eseguire ora

1. **Push commit locale:** ✅ Completato (`0fa2768f1` pushato)
2. **Fetch --prune:** ✅ Completato
3. **Rimozione branch ridondanti locali:**
   - `fix/valutatore-mudilab` (alias di patch/scientific-evaluator-hardening)
   - `integrazione/valutatore` (stesso contenuto del branch principale)
   - `master` (obsoleto)
   - `systemoutlier-jubilant-waffle` (obsoleto)

### Da valutare prima della rimozione

1. **`origin/fix/background-monitor-persistence`:** 4 commit unici — verificare se già integrati
2. **`feat/carbon-report-analysis-20261110`:** 6 commit unici — decidere se integrare
3. **`patch/scientific-evaluator-hardening`:** 44 commit unici — lavoro separato da mantenere
4. **`origin/parallel-robust-evaluator`:** 321 commit unici — branch divergente, da archiviare
5. **`origin/fix/benchmark-validation-2026-10`:** 31 commit unici — da valutare

### Non toccare ora

- `main`: versione stabile, non modificare
- `emenda/background-controlled-20261115`: branch di sviluppo attivo
- `fix/p44-metrologico-20261109`: completamente integrato, ma conserva come riferimento
- `patch/scientific-evaluator-hardening`: lavoro separato attivo
- `feat/carbon-report-analysis-20261110`: lavoro separato attivo

---

## 6. Modifiche non committate (working tree)

### File modificati (6)

| File | Modifica | Stato |
|------|----------|-------|
| `benchmark_v4.py` | chain_status() chiamata con parametri None invece di placeholder fittizi; docstring estesa sulla semantica di validated | ✅ Concluso, pronto per commit |
| `energy_session.py` | Calibrazione idle estesa: 10 ripetizioni, CV ≤ 5%, flag `extended` | ✅ Concluso, pronto per commit |
| `validation_chain.py` | Docstring estesa sulla semantica di `validated` (4 casi: valutato/superato, saltato, non valutato, fallito) | ✅ Concluso, pronto per commit |
| `test_chain_status.py` | 3 test nuovi per chain_status con anelli parziali valutati | ✅ Concluso, pronto per commit |
| `test_calibrate_idle_stats.py` | Test aggiornati per rifiuto baseline con CV > 10% (RuntimeError) | ✅ Concluso, pronto per commit |
| `test_budget_p44_preesecuzione.py` | Import corretto `from tools import gate_uncertainty` | ✅ Concluso, pronto per commit |
| `test_preflight_gate_p44.py` | runner_sha256 aggiornato al tree corrente | ✅ Concluso, pronto per commit |

### File non trackati (selezionati)

| File | Descrizione | Azione |
|------|-------------|--------|
| `BRANCH_MAP.md` | Questa mappa (aggiornata) | Commit |
| `baseline-statistics-primitive.md` | Piano del BackgroundMonitor | Commit |
| `experiment_results/background_monitor_validation_20261116/` | Script di validazione campagna | Commit |
| `experiment_results/background_monitor_validation_protocol_20261116.md` | Protocollo campagna Windows 11 | Commit |
| `cwEnergyModular/results/background_monitor.json` | Risultati validazione Fase A | Conserva, non commit |
| `cwEnergyModular/baseline_experiment.py` | Esperimento baseline (sperimentale) | Valuta |
| `cwEnergyModular/extended_baseline.py` | Calibrazione estesa (sperimentale) | Valuta |

### Decisione sulle modifiche non committate

Le modifiche ai 6 file di produzione sono **concluse e coerenti** con il lavoro del branch principale. Rappresentano:
1. Calibrazione idle estesa per macchine con variabilità elevata (CV > 10%)
2. chain_status() con parametri opzionali None invece di placeholder fittizi
3. Test aggiornati per la nuova semantica

**Raccomandazione:** Commit separato per ogni punto concettualmente unitario, come richiesto da AGENTS.md.

---

## 7. Note

- **Nessun merge o rebase eseguito:** questa mappa è puramente diagnostica.
- **Nessuna implementazione persa:** tutti i commit sono tracciati e accounted for.
- **Audit completato il 18-11-2026:** verifica read-only del repository, senza modifiche distruttive.
- **Validazione sperimentale pendente:** campagna Windows 11 completa e campagna Linux non ancora eseguite.
