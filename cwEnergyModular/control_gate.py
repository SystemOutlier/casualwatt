# -*- coding: utf-8 -*-
"""P4.5 — il criterio del test load-versus-control (F.12).

Il protocollo (`experiment_results/protocollo_v4_20261024.md`, P4.5
`:1518-1663` e formulario F.12 `:3089-3160`) fissa il criterio come tre
passaggi distinti, e questo modulo li applica senza aggiungerne un quarto:

    filtro:     controllo utilizzabile se  pre_range_w,c <= 1,0 W
                                      e    |dP_c| <= 1,0 W
    per blocco: |E_net,control,c| <= budget_base_j,c
    aggregato:  bias_w = sum_c E_net,control,c / sum_c dt_W,c
                passa se |bias_w| <= mediana_c(budget_base_w,c)

sui soli controlli utilizzabili, con quorum ``ceil(2/3 * n_coppie)`` (4 su 6):
sotto il quorum il gate non e' eseguibile e ``chain_status`` scende a
``bias_declared`` con la ragione scritta, senza pubblicare un bias medio su un
pugno di blocchi.

Cosa non fa, e perche'. Non esegue la campagna e non sceglie ``dt_nominal_s``
(P4.4 requisiti 1 e 5: la durata si fissa prima, e i blocchi li produce il
runner). Non calcola ``u_bias,b = |bias_w| * dt_bar_W,b``: la durata media e'
quella dei blocchi della campagna **principale**, che al momento del gate non
esiste (F.12). Non promuove nessuna riga a ``validated``: il gate e' l'anello 4
di P4.9, non la catena intera.

Due decisioni di lettura, dichiarate perche' cambiano i numeri. La mediana e'
``statistics.median``, che con un numero pari di valori e' la media dei due
centrali. Il criterio per blocco si applica ai soli controlli utilizzabili:
P4.5 `:1578-1580` dice che il filtro "ammette al criterio solo blocchi la cui
deriva e' piccola in assoluto", quindi un controllo scartato riporta
``block_pass = None`` con la ragione, non un verdetto costruito sul proprio
budget.

Nessun degrado silenzioso. Una cella vuota significa "non calcolata" e rende il
controllo non utilizzabile o il gate non eseguibile, con il campo nominato; un
valore non numerico e' invece un dato corrotto e solleva ``ValueError``. Un
controllo utilizzabile a cui manca una delle grandezze dell'aggregato non viene
escluso in silenzio: il gate si dichiara non eseguibile e nomina il blocco.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from statistics import median
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

#: P1.6 / P4.5: le due soglie assolute, congelate prima dei dati. La stessa
#: scala di 1,0 W di `pre_unstable`, non una metrica nuova.
PRE_RANGE_MAX_W = 1.0
DP_MAX_W = 1.0

#: P4.5, emendamento del 2026-10-24: la frazione congelata e' due su tre, e il
#: quorum e' quella frazione riportata alle coppie, non un numero assoluto.
QUORUM_FRACTION = Fraction(2, 3)

#: F.12: la coppia di percentuali di J/token per watt di bias. E' una
#: grandezza riportata (scala ancorata a 1 W), non una soglia.
BIAS_JTOK_PCT_PER_W = (6.0, 11.0)


@dataclass(frozen=True)
class ControlCheck:
    """Un blocco di controllo con il filtro e il verdetto per blocco.

    ``usable`` e' l'esito del filtro assoluto; ``control_unstable`` e' il flag
    del protocollo, vero solo quando una delle due soglie e' superata (una
    cella vuota rende il controllo inutilizzabile senza affermarne
    l'instabilita'). ``block_pass`` e' ``None`` quando il criterio per blocco
    non si applica o non e' calcolabile, con la ragione in ``block_reason``.
    """

    block_id: str
    pair_id: str
    usable: bool
    control_unstable: bool
    reason: str
    pre_range_w: Optional[float]
    dP: Optional[float]
    e_net_j: Optional[float]
    dt_w_s: Optional[float]
    budget_base_j: Optional[float]
    budget_base_w: Optional[float]
    window_source: str
    block_pass: Optional[bool]
    block_reason: str


@dataclass(frozen=True)
class GateResult:
    """L'esito del gate di F.12.

    ``status`` e' ``pass``/``fail``/``not-executable``; ``chain_status`` porta
    ``bias_declared`` solo nel terzo caso, come prescrive F.12. ``bias_w`` e
    ``bias_jtok_pct`` sono ``None`` quando il gate non e' eseguibile: un bias
    calcolato su meno del quorum non e' un risultato.
    """

    n_pairs: int
    quorum: int
    controls: Tuple[ControlCheck, ...]
    controls_usable_n: int
    executable: bool
    status: str
    chain_status: str
    bias_w: Optional[float]
    bias_threshold_w: Optional[float]
    bias_jtok_pct: Optional[Tuple[float, float]]
    reasons: Tuple[str, ...]

    def to_dict(self) -> Dict[str, object]:
        """Rappresentazione JSON: ``controls`` diventa una lista di oggetti."""
        data = asdict(self)
        data["controls"] = [asdict(c) for c in self.controls]
        data["bias_jtok_pct"] = (
            list(self.bias_jtok_pct) if self.bias_jtok_pct is not None else None)
        data["reasons"] = list(self.reasons)
        return data


def _number(record: Mapping[str, object], key: str,
            where: str) -> Optional[float]:
    """Legge una grandezza numerica dal riepilogo, distinguendo i tre casi.

    Vuoto/assente -> ``None`` (cella non calcolata, dichiarata). Numero finito
    -> valore. Qualunque altro contenuto -> ``ValueError``: un file corrotto
    non e' una cella vuota, e trattarlo come tale lo nasconderebbe.
    """
    value = record.get(key, "")
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(
            f"{where}: '{key}' non numerico ({value!r})") from None
    if not math.isfinite(number):
        raise ValueError(f"{where}: '{key}' non finito ({value!r})")
    return number


def _check_control(record: Mapping[str, object], index: int) -> ControlCheck:
    block_id = str(record.get("block_id", "") or f"controllo#{index + 1}")
    pair_id = str(record.get("pair_id", "") or "")
    where = f"controllo {block_id}"
    kind = record.get("block_kind")
    if kind not in (None, "", "control"):
        raise ValueError(
            f"{where}: block_kind={kind!r}, atteso 'control'. Un blocco di "
            "carico non ha E_net,control e non appartiene al gate")

    pre = _number(record, "pre_range_w", where)
    dp = _number(record, "dP", where)
    e_net = _number(record, "control_e_net_j", where)
    dt_w = _number(record, "control_dt_w_s", where)
    budget_j = _number(record, "budget_base_j", where)
    budget_w = _number(record, "budget_base_w", where)

    unstable = False
    if pre is None:
        usable, reason = False, "pre_range_w assente: stabilita' non misurata"
    elif pre > PRE_RANGE_MAX_W:
        usable, unstable = False, True
        reason = (f"pre_range_w={pre:g} W > {PRE_RANGE_MAX_W:g} W "
                  "(soglia di pre_unstable, P1.6)")
    elif dp is None:
        usable, reason = False, "dP assente: deriva non misurata"
    elif abs(dp) > DP_MAX_W:
        usable, unstable = False, True
        reason = f"|dP|={abs(dp):g} W > {DP_MAX_W:g} W"
    else:
        usable = True
        reason = (f"pre_range_w={pre:g} W <= {PRE_RANGE_MAX_W:g} W e "
                  f"|dP|={abs(dp):g} W <= {DP_MAX_W:g} W")

    if not usable:
        block_pass: Optional[bool] = None
        block_reason = ("criterio per blocco non applicato: il controllo non "
                        "e' utilizzabile (P4.5)")
    elif e_net is None or budget_j is None:
        block_pass = None
        missing = "E_net,control" if e_net is None else "budget_base_j"
        block_reason = f"criterio per blocco non calcolabile: {missing} assente"
    else:
        block_pass = abs(e_net) <= budget_j
        block_reason = (f"|E_net,control|={abs(e_net):g} J "
                        f"{'<=' if block_pass else '>'} "
                        f"budget_base_j={budget_j:g} J")

    return ControlCheck(
        block_id=block_id,
        pair_id=pair_id,
        usable=usable,
        control_unstable=unstable,
        reason=reason,
        pre_range_w=pre,
        dP=dp,
        e_net_j=e_net,
        dt_w_s=dt_w,
        budget_base_j=budget_j,
        budget_base_w=budget_w,
        window_source=str(record.get("control_package_window_source", "") or ""),
        block_pass=block_pass,
        block_reason=block_reason,
    )


def quorum_for(n_pairs: int) -> int:
    """Quorum di F.12: ``ceil(2/3 * n_coppie)``, esatto sui razionali."""
    if n_pairs < 1:
        raise ValueError(f"n_pairs={n_pairs}: servono almeno una coppia")
    return math.ceil(QUORUM_FRACTION * n_pairs)


def evaluate_gate(controls: Sequence[Mapping[str, object]],
                  n_pairs: int = 6) -> GateResult:
    """Applica F.12 ai blocchi di controllo del gate.

    ``controls`` sono i riepiloghi di blocco del runner per i soli controlli
    (``block_kind='control'``), con le quantita' ``control_*``; ``n_pairs`` e'
    il numero di coppie del disegno, non quello dei blocchi ricevuti: una
    lista di lunghezza diversa e' un disegno diverso e solleva ``ValueError``
    invece di calcolare il quorum su un dato che non c'e'.
    """
    if n_pairs < 1:
        raise ValueError(f"n_pairs={n_pairs}: servono almeno una coppia")
    if len(controls) != n_pairs:
        raise ValueError(
            f"il gate e' definito su {n_pairs} coppie ma ha ricevuto "
            f"{len(controls)} blocchi di controllo: il quorum si calcola sul "
            "disegno, non su cio' che e' arrivato")

    checks = tuple(_check_control(rec, i) for i, rec in enumerate(controls))
    usable = [c for c in checks if c.usable]
    n_usable = len(usable)
    quorum = quorum_for(n_pairs)

    if n_usable < quorum:
        reasons = [f"controlli utilizzabili {n_usable} < quorum {quorum} "
                   f"(ceil(2/3 * {n_pairs}))"]
        reasons.extend(f"{c.block_id}: {c.reason}"
                       for c in checks if not c.usable)
        return GateResult(
            n_pairs=n_pairs, quorum=quorum, controls=checks,
            controls_usable_n=n_usable, executable=False,
            status="not-executable", chain_status="bias_declared",
            bias_w=None, bias_threshold_w=None, bias_jtok_pct=None,
            reasons=tuple(reasons))

    # Da qui il gate e' eseguibile: l'aggregato vuole tutte e tre le grandezze
    # su ogni controllo utilizzabile. Un'assenza non si aggira restringendo il
    # campione, perche' quel restringimento sarebbe un filtro non dichiarato.
    missing = [
        f"{c.block_id}: {nome}" for c in usable
        for nome, valore in (("E_net,control", c.e_net_j),
                             ("dt_W", c.dt_w_s),
                             ("budget_base_w", c.budget_base_w))
        if valore is None
    ]
    if missing:
        return GateResult(
            n_pairs=n_pairs, quorum=quorum, controls=checks,
            controls_usable_n=n_usable, executable=False,
            status="not-executable", chain_status="bias_declared",
            bias_w=None, bias_threshold_w=None, bias_jtok_pct=None,
            reasons=("gate eseguibile per quorum ma non calcolabile: "
                     + ", ".join(missing),))

    somma_e = sum(float(c.e_net_j) for c in usable)
    somma_dt = sum(float(c.dt_w_s) for c in usable)
    if somma_dt <= 0.0:
        return GateResult(
            n_pairs=n_pairs, quorum=quorum, controls=checks,
            controls_usable_n=n_usable, executable=False,
            status="not-executable", chain_status="bias_declared",
            bias_w=None, bias_threshold_w=None, bias_jtok_pct=None,
            reasons=(f"somma delle dt_W non positiva ({somma_dt:g} s): il "
                     "denominatore del bias non esiste",))

    bias = somma_e / somma_dt
    threshold = float(median(float(c.budget_base_w) for c in usable))
    passes = abs(bias) <= threshold
    if passes:
        reasons: Tuple[str, ...] = ()
    else:
        reasons = (f"|bias_w|={abs(bias):g} W > mediana_c(budget_base_w,c)"
                   f"={threshold:g} W",)
    jtok = (abs(bias) * BIAS_JTOK_PCT_PER_W[0],
            abs(bias) * BIAS_JTOK_PCT_PER_W[1])
    return GateResult(
        n_pairs=n_pairs, quorum=quorum, controls=checks,
        controls_usable_n=n_usable, executable=True,
        status="pass" if passes else "fail", chain_status="",
        bias_w=bias, bias_threshold_w=threshold, bias_jtok_pct=jtok,
        reasons=reasons)


def _load_blocks(path: Path) -> List[Mapping[str, object]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, Mapping):
        data = data.get("blocks", data.get("controls", []))
    if not isinstance(data, list):
        raise ValueError(f"{path}: attesa una lista di riepiloghi di blocco")
    return data


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Esegue il gate su un file JSON di riepiloghi di blocco.

    Codici di uscita: ``0`` gate superato, ``1`` gate fallito, ``2`` gate non
    eseguibile (quorum o dati mancanti). Il file di uscita ha la stessa forma
    del dizionario di :class:`GateResult`.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--blocks", required=True,
                        help="JSON con i riepiloghi dei blocchi di controllo")
    parser.add_argument("--pairs", type=int, default=6,
                        help="numero di coppie del disegno (default 6)")
    parser.add_argument("--out", default="",
                        help="file JSON di uscita (default: stdout)")
    args = parser.parse_args(argv)

    result = evaluate_gate(_load_blocks(Path(args.blocks)), n_pairs=args.pairs)
    testo = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(testo + "\n", encoding="utf-8")
    else:
        print(testo)
    return {"pass": 0, "fail": 1, "not-executable": 2}[result.status]


if __name__ == "__main__":
    raise SystemExit(main())
