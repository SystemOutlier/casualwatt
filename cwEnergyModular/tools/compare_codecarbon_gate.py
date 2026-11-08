# -*- coding: utf-8 -*-
"""tools/compare_codecarbon_gate.py — confronto diagnostico gate/CodeCarbon.

Perche' esiste. Il probe ``--codecarbon`` (commit del 2026-11-08) registra
una run CodeCarbon per blocco del gate P4.4. Questo modulo LEGGE dopo i
dati — ``analysis.json``, ``blocks_controllo.json``,
``control_power_series.json`` e gli artefatti in ``codecarbon/`` — e scrive
``codecarbon_confronto.md`` accanto ad essi, nella stessa directory di
campagna.

Cosa NON fa, per mandato. Non produce un secondo verdetto: l'esito del
gate resta quello di F.12 in ``analysis.json`` e qui e' solo citato. Non
corregge, non normalizza e non sostituisce nessuna grandezza del gate. Non
importa il runner ne' ``codecarbon``: legge file, e per questo funziona
anche su host dove la libreria non e' installata.

Allineamento temporale, dichiarato perche' e' un'approssimazione.
CodeCarbon pubblica una riga per run (inizio/fine = finestre wall del
probe), non una serie per campione. La finestra del controllo si ricava
dalla serie di potenza del gate: i campioni portano ``wall`` (epoch) e
``t`` (monotono), e i bordi ``t0_mono``/``t1_mono`` vengono proiettati
sull'orologio wall del campione piu' vicino — errore dell'ordine
dell'intervallo di campionamento (~0,5 s). L'energia CC "nello stesso
intervallo" NON e' una lettura: e' una STIMA a potenza costante sul blocco,
``P_media_blocco = cpu_energy/duration`` moltiplicata per i secondi di
sovrapposizione fra finestra del controllo e run CC. La sovrapposizione
puo' essere piena (finestra dentro la run), parziale o assente: nei tre
casi il confronto e' quantitativo, quantitativo-con-nota, o non fatto.

Avvertenze metrologiche obbligatorie nel report:
- su Windows 11 ``windows_emi`` legge lo stesso MSR 0x611 della catena
  ``emi-counter`` di CasualWatt: l'accordo e' coerenza di implementazione,
  non validazione indipendente; la scala assoluta resta non arbitrata
  senza wattmetro esterno;
- ``ram_energy`` e` un modello di stima (euristica DIMM), ``gpu_energy``
  vale 0 perche' nessun device NVML/AMD risponde su questo host: il totale
  ``energy_consumed`` include entrambi, quindi il confronto con il package
  CPU usa ``cpu_energy``, non il totale;
- ``pue`` e' dichiarato 1,0 dal probe (nessun fattore datacenter);
  CodeCarbon di default potrebbe applicarne e usare stime: qui la
  provenienza e' registrata riga per riga nello status;
- ``tracking_mode=machine``: i numeri CC sono della macchina intera, non
  del solo albero Ollama; la finestra CC copre l'intera invocazione
  (settle, calibrazioni, post-windows, cooldown), non la sola finestra
  passiva di ``dt_nominal_s``.

Uscita: 0 con report scritto (anche con status unavailable/partial — il
motivo ENTRA nel report); 2 con messaggio e senza file quando gli
artefatti necessari non ci sono (campagna senza flag, archivio assente,
analysis mancante).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
KWH_TO_J = 3.6e6

REPORT_NAME = "codecarbon_confronto.md"
STATUS_NAME = "codecarbon_status.json"
MANIFEST_NAME = "codecarbon_manifest.json"

FRASI_NESSUN_VERDETTO = (
    "Questo documento non contiene un secondo verdetto: l'esito del gate "
    "e' F.12 in analysis.json e qui e' soltanto citato. I numeri "
    "CodeCarbon non correggono, non normalizzano e non sostituiscono "
    "nessuna misura del percorso di misura."
)
FRASE_STIMA = (
    "L'energia CC nella finestra del controllo e' una STIMA a potenza "
    "costante sul blocco (cpu_energy/duration x secondi di "
    "sovrapposizione), non una lettura: la run CC copre l'intera "
    "invocazione, settle e cooldown inclusi."
)


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _carica(archivio: Path) -> Optional[Dict]:
    """Raccoglie gli artefatti. None = confronto non eseguibile, con la
    ragione stampata qui: i file obbligatori sono i tre del gate piu'
    status del probe. Il CSV non e' obbligatorio (una riga per stop()
    riuscito: con status unavailable non ci aspettiamo righe), e nemmeno
    il manifest — assente, ogni blocco risulta "run CC assente"."""
    mancanti = []
    for nome in ("analysis.json", "blocks_controllo.json",
                 "control_power_series.json"):
        if not (archivio / nome).exists():
            mancanti.append(nome)
    cc_dir = archivio / "codecarbon"
    if not (cc_dir / STATUS_NAME).exists():
        mancanti.append(f"codecarbon/{STATUS_NAME}")
    if mancanti:
        print(f"[ARRESTO] confronto non eseguibile, mancano: "
              f"{', '.join(mancanti)} — la campagna puo' essere stata "
              "eseguita senza --codecarbon, oppure l'archivio non e' "
              "quello giusto (--date/--archive)", flush=True)
        return None
    out = {"analysis": _json(archivio / "analysis.json"),
           "blocks": _json(archivio / "blocks_controllo.json"),
           "serie": _json(archivio / "control_power_series.json"),
           "status": _json(cc_dir / STATUS_NAME),
           "cc_dir": cc_dir}
    if (cc_dir / MANIFEST_NAME).exists():
        out["manifest"] = _json(cc_dir / MANIFEST_NAME)
    else:
        out["manifest"] = {"blocchi": []}
    return out


def _finestra_controllo(blocco_serie: Dict) -> Optional[Tuple[float, float]]:
    """Bordi wall della finestra passiva: t0_mono/t1_mono proiettati
    sull'orologio wall del campione piu' vicino. Serie assente o vuota ->
    None: senza bordi non c'e' allineamento da dichiarare, e il blocco
    finisce nel report come non allineabile, NON come finestra zero."""
    campioni = blocco_serie.get("samples") or []
    if not campioni:
        return None
    t0 = blocco_serie.get("t0_mono")
    t1 = blocco_serie.get("t1_mono")
    if t0 is None or t1 is None:
        return None
    try:
        p0 = min(campioni, key=lambda c: abs(c["t"] - t0))
        p1 = min(campioni, key=lambda c: abs(c["t"] - t1))
        w0, w1 = float(p0["wall"]), float(p1["wall"])
    except (KeyError, TypeError, ValueError):
        return None
    return (min(w0, w1), max(w0, w1))


def _sovrapposizione(fin: Optional[Tuple[float, float]],
                     run: Tuple[float, float]) -> Dict:
    """Tre stati dichiarati, non tre numeri e basta: piena (tipo
    "piena"), parziale ("parziale"), assente ("assente"). Il tipo finisce
    nel report perche' decide se il confronto e' quantitativo."""
    if fin is None:
        return {"overlap_s": None, "tipo": "non-allineabile",
                "motivo": "serie di controllo senza bordi wall"}
    a, b = max(fin[0], run[0]), min(fin[1], run[1])
    overlap = max(0.0, b - a)
    durata = max(0.0, fin[1] - fin[0])
    if overlap <= 0.0:
        return {"overlap_s": 0.0, "tipo": "assente",
                "motivo": "finestra del controllo fuori dalla run CC"}
    piena = overlap >= durata - 1e-6
    return {"overlap_s": overlap,
            "tipo": "piena" if piena else "parziale",
            "motivo": None}


def _confronta(data: Dict) -> List[Dict]:
    """Una riga per controllo di analysis: grandezze gate prese da
    analysis/blocks_controllo (E_net, dt_W, E_pkg_gross, baseline) e CC
    preso dal manifest del probe. JOIN: analysis.runs mette in relazione
    block_id (serie, blocks) con label (manifest)."""
    analisi = data["analysis"]
    blocks = {b["block_id"]: b for b in data["blocks"]}
    serie = {s["block_id"]: s for s in data["serie"]}
    cc_da_label = {b["block_id"]: b
                   for b in data["manifest"].get("blocchi", [])}
    intervallo_cc = data["status"].get("measure_power_secs_used")
    righe: List[Dict] = []
    for c in analisi.get("controls", []):
        bid = c.get("block_id", "")
        run = next((r for r in analisi.get("runs", [])
                    if r.get("block_id") == bid), None)
        label = run["label"] if run else ""
        cc = cc_da_label.get(label)
        riga: Dict = {"block_id": bid, "label": label, "pair_id":
                      c.get("pair_id"), "usable": c.get("usable"),
                      "e_net_j": c.get("e_net_j"),
                      "dt_w_s": c.get("dt_w_s"),
                      "budget_base_w": c.get("budget_base_w"),
                      "window_source": c.get("window_source")}
        blk = blocks.get(bid, {})
        riga["e_pkg_gross_j"] = blk.get("control_e_pkg_gross_j")
        riga["baseline_pre_w"] = blk.get("baseline_pre_w")
        if cc is None:
            riga["cc"] = None
            riga["allineamento"] = {"overlap_s": None,
                                    "tipo": "run CC assente",
                                    "motivo": "label non nel manifest"}
            righe.append(riga)
            continue
        riga["cc_stato_blocco"] = cc.get("block_status")
        run_dati = cc.get("run")
        if not run_dati or cc.get("block_status") != "ok":
            riga["cc"] = None
            riga["allineamento"] = {"overlap_s": None,
                                    "tipo": "senza dati",
                                    "motivo": cc.get("reason")}
            righe.append(riga)
            continue
        cpu_j = (run_dati.get("cpu_energy") or 0.0) * KWH_TO_J
        riga["cc"] = {
            "durata_s": run_dati.get("duration"),
            "cpu_energy_j": cpu_j,
            "gpu_energy_j": (run_dati.get("gpu_energy") or 0.0) * KWH_TO_J,
            "ram_energy_j": (run_dati.get("ram_energy") or 0.0) * KWH_TO_J,
            "energy_consumed_j":
                (run_dati.get("energy_consumed") or 0.0) * KWH_TO_J,
            "emissions_kg": run_dati.get("emissions"),
            "timestamp_end": run_dati.get("timestamp"),
            "run_id": run_dati.get("run_id"),
        }
        fin = _finestra_controllo(serie.get(bid, {}))
        allineamento = _sovrapposizione(
            fin, (cc["wall_start_s"], cc["wall_end_s"]))
        allineamento["finestra_wall_s"] = fin
        durata_run = run_dati.get("duration") or 0.0
        overlap = allineamento["overlap_s"]
        if overlap and durata_run > 0:
            p_media = cpu_j / durata_run
            allineamento["p_media_blocco_w"] = p_media
            allineamento["e_cc_stimata_j"] = p_media * overlap
            if riga["e_pkg_gross_j"] not in (None, ""):
                allineamento["scarto_j"] = (
                    float(riga["e_pkg_gross_j"]) - p_media * overlap)
        if (intervallo_cc is not None and riga["dt_w_s"] not in (None, "")
                and float(intervallo_cc) > float(riga["dt_w_s"])):
            allineamento["campionamento"] = (
                f"CC campiona ogni {intervallo_cc} s, la finestra e' "
                f"{riga['dt_w_s']} s: confronto QUALITATIVO, non di "
                "finestra")
        else:
            allineamento["campionamento"] = None
        riga["allineamento"] = allineamento
        righe.append(riga)
    return righe


def _v(x, fmt="{:.6f}"):
    try:
        return fmt.format(float(x))
    except (TypeError, ValueError):
        return "n/d"


def _markdown(data: Dict, righe: List[Dict], archivio: Path) -> str:
    analisi = data["analysis"]
    status = data["status"]
    parti: List[str] = []
    p = parti.append
    p("# Confronto diagnostico gate P4.4 / CodeCarbon\n\n")
    p(f"- archivio: `{archivio}`\n")
    p(f"- gate (F.12, citato senza toccarlo): status `{analisi.get('status')}`"
      f", bias_w = {_v(analisi.get('bias_w'))} W contro soglia "
      f"{_v(analisi.get('bias_threshold_w'))} W, quorum "
      f"{analisi.get('quorum')}/{analisi.get('n_pairs')}\n")
    p(f"- CodeCarbon: status `{status.get('codecarbon_status')}`, versione "
      f"{status.get('codecarbon_version')}, intervallo campionamento "
      f"{status.get('measure_power_secs_used')} s "
      f"(richiesto {status.get('measure_power_secs_requested')} s, fallback "
      f"{status.get('measure_power_secs_fallback')}), PUE "
      f"{status.get('pue')}, tracking_mode "
      f"`{status.get('tracking_mode')}`\n")
    if status.get("reason"):
        p(f"- motivo dichiarato dal probe: {status['reason']}\n")
    backend = status.get("backend") or {}
    p("\n## Cosa ha prodotto i numeri CC\n\n")
    p(f"- hardware: `{backend.get('hardware')}`\n")
    p(f"- CPU: modalita' `{backend.get('cpu_mode')}` — "
      f"{backend.get('cpu_kind')}\n")
    p(f"- RAM: {backend.get('ram')}\n")
    p(f"- GPU tracciata: {backend.get('gpu_tracciata')} "
      "(gpu_energy = 0 significa nessun device, non consumo zero)\n")
    if status.get("same_counter_caveat"):
        p(f"\n> **{status['same_counter_caveat']}**\n")
    p("\n## Perche' non e' una replica metrologica\n\n")
    p(f"- {FRASI_NESSUN_VERDETTO}\n")
    p(f"- {FRASE_STIMA}\n")
    p("- `energy_consumed` include RAM (modello) e GPU (assente qui): il "
      "confronto con il package CPU usa `cpu_energy`, non il totale.\n")
    p("- tracking_mode machine: la run CC copre l'intera invocazione "
      "(settle, calibrazioni, post-windows, cooldown), non la sola "
      "finestra passiva.\n")
    p("- allineamento dei bordi della finestra: proiezione di "
      "`t0_mono`/`t1_mono` sul campione wall piu' vicino, errore "
      "dell'intervallo di campionamento (~0,5 s).\n")
    p("\n## Blocchi di controllo\n\n")
    if not righe:
        p("Nessun controllo nell'analysis: confronto non applicabile.\n")
    for r in righe:
        a = r.get("allineamento") or {}
        cc = r.get("cc")
        p(f"\n### {r['label']} (`{r['block_id']}`)\n\n")
        p(f"- gate: usable={r['usable']}, E_net={_v(r['e_net_j'])} J su "
          f"dt_W={_v(r['dt_w_s'])} s, E_pkg_gross="
          f"{_v(r['e_pkg_gross_j'])} J, baseline_pre_w="
          f"{_v(r['baseline_pre_w'])} W, window="
          f"`{r['window_source']}`, budget_base_w="
          f"{_v(r['budget_base_w'])} W\n")
        if cc:
            p(f"- CC: run `{cc['run_id']}` durata {_v(cc['durata_s'])} s, "
              f"cpu_energy={_v(cc['cpu_energy_j'], '{:.3f}')} J, "
              f"gpu_energy={_v(cc['gpu_energy_j'], '{:.3f}')} J, "
              f"ram_energy={_v(cc['ram_energy_j'], '{:.3f}')} J "
              "(modello), energy_consumed="
              f"{_v(cc['energy_consumed_j'], '{:.3f}')} J, emissioni "
              f"{cc['emissions_kg']} kg CO2e, timestamp fine "
              f"`{cc['timestamp_end']}`\n")
        else:
            p(f"- CC: nessun numero per questo blocco "
              f"({a.get('tipo')}{', ' + str(a.get('motivo')) if a.get('motivo') else ''})\n")
        p(f"- allineamento: finestra wall "
          f"{a.get('finestra_wall_s')}, sovrapposizione "
          f"{_v(a.get('overlap_s'), '{:.2f}')} s, tipo `{a.get('tipo')}`\n")
        if a.get("e_cc_stimata_j") is not None:
            p(f"- stima CC nella finestra: {_v(a['p_media_blocco_w'])} W "
              f"x {_v(a.get('overlap_s'), '{:.2f}')} s = "
              f"{_v(a['e_cc_stimata_j'], '{:.3f}')} J contro "
              f"E_pkg_gross={_v(r['e_pkg_gross_j'])} J — scarto "
              f"{_v(a.get('scarto_j'), '{:+.3f}')} J\n")
        if a.get("campionamento"):
            p(f"- campionamento: {a['campionamento']}\n")
    p("\n---\n\n")
    p(f"File letto: `{archivio / 'codecarbon'}` (status, manifest, CSV "
      "delle run). Nessuna scrittura fuori da "
      f"`{archivio / REPORT_NAME}`.\n")
    return "".join(parti)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="confronto diagnostico gate P4.4 / CodeCarbon "
                    "(nessun secondo verdetto)")
    parser.add_argument("--date", default="20261109",
                        help="etichetta di campagna YYYYMMDD: l'archivio e' "
                             "experiment_results/p44_gate_<date>")
    parser.add_argument("--archive", default=None,
                        help="path esplicito dell'archivio, in alternativa "
                             "a --date")
    args = parser.parse_args(argv)
    if args.archive:
        archivio = Path(args.archive)
    else:
        if not re.fullmatch(r"\d{8}", args.date):
            raise SystemExit(f"--date vuole YYYYMMDD, non '{args.date}'")
        archivio = (REPO_ROOT / "experiment_results"
                    / f"p44_gate_{args.date}")
    data = _carica(archivio)
    if data is None:
        return 2
    righe = _confronta(data)
    testo = _markdown(data, righe, archivio)
    out = archivio / REPORT_NAME
    out.write_text(testo, encoding="utf-8")
    print(f"[OK] confronto scritto: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
