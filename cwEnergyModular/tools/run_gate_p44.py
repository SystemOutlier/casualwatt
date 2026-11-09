# -*- coding: utf-8 -*-
"""tools/run_gate_p44.py — il gate load-versus-control di P4.4 sulla v4.

Perche' esiste. P4.4 (emendamento del 2026-10-24, terza emenda sostanziale)
vuole un numero dichiarato di coppie di blocchi (default sei): per ogni
coppia un blocco di carico
(``block_kind='load'``, m=32 richieste, num_predict=32) e un blocco di
controllo (``block_kind='control'``, finestra passiva di ``dt_nominal_s``
SENZA inviare richieste — requisito 5). Il disegno e' dichiarato
PRIMA dei dati in ``plan.json``; l'esito passa dal criterio F.12 di
``control_gate.evaluate_gate``, che restituisce ``status``
pass/fail/not-executable, ``chain_status`` e il bias aggregato.

L'obiettivo del gate e' verificare se il carico introduce un residuo
di potenza o energia compatibile con il fondo misurato della macchina.
Il criterio F.12 confronta il bias aggregato con la mediana dei budget
di fondo, senza essere un test di significatività statistica.

Definizione del measurand: il residuo medio di potenza su finestra di
controllo (durata T_c = DT_NOM_FROZEN). Il budget di fondo deve essere
stimato sulla stessa scala temporale del controllo per garantire la
coerenza metrologica.

L'obiettivo del gate e' verificare se il carico introduce un residuo
di potenza o energia compatibile con il fondo misurato della macchina.
Il criterio F.12 confronta il bias aggregato con la mediana dei budget
di fondo, senza essere un test di significatività statistica.

Definizione del measurand: il residuo medio di potenza su finestra di
controllo (durata T_c = DT_NOM_FROZEN). Il budget di fondo deve essere
stimato sulla stessa scala temporale del controllo per garantire la
coerenza metrologica.

Struttura del run (emendata dopo la verifica pre-esecuzione del 2026-11-08):
DODICI invocazioni di ``run_v4_benchmark``, una per blocco, con
``blocks_per_point=1`` e ``pair_id='pair-<coppia>'`` — non piu' sei invocazioni
da due blocchi, perche' in quel disegno il ``pair_id`` era uno solo per la
coppia e il blocco di controllo non era mai attivato (il runner derivava
``control`` da ``block_kind``, ma l'etichetta di una singola invocazione non
puo' coprire due bracci diversi). L'ordine e' carico-primo per coppia,
dichiarato, non randomizzato; ``order_seed`` e' il seme del disegno
(requisito 3), parametrizzato con ``--seed``: il default e'
``'gate-seed-20261107'``, la campagna dichiarata, quindi nulla cambia per chi
non lo passa. Il numero di coppie e' parametrizzato con ``--pairs``
(default 6): la Quattordicesima emenda (2026-11-08) adotta 12 coppie per la
terza campagna, stessa ``dt_nominal_s`` congelata, quorum 8.

Il cooldown intra-coppia (P1.5) e' una SCELTA OPERATIVA, non un requisito di
P4.4: il requisito 7 vincola la struttura di baseline (3 pre + 3 post su
entrambi i bracci), non il cooldown. Il blocco di controllo riceve il
``P_pre`` del carico della stessa coppia tramite ``initial_last_pre_w``, letto
dall'ultima riga di riepilogo scritta; se la propagazione manca, il tool si
ferma prima di proseguire — un controllo senza cooldown verso il carico e' un
disegno diverso da quello dichiarato, scoperto dopo i dati.

Parametri inerti: su un blocco di controllo ``m``, ``num_predict`` e
``use_nonce`` NON vengono passati — le richieste sono ``range(0)`` per
costruzione (requisito 5), quindi qualunque valore sarebbe una finzione. Il
percorso di controllo e' derivato nel runner da ``block_kind == "control"``.

Come il gate legge i controlli. ``control_e_net_j``, ``control_dt_w_s`` e
``control_package_window_source`` NON hanno colonna nello schema P5 congelato
(``export_summary_csv`` le scarta con ``extrasaction='ignore'``): un tool che
rileggesse i controlli dal CSV consegnerebbe a ``evaluate_gate`` campi per
costruzione vuoti, e il gate si dichiarerebbe non eseguibile DOPO la campagna.
La forma di consumo prevista e' il riepilogo completo del runner (e' quella
che :meth:`control_gate.main` legge da ``--blocks``): il tool cattura i
riepiloghi nell'attimo in cui il runner li passa a ``export_summary_csv`` e
consegna anche ``blocks_controllo.json``, artefatto con la stessa forma. Il
CSV resta la fonte della propagazione (``baseline_pre_w`` e' una colonna) e
dei controlli d'identita'.

Emenda 8: ``K=1`` per invocazione (il runner si invalida al primo guasto) e
``substitution_seed='p44-<label>'`` per blocco. ``dt_nominal_s`` e' congelato
dal pilota P2.9 (requisito 5): 2,930748 s.

La data di campagna e' un parametro (``--date YYYYMMDD``, default la campagna
del 2026-11-07): sposta ``ARCHIVE_DIR`` e ``RESULTS_DIR`` senza toccare
``plan_blocks()`` o la durata congelata, quindi la verifica del piano resta
valida e un secondo run non richiede di editare il codice. Anche il seme e'
un parametro (``--seed``): ``_verifica_piano`` confronta il piano contro il
seme passato, non contro una costante — un execute con un seme diverso da
quello del plan si ferma prima di misurare. Il risultato congelato di una
campagna non si sovrascrive: ``execute`` rifiuta output gia' presenti.

Serie di potenza grezza. Il runner non salva i campioni della finestra
passiva (il riepilogo porta solo gli aggregati ``control_*``): senza la serie
non si puo' dire se il bias di un controllo sia una deriva o un picco. Il tool
la cattura lato proprio — wrapper di ``_run_control_window`` che trattiene i
due bordi e chiede ``samples_between(t0, t1)`` alla sessione, senza letture
aggiuntive sul contatore — e la scrive in ``control_power_series.json``.
E' diagnostica: non entra nel criterio F.12. Per la campagna del 2026-11-07
la serie non esiste e non e' recuperabile a posteriori: la cattura vale per
quelle successive.

Precondizione di quiete. Il gate del 2026-11-07 e' fallito con
``background_load=True`` su 5 controlli su 6: P1.4 registra il flag ma il
runner parte comunque. Prima di OGNI blocco (load e control) il tool
attende che ``ms.background_load_from_samples`` sia False per
``QUIET_CONSECUTIVE`` letture consecutive; una lettura rumorosa azzera il
conteggio; al tetto ``QUIET_CAP_S`` senza quiete, ``SystemExit``
([ARRESTO], exit 3), mai procedere in silenzio. Le costanti sono congelate
in ``plan.json`` prima delle misure (check E) e la verifica del piano le
confronta: il plan del 2026-11-07, che precede la precondizione, non e'
eseguibile e va ripianificato. Attesa e top-5 alla partenza sono registrati
per blocco in ``runs``, nel report e in ``gate_result_frozen.json``. E' una
precondizione di ESECUZIONE: il criterio F.12 non cambia.

Grandezze riportate, non criterio. Per tutti i controlli, anche non
utilizzabili, il tool riporta E_net/dt_W e le statistiche descrittive fra
blocchi (media, sd campionaria ddof=1, SE, CI95 con t di Student: scipy se
installato, altrimenti tabella dichiarata; df>30 senza scipy -> 1.960,
approssimazione normale dichiarata). Nel report una tabella per controllo
con ``background_load`` prima/dopo dal riepilogo del runner. Queste
grandezze NON decidono l'esito (che resta F.12) e non entrano nello schema
CSV: la sd e' fra blocchi, non sulla terna di baseline di P4.12, dove a
n=3 il divieto di stimare una varianza resta.

Confronto diagnostico CodeCarbon (``--codecarbon``, opzionale). Il runner
apre ``tools/codecarbon_probe.py`` e avvolge OGNI invocazione di
``run_v4_benchmark`` con un start/stop del tracker; gli artefatti (CSV,
manifest con finestre wall per blocco, status con backend e motivo) vanno
in ``<archivio>/codecarbon/``, mai nel CSV di misura. Il gate primario non
si muove: senza flag il modulo non viene nemmeno importato e l'analysis non
contiene la chiave ``codecarbon``; con il flag, e con CodeCarbon assente o
guasto, il gate PROSEGUE e lo stato dichiara ``unavailable`` con il motivo.
I numeri CodeCarbon non correggono nulla — su questo host leggono peraltro
lo stesso registro 0x611 della catena emi-counter (caveat nel modulo).
``--codecarbon-interval`` configura ``measure_power_secs`` (default del
probe: 1 s, fallback 15 s). E' un'estensione neutra dichiarata, nel senso
della guardia pre-flight del 2026-11-08: il percorso di misura
(``benchmark_v4.py``, ``energy/``) non cambia, il tool del gate si.
"""
from __future__ import annotations
import argparse
import csv
import datetime as _dt
import hashlib
import json
import math
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
MODULE_DIR = HERE.parent
REPO_ROOT = MODULE_DIR.parent
sys.path.insert(0, str(MODULE_DIR))
sys.path.insert(0, str(REPO_ROOT))

import psutil  # noqa: E402

import config  # noqa: E402
import benchmark_v4 as v4  # noqa: E402
import control_gate as cg  # noqa: E402
import machine_state as ms  # noqa: E402
import gate_uncertainty as gu  # noqa: E402

try:  # scipy e' opzionale: senza, la tabella t dichiarata sotto
    from scipy.stats import t as _scipy_t  # noqa: E402
except ImportError:
    _scipy_t = None

DEFAULT_DATE = "20261107"       # campagna dichiarata; --date per le successive
P44_DATE = DEFAULT_DATE         # etichetta di campagna, non del disegno
ARCHIVE_DIR = REPO_ROOT / "experiment_results" / f"p44_gate_{P44_DATE}"
RESULTS_DIR = MODULE_DIR / "results" / f"p44_gate_{P44_DATE}"
ROWS_NAME = "casualwatt_v4_results_p44.csv"
BLOCKS_NAME = "casualwatt_v4_block_summary_p44.csv"
PLAN_NAME = "plan.json"
ANALYSIS_NAME = "analysis.json"
FREEZE_NAME = "gate_result_frozen.json"
REPORT_NAME = "p44_gate_report.md"
BLOCKS_JSON_NAME = "blocks_controllo.json"
SERIES_NAME = "control_power_series.json"
BUDGET_PREREG_NAME = "budget_preregistrato.json"
WARMUP_LOG_NAME = "warmup_stabilizzazione.jsonl"
DEFAULT_MODEL = "hf.co/sigmanih/Qwen-Qwen3-0.6B-GGUF-Q6_K:latest"
K_MAX = 1                       # Emenda 8: sostituzione di un blocco
DEFAULT_SEED = "gate-seed-20261107"  # campagna dichiarata; --seed per le altre
SEED = DEFAULT_SEED             # requisito 3: seme del disegno, dichiarato
DEFAULT_BUDGET_MODE = "short"    # "short" | "matched" (revisione gate 2026-11-09)
BUDGET_MODE = DEFAULT_BUDGET_MODE
# Regola di aggregazione del budget pre-esecuzione: TERNE di finestre idle
# (3 pre + 3 post), la stessa struttura di P1.3/P1.5 applicata alla scala
# della finestra, senza fattori di scala da 30 s.
BUDGET_N_TERNE = 3               # ripetizioni per gruppo (pre e post)
BUDGET_MATCHED_TARGET_S = 30.0   # durata equivalente dell'aggregato (matched)
# Pavimento del primitivo di lettura: ``energy_session.py:672`` porta la
# finestra richiesta a ``max(duration_s, 0.5)``. Chiedere una finestra piu'
# breve e' FISICAMENTE impossibile su questo canale, quindi una procedura a
# scala Tc con Tc sotto il pavimento non e' eseguibile: non si prende il
# valore di 0,5 s spacciandolo per Tc: sarebbe ancora una volta una
# grandezza letta su una scala e dichiarata su un'altra. Il Tc congelato
# (2,930748 s) e' sopra il pavimento.
BUDGET_FLOOR_FINESTRA_S = 0.5
DT_NOM_FROZEN = 2.930748        # pilota P2.9, requisito 5: congelato
GEOMETRY = "12,32"              # requisito 4: punto operativo di P3.5
NUM_CTX = 8192
LOAD_PROMPT = "Spiega in una frase cos'e' un watt."   # n_in ~51 token
LOAD_M = 32
LOAD_NUM_PREDICT = 32
DEFAULT_PAIRS = 6               # disegno delle campagne 2026-11-07 e 2026-11-08
N_COPPIE = DEFAULT_PAIRS        # --pairs per la terza campagna (Quattordicesima
                                # emenda: 12 coppie, quorum ceil(2/3*12) = 8)
N_BLOCCHI = 2 * N_COPPIE
BLOCKS_PER_POINT = 1            # un blocco per invocazione: due bracci non
                                # possono stare sotto lo stesso block_kind

# Precondizione di quiete (lato tool, P1.4): il gate del 2026-11-07 e'
# fallito con background_load=True su 5 controlli su 6 — il runner registra
# il flag nel verbale ma parte comunque. Questa e' una precondizione di
# ESECUZIONE, lato tool: il criterio F.12, le soglie e il disegno non si
# muovono, e il runner non cambia comportamento.
QUIET_CONSECUTIVE = 3           # letture consecutive non rumorose per partire
QUIET_CAP_S = 600.0             # tetto: oltre, SystemExit, mai in silenzio
QUIET_POLL_S = 0.0              # ogni lettura e' gia' ~3 s di osservazione
                                # (total_cpu_samples): nessuna pausa in piu'
