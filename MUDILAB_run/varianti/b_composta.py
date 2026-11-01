"""Le due correzioni che hanno funzionato, insieme: traduzione verificata ed etichetta per forma.

Perche' esiste. Il piano dichiarato all'inizio era "provare varie implementazioni e
dopo valutare la migliore o se fonderle". Questa e' la fusione, e la si fa perche'
le due varianti componenti toccano due passi diversi e non si disturbano:
`b_verificata` cambia il `translator` (vocabolario del grafo nel prompt, citazioni
sull'evidenza, scarto dichiarato prima del tool), `b_esempi` cambia il
`classificator` (regola di forma e un esempio per etichetta dopo il prompt della
relatrice). Nessun passo e' cambiato due volte, e nessun passo della variante
componente e' stato riscritto qui.

Cosa cambia rispetto a b_base. Entrambi i passi di routing, e solo loro: la
spiegazione resta, la rete resta quella della riga, l'energia resta misurata allo
stesso modo, i prompt originali restano testi integrali in testa alle istruzioni.

Perche' non basta sommare i numeri dei componenti. `b_verificata` recupera le righe
che arrivavano al tool con un'evidenza in piu' (counterfactual, 0/20 -> 10/20
sull'dev); `b_esempi` recupera le righe instradate su `coherence` pur avendo il
numero giusto (cond_prob, etichetta 1/21). Le due popolazioni di righe sono quasi
disgiunte, quindi la somma e' un'aspettativa, non un risultato: se una riga aveva
entrambi i guasti, la fusione la recupera una volta sola e il totale sta sotto la
somma. E' il numero di questa variante a dirlo, misurato, non l'aritmetica.

Nessun fallback silenzioso. Le due regole si applicano entrambe anche quando
l'altra ha gia' fermato la riga: una verifica che rifiuta produce una riga fallita
con il suo motivo, non un ripiegamento sul comportamento di b_base.

Misurato. Dev dell'01-11 ore 18:31 (`harness/risultati/b_composta/20261101_183106`):
**32/81 corrette (39,5%)** -- il migliore dei cinque screening -- con 20 righe
rifiutate prima del tool. Per ramo: counterfactual 11/20, inter 7/20, cond_prob
12/21, coherence 2/20. `etichetta_ok` e' 61/81 e non 81/81 perche' le venti righe
rifiutate escono senza etichetta e il metro le conta fra le non giuste: fra le 61
che un'etichetta la ricevono, la regola di forma di `b_esempi` la azzecca sempre.

La fusione e' sub-additiva, e il `confronto_varianti.py` dice dove: in comune con
`b_esempi` 12 righe, con `b_verificata` 21; nove righe che `b_esempi` prendeva
sono perse qui (CND02, CND10, CND14, CND21, CND26, CND33, CND38, INT26, INT33),
otto volte con il motivo "citazione non presente nella query" e una con "la
citazione non nomina ne' la variabile ne' lo stato". Leggendole una per una (il
punto e' il regime `senza-verbatim` di `replay_traduzione.py`, che toglie solo il
gate sulla frase) il modello riscrive
la frase con un soggetto diverso -- `the vehicle is an older model` contro
`the car is an older model` -- ma la parola dello stato la tiene, e in quelle
righe lo stato e' giusto. CND02 e' il caso opposto e va nella stessa regola: li'
lo stato e' inventato (`Normal` contro la `cautious` della query), e la verifica
lo ferma. Quindi la pretesa che l'intera frase sia un sottostringa della query
punisce la parafrasi insieme all'invenzione.

Il numero ora c'e' (`replay_traduzione.py`, regime `senza-verbatim`, 01-11, sugli
stessi 81 testi gia' registrati): tolto **solo** quel gate le corrette salgono da
32 a **40**, e le otto (CND14 CND21 CND26 CND33 CND38 COH01 INT21 INT33) si
aggiungono senza perdere nessuna delle 32 di prima -- perche' `senza-verbatim` e'
la regola di produzione meno una clausola, non un'altra regola; i rifiuti
scendono da 20 a 10. Il prezzo non e' nel conto, e' nel tipo di errore: CND02,
che oggi e' una riga rifiutata e dichiarata, con quella rilassatura arriva al
tool e stampa 0,704 contro lo 0,221 atteso, e INT26 torna a `bad allocation`.
Con la regola in produzione un'invenzione diventa un fallimento dichiarato; senza
il gate diventa una risposta sbagliata confidente. Quale delle due tenere e'
ancora una scelta di protocollo, ma ora la scelta ha il numero davanti: +8 righe
corrette in cambio di una riga che da dichiarata passa a errata.

L'unione delle righe corrette delle cinque varianti sul dev e' **43/81**: sta li'
il limite superiore di una fusione perfetta, e 38 righe non le prende nessuna. Il
numero vale pero' con la regola di citazione in produzione, ed e' il numero di un
metro, non una proprieta' delle varianti: con il gate sulla frase tolto, solo
`b_composta` ne prende 40 sulle stesse risposte, quindi l'unione sotto quella
regola non e' misurata e quel tetto e' da considerare una soglia inferiore. Sotto
il tetto misurato la scelta della variante e' `b_composta`; le 38 righe che non le
prende nessuna non sono un problema di orchestrazione.

Il resto ha pero' una forma, e sta nel ramo `coherence` (2/20 qui, 0/20 in
`b_esempi`, 2/20 in `b_verificata`: mai meglio di cosi'). Leggendole una per una,
sui JSON della corsa 18:31, si vede cosa: la domanda e' "Is it coherent that P given
Q and R", l'oracolo vuole `input` = {Q, R} e `output` = {P}, e il modello legge il ramo
al contrario o ne perde un pezzo. COH05 mette P in `input` (`ThisCarCost: Million`)
e una delle due evidenze in `output` (`ThisCarDam: Severe`); COH02 fa lo stesso
(`output: Age: Senior` contro il target `Antilock: True`); COH01 il target lo
indovina ma porta una sola delle due evidenze, e il metro `mappatura_ok` di
`valuta.py` vuole l'insieme esatto. La struttura passa sempre la verifica (un
sola chiave in `output`, chiavi nel vocabolario), quindi il tool non protesta e
stampo' una probabilita' conditioning su un sottoinsieme: 0,991 contro 0,98795
attesa su COH01, che e' vicino per caso e sbagliata di principio.
E' la correzione successiva dichiarata, non applicata: una regola di forma per il
ramo `coherence` nel prompt del traduttore, che dica che le `given that` sono
l'`input` e la reggente di "is it coherent that" e' l'`output`. Vale solo se sullo
screening dev sale `mappatura_ok`, non `corrette`, perche' qui il numero esce e non
viene fermato: e' il ramo dove il metro `corretta = etichetta e numero` e' il piu'
debole dei cinque.

Uso:  python harness/esegui_variante.py --variante b_composta ...
"""

import classificazione_controllata as CC
from varianti import core
from varianti.b_verificata import OPZIONI_PASSI, traduttore

ro = core()

NOME = "b_composta"
DESCRIZIONE = ("via B con i due passi di routing corretti insieme: traduttore "
               "ancorato al grafo con scarto dichiarato, e classificatore sulla "
               "forma della domanda")
CAMBIA = ("passo translator come b_verificata (citazione richiesta sull'input, non "
          "sull'output) e passo classificator come b_esempi; spiegazione invariata")

# Il traduttore e il suo schema si importano da b_verificata, non si riscrivono:
# due copie della stessa forma divergono, e la variante dovrebbe differire solo
# per quello che dichiara di cambiare.
_CLASSIFICATORE = None


def classificatore():
    global _CLASSIFICATORE
    if _CLASSIFICATORE is None:
        import agents
        _CLASSIFICATORE = CC.Classificatore(agents.gpt5)
    return _CLASSIFICATORE


async def run(task: str, misura, **kw) -> dict:
    return await ro.run(task, misura, opzioni_passi=OPZIONI_PASSI,
                        traduttore=traduttore(), classificatore=classificatore(), **kw)
