# -*- coding: utf-8 -*-
"""srum.py — lettura del dump SRUM di Windows (`powercfg /srumutil`) come fonte
di energia *per processo* nativa, da confrontare con il contatore EMI.

Cosa e' SRUM: System Resource Usage Monitor, database storico di Windows
(SoftwareDistribution/Srum), esportabile con `powercfg /srumutil /output <csv>`.
Richiede AMMINISTRATORE: senza elevazione il comando fallisce con
`0x1f` + "SruUpdateStats failed, status 5" (misurato 23/10/2026, probe in
experiment_results/alternative_sources_probe_20261023_115948.txt).

Colonne che ci interessano (dump reale su MINI_IT13, 23/10/2026):
  CPUEnergyConsumption, EmiEnergyConsumption, TotalEnergyConsumption,
  TimeInMSec, AppId, TimeStamp.
Su questa macchina i campi energia SONO popolati (31726/31726 righe non zero),
nonostante il PC non abbia batteria — fatto non ovvio e verificato, non assunto.

WARNING di metodologia:
* **colonna `TimeStamp` = UTC naive, non orario locale.** Misurato 23/10/2026:
  dump preso alle 12:14 locali contieneva come bucket piu' recente le 10:13 ->
  121 min di "lag" se interpretato locale, **1,4 min se interpretato UTC**
  (offset della macchina 2:00:00). Non e' un archivio in ritardo: e' vivo a
  granularita' ~1 minuto. Chi confronta finestre deve usare
  :func:`utc_now_naive`, altrimenti la finestra e' vuota per 2 ore.
* i valori sono nella scala interna di Windows (millijoule, da confermare contro
  EMI sulla stessa finestra: e' esattamente lo scopo di srum_emi_cross.py);
* `powercfg /srumutil` FORNISCE un flush e costa CPU: va chiamato solo ai confini
  di fase, mai nel tick, e il suo costo va dichiarato;
* la ripartizione per processo e' prodotta dal modello EPI di Windows (eventualmente
  ancorato alle misure EMI): e' un *terminale di confronto*, non un arbitro.
"""
from __future__ import annotations

import csv
import datetime
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

#: campi che sommiamo quando ci serve "quanta energia ha usato X"
ENERGY_FIELDS = (
    "CPUEnergyConsumption",
    "EmiEnergyConsumption",
    "TotalEnergyConsumption",
    "TimeInMSec",
)


