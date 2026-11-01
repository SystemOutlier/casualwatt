"""Il passo di classificazione ancorato alla forma della domanda.

Perche' esiste. Lo screening dell'01-11 sul dev (`harness/risultati/*/riepilogo.json`,
`valutazione_dev.json`) dice che llama3.2:3b non e' un modello che sbaglia a caso:
l'etichetta esce giusta 20/20 su coherence, 20/20 su counterfactual e 20/20 su
intervention, e 1/21 su cond_prob. Le venti cond_prob su ventuno vanno in
`coherence`, e in quindici casi su ventuno il numero stampato e' comunque quello
giusto: il ramo `coherence` calcola P(target | evidenza) e lo riporta dentro un
giudizio, quindi la domanda riceve la risposta corretta instradata dal ramo
sbagliato. Il guasto e' circoscritto e ha una ragione leggibile nel prompt.

La ragione e' la quinta riga di `label_inst` delle copie (`agents_corretto.py:68`):
`coherence: when the task is to understand if two conditions are compatible or
conflicting`. Una query di forma "Given that the driving quality is normal, how
likely is it that the age of the driver is senior?" **contiene** due condizioni, e
un modello da 3 miliardi le legge come "due condizioni da confrontare". Il
criterio del prompt non distingue le due forme perche' descrive il *significato*
delle etichette e non la *superficie* della domanda; sulla superficie, le quattro
forme del benchmark si distinguono per tre parole ("how likely", "Is it coherent",
"if we intervene", "if the world had been").

Cosa fa. Aggiunge al testo della relatrice, che resta identico e viene solo
seguito, due cose:

  1. la regola di scelta fra le quattro forme, detta come regola di forma e non di
     significato, perche' e' la forma cio' che il classificatore puo' leggere;
  2. un esempio per etichetta, presi dalla rete Insurance e non dal benchmark,
     perche' `label_inst` chiude gia' con un esempio medico ("fever/infection") e
     il modello piccolo a quell'esempio guarda.

Nessuna modifica al prompt della relatrice. `label_inst` non si tocca, non si
riordina, non si accorcia: `istruzioni_classificatore()` restituisce il suo testo
seguito dalle aggiunte, e l'autoverifica lo verifica carattere per carattere. Se
un domani il testo originale cambia, l'autoverifica si ferma.

Nessun fallback silenzioso. L'etichetta resta quella che il modello scrive: questa
nota non converte un "coherence" in "backward_reasoning" per via di regex, perche'
allora il numero lo sceglierei io e non la pipeline. Se il modello sbaglia anche
con la forma davanti, la riga resta sbagliata e lo screening lo conta.

Costo dichiarato. `label_inst` e' 1092 caratteri e il passo classificator di b_base
legge 275 token di input (`harness/risultati/b_base/20261101_150815/COH01_r1.json`,
`steps[1].tokens`): la regola di forma e gli esempi aggiungono 1403 caratteri, cioe'
circa 315 token, e il passo passa da 275 a ~590 token di prompt. Non e' gratis: va
misurato in `j_per_corretta` contro b_base, non in joule assoluti, perche' le risposte
corrette in piu' stanno nel denominatore. Il testo e' identico su tutte le righe,
quindi sta nel prefisso e Ollama lo riusa dalla cache dei prompt (`cache_prompt`,
`run_orchestrato.py:530`): il costo pieno lo paga la prima riga di ogni run, non
tutte. `--scarta-primo-run` dell'harness esiste per questo.

Limite onesto sul cosa dimostri. Le quattro forme sono i quattro template di
`benchmark/genera.py:456-472`, quindi gli esempi sono presi dalla stessa
distribuzione delle query del benchmark: su questo benchmark la variante misura il
riconoscimento di una forma nota, non la generalizzazione a forme nuove. E' il
confronto giusto per dire "quante righe recupera", non per dire "il modello
capuisce l'inferenza causale". La forma generica resta quella di `label_inst`.

Uso:  MUDILAB_COPIE=1 python classificazione_controllata.py --autoverifica
      (--rete per una BIF diversa dal default)
"""

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True

# Regola di forma. Scritta come scelta fra quattro superfici perche' e' la
# superficie cio' che distingue cond_prob da coherence: il significato, nel prompt
# della relatrice, sovrappone le due categorie.
REGOLA_FORMA = """
Choose the label from the FORM of the question, not from how many conditions it
names. A question can name three conditions and still ask for one probability:
- "Given that <value>, how likely is it that <value>?" -> backward_reasoning: the
  "given" clause is evidence, not a compatibility test.
- "Is it coherent that <value> given that ... and that ...?" -> coherence: the
  only form that asks whether statements fit together, not for a probability.
- "... if we intervene to make it so that <value>?" -> intervention.
- "We observed ... What would the probability that <value> be if the world had
  been such that <value>?" -> counterfactual.
"""

# Un esempio per etichetta: (query, etichetta, {nodo: stato} citati nella query).
# Le frasi seguono i nomi e gli stati della rete Insurance vera, non del
# benchmark: `autoverifica` controlla che ogni nodo e ogni stato esistano nel grafo
# e che nessuna di queste quattro query compaia nello split held-out.
ESEMPI = (
    ("Given that the car is a current-year model, how likely is it that the "
     "driver is a senior?",
     "backward_reasoning", {"VehicleYear": "Current", "Age": "Senior"}),
    ("Is it coherent that the medical cost is one million dollars given that the "
     "driver quality is poor and that the car is as fragile as an eggshell?",
     "coherence", {"MedCost": "Million", "DrivQuality": "Poor", "RuggedAuto": "EggShell"}),
    ("What is the probability that the car is stolen if we intervene to make it "
     "so that the cushioning is excellent?",
     "intervention", {"Theft": "True", "Cushioning": "Excellent"}),
    ("We observed that the car has an anti-theft device and that the car is worth "
     "one million dollars. What would the probability that the car is worth one "
     "million dollars be if the world had been such that the car has no "
     "anti-theft device?",
     "counterfactual", {"AntiTheft": "True", "CarValue": "Million"}),
)


