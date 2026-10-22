#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lhm_trace_3min.py — traccia SIMULTANEE LHM 'CPU Package' [W] e IOCTL EMI
(Microsoft PPM) nello stesso processo, per identificare quale campo EMI e'
il contatore PKG e in quale unita'.

Perche' un processo solo: le due serie escono con lo stesso
time.monotonic() per riga -> allineamento perfetto, niente cross-correlazione
tra finestre di orologi diversi.

Fasi automatiche (durata totale ~160 s, modificabile in FASI):
  IDLE 40 s  ->一切 fermo, niente mouse/tastiere
  LOAD 40 s  -> 8 worker busy-loop (carico noto, forte)
  COOLD 40 s -> di nuovo idle
  IDLE2 40 s -> conferma

Requisiti:
  - ESEGUIRE COME AMMINISTRATORE (LHM richiede elevazione; l'EMI no, ma
    se non siamo elevati LHM legge 0 -> righe inutili).
  - NIENTE Ollama attivo: solo noi e il burner.
  - interprete:
    C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe

Output: experiment_results/lhm_emi_trace_<ts>.csv con colonne:
  t_mono; t_wall; fase; lhm_t; lhm_w; emi_v0; emi_ts8; emi_v16; emi_ts24;
  emi_v32; emi_ts40; emi_v48; emi_ts56
Analisi a fine run: regression/medie per fase -> campo EMI che scala come
la W di LHM e fattore unita' (W_emi = delta_emi/unita_s per secondo).
"""
from __future__ import annotations

import ctypes
import csv
import multiprocessing as mp
import statistics
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))
from energy.energy_session import SESSION  # noqa: E402

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
                                     ctypes.POINTER(ctypes.c_uint), ctypes.c_void_p]

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
    raw = out.raw[:max(got.value, 64)]
    return struct.unpack("<8Q", raw[:64])


# ------------------------------------------------------------- LHM (ADMIN) --
def lhm_last(hdl_src):
    """Ultimo campione (t, W) del thread power-integration di CasualWatt."""
    try:
        with hdl_src._pi_lock:
            buf = list(hdl_src._pi_samples)
        return buf[-1] if buf else (None, None)
    except Exception:
        return (None, None)


def burn(stop_at):
    x = 0
    while time.monotonic() < stop_at:
        x = (x + 1) % 1000003


FASI = [("idle", 40.0), ("load", 40.0), ("cool", 40.0), ("idle2", 40.0)]
TICK_S = 0.25


def main():
    import os
    if os.name == "nt":
        try:
            if not ctypes.windll.shell32.IsUserAnAdmin():
                print("[ERRORE] processo NON elevato: LHM legge 0 senza Admin. "
                      "Riavvia come Amministratore.")
                sys.exit(2)
        except AttributeError:
            pass

    SESSION.start()
    src = SESSION._source
    if src.method != "power-integration":
        raise SystemExit(f"[ERRORE] metodo attivo '{src.method}', atteso "
                         "power-integration (Admin? Ollama non c'entra).")

    h = open_emi()
    print("[OK] LHM attivo (power-integration) + EMI aperta.")
    print(f"FASI: {FASI}  tick {TICK_S}s. NON toccare il PC (anche durante "
          "load: il burner e' il carico).")

    rows = []
    procs = []
    t_start = time.monotonic()

    timeline = []
    acc = 0.0
    for fase, dur in FASI:
        timeline.append((fase, acc, acc + dur))
        acc += dur

    while True:
        t = time.monotonic() - t_start
        if t >= acc:
            break
        fase = next(f for (f, a, b) in timeline if a <= t < b)
        if fase == "load" and not procs:
            stop_at = time.monotonic() + (timeline[1][2] - t)  # fine fase load
            print(f"[{t:6.1f}s] LOAD: 8 worker fino a t={timeline[1][2]:.0f}s")
            procs = [mp.Process(target=burn, args=(stop_at,)) for _ in range(8)]
            for p in procs:
                p.start()
        lt, lw = lhm_last(src)
        v = emi_u64s(h)
        rows.append((round(t, 3), datetime.now().isoformat(timespec="milliseconds"),
                     fase,
                     round(lt, 3) if lt is not None else "",
                     round(lw, 3) if lw is not None else "",
                     *v))
        time.sleep(TICK_S)
    for p in procs:
        try:
            p.join(timeout=10)
        except Exception:
            pass
    # sicurezza: se qualche worker e' ancora vivo (clock monotonic figlio),
    # uccidilo: non deve sopravvivere alla trace.
    for p in procs:
        if p.is_alive():
            p.terminate()

    SESSION.stop()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "experiment_results" / f"lhm_emi_trace_{ts}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["t_mono_s", "t_wall", "fase", "lhm_t", "lhm_w",
                    "emi_v0", "emi_ts8", "emi_v16", "emi_ts24",
                    "emi_v32", "emi_ts40", "emi_v48", "emi_ts56"])
        w.writerows(rows)
    print(f"[OK] trace salvata: {out}  ({len(rows)} righe)")

    # ---------------- analisi rapida: quale campo EMI traccia LHM? ----------
    def by_fase(fase):
        return [r for r in rows if r[2] == fase and r[4] != ""]

    print("\n=== riepilogo per fase (LHM vs pendenza campi EMI, se µJ->W) ===")
    for fase, a, b in timeline:
        fr = by_fase(fase)
        if not fr:
            continue
        lhms = [r[4] for r in fr if isinstance(r[4], float)]
        if not lhms:
            continue
        # pendenza tra prima e ultima riga della fase per campo valore
        v0 = fr[0]; v1 = fr[-1]
        dt = v1[0] - v0[0]
        if dt <= 0:
            continue
        d = {f: (v1[c] - v0[c]) / dt for c, f in ((5, "emi_v0"), (7, "emi_v16"),
                                                  (9, "emi_v32"), (11, "emi_v48"))}
        print(f"{fase:6s} LHM {statistics.median(lhms):6.1f} W | " +
              " | ".join(f"{k} {d[k]/1e6:8.1f} (W se uJ)" for k in d))
    print("\nIl campo la cui pendenza (con un fattore unita' costante) segue"
          "\nLHM fase-per-fase (idle<load<idle) e' il PKG. Dividi LHM/pendenza"
          "\nper ricavare il fattore unita'.")


if __name__ == "__main__":
    mp.freeze_support()
    main()
