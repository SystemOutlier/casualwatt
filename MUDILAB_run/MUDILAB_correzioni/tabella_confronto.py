"""Tabella originale contro corretto, costruita eseguendo e non leggendo.

Per ogni caso un processo figlio carica UN solo lato (i file originale
oppure le copie corrette) ed esegue la stessa chiamata, stampando l'esito. Il
padre raccoglie i due esiti e scrive la tabella in markdown. Nessun modello
viene contattato e nessun file viene modificato.

Ogni lato gira nel proprio processo per due motivi: i due `funtions` leggono
DATI.csv all'import e registrerebbero lo stesso nome di modulo, e l'originale
funziona solo se la cartella di lavoro e' MUDILAB (`pd.read_csv('DATI.csv')`
alla riga 43). Il caso `cwd_esterno` misura proprio quello.

Uso:  python tabella_confronto.py --orig "cartella dei file originali"
      [--out tabella_confronto.md]

La cartella degli originali e' quella che contiene agents.py, tools.py e
funtions.py; si puo' indicare anche con la variabile MUDILAB_ORIG.
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
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

# features che un modello piccolo produce davvero: JSON corretto
DRIV = '{"input": {"DrivQuality": "Normal"}, "output": {"Age": "Senior"}}'


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


# --- i casi: stessa chiamata sui due lati -----------------------------------

def c_agents(fu, tools, ctx):
    """Importare il modulo degli agenti."""
    if ctx["lato"] == "originale":
        import agents  # noqa: F401
        return f"importato, modello predefinito: {getattr(agents, '_MODEL', 'n/d')}"
    a = _load("agents", CORR / "agents_corretto.py")
    return f"importato, prompt_descr e' {type(a.prompt_descr).__name__}"


def c_read_graph(fu, tools, ctx):
    """read_graph() senza argomenti, come lo chiama un modello che non sa il path."""
    return tools.read_graph.func()


def c_path_none(fu, tools, ctx):
    """cau_inference con path=None: e' il default che il modello non deve sapere."""
    return tools.cau_inference.func("backward_reasoning", DRIV, None)


def c_cwd_esterno(fu, tools, ctx):
    """La stessa domanda lanciata da una cartella che non e' MUDILAB."""
    vecchia = os.getcwd()
    tmp = tempfile.mkdtemp()
    try:
        os.chdir(tmp)
        return tools.cau_inference.func("backward_reasoning", DRIV, str(bif()))
    finally:
        os.chdir(vecchia)


def c_code_fence(fu, tools, ctx):
    """Le features con le recinzioni markdown, come le scrivono i modelli."""
    testo = "```json\n" + DRIV + "\n```"
    return tools.cau_inference.func("backward_reasoning", testo, str(bif()))


def c_eval_codice(fu, tools, ctx):
    """Il testo del modello non e' solo un dizionario: contiene un'espressione."""
    testo = ('(__import__("os").environ.__setitem__("MUDILAB_PROBE", "eseguito"), '
             + DRIV + ')[1]')
    return tools.cau_inference.func("backward_reasoning", testo, str(bif()))


def c_output_stringa(fu, tools, ctx):
    """output come stringa invece che come dizionario."""
    testo = '{"input": {"DrivQuality": "Normal"}, "output": "Not necessary"}'
    return tools.cau_inference.func("backward_reasoning", testo, str(bif()))


def c_coherence_due(fu, tools, ctx):
    """Coherence con due evidenze: le usa tutte e due?"""
    testo = ('{"input": {"DrivQuality": "Normal", "DrivingSkill": "Expert"}, '
             '"output": {"Age": "Senior"}}')
    return tools.cau_inference.func("coherence", testo, str(bif()))


def c_intervention_tre(fu, tools, ctx):
    """Intervention con tre variabili in input."""
    testo = ('{"input": {"DrivQuality": "Normal", "Age": "Senior", '
             '"SocioEcon": "Wealthy"}, "output": {"Accident": "Severe"}}')
    return tools.cau_inference.func("intervention", testo, str(bif()))


def c_counterfactual(fu, tools, ctx):
    """L'etichetta che il classificatore non puo' emettere (agents.py riga 24)."""
    testo = '{"input": {"Accident": "Severe"}, "output": {"ThisCarCost": "Million"}}'
    return tools.cau_inference.func("counterfactual", testo, str(bif()))


def c_conterfactual(fu, tools, ctx):
    """Il refuso scritto nell'originale: quale dei due lati lo accetta."""
    testo = '{"input": {"Accident": "Severe"}, "output": {"ThisCarCost": "Million"}}'
    return tools.cau_inference.func("conterfactual", testo, str(bif()))