def blocco_esempi() -> str:
    """I quattro esempi nella forma gia' usata da `label_inst` (User/Assistant)."""
    righe = ["Examples on the insurance network:", ""]
    for query, etichetta, _ in ESEMPI:
        righe.append(f"User: '{query}'")
        righe.append(f"Assistant: {etichetta}")
        righe.append("")
    return "\n".join(righe).rstrip() + "\n"


def istruzioni_classificatore() -> str:
    """`label_inst` della relatrice, seguito dalla regola di forma e dagli esempi.

    L'import e' dentro la funzione: il modulo `agents` esiste solo dopo che
    `run_query.py` ha installato le copie, e un import in testa renderebbe questo
    file caricabile solo a pipeline gia' montata.
    """
    import agents
    return agents.label_inst + REGOLA_FORMA + "\n" + blocco_esempi()


class Classificatore:
    """Il passo di classificazione come oggetto, sullo stesso modello delle copie.

    Serve a `run_orchestrato.run(..., classificatore=...)`, che chiama `agente()`
    per il secondo passo. L'agente si costruisce una volta: le istruzioni non
    dipendono dalla rete ne' dalla riga, quindi una sola istanza vale per tutto il
    run e il suo prefisso resta lo stesso, che e' quel che serve alla cache.
    """

    def __init__(self, cliente):
        self._cliente = cliente
        self._agente = None

    def agente(self):
        from agents import Agent
        if self._agente is None:
            self._agente = Agent(name="Classificator", client=self._cliente,
                                 instructions=istruzioni_classificatore())
        return self._agente


# ---------------------------------------------------------------------------
# autoverifica: nessun modello, nessuna query del benchmark eseguita
# ---------------------------------------------------------------------------

def _etichette_del_prompt(label_inst: str) -> list:
    """Le etichette che il prompt della relatrice stessa elenca.

    Si prende l'elenco da li' e non da `run_orchestrato.ETICHETTE` perche' la
    domanda da verificare e' 'gli esempi usano etichette che il modello vede fra
    le ammesse', e quello che il modello vede e' il prompt.
    """
    for riga in label_inst.splitlines():
        if "following labels" in riga:
            # la riga chiude con un punto: "influence, counterfactual." e senza
            # toglierlo l'ultima etichetta risulta non ammessa
            return [e.strip(" .,") for e in riga.split(":")[-1].split(",") if e.strip(" .,")]
    raise ValueError("il prompt della relatrice non elenca piu' le etichette")


def autoverifica(rete: str | None = None) -> bool:
    import agents
    from traduzione_controllata import vocabolario

    voc = vocabolario(rete)
    ammesse = _etichette_del_prompt(agents.label_inst)
    testo = istruzioni_classificatore()
    esiti = []

    # 1. il testo della relatrice resta la testa delle istruzioni, carattere per
    #    carattere: senza questo controllo "aggiunto" e "modificato" diventano la
    #    stessa parola.
    esiti.append(("prompt della relatrice integro",
                  testo.startswith(agents.label_inst)))

    # 2. ogni esempio dichiara un'etichetta che il prompt ammette, e la stessa
    #    etichetta compare alla fine dell'esempio.
    for query, etichetta, _ in ESEMPI:
        esiti.append((f"etichetta {etichetta} ammessa dal prompt",
                      etichetta in ammesse))
        esiti.append((f"esempio [{query[:40]}...] chiude con {etichetta}",
                      f"Assistant: {etichetta}" in blocco_esempi()))

    # 3. nodi e stati degli esempi esistono nel grafo che il tool leggerà: un
    #    esempio con uno stato inventato insegna al modello a inventare stati.
    for query, etichetta, nominati in ESEMPI:
        for nodo, stato in nominati.items():
            esiti.append((f"[{etichetta}] {nodo} e' un nodo del grafo", nodo in voc))
            esiti.append((f"[{etichetta}] {nodo}={stato} e' uno stato ammesso",
                          nodo in voc and stato in voc[nodo]))

    # 4. nessuna query di esempio appartiene allo split held-out: insegnare al
    #    modello la domanda su cui verra' giudicato gonfierebbe il numero.
    import csv
    held = set()
    with open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            if riga["split"] == "held-out":
                held.add(riga["query"].strip())
    for query, etichetta, _ in ESEMPI:
        esiti.append((f"[{etichetta}] esempio fuori dall'held-out",
                      query.strip() not in held))

    mancati = [nome for nome, ok in esiti if not ok]
    for nome, ok in esiti:
        print(f"  {'[ok ]' if ok else '[KO ]'} {nome}")
    print(f"\nregole verificate: {len(esiti)}, mancanti: {len(mancati)}")
    print(f"lunghezza istruzioni: {len(agents.label_inst)} originale + "
          f"{len(testo) - len(agents.label_inst)} aggiunta "
          f"({100 * (len(testo) - len(agents.label_inst)) / len(agents.label_inst):.0f}% di caratteri in piu')")
    return not mancati


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--autoverifica", action="store_true")
    ap.add_argument("--rete", default=None)
    a = ap.parse_args()
    if not a.autoverifica:
        raise SystemExit("senza --autoverifica questo modulo non fa niente: "
                         "la classificazione senza modello non esiste")
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie
    raise SystemExit(0 if autoverifica(a.rete) else 1)
