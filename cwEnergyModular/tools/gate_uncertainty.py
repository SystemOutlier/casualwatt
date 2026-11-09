# -*- coding: utf-8 -*-
"""
tools/gate_uncertainty.py — calcolo dell'incertezza combinata per il gate P4.4.

Il budget di incertezza u_c serve a definire una soglia di conformità scientifica
S = B_matched + k * u_c. u_c e' la radice quadrata della somma dei quadrati
delle componenti di incertezza (metodo GUM).
"""

from __future__ import annotations
import math
from typing import Dict, List, Mapping, Optional, Tuple

def calcola_u_c(
    dispersione_controlli: Optional[float] = None,
    risoluzione_timer: Optional[float] = None,
    dispersione_baseline: Optional[float] = None,
    margine_termico: Optional[float] = None,
    incertezza_allineamento: Optional[float] = None
) -> Tuple[float, Dict[str, Optional[float]]]:
    """
    Calcola l'incertezza combinata u_c come radice della somma dei quadrati.
    
    Componenti:
        - u_A (dispersione): dispersione fra i controlli utilizzabili.
        - u_timer: risoluzione del contatore / tempo di campionamento.
        - u_rumore: dispersione delle finestre di baseline.
        - u_termico: margine dichiarato prima del run (transitorio).
        - u_allineamento: incertezza di sincronizzazione finestre.
    
    Ritorna (u_c, componenti_dettaglio).
    """
    componenti = {
        "u_A": dispersione_controlli,
        "u_timer": risoluzione_timer,
        "u_rumore": dispersione_baseline,
        "u_termico": margine_termico,
        "u_allineamento": incertezza_allineamento,
    }
    
    somma_quadrati = 0.0
    for nome, val in componenti.items():
        if val is not None:
            somma_quadrati += val ** 2
            
    u_c = math.sqrt(somma_quadrati)
    return u_c, componenti
