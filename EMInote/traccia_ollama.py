from codecarbon import EmissionsTracker
import ollama

# 1. Inizializza il tracker impostando esplicitamente la modalità "process"
tracker = EmissionsTracker(
    project_name="ollama_inference_benchmark",
    tracking_mode="process",          # <--- Forza l'isolamento del processo Python e dei suoi figli
    measure_power_seconds=5,         # Intervallo di campionamento (ridotto a 5s per maggiore precisione sui modelli rapidi)
    output_dir="./energy_reports",
    output_file="ollama_emissions.csv"
)

try:
    # 2. Avvia il tracciamento
    tracker.start()
    
    # 3. Esegui la chiamata a Ollama (il tuo carico di lavoro da misurare)
    response = ollama.chat(
        model='llama3', 
        messages=[{'role': 'user', 'content': 'Spiegami la fusione nucleare in due frasi.'}]
    )
    print(response['message']['content'])

finally:
    # 4. Ferma il tracciamento (assicura la scrittura dei dati anche in caso di errore)
    emissions_data = tracker.stop()
    print(f"\n[Framework] Monitoraggio completato. Consumo stimato per il processo: {emissions_data} kg CO2eq")
