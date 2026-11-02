"""Test del recupero dell'etichetta e della sua fonte in `benchmark/valuta.py`.

Perche' esiste. Sull'held-out misurato del 02-11 la riga di report
`etichetta_ok: 138` su 240 veniva letta come "il classificatore sbaglia 102 volte
su 240". E' falso, e il test `test_etichetta_attesa_in_tutti_i_240_testi_registrati`
lo misura sugli artefatti veri: il testo del passo `classificator` contiene
l'etichetta attesa in **240 run su 240**. Il numero 138 e' il conteggio dei run
che il gate della traduzione ha lasciato arrivare al tool, perche' la chiave
`etichetta` viene scritta da `run_orchestrato.run` solo li', e `valuta.py` la
leggeva come se fosse la risposta del modello.
Evidenza: `harness/risultati/analisi_rami_deboli_20261102.txt`, sezione 6.

Cosa fissano questi test.
  1. il parser (`etichette.py`) vale la prima etichetta ammessa per posizione nel
     testo, che e' quella che il modello dichiara;
  2. `valuta.py` distingue **da dove** arriva l'etichetta: `risultato` (chiave
     scritta dal run), `passo` (recuperata dal testo registrato), `assente`
     (ne' l'una ne' l'altra, e non e' una misura del classificatore);
  3. la correzione muove il diagnostico e **non** muove il punteggio: una riga
     fermata dal gate resta `corretta = False` perche' `numero` non c'e', quindi
     `corretta = etichetta_ok AND numero_ok` non cambia. Se un domani un test
     come questo spostasse `corrette`, sarebbe il metro a essere cambiato, non la
     precisione: da qui il vincolo esplicito sul punteggio invariato.

Cosa **non** fanno: nessuna chiamata a Ollama e nessuna misura d'energia. I tre
casi duri -- "il gate rifiuta ma il passo ha risposto giusto", "il passo non
cita etichette", "il passo non c'e'" -- si costruiscono con dizionari sintetici
perche' sono le chiavi del JSON a definire il comportamento, non il modello.

Uso, con il python di sistema che ha pytest (il venv `MUDILabV` della misura NON
deve contenerlo, vedi `test_coherence_e_oracolo.py`):

    python -m pytest MUDILAB_run/test_recupero_etichetta.py -v
"""
import csv
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))

import benchmark.valuta as V  # noqa: E402
import etichette as ET  # noqa: E402

MARCA_HELD_OUT = HERE / "risultati_misura" / "b_composta" / "20261102_191401"
GT = {r["task_id"]: r for r in csv.DictReader(
    (HERE / "benchmark" / "benchmark.csv").open(encoding="utf-8"))}


def _riga(task_id: str, risultato: dict) -> dict:
    """La riga che `_carica` costruisce dal JSON di un run, nella sua forma minima."""
    return {"variante": "b_composta", "task_id": task_id, "ripetizione": 1,
            "risultato": risultato, "rete": "consegna/insurance_grafo.bif",
            "rete_sha256": json.loads((HERE / "benchmark" / "manifest.json")
                                      .read_text(encoding="utf-8"))["reti"]["base"]["sha256"]}


# -- 1. il parser: prima per posizione, e il modulo resta puro ---------------------------

def test_prima_etichetta_per_posizione():
    """Vale la prima etichetta **per posizione nel testo**, non per intenzione.

    Il secondo assert e' il limite dichiarato del parser, fissato qui per non
    scoprirlo dopo: "not coherence, this is counterfactual" esce come
    `coherence`, perche' la ricerca e' per sottostringa e la negazione non si
    legge. E' la regola con cui sono stati prodotti i 240 run misurati, quindi
    cambiare qui sarebbe cambiare il metro a valle dei dati. Il testo ambiguo si
    vede in `etichette_nel_testo`, che restituisce tutte le citazioni.
    """
    assert ET.etichetta_dal_testo(
        "The label is: intervention, perche' la query nomina un intervento.") == "intervention"
    assert ET.etichetta_dal_testo("not coherence, this is counterfactual") == "coherence"
    assert ET.etichette_nel_testo("not coherence, this is counterfactual") == \
        ["coherence", "counterfactual"]


def test_etichetta_dal_testo_senza_etichette_solleva_e_non_solleva():
    """La variante `o_nulla` distingue "il passo non risponde" da "il passo non c'e'"."""
    with pytest.raises(ValueError):
        ET.etichetta_dal_testo("la domanda e' difficile")
    assert ET.etichetta_dal_testo_o_nulla("la domanda e' difficile") is None
    assert ET.etichetta_dal_testo_o_nulla("") is None
    assert ET.etichetta_dal_testo_o_nulla(None) is None


