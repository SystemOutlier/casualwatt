# Valutazione del "Progetto CasualWatt Cloud — Architettura Definitiva senza TokenPowerBench"

Documento di valutazione. Non è un'implementazione e non modifica il codice, che
resta bloccato fino al congelamento di P5 (AGENTS.md, "Stato corrente del lavoro").

Data della verifica: **26-10-2026**.
Materiale valutato: `CWProject/cloud.DOCX` (idea iniziale, letto integralmente) e la
versione estesa del progetto incollata in conversazione (sei pilastri, tre fonti di
calibrazione, roadmap di 7 fasi).
Metodo: ogni claim esterno verificato alla fonte primaria con la data della verifica;
ogni claim interno verificato sul codice e sull'installazione locale. Il materiale
prodotto da altri LLM e quello fornito dall'utente è trattato come spunto, non come
evidenza (AGENTS.md, "Un claim è valido solo se ancorato").

Le sonde usate per le verifiche su `ecologits` sono script read-only scritti in
`%TEMP%` (`probe_ecologits_20261026.py`, `probe_ecologits_registry_20261026.py`,
`probe_ecologits_range_20261026.py`): deliberatamente **fuori dal repository**, perché
non sono harness il cui output entra in una tesi o in un protocollo.

---

## 1. Verdetto sintetico

L'architettura proposta **non è nuova**: i pilastri 1, 4, 5 e 6 sono già decisi in
`experiment_results/metodi_per_dominio_20261025_spec.md` (catena cloud §3.4 righe
401-411, contenuto del numero §6 righe 596-676, rete §7 righe 680-732, decisioni D3,
D4, D8, D10, D12, D13 righe 855-871) e in `Tesi-latex/qoder-bozza/DECISIONI.md`
(DT-1…DT-4, righe 254-319). La proposta li riformula in termini propri.

Contiene però **quattro affermazioni fattualmente errate** e **tre regressioni**
rispetto a decisioni già prese, e **cinque difetti di codice reali** che la proposta
non tocca ma che rendono illusorio il suo punto di partenza (il Tier 2/proxy).

La conseguenza operativa è netta: **la tabella dei coefficienti α, β, γ non è il passo
successivo**. Costruirla ora significherebbe calibrare una forma che il progetto ha
già deciso di tenere fuori dalla catena di misura, con una fonte di calibrazione
citata sbagliata e sopra un percorso di proxy che oggi non funziona.

---

## 2. Mappa: cosa la proposta riprende da decisioni già prese

| pilastro della proposta | dov'è già deciso | scarto |
|---|---|---|
| L1 = `llm_impacts`, `E_req = PUE · E_server` | `cloud_energy.py:5-13`, spec §3.4 C2 (riga 405), DT-1 (`DECISIONI.md:254-258`) | nessuno; la proposta non dice che il PUE è **del provider**, non nostro (1,09–1,20, `tracers/utils.py:146-177`, registrato in `DECISIONI.md:246-252`) |
| L2 = modello analitico prefill/decoding | DT-3 (`DECISIONI.md:268-280`) e spec §6 righe 667-672 | **regressione**: vedi §5 |
| L3 = `E_rete = B_tot · 8 · ε_bit` | `network_energy.py:63-107`, `config.py:341-343`, spec §7 righe 708-732, D8/D13 | nessuno |
| Incertezza `min / nominal / max` | spec §6 righe 610-612, NOTE B4 (`cloud_energy.py:18-19`; semantica della banda `:48-51`) | **regressione**: vedi §3.4 |
| Colonne di tracciabilità (`cloud_method`, `calibration_sources`, `measurement_boundary`, `energy_available`) | D12 (righe 867), D13 (868), regola 9 (righe 584-592) | in parte nuovo: `cloud_provenance` con i valori `C2 / M4 (Fonte A+B) / M4 (Ipotesi)` mescola due scale, vedi §3.5 |
| "mai `0.0` per dato sconosciuto" | D4 (riga 859), F2/F9 (righe 839, 846) | **già scritto nel DOCX**, e già violato nel codice: vedi §4 |

---

## 3. I claim esterni, verificati alla fonte primaria

### 3.1 "Fonte A = ML.ENERGY: energia misurata per token, decine di modelli, framework Zeus controllato; è la stessa fonte su cui è calibrato EcoLogits"

**Verdetto: vero il contenuto, sbagliata la fonte citata.** La proposta (e la voce
`mlenergy2025` come oggi scritta) descrive il *ML.ENERGY Benchmark* citando
arXiv:2410.12032, che è un paper diverso: **MLPerf Power** (Tschand et al., HPCA 2025).
Nel testo di 2410.12032 la stringa "ML.ENERGY" non compare mai. Le quattro affermazioni
si dividono così:

