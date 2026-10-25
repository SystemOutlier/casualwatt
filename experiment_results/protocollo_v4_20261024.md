# Protocollo v4 — decisioni congelate

Documento di lavoro. Ogni punto si definisce, si congela e si salva con un commit
separato. Le decisioni valgono per l'esperimento v4; la produzione non cambia
finché la v4 non produce evidenza. Nessun push automatico.

Data: 2026-10-24. Branch: `energy-consumption-framework-ollama-d248a`.

| punto | oggetto | stato |
|---|---|---|
| P1 | baseline e calibrazione idle | **congelato 2026-10-24** (emendato: sensibilità post-hoc; letteratura e confronto CodeCarbon; terza emenda di forma — motivazione causale del pre applicato in P1.14/F.2, e forma di combinazione di `budget_base_w` dichiarata decisione operativa provvisoria con rinvio motivato ai dati del pilota P2.9: P1.7, P1.13. **Emenda sostanziale del 2026-10-24**: chiuso il difetto `E_trunc`, definito `E_net_abs,b`/`E_net_abs,p` come denominatore di `r_A`/`r_B`, P1.6 e F.3) |
| P2 | token effettivi e terminazione | **congelato 2026-10-24** |
| P3 | geometria, modello e stima | **congelato 2026-10-24** (emendato di forma il 2026-10-24 dopo la revisione esterna: P3.3 costi marginali qualificati a `N_out = 0` / `N_in = 0` e algebra del termine quadratico omesso; P3.10 `E_pred ≤ 0` dichiarato fallimento con `pred_nonpositive` e intervallo rinominato `intervallo_conf`; P3.12/P3.13 `design_deviation_count`; P3.15 pre-pilota esteso ai livelli bassi. **Emenda sostanziale del 2026-10-24**: P3.9, il criterio dell'anello 5 usa `p_lof_perm`, `p` della stessa statistica F pesata ottenuto dalla distribuzione nulla per ricampionamento del puro errore — il `p` asintotico non è valido con pesi conservativi. Statistica e soglia 0,05 invariate, aggiunto `lof_max_rel` descrittivo. **Aggiunta del 2026-10-25, di sola dichiarazione**: all'elenco dei contenuti obbligatori di P3.13 si aggiungono `pre_range_w` e `dP`, grandezze già definite in F.1 e F.3 e già usate da tre flag, perché un flag i cui ingressi non sono registrati non è verificabile da un terzo (P4.12). **Terzo turno, 2026-10-25, ancora di sola dichiarazione**: `design_deviation_count` dichiarato **per blocco** e non per cella, con soglia di discussione `m` per blocco e `3m` per cella (P3.12) e campo aggiunto all'elenco di F.17, che lo ometteva; costi marginali scritti con la propria coordinata anche in P3.11 e nello pseudocodice di F.14 (P3.3 e P3.4 li qualificavano già, P4.8 e F.8 corretti nello stesso turno); punto con `pred_nonpositive` dichiarato **nel conteggio dei casi valutati**, non solo "non escluso dal criterio" (P3.10). Nessuna modifica a disegno, modello, pesi o soglie) |
| P4 | incertezza e validazione | **congelato 2026-10-24** (emendato: inviluppo convesso per la copertura, bootstrap dei residui standardizzati, criterio monolitico di catena, `u_edge` solo nel budget predittivo; seconda emenda solo di forma: P4.1 in quattro clausole, P4.4 a otto requisiti numerati con la baseline 3 pre + 3 post obbligatoria anche sui controlli; terza emenda solo di forma: seconda ragione in P4.12 per non adottare la deviazione standard a n = 3; quarta emenda solo di forma: P4.6, rettificata la giustificazione di `u_edge` — il termine congelato maggiora il disallineamento, non l'interpolazione — con formula e valore invariati. **Emenda sostanziale del 2026-10-24**: chiuso il difetto di `r_A` sui controlli — il requisito 7 di P4.4 elenca ora solo le quantità che esistono su un blocco di controllo, e il filtro di stabilità di P4.5 è sostituito dalle soglie assolute `pre_range_w,c ≤ 1,0 W` e `|dP_c| ≤ 1,0 W` con il flag `control_unstable`; `u_bias,b = |bias_w| · Δt̄_W,b` scritto in formula in P4.6 e F.11 come contributo di incertezza, non come correzione sistematica; copertura decisa su due inviluppi — `hull_design` sui target e `hull_fit` sui token reali dei 33 blocchi di fit — prendendo la fascia più conservativa, P4.7 e F.13. **Seconda emenda sostanziale del 2026-10-24**: P4.8, la copertura del bootstrap è dichiarata *nominale e non arbitrata* finché P6.4 non la verifica per simulazione, e la correzione di leva `1/√(1 − h_b)` è resa **sensibilità obbligatoria** allo stesso seed del primario — leva massima verificata sul disegno nominale 0,2852 sui blocchi (512, 256), fattore 1,1828, media 0,121212 = 4/33. Il primario non cambia e nessuna formula congelata è modificata. **Terza emenda sostanziale del 2026-10-24**: P4.4/P4.5, il gate load-versus-control passa da tre a **sei coppie** (12 blocchi) e il quorum dei controlli utilizzabili da due a **quattro**, stessa frazione congelata `⌈2/3 · n_coppie⌉`; `bias_w` si riporta anche in unità di metrica (coppia di campi `bias_jtok_pct_lo`/`bias_jtok_pct_hi`) con la scala ancorata 1 W ≈ 6–11% di `J/token`, grandezza riportata e non soglia; intervallo t e test di equivalenza a ±3–5% valutati e **non** adottati, con il limite dichiarato che un gate passato non dimostra quell'equivalenza (0,27–0,83 W sulla stessa scala). Costo in P6.1: pavimento 2 h 15 min → **2 h 33 min**. Soglie in watt invariate. **Quarta emenda sostanziale del 2026-10-24**: P4.6, chiusa l'alternativa aperta sul termine di bordo — adottata la via (b), lettura sincrona del contatore ai bordi di finestra con `Δt_W` preso dalla stessa coppia di letture, come requisito vincolante di P5; la via (a) è scartata perché chiede un `ΔP_tick` che nessuna parte del codice misura. Formula e valore congelato di `u_edge,b` invariati: cambia solo cosa è `Δt_tick,b`, e il fattore di riduzione si misura, non si assume. **Quinta emenda, di sola dichiarazione (2026-10-25)**: specificata la metrica di `hull_margin_tok` e `hull_margin_design_tok` (distanza perpendicolare euclidea dalla retta dello spigolo più vicino, coordinate grezze, negativa se fuori) e verificata per esecuzione sui quattro margini pubblicati (1,33 / 64,0 / 21,24 / 107,7), perché con la distanza dal vertice il punto operativo (12,32) darebbe 28,28 e il flag `thin_support` si rovescerebbe; coordinate normalizzate valutate e **non** adottate, decisione metodologica distinta; `pre_range_w` e `dP` entrano nei contenuti obbligatori di P4.12, senza i quali `control_unstable` registra un esito i cui ingressi non sono leggibili; dichiarata la scala di `budget_fit_b`/`budget_pred_b` (joule sulla scala di `Ē_b`, non del totale di blocco) e scartata la lettura a durata aggregata; il passo 5 di F.0 distingue i controlli di stabilità sui blocchi di carico dal filtro assoluto di P4.5 sui blocchi di controllo. **Sesta emenda, di sola dichiarazione e di provenienza (2026-10-25, terzo turno)**: i numeri dei tre errori di bordo di P4.6 sono rigenerati da un harness tracciato (`u_edge_interpolazione_probe.py`, 5/5 verifiche, exit 0) e il residuo assoluto `3,0e-11 J` è **ritirato**, perché era l'assoluto di una griglia non dichiarata e cresce con la densità di griglia; al suo posto il residuo **relativo** alla grandezza del contatore, 7,0e-12, invariante in `P` e dichiarato con la griglia usata; il ritiro vale in **entrambe** le occorrenze, P4.6 e F.11 — la seconda trovata dal controllo incrociato del terzo turno, che ha mostrato il ritiro incompleto. Costi marginali scritti con la propria coordinata anche in P4.8. Nessuna formula cambiata, nessuna soglia spostata, nessun valore numerico congelato modificato. **Nessun difetto dichiarato aperto, nessuna alternativa aperta**) |
| P5 | campi CSV e runner | aperto (requisiti vincolanti trasmessi dai punti congelati: P6.5, fra cui la lettura sincrona del contatore ai bordi, `Δt_W` dalla stessa coppia di letture e il livello di aggregazione dei conteggi di token) |
| P6 | esecuzione e analisi | aperto, ma **non più solo preparatorio**: P6.1 e P6.2 sono aritmetica dei punti congelati (P6.1 ricalcolato il 2026-10-24 per le sei coppie del gate: pavimento delle sole finestre idle 2 h 33 min); P6.3 (audit idle) e P6.4 (simulazione Monte Carlo) sono **adottate come requisiti vincolanti**; P6.5 è l'elenco dei requisiti per P5 |

**Nove difetti dichiarati nel testo congelato, tutti chiusi.** Quattro registrati
il 2026-10-24, un quinto emerso il 2026-10-25 verificando gli ancoraggi del
secondo turno, quattro registrati e chiusi il 2026-10-25 nel terzo turno. Trovati
leggendo il protocollo contro se stesso e contro il codice, su segnalazione di
revisori esterni o verificando le loro segnalazioni. Sono stati registrati **nel
punto in cui stavano**, con le opzioni e la raccomandazione, prima di essere
corretti, perché correggerli cambia una decisione congelata: la correzione è un
emendamento dichiarato, non una riscrittura silenziosa. La tabella resta come
registro — dice cosa bloccava ciascuno e con quale regola è stato chiuso:

| difetto | dove | cosa bloccava | stato |
|---|---|---|---|
| `E_trunc` usato e mai definito | P1.6, F.3 | `r_A`, `r_B`, `baseline_unstable`, `bias_w`, anello 4 di P4.9 | **chiuso 2026-10-24**: definito `E_net_abs,b = m · |Ē_b|`, il nome `E_trunc` è ritirato |
| `r_A` non calcolabile su un blocco di controllo, che non invia richieste | P4.5, F.12 | il gate load-versus-control e l'anello 4 di P4.9 | **chiuso 2026-10-24**: filtro sostituito dalle soglie assolute `pre_range_w,c ≤ 1,0 W` e `|dP_c| ≤ 1,0 W`, flag `control_unstable` |
| `u_bias` dichiarato nel budget, assente dalla formula, e senza `Δt_W` specificato | P4.6, F.11 | il campo obbligatorio `u_bias_j` (P4.12) | **chiuso 2026-10-24**: `budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²` con `u_bias,b = |bias_w| · Δt̄_W,b` (contributo di incertezza, non correzione sistematica) |
| copertura classificata sui target, fit stimato sui token reali | P4.7, F.13 | coerenza di `coverage_tier` e `hull_margin_tok` con `x1_b`, `x2_b` | **chiuso 2026-10-24**: due inviluppi, `hull_design` (target, pre-registrato) e `hull_fit` (reali, dai 33 blocchi); il punto si classifica su `(x1_b, x2_b)` e si prende la fascia più conservativa |
| metrica di `hull_margin_tok` non specificata: "distanza dal bordo" senza dire quale distanza | P4.3, P4.7, F.13, P6.5 | il flag obbligatorio `thin_support` (soglia 2 token) e i quattro margini pubblicati | **chiuso 2026-10-25**: distanza perpendicolare euclidea dalla retta dello spigolo più vicino, coordinate grezze (token, token), negativa se fuori; ricalcolata per esecuzione (1,33 / 64,0 / 21,24 / 107,7). Con la distanza dal vertice `(12,32)` darebbe 28,28 invece di 1,33 e `thin_support` si rovescia |
| numeri di `u_edge` citati da un calcolo non tracciato, e residuo assoluto dichiarato senza griglia | P4.6, F.11 | l'evidenza dei tre errori di bordo: per AGENTS.md un'analisi non tracciata è un numero che nessuno può rigenerare, quindi non è evidenza | **chiuso 2026-10-25**: harness tracciato `u_edge_interpolazione_probe.py` (5/5 verifiche, exit 0). Il residuo `3,0e-11 J` è **ritirato** perché era l'assoluto di una griglia non dichiarata e cresce con `n`; al suo posto il residuo **relativo** alla grandezza del contatore, 7,0e-12 a `P = 35 W`, `Δt_tick = 0,30 s`, `n = 2 000 001`, invariante in `P`. Formula e valore congelato di `u_edge,b` invariati. **Chiuso in due tempi**: la prima stesura ritirava il numero in P4.6 e lasciava in F.11 la stessa cifra, quindi il ritiro era incompleto; l'ha trovato il controllo incrociato del terzo turno (2026-10-25) e la seconda occorrenza è ritirata. Un numero ritirato nel punto congelato e ancora vivo nell'elenco derivato è peggio di un numero sbagliato in un punto solo, perché il formulario è ciò che un implementatore copia |
| costi marginali elencati senza la coordinata a cui si riferiscono, e in ordine inverso rispetto ad `a`/`b` | P3.11, P4.8, F.8, **F.14** (trovata dal controllo incrociato del terzo turno) | quale dei due coefficienti rappresenta il numero pubblicato: `b + c·N_in,ref` è `∂E/∂N_out`, non `∂E/∂N_in` | **chiuso 2026-10-25**: scritti come `∂E/∂N_in = a + c·N_out,ref` e `∂E/∂N_out = b + c·N_in,ref` in tutte le occorrenze. P3.3 (`:887`) e P3.4 (`:928-929`) li qualificavano già, gli elenchi delle metriche no. Le occorrenze sono **quattro**, non tre: la quarta è lo pseudocodice di F.14 (`:3007`), che elencava `b + c·N_in,ref ; a + c·N_out,ref` senza derivata davanti, ed è stata trovata dal controllo incrociato del terzo turno dopo che la chiusura era già stata dichiarata — stessa dinamica del ritiro di `3,0e-11 J` in F.11 |
| `design_deviation_count` senza unità dichiarata (cella o blocco) e assente dall'elenco derivato di F.17 | P3.12, P3.13, F.17 | la soglia di discussione: `m = 3` è per blocco e una cella ha 3 blocchi, quindi "conteggio di cella paragonabile a `m`" confronta due unità diverse | **chiuso 2026-10-25**: il campo è **per blocco**; il valore per cella è la somma dei tre blocchi e va confrontato con `3m`. Aggiunto all'elenco di F.17, che ripeteva P3.13 omettendolo |
| punto con `pred_nonpositive` dichiarato fallimento, ma non dichiarato che resta nel conteggio dei casi valutati | P3.10, F.10 | il denominatore dell'anello 6 di P4.9: un punto scartato in silenzio ridurrebbe i casi valutati da due a uno | **chiuso 2026-10-25**: scritto che il punto **resta nel conteggio**, che i punti di conferma sono due e che l'anello 6 li richiede entrambi, quindi il caso non è né diluito in una media né tolto dal denominatore |

Valutazione completa, con le verifiche numeriche eseguite:
`revisione_esterna_formule_20261024_valutazione.md` (primo turno),
`revisione_esterna_20261025_secondo_turno_valutazione.md` (secondo turno) e
`revisione_esterna_20261025_terzo_turno_valutazione.md` (terzo turno). Nessuno dei
primi cinque era cosmetico: ognuno lasciava una formula o un campo con due letture
possibili, che è esattamente ciò che un implementatore risolve in silenzio
scegliendone una. Il quinto non viene dalla revisione del 2026-10-24: è emerso il
2026-10-25 verificando gli ancoraggi del secondo turno, ed è quello in cui le due
letture della stessa frase danno due esiti **opposti** di un flag già congelato
(`thin_support`), con un fattore 21,3 sul numero pubblicato. Due chiusure vanno
oltre la raccomandazione dei revisori: il filtro dei controlli limita anche la
circolarità (P4.5), e la copertura usa **due** inviluppi invece di spostare solo il
punto sulla base reale (P4.7). Con tutti e nove chiusi, il runner di P5 può essere
scritto contro formule che ne hanno una sola.

I quattro del terzo turno sono di natura diversa e vanno detti come tali: **non
riaprono nulla**, perché le sette osservazioni di quel revisore descrivevano difetti
già chiusi il 2026-10-24 — la separazione dei tre errori di bordo, il
`pred_nonpositive`, il nome dell'intervallo operativo di conferma, la qualifica di
`a` e `b` a coordinata nulla, il conteggio delle sostituzioni, il pre-pilota esteso
ai livelli bassi, il ruolo di `c` come assorbitore parziale di una componente
quadratica. I quattro difetti sono emersi **verificando** quei rilievi, non dai
rilievi: tre sono ambiguità residue in punti diversi da quelli già corretti (le
metriche di P3.11 e P4.8, l'unità di `design_deviation_count`, il conteggio dei casi
valutati), uno è un elenco derivato che ometteva un campo obbligatorio (F.17), e uno
è di **provenienza**: i numeri di P4.6 venivano da un calcolo non tracciato, quindi
non erano evidenza. Il revisore stesso lo segnalava, scrivendo che senza accesso al
codice e alla procedura di calcolo non li avrebbe presentati come verifica
indipendente. Il controllo incrociato che quel revisore chiedeva in chiusura ha
poi trovato ciò che la lettura dei suoi punti non aveva trovato: il residuo
ritirato in P4.6 era ancora pubblicato in F.11, e lo stesso controllo ne ha
trovate sbagliate altre quattro nelle tabelle degli artefatti. Ritiri e correzioni
vanno eseguiti su **tutte** le occorrenze, cercandole e non ricordandole: è la
terza conferma che verificare ancoraggi e provenienza batte leggere le proposte.

Le formule di P1–P4 sono raccolte, con applicazione e giustificazione, nella
sezione finale **Formulario consolidato (F.0–F.17)**: è una sezione derivata, non
introduce decisioni e in caso di divergenza vince il punto congelato. La sezione
**P6 — Esecuzione e analisi** che la precede è anch'essa derivata e dichiarata
aperta: contiene solo vincoli che P1–P4 già impongono all'esecuzione, e in caso di
divergenza vincono i punti congelati.

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
| energia netta assoluta di blocco | `E_net_abs,b` | J | `|Σ_{i∈blocco} E_net_incremental,i| = m · |Ē_b|` (P1.6) |
| energia netta assoluta di punto | `E_net_abs,p` | J | `|Σ_{i∈punto} E_net_incremental,i|` (P1.6) |

- **`E_trunc` non è un termine di questo protocollo.** Compariva come denominatore
  di `r_A` e `r_B` nella prima versione congelata senza essere definito, ed era
  l'eredità del troncamento di produzione che la v4 ha abbandonato (P1.3, F.2). È
  sostituito da `E_net_abs`. Se compare in un documento, in un codice o in una
  tabella, è un referto di una versione precedente e va corretto.
- Il valore assoluto sta **fuori** dalla somma: le singole `E_net_incremental,i`
  restano firmate e nessuna viene clampata. `E_net_abs` è un denominatore, non una
  grandezza pubblicata.

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
E_net_abs,b = |Σ_{i∈blocco} E_net_incremental,i|  =  m · |Ē_b|
E_net_abs,p = |Σ_{i∈punto}  E_net_incremental,i|

r_A = |dP| · Σ_{i∈blocco} Δt_W,i / E_net_abs,b
r_B = |dP| · Σ_{i∈punto}  Δt_W,i / E_net_abs,p
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

**Denominatore di `r_A` e `r_B`: definizione chiusa il 2026-10-24** (emendamento
al punto congelato; prima era un difetto dichiarato). Il simbolo usato nella
versione congelata era `E_trunc`, che **non era definito in nessuna parte del
protocollo**: quattro occorrenze, tutte d'uso (P1.6 e F.3), nessuna di definizione,
e nessuna voce nella Terminologia. Il nome veniva dalla produzione, che tronca due
volte (`local_energy.py:300` e `:309-310`); la v4 non tronca (P1.3, P3.2, F.2),
quindi era l'eredità di un metodo che il protocollo ha abbandonato. Tre letture
erano possibili e danno comportamenti diversi:

| candidato | denominatore | conseguenza se `Σ E_net < 0` |
|---|---|---|
| `Σ E_net_incremental,i` firmato | può essere ≤ 0 | `r_A ≤ 0` passa sempre: il filtro è cieco |
| `|Σ E_net_incremental,i|` | ≥ 0 | `r_A` esplode quando il blocco non ha segnale |
| `Σ |E_net_incremental,i|` | > 0 | confronta il drift con una grandezza che non entra nel fit |

**Scelta: la seconda.** `E_net_abs,b = |Σ_{i∈blocco} E_net_incremental,i| =
m · |Ē_b|`, e analogamente `E_net_abs,p` sul punto. Motivi, tutti verificabili nel
protocollo:

- è l'unica coerente con "nessun troncamento" (P1.3, F.2): il valore assoluto sta
  fuori dalla somma, quindi le singole `E_net_incremental,i` restano firmate e
  nessuna viene clampata;
- è la grandezza che entra davvero nel fit, perché F.7 stima su `Ē_b` e
  `m · |Ē_b|` ne è una funzione diretta. La terza candidata (`Σ |E_net,i|`)
  confronterebbe il drift con una grandezza che il modello non usa;
- rende `r_A ≥ 0` sempre, quindi il filtro `≤ 10%` non diventa cieco quando la
  somma è negativa, che era il difetto della prima candidata;
- dà un senso preciso alla regola già congelata "denominatore zero → blocco
  invalido per costruzione": un blocco la cui energia netta media è zero non porta
  informazione, e il drift non è valutabile in rapporto a nulla.

Il simbolo `E_trunc` **non si usa più**: è eliminato da P1.6, da F.3 e da ogni
altra occorrenza, ed è sostituito da `E_net_abs`. La voce è aggiunta alla
Terminologia. L'emendamento chiude il difetto 1.1 di
`revisione_esterna_formule_20261024_valutazione.md`; le soglie (10%, 5/20%,
0,10 J/token) **non cambiano**.

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
| D7 | criterio ≤ 10% e dentro l'intervallo operativo di conferma (P3.10) |
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
- `a`: J/token di prefill marginale **a `N_out = 0`**;
- `b`: J/token di decode marginale **a `N_in = 0`**;
- `c`: interazione, attesa ≥ 0 perché la KV cache cresce con `N_in` e ogni token
  di decode legge un contesto più lungo.

`a` e `b` da soli non sono costi marginali generali: con l'interazione presente,
`∂E/∂N_in = a + c·N_out` e `∂E/∂N_out = b + c·N_in` (P3.4), quindi il costo
marginale dipende dall'altra coordinata. La qualifica "a `N_out = 0`" / "a
`N_in = 0`" non è una formula nuova: è ciò che la derivata già dice, scritta
dove la parola "marginale" compare da sola.

**Cosa assorbe `c`, e il termine quadratico che il modello non ha** (aggiunta
il 2026-10-24, redazionale: non aggiunge né toglie parametri). Se il costo del
contesto al passo `j` di decode cresce come `N_in + j`, la somma esatta sui
`N_out` passi è

```
Σ_{j=1..N_out} (N_in + j) = N_in·N_out + N_out·(N_out + 1)/2
```

cioè il termine di interazione del modello **più** un termine in `N_out²` che il
modello a 4 parametri non contiene. La stessa giustificazione fisica che fonda
`c ≥ 0` (KV cache crescente) implica quel termine omesso. Non è un motivo per
aggiungerlo — il disegno di P3.5 non lo identifica separatamente da `b` senza
livelli di `N_out` più distanziati, e P3.3 congela l'assenza di quadratici — ma
va scritto che `c` assorbe parte di un effetto che ha anche una componente
quadratica, e che il modello primario è un'**approssimazione dichiarata** della
superficie, non la sua forma fisica. Se il lack-of-fit di P3.9 rifiuta il
modello, questa è la prima spiegazione strutturale da citare.

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
- **riferimento del lack-of-fit** (emendamento del 2026-10-24): il `p` usato
  dall'anello 5 di P4.9 è `p_lof_perm`, ottenuto dalla distribuzione nulla della
  stessa statistica F pesata per ricampionamento, non dal quantile della F
  asintotica. Il `p` asintotico si riporta accanto come `p_lof_asint` ed è
  **indicativo**. Regola e motivazione qui sotto;
- grandezza dell'effetto di lack-of-fit: `lof_max_rel`, scarto relativo massimo fra
  la media di cella e la superficie. È descrittivo, non ha soglia e non è un
  criterio: serve perché un test poco potente può "passare" con uno scarto grande,
  e il lettore deve poterlo vedere;
- intervalli dei coefficienti e loro ampiezza;
- `R²` aggiustato, errore residuo e AIC OLS come diagnostica, mai come criterio
  di accettazione: `R² ≥ 0,9` non basta;
- distanza di Cook: i blocchi influenti si riportano, non si eliminano senza
  dichiararlo;
- segno e ampiezza di `E0`, con il flag `intercept_nonphysical` se serve.

**Perché il `p` del lack-of-fit non è quello asintotico** (emendamento del
2026-10-24, su osservazione della revisione esterna §4.5 — l'osservazione è
corretta, la cura è diversa da quella proposta). L'F-test pesato presume che i pesi
siano l'inverso della varianza. P3.8 dichiara esplicitamente che `w_b = 1/budget_fit_b²`
è "un peso conservativo, non un peso di precisione": i `budget_fit_b` sono limiti
superiori, non stime di σ, e non sono proporzionali fra loro come lo sarebbero delle
varianze. Con pesi che non sono di precisione la statistica non segue la F con
`(6, 23)` gradi di libertà — 6 = punti − parametri = 10 − 4, 23 = Σ_punti (n_p − 1) =
8·2 + 5 + 2, verificato sul disegno di P3.5 — e il `p` asintotico non ha il
significato nominale. L'effetto è asimmetrico e va nella direzione sbagliata: un
`p` troppo grande premia la bassa potenza, e `p ≥ 0,05` è il criterio di
**accettazione** dell'anello 5.

La correzione non cambia né la statistica né la soglia: cambia il riferimento.

```
statistica (invariata):  F_lof = (SS_lof / 6) / (SS_pe / 23)   pesata con w_b

residui di puro errore:  z_pe,b = (r_b − r̄*_{punto(b)}) / budget_fit_b
                          # media zero dentro ogni punto per costruzione: 23 gdl
                          # r̄*_p = Σ_{b∈p} w_b r_b / Σ_{b∈p} w_b , media di cella PESATA
                          # come le medie di cella di SS_lof: stessa base, stessi pesi

replica nulla k = 1..2000:
    Ȳ*_b = f(x_b ; θ̂) + budget_fit_b · z*_b
    z*_b estratto con reintroduzione dal pool GLOBALE dei 23 valori {z_pe,b};
    ciò che la stratificazione preserva è la numerosità del disegno — 3 blocchi per
    punto, 6 al centro — non la provenienza del residuo
    rifit WLS con gli stessi pesi w_b  → θ*_k ,  superficie*_k
    F*_k = (SS_lof(Ȳ* , superficie*_k) / 6) / (SS_pe(Ȳ*) / 23)

p_lof_perm = #{k : F*_k ≥ F_lof} / 2000
p_lof_asint = 1 − F_{6,23}(F_lof)                       # indicativo, si riporta

anello 5 di P4.9:  passa se  p_lof_perm ≥ 0,05
```

Tre ragioni per questa forma e non per un test di permutazione classico:

1. il null è imposto **rigenerando i dati dalla superficie stimata**, non
   permutando i residui fra i blocchi. Permutare `r_b` fra blocchi con
   `budget_fit_b` diversi mescolerebbe scale diverse e distruggerebbe la struttura
   eteroschedastica che il disegno ha;
2. la scala del rumore è quella **osservata**, non il budget: `budget_fit_b · z*_b`
   riproduce lo scatter dentro il punto misurato, quindi la conservativezza dei
   budget si elide e non entra nel riferimento. È la ragione per cui si
   ricampionano i residui di puro errore e non i residui standardizzati di P4.8 —
   questi ultimi contengono anche l'eventuale lack-of-fit reale e gonfierebbero il
   null, rendendo il test conservativo proprio dove deve essere potente;
3. costa zero: le 2000 repliche, la stratificazione per punto, il rifit a pesi
   fissi e il seed registrato sono **gli stessi** di P4.8. Si aggiunge una
   grandezza per blocco (`z_pe,b`) e una statistica per replica (`F*_k`).

Limite dichiarato: il null rigenerato da `f(x_b; θ̂)` presume che la forma
funzionale stimata sia il punto di partenza giusto; con un modello molto sbagliato
i `z_pe,b` restano l'unica fonte di rumore e il riferimento è approssimato. È lo
stesso limite del bootstrap di P4.8, e come quello si dichiara invece di
nasconderlo. Le tre vie alternative valutate e scartate — permutazione sulla
statistica F, scarto massimo relativo con soglia predeclarata, mantenimento
dell'F-test dichiarando il `p` indicativo — sono in
`revisione_esterna_formule_20261024_valutazione.md` §4.5: la seconda introduce una
soglia nuova dopo aver visto il disegno, la terza lascia l'anello 5 senza un
riferimento valido.

### P3.10 Validazione

I due punti di conferma sono misurati nella stessa campagna ma **esclusi dalla
stima**; l'analisi li apre solo dopo che la specifica è congelata e i
coefficienti sono stimati sui soli blocchi di fit. Per ciascun punto, con i 3
blocchi:

```
E_meas  = media dei 3 blocchi
E_pred  = modello ai parametri stimati
err_rel = |E_meas − E_pred| / E_pred                  # solo se E_pred > 0
u_conf  = semi-range(E_meas,1..3)                     # non diviso per √3
intervallo_conf = [q2.5 − 2·u_conf, q97.5 + 2·u_conf] # quantili bootstrap della previsione
```

La validazione passa se `err_rel ≤ 10%` **e** `E_meas` è dentro
`intervallo_conf`. Il 10% è la stessa scala della sensibilità della baseline
(1 W ≈ 6–11% di J/token), non una soglia scientifica. Se fallisce, si dichiara il
fallimento: non si rifà il fit sui punti di conferma e non si sceglie un altro
modello sui dati di validazione. In quel caso `J/token` resta quello del modello,
marcato `validation_failed`, e si riporta anche il rapporto descrittivo del blocco
di produzione (P6).

**Denominatore non positivo** (aggiunta il 2026-10-24, redazionale: chiude una
lacuna, non cambia il criterio). `err_rel` richiede `E_pred > 0`. `E0` è libero
di essere negativo e P3.3 prevede esplicitamente `intercept_nonphysical`, quindi
a geometrie piccole una previsione nulla o negativa è possibile. In quel caso:

```
E_pred ≤ 0  →  err_rel non definito (None, non 0, non +inf aritmetico)
               flag pred_nonpositive = true
               il punto NON passa la validazione
```

Il punto è dichiarato **fallimento della previsione**, non escluso dal criterio e
non salvato da una divisione implicita, e **resta nel conteggio dei casi
valutati**: i punti di conferma sono due e l'anello 6 di P4.9 li richiede
entrambi, quindi un `pred_nonpositive` non può essere né diluito in una media né
tolto dal denominatore. Si riportano comunque `E_meas`,
`E_pred`, `intervallo_conf` e l'esito dell'appartenenza all'intervallo, che resta
informativo: un `E_meas` dentro l'intervallo con `E_pred ≤ 0` dice che il modello
non ha segno coerente in quella regione, e questo va scritto nel testo, non
nascosto in un campo.

**Nome dell'intervallo.** `intervallo_conf` **non è un intervallo al 95%**: i
quantili bootstrap sono al 95%, poi vengono allargati di due semi-range
`u_conf`, quindi la copertura nominale non è il 95% e non è quantificata. Si
chiama *intervallo operativo di conferma costruito dal protocollo*. È la stessa
regola che il protocollo applica altrove: la copertura è un campo, non un
aggettivo nel testo. La forma è congelata e non cambia; cambia solo come la si
nomina.

### P3.11 Metriche

- primarie: `J/token_32` e `J/token_128` (P3.4), con intervallo bootstrap;
- coefficienti `a`, `b`, `c`, `E0` con intervalli;
- costi marginali, ciascuno riferito alla propria coordinata: `∂E/∂N_out =
  b + c·N_in,ref` e `∂E/∂N_in = a + c·N_out,ref`;
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
- **conteggio delle sostituzioni** (aggiunta il 2026-10-24, redazionale: obbliga a
  registrare un numero, non cambia la regola; **unità dichiarata il 2026-10-25**).
  `design_deviation_count` è registrato **per blocco**, non per cella: conta le
  sostituzioni eseguite per arrivare alle `m = 3` richieste assegnabili **di quel
  blocco**, e per ogni sostituzione il prompt scartato e quello che lo sostituisce.
  L'unità non è una scelta amministrativa: `m = 3` è il numero di richieste di un
  blocco, quindi confrontare il conteggio di una cella (3 blocchi, fino a 9
  richieste) con `m` mescola due unità — il valore per cella, se serve, è la somma
  dei tre blocchi e va confrontato con `3m`. La ragione del conteggio non è
  amministrativa: sostituire le richieste che terminano presto **seleziona** prompt
  che generano a lungo, quindi un blocco con molte sostituzioni non contiene un
  campione casuale di prompt ma una popolazione selezionata dal criterio di
  sostituzione. Il conteggio non corregge l'effetto: lo rende visibile, e se il
  conteggio di un blocco arriva a un valore paragonabile a `m` — o quello di una
  cella a `3m` — quel blocco va discusso nel testo, non pubblicato come gli altri;
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
`design_deviation`, `design_deviation_count` (per blocco, P3.12). P6 esegue e
analizza. I campi dell'analisi di conferma (`err_rel`, `pred_nonpositive`,
`intervallo_conf`, F.10) sono per **punto**, non per riga: P5 decide se stanno
nel CSV delle righe o in un artefatto separato. Lo stesso vale per i campi del
lack-of-fit introdotti dall'emendamento di P3.9 (`F_lof`, `p_lof_perm`,
`p_lof_asint`, `lof_max_rel`, per campagna; `z_pe_b`, per blocco).

