# Metodi per dominio e catene di fallback — specifica operativa, 2026-10-25 (rev. 28/10)

Questo documento definisce, per ogni combinazione di sistema operativo,
produttore e dominio fisico, il metodo primario, i fallback successivi,
l'etichetta che ogni livello deve portare e lo stato di evidenza al 28/10/2026.
La revisione del 27/10 aggiunge §4.2, che rilegge otto documenti esterni contro
il codice e produce la matrice dei backend e dei fallback: le regole non
cambiano, cambiano le righe, che dichiarano anche i livelli [P] e i percorsi
rifiutati.
La revisione del 28/10 aggiunge la catena GPU — NVML `energy` con ripiego
sull'integrale della potenza, poi AMD SMI come fallback dichiarato — e le tre
colonne per token in coda al CSV. Nella stessa data C5 entra nella catena cloud
come fallback finale (`C1 -> C2 -> C4 -> C3 -> C5 -> unavailable`, §3.4 e §6):
e' l'allineamento con `metodo_analitico_cloud_20261026.md`, che dichiarava di
superare questo documento solo per il dominio cloud, e chiude il punto aperto
n. 2 della sezione 1.5.
Nasce dalla valutazione di `metodiLoc.DOCX`
(`metodi_loc_20261025_valutazione.md`) e la completa: la valutazione dice cosa
del documento esterno non si adotta, questa specifica dice cosa si usa, in che
ordine e con quale nome.

**Legenda di stato.** Ogni colonna "stato" usa quattro marcatori, combinabili:

| marcatore | significa |
|---|---|
| `[I]` | implementato nel codice |
| `[V]` | esercitato su hardware o sistema reale, con l'esito registrato |
| `[P]` | progettato, non implementato |
| `[A]` | assente, oppure `unavailable` |

`[I][V]` significa le due cose in congiunzione. Nessun marcatore e nessuna
combinazione dice quanto il numero sia vicino alla grandezza vera: quello lo
dice solo G4 con i sei anelli di P4.9. "Implementato" non significa
"esercitato"; "esercitato" non significa "validato".

La differenza fra `[I]` e `[P]` e' la presenza del codice, non quella della
prova: un percorso che il codice ha e che questo host non permette di
esercitare si scrive `[I]` con `[V] da fare` — la catena GPU NVML e AMD SMI
e' in questo caso, perche' qui non c'e' ne' una NVIDIA ne' una AMD.
`[P]` resta riservato al percorso **progettato e non implementato**: non si
usa `[P]` per dire "non ancora provato su hardware reale".

**Statuto.** E' un documento normativo per il progetto, non per il codice: dal
congelamento di P5 (2026-10-26) il sorgente di produzione e' sbloccato, ma questa
specifica non e' una specifica di codice. Non sostituisce
P4.9 e non introduce una seconda tassonomia nel CSV: i livelli M1-M4 sono una
lente documentale, l'arbitro per riga resta il token di metodo. La parola
"validato" ha un solo significato, quello di P4.9
(`protocollo_v4_20261024.md:2084-2128`); qui si dice solo quale canale si puo'
usare e con quale etichetta.

**Data e albero delle verifiche.** Le affermazioni sul codice e sulle fonti
esterne sono verificate al 25-26/10/2026, le fonti esterne alla fonte primaria
con la data scritta accanto a ciascuna. Le righe toccate dalla revisione EMI del
27/10/2026 (E1, §3.1.1, §4.1 riga 26, F10/F11/F13, D17 e gli ancoraggi EMI)
sono riverificate contro l'albero dei commit `544176a` e `ea117ac`. Gli
ancoraggi `file:riga` puntano
pero' all'**albero di lavoro**, non a un commit: la branca `emenda-8` porta
modifiche non committate su `energy/energy_session.py`, `energy/local_energy.py`,
`casualwatt_csv_export.py`, `AGENTS.md` e su vari test (1313 righe aggiunte e 186
rimosse rispetto a HEAD alle 14:14 del 26/10 -- dodici minuti prima erano 1275 e
168: il conteggio cresce mentre questo documento si scrive). Un numero di riga
citato da un albero sporco non e'
riproducibile da chi clone il repository: gli ancoraggi di questo documento vanno
ricontrollati contro il commit che P5 congela. E' un limite dichiarato, non un
risultato, e la nota di salvaguardia resta: le modifiche non si stashano ne' si
resettano, si rivalidano e si committano in modo atomico al gate di P5.

Un effetto visibile dell'albero sporco, registrato qui perche' e' uno stato e non
una ipotesi: `python -m pytest cwEnergyModular -q` alle 14:14 da' **1 failed, 364
passed, 3 skipped**, e il fallimento e' `tests/test_dump_node_id.py::
test_il_frammento_piu_lunguo_del_verbale_sta_in_un_segmento` -- un test di
impaginazione dell'Appendice D, non di misura. Cade perche' i 351 insert non
committati di `test_validazione_valutazione.py` aggiungono casi parametrizzati con
etichette stringa lunghe ("free_text fallback lessicale sopra 0.85"), che finiscono
per intero nel node id e quindi nella prima colonna della tabella LaTeX; il
generatore inserisce punti di capo su underscore e trattini
(`tools/dump_tests_latex.py:69-83`) ma non sugli spazi. La stessa condizione e'
gia' descritta, dal loro autore, nel commento non committato di
`tests/test_dump_node_id.py`: "un parametro stringa lungo finisce node-id per
intero ... e il guard cade, come e' caduto il 26/10 alla prima esecuzione di
questi test". Su `HEAD` l'etichetta incriminata non esiste: `git show
HEAD:cwEnergyModular/test_validazione_valutazione.py` non contiene nessuno dei
parametri stringa aggiunti nell'albero di lavoro, e il commit `027609c` riporta la
suite a "343 passati + 3 saltati". Nessuna catena di questo documento
dipende da quel test, e nessun numero di misura e' toccato.

Il fallimento e' chiuso nella stessa seduta, e chiuso dalla parte giusta: le
etichette parametrizzate di `test_validazione_valutazione.py` sono state riscritte
con l'underscore al posto dello spazio (`free_text_fallback_lessicale_sopra_0.85` e
via cosi'), perche' il generatore spezza su underscore e trattini (`:69-83`) e non
sugli spazi. Il limite del guard resta **26 caratteri, invariato**: nessuna soglia e'
stata mossa per far passare un test, e' stato accorciato l'identificatore che la
sfondava. A valle della riscrittura `pytest cwEnergyModular` raccoglie **368 = 365
passati + 3 saltati**.

Una cosa e' sistemata, e qui si registra per non lasciare un falso allarme: la
sonda citata in §4.1 come fonte delle ragioni di G0 era fuori dal repository. Ora
`probes/cw_probe.py` e il suo output `probes/cw_probe_windows.json` sono
**tracciati** (commit `bb32e26`, 26/10: `mv` senza riscrittura, byte identici al
file del 25/10), perche' AGENTS.md chiede che un harness il cui esito e' citato
sia riproducibile. Con lo stesso criterio, alle 14:20, e' tracciata anche la
seconda sonda di oggi -- `probe_ecologits_release_drift_20261026.py` con il suo
output `experiment_results/ecologits_drift_console_20261026.txt` (commit `ef25987`)
-- perche' il numero di deriva fra release che §6 ora cita e' prodotto li', non da
una lettura. Con le verifiche obbligate di fine sessione (CVE-2020-12912, `perf`,
deriva EcoLogits, EMI su Windows 10: §3.1 e §Appendice "Fonti esterne") restano
aperte, perche' non chiudibili senza macchina o senza scelta, il kernel 5.11 di
arrivo del powercap AMD, la release che porta gli eventi RAPL AMD in `perf`, e i
parametri della presa intelligente non ancora scelta.
Nello stato dell'albero resta invece un secondo effetto
collaterale da tenere d'occhio: su questi stessi percorsi sta lavorando in
parallelo un'altra sessione (i commit `027609c`, `9ef63ac`, `6948e0d` di oggi
mattina toccano codice, test e questa stessa specifica). Due editors sullo
stesso file significano che un ancoraggio `file:riga` qui citato puo' spostare il
numero senza che questo documento cambi: al gate di P5 gli ancoraggi si
riverificano, uno per uno, e non si ereditano.

**Fonti.** Codice in `cwEnergyModular/`; protocollo v4; gli artefatti tracciati
in `experiment_results/`; `PIATTAFORME_METODI.md` e `METODI_E_FORMULE.md` in
`Tesi-latex/qoder-bozza/` sono documenti di progetto **fuori da git**: si
citano come provenienza, non come riferimenti consultabili nel repository.
`metodiLoc.DOCX` resta uno spunto, non evidenza.

---

## 1. L'unita' di decisione e' il dominio, non la macchina

La configurazione non e' "Windows 11" ne' "i9-13900HK": e' la tupla

    (sistema operativo, produttore, dominio, interfaccia disponibile)

I domini trattati sono:

| dominio | che cosa e' | note di confine |
|---|---|---|
| `cpu_package` | package della CPU | include core, uncore e, **sulle CPU Intel provate**, anche la iGPU; sulle APU AMD la relazione iGPU/package non e' verificata |
| `gpu_dedicated` | scheda grafica dedicata | NVIDIA, AMD, Intel; whole-device, non per processo |
| `npu` | unita' neurale | integrata nel package oppure discreta; oggi non separabile |
| `cloud_server` | il server remoto che esegue l'inferenza | fuori dal computer locale |
| `network` | trasporto dei byte fra client e server | solo lato client, non la rete intermedia |

La iGPU **su Intel** e' dentro `cpu_package`: e' verificato sul host (PKG
include il dominio PP1, `energy/emi_backend.py:20-23`) e dichiarato anche dal
sensore LHM "CPU Package". Sulle **APU AMD** la stessa relazione non e'
verificata: va provata, e fino ad allora il confine della riga AMD dice "iGPU
in package: non verificato".

La DRAM **non e' un sottoinsieme** di PKG: nelle definizioni RAPL e' un dominio
distinto, e CodeCarbon la gestisce come "misura diversa, mai un duplicato",
esclusa di default (`include_dram=False`, verificato il 26/10 su
`docs.codecarbon.io/latest/explanation/rapl/`). La regola corretta e' quindi
due righe diverse: PP0 e PP1 sono sottoinsiemi di PKG e **non si sommano**;
DRAM e' un dominio a parte, **si riporta a parte** e si somma solo se la somma
e' dichiarata come tale. Sul nostro host client DRAM legge spesso zero
(`energy/emi_backend.py:21`), quindi oggi i numeri non cambiano: cambia la
regola, non il dato.

Non esiste "la misura del computer": esiste la misura di un dominio, e il
sistema completo solo come riferimento esterno.

Conseguenza operativa: una misura CPU valida resta valida anche se GPU e NPU
non hanno telemetria; l'assenza di un dominio non degrada gli altri.

---

## 1.5 Partizione fra blocco locale e blocco remoto

**Punto #1 della definizione finale, chiuso il 2026-10-26.**

**Decisione in una riga.** I metodi si dividono per **natura della sorgente del
numero**, non per collocazione: *locale* se il numero viene da un elemento
sensibile del dominio fisico, *remoto* se viene da un modello applicato a una
grandezza non energetica letta dal client.

Il criterio non e' la geografia, e il caso che lo verifica e' C0 (§3.4, riga C0):
inferenza su nodo noleggiato con NVML eseguito **la'**. Per collocazione e'
remoto, per natura e' M1/M2 del dominio `gpu_dedicated`. **Sta nel blocco
locale**, con l'host che ha prodotto il numero scritto nella riga (`endpoint`).
§2.1, nel paragrafo "L'eccezione ha un nome e un confine", lo descriveva gia'
come eccezione nominata; questa sezione
ne fa la regola, perche' la partizione non e' una sistemistica dei paragrafi:
decide quali obblighi di etichetta gravano su una colonna e quale parola si puo'
scrivere accanto al suo numero.

### Che cosa appartiene a quale blocco

| | **blocco locale** | **blocco remoto (cloud + rete)** |
|---|---|---|
| origine del numero | elemento sensibile del dominio: contatore cumulativo (M1) o integrale di potenza dello stesso dominio (M2) — §2.1, righe M1 e M2 | grandezza non energetica letta dal client — token, byte, latenza — convertita da un modello: EcoLogits (C2/C4/C3), il fit C5, il coefficiente J/bit (T1/T2) |
| scala M1-M4 | si' | **no**, per dichiarazione gia' scritta in §2.1 ("Le stime cloud e rete non stanno su questa scala"): l'unita' e' il byte o il token, non il dominio |
| token di riga | `energy_calculation_method`, `package_window_source`, `idle_provenance`, `baseline_backend` (campo di P1.3, non ancora nel codice), `measurement_boundary` | `cloud_energy_method` con i campi di provenienza di §6; `network_energy_coefficient_j_per_bit` e `network_measurement_boundary` (D13) |
| G4 | non superato **oggi**: W1 (§3.4, riga W1, `[A]` in acquisto) arbitrera' la scala assoluta del sistema | **non superabile per costruzione** — vedi la prima conseguenza |
| parola ammessa | "funzionamento verificato"; "validato" solo con i sei anelli di P4.9 (`protocollo_v4_20261024.md:2084-2114`) | "stima", sempre con confine e provenienza; **"validato" mai** |
| catene | §4, tabella delle catene, righe 1-15 (`emi-counter` → `power-integration` → …, `nvml-*`, RAPL) | §6 e §7, riga di apertura di ciascuno |

### Prima conseguenza: per il blocco remoto "non validato" e' statuto, non lavoro in corso

Va scritto perche' somiglia a un deficit temporaneo e non lo e'. W1 misura il
sistema completo a monte dell'alimentatore del client (§3.4, riga W1); non esiste
strumento, nella portata del progetto, che misuri l'energia del server di un
provider o il tratto di rete fra client e datacenter. Il riferimento piu' vicino
per la rete sarebbe il contatore del package, che pero' include tutto il resto
(§7). Dunque per il blocco remoto G0-G3 decidono **se** la colonna e'
utilizzabile, mentre G4 non la riguarda per definizione: nessuna riga cloud o
rete sara' mai promossa, e la priorita' 6 di §12 (acquisto di W1) cambia lo
stato del blocco locale, non quello del remoto.

Il precedente metrologico e' lo stesso del locale ed e' la ragione per cui la
parte "confronto" non sostituisce G4: regola 4 di §5 — due numeri che
derivano dalla stessa fonte concordano per costruzione. Vale per la terna EMI /
LHM / SRUM sullo stesso `MSR_PKG_ENERGY_STATUS` 0x611 e vale per C2 contro C5 se
i coefficienti del fit nascono dalle tabelle di ML.ENERGY
(`metodo_analitico_cloud_20261026.md:505-511`): sono una lettura sola.

Ne segue un obbligo di stesura: la regola 6 di §5 (nessuna percentuale
di accuratezza per configurazione) per il blocco remoto vale a tempo
indeterminato, per il locale solo finche' non arriva W1.

### Seconda conseguenza: i blocchi restano colonne separate, e `end_to_end_energy_j` e' una somma dichiarata di nature diverse

Tre obblighi, non uno stile:

- la somma fra blocchi non e' una misura di nessun dominio; la riga la presenta
  con le sue addende nominate, perche' "somma di M1 + stima + stima" e' una
  grandezza con la terza incertezza piu' larga delle tre ma il linguaggio della
  prima (regola 2 di §5; regola 5 di §3.0);
- la rete **non si somma alla serie cloud in una colonna unica**
  (`metodo_analitico_cloud_20261026.md:38`): sono due confini diversi, la
  generazione server-side e un'intensita' di percorso applicata ai byte osservati
  sulla NIC del client (rete di accesso esclusa dalla fonte del coefficiente), e
  una colonna unica renderebbe non separabile un difetto di attribuzione da un
  difetto di scala;
- ogni colonna porta il proprio metodo e il proprio confine anche quando vale
  zero: regola 9 di §5 e il punto 5 della lista in fondo a questa sezione.

### Esempio, con i numeri e il confine di ciascuno

Una riga **composita, costruita a scopo illustrativo**: i tre valori vengono da
tre origini diverse -- un pilota di misura, una sonda del motore di stima,
un'aritmetica del coefficiente -- e non da una singola esecuzione.
Geometria `N_out = 32` per la parte cloud, finestra di 10,059 s per la parte
locale, 1,0 MB nominali per la rete:

| colonna | valore | natura | confine dichiarato |
|---|---|---|---|
| `active_energy_j` (l'`E_active` dell'analisi) | **232,623 J** su finestra 10,059 s | M1, `emi-counter` | package Intel: include core, uncore e iGPU (PP1) |
| `cloud_energy_j` | **11,43 J** (`3,176229044667e-06` kWh) | C2, stima | server-side datacenter, sola generazione; input esclusi |
| `network_energy_j` | **21,6 J** per 1,0 MB decimali transitati | T1, stima x coefficiente | byte system-wide del client x percorso trasmissione+commutazione, accesso escluso |

Il primo numero viene da `MSR_PKG_ENERGY_STATUS` letto con IOCTL (§3.1, riga E1,
e `energy/emi_backend.py:7-16`) ed e' il valore A del pilota di additivita'
(`experiment_results/additivity_20261025_analisi.md:51-52`); il secondo viene da
un registro di terzi, ed e'
l'uscita della sonda tracciata
(`experiment_results/ecologits_clamp_console_20261026.txt:6,14`), dove la latenza
di 1,60 s misurata produce lo stesso identico numero di 1,5697 s perche' il
`min()` del motore ha gia' clampato (la conversione da kWh a joule e' `1 kWh =
3,6e6 J`); il terzo e' aritmetica del coefficiente
dichiarato (`2,7e-6 J/bit`, `config.py:363`, per `8e6 bit` = 1,0 MB decimale;
per 1 MiB, `8,388608e6 bit`, fanno 22,649 J), **non una
misura di questo host**: nessun run ha misurato 1,0 MB su questa macchina, e il
valore sta qui come conversione del confine. `end_to_end_energy_j` sara' la loro
somma, e la riga
dovra' dire che somma di tre nature e'.

### Controesempio: un numero che sembra conservativo e non lo e'

La riga con `request_latency = 1,60 s` dichiara un'attesa **maggiore** del punto
di plateau, e la tentazione e' leggerla come cautelativa: piu' tempo, piu'
energia. Il numero e' identico a quello di 1,5697 s
(`experiment_results/ecologits_clamp_console_20261026.txt:14-17`)
perche' sopra la soglia il tempo misurato viene scartato, non sommato. Una stima
che scarta il dato peggiore non e' conservativa: e' **insensibile** alla lentezza
reale del provider, e il suo errore va nella direzione opposta a quella che
sembra. Per questo il punto 3 della lista porta `cloud_latency_used_s`,
`cloud_latency_threshold_s` e `cloud_latency_binding` nella riga.

### Che cosa questo punto non chiude

- la **catena** del blocco remoto e' stata scritta in due versioni fino al
  28-10-2026: §6, alla sua prima riga, diceva `C1 → C2 → C4 → C3 → unavailable`,
  mentre `metodo_analitico_cloud_20261026.md:29` e la sua tabella §1 dicevano
  `C1 → C2 → C4 → C3 → C5 → unavailable`, e la riga C5 **non esisteva** nella
  tabella di §3.4 di questo documento. **Chiuso il 28-10-2026** su decisione
  dell'autore: C5 entra come fallback finale prima di `unavailable`, §6 scrive
  `C1 -> C2 -> C4 -> C3 -> C5 -> unavailable`, §3.4 porta la riga C5
  (`analytic-class-fit`, `[P]`, boundary "acceleratore di riferimento, serving
  open-source, steady state") e il documento analitico resta il disegno di quel
  gradino. I due testi normativi dicono ora la stessa catena; lo stato di C5 e'
  `[P]` in entrambi;
- i campi di provenienza cloud (punto 3), il coefficiente J/bit e il confine di
  rete (punto 4), la partizione zero/`N/A` (punto 5);
- il blocco locale: le sue catene restano quelle di §4, e i suoi nodi aperti
  (D1-D2, D7-D9, D14-D15) restano aperti — questo punto decide solo **a quale
  blocco** appartengono e quindi quale vocabolario di etichette usano.

### I punti della definizione finale, e il loro stato

| # | punto | blocco | stato al 26-10-2026 |
|---|---|---|---|
| 1 | partizione locale / remoto | trasversale | **chiuso** -- questa sezione |
| 2 | catena cloud con C5, allineamento fra §6 e la tabella di §3.4 | remoto | **chiuso il 28-10-2026** -- `C1 -> C2 -> C4 -> C3 -> C5 -> unavailable` in §6 e in `metodo_analitico_cloud_20261026.md`; riga C5 in §3.4 con etichetta `analytic-class-fit`, stato `[P]`, boundary proprio |
| 3 | campi di provenienza della stima cloud (D3, D12, i campi della latenza clampata) | remoto | aperto |
| 4 | coefficiente J/bit e confine di rete (D8, D13, D16; F7) | remoto | **fonte e confine corretti** il 26-10-2026; resta aperto il confronto empirico e il confine byte/coefficiente |
| 5 | zero contro `N/A` nel blocco remoto (D4; F1 e F9 aperti, F2 chiuso in `HEAD`) | remoto | aperto |
| 6 | CPU/package: fallback, `external_counter`, package multipli, lessico di G0 (D1, D9, D11, D14, D15; F8, F10, F11) | locale | **in parte chiuso il 27-10-2026**: F10, F11 (entrambi i lati), F13 e D17 in codice; **D14 chiuso il 28-10-2026** (flag `external_counter` in riga, chiude anche F8); restano il token di riga (D11) e la somma dei package distinti (D15); D1 e D9 sono superate da D18 |
| 7 | GPU, NPU e i mai-esercitati (D2, D5, D6, D7; F3, F6) | locale | aperto |
| 8 | attribuzione al processo: M3, non un metodo (§8, P6.6) | locale | aperto |
| 9 | allineamento di §9, §10, §11, §12 contro i punti chiusi | trasversale | aperto |

L'ordine non e' la classifica di urgenza di §12, che resta quella: e' la
sequenza di lavoro scelta il 26-10-2026, e parte dal blocco remoto perche' e' li'
che stanno le decisioni aperte e l'unica incoerenza fra due testi normativi del
progetto.

**Ancoraggi di questa sezione.** I riferimenti *a questo documento* sono
localizzatori di sezione (riga C0, riga W1, riga E1, regola 4 di §5, tabella
delle catene di §4), **non numeri di riga**: piu' sessioni scrivono su questo
stesso percorso -- lo dichiara il paragrafo "Data e albero delle verifiche" in
testa al documento -- e un numero di riga qui sarebbe falso alla modifica
successiva. I numeri di riga restano solo dove l'ancoraggio e' un file gia'
committato e non conteso: `protocollo_v4_20261024.md:2084-2114`,
`metodo_analitico_cloud_20261026.md:12-14,29,38,505-511`,
`experiment_results/ecologits_clamp_console_20261026.txt:6,14-17`,
`experiment_results/additivity_20261025_analisi.md:51-52`. Fra i sorgenti,
`energy/emi_backend.py:7-16` e `config.py:341` sono su file **puliti** nell'albero
di lavoro del 26-10-2026 (`git status`: le modifiche non committate sono su
`energy/energy_session.py`, `energy/local_energy.py`,
`casualwatt_csv_export.py`); dove si cita uno di quei tre, il numero va
riverificato al gate di P5.

---

## 2. Livelli di misura e controlli

### 2.1 Quattro livelli

| livello | che cos'e' | esempi | cosa dichiara |
|---|---|---|---|
| M1 | contatore cumulativo di dominio | EMI PKG, RAPL `energy_uj`, NVML total energy | energia del dominio fra due letture |
| M2 | integrazione di potenza dello stesso dominio | LHM `CPU Package`, NVML `PowerUsage`, `powermetrics` | un integrale; dipende da cadenza e copertura |
| M3 | modello o attribuzione | quota di tempo CPU, quota di utilizzo GPU, ripartizione EPI | una **quota**, non una lettura |
| M4 | non disponibile | nessun canale utilizzabile | assenza dichiarata, con la ragione |

Le stime cloud e rete non stanno su questa scala: la loro unita' di misura e'
il byte o il token, non il dominio locale, e hanno campi propri (§6, §7). Usano
la stessa logica (una grandezza misurata piu' un modello), ma non si
classificano con M1-M4 nel CSV.

L'eccezione ha un nome e un confine: quando l'inferenza gira su hardware
noleggiato e NVML si puo' eseguire **la'**, il numero non e' una stima ma M1/M2
del dominio `gpu_dedicated` su un endpoint remoto (riga C0 di §3.4). Cio' che lo
tiene fuori dal caso cloud non e' il luogo: e' che il contatore del dominio
esiste e viene letto. Cambia chi lo legge, e la riga deve dire quale host ha
prodotto il numero.

### 2.2 Cinque controlli

| controllo | domanda | se fallisce |
|---|---|---|
| G0 disponibilita' | l'interfaccia esiste ed e' leggibile? | si passa al livello successivo della catena, e la ragione esce dal lessico di §4.1, non da un testo libero |
| G1 semantica | unita', dominio e conversione sono documentati e verificati, non assunti? | il canale non e' utilizzabile |
| G2 integrita' di finestra | monotonia, reset, rollover, timestamp per dominio, copertura, campioni mancanti | la finestra si segmenta o si dichiara `unavailable`; mai sottrazione cieca |
| G3 confine | cosa include il dominio, cosa si sovrappone, misura o attribuzione? | il canale non e' utilizzabile per quel dominio |
| G4 validazione | esiste un riferimento indipendente sulla stessa finestra? | il canale si usa, ma **non** si scrive "validato" |

G0-G3 decidono **se** un canale e' utilizzabile. G4 non cambia il canale:
cambia la parola che si puo' usare. Un canale piu' forte per semantica ma non
validato non viene sostituito da uno piu' debole "validato": si sceglie il piu'
forte che passa G0-G3 e si dichiara lo stato di validazione.

**Il token di G4 esiste in codice dal 28-10-2026.** `chain_status` era un nome
di colonna senza produttore (`casualwatt_csv_export.py:231`), quindi la regola
"validata solo se tutti e sei gli anelli passano" non era calcolabile.
`validation_chain.py` applica ora le soglie congelate di P4.9 -- `r_A <= 10%`
in almeno 2 blocchi su 3, quorum `ceil(2/3 * n_coppie)` sul test di
sottrazione, `p_lof_perm >= 0,05`, `err_rel <= 10%` su **entrambi** i punti di
conferma -- e restituisce l'etichetta del primo anello che cede, oppure
`reduced_design` quando il disegno e' ridotto a anelli puliti, oppure
`validated`. Non promuove nulla: rende l'esito calcolabile e verificabile
(`tests/test_chain_status.py`, 17 test sui confini delle soglie). L'anello 1
(pilota P2.9) resta una precondizione e non un token: senza pilota superato non
esiste campagna a cui assegnare uno stato.

### 2.3 Regola di selezione

```
per ogni dominio richiesto:
    per ogni canale nella catena pre-registrata (OS, produttore, dominio):
        se G0..G3 passano:
            seleziona il canale
            stato = "validato" se G4 passa, altrimenti "funzionamento verificato"
            interrompi
    se nessun canale passa:
        seleziona "unavailable" con la ragione dichiarata
