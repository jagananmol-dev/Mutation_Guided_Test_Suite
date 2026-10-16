"""Small helpers shared by agent nodes."""
from __future__ import annotations
from typing import Any
from core.trace import record


def traced(state: dict[str, Any], agent: str, event: str, payload: dict[str, Any],
           updates: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = record(state, agent, event, payload)
    result = dict(updates or {})
    result["trace_events"] = [entry]
    return result


def error_update(state: dict[str, Any], agent: str, message: str) -> dict[str, Any]:
    err = {"agent": agent, "message": message}
    entry = record(state, agent, "error", {"message": message})
    return {"errors": [err], "trace_events": [entry]}
