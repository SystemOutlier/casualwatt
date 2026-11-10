# Design — Reporter carbonio di sola analisi (`carbon_report`)

Data: 2026-11-10
Ramo: `feat/carbon-report-analysis-20261110`
Worktree: `C:/Users/Massimo/Documents/CasualWatt/carbon-report-analysis` (da HEAD pulito `6a17ca78e`)
Stato: design approvato dall'utente; spec in review.

## 1. Contesto e problema

Una sessione parallela ha aggiunto al working tree principale otto moduli
«avanzati» ispirati a MELODI, PyJoules, ML CO2 Impact Calculator, CPU Energy
Meter, GREEN-CODE e CodeCarbon. L'esame empirico (non solo lettura) ha mostrato
che:

- la suite sul working tree sporco è a **139 falliti**;
- `multi_level_evaluation.py` solleva `TypeError` (factory con kwarg
  `judge_model` inesistente), `AttributeError` (membri enum
  `MATH_PROBLEM_SOLVING`/`CODE_GENERATION` inesistenti) e `KeyError`
  (`generate_analysis_report` legge chiavi diverse da quelle prodotte);
- `carbon_emissions.py` ha un errore di unità da **1000×**: 1 h @ 100 W =
  0,1 kWh produce 60,0 kg invece di 0,06 kg, perché moltiplica i Wh come se
  fossero kWh (la variabile `energy_kwh` corretta è calcolata ma mai usata);
- `validation.py` «valida» contro numeri `np.random` etichettati come strumenti
  esterni (CPU Energy Meter, GREEN-CODE): è una validazione fabbricata;
- lo schema CSV P5 è spostato da 174 a 180 colonne e la soglia del test
  `test_evaluation_runner.py` è spostata a 180 per farlo tornare;
- `local_energy.py` nasconde un import circolare con `try/except ImportError →
  SESSION=None` (fallback silenzioso);
- `benchmark_v4.py` importa in testa moduli non tracciati (checkout pulito
  rotto) e ha un `except` duplicato irraggiungibile.

Molte di queste idee **esistono già** nel progetto in forma rigorosa: il
confronto CodeCarbon (`docs/CONFRONTO_CODECARBON.md`, `tools/codecarbon_probe.py`,
`tools/compare_codecarbon_gate.py`), la valutazione
(`evaluator.py`, `robust_evaluator.py`, McNemar, Wilson, bootstrap), il monitor
GPU (`_GPUMonitor` in `energy_session.py`, 73 test verdi). CPU Energy Meter e
PyJoules sono Linux-only (già valutati, commit `4ed7fe6`); questa macchina non
ha GPU.

## 2. Obiettivo

Arricchire la tesi con un **layer di sola analisi** che produca un report
carbonio/emissioni **sopra la nostra energia misurata**, con formula corretta,
fattori dichiarati con fonte, e output pronto per la tesi (JSON + LaTeX). È il
pezzo genuinamente nuovo e coerente, e risponde alla richiesta del professore
sulle metriche CodeCarbon.

### Non-obiettivi (espliciti)

- **Non** si tocca il percorso di misura: nessun import dal runner, nessuna
  modifica a `CSV_COLUMNS` (resta **174**), nessuna dipendenza da `SESSION`.
- **Non** si implementano i moduli mock (multi-livello, validation, early-exit,
  gpu-advanced, decorators): o duplicano cose già rigorose o non sono fattibili
  onestamente su questo host. Restano nel working tree principale, fuori da
  questo ramo.
- **Non** si misura nulla: il reporter legge artefatti già misurati.
- **Non** si adotta CodeCarbon come motore di produzione (è il contrasto della
  tesi, già coperto dagli artefatti esistenti).
- **Non** si inventano fattori: intensità di rete e PUE sono dichiarati con
  fonte, mai default presentati come fatto.

## 3. Architettura e collocazione

Due file nuovi, sul registro dei moduli di sola analisi (`surface_fit.py`,
`geometry.py`, `control_gate.py`):

1. **`cwEnergyModular/carbon_report.py`** — modulo di funzioni pure e dataclass,
   testabile in isolamento. Nessuna dipendenza dal runner o da `SESSION`;
   solo stdlib (`csv`, `json`, `hashlib`, `math`, `dataclasses`, `datetime`,
   `pathlib`, `typing`).
2. **`cwEnergyModular/tools/report_carbon.py`** — CLI sottile che legge un CSV
   misurato, chiama il modulo, scrive l'output in `experiment_results/`. Serve
  alla rigenerabilità del numero per la tesi (regola: «un'analisi non tracciata
   è un numero che nessuno può rigenerare»).

