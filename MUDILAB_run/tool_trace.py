"""Trace del forwarding diretto: prova di flusso software, non di uso cognitivo.

Il digest controlla che la trace si riferisca al testo valutato: non autentica
il produttore e non rende attendibile un record falsificato. I record vanno
acquisiti dall'harness fidato, non dalla dichiarazione del modello.
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping


def forward_tool_result(step: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    """Inoltra proprio l'output registrato, costruendo la ricevuta nello stesso passo."""
    if not step.get("call_id") or step.get("step") != "cau_inference":
        raise ValueError("forwarding requires an identified cau_inference call")
    text = step.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("forwarding requires the acquired tool output")
    return text, {
        "producer": "run_orchestrato.forward_tool_result.v1",
        "mode": "direct_forward",
        "call_id": str(step["call_id"]),
        "source_field": "text",
        "destination_field": "numero",
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
