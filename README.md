# AI Supply Chain Thematic Trading System

A quantitative trading system that uses LLM analysis to identify AI supply chain beneficiaries before Wall Street consensus.

## Strategy Concept

Use LLM to scan news for AI supply chain beneficiaries. Trade small-cap stocks ($500M-$5B market cap) that are 2nd/3rd order beneficiaries of AI scaling.

**Example Flow:**
- OpenAI launches Sora → video needs massive storage → SSD demand spikes → buy SNDK (Western Digital) before consensus → ran 40%+

## Target Performance

- Sharpe ratio >1.5 in backtest (2023-2024 period)
- Max drawdown <15%
- Win rate >55%
- Outperform SPY benchmark

## Quick Start

### 1. Setup Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file (copy from .env.template)
# Add your API keys:
# - NEWS_API_KEY (from newsapi.org - free tier: 100 requests/day)
# - ALPACA_API_KEY (for paper trading in Phase 4)
# Note: Using FinBERT (local, free) - no LLM API key needed!
```

### 2. Phase 1: Fetch Data

```bash
# Fetch price data for Russell 2000 stocks
python src/data/price_fetcher.py

# Fetch news articles
python src/data/news_fetcher.py

# Test LLM extraction
python src/signals/llm_analyzer.py
```

### 3. Run Complete Pipeline

```bash
# Run all phases (data → signals → backtest)
python run_strategy.py --phase all

# Or run individual phases
python run_strategy.py --phase 1  # Data infrastructure
python run_strategy.py --phase 2  # Signal generation
python run_strategy.py --phase 3  # Backtesting
```

## Project Structure

```
ai_supply_chain_trading/
├── data/
│   ├── prices/          # OHLCV data (parquet)
│   ├── news/            # News articles (JSON)
│   └── cache/           # Cached data
├── src/
│   ├── data/            # Data fetchers (price, news)
│   ├── signals/         # Signal generation (LLM, sentiment, technical)
│   ├── backtest/        # Backtesting engine
│   └── execution/       # Live trading (Phase 4)
├── backtests/
│   └── results/         # Backtest outputs (plots, reports)
├── config/
│   └── config.yaml      # Strategy configuration
└── logs/                # Application logs
```

## Configuration

Edit `config/config.yaml` to adjust:
- Signal weights
- Market cap filters
- Backtest parameters
- LLM provider (FinBERT - local, free)

## Architecture

**Source-Agnostic Design:**
- Data pipeline accepts multiple sources (news, SEC filings, earnings, social media)
- Modular loaders: add new sources without modifying existing code
- Base loader pattern for extensibility

**LLM Integration:**
- Uses FinBERT (local, free) for sentiment and AI relevance detection
- Extracts: AI relevance, sentiment, keyword-based supply chain detection
- Batch processing (no API rate limits)

## Status

- ✅ Phase 1: Data Infrastructure - **COMPLETE**
- ✅ Phase 2: Signal Generation - **COMPLETE**
- ✅ Phase 3: Backtesting - **COMPLETE**
- ⏳ Phase 4: Production & Paper Trading - **PENDING**

See `PROJECT_STATUS.md` for detailed status and `PHASE*_SUMMARY.md` for each phase.

## License

[Your License Here]
