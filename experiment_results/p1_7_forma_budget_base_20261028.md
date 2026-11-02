# P1.7 / P2.9 — quadratura o somma aritmetica di `budget_base_w`

Data: 2026-10-28. **Stato: decisione ancora aperta, nessuna formula cambiata,
nessun run eseguito.** Questo file separa cio' che il pilota puo' decidere da
cio' che richiede una motivazione teorica, e propone le regole di decisione da
preregistrare. Non sceglie la forma.

Fonti: P1.7 `:317-370`, P1.13 `:516-523`, F.11 `:1719-1723`, P6.4 `:2447-2449`,
e la riga P4 della tabella di stato (`:14`, nona emenda) per il materiale GUM.

## 1. Cosa e' congelato

```
half_range_pre_w = (max(P_rep) − min(P_rep)) / 2
half_drift_w     = |dP| / 2
budget_base_w    = sqrt(half_range_pre_w² + half_drift_w²)
```

La quadratura **e' la formula operativa** e non si tocca in questo turno. Il
protocollo dichiara pero' tre cose che vanno tenute insieme (P1.7 `:335-343`):

1. non e' un limite conservativo garantito: per due termini non negativi
   `sqrt(a²+b²)/(a+b)` sta fra `1/√2` e `1`, quindi la somma aritmetica e' fra
   1,000 e 1,414 volte la quadratura, qualunque siano i valori;
2. l'unico termine oggi ancorato ai dati e' `half_drift_w ≈ 0,23 W`
   (`|dP| = 0,461 W` nel run v3); `half_range_pre_w` **non e' mai stato
   misurato**, perche' i run v3 usavano finestre da 10 s e non hanno terne;
3. la scelta dipende da **che cosa il budget rappresenta**, non da quanto e'
   grande (`:350-357`).

Il rinvio ha due vincoli (`:359-370`): va chiuso **prima** della campagna
principale, perche' `budget_base_w` entra nei pesi `w_b = 1/budget_fit_b²`
(F.9), nel bootstrap `z_b` (F.14) e nella soglia del gate di P4.5; e non
sospende nessuna soglia di P1.6. P1.13 `:521-523` lo dice con una frase che va
citata per intero: "Non e' aperta la formula, che resta congelata e si applica:
e' aperta la sua interpretazione".

## 2. Il dato che manca, e chi lo produce

`half_range_pre_w` esce dalle tre repliche pre da 30 s di ogni blocco (P1.5,
P6.2 `:2376-2382`) e il runner lo calcola gia' (`benchmark_v4.py:685-759`). Il
pilota di P2.9 lo produce **solo se** gira con il runner e con le finestre a
30 s: e' il motivo per cui P6.2 esiste (P6.2 `:2364-2374`) e per cui
l'ambiente di 2.9 di `p6_preparazione_pilota_20261028.md` va dichiarato.

Cio' che il pilota aggiunge rispetto a oggi e' quindi una **distribuzione** di
`half_range_pre_w` su blocchi reali, e con essa il rapporto

```
q_b = half_drift_w,b / half_range_pre_w,b
f_b = sqrt(1 + q_b²) / (1 + q_b)          # quadratura / somma, per blocco
```

`f_b` e' l'unica quantita' che il dato puo' fornire: il fattore di divergenza
fra le due forme **su quel blocco**. Non e' una preferenza fra le due forme, e'
la misura di quanto la scelta pesa.

## 3. Cosa il pilota puo' decidere

Tre cose, tutte descrittive e anterograde rispetto alla decisione:

1. **La rilevanza numerica.** `f_b` per blocco; se su tutti i blocchi `f_b` e'
   vicino a 1, le due forme danno lo stesso numero e la scelta e' ininfluente
   per il gate e per i pesi. Se qualche blocco ha `q_b` vicino a 1, la
   divergenza si avvicina a `1/√2` e la scelta cambia il numero pubblicato.
2. **La direzione sul gate.** La somma aritmetica e' sempre `>=` della
   quadratura, quindi il confronto `|E_net,control,c| <= budget_base_j,c` di
   P4.5 `:1553-1556` diventa **piu' facile** da superare, fino al 41,4%. La
   direzione e' analitica, non statistica: non dipende dai dati, e per questo
   la si puo' scrivere prima.
