# -*- coding: utf-8 -*-
"""
tests/test_filtro_p6_invalidati.py — Filtro P6 eseguibile dell'Emenda 8:
`partition_block_rows` in benchmark_v4.py.

Perche' esiste. `invalid_reason` su una riga NON e' un'esclusione: e' un'info-
rmazione finche' il codice che aggrega non la interpreta, e la nota "NON en-
trano in nessuna analisi" scritta nel CSV non sostituisce un filtro. Il rischio
prioritario resta quindi una riga di blocco invalidato che entra in una stima
primaria per dimenticanza. `partition_block_rows` e' il gate che l'ordine di
servizio del 26-10 chiede: le stime primarie possono leggere SOLO `valid_rows`,
e tutto cio' che non torna SOLLEVA invece di essere incluso o escluso per
default. La fonte autoritativa dell'invalidazione e' il riepilogo di blocco:
una riga non timbrata ma appartenente a un blocco caduto deve essere esclusa
comunque, perche' e' li' che un bug di timbratura si trasformerebbe in un
numero silenziosamente sporco.

Che cosa verifica (le cinque regole dell'ordine di servizio):
  1. esclusione: righe di blocchi invalidati finiscono in excluded_rows ANCHE
     se la riga non ha timbrato nulla (caso decisivo), e non stanno in
     valid_rows per nessuna ragione;
  2. identita': il sostituto valido e' distinguibile dall'originale invalidato
     (chiavi diverse, tentativi diversi, replaced_block_id reciproco) e le
     confusioni (tentativo 2 senza sostituito, tentativo 1 con sostituito,
     sostituto di un blocco valido) sollevano;
  3. conservazione: niente mutazioni, niente cancellazioni, niente
     sovrascritture: gli input restano identici, le liste restituite sono
     copie, e due riepiloghi con la stessa chiave (batch_id, block_id) sono
     un rifiuto;
  4. concordia: motivo, tentativo, replaced_block_id e point_id in disaccordo
     fra riga e riepilogo sollevano — la scelta di quale dei due credere
     sarebbe un fallback silenzioso;
  5. conteggi: validi / invalidati / sostitutivi / mancanti sono ricalcolati
     dai soli riepiloghi e verificabili a posteriori, e il tutto e' provato
     anche sull'output grezzo del runner stesso (integrazione), non solo su
     fixture scritte a mano.

Che cosa NON verifica: che le analisi a valle CHIAMINO davvero il gate (non
esiste ancora un consumatore di analisi: il filtro e' la condizione necessaria,
non la garanzia, e la lacuna e' dichiarata nel rapporto); hardware reale,
round-trip su CSV (il filtro opera su records in memoria, l'integrazione usa
le righe che il runner passa all'export, non quelle rilette da disco); il
contenuto scientifico dei token oltre la loro forma.
"""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

import benchmark_v4 as v4  # noqa: E402
from test_emenda8_sostituzione import _fault, _ok, _run  # noqa: E402


def _summ(block, *, batch="B1", point="m__p1", attempt=1, reason="",
          replaced=""):
    """Riepilogo di blocco minimalista: solo le chiavi che il gate legge."""
    return {"batch_id": batch, "point_id": point, "block_id": block,
            "block_attempt": attempt, "invalid_reason": reason,
            "replaced_block_id": replaced}


def _rrow(block, *, batch="B1", point="m__p1", attempt=None, reason=None,
          replaced=None):
    """Riga di richiesta: i campi Emenda 8 compaiono solo se passati, cosi'
    che la riga "non timbrata" (tutti e tre assenti) sia rappresentabile."""
    r = {"batch_id": batch, "point_id": point, "block_id": block,
         "duration_s": 2.0, "notes": ""}
    if attempt is not None:
        r["block_attempt"] = attempt
    if reason is not None:
        r["invalid_reason"] = reason
    if replaced is not None:
        r["replaced_block_id"] = replaced
    return r


