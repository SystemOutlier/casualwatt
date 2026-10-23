"""Risoluzione temporale effettiva del contatore EMI (domanda posta da ricerca_metodo.DOCX:
campionamento a 50 ms e finestra di prefill separata).

Dai dati che gia' abbiamo: la trace LHM+EMI a ~0,25 s. Se il contatore PKG non cambia
fra campioni consecutivi, allora 50 ms di sampling non aggiunge informazione: il limite
non e' del thread, e' del registro.
"""
import csv
import math
import statistics
from collections import Counter
from fractions import Fraction
from functools import reduce

F = "lhm_emi_trace_20261023_154628.csv"
PWH_TO_J = 3.6e-9

rows = list(csv.DictReader(open(F, encoding="utf-8-sig"), delimiter=";"))
rows = [r for r in rows if r["emi_v0"] not in ("", None)]
n = len(rows)

t = [float(r["t_mono_s"]) for r in rows]
pkg = [int(r["emi_v0"]) for r in rows]
pp0 = [int(r["emi_v32"]) for r in rows]

dt = [t[i + 1] - t[i] for i in range(n - 1)]
print(f"campioni: {n}   durata: {t[-1]-t[0]:.2f} s")
print(f"intervallo di sampling: mediana {statistics.median(dt)*1000:.1f} ms, "
      f"min {min(dt)*1000:.1f}, max {max(dt)*1000:.1f}")

for nome, serie in (("PKG (offset 0)", pkg), ("PP0 (offset 32)", pp0)):
    d = [serie[i + 1] - serie[i] for i in range(n - 1)]
    zero = sum(1 for x in d if x == 0)
    nz = [x for x in d if x > 0]
    print(f"\n--- {nome} ---")
    print(f"  delta fra campioni consecutivi = 0 : {zero}/{len(d)} ({100*zero/len(d):.1f}%)")
    if nz:
        print(f"  delta non nulli: {len(nz)}, minimo {min(nz):,} pWh = {min(nz)*PWH_TO_J*1000:.3f} mJ")
        print(f"  mediana {statistics.median(nz):,.0f} pWh, massimo {max(nz):,} pWh")
        # quantizzazione: il MCD dei delta non nulli (approssimato sui primi 200)
        vals = [int(v) for v in nz[:200]]
        g = reduce(math.gcd, vals)
        print(f"  MCD dei primi {len(vals)} delta non nulli: {g} pWh "
              f"= {g*PWH_TO_J*1000:.4f} mJ (quantum minimo del contatore)")
    # risoluzione effettiva: quantizzazione in funzione del dt reale del campione
    if nz:
        rate = [(serie[i + 1] - serie[i]) * PWH_TO_J / dt[i] for i in range(n - 1) if dt[i] > 0]
        print(f"  potenza per campione: {100*sum(1 for r in rate if r == 0)/len(rate):.1f}% "
              f"a zero, mediana {statistics.median(rate):.2f} W, "
              f"min {min(rate):.2f} W, max {max(rate):.2f} W")

# La domanda vera: quale e' la piu' corta finestra su cui PKG da' un delta non nullo?
print("\n--- finestra minima osservabile (PKG) ---")
for k in (1, 2, 3, 4, 8):
    dd = [pkg[i + k] - pkg[i] for i in range(n - k)]
    zero = sum(1 for x in dd if x == 0)
    span = statistics.median(dt) * k
    print(f"  finestra {span*1000:5.0f} ms ({k} intervalli): delta nulli {zero}/{len(dd)} "
          f"({100*zero/len(dd):5.1f}%)")

# Energia media per fase, e confronto con la finestra di un prefill (~0,3 s)
print("\n--- scala: quanta energia c'e' in una finestra breve ---")
W_med = statistics.median([(pkg[i + 1] - pkg[i]) / (dt[i]) * PWH_TO_J for i in range(n - 1)
                          if dt[i] > 0])
print(f"  potenza istantanea mediana da EMI: {W_med:.2f} W")
for ms in (50, 100, 300, 1000):
    print(f"  energia attesa in {ms:4d} ms: {W_med*ms/1000*1000:7.2f} mJ")

# =============================================================================
# Sezione 2 — geometria reale dei nostri protocolli (prefill risolvibile?)
# Domanda posta dal DOCX: separare prefill (TTFT) e decode, e fare uno sweep
# di N_in (64/512/2048). Per rispondere servono i numeri dei nostri run.
# =============================================================================
import pathlib

CSV = pathlib.Path("lhm_validation_v3_20261023_160430.csv")
print("\n--- geometria reale del protocollo v3 (post-fix) ---")
r3 = list(csv.DictReader(open(CSV, encoding="utf-8-sig"), delimiter=";"))
load = [r for r in r3 if r["phase"] == "load" and int(r["tokens_out"] or 0) > 0]
if load:
    tin = sum(int(r["tokens_in"]) for r in load)
    tout = sum(int(r["tokens_out"]) for r in load)
    dtot = sum(float(r["dt_s"]) for r in load)
    ninf = 15 * len(load)
    print(f"  run con fase load: {len(load)}")
    print(f"  token in totale {tin}, out {tout}  ->  "
          f"per richiesta: N_in {tin/ninf:.1f}, N_out {tout/ninf:.1f}")
    print(f"  durata load {dtot:.1f} s su {ninf} richieste -> "
          f"{dtot/ninf:.2f} s a richiesta")
    # se il prefill di ~12 token vale una frazione minima della richiesta,
    # il rapporto decode/prefill per token non e' misurabile con questa geometria
    print(f"  rapporto N_in/N_out = {tin/max(tout,1):.3f}  "
          f"(una richiesta e' quasi solo decode)")
    print(f"  intervallo PI misurato in fase load: "
          f"{sorted({r['pi_measured_interval_s'] for r in load})}")
    print(f"  j_per_token per run: {[r['j_per_token'] for r in load]}")

