"""Sonda della perdita di memoria: quale passo della via B la produce.

Perche' esiste. Il run misurato del 01-11 su held-out (b_solo_numero) si e'
fermato alla riga 111 su 240: il processo python aveva 19.979 MB di working set
su 31,7 GB di macchina, 145 MB liberi e 26.287 page fault/s imputati al solo
processo (tre valori letti da Get-CimInstance alle 17:30 circa). Un processo che
cresce ~180 MB per riga non finisce 240 righe, e dopo qualche decina il numero
che produce non e' piu' una misura: il tempo a muro e' paging, non inferenza.

Tre rami, uno per parte di una riga. `--core` ripete la parte deterministica
(caricamento del grafo e `cau_inference`) senza toccare nessun modello;
`--energia` ripete la catena di misura di una riga (bordi del contatore e
finestre profilate) senza toccare ne' il grafo ne' il linguaggio; `--agenti`
misura il passo di modello, smontato in due prove perche' una delle due non
costa niente: la sola costruzione del client, poi la chiamata reale.

Nessun fallback silenzioso. La sonda non libera nulla durante i rami;
`gc.collect()` gira una volta alla fine di ciascuno e il suo effetto e' stampato
come numero separato, non sommato alla crescita.

Nessuna pretesa assoluta. `--energia` gira senza calibrazione della baseline
(`settle_idle` + `calibrate_idle` sono tre finestre da 30 s): la baseline non
calibrata cambia i joule, non le allocazioni, e questo ramo guarda le
allocazioni.

Cosa ha risposto, il 01-11. `--core 20` = 20 `loadBN` + 80 `cau_inference`:
+1 MB totale. `--energia 20` = 20 righe di soli bordi e finestre profilate:
+3 MB, e piatto dal bordo 5 (3 MB sono il sampler che si avvia). `--agenti 10`:
costruzione del client +0 MB, 10 `Agent.run` reali +4 MB (+0,4 MB per run).
`--run 10` con la variante intera e la misura attiva: +6 MB, 0 MB per riga,
thread e note lineari. Nessuna delle quattro prove reproduce i ~180 MB per riga
che il run aveva a 111 righe, e le righe su disco non c'entrano: 4,5 KB l'una,
908 KB in tutto. Restano non spiegati dal codice della pipeline, e i due fatti
esterni osservati nello stesso minuto restano: due pull di modelli da ~5 GB nel
log di Ollama e la RAM libera a 145 MB. La conclusione onesta e' che il run non
si puo' ripetere confidando nella sola pipeline: serve il preflight di
`harness/preflight_misura.py`, che quelle due condizioni le verifica prima.

Uso:  MUDILAB_COPIE=1 python sonda_perdita_memoria.py --core 20
      MUDILAB_COPIE=1 python sonda_perdita_memoria.py --energia 20
      MUDILAB_COPIE=1 python sonda_perdita_memoria.py --agenti 10
      MUDILAB_COPIE=1 python sonda_perdita_memoria.py --run 10
      (un ramo per volta: `--core` carica run_query e `--run` lo ricaricherebbe)
"""

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))


def rss_mb() -> float:
    """Resident set del processo, in MB."""
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1e6


def ramo_core(righe: int, rete: str) -> None:
    """Grafo e inferenza, nessun modello."""
    import tools
    import pyagrum as gum

    base = rss_mb()
    print(f"[core] baseline dopo gli import: {base:.0f} MB")

    for i in range(righe):
        gum.loadBN(rete)
        if (i + 1) % 10 == 0:
            print(f"[core] {i + 1:3d} loadBN: {rss_mb() - base:+8.0f} MB")
    del gum
    gc.collect()
    print(f"[core] dopo gc.collect(): {rss_mb() - base:+8.0f} MB")

    # una mappatura valida per ramo, con nodi e stati presi dal BIF
    Casi = {
        "backward_reasoning": {"input": {"DrivQuality": "Normal"},
                               "output": {"MedCost": "Million"}},
        "intervention": {"input": {"DrivQuality": "Normal"},
                         "output": {"MedCost": "Million"}},
        "coherence": {"input": {"MedCost": "Million"},
                      "output": {"DrivQuality": "Normal"}},
        "influence": {"input": {"DrivQuality": "Normal"},
                      "output": {"MedCost": "Million"}},
    }
    for etichetta, features in Casi.items():
        prima = rss_mb()
        for _ in range(righe):
            tools.cau_inference.func(etichetta, json.dumps(features), rete)
        dopo = rss_mb()
        print(f"[core] {etichetta:20s}: {dopo - prima:+7.0f} MB "
              f"({(dopo - prima) / righe:+6.1f} MB/chiamata)")
    gc.collect()
    print(f"[core] totale, dopo gc.collect(): {rss_mb() - base:+.0f} MB")