# --------------------------------------------------------------- 1: esclusione
def test_riga_di_blocco_invalidato_esclusa_anche_se_non_timbrata():
    """IL CASO DECISIVO: il riepilogo dichiara delta_negativo, la riga non ha
    invalid_reason, block_attempt ne' replaced_block_id (timbratura saltata).
    Il gate la esclude PERCHE' E' IL RIEPILOGO LA FONTE AUTORITATIVA: una riga
    del genere, lasciata alle stime primarie perche' "la riga non dice nulla",
    e' esattamente il difetto che l'ordine di servizio prevede qui."""
    out = v4.partition_block_rows(
        [_rrow("m__p1__b01")],
        [_summ("m__p1__b01", reason="delta_negativo")])
    assert out["valid_rows"] == []
    assert len(out["excluded_rows"]) == 1
    assert out["excluded_rows"][0]["block_id"] == "m__p1__b01"
    assert out["counts"]["excluded_rows"] == 1
    assert out["counts"]["valid_rows"] == 0
    assert out["counts"]["invalidated_blocks"] == 1
    assert out["counts"]["valid_blocks"] == 0


def test_motivo_sulla_riga_coerente_esclude_egualmente():
    """La via normale (runner che timbra le righe del post-guasto): la riga
    porta il token identico al riepilogo e viene esclusa; il token sulla riga
    non e' una seconda fonte, e' un riscontro."""
    out = v4.partition_block_rows(
        [_rrow("m__p1__b01", attempt=1, reason="lettura_non_finita",
               replaced="")],
        [_summ("m__p1__b01", reason="lettura_non_finita")])
    assert out["valid_rows"] == [] and len(out["excluded_rows"]) == 1


# --------------------------------------------------------------- 2: identita'
def test_sostituto_valido_non_confuso_con_originale_invalidato():
    """b01 cade (pre, nessuna riga) e il suo sostituto b01__s2 completa con
    due righe: le righe valide sono SOLO del sostituto, il conteggio separa
    i due blocchi, e l'originale resta invalidated_blocks senza righe."""
    rows = [_rrow("m__p1__b01__s2", attempt=2, reason="",
                  replaced="m__p1__b01"),
            _rrow("m__p1__b01__s2", attempt=2, reason="",
                  replaced="m__p1__b01")]
    out = v4.partition_block_rows(
        rows,
        [_summ("m__p1__b01", reason="delta_negativo"),
         _summ("m__p1__b01__s2", attempt=2, replaced="m__p1__b01")])
    assert len(out["valid_rows"]) == 2
    assert {r["block_id"] for r in out["valid_rows"]} == {"m__p1__b01__s2"}
    assert out["excluded_rows"] == []
    c = out["counts"]
    assert (c["valid_blocks"], c["invalidated_blocks"],
            c["substitute_blocks"], c["missing_blocks"]) == (1, 1, 1, 0)


def test_guasto_post_esclude_le_righe_e_il_sostituto_le_produce_di_nuove():
    """Lo scenario completo della regola 1 + 2: l'originale ha righe gia'
    esportate (post) che restano evidenze escluse, il sostituto ha righe
    valide. La stessa chiave (batch, block) non si mescola mai."""
    summ = [_summ("m__p1__b01", reason="replica_non_positiva"),
            _summ("m__p1__b01__s2", attempt=2, replaced="m__p1__b01"),
            _summ("m__p1__b02")]
    rows = ([_rrow("m__p1__b01", attempt=1, reason="replica_non_positiva")
             for _ in range(2)]
            + [_rrow("m__p1__b01__s2", attempt=2, replaced="m__p1__b01")]
            + [_rrow("m__p1__b02")])
    out = v4.partition_block_rows(rows, summ)
    assert [r["block_id"] for r in out["excluded_rows"]] == ["m__p1__b01",
                                                             "m__p1__b01"]
    assert {r["block_id"] for r in out["valid_rows"]} == {"m__p1__b01__s2",
                                                          "m__p1__b02"}
    c = out["counts"]
    assert (c["valid_blocks"], c["invalidated_blocks"],
            c["substitute_blocks"], c["missing_blocks"],
            c["valid_rows"], c["excluded_rows"]) == (2, 1, 1, 0, 2, 2)


