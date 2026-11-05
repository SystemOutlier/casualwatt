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
- chiamata `cau_inference` effettuata, con argomenti verificati;
- output acquisito e adozione verificata con ricevuta di forwarding;
- verdetto end-to-end.

Una trace che prova solo l'esecuzione non basta: senza argomenti e ricevuta la
riga è `indeterminate`, e una coincidenza numerica non è evidenza di adozione
(B5).

Gli adattatori futuri devono produrre lo stesso schema, senza modificare il
core.

### Energia e report

`evaluation_runner.py` associa `energy_j`, `duration_s` e l'identità del task
alla singola riga. Un valore mancante resta `None`, mai `0`. Il report include:

- accuracy sui casi determinati;
- coverage;
- tasso di indeterminati;
- conteggio degli esiti;
- **costo per risposta corretta**: energia disponibile di tutti i tentativi
  diviso tutte le corrette, con stato `complete|partial|unavailable`;
- copertura dell'energia e conteggio delle esclusioni (mancante, non valida,
  negativa, non verificabile);
- mediane dell'energia, diagnostiche e non sostitutive del costo per corretta;
- intervallo di Wilson a livello di riga e bootstrap a cluster a livello di
  task, quest'ultimo solo se l'identità è registrata.

`ece_per_joule = acc_comp / energia` è deprecato e resta `N/A`: `acc_comp` è un
indice descrittivo, non un'accuratezza. Il costo aggregato non si calcola sulla
mediana delle sole corrette, che escluderebbe l'energia spesa negli errori.

## Contratto end-to-end

Una risposta è `correct` solo quando tutti questi elementi sono corretti:

```text
label AND translation AND output
AND tool_called AND arguments_verified AND output_acquired
AND adoption_verified
```

Se un componente è `indeterminate` o non registrato, l'intero caso è
`indeterminate`; se un componente è chiaramente errato — inclusi argomenti che
non corrispondono alla traduzione valutata o una ricevuta che non combacia — il
caso è `incorrect`. `llm_tool_use` resta `not_proven`: il framework misura il
percorso software, non il ragionamento del modello.

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
  "tool_calls": [{"name": "cau_inference", "success": true}],
  "energy_j": 236.2,
  "duration_s": 8.7
}
```

Una voce `{"name": "cau_inference"}` senza esito non prova l'esecuzione: lo
stato è `unverified` e il caso `indeterminate`. Sono accettate anche il dict di
contatori `{"cau_inference": {"invocazioni": 1, "eccezioni": 0}}` e il passo
registrato `{"step": "cau_inference", "text": ...}`; vedi
`ROBUST_EVALUATOR.md`.

Il record scritto dall'orchestratore usa `etichetta`, `traduzione`, `numero`,
`steps` e `output_provenance`, ed è letto senza rinominare i campi. La
ricevuta di forwarding (`producer`, `mode`, `call_id`, campi di origine e
destinazione, SHA-256) è obbligatoria per dichiarare l'adozione: il solo
`output` corretto lascia la riga `indeterminate`. Il digest prova l'integrità
interna della trace, non l'autenticità del produttore.

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
7. L'energia per risposta corretta è la somma dell'energia disponibile di tutti
   i tentativi diviso tutte le corrette; va riportata insieme a coverage e
   accuracy, non al loro posto, e non è la mediana delle sole corrette.
8. L'unità statistica è il task: senza identità dichiarata il bootstrap a
   cluster resta `None` con la ragione, e non si inventano identificativi per
   renderlo calcolabile.
9. L'adozione del risultato del tool richiede una ricevuta di forwarding; la
   coincidenza del numero finale non è prova di uso.

## Riferimenti di metodo

- Rajpurkar et al., *SQuAD*, EMNLP 2016: normalizzazione di articoli,
  punteggiatura e maiuscole per il match testuale; nella nostra B2 la stessa
  normalizzazione vale sui due lati e i numeri non vengono normalizzati.
- Liang et al., *Holistic Evaluation of Language Models* (HELM), 2022, §4.4 e
  App. C.2: la copertura dei casi è riportata separatamente dall'accuratezza.
- Lanham et al., 2023, §2.3: una relazione sequenziale fra due eventi non è una
  relazione causale, quindi la coincidenza fra risposta e output del tool non
  prova l'adozione.
