# 🧠 CausalWatt - Multi-Agent System for Causal Inference

Un sistema multi-agente **neuro-simbolico** che combina la comprensione del linguaggio naturale degli LLM con la precisione matematica di `pyAgrum` per eseguire inferenza causale sulla rete bayesiana **Insurance** (AIMA).

## 🎯 Obiettivo del Progetto

Dimostrare che un'architettura ibrida (**Small Machine + Better Process > Big Machine**) può superare i limiti dei modelli LLM locali nella risoluzione di problemi di inferenza causale complessi, eliminando completamente le "allucinazioni" numeriche.

## 🏗️ Architettura

Il sistema è composto da **3 agenti specializzati** + **1 motore matematico deterministico**:

┌─────────────────┐
│ UTENTE │ Query in linguaggio naturale
└────────┬────────┘
│
▼
┌─────────────────────────────────────────┐
│ 1. TRANSLATOR (LLM locale - Ollama) │ Estrae JSON strutturato
│ {"input": {...}, "output": {...}} │ dalle entità del grafo
└────────┬────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│ 2. CLASSIFICATOR (LLM locale) │ Assegna label causale:
│ posterior | intervention | │ posterior, intervention,
│ coherence | counterfactual │ coherence, counterfactual
└────────┬────────────────────────────────┘
│
▼
┌─────────────────────────────────────────┐
│ 3. MOTORE MATEMATICO (Python + pyAgrum)│ Esecuzione DIRETTA
│ - LazyPropagation (posterior) │ (anti-allucinazione)
│ - causalImpact (intervention) │
│ - Inference + Threshold (coherence) │
│ - cobound + Fréchet (counterfactual)│
└─────────────────────────────────────────┘


### Perché questa architettura?

Gli LLM locali (anche quelli con tool calling) tendono ad **allucinare** i risultati numerici. Delegando il calcolo matematico a `pyAgrum`, otteniamo:
- ✅ **Zero allucinazioni numeriche**
- ✅ **Risultati riproducibili e deterministic**
- ✅ **Gestione elegante degli errori dell'LLM** (sanitizer + fallback)

## 🛠️ Setup

### Prerequisiti
- Python 3.10+
- Ollama installato e in esecuzione
- Almeno 8GB di RAM libera

### Installazione

```bash
# 1. Clona il progetto
cd CWProject/MUDIq2

# 2. Crea un ambiente virtuale
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# 3. Installa le dipendenze
pip install autogen-agentchat autogen-ext[openai] python-dotenv tavily-python pyagrum pandas matplotlib

# 4. Scarica il modello LLM locale (consigliato: qwen2.5:7b o phi3:mini)
ollama pull qwen2.5:7b

# 5. Configura le variabili d'ambiente (opzionale per Tavily)
# Crea un file .env con:
# TAVILY_API_KEY=tvly-tua_chiave_qui

jupyter notebook
# Apri FINAL_test.ipynb ed esegui le celle in ordine

