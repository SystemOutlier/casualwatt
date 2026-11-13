# Come valutiamo la correttezza delle risposte

Relazione breve sul percorso di scoring di CasualWatt: quali stati produce,
come si decide un verdetto, e cosa il framework accetta in ingresso. Tutti i
riferimenti sono `file:riga` sul codice di produzione in `cwEnergyModular/`,
verificati il 2026-11-13.

## 1. L'unità di misura: `is_correct` a tre stati

La correttezza di una risposta è un campo a **tre stati**, non una percentuale
continua:

- `1` — risposta corretta rispetto al riferimento disponibile;
- `0` — risposta errata;
- `None` (scritto `N/A` nel CSV) — non determinabile: riferimento mancante o
  ambiguo, estrazione fallita, giudice non calibrato.

Il terzo stato è un esito dichiarato, non uno zero mascherato: una risposta non
valutabile non è una risposta sbagliata. Sul report il verdetto si presenta a
quattro stati — `correct`, `incorrect`, `indeterminate`, `unscored`
(`evaluation_runner.py:127-141`) — dove `unscored` è riservato al ramo bloccato
dal gate di calibrazione: il giudice non è stato chiamato perché il ramo non è
validato, quindi non è un errore del modello ma una non-valutazione.

## 2. Il decisore unico

Tutta la valutazione passa da una sola funzione:
`evaluator.evaluate_response` (`evaluator.py:422-455`), che non solleva mai
eccezioni. Riceve il testo della risposta, la ground truth (può essere assente),
la modalità, la domanda, il modello valutato e due interruttori: il giudice
(iniettabile, per i test) e il flag `judge_gated` del gate di calibrazione.

La modalità seleziona il regime (`evaluator.py:470-491`):

| modalità | regime | nota |
|---|---|---|
| `skip` | nessuna valutazione | solo energia, `is_correct` resta vuoto |
| `causal` / `heuristic_keyword_fallback` | euristica keyword | alias storico, diagnostico, **non** è un'accuratezza su ground truth |
| `auto` | A se c'è ground truth, B se non c'è | risolto dentro `evaluate_response` |

## 3. Regime A — con ground truth (`evaluator.py:494-640`)

Quando la ground truth è presente, il verdetto è **deterministico**: nessun
giudice LLM è necessario per produrre `is_correct`. Il tipo di risposta si
ricava dalla ground truth stessa (`detect_answer_type`, `evaluator.py:69-80`):
tutte le alternative numeriche finite → `number`; altrimenti ≤ 6 parole →
`short_text`; altrimenti `free_text`.

**`number`** (`evaluator.py:507-552`). Il parser estrae il numero dalla risposta
(`extract_numeric_answer`), lo confronta con ciascuna alternativa della ground
truth (separatore `|`) tramite `compare_numbers` (`evaluator.py:92-107`):
tolleranza relativa 1e-6 se la GT è diversa da zero, assoluta 1e-6 se è zero,
con controllo di compatibilità dimensionale (unità SI e percentuali convertite
prima del confronto). Esiti: estratto e coincidente → `1`; estratto e diverso →
`0`; nessun numero nella risposta → `0` (`:532`); risposta ambigua (più numeri
non marcati) → `None` (`:537`); ground truth non numerica finita → `None`
(`:515`). Su questo ramo `acc_comp` coincide con `is_correct` per definizione.

**`short_text`** (`evaluator.py:554-564`). Normalizzazione del testo e
contenimento con confini di parola (`check_short_text_containment`
`evaluator.py:152`, `_contains_phrase` `:110-126`): "Atene" è contenuta in
"Atene è la capitale", ma "ten" non è contenuta in "Atene".

**`free_text`** (`evaluator.py:565-640`). Similarità semantica con embedding:
`is_correct = 1` se `semantic_similarity >= 0.75` (soglia `SEMANTIC_THRESHOLD`,
`evaluator.py:55-57`). Gli embedding non sono caricati durante il benchmark
(default `use_semantic=False`) per non spendere energia: in quel caso
`is_correct` viene da un fallback lessicale dichiarato (soglia 0.85, `:611`), e
la valutazione semantica completa si fa post-hoc con `semantic_judge.py`. Se gli
embedding non sono disponibili, `is_correct` resta `N/A` (`:602`) — la somiglianza
lessicale non viene presentata come accuratezza.

