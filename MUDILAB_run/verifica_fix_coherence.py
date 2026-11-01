"""Cosa fanno davvero il FIX 19 e il FIX 20, misurato a tre bracci.

Perche' esiste. `tabella_prima_dopo.py` misura 0 righe che cambiano esito sul dev e
32/81 identiche prima e dopo. E' un risultato, ma letto da solo non dice se i due
fix servono: potrebbe essere codice che non tocca niente. Questa sonda lo verifica
invece di dichiararlo, e lo fa sul lato dove il punteggio non puo' nascondere: lo
stesso input, tre versioni del ramo `coherence`.

Bracci.
  A `fissato`        il file com'e' ora (FIX 19 + FIX 20);
  B `senza_FIX_20`   come A, tolti i soli 16 righe del controllo "il target non
                     puo' essere anche evidenza": mostra cosa stampa il ramo su
                     una domanda contraddittoria quando manca solo il FIX 20;
  C `prima_dei_fix`  il file com'era, letto da `MUDILAB_correzioni.zip` (31-10
                     22:41), che e' lo snapshot spedito prima del 01-11. Il diff
                     fra quella copia e il file attuale tocca solo il ramo
                     coherence (75 righe, tutte fra la 366 e la 390), quindi la
                     copia dello zip e' un "prima" fedele e non una
                     ricostruzione.

Input. Le traduzioni realmente registrate delle righe coherence del dev che
arrivarono al tool -- per queste il braccio A deve ridare la stessa identica
stringa di quell'epoca, e il test lo verifica -- piu' i due casi che il protocollo
primario ferma prima del tool ma che il tool non deve numerare: target dentro le
evidenze (la forma osservata su COH09) ed evidenza malformata.

Non chiama il modello, e non scrive nei sorgenti: i bracci B e C sono moduli
costruiti in memoria.

Uso:  MUDILAB_COPIE=1 python verifica_fix_coherence.py
"""
import csv
import json
import sys
import types
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "harness"))
sys.dont_write_bytecode = True

CART = HERE / "harness" / "risultati" / "b_composta" / "20261101_183106"
ZIP = HERE / "MUDILAB_correzioni.zip"
DENTRO_LO_ZIP = "tools_corretto.py"
OUT = HERE / "harness" / "riferimenti" / "fix_coherence_controfattuale.json"

# I due marcatori del blocco FIX 20, unici nel file: fra queste due righe sta
# solo il controllo sul target, e toglierle entrambe costruisce il braccio B.
INIZIO_20 = "            if out in evidence:\n"
FINE_20 = "            for chiave, valore in evidence.items():\n"


def _braccio_B(sorgente: str) -> str:
    i = sorgente.index(INIZIO_20)
    j = sorgente.index(FINE_20, i)
    assert sorgente.count(INIZIO_20) == 1 and sorgente.count(FINE_20) == 1, \
        "i marcatori del FIX 20 non sono unici: la sonda andrebbe riscritta"
    return sorgente[:i] + sorgente[j:]


def _carica(sorgente: str, nome: str):
    """Un modulo `tools` con quel ramo, in memoria, senza scrivere niente."""
    mod = types.ModuleType(nome)
    mod.__file__ = str(HERE / "consegna" / (nome + ".py"))
    exec(compile(sorgente, nome, "exec"), mod.__dict__)
    return mod


def _esito(mod, traduzione: dict, rete: str):
    try:
        return "numero", str(mod.cau_inference.func("coherence", json.dumps(traduzione), rete))[:200]
    except BaseException as e:  # noqa: BLE001
        return "eccezione", f"{type(e).__name__}: {str(e)[:200]}"


