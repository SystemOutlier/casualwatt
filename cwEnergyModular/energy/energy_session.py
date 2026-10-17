# -*- coding: utf-8 -*-
"""
energy/energy_session.py — Sessione CasualWatt: campionamento continuo.

Questa modulo espone il singleton ``SESSION`` usato da tutti gli altri moduli
energetici. Un thread daemon campiona a intervallo fisso:

* energia del package CPU (LibreHardwareMonitor via pythonnet, fallback
  RAPL Linux, fallback stima TDP psutil);
* tempo CPU busy di sistema (deriva dal ``cpu_times`` globale);
* istogrammi I/O del processo Ollama (read+write bytes e cpu_times), per
  poter interpolare con precisione il delta sull'albero dei processi anche
  quando la query HTTP non passa dal PID padre;
* contatori NIC (bytes sent/received) per il tracker di rete;
* potenza GPU NVIDIA (NVML) se disponibile.

Ogni campione e' un ``SystemSample`` ordinato nel tempo: le funzioni di
profilo in ``local_energy.py`` interpolano linearmente tra i campioni ai bordi
di una finestra di richiesta.
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import psutil

try:  # config e' nella cartella padre: import assoluto protetto
    from config import MONITOR_INTERVAL_S, OLLAMA_PROCESS_NAMES
except Exception:  # pragma: no cover - contesto di test standalone
    MONITOR_INTERVAL_S = 0.5
    OLLAMA_PROCESS_NAMES = ("ollama.exe", "ollama_llama_server.exe", "ollama")


# ---------------------------------------------------------------------------
# Sorgente energia package CPU
# ---------------------------------------------------------------------------
class _CPUJouleSource:
    """Astrae ``package_energy_j`` cumulata; sceglie il backend disponibile."""

    #: Campionamento del sensore CPU Package [W] per power-integration (spec §4)
    POWER_SAMPLE_INTERVAL_S = 0.05
    #: Nome sensore PREFERITO su Intel (i9-13900HK espone "CPU Package")
    _PREFERRED_POWER_NAMES = ("cpu package",)
    #: Fallback accettati SOLO se il preferito manca (AMD / varianti chipset)
    _FALLBACK_POWER_NAMES = ("package", "package power", "cpu ppt")

    def __init__(self) -> None:
        self.method = "unavailable"
        self._lhm = None
        self._tdp_w: Optional[float] = None
        self._power_base_j: float = 0.0   # base contatore potenza per read_power_j
        self._power_last_j: Optional[float] = None
        self._notes: List[str] = []
        # Diagnostica LHM: ultimo errore inghiottito durante la scansione
        # sensori (es. proprieta' rinomate fra versioni dell'assembly) e
        # modalita' di lettura usata ("package" | "core-sum").
        self._lhm_last_error: Optional[str] = None
        self._lhm_mode_notes: set = set()
        # ---- power-integration (metodo ufficiale su Windows senza Energy) --
        self._pi_thread: Optional[threading.Thread] = None
        self._pi_stop = threading.Event()
        self._pi_lock = threading.Lock()
        self._pi_samples: List[tuple] = []      # (t_monotono, watt)
        self._pi_energy_j: float = 0.0          # cumulata per integrazione trapezoidale
        self._pi_prev: Optional[tuple] = None   # ultimo punto (t, w) integrato
        self._pi_sensor_name: Optional[str] = None
        self._pi_sensors_seen: List[str] = []   # nomi Power visti (diagnostica)
        self._local_disabled_msg = (
            "Local CPU energy measurement is available only on Windows with "
            "LibreHardwareMonitor."
        )

        if self._try_lhm():
            # LHM agganciata: metodo definito dai sensori reali disponibili.
            if self._lhm_value() is not None:
                self.method = "librehardwaremonitor-energy"
                self._notes.append("LHM: contatore Energy-CPU presente")
            elif self._select_power_sensor() is not None:
                self.method = "power-integration"
                self._notes.append(
                    f"LHM: nessun contatore Energy; metodo 'power-integration' "
                    f"sul sensore '{self._pi_sensor_name}' @ {self.POWER_SAMPLE_INTERVAL_S}s"
                )
                self._start_power_integration()
            else:
                self.method = "librehardwaremonitor"  # nessuna lettura utile
                self._notes.append(
                    "LHM agganciata ma NESSUN sensore Energy/Power CPU esposto: "
                    "misurazione locale dichiarata indisponibile (non silenziosa)"
                )
        elif platform_system() == "Windows":
            # Windows senza LHM funzionante: niente RAPL/turbostat/perf_event
            # (esclusi per specifica), misurazione locale disabilitata con
            # messaggio chiaro. GUI/Ollama/cloud/CSV restano utilizzabili.
            self.method = "unavailable"
            self._notes.append(self._local_disabled_msg)
        elif self._try_power_counter():
            # ONLY Linux/dev: contatore Joule ESPOSTO DALL'UTENTE via
            # CW_ENERGY_FILE (simulatori di test). Non e' RAPL nativo ne'
            # perf_event_open: semplice lettura di un file di testo.
            pass
        else:
            # Piattaforma non-Windows: misurazione locale NON supportata.
            self.method = "unavailable"
            self._notes.append(self._local_disabled_msg)

    # -- backend LHM -------------------------------------------------------
    def _try_lhm(self) -> bool:
        try:
            import platform

            if not platform.system().startswith("Win"):
                self._notes.append("LHM non applicabile (piattaforma non Windows)")
                return False
            import clr  # pythonnet

            from config import LHM_DLL_PATH

            if not LHM_DLL_PATH.exists():
                self._notes.append(
                    f"LHM dll mancante in {LHM_DLL_PATH} "
                    "(reperibile da github.com/LibreHardwareMonitor)"
                )
                return False
            # NOTA: i sensori Energy-CPU di LHM richiedono token elevato.
            # Senza UAC la libreria si aggancia ma legge zero/None: il
            # messaggio e' reso esplicito qui (usato anche dalla GUI).
            try:
                from elevation import is_admin as _is_admin

                if not _is_admin():
                    self._notes.append(
                        "processo NON elevato: LHM potra' leggere i sensori "
                        "solo dopo 'Riavvia come Amministratore'"
                    )
            except Exception:
                pass
            # le DLL di dipendenza (HidSharp, TaskScheduler) devono essere
            # risolte dal loader .NET: si cerca prima nella cartella della libreria
            try:
                import os as _os

                _dir = str(LHM_DLL_PATH.parent)
                _os.add_dll_directory(_dir) if hasattr(_os, "add_dll_directory") else None
            except Exception:
                pass
            # pythonnet 3.x: AddReference(path) fallisce con "Assembly with
            # same name is already loaded" se la stessa DLL viene richiesta
            # piu' volte nel processo (es. dopo 'Calibra idle' + riavvio
            # sessione). Il caricamento via bytes + Assembly.Load e'
            # idempotente; AddReference resta il fallback per pythonnet 2.x.
            try:
                from System.Reflection import Assembly  # type: ignore

                with open(LHM_DLL_PATH, "rb") as _fh:
                    Assembly.Load(_fh.read())
            except Exception:
                clr.AddReference(str(LHM_DLL_PATH))
            from LibreHardwareMonitor.Hardware import Computer  # type: ignore

            comp = Computer()
            comp.IsCpuEnabled = True
            comp.IsGpuEnabled = True
            comp.Open()
            self._lhm = comp
            self._notes.append("LibreHardwareMonitorLib agganciata")
            return True
        except Exception as exc:  # noqa: BLE001 - degradazione voluta
            self._notes.append(f"LHM non disponibile ({type(exc).__name__})")
            return False

    # ------------------------------------------------------------------ LHM
    # Nomi sensore ENERGY accepted (case-insensitive): LibreHardwareMonitor
    # espone il contatore di energia del package con nomi diversi a seconda
    # di vendor/generazione:
    #   Intel  -> "CPU Package"          AMD Ryzen -> "Package"/"Core (Tctl/Tdie)"
    #   alcuni BIOS/chipset -> "Package Power", "CPU PPT", "PPT"/"EDP Limits"
    # Filtrare SOLO per SensorType=="Energy" e accettare qualunque nome che
    # contenga package/ppt/core/cpu/evidp evita il falso negativo
    # "energy_sensors_found=0" su AMD.
    _LHM_ENERGY_NAME_TOKENS = ("package", "ppt", "core", "cpu", "evidp")

    # ------------------------------------------------------------------ POWER
    # Sensori POWER [W] della CPU: usati come fallback quando il driver non
    # espunge alcun contatore Energy cumulato (alcune build LHM / chipset OEM).
    # La calibrazione empirica li accetta come sorgente istantanea: E_start/E_end
    # vengono integrati numericamente dalla potenza W letta ai due estremi.
    # Nota: la stima e' meno precisa dei Joule hardware ma resta misurata,
    # non modellistica (niente TDP).
    _LHM_POWER_NAME_TOKENS = (
        "package", "ppt", "cpu total", "total cpu", "core (tctl",
    )

    @staticmethod
    def _lhm_power_sensor_ok(sensor) -> bool:
        """SensorType==Power + nome plausibile di package/PPT (Intel/AMD)."""
        stype = _CPUJouleSource._lhm_sensor_type_name(sensor)
        if stype.strip().lower() != "power":
            return False
        try:
            sname = str(sensor.Name).lower()
        except Exception:
            return False
        return any(tok in sname for tok in _CPUJouleSource._LHM_POWER_NAME_TOKENS)

    def _lhm_power_w(self) -> Optional[float]:
        """Istantanea potenza CPU [W] dal primo sensore Power valido (o None)."""
        if self._lhm is None:
            return None
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()
                except Exception as exc:
                    self._lhm_last_error = f"Update(power): {exc}"
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                for sensor in hw.Sensors:
                    try:
                        if not self._lhm_power_sensor_ok(sensor):
                            continue
                        raw = sensor.Value
                        if raw is None:
                            continue
                        val = float(raw)
                        if val != val or val < 0:
                            continue
                        return val
                    except Exception as exc:
                        self._lhm_last_error = f"sensore power: {exc}"
                        continue
            return None
        except Exception as exc:
            self._lhm_last_error = str(exc)
            return None

    @staticmethod
    def _lhm_is_cpu_hw(hw) -> bool:
        """True se l'hardware LHM e' una CPU (tipo prima, nome come fallback)."""
        try:
            htype = getattr(hw, "HardwareType", None)
            if htype is not None and str(htype) == "Cpu":
                return True
        except Exception:
            pass
        try:
            n = str(hw.Name).lower()
            return "cpu" in n or "central" in n
        except Exception:
            return False

    # Prefissi di nome sensore che in LHM denotano il PACKAGE/totali della CPU
    # (usati per escludere i contatori Energy dei singoli core, la cui somma
    # sovrastimerebbe l'energia del package).
    _LHM_PACKAGE_TOKENS = ("package", "ppt", "evidp", "cpu total")

    @classmethod
    def _lhm_energy_sensor_ok(cls, sensor) -> bool:
        """Tipo==Energy + nome riconosciuto (Intel/AMD/varianti), solo package.

        Ritorna False se il nome non contiene token di package (es. sensore
        'Core #3'): in quel caso _lhm_value() usera' il fallback-sum, marcato
        pero' con una nota nel log diagnostico.
        """
        stype = cls._lhm_sensor_type_name(sensor)
        if "Energy" not in stype and "energysensor" not in stype.lower():
            return False
        try:
            sname = str(sensor.Name).lower()
        except Exception:
            return False
        if any(tok in sname for tok in cls._LHM_ENERGY_NAME_TOKENS):
            return True
        return False

    @classmethod
    def _lhm_is_package_energy_sensor(cls, sensor) -> bool:
        return (cls._lhm_energy_sensor_ok(sensor)
                and any(tok in str(getattr(sensor, "Name", "")).lower()
                        for tok in cls._LHM_PACKAGE_TOKENS))

    @staticmethod
    def _lhm_sensor_type_name(sensor) -> str:
        """Nome del SensorType LHM, robusto fra le versioni dell'assembly.

        L'interfaccia ISensor di LibreHardwareMonitorLib espone la proprieta'
        .SensorType (es. enum SensorType.Energy). Alcune build/pythonnet non
        la risolvono; il fallback su .Type era la causa dell'errore
        "'ISensor object has no attribute 'Type'". Qui si provano tutti gli
        attributi noti e, in ultimo, il tipo reale dell'oggetto.
        """
        for attr in ("SensorType", "Type"):
            try:
                v = getattr(sensor, attr, None)
                if v is not None:
                    return str(v)
            except Exception:
                continue
        # Ultimo tentativo: il type python.net dell'oggetto sensore
        # (es. <class 'LibreHardwareMonitor...+EnergySensor'>)
        try:
            return type(sensor).__name__
        except Exception:
            return ""

    def _lhm_value(self) -> Optional[float]:
        """Somma Energy-CPU [mJ] dai sensori LHM -> J cumulati monotoni.

        Preferisce il solo sensore PACKAGE (Intel 'CPU Package', AMD
        'Package'/'CPU PPT'); se assente, somma i sensori Energy dei core
        (fallback dichiarato via nota). Non solleva mai eccezioni verso
        l'alto: gli errori per-sensore sono inghiottiti e tracciati in
        _lhm_last_error per il log diagnostico.
        """
        if self._lhm is None:
            return None
        try:
            package_mj = 0.0
            core_mj = 0.0
            n_pkg = 0
            n_core = 0
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()          # senza Update() il Value resta None
                except Exception as exc:
                    self._lhm_last_error = f"Update(): {exc}"
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                for sensor in hw.Sensors:
                    try:
                        if not self._lhm_energy_sensor_ok(sensor):
                            continue
                        raw = sensor.Value
                        if raw is None:
                            continue     # sensore presente ma non ancora popolato
                        val = float(raw)
                        if val != val:   # NaN check
                            continue
                        if self._lhm_is_package_energy_sensor(sensor):
                            package_mj += val
                            n_pkg += 1
                        else:
                            core_mj += val
                            n_core += 1
                    except Exception as exc:
                        self._lhm_last_error = f"sensore: {exc}"
                        continue
            if n_pkg:
                if "package" not in self._lhm_mode_notes:
                    self._lhm_mode_notes.add("package")
                return package_mj / 1000.0
            if n_core:
                if "core-sum" not in self._lhm_mode_notes:
                    self._lhm_mode_notes.add("core-sum")
                    self._notes.append(
                        "LHM: nessun sensore Energy di package; uso somma "
                        "contatori Energy dei core (attributione approssimata)"
                    )
                return core_mj / 1000.0
            return None
        except Exception as exc:
            self._lhm_last_error = str(exc)
            return None

    def diagnose_cpu_sensors(self) -> List[dict]:
        """Ritorna TUTTI i sensori CPU esposti da LHM (per log diagnostico)."""
        out: List[dict] = []
        if self._lhm is None:
            return out
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()
                except Exception:
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                for sensor in hw.Sensors:
                    try:
                        out.append({
                            "hardware": str(hw.Name),
                            "sensor_name": str(sensor.Name),
                            # _lhm_sensor_type_name(): robusto fra versioni
                            # LHM/pythonnet (SensorType -> Type -> class name)
                            "sensor_type": self._lhm_sensor_type_name(sensor),
                            "value": (None if sensor.Value is None
                                      else float(sensor.Value)),
                        })
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    # ------------------------------------------------------------------ OS
    # platform.system() centralizzato (mockabile nei test).
    # NOTE: su Windows si usa SOLO LibreHardwareMonitor; niente
    # perf_event_open / turbostat / /sys/class/powercap (esclusi da specifica).

    # -- POWER-INTEGRATION (metodo ufficiale quando LHM non espone Energy) --
    def _select_power_sensor(self):
        """Sceglie IL sensore Power della CPU secondo priorita' di specifica.

        Preferito : nome esatto "CPU Package" (Intel, es. i9-13900HK).
        Fallback  : "Package", "Package Power", "CPU PPT" (AMD Ryzen), solo se
                    il preferito non esiste.
        Esclusi   : "CPU Cores", "CPU Memory", "CPU Platform" (parziali/altre
                    componenti) e qualunque sensore non di tipo Power.
        Ritorna l'oggetto sensore pythonnet oppure None. Memorizza in
        _pi_sensors_seen TUTTI i nomi Power visti (diagnostica completa).
        """
        if self._lhm is None:
            return None
        preferred = None
        fallback = None
        seen_power: List[str] = []
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()          # senza Update() il Value resta None
                except Exception as exc:
                    self._lhm_last_error = f"Update(select): {exc}"
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                subs = list(getattr(hw, "SubHardware", []) or [])
                for sub in [hw] + subs:
                    for sensor in sub.Sensors:
                        try:
                            if self._lhm_sensor_type_name(sensor).strip().lower() != "power":
                                continue
                            sname = str(sensor.Name).strip()
                            low = sname.lower()
                            seen_power.append(sname)
                            # esclusioni esplicite (spec §3)
                            if low.startswith("cpu cores") or low.startswith("cpu memory") \
                                    or low.startswith("cpu platform") or low.startswith("core #"):
                                continue
                            if low in self._PREFERRED_POWER_NAMES and preferred is None:
                                preferred = sensor
                            elif any(low == fb for fb in self._FALLBACK_POWER_NAMES) and fallback is None:
                                fallback = sensor
                        except Exception as exc:
                            self._lhm_last_error = f"select: {exc}"
                            continue
        except Exception as exc:
            self._lhm_last_error = str(exc)
        self._pi_sensors_seen = seen_power
        chosen = preferred if preferred is not None else fallback
        if chosen is not None:
            try:
                self._pi_sensor_name = str(chosen.Name)
            except Exception:
                self._pi_sensor_name = "?"
        return chosen

    def _read_power_w_direct(self) -> Optional[float]:
        """Legge il valore [W] del sensore selezionato (None se non popolato)."""
        sel = getattr(self, "_pi_selected", None)
        if sel is None:
            sel = self._select_power_sensor()
            self._pi_selected = sel
        if sel is None:
            return None
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()
                except Exception:
                    continue
                for sensor in list(hw.Sensors) + [
                    s for sub in (list(getattr(hw, "SubHardware", []) or [])) for s in sub.Sensors
                ]:
                    try:
                        if sensor is sel or str(sensor.Name) == self._pi_sensor_name:
                            raw = sensor.Value
                            if raw is None:
                                return None
                            val = float(raw)
                            if val != val or val < 0:
                                return None
                            return val
                    except Exception:
                        continue
        except Exception as exc:
            self._lhm_last_error = f"read_power_w: {exc}"
        return None

    def _pi_loop(self) -> None:
        """Thread di integrazione: campiona CPU Package ogni 0.05 s (spec §4).

        Energia con regola trapezoidale incrementale:
            E += ((P_i + P_i+1) / 2) * (t_i+1 - t_i)
        Nessuna stima TDP, nessun moltiplicatore arbitrario.
        """
        while not self._pi_stop.is_set():
            t = time.monotonic()
            w = self._read_power_w_direct()
            if w is not None:
                with self._pi_lock:
                    self._pi_samples.append((t, w))
                    if len(self._pi_samples) > 4000:
                        del self._pi_samples[:2000]
                    if self._pi_prev is not None:
                        pt, pw = self._pi_prev
                        dt = t - pt
                        if dt > 0:
                            self._pi_energy_j += ((pw + w) / 2.0) * dt
                    self._pi_prev = (t, w)
            self._pi_stop.wait(self.POWER_SAMPLE_INTERVAL_S)

    def _start_power_integration(self) -> None:
        if self._pi_thread is not None and self._pi_thread.is_alive():
            return
        self._pi_stop.clear()
        self._pi_thread = threading.Thread(
            target=self._pi_loop, name="cw-power-integration", daemon=True
        )
        self._pi_thread.start()

    def stop_power_integration(self) -> None:
        """Arresta il thread di integrazione (join entro 5 s, spec §7)."""
        th = self._pi_thread
        if th is None:
            return
        self._pi_stop.set()
        th.join(timeout=5.0)
        self._pi_thread = None

    def pi_stats(self) -> dict:
        with self._pi_lock:
            return {
                "samples": len(self._pi_samples),
                "energy_j": round(self._pi_energy_j, 6),
                "sensor": self._pi_sensor_name,
                "power_sensors_seen": list(self._pi_sensors_seen),
            }

    # -- contatore energia via file (SOLO dev/test non-Windows) -------------
    def _try_power_counter(self) -> bool:
        """Backend DEV/TEST su piattaforme non-Windows: contatore Joule da file.

        Configurabile con la variabile d'ambiente ``CW_ENERGY_FILE`` (o in
        .env): il file deve contenere un numero = energia cumulata [J]
        (simulatore nei test). NON e' RAPL nativo, perf_event_open o turbostat:
        su Windows questo backend non viene mai tentato (spec §2).
        """
        try:
            import os

            path = os.environ.get("CW_ENERGY_FILE", "").strip().strip('"')
            if not path or not os.path.isfile(path):
                return False
            v = self._read_energy_file(path)
            if v is None:
                return False
            self._power_path = path
            self.method = "energy-file"  # contatore reale simulato (dev/test)
            self._notes.append(f"[DEV/TEST non-Windows] contatore energia da file {path}")
            return True
        except Exception:
            return False

    @staticmethod
    def _read_energy_file(path: str) -> Optional[float]:
        try:
            with open(path, "r", encoding="ascii") as fh:
                raw = fh.read().strip()
            val = float(raw.split()[0]) if raw else None
            return val
        except Exception:
            return None

    def _file_value(self) -> Optional[float]:
        v = getattr(self, "_power_path", None)
        if not v:
            return None
        return self._read_energy_file(v)

    # -- backend stima TDP -------------------------------------------------
    @staticmethod
    def _guess_tdp() -> float:
        try:
            import platform

            name = platform.processor().lower()
            if any(k in name for k in ("14900", "13900", "i9")):
                return 65.0
            if "i7" in name or "ryzen 7" in name:
                return 45.0
            if "i5" in name or "ryzen 5" in name:
                return 35.0
        except Exception:
            pass
        return 45.0

    # -- diagnostica letture -------------------------------------------------
    @property
    def last_read_error(self) -> Optional[str]:
        """Messione d'errore dell'ultima lettura fallita (per GUI/log)."""
        return getattr(self, "_last_read_error", None)

    def _record_read_error(self, exc: BaseException, ctx: str) -> None:
        msg = f"{ctx}: {type(exc).__name__}: {exc}"
        self._last_read_error = msg
        # log esplicito su console: niente fallimenti silenziosi
        print(f"[CasualWatt][LHM] {msg}", file=sys.stderr, flush=True)

    # -- interfaccia comune --------------------------------------------------
    def read_package_j(self, busy_seconds_total: float) -> Optional[float]:
        """Energia package CPU CUMULATA da inizio sessione [J].

        Metodi reali supportati (nessuna stima TDP, nessun moltiplicatore
        arbitrario):
          * "power-integration"           -> integrazione trapezoidale del
            sensore CPU Package [W] a 0.05 s (metodo ufficiale su i9-13900HK);
          * "librehardwaremonitor-energy" -> contatore Energy LHM [J];
          * "energy-file"                 -> contatore dev/test non-Windows.
        ``busy_seconds_total`` e' ignorato (retro-compatibilita' di firma).
        """
        if self.method == "power-integration":
            with self._pi_lock:
                return self._pi_energy_j
        if self.method in ("librehardwaremonitor-energy", "librehardwaremonitor"):
            return self._lhm_value()
        if self.method == "energy-file":
            fv = self._file_value()
            if fv is None:
                return None
            base = self._power_base_j or 0.0
            return max(fv - base, 0.0) if fv >= base else fv
        # "unavailable": misurazione locale dichiaratamente disabilitata
        return None

    def read_power_j(self) -> Optional[float]:
        """Lettura DIRETTA della grandezza energetica cumulata [J].

        Stessa funzione usata dal benchmark (principio di specifica: la
        calibrazione empirica campiona con il medesimo percorso):
          * power-integration -> energia gia' integrata a 0.05 s;
          * energy-counter LHM / file dev-test -> contatore cumulato.
        Ritorna None se nessun backend reale e' disponibile: il chiamante
        deve dichiararlo (mai fallback TDP silenzioso).
        """
        try:
            if self.method == "power-integration":
                with self._pi_lock:
                    if self._pi_energy_j > 0:
                        return self._pi_energy_j
                # thread appena avviato: aspetta un paio di campioni (0.05 s)
                deadline = time.monotonic() + 0.3
                while time.monotonic() < deadline:
                    time.sleep(0.02)
                    with self._pi_lock:
                        if self._pi_energy_j > 0:
                            return self._pi_energy_j
                return None
            if self.method in ("librehardwaremonitor-energy", "librehardwaremonitor"):
                v = self._lhm_value()
                if v is None:
                    sensors = self.diagnose_cpu_sensors()
                    n_power = sum(1 for s in sensors if "Power" in s["sensor_type"])
                    n_energy = sum(1 for s in sensors if "Energy" in s["sensor_type"])
                    names = sorted({s["sensor_name"] for s in sensors})
                    detail = (
                        f"{len(sensors)} sensori CPU trovati "
                        f"(Energy={n_energy}, Power={n_power}); "
                        f"nomi sensori: {', '.join(names[:12]) or '-'}"
                    ) if sensors else \
                        "LHM non espone ALCUN sensore CPU (0 hw CPU interrogabili)"
                    self._last_read_error = (
                        "LHM agganciata ma nessun contatore Energy-CPU leggibile. "
                        + detail + ". Se i sensori Power ci sono ma Energy=0: "
                        "processo NON elevato (UAC) o driver chipset senza "
                        "Package Energy -> riavvia con 'avvia_casualwatt.bat' "
                        "(amministratore) e riesegui 'py diagnostics.py'; "
                        "in alternativa imposta CW_ENERGY_FILE su un contatore "
                        "Joule esterno"
                    )
                    self._notes.append(
                        "diagnostica lettura LHM: " + detail
                    ) if detail not in " ".join(self._notes) else None
                return v
            if self.method == "energy-file":
                fv = self._file_value()
                if fv is None:
                    return None
                base = self._power_base_j or 0.0
                return max(fv - base, 0.0) if fv >= base else fv
        except Exception as exc:
            self._record_read_error(exc, "lettura contatore energia fallita")
            return None
        return None  # unavailable: nessun backend reale (dichiarato, non silenzioso)

    def read_idle_window_j(self, duration_s: float) -> Optional[tuple]:
        """Delta-energy [J] su una finestra passiva di ``duration_s`` secondi.

        Ritorna ``(delta_j, dt_real, mode)`` oppure None se nessun backend
        reale e' disponibile. Modalita':
          * mode="power-integration": MEDIA delle potenze istantanee del
            sensore CPU Package campionate OGNI 0.05 s durante la finestra
            (integrazione trapezoidale completa, spec §4) — metodo ufficiale
            su Windows quando LHM non espone contatori Energy;
          * mode="energy-counter": delta del contatore Joule cumulato (LHM
            Energy o file dev/test).
        Nessuna modalita' usa stime TDP: entrambe sono misure reali.
        """
        duration_s = max(float(duration_s), 0.5)
        # 1) POWER-INTEGRATION: campionamento fitto durante la finestra a riposo
        if self.method == "power-integration":
            powers: List[float] = []
            t0 = time.monotonic()
            end = t0 + duration_s
            while time.monotonic() < end:
                w = self._read_power_w_direct()
                if w is not None:
                    powers.append(w)
                time.sleep(self.POWER_SAMPLE_INTERVAL_S)
            dt = max(time.monotonic() - t0, 1e-6)
            if powers:
                avg_w = sum(powers) / len(powers)
                return (avg_w * dt, dt, "power-integration")
            self._last_read_error = (
                f"sensore '{self._pi_sensor_name}' agganciato ma Value sempre "
                "None durante la finestra: Update()/driver non popolano il "
                "sensore (riavviare come amministratore)"
            )
            return None
        # 2) contatore Joule reale (LHM Energy / file dev-test)
        e_start = self.read_power_j()
        err_after_counter = getattr(self, "_last_read_error", None)
        t0 = time.monotonic()
        if e_start is not None:
            time.sleep(duration_s)
            e_end = self.read_power_j()
            dt = max(time.monotonic() - t0, 1e-6)
            if e_end is not None and e_end >= e_start:
                return (e_end - e_start, dt, "energy-counter")
        # 3) nessun backend: propagazione diagnostica al chiamante
        if err_after_counter:
            self._last_read_error = err_after_counter
        return None

    @property
    def notes(self) -> List[str]:
        return list(self._notes)


def platform_system() -> str:
    """Wrapper single-source per platform.system() (mockabile nei test)."""
    import platform

    return platform.system()


# ---------------------------------------------------------------------------
# Campione e sessione
# ---------------------------------------------------------------------------
@dataclass
class SystemSample:
    t: float                       # timestamp monotono
    wall: float                    # timestamp wall-clock epoch
    package_energy_j: Optional[float]   # cumulata da inizio sessione
    cpu_busy_seconds: float        # secondi CPU busy aggregati da inizio sessione
    cpu_percent: float             # % media sistema nell'ultimo intervallo
    ollama_pids: tuple = ()
    ollama_io_bytes: int = 0       # read+write cumulati albero Ollama
    ollama_cpu_seconds: float = 0.0  # utime+stime cumulati albero Ollama
    nic_bytes: int = 0             # sent+received cumulati
    gpu_power_w: Optional[float] = None
    gpu_util_pct: Optional[float] = None


@dataclass
class EnergySession:
    """Singleton di sessione: thread di campionamento + storico campioni."""

    interval_s: float = MONITOR_INTERVAL_S

    def __post_init__(self) -> None:
        self._lock = threading.RLock()
        self._samples: List[SystemSample] = []
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._source = _CPUJouleSource()
        self._proc = psutil.Process()
        self._t0_wall = time.time()
        self._cpu_t0 = self._system_busy_seconds()
        self._gpu = _GPUMonitor()
        self.idle_power_w: Optional[float] = None
        # provenienza della calibrazione: "calibrated" (utente/GUI),
        # "session" (ripristinata da sessione precedente), "auto_micro"
        # (micro-calibrazione automatica del profiler). Usata dal profiler
        # per abilitare lo scorporo delle code inattive solo con idle
        # affidabile.
        self.idle_provenance: Optional[str] = None
        self.calibrated_at: Optional[float] = None
        self.last_error: Optional[str] = None

    # ------------------------------------------------------------------ util
    @staticmethod
    def _system_busy_seconds() -> float:
        """Secondi CPU busy aggregati di sistema (non-idle)."""
        try:
            ct = psutil.cpu_times()
            idle = getattr(ct, "idle", 0.0)
            ncpu = max(psutil.cpu_count(logical=True) or 1, 1)
            total_all_cores = sum(
                v for v in ct if isinstance(v, (int, float))
            ) * 0  # placeholder, calcolato sotto
            # busy = (totale per core) - idle, su tutte le CPU logiche
            per_core_total = 0.0
            for c in psutil.cpu_times(percpu=True):
                per_core_total += sum(
                    v for v in c if isinstance(v, (int, float))
                )
            del total_all_cores, ncpu
            return max(per_core_total - idle * 1.0, 0.0) if idle is not None else per_core_total
        except Exception:
            return 0.0

    @staticmethod
    def _nic_bytes() -> int:
        try:
            counters = psutil.net_io_counters()
            return int(counters.bytes_sent + counters.bytes_recv)
        except Exception:
            return 0

    @staticmethod
    def find_ollama_procs() -> List[int]:
        """PID dell'albero Ollama (server + worker llama_server)."""
        pids: List[int] = []
        wanted = {n.lower() for n in OLLAMA_PROCESS_NAMES}
        try:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    nm = (p.info["name"] or "").lower()
                    if nm in wanted or nm.rstrip(".exe") in {w.rstrip(".exe") for w in wanted}:
                        pids.append(int(p.info["pid"]))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass
        return sorted(set(pids))

    @classmethod
    def _ollama_tree_stats(cls, pids: List[int]) -> Dict[str, float]:
        io_bytes = 0
        cpu_secs = 0.0
        seen = set()
        stack = list(pids)
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            try:
                pr = psutil.Process(pid)
                with pr.oneshot():
                    try:
                        c = pr.io_counters()
                        io_bytes += int(c.read_bytes + c.write_bytes)
                    except (AttributeError, psutil.AccessDenied):
                        pass
                    ct = pr.cpu_times()
                    cpu_secs += float(ct.user + ct.system)
                    stack += [c.pid for c in pr.children(recursive=False)]
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except Exception:
                continue
        return {"io_bytes": io_bytes, "cpu_seconds": cpu_secs, "n": len(seen)}

    # ------------------------------------------------------------- sampling
    def _loop(self) -> None:
        # power-integration campiona gia' a 0.05 s nel suo thread dedicato:
        # il sampler di sessione (busy/ollama/nic/gpu) puo' rallentare per
        # non contendere il sensore LHM.
        interval = self.interval_s
        if self._source.method == "power-integration":
            interval = max(interval, 0.25)
        while not self._stop.is_set():
            try:
                self.record_once()
            except Exception as exc:  # il thread non deve mai morire
                self.last_error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(interval)

    def record_once(self) -> Optional[SystemSample]:
        """Registra un campione nella sessione (thread sampler o calibrazione)."""
        with self._lock:
            if not self._running:
                return None
            return self._record_once()

    def _record_once(self) -> SystemSample:
        t = time.monotonic()
        busy = self._system_busy_seconds()
        pids = self.find_ollama_procs()
        stats = self._ollama_tree_stats(pids) if pids else {
            "io_bytes": 0,
            "cpu_seconds": 0.0,
            "n": 0,
        }
        pkg = self._source.read_package_j(busy - self._cpu_t0)
        gpu_w, gpu_u = self._gpu.read()
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
        except Exception:
            cpu_pct = 0.0
        sample = SystemSample(
            t=t,
            wall=time.time(),
            package_energy_j=pkg,
            cpu_busy_seconds=max(busy - self._cpu_t0, 0.0),
            cpu_percent=cpu_pct,
            ollama_pids=tuple(pids),
            ollama_io_bytes=int(stats["io_bytes"]),
            ollama_cpu_seconds=float(stats["cpu_seconds"]),
            nic_bytes=self._nic_bytes(),
            gpu_power_w=gpu_w,
            gpu_util_pct=gpu_u,
        )
        with self._lock:
            self._samples.append(sample)
            # tetto difensivo alla memoria (~2 h a 0.5 s)
            if len(self._samples) > 20_000:
                del self._samples[:2_000]
        return sample

    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            # spec §6/§7: il Computer() LHM e' aperto UNA sola volta nel
            # source; qui si riavvia SOLO il thread di power-integration se
            # era stato fermato da close(), senza mai richiudere l'assembly.
            if self._source.method == "power-integration":
                self._source._start_power_integration()
            self._stop.clear()
            # allinea la base del contatore di potenza al momento dell'avvio:
            # cosi' read_power_j()/package_energy_j restano coerenti tra
            # calibrazione empirica e benchmark anche dopo stop/riconnessione
            pb = self._source.read_power_j()
            if pb is not None and self._source.method != "power-integration":
                self._source._power_base_j = pb
            self._cpu_t0 = self._system_busy_seconds()
            self._samples.clear()
            self._thread = threading.Thread(
                target=self._loop, name="cw-energy-sampler", daemon=True
            )
            self._running = True
        self._thread.start()

    def stop(self) -> None:
        """Ferma il sampler di sessione. NON chiude LibreHardwareMonitor/NVML
        (spec §6): l'assembly resta aperto per calibrazioni/inferenze successive;
        lo shutdown definitivo avviene una sola volta in close()."""
        with self._lock:
            if not self._running:
                return
            self._stop.set()
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)   # spec §7: join entro 5 s
            self._thread = None

    def close(self) -> None:
        """Chiusura DEFINITIVA e unica delle risorse hardware (spec §6).

        - ferma e joina il thread di power-integration (<= 5 s);
        - chiude il Computer() LibreHardwareMonitor UNA sola volta;
        - nvmlShutdown() UNA sola volta.
        Idempotente: chiamata multipla non genera errori.
        """
        self.stop()
        src = self._source
        try:
            src.stop_power_integration()
        except Exception:
            pass
        if getattr(src, "_lhm", None) is not None:
            try:
                src._lhm.Close()
            except Exception:
                pass
            src._lhm = None
            src._pi_selected = None
        self._gpu.shutdown()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def source_method(self) -> str:
        return self._source.method

    @property
    def source_notes(self) -> List[str]:
        return self._source.notes

    def latest(self) -> Optional[SystemSample]:
        with self._lock:
            return self._samples[-1] if self._samples else None

    def samples_between(self, t_start: float, t_end: float) -> List[SystemSample]:
        """Campioni con interpolazione lineare ai bordi della finestra."""
        with self._lock:
            inside = [s for s in self._samples if t_start <= s.t <= t_end]
            before = next(
                (s for s in reversed(self._samples) if s.t < t_start), None
            )
            after = next((s for s in self._samples if s.t > t_end), None)
        out = list(inside)
        if before is not None and (not inside or inside[0].t - t_start > self.interval_s * 1.5):
            out.insert(0, self._interpolate(before, inside[0] if inside else after, t_start))
        if after is not None and (not inside or t_end - inside[-1].t > self.interval_s * 1.5):
            out.append(self._interpolate(inside[-1] if inside else before, after, t_end))
        return [s for s in out if s is not None]

    @staticmethod
    def _interpolate(a: Optional[SystemSample], b: Optional[SystemSample], t: float):
        if a is None or b is None or b.t == a.t:
            return a if (a and abs(a.t - t) < 0.4) else (b if (b and abs(b.t - t) < 0.4) else None)
        frac = (t - a.t) / (b.t - a.t)

        def num(x, y):
            if x is None or y is None:
                return None
            return x + (y - x) * frac

        return SystemSample(
            t=t,
            wall=a.wall + (b.wall - a.wall) * frac,
            package_energy_j=num(a.package_energy_j, b.package_energy_j),
            cpu_busy_seconds=num(a.cpu_busy_seconds, b.cpu_busy_seconds),
            cpu_percent=num(a.cpu_percent, b.cpu_percent),
            ollama_pids=b.ollama_pids or a.ollama_pids,
            ollama_io_bytes=int(num(float(a.ollama_io_bytes), float(b.ollama_io_bytes)) or 0),
            ollama_cpu_seconds=float(num(a.ollama_cpu_seconds, b.ollama_cpu_seconds) or 0.0),
            nic_bytes=int(num(float(a.nic_bytes), float(b.nic_bytes)) or 0),
            gpu_power_w=num(a.gpu_power_w, b.gpu_power_w),
            gpu_util_pct=num(a.gpu_util_pct, b.gpu_util_pct),
        )

    # ------------------------------------------------------------ calibrazione
    def calibrate_idle(self, seconds: Optional[float] = None) -> float:
        """Calibrazione idle empirica SU WINDOWS via LibreHardwareMonitor (spec §5).

        Procedura esatta richiesta:
          1. durata >= 30 s (default; sovrascrivibile solo verso l'alto);
          2. 3 ripetizioni della finestra a riposo (nessun carico generato);
          3. per ogni ripetizione: potenza media = delta energia / dt reale
             (power-integration a 0.05 s sul sensore 'CPU Package', oppure
             contatore Energy cumulato dove esiste);
          4. P_idle = MEDIANA delle potenze medie delle 3 ripetizioni [W].

        L'idle calibrato riflette esattamente il consumo a riposo della
        macchina corrente. La baseline ``idle_power_w`` viene sottratta dal
        profiler e NON e' mai attribuita al modello. Su piattaforme non-
        Windows la funzione solleva RuntimeError con messaggio esplicito
        (la validazione energetica locale e' solo Windows+LHM). Se nessun
        backend reale e' disponibile, RuntimeError dichiarato: niente TDP.
        """
        import config as _cfg

        duration_s = float(seconds or _cfg.IDLE_CALIBRATION_SECONDS)
        # spec §5: almeno 30 secondi per finestra
        duration_s = max(duration_s, 30.0)

        if platform_system() != "Windows":
            raise RuntimeError(
                self._source._local_disabled_msg
                + " Calibrazione idle non eseguibile su questa piattaforma "
                "(ambiente di sviluppo secondario)."
            )

        was_running = self._running
        if not was_running:
            self.start()
        try:
            # breve stabilizzazione prima della misura
            time.sleep(1.0)
            means: List[float] = []
            mode_used = None
            for rep in range(3):
                window = self._source.read_idle_window_j(duration_s)
                if window is None:
                    cause = self._source.last_read_error or (
                        f"metodo attivo: '{self._source.method}' "
                        "(nessun backend a contatore reale)"
                    )
                    raise RuntimeError(
                        "calibrazione idle fallita: nessun contatore di "
                        "energia/potenza package disponibile (LHM). "
                        f"Causa ripetizione {rep + 1}/3: {cause}. "
                        "Esegui 'py diagnostics.py' per il report completo "
                        "(clr/pythonnet/DLL/UAC/sensori Power)."
                    )
                delta_j, dt, mode = window
                if delta_j < 0:
                    raise RuntimeError(
                        "calibrazione idle fallita: contatore decrescente "
                        f"(delta={delta_j:.3f} J)"
                    )
                p_rep = delta_j / max(dt, 1e-6)
                means.append(p_rep)
                mode_used = mode
            power_w = sorted(means)[len(means) // 2]   # mediana di 3 misure
            self._idle_mode = mode_used
            self._idle_reps = means
            self._idle_samples_count = self._source.pi_stats().get("samples", 0) \
                if self._source.method == "power-integration" else len(means)
        finally:
            if not was_running:
                self.stop()

        self.idle_power_w = round(power_w, 3)
        self.idle_provenance = "calibrated"
        self.calibrated_at = time.time()
        return self.idle_power_w


# ---------------------------------------------------------------------------
# GPU NVIDIA (NVML) — opzionale, degradazione silenziosa
# ---------------------------------------------------------------------------
class _GPUMonitor:
    def __init__(self) -> None:
        self.available = False
        self.handle = None
        self.index = 0
        self.name: Optional[str] = None
        self.error: Optional[str] = None
        try:
            import pynvml  # nvidia-ml-py

            pynvml.nvmlInit()
            count = pynvml.nvmlDeviceGetCount()
            if count > 0:
                self.index = 0
                self.handle = pynvml.nvmlDeviceGetHandleByIndex(self.index)
                self.name = pynvml.nvmlDeviceGetName(self.handle)
                if isinstance(self.name, bytes):
                    self.name = self.name.decode("utf-8", "replace")
                self.available = True
            else:
                self.error = "nessuna GPU NVML"
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}"

    def read(self):
        if not self.available:
            return None, None
        try:
            import pynvml

            mw = pynvml.nvmlDeviceGetPowerUsage(self.handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
            return float(mw) / 1000.0, float(util.gpu)
        except Exception:
            try:
                import pynvml

                mw = pynvml.nvmlDeviceGetPowerUsage(self.handle)
                return float(mw) / 1000.0, None
            except Exception:
                return None, None

    def shutdown(self) -> None:
        try:
            import pynvml

            pynvml.nvmlShutdown()
        except Exception:
            pass


# Singleton di sessione (sezione 16: ``from .energy_session import SESSION``)
SESSION = EnergySession()
