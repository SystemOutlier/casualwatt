"""Le etichette del classificatore come lettura di testo, senza modello e senza copie.

Perche' esiste. `etichetta_ok` di `benchmark/valuta.py` valeva, fino al 02-11,
`risultato.get("etichetta") == gt["etichetta_attesa"]`, e la chiave `etichetta`
viene scritta da `run_orchestrato.run` **solo** quando la riga arriva al tool: i
due percorsi d'errore (`except ValueError` a :452 e `except Exception` a :470)
escono senza. Sull'held-out misurato del 02-11 questo ha fatto leggere 138 etichette
giuste su 240, cioe' esattamente il numero dei superstiti del gate, e il report
diceva "l'etichetta e' giusta solo 17/60 sul ramo inter". Falso: ripassando i
240 testi registrati del passo `classificator` con il parser che usa il run,
l'etichetta attesa compare in **240/240** testi. La misura che sembrava del
classificatore misurava il gate.
Vedi `harness/risultati/analisi_rami_deboli_20261102.txt`, sezione 6.

Cosa fa. Estrae dalla risposta del classificatore le etichette che `cau_inference`
sa instradare, cercate per sottostringa e in ordine di comparsa. Nessuna delle due
funzioni tocca Ollama, le copie della relatrice, pyAgrum o il contatore: sono due
`str.find` su una tupla di cinque parole.

Perche' sta in un modulo a se' e non in `run_orchestrato.py`. Il valutatore deve
poter rileggere gli artefatti gia' scritti, e `run_orchestrato` all'import esegue
`rq = _carica_runner()` (:103), che carica `run_query`: quel modulo monta le copie
della relatrice e fa `chdir` nella consegna. Importarlo da `valuta.py` vorrebbe
dire montare la pipeline per leggere un JSON. La stessa ragione vale per
`replay_traduzione.py`, che finora quell'import lo faceva dentro una funzione e
per questo qui riusa lo stesso nome.

Perche' la ricerca e' per sottostringa e non a parola esatta. Un modello piccolo
risponde con una frase invece che con una parola sola (misurato con
tinyllama:latest: "You have classified the query ... as: - Influence: ..."). Vale
la **prima** citata, che e' quella che il modello dichiara; le altre restano nel
JSON perche' un testo ambiguo si deve vedere, non interpretare in silenzio.

Limite dichiarato, e non un bug da nascondere. La sottostringa accetta anche un
"non e' coherence" come "coherence": il parser legge la superficie, non la
negazione. E' la stessa regola che ha prodotto i numeri della misura, quindi
cambiarla qui invalidarebbe il confronto con gli artefatti registrati; chi vuole
il testo ambiguo lo ha in `etichette_nel_testo`, riga per riga.

Uso:  python -c "import etichette; print(etichette.etichetta_dal_testo(open(...).read()))"
      (nessuna variabile d'ambiente necessaria)
"""

# Le cinque etichette che `cau_inference` sa instradare (tools.py:51-118 nella
# copia). L'ordine non conta: la ricerca e' per posizione nel testo.
ETICHETTE = ("backward_reasoning", "intervention", "coherence", "influence", "counterfactual")


def etichette_nel_testo(testo: str) -> list:
    """Etichette ammesse citate nella risposta, in ordine di comparsa."""
    basso = (testo or "").lower()
    posizioni = sorted((basso.find(e), e) for e in ETICHETTE if e in basso)
    return [e for _, e in posizioni]


def etichetta_dal_testo(testo: str) -> str:
    """La prima etichetta ammessa citata nella risposta del classificatore."""
    trovate = etichette_nel_testo(testo)
    if not trovate:
        # `str(...)` perche' il testo puo' arrivare come None da un JSON senza il
        # passo: l'ecceione deve dire "nessuna etichetta", non esplodere sulla
        # fetta di None (misurato: `None[:200]` e' un TypeError).
        raise ValueError(f"nessuna delle {len(ETICHETTE)} etichette nel testo: {str(testo)[:200]!r}")
    return trovate[0]


def etichetta_dal_testo_o_nulla(testo: str):
    """Come `etichetta_dal_testo`, ma senza eccezione: None se il testo non ne cita.

    Serve a chi legge artefatti gia' scritti e deve distinguere "il passo non c'e'"
    da "il passo c'e' ma non dichiara un'etichetta": il primo caso non e' una
    misura, il secondo e' un esito del classificatore e va contato.
    """
    try:
        return etichetta_dal_testo(testo)
    except ValueError:
        return None
