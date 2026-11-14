# Decima settima emenda — proposta ritirata (disapplicata / non adottata)

**Stato: DISAPPLICATA / NON ADOTTATA** — ritirata dal protocollo attivo il
2026-11-14, prima di qualunque commit nel ramo condiviso.

**Cosa fosse:** una proposta di emenda al protocollo v4 che alzava le costanti
di esecuzione del warm-up post-carico (`WARMUP_TOLERANCE_W` da 0,5 W a 2,5 W,
`WARMUP_CPU_MAX_PCT` da 2,0 % a 6,0 %, `WARMUP_CAP_S` da 60 s a 120 s), con
`WARMUP_SUSTAIN_S`, `WARMUP_WINDOW_S`, `WARMUP_STEP_S` e le precondizioni di
quiete invariate. Il testo integrale, copiato verbatim dal working tree, sta
nell'ultima sezione di questo documento.

**Dove stava:** `experiment_results/protocollo_v4_20261024.md`, working tree
non committato, unico hunk `@@ -335,6 +335,44 @@` (38 righe aggiunte dopo il
blocco della Sedicesima emenda). Con il ritiro, il protocollo è riportato allo
stato di HEAD sul punto: nessuna emenda resta nel documento attivo.

## Perché è stata ritirata

Le ragioni sono verifiche eseguite il 2026-11-14 sul materiale esistente, non
giudizi a priori. In ordine di peso:

### 1. Il criterio di produzione, applicato alla traccia del fallimento, non chiude con le soglie nuove

La proposta sosteneva che «con soglie realistiche la macchina entra in banda
prima». La traccia del warm-up fallito del 2026-11-13
(`experiment_results/p44_gate_20261113/warmup_stabilizzazione.jsonl`, blocco
`carico-1`: 30 finestre da 2 s, `tetto_raggiunto` dopo 61,07 s, target
`warmup_target_pre_w = 4,040193 W`) è stata riletta con la logica di
produzione `_stabilizza_post_carico` (`cwEnergyModular/tools/run_gate_p44.py:1651`),
iniettando le soglie e un orologio finto di 2 s per finestra (nessuna misura
nuova, nessuna scrittura):

| soglie | finestre in banda su ENTRAMBI i segnali | massima sequenza CONTINUA | esito sul criterio (10 s continui) |
|---|---|---|---|
| HEAD (0,5 W / 2,0 %) | 0 / 30 | 0 finestre | non soddisfatto — riproduce il fallimento reale |
| emenda (2,5 W / 6,0 %) | 11 / 30 | 4 finestre = 6 s | **non soddisfatto** |

Con le soglie della proposta la macchina non entra in banda: la sequenza
continua massima resta 6 s contro i 10 s richiesti. Raddoppiare il tetto a
120 s non è supportato da nulla nei dati registrati — la traccia finisce a
60 s e non contiene alcun tratto di 10 s, quindi l'unica conseguenza
dimostrata del tetto più lungo è attendere di più lo stesso fallimento.

### 2. La soglia CPU proposta cade dentro il rumore stazionario della condizione che fallisce

Nelle 15 finestre dopo il transitorio iniziale (finestre 15-29 della stessa
traccia) la media di `cpu_percent` è 5,81 %, con 4 valori su 15 a 6,0 % o
oltre (6,0, 6,5, 7,0, 6,3). Una soglia posta alla media della distribuzione
stazionaria, con disuguaglianza stretta (`cpu >= max` è fuori banda,
`run_gate_p44.py:1861`), viene attraversata a caso dal rumore: non può
produrre un tratto continuo di 10 s per costruzione, solo per fortuna.

### 3. La caratterizzazione citata descrive un'altra condizione macchina

`experiment_results/machine_characterization_20261113.jsonl` (150 finestre,
`emi-counter`) riporta `power_w` con massimo 12,032 W, mentre il warm-up
fallito del 13-11 leggeva 15,57-18,45 W nelle prime 14 finestre (scostamento
11,5-14,4 W dal target). La condizione che fallisce è quindi **fuori**
dall'intervallo caratterizzato. L'artefatto non registra quali processi
fossero attivi: la descrizione «macchina rilassata (Chrome, Qoder, WSearch
fermi, Defender attivo)» vive solo nel testo della proposta, non nei dati, e
non è ancorata.