- 2410.12032 **non** dà energia per token: l'unità è per campione ("we measure
  throughput in Samples/s and power consumption in Watts… yielding Samples/Joule",
  §III) e per gli LLM gli autori **abbandonano esplicitamente i token** ("we convert
  tokens into samples using an estimated median sequence length of 69 tokens/sample for
  GPT-J and 292 tokens/sample for Llama2", §V-C; Llama2-70B "consumes 111.4 J/Sample").
  La misura è con strumentazione esterna (Yokogawa WT310, PTDaemon, IPMI/RedFish), non
  con Zeus: Zeus compare solo come lavoro correlato in Tabella I.
- Il *ML.ENERGY Benchmark* (Chung et al., NeurIPS 2025 Datasets & Benchmarks,
  **arXiv:2505.06371**) è quello a cui le affermazioni corrispondono: "we compute the
  average energy consumption per token during the steady state" (§3.2), steady state
  = batch saturato al massimo configurato, misura tramite **Zeus** (§3.1).
- "è la stessa fonte su cui è calibrato EcoLogits": **confermato**, ma verso 2505.06371.
  La metodologia upstream lo dice esplicitamente: "By leveraging the open dataset from
  the ML.ENERGY Leaderboard… see the paper (arxiv.org/pdf/2505.06371)" con filtro
  H100 / batch ≤ 512 / modelli ≤ 200B (`docs/methodology/llm_inference.md`; e
  `docs/blog/posts/2025_11_methodology_update.md`: "adoption of the ML.ENERGY
  Leaderboard (Chung et al., 2025 [2505.06371]) as our energy benchmark"). I
  coefficienti resulting fit sono α=1,17e-6, β=−1,12e-2, γ=4,05e-5, che nel pacchetto
  installato sono le costanti `impacts/llm.py:10-12`.
- Il dataset per-token è pubblico con accesso gated: HF `ml-energy/benchmark-v3`,
  Apache-2.0, campo `energy_per_token_joules` (toolkit `ml-energy/data`).

La conseguenza che la proposta non dichiara: la "coerenza interna fra L1 e L2" che si
invoca è **reale solo se l'L2 resta dentro lo stesso sottoinsieme** — H100, vLLM, batch
saturato, steady state. Un provider sconosciuto non è in quell'insieme, quindi la
coerenza fra i due livelli non è una proprietà del metodo, è una condizione che va
scritta come vincolo di validità (stessa logica già applicata a SweetSpot in DT-4,
`DECISIONI.md:281-286`).

Da fare prima di qualsiasi citazione: la voce `mlenergy2025` è ancora marcata `IN
VERIFICA` in AGENTS.md:213 e oggi punta al benchmark di training. Va sostituita con
Chung 2505.06371; se MLPerf Power serve (per la strumentazione esterna), entra come
voce separata e non come fonte di J/token.

### 3.2 "L2 riprende la struttura di SweetSpot per α e γ, desunti dai valori riportati nei paper"

**Verdetto: la forma attribuita non è la forma pubblicata, e il DOCX lo diceva già.**
Il paper citato dalla tesi (`references.bib:71-78`, `cavagna2026sweetspot`, ICPE '26,
DOI 10.1145/3777884.3797011, arXiv:2602.05695) pubblica:

- Eq. 4: `E_tok = θ0 + θ1·n_in²/n_out + θ2·n_in + θ3·n_in/n_out + θ4·n_out`;
  Eq. 5 aggiunge `θ5/n_out`; Eq. 6 dà il sweet spot `n_out*`. **Verificato alla fonte
  primaria il 26-10-2026** (arXiv:2602.05695v2, versione HTML): l'Eq. 4 ha **cinque**
  termini e `θ5/n_out` compare **solo** nell'Eq. 5, quindi la forma a sei termini etichettata
  "Eq. 4–5" è l'Eq. 5. Confermati anche "fitted per modello / Tabella 5 / MAPE medio
  1,79%";
- i coefficienti θ0…θ5 sono **fitted per modello** con minimi quadrati (Tabella 5),
  MAPE medio 1,79% — sono dunque coefficienti di *modello*, non di *classe*;
- nessun `N_active`, nessun termine legato al numero di parametri, nessun concetto di
  cloud né di PUE;
  boundary: 1B–9B, H100, TensorRT-LLM, 64–4096 token.

La forma `α·n_in + γ·n_in² + δ·n_out` dell'L2 **mescola** l'energia totale (`E_tot`,
§4.1.3) con l'energia per token (`E_tok`, Eq. 4) e sostituisce i θ misurati dai singoli
modelli con coefficienti nostri indicizzati per classe. È esattamente ciò che il DOCX
originale vietava: "non bisogna attribuire agli autori formule semplificate che non
corrispondono al loro modello pubblicato", e "queste formule erano una struttura
proposta per il fallback, non una formula universale già validata. I coefficienti
devono essere calcolati… calibrati con dati sperimentali pertinenti". La verifica
conferma entrambe le avvertenze.

Rischio di citazione aggiunto, emerso durante la ricerca: **due paper diversi si
chiamano "SweetSpot"** (l'altro è un lavoro di power-capping/co-scheduling,
arXiv:2508.03520). La tesi cita quello giusto (`references.bib:71-78`, usato in
cap02:245-280, cap03:492-525, cap05:443-461, cap06:201), ma ogni riferimento futuro
deve portare il DOI, non il nome.

### 3.3 "L1 conta solo output token" — confermato, e con una conseguenza già scritta

`llm_impacts(provider, model_name, output_token_count, request_latency,
electricity_mix_zone=None)`: nessun argomento di input, verificato eseguendo la
chiamata sul pacchetto installato (26-10-2026). Spec §6 righe 614-618 già ne trae la
conseguenza: una richiesta con prompt lungo e output breve è **sistematicamente
sottostimata**, e in un confronto fra geometrie diverse la differenza sta nella
definizione, non nel modello. La proposta ripete il fatto ma non eredita l'obbligo di
scrivere la conseguenza nella riga (`cloud_input_tokens_included = false`, D12).

### 3.4 "`energy_cloud_j_min/max`: EcoLogits fornisce già il range min/max"

**Verdetto: il range esiste, ma non è un'incertezza modellistica.** Costruzione
verificata sul pacchetto installato: `compute_llm_impacts` (`impacts/llm.py:556-595`)
itera su `(min, max)` del **numero di parametri** del modello registrato e sulle
`RangeValue` di PUE/WUE del provider, e impacchetta i due risultati in un `RangeValue`.
Prova diretta: `openai/gpt-4o-mini` con 100 token di output e 1 s di latenza dà
`energy = RangeValue(min=6,1914e-06, max=7,5580e-06)` kWh, e la sua voce di registro
porta `parameters: {min: 8, max: 28}` (il numero di parametri non è pubblicato per
quel modello). Quindi il rapporto max/min ≈ 1,22 **non** è confidenza: è l'intervallo
delle nostre ignoranze sui parametri e sul PUE del provider.

Questo ha due effetti che la proposta non gestisce:

1. DT-1 (`DECISIONI.md:254-258`) dice "valore primario = intervallo [min,max]
   EcoLogits"; il codice in produzione prende la **media** come valore primario
   (`cloud_energy.py:48-51`, `:220-230`, spec §6 righe 610-612). Le due cose si
   riconciliano solo dichiarando che la banda è di assunzione, non di misura — che è
   anche l'unica lettura compatibile con la regola di linguaggio "semi-range
   conservativi, mai deviazione standard" (AGENTS.md, "Linguaggio dell'incertezza").
2. `energy_cloud_j_min/nominal/max` come colonne di incertezza sono **insufficienti**:
   la banda che conta per una stima è quella di validità del modello (provider
   sconosciuto, quantizzazione non nota, prefill escluso), e quelle sono un'altra
   cosa. Vanno tenute distinte: banda del motore da una parte, limiti di validità
   dichiarati dall'altra.

### 3.5 "`cloud_provenance: C2 / M4 (Fonte A+B) / M4 (Ipotesi)`"

**Verdetto: mixed scales.** `C1…C4` è la catena dei livelli di produzione del numero
cloud (spec §3.4 righe 401-411); `M1…M4` è la scala di produzione locale, e la spec
§3.4 etichetta esplicitamente C2/C3/C4/T1/T2 come **stima**, non come M1/M2 (righe
405-409): "non e' una lettura del contatore del server, e non e' validato" (riga 629).
Un token `M4` applicato a una stima cloud non significa quello che sembra nella scala
locale. La proposta deve scegliere un'unica notazione di provenienza per il dominio
cloud — `C1/C2/C3/C4/unavailable` — e mettere la natura dell'L2 (calibrato vs
ipotesi) in un campo separato (per esempio `cloud_calibration_state`), non in un
suffisso della scala M.

### 3.6 `ε_bit` della rete (L3)

**Verdetto: nessun supporto primario per il valore di progetto, e un'incoerenza
confine/valore da risolvere.** Ricontrollato alla fonte (26-10-2026):

| fonte | valore | confine dichiarato dagli autori | in J/bit |
|---|---|---|---|
| Aslan, Mayers, Koomey, France, *J. Industrial Ecology* 22(4):785-798 (2018), DOI 10.1111/jiec.12630, peer-reviewed | "0.06 kWh/GB for 2015"; stime pregresse "136 kWh/GB in 2000" … "0.004 kWh/GB in 2008", "vary up to 5 orders of magnitude" | "including the Internet Protocol (IP) core network and access networks only"; esclude data center e dispositivi utente | centrale 2,7e-8 |
| Heinzelman et al., IEEE VTC 2000 / TWC 2002 (first-order radio model, Tabella 1) | `E_elec = 50 nJ/bit`, `ε_fs = 10 pJ/bit/m²` | elettronica di **un solo hop** su mote WSN, non una WAN | 5e-8 |
| Keranidis et al., ACM SIGCOMM CCR 2014, DOI 10.1145/2581555.2581566 | 6,66-7,705 nJ/bit (NIC AR9380 in trasmissione) | solo il dispositivo NIC wireless — **non verificato alla fonte primaria** (PDF ACM 403), recuperato da snippet: citabile solo come da verificare | ~7e-9 |
| Miller, *J. Lightwave Technology* 35(3):343-393 (2017), DOI 10.1109/JLT.2017.2647779 | "sub-femtojoule", target "~10 fJ/bit" | livello **dispositivo/componente**, l'autore avverte che non è l'energia di sistema per bit | 1e-14–1e-11 |

Il coefficiente di progetto `3,4e-8 J/bit` = **272 J/GB** = `7,6e-5 kWh/GB` (aritmetica
verificata, spec §7 righe 711-714, `config.py:333-343`) sta sopra Aslan e sotto il
radio model: è compatibile con il confine "core + accesso", **non** con il confine
"solo NIC del client" che il commento di `config.py:334-337` dichiara. Il DOCX già
rifiutava il first-order radio model: corretto, e ora argomentato. La via supportata
dalla verifica resta quella già scritta in D8 (riga 863): non esiste una fonte
primaria con confine NIC-client, quindi il coefficiente va presentato come ipotesi
dichiarata, e D13 (riga 868) impone che il nome del campo dica `client-NIC` così la
riga non è confrontabile con cifre "per GB" di percorso completo. Nota relevante:
EcoLogits dichiara di non includere rete ("We do not account for networking or storage
primitives"), quindi `ε_bit` non può essere ancorato a C2.

### 3.7 "Senza TokenPowerBench"

**Verdetto: il benchmark esiste, è pubblico, e rimuoverlo toglie l'unico ancoraggio a
una scaling law che il progetto già usa.** Niu et al., *TokenPowerBench: Benchmarking
the Power Consumption of LLM Inference*, arXiv:2512.03024v1, accettato ad AAAI 2026,
repo `github.com/chenxuniu/TokenPowerBench`: pipeline "phase-aligned" che attribuisce
l'energia a prefill e decode di ogni richiesta, J/token, 15+ modelli (Llama / Falcon /
Qwen / Mistral, 1B–405B), sweep di batch/context/parallelism/quantization, boundary
GPU+nodo+sistema locale via NVML/RAPL/IPMI, **esclude l'energia di rete**. È già la
fonte dell'esponente `b ~ 0,46` della β(N) in DT-3 (`DECISIONI.md:268-280`, rapporto
7,3× da 1B a 70B) e la sua voce bibliografica è già deduplicata in `references.bib`
(`tokenpowerbench_2025 == niu2025tokenpowerbench`, righe 290-296).

