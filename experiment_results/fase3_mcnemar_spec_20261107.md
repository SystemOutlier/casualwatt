# Fase 3 — relazione metodologica McNemar per CasualWatt

Data: 2026-11-07. Stato: specifica proposta e implementata a livello di
modulo (`pairedd_mcnemar` in `cwEnergyModular/evaluation_runner.py`),
con test `cwEnergyModular/tests/test_paired_mcnemar.py`. Nessuna riga del
percorso di misura modificata. La scelta di portare il test fuori dal report
del valutatore e' annunciata in `evaluation_runner.py:79-80`.

## 1. Avviso di presenza

`RobustEvaluator` e il report a livello di task usano Wilson che assume
indipendenza e bootstrap su cluster. Un confronto fra due sistemi **sullo
stesso task** non si fa per sovrapposizione di intervalli: resta una McNemar
appaiata. Questa e' oggi la lacuna della suite di valutazione.

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
- Casi limite: b+c=0 (non indecidibile: da reporter); b+c<10 binomiale esatto;
  esclusi >10% cautela.
- Riferimenti: McNemar 1947, Newcombe 1998, `evaluation_runner.py:67-131`.

## 9. Implementazione in CasualWatt

Il modulo `evaluation_runner.py` ha stanza a `cluster_bootstrap_interval`, che
oggi dichiara esplicitamente "McNemar non implementato". La specifica si traduce
in:

- `pairedd_mcnemar(pairs_a, pairs_b, correction)` -> dict:
   - n_determinate, n_excluded;
   - a, b, c, d, discordant;
   - p_value_exact, p_value_chi2 (se aplicabile);
   - delta, delta_ci (Newcombe);
   - note.
- Input: liste di esiti (0/1 o derivati via `record_verdict`) appaiati per task,
   già ridotte a una coppia per task (vedi §6).

Il test `tests/test_paired_mcnemar.py` documenta i casi limite (b+c=0,
b+c<10, correzione di continuita', indeterminate, task con copertura parziale).
