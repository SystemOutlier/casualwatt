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
| P4 | incertezza e validazione | **congelato 2026-10-24** (budget completo con termine di bordo; campagna load-versus-control; fasce A/B/C; bootstrap stratificato) |
| P5 | campi CSV e runner | aperto |
| P6 | esecuzione e analisi | aperto |

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

Niente per P1. I numeri 0,5 W (settling), 1,0 W (range) e 10% (drift) sono
soglie operative dichiarate, non costanti scientifiche; restano quelle anche dopo
i dati. La sensibilità di P1.10 si esegue in P6, non qui. Il changelog di P1.11
riguarda il protocollo di campionamento, non l'estimatore. Il riferimento MDPI
non leggibile (HTTP 403) resta escluso e non è un punto aperto: è materiale non
citabile finché non verificato.

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

### P4.1 Decisione in una riga

> Ogni numero pubblicato della v4 esce con tre cose: il budget completo
> `u_tot = sqrt(u_base² + u_within² + u_edge²)`, la fascia di copertura A/B/C, e
> — per la differenza incrementale — l'esito del test load-versus-control. La
> sottrazione di baseline è validata su questa macchina se il bias misurato a
> incremento nullo sta dentro il budget; se non ci sta, il bias si dichiara, si
> aggiunge al budget, e P1 non cambia senza nuova evidenza.

### P4.2 Perché serve un punto separato

P1.7 dichiara il solo contributo di baseline e P3.8 dichiara i pesi del fit:
nessuno dei due è l'incertezza di un numero pubblicato. Mancano tre pezzi.

1. **Il bordo della finestra.** I bordi cadono quasi sempre fra due campioni e
   il contatore cumulativo è interpolato linearmente
   (`energy_session.py:1103-1124`). Su finestre di pochi secondi, con una cadenza
   reale di 0,28–0,34 s, questo termine non è trascurabile e finora non era
   scritto da nessuna parte.
2. **La copertura.** La superficie è fittata su un rettangolo (P3.5) e il punto
   operativo reale sta sotto quel rettangolo. P3.13 rimandava qui le regole di
   extrapolazione.
3. **Il bias della sottrazione.** Nessun confronto fra due letture dello stesso
   registro può arbitrarlo: LHM, EMI e SRUM leggono tutti
   `MSR_PKG_ENERGY_STATUS`. Serve un test a incremento nullo per costruzione.

### P4.3 Definizioni

| termine | simbolo | definizione |
|---|---|---|
| blocco di carico | — | blocco con le `m = 3` richieste di inferenza (P3.7) |
| blocco di controllo | — | blocco identico per struttura, stato macchina e durata, **senza alcuna richiesta** |
| bias di sottrazione | `bias_w` | incremento netto medio dei blocchi di controllo, in watt; atteso zero per costruzione |
| termine di bordo | `u_edge,b` | incertezza dell'interpolazione lineare ai due bordi della finestra, in joule |
| budget completo | `u_tot,b` | combinazione conservativa dei tre termini, in joule |
| fascia di copertura | A / B / C | regime in cui cade un punto di valutazione rispetto al disegno misurato |
| penalità di extrapolazione | `u_extrap` | errore relativo misurato in validazione (P3.10), riusato come allargamento dell'intervallo in fascia B |

### P4.4 Campagna di validazione load-versus-control

Provenienza: `baseline miglioramenti.DOCX` §3, "Livello 2" — materiale utente,
valutato contro P1. Le sue raccomandazioni sulla nomenclatura del semi-range,
sulla registrazione delle tre repliche e sulla separazione dei tre valori erano
già congelate (P1.7, P1.5 passo 3, P1.3); la campagna di controllo invece è
nuova ed è l'unico test **diretto** della sottrazione.

Disegno:

- campagna separata, eseguita **prima** della campagna principale, come gate;
- 3 coppie; ogni coppia = 1 blocco di carico + 1 blocco di controllo;
- ordine dentro la coppia e ordine delle coppie randomizzati, seed registrato
  (`order_seed`);
- geometria: il punto di conferma `(12,32)` di P3.5, cioè la geometria operativa
  reale, con terminazione naturale come nel blocco di produzione;
- durata: `dt_nominal_s` fissato **prima** della campagna come 3 × la mediana
  della durata di richiesta misurata nel pilota di P2. Il blocco di controllo
  attende quella durata senza inviare richieste. Lo scarto fra nominale e
  misurato non crea bias: ciascun blocco sottrae `P_pre · Δt_W` con il **proprio**
  `Δt_W` misurato, quindi l'atteso del controllo è zero per ogni durata;
- stato macchina: identico a P1.4 (`keep_alive = -1`, modello residente e caldo,
  GUI di LibreHardwareMonitor chiusa, processi concorrenti dichiarati);
- struttura di baseline: identica a P1.5, tre finestre pre da 30 s e tre post da
  30 s, **anche** sul blocco di controllo;
- per ciascun blocco di controllo si calcola
  `E_net,control = E_pkg_gross − P_pre · Δt_W`, con lo stesso codice di
  produzione e senza troncamento.

