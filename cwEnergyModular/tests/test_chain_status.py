# -*- coding: utf-8 -*-
"""La catena di validazione di P4.9 produce un token, con le soglie congelate.

Perche' esiste. `chain_status` era un nome di colonna senza produttore: la
regola "validata si scrive solo se tutti e sei gli anelli passano" non era
eseguibile dal codice, quindi nessuna riga poteva portare `validated`. Questi
test bloccano le tre cose che rendono il token una decisione e non un'opinione:

  1. **l'ordine**: l'esito e' il primo anello che cede, non l'anello piu'
     comodo da citare;
  2. **le soglie**: 10% di `r_A` (2 blocchi su 3), quorum `ceil(2/3 . n)`,
     `|bias_w| <= mediana`, `p_lof_perm >= 0,05`, `err_rel <= 10%`, con i
     confini **inclusi** dove il protocollo scrive `<=` o `>=`;
  3. **l'assenza di invenzioni**: un campo di analisi vuoto non e' uno zero e
     non produce uno stato; nessuna etichetta fuori dal vocabolario.

Le soglie non si verificano qui nel merito (perche' 10% e non 8%): quello e'
congelato nel protocollo e il test verifica solo che il codice usi QUELLE.
"""

import pytest

from validation_chain import (
    BASELINE_BLOCKS_MIN, BASELINE_R_A_MAX, BIAS_DECLARED, COUNTER_INVALID,
    CONTROL_QUORUM, ERR_REL_MAX, LOF_P_MIN, MODEL_INADEQUATE, REDUCED_DESIGN,
    STATUS_LABELS, VALIDATED, VALIDATION_FAILED, BASELINE_UNSTABLE,
    baseline_unstable, bias_declared, chain_status, counter_invalid,
    model_inadequate, validation_failed,
)


def _blocchi(point_id="p1", r_a=0.05, n=3, **extra):
    """n blocchi di un punto, stabili per default."""
    return [dict({"block_id": f"{point_id}-b{i}", "point_id": point_id,
                  "r_A": r_a, "negative_increment": "false",
                  "invalid_reason": "", "replaced_block_id": ""}, **extra)
            for i in range(n)]


def _controllo(i, **extra):
    rec = {"pre_range_w": 0.4, "dP": 0.2, "e_net_j": 1.0, "dt_w_s": 30.0,
           "budget_base_j": 30.0, "budget_base_w": 0.5}
    rec.update(extra)
    return dict({"control_id": f"c{i}"}, **rec)


def _controlli(n=6, **extra):
    return [_controllo(i, **extra) for i in range(n)]


def _conferma(err_rel=0.02, e_pred_j=100.0, inside_interval=True,
              pred_nonpositive=False):
    return {"err_rel": err_rel, "e_pred_j": e_pred_j,
            "inside_interval": inside_interval,
            "pred_nonpositive": pred_nonpositive}


def _catena(**override):
    dati = dict(blocks=_blocchi("p1") + _blocchi("p2"),
                controls=_controlli(),
                n_pairs=6,
                p_lof_perm=0.40,
                confirmation_points=[_conferma(), _conferma(err_rel=0.05)],
                reduced_design=False)
    dati.update(override)
    return chain_status(**dati)


# ------------------------------------------------------------------ 1 ordine
def test_sei_anelli_puliti_danno_validated():
    """Tutti i criteri rispettati: la parola si assegna, ed e' una sola."""
    assert _catena() == VALIDATED


def test_l_esito_e_del_primo_anello_che_cede():
    """Contatore, baseline, bias, modello e conferma rotti insieme: vince l'anello 2.

    Un solo token per riga: riportare l'anello piu' "interessante" invece del
    primo renderebbe il confronto fra campagne dipendente da chi scrive.
    """
    esito = _catena(
        blocks=[dict(b, negative_increment="true") for b in _blocchi("p1")],
        p_lof_perm=0.001)
    assert esito == COUNTER_INVALID

    esito = _catena(blocks=_blocchi("p1", r_a=0.30) + _blocchi("p2"),
                    p_lof_perm=0.001)
    assert esito == BASELINE_UNSTABLE

    esito = _catena(controls=_controlli(3), p_lof_perm=0.001)
    assert esito == BIAS_DECLARED


