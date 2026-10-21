# -*- coding: utf-8 -*-
"""
tests/test_rapl.py — Test sintetico per il backend RAPL Linux.

Esecuzione:
    python tests/test_rapl.py

Verifica:
  1. Disponibilità del backend RAPL (file energy_uj leggibile)
  2. Lettura energia cumulata
  3. Lettura potenza istantanea
  4. Calibrazione idle (finestra di 2 secondi, non 30s per test rapido)
"""
import sys
import time
from pathlib import Path

# Aggiungi il parent directory al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from energy.rapl_backend import RAPLBackend


def test_rapl_basic():
    """Test base: inizializzazione e letture."""
    print("=" * 70)
    print("TEST 1: Inizializzazione backend RAPL")
    print("=" * 70)

    backend = RAPLBackend()
    print(f"Disponibile: {backend.available}")
    print(f"Metodo: {backend.method}")
    print(f"Note: {backend.notes}")

    if not backend.available:
        print("\n❌ RAPL non disponibile su questo sistema.")
        print("   Possibili cause:")
        print("   - Non sei su Linux")
        print("   - CPU Intel senza supporto RAPL (pre-Sandy Bridge)")
        print("   - Permessi insufficienti (richiede root o gruppo 'power')")
        print("   - Kernel senza CONFIG_INTEL_RAPL")
        return False

    print("\n✓ Backend RAPL inizializzato correttamente")
    return True


def test_rapl_readings():
    """Test letture energetiche."""
    print("\n" + "=" * 70)
    print("TEST 2: Letture energetiche")
    print("=" * 70)

    backend = RAPLBackend()
    if not backend.available:
        print("⚠ Test saltato: RAPL non disponibile")
        return False

    # Lettura energia cumulata
    energy_j = backend.read_cumulative_energy_j()
    print(f"Energia cumulata: {energy_j:.3f} J")

    if energy_j is None:
        print("❌ Lettura energia fallita")
        return False

    # Lettura potenza (richiede due letture)
    power_w = backend.read_power_w()
    print(f"Potenza istantanea (prima lettura): {power_w}")

    time.sleep(0.5)

    power_w = backend.read_power_w()
    print(f"Potenza istantanea (dopo 0.5s): {power_w:.2f} W" if power_w else "Potenza: None")

    # Seconda lettura energia
    time.sleep(0.5)
    energy_j2 = backend.read_cumulative_energy_j()
    print(f"Energia cumulata (dopo 1s totale): {energy_j2:.3f} J")

    delta = energy_j2 - energy_j if energy_j2 and energy_j else 0
    print(f"Delta energia: {delta:.3f} J in ~1s")

    print("\n✓ Letture energetiche funzionanti")
    return True


def test_rapl_idle_window():
    """Test calibrazione idle (finestra breve per test)."""
    print("\n" + "=" * 70)
    print("TEST 3: Calibrazione idle (finestra 2s)")
    print("=" * 70)

    backend = RAPLBackend()
    if not backend.available:
        print("⚠ Test saltato: RAPL non disponibile")
        return False

    print("Misuro energia idle per 2 secondi...")
    result = backend.read_idle_window_j(2.0)

    if result is None:
        print("❌ Misura idle fallita")
        return False

    delta_j, dt_real, mode = result
    power_idle = delta_j / dt_real if dt_real > 0 else 0

    print(f"Delta energia: {delta_j:.3f} J")
    print(f"Durata reale: {dt_real:.3f} s")
    print(f"Potenza media idle: {power_idle:.2f} W")
    print(f"Modalità: {mode}")

    print("\n✓ Calibrazione idle funzionante")
    return True


def test_rapl_diagnostics():
    """Test diagnostica."""
    print("\n" + "=" * 70)
    print("TEST 4: Diagnostica backend")
    print("=" * 70)

    backend = RAPLBackend()
    diag = backend.diagnose()

    print(f"available: {diag['available']}")
    print(f"method: {diag['method']}")
    print(f"path: {diag['path']}")
    print(f"max_energy_uj: {diag['max_energy_uj']}")
    print(f"wrap_count: {diag['wrap_count']}")
    print(f"notes: {diag['notes']}")

    print("\n✓ Diagnostica funzionante")
    return True


def main():
    """Esecuzione completa di tutti i test."""
    print("\n" + "=" * 70)
    print("CASUALWATT - TEST BACKEND RAPL LINUX")
    print("=" * 70)

    results = []

    results.append(("Inizializzazione", test_rapl_basic()))
    results.append(("Letture energetiche", test_rapl_readings()))
    results.append(("Calibrazione idle", test_rapl_idle_window()))
    results.append(("Diagnostica", test_rapl_diagnostics()))

    print("\n" + "=" * 70)
    print("RIEPILOGO TEST")
    print("=" * 70)

    for name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"\nTotale: {passed}/{total} test superati")

    if passed == total:
        print("\n🎉 Tutti i test superati! Backend RAPL funzionante.")
        return 0
    else:
        print("\n⚠ Alcuni test falliti. Verificare la configurazione.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
