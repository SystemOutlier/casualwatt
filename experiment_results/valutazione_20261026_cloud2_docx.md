# Valutazione di `cloud2.DOCX` — definizione di metodo cloud proposta il 26-10-2026

Data: **26-10-2026**. Oggetto: `CWProject/cloud2.DOCX` (testo estratto con `zipfile` +
UTF-8, 8 966 caratteri / 138 righe; il file risulta aperto in Word — esiste
`~$cloud2.DOCX` — quindi ho letto l'ultima versione **salvata su disco**, non
l'eventuale stato non salvato).

Metodo: ogni claim letto nel documento e' stato confrontato con (a) il pacchetto
`ecologits` **0.11.1 installato** (verificato stampando `__version__`, non la stringa
nei commenti), (b) il codice di produzione `cwEnergyModular/`, (c) le decisioni gia'
prese (`DECISIONI.md`, spec `metodi_per_dominio_20261025_spec.md`,
`metodo_analitico_cloud_20261026.md`), (d) la fonte primaria esterna. Postura di
lavoro: il documento e' **spunto, non evidenza** (AGENTS.md, "Un claim e' valido solo
se ancorato").

---

## 1. Verdetto sintetico

**Come presentazione del metodo, il documento e' migliore di quello che abbiamo oggi:
contiene tre cose che vale la pena adottare (§2), e le ho gia' adottate.**
**Come definizione di metodo non e' adottabile nel complesso: porta undici voci che non
possono entrare in tesi (§3), di cui otto sono claim gia' falsi o gia' refutati in
`DECISIONI.md`, una cambia in silenzio una costante di produzione del +47%, e due
contraddicono le correzioni 3.2/3.3/3.4 deliberate oggi.**

La ragione per cui "sembra migliore" e' strutturale e va detta: il documento scrive il
metodo **come lo si presenta** (diagramma, tabella per dominio, formule per fase), mentre
noi lo scriviamo **come lo si difende** (catena con stati, provenienza per riga, gate).
Le due cose non sono in concorrenza: la prima e' il testo della tesi, la seconda e'
l'appendice di metodo. Quello che non puo' succedere e' che la prima importi numeri
della seconda senza i loro ancoraggi — ed e' esattamente quello che le colonne
"Accuratezza Stimata (%)" e "Margine di Errore (%)" fanno.

---

## 2. I tre guadagni veri (adottati in `metodo_analitico_cloud_20261026.md`)

**A1 — Raggruppamento per fase di servizio, non per termine.** Il documento scrive
`E_prefill` e `E_decoding` come componenti nominate. E' la stessa algebra dei cinque
termini dell'Eq. 4, ma espressa nelle fasi che il progetto gia' usa (TokenPowerBench
riporta lo split prefill/decode; `idee_implementative_20261024.md:69` dice che il nostro
J/token "e' di fatto un costo di decode"). Il vantaggio non e' estetico: con il
raggruppamento per fase, la correzione 3.3 diventa una formula invece che una nota —
`E_prefill^C2 = 0` perche' `llm_impacts` non ha argomento di input. Applicato in §2.2
 della spec.

**A2 — La regola `N_active` per MoE.** Il documento da'
`N_active = N_total / E_tot * E_act`. Il concetto **esiste gia' nel motore**, e l'ho
verificato nel codice: `tracers/utils.py:89-94` — se `architecture.parameters` e' un
`ParametersMoE` allora `active = .active`, altrimenti `active = total` (fallback
silenzioso **del motore**, non nostro). Contando il registro installato con la sonda
tracciata `probe_ecologits_gpu_steps_moe_20261026.py`, pero', la premessa del documento
va stretta: le schede `type: moe` sono **87 su 344**, e **86** portano gia'
`parameters: {total, active}` dentro l'oggetto — `huggingface_hub/mistralai/Mixtral-8x7B-v0.1`
ha `{"total": 46.7, "active": 12.9}` — quindi il motore le legge correttamente da solo.
**Una** sola usa la chiave legacy `active_parameters` affiancata a `parameters` scalare
(`cohere/command-a-plus-05-2026`: nome a `data/models.json:136`, `parameters: 218` a
`:139`, `active_parameters: 25` a `:140`, i quattro URL di fonte a `:146-149`), e il
parser non conosce quella chiave: la consegna come `int` 218. Il caso reale non e' "il
registro tace sui MoE", e' **il formato di una scheda** — e per quella scheda il fallback
del motore scatta proprio sul dato che il produttore dichiara.
La regola di A2 nasce comunque con il suo numero, e il numero non e' quello che avevamo
scritto in questa valutazione alla prima stesura. Un MoE da 218B totali / 25B attivi
trattato come denso non sbaglia di 8,72x (il rapporto dei parametri), perche' `f_E` ha
l'offset `gamma`: sui coefficienti installati `f_E(25) = 5,476463e-05` e
`f_E(218) = 1,646615e-04` Wh/token, **rapporto 3,0067**. A parita' di scheda — stessi
parametri totali, quindi stessi `gpu_required_count` — l'energia IT di una richiesta da
200 token in 2 s sale da `9,804007e-05` a `2,738751e-04` kWh: **fattore 2,7935**. Ed e'
questo il numero che C4 va a disfare: `llm_impacts` su `command-a-plus-05-2026` restituisce
oggi `2,985238380999223e-04` kWh, che coincide **a scarto zero** con la brana trattata da
densa, non con quella governata (§2.3 della spec).

**Rettifica di questa valutazione (26-10-2026, stessa sonda).** Le righe precedenti
dicono "1 modello su 344 dichiara il campo" (in realta' 86 lo dichiarano in un'altra
forma) e "fattore 11,17 sulla richiesta" (in realta' `1,369375e-04` e' la brana a **8
bit**, `gpu_required = 4`, quindi quel rapporto mescolava due quantizzazioni: 11,17 =
4/1 × 2,7935). Il gradino 1 → 8 GPU da `1,2*25*16/8 = 60` GB a `1,2*218*16/8 = 523,2` GB
esiste, ma e' l'effetto di **cambiare classe al proxy**, fattore esatto **8,0000**, non
dell'etichetta MoE. Effetti separati: 2,7935 (etichetta) e 8,0000 (gradino); presi
insieme, 22,348. Applicato in §2.3 della spec, etichettato come **approssimazione a
esperti uniformi** con fonte il config del modello, non come formula di EcoLogits ne' di
Cavagna et al.

**A3 — Il formato della tabella metrologica** (riga = dominio x ambiente, colonne =
metodo, provenienza, boundary, note) e' piu' leggibile della tabella di metodo che
cap03 ha oggi per il cloud. Adottiamo **il formato**, sostituendo le due colonne di
percentuali con i campi che abbiamo gia' deliberato (`cloud_energy_method`,
`cloud_energy_band_semantics`, `coverage_tier`, `cloud_calibration_validity`).

