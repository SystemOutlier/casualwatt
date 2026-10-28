# -*- coding: utf-8 -*-
"""
tests/test_measurement_edge.py — Il bordo di misura, senza hardware.

Perche' esiste. La v4 legge l'energia ai due estremi della richiesta invece
di interpolare il buffer: contatore prima, poi albero/cpu_times/busy. Se quel
bordo non dichiara cosa ha letto e con quale scarto, la riga sembra sincrona
per costruzione. Qui il backend EMI e' finto: il test verifica il CONTRATTO
del bordo, non il registro.

Che cosa verifica:
  1. ``read_counter_edge`` porta le chiavi del contatore (pkg_j, pWh,
     ts_100ns, pp1_j), l'istante UTC e ``counter_error`` vuoto;
  2. un backend assente o che risponde None NON solleva: il bordo degrada e
     dichiara la ragione in ``counter_error``;
  3. un backend che solleva viene catturato e la ragione resta nel bordo;
  4. ``read_measurement_edge`` porta tutte le chiavi del contratto (albero,
     worker, busy, contatore, istanti, spread) e l'istante del contatore e'
   preso prima delle letture CPU (``t_counter_mono <= t_cpu_mid``);
  5. ``read_cpu_edge`` resta l'alias storico a TRE chiavi e non fa la IOCTL
     in piu' (compatibilita' del percorso di produzione, D5).

Che cosa NON verifica: che il contatore EMI legga il registro giusto (e'
il test del backend, con l'hardware) ne' la precisione degli istanti.
"""
import re
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import energy.energy_session as es  # noqa: E402
from energy.energy_session import EnergySession  # noqa: E402


class _FakeEmi:
    """Backend EMI minimo: ``read_domains`` con la forma del backend reale."""

    def __init__(self, payload=None, raises=None):
        self._payload = payload
        self._raises = raises

    def read_domains(self):
        if self._raises is not None:
            raise self._raises
        return self._payload


def _session(emi) -> EnergySession:
    """Sessione reale con la sola sorgente sostituita (nessun hardware)."""
    s = EnergySession()
    s._source = SimpleNamespace(_emi=emi, method="emi-counter")
    return s


def _pkg(j, ts, pwh=1000.0):
    return (j, ts, pwh)


# ------------------------------------------------------------------ 1
def test_counter_edge_legge_i_campi_del_contatore():
    """pkg_j, pWh grezzi, timestamp 100 ns e PP1 arrivano nel bordo, con l'UTC."""
    s = _session(_FakeEmi({"pkg": _pkg(12.5, 123456789, 3472.2),
                           "pp1": _pkg(0.4, 123456000, 111.1)}))
    edge = s.read_counter_edge()

    assert edge["counter_error"] == ""
    cnt = edge["counter"]
    assert cnt["pkg_j"] == pytest.approx(12.5)
    assert cnt["pkg_pwh"] == pytest.approx(3472.2)
    assert cnt["ts_100ns"] == 123456789
    assert cnt["pp1_j"] == pytest.approx(0.4)
    # l'istante UTC e' ricostruibile e ha i millisecondi
    parsed = datetime.fromisoformat(edge["t_wall_utc"])
    assert parsed.tzinfo is not None
    assert re.search(r"\.\d{3}\+00:00$", edge["t_wall_utc"]), (
        "i bordi servono a distinguere due richieste rapide: senza millisecondi "
        "due istanti consecutivi sono indistinguibili")
    assert edge["t_mono"] > 0.0


# ------------------------------------------------------------------ 2
def test_backend_assente_o_muto_degrada_senza_eccezioni():
    """Senza backend, o con read_domains()->None, il bordo e' dichiarato, non finto."""
    edge = _session(None).read_counter_edge()
    assert edge["counter"] is None
    assert "non aperto" in edge["counter_error"]

    edge = _session(_FakeEmi(None)).read_counter_edge()
    assert edge["counter"] is None
    assert edge["counter_error"] == "read_domains() -> None"


# ------------------------------------------------------------------ 3
def test_backend_che_solleva_non_interrompe_il_bordo():
    """Un'eccezione dell'IOCTL diventa ``counter_error``, non un crash del run."""
    edge = _session(_FakeEmi(raises=OSError("ioctl negato"))).read_counter_edge()
    assert edge["counter"] is None
    assert "OSError" in edge["counter_error"]
    assert "ioctl negato" in edge["counter_error"]


# ------------------------------------------------------------------ 4
def test_measurement_edge_dichiara_tutte_le_chiavi(monkeypatch):
    """Il bordo completo ha le chiavi del contratto; il contatore viene prima."""
    monkeypatch.setattr(es, "read_process_table", lambda *a, **k: [])
    monkeypatch.setattr(es, "read_worker_cpu_times", lambda *a, **k: {})
    s = _session(_FakeEmi({"pkg": _pkg(12.5, 123456789)}))

    edge = s.read_measurement_edge()

    for key in ("tree", "worker", "busy", "counter", "counter_error",
                "t_wall", "t_wall_utc", "t_counter_mono", "t_before",
                "t_cpu_mid", "t_after", "edge_spread_s"):
        assert key in edge, f"chiave mancante nel bordo: {key}"
    assert edge["tree"] == []
    assert edge["worker"] == {}
    assert edge["counter"]["ts_100ns"] == 123456789
    # ordine dichiarato: contatore (prima dell'IOCTL) -> letture CPU
    assert edge["t_counter_mono"] <= edge["t_cpu_mid"]
    assert edge["t_before"] <= edge["t_cpu_mid"] <= edge["t_after"]
    assert edge["edge_spread_s"] >= 0.0


# ------------------------------------------------------------------ 5
def test_cpu_edge_alias_storico_non_legge_il_contatore(monkeypatch):
    """Il percorso di produzione non paga la IOCTL: alias a tre chiavi."""
    monkeypatch.setattr(es, "read_process_table", lambda *a, **k: [])
    monkeypatch.setattr(es, "read_worker_cpu_times", lambda *a, **k: {})

    def _boom():
        raise AssertionError("read_counter_edge non deve essere chiamato")

    s = _session(_FakeEmi({"pkg": _pkg(1.0, 1)}))
    monkeypatch.setattr(s, "read_counter_edge", _boom)

    edge = s.read_cpu_edge()
    assert set(edge) == {"tree", "worker", "busy"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
