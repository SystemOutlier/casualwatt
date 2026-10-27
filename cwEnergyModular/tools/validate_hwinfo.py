# -*- coding: utf-8 -*-
"""
tools/validate_hwinfo.py — Validazione incrociata CasualWatt vs HWiNFO.

Questo script confronta l'energia misurata da CasualWatt (contatore package CPU
nel CSV) con quella misurata da HWiNFO Sensors, fornendo un confronto esterno.

Utilizzo:
    1. Eseguire il benchmark con CasualWatt (genera CSV risultati)
    2. Avviare HWiNFO logging (File → Logging Start → salva CSV)
    3. Eseguire lo stesso benchmark con HWiNFO in logging
    4. Fermare HWiNFO logging
    5. Eseguire questo script:
       python tools/validate_hwinfo.py --casualwatt results.csv --hwinfo hwinfo_log.csv

Output:
    - Report di validazione con differenza percentuale
    - Grafico confronto (opzionale, richiede matplotlib)
    - File JSON con metriche di validazione
"""
import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    print("⚠ NumPy non disponibile: calcolo meno efficiente", file=sys.stderr)

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


def read_hwinfo_csv(csv_path: str, power_column_hint: str = "CPU Package Power") -> Tuple[List[float], List[float]]:
    """
    Legge il CSV di HWiNFO ed estrae la colonna di potenza CPU Package.
    
    Args:
        csv_path: Percorso al file CSV di HWiNFO
        power_column_hint: Stringa per identificare la colonna di potenza
    
    Returns:
        Tupla (timestamps, power_watts) dove:
          - timestamps: lista di tempi in secondi (relativi all'inizio)
          - power_watts: lista di potenze in Watt
    """
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        
        # HWiNFO CSV ha 2 righe di header:
        # Riga 1: nomi colonne
        # Riga 2: unità di misura
        headers = next(reader)
        units = next(reader)
        
        # Trova la colonna di potenza CPU Package
        power_col_idx = None
        for i, header in enumerate(headers):
            if power_column_hint.lower() in header.lower():
                power_col_idx = i
                break
        
        if power_col_idx is None:
            # Fallback: cerca colonne con "Power" e "CPU"
            for i, header in enumerate(headers):
                if "power" in header.lower() and "cpu" in header.lower():
                    power_col_idx = i
                    print(f"⚠ Colonna '{power_column_hint}' non trovata, uso '{headers[i]}'")
                    break
        
        if power_col_idx is None:
            raise ValueError(
                f"Impossibile trovare colonna di potenza CPU.\n"
                f"Colonne disponibili: {headers}\n"
                f"Suggerimento: usa --power-column per specificare il nome"
            )
        
        # Trova colonna timestamp (prima colonna solitamente)
        time_col_idx = 0
        for i, header in enumerate(headers):
            if "time" in header.lower() or "date" in header.lower():
                time_col_idx = i
                break
        
        # Leggi dati
        timestamps = []
        power_watts = []
        start_time = None
        
        for row in reader:
            if len(row) <= max(power_col_idx, time_col_idx):
                continue
            
            # Parse timestamp
            try:
                time_str = row[time_col_idx].strip()
                # HWiNFO usa formato "YYYY-MM-DD HH:MM:SS.mmm" o simile
                # Per semplicità, usiamo l'indice come tempo relativo
                if start_time is None:
                    start_time = len(timestamps)
                timestamps.append(float(len(timestamps)))
            except (ValueError, IndexError):
                timestamps.append(float(len(timestamps)))
            
            # Parse potenza
            try:
                power_str = row[power_col_idx].strip()
                if power_str and power_str != 'N/A':
                    power_w = float(power_str)
                    power_watts.append(power_w)
                else:
                    power_watts.append(0.0)
            except (ValueError, IndexError):
                power_watts.append(0.0)
        
        return timestamps, power_watts


