# -*- coding: utf-8 -*-
"""Plan v2 schema for P4.4 gate."""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
import json
import hashlib
import sys
import math
from pathlib import Path


PLAN_SCHEMA_VERSION = "casualwatt.p44_gate_plan.v2"


@dataclass
class PlanV2:
    schema: str = PLAN_SCHEMA_VERSION
    requires_idle_characterization: bool = True
    idle_characterization_sha256: str = ""
    background_load_policy: str = "block"  # "block" | "background_controlled"
    quiet_params: Dict = None
    baseline_params: Dict = None
    budget: Dict = None
    blocks: List[Dict] = None
    git_head: str = ""
    seed: str = ""
    model: str = ""
    dt_nominal_s: float = 2.930748
    pairs: int = 6
    n_coppie: int = 6
    n_blocchi: int = 12
    campaign_date: str = ""
    # Fields needed for _verifica_piano compatibility (v2 schema)
    order_seed: str = ""
    runner_sha256: str = ""
    budget_mode: str = "short"
    budget_n_terne: int = 3
    budget_matched_target_s: float = 30.0
    criterio_primario: str = "|bias_w| <= budget_base_w"
    criterio_storico_riportato: str = "f12_mediana_budget_per_blocco_30s"
    quiet_consecutive: int = 3
    quiet_cap_s: float = 600.0
    warmup_tolerance_w: float = 0.5
    warmup_cpu_max_pct: float = 2.0
    warmup_sustain_s: float = 10.0
    warmup_cap_s: float = 60.0
    warmup_step_s: float = 0.0
    warmup_window_s: float = 2.0
    warmup_mode: str = "absolute"  # "absolute" | "stabilization"
    checks: Dict = None

    def __post_init__(self):
        if self.quiet_params is None:
            self.quiet_params = {
                "quiet_threshold_pct": 5.0,
                "quiet_consecutive": 3,
                "quiet_window_s": 3.0,
                "quiet_cpu_sample_interval_s": 1.0,
                "quiet_cap_s": 600.0,
            }
        if self.baseline_params is None:
            self.baseline_params = {
                "baseline_windows_target": 5,
                "baseline_windows_min": 3,
                "baseline_outlier_rule": "iqr_1p5",
                "baseline_cv_max_pct": 10.0,
                "block_repetitions_min": 3,
                "block_repetitions_increase_if_cv_above_pct": 5.0,
                "block_repetitions_max": 6,
            }
        if self.budget is None:
            self.budget = {
                "budget_base_w": 0.0,
                "budget_base_j": 0.0,
            }
        if self.blocks is None:
            self.blocks = []
        if self.checks is None:
            self.checks = {}


