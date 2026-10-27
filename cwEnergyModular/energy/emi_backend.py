# -*- coding: utf-8 -*-
"""
emi_backend.py — contatore di energia EMI di Windows, letto con ctypes puro.

PERCHE' ESISTE (23/10, decisione dell'utente motivata da licenza e precisione)
------------------------------------------------------------------------------
Il canale EMI (interfaccia driver "Energy Estimation Mechanism", IOCTL
documentato sul device PAC ACPI del processore Intel) legge lo STESSO
registro MSR_PKG_ENERGY_STATUS (0x611) che LibreHardwareMonitor usa per il
sensore "CPU Package": LHM pero' lo espone come POTENZA gia' derivata
(``IntelCpu.cs:696`` = ``Δ(0x611)/Δt``) e noi la re-integriamo
(power-integration, cap.3). Il percorso EMI legge invece l'ACCUMULATORE
grezzo in pWh: niente integrazione, niente thread .NET, niente selezione
del sensore per nome (l'omonimia Temperature/Power che ha prodotto il difetto
storico, fix 1422d1b), niente token elevato (verificato il 23/10: CreateFileW
+ IOCTL riescono anche da processo non Admin).

RECORD DELLO SLOT (16 byte per canale: energia + timestamp, little-endian)
--------------------------------------------------------------------------
Sul device di questa macchina i quattro canali del metadato sono, nell'ordine
in cui il driver li enumera:

  canale 0 / ts  8  -> PKG   (package, dominio intero)
  canale 1 / ts 24  -> DRAM  (memoria; su host client vale spesso 0)
  canale 2 / ts 40  -> PP0   (core)
  canale 3 / ts 56  -> PP1   (iGPU)

  * unita': picoWattora (1 pWh = 3,6e-9 J), dichiarata dal metadato
    (``MeasurementUnit``); conferma numerica in
    ``experiment_results/srum_emi_cross_20261023_analisi.md``;
  * timestamp del record in unita' da 100 ns del contatore del driver;
  * NON ADDITIVITA' (Beyer & Wendler 2020, LNCS 12079, e dati nostri):
    PP0 + PP1 != PKG e PKG + DRAM != "tutto"; PP0/PP1 sono SOTTOINSIEMI di
    PKG. I campi si riportano per confronto, MAI si sommano fra loro.
  * la corrispondenza canale->dominio viene dal metadato e dal NOME del
    canale, non da questo ordine: dal 27/10/2026 il backend legge
    ``IOCTL_EMI_GET_VERSION`` / ``GET_METADATA_SIZE`` / ``GET_METADATA`` e
    mappa per nome (vedi sotto). L'ordine qui sopra e' quello del metadato
    verificato, utile a leggere i CSV e i protocolli storici, non un
    presupposto del codice. ``read_domains`` espone comunque il timestamp
    PER DOMINIO, che e' l'unico modo di accorgersi che un canale non viene
    aggiornato. PP1 (involto grafico) e' letto ai bordi di finestra da
    ``energy_session`` e resta campo INFORMATIVO.

SELEZIONE DEL DEVICE E DEL CANALE (27/10/2026, difetti F11/F13, decisione D17)
------------------------------------------------------------------------------
Il device path non e' hardcodato, ma il percorso non prende piu' il "primo
device apribile" ne' il primo canale del record: enumera tutte le interfacce
del GUID e, per ciascuna, legge il contratto documentato dal driver --
``IOCTL_EMI_GET_VERSION`` -> ``GET_METADATA_SIZE`` -> ``GET_METADATA`` -- prima
di decidere. Un device e' un *device CPU* solo se il metadato espone un canale
il cui nome contiene il token ``PKG`` (il nostro: ``RAPL_Package0_PKG``):
batteria, sensor hub e GPU non hanno quel canale e vengono scartati con la
ragione scritta nelle note. Il dominio di ogni valore si ricava dal NOME del
canale e non dalla posizione nel record: l'ordine ``pkg, dram, pp0, pp1`` era
un'assunzione (F13), e con essa cade anche la lettura del solo primo canale
(F11). Il metadato verificato su i9-13900HK il 27/10/2026: ``EMI_VERSION_V2``,
``MetadataSize=492``, ``HardwareOEM="Microsoft"``, ``HardwareModel="PPM"``,
``ChannelCount=4``, canali ``RAPL_Package0_PKG/_DRAM/_PP0/_PP1``, unita' pWh
(``EmiMeasurementUnitPicowattHours``). Un device V1 (un solo canale) non e'
selezionabile: la lettura V1 non e' implementata ne' provata, e il device si
scarta dicendolo invece di farlo passare per un guasto dell'IOCTL.

Su macchine senza driver, senza device CPU o con piu' device CPU (package
multipli) la selezione non produce un canale: ``available`` resta False con la
ragione, e il chiamante dichiara ``unavailable``. ``CW_EMI_DEVICE`` restringe
la scelta a un path esplicito, ma non salta la verifica del metadato.
"""
from __future__ import annotations

