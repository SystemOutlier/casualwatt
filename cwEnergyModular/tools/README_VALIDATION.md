# Strumento di Validazione HWiNFO

## Panoramica

Questo strumento confronta l'energia misurata da **CasualWatt** (via LibreHardwareMonitor) con quella misurata da **HWiNFO Sensors**, fornendo una validazione indipendente delle misure energetiche.

## Perché usare questo strumento

- ✓ **Validazione scientifica**: Confronto con tool indipendente (HWiNFO)
- ✓ **Ground truth esterno**: Verifica che LHM stia leggendo correttamente
- ✓ **Sezione tesi**: Dati per Capitolo 6 "Validazione incrociata"
- ✓ **Diagnostica**: Identifica problemi di configurazione sensori

## Requisiti

- **Python 3.8+**
- **NumPy** (opzionale, per calcolo efficiente): `pip install numpy`
- **Matplotlib** (opzionale, per grafici): `pip install matplotlib`

Installazione dipendenze opzionali:
```bash
pip install numpy matplotlib
```

## Utilizzo

### Passo 1: Eseguire il benchmark con CasualWatt

```bash
cd cwEnergyModular
python main.py
# Configura e avvia il benchmark
# Risultati salvati in: results/benchmark_YYYYMMDD-HHMMSS.csv
```

### Passo 2: Eseguire lo stesso benchmark con HWiNFO in logging

1. **Apri HWiNFO**
2. **Configura logging**:
   - Menu: `File` → `Settings` → `Logging`
   - Polling interval: **100 ms** (10 Hz) o **50 ms** (20 Hz)
   - Log format: **CSV**
3. **Avvia logging**:
   - Menu: `File` → `Logging Start`
   - Salva come: `hwinfo_log_YYYYMMDD.csv`
4. **Esegui lo stesso benchmark** di CasualWatt
5. **Ferma logging**:
   - Menu: `File` → `Logging Stop`

### Passo 3: Eseguire lo script di validazione

```bash
cd cwEnergyModular
python tools/validate_hwinfo.py \
    --casualwatt results/benchmark_20261021-143052.csv \
    --hwinfo hwinfo_log_20261021.csv \
    --output validation_result.json \
    --plot
```

### Parametri

- `--casualwatt`: Percorso al CSV di CasualWatt (obbligatorio)
- `--hwinfo`: Percorso al CSV di HWiNFO (obbligatorio)
- `--power-column`: Nome colonna potenza in HWiNFO (default: "CPU Package Power")
- `--output`: File output JSON (default: validation_result.json)
- `--plot`: Genera grafico di confronto (richiede matplotlib)

### Esempio completo

```bash
python tools/validate_hwinfo.py \
    --casualwatt results/benchmark_20261021-143052.csv \
    --hwinfo hwinfo_log_20261021.csv \
    --power-column "CPU Package Power" \
    --output validation_20261021.json \
    --plot
```

## Output

### Console

```
======================================================================
VALIDAZIONE INCROCIATA: CasualWatt vs HWiNFO
======================================================================

📖 Leggo CSV CasualWatt: results/benchmark_20261021-143052.csv
   ✓ 10 query lette
   ✓ Energia totale CasualWatt: 285.42 J

📖 Leggo CSV HWiNFO: hwinfo_log_20261021.csv
   ✓ 1250 campioni letti
   ✓ Energia totale HWiNFO: 278.91 J

📊 Calcolo statistiche di validazione...

======================================================================
RISULTATI VALIDAZIONE
======================================================================
  Energia CasualWatt (LHM): 285.42 J
  Energia HWiNFO:           278.91 J
  Differenza assoluta:      6.51 J
  Differenza relativa:      2.33 %
  Rapporto CW/HW:           1.0233
======================================================================
✓ VALIDAZIONE RIUSCITA: differenza < 5%

💾 Salvo report: validation_result.json
✓ Report salvato: validation_result.json

📈 Genero grafico di confronto...
✓ Grafico salvato: validation_result.png

✓ Validazione completata
```

### File JSON (validation_result.json)

