# Gate P4.4 load-versus-control

- modello: `hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest`
- DT_NOM congelato = 2.930748 s (pilota P2.9, requisito 5)
- order_seed dichiarato = gate-seed-20261107 (requisito 3)
- geometria (12,32) (requisito 4)
- 24 blocchi / 12 coppie, un blocco per invocazione

## Risultato

gate: not-executable; controlli utilizzabili = 5/12 coppie, quorum = 8; chain_status = 'bias_declared'
- VERDETTO PRIMARIO (decide) `bias_vs_budget_tc`: **not-executable** - gate non eseguibile (filtro/quorum di F.12): nessun bias da confrontare con il budget
- verdetto F.12 storico (riportato, non decide; `f12_mediana_budget_per_blocco_30s`): not-executable
- utilizzabili con block_pass=False: 5/5 (il criterio per blocco e' riportato, non decide lo status del gate)

- bias non calcolato: gate non eseguibile

## Budget pre-registrato e incertezza (grandezza riportata, NON il criterio F.12)

La soglia nasce qui, PRIMA che esista un solo blocco di questa campagna: il fondo e' letto dal contatore di package su finestre della durata nominale del controllo e aggregato con le stesse regole del budget lungo (`benchmark_v4.block_baseline`, F.1/F.4). Nessuna riscalatura per Tc/30 e nessun contributo di CodeCarbon. Il criterio che decide e' dichiarato nel piano (`criterio_primario`): |bias_w| <= budget_base_w a scala Tc. Il verdetto F.12 storico (mediana dei budget per blocco) e' riportato accanto.

- procedura: `short` | Tc = 2.930748 s | 3 unita' pre + 3 post | 1 finestre Tc per unita' (2.930748 s nominali) | 6 finestre lette in tutto | canale `emi-counter`
- potenze unita' pre = [16.388511252489543, 14.370964524691527, 13.60335907736049] W, post = [11.756515751702185, 20.755530468166814, 11.817322038395645] W
- mediana pre (baseline del fondo) = 14.370965 W | half_range_pre_w = 1.392576 W | half_drift_w = 1.276821 W
- budget_base_w = 1.889323 W | scala 30 s applicata = False | CodeCarbon usato = False | timer = 0.015625 s | quiete pre-fondo = 0.0 s

### u_c pre-esecuzione

- u_c = assente (None); U = assente; soglia del criterio primario = budget = 1.889323 W
  - u_rumore = 1.392576 W - tipo A, ESCLUSA: gia' contenuta in budget_base_w = hypot(u_rumore, u_termico): includerla in u_c conterebbe due volte la stessa dispersione e porterebbe la soglia a >= 3 * budget; `half_range_pre_w = (max - min) / 2 sulle unita' pre`; fonte: misura del fondo pre-esecuzione (short), 3 unita' di 2.93075 s nominali, canale emi-counter
  - u_termico = 1.276821 W - tipo A, ESCLUSA: nome storico: e' la deriva fra i due gruppi di finestre, non un margine termico (nessun canale termico e' usato come criterio); gia' contenuta in budget_base_w, quindi esclusa dal conto per non contarla due volte; `half_drift_w = |mediana(post) - mediana(pre)| / 2`; fonte: stessa misura del fondo: i due gruppi non sovrapposti dell'attesa di stabilizzazione, come P1.5
  - u_timer = 0.038304 W - tipo B, ESCLUSA: la risoluzione dei cpu_times e' il clock dell'attribuzione CPU, non quello della finestra del contatore: E_net,control usa il dt_W degli stessi bordi del contatore (benchmark_v4._run_control_window), quindi questo valore e' informativo e non entra in u_c; `P_fondo * (mezza risoluzione dei cpu_times) / min(dt osservato): l'errore di tempo agisce sul denominatore della potenza`; fonte: CasualWattLocalEnergyProfiler.probe_cpu_time_resolution() = 0.0156 s, stesso chiamante del runner (benchmark_v4.py:2635)
  - u_allineamento = 0.003750 W - tipo B, ESCLUSA: E_net,control sottrae P_pre * dt_W con il dt_W osservato dalla stessa coppia di bordi del contatore (benchmark_v4._run_control_window, requisito 5): lo scarto fra durata nominale e osservata non genera bias; valore informativo, non incluso in u_c; `P_fondo * max|dt_osservato - dt_nominale| / min(dt osservato): bordo temporale fra finestra chiesta e finestra effettivamente letta dal contatore`; fonte: unita' della misura del fondo: 6 unita', deviazione massima 0.000765 s su nominale 2.93075 s

### u_c post-controlli

- u_c = 0.217652 W; U = 0.604298 W (k = 2.7764, t di Student 0,975 con 4 gradi di liberta': scipy); soglia del criterio primario = budget = 1.889323 W
- accettazione con banda di guardia (riportata, non decide): None - bias o U non calcolabili: nessuna accettazione guardata. Grandezza riportata, non decide.
  - u_rumore = 1.392576 W - tipo A, ESCLUSA: gia' contenuta in budget_base_w = hypot(u_rumore, u_termico): includerla in u_c conterebbe due volte la stessa dispersione e porterebbe la soglia a >= 3 * budget; `half_range_pre_w = (max - min) / 2 sulle unita' pre`; fonte: misura del fondo pre-esecuzione (short), 3 unita' di 2.93075 s nominali, canale emi-counter
  - u_termico = 1.276821 W - tipo A, ESCLUSA: nome storico: e' la deriva fra i due gruppi di finestre, non un margine termico (nessun canale termico e' usato come criterio); gia' contenuta in budget_base_w, quindi esclusa dal conto per non contarla due volte; `half_drift_w = |mediana(post) - mediana(pre)| / 2`; fonte: stessa misura del fondo: i due gruppi non sovrapposti dell'attesa di stabilizzazione, come P1.5
  - u_timer = 0.038304 W - tipo B, ESCLUSA: la risoluzione dei cpu_times e' il clock dell'attribuzione CPU, non quello della finestra del contatore: E_net,control usa il dt_W degli stessi bordi del contatore (benchmark_v4._run_control_window), quindi questo valore e' informativo e non entra in u_c; `P_fondo * (mezza risoluzione dei cpu_times) / min(dt osservato): l'errore di tempo agisce sul denominatore della potenza`; fonte: CasualWattLocalEnergyProfiler.probe_cpu_time_resolution() = 0.0156 s, stesso chiamante del runner (benchmark_v4.py:2635)
  - u_allineamento = 0.003750 W - tipo B, ESCLUSA: E_net,control sottrae P_pre * dt_W con il dt_W osservato dalla stessa coppia di bordi del contatore (benchmark_v4._run_control_window, requisito 5): lo scarto fra durata nominale e osservata non genera bias; valore informativo, non incluso in u_c; `P_fondo * max|dt_osservato - dt_nominale| / min(dt osservato): bordo temporale fra finestra chiesta e finestra effettivamente letta dal contatore`; fonte: unita' della misura del fondo: 6 unita', deviazione massima 0.000765 s su nominale 2.93075 s
  - u_A = 0.217652 W - tipo A, INCLUSA: incertezza di tipo A della media dei controlli: decresce con n, a differenza di un range. Indipendente dal budget (derivato dal fondo, non dai controlli); `s / sqrt(n) sulle potenze nette dei controlli utilizzabili (s campionaria, ddof=1)`; fonte: potenze nette dei 5 controlli utilizzabili: media -0.195532 W, sd campionaria (ddof=1) 0.486684 W, s / sqrt(n) = 0.217652 W

### Assunzioni dichiarate

- il fondo e' letto dal contatore di package (read_idle_window_j), lo stesso canale di calibrate_idle e dell'audit P6.3: non e' un integrale di campioni
- le 3 unita' pre e le 3 post sono misurate in due gruppi consecutivi non sovrapposti: dP e' la deriva fra i due gruppi, come in P1.5, e non si assume nulla
- un delta negativo o una lettura assente fermano la misura: nessun clamp a zero e nessuna degradazione silenziosa
- budget_base_w e' un proxy conservativo di incertezza standard, non una deviazione standard (P4.12: con n = 3 non si stima una varianza) e la quadratura non e' un limite massimo garantito (P1.7)
- la procedura e' pre-registrata nel piano (budget_mode) e verificata da _verifica_piano PRIMA di qualunque misura

- artefatto: `C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261114\budget_preregistrato.json`

## Blocchi di controllo

- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: usable=False, unstable=True, pre_range_w=0.983227, dP=2.681258, E_net=-0.00913 J, dt_W=2.931086 s, E_net/dt_W=-0.003115 W, budget_base_j=4.185371, budget_base_w=1.427925 W, window=exact-counter, block_pass=None — |dP|=2.68126 W > 1 W
  baseline: P_pre_ref propagata dal carico=11.88187 W, propria del blocco=11.398864 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: usable=False, unstable=True, pre_range_w=3.067362, dP=-0.228753, E_net=-2.153066 J, dt_W=2.935595 s, E_net/dt_W=-0.733434 W, budget_base_j=4.514769, budget_base_w=1.53794 W, window=exact-counter, block_pass=None — pre_range_w=3.06736 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=12.68444 W, propria del blocco=12.899955 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01: usable=True, unstable=False, pre_range_w=0.651092, dP=0.438788, E_net=-1.809014 J, dt_W=2.931087 s, E_net/dt_W=-0.617182 W, budget_base_j=1.150666, budget_base_w=0.392573 W, window=exact-counter, block_pass=False — pre_range_w=0.651092 W <= 1 W e |dP|=0.438788 W <= 1 W
  baseline: P_pre_ref propagata dal carico=12.970362 W, propria del blocco=11.065113 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: usable=False, unstable=True, pre_range_w=2.673233, dP=-0.105556, E_net=1.318548 J, dt_W=2.931301 s, E_net/dt_W=0.449817 W, budget_base_j=3.921078, budget_base_w=1.337658 W, window=exact-counter, block_pass=None — pre_range_w=2.67323 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=10.987674 W, propria del blocco=13.868447 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: usable=False, unstable=True, pre_range_w=2.905454, dP=2.731008, E_net=2.990068 J, dt_W=2.966892 s, E_net/dt_W=1.007812 W, budget_base_j=5.915223, budget_base_w=1.993744 W, window=exact-counter, block_pass=None — pre_range_w=2.90545 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=13.714868 W, propria del blocco=14.224949 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: usable=False, unstable=True, pre_range_w=2.965801, dP=3.233303, E_net=21.940406 J, dt_W=2.931261 s, E_net/dt_W=7.484972 W, budget_base_j=6.430468, budget_base_w=2.193755 W, window=exact-counter, block_pass=None — pre_range_w=2.9658 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=18.435073 W, propria del blocco=13.173233 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-7__b01: usable=False, unstable=True, pre_range_w=4.730101, dP=0.55201, E_net=4.285206 J, dt_W=2.931189 s, E_net/dt_W=1.461934 W, budget_base_j=6.979457, budget_base_w=2.381101 W, window=exact-counter, block_pass=None — pre_range_w=4.7301 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=13.601516 W, propria del blocco=11.815888 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-8__b01: usable=False, unstable=True, pre_range_w=3.593223, dP=-5.335328, E_net=-16.254857 J, dt_W=2.931352 s, E_net/dt_W=-5.545174 W, budget_base_j=9.427952, budget_base_w=3.216247 W, window=exact-counter, block_pass=None — pre_range_w=3.59322 W > 1 W (soglia di pre_unstable, P1.6)
  baseline: P_pre_ref propagata dal carico=12.953381 W, propria del blocco=12.121097 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-9__b01: usable=True, unstable=False, pre_range_w=0.328263, dP=-0.112013, E_net=-1.167044 J, dt_W=2.931245 s, E_net/dt_W=-0.398139 W, budget_base_j=0.508348, budget_base_w=0.173424 W, window=exact-counter, block_pass=False — pre_range_w=0.328263 W <= 1 W e |dP|=0.112013 W <= 1 W
  baseline: P_pre_ref propagata dal carico=8.047689 W, propria del blocco=4.696998 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-10__b01: usable=True, unstable=False, pre_range_w=0.588352, dP=-0.124657, E_net=-1.78429 J, dt_W=2.931172 s, E_net/dt_W=-0.608729 W, budget_base_j=0.881421, budget_base_w=0.300706 W, window=exact-counter, block_pass=False — pre_range_w=0.588352 W <= 1 W e |dP|=0.124657 W <= 1 W
  baseline: P_pre_ref propagata dal carico=5.754929 W, propria del blocco=4.974318 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-11__b01: usable=True, unstable=False, pre_range_w=0.04107, dP=-0.073967, E_net=1.238526 J, dt_W=2.931461 s, E_net/dt_W=0.422494 W, budget_base_j=0.12401, budget_base_w=0.042303 W, window=exact-counter, block_pass=False — pre_range_w=0.04107 W <= 1 W e |dP|=0.073967 W <= 1 W
  baseline: P_pre_ref propagata dal carico=4.798759 W, propria del blocco=4.852324 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-12__b01: usable=True, unstable=False, pre_range_w=0.041367, dP=0.081082, E_net=0.658787 J, dt_W=2.9424 s, E_net/dt_W=0.223894 W, budget_base_j=0.133915, budget_base_w=0.045512 W, window=exact-counter, block_pass=False — pre_range_w=0.041367 W <= 1 W e |dP|=0.081082 W <= 1 W
  baseline: P_pre_ref propagata dal carico=4.767294 W, propria del blocco=4.775118 W

## Grandezze riportate, non criterio

E_net/dt_W per TUTTI i controlli (anche non utilizzabili) e statistiche descrittive fra blocchi: media, sd campionaria (ddof=1), SE, CI95 t di Student. Non decidono l'esito del gate, che resta F.12; non entrano nello schema CSV. background_load prima/dopo dal riepilogo del runner (P1.4).

| blocco | utilizzabile | E_net/dt_W (W) | background_load prima | dopo |
|---|---|---|---|---|
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01 | False | -0.003115 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01 | False | -0.733434 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01 | True | -0.617182 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01 | False | 0.449817 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01 | False | 1.007812 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01 | False | 7.484972 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-7__b01 | False | 1.461934 | True | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-8__b01 | False | -5.545174 | False | True |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-9__b01 | True | -0.398139 | True | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-10__b01 | True | -0.608729 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-11__b01 | True | 0.422494 | False | False |
| hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-12__b01 | True | 0.223894 | False | False |

### Statistiche su tutti i controlli

- n=12, media=0.262096 W, sd=2.875938 W, SE=0.830212 W, CI95=[-1.565188, 2.089380] W (t=2.2010, provenienza: scipy)

### Statistiche su soli utilizzabili

- n=5, media=-0.195532 W, sd=0.486684 W, SE=0.217652 W, CI95=[-0.799830, 0.408766] W (t=2.7764, provenienza: scipy)

## Propagazione cooldown (scelta operativa)

- controllo-1: P_pre_ref=11.88187, baseline propria del blocco=11.398864, cooldown_timeout='true'
- controllo-2: P_pre_ref=12.68444, baseline propria del blocco=12.899955, cooldown_timeout='false'
- controllo-3: P_pre_ref=12.970362, baseline propria del blocco=11.065113, cooldown_timeout='true'
- controllo-4: P_pre_ref=10.987674, baseline propria del blocco=13.868447, cooldown_timeout='true'
- controllo-5: P_pre_ref=13.714868, baseline propria del blocco=14.224949, cooldown_timeout='true'
- controllo-6: P_pre_ref=18.435073, baseline propria del blocco=13.173233, cooldown_timeout='true'
- controllo-7: P_pre_ref=13.601516, baseline propria del blocco=11.815888, cooldown_timeout='true'
- controllo-8: P_pre_ref=12.953381, baseline propria del blocco=12.121097, cooldown_timeout='true'
- controllo-9: P_pre_ref=8.047689, baseline propria del blocco=4.696998, cooldown_timeout='true'
- controllo-10: P_pre_ref=5.754929, baseline propria del blocco=4.974318, cooldown_timeout='true'
- controllo-11: P_pre_ref=4.798759, baseline propria del blocco=4.852324, cooldown_timeout='false'
- controllo-12: P_pre_ref=4.767294, baseline propria del blocco=4.775118, cooldown_timeout='false'

## Precondizione di quiete

Prima di OGNI blocco (load e control): 3 letture consecutive con background_load=False; una lettura rumorosa azzera il conteggio; al tetto (600 s) il run si ferma. Precondizione di esecuzione lato tool (P1.4): non entra nel criterio F.12.

- carico-1 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-1 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-2 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-2 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-3 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-3 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-4 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-4 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-5 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-5 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-6 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-6 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-7 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-7 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-8 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-8 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-9 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-9 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-10 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-10 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-11 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-11 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- carico-12 (load): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno
- controllo-12 (control): attesa=0.0 s, letture=0, top-5 alla partenza: nessuno

## Warm-up post-carico (criterio misurato)

Dopo OGNI blocco di carico e prima del controllo della coppia. Finestra osservata di 2 s; la fase chiude quando, SULLA STESSA finestra, la potenza resta entro 0.5 W dalla baseline_pre_w del blocco di carico E la media di cpu_percent resta sotto 2 % per 10 s continui; un campione fuori soglia su uno dei due, o una lettura assente, azzera il tratto. Al tetto 60 s la campagna si ferma (SystemExit). La temperatura CPU e' registrata all'ingresso e all'uscita e NON decide: su questo host non esiste canale termico con deriva misurata. Il warm-up NON e' un controllo e non entra in ``bias_w`` ne' in ``evaluate_gate``; le soglie sono pre-registrate sui dati della campagna 20261108 (commento delle costanti nel tool).

- carico-1 (pair-0): completed=True, durata=13.664502 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=11.88187 W, soglia=0.5 W / 18 %, ultimi W=[8.967211, 10.713162, 9.320131, 9.956245], ultimi %=[10.4, 8.6, 9.9, 10.6], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-2 (pair-1): completed=True, durata=18.436297 s, motivo='criterio_soddisfatto', campioni=9, letture mancanti=0, target=12.68444 W, soglia=0.5 W / 18 %, ultimi W=[10.589961, 11.193747, 11.527245, 10.623175], ultimi %=[9.4, 9.6, 9.1, 7.7], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-3 (pair-2): completed=True, durata=20.423588 s, motivo='criterio_soddisfatto', campioni=10, letture mancanti=0, target=12.970362 W, soglia=0.5 W / 18 %, ultimi W=[10.793382, 10.671885, 10.899134, 10.938778], ultimi %=[8.6, 8.0, 11.1, 10.3], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-4 (pair-3): completed=True, durata=36.356153 s, motivo='criterio_soddisfatto', campioni=18, letture mancanti=0, target=10.987674 W, soglia=0.5 W / 18 %, ultimi W=[10.123043, 9.533056, 10.052958, 9.466231], ultimi %=[6.8, 9.2, 12.5, 7.6], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-5 (pair-4): completed=True, durata=12.380264 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=13.714868 W, soglia=0.5 W / 18 %, ultimi W=[9.581694, 9.69778, 9.372416, 10.058715], ultimi %=[6.4, 7.7, 6.9, 8.8], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-6 (pair-5): completed=True, durata=38.408138 s, motivo='criterio_soddisfatto', campioni=19, letture mancanti=0, target=18.435073 W, soglia=0.5 W / 18 %, ultimi W=[10.42974, 10.488043, 11.556178, 10.647282], ultimi %=[12.4, 15.6, 10.3, 12.8], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-7 (pair-6): completed=True, durata=13.278226 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=13.601516 W, soglia=0.5 W / 18 %, ultimi W=[11.090136, 9.856457, 9.650491, 9.773029], ultimi %=[9.8, 8.0, 8.8, 10.5], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-8 (pair-7): completed=True, durata=12.335255 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=12.953381 W, soglia=0.5 W / 18 %, ultimi W=[5.766995, 6.065143, 5.418783, 6.150033], ultimi %=[5.5, 6.6, 6.8, 5.4], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-9 (pair-8): completed=True, durata=13.137511 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=8.047689 W, soglia=0.5 W / 18 %, ultimi W=[4.419267, 4.380208, 4.322737, 4.8515], ultimi %=[6.2, 6.0, 5.7, 6.3], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-10 (pair-9): completed=True, durata=19.495908 s, motivo='criterio_soddisfatto', campioni=9, letture mancanti=0, target=5.754929 W, soglia=0.5 W / 18 %, ultimi W=[3.821374, 3.540093, 3.559674, 3.98463], ultimi %=[1.3, 1.5, 0.9, 1.0], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-11 (pair-10): completed=True, durata=35.08036 s, motivo='criterio_soddisfatto', campioni=17, letture mancanti=0, target=4.798759 W, soglia=0.5 W / 18 %, ultimi W=[4.861644, 3.579547, 3.868793, 3.361759], ultimi %=[2.3, 1.5, 1.2, 0.8], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)
- carico-12 (pair-11): completed=True, durata=13.118199 s, motivo='criterio_soddisfatto', campioni=6, letture mancanti=0, target=4.767294 W, soglia=0.5 W / 18 %, ultimi W=[3.601305, 4.130562, 3.867248, 3.89236], ultimi %=[0.8, 1.2, 0.9, 2.0], temperatura: ingresso=27.85 C (cim:MSAcpi_ThermalZoneTemperature); uscita=27.85 C (cim:MSAcpi_ThermalZoneTemperature)

## Ragioni

- controlli utilizzabili 5 < quorum 8 (ceil(2/3 * 12))
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: |dP|=2.68126 W > 1 W
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: pre_range_w=3.06736 W > 1 W (soglia di pre_unstable, P1.6)
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: pre_range_w=2.67323 W > 1 W (soglia di pre_unstable, P1.6)
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: pre_range_w=2.90545 W > 1 W (soglia di pre_unstable, P1.6)
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: pre_range_w=2.9658 W > 1 W (soglia di pre_unstable, P1.6)
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-7__b01: pre_range_w=4.7301 W > 1 W (soglia di pre_unstable, P1.6)
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-8__b01: pre_range_w=3.59322 W > 1 W (soglia di pre_unstable, P1.6)

## Serie di potenza grezza (diagnostica)

Campioni del sampler nella finestra passiva [t0, t1] del contatore; potenza = delta del contatore cumulativo / delta t fra campioni consecutivi. Diagnostica per distinguere deriva e picchi: non entra nel criterio F.12.

- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-1__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-2__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-3__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-4__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-5__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-6__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-7__b01: 4 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-8__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-9__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-10__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-11__b01: 5 campioni
- hf.co-sigmanih-Qwen-Qwen3-0.6B-GGUF-Q6_K-latest__ctrl-12__b01: 6 campioni

## Artefatti

- results CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261114\casualwatt_v4_results_p44.csv
- block summary CSV: C:\Users\Massimo\Documents\CasualWatt\CWProject\cwEnergyModular\results\p44_gate_20261114\casualwatt_v4_block_summary_p44.csv
- riepiloghi controllo (JSON, forma --blocks): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261114\blocks_controllo.json
- serie di potenza grezza dei controlli (JSON): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261114\control_power_series.json
- registro stabilizzazione post-carico (JSONL, una riga per fase): C:\Users\Massimo\Documents\CasualWatt\CWProject\experiment_results\p44_gate_20261114\warmup_stabilizzazione.jsonl
- run ids: 3bae9697f0634ceaa75a1fd7ebebdc4b, 061e9f82902d4e7b94c4a47994ab8b55, 4dfb22d5226a426ebaeef616305eb881, f9a164ad165448ce9587043af3b5fdbc, a84f985bf6a04b3fb9622a71cc36de0e, c281ec5b26624b9f84da9d5e131ff58a, 3fc31863238a4bea9f9dd198cd24d9ee, 8b34b589da3d4def927c9bf455251dd6, 93c1830ff00c4349b5d02404fd85501a, d30e4e5573174ac5a38f6ea8215a71ae, a91f1c3c6b634611bb4d83df67fcc0d6, cab2b58c40c64e28b32fd00782934bce, 70c9320f979d4198a8d86c0a29c4ee67, 6be0459d7eb9478f8c7b4afa4bd61a25, 9820a2d3d82b437fa50529fe491f9bb0, fd7c8a14792f4e5e8daaf76a690a96f0, 25a3fd6935784234a04b8522099af9a5, d61eba4d90d2457e93b3e3e3aa3ed20f, e5b1118595654703bbb583014d820d52, cbc9fa837a5c4ba4b5f97fd4b125db57, 69a36cabd6ad471ea89e4c7ad97a9b03, 8bca3b12e51f4fa7ae158f0a75d4ae6e, cc90a27c607145deb0cabbe55c005ab6, 054f0e01bd2e4886904919a4e7625258
- git head: 8a1aaf13812bb84dcf1f053af4c9a45aad66725e
- runner sha256: 6f3bad16859c92ec9f9401605b1a367368978ed3d2fc3cb5885f3384e3d0288c
