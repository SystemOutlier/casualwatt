# -*- coding: utf-8 -*-
"""
tests/test_gate_uncertainty_p44.py — la regola di combinazione dell'incertezza.

Verifica ``tools/gate_uncertainty.py``: ogni componente dichiara tipo (A/B),
inclusione e motivo; u_c e' la somma in quadratura delle SOLE componenti
incluse; "nessuna incluse" e' None e non zero; una forma non conforme solleva
invece di degradare in silenzio (la forma storica ``calcola_u_c`` saltava le
componenti None senza dirlo).

Non verifica la STIMA delle componenti: quella e' in
``test_budget_p44_preesecuzione.py``.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import pytest  # noqa: E402

import gate_uncertainty as gu  # noqa: E402


def _c(value, tipo="A", inclusa=True, motivo="dichiarata"):
    return {"value": value, "tipo": tipo, "inclusa": inclusa,
            "motivo": motivo}


def test_rss_delle_sole_componenti_incluse():
    comp = {"a": _c(0.3), "b": _c(0.4, tipo="B"),
            "esclusa": _c(9.0, inclusa=False, motivo="gia' nel budget")}
    assert gu.combina_incluse(comp) == pytest.approx(0.5)     # 3-4-5


def test_nessuna_componente_inclusa_e_none_non_zero():
    comp = {"x": _c(0.3, inclusa=False, motivo="gia' nel budget"),
            "y": _c(None, tipo="B", inclusa=False, motivo="non misurabile")}
    assert gu.combina_incluse(comp) is None
    assert gu.combina_incluse({}) is None


def test_inclusa_con_valore_none_o_non_finito_solleva():
    for valore in (None, float("nan"), float("inf"), -0.1, "x", True):
        with pytest.raises(ValueError) as exc:
            gu.combina_incluse({"u": _c(valore)})
        assert "u: inclusa ma value=" in str(exc.value)


def test_forma_non_conforme_solleva_con_tutti_gli_errori():
    comp = {"senza_tipo": {"value": 0.1, "inclusa": True, "motivo": "m"},
            "senza_motivo": _c(0.1, motivo="  "),
            "inclusa_non_bool": {"value": 0.1, "tipo": "A", "inclusa": 1,
                                 "motivo": "m"}}
    with pytest.raises(ValueError) as exc:
        gu.combina_incluse(comp)
    msg = str(exc.value)
    assert "senza_tipo: tipo" in msg
    assert "senza_motivo: 'motivo' obbligatorio" in msg
    assert "inclusa_non_bool: 'inclusa' deve essere True/False" in msg


def test_componente_esclusa_con_valore_informativo_e_ammessa():
    errori = gu.valida_componente(
        "u_rumore", _c(0.1, inclusa=False, motivo="gia' nel budget"))
    assert errori == []
    assert gu.valida_componente(
        "u_rumore", _c(float("nan"), inclusa=False, motivo="m"))


def test_il_doppio_conteggio_storico_e_riproducibile_e_non_piu_prodotto():
    """calcola_u_c (forma storica) sommava anche i due termini del budget:
    con half_range e half_drift u_c == budget. combina_incluse, con quelle
    due componenti marcate escluse, non li somma."""
    half_range, half_drift = 0.1, 0.2
    budget = math.hypot(half_range, half_drift)
    storico = gu.calcola_u_c(dispersione_baseline=half_range,
                             margine_termico=half_drift)[0]
    assert storico == pytest.approx(budget)          # S = budget + 2 u_c = 3 budget
    comp = {"u_rumore": _c(half_range, inclusa=False, motivo="nel budget"),
            "u_termico": _c(half_drift, inclusa=False, motivo="nel budget")}
    assert gu.combina_incluse(comp) is None
