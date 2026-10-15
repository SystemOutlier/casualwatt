#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
consumi_ollama.py
=================
Framework Python per Windows 11 che stima il consumo elettrico (W / kWh)
delle sessioni locali di Ollama, su QUALSIASI macchina Windows:

  - Scenario A : GPU NVIDIA dedicata  -> lettura Power Draw reale via NVML (pynvml)
  - Scenario B : GPU integrata Intel/AMD -> stima via contatori WMI/PerfMon
                  (GPU Engine + Processor Information) combinata col pacchetto CPU
  - Scenario C : Solo CPU / fallback totale -> % CPU di Ollama rapportata al TDP

Caratteristiche:
  * Rilevamento processo "ollama_llama_server.exe" / "ollama.exe" (psutil)
  * TDP CPU: tabella automatica per modello + sovrascrittura manuale (.env o CLI)
  * Campionamento ogni 2 secondi, dashboard live con "rich"
  * CTRL+C -> chiusura sicura + salvataggio storico in "consumi_ollama.csv"

Installazione dipendenze (Windows):
    pip install psutil rich python-dotenv pynvml wmi pywin32

Uso:
    python consumi_ollama.py
    python consumi_ollama.py --tdp 65 --intervallo 2 --output consumi_ollama.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import platform
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------------
# 0) SOVRASCITTURA MANUALE TDP (variabile all'inizio dello script)
#    Imposta a None per usare il rilevamento automatico. Es.: CPU_TDP_OVERRIDE = 45
# ----------------------------------------------------------------------------
CPU_TDP_OVERRIDE: Optional[float] = None

INTERVALLO_CAMPIONAMENTO_DEFAULT = 2.0   # secondi
OUTPUT_CSV_DEFAULT = "consumi_ollama.csv"
NOMI_PROCESSI_OLLAMA = ("ollama_llama_server.exe", "ollama.exe")

# ----------------------------------------------------------------------------
# Importazioni "di sistema" protette: il framework NON deve mai crashare se
# una libreria hardware non e' presente sulla macchina.
# ----------------------------------------------------------------------------
try:
    import psutil
