# Audit integrativo del rapporto di verifica metrologica P4.4 — 2026-11-09

**Data:** 2026-11-09  
**Oggetto:** Audit integrativo delle grandezze metrologiche del gate P4.4 (load-versus-control). Cinque punti: definizioni B_matched/u_c/u_rumore/u_termico/k/S, giustificazione della quadratura (Emenda 8), statistica di bias_w e U, verifica indipendente del pilota P2.9, proposte documentali per la Quindicesima emenda.  
**Stato:** rapporto di audit, non documento di emenda adottato.  
**Vincoli osservati:** nessuna modifica a codice di produzione, nessuna modifica a dati/risultati, nessun commit, nessuna terza campagna avviata. Tutti i claim ancorati a file:riga o ad artefatti tracciati in `experiment_results/`.

---

## 0. Riferimenti primari usati

| Artefatto | Percorso | Ruolo |
|---|---|---|
| Relazione revisione gate P4.4 | `relazione_revisione_gate_p44.md` | Propone S = B_matched + k*u_c (cap.4-5), componenti incertezza (cap.5), warm-up (cap.6), CodeCarbon (cap.7) |
| Protocollo v4 | `experiment_results/protocollo_v4_20261024.md` | Formulario F.0-F.17, P1.7 (linee 537-595), Emenda 8 (linee 3635-3754), F.4 (linee 3042-3063), F.12 (linee 3308-3329) |
| Modulo incertezza | `cwEnergyModular/tools/gate_uncertainty.py` | `valida_componente` (linea 37), `combina_incluse` (linea 63), `calcola_u_c` deprecata (linea 83) |
| Runner gate P4.4 | `cwEnergyModular/tools/run_gate_p44.py` | Commenti criterio (linee 891-920), `_calcola_budget_pre_esecuzione` (linea 761), `_incertezza_pre_esecuzione` (linea 939), `_incertezza_con_au_controlli` (linea 1088), `_verdetto_primario` (linea 1161), `_accettazione_guardata` (linea 1190) |
| Frozen P2.9 | `experiment_results/p29_pilot_20261107/dt_nominal_frozen.json` | `dt_nominal_s = 2.930748`, mediana 0.976916, SHA-256 dichiarato |
| CSV pilota P2.9 | `experiment_results/p29_pilot_20261107/casualwatt_v4_results_p29.csv` | 10 righe valide, `test_source = pilot_p29` |
| Campagna 1 | `experiment_results/p44_gate_20261107/analysis.json` + `blocks_controllo.json` | bias_w = 0.479571 W, soglia = 0.262324 W, 4/6 utilizzabili |
| Campagna 2 | `experiment_results/p44_gate_20261108/analysis.json` + `blocks_controllo.json` | bias_w = 0.125171 W, soglia = 0.117995 W, 6/6 utilizzabili |

---

## 1. Definizioni originali e complete delle grandezze del criterio A

### 1.1 Testo originale della relazione (cap.4)

Nella relazione `relazione_revisione_gate_p44.md`:

- **Linee 41-49:** «La soglia va riformulata come: S = B_matched + k * u_c. dove: B_matched è il budget stimato sulla stessa scala temporale del controllo; u_c è l'incertezza combinata della misura; k è il fattore di copertura, pre-registrato, con default k = 2.»
- **Linea 67:** «La regola proposta è: bias_w <= mediana_c(B_{w,c}^{Tc}) + 2 * u_c»

### 1.2 Distinzione grandezze identiche vs analoghe

