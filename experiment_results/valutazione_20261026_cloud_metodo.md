# Audit metrologico dei quattro punti operativi — Rete (`E_rete`) e Cloud (`E_cloud`)

Data: 2026-10-26. Branch: `emenda-8`. Nessun file di produzione modificato o committato in
questa seduta. Gli ancoraggi di codice sono verificati su **`f834691`**, che è HEAD al
momento di scrivere. Durante questa seduta il lavoro parallelo su P5/C5 ha portato sette
commit — `2a448d0` (rete: `config.py`, `energy/network_energy.py`,
`tests/test_rete_nic_confine.py`), `768eb80` e `f3a6924` (cloud: banda min-max e sei
colonne di diagnostica), `ab30fa0` (pavimenti dichiarati e cache), `f0cfecc` (confine che
cita Baliga solo col valore della fonte), `c1f9161` (test del blocco remoto), `f834691`
(**P5 dichiarato congelato** nel protocollo) — e l'albero di lavoro è tornato pulito. È la
ragione per cui i §3 e §5 registrano **lo stato attuale**, non la premessa della richiesta,
e per cui i numeri di riga di questo documento sono legati a un commit.

**Provenienza del materiale.** I quattro punti arrivano come "Analisi Tecnica e Revisione
Formale" prodotta da un modello, non dal codice. Per AGENTS.md è **spunto, non evidenza**:
ogni affermazione numerica, ogni citazione e ogni nome di campo è stata verificata contro
`cwEnergyModular/`, `experiment_results/metodi_per_dominio_20261025_spec.md`,
`experiment_results/metodo_analitico_cloud_20261026.md` e
`Tesi-latex/qoder-bozza/references.bib`. Le decisioni restano dell'utente; qui si registra
**a quali condizioni sono ancorate**.

**Esito in una riga.** Le quattro scelte sono adottate. Sette affermazioni che le
accompagnano non sono riprodotte dalle fonti e sono corrette qui, con etichette A-G: una
citazione bibliografica sbagliata (l'articolo sbagliato, già ritirato il 26-10), un
perimetro rovesciato rispetto alla fonte, un intervallo di sensibilità già ritirato dalla
spec con un estremo privo di fonte, un'affermazione di copertura (idle NIC dentro la
baseline CPU) che il codice smentisce, una soglia `MAPE ≤ 15%` senza ancora, una collisione
di nomi fra la scala di provenienza e i punti del protocollo, e un delta di sei colonne che
ne omette nove già deliberate. A queste si aggiunge un fatto di **stato**, non di metodo:
P5 è stato dichiarato congelato a metà seduta (`f834691`, 22:36) con lo schema così com'è,
quindi il difetto G non è più un pendente: è una caratteristica dello schema congelato, e si
corregge con un'emendamento o con una riapertura, non in silenzio (§4, §5).

---

## 1. Punto 1 — perimetro e confine di `E_rete`

**Adottato.** Il confine è quello della fonte di ordine più alto disponibile e il valore
nominale resta `2,7e-6 J/bit` (`cwEnergyModular/config.py:371`, con il commento a
`:332-369` e il valore di confronto `NETWORK_ENERGY_COEFFICIENT_DEFAULT_J_PER_BIT` a `:370`,
tutto committato oggi fra `2a448d0` e `f0cfecc`). Nota di margine: la spec cita quel blocco
come `config.py:332-362` e la costante come `:363` — numeri veri fino a `2a448d0`, scostati
di +7/+8 dopo le dieci righe aggiunte da `f0cfecc`. È lo stesso invecchiamento registrato
oggi dalla nona emenda del protocollo, ed è il motivo per cui questo documento ancora i
numeri di riga a un commit (`ab30fa0`/`b918959`) invece che a "com'è il file".
L'aggettivo **"conservativo" è ritirato**:
su questo la richiesta ha ragione, e il ritiro è una **dichiarazione nuova di questo
audit**. Gli ancoraggi già scritti dicono che il coefficiente è "documentato ma non
validato" con perimetro dichiarato (`metodi_per_dominio_20261025_spec.md:702-707`), che
"non è una misura diretta dell'energia di rete" (`spec:1071-1073`), e che `eps_bit` è un
valore adottato non confrontabile (`metodo_analitico_cloud_20261026.md:394-400`); nessuno
dei tre usa la parola "conservativo", quindi il ritiro non contraddice nessuna frase
esistente — aggiunge un divieto d'uso.

