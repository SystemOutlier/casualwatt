#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
emi_50ms_probe.py — il limite di risoluzione e' del registro o del nostro thread?
=================================================================================

Domanda posta (cap.3.3 e cap.5.5 della tesi, e ricerca_metodo.DOCX):
CasualWatt dichiara un campionamento a 50 ms ma ne misura 0,28-0,34 s. Il
lavoro ha finora attribuito il gap al carico del thread di integrazione LHM.
Resta pero' aperta la domanda precedente e piu' forte:

    SE leggessimo il contatore EMI direttamente, a 50 ms,
    il registro darebbe un delta non nullo ad ogni lettura?

Se la risposta e' NO, allora la cadenza di acquisizione NON e' il collo di
bottiglia: il collo e' la granularita' del contatore, e nessun refactor del
thread di sampling puo' risolvere le finestre brevi (un prefill di 0,23 s).
Se la risposta e' SI, allora il percorso di lettura va rivisto.

Questo probe risponde senza passare da LibreHardwareMonitor: apre il device
EMI con ctypes e legge l'IOCTL in un loop a scadenza nominale di 50 ms.
Non tocca nessun altro file e non sostituisce nessun percorso in produzione.

COSA MISURA
-----------
Per ciascuno dei quattro canali del record EMI (8 uint64: valore + timestamp
a 100 ns, intervallati):

  offset  0 / ts  8  -> PKG   (package, intero dominio)
  offset 16 / ts 24  -> DRAM  (memoria; su questo host vale spesso 0)
  offset 32 / ts 40  -> PP0   (core)
  offset 48 / ts 56  -> PP1   (iGPU)

  ATTENZIONE NON ADDITIVITA' (confermata da Beyer & Wendler 2020, LNCS 12079,
  e rilettura dei nostri dati): PP0 + PP1 != PKG e PKG + DRAM != "tutto".
  PP0 e PP1 sono SOTTOINSIEMI di PKG. Le colonne sono reportate per
  confronto per fase, MAI sommate fra loro.

  - frequenza reale del loop (la scadenza dichiarata vs il dt campionato):
    su Windows un time.sleep(0.05) non e' un timer HW, e questo e' parte
    della risposta, non un difetto da nascondere;
  - percentuale di delta consecutivi nulli, per canale, alla cadenza reale;
  - quantitizzazione minima: MCD dei delta non nulli (il "ticchettio" del
    contatore) in pWh e millijoule;
  - finestra minima osservabile: la piu' corta k-intervalli per cui TUTTI i
    delta di quella larghezza sono non nulli.

DUE FASI DI CARICO
------------------
Il contatore e' un accumulatore: a parita' di granularita' di bit, un dominio
che consuma piu' potenza accumula piu' energia per unita' di tempo, quindi un
delta non nullo diventa PIU' facile sotto carico. Misurare solo a riposo
sottostimerebbe la risoluzione. Per questo il probe gira due fasi: riposo, poi
load generato da PROCESSI di spin in puro Python (default 4, niente Ollama: il
caricamento del modello aggiunge 6-6,6 s fuori fase, osservato nel CSV di
produzione, e inquinerebbe la geometria).

REQUISITI
---------
  - terminale ELEVATO (l'IOCTL EMI e' identico a quello usato da
    four_way_test.py: senza Admin CreateFileW fallisce);
  - nessuna dipendenza da CasualWatt, oltre allo standard library.

Uso:
  python emi_50ms_probe.py                       # 40 s riposo + 40 s load
  python emi_50ms_probe.py --interval 0.05 --seconds 30 --threads 8
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import math
import statistics
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "experiment_results"

DEVICE = (r'\\?\acpi#genuineintel_-_intel64_family_6_model_186_-_13th_gen_'
          r'intel(r)_core(tm)_i9-13900hk#0#{45bd8344-7ed6-49cf-a440-c276c933b053}')
IOCTL_GET_MEASUREMENT = 0x0022400C
PWH_TO_J = 3.6e-9            # 1 pWh = 1e-12 Wh * 3600 s/h

# (nome, indice nel tuple degli 8 uint64 per il valore, indice del timestamp)
CHANNELS = [("PKG", 0, 1), ("DRAM", 2, 3), ("PP0", 4, 5), ("PP1", 6, 7)]

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


def open_emi():
    h = kernel32.CreateFileW(DEVICE, 0x80000000, 3, None, 3, 0x80, None)
    if h is None or ctypes.c_ssize_t(h).value == -1:
        raise OSError(f"CreateFileW EMI fallita (err={ctypes.GetLastError()}) "
                      "-- riesegui da terminale ELEVATO")
    return h


