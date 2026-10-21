# -*- coding: utf-8 -*-
"""
diagnostics.py — Diagnostica hardware/energia all'avvio.

Scopo: quando la calibrazione idle empirica fallisce ("nessun contatore di
energia package disponibile"), l'utente deve poter capire SUBITO perche',
senza log silenziosi. Questo modulo verifica, con eccezioni esatte stampate
in console (e opzionalmente in un log callback):

1. interprete / piattaforma / privilegi amministratore;
2. presenza e dimensione delle DLL nella cartella LibreHardwareMonitorLib/;
3. importabilita' del pacchetto ``clr`` (pythonnet) con traceback completo
   (ModuleNotFoundError vs ImportError vs problemi di CLR);
4. caricamento reale dell'assembly ``LibreHardwareMonitorLib.dll`` via
   clr.AddReference + risoluzione dei tipi ``Computer`` (l'errore tipico di
   pythonnet 3.x "Assembly with same name is already loaded" viene qui
   neutralizzato con il caricamento via bytes, gia' usato dal motore);
5. istanza ``Computer`` + ``Open()`` + scansione sensori Energy-CPU
   (un processo non elevato legge tipicamente zero sensori energy: anche
   questo stato viene riportato esplicitamente).

Il controllo e' PASSIVO: non altera lo stato del motore energetico.
Uso da console:  py diagnostics.py
"""
from __future__ import annotations

import os
import platform
import sys
import traceback
from pathlib import Path
from typing import Callable, List, Optional

BASE_DIR = Path(__file__).resolve().parent
LHM_DIR = BASE_DIR / "LibreHardwareMonitorLib" / "LibreHardwareMonitor"
LHM_DLL_PATH = LHM_DIR / "LibreHardwareMonitorLib.dll"
REQUIRED_DLLS = ("LibreHardwareMonitorLib.dll", "HidSharp.dll", "Microsoft.Win32.TaskScheduler.dll")

_OK = "[ OK ]"
_WARN = "[WARN]"
_ERR = "[FAIL]"
_INFO = "[INFO]"


def _emit(lines: List[str], cb: Optional[Callable[[str], None]], tag: str, msg: str) -> None:
    entry = f"{tag} {msg}"
    lines.append(entry)
    print(entry, flush=True)
    if cb is not None:
        try:
            cb(entry)
        except Exception:  # il logger GUI non deve mai rompere la diagnostica
            pass


def _is_windows() -> bool:
    return platform.system().startswith("Win")


def _is_admin() -> Optional[bool]:
    """None se non determinabile (piattaforme non supportate)."""
    try:
        from elevation import is_admin as _ia

        return bool(_ia())
    except Exception:
        return None


