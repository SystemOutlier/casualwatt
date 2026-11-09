# Quindicesima emenda — bozza (budget di soglia del gate P4.4)

**Data:** 2026-11-09  
**Oggetto:** bozza della Quindicesima emenda al protocollo v4 (P1–P4 congelati, F.0–F.17) per la terza campagna del gate P4.4 (load-versus-control).  
**Stato:** bozza di emenda da adottare PRIMA della terza campagna. Non è ancora adottata.  
**Vincoli osservati:** nessuna modifica a codice di produzione, nessuna modifica a dati/risultati, nessun commit, nessuna terza campagna avviata. Tutti i claim sono ancorati a `file:riga` o ad artefatti tracciati in `experiment_results/`.

---

## Premessa

La seconda campagna del gate P4.4 (08-11-2026) si è chiusa con il criterio primario B (`|bias_w| <= budget_base_w` a scala Tc) in **fail**: `|bias_w| = 0,125171 W` contro `mediana_c(budget_base_w) = 0,117995 W`, quorum 6/6 raggiunto. La prima campagna (07-11-2026) è anch'essa in **fail** (`|bias_w| = 0,479571 W` contro `0,262324 W`, quorum 4/6). In entrambe, l'applicazione della vecchia forma `S = budget + k * u_c` con `u_c` comprendente `u_rumore` e `u_termico` (già contenuti in `budget_base_w`) avrebbe convertito fail corretti in pass spuri per doppio conteggio (dimostrato in `experiment_results/audit_integrativo_p44_20261109.md:punto 1` e `experiment_results/p44_verifica_metrologica_20261109.md:punto 5`).

La Quindicesima emenda congela, come documenti di governance, le scelte già implementate nel codice di produzione:

- il criterio primario `|bias_w| <= budget_base_w` a scala Tc (`run_gate_p44.py:922`, `:1161`);
- la regola di combinazione dell'incertezza (RSS delle sole componenti incluse, `u_c = None` se nessuna, divieto di doppio conteggio) (`gate_uncertainty.py:37`, `:63`; `run_gate_p44.py:939-1063`, `:1088-1141`);
- il nuovo disegno con 12 coppie e quorum `ceil(2/3 * 12) = 8` (decisione 6 della seconda campagna, `experiment_results/confronto_campagne_p44_20261108.md`);
- la provenienza e il congelamento di `dt_nominal_s = 2,930748 s` dal pilota P2.9 (`experiment_results/p29_pilot_20261107/dt_nominal_frozen.json`).

---

## Articolo 1 — Criterio primario e soglia a scala Tc

> Il criterio primario del gate P4.4 è `|bias_w| <= budget_base_w` a scala Tc, con `Tc = dt_nominal_s` congelato dal pilota P2.9 (requisito 5 del protocollo). Il budget `budget_base_w` è misurato PRIMA dei blocchi (pre-registrato) sulla stessa scala temporale della finestra di controllo. Il verdetto F.12 storico (mediana dei budget per blocco derivati da finestre da 30 s) resta calcolato e riportato accanto ma NON decide.

**Ancoraggio:** `cwEnergyModular/tools/run_gate_p44.py:891-920` (commenti criterio), `:922` (`CRITERIO_PRIMARIO = "bias_vs_budget_tc"`), `:1161` (`_verdetto_primario`).

**Motivo:** chiude il mismatch di scala fra budget (finestre da 30 s) e controllo (Tc = 2,930748 s) individuato nella relazione di revisione cap. 3.

---

## Articolo 2 — Regola di combinazione dell'incertezza e divieto di doppio conteggio

> `u_c` è la somma in quadratura (RSS) delle sole componenti con `inclusa = True`; se nessuna è inclusa, `u_c = None` (non zero). Le componenti `u_rumore` (`half_range_pre_w`) e `u_termico` (`half_drift_w`) sono già contenute in `budget_base_w = hypot(half_range_pre_w, half_drift_w)` per costruzione; vanno dichiarate `inclusa = False` con motivo esplicito. La forma `S = budget + k * u_c` è rimossa e non può essere reintrodotta senza un'analisi di doppio conteggio documentata. `u_A = s / sqrt(n)` (tipo A, post-controlli) è l'unica componente inclusa in `u_c` dopo i controlli; `U = t(0,975, n-1) * u_c` è grandezza riportata, non criterio decisivo.

**Ancoraggio:** `cwEnergyModular/tools/gate_uncertainty.py:37` (`valida_componente`), `:63` (`combina_incluse`); `cwEnergyModular/tools/run_gate_p44.py:969-993` (`inclusa = False` con motivo), `:1088-1124` (`u_A` inclusa post-controlli), `:1190-1207` (banda di guardia riportata, non decisiva).

