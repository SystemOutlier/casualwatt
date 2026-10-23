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

**(c) "Separare prefill e decode al TTFT" con i nostri protocolli attuali è impossibile, e non
solo perché non registriamo il TTFT.** Due blocchi indipendenti, entrambi verificati:

1. `stream: False` è in **tutte** le chiamate Ollama del repo:
   `cwEnergyModular/benchmark_unified.py:132`, `experiment_validate_lhm.py:112`,
   `four_way_test.py:220`, `emi_lhm_offset_test.py:117`, `cwEnergyModular/llm_judge.py:127`.
   Nessun timestamp di primo token esiste nei dati; servirebbe cambiare il client.
2. Anche cambiandolo, **la nostra geometria non ha prefill da separare**. Dai CSV v3 post-fix
   (`lhm_validation_v3_20261023_160430.csv`, 5 fasi load):

```
N_in  per richiesta : 12,3 token      (925 token su 75 richieste)
N_out per richiesta : 31,8 token      (2387 token su 75 richieste)
durata per richiesta: 3,60 s
intervallo PI in load: 0,3148 / 0,3224 / 0,3265 / 0,3335 / 0,339 s
J/token per run      : 0,988 / 1,076 / 0,834 / 0,980 / 1,058
```

Un prefill di ~12 token su llama3.2:3b in CPU è una frazione di secondo, confrontabile con
*un solo* intervallo di campionamento. Il documento chiede una cosa che i nostri dati non
possono dire, e la chiede a una geometria (prompt da 8 parole) dove il fenomeno è minimo.
**La nostra metrica J/token è oggi, di fatto, un costo di decode** — e non l'abbiamo mai
scritto. Questa è la scoperta più utile della sezione 2, ed è una limitazione da dichiarare nel
capitolo limiti, non da nascondere.

**(d) Lo sweep di geometrie (64/512/2048 token in input) è quindi la vera azione, non il TTFT.**
E' l'unico modo di rispondere alla domanda che il documento pone male: se `E_tot ≈ a·N_in +
b·N_out` (SweetSpot/Cavagna, che abbiamo già in bibliografia da `benchmark vari.DOCX`), allora
il nostro 1,29 J/token vale solo per `N_in ≈ 12`. Con 2-3 geometrie a `N_out` fisso stimiamo
`a` e `b` e il numero diventa una curva. Questo ridefinisce il protocollo v4: non solo "numero
fisso di richieste", ma **numero fisso di richieste × geometria dichiarata**.

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
