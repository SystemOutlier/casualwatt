import re
import pandas as pd
import pyagrum as gum
import pyagrum.causal as csl

dati = pd.read_csv('DATI.csv')
names = dati['Name'].to_list()
surnames = dati['Surnames'].to_list()

def pulisci_output(l: str):
    l = l.replace("\n ", " ")
    l = l.replace("python ", " ")
    l = l.replace("`", " ")
    l = re.sub(r"(node ([1-9][0-9]?)\s*)", " ", l)
    return l

# Dizionario PULITO: nessuno spazio finale, nomi esatti del file .bif
node_descr = {
    "GoodStudent": "with academic results or not. Values: True, False",
    "Age": "Values: Adolescent, Adult, Senior",
    "SocioEcon": "socio-economic status. Values: Prole, Middle, UpperMiddle, Wealthy",
    "RiskAversion": "Values: Psychopath, Adventurous, Normal, Cautious",
    "VehicleYear": "vehicle age. Values: Current, Older",
    "ThisCarDam": "damage to this car. Values: None, Mild, Moderate, Severe",
    "RuggedAuto": "ruggedness of the car. Values: EggShell, Football, Tank",
    "Accident": "severity of the accident. Values: None, Mild, Moderate, Severe",
    "MakeModel": "car's model. Values: SportsCar, Economy, FamilySedan, Luxury, SuperLuxury",
    "DrivQuality": "driving quality. Values: Poor, Normal, Excellent",
    "Mileage": "Values: FiveThou, TwentyThou, FiftyThou, Domino",
    "Antilock": "Values: True, False",
    "DrivingSkill": "Values: SubStandard, Normal, Expert",
    "SeniorTrain": "seniority training. Values: True, False",
    "ThisCarCost": "costs for the insured car. Values: Thousand, TenThou, HundredThou, Million",
    "Theft": "Values: True, False",
    "CarValue": "value of the car. Values: FiveThou, TenThou, TwentyThou, FiftyThou, Million",
    "HomeBase": "neighbourhood type. Values: Secure, City, Suburb, Rural",
    "AntiTheft": "anti-theft system. Values: True, False",
    "PropCost": "ratio of the cost for the two cars. Values: Thousand, TenThou, HundredThou, Million",
    "OtherCarCost": "Values: Thousand, TenThou, HundredThou, Million",
    "OtherCar": "Values: True, False",
    "MedCost": "Values: Thousand, TenThou, HundredThou, Million",
    "Cushioning": "Values: Poor, Fair, Good, Excellent",
    "Airbag": "Values: True, False",
    "ILiCost": "inspection cost. Values: Thousand, TenThou, HundredThou, Million",
    "DrivHist": "driving history. Values: Zero, One, Many"
}

def complex_prob(data_df, grafo, y, yval, x, nox, **kwargs):
    ie = gum.LazyPropagation(grafo)
    valid_evidence = {k: v for k, v in kwargs.items() if v is not None}
    if valid_evidence:
        ie.setEvidence(valid_evidence)
    
    labels = grafo.variable(x).labels()
    den = 0
    n2 = []
    for i, o in enumerate(labels):
        if o in nox:
            tden = ie.posterior(x)[i]
            n2.append(tden)
            den += tden
            
    num = 0
    for i, p in enumerate(nox):
        condition = (data_df[x] == p)
        for k, v in kwargs.items():
            if v is not None:
                condition = condition & (data_df[k] == v)
        
        subset = data_df[condition]
        n1 = (subset[y] == yval).mean() if len(subset) > 0 else 0.0
        num += n1 * n2[i]
        
    return num / den if den > 0 else 0.0

def g_bin(grafo, x, xval, nox, data_df):
    new_bn = gum.BayesNet(grafo)
    id_x = new_bn.idFromName(x)
    id_childx = new_bn.children(id_x)
    id_pax = new_bn.parents(id_x)
    
    new_bn.erase(x)
    new_bn.add(gum.LabelizedVariable(x, x, ["0", "1"]))
    
    for i in id_childx: 
        new_bn.addArc(x, new_bn.variable(i).name())
    for i in id_pax: 
        new_bn.addArc(new_bn.variable(i).name(), x)
        
    cptx = grafo.cpt(x).topandas()
    new_x = pd.DataFrame(index=cptx.index)
    new_x[("1")] = cptx[(x, xval)]
    new_x[("0")] = sum(cptx[(x, s)] for s in nox)
    new_x.columns = pd.MultiIndex.from_tuples([(x, '1'), (x, '0')])
    
    cptnew = new_bn.cpt(x)
    for idx, row in new_x.iterrows():
        parent_vals = {name: str(val) for name, val in zip(new_x.index.names, idx)}
        for child_label, prob in row.items():
            full_key = {**parent_vals, x: str(child_label[1])}
            cptnew[full_key] = float(prob)
            
    for i in id_childx:
        child = new_bn.variable(i).name()
        v = grafo.cpt(child)
        df = v.topandas().reset_index()
        newcpt = new_bn.cpt(child)
        
        yvals = [col[1] for col in df.columns if col[0] == child]
        parent_names = df.index.names
        
        for idx, row in df.iterrows():
            parent_vals_dict = {name: str(val) for name, val in zip(parent_names, idx)}
            kwargs = {k: v for k, v in parent_vals_dict.items() if k != x}
            
            for yy in yvals:
                newval = complex_prob(data_df, grafo, child, yy, x, nox, **kwargs)
                key0 = {**parent_vals_dict, x: "0", child: yy}
                newcpt[key0] = float(newval)
                
                key1 = {**parent_vals_dict, x: "1", child: yy}
                keyold = {**parent_vals_dict, x: xval, child: yy}
                newcpt[key1] = float(v[keyold])
                
    return new_bn

def cobound(y, yval, x, xval, data, graph):
    y_vals = list(graph.variable(y).labels())
    x_vals = list(graph.variable(x).labels())   
    
    copyx = x_vals.copy()
    copyx.remove(xval)
    nox = copyx
    
    copyy = y_vals.copy()
    copyy.remove(yval)
    noy = copyy
    
    bingraph = g_bin(graph, x, xval, nox, data)
    bingraph = g_bin(bingraph, y, yval, noy, data)
    
    do_g = gum.BayesNet(bingraph)
    mod = csl.CausalModel(do_g)
    
    formula, imp, explanation = csl.causalImpact(mod, on=y, doing=x, values={x: "1"})
    PYx = round(float(imp[1]), 3)
    
    ny = data[data[y] == yval].shape[0]
    Py = ny / data.shape[0]
    
    formula2, imp2, explanation2 = csl.causalImpact(mod, on=y, doing=x, values={x: "0"})
    PYnox = round(float(imp2[1]), 3)
    
    low_B = max(0, PYx - PYnox, Py - PYnox, PYx - Py)
    
    ie = gum.LazyPropagation(bingraph)
    ie.makeInference()
    joint = ie.jointPosterior({x, y})
    
    p_xy = float(joint[{x: "1", y: "1"}])
    p_noxy = float(joint[{x: "0", y: "0"}])
    Pxny = float(joint[{x: "1", y: "0"}])
    Pnxy = float(joint[{x: "0", y: "1"}])
    
    upper_B = min(PYx, 1 - PYnox, p_xy + p_noxy, PYx - PYnox + Pxny + Pnxy)
    
    return f'The answer is between {round(low_B, 4)} and {round(upper_B, 4)}'