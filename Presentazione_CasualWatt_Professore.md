# CasualWatt: Metrologia e Attribuzione Energetica per l'Inferenza LLM Locale ed Eterogenea
**Dossier di Presentazione Accademica per il Relatore**

---

## 1. Inquadramento e Domanda di Ricerca

La crescente diffusione di modelli linguistici di grandi dimensioni (LLM) su workstation, laptop e dispositivi edge impone il passaggio da benchmark unicamente prestazionali a metriche rigorose di **efficienza energetica e sostenibilità computazionale**.

> **Domanda di Ricerca Centrale:**  
> *«La domanda scientifica corretta non è soltanto "quale modello consuma meno?", ma "quale configurazione (modello, quantizzazione, agent scaffolding con tool use) massimizza la qualità logica, l'affidabilità e minimizza l'energia per risposta corretta (ECPC ed EPCL), per ciascuna categoria di query causale?"»*

---

## 2. I Pilastri Metodologici di CasualWatt

| Dimensione Metrologica | Approccio Comune in Letteratura | Innovazione Rigorosa di CasualWatt |
| :--- | :--- | :--- |
| **Acquisizione Energetica** | Campionamento periodico della potenza istantanea $P(t)$ (intervalli 100–1000 ms) e integrazione numerica approssimata $\int P(t)\,dt$. | **Lettura differenziale da registri hardware cumulativi** (MSR RAPL su Linux, EMI/PawnIO su Windows, NVML/SMI per GPU) ai bordi della finestra con interpolazione temporale. |
| **Compensazione Baseline** | Baseline assente oppure valore costante arbitrario con troncamento a zero dei residui negativi: $\max(0, E - E_{\text{base}})$. | **Baseline dinamica trifasica** (mediana su tre finestre da 30 s in idle) e **conservazione del residuo firmato** ($\pm$) per scongiurare bias positivi sistematici. |
| **Omogeneità Epistemica** | Somma scalare acritica di grandezze eterogenee (silicio locale, traffico router, datacenter cloud). | **Separazione Epistemica a Tre Tier:** distinzione formale tra valori Misurati (Tier 1), Attribuiti (Tier 2) e Modellati (Tier 3). |
| **Valutazione Agenti (LLM-as-a-Judge)** | Consumo aggregato che include l'energia dell'oracolo e ignora l'energia sprecata nei tentativi falliti. | **Scorporo dell'energia del giudice** e adozione dell'indice **ECPC** (*Energy Cost Per Correct response*), imputando i tentativi falliti a numeratore. |
| **Integrità Scientifica** | Trattamento silente delle anomalie; omissione dei fallimenti dei controlli di guardia. | **Trasparenza sui risultati negativi:** documentazione esplicita del fallimento del gate *load-vs-control* e dei limiti fisici del silicio. |

---

## 3. Il Ciclo di Vita Completo degli LLM: Dalla Nascita all'Inferenza (LCA & TCO)

Il framework inquadra l'impatto dell'IA generativa in una prospettiva sistemica completa (*From Cradle to Grave*):
1. **Embodied Impact (Fabbricazione Hardware):** Fabbricazione di chip, acceleratori e server ammortizzata sull'orizzonte utile (3–5 anni).
2. **Pre-Training (Nascita del Modello):** Calcolo computazionale teorico $\text{FLOPs} \approx 6 \cdot P \cdot D$ (leggi di scala di Chinchilla/Kaplan), scalato sull'efficienza reale del cluster ($\text{MFU} \in [0.35, 0.50]$) e sul $\text{PUE}$ del datacenter.
3. **Post-Training ed Allineamento:** Fine-tuning supervisionato (SFT), allineamento (DPO, RLHF) e distillazione.
4. **Inferenza Operativa e Break-Even Point:** Dimostrazione che per modelli ampiamente utilizzati il consumo aggregato dell'inferenza supera rapidamente quello del training ($E_{\text{inference}} \gg E_{\text{training}}$).
5. **Total Cost of Ownership (TCO):** Analisi comparativa tra investimenti infrastrutturali fissi (**CAPEX**) e costi operativi ricorrenti (**OPEX** al kWh o costi API cloud).

---

## 4. Applicazione al Caso di Studio MUDILAB e Pipeline Multi-Livello

