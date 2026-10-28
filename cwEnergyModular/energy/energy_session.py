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
* potenza e contatore di energia della GPU: NVML se c'e' una NVIDIA, altrimenti
  AMD SMI (fallback dichiarato, mai in parallelo).

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
MEASURED_METHODS = ("emi-counter", "pawnio-counter", "power-integration",
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
        self._pawnio = None  # fallback MSR Windows (energy.pawnio_backend)
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
            "meter or the PawnIO MSR counter) and Linux (RAPL via "
            "/sys/class/powercap/)."
        )

        if self._try_power_counter():
            # Contatore Joule ESPOSTO DALL'UTENTE (CW_ENERGY_FILE).
            pass
        elif platform_system() == "Windows" and self._try_emi():
            # 23/10: il METODO PRINCIPALE su Windows e' il contatore EMI
            # (cumulativo, ctypes, senza token elevato).
            pass
        elif platform_system() == "Windows" and self._try_pawnio():
            # 28/10: fallback MSR dichiarato, lo stesso registro di EMI letto
            # dal driver PawnIO (token distinto: pawnio-counter).
            pass
        elif platform_system() == "Linux":
            # Backend Linux: contatori RAPL via /sys/class/powercap/
            self._activate_rapl_backend()
        else:
            # Windows senza device EMI ne' PawnIO utilizzabile, oppure
            # piattaforma non-Windows/non-Linux (es. macOS): misurazione
            # locale NON supportata. LHM e' fuori dall'implementazione (D18):
            # la catena finisce qui, dichiarata e con la ragione dei backend.
            self.method = "unavailable"
            self._notes.append(self._local_disabled_msg)
            if platform_system() == "Windows":
                self._notes.append(
                    "catena Windows esaurita: EMI non disponibile e il "
                    "contatore MSR via PawnIO non utilizzabile"
                )

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
                "EMI non disponibile: si prova il contatore MSR via PawnIO"
            )
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            self._notes.append(f"EMI non disponibile ({type(exc).__name__})")
        return False

    def _try_pawnio(self) -> bool:
        """Aggancia il contatore MSR via PawnIO; False se la sonda lo esclude.

        Stesso registro di EMI (``MSR_PKG_ENERGY_STATUS``) letto dal driver
        PawnIO: il token e' ``pawnio-counter`` e non si somma mai a EMI,
        perche' i due leggono lo stesso contatore. La sonda del backend
        verifica vendor, servizio, HVCI e firma del driver, hash dei moduli:
        ogni rifiuto ha una ragione, e qui non si aggira.
        """
        try:
            from energy.pawnio_backend import PawnIOMSRBackend, METHOD_LABEL

            backend = PawnIOMSRBackend()
            self._notes.extend(backend.notes)
            if not backend.available:
                self._notes.append(
                    f"PawnIO non disponibile: {backend.reason}"
                )
                return False
            self._pawnio = backend
            self.method = METHOD_LABEL
            # come per EMI il sampler non parte qui: parte in start()
            self._notes.append(
                "fallback 'pawnio-counter': contatore MSR del package letto "
                "dal driver PawnIO (non si somma a EMI: stesso registro)"
            )
            return True
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            self._notes.append(
                f"PawnIO non disponibile ({type(exc).__name__}: {exc})")
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
    def _counter_backend(self):
        """Backend del contatore cumulativo attivo (EMI, oppure PawnIO).

        Il sampler e' UNO: cambia la sorgente, non il meccanismo. Mai due
        backend insieme — leggerebbero lo stesso registro e il numero
        risulterebbe doppio.
        """
        return self._emi if self._emi is not None else self._pawnio

    def _emi_loop(self) -> None:
        """Campiona il contatore cumulativo ogni 0,05 s.

        NON integra nulla: il contatore e' gia' energia. Il buffer (t, J)
        serve solo a poter collocare i bordi di una finestra trascorsa fra
        due campioni (lettura ai bordi per interpolazione del cumulativo).

        UNA sola IOCTL per tick alimenta sia il PKG sia il PP1: leggere i
        due domini con due chiamate avrebbe significato due record diversi
        nella stessa riga di CSV, e il delta PP1 non sarebbe piu' sullo
        stesso istante del delta PKG. Il backend PawnIO non ha domini (un
        solo MSR): il tick porta il cumulativo e il grezzo in conteggi.
        """
        while not self._emi_stop.is_set():
            t = time.monotonic()
            cum = None
            cum_raw = None
            pp1 = None
            try:
                backend = self._counter_backend()
                if backend is not None:
                    domains = backend.read_domains() if hasattr(
                        backend, "read_domains") else None
                    if domains is not None:
                        # (J, ts, pWh): il pWh e' il grezzo del contatore,
                        # persistito accanto alla finestra per rendere la
                        # misura revisionabile (alt_lhm §3). I domini sono
                        # quelli che il metadato del device dichiara: un
                        # device senza PP1 non deve far cadere il PKG.
                        pkg = domains.get("pkg")
                        if pkg is not None:
                            cum = pkg[0]
                            cum_raw = pkg[2]
                        d_pp1 = domains.get("pp1")
                        if d_pp1 is not None:
                            pp1 = (d_pp1[0], d_pp1[1])
                    else:
                        cum = backend.read_cumulative_energy_j()
                        counts = getattr(backend, "cumulative_counts", None)
                        cum_raw = counts if counts is not None else None
            except Exception:
                cum = None
                pp1 = None
            self._accept_emi_sample(t, cum, cum_raw, pp1)
            self._emi_stop.wait(self.EMI_SAMPLE_INTERVAL_S)

    def _accept_emi_sample(self, t: float, cum: Optional[float],
                           cum_raw: Optional[float] = None,
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
                self._emi_samples.append((t, cum, cum_raw))
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
        if self.method == "pawnio-counter":
            from energy import pawnio_backend
            lib = getattr(self._pawnio, "lib_version", "") or "?"
            return f"{pawnio_backend.BACKEND_VERSION}, PawnIOLib {lib}"
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

        Ritorna None se il metodo non e' un contatore ('emi-counter' o
        'pawnio-counter'), se il backend non ha letture, se il buffer non
        copre la finestra (il chiamante degrada al fallback dichiarato sui
        campioni) o se il dominio e' fermo. La ragione del None finisce in
        ``pp1_read_reason`` per le note del CSV: un'assenza muta e' ambigua
        quanto un numero sbagliato.
        """
        if domain == "pp1":
            # la ragione e' lo slot DELL'ultima lettura PP1: una lettura del
            # package non la deve cancellare (il profiler le fa entrambe)
            self._pp1_read_reason = None
        if self.method not in ("emi-counter", "pawnio-counter"):
            return None
        if domain == "pkg":
            with self._emi_lock:
                buf = list(self._emi_samples)
        elif domain == "pp1":
            if self.method != "emi-counter":
                self._pp1_read_reason = (
                    f"dominio PP1 non letto da {self.method!r}: il backend "
                    "campiona il solo registro del package"
                )
                return None
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

    # -- contatore energia via file (DEV/TEST, override di selezione) --------
    def _try_power_counter(self) -> bool:
        """Override di selezione del contatore energetico tramite file.

        Se ``CW_ENERGY_FILE`` e' impostato e il file e' leggibile, questo
        backend viene provato per primo su ogni piattaforma, Windows incluso.
        Se la lettura riesce, la catena termina qui: non si tenta EMI ne'
        PawnIO.

        Il file deve contenere l'energia cumulativa in joule. E' un canale
        DEV/TEST: non e' RAPL nativo, perf_event_open ne' turbostat. Se il
        file e' assente, illeggibile o non contiene un valore valido, il
        metodo restituisce False e la selezione prosegue con la catena di
        piattaforma.
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
            self._notes.append(
                f"[DEV/TEST/{platform_system()}] contatore energia da file {path}"
            )
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
          * "pawnio-counter"              -> contatore MSR del package letto
            dal driver PawnIO [J] (Windows, fallback dichiarato di EMI);
          * "rapl"                        -> contatore RAPL Linux [J]
            (via /sys/class/powercap/intel-rapl/);
          * "energy-file"                 -> contatore dev/test da file
            (override di selezione: vince su ogni piattaforma).
        ``busy_seconds_total`` e' ignorato (retro-compatibilita' di firma).
        """
        if self.method == "emi-counter":
            return self._emi.read_cumulative_energy_j() if self._emi else None
        if self.method == "pawnio-counter":
            return self._pawnio.read_cumulative_energy_j() if self._pawnio else None
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
          * pawnio-counter -> contatore MSR del package cumulato [J];
          * energy-file -> contatore cumulato dev/test;
          * rapl -> contatore RAPL Linux cumulato.
        Ritorna None se nessun backend reale e' disponibile: il chiamante
        deve dichiararlo (mai fallback TDP silenzioso).
        """
        try:
            if self.method == "emi-counter":
                return self._emi.read_cumulative_energy_j() if self._emi else None
            if self.method == "pawnio-counter":
                return (self._pawnio.read_cumulative_energy_j()
                        if self._pawnio else None)
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
          * mode="emi-counter" / "pawnio-counter": delta del contatore
            cumulativo Windows (EMI su device, MSR via PawnIO in fallback);
          * mode="energy-counter": delta del contatore Joule da file (dev/test).
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
                _mode = (self.method if self.method in
                         ("emi-counter", "pawnio-counter")
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
    gpu_energy_mj: Optional[float] = None   # contatore cumulativo della GPU (mJ)
    # Timestamp del contatore, solo AMD SMI (ns, doc C "Resolution: 1 ns").
    # NVML non lo espone: None. Serve a distinguere una lettura ferma da uno
    # zero legittimo, non a datare il campione (quello e' ``t``).
    gpu_energy_ts_ns: Optional[int] = None


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
        self._gpu = _open_gpu_monitor()
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
        """Una lettura del contatore, con l'istante e il timestamp del record.

        Ritorna ``counter`` (None se il canale non e' aperto o la lettura
        fallisce) e, in ogni caso, ``counter_error`` con la ragione: un bordo
        senza contatore e' un fatto dichiarato, non un bordo "sincrono"
        presunto. ``t_mono`` e' preso PRIMA della lettura, come fa il sampler
        (``_emi_loop``): cosi' l'istante e' confrontabile con il buffer.

        Il record ha la stessa forma per EMI e PawnIO: ``pkg_j`` (cumulato),
        il grezzo in unita' nativa (``pkg_pwh`` per EMI, ``pkg_counts`` per
        PawnIO, entrambi assenti nell'altro caso) e ``ts_100ns`` (solo EMI:
        il record MSR non porta un timestamp del dominio).
        """
        t_wall = time.time()
        t_mono = time.monotonic()
        counter = None
        err = ""
        try:
            backend = getattr(self._source, "_emi", None)
            if backend is not None:
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
            else:
                pbackend = getattr(self._source, "_pawnio", None)
                if pbackend is None:
                    err = "contatore non aperto (ne' EMI ne' PawnIO)"
                else:
                    j = pbackend.read_cumulative_energy_j()
                    if j is None:
                        err = "lettura del contatore PawnIO fallita"
                    else:
                        counter = {
                            "pkg_j": float(j),
                            "pkg_counts": int(pbackend.cumulative_counts),
                            "ts_100ns": None,
                            "pp1_j": None,
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
        gpu_mj, gpu_ts = self._gpu.read_energy()
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
            gpu_energy_mj=gpu_mj,
            gpu_energy_ts_ns=gpu_ts,
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
            # contatore cumulativo (EMI o PawnIO): il buffer (t, cumulata)
            # parte qui, non all'import (l'import non deve avviare thread).
            if self._source.method in ("emi-counter", "pawnio-counter"):
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

        - ferma e joina il sampler del contatore cumulativo (<= 5 s);
        - chiude il device EMI o la libreria PawnIO UNA sola volta;
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
        if getattr(src, "_pawnio", None) is not None:
            try:
                src._pawnio.close()
            except Exception:
                pass
            src._pawnio = None
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
        * PawnIO: conteggi del contatore MSR cumulati dall'apertura (interi,
          gia' srotolati: un riporto non rientra), con il quantum in unita';
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
        if src.method in ("emi-counter", "pawnio-counter"):
            with src._emi_lock:
                buf = list(src._emi_samples if domain == "pkg"
                           else src._emi_pp1_samples)
            if len(buf) >= 2:
                out["domain"] = "PKG" if domain == "pkg" else "PP1"
                out["sampling_interval_observed_s"] = _median_sampling_interval(
                    buf, t_start, t_end)
                if domain == "pkg":
                    if src.method == "emi-counter":
                        out["raw_unit"] = "pWh"
                    else:
                        q = getattr(src._pawnio, "quantum_j", None)
                        out["raw_unit"] = (
                            f"counts (32-bit MSR, quantum {q:.9g} J)"
                            if q else "counts (32-bit MSR)")
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
        ai bordi (stesso buffer a 0,05 s del contatore cumulativo).

        * EMI o PawnIO: differenza del contatore cumulativo sui segmenti
          tenuti (niente trapezi; le sottofinestre escluse sono rimosse alla
          fonte);
        * energy-counter (file dev-test): delta del contatore cumulato
          read_power_j() agli estremi; le sottofinestre escluse vengono
          sottratte integrando i campioni package nella regione esclusa
          (i campioni ci sono: niente scaling per frazione temporale).
        Ritorna None se il backend non puo' esprimere una lettura esatta
        (il profiler degrada al fallback dichiarato sui campioni).
        """
        m = self._source.method
        if m in ("emi-counter", "pawnio-counter"):
            # bordi esatti letti dal buffer del cumulativo a 0,05 s: niente
            # trapezi, e' la differenza del contatore sui segmenti tenuti.
            e_buf = self._source.emi_window_energy_j(t_start, t_end, exclude_windows)
            if e_buf is not None:
                return e_buf
            # buffer insufficiente (finestra oltre la copertura): degrada al
            # ramo contatore qui sotto, che resta un percorso a campione
            # reale e dichiarato — mai un valore interpolato inventato.
        if m in ("emi-counter", "pawnio-counter", "energy-file", "rapl"):
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
            # Il contatore e' cumulativo: interpolarlo ai bordi e' la stessa
            # convenzione usata per package_energy_j, non una stima in piu'.
            gpu_energy_mj=num(a.gpu_energy_mj, b.gpu_energy_mj),
            # Il timestamp e' un orologio del device, non una grandezza da
            # mediare: si porta il valore del campione precedente e non si
            # interpola. Serve solo a dire se il contatore e' avanzato.
            gpu_energy_ts_ns=a.gpu_energy_ts_ns,
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
        if self._source.method not in ("rapl", "emi-counter", "pawnio-counter"):
            cause = "; ".join(self._source.notes[-3:]) or f"metodo='{self._source.method}'"
            raise RuntimeError(
                "calibrazione idle fallita: nessun contatore di energia/potenza "
                "package disponibile. Causa: " + cause +
                ". Su Windows: esegui 'py diagnostics.py' (device EMI o "
                "contatore MSR via PawnIO). "
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
    backend = "nvml"

    def __init__(self) -> None:
        self.available = False
        self.handle = None
        self.index = 0
        self.name: Optional[str] = None
        self.error: Optional[str] = None
        # Unita' del valore scritto in ``gpu_power_w``, non della sorgente:
        # qui mW/1000 -> W. "unknown" finche' non si e' letto un valore, cosi'
        # una riga senza potenza non dichiara un'unita' che non ha usato.
        self.power_unit = "unknown"
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
        self.energy_counter = False
        self.energy_counter_reason = ""
        self._probe_energy_counter()

    def _probe_energy_counter(self) -> None:
        """Sonda il contatore cumulativo NVML una volta, all'apertura.

        Documentazione verificata alla fonte il 28-10-2026 (NVML API Guide,
        R535): ``nvmlDeviceGetTotalEnergyConsumption(device, unsigned long
        long* energy)`` restituisce "the total energy consumed in mJ", "since
        the last reset", su Kepler e successivi, e "does not overflow". Il
        punto zero e' un reset, non l'inizio della finestra: il valore si usa
        per DELTA. Una lettura reale qui, non solo ``hasattr``: il supporto si
        verifica, non si presume (un device pre-Kepler risponde
        NVML_ERROR_NOT_SUPPORTED).
        """
        if not self.available:
            self.energy_counter_reason = "GPU non disponibile"
            return
        try:
            import pynvml

            fn = getattr(pynvml, "nvmlDeviceGetTotalEnergyConsumption", None)
            if fn is None:
                self.energy_counter_reason = (
                    "pynvml senza nvmlDeviceGetTotalEnergyConsumption")
                return
            fn(self.handle)
            self.energy_counter = True
        except Exception as exc:  # noqa: BLE001
            self.energy_counter_reason = f"{type(exc).__name__}"

    def read_energy(self):
        """(contatore cumulativo [mJ], timestamp [ns]) o (None, None).

        NVML non espone un timestamp del contatore: il secondo elemento e'
        sempre ``None``, quindi il controllo di avanzamento non si applica a
        questo backend. ``None`` e' l'assenza dichiarata: il chiamante integra
        la potenza e lo scrive in ``gpu_attribution_method``, non inventa un
        delta.
        """
        if not (self.available and self.energy_counter):
            return None, None
        try:
            import pynvml

            return (float(pynvml.nvmlDeviceGetTotalEnergyConsumption(self.handle)),
                    None)
        except Exception:  # noqa: BLE001
            return None, None

    def read(self):
        if not self.available:
            return None, None
        try:
            import pynvml

            mw = pynvml.nvmlDeviceGetPowerUsage(self.handle)
            util = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
            self.power_unit = "W"   # sorgente mW, divisa per 1000 qui
            return float(mw) / 1000.0, float(util.gpu)
        except Exception:
            try:
                import pynvml

                mw = pynvml.nvmlDeviceGetPowerUsage(self.handle)
                self.power_unit = "W"
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


# ---------------------------------------------------------------------------
# GPU AMD (AMD SMI) — fallback dichiarato, non un secondo lettore simultaneo
# ---------------------------------------------------------------------------
class _AMDGPUMonitor:
    """Contatore e potenza GPU AMD via AMD SMI.

    Documentazione verificata alla fonte il 28-10-2026. Python API (versione
    27.1.0): ``amdsmi_get_energy_count`` restituisce ``energy_accumulator``,
    ``counter_resolution`` e ``timestamp`` con la regola scritta
    "energy_accumulator * counter_resolution = total_energy_consumption in
    micro-Joules", accumulata "since last restart/gpu reset"; la funzione
    "is not supported on virtual machine guest". La reference C dichiara la
    risoluzione del timestamp, "1 ns": l'unita' del campo non e' nella pagina
    Python, e per questo il timestamp si usa solo per confrontare due letture
    (avanzato / fermo), mai come durata.

    Potenza: ``socket_power`` "matches current or average socket power" ed e'
    il campo generale; ``current_socket_power`` e' quello delle "Mi300+ Series
    Cards", ``average_socket_power`` quello di "Navi + Mi 200 and earlier".
    L'ordine di lettura segue il campo generale, non la preferenza storica.
    Tutti e tre sono documentati in W: l'unita' non si deduce dal nome.

    Il contatore si converte in mJ all'ingresso (uJ/1000) perche' il resto del
    percorso parla una sola unita': il campo del campione e' ``gpu_energy_mj``
    indipendentemente dal backend, e la conversione sta qui, non nel profilo.
    """

    backend = "amdsmi"

    def __init__(self) -> None:
        self.available = False
        self.handle = None
        self.index = 0
        self.name: Optional[str] = None
        self.error: Optional[str] = None
        self.power_field = ""
        self.power_unit = "unknown"     # "W" solo dopo una lettura riuscita
        self.platform_context = "unknown"
        self.energy_counter = False
        self.energy_counter_reason = ""
        self._resolution_uj = 0.0
        try:
            import amdsmi

            amdsmi.amdsmi_init()
            handles = list(amdsmi.amdsmi_get_processor_handles() or [])
            if not handles:
                self.error = "nessuna GPU AMD SMI"
            else:
                self.handle = handles[0]
                self.index = 0
                try:
                    info = amdsmi.amdsmi_get_gpu_asic_info(self.handle) or {}
                    self.name = info.get("market_name") or None
                except Exception:  # noqa: BLE001
                    self.name = None
                self.available = True
        except Exception as exc:  # noqa: BLE001
            self.error = f"{type(exc).__name__}"
        if self.available:
            # La reference C marca questa chiamata ``Platform: gpu_bm_linux``:
            # se ha risposto, la restrizione "not supported on virtual machine
            # guest" non ha morso. Non prova il bare metal, dichiara che il
            # vincolo del fornitore non si e' applicato.
            self.platform_context = ("gpu_bm_linux"
                                     if sys.platform.startswith("linux")
                                     else "non-linux")
        self._probe_energy_counter()

    def _probe_energy_counter(self) -> None:
        """Una lettura reale del contatore: la risoluzione si verifica, non si presume."""
        if not self.available:
            self.energy_counter_reason = "GPU non disponibile"
            return
        try:
            import amdsmi

            ec = amdsmi.amdsmi_get_energy_count(self.handle) or {}
            res = float(ec.get("counter_resolution") or 0.0)
            if res <= 0.0 or ec.get("energy_accumulator") is None:
                self.energy_counter_reason = "risoluzione del contatore nulla"
                return
            self._resolution_uj = res
            self.energy_counter = True
        except Exception as exc:  # noqa: BLE001
            self.energy_counter_reason = f"{type(exc).__name__}"

    def read_energy(self):
        """(energia cumulativa [mJ], timestamp [ns]) o (None, None).

        ``mJ = accumulator * resolution [uJ] / 1000``. Il timestamp viene
        dalla stessa lettura del contatore, quindi la coppia e' coerente: due
        campioni con lo stesso timestamp sono la stessa lettura del device,
        anche se il contatore e' avanzato.
        """
        if not (self.available and self.energy_counter):
            return None, None
        try:
            import amdsmi

            ec = amdsmi.amdsmi_get_energy_count(self.handle) or {}
            acc = float(ec.get("energy_accumulator"))
            ts = ec.get("timestamp")
            return (acc * self._resolution_uj / 1000.0,
                    int(ts) if ts is not None else None)
        except Exception:  # noqa: BLE001
            return None, None

    def read(self):
        """(potenza W, attivita' %). La chiave di potenza usata resta dichiarata."""
        if not self.available:
            return None, None
        try:
            import amdsmi

            info = amdsmi.amdsmi_get_power_info(self.handle) or {}
            power_w = None
            # ``socket_power`` e' il campo generale ("matches current or
            # average"); gli altri due sono specifici per generazione.
            for key in ("socket_power", "current_socket_power",
                        "average_socket_power"):
                val = info.get(key)
                if val is not None:
                    power_w = float(val)
                    self.power_field = key
                    self.power_unit = "W"    # unita' dichiarata dalla doc
                    break
            try:
                act = amdsmi.amdsmi_get_gpu_activity(self.handle) or {}
                util = float(act.get("gfx_activity"))
            except Exception:  # noqa: BLE001
                util = None
            return power_w, util
        except Exception:  # noqa: BLE001
            return None, None

    def shutdown(self) -> None:
        try:
            import amdsmi

            amdsmi.amdsmi_shut_down()
        except Exception:  # noqa: BLE001
            pass


def _open_gpu_monitor():
    """NVML -> AMD SMI -> monitor non disponibile, con i motivi di entrambi.

    Un solo backend alla volta: se NVML risponde si usa NVML, anche su una
    macchina con entrambi i driver, perche' due lettori della stessa scheda
    nella stessa riga sarebbero un doppio conteggio da giustificare.
    """
    nv = _GPUMonitor()
    if nv.available:
        return nv
    amd = _AMDGPUMonitor()
    if amd.available:
        return amd
    nv.error = (f"NVML: {nv.error or 'non disponibile'}; "
                f"AMD SMI: {amd.error or amd.energy_counter_reason or 'non disponibile'}")
    return nv


# Singleton di sessione (sezione 16: ``from .energy_session import SESSION``)
SESSION = EnergySession()
