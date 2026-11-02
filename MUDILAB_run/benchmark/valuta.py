"""Valuta i risultati dell'harness contro il ground truth del benchmark.

Cosa legge
  benchmark/benchmark.csv     le righe con l'oracolo (scritte da genera.py);
  benchmark/manifest.json     gli hash delle due reti;
  <cartelle>/<variante>/<marca>/  `riepilogo.json` piu' un JSON per run, come
                              li scrive harness/esegui_variante.py.

Cosa misura, per ogni run
  etichetta   il classificatore ha dato l'etichetta del ground truth;
  mappatura   `traduzione` porta esattamente l'input e l'output attesi
              (confronto senza distinzione di maiuscole: dice se il modello ha
              capito, non se il tool accetterebbe la stringa);
  numero      il testo stampato dal ramo contiene gli stessi numeri
              dell'oracolo a TOLL, e per coherence anche la stessa decisione.
              Si riusa `_confronta` di genera.py: se la tolleranza o il
              vocabolario delle risposte cambia, cambia in un posto solo;
  risposta    **corretta = etichetta giusta e numero giusto**. La mappatura e'
              diagnostica: una mappatura giusta con un errore di forma puo'
              comunque produrre il numero sbagliato, e il numero e' cio' che
              l'utente legge.

Energia. La metrica e' **joule per risposta corretta**: si somma l'energia di
tutti i run (anche quelli sbagliati, che l'energia l'hanno comunque spesa) e si
divide per il numero di risposte corrette. Per riga si usa l'energia attiva se
la baseline e' calibrata e la finestra e' valida, altrimenti quella del package,
e la si etichetta (`totale_attiva`, `totale_pkg`, `somma_passi`, `assente`): un
run fallito prima del calcolo non ha una finestra totale, e senza i passi la
copertura scende. Se la copertura non e' 1 il joule per corretta e' un limite
inferiore e va scritto come tale.

Integrita'. Ogni riga dichiara `rete` e `rete_hash`; se l'hash non e' quello del
manifest, la riga ha girato su una rete diversa da quella dell'oracolo e non e'
confrontabile. Si conta in `rete_non_coerente`, non si corregge.
Il confronto ha due livelli, etichettati in `rete_confronto`: `esatto` quando il
digest del run e' proprio quello del manifest, `a-capo` quando lo diventa
normalizzando i fine riga del file attuale **e la normalizzazione restituisce
esattamente il digest del manifest** (vedi `_digest_accettati`: e' il caso di
`core.autocrlf`, che riscrive il .bif all'checkout senza cambiare un byte di
contenuto). Un contenuto diverso non passa a `a-capo`: la normalizzazione non puo'
far tornare un hash che non torna.

Uso:
    python benchmark/valuta.py [cartella ...] [--out percorso.json]
Senza cartelle valuta `harness/risultati` (il default dell'harness).
"""

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

import benchmark as B  # noqa: E402
from benchmark.genera import _confronta  # noqa: E402

CSV_GT = HERE / "benchmark.csv"
MANIFEST = HERE / "manifest.json"
RISULTATI = ROOT / "harness" / "risultati"


def _gt() -> dict:
    with open(CSV_GT, encoding="utf-8-sig", newline="") as f:
        return {r["task_id"]: r for r in csv.DictReader(f)}


def _chiave_rete(percorso) -> str | None:
    """Chiave di confronto per un percorso di rete, o None.

    L'harness registra il percorso **assoluto** risolto (`ROOT / rete`), il
    manifest il percorso relativo: senza normalizzare, la lookup non trova mai
    la chiave e ogni riga risulterebbe incoerente. Su Windows il confronto e'
    case-insensitive per costruzione del filesystem, quindi si abbassa tutto.
    """
    if not percorso:
        return None
    return str(Path(percorso).resolve()).lower()


