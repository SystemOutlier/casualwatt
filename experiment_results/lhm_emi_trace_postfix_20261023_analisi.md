# Trace LHM + EMI rilanciata col percorso di lettura corretto — analisi

Run: `experiment_results/lhm_emi_trace_20261023_154628.csv` (635 righe, tick
mediano **0,251 s**), 2026-10-23 **15:46:28**, processo elevato, MINI_IT13.
Analisi: `lhm_trace_same_window.py` →
`lhm_emi_trace_20261023_154628_stessa_finestra.json`.
Confronto storico rieseguito con **lo stesso codice di analisi** sulla trace
pre-fix `lhm_emi_trace_20261022_022207.csv` (634 righe).

## 1. Perche' questa trace, adesso

Non serve piu' a stabilire quale campo EMI sia il package (e' il record a
offset 0, in pWh — stabilito il 22/10). E' l'unico artefatto che mette LHM ed
EMI **sullo stesso orologio con tick 0,25 s** con un carico **diverso
dall'inferenza**: 8 worker busy-loop, nessun Ollama. Se il "pendenza divergente"
dei four-way pre-fix fosse stata una proprieta' del sensore, qui si ripresenterebbe
su uno stimolo che non c'entra niente con il path GPU/CPU dell'LLM.

## 2. Prima e dopo, stesso protocollo, stesso codice di analisi

Fasi 40 s idle → 40 s load (8 burner) → 40 s cool → 40 s idle2.

**PRE-FIX** (22/10, LHM integrava la temperatura di package):

| fase | LHM "W" | EMI W | rapporto |
|---|---|---|---|
| idle | 69,60 | 16,40 | 4,2434 |
| load | 95,42 | 38,63 | 2,4700 |
| cool | 71,63 | 16,22 | 4,4173 |
| idle2 | 69,62 | 15,78 | 4,4126 |

offset sugli assoluti (base media delle due idle) = **+53,52 W**; differenziale
della fase load = EMI 896,0 J vs LHM 1026,7 J → rapporto **1,1459**.

**POST-FIX** (23/10, stesso script, fix 1422d1b nel backend di produzione):

| fase | LHM W | EMI W | rapporto |
|---|---|---|---|
| idle | 11,41 | 11,44 | **0,9966** |
| load | 38,43 | 38,54 | **0,9970** |
| cool | 13,49 | 13,29 | **1,0150** |
| idle2 | 12,86 | 12,67 | **1,0156** |

offset sugli assoluti = **+0,08 W**; differenziale load = EMI 1047,1 J vs LHM
1031,0 J → rapporto **0,9846**.

## 3. Cosa dice

1. Il rapporto medio LHM/EMI a finestra identica passa da **3,89** (media dei
   quattro rapporti pre-fix) a **1,006**, e il differenziale della fase load da
   1,1459 a 0,9846. Su uno stimolo che non e' inferenza: non e' un adattamento
   al caso, e' il canale giusto.
2. Il valore assoluto del package a riposo (EMI **11,4 W** a 15:46, 16,4 W il
   22/10 alle 02:22) e' coerente con l'involucro PL1 35 W / PL2 55 W e con le
   altre sorgenti; il delta fra i due idle e' lo stato della macchina, non il
   sensore (vedi §5).
3. Le due fasi in transizione (`cool`, `idle2`) restano le peggiori (rapporto
   +1,5%): sono quelle in cui la potenza cambia durante la finestra, e li' il
   campione LHM puo' avere fino a ~0,30 s di eta' diversa dai bordi. Da
   dichiarare come risoluzione, non come errore.

## 4. Perche' il bug e' durato tre protocolli

Il rapporto dei **differenziali** pre-fix valeva 1,15, non 3,89 come gli
assoluti: un metodo A-B-A sottrae il livello medio, e il livello medio era
appunto l'offset da 53 W che rendeva gli assoluti assurdi. Integrare gradi al
posto di watt lascia passare una quota della variazione, e la quota che passa
ha la forma giusta (cresce col carico, scende nel cooldown). Peggio: il canale
sbagliato era **plausibile come temperatura** — 69,6 a riposo e 95,4 sotto 8
worker sono gradi realistici per un 13900HK; letti come watt sembravano solo
"un package caldo", mai un'impossibilita' fisica finche' non sono stati
confrontati con PL2 = 55 W. La prova diretta del canale e' nel probe del
percorso di lettura (commit 8aae3f9,
`lhm_pi_readpath_probe_20261023_132621.csv`): li' `_read_power_w_direct()`
valeva 64/68/67 nelle tre fasi idle/burn8/cool, cioe' la temperatura (con
inerzia: restava alta in cool a carico spento), mentre il sensore Power reale
valeva 9,37/18,78/11,37 W.
Morale metodologico (da portare in tesi, piu' importante della storia del
sensore): **un differenziale protegge dall'offset, non da un canale
sbagliato**; la coerenza interna di una serie (CV 1,2% sul carico) non e'
validita' della grandezza.

## 5. Stato della macchina e limiti

HWiNFO64 era stato chiuso alle ~15:05 (rimosso il carico dell'osservatore);
nessun altro monitoring. `ollama.exe` PID 16000 vivo ma modello non residente
(ultima inferenza 15:36, `keep_alive` 5 min esaurito): la trace non contiene
carico LLM. Il teardown pythonnet ha prodotto di nuovo l'eccezione CLR, ma
dopo la scrittura del CSV (il fix dell'harness sposta `SESSION.stop()` dopo il
salvataggio), quindi la traccia non puo' piu' andare persa.

Limiti: sempre **same-counter** (LHM ed EMI leggono `MSR_PKG_ENERGY_STATUS`
0x611) → nessuna arbitratura della scala assoluta; un solo run; nessuna
replica; la risoluzione temporale del canale LHM resta 0,30 s misurati, non
0,05 s dichiarati.

## 6. Riprodurre

```
# elevato; NON toccare il PC durante le fasi
python -u lhm_trace_3min.py
python lhm_trace_same_window.py experiment_results/lhm_emi_trace_<ts>.csv
```
