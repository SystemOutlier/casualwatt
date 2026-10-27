# -*- coding: utf-8 -*-
"""
energy/local_energy.py — Profilo energetico causale per inferenza LOCALE.

Formule implementate (sezione 2 della specifica, nessuna invenzione):

    E_attiva = max(0, E_package - P_idle * dt)
    E_ollama = E_attiva * s
    s        = dt_cpu_ollama / dt_cpu_busy

con:
* s              : quota del tempo CPU BUSY di SISTEMA, NON quota sulla
                   capacita'. Il denominatore e' il tempo non-idle di tutti i
                   core nella stessa finestra, non N_eff * dt: sottrarre la
                   baseline e poi moltiplicare per una quota sulla capacita'
                   toglierebbe l'idle due volte, perche' P_idle * dt e' gia'
                   stato sottratto e N_eff * dt include i core inattivi.
                   La formula s = d_ollama / d_busy e' l'unica usata; una
                   quota sulla capacita' non e' implementata e non va usata.
* E_ollama       : STIMA di attribuzione, non una misura per processo. Il
                   contatore package conosce il dominio (PKG), non il
                   processo: E_ollama ripartisce una quantita' derivata con
                   una quota di tempo CPU, e l'equivalenza tempo <-> energia
                   resta un'assunzione dichiarata (protocollo v4, P4.10).
* E_package      : energia package CPU nella finestra della richiesta.
                   METODO PRINCIPALE SU WINDOWS 11 (dal 23/10): "emi-counter"
                   -> contatore package EMI CUMULATIVO (pWh, ioctl documentato
                   sul device del canale energia Intel), letto ai bordi esatti
                   della finestra dal buffer a 0,05 s; nessuna integrazione
                   perche' la grandezza e' gia' energia.
                   Su Windows senza device EMI la misurazione locale e'
                   indisponibile: LibreHardwareMonitor e il suo percorso
                   "power-integration" sono usciti dall'implementazione il
                   27/10/2026 (D18, metodo provato e superato). NIENTE RAPL/
                   perf_event_open/turbostat su Windows, NIENTE stime TDP,
                   NIENTE moltiplicatori arbitrari. Su Linux: contatore RAPL
                   ("rapl"). Su piattaforme non supportate la misurazione
                   locale CPU e' disabilitata con messaggio esplicito
                   (GUI/Ollama/cloud/CSV restano utilizzabili).
* P_idle         : potenza idle calibrata (SESSION.calibrate_idle, contatore
                   EMI su Windows o RAPL su Linux, >=30 s x 3 ripetizioni,
                   mediana);
* dt_cpu_ollama  : secondi CPU (user+system) dell'albero del motore nella
                   finestra;
* dt_cpu_busy    : secondi CPU busy NON-idle di TUTTO il sistema nella
                   stessa finestra. E' il denominatore di s.

La baseline idle e' salvata separatamente in ``baseline_energy_j`` e NON entra
in ``local_energy_j`` ne' in ``end_to_end_energy_j`` (sezioni 12.1/12.3).

GPU:
* NVIDIA dedicata -> catena dichiarata ``nvml-energy`` -> ``nvml-power-
  integral`` -> ``unavailable``. Il contatore cumulativo
  (``nvmlDeviceGetTotalEnergyConsumption``, millijoule, "since the last
  reset": doc NVIDIA verificata il 28-10-2026) si usa per DELTA fra i bordi
  della finestra; se la sonda all'apertura dice che il device non lo espone,
  o il delta e' negativo (reset del driver), o la finestra ha sottofinestre
  escluse che il contatore non sa sottrarre, si integra la POTENZA
  (``nvml-power-integral``) e lo si dichiara in ``gpu_attribution_method``,
  che comincia sempre con il token del percorso usato. In entrambi i casi
  si sottrae la potenza GPU a idle calibrata sullo STESSO intervallo
  (confine: whole-device). La stessa catena vale per le GPU AMD via AMD SMI,
  con prefisso ``amdsmi`` (``amdsmi_get_energy_count``: accumulator x
  counter_resolution in microjoule, doc ROCm verificata il 28-10-2026), ed
  e' il FALLBACK: si usa solo se NVML non risponde, mai in parallelo. Su AMD
  il timestamp del contatore (1 ns) distingue una lettura ferma da uno zero
  legittimo; un delta negativo e' un reset o un avvolgimento e si copre con
  l'integrale, senza clamparlo a zero.
  L'utilizzo medio e' solo campo diagnostico
  (gpu_utilization_share), NON un moltiplicatore: la potenza GPU riflette
  gia' il carico, quindi moltiplicare per lo share conteggierebbe il
  carico due volte. Attribuzione per processo (nvmlDeviceGetProcess-
  Utilization) esposta in gpu_process_energy_j quando disponibile,
  altrimenti N/A con nota;
* iGPU Intel/AMD integrata -> NON viene aggiunta alcuna quota separata a
  local_energy_j quando la sorgente CPU e' il package: l'energia della
  grafica integrata e' GIÀ inclusa nel contatore package. Il dominio PP1
  del record EMI viene letto come campo INFORMATIVO igpu_energy_j, mai
  sommato. La vecchia euristica IGPU_POWER_SHARE e' deprecata e non usata.

Coerenza finestra (correzioni A1/B1): E_package e baseline coprono SEMPRE
lo stesso intervallo [t_start, t_end] ridotto delle sottofinestre escluse:
la baseline e' P_idle * dt_effettiva, mai scalata su una porzione diversa
dell'integrale. Con backend attivo l'energia package e' letta ESATTAMENTE
a t_start/t_end dal contatore cumulativo campionato a 0,05 s (lock del
sampler); il percorso sui campioni interpolati resta solo come
fallback dichiarato nelle note.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import psutil

from .energy_session import SESSION, SystemSample


@dataclass
class LocalEnergyResult:
    duration_s: float = 0.0
    package_energy_j: float = 0.0
    # Valore GREZZO del contatore sulla finestra, senza il clamp a zero di
    # package_energy_j. Un contatore cumulativo non produce incrementi negativi
    # in condizioni normali; se succede, il numero che lo dichiara e' questo.
    package_energy_raw_j: Optional[float] = None
    idle_power_w: float = 0.0
    baseline_energy_j: float = 0.0
    active_energy_j: float = 0.0
    # E_package - baseline CON SEGNO. Negativo significa "la finestra ha
    # consumato meno della baseline": e' un dato, non un errore da azzerare.
    active_energy_raw_j: float = 0.0
    # True solo se la sottrazione ha senso: raw >= 0, P_idle calibrata e
    # package effettivamente letto. Con active_valid=False, active_energy_j
    # (troncato) non e' una quantita' misurabile.
    active_valid: bool = False
    ollama_active_energy_j: float = 0.0
    cpu_time_share: float = 0.0
    # Quota GREZZA d_ollama/d_busy, senza clamp a [0,1]; None quando il
    # denominatore e' nullo. E' il numero che dice se il clamp ha nascosto
    # qualcosa.
    cpu_time_share_raw: Optional[float] = None
    # "" oppure il primo token anomalo per gravita':
    # "d_busy=0" | "d_busy>capacita'" | "d_ollama>d_busy".
    share_anomaly: str = ""
    gpu_available: bool = False
    gpu_device_index: Optional[int] = None
    gpu_board_energy_j: float = 0.0
    gpu_energy_attributed_j: float = 0.0
    gpu_utilization_share: float = 0.0
    # attribuzione per processo NVIDIA (N/A se NVML non la espone)
    gpu_process_energy_j: Optional[float] = None
    # Punto 2: provenienza della potenza idle GPU usata nello scorporo
    # ("calibrated" | "missing"); "" se la GPU dedicata non e' stata misurata.
    gpu_idle_provenance: str = ""
    igpu_energy_j: Optional[float] = None   # informativo, MAI sommato
    package_window_source: str = ""         # exact-counter | samples-fallback
    idle_provenance: Optional[str] = None   # calibrated|session|uncalibrated
    measurement_boundary: str = ""
    cpu_attribution_method: str = ""
    gpu_attribution_method: str = ""
    # canale che ha prodotto package_energy_j di questa riga (emi-counter |
    # rapl | energy-file | unavailable): identico a SESSION.source_method al
    # momento della misura, salvato PER RIGA. I token storici
    # "power-integration"/"librehardwaremonitor*" restano validi per le righe
    # gia' archiviate in experiment_results/, non sono piu' prodotti.
    energy_calculation_method: str = ""
    # ---- provenienza del contatore (contratto alt_lhm §3) ----------------
    # Valori GREZZI agli estremi della finestra, nell'unita' nativa del canale:
    # pWh per EMI, uJ per RAPL. Un campo vuoto dichiara l'assenza; un numero
    # inventato no.
    raw_start: Optional[float] = None
    raw_end: Optional[float] = None
    raw_unit: str = ""
    # Dominio del contatore: PKG per l'energia package, PP1 per l'iGPU.
    domain: str = ""
    # Cadenza REALE (mediana dei delta) del buffer nella finestra, non quella
    # richiesta in config (0,5 s) ne' quella dichiarata dal sampler (0,05 s):
    # sotto spin il tick osservato e' piu' lento del nominale.
    sampling_interval_observed_s: Optional[float] = None
    # Versione del percorso di lettura (emi-reader/..., kernel RAPL).
    backend_version: str = ""
    notes: List[str] = field(default_factory=list)
    # Diagnostica cpu-time-share (per riga)
    ollama_pids_used: str = ""          # lista PID usati, separati da virgola
    d_ollama_cpu_s: float = 0.0         # delta CPU-time Ollama nella finestra
    d_busy_s: float = 0.0               # delta CPU busy nella finestra
    n_samples_in_window: int = 0        # campioni nella finestra [t_start, t_end]
    # ---- denominatore dello share dichiarato (rev_metodo §2b) ------------
    # La quota e' d_ollama/d_busy, ma il rapporto ha senso solo se si dice su
    # QUALE intervallo e' calcolato e quale capacita' era disponibile:
    # d_busy_s <= cpu_busy_capacity_cores * cpu_share_window_s e' la
    # disuguaglianza verificabile a posteriori. La finestra e' quella
    # dell'energia, gia' ridotta delle sottofinestre escluse.
    cpu_share_window_s: float = 0.0
    cpu_busy_capacity_cores: int = 0    # core LOGICI (psutil percpu)
    # Passo minimo non nullo osservato nei cpu_times per processo: la
    # granularita' reale del contatore (il tick del kernel), non i 100 ns
    # nominali di GetProcessTimes. Una finestra confrontabile con questo passo
    # ha un delta CPU quantizzato.
    cpu_time_resolution_s: Optional[float] = None
    # True se un processo presente a t_start non era piu' leggibile a t_end:
    # il suo tempo CPU non e' nel numeratore e la finestra non e' integra.
    # Non e' una prova indipendente da ``engine_tree_changed``: sotto la
    # definizione congelata (protocollo v4) descrivono lo STESSO insieme --
    # questo e' il nome storico, l'altro quello che governa l'invalidazione.
    worker_exit_in_window: bool = False
    # ---- P5: bordo di misura e integrita' dell'albero ---------------------
    # True quando l'insieme delle identita' a t_end non e' un sovrainsieme di
    # quello a t_start: un worker e' sparito (o il PID e' stato riusato).
    # In quel caso la sua CPU non e' nel numeratore e s e' sottostimato in una
    # direzione sola: la quota NON si calcola, non si sostituisce con un
    # fallback che eredita la stessa perdita.
    engine_tree_changed: bool = False
    tree_born: str = ""                 # identita' nate, "pid:create_time;..."
    tree_lost: str = ""                 # identita' perse, stesso formato
    # Provenienza della quota: direct-edge | samples-fallback |
    # not-computed-tree-changed | not-observable. Un numero senza provenienza
    # non dice da dove viene.
    cpu_share_source: str = ""
    # False quando la quota non e' una stima utilizzabile: albero cambiato,
    # denominatore nullo, numeratore non osservabile o d_ollama > d_busy.
    # ``cpu_time_share = 0.0`` non basta: da solo e' indistinguibile da
    # "nessuna CPU usata".
    cpu_time_share_valid: bool = False
    # Baseline del blocco (P_pre, mediana di tre finestre) applicata a questa
    # riga; None = si usa lo stato della sessione. P_post non entra mai qui.
    baseline_pre_w: Optional[float] = None
    # Finestra ENERGETICA dai bordi del contatore, distinta dalla finestra
    # CPU: dt_W_s e' il tempo su cui e' stato letto il contatore,
    # cpu_share_window_s quello su cui sono stati letti i cpu_times.
    dt_W_s: float = 0.0
    # emi-counter-ts | python-monotonic | python-window ("" = non dichiarato)
    edge_time_source: str = ""
    edge_spread_s: Optional[float] = None
    emi_ts_start_100ns: Optional[int] = None
    emi_ts_end_100ns: Optional[int] = None
    # direct-ioctl | buffer-interp | samples-fallback | unavailable
    emi_edge_source: str = ""
    edge_start_utc: str = ""
    edge_end_utc: str = ""


class CasualWattLocalEnergyProfiler:
    """Profilatore causale: misura la finestra [t_start, t_end] sui campioni."""

    def __init__(self) -> None:
        self.session = SESSION

    # ------------------------------------------------------------------ core
    def profile_window(
        self,
        t_start: float,
        t_end: float,
        ollama_pids: Optional[List[int]] = None,
        direct_io_delta: Optional[float] = None,
        direct_cpu_delta: Optional[float] = None,
        direct_busy_delta: Optional[float] = None,
        worker_exit_in_window: bool = False,
        exclude_windows: Optional[List[tuple]] = None,
        edge_start: Optional[Dict[str, object]] = None,
        edge_end: Optional[Dict[str, object]] = None,
        baseline_pre_w: Optional[float] = None,
        engine_tree_changed: bool = False,
        tree_born: str = "",
        tree_lost: str = "",
    ) -> LocalEnergyResult:
        """Profilazione causale della finestra [t_start, t_end].

        direct_cpu_delta / direct_busy_delta: numeratore e denominatore dello
        share letti agli stessi estremi. Quando forniti, sostituiscono i delta
        ricavati dai campioni. Con sottofinestre escluse il denominatore
        diretto copre il segmento di inferenza (la stessa lettura del
        numeratore), non le sottofinestre escluse: la nota della riga lo dice.

        exclude_windows: lista di (a, b) da SCORPORARE dal calcolo (es. la
        chiamata al LLM Judge, che avviene DOPO l'inferenza e non deve essere
        attribuita al modello valutato). Le finestre escluse riducono dt,
        sottraggono il tempo busy Ollama e accorciano la coda dei campioni per
        lo share CPU — tutto dichiarato nelle note.

        edge_start / edge_end: bordo di misura (``read_measurement_edge``).
        Quando ci sono entrambi, la finestra energetica e' quella del
        contatore: l'energia e' la differenza diretta dei due valori (una
        IOCTL per bordo, nessuna interpolazione) e ``dt_W_s`` e' la differenza
        dei timestamp 100 ns del PKG. Se il contatore manca, l'energia torna
        al buffer e ``emi_edge_source`` lo dichiara. Con sottofinestre escluse
        la differenza diretta non puo' scorporarle: si usa il percorso buffer,
        gia' ridotto, e lo dichiara.

        baseline_pre_w: P_pre del blocco (P1.5). Sostituisce lo stato
        mutabile della sessione, cosi' le righe dello stesso blocco sono
        confrontabili; P_post non entra mai nella sottrazione.

        engine_tree_changed: se True un worker presente a t_start non c'era
        piu' a t_end (o il PID e' stato riusato). La quota non si calcola:
        ``cpu_time_share = 0.0`` con ``cpu_time_share_valid = False`` e
        ``cpu_share_source = "not-computed-tree-changed"``. Gli ingressi
        grezzi (d_ollama, d_busy, identita' nate/perse) restano nella riga.
        """
        res = LocalEnergyResult()
        notes: List[str] = []
        dt = max(t_end - t_start, 1e-6)

        # ---- P5: la finestra energetica e' quella del contatore ------------
        # I bordi sono letti sullo stesso orologio del buffer (monotono, prima
        # dell'IOCTL): usarli come estremi dell'energia evita che dt e
        # integrazione descrivano due intervalli diversi. Senza bordi resta la
        # finestra Python di sempre, dichiarata.
        has_edges = edge_start is not None and edge_end is not None
        if has_edges:
            win_start = float(edge_start.get("t_counter_mono", t_start))
            win_end = float(edge_end.get("t_counter_mono", t_end))
            if win_end > win_start:
                t_start, t_end = win_start, win_end
                dt = win_end - win_start
            else:
                has_edges = False
                notes.append(
                    "bordi di misura non ordinati (t_start >= t_end): "
                    "finestra Python usata, nessun dt dai contatori")

        # ---- scorporo sottofinestre escluse (es. LLM Judge) ----------------
        excl = sorted(
            [(max(a, t_start), min(b, t_end)) for a, b in (exclude_windows or [])
             if b > t_start and a < t_end and max(b, t_end) - min(a, t_start) > 0],
            key=lambda w: w[0],
        )
        excl_s = sum(b - a for a, b in excl)
        if excl_s > 0:
            excl_txt = ", ".join(f"[{a:.2f}-{b:.2f}]" for a, b in excl)
            notes_excl = (
                f"sottofinestre escluse dal profilo ({excl_s:.2f} s: {excl_txt}): "
                "energia del LLM Judge SCORPORATA dal modello valutato"
            )
            dt = max(dt - excl_s, 1e-6)
        else:
            notes_excl = ""

        res.duration_s = dt
        res.dt_W_s = round(dt, 6)
        if has_edges:
            dt_w, edge_time_source = self._edge_dt_w(edge_start, edge_end)
            if excl_s > 0:
                # l'esclusione e' misurata in secondi monotoni, dt_W in un'altra
                # base: si usa la finestra Python gia' ridotta, dichiarata.
                dt_w = max((t_end - t_start) - excl_s, 1e-6)
                edge_time_source = "python-monotonic"
            elif dt_w is None:
                # nessun timestamp utilizzabile sui bordi: la finestra Python
                # resta l'unico intervallo dichiarabile.
                dt_w = max(t_end - t_start, 1e-6)
                edge_time_source = "python-monotonic"
            res.dt_W_s = round(dt_w, 6)
            res.duration_s = res.dt_W_s
            res.edge_time_source = edge_time_source
            res.edge_start_utc = str(edge_start.get("t_wall_utc", "") or "")
            res.edge_end_utc = str(edge_end.get("t_wall_utc", "") or "")
            res.edge_spread_s = max(
                float(edge_start.get("edge_spread_s", 0.0) or 0.0),
                float(edge_end.get("edge_spread_s", 0.0) or 0.0),
            )
            res.emi_ts_start_100ns = self._edge_counter_ts(edge_start)
            res.emi_ts_end_100ns = self._edge_counter_ts(edge_end)
        else:
            res.edge_time_source = "python-window"

        samples: List[SystemSample] = self.session.samples_between(t_start, t_end)
        if notes_excl:
            notes.append(notes_excl)
        
        # Diagnostica: numero campioni nella finestra
        res.n_samples_in_window = len(samples)

        # ---------------------------------------------------------- CPU part
        busy_first = samples[0].cpu_busy_seconds if samples else 0.0
        busy_last = samples[-1].cpu_busy_seconds if samples else 0.0

        idle_power_w = self.session.idle_power_w
        idle_proven = getattr(self.session, "idle_provenance", None)
        if baseline_pre_w is not None:
            # P1.5: P_pre del blocco, non lo stato mutabile della sessione.
            # Il valore viene dal runner, che ha gia' calibrato (3 x >=30 s,
            # mediana); il post non entra mai qui.
            idle_power_w = float(baseline_pre_w)
            res.baseline_pre_w = round(float(baseline_pre_w), 6)
            notes.append(
                f"baseline del blocco P_pre={float(baseline_pre_w):.3f} W "
                "applicata a questa riga (override dello stato di sessione)"
            )
        if idle_power_w is None:
            # B3: NESSUNA micro-calibrazione in mezzo al benchmark (blocca e
            # avviene a macchina calda -> sovrastima P_idle). Se l'utente non
            # ha calibrato, la baseline e' 0 con provenienza dichiarata.
            idle_power_w = 0.0
            idle_proven = "uncalibrated"
            notes.append(
                "P_idle NON calibrato (provenienza 'uncalibrated'): "
                "baseline_energy_j = 0; eseguire 'Calibra idle' dalla GUI "
                "(>=30 s x 3 ripetizioni, PC a riposo) prima del benchmark"
            )
        res.idle_power_w = float(idle_power_w or 0.0)
        res.idle_provenance = idle_proven

        method = self.session.source_method
        # Un solo token che dice DA QUALE CANALE viene il package_energy_j di
        # QUESTA riga. Fino ad ora il nome del canale compariva solo dentro
        # stringhe composite (cpu_attribution_method, measurement_boundary),
        # quindi un CSV di risultati che accoda righe di run fatti con canali
        # diversi -- emi-counter, rapl, energy-file -- non era
        # auto-descrittivo senza il file di run metadata.
        res.energy_calculation_method = method

        # ---- provenienza del contatore (raw + cadenza reale + versione) ---
        # Contratto di alt_lhm §3: senza i valori grezzi e la cadenza
        # osservata, package_energy_j richiede di fidarsi del buffer. Qui si
        # persiste cio' che si puo' dichiarare; un canale senza contatore
        # lascia i grezzi vuoti, non a zero.
        prov_fn = getattr(self.session, "window_counter_provenance", None)
        if callable(prov_fn):
            try:
                prov = prov_fn(t_start, t_end, "pkg") or {}
            except Exception as exc:  # mai un crash: campo assente + nota
                prov = {}
                notes.append(
                    f"provenienza contatore non disponibile ({type(exc).__name__})")
            res.raw_start = prov.get("raw_start")
            res.raw_end = prov.get("raw_end")
            res.raw_unit = prov.get("raw_unit", "") or ""
            res.domain = prov.get("domain", "") or ""
            res.sampling_interval_observed_s = prov.get(
                "sampling_interval_observed_s")
            res.backend_version = prov.get("backend_version", "") or ""

        # ---- B1: energia package ESATTA ai bordi della finestra -----------
        # Con backend attivo si legge il contatore integrato a 0,05 s (stesso
        # lock del thread di integrazione) esattamente a t_start e t_end:
        # nessuna interpolazione sui campioni a ~0,25-0,5 s. Il percorso sui
        # campioni resta SOLO come fallback dichiarato nelle note.
        e_package: Optional[float] = None
        # P5: con la coppia di bordi e nessuna sottofinestra da scorporare,
        # l'energia e' la DIFFERENZA dei due valori del contatore: nessuna
        # interpolazione fra campioni, nessun percorso sul buffer. Se il
        # contatore manca si torna al buffer e il token lo dichiara.
        if has_edges and not excl:
            e_edge = self._edge_energy_j(edge_start, edge_end)
            if e_edge is not None:
                e_package = e_edge
                res.emi_edge_source = "direct-ioctl"
                notes.append(
                    "energia package = differenza del contatore fra i due "
                    "bordi (una IOCTL per bordo, nessuna interpolazione)")
                # I grezzi della riga devono essere quelli dei BORDI, non
                # quelli interpolati dal buffer: il campo cita il numero
                # effettivamente letto agli estremi.
                pkg_raw_0 = self._edge_raw_value(edge_start)
                pkg_raw_1 = self._edge_raw_value(edge_end)
                if pkg_raw_0 is not None and pkg_raw_1 is not None:
                    res.raw_start = pkg_raw_0
                    res.raw_end = pkg_raw_1
                    res.raw_unit = (
                        self._edge_raw_unit(edge_start)
                        or self._edge_raw_unit(edge_end) or "pWh")
                    res.domain = "pkg"
            else:
                edge_reason = (
                    str(edge_start.get("counter_error") or "")
                    or str(edge_end.get("counter_error") or "")
                    or "valore assente o non crescente"
                )
                notes.append(
                    "differenza diretta del contatore non disponibile ai "
                    f"bordi ({edge_reason}): energia dal buffer a 0,05 s "
                    "(interpolazione dichiarata, emi_edge_source=buffer-interp)")
        exact_fn = getattr(self.session, "package_energy_exact_between", None)
        if e_package is None and callable(exact_fn):
            try:
                e_package = exact_fn(t_start, t_end, excl)
            except Exception as exc:  # mai un crash: degrada al fallback
                notes.append(f"lettura esatta contatore fallita ({type(exc).__name__})")
                e_package = None
            if e_package is not None and has_edges:
                res.emi_edge_source = "buffer-interp"
                if excl:
                    notes.append(
                        "sottofinestre escluse: la differenza diretta fra i "
                        "bordi non puo' scorporarle; energia dal buffer gia' "
                        "ridotto (emi_edge_source=buffer-interp)")
        if e_package is not None and e_package >= 0.0:
            res.package_window_source = "exact-counter"
            if not res.emi_edge_source:
                res.emi_edge_source = "buffer-interp"
            if res.emi_edge_source == "direct-ioctl":
                _edge_txt = (
                    "window read exactly as the difference of the counter at "
                    "the two measurement edges (one IOCTL per edge; no "
                    "interpolation, no integration)"
                )
            else:
                _edge_txt = (
                    "window read exactly at t_start/t_end from the 0.05 s "
                    + ("cumulative package counter buffer (no integration)"
                       if method in ("emi-counter", "pawnio-counter")
                       else "integration counter")
                )
            res.cpu_attribution_method = (
                f"{method}; cpu-time-share attribution, ESTIMATE "
                "(E_attiva * d_ollama/d_busy; share of system BUSY time, "
                "not of capacity); " + _edge_txt
            )
        else:
            # FALLBACK dichiarato: differenza dei campioni interpolati
            pkg_first = next((s.package_energy_j for s in samples if s.package_energy_j is not None), None)
            pkg_last = next(
                (s.package_energy_j for s in reversed(samples) if s.package_energy_j is not None),
                None,
            )
            if pkg_first is not None and pkg_last is not None and pkg_last >= pkg_first:
                res.package_window_source = "samples-fallback"
                res.emi_edge_source = "samples-fallback"
                notes.append(
                    "fallback dichiarato: E_package da campioni interpolati "
                    f"(~{self.session.interval_s}s) perche' il contatore esatto "
                    "non era leggibile ai bordi della finestra"
                )
                e_package = 0.0
                prev = samples[0]
                for cur in samples[1:]:
                    if cur.package_energy_j is not None \
                            and prev.package_energy_j is not None:
                        e_package += max(cur.package_energy_j - prev.package_energy_j, 0.0)
                    prev = cur
                res.cpu_attribution_method = (
                    f"{method}; cpu-time-share attribution, ESTIMATE "
                    "(E_attiva * d_ollama/d_busy; share of system BUSY time, "
                    "not of capacity)"
                )
            else:
                e_package = 0.0
                res.package_window_source = "unavailable"
                res.emi_edge_source = "unavailable"
                notes.append(
                    "nessun campione package nella finestra: misurazione locale "
                    "dichiarata indisponibile (metodo attivo: "
                    f"'{self.session.source_method}')"
                )
                res.cpu_attribution_method = "unavailable"

        res.package_energy_j = round(max(e_package, 0.0), 6)
        res.package_energy_raw_j = round(float(e_package), 6)
        # ---- A1: baseline SEMPRE sulla stessa finestra dell'integrale -----
        # La vecchia logica "coda inattiva" scalava la baseline su
        # [t_start, t_last_active] mentre E_package copriva tutta la
        # finestra: E_attiva accumulava P_idle * durata_coda (sovrastima).
        # Ora le due grandezze coprono lo STESSO intervallo:
        #     baseline = P_idle * dt_W_s   (finestra del contatore, gia'
        #     ridotta delle sottofinestre escluse, coerenza B2)
        # Con i bordi di misura dt_W_s e' il tempo dei timestamp del
        # contatore, non la finestra Python: baseline ed energia restano
        # sullo stesso intervallo fisico.
        res.baseline_energy_j = round(
            res.idle_power_w * float(res.dt_W_s or dt), 6)
        # La sottrazione si conserva con il segno: active_energy_j resta
        # troncato a zero per compatibilita' con i CSV gia' scritti, ma la
        # riga dichiara ora il valore grezzo e la validita' della grandezza.
        active_raw = float(e_package) - res.baseline_energy_j
        active = max(active_raw, 0.0)
        res.active_energy_raw_j = round(active_raw, 6)
        res.active_energy_j = round(active, 6)
        idle_missing = (
            res.idle_provenance is None
            or res.idle_provenance == "uncalibrated"
        )
        res.active_valid = bool(
            active_raw >= 0.0
            and not idle_missing
            and res.package_window_source != "unavailable"
        )
        if active_raw < 0.0:
            notes.append(
                f"E_attiva grezza {active_raw:+.3f} J < 0 (package "
                f"{float(e_package):.3f} J < baseline {res.baseline_energy_j:.3f} J): "
                "active_energy_j troncato a 0, active_valid=False"
            )

        # ---- B2: cpu busy sugli intervalli NON esclusi (coerenza) ---------
        busy_direct = (direct_busy_delta is not None and direct_busy_delta >= 0.0)
        if busy_direct:
            # Denominatore letto agli stessi estremi del numeratore (una sola
            # chiamata): e' la lettura coerente con direct_cpu_delta. Con
            # sottofinestre escluse copre il segmento di inferenza, non le
            # escluse, e la nota lo dichiara.
            dt_cpu_busy = float(direct_busy_delta)
            notes.append(
                "cpu busy di sistema da lettura esatta agli estremi, nella "
                "stessa chiamata del numeratore"
                + ("; il denominatore copre il segmento di inferenza, non le "
                   "sottofinestre escluse" if excl else "")
            )
        elif excl:
            def _in_excl(a: float, b: float) -> bool:
                return any(not (b <= x or a >= y) for x, y in excl)
            pairs = list(zip(samples[1:], samples[:-1]))
            kept = [(p, q) for p, q in pairs if not _in_excl(q.t, p.t)]
            d_busy = 0.0
            for p, q in kept:
                d_busy += max(p.cpu_busy_seconds - q.cpu_busy_seconds, 0.0)
            dt_cpu_busy = d_busy
        else:
            dt_cpu_busy = max(busy_last - busy_first, 0.0)

        # delta CPU-time albero Ollama: preferisce letture esatte agli estremi
        # [t_start, t_end] (direct_cpu_delta), fallback ai campioni se assente
        cpu_direct = (direct_cpu_delta is not None and direct_cpu_delta >= 0)
        if cpu_direct:
            d_ollama = direct_cpu_delta
            notes.append("cpu-time Ollama da lettura esatta agli estremi [t_start, t_end]")
        elif excl:
            # scorporo judge: somma i delta di ollama_cpu_seconds SOLO sugli
            # intervalli non esclusi (p = campione piu' recente, q = precedente)
            d_ollama = 0.0
            for p, q in kept:
                if p.ollama_pids and q.ollama_pids:
                    d_ollama += max(p.ollama_cpu_seconds - q.ollama_cpu_seconds, 0.0)
        else:
            d_ollama = self._ollama_cpu_delta(samples)
        d_ollama_observed = d_ollama is not None
        if not d_ollama_observed:
            d_ollama = 0.0
            notes.append(
                "cpu-time Ollama non osservabile: share = 0.0 con "
                "cpu_time_share_valid=False (conservativo, nessun valore "
                "inventato)")
        # Il denominatore si dichiara: intervallo del rapporto = tratto in cui
        # sono stati letti i cpu_times (t_cpu_mid sui bordi, altrimenti la
        # finestra energetica) e capacita' = core logici su cui e' aggregato
        # cpu_busy_seconds. Con i bordi la disuguaglianza d_busy <= core *
        # cpu_share_window_s torna verificabile.
        share_win = dt
        if has_edges:
            try:
                mid0 = float(edge_start.get("t_cpu_mid"))
                mid1 = float(edge_end.get("t_cpu_mid"))
            except (TypeError, ValueError):
                mid0 = mid1 = 0.0
            if mid1 > mid0:
                share_win = mid1 - mid0
        res.cpu_share_window_s = round(share_win, 6)
        res.cpu_busy_capacity_cores = int(psutil.cpu_count(logical=True) or 0)
        # Il rapporto si calcola GREZZO: un clamp silenzioso a [0,1] rendeva
        # indistinguibile un d_ollama > d_busy (contabilita' incoerente, es.
        # letture non simultanee o CPU-time perso) da uno share di 1 legittimo.
        capacity_s = res.cpu_busy_capacity_cores * res.cpu_share_window_s
        share_raw: Optional[float] = None
        anomalies: List[str] = []
        if dt_cpu_busy <= 0.0:
            anomalies.append("d_busy=0")
        else:
            share_raw = d_ollama / dt_cpu_busy
            if capacity_s > 0.0 and dt_cpu_busy > capacity_s + 1e-6:
                anomalies.append("d_busy>capacita'")
            if d_ollama > dt_cpu_busy:
                anomalies.append("d_ollama>d_busy")
        res.engine_tree_changed = bool(engine_tree_changed)
        res.tree_born = str(tree_born or "")
        res.tree_lost = str(tree_lost or "")
        # La colonna porta UNA anomalia (la prima per gravita': denominatore
        # nullo, denominatore impossibile, numeratore maggiore del denominatore);
        # le note le portano tutte, cosi' nessuna viene persa.
        res.share_anomaly = anomalies[0] if anomalies else ""
        share = 0.0 if share_raw is None else min(max(share_raw, 0.0), 1.0)
        res.cpu_time_share = round(share, 6)
        if engine_tree_changed:
            # D1: la riga resta, con gli ingressi grezzi e i flag. Il valore
            # convenzionale zero non e' una stima: la quota non si calcola e
            # non alimenta ne' l'attribuzione ne' il confronto (P6.6).
            res.cpu_share_source = "not-computed-tree-changed"
            res.cpu_time_share_raw = None
            res.share_anomaly = ""
            res.cpu_time_share = 0.0
            res.ollama_active_energy_j = 0.0
            res.cpu_time_share_valid = False
            notes.append(
                "engine_tree_changed=True (persi: "
                f"{res.tree_lost or '-'}; nati: {res.tree_born or '-'}): "
                "la quota non si calcola, cpu_time_share=0.0 e "
                "ollama_active_energy_j=0.0 con cpu_time_share_valid=False; "
                "d_ollama_cpu_s e d_busy_s restano ingressi grezzi, non una "
                "stima (la riga non entra nel confronto di concordanza)")
        else:
            res.cpu_time_share_raw = (
                round(share_raw, 6) if share_raw is not None else None
            )
            if not d_ollama_observed:
                res.cpu_share_source = "not-observable"
            elif cpu_direct and busy_direct:
                res.cpu_share_source = "direct-edge"
            else:
                res.cpu_share_source = "samples-fallback"
            # D5: valida solo se il denominatore esiste, il numeratore e'
            # osservabile e la quota non e' stata clampata da un rapporto
            # incoerente. L'anomalia di capacita' resta un flag, non invalida
            # il rapporto (d_busy e' comunque il denominatore misurato).
            res.cpu_time_share_valid = bool(
                d_ollama_observed
                and share_raw is not None
                and d_ollama <= dt_cpu_busy + 1e-9
            )
            # D1: una riga non valida conserva il numero convenzionale ma non
            # alimenta l'attribuzione.
            res.ollama_active_energy_j = (
                round(active * share, 6)
                if res.cpu_time_share_valid else 0.0
            )
            for anomaly in anomalies:
                notes.append(
                    f"anomalia dello share ({anomaly}): d_ollama={d_ollama:.6f} s, "
                    f"d_busy={dt_cpu_busy:.6f} s, capacita'={capacity_s:.6f} s; "
                    "cpu_time_share resta limitato a [0,1]"
                )

        # D4: i due nomi descrivono lo stesso insieme, ma solo
        # ``engine_tree_changed`` (passato dal runner v4) invalida la quota.
        # Il percorso storico passa solo ``worker_exit_in_window``: qui non si
        # cambia il numero che ha sempre prodotto, ma lo si dichiara non
        # valido e lo si dice, invece di lasciar credere che sia integro.
        if worker_exit_in_window and not engine_tree_changed:
            res.cpu_time_share_valid = False
            notes.append(
                "worker_exit_in_window=True con engine_tree_changed=False: il "
                "chiamante non ha passato il flag v4; la quota e' stata "
                "calcolata come nel percorso storico e cpu_time_share_valid e' "
                "False (stima non integra, non usare nel confronto)")

        # ---- integrita' della finestra: processo sparito e quantizzazione --
        res.worker_exit_in_window = bool(worker_exit_in_window)
        if worker_exit_in_window:
            notes.append(
                "worker_exit_in_window=True: un processo dell'albero presente "
                "a t_start non era piu' leggibile a t_end; il suo tempo CPU "
                "non e' nel numeratore e la finestra non e' integra. D4: sotto "
                "la definizione congelata e' lo STESSO insieme di "
                "engine_tree_changed (nome storico vs nome del protocollo, non "
                "due prove indipendenti); l'invalidazione e' governata da "
                "engine_tree_changed, che il runner v4 passa esplicitamente")
        res.cpu_time_resolution_s = getattr(
            self.session, "cpu_time_resolution_s", None)
        if (res.cpu_time_resolution_s
                and (res.cpu_share_window_s or dt)
                < 30.0 * float(res.cpu_time_resolution_s)):
            notes.append(
                f"finestra {res.cpu_share_window_s or dt:.3f} s < 30 x "
                f"risoluzione osservata dei cpu_times "
                f"({float(res.cpu_time_resolution_s):.4f} s): il "
                "delta CPU puo' essere quantizzato"
            )
        
        # Diagnostica: valori usati per il calcolo dello share
        res.d_ollama_cpu_s = round(d_ollama, 6)
        res.d_busy_s = round(dt_cpu_busy, 6)
        # PID usati: preferisci quelli passati come parametro, altrimenti dai campioni
        if ollama_pids:
            res.ollama_pids_used = ",".join(str(p) for p in ollama_pids)
        else:
            pids_used = []
            for s in reversed(samples):
                if s.ollama_pids:
                    pids_used = list(s.ollama_pids)
                    break
            res.ollama_pids_used = ",".join(str(p) for p in pids_used) if pids_used else ""
        
        # Nota esplicita se share=0 (non quando la quota e' invalidata: in quel
        # caso la nota dell'invalidazione e' quella che spiega lo zero).
        if (share == 0.0 and res.n_samples_in_window > 0
                and not engine_tree_changed and d_ollama_observed):
            notes.append(
                f"cpu_time_share=0: d_ollama_cpu_s={d_ollama:.6f}, "
                f"d_busy_s={dt_cpu_busy:.6f}, n_samples={len(samples)}"
            )

        # ---------------------------------------------------------- GPU part
        gpu_mon = self.session._gpu
        gpu_samples = [s for s in samples if s.gpu_power_w is not None]
        counter_samples = [s for s in samples
                           if getattr(s, "gpu_energy_mj", None) is not None]
        if gpu_mon.available and len(gpu_samples) >= 2:
            res.gpu_available = True
            res.gpu_device_index = gpu_mon.index
            util_sum = 0.0
            util_n = 0
            for cur in gpu_samples[1:]:
                if cur.gpu_util_pct is not None:
                    util_sum += cur.gpu_util_pct
                    util_n += 1
            board_j = 0.0
            gpu_dt = 0.0
            gpu_backend = getattr(gpu_mon, "backend", "nvml")
            # Catena dichiarata: contatore cumulativo -> integrale della
            # potenza -> nessun numero. Il contatore si usa per DELTA fra i
            # bordi e solo senza sottofinestre escluse: un delta non sa
            # sottrarre l'energia del judge, e sottrarla con la potenza
            # mescolerebbe due percorsi nella stessa riga.
            counter_ok = bool(getattr(gpu_mon, "energy_counter", False)
                              and len(counter_samples) >= 2 and not excl)
            if counter_ok:
                first, last = counter_samples[0], counter_samples[-1]
                d_mj = float(last.gpu_energy_mj) - float(first.gpu_energy_mj)
                span = last.t - first.t
                # Controllo sul timestamp del device (solo AMD SMI lo espone):
                # se il device non ha aggiornato il contatore, due letture
                # uguali non sono un intervallo di energia.
                ts0 = getattr(first, "gpu_energy_ts_ns", None)
                ts1 = getattr(last, "gpu_energy_ts_ns", None)
                ts_moved = ts0 is None or ts1 is None or ts1 > ts0
                if gpu_backend == "amdsmi" and (ts0 is None or ts1 is None):
                    notes.append(
                        "contatore AMD SMI senza timestamp: controllo di "
                        "avanzamento non applicato")
                platform = getattr(gpu_mon, "platform_context", "")
                platform_txt = (f", platform={platform}"
                                if platform and platform != "unknown" else "")
                if not ts_moved:
                    counter_ok = False
                    notes.append(
                        f"timestamp del contatore {gpu_backend} fermo "
                        f"({ts0} ns): lettura non valida, si integra la potenza")
                elif d_mj < 0.0 or span <= 0.0:
                    # Nessun clamp a zero: un delta negativo e' un reset o un
                    # avvolgimento del contatore, non energia negativa. La
                    # finestra si copre con l'integrale e il metodo lo dichiara.
                    counter_ok = False
                    notes.append(
                        f"contatore {gpu_backend} non utilizzabile in questa "
                        f"finestra (delta {d_mj:.0f} mJ su {span:.6f} s): "
                        "reset o avvolgimento del contatore; si integra la "
                        "potenza, il delta non si clampa a zero")
                else:
                    board_j = d_mj / 1000.0
                    gpu_dt = span
                    method_txt = (f"{gpu_backend}-energy (delta {d_mj:.0f} mJ "
                                  f"over {span:.3f}s, counter since last reset"
                                  f"{platform_txt})")
                    if d_mj == 0.0:
                        notes.append(
                            f"contatore {gpu_backend} fermo con timestamp che "
                            "avanza: energia zero nella finestra, non una "
                            "lettura mancante")
            if not counter_ok:
                # integrazione trapezoidale del power draw + dt REALE coperto
                prev = gpu_samples[0]

                def _gpu_excl(a, b):
                    return any(not (b <= x or a >= y) for x, y in excl)
                for cur in gpu_samples[1:]:
                    seg_dt = cur.t - prev.t
                    if seg_dt > 0 and not (excl and _gpu_excl(prev.t, cur.t)):
                        board_j += ((prev.gpu_power_w + cur.gpu_power_w) / 2.0) * seg_dt
                        gpu_dt += seg_dt
                    prev = cur
                power_field = getattr(gpu_mon, "power_field", "")
                power_unit = getattr(gpu_mon, "power_unit", "")
                field_txt = (f", power={power_field} [{power_unit}]"
                             if power_field else "")
                method_txt = (f"{gpu_backend}-power-integral (integrated span "
                              f"{gpu_dt:.3f}s{field_txt})")
            idle_gpu_raw = getattr(self.session, "idle_gpu_power_w", None)
            idle_gpu_w = float(idle_gpu_raw) if idle_gpu_raw else 0.0
            # Punto 2: provenienza dell'idle GPU. Se manca (o e' 0) lo scorporo
            # non avviene: l'energia attribuita e' la POTENZA TOTALE della
            # scheda, quindi una sovrastima — dichiarata nel campo e nelle note.
            res.gpu_idle_provenance = "calibrated" if idle_gpu_w > 0.0 else "missing"
            # A2: NESSUNA moltiplicazione per lo share di utilizzo: la potenza
            # board riflette gia' il carico. Attribuzione whole-device:
            #     E_gpu_attr = max(board_j - P_idle_gpu * dt_gpu, 0)
            # con dt_gpu = intervallo reale coperto dall'integrale (coerenza).
            active_gpu_j = max(board_j - idle_gpu_w * gpu_dt, 0.0)
            util_share = (util_sum / util_n / 100.0) if util_n else 1.0
            res.gpu_board_energy_j = round(board_j, 6)
            res.gpu_utilization_share = round(util_share, 6)  # SOLO diagnostico
            res.gpu_energy_attributed_j = round(active_gpu_j, 6)
            idle_txt = ("calibrated idle" if res.gpu_idle_provenance == "calibrated"
                        else "NO idle baseline (gpu_idle_provenance=missing)")
            res.gpu_attribution_method = (
                f"{method_txt} minus {idle_txt} over the same span; "
                "boundary=whole-device; utilization kept as diagnostic field "
                "only (NOT a multiplier)"
            )
            notes.append(
                f"GPU '{gpu_mon.name}': board {board_j:.2f} J, attribuiti "
                f"{res.gpu_energy_attributed_j:.2f} J (whole-device, no double count)"
            )
            if res.gpu_idle_provenance == "missing":
                notes.append(
                    "idle GPU non calibrato: energia GPU = potenza totale della "
                    "scheda, sovrastima (eseguire 'Calibra idle' con GPU a riposo)"
                )
            # attribuzione per processo (opzionale, dichiarata)
            proc_fn = getattr(gpu_mon, "process_energy_j", None)
            if callable(proc_fn):
                try:
                    pj = proc_fn(t_start, t_end, ollama_pids)
                    if pj is not None:
                        res.gpu_process_energy_j = round(pj, 6)
                        notes.append("GPU: attribuzione per processo NVML disponibile")
                    else:
                        notes.append(
                            "GPU: nvmlDeviceGetProcessUtilization non disponibile "
                            "per i PID Ollama -> gpu_process_energy_j = N/A"
                        )
                except Exception:
                    notes.append("GPU process-level attribution unavailable (N/A)")
            else:
                notes.append(
                    "GPU process-level attribution non supportata dal monitor "
                    "attivo -> gpu_process_energy_j = N/A"
                )
        elif method in ("emi-counter", "pawnio-counter"):
            # A3: iGPU Intel/AMD integrata — il sensore 'CPU Package' INCLUDE
            # gia' la grafica: NON si aggiunge ALCUN termine a local_energy_j
            # e NON esiste piu' l'euristica IGPU_POWER_SHARE (deprecata).
            res.gpu_attribution_method = (
                "igpu-included-in-package (no separate term added; "
                "IGPU_POWER_SHARE heuristic deprecated and unused)"
            )
            igpu_fn = getattr(self.session, "read_igpu_energy_j", None)
            if callable(igpu_fn):
                try:
                    res.igpu_energy_j = igpu_fn(t_start, t_end, excl)
                except Exception:
                    res.igpu_energy_j = None
            if res.igpu_energy_j is not None:
                notes.append(
                    "iGPU: contatore PP1 del record EMI, delta letto ai bordi "
                    "di finestra (stessa IOCTL del package, nessuna "
                    "integrazione) come campo INFORMATIVO igpu_energy_j "
                    "(gia' incluso nel package, NON sommato)"
                )
            else:
                why = getattr(self.session, "igpu_unavailable_reason", None)
                notes.append(
                    f"iGPU: metodo {method}, dominio PP1 non espresso"
                    + (f" ({why})" if why else "")
                    + "; energia iGPU inclusa nel package "
                    "(dichiarato, nessuna quota inventata)"
                )
        else:
            res.gpu_attribution_method = "not-applicable"

        # ------------------------------------------------------- boundary
        # B2: le sottofinestre escluse sono gia' state rimosse alla fonte
        # (lettura esatta del contatore sugli intervalli tenuti, busy e
        # cpu-time Ollama sugli stessi intervalli). Nessuno scaling temporale.
        src_desc = {
            "emi-counter": (
                "Windows EMI package energy counter (cumulative pWh, documented "
                "IOCTL on the Intel energy channel device; window edges read "
                "from the 0.05 s cumulative-counter buffer; no integration, "
                "no elevated token required)"
            ),
            "pawnio-counter": (
                "Windows MSR package energy counter via PawnIO driver "
                "(MSR_PKG_ENERGY_STATUS 0x611 on Intel, 0xC001029B on AMD, "
                "cumulative, quantum read from the power-unit MSR; window "
                "edges read from the 0.05 s cumulative-counter buffer; "
                "declared fallback of emi-counter, same register, no "
                "integration)"
            ),
            "power-integration": (
                "LibreHardwareMonitor 'CPU Package' [W] sampled every 0.05 s, "
                "trapezoidal time integration (no Energy counter on this CPU) "
                "[metodo storico, fuori dall'implementazione dal 27/10/2026]"
            ),
            "librehardwaremonitor-energy": (
                "LibreHardwareMonitor package energy counter "
                "[metodo storico, fuori dall'implementazione dal 27/10/2026]"
            ),
            "librehardwaremonitor": (
                "LibreHardwareMonitor (no readable counters) "
                "[metodo storico, fuori dall'implementazione dal 27/10/2026]"
            ),
            "rapl": "RAPL package counter via /sys/class/powercap (Linux)",
            "energy-file": "[DEV/TEST non-Windows] user-provided joule counter file",
            "unavailable": (
                "LOCAL CPU ENERGY MEASUREMENT UNAVAILABLE: needs the Windows "
                "EMI energy channel, the PawnIO MSR counter, or RAPL on Linux"
            ),
        }.get(method, method)
        if res.emi_edge_source == "direct-ioctl":
            win_txt = (
                "energy window read as the direct difference of the counter "
                "at the two measurement edges (dt "
                f"{res.dt_W_s:.3f} s from {res.edge_time_source}; edge spread "
                f"{float(res.edge_spread_s or 0.0):.3f} s); CPU-time window "
                f"{res.cpu_share_window_s:.3f} s from t_cpu_mid")
        else:
            win_txt = (
                f"window interpolation over {len(samples)} samples @ "
                f"{self.session.interval_s}s")
        res.measurement_boundary = (
            f"client-host system boundary; {win_txt}; CPU source: {src_desc}"
        )
        res.notes = notes
        return res

    # ------------------------------------------------------------------ util
    # ------------------------------------------------- bordi di misura (P5)
    @staticmethod
    def _edge_counter(edge: Optional[Dict[str, object]]) -> Optional[dict]:
        """Record del contatore package dentro un bordo, o None."""
        if not edge:
            return None
        cnt = edge.get("counter")
        return cnt if isinstance(cnt, dict) else None

    @classmethod
    def _edge_counter_ts(cls, edge: Optional[Dict[str, object]]) -> Optional[int]:
        """Timestamp 100 ns del record PKG al bordo (None se non EMI)."""
        cnt = cls._edge_counter(edge)
        if not cnt:
            return None
        ts = cnt.get("ts_100ns")
        try:
            return int(ts) if ts is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _edge_raw_value(cls, edge: Optional[Dict[str, object]]
                        ) -> Optional[float]:
        """Valore grezzo del contatore al bordo nella sua unita' nativa.

        EMI espone pWh, il record MSR espone conteggi (``pkg_counts``): il
        chiamante prende anche l'unita' da ``_edge_raw_unit`` per non
        etichettare i conteggi come pWh.
        """
        cnt = cls._edge_counter(edge)
        if not cnt:
            return None
        raw = cnt.get("pkg_pwh")
        if raw is None:
            raw = cnt.get("pkg_counts")
        try:
            return float(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _edge_raw_unit(cls, edge: Optional[Dict[str, object]]) -> str:
        """Unita' del grezzo al bordo: ``pWh`` (EMI), ``counts`` (MSR)."""
        cnt = cls._edge_counter(edge)
        if not cnt:
            return ""
        if cnt.get("pkg_pwh") is not None:
            return "pWh"
        if cnt.get("pkg_counts") is not None:
            return "counts (32-bit MSR)"
        return ""

    @classmethod
    def _edge_dt_w(cls, edge_start: Optional[Dict[str, object]],
                   edge_end: Optional[Dict[str, object]]):
        """Tempo fra i due bordi e la base usata, dichiarata.

        Preferisce la differenza dei timestamp 100 ns del PKG (stessa base
        dell'energia: la finestra e' quella del contatore); se manca, usa la
        differenza dei tempi monotoni presi prima delle IOCTL. Ritorna
        ``(None, "python-window")`` quando nessuna delle due e' utilizzabile:
        il chiamante decide il fallback e non inventa un dt.
        """
        if not edge_start or not edge_end:
            return None, "python-window"
        ts0 = cls._edge_counter_ts(edge_start)
        ts1 = cls._edge_counter_ts(edge_end)
        if ts0 is not None and ts1 is not None and ts1 > ts0:
            return (ts1 - ts0) / 1e7, "emi-counter-ts"
        try:
            m0 = float(edge_start.get("t_counter_mono"))
            m1 = float(edge_end.get("t_counter_mono"))
        except (TypeError, ValueError):
            return None, "python-window"
        if m1 > m0:
            return m1 - m0, "python-monotonic"
        return None, "python-window"

    @classmethod
    def _edge_energy_j(cls, edge_start: Optional[Dict[str, object]],
                       edge_end: Optional[Dict[str, object]]) -> Optional[float]:
        """Differenza diretta del contatore package fra i due bordi [J].

        Nessuna interpolazione: e' il valore del contatore a fine finestra
        meno quello a inizio finestra. Ritorna None se un bordo non ha il
        contatore o se il valore non cresce (lettura non utilizzabile): il
        chiamante torna al buffer e lo dichiara.
        """
        cnt0 = cls._edge_counter(edge_start)
        cnt1 = cls._edge_counter(edge_end)
        if cnt0 is None or cnt1 is None:
            return None
        try:
            j0 = float(cnt0["pkg_j"])
            j1 = float(cnt1["pkg_j"])
        except (KeyError, TypeError, ValueError):
            return None
        if j1 < j0:
            return None
        return j1 - j0

    @staticmethod
    def probe_cpu_time_resolution(
        pid: Optional[int] = None,
        max_seconds: float = 1.0,
        spin_s: float = 0.001,
    ) -> Optional[float]:
        """Passo minimo non nullo di cpu_times per processo (tick osservato).

        GetProcessTimes dichiara 100 ns, ma il kernel aggiorna l'accumulatore
        per processo al tick: un delta chiesto su una finestra piu' corta del
        tick vale 0 o un suo multiplo. Questa sonda misura il passo OSSERVATO
        su un processo che consuma CPU (se stesso), non il valore nominale.
        Ritorna None se non osserva alcun passo positivo.
        """
        try:
            pr = psutil.Process(pid or psutil.Process().pid)

            def _sum_cpu() -> float:
                t = pr.cpu_times()
                return float(t.user + t.system)

            prev = _sum_cpu()
            best: Optional[float] = None
            deadline = time.perf_counter() + max_seconds
            while time.perf_counter() < deadline:
                stop = time.perf_counter() + spin_s
                while time.perf_counter() < stop:
                    pass
                cur = _sum_cpu()
                delta = cur - prev
                if delta > 0.0 and (best is None or delta < best):
                    best = delta
                prev = cur
            return best
        except (psutil.NoSuchProcess, psutil.AccessDenied,
                ValueError, OSError):
            return None

    @staticmethod
    def _ollama_cpu_delta(samples: List[SystemSample]) -> Optional[float]:
        valid = [s for s in samples if s.ollama_pids]
        if len(valid) < 2:
            return None
        first, last = valid[0], valid[-1]
        if not first.ollama_pids or not last.ollama_pids:
            return None
        # confronta solo se l'albero ha PID comparabili (stesso insieme base)
        d = last.ollama_cpu_seconds - first.ollama_cpu_seconds
        if d < 0:
            # processo worker sostituito tra i campioni: usa il max positivo
            run_max = 0.0
            prev_val = None
            for s in valid:
                if prev_val is not None:
                    run_max = max(run_max, s.ollama_cpu_seconds - prev_val)
                prev_val = s.ollama_cpu_seconds
            d = run_max
        return max(d, 0.0)

    @staticmethod
    def _read_ollama_cpu_times(pids: List[int]) -> float:
        """Legge cpu_times (user+system) di tutti i PID Ollama al momento corrente.
        
        Usato per letture esatte agli estremi [t_start, t_end] della finestra,
        non dai campioni a 0.25-0.5 s. Ritorna la somma di user+system per
        tutti i PID nell'albero (ricorsivo).
        """
        if not pids:
            return 0.0
        total = 0.0
        seen = set()
        stack = list(pids)
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            try:
                pr = psutil.Process(pid)
                ct = pr.cpu_times()
                total += float(ct.user + ct.system)
                # Includi figli ricorsivi (runner del modello, worker)
                stack += [c.pid for c in pr.children(recursive=False)]
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                continue
            except Exception:
                continue
        return total

    # ------------------------------------------------------------ convenience
    def measure_request(
        self,
        fn,
        *args,
        **kwargs,
    ):
        """Esegue ``fn`` dentro una finestra profilata. Ritorna (esito, risultato)."""
        t0 = time.monotonic()
        outcome = fn(*args, **kwargs)
        t1 = time.monotonic()
        result = self.profile_window(t0, t1)
        return outcome, result
