# Proposta Definitiva di Indice della Tesi di Laurea Magistrale

**Titolo della Tesi:**  
*CasualWatt: Framework Multi-Piattaforma di Benchmark e Attribuzione Energetica per Inferenza LLM ed Agenti Causali su Hardware Consumer*

---

## Struttura Generale dell'Opera

```
+----------------------------------------------------------------------------------------------------+
|                         ARTICOLAZIONE GENERALE DELLA TESI DI LAUREA                                |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ FRONTESPIZIO ]                                                                                  |
|  [ ABSTRACT (Italiano ed English) ]                                                                |
|  [ SOMMARIO E GUIDA ALLA LETTURA ]                                                                 |
|  [ GLOSSARIO E ACRONIMI ] (CI, CO₂e, ECPC, EPCL, ECE/Acc_comp, EMI, MSR RAPL, NVML, PUE, TTFT, TDP)|
|                                                                                                    |
|  CAPITOLO 1: Introduzione e Motivazioni                                                            |
|  CAPITOLO 2: Contesto e Stato dell'Arte Metrologico                                                |
|  CAPITOLO 3: Consumo Energetico, Economico e di Carbonio nel Ciclo di Vita degli LLM (LCA & TCO)   |
|  CAPITOLO 4: Metodologia e Architettura di CasualWatt                                              |
|  CAPITOLO 5: Valutazione Sperimentale Comparativa su Task Causali (MUDILAB): Domanda Scientifica   |
|  CAPITOLO 6: Conclusioni e Sviluppi Futuri                                                         |
|                                                                                                    |
|  [ APPENDICI ] (Schema Dati 174 colonne, Protocollo, Suite >1450 Test, Formulario GUM)             |
|  [ BIBLIOGRAFIA ]                                                                                  |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## Indice Dettagliato dei Capitoli

### CAPITOLO 1: Introduzione e Motivazioni
* **1.1 Il paradosso della Red AI vs Green AI:** dalla corsa al throughput e alla scala di parametri all'esigenza di sostenibilità computazionale ed efficienza energetica.
* **1.2 La specificità degli Agent Framework:** oltre la generazione testuale; il costo computazionale del ragionamento causale multi-passo, del do-calculus e dell'uso di strumenti deterministici esterni.
* **1.3 Il problema di misura su hardware consumer:** assenza di interfacce dirette per la singola query sotto Windows e Linux, limiti dei contatori aggregati e distorsioni causate dai processi in background del sistema operativo.
* **1.4 La Domanda Scientifica Centrale:**  
  *«Quale configurazione (modello, quantizzazione, agent scaffolding con tool use) massimizza la qualità logica, l'affidabilità e minimizza l'energia per risposta corretta (ECPC ed EPCL), per ciascuna delle categorie di query causale?»*
* **1.5 Obiettivi della Tesi e Contributi Originali:** formalizzazione dei contributi metrologici ed ingegneristici del framework.
* **1.6 Struttura dell'Opera e Confini Metodologici:** perimetro dell'indagine e dichiarazione di ciò che è escluso (*fuori scope*).

---

### CAPITOLO 2: Contesto e Stato dell'Arte Metrologico
* **2.1 Tassonomia e Gerarchia delle Sorgenti Energetiche:**
  * Misure fisiche esterne al muro (wattmetri, prese smart, analizzatori di potenza).
  * Contatori hardware on-die (Intel/AMD RAPL, Windows EMI, NVIDIA NVML, AMD SMI).
  * Telemetria del sistema operativo (LHM, Windows E3/SRUM).
  * Modelli analitici di stima e proxy euristici (TDP $\times$ carico CPU).
* **2.2 Standard Industriali di Benchmark:** SPECpower_ssj2008 ed MLPerf Power/Inference; trasposizione dai cluster datacenter alle workstation consumer.
* **2.3 Analisi Critica degli Strumenti Esistenti (Verifica alle Fonti Primarie):**
  * *CodeCarbon (v3.3):* progressi sui contatori ma assenza totale di baseline idle (*zero* occorrenze di `idle` nel sorgente) e mancanza di attribuzione per processo con contatori.
  * *pyJoules (PowerAPI) e Scaphandre:* efficienza su ambiente Linux vs assenza di supporto nativo per Windows e mancata gestione delle finestre di prompt transitorio.
  * *MELODI:* monitoraggio per LLM basato su integrazione trapezoidale ($\int P\,dt$) vs errori di quadratura sul burst di prefill.
  * *TokenPowerBench:* scomposizione di fase su cluster HPC dedicati vs complessità del calcolo su macchine consumer eterogenee.
  * *EnviroLLM:* campionamento lento (2 s) e stime empiriche statiche su CPU privi di contatori.
* **2.4 Il Gap della Letteratura e il Posizionamento di CasualWatt.**

---

### CAPITOLO 3: Consumo Energetico, Economico e di Carbonio nel Ciclo di Vita Completo degli LLM (LCA & TCO)
* **3.1 L'approccio Life Cycle Assessment (LCA) applicato all'IA Generativa:** valutazione completa dal silicio al decommissionamento (*From Cradle to Grave*).
* **3.2 Embodied Impact (Impatto Incorporato):**
  * Estrazione di materie prime critiche e fabbricazione dei chip (litografia avanzata, packaging CoWoS, memorie HBM3e/DDR5).
  * Ammortamento dell'energia e del carbonio incorporato sull'orizzonte utile del server o della workstation (3–5 anni).
* **3.3 La Fase di Pre-Training (La "Nascita" del Modello):**
  * Calcolo del volume computazionale teorico e leggi di scala (Chinchilla e Kaplan: $\text{FLOPs} \approx 6 \cdot P \cdot D$).
  * Model FLOPs Utilization (MFU reale: $35\%\text{–}50\%$), efficienza del cluster hardware e fattore PUE del datacenter.
  * Intensità di carbonio della rete elettrica regionale e consumo idrico indiretto per il raffreddamento termico.
* **3.4 Post-Training, Allineamento ed Adattamento Specialistico:**
  * Supervised Fine-Tuning (SFT), allineamento alle preferenze umane (RLHF, DPO) e distillazione specialistica per Small Language Models (SLM).
* **3.5 Inferenza Operativa e Break-Even Point:**
  * Consumo cumulativo nel deployment operativo; dimostrazione del punto di pareggio in cui l'energia aggregata delle query di inferenza supera il costo di addestramento ($E_{\text{inference}} \gg E_{\text{training}}$).
* **3.6 Total Cost of Ownership (TCO):**
  * Modello economico: investimenti fissi di capitale (**CAPEX**, acquisto hardware/GPU) a confronto con costi operativi ricorrenti (**OPEX**, costo al kWh, manutenzione, raffreddamento e fatturazione per token di API cloud).

---

### CAPITOLO 4: Metodologia e Architettura di CasualWatt
* **4.1 I Tre Verbi Fondativi:** *Misurare* (contatore hardware), *Attribuire* (ripartizione per processo), *Stimare* (modello analitico etichettato).
* **4.2 Acquisizione ai Bordi di Finestra:** lettura differenziale da registri cumulativi a 64 bit ($\Delta E_{\text{pkg}}$) con interpolazione temporale esatta, superando l'errore dell'integrazione numerica.
* **4.3 Trattamento Dinamico della Baseline:**
  * Profilazione trifasica pre-misura (mediana su tre finestre da 30 s in idle controllato).
  * Diagnostica di deriva post-misura e verifica della stabilità termica ($r_A, r_B < 10\%$).
  * **Conservazione del Residuo Firmato (*Signed Residual*):** divieto del troncamento arbitrario a zero ($\max(0, E)$) in conformità alla guida metrologica JCGM/GUM per scongiurare bias positivi sistematici.
* **4.4 Attribuzione della Quota di Processo:** proiezione temporale CPU monotona sull'albero dei PID del motore di inferenza (Ollama / llama.cpp).
* **4.5 Scomposizione Temporale e di Fase:** separazione rigorosa tra energia di *prefill* (Time-To-First-Token, TTFT) ed energia di *decoding* autoregressivo sequenziale.
* **4.6 Tassonomia a Separazione Epistemica (I Tre Tier):**
  * *Tier 1 (Misurato Fisicamente):* contatori di silicio on-die locali (EMI/MSR per CPU, NVML/SMI per GPU).
  * *Tier 2 (Attribuito):* quota energetica imputata al processo applicativo.
  * *Tier 3 (Modellato/Stimato):* telemetria del traffico di rete ($kWh/GB$) e chiamate cloud ad API remote (EcoLogits con PUE).
  * *Principio di Invarianza:* divieto di somma scalare opaca tra grandezze di natura diversa; output a tupla strutturata e disaggregata.
* **4.7 Architettura Software di `cwEnergyModular`:** Pattern Provider/Adapter, isolamento dei driver di piattaforma, unwrapping e protezione dagli overflow hardware e suite di regressione (>1.450 test Pytest).

---

### CAPITOLO 5: Valutazione Sperimentale Comparativa su Task Causali (MUDILAB): Risposta alla Domanda Scientifica
* **5.1 Il Caso di Studio MUDILAB:** architettura dell'agente causale del laboratorio universitario, interazione con il tool deterministico in Python (`cau_inference`) e formalismo della Pearl's Causal Hierarchy (PCH).
* **5.2 Pipeline di Valutazione Multi-Livello:**
  * *Livello 1 (Verifiche Deterministiche Contrattuali):* validazione sintattica, verifica formale degli argomenti inviati al tool, prova di adozione tramite digest SHA-256 e tolleranza numerica $\tau$ derivata dalla precisione di stampa del tool.
  * *Livello 2 (Verdetto Rigido `is_correct` vs Indice `Acc_comp`):* penalizzazione delle allucinazioni fortunate e valutazione multidimensionale dell'avvicinamento al grafo.
  * *Livello 3 (Giudizio Ibrido Validato):* scorporo rigoroso dell'energia dell'oracolo (`judge_energy_j`) e calibrazione dell'LLM-judge su campione annotato da esperti umani (Cohen's Kappa).
  * *Livello 4 (Metriche Condizionate):* formalizzazione e calcolo degli indici **ECPC** (Joule per risposta corretta, ammortizzando a numeratore i tentativi falliti) ed **EPCL** (Joule per nesso causale valido).
* **5.3 Protocollo Sperimentale e Modelli Valutati:**
  * Small Language Models compatti locali: TinyLlama-1.1B, Gemma-2-2B, Phi-3-3.8B, Llama-3.2-3B.
  * Modelli intermedi e di reasoning: Llama-3-8B-Instruct, Qwen2.5-7B, DeepSeek-R1-Distill-8B.
  * Modelli cloud di frontiera: GPT-4o-mini e GPT-4o via API.
  * Variazione di quantizzazione (FP16, INT8, Q4_K_M) e modalità operativa (Direct Text vs Agentic Tool-Use).
* **5.4 Analisi dei Risultati Sperimentali per Categoria di Pearl:**
  * `cond_prob` (Livello 1 - Associazione, $\tau = 5 \cdot 10^{-4}$): efficienza degli SLM compatti e minimo ECPC.
  * `inter` (Livello 2 - Intervento / Do-calculus, $\tau = 5 \cdot 10^{-4}$): soglia dimensionale (7B/8B) per la manipolazione corretta del grafo.
  * `coherence` (Validazione di Ipotesi, $\tau = 5 \cdot 10^{-5}$): impatto dell'instruction tuning sulla classificazione categorica.
  * `counterfactual` (Livello 3 - Controfattuale, $\tau = 5 \cdot 10^{-5}$): criticità del ragionamento causale complesso; collasso dell'ECPC ad infinito per modelli sotto gli 8B ed eccellenza dei modelli di reasoning/cloud.
* **5.5 Tracciamento della Frontiera di Pareto Multi-Obiettivo:** mappe di trade-off $( \text{Energia}, \text{Accuratezza} )$ ed identificazione dei punti di *Sweet Spot*.
* **5.6 Analisi dei Risultati Negativi e Minacce alla Validità:** esito del gate *load-versus-control*, quantificazione dei bias di baseline e propagazione formale dell'incertezza metrologica.

---

### CAPITOLO 6: Conclusioni e Sviluppi Futuri
* **6.1 Sintesi dei Contributi Scientifici e Metrologici.**
* **6.2 Risposta Definitiva alla Domanda di Ricerca:** linee guida per la selezione della configurazione ottimale in base al profilo di carico causale.
* **6.3 Raccomandazioni per la Progettazione di Sistemi Green AI ed Agent Framework.**
* **6.4 Limiti Aperti e Sviluppi Futuri:** integrazione di wattmetri esterni per l'arbitrato di scala assoluta ed estensione ad architetture Apple Silicon (M-series).

---

## APPENDICI

* **Appendice A — Schema Dati e Tracciabilità dei Risultati:** specifica formale delle 174 colonne dello schema P5 congelato e dizionario dei metadati.
* **Appendice B — Protocollo di Misura e Checklist Operative:** procedure di stabilizzazione, warm-up e controlli di guardia pre-esecuzione.
* **Appendice C — Parametri di Configurazione e Pesi:** taratura di $\text{Acc}_{\text{comp}}$ e costanti di sistema.
* **Appendice D — Suite di Test e Verifica del Software:** documentazione di oltre 1.450 asserzioni Pytest per l'integrità del calcolo.
* **Appendice E — Inventario degli Artefatti Sperimentali:** catalogo dei dataset, dei log e delle campagne tracciate nel repository.
* **Appendice F — Formulario Metrologico e Budget di Incertezza:** formulario matematico consolidato e propagazione dell'incertezza conforme a JCGM 100:2008 (GUM).

---

## BIBLIOGRAFIA
*(Tutti i riferimenti della letteratura internazionale verificati alle fonti primarie: IEEE, ACM, AAAI, NeurIPS, SPEC, JCGM/GUM).*
