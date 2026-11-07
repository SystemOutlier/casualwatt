# -*- coding: utf-8 -*-
"""P4.5 / F.12 — il criterio del gate load-versus-control.

Questi test fissano le tre soglie congelate e i confini che le rendono
verificabili: il filtro e' ``<=`` 1,0 W su entrambe le grandezze, il criterio
per blocco e' ``|E_net| <= budget_base_j``, l'aggregato e' ``|bias_w| <=
mediana(budget_base_w)``. Il bias e' un rapporto di somme pesato sulla durata,
non la media dei rapporti: con blocchi di durata diversa le due letture danno
numeri diversi, e il protocollo scrive una sola formula.

Cosa non verificano: l'esecuzione della campagna (P4.4) e il calcolo di
``u_bias,b``, che vuole la durata media dei blocchi della campagna principale
(F.12) e al momento del gate non esiste.

Le convenzioni di lettura sono quelle dichiarate nel modulo: una cella vuota e'
"non calcolata" e rende inutilizzabile il controllo o non eseguibile il gate
(nominando il campo), un valore non numerico e' un dato corrotto e solleva;
il criterio per blocco si applica ai soli controlli utilizzabili.
"""

import json

import pytest

from control_gate import (
    BIAS_JTOK_PCT_PER_W,
    evaluate_gate,
    main,
    quorum_for,
)


def _rec(block_id="c1", pair_id="p1", **over):
    """Riepilogo di blocco di controllo con numeri coerenti fra loro.

    ``budget_base_j`` e' ``budget_base_w * dt_W``, cosi' il criterio per blocco
    e l'aggregato vedono lo stesso budget e un test non puo' passare per una
    coincidenza fra due campi scollegati.
    """
    base = {
        "block_id": block_id,
        "pair_id": pair_id,
        "block_kind": "control",
        "pre_range_w": 0.4,
        "dP": 0.2,
        "control_e_net_j": 1.5,
        "control_dt_w_s": 36.0,
        "budget_base_w": 0.5,
        "budget_base_j": 18.0,
        "control_package_window_source": "exact-counter",
    }
    base.update(over)
    if "budget_base_w" in over or "control_dt_w_s" in over:
        dt = base["control_dt_w_s"]
        bw = base["budget_base_w"]
        if isinstance(dt, (int, float)) and isinstance(bw, (int, float)):
            base["budget_base_j"] = bw * dt
    return base


def _scarto(block_id, **over):
    """Controllo che non passa il filtro: ``dP`` oltre 1,0 W.

    Serve a completare le sei coppie lasciando esattamente quattro controlli
    utilizzabili, che e' il quorum di F.12: un test sull'aggregato non deve
    dipendere da blocchi stabili che entrano nel conto.
    """
    return _rec(block_id=block_id, dP=3.0, **over)


def _quattro(**over):
    return [_rec(block_id=f"c{i}", **over) for i in (3, 4, 5, 6)]


def test_il_filtro_accetta_esattamente_le_due_soglie():
    """``<= 1,0 W`` include la soglia: a 1,0 W il controllo resta utilizzabile.

    Se il confronto fosse stretto, la soglia congelata di P1.6 non sarebbe la
    stessa regola applicata ai dati e il gate scarterebbe un controllo
    stabile per un epsilon.
    """
    res = evaluate_gate([_rec(pre_range_w=1.0, dP=-1.0)] * 6, n_pairs=6)
    assert res.controls_usable_n == 6
    assert all(c.usable and not c.control_unstable for c in res.controls)


@pytest.mark.parametrize("campo,valore", [
    ("pre_range_w", 1.0001),
    ("dP", 1.0001),
    ("dP", -1.0001),
])
def test_oltre_la_soglia_il_controllo_e_instabile(campo, valore):
    """Superata una soglia il flag ``control_unstable`` e' vero e il blocco esce.

    Sono le due condizioni di P4.5, e ``dP`` entra in valore assoluto: la
    deriva negativa e' grande quanto quella positiva.
    """
    res = evaluate_gate([_rec(**{campo: valore})] * 6, n_pairs=6)
    assert res.controls_usable_n == 0
    assert all(c.control_unstable for c in res.controls)
    assert all("> 1 W" in c.reason for c in res.controls)


