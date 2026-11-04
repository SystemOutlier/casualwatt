# P6.4 — Simulazione Monte Carlo del protocollo v4: verdetti

**Data di esecuzione: 2026-11-04.** Harness: `montecarlo_protocollo_p64_probe.py`
(radice, tracciato con questo documento). In questo file sono trascritte **per
intero** le cinque tabelle dei verdetti e le righe numeriche che le commentano;
il log completo (250 righe) si rigenera col comando della sezione successiva, e
nessun numero citato qui nasce da un calcolo che quel log non stampa.

Requisito congelato: protocollo P6.4 (`protocollo_v4_20261024.md:2421-2469`),
adottato come vincolante il 2026-10-24. I cinque punti che deve arbitrare sono
`:2445-2465`; il vincolo di metodo — «la simulazione **non** può validare la
scala assoluta, perché genera essa stessa l'energia» — è `:2467-2469` e vale
anche per questa analisi.

## Come rigenerare

```
cd C:\Users\Massimo\Documents\CasualWatt\CWProject
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe montecarlo_protocollo_p64_probe.py
```

Interprete: `pythoncore-3.14-64` (Python 3.14.5, numpy 2.5.1). L'interprete
predefinito sul PATH è un 3.15 senza numpy e non va usato. Host della misura:
`MINI_IT13`. Durata osservata: 1 min 31 s. Exit code atteso `0` e cinque righe
`[OK ]`, una per verifica interna. Il run è deterministico: due esecuzioni
successive dello stesso codice differiscono solo per le righe di prosa cambiate
tra l'una e l'altra (verificato il 04-11 con `diff`).

## Cosa è congelato qui e cosa è assunto

Congelato e rispettato senza duplicazioni: il disegno di P3.5 (`:998-1012`,
33 blocchi di fit su 10 punti = 9 celle + minimo `(8,4)`, centro a 6; 6 blocchi
di conferma su 2 punti; 12 controlli in 6 coppie), `m = 3`, le formule F.1/F.4
di `block_baseline` e `budget_base_j`, i pesi F.9 `w_b = 1/budget_fit_b²`, la
procedura F.14 (`:2032-2042`: `B = 2000`, seed registrato, ricampionamento dei
`z` con reintroduzione **stratificato per punto**, rifit a pesi invariati), le
soglie `10%` fra leva e primario (`:2119-2121`, reiterata in F.14 `:3217`) e
`h_max = 0,40` (`:2128-2131`, `:3219-3220`), il fattore 2
di P3.10/F.10, il quorum `⌈2/3·n_coppie⌉ = 4` e le soglie `1,0 W` del gate —
importate da `cwEnergyModular/validation_chain.py`, non riscritte.

**Assunto** (nessuna di queste è una decisione del protocollo, ognuna va
dichiarata se si cita un numero che la usa):

- la superficie generativa F.8: `E0 = 8,390 J`, `a = 0,13424`, `b = 0,55374`,
  `c = 0,000336 J/token²`, realizzata come `ΔP = 16,78 W` × durata affine
  (`t0 = 0,50 s`, `0,008 s/token` di prefill, `0,033 s/token` di decode,
  `2,0e-05 s/token²`);
- idle: media `11,55 W`, sd fra run `1,29 W`, ancorata alle otto `P_base` e alla
  previsione analitica di `lhm_validation_v3_postfix_20261023_analisi.md:20,:50,:58`;
- rumore di richiesta: `2,0%` dell'energia al centro del disegno;
- `N_REP = 400` campagne esterne: **non** congelato dal protocollo (l'errore
  standard di una copertura stimata su 400 repliche è ≈2,4 punti percentuali, e
  viene stampato accanto); `B = 2000` e `seed = 20261104` sì;
- `Δt_tick = 0,30 s` (P4.6, misurato 0,28–0,34);
- la mappatura `σ_P = ρ·σ_E/20` usata per attraversare il rapporto fra le scale
  dei due termini di budget: la `/20` porta le due scale nello stesso ordine di
  grandezza del pilota. Il `ρ` **realizzato** non coincide con quello nominale
  (i due termini vengono da statistiche diverse) e viene stampato come colonna
  propria;
- l'allargamento predittivo è applicato alla geometria di riferimento dichiarata
  (`(128,128)` per i costi marginali, il proprio punto per `J/token` ed
  `E_attesa`), con `budget_pred` mediano dei blocchi di quel punto diviso per i
  token della metrica; sui costi marginali il predittivo di F.14 **non è
  definito** e viene stampato `n/d`, non un numero inventato;
