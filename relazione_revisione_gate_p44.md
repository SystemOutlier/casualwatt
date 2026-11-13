# Relazione sulla revisione del gate P4.4

## 1. Obiettivo

Il gate P4.4 ha lo scopo di verificare se il carico introduce un residuo
di potenza o energia compatibile con il fondo misurato della macchina.
Il criterio F.12 confronta il bias aggregato con la mediana dei budget
di fondo, senza essere un test di significatività statistica.

## 2. Esito delle campagne

Le prime due campagne hanno entrambe prodotto esito fail:

| grandezza | prima campagna | seconda campagna |
|---|---:|---:|
| verdetto F.12 | fail | fail |
| bias_w | 0,479571 W | 0,125171 W |
| soglia | 0,262324 W | 0,117995 W |
| scarto | +82,8% | +6,1% |
| controlli utilizzabili | 4/6 | 6/6 |
| ambiente | rumoroso | quieto |

La seconda campagna conferma che la precondizione di quiete ha ridotto
fortemente il bias, ma la soglia si è stretta ancora di più, perché
una macchina quieta produce budget più piccoli.

## 3. Diagnosi tecnica

Il fallimento residuo non è attribuibile al rumore di fondo. Il primo
controllo dopo il primo carico, ctrl-1, contribuisce al 75,3% del
numeratore del bias. Tuttavia, anche escludendolo ipoteticamente, il
bias residuo sarebbe 0,037104 W contro una mediana di 0,033178 W:
quindi il fail non dipende da un solo outlier.

Il problema strutturale è la scala temporale: il budget è stimato su
finestre da 30 s, mentre la finestra di controllo dura 2,930748 s.
Il confronto fra queste due scale non è metodologicamente coerente.

## 4. Revisione proposta

La soglia va riformulata come:

S = B_matched + k * u_c

dove:

- B_matched è il budget stimato sulla stessa scala temporale del controllo;
- u_c è l'incertezza combinata della misura;
- k è il fattore di copertura, pre-registrato, con default k = 2.

La nuova soglia non è un allargamento arbitrario: rende esplicito che
la tolleranza deve coprire sia il fondo naturale sia l'incertezza
della procedura di misura.

## 5. Componenti dell'incertezza

| componente | tipo | metodo |
|---|---|---|
| dispersione fra controlli | A | deviazione standard |
| rumore elettrico | A | dispersione delle baseline |
| risoluzione del contatore | B | specifiche hardware |
| transitorio termico | B | warm-up e margine dichiarato |
| allineamento temporale | B | sincronizzazione delle finestre |

La regola proposta è:

bias_w <= mediana_c(B_{w,c}^{Tc}) + 2 * u_c

## 6. Warm-up

Dopo ogni carico va inserita una fase di stabilizzazione non conteggiata
come controllo. Questo evita che il primo controllo post-carico, ctrl-1,
domini il bias aggregato.

Il warm-up deve essere:

- pre-registrato;
- di durata fissa;
- non usato come controllo;
- registrato con un flag di completamento.

## 7. CodeCarbon

CodeCarbon può essere integrato come strumento diagnostico, non come
criterio decisionale. Deve misurare o stimare CPU, GPU e RAM, salvare
CSV/JSON separati e non alterare bias_w, budget_base_w, E_net, dt_W
o il verdetto F.12.

## 8. Riferimenti

- JCGM 100:2008, Guide to the expression of uncertainty in measurement: base per incertezza combinata e propagazione.
- NIST Special Publication 260-202, Evaluating, Expressing, and Propagating Uncertainty: definizione di incertezza standard e combinata.
- NIST Handbook 152, Type A and Type B uncertainty: distinzione fra incertezza Type A e Type B.
- SPECpower_ssj2008 Methodology: warm-up, stabilità, incertezza e condizioni ambientali.
- SPEC Run & Reporting Rules: requisiti di accuratezza e temperatura.
- Hähnlein et al., methodology for power modeling in energy benchmarking: idle/load, gestione termica, ripetizioni.
- Energy-Efficiency Sweet Spots: esclusione dei transitori e media solo in steady state.
- CodeCarbon documentation, power estimation and configuration: misurazione/stima di CPU, GPU, RAM e configurazione del campionamento.

## 9. Conclusione

La revisione del gate non consiste nell'alzare la soglia, ma nel
rendere coerente la definizione del measurand, del budget e
dell'incertezza. La terza campagna deve essere condotta solo dopo
l'adozione formale della Quindicesima emenda e del nuovo piano.