| Grandezza | Definita in | Identica a | Analoghe (NON identiche) |
|---|---|---|---|
| `budget_base_w` | Protocollo P1.7/F.4 (`protocollo_v4_20261024.md:542`) | `hypot(half_range_pre_w, half_drift_w)` | `B_matched` non esiste come campo calcolato nel codice; è una proposta non implementata |
| `half_range_pre_w` | Protocollo P1.7/F.4 (linea 540) | Proxy di `u_rumore` nella relazione cap.5 | `u_rumore` della relazione è «dispersione delle baseline»; nel codice `u_rumore` = `half_range_pre_w` (semi-range, non deviazione standard) |
| `half_drift_w` | Protocollo P1.7/F.4 (linea 541) | Proxy di `u_termico` nella relazione cap.5 | `u_termico` della relazione è «transitorio termico, warm-up e margine dichiarato»; nel codice `u_termico` = `|dP|/2` (deriva fra mediana pre e post, nessun canale termico usato come criterio) |
| `u_c` | `gate_uncertainty.py:63` `combina_incluse` | RSS delle sole componenti incluse | Nella relazione cap.4-5 `u_c` sarebbe inclusa in `S = B_matched + k*u_c`; nel codice post-controlli `u_c = u_A` solo (tipo A, s/sqrt(n)) |
| `k` | Relazione cap.4 (default k=2) | Fattore di copertura pre-registrato | Non dichiarato nel codice vigente (`k = None` pre-esecuzione, `k = t(0.975,n-1)` post-controlli solo per U, non per S) |
| `S` | Relazione cap.4 (linea 43) | `S = B_matched + k*u_c` | Forma RIMOSSA dal codice (`run_gate_p44.py:901-908`); il criterio vigente è `B` (`|bias_w| <= budget_base_w`), non `A` |

### 1.3 Doppio conteggio: dimostrato, condizionato o non dimostrabile?

**DIMOSTRATO** (condizione: `u_rumore` e `u_termico` incluse in `u_c`).

Dimostrazione matematica (`run_gate_p44.py:901-908`, `gate_uncertainty.py:63`):

```
budget_base_w = hypot(u_rumore, u_termico) = sqrt(u_rumore^2 + u_termico^2)
```

Se `u_c` include entrambe:

```
u_c = sqrt(u_rumore^2 + u_termico^2) = budget_base_w
S = budget_base_w + k * u_c = (1 + k) * budget_base_w
```

Per `k >= 1`: `S >= 2 * budget_base_w`  
Per `k = 2`: `S = 3 * budget_base_w`

Conseguenza quantitativa sulle due campagne (verificata aritmeticamente nel rapporto `p44_verifica_metrologica_20261109.md:177-187`):

- Campagna 2: `S = 3 * 0.117995 = 0.353985 W` vs `bias_w = 0.125171 W` → falso pass
- Campagna 1: `S = 3 * 0.262324 = 0.786972 W` vs `bias_w = 0.479571 W` → falso pass

**Conclusione punto 1:** Il doppio conteggio è **dimostrato matematicamente** sotto l'ipotesi che `u_rumore` e `u_termico` entrino in `u_c`. La rimozione della forma `S = budget + k*u_c` dal codice è metrologicamente necessaria. `B_matched` non ha un valore misurato (entrambe le campagne usano `budget_mode = "short"`, `run_gate_p44.py:768-781`), quindi il criterio A non è applicabile quantitativamente.

---

## 2. Giustificazione della quadratura (Emenda 8) e condizioni di hypot()

### 2.1 Testo originale dell'Emenda 8

Nel protocollo `experiment_results/protocollo_v4_20261024.md`, sezione "Emenda 8 (2026-10-26)":

- **Linee 3728-3749 (P2.9 / P1.7):** `budget_base_w = sqrt(half_range_pre_w^2 + half_drift_w^2)` **resta**. La quadratura è dichiarata **proxy di incertezza standard** impiegato nei pesi `w_b = 1/budget_fit_b^2` (F.9). P1.7 continua a chiamare `half_range_pre_w` e `half_drift_w` semi-range conservativi, e a `n = 3` non si stima una varianza. La quadratura **non è un limite massimo**: il rapporto con la somma aritmetica resta fra `1/sqrt(2)` e `1`. La somma aritmetica **non è adottata**. Per le soglie del gate che richiedano una garanzia più forte si applicherà un **fattore di copertura separato**, dichiarato come tale, senza toccare la formula del budget.

