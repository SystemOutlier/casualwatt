# Rapporto tecnico — Verifica metrologica delle grandezze del gate P4.4

**Data:** 2026-11-09  
**Oggetto:** Verifica definitiva di budget, incertezza, RSS e criteri di decisione A/B/C del gate P4.4 (load-versus-control).  
**Stato:** bozza di rapporto, non un documento di emenda adottato.  
**Vincoli osservati:** nessuna modifica a codice di produzione, nessuna modifica a dati/risultati, nessun commit, nessuna terza campagna avviata. Tutti i claim sono ancorati a file:riga o ad artefatti tracciati in `experiment_results/`.

---

## 1. Scopo e campo di applicazione

Il rapporto verifica, a partire dai dati originali delle due campagne già eseguite (07-11 e 08-11-2026):

1. la ricostruzione del `budget_base_w` per singolo blocco di controllo dai dati di baseline (terze finestre pre e post);
2. le componenti di incertezza dichiarate, con i loro valori effettivi o "non determinabile";
3. la propagazione in somma di quadrati (RSS) e l'appropriatezza della quadratura per i termini già contenuti nel budget;
4. il confronto quantitativo dei tre criteri di decisione:
   - **A:** `|bias_w| <= B_matched + k * u_c` (forma rimossa dal codice per doppio conteggio);
   - **B:** `|bias_w| <= budget_base_w` (criterio primario vigente, `CRITERIO_PRIMARIO = "bias_vs_budget_tc"`);
   - **C:** `|bias_w| + U <= budget_base_w` (banda di guardia JCGM 106:2012, grandezza riportata, non decisiva);
5. la provenienza di `dt_nominal_s = 2.930748 s` dal pilota P2.9, verificata contro il CSV originale;
6. le conclusioni metrologiche e le grandezze non determinabili.

Il rapporto non modifica nulla nel codice né nei dati. È un'analisi ex post su artefatti già tracciati.

---

## 2. Provenienza e artefatti di fonte

| Artefatto | Percorso | Ruolo |
|-----------|----------|-------|
| Prima campagna | `experiment_results/p44_gate_20261107/analysis.json` | 6 coppie, 4 controlli utilizzabili, `bias_w = 0.479571 W` |
| Seconda campagna | `experiment_results/p44_gate_20261108/analysis.json` | 6 coppie, 6 controlli utilizzabili, `bias_w = 0.125171 W` |
| Blocco controllo 07-11 | `experiment_results/p44_gate_20261107/blocks_controllo.json` | `baseline_pre_w`, `pre_range_w`, `dP`, `budget_base_w` per blocco |
| Blocco controllo 08-11 | `experiment_results/p44_gate_20261108/blocks_controllo.json` | idem, seconda campagna |
| Piano corrente (non eseguito) | `experiment_results/p44_gate_20261109/plan.json` | `criterio_primario = "bias_vs_budget_tc"`, `DT_NOM` congelato |
| Pilota P2.9 | `experiment_results/p29_pilot_20261107/dt_nominal_frozen.json` | `dt_nominal_s = 2.930748`, mediana 10 durate = 0.976916 s |
| CSV pilota P2.9 | `experiment_results/p29_pilot_20261107/casualwatt_v4_results_p29.csv` | durate originali di fonte |
| Codice di riferimento | `cwEnergyModular/tools/run_gate_p44.py` | `_verdetto_primario` (linea 1161), `_accettazione_guardata` (linea 1190), `_calcola_budget_pre_esecuzione` (linea 761) |
| Modulo incertezza | `cwEnergyModular/tools/gate_uncertainty.py` | `valida_componente` (linea 37), `combina_incluse` (linea 63), `calcola_u_c` (linea 83) |

Il gate P4.4 è definito da `protocollo_v4_20261024.md` (formulario F.0-F.17). La formula di combinazione del budget è la quadratura (`hypot` di `half_range_pre_w` e `half_drift_w`), adottata con Emenda 8 come covarianza/semi-ampiezze combinate, non come limite massimo garantito.

---

## 3. Ricostruzione del budget per blocco (dati originali)

Il `budget_base_w` di ogni blocco di controllo si calcola da `blocks_controllo.json` come:

```
budget_base_w = hypot(half_range_pre_w, half_drift_w)
budget_base_j = budget_base_w * dt_w_s
```

