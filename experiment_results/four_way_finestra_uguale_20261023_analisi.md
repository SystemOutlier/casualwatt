# Four-way a finestra uguale: il divario LHM/EMI sul load era il campionamento dell'harness

Run arbitranti: `four_way_20261023_145041.{csv,json}` e
`four_way_20261023_144252.{csv,json}` (replica), con la prova dell'integrale in
`four_way_20261023_145041_pi.csv`.
Macchina: MINI_IT13, i9-13900HK, Windows 11, guscio elevato, Ollama
`llama3.2:3b`, `num_predict 32`, `temperature 0`. Scalata A-B-A: idle 45 s ->
load 90 s -> idle2 45 s, tick 1 Hz.

## 1. Verdetto

Dopo la correzione del percorso di lettura (`energy_session.py`
`_read_power_w_direct`, commit `1422d1b`) e portando le due sorgenti sulla
**stessa finestra temporale**, CasualWatt/LHM e il contatore EMI coincidono
**entro l'1% su ogni fase**: 0,9986 (idle), 1,0082 (load), 0,9947 (idle2) nel
run `145041`; 0,9967 / 1,0055 / 1,0040 nella replica `144252`.

Il `1,16` che era sopravvissuto al fix **non era una pendenza del sensore**:
era l'artefatto del confronto fra un campione istantaneo LHM e una media EMI
su intervalli disuguali. Nello stesso identico run, con lo stesso buffer e lo
stesso contatore, il confronto istantaneo vale 1,1284 sul load e 1,0204/0,9739
sulle idle.

## 2. Che cosa e' cambiato nel confronto

Prima, per ogni tick, si prendeva `lhm_w` = ultimo campione del buffer e lo si
confrontava con `ΔpWh / Δtempo` fra due tick. Sul load il tick e' bloccato
dalla richiesta Ollama: l'intervallo fra tick vale **4,03 s** (mediana) contro
1,001 s delle fasi idle, e il campione LHM e' letto in un istante privilegiato
appena dopo il ritorno della generazione. Due finestre diverse, non a
comparare.

Ora, per ogni fase:

1. finestra = `[inizio fase, fine fase]` sull'asse `time.monotonic` (`mono`,
   ora colonna del CSV dei tick), intersecata con l'asse dei tick disponibili;
2. LHM = regola trapezoidale sul buffer del thread di produzione snapshottato
   ai confini di fase (`cw_J_fase`, bordi `cw_t0_mono` / `cw_t1_mono`);
3. EMI = contatore cumulativo `pWh` **interpolato linearmente** sull'asse `mono`
   dei tick, stessi bordi (`emi_J_finestra_uguale`) - stesso metodo
   `counter_at` gia' usato in `srum_emi_perminute.py`;
4. rapporto dei soli Joule: la durata si cancella, perche' e' identica.

Due buchi dell'implementazione precedente, entrambi misurati e chiusi:

