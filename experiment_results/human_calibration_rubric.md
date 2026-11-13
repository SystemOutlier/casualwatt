# Rubrica di Annotazione Umana per la Validazione dello Scoring — CasualWatt Fase 0

**Versione:** 2.0  
**Data:** 2026-11-11  
**Ancoraggi riverificati:** 2026-11-12 sul codice corrente. Le coordinate di riga citate dalla versione 2.0 erano stantie per la crescita di `human_calibration_gate.py` e `evaluation_runner.py` (Fase 4 della revisione correttiva): sono state corrette le coordinate, non i comportamenti che descrivono. Due nomi di campo inesistenti (`experiment_scoring_coverage`, `experiment_accuracy_covered`) sono stati riportati ai campi reali del runner (`scoring_coverage`, `verdict_accuracy_covered`).  
**Protocollo:** `human_calibration_protocol.json` (versione 2.0, pre-registrato)  
**Sostituisce:** la versione 1.0, che prescriveva un α ordinale (`Correct > Indeterminate > Incorrect`) e un gate unico α ≥ 0.8: difforme dalle correzioni 1 e 2 della specifica e dal codice `human_calibration_gate.py`.

---

## Scopo: due verifiche distinte

Questa rubrica governa la produzione del riferimento umano di correttezza. Il riferimento serve a due verifiche **non intercambiabili**:

- **Verifica A — Affidabilità delle annotazioni umane:** accordo fra Annotatore 1 e Annotatore 2. Misura se il riferimento umano è stabile, NON se il giudice LLM è valido.
- **Verifica B — Validità del giudice LLM:** accordo fra il giudice e il riferimento umano consolidato dopo adjudication, su un campione indipendente. Misura se il giudice è accurato rispetto al riferimento.

Un buon accordo umano (α alto) **non dimostra** la validità del giudice: un giudice può sbagliare sistematicamente una classe anche quando gli annotatori umani concordano perfettamente. Le due verifiche restano separate anche nel report finale.

Il gate energetico (Gate 1, P4.9, `energy_chain_status`) è indipendente da questa rubrica: un'energia misurata correttamente non è invalidata perché il giudice non è calibrato.

---

## Istruzioni per gli Annotatori

1. **Cieca**: Non conoscete il modello che ha prodotto la risposta, né il suo consumo energetico, né il verdetto dell'LLM Judge.
2. **Indipendente**: Ogni annotatore valuta autonomamente senza consultarsi.
3. **Rubrica comune**: Usate esclusivamente le tre etichette sotto definite.
4. **Giustificazione**: Obbligatoria per ogni giudizio (max 200 caratteri).
5. **Adjudication**: In caso di disaccordo tra i due annotatori, un terzo valutatore cieco o una discussione di consensus risolve. **Un disaccordo senza adjudication NON produce un riferimento consolidato**: il giudice non può essere validato contro un riferimento che non esiste.

---

## Etichette e Definizioni

| Etichetta | Significato | Quando usare |
|-----------|-------------|--------------|
| **Correct** | Risposta sostanzialmente corretta | La risposta risponde accuratamente alla query rispetto alla ground truth / criteri dichiarati. Piccole imprecisioni lessicali non penalizzano se il contenuto fattuale è corretto. |
| **Incorrect** | Risposta errata | La risposta contiene errori fattuali, contraddice la ground truth, o non risponde alla domanda posta. |
| **Indeterminate** | Non stabilibile con certezza | La risposta è ambigua, incompleta, la ground truth è insufficiente, o il criterio di correttezza non è definibile. **Non** usare come "non so" — solo quando oggettivamente indeterminabile. |

**Livello di misura: nominale.** Le tre etichette sono categoriali nominali. `Indeterminate` NON è un livello intermedio fra `Correct` e `Incorrect`: è un esito non determinabile. Nessuna gerarchia ordinale `Correct > Indeterminate > Incorrect` è ammessa (specifica, correzione 2); il codice solleva `ValueError` se si tenta un α non nominale (`human_calibration_gate.py:104-110`).

**Normalizzazione nel riferimento consolidato.** La rubrica usa le etichette con iniziale maiuscola per leggibilità. Nell'artefatto consolidato canonico le etichette sono registrate in minuscolo (`correct`, `incorrect`, `indeterminate`), come atteso dal gate (`_LABELS = ("correct", "incorrect")`, `human_calibration_gate.py:53`). Solo `correct` e `incorrect` producono un riferimento utilizzabile; `indeterminate` (anche quando entrambi gli annotatori concordano) NON produce riferimento e conta come astensione.

