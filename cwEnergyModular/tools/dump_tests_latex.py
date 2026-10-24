# -*- coding: utf-8 -*-
"""
tools/dump_tests_latex.py — Inventario della suite di test per l'Appendice D,
generato eseguendo la suite e leggendo le docstring, non trascritto a mano.

Motivo: come per lo schema CSV (dump_schema_latex.py), l'elenco dei test invecchia
al primo test nuovo. Qui la fonte tripla e' (a) `pytest --collect-only` per i node
id reali, (b) l'AST dei file di test per la prima riga di docstring di ciascuno,
(c) un `pytest -v` eseguito adesso per lo stato reale di ogni test e il motivo
di ogni salto. I tre strati possono discordare (test scritto e mai raccolto,
raccolto e mai eseguito): il generatore li confronta e segnala la discordanza
invece di nasconderla.

Nessuna etichetta e' inventata: la colonna "che cosa asserisce" e' la prima riga
di docstring dell'autore del test, troncata; se manca, si stampa 'nessuna
docstring' (caso documentato, non mascherato).

Uso (da cwEnergyModular/):
    python tools/dump_tests_latex.py > ../Tesi-latex/qoder-bozza/generated/test_suite_appD.tex
"""
from __future__ import annotations

import argparse
import ast
import os
import platform
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

try:
    import elevation  # noqa: E402  (is_admin: condizione di esecuzione reale)
except Exception:  # pragma: no cover - piattaforma non Windows
    elevation = None

MAX_DOC = 150
MAX_MOD_DOC = 420

# Esiti pytest -> etichetta della tabella. Un fallimento resta in grassetto: se
# un giorno la suite non passa, l'appendice deve dirlo, non nasconderlo.
ESITI = {
    "PASSED": "passato",
    "SKIPPED": "saltato",
    "FAILED": "\\textbf{fallito}",
    "ERROR": "\\textbf{errore}",
    "XFAIL": "atteso fallito",
    "XPASS": "\\textbf{atteso, passata}",
    "": "\\textbf{n/eseguito}",
}

_SOSTITUZIONI = {
    "\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "$": "\\$",
    "&": "\\&", "#": "\\#", "_": "\\_", "%": "\\%",
    "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
    '"': "\\textquotedbl{}",
}


def tex_escape(testo: str) -> str:
    """Escape LaTeX a passaggio singolo (stessa regola di dump_schema_latex.py)."""
    return re.sub(r'[\\{}$&#%_~^"]', lambda m: _SOSTITUZIONI[m.group(0)], testo)


def _spezza_identificatore(testo_escaped: str) -> str:
    """Punti di capo dopo underscore e trattini.

    Gli identificatori dei test sono lunghi e privi di spazi (
    test_A2_gpu_energia_indipendente_dall_utilizzo) e in \\texttt non vengono
    sillabati: senza \\allowbreak la colonna sfonda e longtable va in overfull.

    Il trattino serve quanto l'underscore perch\\`e i valori parametrizzati di
    oggi sono etichette di canale (emi-counter, librehardwaremonitor-energy,
    power-integration): il parametro e' stampato in \\texttt dentro la stessa
    colonna da 0,30\\textwidth, e 'librehardwaremonitor-energy' da sola e' pi\\`u
    larga della colonna (24/10, overfull di 66 pt su riga 243 del file generato).
    """
    out = testo_escaped.replace("\\_", "\\_\\allowbreak{}")
    return out.replace("-", "-\\allowbreak{}")


def _spezza_percorso(testo_escaped: str) -> str:
    """Punti di capo in un percorso relativo (\texttt{tests/test\\_x.py}).

    Un percorso lungo in \\paragraph puo' andare a capo solo qui, non nel testo
    circostante: senza \\allowbreak il titolo del paragrafo va in overfull.
    L'ordine conta: si lavora sull'escaped, quindi '\\_' e' gia' la forma LaTeX.
    """
    out = testo_escaped.replace("\\_", "\\_\\allowbreak{}")
    return out.replace("/", "/\\allowbreak{}")


