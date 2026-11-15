from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
from tools import read_graph, cau_inference, web_search
from funtions import node_descr
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_BASE_URL = "http://localhost:11434/v1"

custom_model_info = {
    "vision": False,
    "function_calling": True,
    "json_output": True,
    "structured_output": True,
    #"family": "llama"
    "family": "qwen"
}

gpt5 = OpenAIChatCompletionClient(
    #model="llama3.1:8b",  # o "phi3:mini" se hai poca RAM
    model="qwen2.5:7b",
    api_key="ollama",
    base_url=OLLAMA_BASE_URL,
    temperature=0.1,
    model_info=custom_model_info
)

small = OpenAIChatCompletionClient(
    #model="llama3.1:8b",
    model="qwen2.5:7b",
    api_key="ollama",
    base_url=OLLAMA_BASE_URL,
    temperature=0.0,
    model_info=custom_model_info
)

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

classificator = AssistantAgent(
    name="Classificator",
    model_client=gpt5,
    system_message=label_inst,
)

# CORRETTO: rimosso tools=[read_graph] per forzare il modello a generare solo il JSON
translator = AssistantAgent(
    name="To_Math",
    model_client=small,
    system_message=(
        "You must rewrite the user's query as a structured dictionary with exactly two keys: "
        "'input' (evidence/known facts) and 'output' (target variable to infer).\n\n"
        f"Allowed variable names: {list(node_descr.keys())}\n\n"
        "CRITICAL RULES:\n"
        "- Use EXACT variable names and EXACT state values from the allowed list.\n"
        "- DO NOT expand abbreviations (e.g., 'TwentyThou' NOT 'Twenty Thousand').\n"
        "- Return ONLY valid JSON, no explanation.\n\n"
        "PATTERN EXAMPLES (learn from these, but apply the rules to NEW queries):\n\n"
        "Example 1 (Coherence pattern):\n"
        "Query: 'Is a SubStandard driving skill compatible with an Adolescent age?'\n"
        '-> { "input": { "Age": "Adolescent" }, "output": { "DrivingSkill": "SubStandard" } }\n\n'
        "Example 2 (Driving skill pattern):\n"
        "Query: 'What is the probability of an Expert driving skill given that the driver is Senior?'\n"
        '-> { "input": { "Age": "Senior" }, "output": { "DrivingSkill": "Expert" } }\n\n'
        "Example 3 (Car damage pattern):\n"
        "Query: 'Given that the car damage is Moderate, what is the probability of a Severe accident?'\n"
        '-> { "input": { "ThisCarDam": "Moderate" }, "output": { "Accident": "Severe" } }\n\n'
        "Example 4 (Intervention with state extraction):\n"
        "Query: 'If the mileage changes to FiftyThou, what is the probability of a None damage?'\n"
        '-> { "input": { "Mileage": "FiftyThou" }, "output": { "ThisCarDam": "None" } }\n\n'
        "Example 5 (Coherence with multiple conditions):\n"
        "Query: 'Is a Wealthy socio-economic status compatible with a Luxury car model and an Excellent airbag?'\n"
        '-> { "input": { "SocioEcon": "Wealthy", "MakeModel": "Luxury" }, "output": { "Airbag": "Excellent" } }\n\n'
        "GENERAL RULES (apply to any query):\n"
        "1. 'Is X compatible with Y?' -> the variable being questioned is 'output', known facts are 'input'.\n"
        "2. 'driving skill' or 'driving quality' -> use 'DrivQuality' variable.\n"
        "3. 'damage to a car' or 'car damage' -> use 'ThisCarDam' variable.\n"
        "4. Extract states from adjectives: 'older' -> 'Older', 'severe' -> 'Severe', 'mild' -> 'Mild', 'fair' -> 'Fair'.\n"
        "5. NEVER use 'Not necessary' if a state adjective is explicitly mentioned."
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

causal_A = AssistantAgent(
    name="Causal_Relator_Small",
    model_client=small,
    tools=[cau_inference, read_graph],
    system_message=causal_prompt,
)