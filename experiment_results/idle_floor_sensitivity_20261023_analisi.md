# Sensibilita' di J/token al fondo di idle — RQ2 senza hardware nuovo

Script: `idle_floor_sensitivity.py` (radice del repo).
Output: `experiment_results/idle_floor_sensitivity_20261023.json`.
Eseguito 2026-10-23. **Nessun rilancio**: legge i due CSV A-B-A gia' committati
dopo il fix del percorso di lettura (`1422d1b`) e riapplica la forma chiusa
dell'eq. (3.4) di tesi, `E_inc = max(E_load − P_fondo·dt_load, 0)`.

## 0. Prima cosa: la ricalcolazione indipendente torna esatta

Il riscrive i numeri primari dai soli campi grezzi (`energy_j`, `dt_s`,
`tokens_out`, `power_w` delle fasi base), senza leggere i riepiloghi gia'
pubblicati:

| protocollo | qui | pubblicato nel JSON del run |
|---|---|---|
| 15:09→15:36, 8 run × 15 inferenze | **1,2862 J/token, CV 8,99%** | 1,286172 / 8,99 |
| replay v2, 5 run × 5 inferenze | **0,9873 J/token, CV 9,66%** | 0,987342 / 9,66 |

Identici alla quarta cifra: il percorso di calcolo di questo esperimento e'
indipendente e concorde. E' il controllo che va citato prima di usare i numeri
che seguono.

## 1. pendenza in forma chiusa, e i suoi due protocolli

`d(J/token)/dP_fondo = − dt_load / tok_out` = il **reciproco del throughput**,
non un parametro libero:

| protocollo | pendenza media [J/token per W] | intervallo sui run |
|---|---|---|
| 8 × 15 inferenze | **−0,0766** | −0,0789 … −0,0731 |
| 5 × 5 inferenze | **−0,1134** | −0,1232 … −0,0976 |

Il protocollo corto e' il 48% piu' sensibile al fondo: stesso modello, stesso
prompt, stessa baseline da 30 s × 2, e la metrica diventa piu' fragile perche'
il carico e' piu' breve rispetto alla sua energia lorda. Questa e' la ragione
quantitativa per cui il confronto fra protocolli diversi (v2 0,99 contro v3 1,29,
rapporto 1,30) **non** e' una differenza di misura.

## 2. Quanto vale sbagliare il fondo

Fondo unico per tutti i run, valore al posto di quello calibrato:

| fondo imposto [W] | provenienza | J/token (8×15) | delta | J/token (5×5) | delta |
|---|---|---|---|---|---|
| 11,547 | fondo medio di questo protocollo | **1,2853** | — | — | — |
| 13,400 | EMI, four-way 23/10 ore 12:08 | 1,1434 | **−11,0%** | 1,1799 (+18,9% sul suo 0,9924) | — |
| 15,053 | fondo medio del protocollo corto | — | — | **0,9924** | — |
| 16,500 | EMI, fondo dei 5 test | 0,9059 | **−29,5%** | 0,8282 | −16,6% |
| 65,000 | `idle_power_w` delle 9 righe pubblicate | **clamp** | 8/8 run a zero | **clamp** | 5/5 a zero |
| 66,095 | fondo "calibrato" pre-fix (era °C) | **clamp** | 8/8 run a zero | **clamp** | 5/5 a zero |

Due letture, entrambe da portare in discussione.

(1) **Errore sistematico**: sbagliare il fondo di 1 W sposta la metrica del
6–11%; 5 W di fondo (la distanza fra il fondo proprio e quello EMI dei 5 test)
valgono **−30%** su J/token. Nessun sensore al mondo recupera quel errore: e' il
parametro, non la strumentazione.

(2) **Non e' un bias, e' un'annullazione**. Con fondo 65 o 66,095 W il termine
dentro il `max(·, 0)` di eq. (3.4) diventa negativo per **tutti** i run: la
metrica non esce gonfia o sgonfia, esce **zero**, e il clamp la nasconde. E'
esattamente la firma delle 9 righe pubblicate in
`cwEnergyModular/results/semantic_evaluation_results.csv`, dove
`active_energy_j` e `local_energy_j` valgono 0,0 in 7 righe su 9 e il resto e'
spiegato dal `package_window_source = unavailable`. Il pavimento del pacchetto
vale 28,3 W (8×15) e 23,8 W (5×5) **comprensivo del fondo**: un fondo dichiarato
sopra quel valore non e' "alto", e' fuori dominio.

## 3. Meta' del rumore e' la stima del fondo, non il fondo

`sd(P_base)` fra i run e' 1,29 W (8×15) e 0,97 W (5×5). Moltiplicata per la
pendenza del protocollo prevede CV di **7,68%** e **11,14%** contro l'8,99% e
il 9,66% osservati: il modello "il rumore e' tutto nella baseline" predice bene
anche qui (e il 14% di scarto sul protocollo corto e' dentro 1,3 W di fondo).

La prova controfattuale, stessa identica energia lorda:

| convenzione sul fondo (8×15) | J/token | CV |
|---|---|---|
| media A-B di eq. (3.4), run per run | 1,2862 | **8,99%** |
| solo finestra A | 1,2353 | 19,59% |
| solo finestra B | 1,3370 | 11,97% |
| **fondo unico dichiarato** (11,547 W per tutti) | 1,2853 | **2,20%** |

| convenzione sul fondo (5×5) | J/token | CV |
|---|---|---|
| media A-B, run per run | 0,9873 | 9,66% |
| solo A | 1,0334 | 10,35% |
| solo B | 0,9413 | 26,90% |
| fondo unico dichiarato | 0,9924 | **4,52%** |

Tre conclusioni operative per il protocollo v4:

- la **scelta** della finestra di riferimento sposta la media di ±4,0% (8×15) e
  ±4,8% (5×5): e' un parametro del protocollo, va dichiarata, non decisa a
  runtime; con le convenzioni sbagliate (solo A o solo B su 5×5) il CV
  esplode a 19,6% e 26,9%;
- quasi **tutta** la dispersione fra run scompare quando il fondo smette di
  essere stimato 16 volte da 30 s e diventa un numero solo: CV 8,99% → 2,20%.
  Non perche' la macchina sia piu' silenziosa, ma perche' eq. (3.4) sottrae
  una quantita' stimata, e la stima era la parte rumorosa;
- il guadagno pero' va misurato, non assunto: con il fondo unico la correzione
  run-per-run non esiste piu', quindi se il fondo **varia davvero** fra un run e
  l'altro la media si sposta. Il test che lo decide e' il protocollo v4 con il
  fondo EMI a fare da riferimento esterno, perche' EMI e LHM qui sono lo stesso
  contatore (`MSR_PKG_ENERGY_STATUS 0x611`) e non possono arbitrarsi a vicenda.

## 4. Cosa NON dice questo esperimento

Non tocca `s` di eq. (3.5) (la quota per-processo), perche' i protocolli A-B-A
non la usano: qui il fondo si sottrae all'intera macchina. Non da' J/risposta
corretta, perche' i due protocolli non hanno etichette di correttezza. Non
arbitra la scala assoluta. E' un'esperimento di sensibilita' **aritmetica** su
dati reali e committati, ed e' il motivo per cui costa zero e si riesegue con
`python idle_floor_sensitivity.py`.
