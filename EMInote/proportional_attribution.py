# --- Da inserire nella fase di calcolo delle metriche di local_energy.py ---

# 1. Recupera l'energia esatta letta dal contatore hardware cumulativo Windows EMI / RAPL
e_ttft_total_j = SESSION.package_energy_exact_between(t_start, t_ttft)

# 2. Estrai i campioni della sessione CasualWatt che cadono esattamente nella finestra TTFT
samples_ttft = SESSION.samples_between(t_start, t_ttft)

ollama_cpu_ttft_j = 0.0  # Valore di fallback

if e_ttft_total_j is not None and len(samples_ttft) >= 2:
    first_sample = samples_ttft[0]
    last_sample = samples_ttft[-1]
    
    # Delta del tempo CPU totale in cui il sistema è stato attivo (busy) nella sottofinestra
    # Questo valore esclude i cicli in cui la CPU è rimasta in stato di Idle generico
    delta_sys_busy_s = last_sample.cpu_busy_seconds - first_sample.cpu_busy_seconds
    
    # Delta del tempo CPU (User + System) consumato strettamente dall'albero dei processi Ollama
    # (Incluso il demone principale e i runner figli come llama-server)
    delta_ollama_cpu_s = last_sample.ollama_cpu_seconds - first_sample.ollama_cpu_seconds
    
    # Gestione difensiva: applichiamo la proporzione solo se c'è stato effettivo lavoro di sistema
    if delta_sys_busy_s > 0 and delta_ollama_cpu_s >= 0:
        # La frazione non può matematicamente superare 1.0 (limite difensivo del framework)
        frazione_cpu_ollama = min(delta_ollama_cpu_s / delta_sys_busy_s, 1.0)
        
        # Isola la quota energetica di Ollama dall'eventuale rumore di fondo di Windows
        ollama_cpu_ttft_j = round(e_ttft_total_j * frazione_cpu_ollama, 4)
    else:
        # Se il delta è zero o infinitesimo (finestra troppo breve per il campionamento psutil),
        # si applica un fallback conservativo impostando la quota a 0 o al totale del pacchetto.
        ollama_cpu_ttft_j = 0.0

# Aggiungi il valore mappato al dizionario delle metriche finali
metrics["cpu_energy_attributed_ttft_j"] = ollama_cpu_ttft_j
metrics["cpu_energy_noise_background_ttft_j"] = round(max(e_ttft_total_j - ollama_cpu_ttft_j, 0.0), 4) if e_ttft_total_j else 0.0