import ctypes
import os
import platform
import re
import struct
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

#: GUID dell'interfaccia device del canale energia
#: {45bd8344-7ed6-49cf-a440-c276c933b053}, verificato il 23/10 con
#: enumerazione SetupAPI su i9-13900HK: un'unica interfaccia, path identico
#: a quello hardcoded in experiment_validate_lhm.py:241-242.
INTERFACE_GUID_L1 = 0x45BD8344
INTERFACE_GUID_W1 = 0x7ED6
INTERFACE_GUID_W2 = 0x49CF
INTERFACE_GUID_DATA = (0xA4, 0x40, 0xC2, 0x76, 0xC9, 0x33, 0xB0, 0x53)

#: IOCTL del contratto EMI. In ``emi.h`` sono
#: ``CTL_CODE(FILE_DEVICE_UNKNOWN, funzione, METHOD_BUFFERED, FILE_READ_ACCESS)``
#: con ``FILE_DEVICE_UNKNOWN = 0x22`` e funzione 0-3, cioe' 0x00224000 +
#: 4*funzione; ``GET_MEASUREMENT`` = 0x0022400C e' il valore letto dai
#: protocolli dal 22/10, e il 27/10/2026 i tre IOCTL dei metadati hanno
#: risposto sul device di questa macchina (versione 2, metadato di 492 byte).
IOCTL_GET_VERSION = 0x00224000
IOCTL_GET_METADATA_SIZE = 0x00224004
IOCTL_GET_METADATA = 0x00224008
IOCTL_ENERGY_READ = 0x0022400C

#: Valori di ``EMI_VERSION``: 1 = un solo canale, 2 = canali multipli con nome.
EMI_VERSION_V1 = 1
EMI_VERSION_V2 = 2

#: Unico valore documentato di ``EMI_MEASUREMENT_UNIT``
#: (``EmiMeasurementUnitPicowattHours``): il dato vale pWh e ``PWH_TO_J``.
UNIT_PWH = 0

#: Nome del canale -> dominio. Il confronto e' per TOKEN del nome, mai per
#: posizione nel record: ``RAPL_Package0_PKG`` -> ``pkg``.
_DOMAIN_TOKENS = {"PKG": "pkg", "DRAM": "dram", "PP0": "pp0", "PP1": "pp1"}

#: 1 pWh = 1e-12 Wh = 3,6e-9 J
PWH_TO_J = 3.6e-9

#: Nome del dominio per ogni coppia (valore, timestamp) del record
DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")

#: Metodo riportato nel campo ``method`` del CSV quando questo canale e'
#: quello attivo (il campo per riga resta l'unico arbitro di comparabilita').
METHOD_LABEL = "emi-counter"

#: Versione del PERCORSO DI LETTURA (non del driver): cambia quando cambia il
#: contratto di lettura (record, unita', IOCTL). Finisce in ``backend_version``
#: accanto ai valori grezzi, perche' una riga di CSV senza la versione del
#: lettore non e' riproducibile.
READER_VERSION = "emi-reader/2"
BACKEND_VERSION = (f"{READER_VERSION} (IOCTL 0x{IOCTL_ENERGY_READ:08X}, "
                   "metadato EMI V2, canale PKG scelto per nome)")


@dataclass(frozen=True)
class EmiChannel:
    """Un canale del metadato: indice NEL RECORD, nome, unita', dominio.

    ``index`` e' la posizione della coppia (energia, timestamp) nel record di
    misura, cioe' l'ordine di enumerazione del metadato; ``domain`` e' None per
    un canale il cui nome non contiene un token noto, e quei canali non
    producono campi (non si indovina un dominio dal nome che non ce l'ha).
    """

    index: int
    name: str
    unit: int
    domain: Optional[str]