def read_casualwatt_csv(csv_path: str, use_package_energy: bool = True) -> Tuple[List[float], List[float]]:
    """
    Legge il CSV di CasualWatt ed estrae l'energia per query.
    
    Args:
        csv_path: Percorso al file CSV di CasualWatt
        use_package_energy: Se True, legge package_energy_j (energia totale del
            package CPU, prima dell'attribuzione). Se False, legge local_energy_j
            (energia attribuita a Ollama). Per confronto con HWiNFO, usare True.
    
    Returns:
        Tupla (timestamps, energy_j) dove:
          - timestamps: lista di tempi in secondi (relativi all'inizio)
          - energy_j: lista di energie in Joule per query
    """
    timestamps = []
    energy_j = []
    
    # Scegli quale colonna leggere
    energy_column = 'package_energy_j' if use_package_energy else 'local_energy_j'
    fallback_column = 'end_to_end_energy_j' if use_package_energy else 'package_energy_j'
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for i, row in enumerate(reader):
            # CasualWatt CSV ha colonne: timestamp, package_energy_j, local_energy_j, etc.
            try:
                # Timestamp (se presente) o indice
                if 'timestamp' in row:
                    t = float(row['timestamp'])
                else:
                    t = float(i)
                timestamps.append(t)
                
                # Energia: preferisci package_energy_j per confronto con HWiNFO
                if energy_column in row:
                    e = float(row[energy_column])
                elif fallback_column in row:
                    e = float(row[fallback_column])
                    print(f"⚠ Colonna '{energy_column}' non trovata, uso '{fallback_column}'", file=sys.stderr)
                else:
                    e = 0.0
                    print(f"⚠ Nessuna colonna energetica trovata per riga {i}", file=sys.stderr)
                energy_j.append(e)
                
            except (ValueError, KeyError) as exc:
                print(f"⚠ Riga {i} saltata: {exc}", file=sys.stderr)
                continue
    
    return timestamps, energy_j


def integrate_trapezoidal(timestamps: List[float], power_watts: List[float]) -> float:
    """
    Calcola l'energia totale tramite integrazione trapezoidale.
    
    E = Σ ((P_i + P_{i+1}) / 2) * (t_{i+1} - t_i)
    
    Args:
        timestamps: Lista di tempi in secondi
        power_watts: Lista di potenze in Watt
    
    Returns:
        Energia totale in Joule
    """
    if len(timestamps) < 2 or len(power_watts) < 2:
        return 0.0
    
    if HAS_NUMPY:
        # Versione numpy (più efficiente)
        t = np.array(timestamps)
        p = np.array(power_watts)
        dt = np.diff(t)
        avg_p = (p[:-1] + p[1:]) / 2.0
        energy_j = float(np.sum(avg_p * dt))
    else:
        # Versione pura Python
        energy_j = 0.0
        for i in range(len(timestamps) - 1):
            dt = timestamps[i+1] - timestamps[i]
            avg_p = (power_watts[i] + power_watts[i+1]) / 2.0
            energy_j += avg_p * dt
    
    return max(energy_j, 0.0)


def calculate_statistics(
    casualwatt_energy_j: float,
    hwinfo_energy_j: float
) -> Dict[str, float]:
    """
    Calcola statistiche di validazione.
    
    Args:
        casualwatt_energy_j: Energia misurata da CasualWatt [J]
        hwinfo_energy_j: Energia misurata da HWiNFO [J]
    
    Returns:
        Dict con:
          - absolute_difference_j: Differenza assoluta [J]
          - relative_difference_pct: Differenza relativa [%]
          - ratio: Rapporto CasualWatt / HWiNFO
    """
    abs_diff = abs(casualwatt_energy_j - hwinfo_energy_j)
    
    if hwinfo_energy_j > 0:
        rel_diff_pct = (abs_diff / hwinfo_energy_j) * 100.0
        ratio = casualwatt_energy_j / hwinfo_energy_j
    else:
        rel_diff_pct = 0.0
        ratio = 1.0
    
    return {
        "casualwatt_energy_j": round(casualwatt_energy_j, 3),
        "hwinfo_energy_j": round(hwinfo_energy_j, 3),
        "absolute_difference_j": round(abs_diff, 3),
        "relative_difference_pct": round(rel_diff_pct, 2),
        "ratio": round(ratio, 4),
    }


