# Protocollo v4 — decisioni congelate

Documento di lavoro. Ogni punto si definisce, si congela e si salva con un commit
separato. Le decisioni valgono per l'esperimento v4; la produzione non cambia
finché la v4 non produce evidenza. Nessun push automatico.

Data: 2026-10-24. Branch: `energy-consumption-framework-ollama-d248a`.

| punto | oggetto | stato |
|---|---|---|
| P1 | baseline e calibrazione idle | **congelato 2026-10-24** (emendato: sensibilità post-hoc; letteratura e confronto CodeCarbon) |
| P2 | token effettivi e terminazione | **congelato 2026-10-24** |
| P3 | geometria, modello e stima | **congelato 2026-10-24** |
| P4 | incertezza e validazione | **congelato 2026-10-24** (emendato: inviluppo convesso per la copertura, bootstrap dei residui standardizzati, criterio monolitico di catena, `u_edge` solo nel budget predittivo; seconda emenda solo di forma: P4.1 in quattro clausole, P4.4 a otto requisiti numerati con la baseline 3 pre + 3 post obbligatoria anche sui controlli) |
| P5 | campi CSV e runner | aperto |
| P6 | esecuzione e analisi | aperto |

Le formule di P1–P4 sono raccolte, con applicazione e giustificazione, nella
sezione finale **Formulario consolidato (F.0–F.17)**: è una sezione derivata, non
introduce decisioni e in caso di divergenza vince il punto congelato.

---

## Terminologia (vincolante per il protocollo e per la tesi)

Un solo termine primario: **baseline**. Indica la stima della potenza idle del
package, in watt.

| termine | simbolo | unità | definizione |
|---|---|---|---|
| baseline | `P_pre` | W | mediana delle tre repliche idle pre |
| energia di baseline | `E_base` | J | `P_pre · Δt_W` |
| incremento netto | `E_net_incremental` | J | `E_pkg_gross − E_base` |
| drift | `dP` | W | `P_post − P_pre` |

- **Idle floor** è un sinonimo operativo di baseline. Compare una sola volta,
  qui, e poi non si usa più. Non è una seconda grandezza e non indica l'energia.
- **Fondo** non si usa come sostantivo tecnico: al suo posto, baseline.
- "Baseline" da sola non indica mai l'energia. Se serve l'energia, si dice
  *energia di baseline* (`E_base`).
- La formula, già in P1.3, è:

```
E_net_incremental = E_pkg_gross − P_pre · Δt_W
P_pre = baseline_pre_w = mediana(P_rep,1, P_rep,2, P_rep,3)
```

Questa terminologia si applica anche alla tesi: nei capitoli 3 e 5 si sostituisce
"fondo di idle" con "baseline", e "idle floor" resta solo come sinonimo
dichiarato alla prima occorrenza.

---

## P1 — Baseline e calibrazione idle

### P1.1 Decisione in una riga

La baseline della v4 è stimata **per blocco** con lo stesso estimatore della
produzione — tre finestre idle consecutive da 30 s, `P_rep = ΔE/Δt`,
`P_pre = mediana(P_rep)` — misurata prima del blocco e ripetuta dopo; si applica
`P_pre`, il post è diagnostico.

### P1.2 Perché non un estimatore nuovo

`calibrate_idle` implementa già tre ripetizioni da almeno 30 s e la mediana
(`energy_session.py:2363-2396`), con floor a 30 s (`:2252-2257`) e rifiuto dei
delta negativi (`:2383-2387`). La lettura di una finestra è
`read_idle_window_j(30.0)` (`:1576-1645`); con EMI restituisce
`(delta_j, dt_reale, "emi-counter")`.

La v4 non cambia la formula: cambia il momento e il numero di applicazioni (per
blocco, pre/post). Cambiare estimatore e protocollo insieme confonderebbe
l'esperimento. Implementazione: chiamare `read_idle_window_j(30.0)` tre volte e
calcolare la mediana; non chiamare `calibrate_idle`, che gestisce start/stop
della sessione e un `sleep(1.0)` iniziale.

### P1.3 Definizioni

```
finestra idle      = 30,000 s, passati esplicitamente
P_rep,k            = ΔE_contatore,k / Δt_reale,k     k = 1..3
baseline_pre_w     = mediana(P_rep,1, P_rep,2, P_rep,3)
baseline_post_w    = idem, dopo l'ultimo punto
baseline_drift_w   = baseline_post_w − baseline_pre_w
baseline_energy_j  = baseline_pre_w · Δt_W
E_net_incremental  = E_pkg_gross − baseline_energy_j
```

Dominio: PKG, lo stesso di `E_pkg_gross`. Backend: lo stesso della misura della
richiesta; su questo host `emi-counter`. Se si usa il fallback, si registra
`baseline_backend` e l'incertezza di bordo del backend.

### P1.4 Stato della macchina

- modello caricato con `keep_alive=-1` e verificato residente (`/api/ps`);
- due warm-up a `(512,128)`, scartati;
- GUI di LibreHardwareMonitor chiusa;
- alimentatore collegato, piano energetico invariato e registrato, stato batteria
  registrato;
- sampler attivo con la stessa cadenza della misura;
- top-5 processi e CPU totale prima e dopo; `background_load` se la CPU totale
  resta sopra il 5% per 3 s;
- nessuna sottrazione del costo dell'osservatore: la GUI si chiude.

Il costo misurato della GUI è 0,2–0,9 W, inferiore a 1 W e confondibile con il
drift (`observer_cost_20261023_analisi.md` §2): sottrarlo sarebbe arbitrario.

Nota su `keep_alive`: la produzione ora lo dichiara e lo invia solo se
configurato (`benchmark_unified.py:138-146`, `:191`, `:860`), con default vuoto
(`config.py:146-147`). La v4 lo imposta esplicitamente a `-1` e registra
`keep_alive_sent`.

### P1.5 Sequenza pre e post

Pre:

1. settling: la media mobile a 10 s cambia meno di 0,5 W in 10 s, con tetto di
   120 s; si registra `settle_pre_s`;
2. tre finestre consecutive da 30 s, senza richieste;
3. `baseline_pre_w` = mediana; si registrano le tre misure.

Post:

1. stesso settling, con tetto 120 s;
2. tre finestre da 30 s;
3. `baseline_post_w` = mediana; drift.

Il settling usa la stazionarietà, non l'uguaglianza con `P_pre`: altrimenti il
post sarebbe ancorato al pre e il drift invisibile.

Il cooldown fra i punti usa un criterio distinto: la media a 10 s rientra entro
0,5 W da `P_pre` per 10 s, con tetto 120 s; se il tetto viene raggiunto, si
procede e si marca `cooldown_timeout`.

### P1.6 Controlli

- `pre_range_w = max(P_rep) − min(P_rep)`.
- `pre_unstable` se `pre_range_w > 1,0 W`. Motivazione misurata: 1 W di errore
  sulla baseline sposta J/token del 6–11%
  (`idle_floor_sensitivity_20261023_analisi.md` §2). Il flag non invalida da
  solo: entra in `half_range_pre_w`.
- Se una finestra ha delta negativo, contatore resettato o lettura non finita:
  si ripete una volta; alla seconda si invalida il blocco. Non si corregge.
- Drift, con somme sulle richieste valide (non sul tempo a muro del blocco):

```
r_A = |dP| · Σ_{i∈blocco} Δt_W,i / Σ_{i∈blocco} E_trunc,i
r_B = |dP| · Σ_{i∈punto}  Δt_W,i / Σ_{i∈punto}  E_trunc,i
```

  Soglia operativa 10%, sensibilità a 5/20%, non modificabile dopo i dati.
  `0,10 J/token` resta soglia assoluta secondaria e provvisoria.
- Se `r_A > 10%`: blocco marcato `baseline_unstable`; con due blocchi su tre
  marcati, campagna invalida.
- Se `r_B` è 10–20%: punto mantenuto, marcato, peso ridotto; oltre 20%: escluso
  dal fit primario e riportato in sensibilità. Regola congelata prima dei dati.
- Se oltre il 5% delle richieste valide di un punto ha
  `E_net_incremental < 0`: punto marcato `negative_increment`; il grezzo resta
  firmato.
- Se il denominatore di `r_A` o `r_B` è zero, il blocco o il punto è invalido
  per costruzione.

### P1.7 Incertezza di baseline

```
half_range_pre_w = (max(P_rep) − min(P_rep)) / 2     # semi-range conservativo
half_drift_w     = |dP| / 2                         # semi-range conservativo
budget_base_w    = sqrt(half_range_pre_w² + half_drift_w²)
budget_base_j    = Δt_W · budget_base_w
budget_J_base    = budget_base_j / N_out_actual
```

Nessuna di queste grandezze è una deviazione standard: `half_range_pre_w` e
`half_drift_w` sono **semi-range conservativi**; `budget_base_w` è la loro
combinazione in quadratura, un budget, non una varianza. Con n=3 non si stima una
deviazione standard, e nella tesi si usa l'espressione "semi-range conservativo",
mai "deviazione standard". `budget_J_base` è **solo** il contributo di baseline;
il totale aggiunge bordo finestra e repliche. L'esempio di 0,034 J/token a 0,3 W,
3,6 s e 32 token è solo questo contributo.

**Stato della forma di combinazione (aggiornamento 24-10-2026).** La quadratura
resta la formula operativa della campagna e non viene modificata. Non va però
presentata come un limite conservativo garantito: per due termini non negativi
`sqrt(a² + b²) / (a + b)` sta fra `1/√2` e `1`, quindi la somma aritmetica è fra
1,000 e 1,414 volte la quadratura, qualunque siano i valori misurati. Con l'unico
termine ancorato ai dati — `|dP| = 0,461 W` nel run v3, cioè
`half_drift_w ≈ 0,23 W` (`lhm_validation_v3_20261023_185232.md:13,24`) — e
nell'ipotesi puramente illustrativa che i due termini siano uguali, la quadratura
dà 0,326 W contro 0,461 W della somma.

