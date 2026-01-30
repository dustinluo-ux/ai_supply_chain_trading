"""
Weekly rebalance runner: Composite Score (momentum + sentiment) -> rank -> target weights
-> delta trades -> BUY/SELL/HOLD -> optional execution (dry-run or live).

Uses setup_logger() so output is saved to logs/.
"""
import os
import sys
import argparse
import yaml
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.utils.yfinance_cache_init import init_yfinance_cache
from src.signals.signal_combiner import SignalCombiner
from src.portfolio.position_manager import PositionManager
from src.execution.executor_factory import ExecutorFactory

logger = setup_logger()

# Optional: init yfinance cache to avoid SQLite issues
init_yfinance_cache()


def load_config():
    path = project_root / "config" / "config.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_trading_config():
    path = project_root / "config" / "trading_config.yaml"
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)


def run_weekly_rebalance(
    date: str = None,
    top_n: int = 10,
    dry_run: bool = True,
    mode: str = "technical_only",
):
    """
    Run weekly rebalance: signals -> optimal weights -> delta trades -> optional submit.

    Args:
        date: Signal date (YYYY-MM-DD); if None, use latest.
        top_n: Number of top stocks to hold (equal weight).
        dry_run: If True, do not submit orders; only log trades.
        mode: "technical_only" or "full_with_news".
    """
    logger.info("=" * 60)
    logger.info("WEEKLY REBALANCE RUN")
    logger.info("=" * 60)
    logger.info(f"date={date}, top_n={top_n}, dry_run={dry_run}, mode={mode}")

    config = load_config()
    trading = load_trading_config().get("trading", {})
    executor_type = trading.get("executor", "mock")
    initial_capital = trading.get("initial_capital", 100_000)

    # 1) Composite score -> top N
    combiner = SignalCombiner(data_dir="data", output_dir="data/signals")
    combiner.set_weights(config.get("signal_weights", combiner.weights))
    top_stocks = combiner.get_top_stocks(date=date, top_n=top_n, mode=mode)
    if top_stocks is None or top_stocks.empty:
        logger.warning("No top stocks from signal combiner; aborting rebalance.")
        return

    tickers = top_stocks["ticker"].tolist()
    optimal_weights = dict(zip(tickers, [1.0 / len(tickers)] * len(tickers)))
    optimal_weights_series = __import__("pandas").pd.Series(optimal_weights)

    # 2) Executor and position manager
    executor = ExecutorFactory.from_config_file()
    position_manager = PositionManager(executor)
    account_value = position_manager.get_account_value()
    if account_value <= 0:
        account_value = float(initial_capital)
        logger.info(f"Using initial_capital as account value: {account_value}")
    current_positions = position_manager.get_current_positions()
    current_weights = position_manager.positions_to_weights(current_positions)

    # 3) Delta trades (no prices -> quantities may be 0; executor can use current price)
    prices = None  # Optional: pass current prices for exact qty
    delta_trades = position_manager.calculate_delta_trades(
        current_weights=current_weights,
        optimal_weights=optimal_weights_series,
        account_value=account_value,
        prices=prices,
        min_trade_size=0.005,
        significance_threshold=0.02,
    )
    executable = delta_trades[delta_trades["should_trade"] & (delta_trades["quantity"] > 0)]

    logger.info(f"Account value: {account_value:,.2f}")
    logger.info(f"Optimal tickers: {tickers}")
    logger.info(f"Executable trades: {len(executable)}")
    for _, row in executable.iterrows():
        logger.info(f"  {row['side']} {row['quantity']} {row['symbol']} (delta_w={row['delta_weight']:+.2%})")

    if dry_run:
        logger.info("DRY RUN: No orders submitted.")
        return

    # 4) Submit orders
    for _, row in executable.iterrows():
        try:
            executor.submit_order(
                ticker=row["symbol"],
                quantity=int(row["quantity"]),
                side=row["side"],
                order_type="MARKET",
            )
        except Exception as e:
            logger.error(f"Order failed {row['symbol']}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Weekly rebalance: signals -> delta trades -> optional execution")
    parser.add_argument("--date", type=str, default=None, help="Signal date (YYYY-MM-DD)")
    parser.add_argument("--top-n", type=int, default=10, help="Top N stocks")
    parser.add_argument("--dry-run", action="store_true", help="Do not submit orders (default)")
    parser.add_argument("--live", action="store_true", help="Submit orders to broker")
    parser.add_argument("--mode", type=str, default="technical_only", choices=["technical_only", "full_with_news"])
    args = parser.parse_args()
    dry_run = not args.live
    run_weekly_rebalance(date=args.date, top_n=args.top_n, dry_run=dry_run, mode=args.mode)


if __name__ == "__main__":
    main()
