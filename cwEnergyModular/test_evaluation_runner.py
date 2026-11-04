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


def test_righe_senza_id_escluse_ma_contate():
    """Le righe aggregabili producono l'intervallo, quelle senza id restano conteggiate
    nella nota: escluderle in silenzio sposterebbe il denominatore senza dirlo."""
    rows = [
        {"end_to_end": "correct", "task_id": "T1"},
        {"end_to_end": "incorrect", "task_id": "T2"},
        {"end_to_end": "correct"},
    ]
    summary = summarize_records(rows)
    assert summary["n_effective_tasks"] == 2
    assert summary["n_determinate"] == 3
    assert ("righe senza id escluse dal ricampiono=1"
            in summary["cluster_bootstrap_note"])