---

## 3. Le undici voci non adottabili

| # | voce del documento | perche' non entra | ancoraggio |
|---|---|---|---|
| R1 | Tier 1 "**intercetta i token di input** (n_in) e output (n_out)" | falso, e contraddice la correzione **3.3 deliberata oggi**: `llm_impacts` accetta solo `output_token_count` + `request_latency` | firma verificata eseguendo la chiamata, 26-10-2026; nota B4 `cloud_energy.py:159-166` |
| R2 | `eps_bit = 0.05e-6` J/bit, etichettato "**IEEE Green Communications**" | (a) e' un valore **diverso** da quello di produzione: 5,0e-8 contro 3,4e-8 = **+47,06%** sul termine di rete (400 J/GB contro 272 J/GB); (b) l'etichetta non e' una fonte primaria (nessun numero di standard, nessun DOI, nessun autore) e il progetto dichiara esplicitamente che la fonte **non c'e' ancora** | `config.py:339-342` ("fonte bibliografica specifica non ancora fissata nel progetto — segnalato, NON modificato senza fonte"), `energy/network_energy.py:25`, spec §7, D8/F7 riga 844 |
| R3 | intere colonne "**Accuratezza Stimata (%)**" e "Margine di Errore (%)" (95-99, 1-5, 2-5, 70-85, 15-30, 90-95, 5-10, 70-80, 20-30, 50-70, 30-50, 85-90, 10-15) | nessuna misura nel repo le produce; e la nostra stessa dottrina dice che **la scala assoluta non e' arbitrata** (EMI/LHM/SRUM leggono tutti `MSR_PKG_ENERGY_STATUS` 0x611, wattmetro esterno assente), quindi "95-99% accurato" non e' semplicemente asseribile. Non e' linguaggio di incertezza del progetto | AGENTS.md ("confronto same-counter ≠ validazione", "Linguaggio dell'incertezza"), memoria di progetto "resta non arbitrata la scala assoluta" |
| R4 | "CasualWatt (**LHM + PawnIO Driver**)", "campionamento **20 Hz** superando i blocchi **HVCI/VBS**" | claim **gia' refutati nel progetto**: PawnIO assente nel codice, driver Ring-0 mai caricato, e la riga di tabella "95-98%" e' la stessa che era gia' stata giudicata auto-smentita. Il canale principale reale e' **EMI via ctypes/SetupAPI, senza Admin e senza driver** | `DECISIONI.md:151`, `DECISIONI.md:554-564`, `energy/energy_session.py:210` (`CW_PRIMARY_CHANNEL = "emi"`); origine delle righe: `Tesi-latex/capMiei/genera_capitolo_pdf.py:40,167,189,214` (materiale legacy, fuori git) |
| R5 | riga "macOS (`powermetrics`) — **Misurato**" | macOS e' **lavoro futuro** dichiarato; una riga di tabella di metodo che lo dia come coperto sovracompone il perimetro reale della tesi | `DECISIONI.md` sezione portabilita' (cap.12/conclusioni: "macOS come lavoro futuro", righe 725-729) |
| R6 | "Linux: MSR/RAPL + NVML (**Scaphandre/CodeCarbon**)" e "CodeCarbon **modalita' TDP**" | CasualWatt **non ha un percorso TDP**: `MEASURED_METHODS` e' chiuso a cinque canali misurati, e il percorso TDP e' di CodeCarbon, usato in tesi **come contrasto**, non come nostro fallback. Scaphandre compare solo come nome in una lista di tool, mai implementato | AGENTS.md ("CasualWatt non ha un percorso di stima TDP"), `energy/energy_session.py:49-50`, `DECISIONI.md:385` |
| R7 | "costanti ... **calibrate su** benchmark sperimentali (ML.ENERGY e TokenPowerBench)" | due volte non asseribile oggi: il dataset ML.ENERGY e' **gated** e senza token HF (gate **G0 non superato**, 26-10-2026), quindi una calibrazione grezza P1 non e' eseguibile; e TokenPowerBench ha confine **nodo locale single-GPU**, non arbitra un coefficiente cloud. La parola "calibrato" e' riservata a `fit-raw-holdout` | spec C5 §3 (livelli P1-P4) e §6 (G0), `huggingface_hub.whoami()` -> `LocalTokenNotFoundError`, valutazione precedente §3.7 |
| R8 | token `energy_method`: `ecologits_lca`, **`sweetspot_fallback`**, `hardware_msr` | `sweetspot_fallback` **attribuisce il nostro modello agli autori nel nome del campo** — e' esattamente la proibizione della correzione 3.2. `hardware_msr` mischia il dominio locale in un campo cloud. E il set a tre valori ignora la separazione del proxy (D3) e i cinque livelli | spec C5 §1 (catena) e §4 (campo `cloud_energy_method` con `analytic-class-fit`), DT-5 |
| R9 | cascata binaria "**EcoLogits supportato?** si' -> Tier 1 / no -> Tier 2" | cancella **C4 e C3** e mette il modello analitico subito dopo il nativo; l'ordine deliberato oggi e' `C1 -> C2 -> C4 -> C3 -> C5`. Conseguenza concreta: **`groq` non esiste nel registro** (6 provider, 344 modelli, contato 26-10-2026), quindi con la cascata del documento *ogni* chiamata Groq andrebbe in C5 saltando il proxy dichiarato C3 | spec C5 §1, `data/models.json` (provider: cohere, huggingface_hub, mistralai, anthropic, google_genai, openai) |
| R10 | "Modello Analitico Disaggregato **(2N*T)**" nella tabella | formula mai definita, non nella spec e non nel codice; `2N` e' il conteggio di FLOP per token di un transformer denso, non un coefficiente energetico. Non adottata | nessuna occorrenza in `cwEnergyModular/` ne' in `experiment_results/` |
| R11 | EcoLogits "applichi i principi LCA **conformi allo standard ISO 14044**" | **non confutata, ma non asseribile**: nel pacchetto installato non compare mai ("14044" e "ISO 14": zero occorrenze in tutta la libreria). O si trova la dichiarazione alla fonte primaria (docs/mlco2), o la conformita' ISO non va scritta in tesi | grep ricorsivo su `site-packages/ecologits` (0.11.1), 26-10-2026 |