---

## Criteri per Strato

### Strato: `number` (14 item)
- **Ground truth**: Valore numerico finito (es. `21`, `3.14`, `1.5 kg`, `42%`)
- **Criterio (valutatore primario)**: questo strato segue il valutatore **primario** `evaluator.py::compare_numbers` (92-107), NON il valutatore robusto secondario. Tolleranza `1e-6`; le quantità devono essere finite e dimensionalmente compatibili, e percentuali e simboli SI sono convertiti prima del confronto. Il confronto è:
  - **GT ≠ 0**: differenza relativa `|risposta − GT| / |GT| < 1e-6`.
  - **GT = 0**: valore assoluto della risposta `|risposta| < 1e-6` (trattamento speciale: per GT nulla la differenza relativa non è definita, quindi si usa la soglia assoluta).
  Non si applica la combinazione `absolute_tolerance 1e-9 + relative_tolerance 1e-6` del valutatore robusto secondario (`robust_evaluator.py:267-268`): quei parametri non appartengono al primario e non vanno trasferiti.
- **Correct**: Numero estratto matcha GT secondo il criterio qui sopra
- **Incorrect**: Numero estratto fuori tolleranza o assente quando atteso
- **Indeterminate**: Risposta senza numero parsabile, GT non numerica valida

### Strato: `short_text` (13 item)
- **Ground truth**: Testo breve ≤ 6 parole (es. nomi, capitali, definizioni concise)
- **Criterio**: Contenimento normalizzato (minuscole, no accenti, no punteggiatura, no articoli) — GT normalizzata deve essere contenuta come parola/frase intera nella risposta normalizzata
- **Correct**: Almeno una alternativa GT normalizzata contenuta in risposta normalizzata
- **Incorrect**: Nessuna alternativa GT contenuta
- **Indeterminate**: GT vuota/non normalizzabile, risposta vuota

### Strato: `free_text` (13 item)
- **Ground truth**: Risposta aperta, ragionamento, spiegazione (es. "Perché il cielo è blu?")
- **Criterio**: Giudizio olistico su correttezza fattuale, completezza, coerenza. **Non** matching lessicale.
- **Correct**: Risposta factualmente corretta, completa per l'essenziale, coerente
- **Incorrect**: Errori fattuali, omissioni gravi, contraddizioni interne
- **Indeterminate**: Risposta troppo vaga, ground truth ambigua, criterio non applicabile

---

## Formato Output

### Record per annotatore (cieco)

Ogni annotatore produce, per item, un'etichetta e una giustificazione, senza consultare l'altro annotatore né conoscere modello/energia/giudice. File di lavoro: `human_calibration_annotations_<annotator_id>.jsonl`.

```json
{
  "task_id": "CAL_001",
  "answer_type": "number",
  "verdict": "Correct",
  "justification": "Risposta contiene 21, calcolo corretto mostrato",
  "annotator_id": "A1",
  "timestamp": "2026-11-11T10:00:00Z"
}
```

Il contesto di giudizio (prompt/query, `expected`/ground truth, `model_response`) è fornito dall'item del campione: l'annotatore vede il contenuto, non l'identità del modello.

### Artefatto consolidato canonico (consumato dal gate)

Lo schema canonico è quello del template del gate (`human_calibration_gate.py::calibration_sample_template`, 1162-1183). Le due etichette cieche confluiscono in `annotations`, l'adjudication del disaccordo in `adjudicated`:

```json
{
  "task_id": "CAL_001",
  "category": "",
  "answer_type": "number",
  "model_response": "",
  "expected": "",
  "response_typology": "",
  "annotations": {
    "annotator_1": "correct",
    "annotator_2": "correct"
  },
  "adjudicated": ""
}
```

- `answer_type` è il ramo (`number`, `short_text`, `free_text`) letto dalla Verifica A (`:272`) e dalla Verifica B (`:572`).
- `annotations.annotator_1` / `annotator_2` sono le etichette cieche normalizzate in minuscolo, lette dalla Verifica A (`:289-290`) e dal consolidamento del riferimento (`adjudicated_reference`, `:378-379`).
- `adjudicated` è l'etichetta del terzo revisore per i disaccordi, letta dal consolidamento (`adjudicated_reference`, `:392`); vuota se non serve.
- `response_typology` registra la tipologia di risposta (corretta, scorretta, errore parziale, informazione superflua, convincente-ma-errata, ambigua, famiglia di modelli), non solo le due etichette.
- Le giustificazioni e la provenienza (`annotator_id`, `timestamp`) sono conservate nei record per annotatore per audit; il template canonico registra le etichette consolidate.

