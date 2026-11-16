# CasualWatt — Benchmark energetico per inferenza LLM locale

CasualWatt misura l'energia di una singola inferenza LLM locale su Windows,
leggendo il contatore energetico del package CPU. Ogni riga CSV dichiara metodo,
provenienza e confine di misura; l'accuratezza della risposta viene valutata
accanto all'energia, producendo **ECPC** (Energy Per Correct Prediction) come
metrica ibrida energia-accuratezza.

Su **Windows 11** la catena del package CPU è:

```text
CW_ENERGY_FILE (override esplicito)
    -> emi-counter
    -> pawnio-counter
    -> unavailable
```

`emi-counter` legge il contatore cumulativo EMI del processore Intel tramite
`ctypes` e funziona a privilegi standard. `pawnio-counter` è il fallback
dichiarato che legge lo stesso registro MSR del package tramite PawnIO: richiede
un processo elevato e non viene sommato a EMI. Se nessuna sorgente risponde,
l'energia è `unavailable`, non zero. Su Linux il backend attivo è RAPL
(`/sys/class/powercap`). LibreHardwareMonitor è fuori dal percorso di produzione
dal 27/10/2026; resta soltanto per harness e risultati storici.

La GPU viene selezionata per vendor: NVIDIA usa NVML (`nvml-energy` oppure
`nvml-power-integral`), AMD usa AMD SMI (`amdsmi-energy` oppure
`amdsmi-power-integral`). L'energia attribuita a Ollama è una stima ottenuta
dalla misura della scheda, dalla baseline idle e dalla quota temporale del
processo; non è una lettura diretta dell'energia del singolo processo.

Target principale: **Windows 11**, Python **3.11+** (testato su Python 3.14 x64).
L'applicazione funziona normalmente senza elevazione quando EMI è disponibile;
il solo fallback PawnIO richiede elevazione.

**Documenti di riferimento.** Il metodo vigente, con le decisioni congelate P1-P5
e il formulario F.0-F.17, è in `experiment_results/protocollo_v4_20261024.md`;
le regole vincolanti per chi lavora nel repository sono in `AGENTS.md`.
`RELAZIONE.md` **non** è la relazione di questo framework: è la verifica del
15/10/2026 del tool monofile legacy `consumi_ollama.py`, che stima la potenza
dal TDP e sta fuori dal percorso di misura.

## Caratteristiche