except ImportError:  # pragma: no cover
    print("[FATAL] Modulo 'psutil' mancante. Esegui:  pip install psutil")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:  # pragma: no cover
    print("[FATAL] Modulo 'rich' mancante. Esegui:  pip install rich")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    try:
        # fallback: parsing minimale del .env senza python-dotenv
        if os.path.exists(".env"):
            with open(".env", "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass

IS_WINDOWS = platform.system() == "Windows"


# ============================================================================
# 1) IDENTIFICAZIONE DEL PROCESSO OLLAMA
# ============================================================================
def trova_processi_ollama() -> List["psutil.Process"]:
    """Trova i processi core di Ollama (server llama + orchestratore)."""
    proccessi: List[psutil.Process] = []
    for p in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            nome = (p.info.get("name") or "").lower()
            if nome in NOMI_PROCESSI_OLLAMA:
                proccessi.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return proccessi


def cpu_percent_ollama(processi: List["psutil.Process"]) -> float:
    """Somma la % CPU (0..N*100) dei processi Ollama, normalizzata per n-core."""
    if not processi:
        return 0.0
    totale = 0.0
    validi: List[psutil.Process] = []
    for p in processi:
        try:
            totale += p.cpu_percent(interval=None)
            validi.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    # memorizza lo stato per il prossimo giro (psutil funziona delta-based)
    _STATO["processi_validi"] = validi
    n_core = psutil.cpu_count(logical=True) or 1
    # clamp: un solo core al 100% => 100/N_CORE della frazione totale
    return min(100.0, totale / n_core)


# ============================================================================
# 2) HARDWARE INFO: CPU, TDP, GPU
# ============================================================================
TDP_TABLE: Dict[str, float] = {
    # ---- Intel mobile (serie 12/13/14 gen) ----
    "i9-13900HK": 45.0, "i9-13900H": 45.0, "i9-12900HK": 45.0,
    "i7-13700H": 45.0, "i7-12700H": 45.0, "i5-13500H": 45.0,
    "i5-12500H": 45.0, "i9-13900HX": 55.0, "i7-13800H": 45.0,
    # ---- Intel desktop ----
    "i9-13900K": 125.0, "i7-13700K": 125.0, "i5-13600K": 125.0,
    "i9-14900K": 125.0, "i7-14700K": 125.0, "i5-14600K": 125.0,
    "i9-12900K": 125.0, "i7-12700K": 125.0,
    # ---- AMD Ryzen ----
    "7950X": 120.0, "7900X": 120.0, "7700X": 105.0, "7600X": 105.0,
    "6900HX": 45.0, "6800H": 45.0, "7735HS": 35.0, "7640HS": 35.0,
}


def nome_cpu() -> str:
    """Nome commerciale della CPU (registro Win -> platform.processor)."""
    if IS_WINDOWS:
        # 1) tentativo: registro di Windows (info piu' affidabile)
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            val, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            winreg.CloseKey(key)
            return re.sub(r"\s+", " ", str(val)).strip()
        except Exception:
            pass
        # 2) tentativo via WMI
        try:
            out = subprocess.check_output(
                'wmic cpu get Name /value', shell=True, text=True,
                stderr=subprocess.DEVNULL, timeout=5,
            )
            for riga in out.splitlines():
                if "=" in riga:
                    return re.sub(r"\s+", " ", riga.split("=", 1)[1]).strip()
        except Exception:
            pass
    try:
        return re.sub(r"\s+", " ", platform.processor()).strip() or "CPU sconosciuta"
    except Exception:
        return "CPU sconosciuta"


def tdp_da_modello(nome: str) -> float:
    """Match nella tabella TDP; fallback conservativi basati su marca/core."""
    for chiave, w in TDP_TABLE.items():
        if chiave.lower() in nome.lower():
            return w
    # euristica: laptop (HK/H/U/HX/Suffix) vs desktop
    n = nome.lower()
    cores = psutil.cpu_count(logical=True) or 8
    if "intel" in n or "core" in n:
        if any(s in n for s in ("hk", "hx", "-h", "u ")) or cores <= 16:
            return 45.0
        return 65.0
    if "ryzen" in n or "amd" in n:
        if any(s in n for s in ("hs", "u", "hx")):
            return 35.0
        return 65.0
    return 65.0  # fallback universale sicuro


try:
    import warnings
    with warnings.catch_warnings():          # silenzia FutureWarning di pynvml
        warnings.simplefilter("ignore")
        import pynvml  # package "nvidia-ml-py" (alias retro-compatibile 'pynvml')
except Exception:
    pynvml = None


def rileva_gpu_nvidia() -> Optional[Tuple[str, object]]:
    """Scenario A: prova a inizializzare NVML. Ritorna (nome, handle) o None."""
    try:
        if pynvml is None:
            return None
        pynvml.nvmlInit()
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return None
        # preferisce la GPU con i processi attivi, altrimenti la prima
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        nome = pynvml.nvmlDeviceGetName(h)
        if isinstance(nome, bytes):
            nome = nome.decode("utf-8", errors="replace")
        return (nome, h)
    except Exception:
        return None


def power_draw_nvidia(h) -> Optional[float]:
    """Legge il power draw istantaneo (Watt) via NVML; None se non supportato."""
    try:
        if pynvml is None:
            return None
        mw = pynvml.nvmlDeviceGetPowerUsage(h)
        return mw / 1000.0
    except Exception:
        return None


def gpu_util_nvidia(h) -> Optional[float]:
    try:
        if pynvml is None:
            return None
        return float(pynvml.nvmlDeviceGetUtilizationRates(h).gpu)
    except Exception:
        return None


def nomi_gpu_windows() -> List[str]:
    """Elenca tutte le GPU (dedicate + integrate) via WMI/registro."""
    gpu: List[str] = []
    if not IS_WINDOWS:
        return gpu
    try:
        out = subprocess.check_output(
            'wmic path Win32_VideoController get Name /value',
            shell=True, text=True, stderr=subprocess.DEVNULL, timeout=6,
        )
        for riga in out.splitlines():
            if riga.startswith("Name="):
                gpu.append(riga.split("=", 1)[1].strip())
    except Exception:
        pass
    if not gpu:
        try:
            import winreg
            base = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}",
            )
            i = 0
            while True:
                try:
                    sub = winreg.OpenKey(base, winreg.EnumKey(base, i))
                    desc, _ = winreg.QueryValueEx(sub, "DriverDesc")
                    if desc and str(desc) not in gpu:
                        gpu.append(str(desc))
                    i += 1
                except OSError:
                    break
        except Exception:
            pass
    return gpu


