# D11 e D15 — che cosa manca: codice, evidenza o decisione

Data: 2026-10-28. Ambito: audit di Fase A, senza toccare il percorso di misura.
**Nessuna riga di codice modificata, nessuna colonna aggiunta, nessun run.**
Le due voci hanno esiti diversi: D11 e' codice mancante dietro una decisione di
schema; D15 e' chiuso a meta', con la meta' Linux in codice e la meta' Windows
ancora aperta. La specifica le descrive tutte e due come aperte, e su D15 e'
rimasta indietro rispetto al codice.

Fonti verificate oggi: `metodi_per_dominio_20261025_spec.md` (§4.1, righe
`1164`, `1186-1199`, `1256`, `1931`, `1935`, `1984-1987`), `probes/cw_probe.py`,
`energy/emi_backend.py`, `energy/rapl_backend.py`, `diagnostics.py`,
`casualwatt_csv_export.py`, `energy/local_energy.py`, `tests/test_rapl_zone.py`.

---

## 1. D11 — le ragioni di G0 come token di riga

**Requisito.** Il lessico di §4.1 (`vm`, `remote_endpoint`, `permission_denied`,
`driver_missing`, `no_energy_domain`, `counter_stale`, `ambiguous_domain`) deve
produrre **un token della riga**, non un file a parte, e il testo del motivo non
deve nominare il produttore (`:1931`). La frase che chiude la sezione lo dice
come lavoro da fare, non come scelta aperta: "Serve che il suo esito diventi un
token della riga, non un file a parte (D11)" (`:1194-1199`).

**Che cosa esiste.**

| pezzo | dove | che cosa produce |
|---|---|---|
| sonda di sola lettura, tracciata (commit `bb32e26`, 26-10) | `probes/cw_probe.py` | *osservazioni*: `hypervisor_flag`, `systemd_detect_virt`, `wsl` (`:31-39`), `vm_by_model_string` (`:50`), canali EMI, zone powercap (`:92-126`), NVML, `OLLAMA_HOST`/`is_local` (`:181-193`); scrive un JSON (`:225`) |
| token `ambiguous_domain` | `energy/emi_backend.py:255`, `:280` | una **stringa di rifiuto** del selettore, non un campo di riga |
| token `driver_missing` | `diagnostics.py:300` | un messaggio della diagnostica, non un campo di riga |

Gli altri cinque token non compaiono in nessun percorso di produzione: vivono
nella tabella di §4.1 e, come osservazioni, nella sonda.

**Che cosa manca.**
1. **Codice — il campo non c'e'.** Nessuna colonna in `CSV_COLUMNS`
   (`casualwatt_csv_export.py:17-200`, 172 voci), nessun campo nel dataclass di
   riga. `invalid_reason` (`casualwatt_csv_export.py:222`) e' un token di
   **blocco** per i guasti del contatore (`delta_negativo`, `lettura_non_finita`):
   vocabolario diverso e granularita' diversa, non sostituisce D11.
2. **Codice — manca la mappatura osservazione -> token.** La sonda non e' un
   pacchetto (`probes/` non ha `__init__.py`) e la produzione non la importa: il
   lettore EMI di produzione e' `energy/emi_backend.py` (ctypes), mentre la sonda
   usa `codecarbon.core.windows_emi` (`probes/cw_probe.py:63-69`). Sono due
   lettori distinti, quindi "l'esito della sonda diventa un token" non e' un
   ritocco: o si importa la logica di rilevazione, o la si duplica dichiarandolo.
3. **Decisione — dove vive il token.** P5 ha congelato 172 colonne di riga
   (2026-10-26, riconteggiate dal decimo emendamento il 2026-10-28): una colonna
   nuova e' un emendamento. L'alternativa — allargare `energy_calculation_method`
   a un insieme di ragioni — confonderebbe due vocabolari (canale contro
   motivo) e renderebbe non filtrabile per canale una tabella che oggi lo e'.
   La scelta e' dell'utente; il codice non la prende da solo.

**Classificazione: codice mancante**, dietro **una decisione di schema**. Non e'
evidenza mancante: le ragioni sono gia' osservabili su questo host (hypervisor
falso, endpoint locale, `ambiguous_domain` gia' coperto da
`tests/test_emi_selezione.py:138`, `:168`), e non serve hardware nuovo per
scriverle in una riga.

**Che cosa lo chiude.** (a) decisione colonna nuova contro estensione del
vocabolario, con emendamento P5; (b) campo nel dataclass e scrittura per riga;
(c) una funzione di mappatura a vocabolario chiuso, con un test per token e il
rifiuto dei valori fuori elenco; (d) la regola "il testo non nomina il
produttore" verificata da un test, non dalla prosa.

---

## 2. D15 — package multipli e canali specchiati

**Decisione.** Gia' presa (`:1935`): enumerare le zone powercap per `name` e i
device EMI per path, **deduplicare i canali specchiati**, poi **sommare** i
package distinti. Cio' che resta e' l'implementazione, e non e' uniforme fra i
due sistemi.

**Linux: implementato, con l'evidenza solo su sysfs finto.**

| pezzo | dove |
|---|---|
| enumerazione e deduplica dei canali specchiati | `energy/rapl_backend.py:128-183` (dedup `:154-159`) |
| **somma** delle zone package distinte | `energy/rapl_backend.py:209-226` (`sum(...)` a `:222`), con rifiuto della somma parziale (`:223-225`) |
| potenza istantanea come somma | `energy/rapl_backend.py:230-244` |
| due socket sommati | `tests/test_rapl_zone.py:57` |
| canale specchiato contato una volta | `tests/test_rapl_zone.py:70` |
| potenza come somma delle zone | `tests/test_rapl_zone.py:125` |

