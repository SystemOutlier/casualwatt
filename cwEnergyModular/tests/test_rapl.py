# -*- coding: utf-8 -*-
"""
tests/test_rapl.py — Test del backend RAPL Linux (contatori ``energy_uj``).

Esecuzione (dalla cartella cwEnergyModular/):
    python -m pytest tests/test_rapl.py -v
    python tests/test_rapl.py

Che cosa verifica, quando il contatore c'e':
  1. inizializzazione del backend su un file energy_uj leggibile;
  2. lettura dell'energia cumulata e sua non decrescita (il riporto del
     contatore lo gestisce il backend, non il test);
  3. finestra di riposo da contatore: delta, durata reale e potenza media
     coerenti (2 s, non la procedura ufficiale da 30 s x 3);
  4. registro di diagnostica: chiavi e tipi attesi. Vale su OGNI piattaforma,
     percio' non e' condizionato alla disponibilita' del contatore.

Forma dei test -- riscritta il 23/10/2026. La versione precedente usciva con
``return False`` prima di qualunque asserzione quando RAPL non era disponibile,
e ``test_rapl_diagnostics`` restituiva ``True`` senza controllare nulla: pytest
contava quattro test "passati" su Windows che non avevano eseguito nessuna
asserzione (con PytestReturnNotNoneWarning). Ora la non disponibilita' e' uno
SKIP DICHIARATO: un verde che non asserisce e' una cifra sbagliata nel verbale,
ed e' il difetto che la tesi denuncia negli strumenti che stampano un numero
senza confine.
"""
import sys
import time
from pathlib import Path

# Aggiungi il parent directory al path (il file deve girare anche da script)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402  (importato dopo sys.path, serve allo skip dichiarato)

from energy.rapl_backend import RAPLBackend  # noqa: E402


def _backend_or_skip() -> RAPLBackend:
    """Backend RAPL pronto all'uso, o skip con il motivo scritto nel verbale."""
    backend = RAPLBackend()
    if not backend.available:
        pytest.skip(
            "RAPL non disponibile su questo host: servono Linux, una zona "
            "package con energy_uj leggibile e permessi di lettura sul nodo "
            "(root o permessi concessi esplicitamente)"
        )
    return backend


def test_rapl_basic():
    """Test 1: il backend si inizializza su un contatore leggibile."""
    print("=" * 70)
    print("TEST 1: Inizializzazione backend RAPL")
    print("=" * 70)

    backend = _backend_or_skip()
    print(f"Metodo: {backend.method}")
    print(f"Note: {backend.notes}")

    assert backend.available is True
    assert backend.method, "method vuoto su backend dichiarato disponibile"
    e0 = backend.read_cumulative_energy_j()
    assert e0 is not None, "prima lettura del contatore fallita"
    assert e0 >= 0.0, f"energia cumulata negativa alla prima lettura: {e0}"
    print(f"Prima lettura: {e0:.3f} J")


def test_rapl_readings():
    """Test 2: energia cumulata letta, non negativa e non decrescente."""
    print("\n" + "=" * 70)
    print("TEST 2: Letture energetiche")
    print("=" * 70)

    backend = _backend_or_skip()

    e1 = backend.read_cumulative_energy_j()
    assert e1 is not None, "lettura dell'energia cumulata fallita"
    assert e1 >= 0.0, f"energia cumulata negativa: {e1}"
    print(f"Energia cumulata: {e1:.3f} J")

    time.sleep(0.5)
    p = backend.read_power_w()
    assert p is None or p >= 0.0, f"potenza istantanea negativa: {p}"
    print(f"Potenza istantanea: {p:.2f} W" if p is not None else "Potenza: None")

    time.sleep(0.5)
    e2 = backend.read_cumulative_energy_j()
    assert e2 is not None, "seconda lettura dell'energia cumulata fallita"
    delta = e2 - e1
    assert delta >= 0.0, (
        f"contatore decresciuto di {-delta:.3f} J senza riporto dichiarato: "
        "la gestione del wrap e' del backend (energy/rapl_backend.py)"
    )
    print(f"Delta energia in ~1 s: {delta:.3f} J")


