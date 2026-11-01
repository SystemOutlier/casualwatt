"""Esegue la pipeline MUDILAB senza modificare i file della professoressa.

Due sorgenti, scelte da MUDILAB_COPIE:

  MUDILAB_COPIE non impostata -> i file originali (agents.py, tools.py,
      funtions.py). `agents.py` definisce `small` e `gpt5` ma lascia vuota la
      sezione #CLIENTS: i due client vengono iniettati in `builtins` prima
      dell'import, cosi' il modulo resta intatto.

  MUDILAB_COPIE=1 -> le tre versioni corrette in consegna/ (agents_corretto.py,
      tools_corretto.py, funtions_corretto.py), caricate sotto i nomi che gli
      import si aspettano. Le copie definiscono i client da sole.

Solo per gli originali la CWD va messa nella loro cartella, perche' funtions.py
legge DATI.csv all'import.

Uso:  python run_query.py "<query>" [--orig "cartella dei file originali"]

La cartella degli originali (quella con agents.py, tools.py, funtions.py) si
indica con --orig o con la variabile MUDILAB_ORIG; nello zip i file stanno tutti
accanto a questo script, nel repo le copie stanno in consegna/.
"""

import asyncio
import builtins
import functools
import importlib.util
import inspect
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def _copie() -> Path:
    """Le copie corrette: accanto a questo file nello zip, in consegna/ nel repo."""
    return HERE if (HERE / "tools_corretto.py").exists() else HERE / "consegna"


def orig() -> Path:
    """Cartella dei file originali: MUDILAB_ORIG, poi i posti noti accanto a questo file."""
    if os.environ.get("MUDILAB_ORIG"):
        c = Path(os.environ["MUDILAB_ORIG"]).resolve()
        if not (c / "tools.py").exists():
            raise SystemExit(f'MUDILAB_ORIG={c} non contiene tools.py')
        return c
    for c in (ROOT / "MUDILAB", HERE / "MUDILAB", HERE):
        if (c / "tools.py").exists():
            return c.resolve()
    raise SystemExit(
        "cartella degli originali non trovata (ci deve essere tools.py): "
        'indicala con --orig "percorso" oppure con la variabile MUDILAB_ORIG'
    )


# --orig si toglie dagli argomenti prima che il resto diventi la query
_args = sys.argv[1:]
if "--orig" in _args:
    _i = _args.index("--orig")
    os.environ["MUDILAB_ORIG"] = _args[_i + 1]
    del _args[_i:_i + 2]

COPIE = os.environ.get("MUDILAB_COPIE", "").strip().lower() in ("1", "true", "yes", "si", "si'")


