# Metodologie Scientifiche e Tassonomia delle Metriche per la Valutazione Energetica degli LLM

Questo documento formalizza in dettaglio le definizioni matematiche, le caratteristiche, i pregi, i difetti, i perimetri metrologici e i riferimenti bibliografici delle metriche energetiche per Large Language Model, rispondendo alla richiesta del relatore:

> *«Metodologie scientifiche per la valutazione energetica degli LLM: definizioni, caratteristiche, pregi e difetti, cosa misurano, quando è meglio una piuttosto dell'altra, con i relativi riferimenti alla letteratura.»*

---

## 1. Tassonomia a Quattro Livelli

```
+----------------------------------------------------------------------------------------------------+
|                         TASSONOMIA DELLE METRICHE ENERGETICHE PER LLM                              |
+----------------------------------------------------------------------------------------------------+
|                                                                                                    |
|  [ LIVELLO 1: Metriche Hardware e di Sistema ]                                                     |
|  • Potenza Media (P_avg [W]) e Picco di Potenza (P_peak [W])                                       |
|  • Energia Lorda di Esecuzione (E_total [J, kWh])                                                  |
|  • Energy-Delay Product (EDP [J·s]) e Energy-Delay Squared (ED²P [J·s²])                           |
|                                                                                                    |
|  [ LIVELLO 2: Metriche Normalizzate di Throughput e Generazione ]                                  |
|  • Joule per Token (J/token) e Tokens per Joule (Tokens/J)                                         |
|  • Scomposizione Energetica di Fase: Prefill Energy (E_prefill) vs Decoding Energy (E_decode)       |
|                                                                                                    |
|  [ LIVELLO 3: Metriche Condizionate all'Utilità e alla Qualità ]                                   |
|  • Energy Cost Per Correct Response (ECPC [J/risposta corretta])                                   |
|  • Energy Per Causal Link (EPCL [J/nesso logico valido])                                           |
|  • Frontiera di Pareto Multi-Obiettivo (Trade-off Energia-Accuratezza)                             |
|                                                                                                    |
|  [ LIVELLO 4: Metriche di Impatto Sistemico e Carbon Footprint ]                                   |
|  • Intensità Carbonica dell'Inferenza (gCO₂eq/query)                                               |
|  • Operational vs Embodied Energy (Quota di ciclo di vita LCA)                                     |
|                                                                                                    |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. Livello 1: Metriche Hardware e di Sistema

### A. Potenza Media Assorbita ($P_{\text{avg}}$) e Picco ($P_{\text{peak}}$)
* **Definizione Matematica:**
  $$P_{\text{avg}} = \frac{1}{\Delta t} \int_{t_0}^{t_1} P(t)\,dt = \frac{\Delta E}{\Delta t} \quad [\text{Watt, W}]$$
* **Cosa Misura:** La velocità istantanea o mediata di conversione dell'energia elettrica in calore termico da parte del silicio (package CPU, GPU o DRAM) durante l'inferenza.
* **Pregi:** Fondamentale per la progettazione termica, il dimensionamento dei sistemi di dissipazione e il rispetto dei vincoli di alimentazione (Power Capping e TDP).
* **Difetti:** Non quantifica il lavoro svolto. Un modello può assorbire una potenza modesta ($20\text{ W}$) ma impiegare 60 secondi ($1.200\text{ J}$), consumando molta più energia di un modello da $100\text{ W}$ che termina in 3 secondi ($300\text{ J}$).
* **Quando Usarla:** Nella caratterizzazione termica e nell'analisi dei transitori di clock dell'hardware.
* **Letteratura:** Rotem et al. (IEEE Micro, 2012); SPECpower_ssj2008 Methodology.

### B. Energy-Delay Product ($\text{EDP}$) ed $\text{ED}^2\text{P}$
* **Definizione Matematica:**
  $$\text{EDP} = E_{\text{totale}} \cdot \Delta t \quad [\text{J}\cdot\text{s}], \qquad \text{ED}^2\text{P} = E_{\text{totale}} \cdot (\Delta t)^2 \quad [\text{J}\cdot\text{s}^2]$$
* **Cosa Misura:** Il compromesso di efficienza architetturale tra l'energia consumata e il tempo necessario per completare l'elaborazione.
* **Pregi:** Penalizza sia le soluzioni ad altissimo consumo energetico, sia quelle eccessivamente lente (latenza inaccettabile). $\text{ED}^2\text{P}$ è indipendente dal ridimensionamento della tensione nei modelli CMOS ideali.
* **Difetti:** Indice privo di significato semantico diretto; non normalizza per lunghezza del prompt né per correttezza del task.
* **Quando Usarla:** Nel benchmarking architetturale comparativo tra acceleratori (GPU vs TPU vs NPU) e nella selezione dei regimi di clock.
* **Letteratura:** Horowitz et al. (IEEE ISSCC, 1994); Martin (ACM SIGARCH, 2001); Beyer & Wendler (ACM/SPEC ICPE, 2020).

---

## 3. Livello 2: Metriche Normalizzate di Throughput e Generazione

### A. Joule per Token ($J/\text{token}$) e Tokens per Joule ($\text{Tokens}/J$)
* **Definizione Matematica:**
  $$\text{Cost}_{\text{token}} = \frac{E_{\text{attiva}}}{N_{\text{out}}} \quad [\text{J/token}], \qquad \text{Throughput}_{\text{energy}} = \frac{N_{\text{out}}}{E_{\text{attiva}}} \quad [\text{Tokens/J}]$$
* **Cosa Misura:** La spesa energetica media marginale necessaria per generare una singola unità lessicale (token).
* **Pregi:** Standard de-facto ampiamente diffuso per confrontare modelli con architettura simile o quantizzazioni differenti (FP16 vs Q4).
* **Difetti (Critica Metrologica di CasualWatt):**
  1. Tratta i token di input (prefill) e di output (decoding) come entità equivalenti, ignorando la diversa natura computazionale.
  2. Non considera la qualità logica o semantica, premiando modelli prolissi con allucinazioni (*verbosity bias*).
* **Quando Usarla:** Per confrontare quantizzazioni dello stesso modello su prompt a lunghezza fissa ($N_{\text{in}}$ costante) e generazione omogenea.
* **Letteratura:** ML.ENERGY Benchmark (2025); Gül (ACM Computing Surveys, 2026); Husom et al. (MELODI, 2024).

### B. Scomposizione Energetica di Fase: $E_{\text{prefill}}$ vs $E_{\text{decode}}$
* **Definizione Matematica:**
  $$E_{\text{request}} = E_{\text{prefill}} + E_{\text{decode}}$$
  $$E_{\text{prefill}} = \Delta E(t_{\text{start}} \to t_{\text{TTFT}}), \qquad E_{\text{decode}} = \Delta E(t_{\text{TTFT}} \to t_{\text{end}})$$
  $$e_{\text{prefill}} = \frac{E_{\text{prefill}}}{N_{\text{in}}} \quad [\text{J/in\_tok}], \qquad e_{\text{decode}} = \frac{E_{\text{decode}}}{N_{\text{out}}} \quad [\text{J/out\_tok}]$$
* **Cosa Misura:** Disaccoppia la fase *compute-bound* (elaborazione parallela del prompt fino al Time-To-First-Token, TTFT) dalla fase *memory-bound* (generazione autoregressiva token per token con continuo accesso alla KV-cache).
* **Pregi:** Isola la non-linearità dell'attenzione ($O(N_{\text{in}}^2)$) dall'overhead sequenziale di decodifica. Evidenzia che $e_{\text{decode}}$ è da 5 a 11 volte superiore a $e_{\text{prefill}}$.
* **Difetti:** Richiede strumentazione software con intercettazione del segnale di TTFT in streaming e lettura sincronizzata del contatore hardware al millisecondo.
* **Quando Usarla:** Nei carichi asimmetrici (RAG, prompt con lungo contesto o task con codice esteso).
* **Letteratura:** Niu et al. (AAAI-26, *TokenPowerBench*); Cavagna et al. (2026, *SweetSpot*).

---

## 4. Livello 3: Metriche Condizionate all'Utilità e alla Qualità

### A. Energy Cost Per Correct Response ($\text{ECPC}$)
* **Definizione Matematica:**
  $$\text{ECPC} = \frac{\sum_{i=1}^{N_{\text{totale}}} E_{\text{inferenza}}(i)}{K_{\text{corrette}}} = \frac{\sum_{i \in \text{successi}} E_i + \sum_{j \in \text{fallimenti}} E_j}{K_{\text{corrette}}} \quad [\text{Joule / risposta corretta}]$$
* **Cosa Misura:** L'energia totale reale necessaria affinché il sistema produca un'unità di utilità verificata, **ammortizzando a numeratore l'energia dissipata nei tentativi falliti**, nelle allucinazioni o nei loop di retry dell'agente.
* **Pregi:**
  * Risolve il paradosso del modello che sembra efficiente solo perché consuma poco per singola query errata.
  * Integra intrinsecamente l'accuratezza ($\text{Pass@1}$, $\text{Accuracy}$) nella metrica energetica.
* **Difetti:** Tende all'infinito ($\infty$) se il modello fallisce tutti i task ($K_{\text{corrette}} = 0$), richiedendo la dichiarazione esplicita della copertura (*Coverage*).
* **Quando Usarla:** Obbligatoria nella valutazione di agent framework, task decisionali, compiti di programmazione (code repair) e inferenza causale (MUDILAB).
* **Letteratura:** Naqvi & Anwar (ESEM 2026, LIPIcs); Kim et al. (IEEE/ACM Micro, 2026).

#### Metriche di accuratezza come denominatore di ECPC

ECPC dipende dalla definizione di "corretto", che varia con il tipo di task e la metrica di accuratezza usata. Le metriche standard usate da lm-evaluation-harness e Evalita-LLM sono:

* **Exact match (EM):** la risposta coincide esattamente con il riferimento. È binaria (0/1), deterministica, ma severa: un singolo token diverso rende la risposta "errata". Usata per risposte fattuali brevi (es. "42", "Paris"). In CasualWatt, `is_correct` per risposte numeriche o testuali brevi coincide con exact match.
* **F1 score:** media armonica di precisione e recall a livello di token: $F1 = 2 \cdot \frac{\text{precision} \cdot \text{recall}}{\text{precision} + \text{recall}}$. Dà credito parziale per risposte parzialmente corrette, tollerante al parafrasamento. Usata per question answering estrattivo e NER. CasualWatt supporta `factual_f1` (F1 fattuale su claim verificati) nello schema di valutazione.
* **Pass@k:** per codice, genera $k$ soluzioni e conta se almeno una passa i test unitari. Misura la correttezza funzionale, non la similarità testuale. La formula unbiased è $1 - \binom{N-c}{k} / \binom{N}{k}$ dove $N$ è il numero di campioni generati e $c$ il numero di campioni corretti. CasualWatt implementa `compute_pass_at_k_unbiased` in `evaluation_schema.py`.

In CasualWatt, il valutatore primario usa `is_correct` (binario 1/0/N/A) come base per ECPC. Questo campo unifica tutti i tipi di risposta in un unico indicatore binario, permettendo di aggregare ECPC su task eterogenei. Lo schema di valutazione (`evaluation_schema.py`) supporta anche `factual_f1` e `pass_at_k`, ma ECPC aggrega su `is_correct` perché è il campo che permette il confronto cross-task.

La scelta della metrica di accuratezza influenza direttamente ECPC: una metrica più permissiva (F1) aumenta il denominatore, riducendo ECPC; una metrica più severa (exact match) lo riduce, aumentando ECPC. CasualWatt dichiara esplicitamente quale metrica usa per ogni riga (`eval_method` nello schema di valutazione) e non mescola metriche diverse nello stesso aggregato ECPC. Questo è fondamentale per la riproducibilità: un ECPC calcolato con exact match non è confrontabile con un ECPC calcolato con F1, anche se l'energia misurata è la stessa.

#### Regola di binarizzazione di `is_correct`

Il passaggio dalla metrica continua al denominatore discreto di ECPC è determinato dal tipo di risposta (`answer_type`) rilevato o dichiarato, non da una soglia applicata a posteriori su F1 o pass@k. Le regole sono implementate in `evaluator.py` e `robust_evaluator.py`:

1. **number**: estrazione numerica dalla risposta, confronto con la ground truth usando una tolleranza assoluta τ = 1e-6. `is_correct` = 1 se |estratto - GT| ≤ τ, altrimenti 0. Se il numero non è estraibile, `is_correct` = 0. Se la GT non è numerica finita, `is_correct` = N/A.
2. **short_text**: normalizzazione (case folding, punteggiatura, spazi) e verifica di contenimento lessicale. `is_correct` = 1 se la risposta normalizzata contiene la GT normalizzata, altrimenti 0. Alternative separate da "|" sono accettate.
3. **free_text**: similarità semantica tra risposta e GT. Se la valutazione semantica è abilitata (`use_semantic=True`), `is_correct` = 1 se `semantic_similarity` ≥ τ, con τ = `SEMANTIC_THRESHOLD` = 0.75 di default, configurabile via `CW_SEMANTIC_THRESHOLD`. Se la valutazione semantica è disabilitata (default durante il benchmark), `is_correct` = 1 se `lexical_similarity` ≥ 0.85 come stima provvisoria, da confermare POST-HOC con `semantic_judge.py`.
4. **label**: confronto esatto dopo normalizzazione del testo (case folding, strip). `is_correct` = 1 se la risposta normalizzata è uguale alla GT normalizzata, altrimenti 0.
5. **structured**: confronto esatto di chiavi/valori JSON. `is_correct` = 1 se la struttura estratta corrisponde alla GT, altrimenti 0.

`is_correct` = N/A (indeterminato) quando la valutazione non è decidibile: ground truth assente o non valida, giudice LLM non calibrato, o estrazione ambigua senza fallback deterministico. Le metriche continue `factual_f1` e `pass_at_k` restano registrate come colonne indipendenti dello schema, ma non sono binarizzate verso `is_correct`: sono indicatori diagnostici che non entrano nel denominatore di ECPC.

### B. Energy Per Causal Link ($\text{EPCL}$) ed Indici di Struttura
* **Definizione Matematica:**
  $$\text{EPCL} = \frac{E_{\text{attiva}}}{N_{\text{nessi\_validati}}} \quad [\text{Joule / nesso causale}]$$
* **Cosa Misura:** Il costo energetico sostenuto per estrarre o validare ogni singola relazione orientata causa-effetto in un grafo causale (DAG) verificato a fronte del ground truth.
* **Pregi:** Quantifica la densità energetica dell'estrazione di conoscenza relazionale.
* **Difetti:** Applicabile specificamente a compiti basati su grafi o estrazione di relazioni strutturate.
* **Quando Usarla:** Nei benchmark di causal discovery e causal reasoning (MUDILAB, CLadder).
* **Letteratura:** Sheth et al. (2025); Tu et al. (2024).

### C. Frontiera di Pareto Multi-Obiettivo (Trade-off Energia-Qualità)
* **Definizione:** L'insieme delle configurazioni di sistema $\mathbf{c}^* = \langle \text{Modello}, \text{Quantizzazione}, \text{Prompting} \rangle$ non dominate nel piano bi-dimensionale $(\text{Energia}, \text{Accuratezza})$:
  $$\mathbf{c}_1 \succ \mathbf{c}_2 \iff \left( \text{Acc}(\mathbf{c}_1) \ge \text{Acc}(\mathbf{c}_2) \land E(\mathbf{c}_1) \le E(\mathbf{c}_2) \right) \text{ con almeno una disuguaglianza stretta}$$
* **Pregi:** Rifiuta l'aggregazione arbitraria di grandezze eterogenee, fornendo la curva di trade-off reale.
* **Quando Usarla:** Nella selezione della migliore configurazione di deployment per contesti operativi.
* **Letteratura:** Schwartz et al. (Communications of the ACM, 2020, *Green AI*).

---

## 5. Livello 4: Metriche di Impatto Sistemico e Carbon Footprint

### A. Emissioni Operative di Carbonio ($gCO_2eq/\text{query}$)
* **Definizione Matematica:**
  $$\text{Em}_{\text{op}} = E_{\text{totale}} [\text{kWh}] \cdot \text{PUE} \cdot \text{CI}_{\text{grid}} \quad [gCO_2eq]$$
  dove $\text{PUE}$ è il Power Usage Effectiveness del datacenter e $\text{CI}_{\text{grid}}$ è l'intensità carbonica della rete elettrica locale ($gCO_2eq/\text{kWh}$).
* **Pregi:** Connette l'ingegneria del software con la contabilità climatica e i criteri ESG aziendali.
* **Difetti:** Non misura l'efficienza algoritmica. Il medesimo codice genera emissioni molto diverse in base alla regione geografica (es. Norvegia vs Polonia) o all'orario del giorno.
* **Quando Usarla:** Nei report di sostenibilità ambientale e per la selezione geografica dei datacenter cloud.
* **Letteratura:** Strubell et al. (ACL, 2019); Luccioni et al. (FAccT, 2024); Ren et al. (Nature Computational Science, 2024).

---

## 6. Quadro Sinottico di Selezione Operativa

| Domanda Scientifica / Obiettivo | Metrica Raccomandata | Unità | Metrica Sconsigliata (e perché) |
| :--- | :--- | :--- | :--- |
| **Dimensionamento termico e hardware locale** | Potenza Media ($P_{\text{avg}}$) e Picco ($P_{\text{peak}}$) | $\text{W}$ | $J/\text{token}$ (ignora i picchi istantanei di corrente). |
| **Ottimizzazione del runtime / KV-cache** | Energia di Fase ($E_{\text{prefill}}$ vs $E_{\text{decode}}$) | $\text{J/tok}$ | $J/\text{token}$ aggregato (maschera la disparità tra prefill e decode). |
| **Confronto tra formati di quantizzazione (FP16 vs Q4)** | Tokens per Joule ($\text{Tokens}/J$) a $N_{\text{in}}$ fisso | $\text{tok/J}$ | Potenza pura $P_{\text{avg}}$ (non quantifica la velocità di elaborazione dei pesi). |
| **Valutazione di Agent Framework e Task Logici (MUDILAB)** | **Energy Cost Per Correct Response (ECPC)** | **J/corretta** | **$J/\text{token}$ o $P_{\text{avg}}$** (premia modelli che allucinano velocemente a basso consumo). |
| **Estrazione di Grafi Relazionali e Reti Causali** | **Energy Per Causal Link (EPCL)** | **J/nesso** | Accuratezza scalare binaria (non cattura la qualità strutturale parziale). |
| **Scelta di compromesso per il deployment finale** | **Frontiera di Pareto Multi-Obiettivo** | $(\text{J}, \text{Acc})$ | Formula a punteggio unico arbitrario (somma indebitamente dimensioni eterogenee). |
| **Rendicontazione di sostenibilità e cloud** | Emissioni Operative ($gCO_2eq$) | $\text{g}$ | Trattamento locale al silicio (il PUE non si applica al laptop consumer). |

---

## 7. Strumenti di Benchmarking dell'Accuratezza vs Strumenti di Misura Energetica

Questa sezione distingue due categorie di strumenti che operano su domini diversi ma complementari.

### Strumenti di Benchmarking dell'Accuratezza

Misurano **quanto è bravo il modello**, non quanto costa energeticamente.

| Strumento | Cosa standardizza | Unità | Dove non arriva |
|---|---|---|---|
| **lm-evaluation-harness** (EleutherAI) | Accuratezza su 200+ task accademici (MMLU, GSM8K, HellaSwag, ARC, ecc.) | %, F1, pass@k | Non misura energia; motore dell'Open LLM Leaderboard di Hugging Face |
| **VLMEvalKit** (OpenCompass) | Accuratezza multimodale su 80+ benchmark (MMBench, MM-Vet, MathVista) | %, exact match | Non misura energia; estende il problema di valutazione al dominio VLM |
| **Evalita-LLM** (Magnini et al., CLiC-it 2025) | Accuratezza su 10 task nativi in italiano (multiple-choice e generativi) | %, CPS | Non misura energia; implementato su lm-evaluation-harness, leaderboard Hugging Face |

**Posizionamento:** CasualWatt non valuta l'accuratezza, ma la rende misurabile energeticamente. lm-evaluation-harness o Evalita-LLM potrebbero essere il *generatore di workload* mentre CasualWatt è il *misuratore di energia*. Evalita-LLM ha rilevanza diretta per CasualWatt perché fornisce workload la cui accuratezza è standardizzata per la lingua italiana, che è la lingua di lavoro del framework. Nessun lavoro pubblicato combina uno di questi benchmark con misura energetica fine-grained per singola inferenza su CPU consumer.

### Strumenti di Misura Energetica

Misurano **quanto costa energeticamente**, non quanto è bravo il modello.

| Strumento | Natura | Piattaforma | Granularità |
|---|---|---|---|
| **CasualWatt** (questo lavoro) | Misura + attribuzione, a tier separati | Windows (EMI/PawnIO), Linux (RAPL), GPU per vendor | 0.28–0.34 s misurati |
| **TokenPowerBench** (AAAI-26) | Misura (NVML/RAPL) | Nodo GPU su cluster | J/token con decomposizione prefill/decode |
| **MELODI** (2024) | Misura (Scaphandre + nvidia-smi) | GPU/server | Per configurazione |
| **CodeCarbon** | Misura (contatori) o stima (TDP) | Cross-platform | 15 s di default |
| **EnviroLLM** (2025) | Stima CPU / misura GPU | Anche Windows | Campionamento 2 s |

**Gap di CasualWatt:** Nessun strumento combina, nella stessa riga di risultato: (i) contatore on-die su CPU consumer, (ii) attribuzione alla singola chiamata, (iii) tassonomia per riga fra misura, attribuzione e stima, (iv) qualità della risposta con energia del valutatore scorporata.

---

## 8. Valutazione dei Metodi dei Tre Strumenti per CasualWatt

Questa sezione analizza quali metodi di lm-evaluation-harness, VLMEvalKit e Evalita-LLM possono essere utili a CasualWatt, distinguendo tra:
- **(A) Metodi copiabili senza integrazione**: principi o pattern che CasualWatt può adottare nel proprio codice senza dipendere dal repository sorgente.
- **(B) Integrazione utile**: casi in cui integrare il repository sorgente porta un valore significativo.
- **(C) Non applicabile**: metodi che non si applicano al dominio di CasualWatt.

### 8.1 lm-evaluation-harness (EleutherAI)

| Metodo | Cosa fa | Categoria | Motivazione |
|---|---|---|---|
| **Task definition YAML** | Ogni task è definito da un file YAML con dataset, prompt, metriche, filtri di post-processing | **(A) Copiabile** | CasualWatt può adottare lo stesso pattern per definire i task di benchmark energetico: un file YAML che dichiara il modello, il prompt, la finestra di misura e le metriche energetiche attese. Non serve il repository, serve il pattern. |
| **Filtri di post-processing** | Pipeline di filtri applicati agli output del modello prima dello scoring (truncamento, estrazione risposte, ensemble) | **(A) Copiabile** | CasualWatt ha già filtri di validità energetica (`energy_valid`, `active_valid`). Estendere il pattern a filtri dichiarativi (YAML) renderebbe la catena di validazione più trasparente e riproducibile. |
| **Decontaminazione n-gram** | Rileva sovrapposizione tra dataset di test e dati di addestramento per evitare benchmark inflazionati | **(C) Non applicabile** | CasualWatt misura energia, non accuratezza. La decontaminazione è un problema di valutazione dell'accuratezza, non di misura energetica. |
| **Loglikelihood vs generate_until** | Due modalità di interrogazione: probabilità del target token vs generazione libera fino a EOS | **(C) Non applicabile** | CasualWatt non interroga i modelli, misura l'energia delle chiamate che l'utente fa. La modalità di interrogazione è fuori perimetro. |
| **Conteggio few-shot controllato** | Ogni task dichiara esplicitamente il numero di esempi few-shot nel prompt | **(A) Copiabile** | CasualWatt può dichiarare il contesto (prompt length, few-shot count) come metadato del benchmark, non per accuratezza ma per tracciabilità energetica: un prompt con 10 few-shot costa più di uno zero-shot. |
| **Cache dei risultati** | Memorizza i risultati valutati per evitare ricalcoli costosi | **(C) Non applicabile** | CasualWatt misura energia in tempo reale, non ha risultati cached da ricalcolare. |
| **Request reordering** | Riordina le richieste per ottimizzare il batch processing | **(C) Non applicabile** | CasualWatt misura l'energia delle chiamate reali, non ottimizza il throughput. |

**Sintesi lm-evaluation-harness:** I metodi più utili sono il **task definition YAML** (pattern dichiarativo) e i **filtri di post-processing** (catena dichiarativa di validazione). Entrambi sono pattern architetturali, non codice da copiare: CasualWatt li adotta come principio, non come dipendenza.

### 8.2 VLMEvalKit (OpenCompass)

| Metodo | Cosa fa | Categoria | Motivazione |
|---|---|---|---|
| **LLM-augmented answer extraction** | Se l'exact matching fallisce, un LLM ausiliario (es. ChatGPT) estrae la risposta semantica | **(A) Copiabile** | CasualWatt ha già un valutatore robusto (`robust_evaluator.py`) che usa contratti deterministici. Potrebbe adottare un ramo secondario dove un LLM ausiliario valida risposte ambigue, ma solo come diagnostica, non come decisione primaria. |
| **CircularEval** | Valutazione circolare per MCQ: ruota le opzioni per rilevare bias posizionali | **(C) Non applicabile** | CasualWatt non valuta l'accuratezza delle risposte, misura l'energia. Il bias posizionale è un problema di valutazione, non di misura. |
| **Pipeline unificata** | Un'interfaccia `.generate()` per tutti i modelli, con dati in formato `.tsv` standardizzato | **(A) Copiabile** | CasualWatt può adottare un formato standardizzato per i dati di benchmark (già fatto con lo schema CSV a 174 colonne). L'interfaccia unificata è un principio architetturale, non codice da copiare. |
| **Parallelized inference** | Esecuzione parallela su API commerciali e modelli open-source | **(C) Non applicabile** | CasualWatt misura l'energia delle chiamate sequenziali reali, non parallelizza l'inferenza. |
| **Resume functionality** | Riprende le valutazioni interrotte senza ricominciare da zero | **(A) Copiabile** | CasualWatt può implementare il resume delle campagne di benchmark, salvando lo stato dopo ogni blocco e riprendendo dall'ultimo blocco completato. |

**Sintesi VLMEvalKit:** Il metodo più utile è il **resume delle campagne interrotte**, che CasualWatt può implementare come estensione del runner v4. L'**LLM-augmented answer extraction** è un principio già parzialmente implementato nel valutatore robusto (ramo diagnostico opzionale).

### 8.3 Evalita-LLM (Magnini et al.)

| Metodo | Cosa fa | Categoria | Motivazione |
|---|---|---|---|
| **Multi-prompt per robustezza** | Ogni task è valutato con più formulazioni del prompt per mitigare la sensibilità al prompt | **(A) Copiabile** | **Il metodo più utile a CasualWatt.** Un prompt diverso può produrre risposte di lunghezza diversa, quindi energia diversa. Misurare con un solo prompt dà un numero legato a quella formulazione, non al modello. CasualWatt può adottare il multi-prompt come opzione del runner v4: eseguire lo stesso task con N prompt diversi e aggregare l'energia con la stessa statistica (Wilson CI, bootstrap a cluster) già implementata. |
| **Validazione iterativa dei prompt** | I prompt candidati sono validati contro un set di LLM prima di entrare nel benchmark | **(C) Non applicabile** | CasualWatt non crea benchmark di accuratezza, misura l'energia dei benchmark esistenti. |
| **Metriche di stabilità del prompt** | Misura quanto varia l'accuratezza al variare del prompt | **(A) Copiabile** | CasualWatt può estendere il concetto: misurare quanto varia l'energia al variare del prompt, non l'accuratezza. Questo è un nuovo metrica: la **sensibilità energetica al prompt**, che restituisce tre metriche complementari: (1) `std_energy_j` = deviazione standard assoluta in Joule, utile per un singolo modello ma non confrontabile cross-modello; (2) `cv` = Coefficiente di Variazione (σ/μ), che normalizza la deviazione rispetto alla media permettendo il confronto equo fra modelli di dimensione diversa; (3) `max_min_ratio` = rapporto massimo/minimo, che misura l'ampiezza conservativa della variabilità. |
| **Task nativi in italiano** | 10 task in italiano per evitare bias culturali da traduzione | **(B) Integrazione utile** | Evalita-LLM fornisce workload la cui accuratezza è standardizzata per l'italiano. CasualWatt può integrare Evalita-LLM come generatore di workload per campagne di benchmark in italiano, senza modificare il codice di misura. |
| **Leaderboard Hugging Face** | Leaderboard pubblico per confrontare i modelli su Evalita-LLM | **(C) Non applicabile** | CasualWatt non mantiene leaderboard di accuratezza. |

**Sintesi Evalita-LLM:** Il **multi-prompt** è il metodo più utile a CasualWatt. Non serve integrare il repository, serve adottare il principio: eseguire lo stesso task con più prompt e aggregare l'energia con la statistica già implementata. La **sensibilità energetica al prompt** è una nuova metrica derivabile da questo principio.

### 8.4 Riepilogo: Cosa CasualWatt può adottare

| Metodo | Strumento sorgente | Cosa cambia in CasualWatt | Sforzo |
|---|---|---|---|
| **Task definition YAML** | lm-evaluation-harness | Pattern dichiarativo per definire i task di benchmark energetico | Medio: estendere il runner v4 per leggere i task da YAML |
| **Filtri dichiarativi** | lm-evaluation-harness | Catena di validazione energetica dichiarativa (YAML) | Medio: estendere i filtri esistenti |
| **Conteggio few-shot** | lm-evaluation-harness | Metadato del benchmark per tracciabilità energetica | Basso: aggiungere colonna a `notes` |
| **Resume campagne** | VLMEvalKit | Salvare lo stato dopo ogni blocco e riprendere | Medio: estendere il runner v4 |
| **Multi-prompt** | Evalita-LLM | Eseguire lo stesso task con N prompt e aggregare l'energia | Alto: estendere il runner v4 con il loop sui prompt |
| **Sensibilità energetica al prompt** | Evalita-LLM (derivato) | Tre metriche: std assoluta, CV (σ/μ) per confronto cross-modello, Max/Min per ampiezza conservativa | Basso: calcolare dopo il multi-prompt |
| **LLM-augmented answer extraction** | VLMEvalKit | Ramo diagnostico opzionale per risposte ambigue | Alto: integrare un LLM ausiliario nel valutatore |

### 8.5 Implementazione

I tre metodi a **maggiore rapporto beneficio/sforzo** sono stati implementati nel codice di CasualWatt:

1. **Task definition YAML** (lm-evaluation-harness): `cwEnergyModular/task_definition.py` implementa la classe `TaskDefinition` che carica i task da file YAML, convalida i campi obbligatori (`task_name`, `model`, `prompt`) e gestisce le varianti del prompt. Un esempio è fornito in `cwEnergyModular/tasks/qwen2.5_0.5b_italiano.yaml`.

2. **Multi-prompt** (Evalita-LLM): `cwEnergyModular/multi_prompt.py` implementa `run_multi_prompt()` che esegue lo stesso task con N prompt diversi e `aggregate_prompt_energy()` che aggrega l'energia con la statistica già implementata (media, deviazione standard, min, max).

3. **Sensibilità energetica al prompt** (derivato da Evalita-LLM): `cwEnergyModular/multi_prompt.py` implementa `calculate_energy_prompt_sensitivity()` che restituisce tre metriche complementari:
   - `std_energy_j`: deviazione standard assoluta in Joule, utile per un singolo modello ma non confrontabile cross-modello perché un LLM da 70B consuma ordini di grandezza più di un SLM da 3B.
   - `cv` (Coefficient of Variation, σ/μ): normalizza la deviazione rispetto alla media, permettendo il confronto equo — se un SLM ha CV = 0,15 e un LLM ha CV = 0,08, l'SLM è più sensibile alla formulazione rispetto al suo consumo medio.
   - `max_min_ratio`: rapporto massimo/minimo, misura l'ampiezza conservativa — un rapporto 2,0 significa che la variante più costosa consuma il doppio della più economica.

I test stanno in `cwEnergyModular/tests/test_task_definition.py` (6 test) e `cwEnergyModular/tests/test_multi_prompt.py` (10 test), per un totale di **16 test passati**.

Nessuno di questi richiede di integrare i repository sorgente. Sono principi architetturali che CasualWatt adotta nel proprio codice, mantenendo l'indipendenza dai benchmark di accuratezza.