def test_una_cella_vuota_non_e_un_controllo_instabile():
    """Vuoto = grandezza non calcolata: inutilizzabile, ma senza affermare deriva.

    Il flag ``control_unstable`` descrive il superamento di una soglia; una
    baseline non misurata non dice che la macchina si muoveva, e confondere i
    due casi renderebbe il flag un'etichetta generica.
    """
    blocchi = [_rec(pre_range_w=""), _rec(dP=None), _rec(dP="")]
    blocchi += [_rec(block_id=f"c{i}") for i in (4, 5, 6)]
    res = evaluate_gate(blocchi, n_pairs=6)
    senza_pre, senza_dp = res.controls[0], res.controls[1]
    assert not senza_pre.usable and not senza_pre.control_unstable
    assert "pre_range_w assente" in senza_pre.reason
    assert not senza_dp.usable and not senza_dp.control_unstable
    assert "dP assente" in senza_dp.reason
    assert res.controls_usable_n == 3
    assert res.status == "not-executable"


def test_un_valore_non_numerico_e_un_dato_corrotto():
    """``"tre"`` in un campo numerico solleva invece di valere come assente.

    Trattarlo come vuoto trasformerebbe un file corrotto in un disegno con un
    controllo in meno, cioe' in un gate che sembra eseguito e non lo e'.
    """
    with pytest.raises(ValueError, match="non numerico"):
        evaluate_gate([_rec(pre_range_w="tre")] * 6, n_pairs=6)


def test_il_quorum_e_la_frazione_non_un_numero_assoluto():
    """``ceil(2/3 * n)``: 4 su 6, 2 su 3, 1 su 1; zero coppie e' un errore."""
    assert quorum_for(6) == 4
    assert quorum_for(3) == 2
    assert quorum_for(1) == 1
    assert quorum_for(9) == 6
    with pytest.raises(ValueError):
        quorum_for(0)


def test_sotto_il_quorum_il_gate_non_esegue_e_dichiara_il_bias():
    """Tre controlli utilizzabili su sei: nessun bias medio, ``bias_declared``.

    F.12 non ammette un bias calcolato su un pugno di blocchi: il risultato e'
    "non eseguibile" e la ragione nomina i blocchi scartati.
    """
    blocchi = [_rec(block_id="c1", pre_range_w=2.0),
               _rec(block_id="c2", dP=1.5),
               _rec(block_id="c3", pre_range_w="")]
    blocchi += [_rec(block_id=f"c{i}") for i in (4, 5, 6)]
    res = evaluate_gate(blocchi, n_pairs=6)
    assert not res.executable
    assert res.status == "not-executable"
    assert res.chain_status == "bias_declared"
    assert res.controls_usable_n == 3
    assert res.bias_w is None and res.bias_threshold_w is None
    assert res.bias_jtok_pct is None
    assert "quorum 4" in res.reasons[0]
    assert any("c1" in r for r in res.reasons)
    assert any("c2" in r for r in res.reasons)
    assert any("c3" in r for r in res.reasons)


def test_col_quorum_il_bias_si_calcola_sui_soli_utilizzabili():
    """Quattro utilizzabili su sei: il bias ignora i due scartati.

    Se entrassero anche i controlli instabili, il filtro di P4.5 non
    cambierebbe il numero che il gate pubblica.
    """
    blocchi = [_scarto("c1", control_e_net_j=1000.0),
               _scarto("c2", control_e_net_j=-1000.0)]
    blocchi += _quattro(control_e_net_j=2.0, control_dt_w_s=10.0,
                        budget_base_w=1.0)
    res = evaluate_gate(blocchi, n_pairs=6)
    assert res.executable and res.controls_usable_n == 4
    assert res.bias_w == pytest.approx(0.2)
    assert res.status == "pass"


