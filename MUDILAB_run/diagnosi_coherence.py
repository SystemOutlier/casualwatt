"""Perche' il ramo coherence perde: chi confronta cosa, riga per riga.

Serve perche' il conteggio dei motivi del replay (`--motivi`) dice gia' che forma
ha la perdita, e la forma non e' quella che ci si aspettava: sui 240 run del 02-11
il ramo `coherence` ferma 42 righe su 60, ma **27 di quelle 42 passano il gate**,
ricevono un numero dal tool, e quel numero non e' quello dell'oracolo. Solo 15 si
fermano a una regola. Una "regola di forma per il traduttore" -- l'idea con cui
questo ramo era stato messo in lista -- non ha niente da agganciare su 27 righe
che il traduttore lo hanno gia' superato, e la decisione va presa su questo, non
sull'idea.

Quindi qui si confronta l'insieme di evidenza che il gate ha lasciato passare con
quello che l'oracolo della riga si aspetta (`evidence_json` di
`benchmark/benchmark.csv`), e si incrocia con la **rete** su cui la riga gira:
meta' della marca `b_composta` sta su `insurance_grafo_perturbato.bif`, e li' un
numero giusto su una rete sbagliata e' un numero sbagliato per costruzione. Le
classi sono sei e si aiutano a vicenda:

  - `target sbagliato`      la variabile in `output` non e' quella dell'oracolo: e'
                          lo scambio, e prima di questa classe le tre righe di COH03
                          stavano in `insieme identico` perche' l'evidenza era giusta
                          e il target no -- il difetto contato come sintomo;
  - `insieme identico`    le evidenze coincidono nome e stato, il target pure, e il
                          numero no: o la rete, o lo stato del target, e va detto
                          quale;
  - `manca` / `in piu'`   l'insieme non coincide: qui il gate non puo' niente,
                          perche' le variabili citate sono genuine nella query;
  - `stato diverso`       la variabile c'e' ma lo stato no: e' il caso che una
                          regola potrebbe agganciare;
  - `target fra le evidenze`, e `decisione` per le righe il cui numero torna ma
                          il verdetto no (soglia 0.60 nel testo della risposta).

Nessun modello, nessuna scrittura: legge i JSON registrati e `valida` con le
impostazioni della marca (`citazione_output=False`, il default della variante
composta). Non adotta niente: e' la misura che decide se la regola ha un soggetto.

Il conto, uscito il 03-11 sulla marca del 02-11
(`harness/risultati/diagnosi_coherence_20261103.txt`): dei 27 run che arrivano al tool
con il numero sbagliato, **24 stanno in `target sbagliato`** -- otto task per tre
ripetizioni: COH03, COH07, COH11, COH12, COH15, COH27, COH28, COH36 -- e **3 in
`manca`**, tutti COH35, dove l'evidenza che non c'e' e' `RuggedAuto`. Le due classi
sono esaustive: nessuna riga e' `insieme identico`, nessuna `stato diverso`, nessuna
`target fra le evidenze`. Quindi la perdita del ramo non e' il numero approssimato o
la rete sbagliata -- e' la domanda sbagliata, e `in piu'`/`manca` da soli non
spiegherebbero perche' il 90% delle righe ha un output che l'oracolo non chiede.

Uso:
    MUDILAB_COPIE=1 python diagnosi_coherence.py risultati_misura/b_composta/20261102_191401
"""

import argparse
import collections
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _classifica(evid_modello: dict, gt: dict, target_modello: dict | None = None):
    """(classe, dettaglio) fra l'insieme lasciato dal gate e quello dell'oracolo.

    `target_modello` e` {variabile: stato}` com'e' uscito dal gate: senza di esso la
    classe `insieme identico` era una menzogna parziale, perche' le tre righe di COH03
    hanno l'evidenza giusta e il **target** sbagliato, e qui sopra erano contate come
    "evidenza uguale, numero diverso" -- che e' il sintomo, non il difetto.
    """
    atteso = json.loads(gt["evidence_json"] or "{}")
    in_piu = sorted(set(evid_modello) - set(atteso))
    manc = sorted(set(atteso) - set(evid_modello))
    diversi = sorted(v for v in set(atteso) & set(evid_modello)
                     if str(atteso[v]) != str(evid_modello[v]))
    if target_modello and gt["target_variable"] not in target_modello:
        return ("target sbagliato",
                f"{sorted(target_modello)} invece di {gt['target_variable']}"
                f"={gt['target_state']}")
    if gt["target_variable"] in evid_modello:
        return "target fra le evidenze", f"{gt['target_variable']} e' anche evidenza"
    if manc:
        return "manca", ", ".join(manc)
    if in_piu:
        return "in piu'", ", ".join(in_piu)
    if diversi:
        return "stato diverso", ", ".join(f"{v}: {evid_modello[v]!r} vs {atteso[v]!r}"
                                          for v in diversi)
    return "insieme identico", f"{len(atteso)} evidenze"


