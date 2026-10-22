# Validazione Linux/RAPL — checklist operativo (MINI_IT13, i9-13900HK)

Scopo: eseguire `experiment_validate_lhm.py` (protocollo v3 invariato:
A-B-A, 15 inferenze x 8 run, num_predict 128) con backend **rapl**
(`/sys/class/powercap`) e confrontare J/token con i dati Windows
`experiment_results/lhm_validation_v3_20261022_010741.*`
(J/token 0,5245 CV 13,7%, IC95 [0,467; 0,582]).

Perche' NON una VM (VMware/HOL): i contatori RAPL sono del package FISICO;
il guest non vede `/sys/class/powercap` (o vede valori virtualizzati) →
ambiente non valido per misurare. La VM va bene SOLO per testare il
degrado `unavailable` e il simulatore CW_ENERGY_FILE.

## 1. Preparazione (da Windows, oggi)

- [ ] Scrivere chiavetta Ubuntu 24.04 Desktop (≥ 8 GB) con Rufus/balenaEtcher.
- [ ] Copiare nella chiavetta (o su una seconda partizione exFAT):
  - la cartella `CWProject` **senza** `dll` inutili (basta: `cwEnergyModular/`,
    `experiment_validate_lhm.py`, `experiment_results/` per riferimento);
  - questo file.
- [ ] Scaricare l'installer Ollama per Linux e tenerlo offline (opzionale,
  se il Wi-Fi in dual/USB non fosse disponibile):
  `curl -fsSL https://ollama.com/install.sh -o ollama_install.sh`
- [ ] Nota: i modelli si scaricano da hub (llama3.2:3b ≈ 2 GB) → serve rete.

## 2. Avvio da Ubuntu live (Try Ubuntu)

- [ ] Alimentatore inserito; non toccare il PC durante la run.
- [ ] `ls /sys/class/powercap/` → attendersi `intel-rapl:0`, `intel-rapl:1`...
- [ ] `sudo cat /sys/class/powercap/intel-rapl:0/energy_uj` → numero che
      SALE leggendo due volte (contatore cumulato, µJ). Se il file non
      esiste: RAPL bloccato dal firmware (su questo portatile Windows lo
      leggeva via firmware, quindi attendiamo presente; dichiarare se assente).
- [ ] Identificare il dominio package:
  `for f in /sys/class/powercap/intel-rapl:*/; do echo $f $(cat $f/name 2>/dev/null); done`
  → cercare `package-0`.

## 3. Dipendenze (sessione live, tutto in RAM)

```bash
sudo apt update && sudo apt install -y python3-pip
sudo apt install -y python3-psutil python3-requests || \
    pip install --break-system-packages psutil requests
# NOT needed su Linux: pythonnet/LHM/DLL (activation e' platform-gated)
```

- [ ] `python3 -m pytest cwEnergyModular/tests/ -q` → attendersi tutti
      passed con `rapl` attivo (backend reale, non mock).

## 4. Ollama + modello

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:3b
ollama run llama3.2:3b "ciao" --verbose   # smoke test (poi Ctrl+D)
```

- [ ] `curl http://localhost:11434/api/tags` risponde.

## 5. Run esperimento (~30 min, come root per RAPL)

```bash
cd <cartella CWProject copiata>
sudo -E python3 experiment_validate_lhm.py
```

- [ ] Header atteso: `Metodo: rapl` (se `unavailable` → fermare, permessi).
- [ ] Attendere il termine: `RISULTATI` + file
      `experiment_results/rapl_validation_v3_<ts>.{csv,json,md}`.
- [ ] Copiare i file `rapl_validation_v3_*` SULLA CHIAVETTA (partizione
      exFAT) prima di spegnere: la live session non persiste.

## 6. Confronto con Windows (dopo, su Windows)

Confrontare con `lhm_validation_v3_20261022_010741`:
- J/token medio: concordante entro ~15-20% → valida il metodo cross-backend;
- `window_sources`: con RAPL ci si attende `exact-counter` (campi contatore
  cumulato nei campioni a 0,25 s), a differenza del fallback LHM — se cosi'
  e', e' evidenza che il limite era l'update LHM, non il profiler;
- P_base/P_load: i wattaggi Linux differiscono per driver/power plan →
  confronto ASSOLUTO dichiarato come limite, il claim e' sul rapporto
  energia/token.

## Limiti da dichiarare in tesi

1. Ambienti termici diversi (driver Windows vs kernel Linux, fan curve,
   power plan) → si confrontano i due metodi, non gli assoluti di idle.
2. Il dominio package RAPL include iGPU/controllori (same-domain note
   di `local_energy.py`, value unchanged).
3. Run singola sessione USB-live: niente persistenza; archiviare subito.