#
# Warm-up post-carico (Revisione del Gate 2026-11-09, secondo ciclo): criterio
# MISURATO su due segnali contemporanei, non una durata fissa.
#
# Perche' i numeri non sono una convenzione. Le due popolazioni sono misurate
# nella seconda campagna, lette il 2026-11-09 da
# ``experiment_results/p44_gate_20261108/control_power_series.json`` (campioni
# di contatore) e ``.../blocks_controllo.json`` (``baseline_pre_w`` di ogni
# blocco), RIAGGREGATE alla scala che il criterio legge: finestre non
# sovrapposte da ``WARMUP_WINDOW_S`` = 2 s ancorate a ``t0_mono`` del blocco,
# potenza = delta del contatore / delta di tempo dentro la finestra,
# cpu_percent = media dei campioni della finestra. ctrl-1, il primo blocco
# della campagna, e' il transitorio (potenza per-campione 4,3858 / 3,9937 /
# 3,4544 / 4,5059 W e ``cpu_percent`` 8,3 % al primo campione); ctrl-2..6 sono
# i cinque stabilizzati. Sulle finestre:
#   stabilizzati -> deviazione massima 0,3626 W, cpu media massima 1,000 %
#   transitorio  -> finestra 1: 0,4802 W e 4,100 %
#                   finestra 2: 0,7951 W e 1,800 %
# Di qui le tre scelte, ciascuna stretta fra le due popolazioni:
#   WARMUP_TOLERANCE_W = 0,5  -> sopra il massimo degli stabilizzati (0,3626),
#                               sotto l'escursione del transitorio (0,7951)
#   WARMUP_CPU_MAX_PCT  = 2,0 -> sopra il massimo degli stabilizzati (1,000),
#                               sotto la prima finestra del transitorio (4,100)
#   WARMUP_SUSTAIN_S    = 10  -> la massima sequenza CONTINUA dentro la banda
#                               di potenza nel blocco in transitorio e' 1,09 s e
#                               le sue oscillazioni riempiono l'intera finestra
#                               da 2,94 s; 10 s chiedono 3,41 finestre Tc
#                               (2,930748 s) consecutive e non sono piu' lasche
#                               della persistenza gia' pretesa dalla quiete
#                               P1.4 (tre letture da ~3 s).
# I DUE segnali vanno dentro soglia nella STESSA finestra, e non e' un
# rafforzamento: guardando le finestre sopra, la prima del transitorio e'
# DENTRO la banda di potenza (0,4802 < 0,5) e fuori da quella di cpu, la
# seconda e' viceversa. Nessuna delle due soglie da sola respinge il
# transitorio per intero; insieme lo respingono su entrambe le finestre, e
# su nessuna finestra dei cinque stabilizzati alcuna delle due scatta.
# E' questa la ragione per cui la guardia non puo' stare sulla sola potenza.
# Il tetto ``WARMUP_CAP_S`` ferma la campagna con ``SystemExit``: un controllo
# immesso in transitorio rimetterebbe il residuo di carico dentro ``E_net``,
# che e' esattamente il difetto che questa fase esiste per togliere.
#
# La temperatura NON e' un criterio, ed e' registrato perche' non lo e'. Su
# questo host psutil 7.2.2 non espone ``sensors_temperatures`` (misurato
# 2026-11-09: ``dir(psutil)`` da' ``sensors_battery`` e nessun ``sensors_*``
# termico) e il thermal zone ACPI letto via CIM e' rimasto 3010 (= 27,85 C) su
# sei letture a 5 s: nessuna deriva osservata, quindi nessuna soglia motivata;
# inventarne una sarebbe la convenzione appena tolta. Il valore viene
# REGISTRATO all'ingresso e all'uscita del warm-up, una sola letta per fase,
# perche' lo spawn del lettore consuma CPU proprio mentre si osserva il
# ``cpu_percent``: la registrazione servira' da evidenza per una soglia termica
# di una campagna futura, non da guardia di questa. La lettura d'ingresso puo'
# sporcare la PRIMA finestra di ``cpu_percent`` (costo misurato 0,26-0,33 s):
# l'effetto e' solo conservativo perche' puo' azzerare un tratto gia' aperto e
# mai chiuderlo su una macchina rumorosa.
WARMUP_TOLERANCE_W = 0.5        # tolleranza di rientro dalla baseline [W]
WARMUP_CPU_MAX_PCT = 2.0        # media di finestra di cpu_percent [%]
WARMUP_SUSTAIN_S = 10.0         # permanenza consecutiva dei DUE segnali [s]
WARMUP_CAP_S = 60.0             # tetto: oltre, SystemExit, mai in silenzio
WARMUP_WINDOW_S = 2.0           # finestra osservata per campione [s]
WARMUP_STEP_S = 0.0             # nessuna pausa in piu': la lettura di
                                # ``cpu_percent`` SULLA finestra e' gia'
                                # l'osservazione (come QUIET_POLL_S)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _scrittura_atomica(path: Path, payload) -> None:
    text = payload if isinstance(payload, str) else \
        json.dumps(payload, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _git_esegui(args: Sequence[str]) -> Tuple[Optional[int], str, str]:
    """Esegue git nel repository del piano: (codice, stdout, ragione).

    ``codice`` e' ``None`` quando il processo non parte affatto (git
    mancante, timeout, o la CreateProcess che su questo host risponde
    ``OSError(22, ..., winerror=50)`` se chiamata dalla cattura di pytest).
    I due stati non sono lo stesso evento e non hanno la stessa colpevole:
    ``git`` che esce diverso da zero e' una risposta (la storia non contiene
    quel commit), ``git`` che non parte e' una guardia non decidibile. Il
    fail-closed e' identico — nessuna delle due passa — ma la ragione
    stampata deve essere quella vera.
    """
    try:
        out = subprocess.run(["git", *args], cwd=str(REPO_ROOT),
                             capture_output=True, text=True, timeout=20)
    except Exception as exc:  # noqa: BLE001 - non decidibile, non "falso"
        return None, "", f"git non eseguibile: {type(exc).__name__}: {exc}"
    if out.returncode != 0:
        stderr = (out.stderr or "").strip()
        return (out.returncode, out.stdout,
                stderr or f"git esce con codice {out.returncode}")
    return 0, out.stdout, ""


def _git_provenienza() -> Tuple[str, str]:
    """(sha di HEAD, ragione): la testa del repository al momento del plan."""
    codice, out, ragione = _git_esegui(["rev-parse", "HEAD"])
    return ((out.strip(), "") if codice == 0 else ("", ragione))


def _git_head() -> str:
    return _git_provenienza()[0]


# Il percorso di misura che il piano congela con ``git_head``: il runner e
# la catena dei contatori. Il tool del gate puo' ricevere estensioni neutre
# dichiarate (es. il probe diagnostico CodeCarbon); QUESTO percorso no.
PERCORSO_MISURA = ("cwEnergyModular/benchmark_v4.py", "cwEnergyModular/energy")


def _git_antenato_con_ragione(sha: str) -> Tuple[bool, str]:
    codice, _, ragione = _git_esegui(
        ["merge-base", "--is-ancestor", sha, "HEAD"])
    return (True, "") if codice == 0 else (False, ragione)


def _git_antenato(sha: str) -> bool:
    """True se ``sha`` e' un antenato di HEAD (o HEAD stesso).

    Forma scelta il 2026-11-08 per la guardia sul ``git_head`` del piano:
    l'uguaglianza stretta ``git_head == HEAD`` sarebbe rotta dal commit del
    piano stesso (il piano registra il commit dell'emenda, poi si committa
    il piano). Se git non risponde, False: una guardia non verificabile
    non passa in silenzio.
    """
    return _git_antenato_con_ragione(sha)[0]


def _git_percorso_misura_mutato(da_sha: str) -> Optional[bool]:
    """True se il percorso di misura e' cambiato fra ``da_sha`` e HEAD,
    False se e' invariato, None se git non risponde (non decidibile).

    Il diff e' fra commit, non sull'albero di lavoro: le modifiche non
    committate al tool del gate non entrano, e il runner e' ancorato anche
    dal suo SHA-256 registrato nel piano (guardia separata).
    """
    codice, out, _ = _git_esegui(
        ["diff", "--name-only", f"{da_sha}..HEAD", "--", *PERCORSO_MISURA])
    return None if codice != 0 else bool(out.strip())


def _imposta_data(data: str) -> None:
    """Sposta archivio e results su un'altra campagna dichiarata (``--date``).

    La data e' un'etichetta di campagna, non un parametro del disegno:
    ``plan_blocks()``, il seed e ``DT_NOM_FROZEN`` non dipendono da essa,
    quindi la verifica del piano resta quella congelata. Un secondo run
    non richiede di editare il codice; il risultato della prima campagna
    non si tocca. Formato accettato: YYYYMMDD (otto cifre, data reale).
    """
    global P44_DATE, ARCHIVE_DIR, RESULTS_DIR
    try:
        _dt.datetime.strptime(data, "%Y%m%d")
    except (TypeError, ValueError):
        raise SystemExit(
            f"--date '{data}' non valida: atteso YYYYMMDD (es. 20261107)")
    if len(data) != 8 or not data.isdigit():
        raise SystemExit(
            f"--date '{data}' non valida: atteso YYYYMMDD (es. 20261107)")
    P44_DATE = data
    ARCHIVE_DIR = REPO_ROOT / "experiment_results" / f"p44_gate_{data}"
    RESULTS_DIR = MODULE_DIR / "results" / f"p44_gate_{data}"


def _imposta_seme(seme: str) -> None:
    """Il seme del disegno e' un parametro (``--seed``), non una costante.

    Default = il seme della campagna dichiarata del 2026-11-07: nulla cambia
    per chi non lo passa. ``_verifica_piano`` confronta il piano contro
    QUESTO valore: un execute con un seme diverso da quello del plan si
    ferma prima di misurare, perche' un ordine dei blocchi estratto con un
    seme diverso e' un disegno diverso da quello dichiarato. Il valore e'
    conservato esattamente come passato (nessuno strip silencioso): un seme
    vuoto o di soli spazi non e' un seme e si rifiuta.
    """
    global SEED
    if not isinstance(seme, str) or not seme.strip():
        raise SystemExit(
            f"--seed '{seme}' non valido: atteso un seme non vuoto "
            f"(default {DEFAULT_SEED!r})")
    SEED = seme


def _imposta_coppie(n: int) -> None:
    """Il numero di coppie e' un parametro (``--pairs``), non una costante.

    Default = 6, il disegno delle prime due campagne: nulla cambia per chi
    non lo passa. La Quattordicesima emenda (2026-11-08) adotta la decisione 6
    della Tredicesima nella forma minima: 12 coppie, stessa ``dt_nominal_s``
    congelata, quorum ``ceil(2/3 * 12) = 8``. ``_verifica_piano`` confronta il
    piano contro QUESTO valore: un execute con un numero di coppie diverso da
    quello del plan si ferma prima di misurare, perche' un disegno con piu'
    (o meno) coppie e' un disegno diverso da quello dichiarato. Un intero
    positivo e' l'unico valore accettato: zero o negativo non sono un disegno,
    e un non intero non e' un conteggio.
    """
    global N_COPPIE, N_BLOCCHI
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise SystemExit(
            f"--pairs '{n}' non valido: atteso un intero positivo "
            f"(default {DEFAULT_PAIRS})")
    N_COPPIE = n
    N_BLOCCHI = 2 * n


def plan_blocks() -> List[Dict]:
    """Le righe dichiarate (due per coppia): carico poi controllo."""
    blocchi = []
    for i in range(N_BLOCCHI):
        coppia = i // 2
        if i % 2 == 0:
            blocchi.append({
                "index": i, "label": f"carico-{coppia + 1}", "arm": "load",
                "pair_id": f"pair-{coppia}",
                "prompt_id": f"load-{coppia + 1}", "text": LOAD_PROMPT,
                "source": "p44_gate",
                "m": LOAD_M, "num_predict": LOAD_NUM_PREDICT,
                "use_nonce": True,
            })
        else:
            # m/num_predict/use_nonce NON si passano: su una finestra passiva
            # sono inerti (requisito 5) e passarli fingerebbe che operino.
            blocchi.append({
                "index": i, "label": f"controllo-{coppia + 1}",
                "arm": "control", "pair_id": f"pair-{coppia}",
                "prompt_id": f"ctrl-{coppia + 1}", "text": "",
                "source": "gate_control",
                "richieste": 0, "dt_nominal_s": DT_NOM_FROZEN,
            })
    return blocchi


def plan_payload() -> Dict:
    """Disegno dichiarato. Tutto dipende da P2.9: DT_NOM e' il pilota."""
    return {
        "pilot": "P4.4 gate",
        "campaign_date": P44_DATE,
        "declared_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        "model": DEFAULT_MODEL,
        "temperature": config.DEFAULT_TEMPERATURE,
        "timeout_s": config.DEFAULT_TIMEOUT_S, "num_ctx": NUM_CTX,
        "order_seed": SEED,
        "n_coppie": N_COPPIE, "n_blocchi": N_BLOCCHI,
        "blocks_per_point": BLOCKS_PER_POINT,
        "invocazioni": (f"una run_v4_benchmark per blocco ({N_BLOCCHI}), "
                        f"non {N_COPPIE} da 2"),
        "emenda8": {"max_invalidated_blocks": K_MAX,
                    "substitution_seed": "p44-<label> per blocco"},
        # Congelate PRIMA delle misure: un'esecuzione con una precondizione
        # diversa e' un disegno di esecuzione diverso, e la verifica sotto
        # lo rifiuta invece di scoprirlo sui dati.
        "quiet_consecutive": QUIET_CONSECUTIVE,
        "quiet_cap_s": QUIET_CAP_S,
        "warmup_tolerance_w": WARMUP_TOLERANCE_W,
        "warmup_cpu_max_pct": WARMUP_CPU_MAX_PCT,
        "warmup_sustain_s": WARMUP_SUSTAIN_S,
        "warmup_cap_s": WARMUP_CAP_S,
        "warmup_step_s": WARMUP_STEP_S,
        "warmup_window_s": WARMUP_WINDOW_S,
        "budget_mode": BUDGET_MODE,
        "budget_n_terne": BUDGET_N_TERNE,
        "budget_matched_target_s": BUDGET_MATCHED_TARGET_S,
        "budget_floor_finestra_s": BUDGET_FLOOR_FINESTRA_S,
        "criterio_primario": CRITERIO_PRIMARIO,
        "criterio_storico_riportato": CRITERIO_STORICO_F12,
        "geometry": GEOMETRY,
        "checks": {
            "A": (f"{N_BLOCCHI} blocchi in {N_COPPIE} coppie; ogni coppia: "
                  "blocco load m=32/np=32/nonce, poi blocco control con "
                  "finestra passiva di dt_nominal_s e ZERO richieste "
                  "(requisiti 1 e 5)"),
            "B": (f"geometria operativa (12,32) confermata (requisito 4); "
                  f"DT_NOM = {DT_NOM_FROZEN} s congelata dal pilota P2.9 "
                  "(requisito 5)"),
            "C": ("ordine carico-primo per coppia, dichiarato nel piano; "
                  f"order_seed = {SEED} registrato su ogni blocco "
                  "(requisito 3)"),
            "D": ("baseline 3 pre + 3 post su ENTRAMBI i bracci (requisito 7); "
                  "cooldown intra-coppia carico->controllo via "
                  "initial_last_pre_w: scelta operativa, non requisito P4.4"),
            "E": ("precondizione di quiete PRIMA di ogni blocco (load e "
                  f"control): {QUIET_CONSECUTIVE} letture consecutive con "
                  "background_load=False, una rumorosa azzera il conteggio; "
                  f"tetto {QUIET_CAP_S:g} s poi SystemExit. Parametro di "
                  "esecuzione lato tool: il criterio F.12 non cambia"),
            "F": ("warm-up post-carico a CRITERIO MISURATO su DUE segnali "
                  "contemporanei, dopo ogni blocco di carico e prima del "
                  f"controllo della coppia: sulla finestra osservata di "
                  f"{WARMUP_WINDOW_S:g} s la potenza del contatore sta entro "
                  f"{WARMUP_TOLERANCE_W} W dalla baseline_pre_w del blocco "
                  "di carico E la media di finestra di cpu_percent sta sotto "
                  f"{WARMUP_CPU_MAX_PCT:g} %, per {WARMUP_SUSTAIN_S:g} s "
                  "CONTINUI; un campione fuori soglia su uno qualunque dei "
                  "due, o una lettura assente, azzera il tratto; la "
                  "disuguaglianza e' stretta su entrambi. Passo "
                  f"{WARMUP_STEP_S:g} s perche' la lettura di cpu_percent "
                  "sulla finestra e' anche il passo (come QUIET_POLL_S). Tetto "
                  f"{WARMUP_CAP_S:g} s poi SystemExit. Soglie PRE-REGISTRATE "
                  "sui dati della campagna 20261108, letti il 2026-11-09 da "
                  "experiment_results/p44_gate_20261108/"
                  "control_power_series.json e blocks_controllo.json, "
                  "riaggregati alla scala delle finestre del criterio: ogni "
                  "finestra dei cinque controlli stabilizzati sta sotto "
                  "0,3626 W dalla propria baseline e sotto 1,000 % di "
                  "cpu_percent; il transitorio (ctrl-1) da' 0,4802 W con "
                  "4,100 % alla prima finestra e 0,7951 W con 1,800 % alla "
                  "seconda, per cui ciascuna delle due soglie ne respinge "
                  "una finestra e sole le respingono entrambe. Temperatura "
                  "REGISTRATA all'ingresso e all'uscita (psutil "
                  "sensors_temperatures, poi MSAcpi_ThermalZoneTemperature "
                  "via CIM) ma NON criterio: su questo host il primo canale "
                  "non esiste e il secondo e' rimasto 3010 decikelvin su sei "
                  "letture a 5 s, quindi nessuna deriva e nessuna soglia "
                  "motivata. Il warm-up NON e' un controllo e non entra in "
                  "bias_w: duration, motivo, serie e letture mancanti "
                  "vanno in analysis.json, nel report e in "
                  "warmup_stabilizzazione.jsonl. Nessuna durata fissa: la "
                  "forma precedente sleep(10 s) non era ancorata a nessuna "
                  "misura ed era collocata PRIMA del carico, non dopo"),
            "G": (f"budget di soglia PRE-ESECUZIONE con procedura "
                  f"{BUDGET_MODE.upper()}: {BUDGET_N_TERNE} unita' per "
                  "gruppo (pre e post, non sovrapposti) lette da "
                  "read_idle_window_j alla scala del controllo e aggregate "
                  "da benchmark_v4.block_baseline (F.1/F.4). "
                  + ("Nessun fattore di scala da 30 s: il fondo e' misurato "
                     "su finestre di Tc."
                     if BUDGET_MODE == "short" else
                     f"Aggregato di "
                     f"{math.ceil(BUDGET_MATCHED_TARGET_S / DT_NOM_FROZEN)} "
                     "finestre Tc consecutive per unita' "
                     f"(somma(delta_j)/somma(dt_s) = "
                     f"{BUDGET_MATCHED_TARGET_S:g} s nominali): nessun "
                     "campione singolo vale come budget e nessun fattore "
                     "di scala.")
                  + " CodeCarbon non interviene ne' in correzione ne' in "
                    "calibrazione del budget: e' solo registro diagnostico "
                    "aperto dal flag --codecarbon"),
            "H": ("criterio che DECIDE, dichiarato PRIMA dei dati: "
                  f"{CRITERIO_PRIMARIO} = |bias_w| <= budget_base_w misurato "
                  "a scala Tc prima dei blocchi (check G), con il filtro e il "
                  "quorum di F.12. Il verdetto F.12 storico (mediana dei "
                  "budget per blocco da finestre da 30 s) resta calcolato e "
                  "riportato come " + CRITERIO_STORICO_F12 + ", NON decide. "
                  "Nessuna soglia del tipo budget + k * u_c: u_c non include "
                  "componenti gia' contenute nel budget. U = t * s / sqrt(n) "
                  "e |bias| + U <= budget sono grandezze riportate"),
        },
        "deviazioni_dichiarate": [
            f"{N_BLOCCHI} invocazioni = {N_BLOCCHI} preparazioni di stato "
            f"macchina (P1.4) e fino a {2 * N_BLOCCHI} warm-up (2 per "
            f"invocazione): costo non pagato dal disegno a {N_COPPIE} "
            "invocazioni",
            "le finestre idle pre/post del blocco control non sono contigue a "
            "quelle del carico: la coppia e' congiunta dal pair_id e dal "
            "cooldown propagato, non dalla contiguita' temporale",
            "prepare_model_state (i due warm-up) precede il cooldown: il "
            "warm-up scalda il motore prima di attendere il rientro a P_pre",
            "i parametri inerti del controllo (m, num_predict, use_nonce) non "
            "sono passati: valore_effectivo = default del runner, inerte per "
            "costruzione su range(0)",
        ],
        "dt_nominal_rule": ("3 x mediana(duration_s) su TUTTE righe valide del "
                            "pilot P2.9; DT_NOM = 2.930748 s, congelato prima "
                            "della campagna (requisito 5)"),
        "blocks": plan_blocks(),
        "outputs": {"results_csv": str(RESULTS_DIR / ROWS_NAME),
                    "block_summary_csv": str(RESULTS_DIR / BLOCKS_NAME)},
        "git_head": _git_head(),
        "runner_sha256": _sha256(MODULE_DIR / "benchmark_v4.py"),
    }


def cmd_plan(model: str) -> int:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    plan = plan_payload()
    # Un piano senza provenienza non e' un piano pre-registrato: e' un
    # documento che nessuno puo' collocare su una storia del codice. Il
    # fallimento di git va detto qui, all'atto della scrittura, perche' il
    # sintomo ritardo all'execute (guardia su git_head) accusa la storia di
    # essere stata riscritta, che e' un'altra cosa.
    if not plan["git_head"]:
        _, ragione = _git_provenienza()
        raise SystemExit(
            "il piano non puo' essere scritto: git non risponde a "
            f"rev-parse HEAD ({ragione or 'codice diverso da zero'}). "
            "Un plan.json senza git_head non ha provenienza e le guardie "
            "pre-flight non potrebbero deciderlo.")
    _scrittura_atomica(ARCHIVE_DIR / PLAN_NAME, plan)
    print("[OK] piano scritto:", ARCHIVE_DIR / PLAN_NAME)
    for b in plan["blocks"]:
        if b["arm"] == "load":
            dettagli = (f"m={b['m']} num_predict={b['num_predict']} "
                        f"nonce=on")
        else:
            dettagli = f"richieste=0 finestra={b['dt_nominal_s']} s"
        print(f"  [{b['index']:>2}] {b['label']:<12} {b['arm']:<7} "
              f"{b['pair_id']:<8} {dettagli}", flush=True)
    return 0


# ---------------------------------------------------------------------------
# Budget pre-esecuzione (Revisione del Gate 2026-11-09): il fondo di
# incertezza contro cui il bias del controllo va deciso e' MISURATO sulla
# scala del controllo, non ricavato per riscalatura del budget lungo. La
# forma B_short = B_long * (Tc / 30) e' stata rimossa: non e' una stima del
# fondo sulla scala breve, e' un coefficiente arbitrario applicato a una
# grandezza misurata su un'altra scala, e nessuna misura lo giustifica.
#
# Le due procedure ammesse (BUDGET_MODE) condividono il primitivo di lettura
# ``SESSION._source.read_idle_window_j(durata_s)`` -- lo stesso di
# ``calibrate_idle`` e di ``tools/audit_idle_p63.py``, quindi il contatore di
# package, non un integrale di campioni -- e la stessa regola di aggregazione
# del budget lungo: ``benchmark_v4.block_baseline`` (P1.5-P1.7, F.1/F.4),
# chiamata verbatim su terne di potenze.
#
#   short:   terne di finestre idle di durata nominale Tc (3 pre + 3 post),
#            budget = hypot(half_range_pre_w, half_drift_w) a scala Tc.
#   matched: N = ceil(BUDGET_MATCHED_TARGET_S / Tc) finestre Tc CONSECUTIVE
#            aggregate per gruppo in un aggregato la cui durata nominale
#            reacha i 30 s equivalenti; l'aggregato vale
#            somma(delta_j) / somma(dt_s), che e' la potenza dell'aggregato
#            e non la media delle potenze delle sue finestre; 3 aggregati pre
#            + 3 aggregati post, poi block_baseline verbatim. Un singolo
#            campione breve non e' mai il budget: il budget e' l'aggregato.
#
# In entrambi i casi: nessuna soglia, nessun coefficiente da 30 s a Tc, e
# CodeCarbon non interviene ne' in correzione ne' in calibrazione (e' solo
# registro diagnostico, ``--codecarbon``). Il numero si produce PRIMA dei
# blocchi e viene scritto nel suo artefatto; ``_verifica_piano`` ha gia'
# registrato la procedura nel piano.
# ---------------------------------------------------------------------------
def _sessione_misura():
    """La sessione energetica del runner, risolta alla chiamata.

    Non un'istanza locale: e' la stessa di ``benchmark_v4.SESSION`` che i
    blocchi usano, cosi' il fondo su cui si calcola la soglia e' letto dal
    canale che produrra' i joule dei controlli. Si risolve qui, e non si
    importa una volta, perche' il runner la sostituisce all'avvio del run.
    """
    return v4.SESSION


def _finestra_idle(sessione, durata_s: float, etichetta: str) -> Dict:
    """Una finestra idle di durata nominale ``durata_s`` letta dal contatore.

    ``read_idle_window_j`` ritorna ``None`` quando il canale non esprime una
    lettura: il budget e' una misura, quindi qui la campagna si ferma con la
    ragione, invece di degradare a un numero derivato da altro. Un delta
    negativo non viene clampato a zero (regola "nessun troncamento"): viene
    dichiarato e ferma la misura, perche' su una finestra idle un decremento
    del contatore non e' un fondo, e' un reset.
    """
    src = sessione._source
    lettura = src.read_idle_window_j(durata_s)
    if lettura is None:
        causa = getattr(src, "last_read_error", "") or (
            f"metodo attivo: {getattr(src, 'method', 'non dichiarato')!r} "
            "(nessun backend a contatore reale)")
        raise SystemExit(
            f"[BUDGET] finestra {etichetta}: nessun contatore di energia del "
            f"package leggibile ({causa}). Il budget pre-esecuzione e' una "
            "misura del fondo sulla scala del controllo: senza contatore la "
            "campagna non parte, e non viene usato niente al suo posto.")
    delta_j, dt_s, canale = lettura
    delta_j, dt_s = float(delta_j), float(dt_s)
    if not (math.isfinite(delta_j) and math.isfinite(dt_s)):
        raise SystemExit(
            f"[BUDGET] finestra {etichetta}: lettura non finita "
            f"(delta_j={delta_j!r}, dt_s={dt_s!r}).")
    if dt_s <= 0.0:
        raise SystemExit(
            f"[BUDGET] finestra {etichetta}: dt_s={dt_s} non positivo; una "
            "finestra senza durata non ha potenza.")
    if delta_j < 0.0:
        raise SystemExit(
            f"[BUDGET] finestra {etichetta}: contatore decrescente "
            f"(delta_j={delta_j:.6f} J su {dt_s:.6f} s). Su una finestra idle "
            "un decremento e' un reset del registro, non un fondo: il valore "
            "non si clampa e la misura si ferma.")
    return {"label": etichetta, "delta_j": delta_j, "dt_s": dt_s,
            "power_w": delta_j / dt_s, "channel": canale,
            "durata_nominale_s": float(durata_s)}


def _gruppo_finestre(sessione, durata_s: float, n: int,
                     etichetta: str) -> List[Dict]:
    """n finestre idle consecutive, stessa durata nominale."""
    return [_finestra_idle(sessione, durata_s, f"{etichetta}-{i + 1}")
            for i in range(int(n))]


def _aggregato_consecutivo(finestre: List[Dict], etichetta: str) -> Dict:
    """Potenza di un aggregato di finestre consecutive.

    ``somma(delta_j) / somma(dt_s)``: l'energia totale divisa il tempo totale.
    NON e' la media delle potenze delle finestre -- le finestre hanno durate
    osservate diverse e una media semplice darebbe peso uguale a campioni di
    durata diversa, mentre qui l'aggregato conta per la sua energia.
    """
    delta = sum(f["delta_j"] for f in finestre)
    dt = sum(f["dt_s"] for f in finestre)
    if dt <= 0.0:
        raise SystemExit(f"[BUDGET] aggregato {etichetta}: dt totale {dt}")
    return {"label": etichetta, "power_w": delta / dt, "delta_j": delta,
            "dt_s": dt,
            "durata_nominale_s": sum(f["durata_nominale_s"] for f in finestre),
            "n_finestre": len(finestre),
            "finestre": [f["label"] for f in finestre],
            "canali": sorted({str(f["channel"]) for f in finestre})}


def _budget_da_termine(b: Dict, etichetta: str) -> float:
    """``budget_base_w`` di ``block_baseline``, pretendendo il numero.

    ``block_baseline`` lascia le celle non calcolabili vuote (non zero): se
    la cella del budget e' vuota significa che le terne non erano terne, e
    procedere con un budget assente sarebbe decidere il gate senza soglia.
    """
    valore = b.get("budget_base_w")
    if valore == "" or valore is None:
        raise SystemExit(
            f"[BUDGET] {etichetta}: block_baseline non ha prodotto "
            "budget_base_w (terna non completa). Il gate non parte senza "
            "soglia misurata.")
    return float(valore)


def _calcola_budget_pre_esecuzione(mode: str, sessione) -> Tuple[float, Dict]:
    """Budget del gate misurato PRIMA dei blocchi, alla scala del controllo.

    Ritorna ``(budget_w, dettagli)``. ``budget_w`` e' in watt, come il
    ``bias_w`` di F.12 e come i ``budget_base_w`` per blocco: nessuna
    conversione fra scale, quindi nessuna riscalatura.
    """
    if mode not in ("short", "matched"):
        raise SystemExit(
            f"[BUDGET] BUDGET_MODE = {mode!r} non ammesso: le procedure "
            "pre-registrate sono 'short' e 'matched'.")
    tc = float(DT_NOM_FROZEN)
    if tc <= 0.0:
        raise SystemExit(f"[BUDGET] DT_NOM_FROZEN = {tc} non positivo")
    if tc < BUDGET_FLOOR_FINESTRA_S:
        raise SystemExit(
            f"[BUDGET] Tc = {tc:g} s sotto il pavimento del primitivo "
            f"({BUDGET_FLOOR_FINESTRA_S:g} s, energy_session.py:672): la "
            "finestra breve non esiste su questo canale. La procedura a "
            "scala Tc non e' eseguibile e non si accettano i 0,5 s del "
            "pavimento come se fossero Tc.")
    n_terne = int(BUDGET_N_TERNE)
    if n_terne < 2:
        raise SystemExit(
            f"[BUDGET] BUDGET_N_TERNE = {n_terne}: una semi-ampiezza su un "
            "solo campione non e' una misura di dispersione")

    canali: set = set()
    if mode == "short":
        pre = _gruppo_finestre(sessione, tc, n_terne, "pre")
        post = _gruppo_finestre(sessione, tc, n_terne, "post")
        unita_pre, unita_post = pre, post
        n_per_aggregato = 1
        durata_aggregato_s = tc
        n_finestre_totali = len(pre) + len(post)
    else:
        n_per_aggregato = max(2, math.ceil(
            float(BUDGET_MATCHED_TARGET_S) / tc))
        unita_pre, unita_post = [], []
        pre, post = [], []
        for g in range(n_terne):
            chunk_pre = _gruppo_finestre(sessione, tc, n_per_aggregato,
                                         f"pre-g{g + 1}")
            pre.extend(chunk_pre)
            unita_pre.append(_aggregato_consecutivo(
                chunk_pre, f"agg-pre-{g + 1}"))
        for g in range(n_terne):
            chunk_post = _gruppo_finestre(sessione, tc, n_per_aggregato,
                                          f"post-g{g + 1}")
            post.extend(chunk_post)
            unita_post.append(_aggregato_consecutivo(
                chunk_post, f"agg-post-{g + 1}"))
        durata_aggregato_s = n_per_aggregato * tc
        n_finestre_totali = len(pre) + len(post)

    for f in pre + post:
        canali.add(str(f["channel"]))
    if len(canali) > 1:
        raise SystemExit(
            f"[BUDGET] canali misti nella misura del fondo: {sorted(canali)}. "
            "Un budget composto da letture di origine diversa non e' una "
            "misura, e non si decide una soglia con esso.")

    b = v4.block_baseline([f["power_w"] for f in unita_pre],
                          [f["power_w"] for f in unita_post])
    budget_w = _budget_da_termine(b, mode)

    dettagli = {
        "budget_mode": mode,
        "tc_duration_s": tc,
        "n_terne": n_terne,
        "n_per_aggregato": n_per_aggregato,
        "durata_aggregato_s": durata_aggregato_s,
        "n_finestre_usate": n_finestre_totali,
        "durata_totale_misura_s": n_finestre_totali * tc,
        "canale": sorted(canali)[0],
        "finestre_pre": pre,
        "finestre_post": post,
        "unita_pre_w": [f["power_w"] for f in unita_pre],
        "unita_post_w": [f["power_w"] for f in unita_post],
        "baseline": b,
        "budget_base_w": budget_w,
        "regola_aggregazione": (
            "benchmark_v4.block_baseline (P1.5-P1.7, F.1/F.4) chiamata "
            "verbatim sulle unita' di durata "
            + ("Tc" if mode == "short" else "aggregato")
            + "; pre_range/2 e |dP|/2 in quadratura"),
        "scala_30_s_applicata": False,
        "codecarbon_usato": False,
        "assunzioni": [
            "il fondo e' letto dal contatore di package "
            "(read_idle_window_j), lo stesso canale di calibrate_idle e "
            "dell'audit P6.3: non e' un integrale di campioni",
            f"le {n_terne} unita' pre e le {n_terne} post sono misurate in "
            "due gruppi consecutivi non sovrapposti: dP e' la deriva fra i "
            "due gruppi, come in P1.5, e non si assume nulla",
            "un delta negativo o una lettura assente fermano la misura: "
            "nessun clamp a zero e nessuna degradazione silenziosa",
            "budget_base_w e' un proxy conservativo di incertezza standard, "
            "non una deviazione standard (P4.12: con n = 3 non si stima "
            "una varianza) e la quadratura non e' un limite massimo "
            "garantito (P1.7)",
            "la procedura e' pre-registrata nel piano (budget_mode) e "
            "verificata da _verifica_piano PRIMA di qualunque misura",
        ],
    }
    if mode == "matched":
        dettagli["aggregati_pre"] = unita_pre
        dettagli["aggregati_post"] = unita_post
        dettagli["assunzioni"].append(
            f"aggregato = {n_per_aggregato} finestre Tc consecutive, "
            f"somma(delta_j)/somma(dt_s) = {durata_aggregato_s:.3f} s "
            f"nominali (obiettivo "
            f"{BUDGET_MATCHED_TARGET_S:g} s): nessun campione singolo vale "
            "come budget")
    return budget_w, dettagli


def _scrivi_budget_preregistrato(budget_w: float, dettagli: Dict) -> Path:
    """L'artefatto della soglia: nasce prima dei blocchi, e il nome lo dice."""
    payload = {"budget_preregistrato": {
        "budget_base_w": budget_w,
        "calcolato_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(
            timespec="seconds"),
        **dettagli}}
    _scrittura_atomica(ARCHIVE_DIR / BUDGET_PREREG_NAME, payload)
    return ARCHIVE_DIR / BUDGET_PREREG_NAME


