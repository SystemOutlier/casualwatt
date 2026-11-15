# Durante la profilazione di una query Ollama in local_energy.py:
E_gpu_totale_mj, _ = SESSION._gpu.read_energy() # delta della finestra convertito in Joule

if E_gpu_totale_mj is not None and getattr(SESSION, "gpu_idle_power_w", None) is not None:
    E_gpu_totale_j = E_gpu_totale_mj / 1000.0
    dt_finestra = t_end - t_start
    
    # Sottrazione della baseline idle per ottenere l'energia dinamica attribuibile a Ollama
    E_gpu_ollama_dinamica_j = max(E_gpu_totale_j - (SESSION.gpu_idle_power_w * dt_finestra), 0.0)
