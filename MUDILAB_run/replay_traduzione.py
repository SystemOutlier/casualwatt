"""Replay offline della verifica di traduzione: cosa cambierebbe una regola, senza modelli.

Perche' esiste. `b_verificata` sull'dev (81 righe, 01-11) raddoppia le risposte
corrette di b_base -- 15 contro 6 -- e pero' fallisce 46 righe su 81 contro le 36
di b_base: la verifica rifiuta piu' righe di quante ne recuperi. Contate su
`harness/risultati/b_verificata/20261101_174518`, 40 refusi su 45 righe con output
leggibile colpiscono la **citazione dell'output**, e fra quelle 20 hanno il target
giusto e 20 ce l'hanno sbagliato: come filtro e' una moneta. Prima di toccare una
regola serve pero' il numero completo, non questa frazione: le 20 righe con il
target giusto non sono 20 risposte corrette in piu', perche' una riga si gioca
anche sull'etichetta e sul numero che il tool stamperebbe.

Cosa fa. Riprende i JSON gia' scritti dallo screening -- testo del traduttore,
etichetta del classificatore, rete -- e riesegue da li' in poi la parte che non
ha bisogno del modello: `traduzione_controllata.valida` con le regole scelte,
`tools.cau_inference` sul dizionario verificato, `_confronta` di genera.py contro
l'oracolo. Niente Ollama, niente calore, niente energia: risponde a "con questa
regola quante righe diventano corrette", non a "quanto costano".

Perche' e' tracciato. Le sue righe di output sono l'evidenza sotto la correzione
della regola `citazione` sull'output: senza questo file quella correzione e'
un'opinione. `confronta` e' la stessa funzione che valuta i run reali, quindi il
replay e il run reale usano lo stesso metro e la stessa tolleranza.

Cosa non fa. Non riclassifica: l'etichetta e' quella che il modello ha scritto nel
run reale, perche' la classificazione e' un passo di modello. Una variante che
cambia il classificatore (`b_esempi`) va schermata davvero, non riproducibile qui.

Uso:  MUDILAB_COPIE=1 python replay_traduzione.py harness/risultati/b_verificata/20261101_174518
      --regole output=obbligatorio|output=se-citata|output=libero|libero+parola-stato|senza-verbatim
      (default: tutte e cinque, a confronto)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

REGIMI = ("output=obbligatorio", "output=se-citata", "output=libero",
          "libero+parola-stato", "senza-verbatim")

# Le due regole alternative, misurate qui e non nel modulo: `valida` chiama
# `_citazione_valida` per nome globale, quindi sostituirla su `TC` per la durata
# del replay basta, e il protocollo in produzione resta quello scritto nei JSON.
# Perche' vale la pena misurarle: sull'dev di `b_composta` (01-11, 18:31) nove
# righe corrette in `b_esempi` vengono rifiutate qui, e il motivo e' sempre
# "citazione non presente nella query". Leggendole una per una si vede che il
# modello riscrive la frase con un soggetto diverso (`the vehicle is an older
# model` contro `the car is an older model`), tenendo pero' la parola dello stato.
# La pretesa che l'intera frase sia un sottostringa della query punisce la
# parafrasi, non l'invenzione; e su CND02 l'invenzione c'e' davvero
# (`Normal` contro `cautious`), quindi la regola nuova va provata su entrambi i
# casi, non solo su quelli che recupera.
#
# `libero+parola-stato`, misurata (01-11, 19:31, cartella 20261101_183106): 16
# corrette contro le 32 di `output=libero` sulle stesse identiche risposte dei
# modelli, e 50 righe rifiutate contro 20. Non e' una rilassatura: sostituisce
# l'intera verifica invece di togliere una clausola, e con lei sparisce il
# fallback sulla variabile -- che e' la via per cui passa quasi ogni citazione,
# perche' un valore come `Total` o `Ransom` nella query non c'e' mai alla lettera.
# Fra le righe che questa regola lascia arrivare al tool una (`INT26`) porta
# `bad allocation`: e' l'incidente dei 26 GB, e la regola in produzione lo stava
# impedendo.
#
# `senza-verbatim`, misurata (01-11, stessa cartella e stessi testi): **40 corrette
# contro le 32** di `output=libero`, con l'ottava in piu' che si chiama
# CND14 CND21 CND26 CND33 CND38 COH01 INT21 INT33 e **nessuna riga buona persa** --
# le otto si aggiungono, non si scambiano, e i rifiuti scendono da 20 a 10. Il
# costo non e' nel conteggio ma nel tipo di errore: su CND02, l'invenzione
# dichiarata (`Normal` contro `cautious`), la regola A rifiuta la riga e la regola
# C la porta al tool, che stampa 0,704 contro lo 0,221 atteso. Con A un'invenzione
# diventa una riga fallita dichiarata; con C diventa una risposta sbagliata
# confidente. INT26 torna a `bad allocation` anche con C. Sono i due numeri che
# decidono la regola, e la regola e' una scelta di protocollo: non viene cambiata
# qui dentro.
#
# Ordine di grandezza per chi legge: 40/81 sarebbe il nuovo massimo su dev, sopra
# `b_composta` (32) e sotto il tetto dell'unione delle cinque varianti (43).
def _regola_parola_stato(TC):
    """La citazione regge se la parola che porta il valore compare nella query."""
    def versione(cit, variabile, valore, query_norm):
        if not isinstance(cit, str) or not cit.strip():
            return "citazione assente o vuota"
        c = TC._norm(cit)
        if not c:
            return "citazione senza parole"
        v = TC._norm(valore)
        if v and v in query_norm:
            return ""
        return "la parola dello stato non compare nella query"
    return versione


def _regola_senza_verbatim(TC):
    """La regola di produzione senza il solo gate sulla frase: vale la parola dello
    stato o quella della variabile, anche se la citazione e' una parafrasi.

    E' la rilassatura che i commenti sopra descrivono come ipotesi, riscritta da
    `_citazione_valida` clausola per clausola: cambia un gate, non l'intera
    verifica. Misurarla era il modo di sapere se le nove righe perse da
    `b_composta` contro `b_esempi` si recuperano senza perdere CND02.
    """
    def versione(cit, variabile, valore, query_norm):
        if not isinstance(cit, str) or not cit.strip():
            return "citazione assente o vuota"
        c = TC._norm(cit)
        if not c:
            return "citazione senza parole"
        if TC._norm(valore) and TC._norm(valore) in c:
            return ""
        if any(w in c for w in TC._parole(variabile)):
            return ""
        return "la citazione non nomina ne' la variabile ne' lo stato"
    return versione


def _regola_alt(TC, regime):
    """(funzione di verifica, `citazione_output`) per un regime del replay.

    I tre regimi di `citazione_output` non toccano `_citazione_valida`; i due che
    la sostituiscono giocano un asse diverso, quello di come si valuta una
    citazione scritta, e per quello `citazione_output` resta `False`.
    """
    if regime == "libero+parola-stato":
        return _regola_parola_stato(TC), False
    if regime == "senza-verbatim":
        return _regola_senza_verbatim(TC), False
    return None, {"output=obbligatorio": True, "output=se-citata": "se-citata",
                  "output=libero": False}[regime]


def _righe(cartella: Path):
    """I run con un testo di traduttore registrato: il materiale del replay.

    Reso come (elaborabili, escluse): una riga senza il passo `translator` non e'
    riproducibile e va contata a parte, perche' il numero in fondo al report dice
    quante righe il metro nuovo ha visto, non quante esistevano.
    """
    elaborabili, escluse = [], []
    for p in sorted(cartella.glob("*_r*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        r = d.get("risultato") or {}
        passi = {s["step"]: s for s in (r.get("steps") or []) if "step" in s}
        if "translator" not in passi or not passi["translator"].get("text"):
            escluse.append(d.get("task_id"))
            continue
        elaborabili.append((d, r, passi, p))
    return elaborabili, escluse


def riproduci(d: dict, r: dict, passi: dict, regime: str, gt: dict, TC, tools, _confronta):
    """(esito, dettaglio) per un regime dato, sullo stesso testo della riga reale."""
    task_id = d["task_id"]
    riga_gt = gt[task_id]
    etichetta = str(r.get("etichetta") or "").strip().lower()
    if not etichetta:
        # lo stesso parser del run, ma dal modulo puro: `run_orchestrato` all'import
        # monta la pipeline di `run_query` e fa chdir nella consegna
        from etichette import etichetta_dal_testo
        etichetta = etichetta_dal_testo(passi["classificator"]["text"])
    rete = d.get("rete") or None

    _alt, regola = _regola_alt(TC, regime)
    traduzione, esito = TC.valida(passi["translator"]["text"], etichetta,
                                  riga_gt["query"], rete, citazione_output=regola)
    if traduzione is None:
        return "rifiutata", esito["motivo"][:60]
    if etichetta != riga_gt["etichetta_attesa"]:
        return "etichetta", f"{etichetta} invece di {riga_gt['etichetta_attesa']}"
    try:
        risposta = tools.cau_inference.func(etichetta, json.dumps(traduzione), rete)
    except Exception as e:
        return "tool", f"{type(e).__name__}: {e}"[:60]
    motivo = _confronta(riga_gt["ramo"], str(risposta), _atteso(riga_gt))
    return ("corretta" if motivo is None else "numero"), (motivo or "")[:60]


def _atteso(gt: dict):
    """La stessa tupla che costruisce valuta.py: probabilita' o estremi."""
    if gt["ramo"] == "counterfactual":
        return {"lower": float(gt["expected_lower"]), "upper": float(gt["expected_upper"]),
                "decisione": ""}
    return {"prob": float(gt["expected_probability"]), "decisione": gt["expected_decision"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella", help="la marca di uno screening, es. harness/risultati/b_verificata/<ts>")
    ap.add_argument("--regole", default=",".join(REGIMI))
    a = ap.parse_args()

    argv = sys.argv
    sys.argv = [argv[0]]                      # run_query legge argv all'import
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools
    import traduzione_controllata as TC
    from benchmark.genera import _confronta
    import csv
    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}

    cartella = (HERE / a.cartella) if not Path(a.cartella).is_absolute() else Path(a.cartella)
    regimi = [x.strip() for x in a.regole.split(",") if x.strip()]
    for x in regimi:
        if x not in REGIMI:
            raise SystemExit(f"regime sconosciuto: {x!r}; validi: {', '.join(REGIMI)}")

    memorizzate, escluse = _righe(cartella)
    print(f"cartella: {cartella.name}")
    print(f"righe con un testo di traduttore: {len(memorizzate)}, "
          f"senza: {len(escluse)}{(' (' + ', '.join(map(str, escluse)) + ')') if escluse else ''}")
    for regime in regimi:
        originale = TC._citazione_valida
        alt, _regola = _regola_alt(TC, regime)
        if alt is not None:
            TC._citazione_valida = alt
        conti = Counter()
        esempio = {}
        for d, r, passi, _p in memorizzate:
            esito, dettaglio = riproduci(d, r, passi, regime, gt, TC, tools, _confronta)
            conti[esito] += 1
            esempio.setdefault(esito, f"{d['task_id']}: {dettaglio}")
        TC._citazione_valida = originale
        n = sum(conti.values())
        print(f"\n--- {regime}: {n} righe riprodotte")
        for esito in ("corretta", "numero", "etichetta", "rifiutata", "tool"):
            if conti[esito]:
                print(f"  {esito:10s} {conti[esito]:3d}   es. {esempio.get(esito, '-')}")
        print(f"  corrette/prodotte = {conti['corretta']}/{n}")


if __name__ == "__main__":
    main()
