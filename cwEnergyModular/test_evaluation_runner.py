import pytest

from evaluation_runner import summarize_records, summarize_unified_records


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


def test_costo_aggregato_usa_tutti_i_tentativi_non_la_mediana_delle_corrette():
    """B8: 12 J corretti, 8 J sbagliati, 5 J indeterminati = 25 J per UNA corretta.

    La mediana delle sole corrette resta 12 J come diagnostica, ma non e' il
    costo per risposta corretta: quella definizione escluderebbe l'energia spesa
    negli errori, che e' un costo realmente sostenuto.
    """
    rows = [
        {"end_to_end": "correct", "energy_j": 12.0},
        {"end_to_end": "incorrect", "energy_j": 8.0},
        {"end_to_end": "indeterminate", "energy_j": 5.0},
    ]
    summary = summarize_records(rows)
    assert summary["total_energy_j"] == 25.0
    assert summary["n_correct"] == 1
    assert summary["energy_per_correct_j"] == 25.0
    assert summary["median_energy_correct_j"] == 12.0
    assert summary["energy_per_correct_j"] != summary["median_energy_correct_j"]


def test_zero_corrette_non_define_un_costo():
    """Senza corrette il rapporto non esiste: None con la ragione, mai infinito o zero."""
    rows = [
        {"end_to_end": "incorrect", "energy_j": 8.0},
        {"end_to_end": "indeterminate", "energy_j": 5.0},
    ]
    summary = summarize_records(rows)
    assert summary["total_energy_j"] == 13.0
    assert summary["n_correct"] == 0
    assert summary["energy_per_correct_j"] is None
    assert "zero correct answers" in summary["energy_per_correct_reason"]


def test_copertura_parziale_usa_tutte_le_corrette_al_denominatore():
    """15 J disponibili su due corrette, una senza energia: 5 J per corretta,
    con status partial. Escludere la corretta senza energia gonfierebbe la stima."""
    rows = [
        {"end_to_end": "correct", "energy_j": 10.0},
        {"end_to_end": "correct", "energy_j": None},
        {"end_to_end": "incorrect", "energy_j": 5.0},
    ]
    summary = summarize_records(rows)
    assert summary["total_energy_j"] == 15.0
    assert summary["n_correct"] == 2
    assert summary["energy_per_correct_j"] == 7.5
    assert summary["energy_status"] == "partial"
    assert "available subtotal" in summary["energy_reason"]


def test_energia_negativa_o_invalida_non_entra_nel_consumo():
    """I negativi restano nelle mediane diagnostiche ma non si sommano come
    energia consumata; un flag falso o una finestra invalida escludono la riga."""
    rows = [
        {"end_to_end": "correct", "energy_j": 10.0, "active_valid": True},
        {"end_to_end": "incorrect", "energy_j": -2.0, "active_valid": True},
        {"end_to_end": "incorrect", "energy_j": 3.0, "active_valid": False},
        {"end_to_end": "incorrect", "energy_j": 4.0, "active_valid": True,
         "package_window_source": "counter-invalid"},
        {"end_to_end": "incorrect", "energy_j": None},
        {"end_to_end": "incorrect", "energy_j": float("nan")},
    ]
    summary = summarize_records(rows)
    assert summary["total_energy_j"] == 10.0
    assert summary["n_available_energy"] == 1
    assert summary["n_negative_energy"] == 1
    # Mediana diagnostica di [-2, 3, 4, 10]: il negativo resta nell'ordinamento.
    assert summary["median_energy_j"] == 3.5
    assert summary["energy_exclusion_counts"]["negative_not_consumed"] == 1
    assert summary["energy_exclusion_counts"]["validity_flag_false"] == 1
    assert summary["energy_exclusion_counts"]["package_window_invalid_or_unavailable"] == 1
    assert summary["energy_exclusion_counts"]["nonfinite_or_nonnumeric"] == 1
    assert summary["energy_exclusion_counts"]["missing"] == 1


def test_unified_senza_active_valid_non_entra_nel_totale():
    """Il CSV unificato non prova che la sottrazione della baseline sia valida:
    l'assenza di active_valid rende la riga non verificabile, non la promuove."""
    rows = [
        {"end_to_end": "correct", "end_to_end_energy_j": 10.0, "active_valid": "True"},
        {"end_to_end": "correct", "end_to_end_energy_j": 5.0},
    ]
    summary = summarize_records(rows, energy_key="end_to_end_energy_j")
    assert summary["total_energy_j"] == 10.0
    assert summary["n_available_energy"] == 1
    assert summary["energy_exclusion_counts"]["validity_unverifiable"] == 1
    assert summary["energy_status"] == "partial"


def test_energia_generica_senza_flag_resta_compatibile_e_dichiarata():
    """`energy_j` storico non ha flag: il valore finito si accetta per compatibilita',
    ma la riga dichiara che la validita' metrologica non e' provata."""
    summary = summarize_records([{"end_to_end": "correct", "energy_j": 10.0}])
    assert summary["total_energy_j"] == 10.0
    assert summary["n_compatibility_energy"] == 1
    assert summary["n_unverified_energy_validity"] == 1


