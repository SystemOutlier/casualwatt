"""Le sei righe di DATI.csv usate come query, eseguite sui due lati.

Per ogni riga di DATI.csv si costruisce la stessa query: le celle della riga come
evidenza, una variabile della riga come bersaglio. La query viene data sia ai
file originali sia alle copie corrette, in due processi separati, e i due
esiti finiscono nella stessa riga di tabella.

Due tipi di query per riga:

  backward     evidenza = celle valide tranne il bersaglio, bersaglio = valore
               della riga. Qui i due lati devono coincidere: e' il controllo che
               la correzione non cambia il calcolo quando il calcolo e' giusto.
  coherence    stessa evidenza, chiesto come compatibilita'. Qui devono
               differire, perche' l'originale aggiunge una sola evidenza
               (`list(input_.keys()) == 2` a tools.py riga 94 confronta una
               lista con un intero, quindi e' sempre falso).

Piu' un terzo tipo, solo per le righe che hanno celle non valide:

  intera       la riga come sta, celle non valide comprese: serve a vedere se i
               due lati rifiutano il dato sporco e cosa rispondono.

Nessun modello viene contattato e nessun file viene toccato.

Uso:  python verifica_righe_dati.py --orig "cartella dei file originali"
      [--out verifica_righe_dati.md]

La cartella degli originali e' quella che contiene agents.py, tools.py e
funtions.py; si puo' indicare anche con la variabile MUDILAB_ORIG.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _copie() -> Path:
    """Le copie corrette: accanto a questo file nello zip, in consegna/ nel repo."""
    return HERE if (HERE / "tools_corretto.py").exists() else HERE / "consegna"


CORR = _copie()

_orig = None


def orig() -> Path:
    """Cartella dei file originali: MUDILAB_ORIG, poi i posti noti accanto a questo file."""
    global _orig
    if _orig is not None:
        return _orig
    candidati = [Path(os.environ["MUDILAB_ORIG"])] if os.environ.get("MUDILAB_ORIG") else []
    candidati += [ROOT / "MUDILAB", HERE / "MUDILAB", HERE]
    for c in candidati:
        if (c / "tools.py").exists():
            _orig = c.resolve()
            return _orig
    raise SystemExit(
        "cartella degli originali non trovata (ci deve essere tools.py): "
        'indicala con --orig "percorso" oppure con la variabile MUDILAB_ORIG'
    )


def bif() -> Path:
    return orig() / "insurance_grafo.bif"


def dati() -> Path:
    return orig() / "DATI.csv"

NOME_BERSAGLIO = "Accident"     # se la cella e' vuota si ripiega su FALLBACK
FALLBACK = "ThisCarCost"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def carica(lato: str):
    """Restituisce (funtions, tools). L'originale gira con CWD in MUDILAB."""
    if lato == "originale":
        os.chdir(orig())
        sys.path.insert(0, str(orig()))
        import funtions  # noqa: F401
        import tools
        return sys.modules["funtions"], tools
    _load("funtions", CORR / "funtions_corretto.py")
    tools = _load("tools", CORR / "tools_corretto.py")
    return sys.modules["funtions"], tools


def _valore(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    return str(v).strip()


def righe():
    """Legge DATI.csv e il grafo e restituisce le query da eseguire.

    Ogni elemento: (indice, riga_csv, bersaglio, cella_bersaglio, evidenza,
    celle_non_valide). L'evidenza contiene solo le celle che sono etichette
    valide della loro variabile; le altre sono elencate a parte.
    """
    import pandas as pd
    import pyagrum as gum

    d = pd.read_csv(dati())
    g = gum.loadBN(str(bif()))
    variabili = set(g.names())
    colonne = [c for c in d.columns if c in variabili]

    fuori = []
    for i, riga in d.iterrows():
        for c in colonne:
            v = _valore(riga[c])
            if v not in list(g.variable(c).labels()):
                fuori.append((int(i), c, v))

    uscite = []
    for i, riga in d.iterrows():
        i = int(i)
        target = NOME_BERSAGLIO
        if _valore(riga.get(target, "nan")) not in list(g.variable(target).labels()):
            target = FALLBACK
        valore = _valore(riga[target])
        evidenza, sporche = {}, []
        for c in colonne:
            if c == target:
                continue
            v = _valore(riga[c])
            if v in list(g.variable(c).labels()):
                evidenza[c] = v
            else:
                sporche.append((c, v))
        uscite.append({"indice": i, "target": target, "valore": valore,
                       "evidenza": evidenza, "sporche": sporche,
                       "colonne": colonne})
    return uscite, fuori


def _query(q, tipo):
    """Costruisce la stringa features per un tipo di query."""
    import json
    if tipo == "intera":
        # tutta la riga, comprese le celle che il grafo non conosce
        import pandas as pd
        import pyagrum as gum
        d = pd.read_csv(dati())
        g = gum.loadBN(str(bif()))
        riga = d.iloc[q["indice"]]
        ev = {c: _valore(riga[c]) for c in q["colonne"] if c != q["target"]}
    else:
        ev = dict(q["evidenza"])
    return json.dumps({"input": ev, "output": {q["target"]: q["valore"]}})


def _figlio(lato: str):
    # senza questo, `from client import ...` di agents.py troverebbe il nostro
    # shim in MUDILAB_run invece di misurare il difetto
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]
    fu, tools = carica(lato)
    righe_ = righe()[0]
    for q in righe_:
        tipi = ["backward", "coherence"]
        if q["sporche"]:
            tipi.append("intera")
        for tipo in tipi:
            etichetta = "coherence" if tipo == "coherence" else "backward_reasoning"
            cattura = StringIO()
            try:
                with redirect_stdout(cattura):
                    esito = tools.cau_inference.func(
                        etichetta, _query(q, tipo), str(bif()))
                stato = f"OK -> {esito}"
            except Exception as e:
                stato = f"{type(e).__name__}: {e}"
            rumore = cattura.getvalue().strip()
            if rumore:
                stato += f"  [stdout: {rumore[:60]!r}]"
            print(f"RIGA\t{q['indice']}\t{tipo}\t{' '.join(stato.split())}",
                  flush=True)


