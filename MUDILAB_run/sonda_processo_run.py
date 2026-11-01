"""Campionatore esterno del processo di run: guarda la memoria di un PID dall'esterno.

Perche' esiste. Il 01-11 il run misurato si e' fermato a 111 righe su 240 con il
processo a ~20 GB di working set, ma `sonda_perdita_memoria.py` (che misura la
*propria* RSS dentro rami sintetici) non reproduce la crescita: i suoi quattro
rami danno +1, +3, +4, +6 MB. Il 01-11 alle 18:21 invece il processo vivo di uno
screening in corso (b_esempi, riga ~25 su 81) e' stato letto da PowerShell a
23,77 GB di working set e 80,00 GB di commit privato, con la RAM libera della
macchina a 0,1 GB su 31,7; un minuto dopo lo stesso PID, riesaminato con lo
stesso strumento, era a 0,02 GB e 0,74 GB. Quindi l'evento non e' una perdita
monotona riga-per-riga: e' un'**allocazione transientissima e enorme**, e uno
strumento che campiona se stesso dentro un ramo sintetico non la puo' vedere.
Serve un campione esterno, a cadenza fissa, che giri mentre il run gira.

Cosa produce. Un CSV con, ogni `--ogni` secondi: timestamp, working set, commit
privato, page fault cumulati, numero di handle del PID, e RAM libera e totale del
sistema. Dopo il run il CSV si correla a due cose che gia' esistono: i `secondi`
per riga nel `riepilogo.json` della variante e il mtime di ogni JSON scritto. Se
il picco capita dentro la finestra di una riga, quella riga ha un nome.

Nessuna pretesa di causalita'. Il campionatore dice *quando* e *quanto*, non
*perche'*. Il perche' richiede di fermare il run su quella riga e ripeterla da
sola, che e' un altro esperimento e va deciso con chi legge.

Cosa ha risposto, il 01-11 alle 18:26. `PeakWorkingSetSize` e' un contatore che
non si abbassa mai: il processo vivo dello screening di `b_esempi` segnava
**25,97 GB di picco** mentre il working set corrente era 0,03 GB e la macchina
aveva 21,66 GB liberi. Il picco quindi c'e' stato ed e' gia' finito, e la riga
che lo ha prodotto si trova dai `secondi` writteni nel `riepilogo.json`: due buchi
di **219,3 s** (INT09) e **168,7 s** (INT17) fra una riga e la successiva contro
una mediana di 11 s,
con INT17 che chiude in `cau_inference: Exception: bad allocation`. Gli stessi
due task, nello stesso ramo, in `b_base` del pomeriggio: 514,1 s e 370,8 s con la
stessa `bad allocation`. E' il ramo `intervention`, che passa da
`csl.causalImpact` (`consegna/tools_corretto.py:346`).
La variante `b_verificata` sugli stessi due task non ha nessun buco (4,8 s e
6,9 s) perche' il traduttore verificato rifiuta la riga *prima* del tool: il
collo di bottiglia non e' solo di precisione, e' anche di allocazione.

Uso:  python sonda_processo_run.py --pid 20872 --etichetta b_esempi
      (gira finche' il PID vive; --minuti per fermarlo prima)
"""

import argparse
import ctypes
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CARTELLA = HERE / "harness" / "sonde_memoria"

psapi = ctypes.windll.psapi
kernel32 = ctypes.windll.kernel32


class PMC(ctypes.Structure):
    """PROCESS_MEMORY_COUNTERS_EX: il campo `PrivateUsage` e' il commit privato."""
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def misura_processo(handle) -> dict | None:
    m = PMC()
    m.cb = ctypes.sizeof(PMC)
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(m), m.cb):
        return None
    n = wintypes.DWORD()
    kernel32.GetProcessHandleCount(handle, ctypes.byref(n))
    return {
        "ws_gb": m.WorkingSetSize / 2**30,
        "pm_gb": m.PrivateUsage / 2**30,
        "peak_ws_gb": m.PeakWorkingSetSize / 2**30,
        "page_fault": m.PageFaultCount,
        "handle": n.value,
    }


def misura_sistema() -> dict:
    s = MEMORYSTATUSEX()
    s.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(s))
    return {"ram_libera_gb": s.ullAvailPhys / 2**30,
            "ram_totale_gb": s.ullTotalPhys / 2**30,
            "carico_pct": s.dwMemoryLoad}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etichetta", default="")
    p.add_argument("--minuti", type=float, default=0.0, help="0 = finche' il PID vive")
    p.add_argument("--ogni", type=float, default=2.0, help="cadenza del campione, secondi")
    a = p.parse_args()

    CARTELLA.mkdir(parents=True, exist_ok=True)
    pref = (a.etichetta + "_") if a.etichetta else ""
    csv = CARTELLA / f"{pref}{datetime.now():%Y%m%d_%H%M%S}.csv"
    # PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ: basta per leggere i
    # contatori di memoria di un processo della stessa architettura e non
    # chiede di esserne il proprietario.
    handle = kernel32.OpenProcess(0x1010, False, a.pid)
    if not handle:
        print(f"OpenProcess fallita per il PID {a.pid} (codice {kernel32.GetLastError()}): "
              "processo gia' terminato o privilegi insufficienti", flush=True)
        return 2

    t0 = time.perf_counter()
    riga_prec = None
    with open(csv, "w", encoding="utf-8", newline="") as f:
        f.write("istante,ws_gb,pm_gb,peak_ws_gb,page_fault,handle,"
                "ram_libera_gb,ram_totale_gb,carico_pct\n")
        while True:
            m = misura_processo(handle)
            if m is None:
                print("GetProcessMemoryInfo fallita: il processo e' terminato", flush=True)
                break
            s = misura_sistema()
            istante = datetime.now().strftime("%H:%M:%S")
            f.write(f"{istante},{m['ws_gb']:.2f},{m['pm_gb']:.2f},{m['peak_ws_gb']:.2f},"
                    f"{m['page_fault']},{m['handle']},{s['ram_libera_gb']:.2f},"
                    f"{s['ram_totale_gb']:.2f},{s['carico_pct']}\n")
            f.flush()
            if (m["ws_gb"] >= 1.0 or m["pm_gb"] >= 1.0 or s["ram_libera_gb"] < 2.0) \
                    and m != riga_prec:
                print(f"{istante} WS={m['ws_gb']:.2f} GB  commit={m['pm_gb']:.2f} GB  "
                      f"RAM libera={s['ram_libera_gb']:.2f} GB", flush=True)
                riga_prec = m
            if a.minuti and time.perf_counter() - t0 > a.minuti * 60:
                break
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(ct := wintypes.DWORD())) \
                    or ct.value != 259:  # STILL_ACTIVE
                print(f"PID {a.pid} terminato", flush=True)
                break
            time.sleep(a.ogni)
    print("scritto:", csv, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
