import re
import pandas as pd
import pyagrum.causal.notebook as cslnb
import pyagrum.causal as csl

dati = pd.read_csv('DATI.csv')
names = dati['Name'].to_list()
surnames = dati['Surnames'].to_list()

def pulisci_output(l:str):
    l = l.replace("\n", "")
    l = l.replace("python", "")
    l = l.replace("`", "")
    l = re.sub(r"\(node ([1-9][0-9]?)\s*\)", "", l)
    return l

node_descr = nodes_descr = {"name": "description and values of the feature.","GoodStudent": "with academic results or not. Values: True, False", "Age": "Values: Adolescent, Adult, Senior", 
"SocioEcon": "socio-economic status. Values: Prole, Middle, UpperMiddle, Wealthy", "RiskAversion": "Values: Psychopath, Adventurous, Normal, Cautious",
"VehicleYear": "vehicle age. Values: Current, Older", "ThisCarDam": "damage to this car. Values: None, Mild, Moderate, Severe", 
"RuggedAuto": "ruggedness of the car. Values: EggShell, Football, Tank", "Accident": "severity of the accident. Values: None, Mild, Moderate, Severe", 
"MakeModel": "car's model. Values: SportsCar, Economy, FamilySedan, Luxury, SuperLuxury", "DrivQuality": "driving quality. Values: Poor, Normal, Excellent", 
"Mileage": "FiveThou, TwentyThou, FiftyThou, Domino", "Antilock": "True, False", "DrivingSkill": "SubStandard, Normal, Expert", "SeniorTrain":"seniority training. Values: True, False",
"ThisCarCost": "osts for the insured car. Values: Thousand, TenThou, HundredThou, Million", "Theft": "True', 'False", "CarValue": "value of the car. Values: FiveThou, TenThou, TwentyThou, FiftyThou, Million", 
"HomeBase": "neighbourhood type. Values: Secure, City, Suburb, 'Rural", "AntiTheft": "anti-theft system. Values: True, False", 
"PropCost": "ratio of the cost for the two cars. Values: Thousand, TenThou, HundredThou, Million", "OtherCarCost": "Thousand, TenThou, HundredThou, Million",
"OtherCar": "True, False", "MedCost": "Thousand, TenThou, HundredThou, Million", "Cushioning": "Poor, Fair, Good, Excellent",
"Airbag": "True', 'False", "ILiCost": "inspection cost. Values: Thousand, TenThou, HundredThou, Million", "DrivHist": "driving history. Values: Zero, One, Many"}

import pyro
import pyro.distributions as dist
import torch
import pyagrum as gum

def complex_prob(df,grafo, y, yval, x, nox, j = None, jval = None, z = None, zval= None):
    ie = gum.LazyPropagation(grafo)
    labels = grafo.variable(x).labels()
    den = 0
    n2 = []
    ie.setEvidence({j: jval, z:zval})
    for i, o in enumerate(labels):
        if o in nox:
            tden = ie.posterior(x)[i]
            n2.append(tden)
            den = den + tden
        
    num = 0
    
    for i,p in enumerate(nox):
        n1 = df[(df[x] == p) & (df[j] == jval) & (df[z] == zval)][y][yval].values[0]
        tnum = n1*n2[i]
        num = num + tnum
    
    answ= num/den
    
    return answ

