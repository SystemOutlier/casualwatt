# Fase B — integrazione alla proposta R1–R6

Data: 2026-10-29. **Stato: proposta. Nessuna riga di codice, schema, soglia o
documento normativo modificata; nessun run; nessun `powercfg`; nessun push.**
Questa integrazione accompagna `fase_b_proposta_r1_r6_20261029.md` (commit
`cb6b227`) e ne corregge tre punti: il ramo a uno o due run (R1), la
formalizzazione di `B_min`, la collocazione di `study` e dell'esito R6. Le sei
domande sono trattate nell'ordine in cui le hai poste.

Due fatti verificati oggi cambiano la proposta precedente e vanno detti subito:

1. **`budget_pred` non e' disponibile prima della campagna.** `budget_pred_b² =
   budget_fit_b² + u_edge,b² + u_bias,b²` (P4.6 `:1659`), e `u_bias,b =
   |bias_w|·Δt̄_W,b` (P4.6 `:1664`) con `bias_w` **grandezza di campagna**,
   comune a tutti i blocchi (`:1714`). L'ancora A1 di
   `p6_6_prepilota_20261025.md:322-325` dice che `budget_pred` "esce dal pilota
   P6.2": non e' esatto. Il pilota P6.2 produce `half_range_pre_w` e
   `u_within,b` (`:2376-2382`), non `u_bias`. L'ancora va spostata su
   `budget_fit` (§2.4).
2. **`study` non richiede una colonna in `CSV_COLUMNS`.** Esiste un file di run
   metadata con `run_id` (`casualwatt_csv_export.py:336-350`), il meccanismo di
   accodamento e' gia' in uso (D1, `ollama_keep_alive`, `:347-349`) e ogni riga
   dei dati porta gia' `run_id` (`:19`). La collocazione minima e' un'altra
   (§6).

---

## 1. Un run contro due run

### 1.1 Le tre architetture possibili

| | **A — un run, banda da P6.2** | **B — un run, banda dallo stesso run** | **C — due run: calibrazione + conferma** |
|---|---|---|---|
| **da quali dati deriva la banda** | `budget_pred`/`E_active` dal pilota P6.2, `B_rel` dichiarato | `s_med` delle fasi valutate, `B_rel` dichiarato | `budget_fit`/`E_active` per configurazione dal run di calibrazione, `q` e `B_rel` dichiarati |
| **quali dati la valutano** | le 15 fasi del run P6.6 | le stesse 15 fasi da cui esce `s_med` | le 15 fasi del run di conferma, distinte |
| **indipendenza banda/valutazione** | parziale: la scala viene da un altro run, ma non dalla stessa configurazione | **nessuna**: la forma assoluta usa una statistica delle fasi che giudica | piena: nessun dato entra in due ruoli |
| **indipendenza del veto `B_min`** | no: si calcola sulle fasi valutate | no | si': si calcola in calibrazione, prima del run di conferma |
| **coerenza di scala per configurazione** | **no**: P6.2 ha blocchi da `m = 3` (P3.8 `:1056`) e la geometria della campagna; `cfg_lungo` (256 token) non e' quella geometria | si', ma a costo della circolarita' | si': stesso disegno nei due run, quindi stessa `m`, stesso `T`, stesse configurazioni |
| **costo** | ≈3 h con H | ≈3 h con H | ≈6 h con H (30 fasi) + copertura e sensibilita' una volta |
| **cosa si puo' pubblicare** | `d`, `r`, `k/n` del run, con un'ancora di scala discutibile | `d`, `r`, `k/n` con una banda costruita sui dati giudicati | `d`, `r`, `k/n` del run di conferma; la calibrazione si pubblica come calibrazione |

### 1.2 Perche' B si esclude

`B_abs = B_rel·s_med` con `s_med` delle fasi valutate rende la forma assoluta
una funzione del campione che giudica: un campione con `s` alto allarga la
banda e facilita il passaggio. Non e' un caso limite: e' la definizione. Il
documento del 25/10 lo vieta due volte, in modo indiretto ma chiaro — "la banda
si congela al valore dell'ancora, non al valore osservato"
(`p6_6_prepilota_20261025.md:350-351`) e "l'accordo osservato si riporta a
parte e non la sposta" (`:351`). B e' esclusa, non sconsigliata.

### 1.3 Perche' A non basta

Due difetti, entrambi di scala e non di indipendenza formale:

- **`m` e geometria.** `budget_fit` e `budget_pred` sono definiti su un blocco
  di `m` richieste (`P3.8 :1056-1063`, `P4.6 :1666`). P6.2 usa blocchi da `m =
  3` alla geometria della campagna; il run P6.6 usa fasi da `T = 420 s` in tre
  configurazioni che non sono quella geometria. Mescolare le due scale e'
  esattamente il difetto che P4.6 ha chiuso il 24/10, quando un `Δt_W`
  aggregato invece della media per blocco avrebbe reso il budget fino a tre
  volte piu' largo (`:1675-1686`). Ripeterlo qui su `E_active` sarebbe lo
  stesso errore con un altro nome.
- **`u_bias`.** Come detto in testa: `budget_pred` contiene un termine che si
  misura sulla campagna. Prima della campagna o si assume `u_bias = 0`
  (convenzione di `:1702-1706`, ma il gate di P4.5 non e' stato valutato) o il
  numero non esiste.

Il veto `B_min` in A si calcola inoltre sulle fasi che vengono giudicate. E'
accettabile in linea di principio — un veto puo' solo impedire (§3.4) — ma non
e' indipendenza.

### 1.4 Perche' C e' la raccomandazione

**Raccomando C: due run distinti, con ruoli disgiunti.** La ragione non e' il
costo, che raddoppia, ed e' una scelta tua; la ragione e' che C e' l'unica
architettura in cui **nessun dato entra sia nella determinazione del criterio
sia nella sua valutazione**, e in cui la scala del criterio e' la stessa dei
dati che giudica:

- **run 1, calibrazione**: 15 fasi, stesso disegno del run 2 (`C = 3`, `R = 5`,
  `T = 420 s`, H). Produce, per configurazione, `budget_fit` ed `Ē_active`
  (scala della banda), i semi-range di `s` e `s_EPI` (veto `B_min`) e nient'altro
  che entri nel verdetto. I suoi `d` e `r` si riportano come **calibrazione**,
  non come risultato.
- **congelamento**: `B_abs,cfg = q·budget_fit,cfg/Ē_active,cfg`, `B_rel = 0,05`,
  `B_min,cfg` e l'esito del veto si scrivono nel piano e si committano.
- **run 2, conferma**: 15 fasi nuove, stesse condizioni. Si valutano contro la
  banda congelata. E' il run di P6.6, e i suoi numeri sono quelli che si
  pubblicano.

Perche' la calibrazione non puo' essere piu' corta: `B_min` confronta due
grandezze adimensionali misurate sulla **stessa** `T`. Calcolarlo su finestre
piu' brevi e applicarlo a `d` misurato su 420 s mescolerebbe due scale, di nuovo
il difetto di `:1675-1686`. Idem per `budget_fit`, che dipende da `Δt̄_W`.

Perche' **non** si adotta una banda *misurata* dalla calibrazione, ora che si
potrebbe senza circolarita': perche' `B_abs = B_min` renderebbe il veto vacuo
(`B_min ≤ B_abs` sempre), e `B_abs = k·B_min` introdurrebbe un `k` arbitrario,
cioe' un parametro nuovo senza ancora. La banda resta una **decisione**; la
calibrazione produce solo la **scala** e il **veto**. E' la distinzione
decisione/fattibilita' di `:339-354`, resa operativa.

### 1.5 Cosa cambia nel testo del protocollo

P6.6 `:2610` dice "prima del primo run". Con C servono due run e la frase va
letta come "prima del run **confermativo**": e' la decisione E del documento del
25/10 (`:413`), che questa integrazione rende obbligatoria e non piu'
facoltativa. In piu' va dichiarato che il run di calibrazione e' uno **studio
distinto**: i suoi `d` e `r` non si uniscono a quelli di conferma
(`p6_6_prepilota_20261025.md:9-37`), ed e' la ragione per cui serve il
marcatore `study` (§6).

---

## 2. `q = 1/3` e `B_rel = 0,05`, motivati separatamente

### 2.1 Tre tipi di numero, e l'evidenza disponibile

| tipo | esempi | cosa lo sostiene | stato |
|---|---|---|---|
| **misurato** | `B_min`, semi-range, `budget_fit`, `Ē_active` | dati della calibrazione | disponibile solo dopo il run 1 |
| **derivato** | `B_abs,cfg = q·budget_fit,cfg/Ē_active,cfg` | un rapporto fra grandezze misurate e un numero dichiarato | calcolabile |
| **progettuale** | `q = 1/3`, `B_rel = 0,05` | una decisione con una motivazione, non una misura | **[A] da approvare** |

**Non esiste alcun valore empirico o metrologico che sostenga `q` o `B_rel`.**
Va detto senza attenuazioni:

- l'unica osservazione di concordanza esistente e' **una fase**
  (`srum_emi_cross_20261023_analisi.md:147-148`): `s = 0,7339`, `s_EPI = 0,7361`,
  quindi `d = −0,0022` e `r = −0,0030`. E' un punto, non una distribuzione; e
  per giunta e' l'osservazione che ha motivato la banda, quindi non puo'
  calibrare cio' che ha contribuito a far nascere;
- la quantizzazione SRUM (2.582 bucket su 15.658 con `TimeInMSec > 60.000`,
  16,5%) e' un effetto di **finestra**, non una risoluzione di `d`: entra nel
  conteggio dei bucket interni, non nella banda;
- la risoluzione EMI e la scala assoluta non c'entrano: `d` e' un rapporto di
  quote, e la scala del contatore si semplifica. Nessuna soglia metrologica del
  contatore si trasferisce a `d`.

Quindi `q` e `B_rel` sono **[A] scelte progettuali**, e la calibrazione non le
sostiene: puo' solo **vetarle** (§3). Questa e' la risposta alla tua richiesta di
separare le scelte dai valori supportati.

### 2.2 `q = 1/3`

**Significato.** `q` e' la frazione del budget gia' dichiarato su una fase che
la differenza fra le due procedure e' autorizzata a consumare: `|d|·Ē_active ≤
q·budget_fit`. Detto in energia: l'attribuzione sbagliata non supera un terzo
dell'incertezza che pubblichiamo su quel numero.

**Perche' un terzo e non un altro numero.** Aritmetica, non evidenza. Il budget
e' una combinazione in quadratura (`P4.6 :1658-1659`): aggiungere un quinto
termine di dimensione `q·budget` porta il totale a `budget·√(1+q²)`.

| `q` | nuovo totale | variazione |
|---|---|---|
| 1/4 | 1,0308 | +3,1% |
| **1/3** | **1,0541** | **+5,4%** |
| 1/2 | 1,1180 | +11,8% |
| 1 | 1,4142 | +41,4% |

`q = 1/3` e' la frazione piu' grande che, presa da sola, resta una correzione
sotto il 6% del budget: non puo' diventare il termine dominante. E' un criterio
di **non-dominanza**, espresso con numeri e senza soglie introdotte a
posteriori; il valore 1/3 che il documento del 25/10 propone (`:322`,
decisione B `:409`) resta invariato, ma la sua motivazione qui e' questa e non
un'altra.

**Cosa non e'.** Non e' la significativita' statistica di un test, non e' un
livello di confidenza, non e' derivato da `err_rel <= 10%` (che riguarda la
previsione, §0 della proposta precedente) ne' dalle soglie 10%/20% di P1.6.

### 2.3 `B_rel = 0,05`

**Significato.** E' la tolleranza sulla forma relativa: `|r| ≤ 0,05`.

**Perche' 5%.** Convenzione dichiarata, non misura: e' la variazione relativa
che non sposta la seconda cifra significativa del J/token attribuito riportato
(`p6_6_prepilota_20261025.md:327-331`). E' l'unica motivazione disponibile, e il
documento stesso la chiama "piu' debole di A1, ma disponibile subito" (`:330-331`).

**Perche' serve comunque.** La forma assoluta non morde quando `s` e' piccolo:
con `s = 0,05`, `|d| ≤ 0,033` e' il 66% di `s`. La forma relativa e' l'unica che
in quella condizione distingue "differenza piccola rispetto alla quota" da
"differenza piccola in assoluto". E' il caso di `cfg_breve`, ed e' la ragione
per cui le due forme sono in congiunzione (F-R2).

**Cosa non e'.** Non e' una tolleranza di previsione. Il fatto che `err_rel ≤
10%` (P3.10) e `B_rel = 5%` stiano entrambi nell'ordine del 5–10% e' una
coincidenza numerica, non una derivazione: il primo confronta `E_pred` con
`E_oss`, il secondo confronta due quote. Scriverlo evita l'equivoco piu'
probabile in fase di revisione.

### 2.4 Conseguenza: l'ancora e' `budget_fit`, non `budget_pred`

`budget_pred` non e' calcolabile prima della campagna (§0, fatto 1). L'ancora
A1 va quindi riformulata su **`budget_fit`**, che dipende solo da `u_base` e
`u_within` (`P4.6 :1658`; `P3.8 :1059-1063`), entrambi prodotti dalla sequenza
P1.5 che il run di calibrazione esegue per intero (P6.2 `:2376-2382`):

```
B_abs,cfg = q · budget_fit,cfg / Ē_active,cfg        q = 1/3
```

La direzione dell'errore e' dichiarata e favorevole: `budget_pred` e' piu'
grande di `budget_fit` (aggiunge `u_edge` e `u_bias`), quindi una banda ancorata
a `budget_fit` e' **piu' stretta** di una ancorata a `budget_pred`. Se il
confronto passa contro `budget_fit`, passa anche contro la scala del numero
pubblicato. Se non passa, non si allarga: si dichiara non risolvibile.

Questo e' un emendamento alla formula di A1 come scritta in
`p6_6_prepilota_20261025.md:318-320`, e va approvato come tale.

---

## 3. `B_min` formalizzato

### 3.1 Formula e unita'

```
per configurazione cfg, sulle fasi VALIDE del run di calibrazione:

