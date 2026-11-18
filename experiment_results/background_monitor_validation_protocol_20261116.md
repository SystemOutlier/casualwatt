# Protocollo operativo — Campagna Windows 11
## Validazione BackgroundMonitor + classificazione processi + integrazione P4.9

**Data:** 2026-11-18 (corretto da 2026-11-16)
**Commit:** `1c09e8dc7` su `emenda/background-controlled-20261115`
**Obiettivo:** Verificare sperimentalmente che il BackgroundMonitor funzioni in condizioni reali su Windows 11, prima di procedere con il Background Activity Compensation & Validation System.

---

## 1. Configurazione

| Parametro | Valore |
|-----------|--------|
| Modello | `hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest` |
| Prompt | c-001, c-002, c-003 (prompt corti esistenti) |
| Repliche per configurazione | 6 (protocollo P4.4) |
| Blocchi totali | 18 (3 prompt × 6 repliche) |
| Contatore energetico | EMI (primario) → PawnIO (fallback) |
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

```powershell
Set-Location "C:\Users\Massimo\Documents\CasualWatt\CWProject"

# Verifica commit corretto
git log -1 --oneline
# Deve mostrare: 1c09e8dc7 docs: piano e protocollo campagna Windows 11

# Verifica branch
git status --short --branch
# Deve mostrare: emenda/background-controlled-20261115
```

### 2.2 Verifica ambiente Python

```powershell
# Verifica Python e pytest
$python = "C:\Users\Massimo\AppData\Local\Python\pythoncore-3.15-64\python.exe"
& $python --version
# Deve mostrare: Python 3.15.x

& $python -m pytest --version
# Deve mostrare: pytest 8.x
```

### 2.3 Verifica suite completa

```powershell
# Esegui la suite completa prima della campagna
& $python -m pytest cwEnergyModular -q -ra 2>&1 |
    Tee-Object "$env:TEMP\casualwatt-pre-campaign.log"

# Verifica: 1727+ passed, 4 skipped, 4 failed preesistenti
# I 4 fallimenti sono: gate_uncertainty non installato + git_head non antenato
```

### 2.4 Verifica motore Ollama

```powershell
# Verifica che Ollama sia in esecuzione
curl http://localhost:11434/api/version

# Verifica che il modello sia residente
curl http://localhost:11434/api/ps | ConvertFrom-Json | Select-Object -ExpandProperty models

# Se il modello non è caricato, scaricalo
ollama pull hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest
```

### 2.5 Verifica contatore energetico

```powershell
# Verifica EMI
& $python -c "
from energy.emi_backend import EMIBackend
emi = EMIBackend()
print(f'Device: {emi.device_name}')
print(f'Channel: {emi.channel_name}')
reading = emi.read_energy_j()
print(f'Reading: {reading:.6f} J')
"
```

### 2.6 Verifica baseline idle

```powershell
# Esegui una calibrazione idle di test (firma: seconds, extended)
& $python -c "
from energy.energy_session import EnergySession
session = EnergySession()
session.calibrate_idle(seconds=30)
print(f'Idle power: {session.idle_power_w:.4f} W')
print(f'Baseline stats: {session.baseline_stats}')
"

# Calibrazione estesa (10 ripetizioni, CV ≤ 5%)
& $python -c "
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

```powershell
# Crea directory per la campagna e le sotto-directory delle fasi
$campaign_dir = "C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\background_monitor_validation_20261116"
New-Item -ItemType Directory -Path "$campaign_dir\phase_a_stable" -Force
New-Item -ItemType Directory -Path "$campaign_dir\phase_b_variable" -Force

# Copia il piano sperimentale
Copy-Item "experiment_results/prep_plan_frozen.json" "$campaign_dir\" -ErrorAction SilentlyContinue
```

### 3.2 Fase A — Background stabile

```powershell
Set-Location $campaign_dir

# Configura il piano sperimentale
# (adatta i prompt e il modello alla configurazione scelta)

# Esegui il benchmark con runner v4 (interfaccia reale)
& $python -c "
import sys
sys.path.insert(0, 'C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular')
from benchmark_v4 import run_v4_benchmark

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
    results_path=r'$campaign_dir\phase_a_stable\casualwatt_v4_results.csv',
    block_summary_path=r'$campaign_dir\phase_a_stable\casualwatt_v4_block_summary.csv',
)
```

### 3.3 Fase B — Background variabile

```powershell
# Avvia un processo CPU-intensivo
$cpuStressProcess = Start-Process -FilePath $python -ArgumentList '-c', '
import time
while True:
    sum(i*i for i in range(10000))
' -WindowStyle Hidden -PassThru

# Salva il PID per la terminazione
$cpuStressPid = $cpuStressProcess.Id
Write-Host "Processo CPU stress avviato: PID $cpuStressPid"

# Attendi 30 secondi per stabilizzazione
Start-Sleep -Seconds 30

