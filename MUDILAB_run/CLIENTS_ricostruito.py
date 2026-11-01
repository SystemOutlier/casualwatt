# =============================================================================
# CLIENTS_ricostruito.py
#
# Ricostruzione del blocco `#CLIENTS` di MUDILAB/agents.py. Nell'originale della
# relatrice quel blocco e' vuoto (agents.py:17) e sotto gli agenti usano due nomi
# che nessuno definisce:
#
#   agents.py:37  classificator ... client= gpt5
#   agents.py:43  translator    ... client= gpt5   (+ tools=[read_graph], :44)
#   agents.py:67  causal_A      ... client = small (+ tools=[cau_inference, ...])
#
# Effetto misurato il 28-10-2026: il modulo muore con
#   NameError: name 'gpt5' is not defined
# alla definizione di `classificator`, cioe' prima di importare gli agenti, prima
# di qualunque query. Quindi mancano DUE cose indipendenti: il file `client.py`
# (agents.py:8) e questo blocco.
#
# Questo file NON e' un modulo da importare e non e' stato eseguito: contiene due
# varianti, una ipotetica e una eseguibile, entrambe commentate. MUDILAB/ non e'
# stato toccato (agents.py md5 6c465fe23bae577c0dc968ffcdc93d5e, invariato).
# Non e' dentro lo zip: il pacchetto per la relatrice e' invariato.
# =============================================================================


# -----------------------------------------------------------------------------
# 0. COSA DICONO GLI IMPORT (verificato il 29-10-2026)
# -----------------------------------------------------------------------------
#
# agents.py importa sette nomi e non ne usa NESSUNO fuori dal blocco vuoto
# `#CLIENTS`: sono le tracce di com'era scritto. In ordine:
#
#   agents.py:2   FoundryChatClient        -> per gpt5, via Microsoft Foundry
#   agents.py:3   AzureCliCredential       -> l'autenticazione dell'utente Azure
#   agents.py:8   HuggingFaceChatClient    -> il file mai fornito, per small
#   agents.py:9   InferenceClient          -> cosa avvolgeva quel file
#   agents.py:10  OpenAIChatCompletionClient -> alternativa OpenAI-compatibile
#   agents.py:11  AzureKeyCredential       -> vedi nota sotto: inutilizzabile
#   agents.py:12  load_dotenv (:14)        -> i nomi dei modelli stavano nel .env
#
# Nota su AzureKeyCredential (agents.py:11): nel framework installato il
# parametro `credential` dei due chat client accetta solo credenziali Entra,
#   AzureCredentialTypes = TokenCredential | AsyncTokenCredential
#   (agent_framework_foundry/_chat_client.py:89, :181 e
#    agent_framework_openai/_chat_completion_client.py:103)
# e nessun file di `agent_framework_openai` nomina AzureKeyCredential; l'unico
# posto che lo usa e' FoundryEmbeddingClient (agent_framework_foundry/
# _embedding_client.py:28, :166), che qui non c'entra. Quindi quell'import o
# viene da una versione diversa del framework o e' un residuo: non entra in
# nessuna delle due varianti sotto.


# -----------------------------------------------------------------------------
# A. RICOSTRUZIONE STORICA (ipotesi) — com'era probabilmente nella sua sessione
# -----------------------------------------------------------------------------
#
# Da leggere come ipotesi, non come copia: la firma di HuggingFaceChatClient non
# e' ricostruibile (del file non c'e' traccia ne' nel repo ne' nel notebook).
#
# from agent_framework.foundry import FoundryChatClient          # agents.py:2
# from azure.identity import AzureCliCredential                 # agents.py:3
# from client import HuggingFaceChatClient                      # agents.py:8
# import os
#
# # [VERIFICATO] il client installato legge davvero queste due variabili, e le
# # esige: senza, ValueError a _chat_client.py:222 e :229.
# #   FOUNDRY_PROJECT_ENDPOINT  agent_framework_foundry/_chat_client.py:107
# #   FOUNDRY_MODEL             agent_framework_foundry/_chat_client.py:109
# # [IPOTESI] che le sue si chiamassero cosi': il .env non e' stato fornito.
# # [IPOTESI] che "gpt5" fosse il nome del *deployment* nel progetto Foundry:
# # il parametro si chiama `model` ed e' un nome di deployment, non un modello.
# gpt5 = FoundryChatClient(
#     project_endpoint=os.getenv("FOUNDRY_PROJECT_ENDPOINT"),
#     model=os.getenv("FOUNDRY_MODEL"),
#     credential=AzureCliCredential(),   # az login: e' un TokenCredential, ok
# )
#
# # [IPOTESI] `small` era un modello piccolo su Hugging Face, avvolto da client.py
# # in un BaseChatClient. Il nome non si sa; il notebook (MUDILAB/FINAL.ipynb,
# # cella 8) indica PHI-4-MINI-INSTRUCT e 4o-mini come "small machine", la cella 7
# # dichiara il disegno "_Small Machine + Better Process_ > _Big Machine_".
# # [VERIFICATO] in huggingface_hub 2.2.0 InferenceClient accetta
# #   (model, provider, token, timeout, headers, cookies, bill_to, base_url, api_key)
# small = HuggingFaceChatClient(
#     model=os.getenv("HUGGINGFACE_MODEL"),
#     token=os.getenv("HUGGINGFACE_TOKEN"),
# )
#
# Perche' questa variante non e' eseguibile qui: `gpt5` richiede un progetto
# Foundry e un `az login` (agents.py:3), `small` richiede client.py e un token HF.
# Nessuna delle due cose esiste su questa macchina; il run si fermerebbe prima
# della prima query, come si e' fermato con gli originali.