## 4. Regime B — senza ground truth (`evaluator.py:642-713`)

Senza ground truth l'unico produttore possibile di correttezza è un modello
supervisore: `llm_judge.call_llm_judge` (`llm_judge.py:107`; modello default
`llama3.2:1b`, variabile `CW_JUDGE_MODEL`, `llm_judge.py:75`). Il giudice
restituisce un punteggio 1-5 e la soglia è **4.0**:

```python
res.is_correct = (1 if j_score >= 4.0 else 0) if j_score is not None else NA
```

(`evaluator.py:704`). Giudice non disponibile → `is_correct = N/A`, mai `0`.
I campi che richiedono un riferimento non esistono e restano `N/A`:
`cosine_sim`, `semantic_similarity`, `triples_gt`. `acc_links` in questo regime
dice solo che una struttura causale **è presente ed estraibile**, non che è
corretta (`evaluator.py:670-690`) — campo dichiaratamente diagnostico.

**Il gate di calibrazione.** Finché il ramo del giudice non è validato contro il
riferimento umano (protocollo in `experiment_results/human_calibration_protocol.json`),
il parametro `judge_gated=True` blocca il regime B in modo *fail-closed*
(`evaluator.py:648-660`): `is_correct = N/A` con motivo `judge_uncalibrated`,
giudice **non chiamato**, nessuna accuratezza pubblicata. I rami deterministici
del regime A non sono toccati: la loro `is_correct` viene dalla ground truth,
non dal giudice. I flag per strato sono prodotti da
`human_calibration_gate.judge_gated_flags` (`human_calibration_gate.py:1055-1062`):
`judge_gated_{strato}` è vero quando lo strato non è `validated`.

## 5. Cosa non è l'accuratezza

`acc_comp` è un **indice descrittivo composito** a pesi (nel regime A:
`acc_links`, `judge/5`, coseno; nel regime B: `acc_links`, `judge/5`), la cui
scala mescola un punteggio 0-1 con una media su scala 0-5. L'accuratezza primaria
è `is_correct`, determinata **prima** di `acc_comp` in ogni ramo. Il ruolo è
dichiarato nelle note di riga (`RUOLO_COMPOSITO` / `RUOLO_BINARIA`,
`evaluator.py:234-241`), non in una colonna dello schema. `acc_comp` non è un
numeratore di efficienza energetica e non va presentata come accuratezza.

## 6. Da dove arrivano i prompt

Le richieste possono venire da tre sorgenti (`test_source.py`):

- **CSV esterno** (`test_source.py:9-17`): colonna del testo cercata tra
  `prompt`/`text`/`question`/`input`/`query`; ground truth opzionale tra
  `ground_truth`/`expected_result`/`expected`/`answer`/`target`/`label`
  (`:41-43`); tipo di risposta opzionale tra `answer_type`/`type`/
  `response_type` (`:45-47`). Un CSV a colonna singola senza header è trattato
  come prompt grezzi, quindi **senza ground truth**.
- **Prompt manuale** (`:19-21`, `:205-227`): una riga per prompt; la ground
  truth e il tipo si possono accodare con separatori dedicati.
- **Dataset di default** in configurazione (`:270-292`).

La scelta del regime è **per singolo prompt** (`benchmark_v4.py:1956-1963`, che
chiama `_resolve_eval_mode`, `benchmark_unified.py:424-443`):

1. ground truth presente nel prompt → `auto` → regime A deterministico;
2. prompt marcato causale (flag, id o contenuto) → euristica keyword,
   esplicitamente **non** un'accuratezza su ground truth;
3. altrimenti → `skip`: si misura l'energia e **non si pubblica alcuna
   correttezza**.