Una voce che invece **trova il documento allineato a noi**: la gestione `None` (non
`0.0`) quando la stima cloud non riesce, con la motivazione che altrimenti la query
appare a costo zero nelle metriche derivate. E' gia' nostra regola dello zero, e il
codice la applica in senso opposto oggi (`benchmark_unified.py:1101` `est.energy_j or
0.0` = difetto F2). Nota: ECE ed EPCL **esistono** nel codice
(`benchmark_unified.py:502,543`), ma `evaluator.py:380` dichiara la formula legacy non
usabile per confronti causali formali e `:602` mette EPCL a `None` in regime B — quindi
il legame che il documento fa fra `None` ed ECE/EPCL e' corretto come principio e
va citato con questi avvertimenti.

---

## 4. Cosa cambia nel disegno, in pratica

1. §2.2 (nuovo) nella spec: la forma C5 scritta **per fasi** con `E_prefill^C2 = 0`
   reso esplicito; niente algebra nuova.
2. §2.3 (nuovo) nella spec: `N_active` per MoE, con l'ancoraggio sul motore
   (`tracers/utils.py:89-94`) e sul registro (`data/models.json:136-141` per la scheda
   legacy, `:146-149` per le sue fonti) e il numero dell'effetto **spacato in due**:
   3,0067x sul termine per token e 2,7935x sulla richiesta a parita' di scheda (etichetta
   MoE), 8,0000x se cambia la classe del proxy (gradino GPU), 22,348x se le due cose
   arrivano insieme.