# la funzione può essere per una sola variabile e può essere chiamata due volte con due grafi diversi...
def g_bin(grafo, x, xval, nox):
    
    new_bn = gum.BayesNet(grafo)                               #copia del grafo
    id_x = new_bn.idFromName(x)                                #id variabile
    id_childx = new_bn.children(id_x)                          # ids nodi figli (serve perchè bisogna aggiustare le loro cpt)
    id_pax = new_bn.parents(id_x)                              # ids nodi padri
            
    #binarizzare i nodi
    new_bn.erase(x)                                            #cancellare vecchio nodo
    new_bn.add(gum.LabelizedVariable(x, x, ["0", "1"]))        #aggiungerne uno binario con lo stesso nome
        
        #add arcs sons and fathers
    for i in id_childx: 
        new_bn.addArc(x,new_bn.variable(i).name())              # ricreare gli archi del grafo originario (gli id rimangono invariati)
    for i in id_pax: 
        new_bn.addArc(new_bn.variable(i).name(),x)
    
        
        #change the cpt of x and y
    cptx = grafo.cpt(x)                                         #prendere la cpt di partenza
    cptx = cptx.topandas()                                          
    new_x = pd.DataFrame(index=cptx.index)                        
    new_x[("1")] = cptx[(x, xval)]                             #binarizzare con 1 = valore di interesse e 0 = tutti gli altri
    new_x[("0")] = sum(cptx[(x, s)] for s in nox)              #le probabilà in 0 sono le somme delle probabilità dei valori in 0 contenuti
    new_x.columns = pd.MultiIndex.from_tuples([(x, '1'),(x, '0')])    #sistemare gli indici
    cptnew = new_bn.cpt(x)    
    
    for idx, row in new_x.iterrows():
        parent_vals = {name: str(val) for name, val in zip(new_x.index.names, idx)}
    
        for child_label, prob in row.items():
            #print(child_label[1])
            full_key = {**parent_vals, x: str(child_label[1])}
            cptnew[full_key] = float(prob)                                  #--> FUNZIONA, top!
        
                                
    
        #fix the cpt of sons
    for i in id_childx:
        child = new_bn.variable(i).name()
        genitori_id = new_bn.parents(i)  # set di interi
        cols = [new_bn.variable(id).name() for id in genitori_id]
        v = grafo.cpt(child)                                   # tieni il riferimento, NON riassegnare v
        df = v.topandas()
        df = df.reset_index()
        #df[x] = (df[x] == xval).astype(int)
        #df = df.set_index(col)
        newcpt = new_bn.cpt(child)
        dim = len(cols)
        yvals = list(df.columns.get_level_values(1)[dim:])
        
        if dim != 1:
            col_nox = [item for item in cols if item != x]
            vvals = df[col_nox[0]].unique() 
            for n in vvals:
                if dim == 3:
                    vvals2 = df[col_nox[1]].unique() 
                    for m in vvals2:
                        for idx, row in df.iterrows():
                            for yy in yvals:
                                for child_label, val in row.items():
                                    key = {x: 0, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newval = complex_prob(df ,grafo ,child , yy, x, nox, col_nox[0], n, col_nox[1], m)
                                    newcpt[key] = float(newval)
                                    key = {x: 1, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    keyold = {x: xval, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newcpt[key] = v[keyold]
                                    
                                    
                elif dim == 2:
                    for idx, row in df.iterrows():
                            for yy in yvals:
                                for child_label, val in row.items():
                                    key = {x: 0, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newval = complex_prob(df ,grafo ,child , yy, x, nox, col_nox[0], n, col_nox[1], m)
                                    newcpt[key] = float(newval)
                                    key = {x: 1, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    keyold = {x: xval, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newcpt[key] = v[keyold]
    
        elif dim == 1:
            for idx, row in df.iterrows():
                            for yy in yvals:
                                for child_label, val in row.items():
                                    key = {x: 0, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newval = complex_prob(df ,grafo ,child , yy, x, nox, col_nox[0], n, col_nox[1], m)
                                    newcpt[key] = float(newval)
                                    key = {x: 1, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    keyold = {x: xval, col_nox[0]: n, col_nox[1]: m, child: yy}
                                    newcpt[key] = v[keyold]
                
            
#FUNZIONAAAAAAAAAAAAAAAA          # scrive DIRETTAMENTE nella CPT della rete
    
    return new_bn



def cobound(y, yval, x, xval, data, graph):                        
    y_vals = list(graph.variable(y).labels())
    
    x_vals = list(graph.variable(x).labels())   
    copyx =  x_vals.copy()
    copyy = y_vals.copy()
    copyx.remove(xval)
    nox = copyx
    copyy.remove(yval)
    noy = copyy
    bind = data[[y,x]]
    bind[x] = (bind[x] == xval).astype(int)
    bind[y] = (bind[y] == yval).astype(int)
    bingraph = g_bin(graph, x, xval, nox)
    bingraph = g_bin(bingraph, y, yval, noy)
    do_g = gum.BayesNet(bingraph)
    mod = csl.CausalModel(do_g)
    
    formula, imp, explanation = csl.causalImpact(mod, on=y, doing=x, values = {x: 1})
    print(f'imp: {imp[1]}')
    PYx = round(imp[1],3)                                              #PYx
    #print(f'probability {PYx}')
    ny = data[data[y] == yval].shape[0]
    Py = ny/data.shape[0]                                                      #Py
    
    formula2, imp2 , explanation2 = csl.causalImpact(mod, on=y, doing=x, values = {x: 0})
    PYnox = round(imp2[1],3)                                           #PYnox
    low_B = max(0, PYx-PYnox, Py-PYnox, PYx-Py)

    ie = gum.LazyPropagation(bingraph)
    ie.makeInference()
    joint = ie.jointPosterior({x,y})   # Potential congiunto su X,Y
    p_xy = joint[{x: 1, y: 1}]
    p_noxy = joint[{x: 0, y: 0}]
    Pxny = joint[{x: 1,y: 0}]                                              #Pxny
    Pnxy = joint[{x:0, y: 1}]            #Pnxy

    upper_B = min(PYx, 1-PYnox, p_xy+ p_noxy, PYx - PYnox + Pxny +Pnxy) 

    answer = f'The answer is between {round(low_B,4)} and {round(upper_B,4)}'
    
    return answer