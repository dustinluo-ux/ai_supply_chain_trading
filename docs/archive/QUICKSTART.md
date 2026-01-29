# Quick Start Guide

## 1. Install Dependencies

```bash
pip install -r requirements.txt
```

## 2. Setup API Keys

Run the setup script:
```bash
python setup_env.py
```

Then edit `.env` file and add your API keys:

- **NEWS_API_KEY**: Get free key from https://newsapi.org/register (100 requests/day)
- **ANTHROPIC_API_KEY**: Get from https://console.anthropic.com/ (for Claude API)
- **ALPACA keys**: Get from https://alpaca.markets/ (for Phase 4 paper trading)

## 3. Test Phase 1

```bash
python run_phase1_test.py
```

This will test:
- Price data fetching (works without API keys)
- News data fetching (requires NEWS_API_KEY)
- LLM analyzer (requires ANTHROPIC_API_KEY, or uses FinBERT as fallback)

## 4. Fetch Data

### Fetch Price Data
```python
from src.data.price_fetcher import PriceFetcher

fetcher = PriceFetcher()
results = fetcher.run(start_date="2023-01-01", end_date="2024-12-31")
```

### Fetch News Data
```python
from src.data.news_fetcher import NewsFetcher

fetcher = NewsFetcher()
results = fetcher.fetch_all_tickers(
    tickers=['NVDA', 'AMD', 'MU'],
    start_date="2023-01-01",
    end_date="2024-12-31"
)
```

### Test LLM Analyzer
```python
from src.signals.llm_analyzer import LLMAnalyzer

# Using Claude (requires API key)
analyzer = LLMAnalyzer(provider="anthropic", model="claude-sonnet-4")

# Or using FinBERT (free, local)
analyzer = LLMAnalyzer(provider="finbert")

# Analyze article
result = analyzer.analyze_article(article_dict)
```

## What's Next?

Phase 1 is complete! Ready to proceed to Phase 2:
- Supply chain scanner (batch LLM processing)
- Sentiment analyzer (time series)
- Technical indicators
- Signal combiner

See `PHASE1_SUMMARY.md` for details.
