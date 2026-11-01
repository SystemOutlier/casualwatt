"""Genera il benchmark dalla rete: righe, oracoli e rete perturbata.

Cosa produce (accanto a questo file):
  benchmark.csv                    le query con il loro ground truth;
  insurance_grafo_perturbato.bif   la stessa struttura con CPT risorteggiate;
  manifest.json                    seed, costanti congelate, hash dei due BIF,
                                   conteggi per ramo/split/rete/classe.

Perche' esiste. Il riferimento attuale e' fatto di 12 query scelte a mano, 8 su
12 marcate `review` perche' la mappatura era ambigua, e una sola query provata
end-to-end. Non basta per un claim di accuratezza. Qui le righe si generano
dalla rete con un seed fisso, cosi' query, etichetta, evidenza e target sono
coerenti per costruzione e non vanno confermati a mano uno per uno.

Vocabolario. Le frasi usano una tabella scritta qui sotto (`FRASI`) e non
`node_descr` della relatrice: quella tabella ha voci malformate ("osts for the
insured car", "True', 'False", "Values: ..." al posto della descrizione) e da
esse non esce una frase con mappatura unica. La tabella copre tutti e 27 i nodi
della rete, cosi' il generatore puo' scegliere fra cause e bersagli veri invece
di girare intorno a un sottoinsieme: con tredici variabili il ramo
controfattuale aveva due sole cause binarie e non riusciva a produrre 40
domande distinte. Ogni frase nomina una sola variabile e un solo stato, e i
costi si distinguono per il soggetto ("repair cost for this car", "for the
other car", "injury liability cost", "medical cost", "total property cost").
L'unico stato lasciato fuori e' `Mileage=Domino`, che nel BIF pubblicato non e'
una categoria di chilometraggio e non ha una descrizione non ambigua.

Oracoli. Non passano dalla pipeline: ogni valore si calcola qui da pyagrum.
  cond_prob      posterior di LazyPropagation con l'evidenza (non cau_inference);
  inter          do strutturale: copia del grafo, archi entranti cancellati,
                 CPT a massa puntuale sulla variabile trattata, poi posterior.
                 `LazyPropagation.doIntervention` non esiste in pyagrum 3.2.1;
  coherence      posterior + la soglia 0,60 del codice della relatrice;
  counterfactual **causa binaria soltanto**. Con due stati `g_bin` e' esatto
                 (non c'e' niente da marginalizzare), quindi l'oracolo Tian-Pearl
                 si puo' calcolare sui do del grafo originale invece che sulla
                 rete binarizzata: PYx, PYnox, Py e il giunto (x, y) vengono
                 tutti dal grafo originale. Non e' indipendente *nella formula*
                 (e' la stessa), ma lo e' nelle quantita': nessun passaggio da
                 g_bin, complex_prob o causalImpact. Il ramo `influence` resta
                 fuori dal benchmark quantitativo (vedi benchmark/__init__.py).

Rete perturbata. Le CPT dell'Insurance sono quelle del libro: un modello di
frontiera puo' ricordarne le probabilita' e rispondere senza usare il tool.
Ogni riga di ogni CPT viene ridisegnata da una Dirichlet(1) (esponenziali
normalizzati con seed fisso) e la rete si salva con `saveBN`. Non conserva la
struttura deterministica dell'originale: e' una rete diversa con lo stesso
scheletro, e il manifest ne registra l'hash. Gli oracoli si calcolano sul file
**riletto**, cioe' sullo stesso byte che legge il tool (il giro BIF costa fino a
3e-8 per valore, misurato, ed e' sotto la tolleranza ma non nullo).

Stratificazione. Per ogni ramo 40 righe, cosi' ripartite: rete base/perturbata
alternata, split sviluppo/held-out alternato su due, e per coherence anche la
classe di decisione (compatibile / non compatibile) alternata su quattro. Ogni
combinazione delle tre alternanze esce 5 volte. Lo split serve a scegliere la
variante sullo sviluppo e riportarla sull'held-out, non a gonfiare il numero.

Righe degeneri. Una risposta che si stampa uguale per qualunque variante non
misura l'orchestrazione: la rete del libro ha CPT deterministiche, quindi
l'evidenza porta spesso a P = 1,0000, e un intervallo di `cobound` puo' ridursi
a "between X and X". Sono esclusi i valori che, alla precisione stampata dal
ramo, valgono 0 o 1; gli intervalli vuoti, cioe' con i due estremi uguali alla
quarta cifra; e, per coherence, le probabilita' entro 1e-3 dalla soglia 0,60,
dove la classe la deciderebbe l'arrotondamento e non il dato. Si contano in
`esclusi_degeneri`, separati dagli scarti per difetto del codice.

Verifica. `--verifica` rilegge il CSV appena scritto, chiama
`cau_inference` con l'etichetta del ground truth e confronta i numeri stampati
con l'oracolo a `TOLL`. Il campo `oracole` dice quale oracolo ha prodotto la
riga; la verifica non tocca il classificatore, che e' un compito del modello.

Uso:  python benchmark/genera.py [--verifica]
"""