def cella_test(fname: str, classe: str, param: str) -> str:
    """La prima colonna della riga: \texttt{nome(classe)} col parametro tra parentesi.

    Estratta dal ciclo di emissione perche' e' IL punto dove l'impaginazione si
    decide: se qui un frammento non ha un \\allowbreak, la colonna da
    0,30\\textwidth sfonda e il PDF va in overfull (24/10, sei righe). Tenere la
    logica in una funzione vuol dire poterla verificare senza compilare la tesi.
    """
    nome = _spezza_camel(_spezza_identificatore(tex_escape(fname)))
    if param:
        # \\allowbreak ANCHE prima della parentesi: senza, la coda del nome e
        # l'apertura del parametro formano un solo blocco inseguibile
        # ('numero({librehardwaremonitor-', 29 caratteri) e la colonna sfonda
        # comunque, hyphen o non hyphen.
        nome += "\\allowbreak{}\\,(\\texttt{%s})" % _spezza_identificatore(
            tex_escape(param))
    if classe:
        nome = "\\texttt{%s}:\\allowbreak{} %s" % (
            _spezza_camel(_spezza_identificatore(tex_escape(classe))), nome)
    else:
        nome = "\\texttt{%s}" % nome
    return nome


def frammenti_inseguibili(testo_tex: str) -> list:
    """I pezzi di testo LaTeX che NON possono andare a capo, cioe' fra un \\allowbreak e l'altro.

    Serve alla verifica (tests/test_dump_node_id.py): un frammento piu' lungo
    della colonna e' un overfull box gia' scritto, indipendentemente da che cosa
    dice la riga.
    """
    pulito = (testo_tex.replace("\\allowbreak{}", "\x00")
              .replace("\\,", "").replace("\\texttt", "").replace("\\_", "_"))
    return [f.strip("{}():; ") for f in pulito.split("\x00") if f.strip("{}():; ")]


def _spezza_camel(testo_escaped: str) -> str:
    """Punti di capo prima di ogni maiuscola interna a un identificatore.

    I nomi delle classi di test sono CamelCase senza underscore
    (TestEvaluateResponseIntegration) e \\texttt non li sillaba: un solo
    identificatore del genere in una colonna da 0.30\\textwidth va in overfull di
    44 pt. \\allowbreak prima di ogni maiuscola spezza sui confini delle parole.
    """
    return re.sub(r'(?<!^)(?<!\\)([A-Z])', r"\\allowbreak{}\1", testo_escaped)


# Caratteri che pdflatex + T1 sa comporre. I docstring dei test citano testi di
# esempio in qualsiasi lingua (uno di essi riporta "Atene (in greco: ...)"), e
# un solo carattere fuori dal range latino interrompe la compilazione di tutta
# la tesi con "Unicode character not set up for use with LaTeX".
_LATINA = (lambda ch: (0x20 <= ord(ch) <= 0x7E) or (0xA0 <= ord(ch) <= 0x17F)
           or ord(ch) in {0x2013, 0x2014, 0x2018, 0x2019, 0x201C, 0x201D, 0x2026})


def fuori_latino(testo_escaped: str) -> tuple:
    """Sostituisce i caratteri non latini con il loro codepoint, e li conta.

    Non c'e' translitterazione: riscrivere "Αθήνα" come "Athina" in una citazione
    della docstring di un altro autore sarebbe invenzione. Il marcatore
    \texttt{[U+0391 U+03B8 ...]} e' verificabile e dice esattamente quanto il
    generatore non ha saputo comporre.
    """
    fuori = [ch for ch in testo_escaped if not _LATINA(ch)]
    if not fuori:
        return testo_escaped, 0

    def sostitu(m):
        codici = " ".join("U+%04X" % ord(ch) for ch in m.group(0))
        return "\\texttt{%s}" % ("[" + codici + "]")

    out = re.sub(r'[^\x20-\x7E\xA0-\u017F\u2013\u2014\u2018-\u201D\u2026]+', sostitu,
                 testo_escaped)
    return out, len(fuori)


