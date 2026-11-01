import re
import itertools
import pandas as pd
import pyagrum as gum
# --- originale: importa il modulo notebook, che qui non e' usato: a ogni import
#     stampa "pyagrum.lib.notebook has to be imported from an IPython's instance".
# import pyagrum.causal.notebook as cslnb
import pyagrum.causal as csl
from pathlib import Path

# --- originale, rotto: percorso relativo alla CWD di avvio ---
# dati = pd.read_csv('DATI.csv')
# names = dati['Name'].to_list()
# surnames = dati['Surnames'].to_list()
# FIX: il file sta accanto a questo modulo, non nella CWD da cui parte lo script.
#      Con il percorso relativo l'import fallisce se la CWD non e' MUDILAB.
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / 'DATI.csv'
dati = pd.read_csv(DATA_PATH)
names = dati['Name'].to_list()
surnames = dati['Surnames'].to_list()


def pulisci_output(l: str):
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

# --- originale: tre import mai usati nel resto del file (zero occorrenze di
#     pyro., dist. e torch.) Erano per una validazione PNS che non c'e' piu'.
#     Restano perche' bloccano l'import su un ambiente pulito: con python 3.14
#     `import funtions` si ferma qui (ModuleNotFoundError: pyro, misurato il
#     31-10-2026), quindi nessuna correzione di questo file arriva a girare.
# import pyro
# import pyro.distributions as dist
# import torch


# ---------------------------------------------------------------------------
# complex_prob
# ---------------------------------------------------------------------------
# --- originale: firma posizionale fissa a due condizionanti (j, z) ---
# def complex_prob(df,grafo, y, yval, x, nox, j = None, jval = None, z = None, zval= None):
#     ie = gum.LazyPropagation(grafo)
#     labels = grafo.variable(x).labels()
#     den = 0
#     n2 = []
#     ie.setEvidence({j: jval, z:zval})
#     for i, o in enumerate(labels):
#         if o in nox:
#             tden = ie.posterior(x)[i]
#             n2.append(tden)
#             den = den + tden
#
#     num = 0
#
#     for i,p in enumerate(nox):
#         n1 = df[(df[x] == p) & (df[j] == jval) & (df[z] == zval)][y][yval].values[0]
#         tnum = n1*n2[i]
#         num = num + tnum
#
#     answ= num/den
#
#     return answ
# FIX 1: la funzione vale per un numero qualsiasi di padri di y. `conditions` e'
#        il dizionario con i valori degli altri padri (anche vuoto), non due nomi
#        fissi j e z: con un solo padre j/z valgono None e setEvidence({None: None})
#        alza un'eccezione.
# FIX 2: la probabilita' condizionata del figlio si legge dalla CPT del grafo
#        (cpt_y[{..., x: p, y: yval}]) e non da `df`, che e' la stessa CPT in forma
#        pandas: cosi' il risultato non dipende dall'ordine o dal nome delle righe.
# FIX 3: denominatore nullo = nessuna massa sugli stati "0". Succede davvero:
#        P(Age in {Adolescent, Adult} | SeniorTrain=True) = 0, perche' la CPT di
#        SeniorTrain vale 0 su quegli stati. La funzione restituisce None e chi
#        chiama decide il valore dichiarato (vedi g_bin), invece di dividere per zero.
def complex_prob(grafo, y, yval, x, nox, conditions=None):
    """P(y=yval | x=0, conditions) con "x=0" = x in nox, pesata su P(x|conditions).

    E' la probabilita' di y quando x non assume il valore di interesse, mediata
    sugli stati di x esclusi xval con i pesi che il grafo assegna loro.
    Restituisce None se (x in nox, conditions) ha probabilita' zero.
    """
    conditions = dict(conditions or {})
    ie = gum.LazyPropagation(grafo)
    ie.setEvidence(conditions)
    ie.makeInference()

    post_x = ie.posterior(x)
    cpt_y = grafo.cpt(y)

    den = 0.0
    num = 0.0
    for p in nox:
        w = float(post_x[{x: p}])
        den += w
        num += float(cpt_y[{**conditions, x: p, y: yval}]) * w

    if den == 0.0:
        return None
    return num / den


def marginal_prob(grafo, y, yval, conditions=None):
    """P(y=yval | conditions): usata solo sulle configurazioni impossibili."""
    ie = gum.LazyPropagation(grafo)
    ie.setEvidence(dict(conditions or {}))
    ie.makeInference()
    return float(ie.posterior(y)[{y: yval}])