Δ_cfg(x)   = ( max_i x_i − min_i x_i ) / 2          semi-range, i = 1..n_valid
B_min,cfg  = Δ_cfg(s) + Δ_cfg(s_EPI)

veto:  B_min,cfg ≤ B_abs,cfg        e        B_min,cfg / s_med,cfg ≤ B_rel
con    s_med,cfg = mediana_i(s_i)   sulle stesse fasi valide
```

- **unita'**: `s` e `s_EPI` sono quote adimensionali in `[0,1]`, i loro
  semi-range sono adimensionali, `B_min` e' adimensionale, come `d` e `B_abs`.
  Nessuna conversione, nessun joule. Il confronto con `B_abs` e' fra grandezze
  omogenee per costruzione;
- **perche' la somma aritmetica**: e' il lato conservativo dichiarato in
  `AGENTS.md` (la quadratura sta fra `1/√2` e `1` della somma). Non e' una
  deviazione standard e non si chiama cosi' (P4.12);
- **perche' i marginali e non `d`**: `Δ(s) + Δ(s_EPI)` misura quanto ciascuna
  procedura si muove fra repliche. `Δ(d)` misurerebbe quanto si muove la loro
  differenza, cioe' importerebbe `d` nel criterio che deve giudicare `d`:
  sarebbe la circolarita' di B in un'altra forma.

Esempio aritmetico, **sintetico, non un run**: cinque fasi con `s` =
0,60/0,63/0,58/0,61/0,64 e `s_EPI` = 0,62/0,60/0,63/0,61/0,59 danno
`Δ(s) = 0,03`, `Δ(s_EPI) = 0,02`, `B_min = 0,05`; con `s_med = 0,612` il
secondo confronto e' `0,05/0,612 = 0,082 > 0,05`, quindi il veto **scatta** e
il confronto si dichiara non risolvibile a `B_rel = 5%`. Serve a mostrare che
il veto puo' mordere davvero, non a prevedere l'esito.

### 3.2 Dati necessari

| dato | da dove | quando |
|---|---|---|
| `s_i`, `s_EPI,i` delle fasi valide | harness sul run di calibrazione | prima del congelamento |
| validita' della fase | regole gia' esistenti, **nessuna dipende dalla banda**: finestra integra, `done_reason` atteso, nessun albero cambiato, ≥5 bucket interni, albero presente ogni minuto (`s_epi_phase.py:284-291`, `:106`) | idem |
| `B_abs,cfg` | §2.4 | idem |
| `B_rel` | dichiarato | gia' noto |

La validita' non dipende dalla banda, quindi `B_min` non e' affetto dal
problema di circolarita' che riguarda `B_abs`: si puo' calcolare su un run di
calibrazione senza aver ancora deciso nulla.

### 3.3 Casi limite, con la regola esplicita

| caso | regola | perche' |
|---|---|---|
| `n_valid,cfg < 4` | `B_min,cfg` = **nullo**, non zero | uno zero silenzioso farebbe passare il veto. Con meno di 4 fasi il quorum di R4 non c'e' comunque: la configurazione e' gia' "non valutabile" (§4) |
| `n_valid,cfg = 4` | calcolabile, si riporta | e' il minimo del disegno |
| `Δ(s) = Δ(s_EPI) = 0` con ≥4 fasi | `B_min = 0`, veto superato, e si annota "dispersione non osservata" | e' legittimo, ma con quattro fasi reali una coincidenza al bit e' implausibile: si tratta di un controllo di integrita' (finestre distinte, `t_start` distinti), **non** di una soglia. Nessun gate nuovo |
| `B_min > 1` | impossibile per costruzione (`Δ ≤ 1/2` ciascuno), nessun clamp | un clamp nasconderebbe un errore di calcolo |
| veto superato in una configurazione e non in un'altra | si applica **per configurazione** | R3 livello 3 non emette un verdetto di studio: non c'e' un esito unico da invalidare |
| veto ricalcolato sul run di conferma | si calcola e si riporta come **controllo**, e se fallisce la configurazione passa a "non risolvibile" | azione ammessa solo in direzione restrittiva: ritira una dichiarazione, non ne crea. La regola e' fissata prima; cambia solo il momento del calcolo |

### 3.4 Conseguenze sul verdetto

Il veto **non tocca `in_band`**: nessuna fase cambia stato. Introduce un quarto
esito di configurazione, accanto ai tre di R3:

| esito di configurazione | quando |
|---|---|
| in concordanza | `n_valid ≥ 4` e tutte le valide in banda, e veto superato |
| fuori concordanza | `n_valid ≥ 4` e almeno una valida fuori banda |
| **non risolvibile a questa precisione** | `n_valid ≥ 4` e veto fallito |
| non valutabile | `n_valid ≤ 3`, oppure `B_min` nullo in calibrazione |

"Non risolvibile" e' un esito, non un guasto: e' la formula di
`p6_6_prepilota_20261025.md:346-349` ("si riporta che il confronto non e'
risolvibile a quella precisione, #70 resta aperto"). La differenza rispetto a
"non valutabile" e' che nel primo caso la misura e' stata fatta e la procedura
non distingue; nel secondo la misura non c'e'.

### 3.5 Dove vive

Funzione di analisi nell'harness, non produzione: legge le righe per fase,
calcola, e scrive il risultato nel piano/JSON di analisi. Nessuna colonna
nuova, nessun tocco al percorso energetico. La funzione e' testabile senza
hardware (§7).

---

## 4. R5 — come l'esclusione per `engine_tree_changed` incide sul quorum

### 4.1 Gli stati di una fase, e chi li conta

Per ogni configurazione si eseguono `R = 5` fasi di misura. Ogni fase finisce
in **uno** di questi stati, e il conteggio e' esaustivo:

| stato | cause | entra in `n_valid` | produce verdetto | entra in `k/n` |
|---|---|---|---|---|
| valida, in banda | — | si' | si' | numeratore |
| valida, fuori banda | — | si' | si' | **no** (denominatore) |
| invalida per albero cambiato | `engine_tree_changed` | **no** | no (`in_band = null`) | no |
| invalida per altro guasto | `meno_di_5_bucket`, `minuto_senza_albero`, `done_reason`, `finestra_non_valida`, `denominatore_nullo`, `albero_a_zero`, `s_fuori_da_0_1`, `s_assente`, `esclusione_dichiarata` | **no** | no | no |
| di sensibilita' al bordo | ±30 s | — | fuori dal verdetto | — |

Le nove cause tecniche sono l'elenco di `BLOCKING_FLAGS` e `BLOCKING_PREFIXES`
(`s_epi_phase.py:284-291`).

### 4.2 La regola, in una riga

`engine_tree_changed` **concorre al quorum come qualunque altra invalidita'**:
consuma una delle 5 fasi, non si sostituisce, e `n_valid` scende a 4. Non
esiste un conto separato che la renda gratuita. Il verdetto resta congiuntivo
sulle `n_valid` rimaste:

```
n_valid = 5 − (fasi invalide, qualunque causa)
verdetto se n_valid ≥ 4;  altrimenti "non valutabile"
```

### 4.3 Cosa questo comporta, detto per intero

- **Il criterio diventa piu' facile da soddisfare, non piu' difficile.** Con
  `n_valid = 4` servono quattro fasi in banda invece di cinque: la tolleranza
  riduce la base probatoria. E' il costo dichiarato di `R = 5` con una fase
  tollerata (`:101`), e va scritto accanto a `k/n`, non nascosto: si riporta
  `k/n` **e** `n_valid`, e il lettore vede 4/4 accanto a 3/5.
- **Il conto si fa per configurazione, mai in pool.** Due invalide in `cfg_breve`
  non si compensano con cinque valide in `cfg_lungo`.
- **Una fase con piu' cause e' una fase.** Si conta una volta, si riportano
  tutte le cause. Una fase con `engine_tree_changed` e `meno_di_5_bucket` e'
  una fase invalida con due ragioni.
- **La causa si riporta separata**: `n_blocking_tree_changed` distinto dagli
  altri bloccanti, perche' un albero instabile e' un fatto sulla macchina e un
  `done_reason` mancato e' un fatto sulla richiesta.
- **Due invalide nella stessa configurazione ⇒ `n_valid = 3` ⇒ "non
  valutabile"**, e non "fuori concordanza". Sulla configurazione non si dice
  nulla; R3 livello 3 lo registra come `k_cfg` ridotto.
- **La calibrazione ha il suo quorum.** Serve `n_valid ≥ 4` anche nel run 1,
  altrimenti `B_min` e' nullo (§3.3) e la configurazione non e' dichiarabile.
- **Le fasi di sensibilita' non entrano mai in `R`** e non consumano la
  tolleranza: non sono repliche (`:93-94`).

### 4.4 Cosa non si fa

Non si sostituisce una fase persa (sarebbe un cambio di disegno dopo l'inizio),
non si "recupera" una fase invalida con una delle fasi di sensibilita', non si
sposta la tolleranza su un'altra configurazione, e non si riduce `T` per far
entrare piu' fasi.

---

## 5. R6 — come si riporta una divergenza senza scegliere dopo

### 5.1 Due verdetti registrati, uno che conta

Ogni fase con almeno un nato produce **due** verdetti, entrambi scritti:

- `verdetto_primario`: `s` con il tempo CPU intero dalla nascita, cioe' il
  comportamento di produzione (`worker_tree.py:184-189`);
- `verdetto_sensibilita`: `s` ricalcolato sulla sola intersezione dell'albero.

Regola fissa, identica nei quattro casi:

| primario | sensibilita' | `nascita_non_stabile` | cosa entra in `k/n` | cosa si scrive |
|---|---|---|---|---|
| in banda | in banda | no | il primario (dentro) | la fase non e' ambigua |
| in banda | fuori banda | **si'** | il primario (dentro) | la fase e' dentro solo se il tempo dei nati si conta intero; il dato non distingue le due trattazioni |
| fuori banda | in banda | **si'** | il primario (fuori) | la fase e' fuori; l'uscita dipende dalla trattazione della natalita', non solo dal disaccordo fra procedure |
| fuori banda | fuori banda | no | il primario (fuori) | la fase non e' ambigua |

In nessuno dei quattro casi il verdetto che entra in `k/n` e' quello della
sensibilita'. La divergenza **non cambia il numero**: cambia la frase che lo
accompagna. E' la sola costruzione che impedisce la scelta a posteriori, perche'
il valore usato nel verdetto e' fissato prima di sapere se i due bracci
divergono.

### 5.2 Le tre proibizioni

1. non si sceglie il braccio dopo aver visto i risultati: il braccio primario e'
   la produzione, per definizione e prima del run;
2. non si scarta una fase perche' il braccio secondario e' sfavorevole: una
   fase resta nel denominatore qualunque cosa dica la sensibilita';
3. non si riesegue la fase per ottenere un caso non ambiguo.

### 5.3 Livello configurazione e livello studio

- con **almeno una** fase `nascita_non_stabile`, la frase sulla configurazione
  porta la clausola "condizionata al trattamento della natalita'", e si
  elencano le fasi interessate;
- se **tutte** le fasi di una configurazione sono `nascita_non_stabile`, la
  configurazione non si dichiara ne' in concordanza ne' fuori: si dichiara che
  la procedura non distingue le due trattazioni;
- a livello di studio non si emette comunque un verdetto (R3 livello 3), quindi
  la clausola si propaga alla frase su `k_cfg/C`.

### 5.4 Quando il braccio non esiste

Oggi il tempo CPU dei nati non e' registrato: `tree_born` porta le identita'
(`casualwatt_csv_export.py:135`), non il tempo. Senza quel dato il braccio di
sensibilita' **non si calcola**, e la regola e':

- si riporta la natalita' come **osservata e non quantificata**, con il numero
  di fasi che hanno almeno un nato;
- **l'assenza del braccio non e' una prova che la natalita' non conti.** E'
  esattamente il caso in cui un limite dichiarato viene letto come un risultato:
  la frase obbligatoria e' "la sensibilita' non e' stata calcolata", non "la
  natalita' non ha effetto";
- se nessuna fase ha nati, la frase e' diversa e piu' forte: "trattamento non
  esercitato", che e' un fatto sull'osservazione.

---

## 6. Collocazione minima di `study` e dell'esito R6

### 6.1 `study`

**Minimo, senza emendamento allo schema dei dati.** Tre pezzi, tutti gia'
esistenti:

| pezzo | dove | stato |
|---|---|---|
| `study` nel piano di analisi | campo del JSON letto da `_load_plan` (`s_epi_phase.py:506`); oggi il piano porta gia' `campaign_id`, `ollama_version`, `model_digest` | **nessuna modifica allo schema**: il piano e' un artefatto di analisi |
| `study` nell'output dell'harness | accanto a `campaign_id` nel payload (`:549-557`) — e' un campo di un file di analisi, non del CSV di produzione | idem |
| `study` nel run metadata | una riga in coda a `RUN_METADATA_COLUMNS` (`casualwatt_csv_export.py:336-350`), con il precedente esplicito di D1 (`ollama_keep_alive`, `:347-349`) | **un emendamento di una riga**, compatibile: le righe gia' scritte restano leggibili (`meta.get(c, "")` a `:362`) |

Il legame fra i due mondi e' `run_id`, che e' gia' colonna dei dati
(`:19`) e gia' colonna del run metadata (`:337`). Quindi: **nessuna colonna in
`CSV_COLUMNS` (172, `:17-200`), nessuna in `BLOCK_SUMMARY_COLUMNS` (36,
`:208-223`), nessuna in `POINT_SUMMARY_COLUMNS` (19, `:225-233`).**

**Se invece si vuole che una riga sia auto-descrittiva senza join**, allora
serve un emendamento vero: appendere `study` come ultima colonna di
`CSV_COLUMNS` **e** delle due tabelle di riepilogo (una riga per blocco e per
punto non ereditano le colonne dei dati). Costo: tre colonne in coda, i test di
schema da aggiornare (`tests/test_csv_schema_p5.py`, `test_shared_components_v4.py`,
`test_cpu_share_window.py`, `test_energy_corrections.py`, `test_metodo_per_riga.py`
contengono l'elenco delle colonne), nessun cambio di significato a una colonna
esistente. E' compatibile con la convenzione di Emenda 8, ma non e' il minimo:
lo propongo solo se ritieni insufficiente il legame via `run_id`.

### 6.2 Esito della sensibilita' R6

**Solo lato analisi, nessun emendamento.** Campi nuovi nella riga dell'harness
e nell'elenco `fields` che scrive il CSV di analisi (`s_epi_phase.py:566-573`):

`verdetto_primario`, `verdetto_sensibilita`, `nascita_non_stabile`,
`s_epi_intersezione`, `n_born`, `n_born_reused_pid`.

Sono campi di un artefatto di analisi, non del CSV di produzione
(`casualwatt_csv_export.py` non e' toccato). L'harness ignora le chiavi non
elencate in `fields` (`extrasaction="ignore"`, `:575`), quindi l'aggiunta e' un
atto esplicito e non silenzioso.

**L'unica cosa che R1–R6 possono richiedere allo schema di produzione** e' il
testo CPU dei nati, se si vuole il braccio numerico: una colonna in coda a
`CSV_COLUMNS`, per esempio `worker_born_cpu_s` (somma per riga, non per
processo: basta per il braccio dell'intersezione). Un emendamento, una colonna,
in coda. Se non la si autorizza, R6 resta diagnostica e la frase obbligatoria e'
quella di §5.4: osservata, non quantificata.

---

## 7. Formulazioni aggiornate

Sostituiscono F-R1, F-R4, F-R5 e F-R6 della proposta del 29/10; F-R2 e F-R3
restano invariate.

> **F-R1′ — banda di concordanza, con run di calibrazione distinto.**
> La banda si fissa prima del run **confermativo**, su dati di un run di
> **calibrazione** con lo stesso disegno (`C = 3`, `R = 5`, `T = 420 s`), e si
> committa nel piano:
> `B_abs,cfg = q · budget_fit,cfg / Ē_active,cfg` con `q = 1/3`, e
> `B_rel = 0,05` dichiarato. `budget_fit` ed `Ē_active` sono medie delle fasi
> valide della calibrazione per configurazione; `B_rel` non si ricava da
> `B_abs` e nessuno dei due dipende da una fase del run di conferma. Una fase e'
> in concordanza se e solo se `|d| <= B_abs,cfg` **e** `|r| <= B_rel`. Senza
> banda nel piano `in_band` resta nullo. `B_min,cfg = Δ(s) + Δ(s_EPI)` sui
> semi-range delle stesse fasi valide, mai su `d`, e' un veto: se
> `B_min,cfg > B_abs,cfg` oppure `B_min,cfg/s_med,cfg > B_rel`, la configurazione
> si dichiara "non risolvibile a questa precisione", la banda non si tocca e la
> decisione torna all'utente. `B_min,cfg` e' nullo, non zero, con meno di 4 fasi
> valide. Il piano e' rifiutato se `q`, `B_rel`, `B_abs,cfg` o `B_min,cfg`
> mancano. I `d` e `r` della calibrazione si riportano come calibrazione e non
> si uniscono a quelli di conferma.

> **F-R4′ — disegno, con i due run.** `C = 3`, `R = 5`, `T = 420 s`, dove `T` e'
> la finestra fra le due letture ai bordi e con H il carico dura `T + 120 s`.
> Minimo 4 fasi valide per configurazione, cioe' `⌈2/3·5⌉`. Una fase invalida
> non si sostituisce. Il disegno si esegue **due volte**: calibrazione, poi
> conferma, con un blocco di riposo fra i due e senza riusare le fasi. Le fasi
> di sensibilita' al bordo non sono repliche, non entrano in `R` e non
> consumano la tolleranza. Il piano e' rifiutato se `C`, `R` o `T` mancano, se
> il numero di fasi di misura per configurazione non e' `R`, se le fasi di
> sensibilita' sono conteggiate in `R`, o se `T/60 − 1 < 5`.

> **F-R5′ — `engine_tree_changed` e il quorum.** L'esclusione e' ratificata: la
> fase non produce verdetto (`in_band = null`), non si sostituisce, e **concorre
> al minimo di 4 fasi valide come qualunque altra invalidita'**:
> `n_valid = 5 − (fasi invalide di qualunque causa)`, verdetto congiuntivo se
> `n_valid >= 4`, altrimenti "non valutabile". Si riportano `k/n_valid` e
> `n_valid` insieme. La causa si riporta a parte
> (`n_blocking_tree_changed`). Una fase ha `engine_tree_changed = true` se
> almeno una delle sue richieste ha la riga a vero. Il ramo "`s` dal fallback
> dichiarato" non e' disponibile e resta chiuso. La riduzione di `n_valid`
> riduce la base probatoria del verdetto: e' dichiarata, non compensata.

> **F-R6′ — natalita': due verdetti, uno che conta.** Ogni fase con almeno un
> nato riceve un verdetto primario (tempo CPU intero dalla nascita,
> comportamento di produzione) e un verdetto di sensibilita' (`s` ricalcolato
> sulla sola intersezione dell'albero). In `k/n` entra **sempre** il primario,
> qualunque sia l'esito della sensibilita'. Se i due verdetti divergono, la
> fase si annota `nascita_non_stabile` e la relazione dichiara che quella fase
> non distingue le due procedure dalle due trattazioni della natalita'. Con
> tutte le fasi di una configurazione non stabili, la configurazione non si
> dichiara ne' in concordanza ne' fuori. Non si sceglie il braccio dopo aver
> visto i risultati, non si scarta una fase perche' il braccio secondario e'
> sfavorevole, non si riesegue la fase. Senza il tempo CPU dei nati la
> natalita' e' osservata e non quantificata, e l'assenza del braccio non e'
> prova che la natalita' non conti. Nessuna nascita ⇒ "trattamento non
> esercitato".

---

## 8. Cosa aspetta la tua approvazione

Cinque punti, in ordine di conseguenza:

1. **Due run (C) invece di uno.** Costo ≈6 h con H invece di ≈3 h; in cambio
   nessun dato in due ruoli, scala coerente per configurazione, veto calcolato
   prima del run che giudica. Se preferisci un run, va detto che l'ancora A1
   non e' formabile per configurazione (§1.3) e che il veto si calcola sui dati
   giudicati.
2. **`budget_fit` al posto di `budget_pred`** in A1 (§2.4): `budget_pred`
   contiene `u_bias`, che e' una grandezza di campagna (P4.6 `:1664`, `:1714`).
   La banda diventa piu' stretta, quindi conservativa.
3. **`q = 1/3`** confermato, con la motivazione di non-dominanza (§2.2); non e'
   un valore empirico e va approvato come scelta.
4. **`B_min` come veto con la formalizzazione di §3**, inclusi i due casi
   limite che decidono un verdetto: nullo (non zero) sotto 4 fasi valide, e
   "non risolvibile" come quarto esito di configurazione.
5. **Collocazione**: minimo di §6.1 (`study` nel piano, nell'output
   dell'harness e in coda a `RUN_METADATA_COLUMNS`), oppure colonna anche in
   `CSV_COLUMNS` e nei due riepiloghi. E, per R6, o la sola diagnostica o la
   colonna `worker_born_cpu_s`.

Nessuna implementazione comincia prima della tua approvazione finale.

---

## 9. Ancore verificate in questo turno

* `experiment_results/protocollo_v4_20261024.md`: `:1653-1674` (P4.6, i due
  budget e la loro composizione), `:1663-1664` (`u_edge`, `u_bias`), `:1675-1686`
  (scala su `Ē_b`, difetto `Δt̄_W` contro `Σ Δt_W`), `:1714` (`bias_w` comune
  alla campagna), `:1054-1071` (P3.8, `m`, `u_within` non diviso per `√m`),
  `:2364-2382` (P6.2, cosa produce il pilota), `:2608-2615` (banda prima del
  run), `:2617-2622` (risultato e interpretazione separati), `:2624-2635`
  (`engine_tree_changed`);
* `experiment_results/p6_6_prepilota_20261025.md`: `:9-37` (studio di
  calibrazione, nessun pooling), `:96-127` (disegno e costo), `:301-354`
  (ancore A1/A2/A3, regola di fattibilita', divieto di restringere),
  `:405-427` (decisioni A–H);
* `cwEnergyModular/casualwatt_csv_export.py`: `:19` (`run_id` in
  `CSV_COLUMNS`), `:17-200` (`CSV_COLUMNS`), `:208-223`
  (`BLOCK_SUMMARY_COLUMNS`), `:225-233` (`POINT_SUMMARY_COLUMNS`), `:336-350`
  (`RUN_METADATA_COLUMNS`, precedente D1), `:353-362` (`write_run_metadata`,
  `meta.get(c, "")`), `:135` (`tree_born`, identita' senza tempo);
* `s_epi_phase.py`: `:106` (`MIN_BUCKETS_PER_PHASE`), `:284-291`
  (`BLOCKING_FLAGS` e prefissi), `:506` (`_load_plan`), `:549-563` (payload
  JSON: `campaign_id`, `ollama_version`, `model_digest`, `band`), `:566-573`
  (elenco `fields` del CSV di analisi), `:575` (`extrasaction="ignore"`);
* `cwEnergyModular/energy/worker_tree.py`: `:184-189` (nato conta da zero),
  `:200-208` (perdita e riuso di PID).

Non eseguito: nessun `pytest`, nessun `--selftest`, nessun run, nessun
`powercfg`. Il conteggio di riferimento resta 526 = 523 + 3 di `AGENTS.md`.
