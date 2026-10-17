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
        _emit(lines, log_callback, _INFO, "LHM applicabile solo su Windows: su Linux il motore usera' RAPL/CW_ENERGY_FILE")
        summary["method_expected"] = "rapl-or-file" if (Path("/sys/class/powercap").exists() or os.environ.get("CW_ENERGY_FILE")) else "unavailable"
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
    comp = None
    try:
        comp = Computer()
        comp.IsCpuEnabled = True
        comp.IsGpuEnabled = True
        comp.Open()
        summary["computer_opened"] = True
        _emit(lines, log_callback, _OK, "Computer() aperto: interrogazione hw in corso...")
    except BaseException as exc:
        _emit(lines, log_callback, _ERR, f"Computer().Open() FALLITA: {type(exc).__name__}: {exc}")
        summary["errors"].append(f"open:{type(exc).__name__}")
        summary["method_expected"] = "lhm-open-failed"
        return summary

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
            for sensor in hw.Sensors:
                try:
                    stype = _JS._lhm_sensor_type_name(sensor)
                    sname = str(sensor.Name).lower()
                except Exception:
                    continue
                if "Energy" in stype or "energysensor" in stype.lower():
                    # AMD Ryzen espone il contatore come "Package"/"Package
                    # Power"/"CPU PPT"; Intel come "CPU Package". Accettare
                    # qualunque token riconosciuto evita il falso negativo.
                    if any(tok in sname for tok in
                           ("package", "ppt", "core", "cpu", "evidp")):
                        n_energy += 1
                        energy_names.append(str(sensor.Name))
                    else:
                        energy_names.append(f"{sensor.Name} [non riconosciuto]")
                elif stype.endswith("Power") or (stype == "Power" and "power" in sname):
                    n_power_cpu += 1
                    power_names.append(str(sensor.Name))
                else:
                    key = stype.split(".")[-1] or "?"
                    n_other_types[key] = n_other_types.get(key, 0) + 1
        summary["energy_sensors_found"] = n_energy
        if energy_names:
            _emit(lines, log_callback, _OK,
                  f"Sensori Energy riconosciuti: {', '.join(energy_names)}")
        # Dump dei sensori Power W visti (Intel/AMD li espongono spesso): utile
        # per capire se il sensore c'e' ma ha un nome non in whitelist.
        if power_names:
            _emit(lines, log_callback, _INFO,
                  f"Sensori Power(W) su CPU: {', '.join(power_names[:12])}")
        if n_other_types:
            _emit(lines, log_callback, _INFO,
                  "Altri tipi sensore CPU: "
                  + ", ".join(f"{k} x{v}" for k, v in sorted(n_other_types.items())))
        if n_power_cpu and not energy_names:
            _emit(lines, log_callback, _WARN,
                  f"Sensori Power presenti ({', '.join(power_names[:8])}) "
                  "MA nessun contatore Energy cumulato")
        if n_energy > 0:
            _emit(lines, log_callback, _OK, f"Trovati {n_energy} sensori Energy-CPU: il backend LHM sara' attivo (metodo: librehardwaremonitor)")
            summary["method_expected"] = "librehardwaremonitor"
        elif admin is False:
            _emit(lines, log_callback, _WARN, f"CPU rilevata ({n_cpu_hw} hw, {n_power_cpu} sensori power) MA ZERO sensori Energy: comportamento TIPICO senza elevazione UAC. Riavvia come Amministratore e riesegui la calibrazione")
            summary["method_expected"] = "lhm-no-energy-unprivileged"
            summary["errors"].append("energy_sensors_unavailable_unprivileged")
        else:
            _emit(lines, log_callback, _WARN, f"Elevato, ma ZERO sensori Energy-CPU esposti dal driver: alcuni chipset (es. AMD recenti o laptop OEM) richiedono LHM >= 0.9.x aggiornata o non espongono Package Energy. In alternativa imposta CW_ENERGY_FILE puntato a un contatore Joule esterno")
            summary["method_expected"] = "lhm-no-energy-sensors"
            summary["errors"].append("energy_sensors_absent")
    except BaseException as exc:
        _emit(lines, log_callback, _ERR, f"Scansione sensori fallita: {type(exc).__name__}: {exc}")
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
