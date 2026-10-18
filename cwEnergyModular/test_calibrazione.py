# -*- coding: utf-8 -*-
"""
test_calibrazione.py — Test RAPIDO della sola calibrazione idle, da console.

Scopo: isolare il percorso LHM -> sensore 'CPU Package' -> power-integration
-> P_idle senza aprire la GUI e senza attendere le 3 finestre piene da 30 s
della procedura ufficiale (spec §5). E' uno strumento di collaudo: i valori
che produce NON sono calibrazioni valide da usare in benchmark (finestre
corte, una sola ripetizione); per il dato ufficiale usa sempre il pulsante
"Calibra idle" nella GUI o SESSION.calibrate_idle().

Uso su Windows 11 (amministratore, dalla cartella cwEnergyModular):

    py test_calibrazione.py                # finestra breve 4 s x 1 rep
    py test_calibrazione.py --finestra 10  # finestra 10 s
    py test_calibrazione.py --rep 3        # 3 ripetizioni (mediana)
    py test_calibrazione.py --completa     # procedura UFFICIALE (30 s x 3)

Il flag CW_IDLE_WINDOW_S viene impostato automaticamente per consentire
finestre piu' corte del floor di 30 s previsto dalla specifica.
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Test rapido calibrazione idle CasualWatt")
    ap.add_argument("--finestra", type=float, default=4.0,
                    help="durata di ogni finestra idle in secondi (default 4)")
    ap.add_argument("--rep", type=int, default=1,
                    help="numero di ripetizioni (default 1; la procedura "
                         "ufficiale ne usa 3 con mediana)")
    ap.add_argument("--completa", action="store_true",
                    help="esegue la procedura UFFICIALE completa (>=30 s x 3)")
    args = ap.parse_args()

    if args.completa:
        os.environ.pop("CW_IDLE_WINDOW_S", None)
    else:
        # abbatte il floor di 30 s della spec solo per questo collaudo
        os.environ["CW_IDLE_WINDOW_S"] = str(max(1.0, min(args.finestra, 29.0)))

    window = max(args.finestra, float(os.environ.get("CW_IDLE_WINDOW_S", "30"))) \
        if not args.completa else 30.0
    reps = 3 if args.completa else max(1, args.rep)

    log(f"=== TEST CALIBRAZIONE IDLE ({'COMPLETA/ufficiale' if args.completa else 'RAPIDA'}) ===")
    log(f"Finestra: {window:.0f} s | Ripetizioni: {reps} | "
        f"Durata prevista misura: ~{window * reps + 5:.0f} s (+ apertura LHM)")
    log("NON generare carico sul PC durante la misura.")

    t_total0 = time.monotonic()

    log("Import del motore (con probe LHM lazy: niente Computer() ancora)…")
    try:
        from energy.energy_session import SESSION
    except Exception as exc:  # noqa: BLE001
        log(f"[FALLITO] import motore: {type(exc).__name__}: {exc}")
        return 1
    log(f"Backend al momento dell'import: method='{SESSION.source_method}' "
        f"(atteso: 'unavailable' con nota lazy — nessuna apertura bloccante)")

    def progress(msg: str) -> None:
        log(f"    > {msg}")

    SESSION.on_progress = progress

    log("Avvio sessione (QUI avviene il probe LHM pigro: Computer().Open(), "
        "puo' richiedere fino a ~2 minuti)…")
    t0 = time.monotonic()
    try:
        SESSION.start()
    except Exception as exc:  # noqa: BLE001
        log(f"[FALLITO] start(): {type(exc).__name__}: {exc}")
        for n in SESSION.source_notes:
            log(f"    nota: {n}")
        return 1
    log(f"Sessione avviata in {time.monotonic() - t0:.1f} s | "
        f"metodo attivo: '{SESSION.source_method}'")
    for n in SESSION.source_notes[-6:]:
        log(f"    nota: {n}")

    if SESSION.source_method not in ("power-integration",
                                     "librehardwaremonitor-energy"):
        log("[FALLITO] nessun backend energetico reale attivo dopo start().")
        log("Prossimo passo: 'py diagnostics.py' come amministratore e "
            "inviare l'output completo.")
        SESSION.stop()
        return 2

    # lettura istantanea di potenza (solo power-integration)
    try:
        if SESSION.source_method == "power-integration":
            time.sleep(1.0)  # lascia popolare qualche campione al thread PI
            stats = SESSION._source.pi_stats()
            log(f"power-integration attiva: {stats.get('samples', 0)} campioni, "
                f"W attuale ≈ {stats.get('last_w')}")
    except Exception as exc:  # noqa: BLE001
        log(f"(lettura istantanea non disponibile: {type(exc).__name__})")

    log(f"Calibrazione: {reps} finestra/e da {window:.0f} s…")
    t0 = time.monotonic()
    try:
        pw = SESSION.calibrate_idle(seconds=window)
    except Exception as exc:  # noqa: BLE001
        log(f"[FALLITO] calibrazione: {type(exc).__name__}: {exc}")
        for n in SESSION.source_notes[-8:]:
            log(f"    nota: {n}")
        SESSION.stop()
        return 3
    dt = time.monotonic() - t0

    reps_vals = getattr(SESSION, "_idle_reps", []) or []
    samples = getattr(SESSION, "_idle_samples_count", 0)
    log(f"[OK] P_idle = {pw:.2f} W  "
        f"(ripetizioni: {', '.join(f'{r:.2f} W' for r in reps_vals)})")
    log(f"     provenance={SESSION.idle_provenance} | metodo={SESSION.source_method} | "
        f"campioni PI={samples} | durata misura={dt:.1f}s | totale script={time.monotonic() - t_total0:.1f}s")
    if not args.completa:
        log("NB: test rapido — per il benchmark riesci con 'Calibra idle' in GUI "
            "(finestre >=30 s x 3, mediana).")

    SESSION.stop()
    SESSION.close()   # chiude LHM/NVML una sola volta (spec §6)
    log("Chiusura pulita completata.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