Il modulo non è chiamato dal runner e non tocca lo schema P5.

## 4. Formula e modello dei fattori

### Conversione (fix del 1000×)

```
E_kWh = E_J / 3_600_000.0          # 1 kWh = 3.6e6 J
emissions_kg = E_kWh * PUE * grid_intensity_kg_per_kwh
```

### Fattori dichiarati

- **PUE**: default **1.0** per host locale, dichiarato. Il contatore del package
  misura già energia elettrica, senza overhead di raffreddamento da datacenter.
  Un `--pue > 1` è ammesso solo se si dichiara di modellare un datacenter, con
  `--pue-source`. Il default 1.2 del mock (datacenter su macchina locale) è
  sbagliato e non si replica.
- **Intensità di rete** (`grid_intensity_kg_per_kwh`): parametro **obbligatorio**,
  con **fonte obbligatoria** (`grid_source`, es. ISPRA/Ember Italia + data di
  verifica). **Nessun default**: se manca, è non finita o è `<= 0`, il report si
  rifiuta e lo dichiara. Il «0.5 media UE» inventato del mock non si replica.
- **Equivalenze** (km auto, kg carbone, ...): solo con fattori dichiarati e
  marcati come **illustrativi**; sono contesto divulgativo, non misura.

### Dataclass

```python
@dataclass(frozen=True)
class CarbonFactors:
    grid_intensity_kg_per_kwh: float   # obbligatorio, > 0, finito
    grid_source: str                   # obbligatorio, non vuoto
    pue: float = 1.0                   # default locale
    pue_source: str = "host locale: nessun overhead datacenter"
```

## 5. Flusso dati e interfacce

### Input

CSV misurato (path parametrizzato), colonna energia netta (default
`ollama_active_energy_j`, configurabile). La **CLI** legge le righe con
`csv.DictReader` e calcola lo SHA-256 del file; il **modulo** opera su righe già
parsate (`Iterable[dict]`) e riceve la provenance come argomento, restando puro.
Il reporter **non misura**. Ogni riga valida contribuisce con la sua energia in J.

### Funzioni del modulo (firma propuesta)

```python
def joule_to_kwh(energy_j: float) -> float: ...
def estimate_emissions_kg(energy_kwh: float, *, grid_intensity_kg_per_kwh: float,
                          pue: float = 1.0) -> float: ...

@dataclass
class CarbonRowResult:
    energy_j_measured: Optional[float]   # firmato, conservato
    energy_kwh: Optional[float]
    emissions_kg_estimate: Optional[float]
    status: str                          # "ok" | "excluded"
    reason: str                          # "" se ok, altrimenti la ragione

def report_carbon(rows: Iterable[dict], factors: CarbonFactors, *,
                  energy_column: str, input_provenance: dict) -> dict: ...
def render_latex(summary: dict, factors: CarbonFactors) -> str: ...
def illustrative_equivalences(emissions_kg: float, factors_eq: dict) -> list: ...
```

### Output JSON

Per riga e aggregato, con distinzione esplicita misurato/stimato:

```json
{
  "label": "stima",
  "measured": {"energy_j_total": ..., "energy_kwh_total": ..., "n_rows": ...,
               "n_excluded": ..., "excluded_reasons": {...}},
  "factors": {"pue": 1.0, "pue_source": "...",
              "grid_intensity_kg_per_kwh": ..., "grid_source": "..."},
  "estimate": {"emissions_kg": ..., "emissions_kg_per_row": ...},
  "provenance": {"input_csv": "...", "input_csv_sha256": "...",
                 "energy_column": "...", "generated_utc": "...",
                 "module": "carbon_report", "formula": "E_J/3.6e6 * PUE * grid"},
  "rows": [CarbonRowResult, ...]
}
```

### Output LaTeX

Tabella + template di paragrafo alla ML CO2 Impact, con la formula e i parametri
dichiarati, pronto per la tesi. Misurato (`E_J`, `E_kWh`) e stimato
(`emissions_kg`, etichetta «stima») tenuti visivamente distinti. Il template
dichiara che la scala assoluta del contatore non è arbitrata senza wattmetro
AC/DC (caveat del progetto) e che i fattori sono assunzioni dichiarate.

### CLI

```
python tools/report_carbon.py --input <csv> --energy-column <col>
    --grid-intensity <kg/kWh> --grid-source "<fonte + data>"
    [--pue 1.0] [--pue-source "..."] [--output-dir <dir>]
```

