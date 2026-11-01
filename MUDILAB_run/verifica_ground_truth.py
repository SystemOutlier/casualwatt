"""
Accettazione delle 12 query di ground_truth.csv contro le copie corrette.

Ogni riga del file dichiara tipo, query, variabile e stato di output, evidenza
o intervento, e il valore atteso. Qui si chiama `cau_inference` con
l'etichetta che il classificatore deve emettere per quel tipo di task:

    cond_prob       -> backward_reasoning
    inter           -> intervention
    coherence       -> coherence
    counterfactual  -> counterfactual

e si confronta la risposta con il valore atteso. Il test non chiama un
modello: verifica il calcolo, non la classificazione. Se una riga non torna,
il difetto e' nel tool o nella mappatura, non nel modello.

Uso:  python verifica_ground_truth.py [--tolleranza 5e-4]

Esce 0 se tutte le righe tornano, 1 altrimenti, elencando quelle sbagliate.
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

QUI = Path(__file__).resolve().parent
# nella cartella di lavoro le copie stanno in `consegna/`, nello zip scompattato
# sono accanto a questo script
CONSEGNA = QUI if (QUI / "tools_corretto.py").exists() else QUI / "consegna"
GT = CONSEGNA / "ground_truth.csv"

ETICHETTA = {
    "cond_prob": "backward_reasoning",
    "inter": "intervention",
    "coherence": "coherence",
    "counterfactual": "counterfactual",
}

NUM = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _load(nome: str, file: str):
    spec = importlib.util.spec_from_file_location(nome, CONSEGNA / file)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[nome] = modulo
    spec.loader.exec_module(modulo)
    return modulo


sys.path.insert(0, str(CONSEGNA))
_load("funtions", "funtions_corretto.py")
tools = _load("tools", "tools_corretto.py")
cau_inference = tools.cau_inference.func


def numeri(testo: str):
    return [float(x) for x in NUM.findall(testo)]


def confronta(riga, risposta):
    """Restituisce (ok, atteso, ottenuto) per una riga di ground_truth."""
    tipo = riga["task_type"]
    if tipo == "counterfactual":
        valori = numeri(risposta)
        if len(valori) != 2:
            return False, f"{riga['expected_lower_graph']} - {riga['expected_upper_graph']}", risposta
        atteso = (float(riga["expected_lower_graph"]), float(riga["expected_upper_graph"]))
        return (abs(valori[0] - atteso[0]) <= TOLL and abs(valori[1] - atteso[1]) <= TOLL,
                f"{atteso[0]} - {atteso[1]}", f"{valori[0]} - {valori[1]}")
    valori = numeri(risposta)
    if not valori:
        return False, riga["expected_probability"], risposta
    ottenuto = valori[-1]
    atteso = float(riga["expected_probability"])
    # FIX 12: il ramo coherence riporta quattro decimali come gli altri
    #         (round(prob,4) in tools_corretto), quindi la tolleranza e' la
    #         stessa di tutti i rami.
    ok = abs(ottenuto - atteso) <= TOLL
    if tipo == "coherence":
        attesa = riga["expected_label"]
        forte = "NOT strongly" not in risposta
        ok = ok and (forte == (attesa == "strongly_compatible"))
    return ok, atteso, ottenuto


def main():
    global TOLL
    ap = argparse.ArgumentParser()
    ap.add_argument("--tolleranza", type=float, default=5e-4)
    args = ap.parse_args()
    TOLL = args.tolleranza

    with open(GT, encoding="utf-8-sig", newline="") as f:
        righe = list(csv.DictReader(f))

    print(f"{'id':<5}{'tipo':<16}{'esito':<8}{'atteso':>22}   ottenuto")
    print("-" * 78)
    sbagliate = []
    for r in righe:
        tipo = r["task_type"]
        etichetta = ETICHETTA[tipo]
        sorgente = r["intervention_json"] if tipo in ("inter", "counterfactual") else r["evidence_json"]
        features = {"input": json.loads(sorgente or "{}"),
                    "output": {r["target_variable"]: r["target_state"]}}
        try:
            risposta = cau_inference(etichetta, json.dumps(features), None)
        except Exception as e:
            print(f"{r['task_id']:<5}{tipo:<16}{'ERRORE':<8}{'':>22}   {type(e).__name__}: {e}")
            sbagliate.append(r["task_id"])
            continue
        ok, atteso, ottenuto = confronta(r, risposta)
        if isinstance(atteso, float):
            atteso_txt, ottenuto_txt = f"{atteso:.6f}", f"{ottenuto:.6f}"
        else:
            atteso_txt, ottenuto_txt = str(atteso), str(ottenuto)
        print(f"{r['task_id']:<5}{tipo:<16}{'ok' if ok else 'NO':<8}{atteso_txt:>22}   {ottenuto_txt}")
        if not ok:
            sbagliate.append(r["task_id"])

    print("-" * 78)
    print(f"{len(righe) - len(sbagliate)}/{len(righe)} righe tornano"
          + (f"; sbagliate: {', '.join(sbagliate)}" if sbagliate else ""))
    return 0 if not sbagliate else 1


TOLL = 5e-4

if __name__ == "__main__":
    sys.exit(main())
