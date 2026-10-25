# Costo della scansione psutil nell'harness di telemetria — A-B-C del 25/10/2026

Domanda: l'enumerazione dei processi con psutil che `monitor_ollama.py` esegue
ogni 0,5 s sposta l'energia per richiesta o la durata della richiesta, misurate
dal contatore EMI, durante le stesse richieste?

Risposta di questo run: **la manipolazione è verificata e grande in termini di
CPU, ma il suo effetto energetico non è risolto.** Il contrasto primario B−C
dà −2,54 J per richiesta con intervallo al 95% [−7,95, +2,87] e −0,062 s di
durata con [−0,278, +0,153]. L'intervallo attraversa la banda di soglia
preregistrata (±1,0 J, ±0,10 s): il verdetto è **non conclusivo**, non
"nessun effetto". La numerosità richiesta per una semi-ampiezza pari a metà
soglia supera il tetto preregistrato di 18 cicli; il pilota a 6 cicli è quindi
la prova definitiva di questo esperimento.

## 1. Disegno

Tre condizioni a parità di modello, prompt, opzioni, `keep_alive`, carico e
macchina:

| condizione | driver delle richieste | scansione dei processi |
|---|---|---|
| A | `harness_overhead_probe.py` | nessuna |
| B | `monitor_ollama.py` | `--process-scan full` |
| C | `monitor_ollama.py` | `--process-scan off` |

- B−C isola la scansione a driver costante.
- B−A è la differenza totale harness+driver.
- C−A è il residuo del driver e delle componenti fisse comuni a B e C,
  compresa l'interrogazione periodica di `/api/ps`.

Il riferimento EMI (sonda a 100 ms) è attivo in tutte le fasi; il suo costo è
dentro ogni condizione. I contrasti sono quindi **incrementali** e non misurano
il costo zero-osservatore, che richiederebbe un wattmetro esterno.

