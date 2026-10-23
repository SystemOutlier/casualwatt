# Audit del benchmark pubblicato (run `R20261019-164316-74070d`)

Analisi di `cwEnergyModular/results/semantic_evaluation_results.csv` — le 9 righe
che oggi sono l'unico output della pipeline di produzione, e che la tesi usa come
"frontiera di Pareto accuratezza-energia". Riproducibile con:

```
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe audit_benchmark_pubblicato.py
```

Output: `experiment_results/benchmark_prodotto_20261019_audit.json` (+ stdout nel
`.txt` accanto). Lo script non riscrive nessuna metrica: calcola cosa e'
effettivamente calcolabile dai campi pubblicati e marca `None` cio' che non lo e'.

## 0. Il dataset in sei numeri

| cosa | valore |
|---|---|
| righe | 9 (3 modelli x 3 item) |
| `run_id` distinti | **1** — `R20261019-164316-74070d`, finestra 14:43:16 -> 14:44:17 UTC (61 s) |
| ripetizioni per cella modello-item | 1 esecuzione, zero ripetizioni |
| `active_energy_j` > 0 | **2 / 9** |
| righe tenute dal filtro di `genera_grafici_tesi.py:79` (`end_to_end_energy_j > 0`) | **2** (il file generato lo dichiara: "Numero di righe valide analizzate: 2", "Modelli cloud: 0") |
| `provider` | `ollama` in 9/9; `cloud_energy_j`, `network_total_bytes`, `gpu_available` tutti nulli/falsi in 9/9 |

Con una ripetizione per cella non esiste alcuna statistica aggregata da produrre:
mediana e CV di "E, J/token, J/risposta corretta, tok/s, durata per modello" — la
tabella che lo scheletro di sezione chiedeva — hanno `n = 3` per modello e `n = 1`
per item. La tabella per-modello della tesi riporta quindi i singoli valori, non
aggregati.

## 1. Perche' le 2 righe "valide" non sono una misura di energia

Le uniche 4 righe con `package_energy_j > 0` danno, dividendo per `duration_s`:

| modello | item | `package_energy_j` [J] | `duration_s` [s] | potenza implicita [W] | dentro PL1/PL2? |
|---|---|---|---|---|---|
| llama3.2:3b-q4_K_M | man-001 | 1572,818 | 12,577 | **125,06** | no (> PL2 55) |
| llama3.2:3b-q4_K_M | man-002 | 915,388 | 13,542 | **67,60** | no |
| llama3.2:3b-q4_K_M | man-003 | 127,192 | 1,870 | **68,01** | no |
| nemotron-mini | man-001 | 231,536 | 12,222 | 18,94 | si' |

Involucro OEM della macchina: PL1 35 W / PL2 55 W (`hwinfo_idle_20261023_011237.csv`,
riportato in `lhm_gui_report_20261023_analisi.md:63`). Tre potenze implicite su
quattro sono **fisicamente impossibili** per il package: sono il canale
`power-integration` che integrava la temperatura come fosse joule — lo stesso
difetto arbitrato in `energy_session.py:819` e corretto in `1422d1b`, e questo run
e' del 19/10, cioe' **anteriore al fix**.

Le 2 righe sopravvissute al filtro sono quindi il residuo di due quantita'
contaminate. Su man-002 (llama): `package_energy_j` 915,388 J impliano 67,6 W e
`baseline_energy_j` 887,744 J impliano 65,6 W; la differenza e' 27,64 J, **il 3%
del sottraendo**. Con il canale pulito dello stesso chip, la
potenza incrementale del protocollo A-B-A vale 16,78 W
(`lhm_validation_v3_20261023_153604.csv`, `P_load - P_base`) e su 13,54 s di
richiesta attende ~227 J: il J/token pubblicato (0,1153) e' **12,3 volte** sotto
l'ordine di grandezza atteso, quello di man-003 (0,0963) 15,5 volte.
Non e' una proprieta' del modello: e' un resto di sottrazione.

