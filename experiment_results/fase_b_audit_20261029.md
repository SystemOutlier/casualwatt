# Fase B — audit del registro R1-R13 contro codice e artefatti

Data: 2026-10-29. **Stato: audit. Nessuna riga di codice, schema, runner o
protocollo modificata; nessun run; nessun `pytest` rieseguito; nessun push,
nessun branch.** Oggetto: `experiment_results/fase_b_registro_decisioni_20261028.md`
(commit `a8a8d28`). Questo documento non lo sostituisce: dice cosa e' verificato,
cosa non lo e', e in quali punti il registro e' impreciso.

---

## 0. Metodo, cosa e' stato eseguito, limiti

Regola applicata: una conclusione vale solo se ancorata a `file:riga` riletto
oggi, a un artefatto tracciato, o a un comando rieseguito. Cio' che e'
documentato ma non verificabile e' segnalato come tale, non accettato.

**Eseguito in questo turno.** Un solo comando che tocca il codice, offline
(nessun `powercfg`, nessun accesso all'hardware), per verificare una cifra che
un documento di preparazione dichiara:

```
$ python s_epi_phase.py --selftest
[selftest OK] 66 controlli; nessun run, nessun powercfg, nessun accesso all'hardware
```

**Non eseguito.** `pytest cwEnergyModular` non e' stato rieseguito: non e' stata
modificata una riga di codice, quindi il conteggio di riferimento resta quello
di `AGENTS.md` (526 raccolti = 523 passati + 3 saltati), che questo audit
**non** ha rigenerato. Nessun run sperimentale, nessuna sonda hardware, nessuna
lettura del contatore EMI o PawnIO.

**Non verificabile da questo audit** (elencato qui, non nascosto):

- le cifre di costo del disegno R4 (`≈ 2 h 30`, `≈ 3 h`) sono aritmetica su
  tempi dichiarati, non tempi misurati (`p6_6_prepilota_20261025.md:96-128`,
  `:424-427`);
- l'ancora A1 di R1 dipende da `budget_pred`, che non esiste prima del pilota
  P6.2 (`p6_6_prepilota_20261025.md:313-325`): oggi non e' valutabile, solo
  dichiarabile;
- tutto cio' che richiede hardware: W1, catene GPU su scheda reale, D15
  multi-socket Windows, dataset G0 (§6).

---

## 1. Le tredici voci nelle cinque classi richieste

Legenda: **C** = gia' congelato dal protocollo; **A** = ancora da approvare;
**I** = implementato; **IN** = implementato ma non collegato al percorso di
produzione; **M** = mancante o non testato.

| id | C | A | I | IN | M | prova del livello raggiunto |
|---|---|---|---|---|---|---|
| R1 banda `B_abs` | no, P6.6 la impone ma il valore e' aperto (`:2608-2615`) | si' | — | — | si' | nessun produttore di banda; `s_epi_phase.py:_load_plan` accetta solo banda gia' nel piano, altrimenti `in_band = null` |
| R2 forma relativa | P6.6 chiede forma "assoluta e relativa" (`:2608-2611`), non fissa la formula | si', la forma e il denominatore di `B_rel` | si', la simmetrica, nell'harness | — | si' fuori dall'harness | `s_epi_phase.py:350-354`; nessun altro modulo |
| R3 aggregazione | no | si' | solo i conteggi | — | si' | `s_epi_phase.py:464-500` conta `in_band: (k, n)`; mancano verdetto congiuntivo, `d_agg`/`r_agg`, sensibilita' di bordo |
| R4 `C`, `R`, `T` | no | si' | no | — | si' | l'harness non impone `C/R/T` ne' legge un campo `study` |
| R5 `engine_tree_changed` | P6.6 lascia due alternative (`:2624-2635`) | si', ratifica dell'esclusione | si', riga e fase | — | si' (nessun test pytest della fase) | runner `benchmark_v4.py:1490`, `:1518` (`bool(wd.lost)`); harness lo tratta come bloccante di fase (`s_epi_phase.py:284-291`) |
| R6 worker nati | definizione letterale in P6.6 (`:2624-2630`) | si', semantica e sensibilita' | conteggio dal grezzo | — | si' | `energy/worker_tree.py:197` conta il nato da zero; nessuna diagnostica, nessun ramo di sensibilita' |
| R7 `u_within` | formula congelata (P3.8 `:1063-1068`) | si', il produttore | no | — | si' | grep: solo docstring `benchmark_v4.py:712` e sonda simulata; `budget_fit_j` lasciato `""` (`:1684`) |
| R8 ammissibilita' | soglie congelate (P1.6, Emenda 8) | si', il gate unico per il fit | meta' scrittura | si', `partition_block_rows` | si', `r_A`/`r_B` e peso ridotto | `benchmark_v4.py:260-421` senza chiamante di produzione; solo `tests/test_filtro_p6_invalidati.py` (15 test) |
| R9 chiusura P1.7 | deciso dall'Emenda 8 (`:3478-3504`) | si', la clausola di sostituzione | no | — | si' | sei testi e due punti di codice dicono ancora il rinvio (F1) |
| R10 ambiente dichiarato | P1.3 `:193-205` (30 s espliciti) | si' | il floor esiste di fatto | — | si', dichiarazione e guardia | `energy_session.py:1380-1389`, `config.py:331` |
| R11 `baseline_backend` | requisito in P1.3 `:203-205` | si', livello e vocabolario | no | — | si' | zero occorrenze in `cwEnergyModular/`; `_idle_mode` sovrascritto dalla post (`:1449`) |
| R12 token D11 | direzione decisa nella specifica metodi `:1186-1199` | si' | no | — | si' | nessun campo; `probes/` senza `__init__.py` verificato oggi |
| R13 guardia `CW_ENERGY_FILE` | no | si' | il rifiuto attuale | — | si', il test che lo fissa | `energy_session.py:1394-1403`; nessun test del rifiuto |

### 1.2 Cosa blocca cosa

Il registro distingue, nella colonna "blocca" (`:43-57`), il run del pilota dal
run confermativo P6.6. L'audit conferma la distinzione e la rende esplicita,
perche' "pronto per il pilota" e "pronto per P6.6" non sono lo stesso stato.

| id | blocca il run P2.9 | blocca l'analisi del pilota | blocca il run P6.6 | blocca la campagna | dipende da | test mancanti |
|---|---|---|---|---|---|---|
| R1 | no | si' (banda usata nel confronto) | si' | si' se resta aperta | R4, dati P6.2 se A1 | validazione del piano; nessun default di banda |
| R2 | no | si' | si' | si' | R1 (denominatore) | caso `s+s_EPI = 0`, `s = s_EPI = 0` |
| R3 | no | si' | si' | si' | R1, R2 | verdetto congiuntivo per configurazione; `d_agg`; fasi di bordo escluse dalla sensibilita' |
| R4 | no | no | si' | si' | R1 (la banda condiziona `R`) | piano rifiutato se `C`/`R`/`T` incoerenti o assenti |
| R5 | no | si' (quali fasi entrano) | si' | si' | — | fase con flag → bloccante; assenza di `done_reason` atteso |
| R6 | no | si' (quali fasi entrano) | si' | si' | R5 | nato presente → diagnostica e ramo di sensibilita' |
| R7 | **si'** (P6.2 lo richiede, `:2376-2382`) | si' | si' | si' | R8 | semi-range su grezzo firmato; `m_valide = 2`; blocco invalido → vuoto; nessuna divisione per `√m` |
| R8 | no per il run, si' per l'analisi | si' | si' | si' | — | `r_A`/`r_B` calcolati; confini 10/20/5%; `abs(dP_c) = 1,0 W` incluso; quorum 4/6 |
| R9 | no | no | no | **si'** | nessuno (documento) | nessuno: e' un documento, la verifica e' la rilettura |
| R10 | **si'** (ambiente non dichiarato = dato non interpretabile) | si' | si' | si' | decisione (i)/(ii)/(iii) | floor 30/10/45; rifiuto della guardia, solo v4 |
| R11 | **si'** (P1.3 lo richiede) | si' | si' | si' | emendamento P5 | mappatura dei quattro token; pre non sovrascritta; repliche discordi; invarianza |
| R12 | no | no | no | no | R12 (non usato da G0 nel pilota) | sette token; vuoto se misurato; rifiuto fuori vocabolario |
| R13 | no | no | no | no | decisione (a)/(b) | test che fissa il rifiuto attuale |

Le tre voci che bloccano **il run** del pilota sono R7, R10, R11. Le altre
bloccano l'analisi, il run P6.6 o la campagna. Il criterio di prontezza della
Fase 4 richiede tutte e tre le cose insieme, quindi nessuna voce e' rinviabile
"perche' non blocca il run".

---

## 2. Verifica per voce

### R1 — banda assoluta

**Ancore confermate.** P6.6 `:2608-2615` (la banda si fissa prima del primo
run), `:2657-2658` (unico valore aperto); alternativa D in
`p6_6_banda_20261025.md:145-152`; A1/A2/A3 in
`p6_6_prepilota_20261025.md:313-337`; regola di fattibilita' `:339-354`
(`B_min <= B_abs` e `B_min/s_med <= B_rel`, con divieto di restringere la banda
per far passare il test).

**Da correggere.** Nulla di sostanziale: il registro (`:80-98`) elenca le
quattro alternative di `p6_6_banda_20261025.md` §6 con i nomi giusti (A, B, C,
D) e mette A1/A2/A3 dentro C, che e' corretto. L'unica trappola e' che "A" non
significa la stessa cosa nei due documenti: in `p6_6_banda` e' il pavimento
metrologico, in `p6_6_prepilota` e' la scelta tra ancore e A1/A2/A3 sono le
sue varianti (`:407-409`). Chi approva deve citare documento e sezione, non la
lettera.

**Stato reale.** Aperto il valore, non la regola. `s_epi_phase.py` implementa
gia' il vincolo che conta: la banda si legge dal piano e senza piano resta
`null` (`_load_plan` `:506-521`; `evaluate_phase` `:387-461`).

### R2 — forma relativa

**Ancore confermate.** P6.6 `:2608-2611` chiede una forma "assoluta e relativa"
e non fissa la formula; la simmetrica `r = 2(s - s_EPI)/(s + s_EPI)` e' la
proposta di `p6_6_banda_20261025.md` §2, e il registro la riporta con le tre
letture alternative (`:136-141`). L'harness la implementa (`:350-354`).

**Da correggere.** Nulla. R2 e' correttamente aperto: la formula non e' nel
protocollo e il registro non finge che lo sia. Restano da decidere, insieme a
R1, il **denominatore di `B_rel`** (`s_med` delle fasi valide,
`p6_6_prepilota_20261025.md:318-320`) e il caso di somma nulla, che l'harness
risolve con `None` (`:351-353`) e il registro non tratta.

**Test mancanti.** `r(a,b) = -r(b,a)`; `|r| <= 2` su coppie non negative;
`s = s_EPI = 0`; `s + s_EPI` non positivo (impossibile con `s` in `[0,1]`, ma
il codice non lo assume: `s` arriva dal piano).

### R3 — aggregazione

**Ancore confermate.** `p6_6_prepilota_20261025.md:62-95` (fase come unita',
`s_agg`, `s_EPI,agg`, `d_agg` descrittivo, verdetto congiuntivo per
configurazione, conteggio `k/n`, fasi di bordo in sensibilita'); P6.6
`:2600-2615`.

**Stato reale.** L'harness fa **una parte**: `summarize` (`:464-500`) riporta
per configurazione `n_phases`, `n_with_s_epi`, `n_blocking`, `n_with_verdict`,
media/mediana/min/max/range (niente `sd`) e `in_band: (k, n)`. **Non** fa il
verdetto congiuntivo, non calcola `d_agg`/`r_agg`, non separa le fasi di bordo
dalla sensibilita'. Il registro lo tratta come da implementare: corretto, ma
senza dire che il file esiste.

### R4 — `C`, `R`, `T`

**Ancore confermate.** `p6_6_prepilota_20261025.md:96-128` (tre configurazioni
`cfg_breve` 32, `cfg_lungo` 256, `cfg_conc` 2 in volo / 128; temperatura 0,
`num_ctx` 8192, `keep_alive` -1, `stream` false; `C = 3`, `R = 5`, `T = 420 s`,
una fase invalida tollerata); `:405-427` decisioni C, D, G, H (margine di 60 s
di carico, costo `≈ 3 h`). P6.6 `:2600-2606`.

**Precisazione di stato.** Il registro (`:229-240`) mette in R4 anche G e H
con la ragione giusta, ma non distingue cosa esiste gia': G (bucket di bordo
escluso, dichiarato, non bloccante) e' **implementato** dall'harness del 25/10
(`s_epi_phase.py:300-347`, flag `bucket_di_bordo` fuori da `BLOCKING_FLAGS`);
H e' una scelta del piano; `C`, `R`, `T` e il campo `study` non ci sono. La
tabella `:713-720` tratta R4 come lavoro interamente da fare: e' vero per
`C/R/T/study`, non per G.

**Test mancanti.** Rifiuto di un piano con `C`, `R` o `T` assenti o incoerenti;
`T` inferiore al minimo di 5 bucket (`s_epi_phase.py:106`,
`MIN_BUCKETS_PER_PHASE = 5`); `study: "p6_6_prepilot"` presente in ogni
artefatto (`s_epi_phase.py` oggi non legge quel campo).

### R5 — `engine_tree_changed`

**Ancore confermate.** P6.6 `:2596-2598` (fase valida), `:2624-2635`
(alternativa esclusione/fallback); riga: `benchmark_v4.py:1490`, `:1518`
(`engine_tree_changed = bool(wd.lost)`, cioe' solo processi persi);
`energy/worker_tree.py:206` (`worker_exit_in_window = bool(lost)`);
`local_energy.py:662-678` (quota non calcolata, `not-computed-tree-changed`,
`cpu_time_share_valid = False`).

**Stato reale.** Esclusione applicata a **entrambi** i livelli: riga (la quota
non si calcola) e fase (bloccante nell'harness, `:284-291`). La decisione da
ratificare e' quindi una conferma, non una scelta.

### R6 — worker nati

**Ancore confermate.** P6.6 `:2624-2630`; `energy/worker_tree.py:178-210`
(nato contato da zero, `:197`). Il registro cita `worker_tree.py:194-198`
senza il prefisso `energy/` (`:288`).

**Stato reale.** La semantica letterale e' implementata nel conteggio e **non**
alza il flag: verificato. Manca tutto il resto proposto dal registro
(diagnostica del nato, ramo di sensibilita'): verificato per assenza.

### R7 — `u_within`

**Ancore confermate.** P3.8 `:1063` (formula), `:1066-1068` (non diviso per
`√m`), `:1070-1071` (budget nullo → peso uguale e blocco marcato); P4.6
`:1658-1662`, `:1675-1686`; P6.2 `:2376-2382`; P6.4 `:2434-2439`; schema
`casualwatt_csv_export.py:208-223` senza il campo, `budget_fit_j` a `:215`
lasciato vuoto (`benchmark_v4.py:1684`).

**Stato reale.** Formula decisa, produttore assente: verificato con grep (solo
`benchmark_v4.py:712` in docstring e `semi_range_concentrazione_pesi_probe.py:61`
in una sonda dichiarata simulata). Il registro e' esatto.

**Un punto da correggere (F7).** La proposta di leggere il marcatore di budget
nullo da `budget_fit_j == 0` (`:396-398`) convive male con la convenzione della
cella vuota: oggi `budget_fit_j` e' `""` quando l'analisi non e' stata fatta
(`benchmark_v4.py:1684`). `""` e `0.0` sono due stati diversi e un lettore che
converte il vuoto in zero li confonde. Il marcatore va definito sul valore
**dopo** analisi, con il vuoto che resta "non calcolato".

### R8 — ammissibilita'

**Ancore confermate.** P1.6 `:249-278`; Emenda 8 `:3415-3461`; P4.5
`:1507-1576` (controlli `pre_range_w <= 1,0 W`, `|dP| <= 1,0 W`, quorum
`⌈2/3·n⌉ = 4`); costanti in `validation_chain.py:47-66`; `partition_block_rows`
`benchmark_v4.py:260-421` (il registro scrive `:260-417`: il `return` e' a
`:420-421`).

**Da correggere (F3).** Il registro dice "oggi l'anello 1 di P4.9 non e'
calcolabile" (`:437`). Due errori:
1. la numerazione: `counter_invalid` e' l'**Anello 2** (`validation_chain.py:105`)
   e `baseline_unstable` l'**Anello 3** (`:128`); `r_A` alimenta il terzo, non
   il primo;
2. la conseguenza e' piu' forte: `_num` solleva su un campo vuoto
   (`:92-102`), e c'e' un test che lo pretende
   (`tests/test_chain_status.py:139-142`, `pytest.raises(ValueError, match="r_A")`).
   Con le righe che il runner produce oggi, `chain_status()` **non restituisce
   nessuna etichetta**: fallisce, non degrada. Non e' "un anello non
   calcolabile", e' "il produttore del token non eseguibile sui dati v4".

**Le due meta' (F4).** Scrittura dei guasti tecnici: implementata **e
collegata** (`resolve_emenda8_params` `:147-199`, `V4CounterFault` `:107`,
una sostituzione, `K` senza default `:2012-2019`, mancante alla seconda
occorrenza `:2020-2028`). Lettura: `partition_block_rows` implementata e
testata, **senza chiamante di produzione**. Il registro lo dice in modo
generico ("solo il guasto tecnico"); la distinzione collegato/non collegato e'
quella che conta per la Fase 3.

### R9 — chiusura di P1.7

**Ancore confermate.** P1.7 `:359-371` (rinvio); P1.13 `:518-523`; riga P1
`:11`; F.11 `:1719-1723`; P6.4 `:2447-2449`; Emenda 8 `:3478-3504` (chiude la
direzione, non elenca le frasi superate); `AGENTS.md:62-67` (rinvio).

**Da correggere (F1).** Il registro scrive "tre testi su quattro dicono ancora
il contrario" (`:524`). Il conto non regge: i testi che ripetono il rinvio
sono **sei** — P1.7 `:359-371`, P1.13 `:518-523`, riga P1 `:11`, F.11
`:1719-1723`, P6.4 `:2447-2449`, `AGENTS.md:62-67` — e i due che il registro
stesso cita in Riferimento (`:477-479`) non entrano nel conteggio. In piu' il
rinvio e' scritto anche **nel codice**: docstring `benchmark_v4.py:701-714`
("resta ... rinviata ai dati del pilota P2.9/P6.2") e commento `:747-754` ("da
chiudere sui dati del pilota PRIMA della campagna"). La clausola di
sostituzione deve elencare anche quei due punti, altrimenti la correzione
documentale lascia il codice a contraddire l'emenda.

### R10 — ambiente dichiarato

**Ancore confermate.** P1.3 `:193-205`; `config.py:331`
(`IDLE_CALIBRATION_SECONDS = 10`, non impostata); `energy_session.py:1380-1389`
(`duration_s = max(10, CW_IDLE_WINDOW_S)`, floor 30). Il rischio e' reale:
il CSV registra le potenze ma non la durata, quindi 10 s e 30 s sono
indistinguibili dagli artefatti.

**Test mancanti.** La guardia proposta (ii) deve essere **solo v4**:
`cwEnergyModular/test_calibrazione.py:54` abbassa la finestra via ambiente per i
collaudi rapidi, quindi una guardia in `calibrate_idle` romperebbe la suite.

### R11 — `baseline_backend`

**Ancore confermate.** P1.3 `:203-205`; zero occorrenze del campo in
`cwEnergyModular/`; `energy_session.py:685-688` (token di modalita'), `:1434`
(unpack), `:1442` (`mode_used = mode` in ciclo), `:1449` (`self._idle_mode`),
`benchmark_v4.py:1598` (la post lo sovrascrive). Il disegno in
`p1_3_baseline_backend_20261028.md:35-134` e' verificato: mappatura
`rapl-counter → rapl`, `energy-counter → energy-file`, `emi-counter` e
`pawnio-counter` invariati; `energy_calculation_method == baseline_backend`
per costruzione (`local_energy.py:391-398`).

**Stato reale.** Aperto con disegno completo: corretto. Due punti che il
registro tratta e che l'audit conferma: il campo pre va catturato **prima**
della post (`:82-83`, `:604-610`) e le tre repliche possono in teoria
discordare (`_idle_mode` e' l'ultima), quindi serve un rifiuto o un token
dedicato, non "l'ultima".

### R12 — token D11

**Ancore confermate.** Specifica metodi `metodi_per_dominio_20261025_spec.md:1186-1199`,
`:1931`; `invalid_reason` e' di blocco (`casualwatt_csv_export.py:222`), non di
riga. Il fatto sulla sonda e' verificato oggi: `probes/` non ha `__init__.py`
(solo `cw_probe.py` e un json), e `probes/cw_probe.py:63-69` usa
`codecarbon.core.windows_emi`, non `energy/emi_backend.py`. "Importare la
logica" e' quindi un lavoro reale, non una formalita'. Non bloccante: corretto.

### R13 — guardia `CW_ENERGY_FILE`

**Ancore confermate.** `energy_session.py:548` (`self.method = "energy-file"`),
`:649-654` (ramo del lettore), `:1394-1403` (guardia); `benchmark_v4.py:202-217`
(classificatore), `:1414-1420` (propagazione). Verificato: sotto override il v4
si ferma al primo blocco con `V4MeasurementError`, non con una sostituzione.
Nessun test fissa il rifiuto: confermato.

---

## 3. Riscontri che modificano il registro

**F1 — R9 sottostima il conflitto.** Sei testi, non "tre su quattro", e due
punti di codice. Dettaglio in R9. Effetto: la clausola di sostituzione della
Fase 3 deve nominare `benchmark_v4.py:701-714` e `:747-754`, che oggi il
registro non elenca.

**F2 — esiste gia' un harness P6.6, e il registro non lo nomina.** `s_epi_phase.py`
(radice, **non tracciato**, **non ignorato**: verificato con `git check-ignore`,
exit 1) implementa: banda solo dal piano e `null` altrimenti; `r` simmetrico
con guardia sulla somma; `in_band` solo dentro banda e senza flag bloccanti;
`done_reason` atteso; bilancio `s` in `[0,1]`; esclusione dichiarata bloccante;
bucket di bordo dichiarato e **non** bloccante; minimo 5 minuti; conteggi
`k/n`; nessuna `sd`. Il registro parla di "harness P6.6" come lavoro da fare
(`:120`, `:739-740`) e non include il file tra i "File esaminati" (`:794-811`).
Il file e' invece descritto in `p6_6_congelamento_20261025.md:62-83`, che ne
dichiara anche i limiti (riceve `engine_tree_changed` dal piano, non lo
calcola; `s` dai campi della riga). Quella scheda dichiara "56 controlli";
oggi `--selftest` ne riporta **66**: la cifra del 25/10 e' stantia. Effetto: la
tranche T8 parte da un file esistente, non da zero; e prima va deciso se
tracciarlo.

**F3 — R8: numerazione dell'anello e conseguenza.** Dettaglio in R8. Anello 3,
non 1; e `chain_status()` oggi **solleva** invece di degradare.

**F4 — R8 ha due meta' di stato diverso.** Scrittura collegata, lettura non
collegata. Il registro le tratta come una sola voce ("implementato solo il
guasto tecnico") e questo basta per la descrizione, non per il piano.

**F5 — ancore stantie ripetute in codice ed Emenda 8.** `benchmark_v4.py:206-210`
e `:1426-1427` citano `energy_session.py:2548`, `:2553`, `:2561-2563`,
`:2547-2566`, `:1079-1083`; il file ha 1800 righe, `:1080` e' `def stop()`, e
i `raise` reali sono a `:1396`, `:1427`, `:1436`. Emenda 8 ripete le stesse
posizioni a `:3402-3406` e `:3470`. P1.13 `:513` cita `config.py:319`, ma la
riga e' `:331`. P6.5 `:2521-2527` afferma che `pre_range_w`, `dP` e `budget_base_j`
non sono in `CSV_COLUMNS`, citando il range `:17-108`: quel range si ferma
prima delle colonne, che oggi sono a `casualwatt_csv_export.py:147-148`.
L'affermazione era vera allo snapshot citato, non al file attuale.
Nessuna di queste e' una decisione, ma un emendamento che le eredita propaga
l'errore: vanno corrette nel commit di commenti, prima o insieme a T0.

**F6 — imprecisioni minori del registro.** `partition_block_rows` finisce a
`:421`, non `:417`; `worker_tree.py` e' `energy/worker_tree.py` (nato a `:197`,
non `:194-198`); "P3.8 `:1048-1052`" e' testo di **P3.7** (P3.8 inizia a
`:1054`); R4 mescola G (gia' implementato) con C/R/T (da implementare).

**F7 — il marcatore di budget nullo collide col vuoto.** Dettaglio in R7.
`""` (non calcolato) e `0.0` (budget nullo) sono due stati.

**F8 — nessun test fissa i conteggi dello schema.** `tests/test_csv_schema_p5.py`
non verifica 172/36/19; `tests/test_keep_alive_dichiarato.py:111` controlla solo
l'unicita' dei nomi. Un'aggiunta accidentale di colonna passerebbe la suite.
Conseguenza diretta sul requisito "nuove colonne solo tramite emendamento
esplicito": senza un test di conteggio, l'emendamento non e' verificabile.
Prima di T4 e T9 serve un test di congelamento (T1).

---

## 4. Decisioni richieste al proprietario

Nessuna di queste e' presa qui. Per R1-R6 la Fase 2 preparera' la proposta
motivata (formule, parametri, alternative, conseguenze, test); le altre sono
decisioni di contratto dei dati o di documento.

### P6.6 (metodologiche, Fase 2)

| # | domanda | opzioni | cosa cambia |
|---|---|---|---|
| D-1 | ancora della banda `B_abs`/`B_rel` | A1 (`q·budget_pred/E_active`, `q = 1/3`), A2 (`B_rel = 5%`), D (nessuna banda, solo `d` e `r`) | A1 richiede il pilota P6.2 prima; A2 e' subito disponibile; D richiede emenda esplicita |
| D-2 | denominatore relativo | `s_med` delle fasi valide | entra nella banda; va preregistrato con D-1 |
| D-3 | aggregazione | verdetto congiuntivo per configurazione, `d_agg`/`r_agg` descrittivi, `k/n` | definisce cosa si scrive nel risultato P6.6 |
| D-4 | `C`, `R`, `T` e margine H | `C = 3`, `R = 5`, `T = 420 s`, H si'/no | condizionato a D-1; costo dichiarato |
| D-5 | `engine_tree_changed` a livello fase | ratifica dell'esclusione | nessun cambio di codice; ratifica il comportamento dell'harness |
| D-6 | worker nati | semantica letterale (conteggio da zero, nessun flag) + ramo di sensibilita' | aggiunge solo analisi |

### Contratto dei dati

| # | domanda | opzioni | cosa cambia |
|---|---|---|---|
| D-7 | produttore di `u_within` | (b) analisi, poi (c) entrambi; oppure (c) subito | (b) nessuno schema; (c) emendamento 36 → 38 |
| D-8 | gate unico per il fit | (a) modulo di analisi con soglie congelate; (b) flag nel fit; (c) runner | (a) e' l'unica che non duplica le regole |
| D-9 | `baseline_backend` | riepilogo di blocco (raccomandato) o riga; bordo zero per costruzione | emendamento 36 → 37/38, cattura della pre |
| D-10 | `CW_ENERGY_FILE` | (b) rifiuto dichiarato e fissato da un test; (a) ammissione DEV/TEST con filtro `external_counter` | (a) tocca il percorso di misura |
| D-11 | token D11 | (a) nuova colonna di riga, sette token; (b) allargare il canale; (c) artefatto a parte | (a) emendamento 172 → 173 |
| D-12 | ambiente dichiarato | (i) dichiarazione nel piano; (ii) guardia fail-closed 30 s solo v4; (iii) durata effettiva in un campo | (ii) cambia il comportamento; (iii) tocca lo schema |

### Documentali e di processo

| # | domanda | effetto |
|---|---|---|
| D-13 | emenda datata R9 con elenco esatto delle frasi superate (sei testi + due punti di codice, F1) | chiude la contraddizione senza riscrivere la specifica |
| D-14 | correzione delle ancore stantie (F5) in un commit di commenti | impedisce che l'emenda le erediti |
| D-15 | track/no-track di `s_epi_phase.py` | senza decisione, l'harness resta fuori dal repo e non e' citabile |
| D-16 | autorizzazione dei branch e della sequenza T0-T9 | nessun lavoro di codice parte prima |

---

## 5. Piano di implementazione ordinato per dipendenze

Il vincolo che ordina il piano: nessun emendamento di schema prima di un test
che fissi i conteggi; nessun campo prima del suo produttore; nessuna soglia
prima dell'approvazione che la fissa.

| tranche | contenuto | tipo | dipende da | tocca il percorso di misura |
|---|---|---|---|---|
| T0 | emenda datata R9 + dichiarazione R10 nel piano; correzione delle ancore stantie (F5, F6) | documento + commenti | D-13, D-14 | no |
| T1 | test di congelamento 172/36/19; test che `baseline_backend` e `u_within_j` non sono nello schema finche' l'emenda non c'e' | test | D-16 | no |
| T2 | modulo di analisi unico: gate (invalidazione tecnica, `r_A`, `r_B`, `negative_increment`, filtro `external_counter`) + liste primaria/sensibilita'/esclusa, con motivo | codice | D-8, T1 | no |
| T3 | `u_within` nel modulo di T2, su `active_energy_raw_j`, con `m_valide` dichiarato | codice | D-7, T2 | no |
| T4 | emendamento P5 unico: `baseline_backend` + `u_within_j` in coda (36 → 38), migrazione per nome, conteggio aggiornato nel test di T1 | schema | D-7, D-9, T3 | no |
| T5 | R11: cattura del modo pre prima della post, tre repliche concordi, colonna, test d'invarianza con `energy_calculation_method` | codice | T4 | si' (sola lettura del modo) |
| T6 | R13: test che fissa il rifiuto attuale; se (a), ramo DEV/TEST con `external_counter` | test/codice | D-10 | solo con (a) |
| T7 | R10(ii): guardia fail-closed 30 s, solo v4 | codice | D-12 | si' (guardia, non misura) |
| T8 | harness P6.6: verdetto congiuntivo, `d_agg`/`r_agg`, fasi di bordo in sensibilita' (R3); `C`/`R`/`T` e campo `study` (R4); nati (R6); decisione di tracking | harness | D-1..D-6, D-15 | no |
| T9 | R12: colonna D11 (172 → 173) e sette token | schema | D-11, T1 | no |

Note di sequenza:

- T2 prima di T3 perche' `u_within` deve nascere **dentro** il gate, altrimenti
  si duplica la regola di ammissibilita' che la Fase 3 vieta;
- T3 prima di T4 perche' un campo senza produttore e' il difetto che R7
  descrive;
- T4 e T5 sono lo stesso emendamento ma due commit (schema, poi codice);
- T8 non introduce soglie nuove: implementa quelle approvate in D-1..D-6;
- nessuna tranche sposta una soglia congelata (1,0 W, 10%, 20%, 5%, `err_rel`).

---

## 6. Prerequisiti che l'audit non chiude

- **W1** — wattmetro AC/DC esterno: senza, la scala assoluta resta non
  arbitrata. EMI e PawnIO leggono lo stesso registro (`0x611` / variante AMD),
  quindi il loro accordo a finestra uguale non e' una validazione indipendente.
- **GPU** — catene NVML e AMD SMI implementate e provate con librerie finte;
  nessuna esecuzione su scheda reale su questo host: `[V]` assente.
- **D15** — Windows multi-socket: decisione e verifica separate.
- **G0** — dataset gated, nessun token HF sull'host; R12 e' la sua parte
  registrabile, non la sblocca.
- **P6.3** — audit idle 30 minuti, `pre_range_w <= 1,0 W`: prerequisito
  separato, non toccato da R1-R13.
- **Piano del pilota** — non esiste ancora come artefatto: deve portare
  `campaign_id`, digest del modello, `done_reason` atteso, `C/R/T`, banda (o
  `null` dichiarato), esclusioni. Senza piano, l'harness rifiuta di dare un
  verdetto, ed e' il comportamento voluto.
- **Appendice D** — ogni test aggiunto nei T1-T9 cambia il conteggio: va
  rigenerata con `tools/dump_tests_latex.py`, non aggiornata a mano.

---

## 7. Cosa non e' stato fatto

- nessuna riga di codice di produzione, schema o protocollo modificata;
- nessun campo aggiunto; nessuna soglia, formula o banda fissata;
- nessun run sperimentale, nessun `powercfg`, nessun accesso al contatore;
- `pytest cwEnergyModular` non rieseguito (nessuna modifica): il conteggio
  resta quello di `AGENTS.md`;
- nessun push, nessun branch creato.

L'unico esito eseguibile di questo turno e' il `--selftest` dell'harness
(66 controlli), citato in §0 e usato per correggere la cifra di
`p6_6_congelamento_20261025.md:75`.
