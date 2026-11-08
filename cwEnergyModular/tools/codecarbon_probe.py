# -*- coding: utf-8 -*-
"""tools/codecarbon_probe.py — registro parallelo CodeCarbon per il gate P4.4.

Perche' esiste. La seconda campagna del gate (2026-11-08) e' fallita in
ambiente quieto con bias_w 0,125171 W contro soglia 0,117995 W (+6,1%): il
disegno e' corretto, ma non c'e' un secondo canale che dica se l'ordine di
grandezza dell'energia dei controlli e' plausibile anche per una pipeline
diversa. CodeCarbon e' quella pipeline: questo modulo apre un tracker, lo
avvia e lo arresta attorno a OGNI blocco del gate, e scrive i suoi numeri in
una directory separata ``<archivio>/codecarbon/`` — mai accanto alle righe
del percorso di misura.

Che cosa NON e'. Non e' un secondo gate, non corregge nulla e non entra nel
criterio F.12: ``bias_w``, ``budget_base_w``, ``control_e_net_j``,
``control_dt_w_s`` e lo status restano esattamente quelli di
``control_gate.evaluate_gate``. Senza il flag ``--codecarbon`` del runner
questo modulo non viene mai importato, e il comportamento del gate e'
identico a oggi. I valori CodeCarbon non sono usati per normalizzare,
sostituire o "validare" una misura del gate: sono un registro diagnostico
con provenienza dichiarata, letto DOPO dai dati.

Vincoli metrologici dichiarati qui, non nel report:
- sulle macchine Windows 11 il backend CPU di CodeCarbon 3.3.2 e'
  ``windows_emi``, che legge ``MSR_PKG_ENERGY_STATUS`` (0x611): LO STESSO
  registro della catena ``emi-counter`` di CasualWatt. Un accordo fra i due
  numeri e' coerenza di implementazione, non validazione indipendente
  (regola AGENTS: confronto same-counter != validazione).
- la potenza RAM di CodeCarbon e' un modello di stima (euristica sui DIMM),
  non un contatore; la GPU e' assente se nessun device NVML/AMD risponde.
- il CSV ``emissions.csv`` e' scritto dal tracker stesso a ogni
  ``stop()``: una riga per run, ``timestamp`` = fine del run. Le finestre
  di allineamento del confronto stanno nel manifest: ``wall_start_s`` /
  ``wall_end_s`` (epoch) del probe, non dedotte dal CSV.
- ``measure_power_secs``: default 1 s — accettato dal costruttore di
  3.3.2 su questo host (misurato il 2026-11-08); se il costruttore non lo
  accetta il probe riprova a 15 s e dichiara il fallback nel suo stato. Un
  intervallo piu' largo della finestra di controllo rende il confronto
  qualitativo: lo dice ``tools/compare_codecarbon_gate.py``, non il gate.
- ``pue`` e' esplicitamente 1,0 (nessun fattore datacenter applicato) e
  viene registrato in ogni riga; ``tracking_mode='machine'``: i numeri sono
  della macchina intera, non del solo processo Ollama — un'altra ragione per
  cui il confronto non e' una replica metrologica.

Ogni fallimento (modulo assente, tracker non costruibile, start/stop che non
produce dati) NON ferma il gate: il blocco e' registrato col suo motivo e
``codecarbon_status.json`` dichiara ``unavailable`` (o ``partial``) con la
ragione. Il probe legge tre attributi privati del tracker
(``_start_time``, ``_hardware``, ``_pue``): e' accettabile perche' la
dipendenza e' pinnata a 3.3.2 in ``requirements-codecarbon.txt`` e perche'
serve solo a dichiarare il backend, mai a decidere un numero.

Unita' di citta', dichiarate nel file di stato: potenze W, energie kWh,
emissioni kg CO2e (le stesse di ``EmissionsData`` di codecarbon 3.3.2).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DIR_NAME = "codecarbon"
CSV_NAME = "emissions.csv"
STATUS_NAME = "codecarbon_status.json"
MANIFEST_NAME = "codecarbon_manifest.json"

DEFAULT_MEASURE_POWER_S = 1.0     # provato accettato su questo host (08-11)
FALLBACK_MEASURE_POWER_S = 15.0   # default storico di codecarbon 3.3.2
PUE = 1.0                         # dichiarato: nessun fattore datacenter

# Campi di EmissionsData (3.3.2) registrati per blocco. La lista e' anagrafica
# del dataclass, non una scelta: copre quanto richiesto dal mandato (timestamp,
# potenze, energie, energy_consumed, emissions) piu' la provenienza (modelli,
# versione, tracciamento, pue). Un campo assente nella classe reale finisce
# None, mai inventato.
CAMPI_RUN = (
    "timestamp", "project_name", "run_id", "experiment_id", "duration",
    "emissions", "emissions_rate", "cpu_power", "gpu_power", "ram_power",
    "cpu_energy", "gpu_energy", "ram_energy", "energy_consumed",
    "water_consumed", "country_name", "country_iso_code", "region",
    "os", "python_version", "codecarbon_version", "cpu_count", "cpu_model",
    "gpu_count", "gpu_model", "ram_total_size", "tracking_mode", "pue", "wue",
)

# Modi CPU che sono UN CONTATORE hardware (fonte: core/resource_tracker.py e
# external/hardware.py di codecarbon 3.3.2, letto l'08-11-2026).
MODI_CONTATORE = ("windows_emi", "intel_rapl", "intel_power_gadget")

SAME_COUNTER_CAVEAT = (
    "windows_emi legge MSR_PKG_ENERGY_STATUS (0x611), lo stesso registro "
    "della catena emi-counter di CasualWatt: un accordo fra i due numeri "
    "e' coerenza di implementazione, non validazione indipendente"
)


def _scrittura_atomica(path: Path, payload) -> None:
    text = payload if isinstance(payload, str) else \
        json.dumps(payload, indent=2, ensure_ascii=False)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _run_da_emissions(data) -> Dict[str, Any]:
    """EmissionsData -> dict a schema fisso CAMPI_RUN. getattr con default
    None: un campo rinominato da una versione diversa resta None e viene
    dichiarato, non dedotto da un altro nome."""
    return {nome: getattr(data, nome, None) for nome in CAMPI_RUN}


def descrivi_backend(tracker) -> Dict[str, Any]:
    """Cosa ha prodotto il numero, dalle sole strutture del tracker.
    ``_hardware`` porta gli oggetti (RAM/CPU/GPU/...); il CPU ha ``_mode``;
    la descrizione stampabile (``description()``) e' conservata perche' e'
    quella che codecarbon stesso pubblica. ``GPU`` presente solo se un
    device NVML/AMD ha risposto: qui la sua assenza NON e' una misura."""
    descrizioni: List[str] = []
    cpu_mode: Optional[str] = None
    gpu = False
    for item in getattr(tracker, "_hardware", []) or []:
        try:
            descrizioni.append(str(item.description()))
        except Exception:
            descrizioni.append(repr(item))
        mode = getattr(item, "_mode", None)
        if isinstance(mode, str) and mode:
            cpu_mode = mode
        if type(item).__name__ == "GPU":
            gpu = True
    if cpu_mode in MODI_CONTATORE:
        cpu_kind = "contatore hardware"
    elif cpu_mode is not None:
        cpu_kind = "modello o stima (nessun contatore)"
    else:
        cpu_kind = "non dichiarato"
    return {
        "hardware": descrizioni,
        "cpu_mode": cpu_mode,
        "cpu_kind": cpu_kind,
        "gpu_tracciata": gpu,
        "ram": "modello di stima (euristica DIMM), non contatore",
        "pue": getattr(tracker, "_pue", PUE),
        "tracking_mode": "machine",
    }