# ------------------------------------------------------------------ 2 contatore
def test_blocco_con_delta_negativo_invalida_la_catena():
    """Anello 2: `negative_increment` su un blocco che resta nel disegno."""
    assert counter_invalid(_blocchi("p1") + _blocchi("p2")) is False
    assert counter_invalid(
        _blocchi("p1") + _blocchi("p2", negative_increment=True)) is True


def test_blocco_tecnico_sostituito_non_invalida_la_campagna():
    """Emenda 8 (P1.6): il guasto sostituito non e' un buco del disegno.

    Il blocco invalidato e' ancora nel file, ma la sua copertura e' nel
    sostituto; se il sostituto cede, il suo `invalid_reason` e' presente e
    l'anello fallisce.
    """
    rotto = dict(_blocchi("p1", n=1)[0], negative_increment="true",
                 invalid_reason="delta_negativo")
    sostituto = dict(_blocchi("p1", n=1)[0], block_id="p1-b0-r2",
                     block_attempt=2, replaced_block_id="p1-b0")
    assert counter_invalid([rotto, sostituto]) is False
    # sostituto a sua volta rotto: nessuno copre quel blocco
    sostituto_rotto = dict(sostituto, invalid_reason="lettura_non_finita")
    assert counter_invalid([rotto, sostituto_rotto]) is True


# ------------------------------------------------------------------ 3 baseline
def test_due_blocchi_stabili_su_tre_bastano_uno_no():
    """Soglia P1.6: `r_A <= 10%` in almeno 2 blocchi su 3 per punto."""
    due = _blocchi("p1") + [dict(_blocchi("p1", n=1)[0], block_id="p1-x",
                                 r_A=0.50)] + _blocchi("p2")
    assert baseline_unstable(due) is False
    uno = _blocchi("p1", n=1) + [dict(_blocchi("p1", n=1)[0], block_id="p1-x",
                                      r_A=0.50),
                                 dict(_blocchi("p1", n=1)[0], block_id="p1-y",
                                      r_A=0.80)] + _blocchi("p2")
    assert baseline_unstable(uno) is True


def test_il_confine_del_dieci_per_cento_e_incluso():
    """`r_A <= 10%`: un blocco a 0,10 esatto e' stabile; a 0,1000001 no."""
    assert baseline_unstable(_blocchi("p1", r_a=BASELINE_R_A_MAX)) is False
    assert baseline_unstable(_blocchi("p1", r_a=BASELINE_R_A_MAX + 1e-6)) is True
    assert BASELINE_BLOCKS_MIN == 2


def test_r_a_vuoto_non_e_uno_zero_e_non_produce_uno_stato():
    """Campo di analisi vuoto = analisi non eseguita: nessuno stato inventato."""
    with pytest.raises(ValueError, match="r_A"):
        _catena(blocks=[dict(b, r_A="") for b in _blocchi("p1")])


# ------------------------------------------------------------------ 4 bias
def test_il_quorum_e_due_terzi_delle_coppie():
    """F.12: con sei coppie servono 4 controlli utilizzabili, non 3.

    `ceil(2/3 * 6) = 4`. Sotto il quorum il gate non e' eseguibile e il bias
    si dichiara: non si pubblica una media su un pugno di blocchi.
    """
    assert CONTROL_QUORUM == pytest.approx(2 / 3)
    assert bias_declared(_controlli(3), 6) is True
    assert bias_declared(_controlli(4), 6) is False
    # cinque coppie: ceil(10/3) = 4, non 3
    assert bias_declared(_controlli(3), 5) is True


def test_controllo_instabile_esce_dal_calcolo_del_bias():
    """Il filtro di stabilita' e' 1,0 W su `pre_range_w` e 1,0 W su `|dP|`, inclusi."""
    assert bias_declared(_controlli(6, pre_range_w=1.0, dP=1.0), 6) is False
    assert bias_declared(_controlli(6, pre_range_w=1.01), 6) is True
    assert bias_declared(_controlli(6, dP=-1.01), 6) is True


