# Confronto fra i due criteri di correttezza MUDILAB, sugli stessi run

**Data:** 3 novembre 2026. **Cosa confronta:** `benchmark/valuta.py` (il criterio che ha
prodotto le misure pubblicate il 02-11) contro `cwEnergyModular/mudilab_adapter.py` del
ramo GitHub `patch/scientific-evaluator-hardening` (e prima ancora
`parallel-robust-evaluator`), alla copia `f8903ba6`.
**Artefatti:** harness `MUDILAB_run/confronto_valutatori_20261103.py`, dettaglio riga per
riga `harness/risultati/confronto_valutatori_20261103.json`, tabella
`harness/risultati/confronto_valutatori_20261103.txt`.

## 1. Perche' questo confronto

La relazione di revisione (`accuratezza/rev_acc_strong.DOCX`, 03-11) chiude con due
affermazioni non verificate: che il nuovo valutatore sia «una base migliore» e che i suoi
test non siano stati eseguiti. Nessuna delle due dice cosa succede **alle misure gia'
pubblicate** se la correttezza comincia a essere definita dal nuovo criterio invece che da
`_confronta` di `genera.py`. Questa e' la domanda che conta, perche' la regola del repo e'
che un metodo non si sostituisce senza evidenza, e il confronto e' cio' che produce
l'evidenza. Non e' stata eseguita nessuna misura nuova: i verdetti sono ricalcolati sui
321 record JSON che l'harness ha scritto il 02-11, e nessun modello e' stato invocato.

## 2. Come

I moduli del ramo sono stati estratti **fuori dal repository** con `git archive
origin/patch/scientific-evaluator-hardening` in una cartella temporanea (`MUDILAB_RAMPO`),
senza checkout: il working tree e' rimasto su `emenda-8` e nessun file di `main` e'
cambiato. Per ogni record i due criteri ricevono **gli stessi campi**:

| campo | da dove viene | perche' |
|---|---|---|
| `label` | `valuta._etichetta_del_run` | e' la stringa che il pubblicato usa per `etichetta_ok` |
| `translation` | `risultato.traduzione` | e' l'oggetto che `valuta` confronta con `_norm` |
| `output` | `risultato.numero` | e' il testo che `genera._confronta` riceve |
| `energy_j` | `valuta._energia` | la stessa cascata pubblicata, non una rimedia |
| `tool_calls` | tre letture, vedi sotto | perche' i due formati non si toccano |

Il campo `tool_calls` e' letto in tre modi, e i tre modi sono il risultato piu' importante
di questa nota: `nessuno` = cosa contiene davvero il record (nulla: la chiamata e'
dimostrata dal passo `cau_inference` in `steps`); `dizionario` = la forma storica registrata
da `MUDILAB_correzioni/run_query.py:188-193` (`{"cau_inference": {"invocazioni": 1,
"eccezioni": 0}}`); `passi` = il passo tradotto a mano nello schema che l'adapter si
aspetta (`[{"name": ..., "success": ...}]`), cioe' il beneficio del dubbio.

## 3. Prima verifica: l'harness riproduce i numeri pubblicati

