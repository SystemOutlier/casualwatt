# Valutazione di `ricerca_metodo.DOCX`: cosa è utile, cosa no, e cosa abbiamo misurato per decidere

**Data**: 2026-10-23, ~17:40
**File letto**: `CWProject/ricerca_metodo.DOCX` (34.587 B, mtime 23/10 17:07), estratto con
`zipfile` + parsing `word/document.xml` (365 righe di testo).
**Regola applicata** (stop-and-reason): il documento è *materiale di un altro LLM*, quindi
spunto, non fede. Ogni claim è stato (a) confermato, (b) confutato con evidenza locale, o
(c) dichiarato non testabile. Dove il documento si sovrappone alla mia valutazione di un'ora
fa (`strumenti_esteri_20261023_valutazione.md`), confronto le due conclusioni e correggo me
stesso dove ho torto.

## 0. Com'è fatto il documento

Tre sezioni incollate una dopo l'altra, senza gerarchia:

1. **WMI/CIM** (righe 1-90 e **91-180: identiche, duplicatione**) — valutazione di
   PowerShell/CIM come sorgente, con script `Get-CimInstance`.
2. **"Benchmark scientifico per Ollama/SLM"** (righe 181-254) — architettura a livelli,
   split prefill/decode, sweep di parametri, tabella metriche, roadmap.
3. **I 4 progetti esterni** (righe 255-364) — CEM, Accenture, AI-Wattch, ML CO2 Impact:
   cioè gli stessi quattro che ho valutato io in `strumenti_esteri_20261023_valutazione.md`.