Le 5 righe a `package_energy_j = 0.0` non dicono "energia zero": dicono
`package_window_source = unavailable` con "nessun campione package nella finestra"
nei `notes` — compresa una finestra da 5,74 s, dove il campionamento dichiarato
(0,5 s) avrebbe dovuto dare ~11 campioni.

## 2. Il verdetto di correttezza non arriva dal ground truth

Stato dichiarato dai campi, in tutte e 9 le righe:

- `eval_mode = ground_truth` ma `eval_method = none`;
- `cosine_similarity` == `causal_accuracy` == `acc_comp` (a 4 decimali) in 9/9;
  i `notes` la spiegano: `acc_links` cade sul proxy semantico
  (`basis = semantic_fallback`), la componente judge e' assente, i pesi del
  regime A (0,5/0,3/0,2) si rinormalizzano sul solo cosine;
- `is_correct` == (`cosine_similarity >= semantic_threshold`) in **9/9**
  (soglia 0,75 unica);
- `epcl_j_per_link` vuoto in 9/9: la metrica sui link causali non ha mai prodotto
  un valore.

Quindi l'accuratezza composita di questo dataset **e' un solo numero**, e il
verdetto binario e' una soglia su quel numero. Confrontandolo con le risposte
reali (etichetta letta a mano in `audit_benchmark_pubblicato.py`, campo `REALE`):

| item | GT | risposta | reale | cosine | verdetto |
|---|---|---|---|---|---|
| man-001 | 21 | llama: "25 - 4 = 21 ... la risposta e': 21" | **Vera** | 0,3544 | **False** |
| man-001 | 21 | nemotron: "5 * 4 = 20 ... the answer is 20" | Falsa | 0,2735 | False |
| man-001 | 21 | tinyllama: "5*5-4 = 10*10 = 100 ... = 1" | Falsa | 0,3308 | False |
| man-002 | Adolf | llama (160 tok, contiene "Adolf Hitler") | Vera | 0,6168 | False |
| man-002 | Adolf | nemotron: "Il nome di Hitler e' Adolf Hitler." | Vera | 0,6409 | False |
| man-002 | Adolf | tinyllama: 'Il nome di Adolf Hitler e' "Adolf Hitler".' | Vera | 0,6430 | False |
| man-003 | Atene | tutte e tre (una in inglese: "Athens") | Vera | 0,777-0,793 | True |

7 risposte su 9 sono realmente corrette; il validatore ne approva 3.
**precisione 1,00, recall 0,43, accordo 6/9.** Per modello: llama 3/3 reali vs
1/3 di verdetto, nemotron 2/3 vs 1/3, tinyllama 2/3 vs 1/3 — cioe' il verdetto
binario non distingue i modelli (tutti 1/3) mentre la realta' li ordina.

La causa e' dimensionale, non casuale: dentro `man-001` la distanza di cosine fra
la risposta corretta e la migliore fra le errate vale **0,0235**; lo stesso
modello, passando da `man-001` a `man-003`, si sposta di **0,4279**. L'item (e la
sua ground truth da 2-5 caratteri) sposta il punteggio ~18 volte piu' di quanto
faccia la correttezza della risposta, e la soglia 0,75 taglia dentro la bande
degli item, non dentro quella della correttezza.

Conseguenza per le metriche di efficienza: `energy_per_correct_answer_j` e'
definita in `benchmark_unified.py:516-527` come `end_to_end` quando `is_correct`,
altrimenti non definita. Nel dataset vale 2,02287 J una sola volta e **0,0 due
volte**: dove la misura locale e' indisponibile e il verdetto e' positivo, la
metrica "Joule per risposta corretta" (lower is better) riporta il suo valore
migliore possibile. Non e' un bug di codice — il codice divide esattamente cio'
che ha ricevuto — e' un buco di semantica: la metrica non ha uno stato
"sconosciuto", e il filtro `end_to_end_energy_j > 0` scarta proprio le righe che
lo mostrerebbero.