# ---------------------------------------------------------------------------
# Incertezza e criterio di decisione (revisione 2026-11-09, secondo giro).
#
# Cosa DECIDE. Il criterio primario e' |bias_w| <= budget_base_w, con il
# budget MISURATO a scala Tc prima dei blocchi (pre-registrato) e con il
# filtro/quorum di F.12. E' dichiarato in plan.json come ``criterio_primario``
# e verificato da ``_verifica_piano``. Il verdetto F.12 storico (mediana dei
# budget per blocco, derivati da finestre da 30 s) resta calcolato e riportato
# accanto ma NON decide: la differenza fra i due e' il mismatch di scala fra
# budget (30 s) e controllo (2,93 s) che la revisione ha individuato.
#
# Cosa NON c'e' piu'. La forma S = budget + k * u_c e' RIMOSSA. u_rumore e
# u_termico erano gli stessi due termini di cui e' fatto budget_base_w
# (= hypot(half_range_pre_w, half_drift_w)): quindi u_c >= budget e S >= 3 *
# budget, cioe' la stessa dispersione contata due volte. Con i numeri delle
# due campagne fallite la soglia sarebbe diventata >= 0,787 W contro un bias
# di 0,480 W, e >= 0,354 W contro 0,125 W: entrambe sarebbero passate. Anche
# u_A come semi-ampiezza (max - min) / 2 e' rimosso: un range cresce con il
# numero di coppie e renderebbe il gate piu' facile con 12 coppie che con 6.
# L'incertezza di tipo A della media dei controlli e' s / sqrt(n) (GUM,
# JCGM 100:2008, 4.2).
#
# Cosa resta. Ogni componente dichiara valore, tipo (A/B), se e' INCLUSA in
# u_c, il motivo, la formula e la fonte (vedi gate_uncertainty.py). Le
# componenti escluse restano nel report con il loro valore informativo e la
# ragione dell'esclusione: escludere non e' tacere. u_c e' la somma in
# quadratura delle sole componenti incluse. Prima dei controlli non ne esiste
# nessuna (None, non zero); dopo i controlli esiste u_A = s / sqrt(n).
# L'incertezza estesa U = t(0,975, n-1) * u_c e l'accettazione con banda di
# guardia (|bias| + U <= budget, JCGM 106:2012) sono GRANDEZZE RIPORTATE, non
# il criterio. CodeCarbon non interviene su nessuna componente.
# ---------------------------------------------------------------------------
CRITERIO_PRIMARIO = "bias_vs_budget_tc"
CRITERIO_STORICO_F12 = "f12_mediana_budget_per_blocco_30s"


