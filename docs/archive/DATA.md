# Data Sources and Management

**Last Updated:** 2026-01-29

---

## Warm-Up and Self-Healing

- **Warm-Up:** `src/data/warmup.py` — Loads historical from `data/prices/` (parquet), optionally fetches last 30 days from yfinance (Recent), merges with no gap. Use `warm_up(tickers, start_date, end_date, last_n_days=30)` before pipeline steps that need continuous data.
- **Self-Healing:** After any live fetch, call `heal_append(ticker, new_bars_df, data_dir="data/prices")` to append new bars to the historical store (duplicate dates dropped).
- **Historical store:** `data/prices/` is the append target for price data; same dir is used for Warm-Up historical load.

---

## Price Data

### Source

Historical stock market data from multiple sources:
- NASDAQ
- S&P 500
- NYSE
- Forbes 2000

### Location

Configured in `config/data_config.yaml`:
```yaml
data_sources:
  data_dir: "data/prices"  # or custom path
  subdirectories:
    - "nasdaq/csv"
    - "sp500/csv"
    - "forbes2000/csv"
    - "nyse/csv"
```

### Format

- **File Format:** CSV
- **File Naming:** `{TICKER}.csv` (e.g., `NVDA.csv`)
- **Required Columns:**
  - `Date` or `date` (index column)
  - `Close` or `close` (closing price)
  - `Volume` or `volume` (optional but recommended)

### Validation

`UniverseLoader` validates:
- Minimum data points (default: 252 trading days)
- Date range coverage
- Missing days ratio (max 10%)
- Minimum price (exclude penny stocks < $1.00)

---

## News Data

### Source: FNSPID Dataset

