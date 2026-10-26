# Metodi per dominio e catene di fallback — specifica operativa, 2026-10-25 (rev. 27/10)

Questo documento definisce, per ogni combinazione di sistema operativo,
produttore e dominio fisico, il metodo primario, i fallback successivi,
l'etichetta che ogni livello deve portare e lo stato di evidenza al 26/10/2026.
Nasce dalla valutazione di `metodiLoc.DOCX`
(`metodi_loc_20261025_valutazione.md`) e la completa: la valutazione dice cosa
del documento esterno non si adotta, questa specifica dice cosa si usa, in che
ordine e con quale nome.

**Statuto.** E' un documento normativo per il progetto, non per il codice: P5 e'
aperto e il codice di produzione resta bloccato (AGENTS.md). Non sostituisce
P4.9 e non introduce una seconda tassonomia nel CSV: i livelli M1-M4 sono una
lente documentale, l'arbitro per riga resta il token di metodo. La parola
"validato" ha un solo significato, quello di P4.9
(`protocollo_v4_20261024.md:2084-2128`); qui si dice solo quale canale si puo'
usare e con quale etichetta.

**Data e albero delle verifiche.** Le affermazioni sul codice e sulle fonti
esterne sono verificate al 25-26/10/2026, le fonti esterne alla fonte primaria
con la data scritta accanto a ciascuna. Gli ancoraggi `file:riga` puntano
pero' all'**albero di lavoro**, non a un commit: la branca `emenda-8` porta
modifiche non committate su `energy/energy_session.py`, `energy/local_energy.py`,
`casualwatt_csv_export.py`, `AGENTS.md` e su alcuni test (848 righe aggiunte
rispetto a HEAD alla data di questa stesura). Un numero di riga citato da un
albero sporco non e' riproducibile da chi clone il repository: gli ancoraggi di
questo documento vanno ricontrollati contro il commit che P5 congela. E' un
limite dichiarato, non un risultato.