def docstring_da_ast(percorso: str) -> tuple:
    """(docstring del file, nome funzione -> prima riga della sua docstring).

    La docstring del modulo e' stampata perche' su questa suite la copertura dei
    singoli test e' parziale (il conteggio reale finisce nell'intestazione del
    file generato): cio' che un file prova sta nella sua intestazione, che e'
    testo dell'autore del test, non una parafrasi aggiunta qui.
    """
    out = {}
    with open(percorso, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=os.path.basename(percorso))

    def prima_riga(node) -> str:
        doc = ast.get_docstring(node)
        if not doc:
            return ""
        return doc.strip().splitlines()[0].strip()

    def registra(nodo, classe) -> None:
        if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name.startswith("test"):
            out[(classe, nodo.name)] = prima_riga(nodo)

    # Chiave (classe, nome), non il solo nome: in test_answer_type_evaluation.py
    # due classi hanno un test_exact_match omonimo, e con la chiave corta una
    # delle due docstring sarebbe finita su entrambe le righe.
    for nodo in tree.body:
        registra(nodo, "")
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ClassDef):
            for figlio in nodo.body:
                registra(figlio, nodo.name)
    return (ast.get_docstring(tree) or "").strip(), out


def raccogli(pytest_args: list) -> list:
    """Node id raccolti da `pytest --collect-only -q` (vuoti se la raccolta fallisce)."""
    proc = subprocess.run([sys.executable, "-m", "pytest", *pytest_args],
                          cwd=MODULE_DIR, capture_output=True, text=True, encoding="utf-8")
    righe = []
    for ln in (proc.stdout or "").splitlines():
        ln = ln.strip()
        if "::" in ln and not ln.startswith("="):
            righe.append(ln.split(" ")[0])
    return righe


def esegui(pytest_args: list) -> tuple[dict, dict, str]:
    """(esito per node id, motivi di skip, riga di riepilogo)."""
    proc = subprocess.run([sys.executable, "-m", "pytest", *pytest_args],
                          cwd=MODULE_DIR, capture_output=True, text=True, encoding="utf-8")
    esiti, motivi = {}, {}
    for ln in (proc.stdout or "").splitlines():
        m = re.match(r"^(\S+::\S+)\s+(PASSED|FAILED|SKIPPED|XFAIL|XPASS|ERROR)", ln.strip())
        if m:
            esiti[m.group(1)] = m.group(2)
        m2 = re.match(r"^SKIPPED \[\d+\] (\S+): (.*)$", ln.strip())
        if m2:
            motivi[m2.group(1)] = m2.group(2)
    riep = ""
    for ln in reversed((proc.stdout or "").splitlines()):
        if "passed" in ln or "skipped" in ln or "failed" in ln:
            riep = ln.strip().strip("=").strip()
            break
    return esiti, motivi, riep


def _spezza_node_id(testo: str, sep: str = "::") -> list:
    """Spezza su ``sep`` SOLO fuori dalle parentesi quadre del parametro.

    Un node id parametrizzato puo' avere un parametro che contiene ``::`` --
    e' il caso di un test parametrizzato con node id come input (in
    ``tests/test_dump_node_id.py``). Con un ``split("::")`` ingenuo il frammento
    dentro le parentesi veniva scambiato per una classe, e il nome del test
    tornava come ``test_semplice-atteso0]``: l'AST non conosce quel nome e la
    riga finisce in ``nomi non risolvibili``, cioe' nel rumore del verbale.
    """
    parti, corrente, profonadita, i = [], "", 0, 0
    while i < len(testo):
        car = testo[i]
        if car == "[":
            profonadita += 1
        elif car == "]":
            profonadita = max(profonadita - 1, 0)
        if profonadita == 0 and testo.startswith(sep, i):
            parti.append(corrente)
            corrente = ""
            i += len(sep)
            continue
        corrente += car
        i += 1
    parti.append(corrente)
    return parti