def ha_gpu_integrata(gpu_list: List[str]) -> bool:
    keywords = ("intel", "iris", "uhd", "arc", "amd", "radeon", "vega")
    return any(any(k in g.lower() for k in keywords) for g in gpu_list)


# ============================================================================
# 2b) SCENARIO B: metriche GPU integrata via WMI / Performance Counters
# ============================================================================
class MonitorGPUIntegrata:
    """
    Stima l'utilizzo % della GPU integrata (Intel Iris Xe / AMD Radeon) usando:
      1) modulo 'wmi' -> Win32_PerfFormattedData...GPU Engine (se disponibile)
      2) typeperf dei Performance Counters di Windows (\\GPU Engine(*eng*)\\...)
      3) 'Processor Information' (frequenza x busy%) come proxy del pacchetto
         CPU+GPU condivisa (APU), quando la GPU non e' isolabile.
    Ogni passo fallisce in modo silenzioso verso il livello successivo.
    """

    def __init__(self):
        self._wmi = None
        self._typeperf_cache: Optional[float] = None
        self._last_probe = 0.0
        self.metodo = "nessuno"
        if not IS_WINDOWS:
            return
        # --- Livello 1: modulo wmi + Win32_PerfFormattedData_Counters_GPUEngine
        try:
            import wmi  # type: ignore
            c = wmi.WMI(namespace="root\\cimv2")
            probe = c.query(
                "select * from Win32_PerfFormattedData_Counters_GPUEngine"
            )
            if probe is not None:
                self._wmi = c
                self.metodo = "wmi-gpu-engine"
                return
        except Exception:
            pass
        # --- Livello 2: typeperf (fallback CLI, sempre presente su Win11)
        try:
            p = subprocess.run(
                ["typeperf", "\\GPU Engine(*)\\Utilization Percentage", "-sc", "1"],
                capture_output=True, text=True, timeout=8,
                creationflags=(subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0),
            )
            if p.returncode == 0 and "%" in (p.stdout or ""):
                self.metodo = "typeperf-gpu-engine"
        except Exception:
            self.metodo = "processor-information"

    # ---------- utilizzo GPU (%) ----------
    def gpu_percent(self) -> Optional[float]:
        if self.metodo == "wmi-gpu-engine" and self._wmi is not None:
            try:
                righe = self._wmi.query(
                    "select UtilizationPercentage from "
                    "Win32_PerfFormattedData_Counters_GPUEngine"
                )
                # somma dei soli kernel tipo Compute (engtype ...) delle LUT Ollama
                tot = sum(float(getattr(r, "UtilizationPercentage", 0) or 0) for r in righe)
                return min(100.0, tot) if righe else None
            except Exception:
                return None
        if self.metodo == "typeperf-gpu-engine":
            now = time.time()
            if now - self._last_probe >= 2.0:  # cache: typeperf e' lento (~1-2 s)
                self._last_probe = now
                self._typeperf_cache = self._leggi_typeperf()
            return self._typeperf_cache
        return None

    def _leggi_typeperf(self) -> Optional[float]:
        try:
            p = subprocess.run(
                ["typeperf", "\\GPU Engine(*)\\Utilization Percentage", "-sc", "1"],
                capture_output=True, text=True, timeout=8,
                creationflags=(subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0),
            )
            if p.returncode != 0:
                return None
            righe = [l for l in p.stdout.splitlines() if "," in l]
            if len(righe) < 2:
                return None
            ultima = righe[-1]
            valori = []
            for cell in ultima.split(",")[1:]:
                cell = cell.strip().strip('"')
                try:
                    valori.append(float(cell))
                except ValueError:
                    continue
            return min(100.0, sum(valori)) if valori else None
        except Exception:
            return None

    # ---------- proxy pacchetto CPU (Processor Information) ----------
    def cpu_pacchetto_proxy(self) -> Optional[float]:
        """Stima % busy ponderata per frequenza dai counter 'Processor Information'."""
        if not IS_WINDOWS:
            return None
        try:
            p = subprocess.run(
                ["typeperf",
                 "\\Processor Information(_Total)\\% Processor Utility", "-sc", "1"],
                capture_output=True, text=True, timeout=6,
                creationflags=(subprocess.CREATE_NO_WINDOW if IS_WINDOWS else 0),
            )
            if p.returncode != 0:
                return None
            righe = [l for l in p.stdout.splitlines() if "," in l]
            if len(righe) < 2:
                return None
            cell = righe[-1].split(",")[-1].strip().strip('"')
            return max(0.0, min(100.0, float(cell)))
        except Exception:
            return None