3. **La posizione su una curva gia' misurata.** L'effetto sui pesi non e'
   monotono in `rho = u_base/u_within`: l'incrocio e' fra 0,20 e 0,25, sotto la
   somma aritmetica concentra di meno (0,85 a 0,05), sopra di piu' (1,40 a 1,00)
   — `semi_range_concentrazione_pesi_probe.py`, 25-10, citato da P1.7 `:366-368`.
   Con `u_within,b` misurato dal pilota (P6.2 `:2379-2381`) il `rho` di questa
   macchina si colloca su quella curva. Il pilota **non** sposta la curva.

## 4. Cosa il pilota non puo' decidere

**Quale delle due forme sia corretta.** P1.7 `:350-357` lo scrive: i termini
sono semi-range osservati, e "nessuna delle due forme diventa corretta per il
solo fatto di essere applicata a questi valori". Con `n = 3` non si stima una
varianza (P4.12), quindi la quadratura non puo' essere giustificata **dai
dati** come combinazione di incertezze standard: l'ipotesi di indipendenza o
ortogonalita' che la renderebbe lecita non e' verificabile su tre repliche. La
formulazione GUM di quell'ipotesi e' registrata come materiale per questa
decisione dalla nona emenda (`:14`, riga P4): e' un argomento, non un test.

Ne segue che il pilota **quantifica** e non **arbitra**. Un documento che
scegliesse la forma in base a quale produce `f_b` piu' favorevole starebbe
usando i dati come pretesto per una convenzione, che e' esattamente cio' che
P1.7 `:369` vieta ("cambiarlo dopo aver visto i risultati sarebbe spostare una
soglia dopo i dati").

## 5. Regole di decisione da preregistrare

Una sola va scelta e scritta prima del pilota; il codice resta sulla quadratura
finche' la scelta non e' registrata. Le tre opzioni, con la conseguenza
dichiarata:

**D1 — tenere la quadratura e dichiararne il significato.** Il budget si
dichiara *proxy di incertezza standard*, non limite; la somma aritmetica si
riporta come **sensibilita'** per blocco con il fattore `f_b`. Nessun numero
congelato cambia; resta l'onere di scrivere che l'ipotesi di ortogonalita' non
e' verificata.

**D2 — passare alla somma aritmetica.** Il budget si dichiara *limite*, senza
compensazione. Conseguenze da ricalcolare e documentare prima della campagna:
soglia del gate piu' larga (fino a +41,4%), pesi `w_b` spostati secondo la
curva di `rho`, `budget_pred` che segue (`F.11` `:1719-1723`: la forma esterna
di `budget_pred` "resta provvisoria insieme a quella di `budget_base_w`" e le
due decisioni "vanno chiuse insieme"). Non e' una modifica locale.

**D3 — decidere sulla rilevanza, con soglia preregistrata.** Si dichiara prima
che se `f_b` sta sopra un valore `f*` (cioe' le due forme divergono poco) si
tiene la quadratura con la nota di D1, e sotto `f*` la scelta passa alla
motivazione teorica. Il valore `f*` va scritto prima di vedere i dati e non e'
una soglia del protocollo: e' la regola che rende la decisione non post-hoc.
Senza `f*` dichiarato, D3 e' indistinguibile da "scelgo dopo".

## 6. Cosa non si fa qui

- Non si cambia la formula: il codice resta in quadratura
  (`benchmark_v4.py:700-716`, che documenta il rinvio).
- Non si sposta `f*` ne' alcuna soglia di P1.6 dopo aver visto `half_range_pre_w`.
- Non si decide sulla sola forma di `budget_base_w` ignorando `budget_pred`.
- Non si presenta il pilota come arbitro: e' un fornitore di `f_b` e di `rho`.
- Non si scrive "limite superiore garantito" per la quadratura.

## 7. Ancore

- P1.7: `:317-370` (formule, stato della forma, decisione rinviata, vincoli);
  P1.13: `:516-523` (cosa e' aperto e cosa no).
- F.11: `:1719-1723` (la forma esterna di `budget_pred` segue la stessa sorte).
- P6.2: `:2376-2382` (il pilota produce `half_range_pre_w` e `u_within,b`).
- P6.4: `:2447-2449` (le tre grandezze mosse dalla scelta).
- Codice: `benchmark_v4.py:685-759` (`block_baseline`, quadratura e docstring
  del rinvio); `validation_chain.py:187`, `:191-193` (il gate di P4.5 legge
  `budget_base_j` e `budget_base_w` dalle righe di controllo).
- Prova gia' tracciata sulla concentrazione dei pesi:
  `semi_range_concentrazione_pesi_probe.py` (misura simulata, non un run).
