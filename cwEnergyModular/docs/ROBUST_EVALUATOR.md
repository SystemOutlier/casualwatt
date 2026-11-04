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
   95% e il tasso di casi indeterminati. Il Wilson è a livello di *riga* e
   suppone che ogni riga sia un tentativo indipendente; quando la stessa domanda
   ricompare in più richieste quell'ipotesi cade, quindi `summarize(rows,
   task_ids=[...])` pubblica anche `accuracy_cluster_bootstrap_95` (percentile
   2,5–97,5 di un bootstrap **a cluster** sul task, 2000 ricampioni, seed fisso
   `20261104`) e `n_effective_tasks`. I due intervalli si leggono insieme, non in
   alternativa. Senza `task_ids` il secondo resta `null` con il motivo scritto in
   `cluster_bootstrap_note`: un bootstrap per riga restringerebbe l'intervallo
   assumendo proprio l'indipendenza che il cluster deve correggere. Con un solo
   task distinto l'intervallo non si pubblica affatto (la dispersione sarebbe
   zero per costruzione, non per evidenza). Il confronto fra due sistemi sullo
   stesso task resta una McNemar appaiata.

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
  "minimum_required_facts": 3,
  "fact_match_mode": "literal"
}
```

Una risposta numerica con più numeri deve contenere un marcatore esplicito
(`answer:`, `risposta:`, `result:`) oppure viene classificata come
`indeterminate`. Questo evita di premiare accidentalmente un numero
intermedio o un'estrazione dell'ultimo token.

Una risposta **vuota** è `indeterminate` anche lei (`number_answer_absent`,
`interval_answer_absent`): un run che non ha prodotto testo non ha risposto
male, non ha risposto. `incorrect` resta il verdetto di una risposta che c'è ma
non contiene il numero atteso.

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
  "tool_calls": [{"name": "cau_inference", "success": true, "result": {"ok": true}}],
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

L'adapter legge le tre forme che la pipeline produce davvero, non una sola:

- `[{"name": "cau_inference", "success": true}]` — lo schema dichiarato;
  `success: false` o uno `status` fra `error`, `failed`, `failure`, `exception`
  rende il caso `failed`; una voce senza esito verificabile è `unverified`;
- il dict di contatori scritto da `MUDILAB_correzioni/run_query.py:188-193`
  (`{"cau_inference": {"invocazioni": n, "eccezioni": m}}`): `success` quando
  `invocazioni >= 1` ed `eccezioni == 0`, cioè la condizione di `tool_ok` a
  `:178`; `failed` se le eccezioni sono più di zero; `missing` a zero
  invocazioni;
- il passo registrato in `steps` (`run_orchestrato.py:482-500`): il passo viene
  aggiunto solo dopo che la chiamata è tornata, perché il percorso d'eccezione
  esce a `:470-480` senza aggiungerlo. Un passo `cau_inference` con un testo non
  vuoto è quindi una prova di esecuzione.

Se nessuna voce è leggibile lo stato è `missing` e l'end-to-end è
`indeterminate`, mai un punteggio inventato.

Il caricamento del ground truth MUDILAB interrompe l'esecuzione in presenza di
ID vuoti o duplicati, tipi non supportati, etichette mancanti o riferimenti
numerici/intervalli obbligatori assenti.

## Controllo qualitativo di coerenza

Per le righe `coherence` l'adapter cerca le due frasi che stampa il tool della
relatrice (`MUDILAB_run/consegna/tools_corretto.py:448` e `:453`) e le confronta
con il valore di `expected_decision` del ground truth, che nel dataset è
`compatible` o `non_compatibile`:

- `non_compatibile` richiede `not strongly compatible`;
- `compatible` richiede la forma completa `are compatible with` **e** l'assenza
  del negativo, perché la parola `compatible` sta anche dentro la frase
  negativa;
- un valore fuori da queste due classi non produce un marcatore derivato
  dall'ortografia: la nota lo dichiara e il verdetto è `indeterminate`.

Il controllo è lessicale e non valuta l'equivalenza semantica. Non si esegue su
una risposta vuota: una riga fermata dal gate resta `indeterminate` per il gate,
senza una seconda colpa.

## Argomenti della chiamata

La prova di esecuzione non basta a provare gli argomenti. L'harness orchestrato
passa etichetta, query e path a `cau_inference.func` (`run_orchestrato.py:469`)
e dal 04-11 li registra nel passo insieme alla risposta (`:491-495`), quindi per
i run prodotti da ora lo stato è decidibile: `verified` quando il payload coincide
con la traduzione valutata, `mismatch` quando diverge. Il payload è il secondo
argomento della firma del tool -- la query come stringa JSON
(`consegna/tools_corretto.py:322-323`) -- e viene scartato dall'involucro
`{label, features, path}` prima del confronto, perché confrontare l'involucro con
la traduzione avrebbe dato `mismatch` fra due dizionari che descrivono la stessa
query.

Restano indecidibili, e l'adapter lo dice nei `notes` invece di dedurlo:

- la pipeline a contatori (`MUDILAB_run/MUDILAB_correzioni/run_query.py:188-194`),
  che riporta `invocazioni` ed `eccezioni` e non riceve gli input dal framework
  degli agenti;
- ogni run registrato prima che l'harness cominciasse a scrivere `args`, inclusi
  tutti i 321 già pubblicati: per loro lo stato è `not recorded`.

Un disallineamento degli argomenti è dichiarato, non punito: non cambia
l'esito `end_to_end`, perché renderlo una colpa sarebbe un criterio di valutazione
nuovo e andrebbe deciso sui dati, non scritto nel codice del valutatore.

