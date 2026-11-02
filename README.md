# CasualWatt Energy Benchmark

CasualWatt è un framework di benchmark energetico per LLM locali (Ollama) e cloud, con interfaccia grafica Tkinter. Misura l'energia del package CPU tramite contatori hardware e riporta separatamente le componenti `local`, `network` e `cloud`, con metodo e confine di misura espliciti in ogni riga CSV.

Su **Windows 11** la catena del package CPU è:

```text
CW_ENERGY_FILE (override esplicito)
    -> emi-counter
    -> pawnio-counter
    -> unavailable
```

`emi-counter` legge il contatore cumulativo EMI del processore Intel tramite `ctypes` e funziona a privilegi standard. `pawnio-counter` è il fallback dichiarato che legge lo stesso registro MSR del package tramite PawnIO: richiede un processo elevato e non viene sommato a EMI. Se nessuna sorgente risponde, l'energia è `unavailable`, non zero. Su Linux il backend attivo è RAPL (`/sys/class/powercap`). LibreHardwareMonitor è fuori dal percorso di produzione dal 27/10/2026; resta soltanto per harness e risultati storici.

La GPU viene selezionata per vendor, senza eseguire due catene in parallelo: NVIDIA usa NVML (`nvml-energy` oppure `nvml-power-integral`), AMD usa AMD SMI (`amdsmi-energy` oppure `amdsmi-power-integral`). L'energia attribuita a Ollama è una stima ottenuta dalla misura della scheda, dalla baseline idle e dalla quota temporale del processo; non è una lettura diretta dell'energia del singolo processo.

Target principale: **Windows 11**, Python **3.11+** (testato su Python 3.14 x64). L'applicazione funziona normalmente senza elevazione quando EMI è disponibile; il solo fallback PawnIO richiede elevazione.

**Qual è il documento che serve.** Il metodo vigente, con le decisioni congelate P1-P4 e il formulario F.0-F.17, è in `experiment_results/protocollo_v4_20261024.md`; le regole vincolanti per chi lavora nel repository sono in `AGENTS.md`. `RELAZIONE.md` **non** è la relazione di questo framework: è la verifica del 15/10/2026 del tool monofile legacy `consumi_ollama.py`, che stima la potenza dal TDP e sta fuori dal percorso di misura (`AGENTS.md:135-136`, `AGENTS.md:318-320`).

## Caratteristiche

- GUI a 3 pannelli: selezione modelli (locali/cloud), esecuzione benchmark, risultati + grafici; sezioni Log e Risultati ridimensionabili (PanedWindow).
- Lettura dinamica dei modelli Ollama (`GET /api/tags`) e cloud (Groq, OpenRouter, Google Gemini, OpenAI, Anthropic) con badge `[Gratuito]`.
- Configurazione chiavi API dalla GUI (combobox provider, campi oscurati, persistenza in `.casualwatt_keys.json`).
- Calibrazione idle empirica (mediana di 3 finestre di almeno 30 s).
- Sorgente test universale: dataset CSV esterno (con ground truth opzionale) o prompt manuali a blocchi dinamici.
- Valutazione: similarità semantica (sentence-transformers multilingue) vs ground truth, estrazione triple causali con F1, LLM-as-a-Judge via Ollama; regime senza GT etichettato esplicitamente.
- Export CSV dettagliato: energia, token, latenza, emissioni CO2, metodo, provenienza dei token e boundary di misura per riga.
- Energia package, attiva e GPU attribuita con segno conservato: gli incrementi negativi non vengono troncati a zero.
- Le metriche per token non vengono calcolate quando i token sono stimati; il CSV registra `token_provenance` (`native`, `estimated`, `missing`).

## Installazione (Windows 11)

```powershell
py -m pip install -r cwEnergyModular/requirements.txt        # nucleo dell'applicazione
```

Per gli harness storici che rigenerano artefatti basati su LibreHardwareMonitor:

```powershell
py -m pip install -r cwEnergyModular/requirements-lhm.txt    # non serve all'app
```

`requirements.txt` include le dipendenze opzionali per NVML e la stima energetica cloud. Il backend AMD SMI usa il modulo `amdsmi` quando è disponibile sulla macchina; il percorso EMI usa `ctypes` dalla libreria standard. PawnIO richiede il modulo e il driver verificati dal backend, oltre a un processo elevato. `requirements-lhm.txt` non è necessario per l'applicazione e non riattiva LibreHardwareMonitor nel percorso di produzione.

