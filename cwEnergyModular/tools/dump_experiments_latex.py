# -*- coding: utf-8 -*-
r"""
tools/dump_experiments_latex.py -- Inventario degli artefatti sperimentali per
l'Appendice E, generato da disco, git e codice; mai trascritto a mano.

Perche': la tesi sostiene che ogni numero abbia una provenienza verificabile, e
l'elenco dei run e' la prima cosa a invecchiare. Qui nessuna colonna e' scritta
dall'autore del generatore: ogni colonna viene da una fonte diversa e le fonti si
possono incrociare.

  (a) FILESYSTEM  -- experiment_results/: nome, dimensione, mtime. Il mtime e'
      l'orologio della macchina che ha eseguito il run, non una data copiata in
      un verbale.
  (b) GIT         -- due fatti separati: se il file e' tracciato (`git ls-files`)
      e quale commit lo ha AGGIUNTO (`git log --diff-filter=A`). Un artefatto non
      committato esiste per chi lo ha eseguito e non esiste per chi clona il repo:
      la tabella lo conta invece di tacerlo.
  (c) CODICE      -- quale .py del repo scrive quel prefisso, con file:riga.
      E' l'unica colonna che risponde a "da dove viene questo file" senza chiedere
      il permesso alla memoria di chi scrive.

Le due DATE di taglio non sono costanti del file: vengono chieste a git per hash
(1422d1b = fix degli omonimi non-Power nel percorso power-integration; 3b45a72 =
EMI diventa metodo principale). Il generatore riporta SOLO il rapporto cronologico
fra mtime e commit: "prima", "dopo", "attraversa". Che cosa la cronologia significhi
per un numero -- cioe' che gli assoluti LHM letti prima di 1422d1b sono invalidati
-- e' un giudizio fisico con prove sue (8aae3f9, ebfc269), e come giudizio sta nel
capitolo scritto a mano, non in una colonna generata.

Uso (da cwEnergyModular/):
    python tools/dump_experiments_latex.py > ../Tesi-latex/qoder-bozza/generated/artefatti_appE.tex
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
MODULE_DIR = os.path.dirname(HERE)
ROOT = os.path.dirname(MODULE_DIR)
RESULTS = os.path.join(ROOT, "experiment_results")
if MODULE_DIR not in sys.path:
    sys.path.insert(0, MODULE_DIR)

# Le convenzioni LaTeX dell'Appendice D valgono anche qui: si importano, non si
# duplicano -- due copie della stessa regola divergono, e la divergenza e' invisibile.
from tools.dump_tests_latex import (  # noqa: E402
    _LATINA, fuori_latino, tex_escape, _spezza_camel, _spezza_percorso,
)

#: hash dei due tagli e il perche' della loro scelta (entrambi stampati in testa)
TAGLI = [
    ("1422d1b", "fix omonimi nel percorso power-integration"),
    ("3b45a72", "EMI diventa metodo principale su Windows"),
]

# Cartelle fuori dalla ricerca del codice: la banca di esperimenti di altri non e'
# un harness di questo progetto, e Tesi-latex/ contiene solo testo.
ESCLUDI = {".git", "__pycache__", "experiment_results", "Tesi-latex", "handoff",
           "node_modules", ".qoder", "cpuepower", "cpuepower2", "C"}

SEP = "\x1f"
_RIF_TS = re.compile(r"_\d{8}_\d{6}")
_RIF_TS_SOLO = re.compile(r"_\d{8}$")
_CODA = re.compile(r"_(?:console|err|analisi|stessa_finestra|run2_console)$")


def git(*args: str) -> str:
    """git nel root del repo; '' se il comando fallisce (repo assente, hash ignoto)."""
    try:
        p = subprocess.run(["git", "--no-optional-locks", *args], cwd=ROOT,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=180)
    except Exception:
        return ""
    return p.stdout if p.returncode == 0 else ""


def tracciati() -> set:
    """Percorsi relativi dei file di experiment_results/ conosciuti da git."""
    return {l.strip() for l in git("ls-files", "--", "experiment_results").splitlines()
            if l.strip()}


def commit_che_aggiunge() -> dict:
    """percorso -> (hash corto, data ISO, subject) del commit che lo ha aggiunto.

    `git log` cammina dal piu' recente, quindi l'ultima occorrenza letta e' il
    primo add. Un file rinominato dopo l'aggiunta darebbe il commit del
    rinominamento: il dubbio e' dichiarato nel capitolo, non risolto qui.
    """
    out = git("log", "--diff-filter=A", "--name-only",
              "--format=%h" + SEP + "%aI" + SEP + "%s", "--", "experiment_results")
    mappa, cur = {}, None
    for riga in out.splitlines():
        riga = riga.rstrip("\r")
        if not riga:
            continue
        if SEP in riga:
            parti = riga.split(SEP)
            cur = (parti[0], parti[1], parti[2]) if len(parti) == 3 else None
        elif cur and riga.startswith("experiment_results/"):
            mappa[riga] = cur
    return mappa


def data_taglio(hash_corto: str):
    """(hash, datetime aware, subject) letti da git. None se l'hash non esiste."""
    parti = git("show", "-s", "--format=%h" + SEP + "%aI" + SEP + "%s",
                hash_corto).strip().split(SEP)
    if len(parti) != 3 or not parti[1]:
        return None
    try:
        return parti[0], datetime.fromisoformat(parti[1]), parti[2]
    except ValueError:
        return None


