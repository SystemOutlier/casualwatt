"""Esempio: monitoraggio in continuo della potenza package.

Premere Ctrl-C per uscire. Il driver migliore viene scelto automaticamente;
forzarlo con ``python monitor_package.py pdh`` ad esempio.
"""

import sys
import time

from cpuepower.sampler import EnergySampler, all_drivers, best_driver_for


def main() -> None:
    drv = None
    if len(sys.argv) > 1:
        drv = next((d for d in all_drivers() if d.name == sys.argv[1]), None)
        if drv is None:
            print("driver sconosciuto:", sys.argv[1])
            sys.exit(2)
    else:
        drv = best_driver_for(True)
    if drv is None:
        print("nessun driver disponibile")
        sys.exit(1)
    print(f"Driver: {drv.name}")

    def cb(cur, prev):
        if not cur.available:
            print("non disponibile:", cur.note)
            return
        if prev and prev.available and cur.timestamp > prev.timestamp:
            dt = cur.timestamp - prev.timestamp
            w = max(0.0, (cur.energy_mj or 0) - (prev.energy_mj or 0)) / 1000.0 / dt
            print(f"{w:8.2f} W   cumulato={cur.energy_mj/1000:.1f} J   [{cur.note}]")
        else:
            print(f"baseline cumulato={cur.energy_mj/1000:.1f} J   [{cur.note}]")

    sampler = EnergySampler(drv, interval_s=1.0, on_sample=cb)
    sampler.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        sampler.stop()


if __name__ == "__main__":
    main()
