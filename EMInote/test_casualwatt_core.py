# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch
import sys
import psutil

# Importa le strutture dal tuo framework
# Nota: adatta gli import alla struttura effettiva delle tue cartelle
from energy.worker_tree import WorkerProc
from energy.energy_session import SystemSample, EnergySession

# Importiamo le funzioni ottimizzate/nuove create nei passaggi precedenti
# Se le hai già integrate nei moduli nativi, punta direttamente a quelli.
from energy.worker_tree import build_worker_tree


class TestOllamaProcessTree(unittest.TestCase):
    """Test di regressione per la ricostruzione dell'albero dei processi Ollama."""

    def setUp(self):
        self.mock_table = {}

    def _create_mock_process(self, pid, name, ppid, create_time=1000.0):
        """Helper per generare un finto processo psutil."""
        proc = MagicMock(spec=psutil.Process)
        proc.pid = pid
        proc.name.return_value = name
        proc.ppid.return_value = ppid
        proc.create_time.return_value = create_time
        # Simula il context manager oneshot()
        proc.oneshot.return_value.__enter__ = MagicMock()
        proc.oneshot.return_value.__exit__ = MagicMock()
        return proc

    def test_build_tree_standard_and_stray_runners(self):
        """Verifica che l'albero includa sia la catena lineare che i runner orfani (stray)."""
        # 1. Catena regolare: ollama.exe (10) -> ollama.exe (11, child) -> llama-server.exe (12)
        self.mock_table[10] = self._create_mock_process(10, "ollama.exe", 1)
        self.mock_table[11] = self._create_mock_process(11, "ollama.exe", 10)
        self.mock_table[12] = self._create_mock_process(12, "llama-server.exe", 11)

        # 2. Runner orfano (Stray): Senza un padre ollama attivo (ppid inesistente o slegato)
        self.mock_table[99] = self._create_mock_process(99, "ollama_llama_server.exe", 500)

        # 3. Processo estraneo in background che non deve essere considerato
        self.mock_table[200] = self._create_mock_process(200, "chrome.exe", 1)

        root_names = ("ollama.exe", "ollama")
        runner_names = ("llama-server.exe", "ollama_llama_server.exe")

        result = build_worker_tree(self.mock_table, root_names, runner_names)

        # Estraiamo i PID trovati per fare le asserzioni
        found_pids = [w.pid for w in result]

        # Devono essere inclusi l'albero principale e il server orfano
        self.assertIn(10, found_pids)
        self.assertIn(11, found_pids)
        self.assertIn(12, found_pids)
        self.assertIn(99, found_pids)  # Stray runner catturato con successo
        self.assertNotIn(200, found_pids)  # Chrome ignorato correttamente
        self.assertEqual(len(result), 4)

    def test_zombie_and_disappearing_processes(self):
        """Verifica che i processi che muoiono durante lo scan (NoSuchProcess) non rompano il ciclo."""
        proc_live = self._create_mock_process(10, "ollama.exe", 1)
        
        proc_dying = MagicMock(spec=psutil.Process)
        proc_dying.pid = 11
        proc_dying.ppid.side_effect = psutil.NoSuchProcess(11) # Muore appena provi a leggere il padre

        self.mock_table[10] = proc_live
        self.mock_table[11] = proc_dying

        root_names = ("ollama.exe",)
        runner_names = ("llama-server.exe",)

        # Non deve sollevare eccezioni
        try:
            result = build_worker_tree(self.mock_table, root_names, runner_names)
        except Exception as exc:
            self.fail(f"build_worker_tree ha sollevato un'eccezione inaspettata: {exc}")

        found_pids = [w.pid for w in result]
        self.assertIn(10, found_pids)
        self.assertNotIn(11, found_pids)


class TestGPUIdleCalibration(unittest.TestCase):
    """Test di regressione per la funzione di calibrazione idle della GPU."""

    def setUp(self):
        self.session = EnergySession()
        self.session.on_progress = MagicMock() # Silenzia/traccia i log di avanzamento
        self.session._running = True 

    @patch('time.sleep', return_value=None) # Velocizza i test saltando i sleep reali di 30s
    def test_calibrate_gpu_idle_hardware_counter(self, mock_sleep):
        """Verifica la calibrazione via contatore hardware cumulativo (Mediana corretta)."""
        self.session._gpu = MagicMock()
        self.session._gpu.available = True
        
        # Sottofinestra 1: delta = 300.000 mJ (300 J) in 30s -> 10 W
        # Sottofinestra 2: delta = 600.000 mJ (600 J) in 30s -> 20 W
        # Sottofinestra 3: delta = 450.000 mJ (450 J) in 30s -> 15 W
        self.session._gpu.read_energy.side_effect = [
            (1000000.0, None), (1300000.0, None), # Rep 1
            (1300000.0, None), (1900000.0, None), # Rep 2
            (1900000.0, None), (2350000.0, None), # Rep 3
        ]

        # Forziamo un intervallo fisso mockando time.monotonic
        with patch('time.monotonic', side_effect=[0.0, 30.0, 30.0, 60.0, 60.0, 90.0]):
            with patch.dict('os.environ', {'CW_IDLE_WINDOW_S': '30'}):
                idle_w = self.session.calibrate_gpu_idle(seconds=30)

        # Le tre potenze calcolate sono [10.0, 20.0, 15.0] -> Ordinato: [10.0, 15.0, 20.0]
        # La mediana è 15.0 W
        self.assertEqual(idle_w, 15.0)
        self.assertEqual(self.session.gpu_idle_power_w, 15.0)

    @patch('time.sleep', return_value=None)
    def test_calibrate_gpu_idle_fallback_instant_power(self, mock_sleep):
        """Verifica il fallback sulla potenza istantanea se i contatori non sono disponibili."""
        self.session._gpu = MagicMock()
        self.session._gpu.available = True
        self.session._gpu.energy_counter_reason = "Non supportato da questa scheda"
        
        # Il contatore cumulativo risponde sempre (None, None)
        self.session._gpu.read_energy.return_value = (None, None)
        
        # La potenza istantanea campionata restituisce rispettivamente 12W, 14W, 13W
        self.session._gpu.read.side_effect = [
            (12.0, None),
            (14.0, None),
            (13.0, None)
        ]

        with patch('time.monotonic', side_effect=[0.0, 30.0, 30.0, 60.0, 60.0, 90.0]):
            with patch.dict('os.environ', {'CW_IDLE_WINDOW_S': '30'}):
                idle_w = self.session.calibrate_gpu_idle(seconds=30)

        # Mediana di [12.0, 14.0, 13.0] -> 13.0 W
        self.assertEqual(idle_w, 13.0)

    def test_calibrate_gpu_idle_unavailable_raise(self):
        """Verifica che venga lanciato un errore se la GPU non è presente nel sistema."""
        self.session._gpu = MagicMock()
        self.session._gpu.available = False
        self.session._gpu.error = "Driver NVML o AMD SMI non trovato"

        with self.assertRaises(RuntimeError) as context:
            self.session.calibrate_gpu_idle()
            
        self.assertIn("Calibrazione idle GPU fallita", str(context.exception))
        self.assertIn("Driver NVML o AMD SMI non trovato", str(context.exception))


if __name__ == '__main__':
    unittest.main()