def sorgenti_python() -> list:
    """[(rel, testo)] dei .py del progetto, escluse le cartelle non pertinenti."""
    out = []
    for cart, dirs, files in os.walk(ROOT):
        rel_cart = os.path.relpath(cart, ROOT).replace("\\", "/")
        if rel_cart.split("/")[0] in ESCLUDI:
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in ESCLUDI]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(cart, f)
            try:
                out.append((os.path.relpath(p, ROOT).replace("\\", "/"),
                            open(p, encoding="utf-8", errors="replace").read()))
            except OSError:
                continue
    return out


#: cella quando nessun .py costruisce il nome con questo prefisso
NON_RIPRODUCIBILE = "\\textit{--}"


def cerca_autore(prefisso: str, fonti: list) -> list:
    """['file:riga', ...] dei .py che COSTRUISCONO un nome con questo prefisso.

    Un criterio solo, e preciso: il prefisso deve comparire in una riga dove il
    pezzo dopo l'underscore e' un segnaposto (``lhm_pi_path_{ts}.json``) e non un
    timestamp concreto (``lhm_validation_v3_20261023_160430.csv``). Nel primo caso
    la riga DECIDE il nome di un file che deve nascere, nel secondo nomina un file
    che esiste gia': e' lettore, non autore. I commenti sono esclusi perche'
    citano senza scrivere -- e nella prima versione due commenti da soli
    producevano tre attribuzioni false (``idle_floor_sensitivity.py`` sembrava
    l'autore dei CSV v3 che invece rilegge).

    Un prefisso senza costruttore e' informazione, non un buco da mascherare:
    vuol dire che quell'artefatto non si rigenera dal codice attuale del repo.
    """
    colpiti = []
    esc = re.escape(prefisso)
    costruito = re.compile(esc + r"(?:_[A-Za-z0-9]*)?_\{")   # prefix..._{ts}
    concreto = re.compile(esc + r"_\d{8}")                    # prefix..._20261023
    for rel, testo in fonti:
        base = rel.rsplit("/", 1)[-1]
        for i, riga in enumerate(testo.splitlines(), 1):
            if riga.strip().startswith("#"):
                continue
            if not costruito.search(riga) or concreto.search(riga):
                continue
            colpiti.append((0 if prefisso.lower() in base.lower() else 1,
                            len(rel), i, rel))
    if not colpiti:
        return []
    colpiti.sort()
    visti, out = set(), []
    for _, _, i, rel in colpiti:
        if rel in visti:
            continue
        visti.add(rel)
        out.append(f"{rel}:{i}")
    return out


def periodo(rs: list) -> str:
    """Primo e ultimo giorno del gruppo, senza orario: sta nel registro per file."""
    t0, t1 = rs[0]["dt"], rs[-1]["dt"]
    if t0.date() == t1.date():
        return t0.strftime("%d/%m")
    return f"{t0.strftime('%d/%m')}--{t1.strftime('%d/%m')}"



def gruppo(nome: str) -> str:
    """Prefisso del gruppo: nome senza estensione, senza timestamp, senza coda."""
    base = os.path.splitext(nome)[0]
    g = _RIF_TS.sub("", base)
    g = _CODA.sub("", g)
    g = _RIF_TS_SOLO.sub("", g)
    return g or base


def rapporto(rs: list, taglio) -> str:
    """'pr', 'po', 'at' o '-': solo cronologia dei mtime del gruppo.

    Due lettere perche' la colonna divide il testo con le altre sei. La legenda
    (pr = prima del taglio, po = dopo, at = il gruppo ha file da entrambi i lati)
    viene stampata sopra la tabella, non lasciata immaginare.
    """
    if taglio is None:
        return "-"
    lati = {"pr" if r["dt"] < taglio[1] else "po" for r in rs}
    return "at" if len(lati) > 1 else lati.pop()


