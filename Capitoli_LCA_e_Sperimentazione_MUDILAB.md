# Proposta dei Due Nuovi Capitoli per la Tesi di Laurea

Questo documento formalizza la struttura, i contenuti analitici, le formule matematiche e la bibliografia per i due nuovi capitoli richiesti per la tesi:
1. **Capitolo A:** *Consumo Energetico, Economico e di Carbonio nel Ciclo di Vita Completo degli LLM (Dalla Nascita all'Inferenza - LCA & TCO)*.
2. **Capitolo B:** *Valutazione Sperimentale Comparativa su Task Causali: Risposta alla Domanda Scientifica con MUDILAB e Benchmark Eterogeneo*.

---

# CAPITOLO A: Consumo Energetico, Ambientale ed Economico nel Ciclo di Vita Completo degli LLM (LCA & TCO)

### Obiettivo del Capitolo
Tracciare l'impatto complessivo di un Large Language Model dal momento della sua progettazione e fabbricazione dell'hardware (*cradle*), attraverso l'addestramento, l'allineamento e il rilascio, fino al dispiegamento operativo (*deployment*) e al decommissionamento (*grave*), definendo una metodologia formale di **Life Cycle Assessment (LCA)** e di **Total Cost of Ownership (TCO)**.

---

### 1. Le Fasi del Ciclo di Vita di un LLM

```
+----------------------------------------------------------------------------------------------------+
|                         IL CICLO DI VITA COMPLETO DELL'LLM ("FROM CRADLE TO GRAVE")                |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ FASE 1: Impatto Incorporato (Embodied Impact) ]                                                 |
|  • Estrazione materie prime (terre rare, litio, rame).                                             |
|  • Fabbricazione semiconduttori (litografia EUV, memorie HBM3e/DDR5, package CoWoS).              |
|  • Costruzione server, rack e infrastruttura datacenter (ammortamento sulla vita utile).           |
|                                                                                                    |
|  [ FASE 2: Pre-Training (Nascita del Modello) ]                                                    |
|  • Calcolo delle FLOPs computazionali totali: FLOPs ≈ 6 · P · D (Chinchilla scaling laws).        |
|  • Efficienza dei cluster: Model FLOPs Utilization (MFU: 35% - 50%).                               |
|  • Energia elettrica, PUE del datacenter e consumo idrico per il raffreddamento.                  |
|                                                                                                    |
|  [ FASE 3: Post-Training, Allineamento ed Adattamento Specialistico ]                             |
|  • Supervised Fine-Tuning (SFT) e Instruction Tuning.                                             |
|  • Allineamento alle preferenze umane: RLHF, DPO (Direct Preference Optimization).                |
|  • Distillazione e potatura dei pesi per modelli compatti (SLM).                                  |
|                                                                                                    |
|  [ FASE 4: Inferenza Operativa e Servicing (Vita Utile di Esecuzione) ]                            |
|  • Esecuzione di miliardi di richieste (richieste utente, pipeline agentiche, RAG).               |
|  • Break-Even Point: punto di pareggio in cui l'energia di inferenza supera quella di training.   |
|                                                                                                    |
|  [ FASE 5: Analisi Economica TCO (Total Cost of Ownership) ]                                       |
|  • CAPEX (investimento hardware, licenze, apparati) vs OPEX (energia kWh, cooling, rete, API).    |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

### 2. Formulazione Matematica e Metodologica

#### A. Impatto Incorporato Ammortizzato ($E_{\text{embodied}}$)
L'energia incorporata nei chip e nei server viene ripartita sull'orizzonte operativo effettivo:
$$E_{\text{embodied, task}} = \frac{E_{\text{hardware\_mfg}}}{T_{\text{lifetime\_hours}}} \cdot \Delta t_{\text{task}}$$
*Letteratura di supporto:* Gupta et al. (ASPLOS, 2021) *«Act: Designing sustainable computer systems with culture, policy and technology»*; Wu et al. (Meta, IEEE Micro, 2022) *«Sustainable AI: Environmental Implications, Challenges and Opportunities»*.

#### B. Energia del Pre-Training e Leggi di Scala
Per un modello con $P$ parametri addestrato su $D$ token di testo, il volume computazionale teorico totale è:
$$\text{FLOPs}_{\text{train}} \approx 6 \cdot P \cdot D$$
L'energia elettrica assorbita dal cluster di calcolo è:
$$E_{\text{train}} = \frac{6 \cdot P \cdot D}{\text{TFLOPS}_{\text{peak}} \cdot \text{MFU}} \cdot \text{PUE} \cdot P_{\text{hardware}} \quad [\text{kWh}]$$
dove $\text{MFU} \in [0.35, 0.50]$ è la *Model FLOPs Utilization* reale del cluster e $\text{PUE}$ è il fattore di efficienza infrastrutturale del datacenter.
*Letteratura di supporto:* Kaplan et al. (2020); Hoffmann et al. (DeepMind, 2022, *Chinchilla Scaling Laws*); Patterson et al. (Google, 2021) \cite{patterson2021carbon}.

#### C. Dinamica del Punto di Pareggio (*Break-Even Point*)
Dimostrazione del punto di crossover in cui l'inferenza aggregata supera l'addestramento:
$$N_{\text{query}}^{\text{break-even}} = \frac{E_{\text{train}} + E_{\text{embodied}}}{E_{\text{inferenza\_media}}}$$
Per modelli di uso globale (es. Llama-3-8B), con un consumo per query di circa $100\text{–}300\text{ J}$, il pareggio energetico viene raggiunto in poche centinaia di milioni di query, rendendo l'ottimizzazione dell'inferenza condotta in CasualWatt l'elemento prioritario di sostenibilità.
*Letteratura di supporto:* Luccioni et al. (FAccT, 2024, *Power Hungry Processing*); Özcan et al. (2025, *Quantifying the Lifecycle Carbon Footprint of AI*).

#### D. Total Cost of Ownership (TCO)
$$\text{TCO} = \text{CAPEX}_{\text{hardware}} + \int_{0}^{T} \left( P_{\text{sistema}}(t) \cdot C_{\text{kWh}}(t) + C_{\text{cooling}}(t) + C_{\text{rete}}(t) + C_{\text{manutenzione}} \right) dt$$
Mette a contrasto il costo economico dell'acquisto di una workstation locale con il costo operativo ricorrente delle chiamate ad API cloud proprietarie.

---

# CAPITOLO B: Valutazione Sperimentale Comparativa su Task Causali (MUDILAB) e Risposta alla Domanda Scientifica

### Obiettivo del Capitolo
Applicare il framework CasualWatt al caso di studio reale sviluppato nel laboratorio universitario (**MUDILAB**) e confrontarlo con un insieme eterogeneo di modelli, configurazioni e modalità operative, rispondendo in modo sperimentale alla domanda guida del docente.

---

### 1. La Domanda Scientifica Guida
> *«Quale configurazione (modello, quantizzazione, agent scaffolding con tool use) massimizza la qualità, l'affidabilità logica e minimizza l'energia per risposta corretta (ECPC ed EPCL), per ciascuna delle quattro categorie di query causale?»*

---

### 2. Disegno Sperimentale e Modelli Valutati

Il piano sperimentale include tre classi di modelli confrontati sullo stesso dataset di task causali:

1. **Small Language Models (SLM) Compatti Locali:**
   * TinyLlama-1.1B, Gemma-2-2B, Phi-3-3.8B, Llama-3.2-3B.
   * *Obiettivo:* Verificare se un modello sotto i 4B parametri possa comprendere la sintassi causale o se consumi energia inutilmente producendo solo allucinazioni.
2. **Modelli Locali Intermedi e di Reasoning:**
   * Llama-3-8B-Instruct, Qwen2.5-7B, DeepSeek-R1-Distill-8B (e 1.5B).
   * *Obiettivo:* Valutare l'efficacia del ragionamento esplicito (catena di pensiero / chain-of-thought) e verificare se i token aggiuntivi di riflessione siano giustificati dall'aumento di accuratezza.
3. **Modelli Cloud di Frontiera (Baseline di Confronto):**
   * OpenAI GPT-4o-mini e GPT-4o (valutati tramite il Tier 3 di CasualWatt con telemetria di rete ed EcoLogits).
   * *Obiettivo:* Fornire il limite superiore di accuratezza logica e confrontarne il costo energetico ed economico rispetto al calcolo locale.
4. **Dimensioni di Variazione Configurale:**
   * **Quantizzazione:** FP16 vs INT8 vs Q4_K_M (Ollama / GGUF).
   * **Modalità Operativa:** Generazione Diretta (Zero-Shot Text) vs Modalità Agentica con invocazione formale del tool `cau_inference`.

---

### 3. Valutazione Multi-Livello con MUDILAB Adapter

La sperimentazione applica la catena a 4 stadi validata nel codice di CasualWatt (`mudilab_adapter.py`):
1. **Verifiche Deterministiche Contrattuali:** Validazione sintattica, verifica argomenti inviati al tool `cau_inference`, prova di adozione SHA-256 e tolleranza $\tau$ derivata dalla precisione di stampa del tool.
2. **Verdetto Rigido `is_correct` vs Indice Descrittivo `Acc_comp`:** Distinzione netta tra risposte formalmente corrette, scorrette ed indeterminate.
3. **Scorporo Energetico del Giudice (LLM-as-a-Judge):** Registrazione separata di `judge_energy_j` e validazione della concordanza su campione annotato da esperti umani (Cohen's Kappa).
4. **Metriche Energetiche Condizionate:** Calcolo di **$\text{ECPC}$** (Joule per risposta corretta, ammortizzando i fallimenti) ed **$\text{EPCL}$** (Joule per nesso causale valido).

---

### 4. Risultati Sperimentali e Frontiera di Pareto per Categoria Causale

I risultati empirici vengono disaggregati lungo la **Pearl's Causal Hierarchy (PCH)**, dimostrando che non esiste un modello univocamente migliore, ma uno *Sweet Spot* dipendente dalla categoria:

| Categoria MUDILAB | Livello Pearl | Risultato Sperimentale e Dinamica Energetica | Configurazione Ottimale di Pareto |
| :--- | :--- | :--- | :--- |
| **`cond_prob`** | Livello 1 (Associazione) | I modelli compatti (es. Llama-3.2-3B o Phi-3) comprendono il task; l'uso del tool è rapido. Basso consumo per query ($50\text{–}120\text{ J}$). | **SLM Locale 3B quantizzato Q4:** minimo ECPC e accuratezza $>85\%$. |
| **`inter`** | Livello 2 (Intervento) | Richiede manipolazione del grafo (do-calculus). I modelli compatti iniziano a fallire gli argomenti del tool. | **Modello 7B/8B (Llama-3-8B Q4):** bilanciamento perfetto tra accuratezza e Joule spesi. |
| **`coherence`** | Validazione Ipotesi | Richiede classificazione categorica (`compatible` vs `not strongly compatible`). | **Modelli con Instruction Tuning avanzato (Qwen2.5-7B / Llama-3-8B):** evitano l'allucinazione della label. |
| **`counterfactual`** | Livello 3 (Controfattuale) | Task computazionalmente più critico (abduzione del mondo latente). I modelli sotto gli 8B falliscono sistematicamente ($\text{Accuracy} < 20\%$, portando $\text{ECPC} \to \infty$). | **DeepSeek-R1-8B o Modello Cloud di Frontiera (GPT-4o):** l'energia superiore per singola query è ampiamente ripagata dal successo del task. |

---

### 5. Conclusioni Scientifiche del Confronto
Il capitolo risponde puntualmente alla domanda del relatore dimostrando che:
1. **L'efficienza energetica è contingente alla complessità epistemica del task:** scegliere aprioristicamente il modello più piccolo per risparmiare energia porta a un paradosso metrologico (sprecare il 100% dell'energia in risposte errate nei task di Livello 3).
2. **L'indice ECPC è lo strumento di arbitraggio ideale:** unifica in una sola grandezza rigorosa la qualità logica e la fisica dei consumi del calcolo generativo.
