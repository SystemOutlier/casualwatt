# -*- coding: utf-8 -*-
"""
tests/test_compute_annotator_agreement.py — il tool consuma lo schema canonico
e delega al gate, invece di implementare una seconda metrica.

Perche' esiste. ``tools/compute_annotator_agreement.py`` era scritto contro la
versione 1.0 del protocollo, superata per difformita' dal codice
(``human_calibration_protocol.json``, campo ``supersedes``): calcolava
Krippendorff alpha su una scala ORDINALE che la rubrica non dichiara, usava
Cohen kappa come soglia di gate (la preregistrazione corrente lo riporta come
metrica, non criterio), leggeva un proprio schema (``item_id``/``stratum``/
``verdict`` maiuscolo, due file per annotatore) diverso da quello canonico del
gate, sovrascriveva in silenzio gli ``item_id`` duplicati perche' li teneva in
un dict, perdeva senza contare gli item annotati da un solo annotatore, e
lasciava ``compare_with_judge`` come stub. Con ``krippendorff`` non installato
la sua metrica primaria era comunque sempre ``None``.

Che cosa verifica:
  1. il report riporta i valori del gate (una sola implementazione autorevole:
     alpha nominale, kappa, accordo percentuale, numerosita');
  2. kappa non e' un criterio: un ramo con kappa non disponibile resta
     ``validated'' se il gate lo promuove -- il tool non inventa soglie;
  3. nessuna scala ordinale inventata: le etichette restano categoriali e la
     distribuzione delle classi le riporta verbatim;
  4. lo schema non canonico (il fixture sintetico con ``expected_verdict``) e'
     rifiutato, non convertito: un'etichetta preassegnata non e' un giudizio
     umano indipendente;
  5. i task_id duplicati sono rifiutati e nominati, come nel loader del gate;
  6. il secondo report contiene la Verifica B completa (matrice di confusione,
     metriche, coverage, stati per ramo, diagnostica dei difetti);
  7. il codice d'uscita segue lo stato del gate, non una decisione propria;
  8. lo stato del campione (fixture tecnico vs annotazioni scientifiche) e i
     digest degli input sono dichiarati nei report: il tool non promuove mai un
     campione tecnico a campione scientifico.

Che cosa NON verifica: il gate stesso (suo test dedicato), il motore LLM e la
campagna reale.
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import compute_annotator_agreement as tool  # noqa: E402
from human_calibration_gate import (  # noqa: E402
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    CALIBRATION_THRESHOLD,
    MIN_ADMISSIBLE_FRACTION,
    MIN_DECIDED_ITEMS,
    MIN_PAIRABLE_ITEMS,
    JudgeAcceptanceCriteria,
    run_scoring_validation_gate,
    verifica_a,
)

CRITERI = JudgeAcceptanceCriteria(
    min_precision_correct=0.90,
    min_recall_correct=0.80,
    max_fp_rate=0.10,
    min_accuracy=0.85,
    min_coverage=0.80,
)


def _cal(n=12, etichetta="correct"):
    """Calibrazione in schema canonico (annotations nidificato, come il
    template del gate)."""
    return [{"task_id": f"cal_number_{i}", "answer_type": "number",
             "annotations": {"annotator_1": etichetta,
                             "annotator_2": etichetta}}
            for i in range(n)]


def _val(n=10, verdetto="correct"):
    """Validazione in schema canonico: riferimento da accordo concorde."""
    return [{"task_id": f"val_number_{i}", "answer_type": "number",
             "annotator_1": "correct", "annotator_2": "correct",
             "judge_verdict": verdetto}
            for i in range(n)]


def _preregistrazione(tmp_path, criteri=CRITERI):
    """Protocollo preregistrato minimo, nella forma del template del gate."""
    p = tmp_path / "protocol.json"
    p.write_text(json.dumps({
        "strata": ["number"],
        "verifica_a": {"threshold_alpha": 0.8},
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": criteri.min_precision_correct,
            "min_recall_correct": criteri.min_recall_correct,
            "max_fp_rate": criteri.max_fp_rate,
            "min_accuracy": criteri.min_accuracy,
            "min_coverage": criteri.min_coverage,
        }},
    }, ensure_ascii=False), encoding="utf-8")
    return p


def _scrivi(tmp_path, cal, val):
    cal_file = tmp_path / "cal.jsonl"
    val_file = tmp_path / "val.jsonl"
    cal_file.write_text("\n".join(json.dumps(r) for r in cal), encoding="utf-8")
    val_file.write_text("\n".join(json.dumps(r) for r in val), encoding="utf-8")
    return cal_file, val_file


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _lancia(tmp_path, cal, val, prereg=None, sample_status=None, out_dir=None):
    cal_file, val_file = _scrivi(tmp_path, cal, val)
    argv = ["--calibration", str(cal_file), "--validation", str(val_file)]
    if prereg is not None:
        argv += ["--preregistration", str(prereg)]
    if sample_status is not None:
        argv += ["--sample-status", sample_status]
    if out_dir is not None:
        argv += ["--out-dir", str(tmp_path / out_dir)]
    return tool.main(argv), (tmp_path / out_dir if out_dir else tmp_path)


def test_report_di_accordo_riporta_i_valori_del_gate(tmp_path):
    """Una sola implementazione autorevole: il report di Verifica A riporta
    alpha, kappa, accordo percentuale e numerosita' pari a quelli che il gate
    calcola sugli stessi record. Se il tool ricalcolasse per conto proprio --
    con un altro livello di misura o un altro vocabolario -- i due numeri
    divergerebbero e il preregistrato perderebbe il suo produttore unico."""
    cal, val = _cal(), _val()
    cal_file, val_file = _scrivi(tmp_path, cal, val)
    codice, out = _lancia(tmp_path, cal, val, prereg=_preregistrazione(tmp_path),
                          out_dir="out")
    assert codice == 0
    report = json.loads((out / "human_calibration_agreement_report.json")
                        .read_text(encoding="utf-8"))
    attesi = verifica_a([dict(r, **r["annotations"]) for r in cal])["number"]
    riga = report["verifica_a"]["number"]
    assert riga["alpha_nominal"] == attesi.alpha_nominal
    assert riga["kappa_nominal"] == attesi.kappa_nominal
    assert riga["percent_agreement"] == attesi.percent_agreement
    assert riga["n_items"] == attesi.n_items
    assert riga["n_pairable"] == attesi.n_pairable


def test_kappa_non_e_un_criterio_del_gate(tmp_path):
    """Kappa e' una metrica riportata, non un criterio: con un'annotazione di
    una classe sola kappa non e' calcolabile (p_e = 1) e il vecchio tool
    trattava ``None`` come 0, bocciando il ramo con una soglia che la
    preregistrazione corrente non contiene. Il report deve promuovere il ramo
    quando il gate lo promuove, riportando kappa come None con la sua ragione."""
    cal, val = _cal(), _val()
    codice, out = _lancia(tmp_path, cal, val, prereg=_preregistrazione(tmp_path),
                          out_dir="out")
    accordo = json.loads((out / "human_calibration_agreement_report.json")
                         .read_text(encoding="utf-8"))
    giudice = json.loads((out / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    assert accordo["verifica_a"]["number"]["kappa_nominal"] is None
    assert accordo["verifica_a"]["number"]["kappa_reason"] != ""
    assert giudice["scoring_status_per_stratum"]["number"] == "validated"
    assert giudice["scoring_status"] == "validated"


def test_nessuna_scala_ordinale_inventata(tmp_path):
    """Le etichette sono categoriali: la rubrica non dichiara alcun ordine
    Correct > Indeterminate > Incorrect, quindi il tool non puo' mapparle su
    una scala numerica. La distribuzione delle classi deve riportare le
    etichette verbatim e alpha deve essere quella nominale del gate, non il
    valore che una metrica ordinale produrrebbe sugli stessi disaccordi."""
    cal = []
    for i in range(12):
        coppia = ([("correct", "correct")] * 6
                  + [("incorrect", "incorrect")] * 3
                  + [("indeterminate", "indeterminate")] * 3)
        a1, a2 = coppia[i]
        cal.append({"task_id": f"cal_number_{i}", "answer_type": "number",
                    "annotator_1": a1, "annotator_2": a2})
    val = _val()
    codice, out = _lancia(tmp_path, cal, val, prereg=_preregistrazione(tmp_path),
                          out_dir="out")
    assert codice == 0
    report = json.loads((out / "human_calibration_agreement_report.json")
                        .read_text(encoding="utf-8"))
    riga = report["verifica_a"]["number"]
    attesi = verifica_a(cal)["number"]
    assert riga["alpha_nominal"] == attesi.alpha_nominal
    assert riga["class_distribution"] == {"correct": 6, "incorrect": 3,
                                          "indeterminate": 3}
    assert "ORDINAL_MAP" not in dir(tool)


def test_lo_schema_non_canonico_e_rifiutato_senza_conversione(tmp_path):
    """Il fixture sintetico del campione precedente (item_id, stratum,
    expected_verdict preassegnato) non e' uno schema canonico e non e'
    convertito: un'etichetta attesa dall'autore non e' un giudizio umano
    indipendente e cieco. Il rifiuto arriva dal loader del gate, che nomina il
    campo mancante, e nessun report viene scritto."""
    fixture = [{"item_id": f"HC-{i:03d}", "stratum": "number",
                "query": "Quanto fa 5*5-4?", "ground_truth": "21",
                "expected_verdict": "Correct", "difficulty": "clear_correct"}
               for i in range(12)]
    val = _val()
    cal_file, val_file = _scrivi(tmp_path, fixture, val)
    with pytest.raises(ValueError, match="task_id"):
        tool.main(["--calibration", str(cal_file), "--validation", str(val_file),
                   "--preregistration", str(_preregistrazione(tmp_path)),
                   "--out-dir", str(tmp_path / "out")])
    assert not (tmp_path / "out" / "human_calibration_agreement_report.json").exists()


def test_task_id_duplicato_e_rifiutato_e_nominato(tmp_path):
    """Un duplicato nel campione di validazione -- il verdetto del giudice
    registrato due volte per lo stesso item -- conterebbe doppio nella matrice
    di confusione. Il tool non sovrascrive (il vecchio caricava in un dict per
    item_id): l'errore nomina il task_id colpevole."""
    cal = _cal()
    val = _val()
    val.append(dict(val[0]))
    cal_file, val_file = _scrivi(tmp_path, cal, val)
    with pytest.raises(ValueError, match="val_number_0"):
        tool.main(["--calibration", str(cal_file), "--validation", str(val_file),
                   "--preregistration", str(_preregistrazione(tmp_path))])


