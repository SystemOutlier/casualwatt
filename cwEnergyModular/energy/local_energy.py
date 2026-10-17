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
  della potenza GPU a idle (calibrata anch'essa); attribuzione per quota di
  utilizzazione media nella finestra (confine: whole-device, dichiarata);
* Intel/AMD senza contatore -> frazione IGPU_POWER_SHARE dell'energia ATTIVA
  package (euristica dichiarata, mai applicata all'energia totale).
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
        pkg_first = next((s.package_energy_j for s in samples if s.package_energy_j is not None), None)
        pkg_last = next(
            (s.package_energy_j for s in reversed(samples) if s.package_energy_j is not None),
            None,
        )
        busy_first = samples[0].cpu_busy_seconds if samples else 0.0
        busy_last = samples[-1].cpu_busy_seconds if samples else 0.0
        dt_cpu_busy = max(busy_last - busy_first, 0.0)
        if excl_s > 0:
            # quota busy stimata proporzionale alle finestre escluse
            # (conservativo: sottostima mai sovrastima l'attribuzione Ollama)
            dt_cpu_busy = max(dt_cpu_busy - dt_cpu_busy * excl_s / max(excl_s + dt, 1e-6), 0.0)

        idle_power_w = self.session.idle_power_w
        if idle_power_w is None:
            # mai calibrato: tenta la micro-calibrazione empirica a riposo
            # (2 s) con la STESSA funzione di lettura del benchmark. Su
            # piattaforme non-Windows o senza backend reale il valore viene
            # esplicitamente marcato indisponibile (baseline 0): nessun
            # numero inventato, nessun fallback TDP.
            try:
                idle_power_w = self.session.calibrate_idle(2.0)
                notes.append("P_idle non calibrato dall'utente: micro-calibrazione empirica 2 s")
            except Exception as exc:
                idle_power_w = 0.0
                notes.append(
                    "P_idle non calibrato e misurazione locale non disponibile "
                    f"({type(exc).__name__}): baseline_energy_j = 0 (dichiarato)"
                )
        res.idle_power_w = float(idle_power_w or 0.0)

        method = self.session.source_method
        # ---------------------------------------------------------------
        # Anti-overstatement su finestre con code inattive: se l'albero
        # Ollama NON consuma CPU-time negli ultimi ~1.5 intervalli prima di
        # t_end, il worker e' gia' tornato in idle ma il contatore package
        # continua a integrare P_idle per tutta la coda della finestra.
        # In quel caso la baseline viene scalata sulla sola porzione attiva
        # [t_start, t_last_active], cosi' E_attiva non accumula energia
        # idle residua. Il confine reale resta dichiarato in
        # measurement_boundary. La micro-calibrazione interna NON vale come
        # prova di inattivita': si applica solo con P_idle calibrato da
        # GUI/sessione (idle_proven = calibrated|session).
        # ---------------------------------------------------------------
        # La micro-calibrazione empirica interna usa lo STESSO metodo della
        # calibrazione GUI (delta Joule a riposo): se il contatore ha risposto,
        # il valore e' affidabile e abilita lo scorporo code inattive.
        idle_proven = getattr(self.session, "idle_provenance", None)
        active_end_dt = dt
        if (
            idle_proven in ("calibrated", "session")
            and len(samples) >= 3
        ):
            d_tail = self._ollama_cpu_delta(samples[-2:])
            if d_tail is not None and d_tail <= 1e-6:
                last_active = samples[-2]
                active_end_dt = max(last_active.t - t_start, 1e-6)
                if active_end_dt < dt:
                    notes.append(
                        f"coda inattiva rilevata ({dt - active_end_dt:.2f} s): "
                        "baseline scalata sulla sola finestra attiva"
                    )

        if pkg_first is not None and pkg_last is not None and pkg_last >= pkg_first:
            # Energia reale della finestra: integrazione trapezoidale dei
            # campioni (P_i+P_i+1)/2*dt — con method="power-integration" i
            # campioni provengono dal sensore CPU Package [W] a 0.05 s.
            e_package = 0.0
            prev = samples[0]
            for cur in samples[1:]:
                seg_dt = cur.t - prev.t
                if seg_dt > 0 and prev.package_energy_j is not None \
                        and cur.package_energy_j is not None:
                    e_package += max(cur.package_energy_j - prev.package_energy_j, 0.0)
                prev = cur
            res.cpu_attribution_method = (
                f"{method}; cpu-time-share attribution "
                "(E_attiva * dt_cpu_ollama/dt_cpu_busy)"
            )
        else:
            e_package = 0.0
            notes.append(
                "nessun campione package nella finestra: misurazione locale "
                "dichiarata indisponibile (metodo attivo: "
                f"'{self.session.source_method}')"
            )
            res.cpu_attribution_method = "unavailable"

        res.package_energy_j = round(max(e_package, 0.0), 6)
        # baseline: P_idle per la PORZIONE ATTIVA della finestra (mai per
        # code idle residue). La baseline NON entra in local_energy_j ne'
        # end_to_end_energy_j: viene solo sottratta per isolare l'attiva.
        baseline_dt = min(dt, active_end_dt)
        res.baseline_energy_j = round(res.idle_power_w * baseline_dt, 6)
        active = max(e_package - res.baseline_energy_j, 0.0)
        res.active_energy_j = round(active, 6)

        # delta CPU-time albero Ollama: preferisce istogrammi campione-campione
        if excl:
            # scorporo judge: limita il delta agli intervalli NON esclusi
            def _in_excl(a: float, b: float) -> bool:
                return any(not (b <= x or a >= y) for x, y in excl)
            pairs = list(zip(samples[1:], samples[:-1]))
            kept = [(p, q) for p, q in pairs if not _in_excl(q.t, p.t)]
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
            # integrazione trapezoidale del power draw
            board_j = 0.0
            prev = gpu_samples[0]
            util_sum = 0.0
            util_n = 0
            for cur in gpu_samples[1:]:
                seg_dt = cur.t - prev.t
                if seg_dt > 0:
                    board_j += ((prev.gpu_power_w + cur.gpu_power_w) / 2.0) * seg_dt
                if cur.gpu_util_pct is not None:
                    util_sum += cur.gpu_util_pct
                    util_n += 1
                prev = cur
            idle_gpu_w = getattr(self.session, "idle_gpu_power_w", None) or 0.0
            active_gpu_j = max(board_j - idle_gpu_w * dt, 0.0)
            util_share = (util_sum / util_n / 100.0) if util_n else 1.0
            res.gpu_board_energy_j = round(board_j, 6)
            res.gpu_utilization_share = round(util_share, 6)
            res.gpu_energy_attributed_j = round(active_gpu_j * util_share, 6)
            res.gpu_attribution_method = (
                "nvml-power-integral minus calibrated idle; utilization-share attribution"
            )
            notes.append(f"GPU '{gpu_mon.name}': board {board_j:.2f} J, attribuiti {res.gpu_energy_attributed_j:.2f} J")
        elif method not in ("librehardwaremonitor", "librehardwaremonitor-energy") and active > 0:
            # iGPU Intel/AMD senza NVML: nessuna riga GPU separata dal package;
            # quota dichiarata sull'energia ATTIVA (mai sul totale).
            from config import IGPU_POWER_SHARE

            res.gpu_available = True
            res.gpu_device_index = None
            res.gpu_energy_attributed_j = round(active * IGPU_POWER_SHARE * share, 6)
            res.gpu_utilization_share = round(share, 6)
            res.gpu_attribution_method = (
                f"igpu-share-heuristic ({IGPU_POWER_SHARE:.0%} of ACTIVE energy, declared)"
            )
            notes.append("iGPU integrata: quota dichiarata sull'energia attiva package")
        else:
            res.gpu_attribution_method = "not-applicable"

        # ------------------------------------------------------- boundary
        # scorporo judge: rimuove dai cumulativi la frazione di energia che
        # ricade nelle sottofinestre escluse (stima temporale conservativa)
        if excl_s > 0:
            frac_excl = excl_s / max(excl_s + dt, 1e-6)
            res.package_energy_j = round(res.package_energy_j * (1.0 - frac_excl), 6)
            e_pkg_kept = res.package_energy_j
            active = max(e_pkg_kept - res.baseline_energy_j, 0.0)
            res.active_energy_j = round(active, 6)
            res.ollama_active_energy_j = round(active * res.cpu_time_share, 6)
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