def main():
    argv = sys.argv
    sys.argv = [argv[0]]
    import run_query  # noqa: F401  monta `tools`/`agents` sulle copie, fa chdir
    sys.path.insert(0, str(Path(run_query.__file__).resolve().parent))
    import tools as A_mod

    current = (HERE / "consegna" / "tools_corretto.py").read_text(encoding="utf-8")
    vecchia = zipfile.ZipFile(ZIP).read(DENTRO_LO_ZIP).decode("utf-8")
    bracci = {
        "A fissato": A_mod,
        "B senza_FIX_20": _carica(_braccio_B(current), "tools_braccio_B"),
        "C prima_dei_fix": _carica(vecchia, "tools_braccio_C"),
    }

    gt = {r["task_id"]: r for r in csv.DictReader(
        open(HERE / "benchmark" / "benchmark.csv", encoding="utf-8"))}
    casi, reti = [], []
    for t, g in sorted(gt.items()):
        if g["ramo"] != "coherence" or g["split"] != "dev":
            continue
        d = json.loads((CART / f"{t}_r1.json").read_text(encoding="utf-8"))
        r = d.get("risultato") or {}
        if r.get("traduzione") is None:
            continue                     # non arrivo' al tool: nessun ramo lo vede
        casi.append({"nome": f"{t} registrata", "traduzione": r["traduzione"],
                     "rete": d.get("rete"),
                     "risposta_epoca": str(r.get("numero") or "")[:200]})
        reti.append(d.get("rete"))

    # I casi che il protocollo primario ferma prima del tool. La forma e' quella
    # osservata su COH09: la stessa variabile in `input` e in `output`.
    rete = reti[0]
    un_target = next(g for _t, g in sorted(gt.items())
                     if g["ramo"] == "coherence" and g["split"] == "dev")
    target, stato = un_target["target_variable"], un_target["target_state"]
    casi.append({"nome": "sintetico: target anche evidenza",
                 "traduzione": {"input": {target: stato}, "output": {target: stato}},
                 "rete": rete, "risposta_epoca": None})
    casi.append({"nome": "sintetico: target HundredThou, output Million (COH09)",
                 "traduzione": {"input": {"ThisCarCost": "HundredThou"},
                                "output": {"ThisCarCost": "Million"}},
                 "rete": rete, "risposta_epoca": None})
    casi.append({"nome": "sintetico: variabile inesistente nell'evidenza",
                 "traduzione": {"input": {"NonCes variable": "True"},
                                "output": {target: stato}},
                 "rete": rete, "risposta_epoca": None, "bypass": True})
    casi.append({"nome": "sintetico: stato inesistente nell'evidenza",
                 "traduzione": {"input": {"Antilock": "Falso"},
                                "output": {target: stato}},
                 "rete": rete, "risposta_epoca": None, "bypass": True})

    esiti = []
    for c in casi:
        riga = {"caso": c["nome"], "traduzione": c["traduzione"]}
        for nome, mod in bracci.items():
            tipo, testo = _esito(mod, c["traduzione"], c["rete"])
            riga[nome] = {"tipo": tipo, "testo": testo}
        if c["risposta_epoca"]:
            riga["A_uguale_all_epoca"] = (riga["A fissato"]["testo"] == c["risposta_epoca"])
        esiti.append(riga)

    # I due casi di evidenza malformata escono con un `KeyError`/`ValueError` del
    # validatore, non dal ramo: `cau_inference` chiama `_valida_stati` prima di
    # toccare pyAgrum, per ogni etichetta tranne `influence`. Il catch del FIX 19,
    # su questo percorso, quindi non si innesca mai -- e' il secondo risultato di
    # questa sonda e va detto invece di lasciarlo sottinteso. Per misurare COSA
    # comprava il catch, gli stessi due input si rifanno con la guardia
    # neutralizzata, cioe' nella condizione in cui si troverebbe chiunque la
    # rilassasse: una variante, un calling path diverso, una versione nuova.
    originale = {nome: mod.__dict__["_valida_stati"] for nome, mod in bracci.items()}
    try:
        for nome, mod in bracci.items():
            mod.__dict__["_valida_stati"] = lambda *a, **k: None
        for c in casi:
            if not c.get("bypass"):
                continue
            riga = {"caso": c["nome"] + " [guardia `_valida_stati` neutralizzata]",
                    "traduzione": c["traduzione"]}
            for nome, mod in bracci.items():
                tipo, testo = _esito(mod, c["traduzione"], c["rete"])
                riga[nome] = {"tipo": tipo, "testo": testo}
            esiti.append(riga)
    finally:
        for nome, mod in bracci.items():
            mod.__dict__["_valida_stati"] = originale[nome]

    OUT.write_text(json.dumps(esiti, ensure_ascii=False, indent=1), encoding="utf-8")

    registrate = [e for e in esiti if e["caso"].endswith("registrata")]
    uguali = sum(1 for e in registrate if e.get("A_uguale_all_epoca"))
    print(f"righe coherence registrate arrivate al tool: {len(registrate)}")
    print(f"  braccio A ridà la STESSA stringa di quell'epoca: {uguali}/{len(registrate)}")
    for nome in bracci:
        numeri = sum(1 for e in esiti if e[nome]["tipo"] == "numero")
        print(f"  {nome:16s} numeri emessi: {numeri}/{len(esiti)}")
    print("\ncasi sintetici, braccio per braccio:")
    for e in esiti:
        if e["caso"].startswith("sintetico"):
            print(f"  {e['caso']}")
            for nome in bracci:
                print(f"    {nome:16s} {e[nome]['tipo']}: {e[nome]['testo'][:112]}")
    print(f"\nscritto: {OUT}")


if __name__ == "__main__":
    main()
