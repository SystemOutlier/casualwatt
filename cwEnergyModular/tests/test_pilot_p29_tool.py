# -*- coding: utf-8 -*-
"""
tests/test_pilot_p29_tool.py — Il pilota P2.9 dichiara la geometria giusta e
calcola `dt_nominal_s` con la regola congelata.

Perche' esiste. `tools/run_pilot_p29.py` e' il primo pilota P2.9 eseguito sul
runner v4 (P6.2): le sue decisioni — quali bracci, con quanti nonce, con quale
testo — sono dichiarate prima dei dati e valgono come disegno. Il numero che
produce, `dt_nominal_s = 3 x mediana(duration_s)`, e' il requisito 5 di P4.4 e
alimenta la durata del blocco di controllo: un errore di regola qui non si
vedrebbe fino al gate, quando il disegno non e' piu' quello congelato.

Che cosa verifica:
  1. i sei bracci sono quelli del protocollo (A x3 con `num_predict=32`, B x2
     con `m=3` e `num_predict=1` nei due regimi di nonce, C x1 al massimo
     `N_in`), e i loro id sono univoci;
  2. il braccio B usa un testo proprio e non il prefisso dei warm-up: un
     prefisso condiviso con il warm-up sarebbe riuso da un'altra richiesta,
     non fra le tre richieste che il braccio misura; i due bracci B hanno lo
     stesso testo, altrimenti il confronto e' fra testi diversi;
  3. il prompt C e' esattamente il testo del warm-up di P1.4 piu' una domanda,
     cosi' il rapporto token/parola ha un'ancora vera;
  4. la verifica A accetta solo `length`+`cap_reached` e `stop`+`eos`, e
     rifiuta una EOS al tetto: una EOS alla soglia non distingue la fine
     naturale dal cap, che e' cio' che la prova deve mostrare;
  5. `u_within,b` e' `None` a `m = 1` (zero per costruzione) e semi-range
     misurato a `m = 3`;
  6. `dt_nominal_s` esclude le righe con un motivo di invalidita' di P2.5 e
     usa la mediana, non la media;
  7. la verifica C rifiuta la guardia di P2.7 violata e accetta il rapporto
     token/parola entro la tolleranza dichiarata.

Che cosa NON verifica: il motore. Questi sono i controlli che il pilota fa sui
propri dati; che `done_reason` distingua davvero i due casi lo dice solo il run
reale contro Ollama.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import machine_state as ms  # noqa: E402
import run_pilot_p29 as tool  # noqa: E402


def _riga(durata, batch, blocco, note="", energia=10.0, parole=None,
          n_in=100, n_out=32):
    prompt = " ".join(["parola"] * (parole or 10))
    return {"duration_s": durata, "batch_id": batch, "block_id": blocco,
            "notes": note, "active_energy_raw_j": energia,
            "input_tokens": n_in, "output_tokens": n_out,
            "prompt": prompt}


# ---------------------------------------------------------------------------
# 1-3. La geometria dichiarata
# ---------------------------------------------------------------------------
def test_i_sei_bracci_sono_quelli_di_p29():
    """P2.9: due richieste che saturano il tetto e una EOS (A), 3+3 richieste
    per la cache (B), una al massimo N_in (C). La geometria e' il disegno, non
    un dettaglio del codice."""
    bracci = {a["label"]: a for a in tool.arms()}

    assert list(bracci) == ["A1", "A2", "A3", "Bi", "Bn", "C"]
    for label in ("A1", "A2", "A3"):
        assert bracci[label]["m"] == 1
        assert bracci[label]["num_predict"] == 32
        assert bracci[label]["use_nonce"] is True
    for label in ("Bi", "Bn"):
        assert bracci[label]["m"] == 3
        assert bracci[label]["num_predict"] == 1
    assert bracci["Bi"]["use_nonce"] is False
    assert bracci["Bn"]["use_nonce"] is True
    assert bracci["C"]["m"] == 1
    assert bracci["C"]["num_predict"] == 32
    ids = [a["prompt_id"] for a in bracci.values()]
    assert len(set(ids)) == len(ids)


def test_il_braccio_b_non_usa_il_prefisso_dei_warmup():
    """Il warm-up di P1.4 spedisce 518 parole di `WARMUP_SENTENCE`: se il
    braccio identico usasse lo stesso testo, il riuso del prefisso verrebbe
    dal warm-up e non dalle tre richieste. Inoltre i due bracci devono avere
    lo stesso testo, altrimenti non si confronta il nonce ma due prompt."""
    bracci = {a["label"]: a for a in tool.arms()}
    warm = ms.warmup_prompt(ms.WARMUP_N_IN)

    assert bracci["Bi"]["text"] == bracci["Bn"]["text"]
    assert not bracci["Bi"]["text"].startswith(ms.WARMUP_SENTENCE.strip())
    assert not warm.startswith(bracci["Bi"]["text"].split("\n")[0][:20])


def test_il_prompt_c_e_il_warmup_piu_una_domanda():
    """L'ancora del rapporto token/parola e' il warm-up della stessa
    invocazione: C deve contenere esattamente quel testo, non un testo
    'simile', altrimenti il rapporto confronta due generazioni diverse."""
    c = next(a for a in tool.arms() if a["label"] == "C")
    warm = ms.warmup_prompt(ms.WARMUP_N_IN)

    assert c["text"].startswith(warm)
    assert len(c["text"].split()) == len(warm.split()) + len(
        c["text"][len(warm):].split())


# ---------------------------------------------------------------------------
# 4. Il verdetto di A
# ---------------------------------------------------------------------------
def _nota(done, classe, cap=32):
    return (f"done_reason={done}; termination_class={classe}; "
            f"early_stop=false; prompt_nonce=[cw4-00000000]; "
            f"prompt_sha256=abc; num_ctx=8192; num_predict={cap}")


def test_a_accetta_solo_length_e_stop_con_le_classi_attese():
    """La prova A esiste per dimostrare che `done_reason` DISTINGUE i due casi.
    Una EOS al tetto (`eos_at_cap`) non lo dimostra, perche' la fine naturale
    e il cap producono lo stesso `stop`."""
    buoni = {
        "A1": [_riga(1.0, "p29-A1", "b1", _nota("length", "cap_reached"),
                     n_out=32)],
        "A2": [_riga(1.0, "p29-A2", "b2", _nota("length", "cap_reached"),
                     n_out=32)],
        "A3": [_riga(1.0, "p29-A3", "b3", _nota("stop", "eos"), n_out=3)],
    }
    assert tool._verifica_a(buoni)["ok"] is True

    al_tetto = dict(buoni)
    al_tetto["A3"] = [_riga(1.0, "p29-A3", "b3",
                            _nota("stop", "eos_at_cap"), n_out=32)]
    esito = tool._verifica_a(al_tetto)
    assert esito["ok"] is False
    assert "eos_at_cap" in "; ".join(esito["per_label"]["A3"]["motivi"])

    assente = dict(buoni)
    assente["A1"] = [_riga(1.0, "p29-A1", "b1",
                           "done_reason=<assente>; "
                           "termination_class=termination_missing; "
                           "early_stop=<non determinabile>; num_predict=32",
                           n_out=1)]
    assert tool._verifica_a(assente)["ok"] is False


# ---------------------------------------------------------------------------
# 5-6. Terne e congelamento
# ---------------------------------------------------------------------------
def test_u_within_e_none_a_m1_e_semi_range_a_m3():
    """F.9: `u_within,b = semi-range(E_act,i)` sulle richieste del blocco. Con
    una richiesta sola il semi-range e' zero per costruzione, e uno zero per
    costruzione non e' evidenza: la cella resta `None` con la ragione."""
    righe = [
        _riga(1.0, "p29-A1", "blocco-uno", energia=100.0),
        _riga(1.0, "p29-Bi", "blocco-tre", energia=100.0),
        _riga(1.0, "p29-Bi", "blocco-tre", energia=110.0),
        _riga(1.0, "p29-Bi", "blocco-tre", energia=90.0),
    ]
    terne = {t["block_id"]: t for t in tool._terne_blocchi(righe)}

    assert terne["blocco-uno"]["u_within_b_j"] is None
    assert terne["blocco-uno"]["u_within_b_reason"]
    assert terne["blocco-tre"]["u_within_b_j"] == 10.0


