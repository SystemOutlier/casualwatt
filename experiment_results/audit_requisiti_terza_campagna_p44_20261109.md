# Audit dei quattro requisiti per la terza campagna energetica P4.4

**Data:** 2026-11-09  
**Oggetto:** verifica dello stato di implementazione dei quattro requisiti metodologici posti dalla relazione `relazione_revisione_gate_p44.md` come condizioni per avviare la terza campagna del gate P4.4.  
**Autore:** revisore metodologico (senza modifiche al codice, senza commit, senza esecuzione di campagne).  
**Fonti primarie:** `relazione_revisione_gate_p44.md`, `experiment_results/protocollo_v4_20261024.md` (P1–P4 congelati, F.0–F.17), codice in `cwEnergyModular/`.

---

## 1. Sintesi esecutiva

Tutti e quattro i requisiti sono stati **implementati nel codice** e sono coerenti con la relazione di revisione. Non sono state trovate discrepanze sostanziali fra quanto dichiarato nella relazione e quanto presente nel percorso di produzione. Le condizioni che restano da soddisfare prima della terza campagna non sono di codice, ma di metodo e di governance: l'adozione formale della Quindicesima emenda, un nuovo piano dichiarato prima dei dati, e la verifica che `dt_nominal_s` (congelato a 2,930748 s dal pilota P2.9) corrisponda effettivamente al disegno della campagna.

Ogni affermazione qui sotto è ancorata a `file:riga` del codice o a un artefatto tracciato.

---

## 2. Tabella riepilogativa

| ID | Oggetto | Stato | File coinvolti | Riferimenti codice | Evidenze | Test | Discrepanze | Modifiche necessarie |
|---|---|---|---|---|---|---|---|---|
| R1 | Budget a scala Tc (stessa scala della finestra di controllo) | IMPLEMENTATO | `cwEnergyModular/tools/run_gate_p44.py` | `plan_payload()` :464; `CRITERIO_PRIMARIO = "bias_vs_budget_tc"` :922; `_calcola_budget_pre_esecuzione` :761; `BUDGET_MODE` "short"/"matched" | Soglia pre-registrata = `budget_base_w` a scala Tc; nessun fattore di scala 30 s (`scala_30_s_applicata: False` :2150); rimossa la vecchia riscalatura `Tc/30` | `test_budget_p44_preesecuzione.py` (esistente) | Nessuna | Nessuna di codice; da verificare che `budget_mode` scelto nel piano corrisponda al disegno dichiarato |
| R2 | Warm-up post-carico a criterio misurato | IMPLEMENTATO | `cwEnergyModular/tools/run_gate_p44.py` | `_stabilizza_post_carico()` :1650; `_registra_warmup()` :1635; parametri `warmup_*` nel piano :486-491; `warmup_stabilizzazione.jsonl` | Criterio su due segnali (potenza + `cpu_percent`), soglie pre-registrate sulla campagna 20261108, flag `warmup_completed`, log append-only, non entra in `bias_w` | `test_gate_p44_end_to_end.py` (esistente) | Nessuna | Nessuna di codice; le soglie sono ancorate ai dati della seconda campagna e vanno riconfermate per la terza |
| R3 | CodeCarbon solo diagnostico | IMPLEMENTATO | `cwEnergyModular/tools/run_gate_p44.py`, `cwEnergyModular/tools/codecarbon_probe.py` | Import dentro ramo `if codecarbon:` :1946; chiave `analysis["codecarbon"]` :2128; `codecarbon_usato: False` | Mai usato per `bias_w`, `budget_base_w`, `E_net`, `dt_W` o il verdetto; entra solo come chiave accanto al verdetto quando il flag è attivo | Nessun test dedicato (registro parallelo) | Nessuna | Nessuna di codice |
| R4 | Incertezza combinata senza doppio conteggio | IMPLEMENTATO | `cwEnergyModular/tools/gate_uncertainty.py`, `cwEnergyModular/tools/run_gate_p44.py` | `combina_incluse()` :63; `valida_componente()` :37; `calcola_u_c()` deprecata :83; `_incertezza_pre_esecuzione()` :939; `_incertezza_con_au_controlli()` :1088 | `u_c = None` pre-controlli (non zero); `u_A = s/sqrt(n)` post-controlli; componenti escluse con motivo dichiarato; rimossa forma `S = budget + k*u_c` (:901-908) | `test_gate_uncertainty_p44.py` (esistente, 7 test) | Nessuna | Nessuna di codice |

