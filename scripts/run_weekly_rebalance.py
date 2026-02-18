# Canonical Automated Rebalancing entry point.
# Delegates to scripts/run_execution.py (same spine: target_weight_pipeline -> Intent -> PositionManager -> delta trades).
# Logic adapted from graveyard/run_weekly_rebalance.py; uses backtest-style scoring (no SignalCombiner).
"""
Weekly rebalance: signals -> target weights -> delta trades -> optional execution.

Uses canonical spine (SignalEngine -> PolicyEngine -> PortfolioEngine) via
target_weight_pipeline; tickers from config/data_config.yaml watchlist by default.

Usage:
  python scripts/run_weekly_rebalance.py --dry-run
  python scripts/run_weekly_rebalance.py --live --confirm-paper
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def _get_watchlist() -> list[str]:
    """Load default tickers from config/data_config.yaml universe_selection.watchlist."""
    path = ROOT / "config" / "data_config.yaml"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        watchlist = data.get("universe_selection", {}).get("watchlist", [])
        return list(watchlist) if isinstance(watchlist, list) else []
    except Exception:
        return []


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Weekly rebalance: canonical spine -> delta trades -> optional execution (delegates to run_execution)."
    )
    parser.add_argument("--date", type=str, default=None, help="Signal date YYYY-MM-DD; default: latest Monday")
    parser.add_argument("--top-n", type=int, default=3, help="Top N for portfolio")
    parser.add_argument("--tickers", type=str, default=None, help="Comma-separated tickers; default: watchlist from data_config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Do not submit orders (default)")
    parser.add_argument("--live", action="store_true", help="Use IB paper account (implies --confirm-paper if not --dry-run)")
    parser.add_argument("--confirm-paper", action="store_true", help="With --live: actually submit orders to paper account")
    args = parser.parse_args()

    tickers = args.tickers
    if not tickers:
        watchlist = _get_watchlist()
        if not watchlist:
            print("ERROR: No tickers. Set --tickers or config/data_config.yaml universe_selection.watchlist.", flush=True)
            return 1
        tickers = ",".join(watchlist)
    else:
        tickers = ",".join(t.strip() for t in tickers.split(",") if t.strip())
    if not tickers:
        print("ERROR: No tickers provided.", flush=True)
        return 1

    # Build argv for run_execution.main()
    argv = [
        "run_execution",
        "--tickers", tickers,
        "--top-n", str(args.top_n),
    ]
    if args.date:
        argv.extend(["--date", args.date])
    if args.live:
        argv.extend(["--mode", "paper"])
        if args.confirm_paper and not args.dry_run:
            argv.append("--confirm-paper")
    else:
        argv.extend(["--mode", "mock"])

    # Delegate to canonical execution entry point (same spine + PositionManager + delta trades)
    import run_execution
    old_argv = sys.argv
    try:
        sys.argv = argv
        return run_execution.main()
    finally:
        sys.argv = old_argv


if __name__ == "__main__":
    sys.exit(main())
