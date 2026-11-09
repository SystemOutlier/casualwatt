# Change report — consolidamento metrologico P4.4 (2026-11-09)

**Data:** 2026-11-09  
**Oggetto:** modifiche apportate al gate P4.4 (load-versus-control) per renderlo metrologicamente coerente, statisticamente trasparente e riproducibile.  
**Stato:** report delle modifiche effettuate, non documento di emenda. La bozza di emenda è in `experiment_results/quindicesima_emenda_20261109.md`.  
**Vincoli osservati:** nessuna modifica a dati di campagna, nessuna terza campagna avviata, nessun `git push`, nessun touch di `.casualwatt_keys.json`, un commit per punto concettuale (vedi Task #32), nessun `pytest` nudo dalla radice.

---

## 1. Sintesi

Due modifiche puntuali:

1. **Produzione** (`cwEnergyModular/tools/run_gate_p44.py`): `_verdetto_primario` tratta ora i valori di `bias_w` non finiti (NaN, +inf, -inf) come not-executable, coerentemente con il trattamento già previsto per `bias is None`. Prima, un bias non finito arrivava al `float(bias)` di riga 1182 e generava un confronto spuro o un'eccezione non dichiarata.
2. **Test** (`cwEnergyModular/tests/test_run_gate_p44_metrologico.py`): nuovo file con 12 test coprendo integrità di `dt_nominal_frozen.json` (SHA-256 + mediana), gestione di bias_w e u_A non finiti/missing, riproducibilità del seme e verifica che un ordine_seed diverso faccia rifiutare il piano.

Nessuna modifica a `gate_uncertainty.py`, `test_budget_p44_preesecuzione.py`, `test_gate_uncertainty_p44.py` o agli artefatti di campagna.

---

## 2. Modifica di produzione

### File: `cwEnergyModular/tools/run_gate_p44.py`

**Funzione interessata:** `_verdetto_primario` (linea 1161).

**Prima (righe 1178-1181):**
```python
    if status_f12 == "not-executable" or bias is None:
        return {**base, "status": "not-executable", "margine_w": None,
                "motivo": "gate non eseguibile (filtro/quorum di F.12): nessun "
                          "bias da confrontare con il budget"}
```

**Dopo:**
```python
    bias_finito = (bias is not None and math.isfinite(float(bias)))
    if status_f12 == "not-executable" or not bias_finito:
        return {**base, "status": "not-executable", "margine_w": None,
                "motivo": "gate non eseguibile (filtro/quorum di F.12): nessun "
                          "bias da confrontare con il budget"}
```

**Perché:** un bias NaN o inf non è un numero misurato: il verdetto non può confrontarlo col budget e non deve produrre un pass/fail silenzioso su un numero inesistente. La guardia `math.isfinite` è applicata prima di `float(bias)` (riga 1182), quindi il verdetto si ferma con `not-executable` e `margine_w = None`.

**Impatto sul comportamento esistente:** nullo per tutti i casi in cui `bias_w` è già finito (le due campagne eseguite hanno bias finito: 0,479571 W e 0,125171 W). Cambia solo il trattamento di valori inesistenti/non finiti, da errore implicito a not-executable dichiarato.

---

## 3. Nuovo file di test

### File: `cwEnergyModular/tests/test_run_gate_p44_metrologico.py` (12 test, tutti verdi)

| Test | Cosa verifica |
|---|---|
| `test_dt_nominal_frozen_coerente_con_csv_pilota` | Il `dt_nominal_s` congelato (2,930748 s) è `3 x mediana` delle durate del CSV pilota e lo SHA-256 del CSV registrato nel JSON matcha il file su disco |
| `test_dt_nominal_frozen_valore_non_inventato` | `rg.DT_NOM_FROZEN` è lo stesso valore del JSON, letto dal pilota P2.9 prima della campagna |
| `test_verdetto_primario_bias_none_e_not_executable` | `bias_w = None` → `not-executable`, margine `None` |
| `test_verdetto_primario_bias_non_finito_not_executable[nan|inf|-inf]` | bias non finito → `not-executable`, mai pass/fail su NaN o inf |
| `test_verdetto_primario_bias_finito_normale` | bias finito si confronta col budget: `|bias| <= budget` → pass |
| `test_u_a_con_potenza_netta_none_resta_none_non_zero` | `e_net_j = None` → `u_A = None`, `u_c = None`, mai zero |
| `test_u_a_con_dt_w_s_inf_resta_none` | `dt_w_s = +inf` → controllo escluso, `u_A = None` |
| `test_u_a_con_e_net_j_non_finito_escluso` | `e_net_j = NaN` escluso dalla dispersione; un solo valore valido → `u_A = None` |
| `test_stesso_seed_stesso_ordine_blocchi` | stesso `order_seed` → stesso ordine di blocchi/bracci/pair_id |
| `test_seed_diverso_cambia_il_piano_dichiarato` | ordine_seed manomesso → `_verifica_piano` rifiuta con `SystemExit` |

### Cosa NON verifica (già coperto altrove)

- Criterio F.12 → `tests/test_control_gate_p45.py`
- Orchestrazione end-to-end → `tests/test_gate_p44_end_to_end.py`
- Combinazione dell'incertezza → `tests/test_gate_uncertainty_p44.py`
- Budget pre-esecuzione → `tests/test_budget_p44_preesecuzione.py`

---

## 4. Verifica eseguita

Tutti i 12 test del nuovo file passano:

```
12 passed in 1.57s
```

La suite precedente sui moduli già esistenti (`test_budget_p44_preesecuzione.py`, `test_gate_uncertainty_p44.py`, `test_control_gate_p45.py`) non è stata modificata e non richiede riesecuzione per queste modifiche puntuali.

---

## 5. Grandezze non modificate (conferma)

| Grandezza | Stato | Ancoraggio |
|---|---|---|
| `budget_base_w = hypot(half_range_pre_w, half_drift_w)` | invariato | `run_gate_p44.py:761-877` |
| `u_c = RSS solo incluse, None se nessuna` | invariato | `gate_uncertainty.py:63` |
| `u_A = s / sqrt(n)` post-controlli | invariato | `run_gate_p44.py:1088-1124` |
| `S = budget + k * u_c` rimossa | invariato (già rimossa) | `run_gate_p44.py:901-908` |
| Quorum `ceil(2/3 * n_coppie)` | invariato | `test_control_gate_p45.py` / `control_gate.quorum_for` |
| `dt_nominal_s = 2,930748 s` | invariato, congelato | `run_gate_p44.py:200` / `dt_nominal_frozen.json` |

---

## 6. Prossimi passi (Task #31 e #32)

1. Eseguire `pytest cwEnergyModular` (non dalla radice) e incollare l'output completo per regressione.
2. Commitare i due file modificati/aggiunti come punti concettuali separati su `fix/p44-metrologico-20261109`, senza push.
