import pyagrum as gum
import pyagrum.causal as csl
import pandas as pd
import os
from typing import Optional
from tavily import TavilyClient
from agent_framework._tools import tool
from funtions import cobound

# CORRETTO: Istanza del client, non chiamata diretta alla classe
tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "dummy_key"))

@tool
def read_graph(path: str = None):
    if path is None or not os.path.exists(path):
        path = "https://raw.githubusercontent.com/aimacode/aima-data/master/insurance.bif"
    
    grafo = gum.loadBN(path)
    archi = grafo.arcs()
    lista = ', '.join([f"{i} ({grafo.variable(i).name()})" for i in grafo.nodes()])
    arc = ', '.join([str(a) for a in archi])
    return f'Nodi: {lista} \n Archi: {arc}'

@tool
def web_search(query: str) -> str:
    domains = [
        'https://europa.eu/youreurope/citizens/vehicles/insurance/validity/index_en.htm',
        'https://www.moneygeek.com/insurance/auto/car-insurance-basics-101/',
        'https://content.naic.org/article/what-you-should-know-about-auto-insurance-coverage',
        'https://www.geico.com/living/how-does-car-insurance-work/'
    ]
    response = tavily_client.search(query, topic='general', include_domains=domains, language='en')
    return str(response)

@tool
def cau_inference(label: str, features: str, path: Optional[str] = None, name: Optional[str] = None, surname: Optional[str] = None):
    if path is None or not os.path.exists(path):
        path = "https://raw.githubusercontent.com/aimacode/aima-data/master/insurance.bif"
    
    grafo = gum.loadBN(path)
    data = pd.read_csv('DATI.csv')
    ie = gum.LazyPropagation(grafo)
    
    dict_features = eval(features)
    input_ = dict_features.get('input', {})
    output = dict_features.get('output', {})
    
    out = list(output.keys())[0]
    out_v = list(output.values())[0]
    
    if label == 'posterior': # ALLINEATO con agents.py
        ie.setEvidence(input_) 
        ie.makeInference()
        prob = ie.posterior(out)
        var = grafo.variable(out)          
        for i, state in enumerate(var.labels()):
            if state == out_v:
                answer = f"The probability of {out} is {out_v} given the provided conditions is {round(prob[i], 3)}"
                break
                
    elif label == 'counterfactual': # TYPO CORRETTO
        x_key = list(input_.keys())[0]
        x_val = list(input_.values())[0]
        answer = cobound(out, out_v, x_key, x_val, data, grafo)
        
    elif label == 'intervention':
        do_bn = gum.BayesNet(grafo)    
        fdModele = csl.CausalModel(do_bn)
        out_vals = list(grafo.variable(out).labels())  # CORRETTO: aggiunto .labels()
        nout = len(out_vals) 
        
        input_keys = list(input_.keys())
        if len(input_keys) == 1:
            formula, impact, explanation = csl.causalImpact(fdModele, on=out, doing=input_keys[0], values=input_)
        elif len(input_keys) >= 2:
            formula, impact, explanation = csl.causalImpact(fdModele, on=out, doing=input_keys, values=input_)
        else:
            return "No input variables provided for intervention."
            
        if formula is None:
            answer = f"Non identifiable Query!\n Explanation: {explanation}"
        elif out_v == 'Not necessary':
            answer = f"The probability of {out} given the current intervention is {round(impact, 3)}" 
        else:
            found = False
            for i in range(nout):
                if out_vals[i] == out_v:
                    answer = f"The probability of {out} equal to {out_vals[i]} given the current intervention is {round(impact[i], 3)}"
                    found = True
                    break
            if not found:
                answer = f"Value {out_v} not found in possible values {out_vals}."
                
    elif label == 'coherence':
        for k, v in input_.items(): # CORRETTO: ciclo dinamico per 1, 2 o 3 evidenze
            ie.addEvidence(k, v)
        try:
            ie.makeInference()
            post_diag = ie.posterior(out)        
            var = grafo.variable(out)
            prob = 0.0
            for i, state in enumerate(var.labels()):
                if state == out_v:
                    prob = post_diag[i]
                    break
            
            THRESHOLD = 0.60
            compatible = (prob >= THRESHOLD)
            if compatible:
                answer = f"Evidences are compatible with a single {out} of {out_v} with a probability of {round(prob, 2)}"
            else:
                answer = f"Evidences are NOT strongly compatible with a single {out} of {out_v} with a probability of {round(prob, 2)}"
        except gum.InvalidEvidence as e:
            answer = f"Evidences invalid: {e}"
            
    elif label == 'influence':
        archi = grafo.arcs()
        lista = ', '.join([f"{i} ({grafo.variable(i).name()})" for i in grafo.nodes()]) 
        arc = ', '.join([str(a) for a in archi])
        prompt = (
            "If a node has a fixed value the causal relation that goes from its parents nodes to its sons nodes is blocked. "
            "If there is at least an indirect or direct path between the node under consideration and the one on which we want to understand the effects "
            "that does not contain the fixed nodes, the influence is still valid."
        )
        answer = f"Look at the graph and understand the task following this instruction: {prompt}. The nodes are {lista} and the arcs are {arc}"
    else:
        answer = f"Unknown label: {label}"
        
    return answer