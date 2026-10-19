# -*- coding: utf-8 -*-
"""
test_synthetic_window.py — Test sintetico con finestra di 0.4 s.

Verifica che la lettura esatta di cpu_times agli estremi [t_start, t_end]
funzioni correttamente per finestre brevi (< 0.5 s, meno di un campione).
"""
import time
import psutil
from energy.local_energy import CasualWattLocalEnergyProfiler


def test_exact_cpu_times_reading():
    """Test: lettura cpu_times a estremi esatti con finestra di 0.4 s."""
    print("\n=== Test sintetico: finestra 0.4 s ===")
    
    # Trova un processo attivo (questo stesso script)
    current_pid = psutil.Process().pid
    pids = [current_pid]
    
    # Leggi cpu_times a t_start
    cpu_t_start = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(pids)
    print(f"cpu_times a t_start: {cpu_t_start:.6f} s")
    
    # Esegui lavoro CPU per ~0.4 s
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < 0.4:
        _ = sum(i * i for i in range(10000))
    
    # Leggi cpu_times a t_end
    cpu_t_end = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(pids)
    print(f"cpu_times a t_end:   {cpu_t_end:.6f} s")
    
    # Calcola delta
    delta = cpu_t_end - cpu_t_start
    print(f"Delta cpu_times:     {delta:.6f} s")
    
    # Verifica che il delta sia positivo e ragionevole (dovrebbe essere ~0.4 s)
    assert delta >= 0, f"Delta negativo: {delta}"
    assert delta < 2.0, f"Delta troppo grande: {delta} (aspettato ~0.4 s)"
    
    print(f"[OK] Delta corretto: {delta:.3f} s (aspettato ~0.4 s)")
    return delta


def test_profile_window_with_direct_delta():
    """Test: profile_window con direct_cpu_delta fornito."""
    print("\n=== Test: profile_window con direct_cpu_delta ===")
    
    from energy.energy_session import SESSION
    
    # Avvia sessione se non attiva
    if not SESSION.running:
        SESSION.start()
        time.sleep(0.5)
    
    # Simula una richiesta con finestra di 0.4 s
    t_start = time.monotonic()
    
    # Esegui lavoro CPU
    _ = sum(i * i for i in range(50000))
    
    t_end = time.monotonic()
    
    # Leggi cpu_times agli estremi
    current_pid = psutil.Process().pid
    pids = [current_pid]
    cpu_t_start = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(pids)
    
    # Simula lavoro aggiuntivo
    _ = sum(i * i for i in range(50000))
    
    cpu_t_end = CasualWattLocalEnergyProfiler._read_ollama_cpu_times(pids)
    direct_delta = cpu_t_end - cpu_t_start
    
    print(f"Finestra: {t_end - t_start:.3f} s")
    print(f"Direct CPU delta: {direct_delta:.6f} s")
    
    # Chiama profile_window con direct_cpu_delta
    profiler = CasualWattLocalEnergyProfiler()
    result = profiler.profile_window(
        t_start, t_end,
        ollama_pids=pids,
        direct_cpu_delta=direct_delta,
    )
    
    print(f"d_ollama_cpu_s: {result.d_ollama_cpu_s:.6f}")
    print(f"d_busy_s: {result.d_busy_s:.6f}")
    print(f"cpu_time_share: {result.cpu_time_share:.6f}")
    print(f"n_samples_in_window: {result.n_samples_in_window}")
    print(f"ollama_pids_used: {result.ollama_pids_used}")
    
    # Verifica che i campi diagnostici siano popolati
    assert result.d_ollama_cpu_s >= 0, "d_ollama_cpu_s negativo"
    assert result.n_samples_in_window >= 0, "n_samples_in_window negativo"
    assert result.ollama_pids_used, "ollama_pids_used vuoto"
    
    print("[OK] Campi diagnostici popolati correttamente")
    
    # Verifica che la nota sulla lettura esatta sia presente
    has_exact_note = any("lettura esatta agli estremi" in n for n in result.notes)
    assert has_exact_note, "Nota 'lettura esatta agli estremi' non trovata"
    print("[OK] Nota diagnostica presente")
    
    return result


if __name__ == "__main__":
    try:
        test_exact_cpu_times_reading()
        test_profile_window_with_direct_delta()
        print("\n=== Tutti i test passati ===")
    except Exception as e:
        print(f"\n[FAIL] Test fallito: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
