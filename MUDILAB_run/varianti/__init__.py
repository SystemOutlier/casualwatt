"""Registro delle varianti di orchestrazione.

Perche' esiste. L'obiettivo e' confrontare implementazioni diverse della stessa
idea (LLM per la semantica, pyAgrum per il calcolo esatto, rete Insurance,
esecuzione locale) senza che le copie divergano. Una variante non e' una copia
del progetto: e' **solo il modulo di orchestrazione**, poche decine di righe
dietro un'interfaccia comune. Il core (le copie corrette in consegna/, il grafo,
l'harness energetico) resta uno e condiviso, cosi' due varianti differiscono per
quello che dichiarano di cambiare e non per un fix applicato a una sola.

Interfaccia di una variante. Ogni modulo in questa cartella espone:

    NOME          str, il nome con cui viene registrata e scritta nei risultati
    DESCRIZIONE   str, una frase su cosa fa
    CAMBIA        str, cosa cambia rispetto a b_base (il riferimento)
    ro            il modulo run_orchestrato, per Misura e per i parser
    async def run(task, misura, **kw) -> dict

`kw` porta i parametri per riga che l'harness conosce e la variante non deve
indovinare: `path_rete` (la rete da dare al tool, richiesta dal benchmark con le
CPT perturbate). Una variante che non usa un parametro lo inoltra a
`ro.run`, non lo ignora: ignorarlo significherebbe eseguire su una rete diversa
da quella dell'oracolo.

`run` restituisce lo stesso dizionario di run_orchestrato.run (etichetta,
traduzione, numero, steps, misura, totale). L'harness aggiunge variante,
provenienza e ripetizione: la variante non deve scriverle da se'.

Regola dura. **Nessun fallback silenzioso**: se una variante non riesce a fare
quello che dichiara (per esempio Ollama rifiuta lo schema di uscita), solleva o
lascia propagare l'eccezione. Non ripiega di nascosto sulla variante base,
altrimenti il confronto misura due cose con la stessa etichetta.

Esecuzione. Una variante per processo, mai due in parallelo: l'energia e' del
package CPU e due processi la sporcano. Lo sviluppo puo' essere parallelo,
l'esecuzione no.
"""

import hashlib
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# le copie stanno in consegna/: un __pycache__ la' dentro non deve nascere
sys.dont_write_bytecode = True


def core():
    """Il modulo run_orchestrato, caricato una sola volta e condiviso.

    run_orchestrato legge sys.argv all'import (i suoi flag) e a sua volta carica
    run_query, che cambia la CWD nella cartella delle copie. Va quindi importato
    dopo che l'harness ha preparato sys.argv, e una sola volta: un secondo
    caricamento rieseguirebbe l'iniezione dei client.
    """
    if "run_orchestrato" in sys.modules:
        return sys.modules["run_orchestrato"]
    percorso = ROOT / "run_orchestrato.py"
    spec = importlib.util.spec_from_file_location("run_orchestrato", percorso)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


REGISTRO = {
    "b_base": "b_base.py",
    "b_vincolata": "b_vincolata.py",
    "b_solo_numero": "b_solo_numero.py",
    "b_verificata": "b_verificata.py",
    "b_esempi": "b_esempi.py",
    "b_composta": "b_composta.py",
}

# File la cui identita' deve comparire in ogni risultato: senza questi hash, fra
# sei run non si sa piu' quale codice ha prodotto quale numero.
CORE_FILES = (
    ROOT / "run_orchestrato.py",
    ROOT / "run_query.py",
    # la verifica della traduzione decide quali voci arrivano al tool: senza il
    # suo hash due run `b_verificata` non sono confrontabili fra loro
    ROOT / "traduzione_controllata.py",
    # vale lo stesso per il passo di classificazione: la regola di forma e gli
    # esempi stanno qui, non nel prompt della relatrice, che e' immutabile
    ROOT / "classificazione_controllata.py",
    ROOT / "consegna" / "agents_corretto.py",
    ROOT / "consegna" / "tools_corretto.py",
    ROOT / "consegna" / "funtions_corretto.py",
    ROOT / "consegna" / "insurance_grafo.bif",
)


def carica(nome: str):
    """Carica il modulo della variante `nome` dal registro."""
    if nome not in REGISTRO:
        raise SystemExit(
            f"variante sconosciuta: {nome!r}; registrate: {', '.join(sorted(REGISTRO))}")
    percorso = HERE / REGISTRO[nome]
    spec = importlib.util.spec_from_file_location(f"variante_{nome}", percorso)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def provenienza(nome: str) -> dict:
    """SHA-256 della variante e del core, per la tracciabilita' del risultato."""
    percorsi = [HERE / REGISTRO[nome], *CORE_FILES]
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in percorsi
    }