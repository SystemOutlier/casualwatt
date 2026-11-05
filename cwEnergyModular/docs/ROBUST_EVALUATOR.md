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
   stesso task richiede una McNemar appaiata: **non è implementata**. Finché non
   esiste e non ha test propri, non va descritta come disponibile né usata per
   decidere fra due sistemi.

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

`mudilab_adapter.py` valuta separatamente etichetta, traduzione, output e il
percorso della chiamata a `cau_inference`. La pipeline è `correct` solo quando
tutti i livelli sono corretti, la chiamata è stata eseguita con argomenti
verificati, il testo dell'output è stato acquisito **e** l'esito è stato
adottato con una ricevuta di forwarding (B5). Una trace che prova solo
l'esecuzione lascia la riga `indeterminate`, anche quando il numero finale
coincide con quello del tool.

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

L'aggregato riporta accuracy end-to-end, copertura, casi indeterminati e il
costo energetico per risposta corretta: somma dell'energia disponibile di
**tutti** i tentativi diviso **tutte** le corrette, con stato
`complete|partial|unavailable`, copertura e conteggio delle esclusioni. Le
mediane dell'energia restano diagnostiche e non sono il costo per corretta.
Con zero corrette il rapporto è `None` con la ragione, mai zero o infinito.


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

Un disallineamento degli argomenti rende la riga `incorrect` (B5): un numero
ottenuto interrogando una query diversa da quella valutata non è il risultato
del percorso misurato. Le trace senza argomenti registrati restano
`not recorded` e non vengono promosse; non si deduce il payload dalla sola
risposta.

## B1 — Estrazione numerica condivisa conservativa

`numeric_answers.py` è ora l'unico parser numerico dei due valutatori; i loro
criteri di confronto restano distinti. Questo aggiorna la sola estrazione,
non il matching testuale, le funzioni di aggregazione, P1 o `load_case`.

- Precedenza: `final answer` / `risposta finale`, poi `answer` / `result` /
  `risposta` / `risultato`, poi il testo senza marker. I marker ignorano il
  maiuscolo e ammettono `:`, `=`, `is`, `è` oppure nessun separatore.
  `=` da solo **non** è un marker. Un segmento va dal marker al successivo:
  tutti i segmenti al livello scelto devono essere risolvibili e concordi.
  Un marker vuoto non permette il ripiego su un numero precedente o su un
  marker di livello inferiore. Numeri distinti nello stesso segmento o marker
  discordanti allo stesso livello producono astensione, mai l'ultimo numero.
- Un unico valore ripetuto è ammesso: il confronto di unicità è esatto in
  decimale, dopo la conversione SI, non arrotondato né soggetto alla tolleranza
  di correttezza. Le espressioni aritmetiche non vengono calcolate: ad esempio
  `5*5=25,25-4=21` non identifica una risposta. Per ripetizioni con segno usare
  un delimitatore (`+3; +3`): `3 +3` è sintassi aritmetica, non una ripetizione.
- Grammatica: segni ASCII `+`/`-` preservati, decimali con punto o virgola anche
  senza zero iniziale (`.5`, `-,5`), esponente `e`/`E` con segno opzionale.
  La virgola non è un separatore delle migliaia. Le percentuali sono
  adimensionali e normalizzate dividendo per 100, anche nella GT.
- Unità ammesse come suffisso, case-sensitive: `J`, `mJ`, `kJ` (energia),
  `W` (potenza), `s`, `ms` (tempo). Conversioni esplicite: mJ→J e ms→s per
  `10^-3`, kJ→J per `10^3`. L'assenza di unità è adimensionale: `3 W` non
  corrisponde né a `3 J` né a `3`. L'unità canonica resta nella risposta
  estratta. I suffissi sconosciuti o composti non vengono cancellati: causano
  astensione, anche se la cifra isolata sarebbe corretta.
- Limiti deliberati: niente calcolo simbolico, LaTeX, unità composte o tra
  parentesi, segni Unicode, numeri in lettere o convenzioni delle migliaia.
  Dopo un numero, la prosa va separata con punteggiatura; una parola adiacente
  è trattata conservativamente come suffisso (salvo `and`, `or`, `e`, `o`,
  `oppure`, separati da spazio). Non è un'analisi semantica della prosa.
  I riferimenti sono scalari completi della stessa grammatica, non estrazioni
  da testo libero. Valori non finiti, overflow e underflow a zero nel confronto
  float sono rifiutati, non riparati.

