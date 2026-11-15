from agent_framework import Agent, AgentResponse, WorkflowBuilder  
from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureCliCredential
from tools import read_graph, cau_inference, web_search
from funtions import node_descr
import os
import transformers
from client import HuggingFaceChatClient
from huggingface_hub import InferenceClient
from agent_framework.openai import OpenAIChatCompletionClient
from azure.core.credentials import AzureKeyCredential
from dotenv import load_dotenv

load_dotenv()


#CLIENTS


#AGENTS

label_inst = (
        "You are an expert in causal relationships.\n"
        "You HAVE TO classify the user task with ONE of the following labels : backward_reasoning, intervention, coherence, influence. \n"
        "Use the following criterios to assign the label: \n "
        "-backward_reasoning: when the task is to estimate the probability of a causal node given conditional information observed on its child nodes.\n"
        "-intervention: when the task involves estimating the probability of one feature given a change made to another.\n"
        "- coherence: when the task is to understand if two conditions are compatible or conflicting.\n"   
        "-influence: when the tasks involve performing interventions to fix two variables and studying how this impacts the causal influence of one feature on another\n"
        "Your answer will be JUST THE LABEL that you chose.\n "
        "Example: \n"
        "User: 'If I observe fever, what is the probability of infection?'\n"
        "Assistant: backward_reasoning\n")

classificator = Agent(
    name= "Classificator",
    client= gpt5,
    instructions = label_inst,     
)

translator = Agent(
    name= "To_Math",
    client= gpt5,
    tools = [read_graph],
    instructions = (
        "You must rewrite the user's query in a structured dictionary format following these rules:\n"
        "- Produce a dictionary with exactly two sub-dictionaries: input and output.\n"
        f"- In output, the key must be the variable name (chosen from {node_descr}) that best represents the quantity the user is trying to infer. After the “:”, write the value to use, or 'Not necessary' .\n"
        f"- In input, include only the variables (from the same {node_descr}) that appear in the task description except the one selected as output. Each key must contain the specific value mentioned in the task, or 'Not necessary' if the value is irrelevant.\n"
        "-Do not include any variable that does not appear in the task description.\n"
        "- Return only the final dictionary, with no explanation or commentary." ),
  
)   


causal_prompt = (
    "You are an expert in causal and counterfactual inference.\n"
    "Use read_graph to interpret the causal structure provided in the context.\n"
    "Use cau_inference to perform exact causal inference and compute the final result.\n"
    "You MUST actually invoke the tools. Do not describe or simulate a tool call.\n"
    "Always pass the given feature when invoking a tool.\n"
    "After receiving the tool results, provide the final answer and a causal explanation."
)

causal_A = Agent(
        name = "Causal_Relator_Small",
        client = small,
        tools = [cau_inference, read_graph],
        instructions = causal_prompt,
    )

prompt_descr = (
    'You are an expert in car insurance',
    'You are used to justify your answers',
    'You know about causal inference',
    'Avoid examples',
    'Consider the user’s interest as generic'

)


