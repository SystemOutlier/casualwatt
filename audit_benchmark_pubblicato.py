"""
Audit del benchmark pubblicato (run R20261019-164316-74070d).

Perche' esiste
--------------
Le sezioni "Risultati" della tesi (cap. 5) devono riportare J/token,
J/risposta corretta e gCO2e per query. L'unico dataset che la pipeline di
produzione ha pubblicato e' cwEnergyModular/results/semantic_evaluation_results.csv
(9 righe). Questo script non produce una metrica nuova: verifica, riga per riga,
COSA quel dataset puo' sostenere e cosa no, partendo solo dai campi grezzi.

Output: experiment_results/benchmark_prodotto_20261019_audit.json
Esecuzione: C:\\Users\\Massimo\\AppData\\Local\\Python\\pythoncore-3.14-64\\python.exe audit_benchmark_pubblicato.py

Nessun fattore correttivo, nessuna riscrittura a posteriori: se un numero non
e' calcolabile dai campi pubblicati viene marcato None con il motivo.
"""

from __future__ import annotations

import csv
import json
import statistics as st
import sys
from pathlib import Path

CSV_IN = Path("cwEnergyModular/results/semantic_evaluation_results.csv")
JSON_OUT = Path("experiment_results/benchmark_prodotto_20261019_audit.json")

# Involucro termico/elettrico OEM della macchina, ancorato a:
# experiment_results/lhm_gui_report_20261023_analisi.md:63 (hwinfo_idle_20261023_011237.csv)
PL1_W, PL2_W = 35.0, 55.0

# Potenza incrementale media misurata dal protocollo A-B-A rilanciato col backend
# corretto (experiment_results/lhm_validation_v3_20261023_153604.csv, P_load - P_base):
# usata SOLO come cross-check di plausibilita' sul medesimo chip, non come misura
# delle righe pubblicate (condizioni di carico diverse, dichiarato in tesi).
DP_PROTOCOLLO_W = 16.78

# Intensita' di carbonio: unico valore presente nel dataset (column locale).
CI_GCO2_KWH = 267.0
ZONA_CONFRONTO = {"FR": 55.0, "IT": 267.0, "DE": 396.0}


# ANNOTAZIONE MANUALE di correttezza, letta il 23/10/2026 riga per riga nel campo
# `model_response` contro `ground_truth` dello stesso CSV (test_source = manual,
# quindi item senza risposta automatica da confrontare). E' l'unica etichetta
# esterna al verifier in questo file e va trattata come tale: serve a misurare
# l'accordo fra verdetto del validatore e realta', non a sostituirla.
#   man-001 GT "21":  llama scrive "25 - 4 = 21 ... la risposta e': 21"  -> VERA
#                     nemotron scrive "5 * 4 = 20 ... the answer is 20"   -> FALSA
#                     tinyllama scrive "5*5-4 = 10*10 = 100 ... = 1"      -> FALSA
#   man-002 GT "Adolf": tutti e tre contengono "Adolf Hitler"            -> Vera
#   man-003 GT "Atene":   Atene / "Athens" (nemotron risponde in inglese) -> Vera
REALE = {
    ("llama3.2:3b-instruct-q4_K_M", "man-001"): True,
    ("llama3.2:3b-instruct-q4_K_M", "man-002"): True,
    ("llama3.2:3b-instruct-q4_K_M", "man-003"): True,
    ("nemotron-mini:latest", "man-001"): False,
    ("nemotron-mini:latest", "man-002"): True,
    ("nemotron-mini:latest", "man-003"): True,
    ("tinyllama:latest", "man-001"): False,
    ("tinyllama:latest", "man-002"): True,
    ("tinyllama:latest", "man-003"): True,
}


def f(x):
    """float() che non mente: ''/None -> None."""
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.upper() == "N/A":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def i(x):
    v = f(x)
    return None if v is None else int(v)