`wmi`, `pywin32` e `codecarbon` non fanno parte del percorso di misura di `cwEnergyModular`; gli eventuali harness o script legacy che li usano sono separati e non producono misure CasualWatt correnti.

Le DLL di LibreHardwareMonitor (`LibreHardwareMonitorLib.dll`, `HidSharp.dll`, `Microsoft.Win32.TaskScheduler.dll`) restano archiviate in `cwEnergyModular/LibreHardwareMonitorLib/LibreHardwareMonitor/` per quegli harness storici: non fanno parte del percorso di misura. `LibreHardwareMonitorLib.dll` è distribuita senza modifiche sotto **MPL-2.0**: il testo integrale della licenza è allegato in `cwEnergyModular/LibreHardwareMonitorLib/LibreHardwareMonitor/MPL-2.0.txt` ( preso da mozilla.org, verificato il 23/10 sul `LICENSE` upstream), con gli avvisi third-party in `THIRD-PARTY-NOTICES.md` nella stessa cartella; per `HidSharp.dll` e `Microsoft.Win32.TaskScheduler.dll` la licenza va ri-verificata presso i rispettivi upstream prima di qualsiasi ridistribuzione.

## Avvio

Con doppio clic su `cwEnergyModular/avvia_casualwatt.bat` (nessuna elevazione: il launcher non chiede UAC), oppure manualmente:

```powershell
cd cwEnergyModular
py main.py            # GUI (senza amministratore)
py diagnostics.py     # report del canale EMI/PawnIO/RAPL e sonda PMI/WMI
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
| `CW_JUDGE_MODEL` | modello Ollama per LLM Judge |

## Struttura

```
cwEnergyModular/
├── main.py                 # entry point GUI / CLI
├── benchmark_unified.py    # orchestrazione benchmark
├── evaluator.py            # valutazione (GT semantica, triple causali, judge)
├── cloud_estimator.py      # fetch modelli + stima EcoLogits
├── casualwatt_csv_export.py # export CSV
├── gui/                    # pannelli Tkinter
└── energy/                 # sessioni energetiche CPU/GPU/rete/carbonio
```

## Metodologia energetica

```
E_attiva = E_package − P_idle·Δt                  [segno conservato; la baseline non viene attribuita]
E_Ollama = E_attiva · Δt_cpu_Ollama / Δt_cpu_busy [attribuzione per quota temporale CPU]
E_GPU,Ollama = E_board − P_GPU,idle·Δt           [segno conservato; quota processo dichiarata]
end_to_end = local + network + cloud              [componenti separate nel CSV]
```

`baseline_energy_j` è salvata separatamente e non viene attribuita al modello. Un'energia attiva negativa resta nel dataset ma non viene usata per l'attribuzione CPU. L'energia della chiamata LLM Judge è contabilmente separata (`judge_energy_j`).

I token sono classificati come `native`, `estimated` o `missing`. Il runner v4 non inventa token mancanti; il runner storico può usare una stima, ma in quel caso non pubblica metriche `J/token`, `token/J` o equivalenti.

## Note

- Su Linux la misurazione locale usa il contatore RAPL (`/sys/class/powercap`); su macOS è disabilitata con messaggio esplicito (future work). GUI, Ollama, cloud, valutazioni e CSV restano utilizzabili ovunque.
- I backend GPU NVIDIA/AMD e il backend RAPL hanno test sintetici; la verifica su hardware GPU reale e la validazione della scala assoluta con un wattmetro esterno sono ancora da eseguire.
- L'attribuzione CPU/GPU è una procedura per quota temporale, non una misura diretta dell'energia del processo. La parola `validated` è riservata alle righe che superano l'intera catena di validazione prevista dal protocollo v4.
- Il metodo vigente e le decisioni congelate P1-P4 sono in `experiment_results/protocollo_v4_20261024.md`. I risultati archiviati in `experiment_results/` possono contenere canali storici non più prodotti dal percorso corrente.
- Progetto di ricerca (tesi): metriche, provenienza e confini di misura sono dichiarati riga per riga nel CSV.
