# Relazione Tecnica — `consumi_ollama.py`

**Framework Python per il monitoraggio del consumo energetico delle sessioni locali di Ollama su Windows 11**

| Voce | Dettaglio |
|---|---|
| Progetto | `consumi_ollama.py` |
| Tipologia | Tool di sistema monolitico (singolo file) |
| Rigo | ~720 righe / 28 KB |
| Target OS | Windows 11 (compatibilità retroattiva Win 10; eseguibile anche su Linux/macOS in modalità degradata) |
| Linguaggio | Python 3.9+ (tipizzazione `typing` completa) |
| Data verifica | 15/10/2026 |

---

## 1. Obiettivo e scope

Il software misura **in tempo reale la potenza istantanea (W)** e l'**energia accumulata (kWh)** generate dalle sessioni inference di Ollama, identificando i processi `ollama_llama_server.exe` / `ollama.exe` e attribuendo il carico alle risorse hardware (CPU, iGPU, dGPU) disponibili sulla macchina ospite.

Requisito vincolante di progetto: **robustezza universale**. Il tool non deve mai crashare in assenza di sensori hardware, librerie opzionali o privilegi: ogni sorgente dati è facoltativa e inserita in una catena di fallback.

Fuori scope (dichiarato): misurazione al muro (power meter fisico), consumo del solo adapter di alimentazione, attribution energy dei componenti non accessibili via API OS (RAM, SSD, fan).

---

## 2. Architettura

Struttura a funzioni/classi ben separate, senza side-effect all'import (pattern `if __name__ == "__main__"`):

```
CONFIG MANUALE (CPU_TDP_OVERRIDE, INTERVALLO, NOMI_PROCESSI_OLLAMA)
        │
        ▼
┌───────────────────────┐   ┌──────────────────────────┐
│ trova_processi_ollama │──▶│ cpu_percent_ollama       │  (psutil)
└───────────────────────┘   └──────────────────────────┘
        │
┌───────▼────────┐  ┌──────────────────┐  ┌───────────────────────┐
│ nome_cpu()     │  │ tdp_da_modello() │  │ rileva_gpu_nvidia()   │
│ registro/wmic  │  │ TDP_TABLE +      │  │ pynvml → Scenario A   │
│ platform       │  │ euristica        │  └───────────────────────┘
└────────────────┘  └──────────────────┘  ┌───────────────────────┐
                                          │ MonitorGPUIntegrata   │
                                          │ WMI/typeperf → Scen.B │
                                          └───────────────────────┘
                    tutti ▼
              ┌─────────────────────┐
              │ StimaConsumo        │  selezione scenario A/B/C
              │  .campione() → Watt │  accumulo kWh
              └─────────────────────┘
                    │           │
             costruisci_dashboard │ scrivi_csv
                  (rich)          (csv, utf-8-sig)
                    │
                  main()  ← loop 2 s, KeyboardInterrupt-safe
```

### Moduli principali

| Componente | Righe ca. | Responsabilità |
|---|---|---|
| Sezione config/constants | 42–88 | Override manuale TDP, nomi processo, intervallo default |
| `trova_processi_ollama` / `cpu_percent_ollama` | 94–141 | Scoperta processi e CPU% aggregata normalizzata per core logici |
| `nome_cpu` / `tdp_da_modello` | 144–201 | Identificazione CPU (registro HKLM → wmic → platform) e stima TDP |
| `rileva_gpu_nvidia` / `power_draw_nvidia` / `gpu_util_nvidia` | 204–240 | Scenario A: NVML real power draw |
| `nomi_gpu_windows` / `ha_gpu_integrata` | 243–285 | Enumerazione GPU via WMI/PnP per decision tree |
| `MonitorGPUIntegrata` | 288–399 | Scenario B: 3 livelli di degradazione contatori perf |
| `LetturaCampionamento` (dataclass) | 402–411 | Record cronologico (timestamp, scenario, %, W, kWh, note) |
| `StimaConsumo` | 414–504 | Orchestratore: seleziona scenario, calcola watt, integra kWh |
| `costruisci_dashboard` / `console_fallback` | 507–572 | UI live `rich` con fallback testuale |
| `scrivi_csv` + `CAMPI_CSV` | 575–594 | Persistenza storica |
| `parse_args` / `main` | 597–720 | CLI, loop di campionamento, shutdown sicuro |

---

## 3. Logica di rilevamento e calcolo

### 3.1 Selezione dello scenario (decision tree)

All'inizializzazione, `StimaConsumo` tenta nell'ordine:

1. **Scenario A — NVIDIA dedicata**: import protetto di `pynvml` (con soppressione della FutureWarning), `nvmlInit()` e enumerazione device. Successo → lettura **Power Draw reale** via `nvmlDeviceGetPowerUsage()` (mW → W). Se il device espone solo l'utilization (es. alcuni laptop in hybrid mode), si degrada a stima da util% × budget TGP.
2. **Scenario B — iGPU Intel Iris Xe / AMD Radeon**: nessuna NVIDIA trovata ma GPU integrata presente nella lista WMI. Attivato `MonitorGPUIntegrata`.
3. **Scenario C — Fallback totale**: nessuna sorgente GPU isolabile; tutto il carico inference viene attribuito al pacchetto CPU rapportato al TDP.

Ogni passaggio è racchiuso in `try/except Exception`: un fallimento a livello N sposta silenziosamente al livello N+1 e la nota comparirà nella colonna `note` del CSV e nella dashboard.

### 3.2 Scenario B — degradazione a tre livelli

| Livello | Sorgente | Note |
|---|---|---|
| B1 | Modulo `wmi` → `Win32_PerfFormattedData_Counters_GPUEngine` | Preferito, nessun subprocess |
| B2 | `typeperf "\GPU Engine(*)\Utilization Percentage"` via subprocess, output parseato, cache TTL anti-lag | Funziona anche senza pywin32 |
| B3 | Proxy `\Processor Information(_Total)\% Processor Utility` combinato col delta CPU psutil, budget termico iGPU = 20 W | Ultimo tentativo prima di C |

### 3.3 Modello matematico CPU (Scenari B/C)

Curva cubica non lineare che approssima la legge dinamica di potenza CMOS (P ∝ f·V², con V che cresce super-linearmente con il carico):

```
P_cpu(u) = P_idle + (PL2 − P_idle) · u³
P_idle = 0.10 × TDP          (floor termico a idle)
PL2    = 1.40 × TDP          (picco power-limit 2 a u ≈ 100%)
u      = CPU% di Ollama / 100 / n_core_logici_norm
```

La componente percentuale è ottenuta sommando `proc.cpu_percent()` sui processi Ollama e normalizzando per il numero di core logici (`os.cpu_count()`), così da evitare artefatti multi-core.

Esempio (i9-13900HK, TDP 45 W → PL2 63 W): a u=0.5 → ≈16.6 W; a u=1.0 → 63 W.

### 3.4 Integrazione dell'energia

Ad ogni campione: `kWh += W_totale × Δt / 3 600 000` (Δt in ms, W→kW). L'accumulatore è monotono e sopravvive ai cambi di scenario.

### 3.5 Gestione del TDP — priorità di risoluzione

1. CLI `--tdp <watt>`
2. Variabile d'ambiente / file `.env` → `CPU_TDP=` (caricata con `python-dotenv`, import opzionale)
3. Costante `CPU_TDP_OVERRIDE` in testa allo script
4. Auto-rilevamento: lookup in `TDP_TABLE` (copre es. i9-13900HK→45 W, desktop K→125 W, Ryzen HS/U→35 W) con euristica finale marca/suffisso (H/HX→45, U→15, G→65 default)

---

## 4. Interfaccia e persistenza

- **Dashboard live (`rich`)**: layout a due pannelli — anagrafica hardware (CPU, GPU, scenario attivo, TDP usato, sorgente TDP) e metriche correnti (W istantanei con barra color-codificata, split CPU/GPU, kWh accumulati, durata sessione, costo €/kWh configurabile). In caso di terminale non compatibile, `console_fallback()` emette righe di testo plain: la misurazione non si ferma mai per colpa della UI.
- **CSV `consumi_ollama.csv`**: scritto nel `finally` del loop principale (quindi anche su CTRL+C, eccezioni e `sys.exit`). Delimitatore `;` ed encoding `utf-8-sig` per apertura diretta in Excel IT. Colonne: `timestamp;scenario;cpu_pct;gpu_pct;watt_cpu;watt_gpu;watt_totale;kwh_totali;note`. Se anche la scrittura primaria fallisce, è previsto un file di recovery.

---

## 5. Dipendenze

```bash
pip install psutil rich python-dotenv pynvml wmi pywin32
```

