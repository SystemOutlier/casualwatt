"""B1: grammatica numerica condivisa, chiusa e senza scelta dell'ultimo numero.

Segni ASCII, punto/virgola decimale (non migliaia), esponente e/E, percentuali
adimensionali e soli simboli SI dichiarati sotto. Non valuta espressioni,
LaTeX, unita' composte o numeri in lettere. Un suffisso sconosciuto non viene
cancellato: rende l'estrazione indeterminata. La prosa prima del numero e'
ammessa; dopo il numero, separare la prosa con punteggiatura. Le congiunzioni
elencate permettono ripetizioni/alternative, non sono unita'.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


# L'esponente appartiene all'intero token, mai un'alternativa dopo l'intero.
NUMBER_PATTERN = r"[-+]?(?:\d+(?:[.,]\d+)?|[.,]\d+)(?:[eE][-+]?\d+)?"
_NUMBER_RE = re.compile(NUMBER_PATTERN)
_LITERAL_RE = re.compile(rf"({NUMBER_PATTERN})\s*(%|[A-Za-z]+)?")
_MARKER_RE = re.compile(
    r"\b(?P<final>final\s+answer|risposta\s+finale)\b|"
    r"\b(?:answer|result|risposta|risultato)\b", re.I,
)
_MARKER_SEPARATOR_RE = re.compile(r"\s*(?:(?:[:=]|\bis\b|\bè\b)\s*)?", re.I)
_NONFINITE_RE = re.compile(r"(?<!\w)[+-]?(?:nan|inf(?:inity)?)(?!\w)|∞", re.I)
_SUFFIX_RE = re.compile(r"\s*(%|[^\W\d_][\w]*(?:[/^·][\w+-]+)*)", re.UNICODE)
_CONNECTORS = {"and", "or", "e", "o", "oppure"}
# Simboli case-sensitive; esponente di 10 verso l'unita' canonica.
_UNITS = {
    "": ("", 0, ""), "%": ("", -2, ""),
    "J": ("energy", 0, "J"), "mJ": ("energy", -3, "J"),
    "kJ": ("energy", 3, "J"), "W": ("power", 0, "W"),
    "s": ("time", 0, "s"), "ms": ("time", -3, "s"),
}


@dataclass(frozen=True)
class NumericValue:
    value: Decimal
    dimension: str
    text: str


@dataclass(frozen=True)
class NumericExtraction:
    status: str
    quantity: Optional[NumericValue] = None
    reason: str = ""


def parse_numeric_literal(value: Any) -> Optional[NumericValue]:
    """Legge l'intero scalare, non un suo prefisso; converte solo unita' note."""
    match = _LITERAL_RE.fullmatch(str(value).strip())
    if match is None:
        return None
    literal = match.group(1).replace(",", ".")
    unit = match.group(2) or ""
    if unit not in _UNITS:
        return None
    dimension, exponent_shift, canonical = _UNITS[unit]
    try:
        number = Decimal(literal)
        sign, digits, exponent = number.as_tuple()
        # Conversione esatta: non arrotondare due candidati distinti per unirli.
        number = Decimal((sign, digits, exponent + exponent_shift))
        floating = float(number)
    except (InvalidOperation, ValueError, OverflowError):
        return None
    if not math.isfinite(floating) or (floating == 0 and number != 0):
        return None
    normalized = literal if not unit else str(number)
    if canonical:
        normalized += " " + canonical
    return NumericValue(number, dimension, normalized)


def _scan_candidates(text: str) -> NumericExtraction:
    """Accetta una sola quantita' distinta; non interpreta il ragionamento."""
    if not text.strip():
        return NumericExtraction("empty", reason="empty numeric answer")
    if _NONFINITE_RE.search(text):
        return NumericExtraction("invalid", reason="non-finite numeric token")
    matches = list(_NUMBER_RE.finditer(text))
    if not matches:
        return NumericExtraction("no_number", reason="no numeric answer")
    candidates = []
    masked = list(text)
    previous_end = 0
    for match in matches:
        start, end = match.span()
        if start < previous_end:
            return NumericExtraction("invalid", reason="number inside an unsupported suffix")
        if start and (text[start - 1].isalnum() or text[start - 1] in "_.,+-−"):
            return NumericExtraction("invalid", reason="unsupported numeric boundary")
        if (candidates and match.group()[0] in "+-"
                and not text[previous_end:start].strip()):
            return NumericExtraction("ambiguous", reason="arithmetic is not a final answer")
        suffix = _SUFFIX_RE.match(text, end)
        unit = ""
        connector = (suffix is not None
                     and suffix.group(1).lower() in _CONNECTORS
                     and bool(text[match.end():suffix.start(1)]))
        if suffix and not connector:
            unit = suffix.group(1)
            end = suffix.end()
        quantity = parse_numeric_literal(match.group() + unit)
        if quantity is None:
            return NumericExtraction("invalid", reason="unsupported unit or numeric value")
        # Non accettare '3 J/kg', '50% J', '3 J foo' o decimali malformati.
        extra = _SUFFIX_RE.match(text, end) if unit else None
        if extra and extra.group(1).lower() not in _CONNECTORS:
            return NumericExtraction("invalid", reason="unsupported compound suffix")
        if ((end < len(text) and text[end] in "_^/·%")
                or re.match(r"\s*[\[(]\s*[%\w]", text[end:])):
            return NumericExtraction("invalid", reason="unsupported numeric suffix")
        candidates.append(quantity)
        masked[start:end] = " " * (end - start)
        previous_end = end
    if re.search(r"[=+*/^−±×÷$€£-]", "".join(masked)):
        return NumericExtraction("ambiguous", reason="arithmetic is not a final answer")
    if len({(q.value, q.dimension) for q in candidates}) != 1:
        return NumericExtraction("ambiguous", reason="distinct plausible numeric answers")
    return NumericExtraction("ok", candidates[0])


def extract_numeric_answer(text: str) -> NumericExtraction:
    """Marker finali > generici > testo; nessuna scelta dell'ultima occorrenza.

    Ogni marker delimita un segmento fino al successivo. Tutti i segmenti al
    livello prioritario devono essere leggibili e concordi, anche se ripetuti.
    Un marker vuoto non consente il ripiego su un livello inferiore.
    """
    text = text or ""
    markers = list(_MARKER_RE.finditer(text))
    if not markers:
        return _scan_candidates(text)
    final_level = any(marker.group("final") for marker in markers)
    results = []
    for index, marker in enumerate(markers):
        if bool(marker.group("final")) != final_level:
            continue
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        segment = text[marker.end():end]
        segment = _MARKER_SEPARATOR_RE.sub("", segment, count=1)
        results.append(_scan_candidates(segment))
    if (all(result.status == "no_number" for result in results)
            and not _NUMBER_RE.search(text) and not _NONFINITE_RE.search(text)):
        return NumericExtraction("no_number", reason="non-empty answer without numbers")
    for result in results:
        if result.status != "ok":
            return NumericExtraction("ambiguous", reason="unresolved marker: " + result.reason)
    values = [result.quantity for result in results]
    if len({(q.value, q.dimension) for q in values}) != 1:
        return NumericExtraction("ambiguous", reason="discordant markers at the same level")
    return NumericExtraction("ok", values[0])
