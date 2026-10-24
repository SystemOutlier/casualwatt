# Valutazione della revisione esterna del protocollo v4 — 2026-10-24

Materiale valutato: `miglioraFormule.DOCX` (30.797 byte, 192 paragrafi), copia di
due revisioni distinte del protocollo `protocollo_v4_20261024.md` prodotte da due
modelli esterni. Il file non è tracciato e resta fuori dal repo: questa
valutazione è l'artefatto tracciato, e cita il DOCX per paragrafo.

Regola applicata: il materiale fornito dall'utente e le descrizioni prodotte da
altri LLM sono **spunti, non evidenza**. Ogni affermazione è stata verificata
contro il testo del protocollo, il codice in `cwEnergyModular/`, o ricalcolata
qui. Nessuna affermazione della revisione entra nel protocollo senza verifica.

Le due revisioni dichiarano i propri limiti: la seconda scrive esplicitamente
"Non ho verificato i riferimenti di P1.14 (gli arXiv del 2026), i numeri citati
dai file di analisi e i numeri di riga del codice. Non ho eseguito niente del tuo
codice" (par. 191). È un comportamento corretto e va detto: nessuna delle due ha
accesso al repo, quindi i loro numeri o si riproducono o non si citano.

Verdetto sintetico: **4 contraddizioni reali nel testo congelato**, **7
correzioni di forma o di definizione applicabili subito**, **6 proposte che
cambiano un punto congelato e richiedono una decisione**, **4 respinte con
motivo**. Due numeri della revisione si riproducono esattamente; uno no.

---

## 1. Contraddizioni reali nel testo congelato

Non sono opinioni: sono punti in cui due parti del protocollo si escludono.

### 1.1 `r_A` non è calcolabile sui blocchi di controllo

Sollevata dal revisore 1, par. 116-124. **Confermata.**

- P4.4 requisito 7 dichiara che la struttura di baseline 3 pre + 3 post rende
  calcolabili su un blocco di controllo `baseline_pre_w`, `baseline_post_w`,
  `dP`, `budget_base_w`, `budget_base_j`, **`r_A`** e `r_B`;
- P4.5 apre con "`r_A`, `budget_base_j,c` e `budget_base_w,c` esistono su un
  blocco di controllo" e filtra `bias_w` "sui soli blocchi con `r_A ≤ 10%`"
  (`:1149`);
