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

    def __init__(self) -> None:
        self.method = "unavailable"
        self._lhm = None
        self._rapl_last: Optional[float] = None
        self._rapl_base: Optional[float] = None
        self._tdp_w: Optional[float] = None
        self._power_base_j: float = 0.0   # base contatore potenza per read_power_j
        self._power_last_j: Optional[float] = None
        self._notes: List[str] = []

        if self._try_lhm():
            self.method = "librehardwaremonitor"
        elif self._try_rapl():
            self.method = "rapl"
        elif self._try_power_counter():
            # contatore di energia disponibile SENZA LHM (es. RAPL esposto
            # dall'utente come file,vedi CW_ENERGY_FILE): il metodo resta
            # "rapl" per compatibilita' con il profiler.
            pass
        else:
            self.method = "tdp_estimate"
            self._tdp_w = self._guess_tdp()
            self._notes.append(
                "contatore package non disponibile: usera' calibrazione idle "
                "empirica a riposo; stima TDP solo come ultima risorsa"
            )

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

    @classmethod
    def _lhm_energy_sensor_ok(cls, sensor) -> bool:
        """SensorType==Energy + nome riconosciuto (Intel/AMD/varianti)."""
        try:
            stype = str(sensor.Type)
            if "Energy" not in stype:
                return False
            sname = str(sensor.Name).lower()
            return any(tok in sname for tok in cls._LHM_ENERGY_NAME_TOKENS)
        except Exception:
            return False

    def _lhm_value(self) -> Optional[float]:
        """Somma Energy-CPU [mJ] dai sensori LHM -> J cumulati monotoni."""
        if self._lhm is None:
            return None
        try:
            total_mj = 0.0
            found = False
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()          # senza Update() il Value resta None
                except Exception:
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                for sensor in hw.Sensors:
                    if not self._lhm_energy_sensor_ok(sensor):
                        continue
                    raw = sensor.Value
                    if raw is None:
                        continue         # sensore presente ma non ancora popolato
                    val = float(raw)
                    if val != val:       # NaN check
                        continue
                    total_mj += val
                    found = True
            if not found:
                return None
            return total_mj / 1000.0
        except Exception:
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
                            "sensor_type": str(sensor.Type),
                            "value": (None if sensor.Value is None
                                      else float(sensor.Value)),
                        })
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    # -- backend RAPL ------------------------------------------------------
    def _try_rapl(self) -> bool:
        if not hasattr(psutil, "sensors_cpu_battery") and not _rapl_files_exist():
            return False
        try:
            v = self._rapl_read()
            if v is None:
                return False
            self._rapl_base = v
            self._notes.append("contatore energy package RAPL (Linux)")
            return True
        except Exception:
            return False

    @staticmethod
    def _rapl_read() -> Optional[float]:
        import glob

        candidates: List[str] = []
        try:
            candidates += glob.glob(
                "/sys/class/power_supply/BAT*/energy_*"
            )  # container-safe proxy
        except Exception:
            pass
        try:
            candidates += glob.glob("/sys/class/powercap/intel-rapl/intel-rapl:*/energy_uj")
            candidates += glob.glob(
                "/sys/devices/virtual/powercap/intel-rapl/intel-rapl:*/energy_uj"
            )
        except Exception:
            pass
        best: Optional[float] = None
        for path in candidates:
            try:
                with open(path, "r", encoding="ascii") as fh:
                    val = float(fh.read().strip())
                if best is None or val > best:
                    best = val
            except Exception:
                continue
        if best is None:
            return None
        return best / 1_000_000.0  # uJ -> J

    def _rapl_value(self) -> Optional[float]:
        raw = self._rapl_read()
        if raw is None:
            return None
        base = self._rapl_base if self._rapl_base is not None else 0.0
        # gestisce il wrap-around del contatore
        delta_guard = raw if raw >= base else raw + 2 ** 32 * 0 + raw
        return max(raw - base, delta_guard if raw < base else raw - base)

    # -- contatore energia via file (opzionale, portabile) ------------------
    def _try_power_counter(self) -> bool:
        """Backend opzionale: legge un contatore di joule da un file.

        Configurabile con la variabile d'ambiente ``CW_ENERGY_FILE`` (o in
        .env): il file deve contenere un numero = energia cumulata [J]
        (es. sysfs RAPL esposto dall'utente, output di powerstat/nvidia-smi
        wrapper, simulatore nei test). Esporre il path del sysfs RAPL qui
        equivale al backend rapl nativo.
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
            self.method = "rapl"  # riusa il metodo dei contatori reali
            self._notes.append(f"contatore energia da file {path}")
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

        ``busy_seconds_total`` e' il tempo CPU busy aggregato di sistema dall'
        inizio della sessione (usato solo dal backend di stima).
        """
        if self.method == "librehardwaremonitor":
            return self._lhm_value()
        if self.method == "rapl":
            fv = self._file_value()
            if fv is not None:
                return fv - self._power_base_j
            return self._rapl_value()
        if self.method == "tdp_estimate":
            # Energia attiva stimata = TDP * frazione di core-busy-second
            # gia' depurata dell'idle: qui busy_seconds_total e' delta busy,
            # quindi P_idle NON viene incluso (viene sottratto a monte).
            return (self._tdp_w or 45.0) * busy_seconds_total
        return None

    def read_power_j(self) -> Optional[float]:
        """Lettura DIRETTA del contatore cumulato di energia package [J].

        Usata dalla calibrazione idle puramente empirica (delta joule su
        finestra a riposo): stessa funzione di lettura energetica usata dal
        benchmark, nessuna stima TDP. Ritorna None se nessun contatore reale
        e' disponibile (il chiamante deve dichiarare il fallback).
        """
        try:
            if self.method == "librehardwaremonitor":
                v = self._lhm_value()
                if v is None:
                    # DIAGNOSTICA REALE (non fallire silenziosamente): elenca
                    # i sensori CPU esposti da LHM cosi' l'utente capisce se
                    # mancano del tutto (UAC/driver) o se hanno nomi inattesi.
                    sensors = self.diagnose_cpu_sensors()
                    n_power = sum(1 for s in sensors
                                  if "Power" in s["sensor_type"])
                    n_energy = sum(1 for s in sensors
                                   if "Energy" in s["sensor_type"])
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
            if self.method == "rapl":
                fv = self._file_value()
                if fv is not None:
                    return fv - self._power_base_j
                return self._rapl_value()
        except Exception as exc:
            self._record_read_error(exc, "lettura contatore energia fallita")
            return None
        return None  # tdp_estimate / unavailable: nessun contatore reale

    @property
    def notes(self) -> List[str]:
        return list(self._notes)


