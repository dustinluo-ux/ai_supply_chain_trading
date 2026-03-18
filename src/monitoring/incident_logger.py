"""
Append-only incident log (JSONL). No logging module to avoid circular dependency.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LOG_PATH = ROOT / "logs" / "incident_history.jsonl"


def log_incident(event_type: str, payload: dict, log_path: Path | str | None = None) -> None:
    """Append one incident record (timestamp, event_type, payload) to the JSONL log. Never raises."""
    if log_path is None:
        log_path = DEFAULT_LOG_PATH
    else:
        log_path = Path(log_path)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "payload": payload,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"[incident_logger] WARN: could not write incident: {e}", file=sys.stderr)
