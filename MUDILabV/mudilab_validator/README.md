# MUDILab — validatore esterno

Il pacchetto aggiunge un validatore senza modificare `tools.py`, `funtions.py` o `FINAL.ipynb`.

## Funzioni
- Riferimenti per le 3 query `cond_prob` tramite inferenza sulla rete BIF.
- Riferimenti per le 3 query `inter` tramite `pyAgrum.causal.causalImpact`.
- Per `coherence`, probabilità condizionata e soglia 0,60 presente nel codice della professoressa.
- Confronto con le risposte degli agenti: errore assoluto, PASS/FAIL e report CSV.
- Controfattuali esclusi, in accordo con le istruzioni della professoressa.

## Prima di usarlo
Apri `queries.json`. Le query con `mapping_status: "review"` hanno una mappatura interpretativa da confermare. In particolare, il grafo distingue `Accident` da `ThisCarDam`, e `DrivQuality` da `DrivingSkill`; quest'ultima variabile non ha uno stato `Excellent` ma `Expert`. Non considerare definitivi questi riferimenti finché le mappature non sono state verificate.

## Installazione
Usa lo stesso interprete Python dell'ambiente notebook MUDILab:

```bash
python -m pip install pyagrum pandas
```

Metti nella stessa cartella `mudilab_validator.py`, `queries.json` e `insurance_grafo.bif`.

## Generare ground truth

```bash
python mudilab_validator.py --bif insurance_grafo.bif --queries queries.json --generate-reference
```

Viene creato `ground_truth.csv`. Le righe con `reference_status=ERROR` devono essere risolte prima di utilizzare i valori.

## Confrontare le 3 ripetizioni per query
Compila `agent_outputs_template.csv` (o crea `agent_outputs.csv`) usando una riga per ogni risposta. Colonne richieste: `task_id,run,agent_probability`; facoltative: `agent_label,agent_text`. Inserisci la probabilità come numero decimale, ad esempio `0.613`. Per `coherence`, compila anche `agent_label` con `compatible` o `not strongly compatible`.

```bash
python mudilab_validator.py --bif insurance_grafo.bif --queries queries.json --generate-reference --agent-results agent_outputs.csv --compare
```

Output: `comparison_report.csv`. La tolleranza numerica predefinita è 0,02; per cambiarla usa `--tolerance 0.05`.

## Limiti
Non è stato possibile installare `pyAgrum` in questo ambiente perché non disponeva di accesso alla rete; quindi i numeri non sono stati calcolati qui. La parte causale può richiedere adattamenti in base alla versione di pyAgrum installata. Il validatore segnala un errore anziché inventare un numero. La qualità delle spiegazioni in linguaggio naturale non viene valutata automaticamente. Associa energia CasualWatt, tempo e token alle stesse coppie `task_id`/`run`.
