from agent_framework import Agent, AgentResponse, WorkflowBuilder
from agent_framework.openai import OpenAIChatCompletionClient
from tools import read_graph, cau_inference, web_search
from funtions import node_descr
import os
from dotenv import load_dotenv

load_dotenv()

# =====================================================================
# CLIENTS OLLAMA: Endpoint locale. NESSUNA API KEY OpenAI richiesta.
# Assicurati che Ollama sia in esecuzione e di aver scaricato il modello.
# =====================================================================
OLLAMA_BASE_URL = "http://localhost:11434/v1"

# Modello per il classificatore (richiede buon ragionamento)
# Usa "qwen2.5:7b" se hai RAM a sufficienza, altrimenti "phi3:mini"
gpt5 = OpenAIChatCompletionClient(
    model="qwen2.5:7b",
    api_key="ollama",              # Stringa fittizia, Ollama la ignora
    base_url=OLLAMA_BASE_URL,
    temperature=0.2
)

# Modello per il translator (richiede precisione JSON assoluta)
small = OpenAIChatCompletionClient(
    model="qwen2.5:7b",
    api_key="ollama",
    base_url=OLLAMA_BASE_URL,
    temperature=0.0  # Temperatura 0 per massimizzare la precisione del JSON
)

# =====================================================================
# AGENTS
# =====================================================================
label_inst = (
 "You are an expert in causal inference. Classify the user's task into "
 "EXACTLY ONE of these four labels: posterior, intervention, coherence, counterfactual.\n\n "
 "Definitions:\n "
 "- posterior: Estimate the probability of a variable given observed evidence on other "
 "variables (pure observation, no changes proposed). Corresponds to P(Y | X=x).\n "
 "- intervention: Estimate the probability of a variable after an action forces another "
 "variable to a value, breaking its normal causes (do-operator). Corresponds to P(Y | do(X=x)).\n "
 "- coherence: Determine whether two or more stated conditions are jointly compatible or "
 "contradictory, without asking for a probability.\n "
 "- counterfactual: Estimate the probability or likelihood of an alternative outcome that "
 "would have occurred under different circumstances, given what actually happened.\n\n "
 "Disambiguation rules:\n "
 "- If the question describes something actively changed/forced/set, choose intervention, "
 "not posterior.\n "
 "- If the question refers to a hypothetical past ('had X been different', 'if it had...'), "
 "choose counterfactual, not intervention.\n "
 "- If the question asks only whether two facts can hold together, not their probability, "
 "choose coherence.\n\n "
 "Output format: respond with ONLY the label, lowercase, no punctuation, no explanation."
)

classificator = Agent(
    name="Classificator",
    client=gpt5,
    instructions=label_inst,
)

translator = Agent(
    name="To_Math",
    client=small,
    tools=[read_graph],
    instructions=(
     "You must rewrite the user's query as a structured dictionary with exactly two keys: "
     "'input' and 'output'.\n\n "
     f"Allowed variable names (use these EXACT names, chosen from: {list(node_descr.keys())}):\n\n "
     "Rules for 'output':\n "
     "- Contains exactly ONE key: the variable name that best represents the quantity the user "
     "is trying to infer.\n "
     "- Its value is the specific value mentioned in the task, if any, otherwise 'Not necessary'.\n\n "
     "Rules for 'input':\n "
     "- Contains every other variable (from the same allowed list) that appears in the task "
     "description, excluding the one selected as output.\n "
     "- For each, the value is the specific value mentioned in the task, or 'Not necessary' if "
     "the task names the variable but not a specific value.\n "
     "- Do not include any variable that does not appear in the task description.\n\n "
     "Output format:\n "
     "- Return ONLY the final dictionary as valid JSON, with no explanation or commentary.\n\n "
     "Example:\n "
     "Task: Given that the driving quality is normal, how likely is it that the age of the driver is senior?\n "
     '{ "input": { "DrivQuality": "Normal" }, "output": { "Age": "Senior" } }'
    )
)

causal_prompt = (
    "You are an expert in causal and counterfactual inference. You have access to these tools:\n"
    "- read_graph: retrieves the causal graph structure.\n"
    "- cau_inference: performs exact causal inference and returns a numerical or symbolic result.\n\n"
    "Procedure, to follow in order for every task:\n"
    "1. Call cau_inference, passing the label and the dictionary of variables/values exactly as "
    "given. Do not modify, rename, or drop any key from the dictionary.\n"
    "2. You MUST actually invoke the tool — never write out, describe, or simulate what a "
    "tool would return.\n"
    "3. If a tool call fails or returns an error, report the error explicitly.\n\n"
    "Final answer format:\n"
    "1. State the numerical/symbolic result from cau_inference.\n"
    "2. Give a short causal explanation (2-4 sentences) of why this result."
)

causal_A = Agent(
    name="Causal_Relator_Small",
    client=small,
    tools=[cau_inference, read_graph],
    instructions=causal_prompt,
)