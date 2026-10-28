# -*- coding: utf-8 -*-
"""La lettura delle MSR via PawnIO richiede un processo elevato?

L'obbligo della specifica §3.1.2 e' "i privilegi si misurano, non si
deducono": il README di PawnIO non dichiara che, dopo l'installazione del
driver, la lettura sia possibile da un processo normale. Questo strumento
risponde aprendo il backend e leggendo i due registri sotto tre token, e
dichiarando **dal token stesso** che cosa il processo e':

- ``--out`` senza opzioni: il token del processo (la shell da cui si lancia);
- ``--as-medium``: un token ristretto di impersonificazione con il gruppo
  Administrators in deny-only e integrita' media — la forma del processo che
  nasce da un doppio clic di un utente amministratore (UAC filtrato). Il
  controllo di accesso del driver usa il token efficace del thread, quindi
  l'impersonificazione prova la stessa cosa di un processo figlio, senza
  crearne uno.

Per la forma "SAFER normal user" (integrita' alta ma Administrators
deny-only) si usa ``runas``:

    runas /trustlevel:0x20000 "python cwEnergyModular/tools/pawnio_priv_probe.py --out basso.json"

Nessuno dei tre produce il driver: si limita a chiamare ``pawnio_open`` e a
riferire l'esito. Se ``available`` e' vero solo col token elevato, la lettura
richiede elevazione e la riga deve dichiararlo nei ``notes``.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.pawnio_backend import PawnIOMSRBackend  # noqa: E402

INTEGRITY_NAMES = {
    0x0000: "untrusted",
    0x1000: "low",
    0x2000: "medium",
    0x3000: "high",
    0x4000: "system",
}


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", ctypes.c_uint32)]


class _TokenGroups(ctypes.Structure):
    _fields_ = [("GroupCount", ctypes.c_uint32),
                ("Groups", _SidAndAttributes * 1)]


def _api():
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    advapi32.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                          ctypes.POINTER(ctypes.c_void_p)]
    advapi32.OpenProcessToken.restype = ctypes.c_int
    advapi32.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                             ctypes.c_void_p, ctypes.c_uint32,
                                             ctypes.POINTER(ctypes.c_uint32)]
    advapi32.GetTokenInformation.restype = ctypes.c_int
    advapi32.GetSidSubAuthorityCount.argtypes = [ctypes.c_void_p]
    advapi32.GetSidSubAuthorityCount.restype = ctypes.POINTER(ctypes.c_ubyte)
    advapi32.GetSidSubAuthority.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    advapi32.GetSidSubAuthority.restype = ctypes.POINTER(ctypes.c_uint32)
    return advapi32, kernel32


def _identity_from_token(advapi32, token) -> dict:
    out = {}
    buf = ctypes.c_ulong(0)
    size = ctypes.c_uint32(0)
    if advapi32.GetTokenInformation(token, 20, ctypes.byref(buf),  # Elevation
                                    ctypes.sizeof(buf), ctypes.byref(size)):
        out["token_elevation"] = bool(buf.value)
    else:
        out["token_elevation"] = "unreadable"

    need = ctypes.c_uint32(0)
    advapi32.GetTokenInformation(token, 25, None, 0, ctypes.byref(need))  # IL
    raw = ctypes.create_string_buffer(max(need.value, 1))
    if advapi32.GetTokenInformation(token, 25, raw, need.value,
                                    ctypes.byref(need)):
        label = ctypes.cast(raw, ctypes.POINTER(_SidAndAttributes)).contents
        count = advapi32.GetSidSubAuthorityCount(label.Sid).contents.value
        rid = advapi32.GetSidSubAuthority(label.Sid, count - 1).contents.value
        out["integrity_rid"] = f"0x{rid:04X}"
        out["integrity"] = INTEGRITY_NAMES.get(rid, "altro")
    else:
        out["integrity"] = "unreadable"
    return out


def _administrators_sid(advapi32):
    nt_authority = (ctypes.c_ubyte * 6)(0, 0, 0, 0, 0, 5)
    sid = ctypes.c_void_p()
    ok = advapi32.AllocateAndInitializeSid(
        ctypes.byref(nt_authority), 2,
        32, 544, 0, 0, 0, 0, 0, 0, ctypes.byref(sid))  # BUILTIN\Administrators
    if not ok:
        raise OSError(f"AllocateAndInitializeSid: {ctypes.get_last_error()}")
    return sid


def _is_admin_member(advapi32, token) -> str:
    """Stato del gruppo Administrators **nel token**, non nel processo.

    ``enabled`` e' il token elevato; ``deny-only`` e' quello filtrato da UAC o
    ristretto da SAFER. E' questa differenza, non l'integrita', a decidere
    l'accesso al driver quando il suo DACL concede solo ad Administrators.
    """
    advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    advapi32.EqualSid.restype = wintypes.BOOL
    need = ctypes.c_uint32(0)
    advapi32.GetTokenInformation(token, 2, None, 0, ctypes.byref(need))  # Groups
    raw = ctypes.create_string_buffer(max(need.value, 1))
    if not advapi32.GetTokenInformation(token, 2, raw, need.value,
                                        ctypes.byref(need)):
        return "unreadable"
    groups = ctypes.cast(raw, ctypes.POINTER(_TokenGroups)).contents
    entries = ctypes.cast(ctypes.addressof(raw) + _TokenGroups.Groups.offset,
                          ctypes.POINTER(_SidAndAttributes))
    admins = _administrators_sid(advapi32)
    try:
        for i in range(groups.GroupCount):
            entry = entries[i]
            if advapi32.EqualSid(entry.Sid, admins):
                if entry.Attributes & 0x4:      # SE_GROUP_ENABLED
                    return "enabled"
                if entry.Attributes & 0x10:     # SE_GROUP_USE_FOR_DENY_ONLY
                    return "deny-only"
                return f"disabled (0x{entry.Attributes:X})"
        return "absent"
    finally:
        advapi32.FreeSid(admins)


def _process_token(advapi32, kernel32):
    token = ctypes.c_void_p()
    # DUPLICATE serve a DuplicateToken e a CheckTokenMembership, QUERY alle
    # altre informazioni: con il solo QUERY entrambe rispondono access denied
    if not advapi32.OpenProcessToken(kernel32.GetCurrentProcess(),
                                     0x0002 | 0x0008,
                                     ctypes.byref(token)):
        raise OSError(f"OpenProcessToken: {ctypes.get_last_error()}")
    return token


def _medium_restricted_token(advapi32, kernel32):
    """Token di impersonificazione: Administrators deny-only, integrita' media.

    E' la forma del token UAC filtrato di un amministratore; il controllo di
    accesso su un handle usa il token del thread, quindi impersonarlo prova la
    stessa cosa di un processo non elevato senza crearne uno.
    """
    advapi32.CreateRestrictedToken.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32,
        ctypes.POINTER(_SidAndAttributes), ctypes.c_uint32, ctypes.c_void_p,
        ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.CreateRestrictedToken.restype = ctypes.c_int
    advapi32.DuplicateTokenEx.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int,
        ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    advapi32.DuplicateTokenEx.restype = ctypes.c_int
    advapi32.SetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                             ctypes.c_void_p, ctypes.c_uint32]
    advapi32.SetTokenInformation.restype = ctypes.c_int
    advapi32.ImpersonateLoggedOnUser.argtypes = [ctypes.c_void_p]
    advapi32.ImpersonateLoggedOnUser.restype = ctypes.c_int
    advapi32.RevertToSelf.restype = ctypes.c_int
    advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR,
                                                ctypes.POINTER(ctypes.c_void_p)]
    advapi32.ConvertStringSidToSidW.restype = ctypes.c_int
    advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    advapi32.GetLengthSid.restype = ctypes.c_uint32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

    base = _process_token(advapi32, kernel32)
    imp = ctypes.c_void_p()
    restricted = ctypes.c_void_p()
    try:
        # MAXIMUM_ALLOWED: con l'accesso del token originale
        # CreateRestrictedToken risponde ERROR_ACCESS_DENIED
        if not advapi32.DuplicateTokenEx(base, 0x02000000, None, 2, 2,
                                         ctypes.byref(imp)):
            raise OSError(f"DuplicateTokenEx: {ctypes.get_last_error()}")
        admins = _administrators_sid(advapi32)
        try:
            deny = _SidAndAttributes(admins, 0)
            if not advapi32.CreateRestrictedToken(
                    imp, 0x1, 1, ctypes.byref(deny), 0, None, 0, None,
                    ctypes.byref(restricted)):  # DISABLE_MAX_PRIVILEGE
                raise OSError(
                    f"CreateRestrictedToken: {ctypes.get_last_error()}")
        finally:
            advapi32.FreeSid(admins)

        msid = ctypes.c_void_p()
        if not advapi32.ConvertStringSidToSidW("S-1-16-8192",
                                               ctypes.byref(msid)):
            raise OSError(f"ConvertStringSidToSidW: {ctypes.get_last_error()}")
        try:
            label = _SidAndAttributes(msid, 0x20)  # SE_GROUP_INTEGRITY
            size = (ctypes.sizeof(_SidAndAttributes)
                    + advapi32.GetLengthSid(msid))
            if not advapi32.SetTokenInformation(restricted, 25,
                                                ctypes.byref(label), size):
                raise OSError(
                    f"SetTokenInformation: {ctypes.get_last_error()}")
        finally:
            kernel32.LocalFree(msid)
    finally:
        kernel32.CloseHandle(base)
        kernel32.CloseHandle(imp)
    return restricted


def _probe_backend() -> dict:
    backend = PawnIOMSRBackend()
    out = {"probe": backend.probe()}
    try:
        out["available"] = backend.available
        out["reason"] = backend.reason
        out["notes"] = list(backend.notes)
        if backend.available:
            first = backend.read_cumulative_energy_j()
            out["energy_j_first"] = None if first is None else round(first, 6)
            out["quantum_j"] = backend.quantum_j
    finally:
        backend.close()
    return out


def run(as_medium: bool = False) -> dict:
    advapi32, kernel32 = _api()
    out = {"token": "medium (impersonificazione)" if as_medium else "processo"}
    if not as_medium:
        token = _process_token(advapi32, kernel32)
        try:
            out["identity"] = _identity_from_token(advapi32, token)
            out["identity"]["admin_group"] = _is_admin_member(advapi32, token)
        finally:
            kernel32.CloseHandle(token)
        out.update(_probe_backend())
        return out

    token = _medium_restricted_token(advapi32, kernel32)
    if not advapi32.ImpersonateLoggedOnUser(token):
        kernel32.CloseHandle(token)
        raise OSError(f"ImpersonateLoggedOnUser: {ctypes.get_last_error()}")
    try:
        out["identity"] = _identity_from_token(advapi32, token)
        out["identity"]["admin_group"] = _is_admin_member(advapi32, token)
        out.update(_probe_backend())
    finally:
        advapi32.RevertToSelf()
        kernel32.CloseHandle(token)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-medium", action="store_true",
                    help="usa un token UAC filtrato invece di quello del processo")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)
    data = run(as_medium=args.as_medium)
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0 if data.get("available") else 1


if __name__ == "__main__":
    sys.exit(main())