```

L'ordine della catena e' fissato **prima** di eseguire. La disponibilita' si
verifica a runtime; l'ordine no. Un rollover o una copertura incompleta sono un
fallimento di G2 di **quella finestra**: si segmenta o si dichiara l'assenza,
non si "sistema" il numero. Il cambio di canale a meta' finestra non si
concatena: la finestra si interrompe o si separa in segmenti, e il cambio resta
nella riga.

### 2.4 Quanti fallback

Tanti quanti sono i percorsi **meccanicamente distinti**, non di piu'. Due
letture dello stesso registro non sono due canali **indipendenti**: EMI e il
percorso MSR di P1 leggono entrambi `MSR_PKG_ENERGY_STATUS` 0x611
(`energy/emi_backend.py:7-11`; §3.1.2), quindi ai fini della validazione sono una
lettura sola. Ai fini della disponibilita' sono due percorsi meccanici distinti
(IOCTL sul device EMI contro IOCTL a PawnIO piu' decodifica del registro), e il
secondo copre un guasto che il primo non copre: il device del canale EMI puo'
mancare mentre le MSR restano leggibili. Si contano due nella catena, zero nella
colonna delle evidenze indipendenti. Da D18 il secondo percorso **non e' piu'
LHM**, che era un terzo consumatore dello stesso registro con una potenza gia'
derivata: dal 28-10-2026 e' il lettore MSR sopra PawnIO (`pawnio-counter`),
[I] con [V] su questo host Intel, e **richiede un processo elevato**. La
catena recupera un grado di fallback, ma non gratuito: senza elevazione il
secondo percorso non c'e' e la riga torna `unavailable`.

---

## 3. Catalogo dei metodi

### 3.0 Invarianti comuni

Valgono per ogni riga delle tabelle 3.1-3.4: si dichiarano una volta sola qui,
non si ripetono in ogni tabella, e §5 li traduce nella riga del CSV.

1. **Una riga del catalogo non e' uno stato di validazione.** Descrive un
   canale: interfaccia, unita', livello, confine, etichetta, evidenza.
   "Etichetta" e' il token che finisce in `energy_calculation_method` o nel
   campo del dominio, non un aggettivo.
2. **Il livello si dichiara per come il numero e' prodotto, non per la sua
   fonte.** Un contatore cumulativo e' M1 solo se il valore letto e' gia'
   energia; una potenza integrata e' M2 anche quando il campione deriva da un
   registro che EMI legge come contatore (LHM, §3.1).
3. **Un canale non cambia livello a meta' strada.** Se l'interfaccia espone solo
   potenza, il canale e' M2 e resta M2: non si promuove a M1 perche' il numero
   e' plausibile.
4. **Il confine precede il numero.** Ogni riga dice cosa include il dominio
   (package, whole-device, sotto-dominio, sistema) e se il valore e' misura o
   attribuzione; un canale senza confine verificato non passa G3.
5. **Nessuna riga si somma a un'altra per implicito.** PP0 e PP1 sono
   sottoinsiemi di PKG e non si sommano mai; DRAM e' un dominio distinto, si
   riporta a parte e entra in una somma solo se la somma e' dichiarata come
   tale (§1). Una riga informativa resta informativa.
6. **L'assenza e' una riga del catalogo, non un vuoto.** M4 / `unavailable` e'
   un'etichetta legittima e dichiarata; non esiste un canale implicito che
   produce zero.
7. **La catena e' pre-registrata.** L'ordine in §4 e' fissato prima del run; a
   runtime si verifica solo la disponibilita' (G0), non si riordina.
8. **Gli stati riguardano l'evidenza, non l'accuratezza.** `[I]` e `[V]` dicono
   cosa e' stato fatto, non quanto il numero sia vicino alla grandezza vera:
   quello lo dice solo G4, con i sei anelli di P4.9.

### 3.1 CPU / package

| id | interfaccia e unita' | livello | confine | etichetta | stato |
|---|---|---|---|---|---|
| E1 | canale energia di Windows letto via IOCTL sul device enumerato per GUID `{45bd8344-...}`; record PKG in pWh (1 pWh = 3,6e-9 J), timestamp per dominio; il canale si nomina dal metadato del driver (`RAPL_Package0_PKG`), **non dal produttore** | M1 | package; non include VRM, display, alimentatore | `emi-counter` | [I][V] su i9-13900HK, metadato v2 di 492 byte con quattro canali letto il 27/10 e device scelto per nome; [P] su AMD e su Windows 10, probe non eseguito. Nota 26/10: l'interfaccia e' **documentata** da Windows 10 (EMI v1) e da 1809 (v1+v2), il GUID e' quello di `emi.h` / `GUID_DEVICE_ENERGY_METER`, e l'unita' `EmiMeasurementUnitPicowattHour` con `AbsoluteEnergy` cumulativo "with some arbitrary zero-point" e' la definizione che sta dietro M1 (§3.1, fonte Microsoft) |
| E2 | stesso canale, dominio PP1 (`RAPL_Package0_PP1`) | M1 sub-dominio | grafica integrata **su Intel**, sottoinsieme di PKG; informativo | campo `igpu_energy_j` | [I][V] a riposo |
| E3 | stesso canale, dominio DRAM (`RAPL_Package0_DRAM`) | M1, dominio distinto | memoria; **non e' un sottoinsieme di PKG**; sul host client legge spesso zero | si riporta a parte, mai somma implicita | [I][V] |
| L1 | LHM, sensore `SensorType.Energy` | M1/M2 **non determinato** | se e' un contatore hardware e' M1; se LHM lo integra e' M2 | `librehardwaremonitor-energy` | **storico dal 27/10-2026 (D18)**: non selezionabile; metodo provato e superato. [I] codice, [A] sul host (solo batteria in LHM 0.9.6) |
| L2 | LHM, `SensorType.Power` "CPU Package" integrato | M2 | package; stessa sorgente 0x611 di E1; richiesto 0,05 s, osservato 0,28-0,34 s | `power-integration` | **storico dal 27/10-2026 (D18)**: le sue misure restano evidenza, il canale non si seleziona. [I][V] |
| L3 | LHM, sensore "CPU Graphics"/"IA GPU" | M2 sub-dominio | grafica integrata; informativo | campo `igpu_energy_j` | **storico dal 27/10-2026 (D18)**. [I], non esercitato sotto carico grafico |
| P1 | MSR RAPL lette da un client proprio sopra PawnIO: `0x606` + `0x611` su Intel, `0xC0010299` + `0xC001029B` su AMD; delta di contatori cumulativi, unita' derivata dal registro di unita' | M1 | package; **stesso registro di E1** (0x611 / 0xC001029B), quindi non e' una validazione indipendente | `pawnio-counter` | **[I] con [V] su questo host Intel (28/10-2026)**: rapporti 1,000578 e 1,000576 contro EMI a finestra uguale; ramo AMD [I] con libreria finta, [V] su CPU AMD da fare; riporto e reset reali non esercitati. Richiede un processo elevato (`access_denied` senza, misurato). Licenza PawnIO GPL-2.0 con eccezione IOCTL (verificata alla fonte il 27/10); HVCI e firma **verificate sul pacchetto installato** (D18, §3.1.2) |
| P2 | driver di terze parti per Windows che espone i contatori RAPL (Hubblo / Scaphandre) | M1 candidato | package; **stesso registro di E1** | `msr-counter` con interfaccia dichiarata (proposto, non ammesso) | [P]: nome, versione, licenza, dominio e stabilita' del driver da verificare alla fonte; installa un driver, quindi peggiora il profilo di EMI, che usa quello gia' presente |
| P3 | PMI/WMI: namespace `Root\CIMV2\power`, classe `Win32_PowerMeter` (deriva da `CIM_NumericSensor`) | M2 candidato | **da verificare**: la classe e' documentata come meter di piattaforma, quindi probabilmente sistema intero e non package | `pmi-power-integral` (proposto, non ammesso) | [P]: su questo host la classe e' interrogabile e restituisce **zero istanze**; la proprieta' `PowerMeasurement` citata dai documenti esterni **non esiste** sulla classe |
| R1 | RAPL powercap, `energy_uj` + `max_energy_range_uj` | M1 | package; il package **e' uno dei zone**, non `intel-rapl:0` per definizione | `rapl` | [I], [V] da fare (nessun host Linux) |
| R2 | RAPL `psys` | M1 | **dominio piu' ampio** del package | da dichiarare come dominio proprio | [A] non implementato |
| R3 | powercap RAPL su AMD (Zen 1-3), kernel >= 5.11 | M1 candidato | package AMD; zona esposta dal driver `intel_rapl` rinominato, nomi da verificare | `rapl` solo se percorso e semantica verificati | [P] |
| R3b | hwmon `amd_energy`, `energy[N]_input` | M1 candidato | contatori per socket e per core esposti dalle MSR RAPL AMD, incremento dichiarato 15,3 uJ (kernel v5.9 doc); supporta Family 17h/19h/1Ah, quindi EPYC prima che Ryzen client | `rapl` con dominio dichiarato, o etichetta hwmon propria | [P] |
| R3c | contatori RAPL AMD via `perf` (PMU) | M2 candidato | lettura per evento, non contatore sysfs; integrazione richiesta | `power-integration` solo se verificato | [P], versione del kernel non verificata alla fonte |
| R4 | AMD SMI / AMD uProf, potenza CPU | M2 candidato | package o socket, da verificare | `power-integration` (se verificato) | [P] |
| R5 | `perf_event` con gli eventi `power/energy-pkg/` (Intel) | M1 candidato | package; **stesso registro di R1**, esposto dal PMU | `rapl-perf` (proposto, non ammesso) | [P]: l'interfaccia `perf_event` per gli eventi `power/*` esiste dal kernel 3.14 e richiede root o `perf_paranoid < 1` (§3.1, R3c); il token non e' in `MEASURED_METHODS` |
| V1 | `turbostat` (colonna `PkgWatt`); LIKWID come variante dello stesso strumento esterno | M2 derivato | package; legge i contatori via `/dev/cpu/*/msr` | **nessuna**: controprova fuori linea, mai livello di catena | [P]: manuale verificato il 27/10 ("reads hardware counters", `/dev/cpu/*/msr`, `PkgWatt` = "watts consumed by the whole package"); LIKWID per analogia, da verificare. Stesso registro: coerenza, non validazione |
| D1 | RAPL powercap, zona `dram` | M1 | dominio distinto, **non** sotto-dominio di PKG | riportato a parte, come E3 | [P]: il backend enumerato seleziona solo le zone `package-*` e scrive le altre in `notes` come "domini diversi dal package, non sommati" |
| X1 | `CW_ENERGY_FILE`, contatore joule fornito dall'utente | M1 dichiarato | dipende dal file; **priorita' di selezione** su E1 e L2, non una misura EMI | `energy-file` | [I], uso test/dev |
| X2 | stima di ultima istanza da TDP, **opt-in e spenta di default** | nessuno (non e' una misura) | campo proprio, fuori dalla catena e fuori da `energy_calculation_method`; mai a confronto con le misure | `estimate-load-tdp` (proposto, campo `energy_estimate_j`) | [P] non implementato |

Precisazioni.

- **E1.** Il device e' enumerato per GUID di interfaccia con SetupAPI, senza
  filtro di produttore: `energy_session` seleziona Windows e basta, poi chiede
  il contatore e accetta il canale **solo se la prima lettura riesce**
  (`energy/energy_session.py:139-164`, `:166-193`). Fino al 26/10 il percorso
  prendeva la prima interfaccia apribile e il primo canale del record, e
  l'ordine `pkg, dram, pp0, pp1` era assunto dalla posizione: erano i difetti
  F11 e F13. **Dal 27/10/2026 il lettore verifica il meter invece di
  presumerlo** (D17): enumera tutte le interfacce, per ciascuna legge il
  contratto del driver -- `IOCTL_EMI_GET_VERSION` -> `GET_METADATA_SIZE` ->
  `GET_METADATA` (`energy/emi_backend.py:95-98`, `:476-501`) -- e accetta un
  device solo se il metadato espone un canale di dominio `pkg` in pWh
  (`select_cpu_device`, `:226-263`). Un device senza quel canale -- batteria,
  sensor hub, GPU -- si scarta con la ragione scritta nei `notes` ("nessun
  canale PKG: non e' un device CPU (canali: ...)"); senza **nessun** device CPU
  la selezione non produce un canale e la riga e' `unavailable`. Con **piu'**
  device CPU (package multipli) la scelta non e' automatica: la ragione e'
  `ambiguous_domain` e `CW_EMI_DEVICE` dichiara il device, senza saltare la
  verifica del metadato (`choose_single`, `:266-285`).
  Il canale PKG si sceglie per **nome** e non per posizione
  (`domain_from_channel_name`, `:158-167`); il record si legge per
  `16 * ChannelCount` byte e ogni coppia (energia, tempo) si mappa sul canale
  con quell'indice (`_ioctl_raw`, `:526-548`; `read_domains`, `:591-624`). Un
  canale PKG specchiato si legge una volta dichiarandolo, due canali PKG con
  nomi distinti sono `ambiguous_domain` (D15). Un meter **V1**, che la
  documentazione descrive a un solo canale, si scarta con la ragione dichiarata
  -- la lettura V1 non e' implementata ne' provata -- invece di presentare la
  risposta corta come guasto dell'IOCTL. Il metadato verificato su questo host
  il 27/10/2026 e' in §3.1.1.
  L'accumulatore e' letto grezzo, senza integrazione, senza .NET e senza
  privilegi di amministratore (`energy/emi_backend.py:13-16`); i timestamp sono
  **per dominio**, e sono l'unico modo di accorgersi che un canale non si
  aggiorna: un dominio il cui timestamp non avanza restituisce `None` con la
  ragione, un dominio il cui valore non cambia ma il cui timestamp avanza ha
  misurato zero.
- **E3.** DRAM e' un dominio distinto, non un sottoinsieme di PKG: si riporta a
  parte. Sul host vale spesso zero, quindi oggi non cambia nessun numero; la
  modifica e' alla regola (§1 e §5.2), non al dato.
- **L1.** Sull'host di prova il sensore `Energy` non esiste: in LHM 0.9.6 e'
  istanziato solo dalla batteria (`lhm_gui_report_20261023_analisi.md:46-99`).
  Inoltre non e' dimostrato che, dove esiste, sia un contatore hardware e non
  un'integrazione interna di LHM. Il criterio di promozione che questa specifica
  aveva scritto -- (i) il sensore compare a runtime con `SensorType.Energy`; (ii)
  il valore e' cumulativo e monotono al netto dei reset, non il `Δ/Δt` di un
  altro sensore; (iii) unita' e dominio verificati a G1 -- **non e' piu' la via
  di ingresso**: con D18 LHM esce dall'implementazione e L1 e' storico. Il
  criterio resta scritto perche' e' la condizione che una qualunque
  reintroduzione dovrebbe soddisfare, e perche' dice perche' oggi non lo
  soddisfa.
- **L2.** La potenza LHM "CPU Package" e' gia' `Δ(0x611)/Δt`
  (`energy/emi_backend.py:9-11`): il nostro integrale integra una potenza gia'
  derivata, e alla derivata somma la propria cadenza. Copriva il guasto del
  driver EMI e i permessi, non il guasto del registro, e non era una validazione
  di EMI. E' questa la ragione tecnica del ritiro: non un canale in piu', ma lo
  stesso registro con una derivata in piu' e una cadenza in piu'. I sensori
  Energy-CPU di LHM richiedono token elevato -- senza UAC la libreria si aggancia
  ma legge zero o `None` (percorso LHM rimosso il 27/10/2026, D18, commit
  `3562875`) -- quindi la copertura
  che offriva era, sul caso "permessi", parziale. Restano validi e citabili i
  risultati ottenuti col canale finche' era selezionabile: accordo a finestra
  uguale con EMI, differenziale A-B-A, costo di osservazione. La selezione del
  sensore era per `SensorType`, non per nome: il nome da solo ha gia' prodotto il
  difetto che integrava i gradi Celsius di un sensore Temperature omonimo (guard
  su `SensorType`, rimosso con LHM il 27/10/2026, D18; fix `1422d1b`), ed e' la
  ragione per cui il sostituto P1
  sceglie il registro per indirizzo e il dominio per metadato, non per nome.
- **P2.** E' un secondo percorso di **accesso**, non un secondo canale: legge
  lo stesso registro di E1. Nella catena conta come fallback di disponibilita'
  (§2.4) e zero come evidenza indipendente. Non entra finche' nome, versione,
  licenza e dominio del driver non sono verificati alla fonte: un driver kernel
  di terze parti installato per colmare un'assenza e' superficie nuova, e il
  criterio di D18 -- entra solo dopo la sonda contro EMI a finestra uguale e la
  misura del costo di osservazione -- vale anche qui. Rispetto a EMI non
  migliora il profilo di installazione, lo peggiora: EMI usa il driver gia'
  presente.
- **P3.** Due fatti verificati alla fonte il 27/10, e sono la ragione per cui la
  riga resta [P] e non entra in catena. (i) La classe e' `Win32_PowerMeter` nel
  namespace `Root\CIMV2\power`, e le sue proprieta' sono metadati e **budget**
  (`MeterType`, `SupportCapabilities`, `SamplingPeriod`, `BaseUnits`,
  `UnitModifier`, budget minimo/massimo/configurato, `Hysteresis`, intervalli di
  media); la proprieta' `PowerMeasurement` che i documenti esterni usano **non
  esiste**. Un valore di potenza, se c'e', arriva dalla proprieta' ereditata
  `CurrentReading` di `CIM_NumericSensor`, che e' un sensore numerico generico:
  che cosa misura va letto caso per caso, non dedotto dal nome della classe.
  (ii) Su questo host la classe e' interrogabile e restituisce **zero istanze**
  (la diagnostica stampa l'esito in G0): se EMI mancasse, la ragione sarebbe
  `no_energy_domain`, non un problema di permessi. Il confine e' quello che il
  nome dichiara -- un *power meter* di piattaforma -- quindi di sistema, non di
  package: se il dominio verificato e' il sistema, la riga non e' un fallback di
  `cpu_package` e appartiene alla classe di W1/W2 (§3.4), dove non entra in
  catena.
- **R1.** Due limiti, entrambi nel codice, **corretti il 27/10**. Il percorso era
  cablato su `intel-rapl:0`: non reggeva su una macchina con piu' package, ne' su
  un AMD multi-die dove i canali di package separati replicano lo stesso
  contatore socket-wide. Oggi `energy/rapl_backend.py` enumera
  `/sys/class/powercap` (`:128`), tiene le zone il cui `name` inizia per
  `package-` (`:151`), somma **i package distinti** e deduplica i canali
  specchiati per nome con una nota (`:156`); `probes/cw_probe.py:92-126` faceva
  gia' la stessa enumerazione in sola lettura e stampa tutte le zone con la loro
  leggibilita'. Il secondo limite era la nota del backend, che diceva "richiede
  root o gruppo `power`": il gruppo `power` non compare in nessuna fonte letta il
  26/10, mentre il codice verifica solo `os.access(energy_uj, R_OK)` (`:148`).
  Si scrive **"root o permessi di lettura concessi esplicitamente sul nodo"**. Il
  fallback di wrap `2**32` uJ quando `max_energy_range_uj` manca e' **ritirato**:
  il massimo si legge **per zona**, e se il contatore decresce senza massimo
  leggibile la lettura viene rifiutata con "riporto non determinabile"
  (`:190-198`), perche' un avvolgimento ricostruito su un'assunzione e' un numero
  inventato. I test del backend restano saltati senza host Linux, ma
  `tests/test_rapl_zone.py` prova la logica su un finto sysfs da Windows:
  "implementato" qui significa "provato nella logica, non sull'hardware".
- **R2.** `psys` non e' un fallback di `cpu_package`: e' un dominio diverso e
  piu' ampio. Se si vuole il sistema, si dichiara `psys`; non si sostituisce
  PKG con `psys` presentandolo come package.
- **R3/R3b/R3c.** Il nome `amd_atl` che compariva qui **e' sbagliato e va
  ritirato**: `amd_atl` e' la AMD Address Translation Library, usata per la
  traduzione degli indirizzi nel crash dump, e non c'entra nulla con l'energia
  (verificato il 26/10 sui log di kernel che la inizializzano e sul
  changelog RHEL "RAS/AMD/ATL"). I percorsi AMD reali sono tre, tutti [P]:
  powercap RAPL per Zen 1-3 arrivato con il kernel 5.11 (Phoronix, 16/11/2020,
  fonte non peer-reviewed da confermare sul changelog del kernel); hwmon
  `amd_energy`, che espone `energy[N]_input` per socket e per core dalle MSR
  RAPL con incremento dichiarato di 15,3 uJ (documentazione kernel v5.9,
  `kernel.org/doc/html/v5.9/hwmon/amd_energy.html`), supportato su Family 17h
  modello 30h e sulle 19h/1Ah elencate nel README `amd/amd_energy`, quindi
  prima su EPYC che su Ryzen client; e i contatori letti via `perf`.
  **Verifica 26-10-2026, alla fonte, di due righe che prima erano scoperte.**
  (a) La restrizione di permessi sui nodi hwmon **e'** legata a CVE-2020-12912:
  lo dichiara il README del driver, nella repository ufficiale AMD
  (`github.com/amd/amd_energy`: "To address CVE-2020-12912, the visibility of the
  `energy[N]_input` attributes is restricted to owner and groups only"). Il
  numero CVE corrisponde al lato **AMD** degli attacchi PLATYPUS -- gli
  identificatori Intel sono CVE-2020-8694 e CVE-2020-8695 -- quindi la restrizione
  va citata sul percorso R3b (hwmon AMD) e **non** attaccata a powercap/`intel-rapl`,
  che e' un'altra interfaccia e un altro fornitore. Corrobora, senza essere la
  fonte del numero: la documentazione pratica di Weaver (`web.eece.maine.edu`,
  "Reading RAPL energy measurements from Linux") scrive che il driver AMD hwmon
  "senza controlli di permesso" fu **rimosso** in Linux 5.13 (commit `9049572fb`)
  "anche per ragioni di sicurezza".
  (b) Sui contatori via `perf` la situazione verificata e' piu' stretta di quanto
  questo documento scrivesse: l'interfaccia `perf_event` per gli eventi
  `power/energy-*` esiste **dal kernel 3.14** e richiede root o
  `perf_paranoid < 1` (Weaver, 26/10); gli eventi RAPL **AMD** pero' sono materia
  di serie di patch del 2024 -- metriche RAPL per Zen (`lkml`, Ian Rogers, 01/03
  2024) e contatori RAPL per core (`lwn.net/Articles/979104`, 2024) -- e non
  risultano in una release di kernel documentata alla fonte. Il percorso `perf` su
  AMD resta **[P] con la versione non chiusa**, e la riga di §3.4 non lo usa come
  fallback finche' la versione non e' quella del kernel del host di prova.
- **R5.** `perf` non aggiunge un sensore: legge lo stesso contatore che R1
  espone in sysfs. E' un secondo **accesso**, utile quando i nodi powercap non
  sono montati o non sono leggibili (container, immagini minime), e zero come
  evidenza indipendente. Il documento che lo propone aggiunge due dettagli
  operativi non verificati in questa sede: il contatore `perf` sarebbe un intero
  a 64 bit in unita' 1/2^32 J con il fattore di scala nel file `.scale`
  dell'evento, e gli eventi sarebbero `energy-pkg`, `energy-cores`,
  `energy-dram`, `energy-gpu`, `energy-psys`. Entrambi si verificano alla fonte
  (`perf` e la sua documentazione, non un repository di terzi) prima di
  scrivere codice: sono la forma esatta di F13 -- un numero plausibile con
  un'unita' assunta. Il token `rapl-perf` non e' in `MEASURED_METHODS`:
  ammetterlo e' un'emendazione a P5, non una scelta di questa specifica.
- **V1.** `turbostat` e, per analogia, LIKWID non sono livelli di catena e non
  prendono etichetta: sono **controprove** fuori linea, utili a verificare che
  il canale selezionato si muova come il registro. Il manuale (verificato il
  27/10) dice che `turbostat` legge i contatori hardware via `/dev/cpu/*/msr` e
  che `PkgWatt` e' "watts consumed by the whole package", cioe' un M2 derivato
  dallo stesso registro: l'accordo e' coerenza, non evidenza indipendente
  (§5 regola 4), e non arbitra la scala. Richiede gli stessi permessi di R5, e
  produce testo da interpretare, non un numero gia' strutturato: per questo non
  entra in catena nemmeno come ultimo ricorso.
- **D1.** La zona `dram` e' un dominio distinto come E3, non un sotto-dominio di
  PKG. Il backend enumerato seleziona solo le zone il cui `name` inizia per
  `package-`; le altre sono elencate nei `notes` con la dicitura "domini diversi
  dal package, non sommati". Riportare DRAM richiede una colonna propria e la
  stessa regola di E3: mai somma implicita.
- **X1.** `energy-file` e' un canale dichiarato per test e integrazione. Non e'
  un fallback di produzione. La sua prevalenza su EMI e sul percorso MSR P1 non e' una
  precedenza di merito ma di selezione: se la variabile e' impostata, il codice
  legge il file e non interroga il package, quindi cio' che si misura e' il
  contatore esterno, non EMI. La riga deve dirlo
  (`energy_calculation_method = energy-file`); un contatore esterno non e' EMI.
- **X2.** Serve perche' altrimenti, dove non esiste contatore, CasualWatt non
  produce nulla: Windows 10, AMD senza canale energia, macchine virtuali, Mac
  Intel. **Non entra pero' nella catena** e non prende un token di
  `energy_calculation_method` (AGENTS.md: `MEASURED_METHODS` ammette solo canali
  di misura, `energy/energy_session.py:73-74`). Le condizioni sono quelle gia'
  scritte nella valutazione che questa specifica completa: campo proprio
  (`energy_estimate_j`), etichetta propria (`estimate-load-tdp`), **spento di
  default** e acceso solo per opt-in esplicito, mai a confronto con una misura e
  mai nella stessa colonna di una misura. Se un giorno si implementa, il database
  dei TDP viene da CodeCarbon (MIT), che e' un modello, non un contatore: la riga
  resta una stima. E' la decisione D10.

### 3.1.1 Il contratto EMI e' scritto da Microsoft: cosa il lettore deve verificare

La fonte del metodo EMI non e' un'implementazione di terzi ma la documentazione
del fornitore: Microsoft, *Energy Meter Interface* (Windows driver docs) e le
pagine di riferimento di `emi.h`, lette il **27-10-2026**. Il contratto si compone
di cinque passi, e ognuno produce un obbligo verificabile sul nostro lettore.

1. `IOCTL_EMI_GET_VERSION` restituisce `EMI_VERSION`; la pagina dell'IOCTL
   precisa le due versioni: "**EMI_VERSION_V1** indicate there is only one single
   energy measurement channel supported by the device. **EMI_VERSION_V2** indicate
   there is multiple energy measurement channels supported by the device."
2. `IOCTL_EMI_GET_METADATA_SIZE`, poi `IOCTL_EMI_GET_METADATA`, con la verifica
   esplicita scritta nella procedura: "Verify that the returned
   **EMI_MEASUREMENT_UNIT** is EmiMeasurementUnitPicowattHours."
3. Il metadato V2 (`EMI_METADATA_V2`) dichiara `ChannelCount` e un array
   `Channels` di `EMI_CHANNEL_V2 { MeasurementUnit, ChannelNameSize, ChannelName }`,
   dove `ChannelName` e' "a null-terminated, Unicode string that specifies the
   channel name", e in EMI_VERSION_V2 "the only supported unit is
   picowatt-hours".
4. `IOCTL_EMI_GET_MEASUREMENT` restituisce `EMI_MEASUREMENT_DATA_V2`, di cui la
   pagina dice: "Each index in **ChannelData** must correspond to the measurement
   of the channel defined at the same index in **Channels** field of the
   EMI_METADATA_V2 struct." **L'indice non identifica il dominio: lo identifica
   il metadato.**
5. `AbsoluteEnergy` e' "the total accumulated energy in picowatt-hours with some
   arbitrary zero-point", e la procedura e' "compare samples at two different
   times and subtract the energy values"; `AbsoluteTime` e' "in 100 ns
   intervals". La semantica M1 dei nostri delta e' questa, non una convenzione
   nostra.

Il metadato di questo host, letto con gli stessi IOCTL il **27-10-2026** dalla
diagnostica (`diagnostics.py`, cattura integrale in
`experiment_results/emi_metadato_console_20261027.txt`; la console girava in un
processo elevato e lo dichiara -- documenta il metadato, non il privilegio):

| campo | valore osservato |
|---|---|
| `EMI_VERSION` | 2 (`EMI_VERSION_V2`) |
| `MetadataSize` | 492 byte |
| `HardwareOEM` / `HardwareModel` / `HardwareRevision` | `Microsoft` / `PPM` / 1 |
| `ChannelCount` | 4 |
| canali, nell'ordine del record | `RAPL_Package0_PKG`, `_DRAM`, `_PP0`, `_PP1` |
| `MeasurementUnit` | 0 (`EmiMeasurementUnitPicowattHours`) su tutti e quattro |
| `ChannelNameSize` | 100 byte per canale (nome + riempimento NUL), non la lunghezza naturale della stringa |

E' un fatto su **una** macchina (i9-13900HK, Windows 11): dice che il contratto
si legge davvero cosi', non che il formato sia identico altrove. Per questo il
codice mappa per nome e scarta il device quando il nome non basta
(`domain_from_channel_name`, `energy/emi_backend.py:158-167`), invece di
assumere l'ordine osservato qui. I quattro canali confermano che
`DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")` descrive **questo** metadato; la
non additivita' (PP0 + PP1 != PKG, PKG + DRAM != "tutto") resta la regola di
§3.1 e di §5.2, non un effetto dell'ordine.

