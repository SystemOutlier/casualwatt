# Relazione tecnica sul valutatore parallelo robusto

**Progetto:** CasualWatt  
**Componente:** `cwEnergyModular/robust_evaluator.py`  
**Versione analizzata:** branch `parallel-robust-evaluator`, commit `3a82906`  
**Data:** 3 novembre 2026

## 1. Scopo

Il valutatore parallelo nasce per correggere un limite metodologico del
valutatore storico: una similarità semantica fra risposta e ground truth non è,
da sola, una misura sufficiente di correttezza. Può essere utile come evidenza
secondaria, ma tende a confondere:

- correttezza con somiglianza linguistica;
- errore con risposta formulata in modo diverso;
- risposta non valutabile con risposta errata;
- qualità della spiegazione con correttezza del risultato;
- numero dell'item con prestazione del modello.

Il nuovo componente non sostituisce `evaluator.py` e non modifica i benchmark
precedenti. È un secondo percorso di misura, progettato per essere
conservativo, riproducibile e confrontabile con il percorso storico.

## 2. Principio metodologico centrale

La domanda primaria non è:

> «Quanto è simile la risposta alla reference?»

ma:

> «La risposta soddisfa un contratto di verità esplicito, verificabile e
> appropriato al tipo di domanda?»

Per questo il sistema richiede una reference strutturata. Una stringa libera
come `"Roma"` non è considerata automaticamente una specifica sufficiente:
viene classificata come `indeterminate`. Il sistema evita così di trasformare
un riferimento ambiguo o incompleto in un risultato apparentemente preciso.

## 3. Architettura del valutatore

### 3.1 Contratto di riferimento

Ogni item dichiara:

- `answer_type`: `number`, `short_text` o `free_text`;
- una o più risposte accettate;
- tolleranza assoluta e relativa per i numeri;
- fatti necessari e fatti proibiti per il testo libero;
- numero minimo di fatti richiesti.

Esempio numerico:

```json
{
  "answer_type": "number",
  "accepted_answers": ["0.212"],
  "absolute_tolerance": 0.0005,
  "relative_tolerance": 0.000001
}
```

Esempio di testo libero:

```json
{
  "answer_type": "free_text",
  "required_facts": ["Roma", "Lazio", "Tevere"],
  "forbidden_facts": ["Firenze"],
  "minimum_required_facts": 3
}
```

### 3.2 Valutazione numerica

Il sistema:

1. cerca un marcatore esplicito (`answer:`, `risposta:`, `result:`);
2. converte il valore con supporto per la virgola decimale;
3. confronta il valore con le alternative accettate;
4. applica una tolleranza dichiarata:

```text
|x - x_ref| <= max(tolleranza_assoluta,
                   tolleranza_relativa × max(|x_ref|, 1))
```

Se una risposta contiene più numeri ma non dichiara quale sia il risultato
finale, il verdetto è `indeterminate`. Questa scelta è intenzionale: non si
assume che l’ultimo numero nel testo sia necessariamente la risposta.

### 3.3 Valutazione di risposte brevi

Le risposte brevi vengono normalizzate rimuovendo maiuscole, accenti e
punteggiatura, ma il confronto usa i confini delle parole. In questo modo
`Athens` può essere accettato come alias di `Atene`, mentre `Ateneo` non viene
accettato come corrispondenza accidentale di `Atene`.

### 3.4 Valutazione del testo libero

Il sistema non tenta di dedurre la correttezza generale con un embedding.
Verifica invece:

- presenza dei fatti richiesti;
- assenza dei fatti proibiti;
- rispetto del numero minimo di fatti;
- percentuale di fatti richiesti presenti.

Questo è un controllo basato su attributi osservabili. Non pretende di risolvere
tutta la valutazione semantica: se i fatti non sono stati dichiarati nella
reference, il risultato corretto è `indeterminate`.

### 3.5 Stati e aggregazione

Sono definiti tre stati:

- `correct`;
- `incorrect`;
- `indeterminate`.

L’accuracy viene calcolata solo sui casi determinati, mentre il tasso di casi
indeterminati viene riportato separatamente. Per campioni piccoli viene
calcolato anche l’intervallo di Wilson al 95%, evitando di presentare una
percentuale puntuale come se fosse una stima precisa.

## 4. Fondamento teorico e bibliografico

### 4.1 Teoria della misurazione e validità del costrutto

Il valutatore segue il principio della **validità del costrutto**: prima di
misurare occorre definire quale proprietà si vuole misurare e quali osservazioni
la rappresentano. La similarità testuale è un costrutto diverso dalla
correttezza fattuale.