### Campione sintetico vs campione reale

Il file `human_calibration_sample.jsonl` attuale (40 item, schema `item_id`/`stratum`/`query`/`ground_truth`/`model_response`/`difficulty`/`expected_verdict`) è una **fixture sintetica**: le etichette `expected_verdict` sono preassegnate, NON sono annotazioni umane indipendenti e cieche, e lo schema diverge da quello canonico. Serve solo a verificare l'infrastruttura.

**`expected_verdict` NON deve essere trasformato automaticamente in `adjudicated`**: un'etichetta preassegnata non equivale a un giudizio umano indipendente. Il campione destinato alla vera calibrazione va preparato e annotato secondo lo schema canonico, conservando provenienza e cecità delle annotazioni.

---

## Esempi di Calibrazione

| Query | Ground Truth | Model Response | Verdetto | Giustificazione |
|-------|--------------|----------------|----------|-----------------|
| Quanto fa 5*5-4? | 21 | "25-4=21" | **Correct** | Numero corretto estratto |
| Quanto fa 5*5-4? | 21 | "20" | **Incorrect** | Errore aritmetico |
| Capitale Australia? | Canberra | "Sydney" | **Incorrect** | Fatto errato |
| Capitale Australia? | Canberra | "Canberra è la capitale" | **Correct** | Contenimento normalizzato |
| Perché il cielo è blu? | Scattering Rayleigh | "Per lo scattering della luce" | **Correct** | Corretto fattualmente |
| Perché il cielo è blu? | Scattering Rayleigh | "Per l'oceano" | **Incorrect** | Fatto errato |
| Spiega la relatività | (complessa) | "E=mc²" | **Indeterminate** | Incompleta, non valuta correttezza |
| Opinione su clima | (soggettiva) | "Penso che..." | **Indeterminate** | Nessun criterio oggettivo |

---

## Checklist Pre-Annotazione

- [ ] Protocollo `human_calibration_protocol.json` (v2.0) congelato e committato PRIMA dell'annotazione.
- [ ] Registrazione del congelamento nel manifest successivo `fase0_manifest.json` (`protocol_path`, `protocol_blob_sha1`, `freeze_commit_sha1`, `freeze_date`): il protocollo NON contiene il proprio hash di commit (dipendenza circolare). Il manifest è creato solo al congelamento della versione definitiva, non in questa fase.
- [ ] Campione REALE secondo lo schema canonico preparato (il `human_calibration_sample.jsonl` attuale è una fixture sintetica, non il campione di calibrazione).
- [ ] Criteri di accettazione della Verifica B preregistrati (non `null`) prima di vedere i dati.
- [ ] Due annotatori identificati (A1, A2), ciechi a modello/energia/giudice.
- [ ] Rubrica letta e compresa da entrambi.
- [ ] Terzo adjudicator cieco identificato per i disaccordi.
- [ ] Timestamp e giustificazioni delle annotazioni registrati.

---

## Post-Annotazione

### Verifica A — Affidabilità delle annotazioni umane

Confronto: `annotator_1` vs `annotator_2`, per ramo. Producer: `human_calibration_gate.py::verifica_a` (231-357).

