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
* **Letteratura:** Naqvi & Anwar (ACM TOSEM, 2026); Kim et al. (IEEE/ACM Micro, 2026).

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
