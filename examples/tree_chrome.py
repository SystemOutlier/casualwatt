"""Esempio: isola il consumo dell'albero di un software dato il nome exe (es. chrome.exe).

Uso::

    python examples/tree_chrome.py chrome.exe [window_s]

Mostra, per ogni root trovato, la stima di energia/potenza attribuibile all'albero
completo (root + discendenti), con breakdown per PID in verbose.
"""

import sys
import time

from cpuepower.attribution import AttributionMethod, TreeEnergyEstimator
from cpuepower.process_tree import measure_window, tree_for_exe
from cpuepower.sampler import best_driver_for
from cpuepower.types import PackageEnergy, ReadingSource


def main() -> None:
    exe = sys.argv[1] if len(sys.argv) > 1 else "chrome.exe"
    window = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    trees = tree_for_exe(exe)
    if not trees:
        print(f"Nessun processo {exe!r} in esecuzione")
        sys.exit(1)

    drv = best_driver_for(True)
    estimator = TreeEnergyEstimator(drv)

    for tree in trees:
        a = drv.read_package()
        delta = measure_window(tree, window_s=window)
        b = drv.read_package()
        res = estimator.estimate(delta, a, b, method=AttributionMethod.AUTO)
        print(f"\n--- albero pid {tree.root_pid} ({exe}) ---")
        print(tree.describe())
        print(f"metodo={res.method} confidenza={res.confidence}")
        print(f"cpu_fraction={res.cpu_fraction:.3f} "
              f"potenza={res.power_w if res.power_w is None else round(res.power_w,2)} W "
              f"energia={res.energy_mj if res.energy_mj is None else round(res.energy_mj,1)} mJ")
        for n in res.notes:
            print(" note:", n)


if __name__ == "__main__":
    main()
