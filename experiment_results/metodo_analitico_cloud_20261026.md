# Metodo analitico cloud calibrato (livello C5) — specifica di disegno

Data: **26-10-2026**. Documento di disegno, non implementazione: il codice sorgente di
produzione resta bloccato fino al congelamento di P5 (AGENTS.md, "Stato corrente del
lavoro"). Tutto cio' che qui richiede codice e' un **delta per il coder di P5**.

Decisione di riferimento: **DT-5** (`Tesi-latex/qoder-bozza/DECISIONI.md`, sezione
"Decisione cloud DT-5 (26/10/2026)"): "modello analitico ispirato a SweetSpot come
fallback calibrato su ML.ENERGY e letteratura, energia di rete come contributo
separato, incertezza quantificata e provenienza esplicita per ogni numero".

Questo documento **supera** `metodi_per_dominio_20261025_spec.md:667-672` **solo** per
il dominio cloud: li il modello `kappa*n_in/n_out` era escluso dalla catena. Per il
dominio locale la postura X2/D10 (righe 221, 313-323, 865) resta immutata: stima
opt-in, campo proprio, mai a confronto con una misura. La differenza fra i due domini
non e' una contraddizione: locale esiste un contatore, cloud no, quindi li l'alternativa
a "unavailable" era inventare una misura, qui e' dichiarare una classe di stima in piu'.

Letture di supporto: `experiment_results/valutazione_20261026_progetto_cloud.md` (la
verifica claim per claim della proposta da cui DT-5 nasce) e
`experiment_results/valutazione_20261026_cloud2_docx.md` (la verifica della seconda
definizione di metodo, 26-10-2026: da essa vengono le adozioni A1 -- forma per fasi, §2.2
-- e A2 -- regola `N_active` per MoE, §2.3).

---

## 1. La catena cloud aggiornata

`C1 -> C2 -> C4 -> C3 -> C5 -> unavailable`

| id | interfaccia | natura | confine | etichetta `cloud_energy_method` | stato |
|---|---|---|---|---|---|
| C1 | telemetria energetica del provider | misura remota | server del provider | `provider-telemetry` | [A] non esiste fonte nel repo |
| C2 | EcoLogits `llm_impacts`, modello registrato | stima | server-side datacenter (usage + PUE) | `ecologits` | [I] |
| C4 | EcoLogits `compute_llm_impacts` con parametri attivi reali e fonte | stima | come C2, sul modello richiesto | `ecologits-params` | [P] non implementato |
| C3 | EcoLogits con proxy di pari classe | stima | come C2, su modello diverso da quello richiesto | `ecologits-proxy` (D3) | [I] **ma irraggiungibile**, vedi §7 |
| **C5** | **modello analitico per classe, coefficienti con provenienza dichiarata** | **stima con boundary dichiarato** | **acceleratore di riferimento (H100), serving open-source, steady state; NON il hardware del provider** | **`analytic-class-fit` + token di calibrazione (§4)** | **[P] non implementato** |
| T1/T2 | rete: delta contatori NIC / payload HTTP x coefficiente J/bit | stima, scala propria | byte system-wide del client x percorso trasmissione+commutazione fino al data center, accesso escluso (D13) | campo `network_*`, **mai sommato a C-series in una colonna unica** | [I] |

C5 sta **dopo** C3 perche' il motore di stima nativo, anche su un gemello dichiarato,
resta piu' ancorato del nostro fit: ha una regressione pubblicata su una fonte che
abbiamo verificato (`docs/methodology/llm_inference.md` di mlco2/ecologits, 26-10-2026).
La regola dei repo si applica invariata: nessun fallback silenzioso, e **mai presentare
un fallback come un contatore** (AGENTS.md, "Metodologia congelata").

---

## 2. Forma dell'estimatore C5

### 2.0 Il riferimento: la forma di C2, ricalcolata a mano (verifica 26-10-2026)

C5 deve essere confrontabile con C2, quindi la forma di C2 va scritta **esatta**. Non
l'ho letta: l'ho ricalcolata e confrontata con l'uscita del motore. Sonda tracciata
`probe_ecologits_gpu_steps_moe_20261026.py` (output
`experiment_results/probe_ecologits_gpu_steps_moe_console_20261026.txt`). Alla prima
stesura, qui erano citate due invocazioni inline senza file: sostituite dalla sonda, per
le ragioni dette nel paragrafo "Ancoraggio della misura" in fondo a questa sezione.

```
f_E(P_active, B) = alpha * exp(beta * B) * P_active + gamma        # Wh/token
                     (impacts/llm.py:59)
E_gpu  = n_out * f_E(P_active, B) / 1000                            # kWh,  :61-62
E_server = (gen_latency / 3600) * 1,2 kW * (gpus_required / 8) * (1 / B)   # :163
E_it     = E_server + gpus_required * E_gpu                          # :201
E_request = PUE * E_it                                               # :181
```

Costanti installate (verificate stampandole): `alpha = 1,1665273170451914e-06`,
`beta = -0,011205921025579175`, `gamma = 4,052928146734005e-05` (`impacts/llm.py:10-12`),
`BATCH_SIZE = 64` (`:31`), `SERVER_POWER = 1,2` kW (`:24`), `SERVER_GPUS = 8` (`:23`),
`GPU_MEMORY = 80` GB (`:18` -- non `:9`: la sonda ricontrolla ogni numero di riga citato
in questo documento e questo era l'unico fuori di nove), `MODEL_QUANTIZATION_BITS = 16`
(`:8`).

| caso | ricalcolo a mano | `llm_impacts` | scarto relativo |
|---|---|---|---|
| `openai/gpt-4o-mini`, 100 tok, 1,0 s, bordo min (P=8B) | 6,191401e-06 kWh | 6,19140110767128e-06 | **0,00e+00** |
| stesso, bordo max (P=28B) | 7,557994e-06 kWh | 7,557994436647469e-06 | **0,00e+00** |
| `huggingface_hub/meta-llama/Meta-Llama-3.1-70B-Instruct`, 200 tok, 2,0 s | 7,60487313e-05 kWh | 7,60487313e-05 (min del range) | **0,00e+00** |

**Correzione 1 alla proposta — manca il moltiplicatore `gpus_required`.** La proposta
scrive `E_GPU = T_out x f_E(P_active, 64)` e `E_request = PUE x (E_server + E_GPU)`:
il codice moltiplica il termine GPU per il numero di GPU richieste (`impacts/llm.py:201`).
Sul 70B `gpus_required = 4` (memoria `1,2 * 70,55 * 16 / 8 = 169,3` GB su GPU da 80 GB,
`:120`, `:138-139` con arrotondamento alla potenza di 2): la formula della proposta
darebbe 2,327e-05 contro 7,605e-05 reali, **fattore 3,268**. L'errore non si vede su
gpt-4o-mini perche' li `gpus_required = 1`. Il numero di GPU e' una **funzione a gradini**
della classe di modello, non una continuita': 12,9B -> 1 GPU, 46,7B -> 2, 70B -> 4,
123B -> 4, 405B -> 16.

**Correzione 2 — e rovesciamento di una nostra dichiarazione: la `gen_latency` e' un
`min`, non la nostra misura.** `impacts/llm.py:99-102`:
`gen_latency = min(request_latency, n_out * lat_per_token + ttft)`, con
`lat_per_token = 1/tps` quando `tps` e' passato (`:96-97`). Esecuzione sopra
`openai/gpt-4o-mini` (tps registrato 33 -> stima interna 100/33 + 0,6 = 3,6303 s), 100
token, latenza fatta variare:

| latenza misurata | `energy.min` [kWh] | delta sulla 200 ms | `energy` media [kWh] | delta sulla 200 ms |
|---|---|---|---|---|
| 0,2 s | 5,56640111e-06 | 0,000% | 6,249697772159e-06 | 0,000% |
| 1,0 s | 6,19140111e-06 | +11,228% | 6,874697772159e-06 | +10,000% |
| 3,6 s | 8,22265111e-06 | +47,719% | 8,905947772159e-06 | +42,502% |
| 3,7 s | 8,24632535e-06 | +48,145% | 8,929622014584e-06 | +42,881% |
| 5,0 s | 8,24632535e-06 | +48,145% | 8,929622014584e-06 | +42,881% |
| 10,0 s | 8,24632535e-06 | +48,145% | 8,929622014584e-06 | +42,881% |
| 30,0 s | 8,24632535e-06 | +48,145% | 8,929622014584e-06 | +42,881% |
| 120,0 s | 8,24632535e-06 | +48,145% | 8,929622014584e-06 | +42,881% |

La colonna `min` e' quella che circolava in una stesura precedente di questo
documento: era il **minimo della banda**, non il valore che pubblichiamo (che e' la
media, `cloud_energy.py:94` e `:172`). La tabella ora riporta entrambe, perche' la
soglia di appiattimento e' la stessa per le due colonne ma i delta non lo sono.

**Ancoraggio della misura (dichiarazione di provenienza, aggiornata 26-10-2026).** Le
righe di questa tabella con `output_token_count = 100` sono riproducibili dalla sonda
tracciata `probe_ecologits_clamp_20261026.py` (output
`experiment_results/ecologits_clamp_console_20261026.txt`, che copre 32 / 100 / 200
token). Tutto il resto -- le formule di `impacts/llm.py`, i gradini di
`gpu_required_count`, il fattore 3,268 del 70B, la griglia MoE di §2.3 -- viene dalla
sonda tracciata `probe_ecologits_gpu_steps_moe_20261026.py` (output
`experiment_results/probe_ecologits_gpu_steps_moe_console_20261026.txt`), che alla prima
stesura di questo documento era un'invocazione inline senza file, come dichiarato qui
sopra. La sonda (a) ricontrolla riga per riga ogni ancoraggio citato in questo file:
`impacts/llm.py:59/100/120/139/163/181/201` e `tracers/utils.py:89` tornano tutti,
mentre `GPU_MEMORY` era citato `:9` ed e' `:18`, e la citazione va corretta -- la sonda
stampa anche le righe di `data/models.json` della scheda MoE, che invece tornano (136,
139-140, 146-149); (b) ricostruisce le formule e le confronta con l'uscita di
`llm_impacts` reale: scarto relativo `0,00e+00` sul 70B (`7,604873134005532e-05` kWh) e
sul MoE (`2,985238380999223e-04` kWh, vedi §2.3); (c) mette in audit i numeri citati
dal documento piu' i numeri della rettifica di §2.3 -- **25 righe, 25 rigenerate**, dove
l'ultima riga dell'audit non e' piu' il claim "11,17" contro la geometria dichiarata (che
non si rigenerava) ma la sua **origine**: il rapporto `D/A` fra la brana a 8 bit e quella
a 16 bit, che infatti rigenera 11,1740. La sonda registra inoltre il conteggio che ha
rovesciato il capitolo: `tps` non nullo su 157 schede su 344, e la soglia a regressione
del 70B (17,4612 s a 200 token). Da qui in poi i numeri di questo file sono rigenerabili
da artefatti del repository (task #122 chiuso, commit `679eaee`). Con lo stesso criterio
e' stato rieseguito e rigenerato anche l'output della sonda dei clamp,
`experiment_results/ecologits_clamp_console_20261026.txt`, che alla seconda riga ora
riporta entrambi i conteggi (`344 con deployment, 157 con tps non nullo`); i numeri di
plateau gia' misurati in quel file non cambiano, perche' `gpt-4o-mini` e' una delle 157
con `tps`.

Sopra la latenza stimata dal motore la nostra misura **smette di entrare**: il numero
si piatta. Quindi la Nota B4 di `cloud_energy.py` (testo originale: "request_latency
MISURATA end-to-end: include la latenza di rete, non solo il tempo server-side"), la
sua ripetizione in `metodi_per_dominio_20261025_spec.md` ("la stima server-side ne
risulta lievemente **sovrastimata**") e la paraphrase in `cap03_metodologia_misura.tex`
("latenza (rete inclusa) dentro il tempo fatturato -- con sovrastima dell'attesa")
avevano il **segno sbagliato nel regime di risposta lenta**: li la rete non sovrastima,
perche' la misura viene **sostituita in silenzio** dalla stima del modello. Il rischio
reale e' opposto e piu' grave per la tesi: su un provider lento la riga dichiara una
latenza misurata che **non ha influito sul numero**, e la stima risulta **insensibile**
alla lentezza — sottostima, non sovrastima.
**Stato 26-10-2026: i tre testi sono corretti** (nota del codice
`cloud_energy.py:196-219` e intestazione `:21-46`, spec §6 `:630-660`, cap03 §"Tre
limiti di C2"), e la correzione porta con se' il campo proposto `cloud_latency_used_s`
piu' `cloud_latency_threshold_s` e `cloud_latency_binding` (§4: la riga deve portare
la latenza **effective**, la soglia che l'ha troncata, e quale termine ha vincolato).

Conseguenza per C5: la forma di C5 **non** puo' ereditare il `min`. Se il nostro
fallback usa la latenza misurata linearmente e C2 la tronca, le due stime divergono
per ragioni di struttura e non di calibrazione, e il confronto G3 sarebbe viziato.
C5 usa la latenza misurata **con il truncamento dichiarato come scelta**, oppure lo
stesso `min` di C2: la scelta va scritta, non ereditata per caso.

### 2.1 La forma proposta per C5

**Dichiarazione vincolante (correzione 3.2, deliberata 26-10-2026).** C5 **non replica
SweetSpot**: ne usa la *struttura dei termini* pubblicata come scheletro e stima
**coefficienti propri, per classe di modello**, su una fonte e dentro un boundary che
non sono quelli degli autori. Nessun numero di C5 va attribuito a Cavagna et al.; nessun
`theta` pubblicato va usato come nostro coefficiente senza l'etichetta
`fit-published-transcribed` (§3). Questa frase va scritta nel testo della tesi, non solo
intesa.

Struttura verificata alla fonte primaria (arXiv:2602.05695v2, versione HTML, consultata
26-10-2026):

| eq. | forma pubblicata | termini |
|---|---|---|
| Eq. 4 | `E_tok = theta0 + theta1*n_in^2/n_out + theta2*n_in + theta3*n_in/n_out + theta4*n_out` | 5 |
| Eq. 5 | Eq. 4 `+ theta5/n_out` | 6 |
| Eq. 6 | definizione dello sweet spot `n_out*` | -- |

Quindi la forma a sei termini che circola etichettata "Eq. 4--5" **e' l'Eq. 5**, non
l'Eq. 4: il termine `theta5/n_out` compare solo nell'Eq. 5. I `theta` sono fitted **per
singolo modello** (Tabella 5), con MAPE medio **1,79%** --- entrambi confermati alla
fonte primaria il 26-10-2026. Sono dunque coefficienti di *modello*, non di *classe*:
trascriverli come coefficienti di classe sarebbe la stessa fallacia che la correzione 3.2
vieta.

Si adotta la **struttura dei termini** dell'Eq. 4 (DOI 10.1145/3777884.3797011, chiave
`cavagna2026sweetspot`, `references.bib:71-78`) e si fittano **coefficienti nostri
indicizzati per classe di modello**:

```
E_cloud^C5 [J] = PUE_assunto * [
      k_over(N)   * 1              # overhead per richiesta       [J]
    + k_pre(N)    * n_in           # prefill, lineare in input    [J/token]
    + k_dec(N)    * n_out          # decode, lineare in output    [J/token]
    + k_attn(N)   * n_in^2 / n_out # attenzione, ammortizzata     [J/token]
    + k_ratio(N)  * n_in / n_out   # rapporto input/output        [J]
  ( + k_tail(N)  / n_out )         # termine dell'Eq. 5, opzionale [J*token]
]
```

Correzione a questa stessa sezione nella sua prima stesura: la forma che avevo scritto
aveva **quattro** termini e dichiarava di adottarne cinque, e assegnava a `k_attn`
l'unita' `[J/token^2]`, che e' sbagliata perche' `n_in^2/n_out` si esprime in token, non
in token quadrati. I cinque termini dell'Eq. 4 stanno ora uno a uno (overhead, prefill,
decode, attenzione, rapporto) e le unita' sono quelle in commento. Il sesto termine,
`k_tail/n_out`, viene dall'Eq. 5 ed entra **solo se** il fit della classe lo richiede:
quale set di termini e' usato va registrato per classe (`cloud_fit_terms`), perche' due
classi fittate su set diversi non sono confrontabili.

Due vincoli geometrici che la struttura eredita e che vanno dichiarati: i termini con
`/n_out` esplodono per `n_out -> 0` (in produzione il conteggio e' gia' troncato a 1,
`cloud_energy.py:136`), e l'intervallo di validita' della forma pubblicata e' 64--4096
token (DT-4). Sono i due casi in cui `cloud_calibration_validity = "extrapolation"`
scatta per costruzione (§5, punto 3).

La scala di `N` (parametri attivi del modello richiesto) e' lineare in `N` moltiplicata
per una potenza `N^b` con `b` **non libero**: ancorato a `b ~ 0,46` gia' adottato in
DT-3 (`DECISIONI.md:268-280`) su TokenPowerBench (arXiv:2512.03024, verificato
esistente e pubblico il 26-10-2026: `github.com/chenxuniu/TokenPowerBench`, J/token e
split prefill/decode, 1B-405B).

Tre cose che questa forma **non** fa, e vanno dette perche' sono le tre obiezioni
facili in sede di discussione:

1. **Non e' la formula di Cavagna et al.** I loro `theta` sono per singolo modello,
   fitted su 1B-9B, H100, TensorRT-LLM, 64-4096 token (verifica alla fonte primaria
   26-10-2026, sopra). Noi usiamo i loro termini come *struttura* e stimiamo
   coefficienti per classe. Il divieto del `cloud.DOCX` — "non bisogna
   attribuire agli autori formule semplificate che non corrispondono al loro modello
   pubblicato" — e' rispettato da questa distinzione, che va scritta nel testo e non
   solo pensata.
2. **Non include il PUE del provider.** Il `PUE_assunto` e' un parametro dichiarato con
   la sua fonte. Il precedente utile esiste gia': in C2 il PUE **non** e' nostro, e'
   quello del provider registrato (1,09-1,20, `ecologits/tracers/utils.py:146-177`,
   registrato in `DECISIONI.md:246-252`). Per C5, dove il provider e' per definizione
   non noto, il numero va accompagnato dal range 1,09-1,20 come banda di assunzione
   separata (§5).
3. **Non e' l'energia del provider.** E' un **costo di riferimento** alle condizioni di
   riferimento del dataset di calibrazione (H100, serving open-source, batch saturato,
   steady state). La differenza fra "energia consumata da quel provider per quella
   richiesta" e "energia che quel lavoro costa su un acceleratore di riferimento" e'
   esattamente la distinzione che il progetto gia' usa per i fattori di conversione:
   la clausola di DT-4 sull'estrapolazione di SweetSpot (1B-9B, H100, TensorRT-LLM,
   64-4096 token) va ripetuta per ogni classe estesa fuori da quell'intervallo.

### 2.2 La stessa forma scritta per fasi di servizio (adozione da `cloud2.DOCX`)

L'algebra del punto 2.1 non cambia; cambia il **raggruppamento**, che pero' rende
visibile l'unica asimmetria strutturale fra C5 e C2. Riprendendo la notazione per fasi
di `cloud2.DOCX` (valutata in
`experiment_results/valutazione_20261026_cloud2_docx.md`, guadagno A1):

```
E_cloud^C5 = PUE_assunto * ( E_overhead + E_prefill + E_decode )

E_overhead = k_over(N) * 1
E_prefill  = k_pre(N)  * n_in  +  k_attn(N) * n_in^2/n_out  +  k_ratio(N) * n_in/n_out
E_decode   = k_dec(N)  * n_out        ( + k_tail(N)/n_out, se il fit usa l'Eq. 5 )
```

Il motivo per cui vale la pena scriverla cosi', e non e' una scelta di stile:
**per C2 il termine di prefill e' identicamente nullo.** `llm_impacts` non riceve gli
input token (correzione 3.3, `cloud_energy.py:159-166`), quindi la sua stima e'
`E_decode`-only per costruzione. La conseguenza 3.3 del gate G3 -- "C5 sta sopra per
costruzione, non per calibrazione" -- diventa un'affermazione algebrica:

```
E_cloud^C5 - E_cloud^C2 = PUE * ( E_prefill + E_overhead ) + (differenza di calibrazione)
```

e il primo termine si puo' calcolare e sottrarre **prima** di parlare di scarto fra i
due metodi. Con le geometrie reali del progetto (`N_in 12,3` / `N_out 31,8`,
`idee_implementative_20261024.md:69`) gli input token sono il **27,9% del totale** dei
token della richiesta (12,3 su 44,1): il prefill non e' una correzione marginale, e'
circa un terzo del lavoro che la riga dichiara di aver stimato.

Da `cloud2.DOCX` non si prende invece la sua forma esplicita
`E_prefill = n_in*alpha(N_active) + gamma*n_in^2/n_out`, perche' riusa `alpha` e
`gamma` come nomi: sono esattamente i simboli dei coefficienti della regressione di
ML.ENERGY (`GPU_ENERGY_ALPHA/BETA/GAMMA`, `impacts/llm.py:10-12`), e darle un significato
diverso nella stessa tesi e' una collisione di notazione che il relatore puo' legittimamente
contestare. I nostri coefficienti restano `k_*`.

### 2.3 `N_active` per modelli MoE (regola nostra, motore verificato)

La proposta di `cloud2.DOCX` (`N_active = N_total / E_tot * E_act`, rapporto fra esperti
attivi e totali) descrive una cosa che **il motore gia' fa, ma solo quando il registro
gliela fornisce** -- e la verifica eseguita sposta il caso: il registro gliela fornisce
quasi sempre (86 schede MoE su 87), mentre cio' che le sfugge non e' l'assenza del dato,
e' il **formato** di una scheda. Verificato nel pacchetto installato:

- `tracers/utils.py:89-94`: se `architecture.parameters` e' un `ParametersMoE` allora
  `active = parameters.active`, altrimenti `active = parameters` (**l'active coincide
  con il totale**). Non c'e' alcuna stima da rapporto di esperti: e' un campo dichiarato.
- `data/models.json`: **87 schede su 344** sono `type: moe`, e **86** dichiarano gli
  attivi *dentro* l'oggetto `parameters` -- `huggingface_hub/mistralai/Mixtral-8x7B-v0.1`
  ha `"parameters": {"total": 46.7, "active": 12.9}` -- quindi il parser le converte in
  `ParametersMoE` e il motore usa l'attivo giusto. **Una** scheda usa la forma diversa,
  e la sonda la nomina: `cohere/command-a-plus-05-2026` ha `"parameters": 218` a
  `data/models.json:139` e `"active_parameters": 25` a `:140` (nome a `:136`, i quattro
  URL di fonte a `:146-149`). Il parser non conosce quella chiave sorella: consegna
  `parameters` come `int` 218, il ramo `isinstance(..., ParametersMoE)` di
  `tracers/utils.py:89` **non scatta**, e l'attivo collassa sul totale dichiarato.
  Verificato eseguendo (sonda, sezione G): `llm_impacts` su quella scheda, 200 token in
  2,0 s, restituisce `2,985238380999223e-04` kWh, che e' **esattamente** `PUE 1,09` per
  la brana C della tabella qui sotto, scarto relativo `0,00e+00`.

Quindi la clausola A2 di `cloud2.DOCX` non descrive un'assenza del registro sui MoE --
che per 86 schede su 87 c'e' -- descrive il **formato** di una scheda. E' comunque il
caso giusto da quantificare, perche' e' quello che il motore fa oggi. Griglia della sonda
(`n_out = 200`, `request_latency = 2,0` s, `tps`/`ttft` dalla scheda, `batch = 64`, PUE
escluso perche' i rapporti sono su `E_it`; la latenza generata e' 2,0 s in tutte e
quattro le brane, quindi non e' lei a muovere i rapporti):

| brana | `P_active` | `P_total` | bit | GPU | `E_gpu` [kWh] | `E_it` [kWh] |
|---|---|---|---|---|---|---|
| A -- proxy denso da 25B | 25 | 25 | 16 | 1 | `1,095293e-05` | `1,225501e-05` |
| B -- MoE governato (come il registro lo intende) | 25 | 218 | 16 | 8 | `1,095293e-05` | `9,804007e-05` |
| C -- MoE trattato da denso (**brana del motore oggi**) | 218 | 218 | 16 | 8 | `3,293230e-05` | `2,738751e-04` |
| D -- come C, ma a 8 bit | 218 | 218 | 8 | 4 | `3,293230e-05` | `1,369375e-04` |

- **sola etichetta MoE** (B -> C: stessa scheda, stessi gradini, cambia solo l'attivo):
  `f_E` sale da `5,476463e-05` a `1,646615e-04` Wh/token -- **fattore 3,0067**, non 8,72
  perche' l'offset `gamma` ammortizza -- e `E_it` sale di **2,7935**;
- **solo il gradino** (A -> B: etichetta corretta in entrambe, cambia la classe del
  proxy): da `1,2*25*16/8 = 60` GB (1 GPU) a `1,2*218*16/8 = 523,2` GB (8 GPU),
  fattore **esattamente 8,0000**;
- **le due cose insieme** (A -> C): `E_it` passa da `1,225501e-05` a `2,738751e-04` --
  **fattore 22,348**.

**Rettifica (26-10-2026, sonda tracciata; era scritta come «fattore 11,17»).** La prima
stesura di questa sezione confrontava `1,225501e-05` con `1,369375e-04` e ne cavava un
fattore 11,17 presentato come il costo dell'etichetta MoE sbagliata. `1,369375e-04` e' la
brana **D**, cioe' `gpu_required_count = 4`, che su un 218B esce **solo a 8 bit**
(`1,2*218*8/8 = 261,6` GB). Il confronto quindi mescolava due quantizzazioni: 11,17 =
4/1 x 2,7935. Il pacchetto fissa `MODEL_QUANTIZATION_BITS = 16` (`impacts/llm.py:8`) e
nessuno puo' passarla a `llm_impacts`, quindi alla geometria dichiarata i numeri giusti
sono **22,348** (A -> C) e **2,7935** (B -> C), e il gradino 1 -> 8 va citato come
**8,0000** e non come un fattore 11,17. Un errore di questa forma non e' una finezza di
calibrazione, e' il numero sbagliato -- qui sbagliava anche la nostra rettifica.

Regola adottata per C5 (e per C4, dove il modello richiesto non e' registrato):

1. se il modello e' registrato e la scheda dichiara gli attivi, si usa **quella** cifra
   con la sua fonte e con `cloud_moe_active_assumption = registry-declared`; **non** e'
   un coefficiente del fit, quindi non passa dalla scala P1-P4 di §3: e' un dato di
   architettura dichiarato dal produttore, e come tale va etichettato. La fonte puo'
   avere due forme, e la distinzione ora ha una conseguenza operativa: l'oggetto
   `parameters: {total, active}` (86 schede) il motore la legge da solo, la chiave legacy
   `active_parameters` (1 scheda, `command-a-plus-05-2026`, con i suoi quattro URL di
   fonte a `data/models.json:146-149`) il motore la **ignora**. Quindi per quella scheda
   C4 non e' un'opzione di precisione: e' l'unico modo di pubblicare il numero che il
   produttore dichiara, invece dei `2,985238380999e-04` kWh che oggi escono da C2 e che
   sono 2,7935 volte quel numero;
2. altrimenti, per un MoE, `N_active = N_total * (E_act / E_tot)` con `E_act`/`E_tot`
   presi dal **config del modello**. I campi che servono sono quelli che i config MoE su
   Hugging Face espongono (`num_experts` e `num_experts_per_tok` per Mixtral e famiglia
   Qwen-MoE) -- **non l'ho verificato oggi su un config specifico**: prima di usarli in
   C4/C5 vanno letti sul modello reale e riportati in riga, perche' il loro nome cambia
   fra famiglie;
3. la regola vale solo a **esperti uniformi**: se gli esperti hanno dimensioni diverse il
   rapporto non e' corretto (i parametri attivi non sono `N_total * E_act/E_tot`), e il
   caso va marcato `cloud_moe_active_assumption = "uniform-experts"`;
4. dense: `N_active = N_total`, **esplicitato in riga**, non come fallback silenzioso --
   perche' e' esattamente il comportamento del motore che stiamo ereditando
   (`tracers/utils.py:93-94`), e AGENTS.md vieta di presentare un fallback come una
   lettura.

Nota di scala: in `models.json` il numero e' in **miliardi di parametri** (218, 25), e
`f_E` lo consuma cosi' com'e'; `cloud_energy.py` non fa conversioni. Chi scrive il fit
deve tenere la stessa unita' o dichiararla (`N_active` in B di parametri, non in
conteggi assoluti).

---

## 3. Cosa rende un numero "calibrato", e cosa no

Quattro livelli di provenienza dei coefficienti, e **solo il primo autorizza la parola
"calibrato"**.

| livello | come nasce il coefficiente | etichetta | si puo' chiamare calibrato? |
|---|---|---|---|
| P1 | fit eseguito da noi su dati grezzi (serie di energia/timestamp), con hold-out | `fit-raw-holdout` | **si'** |
| P2 | fit eseguito da altri, noi trascriviamo i coefficienti pubblicati con boundary e versione | `fit-published-transcribed` | no: "coefficiente pubblicato da [fonte]" |
| P3 | valore di ordine di grandezza preso da letteratura con boundary diverso dal nostro | `value-adopted` | no: "valore adottato, boundary non confrontabile" |
| P4 | nessun ancoraggio trovato dopo la ricerca di fonte | `hypothesis` | mai; e' un'ipotesi dichiarata |

Nota di riclassificazione (26-10-2026): `eps_bit` **non e' piu' un caso P4**. Il
valore `2,7e-6 J/bit` e' stato verificato alla fonte primaria (Baliga, Ayre,
Hinton, Tucker, *Proc. IEEE* 99(1):149-167, 2011, DOI
10.1109/JPROC.2010.2060451) e ricade in P3 `value-adopted`: valore preso da
letteratura con un confine diverso dal nostro (la fonte esclude la rete di
accesso, i nostri byte sono system-wide sul client). Resta quindi non
confrontabile con le cifre "per GB" di percorso completo, e resta non validato.

Stato reale dei tre input che DT-5 nomina, verificato 26-10-2026:

- **ML.ENERGY**: i J/token steady state esistono e sono la fonte del fit di EcoLogits
  (Chung et al., arXiv:2505.06371, NeurIPS 2025 D&B — **non** 2410.12032/MLPerf Power,
  che riporta J/campione con strumentazione esterna). Il dataset grezzo e' HF
  `ml-energy/benchmark-v3`, Apache-2.0, **gated**, campo `energy_per_token_joules`.
  **Su questo host non c'e' token Hugging Face** (`huggingface_hub.whoami()` ->
  `LocalTokenNotFoundError`, 26-10-2026). Quindi oggi P1 non e' eseguibile; si puo'
  partire solo da P2 (tabelle del paper).
- **SweetSpot**: `theta0..theta5` per modello, pubblicati. Loro uso corretto e' come
  **controllo di forma**: se il nostro C5 e la loro Eq. 4 sullo stesso modello danno
  numeri dello stesso ordine, la struttura regge; se divergono, e' un dato da riportare,
  non da normalizzare — la regola esiste gia' per il cross-confronto C2/C4
  (spec §6 righe 705-706: "lo scarto fra i due non si corregge con un fattore
  inventato").
- **Letteratura** (TokenPowerBench per lo scaling, Jovanovic/LLMCarbon come *stimatori*
  concorrenti non come misura): alimenta P3 e il vincolo di monotonia, non P1.

**Il test di accettazione di una calibrazione**, senza il quale C5 non entra: **leave-
one-model-out per classe**. Un fit che tiene fuori *punti* dello stesso modello misura
interpolazione; tenere fuori *modelli interi* e' l'unica prova che il coefficiente di
classe generalizza, che e' precisamente l'affermazione che C5 fa quando il modello
richiesto non e' nel registro. Si riporta il `loo_mape` per classe insieme ai coefficienti.

---

## 4. Provenienza esplicita per ogni numero

La richiesta di DT-5 si traduce in campi, non in aggettivi. Ogni riga cloud porta:

| campo | contenuto | esiste oggi |
|---|---|---|
| `cloud_energy_method` | token di catena: `ecologits` / `ecologits-params` / `ecologits-proxy` / `analytic-class-fit` / `provider-telemetry` / `unavailable` | si' (D3 chiede di separare il proxy, oggi assente: C2 e C3 condividono l'etichetta, spec §6 righe 663-665) |
| `cloud_coefficient_provenance` | uno fra `fit-raw-holdout`, `fit-published-transcribed`, `value-adopted`, `hypothesis` | no, nuovo |
| `cloud_calibration_source` | fonte dei coefficienti con identificatore persistente (DOI/arXiv), versione del dataset, data della verifica | no, nuovo |
| `cloud_fit_loo_mape` | errore leave-one-model-out della classe usata | no, nuovo |
| `cloud_fit_terms` | quali termini della forma (§2.1) sono attivi nel fit di quella classe (`eq4` a 5 termini, `eq5` a 6) | no, nuovo |
| `cloud_moe_active_assumption` | come e' ottenuto `N_active` per quella riga: `registry-declared` / `uniform-experts` / `dense` (esplicitato) / `unknown`. Vede §2.3: il motore usa `active = total` **senza dirlo** ogni volta che la scheda non e' un `ParametersMoE` -- dense, e la chiave legacy `active_parameters`, non i MoE in generale (`tracers/utils.py:89-94`, contato dalla sonda: 86 MoE su 87 portano gia' l'attivo) | no, nuovo |
| `cloud_active_parameters_b` / `cloud_total_parameters_b` | i due numeri usati, in **miliardi** come nel registro (`models.json`), con la fonte | no, nuovo |
| `ecologits_version`, `cloud_calls_count`, `cloud_hardware_mismatch`, `cloud_quantization_assumed` | gia' deliberati in D12 (riga 867) | no |
| **`cloud_input_tokens_included`** | booleano **obbligatorio per riga** (correzione 3.3, 26-10-2026). Valore: **`false` per C2, C3 e C4** --- `llm_impacts` accetta solo `output_token_count` e `request_latency`, nessun argomento di input (verificato eseguendo la chiamata, 26-10-2026; nota B4 in `cloud_energy.py:159-166`). Valore: **`true` per C5**, perche' `k_pre*n_in` e `k_attn*n_in^2/n_out` sono termini espliciti della forma. Il campo non e' decorativo: i token di input restano contati e salvati (`cloud_input_tokens`) e la riga dichiara quale perimetro hanno | no, nuovo (D12 lo chiede dal 25-10, non implementato) |
| `cloud_latency_used_s` | latenza **effective** entrata nel calcolo, diversa da `duration_s` misurata quando il `min` di `impacts/llm.py:99-102` ha tronciato (§2.0, correzione 2) | no, nuovo |
| `cloud_measurement_boundary` | testo fisso: "acceleratore di riferimento H100, serving open-source, steady state; non il hardware del provider" per C5; "server-side datacenter usage+PUE, esclude rete/client/embodied" per C2-C4 | no |
| **`cloud_energy_band_semantics`** | etichetta del significato della banda min/max della riga: **`parameter_pue_ignorance_range`** per C2-C4 (correzione 3.4, §5 punto 2), **`calibration-semi-range`** per C5, **`assumption-band`** per le bande di contorno. Nessuna riga puo' avere una colonna min/max senza questo campo | no, nuovo |
| `energy_available` | booleano: `false` quando il numero non c'e', con `cloud_unavailable_reason` dal lessico di §4.1 | no, nuovo |

**Conseguenza della correzione 3.3 sul gate G3, da scrivere insieme al gate.** C5
include il prefill e C2 lo esclude. Sulle geometrie reali del progetto --- `N_in 12,3` e
`N_out 31,8` per richiesta, e il fatto che il J/token di produzione sia "di fatto un
costo di decode" (`idee_implementative_20261024.md:69`) --- lo scarto C5 contro C2 non
e' confrontabile come "accordo fra due stime dello stesso lavoro". Il prefill escluso da
C2 e' una **sottostima strutturale** (spec §6 righe 614-618), quindi su prompt lunghi C5
sta sopra per costruzione, non per calibrazione. G3 va eseguito dichiarando l'asimmetria,
e la correzione, se necessaria, non e' un fattore inventato: o si confronta solo il
decode, o si riporta lo scarto grezzo. E' la stessa regola gia' scritta per il
cross-confronto C2/C4 (righe 232-234 sopra) e per "confrontare non significa adottare"
(AGENTS.md).

Regola di combinazione dei domini, che DT-5 fissa come "energia di rete come contributo
separato": `cloud_energy_j` e `network_energy_j` restano **colonne separate** (spec §7,
D13) e la loro somma esiste solo come **metrica derivata con il proprio nome e il
proprio boundary** (per esempio `attivo_energy_j = cloud + network`, etichetta
`derived-sum`), mai come rimpiazzo di una delle due. Il motivo non e' formale: sono due
stime con scale e confini diversi — una con PUE di provider ignoto, l'altra con un
coefficiente J/bit che non ha fonte primaria (D8, F7 riga 844).

Regola dello zero: `energy_available = false` non produce `0.0`. Questo e' **oggi
violato** in due punti e va chiuso come prerequisito (F2 `benchmark_unified.py:1101`
`est.energy_j or 0.0`; F9 `:466-476` local mode con metodo vuoto).

---

## 5. Incertezza quantificata: tre bande, mai fuse

1. **Banda di calibrazione** (C5): dai residui del fit leave-one-model-out, espressa
   come **semi-range conservativo** `[min, max]`, non come deviazione standard. La
   regola di casa si applica senza sconti: con terne di osservazioni non si stima una
   varianza, e "budget", non "limite superiore garantito" (AGENTS.md, "Linguaggio
   dell'incertezza"; P4.12 sui campi a `n = 3`).
2. **Banda di ignoranza parametrica** --- etichetta obbligatoria
   **`parameter_pue_ignorance_range`** (correzione 3.4, deliberata 26-10-2026). Per C2
   esiste gia' ed e' il `RangeValue` di EcoLogits: `compute_llm_impacts`
   (`impacts/llm.py:556-595`) itera su `(min, max)` del **numero di parametri** del
   modello registrato e sulle bande PUE/WUE del provider, e impacchetta i due risultati.
   Prova diretta 26-10-2026: `openai/gpt-4o-mini`, 100 token/1 s -> `[6,19e-06,
   7,56e-06]` kWh con `parameters:{min:8,max:28}` (il conteggio dei parametri di quel
   modello non e' pubblicato). **Non e' un'incertezza del modello** e non va mai
   chiamata cosi': e' l'intervallo delle nostre ignoranze su parametri e PUE. Le parole
   bandite su questa colonna, nel codice come nella tesi: `model_uncertainty`,
   `confidence`, `standard deviation`, `errore di stima`. Per C5 la banda di assunzione
   sul contorno (PUE del provider ignoto, quantizzazione non nota, `N_active` da scheda)
   si propaga moltiplicativamente sulla banda 1 e si riporta separata
   (`cloud_assumption_min/max`). DT-1 ("valore primario = intervallo") va riletto con
   questa etichetta: l'intervallo resta il valore primario, ma e' un intervallo di
   ignoranza di parametro, non di confidenza, e la lettura e' compatibile con la regola
   di casa ("semi-range conservativi, mai deviazione standard").
   Il campo `cloud_energy_band_semantics` (§4) esiste per rendere la distinzione
   verificabile riga per riga: due colonne min/max con semantica diversa non possono
   essere aggregate insieme, ed e' esattamente l'errore che la proposta del `cloud.DOCX`
   faceva quando leggeva `energy_cloud_j_min/max` come incertezza del metodo.
3. **Bandiera di validita'**: la riga dice se il modello richiesto sta dentro
   l'intervallo di calibrazione (parametri, lunghezza contesto, geometria). Fuori
   intervallo la riga resta, ma con `cloud_calibration_validity = "extrapolation"` e
   **non entra nelle statistiche primarie** — stesso meccanismo gia' costruito per le
   righe invalide di Emenda 8 (`partition_block_rows` nel runner v4).

La somma delle bande in quadratura e' la stessa questione aperta di P1.7/P2.9 per
`budget_base_w` e **non si decide qui**: resta l'eccezione dichiarata, e si scrive
quale forma si usa.

---

## 6. Gate per l'ammissione di C5

| gate | condizione | stato |
|---|---|---|
| G0 | accesso alla fonte dei coefficienti con licenza che consenta la ridistribuzione in tesi | **non superato oggi**: `ml-energy/benchmark-v3` gated, nessun token su questo host (26-10-2026). Le tabelle di 2505.06371 e di SweetSpot sono letture pubbliche: P2 si', P1 no |
| G1 | fit con leave-one-model-out e `loo_mape` riportato per classe | non eseguito |
| G2 | sanity: monotonia in `n_out` e in `n_in`; `n_out -> 0` non esplode (i termini `/n_out` di §2.1); MoE vs dense **distinguibili per riga**, con `cloud_moe_active_assumption` valorato (§2.3); `n_in = 0` degrada al solo decode | definibile ora, eseguibile dopo G1 |
| G3 | confronto con C2 sulla stessa geometria, scarto **riportato** e non corretto, **dopo** aver sottratto la componente strutturale `E_prefill^C5` che in C2 e' identicamente nulla (§2.2, correzione 3.3) | eseguibile su sottogruppo (i modelli registrati) |
| G4 | arbitraggio della scala assoluta | **non disponibile e non disponibile per costruzione**: il wattometro W1 (riga 410) arbitrera' il sistema locale, non un datacenter remoto. C5 resta etichettato "non validato", come C2 (riga 629) |

G4 va scritto nella tesi **prima** dei numeri, perche' e' la differenza fra "abbiamo
misurato" e "abbiamo modellato con coerenza". Il precedente di metodo e' lo stesso del
locale: un accordo fra due letture dello stesso registro non e' una validazione
indipendente, e due stime che riconducono alla stessa fonte (EcoLogits e C5, se i suoi
coefficienti nascono dalle tabelle di ML.ENERGY) concordano **per costruzione**.

---

## 7. Prerequisiti di codice (delta per il coder di P5)

Nell'ordine, perche' il primo blocca il percorso che DT-5 descrive come effettivo:

1. **Proxy morto.** `_MODEL_PROXY_RULES` (`cloud_energy.py:33-38`) e il fallback di
   famiglia (`:100-106`) puntano a `openrouter`, che non esiste in `ecologits` 0.11.1:
   6 provider, 344 modelli (contati da `data/models.json` il 26-10-2026). Fix gia'
   deliberato in `DECISIONI.md:240-252`: proxy su `huggingface_hub` (pari classe
   open-weight), con **casing esatto del nome registrato** (`meta-llama/Meta-Llama-3.1-8B-Instruct`,
   non `Llama-3.1-8B-Instruct`) e status transitorio `proxy_provider_unsupported`.
2. **`or 0.0`** (`benchmark_unified.py:1101`) e zero non dichiarato in local mode
   (`:466-476`).
3. **Scope del carbonio**: `cloud_energy.py:145` legge `res.gwp` = usage **+ embodied**
   (`impacts/llm.py:608`) mentre `energy_j` esclude l'embodied (`:15-17`, `:153-158`);
   `benchmark_unified.py:1110` lo etichetta "scope-2 incl. PUE" e `:1113-1116` ne cava
   un'intensita' carbon/energia a scope misti.
4. **Ancora di versione**: le note dichiarano "verificato su ecologits 0.11.3"
   (`cloud_energy.py:18`, `:159`) contro 0.11.1 installato; la versione utile finisce
   solo nel token `method` (`:189-191`).
5. **Segno della nota sulla latenza** (task #119): `cloud_energy.py:170-173` dichiara
   che la latenza misurata, includendo la rete, **sovrastima** la stima server-side.
   E' falso nel regime di risposta lenta, dove il `min` di `impacts/llm.py:99-102`
   sostituisce la nostra misura con la stima del motore (§2.0, tabella di sweep: piatto
   dal 3,7 s in poi, +48,145% sulla soglia dei 200 ms). Delta: correggere il testo della
   nota, e aggiungere `cloud_latency_used_s` perche' la riga dichiari la latenza
   **effective**. Le stesse parole sbagliate stanno in
   `metodi_per_dominio_20261025_spec.md:627-628` e `cap03_metodologia_misura.tex:619-622`.
6. **`N_active` dichiarato, non ereditato**: il motore usa `active = total` in silenzio
   per ogni modello senza il campo MoE nel registro (§2.3, `tracers/utils.py:89-94`).
   Delta: `cloud_moe_active_assumption`, `cloud_active_parameters_b`,
   `cloud_total_parameters_b` in riga, con i valori passati **esplicitamente** alla
   funzione di stima invece di lasciarli dedurre dal registro.
7. Solo dopo: il resto dei campi di §4 e il percorso C5.

---

## 8. Sequenza reale di lavoro

1. Richiedere l'accesso a `ml-energy/benchmark-v3` (serve un token HF dell'utente:
   **non lo creo e non lo tocco**, e in ogni caso il fit parte solo con accesso
   autorizzato). Fino ad allora: **P2**, trascrizione delle tabelle di 2505.06371 e
   SweetSpot con boundary, etichettata `fit-published-transcribed`.
2. Correggere `mlenergy2025` in `references.bib` verso Chung et al. 2505.06371 (toglierla
   dallo stato `IN VERIFICA` di AGENTS.md:213 con la data della verifica) e aggiungere
   la voce SweetSpot con il DOI, perche' **due paper si chiamano SweetSpot** (l'altro,
   arXiv:2508.03520, e' di power-capping).
3. Tabella dei coefficienti per classe: forma, unita', provenienza a 4 livelli,
   `loo_mape`, banda, bandiera di validita'. E' il primo artefatto numerico di C5 e
   nasce gia' con i suoi metadati, non come lista di numeri.
4. G2 e G3 sui soli modelli che hanno un equivalente registrato, cosi' il confronto
   C5/C2 e' una verifica di coerenza e non un modo per accordare i due numeri.
5. P5: campi di §4 nello schema CSV (che e' il congelamento in corso, task #42/#83).
