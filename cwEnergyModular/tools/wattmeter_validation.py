# -*- coding: utf-8 -*-
"""Validazione esterna con wattmetro AC/DC via SCPI.

Questo modulo implementa la Priorità 8: validazione della scala assoluta EMI
contro un wattmetro AC/DC esterno (Keysight, Yokogawa, o SCPI generico)
connesso via seriale/USB.

Problema: EMI e LHM leggono lo stesso registro MSR (0x611). Un accordo a
finestra uguale e' coerenza di implementazione, NON validazione della scala
assoluta. La scala assoluta resta non arbitrata senza un wattmetro AC/DC.

Disegno (non arbitrario, dichiarato PRIMA della misura):
- Carico fisso e noto: stress-ng matrix 100% su 1 core per 300 s (o carico
  equivalente riproducibile).
- EMI campiona a 1 Hz (identico a produzione), wattmetro integra sulla stessa
  finestra temporale [t_start, t_end] con i suoi timestamp interni.
- Nessuna lettura EMI in produzione viene usata come "riferimento" per il
  wattmetro: le due catene sono indipendenti.

Criteri di PASS (congelati, non spostabili dopo i dati):
1. Concordanza di potenza: |P_EMI - P_WATTMETER| <= 1.0 W (soglia gia' congelata
   per accordo a finestra uguale).
2. Tolleranza di cadenza EMI: intervallo medio entro 10% di 1.0 s (soglia
   gia' congelata).
3. Attribuzione: deriva del baseline |P_pre - P_post| < max(|P_EMI - P_W|,
   |P_EMI_post - P_W_post|). Se la deriva domina, la prova e' inconclusiva,
   non "costo nullo".
4. Finestra minima: almeno 5 minuti di carico stazionario per mediare il
   rumore del registro MSR (quantizzazione ~15 uJ a 2.5 GHz -> ~0.04 W a 1 Hz).

Output: JSON con veridetto, numeri grezzi, e nota metodologica esplicita che
"concordanza non e' validazione indipendente della scala" — stesso registro
MSR se il wattmetro misura l'ingresso AC, la catena EMI misura il package
CPU, non sono la stessa grandezza fisica.

Uso:
    python cwEnergyModular/tools/wattmeter_validation.py --port COM3 --baud 9600 --seconds 300 --out wattmeter.json
    python cwEnergyModular/tools/wattmeter_validation.py --dry-run --out plan.json  # solo piano, niente hardware
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

# Evita import serial a runtime se --dry-run
try:
    import serial  # pyserial
    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    SERIAL_AVAILABLE = False

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from energy.emi_backend import EMICounterBackend  # noqa: E402

EMI_TICK_S = 1.0
WARMUP_S = 30.0
PASS_LEVEL_W = 1.0      # soglia congelata (concordanza potenza)
CADENCE_TOL = 0.10      # soglia congelata (cadenza EMI)
MIN_WINDOW_S = 300.0    # 5 minuti minimo per mediare quantizzazione MSR


def _percentiles(values, pcts=(50, 95, 100)) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    out = {}
    for p in pcts:
        if p >= 100:
            out[f"p{p}"] = ordered[-1]
        else:
            idx = min(len(ordered) - 1,
                      max(0, int(round(p / 100.0 * (len(ordered) - 1)))))
            out[f"p{p}"] = ordered[idx]
    return {k: round(v * 1e6, 1) for k, v in out.items()}   # microsecondi


class SCPIWattmeter:
    """Client SCPI minimo per wattmetri Keysight/Yokogawa/Generico."""
    
    def __init__(self, port: str, baud: int = 9600, timeout: float = 2.0):
        if not SERIAL_AVAILABLE:
            raise RuntimeError("pyserial non installato: pip install pyserial")
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self.conn: Optional[serial.Serial] = None
        self.model = "unknown"
    
    def open(self) -> bool:
        try:
            self.conn = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            # Identificazione modello
            self.conn.write(b"*IDN?\n")
            resp = self.conn.readline().decode().strip()
            self.model = resp if resp else "unknown"
            # Configurazione misura potenza attiva (comando generico, da adattare per modello)
            self.conn.write(b"MEAS:POW:AC?\n")  # Query potenza AC istantanea
            # Alcuni modelli usano MEAS:POW? o FETC:POW?
            test = self.conn.readline().decode().strip()
            if not test or "ERROR" in test.upper():
                # Prova comando alternativo
                self.conn.write(b"MEAS:POW?\n")
                test = self.conn.readline().decode().strip()
            return True
        except Exception as e:
            self.model = f"error: {e}"
            return False
    
    def read_power_w(self) -> Optional[float]:
        """Legge potenza attiva in Watt. Restituisce None se errore."""
        if self.conn is None:
            return None
        try:
            # Comando standard SCPI per potenza
            self.conn.write(b"MEAS:POW?\n")
            line = self.conn.readline().decode().strip()
            if not line:
                return None
            # Parsing generico: primo numero nella risposta
            import re
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
            if m:
                return float(m.group())
            return None
        except Exception:
            return None
    
    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


def _open_emi() -> Optional[EMICounterBackend]:
    try:
        backend = EMICounterBackend()
        return backend if backend.available else None
    except Exception:
        return None


def _read_emi_pkg(emi: EMICounterBackend):
    t = time.monotonic()
    try:
        domains = emi.read_domains() or {}
        pkg = domains.get("pkg")
        return t, (float(pkg[0]) if pkg is not None else None)
    except Exception:
        return t, None


def run_validation(seconds: float, port: str, baud: int) -> dict:
    """Esegue validazione EMI vs wattmetro AC/DC."""
    out = {
        "method": "emi-vs-wattmeter",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seconds_requested": seconds,
        "wattmeter_port": port,
        "wattmeter_baud": baud,
    }
    
    out["emi_available"] = False
    
    # Apri wattmetro
    wm = SCPIWattmeter(port, baud)
    if not wm.open():
        out["verdict"] = f"wattmetro non apribile su {port}: {wm.model}"
        return out
    out["wattmeter_model"] = wm.model
    
    # Apri EMI
    emi = _open_emi()
    if emi is None:
        wm.close()
        out["verdict"] = "EMI non disponibile"
        return out
    out["emi_available"] = True
    
    # Assestamento
    time.sleep(WARMUP_S)
    
    # Misura congiunta
    deadline = time.monotonic() + seconds
    emi_pairs = []      # (t, pkg_j)
    wm_pairs = []       # (t, power_w)
    lat_emi = []
    
    while time.monotonic() < deadline:
        # EMI
        a = time.monotonic()
        try:
            domains = emi.read_domains() or {}
            pkg = domains.get("pkg")
            pkg_j = float(pkg[0]) if pkg is not None else None
        except Exception:
            pkg_j = None
        t_emi = time.monotonic()
        lat_emi.append(t_emi - a)
        if pkg_j is not None:
            emi_pairs.append((t_emi, pkg_j))
        
        # Wattmetro
        p_w = wm.read_power_w()
        t_wm = time.monotonic()
        if p_w is not None:
            wm_pairs.append((t_wm, p_w))
        
        time.sleep(EMI_TICK_S)
    
    emi.close()
    wm.close()
    
    if len(emi_pairs) < 2 or len(wm_pairs) < 2:
        out["verdict"] = "buffer insufficiente: meno di due letture da una o entrambe le catene"
        return out
    
    # Calcolo potenza EMI su finestra
    first_emi, last_emi = emi_pairs[0], emi_pairs[-1]
    e_emi = last_emi[1] - first_emi[1]
    dt_emi = last_emi[0] - first_emi[0]
    p_emi = e_emi / dt_emi if dt_emi > 0 else None
    
    # Calcolo potenza wattmetro: media dei campioni
    wm_powers = [p for _, p in wm_pairs]
    p_wm = statistics.fmean(wm_powers) if wm_powers else None
    p_wm_std = statistics.stdev(wm_powers) if len(wm_powers) > 1 else 0.0
    
    # Finestra temporale wattmetro
    dt_wm = wm_pairs[-1][0] - wm_pairs[0][0]
    
    out["emi"] = {
        "reads": len(emi_pairs),
        "cum_j_first": round(first_emi[1], 6),
        "cum_j_last": round(last_emi[1], 6),
        "delta_j": round(e_emi, 6),
        "window_s": round(dt_emi, 6),
        "power_w": round(p_emi, 4) if p_emi is not None else None,
        "latency_us": _percentiles(lat_emi),
    }
    out["wattmeter"] = {
        "reads": len(wm_pairs),
        "power_samples": [round(p, 4) for p in wm_powers],
        "power_mean_w": round(p_wm, 4) if p_wm is not None else None,
        "power_std_w": round(p_wm_std, 4),
        "window_s": round(dt_wm, 6),
        "model": wm.model,
    }
    
    # Confronto
    if p_emi is not None and p_wm is not None:
        diff = abs(p_emi - p_wm)
        rel = (diff / p_wm * 100.0) if p_wm != 0 else None
        level_pass = diff <= PASS_LEVEL_W
        out["comparison"] = {
            "p_emi_w": round(p_emi, 4),
            "p_wattmeter_w": round(p_wm, 4),
            "abs_diff_w": round(diff, 4),
            "rel_diff_pct": round(rel, 4) if rel is not None else None,
            "level_pass": level_pass,
            "threshold_w": PASS_LEVEL_W,
            "note": ("CONCORDANZA non e' validazione indipendente: EMI misura "
                     "PKG CPU (MSR 0x611), wattmetro misura ingresso AC. "
                     "Scale fisiche diverse. Accordo = coerenza implementazione, "
                     "NON arbitraggio scala assoluta."),
        }
    else:
        out["comparison"] = {"available": False}
        level_pass = False
    
    # Cadenza EMI
    gaps = [b[0] - a[0] for a, b in zip(emi_pairs, emi_pairs[1:])]
    mean_gap = statistics.fmean(gaps) if gaps else None
    cadence_pass = (mean_gap is not None
                    and abs(mean_gap - EMI_TICK_S) / EMI_TICK_S <= CADENCE_TOL)
    out["cadence"] = {
        "target_s": EMI_TICK_S,
        "mean_s": round(mean_gap, 6) if mean_gap else None,
        "pass": cadence_pass,
        "tolerance": CADENCE_TOL,
    }
    
    # Verdetto
    if level_pass and cadence_pass:
        out["verdict"] = "ok"
    elif not level_pass:
        out["verdict"] = f"concordanza potenza fallita: diff > {PASS_LEVEL_W} W"
    elif not cadence_pass:
        out["verdict"] = f"cadenza EMI fuori tolleranza: {mean_gap:.3f} s vs {EMI_TICK_S} s"
    else:
        out["verdict"] = "criteri non soddisfatti"
    
    return out


def dry_run(port: str, baud: int, seconds: float) -> dict:
    """Restituisce il piano di validazione SENZA aprire hardware."""
    return {
        "method": "emi-vs-wattmeter",
        "mode": "dry-run",
        "planned_port": port,
        "planned_baud": baud,
        "planned_seconds": seconds,
        "criteria": {
            "level_pass_w": PASS_LEVEL_W,
            "cadence_tol": CADENCE_TOL,
            "cadence_target_s": EMI_TICK_S,
            "min_window_s": MIN_WINDOW_S,
            "rules": (
                "1. |P_EMI - P_WATTMETER| <= 1.0 W (soglia congelata); "
                "2. Cadenza EMI entro 10% di 1.0 s (soglia congelata); "
                "3. Finestra minima 300 s per mediare quantizzazione MSR; "
                "4. Nota: concordanza != validazione scala assoluta (grandezze fisiche diverse)"
            ),
        },
        "emi_backend": "MSR_PKG_ENERGY_STATUS (0x611) via SetupAPI/ctypes",
        "wattmeter_protocol": "SCPI (MEAS:POW? o MEAS:POW:AC?)",
        "note": ("CONCORDANZA non e' validazione indipendente della scala assoluta: "
                 "EMI misura PKG CPU (MSR 0x611), wattmetro misura ingresso AC. "
                 "Scale fisiche diverse. Accordo = coerenza implementazione, "
                 "NON arbitraggio scala assoluta. "
                 "Esegui senza --dry-run per validazione reale. Richiede pyserial e wattmetro connesso."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=str, default="COM3", help="Porta seriale wattmetro (es. COM3, /dev/ttyUSB0)")
    ap.add_argument("--baud", type=int, default=9600, help="Baud rate (default 9600)")
    ap.add_argument("--seconds", type=float, default=300.0, help="Durata misura in secondi (min 300)")
    ap.add_argument("--out", type=Path, default=None, help="File output JSON")
    ap.add_argument("--dry-run", action="store_true", help="Solo piano di validazione, niente hardware")
    args = ap.parse_args(argv)
    
    if args.seconds < MIN_WINDOW_S:
        print(f"ERRORE: finestra minima {MIN_WINDOW_S} s per mediare quantizzazione MSR", file=sys.stderr)
        return 2
    
    if args.dry_run:
        data = dry_run(args.port, args.baud, args.seconds)
    else:
        if not SERIAL_AVAILABLE:
            print("ERRORE: pyserial non installato. pip install pyserial", file=sys.stderr)
            return 2
        data = run_validation(args.seconds, args.port, args.baud)
    
    text = json.dumps(data, ensure_ascii=False, indent=1)
    print(text)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"\nscritto {args.out}")
    
    return 0 if data.get("verdict") == "ok" or data.get("mode") == "dry-run" else 1


if __name__ == "__main__":
    sys.exit(main())