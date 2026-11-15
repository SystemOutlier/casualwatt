import pyagrum as gum
import pyagrum.causal as csl
import pandas as pd
import urllib.request
import os

# 1. Scarica il grafo AIMA ufficiale se non è già nella cartella
bif_path = "insurance.bif"
if not os.path.exists(bif_path):
    url = "https://raw.githubusercontent.com/aimacode/aima-data/master/insurance.bif"
    urllib.request.urlretrieve(url, bif_path)

grafo = gum.loadBN(bif_path)
print("✅ Grafo caricato con successo.\n")
print("="*50)
print("🎯 FONTE DI VERITÀ (GROUND TRUTH) MATEMATICA")
print("="*50)

# ---------------------------------------------------------
# TEST 1: POSTERIOR (Ragionamento all'indietro)
# Domanda: "Given that the driving quality is normal, how likely is it that the age of the driver is senior?"
# ---------------------------------------------------------
print("\n1. TEST POSTERIOR:")
print("Query: P(Age=Senior | DrivQuality=Normal)")
ie = gum.LazyPropagation(grafo)
ie.setEvidence({"DrivQuality": "Normal"})
ie.makeInference()
prob_age = ie.posterior("Age")
labels_age = grafo.variable("Age").labels()

# "Senior" è il terzo valore (indice 2) in ["Adolescent", "Adult", "Senior"]
idx_senior = labels_age.index("Senior")
risultato_posterior = prob_age[idx_senior]
print(f"👉 RISULTATO ATTESO DAL SISTEMA: {risultato_posterior:.4f} (circa {risultato_posterior*100:.2f}%)")

# ---------------------------------------------------------
# TEST 2: INTERVENTION (Intervento causale)
# Domanda: "How do you expect the probability of having a severe car damage if the mileage count is changed to twenty thousand?"
# ---------------------------------------------------------
print("\n2. TEST INTERVENTION:")
print("Query: P(ThisCarDam=Severe | do(Mileage=TwentyThou))")
do_bn = gum.BayesNet(grafo)
fdModele = csl.CausalModel(do_bn)
formula, impact, explanation = csl.causalImpact(fdModele, on="ThisCarDam", doing="Mileage", values={"Mileage": "TwentyThou"})

labels_dam = grafo.variable("ThisCarDam").labels()
# "Severe" è il quarto valore (indice 3) in ["None", "Mild", "Moderate", "Severe"]
idx_severe = labels_dam.index("Severe")
risultato_intervention = impact[idx_severe]
print(f"👉 RISULTATO ATTESO DAL SISTEMA: {risultato_intervention:.4f} (circa {risultato_intervention*100:.2f}%)")

# ---------------------------------------------------------
# TEST 3: COUNTERFACTUAL (Controfattuale)
# Domanda: "If a person’s risk aversion were ‘Cautious’ rather than ‘Psychopath’, how much would this change the likelihood of their driving being excellent?"
# ---------------------------------------------------------
print("\n3. TEST COUNTERFACTUAL:")
print("Query: Bound su P(DrivingSkill=Excellent | RiskAversion=Cautious) dato che osserviamo RiskAversion=Psychopath")
# Nota: Questo richiede il tuo file DATI.csv locale
if os.path.exists("DATI.csv"):
    data = pd.read_csv("DATI.csv")
    # Importiamo la funzione corretta dal tuo file funtions.py
    from funtions import cobound
    
    # Attenzione: la funzione cobound nel tuo codice originale ha una firma specifica.
    # La adattiamo per questo test: y="DrivingSkill", yval="Expert", x="RiskAversion", xval="Cautious"
    # (Nota: nel grafo AIMA il valore è "Expert", non "Excellent")
    try:
        risultato_cf = cobound(y="DrivingSkill", yval="Expert", x="RiskAversion", xval="Cautious", data=data, graph=grafo)
        print(f"👉 RISULTATO ATTESO DAL SISTEMA: {risultato_cf}")
    except Exception as e:
        print(f"⚠️ Errore nel calcolo controfattuale (verifica che DATI.csv abbia le colonne giuste): {e}")
else:
    print("⚠️ File DATI.csv non trovato. Il test controfattuale richiede il dataset locale.")

print("\n" + "="*50)
print("Confronta questi numeri con l'output del tuo sistema multi-agente!")
print("="*50)