**Aritmetica verificata.** `2,7e-6 J/bit × 8·10⁹ bit/GB = 21.600 J/GB = 21,6 kJ/GB =
6,0e-3 kWh/GB` (GB decimale). Corretto, e coincide con `spec:1075-1078`, che aggiunge
21,6 J su 1,0 MB decimale e 22,649 J su 1 MiB.

**Correzione A — la citazione è l'altro articolo.** La richiesta attribuisce `2,7 µJ/bit`
a "Baliga et al. 2011, IEEE Network". La fonte primaria verificata è J. Baliga, R. W. A.
Ayre, K. Hinton, R. S. Tucker, *Green Cloud Computing: Balancing Energy in Processing,
Storage, and Transport*, **Proceedings of the IEEE** 99(1):149-167, 2011, DOI
`10.1109/JPROC.2010.2060451`, eq. (2) a p. 7 e valore a p. 8 — chiave bib
`baliga2011green` (`references.bib:971-980`). L'articolo IEEE Network 25(2):6-12, DOI
`10.1109/MNET.2011.5730522` (chiave `baliga2011power`, `references.bib:986-995`) **non
contiene `2,7 µJ/bit`**: porta efficienze per apparato (≈10 nJ/bit sul livello IP, 1-3
nJ/bit SDH, <1 nJ/bit WDM). La nota in `references.bib:982-985` lo dice alla lettera e
conserva la voce come memoria storica: "fino al 26-10-2026 il progetto citava questo
articolo al posto di `baliga2011green`". Riproporre IEEE Network riapre l'errore appena
chiuso, ed è probabilmente l'origine del vecchio valore `3,4e-8 J/bit`, che sta sulla scala
dei ~10 nJ/bit di quell'articolo.

**Correzione B — il perimetro è l'opposto di "intera catena end-to-end".** La fonte
esclude **esplicitamente la rete di accesso** e esclude server, storage e processing;
include metro Ethernet, switch LAN del data center, BNG, provider edge, gateway del DC,
router di core e WDM, con ridondanza ×2, raffreddamento ×1,5 e utilizzazione <50% ×2
(`spec:1079-1097`). La richiesta elenca "accesso broadband" fra ciò che il coefficiente
modella: non c'è. E il disallineamento con i nostri byte — system-wide sul client, quindi
con traffico di terzi non separabile — è dichiarato, non risolto (`spec:702-707`).
In termini di provenienza, `eps_bit` è **P3 `value-adopted`**, non P4 e non una misura: è
già scritto in `metodo_analitico_cloud_20261026.md:394-400`, con la riclassificazione del
26-10.

