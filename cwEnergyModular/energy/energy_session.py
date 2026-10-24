# -*- coding: utf-8 -*-
"""
energy/energy_session.py — Sessione CasualWatt: campionamento continuo.

Questa modulo espone il singleton ``SESSION`` usato da tutti gli altri moduli
energetici. Un thread daemon campiona a intervallo fisso:

* energia del package CPU: su Windows il contatore cumulativo EMI
  (``energy.emi_backend``, metodo principale dal 23/10, senza token elevato),
  con LibreHardwareMonitor via pythonnet come fallback dichiarato quando il
  driver EMI manca; su Linux i contatori RAPL (``energy.rapl_backend``).
  ``CW_PRIMARY_CHANNEL=lhm`` forza l'ordine precedente per confrontare i canali;
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


#: Metodi che possono esprimere un NUMERO di energia. Sono i metodi che leggono
#: un contatore o integrano una potenza reale; tutto il resto ("unavailable",
#: "librehardwaremonitor" senza sensori Energy/Power) deve produrre N/A nel CSV,
#: non uno zero. La lista sta QUI, accanto a chi quei valori li produce, perche'
#: il 24/10 ne esisteva una copia in benchmark_unified.py:402 rimasta ferma
#: quando il backend RAPL e' stato aggiunto: su Linux il campo judge_energy_j
#: sarebbe stato N/A anche con un contatore funzionante (test in
#: tests/test_energy_corrections.py).
MEASURED_METHODS = ("emi-counter", "power-integration",
                    "librehardwaremonitor-energy", "energy-file", "rapl")


def _median_sampling_interval(points: List[tuple], t_start: float,
                              t_end: float) -> Optional[float]:
    """Cadenza OSSERVATA (mediana dei delta) dei campioni nella finestra.

    La media e' trascinata dalle pause del thread (misurato: 0,0506 s ->
    0,0770 s sotto spin); la mediana descrive il passo tipico. Meno di due
    campioni in finestra: cadenza non stimabile, quindi None.
    """
    ts = sorted(p[0] for p in points if t_start <= p[0] <= t_end)
    if len(ts) < 2:
        return None
    deltas = sorted(b - a for a, b in zip(ts, ts[1:]) if b > a)
    if not deltas:
        return None
    n = len(deltas)
    mid = n // 2
    med = deltas[mid] if n % 2 else 0.5 * (deltas[mid - 1] + deltas[mid])
    return round(med, 6)


# ---------------------------------------------------------------------------
# Sorgente energia package CPU
# ---------------------------------------------------------------------------
class _CPUJouleSource:
    """Astrae ``package_energy_j`` cumulata; sceglie il backend disponibile."""

    #: Campionamento del sensore CPU Package [W] per power-integration (spec §4)
    POWER_SAMPLE_INTERVAL_S = 0.05
    # Timeout massimo del probe LHM in-process: oltre, si presume un hard-
    # crash .NET e si ripiega sul sottoprocesso isolato (watchdog).
    PROBE_INPROCESS_TIMEOUT_S = 90.0
    #: Nome sensore PREFERITO su Intel (i9-13900HK espone "CPU Package")
    _PREFERRED_POWER_NAMES = ("cpu package",)
    #: Fallback accettati SOLO se il preferito manca (AMD / varianti chipset)
    _FALLBACK_POWER_NAMES = ("package", "package power", "cpu ppt")

    def __init__(self) -> None:
        self.method = "unavailable"
        self._lhm = None
        #: Versione dell'assembly LHM effettivamente caricato ("" se non nota).
        #: Serve a ``backend_version``: il sorgente letto puo' essere 0.9.6 e
        #: il runtime 0.9.4, e una riga di CSV non deve confonderli.
        self._lhm_version: str = ""
        self._emi = None   # backend Windows EMI (energy.emi_backend.EMICounterBackend)
        self._rapl = None  # backend Linux RAPL (rapl_backend.RAPLBackend)
        # True solo DOPO Computer().Open() riuscito (spec §6: apertura unica).
        # I lettori di sensori controllano questo flag: un'apertura fallita o
        # non ancora eseguita non deve mai generare NullReferenceException.
        self._lhm_opened = False
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
        # ---- emi-counter (metodo principale Windows dal 23/10) -------------
        # Buffer (t_monotono, cum_j) del contatore cumulativo, campionato a
        # 0,05 s: serve per leggere la finestra AI BORDI ESATTI come fa il
        # buffer del thread PI (per query brevi il delta dei campioni di
        # sessione a ~0,5 s sarebbe troppo rozzo).
        self._emi_thread: Optional[threading.Thread] = None
        self._emi_stop = threading.Event()
        self._emi_lock = threading.Lock()
        self._emi_samples: List[tuple] = []     # (t_monotono, cum_j) del PKG
        # PP1 (involto grafico) nella STESSA IOCTL del PKG: (t, cum_j, ts_j)
        # dove ts_j e' il timestamp del record PP1 in unita' da 100 ns. Il
        # timestamp per dominio esiste per un solo motivo: distinguere "il
        # dominio ha consumato zero" da "il driver non aggiorna quel canale".
        self._emi_pp1_samples: List[tuple] = []
        #: Perche' l'ultima lettura del dominio PP1 ha risposto None (note
        #: del CSV): un'assenza senza motivazione e' ambigua.
        self._pp1_read_reason: Optional[str] = None
        self._local_disabled_msg = (
            "Local CPU energy measurement is available on Windows (LibreHardwareMonitor) "
            "and Linux (RAPL via /sys/class/powercap/)."
        )
        #: Callback opzionale di avanzamento (impostato da SESSION prima di
        #: start()/calibrate_idle): mostra i progressivi dell'apertura LHM,
        #: che puo' richiedere minuti e altrimenti sembra un blocco.
        self._progress_cb = None
        # Watchdog del probe in-process: se Computer().Open() non risponde
        # entro il timeout (hard-crash .NET che congela il worker), si ripiega
        # sul sottoprocesso isolato. Disattivabile con CW_LHM_WATCHDOG=0.
        import os as _os0

        self._probe_watchdog = _os0.environ.get("CW_LHM_WATCHDOG", "1") != "0"
        # Probe PIGRO (CW_LHM_LAZY=1 di default su Windows): l'apertura di
        # Computer() puo' richiedere minuti (bus SMBus/HID/EC); eseguirla nel
        # costruttore significava bloccare l'import del modulo SESSION e
        # far sembrare la GUI congelata PRIMA di qualunque messaggio. Ora il
        # backend LHM viene attivato solo al primo start()/calibrazione, con
        # progressivi espliciti. CW_ENERGY_FILE continua a essere rilevato
        # subito (e' una lettura di file, non tocca CLR/pythonnet).
        self._lazy_pending = False
        try:
            import os as _os1

            lazy_default = "1" if platform_system() == "Windows" else "0"
            lazy = _os1.environ.get("CW_LHM_LAZY", lazy_default) != "0"
        except Exception:  # pragma: no cover
            lazy = platform_system() == "Windows"

        if self._try_power_counter():
            # Contatore Joule ESPOSTO DALL'UTENTE (CW_ENERGY_FILE): niente
            # probe LHM (evita figli inutili su Linux/dev e rispetta la
            # precedenza 'solo se LHM non disponibile' del vecchio ordine).
            pass
        elif (platform_system() == "Windows" and self._primary_channel() == "emi"
                and self._try_emi()):
            # 23/10: il METODO PRINCIPALE su Windows e' il contatore EMI
            # (cumulativo, ctypes, senza token elevato). Con EMI attivo il
            # probe LHM NON viene eseguito nemmeno pigramente: niente .NET,
            # niente watchdog, niente apertura Computer da minuti. LHM resta
            # il fallback completo se il driver EMI manca (CW_PRIMARY_CHANNEL
            # =lhm forza comunque il vecchio ordine).
            pass
        elif lazy and platform_system() == "Windows":
            self._lazy_pending = True
            self._notes.append(
                "probe LHM in attesa (lazy): verra' eseguito al primo avvio "
                "di sessione/calibrazione, con progressivi nel log"
            )
        elif platform_system() == "Windows":
            self._activate_backend()
        elif platform_system() == "Linux":
            # Backend Linux: contatori RAPL via /sys/class/powercap/
            self._activate_rapl_backend()
        else:
            # Piattaforma non-Windows/non-Linux (es. macOS): misurazione
            # locale NON supportata (future work). Niente clr/LHM (spec §2);
            # eventuale simulatore di test gia' gestito sopra da CW_ENERGY_FILE.
            self.method = "unavailable"
            self._notes.append(self._local_disabled_msg)

    # -- canale principale (EMI vs LHM) ------------------------------------
    @staticmethod
    def _primary_channel() -> str:
        """Canale preferito su Windows: "emi" (default dal 23/10) o "lhm".

        CW_PRIMARY_CHANNEL=lhm ripristina l'ordine precedente senza toccare
        codice: serve per confrontare i due canali sulla stessa macchina.
        """
        try:
            import os as _os

            val = _os.environ.get("CW_PRIMARY_CHANNEL", "emi").strip().lower()
        except Exception:  # pragma: no cover
            val = "emi"
        return "lhm" if val == "lhm" else "emi"

    def _try_emi(self) -> bool:
        """Aggancia il contatore EMI; True solo se la PRIMA lettura riesce.

        Nessun fallback silenzioso: se il device non c'e' o l'IOCTL fallisce,
        ritorna False e il chiamante prosegue con la catena LHM esistente.
        """
        try:
            from energy.emi_backend import EMICounterBackend, METHOD_LABEL

            backend = EMICounterBackend()
            if backend.available:
                self._emi = backend
                self.method = METHOD_LABEL
                # Il sampler NON parte qui: l'import del modulo non deve mai
                # avviare thread di misura (stessa regola del thread PI, che
                # parte in EnergySession.start()).
                self._notes.extend(backend.notes)
                self._notes.append(
                    "metodo principale 'emi-counter': contatore package "
                    "cumulativo (pWh) letto via IOCTL; LHM non interrogata "
                    "(fallback automatico solo se il canale EMI manca)"
                )
                return True
            self._notes.extend(backend.notes)
            self._notes.append(
                "EMI non disponibile: si usa la catena LHM "
                "(energy-counter / power-integration)"
            )
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            self._notes.append(f"EMI non disponibile ({type(exc).__name__})")
        return False

    def _activate_backend(self) -> bool:
        """Sonda LHM e classifica il metodo energetico (idempotente).

        Ritorna True se un backend reale risulta attivo dopo la chiamata.
        Chiamata dal costruttore (modalita' eager) o pigramente al primo
        start()/calibrazione (modalita' lazy, default su Windows).
        """
        if self._lazy_pending:
            self._lazy_pending = False
        if self.method != "unavailable":
            return True
        if self._try_lhm():
            # LHM agganciata E APERTA con sensori validi verificati.
            if self._lhm_value() is not None:
                self.method = "librehardwaremonitor-energy"
                self._notes.append("LHM: contatore Energy-CPU presente")
            else:
                # Sensore Power GIA' selezionato/validato durante il probe:
                # riuso qui, senza doppie scansioni dell'assembly.
                power_sel = (self._pi_sensor_name
                             and getattr(self, "_pi_selected", None)) \
                    or self._select_power_sensor()
                if power_sel is not None:
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
        return self.method not in ("unavailable",)

    # -- backend RAPL (Linux) -------------------------------------------------
    def _activate_rapl_backend(self) -> bool:
        """Inizializza il backend RAPL per Linux.

        Tenta di creare un'istanza di RAPLBackend. Se disponibile, imposta
        self.method = "rapl" e ritorna True. Altrimenti degrada a "unavailable"
        con nota diagnostica.

        Returns:
            True se il backend RAPL e' attivo, False altrimenti.
        """
        try:
            from energy.rapl_backend import RAPLBackend
            self._rapl = RAPLBackend()
            if self._rapl.available:
                self.method = "rapl"
                self._notes.extend(self._rapl.notes)
                return True
            else:
                self.method = "unavailable"
                self._notes.extend(self._rapl.notes)
                return False
        except ImportError as exc:
            self.method = "unavailable"
            self._notes.append(f"RAPL backend non importabile: {exc}")
            return False
        except Exception as exc:
            self.method = "unavailable"
            self._notes.append(f"RAPL inizializzazione fallita: {exc}")
            return False

    # -- backend LHM -------------------------------------------------------
    def _try_lhm(self) -> bool:
        # pythonnet + LHM possono CRASHARE il processo con un'eccezione .NET
        # NON intercettabile dal try/except Python (caso reale osservato:
        # InternalPythonnetException/NullReferenceException in
        # TypeManager.AllocateTypeObject durante Computer().Open() su build
        # pythonnet non compatibili con la minor CPython corrente). Il probe
        # completo viene quindi eseguito in un FIGLIO ISOLATO: se il figlio
        # crasha, il padre degrada in modo pulito e riporta l'eccezione
        # esatta letta dallo stderr del figlio.
        import os as _os

        if _os.environ.get("CW_LHM_PROBE_CHILD") == "1":
            return self._lhm_probe_child()
        # STRATEGIA (validata sul machine target): il processo PRINCIPALE
        # elevato apre Computer() e scansiona i sensori senza crash — lo
        # dimostrano i log di diagnostics.py (CPU Package trovato, 4 Power).
        # Si tenta quindi prima IN-PROCESS con try/except: se pythonnet
        # solleva in modo gestibile si degrada; se invece CRASHA il figlio
        # watchdog muore e il padre riprova nel FIGLIO isolato (anti-crash
        # per le build pythonnet difettose). L'ordine precedente (figlio
        # primo) produceva falsi negativi: rc=0xE0434352 nel contesto del
        # figlio -c anche quando l'in-process funzionava perfettamente.
        ok = self._lhm_probe_inprocess()
        if ok:
            return True
        if not getattr(self, "_probe_watchdog", False):
            # Watchdog disattivato (CW_LHM_WATCHDOG=0): niente figli.
            return False
        return self._lhm_probe_parent()

    def _lhm_probe_inprocess(self) -> bool:
        """Probe LHM nel processo corrente, con watchdog anti-crash .NET.

        Il tentativo in-process e' sorvegliato da un thread watchdog: se la
        chiamata a Computer().Open() non completa entro il timeout (segno di
        un hard-crash .NET/pythonnet che congela o uccide il worker), il flag
        ``_probe_watchdog_fired`` consente al chiamante (il PADRE, ancora
        vivo) di ripiegare sul sottoprocesso isolato. Le eccezioni gestibili
        vengono propagate al chiamante come False con nota esplicita.
        I progressivi opzionali (GUI) passano tramite ``self._progress_cb``.
        """
        import threading as _th
        import time as _t

        holder: dict = {"done": _th.Event(), "result": None}

        def _worker():
            try:
                holder["result"] = self._lhm_probe_child()
            except BaseException as exc:  # noqa: BLE001
                holder["result"] = False
                self._notes.append(
                    f"probe in-process eccezione ({type(exc).__name__}): "
                    f"{exc!s:.200}"
                )
            finally:
                holder["done"].set()

        th = _th.Thread(target=_worker, name="cw-lhm-probe", daemon=True)
        th.start()
        # cuori pulsanti: senza questi, un'apertura lenta (fino a ~2 minuti
        # su laptop con molti bus HID/SMBus) sembra un blocco della GUI
        _t0 = _t.monotonic()
        while not holder["done"].wait(timeout=5.0):
            if self._progress_cb:
                self._progress_cb(
                    f"Apertura sensori hardware in corso… "
                    f"{_t.monotonic() - _t0:.0f}s elapsed "
                    f"(timeout watchdog {self.PROBE_INPROCESS_TIMEOUT_S:.0f}s)"
                )
        finished = holder["done"].is_set()
        if not finished:
            self._notes.append(
                "probe in-process TIMEOUT > "
                f"{self.PROBE_INPROCESS_TIMEOUT_S:.0f}s (possibile crash .NET "
                "non gestito): ripiego sul sottoprocesso isolato"
            )
            return False
        result = holder["result"] is True
        if result:
            self._notes.append("probe LHM in-process OK (Computer() aperto)")
        return result

    # ------------------------------------------------------------------ probe
    def _lhm_probe_parent(self) -> bool:
        """Esegue il probe LHM in un sottoprocesso isolato (anti-crash).

        Ritorna True SOLO se il figlio conferma l'apertura pulita di
        Computer() con almeno un sensore valido. In tal caso la stringa
        ``CW_LHM_PROBE_OK=1`` viene iniettata nell'ambiente: consente alle
        istanze successive (es. GUI riavviata) di saltare il probe e aprire
        direttamente in-process — comportamento verificato dal log di
        diagnostics.py sul machine target. Se invece il figlio fallisce o
        crasha (.NET non gestito), NON si riprova in-process: si degrada in
        modo pulito con nota esplicita.
        """
        import os as _os
        import subprocess
        import sys

        if platform_system() != "Windows":
            # Niente figlio su Linux/macOS: LHM non esiste e il probe
            # sarebbe solo rumore nei log (nota unica, non doppia).
            self._notes.append("LHM non applicabile (piattaforma non Windows)")
            return False

        # Probe gia' superato in questo ambiente (vedi docstring): apertura
        # diretta, niente figli inutili a ogni avvio.
        if _os.environ.get("CW_LHM_PROBE_OK") == "1":
            return self._lhm_probe_child()

        cmd = [
            sys.executable, "-B", "-c",
            ("import sys, energy.energy_session as m;"
             "ok = m.SESSION._source._lhm_probe_child();"
             "print('LHM_OK' if ok else 'LHM_NO');"
             "sys.exit(0 if ok else 2)"),
        ]
        try:
            from config import BASE_DIR as _BASE
        except Exception:  # pragma: no cover - standalone
            _BASE = None
        # CW_LHM_PROBE_OK rimosso dall'ambiente del figlio: il probe deve
        # essere reale anche se il padre ha ereditato il flag da sessioni ok.
        env = dict(_os.environ, CW_LHM_PROBE_CHILD="1")
        env.pop("CW_LHM_PROBE_OK", None)
        try:
            r = subprocess.run(
                cmd, cwd=(str(_BASE) if _BASE else None), env=env,
                capture_output=True, text=True, timeout=60,
            )
        except Exception as exc:  # noqa: BLE001
            self._notes.append(f"probe LHM non eseguibile ({type(exc).__name__})")
            return False
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        for ln in out.splitlines():
            if ln.startswith("LHM_NOTE:"):
                self._notes.append(ln[9:].strip())
        if r.returncode != 0:
            tail = "\n".join((err or out).splitlines()[-8:])
            self._notes.append(
                f"PROBE LHM nel figlio FALLITO (rc={r.returncode}): {tail[:400]}. "
                "Nessun tentativo in-process (rischio crash .NET non gestito)."
            )
            return False
        if "LHM_OK" in out:
            return True
        self._notes.append(
            "probe LHM: Computer() aperto ma nessun sensore Energy/Power CPU "
            "valido (dettaglio nelle note del figlio)"
        )
        return False

    def _lhm_probe_child(self) -> bool:
        """Nel FIGLIO (o dopo probe superato): aggancia LHM e valida i sensori.

        Apre il Computer() UNA sola volta e verifica che ESISTA almeno un
        sensore leggibile (contatore Energy oppure sensore Power idoneo alla
        power-integration). Solo allora ritorna True: un False garantisce
        che il chiamante non avvii mai il thread PI contro un oggetto
        pythonnet rotto (causa originale dell'InternalPythonnetException).
        """
        ok = self._try_lhm_direct()
        if not ok:
            return False
        if self._progress_cb:
            self._progress_cb(
                "Computer().Open() in corso (puo' richiedere fino a ~2 minuti "
                "su laptop con molti bus USB/HID/SMBus)…"
            )
        try:
            self.open_computer()
        except BaseException:  # noqa: BLE001 - il crash .NET finisce qui
            import traceback

            print("LHM_NOTE: crash in Computer().Open():\n"
                  + traceback.format_exc().replace("\n", " | "))
            return False
        has_energy = self._lhm_value() is not None
        power_sel = None if has_energy else self._select_power_sensor()
        if has_energy or power_sel is not None:
            print("LHM_OK")
            if self._progress_cb:
                self._progress_cb(
                    "Sensori LHM validati: metodo "
                    + ("energy-counter" if has_energy
                       else f"power-integration su '{self._pi_sensor_name}'")
                )
            return True
        self._notes.append(
            "Computer() aperto ma NESSUN sensore Energy/Power CPU esposto"
        )
        return False

    # ------------------------------------------------------------------ LHM
    def _try_lhm_direct(self) -> bool:
        # Anti-ricorsione: se l'assembly e' gia' agganciata in questo
        # processo (es. secondo tentativo di calibrazione dopo un fallimento,
        # o retry del padre dopo il probe), non si ricrea un Computer():
        # AddReference/Assembly.Load ripetuti su pythonnet 3.x possono dare
        # eccezioni gestite che verrebbero scambiate per "LHM assente".
        if self._lhm is not None:
            return True
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
            try:
                # versione dell'assembly CARICATO, non del sorgente letto:
                # e' l'unica che descrive il comportamento a runtime.
                self._lhm_version = str(
                    comp.GetType().Assembly.GetName().Version)
            except Exception:
                self._lhm_version = ""
            comp.IsCpuEnabled = True
            comp.IsGpuEnabled = True
            # Il computer NON viene aperto qui: l'apertura e' delegata a
            # open_computer(), unico punto di creazione/apertura (spec §6)
            # con gestione esplicita delle eccezioni .NET.
            self._lhm = comp
            self._notes.append("LibreHardwareMonitorLib agganciata")
            return True
        except Exception as exc:  # noqa: BLE001 - degradazione voluta
            self._notes.append(f"LHM non disponibile ({type(exc).__name__})")
            return False

    def open_computer(self) -> None:
        """Apre il Computer() LHM UNA sola volta (spec §6).

        Idempotente: richiami successivi sono no-op. Le eccezioni vengono
        propagate al chiamante (che le logga): in questo modo un crash
        durante Open() non puo' mai essere mascherato da un 'successo'
        silenzioso, e la diagnostica resta veritiera.
        """
        if self._lhm_opened or self._lhm is None:
            return
        try:
            self._lhm.Open()
        except Exception as exc:  # propagata dopo pulizia stato
            self._lhm = None
            self._notes.append(
                f"Computer().Open() fallita ({type(exc).__name__}): sensore "
                "CPU non disponibile"
            )
            raise
        self._lhm_opened = True

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
        if self._lhm is None or not self._lhm_opened:
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
        if self._lhm is None or not self._lhm_opened:
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
        if self._lhm is None or not self._lhm_opened:
            return out
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()
                except Exception:
                    continue
                if not self._lhm_is_cpu_hw(hw):
                    continue
                subs = list(getattr(hw, "SubHardware", []) or [])
                for sub in [hw] + subs:
                    for sensor in sub.Sensors:
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
        if self._lhm is None or not self._lhm_opened:
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
            # Cache dell'oggetto sensore: _read_power_w_direct() lo riusa e
            # il costruttore evita una seconda scansione dell'assembly.
            self._pi_selected = chosen
            # Nota DIAGNOSTICA sempre presente quando si seleziona un
            # sensore Power: rende nel log la scelta fatta (preferito vs
            # fallback) — richiesta di verifica sul machine target.
            kind = ("preferito" if chosen is preferred else "fallback")
            self._notes.append(
                f"sensore Power selezionato per power-integration: "
                f"'{self._pi_sensor_name}' ({kind}); Power visti: "
                f"{', '.join(seen_power) or '-'}"
            )
        return chosen

    def _read_power_w_direct(self) -> Optional[float]:
        """Legge il valore [W] del sensore selezionato (None se non popolato)."""
        if self._lhm is None or not self._lhm_opened:
            return None
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
                        # Match per IDENTITA' dell'oggetto selezionato, oppure per
                        # nome ESATTAMENTE coincidente MA solo se il sensore e'
                        # di tipo Power. Senza il guard sul tipo il confronto per
                        # nome cadeva sul primo omonimo: LibreHardwareMonitor
                        # espone un sensore Temperatura chiamato "CPU Package"
                        # (IntelCpu.cs:401) PRIMA dell'omonimo Power (:480), e
                        # _pi_loop() integrava gradi·celsius come joule.
                        # Misurato 23/10: esperiment_results/
                        # lhm_readpath_probe_20261023_132621.csv — lettura di
                        # produzione 64/68/67 "W" (°C) contro 9,37/18,78/11,37 W
                        # del sensore Power reale.
                        if sensor is not sel and not (
                            str(sensor.Name) == self._pi_sensor_name
                            and self._lhm_sensor_type_name(sensor).strip().lower() == "power"
                        ):
                            continue
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

    # -- emi-counter: sampler del cumulativo e finestra esatta --------------
    def _emi_loop(self) -> None:
        """Campiona il contatore EMI cumulativo ogni 0,05 s.

        NON integra nulla: il contatore e' gia' energia. Il buffer (t, J)
        serve solo a poter collocare i bordi di una finestra trascorsa fra
        due campioni (lettura esatta ai bordi, come per il thread PI).

        UNA sola IOCTL per tick alimenta sia il PKG sia il PP1: leggere i
        due domini con due chiamate avrebbe significato due record diversi
        nella stessa riga di CSV, e il delta PP1 non sarebbe piu' sullo
        stesso istante del delta PKG.
        """
        while not self._emi_stop.is_set():
            t = time.monotonic()
            cum = None
            cum_pwh = None
            pp1 = None
            try:
                if self._emi is not None:
                    domains = self._emi.read_domains() if hasattr(
                        self._emi, "read_domains") else None
                    if domains is not None:
                        # (J, ts, pWh): il pWh e' il grezzo del contatore,
                        # persistito accanto alla finestra per rendere la
                        # misura revisionabile (alt_lhm §3).
                        cum = domains["pkg"][0]
                        cum_pwh = domains["pkg"][2]
                        pp1 = (domains["pp1"][0], domains["pp1"][1])
                    else:
                        cum = self._emi.read_cumulative_energy_j()
            except Exception:
                cum = None
                pp1 = None
            if cum is not None:
                with self._emi_lock:
                    if self._emi_samples and cum < self._emi_samples[-1][1]:
                        # contatore decresciuto (reset del driver/riapertura):
                        # si riparte il buffer, niente estrapolazioni false
                        self._emi_samples.clear()
                    self._emi_samples.append((t, cum, cum_pwh))
                    if len(self._emi_samples) > 4000:
                        del self._emi_samples[:2000]
            if pp1 is not None:
                with self._emi_lock:
                    if (self._emi_pp1_samples
                            and pp1[0] < self._emi_pp1_samples[-1][1]):
                        self._emi_pp1_samples.clear()
                    self._emi_pp1_samples.append((t, pp1[0], pp1[1]))
                    if len(self._emi_pp1_samples) > 4000:
                        del self._emi_pp1_samples[:2000]
            self._emi_stop.wait(self.POWER_SAMPLE_INTERVAL_S)

    def _start_emi_sampling(self) -> None:
        if self._emi_thread is not None and self._emi_thread.is_alive():
            return
        self._emi_stop.clear()
        self._emi_thread = threading.Thread(
            target=self._emi_loop, name="cw-emi-sampler", daemon=True
        )
        self._emi_thread.start()

    def stop_emi_sampling(self) -> None:
        """Arresta il sampler EMI (join entro 5 s, stessa regola del PI)."""
        th = self._emi_thread
        if th is None:
            return
        self._emi_stop.set()
        th.join(timeout=5.0)
        self._emi_thread = None

    def _emi_cum_at(self, buf: List[tuple], t: float) -> Optional[float]:
        """Contatore interpolato linearmente all'istante t (None fuori copertura).

        Funziona sia sui buffer a due campi ``(t, cum_j)`` del PKG sia su
        quelli a tre ``(t, cum_j, ts_j)`` di PP1: indicizza, non spacchetta.
        """
        if not buf:
            return None
        if t <= buf[0][0]:
            # bordo sinistro: arretrato massimo 1 s, poi None (nessuna
            # estrapolazione del cumulativo)
            return buf[0][1] if buf[0][0] - t <= 1.0 else None
        if t >= buf[-1][0]:
            return buf[-1][1] if t - buf[-1][0] <= 1.0 else None
        import bisect
        ts = [p[0] for p in buf]
        i = bisect.bisect_left(ts, t)
        t0, e0 = buf[i - 1][0], buf[i - 1][1]
        t1, e1 = buf[i][0], buf[i][1]
        if t1 == t0:
            return e1
        return e0 + (e1 - e0) * (t - t0) / (t1 - t0)

    def _emi_field_at(self, buf: List[tuple], t: float,
                      idx: int) -> Optional[float]:
        """Campo ``idx`` del record interpolato a t, con le stesse regole dei
        bordi di ``_emi_cum_at`` (nessuna estrapolazione oltre 1 s).

        Serve ai valori GREZZI (pWh) di ``raw_start``/``raw_end``: il buffer
        campiona a 0,05 s, quindi un bordo di finestra cade quasi sempre fra
        due letture. Il valore e' interpolato, non inventato, e la colonna
        ``raw_unit`` dice l'unita' nativa.
        """
        if not buf or len(buf[0]) <= idx or len(buf[-1]) <= idx:
            return None
        if t <= buf[0][0]:
            return float(buf[0][idx]) if buf[0][0] - t <= 1.0 else None
        if t >= buf[-1][0]:
            return float(buf[-1][idx]) if t - buf[-1][0] <= 1.0 else None
        import bisect
        ts = [p[0] for p in buf]
        i = bisect.bisect_left(ts, t)
        t0, v0 = buf[i - 1][0], buf[i - 1][idx]
        t1, v1 = buf[i][0], buf[i][idx]
        if t1 == t0:
            return float(v1)
        return v0 + (v1 - v0) * (t - t0) / (t1 - t0)

    @staticmethod
    def _observed_interval_s(points: List[tuple], t_start: float,
                             t_end: float) -> Optional[float]:
        """Cadenza OSSERVATA (mediana dei delta) del buffer nella finestra."""
        return _median_sampling_interval(points, t_start, t_end)

    def version_label(self) -> str:
        """Versione del percorso di lettura attivo (per ``backend_version``).

        Non e' la versione del driver hardware: e' cio' che possiamo
        dichiarare con certezza. Per LHM e' l'assembly effettivamente caricato
        (non il sorgente letto), per RAPL la release del kernel, per EMI il
        contratto del reader e l'IOCTL.
        """
        if self.method == "emi-counter":
            from energy import emi_backend
            return emi_backend.BACKEND_VERSION
        if self.method in ("power-integration", "librehardwaremonitor-energy",
                           "energy-file"):
            return (f"LibreHardwareMonitorLib {self._lhm_version}"
                    if self._lhm_version
                    else "LibreHardwareMonitorLib (versione non leggibile)")
        if self.method == "rapl":
            import platform
            return f"linux-rapl (kernel {platform.release()})"
        return ""

    def _emi_pp1_frozen(self, buf: List[tuple], t_start: float,
                        t_end: float) -> bool:
        """True se il registro PP1 NON e' stato aggiornato nella finestra.

        Il record EMI porta un timestamp PER dominio: se i timestamp dei
        campioni interni alla finestra sono tutti identici, il canale non
        viene popolato dal driver e il suo valore e' vecchio, non zero.
        Riportarlo come 0,000 J vorrebbe dire dichiarare una misura che non
        c'e'. Con meno di due campioni in finestra la domanda non e'
        decidibile e si lascia rispondere alla copertura del buffer.
        """
        inside = [p for p in buf if t_start <= p[0] <= t_end and len(p) > 2]
        if len(inside) < 2:
            return False
        return len({p[2] for p in inside}) == 1

    def emi_window_energy_j(self, t_start: float, t_end: float,
                            exclude_windows: Optional[List[tuple]] = None,
                            domain: str = "pkg") -> Optional[float]:
        """Delta del CONTATORE cumulativo sulla finestra, letti i bordi dal
        buffer a 0,05 s (nessuna integrazione trapezoidale: il cumulativo
        NON la richiede). Le sottofinestre escluse (LLM Judge) sono rimosse
        alla fonte: si somma solo la differenza sui segmenti tenuti.

        ``domain`` seleziona il dominio del record: "pkg" (come il package
        e' sempre stato letto) o "pp1" (involto grafico, campo informativo
        che NON si somma al package). Altri domini non sono campionati dal
        sampler e rispondono None con la ragione dichiarata.

        Ritorna None se il metodo non e' 'emi-counter', se il backend non ha
        letture, se il buffer non copre la finestra (il chiamante degrada
        al fallback dichiarato sui campioni) o se il dominio e' fermo.
        La ragione del None finisce in ``pp1_read_reason`` per le note del
        CSV: un'assenza muta e' ambigua quanto un numero sbagliato.
        """
        if domain == "pp1":
            # la ragione e' lo slot DELL'ultima lettura PP1: una lettura del
            # package non la deve cancellare (il profiler le fa entrambe)
            self._pp1_read_reason = None
        if self.method != "emi-counter":
            return None
        if domain == "pkg":
            with self._emi_lock:
                buf = list(self._emi_samples)
        elif domain == "pp1":
            with self._emi_lock:
                buf = list(self._emi_pp1_samples)
        else:
            self._pp1_read_reason = (
                f"dominio {domain!r} non campionato dal sampler EMI "
                "(solo pkg e pp1)"
            )
            return None
        if len(buf) < 2:
            if domain == "pp1":
                self._pp1_read_reason = (
                    "nessun campione PP1 nel buffer (dominio non esposto "
                    "dal driver o letture fallite)"
                )
            return None
        if domain == "pp1" and self._emi_pp1_frozen(buf, t_start, t_end):
            self._pp1_read_reason = (
                "registro PP1 fermo nella finestra: il timestamp del dominio "
                "non avanza, quindi il valore sarebbe vecchio, non zero"
            )
            return None
        segments = [(max(t_start, a), min(t_end, b)) for a, b in
                    _free_subintervals((t_start, t_end),
                                       sorted(exclude_windows or []))]
        total = 0.0
        for (a, b) in segments:
            ca, cb = self._emi_cum_at(buf, a), self._emi_cum_at(buf, b)
            if ca is None or cb is None or cb < ca:
                if domain == "pp1" and self._pp1_read_reason is None:
                    self._pp1_read_reason = (
                        "buffer PP1 non copre la finestra richiesta "
                        "(nessuna estrapolazione del cumulativo)"
                    )
                return None
            total += cb - ca
        return round(max(total, 0.0), 6)

    # -- B1: energia ESATTA su una finestra dal buffer a 0,05 s -------------
    def pi_window_energy_j(self, t_start: float, t_end: float,
                           exclude_windows: Optional[List[tuple]] = None
                           ) -> Optional[float]:
        """Energia trapezoidale integrata ESATTAMENTE tra t_start e t_end.

        Usa il buffer (t, W) del thread di integrazione a 0,05 s con lo
        STESSO lock del thread: interpola linearmente la potenza ai bordi
        della finestra e somma i segmenti interni. Se vengono passate
        sottofinestre ``exclude_windows`` (es. chiamata LLM Judge), i segmenti
        che le intersecano vengono INTERPOLATI/TRONCATI al bordo dell'esclusione
        (integrazione reale sugli intervalli tenuti, nessuno scaling per
        frazione temporale). Ritorna None se il backend non e' attivo o il
        buffer non copre la finestra (il chiamante usa il fallback dichiarato).
        """
        if self.method != "power-integration":
            return None
        with self._pi_lock:
            buf = list(self._pi_samples)
        if len(buf) < 2 or buf[0][0] > t_start + 0.1 or buf[-1][0] < t_end - 0.1:
            return None

        def power_at(t: float) -> Optional[float]:
            # potenza interpolata linearmente all'istante t
            import bisect
            ts = [p[0] for p in buf]
            i = bisect.bisect_left(ts, t)
            if i <= 0:
                return buf[0][1] if abs(buf[0][0] - t) < 1.0 else None
            if i >= len(buf):
                return None
            t0, w0 = buf[i - 1]
            t1, w1 = buf[i]
            if t1 == t0:
                return w1
            return w0 + (w1 - w0) * (t - t0) / (t1 - t0)

        excl = sorted(exclude_windows or [], key=lambda w: w[0])

        def _in_excl(a: float, b: float) -> bool:
            return any(not (b <= x or a >= y) for x, y in excl)

        e = 0.0
        prev_t, prev_w = t_start, power_at(t_start)
        if prev_w is None:
            return None
        for (ct, cw) in buf:
            if ct <= t_start:
                continue
            if ct > t_end:
                break
            seg_a, seg_b = prev_t, ct
            if not _in_excl(seg_a, seg_b):
                e += ((prev_w + cw) / 2.0) * (seg_b - seg_a)
            else:
                # segmento parzialmente nell'esclusione: integra solo la
                # parte tenuta (tronca ai bordi delle finestre escluse)
                free = [(seg_a, seg_b)]
                for (xa, xb) in excl:
                    nf = []
                    for (fa, fb) in free:
                        if xb <= fa or xa >= fb:
                            nf.append((fa, fb))
                            continue
                        if xa > fa:
                            nf.append((fa, min(xa, fb)))
                        if xb < fb:
                            nf.append((max(xb, fa), fb))
                    free = nf
                for (fa, fb) in free:
                    if fb - fa > 1e-9:
                        wa = prev_w + (cw - prev_w) * (fa - seg_a) / max(ct - prev_t, 1e-9) \
                            if ct > prev_t else prev_w
                        wb = prev_w + (cw - prev_w) * (fb - seg_a) / max(ct - prev_t, 1e-9) \
                            if ct > prev_t else cw
                        e += ((wa + wb) / 2.0) * (fb - fa)
            prev_t, prev_w = ct, cw
        end_w = power_at(t_end)
        if end_w is not None and prev_t < t_end:
            if not _in_excl(prev_t, t_end):
                e += ((prev_w + end_w) / 2.0) * (t_end - prev_t)
            else:
                free = [(prev_t, t_end)]
                for (xa, xb) in excl:
                    nf = []
                    for (fa, fb) in free:
                        if xb <= fa or xa >= fb:
                            nf.append((fa, fb))
                            continue
                        if xa > fa:
                            nf.append((fa, min(xa, fb)))
                        if xb < fb:
                            nf.append((max(xb, fa), fb))
                    free = nf
                for (fa, fb) in free:
                    if fb - fa > 1e-9:
                        wa = prev_w + (end_w - prev_w) * (fa - prev_t) / max(t_end - prev_t, 1e-9)
                        wb = prev_w + (end_w - prev_w) * (fb - prev_t) / max(t_end - prev_t, 1e-9)
                        e += ((wa + wb) / 2.0) * (fb - fa)
        return round(max(e, 0.0), 6)

    # -- A3: sensore grafico integrato (solo informativo) -------------------
    def read_igpu_power_w(self) -> Optional[float]:
        """Potenza istantanea del sensore 'CPU Graphics'/'IA GPU' se esposto."""
        if self._lhm is None or not self._lhm_opened:
            return None
        try:
            for hw in self._lhm.Hardware:
                try:
                    hw.Update()
                except Exception:
                    pass
                if str(hw.Type) != "Cpu":
                    continue
                for sensor in list(hw.Sensors) + [
                    s for sub in (list(getattr(hw, "SubHardware", []) or []))
                    for s in sub.Sensors
                ]:
                    try:
                        n = str(sensor.Name)
                        if ("Graphics" in n or "GPU" in n.upper()) \
                                and str(sensor.SensorType) == "Power":
                            v = float(sensor.Value)
                            if v == v and v >= 0:
                                return v
                    except Exception:
                        continue
        except Exception as exc:
            self._lhm_last_error = f"read_igpu_power_w: {exc}"
        return None


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

    @property
    def pp1_read_reason(self) -> Optional[str]:
        """Ragione dichiarata dell'ultimo None su una lettura di dominio EMI.

        Lo slot riguarda le letture di dominio (PP1 e i domini non
        campionati); una lettura del package non lo tocca, perche' il
        profiler le esegue entrambe nella stessa finestra.
        """
        return getattr(self, "_pp1_read_reason", None)

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
          * "emi-counter"                 -> contatore package EMI cumulato
            [J] (Windows, ioctl sul record pWh; metodo principale dal 23/10);
          * "power-integration"           -> integrazione trapezoidale del
            sensore CPU Package [W] a 0.05 s (metodo ufficiale su i9-13900HK);
          * "librehardwaremonitor-energy" -> contatore Energy LHM [J];
          * "rapl"                        -> contatore RAPL Linux [J]
            (via /sys/class/powercap/intel-rapl/);
          * "energy-file"                 -> contatore dev/test non-Windows.
        ``busy_seconds_total`` e' ignorato (retro-compatibilita' di firma).
        """
        if self.method == "emi-counter":
            return self._emi.read_cumulative_energy_j() if self._emi else None
        if self.method == "power-integration":
            with self._pi_lock:
                return self._pi_energy_j
        if self.method in ("librehardwaremonitor-energy", "librehardwaremonitor"):
            return self._lhm_value()
        if self.method == "rapl":
            if self._rapl is not None:
                return self._rapl.read_cumulative_energy_j()
            return None
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
          * emi-counter -> contatore package EMI cumulato (pWh -> J);
          * power-integration -> energia gia' integrata a 0.05 s;
          * energy-counter LHM / file dev-test -> contatore cumulato;
          * rapl -> contatore RAPL Linux cumulato.
        Ritorna None se nessun backend reale e' disponibile: il chiamante
        deve dichiararlo (mai fallback TDP silenzioso).
        """
        try:
            if self.method == "emi-counter":
                return self._emi.read_cumulative_energy_j() if self._emi else None
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
            if self.method == "rapl":
                if self._rapl is not None:
                    return self._rapl.read_cumulative_energy_j()
                return None
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
          * mode="rapl-counter": delta del contatore RAPL Linux (via
            /sys/class/powercap/intel-rapl/);
          * mode="energy-counter": delta del contatore Joule cumulato (LHM
            Energy o file dev/test).
        Nessuna modalita' usa stime TDP: tutte sono misure reali.
        """
        duration_s = max(float(duration_s), 0.5)
        # 1) POWER-INTEGRATION: delta dell'energia INTEGRATA DAL THREAD
        #    dedicato (campioni CPU Package ogni 0.05 s, spec §4). Il polling
        #    inline dal thread GUI era la causa di falsi negativi "Value
        #    sempre None" su Windows: le chiamate .NET da thread non-STA si
        #    incrociano con quelle del thread PI. Ora qui si legge SOLO il
        #    contatore cumulato _pi_energy_j — nessuna chiamata .NET da
        #    questo contesto. Se il thread non e' attivo lo si avvia.
        if self.method == "power-integration":
            if self._pi_thread is None or not self._pi_thread.is_alive():
                self._start_power_integration()
            with self._pi_lock:
                e_start = self._pi_energy_j
                n_start = len(self._pi_samples)
            t0 = time.monotonic()
            time.sleep(duration_s)
            dt = max(time.monotonic() - t0, 1e-6)
            with self._pi_lock:
                e_end = self._pi_energy_j
                n_end = len(self._pi_samples)
            if n_end > n_start and e_end >= e_start:
                delta = e_end - e_start
                return (delta, dt, "power-integration")
            if n_end > n_start:
                # campioni presenti ma energia non integrata (primo punto?):
                # media delle potenze osservate nella finestra
                window = self._pi_samples[n_start:]
                avg_w = sum(w for _, w in window) / len(window)
                return (avg_w * dt, dt, "power-integration")
            self._last_read_error = (
                f"sensore '{self._pi_sensor_name}' agganciato ma senza campioni "
                "validi nella finestra (thread power-integration inattivo o "
                "Update()/driver non popolano il sensore): riavviare come "
                "amministratore ed eseguire 'py diagnostics.py'"
            )
            return None
        # 2) RAPL (Linux): delega al backend RAPL
        if self.method == "rapl" and self._rapl is not None:
            return self._rapl.read_idle_window_j(duration_s)
        # 3) contatore Joule reale (LHM Energy / file dev-test)
        e_start = self.read_power_j()
        err_after_counter = getattr(self, "_last_read_error", None)
        t0 = time.monotonic()
        if e_start is not None:
            time.sleep(duration_s)
            e_end = self.read_power_j()
            dt = max(time.monotonic() - t0, 1e-6)
            if e_end is not None and e_end >= e_start:
                _mode = ("emi-counter" if self.method == "emi-counter"
                         else "energy-counter")
                return (e_end - e_start, dt, _mode)
        # 4) nessun backend: propagazione diagnostica al chiamante
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
    # A3: potenza del sensore grafico integrato ('CPU Graphics'), informativo
    igpu_power_w: Optional[float] = None


def _free_subintervals(seg: tuple, excl: List[tuple]) -> List[tuple]:
    """Sottrae le sottofinestre escluse da ``seg`` -> lista di intervalli tenuti."""
    free = [seg]
    for (xa, xb) in excl:
        nxt: List[tuple] = []
        for (fa, fb) in free:
            if xb <= fa or xa >= fb:
                nxt.append((fa, fb))
                continue
            if xa > fa:
                nxt.append((fa, min(xa, fb)))
            if xb < fb:
                nxt.append((max(xb, fa), fb))
        free = nxt
    return [(a, b) for a, b in free if b - a > 1e-9]


@dataclass
class EnergySession:
    """Singleton di sessione: thread di campionamento + storico campioni."""

    interval_s: float = MONITOR_INTERVAL_S
    # callback opzionale di avanzamento (usato dalla GUI durante la
    # calibrazione idle per mostrare le ripetizioni in corso)
    on_progress: Optional[object] = None

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
        # Perche' l'ultima lettura del dominio grafico ha risposto None: la
        # nota finisce nel CSV, perche' un campo informativo assente senza
        # motivazione e' indistinguibile da un dominio che non esiste.
        self._igpu_none_reason: Optional[str] = None

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
        # A3: potenza iGPU campionata SOLO con backend LHM attivo (il sensore
        # 'CPU Graphics' non esiste altrove); mai un crash del sampler.
        igpu_w: Optional[float] = None
        if (self._source.method == "power-integration"
                and getattr(self._source, "_lhm_opened", False)):
            try:
                igpu_w = self._source.read_igpu_power_w()
            except Exception:  # noqa: BLE001 - CLR/pythonnet instabile
                igpu_w = None
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
            igpu_power_w=igpu_w,
        )
        with self._lock:
            self._samples.append(sample)
            # tetto difensivo alla memoria (~2 h a 0.5 s)
            if len(self._samples) > 20_000:
                del self._samples[:2_000]
        return sample

    def start(self) -> None:
        # NOTE: la sonda LHM pigra viene eseguita FUORI dal lock (puo'
        # richiedere minuti); open_computer() resta idempotente.
        if self._source._lazy_pending:
            if self.on_progress:
                self.on_progress(
                    "Inizializzazione LibreHardwareMonitor (primo avvio): "
                    "apertura Computer() in corso…"
                )
            self._source._activate_backend()
        with self._lock:
            if self._running:
                return
            # spec §6: apertura UNICA e protetta del Computer() LHM. Se
            # Open() fallisce, l'errore .NET viene registrato nelle note di
            # sessione (visibili in GUI/CSV) e la misurazione locale degrada
            # a 'unavailable': MAI un crash non gestito del processo.
            try:
                already_open = getattr(self._source, "_lhm_opened", False)
                self._source.open_computer()
                # Recupero post-probe-figlio: se il probe completo era
                # fallito ma Open() appena riuscita in-process, i sensori
                # vanno riclassificati — senza questo ramo il metodo
                # resterebbe 'unavailable' per sempre anche con sensori ok.
                if (not already_open and self._source._lhm is not None
                        and self._source.method == "unavailable"):
                    if self._source._lhm_value() is not None:
                        self._source.method = "librehardwaremonitor-energy"
                    elif self._source._select_power_sensor() is not None:
                        self._source.method = "power-integration"
                    if self._source.method != "unavailable":
                        self._source.notes.append(
                            "recupero riuscito: probe precedente fallito ma "
                            "apertura in-process OK (metodo: "
                            + self._source.method + ")"
                        )
            except Exception as exc:  # noqa: BLE001 - degradazione voluta
                self._source.notes.append(
                    f"Computer().Open() fallita ({type(exc).__name__}): "
                    f"{exc!s:.200} — misurazione locale CPU disabilitata"
                )
                self._source.method = "unavailable"
            # spec §6/§7: il thread di power-integration si avvia SOLO se
            # l'assembly e' realmente aperta; qui si riavvia solo il thread
            # se era stato fermato da close(), senza mai richiudere l'assembly.
            if (
                self._source.method == "power-integration"
                and getattr(self._source, "_lhm_opened", False)
            ):
                self._source._start_power_integration()
            # emi-counter: il buffer (t, cumulata) del contatore parte qui,
            # non all'import (stessa disciplina del thread PI).
            if self._source.method == "emi-counter":
                self._source._start_emi_sampling()
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
        try:
            src.stop_emi_sampling()
        except Exception:
            pass
        if getattr(src, "_emi", None) is not None:
            try:
                src._emi.close()
            except Exception:
                pass
            src._emi = None
        if getattr(src, "_lhm", None) is not None:
            try:
                # Close() solo se Open() era riuscito: chiamarla su un
                # Computer non aperto puo' sollevare NullReferenceException
                # .NET (pythonnet la propagherebbe come crash del processo).
                if src._lhm_opened:
                    src._lhm.Close()
            except Exception:
                pass
            src._lhm = None
            src._lhm_opened = False
            src._pi_selected = None
        self._gpu.shutdown()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def source_method(self) -> str:
        return self._source.method

    # ---- provenienza del contatore sulla finestra (contratto alt_lhm) -----
    def window_counter_provenance(self, t_start: float, t_end: float,
                                  domain: str = "pkg") -> dict:
        """Valori grezzi e cadenza REALE agli estremi della finestra.

        Non produce energia: produce cio' che rende l'energia revisionabile
        (contratto di ``alt_lhm`` §3): con quale valore del contatore sono
        stati letti i bordi, in quale unita', su quale dominio, con quale
        passo effettivo e con quale versione del percorso di lettura.

        * EMI: pWh, interpolati dal buffer a 0,05 s (``_emi_field_at``);
        * power-integration: nessun contatore (si integra una potenza),
          quindi i grezzi restano vuoti e la cadenza e' quella del buffer PI;
        * RAPL: microjoule cumulati (unwrapped) dai campioni di sessione.

        Ogni campo non ottenibile resta ``None``/vuoto: un'assenza muta e'
        ambigua, un numero inventato e' peggio.
        """
        src = self._source
        out = {
            "raw_start": None,
            "raw_end": None,
            "raw_unit": "",
            "domain": "",
            "sampling_interval_observed_s": None,
            "backend_version": src.version_label(),
        }
        if src.method == "emi-counter":
            with src._emi_lock:
                buf = list(src._emi_samples if domain == "pkg"
                           else src._emi_pp1_samples)
            if len(buf) >= 2:
                out["domain"] = "PKG" if domain == "pkg" else "PP1"
                out["sampling_interval_observed_s"] = _median_sampling_interval(
                    buf, t_start, t_end)
                if domain == "pkg":
                    out["raw_unit"] = "pWh"
                    out["raw_start"] = src._emi_field_at(buf, t_start, 2)
                    out["raw_end"] = src._emi_field_at(buf, t_end, 2)
        elif src.method == "power-integration":
            with src._pi_lock:
                buf = list(src._pi_samples)
            out["domain"] = "PKG"
            out["sampling_interval_observed_s"] = _median_sampling_interval(
                buf, t_start, t_end)
        elif src.method == "rapl":
            with self._lock:
                pts = [(s.t, s.package_energy_j) for s in self._samples
                       if t_start <= s.t <= t_end
                       and s.package_energy_j is not None]
            out["domain"] = "PKG"
            out["sampling_interval_observed_s"] = _median_sampling_interval(
                pts, t_start, t_end)
            if pts:
                out["raw_unit"] = "uJ (unwrapped)"
                out["raw_start"] = round(pts[0][1] * 1e6, 3)
                out["raw_end"] = round(pts[-1][1] * 1e6, 3)
        return out

    # ---- B1: energia della finestra letta ESATTA dal contatore -----------
    def package_energy_exact_between(self, t_start: float, t_end: float,
                                     exclude_windows: Optional[List[tuple]] = None
                                     ) -> Optional[float]:
        """Energia package sulla finestra [t_start, t_end], letta esattamente
        ai bordi (stesso lock del thread di integrazione a 0,05 s).

        * power-integration: integrale trapezoidale reale sul buffer (t,W),
          con truncation delle sottofinestre escluse (B2);
        * energy-counter (LHM Energy / file dev-test): delta del contatore
          cumulato read_power_j() agli estremi; le sottofinestre escluse
          vengono sottratte integrando i campioni package nella regione
          esclusa (i campioni ci sono: niente scaling per frazione temporale).
        Ritorna None se il backend non puo' esprimere una lettura esatta
        (il profiler degrada al fallback dichiarato sui campioni).
        """
        m = self._source.method
        if m == "power-integration":
            return self._source.pi_window_energy_j(t_start, t_end, exclude_windows)
        if m == "emi-counter":
            # bordi esatti letti dal buffer del cumulativo a 0,05 s: niente
            # trapezi, e' la differenza del contatore sui segmenti tenuti.
            e_buf = self._source.emi_window_energy_j(t_start, t_end, exclude_windows)
            if e_buf is not None:
                return e_buf
            # buffer insufficiente (finestra oltre la copertura): degrada al
            # ramo contatore qui sotto, che resta un percorso a campione
            # reale e dichiarato — mai un valore interpolato inventato.
        if m in ("emi-counter", "librehardwaremonitor-energy", "energy-file", "rapl"):
            # finestra trascorsa: fonte affidabile sono i campioni del
            # contatore cumulato ai bordi REALI della finestra (nessuna
            # interpolazione), con sottrazione delle regioni escluse.
            with self._lock:
                inside = [s for s in self._samples
                          if t_start <= s.t <= t_end and s.package_energy_j is not None]
            if len(inside) < 2:
                return None
            base = max(inside[-1].package_energy_j - inside[0].package_energy_j, 0.0)
            if exclude_windows:
                removed = 0.0
                for (xa, xb) in exclude_windows:
                    seg = [s for s in inside if xa <= s.t <= xb]
                    if len(seg) >= 2:
                        removed += max(seg[-1].package_energy_j
                                       - seg[0].package_energy_j, 0.0)
                base = max(base - removed, 0.0)
            return round(base, 6)
        return None

    # ---- A3: energia iGPU informativa dal sensore grafico LHM ------------
    def read_igpu_energy_j(self, t_start: float, t_end: float,
                           exclude_windows: Optional[List[tuple]] = None
                           ) -> Optional[float]:
        """Energia del dominio grafico INTEGRATO sulla finestra [J].

        Due percorsi reali, entrambi senza stima e senza termine sommato:

        * ``emi-counter``: delta del contatore PP1 del record EMI, letto ai
          BORDI della finestra dal buffer a 0,05 s (``emi_window_energy_j``
          con ``domain='pp1'``) e con le sottofinestre escluse sottratte alla
          fonte. Niente integrazione: PP1 e' gia' energia, ed e' lo stesso
          record da cui viene il package, quindi il campione e' lo stesso
          istante del PKG.
        * ``power-integration``: integrale TRAPEZOIDALE dei campioni
          ``igpu_power_w`` del sensore 'CPU Graphics' (bordi interpolati da
          ``samples_between``), con le sottofinestre ``exclude_windows`` (es.
          chiamata LLM Judge) rimosse: i segmenti che le intersecano vengono
          troncati ai bordi dell'esclusione e la potenza interpolata
          linearmente, quindi si integra solo la parte tenuta (nessuno
          scaling per frazione temporale).

        CAMPO INFORMATIVO: su Intel/AMD il package include gia' la grafica,
        quindi il valore NON viene mai sommato a local_energy_j. Ritorna None
        (N/A dichiarato, con la ragione in ``igpu_unavailable_reason``) se il
        dominio non e' esposto, se il suo registro e' fermo nella finestra,
        se il sensore LHM non c'e' o se la finestra ha meno di 2 campioni
        validi.
        """
        if self._source.method == "emi-counter":
            v = self._source.emi_window_energy_j(
                t_start, t_end, exclude_windows, domain="pp1")
            self._igpu_none_reason = None if v is not None else (
                self._source.pp1_read_reason)
            return v
        if self._source.method != "power-integration" or not self._source._lhm_opened:
            self._igpu_none_reason = (
                "metodo " + str(self._source.method) + ": nessun sensore "
                "'CPU Graphics' da integrare"
            )
            return None
        pts = [(s.t, s.igpu_power_w)
               for s in self.samples_between(t_start, t_end)
               if s.igpu_power_w is not None]
        if len(pts) < 2:
            self._igpu_none_reason = (
                f"meno di 2 campioni iGPU validi nella finestra ({len(pts)})"
            )
            return None
        excl = sorted(
            [(max(a, t_start), min(b, t_end)) for a, b in (exclude_windows or [])
             if b > t_start and a < t_end],
            key=lambda w: w[0],
        )
        e = 0.0
        for (t0, w0), (t1, w1) in zip(pts, pts[1:]):
            span = t1 - t0
            if span <= 0:
                continue
            for (fa, fb) in _free_subintervals((t0, t1), excl):
                wa = w0 + (w1 - w0) * (fa - t0) / span
                wb = w0 + (w1 - w0) * (fb - t0) / span
                e += ((wa + wb) / 2.0) * (fb - fa)
        return round(max(e, 0.0), 6)

    @property
    def source_notes(self) -> List[str]:
        return self._source.notes

    @property
    def igpu_unavailable_reason(self) -> Optional[str]:
        """Ragione dichiarata dell'ultimo ``igpu_energy_j = None`` (o None se
        l'ultima lettura ha prodotto un valore)."""
        return getattr(self, "_igpu_none_reason", None)

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
            igpu_power_w=num(a.igpu_power_w, b.igpu_power_w),
        )

    # ------------------------------------------------------------ calibrazione
    def calibrate_idle(self, seconds: Optional[float] = None) -> float:
        """Calibrazione idle empirica via backend energetico (spec §5).

        Procedura esatta richiesta:
          1. durata >= 30 s (default; sovrascrivibile solo verso l'alto);
          2. 3 ripetizioni della finestra a riposo (nessun carico generato);
          3. per ogni ripetizione: potenza media = delta energia / dt reale
             (power-integration a 0.05 s sul sensore 'CPU Package', contatore
             Energy cumulato, o contatore RAPL Linux);
          4. P_idle = MEDIANA delle potenze medie delle 3 ripetizioni [W].

        L'idle calibrato riflette esattamente il consumo a riposo della
        macchina corrente. La baseline ``idle_power_w`` viene sottratta dal
        profiler e NON e' mai attribuita al modello. Supportato su Windows
        (LHM) e Linux (RAPL). Se nessun backend reale e' disponibile,
        RuntimeError dichiarato: niente TDP.
        """
        import config as _cfg

        duration_s = float(seconds or _cfg.IDLE_CALIBRATION_SECONDS)
        # spec §5: almeno 30 secondi per finestra (override via env
        # CW_IDLE_WINDOW_S per collaudi rapidi; il floor di 30 s resta se
        # non impostato esplicitamente).
        try:
            import os as _os
            window_floor = float(_os.getenv("CW_IDLE_WINDOW_S", "30"))
        except (TypeError, ValueError):
            window_floor = 30.0
        duration_s = max(duration_s, window_floor)

        # Propaga il callback di avanzamento alla sorgente: i progressivi
        # dell'apertura LHM (probe pigro/watchdog) finiscono nel log GUI.
        self._source._progress_cb = self.on_progress
        was_running = self._running
        if not was_running:
            self.start()
        # guardia esplicita (anti crash .NET non intercettabili): se il
        # backend LHM NON e' attivo con un metodo reale, la calibrazione si
        # ferma PRIMA di toccare qualsiasi oggetto pythonnet.
        # Nota: su Linux con RAPL, il metodo e' gia' "rapl" e non serve recovery LHM.
        if (self._source.method not in ("power-integration", "librehardwaremonitor-energy", "rapl", "emi-counter")
                and self._source._lhm is not None
                and platform_system() == "Windows"):
            # LHM era gia' stata AGGANCIATA in questo processo (Computer()
            # creato) ma il metodo risulta non attivo: possibile probe
            # fallito al primo colpo. Si ritenta UNA sola volta la catena
            # completa apertura+selezione, sempre con eccezioni gestite.
            if self.on_progress:
                self.on_progress(
                    "Aggancio LHM in-process (Computer().Open(): puo' richiedere "
                    "fino a ~2 minuti su laptop con molti bus USB/HID)…"
                )
            try:
                self._source.open_computer()
                if self._source._lhm_value() is not None:
                    self._source.method = "librehardwaremonitor-energy"
                elif self._source._select_power_sensor() is not None:
                    self._source.method = "power-integration"
                    self._source._start_power_integration()
                if self._source.method != "unavailable":
                    self._source.notes.append(
                        "recupero LHM: retry post-probe riuscito "
                        f"(metodo: {self._source.method})"
                    )
                    if self.on_progress:
                        self.on_progress(
                            f"Aggancio LHM in-process RIUSCITO: metodo attivo "
                            f"'{self._source.method}'"
                        )
            except BaseException as exc:  # noqa: BLE001
                self._source.notes.append(
                    f"retry LHM aggiuntivo fallito ({type(exc).__name__})"
                )
        if self._source.method not in ("power-integration", "librehardwaremonitor-energy", "rapl", "emi-counter"):
            # Recupero mirato: diagnostics.py ha GIA' dimostrato che, nel
            # processo principale elevato, Computer().Open() e la scansione
            # sensori funzionano senza crash pythonnet. Un eventuale falli-
            # mento del probe nel FIGLIO (rc=0xE0434352) e' quasi sempre un
            # problema del contesto figlio (console/env/caricamento assembly
            # in -c), non dell'aggancio reale. Qui si ritenta l'apertura IN
            # PROCESS una sola volta, protetta da try/except; se anche il
            # retry produce un'eccezione .NET gestibile, si degrada con la
            # nota originale (niente tentativi multipli anti-crash).
            recovered = False
            if platform_system() == "Windows":
                try:
                    if self.on_progress:
                        self.on_progress(
                            "Recupero LHM in-process: tentativo diretto di "
                            "apertura/lettura sensori (il probe isolato puo' "
                            "fallire per limiti del contesto figlio)…")
                    self._source.open_computer()
                    if self._source._lhm_value() is not None:
                        self._source.method = "librehardwaremonitor-energy"
                        recovered = True
                    elif self._source._select_power_sensor() is not None:
                        self._source.method = "power-integration"
                        self._source._start_power_integration()
                        recovered = True
                except BaseException as exc:  # noqa: BLE001
                    self._source.notes.append(
                        f"retry LHM in-process fallito ({type(exc).__name__})"
                    )
                if recovered:
                    self._source.notes.append(
                        "recupero riuscito: probe precedente fallito ma "
                        "apertura in-process OK (confermata da diagnostics.py "
                        "sul machine)"
                    )
                    if self.on_progress:
                        self.on_progress(
                            f"Recupero RIUSCITO: metodo attivo "
                            f"'{self._source.method}'"
                        )
        if self._source.method not in ("power-integration", "librehardwaremonitor-energy", "rapl", "emi-counter"):
            cause = "; ".join(self._source.notes[-3:]) or f"metodo='{self._source.method}'"
            raise RuntimeError(
                "calibrazione idle fallita: nessun contatore di energia/potenza "
                "package disponibile. Causa: " + cause +
                ". Su Windows: esegui 'py diagnostics.py' (clr/pythonnet/DLL/UAC/sensori Power). "
                "Su Linux: verifica che /sys/class/powercap/intel-rapl/ esista e sia leggibile "
                "(richiede root o gruppo 'power')."
            )
        try:
            # breve stabilizzazione prima della misura
            time.sleep(1.0)
            means: List[float] = []
            mode_used = None
            if self.on_progress:
                self.on_progress(
                    f"Finestra idle: {duration_s:.0f} s x 3 ripetizioni "
                    f"(totale stimato ~{duration_s * 3 + 2:.0f} s). "
                    "NON generare carico…"
                )
            for rep in range(3):
                if self.on_progress:
                    self.on_progress(
                        f"Calibrazione idle: ripetizione {rep + 1}/3 in corso "
                        f"({duration_s:.0f} s)… tieni il PC a riposo"
                    )
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
                if self.on_progress:
                    self.on_progress(
                        f"Ripetizione {rep + 1}/3 completata: "
                        f"P_media = {p_rep:.2f} W su finestra di {dt:.1f} s"
                    )
            power_w = sorted(means)[len(means) // 2]   # mediana di 3 misure
            self._idle_mode = mode_used
            self._idle_reps = means
            self._idle_samples_count = self._source.pi_stats().get("samples", 0) \
                if self._source.method == "power-integration" else len(means)
        finally:
            self._source._progress_cb = None
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

    # ---- A2: attribuzione per processo (opzionale, dichiarata) ------------
    def process_energy_j(self, t_start: float, t_end: float,
                         pids: Optional[List[int]] = None) -> Optional[float]:
        """Energia GPU attribuibile ai processi indicati (es. albero Ollama).

        Usa nvmlDeviceGetProcessUtilization [ms/GPU per PID] nella finestra e
        lo converte in frazione del tempo di finestra; la quota si applica
        all'energia board attiva (whole-device minus idle), che e' l'unica
        grandezza energetica misurata da NVML. Ritorna None (N/A dichiarato)
        se NVML non espone il contatore o i PID non compaiono — mai un valore
        inventato. Campo INFORMATIVO: non sostituisce l'attribuzione
        whole-device usata in gpu_energy_attributed_j.
        """
        if not self.available or not pids:
            return None
        try:
            import pynvml

            # timestamp NVML in microsecondi: finestra degli ultimi 10 s
            samples = pynvml.nvmlDeviceGetProcessUtilization(
                self.handle, int(time.time_ns() // 1000) - 10_000_000)
            span_ms = max((t_end - t_start) * 1000.0, 1e-6)
            busy_ms = 0.0
            for s in samples or []:
                pid = getattr(s, "pid", None)
                if pid in pids:
                    u = getattr(s, "utilization", None) or {}
                    sm = u.get("gpu", 0) or 0
                    st = getattr(s, "time_range", None)
                    dur = (st.end - st.start) / 1e6 if st else 0.0
                    busy_ms += dur * float(sm) / 100.0
            if busy_ms <= 0:
                return None
            frac = min(busy_ms / span_ms, 1.0)
            board_active = getattr(self, "_last_window_board_active_j", None)
            if board_active is None:
                return None
            return round(board_active * frac, 6)
        except Exception:
            return None


# Singleton di sessione (sezione 16: ``from .energy_session import SESSION``)
SESSION = EnergySession()
