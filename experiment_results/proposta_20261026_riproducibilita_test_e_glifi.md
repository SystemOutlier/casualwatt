# Proposta circoscritta — riproducibilità della suite e leggibilità dei glifi in Appendice D

Data: 2026-10-26. Branch: `fix/cpu-attribution`.
Stato: **proposta, non implementazione.** Nessun file di codice né di tesi è stato modificato per scrivere questo documento; nessuna esecuzione hardware, nessun `powercfg`, nessun pilota o pre-pilota; la banda di concordanza P6.6 (#70) non è toccata; P1.6 e P2.9 restano aperte e qui non viene scelta nessuna delle due.

Le prove citate sono state eseguite su questa macchina il 26/10/2026 e sono rigenerabili con i comandi in fondo.

---

## 1. Che cosa è stato verificato oggi (fatti, non stime)

### 1.1 La suite come raccolta e la suite come clone

| quantità | valore | come è stata misurata |
|---|---|---|
| node id raccolti dal working tree | **294** | `pytest --collect-only -q` in `cwEnergyModular/` |
| esito | **291 passati + 3 saltati** | `pytest cwEnergyModular` dalla radice: `291 passed, 3 skipped in 7.89s` (riesecuzione di controllo; l'esecuzione trascritta in Appendice D è la stessa contata in 8,43 s dal generatore) |
| node id raccolti da un clone pulito di `HEAD` | **168** | `git archive HEAD \| tar -x` in directory temporanea, poi `pytest --collect-only -q .`: 168 raccolti, **nessun errore di raccolta** |
| scarto | **126** | di cui **114** da 11 moduli di test non tracciati e **12** dalla crescita non committata di `tests/test_dump_node_id.py` (21 in `HEAD`, 33 nel working tree) |

Confronto file per file fra clone e working tree: tutti gli altri 14 moduli tracciati hanno lo stesso numero di node id (`test_answer_type_evaluation.py` 35, `test_energy_corrections.py` 19, `test_metodo_per_riga.py` 11, `test_cpu_share_window.py` 4, ecc.). Quindi le modifiche non committate agli altri 3 test tracciati **non** cambiano il conteggio: cambiano i corpi.

### 1.2 Gli undici moduli non tracciati, con il loro peso

`tests/test_baseline_ordine_v4.py` 18 · `tests/test_terminazione_v4.py` 28 · `tests/test_cooldown_v4.py` 25 · `tests/test_judge_edge_capture.py` 16 · `tests/test_block_baseline.py` 5 · `tests/test_measurement_edge.py` 5 · `tests/test_shared_components_v4.py` 5 · `tests/test_csv_schema_p5.py` 4 · `tests/test_busy_single_read.py` 3 · `tests/test_tree_change_invalidates_share.py` 3 · `tests/test_edge_window.py` 2. Somma **114**.

### 1.3 La dipendenza che decide l'ordine delle operazioni

Sei di quegli undici importano `benchmark_v4`: `test_baseline_ordine_v4`, `test_block_baseline`, `test_cooldown_v4`, `test_judge_edge_capture`, `test_shared_components_v4`, `test_terminazione_v4` — **97 dei 114 node id**. E `benchmark_v4.py` non è tracciato.
Due verifiche che tengono insieme il quadro:

- nessun test **tracciato** importa un modulo non tracciato — è il motivo per cui il clone raccoglie 168 senza errori (verificato eseguendo la raccolta nel clone, non leggendo i soli sorgenti);
- nessun test legge `.casualwatt_keys.json` (`grep` su `tests/` e sui test alla radice: nessuna occorrenza), quindi il file delle chiavi non è un fattore di riproducibilità della suite e non viene toccato.

Corollario operativo: **versionare quei sei moduli senza versionare `benchmark_v4.py` rotta la raccolta del clone.** I due atti sono uno solo, per lo scopo, anche se resteranno commit separati.

### 1.4 Che cosa è già tracciato e funziona

`cwEnergyModular/conftest.py` ✓ · `cwEnergyModular/tools/dump_tests_latex.py` ✓ (ma con le correzioni del 26/10 non committate) · `tools/dump_experiments_latex.py` ✓ · `tools/dump_schema_latex.py` ✓ · `experiment_additivity.py` ✓. Il generatore importa `_LATINA`, `fuori_latino`, `tex_escape` da `dump_tests_latex` (`tools/dump_experiments_latex.py:52`), quindi **una sola modifica ai glifi si riverbera su Appendice D ed E.**

---

## 2. I tre buchi di riproducibilità sono tre buchi diversi

Non vanno confusi, perché si chiudono con atti diversi.

**(G1) File non versionati** — gli 11 moduli di §1.2 e il runner `benchmark_v4.py`. Un clone non può nemmeno *vedere* 114 dei node id che l'Appendice D stampa. È il caso che la revisione ha chiamato "un clone non riproduce la suite documentata": è vero, e il numero esatto è 126 su 294 (42,9%).

**(G2) Modifiche non committate a file versionati** — `tools/dump_tests_latex.py` (la correzione del parser dei node id con lo spazio, `:207-215` e `:223-224`), `tests/test_dump_node_id.py` (+12 node id), `tests/test_cpu_share_window.py`, `tests/test_energy_corrections.py`, `tests/test_metodo_per_riga.py`. Un clone di `HEAD` rigenera **un'appendice diversa da quella stampata nella tesi**, con un generatore che ha ancora il difetto dei node id con lo spazio: 168 righe e quattro righe `n/eseguito`.

**(G3) Procedura di rigenero non scritta** — il comando esatto con il redirect dell'output non sta da nessuna parte: `AGENTS.md` nomina il generatore ma non dice dove scrive, e il generatore stampa su stdout (`tools/dump_tests_latex.py:459-461`, nessun argomento di output).

---

## 3. Proposta A — chiudere G1 e G2 (richiede autorizzazione, non è decisione di metodo)

Tre opzioni con i loro numeri. **Non ho eseguito nessun `git add` e nessun commit.**

**A1 — versionare il blocco P5 completo (raccomandata).** `benchmark_v4.py` + gli 11 moduli + le 5 modifiche a file già tracciati. Effetto misurabile: il clone passa da 168 a **294** raccolti. Costa: rende durevole il runner v4 mentre P5 non è congelato (#42 aperto) — ma il runner esiste già, è autorizzato, e il suo stato corrente contiene la dichiarazione di discordanza su P1.6 (`benchmark_v4.py:1048-1061`), che è precisamente ciò che una versione dovrebbe congelare: non una soluzione silenziosa, ma il problema scritto.

**A2 — congelare P5 prima di versionare.** Semantica più pulita, ma P1.6 (ritentativo della finestra) e P2.9 (forma del budget) **riguardano l'esecutore del blocco**: congelare il runner con P1.6 non risolta congela la lettura oggi nel codice — invalidare il blocco alla prima occorrenza — invece di lasciarla aperta come il protocollo chiede. Sconsigliata come ordine, non come esito.

**A3 — versionare solo i 5 moduli che non dipendono dal runner** (`busy_single_read`, `csv_schema_p5`, `edge_window`, `measurement_edge`, `tree_change_invalidates_share` = 17 node id). Il clone arriverebbe a 197 raccolti su 294 stampati: chiude un sesto del buco e rende la situazione più difficile da leggere, perché l'appendice tornerebbe "quasi" riproducibile. Sconsigliata.

Ordine dei commit proposed (un punto per commit, come da regole del repo), per A1:

1. `benchmark_v4.py` — il runner v4, con la dichiarazione di discordanza P1.6 già nel corpo;
2. i 6 moduli che lo importano (97 node id);
3. i 5 moduli indipendenti (17 node id);
4. le 5 modifiche a file tracciati (il parser dei node id del generatore e i suoi 12 test di guardia, i 3 corpi corretti);
5. `AGENTS.md`: il comando di rigenero (§4) e la correzione dell'ancoraggio stantio (§6).

**Elenco di esclusione esplicito** (cosa NON va aggiunto, per non travolgere il working tree con `git add -A`, vietato dalle regole): i `.DOCX` e i `.txt` dell'utente alla radice, `cpuepower/`, `cpuepower2/`, i `.tar`, `examples/`, `repomix-output.xml`, `cwEnergyModular/results/` (ignorato), `cwEnergyModular/.casualwatt_keys.json` (mai toccare, regola dura), `Tesi-latex/` (ignorato da `.gitignore:29`), `LibreHardwareMonitor.Report.txt`, `cw_probe.py`/`cw_probe_windows.json`, `s_epi_phase.py`, `handoff/`, `.qoder/`, e gli artefatti di esperimento non ancora citati dalla tesi. Ogni singolo percorso va aggiunto a nome.

---

## 4. Proposta B — la procedura di rigenero, da scrivere in `AGENTS.md`

```
# dalla radice, dopo un clone pulito
py -3.14 -m pytest cwEnergyModular                 # atteso: 294 raccolti, 291 passati, 3 saltati
cd cwEnergyModular
py -3.14 tools/dump_tests_latex.py       > ../Tesi-latex/qoder-bozza/generated/test_suite_appD.tex
py -3.14 tools/dump_schema_latex.py      > ../Tesi-latex/qoder-bozza/generated/schema_appA.tex
py -3.14 tools/dump_experiments_latex.py > ../Tesi-latex/qoder-bozza/generated/artefatti_appE.tex
```

Da scrivere insieme ai comandi, perché sono verifiche che altrimenti diventano false:

- **l'uguaglianza da attendersi è sui conteggi, non sui byte.** L'intestazione del generatore riporta host, versione di Python, stato di elevazione del processo (`processo elevato: si/no`) e durata reale dell'esecuzione: tre di queste quattro rigi rigenerano diversa su un'altra macchina. L'Appendice D, perché sia la stessa, deve dare 294 node id / 291 passati / 3 saltati / gli stessi 3 motivi di salto;
- **i 3 saltati sono platform-dependent.** `tests/test_rapl.py` salta su Windows e su Linux passerebbe: un clone su Linux darebbe 294 passati e un'appendice diversa. L'Appendice D è la fotografia di un host Windows, e va detto lì, non solo in cap. 4;
- **l'Appendice E è commit-dependent per costruzione**: l'intestazione riporta il `HEAD` (`% host: ... | HEAD fcb4994`) e il generatore confronta l'inventario disco con la cronologia di git. Un clone a un commit diverso produce un taglio diverso: è il suo significato, non un difetto, ma rende E non riproducibile byte-per-byte nemmeno con la procedura esatta;
- `--no-run` esiste già (`tools/dump_tests_latex.py:337-338`): va documentato come la modalità che produce l'inventario senza eseguire la suite, utile quando si vuole solo il conteggio dei node id.

---

## 5. Proposta C — i glifi: che cosa si può comporre senza mentire

### 5.1 Lo stato reale, contato

I 15 caratteri fuori dal range latino stanno in **10 righe** del file generato, e sono tre fenomeni distinti, non uno:

| dove | cosa | caratteri | natura |
|---|---|---|---|
| riga 61 (`test_short_text_alternatives_correct_3`) | la parola greca `Ἀθηνᾶ` citata nella docstring | 5 (U+0391 U+03B8 U+03AE U+03BD U+03B1) | **citazione di testo in un'altra lingua** |
| righe 110-113, 122 | `Σ` nelle formule `(1/m)·Σ` | 5 (U+03A3) | **operatore matematico** |
| righe 120, 121, 498, 499 | `Δ` in `Δt_W`, `ΔE` | 4 (U+0394) | **operatore matematico** |
| riga 121 | macron combinante dopo la `t` (`Δt̄`) | 1 (U+0304) | **diacritico** |

### 5.2 La proposta

Una **mappa chiusa e piccola** applicata dentro `fuori_latino` (`tools/dump_tests_latex.py:152-170`), prima del rimpiazzo generico, nell'ordine: (1) lettera + U+0304 → `\ensuremath{\bar{lettera}}`; (2) `Δ` → `\ensuremath{\Delta}`; (3) `Σ` → `\ensuremath{\Sigma}`; (4) **qualsiasi altra cosa resta `[U+xxxx]`**, senza invenzioni. La funzione lavora sul testo già escape-ato, quindi le sequenze LaTeX inserite non vengono toccate due volte (vincolo già documentato in `cella()`, `:379-396`).

Il vincolo di onestà è quello che il generatore stesso dichiara in intestazione: la colonna «è la prima riga di docstring del test, non una parafrasi». Comporre `Σ` in matematica **è** lo stesso carattere; trascriverlo «Sigma» sarebbe una parafrasi. La parola greca della riga 61 resta codepoint: renderla composta richiederebbe l'encoding LGR (`\usepackage[LGR,T1]{fontenc}` + font greco, non presente nel preambolo: `main.tex:10-11` carica solo T1 + utf8), cioè una dipendenza MiKTeX nuova per una sola cella — e il documento ha già un pacchetto mancante segnalato in compilazione (`csquotes`). Proposta: **non aggiungerla ora**; l'alternativa (caricare LGR e comporre la parola) resta documentata qui con il suo costo e non è adottata.

### 5.3 La fattibilità è stata provata, non promessa

test di compilazione eseguito oggi fuori dal repository (documento a sé, in `%TEMP%`: preambolo minimo che riproduce però le colonne reali — T1, utf8, longtable, array, `@{}r p{0.30\textwidth} p{0.47\textwidth} p{0.11\textwidth}@{}`, `footnotesize`, `tabcolsep 4pt`):

- **4 righe reali** estratte verbatim da `generated/test_suite_appD.tex` (le righe 120-123 del file generato, quelle di `budget_base_w`, `Δt̄_W,b` e della media non calcolabile): **exit 0, 0 errori, 0 overfull**;
- le stesse 4 righe con le tre sostituzioni applicate: **exit 0, 0 errori, 0 overfull**;
- **6 costrutti singoli** presi da soli (`\ensuremath{\Sigma}` in cella, `\ensuremath{\Delta}t\_W` con parentesi non chiusa, `\ensuremath{\bar{t}}`, il placeholder `\texttt{[U+0391 ...]}`, una riga banale, una riga troncata a parentesi aperta): ciascuno exit 0.

Non dimostra il compilate dell'intera tesi (i 294 righe insieme, con `\include` e bibliografia): quello resta la verifica di accettazione del punto C. Dimostra che la mappa non introduce né errore né overfull nelle celle che la contengono.

### 5.4 Guardie da scrivere insieme alla mappa

Nuova famiglia in `tests/test_dump_node_id.py` (il file che già custodisce il generatore; +6 node id attesi, quindi suite a **300 raccolti = 297 passati + 3 saltati**), con i nomi e l'assieme:

1. `Δ` e `Σ` escono dalla funzione come `\ensuremath{...}` e non come codepoint;
2. la lettera seguita da U+0304 esce come `\ensuremath{\bar{...}}`;
3. un glifo **non** in mappa (per esempio `θ`) esce ancora come `[U+03B8]` — la mappa non deve mangiarsi l'ignoto;
4. conservazione del conteggio: `mappati + non_composti == caratteri fuori range latino` (è l'asserzione che impedisce alla mappa di far sparire un carattere);
5. l'intestazione distingue le due quantità, quindi la dichiarazione in header non diventa mai falsa in silenzio;
6. la mappa è chiusa: nessuna voce che non corrisponda a un carattere realmente osservato (guardia contro la tentazione di allargarla «per sicurezza»).

Effetto a catena da dichiarare ora, perché i conteggi sono un claim: header del generatore, paragrafo dei 15 caratteri in `capitoli/appD_test.tex`, la frase in cap. 4 che dice «non si sa ancora se si può correggere senza mentire», e — se si sceglie l'opzione A1 — le cifre 294/291 in `AGENTS.md`, cap. 4, cap. 5, Appendice D.

---

## 6. Due altre imprecisioni trovate contando, con correzione da autorizzare separatamente

- `AGENTS.md:181` dichiara «Alla radice del repo stanno 23 script `.py` tracciati»; `git ls-files "*.py"` alla radice ne dà **31**. L'ancoraggio del file è dichiarato «verificato al 24-10-2026» e da allora gli harness sono cresciuti (`experiment_additivity.py`, `harness_overhead_probe.py`, i due probe della settima emenda). Correzione di una riga, non un cambiamento di regola.
- La dichiarazione di discordanza P1.6 in `benchmark_v4.py:1051-1053` cita l'ancoraggio «raise a `:2548`», ma `energy/energy_session.py:2548` è la guardia `if window is None:`; i `raise` sono a `:2553` e `:2562` (la seconda occorrenza, `:2561-2563`, è invece a posto). Un ancoraggio sbagliato in una dichiarazione di ancoraggio è il tipo di cosa che va corretta a mano, non aggirata.

---

## 7. Gli avvisi di compilazione residui, con una proposta ciascuno

| avviso | dove | proposta | perché così |
|---|---|---|---|
| `Float too large for page by 35.04pt` | `capitoli/cap02_contesto_stato_arte.tex:327` (tabella dei concorrenti) | **sì, come voce separata**: ridurre la tabella a una colonna in meno o spezzarla in due | è fuori dall'attività di coerenza dei conteggi e tocca un capitolo non ancora rivisto in questa fase |
| 48 `Underfull hbox` | quasi tutti in tabelle e `\raggedright` | **no, non ora**: dichiararli come cosmetici | inseguirli uno per uno rischia di modificare l'impaginazione di pagine che non fanno parte di nessuna verifica dei numeri |
| `csquotes` non caricato (biblatex) | `main.tex` preambolo | **sì**, una riga | biblatex lo raccomanda; rischio tipografico nullo, toglie un avviso reale |
| `\theauthor already defined` | preambolo | **sì**, dopo aver letto quale pacchetto lo ridefinisce | va capito prima di toccare: se non si sa l'origine, si dichiara e si lascia |
| `\headheight too small` (fancyhdr) | preambolo | **sì**, `\setlength{\headheight}` al valore chiesto | avviso univoco, correzione univoca |

---

## 8. Verifiche di accettazione (la proposta è chiusa solo se passano tutte)

1. clone pulito di `HEAD` → `294` raccolti con `291 passati, 3 saltati` (o `300`/`297` se il punto C è già applicato), output incollato per intero;
2. i tre saltati sono ancora esattamente i tre di `tests/test_rapl.py`, con gli stessi motivi;
3. Appendice D rigenerata dal clone e confrontata con quella in `Tesi-latex/`: stesse 26 intestazioni di file, stessa somma 294, nessun `n/eseguito`;
4. riga 61 ancora con i 5 codepoint (dichiarati), e le altre 9 righe con `\ensuremath{}`; header che distingue le due quantità;
5. compilate completo: **0 Overfull hbox, 0 riferimenti indefiniti, 0 errori `!`**; lettura della pagina dell'appendice per confermare che i glifi rendano davvero leggibili `Δt_W`, `Δt̄_W,b`, `(1/m)·Σ`;
6. suite completa verde anche con i 6 test di guardia nuovi;
7. nessun commit e nessun push senza autorizzazione esplicita, un commit per punto.

---

## 9. Che cosa questa proposta non tocca

Le formule del protocollo (F.0–F.17) e la forma di combinazione di `budget_base_w`; le soglie congelate (1,0 W, 10 %, 5/20 %, 2 token, fattore 2); la banda #70; `benchmark_unified.py` e il percorso di produzione corrente; i due decisioni aperte P1.6 e P2.9, che restano descritte nel rapporto di questa attività e non hanno qui nessuna soluzione nascosta; ogni esecuzione hardware, pilota o pre-pilota.