Da qui una proposizione che questo documento non aveva, e che vale per la regola
7 di §5: **la cadenza non e' una proprieta' del contatore.** La pagina
dell'IOCTL scrive che "the EMI interface of any device should be shared across
the system, therefore how frequently the counters are being sampled and
accumulated depends on how often each of its consumers requests and also the
driver implementation". La cadenza si osserva e si scrive nella riga; non si
prescrive, e non e' la stessa su due macchine.

I cinque scarti fra il contratto documentato e il lettore, elencati qui il
27/10, sono **chiusi in codice nello stesso giorno** (D17,
`energy/emi_backend.py`); restano scritti perche' sono la forma in cui il
difetto F13 si presentava, e perche' una reintroduzione dovrebbe soddisfarli:

- **Versione.** Il lettore interroga `IOCTL_EMI_GET_VERSION` (`:476-486`) e
  distingue i tre casi: V2 si legge, un meter **V1** si scarta con la ragione
  "lettura V1 non implementata ne' provata" (non un guasto dell'IOCTL), una
  versione diversa si scarta come "non riconosciuta".
- **Metadato.** `GET_METADATA_SIZE` e `GET_METADATA` sono chiamati prima di
  ogni altra cosa (`:487-501`); `ChannelCount`, i nomi e l'unita' vengono dal
  metadato e non dalla posizione (`parse_metadata`, `:180-214`).
- **Unita' verificata.** Un canale PKG in un'unita' diversa da pWh si scarta
  con la ragione (`select_cpu_device`, `:226-263`): `PWH_TO_J` si applica solo
  dove il metadato dichiara pWh.
- **Input previsto dal contratto.** `IOCTL_EMI_GET_MEASUREMENT` si chiama senza
  input buffer (`_ioctl`, `:504-524`), come documentato; sul driver di questa
  macchina la risposta e' la stessa della chiamata con i 16 byte che il codice
  vecchio inviava.
- **Canale multiplo.** Il buffer di misura e' 16 byte per canale (`_ioctl_raw`,
  `:526-548`) e ogni dominio si legge dall'indice del **suo** canale
  (`read_domains`, `:591-624`); non si legge piu' "il primo canale"
  (`read_cumulative_energy_j`, `:563-575`).

Cio' che resta [P] non e' il lettore (che e' [I]) ma la copertura: l'esecuzione
su **AMD**, dove il metadato non e' stato visto e la `HardwareModel` "PPM" qui
osservata non e' una garanzia del formato; un meter **V1** reale; e la scala
assoluta, che nessun accordo fra lettori arbitra (regola 4 di §5). E' il difetto
**F13**: chiuso in codice, aperto nell'evidenza. La decisione **D17** lo chiude.

### 3.1.2 LHM esce dall'implementazione; il sostituto e' un lettore MSR proprio

La decisione e' **D18**, e ha due meta'. La prima e' un ritiro: LHM non e' un
secondo canale di misura, e' **lo stesso registro** di E1. LHM espone "CPU
Package" come derivata di quel registro (`energy/emi_backend.py:9-11`, che cita
la riga `IntelCpu.cs` della sorgente 0.9.6) e noi re-integriamo quella potenza:
la catena presentava come percorso alternativo la
stessa sorgente con una derivata in piu', e in piu' passava da un sensore scelto
per nome, che e' la forma esatta del difetto che integrava gradi Celsius
(`guard` su `SensorType`, uscito con LHM il 27/10/2026, D18; fix `1422d1b`). LHM esce quindi
dall'implementazione, e resta nel documento **come metodo provato e superato**:
le sue misure sono l'evidenza che il canale EMI e' corretto a finestra uguale
(rapporti 0,9947-1,0082 per fase, differenziale A-B-A 1,013-1,023, offset
+0,21/+0,27 W dopo il `guard`), il suo costo di osservazione A-B-A misurato
(0,2-0,9 W, non arbitrati) e' il precedente metodologico del nostro, e la sua
storia e' la ragione per cui il codice seleziona i sensori per `SensorType` e
non per nome. Nessuna di queste proposizioni diventa falsa quando il canale
smette di essere selezionabile: cambia lo stato, da `[I][V]` a **storico**.

La seconda meta' e' il sostituto, che dal 28-10-2026 e' **implementato**
(`energy/pawnio_backend.py`). Il ruolo da coprire non e' quello di EMI (che
resta primario) ma quello che aveva LHM: un secondo percorso dichiarato per
quando EMI non c'e'. Il percorso legge le MSR RAPL direttamente, con un
client proprio sopra il driver **PawnIO**, e il token di riga e'
`pawnio-counter` — il nome `msr-counter` della proposta non e' entrato in
codice. I registri sono per produttore:

| | Intel | AMD |
|---|---|---|
| registro di unita' | `MSR_RAPL_POWER_UNIT` `0x606` | `MSR_AMD_RAPL_POWER_UNIT` `0xC0010299` |
| contatore di package | `MSR_PKG_ENERGY_STATUS` `0x611` | `MSR_AMD_PKG_ENERGY_STATUS` `0xC001029B` |
| contatore di core (informativo) | -- | `MSR_AMD_CORE_ENERGY_STATUS` `0xC001029A` |

Gli indirizzi sono quelli di `arch/x86/include/asm/msr-index.h:496-522` (kernel
`master`, letto il 27-10-2026), non quelli della tabella di sostituzione che
circolava, che dava `0x606`/`0x611` per "Intel e AMD (Ryzen)": su un Ryzen
quegli indirizzi non sono l'unita' ne' il package, e un lettore che li usasse
leggerebbe registri diversi senza accorgersene. E' la stessa classe di errore di
F13 -- un valore plausibile dal posto sbagliato -- e per questo la tabella qui
sopra e' per produttore, non per famiglia.

**La porta HVCI/firma, con criteri dichiarati.** Il backend si dichiara
disponibile solo se passano tutti, in quest'ordine (`__init__`,
`energy/pawnio_backend.py:381-537`):

1. piattaforma Windows e produttore dal `VendorIdentifier`: un produttore
   sconosciuto non si indovina (`vendor_unknown`);
2. servizio `PawnIO` in esecuzione (`service_not_running`) e percorso del
   driver noto (`driver_path_unknown`);
3. stato HVCI da
   `HKLM\SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity\Enabled`
   e firma da `Get-AuthenticodeSignature` (`_signature_rejection`, `:540-554`):
   - firma diversa da `Valid` → `driver_signature_invalid`, sempre;
   - con HVCI **attivo o non determinabile** il firmatario deve essere
     Microsoft, altrimenti `driver_signer_not_microsoft`: un `unknown` di
     PowerShell non e' una firma valida e nel dubbio si rifiuta (fail closed);
   - con HVCI **disattivato** una firma valida di terzi e' ammessa, ed e'
     l'unico caso in cui lo e';
4. modulo presente (`module_missing`) e SHA-256 uguale a quello pinnato della
   release 0.2.11 (`module_hash_mismatch`): un blob diverso non e' stato
   verificato da nessuno e non si carica;
5. `pawnio_open` / `pawnio_load` / `pawnio_version`; su `E_ACCESSDENIED` la
   ragione e' `access_denied`, non `pawnio_unavailable` (privilegi, sotto);
6. unita' da `0x606` / `0xC0010299`, poi prima lettura del contatore: un
   registro nullo o implausibile non diventa un quantum assunto
   (`unit_unreadable`).

Il 28-10-2026 la porta e' passata su questo host: HVCI `enabled`, firma
`Valid`, firmatario `Microsoft Windows Hardware Compatibility Publisher`,
`IntelMSR.bin` 0.2.11 con hash pinnato, `PawnIOLib 2.0.0` letta a runtime,
`0x606 = 0xA0E03` → campo `EU` = 14 → quantum 6,103515625e-05 J. Artefatti:
`experiment_results/pawnio_probe_20261028*.json`. I rami di rifiuto sono
provati con firme e moduli sintetici, non su questo host.

Cinque obblighi, e come sono stati assolti:

- **L'unita' si deriva, non si copia.** Il campo e' `(unit >> 8) & 0x1F` e il
  quantum `1 / 2^EU` joule per entrambi i produttori (`arch/x86/events/rapl.c:
  609-620`; il modello AMD usa lo stesso decodificatore, `:837`), letto a
  runtime: nessuna costante scritta a mano. Un registro nullo o tutto uno non
  ha un campo utilizzabile e il backend si ferma (`unit_unreadable`), invece
  di scegliere un quantum. E' l'obbligo che AMD SMI lascia scoperto sul canale
  CPU, dove l'API restituisce un `uint64_t` senza dichiarare l'unita'.
- **Solo delta di contatori cumulativi, un avvolgimento per intervallo,
  nessuna scrittura.** Il contatore e' a 32 bit (`rapl.c:108`, maschera a
  `:573`), quindi il modulo e' `2^32`. Un calo e' un **riporto** solo se il
  vecchio valore e' almeno `0,75 · 2^32` e il nuovo al massimo `0,25 · 2^32`;
  ogni altro calo e' un **reset**, e il segmento non produce energia: mai un
  delta negativo e mai un clamp a zero. Il backend accumula i **conteggi
  interi** gia' srotolati e ne deriva i joule (`conteggi × quantum`), cosi' la
  provenienza della riga e' esatta e non dipende da un float. Nessuna funzione
  di scrittura dei registri viene mai chiamata: su Linux `energy_uj` e' `rw` e
  "Write '0' to reset", cioe' un azzeramento distruggerebbe il delta in corso.
- **Il percorso MSR non e' una validazione indipendente di EMI.** Legge lo
  stesso `0x611` (o `0xC001029B`): vale la regola 4 di §5, e la riga lo dice.
  La prova del 28-10 a finestra uguale da' rapporti PawnIO/EMI di 1,000578 e
  1,000576 su due run da 30 s: e' coerenza di implementazione fra due lettori
  dello stesso registro, **non** un arbitrato della scala assoluta, che resta
  non arbitrata senza un wattometro AC/DC esterno. Il valore del percorso e'
  coprire il caso "driver EMI assente".
- **Licenza e privilegi si citano come sono.** PawnIO e' **GPL-2.0** con
  l'eccezione per "independent modules that communicate with PawnIO solely
  through the device IO control interface": il nostro client ctypes e' quella
  classe e i moduli (`PawnIO.Modules`, **LGPL-2.1**) restano separati dal
  nostro codice. "Licenza pulita" era sbagliato come formulazione: la licenza
  e' GPL-2.0 e il nostro uso e' compatibile *per l'eccezione*, da citare ogni
  volta che si cita il driver. La compatibilita' HVCI e la firma del pacchetto
  distribuito, che la proposta dava per acquisite, sono ora **verificate**:
  HVCI attivo, firma `Valid`, firmatario Microsoft (sopra).
- **I privilegi si misurano, non si deducono.** Misurati il 28-10-2026 con
  `tools/pawnio_priv_probe.py` sotto tre token dello stesso utente, stesso
  driver, stessa configurazione: con il gruppo Administrators **enabled** il
  driver apre; con il token UAC filtrato (integrita' media, Administrators
  deny-only) e con il token SAFER normal user (integrita' **alta**,
  Administrators deny-only) `pawnio_open` risponde `0x80070005` e la ragione e'
  `access_denied`. Il discriminante e' il processo elevato, non l'integrita':
  il token SAFER ha la stessa integrita' di quello elevato e fallisce lo
  stesso. **Il fallback `pawnio-counter` richiede quindi un processo elevato**
  (EMI no), e la riga lo dichiara nei `notes`: un percorso che richiede
  elevazione cambia il profilo operativo.

Il token e' in `MEASURED_METHODS` (`energy/energy_session.py:73-74`) e la catena
Windows e' **`emi-counter` → `pawnio-counter` → `unavailable`**: il secondo si
apre solo se il primo non c'e', perche' legge lo stesso registro e sommarli
conterebbe due volte. L'ammissione richiedeva due misure, e ci sono entrambe:
il confronto a finestra uguale (rapporto 1,000578 e 1,000576 su due run da
30 s) e il costo di osservazione con A-B-A (due run da 3 × 60 s: 0,26-0,42 %
di un core nella fase con il campionatore; livello sotto 1,0 W nel run
attribuibile, inconclusivo nell'altro perche' la deriva idle di 0,56-0,71 W
domina, e la prova non si presenta come "costo nullo"; §4 di
`experiment_results/pawnio_probe_20261028_analisi.md`). Stato: **[I] con [V]
su questo host Intel**; il ramo AMD e' provato con libreria finta, **[V] da
fare**; riporto e reset reali non sono stati esercitati (60 s non bastano a un
riporto da `2^32` a ~12 W). Non e' una validazione indipendente della scala.

**Idee prese dalle fonti lette il 27-10-2026, e dove entrano.** Nessuna di queste
e' codice: sono proposizioni verificate che cambiano una regola, un obbligo o una
nota.

| idea | da dove | dove entra |
|---|---|---|
| la lettura diretta delle MSR RAPL e' pratica corrente, non un'invenzione nostra | Score-P plugin (BSD-3), likwid (GPL-3.0), x86_energy (LGPL-2.1) | D18 come precedente dichiarato, senza prendere codice |
| il registro Intel si aggiorna circa ogni 1 ms, e un intervallo corto disturba mentre uno lungo e' meno esatto | Intel RAPL advisory; `README` del plugin Score-P ("roughly every msec", default 50 000 us) | regola 7 di §5: cadenza osservata e dichiarata; la sonda a 50 ms resta sopra il registro |
| l'unita' di energia puo' non essere dichiarata dall'API e va derivata dal registro di unita' | AMD SMI `group__energyinfo`, canale **CPU** ("RAPL MSR", nessuna unita'); kernel `msr-index.h`. Il canale **GPU** invece la dichiara come regola d'uso (28-10-2026): "energy_accumulator * counter_resolution = total_energy_consumption in micro-Joules" | obbligo "si deriva, non si copia" (§3.1.2), verificato a G1 (§2.2), applicato al canale CPU dove l'unita' manca davvero; sul canale GPU la risoluzione si legge dall'API e si rifiuta il contatore se e' zero o assente |
| il contatore di energia puo' essere scrivibile, e azzerarlo distrugge il delta | kernel powercap (`energy_uj (rw)`, "Write '0' to reset") | R1 e D18: il lettore non scrive mai |
| una cascata che sceglie "whichever answers first" non e' dichiarata nella riga | PowerJoular *How it works* | controesempio della regola 1 (nessun fallback silenzioso) |
| su multi-socket si legge solo il primo package | PowerJoular *How it works* | F11 e D15: la scelta del canale e' un difetto dichiarato, non una semplificazione |
| l'avvolgimento del contatore e' correggibile solo se si legge prima che il contatore riempia meta' del suo intervallo | PowerJoular *How it works* | il backend ricostruisce **un** avvolgimento per intervallo dal `max_energy_range_uj` della zona e rifiuta la lettura se il massimo non e' leggibile (`energy/rapl_backend.py:190-198`); la condizione della fonte -- leggere prima che il contatore riempia meta' del suo intervallo -- resta valida e non e' misurata su questo host |
| 70 W di offset perche' "with RAPL only the energy consumption of the CPU is measurable" | `README` del plugin Score-P | confine di E1: qualunque numero "di sistema" costruito da RAPL e' un'estrapolazione dichiarata |
| i valori possono uscire in mJ interi, cioe' quantizzati | `README` del plugin Score-P | nota di quantizzazione della colonna: da dichiarare, non da nascondere |
| un proxy davanti all'API dichiara i propri limiti (nessuna attribuzione per richiesta, nessuna telemetria CPU o DRAM) | llm-power-profiler (MIT) | §3.2 e riga GPU: modello di come si scrive il confine, nessun ingresso in catena |
| su AMD SMI la GPU espone potenza in W (M2) e, nella documentazione piu' recente, anche un contatore di energia con unita' derivabile (`energy_accumulator * counter_resolution` = uJ) | AMD SMI `group__energyinfo` / Python API (28-10-2026); la verifica del 27-10 su `docs-6.2.0` non lo trovava | A1 e riga 11 di §4: il contatore e' M1 **se la sonda risponde**, altrimenti resta la potenza (M2); l'unita' del canale CPU RAPL MSR resta invece non dichiarata |

### 3.2 GPU e NPU

**Confine, in testa.** Nessun canale di questa tabella misura "Ollama sulla
GPU". N1, N2, A1, A2, A3, I1 e I2 sono **whole-device**: energia dell'intera
scheda nella finestra, qualunque processo la usi, comprese le altre
applicazioni e il desktop. N3 e `gpu_process_energy_j` sono **attribuzione**: ripartiscono
l'energia whole-device secondo una quota di utilizzazione, e restano
informativi. Le due grandezze non si confrontano e non si sommano; una riga che
porta energia GPU deve dire quale delle due sta scrivendo
(`gpu_energy_attributed_j` contro `gpu_process_energy_j`).

