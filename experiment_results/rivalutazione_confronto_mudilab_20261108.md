# Ri-valutazione del confronto MUDILAB del 03-11 con il criterio corrente (08-11-2026)

Documento dell'08-11-2026. Non introduce misure: riapplica il criterio corrente
alle stesse 321 righe del confronto del 03-11-2026 e ne pubblica il risultato
come artefatto separato, con nome proprio, accanto a quello che registra la
misura di allora.

## 1. Perché un artefatto separato

`MUDILAB_run/harness/risultati/confronto_valutatori_20261103.{json,txt}`, al
commit `303051dd9`, è la fotografia del confronto del 03-11: criterio pubblicato
e ramo hardened (`nessuno`/`passi`/`dizionario`) sugli stessi 321 run, con il
ramo `passi` a 90/321 corrette. Dopo quel giorno il ramo ha cambiato il
trattamento della chiamata al tool: `98ec5972` (04-11) fa derivare la tolleranza
dai decimali che il tool stampa, `6fc13d013` (05-11) separa chiamata, argomenti,
esito, output e adozione. Le stesse righe, lette dal criterio nuovo, non danno
la stessa tabella. Sovrascrivere il file del 03-11 avrebbe distrutto la
fotografia contro cui si è deciso e reso non riproducibile il 90/321 citato; per
questo la ri-valutazione ha un nome proprio e un driver proprio.

## 2. Provenienza

- righe: `MUDILAB_run/harness/risultati/confronto_valutatori_20261103.json` al
  commit `303051dd9` (blob `44f6f98d…`, 321 righe, cartelle
  `risultati_misura/b_composta/20261102_191401` e
  `risultati_misura_pilota/b_composta/20261102_183844`);
- codice: `HEAD` `b11c8fc380ae58c89ce2ab0d0902e43bbabab168`, estratto con
  `git archive HEAD cwEnergyModular` in una cartella fuori dal repository
  (`%LOCALAPPDATA%\Temp\rivalutazione_20261108_src\cwEnergyModular`), così la
  provenienza è un commit e non un albero di lavoro;
- driver: `MUDILAB_run/rivalutazione_confronto_20261108.py`, che importa
  `MUDILAB_run/confronto_valutatori_20261103.py`, reindirizza `OUT_BASE`
  (`confronto_valutatori_20261103.py:68`) sul nome nuovo e invoca `main()`
  senza argomenti, quindi sulle stesse due cartelle del 03-11 (`:265-266`);
- comando:

  ```
  set MUDILAB_RAMPO=<cartella>\cwEnergyModular
  python MUDILAB_run\rivalutazione_confronto_20261108.py
  ```

- artefatti: `confronto_valutatori_20261103_rivalutato_20261108.json`
  (2.419.619 B, SHA-256 `eaeb400f1456876154c27c61e0fec154f128ad5cace4e9c5a9add0790cf0de58`)
  e `.txt` (5.512 B, SHA-256
  `f8b2f3ee26beb86ce7def9bb9e4b6518f63ca304676c29ffb77ec79088de6f50`).

Nessun modello è stato invocato e nessuna energia è stata riletta: cambiano solo
i verdetti del ramo. Il lato pubblicato passa dallo stesso `benchmark/valuta.py`
e resta 109/321 con 915,749 J/corretta.

## 3. Risultato

Con il criterio corrente i tre modi di leggere la chiamata al tool collassano
sullo stesso esito: `nessuno`, `passi` e `dizionario` danno 0 corrette su 321,
88 righe determinate (copertura 27,41%) e 233 indeterminate. Per `passi` le
cause sono 212 accordi con il criterio pubblicato e 109 «altra causa».

| insieme | determine | copertura |
|---|---|---|
| dev | 27/81 | 33,33% |
| held-out | 61/240 | 25,42% |
| coherence | 41/80 | 51,25% |
| cond_prob | 8/81 | 9,88% |
| counterfactual | 35/80 | 43,75% |
| inter | 4/80 | 5,00% |

Il riepilogo del ramo `passi` portato nell'artefatto dà `n_determinate = 88`,
`accuracy_on_determinate = 0,0`, `coverage = 0,274143`, intervallo di Wilson
`[0; 0,041827]`, `n_effective_tasks = 48` e bootstrap a cluster `[0; 0]`.

Il confronto appaiato su questo artefatto, prodotto con
`cwEnergyModular/tools/mcnemar_report.py`, è **indeciso**: 161 task ridotti a
una coppia con la regola `first`, matrice `a=0 b=0 c=0 d=48`, 113 coppie
escluse per indeterminazione (70,2%), p esatto 1,0, delta 0, intervallo di
Newcombe `[-0,0741; 0,0741]`. Nessuna coppia discordante non è una parità
dimostrata, e la quota di escluse supera la soglia di cautela del 10%.