L'override esplicito (`auto`/`causal`/`skip`) ha sempre priorità ed è
disponibile come parametro `eval_mode_override` del runner
(`benchmark_v4.py:1803`, `:2449`, `:2714`); la CLI non lo espone oggi, quindi
dal CLI la regola è sempre la risoluzione automatica per prompt.

## 7. La domanda: test con ground truth e prompt casuali

**Sì, il framework è preparato per entrambi, e la differenza è dichiarata, non
nascosta.** Per il confronto di efficienza tra modelli si usa una batteria di
task con ground truth: su quelli il verdetto è deterministico, riproducibile e
non dipende da nessun modello supervisore. Un prompt casuale — senza ground
truth — entrerebbe nel regime B, dove la correttezza la produce il giudice LLM
con soglia 4.0; quel percorso è oggi bloccato *fail-closed* dal gate di
calibrazione (`is_correct = N/A`, motivo `judge_uncalibrated`), quindi un
prompt senza ground truth e senza marcatura causale, nelle condizioni attuali,
produce solo la misura energetica. Un dataset misto è gestito senza
configurazioni: ogni prompt viene risolto per conto proprio, quelli con ground
truth danno il verdetto deterministico, gli altri il percorso giudice (o lo
skip). La valutazione dei prompt casuali diventa pubblicabile quando il ramo del
giudice passa la calibrazione umana prevista dalla Fase 0: è esattamente il
lavoro in corso, non un limite rimosso in silenzio.

## 8. Le formule

Tutte le formule riportate di seguito sono prese direttamente dal codice di
produzione (`cwEnergyModular/`) con gli ancoraggi precisi. Le referenze
bibliografiche contrassegnate `% VERIFICATO` in `references.bib` sono quelle
ufficialmente verificate; le voci `% IN VERIFICA` sono citate come letteratura
ma non possono essere usate come evidenza metrologica.

### 8.1 Toleranza comparativa numerica (`compare_numbers`, `evaluator.py:92-107`)

```latex
\texttt{tolleranza relativa } 10^{-6} \text{ se } E_{\text{GT}} \neq 0,
\quad
\texttt{tolleranza assoluta } 10^{-6} \text{ se } E_{\text{GT}} = 0,
\quad
\texttt{controllo compatibilità dimensionale (unità SI e \% convertite)}
```
Formula nel codice: `:92-107`; ancoraggio bib: `@article{jallouli2026methodology` per
metodologia incertezza su dispositivi eterogenei.

### 8.2 Soglia semantica (`evaluator.py:55-57`)

```latex
\texttt{is\_correct = 1} \text{ se } \texttt{semantic\_similarity} \geq
\texttt{SEMANTIC\_THRESHOLD} \;(0.75)
```
Ancora: embedding non caricati per default (`use_semantic=False`), fallback lessicale
soglia 0.85 (`:611`), valutazione completa post-hoc con `semantic_judge.py`.

### 8.3 Soglia giudice LLM (`evaluator.py:704`)

```latex
\texttt{is\_correct = (1 \text{ se } j\_score \geq 4.0 \text{ else } 0) \text{ se } j\_score \text{ is not None else NA}}
```
Bib: `@inproceedings{zheng2023llmjudge` (NeurIPS 2023 Datasets&Benchmarks) per benchmark
giudice LLM; `@misc{tan2024judgebench` (arXiv:2410.12784, 11-11-2026) per JudgeBench;
`@misc{park2024offsetbias` (arXiv:2407.06551, 11-11-2026) per OffsetBias/EvalBiasBench;
`@misc{ye2024justice` (arXiv:2410.02736, ICLR 2025) per bias nei giudici; `@misc{saadfalcon2025ipw` (arXiv:2511.07885, 11-11-2026) per IPW.

### 8.4 acc_comp: indice composito a pesi (`evaluator.py:292-310`)

