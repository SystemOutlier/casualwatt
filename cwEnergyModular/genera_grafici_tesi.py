# -*- coding: utf-8 -*-
"""
genera_grafici_tesi.py - Grafici per la Tesi di Laurea CasualWatt
==================================================================

Genera 3 grafici in alta risoluzione (300 DPI) dai dati del benchmark:

1. Frontiera di Pareto: Accuratezza vs Energia (scala log X)
   - Annotazioni sui "sweet spot" (miglior ECE)
2. Boxplot Accuratezza per provider (ollama vs cloud)
3. Throughput (token/s) vs Energia

Output:
  - results/grafici_tesi/01_pareto_accuracy_vs_energy.png
  - results/grafici_tesi/02_boxplot_accuracy_per_provider.png
  - results/grafici_tesi/03_throughput_vs_energy.png
  - results/grafici_tesi/summary_table.md

Uso:
  py genera_grafici_tesi.py [--input results/casualwatt_results.csv]

Autore: Massimo Danilo Giuliana - Tesi CasualWatt
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
# Stile grafico per tesi (pulito, professionale)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'legend.fontsize': 10,
    'figure.figsize': (10, 6),
})

# Colori per categoria
COLORS = {
    'local': '#2ecc71',      # Verde - Modelli locali Ollama
    'cloud': '#3498db',      # Blu - Modelli cloud
    'baseline': '#95a5a6',   # Grigio - Baseline
}


def load_and_clean_data(csv_path: str) -> pd.DataFrame:
    """
    Carica e pulisce i dati del CSV.
    
    Filtri applicati:
    - model_name non vuoto
    - end_to_end_energy_j > 0 (esclude righe di test/calibrazione)
    - acc_comp non NaN
    - Sostituisce inf/-inf con NaN in ECE/EPCL
    """
    df = pd.read_csv(csv_path)
    
    # Sostituisci inf e -inf con NaN
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    
    # Filtri di validita'
    initial_count = len(df)
    
    # Filtra model_name vuoto
    df = df[df['model_name'].notna() & (df['model_name'].str.strip() != '')]
    
    # Filtra energia <= 0 (esclude righe di test/calibrazione)
    df = df[df['end_to_end_energy_j'] > 0]
    
    # Filtra acc_comp NaN
    df = df[df['acc_comp'].notna()]
    
    filtered_count = initial_count - len(df)
    if filtered_count > 0:
        print(f"  Filtrate {filtered_count} righe non valide")
    
    # Crea colonne derivate
    df['tokens_per_second'] = df['output_tokens'] / df['duration_s'].replace(0, np.nan)
    df['provider_type'] = df['provider'].apply(
        lambda x: 'cloud' if x != 'ollama' else 'local'
    )
    
    return df


# ==============================================================================
# GRAFICO 1: FRONTIERA DI PARETO (Accuracy vs Energia)
# ==============================================================================
def plot_pareto_frontier(df: pd.DataFrame, output_dir: Path):
    """
    Grafico principale: accuratezza composita vs energia end-to-end.
    Scala logaritmica sull'asse X (ampio range di energie).
    Annotazioni sui "sweet spot" (miglior ECE = acc_comp/energia).
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Separa locali e cloud
    local = df[df['provider'] == 'ollama']
    cloud = df[df['provider'] != 'ollama']
    
    # Scatter plot locali (per modello)
    for model in local['model_name'].unique():
        subset = local[local['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['acc_comp'],
            label=f"Locale: {model}",
            alpha=0.7,
            s=60,
            edgecolors='black',
            linewidth=0.5,
            color=COLORS['local']
        )
    
    # Scatter plot cloud
    for model in cloud['model_name'].unique():
        subset = cloud[cloud['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['acc_comp'],
            label=f"Cloud: {model}",
            alpha=0.7,
            s=80,
            marker='^',
            edgecolors='black',
            linewidth=0.5,
            color=COLORS['cloud']
        )
    
    # Linea di frontiera di Pareto (approssimazione)
    df_sorted = df.sort_values('end_to_end_energy_j')
    pareto_y = df_sorted['acc_comp'].cummax()
    ax.plot(df_sorted['end_to_end_energy_j'], pareto_y,
            'k--', alpha=0.4, linewidth=1.5, label='Frontiera di Pareto')
    
    ax.set_xlabel('Energia End-to-End (Joule)')
    ax.set_ylabel('Accuratezza Composita (acc_comp)')
    ax.set_title('Frontiera di Pareto: Accuratezza vs Consumo Energetico\n'
                 'CasualWatt Benchmark - Tesi di Laurea',
                 fontweight='bold')
    ax.set_xscale('log')  # Scala logaritmica per energia
    ax.legend(loc='lower right', fontsize=9, ncol=1)
    ax.grid(True, alpha=0.3)
    
    # Annotazioni sui "sweet spot" (miglior ECE = acc_comp/energia)
    df_with_ece = df.copy()
    df_with_ece['ece'] = df_with_ece['acc_comp'] / df_with_ece['end_to_end_energy_j']
    sweet_spots = df_with_ece.nlargest(3, 'ece')
    
    for _, row in sweet_spots.iterrows():
        ax.annotate(
            f"{row['model_name'][:20]}\n{row['end_to_end_energy_j']:.1f}J",
            (row['end_to_end_energy_j'], row['acc_comp']),
            textcoords="offset points",
            xytext=(10, 10),
            fontsize=8,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7)
        )
    
    plt.tight_layout()
    output_path = output_dir / "01_pareto_accuracy_vs_energy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"  Salvato: {output_path}")
    plt.close()


# ==============================================================================
# GRAFICO 2: BOXPLOT ACCURATEZZA PER PROVIDER
# ==============================================================================
def plot_boxplot_accuracy(df: pd.DataFrame, output_dir: Path):
    """
    Boxplot dell'accuratezza composita per provider (ollama vs cloud).
    Mostra la distribuzione e la variabilita' delle prestazioni.
    """
    fig, ax = plt.subplots(figsize=(8, 6))
    
    # Prepara dati per boxplot
    df_plot = df[['provider_type', 'acc_comp']].dropna()
    
    # Raggruppa per provider
    data_local = df_plot[df_plot['provider_type'] == 'local']['acc_comp'].values
    data_cloud = df_plot[df_plot['provider_type'] == 'cloud']['acc_comp'].values
    
    # Crea boxplot
    bp = ax.boxplot(
        [data_local, data_cloud],
        tick_labels=['Locale (Ollama)', 'Cloud'],
        patch_artist=True,
        widths=0.6
    )
    
    # Colora i box
    colors = [COLORS['local'], COLORS['cloud']]
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax.set_ylabel('Accuratezza Composita (acc_comp)')
    ax.set_title('Distribuzione Accuratezza per Provider',
                 fontweight='bold')
    ax.grid(True, alpha=0.3, axis='y')
    
    # Aggiungi statistiche
    for i, (data, label) in enumerate([(data_local, 'Locale'), (data_cloud, 'Cloud')], 1):
        if len(data) > 0:
            median = np.median(data)
            ax.text(i, median, f'med={median:.3f}',
                    ha='center', va='bottom', fontsize=9,
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
    
    plt.tight_layout()
    output_path = output_dir / "02_boxplot_accuracy_per_provider.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"  Salvato: {output_path}")
    plt.close()


# ==============================================================================
# GRAFICO 3: THROUGHPUT vs ENERGIA
# ==============================================================================
def plot_throughput_vs_energy(df: pd.DataFrame, output_dir: Path):
    """
    Velocita' di inferenza (token/s) vs energia consumata.
    Mostra l'efficienza computazionale dei modelli.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Filtra righe con tokens_per_second valido
    valid = df[df['tokens_per_second'].notna() & (df['tokens_per_second'] > 0)].copy()
    
    # Separa locali e cloud
    local = valid[valid['provider'] == 'ollama']
    cloud = valid[valid['provider'] != 'ollama']
    
    # Scatter plot locali
    for model in local['model_name'].unique():
        subset = local[local['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['tokens_per_second'],
            label=f"Locale: {model}",
            alpha=0.7,
            s=60,
            edgecolors='black',
            linewidth=0.5,
            color=COLORS['local']
        )
    
    # Scatter plot cloud
    for model in cloud['model_name'].unique():
        subset = cloud[cloud['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['tokens_per_second'],
            label=f"Cloud: {model}",
            alpha=0.7,
            s=80,
            marker='^',
            edgecolors='black',
            linewidth=0.5,
            color=COLORS['cloud']
        )
    
    ax.set_xlabel('Energia End-to-End (Joule)')
    ax.set_ylabel('Velocita\' (Token/secondo)')
    ax.set_title('Throughput vs Consumo Energetico\n'
                 'Efficienza computazionale dei modelli',
                 fontweight='bold')
    ax.set_xscale('log')
    ax.legend(loc='best', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_path = output_dir / "03_throughput_vs_energy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"  Salvato: {output_path}")
    plt.close()


# ==============================================================================
# TABELLA RIEPILOGATIVA (Markdown)
# ==============================================================================
def generate_summary_table(df: pd.DataFrame, output_dir: Path):
    """
    Genera una tabella Markdown con le medie per modello.
    Include: energia, accuratezza, throughput, token output, durata.
    """
    summary = df.groupby(['model_name', 'provider_type']).agg({
        'end_to_end_energy_j': 'mean',
        'acc_comp': 'mean',
        'tokens_per_second': 'mean',
        'output_tokens': 'mean',
        'duration_s': 'mean'
    }).round(3).reset_index()
    
    # Rinomina colonne per chiarezza
    summary.columns = [
        'Modello', 'Provider', 'Energia Media (J)', 'Accuratezza Media',
        'Throughput Medio (tok/s)', 'Token Output Medi', 'Durata Media (s)'
    ]
    
    output_path = output_dir / "summary_table.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Tabella Riepilogativa Benchmark CasualWatt\n\n")
        f.write("*Generato automaticamente da genera_grafici_tesi.py*\n\n")
        
        # Genera tabella markdown manualmente (senza dipendenza tabulate)
        headers = list(summary.columns)
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for _, row in summary.iterrows():
            f.write("| " + " | ".join([str(v) for v in row]) + " |\n")
        
        f.write("\n\n## Note\n\n")
        f.write(f"- Numero di righe valide analizzate: {len(df)}\n")
        f.write(f"- Modelli locali: {len(df[df['provider_type'] == 'local'])}\n")
        f.write(f"- Modelli cloud: {len(df[df['provider_type'] == 'cloud'])}\n")
    
    print(f"  Salvato: {output_path}")
    print("\nAnteprima tabella:")
    print(summary.to_string(index=False))


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Genera grafici per la tesi di laurea CasualWatt"
    )
    parser.add_argument(
        "--input",
        default="results/casualwatt_results.csv",
        help="Path del CSV input (default: results/casualwatt_results.csv)"
    )
    args = parser.parse_args()
    
    csv_path = args.input
    output_dir = Path("results/grafici_tesi")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("GENERAZIONE GRAFICI PER TESI CASUALWATT")
    print("=" * 70)
    
    if not Path(csv_path).exists():
        print(f"ERRORE: CSV non trovato: {csv_path}")
        print("Esegui prima il benchmark.")
        sys.exit(1)
    
    print(f"\nCaricamento dati da: {csv_path}")
    df = load_and_clean_data(csv_path)
    print(f"Righe valide: {len(df)}")
    
    if len(df) == 0:
        print("ERRORE: nessuna riga valida dopo i filtri")
        sys.exit(1)
    
    print(f"\nOutput in: {output_dir}")
    print("-" * 70)
    
    print("\n[1/4] Frontiera di Pareto...")
    plot_pareto_frontier(df, output_dir)
    
    print("\n[2/4] Boxplot Accuratezza per Provider...")
    plot_boxplot_accuracy(df, output_dir)
    
    print("\n[3/4] Throughput vs Energia...")
    plot_throughput_vs_energy(df, output_dir)
    
    print("\n[4/4] Tabella riepilogativa...")
    generate_summary_table(df, output_dir)
    
    print("\n" + "=" * 70)
    print("TUTTI I GRAFICI SONO STATI GENERATI!")
    print(f"Cartella output: {output_dir.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
