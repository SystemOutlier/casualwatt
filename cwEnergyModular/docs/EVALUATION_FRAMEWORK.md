# Framework comune di valutazione CasualWatt

## Obiettivo

Il framework misura due proprietà distinte della stessa esecuzione:

1. **correttezza della risposta**, tramite un contratto verificabile;
2. **costo energetico**, associato alla risposta con lo stesso identificativo
   di esecuzione.

Non esiste un punteggio unico `accuracy-energy`: accuracy ed energia sono
riportate separatamente e possono essere confrontate con una frontiera di
Pareto.

## Strati

### Core

`robust_evaluator.py` contiene i tipi di verifica comuni:

- `number`: valore con tolleranza assoluta/relativa;
- `interval`: estremi verificati separatamente;
- `label`: categoria esatta;
- `structured`: oggetto JSON esatto;
- `short_text`: alternative con confini delle parole;
- `free_text`: fatti richiesti e proibiti.

Ogni verifica produce `correct`, `incorrect` oppure `indeterminate`.

### Adattatori

Un adattatore converte il formato di uno strumento nel contratto comune.
`mudilab_adapter.py` è il primo adattatore e controlla:

- classificazione;
- traduzione della query;
- output numerico o intervallo;
- presenza osservata di `cau_inference`;
- verdetto end-to-end.

Gli adattatori futuri devono produrre lo stesso schema, senza modificare il
core.

### Energia e report

`evaluation_runner.py` associa `energy_j` e `duration_s` alla singola riga.
Un valore mancante resta `None`, mai `0`. Il report include:

- accuracy sui casi determinati;
- coverage;
- tasso di indeterminati;
- conteggio degli esiti;
- energia mediana per tutte le risposte;
- energia mediana per le risposte corrette;
- tasso di energia mancante.

## Contratto end-to-end

Una risposta è `correct` solo quando tutti questi elementi sono corretti:

```text
label AND translation AND output AND tool_call
```

Se un componente è `indeterminate`, l'intero caso è `indeterminate`; se un
componente è chiaramente errato, il caso è `incorrect`.

## Formato comune JSONL

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

## Comando MUDILAB

```bash
python mudilab_eval.py \
  --ground-truth ../MUDILAB_run/consegna/ground_truth.csv \
  --input outputs.jsonl \
  --output evaluated.jsonl \
  --summary summary.json
```

Il ground truth MUDILAB deve essere congelato prima del confronto fra modelli.
Le tolleranze sono parte del contratto e non vanno modificate dopo aver visto i
risultati.

## Regole per la tesi

1. Il test dell'oracolo causale deve essere indipendente dalla risposta del
   modello.
2. Il classificatore, il traduttore e il tool devono avere metriche separate.
3. La metrica primaria end-to-end richiede il superamento di tutti gli strati.
4. `indeterminate` non deve essere contato come corretto né come errore.
5. Energia non misurata non deve essere codificata come zero.
6. Le configurazioni devono mantenere uguali temperatura, cache, prompt,
   modello e confine energetico.
7. L'energia per risposta corretta deve essere riportata insieme a coverage e
   accuracy, non al loro posto.
