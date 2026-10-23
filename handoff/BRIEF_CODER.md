# BRIEF CODER — `cpuepower2` (copia UNICA su cui lavorare)

Verificato su MINI_IT13 (i9-13900HK, Windows 11, build pythoncore-3.14-64) il 23/10/2026
eseguendo, non leggendo. Stato reale: `pytest -q` = **5 failed, 15 passed**;
`python -m cpuepower.cli tree --pid <pid> --window 2 --mock` = **AttributeError**;
`python -m cpuepower.cli probe` = esce 0 senza traceback.

## 0. Prima cosa: i path che hai citato non esistono

Non c'e' nessun `backends/` nel progetto. Mappa reale (dentro la zip):

| quello che hai chiesto | file reale |
|---|---|
| `attribution.py` | `cpuepower/attribution.py` |
| `cli.py` | `cpuepower/cli.py` |
| `process_tree.py` | `cpuepower/process_tree.py` |
| `backends/lhm_backend.py` | `cpuepower/msr_backends.py` (classe `LibreHardwareMonitorBackend`) |
| `backends/mock_backend.py` | `cpuepower/msr_backends.py` (classe `MockRaplBackend`) |
| `backends/rapl_backend.py` | `cpuepower/msr_backends.py` (`WinRing0Backend`, `CimProcessorPowerMetricsBackend`) + `cpuepower/rapl_units.py` (bitfield e mappa MSR) |
| file di test | `tests/test_rapl_real.py`, `tests/test_core.py` |

Servono anche, perche' i fix li toccano: `cpuepower/sampler.py` (`best_driver_for`),
`cpuepower/drivers/base.py` (`DriverCapability.provides_package_energy`),
`cpuepower/drivers/rapl_msr.py`, `cpuepower/types.py`.

Se un fix che dichiavi tocca un file che non esiste, il fix non esiste: prima
`ls`, poi modifica.

## 1. Cosa hai gia' fatto bene (non tocarlo)

- Mappa MSR corretta in `rapl_units.py:54-60` (0x611 / PP0 0x639 / PP1 0x641 /
  DRAM 0x619 / platform 0x64D; 0x618 rinominato `DRAM_POWER_LIMIT_MSR` con nota).
- Decode 0x606 in `rapl_units.py:88-112`: energy `(raw>>8)&0x1F`, power bit 0-3,
  time bit 16-23 = conforme al kernel (`rapl_check_hw_unit()`). `default_client()`
  con `0x000A0E03` deve dare `2^-14 J`, `2^-3 W`, `2^-10 s`.
- `safe_probe()` in `msr_backends.py:73`: la cascata non crasha piu'.
- WinRing0 marcato "NON FUNZIONANTE" con motivo esplicito: onesto, tienilo.
- `provides_package_energy = False` su LHM (`msr_backends.py:119`).

## 2. Task nell'ordine: "marcia verde" prima di tutto

**T1 — `_cpu_time_share()` mancante (blocco totale).**
`attribution.py:109` chiama `self._cpu_time_share(...)` che non esiste:
`AttributeError: 'TreeEnergyEstimator' object has no attribute '_cpu_time_share'`.
Implementala con il **differenziale**, non l'assoluto:
`E_inc = E_pkg_delta - P_base * dt` (P_base da finestra idle A-B-A, default
`DEFAULT_BASE_PACKAGE_W = 16.9` perche' e' il valore EMI misurato su MINI_IT13),
`confidence = "low"`, `CPU_TIME_SHARE_DISCLAIMER` obbligatorio in `notes` e
stampato dal CLI. Criterio: `cli tree --pid <pid> --window 2 --mock` termina 0.

**T2 — test di decode aggiornati (sono loro sbagliati, non il codice).**
`tests/test_rapl_real.py:25-34` costruisce `raw = (14<<0)|(13<<16)|(10<<24)`,
cioe' l'energy unit nei bit 0-3 (vecchio layout errato): per questo ottiene
`joule_unit == 1.0`. Va scritto `raw = (3<<0)|(14<<8)|(10<<16)`.
`test_pkg_unit_data_wrapped_bit` (riga 37-41) asserisce un comportamento che il
brief ha rimosso: sostituiscilo con `assert u.data_wrapped is False` anche con
bit 30 alzato. Criterio: quei due test verdi.

**T3 — regressione LHM (il backend che ci serve davvero).**
`cli probe` ora dice: `pythonnet/LHM non disponibile: No method matches given
arguments for Computer..ctor: ()`. Prima era solo "assembly non trovato", quindi
il refactoring di `set_shared_computer()` ha rotto la costruzione. Copia il
percorso che **funziona in produzione** (`energy_session.py:440-465`): non
`AddReferenceToFileAndPath`, ma (1) `os.add_dll_directory(cartella_dll)` per le
dipendenze `HidSharp.dll` / `Microsoft.Win32.TaskScheduler.dll`, (2)
`from System.Reflection import Assembly; Assembly.Load(bytes)` della DLL letta
in binario (idempotente; `clr.AddReference(path)` solo come fallback per
pythonnet 2.x), (3) `comp = Computer()` **senza argomenti** e SOLO DOPO
`comp.IsCpuEnabled = True; comp.IsGpuEnabled = True` — il tuo codice a `msr_backends.py:167`
costruisce `Computer(IsCpuEnabled=True, IsGpuEnabled=False, IsMemoryEnabled=True,
...)` e da' la `..ctor: ()` che vedi (LHM 0.9.x espone quelle proprieta', non un
costruttore con quegli argomenti). `Open()` in un solo punto.
Le DLL sono nell'archivio in `cpuepower2/dll/` (`LibreHardwareMonitorLib.dll`,
`HidSharp.dll`, `Microsoft.Win32.TaskScheduler.dll`): la cartella passata a
`add_dll_directory` deve contenerle tutte e tre, perche' il loader .NET risolve
le dipendenze da li'. Criterio: `[OK] librehardwaremonitor`
nel probe e `read_snapshot()` che restituisce watt di package plausibili
(idle atteso 15-20 W; 70 W = scala LHM nota come invalidata, non usare quel
numero come successo).

