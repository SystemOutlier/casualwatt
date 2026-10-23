# Avvisi third-party — DLL vendorizzate

Questa cartella contiene binari di terzi usati dal backend energetico di
CasualWatt. Ogni voce dichiara qui lo stato di verifica della licenza alla
data del commit di questo file (2026-10-23).

## LibreHardwareMonitorLib.dll — MPL-2.0

- Opera: LibreHardwareMonitor (https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)
- Licenza: Mozilla Public License 2.0. Verificata il 2026-10-23 sul file
  `LICENSE` del repository upstream.
- Testo integrale della licenza: `MPL-2.0.txt` in questa cartella (copiato
  da https://www.mozilla.org/media/MPL/2.0/index.txt, 373 righe, Exhibit A/B
  inclusi; SHA-256 `3f3d9e00…b9d04`, verificata il 2026-10-23 contro il file
  ufficiale mozilla.org).
- Uso in CasualWatt: DLL **non modificata**, distribuita così come fornita,
  usata come *fallback* del canale energetico su Windows (il metodo
  principale è il contatore cumulativo EMI, `energy/emi_backend.py`).
- Nota MPL: il copyleft è a livello di *file* sorgente. Ridistribuendo la
  DLL non modificata senza apportare modifiche ai suoi sorgenti, non nasce
  alcun obbligo di rilasciare il codice di CasualWatt; gli obblighi sono
  (a) mantenere l'avviso di licenza MPL nei file sorgente della libreria,
  (b) rendere disponibile il testo della licenza — fatto da questo file e
  da `MPL-2.0.txt`, (c) indicare dove ottenere i sorgenti (URL sopra).

## HidSharp.dll e Microsoft.Win32.TaskScheduler.dll — licenza NON verificata

Sono presenti come dipendenze/caricabili a runtime della build vendorizzata
di LibreHardwareMonitorLib.

- `HidSharp.dll` (https://github.com/CodeCorp/HidSharp — il repository
  storico è stato ritirato): al 2026-10-23 la licenza **non è stata
  confermata** dai controlli fatti (ricerca GitHub ha restituito `NOASSERTION`).
- `Microsoft.Win32.TaskScheduler.dll` (https://github.com/dahall/TaskScheduler):
  licenza **non verificata** da noi su questo binario specifico.

Stato onesto: non asseriamo una licenza che non abbiamo letto sul binario.
Prima di qualsiasi distribuzione del pacchetto, verificare i sorgenti di
questi due assembly dalla build esatta da cui provengono (la build
vendorizzata qui è LibreHardwareMonitorLib 0.9.x, runtime osservato 0.9.4,
sorgente letto 0.9.6) e aggiungere in questo file il testo/URL della
licenza. Fino ad allora considerare questi due binari *non ridistribuibili
per certo*: usare la libreria in locale su questa macchina non pone
problemi, una distribuzione pubblica sì finché la licenza non è provata.

## Come viene usata la catena

1. Canale primario Windows: contatore cumulativo EMI (`emi-counter`), nessun
   binario di terzi.
2. Fallback: questa libreria (richiede token elevato per i sensori MSR).
3. Linux: RAPL (`energy/rapl_backend.py`), nessuna DLL.
