"""Confronto fra varianti riga per riga, con lo stesso metro di `benchmark/valuta.py`.

Perche' esiste. La scelta fra "la variante migliore" e "fondere le varianti" non
si decide sui totali: 32 su 81 non dice se `b_composta`, recuperando le etichette,
ha perso righe che `b_esempi` gia' prendeva. Serve l'insieme delle righe corrette
di ciascuna variante e la loro differenza, perche' due totali uguali possono
corrispondere a due insiemi disgiunti, e la fusione in quel caso vale la somma.

Riusa `_valuta_run`, `_gt` e `_carica` di `valuta.py` invece di reimplementare il
confronto: se questo script avesse una sua copia della regola, una modifica al
metro darebbe due verdetti diversi sulla stessa riga. `valuta.py` e' il metro
congelato (TOLL 0,0005, `corretta = etichetta_ok AND numero_ok`).

Cosa stampa, per variante: quante righe corrette e quali; per ogni coppia la
lista `solo A` / `solo B`; poi l'unione, il numero di righe che almeno una
variante prende, che e' il **limite superiore** di una fusione perfetta e non una
previsione -- fondere non aggiunge intelligenza, toglie solo i guasti che si
escludono a vicenda.

Uso:  python confronto_varianti.py harness/risultati/b_esempi/<ts> \
                                  harness/risultati/b_composta/<ts>
      (cartelle del run, non il genitore: due esecuzioni della stessa variante
       sotto lo stesso genitore sono due protocolli diversi e vanno tenute
       separate -- `citazione_output` e' una di quelle differenze)
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import run_query                     # noqa: F401,E402  installa gli shim `tools`/`agents`
from benchmark import valuta         # noqa: E402


def verdetti(cartella: Path) -> dict:
    """{task_id: verdetto} di un run, calcolato dalla funzione usata da valuta.py."""
    gt = valuta._gt()
    hash_reti = valuta._hash_reti()
    esiti = {}
    for riga in valuta._carica(cartella):
        g = gt.get(riga.get("task_id"))
        if g is None:
            raise SystemExit(f"{cartella}: task_id {riga.get('task_id')!r} non e' nel benchmark")
        v = valuta._valuta_run(riga, g, hash_reti)
        esiti[v["task_id"]] = v
    return esiti


def nome(cartella: Path) -> str:
    return f"{cartella.parent.name}/{cartella.name}"


def main() -> int:
    cartelle = [Path(c).resolve() for c in sys.argv[1:]]
    if len(cartelle) < 2:
        print("servono almeno due cartelle di run")
        return 2

    insiemi, tutte_le_righe = {}, set()
    for c in cartelle:
        v = verdetti(c)
        tutte_le_righe |= set(v)
        insieme = {t for t, x in v.items() if x["corretta"]}
        insiemi[nome(c)] = insieme
        etich = sum(1 for x in v.values() if x["etichetta_ok"])
        mapp = sum(1 for x in v.values() if x["mappatura_ok"])
        print(f"{nome(c):44} righe {len(v):3}  etichetta_ok {etich:3}  "
              f"mappatura_ok {mapp:3}  corrette {len(insieme):3}")

    chiavi = list(insiemi)
    unione = set().union(*insiemi.values())
    print(f"\nunione delle righe corrette da almeno una variante: {len(unione)} "
          f"(limite superiore di una fusione perfetta, non una previsione)")
    print(f"righe che nessuna delle varianti confrontate prende: "
          f"{len(tutte_le_righe - unione)} su {len(tutte_le_righe)}")

    print("\ncoppie:")
    for i in range(len(chiavi)):
        for j in range(i + 1, len(chiavi)):
            a, b = chiavi[i], chiavi[j]
            solo_a = sorted(insiemi[a] - insiemi[b])
            solo_b = sorted(insiemi[b] - insiemi[a])
            comune = len(insiemi[a] & insiemi[b])
            print(f"  {a}  vs  {b}")
            print(f"    in comune {comune} | solo prima {len(solo_a)} {solo_a}")
            print(f"               solo seconda {len(solo_b)} {solo_b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