@dataclass(frozen=True)
class EmiMetadata:
    """Metadato di un device EMI (solo V2: vedi ``parse_metadata``)."""

    version: int
    hardware_oem: str
    hardware_model: str
    hardware_revision: int
    channels: Tuple[EmiChannel, ...]


def domain_from_channel_name(name: str) -> Optional[str]:
    """Dominio dedotto dal nome del canale, per token; None se non univoco.

    ``RAPL_Package0_PKG`` -> ``pkg``. Se il nome contiene token di domini
    diversi (o nessuno) il canale non viene assegnato: un dominio indovinato e'
    peggio di un dominio mancante, che almeno si dichiara.
    """
    tokens = {t for t in re.split(r"[^0-9A-Za-z]+", name.upper()) if t}
    found = {_DOMAIN_TOKENS[t] for t in tokens if t in _DOMAIN_TOKENS}
    return found.pop() if len(found) == 1 else None


def channels_from_names(names: Sequence[str]) -> List[EmiChannel]:
    """Canali numerati come nel record, con unita' pWh e dominio dal nome."""
    return [EmiChannel(i, n, UNIT_PWH, domain_from_channel_name(n))
            for i, n in enumerate(names)]


def _wstr(blob: bytes, offset: int, nbytes: int) -> str:
    return blob[offset:offset + nbytes].decode("utf-16-le", "replace").split("\x00", 1)[0]


def parse_metadata(blob: bytes, version: int) -> EmiMetadata:
    """Interpreta il metadato V2 (``EMI_METADATA_V2``) letto dal driver.

    Layout documentato: ``HardwareOEM[16]`` (32 B) a 0, ``HardwareModel[16]``
    (32 B) a 32, ``HardwareRevision`` e ``ChannelCount`` (u16) a 64 e 66,
    poi ``Channels[]``. Ogni ``EMI_CHANNEL_V2`` e' ``MeasurementUnit`` (u32),
    ``ChannelNameSize`` (u16, byte incluso il terminatore) e il nome: la
    lunghezza totale e' 6 + ChannelNameSize, esattamente il passo di
    ``EMI_CHANNEL_V2_NEXT_CHANNEL`` (senza allineamento). Un blob troncato e'
    un errore dichiarato, non un canale in meno letto in silenzio.
    """
    if version != EMI_VERSION_V2:
        raise ValueError(f"versione EMI {version}: il parser e' quello V2")
    if len(blob) < 68:
        raise ValueError(f"metadato EMI troncato ({len(blob)} byte < 68)")
    oem = _wstr(blob, 0, 32)
    model = _wstr(blob, 32, 32)
    revision, count = struct.unpack_from("<HH", blob, 64)
    offset = 68
    channels: List[EmiChannel] = []
    for i in range(count):
        if offset + 6 > len(blob):
            raise ValueError(
                f"canale {i}/{count} oltre il metadato ({len(blob)} byte)")
        unit, name_size = struct.unpack_from("<IH", blob, offset)
        if name_size < 2 or offset + 6 + name_size > len(blob):
            raise ValueError(
                f"canale {i}: ChannelNameSize={name_size} non plausibile "
                f"nel metadato di {len(blob)} byte")
        name = _wstr(blob, offset + 6, name_size)
        channels.append(EmiChannel(i, name, unit,
                                   domain_from_channel_name(name)))
        offset += 6 + name_size
    return EmiMetadata(version, oem, model, revision, tuple(channels))


@dataclass(frozen=True)
class DeviceChoice:
    """Un device accettato: il canale PKG che lo rende un device CPU."""

    path: str
    metadata: EmiMetadata
    channel: EmiChannel
    notes: Tuple[str, ...]