def _rapl_files_exist() -> bool:
    import glob

    return bool(
        glob.glob("/sys/class/powercap/intel-rapl/intel-rapl:*/energy_uj")
        or glob.glob("/sys/devices/virtual/powercap/intel-rapl/intel-rapl:*/energy_uj")
    )


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
        while not self._stop.is_set():
            try:
                self.record_once()
            except Exception as exc:  # il thread non deve mai morire
                self.last_error = f"{type(exc).__name__}: {exc}"
            time.sleep(self.interval_s)

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
            self._stop.clear()
            # allinea la base del contatore di potenza al momento dell'avvio:
            # cosi' read_power_j()/package_energy_j restano coerenti tra
            # calibrazione empirica e benchmark anche dopo stop/riconnessione
            pb = self._source.read_power_j()
            if pb is not None:
                self._source._power_base_j = pb
            self._cpu_t0 = self._system_busy_seconds()
            self._samples.clear()
            self._thread = threading.Thread(
                target=self._loop, name="cw-energy-sampler", daemon=True
            )
            self._running = True
        self._thread.start()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stop.set()
            self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

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
        """Calibrazione idle PURAMENTE EMPIRICA basata su campionamento a riposo.

        Logica (identica a quella usata per il benchmark, nessuna stima TDP):
          1. definisce la finestra ``duration_s`` (default da config);
          2. legge E_start dal contatore cumulato di energia package;
          3. dorme duration_s con il sistema fermo (nessun carico generato);
          4. legge E_end dallo stesso contatore;
          5. P_idle = (E_end - E_start) / duration_s [W].

        L'idle calibrato riflette quindi esattamente il consumo a riposo della
        macchina corrente. Se nessun contatore reale e' disponibile (ne' LHM
        ne' RAPL ne' file custom), viene sollevato RuntimeError con messaggio
        esplicito: il fallback TDP non e' piu' contemplato.
        """
        import config as _cfg

        duration_s = float(seconds or _cfg.IDLE_CALIBRATION_SECONDS)
        duration_s = max(duration_s, 0.5)

        was_running = self._running
        if not was_running:
            self.start()
        try:
            # breve stabilizzazione prima della lettura E_start
            time.sleep(min(0.5, duration_s * 0.1))
            e_start = self._source.read_power_j()
            t_start = time.monotonic()
            if e_start is None:
                cause = self._source.last_read_error or (
                    f"metodo attivo: '{self._source.method}' "
                    "(nessun backend a contatore reale)"
                )
                raise RuntimeError(
                    "calibrazione idle fallita: nessun contatore di energia "
                    "package disponibile (LHM/RAPL/file). La calibrazione "
                    "empirica richiede una lettura reale dei Joule. "
                    f"Causa: {cause}. Esegui 'py diagnostics.py' per il "
                    "report completo (clr/pythonnet/DLL/UAC)."
                )
            # campionamento passivo durante la finestra (per note diagnostiche)
            while True:
                elapsed = time.monotonic() - t_start
                if elapsed >= duration_s:
                    break
                time.sleep(min(0.2, max(duration_s - elapsed, 0.01)))
                self.record_once()
            e_end = self._source.read_power_j()
            t_end = time.monotonic()
            if e_end is None:
                raise RuntimeError(
                    "calibrazione idle fallita: contatore non leggibile a fine finestra"
                )
            dt = max(t_end - t_start, 1e-6)
            delta_j = e_end - e_start
            if delta_j < 0:
                raise RuntimeError(
                    "calibrazione idle fallita: contatore decrescente "
                    f"(E_start={e_start:.3f} J, E_end={e_end:.3f} J)"
                )
            power_w = delta_j / dt
        finally:
            if not was_running:
                self.stop()

        self.idle_power_w = round(power_w, 3)
        # NB: usare ``duration_s`` locale definita sopra, NON variabili esterne.
        self.idle_provenance = "calibrated" if duration_s >= 2.0 else "auto_micro"
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
