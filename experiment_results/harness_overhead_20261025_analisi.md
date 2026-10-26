# Overhead dell'harness di telemetria: A-B-A con EMI come riferimento

**Data**: 2026-10-25, run dalle 15:35:01 alle 15:43:37 UTC (515,1 s)
**Script**: `harness_overhead_probe.py` (nuovo, committato qui insieme ai dati);
usa `monitor_ollama.py` al commit `b1f3ab1` (keep_alive numerico)
**Dati**: `harness_overhead_20261025_{probe,windows}.csv`,
`harness_overhead_20261025_summary.json`,
`harness_overhead_20261025_requests_probe_c{1,2,3}_a{1,2}.csv`,
`harness_overhead_20261025_{telemetry,requests,meta}_b{1,2,3}.csv/json`

## Domanda

`monitor_ollama.py` aggiunge al carico di una richiesta Ollama un sampler EMI
(o LHM) a 0,5 s, una scansione `psutil` di tutti i processi a ogni giro, la
tabella delle richieste e i thread che le coordinano. Serve sapere se questo
osservatore **sposta la misura**: quanto pesa sul package, e in quale
direzione.

La domanda e' distinta da quella del 23/10 (`observer_cost_20261023_analisi.md`),
che riguardava la **GUI di LibreHardwareMonitor** aperta accanto al profiler.
Qui l'osservatore e' il nostro harness di telemetria; la GUI e' chiusa.

## Metodo

Disegno dichiarato **prima dei dati** nella docstring dello script:

- **riferimento comune**: una sonda EMI a 100 ms legge il PKG in *tutte* le
  fasi. Le potenze di finestra sono gli incrementi del contatore interamente
  contenuti in `[t_send, t_end]` di ciascuna richiesta; gli incrementi a
  cavallo dei bordi sono esclusi e contati, i negativi si conservano
  (`contained_metrics`, `harness_overhead_probe.py:138`);
- **A**: 4 richieste pilotate dal processo della sonda (driver minimo, stesso
  prompt, stesse opzioni, stesso `keep_alive`);
- **B**: le stesse 4 richieste pilotate da `monitor_ollama.py` in un processo
  figlio (`run_harness`, `:388`), con `--interval 0.5`, `--tail 2`;
- **3 cicli A1-B-A2** intervallati da 6 s, 2 s di coda dopo B;
- **2 warm-up** scartati, stesso prompt e `keep_alive = -1` numerico;
- **baseline**: 3 finestre da 30 s prima e 3 dopo, con settling P1.5 (media
  mobile a 10 s stabile entro 0,5 W, tetto 120 s), mediana e drift
  (`baseline_windows`, `:208`); i valori grezzi delle sei finestre sono nel
  riepilogo JSON;
- **criterio pre-dichiarato**: il delta e' "non distinguibile dal drift" solo se
  in **ogni** ciclo `|B - media(A1,A2)| <= |A2 - A1|` **e** `< 1,0 W`
  (`SCALE_W`, `:66`; verdetto a `:601-615`).

A non e' "nessun osservatore": contiene la sonda EMI e il driver delle
richieste. Il delta B-A misura quindi il costo **incrementale** di
`monitor_ollama.py` rispetto a un driver minimo, non il costo assoluto
dell'osservazione. Il costo assoluto rispetto a "nessuna lettura" non e'
misurabile senza un wattmetro esterno.

## Numeri

### Baseline e drift

| finestra | P [W] | incrementi EMI | tempo scoperto |
|---|---|---|---|
| pre1 | 15,218 | 299 | 92,6 ms |
| pre2 | 14,361 | 299 | 93,6 ms |
| pre3 | 13,785 | 299 | 97,6 ms |
| post1 | 13,417 | 299 | 105,5 ms |
| post2 | 13,133 | 298 | 196,3 ms |
| post3 | 14,067 | 300 | 6,4 ms |

```
baseline_pre_w    = 14,3609 W   range 1,4328 W   (13,785-15,218)
baseline_post_w   = 13,4171 W   range 0,9347 W   (13,133-14,067)
baseline_drift_w  = -0,9438 W
settle_pre  35,0 s, ultimo passo 15,7792 -> 15,7610 W (0,018 W)
settle_post 35,0 s, ultimo passo 13,4622 -> 13,0404 W (0,422 W)
```

