# Strumenti esterni a confronto, e cosa se ne ricava per CasualWatt

**Data**: 2026-10-23, ~17:10
**Cosa ho letto**: i README grezzi via HTTPS (`raw.githubusercontent.com`), i
metadati via API GitHub (stelle, licenza SPDX, ultimo push, archiviazione), e i
**nostri** dati per le prove crociate (report GUI e trace EMI gia' committati).
Niente di quanto segue e' ricavato a memoria.

**Criterio di valutazione** che ho applicato: uno strumento esterno serve se
(1) **misura** e non stima, (2) documenta unita' e limiti, (3) e' riusabile
legalmente, (4) ci da' un **arbitro** o un'idea esportabile. Dove manca (4) il
progetto va in related work, non nel codice.

## 1. Tabella di stato (metadati verificati oggi)

| progetto | che cosa fa davvero | piattaforma | licenza | ultimo push | per noi |
|---|---|---|---|---|---|
| `sosy-lab/cpu-energy-meter` (CEM) | lettore RAPL in C, output in **joule** per dominio | **Linux only** | BSD-3-Clause | 2026-05-26 (348 *) | **arbitro lato Linux + bibliografia** |
| `powerapi-ng/pyJoules` | libreria Python per energia di snippet di codice | **solo GNU/Linux** (dichiarato) | MIT | 2025-12-29 (95 *) | **corrobora il nostro limite di finestra** |
| `Accenture/energy-consumption-measuring-toolkit` | demo + whitepaper su RAPL/pyJoules, baseline subtraction | non dichiarato (dipende da pyJoules) | **nessun file LICENSE** (API: `license=None`; `LICENSE` grezzo → 404) | 2024-05-02 (7 *) | **metodo si', codice no** |
| `AIWattch/AI-Wattch` | estensione browser che **stima** l'impatto dei prompt su ChatGPT/Claude/Gemini | Chrome MV3 / Firefox | MIT | 2026-10-14 (19 *) | **contrasto: il polo dell'estima** |
| `mlco2/impact` | calcolatore di emissioni ML (potenza misurata **o** stimata) + template LaTeX | CLI/web, HTML/JS | MIT | 2026-10-09 (272 *) | **layer emissioni + formato di reporting** |

## 2. cpu-energy-meter: il pezzo piu' spendibile

Verificato dal README (`cem.md`, righe citate):

- `:21-22` "CPU Energy Meter is a **Linux tool** that allows to monitor power
  consumption of Intel CPUs **at fine time granularities (few tens of
  milliseconds)**" → **non e' un backend Windows** e non puo' sostituire
  LHM/EMI qui; e pero' il nostro standard di risoluzione: poche decine di ms
  contro i 0,28 s del nostro thread. Il gap non e' del sensore, e' del nostro
  percorso: loro leggono l'accumulatore, noi integriamo una rate.
- `:23-30` i domini: package, core, uncore, **memory node ("server CPUs
  only")**, e **platform/PSYS** definito come "all devices in the platform that
  receive power from integrated power delivery mechanism, e.g. processor cores,
  SOC, memory, add-on or peripheral devices".
- `:35-37` "uses the maximal possible measurement interval (depending on the
  hardware this is between a few minutes and an hour), it causes negligible
  overhead" → progetto opposto al nostro, e coerente col perche' noi soffriamo:
  su Windows con LHM l'accumulatore non c'e' (vedi §7 e il report GUI), quindi
  paghiamo l'integrazione.
- `:39` fork di **Intel Power Gadget** → la catena della related work e' pulita:
  Intel Power Gadget → CEM → (noi) HWiNFO/LHM/EMI su Windows.
- `:69-79` si' esegue **senza root** con gruppo `msr`, regola udev e
  `setcap cap_sys_rawio=ep` → la nostra piaga "i sensori Power di LHM sono
  invisibili senza Admin" su Linux non esiste, ed e' un argomento in piu' per il
  dual-boot.
- `:107-115` uscita raw `-r`: `cpu0_package_joules=4.971924`,
  `cpu0_psys_joules=38.904785` → **gia' parseabile**: perfetto per un confronto
  automatico a finestra identica contro il nostro CSV.
- `:121-123` paper: **Beyer & Wendler, "CPU Energy Meter: A Tool for
  Energy-Aware Algorithms Engineering", TACAS 2020, LNCS 12079, pp. 126-133,
  DOI 10.1007/978-3-030-45237-7_8** (open access) → voce bibliografica pronta,
  con metodo descritto in letteratura (raro per questi tool).

**Azione**: entra nella `VALIDAZIONE_LINUX_RAPL_CHECKLIST.md` come **secondo
lettore** (dopo `turbostat`), con l'output `-r` da allineare alle nostre
finestre A-B-A, e con **PSYS** fra le colonne da raccogliere.

## 3. pyJoules: il nostro limite di finestra e' un limite noto in letteratura

Dal README (`pyjoules.md`):

- "### Windows and MacOS — **Only GNU/Linux support is available for the
  moment.** We are working on Mac support" → candidato solo per il lato Linux.
- "### Measurement frequency — ... you can't use Pyjoule to measure energy
  consumption **during a period shorter than the device energy measurement
  frequency**. Pyjoule will return null values if the measurement period is too
  short." → **conferma esterna, dalla stessa famiglia di strumenti, della regola
  che abbiamo derivato da soli**: il vincolo non e' nostro, e' del contatore, e
  sotto la granularita' del dispositivo la risposta giusta e' "nessun valore",
  non un numero interpolato. Va citato nel paragrafo "Risoluzione del
  campionamento".
- "### Known issues — RAPL energy counters **overflow after several minutes or
  hours**, potentially causing false-negative energy readings" (con correzione
  tramite `max_energy_range_uj`) → la classe di difetto che avevamo sospettato
  sul wrap del contatore. Per noi: EMI espone valori a 64 bit in pWh, quindi il
  wrap cadrebbe fra ~600 anni a 35 W (non ci riguarda); LHM invece legge il
  registro a 32 bit e usa la sottrazione `unchecked(uint - uint)`
  (`IntelCpu.cs:696`), che gestisce il wrap per definizione — e' il motivo per
  cui i nostri differenziali non hanno mai mostrato falsi negativi.