**FNSPID (Financial News Sentiment and Price Impact Dataset)**
- **Repository:** [Zihan1004/FNSPID](https://huggingface.co/datasets/Zihan1004/FNSPID) on Hugging Face
- **File:** `Stock_news/nasdaq_exteral_data.csv`
- **Coverage:** NASDAQ, typically 2010-2022
- **Article Count:** ~15 million articles

### Download

```bash
# Install dependencies
pip install huggingface_hub pandas pyarrow

# Set token
export HF_TOKEN=your_token_here

# Download
python scripts/download_fnspid.py
```

Saves to: `data/raw/fnspid_nasdaq_news.csv`

### Processing

```bash
python scripts/process_fnspid.py \
  --input data/raw/fnspid_nasdaq_news.csv \
  --output data/news/ \
  --date-start 2020-01-01 \
  --date-end 2022-12-31
```

**What it does:**
1. Filters by date range
2. Filters by supply chain keywords (90% reduction)
3. Extracts ticker symbols
4. Converts to JSON format
5. Saves to `data/news/{TICKER}_news.json`

### Keyword Filtering

Articles filtered to include only those mentioning:
- Supply chain: `supply`, `supplier`, `contract`, `partnership`
- Infrastructure: `datacenter`, `data center`, `cloud`, `hyperscaler`
- AI/Technology: `AI`, `artificial intelligence`, `GPU`, `CPU`, `chip`, `semiconductor`
- Companies: `AWS`, `Azure`, `GCP`, `Microsoft`, `Google`, `Amazon`, `NVIDIA`, `AMD`, `Intel`, `TSMC`
- Other: `manufacturing`, `order`, `infrastructure`, `server`

**Result:** ~15M → ~1.5M articles (90% reduction)

### Output Format

**File:** `data/news/{TICKER}_news.json`

**JSON Structure:**
```json
[
  {
    "title": "NVIDIA Announces Record GPU Orders",
    "description": "NVIDIA reports unprecedented demand...",
    "content": "NVIDIA Corporation announced today...",
    "publishedAt": "2023-06-15T10:00:00Z"
  }
]
```

Articles sorted by date (newest first).

---

## Cache Management

### Gemini API Cache

**Location:** `data/cache/gemini_*.json`

**Purpose:** Avoid re-analyzing same articles

**Format:**
```json
{
  "ticker": "NVDA",
  "date_range": "2023-06-08 to 2023-06-15",
  "articles_analyzed": 5,
  "scores": {
    "supply_chain_score": 0.95,
    "sentiment_score": 0.8,
    "confidence": 0.9
  }
}
```

**Cache Key:** `{ticker}_{start_date}_{end_date}`

### Supply Chain Extractions Cache

**Location:** `data/{TICKER}_extractions.json`

**Purpose:** Cache LLM extractions (supplier/customer relationships)

**Format:**
```json
[
  {
    "supplier": "TSM",
    "customer": "NVDA",
    "ai_related": true,
    "relevance_score": 0.85,
    "sentiment": 0.7
  }
]
```

---

## Supply Chain Database

**Location:** `data/supply_chain_relationships.json`

**Purpose:** Supplier-customer-competitor relationships for sentiment propagation

**Structure:**
```json
{
  "metadata": {
    "last_updated": "2026-01-25",
    "version": "1.0"
  },
  "relationships": {
    "AAPL": {
      "suppliers": [...],
      "customers": [...],
      "competitors": [...]
    }
  }
}
```

**See:** `docs/SUPPLY_CHAIN_DB.md` for full details.

---

## Data Workflow

### Initial Setup

1. **Download price data** → Save CSV files to `data/prices/`
2. **Download FNSPID** → `python scripts/download_fnspid.py`
3. **Process FNSPID** → `python scripts/process_fnspid.py`
4. **Build supply chain DB** → `python scripts/build_supply_chain_db.py`

### Daily/Weekly Updates

**Price Data:**
- Download new CSV files
- Replace old files (or append if format supports)

**News Data:**
- Re-download FNSPID if updated
- Re-run `process_fnspid.py` with new date range

**Supply Chain DB:**
- Run `python scripts/expand_database_core_stocks.py` to add new stocks
- Manual verification for flagged stocks

---

## Date Range Detection

### Best Coverage Approach

**Current Implementation:**
1. Scans all news files to find month with most tickers
2. Filters to tickers with BOTH price data AND news in that month
3. Uses that month for backtest

**Limitation:** Uses single month, not full multi-month period

**Fallback:** Union approach (all available dates)

---

## Data Quality Checks

### Price Data

- **Missing columns:** Falls back to defaults (volume = 1.0)
- **Date parsing:** Handles multiple formats
- **Empty data:** Skips ticker

### News Data

- **Missing files:** Returns `None` (no fallback)
- **Empty articles:** Returns `None`
- **Date parsing:** Handles ISO, space-separated formats

### Supply Chain DB

- **Missing ticker:** Returns empty relationships
- **Stale data:** Warns if > 6 months old
- **Auto-research:** Attempts to download 10-Ks (requires network)

---

## Disk Space Management

### Cache Cleanup

**Old cache files:**
- `data/supply_chain_mentions.csv` (legacy)
- `data/*_extractions.json` (if stale)

**Backup before deletion:**
```bash
python scripts/backup_cache_files.py
```

### News Data Size

- **Raw FNSPID:** ~15M articles, ~10-20 GB
- **Processed:** ~1.5M articles, ~1-2 GB
- **Per ticker:** 1,000-50,000 articles, ~1-50 MB

---

## Troubleshooting

### No News Data

**Symptoms:** All news signals are `None`

**Solutions:**
1. Check `data/news/` directory exists
2. Verify `{TICKER}_news.json` files exist
3. Check date range matches news data
4. Run `process_fnspid.py` if missing

### No Price Data

**Symptoms:** Tickers skipped in backtest

**Solutions:**
1. Check `config/data_config.yaml` paths
2. Verify CSV files exist in subdirectories
3. Check CSV format (columns: `close`, `date`)
4. Verify date range in CSV matches config

### Cache Issues

**Symptoms:** Stale scores, incorrect rankings

**Solutions:**
1. Delete `data/cache/gemini_*.json` to force re-analysis
2. Delete `data/{TICKER}_extractions.json` to force re-extraction
3. Check cache file dates

---

## Alternative News Sources

### Polygon.io
- REST API with free tier
- Real-time and historical
- Integration: `src/data/news_sources/polygon_source.py`

### MarketAux
- REST API with free tier
- Financial news
- Integration: `src/data/news_sources/marketaux_source.py`

### Custom Sources
- Implement `NewsDataSource` interface
- See `src/data/news_base.py`
- Register in `src/data/news_fetcher_factory.py`

---

## Verification

### Test Data Loading

```python
from src.data.universe_loader import UniverseLoader

loader = UniverseLoader()
tickers = loader.load_universe(max_tickers=10)
print(f"Loaded {len(tickers)} tickers")
```

### Test News Analysis

```python
from src.signals.news_analyzer import NewsAnalyzer

analyzer = NewsAnalyzer()
signals = analyzer.analyze_news_for_ticker("NVDA", "2023-06-08", "2023-06-15")
print(signals)
```

### Test Gemini Integration

```bash
export GEMINI_API_KEY=your_key
python scripts/test_gemini.py
```

---

See `docs/SUPPLY_CHAIN_DB.md` for supply chain database details.