import argparse
import collections
import csv
import hashlib
import importlib.util
import itertools
import json
import math
import random
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CONSEGNA = ROOT / "consegna"

sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

import pyagrum as gum  # noqa: E402
# In pyagrum 3.2.1 la classe non e' esposta come `gum.IncompatibleEvidence` ma
# esiste nel modulo compilato: verificato con un'evidenza a probabilita' zero.
from pyagrum.pyagrumcpp import IncompatibleEvidence  # noqa: E402

import benchmark as B  # noqa: E402

RETE_BASE = CONSEGNA / "insurance_grafo.bif"
RETE_PERT = HERE / "insurance_grafo_perturbato.bif"
CSV_OUT = HERE / "benchmark.csv"
MANIFEST = HERE / "manifest.json"

# Tentativi per riempire uno slot. Un ciclo finito e rumoroso costa secondi; un
# ciclo infinito che non converge sarebbe un blocco silenzioso al primo ramo
# impossibile. Se si esaurisce, il generatore si ferma e lo dice.
MAX_TENTATIVI = 20000

# Chiamate al layer deterministico per un singolo slot. Ogni chiamata ricarica
# un BIF (~0,2 s): senza tetto uno spazio di candidati troppo stretto si
# consuma in minuti di attese invece di fermarsi e dirlo.
MAX_PROVE_SLOT = 300

# Una frase per (variabile, stato). Solo variabili e stati che compaiono qui
# entrano nelle query: la mappatura e' unica per costruzione.
FRASI = {
    "Age": {
        "Adolescent": "the driver is a teenager",
        "Adult": "the driver is an adult",
        "Senior": "the driver is senior",
    },
    "SocioEcon": {
        "Prole": "the socio-economic status is working-class",
        "Middle": "the socio-economic status is middle",
        "UpperMiddle": "the socio-economic status is upper-middle",
        "Wealthy": "the socio-economic status is wealthy",
    },
    "RiskAversion": {
        "Psychopath": "the customer has a psychopathic risk aversion",
        "Adventurous": "the customer has an adventurous risk aversion",
        "Normal": "the customer has a normal risk aversion",
        "Cautious": "the customer has a cautious risk aversion",
    },
    "VehicleYear": {
        "Current": "the car is a current-year model",
        "Older": "the car is an older model",
    },
    "DrivQuality": {
        "Poor": "the driving quality is poor",
        "Normal": "the driving quality is normal",
        "Excellent": "the driving quality is excellent",
    },
    "DrivingSkill": {
        "SubStandard": "the driving skill is sub-standard",
        "Normal": "the driving skill is normal",
        "Expert": "the driving skill is expert",
    },
    "Accident": {
        "None": "there was no accident",
        "Mild": "the accident was mild",
        "Moderate": "the accident was moderate",
        "Severe": "the accident was severe",
    },
    "ThisCarDam": {
        "None": "this car has no damage",
        "Mild": "the damage to this car is mild",
        "Moderate": "the damage to this car is moderate",
        "Severe": "the damage to this car is severe",
    },
    "RuggedAuto": {
        "EggShell": "the car is eggshell-fragile",
        "Football": "the car is as rugged as a football",
        "Tank": "the car is as rugged as a tank",
    },
    "MakeModel": {
        "SportsCar": "the car is a sports car",
        "Economy": "the car is an economy model",
        "FamilySedan": "the car is a family sedan",
        "Luxury": "the car is a luxury model",
        "SuperLuxury": "the car is a super-luxury model",
    },
    "Mileage": {
        "FiveThou": "the mileage is five thousand miles",
        "TwentyThou": "the mileage is twenty thousand miles",
        "FiftyThou": "the mileage is fifty thousand miles",
    },
    "Airbag": {
        "True": "the car has an airbag",
        "False": "the car has no airbag",
    },
    "Antilock": {
        "True": "the car has an antilock braking system",
        "False": "the car has no antilock braking system",
    },
    "GoodStudent": {
        "True": "the customer is a good student",
        "False": "the customer is not a good student",
    },
    "SeniorTrain": {
        "True": "the customer has completed the senior driver training",
        "False": "the customer has not completed the senior driver training",
    },
    "DrivHist": {
        "Zero": "the customer has zero recorded driving incidents",
        "One": "the customer has one recorded driving incident",
        "Many": "the customer has many recorded driving incidents",
    },
    "CarValue": {
        "FiveThou": "the car is worth five thousand dollars",
        "TenThou": "the car is worth ten thousand dollars",
        "TwentyThou": "the car is worth twenty thousand dollars",
        "FiftyThou": "the car is worth fifty thousand dollars",
        "Million": "the car is worth a million dollars",
    },
    "HomeBase": {
        "Secure": "the neighbourhood is secure",
        "City": "the neighbourhood is in the city",
        "Suburb": "the neighbourhood is in the suburbs",
        "Rural": "the neighbourhood is rural",
    },
    "AntiTheft": {
        "True": "the car has an anti-theft device",
        "False": "the car has no anti-theft device",
    },
    "Theft": {
        "True": "the car has been stolen",
        "False": "the car has not been stolen",
    },
    "OtherCar": {
        "True": "the household owns another car",
        "False": "the household owns no other car",
    },
    "Cushioning": {
        "Poor": "the cushioning is poor",
        "Fair": "the cushioning is fair",
        "Good": "the cushioning is good",
        "Excellent": "the cushioning is excellent",
    },
    "MedCost": {
        "Thousand": "the medical cost is one thousand dollars",
        "TenThou": "the medical cost is ten thousand dollars",
        "HundredThou": "the medical cost is a hundred thousand dollars",
        "Million": "the medical cost is a million dollars",
    },
    "ILiCost": {
        "Thousand": "the injury liability cost is one thousand dollars",
        "TenThou": "the injury liability cost is ten thousand dollars",
        "HundredThou": "the injury liability cost is a hundred thousand dollars",
        "Million": "the injury liability cost is a million dollars",
    },
    "ThisCarCost": {
        "Thousand": "the repair cost for this car is one thousand dollars",
        "TenThou": "the repair cost for this car is ten thousand dollars",
        "HundredThou": "the repair cost for this car is a hundred thousand dollars",
        "Million": "the repair cost for this car is a million dollars",
    },
    "OtherCarCost": {
        "Thousand": "the repair cost for the other car is one thousand dollars",
        "TenThou": "the repair cost for the other car is ten thousand dollars",
        "HundredThou": "the repair cost for the other car is a hundred thousand dollars",
        "Million": "the repair cost for the other car is a million dollars",
    },
    "PropCost": {
        "Thousand": "the total property cost is one thousand dollars",
        "TenThou": "the total property cost is ten thousand dollars",
        "HundredThou": "the total property cost is a hundred thousand dollars",
        "Million": "the total property cost is a million dollars",
    },
}