def run_diagnostics(log_callback: Optional[Callable[[str], None]] = None) -> dict:
    """Esegue tutti i controlli. Ritorna un riepilogo e stampa ogni passo.

    Chiavi di ritorno:
      platform, admin, dlls_ok, clr_importable, assembly_loaded,
      types_resolved, computer_opened, energy_sensors_found,
      method_expected, errors (lista stringhe).
    """
    lines: List[str] = []
    summary = {
        "platform": platform.system(),
        "admin": None,
        "dlls_ok": False,
        "clr_importable": False,
        "assembly_loaded": False,
        "types_resolved": False,
        "computer_opened": False,
        "energy_sensors_found": 0,
        "method_expected": "unknown",
        "errors": [],
    }

    _emit(lines, log_callback, _INFO, f"Python {sys.version.split()[0]} ({sys.executable})")
    _emit(lines, log_callback, _INFO, f"Piattaforma: {platform.system()} {platform.release()} ({platform.machine()})")

    # ---------------------------------------------------------------- 1. admin
    admin = _is_admin()
    summary["admin"] = admin
    if admin is True:
        _emit(lines, log_callback, _OK, "Processo ELEVATO (amministratore): i sensori LHM dovrebbero essere leggibili")
    elif admin is False:
        _emit(lines, log_callback, _WARN, "Processo NON elevato: LHM si agganciera' ma potra' leggere ZERO sensori energy. Usa 'avvia_casualwatt.bat' o il pulsante 'Riavvia come Amministratore'")
    else:
        _emit(lines, log_callback, _INFO, "Privilegi amministratore non determinabili su questa piattaforma")

    # ------------------------------------------------------- 2. file DLL presenti
    if not _is_windows():
        # Su Linux: verifica disponibilità RAPL
        if platform.system() == "Linux":
            rapl_path = Path("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj")
            if rapl_path.exists() and os.access(rapl_path, os.R_OK):
                _emit(lines, log_callback, _OK,
                      f"RAPL disponibile: {rapl_path} leggibile. "
                      "Backend Linux attivo per misurazione energia CPU.")
                summary["method_expected"] = "rapl"
            else:
                _emit(lines, log_callback, _WARN,
                      f"RAPL non accessibile: {rapl_path} non esiste o permessi "
                      "insufficienti. Richiede root o gruppo 'power'. "
                      "Misurazione locale CPU disabilitata.")
                summary["method_expected"] = (
                    "energy-file(dev/test)" if os.environ.get("CW_ENERGY_FILE")
                    else "unavailable-rapl-not-accessible"
                )
        else:
            # macOS o altre piattaforme: non supportato (future work)
            _emit(lines, log_callback, _INFO,
                  f"Piattaforma {platform.system()}: misurazione locale CPU non "
                  "supportata (future work). GUI/Ollama/cloud/CSV restano "
                  "utilizzabili. Eventuale simulatore di test solo via "
                  "CW_ENERGY_FILE.")
            summary["method_expected"] = (
                "energy-file(dev/test)" if os.environ.get("CW_ENERGY_FILE")
                else "unavailable-non-windows"
            )
        return summary

    missing = [d for d in REQUIRED_DLLS if not (LHM_DIR / d).exists()]
    if missing:
        for d in missing:
            _emit(lines, log_callback, _ERR, f"DLL mancante: {LHM_DIR / d}")
        summary["errors"].append("dll_mancante")
    else:
        sizes = ", ".join(f"{d} {(LHM_DIR / d).stat().st_size // 1024} KB" for d in REQUIRED_DLLS)
        _emit(lines, log_callback, _OK, f"DLL presenti in {LHM_DIR}: {sizes}")
        summary["dlls_ok"] = True

    # --------------------------------------------------------- 3. import clr
    try:
        import clr  # noqa: F401
        summary["clr_importable"] = True
        ver = ""
        try:
            from Python.Runtime import Runtime as _RT  # type: ignore

            ver = getattr(_RT, "RuntimeVersion", "") or ""
        except Exception:
            try:
                import pythonnet  # type: ignore

                ver = getattr(pythonnet, "__version__", "")
            except Exception:
                pass
        _emit(lines, log_callback, _OK, f"Modulo 'clr' importato (pythonnet {ver or 'versione n/d'})")
    except BaseException as exc:  # ImportError, ModuleNotFoundError, errori CLR
        tb = traceback.format_exc(limit=6)
        _emit(lines, log_callback, _ERR, f"Import di 'clr' FALLITO: {type(exc).__name__}: {exc}")
        for ln in tb.rstrip().splitlines():
            _emit(lines, log_callback, _ERR, f"    {ln}")
        hint = ""
        if isinstance(exc, ModuleNotFoundError) or "No module named" in str(exc):
            hint = " => pythonnet NON installato nell'interprete corrente. Installa con lo STESSO python che lancia CasualWatt: `py -m pip install pythonnet` (verifica `py -c \"import clr\"`)"
        elif "clr" in str(exc).lower() and ("load" in str(exc).lower() or "host" in str(exc).lower()):
            hint = " => problema dell'host .NET CLR: verifica che il .NET Desktop Runtime sia installato"
        if hint:
            _emit(lines, log_callback, _ERR, hint)
        summary["errors"].append(f"clr_import:{type(exc).__name__}")
        _emit(lines, log_callback, _INFO, "Metodo energetico atteso: RAPL(file)/CW_ENERGY_FILE o fallback dichiarato (NIENTE LHM)")
        summary["method_expected"] = "no-lhm"
        return summary

    # ------------------------------------------- 4. AddReference assembly + types
    try:
        import clr

        if not LHM_DLL_PATH.exists():
            raise FileNotFoundError(f"LibreHardwareMonitorLib.dll non trovata in {LHM_DIR}")

        # Risoluzione dipendenze gestite (HidSharp, TaskScheduler): il loader
        # .NET le cerca nella stessa directory della libreria principale.
        try:
            os.add_dll_directory(str(LHM_DIR))
        except Exception:
            pass

        # pythonnet 3.x: AddReference(path) puo' fallire con "Assembly with
        # same name is already loaded" al secondo tentativo; il caricamento
        # via bytes + Assembly.Load e' l'approccio idempotente consigliato.
        loaded = None
        try:
            from System.Reflection import Assembly  # type: ignore

            with open(LHM_DLL_PATH, "rb") as fh:
                raw = fh.read()
            loaded = Assembly.Load(raw)
        except Exception:
            clr.AddReference(str(LHM_DLL_PATH))

        summary["assembly_loaded"] = True
        _emit(lines, log_callback, _OK, f"Assembly LibreHardwareMonitorLib caricata ({LHM_DLL_PATH.name}, {LHM_DLL_PATH.stat().st_size // 1024} KB)")
    except BaseException as exc:
        tb = traceback.format_exc(limit=6)
        _emit(lines, log_callback, _ERR, f"Caricamento assembly LHM FALLITO: {type(exc).__name__}: {exc}")
        for ln in tb.rstrip().splitlines():
            _emit(lines, log_callback, _ERR, f"    {ln}")
        summary["errors"].append(f"assembly:{type(exc).__name__}")
        summary["method_expected"] = "no-lhm"
        return summary

    try:
        from LibreHardwareMonitor.Hardware import Computer  # type: ignore

        summary["types_resolved"] = True
        _emit(lines, log_callback, _OK, "Namespace 'LibreHardwareMonitor.Hardware.Computer' risolto")
    except BaseException as exc:
        tb = traceback.format_exc(limit=4)
        _emit(lines, log_callback, _ERR, f"Risoluzione tipi LHM FALLITA: {type(exc).__name__}: {exc}")
        for ln in tb.rstrip().splitlines():
            _emit(lines, log_callback, _ERR, f"    {ln}")
        summary["errors"].append(f"types:{type(exc).__name__}")
        summary["method_expected"] = "no-lhm"
        return summary

    # --------------------------------------------------- 5. probe Computer+Open
    # NOTA CRITICA (crash pythonnet su Python 3.14 x64): se Open() solleva
    # un'eccezione .NET, pythonnet la converte in oggetto Python chiamando
    # Exceptions.SetError(...). Su build incompatibili (es. wheel pythonnet
    # pre-rilasciati per una minor di CPython diversa) la riflessione del
    # tipo dell'eccezione fallisce INTERNAMENTE con NullReferenceException
    # che il runtime CLR propaga come crash NON gestito del processo: il
    # try/except Python non puo' intercettarlo. Percio' qui Open() viene
    # chiamata SENZA wrapper: se l'assembly si rompe, lo stack .NET grezzo
    # finisce direttamente in console (diagnostica esatta richiesta); se
    # passa, la scansione sensori prosegue protetta.
    comp = Computer()
    comp.IsCpuEnabled = True
    comp.IsGpuEnabled = True
    # Diagnostica pre-Open: versione assembly + runtime .NET (utilissima per
    # verificare compatibilita' pythonnet/LHM prima di qualsiasi chiamata).
    try:
        from System.Reflection import Assembly  # type: ignore

        _asm_ver = str(Assembly.GetExecutingAssembly().ImageRuntimeVersion)
        _emit(lines, log_callback, _INFO, f"Runtime assembly LHM: {_asm_ver}")
    except Exception as exc:
        _emit(lines, log_callback, _WARN, f"Versione assembly non leggibile ({type(exc).__name__})")
    _emit(lines, log_callback, _INFO, "Chiamata Computer().Open() (senza wrapper: "
          "un crash .NET qui e' un problema pythonnet/CLR, non della scansione)...")
    comp.Open()
    summary["computer_opened"] = True
    _emit(lines, log_callback, _OK, "Computer() aperto: interrogazione hw in corso...")

    try:
        # Helper condiviso con il motore (energy_session): robusto fra le
        # versioni dell'assembly LHM e di pythonnet. In alcune build l'ISensor
        # .NET non espone 'Type' (da cui AttributeError); la proprieta' reale
        # e' 'SensorType'. Usare lo stesso helper evita divergenze fra
        # diagnostica e comportamento del profiler.
        from energy.energy_session import _CPUJouleSource as _JS

        n_cpu_hw = 0
        n_energy = 0
        n_power_cpu = 0
        n_other_types: dict = {}
        energy_names: List[str] = []
        power_names: List[str] = []
        all_sensors_dumped = 0
        for hw in comp.Hardware:
            try:
                hw.Update()          # senza Update() il Value resta None
            except Exception:
                continue
            # identificazione CPU robusta: HardwareType prima, nome come fallback
            is_cpu = False
            try:
                is_cpu = str(getattr(hw, "HardwareType", "")) == "Cpu"
            except Exception:
                pass
            if not is_cpu:
                try:
                    name = str(hw.Name).lower()
                    is_cpu = "cpu" in name or "central" in name
                except Exception:
                    continue
            if not is_cpu:
                continue
            n_cpu_hw += 1
            _emit(lines, log_callback, _INFO, f"Hardware CPU: {hw.Name}")
            for sensor in hw.Sensors:
                try:
                    stype = _JS._lhm_sensor_type_name(sensor)
                    sname = str(sensor.Name)
                    sval = sensor.Value
                except Exception:
                    continue
                all_sensors_dumped += 1
                sl = sname.lower()
                stl = stype.strip().lower()
                # --- dump completo di ogni sensore (richiesta utente #2) ---
                if all_sensors_dumped <= 40:
                    _emit(lines, log_callback, _INFO,
                          f"  sensore | {stype:<8} | {sname:<28} | valore={sval}")
                if "energy" in stl:
                    # AMD Ryzen espone il contatore come "Package"/"Package
                    # Power"/"CPU PPT"; Intel come "CPU Package". Accettare
                    # qualunque token riconosciuto evita il falso negativo.
                    if any(tok in sl for tok in
                           ("package", "ppt", "core", "cpu", "evidp")):
                        n_energy += 1
                        energy_names.append(sname)
                    else:
                        energy_names.append(f"{sname} [non riconosciuto]")
                elif stl == "power":
                    n_power_cpu += 1
                    power_names.append(sname)
                else:
                    key = stype.split(".")[-1] or "?"
                    n_other_types[key] = n_other_types.get(key, 0) + 1
        summary["energy_sensors_found"] = n_energy
        # --- requisito #3/#4: evidenziazione sensori Power e nome CPU power ---
        if power_names:
            _emit(lines, log_callback, _OK,
                  f"[POWER] Sensori Power(W) su CPU: {', '.join(power_names[:12])}")
            cpu_power_sel = next(
                (n for n in power_names if "package" in n.lower()),
                next((n for n in power_names if "ppt" in n.lower()),
                     power_names[0]))
            _emit(lines, log_callback, _INFO,
                  f"Sensore di potenza CPU selezionato (fallback): '{cpu_power_sel}'")
        if energy_names:
            _emit(lines, log_callback, _OK,
                  f"[ENERGY] Contatori Energy riconosciuti: {', '.join(energy_names)}")
            sel = next((n for n in energy_names if "package" in n.lower()),
                       energy_names[0])
            _emit(lines, log_callback, _INFO,
                  f"Sensore di energia CPU selezionato: '{sel}'")
        if n_other_types:
            _emit(lines, log_callback, _INFO,
                  "Altri tipi sensore CPU: "
                  + ", ".join(f"{k} x{v}" for k, v in sorted(n_other_types.items())))
        _emit(lines, log_callback, _INFO,
              f"Scansione sensori completata: {all_sensors_dumped} sensori totali "
              f"sulla CPU (Energy={n_energy}, Power={n_power_cpu})")
        if n_energy > 0:
            _emit(lines, log_callback, _OK,
                  f"Trovati {n_energy} sensori Energy-CPU: il backend LHM sara' attivo "
                  "(metodo: librehardwaremonitor-energy, calibrazione empirica Joule)")
            summary["method_expected"] = "librehardwaremonitor-energy"
        elif n_power_cpu > 0:
            # Intel (es. i9-13900HK): nessun contatore Energy -> il metodo
            # UFFICIALE e' power-integration sul sensore 'CPU Package' [W]
            # campionato ogni 0.05 s con integrazione trapezoidale.
            preferred = next((n for n in power_names
                              if n.strip().lower() == "cpu package"), None)
            fb = next((n for n in power_names
                       if n.strip().lower() in ("package", "package power", "cpu ppt")), None)
            sel = preferred or fb
            _emit(lines, log_callback, _WARN,
                  f"Nessun contatore Energy ma {n_power_cpu} sensori POWER presenti: "
                  "METODO ATTIVO: 'power-integration' — integrazione trapezoidale "
                  "del sensore di potenza CPU a 0.05 s (dichiarata nelle note CSV). "
                  "Sensore preferito: 'CPU Package'; fallback: 'Package', "
                  "'Package Power', 'CPU PPT'. Esclusi: 'CPU Cores', 'CPU Memory', "
                  "'CPU Platform'.")
            _emit(lines, log_callback, _OK,
                  f"Sensore selezionato per power-integration: "
                  f"'{sel}'" + (" (preferito)" if preferred else " (fallback)"))
            summary["method_expected"] = "power-integration"
            summary["power_sensor_selected"] = sel
        elif admin is False:
            _emit(lines, log_callback, _WARN,
                  f"CPU rilevata ({n_cpu_hw} hw) MA ZERO sensori Energy/Power: "
                  "comportamento TIPICO senza elevazione UAC. Riavvia come "
                  "Amministratore e riesegui la calibrazione")
            summary["method_expected"] = "lhm-no-energy-unprivileged"
            summary["errors"].append("energy_sensors_unavailable_unprivileged")
        else:
            _emit(lines, log_callback, _ERR,
                  "Elevato, ma il driver NON espone ALCUN sensore Energy o Power "
                  "per la CPU: questo hardware/chipset non fornisce la misura via "
                  "LHM. Aggiorna LibreHardwareMonitorLib alla >= 0.9.4 oppure "
                  "impostate CW_ENERGY_FILE su un contatore Joule esterno. "
                  "La calibrazione idle fallira' CON MESSAGGIO ESPLICITO "
                  "(nessun fallimento silenzioso)")
            summary["method_expected"] = "lhm-no-energy-sensors"
            summary["errors"].append("energy_sensors_absent")
    except BaseException as exc:
        tb = traceback.format_exc(limit=4)
        _emit(lines, log_callback, _ERR, f"Scansione sensori fallita: {type(exc).__name__}: {exc}")
        for ln in tb.rstrip().splitlines():
            _emit(lines, log_callback, _ERR, f"    {ln}")
        summary["errors"].append(f"scan:{type(exc).__name__}")
    finally:
        try:
            comp.Close()
        except Exception:
            pass

    # ------------------------------------------------------------- riepilogo
    _emit(lines, log_callback, _INFO, "Riepilogo diagnostica: " + "; ".join(
        f"{k}={v}" for k, v in summary.items() if k != "errors"
    ))
    return summary


if __name__ == "__main__":
    res = run_diagnostics()
    sys.exit(0 if not res["errors"] else 1)
