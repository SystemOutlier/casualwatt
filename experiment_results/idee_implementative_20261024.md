# Idee implementative dai progetti esterni e dai report (24-10-2026)

**Cosa contiene.** La sintesi operativa di quanto letto e provato fra il 22 e il
24 ottobre: i progetti GitHub valutati (CEM, pyJoules, toolkit Accenture,
AI-Wattch, mlco2/impact, piu' i competitor gia' in tesi) e i report interni
(`strumenti_esteri_20261023`, `ricerca_metodo_docx_valutazione_20261023`,
`rev_metodo_20261023`, `alt_lhm_20261024`, `srum_emi_cross_20261023`,
`four_way_finestra_uguale_20261023`, `observer_cost_20261023`,
`emi_cadenza_distribuzione_20261023`, `idle_floor_sensitivity_20261023`).

**Criterio di selezione**, lo stesso dei report: un'idea entra nel codice solo
se (1) riguarda una grandezza **misurata** e non stimata, (2) e' verificabile
con un test o un esperimento prima/dopo, (3) non sostituisce il canale di
produzione senza evidenza (regola "tenere l'attuale finche' provato"), (4) il
costo e' proporzionato al beneficio. Le idee che richiedono hardware assente
(GPU NVIDIA, dual-boot Linux, wattometro) restano in backlog con lo stato
dichiarato, non vengono simulate e spacciate per fatte.

---

## 1. Cosa si implementa subito (offline, senza toccare il canale)

| # | idea | da dove viene | cosa cambia | costo | stato |
|---|---|---|---|---|---|
| P0-1 | **Provenienza del contatore nella riga CSV**: `raw_start`, `raw_end`, `raw_unit`, `domain`, `sampling_interval_observed_s`, `backend_version` | `alt_lhm_20261024` §3 (contratto §2, par. 31-52); `rev_metodo` §2(b) | una riga dice con quali valori grezzi e con quale cadenza reale e' stata ottenuta l'energia, non solo con quale metodo; la cadenza osservata sostituisce l'equivoco fra `interval_s` richiesto (0,5 s) e thread reale (0,28-0,34 s su LHM, 0,05 s su EMI) | basso: campi in coda, migrazione header gia' esistente | **fatto in questo ciclo** |
| P0-2 | **Test di reset/non monotonia del contatore cumulativo** | `alt_lhm` §6 fase 2 ("manca: un test che modelli il reset") | il ramo che svuota il buffer quando il contatore decresce (driver ricaricato, sospensione/ripresa) smette di essere solo codice non provato | basso | **fatto in questo ciclo** |
| P0-3 | **Finestra e capacità dichiarate per `cpu_time_share`** | `rev_metodo` §2(b): "la quota va definita rispetto allo stesso intervallo e normalizzata alla capacità realmente disponibile" | due campi nuovi: `cpu_share_window_s` (intervallo su cui e' calcolato il rapporto, gia' ridotto delle sottofinestre escluse) e `cpu_busy_capacity_cores` (core logici), cosi' `d_busy_s <= core x finestra` e' verificabile a posteriori | basso: i delta sono gia' calcolati sulla stessa finestra; mancava la dichiarazione | **fatto in questo ciclo** |

Perche' queste tre e non altre: sono le uniche del backlog che (a) non
richiedono una nuova esecuzione sul campo, (b) rendono **revisionabile** un
numero gia' prodotto, (c) non cambiano il valore di `package_energy_j`. Le
righe storiche restano leggibili: le colonne nuove si accodano e la migrazione
di `ensure_header` le riempie con celle vuote, come gia' fatto per
`energy_calculation_method` (commit `b6539e1`).

### Dettaglio P0-1: cosa significa "grezzo"

- **EMI**: il record del driver e' in **pWh**; il valore agli estremi di
  finestra e' interpolato dal buffer a 0,05 s (stessa regola di
  `_emi_cum_at`: nessuna estrapolazione oltre 1 s). `raw_unit = pWh`,
  `domain = PKG`. La conversione in joule resta quella del backend
  (`PWH_TO_J`, verificata contro SRUM: accordo 0,9946 a finestra identica).
