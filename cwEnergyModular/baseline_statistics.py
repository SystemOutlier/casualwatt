# -*- coding: utf-8 -*-
"""Primitivo comune di analisi statistica della baseline.

Modulo di sola analisi (come `surface_fit.py`, `geometry.py`, `control_gate.py`),
non di acquisizione: riceve le potenze delle finestre come input e restituisce
le statistiche calcolate. L'acquisizione resta responsabilita' di `EnergySession`
e del gate P4.4.

La dataclass `BaselineStatistics` e' immutabile (`frozen=True`) per garantire
che le statistiche una volta calcolate non siano modificate — coerente con la
regola "nessun troncamento" e con l'onestà metrologica.

Vocabolario chiuso per `stability_status`:
- `stable`: CV ≤ soglia, ≥ 2 finestre valide
- `unstable`: CV > soglia
- `insufficient_data`: < 2 finestre o media = 0
- `not_evaluated`: lista vuota

Le formule sono:
- CV = (std_campione / media) × 100, dove std_campione usa n-1 (Bessel)
- IQR = Q3 - Q1 (percentili al 25° e 75°)
- Mediana: valore centrale dopo ordinamento
- Deviazione standard campione: sqrt(sum((x - mean)^2) / (n - 1))
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from statistics import median as _median
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class BaselineStatistics:
    """Statistiche complete della baseline idle, immutabili dopo il calcolo.

    Campi:
        window_count: numero di finestre valide usate per il calcolo.
        power_mean_w: media aritmetica delle potenze [W].
        power_std_w: deviazione standard campione (n-1, Bessel) [W].
        cv_pct: coefficiente di variazione in percentuale,
            CV = (power_std_w / power_mean_w) × 100.
        power_median_w: mediana delle potenze [W].
        power_iqr_w: dispersione interquartile Q3 - Q1 [W].
        duration_s: durata complessiva, somma dei dt delle finestre [s].
        cpu_utilization_avg: utilizzo CPU medio sulle stesse finestre temporali,
            o None se non misurato.
        stability_status: uno dei quattro token chiusi:
            `stable`, `unstable`, `insufficient_data`, `not_evaluated`.
        notes: dichiarazioni diagnostiche (es. finestre scartate, ragioni).
    """

    window_count: int
    power_mean_w: float
    power_std_w: float
    cv_pct: float
    power_median_w: float
    power_iqr_w: float
    duration_s: float
    cpu_utilization_avg: Optional[float]
    stability_status: str
    notes: List[str] = field(default_factory=list)

    # -- factory methods -----------------------------------------------------

    @classmethod
    def from_power_windows(
        cls,
        powers: List[Tuple[float, float]],
        cpu_samples: Optional[List[Tuple[float, float]]] = None,
        cv_max_pct: float = 10.0,
    ) -> BaselineStatistics:
        """Calcola tutte le statistiche da finestre con potenza e durata.

        Input:
            powers: lista di tuple (power_w, dt_s). Le finestre con dt ≤ 0
                o potenza negativa vengono scartate con dichiarazione.
            cpu_samples: opzionale, lista di tuple (cpu_pct, dt_s) per calcolare
                l'utilizzo CPU medio sulle stesse finestre temporali.
            cv_max_pct: soglia massima del CV per considerare la baseline stabile
                (default 10%, coerente con la regola "soglie congelate prima
                dei dati").

        Restituisce:
            Istanza immutabile di BaselineStatistics con tutte le metriche
            calcolate e lo stability_status valutato.
        """
        notes: List[str] = []

        # Filtra finestre non valide, inclusi valori non finiti
        valid_powers: List[Tuple[float, float]] = []
        for power_w, dt_s in powers:
            if not _is_finite(power_w):
                notes.append(f"finestra scartata: potenza non finita ({power_w})")
                continue
            if not _is_finite(dt_s):
                notes.append(f"finestra scartata: dt non finito ({dt_s})")
                continue
            if dt_s <= 0:
                notes.append(f"finestra scartata: dt={dt_s:.3f} s ≤ 0")
                continue
            if power_w < 0:
                notes.append(f"finestra scartata: potenza negativa ({power_w:.3f} W)")
                continue
            valid_powers.append((power_w, dt_s))

        if not valid_powers:
            return cls(
                window_count=0,
                power_mean_w=0.0,
                power_std_w=0.0,
                cv_pct=0.0,
                power_median_w=0.0,
                power_iqr_w=0.0,
                duration_s=0.0,
                cpu_utilization_avg=None,
                stability_status="not_evaluated",
                notes=notes or ["nessuna finestra valida"],
            )

        power_values = [p for p, _ in valid_powers]
        durations = [dt for _, dt in valid_powers]
        window_count = len(power_values)
        duration_s = sum(durations)

        # Media
        power_mean_w = sum(power_values) / window_count

        # Se la media è zero, il CV non è calcolabile
        if power_mean_w == 0.0:
            return cls(
                window_count=window_count,
                power_mean_w=0.0,
                power_std_w=0.0,
                cv_pct=0.0,
                power_median_w=0.0,
                power_iqr_w=0.0,
                duration_s=duration_s,
                cpu_utilization_avg=None,
                stability_status="insufficient_data",
                notes=notes + ["media delle potenze = 0 W: CV non calcolabile"],
            )

        # Deviazione standard campione (n-1, Bessel)
        if window_count < 2:
            power_std_w = 0.0
        else:
            variance = sum((p - power_mean_w) ** 2 for p in power_values) / (window_count - 1)
            power_std_w = math.sqrt(variance)

        # CV in percentuale
        cv_pct = (power_std_w / power_mean_w) * 100.0

        # Mediana
        power_median_w = _median(power_values)

        # IQR (Q3 - Q1)
        power_iqr_w = _compute_iqr(power_values)

        # CPU utilization medio (pesato per durata, se disponibile)
        cpu_utilization_avg: Optional[float] = None
        if cpu_samples:
            valid_cpu = [
                (cpu_pct, dt_s)
                for cpu_pct, dt_s in cpu_samples
                if dt_s > 0
            ]
            if valid_cpu:
                total_cpu_weighted = sum(cpu_pct * dt_s for cpu_pct, dt_s in valid_cpu)
                total_cpu_duration = sum(dt_s for _, dt_s in valid_cpu)
                if total_cpu_duration > 0:
                    cpu_utilization_avg = total_cpu_weighted / total_cpu_duration

        # Valuta stabilità
        stability_status = _evaluate_stability(
            window_count=window_count,
            cv_pct=cv_pct,
            cv_max_pct=cv_max_pct,
            power_mean_w=power_mean_w,
        )

        return cls(
            window_count=window_count,
            power_mean_w=round(power_mean_w, 4),
            power_std_w=round(power_std_w, 4),
            cv_pct=round(cv_pct, 4),
            power_median_w=round(power_median_w, 4),
            power_iqr_w=round(power_iqr_w, 4),
            duration_s=round(duration_s, 4),
            cpu_utilization_avg=round(cpu_utilization_avg, 4) if cpu_utilization_avg is not None else None,
            stability_status=stability_status,
            notes=notes,
        )

    @classmethod
    def from_single_values(
        cls,
        powers: List[float],
        cv_max_pct: float = 10.0,
    ) -> BaselineStatistics:
        """Calcola le statistiche da potenze senza durata.

        Usato quando i dt non sono disponibili, ad esempio da `_idle_reps`
        di `EnergySession` o dai valori grezzi del gate P4.4.

        Input:
            powers: lista di potenze [W]. I valori negativi vengono scartati.
            cv_max_pct: soglia massima del CV (default 10%).

        Restituisce:
            Istanza immutabile di BaselineStatistics con duration_s = 0.
        """
        notes: List[str] = []

        # Filtra potenze non finite e negative
        valid_powers = [p for p in powers if _is_finite(p) and p >= 0]
        if len(valid_powers) != len(powers):
            notes.append(f"{len(powers) - len(valid_powers)} potenza(e) non finita(e) o negativa(e) scartata(e)")

        if not valid_powers:
            return cls(
                window_count=0,
                power_mean_w=0.0,
                power_std_w=0.0,
                cv_pct=0.0,
                power_median_w=0.0,
                power_iqr_w=0.0,
                duration_s=0.0,
                cpu_utilization_avg=None,
                stability_status="not_evaluated",
                notes=notes or ["nessuna potenza valida"],
            )

        window_count = len(valid_powers)
        power_mean_w = sum(valid_powers) / window_count

        if power_mean_w == 0.0:
            return cls(
                window_count=window_count,
                power_mean_w=0.0,
                power_std_w=0.0,
                cv_pct=0.0,
                power_median_w=0.0,
                power_iqr_w=0.0,
                duration_s=0.0,
                cpu_utilization_avg=None,
                stability_status="insufficient_data",
                notes=notes + ["media delle potenze = 0 W: CV non calcolabile"],
            )

        # Deviazione standard campione (n-1, Bessel)
        if window_count < 2:
            power_std_w = 0.0
        else:
            variance = sum((p - power_mean_w) ** 2 for p in valid_powers) / (window_count - 1)
            power_std_w = math.sqrt(variance)

        cv_pct = (power_std_w / power_mean_w) * 100.0
        power_median_w = _median(valid_powers)
        power_iqr_w = _compute_iqr(valid_powers)

        stability_status = _evaluate_stability(
            window_count=window_count,
            cv_pct=cv_pct,
            cv_max_pct=cv_max_pct,
            power_mean_w=power_mean_w,
        )

        return cls(
            window_count=window_count,
            power_mean_w=round(power_mean_w, 4),
            power_std_w=round(power_std_w, 4),
            cv_pct=round(cv_pct, 4),
            power_median_w=round(power_median_w, 4),
            power_iqr_w=round(power_iqr_w, 4),
            duration_s=0.0,
            cpu_utilization_avg=None,
            stability_status=stability_status,
            notes=notes,
        )

    # -- serializzazione -----------------------------------------------------

    def to_json(self) -> str:
        """Serializza in JSON compatto per il campo `notes` del runner.

        Il formato e' una stringa JSON con chiave strutturata per facilitare
        l'estrazione: `baseline_stats:{...}`.
        """
        data = {
            "window_count": self.window_count,
            "power_mean_w": self.power_mean_w,
            "power_std_w": self.power_std_w,
            "cv_pct": self.cv_pct,
            "power_median_w": self.power_median_w,
            "power_iqr_w": self.power_iqr_w,
            "duration_s": self.duration_s,
            "cpu_utilization_avg": self.cpu_utilization_avg,
            "stability_status": self.stability_status,
        }
        if self.notes:
            data["notes"] = self.notes
        return "baseline_stats:" + json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_json(cls, json_str: str) -> Optional[BaselineStatistics]:
        """Deserializza da una stringa JSON prodotta da `to_json()`.

        Restituisce None se la stringa non inizia con `baseline_stats:`.
        """
        if not json_str.startswith("baseline_stats:"):
            return None
        data = json.loads(json_str[len("baseline_stats:"):])
        return cls(
            window_count=data["window_count"],
            power_mean_w=data["power_mean_w"],
            power_std_w=data["power_std_w"],
            cv_pct=data["cv_pct"],
            power_median_w=data["power_median_w"],
            power_iqr_w=data["power_iqr_w"],
            duration_s=data["duration_s"],
            cpu_utilization_avg=data.get("cpu_utilization_avg"),
            stability_status=data["stability_status"],
            notes=data.get("notes", []),
        )


# -- funzioni helper ---------------------------------------------------------

def _is_finite(value) -> bool:
    """Verifica che un valore sia un numero finito (non NaN, non inf)."""
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _compute_iqr(values: List[float]) -> float:
    """Calcola l'IQR (Q3 - Q1) usando il metodo dei quartili.

    Q1 = mediana della prima meta' dei dati ordinati.
    Q3 = mediana della seconda meta' dei dati ordinati.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n < 2:
        return 0.0

    # Q1: mediana della prima meta'
    q1_idx = n // 4
    if n % 4 == 0:
        q1 = (sorted_vals[q1_idx - 1] + sorted_vals[q1_idx]) / 2.0
    else:
        q1 = sorted_vals[q1_idx]

    # Q3: mediana della seconda meta'
    q3_idx = 3 * n // 4
    if n % 4 == 0:
        q3 = (sorted_vals[q3_idx - 1] + sorted_vals[q3_idx]) / 2.0
    else:
        q3 = sorted_vals[q3_idx]

    return q3 - q1


def _evaluate_stability(
    window_count: int,
    cv_pct: float,
    cv_max_pct: float,
    power_mean_w: float,
) -> str:
    """Valuta lo status di stabilità della baseline.

    Vocabolario chiuso:
        - `stable`: CV ≤ soglia, ≥ 2 finestre, media > 0
        - `unstable`: CV > soglia
        - `insufficient_data`: < 2 finestre o media = 0
        - `not_evaluated`: lista vuota (gestito prima di questa funzione)

    La soglia CV e' parametrizzabile (default 10%), coerente con la regola
    "soglie congelate prima dei dati".
    """
    if window_count == 0:
        return "not_evaluated"
    if window_count < 2 or power_mean_w == 0.0:
        return "insufficient_data"
    if cv_pct > cv_max_pct:
        return "unstable"
    return "stable"


def iqr_filter(values: List[float], k: float = 1.5) -> List[float]:
    """Filtro IQR condiviso per rimuovere outlier.

    Rimuove i valori al di fuori di [Q1 - k*IQR, Q3 + k*IQR].
    Se IQR = 0, non rimuove nulla (tutti i valori sono uguali o quasi).

    Input:
        values: lista di valori numerici.
        k: moltiplicatore IQR (default 1.5, coerente con boxplot standard).

    Restituisce:
        Lista filtrata senza outlier.
    """
    if len(values) < 2:
        return list(values)

    sorted_vals = sorted(values)
    n = len(sorted_vals)

    # Q1
    q1_idx = n // 4
    if n % 4 == 0:
        q1 = (sorted_vals[q1_idx - 1] + sorted_vals[q1_idx]) / 2.0
    else:
        q1 = sorted_vals[q1_idx]

    # Q3
    q3_idx = 3 * n // 4
    if n % 4 == 0:
        q3 = (sorted_vals[q3_idx - 1] + sorted_vals[q3_idx]) / 2.0
    else:
        q3 = sorted_vals[q3_idx]

    iqr = q3 - q1
    if iqr <= 0.0:
        return list(values)

    lower = q1 - k * iqr
    upper = q3 + k * iqr
    return [v for v in values if lower <= v <= upper]
