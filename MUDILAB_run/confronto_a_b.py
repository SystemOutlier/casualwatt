"""Le due varianti sullo stesso run: (a) modello che chiama il tool, (b) codice che chiama cau_inference.

Cosa misura
-----------
La stessa query, lo stesso modello, lo stesso processo, le stesse copie
corrette (MUDILAB_COPIE=1), la stessa finestra energetica. Cambia solo chi
esegue il calcolo:

  (a) `run_query.run`  - la pipeline originale: traduttore con i tool,
      classificatore, poi l'esperto causale che sceglie quale tool chiamare e
      con quali argomenti (agents.py:44 dichiara tools=[read_graph], :67
      tools=[read_graph, cau_inference]).
  (b) `run_orchestrato.run` - traduttore e classificatore senza tool, il codice
      legge il dizionario e l'etichetta e chiama `cau_inference`; all'esperto
      causale resta la sola spiegazione.

Perche' un solo processo
------------------------
Misure precedenti hanno mostrato che un secondo `asyncio.run` fallisce ("Event
loop is closed": il client httpx resta legato al primo loop). Le due varianti
stanno quindi nello stesso event loop, sugli stessi oggetti agente e sullo
stesso client: cambia il percorso, non l'ambiente.

Perche' a interleaving
----------------------
A e B alternati (A B A B A B) e non in blocco: la deriva della macchina nel
tempo colpisce un blocco in modo asimmetrico, l'alternanza la distribuisce su
entrambe le varianti. Il primo run di ogni variante e' di riscaldamento e non
si usa: paga il caricamento del modello (77,5 s e 2644,5 J a freddo contro
494 J a caldo, misurato) e la cache fredda dei prompt di Ollama (1346 token di
prompt: 39 s a freddo contro 1,3 s a caldo).

Cosa resta diverso fra le due varianti, e va dichiarato
-------------------------------------------------------
- temperatura: (b) gira a 0 (run_orchestrato.OPZIONI), (a) con il valore
  predefinito di Ollama perche' run_query.py non passa opzioni. E' il
  comportamento della pipeline originale, non una scelta di questa misura.
- (a) puo' fallire: se il modello chiama un tool inesistente o passa argomenti
  sbagliati, `tool_ok` e' falso e il numero nella risposta e' inventato. In quel
  caso i joule si contano lo stesso: sono il costo di un run senza risultato.

La finestra energetica e' quella del package CPU (cwEnergyModular, catena
EMI -> PawnIO -> unavailable). La baseline e' calibrata su tre finestre da 30 s
(P1.3) perche' senza baseline `energia_attiva_j` non e' valida; si riportano
entrambe, package e attiva, e i joule totali della finestra.

Uso:
    python confronto_a_b.py [--ripetizioni 3] [--modello llama3.2:3b]
                            [--senza-calibrazione] [--query "..."]

Scrive confronto_a_b_<data>.json accanto a se' e stampa la tabella.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

QUERY = ("Given that the driving quality is normal, how likely is it that the "
         "age of the driver is senior?")

# Il riferimento per questa query sul grafo: 0.2117 (Age=Senior dato
# DrivQuality=Normal). Serve solo a dire se una risposta e' quella giusta.
RIFERIMENTO = 0.212


def _prepara_ambiente(modello: str) -> None:
    os.environ["MUDILAB_COPIE"] = "1"
    os.environ["MUDILAB_MODEL"] = modello


def _azzera_contatori(agenti) -> None:
    """I contatori dei tool sono cumulativi: senza azzerarli un run senza
    chiamate erediterebbe il `tool_ok` del precedente."""
    for nome in ("read_graph", "cau_inference"):
        oggetto = getattr(agenti, nome, None)
        for campo in ("invocation_count", "invocation_exception_count"):
            if oggetto is not None and hasattr(oggetto, campo):
                setattr(oggetto, campo, 0)


def _numero_dal_testo(testo: str) -> list:
    """I numeri fra 0 e 1 nel testo, per vedere se la risposta e' quella giusta."""
    import re

    trovati = []
    for blocco in re.findall(r"\d+\.\d+|\b[01]\b", testo or ""):
        try:
            v = float(blocco)
        except ValueError:
            continue
        if 0.0 <= v <= 1.0:
            trovati.append(v)
    return trovati