| id | interfaccia e unita' | livello | confine | etichetta | stato |
|---|---|---|---|---|---|
| N1 | NVML `nvmlDeviceGetTotalEnergyConsumption`, mJ | M1 | whole-device; delta fra i bordi, punto zero = ultimo reset; Kepler o superiore | `nvml-energy` | **[I] implementato il 28-10-2026** (doc NVIDIA R535 verificata: mJ, "since the last reset", "does not overflow"); [V] su GPU reale da fare |
| N2 | NVML `nvmlDeviceGetPowerUsage`, mW, integrata | M2 | whole-device; sampling richiesto 0,5 s, cadenza effettiva NVML da verificare | `nvml-power-integral` | [I], [V] da fare (nessuna GPU sul host) |
| N3 | NVML `nvmlDeviceGetProcessUtilization`, ms di GPU per PID | M3 | attribuzione, non misura | campo `gpu_process_energy_j` | [I] informativo |
| A1 | AMD SMI, `amdsmi_get_energy_count` (accumulator x resolution, uJ, piu' timestamp a 1 ns) e `amdsmi_get_power_info` (W) | M1 per il contatore, M2 per la potenza | whole-device; contatore "since last restart/gpu reset"; non supportato su VM guest; timestamp fermo = lettura non valida, delta negativo = reset/avvolgimento (nessun clamp) | `amdsmi-energy` -> `amdsmi-power-integral` | **[I] implementato il 28-10-2026** (doc ROCm 27.1.0 letta il 28-10: "energy_accumulator * counter_resolution = total_energy_consumption in micro-Joules"; campi di potenza tutti in W, `socket_power` generale); [V] su GPU AMD reale da fare |
| A2 | ADLX (Windows), potenza GPU | M2 candidato | whole-device | `power-integration` (GPU) | [P]: API e stabilita' da verificare alla fonte; su Windows e' il percorso AMD dopo AMD SMI |
| A3 | `amdgpu` hwmon, `power1_average` (uW, media su intervallo) | M2 candidato | whole-device | `power-integration` (GPU) | [P]: percorso Linux; legge lo stesso sensore che alimenta AMD SMI, quindi l'accordo non e' indipendente |
| I1 | dGPU Intel: nessun backend; candidati Level Zero (Windows e Linux) e hwmon `xe`/`i915` (Linux) | M4 | whole-device | `unavailable` | [A] oggi; i due candidati sono [P] |
| I2 | `xe`/`i915` hwmon, `power1_average` (Linux) | M2 candidato | whole-device per la dGPU; per la iGPU il valore e' dentro PKG e non separabile | `power-integration` (GPU) | [P] |
| PP1 | EMI PP1 / LHM "CPU Graphics" | M1/M2 sub-dominio | iGPU **dentro** PKG | campo informativo | [I][V] |
| NPU | nessuna interfaccia verificata su Windows/Linux | M4 | integrata: dentro PKG; discreta: nessun backend | `unavailable` | [A] |
| ANE | `powermetrics` su Apple Silicon | M2 candidato (M1 se il valore e' cumulativo) | unita' neurale Apple; dominio, unita' e copertura da verificare | `powermetrics` (proposto) | [P] |

Precisazioni.

- **N2 e' whole-device.** `idle_gpu_power_w` e' letto ma non assegnato da
  nessun percorso di produzione: `gpu_idle_provenance` e' `missing` per
  costruzione e `gpu_energy_attributed_j` e' l'energia dell'**intera scheda**
  nella finestra (`energy/local_energy.py:849-880`). Non e' la stessa
  grandezza di `ollama_active_energy_j`.
- **N1, se implementato, sostituisce N2 come canale primario.** Nella catena
  diventa il primo livello e N2 scende a fallback: un contatore non ha bisogno
  di integrazione e non soffre della cadenza, ma resta da verificare che il
  driver lo esponga e con quale dominio. Finche' non c'e', N2 e' l'unico
  canale GPU NVIDIA.
- **N3 e' M3: ripartizione proporzionale.** Ripartisce l'energia board attiva
  tra i PID secondo la frazione di utilizzazione GPU
  (`energy/energy_session.py:1574-1613`): e' un modello, etichettato
  informativo, non una lettura per processo. La quota di utilizzazione non e'
  una quota di energia, e il risultato non si presenta come misurata.
- **A2, A3, I2: stesso confine, interfacce diverse.** AMD SMI e' l'interfaccia
  documentata dal produttore; ADLX e hwmon sono percorsi di accesso alternativi,
  e il loro ordine e' quello della catena (AMD SMI prima) non un giudizio di
  qualita' misurata. Su Linux `power1_average` e' una **media su intervallo** in
  microwatt: integrarla somma la cadenza dell'interfaccia a quella del nostro
  campionamento, come per N2, e vale la regola 7 di §5 (cadenza osservata). Su
  AMD la documentazione dell'API dichiara che alcune letture non sono
  disponibili nelle VM guest: e' un caso di `vm` (§4.1), non un guasto del
  canale. Nessuna di queste righe e' un contatore: la catena GPU AMD resta M2 e
  non si promuove a M1 perche' il numero e' plausibile (invariante 2 di §3.0).
  `rocm-smi --showpower` e' la stessa lettura via CLI, non un canale in piu'.
- **I1, I2: la iGPU non si somma.** La grafica integrata Intel e AMD e' dentro
  PKG (riga 13 di §4): un `power1_average` della iGPU non si somma al package
  ne' si presenta come energia di una GPU discreta. Per la dGPU Intel non
  esiste oggi un canale verificato; Level Zero e' un candidato su entrambi i
  sistemi, `xe`/`i915` solo su Linux, entrambi [P] e fuori dalla catena finche'
  G0-G3 non sono verificati su hardware.
- **NPU.** Su Windows e Linux non esiste un backend verificato. Una NPU
  integrata consuma dentro PKG ma non e' separabile: non si puo' dire "energia
  della NPU" ne' per differenza ne' per quota inventata. Non si aggiungono
  colonne NPU al CSV prima che esista un backend: sarebbero colonne vuote che
  suggeriscono un canale inesistente.
- **ANE [P]: cosa va verificato.** Tre cose, tutte prima di qualunque
  dichiarazione. Il **dominio**: cosa include il contatore ANE dichiarato da
  `powermetrics`, se e' solo l'unita' neurale o anche memoria e altri blocchi
  condivisi. L'**unita'**: se il valore e' potenza media su intervallo, il
  canale e' M2 e si integra con la cadenza dichiarata; se e' cumulativo, e' M1
  e va sottratto, non integrato. La **copertura**: se lo strumento riporta solo
  gli intervalli in cui l'ANE e' attivo, la finestra non e' confrontabile con
  quella del client e va segmentata o dichiarata. Finche' le tre verifiche non
  ci sono, ANE resta `unavailable` e non produce colonne.

### 3.3 macOS

| id | interfaccia e unita' | livello | confine | etichetta | stato |
|---|---|---|---|---|---|
| PW1 | `powermetrics`, potenza media in mW per CPU/GPU/ANE, integrata | M2 | dominio dichiarato; richiede sudo; cadenza ~1 s | `powermetrics` (proposto) | [P] |
| BT1 | delta energia batteria via IOKit AppleSmartBattery | M2 di **sistema** | tutto tranne la carica; non e' un dominio | `battery-delta` (proposto) | [P] |
| EI | Monitoraggio Attivita' "Energy Impact" | nessuno | indice composito relativo, non joule | **non usato** | [A] |

Oggi il codice risponde `unavailable` su macOS
(`energy/energy_session.py:153-164`). La catena progettata e'
`powermetrics -> unavailable`; il delta batteria e' un limite di sistema, non
un fallback di dominio, e non si presenta come energia della CPU. "Energy
Impact" non e' energia: non entra nella catena.

Su **Mac Intel** `powermetrics` espone stime derivate dai modelli energetici
Intel, non misure assolute: stessa etichetta, classe di incertezza piu' alta,
e mai presentate come contatore. Su Apple Silicon i domini CPU/GPU/ANE sono
quelli dichiarati dallo strumento; anche li' la verifica alla fonte Apple e'
condizione di G1.

### 3.4 Cloud e rete

| id | interfaccia e unita' | livello | confine | etichetta | stato |
|---|---|---|---|---|---|
| C0 | hardware noleggiato misurato con NVML sul nodo stesso (es. Colab) | **M1/M2 di un dominio remoto** | GPU del nodo remoto, whole-device; non e' una stima | `power-integration` / `nvml-energy` con `endpoint = rented-gpu` | [P] percorso non integrato lato client |
| C1 | telemetria energetica reale del provider | misura remota | server del provider | `provider-telemetry` (proposto) | [A] non disponibile |
| C2 | EcoLogits `llm_impacts`, modello registrato | stima | server-side datacenter (usage + PUE); esclude rete, client, embodied | `ecologits` | [I] non validato |
| C3 | EcoLogits con proxy di pari classe dichiarato | stima | come C2, su un modello diverso da quello richiesto | `ecologits` + proxy in `hw_profile`/note | [I] |
| C4 | EcoLogits `compute_llm_impacts` con i parametri attivi reali del modello, e la loro fonte, in config | stima | come C2, ma con il costo per token del modello **richiesto** invece che di un gemello registrato | `ecologits` con `model_params_source` | [P] non implementato |
| C5 | modello analitico per classe di modello, con coefficienti propri e provenienza dichiarata (la struttura dei termini di SweetSpot come scheletro, non i suoi coefficienti) | stima con boundary dichiarato, **non misura** | acceleratore di riferimento, serving open-source, steady state | `analytic-class-fit` | **[P] non implementato**; disegno in `metodo_analitico_cloud_20261026.md` |
| T1 | delta contatori NIC del client x coefficiente J/bit | stima, scala propria | byte system-wide del client x percorso trasmissione+commutazione fino al data center, accesso escluso; ne' NIC del client ne' accesso sono contate | campo `network_*` | [I] non validato |
| T2 | byte del payload HTTP x coefficiente J/bit | stima, scala propria | body richiesta+risposta al socket x lo stesso percorso; sottostima header, TLS e ritrasmissioni | campo `network_*` | [I] |
| W1 | wattometro AC/DC esterno | riferimento | sistema completo a monte dell'alimentatore | non e' un livello runtime: e' **validazione off-line** | [A] in acquisto |
| W2 | presa intelligente con misura di energia | riferimento provvisorio | intero sistema alimentato dalla presa; non e' un dominio | `smart-plug` (proposto, mai in una catena) | [A] non misurato, specifiche da verificare |

Precisazioni.

- **C3: che cosa rende un proxy "di pari classe".** Il proxy e' ammesso solo se
  coincide con il modello richiesto su tutte le dimensioni che determinano il
  costo per token: famiglia e architettura, parametri **attivi** per token (nei
  MoE i parametri totali non sono il costo), quantizzazione/precisione, e
  classe hardware che EcoLogits associa al modello. Se una dimensione diverge,
  il proxy non e' di pari classe. La banda numerica che rende "comparabili" i
  parametri attivi e' una soglia: va congelata in P5 prima dei dati, non
  scelta qui; fino ad allora le quattro dimensioni si scrivono nella riga e la
  decisione si prende caso per caso. Se nessun modello coincide, il risultato
  e' `unavailable`, non un proxy di classe diversa presentato come C2.
- **C0: il GPU noleggiato non e' una stima.** Se l'inferenza gira su una macchina
  di terzi a cui si puo' eseguire codice (Colab, un nodo affittato), NVML li'
  misura la scheda: e' un M1/M2 del dominio `gpu_dedicated` sul **remote
  endpoint**, non un modello cloud. La riga deve dire quale host ha prodotto il
  numero (`endpoint`), e il client locale non aggiunge nulla: quando il server
  e' remoto, l'energia locale del package non rappresenta l'inferenza (vedi
  `remote_endpoint` in §4.1). Oggi C0 non esiste nel percorso client: [P].
- **C4: prima del proxy, i parametri reali.** `compute_llm_impacts` accetta i
  parametri del modello (attivi inclusi) senza chiedere un modello registrato:
  con i parametri reali del modello richiesto, e la loro fonte scritta in
  config, la stima resta dentro EcoLogits ed e' piu' aderente di un proxy di
  pari classe. Quindi la catena effettiva e' C2 -> C4 -> C3 -> C5 -> `unavailable`:
  il proxy e' l'ultimo ricorso **dentro** EcoLogits, non la scorciatoia. Il divieto
  di §6 resta per tutto cio' che precede C5: fuori dal motore c'e' un solo
  gradino ammesso, C5, con fit proprio, boundary proprio e gate di ammissione
  (bullet sotto).
- **C5: l'ultimo gradino e' una stima con un boundary diverso dagli altri.** C5
  non e' un secondo lettore di C2 e non e' una misura: e' un modello analitico
  per **classe** di modello, i cui coefficienti sono fittati da noi e la cui
  provenienza va scritta in riga. Tre regole, perche' senza di esse il gradino
  diventerebbe un numero indistinguibile dagli altri:
  - **non e' additivo con C2, C3 e C4**: sono gradini alternativi della stessa
    catena, e la riga porta **uno** `cloud_energy_method`, non una somma;
  - **non eredita il `min(request_latency, gpu_latency)` di C2 senza dichiararlo**:
    se C5 usa la latenza misurata linearmente e C2 la tronca, le due stime
    divergono per struttura e non per calibrazione, e il confronto G3 sarebbe
    viziato. La scelta (latenza lineare con il troncamento dichiarato come
    scelta, oppure lo stesso `min`) va scritta nel fit della classe, non
    ereditata per caso;
  - **include i token di input** (`cloud_input_tokens_included = true`): nel
    modello `k_pre·n_in` e `k_attn·n_in^2/n_out` sono termini espliciti, mentre
    C2-C4 li escludono. Per questo C5 sta sopra C2 per costruzione su prompt
    lunghi, e lo scarto non e' calibrazione.
  Il boundary e' "acceleratore di riferimento, serving open-source, steady
  state": non e' l'hardware del provider, e il campo `cloud_measurement_boundary`
  lo dice con il testo fisso della riga. La banda min/max di C5, quando ci sara',
  e' un `calibration-semi-range` dai residui leave-one-model-out, non un
  `parameter_pue_ignorance_range`: `cloud_energy_band_semantics` distingue le due
  cose. C5 entra solo con un fit che passi il test **leave-one-model-out per
  classe**; fino ad allora lo stato e' `[P]` e la catena si ferma a `unavailable`
  dopo C3. I coefficienti pubblicati da altri non diventano i nostri senza
  l'etichetta `fit-published-transcribed`, e nessun numero di C5 si attribuisce
  agli autori della forma.
- **T1 e T2 non sono due misure della stessa grandezza.** Hanno lo stesso
  coefficiente e numeratori diversi: T1 conta i byte realmente transitati sulle
  interfacce del client, T2 solo i body HTTP della conversazione. Uno
  sovrastima per attribuzione, l'altro sottostima per costruzione; il dettaglio
  e' in §7.
- **W1 non e' un canale della catena.** Il wattometro misura il sistema
  completo a monte dell'alimentatore, non un dominio, e serve a validare
  off-line la scala assoluta degli altri canali: non produce numeri runtime e
  non si presenta come `measurement_boundary` di una riga.
- **W2: che cosa puo' dare una presa intelligente, e che cosa no.** E' un
  riferimento provvisorio **di sistema**, ordinabile subito e piu' economico del
  wattometro: serve a un controllo d'ordine di grandezza sulla scala assoluta, e
  a intercettare un errore macroscopico (un fattore 2 sul package si vede). Non
  chiude G4 e non sostituisce W1, per tre ragioni strutturali, non di misura: il
  suo numero e' a monte dell'alimentatore e include le perdite di conversione,
  quindi e' un limite superiore lasco della somma dei domini, non la somma; non
  separa nessun dominio; e su un portatile, se la batteria carica nella
  finestra, parte dell'energia misurata finisce nella batteria e non nel carico.
  Prima di usarla come riferimento vanno verificate alla fonte le tre cose che
  ne determinano la leggibilita': risoluzione e passo di quantizzazione, finestra
  di media interna, e offset o deriva a basso carico. Nessuno di questi e' noto
  per un modello specifico finche' non se ne legge il datasheet, quindi qui
  restano un obbligo di verifica, non un numero.
  Il terzo vincolo pero' **su questo host non si applica**, e la correzione e'
  di oggi: `GetSystemPowerStatus` restituisce `BatteryFlag = 128` (nessuna
  batteria installata) e `Win32_Battery` non restituisce nessuna istanza
  (verificato sull'host il 26/10; il probe registra `manufacturer = GEEKOM`,
  `model = Mini IT13`, `probes/cw_probe_windows.json`). La macchina e' un mini
  PC alimentato in rete, non un portatile: per la presa intelligente non esiste
  una carica da confondere con il carico, e il confine di sistema e' il piu'
  pulito che si possa ottenere senza wattometro. P1.4 continua a chiedere di
  registrare lo stato batteria (`protocollo_v4_20261024.md:177-178`): su questa
  macchina la registrazione da' "assente", che va scritto, non omesso. Su un
  host con batteria, invece, il vincolo torna e la presa misura anche la carica.
- Il coefficiente `2,7e-6 J/bit` (`config.py:332-362`) e' **documentato ma non
  validato**: valore e perimetro vengono da una fonte primaria verificata il
  26-10-2026 (Baliga, Ayre, Hinton, Tucker, *Proc. IEEE* 99(1):149-167, 2011,
  DOI 10.1109/JPROC.2010.2060451), ma la fonte e' una stima da modello con la
  rete di accesso esclusa, mentre i byte contati sono system-wide sul client. La
  discrepanza di perimetro e' dichiarata, non risolta. Dettagli in §7.

---

## 4. Catene per configurazione

La catena si legge da sinistra a destra; la prima che passa G0-G3 vince. La
colonna "oggi" dice cosa fa il codice al 26/10, non cosa dovrebbe fare. La
matrice della revisione del 27/10, livello per livello e con i percorsi
rifiutati, e' in §4.2: e' la vista piu' recente, e dove le due tavole divergono
vale quella.

| # | configurazione / dominio | catena | etichette | oggi |
|---|---|---|---|---|
| 1 | Windows Intel, `cpu_package` | EMI PKG -> `pawnio-counter` -> `unavailable` | `emi-counter` -> `pawnio-counter` -> `unavailable` | EMI attivo e primo; **LHM rimosso dall'implementazione (D18)**: se EMI manca si prova il contatore MSR via PawnIO, che pero' richiede un processo elevato; senza elevazione la riga e' `unavailable` |
| 2 | Windows Intel, EMI non disponibile e PawnIO installato | MSR P1 (`0x606` + `0x611`) -> `unavailable` | `pawnio-counter` -> `unavailable` | **[I] con [V] su questo host (28/10)**: confronto a finestra uguale e costo di osservazione misurati; richiede un processo elevato (`access_denied` senza), altrimenti `unavailable` con la ragione |
| 3 | Windows AMD, `cpu_package` | EMI **se il probe passa** -> MSR P1 AMD (`0xC0010299` + `0xC001029B`) -> `unavailable` | `emi-counter` -> `pawnio-counter` -> `unavailable` | il ramo AMD e' implementato con i registri propri (`0x611` non si legge su AMD) e provato con libreria finta; **[V] da fare**: su AMD non e' mai stato eseguito; con piu' die vale la deduplica di F11 |
| 4 | Qualsiasi OS, `CW_ENERGY_FILE` impostato | `energy-file` -> (catena normale se non impostato) | `energy-file` | priorita' di selezione su EMI e su P1; uso test/dev |
| 5 | Linux Intel, `cpu_package` | RAPL package -> `unavailable` | `rapl` -> `unavailable` | implementato, mai esercitato; 3 test saltati |
| 6 | Linux Intel, `psys` | RAPL psys -> `unavailable` | `rapl` con dominio `psys` | non implementato; non e' un fallback di 5 |
| 7 | Linux AMD, `cpu_package` | powercap RAPL AMD (kernel >= 5.11, se il percorso e la semantica sono verificati) -> hwmon `amd_energy` -> `unavailable` | `rapl` (dominio dichiarato) -> `unavailable` | non implementato; R3b ha scala propria (15,3 uJ) e copre prima EPYC che Ryzen client |
| 8 | macOS Intel o Apple Silicon, CPU/GPU/ANE | `powermetrics` -> `unavailable` | `powermetrics` -> `unavailable` | `unavailable`; powermetrics progettato |
| 9 | macOS laptop, sistema | delta batteria (limite di sistema) -> `unavailable` | `battery-delta` -> `unavailable` | non implementato |
| 10 | NVIDIA, `gpu_dedicated` | NVML total energy -> NVML power -> `unavailable` | `nvml-energy` -> `nvml-power-integral` -> `unavailable` | contatore sopra l'integrale dal 28-10; [V] su GPU reale da fare; idle mai calibrato -> whole-device |
| 11 | AMD, `gpu_dedicated` | AMD SMI contatore -> AMD SMI potenza -> `unavailable`; su Windows ADLX e su Linux `amdgpu` hwmon sono accessi alternativi [P] | `amdsmi-energy` -> `amdsmi-power-integral` -> `unavailable` | implementato il 28-10; percorso **AMD**, selezionato per vendor, non un gradino dopo NVML; §3.2 A1/A2/A3 |
| 12 | Intel dGPU | Level Zero (Windows e Linux) o `xe`/`i915` hwmon (Linux), entrambi [P] -> `unavailable` | `unavailable` | nessun backend; §3.2 I1/I2 |
| 13 | iGPU Intel/AMD | nessun termine separato (dentro PKG); PP1/Graphics informativi | campi `igpu_*` | PP1 letto da EMI; mai sommato |
| 14 | NPU Windows/Linux | `unavailable` | `unavailable` | nessun backend, nessuna colonna |
| 15 | NPU Apple Silicon (ANE) | `powermetrics` ANE (se verificato) -> `unavailable` | `powermetrics` -> `unavailable` | progettato, non implementato |
| 16 | Cloud | telemetria provider -> EcoLogits registrato -> `compute_llm_impacts` con parametri reali -> EcoLogits proxy -> modello analitico per classe -> `unavailable` | `provider-telemetry` -> `ecologits` -> `ecologits` (C4, con fonte dei parametri) -> `ecologits` (proxy; D3 propone `ecologits-proxy`) -> `analytic-class-fit` (C5) -> `unavailable` | TDP; stima senza provenienza; somma dei gradini; l'analisi `κ·n_in/n_out`; mai C5 presentato come misura o come EcoLogits |
| 16b | Inferenza su GPU noleggiata con codice eseguibile sul nodo | NVML sul nodo remoto (C0) -> `unavailable` | `nvml-energy` / `nvml-power-integral` con `endpoint` del nodo | non integrato nel percorso client: [P] |
| 17 | Rete | delta NIC -> contabilita' payload -> `unavailable` | campo `network_*` | delta NIC; se illeggibile restituisce 0 (difetto F1) |
| 18 | Sistema completo | wattometro (riferimento); in attesa, presa intelligente come riferimento provvisorio d'ordine di grandezza | `wall` / `smart-plug` (mai in una catena di dominio) | non disponibile nessuno dei due |
| 19 | Qualsiasi altra combinazione | `unavailable` | `unavailable` | caso residuo dichiarato, non aggirato |
| 20 | Macchina virtuale (hypervisor), `cpu_package` | nessun contatore di dominio -> `unavailable` con ragione `vm` | `unavailable` | `probes/cw_probe.py:31-58` rileva hypervisor flag, `systemd-detect-virt`, DMI; il contatore del guest non e' quello del package fisico |
| 21 | WSL2, `cpu_package` | contatore non esposto al guest -> `unavailable` con ragione `vm` (WSL2 e' una VM) | `unavailable` | il probe distingue `microsoft` nel release (`probes/cw_probe.py:41`) |
| 22 | Container (Docker) su host con contatore | RAPL/EMI **dell'host**, se il mount lo consente -> `unavailable` con ragione `permission_denied` | `rapl` / `emi-counter` con confine "host, non container" | l'energia letta e' dell'host condiviso: attribuirla al container e' M3, non M1 |
| 23 | Windows ARM, `cpu_package` | nessun canale verificato -> `unavailable` con ragione `driver_missing` | `unavailable` | EMI non verificato su ARM (ne' il percorso MSR P1, che dipende da un modulo PawnIO per l'architettura); `probes/cw_probe.py` segna il machine (`platform.machine()`) |
| 24 | Linux ARM / SBC, `cpu_package` | nessun contatore di dominio verificato -> `unavailable` con ragione `no_energy_domain` | `unavailable` | mai provato su hardware ARM: e' un'assenza **dichiarata**, non una dimostrazione; se un SBC espone powercap o hwmon, la riga 5 o la 7 si applicano |
| 25 | `OLLAMA_HOST` non locale, `cpu_package` | **la misura locale non rappresenta l'inferenza**: `unavailable` con ragione `remote_endpoint`, piu' la riga cloud del server remoto | `unavailable` + campi cloud | il probe legge `OLLAMA_HOST` (`probes/cw_probe.py:181`); senza questo flag la riga sembrerebbe locale |
| 26 | Piu' package/socket | enumerare le zone per `name`, sommare i package distinti, deduplicare i canali specchiati -> `unavailable` | `rapl` / `emi-counter` con dominio `package-0..N` | Linux: enumerazione e deduplica corrette dal 27/10 (`energy/rapl_backend.py:128-158`). Windows: enumerazione per metadato e selezione solo con **un** device CPU (27/10, `energy/emi_backend.py:226-263`); due device PKG distinti danno `ambiguous_domain` (`:266-285`). La **somma** dei package distinti resta D15, non implementata |

Cinque regole valgono per tutte le righe:

- un livello inferiore non si presenta mai con l'etichetta del superiore;
- il fallback non e' una licenza a inventare: se anche l'ultimo livello di
  misura fallisce, il risultato e' `unavailable`;
- il fallback di un dominio non degrada gli altri;
- l'assenza di un dominio (GPU, NPU) non rende invalida la misura CPU;
- nessuna riga scrive `unavailable` senza la ragione del lessico di §4.1:
  `unavailable` e' un esito, la ragione e' la meta' che dice a chi legge cosa
  fare, e le righe 20-26 esistono perche' ragioni diverse hanno rimedi diversi.

### 4.1 Le ragioni di G0 sono un lessico, non un testo libero

La riga 19 copre il caso residuo, ma `unavailable` senza ragione distinguibile
non e' utilizzabile: VM, WSL2, container, Windows ARM, Ollama remoto, permessi
e driver assente sono casi **diversi**, con rimedi diversi. G0 deve produrne la
ragione in un token:

| ragione | quando | che cosa si puo' fare |
|---|---|---|
| `vm` | hypervisor o guest senza contatore di dominio | passare a una misura dell'host, o dichiarare l'assenza |
| `remote_endpoint` | il motore di inferenza non e' sulla macchina che misura | la riga locale non rappresenta l'inferenza: si misura il nodo remoto o si usa la stima cloud |
| `permission_denied` | il nodo esiste ma non e' leggibile dal processo | root, regola udev, o privilegio del canale. Sul percorso P1 **non** basta l'installazione del driver: la lettura richiede un **processo elevato** (misurato il 28/10: `pawnio_open` da token UAC filtrato o SAFER risponde `0x80070005`, ragione `access_denied`), mentre EMI non ha questo requisito |
| `driver_missing` | il driver del canale non e' installato o non e' esposto | installare il canale, o passare al fallback |
| `no_energy_domain` | la piattaforma non espone un dominio energia | `unavailable` strutturale, non un guasto |
| `counter_stale` | timestamp di dominio fermo (G2) | segmentare o dichiarare, mai sottrarre |
| `ambiguous_domain` | package multipli o canali specchiati non risolti | enumerare e deduplicare (D15) prima di sommare; su Windows il lettore rifiuta due device PKG distinti e chiede `CW_EMI_DEVICE` (`energy/emi_backend.py:266-285`) |

La sonda che raccoglie queste evidenze esiste gia' ed e' di sola lettura:
`probes/cw_probe.py` rileva hypervisor e WSL (`:31-58`), elenca le zone powercap con
la loro leggibilita' (`:92-126`), conta i device NVML e prova il contatore di
energia (`:127-162`), legge `OLLAMA_HOST` (`:181-190`) e distingue `machine`
(`:9`). Serve che il suo esito diventi un token della riga, non un file a parte
(D11).

### 4.2 Matrice dei backend e dei fallback — revisione del 27/10/2026

Gli otto documenti di `matrice/` e `Multi-Provider EMI-First.DOCX` sono spunti,
non evidenza. Riletti contro il codice il 27/10/2026, producono tre cose: una
matrice per configurazione (a), un verdetto per documento (b) e le modifiche
di codice di questa revisione (c). Tre regole valgono per tutta la sezione, e
sono quelle di §2.3-§2.4 applicate ai documenti: un gradino in piu' nella
catena non e' un canale in piu' se legge lo stesso registro; nessun token nuovo
entra in `MEASURED_METHODS` perche' un documento lo propone; un percorso che
richiede un driver o un privilegio si dichiara con quel costo, non lo si
nasconde dietro un nome di metodo.

**(a) La matrice.** "Fallback" significa disponibilita', non precisione: i
gradini dopo il primo si usano solo se il precedente fallisce G0-G3, e nessun
gradino si somma a un altro. Due marchi in piu' rispetto a §4: `†` = stessa
lettura del gradino precedente (nessuna evidenza indipendente), `‡` = non e' un
livello di catena (controprova o riferimento).

**La GPU si seleziona per vendor.** NVIDIA si legge con NVML (`nvml-energy` ->
`nvml-power-integral`), AMD con AMD SMI (`amdsmi-energy` ->
`amdsmi-power-integral`): non esiste una catena NVML -> AMD SMI per la stessa
scheda, e i due backend non girano mai in parallelo. Nel codice il selettore
`_open_gpu_monitor()` prova NVML e poi AMD SMI (`energy/energy_session.py:1760-1775`):
e' un controllo di presenza del driver, non un gradino di fallback. Ne segue un
limite dichiarato degli host misti: con entrambi i driver installati vince NVML
e una scheda AMD presente nella stessa macchina non viene letta.

| configurazione, dominio | primario | fallback, in ordine | esclusi | etichette | stato (27/10, righe GPU aggiornate al 28/10) |
|---|---|---|---|---|---|
| Windows Intel, `cpu_package` | EMI PKG | P1 PawnIO `0x606`+`0x611` [I][V] † (richiede elevazione) -> P2 Hubblo [P] † -> P3 PMI/WMI [P] | LHM (D18) †; TDP; somma con PP0/PP1 | `emi-counter` -> `pawnio-counter` -> `unavailable` | EMI [I][V]; P1 [I][V] il 28/10; P2/P3 [P] |
| Windows AMD, `cpu_package` | EMI, se il probe passa | P1 AMD `0xC0010299`+`0xC001029B` [I] † -> P2 -> P3 | `0x611` su AMD; somma dei core `C001_029A` al package | `emi-counter` -> `pawnio-counter` -> `unavailable` | P1 [I], **[V] da fare** su AMD |
| Linux Intel, `cpu_package` | RAPL powercap (R1) | R5 `perf power/energy-pkg/` [P] †; V1 turbostat ‡ | turbostat come livello; somma delle zone; `psys` presentato come package (R2) | `rapl` -> `rapl-perf` (non ammesso) -> `unavailable` | R1 [I], [V] da fare; R5 [P] |
| Linux AMD, `cpu_package` | powercap AMD (R3, Zen 1-3, kernel >= 5.11) | hwmon `amd_energy` (R3b) † -> MSR `C001_029B` (R3c/P1) †; V1 ‡ | somma core+socket; powercap e `amd_energy` insieme; `amd_atl` (nome ritirato) | `rapl` (dominio dichiarato) -> `unavailable` | [P] |
| Qualsiasi OS, `CW_ENERGY_FILE` | contatore esterno (X1) | catena normale se la variabile non e' impostata | presentare il file come EMI | `energy-file` | [I], test/dev |
| Windows, meter V1 | EMI a un canale (E1) | catena normale | trattare un V1 come guasto; leggerlo con il parser V2 | `emi-counter` (solo V2) | **[I]**: `GET_VERSION` letto e V1 scartato con la ragione (D17, 27/10); un V1 reale non e' stato provato |
| macOS CPU/GPU/ANE | `powermetrics` (PW1) | nessuno; delta batteria e' sistema, non dominio (BT1 ‡) | Energy Impact; carico CPU come stima | `powermetrics` -> `unavailable` | [P] |
| NVIDIA, `gpu_dedicated` | NVML total energy (N1) | NVML potenza integrata (N2) | potenza per PID presentata come misura (N3) | `nvml-energy` -> `nvml-power-integral` -> `unavailable` | N1 [I] dal 28/10 (test con `pynvml` finto), [V] reale da fare; N2 [I]; idle mai calibrato |
| AMD, `gpu_dedicated` | AMD SMI contatore (A1) | AMD SMI potenza integrata (A1) -> `unavailable`; poi ADLX (A2) ‡ e Linux `amdgpu` hwmon (A3) ‡ come accessi alternativi; `rocm-smi --showpower` ‡ | somma iGPU+dGPU; attribuzione per PID | `amdsmi-energy` -> `amdsmi-power-integral` -> `unavailable` | A1 [I] dal 28/10 (test con `amdsmi` finto), [V] reale da fare; percorso AMD, non un gradino dopo NVML |
| Intel dGPU | Level Zero (I1) [P] | Linux `xe`/`i915` hwmon (I2) [P] ‡ | iGPU sommata al package | `unavailable` oggi | [A] |
| iGPU Intel/AMD | dentro PKG (PP1, E2) | nessun termine separato | somma al package; PP1 presentato come GPU | campo `igpu_energy_j` | [I][V] |
| NPU Intel/AMD | nessun canale verificato | -- | colonne NPU vuote; "per differenza" | `unavailable` | [A] |
| ANE (Apple Silicon) | `powermetrics` ANE [P] | -- | -- | `powermetrics` -> `unavailable` | [P] |
| DRAM | EMI DRAM (E3) / zona `dram` powercap (D1) [P] | -- | somma al package | campo separato | E3 [I][V]; D1 [P] |
| Rete | delta dei contatori NIC del client x coefficiente J/bit (T1) | byte del payload HTTP x coefficiente J/bit (T2) -> `unavailable` | un contatore **energetico** di rete (non esiste); J/bit senza fonte; zero al posto di N/A | `network_*` | [I] non validato: i byte sono **misurati** da contatori NIC, il J/bit e' un'ipotesi dichiarata, quindi il numero e' una stima |
| Cloud | telemetria provider (C1) | EcoLogits registrato (C2) -> C4 parametri reali -> proxy (C3) -> modello analitico per classe (C5) -> `unavailable` | TDP; stima senza provenienza; somma dei gradini; `κ·n_in/n_out` | `provider-telemetry` -> `ecologits` -> `analytic-class-fit` -> `unavailable` | [I] C2/C3, [P] C4 e C5 |
| Sistema | wattometro AC/DC (W1) ‡ | presa intelligente (W2) ‡ | RAPL estrapolato a "sistema" | `wall` / `smart-plug`, mai in catena | [A] |
| VM, WSL2, container | contatore dell'host, se dichiarato | `unavailable` con ragione `vm` / `permission_denied` | contatore del guest presentato come package fisico | `unavailable` + ragione | [I] sonda |
| Nessun canale | `unavailable` con la ragione | -- | zero | `unavailable` | [I] |

**(b) Cosa si adotta, cosa si rinvia, cosa si rifiuta.** Per ogni documento,
l'apporto e il verdetto; dove il verdetto e' "rifiutato" la ragione e' scritta,
perche' un rifiuto senza ragione diventa un arretrato.

| documento | apporto | verdetto |
|---|---|---|
| `powerjoular.DOCX` | ordine EMI -> PawnIO -> Hubblo su Windows; catena "primo che risponde"; solo il primo package su multi-socket; attribuzione per quota CPU-time | **adottato** l'ordine e la regola "fallback = disponibilita'"; **rifiutate** la cascata non dichiarata (regola 1 di §5) e la lettura del solo primo package (F11: corretta dall'enumerazione su Linux e, dal 27/10, dalla selezione per metadato su Windows; la **somma** dei package distinti resta D15); la quota CPU-time e' gia' M3 (§8). Uso: stato dell'arte in tesi, nessun codice |
| `llm-power-profiler.DOCX` | proxy davanti all'API che dichiara i propri limiti: nessuna attribuzione per richiesta, nessuna telemetria CPU/DRAM; export per richiesta | **adottato** il modello di confine (§3.2, §5); **rinviato** l'export per-richiesta: aggiunge un campionamento il cui costo di osservazione non e' ancora misurato A-B-A (precedente: 0,2-0,9 W, non arbitrati) |
| `pmi-wmi.DOCX` | PMI/WMI come fallback di potenza | **adottato** come riga P3 [P] e come sonda di G0 nella diagnostica; **corrette** due affermazioni: la proprieta' `PowerMeasurement` non esiste, il dominio e' di piattaforma (probabilmente sistema), e su questo host le istanze sono zero |
| `1.DOCX` | mappa completa dei metodi RAPL; dettagli di `perf` (contatore a 64 bit in 1/2^32 J, scala nel file `.scale`); tabella MSR con `0x64d` psys; turbostat e LIKWID come diagnostica | **adottati** R5, V1 e D1 come righe, e la regola che solo il wattometro arbitra la scala; **rinviati** i due dettagli di `perf` e l'indirizzo di `psys` alla verifica alla fonte prima del codice (classe F13); **rifiutato** turbostat come livello di catena |
| `2.DOCX` | catene AMD: powercap `amd-rapl`, hwmon `amd_energy`, MSR `C001_029B`; AMD SMI per GPU; "mai `0x611` per AMD" | **confermato** cio' che R3/R3b/R3c e A1 gia' dicono (§3.1.2); **adottate** A2 e A3; il percorso `amd-rapl:*` e la disponibilita' di EMI su AMD restano da verificare (stato [P]) |
| `librerie.DOCX` | scelta delle librerie (ctypes per EMI, sysfs per powercap, `pynvml`, `amdsmi`, `psutil`); gerarchia `EnergyBackend`/`EnergyReading`; `measure_window` con `max(0.0, end-start)`; protocollo LIKWID a N >= 10 con media e deviazione standard | **adottate** le librerie gia' in uso e LIKWID come controprova (V1), non runtime; **rifiutati** il clamp a zero (viola "nessun troncamento": gli incrementi negativi si conservano con `negative_increment`), la gerarchia parallela (la tassonomia arbitro e' il CSV, non una classe) e N >= 10 con `sd` (P4.12, e `n` e' fissato da P2.9/P6); il frammento EMI usa una costante IOCTL che non e' ne' quella documentata ne' la nostra (`0x0022400C`, `energy/emi_backend.py:67`) |
| `matrice.DOCX` | parte iniziale coincidente con questa specifica; coda con la vecchia proposta PawnIO (`0x606`/`0x611` "Intel e AMD (Ryzen)", "licenza pulita") | **ritirate** le due affermazioni errate (§3.1.2); **adottata** la correzione del 27/10 (EMI primo, `C001_029B` per AMD), che e' quella gia' scritta qui; **da verificare** il dato su N2: su Ampere e successive la potenza NVML sarebbe mediata su circa 1 s, e cambierebbe la cadenza dichiarata |
| `matricefull.DOCX` | matrice per dominio e OS; righe GPU Intel, NPU, DRAM, rete, sistema; schema JSON per riga con `quality`; priorita' di implementazione | **adottate** le righe mancanti (I1/I2, D1) e la regola "un fallback non degrada gli altri domini" (gia' §4); **rifiutato** il vocabolario `quality` parallelo a M1-M4 (doppia tassonomia: l'arbitro per riga resta il token di metodo, §3.0 invariante 1) e il campo `attribution`, che e' il confine G3 gia' dichiarato in `measurement_boundary` |
| `Multi-Provider EMI-First.DOCX` (radice) | EMI primo, conversione pWh, GUID; `EnergyProvider` con `select_energy_backend`; JSON `backend_id`/`measurement_type`/`status`; fallback "TDP x CPU time" marcato `estimated` | **adottato** EMI primo e la conversione, gia' in produzione; **rifiutati** il TDP in catena (X2/D10: opt-in, fuori catena, nessun token `estimated` in `MEASURED_METHODS`) e la gerarchia con JSON parallelo (stesse ragioni di `librerie.DOCX`) |

**(c) Cosa e' cambiato nel codice in questa revisione.** Tre modifiche, tutte
verificabili senza hardware e senza toccare la catena di produzione.

1. **RAPL: enumerazione delle zone e riporto onesto.** `energy/rapl_backend.py`
   non e' piu' cablato su `intel-rapl:0`: enumera `/sys/class/powercap`, tiene
   le zone il cui `name` inizia per `package-`, somma i package distinti,
   deduplica i canali specchiati per nome con una nota, legge
   `max_energy_range_uj` **per zona**. Se il contatore decresce e il massimo non
   e' leggibile, la lettura viene rifiutata con "riporto non determinabile"
   invece di applicare il `2**32` che il codice assumeva: un'avvolgimento
   ricostruito su un'assunzione e' un numero inventato, non una misura. Chiude
   la prima meta' di R1 (§3.1) e F11 sul lato Linux. Otto test nuovi
   (`tests/test_rapl_zone.py`) su un finto sysfs, eseguibili su Windows.
2. **Diagnostica: la sonda PMI esiste, il valore no.** Su Windows, quando EMI
   non e' disponibile, `diagnostics.py` interroga `Win32_PowerMeter` e distingue
   tre esiti: meter presenti (non e' un canale: manca G1, e il dominio va
   verificato), zero meter (coerente con `driver_missing` o
   `no_energy_domain`), sonda non conclusiva (permessi o provider). Non legge
   nessun valore e non cambia lo stato del motore energetico. Sette test
   (`tests/test_diagnostics_pmi.py`) sul parser e sulla classificazione.
3. **Riga locale: il cloud zero dichiara metodo e confine.** In `local` la riga
   scrive `cloud_energy_method = "not-applicable"` e
   `cloud_estimation_boundary = "not-applicable (local mode)"` accanto allo zero
   di confine (`benchmark_unified.py:508-517`); la riga cloud continua a non
   pre-etichettare alcun metodo, perche' il metodo lo scrive il blocco che
   produce la stima. Chiude F9.
4. **Selezione EMI semantica: il device e il canale si scelgono dal metadato.**
   `energy/emi_backend.py` enumera tutte le interfacce del GUID e legge, per
   ciascuna, `GET_VERSION` -> `GET_METADATA_SIZE` -> `GET_METADATA`; accetta
   solo un device con un canale PKG in pWh e scarta batteria, sensor hub e GPU
   con la ragione nei `notes`. Il dominio di ogni valore viene dal nome del
   canale, il buffer di misura e' 16 byte per canale, un meter V1 si dichiara
   non selezionabile e due device CPU distinti restano `ambiguous_domain`
   (`CW_EMI_DEVICE` per la scelta esplicita). Il lettore si dichiara
   `emi-reader/2` in `backend_version`; `diagnostics.py` stampa metadato,
   canali e scarti. Sedici test (`tests/test_emi_selezione.py`) su metadati
   sintetici, con il metadato reale di 492 byte come primo caso. Chiude la
   meta' Windows di F11 e F13 (§3.1.1); la catena non cambia e resta
   `EMI -> unavailable`.

5. **GPU NVIDIA: il contatore va sopra l'integrale (28-10-2026).**
   `energy/energy_session.py` sonda `nvmlDeviceGetTotalEnergyConsumption` con
   una lettura reale all'apertura — il supporto si verifica, non si presume da
   un `hasattr` — e campiona il contatore cumulativo. La documentazione e'
   quella del fornitore (NVML API Guide, R535, letta il 28-10-2026): valore in
   millijoule, "since the last reset", Kepler o superiore, "does not
   overflow". `energy/local_energy.py` usa il **delta** fra i bordi, perche'
   il punto zero e' un reset e non l'inizio della finestra, e scende a
   `nvml-power-integral` in tre casi dichiarati: contatore non esposto dal
   device, delta negativo (reset del driver), finestra con sottofinestre
   escluse (un delta non sa sottrarre il judge). Il percorso effettivo e' il
   prefisso di `gpu_attribution_method`, che comincia sempre con
   `nvml-energy` o `nvml-power-integral`. Il percorso e' **[I]**: otto test
   (`tests/test_gpu_nvml_energy.py`) con `pynvml` finto; la prova su GPU reale
   resta **[V] da fare** — su questa macchina NVML non c'e'
   (`NVMLError_LibraryNotFound`) — non e' [P]: il codice c'e' ed e' quello che
   i test esercitano.
   **Emendazione a P5, 28-10-2026:** tre colonne accodate —
   `energy_per_total_token_j`, `tokens_per_joule`, `kwh_per_million_tokens` —
   calcolate da `_finalize_energy_fields` su `total_tokens` (input + output),
   con `N/A` quando l'end-to-end non e' calcolabile e cella vuota quando
   mancano i token. Sono tre letture della stessa grandezza, non stime
   indipendenti. Nessuna colonna storica cambia posizione; la migrazione resta
   `ensure_header`.

6. **GPU AMD: AMD SMI entra come backend della scheda AMD (28-10-2026).**
   `_AMDGPUMonitor` in `energy/energy_session.py` importa `amdsmi`, chiama
   `amdsmi_init()` e prende il primo handle di `amdsmi_get_processor_handles()`;
   il nome commerciale esce da `amdsmi_get_gpu_asic_info`. La sonda di energia
   legge `counter_resolution` e lo memorizza: se e' zero o assente il contatore
   **non** si usa, e la ragione resta in `energy_counter_reason`.
   `read_energy()` applica la regola documentata dal fornitore,
   `accumulator * resolution` in microjoule, converte in millijoule perche' e'
   l'unita' che il campione porta gia' per NVML, e restituisce anche il
   `timestamp` del device. `read()` usa la potenza in W nell'ordine
   `socket_power` (generale), `current_socket_power` (Mi300+),
   `average_socket_power` (Navi e MI 200 o precedenti) — l'ordine lo detta la
   tabella del fornitore, non una preferenza — e registra in `power_field`
   quale ha risposto e in `power_unit` l'unita' (`W`, dichiarata; `unknown`
   finche' non si e' letto nulla). `platform_context` vale `gpu_bm_linux` sulla
   piattaforma che la reference C tagga per questa chiamata, `non-linux` se la
   chiamata risponde altrove, `unknown` senza GPU: dichiara che la restrizione
   "not supported on virtual machine guest" non ha morso, non prova il bare
   metal. `gfx_activity` resta diagnostica.

   **Il controllo di avanzamento e' sul timestamp.** Se primo e ultimo
   campione hanno lo stesso timestamp, il device non ha aggiornato il
   contatore: il delta non si legge come energia, si integra la potenza e la
   nota lo dice. Se il timestamp avanza e il contatore e' immobile, la finestra
   vale **zero**, ed e' un dato dichiarato, non una lettura mancante. Se il
   delta e' negativo e' un reset o un avvolgimento: **non si clampa a zero** e
   non si scrive come energia negativa, si copre la finestra con l'integrale.
   (`negative_increment` in questa codebase e' il flag di rete, non un campo
   GPU: riusarlo qui etichetterebbe la serie sbagliata.)

   Il selettore `_open_gpu_monitor()` prova NVML, poi AMD SMI, e se nessuno dei
   due risponde costruisce un errore che **nomina entrambi**: i due backend non
   girano mai in parallelo, quindi non esiste una somma. Il token del percorso
   e' il prefisso di `gpu_attribution_method`: `amdsmi-energy` (con
   `platform=...`) oppure `amdsmi-power-integral` (con `power=<campo> [W]`).
   Diciannove test (`tests/test_gpu_amdsmi.py`) con `amdsmi` finto, compresi
   risoluzione nulla, timestamp fermo, zero legittimo, delta negativo,
   assenza di timestamp, assenza di handle e la precedenza di NVML. Anche qui
   lo stato e' **[I]** con **[V] da fare**: la prova su GPU AMD reale manca e
   questa macchina non ne ha una, ma il percorso esiste nel codice e i test lo
   esercitano. **Misurato e attribuito restano
   separati**: `gpu_board_energy_j` e' la scheda intera, senza baseline idle
   calibrata `gpu_energy_attributed_j` coincide con essa
   (`gpu_idle_provenance=missing`, dichiarato in nota), e l'energia di Ollama
   sulla GPU e' solo `gpu_process_energy_j`, informativo.

Non cambiano: l'ordine della catena Windows e i clamp di
`energy/local_energy.py`, che restano una differenza dichiarata fra produzione e
v4 (AGENTS.md). Il CSV cambia solo per aggiunta in coda (punto 5). Con questa
revisione la catena Windows era ancora `EMI -> unavailable` e `MEASURED_METHODS`
senza `pawnio-counter`; il fallback PawnIO, entrato lo stesso 28/10, ha poi
portato la catena a `emi-counter` -> `pawnio-counter` -> `unavailable` e il token
in `MEASURED_METHODS` (D18, §3.1.2). La suite raccoglie **460 test: 457 passati,
3 saltati** al momento di questa revisione (429 il 27/10, dopo i primi quattro
punti; 12 nuovi il 28/10 con NVML e le tre colonne; 8 nuovi con il controllo di
timestamp e la provenienza AMD SMI); il conteggio corrente e' in AGENTS.md e a
fine lavoro e' 500.


---

## 5. Regole trasversali

1. **Nessun fallback silenzioso.** Il canale effettivo va nella riga, non solo
   nel log: `energy_calculation_method` per il package CPU
   (`energy/local_energy.py:134-148`), `package_window_source` per la finestra,
   `idle_provenance` per la baseline, `measurement_boundary` per il confine,
   `cloud_energy_method` per il server, `network_measurement_boundary` per la
   rete. Un fallback presentato come contatore e' un errore di metodo.
2. **Nessun doppio conteggio.** PKG + DRAM e PKG + PP0 + PP1 non si sommano;
   PP0/PP1 sono sottoinsiemi (`energy/emi_backend.py:28-30`). `igpu_energy_j` e
   `gpu_process_energy_j` restano informativi.
3. **Nessuno zero inventato.** La regola completa e' la 9. Il percorso della
   rete illeggibile la violava fino al 26-10-2026: il tracker restituiva gia'
   `None` con nota "energia rete = N/A" (`energy/network_energy.py:270-274`), ma
   il log della riga formattava `net_res.energy_j` con `.5f`
   (`benchmark_unified.py:1176`), che su `None` solleva `TypeError`: il blocco
   `except` (`:1179`) trasformava una richiesta riuscita in riga d'errore con
   locale e rete a `0.0` (`:1190`). Il campo `_j_log` (`:1269-1275`), gia'
   disponibile per le altre grandezze, e' ora usato anche per la rete: `None`
   arriva alla riga come `"N/A"` e la richiesta resta una riga valida.
   Il cloud non lo viola piu' (commit `027609c` del 26/10, §9 F2).
4. **Un accordo fra due lettori dello stesso contatore non e' una validazione.**
   Il criterio non guarda le librerie ne' i percorsi di codice: guarda l'elemento
   sensibile. Due letture concordano per costruzione quando derivano dallo stesso
   registro, qualunque interfaccia le esponga, e quindi concordano anche se la
   scala fosse sbagliata. Vale per qualunque coppia, non solo per la terna nota:
   EMI, LHM e SRUM leggono lo stesso `MSR_PKG_ENERGY_STATUS` (0x611)
   (`energy/emi_backend.py:7-16`); su Linux, dove powercap `energy_uj` e hwmon
   `energy*_input` derivano dagli stessi MSR di energia (§3.1, R3 e R3b: per AMD
   e' la documentazione del kernel a dichiararlo), sono la stessa lettura esposta
   due volte, non due prove; NVML potenza e NVML energia cumulativa, se derivano
   dallo stesso sensore di scheda, valgono una lettura sola. Un accordo e'
   indipendente solo se i due numeri vengono da elementi sensibili diversi, e
   finche' non esiste il wattometro la scala assoluta resta non arbitrata.
5. **"Validato" e' una parola sola.** Solo con i sei anelli di P4.9. Negli
   altri casi si scrive "funzionamento verificato" o "stima", e si dice quale
   anello manca.
6. **Nessuna percentuale di accuratezza per configurazione.** Non esiste un
   riferimento indipendente per EMI, LHM, RAPL, NVML, powermetrics, cloud o
   rete: le percentuali dei documenti esterni non si citano.
7. **Cadenza osservata, non richiesta.** LHM dichiara 0,05 s e osserva
   0,28-0,34 s; NVML richiede 0,5 s e la cadenza effettiva va verificata. La
   riga porta il valore osservato.
8. **Segmentazione al cambio di canale.** Mai concatenare backend diversi nella
   stessa finestra: si interrompe o si separa, e il cambio resta scritto.
9. **Zero legittimo contro zero da guasto.** Uno zero entra in una colonna solo
   se la riga lo **dichiara**: metodo e confine non vuoti, e una ragione che dice
   perche' quel dominio non consuma (local mode: nessuna chiamata cloud, nessun
   traffico). Un canale che non ha misurato non produce zero: produce `N/A` con
   il token di §4.1. La distinzione non si ricava dal valore — due righe con `0`
   sono identiche in coda — ma dai campi che lo accompagnano: uno zero senza
   metodo e' un guasto, non un'assenza. Oggi la regola e' violata in un punto
   (F1: la rete illeggibile scrive `0`) e resta illeggibile in un terzo (F9: lo
   zero cloud in local mode e' legittimo, il campo `cloud_energy_method` e'
   vuoto). Il secondo violatore, F2, e' chiuso in codice il 26/10 dal commit
   `027609c`: una stima assente diventa `"N/A"`, e lo `0.0` sopravvive solo
   quando e' il confine dichiarato a produrlo. Vale per ogni dominio, non solo
   per rete e cloud.
   **Un nome solo:** il codice chiama questa regola "12.1" (perche' in
   `benchmark_unified.py:502` rinvia alle regole del proprio verbale, non a
   questo documento). E' la stessa regola con due numerazioni; P5 deve allineare
   il token nel codice alla 9, perche' due tassonomie di numeri -- e non di
   contenuti -- sono il modo piu' sicuro di disubbidire a una credendo di
   obbedire all'altra.

---

## 6. Cloud: che cosa dichiara il numero

La catena cloud e' `C1 -> C2 -> C4 -> C3 -> C5 -> unavailable` (le righe e i
criteri sono in §3.4). Oggi C1 non esiste in CasualWatt: non c'e' integrazione, e
nel repository non c'e' una fonte che documenti una telemetria energetica per
richiesta di un provider. La catena effettiva e' quindi C2, con C4 non
implementato, C3 come proxy dichiarato e C5 come ultimo gradino prima di
`unavailable`, anch'esso non implementato.