def test_bias_oltre_la_mediana_dei_budget_si_dichiara():
    """`|bias_w| <= mediana(budget_base_w)`: il confine e' incluso."""
    # bias = 6 J / 180 s = 0,0333 W contro mediana 0,5 W
    assert bias_declared(_controlli(6), 6) is False
    # bias = 180 J / 180 s = 1 W contro mediana 0,5 W
    assert bias_declared(_controlli(6, e_net_j=30.0), 6) is True


def test_un_controllo_oltre_il_proprio_budget_fa_fallire_il_gate():
    """F.12: `|E_net,c| <= budget_base_j,c` per ogni controllo utilizzabile."""
    assert bias_declared(_controlli(6, budget_base_j=0.5), 6) is True


# ------------------------------------------------------------------ 5 modello
def test_lack_of_fit_al_confine():
    """Anello 5: `p_lof_perm >= 0,05` passa; sotto e' `model_inadequate`."""
    assert LOF_P_MIN == 0.05
    assert model_inadequate(0.05) is False
    assert model_inadequate(0.0499) is True
    assert _catena(p_lof_perm=0.0499) == MODEL_INADEQUATE


# ------------------------------------------------------------------ 6 conferma
def test_entrambi_i_punti_di_conferma_devono_passare():
    """Un punto solo non e' un caso valutato: il denominatore non si riduce."""
    assert validation_failed([_conferma(), _conferma(err_rel=ERR_REL_MAX)]) is False
    assert validation_failed([_conferma(err_rel=ERR_REL_MAX + 1e-6)]) is True
    assert validation_failed([_conferma()]) is True
    assert validation_failed([_conferma(inside_interval=False), _conferma()]) is True
    assert validation_failed([_conferma()]) is True
    assert _catena(confirmation_points=[_conferma(err_rel=0.5), _conferma()]) \
        == VALIDATION_FAILED


def test_previsione_non_positiva_e_un_fallimento():
    """`E_pred <= 0` non si rifitta: e' `validation_failed` (`pred_nonpositive`)."""
    assert validation_failed([_conferma(e_pred_j=0.0), _conferma()]) is True
    assert validation_failed([_conferma(pred_nonpositive=True), _conferma()]) is True


# ------------------------------------------------------------ disegno ridotto
def test_disegno_ridotto_non_copre_un_anello_rotto():
    """`reduced_design` si aggiunge alle etichette, non le sostituisce."""
    assert _catena(reduced_design=True) == REDUCED_DESIGN
    assert _catena(reduced_design=True, p_lof_perm=0.001) == MODEL_INADEQUATE


# ------------------------------------------------------------- vocabolario
def test_nessuna_etichetta_fuori_dal_vocabolario_congelato():
    """Il protocollo ha sei etichette di anello piu' `validated` e `reduced_design`."""
    assert set(STATUS_LABELS) == {
        VALIDATED, COUNTER_INVALID, BASELINE_UNSTABLE, BIAS_DECLARED,
        MODEL_INADEQUATE, VALIDATION_FAILED, REDUCED_DESIGN}
    # l'anello 1 (pilota P2.9) non e' un esito di catena: non ha un token
    assert not any("pilot" in label or "campaign" in label
                   for label in STATUS_LABELS)


def test_le_righe_lette_dal_csv_si_valutano_come_i_dict_del_runner():
    """Nel CSV i numeri e i booleani sono stringhe: `"true"` e `"0.05"` valgono.

    Il produttore gira dopo l'analisi, quindi legge i riepiloghi dal file. Se
    leggesse solo i dict del runner, la catena non sarebbe calcolabile sul
    dataset pubblicato.
    """
    blocchi = [dict(b, r_A="0.0500", negative_increment="false")
               for b in _blocchi("p1") + _blocchi("p2")]
    controlli = [dict(c, pre_range_w="0.40", dP="0.20", e_net_j="1.0",
                      dt_w_s="30.0", budget_base_j="30.0",
                      budget_base_w="0.5") for c in _controlli()]
    conferme = [dict(_conferma(), err_rel="0.0200", e_pred_j="100.0",
                     inside_interval="true") for _ in range(2)]
    assert chain_status(blocks=blocchi, controls=controlli, n_pairs=6,
                        p_lof_perm="0.40", confirmation_points=conferme) \
        == VALIDATED
