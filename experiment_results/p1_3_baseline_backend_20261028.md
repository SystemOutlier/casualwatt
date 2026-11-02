# P1.3 `baseline_backend` — che cosa deve descrivere, dove va

Data: 2026-10-28. Ambito: audit del percorso reale della baseline e del
contratto CSV. **Nessuna riga di codice toccata, nessuna colonna aggiunta,
nessuna soglia o formula modificata, nessun run eseguito, nessun test
rieseguito** (non c'e' modifica di codice da verificare). Questo documento
risponde alla domanda di Fase A: dove va il campo e quale comportamento deve
descrivere. Non lo aggiunge.

Fonti verificate oggi: protocollo P1.3 (`:191-205`), `AGENTS.md:97`,
`metodi_per_dominio_20261025_spec.md:192`, e il codice di `cwEnergyModular/`.

---

## 1. Il requisito

P1.3 `:203-205`:

> Dominio: PKG, lo stesso di `E_pkg_gross`. Backend: lo stesso della misura
> della richiesta; su questo host `emi-counter`. Se si usa il fallback, si
> registra `baseline_backend` e l'incertezza di bordo del backend.

Due obblighi distinti, non uno:

1. **lo stesso backend** della richiesta — un vincolo, verificabile;
2. **registrare il backend e la sua incertezza di bordo** — due campi, di cui
   oggi il codice non ne produce nessuno con quel nome.

`baseline_backend` non esiste nel codice: le sole occorrenze nel repository
sono il protocollo (`:205`), la specifica per dominio (`:192`, che lo dichiara
"campo di P1.3, non ancora nel codice") e `AGENTS.md:97`. Nessuna in `.py`.

---

## 2. Dove nasce la baseline, nel codice attuale

Il runner v4 chiama la calibrazione **due volte per blocco**, prima e dopo le
`m` richieste:

| punto | riga | cosa succede |
|---|---|---|
| pre | `benchmark_v4.py:1411-1413` | `settle_idle()` poi `calibrate_idle()` |
| post | `benchmark_v4.py:1596-1598` | idem, dopo l'ultima richiesta |

`calibrate_idle` (`energy_session.py:1362-1459`):

- guard sul metodo (`:1394`) — ammessi `rapl`, `emi-counter`, `pawnio-counter`;
- 3 ripetizioni (`:1415-1447`), ognuna una `read_idle_window_j(duration_s)`;
- mediana (`:1448`);
- `self._idle_mode = mode_used` (`:1449`), `self._idle_reps` (`:1450`);
- `self.idle_provenance = "calibrated"` (`:1457`).

Ogni ripetizione passa da `read_idle_window_j` (`energy_session.py:660-692`),
che ritorna `(delta_j, dt_real, mode)`; il `mode` e' calcolato a `:685-688`. La
corrispondenza fra `mode` e backend reale:

| `_idle_mode` | backend che ha prodotto il numero | dove |
|---|---|---|
| `emi-counter` | `emi-counter` | `energy_session.py:640-641` |
| `pawnio-counter` | `pawnio-counter` (fallback dichiarato) | `:642-644` |
| `rapl-counter` | `rapl` | `:674-675`, `rapl_backend.py:270-296` |
| `energy-counter` | `energy-file` (`CW_ENERGY_FILE`, DEV/TEST) | `:649-654`, `:685-688` |

L'unico token il cui nome non coincide col backend e' `energy-counter`: e'
l'override da file. La mappatura e' quindi il primo contenuto che
`baseline_backend` deve avere — il valore del campo non e' `_idle_mode` grezzo,
e' il token di backend.

---

## 3. Che cosa il codice sa gia' e non pubblica

**Il modo di acquisizione e' misurato e poi perso.** `_idle_mode` viene
assegnato (`:1449`) e non finisce in nessuna colonna: nel runner unificato
compare solo in una riga di log (`benchmark_unified.py:846`); il runner v4
registra `P_pre`, le repliche e il settling (`benchmark_v4.py:1447-1448`) ma
non il modo.

**Trappola d'ordine.** `_idle_mode` e' sovrascritto dalla calibrazione post
(`:1449` richiamato da `:1598`). Letto al momento di comporre il riepilogo
(`benchmark_v4.py:1657-1699`) restituirebbe il modo **post** anche per il pre.
Il valore pre va catturato subito dopo `:1413`, prima che parta il blocco.

**`idle_provenance` non distingue il canale.** E' per riga
(`local_energy.py:366`, `:389`; colonna in `casualwatt_csv_export.py:67`). Nel
v4 puo' valere solo `calibrated`: il ramo `uncalibrated`
(`local_energy.py:377-387`) non e' raggiungibile, perche' `calibrate_idle`
solleva invece di tornare `None` (`energy_session.py:1394-1403`, `:1427-1433`)
e il runner traduce l'eccezione in guasto o stop (`benchmark_v4.py:1414-1420`,
`:1599-1608`). Su una riga v4 `idle_provenance` dice dunque "la baseline
esiste", non "su quale canale".