def _load(name: str, path: Path):
    """Carica il file `path` sotto il nome di modulo `name`."""
    path = Path(path).resolve()
    if not path.exists():
        raise SystemExit(f"file non trovato: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


if COPIE:
    # le copie correttive stanno fuori dalla cartella della professoressa:
    # MUDILAB/ deve contenere solo i suoi file originali
    needed_dir = _copie()
    needed = ["agents_corretto.py", "tools_corretto.py", "funtions_corretto.py", "insurance_grafo.bif", "DATI.csv"]
else:
    needed_dir = orig()
    needed = ["agents.py", "tools.py", "funtions.py", "insurance_grafo.bif", "DATI.csv"]
missing = [n for n in needed if not (needed_dir / n).exists()]
if missing:
    raise SystemExit(f"file mancanti in {needed_dir}: {missing}")

sys.path.insert(0, str(needed_dir))
sys.path.insert(0, str(HERE))
os.chdir(needed_dir)

from agent_framework.openai import OpenAIChatCompletionClient  # noqa: E402

MODEL = os.environ.get("MUDILAB_MODEL", "tinyllama:latest")
_client = OpenAIChatCompletionClient(
    model=MODEL,
    base_url=os.environ.get("MUDILAB_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.environ.get("MUDILAB_API_KEY", "ollama"),
)
# servono solo all'originale, che non li definisce; le copie li ridefiniscono
builtins.small = _client
builtins.gpt5 = _client

if COPIE:
    _load("funtions", needed_dir / "funtions_corretto.py")
    _load("tools", needed_dir / "tools_corretto.py")
    mudilab_agents = _load("agents", needed_dir / "agents_corretto.py")
    SOURCE = {
        "agents": "agents_corretto.py",
        "tools": "tools_corretto.py",
        "funtions": "funtions_corretto.py",
    }
else:
    # MUDILAB_TOOLS permette di caricare una sola copia di tools.py sotto il
    # nome "tools", che e' quello che agents.py importa. Default: l'originale.
    tools_name = os.environ.get("MUDILAB_TOOLS", "")
    if tools_name:
        tools_path = Path(tools_name)
        if not tools_path.is_absolute():
            tools_path = HERE.parent / tools_path
        _load("tools", tools_path)
    import agents as mudilab_agents  # noqa: E402

    SOURCE = {
        "agents": "agents.py",
        "tools": tools_name or "tools.py",
        "funtions": "funtions.py",
    }

# Le copie scelgono il modello da sole se MUDILAB_MODEL non e' impostata: il
# campo "model" del risultato deve dire quello che ha davvero risposto.
ACTIVE_MODEL = os.environ.get("MUDILAB_MODEL") or getattr(mudilab_agents, "_MODEL", None) or MODEL

# Il framework conta le eccezioni dei tool ma non ne conserva il testo
# (agent_framework/_tools.py:897-899 incrementa e rilancia). Con il solo
# conteggio si sa che una chiamata e' fallita, non perche', e la ragione e'
# l'unica cosa che permette di riferirla o di correggerla.
ERRORI_TOOL: dict[str, str] = {}
CATTURA = {}


def _avvolgi(nome: str, tool) -> str:
    """Avvolge tool.func per ricordare il testo dell'ultima eccezione.

    L'eccezione viene rilanciata identica, quindi il comportamento del tool non
    cambia: cambia solo cosa resta nel JSON. functools.wraps conserva firma e
    annotazioni, che il framework rilegge per costruire lo schema degli
    argomenti (agent_framework/_tools.py:854-865).
    """
    func = getattr(tool, "func", None)
    if func is None:
        return "non installata: il tool non espone .func"
    if getattr(func, "__cw_eccezioni__", False):
        return "gia' installata"

    if inspect.iscoroutinefunction(func):
        @functools.wraps(func)
        async def avvolto(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                ERRORI_TOOL[nome] = f"{type(e).__name__}: {e}"
                raise
    else:
        @functools.wraps(func)
        def avvolto(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                ERRORI_TOOL[nome] = f"{type(e).__name__}: {e}"
                raise

    avvolto.__cw_eccezioni__ = True
    try:
        tool.func = avvolto
    except Exception as e:
        return f"non installata: {type(e).__name__}: {e}"
    return "installata"


for _nome in ("read_graph", "cau_inference"):
    CATTURA[_nome] = _avvolgi(_nome, getattr(mudilab_agents, _nome, None))


async def run(task: str):
    session = mudilab_agents.causal_A.create_session()
    steps = []

    t0 = time.perf_counter()
    translation = (
        await mudilab_agents.translator.run(
            f"Create a dictionary following your instruction of the query:{task}",
            session=session,
        )
    ).text
    t1 = time.perf_counter()
    steps.append({"step": "translator", "seconds": round(t1 - t0, 3), "text": translation})

    label = (
        await mudilab_agents.classificator.run(
            f"classify the following query using your instructions:{task}",
            session=session,
        )
    ).text
    t2 = time.perf_counter()
    steps.append({"step": "classificator", "seconds": round(t2 - t1, 3), "text": label})

    answer = (
        await mudilab_agents.causal_A.run(
            f"Provide the precise answer to the user's task ({task}) using your TOOLS"
            f" with the follonwing parameters-> label:{label}, features:{translation}."
            " After that give the causal explanation of this answer.",
            session=session,
        )
    ).text
    t3 = time.perf_counter()
    steps.append({"step": "causal_A", "seconds": round(t3 - t2, 3), "text": answer})

    cau = getattr(mudilab_agents, "cau_inference", None)
    # Un run vale solo se il numero viene da una chiamata riuscita a
    # cau_inference: i modelli piccoli inventano la risposta (visto: 0.5 e 0.8
    # con zero invocazioni) e una misura energetica su quella risposta non
    # misura il calcolo del riferimento.
    tool_ok = bool(cau) and cau.invocation_count > 0 and cau.invocation_exception_count == 0

    return {
        "model": ACTIVE_MODEL,
        "source": SOURCE,
        "task": task,
        "seconds_total": round(t3 - t0, 3),
        "tool_ok": tool_ok,
        # invocation_count dice se il modello ha davvero chiamato il tool o se ha
        # scritto un numero inventato; exception_count se la chiamata e' fallita.
        "tool_calls": {
            nome: {
                "invocazioni": getattr(getattr(mudilab_agents, nome, None), "invocation_count", None),
                "eccezioni": getattr(getattr(mudilab_agents, nome, None), "invocation_exception_count", None),
            }
            for nome in ("read_graph", "cau_inference")
        },
        # il testo dell'ultima eccezione per tool: vuoto se non ne ha sollevate.
        # Serve a distinguere "non ha chiamato" da "ha chiamato male".
        "errore_tool": dict(ERRORI_TOOL),
        "cattura_eccezioni": CATTURA,
        "steps": steps,
    }


if __name__ == "__main__":
    query = " ".join(_args) or (
        "Given that the driving quality is normal, how likely is it that the age "
        "of the driver is senior?"
    )
    result = asyncio.run(run(query))
    print(json.dumps(result, indent=2, ensure_ascii=False))