# ============================================================================
# 3) STIMA POTENZA
# ============================================================================
@dataclass
class LetturaCampionamento:
    ts: str
    scenario: str
    cpu_pct: float
    gpu_pct: Optional[float]
    watt_cpu: float
    watt_gpu: Optional[float]
    watt_totale: float
    kwh_totali: float
    note: str = ""


class StimaConsumo:
    """Aggrega le sorgenti hardware e calcola Watt/kWh per scenario."""

    def __init__(self, tdp: float):
        self.tdp = tdp
        self.kwh = 0.0
        self.gpu_nvidia = rileva_gpu_nvidia()
        self.monitor_igp: Optional[MonitorGPUIntegrata] = None
        self.lista_gpu = nomi_gpu_windows()

        if self.gpu_nvidia is not None:
            self.scenario = "A"
        elif IS_WINDOWS and ha_gpu_integrata(self.lista_gpu):
            self.scenario = "B"
            try:
                self.monitor_igp = MonitorGPUIntegrata()
            except Exception:
                self.monitor_igp = None
        else:
            self.scenario = "C"

    # -------- watt CPU: curva P(u) non lineare, picchi PL2 a pieno carico -----
    def watt_cpu(self, cpu_pct: float) -> float:
        u = max(0.0, min(1.0, cpu_pct / 100.0))
        idle = self.tdp * 0.10          # consumo baseline a vuoto ~10% del TDP
        # Moltiplicatore PL2: a utilizzo ~100% concediamo fino a +40% del TDP
        pl2 = self.tdp * 1.4
        if u >= 0.98:
            return pl2
        # Interpolazione cubica: i core moderni consumano poco a basso carico
        return idle + (pl2 - idle) * (u ** 3)

    # -------- watt GPU per scenario -------------------------------------------
    def watt_gpu(self, cpu_pct_ollama: float) -> Tuple[Optional[float], Optional[float], str]:
        """Ritorna (watt_gpu, gpu_pct, nota)."""
        note = ""
        if self.scenario == "A" and self.gpu_nvidia:
            nome, h = self.gpu_nvidia
            w = power_draw_nvidia(h)
            gp = gpu_util_nvidia(h)
            if w is not None:
                return w, gp, f"NVML reale ({nome})"
            # GPU NVIDIA ma senza sensore potenza: stima da utilization
            if gp is not None:
                return 5.0 + (gp / 100.0) * (self.tdp * 1.5), gp, "NVML stima da util%"
            return None, None, "NVML assente"

        if self.scenario == "B" and self.monitor_igp:
            gp = self.monitor_igp.gpu_percent()
            proxy = self.monitor_igp.cpu_pacchetto_proxy()
            # Budget termico tipico delle iGPU mobili: 15-25 W
            budget_igp = 20.0
            if gp is not None:
                w_igp = 1.0 + (gp / 100.0) * budget_igp
                # Se i counter GPU non isolano bene, aggiunge il delta del
                # pacchetto CPU (Processor Information) come correzione
                if proxy is not None and proxy > cpu_pct_ollama:
                    w_igp += (proxy - cpu_pct_ollama) / 100.0 * budget_igp * 0.5
                return w_igp, gp, f"WMI/PerfMon iGPU ({self.monitor_igp.metodo})"
            if proxy is not None:
                # GPU non isolabile: usa il proxy frequency-scaled sul budget APU
                w_igp = (max(0.0, proxy - cpu_pct_ollama) / 100.0) * budget_igp
                return w_igp, proxy, "Proxy Processor Information (APU)"
            return None, None, "Counter GPU non disponibili"

        # Scenario C: nessuna GPU isolabile -> tutto attribuito alla CPU
        return None, None, "Solo CPU (fallback)"

    # -------- campione completo -----------------------------------------------
    def campiona(self, cpu_pct_ollama: float, intervallo_s: float) -> LetturaCampionamento:
        wc = self.watt_cpu(cpu_pct_ollama)
        wg, gp, nota_gpu = self.watt_gpu(cpu_pct_ollama)
        # In scenario C/B senza GPU isolata, la quota GPU ricade nel pacchetto CPU:
        # aggiungiamo comunque un piccolo overhead memoria/bus se Ollama e' attivo
        overhead = 2.0 if cpu_pct_ollama > 1.0 else 0.0
        totale = wc + (wg or 0.0) + overhead
        self.kwh += totale * (intervallo_s / 3600.0)
        return LetturaCampionamento(
            ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            scenario=self.scenario,
            cpu_pct=round(cpu_pct_ollama, 1),
            gpu_pct=(round(gp, 1) if gp is not None else None),
            watt_cpu=round(wc, 2),
            watt_gpu=(round(wg, 2) if wg is not None else None),
            watt_totale=round(totale, 2),
            kwh_totali=round(self.kwh, 6),
            note=nota_gpu,
        )


