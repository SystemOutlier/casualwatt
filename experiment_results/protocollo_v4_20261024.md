# Protocollo v4 — decisioni congelate

Documento di lavoro. Ogni punto si definisce, si congela e si salva con un commit
separato. Le decisioni valgono per l'esperimento v4; la produzione non cambia
finché la v4 non produce evidenza. Nessun push automatico.

Data: 2026-10-24. Branch: `energy-consumption-framework-ollama-d248a`.

| punto | oggetto | stato |
|---|---|---|
| P1 | baseline e calibrazione idle | **congelato 2026-10-24** (emendato: sensibilità post-hoc) |
| P2 | token effettivi e terminazione | aperto |
| P3 | geometria, modello e stima | aperto |
| P4 | incertezza e validazione | aperto |
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
riguarda il protocollo di campionamento, non l'estimatore.
