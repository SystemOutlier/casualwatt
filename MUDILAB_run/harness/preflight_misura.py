"""Verifica che il canale energetico risponda, prima di un run misurato.

Perche' esiste. `--calibra-idle` costa 90 s e il run sull'held-out costa ore: se
il contatore non risponde, l'harness lo dichiara nei campi (`canale`,
`finestra`, `idle`) e prosegue sulla sola energia del package, quindi il run non
si perde ma il numero non e' quello che si voleva. Questo preflight lo dice in
qualche secondo, usando gli stessi oggetti della misura
(`energy_session.SESSION` e `CasualWattLocalEnergyProfiler`) nello stesso ordine
di chiamate: non e' un secondo percorso che puo' rispondere quando la misura no.

Le due condizioni della macchina, aggiunte il 01-11 dopo un run perso. Il run
misurato su held-out delle 16:39 si e' fermato alla riga 111 su 240 con il
processo a 19.979 MB di working set, 145 MB liberi e 26.287 page fault/s; nel
log di Ollama, alle 17:12 e alle 17:14, compaiono due download di parti da
291 MB e 340 MB (sedici parti ciascuno), cioe' due modelli da ~5 GB che non
erano gia' su disco. La macchina non regge una misura con quelle condizioni, e
nessuno dei due fatti era visibile prima di partire. Da qui i due controlli: **i
modelli chiesti devono essere gia' presenti** (una richiesta a un nome assente
fa partire un `pull` dentro il run) e **la RAM libera deve essere sopra una
soglia dichiarata**. Non sostituiscono la misura: impediscono di sprecarla.

La soglia di RAM (6.144 MB) non e' un numero misurato: e' il modello da 2 GB
sommato a un margine per il campionatore e per cio' che gira in parallelo. E'
dichiarata qui, si puo' cambiare con `--ram-min`, e un run rifiutato lo dice per
nome, non con un errore generico.

Cosa stampa: metodo del canale, provenienza della finestra, origine della
baseline, energia del package sui due bordi, ogni errore di lettura del
contatore, la RAM libera e i modelli verificati. Ritorna 0 se il contatore ha
risposto e la macchina e' pronta, 1 altrimenti.

**Non e' una misura.** La finestra e' di pochi secondi e puo' cadere sotto il
carico di altre attivita': serve a dire "il canale c'e'", non a produrre un
joule pubblicabile. Con `--calibra` fa anche la calibrazione della baseline
(90 s), che e' utile solo se subito dopo parte il run vero.

Uso:
    python harness/preflight_misura.py [--secondi 2] [--calibra]
                                       [--modelli nome,nome] [--ram-min 6144]
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent          # MUDILAB_run
PROGETTO = ROOT.parent      # la radice del repository, dove sta cwEnergyModular
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROGETTO / "cwEnergyModular"))


def modelli_locali(base_url: str) -> set:
    """I nomi dei modelli gia' presenti sul server, senza caricarne nessuno.

    `GET /api/tags` elenca il locale e non tocca i pesi: e' l'unica chiamata che
    si puo' fare prima di un run senza cambiare le condizioni che il run
    misurera'. L'origine si prende dalla base del client (`.../v1`), perche'
    l'endpoint non sta sotto `/v1`.
    """
    u = urllib.parse.urlsplit(base_url)
    tags = urllib.parse.urlunsplit((u.scheme, u.netloc, "/api/tags", "", ""))
    with urllib.request.urlopen(tags, timeout=10) as r:
        dati = json.loads(r.read())
    # Match esatto sul tag completo: `llama3.2:3b` e `llama3.2:3b-instruct-q4_K_M`
    # sono modelli diversi e il client chiede il secondo; accettare il prefisso
    # lascerebbe passare una richiesta che non ha nulla sul disco.
    return {m.get("name", "") for m in dati.get("models", [])}


def condizioni_macchina(ram_min: float, modelli: list) -> list:
    """Le ragioni per cui la macchina non e' pronta. Lista vuota = pronta."""
    ragioni = []
    try:
        import psutil
        libera = psutil.virtual_memory().available / 1e6
        print(f"RAM libera: {libera:.0f} MB (richiesti {ram_min:.0f} MB)")
        if libera < ram_min:
            ragioni.append(f"RAM libera {libera:.0f} MB sotto i {ram_min:.0f} MB")
    except Exception as e:
        ragioni.append(f"RAM non verificabile: {type(e).__name__}: {e}")

    if modelli:
        base = os.environ.get("MUDILAB_BASE_URL", "http://localhost:11434/v1")
        try:
            presenti = modelli_locali(base)
        except Exception as e:
            ragioni.append(f"elenco modelli non letto ({base}): "
                           f"{type(e).__name__}: {e}")
        else:
            for nome in modelli:
                c_e = nome in presenti
                print(f"modello {nome}: {'presente' if c_e else 'ASSENTE'}")
                if not c_e:
                    ragioni.append(f"modello {nome} non scaricato: la prima "
                                   "richiesta avvia un pull dentro il run")
    return ragioni


