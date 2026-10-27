# -*- coding: utf-8 -*-
"""
diagnostics.py — Diagnostica hardware/energia all'avvio.

Scopo: quando la calibrazione idle fallisce ("nessun contatore di energia
package disponibile"), l'utente deve poter capire SUBITO perche', senza log
silenziosi. Dal 27/10/2026 (D18) l'implementazione ha due soli canali locali:
il contatore EMI su Windows e i contatori RAPL su Linux. Questo modulo
verifica, con eccezioni esatte stampate in console (e opzionalmente in un log
callback):

1. interprete / piattaforma / privilegi;
2. Windows: enumerazione del device del canale energia, apertura dell'handle,
   lettura del contatore cumulativo e dei quattro domini (PKG/DRAM/PP0/PP1);
   se il device manca, sonda di sola esistenza su un meter PMI/WMI, che
   distingue "nessun meter esposto" da "non e' un canale implementato";
3. Linux: enumerazione delle zone powercap e selezione di quelle
   ``package-*`` (stessa logica del backend, ``energy/rapl_backend.py``);
4. la nota esplicita quando il contatore non c'e': il sostituto MSR (PawnIO)
   e' ancora una proposta [P], quindi la catena finisce in ``unavailable``.

LibreHardwareMonitor non e' piu' interrogata: e' un metodo provato e superato,
tenuto solo negli harness storici che hanno prodotto gli artefatti in
``experiment_results/``.

Il controllo e' PASSIVO: non altera lo stato del motore energetico.
Uso da console:  py diagnostics.py
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import traceback
from typing import Callable, List, Optional

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


def _energy_file_expected() -> Optional[str]:
    """``CW_ENERGY_FILE`` ha precedenza su ogni backend (contatore esterno)."""
    return os.environ.get("CW_ENERGY_FILE") or None


#: Namespace documentato della classe (Microsoft Learn, "Win32_PowerMeter
#: class", Requirements: Namespace Root\CIMV2\power; letto il 27-10-2026).
_PMI_NAMESPACE = r"root\CIMV2\power"
_PMI_FIELDS = ("DeviceID,Name,MeterType,SupportCapabilities,SamplingPeriod,"
               "BaseUnits,UnitModifier,MinimumAveragingInterval,"
               "MaximumAveragingInterval")


def _probe_pmi_power_meter(timeout_s: float = 5.0) -> dict:
    """Sonda di sola esistenza: Windows espone un power meter PMI via WMI?

    Serve a distinguere due ragioni diverse dello stesso ``unavailable``:
    un meter esiste ma non e' un canale implementato, oppure nessun meter e'
    esposto dal driver. Non legge una potenza: la pagina Microsoft della
    classe documenta budget e intervalli di media, non una proprieta' di
    lettura istantanea (verificato il 27-10-2026), quindi un valore ricavato
    da qui non sarebbe ancorato a nulla.

    Returns:
        ``{"probed": bool, "meters": list[dict], "error": str | None}``.
        ``probed`` falso significa che la sonda non ha concluso: non e' la
        stessa cosa di "nessun meter".
    """
    script = (
        "$ErrorActionPreference='Stop'; "
        f"Get-CimInstance -Namespace '{_PMI_NAMESPACE}' "
        f"-ClassName Win32_PowerMeter | Select-Object {_PMI_FIELDS} | "
        "ConvertTo-Json -Compress"
    )
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=timeout_s, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"probed": False, "meters": [], "error": type(exc).__name__}

    if proc.returncode != 0:
        lines = (proc.stderr or "").strip().splitlines()
        error = lines[0][:200] if lines else f"exit={proc.returncode}"
        return {"probed": False, "meters": [], "error": error}

    out = (proc.stdout or "").strip()
    if not out:
        return {"probed": True, "meters": [], "error": None}
    try:
        data = json.loads(out)
    except ValueError:
        return {"probed": False, "meters": [], "error": "json_non_valido"}
    meters = data if isinstance(data, list) else [data]
    return {
        "probed": True,
        "meters": [m for m in meters if isinstance(m, dict)],
        "error": None,
    }


def _diagnose_linux(lines: List[str], cb: Optional[Callable[[str], None]], summary: dict) -> None:
    """Linux: l'unico canale locale e' RAPL via powercap.

    La scoperta delle zone e' quella del backend vero
    (``energy/rapl_backend.py``): zone ``package-*``, canali specchiati contati
    una volta. Ripetere qui la logica darebbe due risposte diverse allo stesso
    filesystem.
    """
    try:
        from energy.rapl_backend import RAPLBackend
    except Exception as exc:  # noqa: BLE001 - import rotto = misura impossibile
        _emit(lines, cb, _ERR,
              f"Import del backend RAPL fallito: {type(exc).__name__}: {exc}")
        summary["errors"].append(f"rapl_import:{type(exc).__name__}")
        summary["method_expected"] = (
            "energy-file(dev/test)" if _energy_file_expected()
            else "unavailable"
        )
        return

    backend = RAPLBackend()
    diag = backend.diagnose()
    summary["rapl_path"] = diag["path"]
    summary["rapl_zones"] = [z["name"] for z in diag["zones"]]
    if backend.available:
        summary["rapl_readable"] = True
        _emit(lines, cb, _OK,
              "RAPL disponibile: zone package = "
              + ", ".join(f"{z['name']} ({z['path']})" for z in diag["zones"])
              + ". Backend Linux attivo per misurazione energia CPU.")
        summary["method_expected"] = "rapl"
        return

    summary["rapl_readable"] = False
    _emit(lines, cb, _ERR,
          "RAPL non accessibile: nessuna zona package leggibile sotto "
          f"{diag['path']}. Richiede root oppure permessi di lettura concessi "
          "esplicitamente sui nodi energy_uj. Misurazione locale CPU "
          "disabilitata.")
    for note in diag["notes"][-6:]:
        _emit(lines, cb, _INFO, f"    nota RAPL: {note}")
    summary["errors"].append("rapl_not_accessible")
    summary["method_expected"] = (
        "energy-file(dev/test)" if _energy_file_expected()
        else "unavailable"
    )


def _diagnose_windows(lines: List[str], cb: Optional[Callable[[str], None]],
                      summary: dict) -> None:
    """Windows: l'unico canale locale e' il device del canale energia (EMI)."""
    try:
        from energy.emi_backend import EMICounterBackend
    except Exception as exc:  # noqa: BLE001 - import rotto = misura impossibile
        tb = traceback.format_exc(limit=6)
        _emit(lines, cb, _ERR,
              f"Import del backend EMI fallito: {type(exc).__name__}: {exc}")
        for ln in tb.rstrip().splitlines():
            _emit(lines, cb, _ERR, f"    {ln}")
        summary["errors"].append(f"emi_import:{type(exc).__name__}")
        summary["method_expected"] = "unavailable"
        return

    emi = EMICounterBackend()
    try:
        summary["emi_available"] = bool(emi.available)
        summary["emi_device_path"] = emi.device_path
        if not emi.available:
            _emit(lines, cb, _ERR,
                  "[EMI] canale energia non disponibile "
                  f"({emi.last_error or 'nessun device corrispondente'}): "
                  "nessun altro canale di misura locale e' implementato su "
                  "Windows (LHM e' fuori dall'implementazione, D18; il "
                  "sostituto MSR via PawnIO e' ancora una proposta).")
            for note in getattr(emi, "notes", [])[-6:]:
                _emit(lines, cb, _INFO, f"    nota EMI: {note}")

            pmi = _probe_pmi_power_meter()
            summary["pmi_probe"] = pmi
            if pmi["probed"] and pmi["meters"]:
                summary["pmi_meters"] = len(pmi["meters"])
                _emit(lines, cb, _WARN,
                      "[PMI] WMI espone "
                      f"{len(pmi['meters'])} power meter (namespace "
                      f"{_PMI_NAMESPACE}). Non e' un canale implementato: la "
                      "classe documenta budget e intervalli di media, non una "
                      "lettura istantanea, quindi serve G1 prima di usarlo.")
            elif pmi["probed"]:
                summary["pmi_meters"] = 0
                _emit(lines, cb, _INFO,
                      "[PMI] nessun Win32_PowerMeter esposto: coerente con la "
                      "ragione 'driver_missing', cioe' nessun meter dal "
                      "driver, non un problema di permessi.")
            else:
                _emit(lines, cb, _INFO,
                      f"[PMI] sonda non conclusa ({pmi['error']}): nessuna "
                      "conclusione sull'esistenza di un meter.")

            summary["errors"].append("emi_device_absent")
            summary["method_expected"] = (
                "energy-file(dev/test)" if _energy_file_expected()
                else "unavailable"
            )
            return

        _emit(lines, cb, _OK,
              f"[EMI] device del canale energia aperto: {emi.device_path}")

        domains = emi.read_domains() if hasattr(emi, "read_domains") else None
        if domains is None:
            _emit(lines, cb, _ERR,
                  "[EMI] device aperto ma il record non e' leggibile: "
                  f"{emi.last_error or 'IOCTL fallita'}.")
            for note in getattr(emi, "notes", [])[-6:]:
                _emit(lines, cb, _INFO, f"    nota EMI: {note}")
            summary["emi_record_read"] = False
            summary["errors"].append("emi_record_unreadable")
            summary["method_expected"] = "unavailable"
            return

        summary["emi_record_read"] = True
        pkg_j, _pkg_ts, pkg_pwh = domains["pkg"]
        summary["emi_pkg_cum_j"] = round(float(pkg_j), 3)
        summary["emi_pkg_cum_pwh"] = pkg_pwh
        _emit(lines, cb, _OK,
              "[EMI] contatore package cumulativo leggibile "
              f"(PKG = {summary['emi_pkg_cum_j']} J, grezzo {pkg_pwh} pWh); "
              "nessun token elevato richiesto")
        _emit(lines, cb, _INFO,
              "[EMI] domini esposti: "
              + ", ".join(sorted(domains))
              + " (solo PKG produce l'energia package; PP1 e' informativo)")
        summary["emi_domains"] = sorted(domains)
        summary["method_expected"] = (
            "energy-file(dev/test)" if _energy_file_expected() else "emi-counter"
        )
    finally:
        try:
            emi.close()
        except Exception:
            pass


def run_diagnostics(log_callback: Optional[Callable[[str], None]] = None) -> dict:
    """Esegue tutti i controlli. Ritorna un riepilogo e stampa ogni passo.

    Chiavi di ritorno (le prime sei sempre presenti):
      platform, admin, energy_file, method_expected, errors, lines;
    su Windows: emi_available, emi_device_path, emi_record_read,
      emi_pkg_cum_j, emi_pkg_cum_pwh, emi_domains; se EMI manca, in piu'
      pmi_probe e pmi_meters (sola esistenza di un meter PMI/WMI);
    su Linux: rapl_path, rapl_zones, rapl_readable.
    """
    lines: List[str] = []
    summary = {
        "platform": platform.system(),
        "admin": None,
        "energy_file": _energy_file_expected(),
        "method_expected": "unknown",
        "errors": [],
        "lines": lines,
    }

    _emit(lines, log_callback, _INFO,
          f"Python {sys.version.split()[0]} ({sys.executable})")
    _emit(lines, log_callback, _INFO,
          f"Piattaforma: {platform.system()} {platform.release()} "
          f"({platform.machine()})")

    admin = _is_admin()
    summary["admin"] = admin
    if admin is True:
        _emit(lines, log_callback, _INFO,
              "Processo ELEVATO. Non serve al contatore EMI (letto senza token "
              "elevato); resta richiesto solo da operazioni di sistema.")
    elif admin is False:
        _emit(lines, log_callback, _INFO,
              "Processo NON elevato: il contatore EMI non richiede privilegi "
              "amministrativi.")
    else:
        _emit(lines, log_callback, _INFO,
              "Privilegi amministratore non determinabili su questa piattaforma")

    if summary["energy_file"]:
        _emit(lines, log_callback, _WARN,
              "CW_ENERGY_FILE impostato: la misura usera' il contatore in "
              f"'{summary['energy_file']}' (percorso DEV/TEST), non il device.")

    if _is_windows():
        _diagnose_windows(lines, log_callback, summary)
    elif platform.system() == "Linux":
        _diagnose_linux(lines, log_callback, summary)
    else:
        _emit(lines, log_callback, _INFO,
              f"Piattaforma {platform.system()}: misurazione locale CPU non "
              "supportata (future work). GUI/Ollama/cloud/CSV restano "
              "utilizzabili. Eventuale simulatore di test solo via "
              "CW_ENERGY_FILE.")
        summary["method_expected"] = (
            "energy-file(dev/test)" if summary["energy_file"]
            else "unavailable"
        )

    _emit(lines, log_callback, _INFO, "Riepilogo diagnostica: " + "; ".join(
        f"{k}={v}" for k, v in summary.items() if k not in ("errors", "lines")
    ))
    return summary


if __name__ == "__main__":
    res = run_diagnostics()
    sys.exit(0 if not res["errors"] else 1)
