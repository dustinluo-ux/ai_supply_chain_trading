"""
Task 7: Standalone daily workflow runner.

Runs update_price_data (with SPY), update_news_data, then generate_daily_weights
via subprocess. Reads watchlist from data_config.yaml (no CLI args required).
Non-fatal step failures; exits 0 when all steps have been attempted.

Usage:
  python scripts/daily_workflow.py
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    try:
        from src.utils.config_manager import get_config
    except Exception as e:
        logger.error("Failed to load config: %s", e)
        return 1

    cfg = get_config()
    watchlist = cfg.get_watchlist()
    if not watchlist:
        logger.error("Watchlist empty in data_config.yaml")
        return 1
    watchlist_tickers = ",".join(watchlist)
    benchmark = "SPY"
    try:
        bench = cfg.get_param("data_config.universe_selection.benchmark", "SPY")
        if bench:
            benchmark = str(bench)
    except Exception:
        pass
    tickers_with_spy = watchlist_tickers + "," + benchmark if benchmark not in watchlist else watchlist_tickers

    py = sys.executable
    scripts_dir = ROOT / "scripts"

    # 1. Price update (watchlist + SPY)
    r1 = subprocess.run(
        [py, str(scripts_dir / "update_price_data.py"), "--tickers", tickers_with_spy],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_price_data.py exit code: %s", r1.returncode)

    # 2. News update (watchlist only)
    r2 = subprocess.run(
        [py, str(scripts_dir / "update_news_data.py"), "--tickers", watchlist_tickers],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("update_news_data.py exit code: %s", r2.returncode)

    # 3. Generate daily weights
    r3 = subprocess.run(
        [py, str(scripts_dir / "generate_daily_weights.py")],
        cwd=str(ROOT),
        capture_output=False,
    )
    logger.info("generate_daily_weights.py exit code: %s", r3.returncode)

    print("Daily workflow complete.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
