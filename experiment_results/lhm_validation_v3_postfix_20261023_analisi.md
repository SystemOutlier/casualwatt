# Rilancio del protocollo v3 col percorso di lettura corretto — analisi

Run: `experiment_results/lhm_validation_v3_20261023_153604.{csv,json,md}`
(console integrale in `lhm_v3_postfix_console.txt`, con errori in
`lhm_v3_postfix_err.txt`, vuoto).
Eseguito 2026-10-23 **15:09:56 → 15:36:04** (26 min 08 s), processo elevato,
MINI_IT13.

## 1. Verdetto

Il protocollo v3 **non e' stato cambiato**: stessi knobs (`llama3.2:3b`,
`num_predict=128`, 8 run × 15 inferenze, baseline 30 s × 2, cooldown 15 s),
stesso script `experiment_validate_lhm.py`, stesse colonne. E' cambiato solo il
percorso di lettura di `energy_session` (fix 1422d1b, guard su `SensorType ==
Power`). Il numero che ne esce e' lo stesso esperimento espresso in watt invece
che in gradi.

| | v3 pre-fix (22/10 01:07) | v3 post-fix (23/10 15:36) |
|---|---|---|
| P_base (A-B-A) | 73,37 "W" | **11,55 W** |
| P_load | 79,53 "W" | **28,33 W** |
| segnale ΔP = P_load − P_base | 6,16 | **16,78** |
| E_inc | 731,4 J (CV 13,72%) | **1778,7 J (CV 11,02%)** |
| J/token | 0,5245 (CV 13,73%) | **1,2862 (CV 8,99%)** |
| IC95 J/token | [0,467; 0,582] | [1,194; 1,379] |
| intervallo PI misurato | 0,3224 s | **0,3025 s** |
| finestre exact-counter | 0/24 | **0/24** (invariato) |

I valori post-fix stanno sulla linea delle altre tre sorgenti dello stesso
package (EMI 12-23 W, SRUM idem, HWiNFO 15-19 W a riposo, PL1 35 / PL2 55 W):
`experiment_results/four_way_finestra_uguale_20261023_analisi.md`.

## 2. La prova numerica del bug, senza retorica

Il sensore che la produzione integrava era la temperatura di package. Il
prodotto "°C × secondi" ha una firma precisa, visibile in questa tabella: a
carico spento vale ~73 e a carico pieno ~79,5, cioe' un **segnale di 6 unita'**
per un gradino elettrico che vale 16,8 W. La temperatura di un 13900HK a 28 W
non si muove di 6 gradi in 100 secondi; il package elettrico si muove del 60%.
Nello stesso run pre-fix il CV del carico era 1,18%: la serie "assomigliava" a
una misura perche' il termico e' liscio, ed e' esattamente per questo che la
scala sbagliata e' passata inosservata per tre protocolli.

## 3. Il rumore e' tutto nella baseline (misurato, non ipotizzato)

Per-run J/token e P_base(A-B-A), nello stesso ordine dei run:

| run | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| P_base (W) | 14,13 | 12,25 | 11,66 | 11,48 | 10,77 | 10,95 | 11,47 | 9,67 |
| J/token | 1,0489 | 1,2175 | 1,3158 | 1,2790 | 1,3794 | 1,3156 | 1,2989 | 1,4341 |

- correlazione J/token ↔ P_base: **r = −0,982** (8 punti);
- correlazione J/token ↔ numero del run: r = +0,808 (piu' debole: la "deriva
  termica" segnalata nel v3 pre-fix era questo, cioe' la baseline che scende
  man mano che la macchina si stabilizza, non il carico che cambia);
- P_load e' stabile: 28,33 W con **CV 1,06%** su tutti i run;
- previsione analitica del modello "rumore = baseline": sd(P_base) = 1,29 W su
  un segnale di 16,78 W → CV attesa **7,7%**, osservata **8,99%**. Il modello
  predice bene anche questo run, come prediceva v2 e v3 pre-fix.
  (Attenzione alle due CV di P_base che circolano: il report generato dallo
  script dice **22,5% perche' campiona le 16 finestre singole** A e B; qui la
  propagazione usa la media A-B-A per run, 8 valori, sd 1,29 W = CV **11,2%** —
  ed e' quella che entra nel predittore, perche' E_inc sottrae la media delle
  due.)

