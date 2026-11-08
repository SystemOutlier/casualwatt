# Fase 3 — relazione metodologica McNemar per CasualWatt

Data: 2026-11-07. Stato: specifica proposta e implementata a livello di
modulo (`paired_mcnemar` in `cwEnergyModular/evaluation_runner.py`),
con test `cwEnergyModular/tests/test_paired_mcnemar.py`. Nessuna riga del
percorso di misura modificata. La scelta di portare il test fuori dal report
del valutatore e' annunciata in `evaluation_runner.py:79-81`.

Aggiornata l'08-11-2026: l'intervallo e' quello di Newcombe (metodo 10) con il
phi corretto del 2x2, non piu' la quadratura degli errori marginali, e
`correction_applied` distingue `yes`, `no` e `not_applicable` invece di essere
una costante (vedi §9).

## 1. Avviso di presenza

`RobustEvaluator` e il report a livello di task usano Wilson che assume
indipendenza e bootstrap su cluster. Un confronto fra due sistemi **sullo
stesso task** non si fa per sovrapposizione di intervalli: resta una McNemar
appaiata. Alla data della specifica questa era la lacuna della suite di
valutazione; dal 2026-11-08 la funzione esiste e ha test proprio (§9).

## 2. Caso di studio: due sistemi sullo stesso task

Si confrontano due sistemi `A` e `B` sulle **stesse** richieste. Ogni task `i`
produce una coppia `(A_i, B_i)` di esiti binari.

## 3. Matrice di McNemar

Per task `i`, `A_i, B_i ∈ {0,1}` (1 = corretto, 0 = non corretto). La
tabella 2x2 e':

```
              B = corretto   B = non corretto
A = corretto      a               b
A = non corretto  c               d
```

- `a` = entrambi corretti
- **`b`** = solo A corretto
- **`c`** = solo B corretto
- `d` = entrambi non corretti

`b` e `c` sono le coppie **discordanti**. Il test usa solo queste: `a` e `d`
sono concordanti e non portano informazione sulla differenza.