def emi_u64s(h):
    """Gli 8 uint64 del record EMI: (v0, ts0, v1, ts1, v2, ts2, v3, ts3).

    NB: i quattro canali sono PKG, DRAM, PP0, PP1 e PP0/PP1 stanno DENTRO PKG.
    Non sommarli: vedi il paragrafo 'attenzione non additivita'' nel docstring
    del modulo.
    """
    inbuf = ctypes.create_string_buffer(16)
    struct.pack_into("<H", inbuf, 0, 0)
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not kernel32.DeviceIoControl(h, IOCTL_GET_MEASUREMENT, inbuf, 16,
                                    out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    raw = out.raw[:max(got.value, 64)]
    return struct.unpack("<8Q", raw[:64])


# ---------------------------------------------------------------- carico ----
def _spin_worker(stop_evt, seconds):
    """Busy-work in un PROCESSO separato.

    Il caricatore NON puo' essere un thread Python: con i thread di spin il GIL
    affama il thread che campiona e la cadenza reale collassa (misurato nel
    smoke test del 23/10: mediana 31,6 ms con burst da 0,0 a 346,8 ms su 4
    thread). Un processo per core lascia il sampler indisturbato -- e' anche il
    motivo per cui questo file usa multiprocessing con contesto 'spawn'.
    NB: il carico genera comunque calore e sposta la baseline; e' il caso worst
    in cui serve la risposta, non una condizione pulita.
    """
    deadline = time.monotonic() + seconds
    x = 1.0
    while not stop_evt.is_set() and time.monotonic() < deadline:
        for _ in range(50000):
            x = (x * 1.000000001 + 1.0) % 1e9
    return x


class SpinLoad:
    """Carico CPU deterministico N-processi, senza dipendenze esterne.

    Il contatore EMI e' un accumulatore: a parita' di bit, piu' potenza significa
    piu' energia per unita' di tempo, quindi delta non nulli PIU' facili. Per
    questo il probe gira anche una fase di load: misurare solo a riposo
    sovrastimerebbe il limite del registro.
    """

    def __init__(self, processes: int, seconds: float):
        import multiprocessing as _mp
        self._ctx = _mp.get_context("spawn")
        self.processes = processes
        self.seconds = seconds
        self._stop = self._ctx.Event()
        self._procs: list = []

    def __enter__(self):
        for _ in range(self.processes):
            p = self._ctx.Process(target=_spin_worker,
                                  args=(self._stop, self.seconds + 15.0),
                                  daemon=True)
            p.start()
            self._procs.append(p)
        return self

    def __exit__(self, *exc):
        self._stop.set()
        for p in self._procs:
            p.join(timeout=3.0)
            if p.is_alive():
                p.terminate()
        return False


# ---------------------------------------------------------------- sampling --
def sample(h, seconds: float, interval_s: float, label: str, phase: str):
    """Loop a scadenza: legge l'IOCTL ogni `interval_s` per `seconds` secondi.

    La scadenza e' assoluta (next += interval) per non accumulare drift, ma il
    dt REALE viene registrato: e' una delle due risposte che cercavamo.
    """
    rows = []
    t0 = time.monotonic()
    next_due = t0 + interval_s
    n = 0
    while True:
        now = time.monotonic()
        if now - t0 >= seconds:
            break
        v = emi_u64s(h)
        rows.append((now - t0, phase, v))
        n += 1
        due = next_due
        next_due += interval_s
        remaining = due - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    print(f"  [{label}] {n} letture in {rows[-1][0]:.2f} s "
          f"-> cadenza reale {rows[-1][0]/max(len(rows)-1,1)*1000:.1f} ms "
          f"(dichiarata {interval_s*1000:.0f} ms)")
    return rows


def gcd_of(vals):
    vals = [int(v) for v in vals]
    if not vals:
        return 0
    g = vals[0]
    for v in vals[1:]:
        g = math.gcd(g, v)
        if g == 1:
            return 1
    return g


def analyse(rows, interval_s):
    """Tabella di risoluzione per canale.

    Ritorna una lista di dict, una riga per canale, con:
      delta_nulli_pct      % di delta fra campioni consecutivi pari a zero
      quantum_pwh          MCD dei delta non nulli (ticchettio del contatore)
      finestra_ms_min      piu' corta k*dt con tutti i delta non nulli
      copertura            % di finestre di quella larghezza non nulle
    """
    t = [r[0] for r in rows]
    dt = [t[i + 1] - t[i] for i in range(len(t) - 1)]
    out = []
    for name, vi, ti in CHANNELS:
        ser = [r[2][vi] for r in rows]
        d = [ser[i + 1] - ser[i] for i in range(len(ser) - 1)]
        nz = [x for x in d if x > 0]
        neg = sum(1 for x in d if x < 0)
        zero = sum(1 for x in d if x == 0)
        best = None
        for k in (1, 2, 3, 4, 6, 8, 12, 16, 20):
            if k >= len(d):
                break
            dd = [ser[i + k] - ser[i] for i in range(len(ser) - k)]
            z = sum(1 for x in dd if x == 0)
            cover = 100.0 * (len(dd) - z) / len(dd)
            if best is None and cover >= 99.9:
                med = statistics.median([dt[i] for i in range(max(0, len(dt) - k))])
                best = (k, k * med * 1000.0, cover)
        rate = [d[i] * PWH_TO_J / dt[i] for i in range(len(d)) if dt[i] > 0]
        out.append({
            "canale": name,
            "letture": len(rows),
            "delta_nulli_pct": round(100.0 * zero / max(len(d), 1), 2),
            "delta_negativi": neg,
            "min_pwh": min(nz) if nz else None,
            "med_pwh": round(statistics.median(nz)) if nz else None,
            "max_pwh": max(nz) if nz else None,
            "quantum_pwh": gcd_of(nz[:400]) if nz else None,
            "quantum_mj": round(gcd_of(nz[:400]) * PWH_TO_J * 1000, 4) if nz else None,
            "finestra_k": best[0] if best else None,
            "finestra_ms": round(best[1], 1) if best else None,
            "potenza_mediana_w": round(statistics.median(rate), 3) if rate else None,
            "potenza_min_w": round(min(rate), 3) if rate else None,
            "potenza_max_w": round(max(rate), 3) if rate else None,
            "tot_j_finestra": round((ser[-1] - ser[0]) * PWH_TO_J, 3),
        })
    return out, dt


def print_report(analysis, dt, interval_s):
    real = statistics.median(dt) * 1000 if dt else float("nan")
    print(f"\nCadenza reale mediana: {real:.1f} ms "
          f"(dichiarata {interval_s*1000:.0f} ms, "
          f"min {min(dt)*1000:.1f} / max {max(dt)*1000:.1f})")
    print("\n--- risoluzione per canale (fase considerata: quella indicata) ---")
    hdr = (f"{'canale':6} {'nulli%':>7} {'quantum_pWh':>12} {'quantum_mJ':>11} "
           f"{'fin_k':>6} {'fin_ms':>8} {'P_med_W':>8} {'tot_J':>9}")
    print(hdr)
    for a in analysis:
        print(f"{a['canale']:6} {a['delta_nulli_pct']:7.2f} "
              f"{str(a['quantum_pwh']):>12} {str(a['quantum_mj']):>11} "
              f"{str(a['finestra_k']):>6} {str(a['finestra_ms']):>8} "
              f"{str(a['potenza_mediana_w']):>8} {a['tot_j_finestra']:9.3f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--interval", type=float, default=0.05,
                    help="cadenza dichiarata del loop [s] (default 0.05)")
    ap.add_argument("--seconds", type=float, default=40.0,
                    help="durata di OGNI fase [s] (default 40)")
    ap.add_argument("--processes", type=int, default=4,
                    help="processi di spin nella fase di load (default 4)")
    ap.add_argument("--skip-load", action="store_true",
                    help="esegui solo la fase a riposo")
    args = ap.parse_args()

    print(f"[INFO] python: {sys.executable}")
    print(f"[INFO] apertura EMI: {DEVICE[:60]}...")
    try:
        h = open_emi()
    except OSError as e:
        print(f"[ERRORE] {e}")
        return 2

    ts_wall = datetime.now().isoformat(timespec="seconds")
    phases = [("riposo", 0)]
    if not args.skip_load:
        phases.append((f"load{args.processes}", args.processes))

    all_rows = []
    for label, n_proc in phases:
        print(f"\n[FASE] {label}: {args.seconds:.0f} s "
              f"a {args.interval*1000:.0f} ms")
        if n_proc == 0:
            rows = sample(h, args.seconds, args.interval, label, label)
        else:
            with SpinLoad(n_proc, args.seconds):
                time.sleep(3.0)   # stabilizzazione del carico
                rows = sample(h, args.seconds, args.interval, label, label)
        all_rows.extend(rows)

    # ---- scrittura grezzo (riproducibilita': ogni riga e' una lettura) -----
    OUT_DIR.mkdir(exist_ok=True)
    stem = datetime.now().strftime("emi_50ms_probe_%Y%m%d_%H%M%S")
    csv_path = OUT_DIR / f"{stem}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["t_mono_s", "t_wall_run", "fase", "interval_dichiarato_s",
                    "emi_v0", "emi_ts8", "emi_v16", "emi_ts24",
                    "emi_v32", "emi_ts40", "emi_v48", "emi_ts56"])
        for (t, phase, v) in all_rows:
            w.writerow([f"{t:.6f}", ts_wall, phase, args.interval, *v])
    print(f"\n[OK] CSV grezzo: {csv_path}")

    # ---- analisi per fase ---------------------------------------------------
    for label, _ in phases:
        rows = [r for r in all_rows if r[1] == label]
        if len(rows) < 5:
            print(f"[ATTENZIONE] fase '{label}' con {len(rows)} letture: "
                  "analisi saltata")
            continue
        analysis, dt = analyse(rows, args.interval)
        print(f"\n=== FASE {label} ===")
        print_report(analysis, dt, args.interval)

    print("\n[LETTURA DELLA RISPOSTA]")
    print("  Se alla cadenza reale i delta PKG sono nulli in una frazione")
    print("  consistente dei casi, allora 50 ms di sampling NON aggiunge")
    print("  informazione: il limite e' del registro, e la tesi deve scriverlo")
    print("  come proprieta' dello strumento (cap.3.3), non come nostro difetto.")
    print("  Se invece i delta sono quasi sempre non nulli, il collo e' il")
    print("  nostro percorso di lettura (thread LHM) e va rivisto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
