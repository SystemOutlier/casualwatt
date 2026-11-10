# Reporter carbonio di sola analisi — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere un layer di sola analisi che produce un report carbonio/emissioni (JSON + LaTeX) sopra l'energia misurata, con formula kWh corretta e fattori dichiarati con fonte, senza toccare il percorso di misura.

**Architecture:** Modulo puro `cwEnergyModular/carbon_report.py` (registro di `surface_fit.py`/`geometry.py`/`control_gate.py`: non importato dal runner, non tocca lo schema P5, non dipende da `SESSION`) + CLI sottile `cwEnergyModular/tools/report_carbon.py` che legge un CSV misurato e scrive l'artefatto rigenerabile. TDD, un commit per punto.

**Tech Stack:** Python stdlib (`csv`, `json`, `hashlib`, `math`, `dataclasses`, `datetime`, `pathlib`, `argparse`, `typing`); pytest per i test. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-11-10-carbon-report-analysis-design.md`

**Working directory (tutti i comandi):** `C:/Users/Massimo/Documents/CasualWatt/carbon-report-analysis` — il worktree isolato su `feat/carbon-report-analysis-20261110`, da HEAD pulito `6a17ca78e`. NON lavorare nel checkout principale `CWProject` (lì c'è lavoro concorrente di un'altra sessione).

## Global Constraints

- Schema P5 congelato: `CSV_COLUMNS` resta a **174** nomi; nessuna colonna nuova.
- `carbon_report.py` NON importa il runner né `SESSION`; non è chiamato dal percorso di misura.
- Formula: `E_kWh = E_J / 3_600_000.0`; `emissions_kg = E_kWh * PUE * grid_intensity_kg_per_kwh`.
- Fattori dichiarati, mai inventati: `grid_intensity_kg_per_kwh` obbligatorio, finito, `> 0`, con `grid_source` non vuoto; `pue` default **1.0** (host locale), finito, `> 0`.
- Nessun fallback silenzioso; nessun `try/except` che nasconde errori; nessuna soglia spostata.
- Delta negativi conservati firmati, mai clampati; energia assente/non finita → riga esclusa con ragione dichiarata, mai zero inventato.
- Ogni emissione è etichettata **«stima»**, distinta dall'energia misurata.
- Suite: `python -m pytest cwEnergyModular` dalla radice del worktree (MAI pytest nudo dalla radice del repo principale).
- Baseline costante del worktree: `2 failed, 1155 passed, 4 skipped`. I 2 falliti sono artefatti CRLF (`tests/test_preflight_gate_p44.py:271`, `tests/test_run_gate_p44_metrologico.py:111`). Criterio: **nessun fallimento nuovo** oltre i 2 costanti.
- Un commit per punto; MAI `git push`; MAI `git add -A`/`git add .` (aggiungere percorsi espliciti).
- Prosa italiana; identificatori/token/campi in inglese. Ogni test ha docstring che dice *perché* esiste.

---

### Task 1: Factors, conversione kWh e formula di emissione

**Files:**
- Create: `cwEnergyModular/carbon_report.py`
- Test: `cwEnergyModular/tests/test_carbon_report.py`

**Interfaces:**
- Consumes: nulla (primo task).
- Produces: `JOULE_PER_KWH: float = 3_600_000.0`; `CarbonFactors(grid_intensity_kg_per_kwh: float, grid_source: str, pue: float = 1.0, pue_source: str = "host locale: nessun overhead datacenter")` (frozen dataclass, `__post_init__` solleva `ValueError` se non valido); `joule_to_kwh(energy_j: float) -> float`; `estimate_emissions_kg(energy_kwh: float, *, grid_intensity_kg_per_kwh: float, pue: float = 1.0) -> float`.

- [ ] **Step 1: Write the failing test**

Creare `cwEnergyModular/tests/test_carbon_report.py`:

```python
# -*- coding: utf-8 -*-
"""Guardie del reporter carbonio di sola analisi.

Il modulo esiste per produrre un report emissioni SOPRA l'energia misurata,
con la formula kWh corretta e fattori dichiarati. Il bug del modulo mock
(energy/carbon_emissions.py, non tracciato) era un fattore 1000x: usava i Wh
come kWh. Qui si fissano la conversione, la formula e il rifiuto dei fattori
non dichiarati.
"""
import math

