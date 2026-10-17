# -*- coding: utf-8 -*-
"""
energy/network_energy.py — Stima energia di trasmissione (sezione 9/12.2).

Misura il delta dei contatori NIC del client durante la finestra della
richiesta cloud e converte i bit in Joule con un coefficiente dichiarato
in ``config.NETWORK_ENERGY_COEFFICIENT_J_PER_BIT``.

Confine di misura: client-side NIC counters (psutil.net_io_counters),
system-wide nella finestra; il traffico degli altri processi concorrenti
viene dichiarato come rumore nelle note. Non viene stimata l'energia dei
router intermedi ne' quella della NIC lato datacenter.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List, Optional

import psutil

try:
    from config import NETWORK_ENERGY_COEFFICIENT_J_PER_BIT
except Exception:  # pragma: no cover
    NETWORK_ENERGY_COEFFICIENT_J_PER_BIT = 3.4e-8


@dataclass
class NetworkEnergyResult:
    duration_s: float = 0.0
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0
    energy_j: float = 0.0
    coefficient_j_per_bit: float = NETWORK_ENERGY_COEFFICIENT_J_PER_BIT
    measurement_boundary: str = ""
    notes: List[str] = field(default_factory=list)


class NetworkEnergyTracker:
    """Delta NIC tra due istanti -> byte e stima J."""

    @staticmethod
    def _read() -> Optional[int]:
        try:
            pernic = psutil.net_io_counters(pernic=True)
            sent = recv = 0
            for nic, c in pernic.items():
                # esclude interfacce loopback/virtuali ovvie
                low = nic.lower()
                if "lo" == low or "loopback" in low:
                    continue
                sent += c.bytes_sent
                recv += c.bytes_recv
            return sent, recv
        except Exception:
            try:
                c = psutil.net_io_counters()
                return int(c.bytes_sent), int(c.bytes_recv)
            except Exception:
                return None

    def measure(self, fn, *args, **kwargs):
        """Esegue ``fn`` e misura il traffico generato. (esito, net_result)."""
        before = self._read()
        t0 = time.monotonic()
        outcome = fn(*args, **kwargs)
        t1 = time.monotonic()
        after = self._read()

        res = NetworkEnergyResult(duration_s=max(t1 - t0, 1e-6))
        if before is None or after is None:
            res.notes.append("contatori NIC non leggibili: energia rete = 0 (dichiarato)")
            res.measurement_boundary = "client-NIC counters unavailable"
            return outcome, res

        up = max(after[0] - before[0], 0)
        down = max(after[1] - before[1], 0)
        res.upload_bytes = int(up)
        res.download_bytes = int(down)
        res.total_bytes = int(up + down)
        bits = res.total_bytes * 8
        res.energy_j = round(bits * res.coefficient_j_per_bit, 9)
        res.measurement_boundary = (
            "client-side NIC delta over request window; coefficient "
            f"{res.coefficient_j_per_bit:.1e} J/bit (declared access-network model); "
            "excludes intermediate routers and datacenter-side NIC"
        )
        if res.total_bytes < 512:
            res.notes.append("traffico quasi nullo nella finestra: possibile proxy/cache")
        return outcome, res

    def measure_window(self, t_start: float, t_end: float,
                       up_bytes: int, down_bytes: int) -> NetworkEnergyResult:
        """Costruisce un risultato da byte gia' noti (es. payload HTTP)."""
        res = NetworkEnergyResult(
            duration_s=max(t_end - t_start, 1e-6),
            upload_bytes=int(max(up_bytes, 0)),
            download_bytes=int(max(down_bytes, 0)),
        )
        res.total_bytes = res.upload_bytes + res.download_bytes
        res.energy_j = round(res.total_bytes * 8 * res.coefficient_j_per_bit, 9)
        res.measurement_boundary = (
            "HTTP payload accounting (request+response bodies) at client socket "
            f"level; coefficient {res.coefficient_j_per_bit:.1e} J/bit (declared)"
        )
        return res
