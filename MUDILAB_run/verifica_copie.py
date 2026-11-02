"""Verifica deterministica delle tre copie correttive, senza chiamare un modello.

Carica `funtions - Copia.py` e `tools - Copia.py` come fa run_query.py con
MUDILAB_COPIE=1 e prova ogni ramo di `cau_inference` piu' i casi che devono
fallire con un messaggio leggibile. Non tocca Ollama e non modifica nulla.

Uso:  python verifica_copie.py
"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUDILAB = HERE.parent / "MUDILAB"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, MUDILAB / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(MUDILAB))
_load("funtions", "funtions - Copia.py")
tools = _load("tools", "tools - Copia.py")

cau_inference = tools.cau_inference.func


def prova(titolo: str, *args, **kwargs):
    try:
        print(f"{titolo}: {cau_inference(*args, **kwargs)}")
    except Exception as e:
        print(f"{titolo}: {type(e).__name__}: {e}")


def main():
    print("read_graph() senza percorso:", tools.read_graph.func()[:80].replace("\n", " "), "...")
    print("--- rami che devono rispondere ---")
    # riferimento noto per questa query: 0.2117, quindi 0.212 arrotondato
    prova("backward_reasoning", "backward_reasoning",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}))
    prova("intervention", "intervention",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": {"Accident": "Severe"}}))
    prova("intervention senza valore di output", "intervention",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": {"Accident": "Not necessary"}}))
    prova("coherence due evidenze", "coherence",
          json.dumps({"input": {"DrivQuality": "Normal", "DrivingSkill": "Expert"}, "output": {"Age": "Senior"}}))
    prova("counterfactual", "counterfactual",
          json.dumps({"input": {"Accident": "Severe"}, "output": {"ThisCarCost": "Million"}}))
    prova("conterfactual (refuso accettato)", "conterfactual",
          json.dumps({"input": {"Accident": "Severe"}, "output": {"ThisCarCost": "Million"}}))
    prova("influence", "influence",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}))
    print("--- casi che devono fallire con un messaggio leggibile ---")
    prova("output come stringa", "backward_reasoning",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": "Not necessary"}))
    prova("etichetta inventata", "probabilmente", json.dumps({"input": {}, "output": {"Age": "Senior"}}))
    prova("variabile inesistente", "backward_reasoning",
          json.dumps({"input": {"Colore": "Rosso"}, "output": {"Age": "Senior"}}))
    prova("testo non dizionario", "backward_reasoning", "the answer is probably high")
    print("--- casi che devono passare lo stesso ---")
    prova("JSON in blocco markdown", "backward_reasoning",
          '```json\n{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}\n```')
    prova("Not necessary filtrato dall'evidenza", "backward_reasoning",
          json.dumps({"input": {"DrivQuality": "Normal", "Mileage": "Not necessary"},
                      "output": {"Age": "Senior"}}))


if __name__ == "__main__":
    main()
