"""Via B senza il terzo passo: si restituisce il numero del tool, niente prosa.

Perche' esiste. Nella via B il numero e' gia' esatto e lo calcola il codice: la
spiegazione e' un costo, non un passaggio del calcolo. Con due passi di modello
invece di tre la domanda diventa quanto costa quella prosa, in joule per
risposta corretta, e se serve al compito.

Cosa cambia rispetto a b_base. `spiegazione=False` in `run_orchestrato.run`:
traduttore e classificatore restano identici, la chiamata a cau_inference resta
identica, il JSON dichiara `"spiegazione": false`. Nessun prompt viene toccato.

Limite dichiarato. Non e' un metodo equivalente a b_base: la risposta che
l'utente legge e' il numero del tool e basta. Se il confronto si fa su
"risposta corretta" definite come numero giusto, la variante e' avvantaggiata
di tutto il costo della spiegazione, ed e' esattamente cio' che si vuole
misurare; se il deliverable richiede la spiegazione, questa variante non lo
soddisfa ed e' il confronto a dirlo, non il benchmark.

La misura resta quella degli altri: stesse finestre, stessi bordi, stesso
canale. Il risparmio che si legge e' del passo in meno, non dell'harness.
"""

from varianti import core

ro = core()

NOME = "b_solo_numero"
DESCRIZIONE = "via B con due passi di modello: il numero del tool senza spiegazione"
CAMBIA = "spiegazione=False: salta il terzo passo (causal_A)"


async def run(task: str, misura, **kw) -> dict:
    return await ro.run(task, misura, spiegazione=False, **kw)