---

## 3. Dettaglio per requisito

### R1 — Budget di soglia alla stessa scala temporale del controllo

**Stato:** IMPLEMENTATO.

La relazione (§4, check G del piano) richiede che il budget di soglia sia stimato sulla stessa scala temporale della finestra di controllo (Tc = 2,930748 s, congelata dal pilota P2.9), non derivato da finestre da 30 s con riscalatura.

**Evidenze nel codice:**
- `run_gate_p44.py:464` `plan_payload()` dichiara `budget_mode`, `budget_n_terne`, `budget_matched_target_s`, `budget_floor_finestra_s` e `criterio_primario` prima delle misure (pre-registrazione).
- `run_gate_p44.py:761` `_calcola_budget_pre_esecuzione(mode, sessione)` calcola il budget su unità di durata Tc (modalità `short`) o su aggregati consecutivi di finestre Tc (modalità `matched`), senza alcun fattore di scala da 30 s.
- `run_gate_p44.py:2150` `analysis["budget_pre_esecuzione"]["scala_30_s_applicata"] = False`.
- `run_gate_p44.py:922` `CRITERIO_PRIMARIO = "bias_vs_budget_tc"`: il verdetto che decide confronta `|bias_w| <= budget_base_w` a scala Tc (`run_gate_p44.py:1161` `_verdetto_primario`).
- `run_gate_p44.py:901-908` documenta esplicitamente la rimozione della vecchia forma riscalata `Tc/30` e della forma `S = budget + k*u_c` (doppio conteggio).

**Test:** `test_budget_p44_preesecuzione.py` copre la stima pre-esecuzione. La guardia `_verifica_piano()` (:1210) rifiuta un piano che manchi di `budget_mode`, `budget_n_terne`, `budget_matched_target_s` o `criterio_primario`.

**Discrepanze:** nessuna trovata.

**Modifiche necessarie:** nessuna di codice. Prima della terza campagna va confermato che il `budget_mode` scelto (`short` o `matched`) sia coerente con il disegno dichiarato nel nuovo piano.

---

### R2 — Warm-up post-carico a criterio misurato

**Stato:** IMPLEMENTATO.

La relazione (§6) richiede una fase di stabilizzazione dopo ogni carico, non conteggiata come controllo, pre-registrata, di durata non fissa ma a criterio misurato, con flag di completamento.

**Evidenze nel codice:**
- `run_gate_p44.py:1650` `_stabilizza_post_carico()` implementa il criterio misurato su due segnali contemporanei (potenza del contatore entro `WARMUP_TOLERANCE_W` da `baseline_pre_w` E media di finestra di `cpu_percent` sotto `WARMUP_CPU_MAX_PCT`, per `WARMUP_SUSTAIN_S` s continui).
- `run_gate_p44.py:1635` `_registra_warmup()` scrive in `warmup_stabilizzazione.jsonl` (append-only) con identità di coppia, blocco, braccio, motivo (`criterio_soddisfatto` | `tetto_raggiunto`).
- `run_gate_p44.py:486-491` i parametri `warmup_tolerance_w`, `warmup_cpu_max_pct`, `warmup_sustain_s`, `warmup_cap_s`, `warmup_step_s`, `warmup_window_s` sono dichiarati in `plan_payload()` prima del run.
- `run_gate_p44.py:518-551` (check F del piano) documenta che il warm-up è dopo il carico, prima del controllo, non è un controllo e non entra in `bias_w`.
- Le soglie sono pre-registrate sui dati della campagna 20261108 (:531-539).

**Test:** `test_gate_p44_end_to_end.py` copre l'esecuzione end-to-end inclusa la fase di warm-up.

**Discrepanze:** nessuna trovata.

**Modifiche necessarie:** nessuna di codice. Le soglie numeriche sono ancorate alla seconda campagna e vanno riconfermate (o ridefinite) per il nuovo piano della terza campagna.

---

### R3 — CodeCarbon solo diagnostico, non criterio decisionale

**Stato:** IMPLEMENTATO.

La relazione (§7) richiede CodeCarbon come strumento diagnostico, mai usato per `bias_w`, `budget_base_w`, `E_net`, `dt_W` o il verdetto F.12.

