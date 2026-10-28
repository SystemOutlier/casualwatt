#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lhm_sensor_dump.py — chi e' DAVVERO il sensore "CPU Package" che leggiamo?

Perche' esiste (23/10/2026). Il sorgente LibreHardwareMonitor 0.9.6 che l'utente
ha messo in `..\\LHM\\LibreHardwareMonitor-0.9.6` dice, file:riga:

  IntelCpu.cs:28   _energyStatusMsrs = { MSR_PKG_ENERGY_STATUS(0x611), PP0, PP1,
                   DRAM, PLATFORM }                                    (0x611 a riga 762)
  IntelCpu.cs:469  ReadMsr(MSR_RAPL_POWER_UNIT=0x606) ->
                   EnergyUnitsMultiplier = 1f / (1 << ((eax >> 8) & 0x1F))
  IntelCpu.cs:480  labels = ["CPU Package","CPU Cores","CPU Graphics","CPU Memory",
                   "CPU Platform"], tutti SensorType.Power
  IntelCpu.cs:696  sensor.Value = EnergyUnitsMultiplier
                   * unchecked(energyConsumed - _lastEnergyConsumed[index]) / deltaTime

Quindi il "CPU Package" di LHM (0.9.6) NON e' un modello ne' un altro dominio: e'
delta(MSR 0x611) al secondo, lo STESSO contatore RAPL di package che il nostro EMI
nativo espone come record PKG. Se la DLL che usiamo in produzione facesse altrettanto,
LHM ed EMI devraient darmi lo STESSO wattaggio; invece misuriamo offset +55 W e
pendenza ~0,5 sull'inferenza (four_way run 1 e 2, 23/10). La divergenza deve quindi
venire da una di queste tre cose, e questo script le distingue con evidenza:

  (a) QUALE sensore seleziona davvero `energy_session._select_power_sensor()`
      (cerca SensorType==Power con nome esattamente "cpu package" su qualunque
      hardware di tipo CPU, inclusa la SubHardware): su questa macchina esistono
      altri sensori Power con lo stesso nome o nome simile?
  (b) la DLL di produzione e' 0.9.4+b807743 (verificato 23/10), due versioni SOTTO
      il sorgente che leggiamo: il percorso 0x611 puo' essere diverso;
  (c) il `deltaTime` e il ritmo di aggiornamento del sensore (0,32 s misurato).

Cosa fa:
  * apre il Computer() con la STESSA recipe di produzione (energy_session.py:443-466),
    senza modificare quel file;
  * ELLENA tutti gli hardware e tutti i sensori Power/Energy che la libreria espone,
    con hardware di provenienza (CPU, motherboard, controller...);
  * campiona a ~1 Hz una scalinata idle -> burn2 -> burn8 -> cool leggendo INSIEME
    ogni sensore e i 4 domini EMI (PKG/DRAM/PP0/PP1, trasporto riusato da
    four_way_test.py);
  * riporta per ogni sensore: offset a idle rispetto a EMI PKG, delta per fase di
    burn, e il RAPPORTO delta_EMI/delta_sensore.

Lettura: rapporto ~1 e offset ~0 => stesso contatore di EMI (la divergenza e' solo
di selezione o di integrazione). Rapporto lontano da 1 => il sensore NON e' 0x611.

