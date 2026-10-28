# -*- coding: utf-8 -*-
"""
tests/test_rapl_zone.py — Selezione delle zone RAPL su un filesystem finto.

Perche' esiste: il backend Linux era cablato su ``intel-rapl:0``
(``energy/rapl_backend.py`` fino al 27/10/2026), quindi su una macchina con
piu' package leggeva un solo package, e su AMD — dove il nome della zona e il
numero di contatori dipendono dal driver — non era verificabile. La forma
corretta e' quella del documento di specifica (§3.1, voce R1): enumerare le
zone, leggere ``name``, tenere solo ``package-*``, contare una volta sola i
canali specchiati. Questi test verificano la LOGICA DI SELEZIONE e il RIPORTO
sul filesystem, senza hardware RAPL: gli stessi file che il kernel espone
(``energy_uj``, ``max_energy_range_uj``, ``name``) costruiti in ``tmp_path``.

Che cosa NON verificano: che il contatore reale abbia quei valori, ne' la
scala assoluta. Quello resta il compito dei tre test di ``test_rapl.py`` su un
host Linux, che qui non esiste.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from energy.rapl_backend import RAPLBackend  # noqa: E402


def _zone(root: Path, dirname: str, name: str, energy_uj: int,
          max_uj=None) -> Path:
    """Crea una zona finta. Il dominio lo dichiara il file ``name``, non la
    directory: il nome della directory usa un trattino perche' ':' non e'
    valido nei nomi di file su Windows, dove questi test girano."""
    d = root / dirname
    d.mkdir(parents=True)
    (d / "energy_uj").write_text(str(energy_uj))
    (d / "name").write_text(name)
    if max_uj is not None:
        (d / "max_energy_range_uj").write_text(str(max_uj))
    return d


def _write_uj(zone_dir: Path, value: int) -> None:
    (zone_dir / "energy_uj").write_text(str(value))


def test_seleziona_solo_le_zone_package(tmp_path):
    """Una zona psys e' un dominio diverso: non entra nel totale del package."""
    _zone(tmp_path, "intel-rapl-0", "package-0", 1_000, max_uj=2**32)
    _zone(tmp_path, "intel-rapl-1", "psys", 5_000, max_uj=2**32)

    b = RAPLBackend(root=tmp_path)
    assert b.available is True
    assert b.method == "rapl"
    assert [z["name"] for z in b.diagnose()["zones"]] == ["package-0"]
    assert "psys" in b.notes[-1] or any("psys" in n for n in b.notes)


def test_due_package_distinti_si_sommano(tmp_path):
    """Due socket sono due contatori: l'energia del package e' la loro somma."""
    z0 = _zone(tmp_path, "intel-rapl-0", "package-0", 1_000, max_uj=2**32)
    z1 = _zone(tmp_path, "intel-rapl-1", "package-1", 2_000, max_uj=2**32)

    b = RAPLBackend(root=tmp_path)
    assert b.read_cumulative_energy_j() == 0.0

    _write_uj(z0, 1_500)   # +500 uJ
    _write_uj(z1, 2_300)   # +300 uJ
    assert abs(b.read_cumulative_energy_j() - 800e-6) < 1e-12


def test_canali_specchiati_contati_una_volta(tmp_path):
    """Due zone con lo stesso nome sono lo stesso contatore: nessuna somma."""
    _zone(tmp_path, "intel-rapl-0", "package-0", 1_000, max_uj=2**32)
    _zone(tmp_path, "intel-rapl-0-dup", "package-0", 1_000, max_uj=2**32)

    b = RAPLBackend(root=tmp_path)
    assert len(b.diagnose()["zones"]) == 1
    assert any("specchiato" in n for n in b.notes)
    assert b.read_cumulative_energy_j() == 0.0


def test_riporto_del_contatore_ricostruito(tmp_path):
    """Con max_energy_range_uj noto il riporto e' aritmetico, non un'assunzione."""
    z = _zone(tmp_path, "intel-rapl-0", "package-0", 900, max_uj=1_000)

    b = RAPLBackend(root=tmp_path)
    assert b.read_cumulative_energy_j() == 0.0

    _write_uj(z, 950)
    assert abs(b.read_cumulative_energy_j() - 50e-6) < 1e-12

    _write_uj(z, 100)      # riporto: 1000 - 950 + 100 = 150 uJ in piu'
    assert abs(b.read_cumulative_energy_j() - 200e-6) < 1e-12
    assert b.diagnose()["wrap_count"] == 1


def test_riporto_senza_massimo_non_si_inventa(tmp_path):
    """Senza max_energy_range_uj il riporto non e' determinabile: None, non 2**32."""
    z = _zone(tmp_path, "intel-rapl-0", "package-0", 900)

    b = RAPLBackend(root=tmp_path)
    _write_uj(z, 100)
    assert b.read_cumulative_energy_j() is None
    assert any("riporto non determinabile" in n for n in b.notes)


def test_radice_assente_backend_indisponibile(tmp_path):
    """Senza powercap il metodo e' 'unavailable' con la ragione scritta."""
    b = RAPLBackend(root=tmp_path / "non-esiste")
    diag = b.diagnose()
    assert b.available is False
    assert diag["method"] == "unavailable"
    assert diag["zones"] == []
    assert diag["notes"]


def test_solo_psys_non_e_un_package(tmp_path):
    """Una macchina con solo psys non ha un contatore di package da leggere."""
    _zone(tmp_path, "intel-rapl-0", "psys", 5_000, max_uj=2**32)

    b = RAPLBackend(root=tmp_path)
    assert b.available is False
    assert any("senza zona package" in n for n in b.notes)


def test_potenza_somma_le_zone(tmp_path):
    """La potenza istantanea e' la somma dei contributi delle zone distinte."""
    z0 = _zone(tmp_path, "intel-rapl-0", "package-0", 0, max_uj=2**32)
    z1 = _zone(tmp_path, "intel-rapl-1", "package-1", 0, max_uj=2**32)

    b = RAPLBackend(root=tmp_path)
    _write_uj(z0, 1_000_000)   # 1 J
    _write_uj(z1, 2_000_000)   # 2 J
    p = b.read_power_w()
    assert p is not None and p > 0.0
    # 3 J su una finestra brevissima: la potenza e' grande ma finita
    assert p < 1e9