## 4. Perché il ramo passa da 90 corrette a 0

La causa non è un peggioramento del ramo: è ciò che il record registrato
contiene. L'harness traduce un passo `cau_inference` in una chiamata con
`success` vero quando il passo esiste e ha stampato un testo
(`confronto_valutatori_20261103.py:76-88`), e non passa alcuna provenienza
dell'output (`:112-121`). Il criterio del 05-11 chiede di più: lo stato di
esecuzione senza chiamata diventa `missing` (`mudilab_adapter.py:166` e
`:193`), l'adozione dell'output senza ricevuta diventa `not recorded`
(`:479` e `:486-487`) e gli argomenti vanno verificati separatamente
(`:289`). Con uno stadio indeterminato il verdetto finale è indeterminato
(`:543-545`).

L'asimmetria è voluta: un numero sbagliato resta sbagliato anche senza prova di
adozione, un numero giusto no. Per questo le 88 righe determinate sono tutte
incorrect, le 109 righe con output corretto ma adozione non provata cadono fra
le indeterminate, e le 124 con output già indeterminato fanno il resto dei 233.
Il 90/321 del 03-11 resta il numero giusto per il criterio di allora; lo 0/321
di oggi dice che quel record non basta a certificare la correttezza sotto la
regola nuova. Se il ramo deve essere adottato, l'harness che produce i run deve
registrare argomenti, call-id e provenienza dell'output, non solo il testo del
passo.

## 5. Limiti

- Non è una nuova misura: gli stessi 321 run del 02-11, nessun modello
  rieseguito, nessuna finestra energetica riletta, energia del lato pubblicato
  invariata.
- Non sostituisce `confronto_valutatori_20261103`: quello resta la fotografia
  del 03-11, e i numeri del 03-11 (109/321 del criterio pubblicato, 90/321 del
  ramo, 915,749 J/corretta) non cambiano.
- I tre modi di leggere il tool coincidono qui perché nessuno dei tre porta la
  prova che il criterio nuovo richiede; la loro distinzione resta utile solo
  per ricostruire la storia del formato, non per confrontare i criteri.
- L'intervallo di Wilson `[0; 0,041827]` e il bootstrap `[0; 0]` sono degeneri:
  88 determinati su 88 sono incorrect, quindi la varianza campionaria è zero.
  Un intervallo di larghezza nulla non è una precisione, è un campione senza
  successi; il bootstrap a cluster resta comunque quello di 48 task distinti.
- Il test appaiato non può concludere nulla: 113 task su 161 sono esclusi e le
  48 coppie rimaste sono concordanti nel torto. La cautela del 10% è superata
  di sette volte.

## 6. Riproducibilità

La riesecuzione dell'08-11-2026 dà un `summary` e una lista `righe` identici,
come oggetti JSON, e un `.txt` identico byte per byte alla copia rigenerata il
07-11-2026 che era stata conservata fuori dal repository prima del ripristino
del file tracciato: la ri-valutazione è deterministica a parità di codice e
righe, e la copia del 07-11 è riprodotta esattamente, non solo nei conteggi.
Il driver richiede `MUDILAB_RAMPO`
e non indovina il codice; il ripristino del file del 03-11 è descritto nella
sezione 3.6 della revisione del metodo di accuratezza
(`experiment_results/revisione_metodo_accuratezza_20261108.md`).

## 7. Ancore

- `MUDILAB_run/confronto_valutatori_20261103.py:68` — `OUT_BASE` del confronto
  del 03-11, reindirizzato dal driver;
- `:76-88` — `tool_calls_passi`, la prova più forte che il record offre;
- `:99-100` — i tre modi (`nessuno`, `passi`, `dizionario`);
- `:112-121` — chiamata a `evaluate_case` senza `output_provenance`;
- `:263-292` — `main()` e costruzione del riepilogo;
- `cwEnergyModular/mudilab_adapter.py:166`, `:193` — stato di esecuzione
  mancante;
- `:289` — verifica degli argomenti;
- `:479`, `:486-487` — adozione dell'output non registrata;
- `:543-545` — stadio indeterminato che rende indeterminato il verdetto finale;
- commit `98ec5972` (04-11-2026) e `6fc13d013` (05-11-2026) — i due cambi del
  criterio che separano le due letture;
- `MUDILAB_run/rivalutazione_confronto_20261108.py` — il driver, con la
  provenienza dichiarata nella docstring.