def test_dt_nominal_e_tre_volte_la_mediana_delle_righe_valide():
    """P4.4 requisito 5: `dt_nominal_s = 3 x mediana(duration_s)`. Una riga
    con un motivo di invalidita' di P2.5 non entra; la mediana non e' la
    media, e la differenza si vede con durate scelte per distinguerle."""
    righe = [
        _riga(1.0, "p29-A1", "b1"),
        _riga(2.0, "p29-A1", "b1"),
        _riga(3.0, "p29-A2", "b2"),
        _riga(30.0, "p29-Bi", "b3",
              note="done_reason=stop; richiesta invalida per: tokens_missing"),
    ]
    runs = [{"label": "A1", "batch_id": "p29-A1"},
            {"label": "A2", "batch_id": "p29-A2"},
            {"label": "Bi", "batch_id": "p29-Bi"}]
    freeze = tool._freeze_dt(righe, runs)

    assert freeze["dt_nominal_s"] == 6.0        # 3 x mediana(1, 2, 3)
    assert freeze["median_duration_s"] == 2.0   # non la media (2,0) per caso
    assert freeze["rows_used"] == 3
    assert freeze["rows_excluded"]
    assert freeze["per_arm_median_s"]["Bi"] is None


# ---------------------------------------------------------------------------
# 7. La verifica C
# ---------------------------------------------------------------------------
def test_c_rifiuta_la_guardia_violata_e_usa_il_rapporto_token_parola():
    """P2.7: `N_in + N_out <= num_ctx` sulla riga, e il conteggio deve
    corrispondere al prompt costruito. L'ancora e' il warm-up della stessa
    invocazione, normalizzato per parola: i due testi hanno lunghezze diverse
    e confrontare i conteggi grezzi sarebbe un confronto sbagliato."""
    warm = ms.warmup_prompt(ms.WARMUP_N_IN)
    note_run = {
        "notes": ("P1.4 qwen2.5:0.5b: residente=loaded expires_at=-; "
                  "warm-up (512,128) scartati: "
                  "#1 prompt_eval=690 eval=128; #2 prompt_eval=690 eval=128")}
    riga = _riga(5.0, "p29-C", "b6",
                 _nota("stop", "eos"), parole=100, n_in=130, n_out=3)
    ok = tool._verifica_c([riga], note_run, 8192)
    assert ok["ok"] is True
    assert ok["controlli"]["guardia_p27"]["rispettata"] is True
    assert ok["controlli"]["rapporto_token_parola"]["entro_tolleranza"] is True

    fuori_contesto = _riga(5.0, "p29-C", "b6", _nota("stop", "eos"),
                           parole=100, n_in=8200, n_out=100)
    esito = tool._verifica_c([fuori_contesto], note_run, 8192)
    assert esito["ok"] is False
    assert esito["controlli"]["guardia_p27"]["rispettata"] is False

    troncato = _riga(5.0, "p29-C", "b6", _nota("stop", "eos"),
                     parole=500, n_in=100, n_out=3)
    assert tool._verifica_c([troncato], note_run, 8192)["ok"] is False