All'elenco si aggiungono `pre_range_w` e `dP` (P4.12, aggiunta del 2026-10-25):
sono gli ingressi di `pre_unstable`, `baseline_unstable` e `control_unstable`, e un
flag i cui ingressi non sono registrati non è verificabile da un terzo. Non sono
grandezze nuove, sono già definite in F.1 e F.3.

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

Niente per P3. Il pre-pilota verifica la fattibilità dei livelli **a entrambe le
estremità**: in alto (512 input, 256 output, prompt che sostengono la
generazione) e in basso (estensione aggiunta il 2026-10-24: allarga ciò che il
pre-pilota deve provare, non cambia il disegno). I livelli critici sono quelli
bassi, e il protocollo oggi li dà per raggiungibili senza averlo misurato:

- `(8, 4)` è un **vertice dell'inviluppo convesso** (P4.7). Se 8 token di input o
  4 di output non sono raggiungibili dentro la tolleranza ±5% di P3.12, il vertice
  non esiste nelle coordinate dichiarate e `hull_design` è costruito su un punto
  fittizio: `hull_margin_design_tok` di tutti gli altri punti sarebbe calcolato
  contro un bordo che non c'è;
- `(12, 32)` è il **punto operativo di conferma**, con `hull_margin_design_tok =
  1,33` (misurato il 2026-10-24, P4.7). Il margine è più piccolo della tolleranza
  del prompt, quindi la sua fascia di copertura dipende dal token reale e non dal
  target — ed è esattamente perché P4.7 classifica su **due** inviluppi, di progetto
  e di fit, prendendo il più conservativo;