Cosa **e'** `cloud_energy_j` (C2/C3/C4): una stima dell'energia del server-side
datacenter — **solo della generazione**, perche' il motore accetta numero di
token di **output** e latenza e i token di input non entrano nel calcolo
(`energy/cloud_energy.py:188-195`); `prompt_tokens` e' un argomento della
funzione e finisce in una nota dichiarativa, non nella formula
(`:138-146`, `:162-168`), mentre il conteggio resta nel campo `cloud_input_tokens`
a solo scopo dichiarativo (`:192-195`; il campo e' scritto in
`benchmark_unified.py:1121` e dichiarato in `casualwatt_csv_export.py:47`). Il
valore principale e' la **media** del
range (`_range_of`, `:94`, prelevata a `:172`), con min/max nei campi
`cloud_energy_min_j` / `cloud_energy_max_j` (`:230-238`; funzione completa
`energy/cloud_energy.py:138-254`).

La conseguenza si deve scrivere, non la si puo' inferire dal numero: una
richiesta con prompt lungo e output breve e' sottostimata, perche' il prefill e'
la parte di lavoro che il motore non vede. Piu' il prompt e' pesante rispetto
all'output, piu' la stima e' bassa; in un confronto fra righe con geometrie
diverse la differenza non e' nel modello, e' in questa definizione.

Cosa **non e'**:

- non include rete e client (sono campi separati);
- non include la quota embodied (fabbricazione hardware): e' un impatto GWP
  separato;
- non e' energia della richiesta completa: esclude i token di input, come
  dichiarato nella definizione sopra;
