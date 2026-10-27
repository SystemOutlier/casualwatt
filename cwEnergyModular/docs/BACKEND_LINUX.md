# Backend Linux per CasualWatt - Contatori RAPL

## Panoramica

Il backend Linux di CasualWatt utilizza i contatori hardware **RAPL** (Running Average Power Limit) esposti dal kernel Linux in `/sys/class/powercap/intel-rapl/` per misurare l'energia del package CPU.

A differenza delle stime TDP-based (es. CodeCarbon, EnviroLLM), RAPL fornisce **misure reali** dell'energia consumata dal processore, con risoluzione di ~61 microjoule.

## Requisiti

### Hardware
- CPU Intel con supporto RAPL (Sandy Bridge, 2a gen o successiva)
- Per CPU AMD: supporto RAPL limitato (verificare con `ls /sys/class/powercap/`)

### Software
- Linux kernel >= 3.13 con `CONFIG_INTEL_RAPL` abilitato
- Permessi di lettura su `/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj`

### Permessi

I contatori RAPL richiedono privilegi di root o appartenenza al gruppo `power`:

**Opzione 1: Esecuzione come root**
```bash
sudo python main.py
```

**Opzione 2: Aggiungere l'utente al gruppo power**
```bash
# Crea il gruppo se non esiste
sudo groupadd -f power

# Aggiungi l'utente al gruppo
sudo usermod -a -G power $USER

# Applica le regole udev per /sys/class/powercap/
sudo tee /etc/udev/rules.d/99-rapl.rules > /dev/null <<'EOF'
SUBSYSTEM=="powercap", ACTION=="add", MODE="0640", GROUP="power"
EOF

# Ricarica le regole udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# Logout e login per applicare il cambio di gruppo
```

**Opzione 3: Permessi temporanei (solo per test)**
```bash
sudo chmod -R a+r /sys/class/powercap/intel-rapl/
```

## Verifica disponibilità

Controlla se RAPL è disponibile sul tuo sistema:

```bash
# Verifica esistenza del file
ls -l /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj

# Verifica permessi di lettura
cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj

# Esegui diagnostica CasualWatt
python diagnostics.py
```

Output atteso:
```
[ OK ] RAPL disponibile: /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj leggibile.
       Backend Linux attivo per misurazione energia CPU.
```

## Test del backend

Esegui i test sintetici:

```bash
python tests/test_rapl.py
```

Test eseguiti:
1. **Inizializzazione**: verifica che il backend RAPL sia disponibile
2. **Letture energetiche**: testa `read_cumulative_energy_j()` e `read_power_w()`
3. **Calibrazione idle**: misura l'energia idle per 2 secondi
4. **Diagnostica**: mostra lo stato del backend

## Utilizzo

Il backend RAPL è **automaticamente selezionato** su Linux quando:
- Il file `/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj` esiste ed è leggibile
- Non è impostata la variabile d'ambiente `CW_ENERGY_FILE` (che ha precedenza per dev/test)