- la tolleranza ±5% è incompatibile con lo scarto misurato fra target e actual:
  nel run 18:52 della v3 il target `N_in = 64` ha prodotto **126** token reali per
  inferenza, cioè circa il doppio (P2.2). La riga citata riporta i totali di run su
  3 inferenze, `tokens_in=378` e `tokens_out=352`, da cui 126 e 117 per inferenza;
  la stessa riga li corrobora con `prefill_s=0.3289` (0,87 ms/token × 378) e
  `decoding_s=33.6428` (95,58 ms/token × 352) —
  `lhm_validation_v3_20261023_185232.csv:2`, md `:13`, `:25`. **Caveat della
  sorgente**: quel run è etichettato `method=power-integration` con
  `window_source=counter-delta-fallback`, non `emi-counter`, quindi è evidenza
  sulla geometria del prompt e non sulla scala energetica (P2.2). Su
  `N_in = 8` uno scarto di quella taglia non è riducibile a una tolleranza del 5%:
  va misurato nel pre-pilota, non assunto.

Se un livello — alto **o basso** — non è raggiungibile, P3 si riapre e si
dichiara; non si cambia il livello in silenzio. Il fallimento della conferma è un
risultato di P6, non una decisione aperta.

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
predittivo `budget_pred = sqrt(u_base² + u_within² + u_edge² + u_bias²)`, la fascia
di copertura A/B/C decisa sul più conservativo fra l'inviluppo convesso del disegno
(sui target) e quello dei blocchi di fit (sui token reali), e — per la differenza
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
| bias in unità di metrica | `bias_jtok_pct_lo`, `bias_jtok_pct_hi` | i due estremi dell'intervallo `[|bias_w| · 6 , |bias_w| · 11]` % di `J/token`, traduzione del primo ordine con la scala ancorata a 1 W; **grandezza riportata, non soglia**; esportata come coppia perché un intervallo non sta in un campo solo (P4.5) |
| controlli utilizzabili | `controls_usable_n` | numero di blocchi di controllo che superano il filtro di stabilità; il gate è eseguibile se `≥ ⌈2/3 · n_coppie⌉` (P4.5) |
| termine di bordo | `u_edge,b` | `2 · P_peak,b · δt_edge,b`, incertezza di **disallineamento** ai due bordi della finestra, in joule; non maggiora l'interpolazione (P4.6) |
| durata media di finestra | `Δt̄_W,b` | `(1/m) · Σ_{i∈blocco b} Δt_W,i`; grandezza già usata da `u_base,b` (P3.8) |
| budget di fit | `budget_fit,b` | il `budget_b` di P3.8, rinominato: è ciò che pesa i blocchi nel fit |
| contributo del bias | `u_bias,b` | `|bias_w| · Δt̄_W,b`, zero se il gate di P4.5 passa; contributo di incertezza, **non** correzione sottratta dai dati |
| budget predittivo | `budget_pred,b` | `sqrt(budget_fit_b² + u_edge,b² + u_bias,b²)`: accompagna ogni numero pubblicato |
| inviluppo di progetto | `hull_design` | inviluppo convesso dei 10 punti di disegno sulle coordinate **target**; noto prima dei dati |
| inviluppo di fit | `hull_fit` | inviluppo convesso delle 33 coppie `(x1_b, x2_b)` dei blocchi di fit, sui token **reali**; noto dopo la campagna |
| fascia di copertura | A / B / C | dentro l'inviluppo / dentro il box ma fuori dall'inviluppo / fuori dal box; si assegna sui due inviluppi, ciascuno nella propria base, e si prende la più conservativa |
| fascia di progetto / di fit | `coverage_tier_design`, `coverage_tier_fit` | la fascia del punto **target** rispetto a `hull_design` e del punto **reale** `(x1_b, x2_b)` rispetto a `hull_fit`; `coverage_tier` è il più conservativo dei due |
| margine di inviluppo | `hull_margin_tok`, `hull_margin_design_tok` | distanza **perpendicolare euclidea** in coordinate grezze (token, token) dalla retta dello spigolo più vicino di `hull_fit` (punto reale) e di `hull_design` (punto target), negativa se fuori; la metrica è dichiarata in F.13 e non è la distanza dal vertice |
| stato della catena | `chain_status` | `validated` solo se tutti gli anelli di P4.9 passano; altrimenti l'etichetta dell'anello ceduto |
| lack-of-fit, riferimento | `p_lof_perm` | `p` della statistica F pesata ottenuto dalla distribuzione nulla per ricampionamento del puro errore; è il criterio dell'anello 5 (P3.9) |
| lack-of-fit, asintotico | `p_lof_asint` | `1 − F_{6,23}(F_lof)`; **indicativo**, si riporta accanto ma non decide |
| grandezza del lack-of-fit | `lof_max_rel` | scarto relativo massimo fra media di cella e superficie; descrittivo, senza soglia |
| leva del blocco | `h_b` | `w_b · x_bᵀ (XᵀWX)⁻¹ x_b`, elemento diagonale della matrice cappello agli stessi pesi del fit; `Σ_b h_b = 4` per l'identità della traccia (P4.8) |
| residuo corretto per la leva | `z_b^leva` | `r_b / (budget_fit_b · √(1 − h_b))`; alimenta la **sensibilità obbligatoria** del bootstrap, non il primario (P4.8) |
| copertura nominale | — | livello dichiarato dall'intervallo bootstrap (95%) senza che la copertura reale sia arbitrata; si scrive *copertura non arbitrata* finché P6.4 non la verifica per simulazione |

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
2. **Sei coppie** (emendamento del 2026-10-24, revisione esterna §4.7; la versione
   congelata ne prevedeva tre). Ogni coppia = 1 blocco di carico + 1 blocco di
   controllo. La ragione è aritmetica, non statistica: il quorum di P4.5 è una
   frazione dei controlli utilizzabili e la soglia aggregata è una **mediana** dei
   loro budget. Con tre coppie la mediana è su tre valori e un solo controllo
   scartato dal filtro lascia il gate nelle mani di due blocchi; con sei coppie la
   mediana è su sei e il quorum proporzionale ne richiede quattro. Costo
   dichiarato in P6.1: 1.080 s in più di sole finestre idle, cioè 18 minuti.
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
   blocco `baseline_pre_w`, `baseline_post_w` e quindi `dP`, `pre_range_w`,
   `budget_base_w` e `budget_base_j` (P1.5, P1.6, P1.7), e sono esattamente le
   quantità che il criterio di P4.5 usa — filtro di stabilità sui blocchi con
   `pre_range_w,c ≤ 1,0 W` e `|dP_c| ≤ 1,0 W`, confronto per blocco con
   `budget_base_j,c`, confronto aggregato con
   `mediana_c(budget_base_w,c)`. Un blocco di controllo senza struttura pre/post
   produrrebbe un `E_net` privo di `P_pre` e non confrontabile con nessun budget,
   cioè inutilizzabile. Il requisito vale per costruzione anche sul blocco di
   carico della coppia, che è un blocco di produzione a tutti gli effetti.

   **`r_A` e `r_B` su un blocco di controllo non esistono** (emendamento del
   2026-10-24; prima il requisito le elencava fra le quantità calcolabili ed era
   un difetto dichiarato). Le due grandezze hanno al denominatore
   `E_net_abs,b` = `|Σ_{i∈blocco} E_net_incremental,i|` (P1.6), somma sulle
   **richieste valide**: un blocco di controllo non invia richieste per
   costruzione (requisito 5), quindi la somma è vuota, il denominatore è zero e
   P1.6 dichiara il blocco invalido. Applicando il protocollo alla lettera, ogni
   controllo era invalido e il gate non era eseguibile. La ragione è strutturale:
   `r_A` è una grandezza **relativa**, confronta l'errore di drift con l'energia
   misurata, e senza energia misurata non ha denominatore — non esiste un modo di
   definirla su un blocco vuoto che non sia circolare. Serve una metrica di
   stabilità specifica, ed è quella assoluta qui sopra.
8. **Stessa procedura di produzione.** Per ciascun blocco di controllo si calcola
   `E_net,control = E_pkg_gross − P_pre · Δt_W`, con lo stesso codice di
   produzione e senza troncamento.

### P4.5 Criterio del test

Il criterio è calcolabile in virtù del requisito 7 di P4.4: `pre_range_w,c`,
`dP_c`, `budget_base_j,c` e `budget_base_w,c` esistono su un blocco di controllo
perché quel blocco esegue la stessa struttura di baseline 3 pre + 3 post dei
blocchi di carico. **`r_A` e `r_B` no**, e non sono usati qui (emendamento del
2026-10-24).

**Perché il filtro di stabilità dei controlli non è `r_A ≤ 10%`.** La versione
congelata filtrava `bias_w` "sui soli blocchi con `r_A ≤ 10%`". Non è eseguibile:
`r_A` ha al denominatore `E_net_abs,b`, somma sulle richieste valide (P1.6), e un
blocco di controllo non invia richieste (P4.4 requisito 5), quindi il denominatore
è zero e P1.6 dichiara il blocco invalido per costruzione. Alla lettera, ogni
controllo era invalido, il filtro non selezionava nulla e l'anello 4 di P4.9 non
era eseguibile. La ragione è strutturale: `r_A` è una grandezza **relativa**,
confronta l'errore di drift con l'energia misurata, e senza energia misurata non ha
denominatore.

Il filtro è sostituito dalle soglie **assolute già congelate** di P1.6, applicate al
blocco di controllo:

```
controllo utilizzabile se   pre_range_w,c ≤ 1,0 W   e   |dP_c| ≤ 1,0 W
```

Nessun numero nuovo e nessuna metrica nuova: sono la soglia di `pre_unstable` e la
stessa scala di 1,0 W la cui motivazione è misurata (1 W di errore sulla baseline
sposta J/token del 6–11%, `idle_floor_sensitivity_20261023_analisi.md` §2). Le due
vie alternative valutate e scartate sono in
`revisione_esterna_formule_20261024_valutazione.md` §4.2: una metrica nuova
`r_ctrl = |dP_c| · Δt_W,c / E_rif,c` con `E_rif,c` preso dal blocco di carico della
stessa coppia (non circolare, ma accoppia i due blocchi e introduce un simbolo e
una soglia nuovi), e l'eliminazione del filtro (perde la protezione contro un
controllo con baseline impazzita).

Un controllo che non supera il filtro **non entra** in `bias_w` ed è registrato con
il flag `control_unstable`; se i controlli utilizzabili sono meno di quattro, il gate
non è eseguibile e `chain_status` scende a `bias_declared` con la ragione scritta —
non si pubblica un bias medio su un pugno di blocchi dichiarandolo test. Il quorum
**non è una soglia nuova**: è la stessa frazione congelata (due su tre) riportata
alle sei coppie dell'emendamento di P4.4 requisito 2. Con tre coppie il quorum era
"almeno 2", con sei è "almeno 4"; se il numero di coppie cambiasse ancora, il quorum
è `⌈2/3 · n_coppie⌉` e non un numero assoluto. Il numero di controlli utilizzabili
si registra in `controls_usable_n`.

```
per blocco:  passa se  |E_net,control,c| ≤ budget_base_j,c              (P1.7)
aggregato:   bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c
             sui soli controlli utilizzabili (filtro qui sopra)          (P4.4 req. 7)
             passa se  |bias_w| ≤ mediana_c(budget_base_w,c)
```

**Il filtro assoluto limita anche la circolarità del criterio per blocco.** Il
criterio per blocco confronta `|E_net,control,c|` con `budget_base_j,c`, e i due
termini non sono indipendenti: `budget_base_j,c = Δt_W,c · budget_base_w,c` contiene
`half_drift_c = |dP_c|/2` misurato **su quello stesso blocco** (P1.7), mentre
`E_net,control,c ≈ (P̄_c − P_pre,c) · Δt_W,c` è prodotto in gran parte da quello
stesso drift. Un blocco con deriva grande si costruisce quindi sia l'errore sia la
soglia che lo assolve: il criterio è debole proprio dove servirebbe forte
(diagnosi in `revisione_esterna_formule_20261024_valutazione.md` §3.4). Il filtro
`|dP_c| ≤ 1,0 W` lo taglia alla radice, perché ammette al criterio solo blocchi la
cui deriva è piccola in assoluto e non solo piccola rispetto al proprio budget: con
`|dP_c| ≤ 1,0 W` il termine di drift dentro `budget_base_w,c` è al più 0,5 W, e la
parte restante della soglia (`half_range_pre_w,c`) è misurata sulle finestre pre,
non sulla deriva. La circolarità non è eliminata — il budget resta in parte
autocostruito — ma è confinata sotto una soglia assoluta congelata prima dei dati.

- **Se passa**: la sottrazione di P1 è validata su questa macchina nel senso
  dichiarato in P4.9–P4.10 — anello 4 della catena, non scala assoluta — e
  `u_bias,b = 0` per ogni blocco.
