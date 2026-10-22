#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emi_lhm_offset_test.py — TEST DISCRIMINANTE assolute: LHM 'CPU Package' [W]
vs contatore cumulativo EMI (Microsoft PPM), su MINI_IT13 (i9-13900HK, mini
PC senza batteria).

Domanda: la traccia del 22/10 ha mostrato LHM ~ EMI_PKG + 50-58 W su idle e
burner, e il test EMI+Ollama dell'utente da' package 19-29 W dove LHM dice
71-80 W. Chi dice i watt ASSOLUTI veri? Questo run risponde con tre leve:

  1. GRADINI DI POTENZA NOTI: idle -> 2 burner -> 8 burner -> Ollama -> cool.
     Con >=4 punti si fa il fit LHM = a * EMI_PKG + b.
       a ~ 1 e b ~ +50 W  -> offset costante LHM: E_inc/J/token differenziali
                             della tesi SALVI, watt assoluti DA DICHIARARE
                             SOLO come LHM (bias dichiarato).
       a ~ 1,3-2,7        -> errore di SCALA: anche E_inc va corretto.
  2. ENVELOPE INTEL: i9-13900HK base power 45 W, max turbo 95 W (spec Intel).
     Un package idle > 45 W non e' fisicamente plausibile: sanity sui watt.
  3. CONSISTENZA INTERNA EMI: con l'interpretazione pWh (x3,6e-9 J),
     PKG deve restare >= PP0+PP1 e >= DRAM in ogni fase.

Requisiti:
  - ESEGUIRE COME AMMINISTRATORE (LHM senza elevazione legge 0).
  - Ollama opzionale: se l'API su localhost:11434 non risponde, la fase
    Ollama viene saltata con avviso (i restanti gradini restano validi).
  - NON toccare mouse/tastiera durante il run (~5,5 min).

Interprete consigliato:
  C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe

Output:
  experiment_results/emi_lhm_offset_<ts>.csv   (trace 1 Hz)
  stdout: tabella per fase + fit + verdetti.
"""
from __future__ import annotations

import ctypes
import csv
import json
import math
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

PWH_TO_J = 3.6e-9          # 1 pWh = 3,6e-9 J (interpretazione standard EMI v2)
BASE_POWER_W = 45.0        # i9-13900HK Processor Base Power (spec Intel)
MAX_TURBO_W = 95.0         # i9-13900HK Maximum Turbo Power (spec Intel)

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


# ------------------------------------------------------------- LHM helpers --
def lhm_last(hdl_src):
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


def ollama_phase(stop_at, model="llama3.2:3b", tokens=32):
    """Figlio: richieste Ollama sequenziali finche' non scade stop_at."""
    import urllib.request
    body = json.dumps({
        "model": model,
        "prompt": ("Rispondi in italiano in modo breve: spiega perche' e' "
                   "importante verificare le informazioni."),
        "stream": False,
        "options": {"num_predict": tokens, "temperature": 0},
    }).encode("utf-8")
    n = 0
    while time.monotonic() < stop_at:
        try:
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            n += 1
        except Exception:
            return n
    return n


def ollama_available():
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434/api/tags",
                                     timeout=5) as r:
            r.read()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------- piano ----
# (nome, durata s, tipo carico, param)
FASI = [
    ("idle",     45.0, "none",   0),
    ("burn2",    45.0, "burn",   2),
    ("burn8",    45.0, "burn",   8),
    ("cool",     45.0, "none",   0),
    ("ollama",   75.0, "ollama", 1),
    ("cool2",    45.0, "none",   0),
]
TICK_S = 1.0


