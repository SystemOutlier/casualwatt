# -*- coding: utf-8 -*-
"""
energy/rapl_backend.py — Backend Linux per CasualWatt via contatori RAPL.

Questo modulo legge l'energia del package CPU direttamente dai contatori
hardware RAPL (Running Average Power Limit) esposti dal kernel Linux in
/sys/class/powercap/intel-rapl/.

RAPL fornisce misurazioni energetiche REALI (non stime TDP) con risoluzione
di ~61 microjoule (energy_status_unit). Il contatore energy_uj è cumulativo
e wraps around quando raggiunge max_energy_range_uj (tipicamente ~2^32 uJ).

Requisiti:
  - Linux con kernel >= 3.13 (CONFIG_INTEL_RAPL)
  - CPU Intel con supporto RAPL (Sandy Bridge o successivo)
  - Permessi di lettura su /sys/class/powercap/ (root o gruppo 'power')

Riferimenti:
  - Intel SDM Vol. 3, Cap. 14.9 "RUNNING AVERAGE POWER LIMIT (RAPL)"
  - Linux kernel Documentation/powercap/powercap.txt
  - Hähnel et al. "A Fresh Look on the Intel Running Average Power Limit"
    (SIGMETRICS PER 2012) — validazione accuracy RAPL
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List, Optional


class RAPLBackend:
    """Backend Linux per lettura energia package CPU via contatori RAPL.

    Legge il file energy_uj esposto da powercap per il package CPU (dominio
    intel-rapl:0). Il contatore è cumulativo in microjoule e wraps around
    quando raggiunge max_energy_range_uj.

    Attributi:
        available (bool): True se il backend può essere inizializzato.
        method (str): Identificativo del metodo ("rapl").
        notes (List[str]): Note diagnostiche.
    """

    RAPL_PATH = Path("/sys/class/powercap/intel-rapl/intel-rapl:0")
    ENERGY_FILE = RAPL_PATH / "energy_uj"
    MAX_ENERGY_FILE = RAPL_PATH / "max_energy_range_uj"
    NAME_FILE = RAPL_PATH / "name"

    def __init__(self) -> None:
        self.method = "unavailable"
        self.available = False
        self.notes: List[str] = []
        self._base_energy_uj: Optional[int] = None
        self._last_energy_uj: Optional[int] = None
        self._wrap_count: int = 0
        self._max_energy_uj: Optional[int] = None
        self._last_read_time: Optional[float] = None

        if not self._check_access():
            self.notes.append(
                f"RAPL non accessibile: {self.ENERGY_FILE} non esiste o "
                "permessi insufficienti (richiede root o gruppo 'power')"
            )
            return

        try:
            self._max_energy_uj = self._read_max_energy()
            self._base_energy_uj = self._read_energy_uj()
            self._last_energy_uj = self._base_energy_uj
            self._last_read_time = time.monotonic()
            self.method = "rapl"
            self.available = True
            self.notes.append(
                f"RAPL attivo: lettura da {self.ENERGY_FILE}, "
                f"max_energy_range={self._max_energy_uj / 1e6:.3f} J"
            )
        except Exception as exc:
            self.notes.append(f"RAPL inizializzazione fallita: {exc}")

    def _check_access(self) -> bool:
        """Verifica che il file energy_uj esista e sia leggibile."""
        return self.ENERGY_FILE.exists() and os.access(self.ENERGY_FILE, os.R_OK)

    def _read_energy_uj(self) -> int:
        """Legge il contatore energy_uj (microjoule cumulativi)."""
        with open(self.ENERGY_FILE, "r") as f:
            return int(f.read().strip())

    def _read_max_energy(self) -> int:
        """Legge max_energy_range_uj (soglia di wrap-around)."""
        if self.MAX_ENERGY_FILE.exists():
            with open(self.MAX_ENERGY_FILE, "r") as f:
                return int(f.read().strip())
        # Fallback: 2^32 uJ (~4295 J) tipico su Intel
        return 2**32

    def _read_name(self) -> str:
        """Legge il nome del dominio RAPL (es. 'package-0')."""
        if self.NAME_FILE.exists():
            with open(self.NAME_FILE, "r") as f:
                return f.read().strip()
        return "package-0"

    def read_cumulative_energy_j(self) -> Optional[float]:
        """Legge energia cumulata dal package CPU in Joule.

        Gestisce il wrap-around del contatore: se il valore letto è minore
        dell'ultimo valore, si incrementa _wrap_count e si aggiunge
        max_energy_uj al totale.

        Returns:
            Energia cumulata in Joule dalla prima lettura, oppure None se
            il backend non è disponibile.
        """
        if not self.available:
            return None

        try:
            current_uj = self._read_energy_uj()
            current_time = time.monotonic()

            # Rileva wrap-around
            if self._last_energy_uj is not None and current_uj < self._last_energy_uj:
                self._wrap_count += 1
                self.notes.append(
                    f"RAPL wrap-around rilevato (count={self._wrap_count}): "
                    f"{self._last_energy_uj} -> {current_uj}"
                )

            # Energia totale cumulata (base + wraps + delta corrente)
            total_uj = (
                (self._wrap_count * self._max_energy_uj)
                + (current_uj - self._base_energy_uj)
            )
            total_j = total_uj / 1e6

            self._last_energy_uj = current_uj
            self._last_read_time = current_time

            return total_j

        except Exception as exc:
            self.notes.append(f"RAPL lettura fallita: {exc}")
            return None

    def read_power_w(self) -> Optional[float]:
        """Legge potenza istantanea del package CPU in Watt.

        Calcola la potenza come delta_energia / delta_tempo tra due letture
        consecutive. La prima chiamata ritorna None (non c'è un delta).

        Returns:
            Potenza in Watt, oppure None se è la prima lettura o il backend
            non è disponibile.
        """
        if not self.available:
            return None

        try:
            current_uj = self._read_energy_uj()
            current_time = time.monotonic()

            if self._last_energy_uj is None or self._last_read_time is None:
                # Prima lettura: salva e ritorna None
                self._last_energy_uj = current_uj
                self._last_read_time = current_time
                return None

            # Gestisci wrap-around
            if current_uj < self._last_energy_uj:
                delta_uj = (self._max_energy_uj - self._last_energy_uj) + current_uj
            else:
                delta_uj = current_uj - self._last_energy_uj

            delta_time = current_time - self._last_read_time
            if delta_time <= 0:
                return None

            power_w = (delta_uj / 1e6) / delta_time

            self._last_energy_uj = current_uj
            self._last_read_time = current_time

            return power_w

        except Exception as exc:
            self.notes.append(f"RAPL lettura potenza fallita: {exc}")
            return None

    def read_idle_window_j(self, duration_s: float) -> Optional[tuple]:
        """Misura energia su finestra idle di ``duration_s`` secondi.

        Ritorna (delta_j, dt_real, mode) dove:
          - delta_j: energia consumata nella finestra [J]
          - dt_real: durata reale della finestra [s]
          - mode: "rapl-counter" (sempre, per coerenza con altri backend)

        Returns:
            Tupla (delta_j, dt_real, mode) oppure None se il backend non
            è disponibile.
        """
        if not self.available:
            return None

        try:
            e_start = self.read_cumulative_energy_j()
            if e_start is None:
                return None

            t0 = time.monotonic()
            time.sleep(duration_s)
            dt = time.monotonic() - t0

            e_end = self.read_cumulative_energy_j()
            if e_end is None:
                return None

            delta_j = e_end - e_start
            return (delta_j, dt, "rapl-counter")

        except Exception as exc:
            self.notes.append(f"RAPL idle window fallita: {exc}")
            return None

    def diagnose(self) -> dict:
        """Ritorna diagnostica del backend RAPL.

        Returns:
            Dict con chiavi: available, method, path, max_energy_uj,
            wrap_count, notes.
        """
        return {
            "available": self.available,
            "method": self.method,
            "path": str(self.ENERGY_FILE),
            "max_energy_uj": self._max_energy_uj,
            "wrap_count": self._wrap_count,
            "notes": list(self.notes),
        }