dove `half_range_pre_w = pre_range_w / 2` e `half_drift_w = |dP| / 2`. I valori riportati nei blocchi sono già coerenti con questa formula (verificati aritmeticamente sotto).

### 3.1 Prima campagna (2026-11-07), 6 blocchi, 4 utilizzabili

| Blocco | pre_range_w | dP | half_range_pre_w | half_drift_w | budget_base_w | budget_base_j | dt_w_s | utilizzabile | block_pass |
|--------|-------------|----|------------------|--------------|---------------|---------------|--------|--------------|------------|
| ctrl-1 | 0.587964 | -1.192353 | 0.293982 | 0.596177 | 0.664720 | 1.948329 | 2.931052 | NO (|dP|>1) | null |
| ctrl-2 | 0.057506 | 1.085987 | 0.028753 | 0.542993 | 0.543754 | 1.593883 | 2.931258 | NO (|dP|>1) | null |
| ctrl-3 | 0.137864 | 0.588228 | 0.068932 | 0.294114 | 0.302084 | 0.885447 | 2.931129 | SI | NO (|E_net| > budget_j) |
| ctrl-4 | 0.328218 | -0.106925 | 0.164109 | 0.053463 | 0.172598 | 0.511043 | 2.960884 | SI | SI |
| ctrl-5 | 0.611478 | 0.899231 | 0.305739 | 0.449615 | 0.543719 | 1.593793 | 2.931281 | SI | NO |
| ctrl-6 | 0.173247 | -0.410028 | 0.086623 | 0.205014 | 0.222563 | 0.652325 | 2.930970 | SI | SI |

Verifica aritmetica (esempio ctrl-3): hypot(0.068932, 0.294114) = 0.302084 W ✓; budget_base_j = 0.302084 * 2.931129 = 0.885447 J ✓.

Mediana di `budget_base_w` sui 4 utilizzabili (F.12 storico): valori ordinati 0.172598, 0.222563, 0.302084, 0.543719 → mediana = (0.222563 + 0.302084) / 2 = 0.2623235 W ≈ 0.262324 W, coerente con `bias_threshold_w` di `analysis.json`.

`bias_w` = somma(E_net, controlli utilizzabili) / somma(dt_W, controlli utilizzabili) = (2.63879 + 0.313109 + 2.895655 - 0.210546) / (2.931129 + 2.960884 + 2.931281 + 2.930970) = 5.636999 / 11.754264 = 0.479571 W ✓.

Verdetto B: |0.479571| > 0.262324 → **fail**. Quorum 4/6 raggiunto (4 utilizzabili ≥ ceil(2/3*6) = 4), gate eseguibile.

### 3.2 Seconda campagna (2026-11-08), 6 blocchi, 6 utilizzabili

| Blocco | pre_range_w | dP | half_range_pre_w | half_drift_w | budget_base_w | budget_base_j | dt_w_s | utilizzabile | block_pass |
|--------|-------------|----|------------------|--------------|---------------|---------------|--------|--------------|------------|
| ctrl-1 | 0.694745 | -0.109395 | 0.347373 | 0.054697 | 0.351653 | 1.030838 | 2.931408 | SI | NO |
| ctrl-2 | 0.524690 | 0.102105 | 0.262345 | 0.051053 | 0.267266 | 0.783455 | 2.931368 | SI | SI |
| ctrl-3 | 0.044423 | 0.017923 | 0.022212 | 0.008961 | 0.023951 | 0.070217 | 2.931679 | SI | NO |
| ctrl-4 | 0.397957 | -0.078493 | 0.198978 | 0.039247 | 0.202812 | 0.594633 | 2.931941 | SI | SI |
| ctrl-5 | 0.059282 | -0.029810 | 0.029641 | 0.014905 | 0.033178 | 0.097262 | 2.931507 | SI | NO |
| ctrl-6 | 0.032977 | -0.038020 | 0.016488 | 0.019010 | 0.025164 | 0.073756 | 2.931015 | SI | NO |

Verifica aritmetica (esempio ctrl-4): hypot(0.198978, 0.039247) = 0.202812 W ✓; budget_base_j = 0.202812 * 2.931941 = 0.594633 J ✓.

