# Sonda PawnIO sul contatore MSR del package — 28/10/2026

Artefatti: `pawnio_probe_20261028.json` (run A) e `pawnio_probe_20261028_b.json`
(run B), prodotti con

```
python cwEnergyModular/tools/pawnio_probe.py --seconds 30 --out <file>
```

Host: Intel i9-13900HK, Windows 11, driver PawnIO in esecuzione, HVCI attivo
(`HypervisorEnforcedCodeIntegrity\Enabled = 1`). Run A: 23:38:59Z, run B:
23:39:35Z (28/10/2026 circa 01:39 locali). I moduli sono stati scaricati e
verificati con `cwEnergyModular/tools/fetch_pawnio_modules.py` (release 0.2.11,
SHA-256 dello zip `43608cb8…`, di `IntelMSR.bin` `d6ed85d6…`).

## 1. La sonda del backend passa

Dal campo `probe` dei due JSON (identico):

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

## 3. Costo di osservazione

| | run A p50 / p95 / p100 | run B p50 / p95 / p100 |
|---|---|---|
| lettura MSR (PawnIO) | 38,3 / 80,1 / 388,1 µs | 38,9 / 84,8 / 400,4 µs |
| lettura EMI (device) | 105,9 / 216,5 / 750,5 µs | 110,2 / 228,7 / 4181,0 µs |

La lettura del contatore via PawnIO costa circa **un terzo** di quella via
device EMI (mediana), e la coda e' piu' corta. Non e' un argomento per
sostituire il metodo in produzione: la catena resta EMI → PawnIO →
`unavailable`, e il cambio richiederebbe l'evidenza sperimentale che oggi non
c'e' (AGENTS.md, "Non sostituire il metodo in produzione").

## 4. Cosa questa prova non dice

- **Non** dice che la scala assoluta dei joule sia giusta: nessun wattometro
  ha partecipato.
- **Non** copre AMD: su questo host il produttore e' Intel e non esiste un
  secondo host AMD. Il ramo AMD (`0xC0010299`/`0xC001029B`, mai `0x611`) e' in
  `tests/test_pawnio_backend.py` con una libreria finta; l'esecuzione su CPU
  AMD resta **[V] da fare**.
- **Non** esercita riporto e reset reali: in 60 s complessivi il contatore a
  32 bit non si e' avvicinato al riporto (a ~12 W il riporto cade ogni ~6 h di
  macchina accesa) e nessun reset e' avvenuto. I due rami sono provati con
  letture finte.
- **Non** misura il costo di osservazione rispetto a un run senza sonda:
  misura solo la latenza della singola lettura.