def _valido(variante: str, riga: dict) -> bool:
    """Il risultato e' quello richiesto?

    Per (a): il tool e' stato chiamato senza eccezioni e la risposta contiene
    0.212. Per (b): il classificatore ha scelto `backward_reasoning` (la query
    chiede P(Age=Senior | DrivQuality=Normal), non una compatibilita' di
    evidenza) e il numero stampato e' 0.212. La tolleranza e' 5e-4 perche' il
    ramo backward_reasoning arrotonda a tre decimali.
    """
    if variante == "a":
        return bool(riga.get("tool_ok")) and any(
            abs(v - RIFERIMENTO) < 5e-4 for v in riga.get("numeri_nel_testo") or [])
    return riga.get("etichetta") == "backward_reasoning" and any(
        abs(v - RIFERIMENTO) < 5e-4
        for v in _numero_dal_testo(str(riga.get("numero"))))


def _numero_o_none(valore):
    """`cau_inference` non risponde sempre con un numero: sul ramo coherence
    restituisce una frase con dentro la probabilita' dell'evidenza. Un valore
    non numerico non e' un risultato della query, e va tenuto distinto."""
    try:
        return float(valore)
    except (TypeError, ValueError):
        return None


async def _misura_una(variante: str, task: str, misura, rq, ro) -> dict:
    _azzera_contatori(rq.mudilab_agents)
    rq.ERRORI_TOOL.clear()
    e0 = misura.bordo()
    t0 = time.perf_counter()
    esito = {}
    try:
        if variante == "a":
            esito = await rq.run(task)
        else:
            esito = await ro.run(task, misura)
    except Exception as e:
        esito = {"errore": f"{type(e).__name__}: {e}"}
    t1 = time.perf_counter()
    e1 = misura.bordo()
    riga = {"variante": variante, "secondi": round(t1 - t0, 3)}
    riga.update(misura.riga(t0, t1, e0, e1))
    if variante == "a":
        riga["tool_ok"] = esito.get("tool_ok")
        riga["tool_calls"] = esito.get("tool_calls")
        riga["errore_tool"] = esito.get("errore_tool")
        testo = (esito.get("steps") or [{}])[-1].get("text", "")
        riga["numeri_nel_testo"] = _numero_dal_testo(testo)
    else:
        riga["etichetta"] = esito.get("etichetta")
        riga["traduzione"] = esito.get("traduzione")
        riga["numero"] = str(esito.get("numero")) if "numero" in esito else None
        riga["numero_numerico"] = _numero_o_none(riga["numero"])
        riga["numeri_nel_testo"] = _numero_dal_testo(riga["numero"] or "")
    riga["errore"] = esito.get("errore")
    riga["atteso_trovato"] = _valido(variante, riga)
    return riga


def _stampa(righe: list) -> None:
    print()
    print(f"{'#':<3}{'variante':<10}{'s':>7}{'J pkg':>10}{'J active':>10}"
          f"{'W':>7}  {'valido':<7}esito")
    print("-" * 92)
    for i, r in enumerate(righe, 1):
        j = r.get("energia_pkg_j")
        a = r.get("energia_attiva_j")
        w = (j / r["secondi"]) if j and r["secondi"] else None
        valido = "si" if r.get("atteso_trovato") else "no"
        extra = ""
        if r["variante"] == "a":
            extra = f"tool_ok={r.get('tool_ok')} {r.get('numeri_nel_testo')}"
            if r.get("errore_tool"):
                extra += f" errore={list(r['errore_tool'].values())[0][:60]}"
        else:
            extra = (f"etichetta={r.get('etichetta')} "
                     f"numero={str(r.get('numero'))[:50]}")
        if r.get("errore"):
            extra += f" errore={r['errore'][:80]}"
        print(f"{i:<3}{r['variante']:<10}{r['secondi']:>7.2f}"
              f"{(f'{j:.1f}' if j is not None else '-'):>10}"
              f"{(f'{a:.1f}' if a is not None else '-'):>10}"
              f"{(f'{w:.1f}' if w else '-'):>7}  {valido:<7}{extra}")
    print("-" * 92)
    for v in ("a", "b"):
        gruppo = [r for r in righe if r["variante"] == v]
        if not gruppo:
            continue
        j = [r["energia_pkg_j"] for r in gruppo if r.get("energia_pkg_j") is not None]
        s = [r["secondi"] for r in gruppo]
        ok = sum(1 for r in gruppo if r.get("atteso_trovato"))
        print(f"({v}) run misurati {len(gruppo)}   validi {ok}/{len(gruppo)}   "
              f"secondi mediani {sorted(s)[len(s) // 2]:.2f}   "
              f"joule mediani {(sorted(j)[len(j) // 2] if j else float('nan')):.1f}")


