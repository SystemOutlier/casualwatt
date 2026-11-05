from evaluation_runner import summarize_records


def test_summary_rejects_non_finite_energy_and_reports_wilson_interval():
    """`NaN` e `inf` non sono misure: finiscono fra gli invalidi, non nella mediana.

    Con tre righe (12,0 J; `NaN`; `None`) la mediana dell'energia e' quella della
    sola riga valida, mentre `n_invalid_or_missing_energy = 2` dice quante sono
    cadute; una `NaN` nella mediana la renderebbe `NaN` per tutte le righe e un
    `inf` la porterebbe a infinito senza che il conto lo dichiari. La durata segue
    la stessa regola e l'accuratezza resta sul denominatore dei determinati con il
    suo intervallo di Wilson.
    """
    rows = [
        {"end_to_end": "correct", "energy_j": 12.0, "duration_s": 2.0},
        {"end_to_end": "incorrect", "energy_j": float("nan"), "duration_s": float("inf")},
        {"end_to_end": "indeterminate", "energy_j": None, "duration_s": 1.0},
    ]
    summary = summarize_records(rows)
    assert summary["n_total"] == 3
    assert summary["n_determinate"] == 2
    assert summary["accuracy_on_determinate"] == 0.5
    assert summary["accuracy_wilson_95"] is not None
    assert summary["n_invalid_or_missing_energy"] == 2
    assert summary["n_invalid_or_missing_duration"] == 1
    assert summary["median_energy_correct_j"] == 12.0


def test_summary_keeps_negative_energy_observable():
    """Un'energia negativa si conserva: e' un'incoerenza da vedere, non da azzerare.

    `-0,2 J` e' sotto il pavimento di risoluzione del contatore o la traccia di una
    baseline mal calibrata, e in entrambi i casi e' un'informazione sulla misura;
    un clamp a zero nasconderebbe il difetto dentro un valore plausibile. La
    mediana la riporta con il segno.
    """
    rows = [
        {"end_to_end": "correct", "energy_j": -0.2, "duration_s": 1.0},
    ]
    summary = summarize_records(rows)
    assert summary["median_energy_j"] == -0.2


def test_bootstrap_a_cluster_allarga_quando_le_righe_non_sono_indipendenti():
    """Venti righe da DUE task non sono venti prove: l'unita' statistica e' il task.

    Dieci risposte sempre giuste dello stesso task e dieci sempre sbagliate di un
    altro danno accuratezza 0,5 su `n_determinate = 20`, e la Wilson dice circa
    `[0,296; 0,697]` perche' tratta le venti righe come bernoulli indipendenti.
    Ricampionando i task, pero', ogni ricampiono estrae o tutti-corretti o
    tutti-sbagliati o meta' e meta': l'intervallo onesto e' `[0,0; 1,0]`, perche'
    l'evidenza disponibile sono DUE esperimenti, non venti. `n_effective_tasks`
    e' il numero che la riga nascondeva.
    """
    rows = ([{"end_to_end": "correct", "task_id": "T1"}] * 10 +
            [{"end_to_end": "incorrect", "task_id": "T2"}] * 10)
    summary = summarize_records(rows)
    assert summary["n_determinate"] == 20
    assert summary["n_effective_tasks"] == 2
    wilson = summary["accuracy_wilson_95"]
    bootstrap = summary["accuracy_cluster_bootstrap_95"]
    assert bootstrap == [0.0, 1.0]
    assert bootstrap[0] < wilson[0] and bootstrap[1] > wilson[1]


def test_un_solo_task_non_produce_un_intervallo():
    """Con un solo cluster la dispersione del bootstrap e' zero per costruzione:
    pubblicarla come intervallo vorrebbe dire claimare certezza da un task."""
    rows = [{"end_to_end": "correct", "task_id": "T1"}] * 5
    summary = summarize_records(rows)
    assert summary["n_effective_tasks"] == 1
    assert summary["accuracy_cluster_bootstrap_95"] is None
    assert "one distinct task" in summary["cluster_bootstrap_note"]
    # la Wilson a livello di riga resta pubblicata: sono due dichiarazioni, non
    # l'una il sostituto dell'altra
    assert summary["accuracy_wilson_95"] is not None


def test_identita_del_task_assente_e_dichiarata():
    """Senza `task_id` non si puo' raggruppare: l'assenza va detta, non numerata."""
    rows = [{"end_to_end": "correct"}, {"end_to_end": "incorrect"}]
    summary = summarize_records(rows)
    assert summary["accuracy_cluster_bootstrap_95"] is None
    assert summary["n_effective_tasks"] == 0
    assert "task identity not recorded" in summary["cluster_bootstrap_note"]


