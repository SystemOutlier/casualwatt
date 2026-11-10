# -*- coding: utf-8 -*-
"""tools/report_carbon.py — CLI del report carbonio di sola analisi.

Legge un CSV misurato (non misura), converte l'energia in kWh e applica
fattori dichiarati con fonte; scrive report.json + report.tex rigenerabili.
Ogni emissione e' una STIMA, distinta dalla misura. Rifiuta con codice 2 se
i fattori o l'input non sono validi (nessun fallback silenzioso).
"""
import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(MODULE_DIR))
import carbon_report as cr


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Report carbonio (stima) sopra energia misurata.")
    p.add_argument("--input", required=True, help="CSV misurato da leggere")
    p.add_argument("--energy-column", default="ollama_active_energy_j")
    p.add_argument("--grid-intensity", type=float, required=True,
                   help="kg CO2eq/kWh, obbligatorio e dichiarato")
    p.add_argument("--grid-source", required=True, help="fonte del fattore (es. ISPRA + data)")
    p.add_argument("--pue", type=float, default=1.0)
    p.add_argument("--pue-source", default="host locale: nessun overhead datacenter")
    p.add_argument("--output-dir", default=None)
    args = p.parse_args(argv)

    try:
        factors = cr.CarbonFactors(args.grid_intensity, args.grid_source,
                                   args.pue, args.pue_source)
    except ValueError as exc:
        print(f"Fattori non validi: {exc}", file=sys.stderr)
        return 2

    in_path = Path(args.input)
    if not in_path.is_file():
        print(f"Input inesistente: {in_path}", file=sys.stderr)
        return 2

    with in_path.open(newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))

    provenance = {
        "input_csv": str(in_path),
        "input_csv_sha256": _sha256(in_path),
        "energy_column": args.energy_column,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
    }
    summary = cr.report_carbon(rows, factors, energy_column=args.energy_column,
                               input_provenance=provenance)

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = (MODULE_DIR.parent / "experiment_results"
                   / f"carbon_report_{datetime.now(timezone.utc):%Y%m%d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "report.tex").write_text(cr.render_latex(summary, factors), encoding="utf-8")

    m = summary["measured"]
    e = summary["estimate"]
    print(f"Righe: {m['n_rows']} ({m['n_ok']} ok, {m['n_excluded']} escluse)")
    print(f"Energia misurata: {m['energy_j_total']:.3f} J = {m['energy_kwh_total']:.6f} kWh")
    print(f"Emissioni (stima): {e['emissions_kg']:.6f} kg CO2eq")
    print(f"Output: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())