"""
genera_grafici_tesi.py - Grafici per il Capitolo 4 della Tesi
=============================================================
Genera 3 grafici in alta risoluzione (300 DPI) dai dati del benchmark:

1. Frontiera di Pareto: Accuratezza vs Energia (locale)
2. Confronto Lessicale vs Semantico (se disponibile)
3. Throughput (token/s) vs Energia per modello

Output: cartella results/grafici_tesi/
Autore: Massimo Danilo Giuliana
"""
import os
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================
CSV_PATH = "results/casualwatt_results.csv"
OUTPUT_DIR = Path("results/grafici_tesi")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Stile grafico per tesi (pulito, professionale)
plt.style.use('seaborn-v0_8-whitegrid')
plt.rcParams.update({
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'font.size': 12,
    'axes.labelsize': 13,
    'axes.titlesize': 14,
    'legend.fontsize': 11,
    'figure.figsize': (12, 7),
})

# Colori per categoria
COLORS = {
    'local_small': '#2ecc71',      # Verde - SLM locali
    'local_medium': '#3498db',     # Blu - Modelli medi
    'cloud': '#e74c3c',            # Rosso - Cloud
    'baseline': '#95a5a6',         # Grigio - Baseline
}


def load_and_clean_data(csv_path: str) -> pd.DataFrame:
    """Carica e pulisce i dati del CSV."""
    df = pd.read_csv(csv_path)
    
    # Sostituisci inf e -inf con NaN
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    
    # Filtra righe valide (energia > 0 e accuratezza presente)
    df = df[df['end_to_end_energy_j'] > 0].copy()
    df = df[df['acc_comp'].notna()].copy()
    
    # Crea colonne derivate
    df['energy_per_token_j'] = df['end_to_end_energy_j'] / df['output_tokens'].replace(0, np.nan)
    df['provider_type'] = df['provider'].apply(
        lambda x: 'cloud' if x != 'ollama' else 'local'
    )
    
    return df


# ==============================================================================
# GRAFICO 1: FRONTIERA DI PARETO (Accuracy vs Energia)
# ==============================================================================
def plot_pareto_frontier(df: pd.DataFrame):
    """Grafico principale: accuratezza composita vs energia end-to-end."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    # Separa locali e cloud
    local = df[df['provider'] == 'ollama']
    cloud = df[df['provider'] != 'ollama']
    
    # Scatter plot locali (per modello)
    for model in local['model_name'].unique():
        subset = local[local['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['acc_comp'],
            label=f"Local: {model}",
            alpha=0.7,
            s=80,
            edgecolors='black',
            linewidth=0.5
        )
    
    # Scatter plot cloud
    for model in cloud['model_name'].unique():
        subset = cloud[cloud['model_name'] == model]
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['acc_comp'],
            label=f"Cloud: {model}",
            alpha=0.7,
            s=120,
            marker='^',
            edgecolors='black',
            linewidth=0.5
        )
    
    # Linea di frontiera di Pareto (approssimazione)
    df_sorted = df.sort_values('end_to_end_energy_j')
    pareto_y = df_sorted['acc_comp'].cummax()
    ax.plot(df_sorted['end_to_end_energy_j'], pareto_y, 
            'k--', alpha=0.4, linewidth=1.5, label='Frontiera di Pareto')
    
    ax.set_xlabel('Energia End-to-End (Joule)', fontsize=13)
    ax.set_ylabel('Accuratezza Composita (Acc_Comp)', fontsize=13)
    ax.set_title('Frontiera di Pareto: Accuratezza vs Consumo Energetico\n'
                 'CasualWatt Benchmark - Tesi di Laurea', fontsize=14, fontweight='bold')
    ax.set_xscale('log')  # Scala logaritmica per energia (ampio range)
    ax.legend(loc='lower right', fontsize=10, ncol=2)
    ax.grid(True, alpha=0.3)
    
    # Annotazioni sui "sweet spot"
    sweet_spots = df.nlargest(3, 'acc_comp').head(3)
    for _, row in sweet_spots.iterrows():
        ax.annotate(
            f"{row['model_name']}\n{row['end_to_end_energy_j']:.1f}J",
            (row['end_to_end_energy_j'], row['acc_comp']),
            textcoords="offset points",
            xytext=(10, 10),
            fontsize=9,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7)
        )
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "01_pareto_accuracy_vs_energy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Salvato: {output_path}")
    plt.close()


# ==============================================================================
# GRAFICO 2: CONFRONTO METODI DI VALUTAZIONE
# ==============================================================================
def plot_evaluation_methods(df: pd.DataFrame):
    """
    Confronto tra giudice lessicale e semantico.
    Mostra la distribuzione dell'accuratezza per metodo.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    
    # Istogramma distribuzione Acc_Comp
    axes[0].hist(df['acc_comp'].dropna(), bins=20, 
                 color='steelblue', edgecolor='black', alpha=0.7)
    axes[0].set_xlabel('Accuratezza Composita (Acc_Comp)')
    axes[0].set_ylabel('Frequenza')
    axes[0].set_title('Distribuzione Accuratezza (Giudice Lessicale)')
    axes[0].axvline(df['acc_comp'].median(), color='red', 
                    linestyle='--', label=f"Mediana: {df['acc_comp'].median():.3f}")
    axes[0].legend()
    
    # Boxplot per provider
    df_plot = df[['provider', 'acc_comp']].dropna()
    df_plot['provider_short'] = df_plot['provider'].apply(
        lambda x: 'Ollama (Locale)' if x == 'ollama' else x.title()
    )
    bp = axes[1].boxplot(
        [group['acc_comp'].values 
         for _, group in df_plot.groupby('provider_short')],
        labels=df_plot['provider_short'].unique(),
        patch_artist=True
    )
    for patch, color in zip(bp['boxes'], ['#2ecc71', '#e74c3c', '#f39c12']):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    axes[1].set_ylabel('Accuratezza Composita')
    axes[1].set_title('Accuratezza per Provider')
    axes[1].tick_params(axis='x', rotation=45)
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "02_evaluation_methods_comparison.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Salvato: {output_path}")
    plt.close()


