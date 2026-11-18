# Protocollo operativo — Campagna Linux
## Validazione BackgroundMonitor + classificazione processi + integrazione P4.9

**Data:** 2026-11-18
**Commit del codice di produzione congelato:** `1c09e8dc7`  
**Branch documentale:** `emenda/background-controlled-20261115` (i commit successivi al codice congelato devono restare documentali)
**Obiettivo:** Verificare sperimentalmente che il BackgroundMonitor funzioni in condizioni reali su Linux con contatore RAPL, prima di procedere con il Background Activity Compensation & Validation System.

---

## 1. Configurazione

| Parametro | Valore |
|-----------|--------|
| Modello | `hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest` |
| Prompt | c-001, c-002, c-003 (prompt corti esistenti) |
| Blocchi per prompt e condizione | 3 (9 blocchi per fase; 18 complessivi) |
| Blocchi totali | 18 (3 prompt × 6 repliche) |
| Contatore energetico | RAPL (primario) → `unavailable` (se non disponibile) |
| Finestra idle | 30 s (3 ripetizioni standard; 10 ripetizioni estese) |
| Campionamento background | Pre/post blocco (3 s CPU totale) |
| Tolleranza CPU | 5% (default) |
| Tolleranza potenza | Derivata dalla caratterizzazione idle |

### Condizioni del background

| Fase | Descrizione | Blocchi |
|------|-------------|---------|
| A | Background stabile (browser + editor) | 9 (3 prompt × 3 repliche) |
| B | Background variabile (processo CPU-intensivo) | 9 (3 prompt × 3 repliche) |

---

## 2. Controlli preliminari

### 2.1 Verifica repository

```bash
cd /percorso/verso/CWProject

# Verifica branch e stato pulito
git status --short --branch
# Deve mostrare il branch emenda/background-controlled-20261115 senza modifiche locali

# Verifica che il codice di produzione corrisponda al commit congelato
git diff --exit-code 1c09e8dc7..HEAD -- cwEnergyModular
# Nessun output e codice di uscita 0: nessuna modifica al codice di produzione
# I commit successivi possono contenere esclusivamente aggiornamenti documentali.
```

### 2.2 Verifica ambiente Python

```bash
# Verifica Python e pytest
python3 --version
# Deve mostrare: Python 3.10+ (o versione installata)

python3 -m pytest --version
# Deve mostrare: pytest 8.x
```

### 2.3 Verifica suite completa

```bash
# Esegui la suite completa prima della campagna
python3 -m pytest cwEnergyModular -q -ra 2>&1 | tee /tmp/casualwatt-pre-campaign.log

# Non assumere a priori un numero di test o fallimenti attesi.
# Registra l'output completo e classifica ogni errore prima di procedere.
# Non avviare la campagna se falliscono test pertinenti a EnergySession,
# BackgroundMonitor, classificazione processi, runner v4 o export dei risultati.
```

### 2.4 Verifica motore Ollama

```bash
# Verifica che Ollama sia in esecuzione
curl http://localhost:11434/api/version

# Verifica che il modello sia residente
curl http://localhost:11434/api/ps | python3 -m json.tool

# Se il modello non è caricato, scaricalo
ollama pull hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest
```

### 2.5 Verifica permessi RAPL

```bash
# Individua i contatori Powercap effettivamente esposti dal kernel
find /sys/class/powercap -type f -name energy_uj -print

# Verifica permessi sul contatore (sostituisci il percorso con quello trovato)
RAPL_ENERGY_FILE="/sys/class/powercap/intel-rapl:0/energy_uj"
test -r "$RAPL_ENERGY_FILE" && cat "$RAPL_ENERGY_FILE"

# Verifica i nomi dei domini energetici disponibili
find /sys/class/powercap -type f -name name -exec sh -c 'printf "%s: " "$1"; cat "$1"' _ {} \;

# Se il file esiste ma non è leggibile, documenta proprietario/gruppo/permessi.
# Non modificare i permessi di sistema senza aver verificato la policy della macchina.
```

### 2.6 Verifica contatore energetico RAPL