def test_gruppi_unified_separano_run_modello_e_perimetro():
    """Due modelli non sono un solo aggregato: ogni gruppo ha il proprio costo
    per corretta e i propri metodi registrati."""
    base = {"run_id": "r1", "session_id": "s1", "provider": "ollama",
            "mode": "local", "active_valid": "True", "eval_method": "exact"}
    rows = [
        {**base, "model_name": "A", "end_to_end": "correct",
         "end_to_end_energy_j": 10.0},
        {**base, "model_name": "A", "end_to_end": "incorrect",
         "end_to_end_energy_j": 5.0},
        {**base, "model_name": "B", "end_to_end": "correct",
         "end_to_end_energy_j": 20.0},
    ]
    groups = summarize_unified_records(rows)
    assert len(groups) == 2
    by_model = {group["model_name"]: group for group in groups}
    assert by_model["A"]["energy_per_correct_j"] == 15.0
    assert by_model["B"]["energy_per_correct_j"] == 20.0
    assert by_model["A"]["correctness_metadata"]["eval_method"] == {"exact": 2}


def test_ledger_di_un_tentativo_fallito_non_inventa_zero():
    """Un'eccezione dopo la valutazione conserva verdetto ed energia gia' misurata;
    l'assenza di componenti cloud resta N/A e la ragione finisce nella riga."""
    from types import SimpleNamespace
    import benchmark_unified as bu
    rec = {"mode": "cloud", "notes": "", "output_tokens": 10,
           "local_carbon_intensity_gco2eq_kwh": 0}
    ev = SimpleNamespace(
        is_correct=1, eval_mode="ground_truth", eval_method="exact_number_match",
        causal_accuracy=1.0, explanation_quality=None, cosine_sim=None,
        n_correct_links=None, acc_comp=1.0, answer_type="number",
        extracted_answer="21", semantic_similarity=None, lexical_similarity=None,
        semantic_threshold="", acc_links_basis="exact_number_match",
        triples_gt=None, triples_response=None, triples_matched=None,
        f1_precision=None, f1_recall=None, judge_model=None, evaluated_model=None,
        judge_equals_evaluated=None, judge_source=None, notes=())
    local_j, network_j, cloud_j = bu._failed_cloud_components(rec, {})
    assert (local_j, network_j, cloud_j) == (None, None, None)
    bu._finalize_failed_attempt(rec, RuntimeError("rete"), ev, local_j, network_j, cloud_j)
    assert rec["is_correct"] == 1
    assert rec["end_to_end_energy_j"] == "N/A"
    assert rec["request_error"] == "RuntimeError: rete"
    assert "tentativo cloud incompleto" in rec["notes"]


def test_recupero_tentativo_locale_conserva_il_profilo_disponibile():
    """Se la richiesta fallisce dopo l'inferenza, la finestra fino all'errore
    viene profilata e dichiarata parziale: non si riscrive zero."""
    from types import SimpleNamespace
    import benchmark_unified as bu
    profiler = SimpleNamespace(profile_window=lambda a, b: SimpleNamespace(
        ollama_active_energy_j=3.0, gpu_energy_attributed_j=2.0,
        active_valid=True, cpu_time_share_valid=True,
        notes=["profilo parziale"], package_energy_j=5.0))
    rec = {"notes": ""}
    value = bu._recover_local_attempt(rec, None, None, 1.0, 2.0, profiler)
    assert value == 5.0
    assert rec["duration_s"] == 1.0
    assert "profilo del tentativo incompleto" in rec["notes"]
    assert "profilo parziale" in rec["notes"]


def test_tentativo_senza_profilo_non_inventa_zero():
    """Se nemmeno la finestra e' profilabile l'energia resta None, con la ragione."""
    from types import SimpleNamespace
    import benchmark_unified as bu
    profiler = SimpleNamespace(profile_window=lambda a, b: (_ for _ in ()).throw(
        RuntimeError("contatore assente")))
    rec = {"notes": ""}
    assert bu._recover_local_attempt(rec, None, None, 2.0, 2.0, profiler) is None
    assert "nessuno zero inventato" in rec["notes"]


def test_runner_pubblica_il_costo_aggregato_e_i_gruppi():
    """Il riepilogo della run porta lo stesso costo aggregato del runner e i
    gruppi per sistema: il numeratore e' l'energia di tutti i tentativi, il
    denominatore tutte le corrette, senza rivalutare le risposte."""
    import benchmark_unified as bu
    base = {"run_id": "r1", "session_id": "s1", "provider": "ollama",
            "mode": "local", "active_valid": "True", "notes": ""}
    records = [
        {**base, "model_name": "A", "task_id": "t1", "is_correct": 1,
         "end_to_end_energy_j": 10.0},
        {**base, "model_name": "A", "task_id": "t2", "is_correct": 0,
         "end_to_end_energy_j": 5.0},
        {**base, "model_name": "B", "task_id": "t1", "is_correct": 1,
         "end_to_end_energy_j": 20.0},
        {**base, "model_name": "B", "task_id": "t2", "is_correct": 0,
         "end_to_end_energy_j": 20.0},
    ]
    summary = bu._attach_evaluation_summary({}, records)
    assert summary["evaluation"]["energy_per_correct_j"] == pytest.approx(27.5)
    assert summary["evaluation"]["energy_status"] == "complete"
    gruppi = {(g["model_name"]): g for g in summary["evaluation_groups"]}
    assert gruppi["A"]["energy_per_correct_j"] == pytest.approx(15.0)
    assert gruppi["B"]["energy_per_correct_j"] == pytest.approx(40.0)
    # il gruppo non rivaluta: due righe determinate per sistema, una corretta
    assert gruppi["A"]["n_determinate"] == 2
    assert gruppi["A"]["n_correct"] == 1


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