Ciò che si può legittimamente dire è diverso da "senza": il suo confine è un nodo
locale, quindi **non arbitrera mai un numero cloud**. Ma questo non autorizza a
rinunciarvi come fonte della *forma* (split di fase, scaling con i parametri):
rinunciarvi senza sostituire l'ancoraggio lascia l'esponente β senza fonte, che è il
difetto già registrato per κ in DT-2 (righe 260-267) e riaperto in `DECISIONI.md:388`
("il 3,3x-335x per kappa resta SENZA FONTE").

---

## 4. Cinque difetti di codice verificati oggi

Sono anteriori alla proposta e la rendono prematura: la proposta assume un Tier 2 di
proxy che nel codice non arriva a produrre un numero.

1. **Le regole di proxy sono morte sulla versione installata.** `_MODEL_PROXY_RULES`
   (`cloud_energy.py:61-67`) e il fallback di famiglia (`_candidate_models`,
   `:122-135`) puntano tutti al
   provider `openrouter`, che non esiste nel registro di `ecologits` 0.11.1 installato:
   i provider sono 6 — cohere 11, huggingface_hub 176, mistralai 46, anthropic 10,
   google_genai 22, openai 79 modelli (344 entrate totali, `data/models.json`). Prova:
   `openrouter/meta-llama/llama-3.1-8b-instruct`, `groq/llama-3.1-8b-instant` e
   `huggingface_hub/meta-llama/Llama-3.1-8B-Instruct` (casing errato) restituiscono
   `energy=None` con "Could not find model"; `openai/gpt-4o-mini` restituisce un
   numero. Era già dichiarato in `DECISIONI.md:240-252`; oggi è confermato eseguendo.
   Conseguenza: la catena effettiva C2 → C4 → C3 si riduce a C2 → unavailable, e la
   spec §6 righe 601-602 descrive uno stato di fatto più buono del reale.