def _digest_accettati(percorso: Path, sha_manifest: str) -> dict:
    """{digest: modo} che una riga puo' portare per questa rete.

    `esatto` e' il digest registrato al momento della generazione del benchmark,
    preso dal manifest e quindi indipendente da cosa c'e' sul disco adesso.

    `a-capo` si aggiunge **solo** se normalizzare CR+LF in LF i byte del file
    attuale restituisce esattamente il digest del manifest. E' il filtro di
    checkout: su questo host `core.autocrlf` = true (misurato 02-11) e
    `consegna/insurance_grafo.bif` vale 22719 B con 548 LF nell'index git,
    23267 B con 548 coppie CR+LF e zero LF nudi sul disco lavoro; normalizzato
    da 39f9e706..dab4, che e' il digest del manifest. Le due reti sono lo stesso
    grafo: fra il digest del run e quello del manifest c'e' solo il fine riga,
    non una CPT.

    Un contenuto diverso non arriva a `a-capo` -- la normalizzazione non puo' far
    tornare un hash che non torna -- quindi la regola non indebolisce il controllo,
    toglie solo il falso allarme che con `--ripetizioni 3` si porterebbe dietro
    meta' delle righe dell'held-out.
    """
    accettati = {sha_manifest: "esatto"}
    try:
        byte = Path(percorso).read_bytes()
    except OSError:
        return accettati
    digest_disk = hashlib.sha256(byte).hexdigest()
    normale = hashlib.sha256(byte.replace(b"\r\n", b"\n")).hexdigest()
    if normale == sha_manifest and digest_disk not in accettati:
        accettati[digest_disk] = "a-capo"
    return accettati


def _hash_reti() -> dict:
    """Chiave di percorso -> {digest accettati: etichetta del confronto}."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {_chiave_rete(ROOT / v["percorso"]):
            _digest_accettati(ROOT / v["percorso"], v["sha256"])
            for v in m["reti"].values()}


def _confronto_rete(riga: dict, hash_reti: dict) -> tuple:
    """(coerente, modo) per una riga: None se la riga non dichiara la rete.

    `modo` vale `esatto`, `a-capo` o `incoerente`, e dice *quale* dei due
    controlli e' passato. Serve perche' il totale `rete_non_coerente` da solo
    non distingue una rete cambiata da un checkout, e la prima cosa e' da
    scartare, la seconda no.
    """
    percorso = riga.get("rete")
    if not percorso:
        return None, "non dichiarata"
    accettati = hash_reti.get(_chiave_rete(percorso))
    if accettati is None:
        return False, "rete non nel manifest"
    modo = accettati.get(riga.get("rete_hash"))
    return (True, modo) if modo else (False, "incoerente")


def _norm(d):
    """Dizionario normalizzato per il confronto, o None se non e' un dizionario."""
    if not isinstance(d, dict):
        return None
    return {str(k).strip(): str(v).strip().lower() for k, v in d.items()}


def _energia(risultato):
    """(joule, fonte). La finestra totale vince; i passi coprono i run falliti."""
    tot = risultato.get("totale") or {}
    if tot:
        attiva = tot.get("energia_attiva_j")
        if tot.get("attiva_valida") and attiva is not None:
            return float(attiva), "totale_attiva"
        if tot.get("energia_pkg_j") is not None:
            return float(tot["energia_pkg_j"]), "totale_pkg"
    somma, visto = 0.0, False
    for s in risultato.get("steps") or []:
        m = s.get("misura") or {}
        if m.get("energia_pkg_j") is not None:
            somma += float(m["energia_pkg_j"])
            visto = True
    if visto:
        return somma, "somma_passi"
    return None, "assente"


def _atteso_colonne(gt: dict):
    ramo = gt["ramo"]
    inp = gt["intervention_json"] if ramo in ("inter", "counterfactual") else gt["evidence_json"]
    if ramo == "counterfactual":
        atteso = {"lower": float(gt["expected_lower"]),
                  "upper": float(gt["expected_upper"]),
                  "decisione": ""}
    else:
        atteso = {"prob": float(gt["expected_probability"]),
                  "decisione": gt["expected_decision"]}
    return json.loads(inp), {gt["target_variable"]: gt["target_state"]}, atteso