Metriche prescritte dalla specifica:
- **Krippendorff's α nominale** (primaria): le etichette sono categoriali, nessuna scala ordinale. Il gate calcola solo α nominale e solleva `ValueError` su un livello diverso (`:104-110`).
- **Cohen's κ nominale** (complementare): prescritto dalla specifica (correzione 2), **ora prodotto dal gate** (`cohen_kappa_nominal`, `:180-209`; esposto in `StratumAgreement.kappa_nominal`, `:220`, con la ragione di non calcolabilità in `kappa_reason`, `:221`). Metrica riportata, NON criterio: non modifica `passed`, che resta determinato dalla soglia su α (Opzione 1). `None` se le coppie pairable sono meno di due o se `p_e = 1` (una sola classe nominale, nessuna variabilità attesa dal caso); il valore non è clampato. Il gap metrico è chiuso.
- **Pavimento di numerosità** (preregistrato, `MIN_PAIRABLE_ITEMS = 3`, `human_calibration_gate.py:73`): sotto 3 coppie pairable lo strato **non passa** con ragione `insufficient_data` (`:336-339`). Le metriche restano riportate — un α = 1,0 su due item è un dato vero, non un verdetto — e α sotto soglia continua a chiamarsi `human_agreement_failed`: il pavimento dice "non c'è campione", la soglia dice "il campione non concorda", e le due cause non si collassano. Fail-closed: può solo abbassare uno stato, mai alzarlo.
- **Pavimento sulla frazione ammissibile** (preregistrato, `MIN_ADMISSIBLE_FRACTION = 0.5`, `human_calibration_gate.py:75-84`): se le coppie pairable sono meno della metà dei record attribuiti allo strato, lo strato **non passa** con ragione `insufficient_data` anche con α sopra soglia (`:340-345`). I denominatori del gate sono sempre il sottoinsieme ammissibile — un record difettoso non si converte — quindi senza questo pavimento un campione con 27 record esclusi su 30 e 3 superstiti in accordo perfetto sarebbe passato: le metriche sui superstiti descrivono il residuo delle esclusioni, non il campione. Lo stesso pavimento vale per le due sequenze (record fuori dagli strati), dove nessun denominatore di strato li vedrebbe (`run_scoring_validation_gate`, `:907-909`). Fail-closed: può solo abbassare uno stato, mai alzarlo.
- **Percent agreement**, **distribuzione delle classi**, **matrice di confusione** fra annotatori.

