---
title: "CasualWatt — Metodologie scientifiche per la valutazione energetica degli LLM"
author: "Progetto CasualWatt"
geometry: margin=2.5cm
fontsize: 11pt
lang: italian
header-includes:
- \usepackage{booktabs}
- \usepackage{longtable}
- \usepackage{array}
- \usepackage{xcolor}
- \usepackage{colortbl}
- \usepackage{hyperref}
- \hypersetup{colorlinks=true, linkcolor=blue, urlcolor=blue}
---

# CasualWatt: framework di benchmark energetico per inferenza LLM locale e cloud

## 1. Introduzione del progetto in breve

**CasualWatt** è un framework di misura e benchmark per l'energia consumata dall'inferenza di Large Language Model (LLM), sia in esecuzione locale che via API cloud. È progettato per hardware consumer, sia Windows che Linux. L'implementazione è stata avviata su Windows perché, su tale piattaforma, non esisteva uno strumento che misurasse l'energia della singola inferenza con un confine dichiarato e una provenienza esplicita per ogni componente.

### 1.1 Cosa misura CasualWatt

Il framework misura l'energia della singola chiamata di inferenza e la attribuisce ai componenti seguenti, ciascuno con un'etichetta di provenienza:

| Componente | Sorgente | Unità | Provenienza dichiarata |
|---|---|---|---|
| Energia package CPU (locale) | Contatore MSR del package CPU (EMI / PawnIO su Windows, RAPL su Linux) | J | `emi-counter` / `pawnio-counter` / `rapl` / `unavailable` |
| Energia GPU (locale) | NVML (NVIDIA) o AMD SMI | J | `nvml-energy` / `nvml-power-integral` / `amdsmi-energy` / `amdsmi-power-integral` |
| Energia rete | Delta contatori NIC × intensità di percorso | J | `3,4e-8 J/bit` (proxy letterario, dichiarato) |
| Energia cloud | EcoLogits via API (`llm_impacts`) | kWh → J | Stima, intervallo [min, max], etichettata |

### 1.2 Caratteristiche principali del framework

- **Misura per query**, non aggregata su sessioni: ogni riga di output corrisponde a una singola inferenza.
- **Attribuzione incrementale**: l'energia del package CPU viene scorporata della baseline di idle (mediana di tre finestre da 30 s) e l'incremento residuo viene ripartito sul processo per quota di tempo CPU (`cpu_time_share`).
- **Scorporo del giudice**: le sotto-finestre del LLM-as-a-judge vengono sottratte dalla finestra profilata e integrate a parte (`judge_energy_j`), per evitare che l'energia della valutazione venga attribuita alla query misurata. Il giudice è ancora presente nel codice di produzione.
- **Schema dati tracciabile**: colonne esplicite per `method`, `boundary`, `provenance` e `status` di ogni componente.
- **Validazione software**: suite di test che copre formule, regimi di valutazione, gate di stabilità e controllo load-versus-control.
- **Degradazione elegante**: se una sorgente non è disponibile, il framework non inventa valori e riporta `unavailable` con la ragione.

### 1.3 Stato di avanzamento

Il framework è in fase di sviluppo attivo. Le funzionalità di misura e attribuzione energetica sono implementate su Windows (EMI con fallback PawnIO) e Linux (RAPL). Il percorso GPU è implementato per entrambi i vendor (NVML per NVIDIA, AMD SMI per AMD) ma non è ancora stato esercitato su hardware reale. Il confronto locale vs cloud è implementato come stima etichettata, mai sommata alla misura diretta. Il gate di calibrazione e il Pareto energia-accuratezza-copertura sono operativi.

### 1.4 Domanda scientifica e proposta di pipeline di valutazione

La domanda scientifica corretta non è soltanto “quale modello consuma meno?”, ma “quale configurazione massimizza la qualità, l’affidabilità e l’energia per risposta corretta, per ciascuna categoria di query?”.

Per la tesi conviene quindi integrare una pipeline di valutazione a più livelli:

1. **Metriche deterministiche** — misura energetica per richiesta con confine e provenienza dichiarati;
2. **Giudizio umano campionato** — validazione su un sottoinsieme etichettato di risposte;
3. **Giudizio LLM validato** — valutazione automatica con giudice LLM, soggetto a verifica di coerenza;
4. **Metriche energetiche condizionate alla correttezza** — energia riportata solo per le risposte corrette (ECPC) o con indicazione esplicita del fallimento.

Il progetto contiene già una base solida: `acc_comp` (indice composito descrittivo), `epcl_j_per_link` (energia per risposta corretta, ECPC) ed `ece_per_joule` (efficienza per joule), oltre alla telemetria energetica per richiesta con schema dati tracciabile.

---

## 1.5 Mappatura sequenziale dei capitoli della tesi

| Cap. | Titolo macro-sezione | Contenuti chiave e focus scientifico | Estensione |
|---|---|---|---|
| 1 | Introduzione | Motivazione, Green AI, posizionamento su Agent Framework causali, problema di misura, RQ1–RQ4, contributi e confini dello scope | pp. 1–9 |
| 2 | Contesto & Stato dell'Arte | Gerarchia sorgenti energetiche, benchmark esistenti, modelli analitici vs misura diretta, sfide specifiche degli agenti LLM, limiti di CodeCarbon/RAPL | pp. 10–25 |
| 3 | Metodologia di Misura | Formulazione teorica: sensori, frequenza di campionamento, calibrazione baseline (Gate F.12), scorporo Prefill/Decoding, rete, cloud ed ECPC (P6.7–P6.10) | pp. 26–51 |
| 4 | Architettura Framework | Implementazione software: moduli di telemetria energetica, valutatore accuratezza a regimi, schema dati, pipeline post-elaborazione e GUI | pp. 52–76 |
| 5 | Valutazione Sperimentale | Setup sperimentale, confronto SRUM vs CodeCarbon vs Misura HW, overhead dell'osservatore, benchmark J/token, locale vs cloud, Pareto ed ECPC | pp. 77–116 |
| 6 | Conclusioni & Sviluppi | Sintesi dei contributi, minacce alla validità, linee guida metodologiche universali per la misura energetica negli Agent Framework LLM | pp. 117–125 |
| App. A–F | Appendici Tecniche & Formulario | Schema CSV (A), Protocollo Operativo (B), Variabili (C), Inventario Test (D), Inventario Artefatti (E) e Formulario Metrologico F.1–F.17 (F) | pp. 126–257 |

---

## 1.6 Cardini metodologici e punti di forza della tesi

- **Gate Load-versus-Control (F.12 & P4.4)** — Disaccoppiamento rigoroso tra l'energia consumata dall'infrastruttura di base (baseline/idle drift) e l'incremento netto direttamente imputabile al processo di inferenza del modello.
- **ECPC & Frontiera di Pareto (§3.13 / §5.15)** — Introduzione del parametro Energy Cost Per Correct response (ECPC), legato alla frontiera di Pareto accuratezza-energia per valutare la reale efficienza condizionata alla correttezza.
- **Separazione Prefill vs Decoding (§3.6)** — Isolamento energetico della fase di elaborazione del prompt (prefill, quadratico rispetto al contesto) dalla fase di generazione sequenziale (decoding, lineare sui token generati).
- **Formulario Metrologico Unificato (Appendice F)** — Codifica formale di tutte le equazioni (F.1–F.17) per la propagazione delle incertezze, bootstrap dei residui e budget predittivo, elevando la tesi a standard metrologico.

---

# 2. Metodologie scientifiche per la valutazione energetica degli LLM

Questa sezione espone le metriche e le metodologie utilizzate, con definizioni, caratteristiche, pregi e difetti, cosa misurano, quando è preferibile l'una piuttosto che l'altra, e i riferimenti alla letteratura.

## 2.1 Quadro concettuale: misura, attribuzione, stima

CasualWatt adotta una tripartizione che separa nettamente le tre classi di grandezze esportate:

1. **Misura**: valore letto da un contatore o sensore hardware. Esempio: `package_energy_j` dal contatore MSR del package CPU.
2. **Attribuzione**: ripartizione di una misura tra soggetti con criterio dichiarato. Esempio: `ollama_active_energy_j` = incremento del package attributo al processo per quota di tempo CPU.
3. **Stima**: modello di cui si dichiarano input, coefficienti e limiti. Esempio: `cloud_energy_j` da EcoLogits.

**Regola fondamentale**: nessuna grandezza di attribuzione o stima può presentarsi come misura; nessun valore assente può presentarsi come `0` valido.

## 2.2 Metriche di misura energetica (hardware)

### 2.2.1 Contatore MSR del package CPU (EMI / PawnIO)

**Definizione.** Incremento del registro `MSR_PKG_ENERGY_STATUS` (0x611) letto a intervalli regolari e integrato sulla finestra di misura `[t_start, t_end]`. Unità: millijoule (mJ), convertiti in joule.

**Cosa misura.** L'energia totale consumata dal package CPU (tutti i core, inclusi i core grafici integrati e l'unità non-core) durante la finestra.

**Pregi.**
- Contatore hardware on-die, letto direttamente dal MSR: non dipende da driver di terze parti né da interfacce di monitoring grafico.
- Contatore cumulativo (non integrazione numerica di potenza istantanea): evita l'errore di discretizzazione dell'integrale.
- Alta risoluzione temporale (timestamp a 100 ns via EMI).

**Difetti.**
- Richiede privilegi elevati (UAC): su token filtrato o SAFER, l'apertura del driver può rispondere `access_denied`. EMI non ha questo requisito.
- Su Windows consumer non sempre è accessibile senza driver firmato Microsoft (fail closed con HVCI attivo).
- Misura il package intero, non un singolo processo: richiede un criterio di attribuzione per isolare il carico del modello LLM.

**Quando usarlo.** Quando si ha accesso al MSR del package CPU e si vuole una misura diretta dell'energia del package, da scorporare della baseline di idle.