Il run 1 e' un outlier con causa nota e dichiarata: la sua BASE_A vale 18,78 W
perche' arriva subito dopo il warm-up (3 inferenze) e i worker di Ollama non
hanno ancora parcheggiato (`keep_alive` default 5 min), mentre la BASE_B vale
9,47 W. Escludendo il run 1: J/token medio **1,320**, CV **5,29%** (6 run).
Non e' stato escluso nella statistica pubblicata, che resta quella del
protocollo intero.

## 4. Cosa NON vale ancora

1. **La scala assoluta non e' arbitrata.** Il canale LHM "CPU Package" e il
   contatore EMI leggono lo stesso `MSR_PKG_ENERGY_STATUS` 0x611: la loro
   coincidenza e' una validazione del software di lettura, non della scala.
   Servono dual-boot Linux/RAPL (checklist in `VALIDAZIONE_LINUX_RAPL_CHECKLIST.md`)
   e il wattometro a parete.
2. **Il contatore esatto resta irraggiungibile**: 24/24 finestre in
   `counter-delta-fallback`, intervallo reale del thread PI **0,3025 s** contro
   0,05 s dichiarati. Numero identico al 22/10 (0,3224 s): non e' una
   scoperta di oggi e non e' peggiorato.
3. **J/token non e' scale-invariant ne' cross-protocollo**: 1,2862 qui
   (burst 15 × 128 tok, ~107 s di carico) contro 1,03-1,20 EMI nel four-way
   (24 req × 32 tok, ~86 s) e 0,957 nei test EMI dell'utente (30 req × 32 tok).
   Confrontabile solo a protocollo identico.
4. **La baseline e' un parametro del protocollo**, non una costante di
   macchina: qui vale 11,55 W "sistema con Ollama caldo"; i ±8-30% gia'
   misurati sul differenziale al variare della finestra di riferimento
   (SRUM × EMI, commit 580c796) restano il limite principale da dichiarare.

## 5. Stato della macchina durante il run

Chiuso HWiNFO64 (PID 10592, attivo dalle 12:26) prima del run per togliere il
carico dell'osservatore dalla misura — le tre righe di calibrazione idle
(13,16 / 13,70 / 15,49 W) e il calo progressivo della baseline sono coerenti
con una macchina che si stabilizza dopo la chiusura. Nessun altro processo di
monitoring. `ollama.exe` PID 16000 (avviato 13:51, preesistente) = unico
servizio LLM; modello `llama3.2:3b` residente dopo il warm-up. Smoke test del
percorso di lettura eseguito prima del run
(`smoke_test_readpath.py`, commit 5a0c329): sensore scelto
`CPU Package` di tipo **Power**, lettura a riposo **15,18 W**.

## 6. Come riprodurre

```
# processo ELEVATO (i sensori Power LHM sono invisibili senza Admin)
C:\Users\Massimo\AppData\Local\Python\pythoncore-3.14-64\python.exe -u \
    experiment_validate_lhm.py
```

Default = v3. Le varianti si scelgono con le variabili d'ambiente
`CW_EXP_RUNS`, `CW_EXP_INF`, `CW_EXP_NUMPREDICT`, `CW_EXP_BASELINE_S`,
`CW_EXP_COOLDOWN_S` (v2 = 5 run × 5 inferenze, non ancora rilanciata). Il
teardown pythonnet **e' accaduto anche qui**: `lhm_v3_postfix_err.txt` (1089 B)
contiene l'eccezione CLR non gestita (`InternalPythonnetException` su
`NullReferenceException`, `Python.Runtime.TypeManager.AllocateTypeObject`),
pero' **dopo** la stampa di RISULTATI e dopo la scrittura di CSV/JSON/MD (tutti
e tre con timestamp 15:36:04): il blocco `finally` dello script salva prima che
il processo muoia, quindi i dati sono integri. Il processo, essendo distaccato
(`Start-Process`), non ha un codice d'uscita osservabile da questa console; sui
run foreground lo stesso difetto dà exit 127.