# ==============================================================================
# GRAFICO 3: THROUGHPUT vs ENERGIA
# ==============================================================================
def plot_throughput_vs_energy(df: pd.DataFrame):
    """Velocità di inferenza (token/s) vs energia consumata."""
    fig, ax = plt.subplots(figsize=(12, 7))
    
    valid = df[df['tokens_per_second'] > 0].copy()
    
    for provider in valid['provider'].unique():
        subset = valid[valid['provider'] == provider]
        color = COLORS['local_small'] if provider == 'ollama' else COLORS['cloud']
        marker = 'o' if provider == 'ollama' else '^'
        
        ax.scatter(
            subset['end_to_end_energy_j'],
            subset['tokens_per_second'],
            label=provider,
            alpha=0.7,
            s=80,
            marker=marker,
            color=color,
            edgecolors='black',
            linewidth=0.5
        )
    
    ax.set_xlabel('Energia End-to-End (Joule)', fontsize=13)
    ax.set_ylabel('Velocità (Token/secondo)', fontsize=13)
    ax.set_title('Throughput vs Consumo Energetico\n'
                 'Efficienza computazionale dei modelli', fontsize=14, fontweight='bold')
    ax.set_xscale('log')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / "03_throughput_vs_energy.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"✅ Salvato: {output_path}")
    plt.close()


# ==============================================================================
# TABELLA RIEPILOGATIVA (per LaTeX/Word)
# ==============================================================================
def generate_summary_table(df: pd.DataFrame):
    """Genera una tabella Markdown con le medie per modello."""
    summary = df.groupby(['model_name', 'provider']).agg({
        'end_to_end_energy_j': 'mean',
        'acc_comp': 'mean',
        'tokens_per_second': 'mean',
        'output_tokens': 'mean',
        'duration_s': 'mean'
    }).round(3).reset_index()
    
    output_path = OUTPUT_DIR / "summary_table.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# Tabella Riepilogativa Benchmark CasualWatt\n\n")
        f.write(summary.to_markdown(index=False))
        f.write("\n\n*Generato automaticamente da genera_grafici_tesi.py*\n")
    
    print(f"✅ Tabella riepilogativa: {output_path}")
    print("\nAnteprima tabella:")
    print(summary.to_string(index=False))


# ==============================================================================
# MAIN
# ==============================================================================
def main():
    print("=" * 70)
    print("📊 GENERAZIONE GRAFICI PER TESI CASUALWATT")
    print("=" * 70)
    
    if not os.path.exists(CSV_PATH):
        print(f"❌ CSV non trovato: {CSV_PATH}")
        print("Esegui prima il benchmark.")
        return
    
    print(f"\n📂 Caricamento dati da: {CSV_PATH}")
    df = load_and_clean_data(CSV_PATH)
    print(f"✅ Caricate {len(df)} righe valide")
    
    print(f"\n📁 Output in: {OUTPUT_DIR}")
    print("-" * 70)
    
    print("\n🎨 Generazione Grafico 1: Frontiera di Pareto...")
    plot_pareto_frontier(df)
    
    print("\n🎨 Generazione Grafico 2: Confronto Metodi di Valutazione...")
    plot_evaluation_methods(df)
    
    print("\n🎨 Generazione Grafico 3: Throughput vs Energia...")
    plot_throughput_vs_energy(df)
    
    print("\n📋 Generazione tabella riepilogativa...")
    generate_summary_table(df)
    
    print("\n" + "=" * 70)
    print("✅ TUTTI I GRAFICI SONO STATI GENERATI!")
    print(f"📁 Cartella output: {OUTPUT_DIR.resolve()}")
    print("=" * 70)


if __name__ == "__main__":
    main()