**Statistica (correzione di continuita').** `χ² = (|b − c| − 1)² / (b + c)`,
df = 1, p-value a due code. Se `b + c < 10` si usa il test binomiale esatto
su `b ~ Bin(b+c, 0.5)`. Se `b + c = 0` il test è **indecidibile** (non
"parità"), da riportare.

**Non si usa** la formula per due proporzioni indipendenti
`√(p_A(1−p_A)/n + p_B(1−p_B)/n)`: assume indipendenza tra A e B, che non
c'è perché lo stesso task genera entrambe. L'appaiamento esiste proprio per
correggere questo.

## 4. Intervallo di confidenza appaiato

| metodo | quando | cosa dà |
|---|---|---|
| binomiale esatto | sempre, per p-value | p-value esatto |
| Newcombe appaiato | `b+c` moderato, serve CI | intervallo su `Δ=(b−c)/n` |
| bootstrap appaiato per task | dipendenza tra task (§4) | intervallo robusto a cluster |

**Raccomandazione:** binomiale esatto per il p-value (sempre); Newcombe per la
CI quando si pubblica un intervallo. Ipotesi: coppie indipendenti tra task;
sotto H₀ `P(b)=P(c)`. Limite: McNemar misura significativita', non effetto —
si riporta sempre `b`, `c`, `b−c`.

## 5. Risposte indeterminate, missing e technical_error

| categoria | definizione |
|---|---|
| correct | `is_correct = 1` |
| incorrect | `is_correct = 0` |
| indeterminate | esiste ma non interpretabile |
| missing | nessuna risposta prodotta |
| technical_error | errore tecnico (crash, timeout, `V4MeasurementError`) |

**Pericolo.** Escludere le indeterminate dal denominatore aumenta l'accuratezza
se i sistemi differiscono nella propensione a produrle.

**Strategia.** accur_op = correct / (correct+incorrect+indeterminate+missing);
accur_cond = correct / (correct+incorrect); copertura = (correct+incorrect)/totale.
Si riportano tutti e tre. Per McNemar la matrice si costruisce sulle sole coppie
determinate, ma il numero di esclusi va nella nota; se >10% esclusi, interpretare
con cautela.

## 6. Dipendenza fra task

`evaluation_runner.py:74-76` lo ammette già: lo stesso task compare in più righe,
quindi le righe non sono prove indipendenti. Il bootstrap su cluster lo corregge
per una singola accuratezza; il confronto fra sistemi resta McNemar.

**Verifica.**

    from collections import Counter
    counts = Counter(r['task_id'] for r in rows if r.get('task_id'))
    multi = {k:v for k,v in counts.items() if v > 1}
    if multi: dipendenza intra-task

La McNemar standard assume una coppia per task. Se un task ha `m > 1` repliche,
o si riduce a una coppia con regola pre-definita (si sceglie prima del run), oppure
si usa McNemar clusterizzato. CasualWatt raccomando: McNemar standard sulle
coppie ridotte + bootstrap per task come controllo; clusterizzato solo se >20%
dei task ha repliche multiple.

## 7. Correzioni multiple

| | Bonferroni | FDR (BH) |
|---|---|---|
| Controlla | FWER | FDR |
| Soglia | α/k | α·rank/k |
| Quando | k ≤ 5, falso positivo costoso | k ≥ 10, esplorazione |

Bonferroni: confronti pianificati. FDR: analisi esplorative. Si dichiara k e il
metodo prima del run; non aggiungere confronti dopo aver visto i risultati.

## 8. Specifica definitiva

- Test primario (sempre): p-value = 2 · P(X ≤ min(b,c)), X ~ Binom(b+c,0.5).
- Se b+c ≥ 10: χ² = (|b−c|−1)²/(b+c), df=1.
- Δ = (b−c)/n.
- CI su Δ con Newcombe.
- Casi limite: b+c=0 (indecidibile: da riportare); b+c<10 binomiale esatto;
  esclusi >10% cautela.
- Riferimenti: McNemar 1947, Newcombe 1998, `evaluation_runner.py:177-331`.

## 9. Implementazione in CasualWatt

La specifica è implementata in `paired_mcnemar`
(`cwEnergyModular/evaluation_runner.py:177-331`); il riepilogo del bootstrap a
cluster rimanda a quella funzione invece di dichiararla assente (la nota
"McNemar non implementato" è stata rimossa l'08-11-2026). La funzione restituisce:

- `n_total`, `n_determinate`, `n_excluded`, `excluded_by_reason`;
- `a`, `b`, `c`, `d`, `discordant`;
- `p_value_exact` (sempre), `chi2` e `p_value_chi2` (solo con `discordant >= 10`),
  `chi2_correction` (il flag chiesto) e `correction_applied` (`yes`, `no` oppure
  `not_applicable` quando il test è quello binomiale esatto);
- `delta_acc = (b-c)/n` e `delta_ci_newcombe` (metodo 10 con phi corretto, `None`
  se non calcolabile);
- `indecis` e `note`.
- Input: liste di esiti (0/1 o derivati via `record_verdict`) appaiate per
  posizione, già ridotte a una coppia per task (vedi §6).

La riduzione non è lasciata al chiamante: `paired_summary` (stesso modulo,
subito dopo `paired_mcnemar`) prende le due serie allineate e le identità dei
task, tiene la prima riga di ogni task nell'ordine del file (`reduction="first"`,
l'unica ammessa e dichiarata nell'output) e riporta `n_tasks`,
`n_tasks_with_replicas` e `n_without_task`, così che il numero di righe scartate
dalla riduzione non resti implicito. Il percorso di report è
`tools/mcnemar_report.py`: legge un JSON di confronto, risolve i due verdetti con
un percorso puntato, stampa matrice, p esatto, chi², delta, intervallo di
Newcombe ed esclusi per ragione, e scrive JSON più `.txt` accanto all'input;
`--input` è obbligatorio perché un default che punta a un file dell'albero di
lavoro può leggere righe rigenerate, e `--source` permette di registrare la
provenienza quando le righe vengono estratte da un blob git.

Sul confronto MUDILAB del 03-11-2026 (commit `303051dd9`, 321 run), la prima
esecuzione dell'08-11-2026 dà: 161 task (80 con repliche), una coppia per task,
matrice `a=50 b=7 c=0 d=104`, nessuna coppia esclusa, p esatto `0,015625`,
`delta_acc = 0,043478`, intervallo di Newcombe `[0,009472; 0,078023]`. Sette
task su 161 in cui il criterio pubblicato è corretto e il ramo `passi` no, zero
nel verso opposto: il ramo perde, e l'intervallo esclude lo zero. Il report è
`MUDILAB_run/harness/risultati/mcnemar_confronto_valutatori_20261103.json`.
La copia con lo stesso nome di base nell'albero di lavoro, rigenerata il
07-11-2026, non era una misura di quel giorno ma una ri-valutazione delle righe
del 03-11 con i campi nuovi di `mudilab_adapter.py` (`tolerance_provenance` dal
`98ec5972` del 04-11, adozione e argomenti del tool dal `6fc13d013` del 05-11).
L'08-11-2026 il file tracciato è stato ripristinato al blob di `303051dd9`
(hash verificato) e la ri-valutazione è stata rifatta come artefatto separato,
`harness/risultati/confronto_valutatori_20261103_rivalutato_20261108.{json,txt}`,
con il driver `MUDILAB_run/rivalutazione_confronto_20261108.py` e la nota
`experiment_results/rivalutazione_confronto_mudilab_20261108.md`. Su quello il
confronto appaiato è **indeciso**: 161 task, 48 coppie determinate tutte
concordanti (`a=0 b=0 c=0 d=48`), 113 escluse per indeterminazione (70,2%), p
esatto 1,0, delta 0, Newcombe `[-0,0741; 0,0741]`. Questo report continua a
leggere l'artefatto del 03-11, l'unico dei due in cui i due criteri producono
coppie discordanti.

Il test `tests/test_paired_mcnemar.py` copre i casi limite (b+c=0, b+c<10,
correzione di continuità, indeterminate, task con copertura parziale) e fissa
l'esempio di riferimento del metodo 10 e la dipendenza dell'intervallo
dall'appaiamento.