def test_identita_parziale_non_produce_un_intervallo():
    """Togliere righe senza id cambierebbe il denominatore rispetto all'accuratezza:
    si conta la lacuna ma non si pubblica un CI su una popolazione diversa."""
    rows = [
        {"end_to_end": "correct", "task_id": "T1"},
        {"end_to_end": "incorrect", "task_id": "T2"},
        {"end_to_end": "correct"},
    ]
    summary = summarize_records(rows)
    assert summary["n_effective_tasks"] == 2
    assert summary["n_determinate"] == 3
    assert summary["accuracy_cluster_bootstrap_95"] is None
    assert summary["n_determinate_without_task_id"] == 1
    assert "missing for 1 determinate row" in summary["cluster_bootstrap_note"]


def test_csv_preserva_identita_esplicita_non_indici(tmp_path):
    """Riordino e ripetizioni non cambiano l'ID sorgente; prompt_id resta un indice."""
    from test_source import load_prompts_from_csv, parse_manual_prompts
    path = tmp_path / "tasks.csv"
    path.write_text("task_id,prompt,ground_truth\nB,due?,2\nA,uno?,1\nB,due?,2\n", encoding="utf-8")
    items, error = load_prompts_from_csv(path)
    assert not error
    assert [x["task_id"] for x in items] == ["B", "A", "B"]
    assert items[0]["id"] != items[2]["id"]
    assert parse_manual_prompts("uno? / 1")[0]["task_id"] is None
    path.write_text("prompt,ground_truth\nuno?,1\n", encoding="utf-8")
    assert load_prompts_from_csv(path)[0][0]["task_id"] is None


def test_task_id_con_contratti_diversi_e_errore(tmp_path):
    """Un ID riusato per due domande non e' un cluster statisticamente identificato."""
    from test_source import load_prompts_from_csv
    path = tmp_path / "tasks.csv"
    path.write_text("task_id,prompt,ground_truth\nA,uno?,1\nA,due?,2\n", encoding="utf-8")
    rows, error = load_prompts_from_csv(path)
    assert rows == []
    assert "contratti diversi" in error


def test_task_id_attraversa_csv_senza_colonne_nuove(tmp_path, monkeypatch):
    """Il writer conserva l'ID esplicito nelle notes P5, uguale attraverso modelli."""
    import benchmark_unified as bu
    from evaluator import evaluate_skipped
    from casualwatt_csv_export import CSV_COLUMNS, export_results_csv
    from evaluation_runner import read_csv, record_task_id
    from types import SimpleNamespace
    monkeypatch.setattr(bu, "get_carbon_intensity", lambda: SimpleNamespace(
        gco2eq_per_kwh=100, zone="test", source="test", timestamp=0))
    records = []
    for model in ("A", "B"):
        for identity, answer in (("task;\"1", 1), ("task2", 0)):
            record = bu._basic_record("r", "s", model, model, "ollama", "local", None,
                {"id": "csv-001", "text": "domanda", "task_id": identity}, evaluate_skipped("test"))
            record.update(is_correct=answer, notes="nota originale")
            records.append(record)
    path = tmp_path / "results.csv"
    export_results_csv(records, path, mode="w")
    rows = read_csv(path)
    assert list(rows[0]) == CSV_COLUMNS
    assert len(CSV_COLUMNS) == 174
    assert [record_task_id(row) for row in rows] == [r["task_id"] for r in records]
    for model in ("A", "B"):
        result = summarize_records([r for r in rows if r["model_name"] == model])
        assert result["n_effective_tasks"] == 2
        assert result["accuracy_cluster_bootstrap_95"] == [0.0, 1.0]
    assert records[0]["notes"] == "nota originale"


def test_prompt_id_e_identita_vuota_non_sono_task_id():
    """Gli indici legacy e gli spazi non diventano cluster per ottenere un CI."""
    rows = [{"is_correct": "True", "prompt_id": "man-001", "task_id": "  "},
            {"is_correct": "False", "prompt_id": "man-002"}]
    summary = summarize_records(rows)
    assert summary["n_determinate"] == 2
    assert summary["n_effective_tasks"] == 0
    assert summary["accuracy_cluster_bootstrap_95"] is None


def test_metadati_task_conflittuali_non_vengono_scelti():
    """Due identita' discordanti sono una lacuna, non una scelta dell'ultima."""
    from evaluation_runner import record_task_id
    assert record_task_id({"task_id": "A", "notes": 'CW_TASK_ID_V1="B"'}) is None


def test_runner_carica_i_task_prima_di_stimare_la_durata(monkeypatch):
    """La chiamata al loader deve essere raggiungibile: total_tasks non esiste prima."""
    import benchmark_unified as bu
    import test_source
    import pytest
    class StopBeforeMeasurement(BaseException):
        pass
    def loader(**kwargs):
        raise StopBeforeMeasurement()
    monkeypatch.setattr(test_source, "load_test_source", loader)
    with pytest.raises(StopBeforeMeasurement):
        bu.run_unified_benchmark(local_models=[], cloud_selection=[])

