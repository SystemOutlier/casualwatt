"""Verifica deterministica delle tre versioni corrette, senza chiamare un modello.

Carica `funtions_corretto.py` e `tools_corretto.py` e prova ogni ramo di
`cau_inference` piu' i casi che devono fallire con un messaggio leggibile.
Non contatta Ollama, non legge l'ambiente e non scrive nulla: servono solo
questo file, i due moduli corretti, `insurance_grafo.bif` e `DATI.csv`, tutti
nella stessa cartella.

Uso:  python verifica_copie.py
"""

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name: str, filename: str):
    path = HERE / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(HERE))
_load("funtions", "funtions_corretto.py")
tools = _load("tools", "tools_corretto.py")

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
    prova("stato non ammesso dalla variabile", "backward_reasoning",
          json.dumps({"input": {"Age": "Young"}, "output": {"Accident": "Severe"}}))
    prova("controfattuale con stato non ammesso", "counterfactual",
          json.dumps({"input": {"Accident": "Severe"}, "output": {"ThisCarCost": "Billions"}}))
    prova("testo non dizionario", "backward_reasoning", "the answer is probably high")
    print("--- casi che devono passare lo stesso ---")
    prova("JSON in blocco markdown", "backward_reasoning",
          '```json\n{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}\n```')
    prova("Not necessary filtrato dall'evidenza", "backward_reasoning",
          json.dumps({"input": {"DrivQuality": "Normal", "Mileage": "Not necessary"},
                      "output": {"Age": "Senior"}}))
    # FIX 9: i modelli passano path come la parola "None", che e' una stringa
    # vera e saltava il default.
    print("read_graph('None') vale come percorso assente:",
          tools.read_graph.func("None")[:40].replace("\n", " "), "...")
    prova("path scritto come parola None", "backward_reasoning",
          json.dumps({"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}),
          "None")
    # FIX 10: llama3.2:3b scrive il dizionario con virgolette tipografiche.
    prova("virgolette tipografiche", "backward_reasoning",
          '{\u201cinput\u201d: {\u201cDrivQuality\u201d: \u201cNormal\u201d}, '
          '\u201coutput\u201d: {\u201cAge\u201d: \u201cSenior\u201d}}')
    print("--- stessa query controfattuale, due fonti di Py ---")
    # Il tool usa la marginale del grafo (FIX 11 in tools_corretto.py): Py e' la
    # marginale dello stesso giunto da cui cobound prende p_xy e gli altri
    # termini. Qui si mostra anche la variante a file, che `cobound` permette
    # ancora passando `py=None` e `data`, per vedere che numero cambia.
    import pyagrum as gum

    fu = sys.modules["funtions"]
    grafo = gum.loadBN(str(HERE / "insurance_grafo.bif"))
    ie = gum.LazyPropagation(grafo)
    ie.makeInference()
    etichette = list(grafo.variable("ThisCarCost").labels())
    py_grafo = float(ie.posterior("ThisCarCost")[etichette.index("Million")])
    print("Py da DATI.csv:", fu.cobound("ThisCarCost", "Million", "Accident", "Severe",
                                        fu.dati, grafo))
    print(f"Py dal grafo ({py_grafo:.6f}):",
          fu.cobound("ThisCarCost", "Million", "Accident", "Severe", None, grafo,
                     py=py_grafo))


if __name__ == "__main__":
    main()
