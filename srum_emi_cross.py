#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srum_emi_cross.py — la quarta sorgente NATIVA che non conoscevo: SRUM.

Scoperta (23/10/2026, probe in experiment_results/alternative_sources_probe_*.txt):
`powercfg /srumutil` da amministratore esporta il database SRUM di Windows con
colonne per-processo `CPUEnergyConsumption`, `EmiEnergyConsumption`,
`TotalEnergyConsumption`, popolate anche su un mini-PC senza batteria. E' una
ripartizione dell'energia per processo fatta da Windows, quindi UN TERMINE DI
CONFRONTO INDIPENDENTE per il capitolo "perche' l'attribuzione per-processo non
funziona" (e per CPU_TIME_SHARE di cpuepower2) — non un arbitro: la granularita'
e' a bucket e il split e' un modello.

Due fatti MISURATI che hanno cambiato questa v2 (run v1 20261023_121718):
* i campi non sono popolati come claimed dalla doc: su 34156 righe CPU 33346,
  Total 34040, **EmiEnergyConsumption solo 596** -> la riga EMI esiste per pochi
  AppId, e sono proprio i pseudo-AppId `EMI_RAPL_Package0_PKG/PP0/PP1`;
* SRUM fonde i bucket da minuto in un record ORARIO a ogni boundary di epoch
  (misurato: 08:32, 09:32, 10:32 UTC): un solo dump finale preso dopo il boundary
  si ritrova la fase gia' compattata e la finestra vuota.

Cosa misura qui, sulla stessa scalinata A-B-A:
  1. SCALA: rapporto SRUM / delta EMI per fase, per i tre domini EMI (PKG, PP0,
     PP1) che Windows espone come pseudo-AppId. Con il campo in millijoule
     (ipoTESI GIà CONFERMATA il 23/10 da srum_emi_scale.py: rapporto 0,9985 su
     bucket da 60 s) il rapporto in W deve venire ~1; se viene ~1000 o ~3600
     l'unita' e' sbagliata. E' il test, non un'assunzione.
  2. ATTRIBUZIONE: quota di `CPUEnergyConsumption` dell'AppId di ollama.exe (o
     llama-server) secondo SRUM vs la frazione di CPU-time del processo misurata
     con psutil nella stessa fase. Due attribuzioni, NON una validazione.
  3. PENDENZA: EMI e SRUM guardano la stessa finestra nello stesso run.

Fasi: warm-up (fuori misura) -> idle 120 s -> load 600 s (richette Ollama
identiche a four_way_test.py: num_predict 32, temperature 0) -> idle2 120 s.
Dopo OGNI fase: settle di 75 s (per far chiudere e scrivere l'ultimo minuto) e
dump SRUM dedicato.

OROLOGI: la colonna `TimeStamp` del dump SRUM e' UTC naive (misurato: eta' 1,4
min interpretandola UTC contro 121 min interpretandola locale). Le finestre di
fase sono quindi registrate in UTC; il suffisso dei campi e' `utc_*`.

Output:
  experiment_results/srum_emi_cross_<ts>.json  riepilogo e rapporti
  experiment_results/srum_emi_cross_<ts>.csv   righe EMI per fase
  experiment_results/srum_emi_cross_<ts>_buckets.csv  i bucket SRUM aggregati
  experiment_results/srum_dump_<ts>_<fase>.csv i dump per confine (NON committati: ~8 MB l'uno,
                                               eliminati dopo il parsing)