- la latenza passata e' end-to-end, quindi include la rete. **RETTIFICA
  26-10-2026 (Punto #119), con seconda rettifica nella stessa data:** il testo
  originale diceva che la stima server-side "ne risulta lievemente sovrastimata,
  dichiarato e non corretto". E' falso come affermazione unidirezionale:
  `request_latency` entra in EcoLogits in un solo punto (`impacts/llm.py:574`) e
  sempre attraverso `min(request_latency, gpu_latency)` (`:100-102`). La soglia del
  percorso di produzione **dipende dalla scheda**: `llm_impacts` inietta `tps` e
  `ttft` dal `deployment` del modello (`tracers/utils.py:121-122`) e quando ci sono
  la soglia e' `gpu_latency = n_out/tps + ttft` (`:97` + `:99`); quando `tps` e'
  nullo gira il ramo `latency_per_token = alpha*P_active + beta*64 + gamma`
  (`:14-16`, `:31`, ramo `:95`). Contato dalla sonda tracciata
  `probe_ecologits_gpu_steps_moe_20261026.py`: il `deployment` esiste su **tutti i
  344** modelli, ma `tps` non e' nullo su **157** -- quindi su 187 schede, fra cui
  `huggingface_hub/meta-llama/Meta-Llama-3.1-70B-Instruct`, il termine che
  confronta la nostra misura e' la regressione, e la soglia a 200 token vale
  17,4612 s. La prima stesura di questa rettifica asseriva il contrario: guardava
  la sola firma di `llm_impacts` (`tracers/utils.py:62-68`), che in effetti non
  espone `tps` fra gli argomenti, e ne concludeva che il ramo interno fosse sempre
  la regressione. La seconda stesura, correggendo la prima, scriveva "tutti i 344
  modelli hanno un `deployment`, quindi il ramo di produzione e' `1/tps`" -- e qui
  scambiava la **presenza della chiave** per la **presenza del valore**. La firma
  non e' il percorso interno, e nemmeno il metadato lo e': vanno contati i valori.
  Sopra la soglia il tempo di rete e di coda viene **scartato**, non sommato.
  Misura (`probe_ecologits_clamp_20261026.py`, output tracciato
  `experiment_results/ecologits_clamp_console_20261026.txt`, ecologits 0.11.1,
  `openai/gpt-4o-mini` con tps 33,0 e ttft 0,6): energia bit-identica da 1,57 s a
  120 s a 32 token (`3,176229044667e-06` kWh, +50,807% sul valore a 0,20 s), da
  3,70 s a 120 s a 100 token (`8,929622014584e-06` kWh, +42,881%), da 10 s a 120 s
  a 200 token (`1,739049402917e-05` kWh, +40,892%). L'incrocio e' esatto alla
  soglia, non approssimativo: a 200 token la misura di 6,6606 s -- arrotondata, e
  quindi di 6 microsecondi sotto 6,6606060606 s -- restituisce ancora
  `1,739048929432e-05`, un valore diverso dal plateau.
  Il termine e' quindi un **clamp**: nel regime lento la riga dichiara una latenza
  misurata che non ha influito sul numero, e il rischio non e' la sovrastima
  bensi' l'insensibilita' alla lentezza reale del provider. Servono
  `cloud_latency_used_s`, `cloud_latency_binding` e la soglia nella riga stessa
  (righe sotto).
- non e' una lettura del contatore del server, e non e' validata.

**I campi che rendono una stima cloud confrontabile.** Un numero prodotto da un
modello esterno e' riproducibile solo se la riga dice quale modello, con quali
input e con quale versione. I campi proposti per P5:

| campo | che cosa fissa | stato oggi |
|---|---|---|
| `ecologits_version` | la versione del motore e dei suoi fattori: le stime cambiano fra versioni, quindi due righe con versioni diverse non sono la stessa misura | precisazione 26-10-2026: il campo **esiste** a livello di run (`benchmark_unified.py:1235`, colonna `RUN_METADATA_COLUMNS` in `casualwatt_csv_export.py:305-316`) e la versione e' anche nel token `method` per riga (`energy/cloud_energy.py:239-241`); **non** e' una colonna per riga di `CSV_COLUMNS`. Lo scarto reale e' la granularita', non l'assenza. 0.11.1 installata, dichiarata a `:188`; la deriva fra release e' misurata piu' sotto (§6) |
| `cloud_calls_count` | quante chiamate HTTP compongono la riga | non contato; `llm_impacts` produce il valore per una chiamata (`completion_tokens`, `duration_s`) |
| `cloud_input_tokens_included` | `false`, finche' il motore non accetta `prompt_tokens`: rende leggibile l'esclusione senza leggere le note | il conteggio esiste (`cloud_input_tokens`) ma il flag no |
| `cloud_hardware_mismatch` | se il modello stimato (o il proxy) non e' quello richiesto | la discrepanza e' in `hw_profile` + nota (`energy/cloud_energy.py:176-181`, `:242`) |
| `cloud_quantization_assumed` | la quantizzazione che il modello di stima assume | non registrato. Il motore la fissa da sola, a `MODEL_QUANTIZATION_BITS = 16` (`impacts/llm.py:8`), e nessuno gliela chiede: la riga pubblicata quindi dichiara 16 bit **di default**, non per scelta. Non e' un dettaglio di secondo ordine perche' la memoria richiesta vale `1.2 * P_total * bit / 8` (`:120`) e da quella memoria esce il numero di GPU: su un 218B dichiarati, a 16 bit si chiedono 523,2 GB e 8 GPU, a 8 bit 261,6 GB e 4 GPU (contati dalla sonda tracciata `probe_ecologits_gpu_steps_moe_20261026.py`, sezione C). Il gradino 8 -> 4 e' il motivo per cui il numero che il documento `metodo_analitico_cloud_20261026.md` chiamava "fattore MoE 11,17" e' in realta' un confronto fra due quantizzazioni |
| `cloud_latency_used_s` | la latenza **effettivamente consumata** dal motore, cioe' `min(request_latency, n_out/lat_per_token + ttft)` -- non quella che abbiamo misurato | non registrato; senza di esso una riga puo' dichiarare 8 s di attesa mentre il numero ne usa al massimo 1,57 (32 token, `probe_ecologits_clamp_20261026.py`) |
| `cloud_latency_threshold_s` | la soglia interna del modello stimato, **con il ramo che la produce**: `n_out/tps + ttft` quando la scheda porta `tps` non nullo, la regressione `n_out * (alpha*P_active + beta*B + gamma) + ttft` quando non lo porta (`impacts/llm.py:94-97`), con `tps`/`ttft`/`alpha`/`beta`/`gamma` e la loro fonte | non registrato; senza di esso il `min` non e' verificabile da chi legge la riga. Righe omogenee non sono: `tps` e' nullo su 187 delle 344 schede del registro (contato dalla sonda `probe_ecologits_gpu_steps_moe_20261026.py`, sezione D), quindi il campo deve dire quale delle due formule ha prodotto la soglia, non solo quanto vale |
| `cloud_latency_binding` | quale dei due termini vincola: `measured` (la rete conta) o `internal-estimate` (la rete e' stata scartata) | non registrato |
| `cloud_energy_band_semantics` | cosa significa la banda min/max: `parameter_pue_ignorance_range` per EcoLogits (propagazione dei parametri registrati e delle bande PUE/WUE), `calibration-semi-range` per un fit nostro | la banda esiste (`cloud_energy_min_j`/`_max_j`) ma il suo tipo no: senza etichetta e' letta come confidenza del modello |

Sulle **chiamate multiple** (conversazione con piu' round, o un flusso
multi-agente): l'energia cloud della riga e' la **somma delle stime delle
singole chiamate**, non una stima fatta sul totale dei token e sulla latenza
complessiva. Il motivo non e' di forma: la stima e' per-chiamata con la sua
coppia `(token di output, latenza)`, e una chiamata sola con i totali darebbe
un numero diverso; il wrapper cache per `(provider, modello, tok_out,
latenza arrotondata)` (`cloud_estimator.py:192-219`), quindi una stima unica
sul totale e' un'altra chiave, non una somma. La somma di N stime per-chiamata
porta con se' N volte il confine di cui sopra (input esclusi, latenza
end-to-end) e va scritta come tale. `cloud_calls_count` esiste per rendere
visibile quante volte.

La versione dei fattori va verificata, non assunta — e il 26/10 e' stata
verificata eseguendo (`probe_ecologits_release_drift_20261026.py`, output
tracciato `experiment_results/ecologits_drift_console_20261026.txt`). Fissata la
formula -- `impacts/llm.py`, `tracers/utils.py`, `model_repository.py`,
`_ecologits.py` e `data/electricity_mixes.json` sono **byte-identici** fra
l'installazione (0.11.1) e la release 0.11.3 -- cio' che si muove sono i **dati
del registro**: 344 modelli contro 342, di cui 30 presenti solo in 0.11.1 e 28
solo in 0.11.3, e **129 dei 314 modelli comuni con contenuto diverso**. Il campo
che si muove, sul modello della sonda (`openai/gpt-4o-mini`), e' `deployment`:
`tps` passa da 33,0 a 79,0 e `ttft` da 0,6 a 0,54 s, quindi la soglia del clamp
`n_out/tps + ttft` scende da 1,5697 s a 0,9451 s. La conseguenza numerica, sulla
stessa chiamata (32 token di output, 8 s misurate, fattori di mix fissati a 1
perche' non fanno parte del confronto): da `2,646857537222e-06` kWh a
`2,240194986078e-06` kWh, rapporto **0,846360**, **-15,36%**.

Tre limiti di quel numero, da scrivere insieme al numero: e' **una** coppia di
release su **un** modello, non una legge sulla deriva; e' una differenza fra due
**dati di input del motore**, non una differenza di accuratezza rispetto a una
misura (non esiste un riferimento, §5 regola 6); e non e' simmetrica -- la stessa
release puo' spostare un altro modello nella direzione opposta, perche' il
termine che cambia e' una soglia. Cio' che si scrive per questo documento e'
quindi una sola cosa, e vale anche senza il numero: **due righe prodotte da
versioni diverse del motore non sono la stessa misura**, e il campo
`ecologits_version` esiste per non farle sommare (D12). Il 30/28 di modelli
presenti in una sola release aggiunge un secondo effetto, indipendente dalla
scala: la stessa richiesta puo' essere C2 su una versione e cadere in proxy (C3)
sull'altra, perche' il modello richiesto non e' piu' nel registro.

Il proxy C3 e' ammesso solo se dichiarato: modello di pari classe secondo il
criterio di §3.4, latenza reale, e la riga deve dire che il modello stimato non
e' quello richiesto. Oggi il token `cloud_energy_method` e' lo stesso per C2 e
C3 e il proxy vive in `hw_profile` e nelle note: e' una distinzione da rendere
esplicita in P5 (D3).

Non sono livelli della catena: la stima TDP, il modello `κ·n_in/n_out`, e il
rapporto `W_totale/η_eff`. Sono percorsi di altri progetti o proposte non
implementate; se un giorno servisse una stima dichiarata, avra' un campo e
un'etichetta propri, mai il token di un canale di misura. La forma gia' ammessa
per questo caso e' X2 (§3.1, D10): `estimate-load-tdp` in `energy_estimate_j`,
opt-in, spento di default, e mai confrontato con i numeri delle catene. **C5 non
e' quel modello**: `κ·n_in/n_out` resta escluso dalla catena, mentre C5 e' un
fit per classe con termini dichiarati, provenienza dei coefficienti e un gate di
ammissione; il fatto che usi una forma analitica non lo rende C2 ne' lo autorizza
senza il test leave-one-model-out.

**C5, `analytic-class-fit`: l'ultimo gradino e la sua provenienza (28-10-2026).**
C5 entra nella catena come fallback finale prima di `unavailable`
(`C1 -> C2 -> C4 -> C3 -> C5 -> unavailable`, §3.4 riga C5). E' una **stima**,
non una misura; il suo boundary e' "acceleratore di riferimento, serving
open-source, steady state", cioe' **non** l'hardware del provider; non e'
additiva con C2, C3 e C4 (sono gradini alternativi: la riga porta un solo
`cloud_energy_method`); e **non eredita il `min()` di C2** se non dichiarandolo
nel fit della classe -- se C5 usa la latenza lineare e C2 la tronca, lo scarto di
G3 sarebbe strutturale e non di calibrazione. Include i token di input
(`cloud_input_tokens_included = true`), che C2-C4 escludono. Lo stato e' `[P]`:
il disegno e i gate sono in `metodo_analitico_cloud_20261026.md`, e finche' il
fit per classe non passa il test leave-one-model-out la catena si ferma a
`unavailable` dopo C3.

I campi che rendono C5 confrontabile con se' stesso fra righe e classi diverse:

| campo | che cosa fissa | oggi |
|---|---|---|
| `cloud_model_class` | la classe di modello su cui il fit e' calibrato (famiglia, parametri attivi, quantizzazione): due classi diverse non sono lo stesso estimatore | non esiste; proposto per P5 |
| `cloud_reference_accelerator` | l'acceleratore su cui il fit e' calcolato (H100 nel disegno), non quello del provider | non esiste; il testo va in `cloud_measurement_boundary` |
| `cloud_serving_boundary` | lo stack di serving e il regime: open-source, steady state, batch o stream | non esiste; proposto per P5 |
| `cloud_calibration_source` | la fonte dei coefficienti con identificatore persistente (DOI/arXiv), versione del dataset e data della verifica | non esiste; proposto per P5 |
| `cloud_coefficient_provenance` | l'origine del fit: `fit-raw-holdout`, `fit-published-transcribed`, `value-adopted`, `hypothesis` | non esiste; proposto per P5 |
| `cloud_latency_used_s` | la latenza **effettivamente consumata** dal calcolo, diversa da `duration_s` quando c'e' un troncamento -- per C5 e' la scelta dichiarata nel fit | non esiste; proposto per P5 (comune a C2-C4) |
| `cloud_latency_threshold_s` | la soglia oltre la quale la latenza non entra piu', con la formula che la produce (`n_out/tps + ttft`, oppure la regressione) | non esiste; proposto per P5 (comune a C2-C4) |
| `cloud_latency_binding` | quale termine ha vincolato: `measured` o `internal-estimate` | non esiste; proposto per P5 (comune a C2-C4) |

Accanto a questi, e gia' deliberati nel disegno C5: `cloud_fit_terms` (quali
termini della forma sono attivi nella classe: `eq4` a 5 o `eq5` a 6),
`cloud_fit_loo_mape` (l'errore leave-one-model-out della classe usata) e
`cloud_energy_band_semantics = calibration-semi-range` per la sua banda. Nessuno
di questi campi e' nel codice: la riga C5 non esiste finche' non esistono loro,
perche' un numero senza classe, acceleratore, serving boundary e fonte di
calibrazione non e' riproducibile.

In **local mode** `cloud_energy_j = 0` e' legittimo (nessuna chiamata), ma oggi
il metodo e il confine cloud restano vuoti: lo zero non e' dichiarato come
"non applicabile" e va distinto da una stima fallita (F9; regola 9).

---

## 7. Rete: che cosa dichiara il numero

La catena rete e' `T1 -> T2 -> unavailable`.

Cio' che manca non e' un contatore ma un **contatore energetico** della rete: i
byte sono letti da contatori NIC reali del client, il coefficiente J/bit e'
l'ipotesi dichiarata, e il prodotto e' una **stima**, mai un M1. Scriverlo come
"nessun contatore" sarebbe falso due volte -- i contatori dei byte esistono, e
il gradino che manca e' un altro.

T1 misura i byte con i contatori NIC del client nella finestra della richiesta
e li moltiplica per il coefficiente dichiarato
(`energy/network_energy.py:261-322`). Le due meta' del prodotto hanno confini
diversi, e la discrepanza va scritta, non appianata:

- i **byte** sono quelli delle interfacce sommate, system-wide: includono il
  traffico di processi terzi, che non e' sottratto. Non sono "tutte le
  interfacce": il loopback e' sempre escluso e, per default, si sommano le
  **fisiche**, perche' sotto VPN lo stesso pacchetto compare sia
  sull'adattatore tunnel sia su quello fisico che lo trasporta cifrato e
  sommarli lo conterebbe due volte. L'eccezione e' dichiarata: quando le
  fisiche non vedono alcun byte e le virtuali si' -- tipico di un host
  Hyper-V, dove il traffico passa dallo switch virtuale -- si ricade su tutte
  le non-loopback. Il campo `network_measurement_boundary` riporta i nomi
  delle interfacce contate, cosi' una riga non e' confrontabile con un'altra
  senza sapere che cosa ha contato;
- il **coefficiente** e' un'intensita' di percorso "trasmissione + commutazione"
  verso la rete di un cloud pubblico, con la **rete di accesso esclusa dalla
  fonte** e con server, storage e processing esclusi.

Ne segue che l'energia della NIC del client e quella della rete di accesso non
sono contate da nessuno dei due lati, mentre l'energia del percorso fino agli
switch LAN del data center entra come media di percorso, non come misura del
singolo pacchetto. T2 usa i byte del payload HTTP quando i contatori non sono
utilizzabili ma i byte sono noti (`energy/network_energy.py:324-348`).

T1 e T2 hanno lo stesso coefficiente e **non** lo stesso numeratore:

| | che cosa conta | effetto |
|---|---|---|
| T1 | tutti i byte transitati sulle interfacce fisiche sommate nella finestra: header, ritrasmissioni, traffico di altre applicazioni | attribuisce alla richiesta byte che non sono suoi: sovrastima per attribuzione |
| T2 | solo i body HTTP di richiesta e risposta al socket | trascura header, TLS, framing e ritrasmissioni: sottostima per costruzione |

Per questo T1 e' il primario e T2 il fallback: il primo misura byte realmente
transitati, il secondo li ricostruisce da una parte della conversazione. Lo
scarto fra i due non si corregge con un fattore inventato; se e' grande, e' un
dato da riportare, non da normalizzare.

**Correzioni del 26-10-2026 al tracker** (tre, autorizzate come eccezione
circoscritta al blocco di P5):

1. *Selezione delle interfacce.* La vecchia somma di tutte le non-loopback
   contava due volte lo stesso pacchetto sotto VPN. Ora si sommano le fisiche,
   con la ricaduta dichiarata descritta sopra; il confine riporta i nomi
   (`energy/network_energy.py:184-214`, `:287-289`, `:312-319`). La natura
   dell'interfaccia non si legge dall'alias -- su questo host "Ethernet 2" e' un
   VirtualBox Host-Only e "(LAN)* 9" una Wi-Fi Direct -- quindi si usa la
   descrizione del driver dal registro quando c'e' (`:97-160`) e il nome come
   seconda via: il confine dice quale delle due ha deciso (`driver description,
   else name` oppure `name only`). La lista non e' esaustiva: un tunnel con nome
   e descrizione fuori elenco resta classificato come fisico e torna a contare
   due volte -- con i soli contatori di psutil non e' riconoscibile, e il confine
   elenca i nomi sommati proprio perche' il caso resti visibile. Le due letture
   degradate non diventano zeri:
   l'aggregato di ultima istanza dichiara che psutil vi include il loopback
   senza separarlo (`:197-198`), e un bordo per-interfaccia con l'altro
   aggregato attraversa due perimetri e vale `None` (`:275-284`).
2. *`None` fino alla riga.* Il log usa `_j_log` (`benchmark_unified.py:1176`),
   chiudendo F1: un contatore illeggibile non trasforma piu' una richiesta
   riuscita in riga d'errore.
3. *Delta negativo conservato.* Il valore applicato resta troncato a zero per
   continuita' con i CSV gia' scritti, ma il grezzo firmato sta in
   `upload_bytes_raw`/`download_bytes_raw`, con `negative_increment = True` e una
   nota che dice perche' (`energy/network_energy.py:292-298`). La regola del
   repository e' di non troncare: qui il troncamento resta **dichiarato**, ed e'
   la v4 a toglierlo. Resta un obbligo di P5: le due colonne (grezzo e flag)
   devono esistere nel CSV, altrimenti il troncamento torna indistinguibile da
   un traffico nullo esattamente come lo zero di F2.

Il numero e' una stima: i byte vengono da un contatore, il coefficiente e' un
valore documentato con un perimetro dichiarato. Non e' una misura diretta
dell'energia di rete e non e' validato per questa macchina.

**Che grandezza e', in termini leggibili.** `2,7e-6 J/bit` (2,7 uJ/bit) valgono
**21.600 J/GB** con GB decimale (10^9 byte), cioe' `6,0e-3 kWh/GB`; su 1,0 MB
decimale sono **21,6 J**, su 1 MiB **22,649 J**. E' aritmetica, non una misura.

**Fonte e confine, verificati il 26-10-2026.** Il valore sta in J. Baliga,
R. W. A. Ayre, K. Hinton, R. S. Tucker, "Green Cloud Computing: Balancing
Energy in Processing, Storage, and Transport", *Proc. IEEE* 99(1):149-167, 2011,
DOI 10.1109/JPROC.2010.2060451, eq. (2) a p. 7 e valore a p. 8. Il confine della
fonte e' **trasmissione e commutazione per un cloud pubblico**: metro Ethernet,
switch LAN del data center, BNG, provider edge, gateway del data center, router
di core e WDM, con ridondanza x2, raffreddamento x1.5 e utilizzazione sotto il
50% x2 (il "fattore sei"). La **rete di accesso e' esclusa esplicitamente** dalla
fonte, e cosi' server, storage e processing. E' una **stima da modello**,
costruita su datasheet dei costruttori (Tab. 4), non una misura; la fonte non
pubblica un intervallo di incertezza.

Attenzione: la citazione che il repository portava fino al 26-10-2026
(DOI 10.1109/MNET.2011.5730522) e' un altro articolo -- Hinton, Baliga, Feng,
Ayre, Tucker, *Power Consumption and Energy Efficiency in the Internet*, IEEE
Network 25(2):6-12, 2011 -- che riporta solo efficienze per apparato (circa
10 nJ/bit sul livello IP, 1-3 nJ/bit SDH, sotto 1 nJ/bit WDM) e **non contiene
2,7 uJ/bit**. Anche il confine dichiarato nel vecchio commento ("accesso, metro,
core") era l'opposto di quello della fonte.

**I numeri che sembravano un intervallo di sensibilita' sono scenari.**
`0,46 uJ/bit` e' lo scenario "cloud privato" del medesimo articolo (eq. 1, p. 7):
stessa famiglia di modello, perimetro e utilizzazione diversi. `27 uJ/bit`
(0,06 kWh/GB) e' Aslan et al. 2018, riferito al **2015**, con perimetro "core +
accesso fisso" ed esclusione di data center e dispositivi di bordo: e' una stima
ottenuta aggiornando Krug et al. 2014 su dati di rete BT nel Regno Unito. Nessuno
dei due e' un limite dello stesso estimando: i perimetri sono diversi e in
direzioni opposte (Baliga include gli switch del data center ed esclude
l'accesso; Aslan include l'accesso ed esclude il data center). `20,0 uJ/bit`,
che circolava come estremo superiore, **non ha una fonte nel repository** e non
va usato. L'intervallo `[0,46; 20,0]` uJ/bit va quindi ritirato come "intervallo
di sensibilita'": al massimo si riportano come scenari esterni etichettati, mai
come banda di incertezza del coefficiente.

Da questo segue una cosa che va detta prima di qualunque confronto: le cifre
"energia per GB di traffico" che circolano nella letteratura e nei white paper
riguardano percorsi diversi dal nostro — accesso, datacenter, talvolta la
fabbricazione — e non sono un riferimento con cui validare questo coefficiente,
ne' in un senso ne' nell'altro. Il confronto ammissibile e' solo fra righe che
dichiarano lo stesso confine.

**Che cosa resta aperto (D8).** (i) Il coefficiente e' documentato, non
validato: manca un confronto con un riferimento esterno (wattometro o presa) e
manca la prova che il percorso di questa macchina somigli a quello modellato.
(ii) La discrepanza fra byte system-wide e perimetro del coefficiente resta
dichiarata, non corretta: correggerla richiede contatori per processo o per
socket, oggi [P] (D16). (iii) Controllo empirico sull'host: A-B-A con payload
noto e poi senza trasferimento, che da' un ordine di grandezza per questa
macchina e questa rete, non un coefficiente validato, perche' il riferimento
sarebbe il contatore del package e include tutto il resto. In ogni caso la riga
porta il valore usato (`network_energy_coefficient_j_per_bit`, `config.py:363`)
e il confine applicato (`network_measurement_boundary`).

**Traffico concorrente: mitigazioni future [P], non oggi.** Oggi T1 attribuisce
alla richiesta ogni byte transitato nella sua finestra, e il rumore degli altri
processi e' dichiarato ma non sottratto. Tre vie per ridurlo (D16), tutte [P]
perche' nessuna e' verificata su questa macchina:

- *contatori per processo o per socket*, dove l'OS li espone. Su Windows gli
  extended stats TCP per PID (`GetPerTcpConnectionEStats`), su Linux le statistiche
  di cgroup o un aggancio eBPF per socket: candidati individuati per nome, da
  verificare alla fonte documentale prima di scriverli come percorso. Se anche
  funzionassero, il risultato resterebbe un'**attribuzione** con confine piu'
  stretto, non una lettura di un sensore: il livello non cambia (scala propria,
  mai M1).
- *finestra di rumore sottratta come termine dichiarato*: A-B-A con la stessa
  durata, senza richiesta, per misurare il byte-rate di fondo della macchina in
  quel momento, e sottrarre `Δbyte_fondo · coefficiente` dal numeratore. Il
  termine sottratto va scritto con il suo valore, non nascosto dentro il
  risultato; e' la stessa logica con cui la baseline idle si sottrae al package
  (P1.3), e ne eredita il vincolo: si applica la pre, non la post.
- *esecuzione isolata*: interfaccia dedicata o run con il traffico di fondo
  spento, dichiarato nel `measurement_boundary` come condizione del run. Sposta
  il problema dal calcolo alla procedura, e rende la riga non confrontabile con
  una riga in condizioni normali se il confine non lo dice.

Nessuna delle tre entra nel codice prima di P5, e nessuna autorizza a presentare
T1 come misura.

Due zeri che non vanno confusi (regola 9):

- **zero legittimo**: local mode, nessuna chiamata cloud, nessun traffico;
  oggi il campo lo dichiara con `network_measurement_boundary =
  "not-applicable (local mode)"` (`benchmark_unified.py:474`);
- **zero da guasto**: contatori NIC illeggibili. Il tracker restituisce `None`
  con nota "energia rete = N/A" (`energy/network_energy.py:270-274`) e dal
  26-10-2026 anche la riga lo riporta come `"N/A"` tramite `_j_log`
  (`benchmark_unified.py:1176`), invece di finire nel ramo `except` con `0.0`.

---

## 8. Attribuzione al processo: M3, non una misura

L'attribuzione e' una procedura separata dal canale di dominio, e non cambia
con la catena dei metodi.

**Le tre grandezze, definite.** `d_ollama` e' il delta dei secondi CPU
(`utime + stime`, cumulati) dell'**albero del motore** nella finestra — radici
per nome piu' i discendenti, incluso il runner
(`energy/energy_session.py:813-824`, `:938-939`; la lettura `utime+stime` sta in
`energy/worker_tree.py:149-176`). `d_busy`
e' il delta dei **secondi CPU busy aggregati per core** del sistema nella stessa
finestra, calcolato come `totale − idle` dalla stessa chiamata `cpu_times(percpu=True)`
(`energy/energy_session.py:781-802`): non sono secondi di tempo a muro, sono
core-secondi, e il loro tetto e' `core × Δt` — capacita' verificabile a
posteriori (`casualwatt_csv_export.py:114`). `s_cpu = d_ollama / d_busy` e'
quindi una **quota di core**, non una quota di tempo: puo' essere 0,917 anche
quando il motore occupa una frazione piccola del muro, perche' il denominatore e'
gia' una somma su tutti i core.

- **CPU.** `E_att = E_pkg - P_pre·Δt` (con segno conservato), moltiplicata per
  `s_cpu`. Il contatore conosce il package, non il processo: `s_cpu` e'
  un'assunzione dichiarata (tempo CPU come proxy dell'energia), non una lettura.
  Quando l'albero del motore cambia, `s_cpu` non e' calcolabile e la riga lo
  dichiara (P6.6).
- **GPU.** L'energia board attiva moltiplicata per la frazione di utilizzazione
  dei PID e' M3, informativa, e non sostituisce N2: la procedura e' la riga **N3**
  di §3.2 (`nvmlDeviceGetProcessUtilization`, `energy/energy_session.py:1574-1613`),
  con lo stesso statuto e lo stesso divieto. La quota di utilizzazione non e' una
  quota di energia.
- **Nessun fallback inventato.** Se l'attribuzione non e' calcolabile, il
  campo e' `N/A` con la ragione, non zero.

**Che cosa fa l'attribuzione quando arriva un carico estraneo.** Il pilota di
additivita' del 25/10 lo misura (`experiment_results/additivity_20261025_analisi.md:51-73`,
tre condizioni: A solo Ollama, B solo carico CPU, C insieme; 5 blocchi, lavoro
identico di 160 token):

| confronto | numero | che cosa dice |
|---|---|---|
| `E_worker`(C) contro `E_attiva`(A) | 196,539 J contro 232,623 J, rapporto **0,845** | con un estraneo in scena l'attribuzione perde il 15,5% dell'energia attiva, a lavoro invariato |
| `E_attiva`(C) contro `E_attiva`(A)+`E_attiva`(B) riportata a `dt_C` | rapporto **0,612** | le parti sommate sovrastimano l'insieme: l'energia non e' additiva |
| share | 0,917 → 0,832, con `d_busy` cresciuto di **+1,05 core medi** | il denominatore cresce, il numeratore sta fermo: e' il modello a quota che si comporta cosi' |
| `d_ollama` | 99,76 s → 99,28 s, `dt` 10,059 → 9,983 s | il lavoro del modello non cambia |

La lettura corretta e' quella che il modello a quota implica, non una correzione
da inventare: **`E_att`/`E_worker` e' un limite inferiore** dell'energia del
processo in presenza di carichi concorrenti, perche' ripartisce un'energia che il
contatore ha gia' prodotto in blocco, e il peso estraneo entra nel denominatore.
Per questo, quando l'oggetto e' il processo **in isolamento**, la grandezza
primaria resta `E_active` della macchina (`E_pkg − P_pre·Δt`), e la quota e' il
secondo passo, dichiarato. Non esiste un fattore di correzione: 0,845 e' la
deviazione osservata a una intensita' di disturbo precisa — circa un core
consegnato, non sei (`additivity_20261025_analisi.md:78-79`) — non una costante.

L'energia **misurata** del dominio e quella **attribuita** al processo restano
colonne e parole distinte in ogni tabella.

---

## 9. Difetti e incoerenze trovate scrivendo questa specifica

Nessuno e' corretto **da** questa specifica: il codice e' bloccato fino a P5 e
questo documento registra. La colonna **"chiuso da"** dice quale decisione di §10
li chiude -- un difetto senza destinazione diventa un elenco che nessuno ritrova.
Due eccezioni vanno scritte. **F2 e' chiuso nel codice di `HEAD`** dal commit
`027609c` del 26/10, arrivato da un'altra sessione mentre questa specifica si
scriveva. **F1 e F12 sono chiusi il 26-10-2026** da una correzione circoscritta
autorizzata dall'utente sul perimetro di rete (`_j_log` al posto di `.5f`,
selezione delle interfacce, delta firmato conservato): non e' l'apertura di P5,
sono tre difetti della stessa catena riparati dove stavano. Entrambe le
eccezioni vanno rivalidate al freeze.

