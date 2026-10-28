#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hwinfo_shm.py — lettore della Shared Memory di HWiNFO (blocco "HWiNFO-x64|SharedMemory").

PERCHE' UN LETTORE "EMPIRICO" E NON UN PARSER DELLO STRUCT
----------------------------------------------------------
Il layout binario della Shared Memory di HWiNFO NON e' documentato nel manuale
locale ("HWiNFO Manual.pdf", cap. 11 "Shared Memory Support (Pro Version)",
p. 59): il testo rimanda a una sezione del forum HWiNFO "richiede un account".
Quindi ogni offset copiato da fonti di terza mano sarebbe un claim non
verificato. Questo modulo invece:

  1. apre la memory-mapped "Global\\HWiNFO-x64|SharedMemory" (il nome reale
     osservato nel blocco e' "HWiNFO-x64|SharedMemory");
  2. cerca le occorrenze ANSI e UTF-16LE del nome sensore ("CPU Package");
  3. dentro la finestra di byte attorno a ogni occorrenza cerca tutti i
     "run" di 4 float allineati a 4 byte con semantica (current, min, max,
     avg) plausibile per un sensore di potenza;
  4. CALIBRA empiricamente: campiona per N secondi e sceglie il candidato
     la cui serie segue il contatore EMI PKG (correlazione >= CORR_MIN e
     scarto medio <= TOL_W). Se nessun candidato passa, solleva errore:
     il sensore NON viene mai usato "perche' dovrebbe funzionare".

Il passo 4 e' anche una verifica di sanita' scientifica: se HWiNFO e EMI
leggono lo stesso dominio RAPL, le due serie devono coincidere a idle; se
divergono, il canale HWiNFO scartato e' documentato, non silurato.

LIMITI CONOSCIUTI (dal manuale, p. 59): nella versione freeware l'opzione
"Shared Memory Support" viene disattivata automaticamente dopo 12 ore di run
e va riabilitata a mano. Va abilitata in: Impostazioni (Main Settings) ->
tab "Generale / Interfaccia utente" -> "Shared Memory Support" (manuale p. 14).

Uso a mano:
  python hwinfo_shm.py            # probe: cosa c'e' nel blocco + candidati
"""
from __future__ import annotations

import ctypes
import statistics
import struct
import sys
import time
from ctypes import wintypes as wt

kernel32 = ctypes.windll.kernel32
kernel32.OpenFileMappingW.restype = wt.HANDLE
kernel32.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
kernel32.MapViewOfFile.restype = wt.LPVOID
kernel32.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD,
                                   ctypes.c_size_t]
kernel32.VirtualQuery.restype = ctypes.c_size_t
kernel32.VirtualQuery.argtypes = [wt.LPCVOID, ctypes.c_void_p, ctypes.c_size_t]
kernel32.CloseHandle.argtypes = [wt.HANDLE]

FILE_MAP_READ = 0x0004
MAP_NAME = "Global\\HWiNFO-x64|SharedMemory"
MAP_NAME_LOCAL = "HWiNFO-x64|SharedMemory"


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p),
                ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", wt.DWORD),
                ("RegionSize", ctypes.c_size_t),
                ("State", wt.DWORD),
                ("Protect", wt.DWORD),
                ("Type", wt.DWORD)]


def open_view():
    """Apre il blocco HWiNFO. Ritorna (addr, size). OSError se non esposto."""
    last = None
    for name in (MAP_NAME, MAP_NAME_LOCAL):
        h = kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
        if not h:
            last = ctypes.GetLastError()
            continue
        addr = kernel32.MapViewOfFile(h, FILE_MAP_READ, 0, 0, 0)
        if not addr:
            kernel32.CloseHandle(h)
            raise OSError(f"MapViewOfFile fallita err={ctypes.GetLastError()}")
        mbi = MEMORY_BASIC_INFORMATION()
        if not kernel32.VirtualQuery(ctypes.c_void_p(addr), ctypes.byref(mbi),
                                     ctypes.sizeof(mbi)):
            raise OSError("VirtualQuery fallita")
        return addr, mbi.RegionSize, h
    raise OSError(f"OpenFileMapping fallita (err={last}): la Shared Memory di "
                  f"HWiNFO non e' esposta. Abilita 'Shared Memory Support' in "
                  f"Impostazioni -> Generale/Interfaccia utente (manuale p.14) "
                  f"e tieni attiva la finestra sensori.")


class Block:
    """Vista sola-lettura del blocco di shared memory."""

    def __init__(self):
        self.addr, self.size, self._h = open_view()

    def raw(self, off, n):
        return ctypes.string_at(self.addr + off, n)

    def floats_at(self, off):
        return struct.unpack("<4f", self.raw(off, 16))

    def close(self):
        kernel32.CloseHandle(self._h)


def _find_all(buf, needle):
    return [i for i in range(len(buf)) if buf.startswith(needle, i)]


def sensor_hits(buf, name="CPU Package"):
    """Occorrenze del nome sensore in ANSI e in UTF-16LE."""
    hits = _find_all(buf, name.encode("ascii"))
    hits += _find_all(buf, name.encode("utf-16-le"))
    return sorted(hits)


def _plausible_power_run(f):
    """(current, min, max, avg) = 4 float con sematica sensore HWiNFO."""
    cur, mn, mx, avg = f
    vals = (cur, mn, mx, avg)
    if any(v != v or v in (float("inf"), float("-inf")) for v in vals):   # NaN
        return False
    if not all(0.0 < v < 400.0 for v in vals):
        return False
    return mn <= cur <= mx and mn - 1 <= avg <= mx + 1


def candidates(buf, hits, window=512, lo=5.0, hi=120.0):
    """Offset (4-byte) di ogni run di 4 float plausibile vicino al nome."""
    out = []
    for h in hits:
        a = max(0, h - 64)
        b = min(len(buf) - 16, h + window)
        off = a - (a % 4)
        while off < b:
            if off % 4 == 0:
                f = struct.unpack("<4f", buf[off:off + 16])
                if _plausible_power_run(f) and lo <= f[0] <= hi:
                    out.append(off)
            off += 4
    return out


class CalibratedSensor:
    """Sensore HWiNFO scelto per coerenza temporale con una sorgente di rif."""

    def __init__(self, ref_fn, name="CPU Package", seconds=12.0, period=0.5,
                 corr_min=0.85, tol_w=3.0, verbose=True):
        self.block = Block()
        buf = self.block.raw(0, self.block.size)
        hits = sensor_hits(buf, name)
        cands = candidates(buf, hits)
        if verbose:
            print(f"[hwinfo] blocco={self.block.size} B, occorrenze '{name}'={len(hits)}, "
                  f"candidati float={len(cands)}")
        if not cands:
            raise RuntimeError("Nessun candidato float nel blocco: layout "
                               "impossibile da calibrare (HWiNFO in esecuzione "
                               "con sensori attivi?)")
        series = {c: [] for c in cands}
        refs = []
        t0 = time.monotonic()
        while time.monotonic() - t0 < seconds:
            for c in cands:
                series[c].append(self.block.floats_at(c)[0])
            refs.append(ref_fn())
            time.sleep(period)
        if len(refs) < 4:
            raise RuntimeError("Calibrazione troppo corta")
        # Il riferimento puo' essere None nei primi campioni (finestra mobile
        # del contatore EMI non ancora piena): si scartano le coppie iniziali.
        keep = [i for i, r in enumerate(refs) if r is not None]
        if len(keep) < 4:
            raise RuntimeError("Riferimento mai disponibile")
        i0 = keep[0]
        refs = [refs[i] for i in keep]
        series = {c: series[c][i0:] for c in cands}
        best, best_score = None, None
        for c in cands:
            s = series[c]
            if statistics.stdev(s) < 0.05:          # valore morto/costante
                continue
            r = _pearson(s, refs)
            d = statistics.mean(abs(a - b) for a, b in zip(s, refs))
            ok = (r is not None and r >= corr_min and d <= tol_w)
            if verbose:
                print(f"[hwinfo] off=0x{c:05x} mean={statistics.mean(s):6.2f} W "
                      f"sd={statistics.stdev(s):5.2f} r={-9.99 if r is None else round(r,3)} "
                      f"|diff|={d:5.2f} W {'-> ACCETTATO' if ok else ''}")
            if ok and (best_score is None or d < best_score):
                best, best_score = c, d
        if best is None:
            raise RuntimeError("Nessun candidato HWiNFO correla col riferimento "
                               "(EMI): canale non usato")
        self.offset = best
        self.name = name
        if verbose:
            print(f"[hwinfo] sensore '{name}' calibrato a offset 0x{best:05x} "
                  f"(scarto medio {best_score:.2f} W vs riferimento)")

    def read(self):
        return self.block.floats_at(self.offset)[0]


def _pearson(a, b):
    n = len(a)
    if n < 3:
        return None
    ma, mb = statistics.mean(a), statistics.mean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((x - mb) ** 2 for x in b) ** 0.5
    if sa == 0 or sb == 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def main():
    try:
        block = Block()
    except OSError as exc:
        print(f"[MANCA] {exc}")
        return 3
    buf = block.raw(0, block.size)
    print(f"[OK] blocco {block.size} B in 0x{block.addr:x}")
    sig = buf[:8]
    print(f"[sig] {sig!r}")
    for nm in ("CPU Package", "Processor", "DRAM", "GPU"):
        hits = sensor_hits(buf, nm)
        print(f"[hits] '{nm}': {len(hits)} occorrenze -> "
              f"{[hex(h) for h in hits[:6]]}")
    hits = sensor_hits(buf, "CPU Package")
    cands = candidates(buf, hits)
    print(f"[cand] {len(cands)} run float plausibili: {[hex(c) for c in cands[:12]]}")
    for c in cands[:8]:
        print(f"   0x{c:05x} -> {tuple(round(v,2) for v in block.floats_at(c))}")
    block.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