# ---------------------------------------------------------------------------
# g_bin
# ---------------------------------------------------------------------------
# --- originale: tre rami (dim == 1/2/3) con nomi non definiti (m, col_nox, n) ---
# def g_bin(grafo, x, xval, nox):
#     new_bn = gum.BayesNet(grafo)
#     id_x = new_bn.idFromName(x)
#     id_childx = new_bn.children(id_x)
#     id_pax = new_bn.parents(id_x)
#     new_bn.erase(x)
#     new_bn.add(gum.LabelizedVariable(x, x, ["0", "1"]))
#     for i in id_childx:
#         new_bn.addArc(x,new_bn.variable(i).name())
#     for i in id_pax:
#         new_bn.addArc(new_bn.variable(i).name(),x)
#     ... (rami dim == 3 / dim == 2 / dim == 1, con m, col_nox e n non definiti)
# FIX 1: gli id dei nodi cambiano dopo erase(); si salvano i NOMI prima di
#        cancellare la variabile e si ricostruiscono gli archi per nome.
# FIX 2: i padri del figlio diversi da x si enumerano con itertools.product
#        sulle etichette, quindi il codice e' uno solo e vale per 1, 2 o piu'
#        padri (prima c'erano tre rami e solo quello a 3 padri funzionava).
# FIX 3: le chiavi delle CPT usano le etichette "0"/"1" in modo uniforme:
#        prima il ramo di x usava stringhe e i rami dei figli interi 0/1.
# FIX 4: il "valore di interesse" x=1 vale P(y | x=xval), il "resto" x=0 vale
#        complex_prob(...), cioe' la stessa cosa che faceva l'originale ma su
#        tutti gli altri padri del figlio.
def g_bin(grafo, x, xval, nox):
    """Copia di `grafo` con `x` resa binaria: 1 = xval, 0 = tutti gli altri stati.

    Le CPT dei figli di x vengono riscritte in modo che lo stato 0 raccolga la
    probabilita' degli stati esclusi, pesata su P(x | altri padri).
    """
    new_bn = gum.BayesNet(grafo)

    parents_x = [new_bn.variable(i).name() for i in new_bn.parents(x)]
    children_x = [new_bn.variable(i).name() for i in new_bn.children(x)]
    if xval not in grafo.variable(x).labels():
        raise ValueError(f"g_bin: {xval!r} non e' uno stato di {x}, stati: {grafo.variable(x).labels()}")

    new_bn.erase(x)
    new_bn.add(gum.LabelizedVariable(x, x, ["0", "1"]))
    for child in children_x:
        new_bn.addArc(x, child)
    for parent in parents_x:
        new_bn.addArc(parent, x)

    # CPT di x: 1 = xval, 0 = somma degli stati in nox
    cpt_x = grafo.cpt(x)
    new_cpt_x = new_bn.cpt(x)
    parent_states = [grafo.variable(p).labels() for p in parents_x]
    for combo in itertools.product(*parent_states):
        pvals = dict(zip(parents_x, combo))
        p1 = float(cpt_x[{**pvals, x: xval}])
        p0 = sum(float(cpt_x[{**pvals, x: s}]) for s in nox)
        new_cpt_x[{**pvals, x: "1"}] = p1
        new_cpt_x[{**pvals, x: "0"}] = p0

    # CPT dei figli di x: stessa marginalizzazione per ogni configurazione degli
    # altri padri del figlio
    for child in children_x:
        cpt_child = grafo.cpt(child)
        new_cpt_child = new_bn.cpt(child)
        other_parents = [grafo.variable(i).name() for i in grafo.parents(child) if grafo.variable(i).name() != x]
        other_states = [grafo.variable(p).labels() for p in other_parents]
        child_labels = grafo.variable(child).labels()
        for combo in itertools.product(*other_states):
            conds = dict(zip(other_parents, combo))
            p0 = {yval: complex_prob(grafo, child, yval, x, nox, conds) for yval in child_labels}
            if any(v is None for v in p0.values()):
                # (x = 0, conds) e' impossibile nel modello originale, quindi
                # questa riga non riceve massa in nessuna inferenza: si usa la
                # distribuzione del figlio senza x, dichiarata, invece di 0/0.
                p0 = {yval: marginal_prob(grafo, child, yval, conds) for yval in child_labels}
            for yval in child_labels:
                new_cpt_child[{**conds, x: "1", child: yval}] = float(cpt_child[{**conds, x: xval, child: yval}])
                new_cpt_child[{**conds, x: "0", child: yval}] = p0[yval]

    return new_bn


