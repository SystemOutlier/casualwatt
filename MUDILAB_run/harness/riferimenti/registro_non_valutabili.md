# Registro dei casi non valutabili

Generato da: `manifest.json` (manifest del 2026-11-01T14:50:10, seed 7) e `tabella_prima_dopo_20261101.json`. Nessun numero ricopiato a mano.
Benchmark: {'coherence': 40, 'cond_prob': 41, 'counterfactual': 40, 'inter': 40} per ramo.

## 1. Esclusi alla generazione perche' il valore non discrimina

- **per_ramo**: {'coherence': 1, 'cond_prob': 3, 'counterfactual': 3, 'inter': 2}
- **totale**: 9

*Impatto sul denominatore*: non entrano nei 161: il denominatore non cresce. Sono esclusi perche' il valore atteso si stampa 0.0000/1.0000, o sta a ridosso della soglia 0.60, o l'intervallo controfattuale e' nullo: una variante che risponde un numero a caso prende lo stesso punto, quindi la riga non discrimina.

Dettaglio (dal manifest):

```json
{
 "coherence": {
  "probabilita' al bordo (0.0000)": 1
 },
 "cond_prob": {
  "probabilita' al bordo (1.0000)": 3
 },
 "counterfactual": {
  "intervallo nullo [0.0, 0.0]": 2,
  "intervallo nullo [0.8314, 0.8314]": 1
 },
 "inter": {
  "probabilita' al bordo (0.0000)": 2
 }
}
```

## 2. Esclusi alla generazione perche' il codice deterministico non risponde

- **per_ramo**: {'counterfactual': 94, 'inter': 3}
- **totale**: 97

*Impatto sul denominatore*: non entrano nei 161: il denominatore non cresce. E' il codice della consegna che non sa rispondere (cobound non calcola il giunto su ogni coppia, causalImpact si ferma sugli effetti deterministici), non il modello: una riga del genere renderebbe uguale il fallimento di tutte le varianti.

Famiglie di causa (somma dei tentativi scartati su quella coppia di variabili):

| ramo | causa | tentativi |
|---|---|---|
| counterfactual | UndefinedElement | 80 |
| counterfactual | IncompatibleEvidence | 14 |
| inter | IncompatibleEvidence | 3 |

Per sola causa, sommati sui rami: UndefinedElement=80, IncompatibleEvidence=17

## 3. Righe che esistono, ma il protocollo ferma prima del tool

- **esito_per_categoria**: {'corretta': 32, 'numero': 29, 'rifiutata': 20}
- **denominatore**: 81
- **rifiutate_dal_validatore**: 20
- **per_famiglia_di_motivo**: {'evidenze richieste non presenti nella traduzione': 16, "'output' deve avere esattamente una chia": 1, "output: 'ten thousand dollars' non e' un": 1, "output: 'ten thousand' non e' uno stato ": 1, "output: 'one thousand dollars' non e' un": 1}
- **coherence_mappatura**: {'altro errore di mappatura': 13, 'target invertito': 2, 'non arrivato al tool': 3, 'mappatura esatta': 2}

*Come si legge*: le righe contate come 'mappatura esatta' sono quelle che il metro puo' promuovere; le altre escono dal tool con un numero giusto o sbagliato che non corrisponde comunque alla domanda dell'oracolo. Il collo di bottiglia del ramo non e' l'inferenza, e non e' l'etichetta: e' la scelta di quali chiavi vanno in `input` e quale in `output`.

*Impatto sul denominatore*: restano NEL denominatore: 20 su 81 contano come non corrette. E' una scelta di protocollo, non un incidente: se uscissero dal conteggio il punteggio salirebbe a 32/61 senza che il modello abbia fatto nulla in piu'.

