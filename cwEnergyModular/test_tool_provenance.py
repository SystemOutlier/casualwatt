"""B5: il percorso del tool non si deduce dalla coincidenza del numero finale."""
import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from mudilab_adapter import evaluate_case
from test_mudilab_adapter import _case, _passo, _TRADUZIONE

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("tool_trace", ROOT / "MUDILAB_run/tool_trace.py")
_trace = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_trace)


def _forwarded():
    call = {**_passo(), "call_id": "call-1"}
    output, proof = _trace.forward_tool_result(call)
    return call, output, proof


def _evaluate(call, output, proof=None, field="numero"):
    return evaluate_case(_case(), label="backward_reasoning", translation=_TRADUZIONE,
                         output=output, tool_calls=[call],
                         output_provenance=proof, output_field=field)


def test_coincidenza_numerica_non_dimostra_adozione():
    """Anche con args corretti e risposta identica manca la prova del forwarding."""
    call, output, _ = _forwarded()
    result = _evaluate(call, output)
    assert result.output.verdict == "correct"
    assert result.tool_call_valid is True
    assert result.tool_output_status == "acquired"
    assert result.tool_adoption_status == "not recorded"
    assert result.end_to_end == "indeterminate"


def test_forwarding_registrato_prova_il_flusso_non_il_ragionamento_llm():
    """La ricevuta nasce dall'assegnazione del testo: certifica il percorso software."""
    call, output, proof = _forwarded()
    result = _evaluate(call, output, proof)
    assert result.end_to_end == "correct"
    assert result.tool_adoption_status == "verified_direct_forward"
    assert result.to_dict()["llm_tool_use"] == "not_proven"


def test_ricevuta_non_si_trasferisce_alla_spiegazione():
    """Il campo numero e' inoltrato direttamente; causal_A non eredita la ricevuta."""
    call, output, proof = _forwarded()
    result = _evaluate(call, output, proof, field="causal_A")
    assert result.tool_adoption_status == "unverified"
    assert result.end_to_end == "indeterminate"


def test_testo_modificato_dopo_il_forwarding_non_passa():
    """Un digest non coincidente rileva l'alterazione, anche se la probabilita' e' uguale."""
    call, output, proof = _forwarded()
    result = _evaluate(call, output + " (mia ipotesi)", proof)
    assert result.tool_adoption_status == "mismatch"
    assert result.end_to_end == "incorrect"


def test_disponibilita_nel_prompt_non_e_uso_provato():
    """Registrare il risultato nel contesto LLM non dimostra una dipendenza causale."""
    call, output, proof = _forwarded()
    proof["mode"] = "llm_context"
    result = _evaluate(call, output, proof)
    assert result.tool_adoption_status == "unverified"
    assert result.end_to_end == "indeterminate"


def test_chiamate_multiple_non_mescolano_esecuzione_e_argomenti():
    """Senza call-id selezionato non si combinano prove provenienti da call diversi."""
    call, output, proof = _forwarded()
    wrong = {**_passo(args_label="intervention"), "call_id": "call-2"}
    result = evaluate_case(_case(), label="backward_reasoning", translation=_TRADUZIONE,
                          output=output, tool_calls=[wrong, call],
                          output_provenance=proof, output_field="numero")
    assert result.end_to_end == "correct"
    proof["call_id"] = "call-2"
    result = evaluate_case(_case(), label="backward_reasoning", translation=_TRADUZIONE,
                          output=output, tool_calls=[wrong, call],
                          output_provenance=proof, output_field="numero")
    assert result.end_to_end == "incorrect"
    assert result.tool_arguments_status == "mismatch"


def test_call_id_duplicati_non_sono_prova_univoca():
    """Una ricevuta con due sorgenti possibili resta non verificabile."""
    call, output, proof = _forwarded()
    result = evaluate_case(_case(), label="backward_reasoning", translation=_TRADUZIONE,
                          output=output, tool_calls=[call, call],
                          output_provenance=proof, output_field="numero")
    assert result.end_to_end == "indeterminate"
    assert result.tool_adoption_status == "unverified"