**Correzione C — l'intervallo `[0,46 ; 20,0]` µJ/bit è già ritirato, e il suo estremo alto
non ha fonte.** `spec:1099-1111` lo tratta per disteso: `0,46 µJ/bit` è lo scenario "cloud
privato" dello **stesso** articolo (eq. 1, p. 7), perimetro e utilizzazione diversi;
`27 µJ/bit` è Aslan et al. 2018, `0,06 kWh/GB` riferito al **2015**, perimetro "core +
accesso fisso" con data center e dispositivi di bordo esclusi, stima da aggiornamento di
Krug et al. 2014 su dati BT UK; `20,0 µJ/bit` — l'estremo che la richiesta porta come
limite superiore — **non ha una fonte nel repository** e non va usato: `config.py:359` lo
scrive già alla lettera ("20,0 uJ/bit = nessuna fonte nel repository: non va usato come
limite"), e il ritiro è registrato come esito F7/D8 in `spec:1249` e `spec:1269`. Nessuno
dei due è un
limite dello stesso estimando, e i perimetri vanno in direzioni opposte: Baliga include gli
switch del DC ed esclude l'accesso, Aslan include l'accesso ed esclude il DC. La forma
corretta, per la tesi: il valore adottato con il suo perimetro, più **due scenari esterni
etichettati** (`0,46` e `27 µJ/bit`), mai presentati come banda di incertezza. Vale anche
la conseguenza che la richiesta cercava di evitare: `27 µJ/bit` sta **10 volte sopra**
`2,7 µJ/bit`, quindi il numero adottato non è conservativo, è basso rispetto alla
meta-analisi. Questo rafforza il ritiro dell'aggettivo, non lo indebolisce.

**Correzione D — l'idle della NIC non rientra nella baseline del package.** La richiesta
scrive che `P_idle,NIC` "rientra nella baseline di idle del Package CPU misurata pre-blocco
(`P_idle`)" e che quindi non servono costanti arbitrarie. Il codice dice il contrario due
volte: i domini leggibili sono `DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")`
(`energy/emi_backend.py:73`) e non esiste un dominio NIC; e il docstring del modulo di rete
(committato oggi, `energy/network_energy.py:38-39`) chiude i confini con "l'energia della
NIC del client e quella della rete di accesso **non sono contate da nessuno dei due
lati**". La decisione — non aggiungere una costante di idle non misurata — è giusta e la
mantengo; la **ragione** va riscritta: l'idle NIC è **fuori confine e dichiarato fuori
confine**, non dentro la baseline. Presentarlo come coperto da `P_pre` sarebbe una
copertura inventata, cioè il tipo di claim che P4.7 e
`thin_support` esistono per impedire.

---

## 2. Punto 2 — provenienza di `C5` e condizioni per la promozione

**Adottato.** `C5` nasce come stima di ipotesi, si presenta come costo di riferimento su
infrastruttura di riferimento (H100, steady state) e non come misura del provider, e non
diventa "calibrato" finché non passa una calibrazione reale. La frase fissa del confine è
già in `metodo_analitico_cloud_20261026.md:444`: "acceleratore di riferimento H100, serving
open-source, steady state; non il hardware del provider".

**Verificato.** La scala di provenienza esiste ed è quella citata: quattro livelli, e solo
il primo autorizza la parola "calibrato" (`metodo_analitico_cloud_20261026.md:384-392`):
`P1 fit-raw-holdout`, `P2 fit-published-transcribed`, `P3 value-adopted`, `P4 hypothesis`.
Quindi "C5 nasce a P4" e "promozione a P1" sono corretti **nella scala di provenienza dei
coefficienti**.

**Correzione E — i simboli della scala collidono con i numeri dei punti congelati.**
"Stato P4" e "livello P1" sono anche P4 (incertezza e validazione) e P1 (baseline) del
protocollo v4, che in questa stessa seduta ha ricevuto la sua nona emenda: `P1`/`P4` sono
quindi due cose diverse in due tassonomie sovrapposte. Nel documento di audit metrologico e
nella tesi la promozione va scritta con **l'etichetta**, non col numero:
`hypothesis → fit-raw-holdout`. Non è una pignoleria, è una strada già percorsa: lo stesso
simbolo collide una seconda volta sui gate, perché `G4` è il gate di validazione per dominio
(`spec:341`) **e** il nome che la spec usa per la catena dei sei anelli di P4.9
(`spec:100`, `spec:413`) — il quinto turno di revisione esterna ha respinto una proposta
proprio per questa ragione.

**Correzione F — la soglia `MAPE ≤ 15%` non ha ancora, e il test non è "LOO" generico.**
Ricercata in `metodi_per_dominio_20261025_spec.md`, `metodo_analitico_cloud_20261026.md`,
`valutazione_20261026_cloud2_docx.md` e `valutazione_20261026_progetto_cloud.md`: **nessun
15%**. Il numero che circonda è un altro: EcoLogits dichiara MAPE medio **1,79%** sul
proprio fit di tabella (`metodo_analitico_cloud_20261026.md:187`), che è la performance
*pubblicata* di C2, non una soglia nostra. La spec prescrive di **riportare** il
`loo_mape` per classe insieme ai coefficienti, senza soglia numerica
(`metodo_analitico_cloud_20261026.md:420-424`). Due conseguenze operative:

1. il test è **leave-one-model-out per classe**, non leave-one-point-out: tenere fuori
   modelli interi è l'unica prova che il coefficiente di classe generalizza, che è
   esattamente l'affermazione che C5 fa quando il modello richiesto non è nel registro;
2. `15%` come soglia è una **decisione dell'utente registrata qui**, non un ancoraggio:
   AGENTS.md chiede che le soglie siano congelate prima dei dati **con la loro ragione**.
   Finché la ragione non è scritta, la soglia **non** entra come criterio di accettazione:
   `C5` resta `hypothesis` e il `loo_mape` si riporta, come fa la spec.

**Limite operativo da dichiarare insieme alla soglia.** La promozione a
`fit-raw-holdout` oggi **non è eseguibile su questo host**: il dataset grezzo
`ml-energy/benchmark-v3` è gated e `huggingface_hub.whoami()` dà `LocalTokenNotFoundError`
(verificato 26-10, `metodo_analitico_cloud_20261026.md:407-409`). Un criterio di
promozione non ancora eseguibile non deve diventare la ragione per cui C5 non viene usato:
C5 entra come costo di riferimento etichettato, e la soglia si applica quando il fit esiste.

---

## 3. Punto 3 — file di produzione: lo stato è cambiato durante la seduta

**La premessa del punto non descrive più il repository.** Il punto 3 chiede che le modifiche
pendenti a `cwEnergyModular/config.py` e `cwEnergyModular/energy/network_energy.py`
entrino nel commit atomico di P5. Quelle modifiche **sono già committate da oggi** —
`2a448d0` "Rete P5: fisiche per default, letture degradate mai zero, segno grezzo
conservato" (22:18) porta `config.py`, `energy/network_energy.py` e il nuovo
`tests/test_rete_nic_confine.py`; `768eb80`, `f3a6924` e `ab30fa0` portano il percorso cloud.
`git status` non segnala più alcun file tracciato come modificato. Non ho committato né
toccato nulla di tutto questo, e non l'ho ripristinato: registro solo che la decisione 3,
così come scritta, è un'istruzione su uno stato che non esiste più. Va detto anche
l'altro: il punto 3 parla di un **commit atomico**, e il lavoro è arrivato in sei commit
distinti, ciascuno con il suo messaggio — che è la convenzione di AGENTS.md ("un commit
per punto"), non una deviazione, ma non è il commit atomico descritto nella richiesta.

**Resta vera, e si può verificare, la sostanza del punto 3.** Il difetto che avevo segnalato
("tre confini diversi per lo stesso coefficiente") è chiuso nel codice committato, e il
modo in cui è chiuso è più forte della semplice coerenza di testo: il perimetro della fonte
è scritto **una volta sola**, nella funzione `network_coefficient_provenance()`
(`energy/network_energy.py:95-123`), che restituisce la stringa con "access network excluded
by the source, servers/storage/processing excluded" e, quando il valore è sovrascritto da
`CW_NET_J_PER_BIT`, restituisce un altro testo che **ritira la citazione** ("NOT Baliga et
al. 2011"). Le due strade di risultato appendono quella stringa
(`:364`, `:392`), quindi non esiste più un secondo posto dove il confine possa divergere. Il
docstring del modulo (`:10-19`) e il commento di `config.py:332-362` dicono la stessa cosa
in linguaggio diverso, e la riga CSV riporta il confine applicato in
`network_measurement_boundary` (`casualwatt_csv_export.py:44`).

**Residuo che il congelamento di P5 non ha assorbito: la duplicazione è nel nome della
colonna, non nel testo.** Il CSV e il runner usano `cloud_estimation_boundary`
(`casualwatt_csv_export.py:47`, `benchmark_unified.py:1166`); la spec di C5 introduce
`cloud_measurement_boundary` (`metodo_analitico_cloud_20261026.md:444`); la rete ha invece
`network_measurement_boundary`. Stesso oggetto, due nomi, e i due nomi dicono cose diverse:
"estimation" dice che il numero è stimato (vero anche per C2-C4, che non misurano nulla),
"measurement" dice quale confine ha la misura (che per C5 non esiste). La scelta è di
convenzione, non di fatto, e ora ha un costo: il freeze è arrivato con `f834691`, quindi
allinearla vuol dire rinominare una colonna di uno schema congelato. Il progetto ha già un caso di doppia tassonomia da riconciliare (regola 9 della
spec contro regola 12.1 del codice) e non ne aggiunge una seconda.

**Ancoraggi che hanno smesso di essere fragili, e due che no.** La spec cita
`config.py:332-362` e `config.py:363`: con `2a448d0` quei numeri corrispondevano a HEAD, non
più all'albero sporco — quindi il rischio "si rompono al commit" è scaduto; con `f0cfecc`,
che ha aggiunto dieci righe allo stesso commento, sono tornati a non corrispondere (blocco
`:332-369`, costante `:371`). Vale però la lezione opposta, registrata oggi dalla nona
emenda del protocollo: gli ancoraggi di riga di un documento che si auto-emenda invecchiano
in silenzio, e qui l'esempio è interno al codice. L'ancoraggio
`cloud_energy.py:159-166` che la spec stessa cita per la nota B4 era già falso prima di
oggi: a `f834691` quelle righe sono la funzione `_value_of`, e la nota B4 sta a
`energy/cloud_energy.py:35` (docstring) e `:389-392` (il commento che decide il campo,
spostato da `ab30fa0`). Il percorso, inoltre, è `energy/cloud_energy.py`, non
`cloud_energy.py`.

---

## 4. Punto 4 — delta di sei colonne nello schema CSV

**Le sei colonne non sono più una proposta: sono nel codice committato.** `f3a6924` le ha
aggiunte a `CSV_COLUMNS` (`casualwatt_csv_export.py:170-180`, con il commento che dice cosa
è ciascuna) e le scrive il runner. Quindi il controllo che conta non è più "entrano o no",
ma **se ogni colonna ha un produttore che la sa riempire**, perché una colonna senza
produttore si riempie del valore di default e mente meglio di un'assenza. Su questo il
verdetto è favorevole: sei su sei hanno un produttore, e due avevano un produttore che ieri
davo assente.

| colonna | contenuto richiesto | produttore a `f834691` | esito |
|---|---|---|---|
| `cloud_input_tokens_included` | `false` per Tier 1, `true` per Tier 2 | sì, ma **oggi solo `False`**: il runner lo scrive costante a `benchmark_unified.py:389`, perché `llm_impacts` accetta solo `output_token_count` e `request_latency` (nota B4, `energy/cloud_energy.py:35` e `:389-392`, verificata **eseguendo la chiamata** il 26-10). Il `true` di C5 è **prospettico**: `analytic-class-fit` non esiste ancora nel codice (zero occorrenze in `cwEnergyModular/`) | **adottata**, e giustifica l'asimmetria del gate G3: lo scarto C5 contro C2 non è "accordo fra due stime dello stesso lavoro", è perimetro diverso (`metodo_analitico_cloud_20261026.md:442`) |
| `cloud_pue_applied` | valore effettivo di PUE | **sì, e qui correggo me stesso**: ieri scrivevo che `cloud_energy.py` non lo estrae. Da `f3a6924` lo estrae: `_provider_pue` (`energy/cloud_energy.py:179-206`) legge `PROVIDER_CONFIG_MAP[…].datacenter_pue` e lo porta in `pue_applied` (`:462`). Il valore è ancorato: la sonda dei clamp riproduce `2,985238380999223e-04` kWh, che è esattamente PUE `1,09` (`metodo_analitico_cloud_20261026.md:311`) | adottata, **con un caveat nuovo da chiudere in P5**: per i provider a banda (Anthropic, Hugging Face) lo scalare è il **punto medio** `(min+max)/2` (`:197-200`) e la natura del numero viaggia solo in una nota (`:433`, "punto medio della banda […]"). Da sola, la colonna non dice che quel PUE è una sintesi |
| `cloud_pue_source` | `provider_catalog_ecologits` vs `default_hyperscale_assumption` | realizzata con `"provider_catalog_ecologits"` **oppure stringa vuota** (`:463`), con la ragione in docstring: "meglio un campo vuoto che un PUE inventato" (`:187`). La seconda etichetta non esiste, ed è corretto: appartiene a C5, che non ha ancora percorso | adottata **a condizione** che, quando C5 arriva, il valore porti numero + fonte, non l'aggettivo "hyperscale assumption" (la dicotomia è reale: `metodo_analitico_cloud_20261026.md:238-239`) |
| `cloud_latency_used_s` | latenza entrata nel calcolo | sì: `_latency_diagnostics` (`:209`) → `latency_used_s` (`:464-465`), con `N/A` quando `None` (`benchmark_unified.py:369-371`). È la latenza **effective**, diversa da `duration_s` quando il `min()` di `impacts/llm.py:99-102` troncava (`metodo_analitico_cloud_20261026.md:443`) | adottata |
| `cloud_latency_threshold_s` | `n_out/tps + ttft` | sì, **con la formula solo dove è la formula**: il commento del codice dice che su 157 schede su 344 la soglia è `n_out/tps + ttft`, sulle altre 187 gira la regressione del motore (`energy/cloud_energy.py:397-405`; conteggio e soglia `17,4612 s` a 200 token in `metodo_analitico_cloud_20261026.md:134-140`, con le due sonde tracciate `probe_ecologits_gpu_steps_moe_20261026.py` e `probe_ecologits_clamp_20261026.py`) | adottata. Il requisito della richiesta — `N/A`, non `0` — è soddisfatto: `_na_or` produce `N/A` e la **ragione** esce in una nota dedicata (`:426-430`, "soglia … non determinabile dalla scheda") |
| `cloud_latency_binding` | `true` se il clamp è stato vincolante | sì, per **due salti**: il motore interno registra quale termine ha vinto come stringa (`latency_binding`, `:468`), il runner la converte in booleano (`benchmark_unified.py:397`) e la lascia **vuota** quando la soglia non è determinabile. Il default `false` non è mai scritto | adottata, con la clausola della richiesta rispettata per costruzione |

**La regola "nessun falso zero" è implementata meglio di come la richiesta la scrive.** Il
codice distingue tre stati, non due: `N/A` per un numerico che non c'è, stringa vuota per un
campo che quella riga non lo riguarda affatto (è il caso delle righe locali, `benchmark_unified.py:509-516`, dove
il commento spiega che nessun motore cloud è stato interrogato, quindi non c'è né banda né
latenza da descrivere), e `True/False` solo dove il fatto esiste. La richiesta parla di "`N/A`
non `false`", che è la stessa preoccupazione espressa con due stati. P5 è stato congelato con `f834691`, quindi la parte che resta da fare è scrivere la
**convenzione** di quei tre stati accanto allo schema: quale stato significa cosa, e che
`""` non è un valore mancante ma un valore di dominio. Il principio invece è già rispettato.

**Correzione G — l'elenco di sei colonne ne omette nove già deliberate, e una di queste
manca mentre il suo prerequisito è già in schema.** Il delta della richiesta è un sottinsieme
del registro di `metodo_analitico_cloud_20261026.md:432-446`, che chiede già, marcati "no,
nuovo": `cloud_coefficient_provenance`, `cloud_calibration_source`, `cloud_fit_loo_mape`,
`cloud_fit_terms`, `cloud_moe_active_assumption`, `cloud_active_parameters_b`,
`cloud_total_parameters_b`, `cloud_energy_band_semantics`, `energy_available` (con
`cloud_unavailable_reason`). Verifica sul codice: **nessuna delle nove è in `CSV_COLUMNS`**,
e `cloud_energy_band_semantics` esiste solo come testo dentro una nota
(`energy/cloud_energy.py:442`). Il punto non è teorico, perché `cloud_energy_min_j` e
`cloud_energy_max_j` **sono già colonne** (`casualwatt_csv_export.py:73`) e il runner le
riempie (`benchmark_unified.py:387-388`): la riga pubblica oggi una banda senza dire cosa
quella banda significa, che è esattamente il divieto scritto nel registro
(`metodo_analitico_cloud_20261026.md:445`: "nessuna riga puo' avere una colonna min/max senza
questo campo"). Per C2-C4 il significato è `parameter_pue_ignorance_range`, per C5 sarebbe
`calibration-semi-range`: sono due cose diverse e oggi la riga non le distingue. E
`cloud_coefficient_provenance` è il campo che implementa la decisione 2: senza di esso lo
stato `hypothesis` di C5 non esiste nella riga, esiste solo nel documento.

**La conseguenza del freeze.** Con `f834691` lo schema è congelato com'è, quindi G non è più
un'integrazione in attesa: è una proprietà dello schema congelato. Correggerlo vuol dire
emendare P5 — la stessa via usata oggi per P4 con la nona emenda — o riaprire il punto; non
vuol dire completare in silenzio un lavoro aperto, che è il modo in cui questo difetto
sarebbe passato.

---

## 5. Cosa congela questo documento e cosa no

**Congela.** Il confine di `E_rete` come perimetro Baliga *Proc. IEEE* 2011 con la rete di
accesso esclusa; la provenienza `P3 value-adopted` del coefficiente; il ritiro
dell'aggettivo "conservativo" (dichiarazione di questo audit) e dell'intervallo
`[0,46 ; 20,0]` µJ/bit come banda (già ritirato in `spec:1109-1111`); l'esclusione
dichiarata dell'idle NIC, con la ragione vera — fuori confine, non dentro `P_pre`; lo stato
`hypothesis` di C5 con presentazione da costo di riferimento; il traguardo
`fit-raw-holdout` subordinato a leave-one-model-out per classe, con il limite operativo di
G0; l'adozione delle sei colonne diagnostiche perché verificati i loro produttori; e la
regola dei tre stati (`N/A` per un numerico assente, `""` per un campo che non riguarda la
riga, `True/False` solo dove il fatto esiste).

**Non congela.** La soglia numerica di promozione, che aspetta il suo motivo; la convenzione
del nome `..._estimation_boundary` contro `..._measurement_boundary`; l'elenco completo delle
colonne — comprese le nove strutturali del registro e la decisione che una riga con
`cloud_energy_min_j`/`_max_j` senza `cloud_energy_band_semantics` è una riga illeggibile, che
dopo `f834691` è un **emendamento** di P5, non un completamento; e qualunque modifica a
`config.py`, `energy/network_energy.py`, `energy/cloud_energy.py`, `cloud_estimator.py` o
`casualwatt_csv_export.py`.

**Le quattro decisioni che restano all'utente, con la forma minima che le rende verificabili.**

1. **Soglia di promozione.** O `MAPE ≤ 15%` entra con la sua ragione (perché 15 e non 10 o
   20, su quale distribuzione di modelli di classe, prima dei dati), o resta un numero
   riportato senza potere di accettazione. Nel primo caso serve anche la conferma che il test
   sia leave-one-**model**-out per classe, come scrive `metodo_analitico_cloud:420-424`, e non
   leave-one-point-out.
2. **Nome della colonna di confine.** Due strade equivalenti: emendare la spec C5 perché usi
   `cloud_estimation_boundary` (il nome già in schema), o rinominare la colonna. La scelta va
   scritta da qualche parte con la ragione, perché gli artefatti che citano il nome vecchio
   sono più d'uno.
3. **Le nove colonne strutturali, o un motivo per non farle entrare.** La più urgente è
   `cloud_energy_band_semantics`: senza di essa lo schema congelato pubblica bande il cui
   significato non è nella riga. `cloud_coefficient_provenance` è la seconda, perché è
   l'unico posto dove la decisione 2 diventa un dato.
4. **Gli ancoraggi dei due documenti cloud.** Circa quaranta citazioni `file:riga` in
   `metodi_per_dominio_20261025_spec.md` e `metodo_analitico_cloud_20261026.md` sono state
   scritte contro il codice di ieri; due di esse (`config.py:332-362`/`:363` e
   `cloud_energy.py:159-166`) sono già false a `f834691`. La decisione di forma — rendere gli
   ancoraggi verificabili da uno script o sostituirli con etichette stabili — è registrata
   come aperta dalla nona emenda del protocollo e non è ancora presa.

**Lo scarto di stato, e come si è chiuso mentre scrivevo.** La richiesta chiude dicendo che
"l'architettura per Rete ed Cloud è congelata ed è pronta per la finalizzazione del commit
atomico P5". A metà di questa seduta quella frase è diventata vera per i fatti e falsa per il
testo, poi vera anche per il testo: i sei commit di codice sono entrati fra le 22:18 e le
22:28 (`2a448d0`, `768eb80`, `f3a6924`, `ab30fa0`, `f0cfecc`, `c1f9161`) mentre la riga P5 del
protocollo diceva ancora **aperto** — e AGENTS.md tiene il codice bloccato fino al
congelamento di P5 — poi `f834691` (22:36) ha scritto **congelato 2026-10-26** in quella riga
(`protocollo_v4_20261024.md:15`), chiudendo la questione in senso opposto a quello che davo
io dieci righe più sopra. Registro due cose, non una: (1) il congelamento di P5 è un atto del
protocollo, non una proprietà di questo audit, e infatti l'audit non l'ha prodotto; (2) la
sequenza contata dal protocollo adesso è quella che conta per il difetto G — lo schema è
chiuso a `CSV_COLUMNS` di 168 nomi senza nessuno dei nove campi strutturali del registro
C5, quindi correggere G vuol dire emendare P5, non completare un lavoro aperto.

Verifiche eseguite in questa seduta. Sui testi: `grep` sui quattro artefatti di
spec/valutazione per `MAPE`, `15%`, `PUE`, `boundary`, `0,46`, `20,0`, `27 uJ/bit`,
`conservativ`, `gated`, `LocalTokenNotFound`; `references.bib:971-1008`; `DOMAIN_NAMES` a
`energy/emi_backend.py:73`. Sul codice a `b918959`: `CSV_COLUMNS`
(`casualwatt_csv_export.py:38-73` e `:170-180`), `_na_or`/`_cloud_estimate_fields`
(`benchmark_unified.py:369-398`), `_provider_pue`/`_latency_diagnostics`
(`energy/cloud_energy.py:179-206`, `:209`), `network_coefficient_provenance`
(`energy/network_energy.py:95-123`), e la ricerca di `analytic-class-fit` (zero occorrenze).
Sul versionamento: `git log`/`git show --stat` dei sei commit, `git status` a tree pulito.
Esecuzione: `python -m pytest cwEnergyModular -q` → **401 passed, 3 skipped in 8.49s**
(404 raccolti, allineato ad AGENTS.md dopo `b918959`). Nessun run di misura: nulla di questo
documento dipende da dati sperimentali, e nessun file di codice è stato modificato.