### P4.5 Criterio del test

```
per blocco:  passa se  |E_net,control,c| ≤ budget_base_j,c              (P1.7)
aggregato:   bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c
             sui soli blocchi con r_A ≤ 10%                              (P1.6)
             passa se  |bias_w| ≤ mediana_c(budget_base_w,c)
```

- **Se passa**: la sottrazione di P1 è validata su questa macchina nel senso
  dichiarato in P4.9, e `u_bias = 0`.
- **Se non passa**: `u_bias = |bias_w| · Δt_W` entra in `u_tot` (P4.6), il bias è
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

```
u_tot,b²  = u_base,b² + u_within,b² + u_edge,b²            # per blocco, in joule
u_base,b  = Δt̄_W,b · budget_base_w,b                        # P1.7, P3.8
u_within,b = semi-range(E_act,i nel blocco)                  # P3.8, non diviso per √m
u_edge,b  = Δt_tick,b · P̄_net,b                             # due bordi, mezzo tick ciascuno
```

`Δt_tick,b` è l'intervallo **misurato** del buffer EMI nel blocco, non quello
dichiarato da `POWER_SAMPLE_INTERVAL_S = 0.05` (`energy_session.py:80`): sul
percorso di produzione è 0,28–0,34 s. `P̄_net,b` è la potenza netta media del
blocco. Ciascun bordo cade fra due campioni e il cumulativo è interpolato
linearmente, quindi l'errore di un bordo è al più metà dell'energia netta di un
tick; due bordi danno un tick intero. È un limite superiore conservativo, non una
propagazione di varianza — la stessa regola di P1.7.

Regole:

- i **pesi del fit restano quelli congelati in P3.8** (`w_b = 1/budget_b²` con
  `budget_b² = u_base,b² + u_within,b²`). P4 non riapre P3. Come sensibilità si
  rifà il fit con `w_b = 1/u_tot,b²` e si riporta lo spostamento dei coefficienti:
  se resta dentro l'intervallo bootstrap, la scelta dei pesi è dichiarata non
  influente;
- ogni numero **pubblicato** — `J/token`, previsione su un punto, contributo di un
  coefficiente — esce con `u_tot`, mai con il solo `u_base`;
- per le finestre idle da 30 s il termine di bordo si trascura e si dichiara:
  0,3 s su 30 s è l'1% della finestra e la potenza netta in idle è per
  costruzione prossima a zero;
- `u_edge` è anche l'argomento quantitativo dello sviluppo 3 del cap. 6: il probe
  a 50 ms mostra che il registro si aggiorna a quella cadenza, quindi `Δt_tick` è
  riducibile di un fattore ~6 per via software, e questo termine con esso.

### P4.7 Fasce di copertura

Il rettangolo del fit è `32 ≤ N_in ≤ 512`, `32 ≤ N_out ≤ 256` (P3.5). Il
rettangolo **esteso** è quello coperto dai punti effettivamente misurati, griglia
più i due punti di conferma `(12,32)` e `(256,192)`: `12 ≤ N_in ≤ 512`,
`32 ≤ N_out ≤ 256`.

- **Fascia A — interpolazione.** Il punto è dentro il rettangolo del fit. Si
  riporta `E_pred` con l'intervallo di P4.8. Verificata dal punto di conferma
  `(256,192)`, che sta dentro il rettangolo ma non è un nodo della griglia.
- **Fascia B — estrapolazione coperta.** Il punto è fuori dal rettangolo del fit
  ma dentro il rettangolo esteso, cioè `12 ≤ N_in < 32` con
  `32 ≤ N_out ≤ 256`. Si riporta `E_pred` con il flag `extrapolated`,
  l'intervallo allargato di `u_extrap`, e l'avvertenza che in questa fascia il
  valore è dominato da `E0 + a·N_in`, i termini che il disegno vincola meno.
  **Il punto operativo reale e il blocco di produzione cadono in fascia B**, e il
  `J/token` di produzione va pubblicato con quel flag.
- **Fascia C — fuori copertura.** Tutto il resto, inclusa qualsiasi richiesta con
  `N_in > 512` o `N_out > 256`. Il modello è lineare nei parametri e
  extrapolerebbe senza protesta: non si pubblica nessun numero del modello. Si
  riporta solo il rapporto descrittivo `E_act/N_out_actual` del blocco misurato,
  marcato `out_of_coverage`.

La penalità non è inventata: è l'errore relativo misurato in validazione.

```
u_extrap = E_pred · max(err_rel dei due punti di conferma)          # P3.10
intervallo_B = [q2.5 − u_extrap, q97.5 + u_extrap]
```

Quindi `u_extrap` esiste solo dopo P3.10. Se un punto di conferma fallisce la
validazione, `u_extrap` non è definito e la fascia B non pubblica previsioni: si
riporta il fallimento.