### 4. Il testo dell'emenda descrive male il proprio artefatto

La proposta dichiara «150 finestre da 2 s (300 s totali)»; il record di
sintesi dello stesso file dichiara `target_duration_s: 600.0`,
`finestre_totali: 150`, e le finestre coperte vanno da `t_mono_start`
43908,06 s a `t_mono_end` 44510,91 s, cioè ~603 s. La cadenza effettiva per
finestra è di ~4 s (`dt_counter_s` 3,54-4,02 s), non 2 s. Conseguenza
metodologica: le statistiche della proposta (p95 7,919 W, p95 5,8 %) sono
calcolate su finestre di ~4 s e vengono applicate a finestre da 2 s del
criterio; medie su intervallo più lungo attenuano la varianza, quindi il p95
citato **sotto**stima quello delle finestre del warm-up. La proposta non
dimostra l'applicabilità delle proprie statistiche alla scala del criterio.

### 5. Il numero «1,09 s» citato dalla proposta non regge sotto le soglie della proposta

La proposta motiva la permanenza invariata con «massima sequenza continua
1,09 s in campagna 2026-11-08». Quel numero è calcolato dal test di
provenienza `test_provenienza_permanenza_supera_il_tratto_continuo_del_transitorio`
(`cwEnergyModular/tests/test_budget_p44_preesecuzione.py:944-973`) **con la
tolleranza in vigore nel modulo** (`rg.WARMUP_TOLERANCE_W`), quindi dipende
dalla soglia. Con le soglie della proposta, iniettate in memoria senza
modificare alcun file, l'asserzione cade:

```
assert 2.2038846999998896 == 1.09 ± 0.02   (test_budget_p44_preesecuzione.py:973)
```

Il tratto continuo del transitorio cresce da 1,09 s a 2,20 s. Con le soglie
della proposta i tre test di provenienza risultano rossi (verificato con
patch in memoria, `3 failed, 41 passed`):

- `test_warmup_default_pre_registrati_coerenti`
- `test_provenienza_soglie_il_transitorio_occupa_due_finestre_opposte`
- `test_provenienza_permanenza_supera_il_tratto_continuo_del_transitorio`

La giustificazione della proposta poggia su un numero che la proposta stessa
invalida.

### 6. Le soglie sono state cambiate dopo aver visto i fallimenti

Le soglie proposte sono state elaborate il 2026-11-13, cioè **dopo** i
fallimenti del warm-up del 09-11 e del 13-11. La regola del protocollo è che
le soglie si congelano prima dei dati: una soglia tarata sui fallimenti già
osservati perde il requisito della preregistrazione, qualunque sia il suo
valore numerico.

### 7. Difetti formali minori

- La proposta cita `test_warmup_gate_p44.py` («da aggiornare»): il file non
  esiste nel repository.
- Gli artefatti citati a corredo (`machine_characterization_20261113.jsonl`,
  `p44_gate_20261113/`, `p44_gate_20261109/warmup_stabilizzazione.jsonl`,
  `p44_gate_20261109/budget_preregistrato.json`) non sono tracciati in git:
  una proposta congelante che cita evidenze non tracciare non è
  rigenerabile da chi la riceve.

## Cosa è stato fatto invece

1. Le costanti di `cwEnergyModular/tools/run_gate_p44.py` sono state
   riportate ai valori di HEAD (`WARMUP_TOLERANCE_W = 0.5`,
   `WARMUP_CPU_MAX_PCT = 2.0`, `WARMUP_SUSTAIN_S = 10.0`,
   `WARMUP_CAP_S = 60.0`, `WARMUP_WINDOW_S = 2.0`, `WARMUP_STEP_S = 0.0`,
   righe 276-281). Il check "F" di `plan_payload()` è costruito con
   f-string dalle stesse costanti (righe 519-559), quindi dichiarazione del
   piano e codice restano allineati per costruzione.