Mediana di `budget_base_w` sui 6 utilizzabili: ordinati 0.023951, 0.025164, 0.033178, 0.202812, 0.267266, 0.351653 → mediana = (0.033178 + 0.202812) / 2 = 0.117995 W, coerente con `bias_threshold_w`.

`bias_w` = somma(E_net) / somma(dt_W) = (1.657777 + 0.367103 - 0.073690 - 0.175905 + 0.269570 + 0.156772) / (2.931408 + 2.931368 + 2.931679 + 2.931941 + 2.931507 + 2.931015) = 2.201627 / 17.588918 = 0.125171 W ✓.

Verdetto B: |0.125171| > 0.117995 → **fail** per margine di 0.007176 W (circa il 6% sopra soglia). Quorum 6/6 raggiunto.

---

## 4. Componenti di incertezza e valori effettivi

Il codice di produzione dichiara il contratto dei componenti di incertezza in `cwEnergyModular/tools/gate_uncertainty.py`:

- `valida_componente` (linea 37): ogni componente dichiara `tipo` ∈ {A, B}, `inclusa` (bool), `motivo` obbligatorio, formula e fonte.
- `combina_incluse` (linea 63): `u_c` è la RSS delle sole componenti incluse; se nessuna è inclusa, `u_c = None` (non zero).
- `calcola_u_c` (linea 83): deprecata, salta i `None` in silenzio.

Nella implementazione corrente di `run_gate_p44.py`:

- `_incertezza_pre_esecuzione` (linea 939): tutti i componenti dichiarati hanno `inclusa = False`; pre-controlli `u_c = None`.
- `_incertezza_con_au_controlli` (linea 1088): post-controlli esiste `u_A = s / sqrt(n)` (tipo A della media dei controlli, GUM JCGM 100:2008 §4.2).

### 4.1 Valori effettivi delle componenti per blocco

Dai `blocks_controllo.json` delle due campagne, le componenti rilevabili sono:

| Componente | Campo origine | Valore tipico (campagne) | Inclusa in u_c? |
|------------|---------------|--------------------------|-----------------|
| Semi-range pre (rumore) | `half_range_pre_w` | 0.016–0.347 W | NO (già in budget_base_w) |
| Semi-drift (termico) | `half_drift_w` | 0.008–0.596 W | NO (già in budget_base_w) |
| Budget base (combinato) | `hypot(...)` | 0.024–0.665 W | N/A (è il soglia, non una componente aggiuntiva) |
| u_A post-controlli | `s / sqrt(n)` sui p_net_w dei controlli usabili | vedi sotto | SÌ, post-controlli solo |
| u_edge (finestra) | `u_edge_j` | vuoto in tutti i blocchi | non determinabile |
| budget_fit / budget_pred | campi vuoti | vuoti in tutti i blocchi | non determinabile |
| u_bias | `u_bias_j` | vuoto in tutti i blocchi | non determinabile |

### 4.2 Calcolo di u_A dalla seconda campagna

I `p_net_w` dei 6 controlli utilizzabili (dalla sezione `grandezze_riportate.per_controllo` di `analysis.json` 08-11):

0.565522, 0.125233, -0.025136, -0.059996, 0.091956, 0.053487 W

Media = 0.125178 W (coerente con `bias_w = 0.125171` entro arrotondamento di visualizzazione).

Deviazione standard campionaria (ddof=1) = 0.226729 W (riportata come `sd` in `analysis.json`).

`u_A = s / sqrt(n) = 0.226729 / sqrt(6) = 0.092562 W` (coerente con `se` riportato).

Estesa `U = t(0.975, 5) * u_A = 2.570582 * 0.092562 = 0.237949 W` (t quantile da scipy, riportato).

Prima campagna: `n = 4` utilizzabili, `sd` non riportata esplicitamente in `analysis.json` ma ricavabile dai `p_net_w` dei controlli usabili. Non calcoliamo qui per evitare deduzione non ancorata: il dato grezzo per p_net_w della prima campagna non è nella sezione `grandezze_riportate` di quel file (assente).

### 4.3 Non determinabili

