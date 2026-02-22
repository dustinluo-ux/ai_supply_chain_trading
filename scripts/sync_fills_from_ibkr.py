"""
Sync fill ledger with TWS executions for a given date.

After market fills, connect to TWS, query executions for that date, and update
outputs/fills/fills.jsonl — replacing records where qty_filled=0 with actual
fill quantities and prices. Exit 0 always (never raises).

Usage:
  python scripts/sync_fills_from_ibkr.py [--date YYYY-MM-DD]

Default date: today. TWS must be running.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _main() -> int:
    parser = argparse.ArgumentParser(description="Sync fills from IBKR TWS executions.")
    parser.add_argument("--date", type=str, default=None, help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    from datetime import datetime, timezone
    if args.date:
        date_str = args.date
    else:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # 1. Load dotenv; read IBKR_PAPER_ACCOUNT and host/port
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import os
    import yaml
    paper_account = os.getenv("IBKR_PAPER_ACCOUNT", "").strip()
    host, port = "127.0.0.1", 7497
    trading_config_path = ROOT / "config" / "trading_config.yaml"
    if trading_config_path.exists():
        try:
            with open(trading_config_path, "r", encoding="utf-8") as f:
                tc = yaml.safe_load(f) or {}
            if not paper_account:
                paper_account = (tc.get("trading", {}).get("execution", {}) or {}).get("paper_account", "")
            ib = (tc.get("trading", {}) or {}).get("ib", {})
            if ib:
                host = ib.get("host", host)
                port = int(ib.get("port", port))
        except Exception:
            pass
    paper_account = (paper_account or "").strip()
    if not paper_account:
        print("WARNING: IBKR_PAPER_ACCOUNT not set; sync may fail.", flush=True)

    # 2. Read existing fills
    from src.execution.fill_ledger import read_fill_ledger, FILLS_PATH
    records = read_fill_ledger()
    if not records:
        print("No fills to sync.", flush=True)
        return 0

    # 3. Pending: qty_filled == 0 or status in ("failed", "unknown")
    pending_idxs = [
        i for i, r in enumerate(records)
        if (int(r.get("qty_filled") or 0) == 0
        or (r.get("status") or "") in ("failed", "unknown")
    ]
    if not pending_idxs:
        print("All fills already reconciled.", flush=True)
        return 0

    # 4. Connect to TWS
    try:
        from ib_insync import IB, ExecutionFilter
        ib = IB()
        ib.connect(host, port, clientId=10)
    except Exception as e:
        print("WARNING: TWS not available.", flush=True)
        return 0

    try:
        # 5. Query executions
        time_filter = f"{date_str.replace('-', '')} 00:00:00"
        ef = ExecutionFilter(acctCode=paper_account, time=time_filter)
        tws_fills = ib.reqExecutions(ef)
        ib.disconnect()
    except Exception as e:
        try:
            ib.disconnect()
        except Exception:
            pass
        print("WARNING: TWS not available.", flush=True)
        return 0

    # 6. Build lookup: (symbol, side) -> list of Fill; side BOT->BUY, SLD->SELL
    def _norm_side(s: str) -> str:
        if (s or "").upper() == "BOT":
            return "BUY"
        if (s or "").upper() == "SLD":
            return "SELL"
        return (s or "").upper()

    tws_map: dict[tuple[str, str], list] = {}
    for fill in tws_fills:
        try:
            sym = (getattr(fill.execution, "symbol", None) or getattr(fill, "contract", None) and getattr(fill.contract, "symbol", None) or "").strip()
            side = _norm_side(getattr(fill.execution, "side", None) or "")
            if not sym or not side:
                continue
            key = (sym, side)
            tws_map.setdefault(key, []).append(fill)
        except Exception:
            continue

    # 7. Update pending records
    synced = 0
    for i in pending_idxs:
        r = records[i]
        ticker = (r.get("ticker") or "").strip().upper()
        side = (r.get("side") or "").upper()
        if not ticker or not side:
            continue
        fills_list = tws_map.get((ticker, side)) or []
        if not fills_list:
            continue
        fill = fills_list.pop(0)
        try:
            shares = int(getattr(fill.execution, "shares", 0) or getattr(fill.execution, "cumQty", 0) or 0)
            avg_price = float(getattr(fill.execution, "avgPrice", 0) or getattr(fill.execution, "price", 0) or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        qty_req = int(r.get("qty_requested") or 0)
        r["qty_filled"] = shares
        r["avg_fill_price"] = avg_price
        r["status"] = "full" if shares >= qty_req else "partial"
        r["fill_check_passed"] = True
        r["fill_check_reason"] = f"synced from TWS executions on {date_str}"
        synced += 1

    # 8. Rewrite fills.jsonl
    try:
        FILLS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(FILLS_PATH, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"WARNING: Could not write {FILLS_PATH}: {e}", flush=True)
        return 0

    still_pending = len(pending_idxs) - synced
    print(f"Synced {synced} fill(s) from TWS. {still_pending} record(s) still pending.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_main())