- **Se non passa**: `u_bias,b = |bias_w| · Δt̄_W,b` entra in quadratura in
  `budget_pred_b` (P4.6, F.11), il bias è
  dichiarato nella tesi con il suo segno, e **P1 non si cambia**: sostituire
  l'estimatore sulla base di un solo test sarebbe cambiare metodo senza
  evidenza. La campagna si ripete una sola volta, per distinguere un transitorio
  da un bias sistematico; se anche la ripetizione fallisce, il bias è sistematico
  e si riporta come tale.
- Le soglie sono congelate prima dei dati. Non si sceglie la soglia dopo aver
  visto il bias.

**Il bias si riporta anche in unità della metrica pubblicata** (emendamento del
2026-10-24, revisione esterna §4.7). `bias_w` è un watt: per chi legge la tesi è un
numero senza scala, perché la metrica pubblicata è `J/token`. La traduzione usa la
sensibilità già ancorata — 1 W di errore sulla baseline sposta `J/token` del 6–11%
alla geometria operativa (`idle_floor_sensitivity_20261023_analisi.md` §2) — ed è
una **grandezza riportata, non una soglia**:

```
bias_jtok_pct_lo = |bias_w| · 6    % di J/token
bias_jtok_pct_hi = |bias_w| · 11   % di J/token
```

Lineare in `|bias_w|` perché ancorata a 1 W: la sensibilità è misurata a quella
scala e non è verificata altrove, quindi la traduzione è del primo ordine e va
scritta come tale. Non sostituisce il criterio in watt, che resta quello congelato.

**Nomi dei campi (armonizzati il 2026-10-24).** Un intervallo non sta in un campo
solo, quindi la grandezza è esportata come **coppia**: `bias_jtok_pct_lo` e
`bias_jtok_pct_hi` (P4.12, F.12). La forma senza suffisso, `bias_jtok_pct`, indica
l'intervallo nel testo e non è un nome di campo; chi scrive il CSV o il codice usa
la coppia. Prima di questa armonizzazione P4.5 definiva un nome e P4.12 ne
elencava due per la stessa grandezza.

Tre proposte della revisione esterna su questo punto, valutate e **non** adottate:

1. *Intervallo t sul bias medio.* Richiederebbe una varianza stimata su al più sei
   blocchi, e P1.7 vieta il linguaggio della deviazione standard quando non c'è una
   stima di varianza. La soglia aggregata è già una mediana di budget conservativi:
   affiancarle un intervallo t introdurrebbe un secondo criterio con un'altra
   epistemologia. Scartata per coerenza lessicale, non per costo;
2. *Test di equivalenza con margine in `J/token` (±3–5%).* Il margine proposto,
   convertito con la scala ancorata qui sopra, è `3/11 … 5/6` = **0,27–0,83 W**,
   cioè più stretto della scala di 1,0 W su cui sono congelate le soglie di P1.6 e
   il filtro dei controlli. Adottarlo significherebbe o inasprire le soglie dopo
   averle congelate, o avere due criteri che possono contraddirsi. Si dichiara
   invece il limite, che è la parte utile della proposta: **il gate che passa non
   dimostra l'equivalenza a ±3–5% di `J/token`**, dimostra che il bias sta dentro
   il budget di baseline osservato. Scartata come soglia, recepita come limite;
3. *Otto coppie invece di sei.* Oltre sei, il costo marginale di finestre idle e di
   richieste cresce linearmente mentre il quorum proporzionale non cambia
   natura; il punto debole del gate non è la numerosità ma la dipendenza della
   soglia dall'instabilità osservata (§3.4 della valutazione), che più coppie non
   curano. Sei è il raddoppio del congelato e il primo valore dell'intervallo
   proposto dal revisore: dà una mediana su sei valori e un quorum di quattro, a
   18 minuti di costo. P6.4 misura se bastano.

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
principale. È un confronto descrittivo, non un gate. Con l'emendamento a sei coppie
questo sottoprodotto cresce: 6 blocchi × 3 richieste = 18 misure alla geometria
operativa, contro le 9 di prima, cioè la stessa numerosità di due punti di disegno
della griglia. Resta descrittivo — non entra in nessun anello di P4.9 — ma è il
materiale con cui P6.4 può tarare la variabilità fra blocchi a parità di geometria,
che oggi non è misurata.

### P4.6 Budget di incertezza completo

Due budget, nomi distinti, nessun cambiamento ai pesi congelati.

```
budget_fit_b²  = u_base,b² + u_within,b²                  # ≡ budget_b di P3.8, stesso oggetto
budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²    # per ogni numero pubblicato

u_base,b   = Δt̄_W,b · budget_base_w,b                        # P1.7, P3.8
u_within,b = semi-range(E_act,i nel blocco)                  # P3.8, non diviso per √m
u_edge,b   = 2 · P_peak,b · δt_edge,b ,   δt_edge,b = Δt_tick,b / 2
u_bias,b   = |bias_w| · Δt̄_W,b ,          u_bias,b = 0 se il gate di P4.5 passa

Δt̄_W,b     = (1/m) · Σ_{i∈blocco b} Δt_W,i                   # durata media delle finestre del blocco
```

`budget_fit_b` **è** il `budget_b` di P3.8, rinominato solo per distinguerlo dal
predittivo: non è un emendamento. I pesi del fit restano `w_b = 1/budget_fit_b²`,
congelati: `u_edge,b` e `u_bias,b` entrano **solo** nel predittivo e non toccano la
stima. `Δt̄_W,b` è la stessa grandezza già usata da `u_base,b` in P3.8 e qui è
scritta per esteso perché `u_bias,b` ne dipende in modo visibile.

**Scala dei due budget, dichiarata esplicitamente (aggiunta del 2026-10-25).**
`budget_fit_b` e `budget_pred_b` sono in joule **sulla scala di `Ē_b`**, cioè della
media per richiesta del blocco (F.7: `Ē_b = (1/m) · Σ_i E_act,i`; il fit di F.9
stima su `Ē_b`), non sulla scala del totale di blocco. È per questo che la durata
che compare in `u_base,b` e in `u_bias,b` è `Δt̄_W,b`, durata **media** delle
finestre, e non `Σ_i Δt_W,i`. La lettura alternativa, cioè un `Δt_W,b` inteso come
durata dell'intero blocco, è valutata e **non** adottata: con `m = 3` renderebbe
quei due termini tre volte più grandi e `budget_pred_b` fino a tre volte più largo
dove essi dominano, ed è esattamente la "durata aggregata" che il difetto chiuso qui
sotto dichiarava non calcolabile. La regola pratica per P5: il campo durata che
alimenta `u_base,b` e `u_bias,b` è la media per blocco di `duration_s`, la stessa
grandezza di `Δt̄_W,b`, e non la somma delle finestre del blocco.

**Difetto chiuso il 2026-10-24 (emendamento sostanziale di P4.6).** Nella versione
congelata `u_bias` **non compariva** nella formula di `budget_pred_b²`, mentre il
testo ne affermava l'ingresso in cinque punti: P4.4 requisito 1, P4.5 esito
negativo, anello 4 di P4.9, P4.14 e F.12. Regola testuale e formula si
contraddicevano, e la formula è ciò che un implementatore traduce in codice.
Seconda parte dello stesso difetto: `u_bias = |bias_w| · Δt_W` non diceva **quale**
`Δt_W`, e poiché `bias_w` è un watt medio di campagna
(`Σ_c E_net,control,c / Σ_c Δt_W,c`), moltiplicarlo per un `Δt_W` singolo o per una
durata aggregata dà joule diversi di un ordine di grandezza: il campo `u_bias_j`,
obbligatorio in P4.12, non era calcolabile.

La correzione adotta la lettura a **contributo di incertezza**, che è ciò che il
testo descriveva già a parole (valutazione esterna §4.3):

- `u_bias,b = |bias_w| · Δt̄_W,b` entra in quadratura in `budget_pred_b`, e vale
  **zero** se il gate di P4.5 passa. `bias_w` è un watt medio di campagna, `Δt̄_W,b`
  è la durata media delle finestre del blocco: il prodotto è l'energia che il bias
  sposta su quel blocco, nella stessa unità degli altri tre termini;
- **non** è una correzione sistematica. L'alternativa — sottrarre `bias_w · Δt_W`
  da `E_net` e propagare l'incertezza della correzione — cambia i dati, non solo
  gli intervalli, e contraddice P4.5: "il bias è dichiarato nella tesi con il suo
  segno, e **P1 non si cambia**". Il segno di `bias_w` si riporta nel verbale e
  nella tesi, e non si applica ai dati;
- il valore assoluto sta dentro `u_bias,b` perché un contributo di incertezza è non
  negativo per costruzione; il segno resta solo nella quantità dichiarata.

`u_bias,b` è **comune a tutti i blocchi della campagna** attraverso `bias_w`, e
varia da blocco a blocco solo per `Δt̄_W,b`. È l'unico termine di `budget_pred` con
questa struttura: gli altri tre sono misurati sul blocco. Va dichiarato, perché
sposta tutti i numeri pubblicati nella stessa direzione e non si media via.

La forma di combinazione — quadratura — è la stessa già adottata per gli altri
termini e resta **provvisoria** insieme a quella di `budget_base_w` (P1.7, P1.13):
se quella passasse alla somma aritmetica, anche questo termine seguirebbe la stessa
sorte. Le due decisioni vanno chiuse insieme, prima della campagna principale, sui
dati del pilota P2.9.

Il termine di bordo. `δt_edge,b` è metà dell'intervallo **misurato** del buffer EMI
nel blocco, non dell'intervallo dichiarato da `POWER_SAMPLE_INTERVAL_S = 0.05`
(`energy_session.py:80`): sul percorso di produzione `Δt_tick` è 0,28–0,34 s. Ogni
bordo della finestra cade quasi sempre fra due campioni e il contatore cumulativo è
letto per interpolazione lineare (`_emi_cum_at`, `energy_session.py:1103-1124`);
l'errore di un bordo è al più `P_peak · δt_edge` e i bordi sono due — ma **per
disallineamento, non per interpolazione**: vedi la rettifica qui sotto. `P_peak,b` è
la potenza **totale** di picco del blocco, non quella netta: ciò che viene letto
è un contatore che accumula potenza totale, quindi il limite deve usare la potenza
totale — usare quella netta sottostimerebbe il termine. È un limite superiore
conservativo, non una propagazione di varianza: la stessa regola di P1.7.

**Quale errore maggiora, davvero** (rettifica del 2026-10-24: corregge la
giustificazione, **non** la formula né il valore congelato). La versione precedente
di questo paragrafo attribuiva il limite `P_peak · δt_edge` all'interpolazione
lineare. Non è così, e la distinzione va scritta perché cambia cosa il termine
copre.

1. **Errore di interpolazione.** L'interpolazione lineare di un contatore
   cumulativo ha errore **identicamente nullo a potenza costante**, per ogni
   livello di `P_peak` e per ogni griglia. Numeri rigenerati dall'harness
   tracciato `u_edge_interpolazione_probe.py` (5/5 verifiche, 2026-10-25) a
   `P = 35 W`, `Δt_tick = 0,30 s`, `n = 2 000 001`: residuo **relativo** alla
   grandezza del contatore 7,0e-12, invariante in `P` (70 W e 140 W danno lo
   stesso relativo); l'assoluto è proporzionale a `P` e cresce con `n`, quindi il
   `3,0e-11 J` scritto qui in precedenza è **ritirato**: era l'assoluto di una
   griglia non dichiarata e non è riproducibile. Dipende dalla **variazione** di
   potenza dentro il tick, non dal suo livello. Per un gradino `ΔP_tick` posto a
   frazione `f` del tick:

   ```
   max_t |E(t) − interpolante(t)| = ΔP_tick · f · (1 − f) · Δt_tick  ≤  ΔP_tick · Δt_tick / 4
   ```

   dallo stesso harness: `ΔP_tick = 25 W`, `Δt_tick = 0,30 s` → 1,4062 J a
   `f = 0,25`, 1,8750 J a `f = 0,5`, 1,4063 J a `f = 0,75`. Per una rampa lineare
   il limite si dimezza (0,9375 J); scarto dall'analitico al più il passo di
   griglia (1,7e-6 J per il gradino, 3,0e-15 J per la rampa). Il livello di
   potenza non compare nel termine esatto.
2. **Errore di disallineamento.** Se l'istante di bordo usato da Python e il
   timestamp del campione EMI non coincidono, un'energia `P · δt` è attribuita al
   lato sbagliato del bordo. **Questo** è maggiorato da `P_peak · δt_edge`, ed è
   esattamente la forma congelata: `2 × 35 W × 0,15 s = 10,5 J` per due bordi. La
   formula resta quella, il valore resta quello; cambia solo il nome dell'errore
   che copre.
3. **Errore di copertura (non nominato prima).** `_emi_cum_at` non estrapola:
   fuori copertura ma entro 1 s restituisce il valore estremo
   (`energy_session.py:1111-1116`), cioè attribuisce energia **zero** a quel
   tratto. È un terzo modo di sbagliare il bordo, fino a `P_peak · 1 s`, più
   grande degli altri due. Non è coperto dal valore congelato.

I tre termini sono concordi in segno e indipendenti in origine, quindi il limite
della somma è superiore a 10,5 J; il valore congelato **non** li maggiora tutti e
tre.

**Decisione presa il 2026-10-24: via (b), come requisito vincolante di P5.** Le
due vie erano (a) aggiungere a `budget_pred` un termine di interpolazione stimato
sul `ΔP_tick` **misurato** nel
bloco — oggi `ΔP_tick` non è misurato da nessuna parte del codice, quindi la (a)
introduce un termine **non calcolabile** — oppure (b) eliminare alla radice i termini 2 e 3 leggendo il
contatore in modo sincrono ai bordi di finestra, con il suo timestamp, che è
materiale di P5.

**Si adotta la (b) e si scarta la (a)**, per tre ragioni. Prima: la (a) chiede un
termine non calcolabile, cioè un budget che per essere scritto ha bisogno di una
catena di misura nuova. Seconda: quel termine sarebbe a sua volta una stima, un
numero con la propria incertezza dentro un budget che dovrebbe essere un limite
superiore; la (b) non produce stime. Terza: la (b) elimina i tre errori insieme,
non ne maggiora uno. Con due letture sincrone il bordo della finestra **è** un
campione del contatore: non c'è interpolazione (termine 1), non c'è sfasamento fra
l'istante chiesto e l'istante letto (termine 2), e non si esercita il clamp a 1 s
di `_emi_cum_at` (termine 3).

La decisione non tocca la formula congelata di `u_edge,b`, che resta
`2 · P_peak,b · δt_edge,b`: cambia **cosa è** `Δt_tick,b`. Oggi è la cadenza del
nostro sampler, 0,28–0,34 s misurati; con la lettura sincrona diventa l'intervallo
fra gli aggiornamenti del registro, che il probe a 50 ms mostra più breve
(`emi_50ms_probe_20261023_*`). Il fattore di riduzione **si misura, non si
assume**: finché non è misurato sulla macchina nella configurazione di campagna,
il valore pubblicato di `u_edge,b` resta quello della formula congelata con il
`Δt_tick,b` effettivamente osservato nel blocco, che la v4 già registra come
`sampling_interval_observed_s`.

Requisito che ne segue per P5, riportato in P6.5: la finestra di misura è
delimitata dalle **due letture sincrone**, e `Δt_W` è la differenza dei loro
timestamp, non l'intervallo nominale chiesto dal runner. Energia e durata devono
riferirsi allo stesso intervallo, altrimenti `E_base = P_pre · Δt_W` sottrae
l'energia di un tratto diverso da quello misurato. Oggi non è così: `duration_s` è
`t_end − t_start` sull'orologio di Python, meno le sottofinestre escluse
(`local_energy.py:156`, `:171`), mentre l'energia è la differenza dei valori di
contatore **interpolati** a quegli stessi istanti (`energy_session.py:1245-1250`,
`_emi_cum_at` sui bordi della finestra).
Il runner apre la prima lettura prima di inviare la richiesta e chiude la seconda
dopo la terminazione.

Fino all'implementazione in P5, e quindi per ogni numero prodotto con il codice
attuale, vale la regola provvisoria già scritta: `budget_pred` esce nella forma
congelata, con la dichiarazione che il termine di bordo copre il disallineamento e
**non** l'interpolazione né la copertura.