| Libreria | Ruolo | Obbligatoria? |
|---|---|---|
| `psutil` | Processi Ollama, CPU% | **Sì** |
| `rich` | Dashboard live | No (fallback plain text) |
| `python-dotenv` | Lettura `.env` (CPU_TDP) | No (usa comunque `os.environ`) |
| `pynvml` | Scenario A (NVML) | No (solo macchine NVIDIA) |
| `wmi` + `pywin32` | Scenario B livello B1 | No (solo Windows; B2/B3 coprono l'assenza) |

Tutti gli import opzionali avvengono dentro blocchi `try/except ImportError` con flag di disponibilità, mai a livello di modulo globale non protetto.

---

## 6. Hardening e gestione errori

- Nessun accesso hardware privo di guard: registry (`winreg`), WMI, NVML, `subprocess` (typeperf/wmic) sono ciascuno in `try/except` con ritorno `None`/default.
- `psutil` gestisce `NoSuchProcess`, `AccessDenied`, `ZombieProcess` (processi Ollama che muoiono/riaprono durante l'inference).
- `main()` intercetta `KeyboardInterrupt` per shutdown pulito e `Exception` in fase di inizializzazione hardware → forzato scenario C con messaggio `[ERRORE critico hardware, fallback scenario C]`.
- Timeout su ogni `subprocess.run` (evita hang di typeperf/wmic).
- Parse difensivo degli output typeperf (righe vuote, `NO DATA`, `,` come separatore decimale IT).
- Il tool resta eseguibile fuori da Windows (IS_WINDOWS flag): su Linux disabilita WMI/NVML e opera in scenario C — usato per i test.

---

## 7. Verifica effettuata

| Test | Esito |
|---|---|
| `python -m py_compile consumi_ollama.py` | ✅ OK, nessun warning |
| `--help` / parsing argparse (`--tdp`, `--intervallo`, `--output`) | ✅ OK |
| Avvio reale senza Ollama in esecuzione, senza NVML/WMI (ambiente container Linux) | ✅ Parte in scenario C, nessuna eccezione |
| Loop di campionamento 2 s + rendering dashboard/fallback | ✅ OK |
| Interruzione SIGINT (equivalente CTRL+C) | ✅ Shutdown pulito |
| Produzione `consumi_ollama.csv` | ✅ Header + N campioni cronologici, colonne complete |

Limite dichiarato della verifica: i rami Scenario A (NVML) e B1/B2 (WMI/typeperf) non sono esercitabili su host non-Windows/non-NVIDIA; la loro correttezza si fonda su API documentate e sulla catena di fallback che li rende comunque non bloccanti.

---

## 8. Uso operativo

```bash
# installazione
pip install psutil rich python-dotenv pynvml wmi pywin32

# avvio tipico (Windows 11, PowerShell)
python consumi_ollama.py

# TDP manuale 65 W, campionamento 1 s, export custom
python consumi_ollama.py --tdp 65 --intervallo 1 --output run_sessione.csv

# oppure via file .env nella stessa cartella
echo "CPU_TDP=45" > .env && python consumi_ollama.py
```

CTRL+C termina la sessione e salva automaticamente il CSV.

---

## 9. Limiti noti e sviluppi futuri

**Limiti:**
- I valori in scenario B/C sono **stime modellistiche**, non misure elettriche; l'accuratezza attesa è indicativamente ±20–35% rispetto a un power meter al muro. Lo scenario A (NVML) è invece una misura di telemetria on-die affidabile.
- Non distingue il contributo della VRAM né dei componenti di piattaforma (mobo, PSU loss factor).
- Il fattore PL2=1.4×TDP è un compromesso statistico sulle famiglie mobile moderne.

**Roadmap suggerita:**
1. Modalità `--calibra`: regressione lineare tra stime interne e letture di un UPS/KWH-meter esterno per tarare le curve su quella specifica macchina.
2. Integrazione `WHEA`/`Intel RAPL` via driver reader per package power reale anche su CPU non-NVIDIA.
3. Export JSONL + grafico storico finale (`rich.plotly` o matplotlib statico).
4. Servizio Windows (NSSM/sc) per logging continuativo multi-sessione con rotazione CSV.
5. Detection del modello caricato in Ollama (query API `localhost:11434/api/ps`) per associare i kWh al singolo modello.

---

## 10. Conclusioni

Il framework soddisfa integralmente la specifica: identificazione processo, triplo scenario GPU con degradazione automatica, gestione TDP a quattro livelli di priorità, campionamento 2 s con integrazione kWh, dashboard `rich` e chiusura sicura con persistenza CSV. La scelta monofile ne agevola distribuzione e manutenzione su macchine eterogenee; la strategia *graceful degradation by design* garantisce che il tool non fallisca mai in modo duro, riducendo sempre il problema allo scenario stimativo disponibile.