`--grid-intensity` e `--grid-source` obbligatori. Output: `report.json` +
`report.tex` in `--output-dir` (default
`experiment_results/carbon_report_<YYYYMMDD>/`). Stampa il riepilogo. Esce con
codice non zero se i fattori sono assenti/non validi (rifiuto dichiarato).

## 6. Error handling e regole di coerenza

- Energia **assente o non finita** → riga `excluded` con `reason` dichiarata e
  conteggiata; mai zero inventato, mai NaN nel totale.
- **Delta negativo conservato firmato**, mai clampato (regola del progetto
  «nessun troncamento»); l'emissione stimata può essere negativa e va dichiarata.
- Intensità di rete **assente/non finita/<=0** → rifiuto dichiarato
  (`ValueError`), nessun fallback silenzioso, nessun default.
- `grid_source` vuoto → rifiuto dichiarato.
- Nessun `try/except` che nasconde errori; nessuna soglia spostata; nessun
  fallback silenzioso.
- Il totale aggregato somma le sole righe `ok`; le escluse sono conteggiate con
  la loro ragione.

## 7. Testing (TDD) e verifica

File: `cwEnergyModular/tests/test_carbon_report.py`. Ogni test ha docstring che
dice *perché* esiste e quale relazione verifica. Copertura minima:

1. `joule_to_kwh`: 3.6e6 J → 1.0 kWh; 0 → 0; negativo conservato.
2. **Regressione 1000×**: `energy_j = 360000` (0.1 kWh), PUE 1.2, grid 0.5 →
   `emissions_kg == 0.06` (NON 60.0). È il bug del mock, fissato da un test.
3. PUE default 1.0 (locale).
4. Intensità di rete assente/non finita/<=0 → `ValueError`; `grid_source` vuoto
   → `ValueError`.
5. Riga con energia non finita → `excluded` con ragione, conteggiata; totale
   somma le sole `ok`.
6. Energia negativa → conservata firmata, non clampata.
7. Provenance: output porta `input_csv_sha256`, fattori con fonti, `label ==
   "stima"`, formula.
8. `render_latex` contiene la formula, i parametri dichiarati e l'etichetta
   «stima».
9. CLI end-to-end su un CSV minimo (`tmp_path`): scrive `report.json` e
   `report.tex`; rifiuto con codice non zero se grid intensity manca.

### Baseline di verifica (worktree pulito, misurata il 2026-11-10)

```
2 failed, 1155 passed, 4 skipped
```

I 2 falliti sono **artefatti costanti del checkout CRLF**, non difetti di codice
e indipendenti da questo lavoro:
- `tests/test_preflight_gate_p44.py:271` (SHA runner su disco CRLF vs blob LF
  registrato);
- `tests/test_run_gate_p44_metrologico.py:111` (CSV pilota: byte registrati vs
  checkout CRLF).

I 4 salti: 3 RAPL (`tests/test_rapl.py:43`, host Linux) + 1 ecologits
(`tests/test_cloud_proxy_and_mapping.py:46`).

**Criterio di accettazione:** il lavoro aggiunge test verdi e **non introduce
nessun fallimento nuovo** oltre i 2 costanti. La suite si esegue con
`pytest cwEnergyModular` (mai nudo dalla radice), output incollato per intero.
Un commit per punto.

## 8. Piano dei commit (punti unitari)

1. `feat(analysis): modulo carbon_report con formula kWh corretta e fattori
   dichiarati` — modulo + test TDD (punti 1-8).
2. `feat(tool): CLI report_carbon per artefatto rigenerabile` — CLI + test
   end-to-end (punto 9).
3. (eventuale) `docs(analysis): esempio di report su artefatto tracciato` —
   solo se si genera un artefatto reale per la tesi; l'artefatto entra con il
   proprio commit e la propria analisi.

## 9. Fuori perimetro / decisioni esplicite

- I moduli mock e le modifiche ai 5 file tracciati restano nel working tree
  principale (lavoro di un'altra sessione): questo ramo non li tocca.
- Nessuna modifica a `CSV_COLUMNS`, al runner, a `SESSION`, allo schema P5.
- Nessun percorso di stima in produzione: il report è analisi, etichettato
  «stima», separato dalla misura.
- La scelta dei fattori reali (intensità di rete Italia con fonte verificata)
  è dell'utente al momento della generazione dell'artefatto per la tesi; il
  modulo non li inventa.