def test_rapl_idle_window():
    """Test 3: finestra di riposo misurata sul contatore."""
    print("\n" + "=" * 70)
    print("TEST 3: Finestra idle da contatore (2 s)")
    print("=" * 70)

    backend = _backend_or_skip()
    result = backend.read_idle_window_j(2.0)
    assert result is not None, "misura della finestra idle fallita"

    delta_j, dt_real, mode = result
    assert mode == "rapl-counter", f"modalita' di misura inattesa: {mode}"
    assert delta_j >= 0.0, f"delta energia negativo: {delta_j}"
    assert dt_real > 0.0, f"durata reale non positiva: {dt_real}"

    power_idle = delta_j / dt_real
    assert 0.0 <= power_idle < 500.0, (
        f"potenza media idle fuori scala ({power_idle:.2f} W): plausibile per un "
        "package, impossibile come artefatto di unita' di misura"
    )
    print(f"Delta {delta_j:.3f} J in {dt_real:.3f} s -> {power_idle:.2f} W "
          f"[{mode}]")


def test_rapl_diagnostics():
    """Test 4: forma del registro di diagnostica (segue anche senza RAPL)."""
    print("\n" + "=" * 70)
    print("TEST 4: Diagnostica backend")
    print("=" * 70)

    diag = RAPLBackend().diagnose()
    for chiave in ("available", "method", "path", "max_energy_uj",
                   "wrap_count", "zones", "notes"):
        print(f"{chiave}: {diag[chiave]}")

    assert set(diag) == {"available", "method", "path", "max_energy_uj",
                         "wrap_count", "zones", "notes"}, (
        f"chiavi inattese: {sorted(diag)}")
    assert isinstance(diag["available"], bool)
    assert isinstance(diag["notes"], list), "notes deve essere una lista"
    assert isinstance(diag["path"], str) and diag["path"], "path vuoto"
    assert isinstance(diag["wrap_count"], int) and diag["wrap_count"] >= 0
    assert isinstance(diag["zones"], list), "zones deve essere una lista"
    for zona in diag["zones"]:
        assert isinstance(zona, dict) and zona.get("name"), (
            f"zona senza nome: {zona}")
    if diag["available"]:
        assert diag["method"] == "rapl", (
            f"backend disponibile ma metodo inatteso: '{diag['method']}'"
        )
        assert diag["zones"], "backend disponibile senza zone selezionate"
    else:
        assert diag["method"] == "unavailable", (
            f"metodo '{diag['method']}' dichiarato su backend non disponibile"
        )
        assert diag["notes"], "backend non disponibile senza il motivo in notes"


def main() -> int:
    """Esecuzione da script: rende leggibile anche lo skip dichiarato."""
    print("\n" + "=" * 70)
    print("CASUALWATT - TEST BACKEND RAPL LINUX")
    print("=" * 70)

    tests = (
        ("Inizializzazione", test_rapl_basic),
        ("Letture energetiche", test_rapl_readings),
        ("Finestra idle da contatore", test_rapl_idle_window),
        ("Diagnostica", test_rapl_diagnostics),
    )

    esiti = []
    for nome, fn in tests:
        try:
            fn()
            esiti.append((nome, "PASS", ""))
        except pytest.skip.Exception as exc:  # skip dichiarato, non un verde
            esiti.append((nome, "SKIP", str(exc)))
        except AssertionError as exc:
            esiti.append((nome, "FAIL", str(exc)))

    print("\n" + "=" * 70)
    print("RIEPILOGO TEST")
    print("=" * 70)
    for nome, stato, motivo in esiti:
        print(f"{stato}: {nome}" + (f" -- {motivo}" if motivo else ""))

    n_pass = sum(1 for _, s, _ in esiti if s == "PASS")
    n_skip = sum(1 for _, s, _ in esiti if s == "SKIP")
    n_fail = sum(1 for _, s, _ in esiti if s == "FAIL")
    # la sola diagnostica non valida nessuna misura: conta a parte
    n_misure = sum(1 for n, s, _ in esiti if s == "PASS" and n != "Diagnostica")
    print(f"\nTotali {len(esiti)}: {n_pass} passati, {n_skip} saltati "
          f"(backend non disponibile), {n_fail} falliti")

    if n_fail:
        print("\nALCUNI TEST FALLITI: backend RAPL non affidabile su questa "
              "piattaforma.")
        return 1
    if n_misure == 0:
        print("\nNESSUN TEST DI MISURA ESEGUITO: questo host non espone RAPL. "
              "Il backend Linux NON e' validato qui.")
        return 2
    print("\nBackend RAPL validato sul contatore.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