```bash
# Verifica che il backend RAPL funzioni
python3 -c "
from energy.energy_session import EnergySession
session = EnergySession()
# La sessione dovrebbe selezionare RAPL automaticamente su Linux
print(f'Channel: {session._source}')
"
```

### 2.7 Verifica baseline idle

```bash
# Esegui una calibrazione idle di test (firma: seconds, extended)
python3 -c "
from energy.energy_session import EnergySession
session = EnergySession()
session.calibrate_idle(seconds=30)
print(f'Idle power: {session.idle_power_w:.4f} W')
print(f'Baseline stats: {session.baseline_stats}')
"

# Calibrazione estesa (10 ripetizioni, CV ≤ 5%)
python3 -c "
from energy.energy_session import EnergySession
session = EnergySession()
session.calibrate_idle(seconds=30, extended=True)
print(f'Idle power: {session.idle_power_w:.4f} W')
print(f'Baseline stats: {session.baseline_stats}')
"
```

---

## 3. Esecuzione campagna

### 3.1 Directory risultati

```bash
# Crea directory per la campagna e le sotto-directory delle fasi
PROJECT_ROOT="/percorso/verso/CWProject"
export PROJECT_ROOT
CAMPAIGN_DIR="$PROJECT_ROOT/experiment_results/background_monitor_validation_linux_20261118"
export CAMPAIGN_DIR
mkdir -p "$CAMPAIGN_DIR/phase_a_stable"
mkdir -p "$CAMPAIGN_DIR/phase_b_variable"

# Copia il piano sperimentale (se disponibile)
cp "$PROJECT_ROOT/experiment_results/prep_plan_frozen.json" "$CAMPAIGN_DIR/" 2>/dev/null || true
```

### 3.2 Fase A — Background stabile

```bash
cd "$CAMPAIGN_DIR"

# Esegui il benchmark con runner v4 (interfaccia reale)
python3 -c "
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ['PROJECT_ROOT']) / 'cwEnergyModular'))
from benchmark_v4 import run_v4_benchmark
campaign_dir = Path(os.environ['CAMPAIGN_DIR'])

# Configurazione (interfaccia reale di run_v4_benchmark)
run_v4_benchmark(
    local_models=['hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest'],
    prompts=[
        {'id': 'c-001', 'content': 'Scrivi una breve introduzione all\'intelligenza artificiale.'},
        {'id': 'c-002', 'content': 'Spiega cos\'è il machine learning in poche righe.'},
        {'id': 'c-003', 'content': 'Descrivi la differenza tra supervised e unsupervised learning.'},
    ],
    m=1,  # 1 richiesta per blocco
    blocks_per_point=3,  # 3 blocchi per punto (repliche)
    num_predict=160,
    max_invalidated_blocks=5,  # Obbligatorio (Emenda 8)
    substitution_seed='20261118a',  # Obbligatorio (Emenda 8)
    results_path=campaign_dir / 'phase_a_stable' / 'casualwatt_v4_results.csv',
    block_summary_path=campaign_dir / 'phase_a_stable' / 'casualwatt_v4_block_summary.csv',
)
"
```

### 3.3 Fase B — Background variabile