`77/240 (32,1%) e 964,929 J/corretta` sull'held-out `risultati_misura/b_composta/
20261102_191401`, `32/81 (39,5%) e 797,412 J/corretta` sul pilota dev `risultati_misura_
pilota/b_composta/20261102_183844`. Sono esattamente i valori pubblicati il 02-11: la
mappa dei campi non sposta nulla, quindi le divergenze sotto sono del criterio, non
dell'harness.

## 4. Risultato 1 - la verifica del tool azzera la misura

Con le due letture fedeli del record (`nessuno` e `dizionario`) il ramo produce **0 corrette
su 321**: delle 109 risposte che il criterio pubblicato conta come corrette, **90 diventano
`indeterminate`** e **19 diventano `incorrect`** (sono le righe `non_compatibile` del punto 5,
dove la nota sul marcatore scavalca la clausola sull'attrezzo). La causa delle 90 e' che
`mudilab_adapter.py:154-159` cerca una **lista di dict con la chiave `name`**, mentre il
record non ha `tool_calls` (la prova dell'esecuzione sta nel passo `cau_inference`) e la forma
storica e' un **dict con chiavi italiane**. Iterando un dict si ottengono le chiavi-stringa,
`isinstance(call, Mapping)` e' falso, `matching_calls` resta vuoto, `tool_status = "missing"`,
e `end_to_end` scende a `indeterminate` per la clausola a `:174`. Il J/corretta non e'
calcolabile: denominatore zero.

La prova di esecuzione che la revisione stessa chiedeva esiste nei dati gia' registrati
(`invocazioni >= 1` con `eccezioni == 0`, e il campo `tool_ok` a `run_query.py:185`): il ramo
non la usa.

## 5. Risultato 2 - il controllo `coherence`: invertito su una classe, cieco sull'altra

Anche dando al ramo il beneficio del dubbio (`passi`), restano **90 corrette su 321 contro
109**: 19 righe perse, tutte con `expected_decision = non_compatibile`. La distribuzione per
classe decisionale, sulle 80 righe coherence del corpus:

| `expected_decision` | pubblicato corrette | verdetto del ramo |
|---|---|---|
| `compatible` (40 righe) | 1 | 1 correct, 39 incorrect |
| `non_compatibile` (40 righe) | 19 | **0 correct, 40 incorrect** |

Il meccanismo e' leggibile: `mudilab_adapter.py:183-188` gestisce gli enum
`not_strongly_compatible` e `strongly_compatible`, che nel dataset **non compaiono**
(`benchmark/benchmark.csv`, valori reali `compatible` e `non_compatibile`, 20 + 20 task id),
e per ogni altro valore deriva il marker con `replace("_", " ")`. Per `non_compatibile` il
marker diventa la stringa italiana `"non compatibile"`, che non puo' comparire nell'output
inglese del ramo, che e' `Evidences are NOT strongly compatible with a single ...`
(`consegna/tools_corretto.py:453`). Esempio misurato: `COH08 r1`, output `Evidences are NOT
strongly compatible with a single CarValue of FiveThou with a probability of 0.2568`, nota
`coherence qualitative decision mismatch` - la risposta e' giusta, il verdetto e' `incorrect`.
Il controllo non e' quindi "troppo rigido" come diceva la revisione: **e' invertito su una
classe intera**, e il commit `c43d498f` ("Harden MUDILAB decision parsing") ha indurito
l'enum sbagliato.

Lo stesso blocco ha un secondo difetto, opposto e misurato sulla classe `compatible`: la
deriva a `:188` produce il marker `"compatible"`, che e' sottostringa di `"not strongly
compatible"`, e la guardia sul negativo a `:192-193` scatta solo per i due nomi enum, non
per il vocabolario reale (la terza disgiunzione a `:194` rende `decision_ok` uguale a
`any(observed)` senza controlli). Sui dati: **24 righe** (12 task id × 3 ripetizioni) con
`expected_decision = compatible` stampano la frase negativa - `COH03 r1`, output
`Evidences are NOT strongly compatible with a single AntiTheft of False with a probability
of 0.3104` - e il controllo decisione **non emette nessuna nota** su nessuna delle 24 (0 su
24 contro 40 su 40 della classe opposta). Diventano `incorrect` lo stesso, ma per la fase
numero (`stampato [0.3104] atteso 0.7335933572`), non per la qualita': il **falso positivo**
qualitativo esiste ed e' coperto da un altro controllo, non dal controllo che dovrebbe
esisterlo.

## 6. Risultato 3 - dove i due criteri concordano, e la revisione non aggiunge nulla

Sulle altre fasi, in `passi`, la concordenza e' totale sui verdetti che contano:

```
label        etichetta_ok=True / correct                   321
translation  mappatura_ok=True / correct                   109
translation  mappatura_ok=False / incorrect                 88
translation  mappatura_ok=False / indeterminate            124
output       numero_ok=True / correct                      109
output       numero_ok=False / incorrect                   212
```

Due letture oneste di questa tabella. (a) Le due preoccupazioni statiche che avevo sollevato
prima di eseguire - il confronto `_norm` (maiuscole/spazi) contro l'uguaglianza esatta di
`_evaluate_structured`, e il fatto che `_evaluate_interval` esiga le parole inglesi
`between/from ... and/to` dove `_confronta` conta solo i numeri stampati - **non si sono
manifestate su questo corpus**: i 26 controfattuali pubblicati-correct sono correct anche per
il ramo, e nessuna riga con `mappatura_ok` vera e' stata degradata. Vanno letti come
**percorsi non ancora sotto prova, non come percorsi sicuri**: delle 80 righe controfattuali
61 arrivano a `interval_bounds_match` e le 19 a `interval_not_found` hanno tutte il testo di
output vuoto (sono righe fermate dal gate, 0 corrette anche dal pubblicato) - la regex
inglese non ha quindi mai dovuto decidere su un numero stampato in prosa; e le 321 righe
disponibili hanno traduzioni con lo stesso lessico del ground truth, quindi non mettono alla
prova ne' l'espressione libera del numero ne' la traduzione parafrasata - che sono i due casi
in cui `_confronta` e `_evaluate_structured` possono separarsi. (b) La colonna `label` a
321/321 **non e' una misura del
classificatore**: `etichetta_ok` e' alimentato dal recupero che rilegge il testo del passo, e
quel testo cita l'etichetta attesa in tutti i run (rettifica del 02-11,
`benchmark/valuta.py:203-228`). Il contratto `label` del ramo eredita la stessa non-misura.