```latex
\textit{Regime A (con GT)}: w1\cdot acc\_links + w2\cdot(judge/5) + w3\cdot\cosine,
\quad
\textit{Regime B (senza GT)}: w1\cdot acc\_links + w2\cdot(judge/5)
```
Pesi di default: Regime A 0.50/0.30/0.20, Regime B 0.65/0.35 (`:513-514`). Se un
componente è N/A, i pesi si ridistribuiscono proporzionalmente sui componenti
disponibili (`:230-233`, `RUOLO_COMPOSITO` / `RUOLO_BINARIA`). L'indice non è
un'accuratezza: la scala mescola 0-1 con 0-5 (`:102-108`). Bib: `@misc{chen2021humaneval` (arXiv:2107.03374, pass@k) per contesto benchmarking; `@misc{reimers2019sbert` (EMNLP 2019, sentenze embedding) per cosine.

### 8.5 Intervallo di Wilson (`evaluation_runner.py:224-237`)

```latex
\texttt{wilson\_ci(n, k, confidence=0.95)} =
\left(
\frac{p + z^2/(2n)}{1 + z^2/n} \mp
\frac{z}{1 + z^2/n}\sqrt{\frac{p(1-p)}{n} + \frac{z^2}{4n^2}}
\right)
\texttt{con } p = k/n,\; z = \Phi^{-1}((1+\text{confidence})/2)
```
Bib: `@techreport{jcgm100` (GUM 2008, 09-11-2026) per incertezza di misura; `@techreport{jcgm_gum5_2026` (GUM-5:2026, 09-11-2026) per aggiornamento moderno.

### 8.6 Bootstrap a livello di task (`evaluation_runner.py:213-250`)

```latex
\texttt{cluster\_bootstrap\_interval(pairs, resamples=2000, seed=20261104)} =
\texttt{percentile\_2.5-97.5}(E^*_b),\quad b=1..B
```
Unità di ricampionamento = cluster (task ID), non riga singola. Seed 20261104.
Ancora: `@misc{chen2021humaneval` per contesto pass@k; `@misc{zheng2023llmjudge` per
giudice LLM; `@misc{reimers2019sbert` per embeddings. `% IN VERIFICA` per bootstrap
formula classica non ancorata a queste chiavi.

### 8.7 McNemar appaiata / Newcombe (`paired_mcnemar`, `evaluation_runner.py:322-454`)

```latex
\chi^2 = \frac{(|b - c| - 1)^2}{b + c},\quad
\text{interval Newcombe per differenza proporzioni}
```
Applicato riducendo le coppie a una per task. `% IN VERIFICA` per formula
classica non ancorata a queste chiavi.

### 8.8 ECPC (energy-per-correct) (`evaluation_runner.py:706-800`)

```latex
\texttt{ECPC} = \frac{\sum E_{\text{eligible}}}{N_{\text{correct}}}
```
Denominatore = sole righe con `is_correct = 1`. `% IN VERIFICA` per formula
ulteriore di normalizzazione per fasi condizionate.

### 8.9 pass@k non parziale (`evaluation_schema.py:185-217`)

```latex
\texttt{pass@k\_unbiased} = \mathbb{E}_{x \sim \mathcal{D}} \left[ 1 - \prod_{i=1}^{k} (1 - p_i) \right]
```
Chen et al. formula per scomposizione non parziale. Bib: `@misc{chen2021humaneval` per
contesto pass@k.

## 9. Riferimenti scientifici per ogni scelta

Le voci bibliografiche contrassegnate `% VERIFICATO` in `references.bib` sono quelle
ufficialmente verificate alla fonte primaria; le voci `% IN VERIFICA` sono citate
come letteratura ma non possono essere usate come evidenza metrologica.

