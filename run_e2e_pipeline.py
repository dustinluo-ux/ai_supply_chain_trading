"""
E2E pipeline test: Warm-Up data -> Signals -> Weekly rebalance (dry-run).

Uses setup_logger() so all output is saved to logs/ai_supply_chain_YYYYMMDD.log.
Run with: python run_e2e_pipeline.py [--no-warmup] [--mode technical_only]
"""
import os
import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.utils.yfinance_cache_init import init_yfinance_cache

logger = setup_logger()
init_yfinance_cache()


def load_config():
    path = project_root / "config" / "config.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run_e2e(use_warmup: bool = True, mode: str = "technical_only"):
    """
    Run end-to-end: optional warm-up -> signal combiner -> weekly rebalance (dry-run).
    """
    logger.info("=" * 60)
    logger.info("E2E PIPELINE TEST (dry-run)")
    logger.info("=" * 60)
    config = load_config()
    date_range = config.get("data", {}).get("date_range", {})
    start = date_range.get("start", "2023-01-01")
    end = date_range.get("end", "2024-12-31")

    # 1) Optional warm-up (small ticker set for test)
    tickers = None
    if use_warmup:
        try:
            from src.data.warmup import warm_up
            test_tickers = ["SPY", "AAPL", "NVDA", "MSFT", "GOOGL"]
            logger.info(f"Warm-Up: loading historical + recent for {test_tickers}")
            warmed = warm_up(test_tickers, start, end, last_n_days=30, use_recent=True)
            tickers = list(warmed.keys())
            logger.info(f"Warm-Up done: {len(tickers)} tickers")
        except Exception as e:
            logger.warning(f"Warm-Up skipped: {e}")

    # 2) Signal combiner -> top N
    from src.signals.signal_combiner import SignalCombiner
    combiner = SignalCombiner(data_dir="data", output_dir="data/signals")
    combiner.set_weights(config.get("signal_weights", combiner.weights))
    top_n = config.get("backtest", {}).get("portfolio_size", 10)
    top_stocks = combiner.get_top_stocks(date=None, top_n=top_n, mode=mode)
    if top_stocks is None or top_stocks.empty:
        logger.warning("No top stocks; E2E stops (run Phase 2 or ensure data/signals exist).")
        return
    logger.info(f"Top {len(top_stocks)} stocks: {top_stocks['ticker'].tolist()}")

    # 3) Weekly rebalance (dry-run)
    from run_weekly_rebalance import run_weekly_rebalance
    run_weekly_rebalance(date=None, top_n=top_n, dry_run=True, mode=mode)
    logger.info("E2E pipeline test complete (dry-run).")


def main():
    parser = argparse.ArgumentParser(description="E2E pipeline: warm-up -> signals -> rebalance dry-run")
    parser.add_argument("--no-warmup", action="store_true", help="Skip warm-up step")
    parser.add_argument("--mode", type=str, default="technical_only", choices=["technical_only", "full_with_news"])
    args = parser.parse_args()
    run_e2e(use_warmup=not args.no_warmup, mode=args.mode)


if __name__ == "__main__":
    main()