def nome_e_parametri(node_id: str) -> tuple:
    """(file, classe, nomefunzione, parametro) da un node id pytest."""
    percorso, _, resto = node_id.partition("::")
    parti = _spezza_node_id(resto)
    classe = parti[0] if len(parti) > 1 else ""
    ultima = parti[-1]
    m = re.match(r"^([\w]+)\[(.*)\]$", ultima)
    # (.*) e non (.+): un parametro vuoto e' un case reale --
    #   @pytest.mark.parametrize("metodo", ["unavailable", ..., ""])
    # produce il node id 'test_x[]'. Con .+ il match falliva, il nome
    # restituiva 'test_x[]' con le parentesi, la chiave (classe, nome) non
    # trovava la docstring e l'intestazione del verbale dichiarava
    # '100 righe documentate su 101': una copertura sotto-stimata dal
    # generatore, non un test senza docstring (24/10, osservato su
    # tests/test_metodo_ammissibile.py::test_stato_non_di_misura_produce_none).
    if m:
        return percorso, classe, m.group(1), m.group(2)
    return percorso, classe, ultima, ""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-run", action="store_true",
                   help="non eseguire la suite: inventario solo dalla raccolta")
    a = p.parse_args()

    raccolti = raccogli(["--collect-only", "-q"])
    esiti, motivi, riepilogo = ({}, {}, "") if a.no_run else esegui(["-v", "-rs"])
    elevato = None if elevation is None else elevation.is_admin()

    # gli identificatori dei node id di esecuzione sono relativi a MODULE_DIR,
    # quelli della raccolta pure: si confrontano in bassoie minuscole
    esiti_norm = {k.replace("\\", "/").lower(): v for k, v in esiti.items()}
    doc_cache = {}
    mod_doc = {}
    righe_per_file = {}
    for nid in raccolti:
        percorso, classe, fname, param = nome_e_parametri(nid)
        if percorso not in doc_cache:
            abs_path = os.path.join(MODULE_DIR, percorso)
            mod_doc[percorso], doc_cache[percorso] = (
                docstring_da_ast(abs_path) if os.path.exists(abs_path) else ("", {}))
        doc = doc_cache[percorso].get((classe, fname), "")
        esito = esiti_norm.get(nid.replace("\\", "/").lower(), "") if esiti else ""
        righe_per_file.setdefault(percorso, []).append((classe, fname, param, doc, esito, nid))

    n_doc = sum(len(v) for v in righe_per_file.values())
    n_senza_doc = sum(1 for lst in righe_per_file.values()
                      for (_c, _f, _p, doc, _e, _n) in lst if not doc)
    # un node id raccolto ma senza esito nell'esecuzione = discordanza fra i due
    # strati (raccolta vs run), e va stampata invece di sparire dalla tabella.
    non_eseguiti = [] if not esiti else [
        nid for lst in righe_per_file.values()
        for (_classe, _fname, _param, _doc, esito, nid) in lst if not esito
    ]

    # Il corpo si costruisce prima di stampare: l'intestazione deve poter dire
    # quanti caratteri non latini sono stati sostituiti, e lo si sa solo dopo.
    corpo, non_latini = [], [0]

    def emetti(riga: str = "") -> None:
        corpo.append(riga)

    def cella(testo: str, max_len: int) -> str:
        r"""Docstring pronta per una cella: spazio compresso, escape, tronco, non-latino.

        L'ordine conta due volte. (1) Il marcatore di troncamento \ldots va messo
        DOPO l'escape: tex_escape() trasformerebbe il suo backslash in
        '\textbackslash{}ldots', una macro rotta che pero' non ferma la
        compilazione, quindi si vedrebbe solo nella pagina stampata. (2) La
        sostituzione dei caratteri non latini avviene sull'escaped, perche' le
        sequenze LaTeX appena inserite sono ASCII e non vanno toccate due volte.
        """
        piano = " ".join(testo.split())
        tronco = len(piano) > max_len
        if tronco:
            piano = piano[:max_len - 1].rstrip()
        tex, n = fuori_latino(tex_escape(piano))
        non_latini[0] += n
        return tex + ("\\ldots" if tronco else "")

    intest = ("$n$ & \\textbf{test} & \\textbf{che cosa asserisce} & \\textbf{esito} \\\\")
    for percorso in sorted(righe_per_file):
        lst = righe_per_file[percorso]
        percorso_tex = _spezza_percorso(tex_escape(percorso.replace("\\", "/")))
        emetti("\\paragraph{%s --- %d test}\\mbox{}\\par" % (percorso_tex, len(lst)))
        modulo = mod_doc[percorso]
        if modulo:
            emetti("{\\small\\itshape %s}\\par\\medskip" % cella(modulo, MAX_MOD_DOC))
        emetti("{\\footnotesize")
        emetti("\\setlength{\\tabcolsep}{4pt}")
        emetti("\\begin{longtable}{@{}r >{\\raggedright\\arraybackslash}p{0.30\\textwidth} "
               ">{\\raggedright\\arraybackslash}p{0.47\\textwidth} >{\\raggedright\\arraybackslash}p{0.11\\textwidth}@{}}")
        emetti("\\toprule")
        emetti(intest)
        emetti("\\midrule")
        emetti("\\endfirsthead")
        emetti("\\toprule")
        emetti(intest)
        emetti("\\midrule")
        emetti("\\endhead")
        emetti("\\midrule")
        emetti("\\endfoot")
        emetti("\\bottomrule")
        emetti("\\endlastfoot")
        for i, (classe, fname, param, doc, esito, nid) in enumerate(lst, start=1):
            nome = cella_test(fname, classe, param)
            emetti(f"{i} & {nome} & {cella(doc, MAX_DOC) if doc else 'nessuna docstring'} "
                   f"& {ESITI.get(esito, esito.lower())} \\\\")
        emetti("\\end{longtable}")
        emetti("}")
        emetti()

    if motivi:
        emetti("\\paragraph{Motivi dei salti, riportati dall'esecuzione}")
        emetti("{\\footnotesize")
        emetti("\\begin{description}")
        emetti("\\sloppy")
        for nid, motivo in sorted(motivi.items()):
            emetti("\\item[\\texttt{%s}] %s" % (
                _spezza_percorso(tex_escape(nid.replace("\\", "/"))), cella(motivo, 400)))
        emetti("\\end{description}")
        emetti("}")

    print("% generato da tools/dump_tests_latex.py -- NON editare a mano")
    print(f"% host: {platform.system()} {platform.release()} | python {platform.python_version()} | "
          f"processo elevato: {'sconosciuto' if elevato is None else ('si' if elevato else 'no')}")
    if riepilogo:
        print(f"% esito esecuzione reale: {riepilogo}")
    print(f"% node id raccolti: {len(raccolti)}; righe di tabella: {n_doc}")
    if non_eseguiti:
        print(f"% ATTENZIONE: {len(non_eseguiti)} node id raccolti ma senza esito: "
              + ", ".join(non_eseguiti[:6]))
    print("% La colonna 'che cosa asserisce' e' la prima riga di docstring del test,")
    print("% non una parafrasi; 'nessuna docstring' indica il test che non ne ha.")
    print(f"% Copertura delle docstring: {n_doc - n_senza_doc} righe documentate su "
          f"{n_doc}; per ogni file, in corsivo, la sua docstring di intestazione.")
    print(f"% Troncature: docstring oltre {MAX_DOC} caratteri (test) o {MAX_MOD_DOC} "
          "(modulo) chiuse da \\ldots.")
    if non_latini[0]:
        print(f"% {non_latini[0]} caratteri fuori dal range latino (pdflatex con T1 non li")
        print("% compone) resi come codepoint verificabile, senza translitterarli: la")
        print("% docstring cita un testo in un'altra lingua e una citazione non si corregge.")
    print()
    for riga in corpo:
        print(riga)
    return 0


if __name__ == "__main__":
    sys.exit(main())
