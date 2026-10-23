#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""srum_lag_check.py — SRUM e' utilizzabile come canale di misura dal vivo?

Punto di partenza (dato, non ipotesi): il dump preso oggi alle 11:59:48 aveva
come timestamp PIU' RECENTE le 09:59:00 -> sembrava 2 ore indietro. Questo test
distingue le due spiegazioni: (a) archivio in lag, (b) `TimeStamp` esportata in
UTC. ESITO MISURATO (23/10, run con 3 min di carico): eta' 121,4 min se letta
locale contro **1,4 min se letta UTC**, offset macchina 2:00:00, e 4 bucket nuovi
(10:10..10:13) compaiono durante il carico -> **ipotesi (b): SRUM e' vivo a
granularita' ~1 minuto, ma le finestre vanno costruite in UTC**.

Cosa stampa: eta' dell'ultimo bucket sotto le due ipotesi, bucket nuovi fra i due
flush, delta delle somme di sistema e dell'AppId di ollama.

Uso: shell elevata.  python srum_lag_check.py [minuti_di_carico]
"""
from __future__ import annotations

import datetime
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from srum import flush, grand_total, load as srum_load  # noqa: E402

TAG = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = ROOT / "experiment_results"


def newest(rows, ts_of):
    t = [ts_of(r) for r in rows if ts_of(r)]
    return max(t) if t else None


def main() -> int:
    load_min = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    p0 = flush(OUT / f"srum_dump_{TAG}_lag0.csv")
    if p0 is None:
        print("[ERRORE] flush fallito (servie amministrazione?)")
        return 2
    d0 = srum_load(p0)
    n = newest(d0.rows, d0._ts)
    now = datetime.datetime.now()
    print(f"flush #1 alle {now:%H:%M:%S} -> bucket piu' recente: {n}")
    if n is None:
        print("[ERRORE] nessun timestamp parsato")
        return 3
    print(f"ETA' DEL DATO PIU' RECENTE = {(now - n).total_seconds()/60:.1f} minuti")
    per0 = d0.sum_since(None)
    t0 = grand_total(per0)

    if load_min > 0:
        print(f"--- carico {load_min:.0f} min di inferenza Ollama ---")
        from four_way_test import ollama_generate, open_emi
        h = open_emi()
        pj0, pt0 = __import__("four_way_test").emi_pkg(h)
        t_end = datetime.datetime.now() + datetime.timedelta(minutes=load_min)
        tok = 0
        n_ok = 0
        while datetime.datetime.now() < t_end:
            try:
                tok += ollama_generate()
                n_ok += 1
            except Exception as exc:
                print(f"[WARN] ollama: {exc}")
                break
        pj1, pt1 = __import__("four_way_test").emi_pkg(h)
        dt = (pt1 - pt0) * 1e-7
        dj = (pj1 - pj0) * __import__("four_way_test").PWH_TO_J
        print(f"generate ok: {n_ok}, token: {tok};  EMI pkg delta = {dj:.1f} J in "
              f"{dt:.1f} s = {dj/dt:.2f} W" if dt > 0 else "EMI: finestra nulla")

    print("attesa 30 s prima del secondo flush...")
    import time
    time.sleep(30)
    p1 = flush(OUT / f"srum_dump_{TAG}_lag1.csv")
    d1 = srum_load(p1)
    n1 = newest(d1.rows, d1._ts)
    now1 = datetime.datetime.now()
    print(f"flush #2 alle {now1:%H:%M:%S} -> bucket piu' recente: {n1} "
          f"(eta' {(now1 - n1).total_seconds()/60:.1f} min)" if n1 else "nessun bucket")

    per1_all = d1.sum_since(None)
    t1 = grand_total(per1_all)
    print("\ndelta fra i due flush (stessa somma su tutto il file):")
    for k in t1:
        print(f"  {k:24s} raw_delta={t1[k] - t0[k]:>16.1f}")
    per1 = d1.sum_since(n)
    oll = {k: v for k, v in per1.items() if "ollama" in k.lower()}
    print(f"  app ollama nei nuovi bucket: {len(oll)} -> "
          f"cpu={sum(v.get('CPUEnergyConsumption', 0.0) for v in oll.values()):.1f}")
    nuovi_ts = sorted({d1._ts(r) for r in d1.rows if d1._ts(r) and d1._ts(r) > n})
    print(f"  nuovi bucket: {[str(x) for x in nuovi_ts]}")
    if n1:
        off = datetime.datetime.now(datetime.timezone.utc).astimezone().utcoffset()
        eta_loc = (now1 - n1).total_seconds() / 60
        eta_utc = (now1 - n1 - off).total_seconds() / 60
        print(f"\nIPOTESI FUSO: eta'{eta_loc:.1f} min se TimeStamp e' LOCALE, "
              f"{eta_utc:.1f} min se e' UTC (offset {off}).")
        print("VERDETTO:", "SRUM VIVO a granularita' ~1 min e TimeStamp IN UTC"
              if nuovi_ts and eta_utc < 5 else
              ("nuovi bucket presenti ma eta' UTC > 5 min: lag reale da studiare"
               if nuovi_ts else
               "SRUM NON USABILE DAL VIVO: nessun bucket nuovo nella finestra"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