Riferimento generale:

- Messick, S. (1989), *Validity*, in R. L. Linn (ed.), **Educational
  Measurement**, 3rd ed., Macmillan.

Applicazione nel codice:

- il tipo di risposta è esplicito;
- la reference deve dichiarare i criteri verificabili;
- la similarità semantica non viene usata come verità primaria;
- un riferimento insufficiente produce `indeterminate`.

Questa separazione riduce il rischio di **validità di facciata**: un punteggio
numericamente elegante ma non corrispondente alla proprietà che si dichiara di
misurare.

### 4.2 Exact Match e F1 nella valutazione di question answering

La valutazione di SQuAD ha reso pratica comune la combinazione di:

- **Exact Match**, utile quando la risposta deve coincidere con una risposta
  canonica;
- **token-level F1**, utile quando esistono sovrapposizioni parziali.

Riferimento:

- Rajpurkar, P., Zhang, J., Lopyrev, K., Liang, P. (2016), *SQuAD: 100,000+
  Questions for Machine Comprehension of Text*, EMNLP.
  https://aclanthology.org/D16-1264/

Il nuovo valutatore non copia meccanicamente SQuAD, perché il suo obiettivo
include numeri e spiegazioni. Ne riprende però il principio: usare una metrica
deterministica e coerente con la struttura della risposta, invece di una
singola similarità globale.

### 4.3 Valutazione multidimensionale: HELM

HELM propone di non ridurre la valutazione di un modello a una sola accuracy.
Le dimensioni includono, fra le altre:

- accuracy;
- calibrazione;
- robustezza;
- efficienza;
- bias e fairness;
- tossicità.

Riferimento:

- Liang, P. et al. (2022), *Holistic Evaluation of Language Models*,
  arXiv:2211.09110.
  https://arxiv.org/abs/2211.09110

Il valutatore parallelo applica questo principio separando:

- verdetto di correttezza;
- confidenza del metodo;
- diagnostica;
- casi indeterminati;
- aggregati con intervallo d’incertezza.

L’efficienza energetica di CasualWatt resta una dimensione separata e non viene
fusa artificialmente con la correttezza.

### 4.4 Limiti dell’LLM-as-a-Judge

Il precedente valutatore usa un LLM Judge come componente della metrica
composita. La letteratura mostra che un giudice automatico può essere utile,
ma è soggetto a bias, sensibilità all’ordine, preferenza per risposte
verbose e difficoltà nel distinguere forma e correttezza. Per questo il nuovo
percorso non gli delega la decisione primaria.

Riferimento:

- Zheng, L. et al. (2023), *Judging LLM-as-a-Judge with MT-Bench and Chatbot
  Arena*, arXiv:2306.05685.
  https://arxiv.org/abs/2306.05685

L’LLM Judge può essere aggiunto in seguito come:

- diagnostica;
- secondo valutatore;
- strumento per proporre fatti candidati;
- componente validata contro annotatori umani.

Non deve però sostituire una reference verificabile nei compiti chiusi.

### 4.5 Affidabilità tra valutatori umani

Per le risposte libere, la definizione dei fatti richiesti dovrebbe essere
controllata da almeno due annotatori indipendenti. L’accordo non dimostra da
solo la verità, ma segnala se il criterio è sufficientemente chiaro.

Riferimento:

- Krippendorff, K. (2011), *Computing Krippendorff’s Alpha*, Departmental
  Papers, University of Pennsylvania.
  https://repository.upenn.edu/handle/20.500.14332/21537

Sviluppo raccomandato:

1. due annotatori definiscono i fatti richiesti;
2. si calcola Krippendorff’s alpha;
3. i casi di disaccordo diventano esempi del protocollo;
4. solo dopo si congela il contratto dell’item.

Il codice attuale non calcola ancora alpha: il contratto strutturato rende però
possibile aggiungerlo senza cambiare la logica di valutazione.

### 4.6 Intervallo di Wilson

Una proporzione osservata su pochi casi è molto incerta. Il nuovo aggregatore
usa l’intervallo di Wilson al 95% invece dell’approssimazione normale
simmetrica, che è inadeguata soprattutto con campioni piccoli o accuracy vicine
a 0 o 1.

Riferimento:

- Wilson, E. B. (1927), *Probable Inference, the Law of Succession, and
  Statistical Inference*, Journal of the American Statistical Association,
  22(158), 209–212.
  https://doi.org/10.1080/01621459.1927.10502953

Il codice riporta anche:

- numero totale di item;
- numero di item determinati;
- numero di item indeterminati;
- accuracy sui determinati;
- tasso di indeterminati;
- confidenza media del metodo.

