import pyagrum as gum
import pyagrum.causal as csl
import pandas as pd
import os
from typing import Optional
from tavily import TavilyClient
from funtions import cobound

tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY", "dummy_key"))

def sanitize_llm_output(input_dict, output_dict):
    """Corregge automaticamente gli errori di formattazione più comuni dell'LLM"""
    value_mapping = {
        "Mild Severity": "Mild",
        "Twenty Thousand": "TwentyThou",
        "Twenty Thousand Dollars": "TwentyThou",
        "Hundred Thousand": "HundredThou",
        "HundredThousand": "HundredThou"
    }
    for d in [input_dict, output_dict]:
        for key, val in d.items():
            if val in value_mapping:
                d[key] = value_mapping[val]
    return input_dict, output_dict

def validate_and_clean_dict(input_dict, output_dict, grafo):
    """VALIDAZIONE UNIVERSALE: Rimuove chiavi/valori allucinati dall'LLM"""
    valid_nodes = [grafo.variable(i).name() for i in grafo.nodes()]
    clean_input, clean_output = {}, {}
    
    for d, clean_d in [(input_dict, clean_input), (output_dict, clean_output)]:
        for k, v in d.items():
            if k in valid_nodes:
                labels = grafo.variable(k).labels()
                if v in labels or v == 'Not necessary':
                    clean_d[k] = v
                else:
                    print(f"[WARNING] Valore '{v}' non valido per {k}. Ignorato.")
            else:
                print(f"[WARNING] Variabile '{k}' non trovata nel grafo. Ignorata.")
    return clean_input, clean_output

def read_graph(path: str = "insurance_grafo.bif"):
    """Retrieves the causal graph structure"""
    if os.path.exists("insurance_grafo.bif"):
        path = "insurance_grafo.bif"
    try:
        grafo = gum.loadBN(path)
    except Exception as e:
        return f"ERRORE CRITICO: Impossibile caricare il grafo. Dettaglio: {e}"
    archi = grafo.arcs()
    lista = ', '.join([f"{i} ({grafo.variable(i).name()})" for i in grafo.nodes()])
    arc = ', '.join([str(a) for a in archi])
    return f'Nodi: {lista} \n Archi: {arc}'

def web_search(query: str) -> str:
    """Web search Agent"""
    domains = ['https://www.geico.com/living/how-does-car-insurance-work/']
    try:
        response = tavily_client.search(query, topic='general', include_domains=domains, language='en')
        return str(response)
    except Exception as e:
        return f"Web search fallita: {e}"

def cau_inference(label: str, features: str, path: str = "insurance_grafo.bif", name: Optional[str] = None, surname: Optional[str] = None):
    """Performs exact causal inference"""
    if os.path.exists("insurance_grafo.bif"):
        path = "insurance_grafo.bif"
    try:
        grafo = gum.loadBN(path)
    except Exception as e:
        return f"ERRORE CRITICO: Impossibile caricare il grafo. Dettaglio: {e}"
    
    data = pd.read_csv('DATI.csv')
    ie = gum.LazyPropagation(grafo)
    
    try:
        dict_features = eval(features)
    except Exception as e:
        return f"ERRORE: Formato features non valido. Dettaglio: {e}"
        
    input_ = dict_features.get('input', {})
    output = dict_features.get('output', {})
    
    # 1. Sanitizza
    input_, output = sanitize_llm_output(input_, output)
    # 2. Valida universalmente
    input_, output = validate_and_clean_dict(input_, output, grafo)
    
    if not output:
        return "ERRORE: Nessuna variabile di output valida trovata dopo la pulizia."
        
    out = list(output.keys())[0]
    out_v = list(output.values())[0]
    
    if label == 'posterior':
        ie.setEvidence(input_) 
        ie.makeInference()
        prob = ie.posterior(out)
        var = grafo.variable(out)
        answer = f"ERRORE: Il valore '{out_v}' non è valido per {out}. Stati ammessi: {var.labels()}"
        for i, state in enumerate(var.labels()):
            if state == out_v:
                answer = f"The probability of {out} is {out_v} given the provided conditions is {round(prob[i], 3)}"
                break
                
    elif label == 'counterfactual':
        x_key = list(input_.keys())[0]
        x_val = list(input_.values())[0]
        answer = cobound(out, out_v, x_key, x_val, data, grafo)
        
    elif label == 'intervention':
        do_bn = gum.BayesNet(grafo)    
        fdModele = csl.CausalModel(do_bn)
        out_vals = list(grafo.variable(out).labels())
        nout = len(out_vals) 
        input_keys = list(input_.keys())
        
        formula, impact, explanation = csl.causalImpact(
            fdModele, 
            on=out, 
            doing=input_keys[0] if len(input_keys) == 1 else input_keys, 
            values=input_
        )
            
        if formula is None:
            answer = f"Non identifiable Query!\n Explanation: {explanation}"
        else:
            impact_array = impact.toarray() if hasattr(impact, 'toarray') else impact
            if out_v == 'Not necessary':
                answer = f"The intervention on {input_keys} has been applied."
            else:
                found = False
                for i in range(nout):
                    if out_vals[i] == out_v:
                        answer = f"The probability of {out} equal to {out_vals[i]} given the current intervention is {round(float(impact_array[i]), 3)}"
                        found = True
                        break
                if not found:
                    answer = f"Value {out_v} not found in possible values {out_vals}."
                    
    elif label == 'coherence':
        if out_v == 'Not necessary' and len(input_) > 0:
            out = list(input_.keys())[0]
            out_v = input_[out]
            input_for_eval = {k: v for k, v in input_.items() if k != out}
        else:
            input_for_eval = input_

        for k, v in input_for_eval.items():
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
            if prob >= THRESHOLD:
                answer = f"Evidences are compatible with {out} being {out_v} with a probability of {round(prob, 2)}"
            else:
                answer = f"Evidences are NOT strongly compatible with {out} being {out_v} with a probability of {round(prob, 2)}"
        except gum.InvalidEvidence as e:
            answer = f"Evidences invalid: {e}"
    else:
        answer = f"Unknown label: {label}"
        
    return answer