3. §1 (catena): **nessuna modifica** — la cascata binaria R9 non e' adottata.
4. §4 e §5: **nessun campo nuovo** oltre a quelli gia' deliberati oggi
   (`cloud_input_tokens_included`, `cloud_energy_band_semantics`,
   `cloud_latency_used_s`, `cloud_fit_terms`); le colonne percentuali R3 non entrano.
5. Da scrivere in cap03 quando si uscira' dal congelamento: il formato della tabella
   metrologica (A3) con i nostri campi di provenienza.

---

## 5. Cosa resta da verificare prima di qualsiasi frase in tesi

- **ISO 14044**: cercare la dichiarazione su `mlco2.github.io/ecologits` o nel repo
  `mlco2/ecologits`. Se non c'e', la conformita' ISO non si cita.
- **`eps_bit`**: serve la fonte primaria se si vuole un valore **diverso** da 3,4e-8,
  oppure si resta su 3,4e-8 dichiarato come ipotesi (D8) con la sensibilita' gia'
  prevista. Il cambiamento del valore non e' una scelta di stile: sposta il termine di
  rete del +47,06% e quindi il confronto client-vs-cloud.
- **Tabella 5 / MAPE 1,79% di SweetSpot**: Eq. 4 ed Eq. 5 sono state verificate alla
  fonte primaria oggi (arXiv:2602.05695v2, HTML); "Tabella 5" come numero di tabella e
  il perimetro 1B-9B restano da ricontrollare sulla versione **ICPE '26** (ACM risponde
  403 al fetch automatico, gia' registrato in `references.bib:66-68`).

---

### Ancoraggi usati (tutti verificati 26-10-2026)

`cloud2.DOCX` (testo estratto, righe 1-138) - `ecologits` 0.11.1:
`tracers/utils.py:89-94,111`, `data/models.json:136-141`, versione
`ecologits.__version__` - `cwEnergyModular/`: `config.py:339-342`,
`energy/network_energy.py:7,23-25,35`, `energy/energy_session.py:49-50,210`,
`energy/cloud_energy.py:159-166`, `benchmark_unified.py:502,543,1101`,
`evaluator.py:380,602` - `Tesi-latex/qoder-bozza/`: `DECISIONI.md:151,385,554-564,725-729`,
`references.bib:66-78` - `experiment_results/`: `metodo_analitico_cloud_20261026.md`
§1-§5, `metodi_per_dominio_20261025_spec.md` §6-§7 (D8, F7 riga 844),
`idee_implementative_20261024.md:69`,
`valutazione_20261026_progetto_cloud.md` §3.2-§3.4 - `Tesi-latex/capMiei/`:
`genera_capitolo_pdf.py:40,167,189,214`.

Sonde: calcolo dei fattori MoE eseguito a mano sul blocco costanti installato
(α, β, γ di `impacts/llm.py:10-12`), read-only, fuori repo.