```json
{
  "validation_type": "cross_platform_hwinfo",
  "timestamp": "Tue Oct 21 14:45:32 2026",
  "statistics": {
    "casualwatt_energy_j": 285.42,
    "hwinfo_energy_j": 278.91,
    "absolute_difference_j": 6.51,
    "relative_difference_pct": 2.33,
    "ratio": 1.0233
  },
  "conclusion": "VALID",
  "notes": [
    "Differenza < 5%: validazione riuscita",
    "Differenza 5-10%: accettabile ma verificare",
    "Differenza > 10%: controllare configurazione"
  ]
}
```

### Grafico (validation_result.png)

Due subplot:
1. **Potenza HWiNFO**: Andamento temporale della potenza CPU Package [W]
2. **Energia CasualWatt**: Energia per query [J]

## Interpretazione risultati

### Differenza < 5%

**✓ VALIDAZIONE RIUSCITA**

Le misure di CasualWatt sono accurate e coerenti con HWiNFO.

**Per la tesi**:
> "La validazione incrociata con HWiNFO Sensors mostra una differenza del 2.33%, confermando l'accuratezza delle misure di CasualWatt (< 5%)."

### Differenza 5-10%

**⚠ VALIDAZIONE ACCETTABILE**

Le misure sono ragionevoli ma c'è una discrepanza moderata.

**Possibili cause**:
- Intervalli di tempo non perfettamente allineati
- Attività di sistema durante il benchmark
- Polling rate diverso tra LHM e HWiNFO
- Sensori leggermente diversi (firmware vs SMBus)

**Azioni**:
- Ripetere la misura
- Verificare che nessun altro processo fosse attivo
- Controllare che entrambi i tool leggano "CPU Package Power"

### Differenza > 10%

**❌ VALIDAZIONE FALLITA**

Discrepanza significativa tra le misure.

**Possibili cause**:
- CasualWatt e HWiNFO leggono sensori diversi
- Attività di sistema massiccia durante il benchmark
- Configurazione errata di uno dei due tool
- Problemi driver/firmware

**Azioni**:
1. Verifica sensori in HWiNFO:
   - Apri HWiNFO → Sensors
   - Cerca "CPU Package Power"
   - Annota il valore idle (es. 15W)
2. Verifica sensori in CasualWatt:
   - Esegui `python diagnostics.py`
   - Controlla che "CPU Package" sia letto
   - Confronta valore idle con HWiNFO
3. Ripeti il benchmark in condizioni controllate

## Configurazione HWiNFO raccomandata

### Settings

1. **Sensor Settings**:
   - Polling interval: **100 ms** (10 Hz)
   - Disable "Sensor Stability Enhancement"
   - Enable tutti i sensori CPU

2. **Logging Settings**:
   - Format: **CSV**
   - Interval: **100 ms** (coerente con CasualWatt)
   - Fields: CPU Package Power, CPU Core Power, GPU Power (se presente)

3. **CSV Output**:
   - Encoding: UTF-8
   - Decimal separator: punto (.)
   - Date format: ISO 8601

### Verifica sensori

Prima di iniziare il logging:

1. Apri HWiNFO → **Sensors-only mode**
2. Cerca sezione **CPU**
3. Verifica che esistano:
   - ✓ CPU Package Power [W]
   - ✓ CPU Core Power [W] (opzionale)
   - ✓ CPU Temperature [°C]
4. Annota valori idle:
   - Package Power idle: ~10-20W (dipende da CPU)
   - Core Power idle: ~5-15W

Se "CPU Package Power" non esiste:
- CPU potrebbe non supportare il sensore
- Aggiorna BIOS/UEFI
- Prova un'altra versione di HWiNFO

## Configurazione CasualWatt

### Settings

1. **Polling rate**: 20 Hz (0.05s) - default
2. **Backend**: LibreHardwareMonitor (Windows) o RAPL (Linux)
3. **Calibrazione idle**: Abilitata (3 finestre da 30s)

### Verifica sensori

Prima del benchmark:

```bash
python diagnostics.py
```

Output atteso:
```
[ OK ] CPU Package Power trovato: 15.2 W (idle)
[ OK ] Metodo: power-integration
```

Se "CPU Package Power" non è trovato:
- Verifica privilegi amministratore
- Riavvia come amministratore
- Controlla che LHM sia installato correttamente