def ramo_energia(righe: int) -> None:
    """La catena di misura di una riga: bordi del contatore e finestre profilate.

    Ripete `run_orchestrato.Misura` cosi' com'e' nel run, per non misurare una
    cosa diversa da quella che ha mangiato 20 GB: una riga = un bordo totale,
    quattro finestre di passo e una finestra totale.
    """
    sys.argv = [sys.argv[0]]          # i flag del run non devono essere letti
    import run_orchestrato as ro

    base = rss_mb()
    print(f"[energia] baseline prima di SESSION: {base:.0f} MB")
    misura = ro.Misura(attiva=True, calibra=False)
    misura.avvia()
    print(f"[energia] dopo avvia: {rss_mb() - base:+.0f} MB | "
          f"disponibile={misura.disponibile} | note={misura.note}")
    if not misura.disponibile:
        raise SystemExit(f"[energia] la misura non gira: {misura.errore}")

    for i in range(righe):
        e_tot0 = misura.bordo()
        t_tot0 = time.perf_counter()
        time.sleep(0.30)
        for _ in range(4):                       # i quattro passi di una riga
            e0 = misura.bordo()
            t0 = time.perf_counter()
            time.sleep(0.10)
            e1 = misura.bordo()
            misura.riga(t0, time.perf_counter(), e0, e1)
        e_tot1 = misura.bordo()
        misura.riga(t_tot0, time.perf_counter(), e_tot0, e_tot1)
        if (i + 1) % 5 == 0:
            print(f"[energia] {i + 1:3d} righe: {rss_mb() - base:+8.0f} MB")
    gc.collect()
    print(f"[energia] dopo gc.collect(): {rss_mb() - base:+.0f} MB")
    misura.chiudi()