Il range pre **supera 1,0 W**: con la regola P1.6 la baseline sarebbe marcata
`pre_unstable`. La macchina aveva housekeeping di Windows in corso; il livello
scende di quasi 1 W in otto minuti. Non e' una baseline "stabile", e' una
baseline **dichiarata con il suo drift**.

### Potenza di finestra, per ciclo

| ciclo | A1 [W] | B [W] | A2 [W] | B - media(A1,A2) | A2 - A1 |
|---|---|---|---|---|---|
| 1 | 28,4618 | 27,5247 | 27,6490 | **-0,5307** | -0,8128 |
| 2 | 28,6990 | 27,0998 | 28,2615 | **-1,3805** | -0,4375 |
| 3 | 28,6437 | 27,8331 | 27,9858 | **-0,4816** | -0,6579 |
| pooled | 28,2835 (n=24) | 27,4859 (n=12) | | **-0,7976** | |

Il delta e' negativo in **3 cicli su 3**. Il criterio pre-dichiarato **non e'
soddisfatto**: al ciclo 2 `|delta| = 1,3805 W` supera sia la scala di 1,0 W sia
il drift del ciclo (0,4375 W). Il verdetto dello script e' quindi "riportare
l'intervallo, non una stima puntuale": intervallo osservato **-1,38 / -0,48 W**,
valore pooled -0,80 W.

### Durata, energia e token per richiesta

| ciclo | finestra A1 / B / A2 [s] | B - media [s] | E/richiesta A1 / B / A2 [J] | B - media [J] | J/token B - media |
|---|---|---|---|---|---|
| 1 | 2,924 / 3,257 / 3,164 | +0,213 | 79,67 / 86,57 / 85,62 | +3,92 | +0,0613 |
| 2 | 3,086 / 3,191 / 2,969 | +0,164 | 85,29 / 83,90 / 80,37 | +1,07 | +0,0167 |
| 3 | 2,902 / 3,137 / 2,957 | +0,207 | 81,56 / 84,74 / 81,08 | +3,41 | +0,0533 |
| media | 2,971 / 3,195 / 3,030 | **+0,195 (+6,5%)** | 82,18 / 85,07 / 82,36 | **+2,80 (+3,4%)** | **+0,0438** |

Tutte le 36 finestre hanno `status = ok`, `eval_count = 64`,
`done_reason = length`, HTTP 200; zero incrementi negativi, 72 incrementi a
cavallo (2 per finestra, esclusi). Il lavoro per richiesta e' identico: la
differenza non e' "piu' token".

### Costo proprio dell'osservatore

| ciclo B | righe telemetria | intervallo mediano | sweep mediano / massimo | duty sweep | CPU osservatore medio / massimo | CPU nella fase |
|---|---|---|---|---|---|---|
| 1 | 67 | 0,503 s | 0,049 / 0,133 s | 9,7% | 10,2% / 22,5% | 3,33 s |
| 2 | 66 | 0,503 s | 0,053 / 0,147 s | 10,4% | 11,7% / 25,7% | 3,79 s |
| 3 | 66 | 0,503 s | 0,047 / 0,119 s | 9,3% | 10,8% / 20,8% | 3,47 s |

Il processo della sonda EMI, attivo in tutte le fasi, ha consumato 1,609 s di
CPU su 515,1 s (**0,31% di un core**). La sonda ha scritto 5157 righe
(intervallo effettivo ~100 ms).

### Orologi

Offset misurato in questa sessione: **16,571367 s**, mediana su 5157 coppie,
escursione max-min 8,0 ms sull'intera finestra. La mattina del 25/10, nella
prova di associazione, era 16,571370 s: entro la stessa sessione l'offset e'
stabile a pochi microsecondi. Il 23/10 era 14,391844 s: **fra sessioni non si
assume**, si misura (come gia' concluso in `telemetry_association_20261025.md`).

## Cosa si puo' dire

1. **Nessun offset positivo di potenza, ma il criterio non passa.** In tutte e
   tre le fasi B la potenza media di finestra e' *inferiore* a quella delle
   fasi A, di 0,48-1,38 W. Non c'e' evidenza che l'harness scaldi il package.
   Il criterio pre-dichiarato resta pero' non soddisfatto (uscita di -1,38 W al
   ciclo 2): il risultato corretto e' l'intervallo, non "overhead nullo".
