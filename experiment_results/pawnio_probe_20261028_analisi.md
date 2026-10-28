# Sonda PawnIO sul contatore MSR del package — 28/10/2026

Artefatti di questa campagna:

| file | cosa contiene |
|---|---|
| `pawnio_probe_20261028.json` (run A) | confronto EMI/PawnIO a finestra uguale, 30 s |
| `pawnio_probe_20261028_b.json` (run B) | replica del confronto, 30 s |
| `pawnio_aba_20261028.json` (run A) | A-B-A del costo di osservazione, 3 × 60 s |
| `pawnio_aba_20261028_b.json` (run B) | replica dell'A-B-A |
| `pawnio_priv_20261028_elevato.json` | apertura del driver con token elevato |
| `pawnio_priv_20261028_medio.json` | apertura con token UAC filtrato (integrita' media) |
| `pawnio_priv_20261028_safer.json` | apertura con token SAFER normal user |

Prodotti con

```
python cwEnergyModular/tools/pawnio_probe.py --seconds 30 --out <file>
python cwEnergyModular/tools/pawnio_probe.py --aba 60 --out <file>
python cwEnergyModular/tools/pawnio_priv_probe.py [--as-medium] --out <file>
```

Host: Intel i9-13900HK, Windows 11, driver PawnIO in esecuzione, HVCI attivo
(`HypervisorEnforcedCodeIntegrity\Enabled = 1`). I moduli sono stati scaricati
e verificati con `cwEnergyModular/tools/fetch_pawnio_modules.py` (release
0.2.11, SHA-256 dello zip `43608cb8…`, di `IntelMSR.bin` `d6ed85d6…`).

## 1. La sonda del backend passa

Dal campo `probe` dei JSON (identico in tutte le esecuzioni con token elevato):

| Controllo | Esito |
|---|---|
| servizio PawnIO | `running` |
| HVCI | `enabled` |
| firma del driver | `Valid`, firmatario `CN=Microsoft Windows Hardware Compatibility Publisher` |
| modulo | `IntelMSR.bin` 0.2.11, hash pinnato verificato |
| libreria | `PawnIOLib 2.0.0` (letta con `pawnio_version`, non assunta) |
| produttore | `intel` dal `VendorIdentifier` di Windows |
| unita' `0x606` | `0xA0E03` → campo `EU` = 14 → quantum 6,103515625e-05 J |
| contatore `0x611` | leggibile, 32 bit |

E' il primo passaggio della catena HVCI/firma su hardware reale: con HVCI
attivo il backend richiede firma valida **e** firmatario Microsoft, e il
driver installato soddisfa entrambi. I rami di rifiuto (firma non valida,
firmatario terzo con HVCI attivo o non determinabile, modulo assente, hash
diverso, produttore sconosciuto, servizio fermo) sono coperti da
`cwEnergyModular/tests/test_pawnio_backend.py`, non da questo host.

## 2. Il contatore si muove e coincide con EMI a finestra uguale

| | run A | run B |
|---|---|---|
| letture accoppiate | 594 | 593 |
| finestra del contatore MSR | 29,995194 s | 29,962716 s |
| Δ energia PawnIO | 357,065979 J | 333,337341 J |
| Δ energia EMI | 356,859638 J | 333,145339 J |
| potenza PawnIO | 11,9041 W | 11,1251 W |
| potenza EMI | 11,8973 W | 11,1187 W |
| rapporto PawnIO/EMI | **1,000578** | **1,000576** |
| differenza relativa | +0,0578 % | +0,0576 % |
| riporti / reset | 0 / 0 | 0 / 0 |

Il rapporto e' stabile fra i due run a meno di 2e-6 e il segno e' lo stesso:
il contatore MSR letto da PawnIO e' piu' alto di quello letto dal device EMI
di circa **5,8e-4**. La causa non e' determinata da questa sonda; il fatto
osservato e' che i due percorsi non coincidono esattamente pur leggendo lo
stesso registro. Non si attribuisce la differenza a un errore dell'uno o
dell'altro: la scala assoluta resta **non arbitrata** senza un wattmetro
AC/DC esterno, e questa prova **non** la arbitra (stesso registro, stessa
sorgente: un accordo qui e' coerenza di implementazione, non validazione
indipendente).

Il percorso PawnIO espone anche il valore esatto: i conteggi interi del
contatore (run A: 5.850.169 conteggi per 357,065979 J con quantum
6,103515625e-05 J). Il device EMI espone pWh. Il confronto fra le due unita'
e' quindi esatto a meno della conversione, ed e' il motivo per cui il campo
`raw_unit` della riga CSV distingue `pWh` da `counts (32-bit MSR)`.

## 3. Latenza della singola lettura

| | run A p50 / p95 / p100 | run B p50 / p95 / p100 |
|---|---|---|
| lettura MSR (PawnIO), nello stesso ciclo della lettura EMI | 38,3 / 80,1 / 388,1 µs | 38,9 / 84,8 / 400,4 µs |
| lettura EMI (device) | 105,9 / 216,5 / 750,5 µs | 110,2 / 228,7 / 4181,0 µs |

La stessa lettura MSR, misurata nel **thread del campionatore** (sezione 4),
ha mediana 82,5 µs nel run A e 89,3 µs nel run B: circa il doppio della
lettura nello stesso ciclo della EMI. La causa della differenza fra i due
contesti di chiamata non e' determinata da questa sonda e non si attribuisce.
In entrambi i casi la lettura sta oltre due ordini di grandezza sotto il tick
di 50 ms.

## 4. Costo di osservazione: A-B-A (due run)

La specifica §3.1.2 ammette `pawnio-counter` solo se il costo dell'osservatore
e' **misurato** con il metodo A-B-A, non dedotto. Il disegno e i criteri
numerici sono scritti nella docstring di `tools/pawnio_probe.py` **prima**
della misura: 30 s di assestamento, poi A1 (60 s, nessun campionatore
PawnIO), B (60 s, campionatore a 50 ms) e A2 (60 s). Le fasi sono contigue e
in tutte e tre EMI legge a 1 Hz come strumento, con la stessa cadenza: quel
costo si elide nella differenza.

| | run A | run B |
|---|---|---|
| P(A1) | 11,3980 W | 10,4505 W |
| P(B) | 11,5896 W | 10,8669 W |
| P(A2) | 10,6893 W | 11,0094 W |
| B − A1 | +0,1916 W | +0,4164 W |
| B − A2 | +0,9003 W | −0,1425 W |
| deriva \|A1 − A2\| | 0,7087 W | 0,5589 W |
| attribuibile (deriva < max differenza) | si' | **no** |
| verdetto dei criteri dichiarati | passa | **inconclusivo** |
| letture del campionatore | 1188 | 1189 |
| intervallo medio | 50,560 ms | 50,507 ms |
| latenza p50 nel campionatore | 82,5 µs | 89,3 µs |
| CPU del processo nella fase B | 0,250 s su 60 s (0,42 %) | 0,156 s su 60 s (0,26 %) |
| contatore avanzato in B | 696,051 J | 652,596 J |

Come si legge.

- Il run A passa i criteri dichiarati; il run B **non** li passa per la regola
  di attribuzione: la deriva A1-A2 (0,559 W) e' maggiore della differenza
  B-A2 (0,143 W). Non e' "costo nullo": e' una misura che a questo livello di
  rumore non distingue un effetto di pochi decimi di watt.
- Descrittivo, e **non** un criterio dichiarato prima: B sta sopra il punto
  medio di A1 e A2 di +0,546 W (run A) e +0,137 W (run B), con lo stesso
  segno. Si riporta come descrizione, non come superamento di una soglia.
- Il meccanismo e' misurato e non ambiguo: 1188-1189 letture in 60 s,
  intervallo medio 50,5-50,6 ms (+1,0-1,1 % sul bersaglio di 50 ms),
  0,156-0,250 s di CPU del processo nella fase B, cioe' 0,26-0,42 % di un
  core. Non si convertono quei secondi in watt: la conversione richiederebbe
  una potenza per core che qui non e' misurata.
- La fase B e' un **limite superiore**: in produzione gira un solo backend,
  qui EMI (1 Hz, strumento) e PawnIO (20 Hz, osservatore) insieme.

Conclusione: l'obbligo della specifica -- costo misurato con A-B-A -- e'
soddisfatto; il costo e' dell'ordine di pochi decimi di watt e il meccanismo
lo lega a 0,26-0,42 % di un core. La risoluzione del test di **livello** su
questo host e' ~0,6-0,7 W, perche' la potenza idle deriva di tanto in due
minuti: sotto quella soglia la prova non distingue, e le due misure non si
fondono in una sola stima.

## 5. Privilegi: la lettura richiede un processo elevato

L'obbligo "i privilegi si misurano, non si deducono" e' stato verificato con
`tools/pawnio_priv_probe.py` sotto tre token dello stesso utente, sullo stesso
driver e con la stessa configurazione (firma `Valid`, HVCI attivo in tutti):

| token | integrita' | gruppo Administrators | esito di `pawnio_open` |
|---|---|---|---|
| processo (shell elevata) | high | **enabled** | **apre**, `pass = true` |
| UAC filtrato (`--as-medium`, impersonificazione) | medium | deny-only | `access_denied` (0x80070005) |
| SAFER normal user (`runas /trustlevel:0x20000`) | high | deny-only | `access_denied` (0x80070005) |

Il campo `token_elevation` e' `true` in tutti e tre i token e **non**
distingue: il discriminante misurato e' lo stato del gruppo Administrators,
cioe' se il processo e' partito elevato. Il token SAFER ha la stessa
integrita' del token elevato e fallisce lo stesso, quindi il rifiuto non e'
una questione di livello di integrita'.

Conseguenza operativa, che la riga deve dichiarare: **il fallback
`pawnio-counter` richiede un processo elevato**, mentre `emi-counter` no. Il
backend distingue il caso con la ragione `access_denied` e la nota "il driver
richiede un processo elevato", invece di confonderlo con un driver rotto
(`pawnio_unavailable`). E' un motivo in piu' per cui EMI resta primo in
catena.

Il caso "medium" e' provato per impersonificazione, non con un processo figlio:
il controllo di accesso su un handle usa il token efficace del thread, quindi
l'esito e' lo stesso, ma la forma dell'esperimento va detta.

## 6. Cosa queste prove non dicono

- **Non** dicono che la scala assoluta dei joule sia giusta: nessun wattometro
  ha partecipato.
- **Non** coprono AMD: su questo host il produttore e' Intel e non esiste un
  secondo host AMD. Il ramo AMD (`0xC0010299`/`0xC001029B`, mai `0x611`) e' in
  `tests/test_pawnio_backend.py` con una libreria finta; l'esecuzione su CPU
  AMD resta **[V] da fare**.
- **Non** esercitano riporto e reset reali: in 60 s il contatore a 32 bit non
  si e' avvicinato al riporto (a ~12 W il riporto cade ogni ~6 h) e nessun
  reset e' avvenuto. I due rami sono provati con letture finte.
- **Non** misurano il costo di osservazione sotto carico: le fasi A-B-A sono
  idle, come la prova analoga fatta per LHM. Sotto carico il livello e' piu'
  alto e la deriva relativa diversa, e il numero non si trasporta.
- **Non** stabiliscono se il rifiuto `access_denied` dipenda dal DACL del
  device o da un controllo interno del driver: si e' misurato l'esito, non la
  causa nel driver.
