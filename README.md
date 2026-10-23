# CasualWatt Energy Benchmark

Framework di benchmark energetico per LLM locali (Ollama) e cloud, con interfaccia grafica Tkinter. Misura l'energia del package CPU dal contatore cumulativo EMI del processore Intel (metodo principale su Windows, `emi-counter`: ioctl via ctypes, nessuna integrazione, nessuna elevazione), con LibreHardwareMonitor come fallback (`power-integration`) e RAPL su Linux; misura la GPU NVIDIA via NVML, stima l'energia incrementale attribuibile al processo Ollama (baseline idle calibrata + ripartizione del tempo CPU busy), l'energia di rete dal traffico NIC e l'energia dell'inferenza cloud tramite EcoLogits. Le componenti sono riportate separatamente (local / network / cloud), con metodo e confine di misura espliciti in ogni riga CSV.

Target principale: **Windows 11**, Python 3.14 x64. Con il canale EMI attivo l'app gira **senza privilegi amministrativi**; l'elevazione (UAC) serve solo al fallback LibreHardwareMonitor e ad alcuni sensori.

## Caratteristiche

- GUI a 3 pannelli: selezione modelli (locali/cloud), esecuzione benchmark, risultati + grafici; sezioni Log e Risultati ridimensionabili (PanedWindow).
- Lettura dinamica dei modelli Ollama (`GET /api/tags`) e cloud (Groq, OpenRouter, Google Gemini, OpenAI, Anthropic) con badge `[Gratuito]`.
- Configurazione chiavi API dalla GUI (combobox provider, campi oscurati, persistenza in `.casualwatt_keys.json`).
- Calibrazione idle empirica (mediana di 3 finestre >=30 s sul sensore `CPU Package`).
- Sorgente test universale: dataset CSV esterno (con ground truth opzionale) o prompt manuali a blocchi dinamici.
- Valutazione: similarità semantica (sentence-transformers multilingue) vs ground truth, estrazione triple causali con F1, LLM-as-a-Judge via Ollama; regime senza GT etichettato esplicitamente.
- Export CSV dettagliato (~100 colonne): energia, token, latenza, emissioni CO2, metodo e boundary di misura per riga.

## Installazione (Windows 11)

```powershell
py -m pip install requests pandas psutil codecarbon ecologits nvidia-ml-py pythonnet sentence-transformers
```

Le DLL di fallback LibreHardwareMonitor (`LibreHardwareMonitorLib.dll`, `HidSharp.dll`, `Microsoft.Win32.TaskScheduler.dll`) sono incluse in `cwEnergyModular/LibreHardwareMonitorLib/LibreHardwareMonitor/`. `LibreHardwareMonitorLib.dll` è distribuita senza modifiche sotto **MPL-2.0** (testo: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/blob/master/LICENSE, verificato il 23/10); per `HidSharp.dll` e `Microsoft.Win32.TaskScheduler.dll` la licenza va ri-verificata presso i rispettivi upstream prima di qualsiasi ridistribuzione.

## Avvio

Con doppio clic su `cwEnergyModular/avvia_casualwatt.bat` (richiede i privilegi UAC: necessario solo per il fallback LibreHardwareMonitor; con il canale EMI l'app parte anche senza elevazione), oppure manualmente:

```powershell
cd cwEnergyModular
py main.py            # GUI (con canale EMI attivo, senza amministratore)
py diagnostics.py     # report sensori/clr/UAC
py test_calibrazione.py  # verifica rapida calibrazione idle
py main.py --selftest    # test logici senza hardware
```

## Variabili d'ambiente / .env

| Variabile | Descrizione |
|---|---|
| `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | chiavi provider cloud |
| `ELECTRICITY_MAPS_API_TOKEN` | intensità carbonio live |
| `OLLAMA_HOST` | default `http://localhost:11434` |
| `CW_SEMANTIC_THRESHOLD` | soglia is_correct (default 0.75) |
| `CW_EMBED_MODEL_DIR` | cache offline modello embeddings |
| `CW_IDLE_WINDOW_S` | finestra calibrazione idle |
| `CW_PRIMARY_CHANNEL` | `emi` (default, contatore cumulativo) o `lhm` ( catena LibreHardwareMonitor) |
| `CW_JUDGE_MODEL` | modello Ollama per LLM Judge |

## Struttura

```
cwEnergyModular/
├── main.py                 # entry point GUI / CLI
├── benchmark_unified.py    # orchestrazione benchmark
├── evaluator.py            # valutazione (GT semantica, triple causali, judge)
├── cloud_estimator.py      # fetch modelli + stima EcoLogits
├── casualwatt_csv_export.py# export CSV
├── gui/                    # pannelli Tkinter
└── energy/                 # sessioni energetiche (EMI/LHM/RAPL/NVML/rete/carbonio)
```

## Metodologia energetica

```
E_attiva = max(0, E_package − P_idle·Δt)          [Δ contatore cumulativo EMI, bordi dal buffer @0,05s; fallback LHM: integrazione trapezoidale]
E_Ollama = E_attiva · Δt_cpu_Ollama / Δt_cpu_busy [cpu-time-share attribution]
end_to_end = local + network + cloud              [baseline idle ESCLUSA]
```

La `baseline_energy_j` è salvata separatamente e non viene mai attribuita al modello. L'energia della chiamata LLM Judge è contabilmente separata (`judge_energy_j`).

## Note

- Su Linux la misurazione locale usa il contatore RAPL (`/sys/class/powercap`, backend implementato; validazione di scala ancora aperta); su macOS è disabilitata con messaggio esplicito (future work). GUI, Ollama, cloud, valutazioni e CSV restano utilizzabili ovunque.
- Progetto di ricerca (tesi): metriche e confini di misura sono dichiarati riga per riga nel CSV.