Ordine di grandezza, dichiarato come esempio e non come misura: con
`Δt_tick = 0,30 s` e `P_peak = 35 W` il termine vale `10,5 J`, confrontabile con
l'energia netta di una richiesta breve alla geometria operativa. Quindi `u_edge` si
calcola per blocco e si riporta; non si assume trascurabile. La sua grandezza è
anche l'argomento quantitativo dello sviluppo 3 del cap. 6: il probe a 50 ms mostra
che il registro si aggiorna a quella cadenza, quindi `Δt_tick` è riducibile di un
fattore ~6 per via software, e `u_edge` con esso. È la ragione per cui la via (b) è
stata adottata, ma il fattore ~6 resta un valore di probe: non è misurato nella
configurazione di campagna e non si pubblica come riduzione acquisita.

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
fascia si decide quindi sull'**inviluppo convesso** dei punti, calcolato dai punti e
non scritto a mano — nell'emendamento del 2026-10-24, su **due** inviluppi: quello
dei 10 punti di disegno e quello dei 33 blocchi di fit.

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

Le tre definizioni valgono identiche per i due inviluppi introdotti più sotto
(`hull_design` e `hull_fit`): cambia la base, non il criterio.

Due conseguenze da dichiarare, non da nascondere.

1. Il punto di conferma `(12,32)` — la geometria operativa reale, e quindi il
   `J/token` di produzione — cade **in fascia A di progetto**, con un margine di
   `1,33` token dal lato `(8,4)–(32,256)`. L'appartenenza è geometricamente
   sottile. Per questo `hull_margin_tok` è una colonna obbligatoria, e ogni punto
   pubblicato con margine inferiore a 2 token esce anche con il flag
   `thin_support`. Il flag non cambia l'intervallo: dichiara che la
   classificazione A si regge su un supporto di progetto di misura, e che a
   sostenerla è il punto di conferma empirico di P3.10, non la geometria.
2. `(256,192)` sta dentro con margine 64 token: la conferma alta è in fascia A di
   progetto piena.

**Difetto chiuso il 2026-10-24 (emendamento sostanziale di P4.7).** Nella versione
congelata le fasce erano decise sull'inviluppo dei **10 punti di disegno**, cioè
sulle coordinate **target**, e i margini pubblicati qui sopra (1,33 / 64,0 / 21,2 /
107,7) erano calcolati su quelle. Il modello però è stimato sui token **reali**
(P2.3, F.6: `N_in_actual,i = prompt_eval_count_i`), e il protocollo stesso scrive
dei dati v3: "Il target è una richiesta al costruttore del prompt, **non una
coordinata**" (P2.2), con l'evidenza che a `N_in = 64` dichiarato corrispondevano
**126** token reali per inferenza (`tokens_in=378` su 3 inferenze,
`lhm_validation_v3_20261023_185232.csv:2`). Classificare la copertura in una base e
stimare il modello in
un'altra rende `coverage_tier` e `hull_margin_tok` non coerenti con `x1_b`, `x2_b`
di F.7: se `N_in_actual` è sistematicamente circa il doppio del target ai livelli
bassi, il punto operativo `(12,32)` non sta dove la classificazione dice che sta, e
il suo margine di 1,33 token — già sottile — non è il margine reale.

**Regola corretta: due inviluppi, nella stessa base del punto classificato.** La
raccomandazione della valutazione esterna (§4.4) teneva l'inviluppo sui target e
spostava solo il punto sui reali. Non basta, e qui si va un passo oltre: se i reali
sono sistematicamente spostati rispetto ai target, un punto può cadere dentro
l'inviluppo di progetto ed essere comunque **fuori** dall'inviluppo dei dati su cui
il modello è stato stimato — cioè un'estrapolazione pubblicata in fascia A, che è
esattamente l'errore per cui questa sezione esiste. Quindi:

```
metrica dei due margini, obbligatoria e unica (dichiarata il 2026-10-25):
    d(P, inviluppo) = minimo, sulle rette degli spigoli dell'inviluppo, della
                      distanza PERPENDICOLARE euclidea di P dalla retta,
                      in coordinate grezze (token, token); negativa se P è fuori
    non è la distanza dal vertice più vicino: per (12,32) quella dà 28,28
    invece di 1,33, fattore 21,3, e rovescia il flag thin_support

lato di progetto (pre-registrato, calcolabile prima dei dati):
    hull_design  = inviluppo convesso dei 10 punti di disegno sulle coordinate TARGET
                   vertici (8,4) (512,32) (512,256) (32,256)
    box_design   = 8 ≤ N_in ≤ 512 ,  4 ≤ N_out ≤ 256
    punto        = (N_in,target , N_out,target) del punto da classificare
    coverage_tier_design = A dentro hull_design / B dentro box_design / C fuori
    hull_margin_design_tok = d(punto target, hull_design) con la metrica qui sopra

lato di fit (calcolato sui dati, noto solo dopo la campagna):
    hull_fit     = inviluppo convesso delle 33 coppie (x1_b, x2_b) dei blocchi di fit
    box_fit      = [min_b x1_b , max_b x1_b] × [min_b x2_b , max_b x2_b]
    punto        = (x1_b , x2_b) del blocco da classificare, medie dei token REALI (F.7)
    coverage_tier_fit = A dentro hull_fit / B dentro box_fit / C fuori
    hull_margin_tok   = d(punto reale, hull_fit) con la stessa metrica

esito pubblicato:
    coverage_tier = il più conservativo dei due        (A < B < C)
    thin_support  = true se uno dei due margini è < 2 token
```

Ciascun lato confronta coordinate della **stessa base** con un inviluppo costruito
in quella base: target contro `hull_design`, reali contro `hull_fit`. Confrontare un
punto reale con l'inviluppo dei target ripeterebbe in altra forma lo stesso difetto.

Conseguenze, dichiarate prima e non scoperte dopo:

1. i quattro margini pubblicati in questo punto (1,33 / 64,0 / 21,2 / 107,7) sono
   **margini di progetto**, etichettati come tali: valgono per `hull_design` e per
   le coordinate target, e restano l'oggetto pre-registrato con cui si confronta la
   campagna. I margini reali si calcolano a dati raccolti e possono essere più
   piccoli;
2. **la fascia di un punto può cambiare in seguito alla misura.** Un punto
   classificato A in progetto può uscire B o C sui reali, e in quel caso i suoi
   claim si declassano. Non si sposta l'inviluppo per farlo rientrare: la regola
   "le soglie sono congelate prima dei dati" vale anche per la geometria del
   supporto;
3. `hull_fit` è calcolato dai dati, non scritto a mano, come già valeva per
   `hull_design`. Se il pre-pilota di P3.15 cambia i punti di disegno, cambiano
   entrambi gli inviluppi (P4.14);
4. **limite ulteriore, da scrivere insieme al risultato.** La classificazione usa la
   proiezione su `(x1_b, x2_b)`, mentre il fit vive in
   `(x1_b, x2_b, x12_b)`: essere dentro l'inviluppo proiettato **non** garantisce
   di essere dentro l'inviluppo del disegno a quattro dimensioni, perché `x12_b` è
   la media dei prodotti e non il prodotto delle medie (F.7). La fascia A resta
   quindi una condizione **necessaria non sufficiente** per l'interpolazione: la
   garanzia empirica è il punto di conferma di P3.10, non la geometria.

**La metrica del margine è dichiarata e verificata (aggiunta del 2026-10-25).**
"Distanza dal bordo" non specificava quale distanza, e la scelta non è cosmetica
perché `thin_support` scatta sotto i 2 token: con la distanza perpendicolare alla
retta dello spigolo il punto operativo `(12,32)` dà 1,33 ed è marcato
`thin_support`; con la distanza euclidea dal vertice più vicino dà 28,28 e non lo
è. Fattore 21,3 sullo stesso punto e sullo stesso inviluppo, cioè due esiti opposti
di un flag obbligatorio. La metrica adottata è la perpendicolare, ed è quella con
cui i quattro margini pubblicati sono stati **ricalcolati per esecuzione** il
2026-10-25: 1,33 / 64,0 / 21,24 / 107,7, cioè i valori già scritti (il terzo è
21,2 arrotondato). Vertici confermati `(8,4)`, `(512,32)`, `(512,256)`, `(32,256)`.

**Coordinate normalizzate: non adottate, e non per dimenticanza.** `N_in` e `N_out`
sono entrambi in token ma hanno intervalli diversi (8–512 e 4–256), quindi una
distanza euclidea grezza pesa i due assi in modo diseguale; normalizzare renderebbe
il margine adimensionale e più confrontabile fra gli assi. È però una decisione
metodologica **distinta**, non una correzione da introdurre di passata: cambia il
valore di tutti i margini pubblicati e il significato della soglia di 2 token di
`thin_support`, che sta nel testo congelato. Si registra come sviluppo possibile,
da prendere prima dei dati se la si vuole prendere. Finché non è presa, la metrica
è quella grezza dichiarata qui sopra e i margini sono in token. Chi legge un
margine pubblicato deve leggere anche questa riga.

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
  derivate `∂E/∂N_out = b + c·N_in,ref`, `∂E/∂N_in = a + c·N_out,ref`,
  `J/token_32`, `J/token_128`,
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

**Emendamento del 2026-10-24 (revisione esterna §4.6): copertura nominale e
correzione di leva.**

Il bootstrap produce un intervallo al 95% **nominale**. Nominale non è sinonimo di
garantito: la copertura reale è una proprietà congiunta della procedura e dei
dati, e qui poggia su tre condizioni oggi non verificate. Che i `budget_fit_b`
siano proporzionali alle varianze vere dei residui — P3.8 dichiara il contrario,
sono limiti superiori conservativi. Che il modello sia adeguato — P3.9 può fallire
e l'intervallo resta stretto. Che il ricampionamento stratificato per punto
approssimi bene la legge dei residui con 33 blocchi su 10 strati, di cui otto da
tre. La copertura **va verificata per simulazione** in P6.4 prima di scrivere
"95%" nella tesi; finché la simulazione non è eseguita, l'intervallo si riporta
come *bootstrap, livello nominale 95%, copertura non arbitrata*, con la stessa
disciplina lessicale della scala assoluta (P4.11). Non è una formula: è la
condizione perché la formula si possa citare.

Sensibilità **obbligatoria**, non sostituzione del primario. Il ricampionamento
degli `z_b` li tratta come omoschedastici; non lo sono esattamente, perché un
blocco con leva alta ha un residuo contratto dal fit e il suo `z_b` sottostima lo
scarto che un blocco nuovo alla stessa geometria avrebbe. La correzione è
moltiplicare per `1/√(1 − h_b)`, con `h_b` elemento diagonale della matrice
cappello agli stessi pesi del fit:

```
h_b      = w_b · x_bᵀ (Xᵀ W X)⁻¹ x_b ,   x_b = (1, x1_b, x2_b, x12_b)
z_b^leva = r_b / (budget_fit_b · √(1 − h_b))
Σ_b h_b  = 4 = numero di parametri, qualunque siano i pesi (identità della traccia)
```

Sul disegno nominale di P3.5, calcolata a pesi uguali — cioè nel caso
omoschedastico, il più informativo perché è l'unico in cui la leva dipende solo
dalla geometria — e verificata per esecuzione il 2026-10-24:

| punto di disegno | blocchi | `h_b` | `1/√(1 − h_b)` |
|---|---|---|---|
| (512, 256) | 3 | 0,2852 | 1,1828 |
| (512, 32) | 3 | 0,2505 | 1,1551 |
| (32, 256) | 3 | 0,1669 | 1,0956 |
| (8, 4) | 3 | 0,1370 | 1,0765 |
| (128, 256) | 3 | 0,1094 | 1,0596 |
| (512, 128) | 3 | 0,1086 | 1,0592 |
| (32, 32) | 3 | 0,0906 | 1,0487 |
| (128, 32) | 3 | 0,0643 | 1,0338 |
| (32, 128) | 3 | 0,0519 | 1,0270 |
| (128, 128) | 6 | 0,0345 | 1,0177 |
| media | — | 0,121212 = 4/33 | — |

Il fattore correttivo più grande è 1,18. Per questo la correzione è una
sensibilità e non il primario: la leva non è il termine dominante di un budget
costruito per essere conservativo. Si eseguono entrambi i bootstrap, **allo
stesso seed**, e si riportano entrambe le ampiezze; se i quantili delle quantità
derivate differiscono di più del 10%, la differenza si dichiara e si adotta
l'intervallo più largo. Se la correzione cambiasse materialmente il risultato, il
segnale non è statistico ma di disegno: la leva alta sta sui quattro vertici
dell'inviluppo (P4.7), cioè la superficie è sostenuta dai blocchi estremi e non
dal centro, e il centro ha sei blocchi proprio per evitarlo.

Due limiti dichiarati. La leva della tabella è sulle **coordinate nominali**; dopo
la campagna va ricalcolata sulle medie effettive `(x1_b, x2_b, x12_b)` dei token
misurati, perché i target non sono coordinate (P2.2) e quindi nemmeno la leva sui
target è la leva vera. E la soglia operativa è una sola: se la leva massima
effettiva supera 0,40, cioè `1/√(1 − h) > 1,29`, la sensibilità diventa primaria
e lo si dichiara — a quel punto la correzione non è più trascurabile rispetto ai
termini conservativi del budget. Nessun'altra soglia si aggiunge.

Campi che la rendono verificabile (P4.12): `h_leverage` per blocco;
`boot_leva_rel_diff`, massima differenza relativa fra i quantili delle quantità
derivate del primario e della variante; `boot_leva_adopted`, vero se l'intervallo
pubblicato è quello della variante. Con questi tre campi un lettore può
ricostruire quale dei due intervalli è uscito e perché, senza ripetere il
bootstrap.

### P4.9 Catena di validazione: criterio monolitico

"Validata" è una parola sola e si assegna solo se **tutti** gli anelli passano. Non
esiste validazione parziale: un anello rotto rompe la parola, non il dato.

| # | anello | criterio | etichetta se fallisce |
|---|---|---|---|
| 1 | token e terminazione | pilota P2.9 A/B/C superato | campagna non eseguibile: si corregge il pilota, non i dati |
| 2 | contatore | nessun blocco con delta negativo, reset o lettura non finita (P1.6) | `counter_invalid`: il blocco si ripete una volta, poi si scarta e si dichiara |
| 3 | baseline | `r_A ≤ 10%` in almeno 2 blocchi su 3 per punto (P1.6) | `baseline_unstable`; con due punti su tre, campagna invalida |
| 4 | sottrazione | test load-versus-control dentro il budget (P4.5) | `bias_declared`: `u_bias` entra in `budget_pred`, P1 non cambia |
| 5 | adeguatezza del modello | lack-of-fit **non** significativo, `p_lof_perm ≥ 0,05` (P3.9) | `model_inadequate`: la superficie si riporta come descrizione, non come legge |
| 6 | conferma | entrambi i punti di P3.10 con `err_rel ≤ 10%` e dentro `intervallo_conf`; un `E_pred ≤ 0` è fallimento (`pred_nonpositive`) | `validation_failed`: nessun rifit sui punti di conferma |

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
  `bias_w`, `controls_usable_n`, `bias_jtok_pct_lo`, `bias_jtok_pct_hi`,
  `z_resid`, `h_leverage`, `boot_leva_rel_diff`, `boot_leva_adopted`,
  `hull_margin_tok`, `hull_margin_design_tok`,
  `coverage_tier` ∈ {`A`, `B`, `C`}, `coverage_tier_design`, `coverage_tier_fit`,
  `sparse_support`, `thin_support`, `out_of_coverage`, `bootstrap_seed`,
  `validation_bias_pass`, `control_unstable` (sui blocchi di controllo, P4.5),
  `pre_range_w`, `dP` (per blocco: P1.6, F.1, F.3),
  `chain_status`. `Δt̄_W,b` (P4.6, F.11) **non** è una colonna nuova: è la media
  per blocco della `duration_s` già prevista, e P5 lo dichiari come quantità
  derivata;
- `pre_range_w` e `dP` entrano nell'elenco il 2026-10-25 e non sono grandezze
  nuove: sono già definite in P1 (F.1, F.3) e già usate da tre flag. Senza di esse
  `control_unstable` registra un esito i cui due ingressi (`pre_range_w,c ≤ 1,0 W`
  e `|dP_c| ≤ 1,0 W`, P4.5) non sono leggibili, quindi un terzo non può verificare
  né il filtro né che la soglia fosse fissata prima dei dati. Lo stesso vale per
  `pre_unstable`, il cui ingresso è `pre_range_w`; per `baseline_unstable` l'ingresso
  `r_A` era già in elenco. Regola generale, che P5 applichi a ogni campo: **un flag
  obbligatorio porta con sé i valori da cui è stato calcolato**, altrimenti è
  un'affermazione e non un dato;