**Evidenze nel codice:**
- `run_gate_p44.py:1946` l'import di `codecarbon_probe` è dentro il ramo `if codecarbon:` (solo con flag `--codecarbon`); senza flag il comportamento è identico a oggi.
- `run_gate_p44.py:2128` la chiave `analysis["codecarbon"]` viaggia accanto al verdetto, non dentro il riepilogo di `evaluate_gate`.
- `run_gate_p44.py:1062`, `1140` e `2151` `codecarbon_usato: False` in tutte le sezioni di incertezza e budget.
- `cwEnergyModular/tools/codecarbon_probe.py` (`ProbeCodeCarbon`, `avvia()`, `apri_blocco()`, `chiudi_blocco()`, `concludi()`) è un modulo separato, mai caricato se il flag è assente.

**Test:** nessun test dedicato (registro parallelo diagnostico). La copertura è indiretta: senza flag il gate è byte-identico a prima dell'introduzione di CodeCarbon.

**Discrepanze:** nessuna trovata.

**Modifiche necessarie:** nessuna di codice.

---

### R4 — Incertezza combinata senza doppio conteggio

**Stato:** IMPLEMENTATO.

La relazione (§4-§5) proponeva la forma `S = B_matched + k * u_c` con `k = 2`. Il codice ha rimosso questa forma perché `u_rumore` e `u_termico` erano già contenuti in `budget_base_w = hypot(...)`, il che avrebbe prodotto `S >= 3 * budget` e fatto passare entrambi i gate falliti (:901-908). Sostituita con `u_c = RSS delle sole componenti incluse`, tipo A/B dichiarato, inclusione esplicita.

**Evidenze nel codice:**
- `gate_uncertainty.py:63` `combina_incluse()` restituisce la RSS delle sole componenti con `inclusa=True`; `None` se nessuna inclusa (non zero); `ValueError` su forma non conforme.
- `gate_uncertainty.py:37` `valida_componente()` richiede `tipo ∈ {"A","B"}`, `inclusa` booleano, `motivo` non vuoto, `value` finito non negativo se inclusa.
- `run_gate_p44.py:939` `_incertezza_pre_esecuzione()`: tutte le componenti (`u_rumore`, `u_termico`, `u_timer`, `u_allineamento`) hanno `inclusa: False`; `u_c = None` pre-controlli; soglia = `budget_base_w` senza maggiorazioni (:1045-1057).
- `run_gate_p44.py:1088` `_incertezza_con_au_controlli()`: `u_A = s/sqrt(n)` (tipo A) inclusa post-controlli; `k = t(0,975, n-1)`; `U = k * u_c` riportata ma non decisiva (:1134).
- `run_gate_p44.py:1190` `_accettazione_guardata()`: `|bias| + U <= budget` (JCGM 106:2012) è grandezza riportata, non criterio (:1206-1207).

**Test:** `test_gate_uncertainty_p44.py` (7 test: RSS delle sole incluse, `None` non zero, errore su inclusione con valore non finito, errore su forma non conforme, componente esclusa con valore informativo, doppio conteggio storico riproducibile e non più prodotto).

**Discrepanze:** nessuna trovata. La vecchia funzione `calcola_u_c` è deprecata ma mantenuta per retro-compatibilità (:83-107) e non è più usata dal gate.

**Modifiche necessarie:** nessuna di codice.

---

## 4. Condizioni obbligatorie aggiuntive (non di codice)

La relazione (§9) stabilisce due condizioni obbligatorie che **non sono state ancora adottate** e che bloccano l'avvio della terza campagna:

1. **Quindicesima emenda.** La terza campagna deve essere condotta solo dopo l'adozione formale della Quindicesima emenda. Nella relazione (§9): «La terza campagna deve essere condotta solo dopo l'adozione formale della Quindicesima emenda e del nuovo piano.» Nel repository non sono stati trovati riferimenti espliciti a una «Quindicesima emenda» (è presente invece la Tredicesima emenda, `experiment_results/protocollo_v4_20261024.md` punto 6). L'emenda deve formalizzare almeno: la nuova soglia coerente con la scala Tc (già nel codice), la regola di combinazione dell'incertezza (già nel codice), il nuovo disegno con 12 coppie e quorum `ceil(2/3 * 12) = 8` (deciso nella decisione 6 della seconda campagna, `experiment_results/confronto_campagne_p44_20261108.md`).