# -----------------------------------------------------------------------------
# B. VARIANTE ESEGUIBILE QUI — due modelli locali, stessi due ruoli
# -----------------------------------------------------------------------------
#
# Questa e' quella da incollare sotto `#CLIENTS` in agents_corretto.py, al posto
# delle righe attuali. Differenza sostanziale rispetto a oggi:
#
#   oggi:   small = OpenAIChatCompletionClient(...); gpt5 = small
#   sotto:  small e gpt5 sono due client distinti, quindi due modelli distinti
#
# Ripristina il disegno della relatrice (due ruoli, un modello piccolo per
# l'agente causale, uno piu' capace per classificatore e traduttore), che con
# `gpt5 = small` collassa su un solo modello. Entrambi i modelli devono esistere
# in Ollama e dichiarare la capability `tools`: il traduttore ha tools=[read_graph]
# (agents.py:44), e con un modello senza tool Ollama risponde 400 gia' al primo
# passo (tinyllama:latest, misurato il 28-10-2026).
#
# import os
# from agent_framework.openai import OpenAIChatCompletionClient
#
# _BASE_URL = os.getenv("MUDILAB_BASE_URL", "http://localhost:11434/v1")
# _API_KEY = os.getenv("MUDILAB_API_KEY", "ollama")
#
# # gpt5 = il ruolo "modello capace" (classificatore e traduttore)
# _MODEL_BIG = os.getenv("MUDILAB_MODEL_BIG", "llama3.1:8b")
# # small = il ruolo dell'agente che si chiama Causal_Relator_Small (agents.py:66)
# _MODEL_SMALL = os.getenv("MUDILAB_MODEL_SMALL", "llama3.2:3b-instruct-q4_K_M")
#
# small = OpenAIChatCompletionClient(
#     model=_MODEL_SMALL, base_url=_BASE_URL, api_key=_API_KEY)
# gpt5 = OpenAIChatCompletionClient(
#     model=_MODEL_BIG, base_url=_BASE_URL, api_key=_API_KEY)
#
# Nota sui due modelli: la scelta dei nomi e' un parametro, non una conclusione.
# Nella campagna del 29-10-2026 nessun modello locale disponibile ha chiuso i tre
# passi con il numero corretto; `llama3.1:8b` e' quello che segue meglio il
# protocollo dei tool ma inventa il `path` di `read_graph` (14/15 run), e
# `llama3.2:3b` sbaglia l'etichetta. Questa variante serve a misurare il costo
# energetico del suo disegno a due modelli, non a dichiararlo funzionante.


# -----------------------------------------------------------------------------
# C. COSA RESTA NON RICOSTRUIBILE, E COSA CHIEDERE
# -----------------------------------------------------------------------------
#
# Non ricostruibile per assenza di evidenza:
#   - la firma di HuggingFaceChatClient (argomenti, streaming, retry);
#   - se `gpt5` fosse un deployment Foundry o un endpoint OpenAI-compatibile:
#     gli import :2 e :10 sono due alternative per lo stesso ruolo, e non c'e'
#     modo di sapere quale fosse attiva;
#   - i nomi delle variabili nel .env (per Foundry valgono FOUNDRY_MODEL e
#     FOUNDRY_PROJECT_ENDPOINT solo perche' li legge il client, non perche'
#     compaiano in agents.py);
#   - il modello HF dietro `small`.
#
# Da chiedere a lei, in ordine di importanza:
#   1. client.py: e' suo o veniva da un esempio? Va fornito, altrimenti
#      l'import a agents.py:8 blocca il modulo prima di tutto il resto.
#   2. i due modelli veri: quali erano, e con quale criterio erano divisi fra
#      classificatore/traduttore e agente causale.
#   3. se `AzureKeyCredential` (agents.py:11) serviva a qualcosa o e' un residuo.
#
# Perche' conta per la misura: il costo per token di un modello 8B non e'
# confrontabile con quello di un 3B, e la divisione dei ruoli decide quanti
# token passano da ciascuno dei due. Ricostruire il blocco con lo stesso modello
# per tutti gli agenti cambierebbe la grandezza misurata, non solo il risultato.