**Riferimenti.** Non esiste un riferimento bibliografico formale dedicato a EMI: è un contatore MSR (`MSR_PKG_ENERGY_STATUS`, 0x611) della classe dei contatori RAPL/MSR. Per la classe di riferimento si veda `hahnel2012rapl` (misura RAPL su piattaforme Intel), `khan2018rapl` (esperienze d'uso RAPL), `rotem2012sandybridge` (architettura MSR energetica Sandy Bridge).

### 2.2.2 RAPL (Linux)

**Definizione.** Lettura dei contatori RAPL (Running Average Power Limit) su Linux tramite interfaccia sysfs o libreria dedicata.

**Cosa misura.** L'energia del package CPU e di sottodomain (DRAM, PP0, PP1) su piattaforme Intel e AMD.

**Pregi.**
- Contatore hardware on-die, ampiamente documentato e validato in letteratura.
- Disponibile nativamente su Linux senza driver proprietari aggiuntivi.

**Difetti.**
- Disponibile solo su Linux; su Windows non è accessibile allo stesso modo.
- Misura il package o sottodomain, non un singolo processo.

**Quando usarlo.** Su Linux, come contatore principale del package CPU.

**Riferimenti.** `hahnel2012rapl`, `khan2018rapl`.

### 2.2.3 NVML (NVIDIA Management Library)

**Definizione.** Lettura del contatore di energia cumulativo della GPU NVIDIA tramite `nvmlDeviceGetPowerUsage` (mW) o `nvmlDeviceGetTotalEnergyConsumption` (mJ), con delta tra i bordi della finestra.

**Cosa misura.** L'energia della scheda GPU intera (board power), non ripartita per processo.

**Pregi.**
- Contatore hardware on-die del dispositivo NVIDIA.
- Delta non negativo e senza sottofinestre escluse: un delta negativo indica reset o avvolgimento del contatore, mai clampato a zero.

**Difetti.**
- Disponibile solo su GPU NVIDIA; assente su macchine consumer senza dGPU.
- Non esiste una catena NVML → AMD SMI per la stessa scheda: i due non girano mai in parallelo.
- Il ramo per processo non ha una durata da usare: i campioni di `nvmlDeviceGetProcessUtilization` non espongono un intervallo per processo, quindi `gpu_process_energy_j` è N/A nella quasi totalità dei casi.

**Quando usarlo.** Quando è presente una GPU NVIDIA e si vuole misurare l'energia della scheda intera durante l'inferenza.

**Riferimenti.** `niu2025tokenpowerbench` (TokenPowerBench usa NVML/DCGM + RAPL + IPMI per nodo GPU), documentazione NVIDIA NVML.

### 2.2.4 AMD SMI

**Definizione.** Lettura del contatore di energia della GPU AMD tramite `amdsmi_get_energy_count`, con risoluzione letta dall'API (`accumulator × resolution` in microjoule).

**Cosa misura.** L'energia della scheda AMD intera.

**Pregi.**
- Contatore hardware on-die per GPU AMD.
- Il timestamp del device (1 ns) serve come controllo di avanzamento: timestamp fermo = lettura non valida; timestamp che avanza con contatore immobile = zero legittimo.

**Difetti.**
- Se la risoluzione manca o è zero, il contatore non si usa: non si assume un valore.
- Disponibile solo su GPU AMD; non esiste una catena AMD SMI → NVML.

**Quando usarlo.** Quando è presente una GPU AMD e si vuole misurare l'energia della scheda intera.

**Riferimenti.** Documentazione AMD ROCm / AMD SMI.

## 2.3 Metriche derivate (attribuzione incrementale)

### 2.3.1 Baseline di idle e energia incrementale

**Definizione.** `P_idle` = mediana della potenza media su tre finestre da 30 s senza attività. `E_base = P_idle · Δt_eff`. L'energia incrementale è `Ê_att = E_pkg^raw − E_base`, firmata, mai clampata a zero.

**Cosa misura.** La parte di energia del package eccedente il consumo di idle, attribuibile al carico attivo.

**Pregi.**
- La mediana è robusta a finestre contaminate (con n = 3 una finestra anomala sposta la media ma non la mediana).
- L'incremento firmato conserva informazioni diagnostiche (delta negativi = reset del contatore, non errore da nascondere).
- Calibrazione pre-run: la baseline viene stabilita prima della campagna di misura.

**Difetti.**
- Se la baseline non è calibrata (`idle_provenance = uncalibrated` o `missing`), l'energia incrementale non è confrontabile e viene esportata con status `baseline_not_comparable`.
- Richiede un periodo di assestamento (settling) prima della misura; su macchine cariche il run parte con `background_load = True`.

**Quando usarlo.** Sempre, come primo passo di qualsiasi misura energetica su hardware consumer.

**Riferimenti.** `jcgm100` / `jcgm_gum5_2026` (GUM, Guide to the Expression of Uncertainty in Measurement).

### 2.3.2 Quota di tempo CPU (`cpu_time_share`)

**Definizione.** `s_cpu = clamp(Δt_cpu,ollama / Δt_cpu,busy, 0, 1)`, dove il numeratore è il CPU time dell'albero di processi del modello LLM e il denominatore è il tempo CPU busy di sistema sulla stessa selezione di intervalli.

**Cosa misura.** La frazione del tempo CPU busy attribuibile al processo del modello LLM, usata per ripartire l'incremento energetico del package.

**Pregi.**
- Criterio di attribuzione semplice e dichiarato.
- Conservative: se il processo non è osservabile, `s_cpu = 0` con status `cpu_share_unobservable`.

**Difetti.**
- Assume equivalenza fra quota di tempo CPU e quota di energia: un'assunzione dichiarata, non verificata da wattmetro esterno.
- Non è una misura diretta di energia, ma una ripartizione di una misura esistente.

**Quando usarlo.** Quando si deve attribuire l'incremento del package CPU a un singolo processo su hardware consumer senza contatori per-processo.

**Riferimenti.** `jcgm100` (GUM per l'incertezza di misura, applicata alla propagazione dell'attribuzione).

## 2.4 Metriche di stima (cloud e rete)

### 2.4.1 EcoLogits

**Definizione.** Stima dell'impatto ambientale di una chiamata API LLM tramite `llm_impacts(prov, modello, n_out, latenza)`, convertita da kWh in joule e da kg CO₂e in gCO₂e. Esportata come intervallo [min, max].

**Cosa misura.** Stima dell'energia e delle emissioni di CO₂e per una chiamata API cloud, basata su modello, output token e latenza.

**Pregi.**
- Non richiede accesso hardware al server remoto.
- Fornisce un intervallo di incertezza ([min, max]) invece di un valore puntuale.

**Difetti.**
- Scatola chiusa: il termine di prefill non è isolato né misurato direttamente; entra implicitamente tramite la latenza server-side.
- Gli input token sono ignorati nel percorso CasualWatt (solo `output_token_count` e `request_latency` vengono passati).
- I provider `openrouter` e `groq` non esistono in EcoLogits 0.11.1: le regole di proxy che li citano collassano a `unavailable`.

**Quando usarlo.** Lato cloud, quando non si ha accesso alla misura diretta del server e si accetta una stima con intervallo di incertezza dichiarato.

**Riferimenti.** `rince2025ecologits` (EcoLogits, JOSS 2025, verificato 20-10-2026).

### 2.4.2 Rete (stima J/bit)

**Definizione.** `E_net = B · c_bit`, dove `B` è il delta byte NIC (loopback escluso) × 8 e `c_bit = 3,4e-8 J/bit` (intensità di percorso trasmissione + commutazione verso cloud pubblico).

**Cosa misura.** Stima dell'energia di trasmissione dei dati di rete tra client e server cloud.

**Pregi.**
- Semplice da calcolare dai contatori NIC di sistema.
- Confine dichiarato: byte delle interfacce fisiche del client, NIC di accesso non contati.

**Difetti.**
- Il coefficiente `c_bit` è un proxy letterario, non validato sperimentalmente da CasualWatt.
- La rete di accesso del client è esclusa dalla fonte del coefficiente.

**Quando usarlo.** Quando si vuole includere una stima del costo energetico di rete nel confronto locale vs cloud.

**Riferimenti.** Baliga, Ayre, Hinton, Tucker, *Proc. IEEE* 99(1):149-167, 2011 (verificato 26-10-2026).

## 2.5 Metriche derivate per query

| Metrica | Definizione | Condizione di validità |
|---|---|---|
| `energy_per_output_token_j` | `E_valida / T_out` | `E_valida` = livello più alto valido della catena misura→attribuzione |
| `energy_per_correct_answer_j` (ECPC) | `E_valida` se `is_correct = 1`, `N/A` letterale se 0 | `is_correct` determinato prima di `acc_comp`; valido anche per le risposte errate (energia del fallimento) |
| `ece_per_joule` | `acc_comp / E_valida` | `E_valida > 0`; `acc_comp` è indice descrittivo, non accuratezza |
| `epcl_j_per_link` | solo con `basis = f1_triples` e `f1 > 0` | `f1_triples` come base |
| `cpu_time_share` | quota di tempo CPU del processo sul busy time di sistema | processo osservabile |

**Nota su `acc_comp`.** `acc_comp` non è un'accuratezza: è un indice descrittivo a pesi su tre componenti di natura eterogenea. L'accuratezza primaria resta `is_correct` (1/0/N/A), determinata prima di `acc_comp`. Il nome storico "accuracy composita" è ambiguo e la rinomina è dichiarata nel codice; `acc_comp` resta come indice descrittivo supplementare, non come metrica principale.

## 2.6 Tabella comparativa: quando usare quale metodo

| Metodo | Cosa misura | Strumentazione | Scala | Limite principale per CasualWatt |
|---|---|---|---|---|
| **MLPerf Inference** | Prestazioni (latenza/throughput) | Certificata, datacenter | Sistema | Non misura energia |
| **MLPerf Power** | Energia/efficienza (mW→MW) | UPS/PDU certificati + firmware | Sistema/nodo | Richiede hw enterprise; nessuna GPU dedicata nel target |
| **Green500** | FLOP/watt (HPCG) | PDU di nodo | Top500 supercomputer | Non applicabile a endpoint user |
| **TokenPowerBench** | Potenza/energia inferenza, J/token, prefill/decode | NVML/DCGM, RAPL, IPMI | Nodo GPU | Presuppone GPU NVIDIA e Linux; non Windows senza dGPU |
| **EcoLogits** | Stima LCA per chiamata API (usage + embodied) | Nessuna (modello) | API cloud | Scatola chiusa; solo g(T_out, L) |
| **CodeCarbon** | Stima CPU+GPU+RAM con intensità carbonio regionale | Nessuna (modello) | Host/codice | Stima, non misura; usato come contrasto, non come percorso di produzione |
| **CasualWatt** | Misura package + attribuzione per-processo + Judge scorporato + stima cloud | MSR (EMI/PawnIO/RAPL), NVML, AMD SMI, NIC | PC Windows e Linux consumer | Nessun benchmark sopra copre Windows/Linux consumer senza dGPU, per-chiamata, con status di validità |

## 2.7 Sintesi dello stato di implementazione

| Area | Stato | Dettaglio |
|---|---|---|
| Misura energia CPU | Implementata | Contatore cumulativo, non integrazione di potenza |
| Windows | Implementata | EMI, con fallback PawnIO |
| Linux | Implementata | RAPL |
| Attribuzione al processo | Implementata | Quota di tempo CPU dell'albero di processo |
| Baseline | Implementata | Mediana di 3 finestre da 30 s |
| Incertezza | Implementata | Budget in quadratura di semi-intervalli |
| GPU | Parzialmente implementata | NVML o AMD SMI secondo vendor |
| Cloud | Implementata come stima | Etichettata, non sommata alla misura |
| Qualità | Implementata | Verdetto binario + indice composito |
| ECPC | Implementata | Energia per risposta corretta |
| Pipeline di valutazione | Implementata | Gate, perturbazioni, Pareto, tassonomie |

**Cosa è già ben fatto.**
- Contatore cumulativo invece di integrazione numerica.
- Baseline pre-run.
- Residuo firmato, non troncato a zero.
- Attribuzione per processo.
- Separazione locale/cloud.
- Dichiarazione esplicita di unità, metodo e confini.
- ECPC con energia dei fallimenti.
- Gate di calibrazione.
- Pareto energia-accuratezza-copertura.

## 2.8 Riferimenti bibliografici verificati

- **Schwartz et al., 2020** — Green AI: costi ambientali e politici del deep learning.
- **Strubell et al., 2019** — Energia e politiche nell'NLP (addestramento modelli grandi).
- **Henderson et al.** — Rumore di misura nelle metriche di scaling.
- **Luccioni et al., 2024** — Impronta di BLOOM (PowerHungry).
- **Rincé & Banse, 2025** — EcoLogits: framework per stimare l'impronta ambientale del GenAI (JOSS, verificato 20-10-2026).
- **Niu et al., 2025** — TokenPowerBench: benchmarking del consumo energetico dell'inferenza LLM (AAAI 2026, arXiv 2512.03024).
- **Tschand et al., 2025** — MLPerf Power: benchmarking dell'efficienza energetica dei sistemi ML (HPCA 2025, arXiv 2410.12032).
- **Reddi et al., 2020** — MLPerf Inference Benchmark (ISCA 2020).
- **Cavagna et al., 2026** — SweetSpot: modello non lineare di energia inferenza (arXiv 2602.05695).
- **JCGM 100 / GUM** — Guida all'espressione dell'incertezza di misura.
- **Hahnel et al.** — Validazione dei contatori RAPL su piattaforme Intel.
- **Khan et al., 2018** — RAPL in Action: esperienze d'uso dei contatori RAPL.
- **Rotem et al., 2012** — Architettura MSR energetica Sandy Bridge.
- **Baliga et al., 2011** — Intensità energetica di rete (Proc. IEEE).
- **Documentazione NVIDIA NVML** — Contatori di energia GPU NVIDIA.
- **Documentazione AMD ROCm / SMI** — Contatori di energia GPU AMD.

*Documento generato dal repository CasualWatt. Tutte le affermazioni tecniche sono ancorate al codice in `cwEnergyModular/` e ai file di protocollo in `experiment_results/`.*
