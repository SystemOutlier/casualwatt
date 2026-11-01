"""Esegue una variante su una query o su un benchmark, con la misura condivisa.

Perche' esiste. Il confronto fra implementazioni vale solo se l'harness e' lo
stesso: stessa finestra energetica, stessi bordi scartati, stessa calibrazione,
stesso ordine. Se ogni variante avesse il suo runner, una differenza di joule
potrebbe essere del runner e non della variante. Qui il runner e' uno e la
variante e' un parametro.

Regole di esecuzione (non negoziabili per la misura):
  - **una variante per processo, mai due in parallelo**: l'energia e' del package
    CPU e un secondo processo la sporcano;
  - riscaldamento e primo run si pagano **una volta per batch**, fuori dalla
    finestra: il caricamento dell'8B costa ~2150 J e la cache dei prompt fredda
    39 s contro 1,3 s, quindi il primo run di una configurazione si scarta;
  - la baseline si calibra una volta per batch (~90 s, tre finestre da 30 s di
    P1.3); senza --calibra-idle la riga dichiara `idle_provenance=uncalibrated`
    e riporta la sola energia grezza del package;
  - un solo event loop per tutto il batch: il client httpx resta legato al primo
    loop e un secondo asyncio.run fallisce con "Event loop is closed".

Nessun fallback silenzioso: un'eccezione della variante finisce nel JSON della
query con il suo testo, e il batch prosegue. Il riepilogo conta i falliti.

Uso:
    python harness/esegui_variante.py --variante b_base --query "<testo>"
    python harness/esegui_variante.py --variante b_vincolata --benchmark percorso.csv
                                      [--ripetizioni 3] [--calibra-idle]
                                      [--senza-misura] [--riscalda-modelli]
                                      [--scarta-primo-run] [--out cartella]

Il CSV del benchmark deve avere almeno le colonne `task_id` e `query`.
Le metriche e il dataset stanno in benchmark/ (non ancora generato).
"""

import argparse
import asyncio
import csv
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))

import benchmark as BENCH  # noqa: E402  (colonne e costanti congelate)


def _argomenti():
    ap = argparse.ArgumentParser(description="Esegue una variante di orchestrazione MUDILAB")
    ap.add_argument("--variante", help="nome registrato in varianti/REGISTRO")
    ap.add_argument("--elenco", action="store_true", help="elenca le varianti registrate")
    ap.add_argument("--query", help="una sola query, come testo")
    ap.add_argument("--benchmark", help="CSV con colonne task_id e query")
    ap.add_argument("--split", help="esegue solo le righe con questo valore in `split` "
                                    "(dev, held-out): la scelta si fa sullo sviluppo")
    ap.add_argument("--ripetizioni", type=int, default=1)
    ap.add_argument("--out", default=str(HERE / "risultati"))
    ap.add_argument("--orig", help="cartella dei file originali (inoltrata a run_query)")
    ap.add_argument("--senza-misura", action="store_true")
    ap.add_argument("--calibra-idle", action="store_true")
    ap.add_argument("--riscalda-modelli", action="store_true")
    ap.add_argument("--scarta-primo-run", action="store_true")
    return ap.parse_args()


def _query(a) -> list:
    """Le righe da eseguire: (task_id, query, rete). Una sola fonte per volta.

    `rete` e' il percorso della rete bayesiana da dare al tool, relativo a
    MUDILAB_run/ e risolto qui in percorso assoluto: la CWD dopo l'import di
    run_query finisce in consegna/, quindi un percorso relativo letto da
    cau_inference punterebbe a un altro file. Assente = la rete di default.
    """
    if bool(a.query) == bool(a.benchmark):
        raise SystemExit("indica --query oppure --benchmark, non entrambi e non nessuno")
    if a.query:
        return [("q1", a.query, None)]
    with open(a.benchmark, encoding="utf-8-sig", newline="") as f:
        righe = list(csv.DictReader(f))
    if not righe or not set(BENCH.COLONNE_HARNESS) <= set(righe[0]):
        raise SystemExit(f"{a.benchmark}: servono le colonne {BENCH.COLONNE_HARNESS}")
    if a.split:
        # il filtro non crea un file derivato: lo split e' una colonna del CSV
        # congelato, e un secondo CSV a mano sarebbe una seconda verita'
        righe = [r for r in righe if (r.get("split") or "").strip() == a.split]
        if not righe:
            raise SystemExit(f"{a.benchmark}: nessuna riga con split={a.split!r}")
    out = []
    for r in righe:
        rete = (r.get("rete") or "").strip() or None
        if rete:
            p = (ROOT / rete).resolve()
            if not p.exists():
                raise SystemExit(f"{r['task_id']}: rete dichiarata non trovata: {p}")
            rete = str(p)
        out.append((r["task_id"], r["query"], rete))
    return out