Due cose, inoltre, non sono a posto e qui si segnalano invece di aggirarsi:
`cw_probe.py`, citato in §4.1 come fonte delle ragioni di G0, **non e' tracciato**
(ne' il suo output `cw_probe_windows.json`), mentre AGENTS.md richiede che un
harness il cui esito e' citato venga committato; e lo stato dell'albero appena
descritto convive male con il congelamento del codice. Nessuna delle due si
risolve scrivendo documenti: serve una decisione esplicita.

**Fonti.** Codice in `cwEnergyModular/`; protocollo v4; gli artefatti tracciati
in `experiment_results/`; `PIATTAFORME_METODI.md` e `METODI_E_FORMULE.md` in
`Tesi-latex/qoder-bozza/` sono documenti di progetto **fuori da git**: si
citano come provenienza, non come riferimenti consultabili nel repository.
`metodiLoc.DOCX` resta uno spunto, non evidenza.

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

## 1.5 Partizione fra blocco locale e blocco remoto

**Punto #1 della definizione finale, chiuso il 2026-10-26.**

**Decisione in una riga.** I metodi si dividono per **natura della sorgente del
numero**, non per collocazione: *locale* se il numero viene da un elemento
sensibile del dominio fisico, *remoto* se viene da un modello applicato a una
grandezza non energetica letta dal client.

Il criterio non e' la geografia, e il caso che lo verifica e' C0 (§3.4 riga 589):
inferenza su nodo noleggiato con NVML eseguito **la'**. Per collocazione e'
remoto, per natura e' M1/M2 del dominio `gpu_dedicated`. **Sta nel blocco
locale**, con l'host che ha prodotto il numero scritto nella riga (`endpoint`).
§2.1 (righe 283-288) lo descriveva gia' come eccezione nominata; questa sezione
ne fa la regola, perche' la partizione non e' una sistemistica dei paragrafi:
decide quali obblighi di etichetta gravano su una colonna e quale parola si puo'
scrivere accanto al suo numero.

### Che cosa appartiene a quale blocco

| | **blocco locale** | **blocco remoto (cloud + rete)** |
|---|---|---|
| origine del numero | elemento sensibile del dominio: contatore cumulativo (M1) o integrale di potenza dello stesso dominio (M2) — righe 273-274 | grandezza non energetica letta dal client — token, byte, latenza — convertita da un modello: EcoLogits (C2/C4/C3), il fit C5, il coefficiente J/bit (T1/T2) |
| scala M1-M4 | si' | **no**, per dichiarazione gia' scritta a righe 278-281: l'unita' e' il byte o il token, non il dominio |
| token di riga | `energy_calculation_method`, `package_window_source`, `idle_provenance`, `baseline_backend` (campo di P1.3, non ancora nel codice), `measurement_boundary` | `cloud_energy_method` con i campi di provenienza di §6; `network_energy_coefficient_j_per_bit` e `network_measurement_boundary` (D13) |
| G4 | non superato **oggi**: W1 (riga 596, `[A]` in acquisto) arbitrera' la scala assoluta del sistema | **non superabile per costruzione** — vedi la prima conseguenza |
| parola ammessa | "funzionamento verificato"; "validato" solo con i sei anelli di P4.9 (`protocollo_v4_20261024.md:2084-2114`) | "stima", sempre con confine e provenienza; **"validato" mai** |
| catene | §4, righe 673-700 (`emi-counter` → `power-integration` → …, `nvml-*`, RAPL) | §6 (riga 801) e §7 (riga 949) |

### Prima conseguenza: per il blocco remoto "non validato" e' statuto, non lavoro in corso

Va scritto perche' somiglia a un deficit temporaneo e non lo e'. W1 misura il
sistema completo a monte dell'alimentatore del client (riga 596); non esiste
strumento, nella portata del progetto, che misuri l'energia del server di un
provider o il tratto di rete fra client e datacenter. Il riferimento piu' vicino
per la rete sarebbe il contatore del package, che pero' include tutto il resto
(§7). Dunque per il blocco remoto G0-G3 decidono **se** la colonna e'
utilizzabile, mentre G4 non la riguarda per definizione: nessuna riga cloud o
rete sara' mai promossa, e la priorita' 6 di §12 (acquisto di W1) cambia lo
stato del blocco locale, non quello del remoto.

Il precedente metrologico e' lo stesso del locale ed e' la ragione per cui la
parte "confronto" non sostituisce G4: regola 4 (righe 753-765) — due numeri che
derivano dalla stessa fonte concordano per costruzione. Vale per la terna EMI /
LHM / SRUM sullo stesso `MSR_PKG_ENERGY_STATUS` 0x611 e vale per C2 contro C5 se
i coefficienti del fit nascono dalle tabelle di ML.ENERGY
(`metodo_analitico_cloud_20261026.md:505-511`): sono una lettura sola.

Ne segue un obbligo di stesura: la regola 6 (riga 769, nessuna percentuale
di accuratezza per configurazione) per il blocco remoto vale a tempo
indeterminato, per il locale solo finche' non arriva W1.

### Seconda conseguenza: i blocchi restano colonne separate, e `end_to_end_energy_j` e' una somma dichiarata di nature diverse

Tre obblighi, non uno stile:

- la somma fra blocchi non e' una misura di nessun dominio; la riga la presenta
  con le sue addende nominate, perche' "somma di M1 + stima + stima" e' una
  grandezza con la terza incertezza piu' larga delle tre ma il linguaggio della
  prima (regola 2, riga 746; regola 5 di §3.0, riga 359);
- la rete **non si somma alla serie cloud in una colonna unica**
  (`metodo_analitico_cloud_20261026.md:38`): sono due confini diversi, il
  server-side datacenter e la sola NIC del client, e una colonna unica renderebbe
  non separabile un difetto di attribuzione da un difetto di scala;
- ogni colonna porta il proprio metodo e il proprio confine anche quando vale
  zero: regola 9 (righe 777-795) e il punto 5 della lista dei lavori.

### Esempio, con i numeri e il confine di ciascuno

Una riga del pilota con geometria `N_out = 32`, `OLLAMA_HOST` locale per il
package e endpoint remoto per la parte cloud:

| colonna | valore | natura | confine dichiarato |
|---|---|---|---|
| `package_energy_j` (via `E_active`) | **232,623 J** su finestra 10,059 s | M1, `emi-counter` | package Intel: include core, uncore e iGPU (PP1) |
| `cloud_energy_j` | **11,43 J** (`3,176229044667e-06` kWh) | C2, stima | server-side datacenter, sola generazione; input esclusi |
| `network_energy_j` | **0,285 J** per 1,0 MB transitati | T1, stima x coefficiente | sola NIC del client |

Il primo numero viene da `MSR_PKG_ENERGY_STATUS` letto con IOCTL (§3.1 riga 376 e
`energy/emi_backend.py:7-16`); il secondo viene da un registro di terzi, ed e'
l'uscita della sonda tracciata
(`experiment_results/ecologits_clamp_console_20261026.txt:6,14`), dove la latenza
di 1,60 s misurata produce lo stesso identico numero di 1,5697 s perche' il
`min()` del motore ha gia' clampato; il terzo e' aritmetica del coefficiente
dichiarato (`3,4e-8 J/bit`, `config.py:341`), **non una misura di questo host**:
nessun run ha misurato 1,0 MB su questa macchina, e il valore sta qui come
conversione del confine. `end_to_end_energy_j` sara' la loro somma, e la riga
dovra' dire che somma di tre nature e'.

### Controesempio: un numero che sembra conservativo e non lo e'

La riga con `request_latency = 1,60 s` dichiara un'attesa **maggiore** del punto
di plateau, e la tentazione e' leggerla come cautelativa: piu' tempo, piu'
energia. Il numero e' identico a quello di 1,5697 s (righe 14-17 della consolle)
perche' sopra la soglia il tempo misurato viene scartato, non sommato. Una stima
che scarta il dato peggiore non e' conservativa: e' **insensibile** alla lentezza
reale del provider, e il suo errore va nella direzione opposta a quella che
sembra. Per questo il punto 3 della lista porta `cloud_latency_used_s`,
`cloud_latency_threshold_s` e `cloud_latency_binding` nella riga.

### Che cosa questo punto non chiude

- la **catena** del blocco remoto e' ancora scritta in due versioni: §6 riga 801
  dice `C1 → C2 → C4 → C3 → unavailable`, `metodo_analitico_cloud_20261026.md:29`
  e la tabella di §3.4 dicono `C1 → C2 → C4 → C3 → C5 → unavailable` e il
  documento C5 dichiara di superare §6 solo per il cloud (`:12-14`). E'
  un'incoerenza fra due testi normativi dello stesso progetto, dichiarata qui e
  **non** corretta in silenzio: si allinea nel punto 2;
- i campi di provenienza cloud (punto 3), il coefficiente J/bit e il confine di
  rete (punto 4), la partizione zero/`N/A` (punto 5);
- il blocco locale: le sue catene restano quelle di §4, e i suoi nodi aperti
  (D1-D2, D7-D9, D14-D15) restano aperti — questo punto decide solo **a quale
  blocco** appartengono e quindi quale vocabolario di etichette usano.

**Ancoraggi di questa sezione.** Riferimenti di riga all'**albero di lavoro**
alle 14:58 del 26-10-2026, non a un commit, con la stessa salvaguardia
dichiarata in testa al documento (righe 21-31): il file era gia' stato modificato
da una sessione parallela nove minuti prima di questa scrittura, e i numeri
citati vanno riverificati al gate di P5.


---

## 2. Livelli di misura e controlli

### 2.1 Quattro livelli

| livello | che cos'e' | esempi | cosa dichiara |
|---|---|---|---|
| M1 | contatore cumulativo di dominio | EMI PKG, RAPL `energy_uj`, NVML total energy (non implementato) | energia del dominio fra due letture |
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
letture dello stesso registro non sono due canali **indipendenti**: EMI e LHM
sul package Intel leggono entrambi `MSR_PKG_ENERGY_STATUS` 0x611
(`energy/emi_backend.py:7-11`), quindi ai fini della validazione sono una
lettura sola. Ai fini della disponibilita' sono pero' due percorsi meccanici
distinti (IOCTL diretto contro libreria .NET e driver), e il secondo copre
guasti che il primo non copre: driver assente, permessi, formato. Si contano
due nella catena, zero nella colonna delle evidenze indipendenti.

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
| E1 | canale energia di Windows letto via IOCTL sul device enumerato per GUID `{45bd8344-...}`; record PKG in pWh (1 pWh = 3,6e-9 J), timestamp per dominio; il canale si nomina dal metadato del driver (`RAPL_Package0_PKG`), **non dal produttore** | M1 | package; non include VRM, display, alimentatore | `emi-counter` | [I][V] su i9-13900HK; [P] su AMD e su Windows 10, probe non eseguito |
| E2 | stesso canale, dominio PP1 (`RAPL_Package0_PP1`) | M1 sub-dominio | grafica integrata **su Intel**, sottoinsieme di PKG; informativo | campo `igpu_energy_j` | [I][V] a riposo |
| E3 | stesso canale, dominio DRAM (`RAPL_Package0_DRAM`) | M1, dominio distinto | memoria; **non e' un sottoinsieme di PKG**; sul host client legge spesso zero | si riporta a parte, mai somma implicita | [I][V] |
| L1 | LHM, sensore `SensorType.Energy` | M1/M2 **non determinato** | se e' un contatore hardware e' M1; se LHM lo integra e' M2 | `librehardwaremonitor-energy` | [I] codice, [A] sul host (solo batteria in LHM 0.9.6) |
| L2 | LHM, `SensorType.Power` "CPU Package" integrato | M2 | package; stessa sorgente 0x611 di E1; richiesto 0,05 s, osservato 0,28-0,34 s | `power-integration` | [I][V] |
| L3 | LHM, sensore "CPU Graphics"/"IA GPU" | M2 sub-dominio | grafica integrata; informativo | campo `igpu_energy_j` | [I], non esercitato sotto carico grafico |
| R1 | RAPL powercap, `energy_uj` + `max_energy_range_uj` | M1 | package; il package **e' uno dei zone**, non `intel-rapl:0` per definizione | `rapl` | [I], [V] da fare (nessun host Linux) |
| R2 | RAPL `psys` | M1 | **dominio piu' ampio** del package | da dichiarare come dominio proprio | [A] non implementato |
| R3 | powercap RAPL su AMD (Zen 1-3), kernel >= 5.11 | M1 candidato | package AMD; zona esposta dal driver `intel_rapl` rinominato, nomi da verificare | `rapl` solo se percorso e semantica verificati | [P] |
| R3b | hwmon `amd_energy`, `energy[N]_input` | M1 candidato | contatori per socket e per core esposti dalle MSR RAPL AMD, incremento dichiarato 15,3 uJ (kernel v5.9 doc); supporta Family 17h/19h/1Ah, quindi EPYC prima che Ryzen client | `rapl` con dominio dichiarato, o etichetta hwmon propria | [P] |
| R3c | contatori RAPL AMD via `perf` (PMU) | M2 candidato | lettura per evento, non contatore sysfs; integrazione richiesta | `power-integration` solo se verificato | [P], versione del kernel non verificata alla fonte |
| R4 | AMD SMI / AMD uProf, potenza CPU | M2 candidato | package o socket, da verificare | `power-integration` (se verificato) | [P] |
| X1 | `CW_ENERGY_FILE`, contatore joule fornito dall'utente | M1 dichiarato | dipende dal file; **priorita' di selezione** su E1 e L2, non una misura EMI | `energy-file` | [I], uso test/dev |
| X2 | stima di ultima istanza da TDP, **opt-in e spenta di default** | nessuno (non e' una misura) | campo proprio, fuori dalla catena e fuori da `energy_calculation_method`; mai a confronto con le misure | `estimate-load-tdp` (proposto, campo `energy_estimate_j`) | [P] non implementato |

Precisazioni.

- **E1.** Il device e' enumerato per GUID di interfaccia con SetupAPI, senza
  filtro di produttore: `energy_session` seleziona Windows e basta, poi chiede
  il contatore e accetta il canale **solo se la prima lettura riesce**
  (`energy/energy_session.py:188-190`, `:231-260`). Il nome "Intel" che compare
  nei commenti del backend (`energy/emi_backend.py:7-9`, `:43`, `:187`) e' una
  descrizione del machine dove e' stato provato, **non un vincolo del codice**:
  la correttezza di questa nota nel commento e' essa stessa un punto da
  verificare (F10). Il canale si identificava per nome dai metadati del driver
  (`RAPL_Package0_PKG`, `:31-35`), ed e' cosi' che va nominato anche qui. Il
  percorso prende **la prima interfaccia che si apre**
  (`energy/emi_backend.py:195-200`): su macchine con piu' package o con canali
  specchiati per die le altre sono ignorate, e CodeCarbon documenta proprio
  questo caso (canali di package separati che replicano lo stesso contatore
  socket-wide, da deduplicare; verificato il 26/10 su
  `docs.codecarbon.io/latest/explanation/rapl/`). E' il difetto F11.
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
  un'integrazione interna di LHM. **Criterio di promozione:** L1 entra nella
  catena, selezionato prima di L2, solo se sono dimostrate tutte e tre le condizioni seguenti:
  (i) il sensore compare a runtime con `SensorType.Energy`; (ii) il valore e'
  cumulativo e monotono al netto dei reset, non il `Δ/Δt` di un altro sensore:
  servono la sorgente LHM o una sonda che mostri l'accumulatore; (iii)
  unita' e dominio sono verificati a G1. Se (ii) cade, L1 non e' un canale
  distinto da L2 ma la stessa integrazione con un nome diverso, e non si conta
  due volte (§2.4). Finche' le tre condizioni non sono dimostrate, **L1 resta
  fuori dalla catena**.
- **L2.** La potenza LHM "CPU Package" e' gia' `Δ(0x611)/Δt`
  (`energy/emi_backend.py:9-11`): il nostro integrale integra una potenza gia'
  derivata, e alla derivata somma la propria cadenza. Copre il guasto del
  driver EMI e i permessi, non il guasto del registro; non e' una validazione
  di EMI. I sensori Energy-CPU di LHM richiedono token elevato:
  senza UAC la libreria si aggancia ma legge zero o `None`
  (`energy/energy_session.py:557`). Una macchina senza privilegi e senza
  driver EMI puo' quindi non avere nessun canale: e' un caso da dichiarare.
  La selezione del sensore e' per `SensorType`, non per nome: il nome da solo
  ha gia' prodotto il difetto che integrava i gradi Celsius di un sensore
  Temperature omonimo (guard a `energy/energy_session.py:656-663`).
- **R1.** Due limiti, entrambi nel codice. Il percorso e' cablato su
  `intel-rapl:0` (`energy/rapl_backend.py:45-48`): non regge su una macchina con
  piu' package, ne' su un AMD multi-die dove i canali di package separati
  replicano lo stesso contatore socket-wide. La forma corretta e' enumerare le
  zone sotto `/sys/class/powercap/`, leggere `name` per ciascuna
  (`energy/rapl_backend.py:48`, `:98-104` — il metodo esiste gia' ma non viene
  usato per selezionare), sommare **i package distinti** e deduplicare i canali
  specchiati; `cw_probe.py:92-126` lo fa gia' in sola lettura e stampa tutte le
  zone con la loro leggibilita'. Il secondo limite e' la nota del backend, che
  dice "richiede root o gruppo `power`" (`energy/rapl_backend.py:63`): il
  gruppo `power` non compare in nessuna fonte letta il 26/10, mentre il codice
  verifica solo `os.access(energy_uj, R_OK)` (`:81-83`). Si scrive **"root o
  permessi di lettura concessi esplicitamente sul nodo"**; il fallback di wrap
  `2**32` uJ quando `max_energy_range_uj` manca (`:91-96`) e' un'assunzione, non
  una misura. I tre test del backend sono saltati perche' non c'e' host Linux:
  "implementato" qui non significa "provato".
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
  prima su EPYC che su Ryzen client; e i contatori letti via `perf`, per il
  quale **non ho verificato la versione esatta del kernel** e resta una riga da
  confermare alla fonte. La restrizione dipermessi sui nodi hwmon e' reale, ma
  l'associazione con CVE-2020-12912 **non e' stata verificata**: non si scrive
  finche' non lo e'.
- **X1.** `energy-file` e' un canale dichiarato per test e integrazione. Non e'
  un fallback di produzione. La sua prevalenza su EMI e LHM non e' una
  precedenza di merito ma di selezione: se la variabile e' impostata, il codice
  legge il file e non interroga il package, quindi cio' che si misura e' il
  contatore esterno, non EMI. La riga deve dirlo
  (`energy_calculation_method = energy-file`); un contatore esterno non e' EMI.
- **X2.** Serve perche' altrimenti, dove non esiste contatore, CasualWatt non
  produce nulla: Windows 10, AMD senza canale energia, macchine virtuali, Mac
  Intel. **Non entra pero' nella catena** e non prende un token di
  `energy_calculation_method` (AGENTS.md: `MEASURED_METHODS` ammette solo canali
  di misura, `energy/energy_session.py:64-65`). Le condizioni sono quelle gia'
  scritte nella valutazione che questa specifica completa: campo proprio
  (`energy_estimate_j`), etichetta propria (`estimate-load-tdp`), **spento di
  default** e acceso solo per opt-in esplicito, mai a confronto con una misura e
  mai nella stessa colonna di una misura. Se un giorno si implementa, il database
  dei TDP viene da CodeCarbon (MIT), che e' un modello, non un contatore: la riga
  resta una stima. E' la decisione D10.

### 3.2 GPU e NPU

**Confine, in testa.** Nessun canale di questa tabella misura "Ollama sulla
GPU". N1, N2, A1 e I1 sono **whole-device**: energia dell'intera scheda nella
finestra, qualunque processo la usi, comprese le altre applicazioni e il
desktop. N3 e `gpu_process_energy_j` sono **attribuzione**: ripartiscono
l'energia whole-device secondo una quota di utilizzazione, e restano
informativi. Le due grandezze non si confrontano e non si sommano; una riga che
porta energia GPU deve dire quale delle due sta scrivendo
(`gpu_energy_attributed_j` contro `gpu_process_energy_j`).

| id | interfaccia e unita' | livello | confine | etichetta | stato |
|---|---|---|---|---|---|
| N1 | NVML `nvmlDeviceGetTotalEnergyConsumption`, mJ | M1 candidato | whole-device | `nvml-energy` (proposto) | [A] non implementato |
| N2 | NVML `nvmlDeviceGetPowerUsage`, mW, integrata | M2 | whole-device; sampling richiesto 0,5 s, cadenza effettiva NVML da verificare | `power-integration` (GPU) | [I], [V] da fare (nessuna GPU sul host) |
| N3 | NVML `nvmlDeviceGetProcessUtilization`, ms di GPU per PID | M3 | attribuzione, non misura | campo `gpu_process_energy_j` | [I] informativo |
| A1 | AMD SMI, energia o potenza GPU | M1/M2 candidato | whole-device | `power-integration` (se verificato) | [P] |
| I1 | dGPU Intel: nessun backend | M4 | whole-device | `unavailable` | [A] |
| PP1 | EMI PP1 / LHM "CPU Graphics" | M1/M2 sub-dominio | iGPU **dentro** PKG | campo informativo | [I][V] |
| NPU | nessuna interfaccia verificata su Windows/Linux | M4 | integrata: dentro PKG; discreta: nessun backend | `unavailable` | [A] |
| ANE | `powermetrics` su Apple Silicon | M2 candidato (M1 se il valore e' cumulativo) | unita' neurale Apple; dominio, unita' e copertura da verificare | `powermetrics` (proposto) | [P] |

Precisazioni.

- **N2 e' whole-device.** `idle_gpu_power_w` e' letto ma non assegnato da
  nessun percorso di produzione: `gpu_idle_provenance` e' `missing` per
  costruzione e `gpu_energy_attributed_j` e' l'energia dell'**intera scheda**
  nella finestra (`energy/local_energy.py:525-535`). Non e' la stessa
  grandezza di `ollama_active_energy_j`.
- **N1, se implementato, sostituisce N2 come canale primario.** Nella catena
  diventa il primo livello e N2 scende a fallback: un contatore non ha bisogno
  di integrazione e non soffre della cadenza, ma resta da verificare che il
  driver lo esponga e con quale dominio. Finche' non c'e', N2 e' l'unico
  canale GPU NVIDIA.
- **N3 e' M3: ripartizione proporzionale.** Ripartisce l'energia board attiva
  tra i PID secondo la frazione di utilizzazione GPU
  (`energy/energy_session.py:2515-2540`): e' un modello, etichettato
  informativo, non una lettura per processo. La quota di utilizzazione non e'
  una quota di energia, e il risultato non si presenta come misurata.
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
(`energy/energy_session.py:206-212`). La catena progettata e'
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
| T1 | delta contatori NIC del client x coefficiente J/bit | stima, scala propria | solo NIC client; non router intermedi ne' NIC del datacenter | campo `network_*` | [I] non validato |
| T2 | byte del payload HTTP x coefficiente J/bit | stima, scala propria | solo body richiesta+risposta al socket del client | campo `network_*` | [I] |
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
  pari classe. Quindi la catena effettiva e' C2 -> C4 -> C3 -> `unavailable`:
  il proxy e' l'ultimo ricorso, non la scorciatoia. Vale anche qui il divieto
  di cui a §6: nessuna stima fuori da EcoLogits.
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
  restano un obbligo di verifica, non un numero. Sul host corrente il vincolo si applica:
  la macchina e' un portatile e P1.4 congela "alimentatore collegato [...] stato
  batteria registrato" (`experiment_results/protocollo_v4_20261024.md:177-178`),
  quindi la presa misurerebbe anche l'eventuale carica. Una presa su un desktop
  senza batteria da' un riferimento di sistema piu' pulito, ma resta senza
  separazione di dominio.
- Il coefficiente `3,4e-8 J/bit` (`config.py:333-343`) e' un'ipotesi
  dichiarata, non un valore misurato ne' validato: il commento del codice lo
  dice esplicitamente ("fonte bibliografica specifica non ancora fissata"). Il
  piano per identificarlo e' in §7.

---

## 4. Catene per configurazione

La catena si legge da sinistra a destra; la prima che passa G0-G3 vince. La
colonna "oggi" dice cosa fa il codice al 26/10, non cosa dovrebbe fare.

| # | configurazione / dominio | catena | etichette | oggi |
|---|---|---|---|---|
| 1 | Windows Intel, `cpu_package` | EMI PKG -> LHM power -> `unavailable` | `emi-counter` -> `power-integration` -> `unavailable` | EMI attivo; LHM saltato quando EMI funziona |
| 2 | Windows Intel con LHM Energy dimostrato contatore (criterio di promozione in §3.1) | EMI PKG -> LHM Energy -> LHM power -> `unavailable` | `emi-counter` -> `librehardwaremonitor-energy` -> `power-integration` -> `unavailable` | L1 non dimostrato: la catena effettiva e' la 1 |
| 3 | Windows AMD, `cpu_package` | EMI **se il probe passa** -> LHM power (Package/Package Power/CPU PPT) -> `unavailable` | `emi-counter` -> `power-integration` -> `unavailable` | il codice non filtra per produttore (`energy/energy_session.py:188-190`): la catena e' la 1, ma su AMD non e' mai stata provata, quindi lo stato e' [P]; con piu' die vale la deduplica di F11 |
| 4 | Qualsiasi OS, `CW_ENERGY_FILE` impostato | `energy-file` -> (catena normale se non impostato) | `energy-file` | priorita' di selezione su EMI/LHM; uso test/dev |
| 5 | Linux Intel, `cpu_package` | RAPL package -> `unavailable` | `rapl` -> `unavailable` | implementato, mai esercitato; 3 test saltati |
| 6 | Linux Intel, `psys` | RAPL psys -> `unavailable` | `rapl` con dominio `psys` | non implementato; non e' un fallback di 5 |
| 7 | Linux AMD, `cpu_package` | powercap RAPL AMD (kernel >= 5.11, se il percorso e la semantica sono verificati) -> hwmon `amd_energy` -> `unavailable` | `rapl` (dominio dichiarato) -> `unavailable` | non implementato; R3b ha scala propria (15,3 uJ) e copre prima EPYC che Ryzen client |
| 8 | macOS Intel o Apple Silicon, CPU/GPU/ANE | `powermetrics` -> `unavailable` | `powermetrics` -> `unavailable` | `unavailable`; powermetrics progettato |
| 9 | macOS laptop, sistema | delta batteria (limite di sistema) -> `unavailable` | `battery-delta` -> `unavailable` | non implementato |
| 10 | NVIDIA, `gpu_dedicated` | NVML total energy (quando implementato) -> NVML power -> `unavailable` | `nvml-energy` -> `power-integration` -> `unavailable` | solo potenza; idle mai calibrato -> whole-device |
| 11 | AMD, `gpu_dedicated` | AMD SMI energia/potenza (se verificato) -> `unavailable` | `power-integration` -> `unavailable` | non implementato |
| 12 | Intel dGPU | `unavailable` | `unavailable` | nessun backend |
| 13 | iGPU Intel/AMD | nessun termine separato (dentro PKG); PP1/Graphics informativi | campi `igpu_*` | PP1 letto da EMI; mai sommato |
| 14 | NPU Windows/Linux | `unavailable` | `unavailable` | nessun backend, nessuna colonna |
| 15 | NPU Apple Silicon (ANE) | `powermetrics` ANE (se verificato) -> `unavailable` | `powermetrics` -> `unavailable` | progettato, non implementato |
| 16 | Cloud | telemetria provider -> EcoLogits registrato -> `compute_llm_impacts` con parametri reali -> EcoLogits proxy -> `unavailable` | `provider-telemetry` -> `ecologits` -> `ecologits` (C4, con fonte dei parametri) -> `ecologits` (proxy; D3 propone `ecologits-proxy`) -> `unavailable` | EcoLogits + proxy; mai TDP, mai stima fuori EcoLogits |
| 16b | Inferenza su GPU noleggiata con codice eseguibile sul nodo | NVML sul nodo remoto (C0) -> `unavailable` | `nvml-energy` / `power-integration` con `endpoint` del nodo | non integrato nel percorso client: [P] |
| 17 | Rete | delta NIC -> contabilita' payload -> `unavailable` | campo `network_*` | delta NIC; se illeggibile restituisce 0 (difetto F1) |
| 18 | Sistema completo | wattometro (riferimento); in attesa, presa intelligente come riferimento provvisorio d'ordine di grandezza | `wall` / `smart-plug` (mai in una catena di dominio) | non disponibile nessuno dei due |
| 19 | Qualsiasi altra combinazione | `unavailable` | `unavailable` | caso residuo dichiarato, non aggirato |
| 20 | Macchina virtuale (hypervisor), `cpu_package` | nessun contatore di dominio -> `unavailable` con ragione `vm` | `unavailable` | `cw_probe.py:31-58` rileva hypervisor flag, `systemd-detect-virt`, DMI; il contatore del guest non e' quello del package fisico |
| 21 | WSL2, `cpu_package` | contatore non esposto al guest -> `unavailable` con ragione `vm` (WSL2 e' una VM) | `unavailable` | il probe distingue `microsoft` nel release (`cw_probe.py:41`) |
| 22 | Container (Docker) su host con contatore | RAPL/EMI **dell'host**, se il mount lo consente -> `unavailable` con ragione `permission_denied` | `rapl` / `emi-counter` con confine "host, non container" | l'energia letta e' dell'host condiviso: attribuirla al container e' M3, non M1 |
| 23 | Windows ARM, `cpu_package` | nessun canale verificato -> `unavailable` con ragione `driver_missing` | `unavailable` | EMI e LHM non verificati su ARM; `cw_probe.py` segna il machine (`platform.machine()`) |
| 24 | Linux ARM / SBC, `cpu_package` | nessun contatore di dominio verificato -> `unavailable` con ragione `no_energy_domain` | `unavailable` | mai provato su hardware ARM: e' un'assenza **dichiarata**, non una dimostrazione; se un SBC espone powercap o hwmon, la riga 5 o la 7 si applicano |
| 25 | `OLLAMA_HOST` non locale, `cpu_package` | **la misura locale non rappresenta l'inferenza**: `unavailable` con ragione `remote_endpoint`, piu' la riga cloud del server remoto | `unavailable` + campi cloud | il probe legge `OLLAMA_HOST` (`cw_probe.py:181`); senza questo flag la riga sembrerebbe locale |
| 26 | Piu' package/socket | enumerare le zone per `name`, sommare i package distinti, deduplicare i canali specchiati -> `unavailable` | `rapl` / `emi-counter` con dominio `package-0..N` | oggi il codice prende `intel-rapl:0` o il primo device EMI (F11) |

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
| `permission_denied` | il nodo esiste ma non e' leggibile dal processo | root, regola udev, o UAC per i sensori LHM |
| `driver_missing` | il driver del canale non e' installato o non e' esposto | installare il canale, o passare al fallback |
| `no_energy_domain` | la piattaforma non espone un dominio energia | `unavailable` strutturale, non un guasto |
| `counter_stale` | timestamp di dominio fermo (G2) | segmentare o dichiarare, mai sottrarre |
| `ambiguous_domain` | package multipli o canali specchiati non risolti | enumerare e deduplicare (F11) prima di sommare |

La sonda che raccoglie queste evidenze esiste gia' ed e' di sola lettura:
`cw_probe.py` rileva hypervisor e WSL (`:31-58`), elenca le zone powercap con
la loro leggibilita' (`:92-126`), conta i device NVML e prova il contatore di
energia (`:127-162`), legge `OLLAMA_HOST` (`:181-190`) e distingue `machine`
(`:9`). Serve che il suo esito diventi un token della riga, non un file a parte
(D11).

---

## 5. Regole trasversali

1. **Nessun fallback silenzioso.** Il canale effettivo va nella riga, non solo
   nel log: `energy_calculation_method` per il package CPU
   (`energy/local_energy.py:122-132`), `package_window_source` per la finestra,
   `idle_provenance` per la baseline, `measurement_boundary` per il confine,
   `cloud_energy_method` per il server, `network_measurement_boundary` per la
   rete. Un fallback presentato come contatore e' un errore di metodo.
2. **Nessun doppio conteggio.** PKG + DRAM e PKG + PP0 + PP1 non si sommano;
   PP0/PP1 sono sottoinsiemi (`energy/emi_backend.py:28-30`). `igpu_energy_j` e
   `gpu_process_energy_j` restano informativi.
3. **Nessuno zero inventato.** La regola completa e' la 9; qui resta solo
   l'elenco dei due percorsi che oggi la violano: rete illeggibile e cloud non
   stimabile restituiscono `0` al posto di `N/A` (§9, F1 e F2).
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
   metodo e' un guasto, non un'assenza. Oggi la regola e' violata in due punti
   (F1, F2) e resa illeggibile in un terzo (F9: lo zero e' legittimo, il metodo
   e' vuoto). Vale per ogni dominio, non solo per rete e cloud.

---

## 6. Cloud: che cosa dichiara il numero

La catena cloud e' `C1 -> C2 -> C4 -> C3 -> unavailable` (le righe e i criteri
sono in §3.4). Oggi C1 non esiste in CasualWatt: non c'e' integrazione, e nel
repository non c'e' una fonte che documenti una telemetria energetica per
richiesta di un provider. La catena effettiva e' quindi C2, con C4 non
implementato e C3 come proxy dichiarato.

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
  percorso di produzione e' `gpu_latency = n_out/tps + ttft` (`:97` + `:99`),
  perche' `llm_impacts` inietta `tps` e `ttft` dalla scheda del modello
  (`tracers/utils.py:121-122`) e **tutti i 344 modelli del registro hanno un
  `deployment`**; la regressione `n_out * (alpha*P_active + beta*64 + gamma)`
  (`:14-16`, `:31`, ramo `:95`) e' quella usata **solo quando `tps is None`** e qui
  non compare mai. La prima stesura di questa rettifica asseriva il contrario:
  guardava la sola firma di `llm_impacts` (`tracers/utils.py:62-68`), che in effetti
  non espone `tps` fra gli argomenti, e ne concludeva che il ramo interno fosse
  sempre la regressione. La firma non e' il percorso interno, e la conclusione era
  sbagliata.
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
| `ecologits_version` | la versione del motore e dei suoi fattori: le stime cambiano fra versioni, quindi due righe con versioni diverse non sono la stessa misura | **precisazione 26-10-2026: il campo ESISTE a livello di run (`benchmark_unified.py:1235`, colonna `RUN_METADATA_COLUMNS` in `casualwatt_csv_export.py:305-316`) e la versione e' anche nel token `method` per riga (`energy/cloud_energy.py:239-241`); **non** e' una colonna per riga di `CSV_COLUMNS`. Lo scarto reale e' la granularita', non l'assenza. 0.11.1 installata, dichiarata a `:188` |
| `cloud_calls_count` | quante chiamate HTTP compongono la riga | non contato; `llm_impacts` produce il valore per una chiamata (`completion_tokens`, `duration_s`) |
| `cloud_input_tokens_included` | `false`, finche' il motore non accetta `prompt_tokens`: rende leggibile l'esclusione senza leggere le note | il conteggio esiste (`cloud_input_tokens`) ma il flag no |
| `cloud_hardware_mismatch` | se il modello stimato (o il proxy) non e' quello richiesto | la discrepanza e' in `hw_profile` + nota (`energy/cloud_energy.py:176-181`, `:242`) |
| `cloud_quantization_assumed` | la quantizzazione che il modello di stima assume | non registrato |
| `cloud_latency_used_s` | la latenza **effettivamente consumata** dal motore, cioe' `min(request_latency, n_out/tps + ttft)` -- non quella che abbiamo misurato | non registrato; senza di esso una riga puo' dichiarare 8 s di attesa mentre il numero ne usa al massimo 1,57 (32 token, `probe_ecologits_clamp_20261026.py`) |
| `cloud_latency_threshold_s` | la soglia `n_out/tps + ttft` del modello stimato, con `tps`/`ttft` della scheda EcoLogits e la loro fonte | non registrato; senza di esso il `min` non e' verificabile da chi legge la riga |
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

La versione dei fattori va verificata, non assunta: le tabelle EcoLogits si
muovono fra release e l'entita' del movimento non e' stata controllata alla
fonte, quindi qui non si scrive nessun fattore di scala. Cio' che si scrive e'
che due righe prodotte da versioni diverse del motore non si confrontano, e il
campo esiste per farle distinguere (D12).

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
opt-in, spento di default, e mai confrontato con i numeri delle catene.

In **local mode** `cloud_energy_j = 0` e' legittimo (nessuna chiamata), ma oggi
il metodo e il confine cloud restano vuoti: lo zero non e' dichiarato come
"non applicabile" e va distinto da una stima fallita (F9; regola 9).

---

## 7. Rete: che cosa dichiara il numero

La catena rete e' `T1 -> T2 -> unavailable`.

T1 misura i byte con i contatori NIC del client nella finestra della richiesta
e li converte in joule con il coefficiente dichiarato
(`energy/network_energy.py:63-90`). Il confine e' **solo la NIC del client**:
non i router intermedi, non la NIC del datacenter, non il core di rete. Il
traffico degli altri processi nella stessa finestra e' rumore dichiarato, non
sottratto. T1 somma tutte le interfacce non-loopback
(`energy/network_energy.py:46-55`): con una VPN lo stesso pacchetto puo'
comparire sia sull'interfaccia virtuale sia su quella fisica, e in quel caso va
contato una volta sola oppure l'interfaccia va scelta esplicitamente. T2 usa i
byte del payload HTTP quando i contatori non sono utilizzabili ma i byte sono
noti (`:93-107`).

T1 e T2 hanno lo stesso coefficiente e **non** lo stesso numeratore:

| | che cosa conta | effetto |
|---|---|---|
| T1 | tutti i byte transitati sulle interfacce del client nella finestra: header, ritrasmissioni, traffico di altre applicazioni | attribuisce alla richiesta byte che non sono suoi: sovrastima per attribuzione |
| T2 | solo i body HTTP di richiesta e risposta al socket | trascura header, TLS, framing e ritrasmissioni: sottostima per costruzione |

Per questo T1 e' il primario e T2 il fallback: il primo misura byte realmente
transitati, il secondo li ricostruisce da una parte della conversazione. Lo
scarto fra i due non si corregge con un fattore inventato; se e' grande, e' un
dato da riportare, non da normalizzare.

Il numero e' una stima: i byte sono misurati, il coefficiente e' un'ipotesi.
Non e' una misura diretta dell'energia di rete, e non e' validato.

**Che grandezza e', in termini leggibili.** `3,4e-8 J/bit` valgono **272 J/GB**
con GB decimale (10^9 byte), cioe' `7,6e-5 kWh/GB`: e' l'aritmetica del valore
dichiarato, e il commento del codice porta la stessa conversione arrotondata
("~270 J/GB ~ 7,6e-5 kWh/GB", `config.py:333-341`). Il confine e' scritto nello
stesso commento: **solo la NIC del client**, "NON l'intero accesso FTTx o il core
di rete" (`config.py:334-337`).
Da questo segue una cosa che va detta prima di qualunque confronto: le cifre
"energia per GB di traffico" che circolano nella letteratura e nei white paper
riguardano percorsi diversi dal nostro — accesso, datacenter, talvolta la
fabbricazione — e non sono un riferimento con cui validare questo coefficiente,
ne' in un senso ne' nell'altro. Il confronto ammissibile e' solo fra righe che
dichiarano lo stesso confine.

**Piano per il coefficiente.** (i) Cercare la fonte primaria di `3,4e-8 J/bit`
— studio o documento che lo misuri con un confine compatibile con la sola NIC
del client — e citarla con la data della verifica; (ii) se la fonte non esiste,
il coefficiente resta un'ipotesi dichiarata e si presenta come tale, mai come
"misurato" (D8); (iii) controllo empirico sull'host: A-B-A con payload noto e
poi senza trasferimento, che da' un ordine di grandezza per questa macchina e
questa rete, non un coefficiente validato, perche' il riferimento sarebbe il
contatore del package e include tutto il resto. In ogni caso la riga porta il
valore usato (`network_energy_coefficient_j_per_bit`, `config.py:341`).

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
- **zero da guasto**: contatori NIC illeggibili. Oggi il codice scrive
  "energia rete = 0 (dichiarato)" (`energy/network_energy.py:73`): e' un
  numero al posto di un'assenza, e va corretto in P5 (D4).

---

## 8. Attribuzione al processo: M3, non una misura

L'attribuzione e' una procedura separata dal canale di dominio, e non cambia
con la catena dei metodi.

**Le tre grandezze, definite.** `d_ollama` e' il delta dei secondi CPU
(`utime + stime`, cumulati) dell'**albero del motore** nella finestra — radici
per nome piu' i discendenti, incluso il runner
(`energy/energy_session.py:1687`, `:1779-1790`). `d_busy`
e' il delta dei **secondi CPU busy aggregati per core** del sistema nella stessa
finestra, calcolato come `totale − idle` dalla stessa chiamata `cpu_times(percpu=True)`
(`energy/energy_session.py:1747-1769`): non sono secondi di tempo a muro, sono
core-secondi, e il loro tetto e' `core × Δt` — capacita' verificabile a
posteriori (`casualwatt_csv_export.py:110-111`). `s_cpu = d_ollama / d_busy` e'
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
  di §3.2 (`nvmlDeviceGetProcessUtilization`, `energy/energy_session.py:2515-2540`),
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

Nessuno e' corretto qui: il codice e' bloccato fino a P5. Sono registrati
perche' P5 li chiuda o li dichiari, e la colonna **"chiuso da"** dice quale
decisione di §10 li chiude — un difetto senza destinazione diventa un elenco che
nessuno ritrova.

| # | difetto | dove | effetto | chiuso da |
|---|---|---|---|---|
| F1 | contatori NIC illeggibili -> `network_energy_j = 0` | `energy/network_energy.py:73` | un guasto diventa uno zero numerico; la nota lo dice, la colonna no | D4 + regola 9 |
| F2 | cloud non stimabile -> `cloud_energy_j = 0` mentre il metodo dice `unavailable` | `benchmark_unified.py:1101` (`est.energy_j or 0.0`) | la colonna energia contraddice il token di metodo | D4 + regola 9 |
| F3 | GPU senza token di metodo stabile e senza baseline idle | `casualwatt_csv_export.py:63`, `:77`; `energy/local_energy.py:525-535` | GPU non confrontabile per riga; energia whole-device | D2 per il token; la baseline e' priorita' 9 di §12 e chiede hardware che questo host non ha |
| F4 | proxy cloud non distinto nel token di metodo | `energy/cloud_energy.py:138-254` | C2 e C3 hanno la stessa etichetta; il proxy e' solo nelle note | D3 |
| F5 | LHM Energy non dimostrato contatore, e assente sul host | `energy/energy_session.py:770-830`; `lhm_gui_report_20261023_analisi.md:46-99` | non entra nella catena (corretto), ma il token esiste | D9 + criterio di promozione L1 (§3.1) |
| F6 | RAPL, AMD e macOS mai esercitati | `energy/rapl_backend.py:45-48`; `energy/energy_session.py:206-212` | "implementato" non e' "provato"; 3 test saltati | non si chiude con codice (§11): D11 rende leggibile la ragione, le priorita' 7 e 10 di §12 portano l'hardware |
| F7 | coefficiente di rete senza fonte primaria | `config.py:333-343` | numero pubblicabile solo come ipotesi dichiarata | D8 + piano di §7 |
| F8 | una `CW_ENERGY_FILE` dimenticata fa misurare un file al posto del package | `energy/energy_session.py:182-197`, `:1419` | il metodo per riga e' `energy-file`, ma il run somiglia a una misura EMI finche' non si legge quella colonna | D14: etichetta **e** un flag booleano `external_counter` sulla riga, perche' un'etichetta testuale non e' un filtro |
| F9 | local mode: `cloud_energy_j = 0` con metodo e confine vuoti | `benchmark_unified.py:466-476` | zero legittimo ma non dichiarato: non si distingue da una stima fallita | D4 + regola 9 |
| F10 | note e docstring attribuiscono il canale EMI a "Intel", mentre il codice non filtra per produttore | `energy/emi_backend.py:8`, `:43`, `:185-187`; `energy/energy_session.py:188-190` | su una macchina AMD la ragione di guasto direbbe "driver Intel assente" anche se il filtro non esiste; chi legge il log deduce un vincolo che il codice non impone | D11: il testo del motivo diventa indipendente dal produttore, e la verifica su AMD resta [P] |
| F11 | selezione del primo device apribile / zona `intel-rapl:0` cablata | `energy/emi_backend.py:195-200`; `energy/rapl_backend.py:45-48` | su multi-die o multi-socket i canali specchiati rischiano di essere sommati o di scegliere il package sbagliato (CodeCarbon dichiara di scartare i canali specchiati sul proprio backend Windows EMI) | D15: enumerare per `name`, deduplicare, poi sommare i package distinti; ragione `ambiguous_domain` finche' non e' risolto (§4.1, riga 26) |

---

## 10. Decisioni proposte, da congelare in P5

| id | decisione | raccomandazione |
|---|---|---|
| D1 | LHM resta fallback su Windows | **si'**, non come validazione: copre driver/permessi, non il registro; etichetta `power-integration` |
| D2 | token GPU stabile | `gpu_energy_method` con `nvml-energy` / `nvml-power-integration` / `unavailable`, accanto a `gpu_idle_provenance` |
| D3 | proxy cloud esplicito | token distinto (`ecologits-proxy`) o campo `cloud_model_proxy`; C3 non si presenta come C2 |
| D4 | canale non disponibile -> N/A | rete e cloud: `N/A` con ragione, mai `0.0`; zero solo per local mode dichiarato |
| D5 | macOS | `powermetrics` come [P] progettato, non selezionabile; nessuna dichiarazione di supporto |
| D6 | NPU | disponibile solo dove esiste un dominio verificato (ANE via `powermetrics`, [P]); altrove `unavailable` e nessuna colonna finche' non esiste il backend |
| D7 | NVML total energy | quando implementato, **sostituisce la potenza come canale primario**; la potenza resta fallback |
| D8 | coefficiente J/bit | trovare la fonte primaria o declassarlo a ipotesi dichiarata; non chiamarlo "misurato" |
| D9 | LHM Energy | entra nella catena solo se dimostrato contatore hardware; altrimenti resta fuori |
| D10 | stima opt-in fuori catena (X2, §3.1) | `estimate-load-tdp` in un campo proprio (`energy_estimate_j`), **spento di default**, mai in `MEASURED_METHODS`, mai confrontato con i numeri delle catene. Non e' un livello di fallback e non colma un `unavailable` |
| D11 | ragioni di G0 come token di riga | il lessico di §4.1 (`vm`, `remote_endpoint`, `permission_denied`, `driver_missing`, `no_energy_domain`, `counter_stale`, `ambiguous_domain`) prodotto da `cw_probe.py` dentro la riga, non in un file a parte; il testo del motivo **non nomina il produttore** (chiude F10) |
| D12 | campi della stima cloud | `ecologits_version`, `cloud_calls_count`, `cloud_input_tokens_included`, `cloud_hardware_mismatch`, `cloud_quantization_assumed`; una riga multi-round o multi-agente e' la **somma** delle stime per-chiamata (§6) |
| D13 | confine codificato nel nome del campo rete | il coefficiente e il boundary token devono dire **client-NIC** (`network_energy_coefficient_j_per_bit` + `network_measurement_boundary`), cosi' una riga non e' confrontabile con cifre "per GB" di percorso completo (§7, D8) |
| D14 | `energy-file` rende la riga non misurata | oltre all'etichetta, un flag booleano `external_counter` per riga: un canale esterno si filtra a livello di colonna, non si riconosce leggendo una stringa (chiude F8) |
| D15 | package multipli e canali specchiati | enumerare le zone powercap per `name` e i device EMI per path, **deduplicare i canali specchiati**, poi sommare i package distinti; la nota sui permessi dice cosa verifica il codice (`os.access`, `energy/rapl_backend.py:81-83`), non "gruppo power" (chiude F11) |
| D16 | traffico concorrente in finestra rete | oggi: rumore dichiarato, non sottratto. Se P5 vuole ridurlo, la via ammissibile e' la **finestra di rumore sottratta come termine scritto** (A-B-A a stessa durata, §7); i contatori per processo restano [P] finche' l'interfaccia non e' verificata alla fonte, e in ogni caso il risultato resta un'attribuzione con scala propria, mai un M1 |

---

## 11. Cosa questa specifica non decide

- le soglie di validazione e la campagna: sono P4.4-P4.9, congelate;
- i nomi definitivi delle colonne e il runner: sono P5, e questo documento li
  propone solo dove servono a rendere leggibile una catena;
- l'implementazione dei backend mancanti (RAPL reale, AMD, macOS, NVML energy):
  richiede hardware e prove, non solo codice;
- la **banda numerica** che rende "di pari classe" due modelli per il proxy C3:
  le quattro dimensioni del criterio sono in §3.4, la soglia e' una decisione
  di P5 da congelare prima dei dati;
- se una **presa intelligente** entri o no come riferimento di sistema: W2
  descrive cosa puo' dare e cosa non chiude, la scelta dipende dal datasheet
  verificato e dal fatto che su un portatile la batteria e' dentro il confine;
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

1. **N/A al posto di zero** per ogni dominio (regola 9, D4): chiude F1, F2, F9.
   Un numero che dice "non misurato" non deve sembrare una misura.
2. **Token GPU** (D2) e **criterio di promozione L1** (§3.1, D9): decidono la
   confrontabilita' futura delle colonne, e dopo il congelamento non si cambiano.
3. **Lessico G0 e package multipli** (D11, D15): chiude F10 e F11, e rende la
   riga leggibile su macchine diverse dalla nostra senza toccare il metodo.
4. **Flag `external_counter`** (D14): una `CW_ENERGY_FILE` dimenticata smette di
   somigliare a una misura EMI a livello di colonna, non di nota (F8).
5. **Campi cloud** (D12) e **confine nel nome del campo rete** (D13).

**B. Con hardware (in coda perche' richiedono macchine, non codice).**

6. **Riferimento di scala assoluta — da ordinare ora.** Il wattometro AC/DC e'
   l'unico percorso che chiude G4 per le catene locali: senza, nessuna riga
   scrive "validato" e la scala resta non arbitrata anche se tre lettori
   concordano (regola 4). Ha tempi di acquisizione lunghi, quindi si ordina ora
   nonostante sia l'ultimo a entrare in gioco. In attesa, la **presa intelligente
   con misura di energia** (W2) e' un riferimento provvisorio **di sistema**:
   ordine di grandezza, intercetta un errore macroscopico, non separa domini e
   non chiude G4; e su questo host, che e' un portatile con P1.4 che congela lo
   stato batteria, include anche l'eventuale carica.
7. **RAPL su Linux reale** (R1: il percorso Intel e' scritto, cablato su
   `intel-rapl:0`, e mai eseguito; 3 test saltati), **poi AMD** (R3, R3b: non
   implementati, da verificare alla fonte kernel) (F6).
8. **NVML total energy** come M1 che sostituisce la potenza come canale primario
   (D7), con gli stessi G0-G4, su una macchina con NVIDIA.
9. **Baseline idle GPU** (F3): **non si puo' provare su questo host**, che non ha
   una GPU dedicata. Si fa dove esiste il dominio — un nodo noleggiato con NVML
   eseguibile (C0) o un'altra macchina — e fino ad allora ogni numero GPU resta
   whole-device e non confrontabile. Il punto non e' rimandabile: e' un vincolo
   di hardware, e come tale si dichiara.
10. **macOS `powermetrics`** solo con hardware Apple disponibile; fino ad allora
    [P] e nessuna colonna (D5, D6).
11. **Fonte del coefficiente J/bit** o sua declassificazione esplicita (D8): e'
    ricerca di fonte, non misura, e non dipende da hardware.

---

### Ancoraggi principali

Codice (letto il 25-26/10, righe verificate):

- `energy/energy_session.py:64-65` (canali ammessi), `:188-190` (selezione EMI
  senza filtro di produttore), `:231-260` (`_try_emi`), `:206-212` (macOS),
  `:870-871` (nomi sensori LHM), `:656-663` (guard SensorType), `:1687`
  (`utime+stime` albero), `:1747-1769` (`d_busy` = totale − idle, per core),
  `:1779-1790` (ricostruzione dell'albero), `:2490` (NVML potenza),
  `:2515-2540` (NVML per processo).
- `energy/emi_backend.py:7-16` (stesso registro di LHM, nessun admin),
  `:18-23` (domini), `:28-30` (non additivita'), `:185-187` (nota "driver
  canale energia Intel" = F10), `:195-200` (primo device apribile = F11).
- `energy/rapl_backend.py:45-48` (percorso `intel-rapl:0`), `:81-83`
  (il controllo e' `os.access`), `:91-96` (`2**32` come fallback di scala),
  `:120-134` (wrap).
- `energy/local_energy.py:122-132` (campi per riga), `:152-156`
  (`d_ollama_cpu_s`, `d_busy_s`), `:503-590` (GPU), `:525-535` (idle GPU e
  whole-device).
- `energy/cloud_energy.py:1-52`, `:138-146` (`prompt_tokens` fra gli argomenti),
  `:176-181` (proxy dichiarato), `:188-195` (input esclusi), `:196-219` (clamp di
  latenza, Punto #119), `:239-241` (versione EcoLogits dentro `method`), `:138-254`
  (EcoLogits, proxy, confini).
- `cloud_estimator.py:192-219` (cache per `(provider, modello, tok_out,
  latenza)`).
- `energy/network_energy.py:44-55` (somma delle interfacce non-loopback),
  `:63-90` (delta NIC), `:73` (guasto -> 0), `:93-107` (payload).
- `config.py:333-341` (confine e conversione dichiarati nel commento), `:341`
  (valore del coefficiente).
- `benchmark_unified.py:1141-1145` (`cloud_j = est.energy_j`: il vecchio `or 0.0`
  e' rimosso dal commit `027609c`), `:500-634` (`_finalize_energy_fields`: `"N/A"`
  per componente assente, `end_to_end_energy_j = "N/A"`, nota con il nome della
  componente mancante, derivati di efficienza non calcolati su denominatore
  fittizio), `:467-474` (zero di confine in local mode, regola 12.1 -- **non**
  toccato), `:1269-1277` (`_j_log`, log N/A-aware),
  `tests/test_cloud_energy_none_preservato.py` (9 test, blocca `None -> "N/A"`
  **e** `0.0 -> 0.0`).
- `casualwatt_csv_export.py:17-108` (schema), `:44`, `:46`, `:63`, `:77`,
  `:110-111` (capacita' `d_busy_s <= core x finestra`).
- `cw_probe.py` (sonda di sola lettura, **non tracciata in git**: `:9` machine,
  `:31-58` hypervisor/WSL, `:92-126` zone powercap con leggibilita',
  `:127-162` NVML e tentativo di contatore energia, `:181-190` `OLLAMA_HOST`).

Dati e protocollo:

- `experiment_results/protocollo_v4_20261024.md:177-178` (P1.4: alimentatore e
  stato batteria registrati), `:2084-2128` (P4.9/P4.10), `:2414-2499` (P6.5,
  requisiti per P5).
- `experiment_results/additivity_20261025_analisi.md:51-73` (rapporti 0,845 e
  0,612, share 0,917 -> 0,832), `:78-79` (circa un core consegnato).
- `experiment_results/metodi_loc_20261025_valutazione.md` (valutazione del
  documento esterno), `experiment_results/lhm_gui_report_20261023_analisi.md:46-99`.

Fonti esterne, con la data della verifica alla fonte primaria:

- CodeCarbon, spiegazione del backend RAPL/EMI (deduplica dei canali specchiati,
  `include_dram=False`): `docs.codecarbon.io/latest/explanation/rapl/`,
  verificata il 26/10.
- Kernel documentation, `amd_energy` hwmon (incremento 15,3 uJ, Family 17h/19h):
  `kernel.org/doc/html/v5.9/hwmon/amd_energy.html`, verificata il 26/10.
- Beyer & Wendler 2020 (LNCS 12079) per la non additivita' dei domini, come gia'
  citato in `energy/emi_backend.py:28-30`.

Non citate perche' **non verificate alla fonte primaria**: il collegamento fra
`perf`/AMD e una specifica versione di kernel, il legame con CVE-2020-12912, e
qualsiasi fattore di scala fra release di EcoLogits. Restano verifiche obbligate
prima di entrare in una riga.
