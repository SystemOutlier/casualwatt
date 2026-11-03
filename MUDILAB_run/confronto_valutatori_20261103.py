# -*- coding: utf-8 -*-
"""confronto_valutatori_20261103.py -- lo stesso run, valutato due volte.

Perche' esiste. Il ramo GitHub `patch/scientific-evaluator-hardening` aggiunge
`cwEnergyModular/mudilab_adapter.py`: un secondo modo di decidere se una risposta
MUDILAB e' corretta. La misura pubblicata il 02-11 (32/81 dev, 77/240 held-out,
964,929 J/corretta) viene da `benchmark/valuta.py`, che riusa `_confronta` di
`benchmark/genera.py`. Finche' i due criteri non sono applicati agli stessi run
non si sa se misurano la stessa cosa: questo harness li applica entrambi, riga per
riga, ai JSON gia' registrati sul disco, e conta le divergenze per causa.

Cosa fa e cosa non fa. Nessun modello viene invocato e nessuna finestra
energetica viene riletta: i dati sono quelli scritti dall'harness il 02-11
(`--cartelle`, default la misura pubblicata + il pilota dev). L'unica cosa nuova
e' il verdetto. Il codice del ramo si carica da una copia estratta con
`git archive` fuori dal repository (`MUDILAB_RAMPO`), perche' `main` non lo
contiene e il working tree non deve cambiare.

Tre letture del campo `tool_calls`, perche' e' il punto dove i due formati non si
toccano:
  `nessuno`    = quello che il record registrato contiene davvero. Il record non
                 ha `tool_calls`: la chiamata e' dimostrata dal passo
                 `cau_inference` presente in `steps`.
  `passi`      = lo stesso passo tradotto nello schema che l'adapter si aspetta
                 (`[{"name": ..., "success": ...}]`).
  `dizionario` = la forma storica di `MUDILAB_correzioni/run_query.py:188-193`
                 (`{"cau_inference": {"invocazioni": 1, "eccezioni": 0}}`).

Mappa dei campi (dichiarata perche' e' l'unico punto interpretativo del
confronto): `label` e' la stringa che `valuta._etichetta_del_run` usa per
`etichetta_ok`; `translation` e' `risultato.traduzione`, lo stesso oggetto che
`valuta` confronta con `_norm`; `output` e' `risultato.numero`, lo stesso testo
che `genera._confronta` riceve; `energy_j` e' il valore che `valuta._energia`
produce per la riga, non una rimedia.

Output: tabella a stdout, JSON riga-per-riga accanto alle altre analisi
(`harness/risultati/confronto_valutatori_20261103.json`) e testo umano nello
stesso punto con estensione `.txt`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent          # MUDILAB_run/
sys.dont_write_bytecode = True                  # nessuna .pyc nel repo
sys.path.insert(0, str(HERE))

# La copia del ramo, fuori dal repository: `git archive
# origin/patch/scientific-evaluator-hardening cwEnergyModular/<file>` in una
# cartella temporanea. Si passala con la variabile d'ambiente MUDILAB_RAMPO per
# non scrivere nel repo, e si legge **prima** degli import perche' i moduli del
# ramo non sono importabili senza quel percorso in sys.path.
RAMPO = Path(os.environ.get("MUDILAB_RAMPO")
             or r"C:\Users\Massimo\AppData\Local\Temp\ramo_hardened")
sys.path.insert(0, str(RAMPO))

import benchmark.valuta as V                     # noqa: E402  (criterio pubblicato)
import mudilab_adapter as AD                     # noqa: E402  (criterio del ramo)
import evaluation_runner as ER                   # noqa: E402  (riepilogo del ramo)

MISURA = HERE / "risultati_misura" / "b_composta" / "20261102_191401"
PILOTA = HERE / "risultati_misura_pilota" / "b_composta" / "20261102_183844"
OUT_BASE = HERE / "harness" / "risultati" / "confronto_valutatori_20261103"


def tool_calls_none(risultato: dict) -> list:
    """Come il ramo vedrebbe il record se nessuno gli traducesse i passi."""
    return risultato.get("tool_calls") or []


def tool_calls_passi(risultato: dict) -> list:
    """Il passo `cau_inference` tradotto nello schema che l'adapter si aspetta.

    `success` qui vale "il passo c'e' e ha stampato un testo": e' la prova piu'
    forte che il record offre, e viene data per buona per isolare le divergenze
    che non dipendono dal formato del tool.
    """
    out = []
    for passo in risultato.get("steps") or []:
        if passo.get("step") == "cau_inference":
            out.append({"name": "cau_inference",
                        "success": bool(str(passo.get("text") or "").strip())})
    return out


def tool_calls_dizionario(risultato: dict) -> dict:
    """La forma reale registrata da `run_query.py:188-193`: dict, chiavi italiane."""
    inv = sum(1 for p in (risultato.get("steps") or [])
              if p.get("step") == "cau_inference")
    return {"read_graph": {"invocazioni": min(inv, 1), "eccezioni": 0},
            "cau_inference": {"invocazioni": inv, "eccezioni": 0}}


MODI = (("nessuno", tool_calls_none), ("passi", tool_calls_passi),
        ("dizionario", tool_calls_dizionario))


def una_riga(riga: dict, gt: dict, hash_reti: dict) -> dict:
    """Applica i due criteri allo stesso record e tiene entrambi i verdetti."""
    pubblicato = V._valuta_run(riga, gt, hash_reti)
    risultato = riga.get("risultato") or {}
    etichetta, fonte_etichetta = V._etichetta_del_run(risultato)
    caso = AD.load_case(gt)
    # Un verdetto per ogni lettura di tool_calls: la struttura del caso non
    # cambia, cambia solo cosa l'adapter puo' dire dell'esecuzione del tool.
    verdetti = {}
    for nome, estrai in MODI:
        ev = AD.evaluate_case(
            caso,
            label=etichetta,
            translation=risultato.get("traduzione"),
            output=str(risultato.get("numero") or ""),
            tool_calls=estrai(risultato),
            energy_j=pubblicato["energia_j"],
            duration_s=pubblicato["seconds_total"],
        )
        verdetti[nome] = ev.to_dict()
    return {
        "task_id": riga.get("task_id"),
        "ripetizione": riga.get("ripetizione"),
        "ramo": pubblicato["ramo"],
        "split": pubblicato["split"],
        "expected_decision": (gt.get("expected_decision") or "").strip(),
        "testo_output": str(risultato.get("numero") or "")[:400],
        "rete_coerente": pubblicato["rete_coerente"],
        "pubblicato": {
            "corretta": pubblicato["corretta"],
            "etichetta_ok": pubblicato["etichetta_ok"],
            "mappatura_ok": pubblicato["mappatura_ok"],
            "numero_ok": pubblicato["numero_ok"],
            "fonte_etichetta": fonte_etichetta,
            "motivo": pubblicato["motivo"],
            "energia_j": pubblicato["energia_j"],
            "energia_fonte": pubblicato["energia_fonte"],
            "gate_fermato": bool((risultato.get("errore") or "").strip()),
        },
        "rampo": verdetti,
    }


def causa(r: dict, modo: str = "passi") -> str:
    """Prima causa osservabile della divergenza, con i token del ramo nel testo."""
    p, e = r["pubblicato"], r["rampo"][modo]
    if p["corretta"] == (e["end_to_end"] == "correct"):
        return "accordo"
    if p["gate_fermato"]:
        return "gate: pubblicato incorrect, ramo indeterminate (fuori denominatore)"
    note = " ".join(e["notes"])
    if "coherence qualitative decision mismatch" in note:
        return "decision marker: la frase attesa non e' nel vocabolario del dataset"
    if e["output"]["method"] == "interval_not_found":
        return "interval regex: due numeri stampati senza le parole inglesi"
    if e["output"]["method"] in ("number_ambiguous",):
        return "numeri ambigui: il ramo sospende, `_confronta` conta incorrect"
    if e["output"]["method"] == "number_no_answer":
        return "numero non presente per il ramo"
    if e["translation"]["verdict"] == "indeterminate" and p["mappatura_ok"]:
        return "structured: traduzione non letta dal ramo ma accettata da `_norm`"
    if e["translation"]["verdict"] == "incorrect" and p["mappatura_ok"]:
        return "structured: confronto esatto dove `_norm` piega maiuscole e spazi"
    if e["label"]["verdict"] != "correct" and p["etichetta_ok"]:
        return "label: l'etichetta giusta non passa il contratto del ramo"
    if e["output"]["verdict"] != "correct" and p["numero_ok"]:
        return "numero: tolleranza o lettura diverse a TOLL invariato"
    if e["output"]["verdict"] == "correct" and not p["numero_ok"]:
        return "numero: il ramo accetta cio' che l'oracolo respinge"
    if e["tool_call_status"] not in ("success",):
        return f"tool: stato {e['tool_call_status']}"
    return "altra causa"


def somma(righe: list, se_corretta) -> dict:
    """J sommati su tutti i run diviso le corrette: la metrica pubblicata."""
    n = len(righe)
    corrette = sum(1 for r in righe if se_corretta(r))
    energia = sum(r["pubblicato"]["energia_j"] for r in righe
                  if r["pubblicato"]["energia_j"] is not None)
    return {"n": n, "corrette": corrette,
            "precisione": round(corrette / n, 4) if n else None,
            "energia_j": round(energia, 3) if energia else None,
            "j_per_corretta": round(energia / corrette, 3) if corrette and energia else None}


def accordi_per_fase(righe: list, modo: str = "passi") -> dict:
    """Concordenza fase per fase, non solo sul verdetto finale.

    Serve per non attribuire alla decisione qualitativa cio' che e' un_GATE_
    dell'acquisizione: `corretta` del pubblicato e` etichetta AND numero, la
    mappatura` e` diagnostica. Qui si guarda ogni fase contro il suo flag.
    """
    fasi = {"label": "etichetta_ok", "translation": "mappatura_ok", "output": "numero_ok"}
    out = {}
    for fase, flag in fasi.items():
        matrice = Counter()
        for r in righe:
            verdetto = r["rampo"][modo][fase]["verdict"]
            matrice[f"{flag}={r['pubblicato'][flag]} / {verdetto}"] += 1
        out[fase] = dict(sorted(matrice.items()))
    return out


def coerenza_per_decision(righe: list, modo: str = "passi") -> dict:
    """Il verdetto del ramo sulle righe coherence, per `expected_decision` reale.

    E' il test della previsione statica: il dataset congela i valori
    `compatible` e `non_compatibile` (20 + 20 nel dev+held-out), l'adapter
    gestisce gli enum inglesi `strongly_compatible` / `not_strongly_compatible`
    e per ogni altro valore deriva il marker con `replace("_", " ")`. Per
    `non_compatibile` il marker diventa la stringa italiana "non compatibile",
    che non puo' comparire nell'output inglese del ramo.
    """
    out = defaultdict(lambda: defaultdict(int))
    esempi = defaultdict(list)
    for r in righe:
        if r["ramo"] != "coherence":
            continue
        dec = r["expected_decision"] or "<vuoto>"
        e = r["rampo"][modo]
        chiave = f"pubblicato_correct={r['pubblicato']['corretta']} / {e['end_to_end']}"
        out[dec][chiave] += 1
        if len(esempi[dec + "|" + chiave]) < 2:
            esempi[dec + "|" + chiave].append({
                "task_id": r["task_id"], "ripetizione": r["ripetizione"],
                "output": (r.get("testo_output") or "")[:150],
                "note": list(e["notes"]),
                "output_verdict": e["output"]["verdict"],
            })
    return {"distribuzione": {k: dict(v) for k, v in sorted(out.items())},
            "esempi": {k: v for k, v in sorted(esempi.items())}}


def tabella(righe: list) -> list:
    """Incrocio pubblicato x ramo, per split e per ramo, in tutti e tre i modi."""
    out = []
    chiavi = [("*", "*")] + sorted({(r["split"], "*") for r in righe}) + \
             sorted({("*", r["ramo"]) for r in righe})
    for split, ramo in chiavi:
        sub = [r for r in righe
               if (split == "*" or r["split"] == split)
               and (ramo == "*" or r["ramo"] == ramo)]
        if not sub:
            continue
        riga = {"split": split, "ramo": ramo, "n": len(sub),
                "pubblicato": somma(sub, lambda r: r["pubblicato"]["corretta"])}
        for nome, _ in MODI:
            riga[f"ramo_{nome}"] = somma(sub, lambda r, n=nome:
                                         r["rampo"][n]["end_to_end"] == "correct")
            # dove il ramo sospende il giudizio, la riga esce dal denominatore
            det = [r for r in sub if r["rampo"][nome]["end_to_end"] in ("correct", "incorrect")]
            riga[f"ramo_{nome}"]["copertura"] = round(len(det) / len(sub), 4) if sub else None
            riga[f"ramo_{nome}"]["precisione_sui_valutabili"] = (
                round(sum(1 for r in det if r["rampo"][nome]["end_to_end"] == "correct") / len(det), 4)
                if det else None)
        out.append(riga)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Doppio verdetto sugli stessi run")
    ap.add_argument("--cartelle", nargs="*", default=[str(MISURA), str(PILOTA)],
                    help="cartelle di risultati (default: la misura 02-11 + il pilota dev)")
    a = ap.parse_args()

    if not RAMPO.is_dir():
        raise SystemExit(f"cartella del ramo non trovata: {RAMPO} "
                         "(estrarla con `git archive` e passarla con MUDILAB_RAMPO)")
    gt = V._gt()
    hash_reti = V._hash_reti()
    righe = []
    for cartella in a.cartelle:
        c = Path(cartella)
        for riga in V._carica(c):
            g = gt.get(riga.get("task_id"))
            if g is None:
                raise SystemExit(f"{c}: task_id {riga.get('task_id')!r} non nel benchmark")
            righe.append(una_riga(riga, g, hash_reti))

    summary = {"n_righe": len(righe),
               "cartelle": [str(Path(c)) for c in a.cartelle],
               "pubblicato": somma(righe, lambda r: r["pubblicato"]["corretta"])}
    for nome, _ in MODI:
        summary[f"ramo_{nome}"] = somma(righe, lambda r, n=nome:
                                        r["rampo"][n]["end_to_end"] == "correct")
        summary[f"ramo_{nome}"]["cause"] = dict(Counter(causa(r, nome) for r in righe))
        summary[f"ramo_{nome}"]["riepilogo_del_ramo"] = ER.summarize_records(
            [r["rampo"][nome] for r in righe])
    summary["tabella"] = tabella(righe)
    summary["accordi_per_fase_passi"] = accordi_per_fase(righe, "passi")
    summary["coerenza_per_decision_passi"] = coerenza_per_decision(righe, "passi")
    summary["coerenza_per_decision_nessuno"] = coerenza_per_decision(righe, "nessuno")
    summary["gate_comportamento"] = dict(Counter(
        f"gate_fermato={r['pubblicato']['gate_fermato']} / "
        f"{r['rampo']['passi']['end_to_end']}" for r in righe))


    # le righe dove i due criteri non concordano, con i verdetti delle tre fasi
    divergenti = [r for r in righe
                  if r["pubblicato"]["corretta"] != (r["rampo"]["passi"]["end_to_end"] == "correct")]
    summary["n_divergenti_passi"] = len(divergenti)

    OUT_BASE.with_suffix(".json").write_text(
        json.dumps({"summary": summary, "righe": righe}, indent=1, ensure_ascii=False),
        encoding="utf-8")

    linee = [f"confronto valutatori, {len(righe)} run registrati, "
             f"criterio pubblicato vs ramo hardened", ""]
    for chiave in ["pubblicato"] + [f"ramo_{n}" for n, _ in MODI]:
        s = summary[chiave]
        linee.append(f"{chiave:18s} corrette {s['corrette']}/{s['n']} "
                     f"({(s['precisione'] or 0) * 100:.1f}%)  "
                     f"{s['j_per_corretta']} J/corretta")
        for motivo, n in sorted(s.get("cause", {}).items(), key=lambda kv: -kv[1]):
            if n:
                linee.append(f"    {n:4d}  {motivo}")
    linee.append("")
    linee.append("concordenza per fase (modo `passi`):")
    for fase, matrice in summary["accordi_per_fase_passi"].items():
        for chiave, n in matrice.items():
            linee.append(f"  {fase:12s} {chiave:44s} {n:4d}")
    linee.append("righe coherence per `expected_decision` (modo `passi`):")
    for decision, distribuzione in summary["coerenza_per_decision_passi"]["distribuzione"].items():
        for chiave, n in distribuzione.items():
            linee.append(f"  {decision:18s} {chiave:40s} {n:4d}")
    linee.append("righe gate-fermate (modo `passi`):")
    for chiave, n in sorted(summary["gate_comportamento"].items()):
        linee.append(f"  {chiave:52s} {n:4d}")
    esempi = summary["coerenza_per_decision_passi"]["esempi"]
    linee.append("esempi:")
    for chiave, lista in esempi.items():
        for r in lista[:1]:
            linee.append(f"  {chiave} :: {r['task_id']} r{r['ripetizione']} "
                         f"output={r['output']!r} note={r['note']}")
    linee.append("")
    linee.append("per split e ramo (colonna = corrette/n, e copertura del ramo):")
    for t in summary["tabella"]:
        linee.append(f"  {t['split']:9s} {t['ramo']:14s} n={t['n']:4d}  "
                     f"pubblicato {t['pubblicato']['corrette']:4d}/{t['n']:<4d}"
                     f" {t['pubblicato']['j_per_corretta']} J/c  "
                     + "  ".join(f"{n}:{t[f'ramo_{n}']['corrette']:4d}/{t['n']:<4d}"
                                 f"{t[f'ramo_{n}']['j_per_corretta']} J/c"
                                 f"(cov {t[f'ramo_{n}']['copertura']})"
                                 for n, _ in MODI))
    testo = "\n".join(linee) + "\n"
    OUT_BASE.with_suffix(".txt").write_text(testo, encoding="utf-8")
    print(testo)
    print(f"dettaglio riga per riga: {OUT_BASE.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