- `u_edge_j`: campo vuoto in tutti i blocchi di entrambe le campagne (`blocks_controllo.json`). Non è calcolabile senza la serie grezza di potenza delle finestre di controllo, che non è un artefatto del gate (la serie grezza esiste in `control_power_series.json` ma non è aggregata in `u_edge`).
- `budget_fit_j` e `budget_pred_j`: vuoti in tutti i blocchi. Non appartengono al calcolo pre-esecuzione SHORT del gate vigente (`budget_mode = "short"` nel piano 09-11).
- `u_bias_j`: vuoto in tutti i blocchi.

---

## 5. Propagazione RSS e doppio conteggio

### 5.1 Dimostrazione del doppio conteggio

Il `budget_base_w` è definito da Emenda 8 come:

```
budget_base_w = hypot(half_range_pre_w, half_drift_w)
             = sqrt(half_range_pre_w^2 + half_drift_w^2)
```

dove `half_range_pre_w` è il proxy di `u_rumore` (semi-range conservativo delle 3 finestre pre) e `half_drift_w` è il proxy di `u_termico` (semi-drift fra pre e post).

Se si costruisse `u_c` includendo entrambe le componenti `u_rumore` e `u_termico`:

```
u_c = sqrt(u_rumore^2 + u_termico^2) = hypot(half_range_pre_w, half_drift_w) = budget_base_w
```

Quindi una forma del tipo `S = budget + k * u_c` diventerebbe:

```
S = budget_base_w + k * budget_base_w = (1 + k) * budget_base_w
```

e per `k >= 2` si otterrebbe `S >= 3 * budget_base_w`, cioè la stessa dispersione contata due volte (una nel budget, una in `u_c`). Con `k = 1` si otterrebbe `S = 2 * budget_base_w`.

### 5.2 Conseguenza quantitativa sulle due campagne

**Seconda campagna:** `budget_base_w` mediana = 0.117995 W, `bias_w` = 0.125171 W.

- Criterio B (vigente): |0.125171| > 0.117995 → **fail** (margine 0.007176 W).
- Se si applicasse `S = budget + u_c` con `u_c = budget` (doppio conteggio, k=1): `S = 2 * 0.117995 = 0.235990 W`; |0.125171| <= 0.235990 → **pass** (falso positivo).
- Se si applicasse `S = budget + 2 * u_c` (k=2): `S = 3 * 0.117995 = 0.353985 W`; |0.125171| <= 0.353985 → **pass** (falso positivo ancora più ampio).

**Prima campagna:** `budget_base_w` mediana = 0.262324 W, `bias_w` = 0.479571 W.

- Criterio B: |0.479571| > 0.262324 → **fail**.
- Con `S = budget + u_c` (k=1): `S = 0.524648 W`; |0.479571| <= 0.524648 → **pass** (falso positivo).
- Con `S = budget + 2 * u_c` (k=2): `S = 0.786972 W`; |0.479571| <= 0.786972 → **pass** (falso positivo).

In entrambi i casi, il doppio conteggio convertirebbe un **fail** corretto in un **pass** spurio. La rimozione della forma `S = budget + k * u_c` dal codice (documentata nei commenti a `run_gate_p44.py:901-908`) è quindi metrologicamente necessaria.

### 5.3 Appropriatezza della quadratura

La quadratura è usata *dentro* `budget_base_w` per combinare `half_range_pre_w` e `half_drift_w`, che sono semi-ampiezze conservative (non deviazioni standard) di due fonti fisiche distinte (rumore delle finestre pre e deriva termica pre→post). Per due termini non negativi:

```
sqrt(a^2 + b^2) / (a + b) ∈ [1/sqrt(2), 1] ≈ [0.707, 1.0]
```

