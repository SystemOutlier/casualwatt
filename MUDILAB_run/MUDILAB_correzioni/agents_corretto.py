# =============================================================================
# agents - Copia.py
# Copia di lavoro di MUDILAB/agents.py. L'originale della relatrice non si tocca:
# qui il codice sbagliato resta commentato, la correzione sta sotto e ogni
# blocco dice perche'.
# =============================================================================
from agent_framework import Agent, AgentResponse, WorkflowBuilder
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from tools import read_graph, cau_inference, web_search
from funtions import node_descr
import os
import transformers

# --- originale: modulo client.py mai fornito, quindi ImportError all'avvio ---
# from client import HuggingFaceChatClient
#
# FIX: la riga e' commentata. HuggingFaceChatClient non e' usato da nessun
#      agente qui sotto; se serve va scritto client.py, altrimenti
#      l'import blocca tutto il modulo prima di definire gli agenti.


from huggingface_hub import InferenceClient
from agent_framework.openai import OpenAIChatCompletionClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()


#CLIENTS
# --- originale: sezione vuota, ma gli agenti usano `gpt5` e `small` ---
# (niente codice)
# FIX 1: i due nomi esistono, altrimenti NameError alla definizione di
#        `classificator` (riga con client=gpt5) e di `causal_A` (client=small).
# FIX 2: stesso modello per i tre agenti. Ho impostato come default llama3.2:3b-instruct-q4_K_M 
_MODEL = os.getenv("MUDILAB_MODEL", "llama3.2:3b-instruct-q4_K_M")
_BASE_URL = os.getenv("MUDILAB_BASE_URL", "http://localhost:11434/v1")
_API_KEY = os.getenv("MUDILAB_API_KEY", "ollama")

small = OpenAIChatCompletionClient(model=_MODEL, base_url=_BASE_URL, api_key=_API_KEY)

# modello per classificatore e traduttore: per ora lo stesso locale
gpt5 = small

#AGENTS

# --- originale: manca 'counterfactual' fra le etichette, ma tools.py ha il ramo ---
# label_inst = (
#         "You are an expert in causal relationships.\n"
#         "You HAVE TO classify the user task with ONE of the following labels : backward_reasoning, intervention, coherence, influence. \n"
#         ...
#         "Your answer will be JUST THE LABEL that you chose.\n "
#         ...
#         "Assistant: backward_reasoning\n")
# FIX 1: aggiunta l'etichetta counterfactual: senza di essa il classificatore
#        non puo' mai instradare una query controfattuale, anche se il tool ha
#        il ramo corrispondente.
# FIX 2: richiesta esplicita di una sola parola, minuscola, senza punteggiatura:
#        nei run il modello restituiva frasi intere e poi il tool riceveva un
#        `label` che non corrispondeva a nessun ramo.
label_inst = (
        "You are an expert in causal relationships.\n"
        "You HAVE TO classify the user task with ONE of the following labels : backward_reasoning, intervention, coherence, influence, counterfactual. \n"
        "Use the following criterios to assign the label: \n "
        "-backward_reasoning: when the task is to estimate the probability of a causal node given conditional information observed on its child nodes.\n"
        "-intervention: when the task involves estimating the probability of one feature given a change made to another.\n"
        "- coherence: when the task is to understand if two conditions are compatible or conflicting.\n"
        "-influence: when the tasks involve performing interventions to fix two variables and studying how this impacts the causal influence of one feature on another.\n"
        "-counterfactual: when the task already observed an outcome and asks for the probability of a node under a different value of another node.\n"
        "Your answer will be JUST THE LABEL that you chose: one lowercase word, no punctuation, no explanation.\n "
        "Example: \n"
        "User: 'If I observe fever, what is the probability of infection?'\n"
        "Assistant: backward_reasoning\n")

classificator = Agent(
    name= "Classificator",
    client= gpt5,
    instructions = label_inst,
)