def select_cpu_device(
    devices: Sequence[Tuple[str, EmiMetadata]],
) -> Tuple[List[DeviceChoice], List[Tuple[str, str]]]:
    """Separa i device CPU dai device da scartare, con la ragione di ognuno.

    Un device e' CPU se espone un canale di dominio ``pkg`` in pWh. Batteria,
    sensor hub e GPU non hanno quel canale; un device con piu' canali PKG
    distinti (package multipli) e' ``ambiguous_domain`` e non si sceglie: la
    somma di package non e' una decisione che questo lettore puo' prendere da
    solo. Canali PKG omonimi sono invece lo stesso contatore specchiato e si
    leggono una volta sola, dichiarandolo.
    """
    chosen: List[DeviceChoice] = []
    rejected: List[Tuple[str, str]] = []
    for path, meta in devices:
        pkg = [c for c in meta.channels if c.domain == "pkg"]
        if not pkg:
            names = ", ".join(c.name for c in meta.channels) or "nessuno"
            rejected.append(
                (path, f"nessun canale PKG: non e' un device CPU (canali: {names})"))
            continue
        wrong_unit = [c for c in pkg if c.unit != UNIT_PWH]
        if wrong_unit:
            rejected.append(
                (path, f"canale PKG in unita' {wrong_unit[0].unit}, non pWh"))
            continue
        distinct = sorted({c.name for c in pkg})
        if len(distinct) > 1:
            rejected.append(
                (path, "ambiguous_domain: piu' canali PKG distinti ("
                       + ", ".join(distinct) + ")"))
            continue
        notes = []
        if len(pkg) > 1:
            notes.append(f"canale PKG specchiato ({len(pkg)} canali omonimi "
                         f"'{pkg[0].name}'): letto l'indice {pkg[0].index}")
        chosen.append(DeviceChoice(path, meta, pkg[0], tuple(notes)))
    return chosen, rejected


def choose_single(
    chosen: Sequence[DeviceChoice],
) -> Tuple[Optional[DeviceChoice], str]:
    """Politica dello *uno solo*: nessuno o troppi sono un'assenza dichiarata.

    Con piu' device CPU (package multipli) il lettore non sceglie: leggere un
    package e chiamarlo "il package" su una macchina multi-socket e'
    esattamente la classe di errore F11/F13. La scelta esplicita resta
    ``CW_EMI_DEVICE``.
    """
    if not chosen:
        return None, ("EMI: nessun device CPU con canale PKG in pWh: "
                      "il canale resta unavailable")
    if len(chosen) > 1:
        return None, ("EMI: ambiguous_domain, "
                      f"{len(chosen)} device CPU distinti (package multipli): "
                      + "; ".join(c.path for c in chosen)
                      + ". Nessuna selezione automatica: dichiarare il "
                      "device con CW_EMI_DEVICE.")
    return chosen[0], ""


