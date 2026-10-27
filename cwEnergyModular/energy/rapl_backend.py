# -*- coding: utf-8 -*-
"""
energy/rapl_backend.py — Backend Linux per CasualWatt via contatori RAPL.

Questo modulo legge l'energia del package CPU dai contatori hardware RAPL
(Running Average Power Limit) esposti dal kernel Linux in
``/sys/class/powercap/``.

RAPL fornisce misurazioni energetiche REALI (non stime TDP): il file
``energy_uj`` di ogni zona e' un contatore cumulativo in microjoule che
riparte da zero quando raggiunge ``max_energy_range_uj``.

**Le zone si enumerano, non si indovinano.** Il percorso non e' cablato su
``intel-rapl:0``: si elencano le zone sotto la radice, si legge ``name`` per
ciascuna e si selezionano le zone il cui nome comincia con ``package-``. Le
altre (``psys``, ``dram``, ``core``, ...) sono domini diversi e non vengono
sommate al package. Le zone con lo stesso nome sono canali specchiati dello
stesso contatore e si contano una volta sola. E' il difetto F11 della
specifica (``experiment_results/metodi_per_dominio_20261025_spec.md``, §3.1
voce R1).

Riporto del contatore: se il valore decresce e ``max_energy_range_uj`` e'
leggibile, l'incremento e' ``max - precedente + corrente``. Se il massimo non
e' leggibile, il riporto **non e' determinabile**: la lettura restituisce
``None`` con la ragione, invece di assumere ``2**32`` uJ.

Requisiti:
  - Linux con il framework powercap (Intel RAPL, oppure AMD sui kernel che lo
    espongono);
  - permessi di lettura sui nodi ``energy_uj`` (root, oppure permessi concessi
    esplicitamente sul nodo: alcuni driver limitano la visibilita' dopo
    CVE-2020-12912).

Riferimenti:
  - Linux kernel, Documentation/power/powercap/powercap.rst (energy_uj,
    max_energy_range_uj);
  - Intel SDM Vol. 3, "Running Average Power Limit (RAPL)";
  - Hahnel et al., "A Fresh Look on the Intel Running Average Power Limit",
    SIGMETRICS PER 2012 (accuratezza RAPL).
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Dict, List, Optional


class _Unreliable(Exception):
    """Lettura che non si puo' usare senza inventare un numero."""


class _Zone:
    """Stato di una zona powercap selezionata (una per package distinto)."""

    __slots__ = ("name", "path", "max_uj", "base_uj", "last_uj", "wraps",
                 "last_time")

    def __init__(self, name: str, path: Path, max_uj: Optional[int],
                 base_uj: int) -> None:
        self.name = name
        self.path = path
        self.max_uj = max_uj
        self.base_uj = base_uj
        self.last_uj = base_uj
        self.wraps = 0
        self.last_time = time.monotonic()