- `four_way_20261023_142253`: l'integrazione per intervallo chiedeva la
  copertura fino al bordo destro del tick, che il buffer non aveva mai (l'ultimo
  campione del thread PI e' sempre ~0,3 s prima): **114 righe su 114** con i
  campi `cw_*` nulli. Sostituita dall'integrazione di fase con clip
  `ritagliato_s` dichiarato.
- `four_way_20261023_143603`: idle2 senza numeri. Il bordo destro
  dell'ultima fase coincide con l'ultimo tick; `round(mono, 3)` su un valore
  registrato a 4 decimali lo spostava fuori dall'asse del contatore e
  l'interpolazione ritornava `None`. In quel JSON la `cw_win_note` di idle2
  dice "buffer di integrazione non copre la finestra della fase": **e'
  fuorviante**, il buffer copriva (le altre due fasi dello stesso run hanno
  `cw_ritagliato_s` 0,325 e 0,316) e infatti tutti i campi `cw_*` di idle2 sono
  nulli perche' il fallimento dell'interpolazione azzerava anche la diagnostica
  dei bordi. Ora i bordi non passano piu' dalla formattazione e `cw_win_note`
  distingue i due casi (asse dei tick vs copertura del buffer).

## 3. I due run a finestra uguale

| fase | J LHM (145041) | J EMI (145041) | rapporto | rapporto (144252) | confronto istantaneo |
|------|---------------:|---------------:|---------:|------------------:|---------------------:|
| idle | 534,47 | 535,21 | 0,9986 | 0,9967 | 1,0204 |
| load | 2079,71 | 2062,84 | 1,0082 | 1,0055 | 1,1284 |
| idle2 | 550,34 | 553,24 | 0,9947 | 1,0040 | 0,9739 |

Potenze di fase (`145041`): EMI 11,84 / 22,62 / 12,54 W sui soli tick;
LHM integrato a finestra uguale 11,93 / 22,67 / 12,48 W; LHM istantaneo sui
tick 12,25 / 25,41 / 12,54 W. Offset LHM-EMI sugli assoluti: **+0,21 W**
(145041), +0,27 W (144252), +0,22 W nel probe `lhm_readpath_probe_20261023_132621`
- prima del fix era +54,5 W perche' si integrava la temperatura.

Differenziale A-B-A sulla finestra identica: LHM 960,6 J contro EMI 939,0 J ->
**1,023** (144252: 818,6 contro 808,2 -> 1,0129). Il residuo ~1-2% e' tutto
nella baseline: si sottraggono ~12 W per ~92 s, quindi 0,2 W di differenza fra
le due letture della baseline diventano ~19 J.

## 4. Perche' i J/token restano instabili (e non e' colpa del sensore)

| grandezza | 144252 | 145041 |
|---|---:|---:|
| token | 736 | 736 |
| EMI J/token (delta contatore / tempo meter) | 1,0308 | 1,1976 |
| EMI J/token (finestra di fase) | 1,0981 | 1,2758 |
| LHM J/token (finestra di fase) | 1,1122 | 1,3052 |
| rapporto LHM/EMI (finestra di fase) | 1,0129 | 1,0230 |

Il numero assoluto cambia del 16% fra due run consecutivi della STESSA
sorgente, perche' la baseline A-B-A dipende dallo stato termico: in `144252`
idle2 valeva 14,49 W (coda termica dopo il load) contro 12,54 W in `145041`.
Il **rapporto fra le sorgenti invece e' stabile** (1,013 / 1,023).
Conseguenza per la tesi: la metrica va ancorata a un protocollo che fissa il
**numero di richieste**, non la durata - la durata fissa fa cadere un numero
diverso di richieste per finestra (736 token in 84,5 s di span dei tick, con
richieste da ~4 s), e ogni richiesta mezza fuori dalla finestra sposta i
J/token. Era gia' emerso dal secondo run del 23/10 (12:08: 0,996 -> 1,173
J/token con -12,5% di token/finestra); qui si vede che il problema sopravvive
alla correzione del sensore perche' non e' del sensore.

## 5. Revisione indipendente

`four_way_pi_audit.py` (codice separato, riscritto da zero) rilegge i CSV
committati e ricalcola gli integrali sui bordi dichiarati nel JSON:

```
run 20261023_145041 | buffer 662 campioni, dt mediano 0.283 s (il thread dichiara 0,05 s: 5.7x piu' lento)
fase     J_LHM_audit  J_LHM_json   scarto  J_EMI_audit  J_EMI_json  rap_audit  rap_json  modo_debole
idle          534.48      534.47  +0.001%       535.21      535.21     0.9986    0.9986       1.0204
load         2079.71     2079.70  +0.000%      2062.84     2062.84     1.0082    1.0082       1.1284
idle2         550.34      550.34  +0.001%       553.25      553.24     0.9947    0.9947       0.9739
VERDETTO: coerente
```

Serve perche' il JSON e' scritto dallo stesso codice che calcola i numeri: da
solo non e' una verifica.

## 6. Difetto nuovo, misurato ma NON corretto: il thread PI campiona 6x piu' lento del dichiarato