def test_il_bias_e_il_rapporto_delle_somme_pesato_sulla_durata():
    """Non la media dei rapporti: ``sum E / sum dt``, come scrive F.12.

    Con (60 J, 10 s) e (10 J, 40 s) accanto a due blocchi da (1 J, 36 s):
    rapporto delle somme 72/122 = 0,5902, media dei rapporti 1,5764. Due
    letture diverse dello stesso dato, e il protocollo ne congela una sola.
    """
    blocchi = [_scarto("c1"), _scarto("c2"),
               _rec(block_id="c3", control_e_net_j=60.0, control_dt_w_s=10.0,
                    budget_base_w=1.0),
               _rec(block_id="c4", control_e_net_j=10.0, control_dt_w_s=40.0,
                    budget_base_w=1.0),
               _rec(block_id="c5", control_e_net_j=1.0),
               _rec(block_id="c6", control_e_net_j=1.0)]
    res = evaluate_gate(blocchi, n_pairs=6)
    assert res.bias_w == pytest.approx(72.0 / 122.0)
    media_rapporti = (60.0 / 10.0 + 10.0 / 40.0 + 1.0 / 36.0
                      + 1.0 / 36.0) / 4
    assert res.bias_w != pytest.approx(media_rapporti)


def test_la_soglia_aggregata_e_la_mediana_dei_budget_utilizzabili():
    """Con quattro valori pari la mediana e' la media dei due centrali (0,25 W).

    E il confronto e' ``<=``: un bias esattamente sulla soglia passa, perche'
    la mediana e' una soglia del protocollo e non un margine da superare.
    """
    blocchi = [_scarto("c1"), _scarto("c2")]
    blocchi += [
        _rec(block_id=f"c{i}", control_e_net_j=1.0, control_dt_w_s=4.0,
             budget_base_w=bw)
        for i, bw in enumerate((0.1, 0.2, 0.3, 0.4), start=3)
    ]
    res = evaluate_gate(blocchi, n_pairs=6)
    assert res.bias_threshold_w == pytest.approx(0.25)
    assert res.bias_w == pytest.approx(0.25)
    assert res.status == "pass"


def test_il_bias_si_riporta_nella_coppia_a_6_e_11_per_watt():
    """La coppia di F.12 e' una grandezza riportata, non una soglia.

    Con bias 0,2 W le due percentuali sono 1,2% e 2,2%; il campo le porta
    entrambe perche' un intervallo non sta in una cella.
    """
    blocchi = [_scarto("c1"), _scarto("c2")]
    blocchi += _quattro(control_e_net_j=0.4, control_dt_w_s=2.0,
                        budget_base_w=5.0)
    res = evaluate_gate(blocchi, n_pairs=6)
    assert res.bias_w == pytest.approx(0.2)
    assert res.bias_jtok_pct == pytest.approx(
        (0.2 * BIAS_JTOK_PCT_PER_W[0], 0.2 * BIAS_JTOK_PCT_PER_W[1]))
    assert BIAS_JTOK_PCT_PER_W == (6.0, 11.0)


def test_il_criterio_per_blocco_si_applica_solo_ai_utilizzabili():
    """Un controllo scartato non si assolve con il budget costruito dal proprio drift.

    P4.5: il filtro "ammette al criterio solo blocchi la cui deriva e' piccola
    in assoluto". Il blocco instabile porta ``block_pass=None`` e la ragione,
    anche quando il proprio budget gli darebbe ragione.
    """
    instabile = _rec(block_id="c1", dP=3.0, control_e_net_j=0.1,
                     budget_base_w=100.0)
    stabile = _rec(block_id="c2", control_e_net_j=-18.0)
    res = evaluate_gate([instabile, stabile] + _quattro(), n_pairs=6)
    c1 = res.controls[0]
    assert c1.block_pass is None
    assert "non applicato" in c1.block_reason
    # |E| = budget = 18 J: il confine del criterio per blocco e' ``<=``.
    assert res.controls[1].block_pass is True


