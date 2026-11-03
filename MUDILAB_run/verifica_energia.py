"""Le aggregazioni alternative di `_energia`, ricalcolate sui 240 run registrati.

Perche' esiste. Il numero dichiarato della marca `b_composta` del 02-11
(`risultati_misura/b_composta/20261102_191401`) e' **964,929 J per risposta
corretta**: 74.299,5 J su 240 run divisi per le 77 righe uscite giuste. Viene da
`benchmark/valuta.py:_energia`, una cascata a tre rami -- finestra totale attiva,
poi finestra totale di package, poi somma dei passi -- e l'ultimo ramo soma
`energia_pkg_j` **anche quando il passo porta `energia_attiva_j` con
`attiva_valida` vera** (`:166-171`). Su questo il 02-11 ho scritto una frase al
volo, senza harness: "restano dentro 4.870 J di quota di riposo non sottratta, il
limite inferiore con la stessa energia attiva sarebbe 901,7 J/corretta (-6,6%)".
Era un claim ancorato a una lettura, non a un conto: qui lo si mette sotto
verifica aritmetica sugli stessi artefatti, **senza nuovo run e senza modello**.

Cosa produce. Sei definizioni di "joule di questo run", nessuna delle quali
adottata:

  `pubblicata`        la cascata di `valuta.py` cosi' com'e', che e' quella da cui
                      viene il numero in circolazione;
  `passi_attiva`      la stessa cascata, ma il terzo ramo usa l'energia attiva: e'
                      la correzione minima, e tocca solo le righe che il gate ha
                      fermato prima del calcolo della finestra;
  `tutto_attiva`      attiva sempre: finestra quando e' valida, poi i passi;
  `tutto_pkg`         package sempre, nessuna baseline sottratta;
  `solo_passi_pkg`    ignora la finestra totale e soma i passi;
  `solo_passi_attiva` idem, in attivo.

Le ultime due nominano il **secondo dislivello**, che non e' una questione di
baseline: la finestra totale di un run di successo copre anche il tempo fra un
passo e l'altro e il lavoro dell'orchestratore, mentre una riga fermata dal gate
non ha finestra e porta solo i suoi due passi. Confrontare i due rami della
cascata come se fossero la stessa grandezza sarebbe un errore di per se', anche
con le unita' allineate.

Cosa **non** fa: non cambia nessuna soglia, non riscrive nessun artefatto di
misura, non propone di sostituire il numero pubblicato. Le cifre nuove vanno
lette come "cosa direbbe la stessa marca sotto un'altra definizione", e la scelta
della definizione pubblicata e' una decisione, non un risultato di questo script.

Il conto, uscito il 03-11 sulla marca del 02-11
(`harness/risultati/verifica_energia_20261103.txt`). La frase del 02-11 torna
tutta: `pubblicata` 74.299,5 J su 240 righe con 77 corrette = **964,929
J/corretta**; `passi_attiva` 69.429,6 J sulle **stesse 240 righe coperte** =
**901,683 J/corretta**, delta **4.869,9 J**, **-6,6%**. La copertura non si muove
(240 contro 240), quindi nessuna riga entra o esce dal conto: e' solo la stessa
energia letta in attivo. Le 102 righe che cadono sui passi hanno **tutte** l'attiva
per passo valida (`senza l'attiva per passo: 0`), e la quota di riposo che la
cascata non sottrae va da 28,1 a 149,7 J per riga, mediana 44,6.
`tutto_attiva` coincide con `passi_attiva` al joule: su questa marca non esiste
una riga la cui finestra totale non sia valida, perche' il package di finestra non
viene mai usato (i rami pubblicati sono solo `totale_attiva` e `somma_passi`).
Il **secondo dislivello e' piccolo**: la finestra totale supera la somma dei suoi
passi di 320,3 J in tutto, lo 0,5% -- quindi i due rami della cascata coprono
praticamente lo stesso tempo, e la differenza fra 964,9 e 901,7 e' la baseline,
non il tempo. All'altro estremo, la definizione che non sottrae nessuna baseline
(`tutto_pkg`) e' 88.509,7 J = 1.149,477 J/corretta (+19,1%): il numero pubblicato
sta in mezzo perche' sottrae la baseline su 138 righe su 240 e non la sottrae sulle
altre 102 -- ed e' esattamente il dislivello che questo script nomina.
Per ramo la correzione non e' uniforme -- inter -13,9%, cond_prob -6,5%,
coherence -3,9%, counterfactual -4,2%, perche' e' li' che il gate ferma piu' righe
-- ma **l'ordine fra rami non cambia** (counterfactual > coherence > inter >
cond_prob sotto entrambe le definizioni): la classifica che si commenta nella tesi
regge, quello che si muove e' il livello.

Il conto, chiuso il 03-11 (sezioni 6-9 dello stesso output). Lo scarto delle 102
righe **e'** riposo, misurato riga per riga: somma di (package - attiva) per passo
= **4.869,9 J**, e baseline x i secondi registrati degli stessi passi = **4.851,5 J**
(baseline 6,480 W dichiarata nelle note di ogni JSON); residuo **+18,33 J, lo 0,38%**,
per riga mediano 0,156 J cioe' **24 ms** di bordo sempre dello stesso segno -- tempo,
non scala, non un secondo contatore. La stessa identita', dove la cascata non e' in
discussione (le 138 righe con la finestra), da' un residuo mediano di 0,078 J: la
formula e' una sola. Il numero in circolazione si riproduce **dall'artefatto
tracciato** senza rieseguire nulla: `risultati_misura/valutazione.json` ha 240 righe,
**0 joule discordanti** sopra 1e-6, 77 `corretta`, e le stesse fonti per ramo
(138 `totale_attiva` + 102 `somma_passi`) -- quindi la correzione di cui sopra si
applica a un numero che la marca ha gia' pubblicato, non a uno prodotto qui. Sul
pilota dev (81 righe, altra baseline dichiarata: 6,901 W) la coppia si ripresenta:
25.517,2 contro 24.551,4 J, delta **965,8 J (+3,8%)** su 22 righe fermate, con
l'identita' che torna a +4,19 J (0,43%) e l'artefatto `valutazione_pilota_dev.json`
riconciliato a zero: il disallineamento non e' un artefatto di una marca.

E la parte che rende il conto utile (sezione 9): una riga che passa dal gate al tool
**non aggiunge i joule dei passi in piu'** -- cambia ramo della cascata, da
`somma_passi` in package a `totale_attiva`, e il ramo nuovo sottrae il riposo. Sulle
mediane di branca (tratto `cau_inference` + `causal_A`, prese dalle 138 righe che
arrivano al tool) la stima per riga convertita vale +129,8 / +146,0 / +167,5 /
+180,8 J di mediana a seconda del ramo **sotto la definizione pubblicata**, contro
+168,0 / +189,5 / +222,1 / +229,8 J sotto `passi_attiva`; se tutte e 102 le righe
fermate convertissero, i due totali si ricongiungono a 89.416,0 J e la differenza fra
i due incrementi e' **esattamente -4.869,9 J**, il riposo delle stesse righe. Per
questo una stima del tipo "(pubblicato + energia aggiuntiva) / (corrette nuove)" --
la forma in cui circola il ~848 J/corretta del regime `stati-alias` -- **e' un limite
superiore**: somma il lavoro nuovo e tiene dentro il riposo che il ramo vecchio non
sottrae. Non e' lo stesso numero di `901,683`, e non va messo nella stessa frase.

Uso:
    MUDILAB_COPIE=1 python verifica_energia.py risultati_misura/b_composta/20261102_191401

Stampa su stdout; l'output della corsa del 03-11 e' tracciato in
`harness/risultati/verifica_energia_20261103.txt`. Non serve Ollama e non serve
la copia della relatrice: si importa `benchmark.valuta`, che carica pyAgrum per
`_confronta` ma non tocca il modello.
"""