Serve AMMINISTRATORE (LHM popola i sensori Power/Energy solo elevato).
Output: experiment_results/lhm_sensor_dump_<ts>.{csv,json}
Uso: python lhm_sensor_dump.py     (da shell elevata)
"""
from __future__ import annotations

import ctypes
import datetime
import json
import multiprocessing as mp
import statistics
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

# riusa il trasporto EMI del four-way (device path e IOCTL gia' validati eseguendo)
from four_way_test import open_emi  # noqa: E402

IOCTL_GET_MEASUREMENT = 0x0022400C


def emi_all(h) -> dict:
    """I 4 record EMI da 16 B: PKG@0, DRAM@16, PP0@32, PP1@48 [energia pWh, tempo 100 ns]."""
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not ctypes.windll.kernel32.DeviceIoControl(h, IOCTL_GET_MEASUREMENT, None, 0,
                                                  out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return {"package": (v[0], v[1]), "dram": (v[2], v[3]),
            "pp0": (v[4], v[5]), "pp1": (v[6], v[7])}

OUT_DIR = ROOT / "experiment_results"
FASI = [("idle", 30.0), ("burn2", 30.0), ("burn8", 30.0), ("cool", 25.0)]
BURN_N = {"idle": 0, "burn2": 2, "burn8": 8, "cool": 0}


def burn(stop_at: float) -> None:
    x = 0.0
    while time.monotonic() < stop_at:
        for _ in range(200_000):
            x += 1.0


def load_lhm():
    """Recipe di produzione (energy_session.py:443-466), qui senza toccare il file."""
    import clr  # noqa: F401  (pythonnet)
    import os
    from config import LHM_DLL_PATH
    if not LHM_DLL_PATH.exists():
        raise FileNotFoundError(f"DLL LHM non trovata: {LHM_DLL_PATH}")
    os.add_dll_directory(str(LHM_DLL_PATH.parent))
    try:
        from System.Reflection import Assembly
        with open(LHM_DLL_PATH, "rb") as fh:
            Assembly.Load(fh.read())
    except Exception:
        clr.AddReference(str(LHM_DLL_PATH))
    from LibreHardwareMonitor.Hardware import Computer
    comp = Computer()
    comp.IsCpuEnabled = True
    comp.IsGpuEnabled = True
    # NOTA (imparato eseguendo, 23/10): con IsControllerEnabled/IsMotherboardEnabled
    # = True `comp.Open()` solleva FileNotFoundException su "HidSharp,
    # Version=2.1.0.0" (gruppo AquaComputer) perche' l'assembly di dipendenza NON
    # e' risolto: `os.add_dll_directory()` serve ai DLL NATIVI, non al resolver del
    # CLR per gli assembly managed. La produzione (energy_session.py:464-466)
    # accende solo CPU e GPU, e `_select_power_sensor()` filtra per hardware di
    # tipo CPU (`_lhm_is_cpu_hw`): quindi enumerare la motherboard sarebbe
    # comunque fuori dal percorso reale. Restiamo SU_PATH con la produzione.
    comp.Open()
    return comp, str(LHM_DLL_PATH)


def dll_version(path: str) -> str:
    try:
        size = ctypes.windll.version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return "?"
        buf = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(path, 0, size, buf):
            return "?"
        val = ctypes.c_void_p()
        nlen = ctypes.c_uint()
        if (ctypes.windll.version.VerQueryValueW(buf, "\\", ctypes.byref(val),
                                                  ctypes.byref(nlen)) and nlen.value):
            ms = ctypes.c_uint32.from_address(val.value + 8).value
            ls = ctypes.c_uint32.from_address(val.value + 12).value
            return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
    except Exception as exc:
        return f"? ({type(exc).__name__})"
    return "?"


def collect_sensors(comp):
    """Aggiorna tutto l'albero e ritorna [(meta, oggetto_sensore)] per Power/Energy.

    Gli oggetti pythonnet restano validi fra un Update() e l'altro: li cachiamo
    cosi' il tick non deve rincorrere la scansione (che e' la parte lenta).
    """
    found = []
    for hw in comp.Hardware:
        try:
            hw.Update()
        except Exception as exc:
            print(f"[WARN] Update({hw.Name}) fallisce: {exc}")
            continue
        nodes = [(hw, str(hw.HardwareType), str(hw.Name))]
        try:
            for sub in (list(getattr(hw, "SubHardware", []) or [])):
                nodes.append((sub, str(sub.HardwareType) + "/sub", str(sub.Name)))
        except Exception:
            pass
        for node, htype, hname in nodes:
            try:
                sensors = list(node.Sensors)
            except Exception:
                continue
            for s in sensors:
                try:
                    stype = str(s.SensorType)
                except Exception:
                    continue
                if stype.strip().lower() in ("power", "energy"):
                    found.append(({"hw_type": htype, "hw_name": hname,
                                   "name": str(s.Name), "type": stype,
                                   "index": int(s.Index)}, s))
    return found


def main() -> int:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] serve Amministratore: LHM popola i sensori Power/Energy "
              "solo con processo elevato.")
        return 2

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    comp, dll_path = load_lhm()
    ver = dll_version(dll_path)
    print(f"[OK] LHM agganciata: {dll_path}")
    print(f"[OK] versione DLL rilevata: {ver}   (sorgente letto: 0.9.6 -> "
          "discordanza DA DICHIARARE nel referto)")

    pairs = collect_sensors(comp)
    print(f"\n=== sensori Power/Energy esposti: {len(pairs)} ===")
    for i, (m, _s) in enumerate(pairs):
        print(f"  [{i}] {m['type']:<6} '{m['name']}'  <{m['hw_type']} :: {m['hw_name']}> idx={m['index']}")

    h = open_emi()
    print("[OK] EMI attivo (contatore cumulativo, nessun privilegi).")

    rows = []
    t_prev = time.monotonic()
    e_prev = emi_all(h)
    for fase, dur in FASI:
        t0 = time.monotonic()
        procs = []
        for _ in range(BURN_N[fase]):
            p = mp.Process(target=burn, args=(t0 + dur,))
            p.start()
            procs.append(p)
        print(f"--- fase {fase} ({dur:.0f} s, {BURN_N[fase]} processi burn) ---")
        while time.monotonic() - t0 < dur:
            for hw in comp.Hardware:
                try:
                    hw.Update()
                except Exception:
                    pass
            vals = {}
            for i, (_m, s) in enumerate(pairs):
                try:
                    v = float(s.Value)
                    vals[i] = v if v == v else None
                except Exception:
                    vals[i] = None
            e = emi_all(h)
            now = time.monotonic()
            dt = now - t_prev
            w = {k: ((e[k][0] - e_prev[k][0]) * 3.6e-9 / dt) if dt > 1.0 else None
                 for k in e}
            t_prev, e_prev = now, e
            rows.append({"fase": fase, "t": round(now - t0, 2), "emi_W": w, "s": vals})
            time.sleep(1.0)
        for p in procs:
            p.join(timeout=5)
            if p.is_alive():
                p.terminate()

    def mean(fase, i):
        vs = [r["s"].get(i) for r in rows if r["fase"] == fase and r["s"].get(i) is not None]
        return round(statistics.mean(vs), 2) if vs else None

    def emi_mean(fase, dom="package"):
        vs = [r["emi_W"].get(dom) for r in rows if r["fase"] == fase
              and r["emi_W"].get(dom) is not None]
        # scarta il primo tick di ogni fase (delta gia' sporcato dal bordo fase)
        vs = vs[1:] if len(vs) > 2 else vs
        return round(statistics.mean(vs), 2) if vs else None

    idle_emi = emi_mean("idle") or 0.0
    summary = {
        "timestamp": ts,
        "dll_path": dll_path,
        "dll_version": ver,
        "sorgente_di_riferimento": "LibreHardwareMonitor 0.9.6, IntelCpu.cs:696 "
                                   "(sensor.Value = E_unit * delta(MSR 0x611) / dt)",
        "fasi": {f: d for f, d in FASI},
        "emi_W_per_fase": {dom: {f: emi_mean(f, dom) for f, _ in FASI}
                           for dom in ("package", "pp0", "pp1", "dram")},
        "sensori": [],
    }
    print(f"\n=== EMI [W] per fase ===")
    for dom in ("package", "pp0", "pp1"):
        print(f"  {dom:<8} " + "  ".join(f"{f}={emi_mean(f, dom)}" for f, _ in FASI))
    print("\n=== ogni sensore Power/Energy contro EMI PKG ===")
    for i, (m, _s) in enumerate(pairs):
        per_fase = {f: mean(f, i) for f, _ in FASI}
        line = {"i": i, "sensore": m["name"], "tipo": m["type"],
                "hardware": f"{m['hw_type']} :: {m['hw_name']}", "index": m["index"],
                "W_per_fase": per_fase,
                "offset_a_idle_vs_EMI_W": (round(per_fase["idle"] - idle_emi, 2)
                                           if per_fase.get("idle") is not None else None)}
        if per_fase.get("idle") is not None:
            for f in ("burn2", "burn8"):
                e, s = emi_mean(f), per_fase[f]
                if e is None or s is None:
                    continue
                d_s, d_e = s - per_fase["idle"], e - idle_emi
                line[f"delta_{f}"] = {"sensore_W": round(d_s, 2), "EMI_W": round(d_e, 2),
                                      "rapporto_EMI_div_sensore": (round(d_e / d_s, 3)
                                                                   if abs(d_s) > 0.5 else None)}
        summary["sensori"].append(line)
        print("  " + json.dumps(line, ensure_ascii=False))

    OUT_DIR.mkdir(exist_ok=True)
    oj = OUT_DIR / f"lhm_sensor_dump_{ts}.json"
    oj.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    oc = OUT_DIR / f"lhm_sensor_dump_{ts}.csv"
    with open(oc, "w", encoding="utf-8") as f:
        f.write("fase;t;emi_pkg_W;emi_pp0_W;emi_pp1_W;" +
                ";".join(f"[{i}]{m['type']}:{m['name']}" for i, (m, _s) in enumerate(pairs)) + "\n")
        for r in rows:
            g = lambda k: ("" if r["emi_W"].get(k) is None else round(r["emi_W"][k], 2))
            f.write(f"{r['fase']};{r['t']};{g('package')};{g('pp0')};{g('pp1')};" +
                    ";".join("" if r["s"].get(i) is None else str(r["s"][i])
                             for i in range(len(pairs))) + "\n")
    print(f"\n[OK] {oj}\n[OK] {oc}")
    try:
        comp.Close()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