# ------------------------------------------------------- 5: conteggi (mancante)
def test_conteggio_mancante_e_tetto_k_il_punto_resta_scoperto():
    """b01 cade, il suo sostituto cade a sua volta (ambedue con righe post),
    e un altro punto ha il suo caduto con sostituto riuscito: il punto
    p1 e' coperto da zero righe valide, e i quattro conteggi separano
    invalidati (3), sostitutivi eseguiti (2), mancante (1), valido (1).
    mancante = invalidato al tentativo 2, la stessa definizione del runner
    (missing_ids)."""
    summ = [_summ("m__p1__b01", reason="delta_negativo"),
            _summ("m__p1__b01__s2", attempt=2, reason="lettura_non_finita",
                  replaced="m__p1__b01"),
            _summ("m__p2__b01", reason="replica_non_positiva"),
            _summ("m__p2__b01__s2", attempt=2, replaced="m__p2__b01")]
    rows = [_rrow("m__p1__b01", attempt=1, reason="delta_negativo"),
            _rrow("m__p1__b01__s2", attempt=2, reason="lettura_non_finita",
                  replaced="m__p1__b01"),
            _rrow("m__p2__b01__s2", attempt=2, replaced="m__p2__b01")]
    out = v4.partition_block_rows(rows, summ)
    c = out["counts"]
    assert (c["valid_blocks"], c["invalidated_blocks"],
            c["substitute_blocks"], c["missing_blocks"]) == (1, 3, 2, 1)
    assert (c["valid_rows"], c["excluded_rows"]) == (1, 2)
    assert out["valid_rows"][0]["block_id"] == "m__p2__b01__s2"


# -------------------------------------------------------------- 3: conservazione
def test_input_non_mutati_e_liste_rese_copiate():
    """Regola 3: il registro append-only non si tocca. Il gate non ammette
    mutationi degli input, e cio' che restituisce sono copie: un'analisi che
    sporca una riga restituita non sporca il registro."""
    rows = [_rrow("m__p1__b01", attempt=1, reason="delta_negativo"),
            _rrow("m__p1__b02")]
    summ = [_summ("m__p1__b01", reason="delta_negativo"),
            _summ("m__p1__b02")]
    rows_before, summ_before = copy.deepcopy(rows), copy.deepcopy(summ)
    out = v4.partition_block_rows(rows, summ)
    assert rows == rows_before and summ == summ_before
    out["valid_rows"][0]["duration_s"] = 999.0
    out["excluded_rows"][0]["invalid_reason"] = "manipolata"
    assert rows[1]["duration_s"] == 2.0
    assert rows[0]["invalid_reason"] == "delta_negativo"


def test_riepiloghi_duplicati_sono_un_rifiuto_non_una_scelta():
    """Due riepiloghi con la stessa (batch_id, block_id): la regola 3 vieta
    la sovrascrittura e il gate non puo' nemmeno scegliere il "primo" o il
    "secondo" — e' un registro corrotto, si ferma."""
    with pytest.raises(ValueError, match="duplicata"):
        v4.partition_block_rows(
            [], [_summ("m__p1__b01"), _summ("m__p1__b01",
                                            reason="delta_negativo")])


def test_gate_vuoto_non_inventa_niente():
    """Nessuna riga e nessun riepilogo (run fermato da K prima di tutto): il
    gate risponde con il vuoto e i suoi zeri, non con un'eccezione ne' con
    un blocco fantasma contato come valido."""
    out = v4.partition_block_rows([], [])
    assert out["valid_rows"] == [] and out["excluded_rows"] == []
    assert all(v == 0 for v in out["counts"].values())


