"""
Phase 2 Pipeline: Signal Generation
Orchestrates supply chain scanning, sentiment analysis, technical indicators, and signal combination
"""
import sys
import os
import yaml
from pathlib import Path
from datetime import datetime

# Add src to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.utils.logger import setup_logger
from src.data.price_fetcher import PriceFetcher
from src.data.news_fetcher import NewsFetcher
from src.signals.supply_chain_scanner import SupplyChainScanner
from src.signals.sentiment_analyzer import SentimentAnalyzer
from src.signals.technical_indicators import TechnicalIndicators
from src.signals.signal_combiner import SignalCombiner

logger = setup_logger()


def run_technical_only_pipeline(config, tickers: list = None, date: str = None):
    """Run technical-only pipeline (no news/LLM)"""
    logger.info("Running technical-only signal generation...")
    
    # Step 1: Get tickers
    if tickers is None:
        price_dir = Path("data/prices")
        if price_dir.exists():
            tickers = [f.stem for f in price_dir.glob("*.parquet")]
        else:
            logger.warning("No price data found. Run Phase 1 first.")
            return None
    
    # Step 2: Technical Indicators
    logger.info("Calculating technical indicators...")
    tech_indicators = TechnicalIndicators(
        data_dir="data/prices",
        output_dir="data"
    )
    
    indicators_df = tech_indicators.process_all_tickers(
        tickers,
        short_momentum=config['technical']['momentum_short'],
        long_momentum=config['technical']['momentum_long'],
        volume_window=config['technical']['volume_window'],
        rsi_period=config['technical']['rsi_period'],
        bb_period=config['technical']['bollinger_period'],
        bb_std=config['technical']['bollinger_std']
    )
    
    logger.info(f"✅ Generated technical indicators for {indicators_df['ticker'].nunique()} tickers")
    
    # Step 3: Generate signals
    logger.info("Generating technical signals...")
    combiner = SignalCombiner(data_dir="data", output_dir="data/signals")
    
    top_stocks = combiner.get_top_stocks(
        date=date,
        top_n=config['backtest']['portfolio_size'],
        mode="technical_only",
        min_price_momentum=0.0
    )
    
    logger.info(f"✅ Generated technical signals for {len(top_stocks)} stocks")
    return top_stocks


def load_config():
    """Load configuration"""
    config_path = project_root / "config" / "config.yaml"
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def run_phase2_pipeline(config, tickers: list = None, date: str = None):
    """
    Run complete Phase 2 signal generation pipeline
    
    Args:
        config: Configuration dict
        tickers: List of tickers to process (if None, uses all available)
        date: Date to generate signals for (if None, uses latest)
    """
    logger.info("=" * 60)
    logger.info("PHASE 2: Signal Generation Pipeline")
    logger.info("=" * 60)
    
    # Check mode
    mode = config['backtest'].get('mode', 'full_with_news')
    logger.info(f"Mode: {mode}")
    
    if mode == 'technical_only':
        logger.info("Technical-only mode: Skipping news/LLM steps")
        # Skip news and LLM steps, go straight to technical indicators
        return run_technical_only_pipeline(config, tickers, date)
    
    # Step 1: Ensure we have price data
    logger.info("\n[Step 1/5] Checking price data...")
    price_fetcher = PriceFetcher(
        data_dir="data/prices",
        min_market_cap=config['market_cap']['min'],
        max_market_cap=config['market_cap']['max']
    )
    
    if tickers is None:
        # Get tickers from price data directory
        price_dir = Path("data/prices")
        if price_dir.exists():
            tickers = [f.stem for f in price_dir.glob("*.parquet")]
        else:
            logger.warning("No price data found. Run Phase 1 first or provide tickers.")
            return None
    
    logger.info(f"Processing {len(tickers)} tickers")
    
    # Check if technical-only mode
    if mode == 'technical_only':
        logger.info("Technical-only mode: Skipping news/LLM steps")
        return run_technical_only_pipeline(config, tickers, date)
    
    # Full pipeline with news/LLM
    # Step 2: Supply Chain Scanner
    logger.info("\n[Step 2/5] Running supply chain scanner...")
    scanner = SupplyChainScanner(
        llm_provider=config['llm']['provider'],
        llm_model=config['llm']['model'],
        data_dir="data/news",
        output_dir="data"
    )
    
    supply_chain_scores = scanner.scan_all_tickers(tickers, use_cache=True)
    logger.info(f"✅ Scanned {len(supply_chain_scores)} tickers for supply chain mentions")
    
    # Step 3: Sentiment Analyzer
    logger.info("\n[Step 3/5] Running sentiment analyzer...")
    sentiment_analyzer = SentimentAnalyzer(
        data_dir="data/news",
        output_dir="data"
    )
    
    # Load articles for sentiment analysis
    articles_dict = {}
    for ticker in tickers:
        news_path = Path("data/news") / f"{ticker}_news.json"
        if news_path.exists():
            import json
            with open(news_path, 'r') as f:
                articles_dict[ticker] = json.load(f)
        else:
            articles_dict[ticker] = []
    
    sentiment_ts = sentiment_analyzer.process_all_tickers(
        tickers,
        articles_dict,
        short_window=config['sentiment']['rolling_short'],
        long_window=config['sentiment']['rolling_long']
    )
    logger.info(f"✅ Generated sentiment time series for {sentiment_ts['ticker'].nunique()} tickers")
    
    # Step 4: Technical Indicators
    logger.info("\n[Step 4/5] Calculating technical indicators...")
    tech_indicators = TechnicalIndicators(
        data_dir="data/prices",
        output_dir="data"
    )
    
    indicators_df = tech_indicators.process_all_tickers(
        tickers,
        short_momentum=config['technical']['momentum_short'],
        long_momentum=config['technical']['momentum_long'],
        volume_window=config['technical']['volume_window'],
        rsi_period=config['technical']['rsi_period'],
        bb_period=config['technical']['bollinger_period'],
        bb_std=config['technical']['bollinger_std']
    )
    logger.info(f"✅ Calculated technical indicators for {indicators_df['ticker'].nunique()} tickers")
    
    # Step 5: Signal Combiner
    logger.info("\n[Step 5/5] Combining signals...")
    combiner = SignalCombiner(
        data_dir="data",
        output_dir="data/signals"
    )
    
    # Set weights from config
    combiner.set_weights(config['signal_weights'])
    
    # Get top stocks
    top_stocks = combiner.get_top_stocks(
        date=date,
        top_n=config['backtest']['portfolio_size'],
        mode="full_with_news",
        min_sentiment_momentum=config['filters']['min_sentiment_momentum'],
        min_market_cap=config['filters'].get('min_market_cap'),
        max_market_cap=config['filters'].get('max_market_cap')
    )
    
    logger.info(f"✅ Generated composite signals for {len(top_stocks)} stocks")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 2 COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Top {len(top_stocks)} stocks by composite signal:")
    if not top_stocks.empty:
        for idx, row in top_stocks.head(10).iterrows():
            logger.info(f"  {row['rank']}. {row['ticker']}: {row['composite_signal']:.4f}")
    
    return top_stocks


if __name__ == "__main__":
    config = load_config()
    
    # Run pipeline
    # You can specify tickers or let it use all available
    # You can specify a date or use latest
    top_stocks = run_phase2_pipeline(config, tickers=None, date=None)
    
    if top_stocks is not None and not top_stocks.empty:
        print("\n✅ Phase 2 pipeline complete!")
        print(f"Top stocks saved to: data/signals/top_stocks_latest.csv")
    else:
        print("\n⚠️  Phase 2 pipeline completed with warnings. Check logs above.")