## 4. Accenture toolkit: metodo si', codice no

Sette stelle, **nessuna licenza dichiarata** (API `license=None`, `LICENSE`
grezzo → 404) e ultimo push maggio 2024: **non ne riusiamo codice**. Resta un
valore documentale, perche' il README enuncia due regole che noi abbiamo
stabilito sperimentalmente e che quindi non sono nostre idiosincrasie:

- "For absolute numbers, **subtract the baseline consumption measurement** from
  the overall consumption measured when running the application" → e' il nostro
  A-B-A, con in piu' la consapevolezza che il livello assoluto a riposo va
  misurato e non assunto.
- "the last step is to **omit the sleep time** of a multithreaded application,
  or the delay time captured in an application ... We leverage the
  `EnergyContext` package to add 'breakpoint' ... `start_tag` parameter ...
  Energy calculation using tagging omits the sleep time set in between the two
  functions" → e' la nostra finestra ancorata ai token emessi invece che al
  wall-clock.
- Idea esportabile: il **pattern `EnergyContext(start_tag/end_tag)`**, cioe'
  l'attribuzione per **annotazione della regione di codice**, che e'
  complementare alla nostra attribuzione per cpu-time-share. Un context manager
  opzionale nel profiler (misura questa regione) sarebbe un'estensione naturale
  del capitolo "estendibilita' del metodo", senza toccare il backend.
  **Chiarimento (23/10, da `ricerca_metodo.DOCX`)**: il pattern non va usato per la
  metrica J/token, che resta per **richiesta e fase**. La granularita' per funzione
  e' incompatibile con la nostra risoluzione (intervallo PI misurato 0,31-0,34 s in
  fase load contro richieste da 3,60 s, di cui il prefill e' una frazione di
  secondo): li' il numero sarebbe costruito, non misurato. Il context manager resta
  un'ipotesi di estendibilita' per codice non-LLM, da citare come tale.

## 5. AI-Wattch: il polo opposto del nostro posizionamento

Estensione browser (TypeScript, MIT, attiva: push 14/10/2026) che **non tocca
l'hardware**: "captures lightweight telemetry (timestamps, token counts, model
selection) - never full chat text", due stimatori (token-based sui caratteri,
time-based dai timestamp request/response) combinati in un "hybrid estimate"
con metadati di quantizzazione e TDP GPU, e fattori regionali PUE/intensita' di
rete ("One Token Model" di Antarctica). Il README dichiara **nessuna
validazione contro strumenti fisici**.