- **Linee 537-591 (P1.7 Incertezza di baseline):** `half_range_pre_w` e `half_drift_w` sono **semi-range conservativi**; `budget_base_w` è la loro combinazione in quadratura, un budget, non una varianza. Con n=3 non si stima una deviazione standard. La scelta fra le due forme dipende da che cosa il budget rappresenta, non da quanto è grande. La quadratura è appropriata quando i termini sono incertezze standard combinabili sotto un'ipotesi probabilistica, per esempio l'indipendenza; la somma aritmetica è appropriata quando i termini sono limiti assoluti. Nessuna delle due forme diventa corretta per il solo fatto di essere applicata a questi valori.

### 2.2 Appropriatezza della quadratura senza assumere indipendenza

La quadratura `sqrt(a^2 + b^2)` è giustificata **solo se** i due termini possono essere trattati come componenti indipendenti (o almeno non perfettamente correlati positivamente). L'Emenda 8 (linee 3735-3740) dichiara esplicitamente che:

1. La quadratura è un **proxy di incertezza standard**, non una dichiarazione che i termini siano deviazioni standard.
2. Non si assume l'indipendenza in modo implicito: il codice `gate_uncertainty.py:63` richiede che chi marca `inclusa=True` risponda dell'indipendenza, e `motivo` è il posto dove dichiararlo (`valida_componente` a linea 37-52).
3. Nella implementazione corrente (`run_gate_p44.py:969-993`), `u_rumore` e `u_termico` hanno entrambe `inclusa = False` proprio perché già dentro `budget_base_w`. Quindi **non c'è una seconda RSS** che sommi di nuovo questi termini.

Condizioni per cui `hypot()` è giustificato:

| Condizione | Stato nel codice | Evidenza |
|---|---|---|
| Termini non negativi | Soddisfatta | `half_range_pre_w >= 0`, `half_drift_w >= 0` (valori absoluti/semi-range) |
| Indipendenza (o scarsa correlazione) | Non assumuta implicitamente | `inclusa = False` per entrambe; nessun componente di `u_c` include entrambi insieme |
| `u_c` RSS solo di componenti incluse | Soddisfatta | `combina_incluse` (linea 63): RSS delle sole `inclusa=True`; `None` se nessuna |

### 2.3 Conclusione punto 2

La quadratura di `budget_base_w` è **giustificata come proxy di incertezza standard** (Emenda 8, linee 3735-3749), non come limite massimo garantito. `hypot()` è appropriato **sotto la condizione** che i due semi-range non siano perfettamente correlati positivamente; l'Emenda 8 non afferma l'indipendenza come fatto, ma la lascia come dichiarazione di chi include il componente in `u_c`. Dato che nel codice vigente entrambi i componenti sono esclusi da `u_c` (`inclusa = False`), non si produce doppio conteggio e `hypot()` non è mai applicato due volte nello stesso conto. La quadratura rimane **provvisoria** (P1.7, linea 579-581): va chiusa prima della campagna principale con un'analisi di sensibilità documentata.

---


---

## 3. Statistica di bias_w e U: ricostruzione dell'estimatore e valutazione critica

### 3.1 Estimatore di bias_w

Nel codice `cwEnergyModular/tools/run_gate_p44.py`:

- **`_verdetto_primario` (linea 1161):** `|bias_w| <= budget_base_w` a scala Tc, con `bias_w` preso da `analysis["bias_w"]`.
- **`bias_w`** (documentato nel rapporto `p44_verifica_metrologica_20261109.md:72, 91`): `somma(E_net, controlli utilizzabili) / somma(dt_W, controlli utilizzabili)` — una **media ponderata per dt_W**, non una media semplice.

Valori verificati:
- Campagna 1: `5.636999 / 11.754264 = 0.479571 W` ✓ (4 controlli utilizzabili)
- Campagna 2: `2.201627 / 17.588918 = 0.125171 W` ✓ (6 controlli utilizzabili)

### 3.2 u_A = s / sqrt(n) — valutazione critica

Nel codice `run_gate_p44.py:1088-1124` (`_incertezza_con_au_controlli`):

- `u_a = stats["se"]` = `s / sqrt(n)` con `s` = deviazione standard campionaria (ddof=1) sulle potenze nette `p_net_w = E_net / dt_W` dei controlli utilizzabili.
- `k = t(0.975, n-1)` (fattore di Student), `U = k * u_c`.
- Documentato: «L'unità statistica è il blocco di controllo, non la terna di baseline di P4.12 (dove a n = 3 il divieto di stimare una varianza resta)» (linea 1093-1095).