2. **Il segno negativo si spiega con la forma della finestra, non con un
   risparmio.** Le finestre B sono piu' lunghe del 6,5% (+0,195 s) con gli
   stessi 64 token, e l'energia per richiesta e' **piu' alta** di 2,8 J
   (+3,4%), in 3 cicli su 3 rispetto al punto medio. Potenza media piu' bassa e
   durata maggiore sono due viste dello stesso fatto: la stessa energia e'
   distribuita su piu' tempo; l'energia totale per richiesta sale.
3. **La grandezza che conta per J/token e' proprio quella che sale.** Il
   `j_per_token` misurato passa da 1,2854 (A) a 1,3292 (B), +0,0438 J/token
   (+3,4%). Non e' una stima puntuale robusta (n=12 finestre B), ma il segno e'
   concorde nei tre cicli.
4. **La scala di 1,0 W e la scala dell'energia sono confrontabili.** Una
   finestra di 3 s a 1,0 W vale 3 J: il +2,8 J per richiesta sta **dentro** la
   scala dichiarata, non sotto di essa. Per confrontare energie servirebbe una
   scala in joule per richiesta dichiarata prima dei dati; qui non c'era, e non
   la si introduce a posteriori.
5. **Meccanismo non stabilito.** Il duty della scansione `psutil` e' 9-10% di un
   core e la CPU dell'osservatore 3,3-3,8 s per fase. Sono compatibili con un
   rallentamento del runner per contesa (GIL del thread di lettura o
   backpressure sulla socket), ma con questi dati non si distingue la contesa
   dal normale jitter di scheduling. Nessuna attribuzione.
6. **Il livello assoluto resta non arbitrato.** La sonda EMI e' il riferimento
   comune: un accordo fra due letture dello stesso registro non e' una
   validazione indipendente, e qui non c'e' un wattmetro AC/DC esterno.

## Conseguenze operative

- Per i **livelli di potenza** l'harness non introduce un offset positivo
  rilevabile; per l'**energia per token** introduce un bias misurato di
  +0,044 J/token in questa configurazione. Se una campagna usa `monitor_ollama`
  accanto alle misure, quel bias va dichiarato, non corretto in silenzio.
- Il protocollo v4 non mette `monitor_ollama.py` nel percorso energetico: il
  risultato non tocca `MEASURED_METHODS` ne' la produzione. Dice pero' che la
  telemetria concorrente puo' **allungare la richiesta**, quindi non va
  attivata durante la campagna principale senza questa dichiarazione.
- La sonda a 100 ms e' la parte piu' economica dell'osservazione (0,31% di un
  core): il costo sta nella scansione dei processi, non nella lettura EMI.
- Se si vuole stringere il numero, il disegno giusto e' piu' cicli e piu'
  richieste per fase, oppure una variante B con la sola scansione `psutil`
  disattivata per separare le due componenti. Sono esperimenti da fare, non
  modifiche da adottare ora.

## Limiti

- A contiene la sonda e il driver delle richieste: il delta e' incrementale,
  non assoluto. Il "costo zero" richiede un riferimento esterno.
- Baseline `pre_unstable` secondo P1.6 (range 1,43 W > 1,0 W) e drift di
  -0,94 W sull'intera prova. Il disegno A-B-A compensa il livello, non
  un'eventuale deriva della *forma* delle richieste.
- Un solo modello (`llama3.2:1b`, Q8_0, 1,52 GB, `size_vram = 0` quindi
  inferenza su CPU), un solo prompt da 64 token, una sola ripetizione della
  prova. La finestra e' dominata dal decode: non si dice nulla sul prefill.
- Non sono stati registrati top-5 processi, piano energetico e stato batteria
  come chiede P1.4; la GUI di LibreHardwareMonitor era chiusa (`tasklist`
  prima del run) e non c'era altro monitoraggio noto.
- 12 finestre B e 24 A: con n cosi' piccolo il range osservato e' l'unico
  intervallo onesto.

## Riprodurre

Processo normale (la sonda EMI non richiede elevazione; LHM non e' usata):

```
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe -u \
    harness_overhead_probe.py --tag harness_overhead_20261025
```

Dry run rapido del solo impianto (usato per verificare il fix di `keep_alive`):

```
... python.exe -u harness_overhead_probe.py --tag overhead_dry3 --cycles 1 \
    --requests 2 --baseline-windows 1 --baseline-seconds 2 --settle-max-s 11 \
    --out-dir experiment_results/_dry
```

Lo script stampa il riepilogo prima del teardown; i file di dati sono elencati
in testa. I log (`*_console.log`, `*_harness_b*.log`) sono ignorati da git.