def _prima_evidenza(q):
    return next(iter(q["evidenza"]), "-")


def _padre(out: Path):
    righe_, fuori = righe()
    esiti = {}
    for lato in ("originale", "corretto"):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            "--figlio", lato],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        if r.returncode != 0:
            raise SystemExit(f"il lato {lato} e' morto:\n{r.stderr}")
        for riga in r.stdout.splitlines():
            if riga.startswith("RIGA\t"):
                _, i, tipo, testo = riga.split("\t", 3)
                esiti[(int(i), tipo, lato)] = testo

    def cella(i, tipo, lato):
        return esiti.get((i, tipo, lato), "non eseguito").replace("|", "\\|")

    per_riga = {}
    for i, c, v in fuori:
        per_riga.setdefault(i, []).append(f"{c}={v!r}")

    md = ["## 1. Validita' delle celle rispetto al grafo", "",
          "Ogni cella e' confrontata con le etichette che il grafo ammette per "
          "quella variabile.", "",
          "| Riga | Celle non valide |", "|---|---|"]
    for q in righe_:
        md.append(f"| {q['indice']} | {', '.join(per_riga.get(q['indice'], ['-']))} |")

    md += ["", "## 2. La riga come query, eseguita sui due lati", "",
           "Bersaglio: `Accident` se la cella e' valida, altrimenti "
           f"`{FALLBACK}`. Le celle non valide sono escluse dall'evidenza, "
           "tranne nel tipo `intera`.", "",
           "| Riga | Bersaglio | Evidenze valide | 1a evidenza usata dall'originale "
           "| backward originale | backward corretto | coherence originale "
           "| coherence corretto |",
           "|---|---|---|---|---|---|---|---|"]
    for q in righe_:
        i = q["indice"]
        md.append(f"| {i} | {q['target']}={q['valore']} | {len(q['evidenza'])} "
                  f"| {_prima_evidenza(q)} "
                  f"| {cella(i, 'backward', 'originale')} "
                  f"| {cella(i, 'backward', 'corretto')} "
                  f"| {cella(i, 'coherence', 'originale')} "
                  f"| {cella(i, 'coherence', 'corretto')} |")

    md += ["", "## 3. La riga come sta, celle non valide comprese", "",
           "Solo le righe che hanno almeno una cella fuori vocabolario.", "",
           "| Riga | Originale | Corretto |", "|---|---|---|"]
    for q in righe_:
        if q["sporche"]:
            i = q["indice"]
            md.append(f"| {i} | {cella(i, 'intera', 'originale')} "
                      f"| {cella(i, 'intera', 'corretto')} |")

    testo = "\n".join(md) + "\n"
    out.write_text(testo, encoding="utf-8")
    print(testo)
    print(f"scritto in {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--figlio", choices=["originale", "corretto"])
    p.add_argument("--orig", type=Path,
                   help="cartella dei file originali (quella che contiene tools.py)")
    p.add_argument("--out", type=Path, default=HERE / "verifica_righe_dati.md")
    args = p.parse_args()
    if args.orig:
        os.environ["MUDILAB_ORIG"] = str(args.orig)
    if args.figlio:
        _figlio(args.figlio)
    else:
        _padre(args.out)


if __name__ == "__main__":
    main()