def _valuta_run(riga: dict, gt: dict, hash_reti: dict) -> dict:
    """Un run: i quattro esiti, l'energia, il motivo se qualcosa non torna."""
    risultato = riga.get("risultato") or {}
    etichetta = str(risultato.get("etichetta", "")).strip().lower()
    atteso_in, atteso_out, atteso_num = _atteso_colonne(gt)

    traduzione = risultato.get("traduzione")
    mappa_ok = (isinstance(traduzione, dict)
                and _norm(traduzione.get("input")) == _norm(atteso_in)
                and _norm(traduzione.get("output")) == _norm(atteso_out))

    numero = risultato.get("numero")
    if numero is None:
        numero_ok, motivo = False, risultato.get("errore") or "nessun numero"
    else:
        m = _confronta(gt["ramo"], str(numero), atteso_num)
        numero_ok, motivo = m is None, m or ""
    if not (etichetta == gt["etichetta_attesa"]) and not motivo:
        motivo = f"etichetta {etichetta!r} invece di {gt['etichetta_attesa']!r}"

    energia, fonte = _energia(risultato)
    rete_ok, rete_modo = _confronto_rete(riga, hash_reti)
    return {
        "variante": riga.get("variante"),
        "task_id": riga.get("task_id"),
        "ripetizione": riga.get("ripetizione"),
        "ramo": gt["ramo"],
        "split": gt["split"],
        "rete": gt["rete"],
        "etichetta_ok": etichetta == gt["etichetta_attesa"],
        "mappatura_ok": mappa_ok,
        "numero_ok": numero_ok,
        "corretta": (etichetta == gt["etichetta_attesa"]) and numero_ok,
        "motivo": motivo,
        "energia_j": energia,
        "energia_fonte": fonte,
        "rete_coerente": rete_ok,
        "rete_confronto": rete_modo,
        "seconds_total": risultato.get("seconds_total"),
    }


def _cartelle(percorsi) -> list:
    """Le cartelle <variante>/<marca>: accetta sia il padre sia le foglie."""
    out = []
    for p in percorsi:
        p = Path(p)
        if not p.exists():
            raise SystemExit(f"cartella non trovata: {p}")
        for r in sorted(p.rglob("riepilogo.json")):
            out.append(r.parent)
    if not out:
        raise SystemExit(f"nessun riepilogo.json sotto {', '.join(map(str, percorsi))}")
    return out


def _carica(cartella: Path) -> list:
    riepilogo = json.loads((cartella / "riepilogo.json").read_text(encoding="utf-8"))
    righe = []
    for esito in riepilogo.get("esiti", []):
        percorso = cartella / esito["file"]
        righe.append(json.loads(percorso.read_text(encoding="utf-8")))
    return righe


def _aggregato(righe: list) -> dict:
    n = len(righe)
    corrette = sum(1 for r in righe if r["corretta"])
    energia = sum(r["energia_j"] for r in righe if r["energia_j"] is not None)
    con_energia = sum(1 for r in righe if r["energia_j"] is not None)
    return {
        "n": n,
        "corrette": corrette,
        "precisione": (corrette / n) if n else None,
        "etichetta_ok": sum(1 for r in righe if r["etichetta_ok"]),
        "mappatura_ok": sum(1 for r in righe if r["mappatura_ok"]),
        "numero_ok": sum(1 for r in righe if r["numero_ok"]),
        "energia_j": round(energia, 6) if con_energia else None,
        "copertura_energia": (con_energia / n) if n else None,
        # joule per risposta corretta: l'energia spesa dalle risposte sbagliate
        # resta nel numeratore, altrimenti un metodo che sbaglia sembra cheap
        "j_per_corretta": round(energia / corrette, 3) if corrette and con_energia else None,
        "rete_non_coerente": sum(1 for r in righe if r["rete_coerente"] is False),
        "rete_solo_a_capi": sum(1 for r in righe if r.get("rete_confronto") == "a-capo"),
    }


def _stampa(tabella: list) -> None:
    nan = float("nan")
    larghezze = (10, 14, 9, 5, 5, 7, 9, 9, 6)
    intestazioni = ("variante", "ramo", "split", "n", "corr", "prec", "J", "J/corr", "cop")
    print("  ".join(f"{h:>{w}s}" for h, w in zip(intestazioni, larghezze)))
    for t in tabella:
        valori = (
            str(t["variante"])[:10],
            t["ramo"],
            t["split"],
            f"{t['n']}",
            f"{t['corrette']}",
            f"{nan if t['precisione'] is None else t['precisione']:.3f}",
            f"{nan if t['energia_j'] is None else t['energia_j']:.1f}",
            f"{nan if t['j_per_corretta'] is None else t['j_per_corretta']:.3f}",
            f"{nan if t['copertura_energia'] is None else t['copertura_energia']:.3f}",
        )
        print("  ".join(f"{v:>{w}s}" for v, w in zip(valori, larghezze)))