MUDILAB (l'agente di inferenza causale sviluppato nel laboratorio universitario) viene valutato attraverso una pipeline a quattro stadi:
* **Livello 1: Verifiche Deterministiche e Contrattuali:** Validità sintattica della label, correttezza degli argomenti del tool `cau_inference`, prova di adozione tramite digest SHA-256 e tolleranza numerica $\tau$ derivata dalla precisione di stampa del tool.
* **Livello 2: Verdetto Rigido (`is_correct`) vs Indice Composito (`Acc_comp`):** `is_correct` impedisce che allucinazioni numeriche fortunate vengano premiate; `Acc_comp` valuta l'avvicinamento multidimensionale al grafo.
* **Livello 3: Giudizio LLM Validato con Campione Umano:** L'energia dell'oracolo è scorporata in `judge_energy_j`; la qualità esplicativa è validata misurando la concordanza con esperti umani (Cohen's Kappa).
* **Livello 4: Metriche Energetiche Condizionate all'Utilità:**
  $$\text{ECPC} = \frac{\sum_{i=1}^{N_{\text{totale}}} E_{\text{inferenza}}(i)}{K_{\text{corrette}}}, \qquad \text{EPCL} = \frac{E_{\text{attiva}}}{\text{Nessi Causali Validi}}$$

### Disaggregazione per le 4 Categorie di MUDILAB (Pearl Hierarchy):
1. **`cond_prob` (Associazione, Livello 1):** $P(Y \mid X)$, tolleranza $\tau = 5 \cdot 10^{-4}$. Ottimale con SLM compatti (3B).
2. **`inter` (Intervento / Do-calculus, Livello 2):** $P(Y \mid \mathrm{do}(X))$, tolleranza $\tau = 5 \cdot 10^{-4}$. Richiede modelli 7B/8B per manipolare correttamente il grafo.
3. **`coherence` (Validazione di Ipotesi):** Verdetto categorico (`compatible` / `not strongly compatible`), tolleranza $\tau = 5 \cdot 10^{-5}$.
4. **`counterfactual` (Controfattuali, Livello 3):** $P(Y_{X=x} \mid X=x', Y=y')$, tolleranza $\tau = 5 \cdot 10^{-5}$. Task computazionalmente critico in cui solo modelli avanzati (8B reasoning o frontier cloud) evitano il collasso dell'ECPC ad infinito.

---

## 5. Articolazione dei Capitoli della Tesi di Laurea

1. **Capitolo 1 — Introduzione e Motivazioni:** Il trade-off tra qualità generativa ed efficienza energetica nell'AI edge e locale.
2. **Capitolo 2 — Contesto e Stato dell'Arte Metrologico:** Analisi critica comparativa di CodeCarbon 3.3, Scaphandre, pyJoules, MELODI, TokenPowerBench, PowerJoular ed EnviroLLM; limiti dell'integrazione numerica e della gestione dell'idle.
3. **Capitolo 3 — Metodologia e Architettura di CasualWatt:** Teoria della misura differenziale ai bordi di finestra, compensazione della baseline trifasica con residui firmati e tassonomia epistemica a tre Tier.
4. **Capitolo 4 — Consumo Energetico, Economico e di Carbonio nel Ciclo di Vita Completo degli LLM (LCA & TCO):** Dalla nascita all'inferenza (*From Cradle to Grave*): embodied impact, training FLOPs (Chinchilla), post-training, break-even point e total cost of ownership.
5. **Capitolo 5 — Valutazione Sperimentale Comparativa su Task Causali (MUDILAB): Risposta alla Domanda Scientifica:** Studio comparativo su modelli open-source (TinyLlama, Gemma-2, Phi-3, Llama-3.2, Llama-3-8B, DeepSeek-R1, Qwen2.5) e cloud (GPT-4o), calcolo di `is_correct`, `Acc_comp`, ECPC ed EPCL disaggregati per la scala di Pearl.
6. **Capitolo 6 — Conclusioni e Linee Guida per il Green Computing:** Sintesi dei contributi, raccomandazioni per gli agent framework e direzioni future di ricerca.

---

## 6. Documenti Operativi nel Repository

* 📄 **[Capitoli_LCA_e_Sperimentazione_MUDILAB.md](file:///c:/Users/Massimo/Documents/CasualWatt/CWProject/Capitoli_LCA_e_Sperimentazione_MUDILAB.md)**
* 📄 **[Metodologie_e_Metriche_Energetiche_LLM.md](file:///c:/Users/Massimo/Documents/CasualWatt/CWProject/Metodologie_e_Metriche_Energetiche_LLM.md)**
* 📄 **[Valutazione_MUDILAB_CasualWatt_Pipeline.md](file:///c:/Users/Massimo/Documents/CasualWatt/CWProject/Valutazione_MUDILAB_CasualWatt_Pipeline.md)**
* 📄 **[Matrice_Comparativa_Stato_Arte_CasualWatt.md](file:///c:/Users/Massimo/Documents/CasualWatt/CWProject/Matrice_Comparativa_Stato_Arte_CasualWatt.md)**
* 🌐 **[Presentazione_CasualWatt_Professore.html](file:///c:/Users/Massimo/Documents/CasualWatt/CWProject/Presentazione_CasualWatt_Professore.html)**