**Motivo:** il doppio conteggio è dimostrato matematicamente (punto 1 dell'audit integrativo): con `u_rumore` e `u_termico` inclusi in `u_c`, `u_c = budget_base_w` e quindi `S >= 2 * budget_base_w` (per `k >= 1`) o `S >= 3 * budget_base_w` (per `k >= 2`), convertendo fail veri in pass spuri in entrambe le campagne eseguite.

---

## Articolo 3 — Natura provvisoria della quadratura di budget_base_w

> `budget_base_w = sqrt(half_range_pre_w^2 + half_drift_w^2)` è un proxy di incertezza standard, non una deviazione standard né un limite massimo garantito. `half_range_pre_w` e `half_drift_w` sono semi-range conservativi; a `n = 3` non si stima una varianza (P4.12). La quadratura è appropriata solo sotto l'ipotesi che i due termini non siano perfettamente correlati positivamente; l'indipendenza non è assunta implicitamente e va dichiarata per ogni componente inclusa in `u_c`. Per soglie del gate che richiedano una garanzia più forte si applica un fattore di copertura separato, dichiarato come tale, senza toccare la formula del budget.

**Ancoraggio:** `experiment_results/protocollo_v4_20261024.md:3728-3749` (Emenda 8, P2.9/P1.7), `:537-591` (P1.7 Incertezza di baseline).

**Motivo:** l'Emenda 8 ha lasciato la forma provvisoria in attesa di un'analisi di sensibilità documentata (linee 579-581 del protocollo). L'emenda dichiara che tale analisi è demandata al piano pre-registrato della terza campagna.

---

## Articolo 4 — Disegno 12 coppie e quorum

> Il disegno della campagna è 12 coppie (24 blocchi: 12 load + 12 control), con quorum di F.12 pari a `ceil(2/3 * 12) = 8` controlli utilizzabili. Il piano `plan.json` deve dichiarare `budget_mode`, `budget_n_terne`, `budget_matched_target_s`, `budget_floor_finestra_s` e `criterio_primario` prima di qualsiasi misura; `_verifica_piano` rifiuta l'esecuzione se questi parametri mancano o sono discordanti.

**Ancoraggio:** `cwEnergyModular/tools/run_gate_p44.py:1210` (`_verifica_piano`), `experiment_results/p44_gate_20261109/plan.json` (piano corrente, 12 coppie, `budget_mode = short`).

**Motivo:** decisione 6 della seconda campagna (`experiment_results/confronto_campagne_p44_20261108.md`).

---

## Articolo 5 — Provenienza e congelamento di dt_nominal_s

> `dt_nominal_s` è fissato PRIMA della campagna principale come `3 * mediana(duration_s delle righe valide del pilota P2.9)`. Il valore congelato è `dt_nominal_s = 2,930748 s` (mediana `0,976916 s` su 10 righe), con SHA-256 del CSV di fonte e run ID dichiarati in `dt_nominal_frozen.json`. Qualsiasi riuso del valore richiede nuova verifica indipendente del SHA-256 e della mediana contro il CSV originale.

**Ancoraggio:** `experiment_results/p29_pilot_20261107/dt_nominal_frozen.json`, `experiment_results/p29_pilot_20261107/casualwatt_v4_results_p29.csv` (SHA-256 `e8fbfabed8a5a2289481a950b7bc88b636738574cb34aca4a59076cb9013204e`).

**Motivo:** requisito 5 del protocollo P4.4; il valore è stato verificato indipendentemente nell'audit integrativo del 2026-11-09 (punto 4) e nel rapporto di verifica metrologica (punto 7).

---

## Sintesi delle modifiche documentali

| Articolo | Oggetto | Stato nel codice | Azione documentale |
|---|---|---|---|
| 1 | Criterio primario a scala Tc | Implementato (`:922`, `:1161`) | Congelare in emenda |
| 2 | Regola combinazione incertezza, no doppio conteggio | Implementato (`gate_uncertainty.py:63`, `run_gate_p44.py:969-993`) | Congelare in emenda |
| 3 | Quadratura provvisoria, non limite garantito | Implementato (`protocollo_v4_20261024.md:3735-3749`) | Dichiarare provvisoria, demandare analisi di sensibilità al piano |
| 4 | 12 coppie, quorum 8 | Piano esistente (`plan.json`) | Congelare in emenda |
| 5 | Provenienza dt_nominal_s | Verificato indipendentemente | Congelare SHA-256 e mediana in emenda |

---

**Nessuna modifica a codice di produzione, nessun dato alterato, nessun commit, nessuna terza campagna avviata.** L'adozione formale di questa emenda è condizione obbligatoria per l'avvio della terza campagna (relazione di revisione cap. 9 e `experiment_results/audit_requisiti_terza_campagna_p44_20261109.md:punto 4`).