def _rete(path):
    """`base` o `perturbata` dal percorso della rete registrata nella riga.

    Serve perche' meta' della marca gira su una rete con le CPT cambiate: li' un
    numero corretto sulla rete sbagliato e' un numero sbagliato per costruzione,
    e senza questa colonna la classe `insieme identico` sarebbe incomprensibile.
    """
    return "perturbata" if path and "perturbat" in str(path) else "base"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cartella")
    a = ap.parse_args()

    argv = sys.argv
    sys.argv = [argv[0]]                      # run_query legge argv all'import
    import run_query  # noqa: F401  installa `tools`/`agents` sulle copie
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools
    import traduzione_controllata as TC
    from benchmark.genera import _confronta
    from replay_traduzione import _atteso, _chiave, _righe

    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    cartella = (HERE / a.cartella) if not Path(a.cartella).is_absolute() else Path(a.cartella)
    memorizzate, escluse = _righe(cartella)

    classi = collections.Counter()
    per_classe = collections.defaultdict(list)
    rifiutate = collections.Counter()
    rete_conti = collections.Counter()
    esiti = collections.Counter()

    for d, r, passi, _p in memorizzate:
        riga = gt[d["task_id"]]
        if riga["ramo"] != "coherence":
            continue
        rete = d.get("rete") or None
        rete_conti[_rete(rete)] += 1
        etichetta = str(r.get("etichetta") or "").strip().lower()
        if not etichetta:
            from etichette import etichetta_dal_testo
            etichetta = etichetta_dal_testo(passi["classificator"]["text"])
        traduzione, esito = TC.valida(passi["translator"]["text"], etichetta,
                                      riga["query"], rete, citazione_output=False)
        if traduzione is None:
            esiti["rifiutata"] += 1
            rifiutate[_chiave(esito["motivo"][:80])] += 1
            continue
        if etichetta != riga["etichetta_attesa"]:
            esiti["etichetta"] += 1
            continue
        try:
            risposta = tools.cau_inference.func(etichetta, json.dumps(traduzione), rete)
        except Exception as e:
            esiti["tool"] += 1
            continue
        motivo = _confronta("coherence", str(risposta), _atteso(riga))
        esiti["corretta" if motivo is None else "numero"] += 1
        if motivo is None:
            continue
        # la classe parla dell'insieme di evidenza, che e' cio' che il gate lascia
        # passare; il `motivo` resta accanto, perche' "numero diverso" e "verdetto
        # sbagliato" sono due perdite diverse con la stessa evidenza
        classe, dettaglio = _classifica(esito["evidenze"], riga, esito["target"])
        chiave = (classe, "decisione" if "decisione" in motivo else "valore")
        classi[chiave] += 1
        per_classe[chiave].append(f"{d['task_id']} [{_rete(rete)}] {dettaglio} | "
                                  f"{motivo[:60]}")

    n = sum(esiti.values())
    print(f"cartella: {cartella.name}")
    print("comando: MUDILAB_COPIE=1 "
          f"{sys.executable} {Path(__file__).name} {a.cartella}")
    print(f"righe `coherence`: {n}, senza testo di traduttore: {len(escluse)}")
    print(f"rete: " + ", ".join(f"{k} {v}" for k, v in rete_conti.items()))
    print("esiti: " + ", ".join(f"{k} {v}" for k, v in esiti.most_common()))
    print("\n--- per classe (insieme di evidenza x cosa non torna):")
    for (classe, cosa), q in classi.most_common():
        print(f"  {q:3d}  {classe:22s} {cosa}")
        # le tre ripetizioni dello stesso task scrivono la stessa identica riga: le
        # si conta accanto invece di stamparle tre volte, cosi' l'elenco resta corto
        # e **completo** -- tagliarlo a sei, come faceva prima, lasciava la classe
        # dominante con i task non nominati, e un elenco di task e' l'unica cosa che
        # rende verificabile il numero che gli sta sopra
        for riga_txt, q_righe in sorted(collections.Counter(
                per_classe[(classe, cosa)]).items()):
            print(f"         {riga_txt}" + (f"  x{q_righe}" if q_righe > 1 else ""))
    print("\n--- le rifiutate, per regola:")
    for chiave, q in rifiutate.most_common():
        print(f"  {q:3d}  {chiave}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
