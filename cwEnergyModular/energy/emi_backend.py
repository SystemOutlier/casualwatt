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

RECORD DELLO SLOT (8 uint64 little-endian, 64 byte)
----------------------------------------------------
  offset  0 / ts  8  -> PKG   (package, dominio intero)
  offset 16 / ts 24  -> DRAM  (memoria; su host client vale spesso 0)
  offset 32 / ts 40  -> PP0   (core)
  offset 48 / ts 56  -> PP1   (iGPU)

  * unita': picoWattora (1 pWh = 3,6e-9 J) — conferma in
    ``experiment_results/srum_emi_cross_20261023_analisi.md``;
  * timestamp del record in unita' da 100 ns del contatore del driver;
  * NON ADDITIVITA' (Beyer & Wendler 2020, LNCS 12079, e dati nostri):
    PP0 + PP1 != PKG e PKG + DRAM != "tutto"; PP0/PP1 sono SOTTOINSIEMI di
    PKG. I campi si riportano per confronto, MAI si sommano fra loro.
  * l'assegnazione offset->dominio, fin qui ASSUNTA dall'ordine dei record,
    il 24/10 e' stata confermata dal metadato del driver: le interrogazioni
    EMI dei canali (stessa GUID, IOCTL dei metadati) restituiscono i nomi
    ``RAPL_Package0_PKG``, ``_DRAM``, ``_PP0``, ``_PP1`` nell'ordine esatto
    di ``DOMAIN_NAMES``, su i9-13900HK. Resta una conferma su UNA macchina,
    non una garanzia del formato: per questo ``read_domains`` espone il
    timestamp PER DOMINIO, che e' l'unico modo di accorgersi che un canale
    non viene aggiornato. PP1 (involto grafico) e' letto ai bordi di
    finestra da ``energy_session`` e resta campo INFORMATIVO.