import pytest

from carbon_report import (
    JOULE_PER_KWH,
    CarbonFactors,
    estimate_emissions_kg,
    joule_to_kwh,
)


def test_joule_to_kwh_un_kwh():
    """3.6e6 J sono esattamente 1 kWh: e' la conversione che il mock sbagliava."""
    assert JOULE_PER_KWH == 3_600_000.0
    assert joule_to_kwh(3_600_000.0) == pytest.approx(1.0)
    assert joule_to_kwh(0.0) == 0.0


def test_joule_to_kwh_negativo_conservato():
    """Il segno si conserva: un delta negativo non si clampа (regola del progetto)."""
    assert joule_to_kwh(-3_600_000.0) == pytest.approx(-1.0)


def test_regressione_fattore_mille():
    """0.1 kWh con PUE 1.2 e rete 0.5 kg/kWh danno 0.06 kg, NON 60 kg.

    E' il bug del mock (Wh usati come kWh), fissato da un test: 360000 J =
    0.1 kWh, e 0.1 * 1.2 * 0.5 = 0.06.
    """
    energy_kwh = joule_to_kwh(360_000.0)
    assert energy_kwh == pytest.approx(0.1)
    assert estimate_emissions_kg(
        energy_kwh, grid_intensity_kg_per_kwh=0.5, pue=1.2
    ) == pytest.approx(0.06)


def test_pue_default_locale():
    """Il default PUE e' 1.0 (host locale), non 1.2 da datacenter."""
    f = CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="ISPRA 2025")
    assert f.pue == 1.0


@pytest.mark.parametrize("grid", [None, float("nan"), float("inf"), 0.0, -0.1])
def test_intensita_rete_non_valida_rifiutata(grid):
    """Intensita' assente/non finita/<=0: rifiuto dichiarato, nessun default."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=grid, grid_source="ISPRA 2025")


def test_fonte_rete_vuota_rifiutata():
    """La fonte e' obbligatoria: un fattore senza provenienza non entra."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="")


