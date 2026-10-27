# -*- coding: utf-8 -*-
"""
energy/pawnio_backend.py — Contatore MSR del package via PawnIO (Windows).

Questo backend legge lo stesso registro che alimenta il contatore EMI —
``MSR_PKG_ENERGY_STATUS`` — tramite il driver PawnIO e il suo modulo MSR, e
non lo sostituisce: entra **dopo** EMI come fallback dichiarato, con il token
``pawnio-counter``. Su Windows senza device EMI e con PawnIO presente, la
catena e' ``emi-counter -> pawnio-counter -> unavailable``.

Fatti verificati alla fonte il 28-10-2026
-----------------------------------------
* Registri (Linux ``arch/x86/include/asm/msr-index.h``: ``MSR_RAPL_POWER_UNIT``
  0x606, ``MSR_PKG_ENERGY_STATUS`` 0x611, ``MSR_AMD_RAPL_POWER_UNIT``
  0xC0010299, ``MSR_AMD_PKG_ENERGY_STATUS`` 0xC001029B): **Intel e AMD hanno
  indirizzi diversi** e non si leggono a vicenda. ``0x611`` su AMD non esiste.
* Unita' (``arch/x86/events/rapl.c:609-620``): il campo energia e' sempre
  ``(unit_msr >> 8) & 0x1F``, quantum ``1 / 2^EU`` joule, per entrambi i
  produttori (il modello AMD usa lo stesso decodificatore, ``:837``). Il
  quantum si **legge**, non si assume.
* Contatore (``rapl.c:108`` ``RAPL_CNTR_WIDTH 32``, ``:573`` maschera
  ``0xFFFFFFFF``): 32 bit, quindi il riporto e' a ``2^32`` conteggi. Un calo
  del valore non e' energia negativa: e' un riporto (se il vecchio valore e'
  alto e il nuovo basso) oppure un reset del driver, e i due casi si
  dichiarano separatamente.
* Moduli (``namazso/PawnIO.Modules``, sorgenti ``IntelMSR.p`` e
  ``AMDFamily17.p``): funziona l'IOCTL ``ioctl_read_msr`` con ``in[0]=MSR`` e
  ``out[0]=valore``; il ``main()`` del modulo rifiuta il produttore sbagliato.
  La release 0.2.11 e' l'unica ammessa, con SHA-256 del modulo pinnato: un
  blob diverso non e' stato verificato da nessuno e non si carica.
* Driver (``PawnIOLib.h`` nella cartella di installazione): ``pawnio_open`` ->
  ``pawnio_load`` -> ``pawnio_execute`` -> ``pawnio_close``; la versione della
  libreria si **legge** con ``pawnio_version`` (2.0.0 su questo host), non si
  assume. Il driver installato e' firmato "Microsoft Windows Hardware
  Compatibility Publisher" (``Get-AuthenticodeSignature``, 28-10-2026) e
  gira con HVCI attivo (``HypervisorEnforcedCodeIntegrity\\Enabled = 1``).

Cosa **non** fa
---------------
Non scrive registri (l'IOCTL di scrittura del modulo esiste, qui non si usa),
non somma EMI e MSR, non stima nulla: se il contatore non si legge, il backend
non e' disponibile e la ragione resta scritta. La scala assoluta non e'
arbitrata: lo stesso registro di EMI, quindi un accordo a finestra uguale e'
coerenza di implementazione, non validazione indipendente.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

METHOD_LABEL = "pawnio-counter"
#: La versione della libreria non si dichiara a priori: si legge da
#: ``pawnio_version`` (su questo host 2.0.0). La costante nomina solo i moduli,
#: che sono l'unica parte con un blob verificato.
BACKEND_VERSION = "pawnio-msr/1 (modules 0.2.11)"

#: Release dei moduli ammessa e hash del modulo usato. Il binario non sta nel
#: repository: `tools/fetch_pawnio_modules.py` scarica la release, verifica
#: questo hash e la estrae nella cache dichiarata.
MODULES_VERSION = "0.2.11"
MODULES_ZIP_SHA256 = (
    "43608cb89bc84247fef1368a139013f7d043e17db6d6c8dfc9b46bf0905a81f4"
)
MODULE_SHA256 = {
    "IntelMSR.bin": (
        "d6ed85d65ab17a22f813ef98207d6d537155ee2ded5976a21cb48413c9b92e5f"
    ),
    "AMDFamily17.bin": (
        "dae74615761b78bdf064dfb3e136252ddcc6fc727d88f14738d0e5800d427a91"
    ),
}

#: Mappa produttore -> registri e modulo. Il produttore si legge dal registro
#: di Windows (`VendorIdentifier`), non si deduce dal nome commerciale.
VENDORS = {
    "intel": {
        "unit_msr": 0x606,
        "energy_msr": 0x611,
        "module": "IntelMSR.bin",
        "identifiers": ("genuineintel",),
    },
    "amd": {
        "unit_msr": 0xC0010299,
        "energy_msr": 0xC001029B,
        "module": "AMDFamily17.bin",
        "identifiers": ("authenticamd",),
    },
}

COUNTER_WIDTH = 32
COUNTER_MODULUS = 1 << COUNTER_WIDTH
#: Un calo e' un riporto solo se il vecchio valore e' nella parte alta del
#: contatore e il nuovo nella parte bassa; altrimenti e' un reset e il
#: segmento non produce energia (mai clampato a zero: si dichiara).
WRAP_HIGH_COUNTS = int(COUNTER_MODULUS * 0.75)
WRAP_LOW_COUNTS = int(COUNTER_MODULUS * 0.25)

_HVCI_KEY = (
    r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios"
    r"\HypervisorEnforcedCodeIntegrity"
)
_SERVICE_KEY = r"SYSTEM\CurrentControlSet\Services\PawnIO"
_CPU_KEY = r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
_DEFAULT_DLL = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / (
    "PawnIO") / "PawnIOLib.dll"

_SIG_CACHE: Dict[tuple, dict] = {}
_SIG_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Stato del sistema: HVCI, firma, servizio, produttore
# ---------------------------------------------------------------------------
def hvci_state() -> str:
    """``enabled`` | ``disabled`` | ``unknown`` (chiave assente o illeggibile)."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _HVCI_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "Enabled")
        return "enabled" if int(value) else "disabled"
    except Exception:
        return "unknown"


