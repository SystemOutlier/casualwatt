---
title: "CasualWatt — Formulario Metrologico"
subtitle: "Formule, riferimenti scientifici e provenienza del codice"
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

# CasualWatt: Formulario Metrologico

Formule, definizioni, riferimenti scientifici e provenienza nel codice.

---

## 0. Principio trasversale

Ogni grandezza esportata appartiene a una delle tre classi della tripartizione:

| Classe | Significato | Esempio |
|---|---|---|
| **Misura** | Valore letto da un contatore o sensore hardware | `package_energy_j` |
| **Attribuzione** | Ripartizione di una misura tra soggetti con criterio dichiarato | `ollama_active_energy_j` |
| **Stima** | Modello di cui si dichiarano input, coefficienti e limiti | `cloud_energy_j`, `network_energy_j` |

**Regole fondamentali:**
- Nessuna grandezza di attribuzione o stima può presentarsi come misura.
- Nessun valore assente può presentarsi come `0` valido.
- Ogni formula riporta il riferimento al codice (file:riga) e i riferimenti scientifici verificati.

---

## 1. Finestra e perimetro temporale

### F.1 — Finestra profilata grezza

$$
\Delta t_{\text{raw}} = t_1 - t_0
$$

- **Significato:** durata totale della finestra profilata, dai bordi `t0` a `t1`.
- **Codice:** `local_energy.py:123–138`
- **Riferimenti scientifici:** `jcgm100` (GUM — guida all'espressione dell'incertezza di misura)

### F.2 — Finestra effettiva (al netto delle sotto-finestre escluse)

$$
\Delta t_{\text{eff}} = \max\left(\Delta t_{\text{raw}} - \sum_k (b_k - a_k),\ 10^{-6}\right)
$$

dove `J = {(a_k, b_k)}` sono le sotto-finestre escluse (segmenti del LLM-as-a-judge).

- **Significato:** durata effettiva di misura, sottraendo le sotto-finestre del giudice.
- **Codice:** `local_energy.py:123–138`
- **Riferimenti scientifici:** `jcgm100` (GUM)

### F.3 — Colonne di perimetro da esportare

| Colonna | Contenuto | Formula |
|---|---|---|
| `profile_window_s` | Finestra profilata grezza | `\Delta t_{\text{raw}}` |
| `excluded_judge_s` | Somma delle sotto-finestre escluse | `\sum_k |J|` |
| `effective_window_s` | Finestra effettiva | `\Delta t_{\text{eff}}` |
| `inference_duration_s` | Durata sola chiamata di inferenza | `duration_s` attuale |

- **Codice:** `local_energy.py:123–138`; `casualwatt_csv_export.py:118`
- **Riferimenti scientifici:** `jcgm100` (GUM)

---

## 2. Energia package (misura)

### F.4 — Energia package grezza

$$
E_{\text{pkg}}^{\text{raw}} = \text{incremento del contatore MSR del package CPU su } [t_0, t_1]
$$

Unità: millijoule (mJ), convertiti in joule.

**Tre livelli di provenienza:**

| Livello | Significato |
|---|---|
| `exact-counter` | Integrazione a 0,05 s letta esattamente ai bordi `t0/t1` (`package_energy_exact_between`) |
| `samples-fallback` | Differenza dei campioni interpolati (>= 0, con note) |
| `unavailable` | Nessun campione → **non** `0.0` valido (DP-A) |

