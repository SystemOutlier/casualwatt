import time
import psutil

def track_ollama_energy_windows(duration_seconds=10, tdp_watts=45.0):
    """
    Calcola il consumo stimato in Joule dedicato a Ollama su Windows 11.
    Usa l'approssimazione accademica basata sull'utilizzo CPU normalizzato e il TDP dell'i9-13900HK.
    """
    print(f"Inizio monitoraggio su Windows 11 per i processi Ollama ({duration_seconds}s)...")
    print(f"TDP Nominale impostato: {tdp_watts}W")
    
    total_ollama_joules = 0.0
    interval = 1.0
    elapsed = 0.0
    
    # Inizializza il contatore CPU complessivo
    psutil.cpu_percent(interval=None)
    
    while elapsed < duration_seconds:
        start_loop = time.time()
        
        # 1. Identifica i processi attivi di Ollama (sia l'interfaccia che il server logico)
        ollama_pids = []
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and 'ollama' in proc.info['name'].lower():
                ollama_pids.append(proc.info['pid'])
        
        if not ollama_pids:
            print("Nessun processo Ollama rilevato in esecuzione su Windows.")
            time.sleep(interval)
            elapsed += interval
            continue
            
        # 2. Calcola l'uso della CPU da parte di Ollama 
        # Su Windows psutil restituisce l'uso aggregato sui core (es. 400% = 4 core attivi)
        ollama_cpu_total = 0.0
        num_cores = psutil.cpu_count()
        
        for pid in ollama_pids:
            try:
                p = psutil.Process(pid)
                # Dividiamo per il numero di core per riportarlo sulla scala 0-100% dell'intero chip
                ollama_cpu_total += p.cpu_percent(interval=None) / num_cores
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        # 3. Calcolo dei Watt teorici istantanei assorbiti dal processo
        # Formula di stima lineare (Power Model standard): 
        # Consumo = Potenza_Idle + (Uso_CPU_Ollama * (TDP - Potenza_Idle))
        # Consideriamo prudenzialmente una Potenza_Idle minima del pacchetto i9 a 10W
        power_idle = 10.0 
        
        if ollama_cpu_total > 0:
            # Calcola la quota parte di potenza dinamica generata dal carico di Ollama
            ollama_power_watts = power_idle + ((ollama_cpu_total / 100.0) * (tdp_watts - power_idle))
        else:
            ollama_power_watts = 0.0
            
        # Garantisce che la stima non superi matematicamente i limiti fisici massimi impostati
        ollama_power_watts = min(ollama_power_watts, 115.0) # PL2 max dell'i9-13900HK
        
        # 4. Converti i Watt in Joule (Energia = Potenza * Tempo)
        loop_time = time.time() - start_loop
        joules_in_interval = ollama_power_watts * loop_time
        total_ollama_joules += joules_in_interval
        
        print(f"| Carico Ollama: {ollama_cpu_total:.1f}% | Assorbimento Stimato: {ollama_power_watts:.2f}W | Joule: {joules_in_interval:.4f}J")
        
        # Allinea lo sleep temporale
        time_to_sleep = max(0.1, interval - (time.time() - start_loop))
        time.sleep(time_to_sleep)
        elapsed += (time.time() - start_loop)
        
    print("-" * 60)
    print(f"MONITORAGGIO TERMINATO.")
    print(f"Energia totale stimata per Ollama: {total_ollama_joules:.2f} Joule")
    return total_ollama_joules

if __name__ == "__main__":
    # Avvia il tracciamento impostando il TDP del tuo processore (45W)
    track_ollama_energy_windows(duration_seconds=10, tdp_watts=45.0)
