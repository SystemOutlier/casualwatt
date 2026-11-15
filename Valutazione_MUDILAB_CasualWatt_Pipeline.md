# Valutazione di MUDILAB con CasualWatt: Pipeline a Più Livelli e Metriche di Efficienza

Questo documento definisce la metodologia di valutazione integrata tra **CasualWatt** e **MUDILAB** (l'agente di inferenza causale del laboratorio universitario), rispondendo alla domanda di ricerca:

> *«Quale configurazione di modello, quantizzazione e scaffolding massimizza la qualità, l'affidabilità e l'energia per risposta corretta, per ciascuna categoria di query causale?»*

---

## 1. Contesto e Domanda Scientifica

Nei benchmark convenzionali di Green AI la valutazione energetica si limita spesso a misurare l'energia o la potenza assorbita a parità di token generati ($\text{J/token}$ o $\text{Tokens/J}$). 

Nel contesto degli agenti autonomi e dei sistemi di **inferenza causale (MUDILAB)**, tale approccio è insufficiente e fuorviante:
* Un modello compatto e poco parametrizzato (es. 3B) può generare token velocemente e a basso consumo, ma fallire sistematicamente l'identificazione delle relazioni di causa-effetto, invocare il tool formale con argomenti scorretti o allucinare numeri privi di fondamento matematico.
* Un modello più robusto (es. 8B o 14B) consuma più Joule per singola query, ma identificando correttamente il grafo e utilizzando il tool deterministico raggiunge un tasso di accuratezza e affidabilità elevato.

La reale misura di efficienza energetica risiede quindi nel costo per unità di **utilità logica verificata**.

---

## 2. La Pipeline di Valutazione Multi-Livello

Per evitare di dipendere da una singola metrica o da giudizi soggettivi, CasualWatt implementa una pipeline epistemica a **quattro stadi sequenziali**:

```
+----------------------------------------------------------------------------------------------------+
|                         PIPELINE DI VALUTAZIONE MULTI-LIVELLO IN CASUALWATT                         |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ LIVELLO 1: Verifiche Deterministiche e Contrattuali (Adapter MUDILAB) ]                         |
|  • Validazione sintattica della label e parsing dell'albero sintattico (AST).                      |
|  • Verifica formale degli argomenti passati al tool formale `cau_inference`.                       |
|  • Prova di adozione (digest SHA-256 dell'output del tool trascritto nella risposta finale).      |
|  • Tolleranza d'errore numerica derivata dai decimali ULP stampati dal tool.                       |
|                                                                                                    |
|  [ LIVELLO 2: Metriche di Correttezza Rigida ed Indici Compositi (is_correct & Acc_comp) ]       |
|  • is_correct: verdetto rigido trinario {correct, incorrect, indeterminate}.                      |
|  • Acc_comp: indice descrittivo multidimensionale a pesi (nessi, label, coerenza).                |
|  • Copertura sperimentale (Coverage): isolamento delle risposte incomplete o indeterminate.       |
|                                                                                                    |
|  [ LIVELLO 3: Giudizio LLM Validato con Calibrazione Umana ]                                       |
|  • LLM-as-a-Judge: valutazione della spiegazione causale del modello (rubrica 0-3).                |
|  • Scorporo Energetico: isolamento dell'energia dell'oracolo (`judge_energy_j`) dal modello.       |
|  • Calibrazione Umana su campione (dev set) per validare l'accordo statistico (Cohen's Kappa).   |
|                                                                                                    |
|  [ LIVELLO 4: Metriche Energetiche Condizionate all'Utilità (ECPC, EPCL, ECE) ]                    |
|  • ECPC: Energy Cost Per Correct response (ammortamento energetico dei fallimenti a numeratore).   |
|  • EPCL: Energy Per Causal Link (Joule spesi per singolo nesso causale corretto nel grafo).        |
|  • Frontiera di Pareto (Trade-off Energia-Accuratezza) disaggregata per classe causale.           |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 3. Specifiche Formali delle Metriche

### A. Verdetto Rigido `is_correct`
Il superamento del task MUDILAB non ammette euristiche approssimate:
$$\text{Verdetto} = \text{Correct} \iff (\text{Label OK}) \land (\text{Args Tool OK}) \land (\text{Tool Exec OK}) \land (\text{Adoption Proven}) \land (|y - \hat{y}| \le \tau)$$
Se il modello indovina il numero finale ma:
* Non ha generato la chiamata al tool con gli argomenti attesi;
* L'output del tool non coincide con il testo trascritto nella risposta (fallimento digest SHA-256);
* La discrepanza supera la tolleranza $\tau$ derivata dalla precisione del tool;

la risposta viene catalogata come `incorrect` o `indeterminate`.

### B. Indice Descrittivo `Acc_comp` (Accuratezza Composita)
A differenza del verdetto binario, `Acc_comp` sintetizza il grado di avvicinamento alla soluzione su una scala pesata $[0, 1]$:
$$\text{Acc}_{\text{comp}} = w_1 \cdot \text{Acc}_{\text{links}} + w_2 \cdot \text{Score}_{\text{judge}} + w_3 \cdot \text{Sim}_{\text{coseno}}$$
*Nota metodologica di CasualWatt:* `Acc_comp` è mantenuto come indice descrittivo indipendente e non viene utilizzato come denominatore per metriche energetiche fisiche, preservando l'omogeneità dimensionale.

### C. ECPC: Energy Cost Per Correct Response
La metrica cardine per la valutazione degli agent framework. L'energia dei tentativi falliti viene imputata a carico del sistema:
$$\text{ECPC} = \frac{\sum_{i=1}^{N_{\text{totale}}} E_{\text{inferenza}}(i)}{K_{\text{corrette}}} = \frac{\sum_{i \in \text{successi}} E_i + \sum_{j \in \text{fallimenti}} E_j}{K_{\text{corrette}}}$$

Se un agente necessita di 5 iterazioni per produrre una risposta corretta, consumando $80\text{ J}$ per tentativo, il costo effettivo ammortizzato sarà $\text{ECPC} = 400\text{ J/risposta}$.

### D. EPCL: Energy Per Causal Link
Misura l'energia spesa per ciascun arco causale formalmente corretto identificato nel Directed Acyclic Graph (DAG):
$$\text{EPCL} = \frac{E_{\text{attiva}}}{\text{Numero di nessi causali validati}}$$

---

## 4. Disaggregazione per le Categorie Causali di MUDILAB

L'inferenza causale scala lungo la **Pearl's Causal Hierarchy** (PCH), presentando complessità computazionali e profili energetici eterogenei:

| Categoria MUDILAB | Livello PCH | Significato Logico | Comportamento del Tool `cau_inference` | Tolleranza Numerica $\tau$ |
| :--- | :--- | :--- | :--- | :--- |
| **`cond_prob`** | Livello 1 (Associazione) | $P(Y \mid X)$: calcolo della probabilità condizionata classica su distribuzioni osservazionali. | Stampa il risultato con 3 cifre decimali. | $\tau = 0{,}5 \cdot 10^{-3} = 5 \cdot 10^{-4}$ |
| **`inter`** | Livello 2 (Intervento) | $P(Y \mid \mathrm{do}(X))$: applicazione del do-calculus e chirurgia del grafo. | Stampa il risultato con 3 cifre decimali. | $\tau = 5 \cdot 10^{-4}$ |
| **`coherence`** | Validazione di Ipotesi | Verifica se le evidenze osservate sono compatibili con una singola istanza causale. | Stampa verdetto categorico (`compatible` / `not strongly compatible`) e 4 decimali. | $\tau = 5 \cdot 10^{-5}$ |
| **`counterfactual`** | Livello 3 (Controfattuale) | $P(Y_{X=x} \mid X=x', Y=y')$: abduzione dello stato latente, azione retroattiva e predizione nel mondo alternativo. | Richiede calcoli di integrazione e stampa 4 cifre decimali. | $\tau = 5 \cdot 10^{-5}$ |

CasualWatt impone che la **Frontiera di Pareto (Accuratezza vs ECPC)** sia calcolata e visualizzata **separatamente per ciascuna delle 4 categorie**, evitando di mascherare i limiti dei modelli sui task di Livello 3 dietro buone prestazioni nei task di Livello 1.

---

## 5. Protocollo per il Giudizio Ibrido (LLM-Judge e Umano)

1. **Scorporo Energetico del Giudice:**  
   Nei test con LLM-as-a-judge, la sessione di misura di CasualWatt isola la chiamata di grading registrandola nel campo dedicato `judge_energy_j`. La query sotto test non viene gravata dal consumo del suo valutatore.
2. **Validazione con Campione Umano:**  
   Su un sottoinsieme calibrato del dataset (es. 50 task per categoria), esperti umani assegnano lo score di qualità della spiegazione logica (rubrica 0–3). Viene calcolato l'indice di concordanza (Cohen's Kappa o F1 pesato) rispetto all'LLM-judge, garantendo la validità scientifica dell'oracolo automatico.