- il ricampionamento a **pool globale** dei 33 `z` è una **diagnostica**: non è
  una proposta e non sostituisce la stratificazione congelata. Serve a disentare
  la terza delle tre ipotesi di F.14.

## Limite di precedenza, dichiarato prima dei verdetti

P6.4 fissa una precedenza (`:2430-2433`): «**dopo** la chiusura di P5 e **prima**
della pubblicazione degli intervalli della campagna, perché la simulazione deve
girare **sul disegno e sui pesi che il runner implementa davvero**». P5 è chiuso
il 2026-10-26, ma la seconda metà della frase oggi **non è soddisfatta**: il
runner di produzione non calcola ancora i campi da cui derivano i pesi WLS e
`budget_fit_b`. `benchmark_v4.py:23-24` lo dichiara («non
calcola i campi di analisi (`r_A`, `r_B`, `u_edge_j`, `budget_fit_j`, ...):
restano celle vuote nei riepiloghi finché l'analisi non li produce») e `:1689-1690`
li scrive vuoti; lo stesso vale per `r_A`, `r_B` (`:1697`) e per `hull_margin_*`
in `casualwatt_csv_export.py:209-211`. Il runner produce invece `pre_range_w`,
`dP`, `budget_base_w` (`:737,:745,:756`) e `budget_base_j` (`:1650,:1686`), e
questi sono gli unici campi di budget che una campagna reale contenga.

Conseguenza esatta su cosa rigira questo harness: **il fit WLS, i pesi
`w_b = 1/budget_fit_b²`, `budget_pred`, l'inviluppo e il bootstrap di F.14
esistono nel protocollo e in questo harness sintetico, non in nessun percorso di
produzione.** I verdetti qui sotto sono quindi verdetti **sulle formule
congelate applicate a dati simulati**, non sul codice che le produrrà. Sono
comunque i verdetti che P6.4 chiede — la condizione di pubblicazione è una
proprietà della procedura statistica — ma vanno citati con questo limite
attaccato, e il secondo run di questa simulazione (quello con la precedenza
pienamente rispettata) va rifatto quando l'analisi produrrà davvero
`budget_fit_b`.

## Cinque verifiche interne (ancore rigenerate, non citate a memoria)

| # | ancora | pubblicato | rigenerato | esito |
|---|---|---|---|---|
| 1 | quota media dei pesi a `ρ = 0` (tab. 3.2, P6.4:2447) | 0,373 | 0,3727 | OK |
| 1 | mediana / p95 / ESS | 0,315 / 0,816 / 7,30 | 0,3126 / 0,8267 / 7,30 | OK |
| 2 | leva massima OLS sui blocchi `(512,256)` | 0,2852 | 0,2852 | OK |
| 2 | media delle leve = `4/33` | 0,121212 | 0,121212 | OK |
| 2 | fattore `1/√(1 − h_max)` | 1,1828 | 1,1828 | OK |
| 3 | margini d'inviluppo di P4.7 | 1,33 / 64,0 / 21,24 / 107,7 | 1,3273 / 64,0000 / 21,2372 / 107,7031 | OK |
| 4 | gate di P4.5 importato da `validation_chain.py` | quattro casi limite | risponde come P4.4/P4.5 prescrive | OK |
| 5 | F.14 sul modello esatto | — | scarto massimo fra β̂ e β vero `2,1e-14`; somma pesata dei residui `3,2e-14`; scarto massimo dei ricampionamenti `2,5e-14` | OK |

La verifica 4 fissa anche il confine: `|E_net| = 5,01 J` contro
`budget_base_j = 5,00 J` dichiara il bias, `5,00 J` **esatto** non lo dichiara —
la prova di `validation_chain.py:187` è `>` stretto, non `>=`.

## I cinque verdetti

### 1 — Concentrazione dei pesi contro `ρ`

La tabella è il **punto 4** (forma di quadratura) letto anche come punto 1; la
colonna `quota max w` è la risposta del punto 1.

```
  rho    |  rho oss. | quota max w | ESS/33 | gate dich. | copr. 95% | scarto leva
  0.00  |    0.000   |     40.1%   |  6.46  |     0.0%    | 62.5% +-2.4 |  14.9%
  0.10  |    0.024   |     37.5%   |  7.04  |    97.2%    | 60.8% +-2.4 |  14.8%
  0.25  |    0.061   |     36.0%   |  7.34  |    98.2%    | 69.0% +-2.3 |  13.9%
  0.50  |    0.122   |     32.3%   |  8.34  |    97.8%    | 68.8% +-2.3 |  12.9%
  1.00  |    0.235   |     28.2%   |  9.29  |    97.5%    | 76.0% +-2.1 |  10.9%
```

**Verdetto.** A `ρ = 0` l'ancora del protocollo si rigenera. Sul disegno reale la
quota **decresce** con `ρ` (40,1% → 28,2%) e l'ESS sale (6,46 → 9,29 su 33):
l'indipendenza da `ρ` che P6.4:2448-2450 invoca per ritirare «8% a `ρ ≥ 0,5`»
vale solo sotto `u_base = ρ·u_within` dello **stesso** blocco, qui i due termini
vengono da statistiche diverse (`budget` di baseline contro semi-range di `m`
richieste), quindi l'indipendenza **non** vale e la tabella è una funzione, come
il requisito già dice. Il ritiro di «8% a `ρ ≥ 0,5`» è confermato, ma per una
ragione diversa da quella scritta: non è che la quota sia indipendente da `ρ`, è
che sul disegno reale **dipende** da `ρ` e va misurata.

### 2 — Potenza e falsi del gate di P4.5

Griglia su `σ_P` (W), macchina **corretta** (bias zero) e con bias dichiarato
`0,30 W`:

```
  sigma_P  | usabili/12 | quorum non | un controllo |  gate  |  gate
     (W)   |  media     |   raggiunt |  sfora (q) | bias 0 | bias 0,30
    0.01   |   12.00    |      0.0%   |    27.3%   |  97.2% |  100.0%
    0.05   |   12.00    |      0.0%   |    27.3%   |  99.2% |  100.0%
    0.10   |   12.00    |      0.0%   |    27.7%   |  97.0% |  100.0%
    0.30   |   11.24    |      0.0%   |    27.6%   |  96.8% |  100.0%
    0.60   |    4.89    |     23.0%   |    43.2%   |  94.8% |   96.5%
    1.00   |    1.53    |     95.5%   |    61.6%   |  99.8% |  100.0%
```

**Verdetto.** La domanda di P6.4:2453-2455 — «quanta probabilità c'è che il gate
dichiari `bias_declared` su una macchina corretta **solo perché il filtro ne
scarta troppi**» — ha una risposta negativa: il quorum **non è il collo di
bottiglia** sulle scale reali (`0,0%` fino a `σ_P = 0,30 W`). Il falso fallimento
arriva prima e da un'altra parte: la prova **per controllo**
`|E_net,c| > budget_base_j,c`. Il gate dichiara `bias_declared` anche in assenza
di bias simulato: su una macchina corretta succede nel **96,8–99,2%** delle
campagne.

Non è un artefatto del generatore: è l'aritmetica della regola congelata. Il
rapporto `|E_net|/budget_base_j` vale, in unità di `σ_P`, `0,926` di scarto
(`√(1/3 + 0,5235)`: la media delle `m = 3` richieste più la mediana di tre
finestre) contro `1,022` di scala del denominatore
(`hypot(0,8463, 0,5715)`: semi-range atteso `0,8463 σ_P` e mezzo-drift atteso
`0,5715 σ_P`), quindi `κ = 0,906` e ogni controllo è un test da ≈**1,10 σ**:
`q = 27,0%` per controllo (misurato `27,3–27,7%`), e la catena li ANDa dodici
volte → `1 − (1 − q)^12 = 97,7%` contro il `96,8–99,2%` misurato. **Il falso
fallimento non dipende dalla scala del rumore.**

Due limiti aggiuntivi, entrambi da dichiarare con la colonna:

- a `σ_P ≥ 0,60 W` la forma chiusa sottostima, perché il filtro di P4.4 agisce
  esattamente sui due termini che compongono `budget_base_w`: tenere solo i
  controlli con `pre_range` e `dP` piccoli **assottiglia il denominatore** mentre
  il numeratore conserva il rumore delle singole finestre di richiesta, che il
  filtro non tocca. La «scelta sui denominatori» fa salire `q` a `43,2%` e
  `61,6%`.
- a `σ_P = 0` (e quindi a `ρ = 0` nelle tabelle del punto 4) il gate **non è
  eseguibile in senso forte**: le tre finestre di baseline sono identiche, quindi
  `pre_range_w = budget_base_w = E_net = 0` e la prova `>` stretto diventa
  `0 > 0 = False`. Lo `0,0%` di dichiarazione non è potenza: è un anello senza
  materia da testare.

La potenza a `bias = 0,30 W` è ≈`100%` su tutta la griglia e **non è un
risultato informativo**: con un bias reale l'anello 4 non può che dichiararsi.
Ciò che il punto 2 arbitrava era il costo in falsi, non il guadagno in potenza.

### 3 — Copertura del fattore 2 di P3.10/F.10

Sui 6 blocchi di conferma × 400 campagne = 2400 casi:

```
  copertura CON il fattore 2 (F.10 congelato): 99,8% ± 0,1
  copertura SENZA il fattore 2 (parametrico) : 69,6%
  amplificazione media della larghezza per il 2: × 9,076
```

**Verdetto.** Il numero che mancava c'è, e conferma la lettera del
protocollo: `intervallo_conf` **non è un 95%**. Con il fattore 2 congelato la
copertura empirica su 400 campagne simulate è ≈`99,8%`, e la larghezza viene
moltiplicata in media per `9,08`. Il motivo aritmetico è nella forma di F.10:
l'intervallo è `[q2.5 − 2·u_conf, q97.5 + 2·u_conf]`, quindi i due capi aggiungono
in tutto `4·u_conf` alla distanza fra i due quantili parametrici; `u_conf` è
il semi-range di un blocco singolo, ed è di un ordine di grandezza più grande
dell'incertezza dei coefficienti. **L'amplificazione non è una maggiorazione
modesta: è quasi un ordine di grandezza.** Chi pubblica `intervallo_conf` deve
scriverlo come intervallo di copertura ≈99,8% (o come intervallo
non probabilistico), mai come «95%».

### 4 — Forma di combinazione di `budget_base_w` (P1.7)

Le due tabelle, trascritte per intero (quadratura = forma di produzione,
`benchmark_v4.py:757`; somma aritmetica = l'eccezione aperta di P1.7):

```
  rho    |  rho oss. | quota max w | ESS/33 | gate dich. | copr. 95% | scarto leva
  0.00  |    0.000   |     40.1%   |  6.46  |     0.0%    | 62.5% +-2.4 |  14.9%
  0.10  |    0.024   |     37.5%   |  7.04  |    97.2%    | 60.8% +-2.4 |  14.8%
  0.25  |    0.061   |     36.0%   |  7.34  |    98.2%    | 69.0% +-2.3 |  13.9%
  0.50  |    0.122   |     32.3%   |  8.34  |    97.8%    | 68.8% +-2.3 |  12.9%
  1.00  |    0.235   |     28.2%   |  9.29  |    97.5%    | 76.0% +-2.1 |  10.9%
```

```
  rho    |  rho oss. | quota max w | ESS/33 | gate dich. | copr. 95% | scarto leva
  0.00  |    0.000   |     37.4%   |  6.97  |     0.0%    | 64.0% +-2.4 |  14.2%
  0.10  |    0.031   |     36.1%   |  6.96  |    90.0%    | 62.5% +-2.4 |  14.9%
  0.25  |    0.078   |     33.9%   |  7.76  |    90.5%    | 64.0% +-2.4 |  14.2%
  0.50  |    0.155   |     31.8%   |  8.47  |    92.0%    | 70.8% +-2.3 |  12.3%
  1.00  |    0.304   |     29.2%   |  9.22  |    92.0%    | 79.0% +-2.0 |  11.0%
```

**Verdetto.** La forma **non è arbitrata** dai dati del pilota (P2.9/P6.2 non
girati: il pilota serve per misurare `u_within,b`, denominatore del primo `ρ`
reale). Ciò che la simulazione dice è **quanto pesa la scelta**: fra le due forme
cambiano la quota del blocco più pesante (≈2–3 punti) e, sul lato del gate, la
frazione di falsi fallimenti (`97,5%` con la quadratura contro `92,0%` con la
somma a `ρ = 1`). L'ordine di grandezza è lo stesso: **la forma di combinazione
non è la leva del problema del gate**, che è la struttura della prova per
controllo (punto 2). Questo è il contenuto con cui P1.7 va chiuso quando il
pilota avrà dato il `ρ` reale.

### 5 — Copertura reale degli intervalli bootstrap di P4.8

Copertura dei quantili 2,5/97,5 su 400 campagne:

```
  quantita'                     primario    con leva   predittivo  |  fuori sotto/sopra
  dE/dN_out | N_in=128           73.8%      77.8%       n/d       |  13.8% / 12.5%
  dE/dN_in | N_out=128           73.8%      80.0%       n/d       |  12.2% / 14.0%
  J/token (32,32)                59.8%      65.2%    100.0%      |  21.2% / 19.0%
  J/token (128,128)              74.2%      77.8%    100.0%      |  12.0% / 13.8%
  E_attesa (32,32)               59.8%      65.2%    100.0%      |  21.2% / 19.0%
```

**Verdetto primario: la copertura dichiarata «nominale e non arbitrata» in P4.8
(`:2072-2080`) è ora arbitrata, e il verdetto è NEGATIVO.** Il `95%` nominale non
è supportato dalla procedura di F.14 nella configurazione simulata: la copertura
empirica del primario — su 400 campagne simulate — sta fra `59,8%` e `74,2%`.

La diagnosi è per **ampiezza**, non per bias né per scala dei budget. Quattro
scale dell'ampiezza di `θ̂`, tutte divise per la diffusione reale di `θ` sulle
400 campagne (`sd vero`):

```
  quantita'                 sd vero  sd boot   sd HC3  sd glob   sd bud    b/v    H/v    g/v    B/v
  dE/dN_out | N_in=128       0.00600    0.00293    0.00613    0.00348    0.00416  0.488  1.022  0.581  0.695
  dE/dN_in | N_out=128       0.00289    0.00152    0.00316    0.00199    0.00238  0.527  1.096  0.690  0.823
  J/token (32,32)            0.01027    0.00416    0.00990    0.00477    0.00570  0.405  0.963  0.464  0.555
  J/token (128,128)          0.00199    0.00108    0.00208    0.00122    0.00146  0.540  1.044  0.613  0.733
  E_attesa (32,32)           0.65755    0.26648    0.63335    0.30504    0.36493  0.405  0.963  0.464  0.555
```

`b/v` = primario congelato, `H/v` = HC3 (l'approssimazione lineare che F.14
chiede di riportare accanto), `g/v` = il controllo a pool globale (diagnostica),
`B/v` = l'ampiezza lineare **prendendo `budget_fit_b` per incertezza standard di
`Ē_b`**, cioè l'ipotesi che F.14 nomina per prima fra quelle su cui poggia il
`95%`.

`J/token (32,32)` e `E_attesa (32,32)` hanno numeri identici perché sono lo
**stesso funzionale** diviso per una costante (`/64`): copertura, rapporti e
bias coincidono per costruzione, e non sono due evidenze indipendenti.

Le tre condizioni dichiarate da F.14 escono in tre colonne diverse:

1. **proporzionalità dei budget alle varianze vere** → `B/v = 0,55–0,82`. Il
   `budget_fit` mediano è `2,465 J` contro una `sd(Ē_b)` reale di `1,716 J`
   (entrambe mediane sui 33 blocchi). Il rapporto che conta è **per blocco** e
   poi mediano: `1,395`, che non è `2,465/1,716 = 1,436` — la mediana dei
   rapporti non è il rapporto delle mediane, e quale blocco produca i tre punti
   di differenza non è indagato qui. Contro il fattore atteso dalle forme
   chiuse del semi-range `0,8468/(1/√3) = 1,4667`. La sd per richiesta osservata
   è `2,500 J`, e
   `σ/radice(3) = 1,444 J`. Il budget entra
   **due volte** con esponenti opposti — `κ⁻²` nei pesi e `κ²` nella varianza —
   quindi l'ampiezza lineare esce `κ⁻¹ = 0,717`: è esattamente la colonna `B/v`,
   e arbitra la prima ipotesi come **falsa in modo attivo**, non solo mancante.
   Nel ricampionamento bootstrap invece `budget_fit` **si cancella per
   costruzione** (`Ȳ* = f + budget_fit·(r/budget_fit)*`), quindi il deficit di
   `b/v` non è il fattore `1,395`: è un'altra cosa.
2. **adeguatezza del modello** → non arbitrata, ed è un limite di questo
   harness, non un risultato: la superficie generata è quella fitata, quindi lo
   scarto medio della stima dal vero è piccolo **per costruzione**
   (`1,2–5,4%` di `sd vero`). La simulazione **esclude** il modello inadeguato,
   non lo verifica.
3. **approssimazione del ricampionamento stratificato** → `b/v` contro `g/v`:
   il pool globale risale solo a `0,46–0,69`, non a `0,94`.

**Lacuna aperta, dichiarata come tale.** Il deficit di `b/v` è più grande di
quanto i due meccanismi noti prevedano: i residui in-campionamento tolgono al
più `√((n−p)/n) = √(29/33) = 0,937`; la stratificazione dentro celle da tre
toglie l'errore delle **medie di cella**, che per le equazioni di score del fit
ha somma pesata nulla, quindi un prelievo entro cella non può generare uno
scarto della media di cella più grande dello scarto fra i suoi tre `z`
(fattore `√(2/3) = 0,816`). Nessuno dei due arriva a `0,5` e nessuno dei due
spiega `b/v`. **La causa completa del deficit di ampiezza non è identificata;
le ipotesi esaminate sono insufficienti.** Ciò che è arbitrato è il fatto, col
numero: l'intervallo pubblicato da F.14 è ≈2 volte
più stretto della diffusione reale, su tutte e cinque le quantità.

Le due soglie operative di F.14, valutate sui numeri:

- **diagnostica HC3 / bootstrap (fattore 2)**: `H/v` sta a `1` (`0,96–1,10`)
  mentre `b/v` sta a `≈0,5`, quindi l'ampiezza bootstrap e quella HC3 differiscono
  di un fattore ≈2 — la condizione di F.14 `:2062-2066` **scatta**, e la sua
  conseguenza è già scritta: «il bootstrap resta primario e la discrepanza si
  dichiara». Non si adotta HC3 al posto del primario.
- **soglia di leva (`h_max > 0,40`)**: la leva massima effettiva del fit pesato
  ha mediana **0,6252**, ben sopra `0,40` (`protocollo:2129-2130`, F.14 `:3219-3220`). La conseguenza congelata
  è che **la sensibilità di leva diventa primaria**, non il primario standard.
  Lo scarto fra i quantili di leva e quelli del primario è `7,3–10,7%` con
  mediana `9,5%`, cioè **attraversa la soglia del 10%**: su `dE/dN_in` (10,7%) e
  `J/token (32,32)`/`E_attesa` la regola congelata chiede di dichiarare e
  adottare l'intervallo più largo.

Il predittivo al `100%` non è un merito: è l'effetto di aggiungere
`budget_pred` (joule di un blocco singolo) a un intervallo parametrico stretto.
Sui costi marginali il predittivo non è definito da F.14 e resta `n/d`.

## Conseguenze per la pubblicazione (non decisioni prese qui)

Tre effetti su ciò che si può scrivere, da portare alla decisione dell'autore:

1. P4.8 può ora sostituire la clausola «copertura non arbitrata» con il numero
   misurato, ma il numero dice che il `95%` nominale **non è supportato dalla
   procedura di F.14 nella configurazione simulata**: le etichette possibili
   sono «bootstrap, copertura empirica su 400 campagne simulate: 60–74%»,
   oppure una revisione della procedura. Non è questa sede per sceglierla, e la
   scelta non è presa.
2. L'anello 4 di P4.9 dichiara `bias_declared` anche in assenza di bias
   simulato — su una macchina corretta nel 97% dei casi simulati — e la sua
   entrata in `chain_status` rende `validated` praticamente irraggiungibile per
   quella via. È una proprietà della **regola congelata**, indipendente dalla
   scala del rumore, e tocca le regole di P5/P6, non solo l'analisi.
3. Il fattore 2 di F.10 produce una copertura ≈99,8%, non 95%: il nome
   `intervallo_conf` e la sua lettura vanno coerenti con P3.10, che infatti non
   lo chiama 95%.

## Incoerenza interna trovata nel testo congelato (segnalata, non corretta)

F.14 `:2078-2079` scrive che il ricampionamento stratificato poggia su «33
blocchi su 10 strati, **di cui otto da tre**». Con il disegno di P3.5
(`:1008-1009`: 10 punti = 9 celle + minimo `(8,4)`, centro a 6) gli strati da
tre sono **nove** (8 celle non centrali + il minimo) e uno da sei, che è
esattamente ciò che il pseudocodice dello stesso F.14 dice a `:2038-2039`
(«10 strati, numerosità preservata: 3 per punto, 6 per il centro»). La prosa
dell'emendamento del 2026-10-24 conta un strato in meno; il conteggio usato
dall'harness è quello del pseudocodice e del disegno. Il testo congelato non è
stato toccato.

## Vincolo di metodo (P6.4:2467-2469)

La simulazione non valida la scala assoluta, perché genera essa stessa
l'energia. Controlla la procedura statistica, non la misura. Tutti i verdetti
sopra restano dentro questa frontiera: nessuno di essi dice che il contatore
legga giusto.
