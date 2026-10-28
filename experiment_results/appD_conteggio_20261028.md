# Appendice D — come si contano i node id, e cosa dice la rigenerazione del 2026-10-28

Data: 2026-10-28. Ambito: verifica del conteggio e rigenerazione dell'artefatto
LaTeX. **Nessuna riga di codice modificata**; l'unico file scritto e'
`Tesi-latex/qoder-bozza/generated/test_suite_appD.tex`, che sta fuori da git ed
e' interamente rigenerabile con un comando.

---

## 1. Da dove escono i node id

`cwEnergyModular/tools/dump_tests_latex.py` non trascrive nulla a mano. Tre
strati, confrontati fra loro:

| strato | come | righe |
|---|---|---|
| node id raccolti | `pytest --collect-only -q`, da `cwEnergyModular/` | `:342`, filtro `:207-215` |
| esiti reali | `pytest -v -rs`, eseguito adesso | `:343`, parser `:223-280` |
| docstring | AST dei file di test, chiave `(classe, nome)` | `:173-204` |

Un node id raccolto ma senza esito finisce in un'avvertenza nell'header
(`:367-370`, `:446-448`), non sparisce dalla tabella. Il node id e' la riga
intera di `--collect-only -q` — non si spezza al primo spazio (`:240-254`): un
parametro con spazi produrrebbe un nome inesistente nell'AST.

## 2. Perche' 526 e non un altro numero

Le due raccolte coincidono:

```
pytest cwEnergyModular --collect-only -q        -> 526 tests collected
pytest --collect-only -q   (da cwEnergyModular) -> 526 tests collected
```

Non c'e' configurazione pytest alla radice (ne' `pytest.ini`, ne'
`pyproject.toml`, ne' `setup.cfg`): l'unico `conftest.py` e' in
`cwEnergyModular/`, quindi la radice di raccolta e' la stessa e cambia solo il
prefisso dei node id (`cwEnergyModular/tests/...` contro `tests/...`).

La partizione e' quella scritta in `AGENTS.md:240-243`: 467 in
`cwEnergyModular/tests/` piu' 59 nei tre file di radice
(`test_answer_type_evaluation.py` 35, `test_synthetic_window.py` 2,
`test_validazione_valutazione.py` 22). 467 + 59 = 526. La somma dei conteggi
per file stampati come `\paragraph` nel file generato e' 526: nessuna riga e'
persa o duplicata.

## 3. La rigenerazione del 2026-10-28

Comando (dalla cartella `cwEnergyModular/`):

```
python tools/dump_tests_latex.py > ../Tesi-latex/qoder-bozza/generated/test_suite_appD.tex
```

Header prodotto:

```
% host: Windows 11 | python 3.14.5 | processo elevato: si
% esito esecuzione reale: 523 passed, 3 skipped in 9.83s
% node id raccolti: 526; righe di tabella: 526
% Copertura delle docstring: 513 righe documentate su 526
% 15 caratteri fuori dal range latino ... resi come codepoint
```

Il file precedente era del 2026-10-26 e dichiarava 404 node id (401 passati, 3
saltati, docstring 404/404). Il divario 526 − 404 = 122 e' crescita reale della
suite fra il 26 e il 28 ottobre (RAPL, diagnostica PMI, selezione EMI, GPU
NVML/AMD SMI, `external_counter`, `chain_status`, PawnIO), non un cambio di
metodo di conteggio.

Verifica di compilazione, in `Tesi-latex/qoder-bozza/`:

```
pdflatex main && biber main && pdflatex main && pdflatex main
```

Esito: `main.pdf`, 176 pagine, **0 overfull**, 0 comandi indefiniti, nessun
riferimento o citazione irrisolti. Gli `Underfull` (49) non sono un requisito
del progetto.

## 4. Il divario che la rigenerazione mette in chiaro

`AGENTS.md:243` enuncia la norma "ogni test ha una docstring". Oggi non e'
vera: 513 righe su 526 sono documentate. Il divario non e' del generatore, e'
di nove funzioni senza docstring che si espandono in tredici node id:

| file | funzione | node id |
|---|---|---|
| `tests/test_diagnostics_pmi.py` | `test_json_non_valido_non_conclusivo` | 1 |
| `tests/test_pawnio_backend.py` | `test_lettura_energia_fallita_e_dichiarata` | 1 |
| `tests/test_pawnio_backend.py` | `test_hvci_decide_quale_firmatario_e_ammesso` | 5 (parametrizzato) |
| `tests/test_pawnio_backend.py` | `test_servizio_fermo_non_si_arriva_alla_firma` | 1 |
| `tests/test_pawnio_backend.py` | `test_modulo_assente` | 1 |
| `tests/test_pawnio_backend.py` | `test_produttore_sconosciuto` | 1 |
| `tests/test_pawnio_backend.py` | `test_probe_riporta_i_criteri_applicati` | 1 |
| `tests/test_pawnio_backend.py` | `test_chiusura_rende_il_backend_non_disponibile` | 1 |
| `tests/test_pawnio_backend.py` | `test_find_modules_dir_rispetta_la_variabile` | 1 |

Nessuna docstring e' stata inventata qui: il generatore stampa "nessuna
docstring" e lo dichiara nell'header (`:451-452`). Chiudere il divario
significa scrivere le nove docstring nel codice, con un commit proprio e la
suite intera incollata, e poi rigenerare: e' debito registrato, non lavoro
fatto in questo turno.

## 5. Ripetibilita'

- un solo comando, nessun conteggio scritto a mano: le cifre stanno
  nell'header del file generato e nei commenti `%`, non nel corpo;
- dopo qualunque test aggiunto, rimosso o rinominato, il file va rigenerato
  prima di citarne i conteggi — il generatore confronta raccolta, esecuzione e
  AST e segnala le discordanze invece di nasconderle;
- i guard del generatore sono essi stessi test
  (`tests/test_dump_node_id.py`, 33 raccolti oggi): la
  selezione delle righe, lo spezzamento dei parametri e la lunghezza dei
  frammenti inseguibili sono verificati senza compilare la tesi;
- il file generato sta fuori da git, quindi non esiste un commit che lo
  versioni: la sua provenienza e' il comando, e il comando e' tracciato.

## 6. Ancore verificate il 2026-10-28

| affermazione | ancora |
|---|---|
| tre strati del generatore | `tools/dump_tests_latex.py:1-20`, `:342-343` |
| filtro delle righe di raccolta | `tools/dump_tests_latex.py:207-215` |
| parser degli esiti | `tools/dump_tests_latex.py:223-280` |
| docstring via AST | `tools/dump_tests_latex.py:173-204` |
| avvertenza sui raccolti non eseguiti | `tools/dump_tests_latex.py:367-370` |
| conteggi nell'header | `tools/dump_tests_latex.py:440-458` |
| 526 = 467 + 59 | `AGENTS.md:240-243`; raccolta verificata oggi |
| artefatto installato | `Tesi-latex/qoder-bozza/generated/test_suite_appD.tex` (fuori da git) |
| inclusione nella tesi | `Tesi-latex/qoder-bozza/capitoli/appD_test.tex:293` |