**T4 — il mock non deve potersi dichiarare hardware.**
`msr_backends.py:690` ha `provides_package_energy = True` sul `MockRaplBackend`
con commento "ma SONO finti": una cascata che si fidi del flag seleziona un
contatore sintetico. Metti `False`. Criterio: nessun percorso di selezione
backend puo' restituire il mock come sorgente di energia reale.

**T5 — `best_driver_for` mente nel CLI.**
`sampler.py:26-34` ritorna il primo driver *available* come fallback, e
`cli.py:33` lo stampa come `Best driver for package energy: wmi_msr` mentre la
riga del probe per wmi_msr dice `package=False`. Su MINI_IT13 nessun driver
espone energia di package: l'output corretto e'
`nessuno (fallback: estimate = STIMA)`. Criterio: test che asserisce che la
stringa "Best driver for package energy: wmi_msr" non compare quando tutti i
`provides_package_energy` sono False.

**T6 — bitfield sovrapposti.**
`rapl_units.py:104-105`: `step_bits = (raw>>14)&0xF` copre i bit 14-17 e
`time_bits = (raw>>16)&0xFF` copre 16-23 → i bit 16-17 contano in entrambi. Il
kernel usa 4 bit per il time unit (`TIME_UNIT_MASK 0xF0000`). Scegli: o
`time = (raw>>16)&0xF`, oppure tieni `step` ma cita la sezione esatta del Volume
4 del SDM Intel da cui lo prendi. Non tenere entrambe le cose non verificate.

**T7 — bug psutil `.name` (stessa classe di bug che hai gia' "corretto").**
`cli.py:121` `root_info.name`, `process_tree.py:42` `_safe(lambda: p.name, "?")`,
`process_tree.py:138`, `process_tree.py:244` `r.name`. Effetto osservato:
`=== Albero pid 6708 (<bound method Process.name of psutil.Process(...)>) ===`.
Nota che `_safe(lambda: p.name, "?")` non solleva eccezione, quindi il fallback
non scatta mai: e' un bug silenzioso. Criterio: l'intestazione stampa `python.exe`.

**T8 — test flaky trasformato in test che non asserisce nulla.**
`tests/test_rapl_real.py:111-117`: `select_backend()` e' chiamato alla riga 112,
PRIMA del guard `if sys.platform != "win32"`, quindi su Windows interroga il WMI
vivo e poi non asserisce niente. E' per questo che in `cpuepower` (copia vecchia,
intatta) i test sono passati da 19/20 a 20/20 **senza toccare codice**: era
instabilita', non un fix. Metti il guard prima della chiamata e copri la cascata
con un finto oggetto WMI che solleva `AttributeError` su `__properties__`.

## 3. Dati di terra da usare per validare (non inventarli)

- EMI nativo Windows: device `\\?\acpi#genuineintel_-_intel64_family_6_model_186_-_13th_gen_intel(r)_core(tm)_i9-13900hk#0#{45bd8344-7ed6-49cf-a440-c276c933b053}`,
  `IOCTL_EMI_GET_MEASUREMENT = 0x0022400C`, 4 record da 16 B (PKG@0, DRAM@16,
  PP0@32, PP1@48), energia in **pWh** (1 pWh = 3,6e-9 J), tempo in 100 ns.
  Contatore cumulativo: delta esatti, nessuna admin richiesta, finestre >= 1,5 s
  (sotto quella granularita' il delta dà potenze assurde: 151 W osservati).
- Valori attesi su MINI_IT13: idle package **16,9 W**; inferenza Ollama
  llama3.2:3b, 768 token, protocollo A-B-A → **0,996 J/token** (EMI) contro
  **0,484 J/token** (LHM power-integration): la divergenza e' nella **pendenza**,
  non solo nell'offset. PL1 35 W / PL2 55 W (OEM). Risoluzione reale del
  power-integration LHM: **0,32 s**.
- CodeCarbon su questa macchina = modello `cpu_load` (80 W x (0.1+0.9·load^3)),
  non una misura. Task Manager/PDH = stima EPI; su MINI_IT13 il counter PDH
  "Processor Power" **non esiste** (macchina localizzata IT, 29 counter
  nell'oggetto, nessun power/energy/watt).

## 4. Regole di consegna

Per ogni task: incolla l'output reale del comando di verifica (pytest, probe,
tree). "FATTO" senza output non conta. Non dichiarare "parita' con EMI" se non
c'e' un `Δ(0x611) × 2^-14` vs `Δ PKG EMI` entro il 2% sulla stessa finestra:
quello e' l'unico criterio ammesso, e se non passa il risultato e' "non
disponibile su questa CPU", che va bene comunque. Non toccare
`cwEnergyModular/energy/energy_session.py`: e' il backend di produzione e resta
finche' una alternativa non dimostra affidabilita' con evidenza misurata.