def test_cli_legge_numero_e_ricevuta_dal_record_dell_orchestratore(tmp_path, capsys):
    """La CLI deve leggere il record come lo scrive `run_orchestrato`: `numero`,
    `etichetta`, `traduzione`, `steps` e `output_provenance`. Se leggesse solo
    i nomi inglesi, un run reale arriverebbe con output vuoto e la ricevuta
    non verrebbe mai usata: il test passa dai file, non dalle funzioni."""
    import csv
    import sys
    from mudilab_eval import main

    call = {**_passo(), "call_id": "cau_inference:0"}
    output, proof = _trace.forward_tool_result(call)
    truth = tmp_path / "truth.csv"
    with truth.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "task_id", "task_type", "expected_probability",
            "expected_lower_graph", "expected_upper_graph", "target_variable",
            "target_state", "evidence_json", "intervention_json"])
        writer.writeheader()
        writer.writerow({
            "task_id": "CP1", "task_type": "cond_prob",
            "expected_probability": "0.2117494190",
            "expected_lower_graph": "0.0827", "expected_upper_graph": "0.2396",
            "target_variable": "Age", "target_state": "Senior",
            "evidence_json": json.dumps({"DrivQuality": "Normal"}),
            "intervention_json": json.dumps({"RiskAversion": "Cautious"}),
        })
    source = tmp_path / "run.jsonl"
    source.write_text(json.dumps({
        "task_id": "CP1", "etichetta": "backward_reasoning",
        "traduzione": _TRADUZIONE, "numero": output,
        "steps": [call], "output_provenance": proof,
        "llm_tool_use": "not_proven",
    }) + "\n", encoding="utf-8")
    evaluated = tmp_path / "evaluated.jsonl"
    summary = tmp_path / "summary.json"
    argv = sys.argv
    sys.argv = ["mudilab_eval", "--ground-truth", str(truth),
                "--input", str(source), "--output", str(evaluated),
                "--summary", str(summary)]
    try:
        assert main() == 0
    finally:
        sys.argv = argv
    records = [json.loads(line) for line in evaluated.read_text(encoding="utf-8").splitlines()]
    assert records[0]["end_to_end"] == "correct"
    assert records[0]["tool_adoption_status"] == "verified_direct_forward"
    assert records[0]["llm_tool_use"] == "not_proven"
    assert json.loads(summary.read_text(encoding="utf-8"))["n_correct"] == 1
    assert "n_correct" in capsys.readouterr().out

    """Si esegue il corpo run con agenti/tool finti, senza l'import che monta Ollama.

    Il test collega la ricevuta al call davvero fatto dal corpo di produzione,
    non a un record scritto separatamente dal test.
    """
    path = ROOT / "MUDILAB_run/run_orchestrato.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    run = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "run")
    class Agent:
        async def run(self, *args, **kwargs):
            return SimpleNamespace(text="fake")
    class Meter:
        def bordo(self):
            return 0
        def riga(self, *args):
            return {}
        def riepilogo(self):
            return {}
    async def step(meter, name, awaitable):
        value = await awaitable
        return value, {"step": name, "text": value.text, "misura": {}}
    received = []
    def inference(*args):
        received.append(args)
        return "The probability is 0.212"
    env = dict(Misura=Meter, OPZIONI={}, RISCALDA=False,
               rq=SimpleNamespace(ACTIVE_MODEL="fake", SOURCE="fake"),
               MODELLO_SPIEGAZIONE="fake", time=__import__("time"), json=json,
               agenti=SimpleNamespace(translator_senza_tool=Agent(), classificator=Agent()),
               tools=SimpleNamespace(cau_inference=SimpleNamespace(func=inference)),
               _passo=step, etichetta_dal_testo=lambda _: "backward_reasoning",
               etichette_nel_testo=lambda _: ["backward_reasoning"],
               dizionario_dal_testo=lambda _: _TRADUZIONE,
               forward_tool_result=_trace.forward_tool_result)
    exec(compile(ast.Module(body=[run], type_ignores=[]), str(path), "exec"), env)
    record = asyncio.run(env["run"]("query", Meter(), spiegazione=False))
    assert received == [("backward_reasoning", json.dumps(_TRADUZIONE), None)]
    result = evaluate_case(_case(), label=record["etichetta"], translation=record["traduzione"],
                          output=record["numero"], tool_calls=record["steps"],
                          output_provenance=record["output_provenance"], output_field="numero")
    assert result.end_to_end == "correct"
    assert record["llm_tool_use"] == "not_proven"
