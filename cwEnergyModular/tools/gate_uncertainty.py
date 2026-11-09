# -*- coding: utf-8 -*-
"""
tools/gate_uncertainty.py — combinazione dell'incertezza per il gate P4.4.

Questo modulo NON stima nessuna componente: le stima ``run_gate_p44.py`` dai
dati misurati. Qui si fissa soltanto la REGOLA DI COMBINAZIONE e la forma che
ogni componente deve avere per entrare nel conto o per restarne fuori.

Perche' esiste la forma obbligatoria. Nella versione precedente ``calcola_u_c``
sommava in quadratura qualunque componente non ``None``: una componente
mancante spariva dalla somma senza una riga che lo dicesse, e due componenti
che descrivevano la stessa dispersione (u_rumore/u_termico e il budget di cui
sono fatte) venivano sommate due volte. Qui ogni componente dichiara:

  * ``value``   numero in watt, oppure ``None`` se non calcolabile;
  * ``tipo``    "A" (stimata da dati ripetuti) o "B" (da altra informazione),
                secondo la classificazione del GUM (JCGM 100:2008, 4.2 e 4.3);
  * ``inclusa`` True se entra in u_c, False se resta fuori;
  * ``motivo``  perche' e' inclusa o esclusa (obbligatorio, non vuoto).

Un'esclusione e' una decisione dichiarata, non un'assenza: la componente resta
nel report con il suo valore informativo e la ragione. Una componente inclusa
con valore ``None`` o non finito e' un errore, non uno zero.

u_c e' la somma in quadratura (RSS) delle SOLE componenti incluse. La RSS
presuppone componenti indipendenti: chi marca ``inclusa=True`` risponde
dell'indipendenza, e ``motivo`` e' il posto dove dirlo.
"""
from __future__ import annotations

import math
from typing import Dict, List, Mapping, Optional, Tuple

TIPI_AMMESSI = ("A", "B")


def valida_componente(nome: str, comp: Mapping) -> List[str]:
    """Elenco degli errori di forma di una componente (vuoto se conforme)."""
    errori: List[str] = []
    if comp.get("tipo") not in TIPI_AMMESSI:
        errori.append(f"{nome}: tipo {comp.get('tipo')!r} non in {TIPI_AMMESSI}")
    if not isinstance(comp.get("inclusa"), bool):
        errori.append(f"{nome}: 'inclusa' deve essere True/False, non "
                      f"{comp.get('inclusa')!r}")
    motivo = comp.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip():
        errori.append(f"{nome}: 'motivo' obbligatorio (inclusione ed "
                      "esclusione si dichiarano entrambe)")
    valore = comp.get("value")
    if comp.get("inclusa") is True:
        if (isinstance(valore, bool) or not isinstance(valore, (int, float))
                or not math.isfinite(float(valore)) or float(valore) < 0.0):
            errori.append(f"{nome}: inclusa ma value={valore!r} non e' un "
                          "numero finito non negativo")
    elif valore is not None and (isinstance(valore, bool)
                                 or not isinstance(valore, (int, float))
                                 or not math.isfinite(float(valore))):
        errori.append(f"{nome}: value={valore!r} non e' ne' None ne' un "
                      "numero finito")
    return errori


def combina_incluse(componenti: Mapping[str, Mapping]) -> Optional[float]:
    """RSS delle sole componenti con ``inclusa=True``; ``None`` se nessuna.

    ``None`` NON e' zero: significa "nessuna componente indipendente e
    calcolabile in questo momento". Una forma non conforme solleva
    ``ValueError`` con tutti gli errori, invece di degradare in silenzio.
    """
    errori: List[str] = []
    for nome, comp in componenti.items():
        errori.extend(valida_componente(nome, comp))
    if errori:
        raise ValueError("componenti di incertezza non conformi: "
                         + "; ".join(errori))
    incluse = [float(c["value"]) for c in componenti.values()
               if c["inclusa"] is True]
    if not incluse:
        return None
    return math.sqrt(sum(v * v for v in incluse))


def calcola_u_c(
    dispersione_controlli: Optional[float] = None,
    risoluzione_timer: Optional[float] = None,
    dispersione_baseline: Optional[float] = None,
    margine_termico: Optional[float] = None,
    incertezza_allineamento: Optional[float] = None
) -> Tuple[float, Dict[str, Optional[float]]]:
    """Forma storica: RSS di tutti gli argomenti non ``None``.

    DEPRECATA per il gate: salta in silenzio le componenti ``None`` e non sa
    nulla di tipo, inclusione o indipendenza. Resta solo per compatibilita'
    con chi la importava; il gate usa ``combina_incluse``.
    """
    componenti = {
        "u_A": dispersione_controlli,
        "u_timer": risoluzione_timer,
        "u_rumore": dispersione_baseline,
        "u_termico": margine_termico,
        "u_allineamento": incertezza_allineamento,
    }
    somma_quadrati = 0.0
    for val in componenti.values():
        if val is not None:
            somma_quadrati += val ** 2
    return math.sqrt(somma_quadrati), componenti