class EMICounterBackend:
    """Lettore del contatore cumulativo EMI (pkg in Joule).

    ``available`` e' True SOLO dopo un'apertura + prima lettura riuscite:
    un backend non disponibile non produce MAI letture inventate.
    """

    def __init__(self, auto_open: bool = True) -> None:
        self.notes: List[str] = []
        self.available = False
        self.device_path: Optional[str] = None
        self.metadata: Optional[EmiMetadata] = None
        #: Canali del device selezionato, nell'ordine del record di misura.
        #: Vuoto finche' l'apertura non e' riuscita: nessun canale presunto.
        self.channels: List[EmiChannel] = []
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()
        self._handle: Optional[int] = None
        if auto_open:
            self._open()

    @property
    def pkg_channel(self) -> Optional[EmiChannel]:
        """Il canale PKG scelto per nome, o None se non c'e' (mai il primo)."""
        for ch in self.channels:
            if ch.domain == "pkg":
                return ch
        return None

    # ------------------------------------------------------------------ open
    @staticmethod
    def _is_windows() -> bool:
        return platform.system() == "Windows"

    def _win32(self):
        return ctypes.windll.kernel32  # type: ignore[attr-defined]

    def enumerate_device_paths(self) -> List[str]:
        """Path delle interfacce device per il GUID del canale energia."""
        if not self._is_windows():
            return []
        try:
            sde = ctypes.windll.setupapi  # type: ignore[attr-defined]

            class _GUID(ctypes.Structure):
                _fields_ = [("l", ctypes.c_uint32), ("w1", ctypes.c_uint16),
                            ("w2", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

            class _IFD(ctypes.Structure):
                _fields_ = [("cbSize", ctypes.c_uint32),
                            ("InterfaceClassGuid", _GUID),
                            ("Flags", ctypes.c_uint32),
                            ("Reserved", ctypes.POINTER(ctypes.c_ulong))]

            guid = _GUID(INTERFACE_GUID_L1, INTERFACE_GUID_W1, INTERFACE_GUID_W2,
                         (ctypes.c_ubyte * 8)(*INTERFACE_GUID_DATA))
            sde.SetupDiGetClassDevsW.restype = ctypes.c_void_p
            sde.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                 ctypes.c_void_p, ctypes.c_uint32]
            sde.SetupDiEnumDeviceInterfaces.restype = ctypes.c_int
            sde.SetupDiEnumDeviceInterfaces.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                        ctypes.c_void_p, ctypes.c_uint32,
                                                        ctypes.c_void_p]
            sde.SetupDiGetDeviceInterfaceDetailW.restype = ctypes.c_int
            sde.SetupDiGetDeviceInterfaceDetailW.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                                             ctypes.c_void_p, ctypes.c_uint32,
                                                             ctypes.POINTER(ctypes.c_uint32),
                                                             ctypes.c_void_p]
            # DIGCF_PRESENT (0x02) | DIGCF_DEVICEINTERFACE (0x10)
            hset = sde.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)
            if not hset or ctypes.c_ssize_t(hset).value == -1:
                self.last_error = f"SetupDiGetClassDevsW err={ctypes.GetLastError()}"
                return []
            paths: List[str] = []
            for i in range(16):
                ifd = _IFD()
                ifd.cbSize = ctypes.sizeof(ifd)
                if not sde.SetupDiEnumDeviceInterfaces(hset, None, ctypes.byref(guid),
                                                       i, ctypes.byref(ifd)):
                    break
                sz = ctypes.c_uint32(0)
                sde.SetupDiGetDeviceInterfaceDetailW(hset, ctypes.byref(ifd), None, 0,
                                                     ctypes.byref(sz), None)
                if not sz.value:
                    continue
                buf = ctypes.create_string_buffer(sz.value)
                # x64: cbSize dell'DETAIL deve essere 8 (DWORD + padding),
                # DevicePath inizia all'offset 4.
                detail_size = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 4 + ctypes.sizeof(ctypes.c_wchar)
                ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32))[0] = detail_size
                if sde.SetupDiGetDeviceInterfaceDetailW(hset, ctypes.byref(ifd), buf,
                                                        sz.value, ctypes.byref(sz), None):
                    paths.append(ctypes.wstring_at(ctypes.addressof(buf) + 4))
            return paths
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            self.last_error = f"enumerazione SetupAPI: {type(exc).__name__}: {exc}"
            return []

    def _open(self) -> bool:
        self.available = False
        self.device_path = None
        self.metadata = None
        self.channels = []
        if not self._is_windows():
            self.notes.append("EMI non applicabile (piattaforma non Windows)")
            return False
        # override esplicito per debug/test: CW_EMI_DEVICE=<path>.
        # Restringe la scelta, non la verifica: il device deve comunque
        # dichiarare un canale PKG nel metadato.
        forced = os.environ.get("CW_EMI_DEVICE")
        if forced:
            candidates = [forced]
        else:
            candidates = self.enumerate_device_paths()
        if not candidates:
            self.notes.append(
                f"EMI: nessuna interfaccia device trovata "
                f"({self.last_error or 'SetupAPI vuoto'}): driver del canale "
                "energia assente o non esposto"
            )
            return False
        k32 = self._win32()
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p]
        parsed: List[Tuple[str, EmiMetadata]] = []
        rejected: List[Tuple[str, str]] = []
        handles: Dict[str, int] = {}
        for dev in candidates:
            h = k32.CreateFileW(dev, 0x80000000, 3, None, 3, 0x80, None)
            hv = ctypes.c_ssize_t(h).value if h is not None else -1
            if hv == -1:
                rejected.append(
                    (dev, f"CreateFileW err={ctypes.GetLastError()}"))
                continue
            meta, why = self._read_metadata(hv)
            if meta is None:
                k32.CloseHandle(ctypes.c_void_p(hv))
                rejected.append((dev, why))
                continue
            parsed.append((dev, meta))
            handles[dev] = hv

        chosen, select_rejected = select_cpu_device(parsed)
        rejected.extend(select_rejected)
        for path, why in rejected:
            self.notes.append(f"EMI: device scartato ({path}): {why}")
        choice, why = choose_single(chosen)
        if choice is None:
            for hv in handles.values():
                k32.CloseHandle(ctypes.c_void_p(hv))
            self.notes.append(why)
            self.last_error = why
            return False
        for path, hv in handles.items():
            if path != choice.path:
                k32.CloseHandle(ctypes.c_void_p(hv))
        self._handle = handles[choice.path]
        self.device_path = choice.path
        self.metadata = choice.metadata
        self.channels = list(choice.metadata.channels)
        # validazione: la PRIMA lettura deve riuscire o si degrada
        if self._ioctl_raw() is None:
            self.notes.append(
                f"EMI: device CPU selezionato ma primo IOCTL fallito "
                f"({self.last_error}) su path " + choice.path
            )
            self._close_handle()
            self.channels = []
            self.metadata = None
            self.device_path = None
            return False
        self.available = True
        self.notes.extend(choice.notes)
        self.notes.append(
            "EMI: device CPU selezionato per metadato: device "
            f"'{self.device_path}' (EMI v{choice.metadata.version}, "
            f"OEM '{choice.metadata.hardware_oem}', "
            f"modello '{choice.metadata.hardware_model}', "
            f"rev {choice.metadata.hardware_revision}, "
            f"{len(self.channels)} canali); canale PKG indice "
            f"{choice.channel.index} '{choice.channel.name}' in pWh. "
            "Domini mappati per nome, non per posizione; lettura senza token "
            "elevato"
        )
        return True

    def _read_metadata(self, handle: int) -> Tuple[Optional[EmiMetadata], str]:
        """Version + metadato di un device. Ritorna (metadato, ragione)."""
        raw, why = self._ioctl(handle, IOCTL_GET_VERSION, out_size=8, min_out=2)
        if raw is None:
            return None, f"GET_VERSION fallita ({why})"
        version = struct.unpack_from("<H", raw, 0)[0]
        if version == EMI_VERSION_V1:
            return None, ("EMI V1 (un solo canale): la lettura V1 non e' "
                          "implementata ne' provata, device scartato")
        if version != EMI_VERSION_V2:
            return None, f"versione EMI {version} non riconosciuta"
        raw, why = self._ioctl(handle, IOCTL_GET_METADATA_SIZE,
                               out_size=8, min_out=4)
        if raw is None:
            return None, f"GET_METADATA_SIZE fallita ({why})"
        size = struct.unpack_from("<I", raw, 0)[0]
        if size < 68:
            return None, f"MetadataSize non plausibile ({size} byte)"
        blob, why = self._ioctl(handle, IOCTL_GET_METADATA,
                                out_size=size, min_out=size)
        if blob is None:
            return None, f"GET_METADATA fallita ({why})"
        try:
            return parse_metadata(blob, version), ""
        except ValueError as exc:
            return None, f"metadato non interpretabile: {exc}"

    # ----------------------------------------------------------------- read
    def _ioctl(self, handle: int, code: int, out_size: int,
               min_out: int) -> Tuple[Optional[bytes], str]:
        """Una ``DeviceIoControl`` senza input; ritorna (byte, ragione)."""
        try:
            k32 = self._win32()
            k32.DeviceIoControl.restype = ctypes.c_bool
            k32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.c_void_p]
            out = ctypes.create_string_buffer(out_size)
            got = ctypes.c_uint32(0)
            ok = k32.DeviceIoControl(ctypes.c_void_p(handle), code, None, 0,
                                     out, out_size, ctypes.byref(got), None)
            if not ok or got.value < min_out:
                return None, (f"DeviceIoControl(0x{code:08X}) "
                              f"err={ctypes.GetLastError()} got={got.value}")
            return out.raw[:got.value], ""
        except Exception as exc:  # noqa: BLE001 - degrazione dichiarata
            return None, f"{type(exc).__name__}: {exc}"

    def _ioctl_raw(self) -> Optional[tuple]:
        """Una lettura del record di misura. NON tocca il lock (chi lo
        chiama lo tiene); ritorna None con last_error popolato.

        La dimensione la detta il metadato: 16 byte per canale
        (``EMI_CHANNEL_MEASUREMENT_DATA`` = energia + tempo). L'IOCTL
        documentato non prende input buffer; il 27/10/2026 la chiamata senza
        input e quella con i 16 byte dell'indice restituiscono lo stesso
        record su questo driver, quindi si usa quella documentata.
        """
        if self._handle is None:
            return None
        n = len(self.channels)
        if n == 0:
            self.last_error = "nessun canale dal metadato: lettura impossibile"
            return None
        size = 16 * n
        raw, why = self._ioctl(self._handle, IOCTL_ENERGY_READ,
                               out_size=size, min_out=size)
        if raw is None:
            self.last_error = why
            return None
        return struct.unpack("<%dQ" % (2 * n), raw[:size])

    def read_raw(self) -> Optional[tuple]:
        """Record completo (8 uint64). Con riapertura tentata UNA volta se
        l'handle e' diventato invalido (es. suspend/resume del portatile)."""
        if not self.available:
            return None
        with self._lock:
            v = self._ioctl_raw()
            if v is None:
                self._close_handle()
                if self._open():
                    v = self._ioctl_raw()
            return v

    def read_cumulative_energy_j(self) -> Optional[float]:
        """Energia package CUMULATA da boot [J] (canale PKG * 3,6e-9).

        Il canale e' quello scelto per nome: senza metadato non si legge,
        invece di assumere che il package sia il primo del record.
        """
        pkg = self.pkg_channel
        if pkg is None:
            return None
        v = self.read_raw()
        if v is None:
            return None
        return v[2 * pkg.index] * PWH_TO_J

    def read_fields_j(self) -> Optional[Dict[str, float]]:
        """I domini presenti nel metadato [J] + timestamp del canale PKG.

        Campi informativi etichettati: NON sommare PP0+PP1 ne' PKG+DRAM. Un
        dominio che il device non espone non compare (prima compariva sempre,
        perche' la posizione lo faceva esistere).
        """
        d = self.read_domains()
        if d is None:
            return None
        out = {name: d[name][0] for name in DOMAIN_NAMES if name in d}
        out["ts_100ns"] = d["pkg"][1] if "pkg" in d else None
        return out

    def read_domains(self) -> Optional[Dict[str, tuple]]:
        """Una sola IOCTL -> ``dominio -> (cumulata [J], timestamp 100 ns, pWh)``.

        La mappa viene dal metadato: ogni coppia (energia, tempo) del record
        appartiene al canale con quell'indice, e il dominio e' quello del
        NOME del canale. Nessuna posizione assunta (F13), quindi un canale
        il cui nome non contiene un token noto non produce un campo: resta
        nel metadato e nel nome, non in un dominio indovinato.

        Il timestamp e' PER DOMINIO (offset dispari di ogni coppia del
        record), non uno solo: e' cio' che distingue un dominio che ha
        misurato zero da un dominio il cui registro non viene aggiornato
        dal driver. ``read_fields_j`` porta solo il timestamp del PKG
        (``ts_100ns``), quindi chi interrogava PP1 non aveva modo di sapere
        se quel valore fosse vecchio o fosse davvero zero.

        Il terzo elemento e' il valore GREZZO in pWh, non ricostruito da J:
        serve al campo ``raw_start``/``raw_end`` del CSV (contratto di
        ``alt_lhm`` §3). I chiamanti storici usano ``[0]`` e ``[1]`` e non
        vengono toccati; chi vuole il grezzo legge ``[2]``.

        Nessuna conversione ne' scelta di canale qui: la politica (quale
        dominio, con quale regola di freschezza) sta nel chiamante.
        """
        v = self.read_raw()
        if v is None:
            return None
        out: Dict[str, tuple] = {}
        for ch in self.channels:
            if ch.domain is None:
                continue
            i = ch.index
            out[ch.domain] = (v[2 * i] * PWH_TO_J, v[2 * i + 1], v[2 * i])
        return out or None

    # --------------------------------------------------------------- close
    def _close_handle(self) -> None:
        h = self._handle
        self._handle = None
        if h is not None and self._is_windows():
            try:
                self._win32().CloseHandle(h)
            except Exception:
                pass

    def close(self) -> None:
        with self._lock:
            self._close_handle()
        self.available = False