# La query storica, tenuta com'e' per continuita' con le misure gia' fatte.
# Il suo valore atteso non si copia dal file: si ricalcola e si confronta.
CP1_QUERY = "Given that the driving quality is normal, how likely is it that the age of the driver is senior?"
CP1_ATTESO = 0.2117494190


class Oracolo:
    """Le quantita' del ground truth, lette dal file della rete (riletto)."""

    def __init__(self, percorso: Path):
        self.percorso = Path(percorso)
        self.bn = gum.loadBN(str(self.percorso))
        ie = gum.LazyPropagation(self.bn)
        ie.makeInference()
        self._ie = ie

    def posterior(self, y: str, yv: str, evidenza: dict) -> float:
        ie = gum.LazyPropagation(self.bn)
        ie.setEvidence(dict(evidenza))
        ie.makeInference()
        return float(ie.posterior(y)[{y: yv}])

    def marginale(self, y: str, yv: str) -> float:
        return float(self._ie.posterior(y)[{y: yv}])

    def do(self, y: str, yv: str, x: str, xv: str) -> float:
        """P(y = yv | do(x = xv)) per via strutturale.

        pyagrum 3.2.1 non ha `LazyPropagation.doIntervention`: si copia il
        grafo, si tolgono gli archi entranti in x, si mette la CPT di x a massa
        puntuale e si legge il posterior. E' la definizione di intervento, non
        l'approssimazione di un ramo della pipeline.
        """
        bn = gum.BayesNet(self.bn)
        for padre in [self.bn.variable(i).name() for i in self.bn.parents(x)]:
            bn.eraseArc(padre, x)
        bn.cpt(x)[{}] = [1.0 if s == xv else 0.0 for s in bn.variable(x).labels()]
        ie = gum.LazyPropagation(bn)
        ie.makeInference()
        return float(ie.posterior(y)[{y: yv}])

    def congiunto(self, x: str, y: str, yv: str) -> dict:
        """P(x=s, y=yv) e P(x=s, y!=yv) per ogni stato s di x.

        `jointPosterior({x, y})` di LazyPropagation non e' indirizzabile su una
        coppia qualunque (verificato: UndefinedElement su Antilock/ThisCarDam),
        quindi il giunto si ricostruisce con la regola del prodotto,
        P(x, y) = P(y | x) P(x), da posteriori a una sola evidenza.
        """
        out = {}
        for xv in self.bn.variable(x).labels():
            px = self.marginale(x, xv)
            py = self.posterior(y, yv, {x: xv})
            out[(xv, True)] = py * px
            out[(xv, False)] = (1.0 - py) * px
        return out


def _vocabolario(bn) -> dict:
    """La tabella FRASI ridotta a cio' che la rete contiene davvero."""
    voc = {}
    for nome, stati in FRASI.items():
        if nome not in bn.names():
            continue
        ammessi = set(bn.variable(nome).labels())
        mappa = {s: f for s, f in stati.items() if s in ammessi}
        if len(mappa) >= 2:
            voc[nome] = mappa
    return voc