- **Runner v4** (`benchmark_v4.py`): sequenza di blocco di protocollo P1.5 con calibrazione idle, settling, warm-up a criterio misurato e gate P4.4 (controllo load-versus-control).
- **Metriche ibride energia-accuratezza**: ECPC (Energy Per Correct Prediction) e EPCL (Energy Per Causal Link) calcolati sul denominatore binario `is_correct` con regola di binarizzazione dichiarata per tipo di risposta.
- **Valutazione multi-criterio**: valutatore primario (`evaluator.py`) con 6 tipi di risposta (number, short_text, free_text, interval, label, structured) e valutatore robusto secondario (`robust_evaluator.py`) con probabilità condizionate a tutti gli stadi.
- **Schema CSV a 174 colonne**: ogni riga dichiara metodo, provenienza, confine di misura e flag di validità energeticamente. I metadati del run (30 colonne) completano l'header.
- **GUI Tkinter** a 3 pannelli: selezione modelli (locali/cloud), esecuzione benchmark, risultati + grafici; sezioni Log e Risultati ridimensionabili.
- **Calibrazione idle empirica**: mediana di 3 finestre di almeno 30 s, con baseline separata per CPU e GPU.
- **Energia con segno conservato**: gli incrementi negativi non vengono troncati a zero; un registro fermo ai bordi invalida la finestra (`counter-invalid`), non la pone a zero.
- **Task definition YAML** (`task_definition.py`): definizione dichiarativa dei task di benchmark, ispirata a lm-evaluation-harness, senza dipendenza dal repository.
- **Multi-prompt** (`multi_prompt.py`): esecuzione dello stesso task con N prompt diversi e aggregazione dell'energia con sensibilità al prompt (deviazione standard, Coefficient of Variation, Max/Min ratio).
- **Moduli di analisi**: `surface_fit.py` (risolutore QR/SVD della superficie predittiva, P6.5), `geometry.py` (copertura geometrica dell'inviluppo, F.13), `s_epi_phase.py` (finestra di fase e tempi di assestamento), `control_gate.py` (criterio F.12 del gate P4.4).
- **Suite di test**: 1582+ node id (pytest), copertura docstring dichiarata, Appendice D rigenerata automaticamente.

## Installazione (Windows 11)

```powershell
py -m pip install -r cwEnergyModular/requirements.txt        # nucleo dell'applicazione
```

Per gli harness storici che rigenerano artefatti basati su LibreHardwareMonitor:

```powershell
py -m pip install -r cwEnergyModular/requirements-lhm.txt    # non serve all'app
```

`requirements.txt` include le dipendenze opzionali per NVML e la stima energetica cloud. Il backend AMD SMI usa il modulo `amdsmi` quando è disponibile sulla macchina; il percorso EMI usa `ctypes` dalla libreria standard. PawnIO richiede il modulo e il driver verificati dal backend, oltre a un processo elevato. `requirements-lhm.txt` non è necessario per l'applicazione e non riattiva LibreHardwareMonitor nel percorso di produzione.

Le DLL di LibreHardwareMonitor restano archiviate per gli harness storici: non fanno parte del percorso di misura. `LibreHardwareMonitorLib.dll` è distribuita senza modifiche sotto **MPL-2.0**.

## Avvio

```powershell
cd cwEnergyModular
py main.py                    # GUI Tkinter (senza amministratore)
py benchmark_v4.py --help     # runner v4 CLI (protocollo P1.5)
py diagnostics.py             # report del canale EMI/PawnIO/RAPL e sonda PMI/WMI
```

### Verifica

```powershell
pytest cwEnergyModular -q     # suite completa (1582+ node id)
python tools/smoke_keep_alive.py --model qwen2.5:0.5b   # controllo pre-campagna sul motore
```

**Mai `pytest` nudo dalla radice**: la raccolta viene interrotta da errori in `cpuepower/` e `cpuepower2/` (moduli sottoposti ad audit, non backend di produzione).

## Variabili d'ambiente

| Variabile | Descrizione |
|---|---|
| `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `GOOGLE_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | chiavi provider cloud |
| `ELECTRICITY_MAPS_API_TOKEN` | intensità carbonio live |
| `OLLAMA_HOST` | default `http://localhost:11434` |
| `CW_SEMANTIC_THRESHOLD` | soglia `is_correct` per free_text (default 0.75) |
| `CW_EMBED_MODEL_DIR` | cache offline modello embeddings |
| `CW_IDLE_WINDOW_S` | finestra calibrazione idle (default 30 s) |
| `CW_JUDGE_MODEL` | modello Ollama per LLM Judge |
| `CW_ENERGY_FILE` | override energia (DEV/TEST, precedenza su tutto) |
| `CW_GPU_INDEX` | indice della scheda GPU (0-based, per backend) |

## Struttura del modulo

```
cwEnergyModular/
├── main.py                     # entry point GUI / CLI
├── benchmark_v4.py             # runner v4 (protocollo P1.5, blocchi di misura)
├── benchmark_unified.py        # runner storico (v1-v3, legacy)
├── evaluator.py                # valutazione primaria (6 tipi di risposta)
├── robust_evaluator.py         # valutazione robusta secondaria
├── evaluation_runner.py        # aggregati, Wilson CI, bootstrap a cluster, McNemar
├── evaluation_schema.py        # schema di valutazione, regola di binarizzazione
├── casualwatt_csv_export.py    # export CSV (174 colonne riga + 30 metadati)
├── machine_state.py            # stato macchina P1.4 (residenza, warm-up, top-5)
├── task_definition.py          # definizione dichiarativa dei task (YAML)
├── multi_prompt.py             # esecuzione multi-prompt e sensibilità energetica
├── cloud_estimator.py          # fetch modelli cloud + stima EcoLogits
├── config.py                   # configurazione e costanti di protocollo
├── taxonomy_ecpc.py            # tassonomia ECPC/EPCL
├── surface_fit.py              # analisi: risolutore QR/SVD superficie predittiva (P6.5)
├── geometry.py                 # analisi: copertura geometrica dell'inviluppo (F.13)
├── s_epi_phase.py              # analisi: finestra di fase e tempi di assestamento
├── control_gate.py             # analisi: criterio F.12 gate P4.4
├── gui/                        # pannelli Tkinter
├── energy/                     # sessioni energetiche CPU/GPU/rete/carbonio
├── tools/                      # generatori LaTeX, sonde, harness di analisi
└── tests/                      # suite di test (1500+ node id)
```

## Metodologia energetica

```
E_attiva = E_package − P_idle·Δt                  [segno conservato]
E_Ollama = E_attiva · Δt_cpu_Ollama / Δt_cpu_busy [quota temporale CPU]
E_GPU,Ollama = E_board − P_GPU,idle·Δt           [segno conservato]
ECPC = ΣE_attiva / Σis_correct                    [energia per previsione corretta]
```

`baseline_energy_j` è salvata separatamente e non viene attribuita al modello.
Un'energia attiva negativa resta nel dataset con il segno conservato.
L'energia della chiamata LLM Judge è contabilmente separata (`judge_energy_j`).

I token sono classificati come `native`, `estimated` o `missing`.
Il runner v4 non inventa token mancanti; le metriche per token non vengono
calcolate quando `token_provenance` non è `native`.

## Note

- Su Linux la misurazione locale usa il contatore RAPL (`/sys/class/powercap`);
  su macOS è disabilitata con messaggio esplicito. GUI, Ollama, cloud, valutazioni
  e CSV restano utilizzabili ovunque.
- I backend GPU NVIDIA/AMD e il backend RAPL hanno test sintetici; la verifica
  su hardware GPU reale e la validazione della scala assoluta con un wattmetro
  esterno sono ancora da eseguire.
- L'attribuzione CPU/GPU è una procedura per quota temporale, non una misura
  diretta dell'energia del processo. La parola `validated` è riservata alle righe
  che superano l'intera catena di validazione di P4.9.
- Il metodo vigente e le decisioni congelate P1-P5 sono in
  `experiment_results/protocollo_v4_20261024.md`. I risultati archiviati in
  `experiment_results/` possono contenere canali storici non più prodotti dal
  percorso corrente.
- `cpuepower/` e `cpuepower2/` sono toolkit sottoposti ad audit: i loro numeri
  erano mock, la CLI crasha, la mappa MSR era sbagliata. **Banca di esperimenti,
  non un backend di misura.** Non importarli, non citarli come risultato.
- Progetto di ricerca (tesi di laurea): metriche, provenienza e confini di misura
  sono dichiarati riga per riga nel CSV. La tesi LaTeX sta in `Tesi-latex/`
  (fuori da git).