def driver_path() -> Optional[str]:
    """Percorso del driver installato, da ``ImagePath`` del servizio."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _SERVICE_KEY) as key:
            image, _ = winreg.QueryValueEx(key, "ImagePath")
        image = str(image)
        root = os.environ.get("SystemRoot", r"C:\Windows")
        if image.lower().startswith(r"\systemroot"):
            image = root + image[len(r"\SystemRoot"):]
        return os.path.expandvars(image)
    except Exception:
        return None


def verify_driver_signature(path: str) -> dict:
    """Stato della firma Authenticode, con cache per (path, mtime, size).

    ``Get-AuthenticodeSignature`` restituisce un nome di stato non tradotto
    ("Valid"/"NotSigned"/...), quindi il criterio non dipende dalla lingua
    del sistema. Un errore di PowerShell non si interpreta come firma valida:
    lo stato diventa ``unknown`` e il backend fallisce chiuso.
    """
    try:
        st = os.stat(path)
        key = (os.path.abspath(path), st.st_mtime_ns, st.st_size)
    except OSError:
        return {"status": "unknown", "subject": "", "thumbprint": "",
                "error": "file non accessibile"}
    with _SIG_LOCK:
        cached = _SIG_CACHE.get(key)
    if cached is not None:
        return dict(cached)
    script = (
        "$s = Get-AuthenticodeSignature -LiteralPath $env:CW_SIG_PATH; "
        "[pscustomobject]@{Status=[string]$s.Status;"
        "Subject=$s.SignerCertificate.Subject;"
        "Thumbprint=$s.SignerCertificate.Thumbprint} | ConvertTo-Json -Compress"
    )
    env = dict(os.environ)
    env["CW_SIG_PATH"] = str(path)
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=30, env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        data = json.loads(proc.stdout.strip() or "{}")
        out = {
            "status": str(data.get("Status") or "unknown"),
            "subject": str(data.get("Subject") or ""),
            "thumbprint": str(data.get("Thumbprint") or ""),
        }
    except Exception as exc:  # noqa: BLE001 - dichiarato, non silenzioso
        out = {"status": "unknown", "subject": "", "thumbprint": "",
               "error": f"{type(exc).__name__}"}
    with _SIG_LOCK:
        _SIG_CACHE[key] = dict(out)
    return out


def service_state(name: str = "PawnIO") -> str:
    """Stato del servizio, da SCM: ``running`` | ``stopped`` | ``unknown``."""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

        class _SERVICE_STATUS(ctypes.Structure):
            _fields_ = [
                ("dwServiceType", ctypes.c_ulong),
                ("dwCurrentState", ctypes.c_ulong),
                ("dwControlsAccepted", ctypes.c_ulong),
                ("dwWin32ExitCode", ctypes.c_ulong),
                ("dwServiceSpecificExitCode", ctypes.c_ulong),
                ("dwCheckPoint", ctypes.c_ulong),
                ("dwWaitHint", ctypes.c_ulong),
            ]

        # gli handle SCM sono a larghezza di puntatore: senza restype esplicito
        # ctypes li tronca a 32 bit e OpenServiceW fallisce su handle alti
        advapi32.OpenSCManagerW.argtypes = [
            ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
        advapi32.OpenSCManagerW.restype = ctypes.c_void_p
        advapi32.OpenServiceW.argtypes = [
            ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_ulong]
        advapi32.OpenServiceW.restype = ctypes.c_void_p
        advapi32.QueryServiceStatus.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(_SERVICE_STATUS)]
        advapi32.QueryServiceStatus.restype = ctypes.c_int
        advapi32.CloseServiceHandle.argtypes = [ctypes.c_void_p]
        advapi32.CloseServiceHandle.restype = ctypes.c_int

        scm = advapi32.OpenSCManagerW(None, None, 0x0001)
        if not scm:
            return "unknown"
        try:
            svc = advapi32.OpenServiceW(scm, name, 0x0004)
            if not svc:
                return "stopped"
            try:
                status = _SERVICE_STATUS()
                if not advapi32.QueryServiceStatus(svc, ctypes.byref(status)):
                    return "unknown"
                return {4: "running", 1: "stopped"}.get(
                    int(status.dwCurrentState), "unknown")
            finally:
                advapi32.CloseServiceHandle(svc)
        finally:
            advapi32.CloseServiceHandle(scm)
    except Exception:
        return "unknown"


def detect_vendor() -> Optional[str]:
    """``intel`` | ``amd`` | ``None`` dal ``VendorIdentifier`` di Windows."""
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _CPU_KEY) as key:
            ident, _ = winreg.QueryValueEx(key, "VendorIdentifier")
    except Exception:
        return None
    low = str(ident).strip().lower()
    for vendor, spec in VENDORS.items():
        if low in spec["identifiers"]:
            return vendor
    return None


def default_modules_dir() -> Path:
    """Cache dichiarata dei moduli (fuori dal repository)."""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
    return Path(base) / "CasualWatt" / "pawnio-modules" / MODULES_VERSION


def find_modules_dir(env: Optional[dict] = None) -> Optional[Path]:
    """Directory dei moduli: ``CW_PAWNIO_MODULES``, install, cache."""
    env = os.environ if env is None else env
    candidates = []
    explicit = str(env.get("CW_PAWNIO_MODULES") or "").strip().strip('"')
    if explicit:
        candidates.append(Path(explicit))
    program_files = env.get("ProgramFiles") or r"C:\Program Files"
    candidates.append(Path(program_files) / "PawnIO" / "modules")
    candidates.append(default_modules_dir())
    for cand in candidates:
        if cand.is_dir() and any(cand.glob("*.bin")):
            return cand
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Wrapper di PawnIOLib (sostituibile nei test)
# ---------------------------------------------------------------------------
class PawnIOLibError(Exception):
    """Errore HRESULT di PawnIOLib, con il codice esatto."""

    def __init__(self, call: str, hr: int) -> None:
        self.hr = hr & 0xFFFFFFFF
        super().__init__(f"{call} hr=0x{self.hr:08X}")


class _PawnIOLib:
    """``PawnIOLib.dll`` via ctypes: open/load/execute/close."""

    def __init__(self, dll_path: str) -> None:
        self._dll = ctypes.WinDLL(str(dll_path))
        self._dll.pawnio_version.argtypes = [ctypes.POINTER(ctypes.c_ulong)]
        self._dll.pawnio_version.restype = ctypes.c_long
        self._dll.pawnio_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self._dll.pawnio_open.restype = ctypes.c_long
        self._dll.pawnio_load.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]
        self._dll.pawnio_load.restype = ctypes.c_long
        self._dll.pawnio_execute.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_ulonglong), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t)]
        self._dll.pawnio_execute.restype = ctypes.c_long
        self._dll.pawnio_close.argtypes = [ctypes.c_void_p]
        self._dll.pawnio_close.restype = ctypes.c_long
        self._handle = ctypes.c_void_p()

    @staticmethod
    def _check(call: str, hr: int) -> None:
        if hr < 0:
            raise PawnIOLibError(call, hr)

    def version(self) -> str:
        value = ctypes.c_ulong(0)
        hr = self._dll.pawnio_version(ctypes.byref(value))
        self._check("pawnio_version", hr)
        v = int(value.value)
        return f"{v >> 16}.{(v >> 8) & 0xFF}.{v & 0xFF}"

    def open(self) -> None:
        hr = self._dll.pawnio_open(ctypes.byref(self._handle))
        self._check("pawnio_open", hr)

    def load(self, blob: bytes) -> None:
        buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        hr = self._dll.pawnio_load(self._handle, buf, len(blob))
        self._check("pawnio_load", hr)

    def read_msr(self, msr: int) -> int:
        inp = (ctypes.c_ulonglong * 1)(int(msr))
        out = (ctypes.c_ulonglong * 1)(0)
        written = ctypes.c_size_t(0)
        hr = self._dll.pawnio_execute(
            self._handle, b"ioctl_read_msr", inp, 1, out, 1,
            ctypes.byref(written))
        self._check("ioctl_read_msr", hr)
        if written.value != 1:
            raise PawnIOLibError("ioctl_read_msr(short)", -1)
        return int(out[0])

    def close(self) -> None:
        if self._handle:
            self._dll.pawnio_close(self._handle)
            self._handle = ctypes.c_void_p()


# ---------------------------------------------------------------------------
# Backend
# ---------------------------------------------------------------------------
class PawnIOMSRBackend:
    """Contatore package MSR, con la sonda che decide se usarlo.

    Ogni controllo ha una ragione: se il backend non e' disponibile,
    ``reason`` dice quale controllo ha ceduto e ``notes`` porta i dettagli.
    """

    method = METHOD_LABEL

    def __init__(self, vendor: Optional[str] = None,
                 modules_dir: Optional[Path] = None,
                 dll_path: Optional[Path] = None,
                 expected_hashes: Optional[dict] = None,
                 hvci_reader=hvci_state,
                 signature_reader=verify_driver_signature,
                 service_reader=service_state,
                 driver_path_reader=driver_path,
                 lib_factory=None) -> None:
        self.available = False
        self.reason = ""
        self.notes: list = []
        self.vendor: Optional[str] = None
        self.unit_msr: Optional[int] = None
        self.energy_msr: Optional[int] = None
        self.unit_raw: Optional[int] = None
        self.quantum_j: Optional[float] = None
        self.module_path: Optional[str] = None
        self.module_sha256: Optional[str] = None
        self.driver_path: Optional[str] = None
        self.driver_signature: Optional[dict] = None
        self.hvci: str = "unknown"
        self.service: str = "unknown"
        self.lib_version: str = ""
        self.last_raw: Optional[int] = None
        self._total_j = 0.0
        self._last_raw: Optional[int] = None
        self._lock = threading.Lock()
        self.wraps = 0
        self.resets = 0
        self._lib = None
        self._hashes = dict(MODULE_SHA256 if expected_hashes is None
                            else expected_hashes)

        if not sys.platform.startswith("win"):
            self.reason = "non-Windows"
            return

        self.vendor = vendor if vendor is not None else detect_vendor()
        if self.vendor not in VENDORS:
            self.reason = "vendor_unknown"
            self.notes.append(
                "produttore non riconosciuto dal registro: non si sceglie un "
                "registro MSR per analogia")
            return
        spec = VENDORS[self.vendor]
        self.unit_msr = int(spec["unit_msr"])
        self.energy_msr = int(spec["energy_msr"])

        self.service = service_reader()
        if self.service != "running":
            self.reason = "service_not_running"
            self.notes.append(f"servizio PawnIO: {self.service}")
            return

        self.driver_path = driver_path_reader()
        self.hvci = hvci_reader()
        if not self.driver_path:
            self.reason = "driver_path_unknown"
            return
        sig = signature_reader(self.driver_path)
        self.driver_signature = dict(sig)
        if self._signature_rejection(sig):
            self.reason, msg = self._signature_rejection(sig)
            self.notes.append(msg)
            return

        mod_dir = Path(modules_dir) if modules_dir is not None else find_modules_dir()
        module = spec["module"]
        if mod_dir is None:
            self.reason = "module_missing"
            self.notes.append(
                "moduli PawnIO non trovati: eseguire "
                "tools/fetch_pawnio_modules.py --install")
            return
        path = Path(mod_dir) / module
        if not path.is_file():
            self.reason = "module_missing"
            self.notes.append(f"modulo assente: {path}")
            return
        digest = sha256_file(path)
        self.module_sha256 = digest
        self.module_path = str(path)
        if digest != self._hashes.get(module):
            self.reason = "module_hash_mismatch"
            self.notes.append(
                f"{module}: SHA-256 {digest[:16]}... diverso dal blob "
                f"verificato ({MODULES_VERSION}); non si carica un modulo "
                "non verificato")
            return

        factory = lib_factory or _PawnIOLib
        try:
            lib = factory(str(dll_path or _DEFAULT_DLL))
            lib.open()
            lib.load(path.read_bytes())
            self.lib_version = lib.version()
        except Exception as exc:  # noqa: BLE001 - ragione dichiarata
            self.reason = "pawnio_unavailable"
            self.notes.append(f"PawnIOLib/load: {type(exc).__name__}: {exc}")
            try:
                lib.close()
            except Exception:
                pass
            return
        self._lib = lib

        try:
            self.unit_raw = int(lib.read_msr(self.unit_msr))
        except Exception as exc:  # noqa: BLE001
            self.reason = "unit_unreadable"
            self.notes.append(
                f"lettura 0x{self.unit_msr:X}: {type(exc).__name__}: {exc}")
            self._close_lib()
            return
        exp = (self.unit_raw >> 8) & 0x1F
        if self.unit_raw in (0, 0xFFFFFFFF) or exp > 31:
            self.reason = "unit_unreadable"
            self.notes.append(
                f"0x{self.unit_msr:X} = 0x{self.unit_raw:016X}: campo EU "
                f"assente o implausibile, unita' non derivabile")
            self._close_lib()
            return
        self.quantum_j = 1.0 / float(1 << exp)

        try:
            self._last_raw = int(lib.read_msr(self.energy_msr))
            self.last_raw = self._last_raw
        except Exception as exc:  # noqa: BLE001
            self.reason = "energy_unreadable"
            self.notes.append(
                f"lettura 0x{self.energy_msr:X}: {type(exc).__name__}: {exc}")
            self._close_lib()
            return

        self.available = True
        self.notes.append(
            f"PawnIO: {self.vendor}, modulo {module} ({MODULES_VERSION}), "
            f"unita' 0x{self.unit_msr:X}=0x{self.unit_raw:X} -> "
            f"quantum {self.quantum_j:.9g} J, contatore "
            f"0x{self.energy_msr:X} a 32 bit, HVCI {self.hvci}, firma "
            f"{sig.get('status')}")

    # -- decisioni della sonda ------------------------------------------------
    def _signature_rejection(self, sig: dict):
        """None se la firma passa i criteri, altrimenti (ragione, messaggio)."""
        status = str(sig.get("status") or "unknown")
        subject = str(sig.get("subject") or "")
        microsoft = "microsoft" in subject.lower()
        if status != "Valid":
            return ("driver_signature_invalid",
                    f"firma del driver {status}: un driver non verificato "
                    "non entra nella catena")
        if self.hvci in ("enabled", "unknown") and not microsoft:
            return ("driver_signer_not_microsoft",
                    f"firma valida ma firmatario non Microsoft ({subject!r}): "
                    "con HVCI attivo o non determinabile il driver deve "
                    "essere firmato Microsoft")
        return None

    def _close_lib(self) -> None:
        if self._lib is not None:
            try:
                self._lib.close()
            except Exception:
                pass
            self._lib = None

    # -- lettura --------------------------------------------------------------
    def read_raw(self) -> Optional[int]:
        if not self.available or self._lib is None:
            return None
        try:
            value = int(self._lib.read_msr(self.energy_msr))
        except Exception as exc:  # noqa: BLE001
            self.notes.append(
                f"lettura 0x{self.energy_msr:X} fallita: {type(exc).__name__}")
            return None
        self.last_raw = value
        return value

    def read_cumulative_energy_j(self) -> Optional[float]:
        """Energia cumulata dall'apertura [J], con riporto e reset dichiarati."""
        with self._lock:
            raw = self.read_raw()
            if raw is None:
                return None
            if self._last_raw is None:
                self._last_raw = raw
                return self._total_j
            old = self._last_raw
            if raw >= old:
                self._total_j += (raw - old) * self.quantum_j
            elif old >= WRAP_HIGH_COUNTS and raw <= WRAP_LOW_COUNTS:
                delta = COUNTER_MODULUS - old + raw
                self._total_j += delta * self.quantum_j
                self.wraps += 1
                self.notes.append(
                    f"riporto del contatore a 32 bit ({old} -> {raw}): "
                    f"aggiunti {delta} conteggi, non energia negativa")
            else:
                self.resets += 1
                self.notes.append(
                    f"contatore tornato indietro ({old} -> {raw}) senza "
                    "riporto: reset del driver o sospensione, il segmento "
                    "non produce energia")
            self._last_raw = raw
            return self._total_j

    def probe(self) -> dict:
        """Esito della sonda, con i criteri espliciti e il verdetto."""
        sig = self.driver_signature or {}
        return {
            "pass": bool(self.available),
            "reason": self.reason,
            "vendor": self.vendor,
            "service": self.service,
            "hvci": self.hvci,
            "driver_path": self.driver_path,
            "driver_signature": sig.get("status", "unknown"),
            "driver_signer": sig.get("subject", ""),
            "module_version": MODULES_VERSION,
            "module_path": self.module_path,
            "module_sha256": self.module_sha256,
            "lib_version": self.lib_version,
            "unit_msr": (f"0x{self.unit_msr:X}" if self.unit_msr else None),
            "unit_raw": (f"0x{self.unit_raw:X}" if self.unit_raw else None),
            "energy_msr": (f"0x{self.energy_msr:X}"
                           if self.energy_msr else None),
            "quantum_j": self.quantum_j,
            "wraps": self.wraps,
            "resets": self.resets,
            "notes": list(self.notes),
        }

    def close(self) -> None:
        self._close_lib()
        self.available = False
