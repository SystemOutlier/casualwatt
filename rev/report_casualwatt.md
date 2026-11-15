# Report di analisi — CasualWatt (MUDILAB)

## 1. Stato del repository
- Suite di test: 888 node id raccolti, 870 passati, 15 falliti, 3 saltati (Python 3.13, pytest 9.2.0).
- I 15 fallimenti riguardano il contratto di identità GPU (`calibrate_gpu_idle`, `_gpu_identity`, `get_uuid`/`get_amd_uuid`/`get_bdf`): le fixture non dichiarano l'identità, quindi la calibrazione raise e `gpu_idle_provenance` finisce `identity-unavailable`. È un cambio di contratto non propagato alle fixture, non un bug di calcolo (confermato da AGENTS.md).

## 2. Bug e problemi rilevati
1. **Dipendenze mancanti nell'ambiente**: `psutil`, `requests`, `pyagrum` non installati di default; la suite non parte senza installazione manuale.
2. **Contratto GPU identity non propagato**: 15 test falliscono per identità GPU non dichiarata nelle fixture.
3. **Codice MUDILAB (agents.py)**: riferimenti a `gpt5`, `small`, `client` non definiti nel file mostrato; `web_search` usa Tavily con domini fissi; `cau_inference` usa `eval(features)` (rischio injection) e path hardcoded Windows.
4. **funtions.py**: `complex_prob` indicizza `df[...][y][yval]` senza gestione KeyError; `g_bin` ha rami `dim==2`/`dim==1` con variabili non definite (`n`, `m`) in alcuni percorsi; `cobound` assume `input_` dict con una chiave.
5. **tools.py**: `read_graph` path default hardcoded; `cau_inference` path default hardcoded a `C:/Users/Samsung/...`.

## 3. Performance
- La suite completa gira in ~19s; i test GPU sono i più lenti per il fake NVML/AMD SMI.
- Suggerimento: parametrizzare le fixture GPU con identità per ridurre i 15 fallimenti e stabilizzare la suite.

## 4. Validazione scientifica del metodo
- CasualWatt misura energia per inferenza LLM locale su Windows via contatore EMI (MSR_PKG_ENERGY_STATUS 0x611), con fallback PawnIO (MSR package via driver PawnIO, release 0.2.11 hash pinnato).
- Metodologia: baseline = mediana di 3 finestre da 30s (P1.3, P1.14); nessun clamp a zero (cd881e6b, 86bba6a8); delta firmati conservati; `active_valid` flag per riga.
- Riferimenti scientifici: RAPL/MSR_PKG_ENERGY_STATUS è il metodo standard per misura energetica CPU su Intel (Intel RAPL, "Running Average Power Limit", documentazione Intel SDM). CodeCarbon usa stima TDP (contrasto). ML.ENERGY Benchmark (Chung et al., arXiv:2505.06371) misura J/token in steady state con Zeus. MLPerf Power (arXiv:2410.12032) usa strumentazione certificata J/campione.
- CasualWatt si distingue per misura diretta del contatore hardware (non stima TDP), con attribuzione per token e bootstrap a livello di task (seed 20261104, 2000 ricampioni).

## 5. Raccomandazioni
- Propagare l'identità GPU nelle fixture di test per chiudere i 15 fallimenti.
- Rimuovere `eval()` in `cau_inference` (usare `json.loads`).
- Parametrizzare i path hardcoded.
- Aggiungere gestione errori in `complex_prob` e `g_bin`.
- Documentare il caveat: accordo EMI/LHM/SRUM non è validazione indipendente (stesso registro 0x611); scala assoluta richiede wattmetro esterno.
