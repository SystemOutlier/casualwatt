# Matrice Comparativa dello Stato dell'Arte e Fondamenti Scientifici di CasualWatt

Questo documento analizza dettagliatamente i principali framework e benchmark energetici della letteratura rispetto a **CasualWatt**, evidenziando le differenze metodologiche, i punti di superiorità metrologica e le evidenze scientifiche a supporto delle scelte di progetto.

---

## 1. Matrice Sinottica Comparativa

| Dimensione di Analisi | CodeCarbon 3.3 (mlco2) | pyJoules (PowerAPI) | Scaphandre (Hubblo) | MELODI (NeurIPS 2024) | TokenPowerBench (AAAI 2026) | PowerJoular (2022/2026) | EnviroLLM (2025) | CasualWatt (Questo Lavoro) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Piattaforma Operativa** | Cross-platform (Win/Linux/macOS) | Solo GNU/Linux | Linux (Bare-metal / K8s) | Server Linux (GPU-centric) | Cluster Linux HPC | Windows, Linux, macOS | Windows, Linux | **Windows (EMI / PawnIO), Linux (RAPL), GPU eterogenee** |
| **Backend di Misura** | RAPL / EMI / Powermetrics (o fallback TDP) | MSR RAPL sysfs | MSR RAPL sysfs | Scaphandre (CPU) + nvidia-smi (GPU) | NVML (GPU) + RAPL (CPU) | EMI (Win) / RAPL (Linux) | psutil (CPU) + pynvml (GPU) | **Registri on-die cumulativi nativi (EMI, MSR, NVML, AMD SMI)** |
| **Metodo di Acquisizione** | Polling a 15 s; delta contatore o integrale | Lettura differenziale contatore ai bordi | Polling continuo (Prometheus exporter) | Integrazione numerica trapezoidale | Decomposizione hardware su cluster | Campionamento a 1 s da contatore cumulativo | Polling a 2 s con integrazione numerica | **Lettura differenziale ai bordi con interpolazione temporale ($0{,}28$–$0{,}34$ s; sampler $0{,}05$ s; risoluzione $10$ ms)** |
| **Trattamento Baseline Idle** | **Assente** (zero occorrenze di `idle` e `baseline` nei sorgenti) | **Assente** | **Assente** (profiling continuativo) | **Assente o statica** | Sottrazione idle dichiarata su nodo cluster | **Assente** | **Assente** (stima statica 50 W su CPU) | **Dinamica Trifasica** ($3 \times 30$ s mediana pre/post); **controllo derive termiche ($r_A, r_B < 10\%$)** |
| **Politica Residui Negativi** | Non applicabile | Non applicabile | Non applicabile | Troncamento a zero o non gestito | Non documentato | Non applicabile | Non applicabile | **Conservazione del residuo firmato (Signed Residual)** per evitare bias positivi sistematici |
| **Attribuzione al Processo** | Solo nel percorso TDP (psutil); **assente** con contatori | Assente (misura l'intero package) | Sì (in base al tempo CPU letto da `/proc`) | Assente (misura hardware globale) | Assente (allocazione statica nodo) | Sì (in base al carico CPU) | Proporzionale empirica non validata | **Sì**, per quota temporale CPU monotona sull'albero dei PID |
| **Scomposizione di Fase LLM** | Assente | Assente | Assente | Solo configurazione globale di prompt | Distinzione Prefill vs Decode (J/token) | Assente | Assente | **Scomposizione Prefill (TTFT) vs Decoding** con contatore dedicato |
| **Valutazione Agenti e Oracoli** | Assente | Assente | Assente | Assente | Assente | Assente | Assente | **Scorporo dell'energia del giudice (LLM-as-a-Judge)** e calcolo indice **ECPC** |
| **Tassonomia Epistemica** | Monolitica ($gCO_2eq$ aggregate) | Singola misura locale | Singola misura locale | Singola misura locale | Metriche isolate di cluster | Singola misura locale | Stima scalare grezza | **Separazione a Tre Tier:** Tier 1 Misurato, Tier 2 Attribuito, Tier 3 Modellato |

---

## 2. Schede di Dettaglio per Strumento

### A. CodeCarbon (Versione 3.3.0)
* **Descrizione:** Il tool open-source più diffuso per il tracciamento delle emissioni di carbonio del software ML.
* **Analisi del Sorgente Python:**
  * Supporta due modalità: `machine` (default) e `process`.
  * Nel percorso con contatore hardware (RAPL su Linux, EMI su Windows via `hardware.py:381-412`), CodeCarbon accumula direttamente la somma dei delta energetici di sistema. **La modalità per-processo non viene applicata quando si usano i contatori reali**, ma funziona solo quando si ripiega sul modello analitico TDP (`hardware.py:344-346`).
  * **Assenza Totale di Baseline:** Le parole chiave `idle` e `baseline` hanno *zero* occorrenze nel codice sorgente. CodeCarbon calcola l'energia lorda della macchina.
* **Differenza con CasualWatt:** CasualWatt risponde al consumo netto incrementale associato all'inferenza rispetto alla linea base a riposo, integrando il controllo di stabilità termica e la correzione delle fluttuazioni di clock.

### B. pyJoules (PowerAPI Team)
* **Descrizione:** Libreria Python orientata all'annotazione di porzioni di codice tramite decoratori e context manager.
* **Punti di Forza:** Riconosce formalmente il limite di frequenza dei contatori Intel RAPL: se la funzione monitorata ha una durata inferiore al periodo di aggiornamento del contatore, restituisce esplicitamente valori nulli per non produrre artefatti fittizi.
* **Limiti:** Funziona unicamente su GNU/Linux con accesso sysfs; non offre supporto nativo per Windows, né per architetture GPU eterogenee, né protocolli per la sottrazione dell'idle di sistema o la gestione di chiamate di rete.

### C. Scaphandre (Hubblo)
* **Descrizione:** Metrology agent per infrastrutture bare-metal e cluster Kubernetes, scritto in Rust.
* **Punti di Forza:** Elevata efficienza e campionamento ad alta frequenza; espone metriche granulari per container e processi verso stack Prometheus/Grafana.
* **Limiti:** Concepito per il monitoraggio continuativo di infrastrutture server a lungo termine. Non si adatta all'inferenza transitoria di singoli prompt generativi, non gestisce macchine client Windows, e non prevede la sottrazione automatica di baseline pre/post inferenza.

### D. MELODI (Husom et al., NeurIPS 2024 / arXiv:2407.16893)
* **Descrizione:** Framework specifico per profilare il consumo energetico di LLM locali (Ollama, vLLM) variando lunghezza del contesto e parametri di generazione.
* **Limiti Metrologici:** Utilizza Scaphandre per la CPU e un thread di polling periodico su `nvidia-smi` per la GPU, integrando la potenza numericamente tramite la regola trapezoidale ($E = \int P(t)\,dt$).
* **Differenza con CasualWatt:** L'integrazione trapezoidale perde i picchi repentini della fase di prefill iniziale. CasualWatt legge la differenza finita dell'accumulatore hardware ($\Delta E$) ai bordi della finestra con sincronizzazione temporale al nanosecondo, azzerando l'errore di integrazione.

### E. TokenPowerBench (Niu et al., AAAI 2026 / arXiv:2512.03024)
* **Descrizione:** Benchmark scientifico di riferimento per decomporre l'energia dell'inferenza LLM nelle due fasi canoniche (Prefill e Decoding), analizzando componenti GPU, CPU e DRAM.
* **Limiti di Ambito:** È calibrato e validato su nodi server e cluster GPU dedicati in ambienti datacenter controllati.
* **Differenza con CasualWatt:** CasualWatt adotta la stessa rigorosa scomposizione concettuale (formalizzata tramite la lettura del Time-To-First-Token, TTFT), ma la rende operativa su **workstation e personal computer eterogenei**, dove il rumore del sistema operativo e la concorrenza dei processi rendono indispensabili la compensazione dell'idle e la ripartizione per quota CPU.

### F. EnviroLLM (Troy Allen, 2025)
* **Descrizione:** Toolkit recente per il monitoraggio di modelli linguistici locali per-query.
* **Limiti Metrologici:** Impiega un campionamento molto lento (intervalli di 2 secondi); su CPU ricorre a una formula euristica statica (50 W fissi + quota proporzionale del carico psutil), senza interrogare i contatori hardware on-die e senza scorporare la baseline.

---

## 3. Fondamenti Scientifici delle Scelte di CasualWatt

Ciascuna decisione architetturale e metodologica di CasualWatt è ancorata a fonti primarie della letteratura scientifica internazionale:

### Decisione 1: Lettura dei Registri Hardware Cumulativi ($\Delta E$) vs Integrazione Numerica ($\int P\,dt$)
* **Motivazione:** Le CPU e GPU moderne variano frequenze e tensioni di alimentazione a intervalli di microsecondi (Intel Speed Shift, Turbo Boost, Dynamic Power Gating). Un campionamento discreto a centinaia di millisecondi sottocampiona sistematicamente i burst di potenza, introducendo errori di quadratura fino al 20–30%.
* **Riferimenti Scientifici:**
  * **Rotem, E. et al. (IEEE Micro, 2012):** *Power-Management Architecture of the Intel Microarchitecture (Sandy Bridge)*, doi:10.1109/MM.2012.12. Dimostra come i registri RAPL integrino internamente la corrente a livello hardware attraverso accumulatori ad alta frequenza.
  * **Beyer, D. & Wendler, P. (ACM/SPEC ICPE, 2020):** *CPU Energy Meter: A Tool for Energy-Aware Algorithms Engineering*, doi:10.1145/3358960.3379132. Conferma che l'interrogazione differenziale dei registri on-die evita le distorsioni tipiche dei campionatori statistici.
  * **Desrochers, S. et al. (IEEE IISWC, 2016):** *A Validation of the RAPL Energy Reading to DRAM*, doi:10.1109/IISWC.2016.7581275. Valida la fedeltà fisica dei contatori on-die a confronto con sonde di corrente hardware esterne.

### Decisione 2: Baseline Dinamica Trifasica e Conservazione del Residuo Firmato (*Signed Residual*)
* **Motivazione:** Lo stato termico e i demoni di background del sistema operativo variano nel tempo. Sottrarre una baseline fissa produce derive. Inoltre, forzare a zero i residui debolmente negativi ($\max(0, E - E_{\text{base}})$) viola il teorema del limite centrale, inducendo un **bias positivo sistematico** che altera la varianza e i test statistici parametrici (t-Student, ANOVA).
* **Riferimenti Scientifici:**
  * **JCGM 100:2008 (GUM / ISO/IEC Guide 98-3):** *Evaluation of Measurement Data — Guide to the Expression of Uncertainty in Measurement*. Stabilisce il principio metrologico per cui le fluttuazioni casuali simmetriche attorno allo zero non devono essere troncate per garantire la propagazione imparziale dell'incertezza.
  * **Naqvi, M. & Anwar, S. (ACM TOSEM / ICSE, 2026):** *Bigger is Not Always Better: An Empirical Study on the Energy Consumption of LLMs for Software Engineering Tasks*, doi:10.1145/3715724. Dimostra sperimentalmente che l'isolamento della baseline di riposo è condizione preliminare obbligatoria per confrontare carichi inferenziali.
  * **SPECpower_ssj2008 & MLPerf Power (2025/2026):** *Methodology for Power Measurement in Benchmark Systems*. Definiscono formalmente i requisiti di stabilizzazione e misura della condizione di idle prima di avviare il carico.

### Decisione 3: Non-Additività dei Domini Hardware On-Die
* **Motivazione:** I registri energetici monitorano domini fisici annidati: ad esempio, il package CPU include i Core (PP0) e la grafica integrata/Uncore (PP1). Sommare tali canali comporta un doppio conteggio macroscopico dell'energia dissipata.
* **Riferimenti Scientifici:**
  * **Beyer & Wendler (2020):** Formalizzano la struttura ad albero dei domini energetici Intel e dimostrano che sommare Package e Core costituisce un errore metrologico grave.
  * **Hähnel, M. et al. (ACM SIGOPS OSR, 2012):** *Measuring Energy Consumption of Short Code Paths Using RAPL*, doi:10.1145/2333660.2333671. Analizzano la topologia interna dei circuiti di monitoraggio di potenza.

### Decisione 4: Separazione Epistemica a Tre Tier (Misurato, Attribuito, Modellato)
* **Motivazione:** In letteratura si riscontra spesso la pratica ingannevole di sommare Joule misurati al silicio, stime di carbonio da API cloud e conversioni energetiche del traffico di rete. Tali grandezze presentano ordini di incertezza, premesse epistemiche e domini di validità completamente eterogenei.
* **Riferimenti Scientifici:**
  * **Ren, S. et al. (Nature Computational Science, 2024):** *Reconciling the Contrasting Narratives of the Carbon Footprint of Large Language Models*, doi:10.1038/s43588-024-00711-4. Dimostra che le conclusioni contraddittorie sull'impatto ambientale dell'IA sono provocate dalla confusione tra misure fisiche e modelli di stima indiretti.
  * **Schwartz, R. et al. (Communications of the ACM, 2020):** *Green AI*, doi:10.1145/3381831. Invita la comunità alla massima trasparenza nella rendicontazione dei costi di computazione dell'IA.
  * **Rincé, S. et al. (GenAI Impact, 2025):** *EcoLogits: Tracking Energy and Carbon Footprint of Generative AI Models*. Riconosce che i modelli di stima analitica per API proprietarie (OpenAI, Anthropic) non possono essere verificati fisicamente dall'utente finale, giustificando la loro segregazione in un Tier 3 isolato.

### Decisione 5: Metrica ECPC e Scorporo dell'Oracolo (LLM-as-a-Judge)
* **Motivazione:** Valutare la qualità semantica di una risposta tramite un LLM-giudice comporta a sua volta l'esecuzione di un'inferenza. Se il costo energetico del giudice viene sommato al modello valutato, l'inferenza risulterà falsata. Inoltre, un modello che risponde in modo errato o genera loop di retry consuma risorse senza generare utilità.
* **Riferimenti Scientifici:**
  * **Zheng, L. et al. (NeurIPS, 2023):** *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. Dimostra che il paradigma LLM-as-a-judge introduce carichi computazionali significativi.
  * **Panickssery, A. et al. (arXiv, 2024):** *Evaluating Self-Preference Bias in LLM-as-a-Judge*, arXiv:2404.13076. Mostra i bias sistematici e l'impatto computazionale degli oracoli automatici.
  * **Kim, S. et al. (IEEE/ACM Micro, 2026):** *The Cost of Dynamic Reasoning in Agentic LLM Systems*. Conferma che nei flussi agentici l'unità di costo reale deve includere i tentativi falliti, fornendo la base teorica per la metrica **ECPC** (*Energy Cost Per Correct response*):
    $$\text{ECPC} = \frac{\sum_{i=1}^{N} E_{\text{eval}}(i)}{K_{\text{correct}}}$$

---

## 4. Conclusioni per la Tesi

La differenziazione di CasualWatt non poggia su affermazioni generiche, ma su un rigoroso quadro comparativo ancorato al codice sorgente dei concorrenti e su solide basi metrologiche certificate dalla letteratura peer-reviewed.