def _hash_rete(rete: str | None) -> str | None:
    """SHA-256 della rete usata per la riga: l'oracolo e il tool devono leggere
    lo stesso file, e questo lo si puo' dichiarare solo con un hash."""
    if not rete:
        return None
    return hashlib.sha256(Path(rete).read_bytes()).hexdigest()


async def _batch(mod, righe, a, provenienza, cartella):
    ro = mod.ro
    misura = ro.Misura(not a.senza_misura, a.calibra_idle)
    misura.avvia()
    esiti = []
    try:
        if a.riscalda_modelli:
            await ro.riscalda_modelli(misura)
        if a.scarta_primo_run and righe:
            # stesso evento loop, senza misura: copre caricamento e cache dei
            # prompt. Il risultato non si usa e non entra nel riepilogo.
            caldo = ro.Misura(False, False)
            caldo.avvia()
            try:
                await mod.run(righe[0][1], caldo, path_rete=righe[0][2])
            except Exception as e:
                misura.note.append(f"primo run scartato, fallito: {type(e).__name__}: {e}")
            finally:
                caldo.chiudi()
            misura.note.append("primo run scartato (caricamento e cache dei prompt)")

        for k in range(a.ripetizioni):
            for task_id, query, rete in righe:
                t0 = time.perf_counter()
                try:
                    risultato = await mod.run(query, misura, path_rete=rete)
                    errore = risultato.get("errore", "")
                except Exception as e:
                    risultato, errore = {}, f"{type(e).__name__}: {e}"
                riga = {
                    "variante": mod.NOME,
                    "descrizione": mod.DESCRIZIONE,
                    "cambia_rispetto_a_b_base": mod.CAMBIA,
                    "task_id": task_id,
                    "ripetizione": k + 1,
                    "rete": rete,
                    "rete_hash": _hash_rete(rete),
                    "provenienza": provenienza,
                    "errore_variante": errore,
                    "risultato": risultato,
                }
                nome = f"{task_id}_r{k + 1}.json"
                (cartella / nome).write_text(
                    json.dumps(riga, indent=2, ensure_ascii=False), encoding="utf-8")
                esiti.append({
                    "task_id": task_id,
                    "ripetizione": k + 1,
                    "file": nome,
                    "secondi": round(time.perf_counter() - t0, 3),
                    "etichetta": risultato.get("etichetta"),
                    "errore": errore,
                })
                stato = "ok" if not errore else f"ERRORE: {errore}"
                print(f"[{mod.NOME}] {task_id} r{k + 1}: {stato}", flush=True)
    finally:
        misura.chiudi()

    falliti = sum(1 for e in esiti if e["errore"])
    riepilogo = {
        "variante": mod.NOME,
        "modello": getattr(mod.ro.rq, "ACTIVE_MODEL", None),
        "modello_spiegazione": getattr(mod.ro, "MODELLO_SPIEGAZIONE", None),
        "provenienza": provenienza,
        "opzioni_harness": {
            "ripetizioni": a.ripetizioni,
            "misura": not a.senza_misura,
            "calibra_idle": a.calibra_idle,
            "riscalda_modelli": a.riscalda_modelli,
            "scarta_primo_run": a.scarta_primo_run,
        },
        "misura": misura.riepilogo(),
        "n_query": len(righe),
        "n_run": len(esiti),
        "n_falliti": falliti,
        "esiti": esiti,
    }
    (cartella / "riepilogo.json").write_text(
        json.dumps(riepilogo, indent=2, ensure_ascii=False), encoding="utf-8")
    return riepilogo


def main() -> int:
    a = _argomenti()
    import varianti

    if a.elenco or not a.variante:
        for nome in sorted(varianti.REGISTRO):
            print(nome)
        return 0

    righe = _query(a)
    # run_orchestrato e run_query leggono sys.argv all'import: gli si lascia solo
    # --orig, i flag di misura li gestisce questo harness.
    sys.argv = [sys.argv[0]] + (["--orig", a.orig] if a.orig else [])
    mod = varianti.carica(a.variante)
    provenienza = varianti.provenienza(a.variante)

    marca = time.strftime("%Y%m%d_%H%M%S")
    cartella = Path(a.out) / a.variante / marca
    cartella.mkdir(parents=True, exist_ok=True)

    riepilogo = asyncio.run(_batch(mod, righe, a, provenienza, cartella))
    print(json.dumps({k: riepilogo[k] for k in
                      ("variante", "n_query", "n_run", "n_falliti")}, ensure_ascii=False))
    print(f"risultati: {cartella}")
    return 1 if riepilogo["n_falliti"] else 0


if __name__ == "__main__":
    raise SystemExit(main())