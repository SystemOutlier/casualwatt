"""
Il classificatore sa emettere `counterfactual`? E la quinta etichetta sposta
le altre nove?

Prova due prompt sullo stesso modello, lo stesso endpoint (/v1 di Ollama) e la
stessa temperatura (0):

  - 4 etichette: il `label_inst` originale di MUDILAB/agents.py
    (backward_reasoning, intervention, coherence, influence);
  - 5 etichette: quello di consegna/agents_corretto.py, che aggiunge
    counterfactual con un criterio e chiede una sola parola minuscola.

Per ognuna delle 12 query di ground_truth.csv registra cosa risponde. Il
confronto che conta e' doppio: le 3 controfattuali devono passare da una
delle quattro etichette a `counterfactual`, e le altre 9 devono restare dove
sono. Se una delle due cose non accade, il risultato si riporta com'e'.

Uso: python verifica_classificatore.py [--modello tinyllama:latest] [--ripetizioni 3]

Esce 0 se le 3 controfattuali sono riconosciute e le 9 restano stabili,
1 altrimenti (con il conteggio di cosa si e' spostato).
"""

import argparse
import ast
import csv
import json
import sys
import urllib.request
from collections import Counter
from pathlib import Path

QUI = Path(__file__).resolve().parent
# nella cartella di lavoro le copie stanno in `consegna/`, nello zip scompattato
# sono accanto a questo script
CONSEGNA = QUI if (QUI / "agents_corretto.py").exists() else QUI / "consegna"
GT = CONSEGNA / "ground_truth.csv"
URL = "http://localhost:11434/v1/chat/completions"
URL_CHAT = "http://localhost:11434/api/chat"

ETICHETTE = ["backward_reasoning", "intervention", "coherence", "influence",
             "counterfactual"]

ATTESA = {
    "cond_prob": "backward_reasoning",
    "inter": "intervention",
    "coherence": "coherence",
    "counterfactual": "counterfactual",
}

# il prompt originale, ricopiato da MUDILAB/agents.py:22-33 senza aggiunte
PROMPT_4 = (
    "You are an expert in causal relationships.\n"
    "You HAVE TO classify the user task with ONE of the following labels : "
    "backward_reasoning, intervention, coherence, influence. \n"
    "Use the following criterios to assign the label: \n "
    "-backward_reasoning: when the task is to estimate the probability of a causal node given conditional information observed on its child nodes.\n"
    "-intervention: when the task involves estimating the probability of one feature given a change made to another.\n"
    "- coherence: when the task is to understand if two conditions are compatible or conflicting.\n"
    "-influence: when the tasks involve performing interventions to fix two variables and studying how this impacts the causal influence of one feature on another\n"
    "Your answer will be JUST THE LABEL that you chose.\n "
    "Example: \n"
    "User: 'If I observe fever, what is the probability of infection?'\n"
    "Assistant: backward_reasoning\n"
)