def _deviazione_allineamento(unita: List[Dict]) -> float:
    """Massimo scostamento fra durata osservata e nominale di un'unita'.

    Semi-ampiezza conservativa, non deviazione standard: con poche unita' non
    si stima una varianza (P4.12) e qui serve un bordo, non una sigma.
    """
    deviations = [abs(float(u["dt_s"]) - float(u["durata_nominale_s"]))
                  for u in unita]
    if not deviations:
        raise SystemExit("[U_C] nessuna unita' misurata: niente allineamento")
    return max(deviations)


def _incertezza_pre_esecuzione(dettagli_budget: Dict,
                               risoluzione_timer_s: Optional[float]) -> Dict:
    """u_c pre-esecuzione con le sue componenti tracciabili.

    Il denominatore delle componenti temporali e' la durata osservata minima
    delle unita' del fondo: usare il minimo rende la conversione la piu'
    sfavorevole delle osservate, quindi conservativa; il valore assoluto della
    potenza da scalare e' la baseline del fondo stesso (mediana delle unita'
    pre), perche' e' quella la potenza su cui l'errore di tempo agisce.
    """
    b = dettagli_budget["baseline"]
    # Le unita' cui applicare le componenti temporali sono quelle che sono
    # entrate in block_baseline: in 'short' le finestre Tc lette dal
    # contatore, in 'matched' gli aggregati consecutivi. Non le finestre
    # singole del matched, perche' li' il denominatore di ogni potenza e'
    # la somma dei dt dell'aggregato.
    if dettagli_budget["budget_mode"] == "matched":
        unita = (list(dettagli_budget["aggregati_pre"])
                 + list(dettagli_budget["aggregati_post"]))
    else:
        unita = (list(dettagli_budget["finestre_pre"])
                 + list(dettagli_budget["finestre_post"]))
    fondo_w = float(b["baseline_pre_w"])
    dt_min_s = min(float(u["dt_s"]) for u in unita)
    dev_allineamento_s = _deviazione_allineamento(unita)

    componenti: Dict[str, Dict] = {}
    durata_unita_s = (float(dettagli_budget["durata_aggregato_s"])
                      if dettagli_budget["budget_mode"] == "matched"
                      else float(dettagli_budget["tc_duration_s"]))
    componenti["u_rumore"] = {
        "value": float(b["half_range_pre_w"]),
        "tipo": "A",
        "inclusa": False,
        "motivo": ("gia' contenuta in budget_base_w = hypot(u_rumore, "
                   "u_termico): includerla in u_c conterebbe due volte la "
                   "stessa dispersione e porterebbe la soglia a >= 3 * budget"),
        "formula": "half_range_pre_w = (max - min) / 2 sulle unita' pre",
        "fonte": (f"misura del fondo pre-esecuzione ({dettagli_budget['budget_mode']}), "
                  f"{dettagli_budget['n_terne']} unita' di "
                  f"{durata_unita_s:g} s nominali, canale "
                  f"{dettagli_budget['canale']}"),
    }
    componenti["u_termico"] = {
        "value": float(b["half_drift_w"]),
        "tipo": "A",
        "inclusa": False,
        "motivo": ("nome storico: e' la deriva fra i due gruppi di finestre, "
                   "non un margine termico (nessun canale termico e' usato "
                   "come criterio); gia' contenuta in budget_base_w, quindi "
                   "esclusa dal conto per non contarla due volte"),
        "formula": "half_drift_w = |mediana(post) - mediana(pre)| / 2",
        "fonte": ("stessa misura del fondo: i due gruppi non sovrapposti "
                  "dell'attesa di stabilizzazione, come P1.5"),
    }
    if risoluzione_timer_s is None:
        componenti["u_timer"] = {
            "value": None,
            "tipo": "B",
            "inclusa": False,
            "motivo": ("non misurabile su questo host: resta assente e non "
                       "vale zero; comunque non sarebbe inclusa (vedi sotto)"),
            "formula": None,
            "fonte": ("probe_cpu_time_resolution non misurabile su questo "
                      "host: la componente resta assente, non vale zero"),
        }
        u_timer = None
    else:
        u_timer = fondo_w * (float(risoluzione_timer_s) / 2.0) / dt_min_s
        componenti["u_timer"] = {
            "value": u_timer,
            "tipo": "B",
            "inclusa": False,
            "motivo": ("la risoluzione dei cpu_times e' il clock dell'attribuzione "
                       "CPU, non quello della finestra del contatore: "
                       "E_net,control usa il dt_W degli stessi bordi del "
                       "contatore (benchmark_v4._run_control_window), quindi "
                       "questo valore e' informativo e non entra in u_c"),
            "formula": ("P_fondo * (mezza risoluzione dei cpu_times) / "
                        "min(dt osservato): l'errore di tempo agisce sul "
                        "denominatore della potenza"),
            "fonte": (f"CasualWattLocalEnergyProfiler.probe_cpu_time_resolution()"
                      f" = {float(risoluzione_timer_s):.4f} s, stesso "
                      "chiamante del runner (benchmark_v4.py:2635)"),
        }
    u_all = fondo_w * dev_allineamento_s / dt_min_s
    componenti["u_allineamento"] = {
        "value": u_all,
        "tipo": "B",
        "inclusa": False,
        "motivo": ("E_net,control sottrae P_pre * dt_W con il dt_W osservato "
                   "dalla stessa coppia di bordi del contatore "
                   "(benchmark_v4._run_control_window, requisito 5): lo "
                   "scarto fra durata nominale e osservata non genera bias; "
                   "valore informativo, non incluso in u_c"),
        "formula": ("P_fondo * max|dt_osservato - dt_nominale| / "
                    "min(dt osservato): bordo temporale fra finestra chiesta "
                    "e finestra effettivamente letta dal contatore"),
        "fonte": (f"unita' della misura del fondo: {len(unita)} unita', "
                  f"deviazione massima {dev_allineamento_s:.6f} s su "
                  f"nominale {durata_unita_s:g} s"),
    }

    # Nessuna componente indipendente dal budget e' calcolabile prima dei
    # controlli: u_c e' None (non zero) e la soglia pre-registrata del criterio
    # primario e' il budget a scala Tc, senza maggiorazioni.
    u_c = gu.combina_incluse(componenti)
    budget_w = float(dettagli_budget["budget_base_w"])
    return {
        "quando": "pre_esecuzione",
        "criterio": CRITERIO_PRIMARIO,
        "u_c": u_c,
        "k": None,
        "U_w": None,
        "budget_base_w": budget_w,
        "soglia_w": budget_w,
        "nota_u_c": ("nessuna componente indipendente dal budget e' "
                     "calcolabile prima dei controlli: u_c = None, non zero; "
                     "la soglia del criterio primario e' il budget a scala Tc"),
        "componenti": componenti,
        "u_A": None,
        "nota_u_A": ("non calcolabile prima dei controlli: richiede le potenze "
                     "nette dei blocchi di controllo, che non esistono ancora"),
        "codecarbon_usato": False,
    }


def _potenze_netta_dei_controlli(controls: Sequence[Mapping]) -> List[float]:
    """E_net/dt_W per ogni controllo utilizzabile, in watt.

    Sono i controlli DI F.12, con lo stesso filtro `usable` gia' applicato
    dal gate: la dispersione non si calcola su una popolazione diversa da
    quella che ha prodotto il bias, perche' due insiemi diversi darebbero
    due numeri non confrontabili fra loro.
    """
    out: List[float] = []
    for c in controls:
        if not c.get("usable"):
            continue
        try:
            dt = float(c.get("dt_w_s"))
            e = float(c.get("e_net_j"))
        except (TypeError, ValueError):
            continue
        if dt > 0.0 and math.isfinite(dt) and math.isfinite(e):
            out.append(e / dt)
    return out


def _incertezza_con_au_controlli(pre: Dict, controls: Sequence[Mapping]) -> Dict:
    """u_c post-controlli: la componente u_A, tipo A, e il suo fattore t.

    u_A = s / sqrt(n) e' l'incertezza di tipo A della MEDIA delle potenze nette
    dei controlli utilizzabili (GUM, JCGM 100:2008, 4.2): decresce con n, a
    differenza di un range (max - min), che cresce con n. L'unita' statistica
    e' il blocco di controllo, non la terna di baseline di P4.12 (dove a n = 3
    il divieto di stimare una varianza resta). U = t(0,975, n-1) * u_c e'
    grandezza riportata: la soglia del criterio primario resta il budget a
    scala Tc e non viene maggiorata.
    """
    potenze = _potenze_netta_dei_controlli(controls)
    stats = _statistiche_descrittive(potenze)
    u_a = stats["se"]          # s / sqrt(n); None se n < 2 (mai zero)
    if u_a is None:
        fonte_a = (f"controlli utilizzabili con dt_W valido: {len(potenze)}; "
                   "serve almeno una coppia di blocchi per una dispersione "
                   "fra blocchi")
    else:
        fonte_a = (f"potenze nette dei {len(potenze)} controlli utilizzabili: "
                   f"media {stats['media']:.6f} W, sd campionaria (ddof=1) "
                   f"{stats['sd']:.6f} W, s / sqrt(n) = {u_a:.6f} W")
    componenti = dict(pre["componenti"])
    componenti["u_A"] = {
        "value": u_a,
        "tipo": "A",
        "inclusa": u_a is not None,
        "motivo": ("incertezza di tipo A della media dei controlli: decresce "
                   "con n, a differenza di un range. Indipendente dal "
                   "budget (derivato dal fondo, non dai controlli)"
                   if u_a is not None else
                   "non calcolabile: servono almeno due controlli utilizzabili"),
        "formula": ("s / sqrt(n) sulle potenze nette dei controlli "
                    "utilizzabili (s campionaria, ddof=1)"),
        "fonte": fonte_a,
    }
    u_c = gu.combina_incluse(componenti)
    k = stats["t_quantile"] if u_c is not None else None
    return {
        "quando": "post_controlli",
        "criterio": CRITERIO_PRIMARIO,
        "u_c": u_c,
        "k": k,
        "k_provenienza": (f"t di Student 0,975 con {len(potenze) - 1} gradi di "
                          f"liberta': {stats['t_provenienza']}"
                          if k is not None else "nessun fattore: u_c assente"),
        "U_w": (k * u_c) if (k is not None and u_c is not None) else None,
        "budget_base_w": pre["budget_base_w"],
        "soglia_w": pre["budget_base_w"],
        "componenti": componenti,
        "u_A": u_a,
        "potenze_nette_w": potenze,
        "codecarbon_usato": False,
    }


def _risoluzione_timer_sessione() -> Optional[float]:
    """Il tick dei cpu_times MISURATO, con la stessa chiamata del runner.

    Non un numero d'esempio: il valore e' osservato su questo host, e None
    vuol dire "non misurabile", che nella somma in quadratura resta assente.
    """
    try:
        val = v4.CasualWattLocalEnergyProfiler.probe_cpu_time_resolution()
    except Exception:  # noqa: BLE001 - non misurabile e' un esito, non un guasto
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) and f > 0.0 else None


def _verdetto_primario(analysis: Mapping, budget_w: float) -> Dict:
    """Il verdetto che DECIDE: |bias_w| <= budget a scala Tc, con il quorum.

    Dichiarato nel piano come ``criterio_primario`` PRIMA dei dati. Condivide
    con F.12 il filtro dei controlli e il quorum (``evaluate_gate`` li ha
    gia' applicati: se il gate non e' eseguibile, nemmeno questo lo e');
    cambia solo la soglia, che e' il budget misurato alla scala del controllo
    invece della mediana dei budget per blocco derivati da finestre da 30 s.
    Il verdetto F.12 storico non si tocca e viaggia in ``f12_status``.
    """
    status_f12 = analysis.get("status")
    bias = analysis.get("bias_w")
    base = {"criterio": CRITERIO_PRIMARIO, "soglia_w": float(budget_w),
            "bias_w": bias, "quorum": analysis.get("quorum"),
            "controls_usable_n": analysis.get("controls_usable_n"),
            "f12_status": status_f12,
            "criterio_storico_riportato": CRITERIO_STORICO_F12}
    bias_finito = (bias is not None and math.isfinite(float(bias)))
    if status_f12 == "not-executable" or not bias_finito:
        return {**base, "status": "not-executable", "margine_w": None,
                "motivo": "gate non eseguibile (filtro/quorum di F.12): nessun "
                          "bias da confrontare con il budget"}
    margine = float(budget_w) - abs(float(bias))
    ok = margine >= 0.0
    return {**base, "status": "pass" if ok else "fail", "margine_w": margine,
            "motivo": (f"|bias_w| = {abs(float(bias)):.6f} W "
                       f"{'<=' if ok else '>'} budget_base_w a scala Tc = "
                       f"{float(budget_w):.6f} W")}


def _accettazione_guardata(bias_w, post: Mapping, budget_w: float) -> Dict:
    """|bias| + U <= budget: regola con banda di guardia (JCGM 106:2012).

    GRANDEZZA RIPORTATA, non il criterio: dice se il risultato resterebbe
    conforme anche tenendo conto dell'incertezza della stima del bias.
    """
    u = post.get("U_w")
    if bias_w is None or u is None:
        return {"accettata": None, "bias_assoluto_w": None, "U_w": u,
                "bias_piu_U_w": None, "budget_base_w": float(budget_w),
                "nota": "bias o U non calcolabili: nessuna accettazione "
                        "guardata. Grandezza riportata, non decide."}
    totale = abs(float(bias_w)) + float(u)
    return {"accettata": totale <= float(budget_w),
            "bias_assoluto_w": abs(float(bias_w)), "U_w": float(u),
            "bias_piu_U_w": totale, "budget_base_w": float(budget_w),
            "nota": "|bias| + U <= budget (JCGM 106:2012). Grandezza "
                    "riportata, non decide l'esito del gate."}


def _verifica_piano() -> Dict:
    """Il piano eseguito deve essere quello dichiarato, non una sua riedizione."""
    path = ARCHIVE_DIR / PLAN_NAME
    if not path.exists():
        raise SystemExit("nessun plan.json: lanciare prima `plan`")
    with path.open(encoding="utf-8") as fh:
        plan = json.load(fh)
    if (plan.get("n_coppie") != N_COPPIE
            or plan.get("n_blocchi") != N_BLOCCHI):
        raise SystemExit(
            f"il piano dichiara {plan.get('n_coppie')} coppie / "
            f"{plan.get('n_blocchi')} blocchi, il tool ne chiede "
            f"{N_COPPIE} / {N_BLOCCHI}: --pairs diverso dal disegno "
            "dichiarato. Ritirare plan.json e ripianificare PRIMA di misurare.")
    dichiarati = plan_blocks()
    if plan.get("blocks") != dichiarati:
        raise SystemExit(
            "il piano dichiarato non coincide con plan_blocks() del codice: "
            "il tool e' cambiato DOPO la dichiarazione. Ritirare plan.json e "
            "ripianificare PRIMA di misurare.")
    # SEED e' il valore passato (--seed), non una costante: il piano deve
    # coincidere con il seme dichiarato al plan, qualunque esso sia.
    if plan.get("order_seed") != SEED or plan.get("model") != DEFAULT_MODEL:
        raise SystemExit("seed o modello discostati dal piano dichiarato")
    attesi = {
        "quiet_consecutive": QUIET_CONSECUTIVE,
        "quiet_cap_s": QUIET_CAP_S,
        "warmup_tolerance_w": WARMUP_TOLERANCE_W,
        "warmup_cpu_max_pct": WARMUP_CPU_MAX_PCT,
        "warmup_sustain_s": WARMUP_SUSTAIN_S,
        "warmup_cap_s": WARMUP_CAP_S,
        "warmup_step_s": WARMUP_STEP_S,
        "warmup_window_s": WARMUP_WINDOW_S,
        "budget_mode": BUDGET_MODE,
        "budget_n_terne": BUDGET_N_TERNE,
        "budget_matched_target_s": BUDGET_MATCHED_TARGET_S,
        "criterio_primario": CRITERIO_PRIMARIO,
    }
    discosti = {chiave: (plan.get(chiave), valore)
                for chiave, valore in attesi.items()
                if plan.get(chiave) != valore}
    if discosti:
        raise SystemExit(
            "precondizione di quiete, warm-up o procedura di budget assenti "
            "o diversi dal piano dichiarato (dichiarato/atteso: "
            + ", ".join(f"{c}: {p!r}/{a!r}"
                        for c, (p, a) in discosti.items()) + "): "
            "il plan precede l'introduzione di questi parametri (o e' stato "
            "cambiato dopo). Ritirare plan.json e ripianificare PRIMA di "
            "misurare.")
    # Guardie pre-flight (2026-11-08): il piano deve essere quello della
    # campagna richiesta, il runner quello dichiarato, e il percorso di
    # misura invariato dalla dichiarazione. Ognuna si ferma PRIMA di
    # misurare; nessuna e' un avviso.
    if plan.get("campaign_date") != P44_DATE:
        raise SystemExit(
            f"il piano dichiara la campagna {plan.get('campaign_date')}, "
            f"execute chiede {P44_DATE}: un piano spostato di archivio non "
            "e' il piano di questa campagna. Ritirare plan.json e "
            "ripianificare con la data del run PRIMA di misurare.")
    sha_attuale = _sha256(MODULE_DIR / "benchmark_v4.py")
    if plan.get("runner_sha256") != sha_attuale:
        raise SystemExit(
            "benchmark_v4.py ha SHA-256 diverso da quello registrato nel "
            f"piano (piano={plan.get('runner_sha256')}, attuale="
            f"{sha_attuale}): il percorso di misura e' cambiato dopo la "
            "dichiarazione. Il vincolo e' bloccante: ritirare plan.json e "
            "ripianificare PRIMA di misurare, oppure ripristinare il "
            "runner dichiarato.")
    head_dichiarato = plan.get("git_head") or ""
    if not head_dichiarato:
        raise SystemExit(
            "git_head del piano assente: il piano non porta la testa del "
            "repository al momento della scrittura, quindi la guardia non ha "
            "un termine di confronto. Mi fermo PRIMA di misurare.")
    if not _git_antenato(head_dichiarato):
        # La sola chiamata a git serve per dire PERCHE': il booleano non
        # distingue "git risponde che non lo e'" da "git non parte", e le
        # due cose hanno colpevoli diversi. Il run si ferma comunque.
        _, ragione = _git_antenato_con_ragione(head_dichiarato)
        accusa = (ragione if ragione.startswith("git non eseguibile") else
                  "la storia e' stata riscritta o il piano arriva da un altro "
                  "repository")
        raise SystemExit(
            f"git_head del piano ({head_dichiarato}) non risulta antenato di "
            f"HEAD ({accusa}). Mi fermo PRIMA di misurare.")
    mutato = _git_percorso_misura_mutato(head_dichiarato)
    if mutato is None:
        raise SystemExit(
            "git non risponde sul confronto del percorso di misura fra "
            f"{head_dichiarato} e HEAD: la guardia non e' decidibile e non "
            "passa in silenzio. Mi fermo PRIMA di misurare.")
    if mutato:
        raise SystemExit(
            "il percorso di misura (benchmark_v4.py, energy/) e' cambiato "
            f"fra il git_head del piano ({head_dichiarato}) e HEAD: il "
            "piano dichiara un altro percorso. Estensioni neutre al tool "
            "del gate sono ammesse, al percorso di misura no. Ritirare "
            "plan.json e ripianificare PRIMA di misurare.")
    return plan


