"""
Da dove va presa Py = P(Y = y) nel calcolo degli estremi di `cobound`.

La domanda non e' di gusto: nel codice Py e' l'unico termine che non viene dal
grafo. Questo script prova due cose distinte.

PARTE A - le due fonti non dicono la stessa cosa.
  Confronta la marginale del grafo con la frequenza in DATI.csv per ogni
  variabile presente in entrambi. Se le due distribuzioni coincidessero, la
  scelta sarebbe indifferente. E conta quante variabili di output delle query
  controfattuali mancano dal file: quelle non si possono calcolare affatto.

PARTE B - stimare Py su sei righe invece di leggerla dal giunto non e' una
  variante, e' un errore.
  Costruisce modelli causali artificiali con accoppiamento noto: due risposte
  Y(1) e Y(0) assegnate a caso su k blocchi di un'esogena uniforme. Per
  ognuno conosce la vera PNS = P(Y(1)=1, Y(0)=0), cioe' la quantita' che
  l'intervallo deve contenere. Poi calcola gli stessi estremi di cobound tre
  volte:
    - con Py esatta, marginale del giunto che produce anche p_xy: deve
      contenere sempre la PNS;
    - con Py stimata su 6 righe campionate dallo stesso modello, come fa
      DATI.csv: conta quante volte la PNS resta fuori. La Py non e' un
      parametro libero - e' la marginale del giunto che il codice gia'
      calcola - quindi la stima su 6 righe sostituisce un numero esatto con
      uno rumoroso;
    - con Py moltiplicata per 1.446, il rapporto fra la frequenza di
      Accident=Severe in DATI.csv (1/6) e la marginale del grafo (0.1153):
      l'errore che si commette davvero su CF2.
  Se con la Py esatta la PNS uscisse anche una sola volta, la formula degli
  estremi sarebbe sbagliata e lo script lo dichiara: in quel caso ci si ferma,
  perche' il problema non e' piu' da dove viene Py.

Uso: python verifica_py.py [--modelli 500] [--blocchi 40] [--seed 20261031]

Esce 0 se: (A) le fonti divergono e mancano colonne, (B) la PNS e' sempre
dentro con la Py della stessa popolazione e almeno una volta fuori con l'altra.
Esce 1 se una delle due attese non si verifica.
"""

import argparse
import csv
import random
import sys
from collections import Counter
from pathlib import Path

import pyagrum as gum

QUI = Path(__file__).resolve().parent
# nella cartella di lavoro le copie stanno in `consegna/`, nello zip scompattato
# sono accanto a questo script
CONSEGNA = QUI if (QUI / "insurance_grafo.bif").exists() else QUI / "consegna"
GRAFO = CONSEGNA / "insurance_grafo.bif"
DATI = CONSEGNA / "DATI.csv"


def marginali_grafo():
    """P(V = v) per ogni nodo del grafo, dall'inferenza esatta."""
    g = gum.loadBN(str(GRAFO))
    ie = gum.LazyPropagation(g)
    ie.makeInference()
    out = {}
    for i in g.nodes():
        v = g.variable(i)
        post = ie.posterior(v.name())
        out[v.name()] = {lab: float(post[k]) for k, lab in enumerate(v.labels())}
    return out


def frequenze_file():
    """Frequenza empirica di ogni valore in DATI.csv, e numero di righe."""
    with open(DATI, encoding="utf-8-sig", newline="") as f:
        righe = list(csv.DictReader(f))
    n = len(righe)
    freq = {}
    for col in righe[0]:
        c = Counter(r[col] for r in righe)
        freq[col] = {k: v / n for k, v in c.items()}
    return freq, n


def distanza_totale_variation(p, q):
    """0.5 * somma |p - q| sugli stati dell'unione. 0 = identiche, 1 = disgiunte."""
    stati = set(p) | set(q)
    return 0.5 * sum(abs(p.get(s, 0.0) - q.get(s, 0.0)) for s in stati)


def estremi(py_x, py_nox, py, q):
    """Gli stessi quattro termini di funtions_corretto.cobound:262 e :272.

    q = P(X = 1) nel modello; serve solo per il giunto osservazionale, che
    nella rete binarizzata viene dall'inferenza. Qui lo si scrive in forma
    chiusa perche' nel modello artificiale e' esatto.
    """
    p_xy = q * py_x
    p_noxy = (1.0 - q) * (1.0 - py_nox)
    p_xny = q * (1.0 - py_x)
    p_nxy = (1.0 - q) * py_nox
    low = max(0.0, py_x - py_nox, py - py_nox, py_x - py)
    upper = min(py_x, 1.0 - py_nox, p_xy + p_noxy,
                py_x - py_nox + p_xny + p_nxy)
    return low, upper


def modello(rng, blocchi, prob=0.35):
    """Due risposte binarie sullo stesso esogeno: y1 = risposta a do(X=1)."""
    y1 = [rng.random() < prob for _ in range(blocchi)]
    y0 = [rng.random() < prob for _ in range(blocchi)]
    return y1, y0