Nel ramo standard: assenza, ambiguità o sintassi numerica non supportata danno
`is_correct=None`, `acc_comp=None`, `extracted_answer=None`; testo non vuoto
senza numeri resta `0`. Nel robusto valgono rispettivamente `indeterminate` e
`incorrect`. Un riferimento numerico esplicitamente dichiarato ma invalido
produce astensione, non un errore del modello. L'auto-detect riconosce scalari
SI e percentuali; le regole di classificazione/matching del testo non numerico
non sono cambiate da B1: B2 le tratta nella sezione seguente.

**Tolleranze invariate**, applicate alle unità canoniche:

- Standard `compare_numbers`: errore relativo **strict `< 1e-6`** rispetto
  a `|GT|`; per GT zero, errore assoluto **`< 1e-6`**.
- Robusto: `distance <= max(absolute, relative * max(|expected|, 1))`, con
  default `absolute=1e-9`, `relative=1e-6`. Non si sommano i due termini;
  il pavimento di scala a 1 resta per compatibilità, anche vicino allo zero.
- MUDILAB: `_case_contract` esplicita `relative_tolerance=0` in tutti i rami;
  l'assoluta derivata resta metà passo decimale stampato più `1e-12`.
- Intervalli controfattuali: `between ... and ...` / `from ... to ...`
  riconoscono anche segni, decimali iniziali ed esponenti interi. Gli estremi
  restano adimensionali; le unità e la prosa subito dopo l'estremo superiore
  non fanno parte della grammatica. Entrambi i limiti devono passare lo stesso
  confronto precedente, senza variazioni alla tolleranza CF.

## B2 — Confini di parola nel match testuale

Il confronto di `short_text` e `free_text` non usa più la sottostringa. Prima di
B2 `Roma` era contenuta in `Romania`, `cat` in `catalog` e `Firenze` in
`Firenzenuova`: il primo caso approvava una risposta che non nominava la
verità, il secondo faceva scattare un fatto proibito che la risposta non
conteneva. Ora `_contains_phrase` (`evaluator.py`) e `_contains_fact`
(`robust_evaluator.py`) cercano il riferimento come sequenza di parole intere,
dopo la stessa normalizzazione applicata a entrambi i lati.

La simmetria è deliberata: maiuscole, accenti e punteggiatura non decidono
l'esito, mentre il confine fra parole sì. La punteggiatura diventa spazio, così
un fatto in più parole (`Roma capitale`) regge anche una virgola in mezzo, e
`RomaItalia` resta una parola diversa da `Roma Italia`. Le alternative multiple
usano lo stesso confine e `matched` dice quale ha combaciato.

Un riferimento che si normalizza a vuoto (`...`, un trattino isolato) non
combacia con nulla: `"" in testo` sarebbe vero per ogni risposta. Nel ramo
`short_text` del criterio robusto un contratto senza alias utilizzabili esce
`indeterminate` con metodo `short_text_contract_missing`; nell'estrattore
storico l'alternativa vuota semplicemente non passa.

Non c'è stemming né entailment: `cane` e `cani` restano parole diverse, e la
similarità lessicale resta secondaria. Il suo valore 1.0 per contenimento ora
richiede parole intere; sotto resta il rapporto di `SequenceMatcher`, che è una
somiglianza e non un riconoscimento. La normalizzazione segue la pratica di
SQuAD (Rajpurkar et al., EMNLP 2016) per maiuscole, punteggiatura e articoli;
l'estrattore storico rimuove anche gli articoli, il ramo robusto no, ma in
entrambi la stessa funzione vale sui due lati. I numeri non vengono
normalizzati, coerentemente con B1, dove `-3` e `3` restano valori distinti.

## B5 — Percorso del risultato del tool

Una risposta numerica corretta non prova che il numero venga dal tool, e un
numero uguale a quello restituito non prova che il modello lo abbia adottato.
La relazione sequenziale fra due eventi non è una relazione causale (Lanham et
al., 2023, §2.3): la coincidenza è compatibile con un'ipotesi del modello, con
una copia manuale o con una trace ricostruita.

Il valutatore registra cinque stati distinti, esposti in `MudilabEvaluation`:

```text
tool_called            chiamata cau_inference presente nella trace
tool_arguments_status  verified | mismatch | not recorded | unreadable
tool_call_status       success | failed | unverified | missing
tool_output_status     acquired | empty | not recorded
tool_adoption_status   verified_direct_forward | unverified | mismatch | not recorded
```

`llm_tool_use` resta `not_proven` in ogni caso: il framework misura il percorso
software, non il ragionamento del modello. L'harness orchestrato crea la
ricevuta con `forward_tool_result` (`MUDILAB_run/tool_trace.py`) nello stesso
passo in cui assegna il testo del tool al campo `numero`; la ricevuta dichiara
`producer`, `mode="direct_forward"`, `call_id`, i due campi e lo SHA-256 del
testo inoltrato. Il digest controlla l'integrità interna della trace, **non**
l'autenticità del produttore: chi falsifica l'intera trace può falsificare
anche la ricevuta. Per questo i record vanno acquisiti dall'harness fidato.

Il verdetto end-to-end richiede tutti e cinque gli stati; una trace legacy che
prova solo l'esecuzione resta `indeterminate` anche con il numero corretto. Un
`args` registrato diverso dalla traduzione valutata rende la riga `incorrect`,
e più chiamate senza `call_id` univoco non mescolano prove di chiamate diverse.
La CLI legge anche i nomi dell'orchestratore (`etichetta`, `traduzione`,
`numero`, `steps`, `output_provenance`) e sceglie il campo di destinazione:
una ricevuta che punta a `numero` non viene trasferita alla spiegazione.

## B7 — Identità esplicita del task

L'unità statistica di un benchmark ripetuto è il task, non la riga. Per
ricampionare i cluster serve un'identità **dichiarata**: `notes_with_task_id`
la serializza in `notes` con il prefisso `CW_TASK_ID_V1=` e
`record_task_id` la rilegge dal record o dal CSV, senza usare `prompt_id` come
sostituto. Lo schema CSV resta a 174 nomi perché l'identità passa da una
colonna già esistente.

Se l'identità manca, è parziale o è conflittuale, il bootstrap a cluster non si
calcola: `accuracy_cluster_bootstrap_95` resta `None` con la ragione in
`cluster_bootstrap_note`. Non si generano identificativi artificiali per far
funzionare l'intervallo: un ID inventato produrrebbe un intervallo più stretto
fingendo l'indipendenza che il cluster deve correggere. Il Wilson a livello di
riga resta pubblicato come diagnostica separata; le due ampiezze non misurano
direttamente l'intra-correlazione.

## B8 — Costo per risposta corretta ed ECE deprecato

`ece_per_joule = acc_comp / energia` è deprecato: `acc_comp` è un indice
descrittivo a pesi eterogenei, non un'accuratezza, e il rapporto mescolava due
scale. La riga scrive `ece_per_joule = "N/A"` con la nota che nomina `acc_comp`
come indice indipendente; nessun grafico o aggregato deve usarlo come misura di
efficienza energetica.

La metrica primaria di costo è operativa e dichiarata:

```text
costo per risposta corretta =
    somma dell'energia disponibile di TUTTI i tentativi
    / numero di TUTTE le risposte corrette
```

Il numeratore include errori, indeterminati e tentativi falliti quando la loro
energia è valida e disponibile: l'energia spesa in una risposta sbagliata è un
costo sostenuto, non un tentativo da cancellare. Il denominatore include anche
le corrette senza energia disponibile, altrimenti la stima si gonfierebbe
tenendo solo le righe misurate. Lo stato è `complete`, `partial` o
`unavailable`; in `partial` il totale è un **subtotale disponibile**, non un
totale completo, e la copertura è pubblicata accanto al rapporto.

La mediana dell'energia delle sole corrette resta una diagnostica separata: non
è il costo per corretta e non va presentata come tale. Con zero corrette il
rapporto è `None` con la ragione `zero correct answers`, mai zero o infinito.
Una riga entra nel totale solo se la validità è verificabile: flag `false`,
finestra `counter-invalid` o `unavailable`, valore negativo o non finito
restano visibili nelle mediane diagnostiche ma sono esclusi dal consumo, mai
clampati. Sul CSV unificato l'assenza di `active_valid` rende la riga non
verificabile; `energy_j` generico è accettato solo per compatibilità e la riga
lo dichiara. La copertura resta un campo separato dall'accuratezza, come in
HELM (§4.4 e App. C.2): un numero di accuratezza non implica che l'energia sia
stata misurata su tutte le righe.