def linear_fit(xs, ys):
    """Minimi quadrati y = a*x + b; ritorna (a, b, r)."""
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx == 0:
        return None
    a = sxy / sxx
    b = my - a * mx
    syy = sum((y - my) ** 2 for y in ys)
    r = (sxy / math.sqrt(sxx * syy)) if sxx and syy and sxy else float("nan")
    return a, b, r


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
                         "power-integration (Admin?).")

    h = open_emi()
    has_ollama = ollama_available()
    piano = [f for f in FASI if f[2] != "ollama" or has_ollama]
    if not has_ollama:
        print("[ATTENZIONE] Ollama non risponde su localhost:11434: fase "
              "ollama SALTATA. Restano idle/burn2/burn8/cool (fit su 3 punti).")

    print(f"[OK] LHM attivo + EMI aperta. Piano: "
          f"{[(f[0], f[1]) for f in piano]}  tick {TICK_S}s")
    dur_tot = sum(f[1] for f in piano)
    print(f"Durata totale ~{dur_tot/60:.1f} min. NON toccare il PC.")

    try:
        import psutil
        psutil.cpu_percent(interval=None)  # priming
    except ImportError:
        psutil = None

    rows = []
    procs = []
    current_fase = None
    t_start = time.monotonic()
    timeline = []
    acc = 0.0
    for fase, dur, kind, param in piano:
        timeline.append((fase, kind, param, acc, acc + dur))
        acc += dur

    def reap_procs():
        for p in procs:
            try:
                p.join(timeout=2)
            except Exception:
                pass
            if p.is_alive():
                p.terminate()
        procs.clear()

    while True:
        t = time.monotonic() - t_start
        if t >= acc:
            break
        cur = next((e for e in timeline if e[3] <= t < e[4]), None)
        if cur is None:
            time.sleep(TICK_S)
            continue
        fase, kind, param, a, b = cur
        if fase != current_fase:
            # cambio fase: SOLO qui si bonificano i worker della fase
            # precedente (bug run 02:53: senza reap, i procs morti inibivano
            # l'avvio delle fasi di carico successive).
            reap_procs()
            current_fase = fase
        if kind in ("burn", "ollama") and not procs:
            stop_at = time.monotonic() + (b - t)
            if kind == "burn":
                print(f"[{t:6.1f}s] {fase}: {param} burner fino a t={b:.0f}s")
                procs = [mp.Process(target=burn, args=(stop_at,))
                         for _ in range(param)]
            else:
                print(f"[{t:6.1f}s] {fase}: richieste Ollama continue fino a "
                      f"t={b:.0f}s")
                procs = [mp.Process(target=ollama_phase, args=(stop_at,))]
            for p in procs:
                p.start()
        lt, lw = lhm_last(src)
        v = emi_u64s(h)
        cpu = f"{psutil.cpu_percent(interval=None):.1f}" if psutil else ""
        frq = ""
        if psutil:
            try:
                frq = f"{psutil.cpu_freq().current:.0f}"
            except Exception:
                pass
        rows.append((round(t, 2), datetime.now().isoformat(timespec="seconds"),
                    fase,
                    round(lw, 3) if lw is not None else "",
                    *v, cpu, frq))
        time.sleep(TICK_S)

    for p in procs:
        try:
            p.join(timeout=15)
        except Exception:
            pass
    for p in procs:
        if p.is_alive():
            p.terminate()

    SESSION.stop()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = ROOT / "experiment_results" / f"emi_lhm_offset_{ts}.csv"
    out.parent.mkdir(exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["t_mono_s", "t_wall", "fase", "lhm_w",
                    "emi_pkg_pWh", "emi_ts1", "emi_dram_pWh", "emi_ts2",
                    "emi_pp0_pWh", "emi_ts3", "emi_pp1_pWh", "emi_ts4",
                    "cpu_pct", "freq_mhz"])
        w.writerows(rows)
    print(f"\n[OK] trace salvata: {out}  ({len(rows)} righe)")

    # -------------------------------------------------- analisi per fase ----
    # Potenza EMI esatta per fase: delta contatore / delta timestamp EMI
    # (100 ns), sui confini di fase -> niente integrazione.
    def phase_emi_w(rs, i_val, i_ts):
        first, last = rs[0], rs[-1]
        dt = (last[i_ts] - first[i_ts]) * 1e-7
        if dt <= 0.5:
            return None
        return (last[i_val] - first[i_val]) * PWH_TO_J / dt

    print("\n=== per fase: LHM (mediana PI) vs EMI (delta contatore esatto) ===")
    print(f"{'fase':8s} {'LHM W':>8s} {'PKG W':>8s} {'DRAM W':>8s} "
          f"{'PP0 W':>8s} {'PP1 W':>8s} {'LHM-PKG':>8s} {'LHM/PKG':>8s}")
    pts = []
    for fase, kind, param, a, b in timeline:
        fr = [r for r in rows if r[2] == fase and r[3] != ""]
        if len(fr) < 5:
            continue
        lhm = statistics.median(r[3] for r in fr)
        pkg = phase_emi_w(fr, 4, 5)
        dram = phase_emi_w(fr, 6, 7)
        pp0 = phase_emi_w(fr, 8, 9)
        pp1 = phase_emi_w(fr, 10, 11)
        if pkg is None or pkg <= 0:
            continue
        off = lhm - pkg
        ratio = lhm / pkg
        pts.append((fase, lhm, pkg))
        def fmt(x):
            return f"{x:8.1f}" if x is not None else "      n/d"
        print(f"{fase:8s} {lhm:8.1f} {fmt(pkg)} {fmt(dram)} {fmt(pp0)} "
              f"{fmt(pp1)} {off:8.1f} {ratio:8.2f}")
        # coerenza interna EMI
        if pp0 is not None and pp1 is not None:
            s = pp0 + pp1
            flag = "OK" if s <= pkg * 1.15 else "SOSPETTO: PP0+PP1 > PKG"
            print(f"         PP0+PP1 = {s:6.1f} W vs PKG {pkg:6.1f} W -> {flag}")

    # --------------------------------------------------------------- fit ----
    if len(pts) >= 3:
        fit = linear_fit([p[2] for p in pts], [p[1] for p in pts])
        if fit:
            a_, b_, r_ = fit
            print(f"\n=== FIT LHM = a*EMI_PKG + b  ({len(pts)} punti, "
                  f"r={r_:.4f}) ===")
            print(f"a = {a_:.3f}   b = {b_:.1f} W")
            print()
            print("INTERPRETAZIONE:")
            if 0.85 <= a_ <= 1.15 and b_ > 15:
                print("  a~1, b~+50W -> OFFSET COSTANTE nel percorso di "
                      "lettura LHM (o domini inclusi da LHM ed esclusi da "
                      "EMI). Le misure DIFFERENZIALI "
                      "CasualWatt (E_load - E_base, J/token) NON cambiano: "
                      "l'offset si annulla. Dichiarare in tesi i watt "
                      "assoluti come 'package-equivalente LHM', non watt "
                      "fisici, sinche' Linux/RAPL non fissa la scala.")
            elif a_ > 1.15:
                print("  a>1,15 -> errore di SCALA tra i due sensori, non solo "
                      "offset: gli E_inc LHM vanno riscalati di un fattore. "
                      "Linux/RAPL decide quale scala e' vera.")
            elif a_ < 0.85:
                print("  a<0,85 -> LHM comprime rispetto a EMI: ancora "
                      "questione di scala. Linux/RAPL decide.")
            else:
                print("  b < 15 W: nessun offset materiale; i due sensori "
                      "dicono sostanzialmente la stessa cosa.")
    else:
        print("\n[TROPPO POCHI PUNTI] fit non calcolato.")

    # ------------------------------------------------ envelope sanity -------
    idle_pts = [p for p in pts if p[0].startswith("idle")]
    if idle_pts:
        ipkg = idle_pts[0][2]
        ilhm = idle_pts[0][1]
        print(f"\n=== SANITY ENVELOPE (base {BASE_POWER_W:.0f} W / turbo max "
              f"{MAX_TURBO_W:.0f} W, spec Intel 13900HK) ===")
        print(f"  idle: LHM {ilhm:.1f} W | EMI_PKG {ipkg:.1f} W")
        if ilhm > BASE_POWER_W:
            print(f"  LHM idle > base power -> plausibile solo se include "
                  f"domini extra o bias; EMI idle {ipkg:.0f} W e' sotto "
                  f"base power e coerente con un mini PC in idle.")
        if ipkg > BASE_POWER_W:
            print(f"  ATTENZIONE: anche EMI idle > base power; rivedere "
                  f"l'interpretazione unita'.")

    print("\nIl verdetto finale sulla scala resta a Linux/RAPL (unita' "
          "garantite dal kernel). Porta questo CSV nella sessione Linux.")


if __name__ == "__main__":
    mp.freeze_support()
    main()