Valore per la campagna 2 (verificato nel rapporto `:126-136`):

| Grandezza | Valore | Fonte |
|---|---|---|
| n (controlli utilizzabili) | 6 | `analysis.json` 08-11 |
| Potenze nette W | 0.565522, 0.125233, -0.025136, -0.059996, 0.091956, 0.053487 | `grandezze_riportate.per_controllo` |
| Media | 0.125178 W | coerente con `bias_w = 0.125171` (arrotondamento) |
| sd (ddof=1) | 0.226729 W | riportata come `sd` in `analysis.json` |
| `u_A = s / sqrt(n)` | 0.092562 W | coerente con `se` riportato |
| `t(0.975, 5)` | 2.570582 | fattore di copertura per U |
| `U = t * u_A` | 0.237949 W | incertezza estesa |

Per la campagna 1 (`u_A`) non calcolabile: i `p_net_w` dei controlli usabili non sono aggregati in `analysis.json` del 07-11 (rapporto `:138`).

### 3.3 Valutazione delle assunzioni statistiche

| Assunzione | Stato | Evidenza / limite |
|---|---|---|
| Indipendenza dei controlli | **Non verificata** | Nessuna dichiarazione di indipendenza tra blocchi di controllo nel codice; i blocchi sono sequenziali nello stesso run, possibili effetti di carry-over termico |
| Omoschedasticità | **Non verificata** | `s / sqrt(n)` assume varianza comune; con n = 4-6 non è testabile |
| Distribuzione normale (per t di Student) | **Non verificabile** | n = 4 o 6, troppo pochi per un test di normalità; il t-quantile è usato come fattore di copertura convenzionale, non come test di significatività |
| Media ponderata per dt_W | **Implementata** | `bias_w = somma(E_net) / somma(dt_W)`; i controlli con dt_W maggiore pesano di più |
| Unità statistica = blocco di controllo | **Dichiarata** | `run_gate_p44.py:1093-1095` |

### 3.4 Distinzione incertezza standard / estesa / banda di guardia

| Grandezza | Formula | Valore (campagna 2) | Ruolo nel codice |
|---|---|---|---|
| `u_c` (incertezza standard combinata) | RSS delle sole incluse = `u_A` | 0.092562 W | `combina_incluse` (linea 63); `None` pre-controlli |
| `U` (incertezza estesa) | `t(0.975, n-1) * u_c` | 0.237949 W | `GRANDEZZA RIPORTATA`, non decide (`_accettazione_guardata` linea 1190-1207) |
| Banda di guardia | `|bias| + U <= budget` | 0.363120 > 0.117995 → non accettata | `reportato`, non criterio decisivo |

**Nota metrologica:** il JCGM 106:2012 è citato nel codice (`run_gate_p44.py:1190-1207`) come riferimento per la banda di guardia `|bias| + U <= budget`, ma **non prescrive** che questa debba essere il criterio decisivo. Nel codice vigente il criterio decisivo rimane B (`|bias_w| <= budget_base_w`), e C è solo grandezza riportata. Attribuire al JCGM 106 l'obbligatorietà della banda di guardia come criterio di accettazione sarebbe una prescrizione non contenuta nella citazione.

### 3.5 Conclusione punto 3

`bias_w` è una media ponderata per dt_W, ricostruibile e verificata su entrambe le campagne. `u_A = s / sqrt(n)` è computabile solo post-controlli (campagna 2: 0.092562 W; campagna 1: non aggregato). Le assunzioni di indipendenza, omoschedasticità e normalità non sono verificabili con n = 4-6 e non sono dichiarate come verificate nel codice. `U = t * u_c` e la banda di guardia `|bias| + U <= budget` sono grandezze riportate, non decisive, e la citazione del JCGM 106:2012 non impone che lo siano.

---


---

## 4. Verifica indipendente del pilota P2.9 (dt_nominal_s)

### 4.1 Artefatti di fonte