def carica() -> list[dict]:
    with open(GT, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def legge_prompt_5() -> str:
    """Estrae label_inst da agents_corretto.py senza importare agent_framework."""
    sorgente = (CONSEGNA / "agents_corretto.py").read_text(encoding="utf-8")
    # rindex: la stessa assegnazione compare anche nel blocco originale
    # commentato, che comincia con "# label_inst = (" e non va letto.
    inizio = sorgente.rindex("\nlabel_inst = (") + 1
    fine = sorgente.index(")\n", inizio) + 2
    blocco = sorgente[inizio:fine]
    corpo = blocco[blocco.index("(") + 1:blocco.rindex(")")]
    righe = []
    for riga in corpo.splitlines():
        riga = riga.strip()
        if not riga:
            continue
        if not (riga.startswith('"') and riga.endswith('"')):
            raise ValueError(f"riga non letterale in label_inst: {riga!r}")
        righe.append(ast.literal_eval(riga))  # letterale del nostro file, non input esterno
    return "".join(righe)


def chiedi(modello: str, sistema: str, domanda: str, endpoint: str = "v1",
           timeout: float = 120.0) -> str:
    messaggi = [{"role": "system", "content": sistema},
                {"role": "user", "content": domanda}]
    if endpoint == "v1":
        corpo = {
            "model": modello,
            "messages": messaggi,
            "temperature": 0,
            "stream": False,
            "max_tokens": 128,
        }
        req = urllib.request.Request(
            URL, data=json.dumps(corpo).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            dati = json.loads(r.read().decode("utf-8"))
        return dati["choices"][0]["message"]["content"]
    # /api/chat: l'interfaccia nativa di Ollama, usata dal client ricostruito
    corpo = {
        "model": modello,
        "messages": messaggi,
        "stream": False,
        "options": {"temperature": 0, "num_predict": 128},
    }
    req = urllib.request.Request(
        URL_CHAT, data=json.dumps(corpo).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dati = json.loads(r.read().decode("utf-8"))
    return dati["message"]["content"]


def etichetta(testo: str, ammesse: list[str]) -> str:
    """L'etichetta emessa, se la risposta e' una sola parola ammessa.

    Il confronto e' esatto, a meno di spazi, virgolette, punti e recinzioni
    markdown: `cau_inference` confronta l'etichetta per uguaglianza (`tools.py:51`),
    quindi una parola ammessa citata dentro una frase non e' una classificazione
    e non va contata come tale. Quando la risposta non e' un'etichetta si
    riporta il testo fra parentesi quadre, cosi' si vede cosa ha scritto.
    """
    nudo = testo.strip().strip("\"'`*_ \t\r\n.:;!?").lower()
    if nudo in ammesse:
        return nudo
    return f"[{testo.strip()[:60]}]"


def e_etichetta(valore: str) -> bool:
    return not valore.startswith("[")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modello", default="tinyllama:latest")
    ap.add_argument("--ripetizioni", type=int, default=3)
    ap.add_argument("--endpoint", choices=["v1", "chat"], default="v1",
                    help="v1 = OpenAI-compatibile (quello del framework); chat = nativo Ollama")
    args = ap.parse_args()

    righe = carica()
    prompt_5 = legge_prompt_5()
    ammesse_4 = ETICHETTE[:4]

    esiti = {"4": {}, "5": {}}
    for chiave, sistema in (("4", PROMPT_4), ("5", prompt_5)):
        for r in righe:
            voti = []
            for _ in range(args.ripetizioni):
                testo = chiedi(args.modello, sistema, r["query"], args.endpoint)
                voti.append(etichetta(testo, ETICHETTE if chiave == "5" else ammesse_4))
            esiti[chiave][r["task_id"]] = voti

    print(f"modello: {args.modello}   endpoint: {args.endpoint}   "
          f"ripetizioni: {args.ripetizioni}   temperatura: 0")
    print()
    print(f"{'id':<5}{'attesa':<20}{'4 etichette':<34}{'5 etichette'}")
    print("-" * 92)
    spostate_altre = []
    non_classificate = []
    cf_ok = []
    for r in righe:
        tid = r["task_id"]
        attesa = ATTESA[r["task_type"]]
        a = Counter(esiti["4"][tid])
        b = Counter(esiti["5"][tid])
        a_txt = ", ".join(f"{k}x{v}" if v > 1 else k for k, v in a.most_common())
        b_txt = ", ".join(f"{k}x{v}" if v > 1 else k for k, v in b.most_common())
        print(f"{tid:<5}{attesa:<20}{a_txt:<34}{b_txt}")
        modo_a, modo_b = a.most_common(1)[0][0], b.most_common(1)[0][0]
        if r["task_type"] == "counterfactual":
            if modo_b == "counterfactual":
                cf_ok.append(tid)
        elif not (e_etichetta(modo_a) and e_etichetta(modo_b)):
            non_classificate.append(tid)
        elif modo_a != modo_b:
            spostate_altre.append(tid)

    print("-" * 92)
    print(f"controfattuali instradate come counterfactual: {len(cf_ok)}/3"
          + (f" ({', '.join(cf_ok)})" if cf_ok else ""))
    print(f"altre query che cambiano etichetta aggiungendo la quinta: "
          f"{len(spostate_altre)}" + (f" ({', '.join(spostate_altre)})" if spostate_altre else ""))
    print(f"altre query senza un'etichetta in risposta (confronto non possibile): "
          f"{len(non_classificate)}"
          + (f" ({', '.join(non_classificate)})" if non_classificate else ""))
    ok = len(cf_ok) == 3 and not spostate_altre
    print()
    print("ESITO:", "OK" if ok else "DA RIFERIRE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
