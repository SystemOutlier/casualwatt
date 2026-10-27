# -*- coding: utf-8 -*-
"""Le tre metriche per token aggiunte a P5 il 28-10-2026.

``energy_per_output_token_j`` esisteva; ``energy_per_total_token_j``,
``tokens_per_joule`` e ``kwh_per_million_tokens`` no, e la tesi li ricavava a
mano dal CSV. Le tre colonne sono TRE LETTURE DELLA STESSA GRANDEZZA (energia
end-to-end sui token totali), non stime indipendenti: il test verifica la
coerenza fra loro, non un accordo fra misure.

Criterio di assenza identico alle altre derivate: ``N/A`` quando l'end-to-end
non e' calcolabile (una componente non stimata), stringa vuota quando manca il
conteggio dei token. Mai uno zero inventato, che abbasserebbe le medie.
"""
from types import SimpleNamespace

import pytest

from benchmark_unified import _finalize_energy_fields


def _ev():
    return SimpleNamespace(n_correct_links=None, acc_comp=None, is_correct=None,
                           acc_links_basis="")


def _rec(**kw):
    rec = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
           "notes": [], "local_carbon_intensity_gco2eq_kwh": 0}
    rec.update(kw)
    return rec


def test_le_tre_metriche_sono_la_stessa_energia_su_token_diversi():
    """60 J su 15 token totali: 4 J/token, 0,25 token/J, 1,111 kWh per milione."""
    rec = _rec()
    _finalize_energy_fields(rec, 60.0, 0.0, 0.0, _ev())
    assert rec["energy_per_total_token_j"] == pytest.approx(4.0)
    assert rec["tokens_per_joule"] == pytest.approx(0.25)
    # 4 J/token x 1e6 token = 4e6 J = 4e6 / 3,6e6 kWh
    assert rec["kwh_per_million_tokens"] == pytest.approx(4e6 / 3.6e6, rel=1e-9)
    # e il denominatore "output" resta distinto: 60 J / 5 = 12 J/token
    assert rec["energy_per_output_token_j"] == pytest.approx(12.0)


def test_end_to_end_non_calcolabile_e_n_a_non_zero():
    """Cloud non stimato: niente e2e, quindi N/A su tutte e tre, non 0 J/token."""
    rec = _rec()
    _finalize_energy_fields(rec, 60.0, 0.0, None, _ev())
    for col in ("energy_per_total_token_j", "tokens_per_joule",
                "kwh_per_million_tokens"):
        assert rec[col] == "N/A"


def test_token_assenti_lasciano_la_cella_vuota():
    """Senza conteggio dei token la metrica non esiste: vuoto, non zero e non N/A."""
    rec = _rec(total_tokens=0, input_tokens=0, output_tokens=0)
    _finalize_energy_fields(rec, 60.0, 0.0, 0.0, _ev())
    for col in ("energy_per_total_token_j", "tokens_per_joule",
                "kwh_per_million_tokens"):
        assert rec[col] == ""


def test_energia_zero_non_divide_per_zero():
    """e2e = 0 con token presenti: J/token 0 e kWh 0 sono misure, token/J resta vuoto."""
    rec = _rec()
    _finalize_energy_fields(rec, 0.0, 0.0, 0.0, _ev())
    assert rec["energy_per_total_token_j"] == pytest.approx(0.0)
    assert rec["kwh_per_million_tokens"] == pytest.approx(0.0)
    assert rec["tokens_per_joule"] == ""