Perche' ci serve: perche' e' esattamente il tipo di numero che la nostra tesi
contesta — J/token **stimati** da telemetria client per servizi chiusi, senza
arbitrato metrologico. Due usi: (a) in related work come polo dell'estima, con
la nostra misura come polo opposto; (b) come **baseline di confronto
dichiaratamente non valida**: se uno dei loro stimatori per un prompt da ~1300
token cade a 5-10 W, il nostro 1,29 J/token misurato diventa un termine di
 paragone utile. Non prendiamo nulla di tecnico.

## 6. mlco2/impact: il layer emissioni e il formato di reporting

**Emendato il 23/10 ~17:50**, dopo verifica su `html/_compute.html` del repo (il README sono
42 righe e non contiene alcuna tassonomia measured/estimated: la frase qui sotto nella prima
versione era un'over-reading, vedi `ricerca_metodo_docx_valutazione_20261023.md` §4).

Calcolatore di emissioni ML (MIT, 272 *, attivo, "passively maintained"): i campi esposti sono
**Hardware type** (select di GPU), **Hours Used**, **Provider**, **Region of Compute** piu' due
campi custom `Carbon Efficiency (kg/kWh)`; la formula dichiarata dalla pagina e' "**Power
consumption x Time x Carbon Produced Based on the Local Power Grid**" (`_compute.html:204-205`).

Due claim della prima versione di questa sezione **vanno ritrattati**:
(a) "**accetta potenza misurata o stimata**" — non esiste un campo di potenza misurata; quindi
`impact` **non e' corroboro per la tassonomia measured/estimated**, che resta nostra (e che
AI-Wattch, al contrario, dichiara esplicitamente nel proprio README).
(b) "**applica PUE**" — la pagina lo **esclude**: `:20-22` "the estimate provided below **does
not** take datacenter PUE (Power Usage Effectiveness) into account. To do so, you need to find
your datacenter's PUE … and multiply the quantity of carbon emitted provided below by that
number". Per noi cambia poco (mini PC alimentato a muro, PUE ~ 1), ma cambia il modo di citare:
il PUE e' un **fattore nostro dichiarato**, non un servizio del tool.

Resta valido e da prendere, a costo basso: (1) il **template LaTeX di reporting** (`README:13`,
"generated latex template which automatically includes the Calculator's output") — il nostro
verbale e' oggi markdown scritto a mano, un template che inietta i numeri dal JSON sarebbe un
salto di qualita' per il capitolo 7; (2) i **fattori di griglia per regione/tempo** (MIT,
riutilizzabili legalmente) per un passaggio J/token → gCO2e/token **da dichiarare come stima**;
(3) il lessico *raw vs offset emissions* della pagina (`:15-19`).

## 7. Le osservazioni dal report LHM

Nota di onesta': `CWProject/LibreHardwareMonitor.Report.txt` **non contiene
annotazioni a mano** — e' il report puro della GUI (mtime 23/10 16:05:40, gia'
archiviato e analizzato in `lhm_gui_report_20261023_analisi.md`). Le
osservazioni sono quindi quelle che se ne estraggono, e tre sono nuove.

**(a) Il confine misurabile della macchina, provato.** Su 3238 righe di report
le uniche righe di potenza sono **5**: `CPU Package`, `CPU Cores`, `CPU Memory`,
`CPU Platform` (i9-13900HK) e `GPU Power` (Iris Xe). Il NVMe Lexar espone solo
SMART (`Power On Count 604`, `Power On Hours 621`, `/nvme/0/factor/23/24`), i
due DIMM WODPOSIT e le voci `/ram` e `/vram` non hanno alcun sensore di potenza,
la motherboard e' "Mini IT13", l'ACPI dice `System Enclosure Power Cords: 1` e
non c'e' batteria. Questo chiude una domanda di metodo: **la metrica "package"
non e' una scorciatoia, e' l'unico dominio elettrico strumentato del machine**.
Da scrivere nel capitolo metodologia/limiti, con questa lista come evidenza.

**(b) Il dominio DRAM e' morto, e ora lo sappiamo due volte.** Nel report
`/intelcpu/0/power/3` (CPU Memory) vale **0,00 W** sia il 15/10 sia il 23/10; e
ricalcolando la nostra trace `lhm_emi_trace_20261023_154628.csv` (635 righe,
160 s) il campo EMI all'offset 16 ha **delta esattamente 0**. Coerente con CEM
che dichiara il dominio memoria "server CPUs only". Conseguenza: l'energia della
RAM non e' separabile su questa macchina, e' dentro il package.

**(c) Novita' operativa: EMI ci sta gia' dando PP0 e PP1 e non li usiamo.**
Dagli stessi 160 s, medi sull'intera finestra:

```
campo EMI offset  0  (PKG)      18,95 W   <- unico usato finora
campo EMI offset 32  (PP0)      13,42 W   <- cores
campo EMI offset 48  (PP1)       0,166 W  <- iGPU
campo EMI offset 16  (DRAM)      0,000 W
```

Quindi `PKG − PP0 ≈ 5,53 W` di "resto del package" e', soprattutto, la quota
cores del **differenziale** di fase: l'inferenza vive li'. Idea di metrica
nuova, da validare: `ΔPP0/ΔPKG` per fase nei protocolli A-B-A, come misura
diretta di quanto il carico cada nel dominio dei core — rafforzerebbe
l'attribuzione senza toccare il modello EPI. **Caveat da arbitrare prima di
usarlo**: l'assegnazione offset→dominio (PKG/DRAM/PP0/PP1) e' assunta
dall'ordine dei record dell'ioctl; e' corroborata dal fatto che l'offset 16 vale
0 e che LHM chiama "CPU Memory" il suo terzo sensore (indice 3, anch'esso a 0),
ma un carico grafico dedicato la confermerebbe in modo pulito.

**(d) Coerenza con LHM, con la solita regola.** Il `CPU Cores` di LHM vale
7,29 W nel report (istantanea a idle), il PP0 di EMI 13,42 W **medi su una
finestra con carico**: numeri non confrontabili cosi', e la verifica va fatta a
finestra identica come al solito.

## 8. Azioni prioritarie

1. **[subito, ~30 min, Windows]** Probe EMI a 4 campi su una finestra A-B-A:
   colonne PP0/PP1/DRAM nel CSV di `experiment_validate_lhm.py` (o in un probe
   separato) + `ΔPP0/ΔPKG` per fase, e un carico grafico per arbitrare
   l'assegnazione offset→dominio.
2. **[dual-boot]** CEM nella checklist come secondo lettore (output `-r`) e
   **PSYS** fra le colonne: e' il sostituto piu' vicino a un wattometro senza
   esserlo. Nota: il "CPU Platform" di LHM vale 0,33 W, che non somiglia a PSYS
   (nell'esempio di CEM PSYS e' ~8 volte il package) → da arbitrare su Linux.
3. **[tesi / related work]** Quattro voci nuove in bibliografia: CEM TACAS 2020
   (DOI 10.1007/978-3-030-45237-7_8), pyJoules, mlco2/impact, AI-Wattch; e il
   paragrafo "confine misurabile" con la lista §7(a).
4. **[reporting]** Ispirarsi al template LaTeX di `impact` per far generare il
   verbale direttamente dal JSON dell'esperimento.
5. **[da evitare]** Riusare codice del toolkit Accenture (nessuna licenza);
   trattare AI-Wattch come una misura (e' un'estima, e lo dichiarano).

## 9. Cosa NON cambia (regola "tenere l'attuale finche' provato")

Nessuno dei cinque strumenti offre una lettura cumulativa su Windows: CEM e
pyJoules sono Linux-only, il toolkit Accenture dipende da pyJoules, AI-Wattch e
`impact` non toccano l'hardware. Il backend di produzione resta
LHM `power-integration` + EMI come contatore, e nessuno dei candidati e'
ammesso a sostituirlo senza evidenza misurata. Quello che cambia e' il **dopo**:
CEM e pyJoules diventano arbitri pronti per la fase Linux, e i campi PP0/PP1 di
EMI sono un'estensione interna gia' disponibile.

## Fonti verificate oggi

- https://github.com/sosy-lab/cpu-energy-meter (README grezzo, righe citate)
- https://github.com/powerapi-ng/pyJoules (README grezzo, sezioni Limitation /
  Known issues / Measurement frequency)
- https://github.com/Accenture/energy-consumption-measuring-toolkit (README
  grezzo + API repo: `license=None`, pushed 2024-05-02)
- https://github.com/AIWattch/AI-Wattch (README via fetch + API repo: MIT,
  pushed 2026-10-14)
- https://github.com/mlco2/impact (README via fetch + API repo: MIT, pushed
  2026-10-09, "passively maintained")
- `CWProject/LibreHardwareMonitor.Report.txt` (report GUI 0.9.6.0, 23/10
  16:05:40) e `experiment_results/lhm_gui_report_20261015.txt`
- `experiment_results/lhm_emi_trace_20261023_154628.csv` (635 righe, ricalcolata
  oggi per i campi PP0/PP1/DRAM)