- P6 fissa l'ordine di esecuzione — la campagna di P4.4 sta prima della principale e
  ne è il gate — e gli script di analisi;
- il wattometro: la scala assoluta resta non arbitrata (cap. 6, sviluppo 1);
- Linux/RAPL: il disegno di P4.4 è indipendente dal backend e si applica a RAPL con
  gli stessi criteri, ma in v4 non è eseguito. Il backend Linux è implementato, non
  validato su questa campagna;
- la deviazione standard campionaria con n = 3 **non si adotta**, per due ragioni
  distinte. Prima: con tre repliche non è una stima utilizzabile di varianza, e
  affiancarla al semi-range invita a trattarla come tale. Seconda: non aggiunge
  informazione, perché con n = 3 la terna (min, med, max) **è** la terna delle
  osservazioni riordinata, quindi la deviazione standard ne è una funzione
  deterministica — con `m = (min + med + max)/3` vale
  `sd = sqrt(((min−m)² + (med−m)² + (max−m)²)/2)`; verificato numericamente il
  24-10-2026 su 20.000 terne casuali in [5, 40] W, scarto massimo 3,6e-15 W — e
  le tre osservazioni sono già registrate (P1.5, P1.7). Un indicatore ridondante
  ha un solo effetto: suggerire
  che esista una σ stimata. Restano registrati i tre valori, la mediana, il
  minimo, il massimo e il range.

### P4.13 Ancoraggi

- interpolazione ai bordi: `energy_session.py:1103-1124` (`_emi_cum_at`),
  `:1126-1148` (`_emi_field_at`), `:2188-2205` (`_interpolate` sui campioni di
  sistema);
- cadenza dichiarata: `energy_session.py:80` (`POWER_SAMPLE_INTERVAL_S = 0.05`);
  cadenza misurata 0,28–0,34 s: cap. 5, §risoluzione;
- finestre di energia: `energy_session.py:1194` (`emi_window_energy_j`), `:1261`
  (`pi_window_energy_j`); lettura finestra idle: `:1576`;
- durata di finestra oggi sull'orologio di Python: `local_energy.py:156`
  (`dt = t_end − t_start`), `:171` (meno le sottofinestre escluse), `:175`
  (`duration_s`); bordi interpolati agli stessi istanti:
  `energy_session.py:1245-1250`;
- bug del sensore omonimo e fix: guard sul tipo a `energy_session.py:951-955`,
  selezione del sensore package a `:855-915`, commit `1422d1b`;
- inviluppo di progetto `hull_design`: calcolato sui 10 punti di disegno di P3.5;
  vertici `(8,4)`, `(512,32)`, `(512,256)`, `(32,256)`; margini di progetto
  verificati numericamente il 24-10-2026 — `(12,32)` → 1,33 token, `(256,192)` →
  64,0, `(32,32)` → 21,2, `(128,128)` → 107,7;
- motivo dell'inviluppo di fit `hull_fit`: il target non è una coordinata, a
  `N_in = 64` dichiarato corrispondevano **126** token reali per inferenza — la
  riga citata riporta il totale di run `tokens_in=378` su 3 inferenze, corroborato
  dai campi `prefill_s=0.3289` e `decoding_s=33.6428` della stessa riga (P2.2,
  `lhm_validation_v3_20261023_185232.csv:2`, md `:13`, `:25`); i token reali sono
  `prompt_eval_count` / `eval_count` (P2.3, F.6);
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

- se il test di P4.5 fallisce anche nella ripetizione, `u_bias,b` entra nel budget
  predittivo e la tesi dichiara che la sottrazione non è validata su questa
  macchina;
- se il pre-pilota di P3.15 mostra che un livello della griglia non è raggiungibile,
  cambiano i punti di disegno e con essi **entrambi** gli inviluppi di P4.7 —
  `hull_design` subito, `hull_fit` per conseguenza, perché cambia l'insieme dei
  blocchi di fit;
- se il lack-of-fit di P3.9 è significativo, `chain_status` scende a
  `model_inadequate` e la superficie si riporta come descrizione.

---

## P6 — Esecuzione e analisi (aperto)

P6 non è congelato: raccoglie i vincoli che i punti già congelati impongono
all'esecuzione, e che altrimenti resterebbero impliciti fino al giorno della
campagna. Ogni numero qui sotto è aritmetica dei punti congelati, non una stima.

**Eccezione dichiarata del 2026-10-24.** Questa sezione diceva di non contenere
decisioni, e da oggi ne contiene due. Le voci da P6.3 in poi sono nate dalla
revisione esterna del 2026-10-24 e non sono vincoli derivati: **P6.3 (audit idle) e
P6.4 (simulazione Monte Carlo) sono adottate come requisiti vincolanti**, perché
punti congelati ne dipendono — P4.8 rimanda a P6.4 per la copertura del bootstrap e
P4.5 per la verifica del quorum di sei coppie. P6.5 resta un elenco di requisiti
trasmessi a P5, che è aperto. L'ordine di esecuzione resta aperto, con l'unica
precedenza fissata in P6.4: dopo la chiusura di P5, prima della pubblicazione degli
intervalli.

### P6.1 Pavimento di tempo a muro delle finestre idle

- ogni blocco misura la baseline una volta sola, con tre finestre pre da 30 s e
  tre post da 30 s (P1.5, P3.7): 6 × 30 s = **180 s per blocco**;
- la campagna principale ha **39 blocchi** (P3.5: 33 di fit su 10 punti, con il
  centro a 6, più 6 di conferma su 2 punti): 39 × 180 s = **7.020 s = 1 h 57 min**;
- la campagna di gate di P4.4 aggiunge **12 blocchi** (6 coppie × carico +
  controllo, emendamento del 2026-10-24; erano 6 blocchi con tre coppie):
  12 × 180 s = **2.160 s = 36 min**;
- pavimento complessivo delle sole finestre idle: **9.180 s = 2 h 33 min**;
- a questo si aggiungono due attese per blocco, ognuna con tetto 120 s: il
  settling prima del pre e il settling prima del post (P1.5). Nel caso peggiore,
  se entrambi raggiungono il tetto: sui 39 blocchi della campagna principale
  39 × 240 s = **9.360 s = 2 h 36 min**, e sui 12 blocchi del gate
  12 × 240 s = **2.880 s = 48 min**.

**Come vanno letti questi numeri.** 2 h 33 min è il **pavimento delle sole
finestre idle**: esclude le 117 richieste della campagna principale e le 18 del
gate, i warm-up, il cooldown fra i punti
(P1.5, criterio distinto dal settling), i ritentativi di P1.6 e ogni
interruzione. 2 h 36 min e 48 min sono il **massimo** dei due settling, non il loro
valore tipico: la durata tipica del settling non è mai stata misurata su questa
macchina con la struttura v4, quindi non esiste una stima di durata totale
affidabile. Sommare pavimento e massimo produrrebbe un numero senza stato — uno è
un limite inferiore certo, l'altro un limite superiore di una sola componente — e
non va fatto. Il passaggio da tre a sei coppie costa 1.080 s = 18 min di
pavimento e, nel caso peggiore del settling, altri 1.440 s = 24 min: è il prezzo
dichiarato della potenza del gate, non un arrotondamento.

**Cosa ne segue.** La durata totale diventa stimabile solo dopo che il pilota ha
prodotto due grandezze: la mediana della durata di richiesta (che P4.4 requisito 5
usa già per fissare `dt_nominal_s`) e la durata reale dei settling. Registrare
`settle_pre_s` — già previsto da P1.5 — e il valore corrispondente del post, il
cui nome è compito di P5, sui primi blocchi del pilota, e stimare la durata
totale **prima** di pianificare la campagna principale. La conseguenza operativa
è che la campagna non è pianificabile a calendario senza quella stima, e che una
sua interruzione rompe la continuità dello stato macchina richiesta da P1.4
(`keep_alive = -1`, modello residente e caldo), producendo blocchi non
confrontabili.

### P6.2 Il pilota deve eseguire la sequenza di baseline di P1.5

Conseguenza del rinvio approvato in P1.7, non una modifica di P2.9.

La forma di combinazione di `budget_base_w` si decide sui dati del pilota, e il
dato che manca è `half_range_pre_w`, cioè l'escursione fra le tre repliche pre.
Le tre prove di P2.9 (A semantica di `done_reason`, B cache, C contesto) non lo
producono da sole: nessuna delle tre prescrive finestre di baseline. I run v3,
che sono gli unici dati di baseline esistenti, usavano una finestra da 10 s per
fase (`lhm_validation_v3_20261023_185232.md:6`), quindi non esiste ancora una
terna.

Il requisito di esecuzione è quindi: **il pilota gira con lo stesso runner della
campagna, e ogni suo blocco esegue la sequenza completa di P1.5** — settling, tre
finestre pre da 30 s, tre post da 30 s — così che le prove A, B e C producano
anche le prime terne reali. P2.9 resta congelato com'è: cambia come il pilota
viene eseguito (P6), non che cosa verifica (P2). Se il pilota fosse eseguito con
un harness diverso dal runner di campagna, la decisione rinviata in P1.7 non
avrebbe dati su cui chiudersi e andrebbe presa senza evidenza.

### P6.3 Audit idle prima della campagna

Proposta della revisione esterna del 2026-10-24, **adottata come requisito
vincolante di esecuzione** lo stesso giorno. Non cambia nessuna soglia.

Il rischio è ancorato ai soli dati di baseline esistenti: nel run v3 post-fix la
baseline pre va da 9,35 a 18,78 W, `dP` per run fra −9,31 e +5,80 W, `P_base`
media 11,55 W con CV 22,5% (`:318-320`,
`lhm_validation_v3_20261023_153604.md:12-20,24`). Se la macchina non è stazionaria
a riposo, i flag `r_A`, `pre_unstable` e `baseline_unstable` invalidano la
campagna **dopo** averla eseguita, cioè dopo il pavimento di 2 h 33 min di P6.1.

Requisito: **prima** del pilota e **prima** della campagna, un audit idle di
30 minuti sulla macchina nella configurazione esatta di misura — GUI di
monitoraggio chiuse (il costo dell'osservatore è misurato: fra ~0,2 e ~0,9 W su un
idle di ~11 W, non distinguibile dal drift, `observer_cost_20261023_analisi.md:69`),
processi in background elencati, piano energetico registrato, aggiornamenti
automatici e antivirus sospesi o dichiarati, nessuna sessione utente interattiva
aperta. Esito registrato come artefatto in `experiment_results/` con l'elenco dei
processi e le sei finestre da 30 s lette con la sequenza di P1.5. Se l'audit mostra
`pre_range_w > 1,0 W`, la campagna non parte e si dichiara perché: la soglia è
quella congelata di P1.6, non una nuova.

Costa mezz'ora e sposta la scoperta da dopo a prima. È l'unico requisito di P6 che
può evitare di bruciare l'intera campagna.

### P6.4 Simulazione Monte Carlo del protocollo

Nata come proposta della revisione esterna del 2026-10-24. Non è codice di
produzione: è un harness di analisi, quindi non tocca il blocco del sorgente.

**Adottata come requisito vincolante il 2026-10-24**, non più come proposta: due
punti congelati ne fanno ormai una condizione di pubblicazione. P4.8 dichiara la
copertura del bootstrap *nominale e non arbitrata* finché questa simulazione non la
verifica, quindi la tesi non può scrivere "95%" prima; e P4.5 rinvia qui la verifica
che sei coppie e il quorum di quattro bastino. Precedenza: **dopo** la chiusura di
P5 e **prima** della pubblicazione degli intervalli della campagna, perché la
simulazione deve girare sul disegno e sui pesi che il runner implementa davvero. Non
è un prerequisito dell'esecuzione: la campagna si può correre prima, sono i numeri
pubblicati che aspettano la simulazione.

Superficie nota con coefficienti scelti entro l'ordine di grandezza atteso, rumore
idle e deriva campionati dalle distribuzioni misurate in v3, 39 blocchi con la
geometria di P3.5 più le 12 del gate di P4.4 per il punto 2, e si osservano: bias
dei coefficienti stimati, copertura reale
degli intervalli, probabilità che i gate falliscano quando il protocollo è
corretto (falso fallimento) e che passino quando non lo è.

Arbitra **cinque** punti aperti in una volta sola, tutti oggi privi di dati:

1. la concentrazione dei pesi `w_b = 1/budget_fit_b²`: la simulazione mostra quanta
   quota del peso totale prende il blocco con il semi-range più piccolo al variare
   del rapporto `ρ = u_base/u_within` — in media il 37% e l'82% nel 5% dei casi
   peggiori a `ρ = 0`, contro l'8% a `ρ ≥ 0,5`. `ρ` oggi non è misurabile:
   `u_base` si può stimare, `u_within` no, perché non esiste ancora un blocco v4
   con tre richieste;
2. la potenza e la circolarità del gate P4.5, la cui soglia per blocco contiene lo
   stesso `dP` che genera `E_net,control`. Con l'emendamento a sei coppie la
   simulazione deve dire anche se il quorum di quattro controlli utilizzabili è
   sufficiente, cioè quanta probabilità c'è che il gate dichiari `bias_declared`
   su una macchina corretta solo perché il filtro ne scarta troppi;
3. il fattore 2 nell'intervallo di conferma di P3.10, di cui oggi non si conosce la
   copertura nominale;
4. la forma di combinazione di `budget_base_w` rinviata in P1.7 (task aperto):
   quadratura contro somma aritmetica, con l'effetto su pesi, bootstrap e gate;
5. la copertura reale degli intervalli bootstrap di P4.8, che il punto congelato
   dichiara **nominale e non arbitrata** e rimanda a questa simulazione. La
   simulazione misura la copertura del parametrico e del predittivo sui quantili
   delle quantità derivate, con e senza la correzione di leva `1/√(1 − h_b)`, e
   verifica se la soglia operativa del 10% sulla differenza fra i due sia
   coerente con lo scarto che effettivamente introducono.

Vincolo di metodo: la simulazione **non** può validare la scala assoluta, perché
genera essa stessa l'energia. Serve a controllare la procedura statistica, non la
misura. Va dichiarata come tale nella tesi.

### P6.5 Requisiti per P5 emersi dalla revisione esterna

P5 è aperto; questi sono vincoli che i punti già congelati gli trasmettono,
registrati qui perché non si perdano.

- **Lettura sincrona del contatore ai bordi di finestra — requisito vincolante,
  deciso il 2026-10-24 in P4.6.** Oggi i bordi passano da
  `_emi_cum_at`, che interpola su un buffer campionato a 0,28–0,34 s misurati, e
  fuori copertura ma entro 1 s restituisce il valore estremo
  (`energy_session.py:1103-1124`). Leggere il contatore direttamente all'istante di
  bordo, col suo timestamp, elimina i termini di disallineamento e di copertura di
  P4.6 e riduce `u_edge` di circa un fattore 6 — fattore che resta da misurare nella
  configurazione di campagna e non si pubblica come acquisito. L'evidenza che la rende possibile
  esiste già (`emi_50ms_probe_20261023_*`). È la via (b) di P4.6, **adottata e non
  più alternativa aperta**: la via (a) è scartata perché richiede un `ΔP_tick` che
  oggi nessuna parte del codice misura, e perché introdurrebbe dentro un limite
  superiore una stima con la propria incertezza.
- **`Δt_W` dalla stessa coppia di letture.** Conseguenza del requisito precedente,
  e non opzionale: la finestra è delimitata dalle due letture sincrone e `Δt_W` è la
  differenza dei loro timestamp. Oggi `duration_s` è `t_end − t_start` sull'orologio
  di Python (`local_energy.py:156`, `:171`) mentre l'energia è interpolata a quegli
  istanti (`energy_session.py:1245-1250`): due intervalli che coincidono solo se
  l'interpolazione è esatta. Energia e durata devono riferirsi allo stesso tratto,
  altrimenti `E_base = P_pre · Δt_W` sottrae l'energia di un tratto diverso da
  quello misurato e `E_act,i` di F.2 perde significato.
