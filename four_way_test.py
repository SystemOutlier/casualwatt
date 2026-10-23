#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
four_way_test.py — Triangolo (in realta' quadrato) di misura su Windows 11.

Stessa scalinata A-B-A del protocollo v2, con QUATTRO sorgenti attive insieme:

  1. EMI nativo (ctypes, IOCTL 0x22400C)  -> contatore cumulativo PKG [pWh]
     (riferimento di scala: confermato da HWiNFO + PL1/PL2 il 23/10;
      NON richiede amministratore)
  2. CasualWatt SESSION (LHM power-integration) -> W "package-equivalente-LHM"
     (richiede AMMINISTRATORE; e' il backend di produzione, e il suo read-path
      e' stato corretto il 23/10: _read_power_w_direct matchava per nome il
      sensore Temperature omonimo "CPU Package" di IntelCpu.cs:401 invece
      dell'omonimo Power (:480) e integrava gradi come joule)
  3. CodeCarbon EmissionsTracker (3.2.9) -> il SUO valore, che su MINI_IT13
     E' UN MODELLO e non una misura (verificato 23/10: Intel Power Gadget non
     istanzia sul 13900HK e il modello CPU non e' nel dataset -> avviso
     "4 W per thread x 20 = 80 W", poi modalita' cpu_load:
     P = 80*(0.1 + 0.9*load^3); il backend realmente scelto viene stampato
     nel log e salvato nel JSON). NB: non legge gli MSR, quindi NON entra in
     conflitto con LHM (vincolo "un solo consumer MSR").
  4. HWiNFO 8.54 (freeware) via Shared Memory, SE esposta: il sensore "CPU
     Package" viene letto con hwinfo_shm.CalibratedSensor, che NON usa offset
     copiati da fonti di terza mano (il manuale locale, cap. 11 p. 59, rimanda
     per il layout a una sezione del forum HWiNFO con account) ma calibra
     empiricamente il candidato che segue il contatore EMI (r >= 0,85 e
     |scarto| <= 3 W su ~12 s). Se la Shared Memory non c'e' o nessun
     candidato correla, lo script CONTINUA senza HWiNFO e lo registra nel
     JSON: in alternativa l'utente puo' usare File>Logging (1 s) e allineare
     il CSV per wall-clock (colonna "Potenza totale CPU [W]", 221 del log
     idle del 23/10).
     Dove si attiva (verificato sul manuale locale, NON a memoria):
     Impostazioni (Main Settings) -> tab "Generale / Interfaccia utente" ->
     "Shared Memory Support" (screenshot p. 14), NON "Remote Sensor Display".
     Cap. 11 p. 59: nella versione freeware l'opzione si disattiva da sola
     dopo 12 ore di run e va riabilitata a mano.
     Attenzione metodologica (manuale p. 6, "Other Software": sconsigliato
     far girare altro software di monitoraggio insieme): il polling di
     HWiNFO e' ESSO UN CARICO, quindi la quarta sorgente non e' un testimone
     passivo ma perturba la misura che confronta.

Vincolo di metodologia (misurato 23/10, non ipotesi): CodeCarbon 3.2.9 scrive
UNA riga cumulativa per coppia start()/stop() -- `api_call_interval` di default
vale 300 misure, quindi i campioni intermedi non arrivano su CSV. Per avere un
numero PER FASE si faziona start()/stop() ai confini di fase e si differenziano
i cumulati `duration` [s] e `cpu_energy` [kWh].

Fasi: warm-up (fuori misura) -> idle 45 s -> load 90 s (richette Ollama
sequenziali, num_predict 32, temperature 0, protocollo identico al ps1 v2)
-> idle2 45 s. Tick 1 Hz (LHM istantaneo + EMI + HWiNFO), con l'asse
time.monotonic salvato come colonna "mono".

Analisi a FINESTRA UGUALE (dal 23/10, dopo il fix del read-path LHM): per ogni
fase il thread di integrazione di produzione viene snapshotted ai confini di
fase e integrato con regola trapezoidale su [inizio fase, fine fase], mentre il
contatore cumulativo EMI viene interpolato linearmente sull'asse "mono" dei
tick sulla STESSA finestra. E' il confronto che risponde alla domanda "LHM e
EMI danno gli stessi Joule?", senza che il risultato dipenda dal punto in cui
il tick 1 Hz capita (sul load ogni richiesta Ollama blocca il tick di ~3,65 s,
e il confronto campione-istantaneo-vs-media dava un rapporto 1,16 spurio).

Output:
  experiment_results/four_way_<ts>.csv       riga per tick
  experiment_results/four_way_<ts>_pi.csv    buffer di integrazione per fase
                                             (e' la prova dell'integrale)
  experiment_results/four_way_<ts>.json      riepilogo per fase + J/token EMI
                                             + LHM/EMI a finestra uguale
  experiment_results/codecarbon_four_way/emissions.csv  (cumulati per fase)

Uso (elevato, dalla shell NORMALe — compare il prompt UAC):
  Start-Process -Verb RunAs -FilePath powershell -ArgumentList `
    '-NoProfile','-ExecutionPolicy','Bypass','-File','.\four_way_run_elevato.ps1'
Log completo: experiment_results\four_way_console_log.txt
"""
from __future__ import annotations

import ctypes
import json
import statistics
import struct
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

DEVICE = (r'\\?\acpi#genuineintel_-_intel64_family_6_model_186_-_13th_gen_'
          r'intel(r)_core(tm)_i9-13900hk#0#{45bd8344-7ed6-49cf-a440-c276c933b053}')
IOCTL_GET_MEASUREMENT = 0x0022400C
PWH_TO_J = 3.6e-9          # 1 pWh = 1e-12 Wh * 3600 s/h = 3.6e-9 J
KWH_TO_J = 3.6e6           # 1 kWh = 3.6e6 J

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:3b"
PROMPT = ("Rispondi in italiano in modo breve: spiega perche' e' importante "
          "verificare le informazioni.")
NUM_PREDICT = 32

FASI = [("idle", 45.0), ("load", 90.0), ("idle2", 45.0)]
TICK_S = 1.0

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
        raise OSError(f"CreateFileW EMI fallita (err={ctypes.GetLastError()})")
    return h


def emi_pkg(h):
    """Ritorna (AbsoluteEnergy_pWh, AbsoluteTime_100ns) del canale PKG (record 0).

    NON ADDITIVITA' DEI DOMINI (Beyer & Wendler 2020, LNCS 12079, e nostri
    dataset): il record EMI espone PKG, DRAM, PP0, PP1, ma PP0 (core) e PP1
    (iGPU) sono SOTTOINSIEMI di PKG. Sommarli per ottenere "il package" e'
    sbagliato per costruzione, e PKG + DRAM non e' "tutto il chip" perche' DRAM
    ricade gia' nel budget di package su questa piattaforma (qui vale 0, misurato
    dal probe emi_50ms_probe.py del 23/10: 0 letture non nulle su 800).
    Questo canale e' l'unico usato nei rapporti perche' e' il confine che il
    nostro metodo dichiara (package), non perche' sia il piu' grande.
    """
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not kernel32.DeviceIoControl(h, IOCTL_GET_MEASUREMENT, None, 0,
                                    out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return v[0], v[1]


class EMIW:
    """Potenza EMI [W] su finestra mobile: il contatore e' cumulativo e ha
    granularita' finita (delta su segmenti ~0 danno valori assurdi, misurato
    22/10: 151 W), quindi si usa sempre una finestra >= MIN_WIN."""

    MIN_WIN = 1.5

    def __init__(self, h):
        self.h = h
        self.hist = []          # [(ts100ns, pwh)]

    def power_W(self):
        pj, pt = emi_pkg(self.h)
        self.hist.append((pt, pj))
        if len(self.hist) > 400:
            del self.hist[:-200]
        old = None
        for (pt0, pj0) in self.hist:
            if (pt - pt0) * 1e-7 >= self.MIN_WIN:
                old = (pt0, pj0)
            else:
                break
        if old is None:
            return None
        dt = (pt - old[0]) * 1e-7
        return None if dt <= 0 else (pj - old[1]) * PWH_TO_J / dt


def line_at(pairs, t):
    """Valore interpolato linearmente di una lista [(x, y)] monotona in x ai bordi.

    Fuori dal range: None (nessuna estrapolazione) -- la finestra va clipped
    dal chiamante.
    """
    import bisect
    xs = [p[0] for p in pairs]
    if t < xs[0] or t > xs[-1]:
        return None
    i = bisect.bisect_left(xs, t)
    if i <= 0:
        return pairs[0][1]
    if i >= len(pairs):
        return pairs[-1][1]
    (t0, y0), (t1, y1) = pairs[i - 1], pairs[i]
    if t1 == t0:
        return y1
    return y0 + (y1 - y0) * (t - t0) / (t1 - t0)


def integrate_j(buf, t0, t1):
    """Joule trapezoidali del buffer (t [mono], W [W]) sulla finestra [t0, t1].

    Clippa la finestra a cio' che il buffer copre davvero e lo dichiara
    ( copertura_s ), perche' il thread di integrazione parte con SESSION.start()
    e il buffer si accorcia da solo a 4000 campioni: chiedere una finestra
    tagliata fuori era l'errore del run 20261023_142253, dove i campi cw_*
    uscivano nulli su 113 righe su 114.
    Ritorna i bordi NON arrotondati: il bordo destro dell'ultima fase coincide
    con l'ultimo tick, e arrotondarlo al alto (round(x, 3) su un mono letto con
    4 decimali) lo mette FUORI dall'asse del contatore EMI -- e' l'errore che
    nel run 20261023_143603 ha lasciato idle2 senza numeri.
    """
    if len(buf) < 2:
        return None
    a, b = max(t0, buf[0][0]), min(t1, buf[-1][0])
    if b - a < 1.0:
        return None
    wa, wb = line_at(buf, a), line_at(buf, b)
    if wa is None or wb is None:
        return None
    pts = [(a, wa)] + [(t, w) for (t, w) in buf if a < t < b] + [(b, wb)]
    e = sum((pts[i][1] + pts[i + 1][1]) / 2.0 * (pts[i + 1][0] - pts[i][0])
            for i in range(len(pts) - 1))
    inside = [t for (t, _) in buf if a <= t <= b]
    gaps = [t2 - t1_ for (t1_, t2) in zip(inside, inside[1:])]
    return {"J": e,
            "t0": a, "t1": b,
            "copertura_s": b - a,
            "n_campioni": len(inside),
            "dt_mediano_s": statistics.median(gaps) if gaps else None,
            "ritagliato_s": (t1 - t0) - (b - a)}


def ollama_generate():
    body = json.dumps({"model": MODEL, "prompt": PROMPT, "stream": False,
                       "options": {"num_predict": NUM_PREDICT,
                                   "temperature": 0}}).encode("utf-8")
    req = urllib.request.Request(OLLAMA_URL, data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode("utf-8"))
    return int(resp.get("eval_count") or 0)


class CCScope:
    """CodeCarbon con un ciclo start/stop per fase e cumulati differenziali.

    `duration` e `cpu_energy` della riga CSV sono CUMULATIVI dall'avvio del
    tracker (misurato 23/10: il secondo run riporta duration 10,9 s dopo un
    primo run da 5,9 s). Il valore di fase e' quindi delta(E)/delta(t).
    """

    def __init__(self, cc_dir: Path) -> None:
        self.dir = cc_dir
        self.t = None
        self.backend = []
        self.rows = []
        self.notes = []
        self._prev = None          # (cum_duration_s, cum_cpu_J)

    def start(self) -> None:
        if self.t is None:
            try:
                from codecarbon import EmissionsTracker
            except Exception as exc:
                self.notes.append(f"import: {type(exc).__name__}: {exc}")
                return
            # NB: in 3.2.x offline_mode non esiste piu' -- offline e' il
            # default quando non si passa emissions_endpoint.
            self.t = EmissionsTracker(output_dir=str(self.dir),
                                      project_name="four_way")
        try:
            self.t.start()
            self.backend = [repr(x) for x in getattr(self.t, "_hardware", [])]
        except Exception as exc:
            self.notes.append(f"start: {type(exc).__name__}: {exc}")
            self.t = None

    def end_phase(self, fase: str) -> None:
        if self.t is None:
            return
        try:
            self.t.stop()
        except Exception as exc:
            self.notes.append(f"stop({fase}): {type(exc).__name__}: {exc}")
            return
        cur = self._last_row()
        if cur is None:
            self.notes.append(f"riga CSV assente dopo la fase {fase}")
            return
        dur, ej = cur
        if self._prev is None:
            dd, dej = dur, ej
        else:
            dd, dej = dur - self._prev[0], ej - self._prev[1]
        self._prev = (dur, ej)
        self.rows.append({"fase": fase,
                          "cum_duration_s": round(dur, 3),
                          "delta_duration_s": round(dd, 3),
                          "delta_cpu_energy_J": round(dej, 2),
                          "cpu_power_W_fase": (round(dej / dd, 2) if dd > 0 else None)})

    def _last_row(self):
        import csv as _csv
        files = sorted(self.dir.glob("**/emissions*.csv"),
                       key=lambda p: p.stat().st_mtime)
        if not files:
            return None
        with open(files[-1], encoding="utf-8-sig") as f:
            rd = list(_csv.DictReader(f))
        if not rd:
            return None
        r = rd[-1]
        try:
            # 3.2.9: cpu_energy [kWh] = solo CPU (modello). energy_consumed
            # [kWh] include anche il modello RAM (20 W fissi) -> scartato perche'
            # non e' package CPU.
            return (float(r["duration"]), float(r["cpu_energy"]) * KWH_TO_J)
        except (TypeError, ValueError, KeyError):
            return None


def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] serve Amministratore: senza elevazione LHM legge 0 e "
              "il CasualWatt SESSION non parte. Usa four_way_run_elevato.ps1.")
        sys.exit(2)

    from energy.energy_session import SESSION  # noqa: E402
    SESSION.start()
    src = SESSION._source
    if src.method != "power-integration":
        raise SystemExit(f"[ERRORE] metodo attivo '{src.method}', atteso power-integration")

    h = open_emi()
    print("[OK] EMI + CasualWatt(LHM) attivi.")

    # ---- quarta sorgente: HWiNFO via Shared Memory (opzionale) ------------
    emi_w = EMIW(h)
    hw = None
    hw_note = ""
    try:
        sys.path.insert(0, str(ROOT))
        from hwinfo_shm import CalibratedSensor      # noqa: E402
        print("Calibrazione sensore HWiNFO 'CPU Package' vs EMI (~12 s)...")
        hw = CalibratedSensor(emi_w.power_W, verbose=True)
        print("[OK] HWiNFO Shared Memory attiva e calibrata.")
    except Exception as exc:
        hw_note = f"{type(exc).__name__}: {exc}"
        print(f"[WARN] HWiNFO non disponibile -> 3 sorgenti. {hw_note}")

    cc_dir = ROOT / "experiment_results" / "codecarbon_four_way"
    cc_dir.mkdir(parents=True, exist_ok=True)
    cc = CCScope(cc_dir)
    cc.start()
    if cc.t is not None:
        print("[OK] CodeCarbon attivo; backend = " + ", ".join(cc.backend))
    else:
        print("[WARN] CodeCarbon non avviato: " + "; ".join(cc.notes))

    print("Warm-up modello (fuori misura)...")
    ollama_generate()

    ticks = []
    tokens = {}
    pi_snaps = {}
    fase_win = {}
    wall_zero = None

    def tick(fase, t_rel):
        """Un campione LHM (buffer power-integration) + EMI (contatore) + HWiNFO."""
        try:
            with src._pi_lock:
                buf = list(src._pi_samples)
            lhm_w = buf[-1][1] if buf else None
        except Exception:
            lhm_w = None
        pj, pt = emi_pkg(h)
        try:
            hw_w = None if hw is None else round(hw.read(), 3)
        except Exception:
            hw_w = None
        ticks.append({"fase": fase, "t_s": round(t_rel, 3),
                      "mono": round(time.monotonic(), 4),
                      "wall": datetime.now().isoformat(timespec="milliseconds"),
                      "lhm_w": None if lhm_w is None else round(lhm_w, 3),
                      "hw_w": hw_w,
                      "emi_pkg_pwh": pj, "emi_pkg_ts100ns": pt})

    for fase, dur in FASI:
        if wall_zero is None:
            wall_zero = datetime.now().isoformat(timespec="milliseconds")
        t0 = time.monotonic()
        print(f"--- fase {fase} ({dur:.0f} s) ---")
        while True:
            t = time.monotonic() - t0
            if t >= dur:
                break
            if fase == "load":
                try:
                    tokens[fase] = tokens.get(fase, 0) + ollama_generate()
                except Exception as exc:
                    print(f"[WARN] ollama: {exc}")
                if time.monotonic() - t0 >= dur:
                    break
            tick(fase, t)
            time.sleep(TICK_S)
        t_end = time.monotonic()
        fase_win[fase] = (t0, t_end)
        try:
            with src._pi_lock:
                pi_snaps[fase] = list(src._pi_samples)
        except Exception:
            pi_snaps[fase] = []
        cc.end_phase(fase)

    tok = tokens.get("load", 0)
    SESSION.stop()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = ROOT / "experiment_results" / f"four_way_{ts}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("t_s;wall;mono;fase;lhm_w;hw_w;emi_pkg_pwh;emi_pkg_ts100ns\n")
        for r in ticks:
            lw = "" if r["lhm_w"] is None else r["lhm_w"]
            hwv = "" if r["hw_w"] is None else r["hw_w"]
            f.write(f"{r['t_s']};{r['wall']};{r['mono']};{r['fase']};{lw};{hwv};"
                    f"{r['emi_pkg_pwh']};{r['emi_pkg_ts100ns']}\n")

    # Il buffer di integrazione di produzione: prova dell'integrale. Gli
    # snapshot per fase sono CUMULATIVI (il buffer non si azzera a fine fase),
    # quindi si uniscono per chiave mono e si scrive una sola serie monotona.
    out_pi = ROOT / "experiment_results" / f"four_way_{ts}_pi.csv"
    uni = {}
    for fase, _ in FASI:
        for (t, w) in pi_snaps.get(fase) or []:
            uni[round(t, 4)] = w
    with open(out_pi, "w", encoding="utf-8") as f:
        f.write("mono;w\n")
        for t in sorted(uni):
            f.write(f"{t:.4f};{uni[t]}\n")

    # ---- analisi per fase -------------------------------------------------
    def phase_stats(fase):
        fr = [r for r in ticks if r["fase"] == fase]
        if len(fr) < 2:
            return None
        dj = (fr[-1]["emi_pkg_pwh"] - fr[0]["emi_pkg_pwh"]) * PWH_TO_J
        dt = (fr[-1]["emi_pkg_ts100ns"] - fr[0]["emi_pkg_ts100ns"]) * 1e-7
        lhms = [r["lhm_w"] for r in fr if r["lhm_w"] is not None]
        hws = [r["hw_w"] for r in fr if r["hw_w"] is not None]
        # FINESTRA UGUALE: il buffer di integrazione di produzione (asse
        # time.monotonic, intervallo reale ~0,3 s misurato: vedi
        # cw_dt_mediano_s) e il contatore EMI cumulativo sono portati sulla
        # STESSA finestra della fase, con interpolazione lineare del contatore
        # sull'asse mono dei tick (metodo counter_at di srum_emi_perminute.py)
        # e ritaglio ai bordi che il buffer copre per davvero. Serve perche' il
        # confronto "campione istantaneo LHM vs media EMI sul delta dei tick"
        # dipende dal punto in cui il tick capita: sul load il tick e' bloccato
        # dalla richiesta Ollama (dt mediano 3,98 s, run 20261023_144252) e
        # valeva 1,1465 contro l'1,0055 dell'integrale a finestra uguale.
        series = [(r["mono"], r["emi_pkg_pwh"]) for r in ticks]
        a, b = fase_win[fase]
        # intersezione con l'asse dei tick: il mono del tick e' letto DOPO la
        # IOCTL, quindi il confine di fase teoricamente coincide con un
        # istante ~pochi ms prima del primo campione EMI disponibile (e ~pochi
        # ms dopo l'ultimo). Senza questo clip line_at andrebbe fuori range.
        a = max(a, series[0][0])
        b = min(b, series[-1][0])
        win = integrate_j(pi_snaps.get(fase) or [], a, b) if b - a >= 1.0 else None
        cw_j = cw_s = cw_w = None
        cw_t0 = cw_t1 = None
        emi_j_win = emi_w_win = None
        cw_n = cw_ritagliato = cw_dt = None
        win_note = "buffer vuoto o sovrapposizione < 1 s alla fase"
        if win:
            tw0, tw1 = win["t0"], win["t1"]
            # pin ai bordi dell'asse dei tick: il confine di fase e' definito
            # dai tick, quindi il bordo destro dell'ultima fase E' l'ultimo
            # tick -- run 143603: arrotondarlo verso l'alto lo portava fuori
            # asse e idle2 restava senza numeri.
            tw0 = min(max(tw0, series[0][0]), series[-1][0])
            tw1 = min(max(tw1, series[0][0]), series[-1][0])
            p0, p1 = line_at(series, tw0), line_at(series, tw1)
            if p0 is None or p1 is None:
                win_note = "bordo fuori dall'asse dei tick"
            elif tw1 <= tw0 or p1 < p0:
                win_note = f"finestra o contatore non monotoni ({tw1 - tw0:.3f} s)"
            else:
                cw_s = tw1 - tw0
                cw_j, cw_n = win["J"], win["n_campioni"]
                cw_t0, cw_t1 = tw0, tw1
                cw_dt, cw_ritagliato = win["dt_mediano_s"], win["ritagliato_s"]
                cw_w = cw_j / cw_s
                emi_j_win = (p1 - p0) * PWH_TO_J
                emi_w_win = emi_j_win / cw_s
                win_note = ""
        r3 = lambda x: None if x is None else round(x, 3)
        r2 = lambda x: None if x is None else round(x, 2)
        # Il MODO DEBOLE, nello stesso run: valore LHM istantaneo al tick b
        # contro la media EMI sull'intervallo (tick a -> tick b).
        coppie = [(b_["lhm_w"],
                   (b_["emi_pkg_pwh"] - a_["emi_pkg_pwh"]) * PWH_TO_J /
                   ((b_["emi_pkg_ts100ns"] - a_["emi_pkg_ts100ns"]) * 1e-7),
                   b_["mono"] - a_["mono"])
                  for a_, b_ in zip(fr, fr[1:])
                  if b_["lhm_w"] is not None
                  and b_["emi_pkg_ts100ns"] > a_["emi_pkg_ts100ns"]
                  and b_["emi_pkg_pwh"] > a_["emi_pkg_pwh"]]
        m_ist = statistics.mean([c[0] for c in coppie]) if coppie else None
        m_emi = statistics.mean([c[1] for c in coppie]) if coppie else None
        return {"n": len(fr),
                "emi_J": round(dj, 2),
                "emi_meter_s": round(dt, 2),
                "emi_W": round(dj / dt, 2) if dt > 0 else None,
                "lhm_mean_W": round(statistics.mean(lhms), 2) if lhms else None,
                "lhm_sd_W": round(statistics.stdev(lhms), 2) if len(lhms) > 1 else None,
                "modo_debole_lhm_W": r2(m_ist),
                "modo_debole_emi_W": r2(m_emi),
                "modo_debole_rapporto": (round(m_ist / m_emi, 4) if m_emi else None),
                "modo_debole_dt_mediano_tick_s": (r2(statistics.median([c[2] for c in coppie]))
                                                  if coppie else None),
                "modo_debole_n_coppie": len(coppie),
                "cw_J_fase": r3(cw_j),
                "cw_s_fase": r3(cw_s),
                "cw_t0_mono": r3(cw_t0),
                "cw_t1_mono": r3(cw_t1),
                "cw_W_finestra_uguale": r2(cw_w),
                "cw_n_campioni": cw_n,
                "cw_dt_mediano_s": r3(cw_dt),
                "cw_ritagliato_s": r3(cw_ritagliato),
                "cw_win_note": win_note or None,
                "emi_J_finestra_uguale": r3(emi_j_win),
                "emi_W_finestra_uguale": r2(emi_w_win),
                "rapporto_cw_div_EMI_finestra_uguale": (
                    round(cw_j / emi_j_win, 4)
                    if cw_j is not None and emi_j_win else None),
                "hw_n": len(hws),
                "hw_mean_W": round(statistics.mean(hws), 2) if hws else None,
                "hw_sd_W": round(statistics.stdev(hws), 2) if len(hws) > 1 else None}

    stats = {f: phase_stats(f) for f, _ in FASI}

    # Diagnosticone: lo STESSO run letto nei due modi. "modo_debole" = valore
    # LHM al tick contro media EMI sull'intervallo tra due tick (il metodo che
    # sul load valeva ~1,15); "finestra uguale" = integrale del buffer vs
    # contatore interpolato sulla stessa finestra di fase.
    print("\n--- LHM vs EMI, stesso run, due modi di confrontare ---")
    for fase, _ in FASI:
        s = stats.get(fase) or {}
        print(f"{fase:6s} istantaneo: LHM {s.get('modo_debole_lhm_W')} W / "
              f"EMI {s.get('modo_debole_emi_W')} W = "
              f"{s.get('modo_debole_rapporto')} (dt mediano tick "
              f"{s.get('modo_debole_dt_mediano_tick_s')} s, "
              f"n {s.get('modo_debole_n_coppie')} coppie)"
              f"   | finestra uguale: LHM {s.get('cw_W_finestra_uguale')} W / "
              f"EMI {s.get('emi_W_finestra_uguale')} W = "
              f"{s.get('rapporto_cw_div_EMI_finestra_uguale')} "
              f"(n {s.get('cw_n_campioni')} campioni buffer, dt "
              f"{s.get('cw_dt_mediano_s')} s) {s.get('cw_win_note') or ''}")
    cc_by_phase = {r["fase"]: r for r in cc.rows}

    load = stats.get("load") or {}
    base = [s for s in (stats.get("idle"), stats.get("idle2")) if s]
    p_base = statistics.mean([s["emi_W"] for s in base]) if base else None
    e_inc = (load["emi_J"] - p_base * load["emi_meter_s"]) if (load and p_base) else None

    lhm_base_vals = [s["lhm_mean_W"] for s in base if s.get("lhm_mean_W") is not None]
    lhm_base_w = statistics.mean(lhm_base_vals) if lhm_base_vals else None
    lhm_load_w = load.get("lhm_mean_W")
    lhm_inc_w = (None if lhm_base_w is None or lhm_load_w is None
                 else round(lhm_load_w - lhm_base_w, 2))
    # Versione "a finestra uguale" (fase): il buffer di produzione integrato e
    # il contatore EMI interpolato sulla STESSA finestra temporale della fase,
    # cosi' il numero NON dipende piu' dal punto in cui il tick capita (vedi
    # commento in phase_stats) e il confronto e' anche same-clock.
    cw_base_vals = [s["cw_W_finestra_uguale"] for s in base
                    if s.get("cw_W_finestra_uguale") is not None]
    cw_base_w = statistics.mean(cw_base_vals) if cw_base_vals else None
    cw_load_w = load.get("cw_W_finestra_uguale")
    cw_s_load = load.get("cw_s_fase")
    cw_inc_w = (None if cw_base_w is None or cw_load_w is None
                else round(cw_load_w - cw_base_w, 2))
    cw_inc_j = (None if cw_inc_w is None or not cw_s_load
                else round(cw_inc_w * cw_s_load, 1))
    ew_base_vals = [s["emi_W_finestra_uguale"] for s in base
                    if s.get("emi_W_finestra_uguale") is not None]
    ew_base_w = statistics.mean(ew_base_vals) if ew_base_vals else None
    ew_load_w = load.get("emi_W_finestra_uguale")
    emi_inc_j_win = (None if ew_base_w is None or ew_load_w is None or not cw_s_load
                     else round((ew_load_w - ew_base_w) * cw_s_load, 1))
    cc_base = [cc_by_phase[f]["cpu_power_W_fase"] for f in ("idle", "idle2")
               if f in cc_by_phase and cc_by_phase[f]["cpu_power_W_fase"] is not None]
    cc_load = (cc_by_phase.get("load") or {}).get("cpu_power_W_fase")
    dur_load = dict(FASI)["load"]

    hw_base_vals = [s["hw_mean_W"] for s in base if s.get("hw_mean_W") is not None]
    hw_base_w = statistics.mean(hw_base_vals) if hw_base_vals else None
    hw_load_w = load.get("hw_mean_W")
    hw_inc_w = (None if hw_base_w is None or hw_load_w is None
                else round(hw_load_w - hw_base_w, 2))

    summary = {
        "timestamp": ts,
        "wall_zero": wall_zero,
        "fasi": FASI,
        "fasi_durata_reale_s": {f: round(b - a, 3) for f, (a, b) in fase_win.items()},
        "tokens_load": tok,
        "per_fase": stats,
        "codecarbon_per_fase": cc.rows,
        "codecarbon_backend": cc.backend,
        "codecarbon_notes": cc.notes,
        "confronto": {
            "EMI_W_base": None if p_base is None else round(p_base, 2),
            "EMI_W_load": load.get("emi_W"),
            "EMI_incrementale_J": None if e_inc is None else round(e_inc, 1),
            "EMI_J_per_token": None if (e_inc is None or not tok) else round(e_inc / tok, 4),
            "LHM_W_base": None if lhm_base_w is None else round(lhm_base_w, 2),
            "LHM_W_load": lhm_load_w,
            "LHM_incrementale_W": lhm_inc_w,
            "LHM_incrementale_J": None if lhm_inc_w is None else round(lhm_inc_w * dur_load, 1),
            "LHM_finestra_uguale_W_base": None if cw_base_w is None else round(cw_base_w, 2),
            "LHM_finestra_uguale_W_load": cw_load_w,
            "LHM_finestra_uguale_incrementale_J": cw_inc_j,
            "EMI_finestra_uguale_W_base": None if ew_base_w is None else round(ew_base_w, 2),
            "EMI_finestra_uguale_W_load": ew_load_w,
            "EMI_finestra_uguale_incrementale_J": emi_inc_j_win,
            "rapporto_LHM_div_EMI_incrementale_finestra_uguale":
                (None if (cw_inc_j is None or not emi_inc_j_win)
                 else round(cw_inc_j / emi_inc_j_win, 4)),
            "J_per_token_LHM_finestra_uguale": (None if cw_inc_j is None or not tok
                                                else round(cw_inc_j / tok, 4)),
            "rapporto_LHM_div_EMI_J_per_token_finestra_uguale":
                (None if (cw_inc_j is None or not tok or not e_inc)
                 else round((cw_inc_j / tok) / (e_inc / tok), 4)),
            "CodeCarbon_W_base": None if not cc_base else round(statistics.mean(cc_base), 2),
            "CodeCarbon_W_load": cc_load,
            "CodeCarbon_incrementale_W": None if (cc_load is None or not cc_base)
                                         else round(cc_load - statistics.mean(cc_base), 2),
            "HWiNFO_W_base": None if hw_base_w is None else round(hw_base_w, 2),
            "HWiNFO_W_load": hw_load_w,
            "HWiNFO_incrementale_W": hw_inc_w,
            "HWiNFO_incrementale_J": None if hw_inc_w is None else round(hw_inc_w * dur_load, 1),
            "J_per_token_LHM": None if (lhm_inc_w is None or not tok)
                               else round(lhm_inc_w * dur_load / tok, 4),
            "J_per_token_HWiNFO": None if (hw_inc_w is None or not tok)
                                  else round(hw_inc_w * dur_load / tok, 4),
            "offset_LHM_meno_EMI_W": None if (lhm_base_w is None or p_base is None)
                                        else round(lhm_base_w - p_base, 2),
            "offset_HWiNFO_meno_EMI_W": None if (hw_base_w is None or p_base is None)
                                         else round(hw_base_w - p_base, 2),
        },
        "confronto_note": (
            "EMI = contatore hardware cumulativo PKG, riferimento di scala; SRUM "
            "(secondo consumatore degli stessi contatori) lo replica a +/-4% su "
            "finestre identiche, quindi la decodifica ctypes e' corretta ma SRUM "
            "NON e' un arbitro indipendente. "
            "LHM = power-integration di produzione: dopo il guard su SensorType "
            "(energy_session.py _read_power_w_direct, 23/10) il match per nome non "
            "cade piu' sull'omonimo sensore Temperature (IntelCpu.cs:401) e "
            "l'offset LHM-EMI e' passato da +54,5 W a +0,22 W "
            "(lhm_readpath_probe_20261023_132621). "
            "CodeCarbon su questa macchina = modello cpu_load "
            "(80 W * (0.1 + 0.9*load^3)), NON una misura: termine di confronto "
            "metodologico, non arbitro. "
            "HWiNFO = package letto dalla Shared Memory (calibrato a caldo vs "
            "EMI), testimone NON passivo perche' il suo polling e' carico CPU. "
            "*_finestra_uguale = LHM integrato con trapezio sul buffer del "
            "thread di produzione e EMI interpolato sull'asse mono dei tick, "
            "sulla STESSA finestra [inizio fase, fine fase]: il rapporto e' "
            "same-window e same-clock, e non dipende piu' dal punto in cui il "
            "tick 1 Hz capita (sul load il tick e' bloccato dalla richiesta "
            "Ollama). I J/token di LHM e HWiNFO senza suffisso usano invece "
            "(W_load - W_base) * durata_fase con i soli campioni istantanei: "
            "sono quelli metodologicamente piu' deboli e restano nel JSON solo "
            "come termine di confronto."),
        "pi_csv": out_pi.name,
        "hwinfo": ("shared-memory" if hw is not None else "ASSENTE"),
        "hwinfo_note": hw_note,
    }
    out_json = ROOT / "experiment_results" / f"four_way_{ts}.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[OK] {out_csv}\n[OK] {out_pi}\n[OK] {out_json}")


if __name__ == "__main__":
    main()