Metriche prodotte dal gate: `alpha_nominal`, `alpha_ci_95`, `kappa_nominal` (con `kappa_reason`), `percent_agreement`, `disagreements`, `class_distribution`, `n_items`/`n_pairable` per ramo. La matrice di confusione fra annotatori è coperta in forma parziale da `disagreements` (conteggi `a1->a2`) e `class_distribution` (margini dell'annotatore 1), non come matrice nominale completa: da dichiarare parziale, non come gap bloccante.

Intervallo di confidenza: bootstrap percentile 2.5-97.5 a livello di item (la coppia di etichette viaggia insieme, l'unità di ricampiono è l'item), seed `20261104`, 2000 ricampioni (`evaluation_runner.py:25-26`).

**Soglia α ≥ 0.8**: condizione NECESSARIA per usare il riferimento umano come gold standard, NON criterio sufficiente per abilitare il giudice. Con classi sbilanciate un coefficiente alto può mascherare errori sistematici sulla classe rara: la distribuzione delle classi va sempre riportata.

Output: `human_calibration_agreement_report.json`.

### Verifica B — Validità del giudice LLM

Confronto: `judge_verdict` vs riferimento umano adjudicato, su campione INDIPENDENTE. Producer: `human_calibration_gate.py::verifica_b` (515-680).

Riferimento consolidato (`adjudicated_reference`, 360-408): etichetta concorde `correct`/`incorrect`, oppure `adjudicated` per i disaccordi. Un disaccordo senza adjudication NON produce riferimento ed è contato.

Indipendenza: nessuna sovrapposizione di `task_id` col campione di calibrazione; una sovrapposizione è un errore dichiarato (`ValueError`), non un'avvertenza (`run_scoring_validation_gate`, :858-863).

Criteri di accettazione preregistrati (fail-closed): `min_precision_correct`, `min_recall_correct`, `max_fp_rate`, `min_accuracy`, `min_coverage`. Tutti `null` finché non registrati → gate non eseguibile (`JudgeAcceptanceCriteria`, 416-450). Nessuna soglia inventata al momento: i valori definitivi si fissano prima dei dati. Regola di igiene della preregistrazione: `min_coverage` non va fissato a 0 (né a un valore che renda la coverage non vincolante), perché una soglia a zero trasforma il criterio in una tautologia — con 27 astensioni su 30 e `min_coverage = 0` il ramo resta `validated`, ed è un limite dichiarato, non un difetto chiuso dal pavimento sulla frazione ammissibile.

Metriche prescritte dalla specifica (riga 19, Validità del giudice): accuracy, precision per classe, recall per classe, **F1 per classe**, falsi positivi, falsi negativi, tasso di astensione. La matrice di confusione **non** è un requisito letterale aggiuntivo per la Verifica B: è la rappresentazione degli stessi conteggi FP/FN/astensioni (`confusion` inizializzata a `human_calibration_gate.py:588-589` e incrementata a `:600`), non un requisito oltre quelli prescritti. Per la Verifica A (riga 18) la matrice di confusione è invece requisito letterale.

Metriche prodotte dal gate: `confusion` (`confusion[reference][correct|incorrect|abstained]`), `accuracy` (sui soli decisi), `precision_correct`/`recall_correct`, `precision_incorrect`/`recall_incorrect`, `f1_correct`/`f1_incorrect` (con `f1_reason`), `fp_rate = IC/(IC+II)`, `abstention_rate`, `coverage`, intervalli di Wilson. **F1 per classe è ora prodotto dal gate** (`_f1`, `:470-482`; esposto in `JudgeValidity.f1_correct`/`f1_incorrect`, `:500-501`): `F1 = 2·P·R/(P+R)` dalle precision/recall già calcolate, senza toccarne i denominatori. Metrica riportata, NON criterio: non modifica `passed` né `failed_criteria` (Opzione 1). `None` se precision o recall non sono definite o se `P+R = 0` (classe senza veri positivi). Le classi sono solo {correct, incorrect}: un riferimento indeterminate è escluso e un verdetto indeterminate del giudice è un'astensione, non una classe. Il gap metrico è chiuso.

**Pavimento di numerosità** (preregistrato, `MIN_DECIDED_ITEMS = 3`, `human_calibration_gate.py:74`): sotto 3 verdetti decisi le metriche sono calcolabili ma non giudicabili, e il solo criterio fallito è `insufficient_numerosity` (`:636`) — un `fp_rate` assente su un item solo non è assenza di falsi positivi, è assenza di casi. Le metriche non vengono giudicate su un campione che non le supporta.

**Pavimento sulla frazione ammissibile** (preregistrato, `MIN_ADMISSIBLE_FRACTION = 0.5`, `human_calibration_gate.py:75-84`): se gli item con riferimento adjudicato utilizzabile sono meno della metà dei record attribuiti allo strato (`n_records_in_stratum`, esposto in `JudgeValidity` a `:490` per ricostruire la frazione), lo strato **non passa** e il criterio fallito è `insufficient_admissible_fraction` (`:638`), in `failed_criteria` accanto a `insufficient_numerosity` quando entrambi i pavimenti aprono. Chiude l'esposizione simmetrica a quella di Verifica A: senza di esso, 6 record su 10 con riferimento inutilizzabile (`"forse"`, etichetta fuori vocabolario) e 4 superstiti giudicati perfetti avrebbero prodotto `validated`. Le frazioni delle due sequenze sono esposte in `ScoringValidationGateResult.admissible_fractions` (`:702`), con la guardia sulle sequenze a `run_scoring_validation_gate:907-909`. Fail-closed: può solo abbassare uno stato, mai alzarlo.

**I pavimenti non sono una garanzia di potenza.** I tre pavimenti preregistrati (`min_pairable_items`, `min_decided_items`, `min_admissible_fraction`) sono condizioni tecniche minime fail-closed: impediscono di accettare campioni troppo piccoli, non dimostrano che tre osservazioni bastino a una stima scientificamente affidabile. Con `n = 3` non si stima una varianza (P4.12) e la potenza resta una proprietà del disegno, dichiarata separatamente — il template del gate la nomina esplicitamente (l'intervallo bootstrap di α dice quanto pesa la numerosità, `human_calibration_gate.py:1084`), e un pilota con numerosità insufficiente si chiude raccogliendo un campione aggiuntivo prima di congelare i criteri, non spostando la soglia.

Falsi positivi: `fp_rate` esplicito più il conteggio IC nella matrice. Falsi negativi: conteggio CI nella matrice; il tasso FN non è un campo nominato ma è derivabile da `recall_correct` (FN rate = 1 − recall_correct). Il tasso di falsi positivi è il danno principale a ECPC: un giudice che promuove risposte errate gonfia il numeratore di corrette; la sola accuratezza non lo vede.

**Due coverage, due accuracy (non intercambiabili).** Le grandezze della Verifica B non vanno confuse con quelle dell'esperimento: hanno numeratore, denominatore e popolazione diversi.

- `judge_decision_coverage` = `n_decided/n_items` = 1 − `abstention_rate` (`human_calibration_gate.py:615`): quota del campione **indipendente di validazione** su cui il giudice produce un verdetto deciso. Il criterio `min_coverage` soglia **questa** (`:660-661`), non la coverage d'esperimento.
- `scoring_coverage` = #{is_correct ≠ null}/N (`evaluation_runner.py:805`, esposta per categoria a `:864` e in forma aggregata come `verdict_coverage` a `:925`): quota di righe dell'**esperimento** con giudizio binario disponibile (correzione 4 della specifica). È un'altra grandezza, su un'altra popolazione.
- `judge_accuracy` = (CC+II)/`n_decided` (`human_calibration_gate.py:608`): accuratezza del giudice sui soli verdetti decisi contro il riferimento adjudicato. Il criterio `min_accuracy` soglia **questa** (`:658-659`).
- `verdict_accuracy_covered` = #{is_correct = true}/#{is_correct ≠ null} (`evaluation_runner.py:926`): accuratezza dell'esperimento condizionata agli item determinati. Distinta dalla `judge_accuracy`.

Output: `human_calibration_judge_comparison.json`.

### Gate di scoring (Gate 2) e stato integrato (Gate 3)

- Un ramo è `validated` solo se **Verifica A supera la soglia E Verifica B supera i criteri preregistrati**. Il token software `validated` (`run_scoring_validation_gate`, `:932-933`) certifica questo, **NON** il completamento scientifico della procedura: Cohen's κ nominale (Verifica A) e F1 per classe (Verifica B) sono ora prodotti dal gate come metriche riportate, ma il token `validated` non dipende dalla loro disponibilità. Un ramo `validated` resta scientificamente incompleto finché `kappa_nominal`, `f1_correct` e `f1_incorrect` non sono disponibili (non-`None`) per quel ramo. `validated` è condizione necessaria, non sufficiente, per dichiarare completa la validazione. Il token non è prodotto quando un pavimento preregistrato apre — numerosità o frazione ammissibile, su ramo o su sequenza — e in quel caso nessun ramo è promosso, qualunque siano le metriche sui superstiti.
- `scoring_status` per ramo: `validated`, `human_agreement_failed`, `criteria_not_registered`, `insufficient_data`, `judge_uncalibrated` (`run_scoring_validation_gate`, 795-1029). Un ramo bloccato non blocca gli altri. `insufficient_data` e `human_agreement_failed` non sono la stessa causa: `insufficient_data` dice che il campione non basta per un verdetto (sotto i pavimenti preregistrati, frazione ammissibile sotto pavimento su un ramo o su una sequenza, o nessun item nello strato), `human_agreement_failed` dice che il campione c'è e gli annotatori non concordano (α sotto soglia, `:918-925`).
- Gate 1 (`energy_chain_status`, P4.9) è indipendente: non è toccato dalla calibrazione del giudice. Un ramo `judge_uncalibrated` resta non valutato (`is_correct = None`), mai `incorrect`.
- Gate 3 (`experiment_status`, `integrate_experiment_status`, 1031-1045) combina `energy_chain_status` e `scoring_status` senza cancellare l'informazione originaria (es. energia `validated`, scoring `partially_validated` → esperimento `partially_validated`).
- Gli indicatori ECPC (`ecpc_value`, `ecpc_status`, `ecpc_verified`, `scoring_coverage`, `verdict_accuracy_covered`) appartengono alla **fase successiva di analisi**, non a questa rubrica di Fase 0: sono definiti nel runner (`evaluation_runner.py:798` `ecpc_verified`, `:808-813` `ecpc_status`, esposti per categoria a `:852` e `:862`, con `scoring_coverage` a `:805`/`:864` e `verdict_accuracy_covered` a `:926`). Un `ecpc_status = partial` non è definitivo: l'energia degli item `unscored` resta nel numeratore ma non nel denominatore.

### Diagnostica dei difetti

Il gate non si limita a non produrre un numero falso: dice **perché** non può produrlo. Sei categorie distinte e non intercambiabili — `ok`, `insufficient_data`, `invalid_schema`, `invalid_label`, `missing_annotation`, `unscored` (`DIAGNOSTIC_CODES`, `human_calibration_gate.py:63-64`). Un record difettoso è escluso dal calcolo e contato, mai convertito e mai promosso; le maiuscole non vengono normalizzate in minuscolo.

**`insufficient_data` è il quinto codice, e non si confonde con `unscored`.** `insufficient_data` conta record corretti ma troppo pochi per un verdetto (sotto un pavimento preregistrato); `unscored` conta record per cui il confronto non esiste — riferimento umano non producibile (disaccordo senza adjudication) o verdetto del giudice assente. Sono cause diverse su popolazioni diverse: il primo dice "il campione non basta", il secondo dice "il confronto non esiste". Confonderli trasformerebbe un campione troppo piccolo in un riferimento mancante e viceversa. `insufficient_data` compare inoltre a **due livelli**, che vanno tenuti distinti: (a) codice per-record nei dict `diagnostics` dei due rami, dove vale 1 se il ramo è sotto il pavimento di numerosità — un flag di ramo contato una volta, non un conteggio di record, e non compete con `ok` per gli stessi record, perché un record sotto pavimento ha comunque prodotto il confronto; (b) **stato di verdetto** dello strato in `scoring_status_per_stratum`, prodotto dai pavimenti preregistrati.

**Token di verdetto, non codici diagnostici.** `insufficient_numerosity` e `insufficient_admissible_fraction` non sono codici di `DIAGNOSTIC_CODES` e non entrano nei dict `diagnostics`: sono criteri di verdetto preregistrati — token di `failed_criteria` in Verifica B (`JudgeValidity`, `:511`) e ragione di mancato pass in Verifica A (`StratumAgreement.reason`, `:227`). Aggiungerli ai codici per-record li farebbe sembrare difetti del dato, mentre sono regole di giudizio sul campione.

**Regola di ricostruibilità: la causa di ogni esclusione è sempre ricostruibile dall'output del gate**, senza riaprire i dati. Per record, dai dict `diagnostics` di ramo (conteggio per causa, con la regola di prevalenza `invalid_schema` su `unscored`). Per ramo, da `StratumAgreement.reason`, `JudgeValidity.failed_criteria`, `JudgeValidity.n_records_in_stratum` (`:490`) e dalle frazioni esposte in `ScoringValidationGateResult.admissible_fractions` (`:702`). Per sequenza, da `n_calibration_items` e `n_validation_items` confrontati con la somma dei record attribuiti agli strati, più il dettaglio in `notes`. Un record escluso dal denominatore non scompare dal resoconto: il denominatore del verdetto è sempre il sottoinsieme ammissibile — un record difettoso non si converte — e la quota esclusa resta esposta accanto al verdetto che essa condiziona.

Regola di conteggio: **un record non viene contato due volte nella stessa categoria**. Le cause di sequenza — riga non-oggetto, `answer_type` assente o fuori dagli strati misurati, riferimento non costruito dal gate — non appartengono ad alcuno strato, quindi il loro conteggio autorevole è a livello di gate e non la somma dei rami: con tre rami un solo record sembrerebbe tre difetti. Le cause di sequenza sono mutuamente esclusive, con precedenza `invalid_schema` su `unscored`. Le cause di contenuto (`invalid_label`, `missing_annotation`) possono invece toccare lo stesso record, perché sono fatti distinti. Nel dict di un ramo, `unscored` conta due cause attribuibili a quel ramo — verdetto del giudice assente e riferimento che il record stesso dichiara inutilizzabile — mentre un riferimento non allegato è contato una volta dal gate (`verifica_b`, `:577-580`; `run_scoring_validation_gate`, `:899-901`).

### Regola di completamento

I due gap metrici — **Cohen's κ nominale** (Verifica A) e **F1 per classe** (Verifica B) — sono ora chiusi sul lato implementazione: il gate li produce come metriche riportate (Opzione 1). La validazione NON può essere dichiarata completa finché `kappa_nominal`, `f1_correct` e `f1_incorrect` non sono **disponibili** (non-`None`) per il ramo, oltre al token `validated`: la loro disponibilità è condizione necessaria aggiuntiva per il completamento scientifico, ma non modifica il pass/fail di `validated`. Una calibrazione a classe sola (κ `None`, `p_e = 1`) o una validazione senza una classe (F1 `None` per la classe non testata) lascia il ramo scientificamente incompleto anche se `validated`. Verifica A e Verifica B restano distinte anche nel report finale: un buon accordo umano non dimostra la validità del giudice, e un giudice non è affidabile solo perché supera una soglia di accordo umano.