def plot_comparison(
    hwinfo_timestamps: List[float],
    hwinfo_power_watts: List[float],
    casualwatt_timestamps: List[float],
    casualwatt_energy_j: List[float],
    output_path: str = "validation_plot.png"
):
    """
    Genera grafico di confronto tra HWiNFO e CasualWatt.
    
    Args:
        hwinfo_timestamps: Tempi HWiNFO
        hwinfo_power_watts: Potenza HWiNFO
        casualwatt_timestamps: Tempi CasualWatt
        casualwatt_energy_j: Energia CasualWatt (cumulativa o per query)
        output_path: Percorso file output PNG
    """
    if not HAS_MATPLOTLIB:
        print("⚠ Matplotlib non disponibile: grafico non generato", file=sys.stderr)
        return
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8))
    
    # Plot 1: Potenza HWiNFO
    ax1.plot(hwinfo_timestamps, hwinfo_power_watts, 'b-', linewidth=1.5, label='HWiNFO Power')
    ax1.set_xlabel('Time [s]')
    ax1.set_ylabel('Power [W]')
    ax1.set_title('CPU Package Power - HWiNFO')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Energia CasualWatt
    ax2.plot(casualwatt_timestamps, casualwatt_energy_j, 'r-', linewidth=1.5, label='CasualWatt Energy')
    ax2.set_xlabel('Query Index')
    ax2.set_ylabel('Energy [J]')
    ax2.set_title('Energy per Query - CasualWatt')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"✓ Grafico salvato: {output_path}")


