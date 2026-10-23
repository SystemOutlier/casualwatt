#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
observer_cost_probe.py
======================
Quantifica il COSTO DELL'OSSERVATORE: quanto pesa, sul livello assoluto di
potenza del package, tenere aperta una seconda istanza di LibreHardwareMonitor
-la GUI- mentre il profiler CasualWatt sta gia' leggendo il package.

Perche' esiste: `smoke_test_readpath.py` e `lhm_trace_3min.py` dichiarano fra i
requisiti "LHM chiuso altrove (un solo Computer() aperto alla volta)". I run
post-fix del 23/10 (14:15-16:04) sono stati eseguiti CON la GUI aperta (PID
14828, avviato 14:06:05): il vincolo documentato non era soddisfatto, quindi il
livello assoluto di quelle finestre include un monitoring extra. Serve un
numero, non un sospetto.

Metodo ( idle puro, nessun Ollama, nessun burner):
  - EMI  = arbitro del livello: delta contatore PKG / durata reale della
    finestra. EMI non viene toccato dalla GUI e legge il package intero, perci
    o' il consumo della GUI LO INCLUDE: la differenza fra le due condizioni
    e' il costo dell'osservatore.
  - LHM power-integration = il nostro thread di lettura: media dei campioni e
    INTERVALLO REALE fra i campioni, per vedere se la GUI allunga anche la
    risoluzione (0,3025 s contro 0,3272 s osservati fra i run).
  - CPU time del processo GUI (GetProcessTimes) = conferma di meccanismo: se la
    GUI consuma k secondi di CPU nella finestra, il suo contributo e' del
    stesso ordine del delta di EMI.

Uso (processo ELEVATO, LHM Power invisibili senza Admin):
  C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe -u \
      observer_cost_probe.py <tag>
  tag = es. "gui_open" oppure "gui_closed"; finisce nel nome del JSON.