2. **Nuovo piano dichiarato prima dei dati.** La relazione (§9) e il codice (`run_gate_p44.py:1210` `_verifica_piano`) richiedono che il piano sia dichiarato prima di qualsiasi misura. La guardia `_verifica_piano` rifiuta l'esecuzione se `plan.json` manca o è discordante con `plan_blocks()`, `n_coppie`, `n_blocchi`, `order_seed`, `model`, `criterio_primario` e i parametri di quiete/warm-up/budget. Questo piano deve essere committato con la derivazione dichiarata dei numeri, come previsto dalla regola dura di AGENTS.md («Le soglie sono congelate prima dei dati»).

3. **Provenienza di `dt_nominal_s`.** Al 07-11-2026 `dt_nominal_s` era congelato a 2,930748 s dal pilota P2.9 (`experiment_results/p29_pilot_20261107/dt_nominal_frozen.json`), ma le durate sopravvissute nel CSV del runner v4 erano di un altro run del 06-11 sera, non del pilota che il requisito 5 del protocollo nomina. Va verificato che il valore congelato corrisponda effettivamente al disegno della terza campagna prima di usarlo come soglia.

---

## 5. Piano di intervento ordinato per priorità e dipendenze

| Priorità | Azione | Dipendenze | Output |
|---|---|---|---|
| 1 (bloccante) | Adozione formale della Quindicesima emenda che congeli: soglia coerente con scala Tc, regola di combinazione incertezza, disegno 12 coppie / quorum 8 | Nessuna (documento di governance) | Emenda committata in `experiment_results/` |
| 2 (bloccante) | Nuovo piano `plan.json` dichiarato prima dei dati, con tutti i parametri richiesti da `_verifica_piano` (:1210-1247) | Quindicesima emenda (priorità 1) | `plan.json` committato con derivazione dichiarata dei numeri |
| 3 (bloccante) | Verifica della provenienza di `dt_nominal_s = 2,930748 s` rispetto al disegno della terza campagna | Nessuna | Conferma scritta o nuovo congelamento da pilota P2.9 |
| 4 (non bloccante) | Riconferma o ridefinizione delle soglie di warm-up (ancorate alla campagna 20261108) per la terza campagna | Nuova campagna pianificata | Parametri `warmup_*` aggiornati nel piano |
| 5 (non bloccante) | Esecuzione della terza campagna P4.4 | Tutte le precedenti | Artefatti congelati (`analysis.json`, `gate_result_frozen.json`, ecc.) |

**Nota:** non sono necessarie modifiche al codice di produzione prima della terza campagna. Tutti e quattro i requisiti sono già implementati e la suite di test è verde. L'unico lavoro residuo è di metodo e governance (emenda, piano, verifica provenienza).

---

## 6. Limitazioni e note

- Questo audit è una verifica di corrispondenza fra relazione e codice. Non costituisce esecuzione della campagna né validazione sperimentale dei numeri.
- I conteggi della suite di test citati in precedenza (1154 passed, 4 skipped) si riferiscono all'albero al momento dell'ultimo commit; non sono stati rieseguiti in questa sessione.
- Nessun file è stato modificato, nessun commit è stato creato, nessuna campagna è stata avviata.
- Il file `.casualwatt_keys.json` non è stato toccato, né creato, né letto, né scritto.

---

Fonti:
- [`relazione_revisione_gate_p44.md`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/relazione_revisione_gate_p44.md) — relazione di revisione del gate P4.4 (2026-11-09).
- [`experiment_results/protocollo_v4_20261024.md`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/experiment_results/protocollo_v4_20261024.md) — protocollo congelato P1–P4, formulario F.0–F.17.
- [`cwEnergyModular/tools/run_gate_p44.py`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/cwEnergyModular/tools/run_gate_p44.py) — gate P4.4 (righe ancorate nel testo).
- [`cwEnergyModular/tools/gate_uncertainty.py`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/cwEnergyModular/tools/gate_uncertainty.py) — regola di combinazione incertezza.
- [`cwEnergyModular/tests/test_gate_uncertainty_p44.py`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/cwEnergyModular/tests/test_gate_uncertainty_p44.py) — test della regola di combinazione.
- [`experiment_results/confronto_campagne_p44_20261108.md`](/C:/Users/Massimo/Documents/CasualWatt/CWProject/experiment_results/confronto_campagne_p44_20261108.md) — confronto campagne e decisione 6 (12 coppie, quorum 8).