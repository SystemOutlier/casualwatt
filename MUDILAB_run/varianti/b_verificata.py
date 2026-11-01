"""Via B con il passo di traduzione reso verificabile.

Perche' esiste. Lo screening del 01-11 sul dev (81 righe, llama3.2:3b) porta tutte
e tre le varianti fra 6 e 7 risposte corrette, e le cause sono fuori dal calcolo:
75 righe su 81 si perdono nel dizionario che il traduttore passa al tool
(`traduzione_controllata.py` le conta una per una, con i JSON di origine). Un
vincolo di decodifica come b_vincolata non le tocca, perche' quelle righe hanno
gia' un JSON di forma corretta con dentro nomi che il grafo non ha o che la query
non menziona.

Cosa cambia rispetto a b_base. **Soltanto il passo `translator`**, in tre punti
che stanno insieme perche' l'uno senza l'altro non chiude:
  1. il prompt della relatrice resta identico e viene **seguito**, non riscritto,
     dal vocabolario dei 27 nodi con i loro stati, letto con `gum.loadBN` sullo
     stesso file che terra' in mano il tool. Serve perche' l'elenco interpolato
     nel prompt originale viene da `node_descr`, che ha voci malformate;
  2. la risposta chiede anche `citazioni`: per ogni variabile usata, le parole
     della query da cui e' stata presa. E' il materiale che rende verificabile
     l'estrazione;
  3. `traduzione_controllata.valida` scarta prima del tool cio' che non e' nel
     grafo, non e' citato, o ripete il target, e scrive ogni voce scartata nel
     JSON. Se il ramo richiede una sola evidenza e ne restano due, la riga viene
     rifiutata con il motivo: il codice non sceglie al posto del modello.

La citazione si pretende sull'`input`, non sull'`output`, e la ragione e' misura.
Nello screening dell'01-11, con la citazione obbligatoria anche sul target, su 45
righe con un output leggibile 40 sono state rifiutate per quel controllo: 20 con
il target giusto e 20 con il target sbagliato, cioe' il filtro non separa niente.
`replay_traduzione.py` lo gira a ritroso sugli stessi testi e conta 15 corrette con
la pretesa, 16 se la citazione si verifica solo quando c'e', 21 se non si chiede.
Il replay riproduce il run reale riga per riga (15 corrette, 46 rifiutate = le
`n_falliti` dell'harness), quindi quei numeri sono dello stesso metro del run. Da
qui `citazione_output=False` in `traduttore()`: il target resta vincolato a essere
un nodo del grafo con uno stato legale, che e' il controllo che regge; la frase
citata la si chiede solo li' dove distingue, cioe' sull'evidenza.

Il classificatore resta come in b_base, senza schema: questa variante misura il
costo e il guadagno del solo passo di traduzione. L'etichetta sbagliata
(`coherence` al posto di `backward_reasoning`, osservata su 20 righe di cond_prob)
e' un guasto diverso, e misurarlo qui dentro vorrebbe dire attribuire al
traduttore anche cio' che non e' suo.

Nessun fallback silenzioso. `run_orchestrato.run` con `traduttore` dato non
ripassa mai da `dizionario_dal_testo`: una verifica che rifiuta produce una riga
fallita dichiarata, non una riga passata con la mappatura non verificata.

Costo dichiarato. Il prompt del traduttore cresce del vocabolario (~250 token) e
la risposta cresce delle citazioni, quindi il confronto con b_base si fa su
`j_per_corretta` e non sui joule assoluti: qui il numeratore sale e il
denominatore deve salire piu' di lui, altrimenti la variante non serve.

Misurato. Con la citazione obbligatoria anche sul target: **15/81 corrette** contro
le 6/81 di b_base (dev, 01-11 ore 17:45, `valutazione_dev.json`), tutto il guadagno
su counterfactual (0/20 -> 10/20, la regola `disgiunzione`). Il replay sulle stesse
identiche risposte dei modelli prevedeva 21/81 senza quella pretesa; il run fatto
con `citazione_output=False` (dev, 01-11 ore 18:30, 21 righe rifiutate contro le 46
di prima) da' **22/81**: counterfactual 12/20, inter 7/20, coherence 2/20,
cond_prob 1/21. Il +1 sul replay e' una riga la cui traduzione cambia perche'
questa e' una risposta nuova, non la risposta replayata: i due numeri non sono lo
stesso oggetto e vanno tenuti distinti.

Guasto collaterale trovato dallo stesso run. `b_base` e `b_esempi`, che non hanno
la verifica, si fermano minutes su due righe `intervention` (INT09 219 s, INT17
169 s contro mediana 11 s, INT17 in `bad allocation`) perche' arrivano a
`csl.causalImpact` con una mappatura che duplica il target: il processo arriva a
25,97 GB di `PeakWorkingSetSize` (letto da `sonda_processo_run.py`). Questa
variante le due righe le rifiuta *prima* del tool, e il campionatore agganciato
al run delle 18:30 non ha mai visto un picco sopra 0,18 GB su 1970 campioni, con
la RAM della macchina mai sotto 18,3 GB. Non e' un argomento di precisione: e'
che un run misurato tenuto con il traduttore non verificato puo' fermarsi per
colpa del layer causale, e il joule che misura in quella finestra non e' piu' la
richiesta, e' il paging.

Uso:  python harness/esegui_variante.py --variante b_verificata ...
"""

import traduzione_controllata as TC
from varianti import core

ro = core()

NOME = "b_verificata"
DESCRIZIONE = ("via B con il traduttore ancorato al grafo: vocabolario letto dal "
               "BIF, citazioni obbligatorie sulle evidenze (non sul target, "
               "misurato), scarto dichiarato prima del tool")
CAMBIA = ("solo il passo translator: prompt + vocabolario del grafo + chiave "
          "'citazioni', e validazione nel codice; classificatore invariato")

# Lo schema chiede la forma, non il contenuto: `additionalProperties` non sa
# dire "una chiave per ogni variabile usata", e infatti il contenuto lo verifica
# `valida`. Senza schema la terza chiave arriverebbe in modo intermittente e la
# verifica rifiuterebbe righe buone per colpa della fortuna.
SCHEMA_TRADUZIONE = {
    "type": "json_schema",
    "json_schema": {
        "name": "traduzione_verificabile",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "input": {"type": "object", "additionalProperties": {"type": "string"}},
                "output": {
                    "type": "object",
                    "minProperties": 1,
                    "maxProperties": 1,
                    "additionalProperties": {"type": "string"},
                },
                "citazioni": {
                    "type": "object",
                    "minProperties": 1,
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["input", "output", "citazioni"],
            "additionalProperties": False,
        },
    },
}

OPZIONI_PASSI = {"translator": {"response_format": SCHEMA_TRADUZIONE}}

_TRADUTTORE = None


def traduttore():
    """Il Traduttore della variante, costruito una volta sul client delle copie.

    `agents` esiste solo dopo che `core()` ha caricato run_query, che e' gia'
    avvenuto all'import di questo modulo; il client e' `gpt5` (`agents_corretto.py:44`),
    lo stesso su cui `agents_corretto.py:116` monta `translator`.
    """
    global _TRADUTTORE
    if _TRADUTTORE is None:
        import agents
        _TRADUTTORE = TC.Traduttore(agents.gpt5, citazione_output=False)
    return _TRADUTTORE


async def run(task: str, misura, **kw) -> dict:
    # kw porta path_rete dal benchmark: il vocabolario si legge su quella rete
    return await ro.run(task, misura, opzioni_passi=OPZIONI_PASSI,
                        traduttore=traduttore(), **kw)