import argparse
import collections
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.dont_write_bytecode = True

import benchmark.valuta as V  # noqa: E402


# ------------------------------------------------------------------ i due rami

def _finestra(risultato, campo):
    """(joule o None, motivo) dalla sola finestra totale `risultato["totale"]`.

    Il gate di validita' e' quello di `valuta._energia`: un numero attivo si prende
    solo se `attiva_valida` e', perche' senza baseline calibrata l'attiva e' la
    package meno zero e chiamarla "attiva" sarebbe una parola in piu'.
    """
    tot = risultato.get("totale") or {}
    if not tot:
        return None, "nessuna_finestra"
    valore = tot.get(campo)
    if valore is None:
        return None, f"finestra_senza_{campo}"
    if campo == "energia_attiva_j" and not tot.get("attiva_valida"):
        return None, "attiva_non_valida"
    return float(valore), "finestra"


def _somma(risultato, campo):
    """(joule o None, passi usati, passi scoperti) sommando **un solo** campo.

    `passi scoperti` conta i passi che quel campo non lo portano (o che, per
    l'attiva, hanno `attiva_valida` spenta): non si sommano come zero. Se nessun
    passo e' coperto torna None e la riga esce dalla copertura, come fa
    `valuta._energia` -- un run senza numero energetico non deve entrare nel
    denominatore dei joule.
    """
    somma, usati, scoperti = 0.0, 0, 0
    for s in risultato.get("steps") or []:
        m = s.get("misura") or {}
        valore = m.get(campo)
        if campo == "energia_attiva_j" and not m.get("attiva_valida"):
            valore = None
        if valore is None:
            scoperti += 1
            continue
        somma += float(valore)
        usati += 1
    return (somma if usati else None), usati, scoperti


# --------------------------------------------------------------- le definizioni

DEFINIZIONI = (
    ("pubblicata", "finestra attiva, poi finestra package, poi passi in package"),
    ("passi_attiva", "come sopra, ma il terzo ramo e' in attivo"),
    ("tutto_attiva", "attiva sempre: finestra quando vale, poi i passi"),
    ("tutto_pkg", "package sempre: nessuna baseline sottratta"),
    ("solo_passi_pkg", "ignora la finestra, soma i passi in package"),
    ("solo_passi_attiva", "ignora la finestra, soma i passi in attivo"),
)