2. **Un dato sconosciuto diventa un numero.** `cloud_j = est.energy_j or 0.0`
   (`benchmark_unified.py:1101` prima di `027609c`, difetto F2 della spec riga 839)
   scriveva `0.0` mentre il token di metodo dice `unavailable`; in local mode lo zero
   è legittimo ma il metodo resta vuoto (`:467-474`, F9, riga 846). Entrambi violavano
   D4 (riga 859) e la regola 9 (righe 584-592). Il DOCX lo diceva già ("il risultato
   deve rimanere mancante (None), non diventare 0.0").
   **CHIUSO dal commit `027609c`**: il sito è ora `cloud_j = est.energy_j`
   (`:1145`, con il commento che nomina F2 a `:1141`), e `_finalize_energy_fields`
   pubblica `"N/A"` per la componente assente, `end_to_end_energy_j = "N/A"` e una nota
   che dice quale componente manca; i derivati di efficienza non usano più un
   denominatore fittizio. Nove test offline in
   `cwEnergyModular/tests/test_cloud_energy_none_preservato.py` bloccano **entrambe**
   le direzioni: `None -> "N/A"` e `0.0 -> 0.0` (perché la regola 12.1 non venga
   cancellata da una correzione troppo zelante — un `if not cloud_j` al posto del vecchio
   `or 0.0` avrebbe distrutto gli zeri di confine).
3. **Etichetta di carbonio con scope sbagliato.** `cloud_energy.py:174` legge
   `res.gwp`, che in EcoLogits è `gwp_usage + gwp_embodied` (`impacts/llm.py:608`),
   mentre l'energia esclude l'embodied (`cloud_energy.py:15-17`, `:182-187`). A valle,
   `benchmark_unified.py:1110` etichetta il valore "ecologits gwp (server-side,
   scope-2 incl. PUE)" e `:1113-1116` ne deriva un'intensità come `carbon / energia`:
   un quoziente fra scope misti, che non è l'intensità della mix elettrica.
   (Ancoraggi riallineati il 26-10-2026 dopo i commit `027609c` e `9ef63ac`: la riga
   era `:1110`/`:1113-1116` prima di `027609c`, ora `benchmark_unified.py:1154` e
   `:1157-1163`.)