Manca **[V]**, non codice: la somma e' provata su un `sysfs` finto, mai su una
macchina con due socket reali.

**Windows: enumerazione e rifiuto implementati, somma assente.**

| pezzo | dove |
|---|---|
| selezione per metadato, canale PKG per nome | `energy/emi_backend.py:226-263` |
| canale specchiato letto una volta | `:252-262` |
| due canali PKG con nomi distinti -> `ambiguous_domain` | `:253-257` |
| piu' device CPU -> nessuna scelta automatica, serve `CW_EMI_DEVICE` | `:266-285` |

Qui la somma **non** c'e', ed e' una scelta difendibile: senza hardware
multi-socket non si puo' verificare che due device PKG distinti siano due socket
additivi invece di due descrizioni dello stesso package. La decisione da
prendere non e' "come sommare" ma **se** sommare automaticamente oppure
richiedere una dichiarazione esplicita di multi-device; il codice oggi rifiuta e
chiede `CW_EMI_DEVICE`, che e' la seconda.

**Classificazione: Linux = evidenza mancante; Windows = codice mancante piu'
evidenza mancante.** Nessuna delle due e' una decisione metodologica aperta, a
meno di voler cambiare la regola "somma i package distinti", che e' congelata
nella specifica.

**Che cosa lo chiude.** Linux: una macchina con due socket e la stessa sonda
A-B-A usata per EMI. Windows: decisione sul modo automatico contro dichiarato,
poi il codice, poi un host con due device PKG distinti per verificare che la
somma sia quella giusta e non un doppio conteggio.

---

## 3. Sei frasi della specifica che il codice ha superato

La specifica e' un documento vivo (rev. 28/10), quindi qui si corregge; il
protocollo congelato non si tocca. Le frasi sotto dicono "la somma non e'
implementata" senza distinguere i due sistemi, e per Linux non e' vero dal
27-10-2026 (commit `1abd5e0`).

| riga | testo attuale | correzione |
|---|---|---|
| `:307` | "restano il token di riga (D11) e la somma dei package distinti (D15)" | qualificare: su Windows; su Linux in codice dal 27/10 |
| `:1164` | "La **somma** dei package distinti resta D15, non implementata" | Linux: somma in codice dal 27/10 (`rapl_backend.py:222`), provata su sysfs finto (`test_rapl_zone.py:57`); Windows: somma non implementata, due device PKG distinti restano `ambiguous_domain` |
| `:1256` | "la **somma** dei package distinti resta D15" | idem, con la distinzione Linux/Windows |
| `:1911` | "Resta non implementata la **somma** dei package distinti, che e' D15" | Linux in codice dal 27/10; resta aperta la meta' Windows |
| `:1935` | "la **somma** dei package resta non implementata" | idem |
| `:1987` | "restano il token di riga (D11) e la **somma** dei package distinti (D15)" | resta la somma **su Windows** (D15); su Linux c'e' dal 27/10 |

Le righe `:914`, `:509` e `:1192` restano valide: parlano di PowerJoular e di
`ambiguous_domain`, non dello stato della somma. Le righe `:581` e `:1271`
descrivevano gia' la somma come implementata e contraddicevano le sei sopra:
sono quelle giuste, e le sei sopra sono state allineate a loro.

---

## 4. Stato di questo turno

- nessuna riga di codice, nessuna colonna, nessun emendamento, nessun run;
- il documento non decide ne' D11 ne' D15: dice per ciascuna quale dei tre
  ostacoli (codice, evidenza, decisione) la tiene ferma;
- la correzione delle quattro frasi della specifica e' un commit di sola
  documentazione, separato da questo.

---

## 5. Ancore verificate il 2026-10-28

| affermazione | ancora |
|---|---|
| lessico di G0 e requisito del token di riga | `metodi_per_dominio_20261025_spec.md:1186-1199`, `:1931` |
| la sonda produce osservazioni, non token | `probes/cw_probe.py:31-55`, `:92-126`, `:181-193`, `:225` |
| la produzione non importa la sonda | nessun `import probes` in `cwEnergyModular/`; `probes/` senza `__init__.py` |
| due lettori EMI distinti | `probes/cw_probe.py:63-69` contro `energy/emi_backend.py` |
| nessun campo di ragione nella riga | `casualwatt_csv_export.py:17-200`; `invalid_reason` di blocco a `:222` |
| token gia' usati come stringhe | `energy/emi_backend.py:255`, `:280`; `diagnostics.py:300` |
| Linux: dedup e somma | `energy/rapl_backend.py:128-183`, `:209-226` |
| Linux: test della somma | `tests/test_rapl_zone.py:57`, `:70`, `:125` |
| Windows: rifiuto dei package multipli | `energy/emi_backend.py:253-285` |
| decisione D15 nella specifica | `metodi_per_dominio_20261025_spec.md:1935` |
| frasi da correggere | `metodi_per_dominio_20261025_spec.md:307`, `:1164`, `:1256`, `:1911`, `:1935`, `:1987` |
| frasi gia' corrette, rimaste come riferimento | `metodi_per_dominio_20261025_spec.md:581`, `:1271` |