- **power-integration (LHM)**: non esiste un contatore grezzo, si integra una
  potenza. `raw_start`/`raw_end` restano vuoti e `raw_unit` vuoto: un campo
  vuoto dichiara l'assenza, un numero inventato no.
- **RAPL**: il contatore e' in microjoule; il valore e' quello cumulato
  (unwrapped) del backend, `raw_unit = uJ`.
- **`backend_version`**: versione del **percorso di lettura**, non del driver.
  Per EMI e' la versione del reader e l'IOCTL; per LHM la versione
  dell'assembly caricato; per RAPL la release del kernel. Dove non e'
  ottenibile resta una stringa che lo dichiara, mai un numero di versione
  supposto (la lezione di `alt_lhm` §3: sorgente 0.9.6, runtime 0.9.4).

La cadenza osservata e' la **mediana** dei delta temporali dei campioni del
buffer nella finestra, non la media: la media e' trascinata dalle pause del
thread (misurate: 0,0506 s -> 0,0770 s sotto carico, `emi_cadenza_distribuzione_20261023.md`),
la mediana descrive il passo tipico.

---

## 2. Backlog ordinato: cosa manca e cosa serve per farlo

### P1 - esperimenti gia' progettati, richiedono esecuzione

| # | idea | fonte | perche' vale | prerequisito |
|---|---|---|---|---|
| P1-1 | **Baseline pre/post con criterio di instabilita' a priori** (`baseline_start_w`, `baseline_end_w`, `deriva_baseline_w_s`, `run_stabile_si_no`) | `rev_metodo` §2(a); `ricerca_metodo` §5.1 | la baseline e' gia' un parametro che sposta il risultato: ∂e_token/∂P_idle = -T/N, e fra run v3 e' passata da 13,39 a 12,19 W (r = -0,982) | una sessione con macchina quieta prima **e** dopo il carico; la soglia va scritta prima, non scelta dopo |
| P1-2 | **Protocollo v4**: n. richieste fisso, geometria `a·N_in + b·N_out`, `keep_alive` dichiarato, durate di fase | `ricerca_metodo` §5.2-5.4; `alt_lhm` §6 fase 5 | i J/token di v2 e v3 (0,9873 vs 1,2862) non sono confrontabili; senza geometria il numero non ha dominio di validita' | run live su Ollama; `prefill_duration_s`/`decoding_duration_s` sono gia' nel CSV |
| P1-3 | **Sweep di N_in a N_out fisso** (2-3 livelli) | `ricerca_metodo` §5.4 | separa il costo di prefill da quello di decode: oggi 1,29 J/token e' di fatto un costo di decode (N_in 12,3 / N_out 31,8) | P1-2 |
| P1-4 | **Costo dell'osservatore EMI in W** con A-B-A reader attivo/inattivo | `rev_metodo` §3 | il costo misurato finora (0,2-0,9 W) e' della GUI LHM, non del thread EMI; la cadenza sotto spin sale da 0,0506 a 0,0770 s | A-B-A con GUI chiusa, stesso carico |
| P1-5 | **Windows senza driver EMI** | `alt_lhm` §6 fase 4 | il ramo di fallback LHM e' l'unico non esercitato su una macchina che non ha il canale | VM (deciso dall'utente) |
| P1-6 | **Ambiente venv senza `pythonnet`** | `alt_lhm` §6 fase 4 | il probe del 24/10 blocca l'import, non disinstalla: manca la prova "installazione pulita" | venv dedicato senza `requirements-lhm.txt` |

### P2 - idee esterne pronte ma legate a un confine diverso

| # | idea | fonte | stato dichiarato |
|---|---|---|---|
| P2-1 | **CEM come secondo lettore Linux** (output `-r`: `cpu0_package_joules`, `cpu0_psys_joules`) e **PSYS** fra le colonne | `strumenti_esteri` §2 e §8.2 | pronto nella `VALIDAZIONE_LINUX_RAPL_CHECKLIST.md`; richiede dual-boot. PSYS e' il sostituto piu' vicino a un wattometro senza esserlo |
| P2-2 | **pyJoules** come corroborazione del limite di finestra (sotto la granularita' del dispositivo la risposta giusta e' "nessun valore") e del wrap-around dei contatori | `strumenti_esteri` §3 | gia' recepito nel capitolo limiti; non eseguibile su Windows (Linux-only) |
| P2-3 | **Wattometro** come confine indipendente della scala assoluta | `alt_lhm` §8 | aperto: SRUM decodifica lo stesso contatore, LHM lo stesso MSR, HWiNFO ha `err=2` sulla Shared Memory |
| P2-4 | **Verbale generato dal JSON dell'esperimento** (template LaTeX stile `impact`) | `strumenti_esteri` §8.4 | utile, ma dopo che il verbale v4 avra' i campi P1-1/P1-2; generare un report da JSON incompleto moltiplica campi vuoti |
| P2-5 | **NVML Tier A** (`nvmlDeviceGetTotalEnergyConsumption`, mJ cumulativi) accanto al Tier B (`GetPowerUsage`, mW) | tesi cap. 6; documentazione NVML in bibliografia | implementabile con un fake offline, ma **non esercitabile** su questo host (nessuna GPU NVIDIA) e non sostituisce l'integrazione di potenza senza una prova sul campo |
| P2-6 | **HWiNFO Shared Memory** come quarta sorgente | `rev_metodo` §2(d); manuale locale p.14/p.59 | `err=2` non risolto; nessuna azione prima di una prova di lettura |
| P2-7 | **Ripetizioni e incertezza** (mediana/IQR, non run singolo) | `observer_cost`, `idle_floor_sensitivity` | la finestra da 4 s non e' ripetibile (13,51/13,05/12,41 W, scarto 8,4%); con finestre da ~90 s il fondo e' 11,92/11,07/11,29 W. Va nel verbale v4, non corretto a posteriori |

### P3 - estensioni di metodo, non di misura

| # | idea | fonte | nota |
|---|---|---|---|
| P3-1 | `EnergyContext(start_tag/end_tag)` per regioni di codice non-LLM | toolkit Accenture, `strumenti_esteri` §4 | **non** per J/token: la granularita' per funzione e' incompatibile con l'intervallo PI (0,31-0,34 s contro richieste da 3,60 s). Solo capitolo estendibilita' |
| P3-2 | Doppio stimatore token/tempo per il tier cloud, etichettato `estimated` | AI-Wattch, `ricerca_metodo` §3 | pattern di **stima** dichiarabile; non entra nel metodo di misura |
| P3-3 | Fattori di griglia e formato di reporting di `impact` | `strumenti_esteri` §6 | gia' usati nel layer carbonio; `impact` esclude esplicitamente il PUE, quindi non e' un arbitro del confine cloud |

---

## 3. Cosa non si adotta (e perche')

| cosa | motivo | fonte |
|---|---|---|
| codice del toolkit Accenture | nessun file LICENSE (API `license=None`, `LICENSE` -> 404): il metodo si' (baseline subtraction, tagging), il codice no | `strumenti_esteri` §4 |
| CEM/pyJoules come backend Windows | Linux-only dichiarato; CEM legge RAPL, pyJoules dipende da RAPL. Su Windows il canale resta EMI, con LHM fallback | `strumenti_esteri` §1-3 |
| AI-Wattch come misura | e' una stima da telemetria browser, senza validazione contro strumenti fisici; serve come polo opposto in related work | `strumenti_esteri` §5 |
| `impact` come arbitro del cloud | hours x hardware x griglia, PUE escluso per scelta; utile per il reporting, non per il confine misurato | `strumenti_esteri` §6 |
| backend MSR del toolkit `cpuepower` | 19/20 test, probe che crasha, mappa MSR e bit-layout sbagliati verificati sul kernel, numeri mock: banca di esperimenti, non backend | audit `cpuepower` (memoria di progetto) |
| split per funzione Python | sotto la risoluzione del contatore il numero sarebbe costruito | `strumenti_esteri` §4; `ricerca_metodo` §5 |
| rimozione di LHM | rifiutata: LHM resta fallback dichiarato e opzionale, non dipendenza obbligatoria | `alt_lhm` §5 |
| somma PP0+PP1 o PKG+DRAM | domini non additivi (sottoinsiemi del package); PP1 e' informativo e va in `igpu_energy_j` | `emi_backend.py` docstring; test `test_igpu_pp1_emi.py` |
| SRUM come validazione indipendente | decodifica lo stesso contatore EMI (accordo 0,9946): valida il parser, non la scala | `srum_emi_cross_20261023_analisi.md` |
| EnviroLLM come metro di confronto | monitoraggio locale con TDP statico: stima, non misura; resta in related work | `ricerca_metodo` §2(f) |
| "nessuno integra locale+cloud+rete" | claim assoluto confutabile; va detto "nessuno dei tool confrontati" | `ricerca_metodo` §2(f) |

---

## 4. Tracciabilita': cosa ha dato ogni fonte

| fonte | idea trattenuta | dove finisce |
|---|---|---|
| CEM (TACAS 2020) | PSYS come confine piu' vicino al wattometro; output `-r` parseabile; esecuzione senza root con `setcap` | checklist Linux, capitolo limiti |
| pyJoules | limite di finestra e overflow del contatore sono proprieta' note della famiglia RAPL, non idiosincrasie nostre | capitolo risoluzione |
| Accenture toolkit | baseline subtraction e tagging; **metodo, non codice** | capitolo metodo, P3-1 |
| AI-Wattch | dualita' token/tempo come pattern di stima dichiarata | capitolo cloud, P3-2 |
| mlco2/impact | formato di reporting + fattori di griglia; PUE escluso | layer carbonio, P2-4 |
| MLPerf Power | protocollo di ripetizioni e verbale | P1-1/P1-2/P2-7 |
| EcoLogits | modello cloud multi-tier con PUE, embodied, mix elettrico | capitolo cloud |
| TokenPowerBench (AAAI-26) | J/token come metrica di sistema, non di singolo prompt | capitolo stato dell'arte |
| SweetSpot (ICPE '26) | compromesso accuratezza/energia per il judge | valutazione |
| SRUM | accordo a finestra identica sul **parser**, non sulla scala | capitolo validazione |
| LHM GUI report | omonimia power/temperature provata dall'esterno; costo dell'osservatore | fix `1422d1b`, P1-4 |
| alt_lhm.DOCX | contratto di misura, Tier A/B, fase 5 | P0-1/P0-2, P2-5 |
| rev_metodo.DOCX | baseline pre/post, quota su stessa finestra, cadenza reale | P0-1/P0-3, P1-1/P1-4 |
| ricerca_metodo.DOCX | `keep_alive`, geometria, sweep N_in | P1-2/P1-3 |

---

## 5. Ordine di esecuzione consigliato

1. **P0-1/P0-2/P0-3** (questo ciclo): rendono revisionabili i numeri gia'
   prodotti; nessun run nuovo.
2. **P1-1 + P1-2 + P1-3**: un solo protocollo v4 che porta baseline pre/post,
   n. richieste fisso, geometria dichiarata e sweep. Da fare insieme, altrimenti
   si producono altri J/token non confrontabili.
3. **P1-4 + P1-5 + P1-6**: costo dell'osservatore e copertura dei rami di
   fallback (VM, venv pulito).
4. **P2-1/P2-3**: dual-boot con CEM e wattometro: e' l'unico passo che puo'
   arbitrare la **scala assoluta**, che oggi resta un limite dichiarato.
5. Il resto come estensione, senza anticipare risultati che non abbiamo.
