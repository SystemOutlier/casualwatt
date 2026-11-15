    def settle_idle(self, window_s: float = 10.0, tolerance_cpu_w: float = 0.5,
                    tolerance_gpu_w: float = 0.5, timeout_s: float = 120.0, 
                    step_s: float = 1.0) -> Optional[float]:
        """Attende la stazionarieta' simultanea della potenza CPU e GPU.

        Criterio di P1.5 esteso: due medie consecutive su finestre di ``window_s``
        devono differire meno di ``tolerance_cpu_w`` per la CPU E meno di
        ``tolerance_gpu_w`` per la GPU. 
        
        La potenza di ogni finestra e' calcolata tramite i delta dei contatori 
        di energia hardware esatti divisi per la durata reale, garantendo la 
        massima precisione scientifica senza medie temporali approssimate.

        Tetto massimo impostato a ``timeout_s``. Se la macchina non si stabilizza 
        entro il limite, il metodo ritorna ``None`` per evitare di validare 
        una baseline instabile.

        Returns:
            I secondi attesi per raggiungere la stazionarieta' [s], o None al timeout.
        """
        t0 = time.monotonic()
        prev_cpu: Optional[float] = None
        prev_gpu: Optional[float] = None

        while True:
            now = time.monotonic()
            elapsed = now - t0
            t_start = now - window_s

            # 1. Calcolo Potenza Media della CPU nella finestra tramite contatore esatto (B1)
            e_cpu_window = self.package_energy_exact_between(t_start, now)
            current_cpu = (float(e_cpu_window) / window_s 
                           if e_cpu_window is not None and window_s > 0 else None)

            # 2. Calcolo Potenza Media della GPU nella finestra tramite contatori hardware (mJ)
            with self._lock:
                samples_gpu = [s for s in self._samples if t_start <= s.t <= now]
            
            current_gpu = None
            if len(samples_gpu) >= 2:
                s_first, s_last = samples_gpu[0], samples_gpu[-1]
                dt_gpu = max(s_last.t - s_first.t, 1e-6)
                
                if s_first.gpu_energy_mj is not None and s_last.gpu_energy_mj is not None:
                    # Caso primario: Delta contatore hardware cumulativo (uJ/mJ) srotolato
                    delta_gpu_j = (s_last.gpu_energy_mj - s_first.gpu_energy_mj) / 1000.0
                    current_gpu = delta_gpu_j / dt_gpu
                else:
                    # Fallback difensivo: Media della potenza istantanea campionata nel buffer
                    valid_powers = [s.gpu_power_w for s in samples_gpu if s.gpu_power_w is not None]
                    if valid_powers:
                        current_gpu = sum(valid_powers) / len(valid_powers)

            # 3. Verifica del Criterio di Stazionarieta' Combinato
            # Entrambe le componenti devono essere leggibili e simultaneamente stabili
            if (prev_cpu is not None and current_cpu is not None and
                prev_gpu is not None and current_gpu is not None):
                
                cpu_stable = abs(current_cpu - prev_cpu) < tolerance_cpu_w
                gpu_stable = abs(current_gpu - prev_gpu) < tolerance_gpu_w
                
                if cpu_stable and gpu_stable:
                    return round(elapsed, 3)

            # Aggiornamento delle baseline per il prossimo ciclo di controllo
            if current_cpu is not None:
                prev_cpu = current_cpu
            if current_gpu is not None:
                prev_gpu = current_gpu

            # Controllo del Timeout di sicurezza
            if elapsed >= timeout_s:
                return None

            # Attesa prima del campionamento successivo
            time.sleep(max(min(step_s, timeout_s - elapsed), 0.0))