- **Livello di aggregazione dei conteggi di token, dichiarato.** Emerso il
  2026-10-24 correggendo un ancoraggio sbagliato (P2.2, P3.15, P4.7, P4.13):
  l'export v3 mette tre inferenze in una sola riga di finestra, quindi
  `tokens_in=378` e `tokens_out=352` sono **totali di run**, mentre il campo JSON
  si chiama `tokens_in_mean` (`experiment_validate_lhm.py:698`, media su run di un
  totale di finestra: 378 con `n_runs=1`) e il report scrive "378 token di input
  medi" (`lhm_validation_v3_20261023_185232.md:25`). Il rapporto `J/token` è
  invariante rispetto all'aggregazione — 430,7375/352 = 1,223686, identico a
  143,579/117,33 per singola inferenza — quindi **non c'è un difetto numerico**:
  c'è un livello non dichiarato, che ha già prodotto una citazione in cui il
  numero giusto (126 per inferenza) puntava a una riga che ne contiene un altro
  (378). P5 fissi il livello per riga. La v4 stima il modello per blocco su
  `prompt_eval_count_i` della singola richiesta (P2.3, F.6), quindi la riga deve
  essere per richiesta, oppure portare `n_inferenze` accanto ai totali e il livello
  nel nome del campo: un conteggio senza livello dichiarato non è leggibile da un
  terzo, e un ancoraggio non verificabile equivale a nessun ancoraggio (AGENTS.md).
- **Matrice di disegno centrata e scalata.** Sui 33 blocchi di P3.5, con matrice
  `(1, N_in, N_out, N_in·N_out)`, il condizionamento in 2-norma vale 1,0227e5 e
  scende a 3,761 con i predittori non costanti in z-score e l'intercetta intatta
  (9,0 con `N_out²`, 17,0 con anche `N_in²`): la doppia convenzione è dichiarata
  perché senza di essa il numero non è riproducibile — è perché i 10/19/33 dei
  revisori non sono citabili. Rango 4 pieno e leva max 0,285 (media 4/33) sono
  stimabilità algebrica, non stabilità numerica: ricalcolati il 2026-10-25 da
  `condizionamento_disegno_probe.py`, che misura anche le cifre perse dai quattro
  solve, 1,05-5,35 sui 24 casi con almeno 10,30 corrette — "circa cinque cifre"
  era il caso con β interi, un limite non una proprietà. P5 prescriva QR o SVD su
  predittori centrati e scalati, mai equazioni normali; β in unità P3.3 con inversa.
- **Nome del campo del settling post.** P6.1 chiede la durata reale di entrambi i
  settling; `settle_pre_s` è già previsto da P1.5, quello del post non ha nome.
- **Collocazione dei campi per punto.** `err_rel`, `intervallo_conf`,
  `pred_nonpositive`, `coverage_tier`, `coverage_tier_design`, `coverage_tier_fit`,
  `hull_margin_tok`, `hull_margin_design_tok` sono per punto di
  conferma o per blocco, non per richiesta: P5 decida se stanno nel CSV delle
  righe (ripetuti) o in un artefatto separato, e lo dichiari.
- **Tre colonne di stabilità non esistono nello schema attuale.** `pre_range_w`,
  `dP` (entrambe elencate da P4.12 dal 2026-10-25) e `budget_base_j` (F.4) non
  compaiono in `CSV_COLUMNS` (`casualwatt_csv_export.py:17-108`), verificato il
  2026-10-25: senza di esse i flag `pre_unstable`, `baseline_unstable` e
  `control_unstable` sono affermazioni non verificabili dai dati salvati e il gate
  di P4.5 non è calcolabile da un terzo. Sono campi nuovi, da aggiungere con
  `ensure_header` come gli altri accodati in coda.
- **Metrica di `hull_margin_tok` da implementare, non da interpretare.** La
  distanza dichiarata in F.13 il 2026-10-25 è la **perpendicolare euclidea dalla
  retta dello spigolo più vicino**, in coordinate grezze e con segno negativo
  fuori dall'inviluppo. P5 specifichi che l'implementazione calcola quella e non
  la distanza dal vertice più vicino, che per il punto di conferma (12,32) dà
  28,28 invece di 1,33 (fattore 21,3) e rovescia il flag congelato
  `thin_support`.

---

## Formulario consolidato (P1–P4)

Sezione derivata: **nessuna decisione nuova**. Ogni formula è riportata dal punto
congelato indicato fra parentesi; se questa sezione e il punto divergono, vince il
punto. Esiste perché P5 e P6 dovranno tradurre queste formule in colonne e in
codice, e una traduzione senza l'ordine di calcolo e senza la ragione di ogni
forma è esattamente il punto in cui si introducono errori silenziosi.

### F.0 Ordine di calcolo

Passo 0, una volta sola **prima** della campagna principale: la campagna gate
load-versus-control di P4.4, sei coppie → `controls_usable_n`, `bias_w`,
`bias_jtok_pct_lo`, `bias_jtok_pct_hi`, `control_unstable`, `validation_bias_pass`
e quindi `u_bias,b = |bias_w| · Δt̄_W,b` (F.12). È il passo 0 perché
`budget_pred_b` del passo 9 ne dipende: con `u_bias,b` scritto in formula
(emendamento del 2026-10-24, P4.6) il budget predittivo non è calcolabile prima
che il gate sia eseguito. Se il gate passa, `u_bias,b = 0` e il passo 9 resta
quello di prima.

Per ogni blocco `b` della campagna principale, nell'ordine:

1. tre finestre pre → `P_rep,1..3`, `baseline_pre_w` (F.1);
2. `m = 3` richieste → per ciascuna `E_pkg_gross,i`, `Δt_W,i`, `N_in,i`,
   `N_out,i`, `done_reason` (F.6);
3. tre finestre post → `baseline_post_w`, `dP` (F.1);
4. `E_act,i` firmato, mai troncato (F.2);
5. controlli di stabilità di P1.6 sul blocco **di carico**: `pre_range_w`, `r_A`,
   `r_B` e flag (F.3). Sui blocchi di **controllo** della campagna di P4.4 `r_A` e
   `r_B` non sono calcolabili, perché il denominatore `E_net_abs` è vuoto: vale il
   filtro assoluto di P4.5 (`pre_range_w,c ≤ 1,0 W` e `|dP_c| ≤ 1,0 W`) e il flag è
   `control_unstable`;
6. `budget_base_w,b`, `budget_base_j,b` (F.4);
7. medie di blocco `Ē_b`, `x1_b`, `x2_b`, `x12_b` (F.7);
8. `u_base,b`, `u_within,b`, `budget_fit_b`, `w_b` (F.9);
9. `Δt_tick,b`, `P_peak,b`, `Δt̄_W,b`, `u_edge,b`, `u_bias,b` (dal passo 0),
   `budget_pred_b` (F.11);
10. fit WLS sui 33 blocchi → `θ̂ = (E0, a, b, c)` (F.9);
11. residui, `z_b`, `z_pe,b`, `h_b`, bootstrap a 2000 repliche → intervallo
    parametrico e predittivo, stessa procedura ripetuta su `z_b^leva` come
    sensibilità obbligatoria e allo stesso seed, `F_lof`, `p_lof_perm`,
    `lof_max_rel` (F.14);
12. conferma sui 6 blocchi esclusi dal fit → `err_rel`, `intervallo_conf`,
    `pred_nonpositive` (F.10);
13. copertura → `hull_design` (noto da prima), `hull_fit` (dai 33 blocchi del
    passo 7), `hull_margin_tok`, `hull_margin_design_tok`, `coverage_tier` come
    più conservativo fra `coverage_tier_design` e `coverage_tier_fit` (F.13);
14. `chain_status` dai sei anelli (P4.9), con l'anello 4 già deciso dal passo 0.

I passi 1–9 sono per blocco e vivono nel CSV riga per riga; il passo 0 e i passi
10–14 sono analisi e vivono nel verbale. Quali dei primi diventino colonne lo
decide P5.

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

E_net_abs,b = |Σ_{i∈blocco} E_net_incremental,i|  =  m · |Ē_b|
E_net_abs,p = |Σ_{i∈punto}  E_net_incremental,i|

r_A = |dP| · Σ_{i∈blocco} Δt_W,i / E_net_abs,b
r_B = |dP| · Σ_{i∈punto}  Δt_W,i / E_net_abs,p
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
attribuibile e gonfierebbero il numeratore. Il denominatore è `E_net_abs` — valore
assoluto **della somma**, non somma dei valori assoluti — così le singole
`E_net_incremental,i` restano firmate (P1.3, F.2), `r_A ≥ 0` sempre e il filtro
non diventa cieco quando la somma è negativa; è anche la grandezza che entra nel
fit, perché F.7 stima su `Ē_b`. Se il denominatore è zero, blocco o punto è
invalido per costruzione: un blocco con energia netta media nulla non porta
informazione e il drift non è valutabile in rapporto a nulla. I flag non
invalidano da soli: entrano nel budget di F.4. Il simbolo `E_trunc` della prima
versione congelata è eliminato (P1.6, emendamento del 2026-10-24).

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
prefill marginale **a `N_out = 0`**, `b` J/token di decode marginale **a
`N_in = 0`**, `c` interazione. Con l'interazione presente i costi marginali sono
`∂E/∂N_in = a + c·N_out` e `∂E/∂N_out = b + c·N_in`, quindi `a` e `b` da soli
non lo sono in generale.

*Giustificazione.* La superficie è lineare **nei parametri**; `c·N_in·N_out` è
un'interazione bilineare, non un termine quadratico, e non si aggiungono `N_in²`
o `N_out²`. `c ≥ 0` è atteso perché la KV cache cresce con `N_in` e ogni token di
decode legge un contesto più lungo — la stessa giustificazione implica però un
termine in `N_out²` che il modello non ha: se il costo del contesto al passo `j`
cresce come `N_in + j`, la somma esatta è `N_in·N_out + N_out·(N_out+1)/2`. `c`
assorbe parte di un effetto con componente quadratica, e il modello primario è
un'**approssimazione dichiarata**, non la forma fisica della superficie (P3.3).
Il modello ridotto
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
E_meas          = media dei 3 blocchi del punto di conferma
E_pred          = modello ai parametri stimati sui soli blocchi di fit
err_rel         = |E_meas − E_pred| / E_pred         # solo se E_pred > 0
u_conf          = semi-range(E_meas,1..3)             # non diviso per √3
intervallo_conf = [q2.5 − 2·u_conf , q97.5 + 2·u_conf] # quantili bootstrap della previsione
passa se        err_rel ≤ 10%  e  E_meas ∈ intervallo_conf

E_pred ≤ 0  →  err_rel = None, pred_nonpositive = true, il punto non passa
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
sensibilità (P4.6). Poiché i quantili predittivi sono già allargati con il
`budget_pred` del blocco nuovo (P4.8), `u_bias,b` — se il gate di P4.5 non passa —
entra in `intervallo_conf` attraverso quella via: non va aggiunto una seconda volta.
`intervallo_conf` non è un intervallo al 95%: i quantili lo
sono, l'allargamento di due semi-range no, e la copertura risultante non è
quantificata (P3.10). Il caso `E_pred ≤ 0` è dichiarato come fallimento della
previsione perché `E0` non è vincolato positivo (P3.3, `intercept_nonphysical`):
una divisione implicita produrrebbe un `err_rel` senza significato.

### F.11 Termine di bordo e budget predittivo (P4.3, P4.6)

```
δt_edge,b      = Δt_tick,b / 2
u_edge,b       = 2 · P_peak,b · δt_edge,b  =  P_peak,b · Δt_tick,b
Δt̄_W,b         = (1/m) · Σ_{i∈blocco b} Δt_W,i
u_bias,b       = |bias_w| · Δt̄_W,b        # 0 se il gate di P4.5 passa
budget_pred_b² = budget_fit_b² + u_edge,b² + u_bias,b²
```

**`u_bias` compare** (emendamento del 2026-10-24: nella versione congelata era
assente dalla formula benché P4.4 requisito 1, P4.5, l'anello 4 di P4.9, P4.14 e
F.12 ne affermassero l'ingresso in `budget_pred`, e benché `u_bias_j` fosse già un
campo obbligatorio di P4.12). La lettura adottata è il **contributo di incertezza**,
non la correzione sistematica: `bias_w` si dichiara con il suo segno nel verbale e
nella tesi, non si sottrae dai dati, e P1 non cambia. La grandezza che moltiplica
`bias_w` è `Δt̄_W,b`, durata media delle finestre del blocco, scritta per esteso
perché `bias_w` è un watt medio di campagna e senza di essa il campo `u_bias_j` non
è calcolabile. Motivi e alternativa scartata in P4.6.

*Applicazione.* Per blocco. Ogni numero **pubblicato** — `J/token`, previsione su
un punto, contributo di un coefficiente — esce con `budget_pred`, mai con il solo
`u_base`. La scala di entrambi i budget è quella di `Ē_b`, media per richiesta del
blocco (F.7), **non** il totale di blocco: è la ragione per cui la durata è
`Δt̄_W,b` e non `Σ_i Δt_W,i` (P4.6, dichiarazione del 2026-10-25).

*Giustificazione.* Ogni bordo della finestra cade quasi sempre fra due campioni e
il contatore cumulativo è letto per interpolazione lineare (`_emi_cum_at`,
`energy_session.py:1103-1124`). L'errore di un bordo è al più `P_peak · δt_edge`,
e i bordi sono due, **per disallineamento**: se l'istante di bordo usato da Python
e il timestamp del campione EMI non coincidono, un'energia `P · δt` finisce dal
lato sbagliato del bordo. Non è invece un limite dell'**interpolazione**, che a
potenza costante ha errore nullo — rigenerato dall'harness tracciato
`u_edge_interpolazione_probe.py` (5/5 verifiche, exit 0, 2026-10-25) a `P = 35 W`,
`Δt_tick = 0,30 s`, `n = 2 000 001`: residuo **relativo** alla grandezza del
contatore 7,0e-12, invariante in `P`. L'assoluto è proporzionale a `P` e cresce
con la densità di griglia, quindi il `3,0e-11 J` scritto qui in precedenza è
**ritirato** anche in questa occorrenza, come già in P4.6: era l'assoluto di una
griglia non dichiarata. L'errore dipende dalla
variazione di potenza dentro il tick, con limite `ΔP_tick · Δt_tick / 4` per bordo
(1,8750 J con `ΔP_tick = 25 W`). Un terzo modo non è coperto: fuori copertura ma
entro 1 s `_emi_cum_at` restituisce il valore estremo (`:1111-1116`), cioè
attribuisce energia zero al tratto, fino a `P_peak · 1 s`. I tre termini sono
concordi in segno, quindi 10,5 J non li maggiora tutti: la formula è congelata e
non cambia. La scelta è **chiusa** il 2026-10-24 a favore della lettura sincrona ai
bordi (via (b), requisito vincolante di P5, con `Δt_W` dalla stessa coppia di
letture); il termine di interpolazione (via (a)) è scartato perché richiede un
`ΔP_tick` misurato che oggi nessuna parte del codice produce, e perché metterebbe
una stima dentro un limite superiore. Finché P5 non è implementato, il valore
pubblicato resta 10,5 J con la dichiarazione che copre il disallineamento e non gli
altri due modi. Dettagli che cambiano il numero:
`Δt_tick,b` è l'intervallo **misurato** del buffer EMI nel blocco, non il
dichiarato `POWER_SAMPLE_INTERVAL_S = 0.05` (`energy_session.py:80`) — in
produzione è 0,28–0,34 s; `P_peak,b` è la potenza **totale** di picco, non la
netta, perché ciò che si legge è un contatore che accumula potenza totale e
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
filtro di stabilità (P4.4 req. 7):  controllo utilizzabile se
                                    pre_range_w,c ≤ 1,0 W  e  |dP_c| ≤ 1,0 W
                                    altrimenti flag control_unstable = true

per blocco di controllo c:  passa se |E_net,control,c| ≤ budget_base_j,c

bias_w = Σ_c E_net,control,c / Σ_c Δt_W,c     sui soli controlli utilizzabili
passa se |bias_w| ≤ mediana_c(budget_base_w,c)

meno di quattro controlli utilizzabili su sei coppie:  gate non eseguibile,
  chain_status = bias_declared          # quorum = ⌈2/3 · n_coppie⌉, frazione congelata

