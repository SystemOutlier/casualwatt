# -*- coding: utf-8 -*-
"""
energy/local_energy.py — Profilo energetico causale per inferenza LOCALE.

Formule implementate (sezione 2 della specifica, nessuna invenzione):

    E_attiva = max(0, E_package - P_idle * dt)
    E_ollama = E_attiva * (dt_cpu_ollama / dt_cpu_busy)

con:
* E_package      : energia package CPU nella finestra della richiesta.
                   METODO UFFICIALE SU WINDOWS 11 (CPU senza contatore
                   Energy, es. Intel i9-13900HK): "power-integration" ->
                   sensore LibreHardwareMonitor 'CPU Package' [W] campionato
                   ogni 0.05 s e integrato nel tempo con regola trapezoidale
                   sum(((P_i + P_i+1)/2) * (t_i+1 - t_i)). NIENTE RAPL/
                   perf_event_open/turbostat, NIENTE stime TDP, NIENTE
                   moltiplicatori arbitrari. Su piattaforme non-Windows la
                   misurazione locale CPU e' disabilitata con messaggio
                   esplicito (GUI/Ollama/cloud/CSV restano utilizzabili).
* P_idle         : potenza idle calibrata (SESSION.calibrate_idle, solo
                   Windows+LHM, >=30 s x 3 ripetizioni, mediana);
* dt_cpu_ollama  : secondi CPU dell'albero Ollama nella finestra;
* dt_cpu_busy    : secondi CPU busy NON-idle di tutto il sistema nella finestra.

La baseline idle e' salvata separatamente in ``baseline_energy_j`` e NON entra
in ``local_energy_j`` ne' in ``end_to_end_energy_j`` (sezioni 12.1/12.3).

GPU:
* NVIDIA dedicata -> integrazione temporale del power draw NVML al netto
  della potenza GPU a idle calibrata, sulla STESSA finestra/dt usati per
  integrare board_j (confine: whole-device, dichiarato in
  gpu_attribution_method). L'utilizzo medio e' solo campo diagnostico
  (gpu_utilization_share), NON un moltiplicatore: la potenza GPU riflette
  gia' il carico, quindi moltiplicare per lo share conteggierebbe il
  carico due volte. Attribuzione per processo (nvmlDeviceGetProcess-
  Utilization) esposta in gpu_process_energy_j quando disponibile,
  altrimenti N/A con nota;
* iGPU Intel/AMD integrata -> NON viene aggiunta alcuna quota separata a
  local_energy_j quando la sorgente CPU e' il package: l'energia della
  grafica integrata e' GIÀ inclusa nel sensore 'CPU Package'. Se LHM
  espone il sensore 'CPU Graphics' viene letto come campo INFORMATIVO
  igpu_energy_j, mai sommato. La vecchia euristica IGPU_POWER_SHARE e'
  deprecata e non usata.

Coerenza finestra (correzioni A1/B1): E_package e baseline coprono SEMPRE
lo stesso intervallo [t_start, t_end] ridotto delle sottofinestre escluse:
la baseline e' P_idle * dt_effettiva, mai scalata su una porzione diversa
dell'integrale. Con backend attivo l'energia package e' letta ESATTAMENTE
a t_start/t_end dal contatore integrato a 0,05 s (lock del thread di
integrazione); il percorso sui campioni interpolati resta solo come
fallback dichiarato nelle note.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import psutil

from .energy_session import SESSION, SystemSample


@dataclass
class LocalEnergyResult:
    duration_s: float = 0.0
    package_energy_j: float = 0.0
    idle_power_w: float = 0.0
    baseline_energy_j: float = 0.0
    active_energy_j: float = 0.0
    ollama_active_energy_j: float = 0.0
    cpu_time_share: float = 0.0
    gpu_available: bool = False
    gpu_device_index: Optional[int] = None
    gpu_board_energy_j: float = 0.0
    gpu_energy_attributed_j: float = 0.0
    gpu_utilization_share: float = 0.0
    # attribuzione per processo NVIDIA (N/A se NVML non la espone)
    gpu_process_energy_j: Optional[float] = None
    igpu_energy_j: Optional[float] = None   # informativo, MAI sommato
    package_window_source: str = ""         # exact-counter | samples-fallback
    idle_provenance: Optional[str] = None   # calibrated|session|uncalibrated
    measurement_boundary: str = ""
    cpu_attribution_method: str = ""
    gpu_attribution_method: str = ""
    notes: List[str] = field(default_factory=list)


class CasualWattLocalEnergyProfiler:
    """Profilatore causale: misura la finestra [t_start, t_end] sui campioni."""

    def __init__(self) -> None:
        self.session = SESSION

    # ------------------------------------------------------------------ core
    def profile_window(
        self,
        t_start: float,
        t_end: float,
        ollama_pids: Optional[List[int]] = None,
        direct_io_delta: Optional[float] = None,
        direct_cpu_delta: Optional[float] = None,
        exclude_windows: Optional[List[tuple]] = None,
    ) -> LocalEnergyResult:
        """Profilazione causale della finestra [t_start, t_end].

        exclude_windows: lista di (a, b) da SCORPORARE dal calcolo (es. la
        chiamata al LLM Judge, che avviene DOPO l'inferenza e non deve essere
        attribuita al modello valutato). Le finestre escluse riducono dt,
        sottraggono il tempo busy Ollama e accorciano la coda dei campioni per
        lo share CPU — tutto dichiarato nelle note.
        """
        res = LocalEnergyResult()
        dt = max(t_end - t_start, 1e-6)

        # ---- scorporo sottofinestre escluse (es. LLM Judge) ----------------
        excl = sorted(
            [(max(a, t_start), min(b, t_end)) for a, b in (exclude_windows or [])
             if b > t_start and a < t_end and max(b, t_end) - min(a, t_start) > 0],
            key=lambda w: w[0],
        )
        excl_s = sum(b - a for a, b in excl)
        if excl_s > 0:
            excl_txt = ", ".join(f"[{a:.2f}-{b:.2f}]" for a, b in excl)
            notes_excl = (
                f"sottofinestre escluse dal profilo ({excl_s:.2f} s: {excl_txt}): "
                "energia del LLM Judge SCORPORATA dal modello valutato"
            )
            dt = max(dt - excl_s, 1e-6)
        else:
            notes_excl = ""

        res.duration_s = dt

        samples: List[SystemSample] = self.session.samples_between(t_start, t_end)
        notes: List[str] = []
        if notes_excl:
            notes.append(notes_excl)

        # ---------------------------------------------------------- CPU part
        busy_first = samples[0].cpu_busy_seconds if samples else 0.0
        busy_last = samples[-1].cpu_busy_seconds if samples else 0.0

        idle_power_w = self.session.idle_power_w
        idle_proven = getattr(self.session, "idle_provenance", None)
        if idle_power_w is None:
            # B3: NESSUNA micro-calibrazione in mezzo al benchmark (blocca e
            # avviene a macchina calda -> sovrastima P_idle). Se l'utente non
            # ha calibrato, la baseline e' 0 con provenienza dichiarata.
            idle_power_w = 0.0
            idle_proven = "uncalibrated"
            notes.append(
                "P_idle NON calibrato (provenienza 'uncalibrated'): "
                "baseline_energy_j = 0; eseguire 'Calibra idle' dalla GUI "
                "(>=30 s x 3 ripetizioni, PC a riposo) prima del benchmark"
            )
        res.idle_power_w = float(idle_power_w or 0.0)
        res.idle_provenance = idle_proven

        method = self.session.source_method

        # ---- B1: energia package ESATTA ai bordi della finestra -----------
        # Con backend attivo si legge il contatore integrato a 0,05 s (stesso
        # lock del thread di integrazione) esattamente a t_start e t_end:
        # nessuna interpolazione sui campioni a ~0,25-0,5 s. Il percorso sui
        # campioni resta SOLO come fallback dichiarato nelle note.
        e_package: Optional[float] = None
        exact_fn = getattr(self.session, "package_energy_exact_between", None)
        if callable(exact_fn):
            try:
                e_package = exact_fn(t_start, t_end, excl)
            except Exception as exc:  # mai un crash: degrada al fallback
                notes.append(f"lettura esatta contatore fallita ({type(exc).__name__})")
                e_package = None
        if e_package is not None and e_package >= 0.0:
            res.package_window_source = "exact-counter"
            res.cpu_attribution_method = (
                f"{method}; cpu-time-share attribution "
                "(E_attiva * dt_cpu_ollama/dt_cpu_busy); window read exactly "
                "at t_start/t_end from the 0.05 s integration counter"
            )
        else:
            # FALLBACK dichiarato: differenza dei campioni interpolati
            pkg_first = next((s.package_energy_j for s in samples if s.package_energy_j is not None), None)
            pkg_last = next(
                (s.package_energy_j for s in reversed(samples) if s.package_energy_j is not None),
                None,
            )
            if pkg_first is not None and pkg_last is not None and pkg_last >= pkg_first:
                res.package_window_source = "samples-fallback"
                notes.append(
                    "fallback dichiarato: E_package da campioni interpolati "
                    f"(~{self.session.interval_s}s) perche' il contatore esatto "
                    "non era leggibile ai bordi della finestra"
                )
                if method == "power-integration":
                    # media dei campioni * dt: equivalente all'integrale ma
                    # meno preciso del percorso esatto
                    e_package = max(pkg_last - pkg_first, 0.0)
                else:
                    e_package = 0.0
                    prev = samples[0]
                    for cur in samples[1:]:
                        if cur.package_energy_j is not None \
                                and prev.package_energy_j is not None:
                            e_package += max(cur.package_energy_j - prev.package_energy_j, 0.0)
                        prev = cur
                res.cpu_attribution_method = (
                    f"{method}; cpu-time-share attribution "
                    "(E_attiva * dt_cpu_ollama/dt_cpu_busy)"
                )
            else:
                e_package = 0.0
                res.package_window_source = "unavailable"
                notes.append(
                    "nessun campione package nella finestra: misurazione locale "
                    "dichiarata indisponibile (metodo attivo: "
                    f"'{self.session.source_method}')"
                )
                res.cpu_attribution_method = "unavailable"

        res.package_energy_j = round(max(e_package, 0.0), 6)
        # ---- A1: baseline SEMPRE sulla stessa finestra dell'integrale -----
        # La vecchia logica "coda inattiva" scalava la baseline su
        # [t_start, t_last_active] mentre E_package copriva tutta la
        # finestra: E_attiva accumulava P_idle * durata_coda (sovrastima).
        # Ora le due grandezze coprono lo STESSO intervallo:
        #     baseline = P_idle * dt_effettiva   (dt gia' ridotto delle
        #     sottofinestre escluse, coerenza B2)
        res.baseline_energy_j = round(res.idle_power_w * dt, 6)
        active = max(res.package_energy_j - res.baseline_energy_j, 0.0)
        res.active_energy_j = round(active, 6)

        # ---- B2: cpu busy sugli intervalli NON esclusi (coerenza) ---------
        if excl:
            def _in_excl(a: float, b: float) -> bool:
                return any(not (b <= x or a >= y) for x, y in excl)
            pairs = list(zip(samples[1:], samples[:-1]))
            kept = [(p, q) for p, q in pairs if not _in_excl(q.t, p.t)]
            d_busy = 0.0
            for p, q in kept:
                d_busy += max(p.cpu_busy_seconds - q.cpu_busy_seconds, 0.0)
            dt_cpu_busy = d_busy
        else:
            dt_cpu_busy = max(busy_last - busy_first, 0.0)

        # delta CPU-time albero Ollama: preferisce istogrammi campione-campione
        if excl:
            # scorporo judge: limita il delta agli intervalli NON esclusi
            d_ollama = self._ollama_cpu_delta([q for q, p in kept] + [p for p, q in kept]) \
                if kept else 0.0
            # calcolo diretto sugli intervalli tenuti (istogrammi consecutivi)
            d2 = 0.0
            ok2 = False
            for p, q in kept:
                if p.ollama_pids and q.ollama_pids:
                    try:
                        pa = sum(p.ollama_pids.values())
                        qa = sum(q.ollama_pids.values())
                        if qa >= pa:
                            d2 += qa - pa
                            ok2 = True
                    except Exception:
                        ok2 = False
            if ok2:
                d_ollama = d2
        else:
            d_ollama = self._ollama_cpu_delta(samples)
        if d_ollama is None and direct_cpu_delta is not None:
            d_ollama = max(direct_cpu_delta, 0.0)
            notes.append("cpu-time Ollama da contatore diretto della request (fallback)")
        if d_ollama is None:
            d_ollama = 0.0
            notes.append("cpu-time Ollama non osservabile: share = 0 (conservativo)")
        share = 0.0
        if dt_cpu_busy > 0:
            share = min(max(d_ollama / dt_cpu_busy, 0.0), 1.0)
        res.cpu_time_share = round(share, 6)
        res.ollama_active_energy_j = round(active * share, 6)

        # ---------------------------------------------------------- GPU part
        gpu_mon = self.session._gpu
        gpu_samples = [s for s in samples if s.gpu_power_w is not None]
        if gpu_mon.available and len(gpu_samples) >= 2:
            res.gpu_available = True
            res.gpu_device_index = gpu_mon.index
            # integrazione trapezoidale del power draw + dt REALE coperto
            board_j = 0.0
            gpu_dt = 0.0
            prev = gpu_samples[0]
            util_sum = 0.0
            util_n = 0
            for cur in gpu_samples[1:]:
                seg_dt = cur.t - prev.t
                if seg_dt > 0:
                    board_j += ((prev.gpu_power_w + cur.gpu_power_w) / 2.0) * seg_dt
                    gpu_dt += seg_dt
                if cur.gpu_util_pct is not None:
                    util_sum += cur.gpu_util_pct
                    util_n += 1
                prev = cur
            idle_gpu_w = getattr(self.session, "idle_gpu_power_w", None) or 0.0
            # A2: NESSUNA moltiplicazione per lo share di utilizzo: la potenza
            # board riflette gia' il carico. Attribuzione whole-device:
            #     E_gpu_attr = max(board_j - P_idle_gpu * dt_gpu, 0)
            # con dt_gpu = intervallo reale coperto dall'integrale (coerenza).
            active_gpu_j = max(board_j - idle_gpu_w * gpu_dt, 0.0)
            util_share = (util_sum / util_n / 100.0) if util_n else 1.0
            res.gpu_board_energy_j = round(board_j, 6)
            res.gpu_utilization_share = round(util_share, 6)  # SOLO diagnostico
            res.gpu_energy_attributed_j = round(active_gpu_j, 6)
            res.gpu_attribution_method = (
                "nvml-power-integral minus calibrated idle over the same "
                f"integrated span ({gpu_dt:.3f}s); boundary=whole-device; "
                "utilization kept as diagnostic field only (NOT a multiplier)"
            )
            notes.append(
                f"GPU '{gpu_mon.name}': board {board_j:.2f} J, attribuiti "
                f"{res.gpu_energy_attributed_j:.2f} J (whole-device, no double count)"
            )
            # attribuzione per processo (opzionale, dichiarata)
            proc_fn = getattr(gpu_mon, "process_energy_j", None)
            if callable(proc_fn):
                try:
                    pj = proc_fn(t_start, t_end, ollama_pids)
                    if pj is not None:
                        res.gpu_process_energy_j = round(pj, 6)
                        notes.append("GPU: attribuzione per processo NVML disponibile")
                    else:
                        notes.append(
                            "GPU: nvmlDeviceGetProcessUtilization non disponibile "
                            "per i PID Ollama -> gpu_process_energy_j = N/A"
                        )
                except Exception:
                    notes.append("GPU process-level attribution unavailable (N/A)")
            else:
                notes.append(
                    "GPU process-level attribution non supportata dal monitor "
                    "attivo -> gpu_process_energy_j = N/A"
                )
        elif method in ("power-integration", "librehardwaremonitor",
                        "librehardwaremonitor-energy"):
            # A3: iGPU Intel/AMD integrata — il sensore 'CPU Package' INCLUDE
            # gia' la grafica: NON si aggiunge ALCUN termine a local_energy_j
            # e NON esiste piu' l'euristica IGPU_POWER_SHARE (deprecata).
            res.gpu_attribution_method = (
                "igpu-included-in-package (no separate term added; "
                "IGPU_POWER_SHARE heuristic deprecated and unused)"
            )
            igpu_fn = getattr(self.session, "read_igpu_energy_j", None)
            if callable(igpu_fn):
                try:
                    res.igpu_energy_j = igpu_fn(t_start, t_end)
                except Exception:
                    res.igpu_energy_j = None
            if res.igpu_energy_j is not None:
                notes.append(
                    "iGPU: sensore 'CPU Graphics' letto come campo INFORMATIVO "
                    "igpu_energy_j (gia' incluso nel package, NON sommato)"
                )
            else:
                notes.append(
                    "iGPU: nessun contatore grafico dedicato esposto da LHM; "
                    "energia iGPU inclusa nel package (dichiarato, nessuna quota inventata)"
                )
        else:
            res.gpu_attribution_method = "not-applicable"

        # ------------------------------------------------------- boundary
        # B2: le sottofinestre escluse sono gia' state rimosse alla fonte
        # (lettura esatta del contatore sugli intervalli tenuti, busy e
        # cpu-time Ollama sugli stessi intervalli). Nessuno scaling temporale.
        src_desc = {
            "power-integration": (
                "LibreHardwareMonitor 'CPU Package' [W] sampled every 0.05 s, "
                "trapezoidal time integration (no Energy counter on this CPU)"
            ),
            "librehardwaremonitor-energy": "LibreHardwareMonitor package energy counter",
            "librehardwaremonitor": "LibreHardwareMonitor (no readable counters)",
            "energy-file": "[DEV/TEST non-Windows] user-provided joule counter file",
            "unavailable": (
                "LOCAL CPU ENERGY MEASUREMENT DISABLED: available only on "
                "Windows with LibreHardwareMonitor"
            ),
        }.get(method, method)
        res.measurement_boundary = (
            f"client-host system boundary; window interpolation over {len(samples)} "
            f"samples @ {self.session.interval_s}s; CPU source: {src_desc}"
        )
        res.notes = notes
        return res

    # ------------------------------------------------------------------ util
    @staticmethod
    def _ollama_cpu_delta(samples: List[SystemSample]) -> Optional[float]:
        valid = [s for s in samples if s.ollama_pids]
        if len(valid) < 2:
            return None
        first, last = valid[0], valid[-1]
        if not first.ollama_pids or not last.ollama_pids:
            return None
        # confronta solo se l'albero ha PID comparabili (stesso insieme base)
        d = last.ollama_cpu_seconds - first.ollama_cpu_seconds
        if d < 0:
            # processo worker sostituito tra i campioni: usa il max positivo
            run_max = 0.0
            prev_val = None
            for s in valid:
                if prev_val is not None:
                    run_max = max(run_max, s.ollama_cpu_seconds - prev_val)
                prev_val = s.ollama_cpu_seconds
            d = run_max
        return max(d, 0.0)

    # ------------------------------------------------------------ convenience
    def measure_request(
        self,
        fn,
        *args,
        **kwargs,
    ):
        """Esegue ``fn`` dentro una finestra profilata. Ritorna (esito, risultato)."""
        t0 = time.monotonic()
        outcome = fn(*args, **kwargs)
        t1 = time.monotonic()
        result = self.profile_window(t0, t1)
        return outcome, result