4. **Ancora di versione non vera.** Le note citavano "llm_impacts (0.11.3)" e un
   commento dichiarava "verificato su ecologits 0.11.3", mentre l'installazione è
   0.11.1. **Parzialmente chiuso dal commit di questa rettifica**: il commento ora
   dichiara 0.11.1 (`cloud_energy.py:188`), versione stampata da
   `probe_ecologits_clamp_20261026.py`. Resta aperto il difetto di forma: la versione
   utile finisce solo nel token `method` (`:239-241`), non in un campo
   `ecologits_version` (D12).
5. **Il proxy richiede il casing registrato.** 41 nomi llama-family in
   `huggingface_hub`, con la forma esatta `meta-llama/Meta-Llama-3.1-8B-Instruct`: la
   risoluzione del proxy non è "stessa famiglia", è match di stringa, e va fissata
   con la lista reale, non con una regola a memoria.
6. **La "sovrastima d'attesa" dichiarata ha il segno sbagliato** (sonda tracciata
   `probe_ecologits_clamp_20261026.py`, output tracciato
   `experiment_results/ecologits_clamp_console_20261026.txt`, eseguita il 26-10-2026
   su ecologits **0.11.1**).
   `request_latency` ha **un solo** punto d'uso dentro il motore — `impacts/llm.py:574`
   — e passa sempre attraverso `generation_latency`, che a `:100-102` è un `min` fra
   la misura e la soglia interna del motore. Sopra la soglia la nostra misura **non
   entra più nel numero**, e il valore pubblicato resta bit-identico.
   La soglia interna, nel percorso di produzione, è `n_out / tps + ttft`
   (`:97` + `:99`), perché `llm_impacts` inietta `tps` e `ttft` dalla scheda del
   modello (`tracers/utils.py:121-122`) e **tutti i 344 modelli del registro hanno un
   `deployment`** (conteggio stampato dalla sonda). La regressione
   `α·P_active + β·BATCH_SIZE + γ` (`:14-16`, `:95`) è il ramo usato **solo quando
   `tps is None`**: qui non compare mai.
   Su `openai/gpt-4o-mini` (`deployment = {tps: 33.0, ttft: 0.6}`):

   | `output_token_count` | soglia `n_out/tps + ttft` | energia pubblicata alla soglia (plateau) | comportamento osservato |
   | --- | --- | --- | --- |
   | 32 (geometria del progetto) | 1,5697 s | `3,176229044667e-06` kWh | identica da 1,57 s a 120 s; +50,807% sul valore a 0,20 s (`2,106153287091e-06`) |
   | 100 | 3,6303 s | `8,929622014584e-06` kWh | identica da 3,70 s a 120 s; +42,881% sul valore a 0,20 s (`6,249697772159e-06`) |
   | 200 | 6,6606 s | `1,739049402917e-05` kWh | identica da 10 s a 120 s; +40,892% sul valore a 0,20 s (`1,234314554432e-05`) |

   L'incrocio è esatto, non approssimativo: a `output_token_count = 200` la misura di
   6,6606 s — arrotondata, e quindi di 6·10⁻⁶ s **sotto** la soglia 6,6606060606 s —
   dà ancora `1,739048929432e-05` kWh, mentre a 10 s il valore è il plateau
   `1,739049402917e-05`. Il termine che vincola cambia all'ultima cifra della soglia.

   Rettifica di una rettifica precedente (commit `9ef63ac`): in quella versione di
   questo punto sostenevo che `llm_impacts` non accetta `tps`, e che di conseguenza il
   percorso di produzione fosse sempre la regressione; cancellai i numeri "tps 33 →
   3,64 s" che stavano nel testo. L'affermazione è **falsa nella conseguenza**: è vero
   che la firma di `llm_impacts` (`tracers/utils.py:62-68`) non espone `tps`, ma la
   funzione lo legge dalla scheda del modello e lo passa a `compute_llm_impacts`
   (`:121-122`), quindi il ramo `1/tps` è quello che gira a ogni chiamata di
   produzione. I numeri "tps 33 → soglia 3,63 s" che avevo cancellato erano **giusti**
   (riga 100 token della tabella) e ora sono riproducibili dalla sonda; resta da
   correggere solo che il valore `8,24632535e-06` kWh era il **minimo** della banda,
   non la media (la media a 3,7 s è `8,929622014584e-06`).
   La Nota B4 e la sua rettifica (`cloud_energy.py:21-46`, nota per riga `:196-219`),
   la sua ripetizione in
   `metodi_per_dominio_20261025_spec.md:630-660` ("sovrastimata") e la paraphrase in
   `cap03_metodologia_misura.tex` (paragrafo "Tre limiti di \texttt{C2}", righe
   `:670-701`, verificata il 26-10-2026)
   descrivevano una sovrastima che nel regime
   lento non esiste: lì la rete viene **sostituita in silenzio** dalla stima del
   modello, e il numero diventa **insensibile** alla lentezza del provider — rischio
   opposto (sottostima) e, per la tesi, più grave: la riga dichiara una latenza misurata
   che non ha influito sul numero. Serve un campo che porti la latenza *effettivamente
   usata* (`cloud_latency_used_s`) e il termine vincolante (`cloud_latency_binding =
   measured | internal-estimate`), oltre alla correzione dei tre testi.