| task | ramo | motivo (troncato a 70 caratteri dal replay) |
|---|---|---|
| CF18 | counterfactual | counterfactual: servono almeno 1 evidenza/e, restano []; sca |
| CND02 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND10 | cond_prob | counterfactual: servono almeno 1 evidenza/e, restano []; sca |
| CND14 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND21 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND26 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND33 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND37 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| CND38 | cond_prob | backward_reasoning: servono almeno 1 evidenza/e, restano []; |
| COH06 | coherence | 'output' deve avere esattamente una chiave: {'AntiTheft': 'F |
| COH09 | coherence | coherence: servono almeno 1 evidenza/e, restano []; scartate |
| COH33 | coherence | coherence: servono almeno 1 evidenza/e, restano []; scartate |
| INT02 | inter | output: 'ten thousand dollars' non e' uno stato di PropCost; |
| INT09 | inter | output: 'ten thousand' non e' uno stato di OtherCarCost; sta |
| INT17 | inter | intervention: servono almeno 1 evidenza/e, restano []; scart |
| INT21 | inter | intervention: servono almeno 1 evidenza/e, restano []; scart |
| INT26 | inter | intervention: servono almeno 1 evidenza/e, restano []; scart |
| INT29 | inter | output: 'one thousand dollars' non e' uno stato di PropCost; |
| INT33 | inter | intervention: servono almeno 1 evidenza/e, restano []; scart |
| INT37 | inter | intervention: servono almeno 1 evidenza/e, restano []; scart |

## 4. Forme che il tool non deve numerare, anche se il validatore le lasciasse passare

- **presenti_nel_dev_81**: 0

Le stesse traduzioni, tre versioni del ramo (`fix_coherence_controfattuale.json`):

| caso | A fissato | B senza FIX 20 | C prima dei fix |
|---|---|---|---|
| sintetico: target anche evidenza | eccezione: `ValueError: coherence: il target MedCost compare anche fra le evidenze` | numero: `Evidences are compatible with a single MedCost of Thousand with a prob` | numero: `Evidences are compatible with a single MedCost of Thousand with a prob` |
| sintetico: target HundredThou, output Million (COH09) | eccezione: `ValueError: coherence: il target ThisCarCost compare anche fra le evid` | numero: `Evidences are NOT strongly compatible with a single ThisCarCost of Mil` | numero: `Evidences are NOT strongly compatible with a single ThisCarCost of Mil` |
| sintetico: variabile inesistente nell'evidenza | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` |
| sintetico: stato inesistente nell'evidenza | eccezione: `ValueError: Antilock='Falso' non e' uno stato ammesso da Antilock; sta` | eccezione: `ValueError: Antilock='Falso' non e' uno stato ammesso da Antilock; sta` | eccezione: `ValueError: Antilock='Falso' non e' uno stato ammesso da Antilock; sta` |
| sintetico: variabile inesistente nell'evidenza [guardia `_valida_stati` neutralizzata] | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` | eccezione: `KeyError: "variabile 'NonCes variable' assente dal grafo"` |
| sintetico: stato inesistente nell'evidenza [guardia `_valida_stati` neutralizzata] | eccezione: `RuntimeError: coherence: inferenza non possibile (OutOfBounds): [pyAgr` | eccezione: `RuntimeError: coherence: inferenza non possibile (OutOfBounds): [pyAgr` | eccezione: `OutOfBounds: [pyAgrum] Out of bound error: label 'Falso' is unknown in` |

*Impatto sul denominatore*: zero righe spostate sul dev con la regola primaria: il validatore le ferma prima. Il fix esiste per non far dipendere il verdetto dal validatore, che e' un altro modulo e un altro protocollo.

## 5. Le quattro quantita' separate, per regime di citazione


*Impatto sul denominatore*: i tre regimi hanno lo stesso denominatore (81) e numeri diversi: non e' lo stesso metro tre volte. Sull'unico regime primario congelato (gate sulla frase, citazione del target libera) il quarto numero e' una misura, perche' il gate protegge le evidenze ma non il target; il regime con la citazione del target obbligatoria riporta zero per costruzione e va letto come proprieta' del filtro, non come assenza di citazioni inventate. La coppia 32/40 e il prezzo della riga INT26, che solo il regime esplorativo manda al tool dove muore di `bad allocation`, stanno rieseguiti e registrati in `replay_regimi_b_composta_20261101.md`.


Le quattro quantita' separate, sullo stesso denominatore di 81 righe dev e sugli stessi testi registrati. `target` e' la variabile della domanda; `evidenza` una delle sue condizioni.

| regime | accettate | rifiutate | copertura | target citato verbatim | target citato ma non supportato | target senza citazione | un'evidenza non supportata |
|---|---|---|---|---|---|---|---|
| primaria congelata (gate sulla frase) | 61 | 20 | 0.753 | 35 | 16 | 10 | 0 |
| primaria, citazione del target obbligatoria | 35 | 46 | 0.432 | 35 | 0 | 0 | 0 |
| esplorativa senza gate (NON protocollo) | 71 | 10 | 0.877 | 37 | 20 | 14 | 18 |

- `primaria congelata (gate sulla frase)`: il quarto numero e' una misura; `avviso_output` scritto dal validatore = 26, che coincide con il conteggio: True
- `primaria, citazione del target obbligatoria`: il quarto numero e' zero per costruzione: e' il filtro, non un risultato; `avviso_output` scritto dal validatore = 0, che coincide con il conteggio: True
- `esplorativa senza gate (NON protocollo)`: il quarto numero e' una misura; `avviso_output` scritto dal validatore = 23, che coincide con il conteggio: False
  La divergenza e' attesa e non e' un difetto del conteggio: in questo regime il validatore applica al target la stessa regola rilassata, quindi dichiara avviso solo sulle citazioni che non reggono nemmeno a quella (23 righe), mentre la regola stretta qui non copre 34 righe. La differenza e' la popolazione delle parafrasi tollerate dal regime esplorativo.

- righe accettate il cui target ha una citazione che la regola stretta non regge, primaria congelata (gate sulla frase): CF05 CF09 CF25 CF37 CND01 CND06 CND09 CND13 CND18 CND22 CND25 COH02 COH05 COH10 COH14 COH17 COH18 COH21 COH22 COH25 COH26 COH30 COH37 INT01 INT10 INT25
- righe accettate il cui target ha una citazione che la regola stretta non regge, esplorativa senza gate (NON protocollo): CF05 CF09 CF25 CF37 CND01 CND02 CND06 CND09 CND13 CND14 CND18 CND21 CND22 CND25 CND38 COH02 COH05 COH10 COH14 COH17 COH18 COH21 COH22 COH25 COH26 COH30 COH37 INT01 INT10 INT17 INT21 INT25 INT26 INT33