Non è richiesta alcuna configurazione aggiuntiva. CasualWatt rileva automaticamente la piattaforma e attiva il backend appropriato:
- **Windows**: contatore cumulativo EMI (`emi_backend.py`); senza device il metodo resta `unavailable` (LHM è fuori dall'implementazione dal 27/10/2026, D18)
- **Linux**: RAPL
- **macOS**: non supportato (future work)

## Architettura

### File implementati

- `energy/rapl_backend.py`: classe `RAPLBackend` che legge i contatori RAPL
- `energy/energy_session.py`: integrazione del backend RAPL in `_CPUJouleSource`
- `diagnostics.py`: verifica disponibilità RAPL su Linux
- `tests/test_rapl.py`: test sintetici del backend

### Metodi implementati

`RAPLBackend` fornisce:
- `read_cumulative_energy_j()`: energia cumulata dal package CPU [J]
- `read_power_w()`: potenza istantanea [W] (calcolata come delta_energia/delta_tempo)
- `read_idle_window_j(duration_s)`: energia su finestra idle per calibrazione
- `diagnose()`: diagnostica del backend

### Gestione wrap-around

Il contatore RAPL `energy_uj` è cumulativo e wraps around quando raggiunge `max_energy_range_uj` (tipicamente ~2^32 µJ = ~4295 J). Il backend gestisce automaticamente il wrap-around incrementando un contatore interno `_wrap_count`.

### Confronto con altri backend

| Caratteristica | Windows (LHM) | Linux (RAPL) | EnviroLLM | CodeCarbon |
|---|---|---|---|---|
| **Tipo** | Misura firmware | Misura hardware | Stima statica | Stima TDP |
| **Sorgente** | CPU Package sensor | energy_uj | 50W + cpu%*2 | TDP * cpu% |
| **Accuracy** | Alta (sensore reale) | Alta (contatore HW) | Bassa (0.1-40% errore) | Bassa (~40% errore) |
| **Risoluzione** | 0.05s (power-integration) | ~61 µJ | 2s | 15s |
| **Attribuzione processo** | Sì (CPU time share) | Sì (CPU time share) | No | No |
| **Calibrazione idle** | Sì (3 finestre ≥30s) | Sì (3 finestre ≥30s) | No | No |

## Troubleshooting

### "RAPL non accessibile: permessi insufficienti"

**Causa**: L'utente non ha permessi di lettura su `/sys/class/powercap/`.

**Soluzione**: Vedi sezione "Permessi" sopra.

### "RAPL non disponibile: file non esiste"

**Causa**: Il kernel non ha caricato il modulo `intel_rapl` o la CPU non supporta RAPL.

**Soluzione**:
```bash
# Verifica supporto CPU
lscpu | grep "Model name"

# Carica manualmente il modulo
sudo modprobe intel_rapl_common
sudo modprobe intel_rapl_msr

# Verifica
ls /sys/class/powercap/
```

### "RAPL wrap-around rilevato"

**Causa**: Il contatore ha raggiunto `max_energy_range_uj` e si è resettato.

**Soluzione**: Questo è normale durante sessioni lunghe. Il backend gestisce automaticamente il wrap-around. Il messaggio è solo informativo.

### Benchmark funziona ma energia = 0

**Causa**: Il backend è attivo ma le letture ritornano 0.

**Soluzione**:
```bash
# Verifica letture dirette
cat /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj

# Esegui test
python tests/test_rapl.py

# Controlla log
python main.py 2>&1 | grep -i rapl
```

## Validazione scientifica

Per la tesi, il backend RAPL può essere validato confrontando le misure con:

1. **Windows (LHM)**: stesso hardware in dual boot, confrontare energia per query identiche
2. **Wattmetro esterno**: misurare potenza totale sistema con wattmetro fisico, confrontare con RAPL + altri componenti
3. **Intel Power Metric**: tool ufficiale Intel che legge gli stessi contatori MSR

Riferimenti bibliografici:
- Hähnel et al. "A Fresh Look on the Intel Running Average Power Limit" (SIGMETRICS PER 2012)
- Rotem et al. "Power Management Architecture of the Intel® Core™ Microarchitecture" (2012)
- Khan et al. "RAPL in Action: Experiences in Using RAPL for Power Measurements" (ACM TECS 2018)

## Limitazioni

- **Solo CPU**: RAPL misura solo il package CPU, non GPU discrete o altri componenti
- **Solo Intel**: Supporto AMD limitato (verificare disponibilità)
- **Permessi**: Richiede root o gruppo `power`
- **Wrap-around**: Sessioni molto lunghe (>1 ora ad alto carico) possono triggerare wrap-around (gestito automaticamente)

## Future work

- Supporto GPU via `nvidia-smi` o `rocm-smi` (già presente per Windows)
- Supporto macOS via `pyobjc` + `IOKit` + `Powermetrics`
- Supporto AMD RAPL (dominio `amd_rapl`)
- Lettura dominio DRAM (RAM energy) se disponibile
