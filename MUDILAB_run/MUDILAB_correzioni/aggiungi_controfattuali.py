"""Aggiunge le tre query controfattuali a ground_truth.csv, con due varianti.

Le nove righe non controfattuali restano quelle generate dal validatore del
20-10; qui si accodano le tre della lista `counter` del notebook della
relatrice. I limiti vengono da `cobound` delle copie corrette, cioe' dalla
stessa funzione che usa `cau_inference` quando l'etichetta e' `counterfactual`.

`cobound` ha un solo termine che non viene dal grafo: Py = P(Y = y). Il file
porta percio' due varianti, in quattro colonne:

  expected_lower_file / expected_upper_file    Py stimata da DATI.csv, cioe' il
                                               comportamento originale
  expected_lower_graph / expected_upper_graph  Py = marginale del grafo,
                                               passata col parametro `py`

La seconda esiste perche' DATI.csv ha 6 righe e non contiene ne' DrivQuality ne'
Theft: con quel file due query su tre non si calcolano, e sulla terza il limite
inferiore dipende interamente da una frazione su sei righe. Da dove vada presa
Py e' una domanda per la relatrice, non una scelta da fare qui.

`expected_probability` resta vuota: un intervallo non e' una probabilita'
puntuale, e il validatore confronta quella colonna con una tolleranza.

Uso:  python aggiungi_controfattuali.py [--base ...] [--out ...]

Si puo' rilanciare sullo stesso file che produce: le righe con task_id CF1-CF3
vengono scartate e ricalcolate, le altre restano intatte.
"""

import argparse
import csv
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _copie() -> Path:
    """Le copie corrette: accanto a questo file nello zip, in consegna/ nel repo."""
    return HERE if (HERE / "tools_corretto.py").exists() else HERE / "consegna"


CONSEGNA = _copie()

COLS = (
    "expected_lower_file",
    "expected_upper_file",
    "expected_lower_graph",
    "expected_upper_graph",
)

# le tre query stanno nella cella 10 del notebook (lista `counter`)
QUERIES = [
    {
        "task_id": "CF1",
        "query": "If a person's risk aversion were 'Cautious' rather than 'Psychopath', how much would this change the likelihood of their driving being excellent?",
        "target_variable": "DrivQuality",
        "target_state": "Excellent",
        "intervention": {"RiskAversion": "Cautious"},
        "mapping_status": "review",
        "notes": (
            "DrivingSkill ha lo stato Expert e non Excellent: letto come "
            "DrivQuality=Excellent, come IN2. `cobound` riduce 'Cautious piuttosto "
            "che Psychopath' al contrasto Cautious contro tutti gli altri stati."
        ),
    },
    {
        "task_id": "CF2",
        "query": "If this customer were a senior citizen rather than an adult, how would the likelihood of causing a serious accident change?",
        "target_variable": "Accident",
        "target_state": "Severe",
        "intervention": {"Age": "Senior"},
        "mapping_status": "review",
        "notes": (
            "Serious accident letto come Accident=Severe e non ThisCarDam=Severe, "
            "stessa ambiguita' di IN1 e CO1."
        ),
    },
    {
        "task_id": "CF3",
        "query": "If the customer had been wealthy rather than working-class, how would the likelihood of theft have changed?",
        "target_variable": "Theft",
        "target_state": "True",
        "intervention": {"SocioEcon": "Wealthy"},
        "mapping_status": "probable",
        "notes": (
            "Mappatura diretta sul nodo Theft. 'Working-class' inteso come Prole; "
            "`cobound` riduce il confronto a Wealthy contro tutti gli altri stati."
        ),
    },
]


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, CONSEGNA / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _bounds(testo: str):
    """Estrae i due estremi da 'The answer is between <low> and <upper>'."""
    m = re.search(r"between\s+(-?[\d.]+)\s+and\s+(-?[\d.]+)", testo)
    if not m:
        raise ValueError(f"formato inatteso da cobound: {testo!r}")
    return m.group(1), m.group(2)


