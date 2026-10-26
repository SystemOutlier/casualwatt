# -*- coding: utf-8 -*-
"""Blocco remoto: alias del provider, proxy dichiarato, banda, N/A.

Quattro difetti del 26-10-2026, uno per test, tutti invisibili alla suite
precedente perche' `tests/test_cloud_energy_none_preservato.py` verificava solo
la semantica None/0 e non chiamava mai il motore.

1. **La mappa del provider valeva per il badge e non per la stima.** La GUI
   traduceva "google" -> "google_genai" prima di chiedere il registro, la stima
   no: la scheda del modello era marcata "registrato" e la riga finiva
   "unavailable", con cloud_energy_j = N/A su una chiamata valida. La mappa ora
   e' un solo oggetto (`ECOLOGITS_PROVIDER_MAP`) importato da entrambi, e il
   test lo congela per identita', non per uguaglianza di contenuto.
2. **Il ramo proxy puntava a un provider che non esiste.** Le regole
   dichiaravano "openrouter", che non e' fra i provider del registro EcoLogits
   0.11.1 (anthropic, cohere, google_genai, huggingface_hub, mistralai, openai):
   nessun proxy poteva risolvere. Ora i proxy vanno su huggingface_hub con gli ID
   esatti del registro, e la taglia e' rispettata -- un 70B su una scheda da 8B
   sarebbe un errore di classe di un ordine di grandezza, non un'approssimazione.
3. **La banda calcolata non arrivava in riga.** Il motore produce un intervallo
   min/max (propagazione delle assunzioni registrate, non confidenza); il valore
   principale e' il punto medio, ma il minimo e il massimo non venivano scritti.
   Il test verifica la conversione kWh -> J (fattore 3,6e6) contro il ritorno
   grezzo del motore, non contro una costante copiata a mano.
4. **Una componente mancante deve restare N/A fino all'end-to-end.** Se la stima
   cloud fallisce, `cloud_energy_j` e `end_to_end_energy_j` sono "N/A": uno zero
   al loro posto abbasserebbe la somma e i J/token della riga, e nessuna colonna
   direbbe che il numero manca.

I test usano il motore EcoLogits installato, senza rete: `llm_impacts` e' puro
calcolo su un registro locale. Se EcoLogits non e' installato il file si salta
(`importorskip`), perche' senza motore non c'e' niente da verificare. La
dipendenza dal registro e' voluta: se un giorno un provider o un ID cambia nome,
questi test falliscono e lo dicono, invece di lasciare la riga a N/A in silenzio.

Esecuzione:  python -m pytest tests/test_cloud_proxy_and_mapping.py -v
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ecologits = pytest.importorskip(
    "ecologits", reason="ecologits non installato: nessun motore da verificare")

import benchmark_unified as bu  # noqa: E402
from cloud_estimator import _ECLOGITS_PROVIDER_MAP  # noqa: E402
from energy.cloud_energy import (  # noqa: E402
    ECOLOGITS_PROVIDER_MAP,
    _candidate_models,
    estimate_cloud_energy,
)

from ecologits.tracers.utils import llm_impacts  # noqa: E402


def _est(**kw):
    """Chiamata di stima con i parametri che i test cambiano uno alla volta."""
    base = dict(model_name="gpt-4o-mini", prompt_tokens=20, completion_tokens=64,
                duration_s=0.5, provider="openai")
    base.update(kw)
    return estimate_cloud_energy(**base)


def _kwh_value(node) -> float:
    """kWh da un nodo del motore, sia esso `Value` o un float nudo."""
    return float(getattr(node, "value", node))


def _ev():
    """Valutazione minima: i soli campi letti da `_finalize_energy_fields`."""
    return SimpleNamespace(
        n_correct_links=None, acc_comp=None, is_correct=None, acc_links_basis="",
        acc_links=None, judge_score=None, cosine_sim=None)


# ---------------------------------------------------------------- 1
def test_l_alias_del_provider_vale_anche_per_la_stima_non_solo_per_il_badge():
    """"google" e "huggingface" devono produrre un numero, non "unavailable".

    Con la mappa applicata solo al badge, una chiamata valida a
    google/gemini-2.0-flash usciva N/A: il registro non conosce "google" e la
    stima non traduceva. Il profilo hardware della riga porta il nome con cui il
    motore ha risposto, quindi e' la prova che la traduzione e' arrivata.
    """
    assert ECOLOGITS_PROVIDER_MAP["google"] == "google_genai"
    assert ECOLOGITS_PROVIDER_MAP["huggingface"] == "huggingface_hub"
    # un solo esemplare: se il badge avesse una copia propria, le due potrebbero
    # divergere di nuovo senza che nessun test lo veda.
    assert _ECLOGITS_PROVIDER_MAP is ECOLOGITS_PROVIDER_MAP

    g = _est(model_name="gemini-2.0-flash", provider="google")
    assert g.energy_j is not None and g.energy_j > 0
    assert g.hw_profile == "google_genai/gemini-2.0-flash"
    assert g.method.startswith("ecologits llm_impacts")

    h = _est(model_name="meta-llama/Meta-Llama-3.1-8B-Instruct",
             provider="huggingface")
    assert h.energy_j is not None and h.energy_j > 0
    assert h.hw_profile == "huggingface_hub/meta-llama/Meta-Llama-3.1-8B-Instruct"


# ---------------------------------------------------------------- 2
def test_il_proxy_risolve_su_huggingface_hub_con_la_taglia_giusta():
    """Il proxy esiste nel registro e non collassa la classe di parametri.

    "openrouter" non e' un provider EcoLogits: finche' le regole puntavano a
    lui, ogni modello non registrato finiva in "unavailable". La taglia conta:
    un 70B stimato su una scheda da 8B sbaglia di un ordine di grandezza, e la
    riga non lo dichiarerebbe.
    """
    pairs = list(_candidate_models("groq", "llama-3.3-70b-versatile"))
    assert pairs[0] == ("groq", "llama-3.3-70b-versatile")
    assert ("huggingface_hub", "meta-llama/Meta-Llama-3.1-70B-Instruct") in pairs
    assert len(pairs) == len(set(pairs)), "una coppia ripetuta duplica le note"

    assert ("huggingface_hub",
            "meta-llama/Meta-Llama-3.1-8B-Instruct") in list(
        _candidate_models("groq", "llama-3.1-8b-instant"))
    assert ("huggingface_hub",
            "meta-llama/Meta-Llama-3.1-405B-Instruct") in list(
        _candidate_models("groq", "llama-3.1-405b"))
    assert ("huggingface_hub", "google/gemma-2-9b-it") in list(
        _candidate_models("google", "gemma-2-9b-it"))

    est = _est(model_name="llama-3.3-70b-versatile", provider="groq")
    assert est.energy_j is not None and est.energy_j > 0
    assert est.hw_profile == (
        "huggingface_hub/meta-llama/Meta-Llama-3.1-70B-Instruct")
    # il proxy si dichiara: la stima e' di una classe di modelli, non del modello
    assert any("proxy dichiarato" in n for n in est.notes)

    # e nessun residuo del provider inesistente: anche se il chiamante lo
    # passasse, ogni ripiego successivo e' huggingface_hub, mai "openrouter".
    for name in ("llama-3.3-70b-versatile", "gemma-2-9b-it", "mixtral-8x7b"):
        fallbacks = list(_candidate_models("openrouter", name))[1:]
        assert fallbacks and all(prov == "huggingface_hub"
                                 for prov, _ in fallbacks)


# ---------------------------------------------------------------- 3
def test_la_banda_min_max_arriva_nel_dizionario_della_riga_in_joule():
    """min/max del motore (kWh) diventano joule e finiscono nelle colonne.

    `energy_j` e' il punto medio dell'intervallo: senza minimo e massimo la riga
    perde il range da cui il numero proviene, e il lettore non puo' distinguere
    una stima stretta da una larga. La conversione e' 1 kWh = 3,6e6 J, e la si
    verifica contro il ritorno grezzo del motore, non contro una costante.
    """
    raw = llm_impacts(provider="openai", model_name="gpt-4o-mini",
                      output_token_count=64, request_latency=0.5)
    est = _est()
    # il motore annida l'intervallo in energy.value; il valore principale e' il
    # punto medio, gli estremi sono quelli che la riga deve conservare.
    kwh = raw.energy.value
    assert est.energy_min_j == pytest.approx(
        _kwh_value(kwh.min) * 3_600_000.0, abs=1e-6)
    assert est.energy_max_j == pytest.approx(
        _kwh_value(kwh.max) * 3_600_000.0, abs=1e-6)
    assert est.energy_min_j < est.energy_j < est.energy_max_j

    fields = bu._cloud_estimate_fields(est)
    assert fields["cloud_energy_min_j"] == est.energy_min_j
    assert fields["cloud_energy_max_j"] == est.energy_max_j
    # la diagnostica che accompagna la banda: chi l'ha prodotta e come
    assert fields["cloud_input_tokens_included"] is False
    assert fields["cloud_pue_source"] == "provider_catalog_ecologits"
    assert fields["cloud_latency_used_s"] == pytest.approx(0.5)


# ---------------------------------------------------------------- 4
def test_una_componente_mancante_porta_end_to_end_a_na():
    """Stima cloud fallita: colonne a "N/A" e end-to-end a "N/A", mai 0.0.

    Uno zero al posto di N/A abbasserebbe la somma end-to-end e i J/token della
    riga, e nessuna colonna direbbe che il numero manca: la riga sembrerebbe
    una richiesta senza costo cloud invece di una stima non riuscita.
    """
    est = _est(model_name="modello-non-registrato-xyz")
    assert est.energy_j is None
    assert est.method.startswith("unavailable")
    fields = bu._cloud_estimate_fields(est)
    assert fields["cloud_energy_min_j"] == "N/A"
    assert fields["cloud_energy_max_j"] == "N/A"
    assert fields["cloud_pue_applied"] == "N/A"

    rec = {"output_tokens": 10, "notes": "",
           "local_carbon_intensity_gco2eq_kwh": 0}
    bu._finalize_energy_fields(rec, 5.0, 0.25, est.energy_j, _ev())
    assert rec["cloud_energy_j"] == "N/A"
    assert rec["end_to_end_energy_j"] == "N/A"
    assert rec["energy_per_output_token_j"] == "N/A"
    assert "cloud_energy_j" in rec["notes"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
