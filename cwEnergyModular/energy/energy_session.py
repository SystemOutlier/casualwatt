# -*- coding: utf-8 -*-
"""
energy/energy_session.py — Sessione CasualWatt: campionamento continuo.

Questa modulo espone il singleton ``SESSION`` usato da tutti gli altri moduli
energetici. Un thread daemon campiona a intervallo fisso:

* energia del package CPU: su Windows il contatore cumulativo EMI
  (``energy.emi_backend``, senza token elevato); su Linux i contatori RAPL
  (``energy.rapl_backend``). Windows senza device EMI resta ``unavailable``:
  LibreHardwareMonitor e' uscita dall'implementazione il 27/10 (D18, metodo
  provato e superato), e il suo sostituto MSR e' ancora [P];
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
from datetime import datetime, timezone
from typing import Dict, List, Optional

import psutil

try:  # config e' nella cartella padre: import assoluto protetto
    from config import (
        MONITOR_INTERVAL_S, OLLAMA_ROOT_NAMES, OLLAMA_RUNNER_NAMES,
    )
except Exception:  # pragma: no cover - contesto di test standalone
    MONITOR_INTERVAL_S = 0.5
    OLLAMA_ROOT_NAMES = ("ollama.exe", "ollama")
    OLLAMA_RUNNER_NAMES = (
        "llama-server.exe", "llama-server",
        "ollama_llama_server.exe", "ollama_llama_server",
    )

from .worker_tree import (
    WorkerProc,
    build_worker_tree,
    read_process_table,
    read_worker_cpu_times,
    stray_runners,
    worker_cpu_delta,
)


#: Metodi che possono esprimere un NUMERO di energia in una riga. Sono i
#: metodi che leggono un contatore o integrano una potenza reale; tutto il
#: resto ("unavailable", "librehardwaremonitor" senza sensori Energy/Power)
#: deve produrre N/A nel CSV, non uno zero. La lista sta QUI, accanto a chi quei
#: valori li produce, perche' il 24/10 ne esisteva una copia in
#: benchmark_unified.py:402 rimasta ferma quando il backend RAPL e' stato
#: aggiunto: su Linux il campo judge_energy_j sarebbe stato N/A anche con un
#: contatore funzionante (test in tests/test_metodo_ammissibile.py).
#:
#: D18 (27/10): da questa macchina il sorgente non produce piu'
#: "power-integration" ne' "librehardwaremonitor-energy" — LHM e' fuori
#: dall'implementazione. I due token restano nell'elenco perche' NON descrivono
#: cosa sa fare il codice oggi ma QUALI righe portano un numero: i CSV
#: archiviati in experiment_results/ (v1-v3, four-way, A-B-A) sono stati
#: misurati con quei canali reali e rileggerli come N/A falserebbe l'archivio.
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

    #: Cadenza del sampler del cumulativo EMI. Vale 0,05 s perche' il registro
    #: aggiorna l'energia a grana fine (probe: nessuna quantizzazione sopra i
    #: 10 ms), quindi il bordo di una finestra breve resta collocabile entro
    #: un tick. Non e' la cadenza della sessione: quella e' ``interval_s``.
    EMI_SAMPLE_INTERVAL_S = 0.05

    def __init__(self) -> None:
        self.method = "unavailable"
        self._emi = None   # backend Windows EMI (energy.emi_backend.EMICounterBackend)
        self._rapl = None  # backend Linux RAPL (rapl_backend.RAPLBackend)
        self._power_base_j: float = 0.0   # base contatore potenza per read_power_j
        self._notes: List[str] = []
        # ---- emi-counter (metodo principale Windows dal 23/10) -------------
        # Buffer (t_monotono, cum_j) del contatore cumulativo, campionato a
        # 0,05 s: serve per leggere la finestra AI BORDI ESATTI (per query
        # brevi il delta dei campioni di sessione a ~0,5 s sarebbe troppo
        # rozzo).
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
            "Local CPU energy measurement is available on Windows (EMI energy "
            "meter) and Linux (RAPL via /sys/class/powercap/)."
        )

        if self._try_power_counter():
            # Contatore Joule ESPOSTO DALL'UTENTE (CW_ENERGY_FILE).
            pass
        elif platform_system() == "Windows" and self._try_emi():
            # 23/10: il METODO PRINCIPALE su Windows e' il contatore EMI
            # (cumulativo, ctypes, senza token elevato).
            pass
        elif platform_system() == "Linux":
            # Backend Linux: contatori RAPL via /sys/class/powercap/
            self._activate_rapl_backend()
        else:
            # Windows senza device EMI, oppure piattaforma non-Windows/
            # non-Linux (es. macOS): misurazione locale NON supportata. LHM e'
            # fuori dall'implementazione (D18, 27/10) e il sostituto MSR e'
            # ancora [P], quindi qui la catena finisce — dichiarata, non muta.
            self.method = "unavailable"
            self._notes.append(self._local_disabled_msg)

    def _try_emi(self) -> bool:
        """Aggancia il contatore EMI; True solo se la PRIMA lettura riesce.

        Nessun fallback silenzioso: se il device non c'e' o l'IOCTL fallisce,
        ritorna False e il chiamante dichiara `unavailable`.
        """
        try:
            from energy.emi_backend import EMICounterBackend, METHOD_LABEL

            backend = EMICounterBackend()
            if backend.available:
                self._emi = backend
                self.method = METHOD_LABEL
                # Il sampler NON parte qui: l'import del modulo non deve mai
                # avviare thread di misura (parte in EnergySession.start()).
                self._notes.extend(backend.notes)
                self._notes.append(
                    "metodo principale 'emi-counter': contatore package "
                    "cumulativo (pWh) letto via IOCTL"
                )
                return True
            self._notes.extend(backend.notes)
            self._notes.append(
                "EMI non disponibile: nessun altro canale di misura locale "
                "su Windows (LHM e' fuori dall'implementazione, D18)"
            )
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            self._notes.append(f"EMI non disponibile ({type(exc).__name__})")
        return False

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

    # -- emi-counter: sampler del cumulativo e finestra esatta --------------
    def _emi_loop(self) -> None:
        """Campiona il contatore EMI cumulativo ogni 0,05 s.

        NON integra nulla: il contatore e' gia' energia. Il buffer (t, J)
        serve solo a poter collocare i bordi di una finestra trascorsa fra
        due campioni (lettura ai bordi per interpolazione del cumulativo).

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
                        # misura revisionabile (alt_lhm §3). I domini sono
                        # quelli che il metadato del device dichiara: un
                        # device senza PP1 non deve far cadere il PKG.
                        pkg = domains.get("pkg")
                        if pkg is not None:
                            cum = pkg[0]
                            cum_pwh = pkg[2]
                        d_pp1 = domains.get("pp1")
                        if d_pp1 is not None:
                            pp1 = (d_pp1[0], d_pp1[1])
                    else:
                        cum = self._emi.read_cumulative_energy_j()
            except Exception:
                cum = None
                pp1 = None
            self._accept_emi_sample(t, cum, cum_pwh, pp1)
            self._emi_stop.wait(self.EMI_SAMPLE_INTERVAL_S)

    def _accept_emi_sample(self, t: float, cum: Optional[float],
                           cum_pwh: Optional[float] = None,
                           pp1: Optional[tuple] = None) -> None:
        """Accoda un tick del contatore, gestendo il RESET del cumulativo.

        Se il valore decresce (driver ricaricato, sospensione/ripresa,
        riapertura dell'handle) il buffer viene svuotato: interpolare fra il
        valore pre-reset e quello post-reset produrrebbe un delta negativo o
        una rampa falsa. Il campione post-reset apre un nuovo buffer.

        Estratto dal loop per essere verificabile senza thread: il caso
        reset era l'unico ramo del backend EMI senza test (alt_lhm §6).
        """
        if cum is not None:
            with self._emi_lock:
                if self._emi_samples and cum < self._emi_samples[-1][1]:
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
        dichiarare con certezza. Per EMI e' il contratto del reader e
        l'IOCTL, per RAPL la release del kernel.
        """
        if self.method == "emi-counter":
            from energy import emi_backend
            return emi_backend.BACKEND_VERSION
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
        print(f"[CasualWatt][energia] {msg}", file=sys.stderr, flush=True)

    # -- interfaccia comune --------------------------------------------------
    def read_package_j(self, busy_seconds_total: float) -> Optional[float]:
        """Energia package CPU CUMULATA da inizio sessione [J].

        Metodi reali supportati (nessuna stima TDP, nessun moltiplicatore
        arbitrario):
          * "emi-counter"                 -> contatore package EMI cumulato
            [J] (Windows, ioctl sul record pWh);
          * "rapl"                        -> contatore RAPL Linux [J]
            (via /sys/class/powercap/intel-rapl/);
          * "energy-file"                 -> contatore dev/test non-Windows.
        ``busy_seconds_total`` e' ignorato (retro-compatibilita' di firma).
        """
        if self.method == "emi-counter":
            return self._emi.read_cumulative_energy_j() if self._emi else None
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
          * energy-file -> contatore cumulato dev/test;
          * rapl -> contatore RAPL Linux cumulato.
        Ritorna None se nessun backend reale e' disponibile: il chiamante
        deve dichiararlo (mai fallback TDP silenzioso).
        """
        try:
            if self.method == "emi-counter":
                return self._emi.read_cumulative_energy_j() if self._emi else None
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
          * mode="rapl-counter": delta del contatore RAPL Linux (via
            /sys/class/powercap/intel-rapl/);
          * mode="emi-counter" / "energy-counter": delta del contatore Joule
            cumulato (EMI su Windows, file dev/test).
        Nessuna modalita' usa stime TDP: tutte sono misure reali.
        """
        duration_s = max(float(duration_s), 0.5)
        # 1) RAPL (Linux): delega al backend RAPL
        if self.method == "rapl" and self._rapl is not None:
            return self._rapl.read_idle_window_j(duration_s)
        # 2) contatore Joule reale (EMI / file dev-test)
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
        """Secondi CPU busy aggregati di sistema (non-idle), da UNA lettura.

        Le due letture precedenti (``cpu_times()`` per l'idle e
        ``cpu_times(percpu=True)`` per il totale) prendevano numeratore e
        denominatore del denominatore in due istanti diversi: fra le due
        chiamate il sistema poteva aver accumulato tempo, e il busy risultava
        sottostimato di quella quantita'. Qui totale e idle vengono dalla
        STESSA chiamata per-core, quindi ``busy = totale - idle`` e' una
        differenza fra grandezze dello stesso istante. La media di
        ``cpu_times()`` non serve: i campi sono gia' cumulati per core.
        """
        try:
            per_core = psutil.cpu_times(percpu=True)
            total = 0.0
            idle = 0.0
            for c in per_core:
                total += sum(v for v in c if isinstance(v, (int, float)))
                idle += float(getattr(c, "idle", 0.0) or 0.0)
            return max(total - idle, 0.0)
        except Exception:
            return 0.0

    @staticmethod
    def _nic_bytes() -> int:
        try:
            counters = psutil.net_io_counters()
            return int(counters.bytes_sent + counters.bytes_recv)
        except Exception:
            return 0

    @classmethod
    def find_worker_tree(cls) -> List[WorkerProc]:
        """Albero del motore locale, ricostruito a ogni richiesta.

        Radici per nome (``OLLAMA_ROOT_NAMES``) + discendenti ricorsivi,
        qualunque sia il loro nome: il runner del modello
        (``llama-server``, ``ollama_llama_server`` o lo stesso ``ollama.exe``
        con argomento ``runner``) e' incluso perche' figlio, non perche'
        compare in una lista. L'identita' e' ``(pid, create_time)``.
        """
        table = read_process_table()
        return build_worker_tree(table, OLLAMA_ROOT_NAMES, OLLAMA_RUNNER_NAMES)

    @classmethod
    def find_stray_runner_procs(
        cls, tree: Optional[List[WorkerProc]] = None,
    ) -> List[WorkerProc]:
        """Runner del modello che NON discendono dall'albero misurato.

        Se ne esiste uno, il run sta misurando un motore che non attribuisce:
        il chiamante lo deve scrivere nel log, non ignorarlo.
        """
        table = read_process_table()
        current = tree if tree is not None else build_worker_tree(
            table, OLLAMA_ROOT_NAMES, OLLAMA_RUNNER_NAMES)
        return stray_runners(table, current, OLLAMA_RUNNER_NAMES)

    @classmethod
    def find_ollama_procs(cls) -> List[int]:
        """PID dell'albero del motore (compatibilita': solo i PID, ordinati)."""
        return [w.pid for w in cls.find_worker_tree()]

    # ------------------------------------------------- bordo di misura (P5)
    @staticmethod
    def _wall_utc(t_wall: float) -> str:
        """Istante di parete in UTC ISO con i millisecondi.

        I bordi servono a ricostruire la finestra anche dopo il run: con i
        soli secondi due bordi consecutivi di un blocco rapido sarebbero
        indistinguibili.
        """
        return datetime.fromtimestamp(
            float(t_wall), tz=timezone.utc).isoformat(timespec="milliseconds")

    def read_counter_edge(self) -> Dict[str, object]:
        """Una IOCTL sul contatore, con l'istante e il timestamp del record.

        Ritorna ``counter`` (None se il canale non e' aperto o la lettura
        fallisce) e, in ogni caso, ``counter_error`` con la ragione: un bordo
        senza contatore e' un fatto dichiarato, non un bordo "sincrono"
        presunto. ``t_mono`` e' preso PRIMA dell'IOCTL, come fa il sampler
        (``_emi_loop``): cosi' l'istante e' confrontabile con il buffer.
        """
        t_wall = time.time()
        t_mono = time.monotonic()
        counter = None
        err = ""
        try:
            backend = getattr(self._source, "_emi", None)
            if backend is None:
                err = "backend EMI non aperto"
            else:
                domains = (backend.read_domains()
                           if hasattr(backend, "read_domains") else None)
                if domains is None:
                    err = "read_domains() -> None"
                else:
                    pkg = domains["pkg"]
                    pp1 = domains.get("pp1")
                    counter = {
                        "pkg_j": float(pkg[0]),
                        "pkg_pwh": pkg[2],
                        "ts_100ns": pkg[1],
                        "pp1_j": (float(pp1[0]) if pp1 is not None else None),
                    }
        except Exception as exc:  # noqa: BLE001 - il bordo degrada, non crasha
            err = f"{type(exc).__name__}: {exc}"
        return {
            "counter": counter,
            "counter_error": err,
            "t_wall": t_wall,
            "t_mono": t_mono,
            "t_wall_utc": self._wall_utc(t_wall),
        }

    def read_measurement_edge(self, include_counter: bool = True) -> Dict[str, object]:
        """Contatore, albero, cpu_times e busy nello stesso bordo.

        Ordine: contatore per primo (la finestra energetica e' la sua), poi le
        letture CPU. Lo scarto fra i due e' ``edge_spread_s``; ``t_cpu_mid``
        e' il centro del tratto CPU, non un istante magico. Il contatore e'
        opzionale solo per i chiamanti storici che leggono il solo lato CPU
        (``read_cpu_edge``): quei bordi dichiarano ``counter_error``.
        """
        t_before = time.monotonic()
        if include_counter:
            cnt = self.read_counter_edge()
        else:
            t_wall = time.time()
            cnt = {
                "counter": None,
                "counter_error": "non richiesto (include_counter=False)",
                "t_wall": t_wall,
                "t_mono": t_before,
                "t_wall_utc": self._wall_utc(t_wall),
            }
        t_cpu_before = time.monotonic()
        tree = self.find_worker_tree()
        worker = read_worker_cpu_times(tree)
        busy = self._system_busy_seconds()
        t_after = time.monotonic()
        return {
            "tree": tree,
            "worker": worker,
            "busy": busy,
            "counter": cnt["counter"],
            "counter_error": cnt["counter_error"],
            "t_wall": cnt["t_wall"],
            "t_wall_utc": cnt["t_wall_utc"],
            "t_counter_mono": cnt["t_mono"],
            "t_before": t_before,
            "t_cpu_mid": (t_cpu_before + t_after) / 2.0,
            "t_after": t_after,
            "edge_spread_s": t_after - t_before,
        }

    def read_cpu_edge(self) -> Dict[str, object]:
        """Alias storico del bordo CPU: le tre chiavi di sempre.

        Non legge il contatore: il percorso di produzione attuale
        (``benchmark_unified``, ``experiment_additivity``) non paga l'IOCTL in
        piu' e continua a leggere numeratore e denominatore nello stesso
        istante. Chi vuole anche l'energia dal bordo usa
        ``read_measurement_edge``.
        """
        edge = self.read_measurement_edge(include_counter=False)
        return {
            "tree": edge["tree"],
            "worker": edge["worker"],
            "busy": edge["busy"],
        }

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
        interval = self.interval_s
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
            # emi-counter: il buffer (t, cumulata) del contatore parte qui,
            # non all'import (l'import non deve avviare thread di misura).
            if self._source.method == "emi-counter":
                self._source._start_emi_sampling()
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
        """Ferma il sampler di sessione. NON chiude il contatore EMI ne' NVML
        (spec §6): restano aperti per calibrazioni/inferenze successive; lo
        shutdown definitivo avviene una sola volta in close()."""
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

        - ferma e joina il sampler EMI (<= 5 s);
        - chiude il device EMI UNA sola volta;
        - nvmlShutdown() UNA sola volta.
        Idempotente: chiamata multipla non genera errori.
        """
        self.stop()
        src = self._source
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
        ai bordi (stesso buffer a 0,05 s del contatore EMI).

        * EMI: differenza del contatore cumulativo sui segmenti tenuti
          (niente trapezi; le sottofinestre escluse sono rimosse alla fonte);
        * energy-counter (file dev-test): delta del contatore cumulato
          read_power_j() agli estremi; le sottofinestre escluse vengono
          sottratte integrando i campioni package nella regione esclusa
          (i campioni ci sono: niente scaling per frazione temporale).
        Ritorna None se il backend non puo' esprimere una lettura esatta
        (il profiler degrada al fallback dichiarato sui campioni).
        """
        m = self._source.method
        if m == "emi-counter":
            # bordi esatti letti dal buffer del cumulativo a 0,05 s: niente
            # trapezi, e' la differenza del contatore sui segmenti tenuti.
            e_buf = self._source.emi_window_energy_j(t_start, t_end, exclude_windows)
            if e_buf is not None:
                return e_buf
            # buffer insufficiente (finestra oltre la copertura): degrada al
            # ramo contatore qui sotto, che resta un percorso a campione
            # reale e dichiarato — mai un valore interpolato inventato.
        if m in ("emi-counter", "energy-file", "rapl"):
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

    # ---- A3: energia iGPU informativa dal dominio PP1 del record EMI ------
    def read_igpu_energy_j(self, t_start: float, t_end: float,
                           exclude_windows: Optional[List[tuple]] = None
                           ) -> Optional[float]:
        """Energia del dominio grafico INTEGRATO sulla finestra [J].

        Un solo percorso reale, senza stima e senza termine sommato:
        delta del contatore PP1 del record EMI, letto ai BORDI della finestra
        dal buffer a 0,05 s (``emi_window_energy_j`` con ``domain='pp1'``) e
        con le sottofinestre escluse sottratte alla fonte. Niente
        integrazione: PP1 e' gia' energia, ed e' lo stesso record da cui
        viene il package, quindi il campione e' lo stesso istante del PKG.

        CAMPO INFORMATIVO: su Intel/AMD il package include gia' la grafica,
        quindi il valore NON viene mai sommato a local_energy_j. Ritorna None
        (N/A dichiarato, con la ragione in ``igpu_unavailable_reason``) se il
        dominio non e' esposto, se il suo registro e' fermo nella finestra o
        se il canale attivo non e' EMI.
        """
        if self._source.method == "emi-counter":
            v = self._source.emi_window_energy_j(
                t_start, t_end, exclude_windows, domain="pp1")
            self._igpu_none_reason = None if v is not None else (
                self._source.pp1_read_reason)
            return v
        self._igpu_none_reason = (
            "metodo " + str(self._source.method) + ": il dominio PP1 esiste "
            "solo nel record EMI"
        )
        return None

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
        )

    # ------------------------------------------------------------ calibrazione
    def settle_idle(self, window_s: float = 10.0, tolerance_w: float = 0.5,
                    timeout_s: float = 120.0, step_s: float = 1.0) -> Optional[float]:
        """Attende la stazionarieta' della potenza e ritorna i secondi attesi.

        Criterio di P1.5: due medie consecutive su finestre di ``window_s``
        differiscono meno di ``tolerance_w``. La potenza di ogni finestra e'
        energia esatta sulla finestra divisa per la durata: la stessa
        grandezza che usano la calibrazione e il profilo, non una media dei
        campioni. Il criterio e' la stazionarieta', non l'uguaglianza con
        ``P_pre``: il post deve poter mostrare il drift.

        Tetto ``timeout_s``. Al tetto ritorna ``None``: il chiamante lo
        dichiara (``settle_pre_s`` vuoto), non inventa un tempo di
        stabilizzazione che non ha osservato.

        La prima finestra puo' non essere leggibile (buffer appena avviato):
        in quel caso si aspetta, senza contare un ``prev`` inesistente.
        """
        t0 = time.monotonic()
        prev: Optional[float] = None
        while True:
            now = time.monotonic()
            elapsed = now - t0
            e_window = self.package_energy_exact_between(now - window_s, now)
            current = (float(e_window) / window_s
                       if e_window is not None and window_s > 0 else None)
            if (prev is not None and current is not None
                    and abs(current - prev) < tolerance_w):
                return round(elapsed, 3)
            prev = current
            if elapsed >= timeout_s:
                return None
            time.sleep(max(min(step_s, timeout_s - elapsed), 0.0))

    def calibrate_idle(self, seconds: Optional[float] = None) -> float:
        """Calibrazione idle empirica via backend energetico (spec §5).

        Procedura esatta richiesta:
          1. durata >= 30 s (default; sovrascrivibile solo verso l'alto);
          2. 3 ripetizioni della finestra a riposo (nessun carico generato);
          3. per ogni ripetizione: potenza media = delta energia / dt reale
             (contatore EMI cumulativo su Windows, contatore RAPL su Linux);
          4. P_idle = MEDIANA delle potenze medie delle 3 ripetizioni [W].

        L'idle calibrato riflette esattamente il consumo a riposo della
        macchina corrente. La baseline ``idle_power_w`` viene sottratta dal
        profiler e NON e' mai attribuita al modello. Supportato su Windows
        (EMI) e Linux (RAPL). Se nessun backend reale e' disponibile,
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

        was_running = self._running
        if not was_running:
            self.start()
        if self._source.method not in ("rapl", "emi-counter"):
            cause = "; ".join(self._source.notes[-3:]) or f"metodo='{self._source.method}'"
            raise RuntimeError(
                "calibrazione idle fallita: nessun contatore di energia/potenza "
                "package disponibile. Causa: " + cause +
                ". Su Windows: esegui 'py diagnostics.py' (device EMI). "
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
                        "energia package leggibile. "
                        f"Causa ripetizione {rep + 1}/3: {cause}. "
                        "Esegui 'py diagnostics.py' per il report completo "
                        "(device EMI)."
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
            self._idle_samples_count = len(means)
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
