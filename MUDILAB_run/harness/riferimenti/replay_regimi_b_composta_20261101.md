# Replay dei due regimi di citazione sugli stessi testi registrati

Scritto il 01-11 alle 21:37, riesecuzione dello stesso metro sulla corsa gia'
registrata. Output del processo incollato per intero, non riscritto ne' arrotondato.

Comando:
  MUDILAB_COPIE=1 python replay_traduzione.py harness/risultati/b_composta/20261101_183106 \
      --regole "output=libero,senza-verbatim"

Perche' questo file esiste. La decisione 1 congela come regola primaria quella con il
gate sulla frase attivo (32/81) e ammette il 40/81 solo come analisi alternativa. Un
confronto del genere regge solo se i due numeri escono dagli stessi testi e dallo
stesso metro, e se il secondo dichiara anche cosa paga. Qui sta la riesecuzione che
ri-produce la coppia senza modelli: `valida` con la regola scelta,
`tools.cau_inference` sul dizionario verificato, `_confronta` di `benchmark/genera.py`
contro l'oracolo.

Unita' di conto: `corretta = etichetta_ok AND numero_ok`, su 81 righe dev.

---

cartella: 20261101_183106
righe con un testo di traduttore: 81, senza: 0

--- output=libero: 81 righe riprodotte
  corretta    32   es. CF01:
  numero      29   es. CF05: stampato [0.0, 0.348] atteso [0.0191, 0.1309]
  rifiutata   20   es. CF18: counterfactual: servono almeno 1 evidenza/e, restano []; sca
  corrette/prodotte = 32/81

--- senza-verbatim: 81 righe riprodotte
  corretta    40   es. CF01:
  numero      30   es. CF05: stampato [0.0, 0.348] atteso [0.0191, 0.1309]
  rifiutata   10   es. CF18: counterfactual: servono almeno 1 evidenza/e, restano []; sca
  tool         1   es. INT26: Exception: bad allocation
  corrette/prodotte = 40/81

---

## Cosa dice il confronto, e cosa non dice

`+8` corrette (32 → 40) e `-10` rifiuti (20 → 10) vengono dal gate tolto, che smette di
punire la parafrasi. Non e' lo stesso metro due volte: `registro_non_valutabili.md`
sezione 5 tiene separate le quattro quantita' e misura che la primaria accetta gia' 26
righe su 61 con una citazione del target che la regola stretta non copre.

I totali quadrano, e il quadratura e' il punto: nel primario 32+29+20 = 81, nel
rilassato 40+30+10+1 = 81. La riga in piu' nella colonna `tool` non e' una riga persa
per incidente di misura: e' una riga che il regime rilassato sposta dal rifiuto
dichiarato al fallimento non dichiarato.

## Il prezzo, che prima di questa esecuzione non era noto

INT26, regime rilassato: `Exception: bad allocation` dentro `cau_inference`. Nel regime
primario la stessa riga si ferma al validatore ed e' fra le 20 rifiutate elencate in
`registro_non_valutabili.md` sezione 3, con il motivo `intervention: servono almeno 1
evidenza/e, restano []`; il tool non la vede mai.

Lo stesso errore e' gia' registrato nelle corse reali su un'altra riga del ramo
`intervention`, INT17: `harness/risultati/b_base/20261101_150815/INT17_r1.json:18` e
`harness/risultati/b_esempi/20261101_181205/INT17_r1.json:20`, entrambi con la stringa
`cau_inference: Exception: bad allocation`. INT26 e' la seconda riga che lo produce, e
il replay la espone perche' il gate non c'e'.

Quello che il replay non stabilisce: quale allocazione esatta di `causalImpact` fallisce
e perche'. `riproduci` cattura l'eccezione e ne registra solo tipo e messaggio
(`replay_traduzione.py:176-177`), non lo stack, quindi il punto di allocazione non e'
noto. La riga resta classificata per il tipo e il messaggio, non per la causa.

Chi volesse adottare il 40/81 dovrebbe prima chiudere questo ramo nel tool; la
chiusura non fa parte di questa consegna, e il 40/81 resta un'analisi alternativa.