## 5. Confronto con il valutatore storico

| Aspetto | Valutatore storico | Valutatore parallelo |
|---|---|---|
| Numeri | estrazione e tolleranza molto stretta | contratto e tolleranze esplicite per item |
| Testo breve | contenimento della stringa | alternative dichiarate e confini delle parole |
| Testo libero | embedding, soglia e possibile judge | fatti richiesti/proibiti |
| Reference mancante | può produrre proxy diagnostici | `indeterminate` |
| Similarità semantica | può diventare la metrica principale | solo diagnostica futura |
| LLM Judge | componente della score composita | non decide da solo |
| Ambiguità numerica | ultimo numero estratto | `indeterminate` senza risposta marcata |
| Aggregazione | percentuale facilmente interpretabile male | accuracy + Wilson + indeterminate rate |
| Tracciabilità | campi numerosi ma metriche miste | metodo e diagnostica per ogni risultato |

## 6. Cosa è già dimostrato

Nel branch parallelo sono presenti sei test automatici:

- risposta numerica marcata corretta;
- risposta numerica marcata errata;
- risposta numerica ambigua;
- tolleranza numerica assoluta;
- alias e confini delle parole;
- fatti richiesti/proibiti;
- reference non strutturata;
- aggregazione con casi indeterminati e intervallo Wilson.

Risultato dell’esecuzione: **6 test superati su 6**.

Questo dimostra la coerenza interna dell’implementazione, non ancora la validità
esterna su un benchmark ampio.

## 7. Limiti attuali

Il nuovo sistema è più solido, ma non è una soluzione completa per ogni tipo di
risposta.

1. La presenza letterale di un fatto non verifica automaticamente negazione,
   contesto o implicazione logica.
2. Il contratto deve essere scritto correttamente da esperti.
3. Le parafrasi complesse possono essere classificate come indeterminate.
4. Non esiste ancora un set di annotazioni umane indipendenti.
5. Non sono ancora calcolati alpha di Krippendorff, precision, recall e F1
   rispetto a un gold standard umano.
6. La confidenza attualmente descrive la robustezza del percorso tecnico, non è
   una probabilità calibrata di correttezza.
7. Non è ancora integrato un controllo sistematico di contaminazione del
   benchmark.

## 8. Piano di validazione scientifica

Per trasformare il componente in un metodo sperimentalmente validato:

### Fase A — Costruzione del dataset

- separare train, development e test;
- congelare il test prima dei confronti fra modelli;
- usare item nuovi e documentare la provenienza;
- definire contratti numerici, brevi e liberi;
- includere casi negativi, quasi-corretti e ambigui.

### Fase B — Annotazione

- almeno due annotatori indipendenti;
- protocollo scritto con esempi;
- calcolo di Krippendorff’s alpha;
- arbitraggio solo dopo la misura dell’accordo iniziale.

### Fase C — Confronto dei valutatori

Confrontare il metodo storico e quello parallelo su identiche risposte,
riportando:

- accuracy;
- precision, recall e F1 sul verdetto binario;
- tasso di indeterminati;
- accordo con il gold standard umano;
- intervalli di confidenza;
- errori separati per tipo di item.

### Fase D — Robustezza

Ripetere la valutazione con:

- parafrasi;
- ordine diverso delle frasi;
- numeri intermedi;
- risposte prolisse;
- negazioni;
- errori intenzionali minimi;
- lingue e formati numerici diversi.

### Fase E — Calibrazione

Se si introduce una confidenza probabilistica, deve essere calibrata su un set
separato. Le metriche possibili sono Brier score, Expected Calibration Error e
reliability diagram. I valori attuali di `confidence` non devono essere
interpretati come probabilità calibrate.

## 9. Conclusione

Il nuovo valutatore è supportato da principi consolidati:

- validità del costrutto e definizione operativa della proprietà misurata;
- metriche deterministiche appropriate al tipo di risposta;
- valutazione multidimensionale e trasparente;
- separazione fra correttezza e qualità linguistica;
- controllo dell’affidabilità tra annotatori;
- intervalli di confidenza adatti a proporzioni su piccoli campioni.

La scelta più importante è metodologica: **quando la reference non consente una
decisione difendibile, il sistema non inventa un punteggio**. Questo rende la
misura meno appariscente, ma più onesta e più adatta a una valutazione
scientifica.

Il componente è quindi una base solida per il nuovo protocollo di benchmark,
ma la sua validità empirica dovrà essere dimostrata con annotazioni
indipendenti, test di robustezza e confronto con un gold standard congelato.
