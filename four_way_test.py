#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
four_way_test.py — Triangolo (in realta' quadrato) di misura su Windows 11.

Stessa scalinata A-B-A del protocollo v2, con QUATTRO sorgenti attive insieme:

  1. EMI nativo (ctypes, IOCTL 0x22400C)  -> contatore cumulativo PKG [pWh]
     (riferimento di scala: confermato da HWiNFO + PL1/PL2 il 23/10;
      NON richiede amministratore)
  2. CasualWatt SESSION (LHM power-integration) -> W "package-equivalente-LHM"
     (richiede AMMINISTRATORE; e' il backend di produzione, NON modificato)
  3. CodeCarbon EmissionsTracker (3.2.9) -> il SUO valore, che su MINI_IT13
     E' UN MODELLO e non una misura (verificato 23/10: Intel Power Gadget non
     istanzia sul 13900HK e il modello CPU non e' nel dataset -> avviso
     "4 W per thread x 20 = 80 W", poi modalita' cpu_load:
     P = 80*(0.1 + 0.9*load^3); il backend realmente scelto viene stampato
     nel log e salvato nel JSON). NB: non legge gli MSR, quindi NON entra in
     conflitto con LHM (vincolo "un solo consumer MSR").
  4. HWiNFO: NON letto qui -- l'utente attiva File>Logging (1 s) PRIMA del
     run e lo ferma dopo; il CSV si allinea dopo per timestamp di wall-clock
     (colonna "Date"/"Time", sensore "Potenza totale CPU [W]", col. 221 del
     log idle del 23/10).

Vincolo di metodologia (misurato 23/10, non ipotesi): CodeCarbon 3.2.9 scrive
UNA riga cumulativa per coppia start()/stop() -- `api_call_interval` di default
vale 300 misure, quindi i campioni intermedi non arrivano su CSV. Per avere un
numero PER FASE si faziona start()/stop() ai confini di fase e si differenziano
i cumulati `duration` [s] e `cpu_energy` [kWh].

Fasi: warm-up (fuori misura) -> idle 45 s -> load 90 s (richette Ollama
sequenziali, num_predict 32, temperature 0, protocollo identico al ps1 v2)
-> idle2 45 s. Tick 1 Hz (LHM + EMI).

Output:
  experiment_results/four_way_<ts>.csv   riga per tick
  experiment_results/four_way_<ts>.json  riepilogo per fase + J/token EMI
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
    """Ritorna (AbsoluteEnergy_pWh, AbsoluteTime_100ns) del canale PKG (record 0)."""
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not kernel32.DeviceIoControl(h, IOCTL_GET_MEASUREMENT, None, 0,
                                    out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return v[0], v[1]


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
    wall_zero = None

    def tick(fase, t_rel):
        """Un campione LHM (buffer power-integration) + EMI (contatore)."""
        try:
            with src._pi_lock:
                buf = list(src._pi_samples)
            lhm_w = buf[-1][1] if buf else None
        except Exception:
            lhm_w = None
        pj, pt = emi_pkg(h)
        ticks.append({"fase": fase, "t_s": round(t_rel, 3),
                      "wall": datetime.now().isoformat(timespec="milliseconds"),
                      "lhm_w": None if lhm_w is None else round(lhm_w, 3),
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
        cc.end_phase(fase)

    tok = tokens.get("load", 0)
    SESSION.stop()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_csv = ROOT / "experiment_results" / f"four_way_{ts}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("t_s;wall;fase;lhm_w;emi_pkg_pwh;emi_pkg_ts100ns\n")
        for r in ticks:
            lw = "" if r["lhm_w"] is None else r["lhm_w"]
            f.write(f"{r['t_s']};{r['wall']};{r['fase']};{lw};"
                    f"{r['emi_pkg_pwh']};{r['emi_pkg_ts100ns']}\n")

    # ---- analisi per fase -------------------------------------------------
    def phase_stats(fase):
        fr = [r for r in ticks if r["fase"] == fase]
        if len(fr) < 2:
            return None
        dj = (fr[-1]["emi_pkg_pwh"] - fr[0]["emi_pkg_pwh"]) * PWH_TO_J
        dt = (fr[-1]["emi_pkg_ts100ns"] - fr[0]["emi_pkg_ts100ns"]) * 1e-7
        lhms = [r["lhm_w"] for r in fr if r["lhm_w"] is not None]
        return {"n": len(fr),
                "emi_J": round(dj, 2),
                "emi_meter_s": round(dt, 2),
                "emi_W": round(dj / dt, 2) if dt > 0 else None,
                "lhm_mean_W": round(statistics.mean(lhms), 2) if lhms else None,
                "lhm_sd_W": round(statistics.stdev(lhms), 2) if len(lhms) > 1 else None}

    stats = {f: phase_stats(f) for f, _ in FASI}
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
    cc_base = [cc_by_phase[f]["cpu_power_W_fase"] for f in ("idle", "idle2")
               if f in cc_by_phase and cc_by_phase[f]["cpu_power_W_fase"] is not None]
    cc_load = (cc_by_phase.get("load") or {}).get("cpu_power_W_fase")
    dur_load = dict(FASI)["load"]

    summary = {
        "timestamp": ts,
        "wall_zero": wall_zero,
        "fasi": FASI,
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
            "CodeCarbon_W_base": None if not cc_base else round(statistics.mean(cc_base), 2),
            "CodeCarbon_W_load": cc_load,
            "CodeCarbon_incrementale_W": None if (cc_load is None or not cc_base)
                                         else round(cc_load - statistics.mean(cc_base), 2),
            "offset_LHM_meno_EMI_W": None if (lhm_base_w is None or p_base is None)
                                        else round(lhm_base_w - p_base, 2),
        },
        "confronto_note": (
            "EMI = contatore hardware cumulativo PKG (riferimento di scala). "
            "LHM = power-integration del package: gli ASSOLUTI sono invalidati "
            "(23/10: HWiNFO 15-19 W a idle + PL1 35 / PL2 55 W), i differenziali "
            "A-B-A restano validi perche' l'offset si cancella. "
            "CodeCarbon su questa macchina = modello cpu_load "
            "(80 W * (0.1 + 0.9*load^3)), NON una misura: termine di confronto "
            "metodologico, non arbitro. "
            "HWiNFO = CSV logging manuale dell'utente, da allineare per "
            "wall-clock a partire da wall_zero."),
        "hwinfo": "CSV logging manuale dell'utente; allineare per wall-clock",
    }
    out_json = ROOT / "experiment_results" / f"four_way_{ts}.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                        encoding="utf-8")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[OK] {out_csv}\n[OK] {out_json}")


if __name__ == "__main__":
    main()