def frow(r: dict) -> dict:
    dur = f(r["duration_s"])
    pkg = f(r["package_energy_j"])
    baseline = f(r["baseline_energy_j"])
    active = f(r["active_energy_j"])
    local = f(r["local_energy_j"])
    e2e = f(r["end_to_end_energy_j"])
    n_in, n_out = i(r["input_tokens"]), i(r["output_tokens"])
    pre, dec = f(r["prefill_duration_s"]), f(r["decoding_duration_s"])
    cos = f(r["cosine_similarity"])
    soglia = f(r["semantic_threshold"])
    out = {
        "model": r["model_name"],
        "item": r["prompt_id"],
        "duration_s": dur,
        "prefill_s": pre,
        "decoding_s": dec,
        "residual_s": None if dur is None or pre is None or dec is None else round(dur - pre - dec, 6),
        "n_in": n_in,
        "n_out": n_out,
        "decode_tok_s": f(r["decoding_tokens_per_second"]),
        "package_energy_j": pkg,
        "baseline_energy_j": baseline,
        "active_energy_j": active,
        "local_energy_j": local,
        "end_to_end_energy_j": e2e,
        "package_w_impl": None if not pkg or not dur else round(pkg / dur, 3),
        "baseline_w_impl": None if not baseline or not dur else round(baseline / dur, 3),
        "package_w_sopra_pl2": None if not pkg or not dur else (pkg / dur > PL2_W),
        "j_per_token_pubbl": f(r["energy_per_output_token_j"]),
        "j_per_risposta_corretta_pubbl": f(r["energy_per_correct_answer_j"]),
        "ece_per_joule_pubbl": f(r["ece_per_joule"]),
        "epcl_j_per_link": (r["epcl_j_per_link"] or None),
        "cosine": cos,
        "soglia": soglia,
        "causal_accuracy": f(r["causal_accuracy"]),
        "acc_comp": f(r["acc_comp"]),
        "acc_comp_uguale_cosine": None if cos is None or f(r["acc_comp"]) is None else abs(f(r["acc_comp"]) - round(cos, 4)) < 5e-5,
        "n_correct_links": i(r["n_correct_links"]),
        "is_correct": r["is_correct"] == "True",
        "verdetto_equivalente_cosine_sopra_soglia": None if cos is None or soglia is None else (r["is_correct"] == "True") == (cos >= soglia),
        "gt": r["ground_truth"],
        "reale": REALE.get((r["model_name"], r["prompt_id"])),
        "risposta_contiene_gt": (r["ground_truth"] or "").lower() in (r["model_response"] or "").lower(),
        "idle_provenance": r["idle_provenance"],
        "idle_w": f(r["idle_power_w"]),
        "package_window_source": r["package_window_source"],
        "cpu_attribution_method": r["cpu_attribution_method"],
        "sample_count_dichiarato": None,
        "gco2eq": f(r["local_emissions_gco2eq"]),
        "cpu_time_share": f(r["cpu_time_share"]),
    }
    # n. campioni dichiarati nel campo measurement_boundary ("... over 30 samples @ 0.5s")
    mb = r["measurement_boundary"] or ""
    tok = mb.split()
    out["sample_count_dichiarato"] = next((int(t) for t, nxt in zip(tok, tok[1:]) if nxt == "samples"), None)
    # J/token attesi dal canale pulito, a solo titolo di plausibilita'
    if dur and n_out:
        out["j_token_atteso_da_delta_p"] = round(DP_PROTOCOLLO_W * dur / n_out, 4)
        out["fattore_pubbl_vs_atteso"] = (
            None if not out["j_per_token_pubbl"] else round(out["j_token_atteso_da_delta_p"] / out["j_per_token_pubbl"], 2)
        )
    return out


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = list(csv.DictReader(CSV_IN.open(encoding="utf-8-sig")))
    audit = [frow(r) for r in rows]

    models = sorted({a["model"] for a in audit})
    per_model = {}
    for m in models:
        s = [a for a in audit if a["model"] == m]
        per_model[m] = {
            "n_righe": len(s),
            "durata_mediana_s": round(st.median([a["duration_s"] for a in s]), 3),
            "decode_tok_s_mediano": round(st.median([a["decode_tok_s"] for a in s]), 3),
            "decode_tok_s_range": [min(a["decode_tok_s"] for a in s), max(a["decode_tok_s"] for a in s)],
            "n_in": sorted(a["n_in"] for a in s),
            "n_out": sorted(a["n_out"] for a in s),
            "cosine_mediane": round(st.median([a["cosine"] for a in s]), 4),
            "corrette_binario": sum(1 for a in s if a["is_correct"]),
            "active_nonzero": sum(1 for a in s if (a["active_energy_j"] or 0) > 0),
            "e2e_nonzero": sum(1 for a in s if (a["end_to_end_energy_j"] or 0) > 0),
        }

    rapporto = sorted(
        (a["decoding_s"] / a["n_out"]) / (a["prefill_s"] / a["n_in"]) for a in audit if a["prefill_s"] and a["decoding_s"]
    )

    sintesi = {
        "provenienza": {
            "file": str(CSV_IN),
            "n_righe": len(audit),
            "run_id_unichi": sorted({r["run_id"] for r in rows}),
            "ripetizioni_per_coppia_modello_item": "1 (nessuna ripetizione)",
            "finestra_temporale": [rows[0]["timestamp_start"], rows[-1]["timestamp_end"]],
        },
        "accuratezza": {
            "eval_mode": sorted({r["eval_mode"] for r in rows}),
            "eval_method": sorted({r["eval_method"] for r in rows}),
            "acc_uguale_cosine": sum(1 for a in audit if a["acc_comp_uguale_cosine"]),
            "verdetto_equivalente_a_cosine_sopra_soglia": sum(1 for a in audit if a["verdetto_equivalente_cosine_sopra_soglia"]),
            "epcl_mai_calcolato": sum(1 for a in audit if a["epcl_j_per_link"] in (None, "")),
            "gt_presente_nella_risposta_ma_marca_False": [
                {"model": a["model"], "item": a["item"], "cosine": a["cosine"]}
                for a in audit
                if a["risposta_contiene_gt"] and not a["is_correct"]
            ],
            "accuratezza_binaria_per_modello": {m: f"{per_model[m]['corrette_binario']}/3" for m in models},
        },
        "energia": {
            "active_nonzero": sum(1 for a in audit if (a["active_energy_j"] or 0) > 0),
            "package_nonzero": sum(1 for a in audit if (a["package_energy_j"] or 0) > 0),
            "package_null_o_zero_con_window_source": sorted(f"{a['package_window_source']}" for a in audit if not a["package_energy_j"]),
            "potenze_implicita_package_dur_w": sorted(a["package_w_impl"] for a in audit if a["package_w_impl"]),
            "potenze_implicit_sopra_pl2": sum(1 for a in audit if a["package_w_sopra_pl2"]),
            "pl1_pl2_w": [PL1_W, PL2_W],
            "j_per_token_pubblicati_nonzero": sorted(a["j_per_token_pubbl"] for a in audit if a["j_per_token_pubbl"]),
            "j_per_risposta_corretta_valori": sorted({str(a["j_per_risposta_corretta_pubbl"]) for a in audit}),
            "j_per_risposta_corretta_uguale_zero_su_verdetto_corretto": [
                {"model": a["model"], "item": a["item"]} for a in audit if a["is_correct"] and a["j_per_risposta_corretta_pubbl"] == 0.0
            ],
            "cross_check_atteso_vs_pubbl": [
                {"model": a["model"], "item": a["item"], "atteso": a.get("j_token_atteso_da_delta_p"),
                 "pubbl": a["j_per_token_pubbl"], "fattore": a.get("fattore_pubbl_vs_atteso")}
                for a in audit if a.get("fattore_pubbl_vs_atteso")
            ],
        },
        "geometria": {
            "n_in_min_max": [min(a["n_in"] for a in audit), max(a["n_in"] for a in audit)],
            "n_in_stesso_item_tra_modelli": {
                it: sorted(a["n_in"] for a in audit if a["item"] == it) for it in sorted({a["item"] for a in audit})
            },
            "prefill_decodifica": {
                "punto_interesse": "ms/token decode diviso ms/token prefill",
                "min": round(rapporto[0], 2), "mediano": round(st.median(rapporto), 2), "max": round(rapporto[-1], 2),
            },
            "residuo_durata_extra_s": sorted(round(a["residual_s"], 3) for a in audit if a["residual_s"] and a["residual_s"] > 1.0),
        },
        "domini_non_locali": {
            "cloud_energy_j_nonzero": sum(1 for a in audit if (f(next(r for r in rows if r["model_name"] == a["model"] and r["prompt_id"] == a["item"])["cloud_energy_j"]) or 0) > 0),
            "network_bytes_nonzero": sum(1 for r in rows if (f(r["network_total_bytes"]) or 0) > 0),
            "gpu_available_true": sum(1 for r in rows if r["gpu_available"] == "True"),
            "provider": sorted({r["provider"] for r in rows}),
        },
        "carbonio": {
            "intensita_unica_gco2_kwh": sorted({f(r["local_carbon_intensity_gco2eq_kwh"]) for r in rows}),
            "zona": sorted({r["local_carbon_intensity_zone"] for r in rows}),
            "fonte": sorted({r["local_carbon_intensity_source"] for r in rows}),
            "emissioni_nonzero": [a["gco2eq"] for a in audit if a["gco2eq"]],
            "sensibilita_zona_su_1000_token_al_jtoken": {
                zona: round(jtok * 1000 / 3.6e6 * ci, 5)
                for zona, ci in ZONA_CONFRONTO.items()
                for jtok in (1.2862,)
            },
        },
    }

    tp = sum(1 for a in audit if a["is_correct"] and a["reale"])
    fn = sum(1 for a in audit if not a["is_correct"] and a["reale"])
    fp = sum(1 for a in audit if a["is_correct"] and not a["reale"])
    tn = sum(1 for a in audit if not a["is_correct"] and not a["reale"])
    per_item = {
        it: [
            {"model": a["model"], "n_out": a["n_out"], "cosine": a["cosine"], "verdetto": a["is_correct"], "reale": a["reale"]}
            for a in audit if a["item"] == it
        ]
        for it in sorted({a["item"] for a in audit})
    }
    llama = [a for a in audit if a["model"].startswith("llama")]
    man001 = per_item["man-001"]
    sintesi["validatore_vs_realta_annotata"] = {
        "nota": "REALE = etichetta letta a mano dal campo model_response, non prodotta dal validatore",
        "TP": tp, "FN": fn, "FP": fp, "TN": tn,
        "accordo_verdetto_realta": round((tp + tn) / len(audit), 4),
        "recall": round(tp / (tp + fn), 4),
        "precisione": round(tp / (tp + fp), 4) if (tp + fp) else None,
        "per_modello": {
            m: {"reale": f"{sum(1 for a in audit if a['model']==m and a['reale'])}/3",
                "verdetto": f"{sum(1 for a in audit if a['model']==m and a['is_correct'])}/3"}
            for m in models
        },
        "per_item": per_item,
        "separazione_cosine_dentro_man-001": round(
            max(a["cosine"] for a in man001 if a["reale"]) - max(a["cosine"] for a in man001 if not a["reale"]), 4),
        "range_cosine_llama_tra_item": round(max(a["cosine"] for a in llama) - min(a["cosine"] for a in llama), 4),
    }
    sintesi["accuratezza"]["soglie_per_riga_uniche"] = sorted({a["soglia"] for a in audit})

    payload = {"sintesi": sintesi, "per_modello": per_model, "righe": audit}
    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(sintesi, ensure_ascii=False, indent=1))
    print(json.dumps(per_model, ensure_ascii=False, indent=1))
    print(f"scritto: {JSON_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