```bash
set -e
cd "$CAMPAIGN_DIR"

# Prepara un carico CPU Python riproducibile come fallback.
STRESS_SCRIPT="$CAMPAIGN_DIR/cpu_stress.py"
cat > "$STRESS_SCRIPT" <<'PY'
while True:
    sum(i*i for i in range(10000))
PY

# Avvia stress-ng se disponibile; altrimenti usa lo script Python.
if command -v stress-ng >/dev/null 2>&1; then
    stress-ng --cpu 1 --timeout 900s &
    CPU_STRESS_PID=$!
else
    python3 "$STRESS_SCRIPT" &
    CPU_STRESS_PID=$!
fi

cleanup_cpu_stress() {
    if kill -0 "$CPU_STRESS_PID" 2>/dev/null; then
        kill "$CPU_STRESS_PID" 2>/dev/null || true
        wait "$CPU_STRESS_PID" 2>/dev/null || true
        echo "Processo CPU stress terminato: PID $CPU_STRESS_PID"
    fi
    rm -f "$STRESS_SCRIPT"
}
trap cleanup_cpu_stress EXIT INT TERM

echo "Processo CPU stress avviato: PID $CPU_STRESS_PID"
sleep 30
if ! kill -0 "$CPU_STRESS_PID" 2>/dev/null; then
    echo "ERRORE: il processo CPU stress è terminato prima del benchmark."
    exit 1
fi

# Esegui il benchmark con runner v4 (interfaccia verificata nel codice congelato).
python3 -c "
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(os.environ['PROJECT_ROOT']) / 'cwEnergyModular'))
from benchmark_v4 import run_v4_benchmark
campaign_dir = Path(os.environ['CAMPAIGN_DIR'])

run_v4_benchmark(
    local_models=['hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest'],
    prompts=[
        {'id': 'c-001', 'content': 'Scrivi una breve introduzione all\\'intelligenza artificiale.'},
        {'id': 'c-002', 'content': 'Spiega cos\\'è il machine learning in poche righe.'},
        {'id': 'c-003', 'content': 'Descrivi la differenza tra supervised e unsupervised learning.'},
    ],
    m=1,
    blocks_per_point=3,
    num_predict=160,
    max_invalidated_blocks=5,
    substitution_seed='20261118b',
    results_path=campaign_dir / 'phase_b_variable' / 'casualwatt_v4_results.csv',
    block_summary_path=campaign_dir / 'phase_b_variable' / 'casualwatt_v4_block_summary.csv',
)
"

# Cleanup esplicito al termine normale; la trap copre errori e interruzioni.
trap - EXIT INT TERM
cleanup_cpu_stress
```

---

## 4. Analisi risultati

### 4.1 Verifica file prodotti

```bash
# Verifica CSV risultati
ls -la "$CAMPAIGN_DIR/phase_a_stable/"*.csv
ls -la "$CAMPAIGN_DIR/phase_b_variable/"*.csv

# Verifica JSON diagnostico
ls -la "$CAMPAIGN_DIR/phase_a_stable/background_monitor.json"
ls -la "$CAMPAIGN_DIR/phase_b_variable/background_monitor.json"
```

### 4.2 Verifica schema CSV P5

```bash
# Verifica che CSV_COLUMNS abbia 174 nomi
python3 -c "
import sys
sys.path.insert(0, str(Path(os.environ['PROJECT_ROOT']) / 'cwEnergyModular'))
from pathlib import Path
import os
sys.path.insert(0, str(Path(os.environ['PROJECT_ROOT']) / 'cwEnergyModular'))
from casualwatt_csv_export import CSV_COLUMNS, BLOCK_SUMMARY_COLUMNS, POINT_SUMMARY_COLUMNS, RUN_METADATA_COLUMNS
print(f'CSV_COLUMNS: {len(CSV_COLUMNS)} nomi')
print(f'BLOCK_SUMMARY_COLUMNS: {len(BLOCK_SUMMARY_COLUMNS)} nomi')
print(f'POINT_SUMMARY_COLUMNS: {len(POINT_SUMMARY_COLUMNS)} nomi')
print(f'RUN_METADATA_COLUMNS: {len(RUN_METADATA_COLUMNS)} nomi')
"
```

### 4.3 Verifica background_monitor.json

```bash
# Analizza il JSON diagnostico
python3 -c "
import json
import sys

json_path = sys.argv[1]
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f'Record totali: {len(data)}')
print(f'Chiavi: {list(data[0].keys()) if data else \"Nessun record\"}')

# Verifica campi obbligatori
required_fields = ['batch_id', 'block_id', 'bg_local_verdict', 'bg_global_verdict']
for field in required_fields:
    present = all(field in record for record in data)
    print(f'{field}: {\"✓\" if present else \"✗\"}')

# Riepilogo verdetti
local_verdicts = [record.get('bg_local_verdict') for record in data]
global_verdicts = [record.get('bg_global_verdict') for record in data]
print(f'Verdetti locali: {local_verdicts}')
print(f'Verdetti globali: {global_verdicts}')
" "$CAMPAIGN_DIR/phase_a_stable/background_monitor.json"
```