| # | difetto | dove | effetto | chiuso da |
|---|---|---|---|---|
| F1 | contatori NIC illeggibili -> la riga finisce a `network_energy_j = 0` | il tracker restituisce `None` + nota "N/A" (`energy/network_energy.py:319-322`), ma il log del runner formattava con `.5f` un valore assente (-> `TypeError`), l'`except` scriveva la riga d'errore e il ramo locale usava `0.0` per rete e cloud | un guasto diventava uno zero numerico, e una richiesta riuscita diventava una riga d'errore | **CHIUSO il 26-10-2026**: il log passa da `_j_log` (`benchmark_unified.py:1343-1350`), il tracker resta intatto; `tests/test_rete_nic_confine.py` blocca sia il `None -> "N/A"` sia il testo di formattazione. Da rivalidare al freeze P5 |
| F2 | cloud non stimabile -> `cloud_energy_j = 0` mentre il metodo dice `unavailable` | era `est.energy_j or 0.0` nel runner; oggi `benchmark_unified.py:1215` passa `est.energy_j` nudo e `_finalize_energy_fields` (`:549-703`) scrive `"N/A"` | la colonna energia contraddiceva il token di metodo, e la somma end-to-end era bassa | **CHIUSO in `HEAD` dal commit `027609c`** (26/10), con `tests/test_cloud_energy_none_preservato.py` che blocca sia `None -> "N/A"` sia `0.0 -> 0.0`; da rivalidare al freeze P5 |
| F3 | GPU senza token di metodo stabile e senza baseline idle | `casualwatt_csv_export.py:63`, `:77`; `energy/local_energy.py:849-880` | GPU non confrontabile per riga; energia whole-device | D2 per il token; la baseline e' priorita' 9 di §12 e chiede hardware che questo host non ha |
| F4 | proxy cloud non distinto nel token di metodo | `energy/cloud_energy.py:304-481` | C2 e C3 hanno la stessa etichetta; il proxy e' solo nelle note | D3 |
| F5 | LHM Energy non dimostrato contatore, e assente sul host | percorso LHM rimosso il 27/10/2026 (D18, commit `3562875`); `lhm_gui_report_20261023_analisi.md:46-99` | non entrava nella catena, ma il token esisteva e la catena contava LHM come secondo percorso | **chiuso il 27-10-2026 da D18**: LHM esce dall'implementazione, il token non e' piu' un'opzione e il secondo percorso e' P1 ([P]) |
| F6 | RAPL, AMD e macOS mai esercitati | `energy/rapl_backend.py:87-158`; `energy/energy_session.py:153-164` | "implementato" non e' "provato"; 3 test saltati | non si chiude con codice (§11): D11 rende leggibile la ragione, le priorita' 7 e 10 di §12 portano l'hardware |
| F7 | coefficiente di rete: citazione sbagliata e confine invertito rispetto alla fonte | `config.py:335-372`; `energy/network_energy.py:10-29` | il valore `2,7e-6` era giusto ma attribuito a un altro articolo (IEEE Network, DOI 10.1109/MNET.2011.5730522) e descritto con l'accesso incluso, mentre la fonte lo esclude; `0,46` e `20,0` uJ/bit attribuiti ad Aslan senza fonte per `20,0` | **corretto il 26-10-2026**: fonte Proc. IEEE 99(1):149-167, DOI 10.1109/JPROC.2010.2060451; accesso escluso; `0,46` = scenario cloud privato; `20,0` senza fonte. Resta aperto il confronto empirico (D8) |
| F8 | una `CW_ENERGY_FILE` dimenticata fa misurare un file al posto del package | `energy/energy_session.py:524-554`, `:1419` | il metodo per riga e' `energy-file`, ma il run somiglia a una misura EMI finche' non si legge quella colonna | **CHIUSO il 28-10-2026 da D14**: l'etichetta resta e accanto c'e' il booleano `external_counter` (`energy/local_energy.py:153`, assegnato a `:401` da `is_external_counter`, `energy/energy_session.py:1791-1796`; colonna in coda, `casualwatt_csv_export.py:199`), cosi' un contatore esterno si esclude con un filtro e non leggendo una stringa |
| F9 | local mode: `cloud_energy_j = 0.0` senza `cloud_energy_method` ne' `cloud_estimation_boundary` | era `benchmark_unified.py:501` (commento "default rete/cloud a zero (regola 12.1)"), `:502-503` (lo zero), `:508` (il confine della **rete** c'e', quello del cloud no) | zero legittimo ma **solo a meta'**: la rete dichiara perche' non consuma, il cloud no, quindi lo zero cloud non si distingue da una stima fallita | **CHIUSO il 27-10-2026**: la riga locale scrive `cloud_energy_method = "not-applicable"` e `cloud_estimation_boundary = "not-applicable (local mode)"` accanto allo zero (`benchmark_unified.py:516-517`), mentre la riga cloud non pre-etichetta alcun metodo; `tests/test_cloud_energy_none_preservato.py` blocca entrambe le condizioni. D4 + regola 9 |
| F10 | note e docstring attribuiscono il canale EMI a "Intel", mentre il codice non filtra per produttore | era `energy/emi_backend.py:8`, `:43`, `:185-187`; `energy/energy_session.py:187-193` | su una macchina AMD la ragione di guasto direbbe "driver Intel assente" anche se il filtro non esiste; chi legge il log deduce un vincolo che il codice non impone | **CHIUSO il 27-10-2026** per il testo operativo: la ragione dice "driver del canale energia assente o non esposto" (`energy/emi_backend.py:402-407`), e la catena e' quella di `energy/energy_session.py:139-164`. Le menzioni di Intel nella docstring (`energy/emi_backend.py:7-16`) descrivono il registro e la macchina di prova, non un filtro. La verifica su AMD resta [P] |
| F11 | selezione del primo device apribile / zona `intel-rapl:0` cablata | era `energy/emi_backend.py:195-200` (Windows) e `energy/rapl_backend.py:45-48` (Linux) | su multi-die o multi-socket i canali specchiati rischiano di essere sommati o di scegliere il package sbagliato (CodeCarbon dichiara di scartare i canali specchiati sul proprio backend Windows EMI) | D15: enumerare per `name`, deduplicare, poi sommare i package distinti; ragione `ambiguous_domain` finche' non e' risolto (§4.1, riga 26). **Meta' Linux chiusa il 27-10-2026**: `energy/rapl_backend.py:128-158`, `tests/test_rapl_zone.py` (8 test, incluso il canale specchiato contato una volta). **Meta' Windows chiusa il 27-10-2026**: enumerazione di tutte le interfacce e scelta del device CPU dal metadato (`energy/emi_backend.py:226-285`), `tests/test_emi_selezione.py` (16 test: tre device, nessun CPU, due PKG distinti, PKG specchiato). Resta non implementata la **somma** dei package distinti, che e' D15 e chiede hardware multi-socket |
| F12 | sotto VPN lo stesso pacchetto contato due volte (interfaccia tunnel + fisica che lo trasporta) | era la somma di tutte le non-loopback, senza selezione | il termine di rete si gonfia di un fattore che dipende dalla configurazione, e la riga non dice quali interfacce ha sommato | **CHIUSO il 26-10-2026**: fisiche per default, virtuali e tunnel escluse, ricaduta dichiarata su tutte le non-loopback quando le fisiche vedono 0 B; il confine riporta i nomi (`energy/network_energy.py:129-265`, `:319-369`); la lettura aggregata dichiara di non separare il loopback e sorgenti miste danno `None`, non `0.0`; `tests/test_rete_nic_confine.py` blocca i casi. Il delta negativo resta troncato nel valore applicato ma e' conservato in `upload_bytes_raw`/`download_bytes_raw` con `negative_increment`; le colonne CSV sono obbligo di P5 |
| F13 | il lettore EMI non interroga versione ne' metadato: il dominio di ogni canale e' assunto dalla posizione | era `energy/emi_backend.py:73` e `:301-302` (indice 0 = pkg, sempre), `:31-37` (la conferma per nome era una sonda esterna del 24/10, su una macchina); nel file non c'era nessuna chiamata a `GET_VERSION`, `GET_METADATA_SIZE`, `GET_METADATA` | su un meter V1 (un solo canale), o con canali in ordine diverso, il valore e' plausibile ma di un dominio diverso, e la riga lo chiama comunque `emi-counter`; su V1 il guasto arriva come "IOCTL fallito" invece della ragione vera; l'unita' pWh non e' verificata prima della conversione | **CHIUSO in codice il 27-10-2026 da D17** (§3.1.1): versione, metadato, nome del canale, `ChannelCount` e unita' letti; il record si legge a 16 byte per canale, il V1 si scarta con la ragione e un canale di nome ambiguo non produce dominio (`energy/emi_backend.py:158-214`, `:476-501`, `:526-548`); `backend_version` passa a `emi-reader/2`. Aperta resta l'**evidenza** su AMD e su un V1 reale. Chiude anche la meta' "quale canale" di F11 |

---

## 10. Decisioni proposte, da congelare in P5

| id | decisione | raccomandazione |
|---|---|---|
| D1 | ~~LHM resta fallback su Windows~~ **superata da D18 (27-10-2026)** | la ragione di allora -- copre driver e permessi, non il registro -- resta vera; il ruolo di secondo percorso passa a P1, e LHM esce dall'implementazione |
| D2 | token GPU stabile | `gpu_energy_method` con `nvml-energy` / `nvml-power-integral` / `unavailable`, accanto a `gpu_idle_provenance` | precisazione 28-10-2026: il percorso e' implementato ma il campo dedicato **non esiste**; il token sta nel prefisso di `gpu_attribution_method`, che e' una stringa. Se P5 vuole il token in una colonna propria, e' una quarta aggiunta in coda |
| D3 | proxy cloud esplicito | token distinto (`ecologits-proxy`) o campo `cloud_model_proxy`; C3 non si presenta come C2 |
| D4 | canale non disponibile -> N/A | rete e cloud: `N/A` con ragione, mai `0.0`; zero solo per local mode dichiarato. Del cloud e' gia' cosi' in `HEAD` (`027609c`: `None -> "N/A"`, `0.0` sopravvive solo se lo produce il confine); la rete e' chiusa da F1 e il confine cloud della riga locale e' dichiarato dal 27-10-2026 (F9) |
| D5 | macOS | `powermetrics` come [P] progettato, non selezionabile; nessuna dichiarazione di supporto |
| D6 | NPU | disponibile solo dove esiste un dominio verificato (ANE via `powermetrics`, [P]); altrove `unavailable` e nessuna colonna finche' non esiste il backend |
| D7 | NVML total energy | **implementato il 28-10-2026**: sostituisce la potenza come canale primario; la potenza resta fallback (`nvml-energy` -> `nvml-power-integral` -> `unavailable`); la prova su GPU reale e' [V] da fare |
| D8 | coefficiente J/bit | **fonte trovata e verificata il 26-10-2026** (Baliga, Ayre, Hinton, Tucker, *Proc. IEEE* 99(1):149-167, 2011, DOI 10.1109/JPROC.2010.2060451): il coefficiente resta documentato e **non validato**, mai chiamato "misurato"; l'intervallo `[0,46; 20,0]` uJ/bit si ritira, perche' `0,46` e' lo scenario cloud privato dello stesso articolo e `20,0` non ha fonte |
| D9 | ~~LHM Energy~~ **superata da D18 (27-10-2026)** | il criterio ("entra nella catena solo se dimostrato contatore hardware") resta come condizione di una qualunque reintroduzione; con D18 LHM resta fuori a prescindere |
| D10 | stima opt-in fuori catena (X2, §3.1) | `estimate-load-tdp` in un campo proprio (`energy_estimate_j`), **spento di default**, mai in `MEASURED_METHODS`, mai confrontato con i numeri delle catene. Non e' un livello di fallback e non colma un `unavailable` |
| D11 | ragioni di G0 come token di riga | il lessico di §4.1 (`vm`, `remote_endpoint`, `permission_denied`, `driver_missing`, `no_energy_domain`, `counter_stale`, `ambiguous_domain`) prodotto da `probes/cw_probe.py` dentro la riga, non in un file a parte; il testo del motivo **non nomina il produttore** (chiude F10) |
| D12 | campi della stima cloud | `ecologits_version`, `cloud_calls_count`, `cloud_input_tokens_included`, `cloud_hardware_mismatch`, `cloud_quantization_assumed`; una riga multi-round o multi-agente e' la **somma** delle stime per-chiamata (§6) |
| D13 | confine codificato nel campo rete | `network_measurement_boundary` deve dichiarare **entrambi** i lati del prodotto: byte system-wide delle interfacce **effettivamente sommate** (per default le fisiche; virtuali e tunnel esclusi salvo la ricaduta dichiarata; loopback mai; nomi riportati nel campo) e intensita' di percorso trasmissione+commutazione con accesso escluso; cosi' una riga non e' confrontabile con cifre "per GB" che includono l'accesso o il data center (§7, D8) |
| D14 | `energy-file` rende la riga non misurata | oltre all'etichetta, un flag booleano `external_counter` per riga: un canale esterno si filtra a livello di colonna, non si riconosce leggendo una stringa (chiude F8). **Realizzata il 28-10-2026**: `energy/local_energy.py:153` (campo), `:401` (assegnazione); il predicato sta in fondo a `energy/energy_session.py` (`:1791-1796`) e la lista esterna e' dichiarata, non derivata dal testo del token; colonna accodata (`casualwatt_csv_export.py:199`) e propagata nelle righe di produzione (`benchmark_unified.py:547`, `:999-1000`, `:1176-1177`; `benchmark_v4.py:1270`, `:1309`). `True` solo per `energy-file`; `False` per EMI, PawnIO, RAPL e per le catene GPU (`nvml-*`, `amdsmi-*`), che restano interne. `tests/test_external_counter.py` (6 test) |
| D15 | package multipli e canali specchiati | enumerare le zone powercap per `name` e i device EMI per path, **deduplicare i canali specchiati**, poi sommare i package distinti; la nota sui permessi dice cosa verifica il codice (`os.access`, `energy/rapl_backend.py:148`), non "gruppo power" (chiude F11). Su Windows l'enumerazione e la deduplica sono in codice dal 27/10 (`energy/emi_backend.py:226-285`), con `ambiguous_domain` per due device PKG distinti; la **somma** dei package resta non implementata |
| D16 | traffico concorrente in finestra rete | oggi: rumore dichiarato, non sottratto. Se P5 vuole ridurlo, la via ammissibile e' la **finestra di rumore sottratta come termine scritto** (A-B-A a stessa durata, §7); i contatori per processo restano [P] finche' l'interfaccia non e' verificata alla fonte, e in ogni caso il risultato resta un'attribuzione con scala propria, mai un M1 |
| D17 | il lettore EMI **verifica** il meter invece di presumerlo, secondo il contratto Microsoft di §3.1.1 | leggere `IOCTL_EMI_GET_VERSION` e riportare la versione nella riga; leggere `GET_METADATA_SIZE` e `GET_METADATA`, verificare `MeasurementUnit == EmiMeasurementUnitPicowattHours` su ogni canale, selezionare i canali di package **per nome** (`_PKG`, uno per socket) fra i `ChannelCount` dichiarati, e trattare metadato fuori misura e risposta corta come guasto. **Non** si ammette un gate "solo V2" (un V1 si dichiara, non si rifiuta in anticipo) ne' la somma di tutti i canali con quel suffisso: la deduplica resta D15. Chiude F13 e fornisce a F11 il "quale canale". **Realizzata il 27-10-2026** in `energy/emi_backend.py`: la versione si legge sempre e il V1 si scarta **dopo** averla letta, con la ragione nelle note, non come guasto dell'IOCTL |
| D18 | LHM esce dall'implementazione e resta **metodo provato e superato**; il secondo percorso e' un lettore MSR proprio sopra PawnIO | LHM non e' un canale distinto ma lo stesso registro `0x611` gia' derivato in potenza e re-integrato da noi, con il sensore scelto per nome: fuori dalla catena, dentro il documento come evidenza (accordo a finestra uguale, A-B-A, costo di osservazione). Il sostituto P1 **e' realizzato dal 28-10-2026** (`energy/pawnio_backend.py`, token `pawnio-counter`): Intel `0x606` + `0x611`, AMD `0xC0010299` + `0xC001029B` (`msr-index.h:496-522`; **non** `0x606`/`0x611` su AMD, che e' l'errore della tabella proposta), unita' **derivata** dal registro di unita' e non copiata, solo delta di contatori cumulativi accumulati in conteggi interi, nessuna scrittura dei registri, e la dichiarazione esplicita che non e' una validazione indipendente di EMI. HVCI e firma del driver **verificate** con criteri espliciti (fail closed quando HVCI e' attivo o non determinabile; §3.1.2). Licenza PawnIO GPL-2.0 **con l'eccezione** per i moduli "that communicate with PawnIO solely through the device IO control interface"; moduli LGPL-2.1. La lettura **richiede un processo elevato** -- misurato il 28/10: con token UAC filtrato e con token SAFER, `pawnio_open` risponde `0x80070005`, e la riga lo dichiara nei `notes`. Stato: **[I] con [V]** su un host Intel; ramo AMD **[V] da fare**; riporto e reset reali non esercitati. La catena Windows e' `emi-counter` -> `pawnio-counter` -> `unavailable` |

---

## 11. Cosa questa specifica non decide

- le soglie di validazione e la campagna: sono P4.4-P4.9, congelate;
- i nomi definitivi delle colonne e il runner: sono P5, e questo documento li
  propone solo dove servono a rendere leggibile una catena;
- l'implementazione dei backend mancanti (macOS `powermetrics`, NPU) e
  l'esecuzione su hardware dei backend gia' scritti (RAPL su un host Linux, AMD
  CPU, GPU su una macchina con NVIDIA o AMD): richiede hardware e prove, non
  solo codice;
- la **banda numerica** che rende "di pari classe" due modelli per il proxy C3:
  le quattro dimensioni del criterio sono in §3.4, la soglia e' una decisione
  di P5 da congelare prima dei dati;
- se una **presa intelligente** entri o no come riferimento di sistema: W2
  descrive cosa puo' dare e cosa non chiude, la scelta dipende dal datasheet
  verificato e dal confine batteria: su un portatile la carica entra nel conteggio
  della presa, su questo host no (nessuna batteria, §3.4 W2).
- la forma di combinazione di `budget_base_w`: resta la decisione operativa
  provvisoria di P1.7, rinviata ai dati del pilota P2.9.

---

## 12. Priorita'

Tre considerazioni prima dell'elenco, perche' l'ordine non e' una classifica di
importanza: **le decisioni di P5 costano zero e non sono reversibili** dopo il
congelamento dello schema, quindi vengono prima di qualunque misura; **il
riferimento indipendente della scala assoluta ha tempi di acquisizione lunghi**
e va ordinato adesso anche se non chiude niente oggi; **le prove che chiedono
macchine che non abbiamo restano in coda e si dichiarano tali**, non si
presentano come lavoro in corso.

**A. Senza hardware (si chiudono in P5).**

1. **N/A al posto di zero** per ogni dominio (regola 9, D4): chiude F9.
   F1 (rete) e' chiusa il 26-10-2026 con `_j_log`; F2 (cloud) e' chiusa in
   `HEAD` da `027609c`. Resta il local mode, che P5 eredita.
   Un numero che dice "non misurato" non deve sembrare una misura.
2. **Token GPU** (D2) e **ritiro di LHM con `pawnio-counter`** (D18):
   decidono la confrontabilita' futura delle colonne, e dopo il congelamento non
   si cambiano. Il ritiro di LHM e' una decisione di catena, non di codice; il
   token del sostituto e' entrato il 28-10-2026 dopo le due misure (finestra
   uguale e costo di osservazione, §3.1.2).
3. **Lessico G0, package multipli e verifica del meter** (D11, D15, D17):
   D17 e' **realizzato in codice il 27/10** (selezione per metadato, canale per
   nome, scarti motivati: chiude F13 e F11 lato Windows); restano il token di
   riga (D11) e la **somma** dei package distinti (D15). Rende la riga
   leggibile su macchine diverse dalla nostra senza toccare il metodo.
4. **Flag `external_counter`** (D14): una `CW_ENERGY_FILE` dimenticata smette di
   somigliare a una misura EMI a livello di colonna, non di nota (F8).
   **Realizzato il 28-10-2026** (`energy/local_energy.py:153`, colonna in coda
   a `casualwatt_csv_export.py:199`, `tests/test_external_counter.py`).
5. **Campi cloud** (D12) e **confine nel nome del campo rete** (D13).

**B. Con hardware (in coda perche' richiedono macchine, non codice).**

6. **Riferimento di scala assoluta — da ordinare ora.** Il wattometro AC/DC e'
   l'unico percorso che chiude G4 per le catene locali: senza, nessuna riga
   scrive "validato" e la scala resta non arbitrata anche se tre lettori
   concordano (regola 4). Ha tempi di acquisizione lunghi, quindi si ordina ora
   nonostante sia l'ultimo a entrare in gioco. In attesa, la **presa intelligente
   con misura di energia** (W2) e' un riferimento provvisorio **di sistema**:
   ordine di grandezza, intercetta un errore macroscopico, non separa domini e
   non chiude G4. Su questo host il confine batteria non si pone: la macchina e'
   un GEEKOM Mini IT13 senza batteria (`BatteryFlag = 128`, `Win32_Battery` vuoto,
   verificato 26/10, §3.4 W2), quindi la presa leggerebbe l'intero assorbito a
   monte dell'alimentatore senza carica da escludere. Il P1.4 dello stato batteria
   resta congelato per le macchine che hanno una batteria.
7. **RAPL su Linux reale** (R1: enumerazione delle zone e riporto onesto scritti
   il 27/10, mai eseguiti su un host Linux; 3 test saltati piu' gli 8 di
   `tests/test_rapl_zone.py`, che girano su Windows contro un finto sysfs), **poi
   AMD** (R3, R3b: non
   implementati, da verificare alla fonte kernel) (F6).
7-bis. **Sonda del percorso MSR proprio** (P1, D18) — **eseguita il 28-10-2026**
   su un host Intel con PawnIO: confronto del delta di `0x611` con EMI nella
   stessa finestra (rapporto 1,000578 e 1,000576 su due run), costo di
   osservazione A-B-A (due run da 3 × 60 s), HVCI e firma verificate sul
   pacchetto **installato** (la documentazione non ne parla), privilegi misurati
   (richiede elevazione).
   Artefatti in `experiment_results/pawnio_probe_20261028*`. Resta **[V] da
   fare** su AMD e con riporto/reset reali; il token `pawnio-counter` e' in
   `MEASURED_METHODS` e la catena Intel e' `emi-counter` -> `pawnio-counter` ->
   `unavailable`.
8. **NVML total energy** (D7): il percorso e' nel codice dal 28-10-2026 e
   sostituisce la potenza come canale primario; resta l'esecuzione su una
   macchina con NVIDIA con gli stessi G0-G4, che e' la [V] ancora da fare (e,
   in assenza di NVIDIA, la stessa prova per AMD SMI su una scheda AMD).
