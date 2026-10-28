# -*- coding: utf-8 -*-
"""
energy/network_energy.py — Stima energia di rete (sezione 9/12.2).

Legge il delta dei contatori NIC del client (``psutil.net_io_counters`` con
``pernic=True``) fra inizio e fine della finestra della richiesta cloud e
moltiplica i bit per il coefficiente dichiarato in
``config.NETWORK_ENERGY_COEFFICIENT_J_PER_BIT``.

Cosa rappresenta il numero: un'intensita' di percorso applicata ai byte
osservati sul client, non l'energia della NIC del client e non la sola energia
di trasporto Internet. Il coefficiente (2,7 uJ/bit) e' la stima di modello di
Baliga, Ayre, Hinton e Tucker, "Green Cloud Computing: Balancing Energy in
Processing, Storage, and Transport", Proc. IEEE 99(1):149-167, 2011,
DOI 10.1109/JPROC.2010.2060451, eq. (2) p. 7, valore a p. 8, per trasmissione +
commutazione verso la rete di un cloud pubblico, con la rete di accesso
esclusa; i byte, invece, sono system-wide e contengono tutto il traffico della
macchina nella finestra, compreso quello di processi terzi, che non e'
separabile e resta nel delta.

Il coefficiente si puo' sostituire con ``CW_NET_J_PER_BIT``. In quel caso il
numero non e' piu' quello dell'articolo: e' un parametro dichiarato
dell'esperimento, e il confine della riga lo scrive
(``network_coefficient_provenance``) invece di attribuire a Baliga un valore che
non e' il suo. Citare la fonte sopra un coefficiente diverso sarebbe una
citazione inventata sopra un dato, e la riga non e' piu' confrontabile con una
che usa 2,7 uJ/bit.

Confini da non confondere:
  - byte: contatori del client, system-wide sulle interfacce sommate (per
    default le fisiche; virtuali e tunnel esclusi, con la ricaduta dichiarata
    descritta sotto; loopback escluso quando i contatori per interfaccia sono
    leggibili -- la lettura aggregata di ultima istanza non lo separa e lo
    dichiara nel confine). Il nome delle interfacce sommate compare nel campo
    ``interfaces`` e nel confine della riga;
  - energia per bit: percorso fino agli switch LAN del data center quale
    modellato dalla fonte, accesso escluso, server/storage/processing esclusi;
  - l'energia della NIC del client e quella della rete di accesso non sono
    contate da nessuno dei due lati.
Il campo ``measurement_boundary`` di ogni risultato dichiara il confine
applicato e la provenienza del coefficiente: con 2,7 uJ/bit cita Baliga et al.
2011, con un valore imposto da ``CW_NET_J_PER_BIT`` dice che il coefficiente e'
un parametro e non attribuisce la stima all'articolo.

Selezione delle interfacce (correzione del 2026-10-26). Lo stesso pacchetto,
sotto VPN, compare due volte: sull'adattatore tunnel e su quello fisico che lo
trasporta cifrato; sommarli entrambi gonfia il termine di rete di un fattore che
dipende dalla configurazione. Si sommano quindi le interfacce **fisiche**, con
il loopback escluso. L'eccezione e' dichiarata: se le fisiche non vedono
alcun byte mentre le virtuali si' -- tipico di un host Hyper-V, dove il traffico
passa dallo switch virtuale e il contatore della NIC fisica resta fermo -- si
ricade su tutte le non-loopback e il confine lo scrive. In ogni caso il confine
riporta i nomi delle interfacce sommate, cosi' una riga non e' comparabile con
un'altra senza sapere che cosa ha contato.

La natura di un'interfaccia non si legge dall'alias: su questo host "Ethernet 2"
e' un VirtualBox Host-Only e "Connessione alla rete locale (LAN)* 9" una Wi-Fi
Direct, nessuno dei due con un marcatore nel nome. Dove Windows lo espone si usa
la descrizione del driver, letta in sola lettura dal registro in
``_nic_descriptions``; i marcatori del nome restano come seconda via e come unica
via sugli altri sistemi. Il confine dice quale via ha deciso.

La lista dei marcatori non e' esaustiva: un tunnel con nome e descrizione fuori
lista viene classificato come fisico, e il termine di rete torna a contare due
volte. Non c'e' un modo, con i soli contatori di psutil, di riconoscerlo: il
confine elenca i nomi sommati proprio perche' quel caso resti visibile a chi
legge la riga, invece di sparire dentro una regola dichiarata completa. Se un
nome noto manca, si aggiunge al marcatore: e' una decisione visibile nel diff.

Due casi di lettura degradata, entrambi dichiarati e mai convertiti in zero:
se i contatori per interfaccia non sono leggibili si usa l'aggregato di psutil,
che include il loopback e non lo separa (il confine lo dice); se in una delle due
letture si passa da un tipo all'altro, il delta attraversa due perimetri diversi
e non e' calcolabile -- l'energia di rete diventa ``None``, non ``0.0``.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import psutil

try:
    from config import (
        NETWORK_ENERGY_COEFFICIENT_DEFAULT_J_PER_BIT,
        NETWORK_ENERGY_COEFFICIENT_J_PER_BIT,
    )
except Exception:  # pragma: no cover
    NETWORK_ENERGY_COEFFICIENT_DEFAULT_J_PER_BIT = 2.7e-6
    NETWORK_ENERGY_COEFFICIENT_J_PER_BIT = 2.7e-6


def network_coefficient_provenance(coefficient: float) -> str:
    """Provenienza del coefficiente applicato, per il campo di confine.

    Baliga et al. 2011 descrive un valore preciso (2,7 uJ/bit) e un perimetro
    preciso: attribuirglielo quando la riga usa un altro numero significherebbe
    citare la fonte sopra un dato che non e' il suo. Con ``CW_NET_J_PER_BIT``
    diverso dal valore della fonte il confine dichiara il parametro e tace la
    citazione; con il valore della fonte la porta per esteso, cosi' il lettore
    sa che cosa contiene il joule che sta leggendo.
    """
    try:
        same = abs(float(coefficient)
                   - float(NETWORK_ENERGY_COEFFICIENT_DEFAULT_J_PER_BIT)) <= 1e-12
    except (TypeError, ValueError):
        same = False
    if same:
        return (
            "source: Baliga et al. 2011 (Proc. IEEE 99(1):149-167, "
            "DOI 10.1109/JPROC.2010.2060451, eq. 2 p. 7, value p. 8), "
            "transmission+switching to a public cloud DC, access network "
            "excluded by the source, servers/storage/processing excluded; "
            "model estimate, not a measurement"
        )
    return (
        "source: coefficient overridden via CW_NET_J_PER_BIT -- NOT Baliga et "
        "al. 2011; the path intensity of this row is a declared parameter, not "
        "the published model estimate, and the row is not comparable with one "
        "using 2.7e-6 J/bit"
    )


# Nomi che identificano un loopback: non e' rete, non ha percorso ne'
# coefficiente. Escluso quando i contatori per interfaccia sono leggibili;
# l'aggregato di psutil non lo separa (il confine lo dichiara).
_LOOPBACK_MARKERS = ("loopback", "lo0")

# Nomi che identificano adattatori virtuali o tunnel: sotto VPN portano gli
# stessi byte dell'interfaccia fisica, e sommarli raddoppia il termine di rete.
# L'alias da solo non basta: su questo host "Ethernet 2" e' un VirtualBox
# Host-Only e "Connessione alla rete locale (LAN)* 9" una Wi-Fi Direct, nomi
# senza marcatori. Per questo la classificazione usa anche la descrizione del
# driver (``_nic_descriptions``); questi marcatori restano come seconda via e
# come unica via dove il registro non e' leggibile.
_VIRTUAL_MARKERS = (
    "vethernet", "vswitch", "hyper-v", "hyperv", "vmware", "virtualbox",
    "virtual", "bluetooth", "wi-fi direct", "teredo", "isatap", "6to4",
    "ip-https", "tap-", "tap_", "tun", "wireguard", "openvpn", "tailscale",
    "zerotier", "wintun", "npcap", "docker", "veth", "wsl", "br-", "pseudo",
    "miniport", "kernel debug",
)


def _is_loopback(name: str) -> bool:
    low = name.lower()
    return low in ("lo", "lo0") or "loopback" in low


def _is_virtual(name: str, description: str = "") -> bool:
    """Vero se alias o descrizione del driver dicono "virtuale o tunnel"."""
    text = f"{name} {description}".lower()
    return any(m in text for m in _VIRTUAL_MARKERS)


_NIC_DESC_CACHE: Optional[Dict[str, str]] = None


def _read_nic_descriptions() -> Dict[str, str]:
    """Legge alias -> descrizione del driver dal registro (solo Windows)."""
    if os.name != "nt":  # pragma: no cover - percorso non Windows
        return {}
    try:
        import winreg
    except Exception:  # pragma: no cover
        return {}
    net = (r"SYSTEM\CurrentControlSet\Control\Network"
           r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")
    cls = (r"SYSTEM\CurrentControlSet\Control\Class"
           r"\{4D36E972-E325-11CE-BFC1-08002BE10318}")
    guid_desc: Dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cls) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    with winreg.OpenKey(key, winreg.EnumKey(key, i)) as sub:
                        guid = str(winreg.QueryValueEx(sub, "NetCfgInstanceId")[0])
                        desc = str(winreg.QueryValueEx(sub, "DriverDesc")[0])
                except OSError:
                    continue
                guid_desc[guid.lower()] = desc
    except OSError:
        guid_desc = {}
    out: Dict[str, str] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, net) as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                guid = winreg.EnumKey(key, i)
                try:
                    with winreg.OpenKey(key, guid + r"\Connection") as conn:
                        alias = str(winreg.QueryValueEx(conn, "Name")[0])
                except OSError:
                    continue
                desc = guid_desc.get(guid.lower())
                if desc:
                    out[alias] = desc
    except OSError:
        pass
    return out


def _nic_descriptions() -> Dict[str, str]:
    """Descrizioni dei driver, in cache: il registro si legge una volta sola.

    Una funzione a se' perche' i test sostituiscano la mappa senza toccare il
    registro e senza dipendere dalla macchina su cui girano.
    """
    global _NIC_DESC_CACHE
    if _NIC_DESC_CACHE is None:
        _NIC_DESC_CACHE = _read_nic_descriptions()
    return _NIC_DESC_CACHE


@dataclass(frozen=True)
class _NicSample:
    """Una lettura dei contatori: byte per interfaccia e origine del dato."""

    per_nic: Dict[str, Tuple[int, int]]
    source: str  # "pernic" | "aggregate"


def _sum_delta(before: _NicSample, after: _NicSample,
               names: List[str]) -> Tuple[int, int]:
    """Delta (up, down) sommato sulle interfacce indicate, senza clamp."""
    up = sum(after.per_nic[n][0] - before.per_nic[n][0] for n in names)
    down = sum(after.per_nic[n][1] - before.per_nic[n][1] for n in names)
    return up, down


def _choose(before: _NicSample, after: _NicSample) -> Tuple[List[str], str]:
    """Interfacce da sommare, con la regola applicata (dichiarata nella riga).

    Ordine: fisiche se hanno visto byte; altrimenti tutte le non-loopback, se
    solo le virtuali hanno visto byte (host con switch virtuale); il loopback
    escluso. La natura dell'interfaccia viene dalla descrizione del driver
    quando il registro la espone, altrimenti dai marcatori del nome: il confine
    dice quale delle due vie ha deciso. Con la lettura aggregata (nessun
    dettaglio per interfaccia) non si sceglie nulla e si dichiara che psutil vi
    include il loopback: il delta fra sorgenti diverse non arriva qui, e' gia'
    stato fermato a ``None`` da ``measure``.
    """
    common = [n for n in before.per_nic if n in after.per_nic]
    if before.source == "aggregate" and after.source == "aggregate":
        return common, "psutil-aggregate (all interfaces, loopback not separable)"
    descs = _nic_descriptions()

    def desc(name: str) -> str:
        return descs.get(name, "")

    cand = [n for n in common
            if not _is_loopback(n) and not _is_loopback(desc(n))]
    phys = [n for n in cand if not _is_virtual(n, desc(n))]
    basis = "driver description, else name" if descs else "name only"
    up_p, down_p = _sum_delta(before, after, phys)
    if phys and (up_p + down_p) != 0:
        return phys, f"physical ({basis})"
    up_c, down_c = _sum_delta(before, after, cand)
    if cand and (up_c + down_c) != 0:
        return cand, f"all-non-loopback ({basis}; physical counters saw 0 B)"
    return cand, f"all-non-loopback ({basis}; no bytes in window)"


@dataclass
class NetworkEnergyResult:
    duration_s: float = 0.0
    upload_bytes: int = 0
    download_bytes: int = 0
    total_bytes: int = 0
    energy_j: Optional[float] = None
    coefficient_j_per_bit: float = NETWORK_ENERGY_COEFFICIENT_J_PER_BIT
    measurement_boundary: str = ""
    notes: List[str] = field(default_factory=list)
    # Valori firmati prima del troncamento: un delta negativo e' un contatore
    # azzerato o un'interfaccia ricreata, non un traffico nullo.
    upload_bytes_raw: int = 0
    download_bytes_raw: int = 0
    negative_increment: bool = False
    # Nomi delle interfacce sommate: senza, la riga non dice che cosa ha contato.
    interfaces: str = ""


class NetworkEnergyTracker:
    """Delta NIC tra due istanti -> byte e stima J."""

    @staticmethod
    def _read() -> Optional[_NicSample]:
        """Legge i contatori per interfaccia; ``None`` solo se nulla e' leggibile."""
        try:
            pernic = psutil.net_io_counters(pernic=True)
            return _NicSample(
                per_nic={
                    str(nic): (int(c.bytes_sent), int(c.bytes_recv))
                    for nic, c in pernic.items()
                },
                source="pernic",
            )
        except Exception:
            try:
                c = psutil.net_io_counters()
                return _NicSample(
                    per_nic={"<aggregato>": (int(c.bytes_sent), int(c.bytes_recv))},
                    source="aggregate",
                )
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
            res.energy_j = None
            res.notes.append("contatori NIC non leggibili: energia rete = N/A")
            res.measurement_boundary = "client-NIC counters unavailable"
            return outcome, res
        if before.source != after.source:
            # Un bordo per interfaccia, l'altro aggregato: il delta sommato
            # attraverserebbe due perimetri e non e' un numero. N/A, non 0.0.
            res.energy_j = None
            res.notes.append(
                "letture NIC di natura diversa nella finestra "
                f"({before.source} -> {after.source}): delta non calcolabile "
                "-> energia rete = N/A"
            )
            res.measurement_boundary = "client-NIC counters unavailable (source mismatch)"
            return outcome, res

        names, scope = _choose(before, after)
        up_raw, down_raw = _sum_delta(before, after, names)
        res.interfaces = ", ".join(names)
        res.upload_bytes_raw = int(up_raw)
        res.download_bytes_raw = int(down_raw)
        if up_raw < 0 or down_raw < 0:
            res.negative_increment = True
            res.notes.append(
                "delta NIC negativo (contatore azzerato o interfaccia ricreata "
                f"nella finestra): up={up_raw} B, down={down_raw} B; il valore "
                "applicato e' 0 e il grezzo resta in upload/download_bytes_raw"
            )
        if set(before.per_nic) != set(after.per_nic):
            res.notes.append(
                "interfacce cambiate nella finestra: sommate solo quelle presenti "
                "in entrambe le letture"
            )

        up = max(up_raw, 0)
        down = max(down_raw, 0)
        res.upload_bytes = int(up)
        res.download_bytes = int(down)
        res.total_bytes = int(up + down)
        bits = res.total_bytes * 8
        res.energy_j = round(bits * res.coefficient_j_per_bit, 9)
        res.measurement_boundary = (
            "client NIC byte delta over request window, interfaces "
            f"[{res.interfaces}] ({scope}) x path intensity "
            f"({res.coefficient_j_per_bit:.1e} J/bit); "
            + network_coefficient_provenance(res.coefficient_j_per_bit)
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
        res.upload_bytes_raw = int(up_bytes)
        res.download_bytes_raw = int(down_bytes)
        res.total_bytes = res.upload_bytes + res.download_bytes
        res.energy_j = round(res.total_bytes * 8 * res.coefficient_j_per_bit, 9)
        if up_bytes < 0 or down_bytes < 0:
            res.negative_increment = True
            res.notes.append(
                "byte di payload negativi in ingresso: applicato 0, il grezzo "
                "resta in upload/download_bytes_raw"
            )
        res.measurement_boundary = (
            "HTTP payload accounting (request+response bodies) at client socket "
            "level x path intensity "
            f"({res.coefficient_j_per_bit:.1e} J/bit); "
            + network_coefficient_provenance(res.coefficient_j_per_bit)
        )
        return res
