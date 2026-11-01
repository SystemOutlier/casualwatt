# Tabella prima/dopo — dev 81 righe, nessun run sul modello

Corsa di riferimento: `20261101_183106` (variant `b_composta`, 18:31 dell'01-11).
Regola di citazione: primaria congelata (`output=libero`: gate che vuole la frase verbatim nella query).
Metro: `_confronta` di `benchmark/genera.py` con la tolleranza `TOLL`; `corretta = etichetta_ok AND numero_ok`.
**Prima** = stringa gia' registrata nel JSON della corsa, prodotta dal codice vecchio. **Dopo** = lo stesso testo del traduttore, ricalcolato con `consegna/tools_corretto.py` corrente.

Totali: corrette **32/81** prima → **32/81** dopo.

## Per ramo

| ramo | righe | corrette prima | corrette dopo | esiti cambiati |
|---|---|---|---|---|
| coherence | 20 | 2 | 2 | 0 |
| cond_prob | 21 | 12 | 12 | 0 |
| counterfactual | 20 | 11 | 11 | 0 |
| inter | 20 | 7 | 7 | 0 |

## Categoria dell'esito, per lato

- prima: {'corretta': 32, 'numero': 29, 'rifiutata': 20}
- dopo:  {'corretta': 32, 'numero': 29, 'rifiutata': 20}

## Righe che cambiano esito

| task | ramo | prima | dopo | motivo (dopo) | traduzione registrata |
|---|---|---|---|---|---|
| _nessuna riga cambia esito_ | | | | | |

## Perche' non cambia niente, detto con i numeri

I due fix stanno dentro il ramo `coherence` del tool. Su questo dev le `20` righe coherence si dividono cosi':

- COH01: numero → numero (stampato [0.991] atteso 0.9879544398)
- COH02: numero → numero (stampato [0.3946] atteso 0.7679832451)
- COH05: numero → numero (stampato [0.5958] atteso 0.0002444291)
- COH06: rifiutata → rifiutata ('output' deve avere esattamente una chiave: {'AntiTheft': 'F)
- COH09: rifiutata → rifiutata (coherence: servono almeno 1 evidenza/e, restano []; scartate)
- COH10: numero → numero (stampato [0.3653] atteso 0.6346713747)
- COH13: numero → numero (stampato [0.01] atteso 0.4999999934)
- COH14: corretta → corretta
- COH17: corretta → corretta
- COH18: numero → numero (stampato [0.2762] atteso 0.7237576809)
- COH21: numero → numero (stampato [0.3517] atteso 0.3204859136)
- COH22: numero → numero (stampato [0.3237] atteso 0.1543227609)
- COH25: numero → numero (stampato [0.0489] atteso 0.9511201960)
- COH26: numero → numero (stampato [0.283] atteso 0.7169521293)
- COH29: numero → numero (stampato [0.9639] atteso 0.0012833709)
- COH30: numero → numero (stampato [0.7241] atteso 0.2759339001)
- COH33: rifiutata → rifiutata (coherence: servono almeno 1 evidenza/e, restano []; scartate)
- COH34: numero → numero (stampato [0.3174] atteso 0.6825630175)
- COH37: numero → numero (stampato [0.9987] atteso 0.4418011778)
- COH38: numero → numero (stampato [0.202] atteso 0.2215002960)

Una riga rifiutata dal validatore non arriva mai al tool, e una riga che al tool arriva con il target fuori dalle evidenze esegue lo stesso calcolo di prima: per questo il punteggio non si muove. Che i due fix non siano codice decorato lo misura `verifica_fix_coherence.py`, che mette lo stesso input sui tre bracci (file attuale, attuale senza il controllo sul target, file dello zip del 31-10) e registra: sul target-dentro-le-evidenze i bracci senza FIX 20 stampano `probability of 1.0` e `probability of 0.0`, quello attuale esce dichiarato; sull'evidenza con stato inesistente il codice vecchio lasciava uscire `OutOfBounds` nudo perche' `addEvidence` era fuori dal `try`.


Righe senza passo traduttore registrato (non riproducibili, contate a parte): 0 -
