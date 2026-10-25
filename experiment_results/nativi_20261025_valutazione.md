# nativi.DOCX — valutazione, 2026-10-25

Materiale valutato: `nativi.DOCX` (radice del repository, non tracciato). Il testo
e' una risposta di assistente: le sue citazioni sono segnaposto
`[ppl-ai-file-upload.s3.amazonaws]`, quindi e' trattato come **spunto, non come
evidenza**. Ogni affermazione qui sotto e' verificata contro il codice o un
artefatto tracciato il 25/10/2026.

## 1. Cosa il documento azzecca

- **EMI misura il dominio, non il processo.** Corretto, ed e' il nostro canale
  primario (`energy/energy_session.py:49-50`, `:210`).
- **L'attribuzione al processo e' una stima, non una misura.** Corretto, ed e'
  gia' la formulazione della tesi: eq. (3.3),
  `Tesi-latex/qoder-bozza/capitoli/cap03_metodologia_misura.tex:426-459`, e
  cap. 5 §validita' di costrutto, `cap05_valutazione_sperimentale.tex:1186-1195`
  ("attribuita, non prelevata").
- **Nessuna percentuale di accuratezza (95-98%) senza un riferimento
  indipendente.** Corretto e coerente con P4.9/P4.10 del protocollo.
- **Licenze.** EMI/PDH/WMI sono API di sistema; NVML non e' in gioco su questo
  host (nessuna NVIDIA); CodeCarbon e' MIT. Manca l'unica componente che il
  nostro progetto usa davvero in fallback, LibreHardwareMonitor MPL-2.0, gia'
  dichiarata nella tesi.
- **Posizionamento.** L'innovazione non e' "usare EMI" ma l'integrazione con
  baseline misurata, separazione modello/judge e multi-tier: e' la stessa tesi
  del cap. 1 e del confronto con CodeCarbon nel protocollo.

## 2. Quattro correzioni da non importare

### 2.1 La formula proposta non sottrae la baseline

Il documento propone

    E_Ollama = E_PKG · CPU_ollama / CPU_totale

mentre la nostra grandezza attribuita e'

    E_active = max(E_PKG − P_idle · Δt, 0)
    E_Ollama = E_active · s

(`energy/local_energy.py:300-310`, `:342-351`). La differenza non e' cosmetica:
la formula del documento attribuisce al modello anche una quota della potenza
idle, cioe' produce una stima piu' alta proprio della grandezza che la
definizione di `E_active` toglie. Se l'obiettivo e' l'energia incrementale, la
baseline va sottratta **prima** di applicare la quota.

### 2.2 "CPU_totale" e' il denominatore che abbiamo gia' misurato come sbagliato

Con i core-secondi totali, che includono `System Idle Process`, la quota
dell'albero Ollama e' 0,50; con il tempo non-idle e' 0,7339
(`experiment_results/srum_emi_cross_20261023_analisi.md:141-154`,
`cap05_valutazione_sperimentale.tex:265-272`). Il modello EPI di Windows
attribuisce 0,7361: la differenza fra 0,50 e 0,73 non e' un dettaglio, e' un
fattore 1,47 sull'energia attribuita. Il codice usa `d_busy_s` e
`cpu_busy_capacity_cores` (`energy/local_energy.py:342-350`;
`casualwatt_csv_export.py:79`, `:107`): chi implementasse la formula del
documento alla lettera reintrodurrebbe l'errore corretto il 23/10.

### 2.3 "Tempo CPU di Ollama" non e' il processo `ollama`

Il worker che esegue l'inferenza e' `llama-server.exe`, non il launcher. Con il
needle `"ollama"` la quota misurata era 0,0011 contro 0,7361 del modello EPI
(`srum_emi_cross_20261023_analisi.md:158-162`): un millesimo dell'energia.
Noi leggiamo l'albero ricorsivo dei PID
(`energy/energy_session.py:38`, `:1761-1775`;
`energy/local_energy.py:550-577`). Una raccolta PDH/WMI per nome "Ollama"
fallirebbe nello stesso modo; non e' un problema di API ma di insieme di
processi.

### 2.4 SRUM non e' un canale per-richiesta, e il suo campo per-processo e' EPI

- Il dump `powercfg /srumutil` richiede una shell elevata
  (`srum_emi_cross.py:49`, `:244`) e costa CPU; va chiamato ai confini di fase,
  mai nel tick (`srum.py:45-46`).
- I bucket sono al minuto e vengono **compattati in un record orario** a ogni
  boundary di epoch, misurato alle :32 (`srum_emi_cross_20261023_analisi.md:42-52`).
  Una richiesta dura secondi: SRUM non puo' risolverla.
- Le righe di package non sono per-processo: nei 34156 record del dump, i 596
  valori non-zero di `EmiEnergyConsumption` sono **tutti** pseudo-AppId
  `EMI_RAPL_Package0_PKG/_PP0/_PP1`, con `CPUEnergyConsumption = 0`
  (`srum_emi_cross_20261023_analisi.md:16-18`). Il campo per-processo
  `CPUEnergyConsumption` e' il modello EPI di Windows, un'attribuzione
  (`srum.py:47-48`; analisi §6). "SRUM da' l'energia del processo" e' quindi
  vero solo con due qualifiche: e' una stima e non e' il contatore EMI.
