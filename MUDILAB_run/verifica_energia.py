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

Uso:
    MUDILAB_COPIE=1 python verifica_energia.py risultati_misura/b_composta/20261102_191401

Stampa su stdout; l'output della corsa del 03-11 e' tracciato in
`harness/risultati/verifica_energia_20261103.txt`. Non serve Ollama e non serve
la copia della relatrice: si importa `benchmark.valuta`, che carica pyAgrum per
`_confronta` ma non tocca il modello.
"""

import argparse
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


def main():
    ap = argparse.ArgumentParser(description="Le definizioni alternative di _energia sui run registrati")
    ap.add_argument("cartella", help="marca dei risultati (quella con riepilogo.json)")
    a = ap.parse_args()

    cartella = Path(a.cartella)
    if not cartella.is_absolute():
        cartella = HERE / cartella

    print("cartella: " + str(cartella))
    print("comando: MUDILAB_COPIE=1 python verifica_energia.py "
          + " ".join(str(x) for x in sys.argv[1:]))

    gt = V._gt()
    hash_reti = V._hash_reti()
    righe = V._carica(cartella)
    valutati = [V._valuta_run(r, gt[r["task_id"]], hash_reti) for r in righe]
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


if __name__ == "__main__":
    main()