- ma `r_A = |dP| · Σ Δt_W,i / Σ E_trunc,i` con somme "sulle **richieste valide**"
  (P1.6, `:150`; F.3, `:1618`), e un blocco di controllo **non invia richieste**
  per costruzione (P4.4 requisito 5: "attende quella durata senza inviare
  richieste").

La somma al denominatore è vuota. P1.6 chiude il caso: "Se il denominatore di
`r_A` o `r_B` è zero, il blocco o il punto è invalido per costruzione". Quindi,
applicando il protocollo alla lettera, **ogni blocco di controllo è invalido** e
il filtro di P4.5 non seleziona nulla: il gate dell'anello 4 di P4.9 non è
eseguibile. Il requisito 7 di P4.4 è corretto per le quantità di baseline e
sbagliato per `r_A` e `r_B`.

`r_A` è una grandezza **relativa**: confronta l'errore di drift con l'energia
misurata. Senza energia misurata non ha denominatore, e non esiste un modo di
definirla su un blocco vuoto che non sia circolare. Il revisore ha ragione anche
sulla direzione della cura: serve una metrica di stabilità **specifica** per i
controlli, con un altro nome.

### 1.2 `u_bias` è dichiarato nel budget ma non compare nella formula

Sollevata dal revisore 1, par. 126-135. **Confermata.**

Il testo dice che `u_bias` entra in `budget_pred` in cinque punti: P4.4 requisito
1 (`:1109`), P4.5 esito negativo (`:1157`), anello 4 di P4.9 (`:1334`), P4.14
(`:1462`), F.12 (`:1848`). La formula congelata di P4.6 è

```
budget_pred_b² = budget_fit_b² + u_edge,b²
```

e `u_bias` non c'è. La regola testuale e la formula si contraddicono, e la
formula è ciò che un implementatore traduce in codice.

Seconda parte della stessa osservazione, anch'essa corretta: `u_bias =
|bias_w| · Δt_W` non dice **quale** `Δt_W`. `bias_w` è aggregato su tutti i
controlli (`Σ_c E_net,control,c / Σ_c Δt_W,c`), quindi è un watt medio di
campagna; moltiplicarlo per un `Δt_W` singolo o per una durata aggregata dà
joule diversi di un ordine di grandezza. Senza specificarlo il campo
`u_bias_j` — già elencato come obbligatorio in P4.12 (`:1410`) — non è
calcolabile.

### 1.3 `E_trunc` è usato in una formula congelata e non è definito

Sollevata dal revisore 2, par. 179. **Confermata**: `grep -n "E_trunc"` dà
quattro occorrenze, tutte d'uso (`:150`, `:151`, `:1618`, `:1619`) e nessuna di
definizione. Il simbolo non compare nella sezione Terminologia, che pure elenca
`P_pre`, `E_base`, `E_net_incremental` e `dP`.

Il nome viene dalla produzione, che tronca due volte (`local_energy.py:300` e
`:309-310`); la v4 non tronca (P1.3, P3.2, F.2). Quindi il simbolo è l'eredità
di un metodo che il protocollo ha esplicitamente abbandonato, e il suo significato
in v4 è ambiguo fra tre candidati che danno comportamenti diversi:

| candidato | denominatore | conseguenza se `Σ E_net < 0` |
|---|---|---|
| `Σ E_net_incremental,i` firmato | può essere ≤ 0 | `r_A ≤ 0` passa sempre: il filtro è cieco |
| `|Σ E_net_incremental,i|` | ≥ 0 | `r_A` esplode quando il blocco non ha segnale: comportamento corretto |
| `Σ |E_net_incremental,i|` | > 0 | confronta il drift con una grandezza che non entra nel fit |

### 1.4 La copertura è classificata sui target, il fit è sugli actual

Sollevata dal revisore 2, par. 186 ("calcola la copertura sui token reali medi
del blocco, non sui target"). **Confermata, ed è il protocollo stesso a
contraddirsi.**

`:585` scrive, dei dati v3: "Il target è una richiesta al costruttore del
prompt, **non una coordinata**", con l'evidenza che a `N_in = 64` dichiarato
corrispondevano **126** token reali per inferenza — la riga citata riporta il
totale di run `tokens_in=378` su 3 inferenze (`lhm_validation_v3_20261023_185232.csv:2`,
md `:6`, `:13`). Il modello però è stimato sui token reali (P2.3, F.6:
`N_in_actual,i = prompt_eval_count_i`), mentre l'inviluppo di P4.7 "si calcola
dai 10 **punti di disegno**" e i margini pubblicati (1,33 / 64,0 / 21,2 / 107,7)
sono calcolati sulle coordinate target. Se `N_in_actual` è sistematicamente
circa il doppio del target ai livelli bassi, il punto operativo `(12,32)` non sta
dove la classificazione dice che sta, e il suo margine di 1,33 token — già
sottile — non è il margine reale.

Classificare la copertura in una base e stimare il modello in un'altra rende
`coverage_tier` e `hull_margin_tok` non coerenti con `x1_b`, `x2_b` di F.7.

---

## 2. Correzioni di forma e di definizione applicabili

Hanno una sola risposta difendibile e non cambiano nessuna decisione congelata.

### 2.1 La giustificazione di `u_edge` è sbagliata, il valore no

Sollevata dal revisore 2, par. 180. **La matematica è confermata, il numero della
revisione no.**

P4.6 scrive: "il contatore cumulativo è interpolato linearmente (`_emi_cum_at`,
`energy_session.py:1103-1124`), quindi l'errore di un bordo è al più
`P_peak · δt_edge`". Non segue. L'interpolazione lineare di un contatore
cumulativo ha errore **nullo a potenza costante**, qualunque sia il livello:
verificato numericamente oggi integrando `P = 35 W` su un tick di 0,30 s, errore
massimo 3,0e-11 J. Il livello di potenza non c'entra; c'entra la sua
**variazione** dentro il tick. Per un gradino `ΔP` posto a frazione `f` del tick:

```
max_t |E(t) − interpolante(t)| = ΔP · f · (1 − f) · Δt_tick   ≤  ΔP · Δt_tick / 4
```

Verificato numericamente: con `ΔP = 25 W` e `Δt_tick = 0,30 s`, `f = 0,25` →
1,4062 J, `f = 0,5` → 1,8750 J, `f = 0,75` → 1,4063 J, contro
`ΔP·f(1−f)·h` = 1,4062 / 1,8750 / 1,4062. Per una rampa lineare l'errore è la
metà del limite del gradino: 0,9375 J.

Il termine congelato `2 · P_peak · δt_edge` con `δt_edge = Δt_tick/2` vale
`2 × 35 W × 0,15 s = 10,5 J` ed è invece la forma corretta di **un altro**
errore: quello di disallineamento, cioè l'energia di un intervallo `δt`
attribuita al lato sbagliato del bordo. Il revisore lo dice ("se c'è invece un
disallineamento tra l'orologio EMI e quello Python, vale `P·δt`: i due casi
vanno distinti") e ha ragione.

Il suo numero alternativo, "3,75 J invece di 10,5 J", è riproducibile ma non
ancorato: è `2 × (25 W × 0,30 s / 4)`, cioè due bordi con un'oscillazione
completa idle→picco dentro un singolo tick. È il caso peggiore del termine di
interpolazione, non una misura. I due termini sono **distinti e concordi in
segno**, quindi il limite della somma è `10,5 + 3,75 = 14,25 J`, e il valore
congelato 10,5 J non li maggiora entrambi.

Codice verificato: `_emi_cum_at` interpola fra due campioni del buffer
(`energy_session.py:1117-1124`) e **non estrapola**: fuori copertura ma entro
1 s restituisce il valore estremo (`:1111-1116`), cioè attribuisce energia zero
a quel tratto. È un terzo modo di sbagliare il bordo, più grande degli altri due
(fino a `P · 1 s`), e non è nominato né in P4.6 né nella revisione. Il
docstring di `_emi_field_at` conferma che "il buffer campiona a 0,05 s" è il
valore dichiarato, non il misurato.

### 2.2 `E_pred ≤ 0` non è gestito nel criterio di validazione

Sollevata dal revisore 1, par. 111. **Confermata.** P3.10 e F.10 definiscono
`err_rel = |E_meas − E_pred| / E_pred` senza condizioni sul denominatore. Con
`E0` libero di essere negativo — e P3.3 lo prevede esplicitamente, con il flag
`intercept_nonphysical` — una previsione nulla o negativa a geometrie piccole è
possibile. La risposta corretta è quella proposta: caso dichiarato come
fallimento della previsione, non divisione implicita.

### 2.3 L'intervallo di conferma non è "al 95%"

Sollevata dal revisore 1, par. 113-114. **Confermata.** `:742`, nella tabella
del disegno, chiama il criterio "≤ 10% e dentro l'intervallo bootstrap **al
95%**". L'intervallo congelato è `[q2.5 − 2·u_conf, q97.5 + 2·u_conf]`: i
quantili sono al 95%, poi vengono allargati di due semi-range, quindi la
copertura nominale non è il 95% e non è quantificata. Il revisore chiede che si
chiami "intervallo operativo costruito dal protocollo": è la stessa regola che il
protocollo applica già altrove ("la copertura è un campo, non un aggettivo nel
testo").

### 2.4 `a` e `b` sono costi marginali solo a `N_out = 0` / `N_in = 0`

Sollevata dal revisore 1, par. 83-88. **Già coperto a metà.** P3.4 riporta le
derivate `∂E/∂N_out = b + c·N_in,ref` e `∂E/∂N_in = a + c·N_out,ref`, e lo
stesso revisore lo riconosce ("Queste derivate sono interpretate correttamente
nel documento"). Resta ambigua solo la lista di P3.3, che chiama `a` "J/token di
prefill marginale" senza dire a quale `N_out`. È una parola da aggiungere, non
una decisione.

Su `E0` il revisore chiede che resti "un parametro del modello, non una misura
indipendente dell'overhead": **già congelato**, P3.3 scrive "`E0` è
un'estrapolazione a `(0,0)`: il punto minimo `(8,4)` la vincola ma non la
identifica", con `intercept_nonphysical`. Nessuna modifica.

### 2.5 Conteggio delle sostituzioni per cella

Sollevata dal revisore 2, par. 187. **Valida.** P3.12 prevede che una richiesta
di geometria che termina a EOS prima del tetto sia `design_deviation`, sostituita
e registrata, ma non chiede il conteggio per cella. L'osservazione di fondo è
corretta e non è nel protocollo: sostituire le richieste che terminano presto
seleziona prompt che generano a lungo, quindi la cella finisce per contenere una
popolazione di prompt non casuale. Registrare quante sostituzioni per cella
costa una colonna e rende visibile l'effetto.

### 2.6 Il pre-pilota deve verificare anche i livelli bassi

Sollevata dal revisore 2, par. 186. **Valida, ed è una lacuna di P3.15**, che
limita il pre-pilota alla "fattibilità dei livelli (512 input, 256 output,
prompt che sostengono la generazione)". I livelli critici sono invece quelli
bassi: `(8,4)` è un vertice dell'inviluppo e `(12,32)` è il punto operativo con
margine 1,33 token, ed entrambi stanno dove l'overhead fisso misurato in v3
(target 64 → actual 126, `:585`) pesa di più in proporzione. Se 8 o 12 token di
input non sono raggiungibili, il vertice e il punto operativo non esistono nelle
coordinate dichiarate.

### 2.7 Cosa assorbe `c`, e il termine quadratico omesso

Sollevata dal revisore 2, par. 189. **L'algebra è corretta e va registrata.**
Se il costo del contesto al passo `j` di decode cresce come `N_in + j`, la somma
esatta è

```
Σ_{j=1..N_out} (N_in + j) = N_in · N_out + N_out · (N_out + 1) / 2
```

cioè esattamente il termine di interazione del modello **più** un termine in
`N_out²` che il modello a 4 parametri non ha. P3.3 giustifica `c ≥ 0` con la
crescita della KV cache: la stessa giustificazione implica il termine omesso. Non
è un motivo per aggiungerlo — P3.3 congela "Non si aggiungono `N_in²` o
`N_out²`" — ma è un motivo per scrivere che `c` assorbe una parte di un effetto
che ha anche una componente quadratica, e che il modello primario è
un'approssimazione dichiarata.

La quantificazione del revisore ("errore sotto lo 0,2% con un costo di contesto
realistico per un 3B su CPU, sotto il 4,5% con un costo 30 volte maggiore") è
**materiale non verificato**: è una sua simulazione, non riprodotta qui, e i suoi
parametri non sono dichiarati. Si cita come affermazione della revisione, non
come risultato.

---

## 3. Numeri della revisione riprodotti, e uno che non lo è

### 3.1 Semi-range con n = 3: i numeri si riproducono esattamente

Il revisore 2, par. 181, afferma: "in media vale 0,85σ contro un errore reale
della mediana di 0,67σ (simulato), ma nel 4,3% dei casi è sotto 0,2σ". Ricalcolo
eseguito oggi, 400.000 terne gaussiane, seed 20261024:

| grandezza | revisione | ricalcolo |
|---|---|---|
| `E[semi-range]` | 0,85 σ | **0,8468 σ** |
| `sd(mediana)` | 0,67 σ | **0,6693 σ** |
| `P(semi-range < 0,2 σ)` | 4,3% | **4,33%** |

Concordano. Aggiungo i percentili, che la revisione non dà: 1% = 0,095 σ,
5% = 0,215 σ, 50% = 0,795 σ, 95% = 1,656 σ. Quindi in media il semi-range è
conservativo di un fattore 1,27 rispetto all'errore della mediana, e nell'1% dei
blocchi è **otto volte** troppo piccolo.

### 3.2 La conseguenza sui pesi è più grave di quanto scriva la revisione

Il revisore 2 dice che "con `w_b = 1/budget²` quel blocco prende un peso enorme,
e il peso è calcolato dagli stessi dati che poi pesa". Vero, ma senza numero. Ho
simulato il fit reale — 33 blocchi, `budget_b² = u_base,b² + u_within,b²`,
`u_within` = semi-range di tre valori gaussiani, `u_base = ρ · u_within` — e ho
misurato la quota di peso totale detenuta dal blocco più pesante:

| `ρ = u_base/u_within` | quota media | mediana | p95 |
|---|---|---|---|
| 0,00 | 0,373 | 0,315 | 0,816 |
| 0,10 | 0,263 | 0,249 | 0,445 |
| 0,25 | 0,143 | 0,141 | 0,195 |
| 0,50 | 0,079 | 0,079 | 0,095 |
| 1,00 | 0,048 | 0,048 | 0,053 |

A `ρ = 0` un blocco su 33 porta il 37% del peso in media e l'82% nel 5% dei casi
peggiori: il fit sarebbe la media di un blocco solo. A `ρ ≥ 0,5` la
concentrazione è trascurabile. **La gravità del difetto dipende interamente da
`ρ`, che oggi non è misurato**: `u_base ≈ Δt̄_W · budget_base_w ≈ 3,6 s × 0,378 W
≈ 1,36 J` si può stimare, ma `u_within` — la dispersione delle tre `E_act` dentro
un blocco a geometria fissa — non è mai stata misurata, perché non esiste ancora
un blocco v4 con tre richieste. È esattamente ciò che produrrà il pilota (P6.2).

### 3.3 Il disegno: leve confermate, numeri di condizionamento no

Il revisore 2, par. 176, dichiara "numero di condizionamento 10 con 4 parametri,
19 con 5 e 33 con 6, leva massima 0,29". Ricalcolato oggi sul disegno di P3.5
(33 blocchi: griglia 3×3 con 3 per cella, centro a 6, minimo `(8,4)` a 3):

| parametri | cond. (predittori standardizzati) | cond. (grezzo) | leva max | leva media |
|---|---|---|---|---|
| 4 | 3,8 | 1,02e5 | 0,285 | 0,121 = p/n |
| 5 (+`N_out²`) | 9,0 | 1,41e5 | 0,294 | 0,152 |
| 6 (+`N_in²`) | 17,0 | 3,96e5 | 0,294 | 0,182 |

Le **leve si riproducono** (0,285 contro il loro 0,29; 0,121 = 4/33 esattamente).
I **numeri di condizionamento no**: 3,8/9,0/17,0 contro 10/19/33. La differenza
è tutta nella convenzione di scaling, che loro non dichiarano. La conclusione
qualitativa regge — l'ordine di grandezza cresce allo stesso modo e il disegno
resta identificabile con due termini in più — ma i loro numeri non sono citabili.

Il grezzo vale 1,02e5 perché la colonna `x12` arriva a 131.072 mentre
l'intercetta vale 1: valori singolari 2,65e5 / 8,79e2 / 6,06e2 / 2,59. Non è un
problema statistico, è un problema **numerico** di implementazione, e nessuna
delle due revisioni lo nota: il risolutore v4 deve centrare e scalare i
predittori o usare una decomposizione stabile, altrimenti si perdono circa
cinque cifre nel solve. Va in P5.

### 3.4 Il test di sottrazione è circolare: confermato, e peggio di come è scritto

Il revisore 2, par. 182: "La soglia è il budget della stessa baseline ... E
`half_drift` dentro il budget fa passare il test anche per un drift reale."

Verificato sul testo. La soglia per blocco è `budget_base_j,c = Δt_W ·
budget_base_w,c` e `budget_base_w,c = sqrt(half_range² + half_drift_c²)` con
`half_drift_c = |dP_c|/2` **del blocco di controllo stesso** (P1.7). L'energia
che il test confronta è `E_net,control,c ≈ (P̄_finestra − P_pre)·Δt_W`, cioè è
prodotta dallo stesso drift. Se il drift domina, numeratore e soglia crescono
insieme: **il test passa per effetto del fenomeno che dovrebbe rilevare**. La
circolarità è strutturale, non marginale.

Ne segue anche la potenza del gate, che è la parte utile dell'osservazione: la
soglia aggregata è `mediana_c(budget_base_w,c)`, quindi la risoluzione del gate è
fissata dall'instabilità osservata. Su una macchina con baseline 9,35–18,78 W e
CV 22,5% (`:345`) il budget può essere dell'ordine del watt, e il gate non
rileverebbe un bias di 1 W — che è appunto la scala che sposta `J/token` del
6–11% (`idle_floor_sensitivity_20261023_analisi.md` §2). Il revisore scrive "non
può rilevare un bias di ordine 1 W" come se fosse sempre vero; è vero **se** la
macchina è instabile, e il punto è proprio che la soglia non è indipendente da
questa instabilità.

---

## 4. Proposte che cambiano un punto congelato: decisione richiesta

### 4.1 Definizione di `E_trunc` (da §1.3)

Raccomandazione: **`|Σ_{i∈blocco} E_net_incremental,i`**, cioè `m · |Ē_b|`, e
analogamente per `r_B` sul punto.

Motivi: è l'unica delle tre coerente con "nessun troncamento" (P1.3, F.2); è la
grandezza che entra davvero nel fit, perché F.7 stima su `Ē_b`; rende `r_A ≥ 0`
sempre, quindi il filtro `≤ 10%` non diventa cieco; e mantiene la regola già
congelata "denominatore zero → blocco invalido", che ora ha un senso preciso: un
blocco la cui energia netta media è zero non porta informazione e il drift non è
valutabile in rapporto a nulla. Va rinominato `E_trunc` → il simbolo corretto, e
aggiunto alla Terminologia.

### 4.2 Metrica di stabilità dei controlli (da §1.1)

Tre opzioni:

- **A.** Sostituire il filtro `r_A ≤ 10%` sui controlli con soglie **assolute**
  già congelate: `pre_range_w,c ≤ 1,0 W` e `|dP_c| ≤ 1,0 W`, cioè i due flag di
  P1.6 con la soglia di 1,0 W che ha già la sua motivazione misurata. Nessun
  numero nuovo, nessuna metrica nuova, e il criterio per blocco di P4.5
  (`|E_net,control,c| ≤ budget_base_j,c`) resta invariato.
- **B.** Definire una metrica nuova per i controlli, per esempio
  `r_ctrl = |dP_c| · Δt_W,c / E_rif,c` con `E_rif,c` preso dal blocco di carico
  della stessa coppia. Non è circolare ma accoppia i due blocchi, e introduce un
  simbolo e una soglia nuovi.
- **C.** Eliminare il filtro sui controlli e dichiarare che tutti e tre entrano
  nel `bias_w` aggregato. Il più semplice, ma perde la protezione contro un
  controllo con baseline impazzita.

Raccomandazione: **A**. È la sola che non aggiunge numeri dopo aver visto il
disegno, e il requisito 7 di P4.4 va corretto elencando le quantità che esistono
davvero su un controllo.

### 4.3 `u_bias` nella formula (da §1.2)

Due interpretazioni non equivalenti, come dice il revisore:

- **contributo di incertezza**: `budget_pred_b² = budget_fit_b² + u_edge,b² +
  u_bias,b²` con `u_bias,b = |bias_w| · Δt̄_W,b`, e `u_bias = 0` se il gate
  passa. Coerente con la convenzione in quadratura già usata, e con il fatto che
  `bias_w` è dichiarato col suo segno ma non sottratto;
- **correzione sistematica**: si sottrae `bias_w · Δt_W` da `E_net` e si
  propaga l'incertezza della correzione. Cambia i dati, non solo gli intervalli,
  e contraddice P4.5 ("il bias è dichiarato nella tesi con il suo segno, e P1 non
  si cambia").

Raccomandazione: la **prima**, che è ciò che il testo descrive già a parole. Va
scritta nella formula di P4.6 e in F.11, con `Δt̄_W,b` esplicito. Nota: se la
forma di combinazione di P1.7 dovesse cambiare in somma aritmetica, anche questo
termine segue la stessa sorte — va deciso insieme (task #43).

### 4.4 Copertura su token reali (da §1.4)

Raccomandazione: `coverage_tier` e `hull_margin_tok` si calcolano su
`(x1_b, x2_b)` di F.7, cioè le medie di blocco dei token **reali**; l'inviluppo
resta quello dei punti di disegno, perché è il disegno a definire il supporto.
I margini già pubblicati (1,33 / 64,0 / 21,2 / 107,7) restano validi come
**margini di progetto**, etichettati come tali, e vanno ricalcolati sui reali a
dati raccolti. Conseguenza da accettare: la fascia di un punto può cambiare dopo
la misura, e questo va dichiarato prima, non scoperto dopo.

### 4.5 Lack-of-fit con pesi non di precisione

Il revisore 2, par. 183: l'F-test pesato presume pesi uguali all'inverso della
varianza; con budget conservativi la distribuzione di riferimento non è esatta,
e `p ≥ 0,05` premia la bassa potenza. **Corretto**: P3.8 dichiara che `w_b` è
"un peso conservativo, non un peso di precisione", e P4.9 anello 5 usa comunque
`p ≥ 0,05` come criterio. Opzioni: test di permutazione sulla statistica F;
oppure scarto massimo relativo fra medie di cella e superficie con soglia
predeclarata; oppure mantenere l'F-test dichiarando che il `p` è indicativo.
L'anello 5 è congelato: decisione richiesta.

### 4.6 Bootstrap: correzione di leva e validazione di copertura

Il revisore 1 chiede di trattare il bootstrap come metodo da diagnosticare, non
come garanzia di copertura al 95%; il revisore 2 propone un wild bootstrap con
residui corretti per la leva, `r/√(1−h)`, citando leva media 0,12. Con la leva
massima verificata a 0,285 il fattore correttivo più grande è
`1/√(1−0,285) = 1,18`: un allargamento del 18% sul blocco più influente, non
trascurabile ma non decisivo. Entrambe le osservazioni sono di **interpretazione**
più che di procedura: la modifica minima è dichiarare che la copertura nominale
non è garantita e che va verificata per simulazione (§5.2).

### 4.7 Potenza del test di sottrazione

Il revisore 2 propone 6–8 controlli invece di 3, un intervallo t sul bias medio e
un test di equivalenza con margine espresso in effetto su `J/token` (±3–5%)
invece che in watt. La diagnosi (§3.4) è confermata; la cura tocca P4.4
congelato ("tre coppie") e le soglie congelate. Costo quantificabile: 6 blocchi
in più sono 18 min di finestre idle (P6.1) più le richieste e i settling. Il
margine in `J/token` invece che in watt ha un vantaggio reale: è espresso nella
stessa unità della metrica pubblicata, e la scala di conversione è già ancorata
(1 W ≈ 6–11% di `J/token`). Decisione richiesta.

---

## 5. Proposte di esecuzione: valide, vanno in P6

### 5.1 Audit idle di 30 minuti prima della campagna

Revisore 2, par. 190. Il rischio è ancorato: baseline post-fix 9,35–18,78 W,
CV 22,5%, `dP` −9,31…+5,80 W (`:345`). Se la macchina non è stazionaria a
riposo, i flag `r_A` invalidano la campagna **dopo** averla eseguita. Un audit
idle di 30 minuti — processi in background, piano energetico, aggiornamenti,
antivirus — costa mezz'ora e sposta la scoperta da dopo a prima. Da aggiungere
come requisito di esecuzione.

### 5.2 Simulazione Monte Carlo del protocollo

Revisore 2, par. 188 e 192. Superficie nota, rumore idle e deriva campionati
dalle distribuzioni misurate, 39 blocchi, e si osservano: bias dei coefficienti,
copertura reale degli intervalli, probabilità di falso fallimento dei gate. È il
controllo più economico disponibile e arbitra **quattro** punti aperti in una
volta sola: la concentrazione dei pesi (§3.2), la potenza e la circolarità del
gate (§3.4), il fattore 2 sull'intervallo di conferma (§2.3), la forma di
combinazione di P1.7 (task #43). Non è codice di produzione: è un harness di
analisi, quindi non viola il blocco del sorgente, ma la precedenza la decide
l'utente.

### 5.3 Lettura sincrona del contatore ai bordi di finestra

Revisore 2, par. 180. Verificato sul codice: oggi i bordi passano da
`_emi_cum_at`, che interpola su un buffer campionato a 0,28–0,34 s misurati. Una
lettura diretta del contatore all'istante di bordo, col suo timestamp, elimina il
termine di disallineamento (§2.1) e riduce `u_edge` di circa un fattore 6, come
già dice P4.6 citando il probe a 50 ms. È una modifica del runner, quindi è
materiale di P5; l'evidenza che la rende possibile esiste già
(`emi_50ms_probe_20261023_*`).

---

## 6. Respinte, con motivo

- **"Specificare come sono gestite le repliche non stimabili"** (revisore 1,
  par. 104). Non applicabile al bootstrap congelato: P4.8 ricampiona i residui,
  non i blocchi, e rifitta "con gli stessi pesi `w_b`". Il disegno `X` è fisso e
  la matrice `X'WX` è la stessa in ogni replica. Verificato oggi: rango 4 su 33
  righe, cioè pieno. Non esiste replica non stimabile, a meno che il disegno di
  P3.5 sia singolare, e non lo è.
- **"Portare il punto `(12,32)` nel fit"** (revisore 2, par. 185). Distruggerebbe
  la validazione: P3.10 esiste perché i due punti di conferma sono esclusi dalla
  stima. Il problema del supporto sottile è reale ma è già gestito —
  `hull_margin_tok` obbligatorio e `thin_support` sotto 2 token (P4.7). L'altra
  metà della proposta, livelli distribuiti in scala logaritmica con un livello
  vicino all'operatività, è disegno di v5.
- **"3,75 J invece di 10,5 J"** come valore di `u_edge` (revisore 2, par. 180).
  La matematica è giusta (§2.1) ma il numero è il caso peggiore di un termine
  solo, con un `ΔP` entro il tick assunto a 25 W e non misurato. Non sostituisce
  il valore congelato; semmai si aggiunge.
- **Passare alla somma aritmetica dei semi-range** (revisore 1, par. 64-67;
  revisore 2, par. 181). È la decisione già rinviata ai dati del pilota P2.9
  dall'utente il 24-10-2026 (P1.7, P1.13, task #43). Le due revisioni la
  sollevano indipendentemente e il revisore 1 preferisce la somma: questo
  **corrobora** il rinvio, non lo riapre. Nessun cambiamento oggi.

---

## 7. Riepilogo operativo

| # | oggetto | stato | dove |
|---|---|---|---|
| 1.1 | `r_A` sui controlli | contraddizione reale | decisione §4.2 |
| 1.2 | `u_bias` fuori dalla formula | contraddizione reale | decisione §4.3 |
| 1.3 | `E_trunc` non definito | contraddizione reale | decisione §4.1 |
| 1.4 | copertura su target, fit su actual | contraddizione reale | decisione §4.4 |
| 2.1 | giustificazione di `u_edge` | sbagliata, valore salvo | forma + decisione sul termine aggiuntivo |
| 2.2 | `E_pred ≤ 0` | lacuna | forma, applicabile |
| 2.3 | "intervallo al 95%" | etichetta sbagliata | forma, applicabile |
| 2.4 | `a`, `b` marginali a zero | ambiguità | forma, applicabile |
| 2.5 | sostituzioni per cella | lacuna | forma, applicabile |
| 2.6 | pre-pilota sui livelli bassi | lacuna di P3.15 | forma, applicabile |
| 2.7 | termine `N_out²` omesso | algebra corretta | forma, applicabile |
| 3.1 | numeri sul semi-range | riprodotti | §3.1 |
| 3.2 | concentrazione dei pesi | quantificata qui per la prima volta | §3.2, P6.2 |
| 3.3 | condizionamento e leve | leve sì, cond. no; cond. grezzo 1,0e5 | P5, nota numerica |
| 3.4 | circolarità del gate | confermata e rafforzata | decisione §4.7 |
| 4.5 | lack-of-fit pesato | critica corretta | decisione |
| 4.6 | bootstrap e leva | fattore max 1,18 | decisione |
| 5.1 | audit idle 30 min | valido | P6 |
| 5.2 | Monte Carlo del protocollo | valido, arbitra 4 punti | P6 |
| 5.3 | lettura sincrona ai bordi | valido, codice verificato | P5 |
| 6 | quattro proposte | respinte con motivo | §6 |

Verifiche eseguite oggi su codice e numeri, tutte riproducibili: rango e leve del
disegno di P3.5, errori di interpolazione e di disallineamento su un tick di
0,30 s, distribuzione del semi-range su 400.000 terne, concentrazione dei pesi su
33 blocchi al variare di `ρ`, lettura di `_emi_cum_at` e `_emi_field_at`
(`energy_session.py:1103-1149`), `grep` delle occorrenze di `E_trunc` e
`u_bias`. Nessun file di produzione è stato modificato.

---

## 8. Esito: tutte le voci chiuse il 2026-10-24

Aggiunto a chiusura del ciclo. Le decisioni sono nel protocollo, non qui: questa
sezione serve solo a dire **dove** è finita ciascuna voce, perché la tabella del §7
le elencava come "decisione richiesta" e oggi non ne resta nessuna aperta. Un commit
per punto, come da regole del repository.

| voce | esito | commit |
|---|---|---|
| 1.3 / 4.1 `E_trunc` | chiuso: `E_net_abs,b = m · \|Ē_b\|`, nome ritirato | `faae5f1` |
| 1.1 / 4.2 `r_A` sui controlli | chiuso: filtro assoluto `pre_range_w,c ≤ 1,0 W` e `\|dP_c\| ≤ 1,0 W`, flag `control_unstable` | `0b2626a` |
| 1.2 / 4.3 `u_bias` | chiuso: `u_bias,b = \|bias_w\| · Δt̄_W,b` in formula, contributo di incertezza | `5951908` |
| 1.4 / 4.4 copertura | chiuso **oltre** la raccomandazione: due inviluppi, ciascuno nella propria base | `18c08a8` |
| 4.5 lack-of-fit pesato | chiuso: `p_lof_perm` da ricampionamento del puro errore, statistica e soglia 0,05 invariate | `71664e4` |
| 4.6 bootstrap e leva | chiuso: copertura dichiarata nominale e non arbitrata fino a P6.4; `1/√(1 − h_b)` come sensibilità obbligatoria, fattore massimo 1,1828 | `b3eeaed` |
| 3.4 / 4.7 potenza del gate | chiuso: sei coppie, quorum `⌈2/3 · n⌉ = 4`, `bias_jtok_pct` riportato; intervallo t e test di equivalenza non adottati, con il limite dichiarato | `9dde1d1` |
| 2.1 / 5.3 termine di bordo | chiuso: via (b) adottata come requisito vincolante di P5, via (a) scartata; `Δt_W` dalla stessa coppia di letture | `81f4381` |
| 5.1 audit idle | adottato come requisito vincolante (P6.3) | `81f4381` |
| 5.2 Monte Carlo | adottato come requisito vincolante (P6.4), con precedenza: dopo P5, prima della pubblicazione degli intervalli | `81f4381` |
| 2.2, 2.3, 2.5 | applicate come correzioni di forma in P3.10, P3.12, P3.13 | `e00de6a` |
| 2.4, 2.7 | applicate come aggiunte redazionali in P3.3, formulario allineato in F.8 | `7066e4e`, `ba01462` |
| 2.6 | applicata: il pre-pilota di P3.15 prova anche i livelli bassi | `7826e9f` |
| 2.1 forma | giustificazione di `u_edge` rettificata, formula e valore invariati | `09ecdce`, `ba01462` |
| 3.2 concentrazione dei pesi | rinviata a P6.4 punto 1: `ρ` non è misurabile prima di un blocco v4 | `481eeea`, `81f4381` |
| 3.3 condizionamento | requisito di P5: predittori centrati e scalati | `481eeea` |
| 6 respinte | restano respinte; la somma aritmetica dei semi-range resta rinviata ai dati del pilota P2.9 (task #43), e il rinvio è corroborato, non riaperto | — |

Due avvertenze per chi legge il protocollo dopo questa tabella. La prima: P6 non è
più una sezione senza decisioni, e il suo preambolo lo dichiara. La seconda: le
emende ai punti congelati sono **quattro** per P4 e una per P1 e P3, tutte elencate
nella tabella di stato in testa al protocollo; nessuna formula congelata è stata
riscritta in silenzio. Una rettifica a questo stesso documento: il §7 scrive che la
simulazione Monte Carlo "arbitra 4 punti"; con la copertura del bootstrap aggiunta
in P4.8 i punti sono **cinque** (P6.4).