def load_idle_characterization(path: Path) -> Dict:
    """Load idle characterization from JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def validate_idle_characterization(char: Dict, expected_hash: str) -> bool:
    """Validate idle characterization by recomputing hash (excluding sha256 field)."""
    # Recompute hash from characterization (excluding sha256 field)
    hash_dict = {k: v for k, v in char.items() if k != "sha256"}
    hash_text = json.dumps(hash_dict, sort_keys=True, separators=(",", ":")).encode()
    computed = hashlib.sha256(hash_text).hexdigest()
    return computed == expected_hash


def create_plan_v2(
    output_dir: Path,
    idle_char_path: Path,
    pairs: int,
    seed: str,
    model: str,
    campaign_date: str,
    background_policy: str = "block",
    # Allow injection of run_gate_p44 module for testing
    _rg_module=None,
) -> int:
    """Create plan v2 from idle characterization."""
    char = load_idle_characterization(idle_char_path)

    # Validate characterization
    if "sha256" not in char:
        print("[ARRESTO] idle_characterization.json missing sha256", file=sys.stderr)
        return 2
    if not validate_idle_characterization(char, char["sha256"]):
        print("[ARRESTO] idle_characterization.json hash mismatch", file=sys.stderr)
        return 2

    # Use injected module or import the real one
    if _rg_module is None:
        import cwEnergyModular.tools.run_gate_p44 as rg
    else:
        rg = _rg_module

    # Use warmup_cpu_max_pct from idle characterization, fallback to constant
    warmup_cpu_max_pct = char.get("warmup_cpu_max_pct", rg.WARMUP_CPU_MAX_PCT)

    plan = PlanV2(
        idle_characterization_sha256=char["sha256"],
        background_load_policy=background_policy,
        quiet_params={
            "quiet_threshold_pct": char.get("quiet_threshold_pct", 5.0),
            "quiet_consecutive": char.get("quiet_consecutive", 3),
            "quiet_window_s": char.get("quiet_window_s", 3.0),
            "quiet_cpu_sample_interval_s": 1.0,
            "quiet_cap_s": char.get("quiet_cap_s", 600.0),
        },
        baseline_params={
            "baseline_windows_target": 5,
            "baseline_windows_min": 3,
            "baseline_outlier_rule": "iqr_1p5",
            "baseline_cv_max_pct": 10.0,
            "block_repetitions_min": 3,
            "block_repetitions_increase_if_cv_above_pct": 5.0,
            "block_repetitions_max": 6,
        },
        seed=seed,
        model=model,
        pairs=pairs,
        n_coppie=pairs,
        n_blocchi=2 * pairs,
        git_head=rg._git_head(),
        order_seed=rg.SEED,
        runner_sha256=rg._sha256(rg.MODULE_DIR / "benchmark_v4.py"),
        budget_mode=rg.BUDGET_MODE,
        budget_n_terne=rg.BUDGET_N_TERNE,
        budget_matched_target_s=rg.BUDGET_MATCHED_TARGET_S,
        criterio_primario=rg.CRITERIO_PRIMARIO,
        criterio_storico_riportato=rg.CRITERIO_STORICO_F12,
        quiet_consecutive=rg.QUIET_CONSECUTIVE,
        quiet_cap_s=rg.QUIET_CAP_S,
        warmup_tolerance_w=rg.WARMUP_TOLERANCE_W,
        warmup_cpu_max_pct=warmup_cpu_max_pct,
        warmup_sustain_s=rg.WARMUP_SUSTAIN_S,
        warmup_cap_s=rg.WARMUP_CAP_S,
        warmup_step_s=rg.WARMUP_STEP_S,
        warmup_window_s=rg.WARMUP_WINDOW_S,
        warmup_mode="stabilization" if background_policy == "background_controlled" else "absolute",
        campaign_date=campaign_date,
        checks={
            "A": (f"{2 * pairs} blocchi in {pairs} coppie; ogni coppia: "
                  "blocco load m=32/np=32/nonce, poi blocco control con "
                  "finestra passiva di dt_nominal_s e ZERO richieste "
                  "(requisiti 1 e 5)"),
            "B": (f"geometria operativa (12,32) confermata (requisito 4); "
                  f"DT_NOM = {rg.DT_NOM_FROZEN} s congelata dal pilota P2.9 "
                  "(requisito 5)"),
            "C": ("ordine carico-primo per coppia, dichiarato nel piano; "
                  f"order_seed = {rg.SEED} registrato su ogni blocco "
                  "(requisito 3)"),
            "D": ("baseline 3 pre + 3 post su ENTRAMBI i bracci (requisito 7); "
                  "cooldown intra-coppia carico->controllo via "
                  "initial_last_pre_w: scelta operativa, non requisito P4.4"),
            # Il testo del check E dipende dalla politica scritta nel piano:
            # in background_controlled la quiete assoluta non e' uno stato
            # della macchina e la precondizione viene SALTATA — un piano che
            # la promettesse sempre descriverebbe una verifica che
            # l'esecuzione non fa.
            "E": ("precondizione di quiete PRIMA di ogni blocco (load e "
                  f"control): {rg.QUIET_CONSECUTIVE} letture consecutive con "
                  "background_load=False, una rumorosa azzera il conteggio; "
                  f"tetto {rg.QUIET_CAP_S:g} s poi SystemExit. "
                  + ("Politica background_controlled: SALTO della precondizione di "
                     "quiete, perche' la caratterizzazione idle misura il "
                     "fondo con il background attivo e la quiete assoluta "
                     "non e' uno stato raggiungibile su questo host; il "
                     "rumore di fondo resta dichiarato, misurato e "
                     "documentato invece che negato. "
                     if background_policy == "background_controlled"
                     else "Politica block: la quiete assoluta si applica, "
                     "senza eccezioni. ")
                  + "Parametro di esecuzione lato tool: il criterio F.12 non "
                    "cambia"),
            "F": ("warm-up post-carico a CRITERIO MISURATO su DUE segnali "
                  "contemporanei, dopo ogni blocco di carico e prima del "
                  f"controllo della coppia: sulla finestra osservata di "
                  f"{rg.WARMUP_WINDOW_S:g} s la potenza del contatore sta entro "
                  f"{rg.WARMUP_TOLERANCE_W} W dalla baseline_pre_w del blocco "
                  "di carico E la media di finestra di cpu_percent sta sotto "
                  f"{warmup_cpu_max_pct:g} %, per {rg.WARMUP_SUSTAIN_S:g} s "
                  "CONTINUI; un campione fuori soglia su uno qualunque dei "
                  "due, o una lettura assente, azzera il tratto; la "
                  "disuguaglianza e' stretta su entrambi. Passo "
                  f"{rg.WARMUP_STEP_S:g} s perche' la lettura di cpu_percent "
                  "sulla finestra e' anche il passo (come QUIET_POLL_S). Tetto "
                  f"{rg.WARMUP_CAP_S:g} s poi SystemExit. Soglie PRE-REGISTRATE "
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
                  "misura ed era collocata PRIMA del carico, non dopo. "
                  "Modalita' background_controlled (warmup_mode=stabilization): "
                  "la baseline_pre_w del blocco di carico e' misurata con il "
                  "background attivo e puo' variare fra un blocco e l'altro; "
                  "il criterio assoluto di rientro non e' raggiungibile. In "
                  "questa modalita' il warm-up si ferma quando la potenza "
                  "smette di salire rispetto a una media mobile degli ultimi "
                  "campioni (stabilizzazione relativa), per "
                  f"{rg.WARMUP_SUSTAIN_S:g} s "
                  "CONTINUI. La cpu_percent e' REGISTRATA ma NON decide: con "
                  "rumore di fondo dichiarato (Qoder, PyCharm, ...) la cpu "
                  "e' sopra soglia per costruzione e un rumore controllato "
                  "non e' un transitorio del carico. La soglia di cpu_percent "
                  "e' attiva SOLO in modalità absolute (block). Il criterio "
                  "F.12 (bias_w <= budget_base_w) non cambia."),
            "G": (f"budget di soglia PRE-ESECUZIONE con procedura "
                  f"{rg.BUDGET_MODE.upper()}: {rg.BUDGET_N_TERNE} unita' per "
                  "gruppo (pre e post, non sovrapposti) lette da "
                  "read_idle_window_j alla scala del controllo e aggregate "
                  "da benchmark_v4.block_baseline (F.1/F.4). "
                  + ("Nessun fattore di scala da 30 s: il fondo e' misurato "
                     "su finestre di Tc."
                     if rg.BUDGET_MODE == "short" else
                     f"Aggregato di "
                     f"{math.ceil(rg.BUDGET_MATCHED_TARGET_S / rg.DT_NOM_FROZEN)} "
                     "finestre Tc consecutive per unita' "
                     f"(somma(delta_j)/somma(dt_s) = "
                     f"{rg.BUDGET_MATCHED_TARGET_S:g} s nominali): nessun "
                     "campione singolo vale come budget e nessun fattore "
                     "di scala.")
                  + " CodeCarbon non interviene ne' in correzione ne' in "
                    "calibrazione del budget: e' solo registro diagnostico "
                    "aperto dal flag --codecarbon"),
            "H": ("criterio che DECIDE, dichiarato PRIMA dei dati: "
                  f"{rg.CRITERIO_PRIMARIO} = |bias_w| <= budget_base_w misurato "
                  "a scala Tc prima dei blocchi (check G), con il filtro e il "
                  "quorum di F.12. Il verdetto F.12 storico (mediana dei "
                  "budget per blocco da finestre da 30 s) resta calcolato e "
                  "riportato come " + rg.CRITERIO_STORICO_F12 + ", NON decide. "
                  "Nessuna soglia del tipo budget + k * u_c: u_c non include "
                  "componenti gia' contenute nel budget. U = t * s / sqrt(n) "
                  "e |bias| + U <= budget sono grandezze riportate"),
        },
    )

    # Generate blocks directly (don't use rg.plan_blocks() which uses global N_BLOCCHI)
    blocchi = []
    for i in range(2 * pairs):
        coppia = i // 2
        if i % 2 == 0:
            blocchi.append({
                "index": i, "label": f"carico-{coppia + 1}", "arm": "load",
                "pair_id": f"pair-{coppia}",
                "prompt_id": f"load-{coppia + 1}", "text": rg.LOAD_PROMPT,
                "source": "p44_gate",
                "m": rg.LOAD_M, "num_predict": rg.LOAD_NUM_PREDICT,
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
                "richieste": 0, "dt_nominal_s": rg.DT_NOM_FROZEN,
            })
    plan.blocks = blocchi

    # Budget will be filled by pre-execution measurement
    plan_file = output_dir / "plan.json"
    plan_file.write_text(json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def verify_plan_v2(plan_path: Path) -> bool:
    """Verify that a plan file is v2 schema."""
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        return plan.get("schema") == PLAN_SCHEMA_VERSION
    except Exception:
        return False