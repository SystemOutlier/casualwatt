r"""Demo in tre blocchi per una registrazione senza operatore davanti.

Ordine: query, blocco 1, blocco 2, pagina. Non e' una scelta di stile -- l'ultimo
blocco e' l'unico che ruba il foreground (apre un browser a schermo intero), quindi
sta in coda e la clip si chiude sulla sua pagina. Nella prova delle 21:41 il blocco
0 era in testa, il browser non si era aperto (nessun predefinito per gli .html:
Windows ha mostrato il selettore "Selezionare un'app"), e i due blocchi a terminale
sono rimasti ripresi dietro una finestra che non c'entrava niente.

Blocco 1: le tre query di `FINAL.ipynb` cella 10 sui file originali della relatrice
(`MUDILAB/`). Blocco 2: le stesse sulle copie corrette (`consegna/`). Sono gli stessi
due gruppi di `verifica_conterfactual.py`, chiamati come processi separati perche'
entrambe le famiglie di moduli fa `from funtions import cobound` e il nome del modulo
collide.

Blocco 0: LA SUA PAGINA, `FINAL.ipynb` in Jupyter Lab, da una copia byte identica
(md5 scritto a video) perche' Lab scrive i checkpoint nella cartella del notebook e
`MUDILAB/` non si tocca. Sulla copia le celle 2, 3, 4, 6 e 10 vengono rieseguite da
un kernel e gli output si salvano nel file: cosi' la cella 4 compare in rosso con
`ModuleNotFoundError: No module named 'client'` (agents.py:8, il file non e' nella
consegna) e la cella 13 resta com'era -- l'output che LEI si era registrata, cioe' il
dizionario con `"Age": "P(Age=Senior | DrivQuality=Normal)"`. La cella 3 passa tutta,
`import dowhy` compreso: `dowhy 0.14` c'e' nell'ambiente `MUDILABV\mudilab_env`
(verificato il 02-11, cella per cella); il `dowhy` mancante che avevo segnalato viene
dall'altro interprete, il 3.14 di AppData, dove mancano anche `agent_framework`,
`chirho` e `azure`. Non va installato niente.

Lo script non calcola niente di nuovo e non scrive sui file della relatrice: stampa
le query verbatim dal suo notebook, lancia i processi, e raccoglie in un log ogni
riga con il suo timestamp. Serve perche' una registrazione video sia accompagnata da
un log rigenerabile, non da una descrizione a posteriori.

Nessun modello, nessuna rete fuori da 127.0.0.1, nessun contatore energetico: gira
anche con Ollama spento. Il blocco 0 apre un kernel Jupyter locale e un browser con
profilo temporaneo proprio; chiude entrambi da solo, senza toccare finestre gia'
aperte.

Uso:
    python demo_controfattuali.py                     # tutti e tre i blocchi
    python demo_controfattuali.py --blocco 1          # solo l'originale
    python demo_controfattuali.py --senza-nota        # niente pagina
    python demo_controfattuali.py --pausa 6           # piu' tempo da leggere a video
    python demo_controfattuali.py --durata-nota 90    # tempo sulla sua pagina
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORIG = HERE.parent / "MUDILAB"
RISULTATI = HERE / "harness" / "risultati"
VERIFICA = HERE / "verifica_conterfactual.py"

# i file che la sua pagina richiede accanto al notebook: se mancano, l'unica cella
# che si puo' aprire e la 2. Copia identici, non corretti.
DELL_NOTA = ("FINAL.ipynb", "agents.py", "tools.py", "funtions.py",
             "DATI.csv", "insurance_grafo.bif")

# l'ancoraggio della copia: md5 del notebook che lei ci ha dato
MD5_NOTA = "5becbcbe7309d97587bfada7142a657d"

# in ordine di preferenza: il primo che esiste viene lanciato in kiosk con un
# profilo temporaneo. Su questa macchina esistono tutti e tre (verificato 02-11).
BROWSER_CANDIDATI = (
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)

BARRA = "=" * 74

# i figli non devono lasciare __pycache__ nelle cartelle altrui, MUDILAB/ inclusa
env_figli = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def md5(percorso: Path) -> str:
    return hashlib.md5(percorso.read_bytes()).hexdigest()


def ora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def dizionario_query(notebook: Path) -> list:
    """Le tre query controfattuali, verbatim dalla cella 10 del suo notebook.

    Si prende l'assegnazione `counter` con l'AST della cella, non con una ricerca di
    parentesi: la stessa cella contiene anche `cond_prob`, `inter` e `coherence`, e
    un taglio per testo prende la lista sbagliata (misurato: JSONDecodeError).
    """
    import ast

    import nbformat

    nb = nbformat.read(str(notebook), as_version=4)
    for cell in nb.cells:
        if cell.cell_type != "code" or "counter" not in cell.source:
            continue
        for nodo in ast.parse(cell.source).body:
            if isinstance(nodo, ast.Assign):
                for bersaglio in nodo.targets:
                    if isinstance(bersaglio, ast.Name) and bersaglio.id == "counter":
                        valori = ast.literal_eval(nodo.value)
                        if isinstance(valori, (list, tuple)):
                            return list(valori)
    raise SystemExit("assegnazione `counter = [...]` non trovata in " + str(notebook))


def prepara_nota(cartella: Path, originale: Path) -> list:
    """Porta i sei file della sua pagina nella cartella di lavoro, identici.

    La copia serve a una sola cosa: Jupyter Lab scrive i checkpoint e le
    modifications nel notebook, nella cartella del notebook. Se aprissimo il suo
    `MUDILAB/FINAL.ipynb` dal suo percorso, la registrazione lascierebbe file
    nuovi dentro la sua cartella. Qui la pagina che si vede e' byte identica (md5
    stampato) e tutto cio' che Lab produce ricade nella nostra cartella.
    """
    cartella.mkdir(parents=True, exist_ok=True)
    righe = []
    for nome in DELL_NOTA:
        src = originale / nome
        dst = cartella / nome
        if not src.exists():
            righe.append(f"  [MANCANTE] {nome}: niente da copiare, la pagina non parte")
            continue
        shutil.copy2(str(src), str(dst))
        marca = md5(dst)
        if nome == "FINAL.ipynb":
            conferma = "coincide con l'ancoraggio" if marca == MD5_NOTA else "DIVERSO da " + MD5_NOTA
            righe.append(f"  [copia] {nome:22s} md5 {marca}  ({conferma})")
        else:
            righe.append(f"  [copia] {nome:22s} md5 {marca}")
    return righe


def esegui_celle(cartella: Path, indici, log, timeout: int = 240) -> list:
    """Esegue solo le celle indicate sulla COPIA e gli scrive dentro l'output.

    Il punto e' avere la cella 4 in rosso sulla sua pagina -- `ModuleNotFoundError:
    No module named 'client'`, prodotta adesso, su questa macchina -- senza perdere
    gli output che lei si era registrata sulle celle 12 e 13, che sono la prova di
    cosa ha prodotto il suo modello. Per questo non si esegue il notebook tutto
    (la cella 13 e' `await main()`: sovrascriverebbe il suo output con un errore da
    kernel senza stdin), ma solo le celle nominate, con un kernel aperto a mano.

    Fallisce in modo innocuo: se il kernel non parte o una cella va fuori tempo, la
    pagina resta quella con i suoi output e il log dice perche'.
    """
    import nbformat
    from jupyter_client.manager import KernelManager

    percorso = cartella / "FINAL.ipynb"
    nb = nbformat.read(str(percorso), as_version=4)
    righe = []
    km = KernelManager(kernel_name="python3")
    try:
        km.cwd = str(cartella)
    except Exception:
        pass
    km.start_kernel()
    kc = km.client()
    kc.start_channels()
    try:
        kc.wait_for_ready(timeout=90)
    except Exception as e:
        righe.append(f"  [!] kernel non pronto ({type(e).__name__}): la pagina resta "
                     "con gli output registrati da lei")
        return righe

    try:
        for i in indici:
            cell = nb.cells[i]
            if cell.cell_type != "code":
                continue
            msg_id = kc.execute(cell.source, store_history=True)
            outputs = []
            while True:
                try:
                    msg = kc.get_iopub_msg(timeout=timeout)
                except Exception:
                    outputs.append({"output_type": "stream", "name": "stderr",
                                    "text": f"[timeout dopo {timeout} s]\n"})
                    break
                if msg["parent_header"].get("msg_id") != msg_id:
                    continue
                contenuto = msg["content"]
                tipo = contenuto.get("msg_type")
                if tipo == "stream":
                    outputs.append({"output_type": "stream",
                                    "name": contenuto["name"],
                                    "text": contenuto["text"]})
                elif tipo in ("execute_result", "display_data"):
                    outputs.append({"output_type": tipo,
                                    "data": contenuto["data"],
                                    "metadata": contenuto.get("metadata", {}),
                                    "execution_count": contenuto.get("execution_count", 0)})
                elif tipo == "error":
                    outputs.append({"output_type": "error",
                                    "ename": contenuto["ename"],
                                    "evalue": contenuto["evalue"],
                                    "traceback": contenuto["traceback"]})
                elif tipo == "status" and contenuto["execution_state"] == "idle":
                    break
            try:
                risposta = kc.get_shell_msg(timeout=10)
                cell.execution_count = risposta["content"].get("execution_count")
            except Exception:
                pass
            cell.outputs = outputs
            marca = "ERRORE" if any(o.get("output_type") == "error" for o in outputs) else "output"
            primo = ""
            for o in outputs:
                if o.get("output_type") == "error":
                    primo = f"{o['ename']}: {o['evalue']}"[:90]
                elif o.get("output_type") == "stream":
                    primo = o["text"].strip().splitlines()[0][:90] if o["text"].strip() else ""
            righe.append(f"  [cella {i}] {marca}: {primo}")
        nbformat.write(nb, str(percorso))
        righe.append("  [scritto] output aggiornati nella copia, non nel suo file")
    finally:
        kc.stop_channels()
        km.shutdown_kernel(now=True)
    return righe


def ammazza(proc: subprocess.Popen) -> None:
    """Chiude un albero di processi che abbiamo aperto noi, non altri.

    Serve per Lab e per il browser del blocco 0: il PID e' quello che abbiamo
    lanciato con `--user-data-dir` nostro, quindi `taskkill /T /F` non tocca
    nessuna finestra gia' aperta dall'utente.
    """
    if proc.poll() is not None:
        return
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    proc.wait()


def apri_pagina(cartella: Path, interprete: str, porta: int, durata: float,
                log, browser: str = None) -> None:
    """Blocco 0: la sua pagina a schermo intero, per `durata` secondi.

    Due scelte nate entrambe da un fallimento misurato sulla clip del 21:41 di
    oggi: (1) Lab senza `--no-browser` chiama `webbrowser`, e su questa macchina
    non c'e' un browser predefinito associato, quindi Windows apre il selettore
    "Selezionare un'app" e la pagina non compare mai; (2) il browser va lanciato
    con un `--user-data-dir` temporaneo nostro e in `--kiosk`, per due motivi:
    una finestra nuova e pulita (niente tab, niente omnibox, niente dati suoi in
    inquadratura) e un PID che possiamo chiudere noi alla fine, senza toccare il
    browser che l'utente ha gia' aperto.
    """
    cmd_lab = [interprete, "-m", "jupyter", "lab", "FINAL.ipynb", "--no-browser",
               "--ServerApp.token=", "--ServerApp.password=",
               f"--ServerApp.port={porta}", "--ServerApp.port_retries=0"]
    lab = subprocess.Popen(cmd_lab, cwd=str(cartella), env=env_figli,
                           stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{porta}/lab/tree/FINAL.ipynb"

    import socket

    pronta = False
    for _ in range(90):
        if lab.poll() is not None:
            break
        try:
            with socket.create_connection(("127.0.0.1", porta), timeout=1.0):
                pronta = True
                break
        except OSError:
            time.sleep(1.0)

    print()
    print(BARRA)
    print(f"[{ora()}] BLOCCO 0 - la sua pagina: {url}")
    print(BARRA)
    log.write(f"\n{BARRA}\nBLOCCO 0 - jupyter lab su {cartella}\n{url}\n{BARRA}\n")
    if not pronta:
        messaggio = ("il server Jupyter non ha risposto sulla porta "
                     f"{porta} entro 90 s: il blocco 0 si salta")
        print("[!] " + messaggio)
        log.write("[!] " + messaggio + "\n")
        ammazza(lab)
        return

    exe = browser
    if exe is None:
        exe = next((str(Path(p)) for p in BROWSER_CANDIDATI if Path(p).exists()), None)
    if exe is None:
        messaggio = ("nessun browser fra " + ", ".join(BROWSER_CANDIDATI) +
                     ": la pagina resta solo sul server, niente da inquadrare")
        print("[!] " + messaggio)
        log.write("[!] " + messaggio + "\n")
        ammazza(lab)
        return

    profilo = cartella / "profilo_browser"
    cmd_browser = [exe, f"--user-data-dir={profilo}", "--kiosk", url,
                   "--no-first-run", "--no-default-browser-check"]
    print(f"[{ora()}] browser: {Path(exe).name} (profilo temporaneo {profilo.name})")
    browser_proc = subprocess.Popen(cmd_browser, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)

    for riga in CHECKLIST_NOTA:
        print(riga)
        log.write(riga + "\n")
    log.flush()

    print(f"[{ora()}] {durata:.0f} s sulla pagina; poi questo script chiude "
          "browser e server e la clip finisce qui")
    tempo_fine = time.time() + durata
    while time.time() < tempo_fine:
        if browser_proc.poll() is not None:
            print("[!] il browser kiosk e' uscito prima del tempo")
            break
        time.sleep(min(5.0, max(0.0, tempo_fine - time.time())))

    ammazza(browser_proc)
    ammazza(lab)
    print(f"[{ora()}] blocco 0 chiuso: browser e server arrestati da questo script")
    log.write("blocco 0 chiuso\n")
    log.flush()


def titolo_console(titolo: str) -> None:
    """Da' un titolo certo alla finestra del terminale.

    `start "MUDILABCLIP" cmd /k ...` non basta: sulla prova delle 21:41 la finestra
    risultava intitolata `npm prefix`, e AppActivate non la trovava. Il titolo qui
    lo scrive il processo stesso che possiede la console, e serve sia a riconoscere
    la finestra nella registrazione sia a catturarla da sola, con
    `ffmpeg -f gdigrab -i title=<titolo>`, se si vuole evitare di riprendere tutto
    il desktop.
    """
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.SetConsoleTitleW(titolo)


CHECKLIST_NOTA = (
    "  Cosa si vede sulla pagina (copia byte-identica, md5 scritto sopra):",
    "    cella 2  -> il path del kernel: qui e' il nostro ambiente, nella sua copia",
    "                     registrata era C:\\Users\\Samsung\\Envs\\causal",
    "    cella 3  -> tutti gli import, `import dowhy` compreso: passano",
    "    cella 4  -> `from agents import ...`: in rosso, ModuleNotFoundError",
    "                     \"No module named 'client'\" -- e' l'import di agents.py:8, il file",
    "                     `client.py` non e' nella consegna",
    "    cella 6  -> `dati.head()`: le sue 6 righe di DATI.csv",
    "    cella 10 -> le tre query controfattuali scritte da lei",
    "    cella 13 -> NON rieseguita: resta l'output registrato da lei, il dizionario",
    "                     prodotto dal suo modello con `\"Age\": \"P(Age=Senior | DrivQuality=Normal)\"`",
    "  In un secondo tempo, a mano: doppio clic su agents.py nel pannello di sinistra e",
    "  riga 17 `#CLIENTS` vuota, con la 37 che chiama `client= gpt5` che nessuno definisce.",
)

