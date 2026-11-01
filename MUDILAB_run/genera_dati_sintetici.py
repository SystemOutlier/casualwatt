"""Genera una tabella sintetica campionando il grafo dell'assicurazione.

Perche' esiste. DATI.csv e' una tavola di sei clienti con 20 delle 27 variabili
del grafo, e alcune celle fuori vocabolario (vedi verifica_righe_dati.md). Non e'
una distribuzione: le frequenze che se ne ricavano sono quantizzate in sesti e
per alcuni stati valgono zero. Questo script produce una tavola completa, con
tutte le variabili del grafo e solo stati ammessi, campionando il modello.

Cosa NON e'. Non e' un dato osservato, non e' una fonte indipendente dal grafo
(le sue frequenze tendono per costruzione alle marginali del modello), non va
usata per la Py di cobound, che va presa dal grafo, e non sostituisce DATI.csv.
Serve a due cose: provare i percorsi che leggono una tabella, e mostrare quanto
deve crescere N perche' una frequenza empirica approssimi la marginale.

Uso:
    python genera_dati_sintetici.py
    python genera_dati_sintetici.py --n 1000 --seed 7 --uscita prova.csv

Il campionamento usa il generatore globale di pyAgrum (initRandom): il seme e'
dichiarato e lo stesso seme produce la stessa tabella.
"""

import argparse
from pathlib import Path

import pandas as pd
import pyagrum as gum

BASE_DIR = Path(__file__).resolve().parent
GRAPH_PATH = BASE_DIR / "consegna" / "insurance_grafo.bif"


def carica_grafo(percorso=None):
    percorso = Path(percorso) if percorso else GRAPH_PATH
    if not percorso.exists():
        raise FileNotFoundError(f"genera_dati_sintetici: grafo non trovato in {percorso}")
    return gum.loadBN(str(percorso))


def nomi_ordinati(grafo):
    """Nomi delle variabili nell'ordine dei nodi.

    grafo.names() restituisce un set: iterarlo direttamente darebbe un ordine
    di colonne diverso a ogni processo (l'hash delle stringhe cambia), quindi la
    stessa tabella avrebbe due impronte diverse. Qui l'ordine e' quello dei nodi.
    """
    return [grafo.variable(i).name() for i in sorted(grafo.nodes())]


def campiona(grafo, n, seed=7):
    """Campiona n righe dal grafo e le valida contro le etichette del grafo.

    Il seme e' fisso e dichiarato: due chiamate con lo stesso seme danno la
    stessa tabella, e le prime m righe di un campione da n sono le stesse che si
    otterrebbero chiedendone m.
    """
    if n <= 0:
        raise ValueError(f"n deve essere positivo, ricevuto {n}")
    gum.initRandom(seed)
    # generateSample restituisce (DataFrame, secondi impiegati)
    frame, _ = gum.generateSample(grafo, n)
    frame = frame.reset_index(drop=True)
    frame.insert(0, "id", range(n))

    attese = nomi_ordinati(grafo)
    mancanti = [c for c in attese if c not in frame.columns]
    if mancanti:
        raise ValueError(f"campionamento incompleto, colonne assenti: {mancanti}")

    non_valide = valida_celle(frame, grafo)
    if non_valide:
        raise ValueError(f"campionamento con celle fuori vocabolario: {non_valide[:5]}")

    return frame[["id"] + attese]


def valida_celle(frame, grafo):
    """Elenca (riga, colonna, valore) delle celle che il grafo non ammette."""
    fuori = []
    for colonna in nomi_ordinati(grafo):
        if colonna not in frame.columns:
            fuori.append((None, colonna, "colonna assente"))
            continue
        ammessi = set(grafo.variable(colonna).labels())
        for riga, valore in enumerate(frame[colonna].tolist()):
            if valore not in ammessi:
                fuori.append((riga, colonna, valore))
    return fuori


def scrivi(frame, percorso):
    percorso = Path(percorso)
    frame.to_csv(percorso, index=False)
    return percorso


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n", type=int, default=2000, help="righe da campionare (default 2000)")
    ap.add_argument("--seed", type=int, default=7, help="seme del generatore (default 7)")
    ap.add_argument("--grafo", default=None, help=f"percorso del BIF (default {GRAPH_PATH.name})")
    ap.add_argument("--uscita", default=None, help="file CSV di uscita")
    args = ap.parse_args()

    grafo = carica_grafo(args.grafo)
    frame = campiona(grafo, args.n, seed=args.seed)

    uscita = args.uscita or BASE_DIR / f"DATI_sintetico_n{args.n}_seed{args.seed}.csv"
    scrivi(frame, uscita)

    print(f"grafo:      {Path(args.grafo) if args.grafo else GRAPH_PATH}")
    print(f"righe:      {len(frame)}")
    print(f"colonne:    {len(frame.columns)} ({len(nomi_ordinati(grafo))} variabili del grafo + id)")
    print(f"celle non valide: {len(valida_celle(frame, grafo))}")
    print(f"scritto:    {uscita}")


if __name__ == "__main__":
    main()