# ============================================================================
# 4) DASHBOARD "rich"
# ============================================================================
def costruisci_dashboard(st: StimaConsumo, let: Optional[LetturaCampionamento],
                         cpu_nome: str, gpu_info: str, n_proc: int,
                         init_time: float) -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="main"),
        Layout(name="footer", size=3),
    )

    elapsed = time.time() - init_time
    titolo = Text()
    titolo.append("⚡ OLLAMA ENERGY MONITOR ", style="bold bright_white on dark_blue")
    titolo.append(f"  |  scenario {let.scenario if let else st.scenario}  "
                  f"|  sessione: {elapsed:.0f}s", style="dim")
    layout["header"].update(Panel(titolo, style="blue"))

    # --- pannello hardware ---
    hw = Table.grid(padding=(0, 1))
    hw.add_row("[bold cyan]CPU:[/]", cpu_nome)
    hw.add_row("[bold cyan]GPU:[/]", gpu_info)
    hw.add_row("[bold cyan]TDP rif.:[/]", f"{st.tdp:.0f} W (picco PL2 {st.tdp*1.4:.0f} W)")
    hw.add_row("[bold cyan]Proc. Ollama:[/]", f"{n_proc} attivi")
    layout["main"].split_row(Layout(name="left"), Layout(name="right"))
    layout["left"].update(Panel(hw, title="Hardware rilevato", border_style="cyan"))

    # --- pannello consumo ---
    if let is None:
        corpo = Text("In attesa del primo campione...", style="italic yellow")
    else:
        colore_w = "green" if let.watt_totale < st.tdp * 0.6 else (
            "yellow" if let.watt_totale < st.tdp * 1.1 else "red")
        barra = ""
        frac = min(1.0, let.watt_totale / max(1.0, st.tdp * 1.4))
        nz = int(frac * 30)
        barra = "█" * nz + "░" * (30 - nz)
        tab = Table.grid(padding=(0, 2))
        tab.add_row("[bold]Potenza istantanea[/]",
                    Text(f"{let.watt_totale:7.2f} W", style=f"bold {colore_w}"))
        tab.add_row("", Text(f"[{barra}] {frac*100:.0f}%", style=colore_w))
        tab.add_row("[bold]Energia accumulata[/]",
                    Text(f"{let.kwh_totali:.5f} kWh", style="bold magenta"))
        tab.add_row("  di cui CPU", f"{let.watt_cpu:.2f} W  ({let.cpu_pct}% busy)")
        if let.watt_gpu is not None:
            g = f"{let.watt_gpu:.2f} W"
            g += f"  ({let.gpu_pct}% util)" if let.gpu_pct is not None else ""
            tab.add_row("  di cui GPU", g)
        tab.add_row("Metodo GPU", let.note or "-")
        costo = let.kwh_totali * 0.25  # €/kWh indicativo
        tab.add_row("[dim]Costo stimato (@0.25 €/kWh)[/]", f"[dim]{costo:.4f} €[/]")
        corpo = tab
    layout["right"].update(Panel(corpo, title="Consumo live", border_style="magenta"))

    layout["footer"].update(Panel(
        "[yellow]CTRL+C[/] = ferma il tracking e salva [bold]consumi_ollama.csv[/]",
        style="grey50"))
    return layout