bias_jtok_pct_lo = |bias_w| · 6    # % di J/token, grandezza riportata,
bias_jtok_pct_hi = |bias_w| · 11   # non una soglia; scala ancorata a 1 W.
                                   # Il campo e' la coppia: un intervallo non
                                   # sta in un campo solo (P4.5)

Δt̄_W,b = (1/m) · Σ_{i∈blocco b} Δt_W,i    # blocchi della campagna principale, non del gate
se non passa:  u_bias,b = |bias_w| · Δt̄_W,b   → in quadratura in budget_pred_b
se passa:      u_bias,b = 0
```

*Applicazione.* Campagna separata, 6 blocchi di carico + 6 di controllo (emendamento
del 2026-10-24: erano tre coppie), stessa geometria del punto di conferma `(12,32)`,
stessa durata, ordine randomizzato con seed registrato; è un gate prima della
campagna principale.

*Giustificazione.* Il criterio è calcolabile in virtù del requisito 7 di P4.4:
`pre_range_w,c`, `dP_c`, `budget_base_j,c` e `budget_base_w,c` esistono su un blocco
di controllo perché quel blocco esegue la stessa struttura di baseline 3 pre + 3 post
dei blocchi di carico. **`r_A` e `r_B` non esistono su un controllo** e non sono
usati qui (emendamento del 2026-10-24): hanno al denominatore `E_net_abs`, somma
sulle richieste valide (P1.6), e un blocco di controllo non invia richieste (P4.4
requisito 5). La versione congelata filtrava `bias_w` "sui soli blocchi con
`r_A ≤ 10%`", che alla lettera rendeva invalido ogni controllo e non eseguibile
l'anello 4: il filtro è sostituito dalle soglie assolute già congelate di P1.6,
senza numeri nuovi. `bias_w` è atteso zero per costruzione — il blocco di
controllo è identico per struttura, stato macchina e durata, senza alcuna
richiesta — quindi il test è falsificabile, a differenza di un confronto fra due
letture dello stesso registro. Se il test fallisce, `bias_w` si dichiara con il suo
segno, `u_bias,b = |bias_w| · Δt̄_W,b` entra in quadratura in `budget_pred_b` dei
blocchi della campagna principale (F.11), e **P1 non cambia**: sostituire
l'estimatore sulla base di un solo test sarebbe cambiare metodo senza evidenza. Il
bias non si sottrae dai dati — è un contributo di incertezza, non una correzione
sistematica (P4.6). Una sola ripetizione, per distinguere un transitorio da un bias
sistematico. Soglie congelate prima dei dati.

Il filtro `|dP_c| ≤ 1,0 W` ha un secondo effetto, non solo di stabilità: limita la
circolarità del criterio per blocco, la cui soglia `budget_base_j,c` contiene
`half_drift_c = |dP_c|/2` misurato sullo stesso blocco che produce
`E_net,control,c`. Vedi P4.5 e §3.4 della valutazione.

Le sei coppie e il quorum di quattro sono l'emendamento del 2026-10-24 (revisione
esterna §4.7): con tre coppie la mediana della soglia era su tre valori e un solo
controllo scartato lasciava il gate in mano a due blocchi. `bias_jtok_pct` traduce
il bias nell'unità della metrica pubblicata con la sensibilità ancorata (1 W ≈
6–11% di `J/token`) ed è una grandezza riportata, non un criterio. Non sono
adottati né l'intervallo t sul bias medio — richiederebbe una varianza stimata su
al più sei blocchi, contro il linguaggio di F.4 — né il test di equivalenza a
±3–5%, che convertito vale 0,27–0,83 W ed è quindi più stretto delle soglie
congelate: si dichiara invece che un gate passato **non** dimostra
quell'equivalenza. Motivazioni complete in P4.5.

Due limiti da scrivere insieme al risultato: il controllo valida lo **zero**
dell'estimatore, non l'assenza di effetti termici sotto carico (un aumento reale
del fondo durante l'inferenza è un effetto fisico che nessun blocco di controllo
rimuove, e P1 lo tratta come drift diagnostico); e non arbitra la **scala
assoluta**, perché legge lo stesso registro di LibreHardwareMonitor.

### F.13 Copertura: inviluppo convesso (P4.7)

```
metrica dei margini: distanza PERPENDICOLARE euclidea dalla retta dello spigolo
                   più vicino, coordinate grezze (token, token), negativa se fuori;
                   non è la distanza dal vertice (P4.7, dichiarata il 2026-10-25)

lato di progetto:  hull_design, vertici (8,4) (512,32) (512,256) (32,256)
                   box_design = 8 ≤ N_in ≤ 512 ,  4 ≤ N_out ≤ 256
                   punto = coordinate TARGET del punto
                   → coverage_tier_design, hull_margin_design_tok

lato di fit:       hull_fit = inviluppo delle 33 coppie (x1_b, x2_b) dei blocchi di fit
                   box_fit  = [min x1_b, max x1_b] × [min x2_b, max x2_b]
                   punto = (x1_b, x2_b), medie di blocco dei token REALI (F.7)
                   → coverage_tier_fit, hull_margin_tok

A = dentro l'inviluppo                    → claim primari
B = dentro il box, fuori dall'inviluppo   → previsione descrittiva, sparse_support
C = fuori dal box                         → nessuna stima, out_of_coverage

coverage_tier = il più conservativo dei due (A < B < C)
thin_support  = true se uno dei due margini < 2 token
```

*Applicazione.* Ogni punto pubblicato esce con `coverage_tier` e con i due margini.
Nessuno dei due inviluppi si scrive a mano: `hull_design` si calcola dai 10 punti di
disegno ed è noto prima dei dati, `hull_fit` si calcola dai 33 blocchi di fit ed è
noto solo dopo la campagna. Ogni lato confronta coordinate della stessa base con un
inviluppo costruito in quella base.

*Giustificazione.* Le celle del disegno non riempiono un rettangolo: la regione
`N_in > 32, N_out < 32` è coperta, la regione `N_in < 32, N_out > 32` no, e
prendere il box avrebbe spacciato per interpolazione bilineare
un'estrapolazione mascherata. I vertici sono **quattro**, non cinque: `(32,32)`
sta dentro con margine 21,2 token e il poligono che lo includesse fra `(8,4)` e
`(512,32)` non sarebbe convesso. Margini di progetto verificati numericamente il
24-10-2026 sulle coordinate **target**: `(12,32)` → 1,33 token, `(256,192)` →
64,0, `(32,32)` → 21,2, `(128,128)` → 107,7.

Il secondo inviluppo esiste perché il fit è stimato sui token **reali** (F.6, F.7)
e il target non è una coordinata: a `N_in = 64` dichiarato corrispondevano **126**
token reali per inferenza, `tokens_in=378` su 3 inferenze (P2.2,
`lhm_validation_v3_20261023_185232.csv:2`). Classificare sulla base di progetto e stimare su quella reale
può mettere in fascia A un punto che è fuori dall'inviluppo dei dati usati dal fit.
Prendere il più conservativo dei due è la sola regola che non sposti una soglia
dopo aver visto i numeri: la fascia può peggiorare a misura fatta, e si dichiara.

Il punto operativo `(12,32)` è in fascia A di progetto per 1,33 token:
`thin_support` non cambia l'intervallo, dichiara che la classificazione A si
regge su un supporto sottile e che a sostenerla è la conferma empirica di F.10,
non la geometria. Limite ulteriore: la classificazione è sulla proiezione
`(x1_b, x2_b)`, il fit vive in `(x1_b, x2_b, x12_b)`, quindi la fascia A è
condizione necessaria non sufficiente per l'interpolazione. Non esiste una
penalità di estrapolazione inventata: la fascia B è descrittiva e la fascia C non
pubblica.

### F.14 Bootstrap dei residui standardizzati e riferimento del lack-of-fit (P4.8, P3.9)

```
r_b = Ē_b − f(x_b; θ̂)
z_b = r_b / budget_fit_b
2000 repliche, seed registrato (bootstrap_seed)
per ciascuna replica:
    ricampiona z con reintroduzione, stratificato per punto di disegno
      (10 strati, numerosità preservata: 3 per punto, 6 per il centro)
    Ȳ*_b = f(x_b; θ̂) + budget_fit_b · z*_b
    rifit WLS con gli stessi pesi w_b  → θ*

parametrico: q2,5 e q97,5 di ∂E/∂N_out = b + c·N_in,ref ; ∂E/∂N_in = a + c·N_out,ref ; J/token_32 ; J/token_128
predittivo : spread parametrico di f(x; θ*) allargato con il budget_pred del blocco nuovo
```

Stesso ciclo di repliche, seconda variante (emendamento del 2026-10-24, P4.8):
sensibilità obbligatoria alla leva, allo stesso seed del primario.

```
h_b      = w_b · x_bᵀ (Xᵀ W X)⁻¹ x_b ,   x_b = (1, x1_b, x2_b, x12_b)
z_b^leva = r_b / (budget_fit_b · √(1 − h_b))
Σ_b h_b  = 4 = p, qualunque siano i pesi

sul disegno nominale di P3.5, a pesi uguali (verificato per esecuzione 2026-10-24):
  h_b max 0,2852 sui 3 blocchi (512, 256) → fattore 1,1828 ; poi 0,2505 su (512, 32)
  0,1669 su (32, 256) ; 0,1370 su (8, 4) ; 0,0345 sui 6 blocchi (128, 128)
  media 0,121212 = 4/33

se i quantili delle quantità derivate differiscono dal primario di più del 10%
  → si dichiara e si adotta l'intervallo più largo
se la leva massima effettiva (sui token misurati, non sui target) supera 0,40
  → la sensibilità diventa primaria e lo si dichiara (1/√(1 − 0,40) = 1,29)
```

La copertura del 95% è **nominale**: poggia sulla proporzionalità dei budget alle
varianze vere (P3.8 dichiara il contrario), sull'adeguatezza del modello (P3.9) e
sull'approssimazione del ricampionamento stratificato con otto strati da tre. Va
verificata per simulazione in P6.4; finché non lo è, si scrive *livello nominale
95%, copertura non arbitrata*.

Stesso ciclo di repliche, secondo uso (emendamento del 2026-10-24, P3.9): la
distribuzione nulla della statistica F di lack-of-fit.

```
F_lof  = (SS_lof / 6) / (SS_pe / 23)     # pesata con w_b; 6 = 10 punti − 4 parametri,
                                         # 23 = Σ_punti (n_p − 1) = 8·2 + 5 + 2
z_pe,b = (r_b − r̄*_{punto(b)}) / budget_fit_b          # puro errore, 23 gdl
         r̄*_p = Σ_{b∈p} w_b r_b / Σ_{b∈p} w_b           # media di cella pesata

per ciascuna replica k:
    z*_b dal pool globale dei 23 z_pe,b, con reintroduzione, a numerosità di disegno
    preservata
    Ȳ*_b = f(x_b; θ̂) + budget_fit_b · z*_b
    rifit WLS agli stessi pesi  → superficie*_k
    F*_k = (SS_lof(Ȳ*, superficie*_k) / 6) / (SS_pe(Ȳ*) / 23)

p_lof_perm  = #{k : F*_k ≥ F_lof} / 2000      # criterio dell'anello 5 di P4.9
p_lof_asint = 1 − F_{6,23}(F_lof)             # indicativo, si riporta accanto

lof_max_rel = max_p |Ē*_p − f(x̄_p; θ̂)| / |f(x̄_p; θ̂)|     # descrittivo, senza soglia
              Ē*_p = media pesata dei Ē_b del punto p,  x̄_p = media dei (x1_b, x2_b) di p
              il valore assoluto al denominatore è d'obbligo: f può essere ≤ 0 (P3.10)
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

*Giustificazione della sensibilità di leva.* `z_b` tratta i residui standardizzati
come omoschedastici; un blocco con leva alta ha invece un residuo contratto dal
fit, quindi sottostima lo scarto di un blocco nuovo alla stessa geometria. Il
fattore correttivo massimo sul disegno nominale è 1,18, piccolo rispetto a termini
di budget costruiti per essere conservativi: per questo la correzione è una
sensibilità obbligatoria e **non** il primario, e si esegue allo stesso seed per
non confondere l'effetto della correzione con quello del rumore di
ricampionamento. La leva alta sta sui quattro vertici dell'inviluppo (F.13): se la
correzione cambiasse materialmente l'intervallo, il segnale è di disegno — la
superficie è sostenuta dai blocchi estremi e non dal centro — e non statistico. I
valori della tabella sono a pesi uguali, l'unico caso in cui la leva dipende solo
dalla geometria; con i `w_b` reali va ricalcolata, e `Σ_b h_b = 4` resta valida per
l'identità della traccia. La leva va inoltre ricalcolata sui token effettivi,
perché i target non sono coordinate (P2.2).

*Giustificazione del riferimento di lack-of-fit.* La F asintotica con `(6, 23)`
gradi di libertà è esatta solo se `w_b` è l'inverso della varianza. P3.8 dichiara
che è un peso **conservativo**, non di precisione: i `budget_fit_b` sono limiti
superiori non proporzionali alle varianze vere, quindi il quantile nominale non ha
il significato che l'anello 5 gli attribuisce, e l'errore va nella direzione
sbagliata perché `p ≥ 0,05` è un criterio di accettazione. Rigenerare i dati dalla
superficie stimata con il solo rumore di puro errore osservato impone il null in
modo esatto rispetto ai pesi realmente usati, e la conservativezza dei budget si
elide perché `z_pe,b` è già diviso per `budget_fit_b`. Si ricampionano i residui di
**puro errore** e non gli `z_b` del bootstrap parametrico perché questi contengono
anche l'eventuale lack-of-fit reale: usarli gonfierebbe il null e renderebbe il test
conservativo proprio dove deve essere potente. Il costo è nullo: repliche,
stratificazione, rifit a pesi fissi e seed sono gli stessi. Limite dichiarato: il
null parte da `f(x_b; θ̂)`, quindi con un modello molto sbagliato il riferimento è
approssimato — lo stesso limite del bootstrap, dichiarato allo stesso modo.

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
`pre_unstable`, `baseline_unstable`, `design_deviation`, `design_deviation_count`
(per blocco: era nell'elenco di P3.13 e mancava qui, corretto il 2026-10-25).
P4.12: `block_kind`,
`pair_id`, `order_seed`, `dt_nominal_s`, `dt_tick_s`, `p_peak_w`, `u_edge_j`,
`budget_fit_j`, `budget_pred_j`, `u_bias_j`, `bias_w`, `z_resid`,
`hull_margin_tok`, `hull_margin_design_tok`, `coverage_tier`,
`coverage_tier_design`, `coverage_tier_fit`, `sparse_support`, `thin_support`,
`out_of_coverage`, `bootstrap_seed`, `validation_bias_pass`, `control_unstable`,
`chain_status`; dal 2026-10-25 anche `pre_range_w` e `dP` per blocco (P4.12,
F.3), che sono gli ingressi dei flag `pre_unstable`, `baseline_unstable` e
`control_unstable`.

Grandezze che compaiono in questo formulario e che **nessun punto ha ancora
messo in elenco**: le tre repliche pre e le tre post di F.1 (oggi il CSV salva
una sola cifra in `idle_power_w`), `baseline_post_w` di F.3 (il suo differenziale
`dP` e il range `pre_range_w` sono invece elencati da P4.12 dal 2026-10-25),
`half_range_pre_w`, `half_drift_w`, `budget_base_w`, `budget_base_j` di F.4,
`Δ_sens` di F.5, `share_E0` di F.8. Sono il lavoro principale di P5, insieme a
nomi, tipi e unità di tutto il resto. Di queste, `budget_base_j` resta la sola
fra gli ingressi del test di F.12 a non essere ancora elencata da nessun punto:
è la soglia del gate di P4.5, quindi se non diventa colonna il gate non è
calcolabile dai dati salvati. `pre_range_w` e `dP` sono elencate ma non sono
colonne esistenti (`CSV_COLUMNS`, `:17-108`): P5 le aggiunga come campi nuovi.
`Δt̄_W,b` di F.11 fa caso a sé: è la media per blocco della `duration_s`
già mappata qui sopra, quindi non è una colonna nuova, ma P5 dichiari che è una
quantità derivata e da dove si calcola — `u_bias,b` ne dipende e senza quella
dichiarazione torna ambiguo.