### 4.4 Verifica note CSV

```bash
# Verifica che le note CSV contengano i verdetti
python3 -c "
import csv
import sys

csv_path = sys.argv[1]
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

notes_with_bg = [row for row in rows if 'bg_local:' in row.get('notes', '') or 'bg_global:' in row.get('notes', '')]
print(f'Righe con verdetti background: {len(notes_with_bg)} / {len(rows)}')

# Mostra esempio
if notes_with_bg:
    print(f'Esempio: {notes_with_bg[0].get(\"notes\", \"\")[:200]}...')
" "$CAMPAIGN_DIR/phase_a_stable/casualwatt_v4_results.csv"
```

### 4.5 Verifica chain_status

```bash
# Verifica che chain_status sia presente nelle note
python3 -c "
import csv
import sys

csv_path = sys.argv[1]
with open(csv_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    rows = list(reader)

chain_status_rows = [row for row in rows if 'chain_status:' in row.get('notes', '')]
print(f'Righe con chain_status: {len(chain_status_rows)} / {len(rows)}')

# Estrai i token
tokens = []
for row in chain_status_rows:
    notes = row.get('notes', '')
    if 'chain_status:' in notes:
        token = notes.split('chain_status:')[1].split(';')[0].split('\n')[0].strip()
        tokens.append(token)

from collections import Counter
print(f'Token P4.9: {Counter(tokens)}')
" "$CAMPAIGN_DIR/phase_a_stable/casualwatt_v4_results.csv"
```

---

## 5. Criteri di accettazione

### 5.1 Campagna Fase A (background stabile)

| Criterio | Risultato atteso | Verifica |
|----------|------------------|----------|
| Campionamento pre/post | Ogni blocco ha campioni pre e post | `background_monitor.json` |
| Classificazione processi | Ollama = TARGET_WORKLOAD | `background_monitor.json` |
| Verdetto locale | `stable` per la maggior parte dei blocchi | `bg_local_verdict` |
| Verdetto globale | `stable` o `unstable` (deriva graduale) | `bg_global_verdict` |
| chain_status | Token P4.9 presente nelle note | CSV `notes` |
| Note CSV | `bg_local:...; bg_global:...` presenti | CSV `notes` |
| Schema CSV P5 | 174 nomi congelati | `CSV_COLUMNS` |
| Nessun TypeError | Finalizzazione senza errori | Log runner |
| Nessun duplicato JSON | Ogni blocco = 1 record | `background_monitor.json` |
| Contatore RAPL | Lettura corretta da `/sys/class/powercap/` | Log runner |

### 5.2 Campagna Fase B (background variabile)

| Criterio | Risultato atteso | Verifica |
|----------|------------------|----------|
| Campionamento pre/post | Ogni blocco ha campioni pre e post | `background_monitor.json` |
| Verdetto locale | `unstable` per alcuni blocchi | `bg_local_verdict` |
| Verdetto globale | `unstable` (deriva significativa) | `bg_global_verdict` |
| chain_status | Token P4.9 riflette instabilità | CSV `notes` |
| Note CSV | `bg_local:unstable; bg_global:unstable` | CSV `notes` |
| Misure energetiche salvate | Le righe CSV sono complete | CSV risultati |
| Nessun blocco perso | 9 blocchi nella Fase B | Conteggio righe CSV |

---

## 6. File da conservare

Dopo la campagna, conserva questi file in `experiment_results/`:

| File | Descrizione |
|------|-------------|
| `casualwatt_v4_results.csv` | Righe energetiche con note |
| `casualwatt_v4_block_summary.csv` | Riepiloghi di blocco |
| `background_monitor.json` | Artefatto diagnostico completo |
| `casualwatt_run_metadata.csv` | Metadati del run |
| `campaign_log.txt` | Log completo dell'esecuzione |
| `prep_plan_frozen.json` | Piano sperimentale (se modificato) |

---

## 7. Analisi post-campagna

Dopo aver completato entrambe le fasi, esegui questa analisi:

```bash
# Confronta Fase A vs Fase B
python3 -c "
import json
import sys

phase_a_json = sys.argv[1]
phase_b_json = sys.argv[2]

with open(phase_a_json, 'r', encoding='utf-8') as f:
    phase_a = json.load(f)
with open(phase_b_json, 'r', encoding='utf-8') as f:
    phase_b = json.load(f)

print('=== CONFRONTO FASE A vs FASE B ===')
print(f'Fase A: {len(phase_a)} blocchi')
print(f'Fase B: {len(phase_b)} blocchi')

# Verdetti locali
a_local = [r.get('bg_local_verdict') for r in phase_a]
b_local = [r.get('bg_local_verdict') for r in phase_b]
print(f'Verdetti locali A: {a_local}')
print(f'Verdetti locali B: {b_local}')

# Verdetti globali
a_global = [r.get('bg_global_verdict') for r in phase_a]
b_global = [r.get('bg_global_verdict') for r in phase_b]
print(f'Verdetti globali A: {a_global}')
print(f'Verdetti globali B: {b_global}')

# Overhead
a_overhead = [r.get('overhead_s') for r in phase_a if r.get('overhead_s')]
b_overhead = [r.get('overhead_s') for r in phase_b if r.get('overhead_s')]
if a_overhead:
    print(f'Overhead medio A: {sum(a_overhead)/len(a_overhead):.3f} s')
if b_overhead:
    print(f'Overhead medio B: {sum(b_overhead)/len(b_overhead):.3f} s')
" "$CAMPAIGN_DIR/phase_a_stable/background_monitor.json" \
  "$CAMPAIGN_DIR/phase_b_variable/background_monitor.json"
```

---

## 8. Note specifiche Linux

### RAPL/Powercap

- RAPL/Powercap è disponibile in funzione di CPU, kernel e driver: su alcune piattaforme AMD è esposto tramite domini `amd-rapl`; `k10temp` è un driver di temperatura e non va considerato un contatore energetico.
- Non assumere che il percorso sia sempre `intel-rapl`: usare i file effettivamente trovati sotto `/sys/class/powercap`.
- Se il contatore non è disponibile, registrare esplicitamente `unavailable`; la sessione non può essere presentata come validazione energetica RAPL.
- I permessi di lettura potrebbero richiedere l'utente nel gruppo `power` o l'esecuzione come root.
- I domini energetici (PKG, PP0, PP1, DRAM) variano per CPU: verifica quali sono disponibili.

### Differenze rispetto a Windows

| Aspetto | Windows | Linux |
|---------|---------|-------|
| Contatore primario | EMI | RAPL/Powercap |
| Fallback | PawnIO | `unavailable` |
| Campionamento CPU | `psutil` | `psutil` (compatibile) |
| Permessi | Admin per PawnIO | Lettura RAPL (gruppo power) |
| Processi | `psutil` Windows | `psutil` Linux |

---

## 9. Report finale

Dopo la campagna, prepara un report che includa:

1. **Configurazione**: modello, prompt, repliche, contatore energetico
2. **Risultati Fase A**: verdetti, chain_status, overhead
3. **Risultati Fase B**: verdetti, chain_status, overhead
4. **Confronto A vs B**: differenze nei verdetti e nell'overhead
5. **Problemi riscontrati**: errori, avvisi, comportamenti inattesi
6. **Conclusioni**: il sistema è pronto per il Background Activity Compensation?

---

## 10. Note importanti

- **Non modificare il codice** durante la campagna: se emergono bug, fermati e correggi prima di riprendere.
- **Conserva tutti i file**: anche quelli che sembrano errati, perché servono per l'analisi post-campagna.
- **Non fare merge in `main`** finché non hai completato tutte le verifiche.
- **Documenta i problemi**: se il monitor fallisce, registra la causa e il contesto.
- **Verifica l'overhead**: il campionamento CPU totale (3 s) prima/dopo ogni blocco aggiunge tempo — misuralo e dichiaralo.
- **Verifica RAPL**: se il contatore non è disponibile, la campagna non è valida per la validazione cross-platform.