def c_etichetta_ignota(fu, tools, ctx):
    """Etichetta che non esiste in nessun ramo."""
    return tools.cau_inference.func("probabilmente", DRIV, str(bif()))


def c_cobound(fu, tools, ctx):
    """Livello funtions: i limiti del controfattuale (cobound -> g_bin)."""
    import pyagrum as gum
    grafo = gum.loadBN(str(bif()))
    return fu.cobound("ThisCarCost", "Million", "Accident", "Severe", fu.dati, grafo)


# (id, descrizione, funzione). L'ordine e' quello della tabella.
CASI = [
    ("agents", f"importare il modulo degli agenti", c_agents),
    ("cobound", f"controfattuale a livello funtions: cobound -> g_bin", c_cobound),
    ("path_none", f"cau_inference(..., path=None), cioe' come la chiama il modello", c_path_none),
    ("cwd_esterno", f"stessa domanda lanciata da una cartella diversa da MUDILAB", c_cwd_esterno),
    ("read_graph", f"read_graph() senza argomenti", c_read_graph),
    ("code_fence", f"features con le recinzioni markdown", c_code_fence),
    ("eval_codice", f"features che contengono un'espressione Python, non solo un dizionario", c_eval_codice),
    ("output_stringa", f"output come stringa invece che come dizionario", c_output_stringa),
    ("coherence_due", f"coherence con due evidenze", c_coherence_due),
    ("intervention_tre", f"intervention con tre variabili in input", c_intervention_tre),
    ("counterfactual", f"etichetta counterfactual", c_counterfactual),
    ("conterfactual", f"refuso conterfactual, l'etichetta scritta nell'originale", c_conterfactual),
    ("etichetta_ignota", f"etichetta che non esiste", c_etichetta_ignota),
]


def _figlio(lato: str):
    # Il figlio parte con sys.path[0] = MUDILAB_run, dove sta il nostro client.py
    # di shim: senza toglierlo, `from client import HuggingFaceChatClient` di
    # agents.py riga 8 trova lo shim e il difetto vero non si vede.
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != HERE]
    fu, tools = carica(lato)
    ctx = {"lato": lato, "bif": bif()}
    for cid, _descr, fn in CASI:
        cattura = StringIO()
        try:
            with redirect_stdout(cattura):
                esito = fn(fu, tools, ctx)
            stato = f"OK -> {esito}"
        except Exception as e:
            stato = f"{type(e).__name__}: {e}"
        rumore = cattura.getvalue().strip()
        if rumore:
            stato += f"  [stdout: {rumore[:80]!r}]"
        if cid == "eval_codice":
            probe = os.environ.get("MUDILAB_PROBE")
            stato += f"  [MUDILAB_PROBE={'eseguito' if probe else 'non impostata'}]"
        print(f"RISULTATO\t{cid}\t{' '.join(stato.split())}", flush=True)


def _padre(out: Path):
    esiti = {}
    for lato in ("originale", "corretto"):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                            "--figlio", lato],
                           capture_output=True, text=True, encoding="utf-8", env=env)
        if r.returncode != 0:
            raise SystemExit(f"il lato {lato} e' morto:\n{r.stderr}")
        for riga in r.stdout.splitlines():
            if riga.startswith("RISULTATO\t"):
                _, cid, testo = riga.split("\t", 2)
                esiti[(cid, lato)] = testo

    righe = ["| # | Caso, stessa chiamata sui due lati | Originale | Corretto |",
             "|---|---|---|---|"]
    for n, (cid, descr, _) in enumerate(CASI, 1):
        o = esiti.get((cid, "originale"), "non eseguito").replace("|", "\\|")
        c = esiti.get((cid, "corretto"), "non eseguito").replace("|", "\\|")
        righe.append(f"| {n} | {descr} | {o} | {c} |")
    testo = "\n".join(righe) + "\n"
    out.write_text(testo, encoding="utf-8")
    print(testo)
    print(f"scritto in {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--figlio", choices=["originale", "corretto"])
    p.add_argument("--orig", type=Path,
                   help="cartella dei file originali (quella che contiene tools.py)")
    p.add_argument("--out", type=Path, default=HERE / "tabella_confronto.md")
    args = p.parse_args()
    if args.orig:
        os.environ["MUDILAB_ORIG"] = str(args.orig)
    if args.figlio:
        _figlio(args.figlio)
    else:
        _padre(args.out)


if __name__ == "__main__":
    main()