Segni di provenienza: citazioni `[1][2]` e `[github]` **senza lista di riferimenti in fondo**,
formole math sostituite da spazi vuoti (righe 219-226: "Request Energy ()", "Geometria dei
Prompt ( vs )", "dove  sono i token di input"). Quindi: **nessun claim della sezione 2 è
risalibile a una fonte verificabile da questo file**. Questo da solo basta per non portarlo in
tesi come citazione; alcune sue *idee* sono però giuste e le verifichiamo noi.

## 1. Confermato: quello che il documento dice bene

**(a) WMI/CIM non misura energia, e va usato come contesto.** Il cuore della sezione 1 è
corretto e coincide con quello che abbiamo già stabilito da soli: le sorgenti energetiche
sono EMI (contatore) e LHM (potenza da integrare), Task Manager/PDH/EPI non arbitrano niente
(memo `project-lhm-validation-experiment`, probe del 23/10). La frase "sono variabili
correlate al consumo, ma non sono misure energetiche" è la nostra stessa regola contro
l'integrazione di °C come joule, detta dall'esterno. Utile ma non nuova.

**(b) La gerarchia in 5 livelli** (EMI energia CPU / NVML energia GPU / WMI contesto /
E3-SRUM attribuzione / wattmetro validazione) **è quasi esattamente il nostro stato dell'arte**,
con due caselle che noi non abbiamo ancora scritto da nessuna parte in forma di elenco e che
conviene adottare: il "flag EMI disponibile" e la "**deriva della baseline**" fra i campi del
verbale. Il secondo in particolare è ciò che il nostro probe dell'osservatore ha reso evidente
(A-C 0,63 W > C-B 0,22 W, `observer_cost_20261023_analisi.md`): dichiararla per campo, non
scoprire la volta dopo.

**(c) Il domini RAPL non vanno sommati.** Righe 271-273: "i tuoi quattro canali EMI (PKG,
DRAM, PP0, PP1) non vanno sommati indiscriminatamente: sono domini diversi, con possibili
sovrapposizioni gerarchiche". **Corretto e importante**: PP0 (cores) e PP1 (iGPU) sono
*contenuti* in PKG, quindi sommarli doppio-counta. La mia proposta `ΔPP0/ΔPKG` (§7(c) del mio
documento) è un rapporto e non una somma, e quindi regge; ma la nota di questo documento è un
argomento in più a favore, e va messa nella tesi come vincolo esplicito ("i canali EMI non sono
additivi").

**(d) "Non copiare formule o accuratezze non validate"** (righe 356-361) è esattamente la
nostra regola "tenere l'attuale finché provato". Su questo il documento è un alleato.

## 2. Confutato con evidenza locale: quello che il documento sbagliava

Qui sta il valore reale della lettura: sei claim falsi per *questa* macchina, quattro dei quali
mi hanno costretto a misurare.

**(a) "NVML → energia GPU" è inapplicabile qui.** NVML è la libreria di *NVIDIA*. Il MINI_IT13
ha solo la Iris Xe integrata: nel report GUI l'unica potenza GPU è `/intelgpu…/0/power/0`
(`lhm_gui_report_20261023.txt`, 5 righe di potenza in 3238). Quindi il ramo GPU del documento
non esiste sul nostro bersaglio; il canale GPU ce lo dà già LHM e vale 0,166 W in media sulla
trace (campo EMI offset 48). Da non adottare.

**(b) "Campionamento ad alta frequenza, es. ogni 50 ms" — il documento non dice che per EMI il
limite potrebbe non esserci, e noi ora lo abbiamo misurato.** `emi_resolution_check.py` (nuovo,
sulla nostra trace `lhm_emi_trace_20261023_154628.csv`, 635 campioni a 251 ms mediani, 160 s):

```
delta PKG fra campioni consecutivi = 0 : 0/634 (0,0%)
delta PKG minimo osservato            : 1,982 J   (mediana 3,149 J)
delta PP0 minimo osservato            : 0,653 J   (mediana 1,774 J)
potenza per campione (PKG)            : mediana 12,50 W, min 7,90, max 50,31
quantum visibile del contatore        : MCD dei delta = 1 pWh  → nessuna quantizzazione
```

**Il contatore EMI si muove a ogni campione, anche a 251 ms, e non mostra gradini.** Il collo
di bottiglia dei nostri 0,28-0,34 s non è il registro: è il nostro thread `power-integration`
che passa da LHM. Conseguenza operativa: **un sampler EMI a 50 ms è plausibile ed è la prova da
fare** — ed è la stessa domanda che avevamo già aperto (ottimizzare `_read_power_w_direct` o
correggere la docstring a 0,3 s), ora con un motivo in più per scegliere: se campiona EMI a 50 ms
funziona, la risoluzione del nostro sistema smette di essere un limite del sensore. Da notare
l'onestà del caso: "0 delta nulli su 634" *non* dimostra che il registro cambi ogni 50 ms;
dimostra solo che accumula fra i nostri campioni. La prova diretta è un probe a 50 ms, non
questa riga.

**(c) "Separare prefill e decode": il tempo ce l'abbiamo gia', l'energia no.**
> **Emendazione (23/10, ore 19:30 — la versione precedente di questo punto era
> in parte falsa, e qui viene corretta).** Avevo scritto che lo split "e'
> impossibile, e non solo perche' non registriamo il TTFT", portando `stream:
> False` come primo blocco. **Non regge.** La documentazione ufficiale
> dell'API Ollama (`docs/api.md`, consultato oggi) espone in **ogni** risposta
> di `/api/generate`, anche non in streaming, i campi `prompt_eval_duration`
> ("time spent in nanoseconds evaluating uncached prompt tokens") e
> `eval_duration` ("time in nanoseconds spent generating the response"): il
> client non deve cambiare, e il nostro codice di produzione **gia' li legge**
> (`cwEnergyModular/benchmark_unified.py:162-163`, con commento "campi nativi
> dell'API, in ns") e **gia' li esporta** nel CSV (`casualwatt_csv_export.py:29`,
> colonne `prefill_duration_s` / `decoding_duration_s`). Prova nei dati reali,
> `cwEnergyModular/results/semantic_evaluation_results.csv`, 9 righe, tutte con
> il campo valorizzato:
>
> ```
>    dur    pre     dec   in  out  ms/tok pre  ms/tok dec  ratio   non coperto
>   12.58  0.464   5.474   35   67       13.3       81.7    6.16        6.64
>   13.54  0.230  13.283   31  160        7.4       83.0   11.17        0.03
>    1.87  0.272   1.545   33   21        8.3       73.6    8.92        0.05
>   12.22  0.254   5.968   18   66       14.1       90.4    6.40        6.00
>    1.02  0.230   0.740   14    9       16.4       82.2    5.00        0.05
>    0.96  0.218   0.624   14    8       15.5       77.9    5.01        0.12
>    5.74  0.176   3.697   44  160        4.0       23.1    5.78        1.87
>    0.39  0.098   0.264   40   12        2.5       22.0    8.97        0.03
>    0.40  0.111   0.256   40   11        2.8       23.3    8.37        0.03
> ```
>
> Tre conseguenze, tutte nuove per noi:
>
> 1. **rapporto decode/prefill per token = 5,0-11,2 (mediana ~8,4)**. Il
>    documento esterno asseriva "fino a 3:1" senza fonte: sui **nostri** dati
>    reali si misura **circa un ordine di grandezza**, che e' esattamente quanto
>    dichiarato da `horswill2026greenpixie` ("roughly an order of magnitude
>    larger than prefill"). E' la prima validazione interna di un claim esterno
>    che facciamo con i nostri numeri, non con quelli altrui.
> 2. **"non coperto" = `duration_s - prefill - decoding`**: due righe hanno
>    6,6 e 6,0 s fuori da prefill+decode (righe 1 e 4), le altre 0,03-1,9 s.
>    Quei secondi sono **caricamento del modello**, e sono la prova misurata del
>    buco `keep_alive` del punto (e): la prima richiesta di una sessione paga
>    il load, e se il modello e' in residenza o meno non e' ne' controllato ne'
>    registrato.
> 3. **Il limite reale non e' il client, e' la cadenza**: mediana prefill
>    **0,230 s** (range 0,098-0,464) contro intervallo PI misurato in fase load
>    **0,3148-0,339 s** → **0,72 campioni attesi dentro il prefill**. La
>    separazione *temporale* e' disponibile da subito; la separazione
>    *energetica* no, perche' la finestra di prefill e' piu' corta di un
>    campione. E' questa la ragione per cui il probe EMI a 50 ms del punto (b)
>    passa da "curiosita'" a "prerequisito": a 50 ms il prefill diventa 5-9
>    campioni, e la somma trapezoidale sulla fase ha un senso.

Resta valido il nucleo della mia osservazione, ma riformulato: **la metrica
J/token dei protocolli v2/v3 e' oggi, di fatto, un costo di decode** per due
ragioni indipendenti — la geometria dei protocolli da esperimento (prompt da 8
parole) e il fatto che **l'harness `experiment_validate_lhm.py` non registra i
campi di fase**, anche se il client di produzione li ha gia'. Da dichiarare nel
capitolo limiti, e da recuperare nell'harness (vedi #15 dei task).

Per completezza, la geometria dei protocolli da esperimento (quella che vale per
il numero 1,286 J/token committato), da `lhm_validation_v3_20261023_160430.csv`,
5 fasi load, 75 richieste:

```
N_in  per richiesta : 12,3 token      (925 token su 75 richieste)
N_out per richiesta : 31,8 token      (2387 token su 75 richieste)
durata per richiesta: 3,60 s
intervallo PI in load: 0,3148 / 0,3224 / 0,3265 / 0,3335 / 0,339 s
J/token per run      : 0,988 / 1,076 / 0,834 / 0,980 / 1,058
```

**(d) Lo sweep di geometrie (64/512/2048 token in input) resta la vera azione sul protocollo;
lo split di fase diventa un'azione sul campionamento.** Corretto dal punto (c), le due cose
non sono in alternativa. Se `E_tot ≈ a·N_in + b·N_out` (`cavagna2026sweetspot`, arXiv:2602.05695,
già verificato e in bibliografia), allora il nostro 1,29 J/token vale solo per `N_in ≈ 12`.
Con 2-3 geometrie a `N_out` fisso stimiamo `a` e `b` e il numero diventa una curva. Questo
ridefinisce il protocollo v4: non solo "numero fisso di richieste", ma **numero fisso di
richieste × geometria dichiarata**. Nello stesso run v4 l'harness deve registrare
`prefill_duration_s`/`decoding_duration_s` (già esposti dall'API, §c): senza di quelli la
geometria non è nemmeno verificabile a ritroso dai CSV.

**(e) Il "30-75% dell'energia è il modello tenuto in memoria" è un numero non firmato, ma il
concetto è un buco reale nel nostro protocollo.** Nel nostro codice **non esiste** `keep_alive`
e non esiste warm-up sul motore: è scritto nella nostra stessa lista decisioni,
`Tesi-latex/qoder-bozza/DECISIONI.md:108-110` (D3, "Il motore non usa né warm-up né keep_alive
(nessun uso nel codice)"). Quindi lo stato di residenza dei pesi fra `base_a`, `load` e
`base_b` non è controllato né dichiarato, e questo è un candidato naturale per l'instabilità
della baseline che vediamo (13,39 → 12,19 W fra run; r = −0,982 fra baseline e J/token).
Azione a costo quasi zero: fissare `keep_alive` (o scaricare il modello fra le fasi) e
**dichiararlo nel verbale**, prima di lanciare la v4.

**(f) "Nessuno integra locale Windows + cloud + rete: questa è la tua specificità" è troppo
forte, ed è la riga più pericolosa del documento.** Il documento esamina 4 progetti e non
nomina **EnviroLLM** (Allen 2025, arXiv:2512.12004, MIT), che fa monitoraggio LLM locale su
Windows e che abbiamo già verificato e messo fra i competitor. Una gap statement del tipo
"nessuno" costruita su un campione di 4 è confutabile da un relatore con una ricerca di 30
secondi. Da riscrivere come: *nessuno dei tool confrontati combina misura locale hardware,
stima cloud multi-tier e rete separata nello stesso strumento* — che è vero, verificabile, e
non rivendica assenze assolute.

## 3. Dove il documento contraddice la mia valutazione, e chi ha ragione

| punto | documento `ricerca_metodo` | mia valutazione (`strumenti_esteri`) | verdetto con fonte |
|---|---|---|---|
| CEM | "alta come riferimento, bassa come dipendenza" | idem + secondo lettore nella checklist Linux | **coincidenti**; il documento non aggiunge nulla di verificato che io non abbia già citato riga per riga |
| Accenture | "granularità per funzione: non adottare per LLM; misurare per richiesta e fase" | proponevo un context manager stile `EnergyContext` come estensione | **il documento ha ragione sulla misura, io solo sul capitolo estendibilità**: il context manager non serve alla metrica J/token (che resta per richiesta/fase), va citato solo come estendibilità. Correggo la mia formulazione |
| AI-Wattch | "può ispirare il fallback token+tempo per il tier cloud" | "non prendiamo nulla di tecnico" | **il documento è più utile**: la dualità token/tempo è un *pattern di stima* dichiarabile, purché resti stima. Da accogliere nel capitolo cloud con etichetta `estimated`, non nel metodo di misura |
| ML CO2 Impact | "solo contesto, focalizzato sul training" | §6 mio: "training/inferenza, accetta potenza misurata o stimata, applica PUE" | **siamo sbagliati tutti e due** — vedi §4 sotto, correggo il mio documento committato |

## 4. Correzione al mio documento committato (commit `4ed7fe6`)

Verificando `html/_compute.html` del repo `mlco2/impact` (non il README, che è di 42 righe e non
contiene alcuna tassonomia measured/estimated), la calcolatrice espone questi soli campi:
**Hardware type** (select di GPU), **Hours Used**, **Provider**, **Region of Compute**, e due
campi custom `Carbon Efficiency (kg/kWh)` impact/offset. Il testo della pagina dice:

- `:15-19` "This calculator will give you 2 numbers: the **raw** carbon emissions … and the
  approximate **offset** … we are open to update our estimates if anything looks inaccurate";
- `:20-22` "keep in mind that the estimate provided below **does not** take datacenter PUE
  (Power Usage Effectiveness) into account. To do so, you need to find your datacenter's PUE …
  and multiply the quantity of carbon emitted provided below by that number";
- `:204-205` "Power consumption x Time x Carbon Produced Based on the Local Power Grid".

Quindi nel mio §6: **(1)** "accetta potenza misurata **o** stimata" è indebito — non c'è un
campo di potenza misurata, c'è un prodotto potenza×tempo con hardware scelto da lista;
**(2)** "applica PUE" è **falso**: la pagina lo esclude esplicitamente e chiede di moltiplicare
a mano; **(3)** "training/inferenza" non è dichiarato né da me né dal DOCX: la forma è
agnostica (ore × tipo di macchina). Il valore che resta valido è il **template LaTeX** (`:13`
"generated latex template which automatically includes the Calculator's output") e i fattori di
griglia per regione. Correggo il file committato.

## 5. Cosa adottare: lista operativa ordinata per costo/beneficio

Da adottare (tutte cose che noi non facevamo):

1. **Verbale di test con campi contesto espliciti**: `flag_emi_disponibile`, `deriva_baseline`
   (A−C), lista processi concorrenti, GUI osservatore aperta/chiusa. Costa 10 righe di JSON
   negli script protocollo e implementa il nostro stesso finding sull'osservatore.
2. **`keep_alive` fissato e dichiarato** prima della v4 (D3 della nostra lista decisioni).
3. **Geometria dichiarata in ogni run** (N_in, N_out medi) — ce l'abbiamo già nei CSV, va nel
   verbale e in tesi: senza di essa 1,29 J/token è privo di dominio di validità.
4. **Sweep di N_in a N_out fisso** (2-3 livelli) come definizione estesa della v4 → modello
   `a·N_in + b·N_out`.
5. **Probe EMI a 50 ms** per rispondere alla domanda di risoluzione aperta al §2(b): se il
   contatore si muove anche a 50 ms, la risoluzione del sistema è nostra, non del sensore, e il
   capitolo limiti si accorcia.
6. "Canali EMI non additivi" (PP0+PP1 ⊂ PKG) come vincolo scritto nel capitolo metodologia.
7. **Registrare le durate di fase nell'harness** (`prefill_duration_s`/`decoding_duration_s`,
   già forniti dall'API non in streaming): serve a rendere la geometria verificabile a ritroso
   e a preparare lo split energetico quando (e solo se) il sampler andrà a 50 ms.

Da non adottare: NVML (niente NVIDIA), split per funzione Python, accuratezza/numeri non firmati
del §2 del documento (3:1, 30-75%), gap statement "nessuno integra locale+cloud+rete".

## 6. Cosa NON cambia

Il backend resta LHM `power-integration` + EMI contatore: il documento non propone alcun
sostituto misurato su Windows e non nomina LHM nemmeno una volta (assenza che dice molto della
sua conoscenza del nostro stato). La metrica primaria resta J/token, che adesso va etichettata come **costo di decode a geometria ~12/32 token**, con la verifica incrociata EMI che
convalida l'accumulatore a 251 ms.

## File prodotti e verifiche fatte

- `CWProject/emi_resolution_check.py` (nuovo): risoluzione del contatore EMI dalla trace
  + geometria reale del protocollo v3. Riproducibile: eseguito 23/10 ~17:35.
- Numeri citati da: `experiment_results/lhm_emi_trace_20261023_154628.csv` (635 righe),
  `experiment_results/lhm_validation_v3_20261023_160430.csv` (15 righe),
  `experiment_results/observer_cost_20261023_analisi.md`,
  `Tesi-latex/qoder-bozza/DECISIONI.md:108-110`, `CWProject/LibreHardwareMonitor.Report.txt`,
  `html/_compute.html` di `mlco2/impact` via raw.githubusercontent.
- Letto integralmente: `CWProject/ricerca_metodo.DOCX` (365 righe di testo estratte).
- **Aggiunte dell'emendazione §2(c) (23/10 ~19:30)**: `docs/api.md` di Ollama via
  raw.githubusercontent (campi `prompt_eval_duration` / `eval_duration` nella risposta **non**
  in streaming, in nanosecondi); `cwEnergyModular/benchmark_unified.py:162-163`;
  `cwEnergyModular/casualwatt_csv_export.py:29`;
  `cwEnergyModular/results/semantic_evaluation_results.csv` (9 righe, delimiter `,`,
  encoding `utf-8-sig`; colonne di fase valorizzate in **tutte** le righe). Nota metodologica:
  la prima lettura di quel CSV con `delimiter=';'` restituiva `None` ovunque — il file è
  in **virgola**, gli export degli esperimenti sono in **ponto e virgola**. I file con `None`
  sistematico sono un artefatto di parsing, non un dato mancante: da tenere presente perché
  è lo stesso errore che produce falsi "0,0".