`half_range_pre_w` invece **non è mai stato misurato**: i run v3 usavano una
finestra da 10 s per fase (`lhm_validation_v3_20261023_185232.md:6`, "Baseline:
10 s x2 (A-B-A)"), quindi non esistono terne di repliche. Le prime le produrrà la
struttura 3 × 30 s di P1.5.

La scelta fra le due forme dipende da che cosa il budget rappresenta, non da
quanto è grande. La quadratura è appropriata quando i termini sono incertezze
standard combinabili sotto un'ipotesi probabilistica, per esempio
l'indipendenza; la somma aritmetica è appropriata quando i termini sono limiti
assoluti e si vuole garantire che la combinazione non li superi, senza assumere
compensazioni. I nostri termini sono semi-range osservati, che non sono
automaticamente deviazioni standard: nessuna delle due forme diventa corretta per
il solo fatto di essere applicata a questi valori.

**Decisione rinviata, motivata.** La combinazione resta com'è e non si modifica
silenziosamente. Dopo il pilota di P2.9, valutati i dati e gli effetti a valle,
si decide se mantenerla o introdurne una diversa, con un'analisi di sensibilità
documentata (opzione approvata dall'utente il 24-10-2026). Due vincoli sul rinvio:

- va risolto **prima** della campagna principale, perché `budget_base_w` entra nei
  pesi del fit `w_b = 1/budget_fit_b²` (F.9), nella standardizzazione del
  bootstrap `z_b = r_b/budget_fit_b` (F.14) e nella soglia del gate di P4.5.
  Cambiarlo dopo aver visto i risultati della campagna sarebbe spostare una
  soglia dopo i dati;
- il rinvio non sospende le altre regole: le soglie di P1.6 (1,0 W, 10%, 5/20%)
  restano congelate e non si muovono in nessuno dei due scenari.

Il pilota non determina da solo quale interpretazione sia corretta: fornisce la
variabilità reale dei termini e la stabilità delle conseguenze a valle, ma la
definizione del budget resta una scelta coerente con la natura dell'incertezza
dichiarata.

### P1.8 Cosa è escluso

- energia di caricamento del modello e costo di residenza: la baseline è
  misurata a modello residente e caldo; la v4 misura il costo marginale
  dell'inferenza, non il cold start;
- rete e cloud;
- GPU;
- costo dell'osservatore (si chiude la GUI, non si sottrae).

La calibrazione di produzione avviene una volta per sessione
(`benchmark_unified.py:700-710`) e, con `keep_alive` non inviato di default, lo
stato del modello durante quella calibrazione dipende dal default di Ollama e
dalla storia recente. La v4 misura la baseline a modello residente e caldo, per
scelta. Le due grandezze non sono la stessa cosa e i valori non vanno confrontati
direttamente.

### P1.9 Perché 3×30 s e non una finestra unica da 90 s

- è l'estimatore di produzione, quindi la v4 non introduce due cambi insieme;
- tre repliche danno un controllo di stabilità che una finestra unica non dà;
- l'analisi di sensibilità mostra che la stima della baseline è la parte
  rumorosa: con una baseline unica il CV scende da 8,99% a 2,20%
  (`idle_floor_sensitivity_20261023_analisi.md` §4), quindi la variabilità della
  baseline va misurata, non assunta;
- la scelta della finestra sposta la media di ±4,0–4,8% (§4): la finestra va
  fissata e dichiarata, non decisa a runtime.

### P1.10 Analisi di sensibilità (post-hoc, secondaria)

L'estimatore primario resta quello di P1.1: mediana di tre finestre da 30 s,
`P_pre` applicato, `P_post` diagnostico. Non si introducono come primari
interpolazione, regressione, Kalman, media mobile o modelli per processo:
cambierebbero stimatore e protocollo insieme, e la differenza fra v4 e
produzione non sarebbe più attribuibile al protocollo.

Aggiunta ammessa, dichiarata secondaria e calcolata **dopo** la chiusura dei dati
primari:

```
t_pre_mid    = centro temporale delle tre finestre pre
t_post_mid   = centro temporale delle tre finestre post
P_lin(t)     = P_pre + (P_post − P_pre) · (t − t_pre_mid) / (t_post_mid − t_pre_mid)
E_base_lin,i = Δt_W,i · P_lin(t_mid,W,i)
E_net_lin,i  = E_pkg_gross,i − E_base_lin,i
Δ_sens,i     = E_net_lin,i − E_net_incremental,i
```

Regole:

- `Δ_sens` si riporta in J e in J/token, per punto e per blocco; non sostituisce
  mai il valore primario e non entra nel fit primario;
- se `|Δ_sens| ≤ budget_base_j` del blocco, l'interpolazione non aggiunge
  informazione: il primario è sufficiente. Altrimenti si dichiara la differenza
  e resta il primario;
- l'interpolazione assume drift lineare fra pre e post. Il drift misurato non è
  necessariamente lineare: nel run v3 la baseline va da 13,28 a 12,82 W, con
  `dP = −0,461 W` (`lhm_validation_v3_20261023_185232.md:13,24`), e fra run è
  passata da 13,39 a 12,19 W (`idee_implementative_20261024.md:67`). Per questo
  la sensibilità non arbitra;
- i numeri di drift citati in bozze esterne (+1,2 / −1,5 / +1,8 W) non provengono
  da questo repository e non entrano nella tesi: i riferimenti citabili sono
  quelli ancorati qui sopra.

Stimatori più complessi (regressione su tutta la finestra, Kalman, media mobile,
modello per processo) sono rinviati a una **v5** con validazione dedicata. Senza
misura dell'errore sul nostro hardware sarebbero complessità aggiuntiva, non
miglioramento.

### P1.11 Changelog del metodo di baseline (v1 → v4)

Il metodo non è stato sostituito: è cambiato il **protocollo di campionamento**
attorno allo stesso estimatore `ΔE/Δt`. Cronologia verificata sui file del repo:

| versione | finestre idle | statistica | drift | applicazione |
|---|---|---|---|---|
| v1 (21/10 23:32) | 1 pre, durata agganciata al carico (32–53 s) | lettura singola | non misurato | pre |
| v2 (22/10 00:16) | 1 pre + 1 post, 30 s | media delle due | implicito nei due valori | media pre/post |
| v3 (22/10 01:07; 23/10 15:36 post-fix) | 1 pre + 1 post, 30 s (10 s nel rilancio 18:52) | media | esplicito (`deriva_baseline_*`) | media pre/post |
| v4 (24/10) | 3 pre + 3 post, 30 s | mediana del pre | misurato, post diagnostico | solo pre |

Ancoraggi: v1 `lhm_validation_20261021_233202.md:8,17-30` (una sola fase
`baseline` per run); v2 `lhm_validation_v2_20261022_001626.md:7` e
`lhm_v2replay_console.txt:36` (`P_base_avg`, media A-B); v3
`lhm_validation_v3_20261022_010741.md:7`,
`lhm_validation_v3_20261023_185232.md:7` e `.json:27-28` (campo di deriva).

Non è cambiato: l'estimatore `ΔE/Δt` per finestra, il dominio PKG, il rifiuto
dei delta negativi e la formula `E_net = E_gross − P_base·Δt`. È cambiato il
backend fisico: dal 23/10 il primario è `emi-counter`, con LHM come fallback
(cfr. protocolli v3 rilanciati post-fix).

Perché è cambiato — con i nostri numeri, non con quelli di una bozza esterna:
nel run v3 post-fix la baseline pre va da 9,35 a 18,78 W e la post da 9,42 a
15,15 W, con `dP` per run fra −9,31 e +5,80 W e `P_base` media 11,55 W (CV
22,5%) (`lhm_validation_v3_20261023_153604.md:12-20,24` e colonne `base_a`/
`base_b` del CSV; sintesi in `lhm_validation_v3_postfix_20261023_analisi.md:20-24`).
Non è un drift lento e lineare: è non stazionarietà di fondo della macchina. Da
qui le tre repliche, la mediana e il flag di stabilità di P1.6, e da qui il
limite di P1.10: un'interpolazione pre→post su `dP` di quest'ordine non è
arbitra.

Attenzione ai valori assoluti di v1 e v2 (72–79 "W"): provengono dal percorso di
lettura pre-fix, che integrava la temperatura di package al posto della potenza
(`lhm_validation_v3_postfix_20261023_analisi.md:20-24`). Restano validi come
cronologia del protocollo, non come potenze. I drift `+1,2 / −1,5 / +1,8 W`
citati in bozze esterne non sono di questo repo e non entrano in tesi.

Testo per la tesi (bozza, da adattare):

> Il metodo di calcolo della baseline è evoluto nel corso della sperimentazione
> senza cambiare l'estimatore di base, che resta il rapporto fra energia e
> durata della finestra idle. La versione v1 misurava una sola finestra prima
> del carico; la v2 ha introdotto una finestra anche dopo, applicando la media
> delle due; la v3 ha reso esplicita la deriva fra pre e post; la v4 adotta tre
> finestre consecutive da 30 s per ciascuna fase e applica la mediana del pre,
> riservando il post alla diagnostica. La scelta è motivata dai dati: nella v3
> post-fix la baseline pre varia fra 9,35 e 18,78 W e la deriva per run fra
> −9,31 e +5,80 W, quindi la sola media non basta a stabilizzare il parametro.

### P1.12 Ancoraggi

- estimatore: `energy_session.py:2229-2409`, in particolare `:2363-2396`; floor
  `:2252-2257`; delta negativo `:2383-2387`;
- lettura finestra: `energy_session.py:1576-1645`, con `emi-counter` per EMI;
- formula applicata: `local_energy.py:308-310`;
- sensibilità: `experiment_results/idle_floor_sensitivity_20261023_analisi.md`
  §1–4;
- osservatore: `experiment_results/observer_cost_20261023_analisi.md` §2;
- drift v3: `experiment_results/lhm_validation_v3_20261023_185232.md:13,24` e
  `.json:27-28`; baseline fra run: `experiment_results/idee_implementative_20261024.md:67`;
- instabilità post-fix: `experiment_results/lhm_validation_v3_20261023_153604.md:12-20,24`
  e colonne `base_a`/`base_b` del CSV; sintesi in
  `experiment_results/lhm_validation_v3_postfix_20261023_analisi.md:20-24`;
- changelog v1/v2/v3: `experiment_results/lhm_validation_20261021_233202.md:8,17-30`,
  `lhm_validation_v2_20261022_001626.md:7`, `lhm_v2replay_console.txt:36`,
  `lhm_validation_v3_20261022_010741.md:7`;
- incoerenza nota: `config.py:319` default 10 s contro floor 30 s; la v4 passa
  30 s espliciti e non tocca il default in questo punto.

### P1.13 Aperto

Un solo punto, aggiunto il 24-10-2026: la **forma di combinazione** di
`budget_base_w` — quadratura o somma aritmetica — è una decisione operativa
provvisoria, rinviata alla valutazione dei dati del pilota P2.9 (P1.7). Non è
aperta la formula, che resta congelata e si applica: è aperta la sua
interpretazione, e va chiusa **prima** della campagna principale per i vincoli
elencati in P1.7.

Il resto non è aperto. I numeri 0,5 W (settling), 1,0 W (range) e 10% (drift)
sono soglie operative dichiarate, non costanti scientifiche; restano quelle anche
dopo i dati e in entrambi gli scenari di combinazione. La sensibilità di P1.10 si
esegue in P6, non qui. Il changelog di P1.11 riguarda il protocollo di
campionamento, non l'estimatore. Il riferimento MDPI non leggibile (HTTP 403)
resta escluso e non è un punto aperto: è materiale non citabile finché non
verificato.

### P1.14 Fondamento nella letteratura (verificato 2026-10-24)

**Decisione in una riga.** La sottrazione della baseline, l'uso di più finestre
con controllo degli outlier e la dichiarazione esplicita del termine idle sono
scelte documentate in letteratura; la variante 3 × 30 s con mediana, applicata
solo al pre, è la nostra variante dichiarata, giustificata dai nostri dati e non
da una prescrizione esterna.

| elemento della v4 | fonte verificata | cosa dice davvero | rapporto con la v4 |
|---|---|---|---|
| `E_net = E_gross − P_base·Δt` | Alizadeh & Castor 2024, *Green AI*, arXiv:2402.13640v2, §3 | idle 10 min, media, sottratta per CPU e GPU: "record the GPU power in idle mode for 10 minutes and subtract the average" | conferma il principio della sottrazione; non il numero di finestre né la statistica |
| idem | Vibhoothi et al. 2025, AV1, arXiv:2510.12380, §V | "Active power is calculated by subtracting the idle power of the system from the total power drawn"; la misura dell'idle non è descritta | conferma il principio; non fornisce un protocollo |
| repliche e scarto delle finestre anomale | Panigrahy et al. 2026, arXiv:2605.22883v1, §4.2 | media su più finestre non sovrapposte, campioni oltre 2σ esclusi prima della media | conferma repliche e controllo anomalie; la statistica è la media, non la mediana |
| baseline come termine separato e tracciabile | West et al. 2026, Ichnos+, arXiv:2607.10586v1, §III-C | termine idle aggiunto una sola volta per nodo nei periodi attivi | conferma una baseline esplicita e non annegata; è un'aggiunta al modello, non una sottrazione dal misurato |
| confine di misura | Tschand et al. 2024, MLPerf Power, arXiv:2410.12032 | misura la potenza dell'intero sistema; non prescrive la sottrazione dell'idle | conferma l'obbligo di dichiarare il confine; non supporta la sottrazione |
| controesempio | CodeCarbon 3.3, docs | nessuna sottrazione di idle; canali RAPL/EMI/powermetrics | strumento affermato che non sottrae la baseline: la nostra scelta non è imposta dallo standard di fatto |
| mediana e split pre/post | dati del repo, P1.10–P1.11 | pre 9,35–18,78 W, `dP` −9,31…+5,80 W, CV 22,5% | è la motivazione empirica, non una prescrizione della letteratura |

**Cosa è nostro.** Nessuna delle fonti prescrive tre finestre da 30 s, la
mediana, l'applicazione al solo pre e il post diagnostico. La mediana è preferita
alla media perché con n = 3 una finestra contaminata sposta la media ma non la
mediana; il pre è applicato perché interpolare su un `dP` non stazionario non è
arbitrario (P1.10); il post resta diagnostico per non tarare retroattivamente la
sottrazione. L'estimatore resta quello di produzione
(`energy_session.py:2363-2396`), così la catena di misura non cambia insieme al
protocollo.

**Motivazione causale dell'applicazione al solo pre** (aggiunta il 24-10-2026;
redazionale: non modifica né formule né soglie, rafforza la giustificazione).
La richiesta è l'intervento. `P_pre` è misurata su uno stato della macchina che
la richiesta non ha ancora modificato; `P_post` è misurata su uno stato che la
richiesta ha modificato — è per questo che intorno alle finestre esiste un
settling (P1.5). La grandezza che la sottrazione vorrebbe, la potenza idle
**durante** `Δt_W`, non è osservata: sia il pre sia il post ne sono proxy, ma solo
il pre non è una funzione del trattamento. Condizionare l'estimatore a una
grandezza post-trattamento renderebbe la correzione dipendente dall'esito che deve
correggere. Sotto l'assunzione che il livello idle sia stabile dentro il blocco —
che è esattamente ciò che `pre_unstable` e `r_A` misurano (P1.6) — `P_pre` è la
scelta che non introduce circolarità, mentre `dP` misura quanto quell'assunzione
deriva: informazione sull'assunzione, non una stima migliore dell'idle non
osservato. Per questo il post si registra e non si applica, e la sua distanza dal
pre entra nel budget (F.4) invece di entrare nella correzione.

**Correzioni al materiale esterno.** Il riferimento citato come "Khan et al."
non compare in queste fonti: il lavoro è Alizadeh & Castor 2024. CodeCarbon non
sottrae idle e va citato come contrasto, non come supporto. MLPerf Power non
prescrive un trattamento dell'idle. Ichnos+ aggiunge l'idle una volta, non lo
sottrae. A-LEMS usa la media dopo esclusione a 2σ, non la mediana. AV1 sottrae
l'idle senza descriverne la misura. Il riferimento MDPI 2410-387x/10/4/55
("baseline di 5 min a 50 campioni/s") non è leggibile (HTTP 403) e resta
escluso. La variante 3 × 30 s con mediana, pre applicato e post diagnostico è
coerente e difendibile sui nostri dati, non è "lo standard".

**Testo per la tesi (bozza, da adattare).**

> La sottrazione della potenza idle è una pratica documentata: Alizadeh e Castor
> misurano l'idle per dieci minuti e ne sottraggono la media, per CPU e GPU
> [arXiv:2402.13640v2], e Vibhoothi et al. calcolano la potenza attiva
> sottraendo l'idle dal totale [arXiv:2510.12380]. L'uso di più finestre con
> esclusione degli outlier è adottato da Panigrahy et al., che stimano la
> baseline come media su finestre non sovrapposte scartando i campioni oltre
> due deviazioni standard [arXiv:2605.22883v1]; Ichnos+ tratta l'energia idle
> come termine esplicito aggiunto una volta per nodo [arXiv:2607.10586v1],
> mentre MLPerf Power misura la potenza dell'intero sistema senza prescrivere la
> sottrazione [arXiv:2410.12032] e CodeCarbon non la applica [CodeCarbon 3.3].
> Nessuna di queste fonti prescrive la variante adottata nella v4 — tre finestre
> da 30 s, mediana applicata al solo pre, post diagnostico — che è una scelta
> dichiarata, motivata dalla non stazionarietà misurata nella v3 post-fix
> (baseline pre 9,35–18,78 W, CV 22,5%) e dalla continuità con l'estimatore di
> produzione.

**Ancoraggi letteratura.**

- Alizadeh & Castor 2024: https://arxiv.org/html/2402.13640v2 §3;
- Vibhoothi et al. 2025: https://arxiv.org/html/2510.12380 §V;
- Panigrahy et al. 2026: https://arxiv.org/html/2605.22883v1 §4.2;
- West et al. 2026: https://arxiv.org/html/2607.10586v1 §III-C;
- Tschand et al. 2024: https://arxiv.org/html/2410.12032v1 e
  https://docs.mlcommons.org/mlperf-power/;
- CodeCarbon 3.3: https://docs.codecarbon.io/3.3/explanation/methodology/.

Citazioni in originale; i testi integrali sono stati letti il 2026-10-24.

### P1.15 Confronto con CodeCarbon (verificato 2026-10-24)

**Decisione in una riga.** CodeCarbon 3.3 e CasualWatt v4 non applicano lo
stesso trattamento della baseline: CodeCarbon misura l'energia della macchina e,
in modalità process, ne attribuisce una quota al processo; non misura né
sottrae una baseline idle. CasualWatt misura la baseline con tre finestre pre e
tre post e la sottrae. Il confronto è fra due oggetti diversi, non fra due
versioni dello stesso principio.

| aspetto | CodeCarbon 3.3 | CasualWatt v4 |
|---|---|---|
| grandezza | energia della macchina da RAPL/EMI/powermetrics, o stima da TDP; in modalità process, quota attribuita per tempo CPU (documentazione) | energia del package da EMI/LHM |
| sottrazione della baseline | non definita: "idle" e "baseline" non compaiono né nella documentazione né nel pacchetto 3.3.0 | `E_net = E_gross − P_pre·Δt` |
| misura della baseline | non eseguita | 3 finestre da 30 s prima del blocco |
| statistica | non applicabile | mediana delle tre repliche |
| pre/post | non distinti | pre applicato, post diagnostico |
| drift | non misurato | `dP = P_post − P_pre` esplicito |
| settling e cooldown | non documentati | criteri separati e dichiarati |
| attribuzione al processo | modalità process: stima per tempo CPU; GPU a livello device, non per processo | energia di Ollama attiva + GPU attribuita, quota CPU dichiarata |
| confine | macchina vs processo; PUE e WUE opzionali | package + GPU attribuita; rete e cloud zero nel locale |
| trasparenza | metodo documentato a livello generale, non la baseline | protocollo esplicito e ripetibile |

**Cosa fa CodeCarbon, verificato.** La documentazione 3.3 distingue due
modalità: `machine` misura "the total energy consumed by the whole hardware
stack", `process` "estimates the energy attributable to your Python process ...
by sampling their CPU time relative to total CPU capacity". La stessa pagina
avverte che la potenza GPU "is always measured at the device level", quindi non
è una quota del singolo processo. Nel percorso TDP la potenza di processo è
`power = TDP · carico_normalizzato / 100` (`hardware.py:346`): è un modello
lineare di attribuzione, non una differenza fra due misure; a carico zero vale
zero, ma non perché sia stata misurata e sottratta una baseline. Nel percorso
RAPL/EMI l'energia viene dai delta del contatore della macchina
(`hardware.py:381-393`) e viene accumulata così com'è
(`emissions_tracker.py:1180-1183`), senza applicare la quota di processo: nel
codice 3.3.0 il percorso che calcola la quota è quello TDP.

La verifica negativa è stata fatta sul pacchetto Python 3.3.0: `grep -rniE
"\bidle\b|baseline" codecarbon --include=*.py` non restituisce alcuna
occorrenza. Non è un silenzio della documentazione: nel codice non c'è un
termine idle da documentare.

**Perché la differenza è di oggetto.** CodeCarbon in modalità process risponde a
"quanta energia attribuire a questo processo?", ripartendo il consumo della
macchina in base al tempo di CPU. CasualWatt risponde a "quanta energia
incrementale ha consumato questa richiesta rispetto a una macchina idle
misurata?", sottraendo una baseline. Le due domande non sono annidate: una quota
si calcola senza mai misurare l'idle; una differenza si calcola senza attribuire
il consumo a un processo. La prima è sensibile al carico concorrente, la seconda
alla stabilità della baseline. Per questo "entrambi sottraggono l'idle" è falso,
e "CasualWatt è più esplicito" è vero ma insufficiente: cambia l'estimatore e
cambia l'unità sperimentale.

**Correzioni al materiale esterno.**

- "CodeCarbon sottrae l'energia idle in modo implicito" → no: non la misura e
  non la sottrae. La quota di processo può sembrare una sottrazione implicita
  perché a carico zero la stima TDP è zero, ma è un modello di attribuzione.
- "Misura idle dipendente dalla piattaforma" → non c'è una misura idle; ciò che
  dipende dalla piattaforma è il canale energetico (RAPL, EMI, powermetrics,
  TDP).
- "Statistica non documentata come mediana" → non c'è una statistica della
  baseline da documentare.
- "Pre/post non distinto", "drift non misurato", "settling e cooldown non
  documentati" → veri, ma vanno detti come "non previsti dal metodo", non come
  omissioni di uno stesso protocollo.
- "Attribuzione al processo sì (machine vs process)" → vero secondo la
  documentazione, con la precisazione che la GPU resta a livello device e che il
  percorso RAPL/EMI restituisce l'energia della macchina.

**Testo per la tesi (bozza, da adattare).**

> CodeCarbon 3.3 e CasualWatt v4 non adottano lo stesso trattamento della
> baseline. CodeCarbon misura l'energia della macchina tramite RAPL, EMI o
> powermetrics, oppure la stima dal TDP, e in modalità process attribuisce al
> processo una quota del consumo in base al tempo di CPU; la documentazione non
> definisce una baseline idle e il termine "idle" non compare nel pacchetto
> 3.3.0. CasualWatt v4, invece, misura esplicitamente la potenza idle del
> package con tre finestre da 30 s prima e dopo ogni blocco, applica la mediana
> del pre e usa il post come diagnostica del drift. Il confronto non riguarda
> quindi due implementazioni dello stesso principio, ma due oggetti diversi:
> un'attribuzione di quota e una differenza fra energie misurate. La
> trasparenza di CasualWatt consiste nel rendere ripetibile e verificabile la
> stima della baseline, non nel rendere esplicito un passaggio che CodeCarbon
> compirebbe in modo implicito.

**Ancoraggi.**

- CodeCarbon 3.3, metodologia:
  https://docs.codecarbon.io/3.3/explanation/methodology/ (modalità machine e
  process, canali RAPL/EMI/powermetrics/TDP, GPU a livello device);
