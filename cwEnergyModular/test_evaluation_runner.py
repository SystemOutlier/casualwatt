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