| Artefatto | Percorso | Contenuto dichiarato |
|---|---|---|
| Frozen JSON | `experiment_results/p29_pilot_20261107/dt_nominal_frozen.json` | `dt_nominal_s = 2.930748`, `median_duration_s = 0.976916`, 10 durate, SHA-256 `e8fbfabe...` |
| CSV pilota | `experiment_results/p29_pilot_20261107/casualwatt_v4_results_p29.csv` | 10 righe, `test_source = pilot_p29`, colonne `duration_s` |

### 4.2 Verifica eseguita (Python, indipendente dal JSON congelato)

Calcolo diretto sul CSV:

1. **SHA-256:** `e8fbfabed8a5a2289481a950b7bc88b636738574cb34aca4a59076cb9013204e` — **match** con `dt_nominal_frozen.json` (`source.results_csv_sha256`).
2. **Conteggio righe:** 10 righe totali, tutte con `test_source = pilot_p29`, nessuna durata non parseabile.
3. **Durata ordinate:** `[0.043409, 0.043732, 0.218623, 0.619917, 0.796816, 1.157016, 1.172488, 1.178841, 1.252318, 3.947675]` — identiche a `durations_s` nel JSON.
4. **Mediana (n=10 pari):** media del 5° e 6° valore ordinato = `(0.796816 + 1.157016) / 2 = 0.976916` — **match** con `median_duration_s`.
5. **dt_nominal_s:** `3 * 0.976916 = 2.930748` — **match** con `dt_nominal_s`.
6. **Run IDs:** 6 run ID dichiarati (`06813d4e...`, `e707eb89...`, `c3cd2357...`, `e32b6aef...`, `7904bd96...`, `6c86c842...`) corrispondenti alle 10 righe del CSV.
7. **Modello:** `qwen2.5:0.5b`, `num_ctx = 8192`, data pilota `20261107`, runner `benchmark_v4.run_v4_benchmark`.

### 4.3 Verifica del congelamento temporale rispetto alle campagne P4.4

- `dt_nominal_frozen.json` è datato `2026-11-07` (prima delle campagne P4.4 del 07-11 e 08-11).
- Il `git_head` dichiarato è `48820a220b707b4ad6668316c0f5d296de856c5b`, antecedente alle campagne.
- Il protocollo P4.4 requisito 5 (linee 3728-3749) richiede che `dt_nominal_s` sia fissato **prima** della campagna principale.
- Il valore congelato (2.930748 s = 3 × mediana di 10 durate pilota) è coerente con il disegno della campagna: Tc = 2.930748 s è la durata della finestra di controllo usata da entrambi i gate P4.4 eseguiti.

### 4.4 Limiti

- La verifica è **ex post** sui dati già raccolti: conferma la coerenza interna del congelamento, ma non può garantire che il valore non sia stato influenzato dalla conoscenza dei risultati delle campagne (il congelamento è dichiarato come avvenuto prima, ma l'audit non può ricostruire l'ordine temporale reale oltre agli artefatti).
- Il CSV originale è ignorato da git (`cwEnergyModular/results/*.csv` è gitignored per AGENTS.md); l'unica copia tracciata è quella in `experiment_results/`. La copia live in `cwEnergyModular/results/` ha lo stesso SHA-256 (verificato), quindi le due copie sono identiche.

### 4.5 Conclusione punto 4

`dt_nominal_s = 2.930748 s` è **verificato indipendentemente**: SHA-256 del CSV match, mediana delle 10 durate = 0.976916 s, 3 × mediana = 2.930748 s, tutto coerente con `dt_nominal_frozen.json`. Il congelamento risale al 2026-11-07, prima delle campagne P4.4, soddisfacendo il requisito 5 del protocollo. La provenienza è difendibile.

---


---

## 5. Proposte di modifiche documentali minime per la Quindicesima emenda

La Quindicesima emenda deve formalizzare, come richiesto dalla relazione `relazione_revisione_gate_p44.md:9`, almeno:

1. La nuova soglia coerente con la scala Tc (già nel codice: `CRITERIO_PRIMARIO = "bias_vs_budget_tc"`, `run_gate_p44.py:922`).
2. La regola di combinazione dell'incertezza (già nel codice: `combina_incluse`, `gate_uncertainty.py:63`; `inclusa = False` per `u_rumore`/`u_termico`, `run_gate_p44.py:969-993`).
3. Il nuovo disegno con 12 coppie e quorum `ceil(2/3 * 12) = 8` (decisione 6 della seconda campagna, `experiment_results/confronto_campagne_p44_20261108.md`).

Di seguito le **modifiche documentali minime** proposte, scritte come bozza di emenda da adottare prima della terza campagna. Nessuna modifica a codice o dati è richiesta.

### 5.1 Articolo 1 — Criterio primario e soglia a scala Tc

> Il criterio primario del gate P4.4 è `|bias_w| <= budget_base_w` a scala Tc (Tc = `dt_nominal_s` congelato dal pilota P2.9), con budget misurato PRIMA dei blocchi (pre-registrato) e filtro/quorum di F.12. Il verdetto F.12 storico (mediana dei budget per blocco da finestre da 30 s) resta calcolato e riportato accanto ma non decide.

**Ancoraggio:** `run_gate_p44.py:891-920` (commenti criterio), `:922` (`CRITERIO_PRIMARIO`), `:1161` (`_verdetto_primario`).  
**Motivo:** chiude il mismatch di scala fra budget (30 s) e controllo (2,93 s) individuato nella relazione cap.3.

### 5.2 Articolo 2 — Regola di combinazione dell'incertezza e divieto di doppio conteggio

> `u_c` è la somma in quadratura (RSS) delle sole componenti con `inclusa = True`; se nessuna è inclusa, `u_c = None` (non zero). Le componenti `u_rumore` (`half_range_pre_w`) e `u_termico` (`half_drift_w`) sono già contenute in `budget_base_w = hypot(half_range_pre_w, half_drift_w)` per costruzione; vanno dichiarate `inclusa = False` con motivo esplicito. La forma `S = budget + k * u_c` è rimossa e non può essere reintrodotta senza un'analisi di doppio conteggio documentata. `u_A = s / sqrt(n)` (tipo A, post-controlli) è l'unica componente inclusa in `u_c` dopo i controlli; `U = t(0.975, n-1) * u_c` è grandezza riportata, non criterio decisivo.

**Ancoraggio:** `gate_uncertainty.py:37` (`valida_componente`), `:63` (`combina_incluse`); `run_gate_p44.py:969-993` (`inclusa = False` con motivo), `:1088-1124` (`u_A` inclusa post-controlli), `:1190-1207` (banda di guardia riportata, non decisiva).  
**Motivo:** il doppio conteggio è dimostrato matematicamente (punto 1 di questo audit): con `u_rumore` e `u_termico` inclusi, `u_c = budget_base_w` e `S >= 2 * budget` (k >= 1) o `S >= 3 * budget` (k = 2), convertendo fail veri in pass spuri in entrambe le campagne eseguite.

### 5.3 Articolo 3 — Natura provvisoria della quadratura di budget_base_w

> `budget_base_w = sqrt(half_range_pre_w^2 + half_drift_w^2)` è un proxy di incertezza standard, non una deviazione standard né un limite massimo garantito. `half_range_pre_w` e `half_drift_w` sono semi-range conservativi; a n = 3 non si stima una varianza. La quadratura è appropriata solo sotto l'ipotesi che i due termini non siano perfettamente correlati positivamente; l'indipendenza non è assunta implicitamente e va dichiarata per ogni componente inclusa in `u_c`. Per soglie del gate che richiedano una garanzia più forte si applica un fattore di copertura separato, dichiarato come tale, senza toccare la formula del budget.

**Ancoraggio:** `protocollo_v4_20261024.md:3728-3749` (Emenda 8, P2.9/P1.7), `:537-591` (P1.7 Incertezza di baseline).  
**Motivo:** l'Emenda 8 ha lasciato la forma provvisoria in attesa dell'analisi di sensibilità (linee 579-581). L'emenda deve dichiarare che tale analisi è demandata al piano pre-registrato della terza campagna.