## 3. Cio' che il dataset dice davvero (e non e' energia)

- **Throughput di decodifica** (`decoding_tokens_per_second`, esposto dall'API
  Ollama, non misurato da CasualWatt): llama 12,05-13,59 (mediana 12,24),
  nemotron 11,06-12,83 (12,16), tinyllama 42,94-45,46 (43,28). Escursione entro
  lo stesso modello: 1,5-2,5 tok/s su tre righe. E' il numero piu' ripetibile del
  dataset, e non proviene dal canale di misura.
- **Il prompt utente non fissa `N_in`**: a parita' di item i token di input sono
  18/35/44 (man-001), 14/31/40 (man-002), 14/33/40 (man-003) — 26 token fra il
  minimo e il massimo dello stesso stimolo, cioe' il template di chat del modello
  cambia il denominatore di J/token piu' di quanto faccia la risposta. Il
  confronto fra modelli a questa geometria non e' a confronto.
- **Rapporto costo per token decode/prefill**: 5,00-11,17, mediana **6,40** (non
  8,4 — corretto in `cap05`, sezione geometria).
- **Tempo fuori dalle due fasi**: 6,64 s, 6,00 s, 1,87 s; negli altri sei casi
  0,03-0,12 s. Le tre righe col residuo maggiore sono le `man-001`, e i timestamp
  le mostrano come **prima richiesta eseguita di ogni modello** (le 9 query sono
  sequenziali, 14:43:16 -> 14:44:17). E' caricamento del modello, e `keep_alive`
  al 19/10 non era ne' fissato ne' registrato — lo diventa in `0be92f8`.

## 4. Carbonio: un solo fattore, e mai quello live

`local_carbon_intensity_gco2eq_kwh = 267,0`, `zone = IT`,
`source = offline-default-table-2024` in **9/9**. Il percorso API esiste nel
codice (`energy/carbon_intensity.py:28,87`, `ELECTRICITYMAPS_API_URL`, source
`electricity-maps-api`) ma non e' stato usato: lo prova il campo `source`. Le
emissioni sono la conversione esatta dell'energia (`J/3,6e6 * CI`): 1,368 mg e
0,150 mg sulle due righe con energia, 0,0 g sulle altre sette (stesso clamp di
sezione 1). La sensibilita' alla zona, sulla stessa tabella offline del codice
(FR 55 / IT 267 / DE 396), e' **x7,2** fra il minimo e il massimo: a 1,2862
J/token una risposta da 1000 token vale 0,0196 g (FR), 0,0954 g (IT), 0,1415 g
(DE) con la stessa identica misura elettrica.

Nessun campo di costo monetario esiste nella repo (grep `EUR|price|cost_eur`:
zero risultati nel codice) — la voce "costo per query in EUR" dello scheletro
di sezione non ha implementazione da riportare, e va messa fra gli sviluppi.

## 5. Cosa ne segue per la tesi

1. `sec:risultati-efficienza` riporta i J/token dei protocolli A-B-A e dei test
   EMI (canale pulito) come risultato, e usa le 9 righe come **risultato
   negativo documentato**: le due righe valide non sono una misura.
2. La frontiera di Pareto (fig. `01_pareto_accuracy_vs_energy.png`) entra in tesi
   come figura del risultato negativo, con la sua didascalia che dichiara 2 punti.
3. `sec:risultati-local-cloud` dichiara che il confronto asimmetrico e'
   implementato (`energy/cloud_energy.py:115-184`) ma mai esercitato: 0 righe
   cloud, e la fig. `02_boxplot_accuracy_per_provider.png` e' un boxplot di 2
   punti di un solo provider.
4. `sec:risultati-co2` riporta la conversione e la sensibilita' a zona, dichiara
   l'assenza del percorso API e del costo in EUR.
5. Il materiale di sezione 2 (verdetto vs realta', recall 0,43, soglia che taglia
   gli item) e' evidenza centrale per RQ4 e per la discussione del validatore.