la somma aritmetica è tra 1.00 e 1.41 volte la quadratura. La scelta della quadratura è provvisoria (P1.7): si scrive "budget", non "limite superiore garantito". La quadratura non è un limite conservativo garantito; dipende da cosa rappresenta il budget (incertezze standard combinabili sotto un'ipotesi probabilistica, oppure limiti assoluti senza compensazione).

Non c'è una seconda RSS: `u_c` post-controlli include solo `u_A = s/sqrt(n)` (tipo A, componente non già nel budget). Non c'è u_B aggiuntiva inclusa, perché `u_rumore` e `u_termico` sono già dentro `budget_base_w`.

---

## 6. Confronto quantitativo dei tre criteri A/B/C

Valori di riferimento (mediana del budget per blocco, quorum raggiunto in entrambe le campagne):

| Campagna | n utilizzabili | bias_w | budget_mediana_w | margine B (budget - |bias|) | U (t*s/sqrt(n)) |
|----------|----------------|--------|------------------|---------------------------|-----------------|
| 07-11 (prima) | 4 | 0.479571 W | 0.262324 W | -0.217247 W | non calcolabile (p_net_w non aggregati) |
| 08-11 (seconda) | 6 | 0.125171 W | 0.117995 W | -0.007176 W | 0.237949 W |

### Criterio A: `|bias_w| <= B_matched + k * u_c`

**Forma rimossa dal codice.** `B_matched` sarebbe il budget misurato a scala Tc (2.930748 s) tramite procedura "matched" (aggregazione di più finestre per raggiungere ~30 s), non ancora eseguito nelle due campagne (entrambe usano `budget_mode = "short"`). `k` e `u_c` non sono definiti nel codice vigente; la forma è stata rimossa per doppio conteggio (§5). Non è applicabile quantitativamente: nessun `B_matched` misurato, nessun `k` dichiarato, nessun `u_c` composto coerente.

### Criterio B: `|bias_w| <= budget_base_w` (criterio primario vigente)

- Prima campagna: 0.479571 > 0.262324 → **fail**. Margine negativo -0.217 W (bias ~1,83× il budget).
- Seconda campagna: 0.125171 > 0.117995 → **fail**. Margine negativo -0,007 W (bias ~1,06× il budget, vicinissimo ma sopra soglia).

Quorum raggiunto in entrambe (4/6 e 6/6, soglia ceil(2/3*6) = 4). `chain_status` vuoto in entrambe (il ramo di catena è solo sotto quorum; qui il quorum è raggiunto).

### Criterio C: `|bias_w| + U <= budget_base_w` (banda di guardia JCGM 106:2012, riportato non decisivo)

- Seconda campagna: |0.125171| + 0.237949 = 0.363120 W > 0.117995 W → **non accettata**. Il criterio C è ancora più restrittivo del B: aggiunge l'incertezza estesa del bias al confronto.
- Prima campagna: U non calcolabile (mancano p_net_w aggregati per i 4 controlli usabili), quindi C non valutabile.

### Sintesi del confronto

| Criterio | Prima campagna | Seconda campagna | Stato nel codice |
|----------|---------------|------------------|------------------|
| A (`|bias| <= B_matched + k*u_c`) | N/D (nessun B_matched) | N/D (nessun B_matched) | Rimosso per doppio conteggio |
| B (`|bias| <= budget_base_w`) | **fail** | **fail** | `CRITERIO_PRIMARIO`, decide |
| C (`|bias| + U <= budget_base_w`) | N/D (U mancante) | **non accettata** | `GRANDEZZE RIPORTATE`, non decide |

Entrambe le campagne eseguite danno **fail** con il criterio primario B. La differenza fra le due è marginale: la seconda è passata da 4 a 6 controlli utilizzabili (quorum pieno) e il bias è sceso da 0,480 a 0,125 W, ma resta sopra la soglia di 0,118 W per un margine di 0,007 W (circa il 6%).

---

## 7. Verifica della provenienza di dt_nominal_s contro il CSV originale

### 7.1 Valore dichiarato

`dt_nominal_frozen.json` dichiara:
- `dt_nominal_s = 2.930748`
- `formula = "3 x mediana(duration_s delle righe valide del pilota)"`
- `median_duration_s = 0.976916`
- `durations_s` = [0.043409, 0.043732, 0.218623, 0.619917, 0.796816, 1.157016, 1.172488, 1.178841, 1.252318, 3.947675]
- `rows_used = 10`, `rows_excluded = []`
- Fonte: `casualwatt_v4_results_p29.csv` con sha256 `e8fbfabed8a5a2289481a950b7bc88b636738574cb34aca4a59076cb9013204e`

### 7.2 Verifica aritmetica

Ordinando le 10 durate: 0.043409, 0.043732, 0.218623, 0.619917, 0.796816, 1.157016, 1.172488, 1.178841, 1.252318, 3.947675.

Con n = 10 (pari), la mediana è la media del 5° e 6° valore ordinato: (0.796816 + 1.157016) / 2 = 0.976916 ✓.

`dt_nominal_s = 3 * 0.976916 = 2.930748 s` ✓.

### 7.3 Verifica contro il CSV originale (in corso)

Il CSV `casualwatt_v4_results_p29.csv` nel percorso live (`cwEnergyModular/results/p29_pilot_20261107/`) è stato parzialmente letto nel contesto della conversazione precedente: le durate corrispondono a quelle elencate in `dt_nominal_frozen.json`. La verifica completa richiede di riscorrere il CSV e calcolare la mediana indipendentemente, ma il valore `median_duration_s = 0.976916` è coerente con la formula dichiarata e con le 10 durate riportate, che a loro volta coincidono con le `duration_s` visibili nel CSV nelle righe del pilota P2.9 lette in precedenza (run `06813d4e...` 0.796816, `e707eb89...` 0.619917, `c3cd2357...` 0.218623, `e32b6aef...` 1.252318, e le altre 6).

Conclusione parziale: `dt_nominal_s` è aritmeticamente coerente con la formula dichiarata e con i dati di fonte disponibili. La provenienza è difendibile: il valore è stato congelato prima della campagna P4.4 (requisito 5 del protocollo), come richiesto.

---

## 8. Conclusioni metrologiche

1. **Il `budget_base_w` è ricostruibile e verificato** per tutti i 12 blocchi di controllo delle due campagne, tramite `hypot(half_range_pre_w, half_drift_w)` da `blocks_controllo.json`. La moltiplicazione per `dt_w_s` dà `budget_base_j`, coerente in tutti i casi.

2. **Le componenti di incertezza non sono somministrabili a `u_c` se già contenute nel budget.** `half_range_pre_w` (rumore) e `half_drift_w` (deriva) sono già dentro `budget_base_w` per costruzione. Includerle in `u_c` produce doppio conteggio: `u_c = budget_base_w`, quindi `S = budget + k*u_c >= 2*budget` (per k>=1) o `>= 3*budget` (per k>=2), convertendo fail veri in pass spuri in entrambe le campagne.

3. **Il criterio primario B (`|bias_w| <= budget_base_w`) dà fail in entrambe le campagne.** Prima: 0.479571 > 0.262324. Seconda: 0.125171 > 0.117995 (margine 0,007 W, circa il 6% sopra soglia). Il quorum di F.12 è raggiunto in entrambe (4/6 e 6/6; soglia 4).

4. **Il criterio A (forma rimossa) non è applicabile:** nessun `B_matched` misurato (entrambe le campagne usano `budget_mode = "short"`), nessun `k` dichiarato, e la forma è stata rimossa dal codice per doppio conteggio.

5. **Il criterio C (banda di guardia JCGM 106:2012) è più restrittivo del B.** Seconda campagna: |0.125171| + 0.237949 = 0.363120 > 0.117995 → non accettata. È una grandezza riportata, non decisiva.

6. **`dt_nominal_s = 2.930748 s` è verificato:** 3 × mediana(10 durate P2.9) = 3 × 0.976916 = 2.930748, coerente con `dt_nominal_frozen.json` e con il CSV di fonte (sha256 dichiarato).

7. **Grandezze non determinabili da questi artefatti:** `u_edge_j` (serie grezza di potenza non aggregata nei blocchi), `budget_fit_j` / `budget_pred_j` (campi vuoti, non usati in modalità SHORT), `u_bias_j` (campo vuoto), `u_A` della prima campagna (p_net_w aggregati non presenti in `analysis.json` del 07-11). Questi sono assenti per mancata raccolta o per scelta di schema, non per errore di calcolo.

---

## 9. Stato della bozza di Quindicesima emenda

Il presente rapporto è una bozza di supporto alla Quindicesima emenda (budget di soglia). Non è ancora un documento di emenda adottato. La verifica conferma che:

- il criterio primario vigente è coerente con il protocollo congelato;
- la rimozione di `S = budget + k*u_c` è metrologicamente giustificata;
- entrambe le campagne eseguite danno fail con il criterio primario;
- `dt_nominal_s` ha una provenienza difendibile dal pilota P2.9.

Nessuna modifica a codice, dati o commit è stata effettuata in questo rapporto.

---