- pacchetto 3.3.0, `codecarbon/external/hardware.py:292-346` (attribuzione di
  processo nel percorso TDP), `:381-393` (delta RAPL/EMI),
  `codecarbon/emissions_tracker.py:1180-1183` (accumulo dell'energia);
- verifica negativa: `grep -rniE "\bidle\b|baseline" codecarbon --include=*.py`
  → 0 occorrenze nel pacchetto 3.3.0.

---

## P2 — Token effettivi e terminazione

### P2.1 Decisione in una riga

Le coordinate della v4 sono i token **realmente contati da Ollama**
(`prompt_eval_count`, `eval_count`); i target sono solo nominali, le stime non
entrano nel dataset primario, e il motivo di terminazione (`done_reason`) è un
campo obbligatorio che distingue tetto raggiunto da EOS naturale.

### P2.2 Perché

La produzione legge i contatori ma, se uno è zero, sostituisce in silenzio una
stima con tiktoken o `len//4` e lascia solo una nota (`benchmark_unified.py:173-179`,
`:226-232`). Sono due definizioni di token nella stessa colonna: una misurata e
una stimata. La v4 non può fonderle, perché il fit attribuisce energia a un
numero di token.

I dati mostrano che target e actual non coincidono. Nel run v3 post-fix, 15
inferenze con `num_predict=128` producono 1302–1429 token di uscita per run, cioè
87–95 per richiesta: il tetto non è raggiunto nella maggior parte dei casi
(`lhm_validation_v3_20261023_153604.csv`, fase `load`; md `:5`). Nel run 18:52 la
geometria dichiarata era `N_in=64`, `N_out=128` e i valori reali sono 378 e 352
su 3 inferenze (126 in, 117 out): 2× il target in ingresso
(`lhm_validation_v3_20261023_185232.csv:2`, md `:6`). Il target è una richiesta
al costruttore del prompt, non una coordinata.

`done_reason` non è letto da nessuna parte nel repo (nessuna occorrenza di
`done_reason` in `cwEnergyModular/`) e `num_ctx` non è mai impostato
(`benchmark_unified.py:132-141`): senza il primo non si distingue una
generazione troncata dal tetto da una conclusa dal modello, senza il secondo una
truncazione del contesto sarebbe invisibile.

### P2.3 Definizioni

```
N_in_actual,i      = prompt_eval_count_i
N_out_actual,i     = eval_count_i
N_total_actual,i   = N_in_actual,i + N_out_actual,i        # solo descrittivo
num_predict,i      = n_output_tokens_target                # vincolo, non misura
dev_in_pct,i       = 100 · (N_in_actual,i − n_input_tokens_target) / n_input_tokens_target
dev_out_pct,i      = 100 · (N_out_actual,i − n_output_tokens_target) / n_output_tokens_target
J/token_pkg,i      = E_net_incremental,i / N_out_actual,i   # richiede N_out_actual ≥ 1
```

`N_total_actual` non è mai un denominatore. `dev_in_pct` e `dev_out_pct` sono
descrittivi: misurano quanto il costruttore del prompt ha centrato il target, non
sono criteri di validità.

### P2.4 Terminazione

`done_reason` si registra grezzo, insieme a una classe:

| `done_reason` | classe | condizione | trattamento |
|---|---|---|---|
| `length` | `cap_reached` | `N_out_actual = num_predict` | valido, controllato |
| `length` | `termination_inconsistent` | `N_out_actual ≠ num_predict` | richiesta invalida |
| `stop` | `eos` | `N_out_actual < num_predict` | valido, marcato `early_stop` |
| `stop` | `eos_at_cap` | `N_out_actual = num_predict` | valido, non è early stop |
| altro o assente | `termination_missing` | — | richiesta invalida |

```
early_stop = (done_reason == "stop" and N_out_actual < num_predict)
```

L'early stop **non è un errore e non si esclude**: il punto resta nel fit alle
coordinate reali. La ragione è nei numeri di P2.2: gli stop anticipati sono la
maggioranza, e scartarli eliminerebbe la maggior parte dei dati proprio alle
`N_out` basse. `cap_reached` è il caso controllato; `eos` è il comportamento del
modello e va descritto, non corretto.

### P2.5 Validità e anomalie

Una richiesta è valida se e solo se:

- `prompt_eval_count ≥ 1` e `eval_count ≥ 1`, entrambi presenti;
- `done_reason` presente e in `{stop, length}`, con la coerenza di P2.4;
- `N_out_actual ≤ num_predict`;
- `N_in_actual + N_out_actual ≤ num_ctx`;
- nessuna stima di token usata (`tokens_estimated = false`).

Flag che non invalidano: `early_stop`, `cap_reached`, `eos_at_cap`. Motivi di
invalidità: `tokens_missing`, `termination_missing`, `termination_inconsistent`,
`counter_inconsistent` (`N_out_actual > num_predict`), `context_boundary`. Una
richiesta invalida resta nel CSV grezzo con il motivo; non entra nel dataset
primario e non si sostituisce con una stima.

### P2.6 Niente stime nel percorso primario

La v4 non chiama `_estimate_tokens` (`benchmark_unified.py:101-116`). Se un
contatore manca, la richiesta è invalida: non esiste un ramo "stima e prosegui".
Il percorso legacy resta com'è; la colonna `tokens_estimated` esiste per
dimostrare che nel dataset v4 è sempre `false`.

### P2.7 Contesto dichiarato

`num_ctx = 8192`, inviato esplicitamente in `options` e registrato nel run
metadata. Il massimo del disegno è `2048 + 512`; 8192 lascia margine anche al
caso osservato di `N_in` reale doppio del target (P2.2). La guardia
`N_in_actual + N_out_actual ≤ num_ctx` è per riga, perché Ollama tronca l'input
per farlo stare nel contesto e `prompt_eval_count` riporterebbe la lunghezza
troncata senza dichiararlo (opzione `truncate` nella specifica).

### P2.8 Identità del prompt e cache

Ogni richiesta porta un **nonce univoco all'inizio** del prompt, a larghezza
fissa, e si registrano `prompt_nonce` e `prompt_sha256`. Così nessuna coppia di
richieste condivide un prefisso byte-identico e `N_in_actual` è l'intero prompt,
non la parte non ancora in cache. La ragione è che un riuso del prefisso KV
cambierebbe il costo attribuito a `N_in` senza cambiare `N_in_actual`: il modello
geometrico vedrebbe un input che non è stato pagato.

Il nonce è obbligatorio anche se il pilot di P2.9 mostrasse che il contatore non
cambia: il suo costo è trascurabile e la regola non dipende da una versione del
server. Il pilot serve a documentare l'entità dell'effetto, non a decidere se
applicare la regola.

### P2.9 Pilot obbligatorio prima della campagna

Tre prove, eseguite sullo stesso host e con la stessa versione di Ollama che farà
la campagna; non consumano richieste del disegno e non entrano nel dataset.

- **A — semantica di `done_reason`**: due richieste con `num_predict` piccolo che
  saturano il tetto (atteso `length` e `N_out_actual = num_predict`) e una con
  prompt corto che induce EOS (atteso `stop`). Se `done_reason` manca o non
  distingue i due casi, la campagna **non parte**.
- **B — cache**: 3 richieste identiche contro 3 con nonce iniziale, a `N_in`
  medio e `num_predict = 1` per isolare il prefill; si confrontano
  `prompt_eval_count` e `prompt_eval_duration`. È descrittivo: quantifica il
  riuso, non cambia la regola di P2.8.
- **C — contesto**: una richiesta al massimo `N_in` del disegno, con
  `num_ctx = 8192`; si verifica che `prompt_eval_count` corrisponda al prompt
  costruito e che la guardia di P2.7 non scatti.

### P2.10 Cosa non è deciso qui

Il costruttore del prompt, la griglia `N_in × N_out` e i valori target sono P3;
le regole di copertura e di extrapolazione sono P4; i nomi finali delle colonne
sono P5. P2 fissa solo la semantica dei token, la terminazione e la validità.

### P2.11 Ancoraggi

- contatori e stima silenziosa: `benchmark_unified.py:170-179`, `:218-232`;
  stimatore: `:101-116`;
- payload senza `num_ctx`: `benchmark_unified.py:132-141`;
- durate di fase: `benchmark_unified.py:187-188`, `:233-234`;
- colonne token esistenti: `casualwatt_csv_export.py:28`
  (`input_tokens`, `output_tokens`, `total_tokens`);
- `done_reason` assente dal codice: grep su `cwEnergyModular/` senza occorrenze;
- actual vs target: `lhm_validation_v3_20261023_153604.csv` fase `load` colonne
  `tokens_in`/`tokens_out` e md `:5,12-20`; `lhm_validation_v3_20261023_185232.csv:2`
  e md `:6`;
- specifica Ollama: `docs/api.md`, esempio di risposta con `done_reason` e
  opzione `truncate` (`https://github.com/ollama/ollama/blob/main/docs/api.md`).

### P2.12 Aperto

Niente per P2. Il pilot di P2.9 è un cancello di esecuzione, non una decisione
ancora aperta: se fallisce, si ferma la campagna e si corregge il client, senza
cambiare le regole qui sopra.

---

## P3 — Geometria, modello e stima

### P3.1 Decisione in una riga

La v4 stima la superficie `E_act = E0 + a·N_in + b·N_out + c·N_in·N_out` su una
griglia 3×3 con punto minimo e centro replicato, usando i token reali di P2 e la
baseline di P1; l'unità del fit è il blocco, la validazione è su due punti fuori
griglia mai usati nel fit, e la baseline non entra mai come punto del modello.

| decisione | contenuto congelato |
|---|---|
| D1 | variabile dipendente `E_act = E_net_incremental` |
| D2 | modello lineare nei parametri con interazione, primario |
| D3 | unità del fit = blocco, non richiesta singola |
| D4 | pesi conservativi da P1.6–P1.7, non inverse varianze |
| D5 | diagnostica completa, `R²` non è criterio |
| D6 | validazione su punti fuori griglia, mai nel fit |
| D7 | criterio ≤ 10% e dentro l'intervallo bootstrap al 95% |
| D8 | baseline P1 separata dal punto minimo (8,4) |
| D9 | griglia 32/128/512 × 32/128/256 |
| D10 | `m = 3` richieste per blocco, 3 batch temporali |

### P3.2 Variabile dipendente

`E_act` è un sinonimo dichiarato di `E_net_incremental` (P1.3); non è una
seconda grandezza. Per la richiesta `i` del blocco `b`:

```
E_act,i = E_pkg_gross,i − P_pre,b · Δt_W,i
```

`P_pre,b` è la mediana delle tre finestre pre del blocco (P1.3), la stessa per
tutte le richieste del blocco. `E_act` **non viene troncata a zero**: i valori
negativi restano nel dataset con il flag `negative_increment` (P1.6). La
produzione attuale tronca (`local_energy.py:310`); la v4 non lo fa, e la
differenza è dichiarata.

### P3.3 Modello

La superficie è **lineare nei parametri**; il termine `c·N_in·N_out` è
un'interazione bilineare, non un termine quadratico. Non si aggiungono `N_in²` o
`N_out²`.

```
E_act,i = E0 + a·N_in,i + b·N_out,i + c·N_in,i·N_out,i + ε_i
```

- `E0`: overhead fisso per richiesta a modello residente;
- `a`: J/token di prefill marginale;
- `b`: J/token di decode marginale;
- `c`: interazione, attesa ≥ 0 perché la KV cache cresce con `N_in` e ogni token
  di decode legge un contesto più lungo.

Il modello con interazione è il **primario** ed è congelato. Il modello ridotto
`E0 + a·N_in + b·N_out` si riporta solo come sensibilità, con F-test sui minimi
quadrati pesati; non sostituisce il primario dopo aver visto i dati. Non si
introducono altri termini o stimatori in v4.

`E0` è un'estrapolazione a `(0,0)`: il punto minimo `(8,4)` la vincola ma non la
identifica. Per questo si riporta con il suo intervallo. Se l'intervallo include
valori negativi, il punto è marcato `intercept_nonphysical` e si riporta; non si
vincola il fit e non si cambia modello.

### P3.4 Interpretazione dei coefficienti

Al punto di riferimento `(N_in,ref, N_out,ref)`:

```
E_model(ref)        = E0 + a·N_in,ref + b·N_out,ref + c·N_in,ref·N_out,ref
J/token_ref         = E_model(ref) / N_out,ref
∂E/∂N_out (ref)     = b + c·N_in,ref
∂E/∂N_in  (ref)     = a + c·N_out,ref
share_E0(ref)       = E0 / E_model(ref)
```

Due riferimenti predeclarati, entrambi sulla griglia:

- `(32, 32)`: punto corto, vicino alla geometria di produzione;
- `(128, 128)`: centro della griglia.

`J/token_32` e `J/token_128` sono valori **fitted**, non stime indipendenti: il
loro intervallo include l'incertezza dei parametri, non l'errore di validazione.
La validazione è separata (P3.10). `share_E0` dice quanto il punto corto è
dominato dall'overhead; se è grande, un J/token a 32 token non è confrontabile
con uno a 128.

### P3.5 Disegno

| punto | `N_in` target | `N_out` target | blocchi | nel fit |
|---|---|---|---|---|
| griglia 3×3 | 32, 128, 512 | 32, 128, 256 | 3 per cella (27) | sì |
| centro | 128 | 128 | 6 totali (3 in griglia + 3 extra) | sì |
| minimo | 8 | 4 | 3 | sì |
| conferma operativa | 12 | 32 | 3 | no |
| conferma alta | 256 | 192 | 3 | no |

Totale: 39 blocchi, 117 richieste. Il fit usa 33 blocchi (10 punti: 9 celle +
minimo, con il centro a 6); la conferma usa 6 blocchi (2 punti × 3) e non entra
mai nella stima. La baseline P1 **non è un punto del modello**: non è una
richiesta e non contiene `E0`. Il punto minimo `(8,4)` è una richiesta reale e
serve ad ancorare `E0`, non si chiama "floor".

Il punto di conferma `(12,32)` copre la geometria operativa reale (~12 token in,
~32 out) e non è sulla griglia; `(256,192)` testa la regione alta. La griglia da
sola non basta a coprire l'operatività: per questo la conferma include `(12,32)`.

### P3.6 Batch temporali e ordine

La campagna è divisa in **3 batch temporali**. Ogni batch contiene un blocco per
ciascuno dei 12 punti (9 celle + minimo + 2 conferme) più un blocco centrale
extra: 13 blocchi per batch, 39 in totale. L'ordine dei blocchi è randomizzato
dentro ogni batch; `batch_id` e `order_index` sono registrati. Il disegno è
bilanciato rispetto al tempo: ogni punto compare una volta per batch, così una
deriva lenta non si concentra su un punto. L'effetto di batch si controlla nei
residui e, come sensibilità, con un modello che aggiunge `batch` come fattore
fisso; il modello primario resta quello di P3.3.

### P3.7 Blocchi, richieste e baseline

Ogni blocco contiene `m = 3` richieste della stessa cella, eseguite
back-to-back. Ogni richiesta ha un **nonce unico all'inizio del prompt** (P2.8),
quindi le tre richieste non sono identiche e non riusano il prefisso in cache.
Le tre condividono `P_pre,b`; la baseline è misurata una volta per blocco.

Sequenza di un blocco:

```
warm-up (escluso dal dataset)
→ settling secondo P1.6
→ 3 finestre idle da 30 s (pre)
→ 3 richieste della cella
→ 3 finestre idle da 30 s (post)
```

L'unità del fit è il **blocco**, non la richiesta. Per il blocco `b`:

```
Ē_b   = (1/m) Σ_i E_act,i
x1_b  = (1/m) Σ_i N_in,i
x2_b  = (1/m) Σ_i N_out,i
x12_b = (1/m) Σ_i N_in,i · N_out,i
```

`x12_b` è la media dei prodotti, non il prodotto delle medie: così la
linearizzazione del modello resta esatta anche con i nonce di lunghezza
leggermente diversa.

I controlli di P1.6 si applicano al blocco: `pre_unstable`,
`baseline_unstable`, `negative_increment`, `r_A`, `r_B`. Un punto con `r_B`
10–20% resta nel fit con il peso ridotto che deriva dal budget di P1.7; oltre
20% è escluso dal fit primario e riportato in sensibilità. Due blocchi su tre
marcati `baseline_unstable` invalidano la campagna, non solo il punto.

### P3.8 Stima

Il modello si stima sui 33 blocchi del fit con minimi quadrati pesati:

```
min_{E0,a,b,c} Σ_b w_b · (Ē_b − E0 − a·x1_b − b·x2_b − c·x12_b)²
w_b = 1 / budget_b²
budget_b² = u_base,b² + u_within,b²
u_base,b   = Δt̄_W,b · budget_base_w,b          # comune alle m richieste
u_within,b = semi-range(E_act,i)                # non diviso per √m
```

`budget_base_w,b` è quello di P1.7; `u_base,b` non si divide per `m` perché
l'errore di baseline è comune alle tre richieste, e `u_within,b` non si divide
per `√m` perché non si assume l'indipendenza delle tre richieste. `budget_b` è
un **budget conservativo**, non una deviazione standard; `w_b` è un peso
conservativo, non un peso di precisione. Se `budget_b = 0`, si usa peso uguale e
si marca il blocco.

La stima primaria è la WLS; la OLS non pesata è la sensibilità. Gli errori
standard sono HC3; gli intervalli dei coefficienti vengono da un bootstrap
stratificato per punto (2000 repliche, blocchi ricampionati dentro ogni punto),
che preserva il disegno. Il bootstrap per batch non si usa: con 3 batch ha troppi
pochi cluster.

### P3.9 Diagnostica

- residui vs fitted, vs `N_in`, vs `N_out`, vs `order_index`, vs `batch_id`;
- QQ-plot e scala-locazione;
- lack-of-fit: confronto tra la superficie e il modello a medie di cella
  (10 punti, 33 blocchi) con F-test sui minimi quadrati pesati; se il test è
  significativo, la superficie è inadeguata e si dichiara;
- intervalli dei coefficienti e loro ampiezza;
- `R²` aggiustato, errore residuo e AIC OLS come diagnostica, mai come criterio
  di accettazione: `R² ≥ 0,9` non basta;
- distanza di Cook: i blocchi influenti si riportano, non si eliminano senza
  dichiararlo;
- segno e ampiezza di `E0`, con il flag `intercept_nonphysical` se serve.

### P3.10 Validazione

I due punti di conferma sono misurati nella stessa campagna ma **esclusi dalla
stima**; l'analisi li apre solo dopo che la specifica è congelata e i
coefficienti sono stimati sui soli blocchi di fit. Per ciascun punto, con i 3
blocchi:

```
E_meas  = media dei 3 blocchi
E_pred  = modello ai parametri stimati
err_rel = |E_meas − E_pred| / E_pred
u_conf  = semi-range(E_meas,1..3)                   # non diviso per √3
intervallo = [q2.5 − 2·u_conf, q97.5 + 2·u_conf]   # quantili bootstrap della previsione
```

La validazione passa se `err_rel ≤ 10%` **e** `E_meas` è dentro l'intervallo.
Il 10% è la stessa scala della sensibilità della baseline (1 W ≈ 6–11% di
J/token), non una soglia scientifica. Se fallisce, si dichiara il fallimento:
non si rifà il fit sui punti di conferma e non si sceglie un altro modello sui
dati di validazione. In quel caso `J/token` resta quello del modello, marcato
`validation_failed`, e si riporta anche il rapporto descrittivo del blocco di
produzione (P6).

### P3.11 Metriche

- primarie: `J/token_32` e `J/token_128` (P3.4), con intervallo bootstrap;
- coefficienti `a`, `b`, `c`, `E0` con intervalli;
- costi marginali `b + c·N_in,ref` e `a + c·N_out,ref`;
- `share_E0` ai due riferimenti;
- descrittiva: `E_act/N_out_actual` per richiesta (mediana, IQR, range), non
  come stima primaria;
- J per risposta corretta: fuori da P3 se `eval_mode=skip`; resta una metrica
  della tesi da altri blocchi, non si calcola qui.

### P3.12 Esecuzione dei blocchi di geometria

- modello `llama3.2:3b`, stesso digest e stessa versione di Ollama della
  campagna; digest, versione e `num_thread` registrati;
- `keep_alive = -1` (P1.4), `num_ctx = 8192` (P2.7), `stream = false`;
- `num_predict = N_out_target` per i blocchi di geometria: l'output è troncato
  dal tetto, `done_reason = length` e `N_out_actual = num_predict` (P2.4);
- ogni richiesta ha un nonce unico (P2.8); il prompt è costruito per un `N_in`
  target con tolleranza ±5%, calibrato in un pre-pilota che non entra nel
  dataset;
- se una richiesta di geometria termina con EOS prima del tetto, la misura resta
  valida per P2 ma **non è assegnabile alla cella**: è `design_deviation`, si
  sostituisce e si registra; non si cambia il target;
- la temperatura è quella di produzione, registrata e non trattata come fattore;
- il blocco di produzione (prompt reali, EOS naturale) è P6 e non entra nel fit
  della superficie: la superficie descrive il costo di decode, non la
  distribuzione dei task.

**Testo per la tesi (bozza, da adattare).**

> La geometria della v4 è modellata con una regressione lineare nei parametri e
> con un termine di interazione fra token di input e output, coerente con la
> crescita della KV cache durante il decoding. L'unità del fit è il blocco, con
> un solo valore di baseline per blocco, e la validazione avviene su due punti
> fuori griglia mai usati nel fit, uno dei quali copre la geometria operativa
> reale. La baseline di P1 non entra nel modello, perché non è una richiesta e
> non contiene l'overhead fisso `E0`. I token sono quelli realmente contati da
> Ollama; le richieste di geometria sono troncate al tetto per garantire
> l'appartenenza alla cella, mentre il blocco di produzione usa la terminazione
> naturale.

### P3.13 Cosa non è deciso qui

P4 fissa le regole generali di copertura e extrapolazione e il budget di
incertezza completo; P3 fissa solo i punti e il criterio di validazione della
superficie. P5 fissa i nomi e i tipi delle colonne CSV; qui si elencano solo i
contenuti obbligatori: `batch_id`, `block_id`, `point_id`, target e actual dei
token, `done_reason`, `early_stop`, `prompt_nonce`, `model_digest`,
`ollama_version`, `temperature`, `num_ctx`, `num_predict`, `order_index`, `r_A`,
`r_B`, `negative_increment`, `pre_unstable`, `baseline_unstable`,
`design_deviation`. P6 esegue e analizza.

### P3.14 Ancoraggi

- payload e opzioni: `benchmark_unified.py:119-141`;
- contatori e stime: `benchmark_unified.py:170-179`, `:218-232`;
- metrica esistente: `benchmark_unified.py:509-516`
  (`energy_per_output_token_j`);
- formula applicata e troncamento di produzione: `local_energy.py:308-310`;
- incertezza e pesi: P1.6–P1.7; token e terminazione: P2.3–P2.8;
- colonne token esistenti: `casualwatt_csv_export.py:28`;
- specifica Ollama per `num_predict`, `num_ctx`, `keep_alive`, `done_reason`:
  `https://github.com/ollama/ollama/blob/main/docs/api.md`.

### P3.15 Aperto

Niente per P3. Il pre-pilota verifica solo la fattibilità dei livelli (512 input,
256 output, prompt che sostengono la generazione): se un livello non è
raggiungibile, P3 si riapre e si dichiara; non si cambia il livello in silenzio.
Il fallimento della conferma è un risultato di P6, non una decisione aperta.

---

## P4 — Incertezza e validazione

**Congelato 2026-10-24.** P4 completa P1 e P3: fissa il budget di incertezza di
un numero pubblicato, le fasce di copertura della superficie, la costruzione
dell'intervallo di previsione e il test della sottrazione di baseline. Non cambia
l'estimatore di baseline (P1.1), né il modello (P3.3), né il disegno (P3.5), né
i pesi del fit (P3.8).

Stesura: una prima versione è stata congelata e committata (`c41a6ec`) con fasce di
copertura a rettangolo e case bootstrap; è stata emendata lo stesso giorno sulle
quattro decisioni approvate — inviluppo convesso per la copertura, bootstrap dei
residui standardizzati, criterio monolitico di catena, `u_edge` solo nel budget
predittivo e in sensibilità (`d9e4af1`). La versione qui sotto è quella emendata,
ed è quella che vale.

Seconda emenda, stessa giornata, su valutazione della struttura di P4 proposta in
`bozza p4.DOCX`: nessuna decisione è cambiata. Sono entrate due sole aggiunte di
forma, entrambe richieste esplicitamente e nessuna delle quali tocca P1, P2, P3 o
i pesi del fit: (i) P4.1 apre con la formulazione secca in quattro clausole,
quella proposta, e il testo precedente resta come dettaglio; (ii) il disegno di
P4.4 passa da elenco puntato a otto requisiti numerati, e la struttura di
baseline 3 pre + 3 post sui blocchi di controllo — che prima era un inciso —
diventa il requisito 7 con la ragione per cui è obbligatorio: senza di essa `r_A`,
`budget_base_j,c` e `budget_base_w,c` non esistono sul blocco di controllo e il
criterio di P4.5 non è calcolabile. P4.5 ora cita quel requisito. I tre punti
della struttura proposta che erano in conflitto con le decisioni approvate
(`u_edge` dentro il budget di fit e senza il fattore 2, inviluppo a cinque vertici
con `(32,32)`, catena costruita sui confronti di coerenza same-counter invece che
sui gate di campagna) **non** sono stati adottati: la valutazione è in chat e le
ragioni restano quelle di P4.6, P4.7 e P4.9–P4.10.

### P4.1 Decisione in una riga

P1 resta operativo così com'è; la validazione della sottrazione è un test
separato, non una modifica dell'estimatore; il budget di un numero pubblicato
aggiunge il termine di bordo ai due contributi già dichiarati; copertura e
intervallo accompagnano ogni numero — la copertura come campo
(`coverage_tier`, `hull_margin_tok`), l'intervallo come numero con il suo budget
— e non come aggettivo nel testo.

Nel dettaglio: ogni numero pubblicato della v4 esce con tre cose: il budget
predittivo `budget_pred = sqrt(u_base² + u_within² + u_edge²)`, la fascia di
copertura A/B/C decisa sull'inviluppo convesso del disegno, e — per la differenza
incrementale — l'esito del test load-versus-control. La sottrazione di baseline è
validata su questa macchina se il bias misurato a incremento nullo sta dentro il
budget; se non ci sta, il bias si dichiara, si aggiunge al budget, e P1 non cambia
senza nuova evidenza. La parola "validata" sull'intera misura si usa solo se tutti
gli anelli di P4.9 passano: altrimenti si scrive quale anello ha ceduto.

### P4.2 Perché serve un punto separato

P1.7 dichiara il solo contributo di baseline e P3.8 dichiara i pesi del fit:
nessuno dei due è l'incertezza di un numero pubblicato. Mancano tre pezzi.

1. **Il bordo della finestra.** I bordi cadono quasi sempre fra due campioni e
   il contatore cumulativo è interpolato linearmente
   (`energy_session.py:1103-1124`). Su finestre di pochi secondi, con una cadenza
   reale di 0,28–0,34 s, questo termine non è trascurabile e finora non era
   scritto da nessuna parte.
2. **La copertura.** I 10 punti di disegno (P3.5) non riempiono nessun rettangolo:
   con il punto minimo `(8,4)` la regione coperta è un poligono, e usare il box
   avrebbe fatto passare per interpolazione quella che è extrapolazione. P3.13
   rimandava qui le regole.
3. **Il bias della sottrazione.** Nessun confronto fra due letture dello stesso
   registro può arbitrarlo: LHM, EMI e SRUM leggono tutti
   `MSR_PKG_ENERGY_STATUS`. Serve un test a incremento nullo per costruzione.

### P4.3 Definizioni

| termine | simbolo | definizione |
|---|---|---|
| blocco di carico | — | blocco con le `m = 3` richieste di inferenza (P3.7) |
| blocco di controllo | — | blocco identico per struttura, stato macchina e durata, **senza alcuna richiesta** |
| bias di sottrazione | `bias_w` | incremento netto medio dei blocchi di controllo, in watt; atteso zero per costruzione |
| termine di bordo | `u_edge,b` | `2 · P_peak,b · δt_edge,b`, incertezza dell'interpolazione lineare ai due bordi della finestra, in joule |
| budget di fit | `budget_fit,b` | il `budget_b` di P3.8, rinominato: è ciò che pesa i blocchi nel fit |
| budget predittivo | `budget_pred,b` | `sqrt(budget_fit_b² + u_edge,b²)`: accompagna ogni numero pubblicato |
| fascia di copertura | A / B / C | dentro l'inviluppo convesso del disegno / dentro il box ma fuori dall'inviluppo / fuori dal box |
| margine di inviluppo | `hull_margin_tok` | distanza in token dal bordo dell'inviluppo, negativa se fuori |
| stato della catena | `chain_status` | `validated` solo se tutti gli anelli di P4.9 passano; altrimenti l'etichetta dell'anello ceduto |

### P4.4 Campagna di validazione load-versus-control

Provenienza: `baseline miglioramenti.DOCX` §3, "Livello 2" — materiale utente,
valutato contro P1. Le sue raccomandazioni sulla nomenclatura del semi-range,
sulla registrazione delle tre repliche e sulla separazione dei tre valori erano
già congelate (P1.7, P1.5 passo 3, P1.3); la campagna di controllo invece è
nuova ed è l'unico test **diretto** della sottrazione.

Disegno. I requisiti sono numerati perché P4.5 fa riferimento per numero al
requisito 7: non è una lista di buone intenzioni, è l'elenco di ciò che rende il
test calcolabile.

1. **Campagna separata, eseguita come gate.** La campagna precede la campagna
   principale. Se il gate non passa, la campagna principale parte comunque ma con
   `bias_declared` e con `u_bias` dentro `budget_pred`: è la conseguenza di P4.5
   e dell'anello 4 di P4.9, non una regola nuova di questo punto.
2. **Tre coppie.** Ogni coppia = 1 blocco di carico + 1 blocco di controllo.
3. **Ordine randomizzato, seed registrato.** Ordine dentro la coppia e ordine
   delle coppie randomizzati; il seed va in `order_seed`.
4. **Geometria operativa.** Il punto di conferma `(12,32)` di P3.5, cioè la
   geometria operativa reale, con terminazione naturale come nel blocco di
   produzione.
5. **Durata fissata prima.** `dt_nominal_s` è fissato **prima** della campagna
   come 3 × la mediana della durata di richiesta misurata nel pilota di P2. Il
   blocco di controllo attende quella durata senza inviare richieste. Lo scarto
   fra nominale e misurato non crea bias: ciascun blocco sottrae `P_pre · Δt_W`
   con il **proprio** `Δt_W` misurato, quindi l'atteso del controllo è zero per
   ogni durata.
6. **Stato macchina identico a P1.4.** `keep_alive = -1`, modello residente e
   caldo, GUI di LibreHardwareMonitor chiusa, processi concorrenti dichiarati.
7. **Struttura di baseline identica su entrambi i tipi di blocco.** Tre finestre
   pre da 30 s e tre post da 30 s, come in P1.5, **anche** sul blocco di
   controllo. Non è una simmetria formale: è ciò che rende calcolabili su quel
   blocco `baseline_pre_w`, `baseline_post_w` e quindi `dP`, `budget_base_w`,
   `budget_base_j`, `r_A` e `r_B` (P1.5, P1.6, P1.7), e sono esattamente le
   quantità che il criterio di P4.5 usa — filtro sui blocchi con `r_A ≤ 10%`,
   confronto per blocco con `budget_base_j,c`, confronto aggregato con
   `mediana_c(budget_base_w,c)`. Un blocco di controllo senza struttura pre/post
   produrrebbe un `E_net` privo di `P_pre` e non confrontabile con nessun budget,
   cioè inutilizzabile. Il requisito vale per costruzione anche sul blocco di
   carico della coppia, che è un blocco di produzione a tutti gli effetti.
8. **Stessa procedura di produzione.** Per ciascun blocco di controllo si calcola
   `E_net,control = E_pkg_gross − P_pre · Δt_W`, con lo stesso codice di
   produzione e senza troncamento.

### P4.5 Criterio del test

Il criterio è calcolabile solo in virtù del requisito 7 di P4.4: `r_A`,
`budget_base_j,c` e `budget_base_w,c` esistono su un blocco di controllo perché
quel blocco esegue la stessa struttura di baseline 3 pre + 3 post dei blocchi di
carico.

```
per blocco:  passa se  |E_net,control,c| ≤ budget_base_j,c              (P1.7)
aggregato:   bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c
             sui soli blocchi con r_A ≤ 10%                              (P1.6)
             passa se  |bias_w| ≤ mediana_c(budget_base_w,c)
```

- **Se passa**: la sottrazione di P1 è validata su questa macchina nel senso
  dichiarato in P4.9–P4.10 — anello 4 della catena, non scala assoluta — e
  `u_bias = 0`.
- **Se non passa**: `u_bias = |bias_w| · Δt_W` entra in `budget_pred` (P4.6), il bias è
  dichiarato nella tesi con il suo segno, e **P1 non si cambia**: sostituire
  l'estimatore sulla base di un solo test sarebbe cambiare metodo senza
  evidenza. La campagna si ripete una sola volta, per distinguere un transitorio
  da un bias sistematico; se anche la ripetizione fallisce, il bias è sistematico
  e si riporta come tale.
- Le soglie sono congelate prima dei dati. Non si sceglie la soglia dopo aver
  visto il bias.

Due limiti del test, da scrivere insieme al risultato:

1. il controllo valida lo **zero** dell'estimatore, non l'assenza di effetti
   termici sotto carico. Un aumento reale del fondo durante l'inferenza
   (ventole, frequenza, temperatura) è un effetto fisico che nessun blocco di
   controllo rimuove: P1 lo tratta come drift diagnostico (`dP`, `r_A`, `r_B`),
   non come errore di stima;
2. il controllo non arbitra la **scala assoluta**: legge lo stesso registro di
   LibreHardwareMonitor. Lo strumento che manca resta il wattometro (cap. 6,
   sviluppo 1).

I blocchi di carico della campagna danno anche una seconda stima di `E_net` alla
geometria `(12,32)`, da confrontare con il punto di conferma della campagna
principale. È un confronto descrittivo, non un gate.

### P4.6 Budget di incertezza completo

Due budget, nomi distinti, nessun cambiamento ai pesi congelati.

```
budget_fit_b²  = u_base,b² + u_within,b²         # ≡ budget_b di P3.8, stesso oggetto
budget_pred_b² = budget_fit_b² + u_edge,b²       # per ogni numero pubblicato

u_base,b   = Δt̄_W,b · budget_base_w,b                        # P1.7, P3.8
u_within,b = semi-range(E_act,i nel blocco)                  # P3.8, non diviso per √m
u_edge,b   = 2 · P_peak,b · δt_edge,b ,   δt_edge,b = Δt_tick,b / 2
```

`budget_fit_b` **è** il `budget_b` di P3.8, rinominato solo per distinguerlo dal
predittivo: non è un emendamento. I pesi del fit restano `w_b = 1/budget_fit_b²`,
congelati.

Il termine di bordo. `δt_edge,b` è metà dell'intervallo **misurato** del buffer EMI
nel blocco, non dell'intervallo dichiarato da `POWER_SAMPLE_INTERVAL_S = 0.05`
(`energy_session.py:80`): sul percorso di produzione `Δt_tick` è 0,28–0,34 s. Ogni
bordo della finestra cade quasi sempre fra due campioni e il contatore cumulativo è
interpolato linearmente (`_emi_cum_at`, `energy_session.py:1103-1124`), quindi
l'errore di un bordo è al più `P_peak · δt_edge` e i bordi sono due. `P_peak,b` è la
potenza **totale** di picco del blocco, non quella netta: ciò che viene interpolato
è un contatore che accumula potenza totale, quindi il limite deve usare la potenza
totale — usare quella netta sottostimerebbe il termine. È un limite superiore
conservativo, non una propagazione di varianza: la stessa regola di P1.7.

Ordine di grandezza, dichiarato come esempio e non come misura: con
`Δt_tick = 0,30 s` e `P_peak = 35 W` il termine vale `10,5 J`, confrontabile con
l'energia netta di una richiesta breve alla geometria operativa. Quindi `u_edge` si
calcola per blocco e si riporta; non si assume trascurabile. La sua grandezza è
anche l'argomento quantitativo dello sviluppo 3 del cap. 6: il probe a 50 ms mostra
che il registro si aggiorna a quella cadenza, quindi `Δt_tick` è riducibile di un
fattore ~6 per via software, e `u_edge` con esso.

Regole:

- ogni numero **pubblicato** — `J/token`, previsione su un punto, contributo di un
  coefficiente — esce con `budget_pred`, mai con il solo `u_base`;
- come sensibilità secondaria si rifà il fit con `w_b = 1/budget_pred_b²` e si
  riporta lo spostamento dei coefficienti: se resta dentro l'intervallo bootstrap,
  la scelta dei pesi è dichiarata non influente;
- per le finestre idle da 30 s il termine di bordo si trascura e si dichiara:
  0,3 s su 30 s è l'1% della finestra, e la potenza netta in idle è per
  costruzione prossima a zero;
- l'intervallo di conferma di P3.10 resta nella forma congelata
  (`q2.5 − 2·u_conf`, `q97.5 + 2·u_conf`); come sensibilità si riporta se l'esito
  cambia sostituendo `u_conf` con `budget_pred`. P4 non riapre P3.

### P4.7 Fasce di copertura: inviluppo convesso, non rettangolo

Le celle del disegno non riempiono un rettangolo. Con il punto minimo `(8,4)` e la
griglia `32/128/512 × 32/128/256` (P3.5), la regione `N_in > 32, N_out < 32` è
coperta dal disegno e la regione `N_in < 32, N_out > 32` no. Prendere il rettangolo
avrebbe spacciato per interpolazione bilineare un'estrapolazione mascherata. La
fascia si decide quindi sull'**inviluppo convesso dei 10 punti di disegno**,
calcolato dai punti e non scritto a mano.

I vertici dell'inviluppo sono quattro:

```
(8,4)   (512,32)   (512,256)   (32,256)
```

`(32,32)` **non** è un vertice: sta dentro l'inviluppo con un margine di 21,2
token. Correzione alla lista a cinque vertici circolata in chat: il poligono con
`(32,32)` fra `(8,4)` e `(512,32)` non è convesso, perché `(32,32)` cade sopra la
retta che unisce quei due punti.

- **Fascia A — dentro l'inviluppo.** Claim primari: `J/token` ai due riferimenti,
  costi marginali, previsioni con l'intervallo di P4.8.
- **Fascia B — dentro il box, fuori dall'inviluppo.** Il box è `8 ≤ N_in ≤ 512`,
  `4 ≤ N_out ≤ 256`. Il modello viene valutato, ma la previsione è **descrittiva**,
  marcata `sparse_support`, e non entra nei claim primari.
- **Fascia C — fuori dal box.** Nessuna stima, nessun modello applicato. Si
  registrano solo le misure grezze del blocco, marcato `out_of_coverage`.

Due conseguenze da dichiarare, non da nascondere.

1. Il punto di conferma `(12,32)` — la geometria operativa reale, e quindi il
   `J/token` di produzione — cade **in fascia A**, con un margine di `1,33` token
   dal lato `(8,4)–(32,256)`. L'appartenenza è geometricamente sottile. Per questo
   `hull_margin_tok` è una colonna obbligatoria, e ogni punto pubblicato con margine
   inferiore a 2 token esce anche con il flag `thin_support`. Il flag non cambia
   l'intervallo: dichiara che la classificazione A si regge su un supporto di
   progetto di misura, e che a sostenerla è il punto di conferma empirico di P3.10,
   non la geometria.
2. `(256,192)` sta dentro con margine 64 token: la conferma alta è in fascia A
   piena.

Non esiste più una penalità di extrapolazione inventata: la fascia B è descrittiva e
la fascia C non pubblica. L'errore misurato in P3.10 resta quello che è — il test
empirico della superficie nei due punti fuori griglia — e non diventa un termine di
allargamento.

Limite di copertura dichiarato: la v4 non pubblica un `J/token` per prompt lunghi
(`N_in > 512`), che è esattamente ciò che la letteratura analitica chiede
(`cavagna2026sweetspot`). Estendere la griglia verso l'alto è lavoro della v5, non
una regola di extrapolazione.

### P4.8 Intervallo: bootstrap dei residui standardizzati

Il bootstrap ricampiona **residui**, non blocchi. Con 33 blocchi il case bootstrap
rimetterebbe in gioco il disegno; il disegno invece è fissato, e ciò che va
propagato è lo scarto fra superficie e misura.

```
fit WLS sui 33 blocchi (P3.8)          → θ̂ = (E0, a, b, c) e fitted f(x_b; θ̂)
residui                                → r_b = Ē_b − f(x_b; θ̂)
residui standardizzati                 → z_b = r_b / budget_fit_b
repliche                               → 2000, seed registrato (bootstrap_seed)
per ciascuna replica:
  ricampiona z con reintroduzione, stratificato per punto di disegno
    (10 strati, numerosità preservata: 3 per punto, 6 per il centro)
  dati sintetici                       → Ȳ*_b = f(x_b; θ̂) + budget_fit_b · z*_b
  rifit WLS con gli stessi pesi w_b    → θ*
```

Standardizzare per `budget_fit_b` invece che per una σ stimata è la scelta coerente
con P1.7 e P3.8: non assume gaussianità dei residui fisici su 33 punti, non
introduce un fattore `√m` fittizio e conserva la natura conservativa dei budget. I
pesi non si ricalcolano dentro la replica, altrimenti l'intervallo dipenderebbe dal
rumore del budget e non da quello dei dati.

I due intervalli sono **oggetti diversi** e vanno riportati come tali:

- **parametrico**, sul costo marginale per token: quantili 2,5 e 97,5 delle quantità
  derivate `b + c·N_in,ref`, `a + c·N_out,ref`, `J/token_32`, `J/token_128`,
  calcolate su `θ*`. Contiene solo l'incertezza dei coefficienti: non contiene la
  dispersione di un blocco di misura singolo, e non deve contenerla;
- **predittivo**, su un blocco nuovo a geometria `x`: lo spread parametrico di
  `f(x; θ*)` allargato con il `budget_pred` del blocco nuovo (P4.6). È questo
  l'intervallo con cui si confronta una misura, ed è ciò che P3.10 usa nella sua
  forma congelata con il termine `2·u_conf`.

Diagnostica: gli errori standard HC3 si riportano accanto come approssimazione
lineare; se l'ampiezza bootstrap e quella HC3 differiscono di più di un fattore 2,
il bootstrap resta primario e la discrepanza si dichiara — è il sintomo di una
superficie mal condizionata o di un blocco influente (P3.9). Il bootstrap non
sostituisce il lack-of-fit: un modello inadeguato ha un intervallo stretto e
sbagliato.

### P4.9 Catena di validazione: criterio monolitico

"Validata" è una parola sola e si assegna solo se **tutti** gli anelli passano. Non
esiste validazione parziale: un anello rotto rompe la parola, non il dato.

| # | anello | criterio | etichetta se fallisce |
|---|---|---|---|
| 1 | token e terminazione | pilota P2.9 A/B/C superato | campagna non eseguibile: si corregge il pilota, non i dati |
| 2 | contatore | nessun blocco con delta negativo, reset o lettura non finita (P1.6) | `counter_invalid`: il blocco si ripete una volta, poi si scarta e si dichiara |
| 3 | baseline | `r_A ≤ 10%` in almeno 2 blocchi su 3 per punto (P1.6) | `baseline_unstable`; con due punti su tre, campagna invalida |
| 4 | sottrazione | test load-versus-control dentro il budget (P4.5) | `bias_declared`: `u_bias` entra in `budget_pred`, P1 non cambia |
| 5 | adeguatezza del modello | lack-of-fit **non** significativo, `p ≥ 0,05` (P3.9) | `model_inadequate`: la superficie si riporta come descrizione, non come legge |
| 6 | conferma | entrambi i punti di P3.10 con `err_rel ≤ 10%` e dentro l'intervallo | `validation_failed`: nessun rifit sui punti di conferma |

Regole di fallimento, congelate:

- se anche un solo anello fallisce, l'esperimento **non si scarta**: si
  riclassifica. Alle etichette della tabella si aggiunge `reduced_design`, per i
  casi in cui un punto è escluso dal fit primario perché `r_B > 20%` (P1.6);
- non si forza l'adattamento del modello sui dati di test, non si sceglie un altro
  modello sui dati di validazione, non si sposta una soglia dopo aver visto il
  numero;
- l'esito della catena è una colonna (`chain_status`) e una riga di verbale, non un
  aggettivo nel testo;
- nella tesi la frase "la misura è validata" compare solo se
  `chain_status = validated`. Negli altri casi si scrive quale anello ha ceduto.

Gli anelli non sono sostituibili fra loro: nessun confronto fra due letture dello
stesso registro può rimpiazzare il test di sottrazione (4), e nessun test di
sottrazione può rimpiazzare la conferma su geometrie mai entrate nel fit (6).

### P4.10 Cosa arbitra ogni prova, e cosa no

Nessun anello, da solo, è validazione. La catena è forte quanto il suo anello più
debole, che su questa macchina è l'assenza del wattometro.

| anello | prova | cosa arbitra | cosa **non** arbitra |
|---|---|---|---|
| contatore EMI ↔ potenza LHM | confronto a finestra identica, 5 run (`four_way_finestra_uguale_20261023_analisi.md`) | che il nostro software non distorce: rapporti 0,9947–1,0082, offset +0,21/+0,27 W | la scala: entrambe le letture stanno su `MSR_PKG_ENERGY_STATUS` 0x611 |
| parser EMI ↔ decodifica Microsoft | SRUM sulla stessa finestra di 7 minuti (`srum_emi_cross_20261023_analisi.md`) | che il parser ctypes decodifica il formato giusto: 0,9946, deviazione massima 3,77% | la scala, e non è un contatore indipendente |
| quota di tempo CPU ↔ quota di energia | albero dei processi del motore contro il modello EPI | la **procedura** di attribuzione: 0,7339 contro 0,7361 | l'equivalenza tempo ↔ energia, che resta assunzione dichiarata |
| cadenza e geometria dei domini | probe a 50 ms e 10 ms con LHM assente (`emi_50ms_probe_20261023_*`) | che il registro si aggiorna anche a 10 ms, che il pavimento di 0,3 s è del nostro thread, il residuo di package 5,59 W, `ΔPP0/ΔPKG ≈ 1` | la scala assoluta |
| baseline e sottrazione | campagna load-versus-control (P4.4) | che lo zero dell'estimatore sta dentro il budget | gli effetti termici sotto carico; la scala |
| superficie e attribuzione | punti di conferma esclusi dal fit (P3.10) | che il modello prevede geometrie mai usate nella stima | che il modello sia la forma vera |
| `J/token` | sensibilità post-hoc (P1.10) e geometria reale (P3.4) | che il numero dipende da baseline (1 W ≈ 6–11%) e da `N_in` | che sia confrontabile fra geometrie diverse |

Un A–B–A fra due letture dello stesso registro **nasconde** un canale sbagliato
invece di correggerlo: è successo. Prima di `1422d1b` la selezione per nome del
sensore (allora `energy_session.py:819`) integrava i gradi Celsius di un sensore
Temperature omonimo, e lo stesso confronto dava rapporti 2,47–4,42 con offset
+53,52 W. Oggi il guard sul tipo sta a `energy_session.py:951-955`. L'unico
controllo che ha salvato il metodo è stato leggere il tipo di sensore, non
confrontare due misure.

**Caveat sulla scala assoluta, obbligatorio nella tesi.** La sovrapposizione
EMI ↔ SRUM (0,9946) e EMI ↔ LHM (0,9947–1,0082 a finestra identica, 0,9966–1,0156
sulla trace busy-loop) è un controllo di **coerenza software e di registro**, non
una validazione metrologica della scala assoluta: tutte le letture stanno sullo
stesso `MSR_PKG_ENERGY_STATUS`, quindi concordano per costruzione anche se la scala
del registro fosse sbagliata. Una validazione metrologica richiede un wattometro
AC/DC esterno, che non c'è. Questo va scritto nel capitolo della valutazione
**prima** dei numeri, non in una nota a piè di pagina: è ciò che protegge il lavoro
da un'obiezione ovvia in sede di revisione.

### P4.11 Confronto con la produzione reale

Il blocco di produzione (terminazione naturale, P3.5) si confronta con il modello
**richiesta per richiesta**, non sul punto medio dei token:

```
Σ_i modello(N_in,i, N_out,i)   contro   Σ_i E_act,i     sulle richieste del blocco
```

con `N_in,i` e `N_out,i` effettivi (P2) e il modello ai coefficienti stimati sui
soli blocchi di fit. Il confronto è **descrittivo** e non ha esito pass/fail: la
produzione reale ha dinamiche proprie — lunghezza variabile, terminazione naturale,
prefissi non uniformi — che il disegno sperimentale descrive senza vincolare.
Trasformarlo in un test significherebbe usare gli stessi dati con due ruoli diversi.

Si riportano il rapporto delle due somme, la sua dispersione fra i blocchi e la
fascia di copertura (P4.7) in cui cade ciascuna richiesta di produzione.

### P4.12 Cosa non è deciso qui

- P5 fissa nomi e tipi delle colonne. P4 elenca i contenuti nuovi obbligatori:
  `block_kind` ∈ {`load`, `control`}, `pair_id`, `order_seed`, `dt_nominal_s`,
  `dt_tick_s`, `p_peak_w`, `u_edge_j`, `budget_fit_j`, `budget_pred_j`, `u_bias_j`,
  `bias_w`, `z_resid`, `hull_margin_tok`, `coverage_tier` ∈ {`A`, `B`, `C`},
  `sparse_support`, `thin_support`, `out_of_coverage`, `bootstrap_seed`,
  `validation_bias_pass`, `chain_status`;
- P6 fissa l'ordine di esecuzione — la campagna di P4.4 sta prima della principale e
  ne è il gate — e gli script di analisi;
- il wattometro: la scala assoluta resta non arbitrata (cap. 6, sviluppo 1);
- Linux/RAPL: il disegno di P4.4 è indipendente dal backend e si applica a RAPL con
  gli stessi criteri, ma in v4 non è eseguito. Il backend Linux è implementato, non
  validato su questa campagna;
- la deviazione standard campionaria con n = 3 **non si adotta**: con tre repliche
  non è una stima utilizzabile di varianza, e affiancarla al semi-range invita a
  trattarla come tale. Restano registrati i tre valori, la mediana, il minimo, il
  massimo e il range (già in P1.5 e P1.7).

### P4.13 Ancoraggi

- interpolazione ai bordi: `energy_session.py:1103-1124` (`_emi_cum_at`),
  `:1126-1148` (`_emi_field_at`), `:2188-2205` (`_interpolate` sui campioni di
  sistema);
- cadenza dichiarata: `energy_session.py:80` (`POWER_SAMPLE_INTERVAL_S = 0.05`);
  cadenza misurata 0,28–0,34 s: cap. 5, §risoluzione;
- finestre di energia: `energy_session.py:1194` (`emi_window_energy_j`), `:1261`
  (`pi_window_energy_j`); lettura finestra idle: `:1576`;
- bug del sensore omonimo e fix: guard sul tipo a `energy_session.py:951-955`,
  selezione del sensore package a `:855-915`, commit `1422d1b`;
- inviluppo convesso: calcolato sui 10 punti di disegno di P3.5; vertici `(8,4)`,
  `(512,32)`, `(512,256)`, `(32,256)`; margini verificati numericamente il
  24-10-2026 — `(12,32)` → 1,33 token, `(256,192)` → 64,0, `(32,32)` → 21,2,
  `(128,128)` → 107,7;
- budget e pesi: P1.7, P3.8; validazione della superficie: P3.10; diagnostica e
  lack-of-fit: P3.9; sensibilità post-hoc: P1.10; controlli di drift: P1.6;
- artefatti della catena: `four_way_finestra_uguale_20261023_analisi.md`,
  `srum_emi_cross_20261023_analisi.md`,
  `idle_floor_sensitivity_20261023_analisi.md`, `emi_50ms_probe_20261023_*`;
- provenienza della campagna di controllo: `baseline miglioramenti.DOCX` §3
  (materiale utente, valutato contro P1: nomenclatura, registrazione delle repliche
  e separazione dei tre valori erano già congelati).

### P4.14 Aperto

Niente per P4. Tre esiti possono riaprirlo, e sono risultati di P6, non decisioni
aperte:

- se il test di P4.5 fallisce anche nella ripetizione, `u_bias` entra nel budget e
  la tesi dichiara che la sottrazione non è validata su questa macchina;
- se il pre-pilota di P3.15 mostra che un livello della griglia non è raggiungibile,
  cambiano i punti di disegno e con essi l'inviluppo di P4.7;
- se il lack-of-fit di P3.9 è significativo, `chain_status` scende a
  `model_inadequate` e la superficie si riporta come descrizione.

---

## Formulario consolidato (P1–P4)

Sezione derivata: **nessuna decisione nuova**. Ogni formula è riportata dal punto
congelato indicato fra parentesi; se questa sezione e il punto divergono, vince il
punto. Esiste perché P5 e P6 dovranno tradurre queste formule in colonne e in
codice, e una traduzione senza l'ordine di calcolo e senza la ragione di ogni
forma è esattamente il punto in cui si introducono errori silenziosi.

### F.0 Ordine di calcolo

Per ogni blocco `b`, nell'ordine:

1. tre finestre pre → `P_rep,1..3`, `baseline_pre_w` (F.1);
2. `m = 3` richieste → per ciascuna `E_pkg_gross,i`, `Δt_W,i`, `N_in,i`,
   `N_out,i`, `done_reason` (F.6);
3. tre finestre post → `baseline_post_w`, `dP` (F.1);
4. `E_act,i` firmato, mai troncato (F.2);
5. controlli `pre_range_w`, `r_A`, `r_B` e flag (F.3);
6. `budget_base_w,b`, `budget_base_j,b` (F.4);
7. medie di blocco `Ē_b`, `x1_b`, `x2_b`, `x12_b` (F.7);
8. `u_base,b`, `u_within,b`, `budget_fit_b`, `w_b` (F.9);
9. `Δt_tick,b`, `P_peak,b`, `u_edge,b`, `budget_pred_b` (F.11);
10. fit WLS sui 33 blocchi → `θ̂ = (E0, a, b, c)` (F.9);
11. residui, `z_b`, bootstrap a 2000 repliche → intervallo parametrico e
    predittivo (F.14);
12. conferma sui 6 blocchi esclusi dal fit → `err_rel`, `intervallo` (F.10);
13. copertura → `hull_margin_tok`, `coverage_tier` (F.13);
14. campagna separata load-versus-control → `bias_w`, `u_bias`,
    `validation_bias_pass` (F.12);
15. `chain_status` dai sei anelli (P4.9).

I passi 1–9 sono per blocco e vivono nel CSV riga per riga; i passi 10–15 sono
analisi e vivono nel verbale. Quali dei primi diventino colonne lo decide P5.

### F.1 Baseline (P1.1, P1.3)

```
P_rep,k          = ΔE_contatore,k / Δt_reale,k          k = 1..3,  finestra = 30,000 s
baseline_pre_w   = mediana(P_rep,1, P_rep,2, P_rep,3)
baseline_post_w  = idem, dopo l'ultimo punto
dP               = baseline_post_w − baseline_pre_w
```

*Applicazione.* Una volta per blocco, prima e dopo le tre richieste; la baseline
non è un punto del modello e non contiene `E0`.

*Giustificazione.* Mediana e non media: con `n = 3` una finestra contaminata
sposta la media ma non la mediana (P1.14, "Cosa è nostro"). L'estimatore è
identico a quello di produzione (`calibrate_idle` già fa tre ripetizioni da
almeno 30 s e la mediana, `energy_session.py:2363-2396`, con floor a 30 s
`:2252-2257` e rifiuto dei delta negativi `:2383-2387`): la v4 non cambia la
formula, cambia il momento e il numero di applicazioni, perché cambiare
stimatore e protocollo insieme confonderebbe l'esperimento (P1.2). Il
denominatore è `Δt_reale` restituito dalla lettura, non i 30 s nominali.

### F.2 Incremento netto (P1.3, P3.2)

```
baseline_energy_j = baseline_pre_w · Δt_W
E_net_incremental = E_pkg_gross − baseline_energy_j
E_act,i           = E_pkg_gross,i − P_pre,b · Δt_W,i        # sinonimo dichiarato
```

*Applicazione.* Per ogni richiesta. È la variabile dipendente del modello F.8.

*Giustificazione.* Si applica `P_pre` e il post resta diagnostico: interpolare su
un `dP` non stazionario sarebbe arbitrario (P1.10) e usare il post tarerebbe
retroattivamente la sottrazione (P1.14). La ragione è causale, non solo
operativa: `P_post` è misurata dopo che il carico ha modificato lo stato della
macchina, quindi è una grandezza post-trattamento, e la potenza idle durante
`Δt_W` non è osservata — `P_pre` è l'unico proxy che non sia funzione del
trattamento (P1.14, motivazione causale). `P_pre,b` è la stessa per le tre
richieste del blocco, perché la baseline è misurata una volta per blocco (P3.7).
**Non si tronca a zero.** La produzione invece tronca, due volte:
`package_energy_j = max(e_package, 0)` a `local_energy.py:300` e
`active = max(package_energy_j − baseline_energy_j, 0)` a `:309-310` (il punto
P3.2 cita `:310`, l'assegnazione del valore troncato). La v4 conserva il segno:
un incremento negativo è l'informazione che il test di F.12 cerca, e troncandolo
diventa invisibile.

### F.3 Stabilità e drift (P1.6)

```
pre_range_w = max(P_rep) − min(P_rep)
r_A = |dP| · Σ_{i∈blocco} Δt_W,i / Σ_{i∈blocco} E_trunc,i
r_B = |dP| · Σ_{i∈punto}  Δt_W,i / Σ_{i∈punto}  E_trunc,i
```

*Applicazione.* `r_A` per blocco, `r_B` per punto di disegno. Soglia operativa
10%, sensibilità a 5% e 20%, non modificabile dopo i dati. Esiti: `pre_unstable`
se `pre_range_w > 1,0 W`; `baseline_unstable` se `r_A > 10%` (due blocchi su tre
marcati → campagna invalida); `r_B` 10–20% → punto mantenuto, marcato, peso
ridotto; oltre 20% → escluso dal fit primario e riportato in sensibilità.

*Giustificazione.* La soglia di 1,0 W è misurata, non scelta: 1 W di errore sulla
baseline sposta J/token del 6–11% (`idle_floor_sensitivity_20261023_analisi.md`
§2). Le somme corrono sulle **richieste valide**, non sul tempo a muro del
blocco: il blocco include warm-up e finestre idle, che non hanno energia netta
attribuibile e gonfierebbero il numeratore. Se il denominatore è zero, blocco o
punto è invalido per costruzione. I flag non invalidano da soli: entrano nel
budget di F.4.

### F.4 Incertezza di baseline (P1.7)

```
half_range_pre_w = (max(P_rep) − min(P_rep)) / 2        # semi-range conservativo
half_drift_w     = |dP| / 2                             # semi-range conservativo
budget_base_w    = sqrt(half_range_pre_w² + half_drift_w²)
budget_base_j    = Δt_W · budget_base_w
budget_J_base    = budget_base_j / N_out_actual
```

*Applicazione.* Per blocco. `budget_base_w` entra in `u_base` del fit (F.9);
`budget_base_j` è la soglia del test di F.12.

*Giustificazione.* Con `n = 3` non si stima una deviazione standard: i due termini
sono **semi-range conservativi** e la radice è la loro combinazione in
quadratura, un budget e non una varianza. Nella tesi il termine è "semi-range
conservativo", mai "deviazione standard". `budget_J_base` è **solo** il
contributo di baseline — l'esempio di 0,034 J/token a 0,3 W, 3,6 s e 32 token è
questo contributo — e il totale aggiunge repliche e bordo (F.9, F.11). La forma di
combinazione è una decisione operativa provvisoria, non definitiva: resta la
quadratura, la scelta fra quadratura e somma è rinviata ai dati del pilota P2.9 e
va chiusa prima della campagna principale (P1.7, P1.13).

### F.5 Sensibilità post-hoc, secondaria (P1.10)

```
P_lin(t)     = P_pre + (P_post − P_pre) · (t − t_pre_mid) / (t_post_mid − t_pre_mid)
E_base_lin,i = Δt_W,i · P_lin(t_mid,W,i)
Δ_sens,i     = (E_pkg_gross,i − E_base_lin,i) − E_net_incremental,i
```

*Applicazione.* Calcolata **dopo** la chiusura dei dati primari. Se
`|Δ_sens| ≤ budget_base_j` del blocco, l'interpolazione non aggiunge
informazione; altrimenti si dichiara la differenza e il primario resta.

*Giustificazione.* Assume drift lineare fra pre e post, e il drift misurato non lo
è: nel run v3 la baseline va da 13,28 a 12,82 W con `dP = −0,461 W`
(`lhm_validation_v3_20261023_185232.md:13,24`) e fra run è passata da 13,39 a
12,19 W (`idee_implementative_20261024.md:67`). Per questo la sensibilità non
arbitra. Stimatori più complessi — regressione sull'intera finestra, Kalman,
media mobile, modello per processo — sono rinviati a una v5 con validazione
dedicata.

### F.6 Token e terminazione (P2.3, P2.4)

```
N_in_actual,i  = prompt_eval_count_i
N_out_actual,i = eval_count_i
dev_in_pct,i   = 100 · (N_in_actual,i − n_input_tokens_target) / n_input_tokens_target
dev_out_pct,i  = 100 · (N_out_actual,i − n_output_tokens_target) / n_output_tokens_target
J/token_pkg,i  = E_net_incremental,i / N_out_actual,i          # richiede N_out_actual ≥ 1
early_stop     = (done_reason == "stop" and N_out_actual < num_predict)
```

*Applicazione.* Ogni riga del CSV. `J/token_pkg,i` è **descrittivo**: la metrica
primaria è F.8 ai due riferimenti predeclarati. `dev_in_pct` e `dev_out_pct`
misurano quanto il costruttore del prompt ha centrato il target, non sono criteri
di validità. `N_total_actual` non è mai un denominatore.

*Giustificazione.* I contatori di Ollama e non una stima: la v4 non chiama
`_estimate_tokens` (`benchmark_unified.py:101-116`) e se un contatore manca la
richiesta è invalida — non esiste un ramo "stima e prosegui" (P2.6). `early_stop`
non è un errore e non si esclude: gli stop anticipati sono la maggioranza, e
scartarli eliminerebbe la maggior parte dei dati proprio alle `N_out` basse
(P2.4). Ogni richiesta porta un nonce univoco a larghezza fissa all'inizio del
prompt (P2.8), così nessuna coppia condivide un prefisso byte-identico e
`N_in_actual` è l'intero prompt, non la parte non ancora in cache: senza nonce il
riuso del prefisso KV cambierebbe il costo attribuito a `N_in` senza cambiare
`N_in_actual`, e il modello geometrico vedrebbe un input che non è stato pagato.

### F.7 Unità del fit: medie di blocco (P3.7)

```
Ē_b   = (1/m) Σ_i E_act,i                    m = 3
x1_b  = (1/m) Σ_i N_in,i
x2_b  = (1/m) Σ_i N_out,i
x12_b = (1/m) Σ_i N_in,i · N_out,i
```

*Applicazione.* Un punto del fit per blocco; 39 blocchi totali, 33 nel fit, 6 di
conferma esclusi.

*Giustificazione.* `x12_b` è la media dei prodotti e non il prodotto delle medie:
così la linearizzazione del modello resta esatta anche con nonce di lunghezza
leggermente diversa. L'unità è il blocco perché la baseline è misurata una volta
per blocco e il suo errore è comune alle tre richieste — ed è la ragione per cui
`u_base` non si divide per `m` in F.9.

### F.8 Modello e quantità derivate (P3.3, P3.4)

```
E_act,i = E0 + a·N_in,i + b·N_out,i + c·N_in,i·N_out,i + ε_i

E_model(ref)    = E0 + a·N_in,ref + b·N_out,ref + c·N_in,ref·N_out,ref
J/token_ref     = E_model(ref) / N_out,ref
∂E/∂N_out (ref) = b + c·N_in,ref
∂E/∂N_in  (ref) = a + c·N_out,ref
share_E0(ref)   = E0 / E_model(ref)
```

*Applicazione.* Riferimenti predeclarati `(32,32)` e `(128,128)`, entrambi sulla
griglia. `E0` overhead fisso per richiesta a modello residente, `a` J/token di
prefill marginale, `b` J/token di decode marginale, `c` interazione.

*Giustificazione.* La superficie è lineare **nei parametri**; `c·N_in·N_out` è
un'interazione bilineare, non un termine quadratico, e non si aggiungono `N_in²`
o `N_out²`. `c ≥ 0` è atteso perché la KV cache cresce con `N_in` e ogni token di
decode legge un contesto più lungo. Il modello ridotto
`E0 + a·N_in + b·N_out` si riporta solo come sensibilità con F-test sui minimi
quadrati pesati e non sostituisce il primario dopo aver visto i dati. `E0` è
un'estrapolazione a `(0,0)`: il punto minimo `(8,4)` la vincola ma non la
identifica, per questo esce con il suo intervallo e con il flag
`intercept_nonphysical` se l'intervallo include valori negativi — non si vincola
il fit e non si cambia modello. `J/token_32` e `J/token_128` sono valori
**fitted**, non stime indipendenti. La quota di attribuzione `s` **non entra nel
modello**: il contatore resta sulla macchina e la geometria spiega l'energia
netta, quindi `s` non ha un coefficiente — ed è la ragione per cui l'anello
"quota CPU" di P4.9 non può fare da gate su nulla.

### F.9 Stima: minimi quadrati pesati (P3.8, P4.6)

```
min_{E0,a,b,c} Σ_b w_b · (Ē_b − E0 − a·x1_b − b·x2_b − c·x12_b)²

u_base,b      = Δt̄_W,b · budget_base_w,b        # comune alle m richieste
u_within,b    = semi-range(E_act,i nel blocco)  # non diviso per √m
budget_fit_b² = u_base,b² + u_within,b²
w_b           = 1 / budget_fit_b²
```

*Applicazione.* Sui 33 blocchi del fit: 10 punti (9 celle della griglia
32/128/512 × 32/128/256 più il minimo `(8,4)`), con il centro `(128,128)` a 6
blocchi. Errori standard HC3.

*Giustificazione.* `u_base,b` non si divide per `m` perché l'errore di baseline è
comune alle tre richieste; `u_within,b` non si divide per `√m` perché non si
assume l'indipendenza delle tre richieste. Sono scelte conservative deliberate:
`budget_fit_b` è un budget conservativo e `w_b` un peso conservativo, non un peso
di precisione. Se `budget_fit_b = 0` si usa peso uguale e si marca il blocco. La
stima primaria è la WLS; la OLS non pesata è sensibilità. Il bootstrap per batch
non si usa: con 3 batch ha troppi pochi cluster. `budget_fit_b` è lo stesso
oggetto del `budget_b` di P3.8, rinominato in P4.3 per distinguerlo dal
predittivo — non è un emendamento e i pesi restano congelati.

### F.10 Validazione della superficie (P3.10)

```
E_meas     = media dei 3 blocchi del punto di conferma
E_pred     = modello ai parametri stimati sui soli blocchi di fit
err_rel    = |E_meas − E_pred| / E_pred
u_conf     = semi-range(E_meas,1..3)                    # non diviso per √3
intervallo = [q2.5 − 2·u_conf , q97.5 + 2·u_conf]       # quantili bootstrap della previsione
passa se   err_rel ≤ 10%  e  E_meas ∈ intervallo
```

*Applicazione.* Sui due punti `(12,32)` e `(256,192)`, misurati nella stessa
campagna ma esclusi dalla stima; l'analisi li apre solo dopo che la specifica è
congelata e i coefficienti stimati.

*Giustificazione.* Il 10% è la stessa scala della sensibilità della baseline
(1 W ≈ 6–11% di J/token), non una soglia scientifica, ed è dichiarato come tale.
Se fallisce si dichiara il fallimento: nessun rifit sui punti di conferma, nessuna
scelta di un altro modello sui dati di validazione, `J/token` resta quello del
modello marcato `validation_failed`. La forma dell'intervallo è congelata; P4 non
la riapre, e la sostituzione di `u_conf` con `budget_pred` si riporta solo come
sensibilità (P4.6).

### F.11 Termine di bordo e budget predittivo (P4.3, P4.6)

```
δt_edge,b      = Δt_tick,b / 2
u_edge,b       = 2 · P_peak,b · δt_edge,b  =  P_peak,b · Δt_tick,b
budget_pred_b² = budget_fit_b² + u_edge,b²
```

*Applicazione.* Per blocco. Ogni numero **pubblicato** — `J/token`, previsione su
un punto, contributo di un coefficiente — esce con `budget_pred`, mai con il solo
`u_base`.

*Giustificazione.* Ogni bordo della finestra cade quasi sempre fra due campioni e
il contatore cumulativo è interpolato linearmente (`_emi_cum_at`,
`energy_session.py:1103-1124`), quindi l'errore di un bordo è al più
`P_peak · δt_edge` e i bordi sono due. Tre dettagli che cambiano il numero:
`Δt_tick,b` è l'intervallo **misurato** del buffer EMI nel blocco, non il
dichiarato `POWER_SAMPLE_INTERVAL_S = 0.05` (`energy_session.py:80`) — in
produzione è 0,28–0,34 s; `P_peak,b` è la potenza **totale** di picco, non la
netta, perché ciò che si interpola è un contatore che accumula potenza totale e
usare la netta sottostimerebbe il termine; e il risultato non è trascurabile,
con `Δt_tick = 0,30 s` e `P_peak = 35 W` vale 10,5 J, confrontabile con l'energia
netta di una richiesta breve alla geometria operativa (ordine di grandezza
dichiarato come esempio, non come misura). È un limite superiore conservativo,
non una propagazione di varianza: la stessa regola di F.4.

`u_edge` entra **solo** nel budget predittivo: fonderlo nel budget di fit
riaprirebbe i pesi congelati di P3.8. Come sensibilità secondaria si rifà il fit
con `w_b = 1/budget_pred_b²` e si riporta lo spostamento dei coefficienti; se
resta dentro l'intervallo bootstrap, la scelta dei pesi è dichiarata non
influente. Sulle finestre idle da 30 s il termine si trascura **e si dichiara**:
0,3 s su 30 s è l'1% della finestra e la potenza netta in idle è per costruzione
prossima a zero. La grandezza di `u_edge` è anche l'argomento quantitativo dello
sviluppo 3 del cap. 6: il probe a 50 ms mostra che il registro si aggiorna a
quella cadenza, quindi `Δt_tick` è riducibile di un fattore ~6 per via software, e
`u_edge` con esso.

### F.12 Test di sottrazione load-versus-control (P4.4, P4.5)

```
per blocco di controllo c:  passa se |E_net,control,c| ≤ budget_base_j,c

bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c     sui soli blocchi con r_A ≤ 10%
passa se |bias_w| ≤ mediana_c(budget_base_w,c)

se non passa:  u_bias = |bias_w| · Δt_W   → entra in budget_pred
```

*Applicazione.* Campagna separata, 3 blocchi di carico + 3 di controllo, stessa
geometria del punto di conferma `(12,32)`, stessa durata, ordine randomizzato con
seed registrato; è un gate prima della campagna principale.

*Giustificazione.* Il criterio è calcolabile solo in virtù del requisito 7 di
P4.4: `r_A`, `budget_base_j,c` e `budget_base_w,c` esistono su un blocco di
controllo perché quel blocco esegue la stessa struttura 3 pre + 3 post dei
blocchi di carico. `bias_w` è atteso zero per costruzione — il blocco di
controllo è identico per struttura, stato macchina e durata, senza alcuna
richiesta — quindi il test è falsificabile, a differenza di un confronto fra due
letture dello stesso registro. Se il test fallisce, `u_bias` si dichiara con il
suo segno e **P1 non cambia**: sostituire l'estimatore sulla base di un solo test
sarebbe cambiare metodo senza evidenza. Una sola ripetizione, per distinguere un
transitorio da un bias sistematico. Soglie congelate prima dei dati.

Due limiti da scrivere insieme al risultato: il controllo valida lo **zero**
dell'estimatore, non l'assenza di effetti termici sotto carico (un aumento reale
del fondo durante l'inferenza è un effetto fisico che nessun blocco di controllo
rimuove, e P1 lo tratta come drift diagnostico); e non arbitra la **scala
assoluta**, perché legge lo stesso registro di LibreHardwareMonitor.

### F.13 Copertura: inviluppo convesso (P4.7)

```
vertici = (8,4)   (512,32)   (512,256)   (32,256)
box     = 8 ≤ N_in ≤ 512 ,  4 ≤ N_out ≤ 256

A = dentro l'inviluppo                    → claim primari
B = dentro il box, fuori dall'inviluppo   → previsione descrittiva, sparse_support
C = fuori dal box                         → nessuna stima, out_of_coverage
hull_margin_tok < 2                       → thin_support
```

*Applicazione.* Ogni punto pubblicato esce con `coverage_tier` e
`hull_margin_tok`; l'inviluppo si calcola dai 10 punti di disegno, non si scrive
a mano.

*Giustificazione.* Le celle del disegno non riempiono un rettangolo: la regione
`N_in > 32, N_out < 32` è coperta, la regione `N_in < 32, N_out > 32` no, e
prendere il box avrebbe spacciato per interpolazione bilineare
un'estrapolazione mascherata. I vertici sono **quattro**, non cinque: `(32,32)`
sta dentro con margine 21,2 token e il poligono che lo includesse fra `(8,4)` e
`(512,32)` non sarebbe convesso. Margini verificati numericamente il 24-10-2026:
`(12,32)` → 1,33 token, `(256,192)` → 64,0, `(32,32)` → 21,2, `(128,128)` →
107,7. Il punto operativo `(12,32)` è quindi in fascia A per 1,33 token:
`thin_support` non cambia l'intervallo, dichiara che la classificazione A si
regge su un supporto di progetto sottile e che a sostenerla è la conferma
empirica di F.10, non la geometria. Non esiste una penalità di estrapolazione
inventata: la fascia B è descrittiva e la fascia C non pubblica.

### F.14 Bootstrap dei residui standardizzati (P4.8)

```
r_b = Ē_b − f(x_b; θ̂)
z_b = r_b / budget_fit_b
2000 repliche, seed registrato (bootstrap_seed)
per ciascuna replica:
    ricampiona z con reintroduzione, stratificato per punto di disegno
      (10 strati, numerosità preservata: 3 per punto, 6 per il centro)
    Ȳ*_b = f(x_b; θ̂) + budget_fit_b · z*_b
    rifit WLS con gli stessi pesi w_b  → θ*

parametrico: q2,5 e q97,5 di b + c·N_in,ref ; a + c·N_out,ref ; J/token_32 ; J/token_128
predittivo : spread parametrico di f(x; θ*) allargato con il budget_pred del blocco nuovo
```

*Giustificazione.* Ricampiona **residui** e non blocchi: con 33 blocchi il case
bootstrap rimetterebbe in gioco il disegno, che invece è fissato, e ciò che va
propagato è lo scarto fra superficie e misura. Standardizzare per `budget_fit_b`
invece che per una σ stimata è coerente con F.4 e F.9: non assume gaussianità dei
residui fisici su 33 punti, non introduce un fattore `√m` fittizio e conserva la
natura conservativa dei budget. I pesi non si ricalcolano dentro la replica,
altrimenti l'intervallo dipenderebbe dal rumore del budget e non da quello dei
dati. I due intervalli sono oggetti diversi e si riportano come tali: il
parametrico contiene solo l'incertezza dei coefficienti e non deve contenere la
dispersione di un blocco singolo; il predittivo è quello con cui si confronta una
misura, ed è ciò che F.10 usa nella forma congelata con `2·u_conf`. Diagnostica:
gli errori standard HC3 si riportano accanto come approssimazione lineare; se le
due ampiezze differiscono di più di un fattore 2, il bootstrap resta primario e
la discrepanza si dichiara. Il bootstrap non sostituisce il lack-of-fit: un
modello inadeguato ha un intervallo stretto e sbagliato.

### F.15 Confronto con la produzione reale (P4.11)

```
Σ_i modello(N_in,i, N_out,i)   contro   Σ_i E_act,i      sulle richieste del blocco
```

*Applicazione.* Sul blocco di produzione, con i token effettivi di F.6 e il
modello ai coefficienti stimati sui soli blocchi di fit. Si riportano il rapporto
delle due somme, la sua dispersione fra i blocchi e la fascia di copertura di
ciascuna richiesta di produzione.

*Giustificazione.* Richiesta per richiesta e non sul punto medio dei token. È
**descrittivo** e non ha esito pass/fail: la produzione reale ha dinamiche
proprie — lunghezza variabile, terminazione naturale, prefissi non uniformi — che
il disegno sperimentale descrive senza vincolare, e trasformare il confronto in
un test significherebbe usare gli stessi dati con due ruoli diversi.

### F.16 Regole di forma che vincolano ogni formula

- nessun `sqrt(Σ u²)` di questa sezione è una propagazione di varianza: sono
  combinazioni in quadratura di **budget conservativi** (F.4, F.9, F.11);
- nessun semi-range diventa σ, e nessun `√m` o `√3` compare dove non è scritto:
  `u_within,b` e `u_conf` non si dividono per la radice del numero di repliche;
- nessuna quantità netta è troncata a zero (F.2); gli zeri legittimi sono
  dichiarati — `baseline_energy_j = 0` con `idle_provenance = "uncalibrated"`
  (`local_energy.py:196-203`) — e non sono celle vuote riempite;
- nessun dominio si somma: PP0 e PP1 sono sottoinsiemi di PKG, e nemmeno
  PKG + DRAM (`emi_backend.py:29`, `:272`; `DOMAIN_NAMES = ("pkg", "dram",
  "pp0", "pp1")` a `:73`);
- ogni soglia — 1,0 W, 10%, 20%, 10% di `err_rel`, 2 token, fattore 2 — è
  congelata prima dei dati e non si sposta dopo aver visto il numero;
- ogni numero pubblicato esce con il suo `budget_pred` e con la sua fascia;
  "validata" si scrive solo se `chain_status = validated` (P4.9);
- l'accordo fra due letture dello stesso registro (EMI ↔ LHM ↔ SRUM, tutte su
  `MSR_PKG_ENERGY_STATUS` 0x611) è coerenza software e di registro, non
  validazione metrologica della scala assoluta (P4.10).

### F.17 Dalla formula alla colonna: stato attuale

Colonne che **esistono già** nello schema di `casualwatt_csv_export.py`
(`CSV_COLUMNS`, `:17-108`) e il simbolo che le abita. Nomi e tipi definitivi, e
quali contenuti nuovi diventino colonne, li decide P5: questa tavola è la mappa
di ciò che c'è, non lo schema.

| simbolo (formula) | colonna esistente | nota per P5 |
|---|---|---|
| `E_pkg_gross,i` (F.2) | `package_energy_j` | oggi `max(·, 0)` a `local_energy.py:300` |
| `baseline_pre_w` (F.1) | `idle_power_w` | una sola cifra per riga: le tre repliche non sono salvate |
| `baseline_energy_j` (F.2) | `baseline_energy_j` | `idle_power_w · dt` a `:308` |
| `E_act,i` (F.2) | `active_energy_j` | oggi troncato a `:309-310`; la v4 conserva il segno |
| `N_in_actual`, `N_out_actual` (F.6) | `input_tokens`, `output_tokens` | — |
| `J/token_pkg,i` (F.6) | `energy_per_output_token_j` | descrittivo, non metrica primaria |
| `Δt_W,i` (F.2) | `duration_s` | — |
| `Δt_tick,b` (F.11) | `sampling_interval_observed_s` | osservato, non richiesto: è già la grandezza giusta |
| valori grezzi del contatore | `raw_start`, `raw_end`, `raw_unit`, `domain` | rendono `package_energy_j` revisionabile |
| canale di misura | `energy_calculation_method` | token di `MEASURED_METHODS` (`energy_session.py:49-50`) |
| origine della finestra | `package_window_source` | `exact-counter \| samples-fallback \| unavailable` |
| origine della baseline | `idle_provenance` | `calibrated \| session \| uncalibrated` |
| `keep_alive` inviato | `keep_alive_sent` | la v4 lo fissa a `-1` (P1.4) |
| quota di tempo CPU | `cpu_time_share`, `cpu_share_window_s`, `cpu_busy_capacity_cores` | la quota `s` non entra in F.8 |

Contenuti obbligatori già elencati dai punti congelati. P3.13: `batch_id`,
`block_id`, `point_id`, target e actual dei token, `done_reason`, `early_stop`,
`prompt_nonce`, `model_digest`, `ollama_version`, `temperature`, `num_ctx`,
`num_predict`, `order_index`, `r_A`, `r_B`, `negative_increment`,
`pre_unstable`, `baseline_unstable`, `design_deviation`. P4.12: `block_kind`,
`pair_id`, `order_seed`, `dt_nominal_s`, `dt_tick_s`, `p_peak_w`, `u_edge_j`,
`budget_fit_j`, `budget_pred_j`, `u_bias_j`, `bias_w`, `z_resid`,
`hull_margin_tok`, `coverage_tier`, `sparse_support`, `thin_support`,
`out_of_coverage`, `bootstrap_seed`, `validation_bias_pass`, `chain_status`.

Grandezze che compaiono in questo formulario e che **nessun punto ha ancora
messo in elenco**: le tre repliche pre e le tre post di F.1 (oggi il CSV salva
una sola cifra in `idle_power_w`), `baseline_post_w`, `dP`, `pre_range_w` di F.3,
`half_range_pre_w`, `half_drift_w`, `budget_base_w`, `budget_base_j` di F.4,
`Δ_sens` di F.5, `share_E0` di F.8. Sono il lavoro principale di P5, insieme a
nomi, tipi e unità di tutto il resto: due di queste — `budget_base_j` e
`r_A` — sono la soglia e il filtro del test di F.12, quindi se non diventano
colonne il gate di P4.5 non è calcolabile dai dati salvati.