def _ultima_baseline_pre(path: Path) -> Optional[float]:
    """L'ultima baseline_pre_w scritta, o None se non c'e'/non e' finita."""
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8-sig") as fh:
        righe = list(csv.DictReader(fh))
    if not righe:
        return None
    try:
        valore = float(righe[-1].get("baseline_pre_w", ""))
    except (TypeError, ValueError):
        return None
    return valore if valore == valore and valore > 0.0 else None


def _filtra_controlli(catturati: List[Dict]) -> List[Mapping]:
    """I riepiloghi completi dei soli blocchi di controllo, notes escluse.

    Sono i dizionari che il runner passa a ``export_summary_csv`` PRIMA che
    lo schema P5 congeli le colonne: contengono i campi ``control_*`` che
    ``evaluate_gate`` legge e che il CSV consegnato non porta.
    """
    out = []
    for rec in catturati:
        if str(rec.get("block_kind", "") or "") == "control":
            c = dict(rec)
            c.pop("notes", None)
            out.append(c)
    if not out:
        raise SystemExit(
            "nessun riepilogo di blocco di controllo catturato: gate non "
            "eseguito")
    return out


def _call_kwargs(b: Dict, initial_pre: Optional[float],
                 rows_path: Path, blocks_path: Path) -> Tuple[Dict, Dict]:
    kw = dict(
        blocks_per_point=BLOCKS_PER_POINT,
        num_ctx=NUM_CTX, temperature=config.DEFAULT_TEMPERATURE,
        timeout_s=config.DEFAULT_TIMEOUT_S,
        batch_id=f"p44-{b['label']}",
        block_kind=b["arm"], pair_id=b["pair_id"], order_seed=SEED,
        dt_nominal_s=str(DT_NOM_FROZEN),
        max_invalidated_blocks=K_MAX,
        substitution_seed=f"p44-{b['label']}",
        initial_last_pre_w=initial_pre,
        results_path=rows_path, block_summary_path=blocks_path,
        on_log=lambda m: print(m, flush=True))
    if b["arm"] == "load":
        kw.update(m=b["m"], num_predict=b["num_predict"],
                  use_nonce=b["use_nonce"])
    prompt = {"id": b["prompt_id"], "text": b["text"],
              "answer_type": "auto", "source": b["source"]}
    return kw, prompt


def _cattura_riepiloghi():
    """Mod (non monkeypatch permanente) di ``export_summary_csv``: passa al
    writer reale e trattiene una copia del riepilogo COMPLETO — con i campi
    ``control_*`` che lo schema P5 scarterebbe. E' l'unico momento in cui il
    chiamante di ``run_v4_benchmark`` li vede interi."""
    reale = v4.export_summary_csv
    catturati: List[Dict] = []

    def wrapper(records, path, columns, mode="a"):
        n = reale(records, path, columns, mode=mode)
        for rec in records:
            catturati.append(dict(rec))
        return n

    return reale, wrapper, catturati


_MANCANTE = object()


def _campione_dict(s) -> Dict:
    """``SystemSample`` -> dict JSON-safe. I pid sono interi, nessun oggetto
    vivo entra nell'artefatto; un campione senza ``package_energy_j`` resta
    None (cella non misurata, non zero)."""
    try:
        d = asdict(s)
    except TypeError:
        d = dict(vars(s))
    d["ollama_pids"] = [int(p) if isinstance(p, (int, float)) else str(p)
                        for p in d.get("ollama_pids", ()) or ()]
    return d


def _serie_potenza(campioni: List[Dict]) -> List[Dict]:
    """Potenza media fra campioni consecutivi: ``ΔE_pkg/Δt`` del contatore
    cumulativo. E' la grandezza che dice se il bias di un controllo e' una
    deriva lenta o un picco; i bordi interpolati da ``samples_between``
    coprono l'intera finestra. Un intervallo con contatore assente o dt<=0
    non produce un numero."""
    out: List[Dict] = []
    for a, b in zip(campioni, campioni[1:]):
        ea, eb = a.get("package_energy_j"), b.get("package_energy_j")
        try:
            dt = float(b["t"]) - float(a["t"])
        except (TypeError, ValueError, KeyError):
            continue
        if ea is None or eb is None or dt <= 0.0:
            continue
        de = float(eb) - float(ea)
        out.append({"t_start": a["t"], "t_end": b["t"], "dt_s": dt,
                    "de_j": de, "power_w": de / dt})
    return out


def _cattura_serie_controllo():
    """Wrapper di ``_run_control_window``: passa al runner reale e salva la
    serie di potenza grezza della finestra passiva, che il runner non
    scrive da nessuna parte (il riepilogo porta solo gli aggregati).

    Metodo: durante la sola finestra passiva la sessione e' quella di
    produzione e ``_run_control_window`` legge esattamente due bordi. Il
    wrapper trattiene quei due bordi (con l'istante monotono subito dopo
    la lettura), ricostruisce ``[t0, t1]`` con la stessa espressione del
    runner (``t_counter_mono`` del primo bordo, monotono dopo il secondo)
    e chiede ``samples_between(t0, t1)`` — gli stessi campioni che il
    sampler ha gia' raccolto, nessuna lettura in piu' sul contatore.
    L'unico overhead e' un ``time.monotonic()`` per bordo.

    La serie e' DIAGNOSTICA: non entra nel criterio F.12 e non cambia
    nessuna quantita' misurata. Se i campioni mancano, l'artefatto lo
    dichiara con la ragione, non inventa una serie.
    """
    reale = v4._run_control_window
    catturate: List[Dict] = []

    def wrapper(*, block_id, durata_s, profiler, p_pre,
                stop_event=None, log=None):
        sessione = v4.SESSION
        bordi: List[Tuple[Dict, float]] = []
        proprio = sessione.__dict__.get("read_measurement_edge", _MANCANTE)
        reale_edge = sessione.read_measurement_edge

        def edge_wrapper(**kw):
            e = reale_edge(**kw)
            bordi.append((e, time.monotonic()))
            return e

        sessione.read_measurement_edge = edge_wrapper
        try:
            rec = reale(block_id=block_id, durata_s=durata_s,
                        profiler=profiler, p_pre=p_pre,
                        stop_event=stop_event, log=log)
        finally:
            if proprio is _MANCANTE:
                sessione.__dict__.pop("read_measurement_edge", None)
            else:
                sessione.read_measurement_edge = proprio
        entry: Dict = {"block_id": block_id, "t0_mono": None,
                       "t1_mono": None, "n_samples": 0,
                       "samples": [], "power_w": [], "reason": ""}
        if len(bordi) != 2:
            entry["reason"] = (f"bordi catturati {len(bordi)} (attesi 2): "
                               "serie non ricostruibile")
            catturate.append(entry)
            return rec
        e0, mono0 = bordi[0]
        _e1, mono1 = bordi[1]
        try:
            t0 = float(e0.get("t_counter_mono"))
        except (TypeError, ValueError):
            t0 = mono0
        entry["t0_mono"], entry["t1_mono"] = t0, mono1
        try:
            campioni = sessione.samples_between(t0, mono1)
        except Exception as exc:
            entry["reason"] = f"samples_between non disponibile: {exc}"
            catturate.append(entry)
            return rec
        dicts = [_campione_dict(s) for s in campioni]
        entry["samples"] = dicts
        entry["n_samples"] = len(dicts)
        entry["power_w"] = _serie_potenza(dicts)
        if not dicts:
            entry["reason"] = "nessun campione nella finestra passiva"
        catturate.append(entry)
        return rec

    return reale, wrapper, catturate


def _attendi_quiete(*, consecutive: Optional[int] = None,
                    cap_s: Optional[float] = None,
                    poll_s: float = QUIET_POLL_S,
                    campiona=None, top_fn=None,
                    clock: Callable[[], float] = time.monotonic,
                    sleep: Callable[[float], None] = time.sleep,
                    on_log=None) -> Dict:
    """Precondizione di quiete: il blocco non parte se la macchina e' carica.

    Perche' esiste. Il gate del 2026-11-07 e' fallito con
    ``background_load=True`` su 5 controlli su 6 (CompatTelRunner,
    SearchIndexer, Defender, Chrome, Qoder): P1.4 registra il flag nel
    verbale ma non impedisce la partenza. Questa e' una precondizione di
    ESECUZIONE, lato tool: il criterio F.12, le soglie e il disegno non si
    muovono, e il runner non cambia comportamento.

    Meccanica. Ogni lettura e' ``ms.total_cpu_samples()`` (~3 s di
    osservazione, P1.4); ``ms.background_load_from_samples`` dice se e'
    rumorosa (persistenza sopra la soglia congelata di P1.4, non un picco
    singolo). Quiete = ``consecutive`` letture consecutive non rumorose;
    una lettura rumorosa AZZERA il conteggio. Al tetto ``cap_s`` senza
    quiete: ``SystemExit`` — main() lo gira in [ARRESTO] exit 3, la
    campagna non parte e non prosegue in silenzio. Diverso dal cooldown
    (che al tetto RITORNA con timed_out, perche' il blocco si puo' comunque
    misurare e flaggare): qui partire senza quiete sarebbe un disegno
    diverso da quello dichiarato, scoperto solo dopo i dati.

    Iniezione. ``clock``/``sleep`` sono legati alla def come in
    ``cooldown_to_baseline``; ``campiona``/``top_fn`` si risolvono alla
    CHIAMATA (sentinella None) cosi' i test li sostituiscono sul modulo
    senza hardware. I default delle costanti sono quelli congelati nel
    piano (``plan_payload``), e ``_verifica_piano`` li confronta.

    Restituisce ``quiet_wait_s`` (attesa misurata), ``quiet_letture``
    (letture eseguite) e ``top_processes`` (top-5 al momento della
    partenza, ``ms.sample_top_processes``): finiscono in ``runs`` per
    blocco, nel report e in ``gate_result_frozen.json``.
    """
    if consecutive is None:
        consecutive = QUIET_CONSECUTIVE
    if cap_s is None:
        cap_s = QUIET_CAP_S
    if campiona is None:
        campiona = ms.total_cpu_samples
    if top_fn is None:
        top_fn = ms.sample_top_processes
    if consecutive < 1:
        raise ValueError(
            f"consecutive={consecutive}: serve almeno una lettura")
    log = on_log or (lambda m: None)
    t0 = clock()
    consec = 0
    letture = 0
    while True:
        campioni = campiona()
        rumorosa = ms.background_load_from_samples(campioni)
        letture += 1
        if rumorosa:
            consec = 0
            log(f"[QUIETE] lettura {letture}: background_load=True "
                f"(campioni={campioni}), conteggio azzerato")
        else:
            consec += 1
        if consec >= consecutive:
            break
        if clock() - t0 >= cap_s:
            raise SystemExit(
                f"precondizione di quiete non raggiunta entro {cap_s:g} s "
                f"({letture} letture, ne servono {consecutive} consecutive "
                "non rumorose): background_load resta True. Il blocco NON "
                "parte e la campagna si ferma — procedere in silenzio "
                "sarebbe un disegno diverso da quello dichiarato.")
        sleep(poll_s)
    attesa = clock() - t0
    top = top_fn()
    log(f"[QUIETE] raggiunta dopo {attesa:.1f} s ({letture} letture); "
        f"top-5 alla partenza: {top}")
    return {"quiet_wait_s": attesa, "quiet_letture": letture,
            "top_processes": top}


def _temperatura_cpu_c() -> Tuple[Optional[float], str]:
    """Temperatura CPU letta per REGISTRAZIONE, mai come criterio.

    Perche' esiste senza decidere niente. Su questo host psutil 7.2.2 non
    espone nessun ``sensors_*`` termico (misurato 2026-11-09: ``dir(psutil)``
    da' ``sensors_battery`` e basta) e la thermal zone ACPI letta via CIM e'
    rimasta 3010 decikelvin (= 27,85 C) su sei letture a 5 s: nessuna deriva
    osservata, quindi nessuna soglia motivata. Una soglia inventata sarebbe la
    convenzione che il warm-up misurato esiste per togliere, ma il numero va
    comunque registrato perche' serva da evidenza a una campagna futura.

    Catena dichiarata, col motivo quando non risponde: prima
    ``psutil.sensors_temperatures`` (il canale che un host che lo espone
    fornisce gia' in gradi), poi ``MSAcpi_ThermalZoneTemperature`` via CIM in
    decikelvin. Il fallimento di entrambe restituisce ``(None, motivo)``, non
    un sostituto: ``None`` qui vuol dire "non letta", non "fredda". Ogni
    lettura costa 0,26-0,33 s di subprocess (misurato 2026-11-09), percio' la
    si chiama due volte per fase e non per campione.
    """
    fonti: List[str] = []
    sensori = getattr(psutil, "sensors_temperatures", None)
    if callable(sensori):
        try:
            gruppi = sensori() or {}
        except Exception as exc:
            gruppi = {}
            fonti.append(f"psutil: {type(exc).__name__}")
        for nome, elenco in gruppi.items():
            for sens in elenco or []:
                try:
                    valore = float(getattr(sens, "current"))
                except (TypeError, ValueError):
                    continue
                if math.isfinite(valore) and valore > 0.0:
                    return round(valore, 2), f"psutil:{nome}"
        if not fonti:
            fonti.append("psutil: nessuna lettura valida")
    else:
        fonti.append("psutil: sensors_temperatures assente")
    try:
        esito = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -Namespace root/wmi "
             "-ClassName MSAcpi_ThermalZoneTemperature).CurrentTemperature"],
            capture_output=True, text=True, timeout=10.0)
        raw = float((esito.stdout or "").strip())
    except Exception as exc:
        fonti.append(f"cim: {type(exc).__name__}")
        return None, "; ".join(fonti)
    if not math.isfinite(raw) or raw <= 0.0:
        fonti.append(f"cim: valore non valido {esito.stdout!r}")
        return None, "; ".join(fonti)
    return round(raw / 10.0 - 273.15, 2), "cim:MSAcpi_ThermalZoneTemperature"


def _registra_warmup(record: Mapping) -> None:
    """Accoda il registro di una fase di stabilizzazione, SUBITO.

    La fase puo' chiudersi su ``SystemExit`` (tetto) e un arresto non scrive
    ``analysis.json``: senza questo file la durata effettiva di un warm-up
    fallito resterebbe solo sullo stderr del terminale. Il registro e'
    append-only e una riga per fase, perche' due warm-up della stessa
    campagna non si sovrascrivano.
    """
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    with (ARCHIVE_DIR / WARMUP_LOG_NAME).open("a",
                                              encoding="utf-8") as fh:
        fh.write(json.dumps(dict(record), ensure_ascii=False) + "\n")


