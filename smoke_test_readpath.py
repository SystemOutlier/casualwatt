#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke_test_readpath.py
======================
Prova veloce (20 s) che il percorso di lettura corretto di
`energy_session._CPUJouleSource._read_power_w_direct()` legga il sensore
POWER e non l'omonimo TEMPERATURE.

Perche' esiste: il fix 1422d1b cambia il backend di produzione, e prima di
rilanciare i protocolli v1/v2/v3 (25-30 min l'uno) conviene spendere 20 s per
accorgersi se la scala e' quella giusta. A idle su MINI_IT13 il package reale
vale ~12-16 W (EMI, SRUM, HWiNFO e i limiti PL1 35/PL2 55); il sensore di
temperatura vale ~60-70 "unita'". Un numero >40 a idle = il fix non ha effetto.

Requisiti: processo ELEVATO (i sensori Power LHM sono invisibili senza Admin),
LHM chiuso altrove (un solo Computer() aperto alla volta).

Uso:
  C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe \
      smoke_test_readpath.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "cwEnergyModular"))

from energy.energy_session import SESSION  # noqa: E402

N_TIZZI = 20


def main() -> int:
    SESSION.start()
    src = SESSION._source
    sel = getattr(src, "_pi_selected", None)
    print(f"metodo            : {getattr(src, '_pi_method', None)}")
    print(f"sensore dichiarato: {getattr(src, '_pi_sensor_name', None)!r}")
    print(f"oggetto scelto    : nome={getattr(sel, 'Name', None)!r} "
          f"tipo={getattr(sel, 'SensorType', None)}")
    print(f"attesa {N_TIZZI} s per il primo campione del thread PI...")
    time.sleep(N_TIZZI)
    lettura = src._read_power_w_direct()
    print(f"_read_power_w_direct() = {lettura}")
    if lettura is None:
        print("VERDETTO: niente lettura — il fix non puo' essere validato (LHM/Elevazione?)")
        verdict = 1
    else:
        ok = 5.0 < lettura < 40.0
        print("VERDETTO: " + ("LETTRA IL SENSORE POWER (scala giusta)"
                             if ok else
                             "SCALA SBAGLIATA — fuori dall'involucro idle atteso (5-40 W)"))
        verdict = 0 if ok else 1
    # Il teardown pythonnet su questa macchina lancia un'eccezione CLR nota
    # (exit 127): il verdetto e' gia' stampato, quindi non va perso per questo.
    try:
        SESSION.stop()
    except Exception as e:
        print(f"teardown (nota, non conta): {type(e).__name__}")
    return verdict


if __name__ == "__main__":
    sys.exit(main())