def _valore(risultato, definizione):
    """(joule o None, dove) per una delle sei definizioni.

    `dove` nomina il ramo che ha prodotto il numero, cosi' il conteggio per ramo
    si legge senza dedurre nulla dalle cifre.
    """
    if definizione == "pubblicata":
        return V._energia(risultato)
    if definizione == "passi_attiva":
        for etichetta, campo in (("totale_attiva", "energia_attiva_j"),
                                 ("totale_pkg", "energia_pkg_j")):
            j, _ = _finestra(risultato, campo)
            if j is not None:
                return j, etichetta
        j, _, _ = _somma(risultato, "energia_attiva_j")
        if j is not None:
            return j, "somma_passi_attiva"
        j, _, _ = _somma(risultato, "energia_pkg_j")
        return (j, "somma_passi_pkg") if j is not None else (None, "assente")
    if definizione == "tutto_attiva":
        j, _ = _finestra(risultato, "energia_attiva_j")
        if j is not None:
            return j, "totale_attiva"
        j, _, _ = _somma(risultato, "energia_attiva_j")
        return (j, "passi_attiva") if j is not None else (None, "attiva_non_disponibile")
    if definizione == "tutto_pkg":
        j, _ = _finestra(risultato, "energia_pkg_j")
        if j is not None:
            return j, "totale_pkg"
        j, _, _ = _somma(risultato, "energia_pkg_j")
        return (j, "passi_pkg") if j is not None else (None, "assente")
    if definizione in ("solo_passi_pkg", "solo_passi_attiva"):
        campo = "energia_pkg_j" if definizione.endswith("pkg") else "energia_attiva_j"
        j, _, _ = _somma(risultato, campo)
        return (j, "passi") if j is not None else (None, "passi_non_coperti")
    raise ValueError(f"definizione sconosciuta: {definizione!r}")


def _aggrega(risultati, corrette, definizione):
    """(joule totali, righe con un numero, J per corretta) su una definizione.

    Il denominatore e' il numero di risposte **corrette**, non quello delle righe
    coperte: e' la definizione di `valuta.py:308`, e qui si tiene la stessa per non
    confrontare numeri che differiscono perche' uno dei due ha cambiato metrica.
    """
    valori = [v for v in (_valore(r, definizione)[0] for _, r in risultati)
              if v is not None]
    totale = sum(valori)
    per_corretta = (totale / corrette) if corrette and valori else None
    return totale, len(valori), per_corretta


def _delta_passi(risultato):
    """(package, attiva) sommandone i passi, o None se non sono comparabili.

    Restituisce la coppia invece del delta perche' il caso "una delle due manca"
    va contato a parte. `None` anche quando i due conti **coprono passi diversi**:
    una riga fermata a meta' con un solo passo che porta l'attiva darebbe un delta
    costruito su denominatori diversi, e il delta e' esattamente la cosa che questo
    script imputa alla quota di riposo.
    """
    pkg, n_pkg, _ = _somma(risultato, "energia_pkg_j")
    attiva, n_att, _ = _somma(risultato, "energia_attiva_j")
    if pkg is None or attiva is None or n_pkg != n_att:
        return None
    return pkg, attiva


# ------------------------------------------------- la chiusura: che cosa e' lo scarto

BASELINE = re.compile(r"baseline calibrata: ([0-9]+(?:\.[0-9]+)?) W")


def baseline_da_note(risultato):
    """I watt di baseline **dichiarati dalla riga**, o None.

    Li si legge dalla nota che l'harness ha scritto nel JSON (`"baseline calibrata:
    6.480 W"`), non da una ricalcolazione: la grandezza che serve e' quella che il
    run ha **sottratto** per produrre `energia_attiva_j`, e quella e' un numero
    registrato, non una stima che questo script potrebbe rifare in disaccordo.
    """
    for nota in ((risultato.get("misura") or {}).get("note") or []):
        m = BASELINE.search(str(nota))
        if m:
            return float(m.group(1))
    return None


def passi_appaiati(risultato):
    """[(nome, package, attiva, secondi)] sui passi che portano tutte e tre le grandezze.

    I secondi sono quelli registrati per passo (`steps[].seconds`), non una durata
    ricostruita: l'identita' che si vuole provare e' fra tre numeri gia' scritti
    nello stesso oggetto, e sostituirla con un tempo dedotto la renderebbe vera per
    costruzione. Un passo che non ha una delle tre esce **senza contare**, perche'
    un'identita' parziale e' un'identita' falsa. Il nome del passo viaggia con la
    tupla: la sezione 9 deve distinguere i passi che una riga fermata al gate ha
    comunque (translator, classificator) da quelli che il gate taglia, e la
    distinzione si fa per nome, non per posizione ne' per conteggio.
    """
    out = []
    for s in risultato.get("steps") or []:
        m = s.get("misura") or {}
        if not m.get("attiva_valida"):
            continue
        pkg, att, sec = (m.get("energia_pkg_j"), m.get("energia_attiva_j"),
                         s.get("seconds"))
        if pkg is None or att is None or sec is None:
            continue
        out.append((str(s.get("step")), float(pkg), float(att), float(sec)))
    return out


TESTA = ("translator", "classificator")


def riposo(risultato):
    """(scarto misurato, riposo identificato) per una riga, o None se non e' provabile.

    `scarto misurato` e' la somma, sui passi, di (package - attiva): la cifra che la
    cascata pubblicata **non** sottrae sulle righe che ricadono sui passi.
    `riposo identificato` e' baseline_w per la somma dei secondi degli stessi passi:
    la stessa cifra prevista dalla definizione di energia attiva del protocollo
    (E_att = E_pkg - P_base * delta_t, F.1).
    Se i due numeri coincidono a frazione di joule per riga, lo scarto **e'**
    riposo: non una scala sbagliata, non un canale diverso, non un secondo
    contatore. E' il pezzo che mancava alla prima versione di questa verifica, perche'
    la sezione 2 calcolava lo scarto senza nominarne la natura riga per riga.
    """
    p = passi_appaiati(risultato)
    base = baseline_da_note(risultato)
    if not p or base is None:
        return None
    return (sum(x - a for _n, x, a, _t in p), base * sum(t for *_rest, t in p))


