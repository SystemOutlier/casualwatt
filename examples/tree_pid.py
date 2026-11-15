"""Esempio: isola il consumo di un albero dato il PID del processo radice.

Uso::

    python examples/tree_pid.py 12345 [window_s] [metodo]

metodo ∈ {auto, apodictic, heuristic, tdp_estimate}
"""

import sys

from cpuepower.attribution import AttributionMethod, TreeEnergyEstimator
from cpuepower.process_tree import ProcessTree, measure_window
from cpuepower.sampler import best_driver_for


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    pid = int(sys.argv[1])
    window = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    method = AttributionMethod(sys.argv[3]) if len(sys.argv) > 3 else AttributionMethod.AUTO

    tree = ProcessTree(pid)
    if not tree.nodes:
        print(f"PID {pid} inesistente o inaccessibile")
        sys.exit(1)

    drv = best_driver_for(True)
    estimator = TreeEnergyEstimator(drv)

    a = drv.read_package()
    delta = measure_window(tree, window_s=window)
    b = drv.read_package()
    res = estimator.estimate(delta, a, b, method=method)

    print("Albero:")
    print(tree.describe())
    print(f"\nmetodo={res.method} sorgente={res.source.value} confidenza={res.confidence}")
    print(f"finestra={res.window_s:.2f}s processi={delta.n_processes_in_tree} "
          f"cpu_tree={delta.total_cpu_s:.3f}s cpu_sys={delta.system_total_cpu_s:.3f}s")
    if res.power_w is not None:
        print(f"potenza albero ≈ {res.power_w:.2f} W")
    if res.energy_mj is not None:
        print(f"energia albero ≈ {res.energy_mj:.1f} mJ")
    if res.package_power_w is not None:
        print(f"(package totale nel periodo: {res.package_power_w:.2f} W)")
    for n in res.notes:
        print("note:", n)
    if res.per_pid_energy_mj:
        print("breakdown per PID (mJ):")
        for p, mj in sorted(res.per_pid_energy_mj.items(), key=lambda kv: -kv[1]):
            print(f"  {p}: {mj:.2f}")


if __name__ == "__main__":
    main()