**`energy_calculation_method` descrive la richiesta, non la baseline.** E'
per riga (`local_energy.py:391-398`; colonna a `casualwatt_csv_export.py:102`)
e dice da dove viene `package_energy_j` di quella riga. Il canale della
sessione e' fissato alla selezione e non cambia a meta' run: tutte le
assegnazioni di `self.method` stanno in `energy_session.py:110`, `:158`,
`:178`, `:215`, `:242`, `:246`, `:250`, `:254`, `:548`, cioe' init o
selezione. Conseguenza: **oggi `baseline_backend == energy_calculation_method`
per costruzione**, tranne il caso dell'override da file (§6.1). Il campo non
aggiunge informazione finche' la catena non degrada a meta' sessione; aggiunge
la possibilita' di *dimostrarlo* invece di dedurlo.

---

## 4. Dove va il campo

Due collocazioni possibili, entrambe dentro uno schema congelato.

**(a) Riepilogo di blocco** — `BLOCK_SUMMARY_COLUMNS`,
`casualwatt_csv_export.py:208-223` (36 colonne). La baseline e' una grandezza
di blocco (tre repliche pre e tre post, P1.5/P1.3); il riepilogo porta gia'
`baseline_pre_w`, `baseline_post_w`, `pre_windows_w`, `post_windows_w`
(`:212`). Il valore e' costante dentro il blocco.

**(b) Riga grezza** — `CSV_COLUMNS`, `casualwatt_csv_export.py:17-200` (172
colonne contate dal decimo emendamento). Rende la riga auto-descrittiva se
righe di run diversi vengono accodate; ripete lo stesso valore su ogni riga
del blocco, mentre il riepilogo e' scritto insieme alle righe.

**Raccomandazione: (a)**, un solo campo nel riepilogo. Motivi: la baseline e'
per blocco e non per richiesta, il riepilogo e' la sede naturale delle
grandezze di blocco, e lo schema largo delle righe e' quello che costa di piu'
allungare. Pre e post sono due terne distinte: se i due modi coincidono il
campo si scrive; se differiscono (oggi impossibile, la catena non cambia fra
`:1413` e `:1598`) il campo resta **vuoto** e la differenza va in una
deviazione dichiarata, non in un token composito da parsare.

**Il livello non e' una scelta di codice.** Sia le 172 colonne delle righe sia
le 36 del riepilogo sono congelate da P5 (2026-10-26) e riconteggiate dal
decimo emendamento (2026-10-28). Aggiungere `baseline_backend` e' un
**emendamento**, e l'emendamento e' il commit in cui la colonna nasce. Non
esiste un commit di codice che aggiunga la colonna prima dell'emendamento, e
non si aggiorna un conteggio a mano: si rigenera dalla fonte.

---

## 5. "L'incertezza di bordo del backend" per la baseline non esiste

Sul lato **richiesta** il bordo e' misurato:
`read_measurement_edge` (`energy_session.py:916-955`) legge il contatore e poi
le grandezze CPU e ritorna `edge_spread_s = t_after - t_before` (`:954`);
`local_energy.py:345-348` ne prende il massimo dei due bordi; la colonna e'
`edge_spread_s` (`casualwatt_csv_export.py:142`).

Sul lato **baseline** no. `read_idle_window_j` (`energy_session.py:660-692`)
ritorna `(delta_j, dt_real, mode)` e nient'altro: `e_start` ed `e_end` vengono
da `read_power_j` (`:639-658`), ognuna con un solo timestamp monotono, e `dt`
e' misurato intorno al `sleep` (`:679-683`). Lo scarto fra la lettura del
contatore e la seconda lettura del bordo — la grandezza che P1.3 chiama
"incertezza di bordo del backend" — non viene conservato. Lo stesso vale nel
backend RAPL (`rapl_backend.py:270-299`, stessa terna).

Tre strade, con costi diversi:

1. **restituire anche il bordo** da `read_idle_window_j` (quarta voce della
   tupla o dizionario): tocca la firma, quindi `calibrate_idle`
   (`:1421`), il backend RAPL (`rapl_backend.py:270`), i test che montano
   finestre finte. E' una modifica al percorso di misura: commit proprio, suite
   intera incollata;
2. **un limite dichiarato a livello di blocco** ricavato dalla risoluzione del
   contatore: non tocca il percorso, ma e' un modello, non una misura, e va
   etichettato come tale;
3. **cella vuota e dichiarazione "non acquisito"**: onesto rispetto al dato,
   ma P1.3 resta non soddisfatto.

**Non sostituire `pre_range_w` al bordo del backend.** Sono grandezze diverse:
`pre_range_w` e' la dispersione fra le tre repliche (`max - min`,
`benchmark_v4.py:685-759`) e descrive la macchina; il bordo descrive il costo
di lettura del canale ai due estremi della finestra. Il pilota usa la prima per
`half_range_pre_w`; P1.3 chiede la seconda.

---

