"""
Main Strategy Runner
Orchestrates complete pipeline: Data → Signals → Backtest → Results
"""
import sys
import argparse
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from run_phase1_test import test_price_fetcher, test_news_fetcher, test_llm_analyzer, load_config
from run_phase2_pipeline import run_phase2_pipeline
from run_phase3_backtest import run_phase3_backtest

logger = setup_logger()


def main():
    parser = argparse.ArgumentParser(description='AI Supply Chain Trading Strategy')
    parser.add_argument('--phase', type=str, choices=['1', '2', '3', 'all'],
                       default='all', help='Phase to run (1=data, 2=signals, 3=backtest, all=complete)')
    parser.add_argument('--tickers', type=str, nargs='+', default=None,
                       help='Specific tickers to process (default: all available)')
    parser.add_argument('--date', type=str, default=None,
                       help='Date for signal generation (YYYY-MM-DD, default: latest)')
    
    args = parser.parse_args()
    
    config = load_config()
    
    logger.info("=" * 60)
    logger.info("AI SUPPLY CHAIN TRADING STRATEGY")
    logger.info("=" * 60)
    
    if args.phase in ['1', 'all']:
        logger.info("\n>>> Running Phase 1: Data Infrastructure")
        try:
            test_price_fetcher(config)
            test_news_fetcher(config)
            test_llm_analyzer(config)
            logger.info("✅ Phase 1 complete")
        except Exception as e:
            logger.error(f"Phase 1 failed: {e}")
            return
    
    if args.phase in ['2', 'all']:
        logger.info("\n>>> Running Phase 2: Signal Generation")
        try:
            top_stocks = run_phase2_pipeline(config, tickers=args.tickers, date=args.date)
            if top_stocks is not None:
                logger.info("✅ Phase 2 complete")
            else:
                logger.warning("Phase 2 completed with warnings")
        except Exception as e:
            logger.error(f"Phase 2 failed: {e}")
            return
    
    if args.phase in ['3', 'all']:
        logger.info("\n>>> Running Phase 3: Backtesting")
        try:
            results = run_phase3_backtest(config)
            if results:
                logger.info("✅ Phase 3 complete")
            else:
                logger.warning("Phase 3 completed with warnings")
        except Exception as e:
            logger.error(f"Phase 3 failed: {e}")
            return
    
    logger.info("\n" + "=" * 60)
    logger.info("STRATEGY RUN COMPLETE")
    logger.info("=" * 60)
    logger.info("Check outputs in:")
    logger.info("  - data/ (price, news, signals)")
    logger.info("  - backtests/results/ (performance reports, plots)")


if __name__ == "__main__":
    main()