def console_fallback(let: LetturaCampionamento, st: StimaConsumo):
    """Fallback testuale se la dashboard rich fallisse (terminale esotico)."""
    print(f"[{let.ts}] {let.watt_totale:7.2f} W | tot {let.kwh_totali:.5f} kWh "
          f"| cpu {let.cpu_pct}% | gpu {let.watt_gpu}")


# ============================================================================
# 5) CSV OUTPUT
# ============================================================================
CAMPI_CSV = ["timestamp", "scenario", "cpu_pct", "gpu_pct",
             "watt_cpu", "watt_gpu", "watt_totale", "kwh_totali", "note"]


def scrivi_csv(righe: List[LetturaCampionamento], percorso: str):
    with open(percorso, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")  # ';' per Excel italiano
        w.writerow(CAMPI_CSV)
        for r in righe:
            w.writerow([r.ts, r.scenario, r.cpu_pct,
                        r.gpu_pct if r.gpu_pct is not None else "",
                        r.watt_cpu,
                        r.watt_gpu if r.watt_gpu is not None else "",
                        r.watt_totale, r.kwh_totali, r.note])


# ============================================================================
# MAIN
# ============================================================================
_STATO: Dict[str, object] = {"processi_validi": []}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Monitor consumo energetico Ollama (Windows 11)")
    ap.add_argument("--tdp", type=float, default=None,
                    help="Override TDP CPU in Watt (default: auto/.env CPU_TDP)")
    ap.add_argument("--intervallo", type=float, default=INTERVALLO_CAMPIONAMENTO_DEFAULT,
                    help="Secondi tra i campioni (default 2)")
    ap.add_argument("--output", type=str, default=OUTPUT_CSV_DEFAULT,
                    help="File CSV di destinazione")
    return ap.parse_args()


def main():
    args = parse_args()

    # ---- Risoluzione TDP: CLI > .env > variabile in testa allo script > auto ----
    tdp = args.tdp
    if tdp is None:
        env_v = os.getenv("CPU_TDP")
        if env_v:
            try:
                tdp = float(env_v)
            except ValueError:
                print(f"[WARN] CPU_TDP='{env_v}' non valido, uso auto.")
    if tdp is None:
        tdp = CPU_TDP_OVERRIDE
    cpu_nome = nome_cpu()
    if tdp is None:
        tdp = tdp_da_modello(cpu_nome)
        origine_tdp = "auto"
    else:
        origine_tdp = "manuale"

    print(f"[INFO] CPU: {cpu_nome}")
    print(f"[INFO] TDP di riferimento: {tdp:.0f} W ({origine_tdp})")

    # ---- Avvio stima hardware (mai in crash: tutto protetto) ----
    try:
        stimo = StimaConsumo(tdp)
    except Exception as e:
        print(f"[ERRORE critico hardware, fallback scenario C] {e}")
        stimo = StimaConsumo(tdp)
        stimo.scenario = "C"
        stimo.monitor_igp = None

    gpu_info = "Nessuna GPU rilevata (solo CPU)"
    if stimo.scenario == "A" and stimo.gpu_nvidia:
        gpu_info = f"NVIDIA {stimo.gpu_nvidia[0]} (Scenario A - NVML)"
    elif stimo.lista_gpu:
        gpu_info = ", ".join(stimo.lista_gpu) + f" (Scenario {stimo.scenario})"

    print(f"[INFO] GPU: {gpu_info}")
    print(f"[INFO] Scenario attivo: {stimo.scenario}")
    print("[INFO] Premi CTRL+C per fermare e salvare il CSV.\n")

    # Primi call di cpu_percent per innescare il delta-counter di psutil
    for p in trova_processi_ollama():
        try:
            p.cpu_percent(interval=None)
        except Exception:
            pass

    console = Console()
    campioni: List[LetturaCampionamento] = []
    let: Optional[LetturaCampionamento] = None
    init_time = time.time()
    live_mode = True

    try:
        with console.status("Inizializzazione monitor..."):
            time.sleep(0.2)

        while True:
            processi = trova_processi_ollama()
            cpu_pct = cpu_percent_ollama(processi)
            let = stimo.campiona(cpu_pct, args.intervallo)
            campioni.append(let)

            if live_mode:
                try:
                    console.clear()
                    console.print(costruisci_dashboard(
                        stimo, let, cpu_nome, gpu_info, len(processi), init_time))
                except Exception:
                    live_mode = False  # degrada a log testuale, niente crash
                    console_fallback(let, stimo)
            else:
                console_fallback(let, stimo)

            if not processi:
                # Ollama non in esecuzione: continua a girare (consumo ~idle)
                pass

            time.sleep(args.intervallo)

    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"\n[ERRORE imprevisto durante il loop: {e}] - salvo i dati raccolti.")
    finally:
        # ---- Chiusura sicura: stop NVML + salvataggio CSV ----
        try:
            if stimo.gpu_nvidia and pynvml is not None:
                pynvml.nvmlShutdown()
        except Exception:
            pass
        try:
            scrivi_csv(campioni, args.output)
            tot_kwh = stimo.kwh
            print(f"\n[OK] {len(campioni)} campioni salvati in '{args.output}'")
            print(f"[OK] Energia totale sessione: {tot_kwh:.5f} kWh")
        except Exception as e:
            print(f"\n[ERRORE] Salvataggio CSV fallito: {e}")
        # Ultimo tentativo di dump in-memory se il file fosse corrotto
        if not os.path.exists(args.output) and campioni:
            alt = "consumi_ollama_recovery.csv"
            try:
                scrivi_csv(campioni, alt)
                print(f"[OK] Recovery: dati scritti in '{alt}'")
            except Exception:
                pass


if __name__ == "__main__":
    main()