Non tocca la GUI: si limita a MISURARLA (letture di tempo di CPU, niente
chiudi/riapri). La chiusura della GUI la fa l'operatore fra le due esecuzioni.
"""
from __future__ import annotations

import ctypes
import csv
import json
import statistics
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

from energy.energy_session import SESSION  # noqa: E402

DURATA_S = 90.0
TICK_S = 0.25
PWH_TO_J = 3.6e-9
TS100NS_TO_S = 1e-7
GUI_NAME = "LibreHardwareMonitor.exe"

# ------------------------------------------------------------------ EMI ----
kernel32 = ctypes.windll.kernel32
kernel32.CreateFileW.restype = ctypes.c_void_p
kernel32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint,
                                 ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                 ctypes.c_void_p]
kernel32.DeviceIoControl.restype = ctypes.c_bool
kernel32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.c_void_p, ctypes.c_uint,
                                     ctypes.POINTER(ctypes.c_uint),
                                     ctypes.c_void_p]

DEVICE = (r'\\?\acpi#genuineintel_-_intel64_family_6_model_186_-_13th_gen_'
          r'intel(r)_core(tm)_i9-13900hk#0#{45bd8344-7ed6-49cf-a440-c276c933b053}')
IOCTL_GET_MEASUREMENT = 0x0022400C


def open_emi():
    h = kernel32.CreateFileW(DEVICE, 0x80000000, 3, None, 3, 0x80, None)
    if h is None or ctypes.c_ssize_t(h).value == -1:
        raise OSError(f"CreateFileW EMI fallita (err={ctypes.GetLastError()})")
    return h


def emi_u64s(h):
    inbuf = ctypes.create_string_buffer(16)
    struct.pack_into("<H", inbuf, 0, 0)
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not kernel32.DeviceIoControl(h, IOCTL_GET_MEASUREMENT, inbuf, 16,
                                    out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    return struct.unpack("<8Q", out.raw[:64])


# ------------------------------------------------------- GUI CPU time -------
# kernel32 esporta solo le varianti W/A: senza il suffisso esplicito il nome
# "Process32First" non esiste e il binding fallirebbe in modo opaco.
kernel32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
kernel32.CreateToolhelp32Snapshot.argtypes = [ctypes.c_uint, ctypes.c_uint]
kernel32.Process32FirstW.restype = ctypes.c_bool
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.OpenProcess.argtypes = [ctypes.c_uint, ctypes.c_bool, ctypes.c_uint]
kernel32.GetProcessTimes.restype = ctypes.c_bool
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

TH32CS_SNAPPROCESS = 0x2


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", ctypes.c_uint),
                ("cntUsage", ctypes.c_uint),
                ("th32ProcessID", ctypes.c_uint),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", ctypes.c_uint),
                ("cntThreads", ctypes.c_uint),
                ("th32ParentPID", ctypes.c_uint),
                ("pcPriority", ctypes.c_long),
                ("dwFlags", ctypes.c_uint),
                ("szExeFile", ctypes.c_wchar * 260)]


def find_pid(name: str):
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap is None or ctypes.c_ssize_t(snap).value == -1:
        return None
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    pid = None
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.strip().lower() == name.lower():
                pid = int(entry.th32ProcessID)
                break
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return pid


def cpu_seconds(pid: int):
    """Secondi di CPU (user+kernel) del processo, o None se introvabile."""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    try:
        creation = ctypes.c_ulonglong(0)
        exit_t = ctypes.c_ulonglong(0)
        kernel = ctypes.c_ulonglong(0)
        user = ctypes.c_ulonglong(0)
        if not kernel32.GetProcessTimes(h, ctypes.byref(creation),
                                        ctypes.byref(exit_t),
                                        ctypes.byref(kernel),
                                        ctypes.byref(user)):
            return None
        return (user.value + kernel.value) * TS100NS_TO_S
    finally:
        kernel32.CloseHandle(h)


# ------------------------------------------------------------------- main ---
def main() -> int:
    tag = (sys.argv[1] if len(sys.argv) > 1 else "probe").strip() or "probe"
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] non elevato: i sensori Power LHM leggono 0 senza Admin.")
        return 2

    SESSION.start()
    src = SESSION._source
    if src.method != "power-integration":
        raise SystemExit(f"[ERRORE] metodo '{src.method}', atteso power-integration")

    pid = find_pid(GUI_NAME)
    cpu0 = cpu_seconds(pid) if pid else None
    print(f"[OSSERVATORE] {GUI_NAME}: pid={pid} "
          f"cpu_cumulata={('%.3f s' % cpu0) if cpu0 is not None else '-'}")

    h = open_emi()
    rows = []
    t_start = time.monotonic()
    while True:
        t = time.monotonic() - t_start
        if t >= DURATA_S:
            break
        with src._pi_lock:
            buf = list(src._pi_samples)
        lt, lw = (buf[-1] if buf else (None, None))
        v = emi_u64s(h)
        rows.append((round(t, 3), datetime.now().isoformat(timespec="milliseconds"),
                    round(lt, 3) if lt is not None else "",
                    round(lw, 3) if lw is not None else "",
                    len(buf), *v))
        time.sleep(TICK_S)

    ts_wall = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = ROOT / "experiment_results" / f"observer_cost_{tag}_{ts_wall}.csv"
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["t_mono_s", "t_wall", "lhm_t", "lhm_w", "pi_samples",
                    "emi_v0", "emi_ts8"])
        w.writerows(rows)

    # --- analisi: EMI a finestra identica, intervallo reale del thread PI ---
    first, last = rows[0], rows[-1]
    e_emi_j = (last[5] - first[5]) * PWH_TO_J
    s_emi = (last[6] - first[6]) * TS100NS_TO_S
    p_emi = e_emi_j / s_emi if s_emi > 0 else None

    pi_ts = [r[2] for r in rows if r[2] != ""]
    pi_ws = [r[3] for r in rows if r[3] != ""]
    intervalli = []
    try:
        with src._pi_lock:
            full = [s[0] for s in src._pi_samples]
        intervalli = [round(b - a, 4) for a, b in zip(full, full[1:]) if b > a]
    except Exception:
        pass

    pid1 = find_pid(GUI_NAME)
    cpu1 = cpu_seconds(pid1) if pid1 else None
    gui_cpu = (cpu1 - cpu0) if (cpu0 is not None and cpu1 is not None) else None

    riassunto = {
        "tag": tag,
        "timestamp": ts_wall,
        "durata_finestra_s": round(s_emi, 3) if s_emi else None,
        "emi_pkg_W": round(p_emi, 4) if p_emi else None,
        "lhm_pi_media_W": (round(statistics.mean(pi_ws), 4) if pi_ws else None),
        "lhm_pi_n_campioni": len(pi_ts),
        "pi_intervallo_mediano_s": (round(statistics.median(intervalli), 4)
                                    if intervalli else None),
        "pi_intervallo_dichiarato_s": 0.05,
        "gui_pid": pid,
        "gui_cpu_s_nella_finestra": (round(gui_cpu, 3) if gui_cpu is not None else None),
        "righe_csv": len(rows),
    }
    out_json = ROOT / "experiment_results" / f"observer_cost_{tag}_{ts_wall}.json"
    out_json.write_text(json.dumps(riassunto, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    print("\n===== RISULTATI =====")
    for k, v in riassunto.items():
        print(f"  {k:30} = {v}")
    print(f"[OK] salvati: {out_csv.name}, {out_json.name}")

    # Il salvataggio precede SEMPRE il teardown: su MINI_IT13 pythonnet lancia
    # un'eccezione CLR non gestita in chiusura (exit 127, osservata 23/10).
    try:
        SESSION.stop()
    except BaseException as e:                        # noqa: BLE001
        print(f"[teardown, non conta] {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