def marginali(righe_per_ramo):
    """Mediane per ramo dei numeri che servono a stimare un passaggio di ramo.

    `righe_per_ramo` sono **solo** le righe che arrivano al tool (finestra totale
    presente): una riga fermata non ha il tratto che serve misurare. I numeri:
      `attiva_extra` = mediana( attiva di tutti i passi meno attiva dei passi di
                     testa ) -- quanto costa in attivo il tratto che il gate taglia;
      `riposo_testa` = mediana( (package - attiva) dei soli passi di testa ) -- quanto
                     riposo porta dentro una riga fermata, perche' la cascata la legge
                     in package e non in attivo;
      `finestra_su_passi` = mediana( `totale.energia_attiva_j` / attiva dei suoi passi )
                     -- quanta attivo della finestra totale non e' coperto dai passi:
                     e' il fattore che converte una stima "per passi" nella cifra che
                     la cascata pubblicata leggerebbe dalla finestra.
    Sono mediane, non medie: la coda dei passi `causal_A` lunghi e' lunga, e tre righe
    possono tirare una media per due ordini.
    """
    out = {}
    for ramo, righe in sorted(righe_per_ramo.items()):
        extra, testa, rapporto = [], [], []
        for r in righe:
            pp = passi_appaiati(r)
            if len(pp) < 3:
                continue
            t = [(x, a, s) for (n, x, a, s) in pp if n in TESTA]
            if not t:
                continue
            extra.append(sum(a for _n, _x, a, _s in pp) - sum(a for _x, a, _s in t))
            testa.append(sum(x - a for x, a, _s in t))
            tot = (r.get("totale") or {}).get("energia_attiva_j")
            if tot is not None:
                rapporto.append(float(tot) / sum(a for _n, _x, a, _s in pp))
        if extra:
            out[ramo] = {"attiva_extra": statistics.median(extra),
                         "riposo_testa": statistics.median(testa),
                         "finestra_su_passi": (statistics.median(rapporto)
                                               if rapporto else None),
                         "n": len(extra)}
    return out


def _valutazione_da_artefatto(cartella: Path, variante, nomi=("valutazione.json",
                                                             "valutazione_pilota_dev.json")):
    """Le righe di `valutazione.json` della stessa variante, o None se non c'e'.

    Serve alla sezione 7 (e, per il pilota, alla sezione 8): chiudere il conto vuol
    dire mostrare che il numero in circolazione si riproduce **dall'artefatto
    tracciato**, non solo rieseguendo `valuta.py` sui JSON. Il percorso e' quello
    standard dell'harness (un livello sopra la marca, in `risultati_misura/`), e il
    pilota ha il nome proprio perche' e' una valutazione separata e dichiarata come
    pilota; se manca, la sezione lo dice invece di simulare un accordo.
    """
    for n in nomi:
        for p in (cartella.parent.parent / n, cartella / n):
            if p.is_file():
                dati = json.loads(p.read_text(encoding="utf-8"))
                v = (dati.get("varianti") or {}).get(variante)
                if v:
                    return p, v["righe"]
    return None, None


def _variante(cartella: Path):
    """Il nome della variante **come lo dichiara la marca**, non come e' il cartello.

    L'artefatto di valutazione indicizza per variante; indovinarlo dal nome della
    cartella funzionere' finche' la marca e' in una cartella che si chiama come la
    variante, e poi smettere di funzionare in silenzio. `riepilogo.json` lo scrive,
    quindi si legge li'.
    """
    p = cartella / "riepilogo.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8")).get("variante")
    return cartella.parent.name


def _leggi_marca(cartella: Path):
    """(valutati, righe) di una marca registrata, con le stesse funzioni di `main`.

    Serve alla sezione 8, che deve rifare il conto sul pilota dev: la via piu' corta
    sarebbe un'altra copia del codice di caricamento, e una copia che diverge dalla
    originale e' proprio il difetto che questo script denuncia (un ramo della cascata
    che legge un campo diverso dall'altro). Qui si richiama `V._valuta_run`, la stessa
    funzione, sulla stessa tavola.
    """
    gt = V._gt()
    hash_reti = V._hash_reti()
    righe = V._carica(cartella)
    valutati = [V._valuta_run(r, gt[r["task_id"]], hash_reti) for r in righe]
    return valutati, righe