def _discendenti(bn) -> dict:
    """Nome -> nomi dei discendenti, una volta sola (sempre ordinati)."""
    return {
        bn.variable(i).name(): {bn.variable(j).name() for j in bn.descendants(i)}
        for i in bn.nodes()
    }


def _perturba(base: Path, uscita: Path, seed: int):
    """Riscrive ogni riga di ogni CPT da una Dirichlet(1) e salva il BIF.

    L'esponenziale normalizzato e' un campione esatto da Dirichlet(1): -log(1-U)
    con U uniforme in [0,1). Nessun parametro da tarare, nessuna struttura
    dell'originale conservata: e' una rete diversa con lo stesso scheletro.
    """
    rng = random.Random(seed)
    bn = gum.loadBN(str(base))
    for nodo in bn.nodes():
        nome = bn.variable(nodo).name()
        padri = [bn.variable(p).name() for p in bn.parents(nodo)]
        stati = list(bn.variable(nodo).labels())
        combinazioni = (list(itertools.product(*[bn.variable(p).labels() for p in padri]))
                        if padri else [()])
        for combo in combinazioni:
            cond = dict(zip(padri, combo))
            pesi = [-math.log(1.0 - rng.random()) for _ in stati]
            totale = sum(pesi)
            bn.cpt(nodo)[cond] = [w / totale for w in pesi]
    gum.saveBN(bn, str(uscita))
    return bn