# ------------------------------------------------------ 4: concordia (solleva)
def test_riga_orfana_solleva_e_non_vi_niente_inclusa():
    """Una riga senza riepilogo per la sua chiave non e' ne' valida ne'
    invalidata: includerla sarebbe il default silenzioso, escluderla
    cancellerebbe evidenza. Il gate la rifiuta."""
    with pytest.raises(ValueError, match="orfana"):
        v4.partition_block_rows([_rrow("m__p1__b09")],
                                 [_summ("m__p1__b01")])


@pytest.mark.parametrize("row,summaries,fragments", [
    # la riga dichiara invalidita' su un blocco che il riepilogo dice valido
    (_rrow("m__p1__b01", reason="delta_negativo"),
     [_summ("m__p1__b01")], "valido"),
    # motivo in disaccordo fra i DUE token congelati
    (_rrow("m__p1__b01", reason="delta_negativo"),
     [_summ("m__p1__b01", reason="lettura_non_finita")], "motivo"),
    # tentativo in disaccordo (l'originale sostituito c'e' ed e' invalidato:
    # il rifiuto deve arrivare sul tentativo, non sull'identita')
    (_rrow("m__p1__b01__s2", attempt=1, reason="replica_non_positiva",
           replaced="m__p1__b01"),
     [_summ("m__p1__b01", reason="replica_non_positiva"),
      _summ("m__p1__b01__s2", attempt=2, reason="replica_non_positiva",
            replaced="m__p1__b01")], "tentativo"),
    # replaced_block_id in disaccordo
    (_rrow("m__p1__b01__s2", attempt=2, replaced="m__p1__b07"),
     [_summ("m__p1__b01", reason="delta_negativo"),
      _summ("m__p1__b01__s2", attempt=2, replaced="m__p1__b01")],
     "replaced_block_id"),
    # point_id in disaccordo
    (_rrow("m__p1__b01", point="m__p2"),
     [_summ("m__p1__b01", point="m__p1")], "point_id"),
])
def test_disaccordo_riga_riepilogo_solleva(row, summaries, fragments):
    """Regola 4 su ciascun asse di concordia (motivo, tentativo,
    identificativo, punto): il disaccordo NON si risolve, si dichiara."""
    with pytest.raises(ValueError, match=fragments):
        v4.partition_block_rows([row], summaries)


@pytest.mark.parametrize("reason", ["counter_invalid", "contatore_pazzo"])
def test_token_non_congelato_sul_riepilogo_solleva(reason):
    """Il quarto token non esiste (P1.6 emendata ne congela tre): un
    marcatore sconosciuto sul riepilogo non puo' autorizzare un'esclusione.
    "counter_invalid" e' il token di P4.9 pre-Emenda: se riappare nel
    registro, il disegno del run non e' quello approvato."""
    with pytest.raises(ValueError, match="token"):
        v4.partition_block_rows([], [_summ("m__p1__b01", reason=reason)])


def test_riga_con_token_non_congelato_solleva():
    """Anche lato riga il token deve essere uno dei tre: un'etichetta
    inventata a mano sul CSV e' un rifiuto, non un'esclusione automatica."""
    with pytest.raises(ValueError, match="token"):
        v4.partition_block_rows(
            [_rrow("m__p1__b01", reason="contatore_pazzo")],
            [_summ("m__p1__b01", reason="delta_negativo")])


