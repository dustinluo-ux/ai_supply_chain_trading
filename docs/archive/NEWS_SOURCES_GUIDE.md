# News Sources Guide

## Modular News Fetcher System

The news fetcher now supports multiple data sources that can be switched via configuration.

## Available Sources

### 1. Alpha Vantage (Recommended) ⭐
- **Free tier**: 5 calls per minute, 500 per day
- **Historical data**: Yes, back to 2023
- **API Key**: Get free key from https://www.alphavantage.co/support/#api-key
- **Best for**: Historical backtesting (has data going back)

### 2. NewsAPI
- **Free tier**: 100 requests per day
- **Historical data**: Limited (1 month)
- **API Key**: Get free key from https://newsapi.org/register
- **Best for**: Recent news only

### 3. Finnhub
- **Free tier**: 60 calls per minute
- **Historical data**: Limited
- **API Key**: Get free key from https://finnhub.io/register
- **Status**: Stub implementation (needs completion)

## Configuration

Edit `config/config.yaml`:

```yaml
news:
  source: "alphavantage"  # Options: "newsapi", "alphavantage", "finnhub"
```

## Usage

### Method 1: Using Config (Recommended)

```python
from src.data.news_fetcher import NewsFetcher

# Automatically reads from config.yaml
fetcher = NewsFetcher()
articles = fetcher.fetch_articles_for_ticker('NVDA', '2023-01-01', '2024-12-31')
```

### Method 2: Direct Source Selection

```python
from src.data.news_fetcher_factory import NewsFetcherFactory

# Create specific source
source = NewsFetcherFactory.create_source('alphavantage', keywords=['AI', 'GPU'])
articles = source.fetch_articles_for_ticker('NVDA', '2023-01-01', '2024-12-31')
```

### Method 3: List Available Sources

```python
from src.data.news_fetcher_factory import NewsFetcherFactory

sources = NewsFetcherFactory.list_available_sources()
print(sources)  # ['newsapi', 'alphavantage', 'finnhub']
```

## API Keys

Add to `.env` file:

```bash
# For Alpha Vantage (recommended)
ALPHAVANTAGE_API_KEY=your_key_here

# For NewsAPI
NEWS_API_KEY=your_key_here

# For Finnhub
FINNHUB_API_KEY=your_key_here
```

## Architecture

```
NewsDataSource (abstract base)
├── NewsAPISource (existing implementation)
├── AlphaVantageSource (new - has historical data)
└── FinnhubSource (stub - needs implementation)

NewsFetcherFactory
└── Creates appropriate source based on config
```

## Adding New Sources

1. Create new class in `src/data/news_sources/your_source.py`
2. Inherit from `NewsDataSource`
3. Implement `fetch_articles_for_ticker()` and `get_name()`
4. Register in `NewsFetcherFactory._sources` dict
5. Add config section in `config.yaml`

Example:

```python
from src.data.news_base import NewsDataSource

class YourSource(NewsDataSource):
    def get_name(self) -> str:
        return "yoursource"
    
    def fetch_articles_for_ticker(self, ticker, start_date, end_date, use_cache=True):
        # Your implementation
        pass
```

## Backward Compatibility

The old `NewsFetcher` class still works - it now uses the factory pattern internally. All existing code continues to work without changes.

## Rate Limits

- **Alpha Vantage**: 5 calls/min, 500/day (automatic rate limiting)
- **NewsAPI**: 100 requests/day (automatic rate limiting)
- **Finnhub**: 60 calls/min (automatic rate limiting)

The system automatically handles rate limiting for each source.

## Testing

```bash
# Test with current config source
python src/data/news_fetcher.py

# Or test specific source
python -c "from src.data.news_fetcher_factory import NewsFetcherFactory; s = NewsFetcherFactory.create_source('alphavantage'); print(s.fetch_articles_for_ticker('NVDA', '2024-01-01', '2024-01-31'))"
```