# ---------------------------------------------------------------------------
# cobound
# ---------------------------------------------------------------------------
# --- originale: stampa di debug, arrotondamento dei termini intermedi, ---
# --- righe morte su `bind` e indici interi 1/0 su variabili etichettate "0"/"1" ---
# def cobound(y, yval, x, xval, data, graph):
#     ...
#     bind = data[[y,x]]
#     bind[x] = (bind[x] == xval).astype(int)
#     bind[y] = (bind[y] == yval).astype(int)
#     ...
#     formula, imp, explanation = csl.causalImpact(mod, on=y, doing=x, values = {x: 1})
#     print(f'imp: {imp[1]}')
#     PYx = round(imp[1],3)
#     ...
# FIX 1: `bind` non viene mai usato dopo le tre righe che lo costruiscono: tolto
#        (era anche un SettingWithCopyWarning).
# FIX 2: niente print di debug dentro una funzione di libreria: la risposta e'
#        il valore di ritorno.
# FIX 3: PYx e PYnox si tengono a piena precisione e si arrotonda solo la
#        risposta finale: arrotondare i termini intermedi falsa i due estremi.
# FIX 4: `values` affetta il tensore anche sulla variabile `doing` (verificato su
#        pyagrum 3.2.1): {x: "1"} restituisce P(y | do(x=1)), un tensore su y.
#        Gli indici sono le etichette "0"/"1", non gli interi 0/1.
# FIX 5: effetto non identificabile -> errore dichiarato invece di `imp[1]` su None.
# FIX 6: `data` serve solo a stimare Py = P(y = yval). Il parametro opzionale `py`
#        permette di passarla esplicitamente, per esempio con la marginale del
#        grafo; con py specificata `data` non viene letto affatto. Il default
#        resta il comportamento originale (Py stimata da `data`).
def cobound(y, yval, x, xval, data, graph, py=None):
    y_vals = list(graph.variable(y).labels())
    x_vals = list(graph.variable(x).labels())
    if yval not in y_vals:
        raise ValueError(f"cobound: {yval!r} non e' uno stato di {y}")
    if xval not in x_vals:
        raise ValueError(f"cobound: {xval!r} non e' uno stato di {x}")
    # la colonna x non viene mai letta, quindi non e' una condizione di validita'
    if py is None:
        if data is None:
            raise ValueError("cobound: serve `data` oppure `py`")
        if y not in data.columns:
            raise KeyError(f"cobound: la colonna {y!r} non e' in DATI.csv ({list(data.columns)})")

    nox = [v for v in x_vals if v != xval]
    noy = [v for v in y_vals if v != yval]

    bingraph = g_bin(graph, x, xval, nox)
    bingraph = g_bin(bingraph, y, yval, noy)
    do_g = gum.BayesNet(bingraph)
    mod = csl.CausalModel(do_g)

    formula, imp, explanation = csl.causalImpact(mod, on=y, doing=x, values={x: "1"})
    if imp is None:
        raise ValueError(f"cobound: effetto non identificabile ({explanation})")
    PYx = float(imp[{y: "1"}])

    formula2, imp2, explanation2 = csl.causalImpact(mod, on=y, doing=x, values={x: "0"})
    if imp2 is None:
        raise ValueError(f"cobound: effetto non identificabile ({explanation2})")
    PYnox = float(imp2[{y: "1"}])

    Py = float(py) if py is not None else data[data[y] == yval].shape[0] / data.shape[0]

    low_B = max(0, PYx - PYnox, Py - PYnox, PYx - Py)

    ie = gum.LazyPropagation(bingraph)
    ie.makeInference()
    joint = ie.jointPosterior({x, y})
    p_xy = float(joint[{x: "1", y: "1"}])
    p_noxy = float(joint[{x: "0", y: "0"}])
    Pxny = float(joint[{x: "1", y: "0"}])
    Pnxy = float(joint[{x: "0", y: "1"}])

    upper_B = min(PYx, 1 - PYnox, p_xy + p_noxy, PYx - PYnox + Pxny + Pnxy)

    answer = f'The answer is between {round(low_B,4)} and {round(upper_B,4)}'

    return answer