def _stabilizza_post_carico(target_pre_w: Optional[float], *,
                            tolerance_w: Optional[float] = None,
                            cpu_max_pct: Optional[float] = None,
                            sustain_s: Optional[float] = None,
                            cap_s: Optional[float] = None,
                            step_s: Optional[float] = None,
                            window_s: Optional[float] = None,
                            campiona_potenza: Optional[
                                Callable[[], Optional[float]]] = None,
                            campiona_cpu: Optional[
                                Callable[[], Sequence[float]]] = None,
                            legge_temperatura: Optional[Callable[
                                [], Tuple[Optional[float], str]]] = None,
                            registra: Optional[Callable[[Dict], None]] = None,
                            clock: Callable[[], float] = time.monotonic,
                            sleep: Callable[[float], None] = time.sleep,
                            on_log=None) -> Dict:
    """Warm-up post-carico come criterio MISURATO, non come durata fissa.

    Perche' la forma fissa e' stata tolta. ``time.sleep(10.0)`` dopo il
    blocco di carico chiudeva una fase il cui termine non dipendeva da
    niente: se la macchina rientrava in 2 s si perdevano 8 s, se non ci
    rientrava in 10 s il controllo partiva lo stesso in transitorio — e il
    residuo del carico finiva dentro ``E_net`` del controllo, cioe' dentro
    la grandezza che il gate deve stimare a residuo nullo. Un timer non e'
    un criterio di stabilizzazione.

    Criterio (meccanica identica al cooldown P1.5, ``cooldown_to_baseline``):
    DUE segnali osservati sulla STESSA finestra di ``window_s`` stanno entro
    soglia -- la potenza media del contatore entro ``tolerance_w`` da
    ``target_pre_w`` (la ``baseline_pre_w`` del blocco di carico appena
    chiuso) e la media di finestra di ``cpu_percent`` sotto ``cpu_max_pct`` —
    per un tratto CONTINUO di ``sustain_s``; un campione fuori soglia su
    QUALSIASI dei due (o una lettura assente) azzera il tratto. La
    disuguaglianza e' stretta su entrambi, come in P1.5: "a bordo" non
    soddisfa.

    Perche' due segnali e non uno solo, misurato: nella seconda campagna,
    riaggregata il 2026-11-09 alla scala delle finestre del criterio (2 s
    non sovrapposte, ``control_power_series.json`` + ``blocks_controllo.json``
    della campagna 20261108), il blocco in transitorio (ctrl-1) da' deviazioni
    di 0,4802 e 0,7951 W e medie di cpu_percent di 4,100 e 1,800 %: la prima
    finestra e' DENTRO la banda di potenza e fuori da quella di cpu, la seconda
    e' il contrario. Ogni finestra dei cinque stabilizzati sta sotto 0,3626 W
    e sotto 1,000 %. Nessuna soglia sola respinge il transitorio per
    intero; insieme lo respingono su entrambe le finestre. Provenienza e
    disuguaglianze nel commento delle costanti e nel test di provenienza.

    L'ordine delle due letture NON e' indifferente: ``cpu_percent`` si legge
    per primo perche' la sua finestra e' ``[t, t+window_s]`` e blocca il
    campione fino a ``t+window_s``; la potenza si legge subito dopo, quando
    ``cooldown_power_w(window_s)`` copre ``[t+window_s-window_s, t+window_s]``
    = la stessa finestra. Letta nell'ordine inverso sarebbero due intervalli
    disgiunti e "stesso campione" sarebbe falso. Di qui ``step_s`` a zero:
    l'osservazione della finestra E il passo, come in ``QUIET_POLL_S``.

    La temperatura CPU e' registrata, non decide: ``legge_temperatura`` vale
    all'ingresso e all'uscita della fase (due letture perche' lo spawn del
    lettore consuma CPU proprio mentre si osserva ``cpu_percent``), e il suo
    valore con la fonte o il motivo dell'assenza finisce nel registro.

    Al tetto ``cap_s`` senza rientro: ``SystemExit``, NON un prosiegui con
    un flag. Il cooldown puo' tornare con ``timed_out`` perche' il blocco e'
    gia' definito e il flag lo dichiara; qui il blocco successivo NON e'
    ancora partito e immetterlo su una macchina in transitorio ricreerebbe
    esattamente il difetto che questa fase esiste per eliminare. La quiete
    di precondizione ha la stessa scelta (tetto -> arresto) e la coerenza
    fra le due e' voluta. L'arresto non avviene pero' in silenzio sul
    registro: ``registra`` viene invocata con il record terminale
    (``warmup_completed=False``, ``warmup_motivo="tetto_raggiunto"``) PRIMA
    di sollevare, perche' la durata di un warm-up fallito e' il dato che
    serve a capire perche' la campagna si e' fermata.

    ``campiona_potenza``/``campiona_cpu``/``legge_temperatura``/``registra``/
    ``clock``/``sleep`` sono iniettabili perche' la meccanica dei limiti si
    verifica deterministicamente in test senza hardware e senza subprocess; i
    default leggono ``v4.cooldown_power_w(window_s)`` (la stessa fonte di
    ``settle_idle`` e della calibrazione: contatore di package, non media dei
    campioni) e ``ms.total_cpu_samples(window_s, window_s)``.

    Restituisce il record della fase: ``warmup_completed``,
    ``warmup_duration_s`` (misurata, non un parametro), ``warmup_motivo``
    (``criterio_soddisfatto`` | ``tetto_raggiunto``), ``warmup_campioni``,
    ``warmup_letture_mancanti``, ``warmup_target_pre_w``, le soglie
    ``warmup_soglia_w``/``warmup_soglia_cpu_pct``, la finestra
    ``warmup_finestra_s`` e le serie ``warmup_valori_w`` e
    ``warmup_valori_cpu_pct``, che contengono TUTTA lettura valida, dentro o
    fuori banda che sia (una lettura assente non entra in una serie: ha il suo
    conteggio), oltre a ``warmup_temperatura``. Finisce nel
    ``runs`` di ``analysis.json``, nel report e, in ogni caso, in
    ``warmup_stabilizzazione.jsonl``. Non e' un
    controllo e non entra in ``bias_w``: nessuna delle sue grandezze arriva a
    ``control_gate.evaluate_gate``.
    """
    if tolerance_w is None:
        tolerance_w = WARMUP_TOLERANCE_W
    if cpu_max_pct is None:
        cpu_max_pct = WARMUP_CPU_MAX_PCT
    if sustain_s is None:
        sustain_s = WARMUP_SUSTAIN_S
    if cap_s is None:
        cap_s = WARMUP_CAP_S
    if step_s is None:
        step_s = WARMUP_STEP_S
    if window_s is None:
        window_s = WARMUP_WINDOW_S
    leggi_potenza = campiona_potenza or (lambda: v4.cooldown_power_w(window_s))
    leggi_cpu = campiona_cpu or (lambda: ms.total_cpu_samples(window_s,
                                                              window_s))
    leggi_temperatura = legge_temperatura or _temperatura_cpu_c
    log = on_log or (lambda m: None)
    try:
        target = float(target_pre_w)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        target = float("nan")
    if not math.isfinite(target) or target <= 0.0:
        raise SystemExit(
            f"[WARM-UP] nessun target di rientro valido "
            f"(baseline_pre_w = {target_pre_w!r}): il criterio di "
            "stabilizzazione e' una distanza da una baseline misurata; senza "
            "baseline non esiste ne' il criterio ne' un sostituto, e la "
            "campagna si ferma invece di dormire un tempo a caso.")

    def media_finestra(campioni_cpu) -> Optional[float]:
        """Media dei campioni di ``cpu_percent`` sulla finestra osservata.

        Non e' il massimo: la soglia 2,0 % e' definita sulle MEDIE di
        finestra della seconda campagna (massimo 1,000 % nei cinque
        stabilizzati, 4,100 % e 1,800 % nelle due finestre del transitorio),
        quindi il segnale confrontato deve essere la stessa grandezza. Una
        finestra che non ha restituito campioni e' una lettura assente, non
        uno zero.
        """
        try:
            valori_cpu = [float(x) for x in (campioni_cpu or [])]
        except (TypeError, ValueError):
            return None
        if not valori_cpu:
            return None
        return sum(valori_cpu) / len(valori_cpu)

    def lettura_termica(fase: str) -> Dict:
        """Una riga del registro termico: valore, fonte o motivo."""
        try:
            valore, fonte = leggi_temperatura()
        except Exception as exc:
            valore, fonte = None, f"lettura {type(exc).__name__}"
        return {"fase": fase, "temperatura_c": valore, "fonte": fonte}

    t0 = clock()
    esito: Dict = {
        "warmup_completed": False,
        "warmup_motivo": "",
        "warmup_duration_s": 0.0,
        "warmup_campioni": 0,
        "warmup_letture_mancanti": 0,
        "warmup_target_pre_w": round(target, 6),
        "warmup_soglia_w": tolerance_w,
        "warmup_soglia_cpu_pct": cpu_max_pct,
        "warmup_finestra_s": window_s,
        "warmup_tetto_s": cap_s,
        "warmup_permanenza_richiesta_s": sustain_s,
        "warmup_valori_w": [],
        "warmup_valori_cpu_pct": [],
        "warmup_temperatura": [lettura_termica("ingresso")],
    }
    valori_w: List[float] = esito["warmup_valori_w"]
    valori_cpu: List[float] = esito["warmup_valori_cpu_pct"]
    soddisfatta_dal: Optional[float] = None
    while True:
        cpu_letti = media_finestra(leggi_cpu())
        ora = clock()
        potenza = leggi_potenza()
        esito["warmup_campioni"] += 1
        try:
            v = None if potenza is None else float(potenza)
        except (TypeError, ValueError):
            v = None
        fuori = []
        mancante = False
        if v is None or not math.isfinite(v):
            mancante = True
            fuori.append("potenza assente")
        else:
            # la serie registra CIO' CHE E' STATO LETTO, non solo il rientro:
            # un'escursione fuori banda e' il dato che spiega perche' la fase
            # non ha chiuso, e scriverla solo nel messaggio la perderebbe
            valori_w.append(round(v, 6))
            if abs(v - target) >= tolerance_w:
                fuori.append(f"{v:.3f} W fuori da {tolerance_w} W da "
                             f"{target:.3f} W")
        if cpu_letti is None or not math.isfinite(cpu_letti):
            mancante = True
            fuori.append("cpu_percent assente")
        else:
            valori_cpu.append(round(cpu_letti, 6))
            if cpu_letti >= cpu_max_pct:
                fuori.append(f"{cpu_letti:.3f} % sopra {cpu_max_pct:g} %")
        if fuori:
            if mancante:
                esito["warmup_letture_mancanti"] += 1
            if soddisfatta_dal is not None:
                fuori.append("tratto azzerato")
            soddisfatta_dal = None
            log(f"[WARM-UP] campione {esito['warmup_campioni']}: "
                + "; ".join(fuori))
        else:
            if soddisfatta_dal is None:
                soddisfatta_dal = ora
            if ora - soddisfatta_dal >= sustain_s:
                attesa = ora - t0
                esito["warmup_completed"] = True
                esito["warmup_motivo"] = "criterio_soddisfatto"
                esito["warmup_duration_s"] = round(attesa, 6)
                esito["warmup_temperatura"].append(lettura_termica("uscita"))
                log(f"[WARM-UP] rientro raggiunto dopo {attesa:.1f} s: "
                    f"{sustain_s:g} s continui con potenza entro "
                    f"{tolerance_w} W da P_pre={target:.3f} W e cpu sotto "
                    f"{cpu_max_pct:g} % ({esito['warmup_campioni']} campioni)")
                if registra is not None:
                    registra(dict(esito))
                return esito
        durato = clock() - t0
        if durato >= cap_s:
            esito["warmup_motivo"] = "tetto_raggiunto"
            esito["warmup_duration_s"] = round(durato, 6)
            esito["warmup_temperatura"].append(lettura_termica("uscita"))
            if registra is not None:
                registra(dict(esito))
            raise SystemExit(
                f"[WARM-UP] tetto {cap_s:g} s raggiunto senza {sustain_s:g} "
                f"s continui entro {tolerance_w} W da P_pre={target:.3f} W "
                f"e sotto {cpu_max_pct:g} % di cpu_percent "
                f"(campioni={esito['warmup_campioni']}, letture mancanti="
                f"{esito['warmup_letture_mancanti']}, ultimi valori "
                f"w={valori_w[-5:]} cpu={valori_cpu[-5:]}): la macchina non "
                "e' rientrata dal carico. Il controllo NON parte — procedere "
                "in silenzio sarebbe immettere un residuo di carico nel bias "
                "che il gate deve misurare.")
        if step_s:
            sleep(max(min(step_s, cap_s - durato), 0.0))


