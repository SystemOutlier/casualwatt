"""Via B con il classificatore addestrato sulle quattro forme, senza esempi nel benchmark.

Perche' esiste. Sulle 81 righe dev dell'01-11 l'etichetta e' giusta 20/20 in tre
rami su quattro e 1/21 nel quarto: le cond_prob ("Given that X, how likely is it
that Y?") vanno in `coherence`, e in 15 casi su 21 il numero stampato e' quello
giusto perche' il ramo `coherence` calcola la stessa probabilita' e la riporta
dentro un giudizio. E' il guasto che costa di piu' nello screening -- 20 righe
perse su un calcolo che era gia' giusto -- e non dipende dai joule ne' dal
traduttore.

Cosa cambia rispetto a b_base. **Soltanto il passo `classificator`**, e soltanto
nel suo prompt: `label_inst` della relatrice resta identico e viene seguito dalla
regola di forma e da un esempio per etichetta
(`classificazione_controllata.py`). Il traduttore resta `translator_senza_tool`
con il suo prompt, senza schema e senza validazione: sono gli ingredienti di
b_verificata, e tenerli fuori e' quel che permette di dire quale dei due ha
spostato quale riga.

Perche' un esempio e non uno schema. `b_vincolata` vincola l'uscita a un enum e
l'etichetta smette di essere illeggibile, ma resta sbagliata: uno schema dice quali
parole sono ammesse, non quale scegliere. Sulle cond_prob l'enum ha portato
l'etichetta da 1/21 a 3/21 (dev, 01-11), cioe' 2 righe su 21. La scelta si cura con
la regola che distingue le forme, non con il vincolo di decodifica.

Nessun fallback silenzioso. La variante non corregge l'etichetta a mano: se il
modello scrive `coherence` su una cond_prob anche con gli esempi davanti, la riga
resta sbagliata e lo screening la conta fra le perse.

Costo dichiarato. Il passo classificator passa da 275 a ~590 token di prompt per
riga (`classificazione_controllata.py`, sezione 'Costo dichiarato'), sempre gli
stessi su tutte le righe, quindi nel prefisso riusato dalla cache dei prompt di
Ollama. Il confronto con b_base si fa su `j_per_corretta`: se le corrette salgono
da 6 a 26 il costo e' pagato, se restano 6 la variante va scartata.

Misurato. Dev dell'01-11 ore 18:12: **21/81 corrette (25,9%)** contro le 6/81 di
b_base, con `mappatura_ok` fermo a 20/81. Per ramo: cond_prob 17/21, inter 4/20,
coherence 0/20, counterfactual 0/20. Il numero che decide pero' e'
`etichetta_ok = 81/81`: l'instradamento errato non esiste piu' in nessun ramo, e
cond_prob passa da 1/21 a 17/21 corrette con lo stesso traduttore di b_base.

I tre guasti che restano sono del traduttore e sono tre, non uno: counterfactual
fallisce 20/20 con `ValueError: counterfactual: serve esattamente una variabile di
input` perche' il target e' ripetuto dentro `input`; inter fallisce 11/20 con
`InvalidArgument: The 3 parts of the query (on, doing, knowing) must be pairwise
disjoint`, che e' lo stesso difetto visto dal ramo che interviene; coherence non
fallisce per niente -- 17 righe su 20 arrivano in fondo con un numero, e il numero
e' quello sbagliato. Etichette e mappature sono ora due guasti separati e
misurati ciascuno: per questo esiste `b_composta`, che mette insieme questa regola
di forma e la validazione di `b_verificata`.

Uso:  python harness/esegui_variante.py --variante b_esempi ...
"""

import classificazione_controllata as CC
from varianti import core

ro = core()

NOME = "b_esempi"
DESCRIZIONE = ("via B con il classificatore ancorato alla forma della domanda: "
               "regola di forma e un esempio per etichetta dopo il prompt originale")
CAMBIA = ("solo il passo classificator: istruzioni = label_integro + regola + 4 esempi; "
          "traduttore e spiegazione invariati, nessuno schema")

_CLASSIFICATORE = None


def classificatore():
    """Il Classificatore della variante, sul client delle copie.

    `agents` esiste dopo `core()`, che ha gia' caricato run_query all'import di
    questo modulo. Il client e' `gpt5` (`agents_corretto.py:44`), lo stesso che
    `agents_corretto.py:76` monta su `classificator`: la variante cambia le
    istruzioni, non il modello.
    """
    global _CLASSIFICATORE
    if _CLASSIFICATORE is None:
        import agents
        _CLASSIFICATORE = CC.Classificatore(agents.gpt5)
    return _CLASSIFICATORE


async def run(task: str, misura, **kw) -> dict:
    # kw porta path_rete e spiegazione dal benchmark o dalle altre varianti
    return await ro.run(task, misura, classificatore=classificatore(), **kw)
