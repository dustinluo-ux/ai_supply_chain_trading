"""
Persistent fill ledger for paper/live order tracking.

Append-only JSON-Lines file: outputs/fills/fills.jsonl.
Helpers: append_fill_record(), read_fill_ledger().
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Project root: src/execution/fill_ledger.py -> src/execution -> src -> project_root
_ROOT = Path(__file__).resolve().parent.parent.parent
FILLS_PATH = _ROOT / "outputs" / "fills" / "fills.jsonl"


def append_fill_record(
    run_id: str,
    ticker: str,
    side: str,
    qty_requested: int,
    qty_filled: int,
    avg_fill_price: float | None,
    order_id: str | None,
    stop_order_id: str | None,
    status: str,
    fill_check_passed: bool,
    fill_check_reason: str,
    order_comment: str | None,
    *,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """
    Append one JSON-Lines record to outputs/fills/fills.jsonl.
    Creates file and directory if absent. Returns the record dict (for audit).
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    record = {
        "run_id": run_id,
        "timestamp": timestamp,
        "ticker": ticker,
        "side": side,
        "qty_requested": qty_requested,
        "qty_filled": qty_filled,
        "avg_fill_price": avg_fill_price,
        "order_id": order_id,
        "stop_order_id": stop_order_id,
        "status": status,
        "fill_check_passed": fill_check_passed,
        "fill_check_reason": fill_check_reason,
        "order_comment": order_comment,
    }
    FILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FILLS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def read_fill_ledger(path: Path | str | None = None) -> list[dict[str, Any]]:
    """Read all records from the fill ledger. Returns list of dicts. path defaults to FILLS_PATH."""
    p = Path(path) if path is not None else FILLS_PATH
    if not p.exists():
        return []
    records = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records