| Scelta metodologica | Chiave bib | Data verifica | Ruolo |
|---|---|---|---|
| Tolleranza comparativa numerica | `@article{jallouli2026methodology` | 09-11-2026 | Metodologia incertezza su dispositivi eterogenei; `% IN VERIFICA` per uso rigoroso |
| Soglia semantica 0.75 | `@inproceedings{reimers2019sbert` | 20-10-2026 | Sentence-BERT (EMNLP 2019), embeddings per similarità semantica; `% VERIFICATO` |
| Soglia giudice 4.0 | `@inproceedings{zheng2023llmjudge` | STRUTTURA.md:28 (arXiv 2306.05685) | NeurIPS 2023 D&B; `% VERIFICATO` per MT-Bench/Chatbot Arena |
| Gate fail-closed | `@misc{tan2024judgebench` | 11-11-2026 | JudgeBench (arXiv:2410.12784); `% VERIFICATO` per benchmark giudici |
| Bias giudice | `@misc{park2024offsetbias` | 11-11-2026 | OffsetBias/EvalBiasBench (arXiv:2407.06551); `% VERIFICATO` per meta-benchmark |
| Quantificazione bias | `@misc{ye2024justice` | 11-11-2026 | Justice or Prejudice? (arXiv:2410.02736, ICLR 2025); `% VERIFICATO` |
| ECPC = E/N_correct | `@misc{saadfalcon2025ipw` | 11-11-2026 | Intelligence per Watt (arXiv:2511.07885); `% VERIFICATO` per IPW |
| pass@k unbiased | `@misc{chen2021humaneval` | 11-11-2026 | HumanEval (arXiv:2107.03374); `% VERIFICATO` per formula pass@k |
| Cosine embeddings | `@inproceedings{reimers2019sbert` | 20-10-2026 | SBERT (EMNLP 2019); `% VERIFICATO` |
| Intervallo Wilson | `@techreport{jcgm100` | 09-11-2026 | GUM 2008 (JCGM 100:2008); `% VERIFICATO` per incertezza di misura |
| Aggiornamento GUM | `@techreport{jcgm_gum5_2026` | 09-11-2026 | GUM-5:2026; `% VERIFICATO` per applicazione moderna |

**Voci IN VERIFICA** (non citabili come evidenza metrologica):
- `@misc{jcgm_gum5_2026` — aggiornamento 2026, non ancora verificato alla fonte primaria;
- `% IN VERIFICA` per bootstrap formula classica non ancorata a queste chiavi;
- `% IN VERIFICA` per ECPC formula ulteriore di normalizzazione per fasi condizionate.

Le voci `@misc{chen2021humaneval` e `@inproceedings{reimers2019sbert` sono citate come
letteratura (contesto pass@k e embeddings), non come evidenza metrologica.

## 10. Esito dei test

Test di regressione eseguiti il **2026-11-13** (raccolta misurata con
`pytest --collect-only -q` per file), sulla branch
`fix/p44-metrologico-20261109`:

| Test suite | N. test (collect) | Esito (run) |
|---|---|---|
| `tests/test_paired_mcnemar.py` | 13 | passati |
| `tests/test_evaluator_judge_gate.py` | 7 | passati |
| `tests/test_human_calibration_gate.py` | 82 | passati |
| `tests/test_ecpc_corrections.py` | 17 | passati |
| `test_answer_type_evaluation.py` (root) | 168 | passati |
| `test_evaluation_runner.py` (root) | 23 | passati |
| `test_mudilab_adapter.py` (root) | 26 | passati |
| `test_robust_evaluator.py` (root) | 59 | passati |
| `test_validazione_valutazione.py` (root) | 22 | passati |
| `test_tool_provenance.py` (root) | 8 | passati |
| `test_synthetic_window.py` (root) | 2 | passati |
| **Totale** | **427** | **427 passati** |

**Esito**: `427 passed, 0 failed, 0 skipped` in 4.83s (command: `pytest
tests/test_paired_mcnemar.py tests/test_evaluator_judge_gate.py
tests/test_human_calibration_gate.py tests/test_ecpc_corrections.py
test_answer_type_evaluation.py test_evaluation_runner.py
test_mudilab_adapter.py test_robust_evaluator.py
test_validazione_valutazione.py test_tool_provenance.py
test_synthetic_window.py -q` dalla cartella `cwEnergyModular/`).

**Copertura delle docstring**: misurata con AST 427/427 (100%).
**Nessun warning di deprecation**: 0.

---

*Relazione aggiornata il 2026-11-13. Ancoraggi `file:riga` verificati sul codice
di produzione; riferimenti bibliografici con stato `% VERIFICATO` o `% IN VERIFICA`
come da `references.bib`.*