class RAPLBackend:
    """Backend Linux per lettura energia package CPU via contatori RAPL.

    Attributi:
        available (bool): True se almeno una zona package e' leggibile.
        method (str): Identificativo del metodo ("rapl" o "unavailable").
        notes (List[str]): Note diagnostiche, incluse le zone scartate.
    """

    #: Radice del framework powercap. Sovrascrivibile nei test con una
    #: directory temporanea: la selezione delle zone e' logica pura sul
    #: filesystem, non richiede un host Linux.
    POWERCAP_ROOT = Path("/sys/class/powercap")

    #: Prefisso del nome delle zone che rappresentano il package CPU.
    PACKAGE_PREFIX = "package-"

    def __init__(self, root: Optional[Path] = None) -> None:
        self.method = "unavailable"
        self.available = False
        self.notes: List[str] = []
        self._root = Path(root) if root is not None else self.POWERCAP_ROOT
        self._zones: List[_Zone] = []
        self._skipped: List[str] = []

        zones = self._discover()
        if not zones:
            if self._skipped:
                self.notes.append(
                    "RAPL senza zona package: zone leggibili = "
                    + ", ".join(self._skipped)
                    + " (domini diversi dal package, non sommati)"
                )
            elif not self.notes:
                self.notes.append(
                    f"RAPL non accessibile: nessuna zona '{self.PACKAGE_PREFIX}*' "
                    f"leggibile sotto {self._root} (servono root o permessi di "
                    "lettura concessi esplicitamente sui nodi energy_uj)"
                )
            return

        self._zones = zones
        self.method = "rapl"
        self.available = True
        self.notes.append(
            "RAPL attivo: zone package = " + ", ".join(z.name for z in zones)
            + (f"; zone scartate per dominio: {', '.join(self._skipped)}"
               if self._skipped else "")
        )

    # -- scoperta delle zone ------------------------------------------------
    @staticmethod
    def _read_text(path: Path) -> Optional[str]:
        try:
            return path.read_text().strip()
        except OSError:
            return None

    def _discover(self) -> List[_Zone]:
        """Elenca le zone package leggibili, deduplicando i canali specchiati."""
        try:
            entries = sorted(Path(self._root).iterdir())
        except OSError as exc:
            self.notes.append(
                f"RAPL non accessibile: {self._root} non enumerabile "
                f"({type(exc).__name__})"
            )
            return []

        zones: List[_Zone] = []
        seen: Dict[str, str] = {}
        for entry in entries:
            try:
                if not entry.is_dir():
                    continue
            except OSError:
                continue
            energy = entry / "energy_uj"
            if not energy.exists() or not os.access(energy, os.R_OK):
                continue
            name = self._read_text(entry / "name") or entry.name
            if not name.startswith(self.PACKAGE_PREFIX):
                self._skipped.append(f"{name} ({entry.name})")
                continue
            if name in seen:
                self.notes.append(
                    f"canale specchiato ignorato: {entry.name} dichiara "
                    f"'{name}' come {seen[name]} (stesso contatore, nessuna somma)"
                )
                continue
            try:
                base_uj = self._read_uj(energy)
            except (OSError, ValueError) as exc:
                self.notes.append(
                    f"zona {name} scartata: energy_uj non leggibile "
                    f"({type(exc).__name__})"
                )
                continue
            max_path = entry / "max_energy_range_uj"
            max_uj = None
            raw_max = self._read_text(max_path) if max_path.exists() else None
            if raw_max is not None:
                try:
                    max_uj = int(raw_max)
                except ValueError:
                    max_uj = None
            if max_uj is None:
                self.notes.append(
                    f"zona {name}: max_energy_range_uj assente o illeggibile; "
                    "un riporto del contatore non sara' ricostruibile"
                )
            seen[name] = entry.name
            zones.append(_Zone(name, entry, max_uj, base_uj))
        return zones

    @staticmethod
    def _read_uj(path: Path) -> int:
        return int(Path(path).read_text().strip())

    # -- letture ------------------------------------------------------------
    def _zone_cumulative_j(self, zone: _Zone) -> float:
        """Energia cumulata di una zona in J, con riporto o errore dichiarato."""
        current = self._read_uj(zone.path / "energy_uj")
        if current < zone.last_uj:
            if zone.max_uj is None:
                raise _Unreliable(
                    f"contatore {zone.name} decresciuto "
                    f"({zone.last_uj} -> {current} uJ) e max_energy_range_uj "
                    "non leggibile: riporto non determinabile"
                )
            zone.wraps += 1
            self.notes.append(
                f"riporto contatore {zone.name} (count={zone.wraps}): "
                f"{zone.last_uj} -> {current} uJ"
            )
        zone.last_uj = current
        total_uj = zone.wraps * (zone.max_uj or 0) + (current - zone.base_uj)
        return total_uj / 1e6

    def read_cumulative_energy_j(self) -> Optional[float]:
        """Energia cumulata del package dalla prima lettura, in Joule.

        Somma le zone package distinte. Se una zona non e' leggibile in modo
        affidabile restituisce ``None``: una somma parziale sarebbe un numero
        che sembra una misura e non lo e'.

        Returns:
            Energia cumulata in Joule, oppure None.
        """
        if not self.available:
            return None
        try:
            return sum(self._zone_cumulative_j(z) for z in self._zones)
        except _Unreliable as exc:
            self.notes.append(f"RAPL lettura non affidabile: {exc}")
            return None
        except (OSError, ValueError) as exc:
            self.notes.append(f"RAPL lettura fallita: {type(exc).__name__}")
            return None

    def read_power_w(self) -> Optional[float]:
        """Potenza istantanea del package in Watt.

        E' delta_energia / delta_tempo fra due letture consecutive, sommato
        sulle zone package. La base temporale e' fissata all'inizializzazione:
        la prima chiamata misura il delta da quella base.

        Returns:
            Potenza in Watt, oppure None se il contatore non e' affidabile.
        """
        if not self.available:
            return None
        try:
            total_w = 0.0
            for zone in self._zones:
                current = self._read_uj(zone.path / "energy_uj")
                now = time.monotonic()
                if current < zone.last_uj:
                    if zone.max_uj is None:
                        raise _Unreliable(
                            f"contatore {zone.name} decresciuto e "
                            "max_energy_range_uj non leggibile"
                        )
                    delta_uj = (zone.max_uj - zone.last_uj) + current
                else:
                    delta_uj = current - zone.last_uj
                dt = now - zone.last_time
                if dt <= 0:
                    return None
                total_w += (delta_uj / 1e6) / dt
                zone.last_uj = current
                zone.last_time = now
            return total_w
        except _Unreliable as exc:
            self.notes.append(f"RAPL potenza non affidabile: {exc}")
            return None
        except (OSError, ValueError) as exc:
            self.notes.append(f"RAPL lettura potenza fallita: {type(exc).__name__}")
            return None

    def read_idle_window_j(self, duration_s: float) -> Optional[tuple]:
        """Misura energia su finestra idle di ``duration_s`` secondi.

        Ritorna (delta_j, dt_real, mode) dove:
          - delta_j: energia consumata nella finestra [J]
          - dt_real: durata reale della finestra [s]
          - mode: "rapl-counter" (sempre, per coerenza con altri backend)

        Returns:
            Tupla (delta_j, dt_real, mode) oppure None.
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

            return (e_end - e_start, dt, "rapl-counter")
        except Exception as exc:  # noqa: BLE001 - il chiamante vede None + nota
            self.notes.append(f"RAPL idle window fallita: {type(exc).__name__}")
            return None

    # -- diagnostica --------------------------------------------------------
    def diagnose(self) -> dict:
        """Ritorna diagnostica del backend RAPL.

        Returns:
            Dict con chiavi: available, method, path, max_energy_uj,
            wrap_count, zones, notes.
        """
        maxes = [z.max_uj for z in self._zones if z.max_uj is not None]
        return {
            "available": self.available,
            "method": self.method,
            "path": str(self._root),
            "max_energy_uj": max(maxes) if maxes else None,
            "wrap_count": sum(z.wraps for z in self._zones),
            "zones": [
                {
                    "name": z.name,
                    "path": str(z.path),
                    "max_energy_uj": z.max_uj,
                    "wraps": z.wraps,
                }
                for z in self._zones
            ],
            "notes": list(self.notes),
        }