def ramo_agenti(righe: int) -> None:
    """Il passo di modello, smontato in due.

    A) costruzione del client, nessuna richiesta di rete. Se la crescita esce
       qui, il leak e' l'oggetto client (pool httpx/pydantic mai chiuso) e non
       c'entra la risposta del modello.
    B) `Agent.run` sul traduttore delle copie, cioe' la chiamata reale. Gira con
       la query piu' corta possibile perche' qui si guarda la memoria, non il
       contenuto: il costo e' ~1 s di modello per ripetizione.
    """
    import asyncio

    import run_query as rq
    import agents
    from agent_framework.openai import OpenAIChatCompletionClient

    base = rss_mb()
    print(f"[agenti] baseline: {base:.0f} MB | modello {rq.ACTIVE_MODEL}")

    prima = rss_mb()
    for _ in range(righe):
        OpenAIChatCompletionClient(
            model=rq.ACTIVE_MODEL,
            base_url=os.environ.get("MUDILAB_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.environ.get("MUDILAB_API_KEY", "ollama"))
    dopo = rss_mb()
    print(f"[agenti] A) {righe} costruzioni di client: {dopo - prima:+7.0f} MB "
          f"({(dopo - prima) / righe:+6.1f} MB/costruzione)")
    gc.collect()
    print(f"[agenti] A) dopo gc.collect(): {rss_mb() - prima:+7.0f} MB")

    async def una():
        return await agents.translator_senza_tool.run(
            "Create a dictionary following your instruction of the query:"
            "Is the car worth a million dollars?", options={"temperature": 0.0})

    async def ripetizioni():
        """Un solo loop per tutte le N chiamate.

        `asyncio.run` ad ogni iterazione chiude il loop e il client httpx che ci
        fu costruito sopra resta vivo ma legato a un loop morto: misurerebbe un
        errore, non una crescita ('Event loop is closed', osservato).
        """
        prima = rss_mb()
        for i in range(righe):
            await una()
            if (i + 1) % 5 == 0:
                print(f"[agenti] B) {i + 1:3d} run del traduttore: "
                      f"{rss_mb() - prima:+7.0f} MB")
        return rss_mb() - prima

    crescita = asyncio.run(ripetizioni())
    print(f"[agenti] B) {righe} run: {crescita:+7.0f} MB "
          f"({crescita / righe:+6.1f} MB/run)")
    gc.collect()
    print(f"[agenti] B) dopo gc.collect(): {rss_mb() - base:+7.0f} MB")


def ramo_run(righe: int, variante: str, scarta: bool) -> None:
    """La riga intera, come la fa l'harness: un Misura, un loop, N `mod.run`.

    E' il ramo che i tre sopra non coprono: la composizione. Se la crescita
    compare qui e non nei rami separati, il problema sta in cio' che una riga
    tiene fra un passo e l'altro (note, steps, agenti) e non in un passo solo.

    `--scarta` aggiunge l'unico pezzo dell'harness che i rami precedenti non
    toccano: `--scarta-primo-run` apre un secondo `Misura` sulla `SESSION`
    globale e lo chiude, cioe' chiama `SESSION.close()` mentre la misura vera ha
    gia' il suo bordo preso. Se dopo la chiusura ricomparissero righe con energia
    e i thread o la memoria crescessero ad ogni bordo, la causa e' un
    riavvio del campionatore, non una perdita di oggetti della pipeline.
    """
    import asyncio
    import threading

    # i flag del run misurato, per non misurare una configurazione diversa:
    # misura attiva e riscaldamento per riga, calibrazione no (90 s)
    sys.argv = [sys.argv[0], "--riscalda-modelli"]
    from varianti import carica, core

    ro = core()
    mod = carica(variante)
    misura = ro.Misura(True, False)
    misura.avvia()
    base = rss_mb()
    print(f"[run] {variante}: baseline {base:.0f} MB | "
          f"disponibile={misura.disponibile} | note={misura.note}")

    if scarta:
        caldo = ro.Misura(False, False)
        caldo.avvia()
        await_none = asyncio.run(mod.run("ok", caldo)) if False else None
        del await_none
        misura.note.append("sonda: secondo Misura chiuso come fa l'harness")
        misura.chiudi()          # chiude la SESSION globale
        misura.avvia()           # e la riapre al primo bordo della prima riga
        base = rss_mb()

    query = ("Given that the driving quality is normal, how likely is it that "
             "the age of the driver is senior?")

    async def cicla():
        for i in range(righe):
            prima = rss_mb()
            await mod.run(query, misura)
            print(f"[run] riga {i + 1:3d}: {rss_mb() - prima:+7.0f} MB "
                  f"(totale {rss_mb() - base:+7.0f} MB, "
                  f"thread {threading.active_count()}, note {len(misura.note)})")

    asyncio.run(cicla())
    gc.collect()
    print(f"[run] dopo gc.collect(): {rss_mb() - base:+.0f} MB "
          f"| thread {threading.active_count()}")
    misura.chiudi()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", type=int, default=0, metavar="N",
                    help="N caricamenti del grafo e N inferenze per ramo")
    ap.add_argument("--energia", type=int, default=0, metavar="N",
                    help="N ripetizioni della catena di misura di una riga")
    ap.add_argument("--agenti", type=int, default=0, metavar="N",
                    help="N costruzioni di client e N run reali del traduttore")
    ap.add_argument("--run", type=int, default=0, metavar="N",
                    help="N righe intere della variante, con la misura attiva")
    ap.add_argument("--variante", default="b_solo_numero",
                    help="variante per --run (default: quella del run fermato)")
    ap.add_argument("--rete", default=None, help="BIF, default: quello delle copie")
    a = ap.parse_args()
    if not (a.core or a.energia or a.agenti or a.run):
        ap.print_help()
        raise SystemExit(2)

    if a.core:
        # run_query installa `tools`/`agents` sulle copie di MUDILAB_COPIE. Va
        # qui, non prima del ramo energia: run_orchestrato carica run_query da
        # solo e un secondo caricamento rieseguirebbe l'iniezione dei client.
        import run_query  # noqa: F401
        import tools
        # assoluto adesso: run_query cambia la CWD nella cartella delle copie
        rete = str(Path(a.rete).resolve()) if a.rete else str(tools.GRAPH_PATH)
        print(f"rete: {rete}")
        ramo_core(a.core, rete)
    if a.energia:
        ramo_energia(a.energia)
    if a.agenti:
        ramo_agenti(a.agenti)
    if a.run:
        ramo_run(a.run, a.variante)


if __name__ == "__main__":
    main()