def main() -> int:
    ap = argparse.ArgumentParser(description="Preflight del contatore energetico")
    ap.add_argument("--secondi", type=float, default=2.0, help="durata della finestra di prova")
    ap.add_argument("--calibra", action="store_true",
                    help="calibra anche la baseline idle (tre finestre da 30 s)")
    ap.add_argument("--modelli", default=None,
                    help="nomi che devono essere gia' sul disco, separati da "
                         "virgola; default: MUDILAB_MODEL e "
                         "MUDILAB_MODEL_SPIEGAZIONE")
    ap.add_argument("--ram-min", type=float, default=6144.0,
                    help="con meno RAM libera di cosi' (MB) il run non parte")
    a = ap.parse_args()

    if a.modelli is None:
        modelli = [m for m in (os.environ.get("MUDILAB_MODEL"),
                               os.environ.get("MUDILAB_MODEL_SPIEGAZIONE")) if m]
    else:
        modelli = [m.strip() for m in a.modelli.split(",") if m.strip()]

    # prima la macchina, poi il contatore: se la macchina non e' pronta non ha
    # senso consumare la finestra di prova ne', dopo, novanta secondi di
    # calibrazione.
    ragioni = condizioni_macchina(a.ram_min, modelli)
    if ragioni:
        for r in ragioni:
            print(f"MACCHINA NON PRONTA: {r}")
        print("il run misurato non parte: vedi il docstring di questo file")
        return 1

    from energy.energy_session import SESSION
    from energy.local_energy import CasualWattLocalEnergyProfiler

    SESSION.start()
    try:
        canale = SESSION.source_method
        print(f"canale: {canale}")

        # stesso ordine di Misura.avvia: un bordo si paga una volta e si scarta
        bordo_caldo = SESSION.read_measurement_edge()
        print(f"bordo di riscaldamento: counter_error={bordo_caldo['counter_error']!r}")

        if a.calibra:
            SESSION.settle_idle()
            baseline = SESSION.calibrate_idle()
            print(f"baseline calibrata: {baseline:.3f} W")

        profiler = CasualWattLocalEnergyProfiler()
        e0 = SESSION.read_measurement_edge()
        t0 = time.perf_counter()
        time.sleep(a.secondi)
        t1 = time.perf_counter()
        e1 = SESSION.read_measurement_edge()

        for nome, e in (("inizio", e0), ("fine", e1)):
            if e["counter_error"]:
                print(f"  errore contatore al bordo {nome}: {e['counter_error']}")

        r = profiler.profile_window(t0, t1, edge_start=e0, edge_end=e1)
        print(f"finestra di prova: {t1 - t0:.3f} s")
        print(f"energia package: {r.package_energy_j} J (grezza {r.package_energy_raw_j})")
        print(f"energia attiva: {r.active_energy_j} J (valida: {r.active_valid})")
        print(f"metodo: {r.energy_calculation_method}")
        print(f"provenienza finestra: {r.package_window_source}")
        print(f"baseline: {r.idle_provenance}")
        ok = not e0["counter_error"] and not e1["counter_error"] and r.package_energy_j is not None
        print("\nNON e' una misura: la finestra e' corta e il carico di fondo puo' essere"
              " quello di altre attivita'.")
        print("canale disponibile" if ok else "CANALE NON DISPONIBILE: il run misurato"
              " produrrebbe solo energia del package")
        return 0 if ok else 1
    finally:
        SESSION.close()


if __name__ == "__main__":
    raise SystemExit(main())