def main() -> int:
    ap = argparse.ArgumentParser(description="Valuta i risultati dell'harness sul benchmark")
    ap.add_argument("cartelle", nargs="*", help="cartelle dei risultati (default: harness/risultati)")
    ap.add_argument("--out", help="dove scrivere il JSON (default: accanto ai risultati)")
    a = ap.parse_args()

    gt = _gt()
    hash_reti = _hash_reti()
    cartelle = _cartelle(a.cartelle or [RISULTATI])

    per_variante, run_valutati = defaultdict(list), []
    for c in cartelle:
        righe = _carica(c)
        valutati = []
        for riga in righe:
            g = gt.get(riga.get("task_id"))
            if g is None:
                raise SystemExit(
                    f"{c}: task_id {riga.get('task_id')!r} non e' nel benchmark; "
                    "benchmark.csv e risultati vengono da due generazioni diverse")
            valutati.append(_valuta_run(riga, g, hash_reti))
        per_variante[valutati[0]["variante"]].extend(valutati)
        run_valutati.extend(valutati)

    tabella, dettaglio = [], {}
    for variante, righe in sorted(per_variante.items()):
        per_ramo = {r: [x for x in righe if x["ramo"] == r] for r in sorted({x["ramo"] for x in righe})}
        per_split = {s: [x for x in righe if x["split"] == s] for s in sorted({x["split"] for x in righe})}
        per_rete = {k: [x for x in righe if x["rete"] == k] for k in sorted({x["rete"] for x in righe})}
        # con n ripetizioni i valori si riportano uno per uno: a n = 3 una
        # deviazione standard non e' una stima, ed e' una funzione deterministica
        # della terna (P4.12)
        per_rip = {k: [x for x in righe if x["ripetizione"] == k]
                   for k in sorted({x["ripetizione"] for x in righe})}
        dettaglio[variante] = {
            "totale": _aggregato(righe),
            "per_ramo": {k: _aggregato(v) for k, v in per_ramo.items()},
            "per_split": {k: _aggregato(v) for k, v in per_split.items()},
            "per_rete": {k: _aggregato(v) for k, v in per_rete.items()},
            "per_ripetizione": {k: _aggregato(v) for k, v in per_rip.items()},
            "righe": righe,
        }
        for ramo, v in per_ramo.items():
            tabella.append({"variante": variante, "ramo": ramo, "split": "*", **_aggregato(v)})
        for split, v in per_split.items():
            tabella.append({"variante": variante, "ramo": "*", "split": split, **_aggregato(v)})
        tabella.append({"variante": variante, "ramo": "*", "split": "*", **_aggregato(righe)})

    _stampa(tabella)

    for variante, d in dettaglio.items():
        t = d["totale"]
        print(f"\n{variante}: {t['corrette']}/{t['n']} corrette "
              f"({(t['precisione'] or 0) * 100:.1f}%), "
              f"{t['j_per_corretta']} J per corretta, copertura energia "
              f"{(t['copertura_energia'] or 0) * 100:.1f}%")
        if t["rete_non_coerente"]:
            print(f"  ATTENZIONE: {t['rete_non_coerente']} run su una rete diversa da quella dell'oracolo")
        if t["rete_solo_a_capi"]:
            print("  note: " + str(t["rete_solo_a_capi"]) +
                  " run con la rete coerente solo normalizzando i fine riga"
                  " (filtro di checkout, contenuto = digest del manifest)")
        if t["copertura_energia"] != 1:
            print("  joule per corretta = limite inferiore (mancano finestre energetiche)")
        rip = d["per_ripetizione"]
        if len(rip) > 1:
            print("  per ripetizione (valori, non deviazione standard):")
            j_per_corr = []
            for k, v in rip.items():
                print(f"    r{k}: {v['corrette']}/{v['n']} corrette"
                      f"  {v['energia_j']} J  {v['j_per_corretta']} J/corretta")
                if v["j_per_corretta"] is not None:
                    j_per_corr.append(v["j_per_corretta"])
            if len(j_per_corr) > 1:
                print(f"    J/corretta min/mediana/max: {min(j_per_corr):.3f} / "
                      f"{statistics.median(j_per_corr):.3f} / {max(j_per_corr):.3f}")
        fallite = [r for r in d["righe"] if not r["corretta"]]
        for r in fallite[:10]:
            print(f"  KO {r['task_id']} r{r['ripetizione']}: etichetta_ok={r['etichetta_ok']} "
                  f"mappatura_ok={r['mappatura_ok']} numero_ok={r['numero_ok']} :: {r['motivo'][:100]}")

    out = Path(a.out) if a.out else (cartelle[0].parent / "valutazione.json")
    out.write_text(json.dumps(
        {"soglia_toll": B.TOLL, "varianti": dettaglio, "tabella": tabella},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nscritto: {out}")
    return 0 if run_valutati else 1


if __name__ == "__main__":
    raise SystemExit(main())