def generate_report(stats: Dict[str, float], output_path: str = "validation_report.json"):
    """
    Genera report JSON di validazione.
    
    Args:
        stats: Dizionario con statistiche di validazione
        output_path: Percorso file output JSON
    """
    report = {
        "validation_type": "cross_platform_hwinfo",
        "timestamp": str(Path.ctime(Path(__file__))),
        "statistics": stats,
        "conclusion": (
            "VALID" if stats["relative_difference_pct"] < 5.0
            else "WARNING" if stats["relative_difference_pct"] < 10.0
            else "INVALID"
        ),
        "notes": [
            "Differenza < 5%: validazione riuscita",
            "Differenza 5-10%: accettabile ma verificare",
            "Differenza > 10%: controllare configurazione"
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    
    print(f"✓ Report salvato: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Validazione incrociata CasualWatt vs HWiNFO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Esempio (confronto energia TOTALE package CPU, raccomandato):
    python tools/validate_hwinfo.py \\
        --casualwatt results/benchmark_20261021.csv \\
        --hwinfo hwinfo_log_20261021.csv \\
        --output validation_result.json \\
        --plot

Nota: Per default confronta l'energia TOTALE del package CPU (prima dell'attribuzione
a Ollama), che è il confronto scientificamente valido con HWiNFO. Usa --use-local-energy
per confrontare l'energia attribuita a Ollama (non raccomandato per validazione).
        """
    )
    
    parser.add_argument(
        "--casualwatt",
        required=True,
        help="Percorso al CSV di CasualWatt (risultati benchmark)"
    )
    parser.add_argument(
        "--hwinfo",
        required=True,
        help="Percorso al CSV di HWiNFO (logging sensori)"
    )
    parser.add_argument(
        "--power-column",
        default="CPU Package Power",
        help="Nome della colonna di potenza in HWiNFO (default: 'CPU Package Power')"
    )
    parser.add_argument(
        "--output",
        default="validation_result.json",
        help="Percorso file output JSON (default: validation_result.json)"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Genera grafico di confronto (richiede matplotlib)"
    )
    parser.add_argument(
        "--use-local-energy",
        action="store_true",
        help="Confronta energia attribuita a Ollama (local_energy_j) invece di "
             "energia totale package CPU (package_energy_j). NON raccomandato per "
             "validazione con HWiNFO (che misura il totale, non l'attribuzione)."
    )
    
    args = parser.parse_args()
    
    # Determina quale energia usare
    use_package = not args.use_local_energy
    energy_type = "TOTALE package CPU (package_energy_j)" if use_package else "ATTRIBUITA a Ollama (local_energy_j)"
    
    # Verifica file esistenti
    if not Path(args.casualwatt).exists():
        print(f"❌ File CasualWatt non trovato: {args.casualwatt}", file=sys.stderr)
        sys.exit(1)
    
    if not Path(args.hwinfo).exists():
        print(f"❌ File HWiNFO non trovato: {args.hwinfo}", file=sys.stderr)
        sys.exit(1)
    
    print("=" * 70)
    print("VALIDAZIONE INCROCIATA: CasualWatt vs HWiNFO")
    print("=" * 70)
    print(f"\n📊 Tipo di confronto: {energy_type}")
    if use_package:
        print("   (Confronto scientificamente valido: entrambi misurano il totale)")
    else:
        print("   (ATTENZIONE: HWiNFO misura il totale, non l'attribuzione)")
    
    # Leggi CSV CasualWatt
    print(f"\n📖 Leggo CSV CasualWatt: {args.casualwatt}")
    try:
        cw_timestamps, cw_energy_j = read_casualwatt_csv(args.casualwatt, use_package_energy=use_package)
        cw_total_energy_j = sum(cw_energy_j)
        print(f"   ✓ {len(cw_timestamps)} query lette")
        print(f"   ✓ Energia totale CasualWatt: {cw_total_energy_j:.2f} J")
        if use_package:
            print(f"   ✓ Tipo: energia TOTALE package CPU (prima dell'attribuzione)")
        else:
            print(f"   ✓ Tipo: energia ATTRIBUITA a Ollama (dopo attribuzione)")
    except Exception as exc:
        print(f"❌ Errore lettura CSV CasualWatt: {exc}", file=sys.stderr)
        sys.exit(1)
    
    # Leggi CSV HWiNFO
    print(f"\n📖 Leggo CSV HWiNFO: {args.hwinfo}")
    try:
        hw_timestamps, hw_power_watts = read_hwinfo_csv(args.hwinfo, args.power_column)
        hw_total_energy_j = integrate_trapezoidal(hw_timestamps, hw_power_watts)
        print(f"   ✓ {len(hw_timestamps)} campioni letti")
        print(f"   ✓ Energia totale HWiNFO: {hw_total_energy_j:.2f} J")
        print(f"   ✓ Tipo: energia TOTALE package CPU (HWiNFO non fa attribuzione)")
    except Exception as exc:
        print(f"❌ Errore lettura CSV HWiNFO: {exc}", file=sys.stderr)
        sys.exit(1)
    
    # Calcola statistiche
    print("\n📊 Calcolo statistiche di validazione...")
    stats = calculate_statistics(cw_total_energy_j, hw_total_energy_j)
    stats["energy_type"] = energy_type
    stats["use_package_energy"] = use_package
    
    print(f"\n{'=' * 70}")
    print("RISULTATI VALIDAZIONE")
    print(f"{'=' * 70}")
    print(f"  Tipo di confronto:        {energy_type}")
    print(f"  Energia CasualWatt:       {stats['casualwatt_energy_j']:.2f} J")
    print(f"  Energia HWiNFO:           {stats['hwinfo_energy_j']:.2f} J")
    print(f"  Differenza assoluta:      {stats['absolute_difference_j']:.2f} J")
    print(f"  Differenza relativa:      {stats['relative_difference_pct']:.2f} %")
    print(f"  Rapporto CW/HW:           {stats['ratio']:.4f}")
    print(f"{'=' * 70}")
    
    # Valutazione
    if stats['relative_difference_pct'] < 5.0:
        print("✓ VALIDAZIONE RIUSCITA: differenza < 5%")
        if use_package:
            print("  Entrambi i tool misurano l'energia TOTALE del package CPU.")
            print("  La differenza < 5% conferma che LHM legge correttamente i sensori.")
    elif stats['relative_difference_pct'] < 10.0:
        print("⚠ VALIDAZIONE ACCETTABILE: differenza 5-10%")
        print("  Suggerimento: verificare configurazione o ripetere misura")
    else:
        print("❌ VALIDAZIONE FALLITA: differenza > 10%")
        if use_package:
            print("  Possibili cause:")
            print("    - Intervalli di tempo non allineati")
            print("    - Sensori diversi letti da LHM vs HWiNFO")
            print("    - Attività di sistema durante il benchmark")
            print("    - Configurazione polling rate diversa")
        else:
            print("  ATTENZIONE: stai confrontando energia ATTRIBUITA (CasualWatt)")
            print("  con energia TOTALE (HWiNFO). La differenza è attesa!")
            print("  Usa --use-package-energy per confronto valido.")
    
    # Genera output
    print(f"\n💾 Salvo report: {args.output}")
    generate_report(stats, args.output)
    
    # Genera grafico (opzionale)
    if args.plot:
        print("\n📈 Genero grafico di confronto...")
        plot_comparison(
            hw_timestamps, hw_power_watts,
            cw_timestamps, cw_energy_j,
            output_path=args.output.replace('.json', '.png')
        )
    
    print("\n✓ Validazione completata")
    return 0 if stats['relative_difference_pct'] < 10.0 else 1


if __name__ == "__main__":
    sys.exit(main())