- **Codice:** `local_energy.py:179–225`; `energy/energy_session.py:1237`
- **Riferimenti scientifici:**
  - `hahnel2012rapl` (misura RAPL su piattaforme Intel)
  - `khan2018rapl` (esperienze d'uso dei contatori RAPL)
  - `rotem2012sandybridge` (architettura MSR energetica Sandy Bridge)
  - Nota: EMI (`MSR_PKG_ENERGY_STATUS`, 0x611) è un contatore MSR della classe RAPL/MSR letto direttamente; non ha un riferimento bibliografico dedicato.

### F.5 — Status del contatore di energia

$$
\texttt{package\_energy\_status} \in \{ \text{exact-counter, samples-fallback, unavailable, counter\_reset\_suspected} \}
$$

- `counter_reset_suspected` scatta se un delta negativo tra campioni consecutivi eccede una soglia (wraparound).
- **Codice:** `local_energy.py:163–164`; `local_energy.py:469`, `:493`, `:556`
- **Riferimenti scientifici:** `jcgm100` (GUM — gestione dell'incertezza e degli outlier)

---

## 3. Baseline di idle e energia incrementale (DP-A)

### F.6 — Potenza di idle (baseline)

$$
P_{\text{idle}} = \text{mediana della potenza media su 3 finestre da 30 s senza attività}
$$

Provenienza: `{calibrated, manual_override, uncalibrated, missing}`.

- **Codice:** `local_energy.py:156–170`; `local_energy.py:405–415`
- **Riferimenti scientifici:** `jcgm100` (GUM — mediana come estimatore robusto a n = 3)

### F.7 — Energia di baseline

$$
E_{\text{base}} = P_{\text{idle}} \cdot \Delta t_{\text{eff}}
$$

- **Codice:** `local_energy.py:242`
- **Riferimenti scientifici:** `jcgm100` (GUM)

### F.8 — Energia incrementale (firmata, mai clampata)

$$
\hat{E}_{\text{att}} = E_{\text{pkg}}^{\text{raw}} - E_{\text{base}}
$$

**Regola DP-A:** il valore è firmato, mai clampato a zero. Delta negativi sono conservati come informazione diagnostica (reset del contatore), non nascosti.


- **Codice:** `local_energy.py:601–607` (integrale senza `max`); `local_energy.py:628` (valore firmato); `local_energy.py:646–647` (`active = active_raw`)
- **Riferimenti scientifici:** `jcgm100` (GUM — non nascondere l'incertezza)

### F.9 — Validità dell'energia incrementale

`active_energy_j` esportata solo se `validità(\hat{E}_{\text{att}}) = valid`, cioè:
- `\hat{E}_{\text{att}} \ge 0` (altrimenti status `baseline_exceeds_raw_energy`);
- stessa regione hardware (package), intervalli coincidenti, unità coerenti;
- contatore non in regime anomalo;
- baseline calibrata in condizioni comparabili (`uncalibrated/missing` → `baseline_not_comparable`).

- **Codice:** `local_energy.py:130`, `:136`, `:141`; `:765–770` (`active_valid`)
- **Riferimenti scientifici:** `jcgm100` (GUM)

---

## 4. Quote di attribuzione al processo (DP-B)

### F.10 — Share di ripartizione dell'incremento

$$
s_{\text{cpu}} = \text{clamp}\left( \frac{\Delta t_{\text{cpu,ollama}}}{\Delta t_{\text{cpu,busy}}},\ 0,\ 1 \right)
$$

- Numeratore: CPU time dell'albero di processi Ollama sugli intervalli non esclusi (preferisce `direct_cpu_delta` letto agli estremi esatti).
- Denominatore: `cpu_busy_seconds` di sistema (psutil percpu) sulla stessa selezione di intervalli.
- Se non osservabile: `s_cpu = 0` conservativo + status `cpu_share_unobservable`.

- **Codice:** `local_energy.py:262–278`
- **Riferimenti scientifici:** `jcgm100` (GUM — propagazione dell'incertezza nell'attribuzione)

### F.11 — Frazione di capacità CPU usata (diagnostica, non usata per l'attribuzione)

$$
r_{\text{CPU}} = \frac{\Delta t_{\text{cpu,proc}}}{\Delta t_{\text{wall}} \cdot N_{\text{CPU,effettivi}}}
$$

dove `N_CPU,effettivi` = CPU logiche realmente disponibili per il processo (affinità mask / CPU Set del job).

- **Codice:** `local_energy.py:262–278`; `local_energy.py:799`, `:802`, `:816`
- **Riferimenti scientifici:** `jcgm100` (GUM)

### F.12 — Energia attiva attribuita al processo

$$
\texttt{ollama\_active\_energy\_j} = \hat{E}_{\text{att}} \cdot s_{\text{cpu}}
$$

Esportata solo se entrambi validi.

- **Codice:** `local_energy.py:646–647`; `benchmark_v4.py:2221`
- **Riferimenti scientifici:** `jcgm100` (GUM)

---

## 5. Scorporo del giudice (DP-D)

### F.13 — Energia del giudice

$$
\texttt{judge\_energy\_j} = \text{integrazione sulla sotto-finestra del giudice con lo stesso metodo di §2–3}
$$

Esportata sempre separata dalla query misurata.

- **Codice:** `benchmark_unified.py:366–390`; `benchmark_unified.py:446–473`
- **Riferimenti scientifici:** `zheng2023llmjudge` (LLM-as-a-judge e i suoi bias)

### F.14 — Perimetro fine-to-end

$$
\texttt{end\_to\_end} = \text{perimetro inferenza (modello valutato), giudice escluso}
$$

**Vietata** la somma `judge_energy_j + ollama_active_energy_j` dentro `end_to_end`: il giudice gira sulla stessa macchina e la sua energia è una porzione della stessa `E_pkg`.

- **Codice:** `benchmark_unified.py:731–741`
- **Riferimenti scientifici:** `jcgm100` (GUM — evitare il doppio conteggio)

---

## 6. Componente GPU

### F.15 — Energia GPU (NVML, NVIDIA)

Lettura del contatore di energia cumulativo della GPU NVIDIA tramite `nvmlDeviceGetPowerUsage` (mW) o `nvmlDeviceGetTotalEnergyConsumption` (mJ), con delta tra i bordi della finestra.

- **Delta non negativo e senza sottofinestre escluse:** un delta negativo indica reset o avvolgimento del contatore, mai clampato a zero.
- **Ramo per processo:** N/A nella quasi totalità dei casi (i campioni di `nvmlDeviceGetProcessUtilization` non espongono un intervallo per processo).

- **Codice:** `energy/energy_session.py:1976` (`nvmlDeviceGetHandleByIndex`); `:2102` (`process_energy_j`); `:2139–2178` (ragioni dell'N/A)
- **Riferimenti scientifici:** `niu2025tokenpowerbench` (TokenPowerBench usa NVML/DCGM + RAPL + IPMI per nodo GPU)

### F.16 — Energia GPU (AMD SMI)

Lettura del contatore di energia della GPU AMD tramite `amdsmi_get_energy_count`, con risoluzione letta dall'API (`accumulator × resolution` in microjoule).

- Il timestamp del device (1 ns) serve come controllo di avanzamento: timestamp fermo = lettura non valida; timestamp che avanza con contatore immobile = zero legittimo.
- Se la risoluzione manca o è zero, il contatore non si usa: non si assume un valore.

- **Codice:** `energy/energy_session.py:2263` (`amdsmi_get_processor_handles`); `:2237–2241` (nota AMD)
- **Riferimenti scientifici:** Documentazione AMD ROCm / AMD SMI

---

## 7. Componente rete (stima)

### F.17 — Energia di rete

$$
E_{\text{net}} = B \cdot c_{\text{bit}}
$$

dove `B` = delta byte NIC (loopback escluso) × 8, e `c_bit = 3,4e-8 J/bit` (intensità di percorso trasmissione + commutazione verso cloud pubblico).

- La costante `c_bit` è un **proxy con sorgente non fissata in codice** — nella tesi va citata come ipotesi letteraria (Joule/bit dell'letteratura networking) e NON come standard IEEE.
- Confine dichiarato: byte delle interfacce fisiche del client; NIC di accesso non contati.

- **Codice:** `config.py:309–330`
- **Riferimenti scientifici:** Baliga, Ayre, Hinton, Tucker, *Proc. IEEE* 99(1):149-167, 2011 (verificato 26-10-2026); `baliga2011green` / `baliga2011power` (riferimento di forma, non fonte del coefficiente 2,7 uJ/bit)

---

## 8. Componente cloud (stima)

### F.18 — EcoLogits diretto (Tier 1)

$$
E_{\text{cloud}} = \text{energy}(\text{llm\_impacts}(\text{prov}, \text{mdl}, n_{\text{out}}, L)) \times 3,6\times 10^6\ \text{[J]}
$$

Esportato come intervallo [min, max]; valore = centro range.

- Il percorso CasualWatt passa a `llm_impacts` solo `output_token_count` e `request_latency`.
- Il termine `E_prefill(N_in)` non è omesso ma agisce implicitamente via `L` (la latenza server-side include il prefill).
- Il contributo del prefill non è isolato né misurato direttamente.

- **Codice:** `cloud_energy.py:133–139`; `cloud_energy.py:159–166`
- **Riferimenti scientifici:** `rince2025ecologits` (EcoLogits, JOSS 2025, verificato 20-10-2026)

### F.19 — Proxy + termine input (Tier 2)

$$
E_2 = E_{\text{ecologits}}(\text{proxy su provider supportato}; N_{\text{active}} \text{ da scheda}) \times (1 + \kappa \cdot n_{\text{in}}/n_{\text{out}})
$$

dove `\kappa \approx 0,1` centro (decode ~ order of magnitude > prefill per token), `\kappa \in [0,009; 0,30]` senza fonte confermata.

- **Codice:** `cloud_energy.py:33–38` (`_MODEL_PROXY_RULES`); `cloud_energy.py:200–204`
- **Riferimenti scientifici:** `horswill2026greenpixie` (white paper su decode vs prefill)

### F.20 — Modello fisico (Tier 3, confronto/sensibilità)

$$
E_{\text{use}} = \text{PUE} \cdot [\alpha(N) n_{\text{in}} + \gamma(N) n_{\text{in}}^2 + \delta(N) n_{\text{out}} + \varepsilon(N) n_{\text{out}}(n_{\text{in}} + n_{\text{out}}/2)]
$$

Coefficienti non calibrati; batch = 1 => upper bound. Numeri di forma da Vartziotis 2026 (0,52 pJ/FLOP; 11,68 pJ/bit HBM H100).

- **Codice:** `cloud_energy.py` (Tier 3 non implementato come default)
- **Riferimenti scientifici:** `vartziotis2026tokenstowatthours` (modello fisico)

---

## 9. Metriche derivate per query

### F.21 — Energia per output token

$$
\texttt{energy\_per\_output\_token\_j} = \frac{E_{\text{valida}}}{T_{\text{out}}}
$$

dove `E_valida` = livello più alto valido della catena misura → attribuzione.

- **Codice:** `benchmark_unified.py:465–530`; `casualwatt_csv_export.py:118`
- **Riferimenti scientifici:** `niu2025tokenpowerbench` (TokenPowerBench, J/token)

### F.22 — Energia per risposta corretta (ECPC)

$$
\texttt{energy\_per\_correct\_answer\_j} =
\begin{cases}
E_{\text{valida}} & \text{se } \texttt{is\_correct} = 1 \\
\texttt{N/A} & \text{se } \texttt{is\_correct} = 0
\end{cases}
$$

N/A letterale, non vuoto, non 0.

- **Codice:** `benchmark_unified.py:465–530`; `evaluator.py:400` e `:406`
- **Riferimenti scientifici:** `niu2025tokenpowerbench` (J/token condizionato alla correttezza)

### F.23 — Efficienza per joule (ECE per joule)

$$
\texttt{ece\_per\_joule} = \frac{\text{acc\_comp}}{E_{\text{valida}}}
$$

**Nota:** `acc_comp` è un indice descrittivo a pesi su tre componenti eterogenee, NON un'accuratezza. L'accuratezza primaria resta `is_correct` (1/0/N/A), determinata prima di `acc_comp`.

- **Codice:** `benchmark_unified.py:653` (`"N/A"` senza calcolo); `evaluator.py:230–237` (`RUOLO_COMPOSITO` / `RUOLO_BINARIA`)
- **Riferimenti scientifici:** `zheng2023llmjudge` (valutazione LLM-as-a-judge)

### F.24 — Energia per link (EPCL)

Valido solo se `basis = f1_triples` e `f1 > 0`.

- **Codice:** `benchmark_unified.py:465–530`
- **Riferimenti scientifici:** `sheth2025causalgraph2llm` (causal graph per LLM)

---

## 10. Carbonio

### F.25 — Emissioni di CO2e

$$
\texttt{CO2e\_g} = \frac{E_{\text{j}}}{3,6\times 10^6} \cdot \text{CI}
$$

dove CI = intensità di carbonio (gCO2e/kWh) da Electricity Maps API, fallback tabella offline 2024 (IT 267 g/kWh), ultima resort media mondiale 480.

- **Codice:** `benchmark_unified.py` (carbon intensity); `config.py`
- **Riferimenti scientifici:** `lacoste2019impact` (ML CO2 Impact / CodeCarbon); `patterson2021carbon` (carbon emissions of ML)

---

## 11. Incertezza e budget predittivo

### F.26 — Budget base (quadratura di semi-intervalli)

$$
\texttt{budget\_base\_w} = \text{quadratura di semi-intervalli conservativi}
$$

Non è un limite superiore garantito: per due termini non negativi, `\sqrt{a^2+b^2}/(a+b)` sta fra `1/\sqrt{2}` e `1`.

- **Codice:** `benchmark_v4.py:1010` (`hypot` di `half_range_pre_w` e `half_drift_w`); `:1021` (docstring)
- **Riferimenti scientifici:** `jcgm100` / `jcgm_gum5_2026` (GUM — propagazione dell'incertezza)

### F.27 — Incertezza di bordo

$$
u_{\text{edge,b}} = \text{lettura sincrona del contatore ai bordi di finestra con } \Delta t_W \text{ dalla stessa coppia di letture}
$$

- **Codice:** `benchmark_v4.py` (cooldown, bordo sincrono `read_counter_edge`); `energy/energy_session.py:828–839`
- **Riferimenti scientifici:** `jcgm100` (GUM — incertezza di misura ai bordi)

### F.28 — Bootstrap a livello di task

Percentile 2,5–97,5, 2000 ricampioni, seed `20261104`.

- **Codice:** `evaluation_runner.py:14–15`; `:565` (`accuracy_cluster_bootstrap_95`); `robust_evaluator.py:459–479` (`n_effective_tasks` a `:513`)
- **Riferimenti scientifici:** `jcgm100` (GUM — bootstrap per l'incertezza)

---

## 12. Gate di stabilità (P4.4 / F.12)

### F.29 — Bias del gate load-versus-control

$$
\texttt{bias\_w} = \text{rapporto delle somme sui soli controlli utilizzabili}
$$

Verdetto per blocco su `budget_base_j`; quorum `\lceil 2/3 \cdot n_{\text{coppie}} \rceil`; `chain_status = bias_declared` sotto quorum.

- **Codice:** `cwEnergyModular/control_gate.py` (modulo di sola analisi); `tests/test_control_gate_p45.py`
- **Riferimenti scientifici:** `jcgm100` (GUM — soglie di stabilità pre-registrate)

---

## 13. Riferimenti bibliografici verificati

Tutti i riferimenti seguenti sono presenti in `references.bib` e verificati alla fonte primaria:

| Chiave | Autori | Anno | Titolo / Contesto |
|---|---|---|---|
| `schwartz2020green` | Schwartz et al. | 2020 | Green AI: costi ambientali e politici del deep learning |
| `strubell2019energy` | Strubell et al. | 2019 | Energia e politiche nell'NLP (addestramento modelli grandi) |
| `hahnel2012rapl` | Hahnel et al. | 2012 | Measuring Energy Consumption for Short Code Paths Using RAPL |
| `khan2018rapl` | Khan et al. | 2018 | RAPL in Action: Experiences in Using RAPL for Power Measurements |
| `rotem2012sandybridge` | Rotem et al. | 2012 | Architettura MSR energetica Sandy Bridge |
| `jcgm100` | JCGM | — | Guide to the Expression of Uncertainty in Measurement (GUM) |
| `jcgm_gum5_2026` | JCGM | 2026 | GUM Supplement 5 (in uncertainty propagation) |
| `niu2025tokenpowerbench` | Niu et al. | 2025/2026 | TokenPowerBench: Benchmarking the Power Consumption of LLM Inference (AAAI 2026, arXiv 2512.03024) |
| `cavagna2026sweetspot` | Cavagna et al. | 2026 | SweetSpot: modello non lineare di energia inferenza (arXiv 2602.05695) |
| `rince2025ecologits` | Rincé & Banse | 2025 | EcoLogits: A framework to estimate the environmental footprint of Generative AI usage (JOSS 2025, verificato 20-10-2026) |
| `baliga2011green` | Baliga et al. | 2011 | Intensità energetica di rete (Proc. IEEE 99(1):149-167) |
| `baliga2011power` | Hinton et al. | 2011 | Riferimento di forma per il coefficiente di rete |
| `vartziotis2026tokenstowatthours` | Vartziotis | 2026 | Modello fisico Token-to-Watt-hours (Tier 3) |
| `horswill2026greenpixie` | Horswill et al. | 2026 | White paper su decode vs prefill (proxy kappa) |
| `reddi2020mlperf` | Reddi et al. | 2020 | MLPerf Inference Benchmark (ISCA 2020) |
| `tschand2025mlperfpower` | Tschand et al. | 2025 | MLPerf Power (HPCA 2025, arXiv 2410.12032) |
| `zheng2023llmjudge` | Zheng et al. | 2023 | LLM-as-a-judge e i suoi bias noti |
| `sheth2025causalgraph2llm` | Sheth et al. | 2025 | CausalGraph2LLM |
| `lacoste2019impact` | Lacoste et al. | 2019 | Quantifying the Carbon Emissions of Machine Learning (CodeCarbon/ML CO2 Impact) |
| `patterson2021carbon` | Patterson et al. | 2021 | Carbon emissions and large neural network training |

---

*Documento generato dal repository CasualWatt. Tutte le affermazioni tecniche sono ancorate al codice in `cwEnergyModular/` e ai file di protocollo in `experiment_results/`. I riferimenti bibliografici sono verificati alla fonte primaria e presenti in `references.bib`. Nessun riferimento è stato inventato.*