async def _esegui(ripetizioni: int, calibra: bool, task: str) -> dict:
    # run_orchestrato legge i flag di misura da sys.argv al momento dell'import:
    # qui gli argomenti di questo script non devono finirci dentro.
    sys.argv = [sys.argv[0]]
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_orchestrato",
                                                  HERE / "run_orchestrato.py")
    ro = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = ro
    spec.loader.exec_module(ro)
    rq = ro.rq

    misura = ro.Misura(True, calibra)
    misura.avvia()
    if not misura.disponibile:
        raise SystemExit(f"misura non disponibile: {misura.errore}")

    righe = []
    try:
        # riscaldamento: uno per variante, scartati (caricamento + cache fredda)
        for v in ("a", "b"):
            r = await _misura_una(v, task, misura, rq, ro)
            r["riscaldamento"] = True
            print(f"riscaldamento ({v}): {r['secondi']:.1f} s, "
                  f"{r.get('energia_pkg_j')} J, valido={r.get('atteso_trovato')}",
                  flush=True)
        # alternanza: A B A B ...
        for rip in range(ripetizioni):
            for v in ("a", "b"):
                r = await _misura_una(v, task, misura, rq, ro)
                r["ripetizione"] = rip + 1
                righe.append(r)
                print(f"run {len(righe)} ({v}): {r['secondi']:.1f} s, "
                      f"{r.get('energia_pkg_j')} J, valido={r.get('atteso_trovato')}",
                      flush=True)
    finally:
        misura.chiudi()

    return {
        "query": task,
        "modello": rq.ACTIVE_MODEL,
        "source": rq.SOURCE,
        "riferimento": RIFERIMENTO,
        "ripetizioni": ripetizioni,
        "calibrazione": calibra,
        "temperatura": {"a": "predefinita di Ollama", "b": 0.0},
        "misura_note": misura.riepilogo(),
        "run": righe,
    }


def _rivaluta(percorso: Path) -> int:
    """Ricalcola `atteso_trovato` dai campi grezzi gia' salvati.

    I numeri (testo finale per (a), `numero` per (b)) e l'etichetta stanno nel
    JSON, quindi la regola di validita' si puo' riapplicare senza rifare i run:
    cambia il verdetto, non il dato. La prima versione di questo script
    convertiva `numero` con float(), e sul ramo backward_reasoning — che
    risponde con una frase — ogni run (b) risultava non valido.
    """
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    for r in dati["run"]:
        r["atteso_trovato"] = _valido(r["variante"], r)
    dati["rivalutazione"] = {
        "quando": time.strftime("%Y-%m-%d %H:%M"),
        "regola": "(a) tool_ok e 0.212 nel testo; (b) etichetta backward_reasoning "
                  "e 0.212 nel numero; tolleranza 5e-4",
    }
    percorso.write_text(json.dumps(dati, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"rivalutato {percorso.name} (modello {dati.get('modello')})")
    _stampa(dati["run"])
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ripetizioni", type=int, default=3)
    ap.add_argument("--modello", default="llama3.2:3b")
    ap.add_argument("--senza-calibrazione", action="store_true",
                    help="salta le tre finestre da 30 s; energia_attiva_j non sara' valida")
    ap.add_argument("--query", default=QUERY)
    ap.add_argument("--rivaluta", default=None,
                    help="ricalcola atteso_trovato di un JSON gia' scritto, "
                         "senza eseguire nessun modello")
    args = ap.parse_args()

    if args.rivaluta:
        return _rivaluta(Path(args.rivaluta))

    _prepara_ambiente(args.modello)
    esito = asyncio.run(_esegui(args.ripetizioni, not args.senza_calibrazione,
                               args.query))
    _stampa(esito["run"])

    nome = f"confronto_a_b_{time.strftime('%Y%m%d_%H%M')}.json"
    destinazione = HERE / nome
    destinazione.write_text(json.dumps(esito, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    print(f"\nscritto {destinazione.name}")
    # esce 1 solo se la misura non ha prodotto energia: il confronto (a)/(b) non
    # e' un criterio di superamento, e' una fotografia delle due varianti
    senza_energia = [r for r in esito["run"] if r.get("energia_pkg_j") is None]
    for r in senza_energia:
        print(f"senza energia: variante {r['variante']}, run {r.get('ripetizione')}: "
              f"{r.get('misura')}", file=sys.stderr)
    return 1 if senza_energia else 0


if __name__ == "__main__":
    raise SystemExit(main())