@pytest.mark.parametrize("summaries,fragment", [
    # tentativo 2 senza dire cosa sostituisce: indistinguibile dal piano
    ([_summ("m__p1__b01__s2", attempt=2, replaced="")], "senza"),
    # tentativo 1 che dichiara un sostituito: identita' incrociata
    ([_summ("m__p1__b01", replaced="m__p1__b00")], "confusion"),
    # il sostituto dichiara di sostituire un blocco.VALIDO
    ([_summ("m__p1__b01"), _summ("m__p1__b01__s2", attempt=2,
                                 replaced="m__p1__b01")], "VALIDO"),
    # il sostituto dichiara di sostituire un blocco inesistente
    ([_summ("m__p1__b01__s2", attempt=2, replaced="m__p1__b00")], "nessun"),
    # un tentativo 3 non esiste nell'Emenda 8
    ([_summ("m__p1__b01", attempt=3)], "1, 2"),
    # un tentativo non intero non si interpreta
    ([_summ("m__p1__b01", attempt="due")], "intero"),
])
def test_identita_del_blocco_non_ambigua_o_si_ferma(summaries, fragment):
    """Regola 2 + 4 lato riepiloghi: ogni forma di ambiguita' fra piano e
    sostituto (riferimento mancante, incrociato, verso un valido, verso un
    nulla, tentativo fuori rango) e' un rifiuto dichiarato."""
    with pytest.raises(ValueError, match=fragment):
        v4.partition_block_rows([], summaries)


def test_riepilogo_senza_block_id_solleva():
    """Un riepilogo non identificabile non puo' autorizzare nulla: la chiave
    primaria del join e' richiesta, non dedotta."""
    with pytest.raises(ValueError, match="senza block_id"):
        v4.partition_block_rows([], [{"batch_id": "B1", "block_id": "",
                                      "invalid_reason": "delta_negativo"}])


# ------------------------------------------------------------- integrazione
def test_integrazione_le_righe_esportate_dal_runner_passano_il_gate(monkeypatch):
    """Il filtro e' provato sull'output del runner VERO, non su fixture:
    run_v4_benchmark con post-calibration fault (righe marcate e esportate)
    e blocco successivo valido. Le righe che il runner esporta devono passare
    il gate ESATTAMENTE come le timbra lui: divise in excluded (il caduto) e
    valid (il resto), coi conteggi che combaciano con i contatori del run
    (invalidated_blocks, substitutions)."""
    def impl(kw):
        if kw["block_id"] == "m__p1__b01":
            # guasto POST: le m=1 righe esistono, con le chiavi di join
            return _fault(kw, rows=[{
                "batch_id": kw["batch_id"], "point_id": kw["point_id"],
                "block_id": kw["block_id"], "duration_s": 2.0,
                "notes": "nota tecnica del fake"}])
        return _ok(kw)

    sink = {}
    calls, summaries, meta, out = _run(
        monkeypatch, impl, [{"id": "p1", "text": "t1"}], blocks=2,
        stub_args={"k": "2", "seed": "seme-filtro"}, sink=sink)
    rows = [r for batch in sink["rows"] for r in batch]
    assert len(rows) == 1, "solo il post-guasto esporta righe (fake)"

    part = v4.partition_block_rows(rows, summaries)
    # la riga del blocco caduto NON sta nelle stime primarie
    assert part["valid_rows"] == []
    assert len(part["excluded_rows"]) == 1
    assert part["excluded_rows"][0]["invalid_reason"] == "delta_negativo"
    # gate e runner concordano sui conteggi, ciascuno calcolato dalla propria
    # fonte: il gate dai soli riepiloghi, il runner dal proprio contatore
    assert part["counts"]["invalidated_blocks"] == out["invalidated_blocks"]
    assert part["counts"]["substitute_blocks"] == out["substitutions"] == 1
    assert part["counts"]["valid_blocks"] == 2  # b02 e il sostituto riuscito
    assert part["counts"]["missing_blocks"] == 0
    # il registro resta intero: 3 riepiloghi (caduto, b02, sostituto) + 1 riga
    assert len(summaries) == 3 and len(calls) == 3
    # e la riga esclusa conserva l'evidenza: nota del runner + nota del fake
    assert "NON entrano in nessuna analisi" in part["excluded_rows"][0]["notes"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