Un accordo che invece **manca** e va detto: le 124 righe fermate dal gate della traduzione
diventano `incorrect` con confidenza 0.99 (`robust_evaluator.py:225`, `number_no_answer`),
non `indeterminate`. Sono fermi dell'acquisizione, non risposte sbagliate del modello - e'
esattamente la distinzione che la revisione chiedeva di introdurre ("separare risposte errate
da risposte non valutabili") e che il ramo non ha introdotto per questo caso.

## 7. Effetto sulle metriche pubblicate

| insieme | pubblicato | ramo (`passi`) | ramo (`nessuno`) |
|---|---|---|---|
| held-out 240 | 77/240 (32,1%) - 964,929 J/c | 59/240 (24,6%) - **1.259,314 J/c (+30,5%)** | 0/240 - non calcolabile |
| pilota dev 81 | 32/81 (39,5%) - 797,412 J/c | 31/81 (38,3%) - 823,135 J/c (+3,2%) | 0/81 - non calcolabile |
| solo coherence (80) | 20/80 - 1.476,745 J/c | 1/80 - **29.534,901 J/c** | 0/80 |
| cond_prob / inter / counterfactual | 39/81, 24/80, 26/80 | identici, identici J/c | 0 |

Il J/corretta cresce perche' il numeratore (l'energia di tutti i run) non cambia e il
denominatore si assottiglia per una ragione di ortografia, non di misura.

## 8. Condizioni perche' il ramo diventi adottabile

1. Mappare il vocabolario reale del ground truth: `compatible` / `non_compatibile` come
   chiavi, e il marker negativo riconosciuto nella forma inglese che il ramo stampa; e
   invertire la guardia anche per il positivo, perche' `"compatible"` e' sottostringa di
   `"not strongly compatible"`.
2. Leggere la prova di esecuzione cosi' come esiste nei record (passo `cau_inference`, o
   `invocazioni`/`eccezioni`, o `tool_ok`) invece di pretendere `[{"name", "success"}]`;
   e verificare anche gli argomenti della chiamata, che la revisione chiedeva e che tuttora
   non sono controllati (`mudilab_adapter.py:154-169` guarda solo nome ed esito).
3. Portare i 18 test del ramo (`test_robust_evaluator.py` 11, `test_mudilab_adapter.py` 5,
   `test_evaluation_runner.py` 2) a includere i tre casi che questo confronto ha colpito:
   una riga `non_compatibile` con output inglese corretto, una riga `compatible` il cui
   output dice il negativo, e un `tool_calls` a dizionario.
   Oggi i fixture sono inventati (`test_mudilab_adapter.py:4-20`) e per questo non vedono
   nessuno dei tre.
4. Dichiarare quale dei due criteri e' l'arbitro, e non fondere le due definizioni nella
   stessa tabella: 109 e 90 non sono due misure dello stesso modello, sono due misure di due
   cose diverse.

## 9. Limiti di questa nota

Una sola variante di prompt (`b_composta`) e un solo modello (`llama3.2:3b-instruct-q4_K_M`),
temperature 0, ripetizioni 3: le 321 righe sono i due insiemi pubblicati, non i sette run del
01-11 (`harness/risultati/b_base`, `b_composta`, `b_esempi`, `b_solo_numero`,
`b_verificata` x2, `b_vincolata`: 567 righe da 81, non usate qui perche' la misura
pubblicata e' quella del 02-11). Non ho eseguito la suite del ramo, e
quindi non dichiaro che i suoi 18 test passino: dichiaro solo cosa producono i suoi criteri
sui dati reali. Il motore energetico non e' stato ne' rieseguito ne' toccato: `energy_j` e'
letto dai record.

## 10. Ancoraggi

`mudilab_adapter.py:154-159, 168-174` (forma e stato del tool), `:181-198` (decisione
qualitativa; `:188` deriva del marker, `:192-194` guardia sul negativo keyed agli enum);
`robust_evaluator.py:225` (`number_no_answer` = incorrect, conf. 0.99),
`:323-351` (intervallo), `:371-393` (structured); `benchmark/genera.py:528-551`
(`_confronta`, marker `"NOT strongly compatible"` a `:548`), `:731-737` (`_features`);
`benchmark/valuta.py:163-168` (`_norm`), `:203-228` (recupero etichetta e sua rettifica),
`:235-276` (`_valuta_run`); `benchmark/__init__.py:56` (`TOLL = 5e-4`);
`benchmark/benchmark.csv` (161 righe, `expected_decision` = `compatible` 20 +
`non_compatibile` 20, misurato il 03-11); `consegna/tools_corretto.py:453` (frase reale del
ramo); `MUDILAB_correzioni/run_query.py:185, 188-193` (forma registrata di `tool_ok` e
`tool_calls`). I conteggi del punto 5 (24 righe `compatible` con marcatore negativo e 0 note,
40 su 40 `non_compatibile` con nota) si rigenerano dai tre campi
`righe[].expected_decision`, `righe[].testo_output`, `righe[].rampo.passi.notes` del JSON.
Rami: `parallel-robust-evaluator` = `b4e6dbd4`,
`patch/scientific-evaluator-hardening` = `f8903ba6`, 18 commit sopra `parallel`, `main`
invariato, nessuna PR, nessun workflow CI nel repo.