9. **Baseline idle GPU** (F3): **non si puo' provare su questo host**, che non ha
   una GPU dedicata. Si fa dove esiste il dominio — un nodo noleggiato con NVML
   eseguibile (C0) o un'altra macchina — e fino ad allora ogni numero GPU resta
   whole-device e non confrontabile. Il punto non e' rimandabile: e' un vincolo
   di hardware, e come tale si dichiara.
10. **macOS `powermetrics`** solo con hardware Apple disponibile; fino ad allora
    [P] e nessuna colonna (D5, D6).
11. **Validazione del coefficiente J/bit** (D8): la fonte e' stata trovata e
    verificata il 26-10-2026, quindi il punto non e' piu' "ricerca di fonte" ma
    "confronto con un riferimento": richiede il wattometro (W1) o la presa (W2),
    oppure l'A-B-A sull'host come ordine di grandezza. Non dipende dal
    congelamento di P5, ma non si chiude con la sola citazione.

---

### Ancoraggi principali

Codice (letto il 25-26/10, righe verificate):

- `energy/energy_session.py:58-74` (canali ammessi, con la nota D18),
  `:139-164` (catena di selezione, senza filtro di produttore), `:166-193`
  (`_try_emi`), `:153-164` (ramo macOS/non supportato), `:938-939` e
  `energy/worker_tree.py:149-176` (`utime+stime` dell'albero Ollama),
  `:781-802` (`d_busy` = totale − idle per core, da una sola lettura),
  `:813-824` (ricostruzione dell'albero), `:1545-1563` (NVML potenza),
  `:1574-1613` (NVML per processo).
  **LHM non c'e' piu'** (D18, commit `3562875`): le righe citate da questa lista
  fino al 26/10 sono uscite con il blocco LHM; il fix `1422d1b` resta in git
  come storia.
- `energy/emi_backend.py:7-16` (stesso registro di LHM, nessun admin),
  `:18-43` (record per canale, unita', non additivita', mappatura per nome),
  `:95-110` (IOCTL del contratto, versioni, token di dominio),
  `:158-214` (dominio dal nome, parser del metadato V2),
  `:226-285` (`select_cpu_device` e `choose_single`: scarti motivati,
  `ambiguous_domain`), `:386-474` (`_open`: enumerazione, metadato, un solo
  device CPU), `:476-501` (`_read_metadata`), `:504-524` (`_ioctl` senza
  input), `:526-548` (buffer 16 byte per canale), `:563-575`
  (`read_cumulative_energy_j` dal canale PKG), `:591-624` (`read_domains` per
  indice di canale), `:402-407` (la ragione dell'assenza non nomina il
  produttore = F10).
- `energy/rapl_backend.py:82` (`POWERCAP_ROOT`), `:85` (prefisso
  `package-`), `:128-158` (enumerazione con deduplica dei canali specchiati),
  `:148` (il controllo e' `os.access`), `:190-198` (riporto rifiutato senza
  massimo per zona), `:302-327` (`diagnose`).
- `energy/local_energy.py:101-222` (campi per riga), `:167-168`
  (`d_ollama_cpu_s`, `d_busy_s`), `:762-928` (GPU), `:849-880` (idle GPU e
  whole-device).
- `energy/cloud_energy.py:1-81` (docstring del modulo, rettifiche del 26/10),
  `:304-312` (`prompt_tokens` fra gli argomenti),
  `:375-382` (proxy dichiarato), `:389-395` (input esclusi), `:396-413` (clamp di
  latenza, Punto #119), `:456-458` (versione EcoLogits dentro `method`), `:304-481`
  (EcoLogits, proxy, confini).
- `cloud_estimator.py:193-238` (cache per `(provider, modello, tok_out,
  latenza)`).
- `energy/network_energy.py:129-265` (loopback, marcatori di nome, descrizioni
  dei driver dal registro, scelta delle interfacce con ricaduta dichiarata),
  `:266-369` (risultato con grezzo firmato e nomi, `_read` per interfaccia,
  `measure` con guasto e sorgenti miste -> `None` e confine con i nomi; `:319-330`
  i due casi degradati; `:331-369` payload), `tests/test_rete_nic_confine.py`
  (12 test: VPN contata una volta, ricaduta dichiarata, loopback escluso,
  alias senza marcatori classificato dalla descrizione del driver, aggregato che
  dichiara di non separarlo, letture di natura diversa -> `None`, delta
  negativo conservato, `None` non formattato con `.5f`).
- `config.py:335-372` (fonte, confine e provenienza dichiarati nel commento),
  `:374-376` (valore del coefficiente).
- `benchmark_unified.py:1211-1215` (`cloud_j = est.energy_j`: il vecchio `or 0.0`
  e' rimosso dal commit `027609c`), `:549-703` (`_finalize_energy_fields`: `"N/A"`
  per componente assente, `end_to_end_energy_j = "N/A"`, nota con il nome della
  componente mancante, derivati di efficienza non calcolati su denominatore
  fittizio), `:501-508` (zero di confine in local mode, regola 12.1 -- **non**
  toccato), `:1343-1350` (`_j_log`, log N/A-aware),
  `tests/test_cloud_energy_none_preservato.py` (9 test, blocca `None -> "N/A"`
  **e** `0.0 -> 0.0`).
- `casualwatt_csv_export.py:17-193` (schema), `:44`, `:46`, `:63`, `:77`,
  `:112-114` (capacita' `d_busy_s <= core x finestra`).
- `probes/cw_probe.py` (sonda di sola lettura, **tracciata** dal commit `bb32e26`
  del 26/10: `:9` machine, `:31-58` hypervisor/WSL, `:92-126` zone powercap con
  leggibilita', `:127-162` NVML e tentativo di contatore energia, `:181-190`
  `OLLAMA_HOST`) e il suo output `probes/cw_probe_windows.json` (EMI disponibile
  con i quattro canali `RAPL_Package0_{PKG,DRAM,PP0,PP1}` senza amministratore,
  NVML assente, `hypervisor_present = true` su macchina fisica).

Dati e protocollo:

- `experiment_results/protocollo_v4_20261024.md:177-178` (P1.4: alimentatore e
  stato batteria registrati), `:2084-2128` (P4.9/P4.10), `:2414-2499` (P6.5,
  requisiti per P5).
- `experiment_results/additivity_20261025_analisi.md:51-73` (rapporti 0,845 e
  0,612, share 0,917 -> 0,832), `:78-79` (circa un core consegnato).
- `probe_ecologits_release_drift_20261026.py` (sonda di sola lettura dei dati
  EcoLogits: niente rete, niente contatori, niente chiavi) e il suo output
  `experiment_results/ecologits_drift_console_20261026.txt` -- entrambi da
  tracciare con il loro commit, perche' il numero di §6 (-15,36%) e' citato da
  questo documento e un'analisi non tracciata e' un numero che nessuno rigenera.
- `experiment_results/metodi_loc_20261025_valutazione.md` (valutazione del
  documento esterno), `experiment_results/lhm_gui_report_20261023_analisi.md:46-99`.
- `experiment_results/emi_metadato_console_20261027.txt` (cattura integrale
  della diagnostica EMI del 27-10-2026: metadato v2 di 492 byte, quattro canali
  `RAPL_Package0_{PKG,DRAM,PP0,PP1}`, canale PKG scelto per nome). La console
  era elevata e il file lo dichiara: documenta il metadato, non il privilegio.

Fonti esterne, con la data della verifica alla fonte primaria:

- CodeCarbon, spiegazione del backend RAPL/EMI (deduplica dei canali specchiati,
  `include_dram=False`): `docs.codecarbon.io/latest/explanation/rapl/`,
  verificata il 26/10.
- Kernel documentation, `amd_energy` hwmon (incremento 15,3 uJ, Family 17h/19h):
  `kernel.org/doc/html/v5.9/hwmon/amd_energy.html`, verificata il 26/10.
- Beyer & Wendler 2020 (LNCS 12079) per la non additivita' dei domini, come gia'
  citato in `energy/emi_backend.py:28-30`.
- README ufficiale del driver AMD (`github.com/amd/amd_energy`) per la
  restrizione di visibilita' degli `energy[N]_input`: la frase "To address
  CVE-2020-12912 ..." letta il 26/10. E' la fonte **del legame CVE-interfaccia**;
  il numero CVE come lato AMD di PLATYPUS (Intel = CVE-2020-8694/8695) viene da
  `kasper-oswald.de/gb/research/cves-vulnerabilities/` (fra gli autori della
  ricerca), verificato 26/10; il paper PLATYPUS (Butera, Lipp, Oswald et al.,
  USENIX Security 2021, `platypusattack.com`) e' la fonte dell'attacco.
- M. Weaver, "Reading RAPL energy measurements from Linux"
  (`web.eece.maine.edu/~vweaver/projects/rapl/`), letta il 26/10: eventi
  `power/energy-*` via `perf_event` dal kernel 3.14, con root o
  `perf_paranoid < 1`; driver AMD hwmon "senza controlli di permesso" rimosso in
  Linux 5.13 (commit `9049572fb`) "anche per ragioni di sicurezza". Fonte
  tecnica di riferimento pratico, **non** peer-reviewed: perche' il codice di
  stima di `perf` non sia una regressione serve il changelog del kernel.
- Serie di patch 2024 per gli eventi RAPL AMD: `perf jevents: Add RAPL event
  metric for AMD zen models` (LKML, 01/03/2024) e `Add per-core RAPL energy
  counter support for AMD CPUs` (LWN, 20/06/2024). Sono proposte, non una release
  verificata: per questo la riga (b) di §3.1 lascia il percorso `perf` su AMD a
  [P] con la versione non chiusa.
- Microsoft, "Energy Meter Interface" (Windows driver docs,
  `learn.microsoft.com/windows-hardware/drivers/powermeter/energy-meter-interface`,
  letta il 26/10): "Starting in Windows 10, drivers can implement the Energy
  Metering Interface (EMI)"; GUID del device interface
  **{45BD8344-7ED6-49cf-A440-C276C933B053}** definito in `emi.h`
  (`GUID_DEVICE_ENERGY_METER`), che e' il GUID usato da `energy/emi_backend.py`;
  EMI v1 su Windows 10 e v1+v2 "In Windows 10 Version 1809"; unita' da verificare
  nel metadata, `EmiMeasurementUnitPicowattHour`; `AbsoluteEnergy` "total
  accumulated energy in picowatt-hours **with some arbitrary zero-point**", da
  differenziare fra due campioni. Sono le quattro proposizioni su cui poggia E1:
  l'unita' pWh, il perche' del delta, il GUID, e il fatto che la disponibilità
  dell'interfaccia parta da Windows 10 -- **non** che su una data build esista un
  meter del package, che resta questione da sonda (stato [P] sulla riga).
  Le pagine di riferimento di `emi.h` sono state lette il **27-10-2026** e
  aggiungono quattro proposizioni, che sono gli obblighi di §3.1.1:
  `EMI_CHANNEL_V2` e' `{ MeasurementUnit, ChannelNameSize, ChannelName }` con
  nome "null-terminated, Unicode string"; `EMI_METADATA_V2` porta `ChannelCount`
  e l'array `Channels`; `EMI_MEASUREMENT_DATA_V2` prescrive che "each index in
  ChannelData must correspond to the measurement of the channel defined at the
  same index in Channels"; `IOCTL_EMI_GET_MEASUREMENT` e' documentato con "Input
  buffer: None" e con la nota che la cadenza dipende da "how often each of its
  consumers requests and also the driver implementation" -- che e' la fonte
  esterna della regola 7 (§5). Da queste pagine vengono anche le due versioni:
  V1 a un canale, V2 a canali multipli.
- Kernel, framework `powercap`
  (`docs.kernel.org/power/powercap/powercap.html`, letta il **27-10-2026**): gli
  attributi di una zona sono `energy_uj (rw)`, "Current energy counter in micro
  joules. Write '0' to reset", e `max_energy_range_uj (ro)`, "Range of the above
  energy counter in micro-joules", accanto a `max_power_range_uw`. Tre
  conseguenze. (i) L'unita' e la scala di avvolgimento sono leggibili, non
  assunte. (ii) La pagina **non documenta** la regola di avvolgimento, il ritmo di
  aggiornamento ne' i permessi: quindi la lettura di `max_energy_range_uj` fatta
  dal backend (`energy/rapl_backend.py:128-158`) e' ancorata a questa pagina, ma il
  ripiego `2**32` uJ quando l'attributo manca **e' stato ritirato** il 27/10 (la
  lettura ora e' rifiutata con "riporto non determinabile", `:190-198`): era
  un'assunzione non ancorata a niente. (iii) `energy_uj` e' scrivibile:
  **non va mai scritto**, perche' azzerarlo distrugge il delta in corso e il
  contatore cumulativo su cui poggia M1.
- Intel, *Running Average Power Limit -- Energy Reporting*
  (`intel.com/content/www/us/en/developer/articles/technical/software-security-guidance/advisory-guidance/running-average-power-limit-energy-reporting.html`,
  letta il **27-10-2026**): i registri riportano l'energia **accumulata** dei
  domini, il registro si aggiorna **circa ogni 1 ms**, il TDP dichiarato varia
  del **5-10%** fra esemplari, e applicare filtri ai campioni introduce
  "artificial unpredictable noise". Le tre frasi hanno tre effetti distinti:
  la prima e' la semantica di M1 gia' in uso; la seconda dice che a 50 ms il
  **registro non e' il limite** del nostro campionamento (coerente con la sonda:
  11 192 transizioni, nessun quantum, §3.1.1); la terza toglie alla stima da TDP
  (X2) qualunque pretesa migliore del 5-10%, e sconsiglia di filtrare i campioni
  invece di dichiarare la cadenza.
- Kernel, `arch/x86/include/asm/msr-index.h` (ramo `master`, letto il
  **27-10-2026**), `:496-522`: `MSR_RAPL_POWER_UNIT 0x00000606` e
  `MSR_PKG_ENERGY_STATUS 0x00000611` per Intel; per AMD
  `MSR_AMD_RAPL_POWER_UNIT 0xc0010299`, `MSR_AMD_CORE_ENERGY_STATUS 0xc001029a`,
  `MSR_AMD_PKG_ENERGY_STATUS 0xc001029b`. E' la fonte che **corregge** la tabella
  di sostituzione proposta per il percorso MSR: `0x606`/`0x611` sono indirizzi
  Intel, e su un Ryzen quegli indirizzi non sono l'unita' ne' il package (D18).
- AMD SMI 24.6.2.0, API di monitoraggio
  (`rocm.docs.amd.com/projects/amdsmi/en/docs-6.2.0/doxygen/docBin/html/group__gpumon.html`
  e `group__energyinfo.html`, lette il **27-10-2026**). Due gruppi che non vanno
  confusi: **GPU** -- `amdsmi_get_power_info` restituisce "the current power and
  voltage of the GPU", potenza in **W** e tensione in mV, e `amdsmi_get_clock_info`
  "averages over 1s": sono M2, non M1, e in questa pagina **non c'e' un contatore
  di energia** (vedi la correzione qui sotto, 28-10-2026); **CPU** -- il gruppo si intitola "Energy information (RAPL MSR)" e
  offre `amdsmi_get_cpu_socket_energy` e `amdsmi_get_cpu_core_energy`, che
  scrivono un `uint64_t` **senza dichiarare l'unita'**, e sono marcati
  `Platform: cpu_bm` (bare metal, non guest). A quella data la lettura era che
  per la riga 11 di §4 il canale GPU fosse di sola potenza; la verifica del 28-10
  la corregge (sotto), mentre il canale CPU resta senza unita' dichiarata: a G1
  va derivata dal registro di unita' e non copiata da una costante.
- **Correzione del 28-10-2026**. AMD SMI, Python API, versione **27.1.0**
  (`rocm.docs.amd.com/projects/amdsmi/en/latest/reference/amdsmi-py-api.html`,
  letta il **28-10-2026**). La verifica del 27-10 si era fermata al Doxygen di
  `docs-6.2.0` e concludeva che la GPU non esponeva un contatore: **non e' cosi'**.
  La pagina documenta `amdsmi_get_energy_count(processor_handle)` con i campi
  `energy_accumulator` e `counter_resolution`, e scrive la regola d'uso testuale:
  "energy_accumulator * counter_resolution = total_energy_consumption in
  micro-Joules". L'energia e' quindi **M1**, ma con due vincoli propri: e'
  accumulata "since last restart/gpu reset" (punto zero non controllabile dal
  processo) e "is not supported on virtual machine guest". La potenza resta M2:
  `amdsmi_get_power_info` espone `socket_power` ("matches current or average
  socket power"), `current_socket_power` ("Mi300+ Series Cards") e
  `average_socket_power` ("Navi + Mi 200 and earlier Series cards"), **tutti e
  tre in W**, e `amdsmi_get_gpu_activity` espone `gfx_activity` (percentuale)
  come diagnostica, non come moltiplicatore. Cio' che dipende dalla generazione
  della scheda non e' l'unita' ma **quale campo e' popolato**: il generale e'
  `socket_power`, e l'ordine di lettura lo mette per primo. La pagina elenca
  anche un campo `timestamp` senza unita'; la reference C
  (`rocm.docs.amd.com/projects/amdsmi/en/docs-6.4.1/doxygen/docBin/html/group__tagPowerQuery.html`,
  letta il **28-10-2026**) dichiara per il timestamp "Resolution: 1 ns" e tagga
  la chiamata `Platform: gpu_bm_linux`. Il Doxygen di `docs-6.2.0` della
  verifica precedente resta la ragione per cui l'unita' si **verifica a
  runtime** e non si assume: l'API rende `counter_resolution`, e se e' zero o
  assente il contatore non si usa.
- **Stato dell'arte, non fonte del metodo.** PowerJoular
  (`github.com/joular/powerjoular`, **GPL-3.0**) e la libreria che lo alimenta,
  Joular Core (`github.com/joular/joularcore`, **LGPL-3.0** secondo il metadato
  della repository, "LGPL-3.0-only" secondo l'intestazione dei file; ramo
  `develop`, commit `b9f2db0b` del 25-10-2026, letto il 27-10-2026), misurano il
  package su Windows proprio via EMI, con scelta a cascata EMI, poi PawnIO, poi
  driver di Hubblo. Si citano come stato dell'arte della strumentazione software
  e come conferma esterna che il canale EMI e' leggibile senza driver ne'
  privilegi; **non** come fonte del metodo: il contratto che questa specifica usa
  e' quello Microsoft qui sopra, e dal loro codice non si prende nulla. La loro
  nota "works only on Windows 11" non si adotta: la pagina Microsoft documenta
  l'interfaccia da Windows 10 in poi, e la riga E1 resta [P] su Windows 10
  finche' una sonda non la esercita. Le due licenze restano distinte se un giorno
  si valutasse l'uso della libreria come dipendenza. La pagina *How PowerJoular
  Works* (`joular.github.io/powerjoular/ref/how_it_works.html`, letta il
  **27-10-2026**) aggiunge quattro proposizioni utili, tre come **controesempio**
  e una come conferma: su Windows legge il package "through the Energy Meter
  Interface built into Windows 11, or through the PawnIO driver or Hubblo's
  driver, **whichever answers first**" (cascata non dichiarata nella riga: e' il
  contrario della regola 1); "On a server with several sockets, only the first
  one is read" (la scelta del primo canale e' il difetto F11, dichiarato da loro
  come limite); "RAPL counters wrap when they fill, and Joular Core corrects
  that, as long as the counter is read before it fills half of its range"
  (condizione operativa che il nostro backend Linux non dichiara, §3.1 R1); e
  divide il delta "by how long the cycle actually took, rather than assuming it
  was exactly one second", che e' la nostra finestra effettiva e non il periodo
  nominale.
- **PawnIO** (`github.com/namazso/PawnIO`, driver; `github.com/namazso/PawnIO.Modules`,
  moduli), letti il **27-10-2026**. La licenza **non e' "pulita"**, come la
  chiamava la tabella di sostituzione: il driver e' **GPL-2.0**, con
  un'eccezione scritta nel `README` che "give[s] you permission to combine PawnIO
  program with free software programs or libraries that are released under the
  GNU LGPL and with **independent modules that communicate with PawnIO solely
  through the device IO control interface**". Il nostro caso cade esattamente
  in quella classe: un client Python che apre un device e chiama
  `DeviceIoControl`, senza linkare ne' incorporare codice del driver. I moduli
  devono essere compatibili LGPL (il README "recommend[s] using the GNU Lesser
  General Public License version 2.1"), e `PawnIO.Modules` e' **LGPL-2.1**: il
  modulo `IntelMSR.p` espone `MSR_RAPL_POWER_UNIT` `0x606`, `MSR_PKG_ENERGY_STATUS`
  `0x611` (e `0x619`, `0x639`, `0x641` per DRAM/PP0/PP1), `AMDFamily17.p` espone
  `MSR_PWR_UNIT 0xC0010299`, `MSR_CORE_ENERGY_STAT 0xC001029A`,
  `MSR_PKG_ENERGY_STAT 0xC001029B`. **Il `README` non dice nulla su HVCI ne' sulla
  firma del pacchetto distribuito** (letto il 27/10; `pawnio.eu` e' una pagina di
  download): la verifica quindi non viene dalla documentazione ma dal pacchetto
  **installato**, ed e' stata fatta il 28/10 con `Get-AuthenticodeSignature` --
  HVCI `enabled`, firma `Valid`, firmatario "Microsoft Windows Hardware
  Compatibility Publisher" (§3.1.2, artefatti `pawnio_probe_20261028*.json`).
  Resta **[V] per altre release e altri host**: il criterio e' nel codice, il
  fatto misurato e' di questo pacchetto.
- **Score-P power/energy plugin** (`github.com/score-p/scorep_plugin_x86_energy`
  -- l'owner e' `score-p`, con il trattino: l'URL `github.com/scorep/...` non
  esiste, `404`; ramo `master`, push del 02-10-2025, **BSD-3-Clause**, letto il
  **27-10-2026**). E' il precedente piu' vicino al percorso MSR che D18 propone:
  "supports reading `msr` registers directly or through the `x86_adapt` library",
  su Intel Sandy Bridge e AMD Bulldozer. Tre proposizioni da prendere come
  esperienza, non come codice: i registri Intel "are updated roughly every msec",
  quindi un intervallo di 1 ms produce "highly variating power consumptions"
  mentre "a longer interval means less disturbance, a shorter interval is more
  exact" (il compromesso perturbazione/accuratezza e' nostro, §5 regola 7); il
  plugin riporta **mJ come interi**, forma di quantizzazione che noi non abbiamo
  perche' partiamo dai pWh; e la sua opzione `..._OFFSET` (default 70 W "measured
  on Taurus") esiste "because with RAPL only the energy consumption of the CPU is
  measurable" -- la conferma esterna che il confine di E1 e' il package e che
  ogni numero "di sistema" costruito da RAPL e' un'estrapolazione dichiarata,
  non una misura.
- **likwid** (`github.com/RRZE-HPC/likwid`, ramo `master`, push del 21-10-2026,
  **GPL-3.0**) e **x86_energy** (`github.com/tud-zih-energy/x86_energy`, ramo
  `master`, push del 06-12-2024, **LGPL-2.1**), letti il **27-10-2026**. Non si
  usano ne' si citano come metodo: servono a dire che la lettura diretta delle
  MSR RAPL e' pratica corrente e non un'invenzione di questa specifica, e che le
  due licenze (GPL-3.0, LGPL-2.1) sono incompatibili con un'incorporazione nel
  nostro codice, esattamente come per PowerJoular e Joular Core.
- **llm-power-profiler** (`github.com/chenxuniu/llm-power-profiler`, ramo `main`,
  push del 17-05-2026, **MIT**, letto il **27-10-2026**). Misura J/token su un
  server OpenAI-compatibile mettendosi come **proxy** davanti a `/v1/*` e
  campionando la potenza NVML: e' la versione "leggera" dello stesso obiettivo, e
  il suo ambito dichiarato dice cosa non fa -- "not request-level precise energy
  attribution", "no CPU or DRAM power telemetry", "energy" aggregata di sessione,
  risposte non-stream. Tre cose si prendono: il **proxy come punto di misura**,
  che e' la stessa scelta della riga di produzione; i token letti da `usage`
  (`prompt_tokens`, `completion_tokens`), che sono la stessa geometria N_in/N_out
  che registriamo noi; e la dichiarazione esplicita dei limiti, che e' il modello
  di come va scritta la colonna. Una non si prende: la sua energia e'
  **whole-device GPU**, quindi non e' confrontabile con una riga `emi-counter` e
  non entra in nessuna catena di §4.
- EcoLogits: la deriva fra release non viene da una fonte esterna, e' **misurata**
  (`probe_ecologits_release_drift_20261026.py` +
  `experiment_results/ecologits_drift_console_20261026.txt`), confrontando
  l'installazione 0.11.1 col wheel 0.11.3 scaricato da PyPI il 26/10. Il wheel
  non e' tracciato: chi ripete la misura lo scarica con il probe stesso
  (`pip download --no-deps ecologits==0.11.3`).

Non citate perche' **non verificate alla fonte primaria**, e ora l'elenco e' piu'
corto di ieri: resta il kernel 5.11 come release di arrivo del powercap RAPL AMD
(fonte Phoronix, non peer-reviewed, da confermare sul changelog del kernel), la
release di kernel in cui gli eventi RAPL **AMD** entrano in `perf` (nel 2024 erano
ancora serie di patch), e ogni parametro di una presa intelligente non ancora
scelta (risoluzione, finestra di media, offset a basso carico).

Sono chiuse invece, il 26/10, quattro verifiche che stavano aperte: il legame fra
CVE-2020-12912 e la restrizione hwmon (README `amd/amd_energy`, e con la
precisazione che il numero e' lato AMD, non Intel); la versione di kernel
dell'interfaccia `perf` per gli eventi `power/energy-*` (3.14, con root o
`perf_paranoid < 1`); l'entita' della deriva dei fattori EcoLogits fra 0.11.1 e
0.11.3 (-15,36% su una chiamata misurata, §6); la disponibilita' documentata
dell'interfaccia EMI a partire da Windows 10, con GUID, unita' pWh e natura
cumulativa del contatore verificati sulla pagina Microsoft (§3.1, riga E1).