def test_il_modulo_puro_non_tira_giu_la_pipeline():
    """`etichette` non deve importare `run_orchestrato`: e' la ragione del modulo.

    Se un domani qualcuno rimettesse il parser in `run_orchestrato.py`, qui
    l'import di `run_orchestrato` risulterebbe fra i moduli caricati e il
    valutatore monterebbe le copie della relatrice (con `chdir` nella consegna)
    per leggere un JSON.
    """
    ET.etichetta_dal_testo("coherence")
    assert "run_orchestrato" not in sys.modules
    assert "run_query" not in sys.modules


# -- 2. la fonte dell'etichetta, sui casi che esistono davvero ----------------------------

def test_chiave_scritta_dal_run_ha_precedenza():
    r = {"etichetta": "Intervention", "steps": [
        {"step": "classificator", "text": "backward_reasoning"}]}
    assert V._etichetta_del_run(r) == ("intervention", "risultato")


def test_riga_fermata_del_gate_recupera_dal_passo():
    """Il caso dei 102 run held-out: nessun `etichetta`, ma il passo c'e' ed e' giusto.

    E' esattamente la forma del JSON scritto dal percorso d'errore di
    `run_orchestrato.run` prima della correzione del 02-11.
    """
    r = {"errore": "ValueError: controllo_traduzione: ...", "steps": [
        {"step": "translator", "text": "{...}"},
        {"step": "classificator", "text": "The label is: intervention, perche' nomina un intervento."}]}
    assert V._etichetta_del_run(r) == ("intervention", "passo")


def test_passo_che_non_cita_etichette():
    r = {"steps": [{"step": "classificator", "text": "non sono sicuro della forma"}]}
    assert V._etichetta_del_run(r) == ("", "passo-senza-etichetta")


def test_passo_classificator_assente_non_e_una_misura():
    """Un run morto prima del secondo passo non da' un voto al classificatore."""
    assert V._etichetta_del_run({"steps": [{"step": "translator", "text": "x"}]}) == ("", "assente")
    assert V._etichetta_del_run({}) == ("", "assente")


def test_chiave_etichetta_null_non_e_una_etichetta():
    """I JSON nuovi scrivono `etichetta: null` sul percorso d'errore: conta il passo."""
    r = {"etichetta": None, "steps": [{"step": "classificator", "text": "coherence"}]}
    assert V._etichetta_del_run(r) == ("coherence", "passo")


# -- 3. il metro: il punteggio non si muove -----------------------------------------------

def test_recupero_non_converte_un_rifiuto_inRisposta_corretta():
    """`corretta` richiede anche il numero: una riga fermata dal gate resta sbagliata."""
    task_id = "INT01"
    gt = GT[task_id]
    riga = _riga(task_id, {
        "errore": "ValueError: controllo_traduzione: citazione non presente nella query",
        "steps": [{"step": "classificator", "text": f"label: {gt['etichetta_attesa']}"}],
        "misura": {}, "totale": {}})
    esito = V._valuta_run(riga, gt, V._digest_accettati(
        HERE / "consegna" / "insurance_grafo.bif",
        json.loads((HERE / "benchmark" / "manifest.json").read_text(encoding="utf-8"))
        ["reti"]["base"]["sha256"]))
    assert esito["etichetta_fonte"] == "passo"
    assert esito["etichetta_ok"] is True
    assert esito["numero_ok"] is False
    assert esito["corretta"] is False


def test_etichetta_attesa_in_tutti_i_240_testi_registrati():
    """Il claim della correzione, misurato sugli artefatti dell'held-out.

    240 run su 240 hanno nel testo del passo l'etichetta attesa dal benchmark, e
    solo 138 portano la chiave `etichetta`: la differenza (102) e' il numero dei
    run fermati dal gate, non quello degli errori del classificatore. Se il test
    si spezza, o la marca non e' piu' quella misurata o il parser e' cambiato.
    """
    files = [p for p in sorted(MARCA_HELD_OUT.glob("*.json")) if p.name != "riepilogo.json"]
    assert len(files) == 240, f"attesi 240 JSON, trovati {len(files)}"
    con_passo = con_attesa = con_chiave = 0
    for p in files:
        d = json.loads(p.read_text(encoding="utf-8"))
        r = d.get("risultato") or {}
        passi = {s["step"]: s for s in (r.get("steps") or []) if "step" in s}
        if "classificator" not in passi:
            continue
        con_passo += 1
        et, fonte = V._etichetta_del_run(r)
        if et == GT[d["task_id"]]["etichetta_attesa"]:
            con_attesa += 1
        if fonte == "risultato":
            con_chiave += 1
    assert con_passo == 240
    assert con_attesa == 240
    assert con_chiave == 138
