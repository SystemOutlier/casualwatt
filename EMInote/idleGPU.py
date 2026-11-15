    def calibrate_gpu_idle(self, seconds: Optional[float] = None) -> float:
        """Calibrazione idle empirica via backend energetico GPU (NVML/AMD SMI).
        
        Procedura simmetrica alla calibrazione CPU (Spec §5):
          1. Durata >= 30 s per singola finestra (configurabile da env);
          2. 3 ripetizioni consecutive a riposo (senza inferenze Ollama attive);
          3. Potenza media = delta mJ / (dt_real * 1000) o basata sull'integrale P(t);
          4. P_gpu_idle = MEDIANA delle tre potenze medie osservate [W].
        """
        import config as _cfg
        import os as _os

        # Spec §5: Minimo 30 secondi per finestra per stabilizzare i transienti
        duration_s = float(seconds or _cfg.IDLE_CALIBRATION_SECONDS)
        try:
            window_floor = float(_os.getenv("CW_IDLE_WINDOW_S", "30"))
        except (TypeError, ValueError):
            window_floor = 30.0
        duration_s = max(duration_s, window_floor)

        was_running = self._running
        if not was_running:
            self.start()

        # Verifica preliminare della disponibilità hardware
        if not self._gpu.available:
            raise RuntimeError(
                f"Calibrazione idle GPU fallita: monitor hardware non disponibile o disabilitato. "
                f"Dettagli errore: {self._gpu.error}"
            )

        try:
            # Breve cooldown del silicio prima di iniziare
            time.sleep(1.0)
            gpu_means: List[float] = []

            if self.on_progress:
                self.on_progress(
                    f"Finestra idle GPU: {duration_s:.0f} s x 3 ripetizioni. "
                    f"Assicurarsi che Ollama non stia eseguendo inferenze..."
                )

            for rep in range(3):
                if self.on_progress:
                    self.on_progress(
                        f"Calibrazione idle GPU: ripetizione {rep + 1}/3 in corso ({duration_s:.0f} s)…"
                    )

                # Lettura dei contatori cumulativi iniziali (mJ)
                mj_start, ts_start = self._gpu.read_energy()
                t0 = time.monotonic()

                time.sleep(duration_s)

                # Lettura dei contatori cumulativi finali
                mj_end, ts_end = self._gpu.read_energy()
                dt = max(time.monotonic() - t0, 1e-6)

                # Gestione del calcolo della potenza media per la ripetizione corrente
                if mj_start is not None and mj_end is not None and mj_end >= mj_start:
                    # CASO 1: Contatore hardware cumulativo funzionante (Kepler+ o AMD bare-metal)
                    delta_j = (mj_end - mj_start) / 1000.0
                    p_rep = delta_j / dt
                else:
                    # CASO 2: Fallback su integrazione discreta della potenza istantanea se il contatore è assente
                    # Legge la potenza istantanea attuale come stima della finestra
                    p_inst, _ = self._gpu.read()
                    if p_inst is not None:
                        p_rep = p_inst
                    else:
                        raise RuntimeError(
                            f"Impossibile leggere i dati energetici della GPU nella ripetizione {rep + 1}/3. "
                            f"Canale: {self._gpu.backend}, Errore contatore: {self._gpu.energy_counter_reason}"
                        )

                gpu_means.append(p_rep)

                if self.on_progress:
                    self.on_progress(
                        f"Ripetizione GPU {rep + 1}/3 completata: P_media = {p_rep:.2f} W"
                    )

            # Calcolo della mediana matematica sulle 3 finestre pulite
            gpu_power_w = sorted(gpu_means)[len(gpu_means) // 2]
            
            # Assegnazione dei metadati di tracciamento interni (esponibili per diagnostica)
            self.gpu_idle_power_w = round(gpu_power_w, 3)
            self._gpu_idle_reps = gpu_means
            
        finally:
            if not was_running:
                self.stop()

        return self.gpu_idle_power_w
