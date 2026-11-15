# -*- coding: utf-8 -*-
contenuto = """# Relazione Tecnica: Analisi di Superiorità Metodologica
### Framework di Riferimento: CasualWatt vs CodeCarbon v3.3.0 (with EMI)

#### 1. Risoluzione dell'Architettura Client-Server (Il problema Ollama)
* **Il limite di CodeCarbon v3.3.0:** Ragiona esclusivamente a livello di singolo processo Python o dell'intera macchina. Non ha alcuna nozione del demone in background (`ollama serve`) o dei motori di inferenza allocati dinamicamente.
* **La soluzione di CasualWatt:** Mappa ricorsivamente i processi radice e intercetta i runner figli (come `llama-server.exe`) tracciando attivamente i loro contatori di I/O e tempi CPU.

#### 2. Accuratezza del Campionamento Hardware (Windows EMI)
* **Il comportamento di CodeCarbon v3.3.0:** Ha integrato l'uso di Windows EMI, ma con intervalli rigidi e standard (15 secondi) pensati per Macro-Tracking.
* **La soluzione di CasualWatt:** Interroga i contatori hardware con un buffer ad altissima frequenza (fino a 0.05 secondi) applicando formule a bordo finestra esatto.

### Tabella Comparativa dei Criteri Scientifici

| Criterio di Confronto | CodeCarbon v3.2 | CodeCarbon v3.3.0 (with EMI) | CasualWatt (Tuo Framework) | Superiorità Scientifica di CasualWatt |
| :--- | :--- | :--- | :--- | :--- |
| **Tracciamento dei Processi** | Solo PID Python o intera macchina. | Solo PID chiamante o macchina intera. | Albero dei processi (`ollama serve` + `llama-server`). | **Isolamento software reale:** Cattura l'inferenza scaricata sui demoni di background. |
| **Precisione CPU su Windows** | Stima teorica (TDP). | **Lettura hardware reale** (Windows EMI). | **Lettura hardware reale** (Windows EMI + PawnIO MSR). | **Flessibilità e Fallback:** Gestisce più backend hardware con buffer a 0.05s. |
| **Granularità Campionamento** | Intervallo rigido (~15s). | Intervallo rigido (~15s). | Campionamento ultra-rapido (0.05s) con interpolazione. | **Micro-Tracking per LLM:** Indispensabile per richieste estemporanee o singoli token. |
| **Profilazione LLM (TTFT)** | Impossibile. | Impossibile. | Separazione del **TTFT** dalla generazione dei token. | **Metriche atomiche:** Isola l'overhead del caricamento dal costo di calcolo puro. |
| **Fase di Stabilizzazione** | Assente. | Assente. | Algoritmo **`settle_idle` integrato (CPU+GPU)**. | **Baseline scientifica:** Garantisce che il PC sia stazionario prima di misurare. |
"""

with open("README_COMPARISON.md", "w", encoding="utf-8") as f:
    f.write(contenuto)

print("File README_COMPARISON.md creato con successo sul tuo PC!")