def cmd_execute(model: str, *, codecarbon: bool = False,
                codecarbon_interval: Optional[float] = None) -> Dict:
    plan = _verifica_piano()
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows_path = RESULTS_DIR / ROWS_NAME
    blocks_path = RESULTS_DIR / BLOCKS_NAME
    for p in (rows_path, blocks_path):
        if p.exists() and p.stat().st_size > 0:
            raise SystemExit(
                f"output gia' presente: {p}. Il gate misura una campagna "
                "dichiarata: rimuovi l'archivio o cambia data (--date), non "
                "accodare.")

    reale, wrapper, catturati = _cattura_riepiloghi()
    reale_cw, wrapper_cw, serie = _cattura_serie_controllo()

    # Budget PRE-registrato (Revisione del Gate 2026-11-09): la soglia si
    # misura qui, prima che esista un solo blocco di questa campagna, e su
    # una macchina gia' quieta (la precondizione vale anche per il fondo: un
    # fondo misurato a macchina carica sarebbe un budget gonfiato dal carico,
    # cioe' la stessa contaminazione che il gate deve dimostrare assente).
    # Il modo e' quello dichiarato nel piano e verificato sopra: short o
    # matched, e in entrambi i casi il numero viene da finestre lette dal
    # contatore alla scala del controllo, NON da una riscalatura del budget
    # lungo per Tc/30 (formula rimossa) e NON da CodeCarbon.
    print("[BUDGET] precondizione di quiete prima della misura del fondo",
          flush=True)
    quiete_fondo = _attendi_quiete(on_log=lambda m: print(m, flush=True))
    print(f"[BUDGET] procedura dichiarata: {BUDGET_MODE} "
          f"(Tc = {DT_NOM_FROZEN:g} s, {BUDGET_N_TERNE} unita' per gruppo)",
          flush=True)
    risoluzione_timer = _risoluzione_timer_sessione()
    budget_w, dettagli_budget = _calcola_budget_pre_esecuzione(
        BUDGET_MODE, _sessione_misura())
    budget_path = _scrivi_budget_preregistrato(budget_w, dettagli_budget)
    incertezza_pre = _incertezza_pre_esecuzione(dettagli_budget,
                                                risoluzione_timer)
    print(f"[BUDGET] fondo: pre {dettagli_budget['unita_pre_w']} W | "
          f"post {dettagli_budget['unita_post_w']} W", flush=True)
    print(f"[BUDGET] budget_base_w = {budget_w:.6f} W "
          f"(half_range {dettagli_budget['baseline']['half_range_pre_w']}, "
          f"half_drift {dettagli_budget['baseline']['half_drift_w']}) | "
          f"soglia pre-registrata del criterio primario ({CRITERIO_PRIMARIO}) "
          f"= budget = {incertezza_pre['soglia_w']:.6f} W -> {budget_path}",
          flush=True)

    # Registro diagnostico CodeCarbon: SOLO con il flag. L'import e' dentro
    # il ramo perche' senza flag il comportamento deve restare identico a
    # oggi — modulo neppure caricato. avvia() non solleva mai: se la
    # libreria manca il gate prosegue e il motivo finisce nello stato.
    probe = None
    riepilogo_probe: Optional[Dict] = None
    if codecarbon:
        import codecarbon_probe as ccp  # noqa: E402  (modulo accanto, tools/)
        probe = ccp.ProbeCodeCarbon(ARCHIVE_DIR / ccp.DIR_NAME,
                                    measure_power_secs=codecarbon_interval)
        probe.avvia()

    runs: List[Dict] = []

    def _registrar_warmup(blocco: Mapping, block_id: str):
        """Chiude il registro di una fase con l'identita' del blocco.

        Serve perche' ``warmup_stabilizzazione.jsonl`` deve restare leggibile
        anche quando la fase si arresta al tetto e ``analysis.json`` non viene
        scritto: senza l'identita' una riga del registro non direbbe a quale
        coppia appartiene la durata che riporta.
        """
        def _reg(record: Dict) -> None:
            record.update({"index": blocco["index"], "label": blocco["label"],
                           "arm": blocco["arm"], "pair_id": blocco["pair_id"],
                           "block_id": block_id})
            _registra_warmup(record)
        return _reg

    v4.export_summary_csv = wrapper
    v4._run_control_window = wrapper_cw
    try:
        for b in plan["blocks"]:
            initial_pre: Optional[float] = None
            if b["arm"] == "control":
                initial_pre = _ultima_baseline_pre(blocks_path)
                if initial_pre is None:
                    raise SystemExit(
                        f"propagazione interrotta prima di {b['label']}: "
                        "nessuna baseline_pre_w valida dall'ultimo blocco. Il "
                        "controllo partirebbe senza cooldown verso il carico: "
                        "disegno diverso da quello dichiarato, mi fermo.")
            kw, prompt = _call_kwargs(b, initial_pre, rows_path, blocks_path)
            print(f"[BLOCCO {b['index']:>2}] {b['label']} ({b['arm']}, "
                  f"{b['pair_id']})"
                  + (f" P_pre_ref={initial_pre:.6f} W" if initial_pre else ""),
                  flush=True)
            # Precondizione PRIMA di ogni invocazione, load E control:
            # una macchina carica non parte (check E del piano).
            quiet = _attendi_quiete(on_log=lambda m: print(m, flush=True))

            # Il tracker avvolge la sola invocazione: l'overhead di
            # start()/stop() (~1 s per blocco, misurato l'08-11) resta
            # FUORI da run_v4_benchmark e il probe lo dichiara nel suo
            # stato. La quiete NON e' riaperta dal tracker: vale il
            # controllo sopra.
            if probe is not None:
                probe.apri_blocco(b["label"], arm=b["arm"],
                                  pair_id=b["pair_id"])
            try:
                summary = v4.run_v4_benchmark([model], [prompt], **kw)
            finally:
                if probe is not None:
                    probe.chiudi_blocco()
            rec = dict(catturati[-1]) if catturati else {}
            # Warm-up post-carico MISURATO (Revisione del Gate 2026-11-09):
            # sta DOPO l'invocazione di carico e PRIMA che la coppia prosegua
            # verso il controllo, perche' cio' che si attende e' il rientro
            # della macchina verso la baseline del blocco appena chiuso. Il
            # target e' quel numero letto dal riepilogo reale, non una
            # costante: se il blocco non lo ha prodotto, la stabilizzazione
            # non ha un criterio e il tool si ferma (vedi la funzione).
            # Il registro passa da ``registra`` perche' la fase puo'
            # chiudersi su SystemExit, e un arresto non scrive analysis: la
            # durata di un warm-up fallito resta cosi' leggibile.
            warmup: Optional[Dict] = None
            if b["arm"] == "load":
                warmup = _stabilizza_post_carico(
                    rec.get("baseline_pre_w"),
                    registra=_registrar_warmup(b, rec.get("block_id", "")),
                    on_log=lambda m: print(m, flush=True))
            run_rec = {
                "index": b["index"], "label": b["label"], "arm": b["arm"],
                "pair_id": b["pair_id"], "run_id": summary["run_id"],
                "batch_id": summary["batch_id"],
                "block_id": rec.get("block_id", ""),
                "records": summary.get("records"),
                "blocks": summary.get("blocks"),
                "errors": summary.get("errors"),
                "invalidated_blocks": summary.get("invalidated_blocks"),
                "initial_last_pre_w": initial_pre,
                "block_baseline_pre_w": rec.get("baseline_pre_w", ""),
                "block_cooldown_timeout": rec.get("cooldown_timeout", ""),
                "quiet_wait_s": quiet["quiet_wait_s"],
                "quiet_letture": quiet["quiet_letture"],
                "quiet_top_processes": quiet["top_processes"],
                "background_load_before": summary.get("background_load_before"),
                "background_load_after": summary.get("background_load_after"),
                "warmup": warmup,
            }
            runs.append(run_rec)
            if summary.get("errors"):
                raise SystemExit(
                    f"[ERRORE] {b['label']}: {summary['errors']} — K=1, mi "
                    "fermo prima del blocco successivo (Emenda 8)")
            if summary.get("invalidated_blocks"):
                raise SystemExit(
                    f"[ERRORE] {b['label']}: blocco invalidato per guasto "
                    f"(K={K_MAX}): {summary.get('stopped_by_k', '')} — mi "
                    "fermo")
            if b["arm"] == "control":
                cd = run_rec["block_cooldown_timeout"]
                if cd == "":
                    raise SystemExit(
                        f"[ERRORE] {b['label']}: cooldown non eseguito "
                        f"nonostante P_pre propagato ({initial_pre} W) — "
                        "cella cooldown_timeout vuota. La propagazione non ha "
                        "raggiunto il runner: mi fermo prima di dichiarare "
                        "il gate.")
    finally:
        v4.export_summary_csv = reale
        v4._run_control_window = reale_cw
        if probe is not None:
            # Scrive status e manifest anche sul percorso di errore: e' qui
            # che il motivo di un blocco saltato deve restare leggibile.
            riepilogo_probe = probe.concludi()
            print(f"[CODECARBON] {riepilogo_probe['codecarbon_status']} "
                  f"({riepilogo_probe['n_blocchi_con_dati']}/"
                  f"{riepilogo_probe['n_blocchi_aperti']} blocchi con "
                  f"dati) -> {riepilogo_probe['directory']}", flush=True)

    controls = _filtra_controlli(catturati)
    if len(controls) != N_COPPIE:
        raise SystemExit(
            f"controlli catturati {len(controls)} su {N_COPPIE}: il gate "
            "sarebbe valutato su un disegno diverso da quello dichiarato")
    _scrittura_atomica(ARCHIVE_DIR / BLOCKS_JSON_NAME, controls)
    if len(serie) != N_COPPIE:
        print(f"[AVVISO] serie di potenza catturate {len(serie)} su "
              f"{N_COPPIE}: diagnostica incompleta, il gate non cambia",
              flush=True)
    _scrittura_atomica(ARCHIVE_DIR / SERIES_NAME, serie)
    q = cg.evaluate_gate(controls, n_pairs=N_COPPIE)

    # Il verdetto F.12 resta quello congelato (mediana dei budget per
    # blocco, quorum, chain_status): non si sposta qui. Accanto, e dichiarata
    # come tale, viaggia la soglia di copertura calcolata sul fondo
    # pre-registrato: la prima con u_A assente perche' i controlli non
    # esistevano ancora, la seconda con la quinta componente quando i
    # controlli ci sono. Nessuna delle due sostituisce l'altra, e nessuna
    # delle due passa da CodeCarbon.
    analysis = q.to_dict()
    incertezza_post = _incertezza_con_au_controlli(incertezza_pre,
                                                   analysis["controls"])
    incertezza_post["accettazione_guardata"] = _accettazione_guardata(
        analysis.get("bias_w"), incertezza_post, budget_w)
    analysis.update({
        "pilot": "P4.4 gate",
        "model": model,
        "dt_nominal_s": DT_NOM_FROZEN,
        "order_seed": SEED,
        "geometry": GEOMETRY,
        "quiet_precondition": {"consecutive": QUIET_CONSECUTIVE,
                               "cap_s": QUIET_CAP_S},
        "warmup_precondition": {
            "tolerance_w": WARMUP_TOLERANCE_W,
            "cpu_max_pct": WARMUP_CPU_MAX_PCT,
            "sustain_s": WARMUP_SUSTAIN_S,
            "cap_s": WARMUP_CAP_S,
            "window_s": WARMUP_WINDOW_S,
            "step_s": WARMUP_STEP_S},
        "runs": runs,
        "results_csv": str(rows_path),
        "block_summary_csv": str(blocks_path),
        "blocks_controllo_json": str(ARCHIVE_DIR / BLOCKS_JSON_NAME),
        "control_power_series_json": str(ARCHIVE_DIR / SERIES_NAME),
        "warmup_log_jsonl": str(ARCHIVE_DIR / WARMUP_LOG_NAME),
        "budget_preregistrato_json": str(budget_path),
        "series_counts": {s["block_id"]: s["n_samples"] for s in serie},
        "run_ids": [r["run_id"] for r in runs],
        "git_head": _git_head(),
        "runner_sha256": _sha256(MODULE_DIR / "benchmark_v4.py"),
        "metadata_path": str(config.CSV_RUN_METADATA_PATH),
    })
    # Grandezze riportate, non criterio: viaggiano nell'analysis e quindi
    # nel freeze, accanto al verdetto F.12 che non toccano.
    analysis["grandezze_riportate"] = _grandezze_riportate(
        analysis["controls"], runs)
    if riepilogo_probe is not None:
        # Chiave diagnostica ACCANTO al verdetto, non dentro: il riepilogo
        # di evaluate_gate e' gia' scritto e non legge questo ramo. Senza
        # flag la chiave non esiste e l'analysis e' byte-identica a oggi.
        analysis["codecarbon"] = riepilogo_probe

    # Soglia di copertura sul fondo pre-registrato, con le componenti
    # dimostrate. E' una grandezza riportata, non il criterio F.12: la
    # riga qui sotto serve a chi legge per verificare il conto, non a
    # decidere l'esito.
    analysis["budget_pre_esecuzione"] = {
        "budget_mode": BUDGET_MODE,
        "budget_base_w": budget_w,
        "tc_duration_s": DT_NOM_FROZEN,
        "n_finestre_usate": dettagli_budget["n_finestre_usate"],
        "n_per_aggregato": dettagli_budget["n_per_aggregato"],
        "durata_aggregato_s": dettagli_budget["durata_aggregato_s"],
        "canale": dettagli_budget["canale"],
        "unita_pre_w": dettagli_budget["unita_pre_w"],
        "unita_post_w": dettagli_budget["unita_post_w"],
        "baseline": dettagli_budget["baseline"],
        "assunzioni": dettagli_budget["assunzioni"],
        "scala_30_s_applicata": False,
        "codecarbon_usato": False,
        "risoluzione_timer_s": risoluzione_timer,
        "quiete_pre_fondo_s": quiete_fondo["quiet_wait_s"],
    }
    analysis["incertezza"] = {"pre_esecuzione": incertezza_pre,
                              "post_controlli": incertezza_post}
    analysis["soglia_preregistrata_w"] = incertezza_pre["soglia_w"]
    # Il verdetto che DECIDE (check H del piano). analysis["status"] resta il
    # verdetto F.12 storico, invariato: i due si leggono accanto e il primo e'
    # quello dichiarato prima dei dati.
    analysis["verdetto_primario"] = _verdetto_primario(analysis, budget_w)

    _scrittura_atomica(ARCHIVE_DIR / ANALYSIS_NAME, analysis)
    _scrittura_atomica(ARCHIVE_DIR / FREEZE_NAME, analysis)
    _write_report(analysis)
    print(json.dumps(analysis, indent=2, ensure_ascii=False), flush=True)
    return analysis


# Quantili t di Student, coda superiore 0.025 (CI95 bilaterale), df 1-30:
# tavola standard della distribuzione t (NIST/SEMATECH e-Handbook, tabella
# dei quantili t; valori arrotondati alla terza cifra). Usata SOLO se scipy
# non e' installato: la provenienza e' dichiarata per ogni calcolo.
_T_TABLE_975 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571,
    6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
    11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131,
    16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    21: 2.080, 22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060,
    26: 2.056, 27: 2.052, 28: 2.048, 29: 2.045, 30: 2.042,
}
_T_INF_975 = 1.960  # df>30 senza scipy: approssimazione normale, dichiarata


def _quantile_t_975(df: int) -> Tuple[float, str]:
    """Quantile t(0.975, df) con la sua provenienza: scipy se c'e',
    altrimenti tabella 1-30; oltre 30, 1.960 (approssimazione normale).
    La provenienza viaggia col numero: un quantile senza fonte non e'
    verificabile da un terzo."""
    if df < 1:
        raise ValueError(f"df={df}: i gradi di liberta' sono n-1, n>=2")
    if _scipy_t is not None:
        return float(_scipy_t.ppf(0.975, df)), "scipy"
    if df <= 30:
        return _T_TABLE_975[df], "tabella"
    return _T_INF_975, "tabella (df>30: 1.960, approssimazione normale)"


def _statistiche_descrittive(valori: Sequence[float]) -> Dict:
    """Media, sd campionaria (ddof=1), SE e CI95 t di Student.

    Descrittiva FRA blocchi di controllo: non e' la terna di baseline di
    P4.12 (lì a n=3 non si stima una varianza, e quel divieto resta), non
    entra nello schema CSV e non decide l'esito del gate. Con n<2 la sd
    non e' calcolabile: None dichiarata, non zero. CI95 = media +/-
    t(0.975, n-1) * SE, con la provenienza del quantile registrata.
    """
    n = len(valori)
    out: Dict = {"n": n, "media": None, "sd": None, "se": None,
                 "ci95": None, "t_quantile": None, "t_provenienza": ""}
    if n == 0:
        out["t_provenienza"] = "nessun valore"
        return out
    media = sum(valori) / n
    out["media"] = media
    if n < 2:
        out["t_provenienza"] = "n<2: sd non calcolabile"
        return out
    sd = math.sqrt(sum((x - media) ** 2 for x in valori) / (n - 1))
    se = sd / math.sqrt(n)
    q, prov = _quantile_t_975(n - 1)
    out.update(sd=sd, se=se, ci95=[media - q * se, media + q * se],
               t_quantile=q, t_provenienza=prov)
    return out


def _grandezze_riportate(controls: Sequence[Mapping],
                         runs: Sequence[Mapping]) -> Dict:
    """E_net/dt_W per TUTTI i controlli, anche non utilizzabili, e le
    statistiche descrittive su tutti e sui soli utilizzabili.

    Non decide l'esito: il gate resta F.12. Un controllo non utilizzabile
    non sparisce dal report — il suo rapporto e' riportato, il criterio lo
    esclude. I flag ``background_load`` prima/dopo arrivano dai runs (il
    runner li espone nel riepilogo), matched per ``block_id``; un run
    assente lascia None, non inventa uno stato. dt_W=0 o assente, E_net
    non numerico: nessun numero (None), non una divisione forzata.
    """
    run_per_blocco = {r.get("block_id", ""): r for r in runs}
    per_controllo: List[Dict] = []
    tutti: List[float] = []
    utilizzabili: List[float] = []
    for c in controls:
        bid = str(c.get("block_id", "") or "")
        r = run_per_blocco.get(bid, {})
        e_net, dt = c.get("e_net_j"), c.get("dt_w_s")
        p_net: Optional[float] = None
        try:
            if e_net is not None and dt is not None and float(dt) != 0.0:
                p_net = float(e_net) / float(dt)
        except (TypeError, ValueError):
            p_net = None
        if p_net is not None and not math.isfinite(p_net):
            p_net = None
        per_controllo.append({
            "block_id": bid,
            "usable": bool(c.get("usable")),
            "e_net_j": e_net, "dt_w_s": dt, "p_net_w": p_net,
            "background_load_before": r.get("background_load_before"),
            "background_load_after": r.get("background_load_after"),
        })
        if p_net is not None:
            tutti.append(p_net)
            if c.get("usable"):
                utilizzabili.append(p_net)
    return {
        "per_controllo": per_controllo,
        "tutti": _statistiche_descrittive(tutti),
        "utilizzabili": _statistiche_descrittive(utilizzabili),
        "nota": ("grandezze descrittive fra blocchi di controllo: non "
                 "decidono l'esito del gate (F.12 invariato), non entrano "
                 "nello schema CSV. sd campionaria (ddof=1) su n blocchi, "
                 "non sulla terna di baseline di P4.12; CI95 = media +/- "
                 "t(0.975, n-1) * SE; n<2 -> sd None dichiarata."),
    }


def _flag_txt(v) -> str:
    """Il flag P1.4 nel report: True/False misurati, None = non rilevato.
    Un 'non rilevato' non si stampa come False."""
    if v is True:
        return "True"
    if v is False:
        return "False"
    return "non rilevato"


def _stats_txt(s: Mapping) -> str:
    """Riga di report per le statistiche: n, media, sd, SE, CI95 e la
    provenienza del quantile t. n<2 e n=0 sono dichiarati, non taciuti."""
    if s["n"] == 0:
        return "- n=0: nessun valore calcolabile\n"
    riga = f"- n={s['n']}, media={s['media']:.6f} W"
    if s["sd"] is None:
        return riga + "; sd/SE/CI95 non calcolabili (n<2), dichiarati\n"
    lo, hi = s["ci95"]
    return (riga + f", sd={s['sd']:.6f} W, SE={s['se']:.6f} W, "
            f"CI95=[{lo:.6f}, {hi:.6f}] W "
            f"(t={s['t_quantile']:.4f}, provenienza: {s['t_provenienza']})\n")


