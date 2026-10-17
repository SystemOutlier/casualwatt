# -*- coding: utf-8 -*-
"""
causal_extractor.py — Estrazione di TRIPLE CAUSALI da testo libero (IT/EN).

Sostituisce il keyword matching grezzo ("cause"/"effect") come fonte di
acc_links. Una tripla e' (soggetto, relazione, oggetto): la struttura minima
confrontabile tra ground truth e risposta del modello.

Euristiche supportate (ordini di priorita'):
  * "X causes/caused/provoca/ha causato/determina/comporta Y"
  * "because X, Y" / "perche' X, Y" / "Y perche'/per via di X"
  * "due to X, Y" / "a causa di X, Y"
  * "X -> Y" / "X => Y" / "X --> Y"            (notazione esplicita)
  * "the effect of X on Y is Z" (pattern strutturato MUDILab-like)

Le triple sono normalizzate (minuscole, punteggiatura rimossa, spazi compressi)
per rendere il confronto robusto a parafrasi a livello di superficie.
Nessuna dipendenza esterna: parsing regex puro, sempre disponibile.
"""
from __future__ import annotations

import re
from typing import List, Tuple, Optional

Triple = Tuple[str, str, str]  # (subject, relation, object)

_STOP = re.compile(
    r"\b(the|a|an|il|lo|la|i|gli|le|un|uno|una|is|are|was|were|e'\xe8|"
    r"sar\xe0|that|which|this|that)\b",
    re.IGNORECASE,
)

_SPLIT_RE = re.compile(r"[,.;:!?\n]+|\s--\s")


def _clean(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^\w\sàèéìòùáíóúäöüß]", " ", s)
    s = _STOP.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _valid(node: str) -> bool:
    """Una causa/effetto deve avere almeno un token significativo."""
    return len(node) >= 2 and not _STOP.fullmatch(node or "")


# ---------------------------------------------------------------------------
# Pattern principali
# ---------------------------------------------------------------------------
_CAUSE_VERB_IT_EN = (
    r"(?:causes?|caused|provoca|provocano|ha\s+causato|hanno\s+causato|"
    r"determina|determinano|comporta|comportano|genera|generano|"
    r"produce|producono|innesca|innescano)"
)
_PATTERNS: List[re.Pattern] = [
    # "X <verbo causa> Y"
    re.compile(rf"(.+?)\s+{_CAUSE_VERB_IT_EN}\s+(.+)", re.IGNORECASE),
    # "because X, Y" / "perche' X, Y" / "poiche' X, Y"
    re.compile(r"(?:because|perch[e\xe9]|poich[e\xe9])\s+(.+?)[,.]\s*(.+)",
               re.IGNORECASE | re.DOTALL),
    # "Y because/per via di/a causa di due to X"
    re.compile(r"(.+?)\s+(?:because|per\s+via\s+di|a\s+causa\s+di|"
               r"a\s+causa\s+della|a\s+causa\s+dell'|grazie\s+a|due\s+to)\s+"
               r"(.+)", re.IGNORECASE | re.DOTALL),
    # "X -> Y" / "X => Y"
    re.compile(r"(.+?)\s*(?:->|=>|-->)\s*(.+)", re.IGNORECASE),
    # "the effect of X on Y is Z" -> (X, 'affects', Y) con oggetto Z scartato
    re.compile(r"the\s+effect\s+of\s+(.+?)\s+on\s+(.+?)\s+is\s+(.+)",
               re.IGNORECASE | re.DOTALL),
    # "l'effetto di X su Y e' Z"
    re.compile(r"l['\u2019]?effetto\s+di\s+(.+?)\s+s[uo]\s+(.+?)\s+\xe8\s+(.+)",
               re.IGNORECASE | re.DOTALL),
]


def extract_triples(text: str) -> List[Triple]:
    """Estrae triple causali (subject, relation, object) da testo libero.

    Restituisce [] se nessuna struttura causale e' riconoscibile: in quel caso
    l'evaluator DEVE demandare il punteggio al judge (acc_links = 0.0 o N/A),
    mai inventare collegamenti.
    """
    triples: List[Triple] = []
    if not text or not text.strip():
        return triples

    for raw in _SPLIT_RE.split(text):
        seg = raw.strip()
        if not seg:
            continue
        for pat in _PATTERNS:
            m = pat.search(seg)
            if not m:
                continue
            g = [x.strip() for x in m.groups()]
            if pat.pattern.startswith("the\\s+effect") or "effetto" in pat.pattern:
                subj, obj = _clean(g[0]), _clean(g[1])
                rel = "affects"
            elif pat.pattern.startswith("(?:because"):
                subj, obj = _clean(g[0]), _clean(g[1])
                rel = "because_of"   # invertito: Y avviene perche' X
            elif "per\\s+via" in pat.pattern or "due\\s+to" in pat.pattern:
                subj, obj = _clean(g[1]), _clean(g[0])
                rel = "because_of"
            else:
                subj, obj = _clean(g[0]), _clean(g[1])
                rel = "causes"
            if _valid(subj) and _valid(obj):
                t = (subj, rel, obj)
                if t not in triples:
                    triples.append(t)
            break  # primo pattern che matcha sul segmento
    return triples


def has_structured_causality(text: str) -> bool:
    return bool(extract_triples(text))


# ---------------------------------------------------------------------------
# Confronto GT <-> risposta (F1 su triple)
# ---------------------------------------------------------------------------
def _node_overlap(a: str, b: str) -> float:
    """Overlap Jaccard sui token di due nodi (tollerante a parafrasi lievi)."""
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _triple_match(t1: Triple, t2: Triple, node_threshold: float = 0.5) -> bool:
    """Match approssimato: relazione compatibile + entrambi i nodi simili."""
    rel_ok = (t1[1] == t2[1]) or (t1[1] in ("causes", "because_of")
                                  and t2[1] in ("causes", "because_of"))
    if not rel_ok:
        return False
    return (_node_overlap(t1[0], t2[0]) >= node_threshold
            and _node_overlap(t1[2], t2[2]) >= node_threshold)


def f1_on_triples(gt_triples: List[Triple], ans_triples: List[Triple],
                  node_threshold: float = 0.5) -> Optional[dict]:
    """F1-score su multiset di triple causali (None se non calcolabile).

    Ritorna dict con precision, recall, f1, n_gt, n_ans, n_matched.
    Se una delle parti non ha triple -> None (valutazione strutturale
    IMPOSSIBILE: l'evaluator usera' il fallback dichiarato, mai F1 fittizio).
    """
    if not gt_triples or not ans_triples:
        return None
    matched = 0
    used = set()
    for tg in gt_triples:
        for i, ta in enumerate(ans_triples):
            if i in used:
                continue
            if _triple_match(tg, ta, node_threshold):
                matched += 1
                used.add(i)
                break
    precision = matched / len(ans_triples)
    recall = matched / len(gt_triples)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "n_gt": len(gt_triples),
        "n_ans": len(ans_triples),
        "n_matched": matched,
    }