## Esempio per la tesi

### Metodologia

> **Validazione incrociata con HWiNFO Sensors**
> 
> Per verificare l'accuratezza delle misure energetiche di CasualWatt, abbiamo condotto una validazione incrociata confrontando i risultati con HWiNFO Sensors (versione 8.20-5700), tool di diagnostica hardware ampiamente utilizzato nel settore.
> 
> **Configurazione sperimentale**:
> - Hardware: Intel Core i9-13900HK, 32 GB RAM, NVIDIA RTX 4060 Laptop
> - CasualWatt: backend LibreHardwareMonitor, polling 20 Hz, calibrazione idle 3x30s
> - HWiNFO: polling 10 Hz, logging CSV, sensore "CPU Package Power"
> - Benchmark: 10 query su modello llama3.1:8b, temperatura 0.7
> 
> **Procedura**:
> 1. Avvio HWiNFO logging (File → Logging Start)
> 2. Esecuzione benchmark CasualWatt
> 3. Arresto HWiNFO logging (File → Logging Stop)
> 4. Analisi comparativa con script `tools/validate_hwinfo.py`
> 
> **Risultati**:
> - Energia CasualWatt (LHM): 285.42 J
> - Energia HWiNFO: 278.91 J
> - Differenza assoluta: 6.51 J
> - Differenza relativa: 2.33%
> 
> La differenza < 5% conferma l'accuratezza delle misure di CasualWatt e la correttezza dell'implementazione LibreHardwareMonitor.

### Tabella comparativa

| Tool | Sorgente | Energia [J] | Differenza [%] |
|---|---|---|---|
| CasualWatt | LHM (firmware) | 285.42 | - |
| HWiNFO | SMBus/EC (vendor) | 278.91 | - |
| **Differenza** | - | 6.51 | **2.33%** |

## Troubleshooting

### "Colonna 'CPU Package Power' non trovata"

**Causa**: Il nome della colonna in HWiNFO è diverso.

**Soluzione**:
1. Apri il CSV HWiNFO con un editor di testo
2. Cerca la riga di header
3. Identifica il nome esatto della colonna di potenza CPU
4. Usa `--power-column "Nome Esatto"`

Esempio:
```bash
python tools/validate_hwinfo.py \
    --casualwatt results.csv \
    --hwinfo hwinfo.csv \
    --power-column "CPU PPT"
```

### "Differenza > 10%"

**Causa**: Discrepanza significativa tra le misure.

**Soluzione**:
1. Verifica che entrambi i tool leggano lo stesso sensore
2. Controlla che non ci fossero attività di sistema durante il benchmark
3. Ripeti la misura in condizioni controllate
4. Verifica polling rate (dovrebbe essere simile)

### "NumPy non disponibile"

**Causa**: NumPy non installato.

**Soluzione**:
```bash
pip install numpy
```

Lo script funziona anche senza NumPy (calcolo meno efficiente).

### "Matplotlib non disponibile"

**Causa**: Matplotlib non installato.

**Soluzione**:
```bash
pip install matplotlib
```

Il grafico è opzionale, lo script funziona senza.

## Limitazioni

1. **HWiNFO è closed-source**: Non puoi modificare il codice
2. **Logging manuale**: Devi avviare/fermare il logging a mano
3. **Allineamento temporale**: I timestamp potrebbero non essere perfettamente sincronizzati
4. **Sensori diversi**: LHM e HWiNFO potrebbero leggere sorgenti leggermente diverse
5. **Solo Windows**: HWiNFO non gira su Linux (per validazione cross-platform)

## Conclusioni

Questo strumento fornisce:
- ✓ Validazione indipendente delle misure CasualWatt
- ✓ Dati quantitativi per la tesi
- ✓ Diagnostica di problemi di configurazione
- ✓ Confronto con tool di riferimento del settore

**Utilizzalo sempre prima di presentare risultati scientifici.**

## Riferimenti

- HWiNFO: https://www.hwinfo.com/
- LibreHardwareMonitor: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor
- Intel RAPL: Intel SDM Vol. 3, Cap. 14.9 "Running Average Power Limit"