def test_report_giudice_contiene_verifica_b_e_la_diagnostica(tmp_path):
    """Il secondo artefatto dichiarato dal protocollo e' il confronto con il
    giudice: matrice di confusione, metriche per classe, coverage e stato per
    ramo. Un disaccordo senza adjudication non produce riferimento: il report
    lo conta in ``unscored`` invece di lasciarlo invisibile."""
    cal = _cal()
    val = _val(n=9)
    val.append({"task_id": "val_number_disaccordo", "answer_type": "number",
                "annotator_1": "correct", "annotator_2": "incorrect"})
    codice, out = _lancia(tmp_path, cal, val, prereg=_preregistrazione(tmp_path),
                          out_dir="out")
    giudice = json.loads((out / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    riga = giudice["verifica_b"]["number"]
    assert riga["confusion"]["correct"]["correct"] == 9
    assert riga["coverage"] == 1.0
    assert riga["accuracy"] == 1.0
    assert giudice["diagnostics"]["unscored"] == 1
    assert giudice["scoring_status"] == "validated"


def test_exit_code_segue_lo_stato_del_gate(tmp_path):
    """Il codice d'uscita non e' una decisione del tool: 0 solo se il gate
    promuove tutti i rami. Senza preregistrazione i criteri non sono
    registrati e il gate e' fail-closed -- il tool non promuove e non inventa
    soglie al posto suo."""
    cal, val = _cal(), _val()
    cal_file, val_file = _scrivi(tmp_path, cal, val)
    codice = tool.main(["--calibration", str(cal_file),
                        "--validation", str(val_file),
                        "--out-dir", str(tmp_path / "out")])
    assert codice == 1
    giudice = json.loads((tmp_path / "out" / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    assert giudice["scoring_status_per_stratum"]["number"] == "criteria_not_registered"


def test_stato_del_campione_e_digest_sono_dichiarati(tmp_path):
    """Il tool non trasforma un campione tecnico in un campione scientifico:
    riporta lo stato dichiarato dall'operatore e i digest dei due file in
    ingresso, cosi' il report e' ricostruibile, e non certifica nulla da se'
    sulla validita' scientifica del campione."""
    cal, val = _cal(), _val()
    codice, out = _lancia(tmp_path, cal, val, prereg=_preregistrazione(tmp_path),
                          sample_status="technical_fixture", out_dir="out")
    assert codice == 0
    for nome in ("human_calibration_agreement_report.json",
                 "human_calibration_judge_comparison.json"):
        report = json.loads((out / nome).read_text(encoding="utf-8"))
        assert report["sample_status"] == "technical_fixture"
        assert report["input_digests"]["calibration"] == _digest(tmp_path / "cal.jsonl")
        assert report["input_digests"]["validation"] == _digest(tmp_path / "val.jsonl")
        assert "scientifically_validated" not in report
        assert "validity_note" in report


def test_report_del_giudice_dichiara_la_catena_di_abilitazione(tmp_path):
    """L'artefatto si porta dietro la dichiarazione della catena: la soglia
    alpha abilita l'uso del riferimento umano, non il giudice. Il report del
    giudice -- quello che un lettore consulta per sapere se le etichette di
    correttezza sono affidabili -- lo dice nelle proprie note, invece di
    lasciare la soglia alpha leggibile come abilitazione (correzione 1 della
    specifica). La nota viene dal gate: il tool non ne scrive una parallela."""
    cal, val = _cal(), _val()
    codice, out = _lancia(tmp_path, cal, val,
                          prereg=_preregistrazione(tmp_path), out_dir="out")
    assert codice == 0
    giudice = json.loads((out / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    note = giudice["notes"].lower()
    assert "necessaria" in note and "sufficiente" in note
    assert "verifica b" in note


# --- Fase 4: prove combinatorie sulle correzioni della revisione -------------
#
# Le correzioni 3.4, 3.5, 3.6, E2, 2.3, 2.4 e 2.5 sono state verifyate una per
# una nei blocchi precedenti. Qui si verificano le COMBINAZIONI al confine del
# tool: una preregistrazione malformata non deve potere promuovere un campione,
# ne' una dichiarazione degenerere deve potere passare per una configurazione.


def _scrivi_prereg(tmp_path, protocollo, nome="protocol.json"):
    p = tmp_path / nome
    p.write_text(json.dumps(protocollo, ensure_ascii=False),
                 encoding="utf-8")
    return p


def _report_non_scritto(tmp_path, out="out"):
    cartella = tmp_path / out
    return (not (cartella / "human_calibration_agreement_report.json").exists()
            and not (cartella
                     / "human_calibration_judge_comparison.json").exists())


def test_g5_prereg_con_min_coverage_degenere_e_rifiutata_senza_report(tmp_path):
    """E2 al confine del tool. Una preregistrazione che dichiara
    ``min_coverage: 0'' non e' una soglia: un giudice che si astiene su ogni
    item la soddisfa, quindi promuoverebbe un ramo su copertura arbitraria.
    Il tool deve rifiutare la configurazione -- con il nome del campo -- e non
    scrivere alcun report: un artefatto scritto a meta' di un rifiuto
    sembrerebbe un risultato."""
    prereg = _scrivi_prereg(tmp_path, {
        "strata": ["number"],
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": 0.10, "min_accuracy": 0.85,
            "min_coverage": 0.0}}})
    with pytest.raises(ValueError, match="min_coverage"):
        tool.main(["--calibration", str(tmp_path / "cal.jsonl"),
                   "--validation", str(tmp_path / "val.jsonl"),
                   "--preregistration", str(prereg),
                   "--out-dir", str(tmp_path / "out")])
    assert _report_non_scritto(tmp_path)


def test_g6_preregistrazione_non_json_e_rifiutata_per_nome(tmp_path):
    """Una preregistrazione illeggibile non e' un fail-closed silenzioso: se
    il tool tratasse un file corroto come "nessuna preregistrazione", i criteri
    risulterebbero non registrati e il run fallirebbe con una causa diversa da
    quella vera -- una configurazione da correggere, non da indovinare. Qui il
    file esiste e non e' JSON: il rifiuto lo nomina."""
    rotto = tmp_path / "rotto.json"
    rotto.write_text("{ questo non e' json", encoding="utf-8")
    with pytest.raises(ValueError, match="preregistrazione"):
        tool.main(["--calibration", str(tmp_path / "cal.jsonl"),
                   "--validation", str(tmp_path / "val.jsonl"),
                   "--preregistration", str(rotto),
                   "--out-dir", str(tmp_path / "out")])
    assert _report_non_scritto(tmp_path)


def test_g7_chiave_non_prevista_nei_criteri_e_rifiutata(tmp_path):
    """Una chiave che non e' un criterio preregistrato (p. es. una soglia
    inventata, o il nome di un campo di un'altra versione del protocollo) non
    viene ignorata in silenzio: una soglia ignorata sarebbe una
    configurazione diversa da quella dichiarata, scoperta dopo i dati. Il
    rifiuto elenca le chiavi ammesse, cosi' la correzione e' leggibile dal
    messaggio."""
    prereg = _scrivi_prereg(tmp_path, {
        "strata": ["number"],
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": 0.10, "min_accuracy": 0.85, "min_coverage": 0.80,
            "min_brier_score": 0.05}}})
    with pytest.raises(ValueError, match="min_brier_score"):
        tool.main(["--calibration", str(tmp_path / "cal.jsonl"),
                   "--validation", str(tmp_path / "val.jsonl"),
                   "--preregistration", str(prereg),
                   "--out-dir", str(tmp_path / "out")])
    assert _report_non_scritto(tmp_path)


def test_g8_strati_a_oggetti_del_protocollo_tracciato_con_criteri_nulli(tmp_path):
    """La forma reale della preregistrazione tracciata: ``strata'' e' un
    elenco di oggetti con ``name'' e ``target_items'', e
    ``acceptance_criteria'' ha tutti i campi a ``None'' -- criteri da fissare
    prima dei dati reali, non ancora registrati. Il tool deve leggere quella
    forma senza convertirla, riportare i tre strati nell'ordine dichiarato e
    restare fail-closed: ``criteria_not_registered'' sullo strato misurato,
    ``insufficient_data'' sui due strati senza campione, uscita 1. Il report
    dice anche quali pavimenti preregistrati vigevano, perche' un verdetto
    cambia significato se il pavimento si sposta."""
    prereg = _scrivi_prereg(tmp_path, {
        "strata": [{"name": "number", "target_items": 14},
                   {"name": "short_text", "target_items": 13},
                   {"name": "free_text", "target_items": 13}],
        "verifica_a": {"threshold_alpha": 0.8, "bootstrap_seed": 20261104,
                       "bootstrap_resamples": 2000},
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": None, "min_recall_correct": None,
            "max_fp_rate": None, "min_accuracy": None,
            "min_coverage": None}}})
    cal_file, val_file = _scrivi(tmp_path, _cal(), _val())
    codice = tool.main(["--calibration", str(cal_file),
                        "--validation", str(val_file),
                        "--preregistration", str(prereg),
                        "--out-dir", str(tmp_path / "out")])
    assert codice == 1
    giudice = json.loads((tmp_path / "out"
                          / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    usata = giudice["preregistration_used"]
    assert usata["required_strata"] == ["number", "short_text", "free_text"]
    assert usata["criteria_registered"] is False
    assert usata["threshold_alpha"] == CALIBRATION_THRESHOLD
    assert usata["bootstrap_seed"] == BOOTSTRAP_SEED
    assert usata["bootstrap_resamples"] == BOOTSTRAP_RESAMPLES
    assert usata["preregistered_floors"] == {
        "min_pairable_items": MIN_PAIRABLE_ITEMS,
        "min_decided_items": MIN_DECIDED_ITEMS,
        "min_admissible_fraction": MIN_ADMISSIBLE_FRACTION}
    assert giudice["scoring_status"] == "not_validated"
    assert giudice["scoring_status_per_stratum"] == {
        "number": "criteria_not_registered",
        "short_text": "insufficient_data",
        "free_text": "insufficient_data"}
    # sample_status non dichiarato resta visibile: il tool non certifica la
    # provenienza del campione ne' per default ne' per omissione.
    assert giudice["sample_status"] == "not_declared"


def test_g9_criteri_parziali_restano_fail_closed(tmp_path):
    """Criteri parzialmente registrati: tre soglie su cinque. La
    preregistrazione non e' completa, quindi il gate e' fail-closed e il tool
    non promuove ne' sostituisce le soglie mancanti con le proprie -- sarebbe
    una configurazione diversa da quella dichiarata, e un ``validated'' ottenuto
    con criteri inventati al momento dei dati."""
    prereg = _scrivi_prereg(tmp_path, {
        "strata": ["number"],
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": None, "min_accuracy": None,
            "min_coverage": None}}})
    codice, out = _lancia(tmp_path, _cal(), _val(), prereg=prereg,
                          out_dir="out")
    assert codice == 1
    giudice = json.loads((out / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    assert giudice["scoring_status_per_stratum"]["number"] == \
        "criteria_not_registered"
    assert giudice["preregistration_used"]["criteria_registered"] is False


def test_g10_elenco_di_strati_vuoto_rifiutato_e_assenza_della_chiave_no(tmp_path):
    """3.6 al confine del tool. Un elenco di strati DICHIARATO vuoto e' una
    configurazione degenere: il gate rifiuterebbe di misurare zero item e il
    verdetto complessivo risulterebbe validated per costruzione, quindi il
    tool rifiuta la preregistrazione invece di rigirarla al gate. La chiave
    ASSENTE non e' invece una dichiarazione: non compare, quindi valgono gli
    strati preregistrati del gate e il run prosegue -- la differenza fra
    "dichiarato vuoto" e "non dichiarato" e' la differenza fra una scelta e
    un silenzio."""
    vuoto = _scrivi_prereg(tmp_path, {
        "strata": [],
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": 0.10, "min_accuracy": 0.85,
            "min_coverage": 0.80}}})
    # Il messaggio nomina la chiave come compare nel file preregistrato
    # ('strata'), non la sua traduzione: la correzione va fatta li'.
    with pytest.raises(ValueError, match="strata"):
        tool.main(["--calibration", str(tmp_path / "cal.jsonl"),
                   "--validation", str(tmp_path / "val.jsonl"),
                   "--preregistration", str(vuoto),
                   "--out-dir", str(tmp_path / "out")])
    assert _report_non_scritto(tmp_path)
    senza_chiave = _scrivi_prereg(tmp_path, {
        "verifica_a": {"threshold_alpha": 0.8},
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": 0.10, "min_accuracy": 0.85,
            "min_coverage": 0.80}}})
    cal_file, val_file = _scrivi(tmp_path, _cal(), _val())
    codice = tool.main(["--calibration", str(cal_file),
                        "--validation", str(val_file),
                        "--preregistration", str(senza_chiave),
                        "--out-dir", str(tmp_path / "out2")])
    giudice = json.loads((tmp_path / "out2"
                          / "human_calibration_judge_comparison.json")
                         .read_text(encoding="utf-8"))
    assert giudice["preregistration_used"]["required_strata"] == [
        "number", "short_text", "free_text"]
    # Con tre strati obbligatori e un campione solo su number, il gate non
    # promuove il complesso: due strati senza campione sono insufficient_data.
    # number resta validated (i criteri sono registrati e superati), quindi
    # l'esito e' partially_validated -- un ramo promosso non copre gli altri.
    assert giudice["scoring_status"] == "partially_validated"
    assert giudice["scoring_status_per_stratum"]["number"] == "validated"
    assert giudice["scoring_status_per_stratum"]["short_text"] == \
        "insufficient_data"
    assert giudice["scoring_status_per_stratum"]["free_text"] == \
        "insufficient_data"
    assert codice == 1


def test_g11_prereg_degenere_su_due_fronti_non_promuove_comunque(tmp_path):
    """E2 + 3.6 presentati insieme: criteri con coverage nulla E elenco di
    strati vuoto. Ogni singolo difetto e' gia' rifiutato per conto suo; la
    combinazione non deve produrre un esito diverso -- ne' un report, ne'
    un'uscita 0. Il rifiuto arriva dal criterio (letto per primo), ma la
    prova e' l'esito: nessun artefatto, nessuna promozione."""
    prereg = _scrivi_prereg(tmp_path, {
        "strata": [],
        "verifica_b": {"acceptance_criteria": {
            "min_precision_correct": 0.90, "min_recall_correct": 0.80,
            "max_fp_rate": 0.10, "min_accuracy": 0.85,
            "min_coverage": 0.0}}})
    with pytest.raises(ValueError, match="min_coverage"):
        tool.main(["--calibration", str(tmp_path / "cal.jsonl"),
                   "--validation", str(tmp_path / "val.jsonl"),
                   "--preregistration", str(prereg),
                   "--out-dir", str(tmp_path / "out")])
    assert _report_non_scritto(tmp_path)
