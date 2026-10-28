# -*- coding: utf-8 -*-
"""D14 — ``external_counter``: un contatore esterno si esclude con un filtro.

Perche' esiste. La regola "nessun fallback silenzioso" chiede che ogni riga
dichiari il canale che l'ha prodotta, e ``energy_calculation_method`` lo fa
dal 24/10. Ma un'etichetta e' una DESCRIZIONE, non una chiave di selezione:
chi analizza un CSV accumulato deve poter dire "queste righe non vengono da
un contatore della catena" senza confrontare stringhe, e senza che l'aggiunta
di un token nuovo cambi in silenzio l'insieme escluso. ``external_counter``
e' quel booleano.

Che cosa e' esterno. ``energy-file`` soltanto: ``CW_ENERGY_FILE`` e' un
override di selezione fornito dall'utente (``energy/energy_session.py:139``,
ramo ``_try_power_counter``), un canale DEV/TEST che ferma la cascata prima
di EMI e PawnIO. Tutti gli altri canali locali leggono il proprio numero
dentro il framework -- EMI e PawnIO dal contatore del package, RAPL dal
sysfs, NVML e AMD SMI dal device -- e dichiarano ``False``. Anche i token GPU
(``nvml-energy``, ``nvml-power-integral``, ``amdsmi-*``) restano interni: la
riga non diventa "esterna" perche' il numero viene dalla scheda.

Che cosa NON verifica: il valore dell'energia. Qui si controlla solo che il
booleano arrivi nella riga con il segno giusto, per cinque canali.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from energy import energy_session as es  # noqa: E402
from energy.energy_session import (  # noqa: E402
    EXTERNAL_COUNTER_METHODS, MEASURED_METHODS, SystemSample,
    is_external_counter,
)
from energy.local_energy import CasualWattLocalEnergyProfiler  # noqa: E402

T0 = 1000.0


class _Sessione:
    """Sessione minima: dichiara il canale e fornisce campioni senza contatore esatto.

    ``gpu`` abilita il ramo GPU con gli attributi che il profiler legge
    (``available``, ``index``, ``backend``, ``energy_counter``); i campioni
    portano ``gpu_energy_mj`` crescente, cosi' la catena NVML produce davvero
    un token ``nvml-energy``.
    """

    def __init__(self, method, gpu=None, n_samples=3):
        self.source_method = method
        self.interval_s = 0.5
        self.idle_power_w = 10.0
        self.idle_provenance = "calibrated"
        self.idle_gpu_power_w = 20.0 if gpu is not None else None
        self._gpu = gpu or SimpleNamespace(available=False, index=0, name="")
        self.samples = [
            SystemSample(
                t=T0 + i * 0.5, wall=0.0, package_energy_j=10.0 * i,
                cpu_busy_seconds=1.0 * i, cpu_percent=0.0,
                ollama_pids=(7,), ollama_cpu_seconds=0.5 * i,
                gpu_power_w=(100.0 if gpu is not None else None),
                gpu_util_pct=(50.0 if gpu is not None else None),
                gpu_energy_mj=(2000.0 * i if gpu is not None else None))
            for i in range(n_samples)
        ]

    def samples_between(self, a, b):
        return [s for s in self.samples if a <= s.t <= b]


def _profile(method, gpu=None):
    prof = CasualWattLocalEnergyProfiler()
    prof.session = _Sessione(method, gpu=gpu)
    return prof.profile_window(T0, T0 + 1.0, ollama_pids=[7])


# ------------------------------------------------------------------ 1
def test_energy_file_e_l_unico_canale_esterno(tmp_path, monkeypatch):
    """CW_ENERGY_FILE valido ferma la cascata e la riga dichiara il contatore esterno.

    Il file non e' un anello della catena: e' l'utente che fornisce il numero.
    La selezione viene costruita davvero (platform Windows simulata, nessun
    tentativo EMI) e la riga del profiler deve riportare lo stesso token con
    ``external_counter=True``.
    """
    path = tmp_path / "energy.joule"
    path.write_text("123.45", encoding="utf-8")
    monkeypatch.setenv("CW_ENERGY_FILE", str(path))
    monkeypatch.setattr(es, "platform_system", lambda: "Windows")

    src = es._CPUJouleSource()
    assert src.method == "energy-file"

    res = _profile(src.method)
    assert res.energy_calculation_method == "energy-file"
    assert res.external_counter is True


# ------------------------------------------------------------------ 2
def test_emi_counter_non_e_un_contatore_esterno():
    """Il contatore EMI e' il canale principale: la riga dichiara False."""
    res = _profile("emi-counter")
    assert res.external_counter is False


# ------------------------------------------------------------------ 3
def test_pawnio_counter_non_e_un_contatore_esterno():
    """PawnIO legge lo stesso registro di EMI dentro il framework: False."""
    res = _profile("pawnio-counter")
    assert res.external_counter is False


# ------------------------------------------------------------------ 4
def test_rapl_non_e_un_contatore_esterno():
    """RAPL legge i contatori di piattaforma via sysfs: canale interno, False."""
    res = _profile("rapl")
    assert res.external_counter is False


# ------------------------------------------------------------------ 5
def test_la_catena_nvml_non_rende_esterna_la_riga():
    """Una riga con GPU da ``nvml-energy`` resta interna.

    ``external_counter`` descrive il contatore che ha prodotto l'energia della
    riga, e la catena NVML e' interna al framework. Se il booleano seguisse
    qualunque token non-EMI, questa riga risulterebbe esterna e verrebbe
    esclusa da un filtro che voleva togliere solo ``energy-file``.
    """
    gpu = SimpleNamespace(available=True, index=0, name="FakeGPU",
                          backend="nvml", energy_counter=True,
                          power_field="", power_unit="",
                          platform_context="")
    res = _profile("emi-counter", gpu=gpu)
    assert res.gpu_attribution_method.startswith("nvml-energy")
    assert res.energy_calculation_method == "emi-counter"
    assert res.external_counter is False


# ------------------------------------------------------- invariante di lista
def test_solo_energy_file_e_esterno_fra_i_canali_misurati():
    """L'insieme esterno e' esattamente ``{energy-file}`` dentro MEASURED_METHODS.

    Se domani un token nuovo entrasse in ``MEASURED_METHODS`` senza una
    decisione esplicita, questo test non lo classificherebbe di nascosto come
    interno: la lista esterna e' dichiarata, non derivata.
    """
    esterni = {m for m in MEASURED_METHODS if is_external_counter(m)}
    assert esterni == {"energy-file"}
    assert EXTERNAL_COUNTER_METHODS == ("energy-file",)
    # i token GPU non sono in MEASURED_METHODS (sono canali della scheda, non
    # del package) ma il predicato deve rispondere False anche su di loro
    for gpu_token in ("nvml-energy", "nvml-power-integral",
                      "amdsmi-energy", "amdsmi-power-integral"):
        assert is_external_counter(gpu_token) is False