L'ordine dei sei cicli è l'insieme completo delle sequenze di Williams per tre
trattamenti — ABC, BCA, CAB, CBA, ACB, BAC — eseguito nell'ordine
`ABC BCA CAB CBA ACB BAC`. Ogni condizione occupa ogni posizione due volte e
segue ogni altra condizione due volte: posizione e carryover sono bilanciati
senza randomizzazione. La sequenza è generata da
[harness_overhead_probe.py:137](file:///C:/Users/Massimo/Documents/CasualWatt/CWProject/harness_overhead_probe.py#L137).

La modifica a `monitor_ollama.py` è isolata: solo il flag `--process-scan`, con
il ramo `off` che non chiama `psutil.process_iter` né in campionamento né nel
warm-up ([monitor_ollama.py:745](file:///C:/Users/Massimo/Documents/CasualWatt/CWProject/monitor_ollama.py#L745),
[monitor_ollama.py:823](file:///C:/Users/Massimo/Documents/CasualWatt/CWProject/monitor_ollama.py#L823)).
Nessuna modifica al backend energetico o al percorso di produzione. La
telemetria è `telemetry/3` e dichiara `process_scan` e `process_scan_s` per
riga. I sei test del flag sono in
`cwEnergyModular/tests/test_monitor_ollama_process_scan.py`.

Commit: `5fee656` (flag e test), `af122dc` (harness A-B-C). Il run è
`harness_overhead_abc_20261025`; i file di dati sono elencati in §11.

## 2. Criteri preregistrati

Congelati nel docstring e nel JSON di riepilogo prima dei dati
([harness_overhead_probe.py:106](file:///C:/Users/Massimo/Documents/CasualWatt/CWProject/harness_overhead_probe.py#L106),
campi `preregistration` del summary):

- **metriche primarie**: energia per richiesta (J) e durata della finestra (s);
- **contrasto primario**: B−C. Secondari: B−A e C−A;
- **soglie di rilevanza pratica**: 1,0 J per richiesta e 0,10 s di durata. La
  prima è circa l'1,2% degli ~82 J del run A-B-A e sta sotto il CV fra run del
  J/token riportato per v3; la seconda è circa il 3,3% di una finestra da
  ~3 s e sta sotto la cadenza di 0,5 s della telemetria dell'harness;
- **finestra valida**: `status == "ok"`, `eval_count` uguale al `num_predict`
  dichiarato e positivo. Una cella condizione-ciclo entra con almeno 3 finestre
  valide su 4; un contrasto entra se entrambe le celle sono incluse
  (eliminazione listwise del ciclo);
- **stima**: differenze pairate a livello di ciclo, intervallo t al 95% con
  n−1 gradi di libertà; sotto 4 cicli pairati l'intervallo non si riporta;
- **verdetto**: "effetto rilevante" se l'intero intervallo sta oltre +soglia o
  oltre −soglia; "equivalenza entro soglia" se l'intero intervallo sta dentro
  (−soglia, +soglia); "non conclusivo" se attraversa un bordo. Il mancato
  superamento di una soglia non è prova di assenza;
- **numerosità**: pilota a 6 cicli; se la semi-ampiezza B−C supera metà della
  soglia, run definitivo da capo a 12, poi 18, con tetto 18. La regola usa solo
  l'ampiezza, non il segno.

## 3. Esecuzione e integrità dei dati

- Modello `llama3.2:1b`, Q8_0, 1,52 GB, `size_vram = 0` (inferenza su CPU),
  residente prima, dopo i warm-up e alla fine (`/api/ps`, `expires_at` 2319).
- Prompt unico da 69 caratteri, `num_predict = 64`, `temperature = 0`,
  `keep_alive = -1` inviato come numero (i meta dei run B e C riportano
  `keep_alive_sent: -1`).
- 4 richieste per condizione per ciclo, invii a 6 s, coda di 2 s.
- Baseline: 3 finestre idle da 30 s prima e 3 dopo, con settling P1.5.
- LHM e HWiNFO64 non erano in esecuzione (`tasklist` prima del run); nessun
  altro monitoraggio noto.
- Durata a muro 812,0 s; sonda EMI 8126 righe, CPU 3,41 s (0,419% di un core).

Validità:

| controllo | valore |
|---|---|
| finestre totali | 72 |
| finestre valide | 72/72 (24 per condizione) |
| token per richiesta | 64 su tutte, `done_reason = length` |
| incrementi EMI contenuti | 2277 |
| incrementi a cavallo del bordo | 144 (2 per finestra) |
| incrementi negativi | 0 |
| tempo scoperto massimo in una finestra | 205,7 ms |

L'offset `mono − ts_100ns/1e7` è 16,571365 s su 8126 coppie, con escursione
max−min di 11,5 ms sull'intera prova. È lo stesso valore del run A-B-A della
stessa sessione (16,571367 s, scarto 2 µs): l'associazione degli orologi non è
il fattore limitante.

Baseline:

| | potenza | finestre | range |
|---|---|---|---|
| pre | 12,9184 W | 12,918 / 12,185 / 14,051 W | **1,8662 W** |
| post | 11,4985 W | 10,862 / 11,499 / 12,571 W | 1,7088 W |

Deriva post−pre: **−1,4199 W**. Il range pre supera 1,0 W, quindi la baseline
è `pre_unstable` secondo P1.6. Il settling pre è durato 10,0 s (20,88 contro
21,17 W) e il post 30,0 s (12,00 contro 11,65 W): il criterio P1.5 confronta
due blocchi consecutivi, non l'uguaglianza a `P_pre`, e non ha intercettato la
discesa successiva del livello idle.

## 4. Controllo di manipolazione

La condizione C deve differire da B solo per l'enumerazione dei processi. La
telemetria dell'harness conferma che il ramo `off` è davvero spento:

| grandezza (mediana dei 6 run) | B (`full`) | C (`off`) |
|---|---|---|
| `process_scan_s` | 0,0535 s | 0,0 s |
| `process_scan` duty | 10,77% | 0,0% |
| `sweep_duration_s` duty | 11,07% | 0,40% |
| CPU dell'osservatore | 11,94% di un core | 0,79% di un core |
| CPU dell'osservatore, secondi totali | 23,77 s | 1,41 s |
| durata del processo harness | 37,9–40,3 s | 33,6–34,8 s |

Il residuo di C (0,40% di duty, 0,79% di CPU) è la lettura EMI, la scrittura
della riga e l'interrogazione di `/api/ps`; non c'è una scansione nascosta. La
differenza di durata dei processi harness (circa +4,4 s in B) è il costo in
tempo a muro della scansione, coerente con 0,0535 s ogni 0,5 s per ~34 s.

Questo è un controllo di **manipolazione**, non di energia: dice che B e C
differiscono per la scansione, non che la scansione costi energia.

## 5. Risultati primari e secondari

Medie descrittive per condizione (tutte le 24 finestre valide):

| condizione | energia/richiesta | durata | potenza | J/token | TTFT |
|---|---|---|---|---|---|
| A | 86,65 J | 3,222 s | 27,61 W | 1,3539 | 0,1000 s |
| B | 85,00 J | 3,242 s | 27,07 W | 1,3282 | 0,1029 s |
| C | 87,55 J | 3,305 s | 27,32 W | 1,3679 | 0,1052 s |

Queste medie raggruppano finestre, non cicli; l'inferenza che segue è sulle
differenze pairate per ciclo.

### Contrasti primari (soglie preregistrate)

| contrasto | metrica | media | intervallo 95% | n | cicli +/− | verdetto |
|---|---|---|---|---|---|---|
| B−C | energia/richiesta | −2,54 J | [−7,95, +2,87] | 6 | 2/4 | non conclusivo |
| B−C | durata | −0,062 s | [−0,278, +0,153] | 6 | 3/3 | non conclusivo |

### Contrasti secondari

| contrasto | metrica | media | intervallo 95% | n | cicli +/− |
|---|---|---|---|---|---|
| B−A | energia/richiesta | −1,64 J | [−7,24, +3,95] | 6 | 2/4 |
| B−A | durata | +0,020 s | [−0,268, +0,308] | 6 | 2/4 |
| C−A | energia/richiesta | +0,90 J | [−3,52, +5,32] | 6 | 4/2 |
| C−A | durata | +0,082 s | [−0,110, +0,274] | 6 | 5/1 |

Altre metriche secondarie, senza soglia (solo descrittive):

| contrasto | J/token | potenza | TTFT |
|---|---|---|---|
| B−C | −0,0397 [−0,1242, +0,0448] | −0,244 W [−0,867, +0,379] | −0,0023 s [−0,0212, +0,0167] |
| B−A | −0,0257 [−0,1131, +0,0618] | −0,558 W [−1,479, +0,364] | +0,0029 s [−0,0075, +0,0133] |
| C−A | +0,0140 [−0,0550, +0,0831] | −0,314 W [−1,241, +0,613] | +0,0052 s [−0,0072, +0,0175] |

### Per ciclo

| ciclo | ordine | A energia / durata | B energia / durata | C energia / durata | B−C energia | B−C durata |
|---|---|---|---|---|---|---|
| 1 | ABC | 87,25 J / 3,286 s | 83,18 J / 3,108 s | 91,91 J / 3,435 s | −8,72 J | −0,327 s |
| 2 | BCA | 87,32 J / 3,248 s | 82,84 J / 3,180 s | 89,64 J / 3,401 s | −6,79 J | −0,221 s |
| 3 | CAB | 94,53 J / 3,552 s | 86,19 J / 3,281 s | 88,43 J / 3,274 s | −2,25 J | +0,006 s |
| 4 | CBA | 85,14 J / 3,094 s | 86,85 J / 3,310 s | 82,82 J / 3,230 s | +4,03 J | +0,080 s |
| 5 | ACB | 86,22 J / 3,278 s | 84,70 J / 3,231 s | 89,11 J / 3,372 s | −4,41 J | −0,141 s |
| 6 | BAC | 79,41 J / 2,876 s | 86,26 J / 3,345 s | 83,36 J / 3,117 s | +2,89 J | +0,228 s |

## 6. Variabilità fra cicli e numerosità

| | energia/richiesta | durata |
|---|---|---|
| dispersione dei differenzi B−C | 5,151 J | 0,2052 s |
| semi-ampiezza a 6 cicli | 5,407 J | 0,2153 s |
| target (metà soglia) | 0,5 J | 0,05 s |
| semi-ampiezza proiettata a 18 cicli | 2,56 J | 0,102 s |

La semi-ampiezza osservata è 10,8 volte il target sull'energia e 4,3 volte
sulla durata. Il fabbisogno calcolato dalla dispersione osservata con la stessa
regola (t ≈ 1,96 per gradi di libertà grandi) è dell'ordine di **400 cicli per
l'energia** e **65 per la durata**: il tetto di 18 non raggiunge l'obiettivo in
nessuna delle due metriche. Anche a 18 cicli, con media zero, l'intervallo
sarebbe ±2,56 J e ±0,102 s, fuori dalle bande ±1,0 J e ±0,10 s.

Per la regola preregistrata il pilota è quindi la prova definitiva:
`recommended_cycles = 18`, `beyond_cap = true` nel summary. Non si esegue
l'estensione, perché il tetto non può consegnare il target; **n_finale = 6**.
La stima è condizionata alla dispersione di questo run, che include una
baseline `pre_unstable` e una deriva di −1,42 W; con una baseline più stabile
la dispersione potrebbe essere minore, ma non è stato misurato e non si
sostituisce un valore ipotetico a quello osservato.

## 7. Cosa si può dire

1. **La scansione costa CPU, non un'energia risolta.** B esegue 0,0535 s di
   enumerazione ogni 0,5 s (10,8% di un core, 23,8 s di CPU su 6 fasi); C la
   elimina. L'effetto misurato sull'energia per richiesta è −2,54 J con
   intervallo [−7,95, +2,87]: include zero e la banda ±1,0 J. Non si può
   concludere né un effetto rilevante né l'equivalenza.
2. **Il segno puntuale non è quello atteso e non è consistente.** La media
   B−C è negativa (B consuma meno di C), ma i cicli sono 2 positivi e 4
   negativi per l'energia, 3 e 3 per la durata. Con questa dispersione il segno
   non è stabilito.
3. **La durata non mostra un allungamento risolto.** −0,062 s con intervallo
   [−0,278, +0,153]: un allungamento di 0,10 s non è escluso, ma non è
   dimostrato. La differenza di durata dei processi harness (B più lungo di
   ~4,4 s) è il costo della scansione nel tempo dell'harness, non nelle
   finestre di richiesta.
4. **Il totale harness+driver non si riproduce come stima puntuale.** Il run
   A-B-A dava +2,80 J e +0,195 s; qui B−A dà −1,64 J [−7,24, +3,95] e
   +0,020 s [−0,268, +0,308]. I due risultati sono compatibili entro
   l'incertezza, ma il valore puntuale dell'A-B-A non va trattato come una
   costante misurata: era una media di 3 cicli senza intervallo.
5. **Nessuna attribuzione ai componenti.** C−A (driver e `/api/ps`, senza
   scansione) è +0,90 J [−3,52, +5,32] e +0,082 s [−0,110, +0,274]: anche
   questo contrasto è irrisolto. Questo run non attribuisce il totale
   dell'A-B-A né alla scansione né al driver.
6. **Duty CPU ≠ energia.** Il conto ingenuo "10,8% di un core per 3,2 s alla
   potenza media della richiesta" darebbe circa 9 J per richiesta, cioè un
   valore attribuito, non misurato, che sta fuori dall'intervallo B−C. Il
   modello proporzionale non è quindi sostenuto dai dati; ma l'intervallo è
   troppo largo per trasformare questo in una stima quantitativa del costo
   energetico della scansione.
7. **Il limite è la variabilità fra cicli, non la strumentazione.** L'offset è
   stabile a 11,5 ms, la cadenza EMI è 100 ms, le finestre sono tutte valide e
   senza incrementi negativi. La dispersione dei differenzi (5,15 J, 0,205 s)
   viene dalle richieste e dalla baseline, non dal contatore.
8. **La baseline è un limite dichiarato.** Range pre 1,87 W (`pre_unstable`
   P1.6) e deriva −1,42 W. Il disegno Williams bilancia una deriva additiva
   costante fra le condizioni, ma non elimina la varianza che la deriva
   aggiunge ai singoli cicli.

## 8. Cosa questi dati non dimostrano

- **Non dimostrano che la scansione abbia costo energetico nullo.** L'intervallo
  B−C è largo 10,8 J: un effetto di +2,9 J è compatibile con i dati.
- **Non dimostrano l'equivalenza entro 1,0 J / 0,10 s.** Per affermarla
  l'intero intervallo dovrebbe stare nella banda; non ci sta.
- **Non dimostrano che la scansione causi (o non causi) il totale A-B-A.** La
  condizione B−C isola la scansione solo se tutto il resto è equivalente; il
  ramo `off` cambia anche il tempo a muro e il carico CPU dell'harness.
- **Non generalizzano** ad altri modelli, prompt, carichi, macchine o cadenze
  di scansione (qui 0,5 s).
- **Non arbitrano la scala assoluta.** EMI e qualunque altro lettore dello
  stesso `MSR_PKG_ENERGY_STATUS` (0x611) concordano per costruzione; senza un
  wattmetro AC/DC esterno la scala resta non arbitrata.
- **Non coprono le pause fra richieste.** La finestra va da invio a fine
  risposta (~3,2 s) e lascia fuori i ~2,8 s di pausa dentro ogni intervallo di
  6 s. Una quota di scansione pagata solo nelle pause è fuori da questa misura;
  la quota che cade dentro le finestre è inclusa.
- **Non separano prefill e decode.** Il TTFT è ~0,10 s su ~3,2 s: la finestra è
  dominata dal decode, e i contrasti non dicono nulla sul prefill.

## 9. Conseguenze operative

- Il costo certo della scansione è in **tempo e CPU dell'harness**: 10,8% di un
  core e ~4,4 s per blocco di 6 fasi. È un argomento per non attivarla durante
  la campagna principale, ma non è una misura di energia.
- Lo statement conservativo resta quello dell'A-B-A: un effetto totale
  harness+driver di alcuni J per richiesta non è escluso. Questo run non lo
  riduce; mostra che un disegno 6×4 non risolve la scala di 1 J.
- Per risolvere 1 J/richiesta con questa variabilità servirebbero centinaia di
  cicli. Un disegno più efficiente deve ridurre la varianza a livello di
  richiesta (più richieste per cella, finestre più lunghe, pairing più stretto,
  baseline più stabile), non cambiare la scansione. È un esperimento separato.
- Nel testo della tesi il duty CPU della scansione non va presentato come
  costo energetico: qui 10,8% di un core non ha prodotto un aumento risolto
  dell'energia per richiesta.

## 10. Limiti

- Un solo modello (`llama3.2:1b`, Q8_0, 1,52 GB, `size_vram = 0`, CPU), un solo
  prompt (69 caratteri, 64 token di uscita), `temperature = 0`,
  `keep_alive = -1`.
- 24 finestre per condizione, 6 cicli; l'intervallo t assume scambiabilità dei
  differenzi fra cicli. Il bilanciamento Williams protegge da posizione e
  carryover, non da una deriva che cambia forma.
- Baseline `pre_unstable` (range 1,87 W) e deriva −1,42 W.
- Cadenza di scansione fissa a 0,5 s; il duty misurato non si trasferisce a
  cadenze diverse.
- Nessun wattmetro esterno; nessuna validazione indipendente della scala.
- La semi-ampiezza proiettata a 18 cicli è una proiezione dalla dispersione
  osservata, non una previsione garantita.

## 11. Riprodurre

Con LHM e HWiNFO64 chiusi, Ollama in ascolto e `llama3.2:1b` disponibile:

```
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe -u \
    harness_overhead_probe.py --tag harness_overhead_abc_20261025 --cycles 6
```

I file del run, in `experiment_results/`:

- `harness_overhead_abc_20261025_probe.csv` — sonda EMI;
- `harness_overhead_abc_20261025_requests_probe_c{1..6}_a.csv` — richieste A;
- `harness_overhead_abc_20261025_{telemetry,requests,meta}_b{1..6}.*`
  e `..._c{1..6}.*` — B e C;
- `harness_overhead_abc_20261025_harness_{b,c}{1..6}.log` — log dell'harness
  (ignorati da git);
- `harness_overhead_abc_20261025_windows.csv` — 72 finestre con energia,
  copertura, potenza e J/token;
- `harness_overhead_abc_20261025_summary.json` — configurazione, criteri
  preregistrati, celle per ciclo, contrasti, regola di numerosità;
- `harness_overhead_abc_20261025_console.log` — log di console (ignorato da
  git).

Un tag nuovo è un run nuovo: il tag è l'identità dei file, non va riusato per
una replica.