def test_pue_non_valido_rifiutato():
    """PUE non finito o <=0 e' un errore dichiarato."""
    with pytest.raises(ValueError):
        CarbonFactors(grid_intensity_kg_per_kwh=0.3, grid_source="ISPRA", pue=0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'carbon_report'` (collection error).

- [ ] **Step 3: Write minimal implementation**

Creare `cwEnergyModular/carbon_report.py`:

```python
# -*- coding: utf-8 -*-
"""carbon_report — report carbonio di sola analisi sopra energia misurata.

Modulo di analisi (registro di surface_fit.py / geometry.py / control_gate.py):
non e' chiamato dal runner, non tocca lo schema P5 (CSV_COLUMNS resta 174),
non dipende da SESSION. Converte l'energia misurata in kWh e applica fattori
dichiarati con fonte; ogni emissione e' una STIMA, distinta dalla misura.
"""
import math
from dataclasses import dataclass

JOULE_PER_KWH = 3_600_000.0


@dataclass(frozen=True)
class CarbonFactors:
    """Fattori dichiarati del report. Nessuno e' inventato: la fonte della
    intensita' di rete e' obbligatoria; il PUE di default e' 1.0 (host locale,
    nessun overhead da datacenter)."""
    grid_intensity_kg_per_kwh: float
    grid_source: str
    pue: float = 1.0
    pue_source: str = "host locale: nessun overhead datacenter"

    def __post_init__(self):
        g = self.grid_intensity_kg_per_kwh
        if g is None or not isinstance(g, (int, float)) or not math.isfinite(g) or g <= 0:
            raise ValueError("intensita' di rete obbligatoria, finita e > 0")
        if not self.grid_source or not str(self.grid_source).strip():
            raise ValueError("fonte dell'intensita' di rete obbligatoria")
        if not isinstance(self.pue, (int, float)) or not math.isfinite(self.pue) or self.pue <= 0:
            raise ValueError("PUE finito e > 0")


def joule_to_kwh(energy_j: float) -> float:
    """Converte J in kWh (1 kWh = 3.6e6 J). Il segno si conserva."""
    return energy_j / JOULE_PER_KWH


def estimate_emissions_kg(energy_kwh: float, *, grid_intensity_kg_per_kwh: float,
                          pue: float = 1.0) -> float:
    """Emissioni stimate: E_kWh * PUE * intensita' di rete (kg CO2eq/kWh)."""
    return energy_kwh * pue * grid_intensity_kg_per_kwh
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: PASS (12 passed: 3 + 1 + 1 + 5 parametrizzati + 1 + 1).

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/carbon_report.py cwEnergyModular/tests/test_carbon_report.py
git commit -m "feat(analysis): carbon_report, formula kWh corretta e fattori dichiarati"
```

---

### Task 2: Report per riga e aggregato con provenance

**Files:**
- Modify: `cwEnergyModular/carbon_report.py` (aggiunge `CarbonRowResult`, `_parse_energy`, `report_carbon`)
- Test: `cwEnergyModular/tests/test_carbon_report.py` (aggiunge i test)

**Interfaces:**
- Consumes: `CarbonFactors`, `joule_to_kwh`, `estimate_emissions_kg` (Task 1).
- Produces: `CarbonRowResult(energy_j_measured: Optional[float], energy_kwh: Optional[float], emissions_kg_estimate: Optional[float], status: str, reason: str)` (dataclass); `report_carbon(rows: Iterable[dict], factors: CarbonFactors, *, energy_column: str, input_provenance: dict) -> dict`. Il dict ha chiavi: `label` ("stima"), `measured` (`energy_j_total`, `energy_kwh_total`, `n_rows`, `n_ok`, `n_excluded`, `excluded_reasons`), `factors` (`pue`, `pue_source`, `grid_intensity_kg_per_kwh`, `grid_source`), `estimate` (`emissions_kg`), `provenance` (input + `module`, `formula`), `rows` (lista di dict).

- [ ] **Step 1: Write the failing test**

Aggiungere a `cwEnergyModular/tests/test_carbon_report.py` (import `report_carbon` e `CarbonRowResult` nella lista di import da `carbon_report`):

```python
def _provenance():
    return {"input_csv": "in.csv", "input_csv_sha256": "abc",
            "energy_column": "ollama_active_energy_j", "generated_utc": "2026-11-10T00:00:00+00:00"}


def test_report_aggrega_sole_righe_valide():
    """Il totale somma le sole righe ok; le escluse sono conteggiate con ragione."""
    factors = CarbonFactors(0.5, "ISPRA", pue=1.2)
    rows = [{"ollama_active_energy_j": "360000"},
            {"ollama_active_energy_j": ""},
            {"ollama_active_energy_j": "nan"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["label"] == "stima"
    assert s["measured"]["n_rows"] == 3
    assert s["measured"]["n_ok"] == 1
    assert s["measured"]["n_excluded"] == 2
    assert s["measured"]["energy_j_total"] == pytest.approx(360000.0)
    assert s["estimate"]["emissions_kg"] == pytest.approx(0.06)
    assert sum(s["measured"]["excluded_reasons"].values()) == 2


def test_report_energia_negativa_conservata():
    """Un delta negativo resta firmato, non clampato: l'emissione puo' essere negativa."""
    factors = CarbonFactors(0.5, "ISPRA", pue=1.0)
    rows = [{"ollama_active_energy_j": "-360000"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["measured"]["n_ok"] == 1
    assert s["measured"]["energy_j_total"] == pytest.approx(-360000.0)
    assert s["estimate"]["emissions_kg"] == pytest.approx(-0.05)


def test_report_riga_esclusa_ha_ragione():
    """Ogni esclusione dichiara la sua ragione, non sparisce in silenzio."""
    factors = CarbonFactors(0.5, "ISPRA")
    rows = [{"ollama_active_energy_j": "abc"}, {"ollama_active_energy_j": "inf"}]
    s = report_carbon(rows, factors, energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["measured"]["n_ok"] == 0
    statuses = [r["status"] for r in s["rows"]]
    assert statuses == ["excluded", "excluded"]
    assert all(r["reason"] for r in s["rows"])


def test_report_provenance_e_label():
    """La provenance porta sha256, fattori con fonte e etichetta 'stima'."""
    factors = CarbonFactors(0.3, "ISPRA 2025")
    s = report_carbon([{"ollama_active_energy_j": "3600000"}], factors,
                      energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    assert s["label"] == "stima"
    assert s["provenance"]["input_csv_sha256"] == "abc"
    assert s["provenance"]["module"] == "carbon_report"
    assert s["factors"]["grid_source"] == "ISPRA 2025"
    assert s["factors"]["pue"] == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: FAIL — `ImportError: cannot import name 'report_carbon'`.

- [ ] **Step 3: Write minimal implementation**

Aggiungere a `cwEnergyModular/carbon_report.py` (in testa: `from dataclasses import dataclass, asdict`, `from typing import Iterable, Optional, Tuple`):

```python
@dataclass
class CarbonRowResult:
    """Esito di una riga: energia misurata (firmata) e stima, o esclusione
    dichiarata. status e' 'ok' oppure 'excluded'; reason e' vuota se ok."""
    energy_j_measured: Optional[float]
    energy_kwh: Optional[float]
    emissions_kg_estimate: Optional[float]
    status: str
    reason: str


def _parse_energy(raw) -> Tuple[Optional[float], str]:
    """Estrae l'energia in J da un valore di riga. Ritorna (valore, '') se
    valida, (None, ragione) se assente/non numerica/non finita. Il segno si
    conserva."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "energia assente"
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None, "energia non numerica"
    if not math.isfinite(val):
        return None, "energia non finita"
    return val, ""


def report_carbon(rows: Iterable[dict], factors: CarbonFactors, *,
                  energy_column: str, input_provenance: dict) -> dict:
    """Report di sola analisi: legge righe gia' parsate, non misura. Somma le
    sole righe valide; le escluse sono conteggiate con la loro ragione."""
    results = []
    reasons: dict = {}
    sum_j = 0.0
    n_ok = 0
    n_excluded = 0
    for row in rows:
        val, reason = _parse_energy(row.get(energy_column))
        if val is None:
            n_excluded += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            results.append(CarbonRowResult(None, None, None, "excluded", reason))
            continue
        kwh = joule_to_kwh(val)
        em = estimate_emissions_kg(
            kwh, grid_intensity_kg_per_kwh=factors.grid_intensity_kg_per_kwh,
            pue=factors.pue)
        sum_j += val
        n_ok += 1
        results.append(CarbonRowResult(val, kwh, em, "ok", ""))
    total_kwh = joule_to_kwh(sum_j)
    total_em = estimate_emissions_kg(
        total_kwh, grid_intensity_kg_per_kwh=factors.grid_intensity_kg_per_kwh,
        pue=factors.pue)
    return {
        "label": "stima",
        "measured": {
            "energy_j_total": sum_j,
            "energy_kwh_total": total_kwh,
            "n_rows": n_ok + n_excluded,
            "n_ok": n_ok,
            "n_excluded": n_excluded,
            "excluded_reasons": reasons,
        },
        "factors": {
            "pue": factors.pue,
            "pue_source": factors.pue_source,
            "grid_intensity_kg_per_kwh": factors.grid_intensity_kg_per_kwh,
            "grid_source": factors.grid_source,
        },
        "estimate": {"emissions_kg": total_em},
        "provenance": {**input_provenance, "module": "carbon_report",
                       "formula": "E_J/3.6e6 * PUE * grid"},
        "rows": [asdict(r) for r in results],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: PASS (16 passed: i 12 del Task 1 + 4 nuovi).

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/carbon_report.py cwEnergyModular/tests/test_carbon_report.py
git commit -m "feat(analysis): report_carbon per riga e aggregato con provenance"
```

---

### Task 3: Rendering LaTeX ed equivalenze illustrative

**Files:**
- Modify: `cwEnergyModular/carbon_report.py` (aggiunge `render_latex`, `illustrative_equivalences`)
- Test: `cwEnergyModular/tests/test_carbon_report.py` (aggiunge i test)

**Interfaces:**
- Consumes: `report_carbon`, `CarbonFactors` (Task 1-2).
- Produces: `render_latex(summary: dict, factors: CarbonFactors) -> str`; `illustrative_equivalences(emissions_kg: float, factors_eq: dict) -> list`. `factors_eq` mappa label → `{"kg_per_unit": float, "unit": str}`.

- [ ] **Step 1: Write the failing test**

Aggiungere a `cwEnergyModular/tests/test_carbon_report.py` (import `render_latex`, `illustrative_equivalences`):

```python
def test_latex_contiene_formula_parametri_e_stima():
    """Il template LaTeX dichiara formula, fattori con fonte e l'etichetta
    'stima': e' il pezzo pronto per la tesi, distinto dalla misura."""
    factors = CarbonFactors(0.3, "ISPRA 2025", pue=1.0)
    s = report_carbon([{"ollama_active_energy_j": "3600000"}], factors,
                      energy_column="ollama_active_energy_j",
                      input_provenance=_provenance())
    tex = render_latex(s, factors)
    assert "stima" in tex
    assert "Energia misurata" in tex
    assert "ISPRA 2025" in tex
    assert "PUE" in tex
    assert "3.6" in tex  # la conversione J -> kWh nella formula


def test_equivalenze_solo_con_fattori_dichiarati():
    """Le equivalenze sono illustrative e solo con fattori dichiarati."""
    eq = {"auto": {"kg_per_unit": 0.12, "unit": "km"}}
    out = illustrative_equivalences(0.06, eq)
    assert len(out) == 1
    assert "illustrativo" in out[0]
    assert "km" in out[0]
    assert illustrative_equivalences(0.06, {}) == []


def test_equivalenze_fattore_non_valido_saltato():
    """Un fattore illustrativo nullo/non finito non produce una riga."""
    eq = {"x": {"kg_per_unit": 0.0, "unit": "u"},
          "y": {"kg_per_unit": float("nan"), "unit": "v"}}
    assert illustrative_equivalences(0.06, eq) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: FAIL — `ImportError: cannot import name 'render_latex'`.

- [ ] **Step 3: Write minimal implementation**

Aggiungere a `cwEnergyModular/carbon_report.py`:

```python
def render_latex(summary: dict, factors: CarbonFactors) -> str:
    """Template LaTeX alla ML CO2 Impact: formula, fattori dichiarati con
    fonte, misurato e stimato distinti. Pronto per la tesi."""
    m = summary["measured"]
    e = summary["estimate"]
    lines = [
        "% Report carbonio di sola analisi -- etichetta: stima",
        "\\subsection{Emissioni carbonio (stima)}",
        "L'energia misurata e' convertita in kWh e moltiplicata per i fattori dichiarati:",
        "\\begin{equation}",
        "\\text{Emissioni} = \\frac{E_J}{3.6\\times 10^6} \\times \\text{PUE} \\times \\text{intensita' di rete}",
        "\\end{equation}",
        "\\begin{itemize}",
        f"  \\item Energia misurata: {m['energy_j_total']:.3f} J = {m['energy_kwh_total']:.6f} kWh "
        f"({m['n_ok']} righe valide, {m['n_excluded']} escluse)",
        f"  \\item PUE: {factors.pue:.3f} ({factors.pue_source})",
        f"  \\item Intensita' di rete: {factors.grid_intensity_kg_per_kwh:.4f} kg CO2eq/kWh ({factors.grid_source})",
        f"  \\item Emissioni (stima): {e['emissions_kg']:.6f} kg CO2eq",
        "\\end{itemize}",
        "I fattori sono assunzioni dichiarate; la scala assoluta del contatore non e' arbitrata "
        "senza un wattmetro AC/DC esterno.",
    ]
    return "\n".join(lines)


def illustrative_equivalences(emissions_kg: float, factors_eq: dict) -> list:
    """Equivalenze divulgative (km auto, ...), solo con fattori dichiarati e
    marcate 'illustrativo'. factors_eq: label -> {'kg_per_unit': float, 'unit': str}."""
    out = []
    for label, spec in factors_eq.items():
        f = spec.get("kg_per_unit")
        unit = spec.get("unit", "")
        if isinstance(f, (int, float)) and math.isfinite(f) and f > 0:
            out.append(f"{emissions_kg / f:.3f} {unit} ({label}, illustrativo)")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest cwEnergyModular/tests/test_carbon_report.py -q`
Expected: PASS (19 passed: i 16 del Task 2 + 3 nuovi).

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/carbon_report.py cwEnergyModular/tests/test_carbon_report.py
git commit -m "feat(analysis): template LaTeX ed equivalenze illustrative dichiarate"
```

---

### Task 4: CLI rigenerabile `tools/report_carbon.py`

**Files:**
- Create: `cwEnergyModular/tools/report_carbon.py`
- Test: `cwEnergyModular/tests/test_report_carbon_cli.py`

**Interfaces:**
- Consumes: `carbon_report.CarbonFactors`, `report_carbon`, `render_latex` (Task 1-3).
- Produces: `main(argv: Optional[Sequence[str]] = None) -> int` (0 ok, 2 fattori/input non validi); scrive `report.json` + `report.tex` in `--output-dir`. Import del modulo via `sys.path.insert(0, str(MODULE_DIR))` con `MODULE_DIR = Path(__file__).resolve().parent.parent` (convenzione di `tools/run_gate_p44.py:151`).

- [ ] **Step 1: Write the failing test**

Creare `cwEnergyModular/tests/test_report_carbon_cli.py`:

```python
# -*- coding: utf-8 -*-
"""Guardie della CLI report_carbon.

La CLI esiste perche' la tesi deve poter RIGENERARE il numero del report
(regola: un'analisi non tracciata e' un numero che nessuno puo' rigenerare).
Qui si verifica il percorso end-to-end su un CSV minimo e il rifiuto
dichiarato quando i fattori non sono validi.
"""
import importlib.util
import json
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parent.parent / "tools" / "report_carbon.py"
_spec = importlib.util.spec_from_file_location("report_carbon", TOOL)
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)


def _csv(tmp_path):
    p = tmp_path / "in.csv"
    p.write_text("ollama_active_energy_j\n360000\n", encoding="utf-8")
    return p


def test_cli_end_to_end(tmp_path):
    """360000 J = 0.1 kWh; con PUE 1.2 e rete 0.5 -> 0.06 kg. Scrive JSON+LaTeX
    con provenance (sha256) ed etichetta 'stima'."""
    out_dir = tmp_path / "out"
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "0.5",
                   "--grid-source", "ISPRA", "--pue", "1.2",
                   "--output-dir", str(out_dir)])
    assert rc == 0
    data = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
    assert data["label"] == "stima"
    assert data["estimate"]["emissions_kg"] == pytest.approx(0.06)
    assert data["provenance"]["input_csv_sha256"]
    assert (out_dir / "report.tex").exists()


def test_cli_rifiuta_intensita_non_finita(tmp_path):
    """Intensita' non finita: rifiuto dichiarato, codice 2, nessun output."""
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "nan",
                   "--grid-source", "ISPRA", "--output-dir", str(tmp_path / "o")])
    assert rc == 2


def test_cli_rifiuta_fonte_vuota(tmp_path):
    """Fonte vuota: il fattore non ha provenienza, rifiuto con codice 2."""
    rc = cli.main(["--input", str(_csv(tmp_path)), "--grid-intensity", "0.5",
                   "--grid-source", "", "--output-dir", str(tmp_path / "o")])
    assert rc == 2


def test_cli_input_inesistente(tmp_path):
    """Input inesistente: errore dichiarato, codice 2."""
    rc = cli.main(["--input", str(tmp_path / "no.csv"), "--grid-intensity", "0.5",
                   "--grid-source", "ISPRA", "--output-dir", str(tmp_path / "o")])
    assert rc == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest cwEnergyModular/tests/test_report_carbon_cli.py -q`
Expected: FAIL — il file `tools/report_carbon.py` non esiste (collection error: FileNotFoundError sul TOOL).

- [ ] **Step 3: Write minimal implementation**

Creare `cwEnergyModular/tools/report_carbon.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest cwEnergyModular/tests/test_report_carbon_cli.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add cwEnergyModular/tools/report_carbon.py cwEnergyModular/tests/test_report_carbon_cli.py
git commit -m "feat(tool): CLI report_carbon per artefatto rigenerabile"
```

---

### Task 5: Verifica della suite intera (gate di accettazione)

**Files:**
- Modify: nessuno (sola verifica).

**Interfaces:**
- Consumes: tutto il lavoro dei Task 1-4.
- Produces: evidenza che la suite non ha fallimenti nuovi oltre i 2 costanti del checkout.

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest cwEnergyModular -q --tb=line`
Expected: `2 failed, 1178 passed, 4 skipped` (i 1155 della baseline + 19 del modulo + 4 della CLI = 1178). I 2 falliti DEVONO essere esattamente `tests/test_preflight_gate_p44.py::test_preflight_reale_piano_terza_campagna` e `tests/test_run_gate_p44_metrologico.py::test_dt_nominal_frozen_coerente_con_csv_pilota` (artefatti CRLF). Se compare un fallito DIVERSO, fermarsi e investigare.

- [ ] **Step 2: Confirm the two failures are the known CRLF artifacts**

Run: `python -m pytest cwEnergyModular/tests/test_preflight_gate_p44.py::test_preflight_reale_piano_terza_campagna cwEnergyModular/tests/test_run_gate_p44_metrologico.py::test_dt_nominal_frozen_coerente_con_csv_pilota -q --tb=line`
Expected: 2 failed, con assertion sugli SHA-256 (`99846365…`/`009c01d2…` e `e8fbfab…`/`e2e56a6d…`). Sono i byte su disco CRLF vs blob registrati, non difetti di codice.

- [ ] **Step 3: Paste full output and report**

Incollare l'output intero della suite (regola del progetto: output pytest per intero, non riassunto). Riportare il conteggio e confermare che i 2 falliti sono i costanti. Nessun commit qui (non c'è modifica).

---

## Self-review (eseguita dall'autore del piano)

**Copertura spec:**
- Sez. 3 (architettura: modulo + CLI, analysis-only) → Task 1-4. ✓
- Sez. 4 (formula kWh, PUE 1.0, grid obbligatoria con fonte, equivalenze) → Task 1 (formula/fattori), Task 3 (equivalenze). ✓
- Sez. 5 (input CSV, output JSON/LaTeX, provenance, CLI) → Task 2 (JSON/provenance), Task 3 (LaTeX), Task 4 (CLI/CSV/sha256). ✓
- Sez. 6 (error handling: non finiti esclusi con ragione, negativo firmato, rifiuto fattori, no fallback) → Task 1 (rifiuto), Task 2 (esclusioni/segno), Task 4 (rifiuto CLI). ✓
- Sez. 7 (test TDD, regressione 1000×, baseline) → Task 1-5. ✓
- Sez. 8 (commit per punto) → 4 commit feat + verifica. ✓
- Sez. 9 (fuori perimetro: schema 174, no runner/SESSION) → Global Constraints + nessun task tocca runner/schema. ✓

**Placeholder scan:** nessun TBD/TODO; ogni step di codice ha il blocco completo. ✓

**Type consistency:** `CarbonFactors`, `joule_to_kwh`, `estimate_emissions_kg`, `CarbonRowResult`, `report_carbon`, `render_latex`, `illustrative_equivalences`, `main` — nomi e firme coerenti fra Tasks 1-4. Le chiavi del dict (`label`, `measured`, `factors`, `estimate`, `provenance`, `rows`) usate identicamente in Task 2 (produzione), Task 3 (render_latex) e Task 4 (CLI/test). ✓

**Conteggio test:** Task 1 = 12 (3+1+1+5+1+1), Task 2 = +4 → 16, Task 3 = +3 → 19, Task 4 = +4 (file separato). Totale nuovi = 23. Baseline 1155 → 1178 passed. ✓