# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import pandas as pd
import matplotlib.pyplot as plt

def generate_casualwatt_plots(csv_path: str = "./experiment_results/ollama_perf_v4.csv", output_img: str = "casualwatt_benchmark.png"):
    """Legge il report CSV di CasualWatt, valida i dati e genera il grafico scientifico."""
    if not os.path.exists(csv_path):
        print(f"[Errore] Il file CSV non esiste al percorso indicato: {csv_path}")
        return

    # 1. Caricamento dei dati trattando esplicitamente i marker 'N/A' del nostro framework
    df = pd.read_csv(csv_path, na_values=["N/A"])

    # 2. Filtraggio preventivo basato sul canale 'generation_status' convalidato dal motore
    df_valid = df[df["generation_status"] == "success"].copy()

    if df_valid.empty:
        print("[Avviso] Nessun record con stato 'success' trovato nel CSV. Impossibile tracciare i grafici.")
        return

    # Conversione esplicita delle colonne in numerico per sicurezza metrologica
    df_valid["joules_per_token"] = pd.to_numeric(df_valid["joules_per_token"])
    df_valid["tokens_per_second"] = pd.to_numeric(df_valid["tokens_per_second"])

    # 3. Aggregazione per modello (Calcolo della media geometrica/aritmetica dei run stabili)
    grouped = df_valid.groupby("model_name").agg({
        "joules_per_token": "mean",
        "tokens_per_second": "mean"
    }).reset_index()

    # Ordinamento decrescente per efficienza energetica (i modelli migliori saranno a destra)
    grouped = grouped.sort_values(by="joules_per_token", ascending=False)

    # 4. Costruzione del Plot a Doppio Asse
    fig, ax1 = plt.subplots(figsize=(11, 6))
    
    # Abilita una griglia pulita di sfondo
    ax1.grid(True, linestyle="--", alpha=0.5, axis="y")

    # Disegno delle barre primarie: Joule per Token
    color_bars = "#1f77b4"  # Blu avio
    bars = ax1.bar(
        grouped["model_name"], 
        grouped["joules_per_token"], 
        color=color_bars, 
        alpha=0.75, 
        width=0.35, 
        label="Efficienza (Joule / Token)"
    )
    
    ax1.set_xlabel("Modelli LLM (Ollama)", fontsize=12, fontweight="bold", labelpad=12)
    ax1.set_ylabel("Efficienza Energetica (J/Token) - Meno è meglio", color=color_bars, fontsize=12, fontweight="bold")
    ax1.tick_params(axis="y", labelcolor=color_bars)

    # Aggiunta dei tag numerici precisi a 4 cifre sopra ogni barra
    for bar in bars:
        yval = bar.get_height()
        ax1.text(
            bar.get_x() + bar.get_width() / 2.0, 
            yval + (yval * 0.02), 
            f"{yval:.4f} J/T", 
            ha="center", 
            va="bottom", 
            fontweight="bold", 
            color="#222222",
            fontsize=10
        )

    # Creazione dell'asse gemello destro per la velocità di generazione
    ax2 = ax1.twinx()
    color_line = "#d62728"  # Rosso mattone
    ax2.plot(
        grouped["model_name"], 
        grouped["tokens_per_second"], 
        color=color_line, 
        marker="o", 
        linewidth=2.5, 
        markersize=8, 
        label="Velocità (Token / Secondo)"
    )
    
    ax2.set_ylabel("Throughput di Generazione (Token/s) - Più è meglio", color=color_line, fontsize=12, fontweight="bold")
    ax2.tick_params(axis="y", labelcolor=color_line)
    ax2.grid(False)  # Impedisce la sovrapposizione disordinata delle linee di griglia

    # Titolo scientifico e ottimizzazione dei margini
    plt.title("CasualWatt Benchmark: Trade-off tra Consumo Energetico e Velocità di Inferenza", fontsize=13, fontweight="bold", pad=20)
    fig.tight_layout()

    # Salva il file immagine ad alta risoluzione pronto per paper o documentazione
    plt.savefig(output_img, dpi=300)
    print(f"[CasualWatt] Grafico a barre generato ed esportato con successo in: {output_img}")

if __name__ == "__main__":
    generate_casualwatt_plots()