def cella(testo, max_len: int, non_latini: list) -> str:
    """Spazi compressi, troncamento, escape, non-latini; \\ldots aggiunto per ultimo."""
    t = " ".join(str(testo).split())
    if max_len and len(t) > max_len:
        t = t[:max_len].rstrip() + "\x00"
    tex = tex_escape(t.replace("\x00", ""))
    tex, n = fuori_latino(tex)
    non_latini[0] += n
    if t.endswith("\x00"):
        tex += "\\ldots"
    return tex


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if not os.path.isdir(RESULTS):
        print("% experiment_results/ non trovato: niente inventario da generare.")
        return 1

    tracc = tracciati()
    adds = commit_che_aggiunge()
    fonti = sorgenti_python()
    tagli = [data_taglio(h) for h, _ in TAGLI]

    # (a) il filesystem: unica fonte dei file che esistono davvero. Ricorsivo:
    # un CSV di CodeCarbon finisce in una sottocartella, e un inventario che
    # guarda solo il primo livello lo perderebbe in silenzio.
    righe = []
    for cart, dirs, files in os.walk(RESULTS):
        for nome in sorted(files):
            p = os.path.join(cart, nome)
            rel = os.path.relpath(p, ROOT).replace("\\", "/")
            st = os.stat(p)
            righe.append({"nome": os.path.relpath(p, RESULTS).replace("\\", "/"),
                          "gruppo": gruppo(nome),
                          "kb": st.st_size / 1024.0,
                          "dt": datetime.fromtimestamp(st.st_mtime).astimezone(),
                          "tracciato": rel in tracc, "add": adds.get(rel)})
    if not righe:
        print("% experiment_results/ vuoto: niente inventario.")
        return 1

    gruppi = {}
    for r in righe:
        gruppi.setdefault(r["gruppo"], []).append(r)
    ordine = sorted(gruppi.items(), key=lambda kv: min(r["dt"] for r in kv[1]))

    non_latini = [0]
    cache_autore = {g: cerca_autore(g, fonti) for g, _ in ordine}
    corpo = []
    a = corpo.append

    # ---- legenda: le colonne sono due lettere, e due lettere senza legenda
    # sono un rebus. Sta nel file generato, non nel capitolo: se la tabella
    # cambia, la legenda cambia con essa.
    a("{\\small\\textbf{Legenda.} \\texttt{file} = tracciati da git / esistenti su "
      "disco; \\texttt{giorni} = dal primo all'ultimo \\texttt{mtime} del gruppo; "
      "\\texttt{scritto da} = il \\texttt{.py} che costruisce il nome del file "
      "(\\texttt{--} in corsivo: nessun costruttore nel codice, quindi l'artefatto "
      "non si rigenera da qui); \\texttt{vs} = cronologia dei \\texttt{mtime} "
      "rispetto ai due commit \\texttt{1422d1b} e \\texttt{3b45a72}: \\texttt{pr} "
      "prima, \\texttt{po} dopo, \\texttt{at} il gruppo ha file da entrambi i lati "
      "del taglio. Nessuna di queste colonne dice se un numero \\`e valido.\\par}")
    a("\\medskip")
    a("")

    # ---- tabella dei gruppi. Sette colonne, non otto: la prima versione ne aveva
    # una per taglio e sfondava di 6-13 pt su ogni riga. I due rapporti stanno ora
    # in una cella sola ("pr/po"), con la legenda scritta sopra la tabella.
    a("{\\footnotesize")
    a("\\setlength{\\tabcolsep}{3.5pt}")
    a("\\begin{longtable}{@{}r >{\\raggedright\\arraybackslash}p{0.215\\textwidth} "
      "r r >{\\raggedright\\arraybackslash}p{0.105\\textwidth} "
      ">{\\raggedright\\arraybackslash}p{0.235\\textwidth} "
      ">{\\raggedright\\arraybackslash}p{0.075\\textwidth}@{}}")
    # Intestazione corta: gli hash dei due tagli stanno nella legenda, perche'
    # "vs 1422d1b/3b45a72" in una colonna da 0.075\textwidth non ci sta e la
    # riga di testata sfonda di 10 pt.
    testata = ("$n$ & \\textbf{gruppo} & \\textbf{file} & \\textbf{KB} & "
               "\\textbf{giorni} & \\textbf{scritto da} & \\textbf{vs i due tagli} \\\\")
    for fine in ("endfirsthead", "endhead"):
        a("\\toprule")
        a(testata)
        a("\\midrule")
        a("\\" + fine)          # non basta "\\" + fine: come espressione nuda e' un
        a("")                   # no-op, e la testata finisce dentro \endfoot
    a("\\midrule")
    a("\\endfoot")
    a("\\bottomrule")
    a("\\endlastfoot")

    for i, (g, rs) in enumerate(ordine, 1):
        rs = sorted(rs, key=lambda r: r["dt"])
        n_t = sum(1 for r in rs if r["tracciato"])
        kb = sum(r["kb"] for r in rs)
        autori = cache_autore[g]
        # al massimo due costruttori nella cella; il resto lo si conta
        if not autori:
            cella_a = NON_RIPRODUCIBILE
        else:
            testo_a = ", ".join(autori[:2]) + (" (+%d)" % (len(autori) - 2)
                                               if len(autori) > 2 else "")
            cella_a = _spezza_percorso(cella(testo_a, 44, non_latini))
        a("%d & \\texttt{%s} & %d/%d & %.0f & %s & \\texttt{%s} & %s/%s \\\\" % (
            i, _spezza_camel(_spezza_percorso(cella(g, 0, non_latini))),
            n_t, len(rs), kb, periodo(rs),
            cella_a, rapporto(rs, tagli[0]), rapporto(rs, tagli[1])))
    a("\\end{longtable}")
    a("}")
    a("")

    # ---- registro: un riga per artefatto, con il commit che l'ha aggiunto.
    # L'assenza di un commit e' una cella, non una nota a pie' di pagina: un
    # artefatto mai committato esiste su questa macchina e non nel repo.
    a("\\paragraph{Registro degli artefatti, con il commit di prima comparizione}")
    a("{\\footnotesize\\begin{longtable}{@{}>{\\raggedright\\arraybackslash}"
      "p{0.40\\textwidth} l r >{\\raggedright\\arraybackslash}"
      "p{0.14\\textwidth}@{}}")
    a("\\toprule \\textbf{file} & \\textbf{mtime} & \\textbf{KB} & "
      "\\textbf{commit} \\\\")
    a("\\midrule\\endfirsthead")
    a("\\toprule \\textbf{file} & \\textbf{mtime} & \\textbf{KB} & "
      "\\textbf{commit} \\\\")
    a("\\midrule\\endhead")
    a("\\midrule\\endfoot\\bottomrule\\endlastfoot")
    for r in sorted(righe, key=lambda r: r["dt"]):
        add = r["add"]
        etichetta = ("\\texttt{%s}" % add[0]) if add else "\\textit{mai committato}"
        a("\\texttt{%s} & %s & %.0f & %s \\\\" % (
            _spezza_percorso(cella(r["nome"], 76, non_latini)),
            r["dt"].strftime("%d/%m %H:%M"), r["kb"], etichetta))
    a("\\end{longtable}}")
    a("")

    # ---- intestazione: costruita per ultima, cosi' i conteggi sono veri.
    # Qui si usano f-string e non l'operatore %: una riga che comincia con il
    # percento dei commenti LaTeX, seguita da spazio e da una lettera, viene
    # letta da Python come flag ' ' + modificatore di lunghezza 'h' + conversione
    # (e "% host" diventa %o, che vuole un intero). Il bug non e' ipotetico.
    tot_kb = sum(r["kb"] for r in righe)
    n_tracc = sum(1 for r in righe if r["tracciato"])
    head = git("rev-parse", "--short", "HEAD").strip() or "?"
    testa = ["% generato da tools/dump_experiments_latex.py -- NON editare a mano",
             f"% host: {platform.system()} {platform.release()} | "
             f"python {platform.python_version()} | HEAD {head}",
             f"% artefatti su disco: {len(righe)} in {len(gruppi)} gruppi; "
             f"tracciati da git: {n_tracc} ({len(righe) - n_tracc} no); "
             f"{tot_kb:.0f} KB in totale",
             "% colonne 'vs' = cronologia fra il mtime del file e il commit del taglio,"]
    for (h, motivo), t in zip(TAGLI, tagli):
        quando = t[1].strftime("%Y-%m-%d %H:%M") if t else "NON RISOLTO DA GIT"
        nota = "" if t else " -- colonne 'vs' a '-'"
        testa.append(f"%   {h} = {quando} ({motivo}){nota}")
    testa += ["% non validita' del numero: la conseguenza e' giudizio, e sta nel capitolo.",
              "% 'scritto da' = .py del repo che COSTRUISCE il nome (con segnaposto,",
              "% non con un timestamp gia' scritto): '--' in corsivo = nessun costruttore",
              "% trovato, cioe' l'artefatto non si rigenera dal codice attuale.",
              "% 'mai committato' = l'artefatto esiste su questa macchina, non nel repo.",
              f"% {non_latini[0]} caratteri fuori dal range latino resi come codepoint.",
              ""]
    sys.stdout.write("\n".join(testa) + "\n" + "\n".join(corpo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
