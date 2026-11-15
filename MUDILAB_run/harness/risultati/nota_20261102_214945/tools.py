import pyagrum as gum
from tavily import TavilyClient
import pandas as pd
import pyagrum.causal as csl
from agent_framework._tools import tool
from funtions import node_descr
from typing import Optional
import dice_ml
from dice_ml.utils import helpers  # helper functions
import torch
from sklearn.compose import ColumnTransformer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.ensemble import RandomForestClassifier
from funtions import cobound



@tool
def read_graph(path: str):
    grafo = gum.loadBN(path)
    archi = grafo.arcs()
    lista = ''
    for i in grafo.nodes():
        lista = lista + f', {i} {grafo.variable(i).name()}' 
    arc = ''
    for a in archi:
        arc = arc + f'{a}'
    res = f'Nodi: {lista} \n Archi:{arc}'
    return res

@tool
def web_search(query:str) -> str:
    """Web search Agent"""
    return TavilyClient.search(query, topic = 'general', include_domains=['https://europa.eu/youreurope/citizens/vehicles/insurance/validity/index_en.htm','https://www.moneygeek.com/insurance/auto/car-insurance-basics-101/','https://content.naic.org/article/what-you-should-know-about-auto-insurance-coverage','https://www.geico.com/living/how-does-car-insurance-work/'], language= 'en' )

@tool
def cau_inference(label: str, features: str, path: Optional[str], name: Optional[str] = None, surname: Optional[str] = None):
    if path is None:
        path = "C:/Users/Samsung/Documents/DOTTORATO/GitHub/IPMU/IPMU/Journal/insurance_grafo.bif"
    grafo = gum.loadBN(path)
    data = pd.read_csv('DATI.csv')
    ie = gum.LazyPropagation(grafo)
    dict = eval(features)
    input_ = dict['input']
    output = dict['output']
    out = list(output.keys())[0]
    out_v = list(output.values())[0]
    
    if (label == 'backward_reasoning'):
        ie.setEvidence(input_) 
        ie.makeInference()

        prob = ie.posterior(out)
        var = grafo.variable(out)          

        for i, state in enumerate(var.labels()):
            if state == out_v:
                answer = f"The probability of {out} is {out_v} given the provided conditions is {round(prob[i],3)}"
            #print(state, prob[i])
    
    elif(label == 'conterfactual'):
        
        answer = cobound(out,  out_v, input_, list(input_.values())[0], data, grafo)
        

    elif label == 'intervention':
        do_bn = gum.BayesNet(grafo)    
        fdModele = csl.CausalModel(do_bn)
        out_vals = list(grafo.variable(out))  #possibili valori della variabile di output
        nout = len(out_vals) 
          
        if len(input_.keys()) == 1:
            formula, impact, explanation = csl.causalImpact(fdModele, on=out, doing= list(input_.keys())[0], values= input_)
                
        elif len(input_.keys()) == 2:
            formula, impact, explanation = csl.causalImpact(fdModele, on=out, doing= list(input_.keys()), values= input_)

        if formula is None:
             answer = f"Non identifiable Query!\n Explanation: {explanation}"

        if out_v == 'Not necessary':
                answer = f"The probability of {out} given the current intervention is {round(impact,3)}" 
        else:
            for i in range (0, nout):
                    if out_vals[i][1] == out_v:
                        answer = f"The probability of {out} equal to {out_vals[i][1]} given the current intervention is {round(impact[i],3)}"  
        
       
                
    elif label == 'coherence':
        ie.addEvidence(list(input_.keys())[0], list(input_.values())[0])
        if list(input_.keys()) == 2:
            ie.addEvidence(list(input_.keys())[1], list(input_.values())[1])
        elif list(input_.keys()) == 3:
            ie.addEvidence(list(input_.keys())[2], list(input_.values())[2])
        
        try:
            ie.makeInference()
        except gum.InvalidEvidence as e:
            print("Evidences invalid:", e)
            compatible = False
        else:

            post_diag = ie.posterior(out)        
            var = grafo.variable(out)
            
            for i, state in enumerate(var.labels()):
                if state == out_v:
                    prob = post_diag[i]

            THRESHOLD = 0.60
            compatible = (prob >= THRESHOLD)
        
            if compatible:
                answer = f"Evidences are compatible with a single {out} of {out_v} with a probability of {round(prob,2)}"
            else:
                answer = f"Evidences are NOT strongly compatible with a single {out} of {out_v} with a probability of {round(prob,2)}"
      

    elif label == 'influence':
        #qui al posto di fare calcoli, forse conviene di più ragionare sugli archi.
        last = list(input_.keys())[-1]
        archi = grafo.arcs()
        
        lista = ''
        for i in grafo.nodes():
            lista = lista + f', {i} {grafo.variable(i).name()}' 
        arc = ''
        for a in archi:
            arc = arc + f'{a}'

        prompt = f'If a node has a fixed value the causal relation that goes from its parents nodes to its sons nodes is blocked (no more influence). If there is at least an indirect or direct path between the node under consideration and the one on which we want to understand the effects that doeas not contain the fixed nodes, the innfluence is still valid.'
        #prompt = f'In order to provide the best answer to this task you have to understand the relationships between {list(input_.keys())[0], list(input_.keys())[1], list(input_.keys())[2]} and the {out}. If all the path between the input feature that we are questioning {list(input_.keys())[2]} and the {out} are blocked betweeen the other input features, the result is that a miskate or a change in this variable does not influence the results. If the path exists, the answer is yes.'
        answer = f'Look at the grafo and understand the task following this instruction: {prompt}. The nodes are {lista} and the arc {arc}'
    
    return answer    


#@tool
#def vector_search():
    