def _write_report(data: Dict) -> None:
    summary = (f"gate: {data['status']}; controlli utilizzabili = "
               f"{data['controls_usable_n']}/{data['n_pairs']} coppie, "
               f"quorum = {data['quorum']}; chain_status = "
               f"'{data['chain_status']}'")
    with (ARCHIVE_DIR / REPORT_NAME).open("w", encoding="utf-8") as fh:
        fh.write("# Gate P4.4 load-versus-control\n\n")
        fh.write(f"- modello: `{data['model']}`\n")
        fh.write(f"- DT_NOM congelato = {data['dt_nominal_s']} s "
                 "(pilota P2.9, requisito 5)\n")
        fh.write(f"- order_seed dichiarato = {data['order_seed']} "
                 "(requisito 3)\n")
        fh.write("- geometria (12,32) (requisito 4)\n")
        fh.write(f"- {2 * data['n_pairs']} blocchi / {data['n_pairs']} "
                 "coppie, un blocco per invocazione\n")
        cc = data.get("codecarbon")
        if cc:
            fh.write(f"- CodeCarbon (registro parallelo, NON criterio): "
                     f"status `{cc['codecarbon_status']}`, "
                     f"{cc['n_blocchi_con_dati']}/"
                     f"{cc['n_blocchi_aperti']} blocchi con dati, "
                     f"intervallo {cc['measure_power_secs_used']} s"
                     + (f" — motivo: {cc['reason']}" if cc["reason"] else "")
                     + f"; artefatti in `{cc['directory']}`\n")
        fh.write("\n")
        fh.write("## Risultato\n\n")
        fh.write(summary + "\n")
        vp = data.get("verdetto_primario")
        if vp:
            fh.write(f"- VERDETTO PRIMARIO (decide) `{vp['criterio']}`: "
                     f"**{vp['status']}** - {vp['motivo']}\n")
            fh.write(f"- verdetto F.12 storico (riportato, non decide; "
                     f"`{vp['criterio_storico_riportato']}`): "
                     f"{vp['f12_status']}\n")
        pass_false = sum(1 for c in data["controls"]
                         if c["usable"] and c["block_pass"] is False)
        fh.write(f"- utilizzabili con block_pass=False: {pass_false}/"
                 f"{data['controls_usable_n']} (il criterio per blocco e' "
                 "riportato, non decide lo status del gate)\n\n")
        if data["bias_w"] is not None:
            fh.write(f"- bias_w = {data['bias_w']:.6f} W contro soglia "
                     f"mediana_c(budget_base_w) = "
                     f"{data['bias_threshold_w']:.6f} W\n\n")
        else:
            fh.write("- bias non calcolato: gate non eseguibile\n\n")
        b_pre = data.get("budget_pre_esecuzione")
        inc = data.get("incertezza") or {}
        if b_pre:
            fh.write("## Budget pre-registrato e incertezza "
                     "(grandezza riportata, NON il criterio F.12)\n\n")
            fh.write("La soglia nasce qui, PRIMA che esista un solo blocco "
                     "di questa campagna: il fondo e' letto dal contatore di "
                     "package su finestre della durata nominale del controllo "
                     "e aggregato con le stesse regole del budget lungo "
                     "(`benchmark_v4.block_baseline`, F.1/F.4). Nessuna "
                     "riscalatura per Tc/30 e nessun contributo di "
                     "CodeCarbon. Il criterio che decide e' dichiarato nel "
                     "piano (`criterio_primario`): |bias_w| <= budget_base_w "
                     "a scala Tc. Il verdetto F.12 storico (mediana dei "
                     "budget per blocco) e' riportato accanto.\n\n")
            fh.write(f"- procedura: `{b_pre['budget_mode']}` | "
                     f"Tc = {b_pre['tc_duration_s']} s | "
                     f"{len(b_pre['unita_pre_w'])} unita' pre + "
                     f"{len(b_pre['unita_post_w'])} post | "
                     f"{b_pre['n_per_aggregato']} finestre Tc per unita' "
                     f"({b_pre['durata_aggregato_s']:.6f} s nominali) | "
                     f"{b_pre['n_finestre_usate']} finestre lette in tutto | "
                     f"canale `{b_pre['canale']}`\n")
            fh.write(f"- potenze unita' pre = {b_pre['unita_pre_w']} W, "
                     f"post = {b_pre['unita_post_w']} W\n")
            base = b_pre["baseline"]
            fh.write(f"- mediana pre (baseline del fondo) = "
                     f"{base['baseline_pre_w']} W | half_range_pre_w = "
                     f"{base['half_range_pre_w']} W | half_drift_w = "
                     f"{base['half_drift_w']} W\n")
            fh.write(f"- budget_base_w = {b_pre['budget_base_w']:.6f} W | "
                     f"scala 30 s applicata = "
                     f"{b_pre['scala_30_s_applicata']} | CodeCarbon usato = "
                     f"{b_pre['codecarbon_usato']} | timer = "
                     f"{b_pre['risoluzione_timer_s']} s | quiete pre-fondo = "
                     f"{b_pre['quiete_pre_fondo_s']:.1f} s\n")
            for nome, gruppo in (("pre-esecuzione",
                                  inc.get("pre_esecuzione")),
                                 ("post-controlli",
                                  inc.get("post_controlli"))):
                if not gruppo:
                    continue
                fh.write(f"\n### u_c {nome}\n\n")
                u_c_txt = (f"{gruppo['u_c']:.6f} W"
                           if gruppo["u_c"] is not None else "assente (None)")
                u_est = gruppo.get("U_w")
                u_est_txt = (f"{u_est:.6f} W (k = {gruppo['k']:.4f}, "
                             f"{gruppo.get('k_provenienza', '')})"
                             if u_est is not None else "assente")
                fh.write(f"- u_c = {u_c_txt}; U = {u_est_txt}; soglia del "
                         f"criterio primario = budget = "
                         f"{gruppo['soglia_w']:.6f} W\n")
                guard = gruppo.get("accettazione_guardata")
                if guard:
                    fh.write(f"- accettazione con banda di guardia "
                             f"(riportata, non decide): {guard['accettata']} - "
                             f"{guard['nota']}\n")
                for componente, det in gruppo["componenti"].items():
                    valore = det["value"]
                    testo = (f"{valore:.6f} W"
                             if isinstance(valore, (int, float))
                             and not isinstance(valore, bool) else "assente")
                    stato = ("INCLUSA" if det.get("inclusa") else "ESCLUSA")
                    fh.write(f"  - {componente} = {testo} - tipo "
                             f"{det.get('tipo', '?')}, {stato}: "
                             f"{det.get('motivo', 'motivo non dichiarato')}; "
                             f"`{det['formula'] or 'non calcolabile'}`; "
                             f"fonte: {det['fonte']}\n")
            fh.write("\n### Assunzioni dichiarate\n\n")
            for assunzione in b_pre["assunzioni"]:
                fh.write(f"- {assunzione}\n")
            fh.write(f"\n- artefatto: "
                     f"`{data.get('budget_preregistrato_json', '')}`\n\n")
        fh.write("## Blocchi di controllo\n\n")
        run_per_blocco = {r.get("block_id", ""): r
                          for r in data.get("runs", [])}
        for c in data["controls"]:
            try:
                p_net_w = float(c["e_net_j"]) / float(c["dt_w_s"])
                p_net_txt = f"{p_net_w:.6f} W"
            except (TypeError, ValueError, ZeroDivisionError):
                p_net_txt = "n/d"
            fh.write(
                f"- {c['block_id']}: usable={c['usable']}, "
                f"unstable={c['control_unstable']}, "
                f"pre_range_w={c['pre_range_w']}, dP={c['dP']}, "
                f"E_net={c['e_net_j']} J, dt_W={c['dt_w_s']} s, "
                f"E_net/dt_W={p_net_txt}, "
                f"budget_base_j={c['budget_base_j']}, "
                f"budget_base_w={c['budget_base_w']} W, "
                f"window={c['window_source']}, block_pass={c['block_pass']}"
                + (f" — {c['reason']}" if c["reason"] else "") + "\n")
            r = run_per_blocco.get(c["block_id"], {})
            if r:
                fh.write(
                    f"  baseline: P_pre_ref propagata dal carico="
                    f"{r.get('initial_last_pre_w')} W, propria del blocco="
                    f"{r.get('block_baseline_pre_w')} W\n")
        g = data.get("grandezze_riportate")
        if g:
            fh.write("\n## Grandezze riportate, non criterio\n\n")
            fh.write("E_net/dt_W per TUTTI i controlli (anche non "
                     "utilizzabili) e statistiche descrittive fra blocchi: "
                     "media, sd campionaria (ddof=1), SE, CI95 t di "
                     "Student. Non decidono l'esito del gate, che resta "
                     "F.12; non entrano nello schema CSV. background_load "
                     "prima/dopo dal riepilogo del runner (P1.4).\n\n")
            fh.write("| blocco | utilizzabile | E_net/dt_W (W) | "
                     "background_load prima | dopo |\n")
            fh.write("|---|---|---|---|---|\n")
            for c in g["per_controllo"]:
                p = c["p_net_w"]
                p_txt = f"{p:.6f}" if p is not None else "n/d"
                fh.write(
                    f"| {c['block_id']} | {c['usable']} | {p_txt} | "
                    f"{_flag_txt(c['background_load_before'])} | "
                    f"{_flag_txt(c['background_load_after'])} |\n")
            for nome, stats in (("tutti i controlli", g["tutti"]),
                                ("soli utilizzabili", g["utilizzabili"])):
                fh.write(f"\n### Statistiche su {nome}\n\n")
                fh.write(_stats_txt(stats))
        fh.write("\n## Propagazione cooldown (scelta operativa)\n\n")
        for r in data["runs"]:
            if r["arm"] == "control":
                fh.write(
                    f"- {r['label']}: P_pre_ref="
                    f"{r['initial_last_pre_w']}, baseline propria del blocco="
                    f"{r.get('block_baseline_pre_w', '')}, cooldown_timeout="
                    f"'{r['block_cooldown_timeout']}'\n")
        fh.write("\n## Precondizione di quiete\n\n")
        q = data.get("quiet_precondition") or {}
        fh.write(f"Prima di OGNI blocco (load e control): "
                 f"{q.get('consecutive', QUIET_CONSECUTIVE)} letture "
                 "consecutive con background_load=False; una lettura "
                 "rumorosa azzera il conteggio; al tetto "
                 f"({q.get('cap_s', QUIET_CAP_S):g} s) il run si ferma. "
                 "Precondizione di esecuzione lato tool (P1.4): non entra "
                 "nel criterio F.12.\n\n")
        for r in data["runs"]:
            attesa = r.get("quiet_wait_s")
            attesa_txt = (f"{attesa:.1f} s"
                          if isinstance(attesa, (int, float)) else "n/d")
            top = r.get("quiet_top_processes") or []
            top_txt = ", ".join(
                f"{p.get('name', '?')} pid={p.get('pid', '?')} "
                f"({p.get('cpu_pct', '?')}%)" for p in top) or "nessuno"
            fh.write(
                f"- {r['label']} ({r['arm']}): attesa={attesa_txt}, "
                f"letture={r.get('quiet_letture', 'n/d')}, top-5 alla "
                f"partenza: {top_txt}\n")
        fh.write("\n## Warm-up post-carico (criterio misurato)\n\n")
        w = data.get("warmup_precondition") or {}
        fh.write(
            "Dopo OGNI blocco di carico e prima del controllo della coppia. "
            f"Finestra osservata di {w.get('window_s', WARMUP_WINDOW_S):g} s; "
            "la fase chiude quando, SULLA STESSA finestra, la potenza resta "
            f"entro {w.get('tolerance_w', WARMUP_TOLERANCE_W)} W dalla "
            "baseline_pre_w del blocco di carico E la media di "
            f"cpu_percent resta sotto "
            f"{w.get('cpu_max_pct', WARMUP_CPU_MAX_PCT):g} % per "
            f"{w.get('sustain_s', WARMUP_SUSTAIN_S):g} s continui; un "
            "campione fuori soglia su uno dei due, o una lettura assente, "
            f"azzera il tratto. Al tetto {w.get('cap_s', WARMUP_CAP_S):g} s "
            "la campagna si ferma (SystemExit). La temperatura CPU e' "
            "registrata all'ingresso e all'uscita e NON decide: su questo "
            "host non esiste canale termico con deriva misurata. Il warm-up "
            "NON e' un controllo e non entra in ``bias_w`` ne' in "
            "``evaluate_gate``; le soglie sono pre-registrate sui dati della "
            "campagna 20261108 (commento delle costanti nel tool).\n\n")
        for r in data["runs"]:
            fase = r.get("warmup")
            if not fase:
                continue
            term = "; ".join(
                f"{t.get('fase')}={t.get('temperatura_c')} C "
                f"({t.get('fonte')})"
                for t in fase.get("warmup_temperatura") or []) or "nessuna"
            fh.write(
                f"- {r['label']} ({r['pair_id']}): completed="
                f"{fase.get('warmup_completed')}, durata="
                f"{fase.get('warmup_duration_s')} s, motivo='"
                f"{fase.get('warmup_motivo')}', campioni="
                f"{fase.get('warmup_campioni')}, letture mancanti="
                f"{fase.get('warmup_letture_mancanti')}, target="
                f"{fase.get('warmup_target_pre_w')} W, soglia="
                f"{fase.get('warmup_soglia_w')} W / "
                f"{fase.get('warmup_soglia_cpu_pct')} %, "
                f"ultimi W={fase.get('warmup_valori_w', [])[-4:]}, "
                f"ultimi %={fase.get('warmup_valori_cpu_pct', [])[-4:]}, "
                f"temperatura: {term}\n")
        if data.get("bias_jtok_pct"):
            lo, hi = data["bias_jtok_pct"]
            fh.write("\n## Rapporto J/token (F.12, grandezza riportata)\n\n")
            fh.write(f"- bias = {lo:.3f}–{hi:.3f} % di J/token "
                     "(scala ancorata 1 W ~ 6–11%)\n")
        if data.get("reasons"):
            fh.write("\n## Ragioni\n\n")
            for motivo in data["reasons"]:
                fh.write(f"- {motivo}\n")
        if data.get("series_counts"):
            fh.write("\n## Serie di potenza grezza (diagnostica)\n\n")
            fh.write("Campioni del sampler nella finestra passiva "
                     "[t0, t1] del contatore; potenza = delta del "
                     "contatore cumulativo / delta t fra campioni "
                     "consecutivi. Diagnostica per distinguere deriva e "
                     "picchi: non entra nel criterio F.12.\n\n")
            for bid, n in data["series_counts"].items():
                fh.write(f"- {bid}: {n} campioni\n")
        fh.write("\n## Artefatti\n\n")
        fh.write(f"- results CSV: {data['results_csv']}\n")
        fh.write(f"- block summary CSV: {data['block_summary_csv']}\n")
        fh.write(f"- riepiloghi controllo (JSON, forma --blocks): "
                 f"{data['blocks_controllo_json']}\n")
        fh.write(f"- serie di potenza grezza dei controlli (JSON): "
                 f"{data.get('control_power_series_json', '')}\n")
        fh.write(f"- registro stabilizzazione post-carico (JSONL, una riga "
                 f"per fase): {data.get('warmup_log_jsonl', '')}\n")
        fh.write(f"- run ids: {', '.join(data['run_ids'])}\n")
        fh.write(f"- git head: {data['git_head']}\n")
        fh.write(f"- runner sha256: {data['runner_sha256']}\n")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate load-versus-control di P4.4 sulla v4")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_plan = sub.add_parser("plan", help="scrivi il piano PRIMA di misurare")
    p_plan.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_plan.add_argument("--date", default=DEFAULT_DATE,
                        help="etichetta della campagna YYYYMMDD: archivio e "
                             "results dedicati, disegno invariato")
    p_plan.add_argument("--seed", default=DEFAULT_SEED,
                        help="seme del disegno dichiarato nel piano "
                             "(default: la campagna 2026-11-07)")
    p_plan.add_argument("--pairs", type=int, default=DEFAULT_PAIRS,
                        help="numero di coppie del disegno (default 6; "
                             "12 per la terza campagna, Quattordicesima "
                             "emenda): il quorum e' ceil(2/3 * coppie)")
    p_exec = sub.add_parser("execute",
                            help="esegui i blocchi del piano e valuta F.12")
    p_exec.add_argument("--model", default=DEFAULT_MODEL,
                        help="modello locale")
    p_exec.add_argument("--date", default=DEFAULT_DATE,
                        help="etichetta della campagna YYYYMMDD: deve essere "
                             "quella del plan dichiarato")
    p_exec.add_argument("--seed", default=DEFAULT_SEED,
                        help="seme del disegno: deve essere quello del plan "
                             "dichiarato, altrimenti execute si ferma")
    p_exec.add_argument("--pairs", type=int, default=DEFAULT_PAIRS,
                        help="numero di coppie: deve essere quello del plan "
                             "dichiarato, altrimenti execute si ferma")
    p_exec.add_argument("--codecarbon", action="store_true",
                        help="registro parallelo CodeCarbon attorno a ogni "
                             "blocco (diagnostico, NON criterio): artefatti "
                             "in <archivio>/codecarbon/; senza libreria il "
                             "gate prosegue e lo stato dichiara unavailable")
    p_exec.add_argument("--codecarbon-interval", type=float, default=None,
                        help="measure_power_secs del probe (default: 1 s, "
                             "fallback 15 s se il tracker non lo accetta)")
    args = parser.parse_args(argv)
    _imposta_data(args.date)
    _imposta_seme(args.seed)
    _imposta_coppie(args.pairs)
    if args.cmd == "plan":
        return cmd_plan(args.model)
    if args.cmd == "execute":
        try:
            r = cmd_execute(args.model, codecarbon=args.codecarbon,
                            codecarbon_interval=args.codecarbon_interval)
        except SystemExit as e:
            if isinstance(e.code, int):
                raise
            print(f"[ARRESTO] {e.code}", file=sys.stderr, flush=True)
            return 3
        mapping = {"pass": 0, "fail": 1, "not-executable": 2}
        decide = (r.get("verdetto_primario") or {}).get("status", r["status"])
        return mapping[decide]
    parser.error("seguono solo plan/execute")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