Uso: da shell ELEVATA (`powercfg /srumutil` senza admin risponde 0x1f / status 5).
"""
from __future__ import annotations

import ctypes
import datetime
import json
import statistics
import struct
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# riusa il trasporto EMI e il carico del four-way, senza duplicarli
from four_way_test import (  # noqa: E402
    MODEL, NUM_PREDICT, PROMPT, PWH_TO_J, emi_pkg, ollama_generate, open_emi,
)
from srum import flush, load as srum_load, utc_now_naive  # noqa: E402

# finestre lunghe per proposito: i bucket SRUM sono da ~1 min e il bucket di
# confine mescola idle+load, quindi serve >= 5 bucket per fase per non essere
# dominati dall'errore di bordo (misurato in srum_lag_check: eta' 1,4 min).
FASI = [("idle", 120.0), ("load", 600.0), ("idle2", 120.0)]
SETTLE_S = 75.0        # per far chiudere E scrivere l'ultimo minuto prima del dump
EMI_STEP_S = 5.0       #_tick_ di tracciamento EMI dentro la fase
OUT_DIR = ROOT / "experiment_results"

#: pseudo-AppId che SRUM usa per esporre i domini RAPL letti da Windows stessi
#: (misurato nel dump 20261023_120955: CPUEnergyConsumption = 0, Emi == Total).
SRUM_EMI_DOMAINS = {
    "EMI_RAPL_Package0_PKG": "package",
    "EMI_RAPL_Package0_PP0": "pp0",
    "EMI_RAPL_Package0_PP1": "pp1",
}

#: soglia superiore per una riga "da minuto". MISURATO sul dump
#: 20261023_120955: i roll-up orari partono da ~1e6 ms (una riga da 7,2e7 ms =
#: 20 h), quindi 70 s separa nettamente i due regimi. NON esiste una soglia
#: inferiore: lo stesso minuto puo' essere scritto come 2 righe complementari
#: (misurato 10:02 -> 26593 + 33399 = 59992 ms); scartare la corta perderebbe
#: energia. Per questo la copertura si valuta MINUTO PER MINUTO (vedi
#: `qualita_bucket_minuto` in aggregate_phase_rows), non filtrando le righe.
MAX_BUCKET_MS = 70_000
#: processi che "sono" Ollama: il worker llama-server.exe NON contiene "ollama"
#: nel nome (e' questo che ha dato la frazione 0,001 nel run v2).
NEEDLES = ("ollama", "llama-server")
#: un minuto si dice "completo" se la somma dei suoi TimeInMSec vale 60 +-3 s
FULL_MINUTE_MS = (57_000, 63_000)


def emi_all(h) -> dict:
    """Tutti e 4 i record EMI: PKG@0, DRAM@16, PP0@32, PP1@48 (energia pWh, tempo 100 ns)."""
    out = ctypes.create_string_buffer(64)
    got = ctypes.c_uint(0)
    if not ctypes.windll.kernel32.DeviceIoControl(h, 0x0022400C, None, 0,
                                                  out, 64, ctypes.byref(got), None):
        raise OSError(f"IOCTL EMI fallita (err={ctypes.GetLastError()})")
    v = struct.unpack("<8Q", out.raw[:64])
    return {"package": (v[0], v[1]), "dram": (v[2], v[3]),
            "pp0": (v[4], v[5]), "pp1": (v[6], v[7])}


def collect_minute_rows(snap, seen: set) -> list:
    """Righe-bucket da minuto MAI viste prima in un dump SRUM.

    Ritorna tuple `(AppId, TimeStamp_iso, ms, cpu_mJ, emi_mJ, tot_mJ)`.
    La deduplica per firma esatta e' corretta perche' il bucket di un minuto
    chiuso non viene piu' riscritto: un dump successivo lo ripesca identico e
    `seen` lo scarta. Cosi' il confine di compattazione oraria (:32) non puo'
    piu' cancellarci una fase intera come e' successo al run v1.
    """
    rows = []
    for r in snap.rows:
        ms = snap._f(r, "TimeInMSec")
        if not (0 < ms <= MAX_BUCKET_MS):
            continue
        ts = snap._ts(r)
        if ts is None:
            continue
        app = r.get("AppId", "?")
        cpu = snap._f(r, "CPUEnergyConsumption")
        emi = snap._f(r, "EmiEnergyConsumption")
        tot = snap._f(r, "TotalEnergyConsumption")
        sig = (app, ts.isoformat(), round(ms), round(cpu, 3), round(emi, 3), round(tot, 3))
        if sig in seen:
            continue
        seen.add(sig)
        rows.append((app, ts.isoformat(timespec="seconds"), ms, cpu, emi, tot))
    return rows


def aggregate_phase_rows(rows):
    """Aggrega le righe-bucket scoperte nel dump di fine fase.

    La potenza SRUM per dominio si calcola con il `TimeInMSec` del bucket
    stesso, NON con la durata della fase: cosi' un bucket di confine
    attribuito alla fase sbagliata sposta il numero di poco (e' una rata,
    non un totale), mentre la finestra temporale reale resta dichiarata
    in `bucket_da` / `bucket_a`.
    """
    if not rows:
        return None
    per_app = {}
    for (app, ts, ms, cpu, emi, tot) in rows:
        p = per_app.setdefault(app, {"cpu_mJ": 0.0, "emi_mJ": 0.0,
                                     "tot_mJ": 0.0, "ms": 0.0, "n": 0})
        p["cpu_mJ"] += cpu
        p["emi_mJ"] += emi
        p["tot_mJ"] += tot
        p["ms"] += ms
        p["n"] += 1
    J, W, cov, minuti = {}, {}, {}, {}
    # copertura reale per minuto: uno stesso minuto puo' essere scritto come
    # righe complementari (misurato 10:02 -> 26593 + 33399 = 59992 ms). Un
    # dominio "copre" il minuto se la somma dei suoi TimeInMSec vale 60 +-3 s.
    bymin = {dom: {} for dom in SRUM_EMI_DOMAINS}
    for (app, ts, ms, cpu, emi, tot) in rows:
        if app in bymin:
            d = bymin[app].setdefault(ts[:16], [0.0, 0.0])
            d[0] += ms
            d[1] += (emi or tot)     # nei pseudo-AppId EMI i due campi coincidono
    for dom, mappe in bymin.items():
        if not mappe:
            continue
        full = {k: v for k, v in mappe.items()
                if FULL_MINUTE_MS[0] <= v[0] <= FULL_MINUTE_MS[1]}
        use = full or mappe          # fallback dichiarato se nessun minuto e' completo
        ms_sum = sum(v[0] for v in use.values())
        e_j = sum(v[1] for v in use.values()) / 1000.0
        # mJ (ipoTESI CONFERMATA il 23/10 da srum_emi_scale.py: rapporto
        # SRUM/EMI = 0,9985 su bucket da 60 s) / 1000 = J; / (ms/1000) = W
        J[dom] = round(e_j, 2)
        W[dom] = round(e_j / (ms_sum / 1000.0), 3) if ms_sum else None
        cov[dom] = round(ms_sum / 1000.0, 1)
        minuti[dom] = {"minuti_totali": len(mappe), "minuti_completi": len(full)}
    tot_cpu = sum(v["cpu_mJ"] for v in per_app.values())
    oll = {k: v for k, v in per_app.items() if "ollama" in k.lower()
           or "llama-server" in k.lower()}
    ts_all = sorted(r[1] for r in rows)
    top = sorted(per_app.items(), key=lambda kv: -kv[1]["cpu_mJ"])[:8]
    return {
        "bucket_nuovi": len(rows),
        "minuti_distinti": len({r[1] for r in rows}),
        "bucket_da": ts_all[0], "bucket_a": ts_all[-1],
        "SRUM_E_J_per_dominio": J,
        "SRUM_W_per_dominio_EMI": W,
        "copertura_bucket_s": cov,
        "qualita_bucket_minuto": minuti,
        "SRUM_cpu_totale_J": round(tot_cpu / 1000.0, 2),
        "SRUM_ollama_cpu_J": round(sum(v["cpu_mJ"] for v in oll.values()) / 1000.0, 2),
        "SRUM_ollama_share_of_cpu": (round(sum(v["cpu_mJ"] for v in oll.values()) / tot_cpu, 4)
                                     if tot_cpu > 0 else None),
        "ollama_appId": sorted(oll),
        "appId_conrighe": len(per_app),
        "top_cpu_mJ": [(k, round(v["cpu_mJ"] / 1000.0, 2)) for k, v in top],
    }

def cpu_seconds_of(needles) -> tuple:
    """(secondi CPU dei processi che matchano UNO dei needles, secondi di TUTTO).

    Due bug trovati ESEGUENDO i run, entrambi documentati per non ripeterli:
    * run v1 (20261023_121718): `cpu_times()` di psutil e' un `pcputimes`
      (namedtuple), NON una dict -> `t.get("user")` solleva AttributeError e il
      `try/except: continue` scartava ogni processo in silenzio => frazione 0,0.
      Usa `getattr`.
    * run v2 (20261023_130553): il needle "ollama" da SOLO matching 12,05 s su
      11794,27 s di sistema (frazione 0,001), perche' il processo che fa il
      lavoro e' `llama-server.exe` e NON contiene "ollama" nel nome. Da qui
      l'argomento `needles`: passare sia "ollama" sia "llama-server".
    """
    import psutil
    if isinstance(needles, str):
        needles = [needles]
    needles = [n.lower() for n in needles]
    mine = 0.0
    total = 0.0
    for p in psutil.process_iter(["name", "cpu_times"]):
        try:
            t = p.info["cpu_times"]
            if t is None:
                continue
            s = float(getattr(t, "user", 0.0) + getattr(t, "system", 0.0))
        except Exception:
            continue
        total += s
        nm = (p.info["name"] or "").lower()
        if any(n in nm for n in needles):
            mine += s
    return mine, total


def main() -> int:
    if not ctypes.windll.shell32.IsUserAnAdmin():
        print("[ERRORE] serve Amministratore: powercfg /srumutil risponde "
              "0x1f + 'SruUpdateStats failed, status 5' senza elevazione.")
        return 2

    print("Warm-up del modello (fuori misura)...")
    ollama_generate()

    h = open_emi()
    print("[OK] EMI attivo.")

    ts_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    d0 = flush(OUT_DIR / f"srum_dump_{ts_tag}_start.csv")
    if d0 is None:
        print("[ERRORE] flush SRUM fallito: niente esperimento.")
        return 3
    snap0 = srum_load(d0)
    print(f"[OK] SRUM dump iniziale: {len(snap0.rows)} righe, "
          f"watermark {snap0.max_ts()}")
    seen: set = set()
    # il baseline RIEMPIE `seen` senza essere contado: le sue righe-bucket sono
    # precedenti alla fase idle e non devono finire nel primo bucket "nuovo"
    baseline_rows = collect_minute_rows(snap0, seen)
    print(f"[OK] righe-bucket gia' presenti nel baseline: {len(baseline_rows)}")
    d0.unlink()

    # CORREZIONE v2 (run 20261023_121718 fallito per questo): SRUM compatta i
    # bucket da minuto in un record ORARIO a ogni boundary di epoch (misurato:
    # 08:32, 09:32, 10:32 UTC). Il dump finale e' stato preso DOPO il boundary
    # delle 10:32 e aveva gia' fuso l'intera fase di load in UN record orario ->
    # finestra vuota, `bucket_nella_finestra = 0`. Qui si dumpa AD OGNI confine
    # di fase e si sommano solo le righe-bucket MAI viste prima (dedup per
    # firma esatta): i bucket chiusi non cambiano, quindi la deduplica e'
    # corretta e il boundary di compattazione non puo' piu' cancellarci la fase.
    marks = {}
    ticks = []
    tokens = 0
    srum_per_fase = {}
    for fase, dur in FASI:
        t0 = time.monotonic()
        w0 = utc_now_naive()          # UTC: stessa base della TimeStamp SRUM
        e0 = emi_all(h)
        c0 = cpu_seconds_of(NEEDLES)
        print(f"--- fase {fase} ({dur:.0f} s) ---")
        last = t0
        while True:
            t = time.monotonic() - t0
            if t >= dur:
                break
            if fase == "load":
                try:
                    tokens += ollama_generate()
                except Exception as exc:
                    print(f"[WARN] ollama: {exc}")
                if time.monotonic() - t0 >= dur:
                    break
            if time.monotonic() - last >= EMI_STEP_S:
                last = time.monotonic()
                pj, pt = emi_pkg(h)
                ticks.append({"fase": fase, "t_s": round(time.monotonic() - t0, 1),
                              "emi_pkg_pwh": pj, "emi_pkg_ts100ns": pt})
        e1 = emi_all(h)
        c1 = cpu_seconds_of(NEEDLES)
        marks[fase] = {
            "utc_start": w0.isoformat(timespec="seconds"),
            "utc_end": utc_now_naive().isoformat(timespec="seconds"),
            "emi_start": e0, "emi_end": e1,
            "cpu_start": c0, "cpu_end": c1,
        }
        # dump di fine fase, dopo che l'ultimo minuto e' stato chiuso e scritto
        target = t0 + dur + SETTLE_S
        while time.monotonic() < target:
            time.sleep(1.0)
        dd = flush(OUT_DIR / f"srum_dump_{ts_tag}_{fase}.csv")
        if dd is None:
            print(f"[WARN] dump di fine fase {fase} fallito: fase SRUM-scoperta.")
            srum_per_fase[fase] = None
            continue
        snapN = srum_load(dd)
        srum_per_fase[fase] = collect_minute_rows(snapN, seen)
        print(f"[OK] {fase}: righe-bucket nuove = "
              f"{len(srum_per_fase[fase])}, watermark {snapN.max_ts()}")
        # ~8 MB per dump, rigenerabili con powercfg /srumutil: tutto quel che
        # serve resta nel JSON, quindi si elimina per non ingolfare experiment_results
        dd.unlink()

    # ---- 1) delta EMI per fase e totale --------------------------------------
    def emi_delta(fase, dom):
        m = marks[fase]
        pj0, pt0 = m["emi_start"][dom]
        pj1, pt1 = m["emi_end"][dom]
        return (pj1 - pj0) * PWH_TO_J, (pt1 - pt0) * 1e-7

    per_phase = {}
    for fase, _ in FASI:
        d = {dom: emi_delta(fase, dom) for dom in ("package", "dram", "pp0", "pp1")}
        m = marks[fase]
        per_phase[fase] = {
            "emi_J": {k: round(v[0], 2) for k, v in d.items()},
            "emi_meter_s": {k: round(v[1], 2) for k, v in d.items()},
            "emi_W": {k: (round(v[0] / v[1], 2) if v[1] > 0 else None)
                      for k, v in d.items()},
            "cpu_ollama_s": round(m["cpu_end"][0] - m["cpu_start"][0], 2),
            "cpu_system_s": round(m["cpu_end"][1] - m["cpu_start"][1], 2),
            "utc_start": m["utc_start"], "utc_end": m["utc_end"],
        }

    srum_fasi = {f: aggregate_phase_rows(srum_per_fase.get(f)) for f, _ in FASI}

    # ---- 3) confronto per fase / dominio: SRUM (rate) vs EMI (delta) ----------
    def rapporto_fase(fase):
        s, e = srum_fasi.get(fase), per_phase[fase]
        if not s:
            return {"stato": "nessun bucket nuovo nel dump di fine fase"}
        out = {}
        for dom_srum, dom_emi in SRUM_EMI_DOMAINS.items():
            sw = s["SRUM_W_per_dominio_EMI"].get(dom_srum)
            ew = e["emi_W"].get(dom_emi)
            out[dom_srum] = {
                "SRUM_W": sw,
                "EMI_W": ew,
                # rapporto ~1 => i due campi sono nella STESSA unita' (mJ, gia'
                # confermato da srum_emi_scale.py); ~1000 => SRUM in uJ; ~1e-3 => J
                "rapporto_SRUM_div_EMI": (round(sw / ew, 4)
                                          if sw is not None and ew else None),
                "SRUM_J_da_bucket": s["SRUM_E_J_per_dominio"].get(dom_srum),
                "EMI_J_finestra": e["emi_J"].get(dom_emi),
                "copertura_s": s["copertura_bucket_s"].get(dom_srum),
            }
        return out

    rapporti = {f: rapporto_fase(f) for f, _ in FASI}

    emi_pkg_load_J, emi_pkg_load_s = emi_delta("load", "package")
    emi_pp0_load_J, _ = emi_delta("load", "pp0")
    base_idle_W = statistics.mean([per_phase[f]["emi_W"]["package"]
                                   for f in ("idle", "idle2")])
    e_inc_J = emi_pkg_load_J - base_idle_W * emi_pkg_load_s

    load_s = srum_fasi.get("load") or {}
    frac_ollama = (per_phase["load"]["cpu_ollama_s"] /
                   per_phase["load"]["cpu_system_s"]
                   if per_phase["load"]["cpu_system_s"] > 0 else None)

    summary = {
        "timestamp": ts_tag,
        "finestra": {"start": marks["idle"]["utc_start"], "end": marks["idle2"]["utc_end"],
                     "load": [marks["load"]["utc_start"], marks["load"]["utc_end"]]},
        "fasi": FASI,
        "settle_s": SETTLE_S,
        "tokens_load": tokens,
        "baseline_bucket_gia_visti": len(baseline_rows),
        "granularita": {f: {"bucket_nuovi": (srum_fasi.get(f) or {}).get("bucket_nuovi"),
                            "minuti_distinti": (srum_fasi.get(f) or {}).get("minuti_distinti"),
                            "bucket_da": (srum_fasi.get(f) or {}).get("bucket_da"),
                            "bucket_a": (srum_fasi.get(f) or {}).get("bucket_a")}
                        for f, _ in FASI},
        "emi_per_fase": per_phase,
        "srum_per_fase": srum_fasi,
        "rapporti_SRUM_vs_EMI": rapporti,
        "confronto": {
            "EMI_pkg_load_J": round(emi_pkg_load_J, 2),
            "EMI_pp0_load_J": round(emi_pp0_load_J, 2),
            "EMI_incrementale_J": round(e_inc_J, 2),
            "EMI_base_idle_W": round(base_idle_W, 2),
            "EMI_J_per_token": round(e_inc_J / tokens, 4) if tokens else None,
            "SRUM_pkg_load_W": (load_s.get("SRUM_W_per_dominio_EMI") or {}).get(
                "EMI_RAPL_Package0_PKG"),
            "rapporto_medio_pkg": [
                (rapporti[f].get("EMI_RAPL_Package0_PKG") or {}).get("rapporto_SRUM_div_EMI")
                for f, _ in FASI],
            "SRUM_ollama_cpu_J_load": load_s.get("SRUM_ollama_cpu_J"),
            "SRUM_cpu_totale_J_load": load_s.get("SRUM_cpu_totale_J"),
            "SRUM_ollama_share_of_cpu_load": load_s.get("SRUM_ollama_share_of_cpu"),
            "cpu_time_share_ollama_misurata": round(frac_ollama, 4) if frac_ollama else None,
            "EMI_pkg_x_cpu_share_J": (round(e_inc_J * frac_ollama, 2) if frac_ollama else None),
            "ipotesi_unita": ("mJ -> rapporto SRUM/EMI in W atteso ~1; J -> ~1e-3; "
                              "uJ -> ~1e6; il valore MISURATO decide, non la doc"),
        },
        "caveat": (
            "SRUM scrive a bucket da minuto e li compatta in record orari a ogni "
            "boundary di epoch (misurato :32): per questo si dumpa a ogni confine di "
            "fase e si contano solo le righe mai viste. La potenza SRUM e' calcolata "
            "sul TimeInMSec del bucket, NON sulla durata della fase, quindi il bucket "
            "di confine sposta la rata di poco ma la finestra reale e' dichiarata in "
            "`granularita`. Il campo per-processo e' prodotto dal modello EPI di "
            "Windows: questo esperimento confronta DUE attribuzioni (la sua e la "
            "nostra frazione di CPU-time), non ne valida una contro la verita' "
            "hardware. L'arbitro resta il delta EMI/PP0, cumulativo e senza modello."),
    }

    out_json = OUT_DIR / f"srum_emi_cross_{ts_tag}.json"
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = OUT_DIR / f"srum_emi_cross_{ts_tag}.csv"
    with open(out_csv, "w", encoding="utf-8") as f:
        f.write("fase;t_s;emi_pkg_pwh;emi_pkg_ts100ns\n")
        for r in ticks:
            f.write(f"{r['fase']};{r['t_s']};{r['emi_pkg_pwh']};{r['emi_pkg_ts100ns']}\n")

    # righe-bucket usate per l'aggregazione: prova verificabile senza riumenre 8 MB
    out_b = OUT_DIR / f"srum_emi_cross_{ts_tag}_buckets.csv"
    with open(out_b, "w", encoding="utf-8") as f:
        f.write("fase;appId;time_stamp_utc;time_in_msec;"
                "cpu_energy_raw;emi_energy_raw;total_energy_raw\n")
        for fase, _ in FASI:
            for (app, ts, ms, cpu, emi, tot) in (srum_per_fase.get(fase) or []):
                keep = (app in SRUM_EMI_DOMAINS or "ollama" in app.lower()
                        or "llama-server" in app.lower())
                if keep:
                    f.write(f"{fase};{app};{ts};{ms};{cpu};{emi};{tot}\n")

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[OK] {out_json}\n[OK] {out_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