# --- originale: nessun esempio di output, e la forma non e' vincolata ---
# translator = Agent(
#     name= "To_Math",
#     client= gpt5,
#     tools = [read_graph],
#     instructions = (
#         "You must rewrite the user's query in a structured dictionary format following these rules:\n"
#         "- Produce a dictionary with exactly two sub-dictionaries: input and output.\n"
#         f"- In output, the key must be the variable name (chosen from {node_descr}) that best represents the quantity the user is trying to infer. After the “:”, write the value to use, or 'Not necessary' .\n"
#         f"- In input, include only the variables (from the same {node_descr}) that appear in the task description except the one selected as output. Each key must contain the specific value mentioned in the task, or 'Not necessary' if the value is irrelevant.\n"
#         "-Do not include any variable that does not appear in the task description.\n"
#         "- Return only the final dictionary, with no explanation or commentary." ),
# )
# FIX 1: 'output' deve essere un dizionario con UNA chiave, non una stringa.
#        Osservato nei run: {"output": "Not necessary"} -> 'str' object has no
#        attribute 'keys'. Ora la regola e' scritta e c'e' un esempio.
# FIX 2: JSON con virgolette doppie, cosi' l'output si legge con json.loads
#        senza eval; niente blocchi di codice markdown attorno.
# FIX 3: i valori devono essere etichette esistenti nel grafo (node_descr le
#        elenca): un valore inventato non e' evidenza valida.
translator = Agent(
    name= "To_Math",
    client= gpt5,
    tools = [read_graph],
    instructions = (
        "Answer with ONE JSON object and nothing else: no tool call, no markdown, no explanation.\n"
        "You must rewrite the user's query in a structured dictionary format following these rules:\n"
        "- Produce a dictionary with exactly two sub-dictionaries: input and output.\n"
        f"- In output, the key must be the variable name (chosen from {node_descr}) that best represents the quantity the user is trying to infer. After the “:”, write the value to use, or 'Not necessary' .\n"
        f"- In input, include only the variables (from the same {node_descr}) that appear in the task description except the one selected as output. Each key must contain the specific value mentioned in the task, or 'Not necessary' if the value is irrelevant.\n"
        "-Do not include any variable that does not appear in the task description.\n"
        "- 'output' must be a dictionary with exactly ONE key: the variable name. Never write a plain string as 'output'.\n"
        "- Use only values that appear in the description of the variable. Never invent a value.\n"
        "- If you call read_graph, wait for its result and then answer with the JSON. Never answer with a tool call.\n"
        "- Write valid JSON: double quotes, no markdown, no code fences, no explanation before or after.\n"
        "Example of the expected answer:\n"
        '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}\n'),
)

# --- originale: non dice come passare label e features al tool ---
# causal_prompt = (
#     "You are an expert in causal and counterfactual inference.\n"
#     "Use read_graph to interpret the causal structure provided in the context.\n"
#     "Use cau_inference to perform exact causal inference and compute the final result.\n"
#     "You MUST actually invoke the tools. Do not describe or simulate a tool call.\n"
#     "Always pass the given feature when invoking a tool.\n"
#     "After receiving the tool results, provide the final answer and a causal explanation."
# )
# FIX: `cau_inference` ha bisogno di (label, features) esatti. Il prompt dice da
#      dove prenderli e impone di riportare l'output del tool com'e', invece di
#      ricalcolarlo o raccontarlo.
causal_prompt = (
    "You are an expert in causal and counterfactual inference.\n"
    "Use read_graph to interpret the causal structure provided in the context.\n"
    "Use cau_inference to perform exact causal inference and compute the final result.\n"
    "The user message contains 'label:' and 'features:': pass both to cau_inference exactly as they are, no reformatting.\n"
    "When you call read_graph, pass no path: its default is the insurance graph.\n"
    "You MUST actually invoke the tools. Do not describe or simulate a tool call.\n"
    "Always pass the given feature when invoking a tool.\n"
    "After receiving the tool results, report the number returned by cau_inference as it is, then add the causal explanation."
)

causal_A = Agent(
        name = "Causal_Relator_Small",
        client = small,
        tools = [cau_inference, read_graph],
        instructions = causal_prompt,
    )

# --- originale: tupla, non stringa ---
# prompt_descr = (
#     'You are an expert in car insurance',
#     'You are used to justify your answers',
#     'You know about causal inference',
#     'Avoid examples',
#     'Consider the user’s interest as generic'
# )
# FIX: una tupla non e' testo da passare a un modello: le righe si uniscono con \n.
prompt_descr = "\n".join((
    'You are an expert in car insurance',
    'You are used to justify your answers',
    'You know about causal inference',
    'Avoid examples',
    'Consider the user’s interest as generic',
))