Conseguenza dichiarata: la v4 non pubblica un `J/token` per prompt lunghi, che è
esattamente ciò che la letteratura analitica chiede
(`cavagna2026sweetspot`). Estendere la griglia verso l'alto è lavoro della v5,
non una regola di extrapolazione.

### P4.8 Intervallo di previsione: bootstrap stratificato

```
unità di ricampionamento : il blocco, non la richiesta — l'errore di baseline è
                           comune alle m richieste del blocco (P3.8)
strati                   : i 10 punti di disegno; dentro ogni strato si
                           ricampionano i blocchi con reintroduzione, mantenendo
                           la numerosità del punto (3; 6 per il centro)
repliche                 : 2000, congelate
per ciascuna replica     : rifit WLS con gli stessi pesi w_b di P3.8 — i pesi non
                           si ricalcolano dentro il bootstrap, altrimenti
                           l'intervallo dipenderebbe dal rumore del budget e non
                           da quello dei dati
previsione               : E_pred*(x) al punto di valutazione; q2.5 e q97.5 dei
                           2000 valori
seed                     : fissato e registrato (bootstrap_seed)
```

Cosa è e cosa non è:

- i quantili bootstrap descrivono la variabilità della **superficie stimata**; la
  dispersione delle tre misure del punto di conferma entra a parte, come `2·u_conf`
  in P3.10, con `u_conf` = semi-range non diviso per `√3`;
- il bootstrap per batch non si usa: 3 batch sono troppo pochi cluster (già in
  P3.8);
- gli errori standard HC3 si riportano accanto come approssimazione lineare e si
  confrontano con l'ampiezza bootstrap: se differiscono di più di un fattore 2, il
  bootstrap resta primario e la discrepanza si dichiara — è il sintomo di una
  superficie mal condizionata o di un blocco influente (P3.9);
- il bootstrap non sostituisce il lack-of-fit di P3.9: un modello inadeguato ha un
  intervallo stretto e sbagliato.

### P4.9 La catena è validata anello per anello

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

### P4.10 Cosa non è deciso qui

- P5 fissa nomi e tipi delle colonne. P4 elenca i contenuti nuovi obbligatori:
  `block_kind` ∈ {`load`, `control`}, `pair_id`, `order_seed`, `dt_nominal_s`,
  `dt_tick_s`, `p_net_mean_w`, `u_edge_j`, `u_bias_j`, `u_tot_j`, `bias_w`,
  `extrapolation_tier` ∈ {`A`, `B`, `C`}, `u_extrap_j`, `coverage_flag`,
  `bootstrap_seed`, `validation_bias_pass`;
- P6 fissa l'ordine di esecuzione — la campagna di P4.4 sta prima della principale
  e ne è il gate — e gli script di analisi;
- il wattometro: la scala assoluta resta non arbitrata (cap. 6, sviluppo 1);
- Linux/RAPL: il disegno di P4.4 è indipendente dal backend e si applica a RAPL
  con gli stessi criteri, ma in v4 non è eseguito. Il backend Linux è
  implementato, non validato su questa campagna;
- la deviazione standard campionaria con n = 3 **non si adotta**: con tre repliche
  non è una stima utilizzabile di varianza, e affiancarla al semi-range invita a
  trattarla come tale. Restano registrati i tre valori, la mediana, il minimo, il
  massimo e il range (già in P1.5 e P1.7).

### P4.11 Ancoraggi

- interpolazione ai bordi: `energy_session.py:1103-1124` (`_emi_cum_at`),
  `:1126-1148` (`_emi_field_at`), `:2188-2205` (`_interpolate` sui campioni di
  sistema);
- cadenza dichiarata: `energy_session.py:80` (`POWER_SAMPLE_INTERVAL_S = 0.05`);
- finestre di energia: `energy_session.py:1194` (`emi_window_energy_j`), `:1261`
  (`pi_window_energy_j`); lettura finestra idle: `:1576`;
- bug del sensore omonimo e fix: guard sul tipo a `energy_session.py:951-955`,
  selezione del sensore package a `:855-915`, commit `1422d1b`;
- budget e pesi: P1.7, P3.8; validazione della superficie: P3.10; sensibilità
  post-hoc: P1.10; controlli di drift: P1.6;
- artefatti della catena: `four_way_finestra_uguale_20261023_analisi.md`,
  `srum_emi_cross_20261023_analisi.md`,
  `idle_floor_sensitivity_20261023_analisi.md`, `emi_50ms_probe_20261023_*`;
- provenienza della campagna di controllo: `baseline miglioramenti.DOCX` §3
  (materiale utente, valutato contro P1: nomenclatura, registrazione delle
  repliche e separazione dei tre valori erano già congelati).

### P4.12 Aperto

Niente per P4. Due esiti possono riaprirlo, e sono risultati di P6, non decisioni
aperte:

- se il test di P4.5 fallisce anche nella ripetizione, `u_bias` entra nel budget e
  la tesi dichiara che la sottrazione non è validata su questa macchina;
- se il pre-pilota di P3.15 mostra che un livello della griglia non è
  raggiungibile, il rettangolo di P4.7 cambia e con esso le fasce.