- `MeasuredPower` non compare fra le colonne del CSV esportato da
  `powercfg /srumutil /output` (header di
  `experiment_results/srum_dump_20261023_121718_start.csv`). L'affermazione del
  documento resta **non verificata**: non va citata senza una fonte primaria.

## 3. Il protocollo di validazione proposto: cosa e' utile e cosa no

Il documento propone di confrontare la stima con

    E_incrementale = E_PKG(con Ollama) − E_PKG(idle)

usando bias, MAE, RMSE, errore relativo e intervallo di confidenza su almeno 10
configurazioni. La prima grandezza coincide con il nostro `E_active`; ma
confrontare `E_active · s` con `E_active` non misura l'accuratezza
dell'attribuzione: misura la **copertura** dell'attribuzione, cioe' `s`. Il bias
relativo atteso e' `s − 1` per costruzione (≈ −0,27 nella nostra misura) e non
e' un errore del metodo. Con "Ollama unico processo attivo" la stima si avvicina al
riferimento solo se anche il resto del sistema e' fermo; non e' il caso di
Windows, dove il tempo busy include kernel e servizi.

L'anello 4 di P4.9 usa un riferimento diverso e piu' onesto: un'altra
attribuzione dichiarata come tale, il modello EPI, 0,7339 contro 0,7361
(`protocollo_v4_20261024.md:2116`). Quell'accordo arbitra la **procedura**
(insieme dei processi e denominatore), non l'equivalenza tempo ↔ energia, che
resta assunzione dichiarata. Anche MAE/RMSE contro EPI misurerebbero soprattutto
la differenza fra due modelli basati entrambi sul tempo CPU: non sono una
validazione contro l'hardware.

## 4. Cosa vale la pena fare

Nessuna modifica al codice di produzione: P5 non e' congelato e il sorgente e'
bloccato. Le proposte sono per P5/P6.

1. **Ripetere l'anello 4 su piu' configurazioni (≥ 10).** E' la parte
   difendibile della proposta del documento, ma con il riferimento EPI e non con
   `E_active`. Si riporta la distribuzione di `s − s_EPI` su modelli,
   `num_predict` e livelli di concorrenza, con una banda di accordo
   preregistrata; nessuna soglia si sposta dopo i dati. Questo trasforma un
   confronto singolo in un test di ripetibilita' della procedura.
2. **Automatizzare l'estrazione EPI per fase in un harness tracciato.** Oggi
   l'anello 4 si ricostruisce da `srum_emi_cross.py` e `cpu_share_check.py`;
   un harness che produce direttamente `s_EPI` e `s_busy` per fase rende
   l'anello rigenerabile. `MeasuredPower` entra solo se una fonte primaria ne
   documenta il significato e il CSV lo espone.
3. **Dichiarare il cambio dell'albero PID.** Se un runner **muore** fra
   `t_start` e `t_end`, la lettura a `t_end` non lo trova e il suo tempo CPU va
   perso senza segnalarlo (un runner che nasce e' invece catturato, perche' a
   `t_start` valeva zero). Un flag per riga (`engine_tree_changed`) e il divieto
   di usare `direct_cpu_delta` quando l'insieme dei PID cambia rendono il
   degrado visibile invece che silenzioso. La campagna v4 mitiga il caso con
   `keep_alive` fissato, ma la produzione no.
4. **Non migrare a PDH/WMI.** `psutil.Process.cpu_times()` legge
   `GetProcessTimes`, la stessa contabilita' nativa da cui PDH deriva
   `% Processor Time`; passare a PDH aggiungerebbe un sottosistema di
   campionamento senza un campo nuovo. La correzione necessaria era
   l'insieme dei processi e il denominatore, non l'API.

## 5. Verdetto

Il documento conferma l'architettura (EMI di dominio + quota di tempo CPU
dichiarata come stima) e la cautela sull'accuratezza, ma le tre formule/identita'
operative che propone sono incomplete o sbagliate sui nostri dati: baseline non
sottratta, denominatore che include l'idle, processo sbagliato. L'unico
contributo originale e' la richiesta di ripetere il confronto su piu'
configurazioni, che va adottata con il riferimento EPI e non con l'incremento
del package.

## Ancoraggi

- `Tesi-latex/qoder-bozza/capitoli/cap03_metodologia_misura.tex:426-459`
  (eq. 3.3 e assunzione tempo ↔ energia).
- `Tesi-latex/qoder-bozza/capitoli/cap05_valutazione_sperimentale.tex:256-272`
  (SRUM come secondo consumatore e quota 0,7339 / 0,7361), `:1186-1195`
  (grandezza attribuita, riferimento esterno mancante).
- `cwEnergyModular/energy/local_energy.py:300-310`, `:342-351`, `:550-577`.
- `cwEnergyModular/energy/energy_session.py:38`, `:1761-1775`.
- `cwEnergyModular/casualwatt_csv_export.py:79`, `:107`.
- `experiment_results/srum_emi_cross_20261023_analisi.md:16-18`, `:42-52`,
  `:133-162`.
- `experiment_results/protocollo_v4_20261024.md:2112-2120` (P4.9/P4.10,
  anello 4).
- `srum.py:45-48`, `srum_emi_cross.py:49`, `:244`.
- `experiment_results/srum_dump_20261023_121718_start.csv` (header).