### 5.4 Articolo 4 — Disegno 12 coppie e quorum

> Il disegno della campagna è 12 coppie (24 blocchi: 12 load + 12 control), con quorum di F.12 pari a `ceil(2/3 * 12) = 8` controlli utilizzabili. Il piano `plan.json` deve dichiarare `budget_mode`, `budget_n_terne`, `budget_matched_target_s`, `budget_floor_finestra_s` e `criterio_primario` prima di qualsiasi misura; `_verifica_piano` rifiuta l'esecuzione se questi parametri mancano o sono discordanti.

**Ancoraggio:** `run_gate_p44.py:1210` (`_verifica_piano`), `experiment_results/p44_gate_20261109/plan.json` (piano corrente, 12 coppie, `budget_mode = short`).  
**Motivo:** decisione 6 della seconda campagna (`experiment_results/confronto_campagne_p44_20261108.md`).

### 5.5 Articolo 5 — Provenienza e congelamento di dt_nominal_s

> `dt_nominal_s` è fissato PRIMA della campagna principale come `3 * mediana(duration_s delle righe valide del pilota P2.9)`. Il valore congelato è `dt_nominal_s = 2.930748 s` (mediana 0.976916 s su 10 righe), con SHA-256 del CSV di fonte e run ID dichiarati in `dt_nominal_frozen.json`. Qualsiasi riuso del valore richiede nuova verifica indipendente del SHA-256 e della mediana contro il CSV originale.

**Ancoraggio:** `experiment_results/p29_pilot_20261107/dt_nominal_frozen.json`, `casualwatt_v4_results_p29.csv` (SHA-256 `e8fbfabe...`, verifica indipendente eseguita in questo audit).  
**Motivo:** requisito 5 del protocollo P4.4; il valore è stato verificato indipendentemente in questo audit (punto 4).

### 5.6 Sintesi delle modifiche documentali

| Articolo | Oggetto | Stato nel codice | Azione documentale |
|---|---|---|---|
| 1 | Criterio primario a scala Tc | Implementato (`:922`, `:1161`) | Congelare in emenda |
| 2 | Regola combinazione incertezza, no doppio conteggio | Implementato (`gate_uncertainty.py:63`, `run_gate_p44.py:969-993`) | Congelare in emenda |
| 3 | Quadratura provvisoria, non limite garantito | Implementato (`protocollo_v4_20261024.md:3735-3749`) | Dichiarare provvisoria, demandare analisi di sensibilità al piano |
| 4 | 12 coppie, quorum 8 | Piano esistente (`plan.json`) | Congelare in emenda |
| 5 | Provenienza dt_nominal_s | Verificato indipendentemente | Congelare SHA-256 e mediana in emenda |

---

## 6. Riepilogo delle conclusioni dell'audit integrativo

| Punto | Questione | Risultato | Conclusione |
|---|---|---|---|
| 1 | Definizioni B_matched/u_c/u_rumore/u_termico/k/S e doppio conteggio | Doppio conteggio dimostrato matematicamente; B_matched non misurato | **Dimostrato** (condizionato all'inclusione di u_rumore/u_termico in u_c) |
| 2 | Giustificazione quadratura (Emenda 8) | Proxy di incertezza standard, non limite garantito; hypot() giustificato solo senza correlazione positiva perfetta | **Condizionato** (indipendenza non assumeta, dichiarata per componente inclusa) |
| 3 | Statistica bias_w e U | bias_w ricostruito e verificato (media ponderata per dt_W); u_A computabile solo post-controlli; U e banda di guardia riportate, non decisive; assunzioni non verificabili con n=4-6 | **Parzialmente verificato** (estimatore corretto, assunzioni non dimostrate) |
| 4 | Verifica indipendente P2.9 dt_nominal_s | SHA-256 match, mediana match, dt_nominal match; congelato prima delle campagne | **Dimostrato** (provenienza difendibile) |
| 5 | Proposte emenda | 5 articoli documentali minimi, nessuna modifica a codice/dati | **Pronte per adozione** |

**Nessuna modifica a codice di produzione, nessun dato alterato, nessun commit, nessuna terza campagna avviata.**