def _sha256(percorso: Path) -> str:
    return hashlib.sha256(Path(percorso).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# candidati: strutturali, senza inferenza; il rng e' quello del ramo e della rete
# ---------------------------------------------------------------------------

def _cand_cond(rng, bn, voc):
    """Target = padre dell'evidenza: e' la definizione di backward_reasoning."""
    con_padri = sorted(n for n in voc if bn.parents(n))
    e = rng.choice(con_padri)
    padri = sorted(bn.variable(p).name() for p in bn.parents(e))
    t = rng.choice([p for p in padri if p in voc])
    return {"e": e, "se": rng.choice(sorted(voc[e])),
            "t": t, "st": rng.choice(sorted(voc[t]))}


def _cand_inter(rng, bn, voc, disc):
    """Target fra i discendenti dell'intervento: altrimenti l'effetto e' nullo."""
    x = rng.choice(sorted(n for n in voc if any(d in voc for d in disc[n])))
    y = rng.choice(sorted(n for n in disc[x] if n in voc))
    return {"x": x, "xv": rng.choice(sorted(voc[x])),
            "y": y, "yv": rng.choice(sorted(voc[y]))}


def _cand_coh(rng, bn, voc, disc):
    """Due evidenze che non discendono dal target: nessuna spiegazione diretta."""
    y = rng.choice(sorted(voc))
    esclusi = set(disc[y]) | {y}
    possibili = sorted(n for n in voc if n not in esclusi)
    if len(possibili) < 2:
        return None
    e1, e2 = rng.sample(possibili, 2)
    return {"y": y, "st": rng.choice(sorted(voc[y])), "e1": e1, "e2": e2}


def _cand_cf(rng, bn, voc, disc, cause):
    x = rng.choice(cause)
    y = rng.choice(sorted(n for n in disc[x] if n in voc))
    xval, xother = rng.sample(sorted(voc[x]), 2)
    return {"x": x, "xval": xval, "xother": xother,
            "y": y, "yv": rng.choice(sorted(voc[y]))}


# ---------------------------------------------------------------------------
# oracoli per riga
# ---------------------------------------------------------------------------

def _gt(ramo, oracolo, c):
    if ramo == "cond_prob":
        p = oracolo.posterior(c["t"], c["st"], {c["e"]: c["se"]})
        return {"expected_probability": p, "oracole": "posterior_lazypropagation"}

    if ramo == "inter":
        p = oracolo.do(c["y"], c["yv"], c["x"], c["xv"])
        return {"expected_probability": p, "oracole": "do_strutturale+posterior"}

    if ramo == "coherence":
        p = oracolo.posterior(c["y"], c["st"], {c["e1"]: c["e1v"], c["e2"]: c["e2v"]})
        decisione = "compatible" if p >= B.SOGLIA_COHERENCE else "non_compatibile"
        return {"expected_probability": p, "expected_decision": decisione,
                "oracole": "posterior_lazypropagation+soglia_0.60"}

    if ramo == "counterfactual":
        pyx = oracolo.do(c["y"], c["yv"], c["x"], c["xval"])
        pynox = oracolo.do(c["y"], c["yv"], c["x"], c["xother"])
        py = oracolo.marginale(c["y"], c["yv"])
        g = oracolo.congiunto(c["x"], c["y"], c["yv"])
        p_xy = g[(c["xval"], True)]
        p_noxy = g[(c["xother"], False)]
        pxny = g[(c["xval"], False)]
        pnxy = g[(c["xother"], True)]
        low = max(0.0, pyx - pynox, py - pynox, pyx - py)
        up = min(pyx, 1 - pynox, p_xy + p_noxy, pyx - pynox + pxny + pnxy)
        if low > up + 1e-12:
            raise ValueError(f"estremi incoerenti: {low} > {up} per {c}")
        return {"expected_lower": round(low, 4), "expected_upper": round(up, 4),
                "oracole": "tian_pearl_causa_binaria"}

    raise ValueError(f"ramo sconosciuto: {ramo}")


# ---------------------------------------------------------------------------
# query
# ---------------------------------------------------------------------------

def _q_cond(c):
    return f"Given that {FRASI[c['e']][c['se']]}, how likely is it that {FRASI[c['t']][c['st']]}?"


def _q_inter(c):
    return (f"What is the probability that {FRASI[c['y']][c['yv']]} if we intervene "
            f"to make it so that {FRASI[c['x']][c['xv']]}?")


def _q_coh(c):
    return (f"Is it coherent that {FRASI[c['y']][c['st']]} given that "
            f"{FRASI[c['e1']][c['e1v']]} and that {FRASI[c['e2']][c['e2v']]}?")


def _q_cf(c):
    return (f"We observed that {FRASI[c['x']][c['xval']]} and that {FRASI[c['y']][c['yv']]}. "
            f"What would the probability that {FRASI[c['y']][c['yv']]} be if the world "
            f"had been such that {FRASI[c['x']][c['xother']]}?")


# ---------------------------------------------------------------------------
# riempimento degli slot
# ---------------------------------------------------------------------------

def _slot(ramo, n):
    """(rete, split, classe) alternati su 1, 2 e 4: ogni combinazione esce n/8 volte."""
    out = []
    for i in range(n):
        rete = "perturbata" if i % 2 else "base"
        split = "dev" if (i // 2) % 2 == 0 else "held-out"
        classe = None
        if ramo == "coherence":
            classe = "compatible" if (i // 4) % 2 == 0 else "non_compatibile"
        out.append((rete, split, classe))
    return out


def _chiave(ramo, c):
    if ramo == "cond_prob":
        return (c["e"], c["se"], c["t"], c["st"])
    if ramo == "inter":
        return (c["x"], c["xv"], c["y"], c["yv"])
    if ramo == "coherence":
        return (c["y"], c["st"], c["e1"], c["e1v"], c["e2"], c["e2v"])
    return (c["x"], c["xval"], c["y"], c["yv"])


def _evidenza_intervento(ramo, c):
    """Cosa deve finire in `input` per il ramo, e in quali colonne."""
    if ramo == "cond_prob":
        return {c["e"]: c["se"]}, {}
    if ramo == "inter":
        return {}, {c["x"]: c["xv"]}
    if ramo == "coherence":
        return {c["e1"]: c["e1v"], c["e2"]: c["e2v"]}, {}
    return {}, {c["x"]: c["xval"]}


def _candidato(ramo, rng, bn, voc, disc, cause):
    if ramo == "cond_prob":
        return _cand_cond(rng, bn, voc)
    if ramo == "inter":
        return _cand_inter(rng, bn, voc, disc)
    if ramo == "coherence":
        c = _cand_coh(rng, bn, voc, disc)
        if c is not None:
            # gli stati delle due evidenze entrano nella chiave e nella domanda
            c["e1v"] = rng.choice(sorted(voc[c["e1"]]))
            c["e2v"] = rng.choice(sorted(voc[c["e2"]]))
        return c
    return _cand_cf(rng, bn, voc, disc, cause)


def _confronta(ramo, risposta, atteso):
    """None se il ramo risponde come l'oracolo, altrimenti il motivo.

    `atteso` = {"prob": float} oppure {"lower", "upper"} piu' "decisione" per
    coherence. La tolleranza e' TOLL su ogni numero stampato: 3 decimali per
    backward_reasoning, intervention e coherence, 4 per gli estremi di cobound.
    """
    numeri = _numeri(risposta)
    if ramo == "counterfactual":
        if len(numeri) != 2:
            return f"numeri stampati {numeri}"
        if any(abs(round(a - b, 12)) > B.TOLL
               for a, b in zip(numeri, (atteso["lower"], atteso["upper"]))):
            return f"stampato {numeri} atteso [{atteso['lower']}, {atteso['upper']}]"
        return None
    if len(numeri) != 1:
        return f"numeri stampati {numeri}"
    if abs(round(numeri[0] - atteso["prob"], 12)) > B.TOLL:
        return f"stampato {numeri} atteso {atteso['prob']:.10f}"
    if ramo == "coherence":
        dice_compatibile = "NOT strongly compatible" not in risposta
        if dice_compatibile != (atteso["decisione"] == "compatible"):
            return f"decisione {dice_compatibile} contro {atteso['decisione']}"
    return None


def _atteso(gt):
    """Il dizionario compatto che `_confronta` vuole, dalle chiavi di _gt."""
    if "expected_lower" in gt:
        return {"lower": gt["expected_lower"], "upper": gt["expected_upper"]}
    return {"prob": gt["expected_probability"], "decisione": gt.get("expected_decision", "")}


def _degenerato(ramo, gt):
    """Motivo per cui la riga non discrimina, oppure None.

    Il criterio e' la precisione con cui il ramo stampa: 3 decimali per
    backward_reasoning e intervention, 4 per coherence e per gli estremi di
    `cobound`. Un valore che si stampa 0,0000 o 1,0000 e' indovinabile da una
    variante che risponde sempre lo stesso numero, e non dice niente
    sull'orchestrazione.
    """
    if ramo == "counterfactual":
        low, up = gt["expected_lower"], gt["expected_upper"]
        if up - low < 1e-4:
            return f"intervallo nullo [{low}, {up}]"
        if up - low >= 0.99:
            return f"intervallo quasi totale [{low}, {up}]"
        return None

    p = gt["expected_probability"]
    cifre = 4 if ramo == "coherence" else 3
    if round(p, cifre) in (0.0, 1.0):
        return f"probabilita' al bordo ({p:.4f})"
    if ramo == "coherence" and abs(p - B.SOGLIA_COHERENCE) < 1e-3:
        return f"a ridosso della soglia ({p:.4f})"
    return None


def _coppia(ramo, c):
    """L'identita' strutturale del candidato, per il registro degli scarti."""
    if ramo == "cond_prob":
        return f"{c['e']}|{c['t']}"
    if ramo == "coherence":
        return f"{c['e1']},{c['e2']}|{c['y']}"
    return f"{c['x']}|{c['y']}"


def _prova_tool(cau, ramo, c, gt, nome_rete):
    """La riga entra solo se il layer deterministico sa rispondere e coincide.

    Perche'. `cobound` non calcola il giunto su ogni coppia (su Antilock ->
    ThisCarDam alza UndefinedElement) e `causalImpact` si ferma sugli effetti
    deterministici (IncompatibleEvidence con DrivQuality dato DrivingSkill).
    Sono limiti del codice, non task: una riga a cui il metro non sa rispondere
    renderebbe uguale per tutti il fallimento e non distinguerebbe le varianti
    di orchestrazione, che sono l'oggetto del confronto. Le righe scartate si
    contano nel manifest e si riportano: qui non spariscono in silenzio.

    Ritorna None oppure (motivo, coppia): la coppia dice quale variabile contro
    quale ha fatto fallire il codice, e senza di essa un conteggio per tipo di
    eccezione non e' verificabile.
    """
    evidenza, intervento = _evidenza_intervento(ramo, c)
    inp = intervento if ramo in ("inter", "counterfactual") else evidenza
    out = {c["y"] if "y" in c else c["t"]: c["yv"] if "yv" in c else c["st"]}
    features = json.dumps({"input": inp, "output": out}, ensure_ascii=False)
    try:
        risposta = cau(B.ETICHETTA[ramo], features, str(RETE_PATH[nome_rete]))
    except Exception as e:
        return (f"{_coppia(ramo, c)}: eccezione {type(e).__name__}", _coppia(ramo, c))
    motivo = _confronta(ramo, risposta, _atteso(gt))
    return None if motivo is None else (motivo, _coppia(ramo, c))


def _riempi(ramo, reti, voc, disc, cause, cau, scarti, esclusi):
    """Le righe del ramo: 40 slot, ognuno riempito da un candidato accettato."""
    righe = []
    # un solo insieme di chiavi per ramo, non uno per rete: la stessa domanda
    # sulle due reti avrebbe due risposte diverse e finirebbe sia in sviluppo
    # sia in held-out, cioe' lo split non separerebbe piu' niente. La chiave di
    # CP1 entra gia' e non e' generata, quindi va messa qui o si duplica.
    visti = {("DrivQuality", "Normal", "Age", "Senior")} if ramo == "cond_prob" else set()
    rngs = {nome: random.Random(f"{B.SEED}:{ramo}:{nome}") for nome in reti}
    bn_riferimento = reti["base"].bn

    for indice, (nome_rete, split, classe) in enumerate(_slot(ramo, B.N_PER_RAMO), start=1):
        oracolo = reti[nome_rete]
        rng = rngs[nome_rete]
        trovato = None
        prove = 0
        for _ in range(MAX_TENTATIVI):
            c = _candidato(ramo, rng, bn_riferimento, voc, disc, cause)
            if c is None:
                continue
            k = _chiave(ramo, c)
            if k in visti:
                continue
            try:
                gt = _gt(ramo, oracolo, c)
            except IncompatibleEvidence:
                # evidenza a probabilita' congiunta zero nella rete base: nella
                # rete perturbata non capita (Dirichlet(1) > 0 ovunque), nella
                # rete del libro capita perche' molte CPT sono deterministiche.
                # La riga non ha una risposta numerica, quindi non e' una riga.
                continue
            if classe is not None and gt["expected_decision"] != classe:
                continue
            motivo = _degenerato(ramo, gt)
            if motivo:
                esclusi[ramo][motivo] += 1
                continue
            if prove >= MAX_PROVE_SLOT:
                raise SystemExit(
                    f"{ramo}/{nome_rete}/{classe}: {MAX_PROVE_SLOT} chiamate al layer "
                    "deterministico in un solo slot, nessun candidato accettato; il "
                    "generatore si ferma invece di girare a vuoto")
            prove += 1
            scarto = _prova_tool(cau, ramo, c, gt, nome_rete)
            if scarto:
                scarti[ramo].append(scarto)
                continue
            visti.add(k)
            trovato = (c, gt)
            break
        if trovato is None:
            raise SystemExit(
                f"{ramo}/{nome_rete}/{classe}: {MAX_TENTATIVI} tentativi senza "
                "un candidato valido; il generatore si ferma invece di riempire "
                "lo slot con un doppione o con un'altra classe")
        c, gt = trovato
        evidenza, intervento = _evidenza_intervento(ramo, c)
        riga = {
            "task_id": f"{TASK[ramo]}{indice:02d}",
            "query": QUERY[ramo](c),
            "ramo": ramo,
            "etichetta_attesa": B.ETICHETTA[ramo],
            "evidence_json": json.dumps(evidenza, ensure_ascii=False),
            "intervention_json": json.dumps(intervento, ensure_ascii=False),
            "target_variable": c["y"] if "y" in c else c["t"],
            "target_state": c["yv"] if "yv" in c else c["st"],
            "expected_probability": (f"{gt['expected_probability']:.10f}"
                                     if "expected_probability" in gt else ""),
            "expected_lower": (f"{gt['expected_lower']:.4f}"
                               if "expected_lower" in gt else ""),
            "expected_upper": (f"{gt['expected_upper']:.4f}"
                               if "expected_upper" in gt else ""),
            "expected_decision": gt.get("expected_decision", ""),
            "oracole": gt["oracole"],
            "rete": RETE_REL[nome_rete],
            "split": split,
        }
        righe.append(riga)
    return righe


TASK = {"cond_prob": "CND", "inter": "INT", "coherence": "COH", "counterfactual": "CF"}
QUERY = {"cond_prob": _q_cond, "inter": _q_inter, "coherence": _q_coh, "counterfactual": _q_cf}
RETE_REL = {"base": "consegna/insurance_grafo.bif",
            "perturbata": "benchmark/insurance_grafo_perturbato.bif"}
RETE_PATH = {"base": RETE_BASE, "perturbata": RETE_PERT}


# ---------------------------------------------------------------------------
# scrittura e verifica
# ---------------------------------------------------------------------------

def _scrivi(righe):
    colonne = list(B.COLONNE_HARNESS) + list(B.COLONNE_GT)
    with open(CSV_OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonne, extrasaction="raise")
        w.writeheader()
        for r in righe:
            w.writerow(r)


def _conta(righe, campo):
    conteggi = {}
    for r in righe:
        conteggi[r[campo]] = conteggi.get(r[campo], 0) + 1
    return dict(sorted(conteggi.items()))


def _features(r):
    """Il dizionario che la pipeline deve dare a cau_inference per questa riga."""
    if r["ramo"] in ("inter", "counterfactual"):
        inp = json.loads(r["intervention_json"])
    else:
        inp = json.loads(r["evidence_json"])
    return {"input": inp, "output": {r["target_variable"]: r["target_state"]}}


def _modulo(nome, percorso):
    spec = importlib.util.spec_from_file_location(nome, percorso)
    m = importlib.util.module_from_spec(spec)
    sys.modules[nome] = m
    spec.loader.exec_module(m)
    return m


def _carica_tool():
    sys.path.insert(0, str(CONSEGNA))
    _modulo("funtions", CONSEGNA / "funtions_corretto.py")
    tools = _modulo("tools", CONSEGNA / "tools_corretto.py")
    return tools.cau_inference.func


def _numeri(testo):
    """I numeri stampati dal ramo, interi compresi: "between 0 and 0.3567" ha due
    estremi e il primo e' uno zero senza virgola (osservato su cobound)."""
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", testo)]


def _verifica():
    """Rimette ogni riga nella pipeline deterministica e confronta i numeri.

    L'etichetta viene dal ground truth: qui si verifica che oracolo e ramo
    dicano la stessa cosa a TOLL. Il classificatore non entra (compito del
    modello), e nemmeno la mappatura delle frasi (verificata dalla chiave).
    """
    with open(CSV_OUT, encoding="utf-8-sig", newline="") as f:
        righe = list(csv.DictReader(f))
    cau = _carica_tool()
    ko = []
    for r in righe:
        path = (ROOT / r["rete"]).resolve()
        try:
            risposta = cau(r["etichetta_attesa"],
                           json.dumps(_features(r), ensure_ascii=False), str(path))
        except Exception as e:
            ko.append((r["task_id"], f"eccezione {type(e).__name__}: {e}"))
            print(f"{r['task_id']:8s} KO  {type(e).__name__}: {e}")
            continue

        atteso = ({"lower": float(r["expected_lower"]), "upper": float(r["expected_upper"])}
                  if r["ramo"] == "counterfactual" else
                  {"prob": float(r["expected_probability"]),
                   "decisione": r["expected_decision"]})
        motivo = _confronta(r["ramo"], risposta, atteso)
        if motivo is None:
            print(f"{r['task_id']:8s} OK  {risposta.strip()[:90]}")
        else:
            ko.append((r["task_id"], f"{motivo} :: {risposta[:120]!r}"))
            print(f"{r['task_id']:8s} KO  {motivo} :: {risposta[:120]!r}")

    print(f"\nverifica: {len(righe) - len(ko)}/{len(righe)} righe coerenti con l'oracolo a TOLL={B.TOLL}")
    for task_id, motivo in ko:
        print(f"  KO {task_id}: {motivo}")
    return 0 if not ko else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera il benchmark MUDILAB dalla rete")
    ap.add_argument("--verifica", action="store_true",
                    help="dopo la generazione rilancia ogni riga in cau_inference")
    a = ap.parse_args()

    if not RETE_BASE.exists():
        raise SystemExit(f"rete base non trovata: {RETE_BASE}")

    base = Oracolo(RETE_BASE)
    voc = _vocabolario(base.bn)
    disc = _discendenti(base.bn)

    # la query storica: se il valore non torna, l'oracolo e' sbagliato e ci si ferma
    cp1 = base.posterior("Age", "Senior", {"DrivQuality": "Normal"})
    if abs(cp1 - CP1_ATTESO) > 1e-9:
        raise SystemExit(
            f"oracolo disallineato da ground_truth.csv su CP1: {cp1!r} contro {CP1_ATTESO!r}")

    _perturba(RETE_BASE, RETE_PERT, B.SEED)
    piena = Oracolo(RETE_PERT)

    reti = {"base": base, "perturbata": piena}
    cause = sorted(n for n in voc
                   if len(voc[n]) == 2 and len(base.bn.variable(n).labels()) == 2
                   and any(d in voc for d in disc[n]))
    cau = _carica_tool()
    scarti = {ramo: [] for ramo in B.RAMI_MISURABILI}
    esclusi = {ramo: collections.Counter() for ramo in B.RAMI_MISURABILI}

    righe = [{
        "task_id": "CP1",
        "query": CP1_QUERY,
        "ramo": "cond_prob",
        "etichetta_attesa": B.ETICHETTA["cond_prob"],
        "evidence_json": json.dumps({"DrivQuality": "Normal"}),
        "intervention_json": "{}",
        "target_variable": "Age",
        "target_state": "Senior",
        "expected_probability": f"{cp1:.10f}",
        "expected_lower": "",
        "expected_upper": "",
        "expected_decision": "",
        "oracole": "posterior_lazypropagation",
        "rete": RETE_REL["base"],
        "split": "dev",
    }]
    for ramo in B.RAMI_MISURABILI:
        righe.extend(_riempi(ramo, reti, voc, disc, cause, cau, scarti, esclusi))

    _scrivi(righe)

    manifest = {
        "generato": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "seed": B.SEED,
        "n_per_ramo": B.N_PER_RAMO,
        "toll": B.TOLL,
        "soglia_coherence": B.SOGLIA_COHERENCE,
        "righe": len(righe),
        "reti": {
            "base": {"percorso": RETE_REL["base"], "sha256": _sha256(RETE_BASE)},
            "perturbata": {"percorso": RETE_REL["perturbata"],
                           "sha256": _sha256(RETE_PERT)},
        },
        "conteggi": {
            "ramo": _conta(righe, "ramo"),
            "split": _conta(righe, "split"),
            "rete": _conta(righe, "rete"),
            "decisione": {k: v for k, v in _conta(
                [r for r in righe if r["ramo"] == "coherence"], "expected_decision").items()},
        },
        # candidati con oracolo valido che il layer deterministico non sa
        # rispondere o non risponde come l'oracolo: un difetto del codice, non
        # del benchmark, e qui resta dichiarato invece di sparire in silenzio.
        # Il secondo livello dice su quale coppia di variabili e' successo.
        "scartati_layer_deterministico": {
            ramo: {motivo: dict(sorted(collections.Counter(
                coppia for m, coppia in v if m == motivo).items()))
                for motivo in sorted({m for m, _ in v})}
            for ramo, v in sorted(scarti.items()) if v
        },
        # righe valide ma non discriminanti (P al bordo, intervallo nullo):
        # escluse per disegno, non perche' il codice sbagli
        "esclusi_degeneri": {
            ramo: dict(sorted(c.items())) for ramo, c in sorted(esclusi.items()) if c
        },
        "cause_binarie": cause,
        "vocabolario": {k: sorted(v) for k, v in sorted(voc.items())},
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"righe": len(righe), "csv": str(CSV_OUT),
                      "conteggi": manifest["conteggi"]}, indent=2, ensure_ascii=False))
    return _verifica() if a.verifica else 0


if __name__ == "__main__":
    raise SystemExit(main())