## 6. Due riscontri da decidere, non da correggere qui

**6.1 `energy-file` contro il guard di calibrazione.** `calibrate_idle`
ammette solo `rapl`, `emi-counter`, `pawnio-counter` (`:1394`), mentre
`read_idle_window_j` supporta l'override da file (`:649-654`, `:685-688`).
Conseguenza misurata sul codice: con `CW_ENERGY_FILE` impostato il v4 si ferma
al primo blocco. Il messaggio del guard non contiene "contatore decrescente",
quindi `classify_calibration_exception` (`benchmark_v4.py:202-217`) ritorna
`None` e l'eccezione diventa `V4MeasurementError` (`:1414-1420`, `:1599-1608`)
— stop del run, non sostituzione del blocco. Due letture possibili, entrambe
decisioni: il guard e' la regola "il v4 non gira sull'override DEV/TEST", e
allora va scritto; oppure e' un buco, e chiuderlo tocca il percorso di misura.
In nessuno dei due casi P1.3 ("backend: lo stesso della misura della
richiesta") e' oggi soddisfacibile sotto override.

**6.2 Vocabolario di `idle_provenance`.** Il commento a
`local_energy.py:139` elenca `calibrated|session|uncalibrated`, ma `session`
non e' assegnato da nessuna riga, mentre la GUI assegna `manual_override`
(`benchmark_panel.py:561`), che il commento non elenca. Il dato e' corretto
(la colonna porta cio' che e' stato assegnato); e' il commento a essere
stantio. Va corretto in un commit di commenti, non in questo.

---

## 7. Cosa serve per procedere

Nell'ordine, come per il pilota:

1. **decisione sul livello** (riepilogo di blocco, raccomandato, oppure riga
   grezza) e **emendamento P5** che aggiunge la colonna e riconteggia;
2. **decisione sull'incertezza di bordo** (§5, strada 1/2/3);
3. **decisione su `energy-file`** (§6.1);
4. solo dopo: implementazione, con un commit per punto e la suite intera
   incollata.

Nessuno dei quattro passi e' stato compiuto in questo turno, e nessuno dei
tre documenti di preparazione (questo, `p6_preparazione_pilota_20261028.md`,
`p1_7_forma_budget_base_20261028.md`) autorizza un run.

---

## 8. Ancore verificate il 2026-10-28

| affermazione | ancora |
|---|---|
| requisito P1.3 su backend e incertezza di bordo | `protocollo_v4_20261024.md:203-205` |
| `baseline_backend` assente dal codice | grep su `*.py`: zero occorrenze |
| il v4 calibra pre e post per blocco | `benchmark_v4.py:1411-1413`, `:1596-1598` |
| guard sui metodi ammessi | `energy_session.py:1394` |
| tre repliche, mediana, modo | `energy_session.py:1415-1457` |
| modo di acquisizione delle finestre | `energy_session.py:660-692`, `:685-688` |
| modo RAPL | `rapl_backend.py:270-299` |
| modo pubblicato solo in un log | `benchmark_unified.py:846` |
| `_idle_mode` sovrascritto dal post | `energy_session.py:1449` richiamato da `benchmark_v4.py:1598` |
| `idle_provenance` per riga | `local_energy.py:366`, `:389`; `casualwatt_csv_export.py:67` |
| canale di richiesta per riga | `local_energy.py:391-398`; `casualwatt_csv_export.py:102` |
| nessun cambio di canale a meta' sessione | assegnazioni a `energy_session.py:110`, `:158`, `:178`, `:215`, `:242`, `:246`, `:250`, `:254`, `:548` |
| riepilogo di blocco, 36 colonne | `casualwatt_csv_export.py:208-223` |
| 172 colonne di riga | `casualwatt_csv_export.py:17-200` |
| bordo misurato solo sulle richieste | `energy_session.py:916-955`; `local_energy.py:345-348`; `casualwatt_csv_export.py:142` |
| classificazione delle eccezioni di calibrazione | `benchmark_v4.py:202-217` |
| vocabolario stantio nel commento | `local_energy.py:139`; `benchmark_panel.py:561` |

### Ancore stantie trovate nello stesso giro (non corrette qui)

Sono commenti e docstring di codice, non testo congelato, ma citano posizioni
che il file non ha piu': `energy_session.py` ha 1800 righe.

| citazione | cosa dichiara | posizione reale |
|---|---|---|
| `benchmark_v4.py:119`, `:206`, `:208`, `:1427` → `energy_session.py:2548-2553`, `:2561-2563`, `:2547-2566` | guard di calibrazione e raise per contatore decrescente | `:1394-1403` e `:1436-1439` |
| `benchmark_v4.py:206-212` → `energy_session.py:1079-1083` | manifestazione del reset | `:1079-1083` e' `stop()`; il reset e' trattato a `:319-325` |
| `tests/test_baseline_ordine_v4.py:39`, `tests/test_emenda8_sostituzione.py:218`, `:262` | le stesse tre posizioni | come sopra |