def utc_now_naive() -> datetime.datetime:
    """Ora in formato UTC naive: stessa base della colonna TimeStamp dei dump."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def flush(out_csv: Path, timeout_s: float = 120.0) -> Optional[Path]:
    """Esegue `powercfg /srumutil /output out_csv` e ritorna il path se scritto.

    Ritorna None (con motivo nel log di chiama) se il processo non e' elevato.
    """
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    if out_csv.exists():
        out_csv.unlink()
    try:
        r = subprocess.run(
            ["powercfg", "/srumutil", f"/output", str(out_csv)],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except Exception as exc:  # pragma: no cover
        print(f"[SRUM] flush eccezione: {type(exc).__name__}: {exc}")
        return None
    if not out_csv.exists():
        print("[SRUM] flush SENZA CSV: " + (r.stdout + r.stderr).strip().replace("\n", " "))
        return None
    return out_csv


def load(csv_path: Path) -> "SrumDump":
    """Legge un dump SRUM. Il dump reale usa separatori '; ' con spazi: normalizziamo."""
    rows: List[Dict[str, str]] = []
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader((line for line in f if line.strip()))
        for raw in rd:
            rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v)
                         for k, v in raw.items()})
    return SrumDump(rows)


class SrumDump:
    """Insieme di righe SRUM con accesso per AppId e watermark temporale."""

    def __init__(self, rows: List[Dict[str, str]]) -> None:
        self.rows = rows

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _ts(r: Dict[str, str]) -> Optional[datetime.datetime]:
        s = (r.get("TimeStamp") or "").strip()
        if not s:
            return None
        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            try:
                return datetime.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                return None

    @staticmethod
    def _f(r: Dict[str, str], k: str) -> float:
        try:
            return float(r.get(k) or 0.0)
        except ValueError:
            return 0.0

    # -------------------------------------------------------------------- public
    def max_ts(self) -> Optional[datetime.datetime]:
        ts = [t for t in (self._ts(r) for r in self.rows) if t]
        return max(ts) if ts else None

    def min_ts(self) -> Optional[datetime.datetime]:
        ts = [t for t in (self._ts(r) for r in self.rows) if t]
        return min(ts) if ts else None

    def bucket_span_s(self, sample: int = 400) -> Optional[float]:
        """Mediana della distanza fra bucket consecutivi dello stesso AppId.

        Serve a sapere la granularita' reale (attesa ~60 s) senza ipotesi.
        """
        from statistics import median
        gaps: List[float] = []
        seen: Dict[str, List[datetime.datetime]] = {}
        for r in self.rows[:sample * 20]:
            t = self._ts(r)
            if t is None:
                continue
            seen.setdefault(r.get("AppId", ""), []).append(t)
        for k, v in seen.items():
            v = sorted(set(v))
            for a, b in zip(v[:-1], v[1:]):
                g = (b - a).total_seconds()
                if 0 < g < 3600:
                    gaps.append(g)
            if len(gaps) > sample:
                break
        return median(gaps) if gaps else None

    def sum_since(self, after: Optional[datetime.datetime]) -> Dict[str, Dict[str, float]]:
        """Somma i bucket con TimeStamp > `after`, per AppId.

        E' il delta fra due flush: i bucket sono storici e gia' chiusi, quindi
        sommarli e' corretto a patto di non ricomprendere il bucket di confine
        (errore sistematico <= 1 granularita', dichiarato).
        """
        out: Dict[str, Dict[str, float]] = {}
        for r in self.rows:
            t = self._ts(r)
            if t is None or (after is not None and t <= after):
                continue
            app = r.get("AppId", "?")
            d = out.setdefault(app, {f: 0.0 for f in ENERGY_FIELDS})
            for f in ENERGY_FIELDS:
                d[f] += self._f(r, f)
        return out

    def apps_matching(self, needle: str, per: Dict[str, Dict[str, float]]
                      ) -> Dict[str, Dict[str, float]]:
        import re
        pat = re.compile(needle, re.I)
        return {k: v for k, v in per.items() if pat.search(k)}

    def top(self, per: Dict[str, Dict[str, float]], field: str = "CPUEnergyConsumption",
            n: int = 10) -> List[Tuple[str, float]]:
        return sorted(((k, v.get(field, 0.0)) for k, v in per.items()),
                      key=lambda x: -x[1])[:n]


def grand_total(per: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    """Somma su TUTTI gli AppId: il totale di sistema, da rapportare al delta EMI."""
    tot = {f: 0.0 for f in ENERGY_FIELDS}
    for v in per.values():
        for f in ENERGY_FIELDS:
            tot[f] += v.get(f, 0.0)
    return tot


if __name__ == "__main__":
    import glob
    import os
    p = max(glob.glob(str(Path(__file__).parent / "experiment_results" / "srum_dump_*.csv")),
            key=os.path.getmtime)
    d = load(Path(p))
    print(f"dump: {p}")
    print(f"righe: {len(d.rows)}  span: {d.min_ts()} -> {d.max_ts()}")
    print(f"granularita' bucket (mediana): {d.bucket_span_s()} s")
    per = d.sum_since(None)
    gt = grand_total(per)
    print(f"totale sistema: {gt}")
    print("top 10 per CPUEnergyConsumption:")
    for k, v in d.top(per):
        print(f"  {v:>16.1f}  {k[:78]}")