---

## 5. La decisione da prendere prima di qualsiasi tabella di coefficienti

C'è un conflitto aperto fra due documenti del progetto, e la proposta incollata lo
attraversa senza risolverlo.

- `DECISIONI.md` DT-2 (righe 260-267) e la "Revisione DT" (righe 300-302) dicono che
  il Tier 2 **è il percorso di stima effettivo del software** e "va IMPLEMENTATO nel
  codice (delta coder: `cloud_energy.py`, formula `E_ecologits(proxy) ×
  (1 + κ·n_in/n_out)`"), oggi assente.
- `metodi_per_dominio_20261025_spec.md` §6 righe 667-672 — scritto **dopo** — dice
  l'opposto: "Non sono livelli della catena: la stima TDP, il modello `κ·n_in/n_out`,
  e il rapporto `W_totale/η_eff`… se un giorno servisse una stima dichiarata, avra' un
  campo e un'etichetta propri, mai il token di un canale di misura", e indica la forma
  già ammessa: **X2 / D10** (righe 221, 313-323, 865): campo proprio
  (`energy_estimate_j`), etichetta propria, spento di default, mai confrontato con i
  numeri delle catene.

La proposta "senza TokenPowerBench" si schiera con DT-2 — l'analitico come fallback
che genera numeri nella catena — mentre la spec più recente lo esclude e ha già
preparato il contenitore (X2/D10) per tenerlo fuori. È **questa** la decisione da
prendere, non la tabella. Le tre opzioni reali:

**A. Coerente con la spec (raccomandata).** La catena cloud resta `C1 → C2 → C4 → C3 →
unavailable` e produce solo numeri EcoLogits (o telemetria del provider, se esiste).
Il modello analitico prefill/decoding vive come la forma X2 per il cloud: campo proprio
(`cloud_estimate_j`), etichetta propria, opt-in spento, mai nella stessa colonna di una
stima C2, mai a confronto. La tesi lo usa per **sensibilità e confronto di scala** —
che è ciò che DT-3 già destina al Tier 3 — e la sua bandiera di provenienza dice
esattamente quello.
Costo: nelle righe in cui il modello non è registrato né proxyzzabile, il numero cloud
resta mancante. È un costo vero, ed è il prezzo di non chiamare stima-validazione
quello che è una regressione con coefficienti nostri.

**B. Emenda esplicita alla spec.** Si ammette l'L2 nella catena, ma allora vanno
scritti: i gate G0-G4 dell'L2 (cosa deve passare per essere ammesso), la fonte dei
coefficienti con confine dichiarato, il fatto che è **calibrato su H100/vLLM/batch
saturato** e che il provider reale è sconosciuto, e la soglia sotto cui la stima non
entra in nessuna analisi. Richiede evidenza, e l'evidenza non c'è: non abbiamo ancora
eseguito nessuna delle tre validazioni del pilastro 4, e i coefficienti non esistono.

**C. Come in DT-3, solo confronto.** L'analitico non genera mai numeri pubblicati;
serve a quantificare quanto il prefill escluso possa spostare una stima. Non risolve
il problema della copertura, ma non impegna nulla.

A e C sono la stessa scelta con due ambizioni diverse; B è l'unica che giustificherebbe
la tabella α/β/γ. Raccomandazione: **A con C come uso analitico**, perché A non
promette una cosa che non possiamo validare e perché D10/X2 è già la forma adottata
per lo stesso identico problema nel dominio locale — usare due posture diverse per
cloud e locale nella stessa tesi sarebbe l'incoerenza più visibile di tutte.

---

## 6. Verdetto sintetico per pilastro

| # | pilastro | verdetto |
|---|---|---|
| 1 | tre livelli L1/L2/L3 | L1 e L3 già implementati e già normati; L2 **non** può entrare nella catena senza emenda |
| 2 | calibrazione a cascata (Fonte A ML.ENERGY, B SweetSpot, C Zeus locale) | A: fonte citata sbagliata, esiste ma con boundary H100/vLLM/steady-state; B: forma attribuita non pubblicata, i θ sono per-modello; C: micro-benchmark locale **non arbitra un provider remoto**, è un anello di plausibilità |
| 3 | incertezza min/nominal/max da EcoLogits | il range esiste ma è propagazione di assunzioni sui parametri e sul PUE: non è un'incertezza statistica; insufficiente da solo |
| 4 | tre validazioni (sensibilità, cross L1-L2, sanity check) | condivisibili e non ancora eseguite; `n_out=0` è già gestito con `max(...,1)` (`cloud_energy.py:165`), e il pavimento di latenza con `max(..., 0.05)` (`:166`) |
| 5 | colonne di tracciabilità | in gran parte già D12/D13; `cloud_provenance` con `M4` mescola due scale |
| 6 | punti di forza e limiti dichiarati | i limiti del DOCX sono più onesti di quelli della proposta: la versione estesa ha perso il divieto di attribuire formule agli autori e la clausola "None, non 0.0" |

---

## 7. Cosa fare, in ordine, senza toccare il codice

1. **Chiudere il conflitto DT-2 / §6** (la decisione A/B/C del §5) e scriverlo in
   `DECISIONI.md` come emenda datata. È il collo di bottiglia: tutto il resto dipende
   da lì.
2. **Correggere la citazione**: `mlenergy2025` → Chung et al., arXiv:2505.06371
   (NeurIPS 2025 D&D); Tschand 2410.12032 entra solo come "MLPerf Power, J/campione,
   strumentazione esterna". Uscire dallo stato `IN VERIFICA` (AGENTS.md:213) con la
   data della verifica.
3. **Aprire i cinque difetti di codice come delta per il coder** nella lista di P5
   (§4): proxy `openrouter` morto, `or 0.0`, etichetta scope-2 su GWP usage+embodied,
   ancora 0.11.3 contro 0.11.1, casing del proxy. Nessuno di questi è una scelta di
   metodo: sono correzioni che valgono qualunque sia l'esito del punto 1.
4. **`ε_bit`**: applicare D8 — declassare il coefficiente a ipotesi dichiarata e
   adottare D13 (nome del campo che dice `client-NIC`). La ricerca di fonte è esaurita:
   non c'è numero primario con quel confine.
5. **Soglia di copertura per le righe cloud non stimabili** (`cloud_validity_note`,
   `cloud_provenance` a token unico C1/C2/C3/C4/unavailable, natura della calibrazione
   in un campo separato).
6. **Solo dopo**: i coefficienti. E nella forma onesta che le fonti permettono —
   o i θ0…θ5 per-modello pubblicati da SweetSpot con il loro boundary, oppure J/token
   misurati da ML.ENERGY v3 (dataset gated Apache-2.0), oppure una regressione nostra
   dichiarata tale. Non "α, β, γ per classi di modello desunti dai paper", che è la
   forma che il DOCX vietava e che la verifica di §3.2 conferma inammissibile.

---

## 8. Cosa resta non verificato

- Keranidis (NIC 6,66-7,7 nJ/bit) e Birsanescu & Mas (EFFIFIT): PDF editore 403,
  valori recuperati da snippet — **non citabili** come evidenza.
- I θ della Tabella 5 di SweetSpot sono letti nell'HTML di arXiv:2602.05695, non
  nell'edizione ACM; prima di ripubblicarli va verificata l'edizione camera-ready.
- L'accesso efetivo al dataset gated `ml-energy/benchmark-v3` (richiesta da fare).
- La versione di `ecologits` dichiarata dalle note del codice (0.11.3) non è quella
  installata: le verifiche qui sopra valgono per **0.11.1**, la versione stampata il
  26-10-2026 da `probe_ecologits_clamp_20261026.py`. Il commento in
  `cloud_energy.py:188` è stato allineato con questa rettifica.
- Il numero MÖVE/Dalerci resta non trovato nell'estrazione, come già registrato in
  DT-4 (`DECISIONI.md:286-290`).

---

### Ancoraggi usati

- `cwEnergyModular/energy/cloud_energy.py:5-13` (strategia, "nessuna formula inventata
  fuori EcoLogits"), `:15-22` (confine, NOTE B4), `:33-38` e `:100-106` (proxy
  `openrouter`), `:136` (`max(tok,1)`), `:145` (`res.gwp`), `:153-158`, `:159-166`
  (input esclusi), `:174-179` (media del range), `:189-191` (versione nel token).
- `cwEnergyModular/benchmark_unified.py:1101` (`or 0.0`), `:1110` (etichetta scope-2),
  `:1113-1116` (intensità mista), `:466-476` (local mode).
- `cwEnergyModular/config.py:333-343` (coefficiente J/bit e confine dichiarato).
- `ecologits` installato: `tracers/utils.py:146-177` (PUE/WUE per provider),
  `impacts/llm.py:10-12` (α, β, γ del fit), `:556-595` (costruzione del
  `RangeValue`), `:608` (`gwp = usage + embodied`), `data/models.json` (344 entrate,
  6 provider).
- `experiment_results/metodi_per_dominio_20261025_spec.md:221`, `:313-323` (X2),
  `:401-411` (catene C e T), `:584-592` (regola 9), `:596-676` (cloud: contenuto,
  campi D12, esclusione dall catena), `:680-732` (rete e piano D8), `:839`, `:846`
  (F2, F9), `:855-871` (D1…D16).
- `Tesi-latex/qoder-bozza/DECISIONI.md:240-252` (verifiche locali ecologits),
  `:254-258` (DT-1), `:260-267` (DT-2 e κ), `:268-280` (DT-3 e β(N) con `b~0,46` da
  TokenPowerBench), `:281-290` (DT-4), `:300-302` ("il Tier 2 va IMPLEMENTATO"),
  `:388` (κ senza fonte).
- `Tesi-latex/qoder-bozza/references.bib:71-78` (SweetSpot ICPE '26), `:290-296`
  (TokenPowerBench deduplicato).
- Fonti esterne verificate 26-10-2026: arXiv:2410.12032 (MLPerf Power), arXiv:2505.06371
  (ML.ENERGY Benchmark), `docs/methodology/llm_inference.md` di mlco2/ecologits,
  HF `ml-energy/benchmark-v3`, arXiv:2512.03024 (TokenPowerBench, AAAI 2026),
  DOI 10.1111/jiec.12630 (Aslan et al. 2018), DOI 10.1109/JLT.2017.2647779 (Miller
  2017), DOI 10.1145/3777884.3797011 (Cavagna et al. SweetSpot, ICPE '26).