2. I test `cwEnergyModular/tests/test_budget_p44_preesecuzione.py` **non**
   sono stati modificati: con le costanti di HEAD risultano
   `44 passed in 1.81s`.
3. Il ripristino non produce commit: `git diff` sul file è vuoto, il file
   coincide con HEAD. Il backup delle modifiche pre-ripristino è conservato
   in `backup_pre_ripristino_warmup.patch` (radice del repo, non tracciato).

## Stato operativo dopo il ritiro

`_verifica_piano` (`cwEnergyModular/tools/run_gate_p44.py:1232-1255`) è
fail-closed: confronta `warmup_tolerance_w`, `warmup_cpu_max_pct`,
`warmup_sustain_s`, `warmup_cap_s`, `warmup_step_s`, `warmup_window_s` del
piano con le costanti del modulo e solleva `SystemExit` su qualunque
discosto. Di conseguenza il piano `experiment_results/p44_gate_20261114/plan.json`
(non tracciato, dichiarato 2026-11-14T00:53:20+00:00 con le soglie della
proposta 2,5 W / 6,0 % / 120 s) **non è eseguibile** contro il tool: la
guardia lo rifiuta prima di misurare. La data `20261114` non va riusata per
una campagna nuova.

## Rimedio corretto, in sequenza

1. **Diagnostica** del carico di fondo con Qoder attivo: identificare i
   processi, misurare CPU e potenza a Qoder attivo e non attivo sulla stessa
   finestra, stabilire cosa è eliminabile e cosa è strutturale. Senza questa
   misura, qualunque soglia è un numero scelto a occhio.
2. **Decisione di protocollo separata**, con la caratterizzazione misurata
   della condizione reale di campagna (stessi processi, stessa finestra,
   stessi 2 s del criterio) e preregistrata prima dei dati.
3. Se la quiete P1.4 risultasse irraggiungibile sulla macchina di
   produzione, aprire una modalità separata e **non aggregabile**
   (`background_controlled`), con propria preregistrazione e proprio
   Budget — non uno spostamento delle soglie esistenti, che renderebbe non
   confrontabili le campagne.
4. Solo allora una campagna nuova, con una data nuova, mai riusando
   `20261114`.

## Testo originale della Decima settima emenda (verbatim dal working tree)

