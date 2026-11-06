# -*- coding: utf-8 -*-
"""
tools/dump_schema_latex.py — Tabella dello schema di export per l'Appendice A,
generata dal codice e da un CSV reale (non trascritta a mano).

Motivo: la lista delle colonne vive in casualwatt_csv_export.CSV_COLUMNS e cresce
accodando (regola testata in
tests/test_energy_corrections.py::test_P2_colonna_csv_accodata_senza_cambiare_ordine);
un'appendice scritta a mano invecchia al primo campo nuovo.

Per ogni colonna stampa: posizione, nome esatto, valore dell'ultima riga dati del
CSV di riferimento (tronco a MAX_CELL), e 'nuova' quando quel file non contiene
ancora la colonna -- cio' documenta la migrazione dell'header, non un errore.
Nessuna unita' o definizione e' inventata qui: solo cio' che si legge nel codice
e nei dati.

Con --macros stampa invece i conteggi come comandi LaTeX (newcommand), da
inputare nel preambolo della tesi (generated/numeri_schema.tex). I capitoli e
l'Appendice A prendono da li' i numeri invece di trascriverli: un conteggio
scritto a mano invecchia alla stessa identica maniera della tabella, e in due
punti del corpo (capitoli 4 e 5) era gia' vecchio di una colonna.

Uso (da cwEnergyModular/):
    python tools/dump_schema_latex.py > schema_appA.tex
    python tools/dump_schema_latex.py --macros > numeri_schema.tex
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

from casualwatt_csv_export import CSV_COLUMNS, RUN_METADATA_COLUMNS  # noqa: E402

MAX_CELL = 30

_SOSTITUZIONI = {
    "\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "$": "\\$",
    "&": "\\&", "#": "\\#", "_": "\\_", "%": "\\%",
    "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
    '"': "\\textquotedbl{}",
}


def tex_escape(testo: str) -> str:
    r"""Escapes LaTeX minimo per una cella in \texttt{}.

    I caratteri sostituiti sono quelli che compaiono davvero nei valori (prompt,
    note, percorsi), e una tabella generata non puo' rompere la compilazione per
    un underscore.

    E' una singola passata con re.sub, non una catena di replace(): le
    sostituzioni inseriscono anch'esse delle parentesi graffe (\textbackslash{},
    \textasciitilde{}) e una seconda passata le scapperebbe di nuovo, producendo
    macro rotte -- e una macro rotta in una colonna larga e' un overfull che non
    si spiega leggendo il sorgente.
    """
    return re.sub(r'[\\{}$&#%_~^"]', lambda m: _SOSTITUZIONI[m.group(0)], testo)


def ultima_riga(csv_path: str) -> tuple[list[str], dict]:
    """(nomi dell'header, ultima riga dati) del CSV.

    L'header va letto a parte: 'colonna presente nel file' e 'colonna con valore
    vuoto' sono due stati diversi, e confonderli riscriverebbe proprio il difetto
    che l'appendice deve documentare.
    """
    if not os.path.exists(csv_path):
        return [], {}
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        righe = list(reader)
        nomi = list(reader.fieldnames or [])
    return nomi, (righe[-1] if righe else {})


def _spezza(testo_escaped: str) -> str:
    """Aggiunge punti di capo dopo i separatori tipici dei valori.

    I valori sono token monolitici in \\texttt{} -- percorsi Windows, timestamp
    ISO, note separate da ';' -- e \\texttt non sillaba: senza un \\allowbreak
    esplicito la colonna larga sfonda il testo e longtable va in overfull.
    L'ordine conta: i sostituti contengono backslash, quindi si lavora sul
    testo gia' escape e si parte dal separatore che produce \\textbackslash{}.
    """
    out = testo_escaped
    for src, dst in (("\\textbackslash{}", "\\textbackslash{}\\allowbreak{}"),
                     ("/", "/\\allowbreak{}"),
                     (";", ";\\allowbreak{}"),
                     (":", ":\\allowbreak{}"),
                     ("-", "-\\allowbreak{}")):
        out = out.replace(src, dst)
    return out


def cella(valore):
    """Cella del valore osservato: assente -> '-', troppo lungo -> tronco.

    L'ordine conta: si escape prima di accorciare, perche' il marcatore di
    troncamento e' una sequenza LaTeX e finirla dentro tex_escape() la
    trasformerebbe in 'backslash-ldots'.
    """
    if valore is None or valore == "":
        return "-"
    # un a capo dentro una cella spezzerebbe la riga del longtable: le note
    # multiple sono separate da ';', quindi la sostituzione e' innocua
    testo = str(valore).replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if len(testo) > MAX_CELL:
        return _spezza(tex_escape(testo[:MAX_CELL - 1])) + "\\ldots"
    return _spezza(tex_escape(testo))


def stato(colonna, header, riga):
    """Stato della colonna nel file di riferimento: '', 'vuota' o 'nuova'.

    Unica fonte del giudizio: la tabella e i conteggi delle macro passano di
    qui, cosi' un '27 vuota' dichiarato in un capitolo non puo' essere un
    numero diverso dai 27 che la tabella stampa.
    """
    if colonna not in header:
        return "nuova"      # colonna accodata dopo l'ultima scrittura del file
    if not riga.get(colonna):
        return "vuota"      # presente nell'header, valore assente in riga
    return ""


def conteggi(colonne, header, riga):
    """(dichiarate, nomi dell'header, nuove, vuote) per uno dei due schemi."""
    stati = [stato(c, header, riga) for c in colonne]
    return {
        "dichiarate": len(colonne),
        "header": len(header),
        "nuove": sum(1 for s in stati if s == "nuova"),
        "vuote": sum(1 for s in stati if s == "vuota"),
    }


def corpo(colonne, header, riga):
    """Righe LaTeX pronte per un ambiente longtable a 4 colonne."""
    note = []
    for i, nome in enumerate(colonne, start=1):
        note.append(
            f"{i} & \\texttt{{{tex_escape(nome)}}} & "
            f"\\texttt{{{cella(riga.get(nome))}}} & {stato(nome, header, riga)} \\\\\n"
        )
    return note


def macro(c_riga, c_meta, a):
    """I conteggi come comandi LaTeX, da inputare nel preambolo.

    Stesso `stato()` e stesse liste della tabella: il numero che un capitolo
    dichiara e il numero che la tabella stampa non possono divergere per
    costruzione. I nomi sono tipizzati per schema (riga / metadato) perche' il
    corpo della tesi cita entrambe le cifre, e confonderle e' l'errore gia'
    commesso sui $30$ che erano $31$.
    """
    righe = [
        ("nColonneRiga", c_riga["dichiarate"],
         "CSV_COLUMNS (casualwatt_csv_export.py:17-204)"),
        ("nColonneMetadati", c_meta["dichiarate"],
         "RUN_METADATA_COLUMNS (:343-361)"),
        ("nNuoveRiga", c_riga["nuove"],
         "di riga dichiarate nel codice e non ancora nel CSV di riferimento"),
        ("nNuoveMetadati", c_meta["nuove"],
         "di metadato dichiarate nel codice e non ancora nel loro CSV"),
        ("nCampiVuoti", c_riga["vuote"] + c_meta["vuote"],
         "header presente, valore assente nell'ultima riga dati"),
        ("nHeaderRiga", c_riga["header"],
         "nomi nell'header del CSV del dataset"),
        ("nHeaderMetadati", c_meta["header"],
         "nomi nell'header del CSV dei metadati"),
    ]
    print("% generato da tools/dump_schema_latex.py --macros -- non editare a mano")
    print("% I capitoli e l'Appendice A prendono i conteggi dello schema da qui:")
    print("% \\input{generated/numeri_schema.tex} sta nel preambolo di main.tex.")
    print(f"% CSV di riferimento: {a.csv} e {a.meta}")
    for nome, valore, commento in righe:
        testo = "\\newcommand{\\%s}{%d}" % (nome, valore)
        print("%-32s %% %s" % (testo, commento))


def main() -> int:
    # stdout in UTF-8: su Windows il codec della console (cp1252) corrompe le
    # lettere accentate che arrivano DAI VALORI del CSV -- il file generato
    # risulterebbe byte-non-UTF8 e pdflatex lo rifiuterebbe con
    # "Invalid UTF-8 byte sequence".
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default="results/semantic_evaluation_results.csv",
                   help="CSV di riferimento da cui leggere i valori di esempio")
    p.add_argument("--meta", default="results/casualwatt_run_metadata.csv",
                   help="CSV dei metadati di run per la seconda tabella")
    p.add_argument("--macros", action="store_true",
                   help="stampa i conteggi come \\newcommand invece della tabella")
    a = p.parse_args()

    header, riga = ultima_riga(a.csv)
    header_meta, riga_meta = ultima_riga(a.meta)
    c_riga = conteggi(CSV_COLUMNS, header, riga)
    c_meta = conteggi(RUN_METADATA_COLUMNS, header_meta, riga_meta)
    if a.macros:
        macro(c_riga, c_meta, a)
        return 0

    intest = ("$n$ & \\textbf{colonna} & \\textbf{ultimo valore del CSV di "
              "riferimento} & \\textbf{stato} \\\\")

    print("% generato da tools/dump_schema_latex.py -- non editare a mano")
    print(f"% CSV di riferimento: {a.csv} (header con {len(header)} campi)")
    print(f"% Colonne dichiarate nel codice: {c_riga['dichiarate']} di riga + "
          f"{c_meta['dichiarate']} metadati")
    print(f"% Non ancora presenti in quel file: {c_riga['nuove']} di riga, "
          f"{c_meta['nuove']} di metadati (acodate dopo la sua ultima scrittura)")
    print("% Le due colonne larghe sono p{} con riga spezzata: i nomi e i valori")
    print("% reali (timestamp ISO, percorsi Windows) non stanno in una l{}.")
    print("{\\footnotesize")
    print("\\setlength{\\tabcolsep}{4pt}")
    print("\\begin{longtable}{@{}r >{\\raggedright\\arraybackslash}p{0.29\\textwidth} "
          ">{\\raggedright\\arraybackslash}p{0.40\\textwidth} l@{}}")
    print("\\toprule")
    print(intest)
    print("\\midrule")
    print("\\endfirsthead")
    print("\\toprule")
    print(intest)
    print("\\midrule")
    print("\\endhead")
    print("\\midrule")
    print("\\endfoot")
    print("\\bottomrule")
    print("\\endlastfoot")
    for riga_tex in corpo(CSV_COLUMNS, header, riga):
        print(riga_tex, end="")
    print("\\end{longtable}")
    print("}")

    print()
    print("% --- metadati di run (RUN_METADATA_COLUMNS) ---")
    print(f"% CSV di riferimento: {a.meta} (header con {len(header_meta)} campi)")
    print("{\\footnotesize")
    print("\\setlength{\\tabcolsep}{4pt}")
    print("\\begin{longtable}{@{}r >{\\raggedright\\arraybackslash}p{0.29\\textwidth} "
          ">{\\raggedright\\arraybackslash}p{0.40\\textwidth} l@{}}")
    print("\\toprule")
    print(intest)
    print("\\midrule \\endfirsthead")
    print("\\toprule")
    print(intest)
    print("\\midrule \\endhead")
    print("\\midrule \\endfoot")
    print("\\bottomrule \\endlastfoot")
    for riga_tex in corpo(RUN_METADATA_COLUMNS, header_meta, riga_meta):
        print(riga_tex, end="")
    print("\\end{longtable}")
    print("}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