Il device path NON e' hardcodato: viene enumerato via SetupAPI dal GUID di
interfaccia, quindi il backend funziona su qualsiasi macchina dove il driver
del canale energia Intel e' installato. Su macchine senza driver,
``available`` resta False e il chiamante degrada dichiaratamente a LHM.
"""
from __future__ import annotations

import ctypes
import os
import platform
import struct
import threading
from typing import Dict, List, Optional

#: GUID dell'interfaccia device del canale energia
#: {45bd8344-7ed6-49cf-a440-c276c933b053}, verificato il 23/10 con
#: enumerazione SetupAPI su i9-13900HK: un'unica interfaccia, path identico
#: a quello hardcoded in experiment_validate_lhm.py:241-242.
INTERFACE_GUID_L1 = 0x45BD8344
INTERFACE_GUID_W1 = 0x7ED6
INTERFACE_GUID_W2 = 0x49CF
INTERFACE_GUID_DATA = (0xA4, 0x40, 0xC2, 0x76, 0xC9, 0x33, 0xB0, 0x53)

#: IOCTL del "GetSlot"-style request (input: u16 index=0, 16 byte;
#: output: 64 byte = 8 uint64). Identico a quello validato nei protocolli
#: del 22-23/10 (experiment_validate_lhm.py:250, four_way_test.py).
IOCTL_ENERGY_READ = 0x0022400C

#: 1 pWh = 1e-12 Wh = 3,6e-9 J
PWH_TO_J = 3.6e-9

#: Nome del dominio per ogni coppia (valore, timestamp) del record
DOMAIN_NAMES = ("pkg", "dram", "pp0", "pp1")

#: Metodo riportato nel campo ``method`` del CSV quando questo canale e'
#: quello attivo (il campo per riga resta l'unico arbitro di comparabilita').
METHOD_LABEL = "emi-counter"


class EMICounterBackend:
    """Lettore del contatore cumulativo EMI (pkg in Joule).

    ``available`` e' True SOLO dopo un'apertura + prima lettura riuscite:
    un backend non disponibile non produce MAI letture inventate.
    """

    def __init__(self, auto_open: bool = True) -> None:
        self.notes: List[str] = []
        self.available = False
        self.device_path: Optional[str] = None
        self.last_error: Optional[str] = None
        self._lock = threading.Lock()
        self._handle: Optional[int] = None
        if auto_open:
            self._open()

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
        if not self._is_windows():
            self.notes.append("EMI non applicabile (piattaforma non Windows)")
            return False
        # override esplicito per debug/test: CW_EMI_DEVICE=<path>
        candidates: List[str] = []
        forced = os.environ.get("CW_EMI_DEVICE")
        if forced:
            candidates.append(forced)
        candidates.extend(self.enumerate_device_paths())
        if not candidates:
            self.notes.append(
                f"EMI: nessuna interfaccia device trovata "
                f"({self.last_error or 'SetupAPI vuoto'}): driver canale "
                "energia Intel assente o non esposto"
            )
            return False
        k32 = self._win32()
        k32.CreateFileW.restype = ctypes.c_void_p
        k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
                                   ctypes.c_void_p]
        for dev in candidates:
            h = k32.CreateFileW(dev, 0x80000000, 3, None, 3, 0x80, None)
            hv = ctypes.c_ssize_t(h).value if h is not None else -1
            if hv == -1:
                self.last_error = f"CreateFileW({dev}) err={ctypes.GetLastError()}"
                continue
            self._handle = hv
            self.device_path = dev
            # validazione: la PRIMA lettura deve riuscire o si degrada
            if self._ioctl_raw() is None:
                self.notes.append(
                    f"EMI: device aperto ma IOCTL fallito ({self.last_error}) "
                    "su path " + dev
                )
                self._close_handle()
                return False
            self.available = True
            self.notes.append(
                "EMI: contatore package cumulativo (pWh) attivo su device "
                "enumerato via SetupAPI (lettura senza token elevato)"
            )
            return True
        self.notes.append(
            f"EMI: nessun candidate device apribile ({self.last_error})"
        )
        return False

    # ----------------------------------------------------------------- read
    def _ioctl_raw(self) -> Optional[tuple]:
        """Una lettura del record a 8 uint64. NON tocca il lock (chi lo
        chiama lo tiene); ritorna None con last_error popolato."""
        if self._handle is None:
            return None
        try:
            k32 = self._win32()
            k32.DeviceIoControl.restype = ctypes.c_bool
            k32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.c_void_p]
            inbuf = ctypes.create_string_buffer(16)
            struct.pack_into("<H", inbuf, 0, 0)
            out = ctypes.create_string_buffer(64)
            got = ctypes.c_uint32(0)
            ok = k32.DeviceIoControl(self._handle, IOCTL_ENERGY_READ, inbuf, 16,
                                     out, 64, ctypes.byref(got), None)
            if not ok or got.value < 64:
                self.last_error = f"DeviceIoControl err={ctypes.GetLastError()} got={got.value}"
                return None
            return struct.unpack("<8Q", out.raw[:64])
        except Exception as exc:  # noqa: BLE001
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None

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
        """Energia package CUMULATA da boot [J] (campo PKG * 3,6e-9)."""
        v = self.read_raw()
        if v is None:
            return None
        return v[0] * PWH_TO_J

    def read_fields_j(self) -> Optional[Dict[str, float]]:
        """Tutti e quattro i domini [J] + timestamp del record PKG. Campi
        informativi etichettati: NON sommare PP0+PP1 ne' PKG+DRAM."""
        d = self.read_domains()
        if d is None:
            return None
        out = {name: d[name][0] for name in DOMAIN_NAMES}
        out["ts_100ns"] = d["pkg"][1]
        return out

    def read_domains(self) -> Optional[Dict[str, tuple]]:
        """Una sola IOCTL -> ``dominio -> (cumulata [J], timestamp 100 ns)``.

        Il timestamp e' PER DOMINIO (offset dispari di ogni coppia del
        record), non uno solo: e' cio' che distingue un dominio che ha
        misurato zero da un dominio il cui registro non viene aggiornato
        dal driver. ``read_fields_j`` porta solo il timestamp del PKG
        (``ts_100ns``), quindi chi interrogava PP1 non aveva modo di sapere
        se quel valore fosse vecchio o fosse davvero zero.

        Nessuna conversione ne' scelta di canale qui: la politica (quale
        dominio, con quale regola di freschezza) sta nel chiamante.
        """
        v = self.read_raw()
        if v is None:
            return None
        return {name: (v[2 * i] * PWH_TO_J, v[2 * i + 1])
                for i, name in enumerate(DOMAIN_NAMES)}

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