# le celle rieseguite sulla copia: 12 e 13 restano fuori per non sovrascrivere
# l'output che lei si era registrata sulla conversazione
CELLE_DA_ESEGUIRE = (2, 3, 4, 6, 10)


def lancia(titolo: str, cmd: list, log, pausa: float) -> int:
    print()
    print(BARRA)
    print(f"[{ora()}] {titolo}")
    print(BARRA)
    log.write(f"\n{BARRA}\n{titolo}\n{BARRA}\n")
    log.flush()
    tempo = time.time()
    proc = subprocess.Popen(cmd, cwd=str(HERE), env=env_figli,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            encoding="utf-8", errors="replace")
    for riga in proc.stdout:
        print(riga, end="", flush=True)
        log.write(riga)
    proc.wait()
    log.flush()
    durato = time.time() - tempo
    print(f"[{ora()}] uscita {proc.returncode} in {durato:.1f} s")
    log.write(f"\n[uscita {proc.returncode}] [tempo {durato:.1f} s]\n")
    log.flush()
    if pausa:
        time.sleep(pausa)
    return proc.returncode


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--blocco", choices=("0", "1", "2", "tutti"), default="tutti")
    p.add_argument("--pausa", type=float, default=4.0,
                   help="secondi di pausa fra i passi, per la lettura a video")
    p.add_argument("--durata-nota", type=float, default=75.0,
                   help="secondi da lasciare la sua pagina a schermo (blocco 0)")
    p.add_argument("--porta", type=int, default=8899,
                   help="porta del server Jupyter Lab del blocco 0")
    p.add_argument("--senza-nota", action="store_true",
                   help="salta il blocco 0: solo terminale, nessuna finestra Lab")
    p.add_argument("--senza-esecuzione", action="store_true",
                   help="non rieseguire le celle sulla copia: pagina ferma agli "
                        "output che lei si era registrata")
    p.add_argument("--browser", default=None,
                   help="eseguibile del browser per il blocco 0 "
                        "(default: il primo esistente fra Brave, Edge, Chrome)")
    p.add_argument("--titolo", default=None,
                   help="titolo da dare alla finestra del terminale (per "
                        "riconoscerla nella registrazione)")
    p.add_argument("--orig", default=None, help="cartella con i file originali")
    p.add_argument("--python", default=None,
                   help="interprete con pyagrum (default: quello che lanci)")
    p.add_argument("--log", default=None, help="percorso del log (default: harness/risultati)")
    args = p.parse_args()

    globale = ORIG
    if args.orig:
        globale = Path(args.orig).resolve()
    interprete = args.python or sys.executable
    if args.titolo:
        titolo_console(args.titolo)

    RISULTATI.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    percorso_log = Path(args.log) if args.log else RISULTATI / f"demo_controfattuali_{stamp}.log"

    # le copie corrette le cerca verifica_conterfactual.py accanto a se' o in consegna/
    cmd_base = [interprete, str(VERIFICA)]

    print(BARRA)
    print(f"[{ora()}] DEMO controfattuali - file originali in {globale}")
    print(f"[{ora()}] interprete: {interprete}")
    print(f"[{ora()}] log: {percorso_log}")
    print(BARRA)

    esiti = {}
    with percorso_log.open("w", encoding="utf-8", newline="") as log:
        log.write(f"demo_controfattuali.py del {stamp}\n")
        log.write(f"originali: {globale}\ninterprete: {interprete}\n")

        try:
            query = dizionario_query(globale / "FINAL.ipynb")
        except FileNotFoundError:
            query = []
            print("[!] FINAL.ipynb non trovato: le query non vengono stampate")
        if query:
            print()
            print("Le tre query controfattuali, verbatim da FINAL.ipynb cella 10:")
            log.write("\nLe tre query controfattuali, verbatim da FINAL.ipynb cella 10:\n")
            for i, q in enumerate(query, 1):
                riga = f"  CF{i}. {q}"
                print(riga)
                log.write(riga + "\n")
            time.sleep(args.pausa)

        if args.blocco in ("1", "tutti"):
            esiti["1"] = lancia("BLOCCO 1 - i suoi file originali: la query NON arriva al ramo",
                                cmd_base + ["--gruppo", "originale", "--orig", str(globale)],
                                log, args.pausa)
        if args.blocco in ("2", "tutti"):
            esiti["2"] = lancia("BLOCCO 2 - le copie corrette, stessa query: i tre intervalli si calcolano",
                                cmd_base + ["--gruppo", "corretto"], log, args.pausa)

        # riepilogo scritto PRIMA di aprire la pagina: dopo, il terminale e' coperto
        # dal kiosk e quella riga non la vede piu' nessuno.
        print()
        print(BARRA)
        print(f"[{ora()}] fine dei blocchi a terminale: " +
                ", ".join(f"blocco {k} uscita {v}" for k, v in esiti.items()))
        print(f"[{ora()}] log: {percorso_log}")
        print(BARRA)
        log.write(f"\nfine dei blocchi a terminale: {esiti}\n")
        log.flush()

        # Il blocco 0 viene per ultimo di proposito: e' l'unico passaggio che ruba
        # il foreground (il browser kiosk), e mettendolo alla fine non c'e' niente
        # da riportare avanti -- la registrazione si chiude sulla sua pagina.
        if args.blocco in ("0", "tutti") and not args.senza_nota:
            cartella_nota = RISULTATI / f"nota_{stamp}"
            for riga in prepara_nota(cartella_nota, globale):
                print(riga)
                log.write(riga + "\n")
            log.flush()
            if not args.senza_esecuzione:
                try:
                    righe = esegui_celle(cartella_nota, CELLE_DA_ESEGUIRE, log)
                except Exception as e:
                    righe = [f"  [!] esecuzione saltata ({type(e).__name__}: {e}): "
                             "la pagina resta con gli output registrati da lei"]
                for riga in righe:
                    print(riga)
                    log.write(riga + "\n")
                log.flush()
            apri_pagina(cartella_nota, interprete, args.porta,
                        args.durata_nota, log, args.browser)
        elif args.senza_nota:
            print(f"[{ora()}] blocco 0 saltato (--senza-nota)")

    return 0 if all(v == 0 for v in esiti.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