def _termini(fu, grafo, y, yv, x, xval, py):
    """Ricalcola i quattro termini di `cobound`, per sapere quale lo vincola.

    Serve a dire dove Py entra davvero: se il termine attivo non dipende da Py,
    le due varianti coincidono per costruzione. `cobound` restituisce solo i due
    estremi, quindi i termini si ricostruiscono qui con le stesse chiamate.
    """
    import pyagrum as gum
    import pyagrum.causal as csl

    y_vals = list(grafo.variable(y).labels())
    x_vals = list(grafo.variable(x).labels())
    nox = [v for v in x_vals if v != xval]
    noy = [v for v in y_vals if v != yv]
    b = fu.g_bin(grafo, x, xval, nox)
    b = fu.g_bin(b, y, yv, noy)
    mod = csl.CausalModel(gum.BayesNet(b))
    _, i1, _ = csl.causalImpact(mod, on=y, doing=x, values={x: "1"})
    _, i0, _ = csl.causalImpact(mod, on=y, doing=x, values={x: "0"})
    pyx, pyn = float(i1[{y: "1"}]), float(i0[{y: "1"}])
    ie = gum.LazyPropagation(b)
    ie.makeInference()
    j = ie.jointPosterior({x, y})
    p11, p00 = float(j[{x: "1", y: "1"}]), float(j[{x: "0", y: "0"}])
    p10, p01 = float(j[{x: "1", y: "0"}]), float(j[{x: "0", y: "1"}])
    caldi = {
        "zero": (0.0, False),
        "PYx-PYnox": (pyx - pyn, False),
        "Py-PYnox": (py - pyn, True),
        "PYx-Py": (pyx - py, True),
    }
    freddi = {
        "PYx": (pyx, False),
        "1-PYnox": (1 - pyn, False),
        "p_xy+p_noxy": (p11 + p00, False),
        "PYx-PYnox+Pxny+Pnxy": (pyx - pyn + p10 + p01, False),
    }
    nome_lo = max(caldi, key=lambda k: caldi[k][0])
    nome_up = min(freddi, key=lambda k: freddi[k][0])
    return pyx, pyn, nome_lo, caldi[nome_lo][1], nome_up


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", type=Path, default=CONSEGNA / "ground_truth.csv",
                   help="il CSV da cui ripartire: le righe non controfattuali "
                        "restano, le tre CF vengono ricalcolate")
    p.add_argument("--out", type=Path, default=CONSEGNA / "ground_truth.csv")
    args = p.parse_args()

    sys.path.insert(0, str(CONSEGNA))
    _load("funtions", "funtions_corretto.py")
    fu = sys.modules["funtions"]
    import pyagrum as gum

    grafo = gum.loadBN(str(CONSEGNA / "insurance_grafo.bif"))
    ie = gum.LazyPropagation(grafo)
    ie.makeInference()

    with args.base.open(encoding="utf-8-sig", newline="") as f:
        righe = [r for r in csv.DictReader(f)]
    colonne = [c for c in righe[0] if c not in COLS] + list(COLS)

    ids = {q["task_id"] for q in QUERIES}
    righe = [r for r in righe if r.get("task_id") not in ids]

    for q in QUERIES:
        y, yv = q["target_variable"], q["target_state"]
        (x, xval), = q["intervention"].items()
        etichette = list(grafo.variable(y).labels())
        py_graph = float(ie.posterior(y)[etichette.index(yv)])

        r = {c: "" for c in colonne}
        r.update({
            "task_id": q["task_id"],
            "task_type": "counterfactual",
            "query": q["query"],
            "target_variable": y,
            "target_state": yv,
            "evidence_json": "{}",
            "intervention_json": json.dumps(q["intervention"]),
            "mapping_status": q["mapping_status"],
            "reference_status": "OK",
        })

        # variante 1: Py stimata da DATI.csv, comportamento originale
        try:
            lo, up = _bounds(fu.cobound(y, yv, x, xval, fu.dati, grafo))
        except Exception as e:
            r["error"] = f"py_file: {type(e).__name__}: {e}"
        else:
            r["expected_lower_file"], r["expected_upper_file"] = lo, up

        # variante 2: Py = marginale del grafo
        lo, up = _bounds(fu.cobound(y, yv, x, xval, None, grafo, py=py_graph))
        r["expected_lower_graph"], r["expected_upper_graph"] = lo, up

        # diagnostica: Pyx, Pynox e il termine che vincola l'estremo inferiore.
        # Py e' l'unico input che non viene dal grafo: se il termine attivo non
        # la contiene, le due varianti coincidono per costruzione.
        pyx, pyn, nome_lo, dip_lo, nome_up = _termini(fu, grafo, y, yv, x, xval, py_graph)
        pezzi = [
            q["notes"],
            f"Py = {py_graph:.10f} dalla marginale del grafo; in variante file Py "
            "verrebbe da DATI.csv (6 righe).",
            f"P({y}={yv} | do({x}={xval})) = {pyx:.6e}, "
            f"P({y}={yv} | do({x} diverso da {xval})) = {pyn:.6e}.",
            f"Termine inferiore attivo '{nome_lo}'"
            + (" (dipende da Py)" if dip_lo else " (non dipende da Py)")
            + f", superiore '{nome_up}'.",
        ]
        if r["expected_lower_file"]:
            n = fu.dati[fu.dati[y] == yv].shape[0]
            py_file = n / fu.dati.shape[0]
            _, _, nome_lo_f, _, _ = _termini(fu, grafo, y, yv, x, xval, py_file)
            pezzi.append(
                f"Con Py da DATI.csv ({n}/{fu.dati.shape[0]} righe, Py = "
                f"{py_file:.6f}) il termine attivo diventa '{nome_lo_f}'."
            )
        if max(abs(float(lo)), abs(float(up))) < 1e-4:
            pezzi.append(
                f"L'intervallo {lo} - {up} non e' vuoto ne' nullo: vale {pyx:.2e}, "
                "sotto la risoluzione di 4 decimali a cui `cobound` stampa."
            )
        pezzi.append("Da confermare con la relatrice da dove va presa Py.")
        r["notes"] = " ".join(pezzi)
        righe.append(r)

    with args.out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=colonne)
        w.writeheader()
        w.writerows(righe)

    for r in righe[-len(QUERIES):]:
        print(f"{r['task_id']}: file {r['expected_lower_file'] or 'N/D'} - "
              f"{r['expected_upper_file'] or 'N/D'} | graph "
              f"{r['expected_lower_graph']} - {r['expected_upper_graph']}")
        if r["error"]:
            print(f"   {r['error']}")
    print(f"scritte {len(righe)} righe in {args.out}")


if __name__ == "__main__":
    main()