def main():
    ap = argparse.ArgumentParser(
        description="Le definizioni alternative di _energia sui run registrati")
    ap.add_argument("cartella", help="marca dei risultati (quella con riepilogo.json)")
    ap.add_argument("--split", default=None,
                    help="filtrare il confronto con `valutazione.json` su questo split")
    a = ap.parse_args()

    cartella = Path(a.cartella)
    if not cartella.is_absolute():
        cartella = HERE / cartella

    print("cartella: " + str(cartella))
    print("comando: MUDILAB_COPIE=1 " + sys.executable + " "
          + str(Path(sys.argv[0]).name) + " "
          + " ".join(str(x) for x in sys.argv[1:]))

    valutati, righe = _leggi_marca(cartella)
    risultati = [(f"{r['task_id']}_r{r['ripetizione']}", v.get("risultato") or {})
                 for r, v in zip(valutati, righe)]
    corrette = sum(1 for r in valutati if r["corretta"])

    print(f"righe: {len(righe)}, corrette: {corrette}, "
          f"rami pubblicati: " + str(sorted({r['energia_fonte'] for r in valutati})))

    # 1. le sei definizioni, una sotto l'altra
    print("\n--- joule per corretta sotto ogni definizione")
    base = None
    for nome, descrizione in DEFINIZIONI:
        totale, n, per_corretta = _aggrega(risultati, corrette, nome)
        if base is None:
            base = totale
        scarto = "" if base is None or nome == "pubblicata" or per_corretta is None else \
            "  delta {:+.1f} J  ({:+.1f}%)".format(totale - base,
                                                   100.0 * (totale - base) / base)
        print(f"  {nome:<18} {totale:>12.1f} J  {n:>3}/{len(righe)} righe  "
              f"{(per_corretta if per_corretta is not None else float('nan')):>9.3f} "
              f"J/corretta{scarto}")
        print(f"  {'':<18} {descrizione}")

    # 2. da dove viene lo scarto: le righe che la cascata pubblica porta sui passi
    di_lato = [f"{r['task_id']}_r{r['ripetizione']}" for r in valutati
               if r["energia_fonte"] == "somma_passi"]
    per_nome = dict(risultati)
    coppie = [c for c in (_delta_passi(per_nome[n]) for n in di_lato) if c]
    delta = sum(pkg - attiva for pkg, attiva in coppie)
    print(f"\n--- le righe che cadono sui passi: {len(di_lato)}")
    print(f"  con entrambe le grandezze per passo: {len(coppie)}")
    print(f"  senza l'attiva per passo: {len(di_lato) - len(coppie)}")
    if coppie:
        v = sorted(pkg - attiva for pkg, attiva in coppie)
        print(f"  quota di riposo non sottratta: {delta:.1f} J  "
              f"(min {v[0]:.1f} / mediana {statistics.median(v):.1f} / max {v[-1]:.1f})")

    # 3. l'altro dislivello: la finestra totale copre piu' dei due passi
    con_finestra = [(n, r) for n, r in risultati if (r.get("totale") or {})]
    fuori_pkg, fuori_attiva, non_coppie, passi_pkg = [], [], 0, 0.0
    for n, r in con_finestra:
        coppia = _delta_passi(r)
        tot = r["totale"] or {}
        if coppia is None or tot.get("energia_pkg_j") is None:
            non_coppie += 1
            continue
        fuori_pkg.append(float(tot["energia_pkg_j"]) - coppia[0])
        passi_pkg += coppia[0]
        if tot.get("attiva_valida") and tot.get("energia_attiva_j") is not None:
            fuori_attiva.append(float(tot["energia_attiva_j"]) - coppia[1])
    print(f"\n--- finestra contro passi ({len(con_finestra)} righe con la finestra)")
    print(f"  confrontabili: {len(fuori_pkg)}, non confrontabili: {non_coppie}")
    if fuori_pkg:
        fuori_tot = sum(fuori_pkg)
        print(f"  package fuori dai passi: {fuori_tot:.1f} J, cioe' il "
              f"{100.0 * fuori_tot / passi_pkg:.1f}% del package dei passi "
              f"delle stesse righe")
    if fuori_attiva:
        print(f"  attiva fuori dai passi: {sum(fuori_attiva):.1f} J su "
              f"{len(fuori_attiva)} righe (la finestra e' presa a baseline "
              f"sottratta, i passi pure: qui la differenza e' tempo, non scala)")
    fuori_dichiarato = [(n, r.get("fuori_dai_passi_j")) for n, r in risultati
                        if r.get("fuori_dai_passi_j") is not None]
    print(f"  chiavi `fuori_dai_passi_j` non vuote nei JSON: {len(fuori_dichiarato)}")

    # 4. la cifra citata il 02-11, riprodotta o smentita
    totale_p, n_p, j_p = _aggrega(risultati, corrette, "pubblicata")
    totale_a, n_a, j_a = _aggrega(risultati, corrette, "passi_attiva")
    print("\n--- il conto citato il 02-11, alla prova")
    print(f"  pubblicato:   {totale_p:.1f} J / {corrette} = {j_p:.3f} J/corretta")
    print(f"  passi_attiva: {totale_a:.1f} J / {corrette} = {j_a:.3f} J/corretta")
    print(f"  differenza:   {totale_p - totale_a:.1f} J "
          f"({100.0 * (totale_p - totale_a) / totale_p:+.1f}%)")
    print(f"  copertura: {n_p} righe contro {n_a} (se e' uguale, nessuna riga "
          f"entra o esce dal conto)")
    for ramo in sorted({r["ramo"] for r in valutati}):
        sel = [(n, r) for (n, r), v in zip(risultati, valutati) if v["ramo"] == ramo]
        c = sum(1 for v in valutati if v["ramo"] == ramo and v["corretta"])
        tp, _, jp = _aggrega(sel, c, "pubblicata")
        ta, _, ja = _aggrega(sel, c, "passi_attiva")
        print(f"  {ramo:<14} {c:>2} corrette  {jp:>9.3f} -> {ja:>9.3f} J/corretta"
              f"   ({tp:.1f} -> {ta:.1f} J)")

    # 5. la domanda vera dietro la correzione: cambia qualcosa che si legge?
    print("\n--- l'ordine fra rami, che e' quello che si commenta nella tesi")
    ordini = {}
    for definizione in ("pubblicata", "passi_attiva"):
        righe_per_ramo = {}
        for ramo in sorted({r["ramo"] for r in valutati}):
            sel = [(n, r) for (n, r), v in zip(risultati, valutati) if v["ramo"] == ramo]
            c = sum(1 for v in valutati if v["ramo"] == ramo and v["corretta"])
            righe_per_ramo[ramo] = _aggrega(sel, c, definizione)[2]
        ordini[definizione] = [r for r, _ in sorted(righe_per_ramo.items(),
                                                   key=lambda kv: kv[1], reverse=True)]
    for definizione in ("pubblicata", "passi_attiva"):
        print(f"  dal piu' caro: {definizione:<13} " + " > ".join(ordini[definizione]))
    print("  " + ("l'ordine NON cambia: la correzione sposta i valori, non la classifica"
                  if ordini["pubblicata"] == ordini["passi_attiva"]
                  else "ATTENZIONE: l'ordine fra rami cambia sotto la definizione attiva"))

    # 6. LA CHIUSURA, PRIMO PEZZO: che cosa sono, fisicamente, i 4.869,9 J.
    # La sezione 2 li calcola come somma degli scarti per passo; qui gli scarti
    # vengono confrontati riga per riga con il riposo **previsto** dalla definizione
    # in vigore (baseline_w x i secondi registrati per lo stesso passo). Se collimano
    # a frazione di joule, il disallineamento fra 964,9 e 901,7 non e' una scala, non
    # e' un secondo contatore e non e' tempo coperto male: e' esattamente il riposo
    # che il terzo ramo della cascata non sottrae.
    scarti = []
    for n in di_lato:
        rp = riposo(per_nome[n])
        if rp:
            scarti.append((n, rp[0], rp[1], baseline_da_note(per_nome[n])))
    baseline = sorted({b for *_rest, b in scarti})
    print(f"\n--- che cosa sono i {totale_p - totale_a:.1f} J (riga per riga)")
    print(f"  righe con le tre grandezze per passo e una baseline dichiarata: "
          f"{len(scarti)}/{len(di_lato)}")
    print(f"  baseline dichiarate nelle note distinte: {baseline}"
          f" (il conto e' per riga, non uno solo per la marca)")
    if scarti:
        m = sum(s for _n, s, _i, _b in scarti)
        i = sum(x for _n, _s, x, _b in scarti)
        print(f"  scarto misurato    : {m:9.1f} J   (la cascata pubblicata non sottrae questo)")
        print(f"  riposo identificato: {i:9.1f} J   (baseline x secondi degli stessi passi)")
        print(f"  identita' con la sezione 4: lo scarto misurato qui e la differenza"
              f" fra le due definizioni torna: {abs(m - (totale_p - totale_a)) < 0.05}")
        print(f"  residuo: {m - i:+.2f} J, cioe' il {100.0 * (m - i) / m:+.2f}% "
              f"dello scarto")
        r = sorted((s - x) for _n, s, x, _b in scarti)
        print(f"  residuo per riga: min {r[0]:.3f} / mediana "
              f"{statistics.median(r):.3f} / max {r[-1]:.3f} J")
        ms = [(s - x) / b for _n, s, x, b in scarti if b]
        print(f"  e' tempo, non energia: convertito alla baseline dichiarata da ogni"
              f" riga, il residuo mediano vale "
              f"{1000.0 * statistics.median(ms):.0f} ms di bordo"
              f" fra il tempo del contatore e `steps[].seconds`"
              f" (min {1000.0 * min(ms):.0f} / max {1000.0 * max(ms):.0f} ms)")
        print(f"  il segno e' sempre lo stesso (tutte le righe {r[0] > 0}): il tempo"
              f" registrato per passo e' sistematicamente un po' meno della finestra"
              f" del contatore, che e' la direzione attesa da un bordo di timestamp,"
              f" non da un rumore")
    # la stessa identita' provata dove la cascata NON e' in discussione: le righe con
    # la finestra totale. Se li' il residuo e' dello stesso ordine di grandezza, la
    # formula e' giusta ovunque e lo scarto delle 102 righe e' solo il suo non uso.
    con_fin = [(n, r) for n, r in risultati if (r.get("totale") or {}).get("energia_pkg_j")
               is not None]
    dif_fin = []
    for n, rr in con_fin:
        t = rr["totale"]
        b = baseline_da_note(rr)
        sec = rr.get("seconds_total")
        if None in (b, sec) or not t.get("attiva_valida"):
            continue
        dif_fin.append(float(t["energia_pkg_j"]) - float(t["energia_attiva_j"]) - b * sec)
    if dif_fin:
        print(f"  controllo sulle {len(dif_fin)} righe con finestra (li' la cascata prende"
              f" l'attiva):")
        print(f"    package - attiva - baseline x seconds_total: mediana "
              f"{statistics.median(dif_fin):.3f} J, "
              f"max in valore assoluto {max(dif_fin, key=abs):.3f} J, "
              f"min {min(dif_fin):.3f} J")
        print("    stesso ordine di grandezza del residuo delle 102: la formula e' una,")
        print("    e lo scarto e' il suo non essere applicata a un ramo della cascata.")

    # 7. LA CHIUSURA, SECONDO PEZZO: il numero in circolazione si riproduce
    # dall'artefatto tracciato, riga per riga. Senza questo, la correzione di cui
    # sopra si applicherebbe a un numero che solo questo script sa calcolare: qui si
    # confrontano i **singoli joule** di `valutazione.json` con quelli della cascata
    # riletta sui JSON, e le due bandiere `corretta`.
    variante = _variante(cartella)
    p_art, righe_art = _valutazione_da_artefatto(cartella, variante)
    print("\n--- il conto contro l'artefatto tracciato, riga per riga")
    if righe_art is None:
        print(f"  nessun artefatto di valutazione per la variante {variante!r}: la"
              f" riconciliazione NON e' stata fatta (non e' passata)")
    else:
        if a.split:
            righe_art = [x for x in righe_art if x.get("split") == a.split]
        orfane, diff, disc_corretta, disc_fonte = [], [], [], []
        per_fonte_art, per_fonte_ric = collections.Counter(), collections.Counter()
        tot_art = tot_ric = 0.0
        for x in righe_art:
            chiave = f"{x['task_id']}_r{x['ripetizione']}"
            rr = per_nome.get(chiave)
            if rr is None:
                orfane.append(chiave)
                continue
            j, dove = _valore(rr, "pubblicata")
            per_fonte_art[x["energia_fonte"]] += 1
            per_fonte_ric[dove] += 1
            if j is None or x.get("energia_j") is None:
                diff.append((chiave, j, x.get("energia_j")))
                continue
            tot_art += float(x["energia_j"])
            tot_ric += j
            if abs(float(x["energia_j"]) - j) > 1e-6:
                diff.append((chiave, j, x["energia_j"]))
            if bool(x["corretta"]) != (x["etichetta_ok"] and x["numero_ok"]):
                disc_corretta.append(chiave)
        n_corr_art = sum(1 for x in righe_art if x["corretta"])
        print(f"  artefatto: {p_art}  variante: {variante}  "
              f"righe a confronto: {len(righe_art)}"
              + (f" (split {a.split})" if a.split else ""))
        print(f"  chiavi dell'artefatto senza JSON nella marca: {len(orfane)}"
              + (f" {orfane[:5]}" if orfane else ""))
        print(f"  energia: artefatto {tot_art:.4f} J | ricalcolo {tot_ric:.4f} J | "
              f"differenza {tot_art - tot_ric:+.6f} J")
        print(f"  righe con un joule diverso (sopra 1e-6): {len(diff)}"
              + (f" prime: {diff[:3]}" if diff else ""))
        print(f"  corrette: artefatto {n_corr_art} | ricalcolo {corrette} | "
              f"discordanze etichetta/numero: {len(disc_corretta)}")
        jp_art = (tot_art / n_corr_art) if n_corr_art else None
        print(f"  J/corretta: artefatto {jp_art:.3f} | ricalcolo "
              f"{(tot_ric / corrette) if corrette else float('nan'):.3f}")
        print(f"  fonti d'arte: {dict(per_fonte_art)}")
        print(f"  fonti del ricalcolo: {dict(per_fonte_ric)}")
        print("  -> se le due colonne Joule coincidono, 964,929 non e' un numero di")
        print("     questo script: e' l'artefatto committato, e la correzione della")
        print("     sezione 4 si applica a un numero che la marca ha gia' pubblicato.")

    # 8. LA CHIUSURA, TERZO PEZZO: la stessa correzione sul pilota dev. Se il delta
    # fosse un artefatto della sola marca held-out -- una baseline storta, una rete
    # diversa -- non si ripeterebbe qui, che gira su un altro split, altri 81 run e
    # un'altra baseline dichiarata.
    print("\n--- la stessa coppia di definizioni sul pilota dev")
    marche = sorted((HERE / "risultati_misura_pilota").glob("*/[0-9]*/riepilogo.json"))
    if not marche:
        print("  nessuna marca in risultati_misura_pilota/: sezione saltata, non passata")
    else:
        car_p = marche[-1].parent
        val_p, righe_p = _leggi_marca(car_p)
        ris_p = [(f"{r['task_id']}_r{r['ripetizione']}", v.get("risultato") or {})
                 for r, v in zip(val_p, righe_p)]
        corr_p = sum(1 for x in val_p if x["corretta"])
        tp, np_, jp = _aggrega(ris_p, corr_p, "pubblicata")
        ta, na, ja = _aggrega(ris_p, corr_p, "passi_attiva")
        bas_p = sorted({b for _n, r in ris_p if (b := baseline_da_note(r)) is not None})
        fer = [n for n, _r in ris_p if not ((_r or {}).get("totale") or {})]
        s_p = [rp for _n, r in ris_p if not (r.get("totale") or {})
               if (rp := riposo(r))]
        print(f"  marca: {car_p.name}  righe: {len(righe_p)}  corrette: {corr_p}  "
              f"baseline dichiarate: {bas_p}")
        print(f"  pubblicata   {tp:9.1f} J / {corr_p} = {jp:.3f} J/corretta  "
              f"({np_}/{len(righe_p)} righe coperte)")
        print(f"  passi_attiva {ta:9.1f} J / {corr_p} = {ja:.3f} J/corretta  "
              f"({na}/{len(righe_p)} righe coperte)")
        print(f"  delta: {tp - ta:.1f} J ({100.0 * (tp - ta) / tp:+.1f}%) su "
              f"{len(fer)} righe fermate dal gate")
        if s_p:
            mm = sum(x[0] for x in s_p)
            ii = sum(x[1] for x in s_p)
            print(f"  identita' anche qui: scarto misurato {mm:.1f} J contro riposo "
                  f"previsto {ii:.1f} J, residuo {mm - ii:+.2f} J "
                  f"({100.0 * (mm - ii) / mm:+.2f}%) su {len(s_p)} righe")
        p_art_p, righe_art_p = _valutazione_da_artefatto(car_p, _variante(car_p))
        if righe_art_p:
            tot_art_p = sum(float(x["energia_j"] or 0.0) for x in righe_art_p)
            n_corr_p = sum(1 for x in righe_art_p if x["corretta"])
            print(f"  artefatto del pilota ({p_art_p.name}): {tot_art_p:.1f} J / "
                  f"{n_corr_p} corrette = {tot_art_p / n_corr_p:.3f} J/corretta")
            print(f"  differenza dal ricalcolo: {tot_art_p - tp:+.4f} J, "
                  f"{n_corr_p - corr_p:+d} corrette")
        else:
            print("  nessun artefatto di valutazione per il pilota: il ricalcolo resta"
                  " non riconciliato")

    # 9. LA CHIUSURA, QUARTO PEZZO -- e il pezzo che rende il conto utile: che cosa
    # succede a una riga che passa dal gate al tool. Non "aggiunge i joule dei passi
    # in piu'": cambia **ramo** della cascata, e il ramo nuovo sottrae la baseline.
    print("\n--- una riga che passa il gate non aggiunge energia: cambia ramo")
    per_ramo_tool = collections.defaultdict(list)
    for (_n, r), v in zip(risultati, valutati):
        t = r.get("totale") or {}
        if t.get("attiva_valida") and t.get("energia_attiva_j") is not None:
            per_ramo_tool[v["ramo"]].append(r)
    marg = marginali(per_ramo_tool)
    print(f"  medie di branca **sul tratto che il gate taglia**, prese dalle "
          f"{sum(len(x) for x in per_ramo_tool.values())} righe che arrivano al tool:")
    print(f"  {'ramo':<14} {'n':>4} {'attiva extra':>13} {'riposo testa':>14} "
          f"{'finestra/passi':>15}")
    for ramo, x in sorted(marg.items()):
        print(f"  {ramo:<14} {x['n']:>4} {x['attiva_extra']:>13.1f} J"
              f" {x['riposo_testa']:>14.1f} J"
              f" {(x['finestra_su_passi'] if x['finestra_su_passi'] else float('nan')):>14.3f}")
    stime = []
    ramo_per_nome = {n: v["ramo"] for (n, _r), v in zip(risultati, valutati)}
    for n in di_lato:
        r = per_nome[n]
        x = marg.get(ramo_per_nome[n])
        pp = [t for t in passi_appaiati(r) if t[0] in TESTA]
        vecchia_p = _valore(r, "pubblicata")[0]
        vecchia_a = _valore(r, "passi_attiva")[0]
        if not x or not pp or vecchia_p is None:
            continue
        a_testa = sum(t[2] for t in pp)
        nuova = (a_testa + x["attiva_extra"]) * (x["finestra_su_passi"] or 1.0)
        stime.append((ramo_per_nome[n], vecchia_p, vecchia_a, nuova))
    if stime:
        print(f"  righe fermate con una stima di ramo nuovo: {len(stime)}/{len(di_lato)}")
        print(f"  {'ramo':<14} {'n':>3}  {'delta su pubblicata':>20} "
              f"{'delta su passi_attiva':>22}")
        for ramo in sorted({s[0] for s in stime}):
            sel = [s for s in stime if s[0] == ramo]
            dp = sorted(s[3] - s[1] for s in sel)
            da = sorted(s[3] - s[2] for s in sel)
            print(f"  {ramo:<14} {len(sel):>3}  "
                  f"{statistics.median(dp):>12.1f} J ({dp[0]:+.1f}/{dp[-1]:+.1f})"
                  f"  {statistics.median(da):>11.1f} J ({da[0]:+.1f}/{da[-1]:+.1f})")
        dp = [s[3] - s[1] for s in stime]
        da = [s[3] - s[2] for s in stime]
        print(f"  se TUTTE le {len(stime)} convertissero, a parita' di corrette:")
        print(f"    pubblicata   {totale_p:.1f} J -> {totale_p + sum(dp):.1f} J  "
              f"({sum(dp):+.1f} J, {100.0 * sum(dp) / totale_p:+.1f}%)")
        print(f"    passi_attiva {totale_a:.1f} J -> {totale_a + sum(da):.1f} J  "
              f"({sum(da):+.1f} J, {100.0 * sum(da) / totale_a:+.1f}%)")
        print(f"    i due deltas differiscono di {sum(dp) - sum(da):+.1f} J: ed e' la"
              f" quota di riposo ({sum(s[2] - s[1] for s in stime):+.1f} J) che il ramo"
              f" nuovo sottrae e quello vecchio no")
    print("  Perche' il numero che gira non e' confrontabile: una stima del tipo")
    print("  `(pubblicato + energia aggiuntiva) / (corrette nuove)` tiene il terzo ramo")
    print("  in package -- cioe' si porta dietro il riposo non sottratto delle righe")
    print(f"  fermate (mediana {statistics.median(sorted(pkg - att for pkg, att in coppie)):.1f} J per riga, sezione 2) e aggiunge")
    print("  i joule del tratto nuovo. Sono due correzioni di segno opposto sullo")
    print("  stesso numeratore: quella che circola e' un **limite superiore**, non il")
    print("  J/corretta della stessa variante sotto la definizione pubblicata.")


if __name__ == "__main__":
    main()