def statistiche(y1, y0):
    k = len(y1)
    py_x = sum(y1) / k
    py_nox = sum(y0) / k
    pns = sum(1 for a, b in zip(y1, y0) if a and not b) / k
    return py_x, py_nox, pns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelli", type=int, default=500)
    ap.add_argument("--blocchi", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261031)
    args = ap.parse_args()

    esito = 0

    # ---------------- PARTE A ----------------
    print("=" * 72)
    print("PARTE A - il grafo e DATI.csv sono la stessa popolazione?")
    print("=" * 72)
    mg = marginali_grafo()
    mf, n_righe = frequenze_file()
    comuni = [v for v in mg if v in mf]
    assenti = [v for v in mg if v not in mf]
    print(f"nodi del grafo: {len(mg)}   colonne di DATI.csv: {len(mf)}   "
          f"righe: {n_righe}")
    print(f"variabili comuni: {len(comuni)}   assenti dal file: {len(assenti)}")
    print(f"assenti: {', '.join(assenti)}")
    print()

    righe = sorted(((distanza_totale_variation(mg[v], mf[v]), v) for v in comuni),
                   reverse=True)
    print("per ogni variabile: lo stato piu' probabile nel grafo, le due "
          "probabilita', la distanza fra le distribuzioni")
    print(f"{'variabile':<14}{'stato':<14}{'P(grafo)':>9}{'P(file)':>9}{'dist':>7}")
    for d, v in righe:
        stato = max(mg[v], key=mg[v].get)
        mark = " " if stato in mf[v] else "*"
        print(f"{v:<14}{stato:<14}{mg[v][stato]:>9.4f}"
              f"{mf[v].get(stato, 0.0):>9.4f}{d:>7.3f}{mark}")
    print("* = stato mai osservato nelle 6 righe")
    massimo = righe[0]
    print()
    print(f"distanza massima: {massimo[0]:.3f} su {massimo[1]}")

    # le tre variabili di output delle query controfattuali
    bersagli = ["DrivQuality", "Accident", "Theft"]
    print()
    for b in bersagli:
        if b in mf:
            print(f"  bersaglio {b:<12} presente nel file")
        else:
            print(f"  bersaglio {b:<12} ASSENTE dal file: la query non si calcola")

    a_ok = massimo[0] > 0.2 and len(assenti) > 0
    print()
    print(f"PARTE A: {'OK' if a_ok else 'INATTESO'} - "
          f"fonti {'divergenti' if massimo[0] > 0.2 else 'coincidenti'}, "
          f"bersagli assenti {sum(1 for b in bersagli if b not in mf)}/3")
    if not a_ok:
        esito = 1

    # ---------------- PARTE B ----------------
    print()
    print("=" * 72)
    print("PARTE B - la PNS cade dentro l'intervallo?")
    print("=" * 72)
    rng = random.Random(args.seed)
    giusti_fuori = 0
    giusti_rovesciati = 0
    sei_fuori = 0
    sei_rovesciati = 0
    fattore_fuori = 0
    fattore_rovesciati = 0
    errori_sei = []
    ampiezza = []
    for _ in range(args.modelli):
        y1, y0 = modello(rng, args.blocchi)
        py_x, py_nox, pns = statistiche(y1, y0)
        q = rng.uniform(0.05, 0.95)
        py_giusta = q * py_x + (1.0 - q) * py_nox

        low, upper = estremi(py_x, py_nox, py_giusta, q)
        if low > upper:
            giusti_rovesciati += 1
        if not (low - 1e-12 <= pns <= upper + 1e-12):
            giusti_fuori += 1
        if low <= upper:
            ampiezza.append(upper - low)

        # Py stimata su 6 righe dello stesso modello, come DATI.csv
        campione = [1 if rng.random() < py_giusta else 0 for _ in range(6)]
        py_sei = sum(campione) / 6.0
        errori_sei.append(abs(py_sei - py_giusta))
        low2, upper2 = estremi(py_x, py_nox, py_sei, q)
        if low2 > upper2:
            sei_rovesciati += 1
        if not (low2 - 1e-12 <= pns <= upper2 + 1e-12):
            sei_fuori += 1

        # Py moltiplicata per il fattore reale di CF2: 0.166667 / 0.115265
        py_fatt = min(1.0, py_giusta * 1.446)
        low3, upper3 = estremi(py_x, py_nox, py_fatt, q)
        if low3 > upper3:
            fattore_rovesciati += 1
        if not (low3 - 1e-12 <= pns <= upper3 + 1e-12):
            fattore_fuori += 1

    n = args.modelli
    errori_sei.sort()
    print(f"modelli: {n}   blocchi dell'esogena: {args.blocchi}   seed: {args.seed}")
    print(f"Py esatta (giunto)      -> PNS fuori: {giusti_fuori}/{n}, "
          f"rovesciati: {giusti_rovesciati}/{n}")
    print(f"Py da 6 righe           -> PNS fuori: {sei_fuori}/{n}, "
          f"rovesciati: {sei_rovesciati}/{n}   "
          f"errore mediano di Py: {errori_sei[len(errori_sei)//2]:.3f}")
    print(f"Py x 1.446 (CF2)        -> PNS fuori: {fattore_fuori}/{n}, "
          f"rovesciati: {fattore_rovesciati}/{n}")
    if ampiezza:
        ampiezza.sort()
        print(f"ampiezza mediana dell'intervallo esatto: "
              f"{ampiezza[len(ampiezza)//2]:.3f}")
    b_ok = giusti_fuori == 0 and sei_fuori > 0
    print()
    print(f"PARTE B: {'OK' if b_ok else 'INATTESO'} - "
          f"{'la formula regge con la Py del giunto e cade con la stima su 6 righe' if b_ok else 'vedi conteggi sopra'}")
    if not b_ok:
        esito = 1

    return esito


if __name__ == "__main__":
    sys.exit(main())