def test_un_utilizzabile_senza_budget_non_chiude_il_campione_in_silenzio():
    """Manca ``budget_base_w`` su un utilizzabile: non eseguibile, non mediana su tre.

    Escluderlo dal calcolo della soglia sarebbe un filtro che il protocollo non
    prevede, applicato proprio alla grandezza che decide il passaggio.
    """
    blocchi = _quattro()
    blocchi[0]["budget_base_w"] = ""
    blocchi += [_scarto("c1"), _scarto("c2")]
    res = evaluate_gate(blocchi, n_pairs=6)
    assert not res.executable
    assert res.status == "not-executable"
    assert res.chain_status == "bias_declared"
    assert any("c3" in r and "budget_base_w" in r for r in res.reasons)


def test_un_denominatore_non_positivo_non_produce_un_bias():
    """Somma delle durate nulla: il bias non esiste e non si inventa.

    Su una finestra di durata zero il rapporto non e' definito; il gate lo
    dichiara invece di restituire un numero che nessuno puo' ricontrollare.
    """
    blocchi = _quattro(control_dt_w_s=0.0, budget_base_w=1.0)
    blocchi += [_scarto("c1"), _scarto("c2")]
    res = evaluate_gate(blocchi, n_pairs=6)
    assert not res.executable
    assert res.bias_w is None
    assert "non positiva" in res.reasons[0]


def test_una_lista_diversa_dalle_coppie_e_un_errore():
    """Il quorum si calcola sul disegno, non su cio' che e' arrivato.

    Cinque controlli per un disegno da sei coppie sono un blocco mancante: se
    il codice calcolasse il quorum sui ricevuti, il gate sembrerebbe completo.
    """
    with pytest.raises(ValueError, match="ha ricevuto 5"):
        evaluate_gate([_rec()] * 5, n_pairs=6)


def test_un_blocco_di_carico_non_entra_nel_gate():
    """``block_kind='load'`` non ha ``E_net,control`` e appartiene a un altro confronto."""
    with pytest.raises(ValueError, match="block_kind"):
        evaluate_gate([_rec(block_kind="load")] * 6, n_pairs=6)


def _rec_lista(e_net, **over):
    return [_rec(block_id=f"c{i}", control_e_net_j=e_net, **over)
            for i in range(1, 7)]


def test_la_riga_di_uscita_e_json_serializzabile_e_ha_il_codice_giusto(
        tmp_path, capsys):
    """La CLI scrive un JSON rileggibile e traduce lo stato in codice di uscita.

    Un gate che passa esce 0, uno non eseguibile esce 2: chi lancia la campagna
    deve poter fermarsi sul codice senza leggere il file.
    """
    sorgente = tmp_path / "blocchi.json"
    sorgente.write_text(json.dumps({"blocks": _rec_lista(0.5)}),
                        encoding="utf-8")
    uscita = tmp_path / "gate.json"
    assert main(["--blocks", str(sorgente), "--out", str(uscita)]) == 0
    dati = json.loads(uscita.read_text(encoding="utf-8"))
    assert dati["status"] == "pass"
    assert dati["executable"] is True
    assert len(dati["controls"]) == 6
    assert dati["bias_jtok_pct"] == pytest.approx(
        [abs(dati["bias_w"]) * 6.0, abs(dati["bias_w"]) * 11.0])

    instabile = tmp_path / "instabile.json"
    instabile.write_text(json.dumps(_rec_lista(0.5, pre_range_w=5.0)),
                         encoding="utf-8")
    assert main(["--blocks", str(instabile)]) == 2
    assert json.loads(capsys.readouterr().out)["chain_status"] == "bias_declared"