class ProbeCodeCarbon:
    """Tracker unico, una run CodeCarbon per blocco del gate.

    Ciclo di vita: ``avvia()`` (import + costruzione, mai una misura) ->
    per blocco ``apri_blocco`` / ``chiudi_blocco`` -> ``concludi()`` che
    scrive status e manifest e restituisce il riepilogo che il runner
    appende in ``analysis.json`` SOLO in presenza del flag. Nessuno dei tre
    metodi solleva: il gate non puo' morire per un osservatore.
    """

    def __init__(self, output_dir: Path,
                 measure_power_secs: Optional[float] = None,
                 project_name: str = "p44_gate_codecarbon") -> None:
        self.output_dir = Path(output_dir)
        self.project_name = project_name
        self.intervallo_richiesto = (
            float(measure_power_secs) if measure_power_secs is not None
            else DEFAULT_MEASURE_POWER_S)
        self.stato: Dict[str, Any] = {
            "codecarbon_status": "not-started",
            "reason": None,
            "codecarbon_version": None,
            "measure_power_secs_requested": self.intervallo_richiesto,
            "measure_power_secs_used": None,
            "measure_power_secs_fallback": False,
            "pue": PUE,
            "tracking_mode": "machine",
            "backend": None,
            "same_counter_caveat": None,
            "units": {"power": "W", "energy": "kWh",
                      "emissions": "kg CO2e", "wall": "epoch s"},
            "directory": str(self.output_dir),
            "csv": str(self.output_dir / CSV_NAME),
            "n_blocchi_aperti": 0,
            "n_blocchi_con_dati": 0,
        }
        self.blocchi: List[Dict[str, Any]] = []
        self._tracker = None
        self._aperto: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    def _unavailable(self, reason: str) -> None:
        self.stato["codecarbon_status"] = "unavailable"
        self.stato["reason"] = reason

    def avvia(self) -> bool:
        """Importa codecarbon e costruisce il tracker. Il costruttore non
        legge i contatori (lo fa ``start()``): qui si decide solo se la
        libreria c'e' e se accetta l'intervallo chiesto. Esce False con la
        ragione nel stato, mai con un'eccezione."""
        try:
            import codecarbon                      # noqa: F401
            from codecarbon import EmissionsTracker
        except Exception as exc:
            self._unavailable(
                f"codecarbon non importabile ({exc!r}): installarlo e' "
                "opzionale (requirements-codecarbon.txt), il gate prosegue")
            return False
        self.stato["codecarbon_version"] = \
            getattr(codecarbon, "__version__", None)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for intervallo, e_fallback in ((self.intervallo_richiesto, False),
                                       (FALLBACK_MEASURE_POWER_S, True)):
            try:
                self._tracker = EmissionsTracker(
                    project_name=self.project_name,
                    measure_power_secs=intervallo,
                    output_dir=str(self.output_dir),
                    output_file=CSV_NAME,
                    save_to_file=True,
                    save_to_api=False,
                    save_to_logger=False,
                    log_level="error",
                    allow_multiple_runs=True,
                    tracking_mode="machine",
                    pue=PUE)
            except Exception as exc:
                self.stato["reason"] = (
                    f"costruttore rifiuta {intervallo} s ({exc!r})")
                self._tracker = None
                continue
            self.stato["measure_power_secs_used"] = intervallo
            self.stato["measure_power_secs_fallback"] = e_fallback
            self.stato["reason"] = None
            self.stato["codecarbon_status"] = "ready"
            if e_fallback:
                self.stato["reason"] = (
                    f"intervallo {self.intervallo_richiesto} s non accettato, "
                    f"fallback a {intervallo} s")
            return True
        self._unavailable(
            f"EmissionsTracker non costruibile neppure a "
            f"{FALLBACK_MEASURE_POWER_S} s: {self.stato['reason']}")
        return False

    # ------------------------------------------------------------------
    def apri_blocco(self, block_id: str, arm: Optional[str] = None,
                    pair_id: Optional[str] = None) -> None:
        """start() del tracker subito prima di run_v4_benchmark. codecarbon
        3.3.2 sopprime le eccezioni dentro start(): il probe quindi NON si
        fida del ritorno e guarda lo stato — ``_start_time`` non None e'
        l'unica prova che la misura e' partita. Se il probe non e' attivo il
        blocco resta registrato come skipped: il manifest copre TUTTI i
        blocchi, non solo quelli osservati."""
        rec: Dict[str, Any] = {
            "block_id": block_id, "arm": arm, "pair_id": pair_id,
            "wall_start_s": time.time(), "wall_end_s": None,
            "block_status": "pending", "reason": None, "run": None,
        }
        self.blocchi.append(rec)
        self.stato["n_blocchi_aperti"] += 1
        self._aperto = rec
        if self._tracker is None:
            rec["block_status"] = "skipped"
            rec["reason"] = (self.stato.get("reason")
                             or "probe non attivo (vedi codecarbon_status)")
            return
        try:
            self._tracker.start()
        except Exception as exc:
            rec["block_status"] = "failed"
            rec["reason"] = f"start() ha sollevato: {exc!r}"
            return
        if getattr(self._tracker, "_start_time", None) is None:
            rec["block_status"] = "failed"
            rec["reason"] = ("start() non ha attivato il tracker "
                             "(_start_time assente): contatori o scheduler "
                             "non disponibili")
            return
        if self.stato["backend"] is None:
            try:
                self.stato["backend"] = descrivi_backend(self._tracker)
                if (self.stato["backend"]["cpu_mode"] == "windows_emi"):
                    self.stato["same_counter_caveat"] = SAME_COUNTER_CAVEAT
            except Exception as exc:
                self.stato["backend"] = {"errore_di_lettura": repr(exc)}
        rec["block_status"] = "open"

    def chiudi_blocco(self) -> None:
        """stop() subito dopo run_v4_benchmark (il runner lo chiama in un
        finally: anche un blocco interrotto da errore ha la sua chiusura).
        Il numero entra nel manifest solo se ``final_emissions_data`` esiste
        davvero; la durata CodeCarbon e' quella del tracker, le finestre
        di allineamento sono wall_start/wall_end del probe."""
        rec = self._aperto
        self._aperto = None
        if rec is None:
            return
        rec["wall_end_s"] = time.time()
        if rec["block_status"] != "open":
            return
        try:
            self._tracker.stop()
            data = getattr(self._tracker, "final_emissions_data", None)
        except Exception as exc:
            rec["block_status"] = "failed"
            rec["reason"] = f"stop() ha sollevato: {exc!r}"
            return
        if data is None:
            rec["block_status"] = "failed"
            rec["reason"] = ("stop() non ha prodotto final_emissions_data: "
                             "nessun numero per questo blocco")
            return
        try:
            rec["run"] = _run_da_emissions(data)
        except Exception as exc:
            rec["block_status"] = "failed"
            rec["reason"] = f"campionatura campi fallita: {exc!r}"
            return
        rec["block_status"] = "ok"
        self.stato["n_blocchi_con_dati"] += 1

    # ------------------------------------------------------------------
    def concludi(self) -> Dict[str, Any]:
        """Status finale + manifest, scritti anche sui percorsi di
        fallimento (e' li' che il motivo deve essere leggibile). Se il loop
        del runner e' terminato presto, l'ultimo blocco aperto viene chiuso
        qui: il manifest non lascia finestre aperte. Il CSV resta al
        tracker: una riga per ogni stop() riuscito."""
        if self._tracker is not None and self._aperto is not None:
            self.chiudi_blocco()
        n_ok = self.stato["n_blocchi_con_dati"]
        n_tot = self.stato["n_blocchi_aperti"]
        if self._tracker is None:
            pass                     # unavailable/ready gia' deciso da avvia
        elif n_ok == n_tot and n_tot > 0:
            self.stato["codecarbon_status"] = "ok"
        elif n_ok > 0:
            self.stato["codecarbon_status"] = "partial"
            motivi = [b["reason"] for b in self.blocchi if b.get("reason")]
            self.stato["reason"] = (
                f"{n_ok}/{n_tot} blocchi con dati, {n_tot - n_ok} senza: "
                + (motivi[0] if motivi else "motivo non registrato"))
        else:
            motivi = [b["reason"] for b in self.blocchi if b.get("reason")]
            self._unavailable(
                "nessun blocco ha prodotto dati CodeCarbon"
                + (f": {motivi[0]}" if motivi else ""))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        _scrittura_atomica(self.output_dir / STATUS_NAME, self.stato)
        _scrittura_atomica(self.output_dir / MANIFEST_NAME, {
            "project_name": self.project_name,
            "codecarbon_status": self.stato["codecarbon_status"],
            "units": self.stato["units"],
            "blocchi": self.blocchi,
        })
        return {
            "codecarbon_status": self.stato["codecarbon_status"],
            "reason": self.stato["reason"],
            "directory": self.stato["directory"],
            "csv": self.stato["csv"],
            "status_file": str(self.output_dir / STATUS_NAME),
            "manifest_file": str(self.output_dir / MANIFEST_NAME),
            "codecarbon_version": self.stato["codecarbon_version"],
            "measure_power_secs_used":
                self.stato["measure_power_secs_used"],
            "measure_power_secs_fallback":
                self.stato["measure_power_secs_fallback"],
            "pue": self.stato["pue"],
            "backend": self.stato["backend"],
            "same_counter_caveat": self.stato["same_counter_caveat"],
            "n_blocchi_aperti": n_tot,
            "n_blocchi_con_dati": n_ok,
        }