# Esegui il benchmark con runner v4 (interfaccia reale)
& $python -c "
import sys
sys.path.insert(0, 'C:\\Users\\Massimo\\Documents\\CasualWatt\\CWProject\\cwEnergyModular')
from benchmark_v4 import run_v4_benchmark

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
    substitution_seed='20261118b',  # Obbligatorio (Emenda 8)
    results_path=r'$campaign_dir\phase_b_variable\casualwatt_v4_results.csv',
    block_summary_path=r'$campaign_dir\phase_b_variable\casualwatt_v4_block_summary.csv',
)

# Ferma il processo CPU-intensivo (PowerShell, fuori dal blocco Python)
"

# Terminazione del processo CPU-intensivo
if (Get-Process -Id $cpuStressPid -ErrorAction SilentlyContinue) {
    Stop-Process -Id $cpuStressPid -Force
    Write-Host "Processo CPU stress terminato: PID $cpuStressPid"
} else {
    Write-Host "Processo CPU stress gia' terminato: PID $cpuStressPid"
}
```

---

## 4. Analisi risultati

### 4.1 Verifica file prodotti

```powershell
# Verifica CSV risultati
Get-ChildItem "$campaign_dir\phase_a_stable\*.csv" | Select-Object Name, Length
Get-ChildItem "$campaign_dir\phase_b_variable\*.csv" | Select-Object Name, Length

# Verifica JSON diagnostico
Get-ChildItem "$campaign_dir\phase_a_stable\background_monitor.json" | Select-Object Name, Length
Get-ChildItem "$campaign_dir\phase_b_variable\background_monitor.json" | Select-Object Name, Length
```

### 4.2 Verifica schema CSV P5

```powershell
# Verifica che CSV_COLUMNS abbia 174 nomi
& $python -c "
import sys
sys.path.insert(0, 'C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular')
from casualwatt_csv_export import CSV_COLUMNS, BLOCK_SUMMARY_COLUMNS, POINT_SUMMARY_COLUMNS, RUN_METADATA_COLUMNS
print(f'CSV_COLUMNS: {len(CSV_COLUMNS)} nomi')
print(f'BLOCK_SUMMARY_COLUMNS: {len(BLOCK_SUMMARY_COLUMNS)} nomi')
print(f'POINT_SUMMARY_COLUMNS: {len(POINT_SUMMARY_COLUMNS)} nomi')
print(f'RUN_METADATA_COLUMNS: {len(RUN_METADATA_COLUMNS)} nomi')
"
```

### 4.3 Verifica background_monitor.json

```powershell
# Analizza il JSON diagnostico
& $python -c "
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
" "$campaign_dir\phase_a_stable\background_monitor.json"
```

### 4.4 Verifica note CSV

```powershell
# Verifica che le note CSV contengano i verdetti
& $python -c "
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
" "$campaign_dir\phase_a_stable\casualwatt_v4_results.csv"
```

### 4.5 Verifica chain_status

```powershell
# Verifica che chain_status sia presente nelle note
& $python -c "
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
" "$campaign_dir\phase_a_stable\casualwatt_v4_results.csv"
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

### 5.2 Campagna Fase B (background variabile)

| Criterio | Risultato atteso | Verifica |
|----------|------------------|----------|
| Campionamento pre/post | Ogni blocco ha campioni pre e post | `background_monitor.json` |
| Verdetto locale | `unstable` per alcuni blocchi | `bg_local_verdict` |
| Verdetto globale | `unstable` (deriva significativa) | `bg_global_verdict` |
| chain_status | Token P4.9 riflette instabilità | CSV `notes` |
| Note CSV | `bg_local:unstable; bg_global:unstable` | CSV `notes` |
| Misure energetiche salvate | Le righe CSV sono complete | CSV risultati |
| Nessun blocco perso | 18 blocchi totali | Conteggio righe CSV |

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

```powershell
# Confronta Fase A vs Fase B
& $python -c "
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
" "$campaign_dir\phase_a_stable\background_monitor.json" `
  "$campaign_dir\phase_b_variable\background_monitor.json"
```

---

## 8. Report finale

Dopo la campagna, prepara un report che includa:

1. **Configurazione**: modello, prompt, repliche, contatore energetico
2. **Risultati Fase A**: verdetti, chain_status, overhead
3. **Risultati Fase B**: verdetti, chain_status, overhead
4. **Confronto A vs B**: differenze nei verdetti e nell'overhead
5. **Problemi riscontrati**: errori, avvisi, comportamenti inattesi
6. **Conclusioni**: il sistema è pronto per il Background Activity Compensation?

---

## 9. Note importanti

- **Non modificare il codice** durante la campagna: se emergono bug, fermati e correggi prima di riprendere.
- **Conserva tutti i file**: anche quelli che sembrano errati, perché servono per l'analisi post-campagna.
- **Non fare merge in `main`** finché non hai completato tutte le verifiche.
- **Documenta i problemi**: se il monitor fallisce, registra la causa e il contesto.
- **Verifica l'overhead**: il campionamento CPU totale (3 s) prima/dopo ogni blocco aggiunge tempo — misuralo e dichiaralo.
