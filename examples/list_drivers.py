"""Esempio: probe dei driver disponibili su questa macchina."""

from cpuepower.sampler import all_drivers, best_driver_for

for d in all_drivers():
    print(d.probe().format())

best = best_driver_for(need_package_energy=True)
print("Miglior driver per energia package:", best.name if best else "nessuno")