```text
**Decima settima emenda — Soglie di quiete e warm-up aggiornate su caratterizzazione macchina (2026-11-14)**

**Ancoraggio:** Tredicesima–Quattordicesima emenda (precondizione di quiete P1.4, warm-up post-carico a criterio misurato F.12). Le soglie congelate nelle emende precedenti (QUIET_CONSECUTIVE=3, WARMUP_TOLERANCE_W=0,5 W, WARMUP_CPU_MAX_PCT=2,0 %, WARMUP_SUSTAIN_S=10 s) derivavano dai dati della campagna 2026-11-08 (5 controlli stabilizzati) e sono risultate **non eseguibili** sulla macchina di produzione quando Qoder è attivo: il warm-up raggiunge il tetto (60 s) con CPU 7–17 % e scostamenti di potenza 1–12 W dalla baseline, senza mai soddisfare le due soglie simultaneamente.

**Caratterizzazione macchina (2026-11-13, `experiment_results/machine_characterization_20261113.jsonl`):** 150 finestre da 2 s (300 s totali, canale emi-counter), macchina "rilassata" (Chrome, Qoder, WSearch fermi, Defender attivo). Statistiche aggregate:

| segnale | count | mean | median | stdev | min | max | p95 | p99 |
|---|---|---|---|---|---|---|---|---|
| power_w | 150 | 5,533 | 5,532 | 1,173 | 4,009 | 12,032 | 7,919 | 10,491 |
| cpu_pct | 150 | 3,409 | 3,6 | 1,625 | 0,9 | 10,2 | 5,8 | 8,7 |

Le soglie precedenti (0,5 W e 2,0 %) stanno **sotto** p95 di entrambe le distribuzioni: una macchina "normale" le viola sistematicamente. La coppia di soglie deve separare il transitorio termico reale (che il warm-up esiste per rimuovere) dalla variabilità stazionaria della macchina.

**Soglie aggiornate (congelate PRIMA della terza campagna, dichiarate nel piano):**

| costante | valore precedente | valore nuovo | giustificazione |
|---|---|---|---|
| `QUIET_CONSECUTIVE` | 3 | 3 | invariata: 3 letture consecutive (~9 s) restano un prerequisito ragionevole; il tetto 600 s non cambia |
| `QUIET_CAP_S` | 600,0 | 600,0 | invariata |
| `WARMUP_TOLERANCE_W` | 0,5 | **2,5** | ≥ p95−median = 2,387 W; copre la variabilità stazionaria (stdev 1,173 W, range 8 W) e resta sotto i picchi transitori osservati in campagna (ctrl-1: 0,795 W alla 2ª finestra) |
| `WARMUP_CPU_MAX_PCT` | 2,0 | **6,0** | ≥ p95 = 5,8 %; copre la variabilità stazionaria (stdev 1,625 %, max 10,2 %) e resta sotto carichi anomali sostenuti |
| `WARMUP_SUSTAIN_S` | 10,0 | 10,0 | invariata: 10 s = 3,4 finestre Tc consecutive; chiede persistenza, non istantaneità |
| `WARMUP_CAP_S` | 60,0 | **120,0** | raddoppiata: con soglie realistiche la macchina entra in banda prima; 120 s = 41 finestre Tc, margine sufficiente |
| `WARMUP_WINDOW_S` | 2,0 | 2,0 | invariata: scala di osservazione coerente con QUIET_POLL_S e dt_nominal_s |
| `WARMUP_STEP_S` | 0,0 | 0,0 | invariata: nessuna pausa extra |

**Logica di separazione transitorio/stazionario (invariata):** i DUE segnali (potenza E cpu_percent) devono stare dentro soglia nella **stessa finestra**, per `WARMUP_SUSTAIN_S` secondi consecutivi. Una finestra fuori soglia su uno qualunque dei due, o una lettura assente, azzera il tratto. La disuguaglianza è stretta su entrambi. Il transitorio termico (ctrl-1 campagna 2026-11-08) mostrava: finestra 1 → 0,4802 W / 4,100 %; finestra 2 → 0,7951 W / 1,800 %. Con le nuove soglie (2,5 W / 6,0 %) **entrambe le finestre del transitorio passano**, mentre la variabilità stazionaria (p95 7,9 W / 5,8 %) sta dentro soglia per costruzione. La separazione non è più sul transitorio vs stazionario (entrambi passano), ma sulla **persistenza**: il warm-up chiede 10 s continui in banda, che il transitorio non dà (massima sequenza continua 1,09 s in campagna 2026-11-08) mentre la macchina stazionaria sì.

**Conseguenze operative:**
- Il piano della terza campagna (`plan --date 20261114 --pairs 12`) congela i nuovi valori in `plan.json` (check E, F). `_verifica_piano` rifiuta un execute con soglie diverse.
- `run_gate_p44.py` aggiorna le costanti globali (`WARMUP_TOLERANCE_W`, `WARMUP_CPU_MAX_PCT`, `WARMUP_CAP_S`) e le propaga nel `plan_payload()`.
- La campagna 2026-11-09 (fallita per warm-up) **non si ripete**; i suoi artefatti restano come fotografia della macchina con soglie non eseguibili.
- Nessuna formula, nessun criterio (F.12), nessun quorum, nessuna `dt_nominal_s`, nessuna geometria cambiano: solo le costanze di esecuzione del tool.

**Tracciabilità:** caratterizzazione `machine_characterization_20261113.jsonl` (150 finestre, 300 s, emi-counter); warm-up fallito `p44_gate_20261109/warmup_stabilizzazione.jsonl` (tetto_raggiunto, CPU 7–17 %, ΔW 1–12 W); codice `run_gate_p44.py` (costanti globali aggiornate); test `test_quiet_gate_p44.py` e `test_warmup_gate_p44.py` (da aggiornare con le nuove soglie).

---

```