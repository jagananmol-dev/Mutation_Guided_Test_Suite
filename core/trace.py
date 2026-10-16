"""Append-only, system-generated JSONL trace. Do not edit trace entries by hand."""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def record(state: dict[str, Any], agent: str, event: str,
           payload: dict[str, Any] | None = None) -> dict[str, Any]:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_id": state.get("run_id", "unknown"),
        "agent": agent,
        "event": event,
        "payload": payload or {},
    }
    path = Path(state.get("trace_path") or os.getenv("TRACE_PATH", "trace.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return entry