`POWER_SAMPLE_INTERVAL_S = 0.05` (`energy_session.py:45`) e i docstring che
promettono "campioni CPU Package ogni 0,05 s" (`:849`, `:898`, `:904`, `:1107`,
`:1203`) non reggono su questa macchina: il thread fa `wait(0.05)` **dopo** la
lettura (`:869`), e `_read_power_w_direct` scorre tutto l'hardware chiamando
`hw.Update()` su ogni hardware finche' non trova il sensore. Periodo reale
misurato dal buffer snapshottato: **0,28-0,30 s** (662 campioni sui 182,4 s di
run; 156-301 per fase). Cinque-sei volte piu' lento del dichiarato.

Impatto sui numeri di questo documento: nessuno rilevabile - l'integrale
trapezoidale a 3,5 Hz su finestre da 45-92 s coincide col contatore a meno
dell'1%. Impatto sul progetto: (a) la documentazione del backend dice una
frequenza falsa, (b) le finestre corte (le `pi_window_energy_j` usate per
escludere sottofinestre) hanno una risoluzione di ~0,3 s, non 0,05 s, (c) il
limite del buffer (4000 campioni) tiene ~19 minuti di storia, non 200 s come
farebbe pensare la soglia letta a 0,05 s. **Non ho toccato nulla**: serve una
decisione (ottimizzare la lettura memorizzando l'oggetto sensore, oppure
aggiornare la spec/docstring a 0,3 s) e, se si ottimizza, una prova che il
rapporto resti ~1,00.

## 7. Cosa vale e cosa non vale

Vale: il percorso software di CasualWatt su Windows (selezione del sensore,
lettura, integrazione trapezoidale, finestra) riproduce il contatore EMI entro
l'1% su idle, load e idle2, e la differenza e' stabile fra run. Il fissato di
`1422d1b` era quindi il difetto, non una approssimazione accettabile.

Non vale: **non e' una validazione indipendente della scala assoluta.** LHM
(`IntelCpu.cs:28/480/687-698`) e l'IOCTL EMI consumano lo stesso
`MSR_PKG_ENERGY_STATUS` (0x611) via lo stesso driver di Windows: qui si e'
arbitrato il software di lettura, non l'hardware. Per la scala restano il
wattometro a parete e il dual-boot Linux/RAPL
(`VALIDAZIONE_LINUX_RAPL_CHECKLIST.md`).

Non arbitrano nulla, e restano nel JSON solo come termini metodologici:
CodeCarbon (modello `cpu_load`, 10,77 W base / 26,61 W load in 145041 - non una
misura) e HWiNFO, che in questi run **non c'era**: Shared Memory non esposta
(`OpenFileMappingW` -> err=2), quindi tre sorgenti come dichiarato in
`hwinfo: "ASSENTE"`.

Bound dell'interpolazione ai bordi: la finestra di fase si estende ~4 s oltre
gli ultimi tick (bordi interpolati), mentre `emi_J` copre solo lo span dei
tick. Le due potenze EMI del load differiscono di 22,619 contro 22,484 W,
cioe' **0,6%**: quell'ordine di grandezza e' l'errore introdotto
dall'interpolazione lineare del cumulato sul bordo.

I tre run intermedi sono committati come traccia, non come risultato:
`141524` (primo four-way dopo il fix: offset +0,22 W, ma ancora senza la
colonna `mono` e senza integrazione a finestra uguale), `142253` (il difetto
dei `cw_*` nulli) e `143603` (il difetto di arrotondamento su idle2).
`144252` e' la replica del metodo corretto; `145041` e' quello usato per le
tabelle.

## 8. Come riprodurre

```
# shell elevata (LHM legge 0 senza Admin)
python four_way_test.py                 # ~4 min, scrive i tre file + log
python four_way_pi_audit.py             # ricalcola gli integrali dai CSV
```

Il thread di integrazione vive dentro `SESSION.start()`: lo snapshot del buffer
avviene alla fine di ogni fase, prima di `SESSION.stop()`. Dal run `145041` il
buffer e' scritto come serie unica deduplicata (`mono;w`), perche' gli snapshot
per fase sono cumulativi (il buffer non si azzera fra le fasi); in `144252`
lo stesso dato e' nel formato precedente `fase;mono;w`, con le righe ripetute
fra le fasi - per ricalcolare un integrale da quel file servono prima le
`uni = {}` per chiave `mono`, come fa il writer nuovo.
`four_way_pi_audit.py` legge il formato `mono;w` e non accetta il vecchio.
