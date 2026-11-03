# Valutatore parallelo conservativo

`robust_evaluator.py` è un percorso indipendente da `evaluator.py`. Non modifica
le metriche storiche e non usa embedding o LLM-as-a-Judge per decidere da solo
se una risposta è corretta.

## Principi

1. **Contratto esplicito**: ogni item deve dichiarare tipo di risposta,
   alternative accettate, tolleranze e, per il testo libero, fatti verificabili.
2. **Gerarchia delle prove**: confronto numerico/testuale deterministico prima;
   semantica e judge solo come diagnostica secondaria.
3. **Indeterminato distinto da errato**: riferimento assente, ambiguo o
   insufficiente non viene trasformato in `0`.
4. **Tracciabilità**: ogni risultato contiene metodo, risposta estratta,
   fatti mancanti, elementi proibiti e diagnostica.
5. **Intervallo d'incertezza**: gli aggregati riportano l'intervallo Wilson al
   95% e il tasso di casi indeterminati.

## Contratto di riferimento

```json
{
  "answer_type": "number",
  "accepted_answers": ["0.212"],
  "absolute_tolerance": 0.0005,
  "relative_tolerance": 0.000001
}
```

Per testo libero:

```json
{
  "answer_type": "free_text",
  "required_facts": ["Roma", "Lazio", "Tevere"],
  "forbidden_facts": ["Firenze"],
  "minimum_required_facts": 3
}
```

Una risposta numerica con più numeri deve contenere un marcatore esplicito
(`answer:`, `risposta:`, `result:`) oppure viene classificata come
`indeterminate`. Questo evita di premiare accidentalmente un numero
intermedio o un'estrazione dell'ultimo token.

## Interpretazione

`correct` e `incorrect` entrano nel calcolo dell'accuracy. `indeterminate` viene
conteggiato separatamente e non viene nascosto nel denominatore. La similarità semantica può essere aggiunta in futuro come evidenza calibrata
su annotazioni umane, mai come sostituto automatico del contratto di verità.

## Tipi comuni aggiuntivi

Il core supporta anche:

- `interval`: confronto indipendente dei due estremi;
- `label`: confronto categorico di un'etichetta;
- `structured`: confronto esatto di un oggetto JSON atteso.

Questi tipi sono usati dall'adattatore MUDILAB.

## Valutazione MUDILAB

`mudilab_adapter.py` valuta separatamente etichetta, traduzione, output e
osservazione della chiamata a `cau_inference`. La pipeline è `correct` solo
quando tutti i livelli sono corretti e la chiamata al tool è osservata.

Il comando:

```bash
python mudilab_eval.py \
  --ground-truth ../MUDILAB_run/consegna/ground_truth.csv \
  --input outputs.jsonl \
  --output evaluated.jsonl \
  --summary summary.json
```

Il file JSONL di input contiene almeno:

```json
{
  "task_id": "CP1",
  "label": "backward_reasoning",
  "translation": {
    "input": {"DrivQuality": "Normal"},
    "output": {"Age": "Senior"}
  },
  "output": "The probability is 0.2117",
  "tool_calls": [{"name": "cau_inference"}],
  "energy_j": 236.2,
  "duration_s": 8.7
}
```

L'aggregato riporta accuracy end-to-end, copertura, casi indeterminati, energia
mediana totale, energia mediana delle risposte corrette e dati mancanti.


## Limiti e interpretazione della confidenza

I valori `confidence` restituiti dai controlli deterministici sono punteggi
euristici interni, **non probabilità calibrate**. Il risultato espone
`confidence_calibrated=false`; gli aggregati non li presentano come media di
confidenza calibrata. Per poterli interpretare probabilisticamente serve una
procedura separata di calibrazione su un insieme indipendente con etichette
umane.

Il controllo `free_text` è deliberatamente lessicale: richiede
`fact_match_mode: "literal"` e verifica la presenza letterale dei fatti
dichiarati. Se rileva una negazione locale di un fatto richiesto, restituisce
`indeterminate`. Non dimostra entailment, correttezza contestuale o assenza
di contraddizioni: non è un valutatore semantico e non deve essere descritto
come tale.

I contratti sono validati prima della valutazione. Contratti incompleti,
tolleranze negative/non finite, limiti non validi e schemi strutturati vuoti
producono `indeterminate` con diagnostica, non un punteggio di accuratezza.

## Verifica dell'esecuzione MUDILAB

La sola presenza di una voce `cau_inference` prova al massimo che la chiamata
è stata registrata. Per considerarla riuscita, il record deve contenere
`success: true` oppure uno `status` esplicito tra `success`, `succeeded`,
`completed`. Una chiamata senza esito verificabile è `unverified` e rende
l'end-to-end `indeterminate`; un fallimento esplicito rende il caso
`incorrect`. Il controllo del nome dello strumento non prova da solo che
argomenti e risultato siano corretti: per quello occorre aggiungere al trace
il contratto degli argomenti attesi e l'output effettivo del tool.

Il caricamento del ground truth MUDILAB interrompe l'esecuzione in presenza di
ID vuoti o duplicati, tipi non supportati, etichette mancanti o riferimenti
numerici/intervalli obbligatori assenti.
